from __future__ import annotations
import json, shutil
from pathlib import Path, PurePosixPath
from typing import Callable
from .models import MediaRecord
from .utils import sha256, heal_fuse_if_disconnected

class SafetyConflictError(RuntimeError):
    """An existing output has different bytes and must never be overwritten."""


def _matches_expected(path: Path, size: int, digest: str | None, source: Path | None = None) -> bool:
    if not path.is_file() or path.stat().st_size != size:
        return False
    expected = digest or (sha256(source) if source and source.is_file() else None)
    return not expected or sha256(path) == expected


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
        if not cand_abs.exists() or _matches_expected(cand_abs, record.size, record.sha256, src_media):
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
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")); output.mkdir(parents=True, exist_ok=True)
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
            if destination.exists() and _matches_expected(destination, record.size, record.sha256, src_media):
                record.export_status = "COPIED"
            else:
                if destination.exists():
                    destination = _resolve_incremental_destination(output, record, src_media)
                if destination.exists():
                    record.export_status = "COPIED"
                else:
                    _copy_atomic(src_media, destination)
                    record.export_status = "COPIED"

            # Preserve matched Sidecar JSON alongside the media file when enabled
            if export_sidecars and record.json_path and record.json_status == "MATCHED":
                src_json = Path(record.json_path)
                if src_json.is_file():
                    orig_name = src_media.name
                    sidecar_name = src_json.name
                    if sidecar_name.startswith(orig_name):
                        dest_sidecar_name = destination.name + sidecar_name[len(orig_name):]
                    else:
                        dest_sidecar_name = destination.name + ".json"
                    dest_json = destination.parent / dest_sidecar_name
                    if not dest_json.exists():
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
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
