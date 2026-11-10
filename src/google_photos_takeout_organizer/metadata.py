from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image

# 允許讀取全景與超高解析度照片，防止 DecompressionBombWarning
Image.MAX_IMAGE_PIXELS = None

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
                base_candidate = (
                    cleaned[:10].replace(":", "-") + "T" + cleaned[11:19]
                    if len(cleaned) >= 19
                    else str(raw).replace(":", "-", 2).replace(" ", "T")
                )
                candidates: list[str] = []
                if len(cleaned) >= 19 and offset and str(offset).strip():
                    off = str(offset).strip()
                    if off.startswith(("+", "-")) and len(off) in (5, 6):
                        candidates.append(base_candidate + off)
                candidates.append(base_candidate)
                for cand in candidates:
                    try:
                        parsed = datetime.fromisoformat(cand)
                        if parsed.year >= 1900:
                            exif_str = cand
                            break
                    except ValueError:
                        continue
            return image.width, image.height, exif_str, "FOUND" if exif_str else "NOT_FOUND"
    except Exception:
        return None, None, None, "CORRUPT_OR_UNSUPPORTED"

def json_date_is_upload(data: dict) -> bool:
    """JSON 沒有拍攝時間、只能用上傳時間 (creationTime) 時為 True。"""
    value = data.get("photoTakenTime")
    return not (isinstance(value, dict) and value.get("timestamp"))

def json_date(data: dict) -> str | None:
    for key in ("photoTakenTime", "creationTime"):
        value = data.get(key)
        if isinstance(value, dict) and value.get("timestamp"):
            try: return datetime.fromtimestamp(int(value["timestamp"]), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except (ValueError, OSError): pass
    return None
