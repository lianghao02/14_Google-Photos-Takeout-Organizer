from __future__ import annotations

import zipfile
from collections.abc import Callable
from pathlib import Path

from .models import Code


COPY_CHUNK_SIZE = 4 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1000.0


def decode_member_name(member: zipfile.ZipInfo) -> str:
    """修復未設定 Bit 11 (0x800) 的 CP437/Big5 解碼 Takeout ZIP 檔名"""
    filename = member.filename
    if not (member.flag_bits & 0x800):
        for encoding in ("utf-8", "big5", "cp950"):
            try:
                raw_bytes = filename.encode("cp437")
                return raw_bytes.decode(encoding)
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
    return filename


def extract_zip(
    source: Path,
    target: Path,
    cancel_requested: Callable[[], bool] | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> list[str]:
    warnings: list[str] = []
    target.mkdir(parents=True, exist_ok=True)
    root = target.resolve()
    try:
        with zipfile.ZipFile(source) as archive:
            members = archive.infolist()
            total_members = len(members)
            for idx, member in enumerate(members, 1):
                if cancel_requested and cancel_requested():
                    raise InterruptedError("CANCELLED")

                # 1. 拒絕符號連結 (Symlinks)
                mode = (member.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    continue

                # 2. 檢查潛在 Zip Bomb 攻擊
                if member.file_size > 0 and member.compress_size > 0:
                    if (member.file_size / float(member.compress_size)) > MAX_COMPRESSION_RATIO:
                        warnings.append(f"{Code.ZIP_BOMB}:{member.filename}")
                        continue

                # 3. 檔名編碼修復 (CP437/Big5 轉 UTF-8)
                decoded_name = decode_member_name(member)
                if progress_callback:
                    progress_callback(idx, total_members, decoded_name)
                destination = (target / decoded_name).resolve()

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
