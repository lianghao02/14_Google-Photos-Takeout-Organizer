import io
import zipfile
from pathlib import PurePosixPath

import pytest
from PIL import Image

from google_photos_takeout_organizer.exporter import export
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
