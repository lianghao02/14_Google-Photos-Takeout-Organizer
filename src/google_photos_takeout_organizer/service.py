from __future__ import annotations
import copy
import json
import logging
import os
import shutil
import stat
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath
from typing import Callable
from . import __version__
from .archive import extract_zip
from .models import Code, MediaRecord
from .scanner import scan
from .matcher import match
from .metadata import image_metadata
from .date_resolver import resolve
from .dedupe import group
from .planner import plan
from .report import write_report
from .utils import heal_fuse_if_disconnected, run_with_fuse_retry, safe_stat, sanitize_filename

log = logging.getLogger(__name__)


def _build_summary(records: list[dict | MediaRecord], json_total: int, groups: list, extra_warnings: list[str]) -> dict:
    def _get(item, key, default=None):
        return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)

    paired_groups_count = len({_get(r, "pair_group_id") for r in records if _get(r, "pair_group_id")})
    return {
        "total_media": len(records),
        "photos": sum(_get(r, "media_type") == "photo" for r in records),
        "videos": sum(_get(r, "media_type") == "video" for r in records),
        "json_total": json_total,
        "json_matched": sum(_get(r, "json_status") == "MATCHED" for r in records),
        "no_json": sum(_get(r, "json_status") == "MEDIA_WITHOUT_JSON" for r in records),
        "unknown_date": sum(not _get(r, "resolved_date") for r in records),
        "date_conflict": sum("DATE_CONFLICT" in (_get(r, "warnings") or []) for r in records),
        "duplicate_groups": len(groups),
        "duplicate_files": sum(not _get(r, "is_primary", True) for r in records),
        "paired_groups": paired_groups_count,
        "unsupported": sum(_get(r, "media_type") == "unsupported" for r in records),
        "planned_primary": sum(bool(_get(r, "is_primary", True)) for r in records),
        "planned_duplicate": sum(not _get(r, "is_primary", True) for r in records),
        "warnings": sum(len(_get(r, "warnings") or []) for r in records) + len(extra_warnings),
        "errors": sum(len(_get(r, "errors") or []) for r in records),
    }


def analyze(
    inputs: list[Path],
    work: Path,
    cancel_requested: Callable[[], bool] | None = None,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
    archive_start_index: int = 1,
) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    extracted = work / "extracted"
    records = []
    jsons = []
    archives = []
    warnings = []

    for index, source in enumerate(inputs, archive_start_index):
        if cancel_requested and cancel_requested():
            raise InterruptedError("CANCELLED")
        archive_id = f"archive_{index:03d}"
        root = source
        if source.suffix.lower() == ".zip":
            root = extracted / archive_id
            st = run_with_fuse_retry(safe_stat, source)
            source_sig = f"{source.name}:{st.st_size}" if st is not None else source.name
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
                        def _stage_zip() -> None:
                            with source.open("rb") as fsrc, staging_zip.open("wb") as fdst:
                                shutil.copyfileobj(fsrc, fdst, length=16 * 1024 * 1024)
                        run_with_fuse_retry(_stage_zip)
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
                pool_jsons = [
                    j_file for j_file in sorted(extra_dir.rglob("*.json"))
                    if j_file.is_file() and not j_file.name.startswith(".gpto-") and j_file not in known_jsons
                ]
                if pool_jsons:
                    roots_key = f"extra_{extra_dir.name}"
                    archives.append({"archive_id": roots_key, "source": str(extra_dir), "root": str(extra_dir)})
                    jsons.extend(pool_jsons)
                    known_jsons.update(pool_jsons)

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
    summary = _build_summary(records, len(jsons), groups, warnings)
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


def _target_folder_for_record(rec: MediaRecord) -> str:
    if rec.is_primary and any(
        code in rec.warnings for code in ("DATE_CONFLICT", "AMBIGUOUS_SIDECAR", "INVALID_JSON", "LOW_CONFIDENCE_DATE")
    ):
        if "DATE_CONFLICT" in rec.warnings:
            return "Review/Date-Conflict"
        if "AMBIGUOUS_SIDECAR" in rec.warnings:
            return "Review/Ambiguous-Sidecar"
        if "INVALID_JSON" in rec.warnings:
            return "Review/Invalid-JSON"
        if "LOW_CONFIDENCE_DATE" in rec.warnings:
            return "Review/Low-Confidence-Date"
        return "Review"
    root = "Photos_Archive" if rec.is_primary else "Duplicates"
    date = rec.resolved_date or ""
    parts = date.split("-")
    if len(parts) >= 2:
        return f"{root}/{parts[0]}/{parts[1]}"
    if len(parts) == 1 and parts[0]:
        return f"{root}/{parts[0]}/Unknown-Month"
    return "Unknown-Date" if rec.is_primary else "Duplicates-Unknown-Date"


