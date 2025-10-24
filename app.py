import streamlit as st
import pandas as pd
import math
import subprocess
import sys
import os
import tempfile
import json

# Install Playwright browsers on first run (for Streamlit Cloud)
@st.cache_resource
def install_playwright_browsers():
    try:
        # Install chromium with dependencies
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium", "--with-deps"],
            check=True,
            capture_output=True,
            timeout=300,
            text=True
        )
        return True, "Playwright installed successfully"
    except Exception as e:
        return False, str(e)

# Call once at startup
playwright_status, playwright_msg = install_playwright_browsers()

st.set_page_config(page_title="Attendance Tracker", page_icon="📚", layout="wide")


def create_scraper_script():
    # Enhanced scraper with better error handling and debugging
    return r'''
import asyncio
import sys
import json
from playwright.async_api import async_playwright


async def scrape_attendance_async(roll, password):
    async with async_playwright() as p:
        try:
            # Launch browser with specific args for cloud environments
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu'
                ]
            )
            page = await browser.new_page()

            # Navigate to MIT SIMS
            await page.goto("http://mitsims.in/", wait_until="load", timeout=30000)
            await page.wait_for_timeout(2000)
            
            # Click student link
            await page.click("a#studentLink")
            await page.wait_for_timeout(3000)
            
            # Wait for login form
            await page.wait_for_selector("#stuLogin input.login_box", timeout=15000)
            
            # Fill credentials
            await page.fill("#stuLogin input.login_box:nth-of-type(1)", roll)
            await page.wait_for_timeout(500)
            await page.fill("#stuLogin input.login_box:nth-of-type(2)", password)
            await page.wait_for_timeout(500)
            
            # Submit login
            await page.click("#stuLogin button[type='submit']")
            
            # Wait for page load after login - increased timeout
            await page.wait_for_load_state("networkidle", timeout=30000)
            await page.wait_for_timeout(8000)
            
            # Get page content for debugging
            page_text = await page.inner_text("body")
            
            # Check if login failed
            if "invalid" in page_text.lower() or "incorrect" in page_text.lower():
                await browser.close()
                return {"error": "Invalid credentials", "success": False, "debug": "Login failed"}
            
            # Extract attendance data
            attendance_data = await page.evaluate("""
                () => {
                    const text = document.body.innerText;
                    const lines = text.split("\\n").map(line => line.trim()).filter(line => line);
                    
                    let startIndex = -1;
                    for (let i = 0; i < lines.length; i++) {
                        if (
                            lines[i] === "CLASSES ATTENDED" &&
                            lines[i - 1] === "SUBJECT CODE" &&
                            lines[i + 1] === "TOTAL CONDUCTED"
                        ) {
                            startIndex = i + 3;
                            break;
                        }
                    }
                    
                    if (startIndex === -1) {
                        // Return debug info if pattern not found
                        return [];
                    }
                    
                    const data = [];
                    for (let i = startIndex; i < lines.length; i += 5) {
                        const sno = lines[i];
                        const subject = lines[i + 1];
                        const attended = lines[i + 2];
                        const conducted = lines[i + 3];
                        const percentage = lines[i + 4];
                        
                        if (
                            !sno ||
                            !subject ||
                            !attended ||
                            !conducted ||
                            !percentage ||
                            sno.includes("Note") ||
                            subject.includes("Note") ||
                            sno.includes("@") ||
                            subject.includes("@")
                        ) {
                            break;
                        }
                        
                        if (
                            /^\\d+$/.test(sno) &&
                            /^\\d+$/.test(attended) &&
                            /^\\d+$/.test(conducted) &&
                            /^\\d+\\.?\\d*$/.test(percentage)
                        ) {
                            data.push({
                                s_no: sno,
                                subject: subject,
                                attended: attended,
                                conducted: conducted,
                                percentage: percentage + "%"
                            });
                        }
                    }
                    return data;
                }
            """)
            
            await browser.close()
            
            if not attendance_data or len(attendance_data) == 0:
                return {"error": "No attendance data found on page", "success": False, "debug": "Empty data"}
            
            return {"data": attendance_data, "success": True}
            
        except Exception as error:
            try:
                await browser.close()
            except:
                pass
            return {"error": str(error), "success": False, "debug": str(error)}


if __name__ == "__main__":
    roll = sys.argv[1]
    password = sys.argv[2]
    result = asyncio.run(scrape_attendance_async(roll, password))
    print(json.dumps(result))
'''


