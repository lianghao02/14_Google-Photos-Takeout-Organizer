from __future__ import annotations
import json
from pathlib import Path
from typing import Callable
from .models import MediaRecord
from .utils import sha256

def verify(manifest_path: Path, output: Path, progress_callback: Callable[[str, int, int, str], None] | None = None, cancel_requested: Callable[[], bool] | None = None) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")); failed = 0; verified = 0
    records = manifest["media_records"]
    for current, data in enumerate(records, 1):
        if cancel_requested and cancel_requested():
            return {"result": "CANCELLED", "verified": verified, "failed": failed}
        record = MediaRecord.from_dict(data); target = output / record.planned_output_path
        if progress_callback:
            progress_callback("VERIFY", current, len(records), target.name)
        if target.exists() and target.stat().st_size == record.size and sha256(target) == record.sha256: record.export_status = "VERIFIED"; verified += 1
        else: record.export_status = "FAILED"; record.errors.append("HASH_MISMATCH"); failed += 1
        data.update(record.to_dict())
    result = {"result": "PASS" if not failed else "FAIL", "verified": verified, "failed": failed}
    manifest["verification"] = result; (output / "verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8"); (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
