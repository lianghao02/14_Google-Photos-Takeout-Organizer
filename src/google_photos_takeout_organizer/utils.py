from __future__ import annotations
import errno, hashlib, os, re, subprocess
from pathlib import Path
from typing import Callable, TypeVar

T = TypeVar("T")

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
def heal_fuse_if_disconnected(exc: BaseException) -> bool:
    is_enotconn = (
        isinstance(exc, OSError)
        and (
            getattr(exc, "errno", None) == getattr(errno, "ENOTCONN", 107)
            or getattr(exc, "errno", None) == 107
            or "Transport endpoint is not connected" in str(exc)
        )
    )
    if is_enotconn:
        try:
            subprocess.run(["fusermount", "-uz", "/content/drive"], stderr=subprocess.DEVNULL, timeout=15)
            subprocess.run(["umount", "-l", "/content/drive"], stderr=subprocess.DEVNULL, timeout=15)
            from google.colab import drive  # type: ignore
            drive.mount("/content/drive", force_remount=True)
            return os.path.isdir("/content/drive/MyDrive")
        except Exception:
            return False
    return False
def run_with_fuse_retry(func: Callable[..., T], *args, retries: int = 2, **kwargs) -> T:
    for attempt in range(retries):
        try:
            return func(*args, **kwargs)
        except OSError as exc:
            if attempt < retries - 1 and heal_fuse_if_disconnected(exc):
                continue
            raise
def safe_stat(path: Path) -> os.stat_result | None:
    try:
        return path.stat()
    except (FileNotFoundError, NotADirectoryError):
        return None
