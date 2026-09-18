"""
replay.py — Demo / replay CLI for the expo.

If the drone can't fly on demo day, use this to push recorded survey JSON
into the live server exactly as M3 would, over the real HTTP API
(not a database shortcut) so the full pipeline is demonstrated end-to-end.

Usage:
    python replay.py                       # replays every sample in sample_data/
    python replay.py sample_survey_1.json  # replay one specific file
"""
import sys
import os
import json
import time
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLE_DIR = os.path.join(BASE_DIR, "sample_data")
SERVER_URL = os.environ.get("M4_SERVER_URL", "http://127.0.0.1:5000")


def replay_file(filename):
    path = os.path.join(SAMPLE_DIR, filename)
    if not os.path.isfile(path):
        print(f"  ✗ {filename}: file not found")
        return False

    with open(path, "r") as f:
        payload = json.load(f)

    print(f"  → Sending {filename} ({len(payload.get('segments', []))} segments) ...")
    resp = requests.post(f"{SERVER_URL}/api/ingest", json=payload, timeout=10)

    if resp.status_code == 201:
        result = resp.json()["result"]
        print(f"  ✓ Stored survey '{result['survey_uid']}' — "
              f"{result['segments_stored']} segments, "
              f"{result['defects_stored']} defects, avg PDI {result['avg_pdi']}")
        return True
    else:
        print(f"  ✗ Server rejected {filename}: {resp.status_code} {resp.text}")
        return False


def main():
    print(f"M4 Replay/Demo Tool — target server: {SERVER_URL}")

    try:
        health = requests.get(f"{SERVER_URL}/api/health", timeout=5)
        if health.status_code != 200:
            raise Exception()
    except Exception:
        print("✗ Could not reach the server. Is app.py running? (python app.py)")
        sys.exit(1)

    print("✓ Server is up.\n")

    if len(sys.argv) > 1:
        files = [sys.argv[1]]
    else:
        files = sorted(f for f in os.listdir(SAMPLE_DIR) if f.endswith(".json"))

    for f in files:
        replay_file(f)
        time.sleep(0.3)

    print("\nDone. Refresh the dashboard and select a survey from the dropdown.")


if __name__ == "__main__":
    main()
