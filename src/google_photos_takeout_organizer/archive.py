from __future__ import annotations
import zipfile
from pathlib import Path
from .models import Code

def extract_zip(source: Path, target: Path) -> list[str]:
    warnings: list[str] = []; target.mkdir(parents=True, exist_ok=True); root = target.resolve()
    try:
        with zipfile.ZipFile(source) as archive:
            for member in archive.infolist():
                destination = (target / member.filename).resolve()
                if destination != root and root not in destination.parents:
                    warnings.append(f"{Code.ZIP_PATH_TRAVERSAL}:{member.filename}"); continue
                if member.is_dir(): destination.mkdir(parents=True, exist_ok=True); continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as input_stream, destination.open("wb") as output_stream:
                    output_stream.write(input_stream.read())
    except zipfile.BadZipFile: warnings.append(str(Code.INVALID_ZIP))
    return warnings
