from __future__ import annotations
from datetime import datetime, timezone
from .models import Code, MediaRecord

def _parse_dt(s: str) -> datetime | None:
    try:
        cleaned = s.strip()
        if cleaned.endswith("Z"):
            return datetime.fromisoformat(cleaned[:-1] + "+00:00")
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None

def _dates_match(json_str: str, exif_str: str) -> bool:
    # Quick exact date prefix match
    if json_str[:10] == exif_str[:10]:
        return True
    
    j_dt = _parse_dt(json_str)
    e_dt = _parse_dt(exif_str)
    if not j_dt or not e_dt:
        return False
    
    # 1. Both are timezone-aware
    if j_dt.tzinfo is not None and e_dt.tzinfo is not None:
        return abs((j_dt - e_dt).total_seconds()) <= 60
    
    # 2. JSON is UTC aware, EXIF is naive local time
    if j_dt.tzinfo is not None and e_dt.tzinfo is None:
        diff_sec = (e_dt - j_dt.astimezone(timezone.utc).replace(tzinfo=None)).total_seconds()
        diff_hours = diff_sec / 3600.0
        # Check if diff is valid timezone offset (-12 to +14 hours, exact minutes/seconds)
        # Note: some timezones have half-hour offsets (+03:30, +04:30, +05:30, +09:30) or 45-min (+05:45)
        # diff_sec % 900 == 0 checks 15-minute intervals
        if -12 <= diff_hours <= 14 and abs(diff_sec % 900) < 1e-4:
            return True
        return False

    # 3. Both naive
    return abs((j_dt - e_dt).total_seconds()) <= 60

def resolve(record: MediaRecord) -> None:
    json_value, exif = record.json_date, record.exif_date
    if json_value and exif and not _dates_match(json_value, exif):
        record.warnings.append(str(Code.DATE_CONFLICT))
        record.date_confidence = "UNKNOWN"
        record.date_source = "CONFLICT"
        record.resolved_date = None
        return
    
    # When both are present and match, prefer EXIF local time if available, or JSON
    value = exif or json_value or record.filename_date or record.folder_date
    source = "EXIF" if exif else "GOOGLE_JSON" if json_value else "FILENAME" if record.filename_date else "FOLDER" if record.folder_date else "UNKNOWN"
    record.resolved_date = value
    record.date_source = source
    record.date_confidence = "HIGH" if (json_value and exif) else "MEDIUM" if (json_value or exif) else "LOW" if value else "UNKNOWN"
    record.date_precision = "DATETIME" if value and "T" in value else "DATE" if value and len(value) >= 10 else "YEAR_MONTH" if value and len(value) == 7 else "YEAR" if value and len(value) == 4 else "UNKNOWN"
    if not value:
        record.warnings.append(str(Code.NO_DATE))

