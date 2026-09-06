from __future__ import annotations
import json
from pathlib import Path
from .models import Code, MediaRecord
from .metadata import json_date

def _candidates(record: MediaRecord, files: list[Path], roots: dict[str, Path]) -> list[Path]:
    source = Path(record.source_path); same_dir = [p for p in files if p.parent == source.parent]
    names = {record.original_filename + ".json", record.original_filename.rsplit(".", 1)[0] + ".json"}
    exact = [p for p in same_dir if p.name in names]
    if exact: return exact
    normalized = record.original_filename.lower().replace(" ", "")
    return [p for p in files if p.stem.lower().replace(" ", "").startswith(normalized)]
def match(records: list[MediaRecord], files: list[Path]) -> tuple[set[Path], list[str]]:
    used: set[Path] = set(); warnings: list[str] = []
    for record in records:
        candidates = _candidates(record, files, {})
        if len(candidates) != 1:
            record.json_status = "AMBIGUOUS_SIDECAR" if candidates else "MEDIA_WITHOUT_JSON"
            record.warnings.append(str(Code.AMBIGUOUS_SIDECAR if candidates else Code.MEDIA_WITHOUT_JSON)); continue
        candidate = candidates[0]; used.add(candidate); record.json_path = str(candidate); record.json_status = "MATCHED"
        try:
            data = json.loads(candidate.read_text(encoding="utf-8")); record.json_date = json_date(data)
            record.album_names = sorted({str(x) for x in data.get("albums", []) if isinstance(x, str)})
        except (OSError, ValueError, json.JSONDecodeError): record.json_status = "INVALID_JSON"; record.warnings.append(str(Code.INVALID_JSON))
    for item in set(files) - used: warnings.append(f"{Code.JSON_ORPHAN}:{item}")
    return used, warnings