def scrape_attendance(roll, password):
    """Run scraper in separate process"""
    try:
        # Create temp script
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(create_scraper_script())
            script_path = f.name

        # Run the scraper
        proc = subprocess.run(
            [sys.executable, script_path, roll, password],
            capture_output=True,
            text=True,
            timeout=120  # Increased timeout
        )

        # Clean up
        os.unlink(script_path)

        if proc.returncode != 0:
            error_msg = proc.stderr.strip() if proc.stderr else "Unknown error"
            raise Exception(f"Process failed: {error_msg}")

        # Parse result
        try:
            result = json.loads(proc.stdout.strip())
        except json.JSONDecodeError:
            raise Exception(f"Could not parse response. Output: {proc.stdout[:200]}")
        
        if not result.get("success", False):
            error = result.get("error", "Unknown error")
            debug = result.get("debug", "")
            raise Exception(f"{error} (Debug: {debug})")

        return result.get("data", [])
        
    except subprocess.TimeoutExpired:
        raise Exception("Timeout - scraping took too long (120s)")
    except Exception as e:
        raise e


def calculate_classes_needed(attended, conducted, target_percentage):
    """Calculate classes needed to reach target"""
    if target_percentage <= 0 or target_percentage > 100:
        return "Invalid"
    if conducted <= 0:
        return 0
    
    target_decimal = target_percentage / 100.0
    current_percentage = (attended / conducted) * 100.0
    
    if current_percentage >= target_percentage:
        return 0
    
    if target_decimal >= 1.0:
        return float('inf')
    
    x = (target_decimal * conducted - attended) / (1 - target_decimal)
    return max(0, math.ceil(x))


def calculate_classes_can_skip(attended, conducted, min_percentage):
    """Calculate classes that can be skipped"""
    if min_percentage < 0 or min_percentage > 100:
        return "Invalid"
    if conducted <= 0:
        return 0
    
    min_decimal = min_percentage / 100.0
    current_percentage = (attended / conducted) * 100.0
    
    if current_percentage < min_percentage:
        return 0
    
    if min_decimal <= 0:
        return float('inf')
    
    x = (attended / min_decimal) - conducted
    return max(0, math.floor(x))


# Session state
if "attendance_data" not in st.session_state:
    st.session_state.attendance_data = None
if "last_roll" not in st.session_state:
    st.session_state.last_roll = ""
if "show_overall_calc" not in st.session_state:
    st.session_state.show_overall_calc = False


# UI
st.title("📚 Attendance Tracker")
st.subheader("Get your attendance data from MIT SIMS")

# Show Playwright status (for debugging)
if not playwright_status:
    st.warning(f"⚠️ Playwright setup issue: {playwright_msg}")

