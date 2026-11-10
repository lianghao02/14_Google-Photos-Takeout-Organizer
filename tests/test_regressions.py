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


def test_incremental_export_collision_updates_manifest_for_verify(tmp_path):
    """跨波次同名不同內容發生 __2 改名時，使用匯出後的 manifest 核對必須 PASS 且保留全波次明細。"""
    from google_photos_takeout_organizer.service import merge_wave_manifests

    def _make_wave_zip(zip_path: Path, color: tuple[int, int, int], ts: str) -> None:
        img_buf = io.BytesIO()
        Image.new("RGB", (6, 6), color).save(img_buf, format="JPEG")
        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr("Takeout/Album/IMG_001.jpg", img_buf.getvalue())
            z.writestr(
                "Takeout/Album/IMG_001.jpg.supplemental-metadata.json",
                f'{{"photoTakenTime": {{"timestamp": "{ts}"}}}}',
            )

    w1_zip = tmp_path / "wave1.zip"
    w2_zip = tmp_path / "wave2.zip"
    _make_wave_zip(w1_zip, (200, 10, 10), "1600000000")
    _make_wave_zip(w2_zip, (10, 200, 10), "1600000000")

    work = tmp_path / "work"
    out = tmp_path / "out"

    analyze([w1_zip], work, archive_start_index=1)
    export(work / "manifest.json", out, export_sidecars=False)
    w1_manifest_snap = work / "w1_exp.json"
    w1_manifest_snap.write_text((out / "manifest.json").read_text(encoding="utf-8"), encoding="utf-8")
    assert verify(w1_manifest_snap, out)["result"] == "PASS"
    w1_verified = __import__("json").loads((out / "manifest.json").read_text(encoding="utf-8"))

    analyze([w2_zip], work, archive_start_index=2)
    export(work / "manifest.json", out, export_sidecars=False)
    w2_manifest_snap = work / "w2_exp.json"
    w2_manifest_snap.write_text((out / "manifest.json").read_text(encoding="utf-8"), encoding="utf-8")
    w2_res = verify(w2_manifest_snap, out)
    assert w2_res["result"] == "PASS"
    w2_verified = __import__("json").loads((out / "manifest.json").read_text(encoding="utf-8"))

    final_manifest = merge_wave_manifests([w1_verified, w2_verified], out)
    assert final_manifest["verification"] == {"result": "PASS", "verified": 2, "failed": 0}
    assert len(final_manifest["media_records"]) == 2
    out_paths = sorted(r["planned_output_path"] for r in final_manifest["media_records"])
    assert out_paths == [
        "Photos_Archive/2020/09/IMG_001.jpg",
        "Photos_Archive/2020/09/IMG_001__2.jpg",
    ]
    assert (out / "report.html").is_file()
    assert (out / "verification.json").is_file()


