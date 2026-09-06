from __future__ import annotations
from pathlib import PurePosixPath
from .models import MediaRecord
from .utils import sanitize_filename

def plan(records: list[MediaRecord]) -> None:
    used: set[str] = set(); duplicate_index: dict[str, int] = {}
    for record in sorted(records, key=lambda r: (r.duplicate_group_id or "", not r.is_primary, r.relative_path)):
        if record.is_primary and any(code in record.warnings for code in ("DATE_CONFLICT", "AMBIGUOUS_SIDECAR", "INVALID_JSON")):
            root, date = "Review", ""
        else:
            root = "Photos_Archive" if record.is_primary else "Duplicates"
            date = record.resolved_date or ""
        parts = date.split("-")
        if len(parts) >= 2: folder = f"{root}/{parts[0]}/{parts[1]}"
        elif len(parts) == 1 and parts[0]: folder = f"{root}/{parts[0]}/Unknown-Month"
        else: folder = "Unknown-Date" if record.is_primary else "Duplicates-Unknown-Date"
        original = sanitize_filename(record.original_filename); stem, suffix = PurePosixPath(original).stem, PurePosixPath(original).suffix
        if not record.is_primary:
            index = duplicate_index.get(record.duplicate_group_id or record.id, 0) + 1; duplicate_index[record.duplicate_group_id or record.id] = index; name = f"{stem}__dup{index:03d}{suffix}"
        else: name = original
        candidate = f"{folder}/{name}"; number = 2
        while candidate.lower() in used:
            candidate = f"{folder}/{stem}__{number}{suffix}"; number += 1; record.warnings.append("OUTPUT_COLLISION")
        used.add(candidate.lower()); record.planned_output_path = candidate; record.output_filename = PurePosixPath(candidate).name
