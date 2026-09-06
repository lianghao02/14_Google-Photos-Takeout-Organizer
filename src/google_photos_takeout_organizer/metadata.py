from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image

def image_metadata(path: Path) -> tuple[int | None, int | None, str | None, str]:
    try:
        with Image.open(path) as image:
            raw = image.getexif().get(36867) or image.getexif().get(306)
            return image.width, image.height, (str(raw).replace(":", "-", 2).replace(" ", "T") if raw else None), "FOUND" if raw else "NOT_FOUND"
    except Exception: return None, None, None, "CORRUPT_OR_UNSUPPORTED"
def json_date(data: dict) -> str | None:
    for key in ("photoTakenTime", "creationTime"):
        value = data.get(key)
        if isinstance(value, dict) and value.get("timestamp"):
            try: return datetime.fromtimestamp(int(value["timestamp"]), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except (ValueError, OSError): pass
    return None
