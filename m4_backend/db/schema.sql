-- M4 Backend Database Schema
-- Stores: Surveys, Road Segments, Defects, GPS coordinates, PDI, GSD/area, Thermal scores

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS surveys (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    survey_uid          TEXT UNIQUE NOT NULL,   -- e.g. SURVEY_2026_09_19_001 (from M3)
    survey_name         TEXT,
    survey_date         TEXT,                   -- ISO8601 timestamp
    drone_id            TEXT,
    gsd_cm_per_px        REAL,                   -- ground sampling distance
    area_covered_sqm    REAL,
    avg_pdi             REAL,                   -- computed on ingest
    total_defects       INTEGER DEFAULT 0,      -- computed on ingest
    raw_json            TEXT,                   -- original payload, kept for audit/replay
    created_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS segments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    survey_id           INTEGER NOT NULL REFERENCES surveys(id) ON DELETE CASCADE,
    segment_uid         TEXT NOT NULL,          -- e.g. SEG_001 (from M3)
    start_lat           REAL NOT NULL,
    start_lon           REAL NOT NULL,
    end_lat             REAL NOT NULL,
    end_lon             REAL NOT NULL,
    length_m            REAL,
    pdi                 REAL NOT NULL,          -- Pavement Distress Index 0-100
    condition           TEXT NOT NULL,          -- Good / Moderate / Severe (derived from PDI)
    thermal_score       REAL,                   -- normalized thermal anomaly score 0-1
    UNIQUE(survey_id, segment_uid)
);

CREATE TABLE IF NOT EXISTS defects (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    survey_id           INTEGER NOT NULL REFERENCES surveys(id) ON DELETE CASCADE,
    segment_id          INTEGER REFERENCES segments(id) ON DELETE CASCADE,
    defect_uid          TEXT,                   -- e.g. DEF_001 (from M3)
    type                TEXT NOT NULL,          -- pothole / crack / raveling / patch / other
    lat                 REAL NOT NULL,
    lon                 REAL NOT NULL,
    severity            TEXT,                   -- low / moderate / high
    area_sqcm           REAL,                   -- derived using GSD
    depth_cm            REAL,
    thermal_anomaly     INTEGER DEFAULT 0,      -- 0/1 boolean
    confidence          REAL                    -- model confidence 0-1
);

CREATE INDEX IF NOT EXISTS idx_segments_survey ON segments(survey_id);
CREATE INDEX IF NOT EXISTS idx_defects_survey  ON defects(survey_id);
CREATE INDEX IF NOT EXISTS idx_defects_segment ON defects(segment_id);