def test_reconcile_cross_wave_bidirectional_moves_live_photo_pair(tmp_path):
    """驗證跨波雙向補配對：前波剩 JSON 供後波使用、後波剩 JSON 召回前波 Live Photo 成對搬移。"""
    import json
    import shutil
    from google_photos_takeout_organizer.service import merge_wave_manifests, reconcile_cross_wave

    w1_zip = tmp_path / "wave1.zip"
    w2_zip = tmp_path / "wave2.zip"

    buf_a = io.BytesIO()
    Image.new("RGB", (4, 4), (40, 80, 120)).save(buf_a, format="JPEG")
    buf_b = io.BytesIO()
    Image.new("RGB", (4, 4), (120, 80, 40)).save(buf_b, format="JPEG")

    with zipfile.ZipFile(w1_zip, "w") as z:
        # 故意使用無效 ZIP 時間戳 (1980 無實際拍攝日期) 且不附帶 Live Photo 的 JSON
        z.writestr(zipfile.ZipInfo("Takeout/Album/IMG_0099.jpg", (2018, 0, 0, 0, 0, 0)), buf_a.getvalue())
        z.writestr(zipfile.ZipInfo("Takeout/Album/IMG_0099.MOV", (2018, 0, 0, 0, 0, 0)), b"live-mov-bytes")
        # 屬於 Wave 2 照片的 JSON 先出現在 Wave 1
        z.writestr(
            "Takeout/Album/future.jpg.supplemental-metadata.json",
            json.dumps({"photoTakenTime": {"timestamp": "1629469800"}}),
        )

    with zipfile.ZipFile(w2_zip, "w") as z:
        z.writestr(zipfile.ZipInfo("Takeout/Album/future.jpg", (2018, 0, 0, 0, 0, 0)), buf_b.getvalue())
        # 屬於 Wave 1 Live Photo 的 JSON 到 Wave 2 才解壓
        z.writestr(
            "Takeout/Album/IMG_0099.jpg.supplemental-metadata.json",
            json.dumps({"photoTakenTime": {"timestamp": "1629469800"}}),
        )

    work = tmp_path / "work"
    out = tmp_path / "out"
    extracted_root = work / "extracted"

    def _prune_wave(m: dict, w_idx: int) -> None:
        used_jsons = {Path(r["json_path"]) for r in m["media_records"] if r.get("json_path")}
        for sub in list(extracted_root.iterdir()):
            if sub.is_dir() and (sub.name.startswith("archive_") or sub.name.startswith("json_pool_w")):
                kept = 0
                for p in list(sub.rglob("*")):
                    if p.is_file():
                        if p.suffix.lower() == ".json" and not p.name.startswith(".gpto-") and p not in used_jsons:
                            kept += 1
                        else:
                            p.unlink(missing_ok=True)
                if kept == 0:
                    shutil.rmtree(sub, ignore_errors=True)
                elif sub.name.startswith("archive_"):
                    sub.replace(extracted_root / f"json_pool_w{w_idx}_{sub.name}")

    # Wave 1
    m1 = analyze([w1_zip], work, archive_start_index=1)
    assert all(r["planned_output_path"].startswith("Unknown-Date/") for r in m1["media_records"])
    export(work / "manifest.json", out, export_sidecars=False)
    snap1 = work / "s1.json"
    snap1.write_text((out / "manifest.json").read_text(encoding="utf-8"), encoding="utf-8")
    assert verify(snap1, out)["result"] == "PASS"
    wm1 = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    _prune_wave(m1, 1)

    # Wave 2：自動消費 json_pool_w1 中的 future.jpg.json
    m2 = analyze([w2_zip], work, archive_start_index=2)
    assert m2["media_records"][0]["planned_output_path"] == "Photos_Archive/2021/08/future.jpg"
    export(work / "manifest.json", out, export_sidecars=False)
    snap2 = work / "s2.json"
    snap2.write_text((out / "manifest.json").read_text(encoding="utf-8"), encoding="utf-8")
    assert verify(snap2, out)["result"] == "PASS"
    wm2 = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    _prune_wave(m2, 2)

    # 跨波補配對：應把 Wave 1 的 IMG_0099.jpg 與伴隨的 IMG_0099.MOV 一起搬回 Photos_Archive/2021/08/
    merged = [r for wm in (wm1, wm2) for r in wm["media_records"]]
    merged, final_orphans, matched_cnt, moved_cnt = reconcile_cross_wave(merged, extracted_root, out)
    assert matched_cnt == 1
    assert moved_cnt == 2
    assert not final_orphans

    c = 0
    for wm in (wm1, wm2):
        n = len(wm["media_records"])
        wm["media_records"] = merged[c : c + n]
        c += n

    final_manifest = merge_wave_manifests([wm1, wm2], out, orphan_warnings=final_orphans)
    assert final_manifest["verification"] == {"result": "PASS", "verified": 3, "failed": 0}
    assert (out / "Photos_Archive/2021/08/IMG_0099.jpg").is_file()
    assert (out / "Photos_Archive/2021/08/IMG_0099.MOV").is_file()
    assert (out / "Photos_Archive/2021/08/future.jpg").is_file()
    assert not (out / "Unknown-Date/IMG_0099.jpg").exists()
    assert not (out / "Unknown-Date/IMG_0099.MOV").exists()
    assert not any(w.startswith("JSON_ORPHAN:") for w in final_manifest["warnings"])


def test_invalid_zero_exif_datetime_and_malformed_offset_fallback(tmp_path):
    """無效全零 EXIF 日期 (0000:00:00 00:00:00) 應判定為 NOT_FOUND；怪異 offset 不應捨棄有效日期。"""
    from google_photos_takeout_organizer.metadata import image_metadata

    zero_jpg = tmp_path / "zero.jpg"
    exif_zero = Image.Exif()
    exif_zero[306] = "0000:00:00 00:00:00"
    Image.new("RGB", (4, 4), (10, 20, 30)).save(zero_jpg, format="JPEG", exif=exif_zero)
    _, _, dt_zero, st_zero = image_metadata(zero_jpg)
    assert st_zero == "NOT_FOUND"
    assert dt_zero is None

    bad_off_jpg = tmp_path / "bad_offset.jpg"
    exif_good = Image.Exif()
    exif_good[306] = "2022:07:15 08:30:00"
    exif_good[36880] = "+99:99"
    Image.new("RGB", (4, 4), (10, 20, 30)).save(bad_off_jpg, format="JPEG", exif=exif_good)
    _, _, dt_ok, st_ok = image_metadata(bad_off_jpg)
    assert st_ok == "FOUND"
    assert dt_ok == "2022-07-15T08:30:00"


