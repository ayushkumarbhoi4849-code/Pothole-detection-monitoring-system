"""
app.py — M4 Backend & Web Dashboard

Pipeline:  M3 processed road data -> Flask -> SQLite -> REST API -> Leaflet dashboard

Run:
    pip install -r requirements.txt
    python app.py
Then open http://127.0.0.1:5000
"""
import os
import glob
import json
from flask import Flask, request, jsonify, render_template, send_from_directory

from db_utils import get_connection, init_db, rows_to_list, row_to_dict
from validators import validate_survey_payload
from ingest import store_survey

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLE_DIR = os.path.join(BASE_DIR, "sample_data")

app = Flask(__name__)

# ---------------------------------------------------------------------------
# STEP 3: health check
# ---------------------------------------------------------------------------
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "M4 Backend",
        "message": "Flask server is running."
    }), 200


# ---------------------------------------------------------------------------
# Dashboard (Leaflet frontend)
# ---------------------------------------------------------------------------
@app.route("/")
def dashboard():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# STEP 6/7: ingest M3 data
# ---------------------------------------------------------------------------
@app.route("/api/ingest", methods=["POST"])
def ingest():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Request body must be valid JSON."}), 400

    errors = validate_survey_payload(data)
    if errors:
        return jsonify({"error": "Validation failed", "details": errors}), 400

    try:
        result = store_survey(data)
    except Exception as e:
        return jsonify({"error": "Failed to store survey", "details": str(e)}), 500

    return jsonify({"message": "Survey stored successfully", "result": result}), 201


# ---------------------------------------------------------------------------
# STEP 8: GET APIs for the dashboard
# ---------------------------------------------------------------------------
@app.route("/api/surveys", methods=["GET"])
def list_surveys():
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, survey_uid, survey_name, survey_date, drone_id,
                  gsd_cm_per_px, area_covered_sqm, avg_pdi, total_defects, created_at
           FROM surveys ORDER BY created_at DESC"""
    ).fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))


@app.route("/api/surveys/<int:survey_id>", methods=["GET"])
def get_survey(survey_id):
    conn = get_connection()
    survey = conn.execute(
        "SELECT * FROM surveys WHERE id = ?", (survey_id,)
    ).fetchone()
    if survey is None:
        conn.close()
        return jsonify({"error": "Survey not found"}), 404

    condition_counts = conn.execute(
        """SELECT condition, COUNT(*) as count FROM segments
           WHERE survey_id = ? GROUP BY condition""",
        (survey_id,),
    ).fetchall()

    defect_type_counts = conn.execute(
        """SELECT type, COUNT(*) as count FROM defects
           WHERE survey_id = ? GROUP BY type""",
        (survey_id,),
    ).fetchall()

    thermal_count = conn.execute(
        """SELECT COUNT(*) as count FROM defects
           WHERE survey_id = ? AND thermal_anomaly = 1""",
        (survey_id,),
    ).fetchone()["count"]

    conn.close()

    survey_dict = row_to_dict(survey)
    survey_dict.pop("raw_json", None)  # keep API responses light
    survey_dict["condition_breakdown"] = rows_to_list(condition_counts)
    survey_dict["defect_type_breakdown"] = rows_to_list(defect_type_counts)
    survey_dict["thermal_anomaly_count"] = thermal_count

    return jsonify(survey_dict)


@app.route("/api/surveys/<int:survey_id>/segments", methods=["GET"])
def get_segments(survey_id):
    conn = get_connection()
    survey = conn.execute("SELECT id FROM surveys WHERE id = ?", (survey_id,)).fetchone()
    if survey is None:
        conn.close()
        return jsonify({"error": "Survey not found"}), 404

    rows = conn.execute(
        "SELECT * FROM segments WHERE survey_id = ? ORDER BY id", (survey_id,)
    ).fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))


@app.route("/api/surveys/<int:survey_id>/defects", methods=["GET"])
def get_defects(survey_id):
    """Supports optional filters: ?type=pothole&severity=high&segment_id=3&thermal_only=true"""
    conn = get_connection()
    survey = conn.execute("SELECT id FROM surveys WHERE id = ?", (survey_id,)).fetchone()
    if survey is None:
        conn.close()
        return jsonify({"error": "Survey not found"}), 404

    query = "SELECT * FROM defects WHERE survey_id = ?"
    params = [survey_id]

    defect_type = request.args.get("type")
    if defect_type:
        query += " AND type = ?"
        params.append(defect_type)

    severity = request.args.get("severity")
    if severity:
        query += " AND severity = ?"
        params.append(severity)

    segment_id = request.args.get("segment_id")
    if segment_id:
        query += " AND segment_id = ?"
        params.append(segment_id)

    if request.args.get("thermal_only", "").lower() == "true":
        query += " AND thermal_anomaly = 1"

    query += " ORDER BY id"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))


@app.route("/api/segments/<int:segment_id>", methods=["GET"])
def get_segment_detail(segment_id):
    conn = get_connection()
    seg = conn.execute("SELECT * FROM segments WHERE id = ?", (segment_id,)).fetchone()
    if seg is None:
        conn.close()
        return jsonify({"error": "Segment not found"}), 404
    defects = conn.execute(
        "SELECT * FROM defects WHERE segment_id = ? ORDER BY id", (segment_id,)
    ).fetchall()
    conn.close()
    seg_dict = row_to_dict(seg)
    seg_dict["defects"] = rows_to_list(defects)
    return jsonify(seg_dict)


@app.route("/api/defects/<int:defect_id>", methods=["GET"])
def get_defect_detail(defect_id):
    conn = get_connection()
    d = conn.execute("SELECT * FROM defects WHERE id = ?", (defect_id,)).fetchone()
    conn.close()
    if d is None:
        return jsonify({"error": "Defect not found"}), 404
    return jsonify(row_to_dict(d))


# ---------------------------------------------------------------------------
# STEP 9: Replay / demo system (no drone needed)
# ---------------------------------------------------------------------------
@app.route("/api/samples", methods=["GET"])
def list_samples():
    files = sorted(glob.glob(os.path.join(SAMPLE_DIR, "*.json")))
    return jsonify([os.path.basename(f) for f in files])


@app.route("/api/replay/<filename>", methods=["POST"])
def replay_sample(filename):
    """Loads a stored sample survey and pushes it through the exact same
    validate -> store pipeline that a live M3 payload would use."""
    safe_name = os.path.basename(filename)  # prevent path traversal
    path = os.path.join(SAMPLE_DIR, safe_name)
    if not os.path.isfile(path):
        return jsonify({"error": f"Sample file '{safe_name}' not found"}), 404

    with open(path, "r") as f:
        data = json.load(f)

    errors = validate_survey_payload(data)
    if errors:
        return jsonify({"error": "Sample failed validation", "details": errors}), 500

    result = store_survey(data)
    return jsonify({"message": f"Replayed {safe_name}", "result": result}), 201


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
