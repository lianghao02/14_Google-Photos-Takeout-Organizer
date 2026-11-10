from __future__ import annotations
import os
from collections import defaultdict
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from .models import DuplicateGroup, MediaRecord
from .utils import sha256

def group(records: list[MediaRecord]) -> list[DuplicateGroup]:
    by_size: dict[int, list[MediaRecord]] = defaultdict(list)
    for record in records:
        if record.media_type != "unsupported":
            by_size[record.size].append(record)

    groups: list[DuplicateGroup] = []

    # 1. 僅對檔案大小相同的群組並行計算 SHA256 進行精確去重（不同大小絕不可能重複）
    collision_records = [r for same_size in by_size.values() if len(same_size) >= 2 for r in same_size]
    if collision_records:
        def _hash_record(r: MediaRecord) -> None:
            if not r.sha256:
                r.sha256 = sha256(Path(r.source_path))
        with ThreadPoolExecutor(max_workers=min(16, (os.cpu_count() or 4) * 4)) as ex:
            list(ex.map(_hash_record, collision_records))

    for same_size in by_size.values():
        if len(same_size) < 2:
            continue
        hashes: dict[str, list[MediaRecord]] = defaultdict(list)
        for record in same_size:
            if not record.sha256:
                record.sha256 = sha256(Path(record.source_path))
            hashes[record.sha256].append(record)

        for digest, members in hashes.items():
            if len(members) < 2:
                continue
            ranked = sorted(
                members,
                key=lambda r: (
                    r.json_status != "MATCHED",
                    r.exif_status != "FOUND",
                    r.original_filename.lower().count("edited"),
                    r.relative_path.lower(),
                ),
            )
            primary = ranked[0]
            gid = "dup-" + digest[:16]
            dates = [r for r in ranked if r.resolved_date]
            chosen = dates[0] if dates else primary
            for record in ranked:
                record.duplicate_group_id = gid
                record.duplicate_status = "PRIMARY" if record is primary else "DUPLICATE"
                record.is_primary = record is primary
                if chosen.resolved_date:
                    record.resolved_date = chosen.resolved_date
                    record.date_precision = chosen.date_precision
                    record.date_source = chosen.date_source
                    record.date_confidence = chosen.date_confidence
            groups.append(
                DuplicateGroup(
                    gid,
                    digest,
                    [r.id for r in ranked],
                    primary.id,
                    [r.id for r in ranked[1:]],
                    sorted({a for r in ranked for a in r.album_names}),
                    chosen.resolved_date,
                    chosen.date_source,
                    chosen.date_confidence,
                    sorted({r.date_source for r in ranked}),
                )
            )

    # 2. 雲端最佳化：非碰撞的獨立檔案免於全量計算 SHA-256（直接節省 20+ 小時 FUSE 網路全量下載）
    # 若環境變數指定 STRICT_FULL_SHA256=1，則使用多執行緒並行補齊
    if os.environ.get("STRICT_FULL_SHA256") == "1":
        pending = [r for r in records if r.sha256 is None]
        if pending:
            def _calc(r):
                r.sha256 = sha256(Path(r.source_path))
            with ThreadPoolExecutor(max_workers=min(16, (os.cpu_count() or 4) * 4)) as ex:
                list(ex.map(_calc, pending))

    return groups
