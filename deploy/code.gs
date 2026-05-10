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

// Full column schema — must match CSV_COLUMNS in logger.py
// AI-ready: one dense row per second, all columns forward-filled
const CSV_HEADERS = [
  "timestamp_utc", "timestamp_local", "trip_id", "trip_sequence",
  "session_odometer", "engine_state", "drive_phase",
  // Critical PIDs (1s)
  "rpm", "coolant_temp_c", "boost_actual_kpa", "vehicle_speed_kph",
  // Standard PIDs (2s)
  "engine_load_pct", "throttle_pos_pct", "stft_pct", "ltft_pct",
  "maf_g_s", "intake_air_temp_c",
  "timing_advance_deg", "fuel_system_status", "o2_lambda",
  "absolute_load_pct",
  // Slow PIDs (5s) — includes derived
  "oil_temp_c", "battery_voltage_v", "baro_pressure_kpa",
  "fuel_pressure_kpa", "ambient_air_temp_c", "engine_run_time_s",
  "dtc_count", "fuel_rate_l_h",
  "fuel_trim_sum", "iat_ambient_delta_c",
  // Metadata
  "raw_pid", "raw_response", "decode_status", "sample_tier",
  "fw_version", "vin_partial"
];

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

    const ss = SpreadsheetApp.openById(SHEET_ID);
    let sheet = ss.getSheetByName(SHEET_NAME);
    
    // Auto-create sheet tab if missing
    if (!sheet) {
      sheet = ss.insertSheet(SHEET_NAME);
    }

    // Always use CSV_HEADERS as authoritative schema
    // Overwrite header row — ensures it matches logger.py CSV_COLUMNS
    // (handles schema migrations when PIDs are added/removed)
    sheet.getRange(1, 1, 1, CSV_HEADERS.length).setValues([CSV_HEADERS]);
    
    // Convert each row object to array matching column order
    // Use explicit check instead of || to preserve falsy values like 0
    const dataRows = rows.map(row =>
      CSV_HEADERS.map(col => (row[col] !== undefined && row[col] !== null) ? row[col] : "")
    );
    
    // Append to sheet
    if (dataRows.length > 0 && dataRows[0].length > 0) {
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