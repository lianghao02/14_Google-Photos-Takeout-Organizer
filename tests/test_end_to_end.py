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

def test_gui_helpers_and_translations(tmp_path):
    from google_photos_takeout_organizer.gui import (
        translate_warning,
        validate_paths,
        format_file_size,
    )

    # 1. Warning translations
    assert translate_warning("DATE_CONFLICT") == "拍攝日期來源不一致，需要人工確認"
    assert translate_warning("MEDIA_WITHOUT_JSON") == "找不到對應的中繼資料"
    assert "未知" in translate_warning("UNKNOWN_CUSTOM_CODE") or "需要注意" in translate_warning("UNKNOWN_CUSTOM_CODE")

    # 2. File size formatting
    assert format_file_size(500) == "500 B"
    assert "KB" in format_file_size(2048)
    assert "MB" in format_file_size(5 * 1024 * 1024)
    assert "GB" in format_file_size(2 * 1024 * 1024 * 1024)

    # 3. Path validation
    assert "至少選取一個" in validate_paths([], tmp_path / "out")
    assert "指定輸出資料夾" in validate_paths([tmp_path / "a.zip"], None)

    # Output same as source
    src_dir = tmp_path / "takeout_dir"
    src_dir.mkdir()
    assert "不可位於來源資料夾內部" in validate_paths([src_dir], src_dir / "sub_out")

    # Valid scenario
    out_valid = tmp_path / "clean_output"
    assert validate_paths([tmp_path / "a.zip"], out_valid) is None

def test_gui_workflow_smoke(tmp_path):
    import time
    from PySide6.QtWidgets import QApplication, QMessageBox
    from google_photos_takeout_organizer.gui import MainWindow

    # 1. Create a minimal test ZIP
    zip_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        img_temp = tmp_path / "temp_sm.jpg"
        Image.new("RGB", (4, 4), (120, 150, 180)).save(img_temp)
        z.write(img_temp, "Google Photos/Photos from 2023/sample.jpg")
        z.writestr("Google Photos/Photos from 2023/sample.jpg.json", json.dumps({
            "photoTakenTime": {"timestamp": "1683700000"}
        }))

    out_dir = tmp_path / "gui_out"
    out_dir.mkdir()

    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.show()

    # Avoid modal blocking in automated test
    QMessageBox.information = lambda *args: None
    QMessageBox.warning = lambda *args: None
    QMessageBox.critical = lambda *args: None

    # Step 1: Add ZIP
    win.sources = [zip_path]
    win._update_source_status()
    assert "已選取 1 個 ZIP" in win.lbl_src_count.text()
    assert not win.widget_res_details.isVisible()
    assert win.lbl_res_placeholder.isVisible()

    # Step 2: Set output
    win.output_dir = out_dir
    win.txt_output.setText(str(out_dir))
    win._update_action_state()
    assert win.btn_start.isEnabled()

    # Step 3: Run pipeline
    win._start_task(analyze_only=False)
    assert win.worker is not None

    # Wait for completion
    timeout = 10
    start = time.time()
    while win.worker is not None and win.worker.isRunning() and (time.time() - start) < timeout:
        app.processEvents()
        time.sleep(0.05)
    app.processEvents()

    # Step 4: Verify UI state progression and results
    assert win.widget_res_details.isVisible()
    assert not win.lbl_res_placeholder.isVisible()
    assert "完整性驗證通過" in win.lbl_stats_verify.text()
    assert "照片 <b>1</b>" in win.lbl_stats_media.text()
    assert win.btn_open_out.isEnabled()

    # Step 5: Verify disk output exists
    exported_photo = out_dir / "Photos_Archive" / "2023" / "05" / "sample.jpg"
    assert exported_photo.exists()
    assert (out_dir / "verification.json").exists()
    assert (out_dir / "manifest.json").exists()
    assert (out_dir / "report.html").exists()
    assert (out_dir / ".gpto_work" / "session.json").exists(), "完成後應保留暫存資料供使用者自行決定是否清除"