def reconcile_cross_wave(
    all_records: list[dict],
    extracted_root: Path,
    output_dir: Path,
) -> tuple[list[dict], list[str], int, int]:
    """跨波次雙向補配對：為前波尚未取得 JSON 的媒體比對後波剩餘孤兒 JSON，並安全搬移至正確分類目錄。"""
    if not extracted_root.is_dir() or not all_records:
        return all_records, [], 0, 0

    roots: dict[str, Path] = {}
    remaining_jsons: list[Path] = []
    for sub in sorted(extracted_root.iterdir()):
        if sub.is_dir():
            roots[sub.name] = sub
            for j_file in sorted(sub.rglob("*.json")):
                if j_file.is_file() and not j_file.name.startswith(".gpto-"):
                    remaining_jsons.append(j_file)

    if not remaining_jsons:
        return all_records, [], 0, 0

    unmatched_indices: list[int] = []
    temp_records: list[MediaRecord] = []
    by_pair_group: dict[str, list[int]] = {}
    for idx, rec_dict in enumerate(all_records):
        pgid = rec_dict.get("pair_group_id")
        if pgid:
            by_pair_group.setdefault(pgid, []).append(idx)
        if rec_dict.get("json_status") == "MEDIA_WITHOUT_JSON" and not rec_dict.get("json_path"):
            rec = MediaRecord.from_dict(copy.deepcopy(rec_dict))
            rec.warnings = [w for w in rec.warnings if w != str(Code.MEDIA_WITHOUT_JSON)]
            unmatched_indices.append(idx)
            temp_records.append(rec)

    if not temp_records:
        orphan_warnings = [f"{Code.JSON_ORPHAN}:{j}" for j in remaining_jsons]
        return all_records, orphan_warnings, 0, 0

    used_jsons, orphan_warnings = match(temp_records, remaining_jsons, roots)
    matched_count = 0
    moved_count = 0

    # 確保 PRIMARY_PHOTO / 獨立檔案先於 LIVE_PHOTO_VIDEO / RAW_PAIR 處理，避免副檔搶先判斷而拆散配對
    ordered_pairs = sorted(
        zip(unmatched_indices, temp_records),
        key=lambda item: (item[1].pair_role in ("LIVE_PHOTO_VIDEO", "RAW_PAIR"), item[0]),
    )

    for idx, rec in ordered_pairs:
        if rec.json_status not in ("MATCHED", "AMBIGUOUS_SIDECAR", "INVALID_JSON"):
            continue

        # 略過或僅更新附屬於主照的成對副檔 Metadata，絕不單獨拆散 Live Photo / RAW 配對
        if rec.pair_role in ("LIVE_PHOTO_VIDEO", "RAW_PAIR") and rec.pair_group_id:
            siblings = [all_records[i] for i in by_pair_group.get(rec.pair_group_id, []) if i != idx]
            primary_siblings = [s for s in siblings if s.get("pair_role") == "PRIMARY_PHOTO"]
            if primary_siblings:
                if any(s.get("resolved_date") for s in primary_siblings):
                    continue
                # 主照依然缺日期時僅記錄副檔本身的 JSON 資訊，不單獨移動檔案破壞配對
                matched_count += 1
                all_records[idx].update(rec.to_dict())
                continue

        matched_count += 1
        rec.warnings = [w for w in rec.warnings if w not in (str(Code.NO_DATE), "LOW_CONFIDENCE_DATE")]
        if rec.json_status == "MATCHED":
            resolve(rec)
        else:
            if not rec.resolved_date and "NO_DATE" not in rec.warnings:
                rec.warnings.append(str(Code.NO_DATE))

        old_rel = rec.planned_output_path
        new_folder = _target_folder_for_record(rec)
        old_folder = PurePosixPath(old_rel).parent.as_posix() if old_rel else ""

        # 確認是否需要跨資料夾安全搬移已匯出的檔案（含伴隨副檔）
        if old_rel and new_folder != old_folder:
            companion_indices = [
                i for i in by_pair_group.get(rec.pair_group_id or "", [])
                if i != idx and all_records[i].get("pair_role") in ("LIVE_PHOTO_VIDEO", "RAW_PAIR")
            ]
            member_indices = [idx, *companion_indices]
            member_recs = [rec] + [MediaRecord.from_dict(copy.deepcopy(all_records[i])) for i in companion_indices]
            for m in member_recs[1:]:
                m.warnings = [w for w in m.warnings if w not in (str(Code.NO_DATE), "LOW_CONFIDENCE_DATE")]
                if rec.resolved_date or "DATE_CONFLICT" in rec.warnings:
                    m.resolved_date = rec.resolved_date
                    m.date_source = rec.date_source
                    m.date_confidence = rec.date_confidence
                    m.date_precision = rec.date_precision
                for warn_code in ("LOW_CONFIDENCE_DATE", "DATE_CONFLICT"):
                    if warn_code in rec.warnings and warn_code not in m.warnings:
                        m.warnings.append(warn_code)

            old_files = [output_dir / str(m.planned_output_path) for m in member_recs]
            old_stats = [run_with_fuse_retry(safe_stat, f) for f in old_files]
            if all(st is not None and stat.S_ISREG(st.st_mode) for st in old_stats):
                base_name = sanitize_filename(PurePosixPath(str(old_rel)).name)
                base_stem = PurePosixPath(base_name).stem
                cand_stem = base_stem
                num = 2
                while True:
                    cand_rels = [f"{new_folder}/{cand_stem}{PurePosixPath(str(m.planned_output_path)).suffix}" for m in member_recs]
                    cand_abs_list = [output_dir / cr for cr in cand_rels]
                    if all(run_with_fuse_retry(safe_stat, ca) is None for ca in cand_abs_list):
                        break
                    cand_stem = f"{base_stem}__{num}"
                    num += 1
                    if "OUTPUT_COLLISION" not in rec.warnings:
                        rec.warnings.append("OUTPUT_COLLISION")

                for m_idx, m_rec, src_f, dst_f, dst_rel in zip(member_indices, member_recs, old_files, cand_abs_list, cand_rels):
                    run_with_fuse_retry(dst_f.parent.mkdir, parents=True, exist_ok=True)
                    run_with_fuse_retry(src_f.replace, dst_f)
                    m_rec.planned_output_path = dst_rel
                    m_rec.output_filename = PurePosixPath(dst_rel).name
                    all_records[m_idx].update(m_rec.to_dict())
                    moved_count += 1
                continue

        all_records[idx].update(rec.to_dict())

    for used_j in used_jsons:
        try:
            used_j.unlink(missing_ok=True)
        except OSError:
            pass

    return all_records, orphan_warnings, matched_count, moved_count


