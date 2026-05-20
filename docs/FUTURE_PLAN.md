# Future Plan — Dashboard & Delta Table

Ideas deferred until real driving data is flowing through Google Sheets.

---

## 1. GitHub Pages Dashboard

A static dashboard hosted on GitHub Pages showing XC90 OBD data.

### Architecture

```
ESP32 ──POST CSV──▶ Google Sheets
                        │
                        ▼
              Share → "Anyone with the link can view"
              (no formal Publish needed)
                        │
                        ▼
              Public JSON endpoint (Google Visualization API)
              https://docs.google.com/spreadsheets/d/<ID>/gviz/tq?tqx=out:json
                        │
                        ▼
                GitHub Pages dashboard
                (static HTML, fetch() at page load)
```

**Zero pipeline.** Share the sheet, copy the URL, fetch it from the dashboard. No API keys, no cron jobs, no build steps.

### Why Google Sheets direct query

| | Sheets direct (gviz) | GitHub Actions + Parquet |
|---|---|---|
| Setup | 30 seconds (share sheet, copy URL) | ~1 day (workflow + secrets + script) |
| Freshness | ~5 min Google cache | Daily cron |
| Page load | 1-3 sec (single fetch) | <100ms (static files) |
| Moving parts | 0 | 3 (Actions, Python, git commits) |
| Cost | Free | Free |
| Cell limit | 10M (~75 driving hours × 37 cols) | Unlimited |
| Privacy | URL-guessable (not indexed) | Fully private |

Tradeoff: the sheet URL is public (not indexed by search engines, but accessible to anyone with the link). For car telemetry this is acceptable — there's no PII, and the data is only useful with context.

### Data flow in the browser

```javascript
// Single fetch at page load — no API keys, no backend
// Sheet must be shared "Anyone with the link can view" (no formal Publish needed)
const url = "https://docs.google.com/spreadsheets/d/<SHEET_ID>/gviz/tq?tqx=out:json&sheet=XC90_Logs";
const res = await fetch(url);
const text = await res.text();
const json = JSON.parse(text.match(/\((.*)\)/)[1]);  // unwrap JSONP wrapper

// Parse rows into flat objects: [{rpm: 800, coolant: 90, ...}, ...]
const headers = json.table.cols.map(c => c.label);
const rows = json.table.rows.map(r => {
  const row = {};
  r.c.forEach((c, i) => { row[headers[i]] = c?.v ?? null; });
  return row;
});
```

### Dashboard views

| View | Data Source | Chart Type |
|------|-----------|------------|
| **Latest gauges** | Last row from Sheets | Radial gauges — RPM, coolant, boost, speed |
| **Trip list** | Aggregate in JS from rows | Table — date, duration, distance, max RPM, max boost |
| **Trip detail** | Filter rows by trip_id | Line charts — RPM, boost, throttle vs trip_sequence |
| **Trends (30 days)** | Aggregate in JS | Multi-line — avg coolant, fuel trims, battery |
| **Drive phase breakdown** | Group by drive_phase | Bar chart — idle/light/moderate/hard/decel % |

All aggregation happens client-side in JavaScript at page load. At 1 row/sec, an hour of driving is ~3,600 rows — well within browser JS performance limits.

### Performance note

With 100K+ rows, the ~5 min Google cache helps, but the JSON payload may reach several MB. If page load becomes slow:
- Add a "last 30 days" filter in JS
- Or migrate to the **GitHub Actions + Parquet** approach (below) for pre-aggregated summaries

### Frontend stack

- **Charting**: Chart.js (lightweight, canvas-based) or Plotly.js (interactive, zoomable)
- **Data**: Single `fetch()` to Google Sheets publish URL
- **Styling**: Vanilla CSS with a dark automotive theme
- **No frameworks, no build step, no CI/CD** — push `index.html` + `dashboard.js` to `gh-pages` branch


*Last updated: 2026-03*
