"""
test_pipeline.py

Proves the full chain works: JSON -> Flask -> SQLite -> API -> (map-ready data).
Uses Flask's own test client, so it does NOT require a server to be running
and it uses a throwaway database so it never touches your real data.

Run:
    python test_pipeline.py
"""
import os
import sys
import json
import tempfile

# Redirect the DB to a temp file BEFORE importing app/db_utils
TMP_DB = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False).name

import db_utils
db_utils.DB_PATH = TMP_DB  # patch before app.py's init_db() runs

import app as flask_app_module

PASS = "✓"
FAIL = "✗"
failures = []


def check(label, condition):
    if condition:
        print(f"  {PASS} {label}")
    else:
        print(f"  {FAIL} {label}")
        failures.append(label)


def main():
    print(f"Using temporary test database: {TMP_DB}\n")
    db_utils.init_db()

    client = flask_app_module.app.test_client()

    # 1. Health check -------------------------------------------------------
    print("1. Flask server health")
    r = client.get("/api/health")
    check("GET /api/health returns 200", r.status_code == 200)
    check("health response reports status ok", r.get_json().get("status") == "ok")

    # 2. Validation rejects bad input ---------------------------------------
    print("\n2. Ingest validation")
    bad_payload = {"survey_name": "missing required fields"}
    r = client.post("/api/ingest", json=bad_payload)
    check("bad payload rejected with 400", r.status_code == 400)
    check("error details list survey_id and segments issues",
          any("survey_id" in e for e in r.get_json().get("details", [])))

    # 3. Ingest valid sample data --------------------------------------------
    print("\n3. Ingest -> SQLite (sample_data/sample_survey_1.json)")
    sample_path = os.path.join(os.path.dirname(__file__), "sample_data", "sample_survey_1.json")
    with open(sample_path) as f:
        sample = json.load(f)

    r = client.post("/api/ingest", json=sample)
    check("valid payload accepted with 201", r.status_code == 201)
    result = r.get_json().get("result", {})
    check("segments_stored matches JSON segment count",
          result.get("segments_stored") == len(sample["segments"]))
    expected_defects = sum(len(s.get("defects", [])) for s in sample["segments"])
    check("defects_stored matches JSON defect count",
          result.get("defects_stored") == expected_defects)

    survey_id = result.get("survey_id")

    # 4. Data actually landed in SQLite --------------------------------------
    print("\n4. SQLite row counts")
    conn = db_utils.get_connection()
    seg_count = conn.execute(
        "SELECT COUNT(*) c FROM segments WHERE survey_id = ?", (survey_id,)
    ).fetchone()["c"]
    def_count = conn.execute(
        "SELECT COUNT(*) c FROM defects WHERE survey_id = ?", (survey_id,)
    ).fetchone()["c"]
    conn.close()
    check("segments table has correct row count", seg_count == len(sample["segments"]))
    check("defects table has correct row count", def_count == expected_defects)

    # 5. GET APIs return the stored data -------------------------------------
    print("\n5. REST API read-back (this is what the map/dashboard consumes)")
    r = client.get("/api/surveys")
    check("GET /api/surveys returns list with our survey", 
          any(s["id"] == survey_id for s in r.get_json()))

    r = client.get(f"/api/surveys/{survey_id}")
    check("GET /api/surveys/<id> returns avg_pdi", r.get_json().get("avg_pdi") is not None)
    check("condition_breakdown present for map legend",
          isinstance(r.get_json().get("condition_breakdown"), list))

    r = client.get(f"/api/surveys/{survey_id}/segments")
    segs = r.get_json()
    check("GET .../segments returns correct count", len(segs) == len(sample["segments"]))
    check("every segment has lat/lon endpoints for Leaflet polylines",
          all("start_lat" in s and "end_lat" in s for s in segs))
    check("every segment has a condition band (Good/Moderate/Severe)",
          all(s["condition"] in ("Good", "Moderate", "Severe") for s in segs))

    # spot-check PDI -> condition mapping matches project spec
    band_ok = True
    for s in segs:
        pdi = s["pdi"]
        expected = "Good" if pdi >= 80 else ("Moderate" if pdi >= 50 else "Severe")
        if s["condition"] != expected:
            band_ok = False
    check("PDI-to-condition bands match spec (80-100/50-79/0-49)", band_ok)

    r = client.get(f"/api/surveys/{survey_id}/defects")
    defs = r.get_json()
    check("GET .../defects returns correct count", len(defs) == expected_defects)
    check("every defect has lat/lon for Leaflet markers",
          all("lat" in d and "lon" in d for d in defs))

    # 6. Filtering ------------------------------------------------------------
    print("\n6. Defect filtering")
    r = client.get(f"/api/surveys/{survey_id}/defects?type=pothole")
    potholes = r.get_json()
    check("filter by type=pothole returns only potholes",
          all(d["type"] == "pothole" for d in potholes) and len(potholes) > 0)

    r = client.get(f"/api/surveys/{survey_id}/defects?thermal_only=true")
    thermal = r.get_json()
    check("filter thermal_only=true returns only thermal-flagged defects",
          all(d["thermal_anomaly"] == 1 for d in thermal) and len(thermal) > 0)

    # 7. Re-ingest same survey_id upserts, doesn't duplicate -----------------
    print("\n7. Re-ingest same survey_id (upsert, no duplicates)")
    r = client.post("/api/ingest", json=sample)
    check("re-ingest accepted", r.status_code == 201)
    r = client.get("/api/surveys")
    matching = [s for s in r.get_json() if s["survey_uid"] == sample["survey_id"]]
    check("only ONE survey row exists for this survey_uid after re-ingest",
          len(matching) == 1)

    # 8. Replay endpoint (expo demo path) --------------------------------------
    print("\n8. Replay endpoint (demo without live drone)")
    r = client.get("/api/samples")
    check("GET /api/samples lists sample files", "sample_survey_2.json" in r.get_json())

    r = client.post("/api/replay/sample_survey_2.json")
    check("POST /api/replay/<file> ingests second sample", r.status_code == 201)

    r = client.post("/api/replay/does_not_exist.json")
    check("replay of missing file returns 404", r.status_code == 404)

    # ---- Summary -------------------------------------------------------------
    print("\n" + "=" * 60)
    if not failures:
        print(f"ALL CHECKS PASSED — pipeline JSON -> Flask -> SQLite -> API -> Map is verified.")
    else:
        print(f"{len(failures)} CHECK(S) FAILED:")
        for f in failures:
            print(f"   - {f}")
    print("=" * 60)

    os.remove(TMP_DB)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
