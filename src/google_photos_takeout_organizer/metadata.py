from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pass

def image_metadata(path: Path) -> tuple[int | None, int | None, str | None, str]:
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            raw = (exif.get(36867) or exif.get(306)) if exif else None
            return image.width, image.height, (str(raw).replace(":", "-", 2).replace(" ", "T") if raw else None), "FOUND" if raw else "NOT_FOUND"
    except Exception: return None, None, None, "CORRUPT_OR_UNSUPPORTED"
def json_date(data: dict) -> str | None:
    for key in ("photoTakenTime", "creationTime"):
        value = data.get(key)
        if isinstance(value, dict) and value.get("timestamp"):
            try: return datetime.fromtimestamp(int(value["timestamp"]), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except (ValueError, OSError): pass
    return None
