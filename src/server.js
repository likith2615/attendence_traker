import express from "express";
import bodyParser from "body-parser";
import cors from "cors";
import path from "path";
import { fileURLToPath } from "url";
import { scrapeAttendance } from "./scraper.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
app.use(cors());
app.use(bodyParser.json());

// Serve frontend static files from public folder
app.use(express.static(path.join(__dirname, "src", "public")));

app.get("/", (req, res) => {
  res.sendFile(path.join(__dirname, "src", "public", "index.html"));
});

// API endpoint for attendance scraping
app.post("/api/attendance", async (req, res) => {
  const { roll, pass } = req.body;

  if (!roll || !pass) {
    return res.status(400).json({ error: "Roll and password required" });
  }

  try {
    const data = await scrapeAttendance(roll, pass);
    res.json({ data });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server listening at http://localhost:${PORT}`);
});

console.log('Static folder is:', path.join(__dirname, "public"));