# Login form
with st.form("attendance_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        roll = st.text_input("Roll Number", value=st.session_state.last_roll, placeholder="Enter your roll number")
    
    with col2:
        password = st.text_input("Password", type="password", placeholder="Enter your password")
    
    submit_button = st.form_submit_button("Get Attendance", use_container_width=True)


# Process form
if submit_button:
    if not roll or not password:
        st.error("Please enter both roll number and password")
    else:
        st.session_state.last_roll = roll
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            status_text.text("🔍 Connecting to server...")
            progress_bar.progress(20)
            
            status_text.text("🔐 Logging in...")
            progress_bar.progress(40)
            
            status_text.text("📊 Scraping attendance data (this may take 30-60 seconds)...")
            progress_bar.progress(70)
            
            # Call scraper
            attendance_data = scrape_attendance(roll, password)
            
            progress_bar.progress(100)
            status_text.text("✅ Complete!")
            
            # Clear progress
            progress_bar.empty()
            status_text.empty()
            
            if attendance_data and len(attendance_data) > 0:
                st.session_state.attendance_data = attendance_data
                st.success(f"✅ Attendance data retrieved successfully! Found {len(attendance_data)} subjects")
            else:
                st.warning("⚠️ No attendance data found. This could mean:\n- The portal might be under maintenance\n- Your session might have timed out\n- The page structure has changed")
        
        except Exception as e:
            progress_bar.empty()
            status_text.empty()
            st.error(f"❌ An error occurred: {str(e)}")
            
            with st.expander("🔧 Troubleshooting"):
                st.write("""
                **If you're seeing this error:**
                1. Verify your credentials work on http://mitsims.in manually
                2. Check if the portal is accessible
                3. The portal might be under maintenance
                4. Try again in a few minutes
                
                **Common issues:**
                - Wrong roll number or password format
                - Portal is down or slow
                - Session timeout
                """)


# Display attendance if available
if st.session_state.attendance_data:
    # Convert to DataFrame
    df = pd.DataFrame(st.session_state.attendance_data)
    df.columns = ["S.No", "Subject", "Attended", "Conducted", "Percentage"]
    df["Attended"] = df["Attended"].astype(int)
    df["Conducted"] = df["Conducted"].astype(int)
    df["Percentage_Float"] = df["Percentage"].str.rstrip('%').astype(float)
    
    # Display statistics
    col1, col2, col3 = st.columns(3)
    with col1:
        avg_percentage = df["Percentage_Float"].mean()
        st.metric("Average Attendance", f"{avg_percentage:.1f}%")
    
    with col2:
        total_attended = df["Attended"].sum()
        st.metric("Total Classes Attended", total_attended)
    
    with col3:
        total_conducted = df["Conducted"].sum()
        st.metric("Total Classes Conducted", total_conducted)
    
    # Display data table
    st.subheader("📊 Attendance Details")
    
    def color_percentage(val):
        if val.endswith('%'):
            percentage = float(val.rstrip('%'))
            if percentage >= 75:
                return 'background-color: #d4edda; color: #155724'
            elif percentage >= 60:
                return 'background-color: #fff3cd; color: #856404'
            else:
                return 'background-color: #f8d7da; color: #721c24'
        return ''
    
    display_df = df[["S.No", "Subject", "Attended", "Conducted", "Percentage"]].copy()
    styled_df = display_df.style.applymap(color_percentage, subset=['Percentage'])
    st.dataframe(styled_df, use_container_width=True)
    
    # Overall Total Calculator
    st.subheader("🎯 Attendance Calculator")
    
    # Button to show/hide calculator
    if st.button("🔢 Open Attendance Calculator", use_container_width=True, type="primary"):
        st.session_state.show_overall_calc = not st.session_state.show_overall_calc
    
    # Show calculator if button clicked
    if st.session_state.show_overall_calc:
        st.markdown("---")
        
        # Choice between attend or skip
        calc_type = st.radio(
            "What would you like to calculate?",
            ("📈 Classes to Attend", "📉 Classes to Skip"),
            horizontal=True
        )
        
        # Single input for desired percentage
        desired_percentage = st.number_input(
            "Enter your desired attendance percentage (%)",
            min_value=0,
            max_value=100,
            value=75,
            step=1,
            key="desired_pct"
        )
        
        # Calculate button
        if st.button("Calculate", use_container_width=True, key="calc_overall"):
            if calc_type == "📈 Classes to Attend":
                # Calculate total classes to attend
                total_classes_needed = 0
                impossible_subjects = []
                
                for _, row in df.iterrows():
                    attended = row["Attended"]
                    conducted = row["Conducted"]
                    subject = row["Subject"]
                    
                    classes_needed = calculate_classes_needed(attended, conducted, desired_percentage)
                    
                    if classes_needed == float('inf'):
                        impossible_subjects.append(subject)
                    elif isinstance(classes_needed, (int, float)) and not math.isnan(classes_needed):
                        total_classes_needed += classes_needed
                
                # Display results
                if impossible_subjects:
                    st.warning(f"⚠️ Cannot reach {desired_percentage}% in: {', '.join(impossible_subjects)}")
                
                if total_classes_needed > 0:
                    st.success(f"🎯 **You need to attend {int(total_classes_needed)} more classes to reach {desired_percentage}%**")
                    
                    current_total_attended = df["Attended"].sum()
                    current_total_conducted = df["Conducted"].sum()
                    future_total_attended = current_total_attended + total_classes_needed
                    future_total_conducted = current_total_conducted + total_classes_needed
                    future_overall_percentage = (future_total_attended / future_total_conducted) * 100
                    
                    st.info(f"📈 After attending {int(total_classes_needed)} classes, your overall attendance will be: **{future_overall_percentage:.1f}%**")
                else:
                    current_overall = (df["Attended"].sum() / df["Conducted"].sum()) * 100
                    st.success(f"✅ You already have {current_overall:.1f}% overall attendance! No need to attend extra classes.")
                    
            else:  # Classes to Skip
                # Calculate total classes can skip
                total_classes_can_skip = 0
                below_minimum_subjects = []
                
                for _, row in df.iterrows():
                    attended = row["Attended"]
                    conducted = row["Conducted"]
                    subject = row["Subject"]
                    current_pct = row["Percentage_Float"]
                    
                    if current_pct < desired_percentage:
                        below_minimum_subjects.append(f"{subject} ({current_pct:.1f}%)")
                    else:
                        classes_can_skip = calculate_classes_can_skip(attended, conducted, desired_percentage)
                        
                        if classes_can_skip == float('inf'):
                            total_classes_can_skip = float('inf')
                            break
                        elif isinstance(classes_can_skip, (int, float)) and not math.isnan(classes_can_skip):
                            total_classes_can_skip += classes_can_skip
                
                # Display results
                if below_minimum_subjects:
                    st.error(f"⚠️ These subjects are below {desired_percentage}%: {', '.join(below_minimum_subjects)}")
                
                if total_classes_can_skip == float('inf'):
                    st.success(f"🎉 **You can skip unlimited classes and still maintain {desired_percentage}%!**")
                elif total_classes_can_skip > 0:
                    st.success(f"😎 **You can skip {int(total_classes_can_skip)} classes and still maintain {desired_percentage}%**")
                    
                    current_total_attended = df["Attended"].sum()
                    current_total_conducted = df["Conducted"].sum()
                    future_total_conducted = current_total_conducted + total_classes_can_skip
                    future_overall_percentage = (current_total_attended / future_total_conducted) * 100
                    
                    st.info(f"📉 After skipping {int(total_classes_can_skip)} classes, your overall attendance will be: **{future_overall_percentage:.1f}%**")
                else:
                    st.warning(f"⚠️ You cannot skip any classes while maintaining {desired_percentage}%!")
    
    # Download option
    st.markdown("---")
    csv = display_df.to_csv(index=False)
    st.download_button(
        "📥 Download Attendance as CSV",
        csv,
        f"attendance_{st.session_state.last_roll}.csv",
        "text/csv",
        use_container_width=True
    )


# Instructions
with st.expander("ℹ️ How to use"):
    st.write("""
    1. Enter your MIT SIMS roll number and password
    2. Click 'Get Attendance' to scrape your data (may take 30-60 seconds)
    3. View your attendance statistics and breakdown
    4. Click **Open Attendance Calculator** to calculate total classes across all subjects
    5. Download data as CSV if needed
    
    **Note:** First load may take longer as browser installs.
    """)


# Footer with social links
st.markdown("---")
st.markdown("""
    <div style='text-align: center;'>
        <p>Built with ❤️ using Streamlit and Playwright</p>
        <p style='margin-top: 10px;'>
            <strong>Created by Likith Kumar Chippe</strong><br>
            <a href='https://www.linkedin.com/in/likith-kumar-chippe/' target='_blank' style='margin: 0 10px;'>
                🔗 LinkedIn
            </a> | 
            <a href='https://instagram.com/ft_._likith' target='_blank' style='margin: 0 10px;'>
                📸 Instagram
            </a>
        </p>
    </div>
""", unsafe_allow_html=True)
