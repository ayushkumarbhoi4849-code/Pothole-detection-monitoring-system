"""
db_utils.py
Handles SQLite connection, schema initialization, and PDI -> condition mapping.
"""
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "db", "m4.sqlite3")
SCHEMA_PATH = os.path.join(BASE_DIR, "db", "schema.sql")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    """Create tables if they don't exist yet. Safe to call on every app start."""
    conn = get_connection()
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


def pdi_to_condition(pdi: float) -> str:
    """Project-proposal PDI bands: 80-100 Good, 50-79 Moderate, 0-49 Severe."""
    if pdi is None:
        return "Unknown"
    if pdi >= 80:
        return "Good"
    elif pdi >= 50:
        return "Moderate"
    else:
        return "Severe"


def row_to_dict(row):
    return dict(row) if row is not None else None


def rows_to_list(rows):
    return [dict(r) for r in rows]
