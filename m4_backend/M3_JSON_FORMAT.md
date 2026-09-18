# M3 → M4 JSON Contract

This is the format M3's processed output must follow when POSTed to `/api/ingest`.
Agreed as STEP 5 before any ingestion code was written.

```json
{
  "survey_id": "SURVEY_2026_09_19_001",
  "survey_name": "Highway 12 North Section",
  "date": "2026-09-19T10:30:00Z",
  "drone_id": "DJI_M300_01",
  "gsd_cm_per_px": 2.5,
  "area_covered_sqm": 15000,
  "segments": [
    {
      "segment_id": "SEG_001",
      "start_lat": 14.4700,
      "start_lon": 78.8200,
      "end_lat": 14.4715,
      "end_lon": 78.8210,
      "length_m": 120.5,
      "pdi": 72.5,
      "thermal_score": 0.35,
      "defects": [
        {
          "defect_id": "DEF_001",
          "type": "pothole",
          "lat": 14.4705,
          "lon": 78.8205,
          "severity": "moderate",
          "area_sqcm": 450.2,
          "depth_cm": 3.2,
          "thermal_anomaly": true,
          "confidence": 0.91
        }
      ]
    }
  ]
}
```

## Field rules

| Field | Required | Notes |
|---|---|---|
| `survey_id` | yes | Unique string. Re-posting the same `survey_id` **replaces** that survey (upsert), so a corrected re-run from M3 doesn't create a duplicate. |
| `survey_name` | no | Free text label shown in dashboard dropdown. |
| `date` | no | ISO8601 string. |
| `drone_id` | no | Free text. |
| `gsd_cm_per_px` | no | Ground Sampling Distance, used by M3 to size defects in real-world units. |
| `area_covered_sqm` | no | Total area covered by the survey. |
| `segments` | yes | Array, at least 1 entry. |
| `segments[].segment_id` | yes | Unique within the survey. |
| `segments[].start_lat/lon`, `end_lat/lon` | yes | Segment endpoints (WGS84 decimal degrees), used to draw the road line on the map. |
| `segments[].pdi` | yes | 0–100. Condition band is derived server-side: 🟢 80–100 Good, 🟡 50–79 Moderate, 🔴 0–49 Severe. |
| `segments[].thermal_score` | no | 0–1 normalized thermal anomaly score for the segment. |
| `segments[].defects` | no | Array, may be empty. |
| `defects[].defect_id` | no | If omitted, one is generated. |
| `defects[].type` | yes | e.g. `pothole`, `crack`, `raveling`, `patch`. |
| `defects[].lat/lon` | yes | Point location of the defect. |
| `defects[].severity` | no | `low` / `moderate` / `high`. |
| `defects[].area_sqcm`, `depth_cm` | no | Physical measurements (M3 derives these using GSD). |
| `defects[].thermal_anomaly` | no | Boolean — flagged by thermal camera pass. |
| `defects[].confidence` | no | Detection model confidence, 0–1. |

## Validation performed by `/api/ingest`
- Rejects payloads missing `survey_id` or `segments`.
- Rejects any segment missing `segment_id`, `pdi`, or lat/lon endpoints.
- Rejects PDI values outside 0–100.
- Rejects any defect missing `type` or lat/lon.
- Returns `400` with a JSON body listing every problem found (not just the first one).
