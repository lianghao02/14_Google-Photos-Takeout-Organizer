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
