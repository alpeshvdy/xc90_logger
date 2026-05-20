# ============================================================
# GOOGLE SHEETS WEBHOOK SETUP GUIDE
# ============================================================

## Step 1: Get Your Spreadsheet ID
1. Open your Google Sheet (the one you want to log data to)
2. Copy the ID from the URL:
   https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit#gid=0
   
   Example: 1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p

## Step 2: Create Sheet Tab
1. In Google Sheet, create a new tab (sheet) named: `XC90_Logs`
2. Headers are automatically written by the Apps Script on every POST.
   The full schema (37 columns) is defined in `deploy/code.gs` → `CSV_HEADERS`.
   See `docs/SCHEMA.md` for the complete column reference.

## Step 3: Update Apps Script
1. Go back to Apps Script editor (Extensions → Apps Script)
2. Replace the SHEET_ID variable with your actual ID:
   
   const SHEET_ID = "1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p";  // ← Your ID here

3. Save the project (Ctrl+S)
4. Re-deploy (no need to create new version, just update)

## Step 4: Test Again
Run:  python test_webhook.py

Expected output:
  ✅ SUCCESS — 2 rows received by webhook
     Timestamp: 2024-03-15T14:30:25.123Z

## Step 5: Verify in Google Sheet
Check that 2 rows appeared in the XC90_Logs sheet

---

Once this works, the ESP32 logger will automatically upload trip data!
