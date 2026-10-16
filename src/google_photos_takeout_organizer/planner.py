from __future__ import annotations
from pathlib import PurePosixPath
from .models import MediaRecord
from .utils import sanitize_filename

PHOTO_EXTS = {".jpg", ".jpeg", ".heic", ".heif", ".png", ".webp"}
LIVE_VIDEO_EXTS = {".mov", ".mp4"}
RAW_EXTS = {".arw", ".cr2", ".cr3", ".nef", ".dng", ".raf", ".rw2", ".orf"}


def identify_pairs(records: list[MediaRecord]) -> dict[str, MediaRecord]:
    """識別 Live Photo (照片 + MOV/MP4) 與 RAW+JPG 成對關係。"""
    by_parent: dict[str, list[MediaRecord]] = {}
    for r in records:
        parent = str(PurePosixPath(r.relative_path).parent)
        by_parent.setdefault(parent, []).append(r)

    child_to_primary: dict[str, MediaRecord] = {}
    for parent, group in by_parent.items():
        by_stem: dict[str, list[MediaRecord]] = {}
        for r in group:
            stem = PurePosixPath(r.original_filename).stem.lower()
            by_stem.setdefault(stem, []).append(r)

        for stem, stem_members in by_stem.items():
            if len(stem_members) < 2:
                continue

            photos = [m for m in stem_members if m.extension.lower() in PHOTO_EXTS]
            live_videos = [m for m in stem_members if m.extension.lower() in LIVE_VIDEO_EXTS]
            raws = [m for m in stem_members if m.extension.lower() in RAW_EXTS]

            if photos and live_videos:
                primary = photos[0]
                gid = f"pair-live-{primary.id[:8]}"
                primary.pair_group_id = gid
                primary.pair_role = "PRIMARY_PHOTO"

                for v in live_videos:
                    v.pair_group_id = gid
                    v.pair_role = "LIVE_PHOTO_VIDEO"
                    child_to_primary[v.id] = primary
                    if primary.resolved_date:
                        v.resolved_date = primary.resolved_date
                        v.date_source = primary.date_source
                        v.date_confidence = primary.date_confidence
                        v.date_precision = primary.date_precision

            elif photos and raws:
                primary = photos[0]
                gid = f"pair-raw-{primary.id[:8]}"
                primary.pair_group_id = gid
                primary.pair_role = "PRIMARY_PHOTO"

                for raw in raws:
                    raw.pair_group_id = gid
                    raw.pair_role = "RAW_PAIR"
                    child_to_primary[raw.id] = primary
                    if primary.resolved_date:
                        raw.resolved_date = primary.resolved_date
                        raw.date_source = primary.date_source
                        raw.date_confidence = primary.date_confidence
                        raw.date_precision = primary.date_precision

    return child_to_primary


def plan(records: list[MediaRecord]) -> None:
    child_to_primary = identify_pairs(records)
    used: set[str] = set()
    duplicate_index: dict[str, int] = {}

    # 確保 PRIMARY_PHOTO 比其 LIVE_PHOTO_VIDEO / RAW_PAIR 先被處理
    sorted_records = sorted(
        records,
        key=lambda r: (
            r.duplicate_group_id or "",
            not r.is_primary,
            r.pair_role in ("LIVE_PHOTO_VIDEO", "RAW_PAIR"),
            r.relative_path,
        ),
    )

    for record in sorted_records:
        suffix = PurePosixPath(record.original_filename).suffix

        # 如果此檔案是成對的副成員 (例如 Live Photo MOV 或 RAW)，且主照片已規劃路徑
        if record.id in child_to_primary:
            primary = child_to_primary[record.id]
            if primary.planned_output_path:
                primary_p = PurePosixPath(primary.planned_output_path)
                folder = str(primary_p.parent)
                candidate = f"{folder}/{primary_p.stem}{suffix}"
                used.add(candidate.lower())
                record.planned_output_path = candidate
                record.output_filename = PurePosixPath(candidate).name
                continue

        if record.is_primary and any(code in record.warnings for code in ("DATE_CONFLICT", "AMBIGUOUS_SIDECAR", "INVALID_JSON")):
            if "DATE_CONFLICT" in record.warnings:
                folder = "Review/Date-Conflict"
            elif "AMBIGUOUS_SIDECAR" in record.warnings:
                folder = "Review/Ambiguous-Sidecar"
            elif "INVALID_JSON" in record.warnings:
                folder = "Review/Invalid-JSON"
            else:
                folder = "Review"
        else:
            root = "Photos_Archive" if record.is_primary else "Duplicates"
            date = record.resolved_date or ""
            parts = date.split("-")
            if len(parts) >= 2:
                folder = f"{root}/{parts[0]}/{parts[1]}"
            elif len(parts) == 1 and parts[0]:
                folder = f"{root}/{parts[0]}/Unknown-Month"
            else:
                folder = "Unknown-Date" if record.is_primary else "Duplicates-Unknown-Date"

        original = sanitize_filename(record.original_filename)
        stem = PurePosixPath(original).stem
        if not record.is_primary:
            index = duplicate_index.get(record.duplicate_group_id or record.id, 0) + 1
            duplicate_index[record.duplicate_group_id or record.id] = index
            name = f"{stem}__dup{index:03d}{suffix}"
        else:
            name = original

        candidate = f"{folder}/{name}"
        number = 2
        while candidate.lower() in used:
            candidate = f"{folder}/{stem}__{number}{suffix}"
            number += 1
            record.warnings.append("OUTPUT_COLLISION")

        used.add(candidate.lower())
        record.planned_output_path = candidate
        record.output_filename = PurePosixPath(candidate).name
