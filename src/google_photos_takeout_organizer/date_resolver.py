from __future__ import annotations
from .models import Code, MediaRecord

def resolve(record: MediaRecord) -> None:
    json_value, exif = record.json_date, record.exif_date
    if json_value and exif and json_value[:10] != exif[:10]:
        record.warnings.append(str(Code.DATE_CONFLICT)); record.date_confidence = "UNKNOWN"; record.date_source = "CONFLICT"; record.resolved_date = None; return
    value = json_value or exif or record.filename_date or record.folder_date
    source = "GOOGLE_JSON" if json_value else "EXIF" if exif else "FILENAME" if record.filename_date else "FOLDER" if record.folder_date else "UNKNOWN"
    record.resolved_date = value; record.date_source = source
    record.date_confidence = "HIGH" if json_value and exif else "MEDIUM" if json_value or exif else "LOW" if value else "UNKNOWN"
    record.date_precision = "DATETIME" if value and "T" in value else "DATE" if value and len(value) >= 10 else "YEAR_MONTH" if value and len(value) == 7 else "YEAR" if value and len(value) == 4 else "UNKNOWN"
    if not value: record.warnings.append(str(Code.NO_DATE))