def test_format_eta_and_progress_display():
    from google_photos_takeout_organizer.gui import format_eta_text, MainWindow
    from PySide6.QtWidgets import QApplication

    assert format_eta_text(15.2) == "< 1 分鐘"
    assert format_eta_text(59.4) == "< 1 分鐘"
    assert format_eta_text(60.0) == "1 分 00 秒"
    assert format_eta_text(125.0) == "2 分 05 秒"
    assert format_eta_text(350.0) == "5 分鐘"
    assert format_eta_text(3720.0) == "1 小時 2 分"

    app = QApplication.instance() or QApplication([])
    win = MainWindow()

    # 剛開始（未滿 3 秒或未滿 3 筆）：進度統計顯示「預估時間計算中…」
    win._on_progress("EXPORT", 1, 100, "test1.jpg")
    assert "正在整理照片與影片 · 1%" in win.lbl_stage.text()
    assert "1 / 100" in win.lbl_prog_stats.text()
    assert "計算中" in win.lbl_prog_stats.text()

    # 模擬經過時間與筆數
    win._stage_start_time -= 10.0
    win._stage_start_current = 0
    win._last_progress_time = win._stage_start_time
    win._last_progress_current = 0
    win._on_progress("EXPORT", 50, 100, "test50.jpg")
    assert "正在整理照片與影片 · 50%" in win.lbl_stage.text()
    assert "50 / 100" in win.lbl_prog_stats.text()
    assert "剩餘約" in win.lbl_prog_stats.text()

    # 完成時 (current == total)
    win._on_progress("EXPORT", 100, 100, "test100.jpg")
    assert win.lbl_stage.text() == "正在整理照片與影片 · 100%"
    assert win.lbl_prog_stats.text() == "100 / 100"


def test_gui_ux_convergence(tmp_path):
    from google_photos_takeout_organizer.gui import MainWindow
    from PySide6.QtWidgets import QApplication, QMessageBox

    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.show()

    # Avoid modal blocking in automated test
    QMessageBox.information = lambda *args: None
    QMessageBox.warning = lambda *args: None
    QMessageBox.critical = lambda *args: None

    # 1. 初始狀態驗證
    assert win.lbl_empty_hint.isVisible()
    assert "將 Google Takeout ZIP 拖曳至此" in win.lbl_empty_hint.text()
    assert not win.btn_start.isEnabled()
    assert win.btn_start.toolTip() == "請先加入 Takeout ZIP。"
    assert not win.btn_cancel.isVisible()

    # 2. 加入來源 ZIP
    dummy_zip = tmp_path / "takeout-001.zip"
    dummy_zip.write_bytes(b"PK\x05\x06" + b"\x00" * 18)
    win.sources = [dummy_zip]
    win._update_source_status()
    assert not win.lbl_empty_hint.isVisible()
    win._update_action_state()
    assert not win.btn_start.isEnabled()
    assert win.btn_start.toolTip() == "請先選擇輸出位置。"

    # 3. 指定輸出位置
    out_dir = tmp_path / "organizer_out"
    out_dir.mkdir()
    win.output_dir = out_dir
    win.txt_output.setText(str(out_dir))
    win._update_action_state()

    assert win.btn_start.isEnabled()
    assert win.btn_start.toolTip() == "開始整理照片與影片"
    assert win.lbl_disk_info.isVisible()
    assert "空間充足" in win.lbl_disk_info.text()

    # 4. 檔名 Middle-Elide 驗證
    long_filename = "very_long_path_to_some_camera_photo_taken_in_2023_05_10_numbered_999999999999.jpg"
    win._on_progress("EXPORT", 10, 100, long_filename)
    assert win.lbl_current_file.toolTip() == long_filename
    assert "…" in win.lbl_current_file.text() or "..." in win.lbl_current_file.text() or "目前：" in win.lbl_current_file.text()

    # 5. 完成結果狀態分流驗證 (無人工確認項目)
    win._on_finished_success({
        "manifest": {"summary": {"photos": 5, "videos": 2, "json_matched": 7}, "media_records": []},
        "verification": {"result": "PASS", "verified": 7, "failed": 0},
        "work_dir": str(tmp_path),
    })
    assert win.widget_res_details.isVisible()
    assert "無待確認項目" in win.lbl_stats_verify.text()
    assert not win.btn_open_review.isVisible()

    # 6. 重設下一批
    win._reset_next_batch()
    assert win.lbl_empty_hint.isVisible()
    assert win.lbl_stage.text() == "就緒"
    assert win.lbl_prog_stats.text() == ""
    assert win.lbl_current_file.text() == ""




