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
    used: set[Path] = set()
    warnings: list[str] = []
    unmatched: list[MediaRecord] = list(records)

    def get_phase1_candidates(rec: MediaRecord, available_files: list[Path]) -> list[Path]:
        source = Path(rec.source_path)
        expected = sidecar_candidate_names(rec.original_filename)
        return [p for p in available_files if p.parent == source.parent and p.name in expected]

    def get_phase2_candidates(rec: MediaRecord, available_files: list[Path]) -> list[Path]:
        expected = sidecar_candidate_names(rec.original_filename)
        rel_parent = PurePosixPath(rec.relative_path).parent
        cands = []
        for p in available_files:
            if p.name not in expected:
                continue
            for root in roots_map.values():
                try:
                    p_rel = PurePosixPath(p.relative_to(root).as_posix())
                    if p_rel.parent == rel_parent:
                        cands.append(p)
                    break
                except ValueError:
                    continue
        return cands

    def get_phase3_candidates(rec: MediaRecord, available_files: list[Path]) -> list[Path]:
        expected = sidecar_candidate_names(rec.original_filename)
        cands = []
        for p in available_files:
            if p.name not in expected:
                continue
            for root in roots_map.values():
                try:
                    p_rel = PurePosixPath(p.relative_to(root).as_posix())
                    if str(p_rel.parent) in (".", ""):
                        cands.append(p)
                    break
                except ValueError:
                    continue
        return cands

    def get_phase4_candidates(rec: MediaRecord, available_files: list[Path]) -> list[Path]:
        source = Path(rec.source_path)
        stem_lower = PurePosixPath(rec.original_filename).stem.lower().replace(" ", "")
        return [
            p for p in available_files
            if p.parent == source.parent and p.stem.lower().replace(" ", "").startswith(stem_lower)
        ]

    phases = [
        get_phase1_candidates,
        get_phase2_candidates,
        get_phase3_candidates,
        get_phase4_candidates,
    ]

    for phase_fn in phases:
        if not unmatched:
            break
        available = [p for p in files if p not in used]
        if not available:
            break

        rec_to_candidates: dict[str, list[Path]] = {}
        cand_to_recs: dict[Path, list[MediaRecord]] = {}

        for rec in unmatched:
            cands = phase_fn(rec, available)
            if cands:
                rec_to_candidates[rec.id] = cands
                for c in cands:
                    cand_to_recs.setdefault(c, []).append(rec)

        resolved_this_phase: list[MediaRecord] = []
        for rec in unmatched:
            cands = rec_to_candidates.get(rec.id)
            if not cands:
                continue
            if len(cands) > 1:
                rec.json_status = "AMBIGUOUS_SIDECAR"
                rec.warnings.append(str(Code.AMBIGUOUS_SIDECAR))
                resolved_this_phase.append(rec)
                continue

            cand = cands[0]
            competing = cand_to_recs.get(cand, [])
            if len(competing) > 1:
                for comp in competing:
                    if comp.json_status != "AMBIGUOUS_SIDECAR":
                        comp.json_status = "AMBIGUOUS_SIDECAR"
                        comp.warnings.append(str(Code.AMBIGUOUS_SIDECAR))
                        resolved_this_phase.append(comp)
                continue

            used.add(cand)
            rec.json_path = str(cand)
            rec.json_status = "MATCHED"
            try:
                data = json.loads(cand.read_text(encoding="utf-8"))
                rec.json_date = json_date(data)
                rec.album_names = sorted({str(x) for x in data.get("albums", []) if isinstance(x, str)})
            except (OSError, ValueError, json.JSONDecodeError):
                rec.json_status = "INVALID_JSON"
                rec.warnings.append(str(Code.INVALID_JSON))
            resolved_this_phase.append(rec)

        for rec in resolved_this_phase:
            if rec in unmatched:
                unmatched.remove(rec)

    for rec in unmatched:
        if rec.json_status not in ("MATCHED", "AMBIGUOUS_SIDECAR", "INVALID_JSON"):
            rec.json_status = "MEDIA_WITHOUT_JSON"
            rec.warnings.append(str(Code.MEDIA_WITHOUT_JSON))

    for item in set(files) - used:
        warnings.append(f"{Code.JSON_ORPHAN}:{item}")
    return used, warnings
