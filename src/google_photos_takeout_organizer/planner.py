from __future__ import annotations
from pathlib import PurePosixPath
from .models import MediaRecord
from .utils import sanitize_filename

PHOTO_EXTS = {".jpg", ".jpeg", ".heic", ".heif", ".png", ".webp"}
LIVE_VIDEO_EXTS = {".mov", ".mp4"}
RAW_EXTS = {".arw", ".cr2", ".cr3", ".nef", ".dng", ".raf", ".rw2", ".orf"}


def identify_pairs(records: list[MediaRecord]) -> dict[str, MediaRecord]:
    """識別 Live Photo (照片 + MOV/MP4) 與 RAW+JPG 成對關係。"""
    by_parent: dict[tuple[str, str], list[MediaRecord]] = {}
    for r in records:
        parent = str(PurePosixPath(r.relative_path).parent)
        r.pair_group_id = None
        r.pair_role = None
        by_parent.setdefault((r.archive_id, parent), []).append(r)

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

            # 同來源、同資料夾且主照片唯一才成對，避免僅憑同名誤綁。
            companions = live_videos or raws
            if len(photos) != 1 or len({m.extension.lower() for m in companions}) != len(companions):
                continue

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
    children: dict[str, list[MediaRecord]] = {}
    for child in records:
        child.planned_output_path = None
        child.output_filename = None
        if child.id in child_to_primary:
            children.setdefault(child_to_primary[child.id].id, []).append(child)
    used: set[str] = set()
    duplicate_index: dict[str, int] = {}

    # 確保 PRIMARY_PHOTO 比其 LIVE_PHOTO_VIDEO / RAW_PAIR 先被處理
    sorted_records = sorted(
        records,
        key=lambda r: (
            r.pair_role in ("LIVE_PHOTO_VIDEO", "RAW_PAIR"),
            r.duplicate_group_id or "",
            not r.is_primary,
            r.relative_path,
        ),
    )

    for record in sorted_records:
        suffix = PurePosixPath(record.original_filename).suffix

        # 如果此檔案是成對的副成員 (例如 Live Photo MOV 或 RAW)，且主照片已規劃路徑
        if record.id in child_to_primary:
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

        # 整組預留名稱，避免照片名稱可用、伴隨影片名稱已被占用。
        members = [record, *children.get(record.id, [])]
        candidate_stem = PurePosixPath(name).stem
        number = 2
        while True:
            candidates = [f"{folder}/{candidate_stem}{PurePosixPath(m.original_filename).suffix}" for m in members]
            if all(candidate.lower() not in used for candidate in candidates):
                break
            candidate_stem = f"{stem}__{number}"
            number += 1
            if "OUTPUT_COLLISION" not in record.warnings:
                record.warnings.append("OUTPUT_COLLISION")

        for member, candidate in zip(members, candidates):
            used.add(candidate.lower())
            member.planned_output_path = candidate
            member.output_filename = PurePosixPath(candidate).name
