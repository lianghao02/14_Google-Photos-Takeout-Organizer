from __future__ import annotations
import json, shutil
from pathlib import Path
from typing import Callable
from .models import MediaRecord
from .utils import sha256

class SafetyConflictError(RuntimeError):
    """An existing output has different bytes and must never be overwritten."""


def _matches_expected(path: Path, size: int, digest: str) -> bool:
    return path.is_file() and path.stat().st_size == size and sha256(path) == digest


def export(
    manifest_path: Path,
    output: Path,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
    cancel_requested: Callable[[], bool] | None = None,
) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")); output.mkdir(parents=True, exist_ok=True)
    records = manifest["media_records"]
    for current, data in enumerate(records, 1):
        if cancel_requested and cancel_requested():
            manifest["export_state"] = "CANCELLED"
            break
        record = MediaRecord.from_dict(data); destination = output / record.planned_output_path
        try:
            if progress_callback:
                progress_callback("EXPORT", current, len(records), destination.name)
            if destination.exists() and _matches_expected(destination, record.size, record.sha256):
                record.export_status = "COPIED"
            elif destination.exists():
                raise SafetyConflictError(f"既有輸出檔案與預期內容不同：{destination}")
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(record.source_path, destination)
                record.export_status = "COPIED"
            
            # Preserve matched Sidecar JSON alongside the media file
            if record.json_path and record.json_status == "MATCHED":
                src_json = Path(record.json_path)
                if src_json.is_file():
                    # Destination sidecar uses destination media filename + original sidecar suffix
                    orig_name = Path(record.source_path).name
                    sidecar_name = src_json.name
                    if sidecar_name.startswith(orig_name):
                        dest_sidecar_name = destination.name + sidecar_name[len(orig_name):]
                    else:
                        dest_sidecar_name = destination.name + ".json"
                    dest_json = destination.parent / dest_sidecar_name
                    if dest_json.exists() and not _matches_expected(dest_json, src_json.stat().st_size, sha256(src_json)):
                        raise SafetyConflictError(f"既有中繼資料與預期內容不同：{dest_json}")
                    if not dest_json.exists():
                        shutil.copyfile(src_json, dest_json)
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
