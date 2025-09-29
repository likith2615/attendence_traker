const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({ headless: false, slowMo: 70 });
  const page = await browser.newPage();

  try {
    // 1. Login process
    console.log("🌐 Opening IMS website...");
    await page.goto("http://mitsims.in/", { waitUntil: "load" });
    await page.click("a#studentLink");
    await page.waitForSelector("#stuLogin input.login_box", { timeout: 15000 });
    await page.fill("#stuLogin input.login_box:nth-of-type(1)", "24691A05Q2");
    await page.fill("#stuLogin input.login_box:nth-of-type(2)", "Likith@26");
    await page.click("#stuLogin button[type='submit']");

    // 2. Wait for dashboard to load
    console.log("⏳ Waiting for dashboard to load...");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(5000);

    // 3. Extract and parse attendance data
    console.log("📊 Extracting attendance data...");
    const attendanceData = await page.evaluate(() => {
      const text = document.body.innerText;
      const lines = text.split("\n").map(line => line.trim()).filter(line => line);

      // Find the start of attendance data
      let startIndex = -1;
      for (let i = 0; i < lines.length; i++) {
        if (
          lines[i] === "CLASSES ATTENDED" &&
          lines[i - 1] === "SUBJECT CODE" &&
          lines[i + 1] === "TOTAL CONDUCTED"
        ) {
          startIndex = i + 3; // Start after "ATTENDANCE %"
          break;
        }
      }
      if (startIndex === -1) return [];

      const data = [];
      // Parse data in groups of 5 (S.NO, SUBJECT, ATTENDED, CONDUCTED, PERCENTAGE)
      for (let i = startIndex; i < lines.length; i += 5) {
        const sno = lines[i];
        const subject = lines[i + 1];
        const attended = lines[i + 2];
        const conducted = lines[i + 3];
        const percentage = lines[i + 4];

        // Stop if we hit the note section or end
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

        // Validate the data format
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

    // 4. Display results in formatted table with overall average
    if (attendanceData.length > 0) {
      // Calculate total and average
      const totalAttended = attendanceData.reduce((sum, r) => sum + parseInt(r.attended, 10), 0);
      const totalConducted = attendanceData.reduce((sum, r) => sum + parseInt(r.conducted, 10), 0);
      const overallAvg = ((totalAttended / totalConducted) * 100).toFixed(2) + "%";

      console.log("\n✅ ATTENDANCE DATA EXTRACTED SUCCESSFULLY!\n");

      // Print formatted table (individual records)
      console.log("┌─────┬─────────────────────┬──────────┬───────────┬─────────────┐");
      console.log("│ S.NO│ SUBJECT CODE        │ ATTENDED │ CONDUCTED │ ATTENDANCE %│");
      console.log("├─────┼─────────────────────┼──────────┼───────────┼─────────────┤");

      attendanceData.forEach(row => {
        console.log(
          `│ ${row.s_no.padEnd(3)} │ ${row.subject.padEnd(19)} │ ${row.attended.padEnd(8)} │ ${row.conducted.padEnd(9)} │ ${row.percentage.padEnd(11)} │`
        );
      });

      console.log("└─────┴─────────────────────┴──────────┴───────────┴─────────────┘");

      // Print overall average outside the table
      console.log(`\n📊 Overall Attendance Average: ${overallAvg}\n`);

      // Also print as console.table for quick view
      console.log("\n📊 Console Table Format:");
      console.table(attendanceData);
    } else {
      console.log("❌ No attendance data found.");
    }

    console.log("\n🔍 Browser kept open for inspection...");
  } catch (error) {
    console.error("❌ Error:", error.message);
  }
})();