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
            raw = None
            offset = None
            if exif:
                # 1. Try Exif IFD
                try:
                    from PIL import ExifTags
                    ifd = exif.get_ifd(ExifTags.IFD.Exif)
                    raw = ifd.get(36867) or ifd.get(36868)
                    offset = ifd.get(36881) or ifd.get(36882) or ifd.get(36880)
                except Exception:
                    pass
                # 2. Try _getexif() fallback if raw not found
                if not raw and hasattr(image, "_getexif"):
                    try:
                        raw_dict = image._getexif() or {}
                        raw = raw_dict.get(36867) or raw_dict.get(36868)
                        offset = offset or raw_dict.get(36881) or raw_dict.get(36882) or raw_dict.get(36880)
                    except Exception:
                        pass
                # 3. Fallback to 0th IFD DateTime (tag 306) if still not found
                if not raw:
                    raw = exif.get(306)
            
            exif_str = None
            if raw:
                cleaned = str(raw).strip()
                if len(cleaned) >= 19:
                    exif_str = cleaned[:10].replace(":", "-") + "T" + cleaned[11:19]
                    if offset and str(offset).strip():
                        off = str(offset).strip()
                        if off.startswith(("+", "-")) and len(off) in (5, 6):
                            exif_str += off
                else:
                    exif_str = str(raw).replace(":", "-", 2).replace(" ", "T")
            return image.width, image.height, exif_str, "FOUND" if exif_str else "NOT_FOUND"
    except Exception:
        return None, None, None, "CORRUPT_OR_UNSUPPORTED"

def json_date(data: dict) -> str | None:
    for key in ("photoTakenTime", "creationTime"):
        value = data.get(key)
        if isinstance(value, dict) and value.get("timestamp"):
            try: return datetime.fromtimestamp(int(value["timestamp"]), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except (ValueError, OSError): pass
    return None
