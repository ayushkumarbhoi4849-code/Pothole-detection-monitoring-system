"""
validators.py
Validates incoming JSON from M3 against the agreed contract (see M3_JSON_FORMAT.md).
Collects ALL problems found rather than failing on the first one, so M3 gets a full
list of what to fix in one round trip.
"""


def validate_survey_payload(data):
    errors = []

    if not isinstance(data, dict):
        return ["Payload must be a JSON object."]

    if not data.get("survey_id"):
        errors.append("Missing required field: survey_id")

    segments = data.get("segments")
    if segments is None:
        errors.append("Missing required field: segments")
        return errors  # nothing more we can check
    if not isinstance(segments, list) or len(segments) == 0:
        errors.append("segments must be a non-empty array")
        return errors

    for i, seg in enumerate(segments):
        prefix = f"segments[{i}]"
        if not isinstance(seg, dict):
            errors.append(f"{prefix} must be an object")
            continue

        if not seg.get("segment_id"):
            errors.append(f"{prefix}.segment_id is required")

        for field in ("start_lat", "start_lon", "end_lat", "end_lon"):
            if seg.get(field) is None:
                errors.append(f"{prefix}.{field} is required")
            elif not isinstance(seg.get(field), (int, float)):
                errors.append(f"{prefix}.{field} must be numeric")

        pdi = seg.get("pdi")
        if pdi is None:
            errors.append(f"{prefix}.pdi is required")
        elif not isinstance(pdi, (int, float)) or not (0 <= pdi <= 100):
            errors.append(f"{prefix}.pdi must be a number between 0 and 100")

        defects = seg.get("defects", [])
        if defects is None:
            defects = []
        if not isinstance(defects, list):
            errors.append(f"{prefix}.defects must be an array")
            defects = []

        for j, d in enumerate(defects):
            dprefix = f"{prefix}.defects[{j}]"
            if not isinstance(d, dict):
                errors.append(f"{dprefix} must be an object")
                continue
            if not d.get("type"):
                errors.append(f"{dprefix}.type is required")
            for field in ("lat", "lon"):
                if d.get(field) is None:
                    errors.append(f"{dprefix}.{field} is required")
                elif not isinstance(d.get(field), (int, float)):
                    errors.append(f"{dprefix}.{field} must be numeric")
            conf = d.get("confidence")
            if conf is not None and not (0 <= conf <= 1):
                errors.append(f"{dprefix}.confidence must be between 0 and 1")

    return errors
