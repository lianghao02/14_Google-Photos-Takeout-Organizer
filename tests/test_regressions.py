import io
import time
import zipfile
from pathlib import Path, PurePosixPath

import pytest
from PIL import Image

from google_photos_takeout_organizer.exporter import export
from google_photos_takeout_organizer.matcher import match
from google_photos_takeout_organizer.models import MediaRecord
from google_photos_takeout_organizer.planner import plan
from google_photos_takeout_organizer.service import analyze
from google_photos_takeout_organizer.utils import sha256
from google_photos_takeout_organizer.verifier import verify


def test_cross_zip_pairs_export_without_collisions(tmp_path):
    sources = []
    for index in range(2):
        source = tmp_path / f"source{index}.zip"
        buffer = io.BytesIO()
        Image.new("RGB", (2, 2), (index * 100, 20, 30)).save(buffer, format="JPEG")
        with zipfile.ZipFile(source, "w") as archive:
            for name, data in (("IMG_0001.JPG", buffer.getvalue()), ("IMG_0001.MOV", bytes([index]) * 20)):
                info = zipfile.ZipInfo(f"Album/{name}", (2018, 2, 3, 12, 0, 0))
                archive.writestr(info, data)
        sources.append(source)
    before = [sha256(source) for source in sources]
    work = tmp_path / "work"
    manifest = analyze(sources, work)
    records = manifest["media_records"]
    paths = [r["planned_output_path"].casefold() for r in records]
    assert len(set(paths)) == 4
    assert manifest["summary"]["paired_groups"] == 2
    for archive_id in ("archive_001", "archive_002"):
        pair = [r for r in records if r["archive_id"] == archive_id]
        assert len({r["pair_group_id"] for r in pair}) == 1
        assert len({PurePosixPath(r["planned_output_path"]).stem for r in pair}) == 1
    output = tmp_path / "output"
    result = export(work / "manifest.json", output)
    assert result["export_state"] == "COMPLETED"
    assert verify(output / "manifest.json", output)["result"] == "PASS"
    assert [sha256(source) for source in sources] == before


def test_pair_reserves_companion_name_when_only_video_collides():
    def record(identity, folder, extension):
        return MediaRecord(identity, "a", f"/{folder}/IMG{extension}", f"{folder}/IMG{extension}",
                           f"IMG{extension}", extension, 1, "photo" if extension == ".JPG" else "video",
                           resolved_date="2018-02-03")
    standalone = record("standalone", "00", ".MOV")
    photo = record("photo", "Album", ".JPG")
    video = record("video", "Album", ".MOV")
    records = [standalone, photo, video]
    plan(records)
    paths = [r.planned_output_path.casefold() for r in records]
    assert len(set(paths)) == 3
    assert photo.output_filename == "IMG__2.JPG"
    assert video.output_filename == "IMG__2.MOV"
    plan(records)
    assert [r.planned_output_path.casefold() for r in records] == paths


@pytest.mark.parametrize("zip_date, expected", [((2018, 2, 3, 12, 34, 56), "2018-02"), ((2020, 12, 31, 12, 0, 0), "2020-12")])
def test_zip_date_fallback_preserves_original_month(tmp_path, zip_date, expected):
    source = tmp_path / "source.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(zipfile.ZipInfo("clip.mov", zip_date), b"synthetic video")
    before = sha256(source)
    manifest = analyze([source], tmp_path / "work")
    record = manifest["media_records"][0]
    assert record["date_source"] == "FILESYSTEM"
    assert record["date_confidence"] == "FALLBACK"
    assert record["resolved_date"].startswith(expected)
    assert sha256(source) == before


def test_invalid_zip_timestamp_does_not_use_extraction_time(tmp_path):
    source = tmp_path / "invalid.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(zipfile.ZipInfo("clip.mov", (2018, 0, 0, 0, 0, 0)), b"video")
    manifest = analyze([source], tmp_path / "work")
    record = manifest["media_records"][0]
    assert record["resolved_date"] is None
    assert record["date_source"] == "UNKNOWN"
    assert any("ZIP_INVALID_TIMESTAMP" in warning for warning in manifest["warnings"])


def test_safe_zip_resume_and_changed_zip_invalidation(tmp_path):
    zip_a = tmp_path / "batch_a.zip"
    zip_b = tmp_path / "batch_b.zip"
    with zipfile.ZipFile(zip_a, "w") as z:
        z.writestr("Album/a1.mov", b"video-a1")
        z.writestr("Album/a2.mov", b"video-a2")
    with zipfile.ZipFile(zip_b, "w") as z:
        z.writestr("Album/b1.mov", b"video-b1-different-size")

    work = tmp_path / "work"
    partial_dir = work / "extracted" / "archive_001" / "Album"
    partial_dir.mkdir(parents=True)
    # 模擬舊版無標記的中斷殘留目錄：不應跳過 zip_a 的 a2.mov
    (partial_dir / "stale.mov").write_bytes(b"stale")

    manifest_a = analyze([zip_a], work)
    names_a = sorted(r["original_filename"] for r in manifest_a["media_records"])
    assert names_a == ["a1.mov", "a2.mov"]
    assert (work / "extracted" / "archive_001" / ".gpto-extracted.ok").is_file()

    # 當輸入 ZIP 清單變更為 zip_b 時，archive_001 必須自動重建而非沿用 zip_a 的解壓結果
    manifest_b = analyze([zip_b], work)
    names_b = [r["original_filename"] for r in manifest_b["media_records"]]
    assert names_b == ["b1.mov"]


def test_fast_large_batch_sidecar_matching():
    class FastDummySidecar:
        def __init__(self, p: Path):
            self.p = p
            self.name = p.name
            self.stem = p.stem
            self.parent = p.parent
        def __str__(self): return str(self.p)
        def read_text(self, encoding="utf-8"):
            return '{"photoTakenTime": {"timestamp": "1600000000"}}'

    records = [
        MediaRecord(f"id_{i}", "a1", f"/vol/2026/IMG_{i:05d}.JPG", f"2026/IMG_{i:05d}.JPG", f"IMG_{i:05d}.JPG", ".jpg", 100, "photo")
        for i in range(2000)
    ]
    sidecars = [FastDummySidecar(Path(f"/vol/2026/IMG_{i:05d}.JPG.supplemental-metadata.json")) for i in range(2000)]
    start = time.perf_counter()
    used, warnings = match(records, sidecars, {"a1": Path("/vol")})
    elapsed = time.perf_counter() - start
    assert len(used) == 2000
    assert not warnings
    assert elapsed < 2.0
