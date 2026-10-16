import io
import json
import zipfile
from pathlib import Path
from PIL import Image

from google_photos_takeout_organizer.models import MediaRecord, Code
from google_photos_takeout_organizer.archive import extract_zip, decode_member_name
from google_photos_takeout_organizer.scanner import scan
from google_photos_takeout_organizer.matcher import match
from google_photos_takeout_organizer.date_resolver import resolve
from google_photos_takeout_organizer.planner import plan, identify_pairs


def test_live_photo_pairing_and_path_sync():
    """驗證 iPhone Live Photo (HEIC + MOV) 成對綁定、日期繼承與檔名同步更名。"""
    photo = MediaRecord(
        id="rec_photo_01",
        archive_id="a1",
        source_path="/takeout/2021/IMG_0099.HEIC",
        relative_path="2021/IMG_0099.HEIC",
        original_filename="IMG_0099.HEIC",
        extension=".heic",
        size=2_000_000,
        media_type="photo",
        json_date="2021-08-20T14:30:00Z",
    )
    resolve(photo)
    assert photo.resolved_date == "2021-08-20T14:30:00Z"

    # 短影片原本沒有任何中繼資料
    video = MediaRecord(
        id="rec_video_01",
        archive_id="a1",
        source_path="/takeout/2021/IMG_0099.MOV",
        relative_path="2021/IMG_0099.MOV",
        original_filename="IMG_0099.MOV",
        extension=".mov",
        size=15_000_000,
        media_type="video",
    )
    # 執行識別成對
    child_to_primary = identify_pairs([photo, video])
    assert video.id in child_to_primary
    assert video.pair_role == "LIVE_PHOTO_VIDEO"
    assert photo.pair_role == "PRIMARY_PHOTO"
    # 短影片應成功繼承照片日期
    assert video.resolved_date == "2021-08-20T14:30:00Z"

    # 執行路徑規劃
    plan([photo, video])
    assert photo.planned_output_path == "Photos_Archive/2021/08/IMG_0099.HEIC"
    assert video.planned_output_path == "Photos_Archive/2021/08/IMG_0099.MOV"


def test_live_photo_collision_synchronized_renaming():
    """驗證當 Live Photo 遭遇同名衝突時，主照與短影片能同步重命名 (例如 __2.HEIC 與 __2.MOV)。"""
    # 既有檔案先佔用 IMG_0099.HEIC
    existing = MediaRecord(
        id="existing_photo",
        archive_id="a0",
        source_path="/other/IMG_0099.HEIC",
        relative_path="00_album/IMG_0099.HEIC",
        original_filename="IMG_0099.HEIC",
        extension=".heic",
        size=1_000_000,
        media_type="photo",
        resolved_date="2021-08-20T10:00:00Z",
    )
    photo = MediaRecord(
        id="rec_photo_02",
        archive_id="a1",
        source_path="/takeout/2021/IMG_0099.HEIC",
        relative_path="2021/IMG_0099.HEIC",
        original_filename="IMG_0099.HEIC",
        extension=".heic",
        size=2_000_000,
        media_type="photo",
        resolved_date="2021-08-20T14:30:00Z",
    )
    video = MediaRecord(
        id="rec_video_02",
        archive_id="a1",
        source_path="/takeout/2021/IMG_0099.MOV",
        relative_path="2021/IMG_0099.MOV",
        original_filename="IMG_0099.MOV",
        extension=".mov",
        size=15_000_000,
        media_type="video",
    )

    plan([existing, photo, video])
    assert existing.planned_output_path == "Photos_Archive/2021/08/IMG_0099.HEIC"
    # 第二組應同步被更名為 __2
    assert photo.planned_output_path == "Photos_Archive/2021/08/IMG_0099__2.HEIC"
    assert video.planned_output_path == "Photos_Archive/2021/08/IMG_0099__2.MOV"


