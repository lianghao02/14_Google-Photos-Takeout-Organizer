from __future__ import annotations
import json
import re
from pathlib import Path, PurePosixPath
from .models import Code, MediaRecord
from .metadata import json_date, json_date_is_upload

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

def match(records: list[MediaRecord], files: list[Path], roots: dict[str, Path] | None = None) -> tuple[set[Path], list[str]]:
    roots_map = roots or {}
    used: set[Path] = set()
    warnings: list[str] = []
    unmatched: list[MediaRecord] = list(records)
    file_order = {p: idx for idx, p in enumerate(files)}

    def run_phase1(avail: list[Path]) -> dict[str, list[Path]]:
        by_parent_name: dict[tuple[Path, str], list[Path]] = {}
        for p in avail:
            by_parent_name.setdefault((p.parent, p.name), []).append(p)
        result: dict[str, list[Path]] = {}
        for rec in unmatched:
            source_parent = Path(rec.source_path).parent
            cands: list[Path] = []
            for name in sidecar_candidate_names(rec.original_filename):
                matched = by_parent_name.get((source_parent, name))
                if matched:
                    cands.extend(matched)
            if len(cands) > 1:
                cands.sort(key=file_order.__getitem__)
            if cands:
                result[rec.id] = cands
        return result

    def run_phase2(avail: list[Path]) -> dict[str, list[Path]]:
        if not roots_map:
            return {}
        by_rel_parent_name: dict[tuple[PurePosixPath, str], list[Path]] = {}
        for p in avail:
            raw_p = getattr(p, "p", p)
            for root in roots_map.values():
                try:
                    p_rel = PurePosixPath(raw_p.relative_to(root).as_posix())
                    by_rel_parent_name.setdefault((p_rel.parent, p.name), []).append(p)
                    break
                except ValueError:
                    continue
        result: dict[str, list[Path]] = {}
        for rec in unmatched:
            rel_parent = PurePosixPath(rec.relative_path).parent
            cands: list[Path] = []
            for name in sidecar_candidate_names(rec.original_filename):
                matched = by_rel_parent_name.get((rel_parent, name))
                if matched:
                    cands.extend(matched)
            if len(cands) > 1:
                cands.sort(key=file_order.__getitem__)
            if cands:
                result[rec.id] = cands
        return result

    def run_phase3(avail: list[Path]) -> dict[str, list[Path]]:
        if not roots_map:
            return {}
        by_root_name: dict[str, list[Path]] = {}
        for p in avail:
            raw_p = getattr(p, "p", p)
            for root in roots_map.values():
                try:
                    p_rel = PurePosixPath(raw_p.relative_to(root).as_posix())
                    if str(p_rel.parent) in (".", ""):
                        by_root_name.setdefault(p.name, []).append(p)
                    break
                except ValueError:
                    continue
        result: dict[str, list[Path]] = {}
        for rec in unmatched:
            cands: list[Path] = []
            for name in sidecar_candidate_names(rec.original_filename):
                matched = by_root_name.get(name)
                if matched:
                    cands.extend(matched)
            if len(cands) > 1:
                cands.sort(key=file_order.__getitem__)
            if cands:
                result[rec.id] = cands
        return result

    def run_phase4(avail: list[Path]) -> dict[str, list[Path]]:
        by_parent_stem: dict[Path, list[tuple[str, Path]]] = {}
        for p in avail:
            by_parent_stem.setdefault(p.parent, []).append((p.stem.lower().replace(" ", ""), p))
        result: dict[str, list[Path]] = {}
        for rec in unmatched:
            source_parent = Path(rec.source_path).parent
            entries = by_parent_stem.get(source_parent)
            if not entries:
                continue
            stem_lower = PurePosixPath(rec.original_filename).stem.lower().replace(" ", "")
            if not stem_lower:
                continue
            stem_len = len(stem_lower)
            cands = [
                p
                for norm_stem, p in entries
                if norm_stem == stem_lower
                or (norm_stem.startswith(stem_lower) and norm_stem[stem_len] in (".", "(", "-", "_"))
            ]
            if cands:
                result[rec.id] = cands
        return result

    phases = [run_phase1, run_phase2, run_phase3, run_phase4]

    for phase_runner in phases:
        if not unmatched:
            break
        available = [p for p in files if p not in used]
        if not available:
            break

        rec_to_candidates = phase_runner(available)
        cand_to_recs: dict[Path, list[MediaRecord]] = {}
        for rec in unmatched:
            cands = rec_to_candidates.get(rec.id)
            if cands:
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
                if rec.json_date and json_date_is_upload(data):
                    rec.warnings.append("UPLOAD_DATE_ONLY")
                rec.album_names = sorted({str(x) for x in data.get("albums", []) if isinstance(x, str)})
            except (OSError, ValueError, json.JSONDecodeError):
                rec.json_status = "INVALID_JSON"
                rec.warnings.append(str(Code.INVALID_JSON))
            resolved_this_phase.append(rec)

        if resolved_this_phase:
            resolved_ids = {id(rec) for rec in resolved_this_phase}
            unmatched = [rec for rec in unmatched if id(rec) not in resolved_ids]

    for rec in unmatched:
        if rec.json_status not in ("MATCHED", "AMBIGUOUS_SIDECAR", "INVALID_JSON"):
            rec.json_status = "MEDIA_WITHOUT_JSON"
            rec.warnings.append(str(Code.MEDIA_WITHOUT_JSON))

    for item in set(files) - used:
        warnings.append(f"{Code.JSON_ORPHAN}:{item}")
    return used, warnings
