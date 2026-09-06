from __future__ import annotations
import uuid
from pathlib import Path
from .models import MediaRecord, Code
from .utils import dated_from_folder, dated_from_name

IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"}; VIDEOS = {".mp4", ".mov", ".m4v", ".avi"}
def scan(root: Path, archive_id: str) -> tuple[list[MediaRecord], list[Path]]:
    media: list[MediaRecord] = []; sidecars: list[Path] = []
    for item in sorted(root.rglob("*")):
        if not item.is_file(): continue
        relative = item.relative_to(root).as_posix(); suffix = item.suffix.lower()
        if suffix == ".json": sidecars.append(item); continue
        kind = "photo" if suffix in IMAGES else "video" if suffix in VIDEOS else "unsupported"
        record = MediaRecord(str(uuid.uuid5(uuid.NAMESPACE_URL, f"{archive_id}/{relative}")), archive_id, str(item), relative, item.name, suffix, item.stat().st_size, kind)
        record.filename_date = dated_from_name(item.name); record.folder_date = dated_from_folder(relative)
        if kind == "unsupported": record.warnings.append(str(Code.UNSUPPORTED_FORMAT))
        media.append(record)
    return media, sidecars
