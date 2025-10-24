import streamlit as st
import pandas as pd
import math
import subprocess
import sys
import os
import tempfile
import json

# Install Playwright browsers ONLY (without system dependencies)
@st.cache_resource
def install_playwright_browsers():
    try:
        # Install ONLY chromium without system deps (works on Streamlit Cloud)
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
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
    # Enhanced scraper - installs playwright in subprocess too
    return r'''
import asyncio
import sys
import json
import subprocess

# Install playwright browsers in this subprocess too
try:
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], 
                   check=True, capture_output=True, timeout=60)
except:
    pass  # Already installed

from playwright.async_api import async_playwright


async def scrape_attendance_async(roll, password):
    async with async_playwright() as p:
        try:
            # Launch browser with cloud-friendly args
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--single-process',
                    '--disable-web-security'
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
            
            # Wait for page load after login
            await page.wait_for_load_state("networkidle", timeout=30000)
            await page.wait_for_timeout(8000)
            
            # Get page content
            page_text = await page.inner_text("body")
            
            # Check if login failed
            if "invalid" in page_text.lower() or "incorrect" in page_text.lower():
                await browser.close()
                return {"error": "Invalid credentials", "success": False}
            
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
                    
                    if (startIndex === -1) return [];
                    
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
                return {"error": "No attendance data found", "success": False}
            
            return {"data": attendance_data, "success": True}
            
        except Exception as error:
            try:
                await browser.close()
            except:
                pass
            return {"error": str(error), "success": False}


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

        # Run the scraper with environment variables for Playwright
        env = os.environ.copy()
        env['PLAYWRIGHT_BROWSERS_PATH'] = os.path.expanduser('~/.cache/ms-playwright')
        
        proc = subprocess.run(
            [sys.executable, script_path, roll, password],
            capture_output=True,
            text=True,
            timeout=120,
            env=env
        )

        # Clean up
        os.unlink(script_path)

        if proc.returncode != 0:
            error_msg = proc.stderr.strip() if proc.stderr else "Unknown error"
            raise Exception(f"Scraper error: {error_msg[:200]}")

        # Parse result
        try:
            result = json.loads(proc.stdout.strip())
        except json.JSONDecodeError:
            raise Exception(f"Could not parse response")
        
        if not result.get("success", False):
            error = result.get("error", "Unknown error")
            raise Exception(error)

        return result.get("data", [])
        
    except subprocess.TimeoutExpired:
        raise Exception("Timeout - scraping took too long")
    except Exception as e:
        raise e


def calculate_classes_needed(attended, conducted, target_percentage):
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
            status_text.text("🔍 Initializing browser...")
            progress_bar.progress(20)
            status_text.text("🔐 Logging in...")
            progress_bar.progress(40)
            status_text.text("📊 Scraping attendance (30-60s)...")
            progress_bar.progress(70)
            
            attendance_data = scrape_attendance(roll, password)
            
            progress_bar.progress(100)
            status_text.text("✅ Complete!")
            progress_bar.empty()
            status_text.empty()
            
            if attendance_data and len(attendance_data) > 0:
                st.session_state.attendance_data = attendance_data
                st.success(f"✅ Found {len(attendance_data)} subjects!")
            else:
                st.warning("⚠️ No data found")
        except Exception as e:
            progress_bar.empty()
            status_text.empty()
            st.error(f"❌ Error: {str(e)}")

# Display attendance
if st.session_state.attendance_data:
    df = pd.DataFrame(st.session_state.attendance_data)
    df.columns = ["S.No", "Subject", "Attended", "Conducted", "Percentage"]
    df["Attended"] = df["Attended"].astype(int)
    df["Conducted"] = df["Conducted"].astype(int)
    df["Percentage_Float"] = df["Percentage"].str.rstrip('%').astype(float)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Average Attendance", f"{df['Percentage_Float'].mean():.1f}%")
    with col2:
        st.metric("Total Attended", int(df["Attended"].sum()))
    with col3:
        st.metric("Total Conducted", int(df["Conducted"].sum()))
    
    st.subheader("📊 Attendance Details")
    
    def color_percentage(val):
        if val.endswith('%'):
            p = float(val.rstrip('%'))
            if p >= 75: return 'background-color: #d4edda; color: #155724'
            if p >= 60: return 'background-color: #fff3cd; color: #856404'
            return 'background-color: #f8d7da; color: #721c24'
        return ''
    
    display_df = df[["S.No", "Subject", "Attended", "Conducted", "Percentage"]].copy()
    st.dataframe(display_df.style.applymap(color_percentage, subset=['Percentage']), use_container_width=True)
    
    st.subheader("🎯 Attendance Calculator")
    
    if st.button("🔢 Open Calculator", use_container_width=True, type="primary"):
        st.session_state.show_overall_calc = not st.session_state.show_overall_calc
    
    if st.session_state.show_overall_calc:
        st.markdown("---")
        calc_type = st.radio("Calculate:", ("📈 Classes to Attend", "📉 Classes to Skip"), horizontal=True)
        desired_percentage = st.number_input("Desired %", 0, 100, 75, 1, key="desired_pct")
        
        if st.button("Calculate", use_container_width=True, key="calc"):
            if calc_type == "📈 Classes to Attend":
                total = 0
                for _, row in df.iterrows():
                    need = calculate_classes_needed(row["Attended"], row["Conducted"], desired_percentage)
                    if isinstance(need, (int, float)) and need != float('inf'):
                        total += need
                if total > 0:
                    st.success(f"🎯 **Attend {int(total)} more classes to reach {desired_percentage}%**")
                else:
                    st.success(f"✅ Already at {desired_percentage}%!")
            else:
                total = 0
                for _, row in df.iterrows():
                    if row["Percentage_Float"] >= desired_percentage:
                        skip = calculate_classes_can_skip(row["Attended"], row["Conducted"], desired_percentage)
                        if isinstance(skip, (int, float)) and skip != float('inf'):
                            total += skip
                if total > 0:
                    st.success(f"😎 **Can skip {int(total)} classes and maintain {desired_percentage}%**")
                else:
                    st.warning(f"⚠️ Cannot skip any classes")
    
    csv = display_df.to_csv(index=False)
    st.download_button("📥 Download CSV", csv, f"attendance_{st.session_state.last_roll}.csv", "text/csv", use_container_width=True)

with st.expander("ℹ️ How to use"):
    st.write("1. Enter credentials\n2. Wait 30-60s\n3. View results\n4. Use calculator\n5. Download CSV")

st.markdown("---")
st.markdown("""
    <div style='text-align: center;'>
        <p>Built with ❤️ by <strong>Likith Kumar Chippe</strong></p>
        <a href='https://www.linkedin.com/in/likith-kumar-chippe/' target='_blank'>🔗 LinkedIn</a> | 
        <a href='https://instagram.com/ft_._likith' target='_blank'>📸 Instagram</a>
    </div>
""", unsafe_allow_html=True)