def test_raw_jpeg_pair_binding():
    """驗證單眼相機 RAW + JPEG 檔名與目錄成對綁定。"""
    jpg = MediaRecord(
        id="rec_jpg",
        archive_id="a1",
        source_path="/takeout/RAW_TEST/DSC_0001.JPG",
        relative_path="RAW_TEST/DSC_0001.JPG",
        original_filename="DSC_0001.JPG",
        extension=".jpg",
        size=5_000_000,
        media_type="photo",
        resolved_date="2022-11-05T09:00:00Z",
    )
    raw = MediaRecord(
        id="rec_raw",
        archive_id="a1",
        source_path="/takeout/RAW_TEST/DSC_0001.ARW",
        relative_path="RAW_TEST/DSC_0001.ARW",
        original_filename="DSC_0001.ARW",
        extension=".arw",
        size=25_000_000,
        media_type="photo",
    )
    plan([jpg, raw])
    assert raw.pair_role == "RAW_PAIR"
    assert raw.planned_output_path == "Photos_Archive/2022/11/DSC_0001.ARW"
    assert jpg.planned_output_path == "Photos_Archive/2022/11/DSC_0001.JPG"


def test_phase_by_phase_sidecar_matcher_cross_zip_no_steal():
    """驗證全域階段式配對：同目錄同名 JSON (Phase 1) 絕不被跨卷候補 (Phase 2/3) 搶走。"""
    # 卷 1 的照片
    r1 = MediaRecord("r1", "zip1", "/z1/AlbumA/pic.jpg", "AlbumA/pic.jpg", "pic.jpg", ".jpg", 100, "photo")
    # 卷 2 的同名照片
    r2 = MediaRecord("r2", "zip2", "/z2/AlbumB/pic.jpg", "AlbumB/pic.jpg", "pic.jpg", ".jpg", 100, "photo")

    # 只有一個 JSON，位於卷 1 的 AlbumA
    j1 = Path("/z1/AlbumA/pic.jpg.json")

    class DummySidecar:
        def __init__(self, p: Path):
            self.p = p
            self.name = p.name
            self.stem = p.stem
            self.parent = p.parent
        def __str__(self): return str(self.p)
        def __repr__(self): return repr(self.p)
        def read_text(self, encoding="utf-8"):
            return json.dumps({"photoTakenTime": {"timestamp": "1600000000"}})

    d1 = DummySidecar(j1)
    roots = {"zip1": Path("/z1"), "zip2": Path("/z2")}

    used, warnings = match([r1, r2], [d1], roots)
    # r1 在 Phase 1 同目錄精確配對成功
    assert r1.json_status == "MATCHED"
    assert r1.json_path == str(j1)
    # r2 未能跨卷搶佔已用 JSON
    assert r2.json_status == "MEDIA_WITHOUT_JSON"
    assert len(used) == 1


def test_filesystem_date_fallback_zero_unknown():
    """驗證五層日期保底階梯：無 EXIF、無 JSON 時由檔案修改時間 (mtime) 兜底。"""
    record = MediaRecord(
        id="rec_nodata",
        archive_id="a1",
        source_path="/tmp/unknown_img.png",
        relative_path="unknown_img.png",
        original_filename="unknown_img.png",
        extension=".png",
        size=500,
        media_type="photo",
        filesystem_date="2020-03-15T08:20:00Z",
    )
    resolve(record)
    assert record.resolved_date == "2020-03-15T08:20:00Z"
    assert record.date_source == "FILESYSTEM"
    assert record.date_confidence == "FALLBACK"
    assert Code.NO_DATE not in record.warnings

    plan([record])
    assert record.planned_output_path == "Photos_Archive/2020/03/unknown_img.png"


def test_zip_bomb_protection(tmp_path):
    """驗證 ZIP 解壓面對高膨脹率檔案時進行 Zip Bomb 防禦攔截。"""
    zip_path = tmp_path / "bomb.zip"
    out_dir = tmp_path / "out"

    # 建立一個模擬的 ZipInfo，未壓縮 10MB，壓縮大小極小
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 寫入高度可壓縮的全 0 內容 (超過 1000:1)
        zf.writestr("huge_zero.txt", b"\x00" * (2 * 1024 * 1024))

    warnings = extract_zip(zip_path, out_dir)
    assert any("ZIP_BOMB" in w for w in warnings)


def test_cp437_filename_decoding():
    """驗證早期非 UTF-8 ZIP 繁體中文檔名經 decode_member_name 自動轉碼修復。"""
    info = zipfile.ZipInfo()
    info.flag_bits = 0  # 未設定 0x800 (非 UTF-8)
    original_text = "家族旅行_相片"
    # 模擬當初以 UTF-8 字節直接存入但解譯為 CP437
    raw_utf8 = original_text.encode("utf-8")
    info.filename = raw_utf8.decode("cp437")

    decoded = decode_member_name(info)
    assert decoded == original_text


