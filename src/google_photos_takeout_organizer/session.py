"""Small, file-based state for an interrupted GUI workflow."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path


class WorkflowState(StrEnum):
    READY = "READY"
    RUNNING_ANALYZE = "RUNNING_ANALYZE"
    RUNNING_EXPORT = "RUNNING_EXPORT"
    RUNNING_VERIFY = "RUNNING_VERIFY"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    RESUME_AVAILABLE = "RESUME_AVAILABLE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SAFETY_CONFLICT = "SAFETY_CONFLICT"


def session_path(output_dir: Path) -> Path:
    return output_dir / ".gpto_work" / "session.json"


def source_fingerprints(sources: list[Path]) -> list[dict[str, object]]:
    return [
        {"path": str(path.resolve()), "size": path.stat().st_size, "mtime": path.stat().st_mtime_ns}
        for path in sources
    ]


def create_session(sources: list[Path], output_dir: Path) -> dict[str, object]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "session_version": 1, "status": WorkflowState.READY,
        "sources": source_fingerprints(sources), "output_dir": str(output_dir.resolve()),
        "current_stage": "ANALYZE", "analyze_completed": False,
        "export_completed": False, "verify_completed": False,
        "cancelled": False, "completed": False,
        "manifest_path": str((output_dir / ".gpto_work" / "manifest.json").resolve()),
        "created_at": now, "updated_at": now,
    }


def save_session(output_dir: Path, session: dict[str, object]) -> None:
    path = session_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")


def load_session(output_dir: Path) -> dict[str, object] | None:
    path = session_path(output_dir)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def is_incomplete_session(session: dict[str, object] | None) -> bool:
    return bool(session and not session.get("completed", False))


def sources_match(session: dict[str, object]) -> bool:
    try:
        for saved in session["sources"]:  # type: ignore[index]
            path = Path(str(saved["path"]))
            stat = path.stat()
            if stat.st_size != saved["size"] or stat.st_mtime_ns != saved["mtime"]:
                return False
    except (KeyError, OSError, TypeError):
        return False
    return True


def safe_temp_target(output_dir: Path) -> Path | None:
    output = output_dir.resolve()
    target = (output / ".gpto_work").resolve()
    return target if target.name == ".gpto_work" and target.parent == output else None
