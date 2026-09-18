"""
ingest.py
Takes an already-validated M3 payload and writes it into SQLite.
Re-posting the same survey_id replaces the old survey (upsert), so a corrected
re-run from M3 (or a repeated demo replay) never creates duplicates.
"""
import json
from db_utils import get_connection, pdi_to_condition


def store_survey(data: dict) -> dict:
    conn = get_connection()
    cur = conn.cursor()

    survey_uid = data["survey_id"]

    # Upsert: if this survey_id already exists, wipe it and its children first
    # (ON DELETE CASCADE on segments/defects handles the children).
    existing = cur.execute(
        "SELECT id FROM surveys WHERE survey_uid = ?", (survey_uid,)
    ).fetchone()
    if existing:
        cur.execute("DELETE FROM surveys WHERE id = ?", (existing["id"],))

    cur.execute(
        """INSERT INTO surveys
           (survey_uid, survey_name, survey_date, drone_id, gsd_cm_per_px,
            area_covered_sqm, avg_pdi, total_defects, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            survey_uid,
            data.get("survey_name"),
            data.get("date"),
            data.get("drone_id"),
            data.get("gsd_cm_per_px"),
            data.get("area_covered_sqm"),
            0,  # placeholder, updated below
            0,
            json.dumps(data),
        ),
    )
    survey_id = cur.lastrowid

    pdi_values = []
    total_defects = 0

    for seg in data["segments"]:
        pdi = float(seg["pdi"])
        pdi_values.append(pdi)
        condition = pdi_to_condition(pdi)

        cur.execute(
            """INSERT INTO segments
               (survey_id, segment_uid, start_lat, start_lon, end_lat, end_lon,
                length_m, pdi, condition, thermal_score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                survey_id,
                seg["segment_id"],
                seg["start_lat"],
                seg["start_lon"],
                seg["end_lat"],
                seg["end_lon"],
                seg.get("length_m"),
                pdi,
                condition,
                seg.get("thermal_score"),
            ),
        )
        segment_id = cur.lastrowid

        for d in seg.get("defects", []) or []:
            total_defects += 1
            cur.execute(
                """INSERT INTO defects
                   (survey_id, segment_id, defect_uid, type, lat, lon, severity,
                    area_sqcm, depth_cm, thermal_anomaly, confidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    survey_id,
                    segment_id,
                    d.get("defect_id"),
                    d["type"],
                    d["lat"],
                    d["lon"],
                    d.get("severity"),
                    d.get("area_sqcm"),
                    d.get("depth_cm"),
                    1 if d.get("thermal_anomaly") else 0,
                    d.get("confidence"),
                ),
            )

    avg_pdi = round(sum(pdi_values) / len(pdi_values), 2) if pdi_values else None
    cur.execute(
        "UPDATE surveys SET avg_pdi = ?, total_defects = ? WHERE id = ?",
        (avg_pdi, total_defects, survey_id),
    )

    conn.commit()
    conn.close()

    return {
        "survey_id": survey_id,
        "survey_uid": survey_uid,
        "segments_stored": len(data["segments"]),
        "defects_stored": total_defects,
        "avg_pdi": avg_pdi,
    }
