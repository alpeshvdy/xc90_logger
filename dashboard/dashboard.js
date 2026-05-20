// ============================================================
// XC90 Logger — Dashboard JavaScript
// Fetches from Google Sheets gviz endpoint, renders gauges & charts
// ============================================================

// --- CONFIGURATION ----------------------------------------------------------
// Replace with your Google Sheet ID (from the sheet URL)
// Or use the input field in the UI
const DEFAULT_SHEET_ID = "1x410PkWqVuKIS8Dq5XZfnkwocMwZ6ISID5oFtmfKYcU";
const DEFAULT_SHEET_NAME = "XC90_Logs";

// Column schema — must match CSV_COLUMNS in logger.py
const COLUMNS = [
  "timestamp_utc", "timestamp_local", "trip_id", "trip_sequence",
  "session_odometer", "engine_state", "drive_phase",
  "rpm", "coolant_temp_c", "boost_actual_kpa", "vehicle_speed_kph",
  "engine_load_pct", "throttle_pos_pct", "stft_pct", "ltft_pct",
  "maf_g_s", "intake_air_temp_c", "timing_advance_deg",
  "fuel_system_status", "o2_lambda", "absolute_load_pct",
  "oil_temp_c", "battery_voltage_v", "baro_pressure_kpa",
  "fuel_pressure_kpa", "ambient_air_temp_c", "engine_run_time_s",
  "dtc_count", "fuel_rate_l_h", "fuel_trim_sum", "iat_ambient_delta_c",
  "raw_pid", "raw_response", "decode_status", "sample_tier",
  "fw_version", "vin_partial"
];

// --- STATE ------------------------------------------------------------------
let allRows = [];         // parsed rows (flat objects)
let trips = [];           // aggregated trip summaries
let currentTrip = null;   // trip_id currently viewed in detail
let charts = {};          // Chart.js instances { key: Chart }

// --- DOM ELEMENTS -----------------------------------------------------------
const $sheetId = document.getElementById("sheet-id");
const $sheetName = document.getElementById("sheet-name");
const $btnLoad = document.getElementById("btn-load");
const $statusText = document.getElementById("status-text");
const $statusMeta = document.getElementById("status-meta");
const $configPanel = document.getElementById("config-panel");
const $tripListPanel = document.getElementById("trip-list-panel");
const $tripDetailPanel = document.getElementById("trip-detail-panel");
const $trendsPanel = document.getElementById("trends-panel");
const $tripTbody = document.getElementById("trip-tbody");
const $tripDetailTitle = document.getElementById("trip-detail-title");
const $phaseBar = document.getElementById("phase-bar");
const $btnBack = document.getElementById("btn-back");
const $btnBackTrends = document.getElementById("btn-back-trends");
const $btnTrends = document.getElementById("btn-trends");
const $footerUpdated = document.getElementById("footer-updated");

// Seed the input with the default
$sheetId.placeholder = DEFAULT_SHEET_ID;

// --- INITIALIZATION ---------------------------------------------------------
// Guard against Chart.js CDN failure
if (typeof Chart === "undefined") {
  document.getElementById("status-bar").textContent = "Chart.js failed to load — check your internet connection";
  document.getElementById("status-bar").className = "status-bar status-error";
  throw new Error("Chart.js not loaded");
}

$btnLoad.addEventListener("click", loadData);
$btnBack.addEventListener("click", showTripList);
$btnBackTrends.addEventListener("click", showTripList);
$btnTrends.addEventListener("click", showTrends);

// Allow Enter key to trigger load
$sheetId.addEventListener("keydown", (e) => { if (e.key === "Enter") loadData(); });
$sheetName.addEventListener("keydown", (e) => { if (e.key === "Enter") loadData(); });

// --- DATA FETCHING ----------------------------------------------------------