def test_chinese_interactive_report_and_gui_enhancements(tmp_path):
    """驗證繁體中文互動式 HTML5 報告與 GUI 第一階段確定性進度、清空列表、成對膠囊顯示。"""
    from google_photos_takeout_organizer.report import write_report
    from google_photos_takeout_organizer.gui import MainWindow, translate_warning
    from PySide6.QtWidgets import QApplication, QMessageBox

    # 1. 驗證 ZIP_BOMB 繁中翻譯
    assert "異常膨脹" in translate_warning("ZIP_BOMB")

    # 2. 驗證繁體中文互動式 HTML5 報告生成
    manifest = {
        "generated_at": "2026-10-16T11:30:00Z",
        "app_version": "1.3.0",
        "summary": {
            "photos": 3,
            "videos": 1,
            "json_matched": 3,
            "paired_groups": 1,
            "duplicate_files": 1,
            "conflict_review": 0,
            "unknown_date": 0,
        },
        "warnings": ["ZIP_BOMB: 壓縮膨脹比例異常: bomb.bin"],
        "media_records": [
            {
                "original_filename": "IMG_1001.HEIC",
                "media_type": "photo",
                "pair_role": "PRIMARY_PHOTO",
                "resolved_date": "2023-05-01T12:00:00Z",
                "date_source": "GOOGLE_JSON",
                "date_confidence": "HIGH",
                "json_status": "MATCHED",
                "planned_output_path": "Photos_Archive/2023/05/IMG_1001.HEIC",
                "warnings": [],
            },
            {
                "original_filename": "IMG_1001.MOV",
                "media_type": "video",
                "pair_role": "LIVE_PHOTO_VIDEO",
                "resolved_date": "2023-05-01T12:00:00Z",
                "date_source": "GOOGLE_JSON",
                "date_confidence": "HIGH",
                "json_status": "MEDIA_WITHOUT_JSON",
                "planned_output_path": "Photos_Archive/2023/05/IMG_1001.MOV",
                "warnings": [],
            },
        ],
    }
    report_path = tmp_path / "report.html"
    write_report(manifest, report_path)
    html_text = report_path.read_text(encoding="utf-8")
    assert "Google 相簿 Takeout 整理與驗證報告" in html_text
    assert "搜尋檔名、日期或輸出路徑" in html_text
    assert "動態照片 / RAW 成對" in html_text
    assert "成對主照" in html_text
    assert "Live 動態短片" in html_text

    # 3. 驗證 GUI 第一階段進度標籤、清空列表與完成摘要膠囊
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    QMessageBox.information = lambda *args: None

    # 測試清空列表 (_clear_sources)
    dummy_zip = tmp_path / "takeout.zip"
    dummy_zip.write_bytes(b"PK\x05\x06" + b"\x00" * 18)
    win._add_zip_paths([dummy_zip])
    assert len(win.sources) == 1
    assert win.btn_add_more.isEnabled()
    win._clear_sources()
    assert len(win.sources) == 0
    assert not win.btn_add_more.isEnabled()

    # 測試第一階段進度顯示 (ANALYZE_EXTRACT 與 ANALYZE)
    win._on_progress("ANALYZE_EXTRACT", 5, 20, "IMG_0005.JPG")
    assert "正在解壓並掃描 Takeout · 25%" in win.lbl_stage.text()
    win._on_progress("ANALYZE", 10, 20, "IMG_0010.JPG")
    assert "正在分析中繼資料與日期 · 50%" in win.lbl_stage.text()

    # 測試完成摘要膠囊顯示重複隔離與成對綁定
    win.output_dir = tmp_path
    work_dir = tmp_path / ".gpto_work"
    work_dir.mkdir(exist_ok=True)
    (work_dir / "temp.dat").write_bytes(b"x" * 2048)
    win._on_finished_success({
        "manifest": manifest,
        "verification": {"result": "PASS", "verified": 4, "failed": 0},
        "work_dir": str(work_dir),
    })
    assert "重複隔離 <b>1</b>" in win.lbl_stats_media.text()
    assert "成對綁定 <b>1</b> 組" in win.lbl_stats_media.text()
    assert "可釋放" in win.btn_clear_temp.text()

