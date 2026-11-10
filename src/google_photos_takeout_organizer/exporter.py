from __future__ import annotations
import json, shutil, stat
from pathlib import Path, PurePosixPath
from typing import Callable
from .models import MediaRecord
from .utils import sha256, heal_fuse_if_disconnected, run_with_fuse_retry, safe_stat

class SafetyConflictError(RuntimeError):
    """An existing output has different bytes and must never be overwritten."""


def _is_regular_file(path: Path) -> tuple[bool, int]:
    st = run_with_fuse_retry(safe_stat, path)
    if st is None or not stat.S_ISREG(st.st_mode):
        return False, -1
    return True, st.st_size


def _matches_expected(path: Path, size: int, digest: str | None, source: Path | None = None) -> bool:
    exists, actual_size = _is_regular_file(path)
    if not exists or actual_size != size:
        return False
    src_ok = bool(source and _is_regular_file(source)[0])
    expected = digest or (run_with_fuse_retry(sha256, source) if src_ok else None)
    return not expected or run_with_fuse_retry(sha256, path) == expected


def _copy_atomic(source: Path, destination: Path) -> None:
    """先寫暫存檔再改名，中斷或磁碟滿時不會在最終檔名留下殘缺檔。"""
    partial = destination.with_name(f".{destination.name}.gpto-part")
    for attempt in range(2):
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, partial)
            partial.replace(destination)
            return
        except BaseException as exc:
            try:
                partial.unlink(missing_ok=True)
            except OSError:
                pass
            if attempt == 0 and heal_fuse_if_disconnected(exc):
                continue
            raise


def _resolve_incremental_destination(output: Path, record: MediaRecord, src_media: Path) -> Path:
    """當跨波次或增量匯出遇到目標路徑已有不同內容的檔案時，自動遞增檔名避免覆寫或崩潰。"""
    rel = PurePosixPath(record.planned_output_path)
    stem = rel.stem
    suffix = rel.suffix
    parent = rel.parent
    num = 2
    while True:
        cand_rel = parent / f"{stem}__{num}{suffix}"
        cand_abs = output / str(cand_rel)
        exists, _ = _is_regular_file(cand_abs)
        if not exists or _matches_expected(cand_abs, record.size, record.sha256, src_media):
            record.planned_output_path = cand_rel.as_posix()
            record.output_filename = cand_rel.name
            if "OUTPUT_COLLISION" not in record.warnings:
                record.warnings.append("OUTPUT_COLLISION")
            return cand_abs
        num += 1


def export(
    manifest_path: Path,
    output: Path,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
    cancel_requested: Callable[[], bool] | None = None,
    export_sidecars: bool = True,
) -> dict:
    manifest = json.loads(run_with_fuse_retry(manifest_path.read_text, encoding="utf-8"))
    run_with_fuse_retry(output.mkdir, parents=True, exist_ok=True)
    records = manifest["media_records"]
    for current, data in enumerate(records, 1):
        if cancel_requested and cancel_requested():
            manifest["export_state"] = "CANCELLED"
            break
        record = MediaRecord.from_dict(data); destination = output / record.planned_output_path
        src_media = Path(record.source_path)
        try:
            if progress_callback:
                progress_callback("EXPORT", current, len(records), destination.name)
            dest_exists, _ = _is_regular_file(destination)
            if dest_exists and _matches_expected(destination, record.size, record.sha256, src_media):
                record.export_status = "COPIED"
            else:
                if dest_exists:
                    destination = _resolve_incremental_destination(output, record, src_media)
                cand_exists, _ = _is_regular_file(destination)
                if cand_exists:
                    record.export_status = "COPIED"
                else:
                    _copy_atomic(src_media, destination)
                    record.export_status = "COPIED"

            # Preserve matched Sidecar JSON alongside the media file when enabled
            if export_sidecars and record.json_path and record.json_status == "MATCHED":
                src_json = Path(record.json_path)
                if _is_regular_file(src_json)[0]:
                    orig_name = src_media.name
                    sidecar_name = src_json.name
                    if sidecar_name.startswith(orig_name):
                        dest_sidecar_name = destination.name + sidecar_name[len(orig_name):]
                    else:
                        dest_sidecar_name = destination.name + ".json"
                    dest_json = destination.parent / dest_sidecar_name
                    json_exists, _ = _is_regular_file(dest_json)
                    if not json_exists:
                        _copy_atomic(src_json, dest_json)
            if cancel_requested and cancel_requested():
                manifest["export_state"] = "CANCELLED"
                data.update(record.to_dict())
                break
        except SafetyConflictError:
            manifest["export_state"] = "SAFETY_CONFLICT"
            raise
        except OSError:
            record.export_status = "FAILED"
            record.errors.append("COPY_FAILED")
        data.update(record.to_dict())
    else:
        manifest["export_state"] = "COMPLETED"
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2)
    run_with_fuse_retry((output / "manifest.json").write_text, manifest_text, encoding="utf-8")
    return manifest
