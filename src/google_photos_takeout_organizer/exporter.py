from __future__ import annotations
import json, shutil
from pathlib import Path
from .models import MediaRecord
from .utils import sha256

def export(manifest_path: Path, output: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")); output.mkdir(parents=True, exist_ok=True)
    for data in manifest["media_records"]:
        record = MediaRecord.from_dict(data); destination = output / record.planned_output_path
        try:
            if destination.exists() and destination.stat().st_size == record.size and sha256(destination) == record.sha256: record.export_status = "COPIED"
            else:
                destination.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(record.source_path, destination); record.export_status = "COPIED"
        except OSError: record.export_status = "FAILED"; record.errors.append("COPY_FAILED")
        data.update(record.to_dict())
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
