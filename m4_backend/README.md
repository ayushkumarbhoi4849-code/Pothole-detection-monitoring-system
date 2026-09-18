# M4 — Backend & Web Dashboard

Pipeline: **M3 processed road data → Flask → SQLite → REST API → Leaflet dashboard**

This folder is a complete, working implementation of everything M4 owns:
Flask backend, SQLite database, REST API, Leaflet map, dashboard, filters,
interactions, and an offline replay/demo system for the expo.

## Folder structure

```
m4_backend/
├── app.py                 # Flask app + all REST routes + /api/health
├── db_utils.py             # SQLite connection, schema init, PDI->condition mapping
├── ingest.py                # Validated JSON -> SQLite writer (upsert by survey_id)
├── validators.py            # Validates M3's JSON against the agreed contract
├── replay.py                # CLI demo tool: replays sample_data/*.json over real HTTP
├── test_pipeline.py         # Automated test: JSON -> Flask -> SQLite -> API -> Map
├── requirements.txt
├── M3_JSON_FORMAT.md        # The JSON contract agreed with M3 (read this first)
├── db/
│   └── schema.sql           # Table definitions (surveys, segments, defects)
├── sample_data/
│   ├── sample_survey_1.json # Recorded demo survey #1 (NH-40 Kadapa Bypass)
│   └── sample_survey_2.json # Recorded demo survey #2 (Kadapa–Pulivendla Rd)
├── templates/
│   └── index.html           # Dashboard page (Leaflet map + sidebar + detail panel)
└── static/
    ├── css/style.css
    └── js/app.js             # Talks to the REST API, drives the Leaflet map
```

## 1. Setup

```bash
cd m4_backend
python3 -m venv venv && source venv/bin/activate      # optional but recommended
pip install -r requirements.txt
```

## 2. Run the server

```bash
python app.py
```

This creates `db/m4.sqlite3` automatically on first run (STEP 4) and starts Flask
on **http://127.0.0.1:5000**. Open that URL in a browser to see the dashboard.

At this point the database is empty — the dropdown will say "No surveys yet."

## 3. Load data (two ways)

**A. Replay demo (no drone needed — for the expo):**
Click the **▶ Replay Demo** button on the dashboard, or run:
```bash
python replay.py
```
This posts the two recorded sample surveys through the *real* `/api/ingest`
pipeline (not a database shortcut), so it proves the whole chain works even
without live drone data.

**B. Real M3 output:**
Have M3 `POST` its JSON (format defined in `M3_JSON_FORMAT.md`) to:
```
POST http://<server>:5000/api/ingest
Content-Type: application/json
```
Re-posting the same `survey_id` replaces that survey — safe to re-run.

## 4. REST API reference

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Server up-check |
| POST | `/api/ingest` | Submit M3's JSON survey |
| GET | `/api/surveys` | List all surveys |
| GET | `/api/surveys/<id>` | Survey detail + condition/defect breakdowns |
| GET | `/api/surveys/<id>/segments` | All road segments for a survey |
| GET | `/api/surveys/<id>/defects` | All defects (filters: `?type=`, `?severity=`, `?segment_id=`, `?thermal_only=true`) |
| GET | `/api/segments/<id>` | One segment + its defects |
| GET | `/api/defects/<id>` | One defect's full detail |
| GET | `/api/samples` | List available replay/demo files |
| POST | `/api/replay/<filename>` | Ingest a sample file through the real pipeline |

## 5. PDI → Condition bands (per project proposal)

| Band | PDI range | Color |
|---|---|---|
| Good | 80–100 | 🟢 |
| Moderate | 50–79 | 🟡 |
| Severe | 0–49 | 🔴 |

Computed server-side in `db_utils.pdi_to_condition()` and stored on each segment.

## 6. Testing the pipeline

```bash
python test_pipeline.py
```
Runs 22 checks against a throwaway database (your real `db/m4.sqlite3` is never
touched) proving: health check → validation rejects bad input → valid JSON is
stored correctly in SQLite → REST API reads it back correctly → PDI bands match
spec → filtering works → re-ingesting the same survey upserts instead of
duplicating → the replay endpoints work. All 22 currently pass.

## 7. Dashboard features

- **Survey selector** — switch between surveys, or replay a new one live.
- **Summary cards** — average PDI, total potholes, total cracks, thermal anomalies.
- **Condition breakdown bars** — Good/Moderate/Severe segment counts.
- **Leaflet map** — road segments colored by PDI band, defect markers by type.
- **Filters** — by defect type, severity, and a thermal-anomaly-only toggle, plus a
  one-click "Reset filters" button.
- **Click interactions** — click a road segment or a defect marker to see full
  measurements (PDI, length, area, depth, confidence, thermal flag) in the
  right-hand detail panel.

### UX polish added on top of the core pipeline
- **Light/dark theme toggle** (saved to the browser, persists across visits).
- **Toast notifications** instead of browser `alert()` popups for replay success/failure
  and server-connection issues.
- **Boot loading screen** and a **map loading spinner** while data is being fetched, so
  the UI never looks frozen or broken while waiting on the API.
- **Friendly empty state** — if the database has no surveys yet, the map area shows a
  clear "No survey data yet" card with a big Replay Demo button, instead of a blank map.
- **Defect List view** — a second tab next to the map with a searchable, sortable table
  of every defect (type, severity, segment, area, depth, thermal flag, confidence).
  Clicking a row jumps the map to that defect and opens its detail panel — useful for
  reviewing on a laptop without hunting around the map, or for a jury looking for specifics.
- **Fully responsive/mobile layout** — on narrow screens the sidebar and detail panel
  become slide-over panels opened via a hamburger menu, so the dashboard is usable on a
  phone or tablet at the expo, not just a laptop.

## 8. Next steps to wire in the real drone feed

1. Confirm `M3_JSON_FORMAT.md` with M3 (already drafted here as a starting point).
2. Point M3's output step at `POST http://<your-server-ip>:5000/api/ingest`.
3. Run `test_pipeline.py` again after any schema/contract change.
4. Keep `replay.py` and `sample_data/` as your expo fallback — they are not
   test fixtures only, they are wired through the exact same ingest code path
   as production data.
