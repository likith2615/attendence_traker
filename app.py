"""
AttendIQ — Python Scraper API
Deploy this FREE on Render.com:
  1. Create GitHub repo, push this file
  2. Go to render.com → New → Web Service → connect your repo
  3. Build Command: pip install -r requirements.txt && playwright install chromium
  4. Start Command: gunicorn app:app
  5. Copy your Render URL into scrape.php PYTHON_SCRAPER_URL
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import asyncio
from playwright.async_api import async_playwright
import os

app = Flask(__name__)
CORS(app)

async def scrape_async(roll, password):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--single-process',
            ]
        )
        try:
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
                return {"success": False, "error": "Invalid credentials"}

            attendance_data = await page.evaluate("""
                () => {
                    const text = document.body.innerText;
                    const lines = text.split("\\n").map(l => l.trim()).filter(l => l);
                    let startIndex = -1;
                    for (let i = 0; i < lines.length; i++) {
                        if (lines[i]==="CLASSES ATTENDED" && lines[i-1]==="SUBJECT CODE" && lines[i+1]==="TOTAL CONDUCTED") {
                            startIndex = i + 3; break;
                        }
                    }
                    if (startIndex === -1) return [];
                    const data = [];
                    for (let i = startIndex; i < lines.length; i += 5) {
                        const [sno, subject, attended, conducted, percentage] = [lines[i],lines[i+1],lines[i+2],lines[i+3],lines[i+4]];
                        if (!sno||!subject||!attended||!conducted||!percentage) break;
                        if (sno.includes("Note")||subject.includes("@")) break;
                        if (/^\\d+$/.test(sno)&&/^\\d+$/.test(attended)&&/^\\d+$/.test(conducted)&&/^\\d+\\.?\\d*$/.test(percentage)) {
                            data.push({ s_no:sno, subject, attended, conducted, percentage: percentage+"%" });
                        }
                    }
                    return data;
                }
            """)

            await browser.close()
            if not attendance_data:
                return {"success": False, "error": "No attendance data found"}
            return {"success": True, "data": attendance_data}

        except Exception as e:
            await browser.close()
            return {"success": False, "error": str(e)}


@app.route('/scrape', methods=['POST'])
def scrape():
    body = request.get_json()
    roll = (body.get('roll') or '').strip()
    password = (body.get('password') or '').strip()
    if not roll or not password:
        return jsonify({'success': False, 'error': 'Missing credentials'})
    try:
        result = asyncio.run(scrape_async(roll, password))
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
