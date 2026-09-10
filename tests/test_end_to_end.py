import json, zipfile
from pathlib import Path
from PIL import Image
from google_photos_takeout_organizer.service import analyze
from google_photos_takeout_organizer.exporter import export
from google_photos_takeout_organizer.verifier import verify
from google_photos_takeout_organizer.utils import sha256, sanitize_filename

def image(path: Path, color=(20, 40, 60)):
    path.parent.mkdir(parents=True, exist_ok=True); Image.new("RGB", (10, 10), color).save(path)
def sidecar(path: Path, timestamp="1527897600"):
    path.write_text(json.dumps({"photoTakenTime":{"timestamp":timestamp}, "albums":["家庭", "日本旅行"]}), encoding="utf-8")

def test_folder_analyze_export_verify_and_source_immutable(tmp_path):
    source = tmp_path / "takeout"; first = source / "Album" / "IMG_001.jpg"; image(first); sidecar(first.with_name("IMG_001.jpg.json"))
    duplicate = source / "Other" / "copy.jpg"; duplicate.parent.mkdir(parents=True); duplicate.write_bytes(first.read_bytes())
    image(source / "Album" / "IMG_001__edited.jpg", (1,2,3)); (source / "bad.txt").write_text("not media")
    before = {str(p): sha256(p) for p in source.rglob("*") if p.is_file()}; manifest = analyze([source], tmp_path / "work")
    assert manifest["summary"]["duplicate_groups"] == 1
    assert any(r["planned_output_path"].startswith("Photos_Archive/2018/06") for r in manifest["media_records"])
    assert (tmp_path / "work" / "report.html").exists(); assert before == {str(p): sha256(p) for p in source.rglob("*") if p.is_file()}
    out = tmp_path / "output"; export(tmp_path / "work" / "manifest.json", out); assert verify(out / "manifest.json", out)["result"] == "PASS"
    assert before == {str(p): sha256(p) for p in source.rglob("*") if p.is_file()}
    export(out / "manifest.json", out); assert verify(out / "manifest.json", out)["result"] == "PASS"

def test_multiple_zips_cross_archive_and_zip_slip(tmp_path):
    a, b = tmp_path / "a.zip", tmp_path / "b.zip"
    with zipfile.ZipFile(a, "w") as z: z.writestr("Google Photos/X.jpg", b"same synthetic bytes")
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("X.jpg.json", json.dumps({"photoTakenTime":{"timestamp":"1527897600"}})); z.writestr("../escape.jpg", b"bad")
    manifest = analyze([a,b], tmp_path / "work")
    record = manifest["media_records"][0]
    assert record["json_status"] == "MATCHED" and record["resolved_date"].startswith("2018-06")
    assert any("ZIP_PATH_TRAVERSAL" in x for x in manifest["warnings"]); assert not (tmp_path / "escape.jpg").exists()

def test_windows_name_safety():
    assert sanitize_filename('CON.jpg').startswith('_CON'); assert sanitize_filename('a<b>.jpg') == 'a_b_.jpg'

def test_sidecar_matcher_patterns():
    from google_photos_takeout_organizer.models import MediaRecord
    from google_photos_takeout_organizer.matcher import match

    r1 = MediaRecord("1", "a1", "/p/IMG_1234.jpg", "Takeout/IMG_1234.jpg", "IMG_1234.jpg", ".jpg", 100, "photo")
    j1 = Path("/p/IMG_1234.jpg.supplemental-metadata.json")
    r2 = MediaRecord("2", "a1", "/p/IMG_5678.jpg", "Takeout/IMG_5678.jpg", "IMG_5678.jpg", ".jpg", 100, "photo")
    j2 = Path("/p/IMG_5678.jpg.json")
    r3 = MediaRecord("3", "a1", "/p/IMG_9999.jpg", "Takeout/IMG_9999.jpg", "IMG_9999.jpg", ".jpg", 100, "photo")
    j3 = Path("/p/IMG_9999.json")
    r4 = MediaRecord("4", "a1", "/p/DSCF0787(1).AVI", "Takeout/DSCF0787(1).AVI", "DSCF0787(1).AVI", ".avi", 100, "video")
    j4 = Path("/p/DSCF0787.AVI.supplemental-metadata(1).json")

    class DummyPath:
        def __init__(self, p: Path):
            self.p, self.name, self.stem, self.parent = p, p.name, p.stem, p.parent
        def __str__(self): return str(self.p)
        def __repr__(self): return repr(self.p)
        def read_text(self, encoding="utf-8"):
            return json.dumps({"photoTakenTime": {"timestamp": "1527897600"}})

    d1, d2, d3, d4 = DummyPath(j1), DummyPath(j2), DummyPath(j3), DummyPath(j4)
    used, warnings = match([r1, r2, r3, r4], [d1, d2, d3, d4])
    assert r1.json_status == "MATCHED" and r1.json_date.startswith("2018-06")
    assert r2.json_status == "MATCHED" and r2.json_date.startswith("2018-06")
    assert r3.json_status == "MATCHED" and r3.json_date.startswith("2018-06")
    assert r4.json_status == "MATCHED" and r4.json_date.startswith("2018-06")
    assert len(used) == 4 and len(warnings) == 0

