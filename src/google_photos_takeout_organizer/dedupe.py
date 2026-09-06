from __future__ import annotations
from collections import defaultdict
from .models import DuplicateGroup, MediaRecord
from .utils import sha256

def group(records: list[MediaRecord]) -> list[DuplicateGroup]:
    by_size: dict[int, list[MediaRecord]] = defaultdict(list)
    for record in records:
        if record.media_type != "unsupported": by_size[record.size].append(record)
    groups: list[DuplicateGroup] = []
    for same_size in by_size.values():
        if len(same_size) < 2: continue
        hashes: dict[str, list[MediaRecord]] = defaultdict(list)
        for record in same_size: record.sha256 = sha256(__import__("pathlib").Path(record.source_path)); hashes[record.sha256].append(record)
        for digest, members in hashes.items():
            if len(members) < 2: continue
            ranked = sorted(members, key=lambda r: (r.json_status != "MATCHED", r.exif_status != "FOUND", r.original_filename.lower().count("edited"), r.relative_path.lower()))
            primary = ranked[0]; gid = "dup-" + digest[:16]
            dates = [r for r in ranked if r.resolved_date]
            chosen = dates[0] if dates else primary
            for record in ranked:
                record.duplicate_group_id = gid; record.duplicate_status = "PRIMARY" if record is primary else "DUPLICATE"; record.is_primary = record is primary
                if chosen.resolved_date: record.resolved_date, record.date_precision, record.date_source, record.date_confidence = chosen.resolved_date, chosen.date_precision, chosen.date_source, chosen.date_confidence
            groups.append(DuplicateGroup(gid, digest, [r.id for r in ranked], primary.id, [r.id for r in ranked[1:]], sorted({a for r in ranked for a in r.album_names}), chosen.resolved_date, chosen.date_source, chosen.date_confidence, sorted({r.date_source for r in ranked})))
    for record in records:
        if record.sha256 is None: record.sha256 = sha256(__import__("pathlib").Path(record.source_path))
    return groups
