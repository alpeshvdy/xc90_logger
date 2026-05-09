// ============================================================
// Google Apps Script - XC90 Logger Data Receiver
// 1. Create new Google Sheet
// 2. Create new Apps Script project (Extensions → Apps Script)
// 3. Replace Code.gs with this script
// 4. Deploy as web app (Execute as: your account, Anyone)
// 5. Copy deployment URL to config.py SHEETS_WEBHOOK_URL
// ============================================================

const SHEET_NAME = "XC90_Logs";  // Google Sheet tab name
const SHEET_ID = "1x410PkWqVuKIS8Dq5XZfnkwocMwZ6ISID5oFtmfKYcU";  // Get from sheet URL

function doPost(e) {
  try {
    const payload = JSON.parse(e.postData.contents);
    const rows = payload.rows || [];
    
    if (rows.length === 0) {
      return ContentService.createTextOutput(JSON.stringify({
        status: "error",
        message: "No rows provided"
      })).setMimeType(ContentService.MimeType.JSON);
    }

    const sheet = SpreadsheetApp.openById(SHEET_ID).getSheetByName(SHEET_NAME);
    
    // Get column headers from first row
    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    
    // Convert each row object to array matching column order
    const dataRows = rows.map(row => 
      headers.map(col => row[col] || "")
    );
    
    // Append to sheet
    if (dataRows.length > 0) {
      sheet.getRange(
        sheet.getLastRow() + 1, 
        1, 
        dataRows.length, 
        dataRows[0].length
      ).setValues(dataRows);
    }

    return ContentService.createTextOutput(JSON.stringify({
      status: "success",
      rows_received: rows.length,
      timestamp: new Date().toISOString()
    })).setMimeType(ContentService.MimeType.JSON);

  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({
      status: "error",
      message: error.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  return ContentService.createTextOutput("XC90 Logger webhook - POST requests only");
}