def test_phase4_stem_prefix_boundary_no_cross_steal(tmp_path):
    """Phase 4 字首比對不應讓 IMG_10.jpg 誤搶同目錄的 IMG_100.jpg.json，但允許界線分隔衍生名。"""
    j100 = tmp_path / "IMG_100.jpg.json"
    j100.write_text('{"photoTakenTime": {"timestamp": "1600000000"}}', encoding="utf-8")
    r10 = MediaRecord("1", "a1", str(tmp_path / "IMG_10.jpg"), "IMG_10.jpg", "IMG_10.jpg", ".jpg", 100, "photo")
    used, warnings = match([r10], [j100], {"a1": tmp_path})
    assert r10.json_status == "MEDIA_WITHOUT_JSON"
    assert not used
    assert any("JSON_ORPHAN:" in w for w in warnings)

    j_edited = tmp_path / "IMG_10-edited.jpg.json"
    j_edited.write_text('{"photoTakenTime": {"timestamp": "1600000000"}}', encoding="utf-8")
    r10_b = MediaRecord("2", "a1", str(tmp_path / "IMG_10.jpg"), "IMG_10.jpg", "IMG_10.jpg", ".jpg", 100, "photo")
    used_b, warnings_b = match([r10_b], [j_edited], {"a1": tmp_path})
    assert r10_b.json_status == "MATCHED"
    assert len(used_b) == 1
    assert not warnings_b


def test_exporter_and_verifier_retry_on_fuse_enotconn(tmp_path, monkeypatch):
    """當 Google Drive FUSE 拋出 Errno 107 時，export 與 verify 皆應觸發自癒並重試成功。"""
    import json
    from google_photos_takeout_organizer import exporter, utils, verifier

    src = tmp_path / "pic.jpg"
    src.write_bytes(b"real-image-bytes")
    rec = MediaRecord(
        id="r1", archive_id="a1", source_path=str(src), relative_path="pic.jpg",
        original_filename="pic.jpg", extension=".jpg", size=len(src.read_bytes()),
        media_type="photo", sha256=sha256(src),
        planned_output_path="Photos_Archive/2023/01/pic.jpg",
    )
    m_path = tmp_path / "manifest.json"
    m_path.write_text(json.dumps({"media_records": [rec.to_dict()]}), encoding="utf-8")
    out = tmp_path / "out"

    heal_calls = 0

    def fake_heal(exc):
        nonlocal heal_calls
        if getattr(exc, "errno", None) == 107 or "Transport endpoint is not connected" in str(exc):
            heal_calls += 1
            return True
        return False

    monkeypatch.setattr(utils, "heal_fuse_if_disconnected", fake_heal)
    monkeypatch.setattr(exporter, "heal_fuse_if_disconnected", fake_heal)

    real_stat = utils.safe_stat
    stat_attempts = 0

    def flaky_stat(p: Path):
        nonlocal stat_attempts
        stat_attempts += 1
        if stat_attempts in (1, 6):
            raise OSError(107, "Transport endpoint is not connected")
        return real_stat(p)

    monkeypatch.setattr(exporter, "safe_stat", flaky_stat)
    monkeypatch.setattr(verifier, "safe_stat", flaky_stat)

    exp_res = exporter.export(m_path, out, export_sidecars=False)
    assert exp_res["media_records"][0]["export_status"] == "COPIED"

    stat_attempts = 5
    ver_res = verifier.verify(out / "manifest.json", out)
    assert ver_res == {"result": "PASS", "verified": 1, "failed": 0}
    assert heal_calls >= 2


def test_scanner_raw_formats_and_colab_notebook_regex(tmp_path):
    """確認 scanner 納入 RAW 格式，並驗證 01 號筆記本多分卷與 4 位數分卷正規表示式。"""
    import json
    import re
    from google_photos_takeout_organizer.scanner import scan

    raw_file = tmp_path / "DSC_0001.ARW"
    raw_file.write_bytes(b"raw")
    media, _ = scan(tmp_path, "a1")
    assert media[0].media_type == "photo"

    nb_path = Path(__file__).resolve().parents[1] / "colab" / "01_相簿整理去重.ipynb"
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    cell3_src = "".join(nb["cells"][6]["source"])
    m_pat = re.search(r"zip_pat = re\.compile\(r'([^']+)'", cell3_src)
    assert m_pat is not None
    zip_pat = re.compile(m_pat.group(1), re.IGNORECASE)

    samples = {
        "takeout-20260807T131922Z-001.zip": ("20260807T131922Z", None, "001", None),
        "takeout-20260807T131922Z-1-002.zip": ("20260807T131922Z", "1", "002", None),
        "takeout-20260807T131922Z-2-001 (1).zip": ("20260807T131922Z", "2", "001", "1"),
        "takeout-20260807T131922Z-1-1000.zip": ("20260807T131922Z", "1", "1000", None),
    }
    for fname, expected in samples.items():
        m = zip_pat.match(fname)
        assert m is not None, fname
        assert m.groups() == expected
