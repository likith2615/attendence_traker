import { chromium } from "playwright";

export async function scrapeAttendance(roll, pass) {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  try {
    await page.goto("http://mitsims.in/", { waitUntil: "load" });
    await page.click("a#studentLink");
    await page.waitForSelector("#stuLogin input.login_box", { timeout: 15000 });
    await page.fill("#stuLogin input.login_box:nth-of-type(1)", roll);
    await page.fill("#stuLogin input.login_box:nth-of-type(2)", pass);
    await page.click("#stuLogin button[type='submit']");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(5000);

    const attendanceData = await page.evaluate(() => {
      const text = document.body.innerText;
      const lines = text.split("\n").map(line => line.trim()).filter(line => line);

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
          /^\d+$/.test(sno) &&
          /^\d+$/.test(attended) &&
          /^\d+$/.test(conducted) &&
          /^\d+\.?\d*$/.test(percentage)
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
    });

    await browser.close();
    return attendanceData;
  } catch (error) {
    await browser.close();
    throw error;
  }
}
