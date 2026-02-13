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

playwright_status, playwright_msg = install_playwright_browsers()

st.set_page_config(page_title="Attendance Tracker", page_icon="📚", layout="wide")


def create_scraper_script():
    return r'''
import asyncio
import sys
import json
import subprocess

try:
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], 
                   check=True, capture_output=True, timeout=60)
except:
    pass

from playwright.async_api import async_playwright


async def scrape_attendance_async(roll, password):
    async with async_playwright() as p:
        try:
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

            await page.goto("http://mitsims.in/", wait_until="load", timeout=30000)
            await page.wait_for_timeout(2000)
            await page.click("a#studentLink")
            await page.wait_for_timeout(3000)
            await page.wait_for_selector("#stuLogin input.login_box", timeout=15000)
            await page.fill("#stuLogin input.login_box:nth-of-type(1)", roll)
            await page.wait_for_timeout(500)
            await page.fill("#stuLogin input.login_box:nth-of-type(2)", password)
            await page.wait_for_timeout(500)
            await page.click("#stuLogin button[type='submit']")
            await page.wait_for_load_state("networkidle", timeout=30000)
            await page.wait_for_timeout(8000)
            
            page_text = await page.inner_text("body")
            
            if "invalid" in page_text.lower() or "incorrect" in page_text.lower():
                await browser.close()
                return {"error": "Invalid credentials", "success": False}
            
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
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(create_scraper_script())
            script_path = f.name

        env = os.environ.copy()
        env['PLAYWRIGHT_BROWSERS_PATH'] = os.path.expanduser('~/.cache/ms-playwright')
        
        proc = subprocess.run(
            [sys.executable, script_path, roll, password],
            capture_output=True,
            text=True,
            timeout=120,
            env=env
        )

        os.unlink(script_path)

        if proc.returncode != 0:
            error_msg = proc.stderr.strip() if proc.stderr else "Unknown error"
            raise Exception(f"Scraper error: {error_msg[:200]}")

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
    """
    CORRECT FORMULA: x = (T × C - 100 × A) / (100 - T)
    Where: A = attended, C = conducted, T = target percentage
    """
    if target_percentage <= 0 or target_percentage > 100:
        return "Invalid"
    if conducted <= 0:
        return 0
    
    # Calculate current percentage
    current_percentage = (attended / conducted) * 100.0
    
    # If already at or above target
    if current_percentage >= target_percentage:
        return 0
    
    # Edge case: impossible to reach 100%
    if target_percentage >= 100:
        return float('inf')
    
    # CORRECT FORMULA
    numerator = (target_percentage * conducted) - (100 * attended)
    denominator = 100 - target_percentage
    
    x = numerator / denominator
    
    return max(0, math.ceil(x))


def calculate_classes_can_skip(attended, conducted, min_percentage):
    """
    CORRECT FORMULA: x = (100 × A - T × C) / T
    Where: A = attended, C = conducted, T = minimum percentage
    """
    if min_percentage < 0 or min_percentage > 100:
        return "Invalid"
    if conducted <= 0:
        return 0
    
    # Calculate current percentage
    current_percentage = (attended / conducted) * 100.0
    
    # If below minimum
    if current_percentage < min_percentage:
        return 0
    
    # Edge case: if minimum is 0%
    if min_percentage <= 0:
        return float('inf')
    
    # CORRECT FORMULA
    numerator = (100 * attended) - (min_percentage * conducted)
    denominator = min_percentage
    
    x = numerator / denominator
    
    return max(0, math.floor(x))


def calculate_percentage(attended, conducted):
    if conducted <= 0:
        return 0.0
    return (attended / conducted) * 100.0


# Session state
if "attendance_data" not in st.session_state:
    st.session_state.attendance_data = None
if "last_roll" not in st.session_state:
    st.session_state.last_roll = ""
if "show_overall_calc" not in st.session_state:
    st.session_state.show_overall_calc = False

# UI
st.title("📚 Attendance Tracker")
st.subheader("Get your attendance data from MITS IMS by Likith")

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
    df["Scraped_Percentage"] = df["Percentage"].str.rstrip('%').astype(float)
    df["Computed_Percentage"] = df.apply(
        lambda row: calculate_percentage(row["Attended"], row["Conducted"]), axis=1
    )
    total_attended = int(df["Attended"].sum())
    total_conducted = int(df["Conducted"].sum())
    overall_percentage = calculate_percentage(total_attended, total_conducted)

    # Prefer mathematically-correct weighted overall instead of simple mean of percentages.
    mean_percentage = float(df["Computed_Percentage"].mean())
    mismatch_subjects = df[(df["Scraped_Percentage"] - df["Computed_Percentage"]).abs() > 0.1]
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Overall Attendance", f"{overall_percentage:.1f}%", help="Weighted overall percentage based on total attended/total conducted classes")
    with col2:
        st.metric("Total Attended", total_attended)
    with col3:
        st.metric("Total Conducted", total_conducted)

    st.caption(f"Simple average across subjects: {mean_percentage:.1f}% (shown only for comparison)")

    if not mismatch_subjects.empty:
        st.warning(
            f"{len(mismatch_subjects)} subject(s) had scraped percentages that did not match attended/conducted values. "
            "Showing computed percentages for accuracy."
        )
    
    st.subheader("📊 Attendance Details")
    
    def color_percentage(val):
        if val.endswith('%'):
            p = float(val.rstrip('%'))
            if p >= 75: return 'background-color: #d4edda; color: #155724'
            if p >= 60: return 'background-color: #fff3cd; color: #856404'
            return 'background-color: #f8d7da; color: #721c24'
        return ''
    
    display_df = df[["S.No", "Subject", "Attended", "Conducted", "Computed_Percentage"]].copy()
    display_df["Computed_Percentage"] = display_df["Computed_Percentage"].map(lambda value: f"{value:.2f}%")
    display_df = display_df.rename(columns={"Computed_Percentage": "Percentage"})
    st.dataframe(display_df.style.applymap(color_percentage, subset=['Percentage']), use_container_width=True)

    st.subheader("⚡ Interactive Insights")
    target_threshold = st.slider("Set your target attendance", min_value=50, max_value=95, value=75, step=1)

    df["Status"] = df["Computed_Percentage"].apply(lambda x: "On Track" if x >= target_threshold else "Needs Attention")
    st.progress(min(overall_percentage, 100.0) / 100.0, text=f"Overall progress toward classes: {overall_percentage:.2f}%")

    insight_cols = st.columns(2)
    with insight_cols[0]:
        at_risk_count = int((df["Computed_Percentage"] < target_threshold).sum())
        st.metric("Subjects below target", at_risk_count)
    with insight_cols[1]:
        best_subject = df.sort_values("Computed_Percentage", ascending=False).iloc[0]
        st.metric("Best subject", f"{best_subject['Subject']} ({best_subject['Computed_Percentage']:.1f}%)")

    st.bar_chart(df.set_index("Subject")["Computed_Percentage"])

    with st.expander("Subject-wise action plan"):
        selected_subject = st.selectbox("Choose subject", options=df["Subject"].tolist())
        selected_row = df[df["Subject"] == selected_subject].iloc[0]
        subject_attended = int(selected_row["Attended"])
        subject_conducted = int(selected_row["Conducted"])
        subject_current = float(selected_row["Computed_Percentage"])

        st.write(f"Current attendance in **{selected_subject}**: **{subject_current:.2f}%**")

        subject_needed = calculate_classes_needed(subject_attended, subject_conducted, target_threshold)
        subject_skip = calculate_classes_can_skip(subject_attended, subject_conducted, target_threshold)

        if subject_current >= target_threshold:
            st.success(f"You are already above {target_threshold}% in this subject.")
        else:
            st.info(f"Attend **{int(subject_needed)}** more consecutive classes in this subject to reach {target_threshold}%.")

        if subject_skip == float('inf'):
            st.warning(f"You can skip unlimited classes in this subject for a {target_threshold}% target.")
        else:
            st.warning(f"You can skip **{int(subject_skip)}** class(es) in this subject while staying at {target_threshold}%.")
    
    st.subheader("🎯 Attendance Calculator")
    
    if st.button("🔢 Open Calculator", use_container_width=True, type="primary"):
        st.session_state.show_overall_calc = not st.session_state.show_overall_calc
    
    if st.session_state.show_overall_calc:
        st.markdown("---")
        calc_type = st.radio("Calculate:", ("📈 Classes to Attend", "📉 Classes to Skip"), horizontal=True)
        desired_percentage = st.number_input("Desired Attendance Percentage (%)", 0, 100, 75, 1, key="desired_pct")
        
        if st.button("Calculate", use_container_width=True, key="calc"):
            # Get OVERALL totals (not per subject)
            current_overall = calculate_percentage(total_attended, total_conducted)
            
            if calc_type == "📈 Classes to Attend":
                # Check if already at target
                if current_overall >= desired_percentage:
                    st.success(f"🎉 **You already have {current_overall:.2f}% attendance!**")
                    st.info(f"Your target is {desired_percentage}%. No need to attend extra classes! ✅")
                else:
                    # Calculate using CORRECT FORMULA for OVERALL attendance
                    classes_needed = calculate_classes_needed(total_attended, total_conducted, desired_percentage)
                    
                    if classes_needed == float('inf'):
                        st.warning(f"⚠️ Impossible to reach {desired_percentage}%")
                    elif classes_needed > 0:
                        # Calculate future overall percentage
                        future_attended = total_attended + classes_needed
                        future_conducted = total_conducted + classes_needed
                        future_overall = (future_attended / future_conducted) * 100
                        
                        st.success(f"🎯 **You need to attend {int(classes_needed)} more classes**")
                        st.info(f"📊 **Current:** {current_overall:.2f}% → **After:** {future_overall:.2f}%")
                        st.caption(f"Formula: ({total_attended} + {int(classes_needed)}) / ({total_conducted} + {int(classes_needed)}) = {future_overall:.2f}%")
                        st.caption(f"Calculation: ({desired_percentage} × {total_conducted} - 100 × {total_attended}) / (100 - {desired_percentage}) = {classes_needed:.1f} ≈ {int(classes_needed)}")
                    else:
                        st.success(f"✅ You're already at {current_overall:.2f}%!")
                        
            else:  # Classes to Skip
                # Check if below minimum
                if current_overall < desired_percentage:
                    st.error(f"⚠️ **Your current attendance is {current_overall:.2f}%**")
                    st.warning(f"You're below {desired_percentage}%. Cannot skip any classes!")
                else:
                    # Calculate using CORRECT FORMULA for OVERALL attendance
                    classes_can_skip = calculate_classes_can_skip(total_attended, total_conducted, desired_percentage)
                    
                    if classes_can_skip == float('inf'):
                        st.success(f"🎉 **You can skip unlimited classes!** (theoretical)")
                        st.info(f"Current attendance: {current_overall:.2f}%")
                    elif classes_can_skip > 0:
                        # Calculate future overall percentage after skipping
                        future_conducted = total_conducted + classes_can_skip
                        future_overall = (total_attended / future_conducted) * 100
                        
                        st.success(f"😎 **You can skip {int(classes_can_skip)} classes**")
                        st.info(f"📊 **Current:** {current_overall:.2f}% → **After:** {future_overall:.2f}%")
                        st.caption(f"Formula: {total_attended} / ({total_conducted} + {int(classes_can_skip)}) = {future_overall:.2f}%")
                        st.caption(f"Calculation: (100 × {total_attended} - {desired_percentage} × {total_conducted}) / {desired_percentage} = {classes_can_skip:.1f} ≈ {int(classes_can_skip)}")
                    else:
                        st.warning(f"⚠️ Cannot skip any classes while maintaining {desired_percentage}%")
    
    csv = display_df.to_csv(index=False)
    st.download_button("📥 Download CSV", csv, f"attendance_{st.session_state.last_roll}.csv", "text/csv", use_container_width=True)

with st.expander("ℹ️ How to use"):
    st.write("""
    **Steps:**
    1. Enter your MITS IMS credentials
    2. Wait 30-60 seconds for scraping
    3. View your attendance details
    4. Use calculator to plan ahead
    5. Download data as CSV
    
    **Calculator Formulas:**
    - **To Attend:** x = (T × C - 100 × A) / (100 - T)
    - **To Skip:** x = (100 × A - T × C) / T
    
    Where: A = attended, C = conducted, T = target %
    """)

st.markdown("---")
st.markdown("""
    <div style='text-align: center;'>
        <p>Built with ❤️ by <strong>Likith Kumar Chippe</strong></p>
        <a href='https://www.linkedin.com/in/likith-kumar-chippe/' target='_blank'>🔗 LinkedIn</a> | 
        <a href='https://instagram.com/ft_._likith' target='_blank'>📸 Instagram</a>
    </div>
""", unsafe_allow_html=True)