async function loadData() {
  const sheetId = $sheetId.value.trim() || DEFAULT_SHEET_ID;
  const sheetName = $sheetName.value.trim() || DEFAULT_SHEET_NAME;

  setStatus("Fetching data from Google Sheets…", "loading");

  try {
    const url = `https://docs.google.com/spreadsheets/d/${sheetId}/gviz/tq?tqx=out:json&sheet=${encodeURIComponent(sheetName)}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    const text = await res.text();

    // Unwrap Google's JSONP wrapper: /*O_o*/google.visualization.Query.setResponse({…});
    const match = text.match(/\{[\s\S]*\}/);
    if (!match) throw new Error("Could not parse gviz response — check Sheet ID and sharing settings");

    const json = JSON.parse(match[0]);

    if (json.status === "error") {
      throw new Error(json.errors?.map(e => e.detailed_message).join("; ") || "Unknown gviz error");
    }

    if (!json.table || !json.table.rows) {
      throw new Error("Sheet is empty — no data rows found");
    }

    parseRows(json.table);
    buildTrips();
    renderAll();

    setStatus(
      `Loaded ${allRows.length.toLocaleString()} rows across ${trips.length} trips`,
      "success"
    );

  } catch (err) {
    setStatus(`Error: ${err.message}`, "error");
    console.error(err);
  }
}

// --- PARSING ----------------------------------------------------------------

function parseRows(table) {
  // Google gviz may return column labels; fall back to our COLUMNS array
  const labels = table.cols.map(c => c.label);

  allRows = table.rows.map(r => {
    const row = {};
    r.c.forEach((cell, i) => {
      const colName = (labels[i] && labels[i].trim()) || COLUMNS[i] || `col_${i}`;
      const val = cell?.v;
      // Convert numeric strings to numbers
      if (val === null || val === undefined || val === "") {
        row[colName] = null;
      } else if (!isNaN(val) && val !== "" && typeof val !== "boolean") {
        row[colName] = Number(val);
      } else {
        row[colName] = val;
      }
    });
    return row;
  });

  // Filter out the header row if Google included it
  allRows = allRows.filter(r => {
    const ts = r.timestamp_utc;
    return ts && String(ts).match(/^\d{4}-\d{2}-\d{2}/);
  });

  // Sort by timestamp ascending (ensures last row = latest for gauges)
  allRows.sort((a, b) => {
    const ta = a.timestamp_utc || "";
    const tb = b.timestamp_utc || "";
    return ta.localeCompare(tb);
  });
}

// --- TRIP AGGREGATION -------------------------------------------------------

function buildTrips() {
  const tripMap = {};

  allRows.forEach(row => {
    const tid = row.trip_id || "unknown";
    if (!tripMap[tid]) {
      tripMap[tid] = {
        trip_id: tid,
        rows: [],
        startTime: null,
        endTime: null,
        maxRpm: 0,
        maxBoost: 0,
        maxSpeed: 0,
        sumCoolant: 0,
        coolantCount: 0,
      };
    }

    const t = tripMap[tid];
    t.rows.push(row);

    const rpm = row.rpm;
    const boost = row.boost_actual_kpa;
    const speed = row.vehicle_speed_kph;
    const coolant = row.coolant_temp_c;

    if (rpm != null && rpm > t.maxRpm) t.maxRpm = rpm;
    if (boost != null && boost > t.maxBoost) t.maxBoost = boost;
    if (speed != null && speed > t.maxSpeed) t.maxSpeed = speed;
    if (coolant != null) {
      t.sumCoolant += coolant;
      t.coolantCount++;
    }
  });

  trips = Object.values(tripMap).map(t => {
    // Rows come from Sheets in insertion order (already sorted by trip_sequence)
    const sorted = t.rows;
    const first = sorted[0];
    const last = sorted[sorted.length - 1];
    const durationSec = first && last
      ? (new Date(last.timestamp_utc) - new Date(first.timestamp_utc)) / 1000
      : 0;
    const distance = last?.session_odometer ?? 0;

    return {
      trip_id: t.trip_id,
      rowCount: t.rows.length,
      startTime: first?.timestamp_utc ?? null,
      endTime: last?.timestamp_utc ?? null,
      durationSec,
      distanceKm: distance,
      maxRpm: t.maxRpm,
      maxBoost: t.maxBoost,
      maxSpeed: t.maxSpeed,
      avgCoolant: t.coolantCount > 0 ? t.sumCoolant / t.coolantCount : null,
      rows: sorted,
    };
  });

  // Sort by start time descending (newest first)
  trips.sort((a, b) => (b.startTime || "").localeCompare(a.startTime || ""));
}

// --- RENDERING --------------------------------------------------------------

function renderAll() {
  renderGauges();
  renderTripList();
  $tripListPanel.style.display = "";
  $tripDetailPanel.style.display = "none";
  $trendsPanel.style.display = "none";
}

// --- GAUGES -----------------------------------------------------------------

function destroyCharts(...keys) {
  keys.forEach(k => {
    if (charts[k]) { charts[k].destroy(); delete charts[k]; }
  });
}

function createGauge(canvasId, value, min, max, unit, colorZones) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  // Normalize value between 0 and 1 for the gauge
  const pct = Math.max(0, Math.min(1, (value - min) / (max - min)));

  // Determine color based on zones
  let color = "#4fd1c5"; // default teal
  if (colorZones) {
    for (const zone of colorZones) {
      if (value >= zone.min && value < zone.max) {
        color = zone.color;
        break;
      }
    }
  }

  const ctx = canvas.getContext("2d");
  const chart = new Chart(ctx, {
    type: "doughnut",
    data: {
      datasets: [{
        data: [pct, 1 - pct],
        backgroundColor: [color, "#1e293b"],
        borderWidth: 0,
        circumference: 270,
        rotation: 225,
        cutout: "75%",
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      animation: { duration: 0 },
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false },
      },
    },
    plugins: [{
      id: "centerText",
      afterDraw(chart) {
        const { ctx, width, height } = chart;
        ctx.save();
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";

        // Value
        const valStr = value != null ? (Number.isInteger(value) ? value.toString() : value.toFixed(1)) : "--";
        ctx.font = `bold ${Math.round(height * 0.18)}px "JetBrains Mono", "SF Mono", monospace`;
        ctx.fillStyle = "#e2e8f0";
        ctx.fillText(valStr, width / 2, height * 0.42);

        // Unit
        ctx.font = `${Math.round(height * 0.09)}px "Inter", sans-serif`;
        ctx.fillStyle = "#94a3b8";
        ctx.fillText(unit, width / 2, height * 0.6);

        ctx.restore();
      },
    }],
  });

  return chart;
}

function renderGauges() {
  if (allRows.length === 0) return;

  const last = allRows[allRows.length - 1];

  destroyCharts("gauge-rpm", "gauge-coolant", "gauge-boost", "gauge-speed", "gauge-battery");

  charts["gauge-rpm"] = createGauge("gauge-rpm", last.rpm, 0, 7000, "RPM", [
    { min: 0, max: 900, color: "#f59e0b" },
    { min: 900, max: 3000, color: "#4fd1c5" },
    { min: 3000, max: 5500, color: "#3b82f6" },
    { min: 5500, max: 7000, color: "#ef4444" },
  ]);

  charts["gauge-coolant"] = createGauge("gauge-coolant", last.coolant_temp_c, 0, 120, "°C", [
    { min: 0, max: 60, color: "#3b82f6" },
    { min: 60, max: 85, color: "#4fd1c5" },
    { min: 85, max: 100, color: "#f59e0b" },
    { min: 100, max: 120, color: "#ef4444" },
  ]);

  charts["gauge-boost"] = createGauge("gauge-boost", last.boost_actual_kpa, 0, 250, "kPa", [
    { min: 0, max: 105, color: "#4fd1c5" },
    { min: 105, max: 160, color: "#3b82f6" },
    { min: 160, max: 250, color: "#ef4444" },
  ]);

  charts["gauge-speed"] = createGauge("gauge-speed", last.vehicle_speed_kph, 0, 220, "km/h", [
    { min: 0, max: 60, color: "#4fd1c5" },
    { min: 60, max: 120, color: "#3b82f6" },
    { min: 120, max: 220, color: "#ef4444" },
  ]);

  charts["gauge-battery"] = createGauge("gauge-battery", last.battery_voltage_v, 10, 16, "V", [
    { min: 10, max: 12, color: "#ef4444" },
    { min: 12, max: 13.5, color: "#f59e0b" },
    { min: 13.5, max: 14.8, color: "#4fd1c5" },
    { min: 14.8, max: 16, color: "#f59e0b" },
  ]);

  $footerUpdated.textContent = `Latest: ${last.timestamp_utc || "--"}`;
}

// --- TRIP LIST --------------------------------------------------------------

function renderTripList() {
  $tripTbody.innerHTML = "";

  if (trips.length === 0) {
    $tripTbody.innerHTML = `<tr><td colspan="9" class="empty-msg">No trips found</td></tr>`;
    return;
  }

  trips.forEach(t => {
    const date = t.startTime ? new Date(t.startTime).toLocaleDateString("en-CA") : "--";
    const time = t.startTime ? new Date(t.startTime).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) : "--";
    const durMin = Math.floor(t.durationSec / 60);
    const durSec = Math.round(t.durationSec % 60);
    const duration = t.durationSec > 0 ? `${durMin}:${String(durSec).padStart(2, "0")}` : "--";

    const tr = document.createElement("tr");
    tr.className = "trip-row";
    tr.innerHTML = `
      <td class="trip-id-cell">${escHtml(t.trip_id)}</td>
      <td>${date} ${time}</td>
      <td>${duration}</td>
      <td>${t.distanceKm > 0 ? t.distanceKm.toFixed(1) : "--"}</td>
      <td>${t.maxRpm > 0 ? Math.round(t.maxRpm) : "--"}</td>
      <td>${t.maxBoost > 0 ? t.maxBoost.toFixed(1) : "--"}</td>
      <td>${t.maxSpeed > 0 ? Math.round(t.maxSpeed) : "--"}</td>
      <td>${t.avgCoolant != null ? t.avgCoolant.toFixed(0) : "--"}</td>
      <td>${t.rowCount.toLocaleString()}</td>
    `;
    tr.addEventListener("click", () => showTripDetail(t.trip_id));
    $tripTbody.appendChild(tr);
  });
}

// --- TRIP DETAIL ------------------------------------------------------------

function showTripDetail(tripId) {
  const trip = trips.find(t => t.trip_id === tripId);
  if (!trip || trip.rows.length === 0) return;

  currentTrip = tripId;
  $tripDetailTitle.textContent = tripId;
  $tripListPanel.style.display = "none";
  $trendsPanel.style.display = "none";
  $tripDetailPanel.style.display = "";

  // Scroll to detail
  $tripDetailPanel.scrollIntoView({ behavior: "smooth", block: "start" });

  renderPhaseBar(trip);
  renderTripCharts(trip);
}

function renderPhaseBar(trip) {
  const phases = { idle: 0, light: 0, moderate: 0, hard: 0, decel: 0 };
  trip.rows.forEach(r => {
    const p = r.drive_phase;
    if (phases[p] !== undefined) phases[p]++;
  });
  const total = trip.rows.length || 1;

  const colors = {
    idle: "#f59e0b",
    light: "#4fd1c5",
    moderate: "#3b82f6",
    hard: "#ef4444",
    decel: "#8b5cf6",
  };

  let html = "";
  for (const [phase, count] of Object.entries(phases)) {
    const pct = ((count / total) * 100).toFixed(1);
    if (count > 0) {
      html += `<span class="phase-seg" style="background:${colors[phase]};flex:${count}">
        <span class="phase-label">${phase} ${pct}%</span>
      </span>`;
    }
  }

  $phaseBar.innerHTML = html;
}

function showTripList() {
  currentTrip = null;
  $tripDetailPanel.style.display = "none";
  $trendsPanel.style.display = "none";
  $tripListPanel.style.display = "";

  // Destroy detail/trends charts to free memory
  destroyCharts(
    "chart-rpm", "chart-boost-speed", "chart-coolant-iat",
    "chart-fuel-trims", "chart-throttle-load",
    "chart-trend-coolant", "chart-trend-battery"
  );

  $tripListPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

// --- TRENDS (30-DAY) -------------------------------------------------------

function showTrends() {
  if (allRows.length === 0) return;

  currentTrip = null;
  $tripListPanel.style.display = "none";
  $tripDetailPanel.style.display = "none";
  $trendsPanel.style.display = "";

  // Destroy detail charts to free memory
  destroyCharts(
    "chart-rpm", "chart-boost-speed", "chart-coolant-iat",
    "chart-fuel-trims", "chart-throttle-load"
  );

  renderTrends();
  $trendsPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderTrends() {
  // Show last 30 days of data
  const now = new Date();
  const thirtyDaysAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);

  const recentRows = allRows.filter(r => {
    const ts = r.timestamp_utc;
    return ts && new Date(ts) >= thirtyDaysAgo;
  });

  if (recentRows.length === 0) {
    destroyCharts("chart-trend-coolant", "chart-trend-battery");
    $trendsPanel.querySelector("h2").textContent =
      "30-Day Trends — No data in the last 30 days";
    return;
  }

  // Group by date (daily averages)
  const dailyMap = {};
  recentRows.forEach(r => {
    const date = r.timestamp_utc?.slice(0, 10); // YYYY-MM-DD
    if (!date) return;
    if (!dailyMap[date]) {
      dailyMap[date] = {
        coolant: [], battery: [], boost: [], rpm: [],
        stft: [], ltft: [], count: 0,
      };
    }
    const d = dailyMap[date];
    if (r.coolant_temp_c != null) d.coolant.push(r.coolant_temp_c);
    if (r.battery_voltage_v != null) d.battery.push(r.battery_voltage_v);
    if (r.boost_actual_kpa != null) d.boost.push(r.boost_actual_kpa);
    if (r.rpm != null) d.rpm.push(r.rpm);
    if (r.stft_pct != null) d.stft.push(r.stft_pct);
    if (r.ltft_pct != null) d.ltft.push(r.ltft_pct);
    d.count++;
  });

  const dates = Object.keys(dailyMap).sort();

  const avg = (arr) => arr.length > 0 ? arr.reduce((a, b) => a + b, 0) / arr.length : null;

  destroyCharts("chart-trend-coolant", "chart-trend-battery");

  // Trend 1: Coolant & Boost (daily avg)
  charts["chart-trend-coolant"] = createLineChart("chart-trend-coolant",
    "Daily Averages — Coolant, Boost, RPM", dates, [
    {
      label: "Coolant (°C)",
      data: dates.map(d => avg(dailyMap[d].coolant)),
      color: "#ef4444", tension: 0.4,
    },
    {
      label: "Boost (kPa)",
      data: dates.map(d => avg(dailyMap[d].boost)),
      color: "#3b82f6", tension: 0.4,
    },
    {
      label: "RPM ÷ 10",
      data: dates.map(d => { const a = avg(dailyMap[d].rpm); return a ? a / 10 : null; }),
      color: "#f59e0b", tension: 0.4,
    },
  ]);

  // Trend 2: Battery voltage & Fuel trims
  charts["chart-trend-battery"] = createLineChart("chart-trend-battery",
    "Daily Averages — Battery, STFT, LTFT", dates, [
    {
      label: "Battery (V)",
      data: dates.map(d => avg(dailyMap[d].battery)),
      color: "#4fd1c5", tension: 0.4,
    },
    {
      label: "STFT (%)",
      data: dates.map(d => avg(dailyMap[d].stft)),
      color: "#f59e0b", tension: 0.4,
    },
    {
      label: "LTFT (%)",
      data: dates.map(d => avg(dailyMap[d].ltft)),
      color: "#8b5cf6", tension: 0.4,
    },
  ]);
}

function renderTripCharts(trip) {
  const rows = trip.rows;
  const seq = rows.map(r => r.trip_sequence);
  const labels = seq;

  destroyCharts(
    "chart-rpm", "chart-boost-speed", "chart-coolant-iat",
    "chart-fuel-trims", "chart-throttle-load"
  );

  // Chart 1: RPM over time
  charts["chart-rpm"] = createLineChart("chart-rpm", "RPM", labels, [
    { label: "RPM", data: rows.map(r => r.rpm), color: "#ef4444", tension: 0.3 },
  ]);

  // Chart 2: Boost & Speed (dual-axis)
  charts["chart-boost-speed"] = createLineChart("chart-boost-speed", "Boost & Speed", labels, [
    { label: "Boost (kPa)", data: rows.map(r => r.boost_actual_kpa), color: "#3b82f6", tension: 0.3 },
    { label: "Speed (km/h)", data: rows.map(r => r.vehicle_speed_kph), color: "#4fd1c5", tension: 0.3 },
  ]);

  // Chart 3: Coolant & IAT
  charts["chart-coolant-iat"] = createLineChart("chart-coolant-iat", "Temperatures", labels, [
    { label: "Coolant (°C)", data: rows.map(r => r.coolant_temp_c), color: "#ef4444", tension: 0.3 },
    { label: "Intake Air (°C)", data: rows.map(r => r.intake_air_temp_c), color: "#f59e0b", tension: 0.3 },
    { label: "Ambient (°C)", data: rows.map(r => r.ambient_air_temp_c), color: "#94a3b8", tension: 0.3 },
  ]);

  // Chart 4: Fuel Trims
  charts["chart-fuel-trims"] = createLineChart("chart-fuel-trims", "Fuel Trims", labels, [
    { label: "STFT (%)", data: rows.map(r => r.stft_pct), color: "#f59e0b", tension: 0.3 },
    { label: "LTFT (%)", data: rows.map(r => r.ltft_pct), color: "#8b5cf6", tension: 0.3 },
    { label: "Sum (%)", data: rows.map(r => r.fuel_trim_sum), color: "#4fd1c5", tension: 0.3 },
  ]);

  // Chart 5: Throttle & Load
  charts["chart-throttle-load"] = createLineChart("chart-throttle-load", "Throttle & Load", labels, [
    { label: "Throttle (%)", data: rows.map(r => r.throttle_pos_pct), color: "#3b82f6", tension: 0.3, fill: true },
    { label: "Engine Load (%)", data: rows.map(r => r.engine_load_pct), color: "#f59e0b", tension: 0.3, fill: true },
  ]);
}

// --- LINE CHART HELPER ------------------------------------------------------

function createLineChart(canvasId, title, labels, series) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return null;

  const ctx = canvas.getContext("2d");
  const datasets = series.map(s => ({
    label: s.label,
    data: s.data,
    borderColor: s.color,
    backgroundColor: s.fill ? (s.color + "20") : "transparent",
    borderWidth: 1.5,
    pointRadius: 0,
    tension: s.tension || 0.3,
    spanGaps: true,
  }));

  const chart = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 0 },  // instant render for large datasets
      interaction: {
        mode: "index",
        intersect: false,
      },
      plugins: {
        legend: {
          position: "top",
          labels: {
            color: "#94a3b8",
            font: { size: 11 },
            boxWidth: 12,
            padding: 12,
            usePointStyle: true,
          },
        },
        title: {
          display: true,
          text: title,
          color: "#e2e8f0",
          font: { size: 13, weight: "600" },
          padding: { bottom: 12 },
        },
        tooltip: {
          backgroundColor: "#1e293b",
          titleColor: "#e2e8f0",
          bodyColor: "#cbd5e1",
          borderColor: "#334155",
          borderWidth: 1,
        },
      },
      scales: {
        x: {
          ticks: {
            color: "#64748b",
            font: { size: 10 },
            maxRotation: 0,
            autoSkip: true,
            maxTicksLimit: 15,
          },
          grid: { color: "#1e293b" },
        },
        y: {
          ticks: {
            color: "#64748b",
            font: { size: 10 },
          },
          grid: { color: "#1e293b" },
        },
      },
    },
  });

  return chart;
}

// --- UTILITY ----------------------------------------------------------------

function setStatus(text, type) {
  $statusText.textContent = text;
  $statusMeta.textContent = "";
  const bar = document.getElementById("status-bar");
  bar.className = "status-bar status-" + (type || "info");
}

function escHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
