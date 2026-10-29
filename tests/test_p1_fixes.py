import json
import shutil

from google_photos_takeout_organizer import exporter
from google_photos_takeout_organizer.date_resolver import resolve
from google_photos_takeout_organizer.matcher import match
from google_photos_takeout_organizer.models import MediaRecord
from google_photos_takeout_organizer.planner import plan
from google_photos_takeout_organizer.utils import sha256


def _record(**kw):
    base = dict(id="r", archive_id="a", source_path="/x/p.jpg", relative_path="p.jpg",
                original_filename="p.jpg", extension=".jpg", size=1, media_type="photo")
    base.update(kw)
    return MediaRecord(**base)


def _manifest(tmp_path, source, content):
    source.write_bytes(content)
    rec = _record(source_path=str(source), original_filename="a.jpg", relative_path="a.jpg",
                  size=len(content), sha256=sha256(source), planned_output_path="Photos_Archive/2020/01/a.jpg")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"media_records": [rec.to_dict()]}), encoding="utf-8")
    return path


def test_failed_copy_leaves_no_partial_file_and_can_retry(tmp_path, monkeypatch):
    manifest = _manifest(tmp_path, tmp_path / "src.jpg", b"payload-bytes")
    out = tmp_path / "out"
    real = shutil.copyfile

    def broken(src, dst, *a, **k):
        real(src, dst)
        with open(dst, "r+b") as f:
            f.truncate(3)
        raise OSError("disk full")

    monkeypatch.setattr(exporter.shutil, "copyfile", broken)
    result = exporter.export(manifest, out)
    assert result["media_records"][0]["export_status"] == "FAILED"
    assert not (out / "Photos_Archive/2020/01/a.jpg").exists()
    assert not list(out.rglob("*.gpto-part"))

    monkeypatch.setattr(exporter.shutil, "copyfile", real)
    result = exporter.export(manifest, out)
    assert result["media_records"][0]["export_status"] == "COPIED"
    assert (out / "Photos_Archive/2020/01/a.jpg").read_bytes() == b"payload-bytes"


def test_upload_time_only_goes_to_low_confidence_review(tmp_path):
    media = tmp_path / "p.jpg"; media.write_bytes(b"x")
    sidecar = tmp_path / "p.jpg.json"
    sidecar.write_text(json.dumps({"creationTime": {"timestamp": "1600000000"}}), encoding="utf-8")
    rec = _record(source_path=str(media))
    match([rec], [sidecar], {"a": tmp_path})
    resolve(rec)
    assert rec.date_source == "GOOGLE_JSON"
    assert "LOW_CONFIDENCE_DATE" in rec.warnings
    plan([rec])
    assert rec.planned_output_path.startswith("Review/Low-Confidence-Date/")


def test_taken_time_stays_in_archive(tmp_path):
    media = tmp_path / "p.jpg"; media.write_bytes(b"x")
    sidecar = tmp_path / "p.jpg.json"
    sidecar.write_text(json.dumps({"photoTakenTime": {"timestamp": "1600000000"}}), encoding="utf-8")
    rec = _record(source_path=str(media))
    match([rec], [sidecar], {"a": tmp_path})
    resolve(rec)
    assert "LOW_CONFIDENCE_DATE" not in rec.warnings
    plan([rec])
    assert rec.planned_output_path.startswith("Photos_Archive/2020/09/")