def test_sidecar_matcher_strictness_no_false_matches():
    from google_photos_takeout_organizer.models import MediaRecord
    from google_photos_takeout_organizer.matcher import match

    r1 = MediaRecord("1", "a1", "/p/56.JPG", "Takeout/56.JPG", "56.JPG", ".jpg", 100, "photo")
    j_wrong = Path("/p/256.JPG.supplemental-metadata.json")
    used, warnings = match([r1], [j_wrong])
    assert r1.json_status == "MEDIA_WITHOUT_JSON"
    assert any("JSON_ORPHAN" in w for w in warnings)

    r2 = MediaRecord("2", "a1", "/p/IMG_01.jpg", "Takeout/IMG_01.jpg", "IMG_01.jpg", ".jpg", 100, "photo")
    j_cand1 = Path("/p/IMG_01.jpg.json")
    j_cand2 = Path("/p/IMG_01.jpg.supplemental-metadata.json")
    used2, warnings2 = match([r2], [j_cand1, j_cand2])
    assert r2.json_status == "AMBIGUOUS_SIDECAR"

def test_multi_archive_pooling_and_no_silent_overwrite(tmp_path):
    za, zb = tmp_path / "takeout_a.zip", tmp_path / "takeout_b.zip"
    with zipfile.ZipFile(za, "w") as z:
        img_path = tmp_path / "temp_img.jpg"
        Image.new("RGB", (2, 2), (100, 100, 100)).save(img_path)
        z.write(img_path, "Takeout/Album2020/photo.jpg")
    with zipfile.ZipFile(zb, "w") as z:
        z.writestr("Takeout/Album2020/photo.jpg.supplemental-metadata.json", json.dumps({
            "photoTakenTime": {"timestamp": "1593561600"}
        }))
    manifest = analyze([za, zb], tmp_path / "work_multi")
    record = manifest["media_records"][0]
    assert record["json_status"] == "MATCHED" and record["resolved_date"].startswith("2020-07-01")
    assert manifest["summary"]["no_json"] == 0
    assert not any("JSON_ORPHAN" in w for w in manifest["warnings"])

def test_heic_metadata_fallback(tmp_path):
    from google_photos_takeout_organizer.metadata import image_metadata
    fake_heic = tmp_path / "test.heic"
    fake_heic.write_bytes(b"not a real heic file")
    w, h, dt, status = image_metadata(fake_heic)
    assert status == "CORRUPT_OR_UNSUPPORTED" and dt is None

def test_exif_ifd_datetimeoriginal_and_timezone_matching():
    from google_photos_takeout_organizer.models import MediaRecord
    from google_photos_takeout_organizer.date_resolver import resolve
    from google_photos_takeout_organizer.planner import plan

    # 1. UTC JSON vs Local EXIF with +8h offset
    r1 = MediaRecord("1", "a1", "p1", "p1", "IMG_2073.JPG", ".jpg", 100, "photo",
                     json_date="2018-03-31T23:19:29Z", exif_date="2018-04-01T07:19:29")
    resolve(r1)
    assert "DATE_CONFLICT" not in r1.warnings
    assert r1.resolved_date == "2018-04-01T07:19:29"
    assert r1.date_confidence == "HIGH"
    plan([r1])
    assert r1.planned_output_path == "Photos_Archive/2018/04/IMG_2073.JPG"

    # 2. Genuine DATE_CONFLICT -> goes to Review/Date-Conflict
    r2 = MediaRecord("2", "a1", "p2", "p2", "conflict.jpg", ".jpg", 100, "photo",
                     json_date="2020-01-01T10:00:00Z", exif_date="2020-01-02T09:00:00")
    resolve(r2)
    assert "DATE_CONFLICT" in r2.warnings
    assert r2.resolved_date is None
    plan([r2])
    assert r2.planned_output_path == "Review/Date-Conflict/conflict.jpg"

    # 3. Truly unknown date -> goes to Unknown-Date
    r3 = MediaRecord("3", "a1", "p3", "p3", "no_date.jpg", ".jpg", 100, "photo")
    resolve(r3)
    assert "NO_DATE" in r3.warnings
    assert r3.resolved_date is None
    plan([r3])
    assert r3.planned_output_path == "Unknown-Date/no_date.jpg"

def test_sidecar_exported_alongside_media(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    media_file = source / "photo.jpg"
    media_file.write_bytes(b"image data here")
    sidecar_file = source / "photo.jpg.supplemental-metadata.json"
    sidecar_file.write_text('{"description": "family vacation"}', encoding="utf-8")

    from google_photos_takeout_organizer.models import MediaRecord
    from google_photos_takeout_organizer.planner import plan
    from google_photos_takeout_organizer.exporter import export
    from google_photos_takeout_organizer.utils import sha256

    record = MediaRecord(
        id="rec1", archive_id="a1", source_path=str(media_file), relative_path="photo.jpg",
        original_filename="photo.jpg", extension=".jpg", size=len(media_file.read_bytes()),
        media_type="photo", sha256=sha256(media_file), json_path=str(sidecar_file),
        json_status="MATCHED", resolved_date="2021-05-10"
    )
    plan([record])
    manifest_data = {
        "media_records": [record.to_dict()],
        "duplicate_groups": [],
        "summary": {}
    }
    m_path = tmp_path / "manifest.json"
    m_path.write_text(json.dumps(manifest_data), encoding="utf-8")

    out = tmp_path / "out"
    export(m_path, out)

    exported_media = out / "Photos_Archive" / "2021" / "05" / "photo.jpg"
    exported_sidecar = out / "Photos_Archive" / "2021" / "05" / "photo.jpg.supplemental-metadata.json"
    assert exported_media.exists()
    assert exported_sidecar.exists()
    assert json.loads(exported_sidecar.read_text(encoding="utf-8"))["description"] == "family vacation"

