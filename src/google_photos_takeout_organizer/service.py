from __future__ import annotations
import json, logging, uuid
from pathlib import Path
from typing import Callable
from . import __version__
from .archive import extract_zip
from .scanner import scan
from .matcher import match
from .metadata import image_metadata
from .date_resolver import resolve
from .dedupe import group
from .planner import plan
from .report import write_report

log = logging.getLogger(__name__)
def analyze(
    inputs: list[Path],
    work: Path,
    cancel_requested: Callable[[], bool] | None = None,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
) -> dict:
    work.mkdir(parents=True, exist_ok=True); extracted = work / "extracted"; records = []; jsons = []; archives = []; warnings = []
    for index, source in enumerate(inputs, 1):
        if cancel_requested and cancel_requested():
            raise InterruptedError("CANCELLED")
        archive_id = f"archive_{index:03d}"; root = source
        if source.suffix.lower() == ".zip":
            root = extracted / archive_id
            ext_cb = (
                (lambda cur, tot, name, s_name=source.name: progress_callback("ANALYZE_EXTRACT", cur, tot, f"[{s_name}] {name}"))
                if progress_callback
                else None
            )
            warnings.extend(extract_zip(source, root, cancel_requested=cancel_requested, progress_callback=ext_cb))
        archives.append({"archive_id": archive_id, "source": str(source), "root": str(root)})
        found, sidecars = scan(root, archive_id); records.extend(found); jsons.extend(sidecars)
    roots = {a["archive_id"]: Path(a["root"]) for a in archives}
    _, match_warnings = match(records, jsons, roots); warnings.extend(match_warnings)
    total_recs = len(records)
    for idx, record in enumerate(records, 1):
        if cancel_requested and cancel_requested():
            raise InterruptedError("CANCELLED")
        if progress_callback:
            progress_callback("ANALYZE", idx, total_recs, record.original_filename)
        if record.media_type == "photo":
            record.width, record.height, record.exif_date, record.exif_status = image_metadata(Path(record.source_path))
        resolve(record)
    groups = group(records); plan(records)
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
