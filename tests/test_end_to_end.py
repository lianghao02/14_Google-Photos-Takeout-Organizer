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
