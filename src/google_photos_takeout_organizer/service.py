from __future__ import annotations
import json
import logging
import os
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable
from . import __version__
from .archive import extract_zip
from .models import Code
from .scanner import scan
from .matcher import match
from .metadata import image_metadata
from .date_resolver import resolve
from .dedupe import group
from .planner import plan
from .report import write_report
from .utils import heal_fuse_if_disconnected

log = logging.getLogger(__name__)

def analyze(
    inputs: list[Path],
    work: Path,
    cancel_requested: Callable[[], bool] | None = None,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    extracted = work / "extracted"
    records = []
    jsons = []
    archives = []
    warnings = []

    for index, source in enumerate(inputs, 1):
        if cancel_requested and cancel_requested():
            raise InterruptedError("CANCELLED")
        archive_id = f"archive_{index:03d}"
        root = source
        if source.suffix.lower() == ".zip":
            root = extracted / archive_id
            try:
                source_sig = f"{source.name}:{source.stat().st_size}" if source.exists() else source.name
            except OSError as exc:
                if heal_fuse_if_disconnected(exc):
                    source_sig = f"{source.name}:{source.stat().st_size}" if source.exists() else source.name
                else:
                    raise
            source_id_file = root / ".gpto-source.id"
            done_marker = root / ".gpto-extracted.ok"
            already_extracted = False
            if root.is_dir():
                try:
                    recorded_sig = source_id_file.read_text(encoding="utf-8").strip() if source_id_file.is_file() else ""
                    done_sig = done_marker.read_text(encoding="utf-8").strip() if done_marker.is_file() else ""
                except OSError:
                    recorded_sig, done_sig = "", ""
                if done_sig == source_sig:
                    already_extracted = True
                elif recorded_sig != source_sig:
                    # 舊版無標記或壓縮檔清單順序變更：清除殘留目錄避免混入舊檔案或漏解壓
                    shutil.rmtree(root, ignore_errors=True)
            if not already_extracted:
                root.mkdir(parents=True, exist_ok=True)
                try:
                    source_id_file.write_text(source_sig, encoding="utf-8")
                except OSError:
                    pass
                ext_cb = (
                    (lambda cur, tot, name, s_name=source.name: progress_callback("ANALYZE_EXTRACT", cur, tot, f"[{s_name}] {name}"))
                    if progress_callback
                    else None
                )
                # 若來源位於 Colab Google Drive FUSE (/content/drive) 而工作區在本地 SSD，先單流循序複製至本地再解壓，避免數萬次隨機 FUSE 讀取觸發 Errno 107 斷線
                use_local_staging = (
                    str(source).startswith("/content/drive")
                    and not str(work).startswith("/content/drive")
                )
                staging_zip = work / f".gpto-staging-{archive_id}.zip" if use_local_staging else None
                try:
                    zip_to_open = source
                    if staging_zip is not None:
                        if progress_callback:
                            progress_callback("ANALYZE_EXTRACT", 0, 1, f"[{source.name}] 正在高速載入至本地 SSD...")
                        for attempt in range(2):
                            try:
                                with source.open("rb") as fsrc, staging_zip.open("wb") as fdst:
                                    shutil.copyfileobj(fsrc, fdst, length=16 * 1024 * 1024)
                                break
                            except OSError as exc:
                                if attempt == 0 and heal_fuse_if_disconnected(exc):
                                    continue
                                raise
                        zip_to_open = staging_zip
                    ext_warnings = extract_zip(zip_to_open, root, cancel_requested=cancel_requested, progress_callback=ext_cb)
                finally:
                    if staging_zip is not None:
                        staging_zip.unlink(missing_ok=True)
                warnings.extend(ext_warnings)
                if not any(w == str(Code.INVALID_ZIP) for w in ext_warnings):
                    try:
                        done_marker.write_text(source_sig, encoding="utf-8")
                    except OSError:
                        pass
            elif progress_callback:
                progress_callback("ANALYZE_EXTRACT", 1, 1, f"[{source.name}] (已解壓，秒速跳過)")
        archives.append({"archive_id": archive_id, "source": str(source), "root": str(root)})
        found, sidecars = scan(root, archive_id)
        records.extend(found)
        jsons.extend(sidecars)

    # 若工作區內保留有先前波次預先解壓的跨卷 JSON Sidecar，一併納入全域配對候選池
    if extracted.is_dir():
        known_roots = {Path(a["root"]) for a in archives}
        known_jsons = set(jsons)
        for extra_dir in sorted(extracted.iterdir()):
            if extra_dir.is_dir() and extra_dir not in known_roots:
                roots_key = f"extra_{extra_dir.name}"
                archives.append({"archive_id": roots_key, "source": str(extra_dir), "root": str(extra_dir)})
                for j_file in sorted(extra_dir.rglob("*.json")):
                    if j_file.is_file() and not j_file.name.startswith(".gpto-") and j_file not in known_jsons:
                        jsons.append(j_file)
                        known_jsons.add(j_file)

    roots = {a["archive_id"]: Path(a["root"]) for a in archives}
    _, match_warnings = match(records, jsons, roots)
    warnings.extend(match_warnings)

    total_recs = len(records)

    # 多執行緒並行讀取 EXIF 與日期解析（大幅解決 Google Drive FUSE 網路單線程延遲）
    def _analyze_single(record):
        if record.media_type == "photo":
            record.width, record.height, record.exif_date, record.exif_status = image_metadata(Path(record.source_path))
        resolve(record)
        return record

    max_workers = min(16, (os.cpu_count() or 4) * 4)
    completed_count = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_analyze_single, r): r for r in records}
        for fut in as_completed(futures):
            if cancel_requested and cancel_requested():
                executor.shutdown(wait=False, cancel_futures=True)
                raise InterruptedError("CANCELLED")
            completed_count += 1
            rec = fut.result()
            if progress_callback:
                progress_callback("ANALYZE", completed_count, total_recs, rec.original_filename)

    groups = group(records)
    plan(records)
    paired_groups_count = len({r.pair_group_id for r in records if r.pair_group_id})
    summary = {
        "total_media": len(records),
        "photos": sum(r.media_type == "photo" for r in records),
        "videos": sum(r.media_type == "video" for r in records),
        "json_total": len(jsons),
        "json_matched": sum(r.json_status == "MATCHED" for r in records),
        "no_json": sum(r.json_status == "MEDIA_WITHOUT_JSON" for r in records),
        "unknown_date": sum(not r.resolved_date for r in records),
        "date_conflict": sum("DATE_CONFLICT" in r.warnings for r in records),
        "duplicate_groups": len(groups),
        "duplicate_files": sum(not r.is_primary for r in records),
        "paired_groups": paired_groups_count,
        "unsupported": sum(r.media_type == "unsupported" for r in records),
        "planned_primary": sum(r.is_primary for r in records),
        "planned_duplicate": sum(not r.is_primary for r in records),
        "warnings": sum(len(r.warnings) for r in records) + len(warnings),
        "errors": sum(len(r.errors) for r in records),
    }
    manifest = {
        "schema_version": "0.1",
        "app_version": __version__,
        "dataset_id": str(uuid.uuid4()),
        "input_archives": archives,
        "media_records": [r.to_dict() for r in records],
        "duplicate_groups": [g.to_dict() for g in groups],
        "summary": summary,
        "warnings": warnings,
        "errors": [],
        "export_state": "PLANNED",
    }
    (work / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (work / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(manifest, work / "report.html")
    return manifest
