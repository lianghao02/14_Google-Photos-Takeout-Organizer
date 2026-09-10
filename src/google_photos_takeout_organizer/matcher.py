from __future__ import annotations
import json
from pathlib import Path
from .models import Code, MediaRecord
from .metadata import json_date

import re
from pathlib import PurePosixPath

def sidecar_candidate_names(original_filename: str) -> list[str]:
    p = PurePosixPath(original_filename)
    name, stem = p.name, p.stem
    names = [
        f"{name}.supplemental-metadata.json",
        f"{name}.json",
        f"{stem}.json",
    ]
    num_match = re.match(r"^(.*)\((\d+)\)(\.[^.]+)$", name)
    if num_match:
        base, num, ext_part = num_match.groups()
        names.extend([
            f"{base}{ext_part}.supplemental-metadata({num}).json",
            f"{base}{ext_part}({num}).supplemental-metadata.json",
            f"{base}({num}){ext_part}.supplemental-metadata.json",
            f"{base}{ext_part}.json({num})",
            f"{base}{ext_part}({num}).json",
            f"{base}({num}){ext_part}.json",
            f"{base}.supplemental-metadata({num}).json",
            f"{base}({num}).supplemental-metadata.json",
            f"{base}({num}).json",
        ])
    return list(dict.fromkeys(names))

def _candidates(record: MediaRecord, files: list[Path], roots: dict[str, Path]) -> list[Path]:
    source = Path(record.source_path)
    expected_names = sidecar_candidate_names(record.original_filename)
    
    # 1. Exact match in the same directory
    same_dir = [p for p in files if p.parent == source.parent]
    exact_same_dir = [p for p in same_dir if p.name in expected_names]
    if exact_same_dir:
        return exact_same_dir

    # 2. Cross-archive match:
    # First check sidecars in the same relative parent folder
    rel_parent = PurePosixPath(record.relative_path).parent
    cross_candidates = []
    root_level_cross_candidates = []
    for p in files:
        if p.name not in expected_names:
            continue
        p_rel = None
        for root in roots.values():
            try:
                p_rel = PurePosixPath(p.relative_to(root).as_posix())
                break
            except ValueError:
                continue
        if p_rel is not None:
            if p_rel.parent == rel_parent:
                cross_candidates.append(p)
            elif str(p_rel.parent) in (".", ""):
                root_level_cross_candidates.append(p)

    if cross_candidates:
        return cross_candidates
    if root_level_cross_candidates:
        return root_level_cross_candidates

    # 3. Fallback: if filename was truncated or legacy format, only match within same directory
    # and require candidate stem to start with the full media stem (not arbitrary prefix)
    stem_lower = PurePosixPath(record.original_filename).stem.lower().replace(" ", "")
    strict_same_dir = [
        p for p in same_dir
        if p.stem.lower().replace(" ", "").startswith(stem_lower)
    ]
    return strict_same_dir

def match(records: list[MediaRecord], files: list[Path], roots: dict[str, Path] | None = None) -> tuple[set[Path], list[str]]:
    roots_map = roots or {}
    used: set[Path] = set(); warnings: list[str] = []
    for record in records:
        candidates = _candidates(record, files, roots_map)
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
