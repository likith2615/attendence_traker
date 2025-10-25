# 📚 Attendance Tracker

**Attendance Tracker** is a powerful Streamlit web application that automatically scrapes your attendance data from the [MIT SIMS Portal](http://mitsims.in) and provides intelligent calculators to help you strategically plan your classes!

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://ims-tracker.streamlit.app/)

---

## ✨ Features

### 🔐 Automated Data Scraping
- Securely logs into MIT SIMS using Playwright automation
- Fetches real-time attendance data for all your subjects
- No manual data entry required!

### 📊 Visual Dashboard
- Clear attendance summary with color-coded indicators
- Subject-wise breakdown with percentages
- Overall attendance metrics at a glance

### 🧮 Smart Calculators
**1. Classes to Attend Calculator**
- Calculate exactly how many classes you need to reach your target percentage
- Formula: `x = (T × C - 100 × A) / (100 - T)`

**2. Classes to Skip Calculator**
- Find out how many classes you can safely skip
- Formula: `x = (100 × A - T × C) / T`

### 📈 Additional Features
- **Color-Coded Indicators**
  - 🟢 Green (≥75%): Good attendance
  - 🟡 Yellow (60-74%): Moderate attendance
  - 🔴 Red (<60%): Low attendance
- **CSV Export**: Download your attendance data
- **Mobile Responsive**: Works on all devices
- **Real-time Calculations**: Instant results with formula breakdown

---

## 🧮 How It Works

### Example Calculation

**Current Status:**
- Total Attended (A) = 274 classes
- Total Conducted (C) = 361 classes
- Current Percentage = 75.9%

**Scenario 1: Reach 76% attendance**