def merge_wave_manifests(
    wave_manifests: list[dict],
    output_dir: Path,
    extra_warnings: list[str] | None = None,
    orphan_warnings: list[str] | None = None,
) -> dict:
    """合併所有波次的清冊、驗證狀態並寫入最終完整 manifest.json、verification.json 與 report.html。"""
    all_archives: list[dict] = []
    all_records: list[dict] = []
    all_dup_groups: list[dict] = []
    merged_warnings: list[str] = []
    seen_warnings: set[str] = set()
    total_json_seen = 0

    for wm in wave_manifests:
        all_archives.extend(wm.get("input_archives", []))
        all_records.extend(wm.get("media_records", []))
        all_dup_groups.extend(wm.get("duplicate_groups", []))
        total_json_seen += int(wm.get("summary", {}).get("json_total", 0))
        for w in wm.get("warnings", []):
            if orphan_warnings is not None and str(w).startswith(f"{Code.JSON_ORPHAN}:"):
                continue
            if w not in seen_warnings:
                seen_warnings.add(w)
                merged_warnings.append(w)

    for w in (extra_warnings or []) + (orphan_warnings or []):
        if w not in seen_warnings:
            seen_warnings.add(w)
            merged_warnings.append(w)

    verified = sum(1 for r in all_records if r.get("export_status") == "VERIFIED")
    failed = sum(1 for r in all_records if r.get("export_status") == "FAILED")
    verification = {
        "result": "PASS" if (failed == 0 and verified == len(all_records)) else "FAIL",
        "verified": verified,
        "failed": failed,
    }
    summary = _build_summary(all_records, total_json_seen, all_dup_groups, merged_warnings)
    final_manifest = {
        "schema_version": "0.1",
        "app_version": __version__,
        "dataset_id": str(uuid.uuid4()),
        "input_archives": all_archives,
        "media_records": all_records,
        "duplicate_groups": all_dup_groups,
        "summary": summary,
        "warnings": merged_warnings,
        "errors": [],
        "export_state": "COMPLETED" if failed == 0 else "PARTIAL",
        "verification": verification,
    }
    run_with_fuse_retry(output_dir.mkdir, parents=True, exist_ok=True)
    run_with_fuse_retry(
        (output_dir / "verification.json").write_text,
        json.dumps(verification, indent=2),
        encoding="utf-8",
    )
    run_with_fuse_retry(
        (output_dir / "manifest.json").write_text,
        json.dumps(final_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    run_with_fuse_retry(write_report, final_manifest, output_dir / "report.html")
    return final_manifest
