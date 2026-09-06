from __future__ import annotations
import hashlib, re
from pathlib import Path

WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()
def sanitize_filename(name: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).rstrip(". ") or "unnamed"
    stem, dot, suffix = value.partition(".")
    if stem.upper() in WINDOWS_RESERVED: stem = "_" + stem
    return stem + (dot + suffix if dot else "")
def dated_from_name(name: str) -> str | None:
    found = re.search(r"(?<!\d)((?:19|20)\d{2})[-_]?([01]\d)[-_]?([0-3]\d)(?!\d)", name)
    return "-".join(found.groups()) if found else None
def dated_from_folder(relative: str) -> str | None:
    found = re.search(r"(?<!\d)((?:19|20)\d{2})(?:[-_/]([01]\d))?", relative)
    return "-".join(x for x in found.groups() if x) if found else None
