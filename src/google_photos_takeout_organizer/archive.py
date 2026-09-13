from __future__ import annotations

import zipfile
from collections.abc import Callable
from pathlib import Path

from .models import Code


COPY_CHUNK_SIZE = 4 * 1024 * 1024


def extract_zip(
    source: Path,
    target: Path,
    cancel_requested: Callable[[], bool] | None = None,
) -> list[str]:
    warnings: list[str] = []
    target.mkdir(parents=True, exist_ok=True)
    root = target.resolve()
    try:
        with zipfile.ZipFile(source) as archive:
            for member in archive.infolist():
                if cancel_requested and cancel_requested():
                    raise InterruptedError("CANCELLED")

                destination = (target / member.filename).resolve()
                if destination != root and root not in destination.parents:
                    warnings.append(f"{Code.ZIP_PATH_TRAVERSAL}:{member.filename}")
                    continue
                if member.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue

                destination.parent.mkdir(parents=True, exist_ok=True)
                partial_destination = destination.with_name(f".{destination.name}.gpto-part")
                try:
                    with archive.open(member) as input_stream, partial_destination.open("wb") as output_stream:
                        while chunk := input_stream.read(COPY_CHUNK_SIZE):
                            if cancel_requested and cancel_requested():
                                raise InterruptedError("CANCELLED")
                            output_stream.write(chunk)
                    partial_destination.replace(destination)
                except InterruptedError:
                    partial_destination.unlink(missing_ok=True)
                    raise
    except zipfile.BadZipFile:
        warnings.append(str(Code.INVALID_ZIP))
    return warnings
