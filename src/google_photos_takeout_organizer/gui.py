from __future__ import annotations
import os
import sys
import shutil
import webbrowser
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QProgressBar,
    QMessageBox,
    QFileDialog,
    QGroupBox,
    QTextEdit,
)

from .service import analyze
from .exporter import export
from .verifier import verify


WARNING_TRANSLATIONS: dict[str, str] = {
    "MEDIA_WITHOUT_JSON": "找不到對應的中繼資料",
    "JSON_ORPHAN": "找不到對應的照片或影片",
    "AMBIGUOUS_SIDECAR": "有多個可能的中繼資料檔，需要人工確認",
    "DATE_CONFLICT": "拍攝日期來源不一致，需要人工確認",
    "INVALID_JSON": "中繼資料檔格式異常",
    "CORRUPT_MEDIA": "檔案可能損壞或格式暫不支援",
    "UNSUPPORTED_FORMAT": "檔案可能損壞或格式暫不支援",
    "NO_DATE": "無法判定拍攝日期",
    "UNKNOWN_DATE": "無法判定拍攝日期",
    "ZIP_PATH_TRAVERSAL": "壓縮檔包含不安全路徑",
    "INVALID_ZIP": "無法讀取壓縮檔或格式損毀",
    "OUTPUT_COLLISION": "輸出檔名重複，已自動重新命名避免覆寫",
    "COPY_FAILED": "檔案複製失敗",
    "HASH_MISMATCH": "完整性驗證發現問題",
}

def translate_warning(code: str) -> str:
    return WARNING_TRANSLATIONS.get(code, f"需要注意：{code}")

def validate_paths(sources: list[Path], output_dir: Path | None) -> str | None:
    if not sources:
        return "請至少選取一個 Takeout ZIP 檔案。"
    if not output_dir:
        return "請指定輸出資料夾。"
    out_res = output_dir.resolve()
    for s in sources:
        s_res = s.resolve()
        if s_res == out_res:
            return "輸出資料夾不可與來源檔案相同。"
        if s_res.is_dir() and (out_res == s_res or out_res.is_relative_to(s_res)):
            return "輸出資料夾不可位於來源資料夾內部，以避免資料混淆。"
    app_root = Path(__file__).resolve().parent.parent.parent
    if out_res == app_root:
        return "輸出資料夾不可設定於程式專案根目錄。"
    return None

def format_file_size(size_in_bytes: int) -> str:
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    elif size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes / 1024:.1f} KB"
    elif size_in_bytes < 1024 * 1024 * 1024:
        return f"{size_in_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_in_bytes / (1024 * 1024 * 1024):.2f} GB"


class WorkerThread(QThread):
    stage_changed = Signal(str, int)  # status_text, stage_index (1: analyze, 2: export, 3: verify, 4: complete)
    progress_mode = Signal(bool)
    finished_success = Signal(dict)
    finished_error = Signal(str, str, int)

    def __init__(self, sources: list[Path], output_dir: Path, analyze_only: bool = False) -> None:
        super().__init__()
        self.sources = sources
        self.output_dir = output_dir
        self.analyze_only = analyze_only
        self._is_cancelled = False

    def run(self) -> None:
        current_stage = 1
        try:
            work_dir = self.output_dir / ".gpto_work"
            
            current_stage = 1
            self.stage_changed.emit("正在分析 Takeout 檔案...", 1)
            self.progress_mode.emit(True)
            manifest = analyze(self.sources, work_dir)
            
            if self.analyze_only:
                self.stage_changed.emit("分析完成", 4)
                self.progress_mode.emit(False)
                self.finished_success.emit({"manifest": manifest, "analyze_only": True, "work_dir": str(work_dir)})
                return

            if self._is_cancelled:
                return

            current_stage = 2
            self.stage_changed.emit("正在整理照片與影片...", 2)
            export_result = export(work_dir / "manifest.json", self.output_dir)

            if self._is_cancelled:
                return

            current_stage = 3
            self.stage_changed.emit("正在驗證整理結果...", 3)
            verify_result = verify(self.output_dir / "manifest.json", self.output_dir)

            # 只有在全部成功且已寫入正式檔案時，才自動安全清理 .gpto_work
            if (
                not self._is_cancelled
                and verify_result.get("result") == "PASS"
                and verify_result.get("failed", 1) == 0
                and (self.output_dir / "manifest.json").exists()
                and (self.output_dir / "verification.json").exists()
            ):
                # 清理前將視覺化報告 report.html 安全複製至正式輸出根目錄
                work_report = work_dir / "report.html"
                dest_report = self.output_dir / "report.html"
                if work_report.exists() and not dest_report.exists():
                    try:
                        shutil.copyfile(work_report, dest_report)
                    except Exception:
                        pass

                # 安全清理暫存工作區
                try:
                    shutil.rmtree(work_dir, ignore_errors=True)
                except Exception:
                    pass

            current_stage = 4
            self.stage_changed.emit("整理完成", 4)
            self.progress_mode.emit(False)
            self.finished_success.emit({
                "manifest": export_result,
                "verification": verify_result,
                "analyze_only": False,
                "work_dir": str(work_dir),
            })
        except Exception as exc:
            import traceback
            tb = traceback.format_exc()
            self.progress_mode.emit(False)
            self.finished_error.emit(str(exc), tb, current_stage)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Google 相簿 Takeout 整理工具")
        self.resize(920, 640)
        self.setMinimumSize(820, 580)

        self.sources: list[Path] = []
        self.output_dir: Path | None = None
        self.worker: WorkerThread | None = None
        self.last_work_dir: Path | None = None
        self.last_summary: dict[str, Any] | None = None

        self._init_ui()
        self._update_action_state()

    def _init_ui(self) -> None:
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(18, 16, 18, 16)

        # 1. 標題與說明 (Header)
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        lbl_title = QLabel("Google 相簿 Takeout 整理工具", self)
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1a1a1a;")
        lbl_subtitle = QLabel("將 Google Takeout 照片安全整理成依日期分類的資料夾", self)
        lbl_subtitle.setStyleSheet("color: #666666; font-size: 12px;")
        header_layout.addWidget(lbl_title)
        header_layout.addWidget(lbl_subtitle)
        main_layout.addLayout(header_layout)

        # 2. 來源檔案區塊
        src_group = QGroupBox("來源檔案", self)
        src_layout = QVBoxLayout(src_group)
        src_layout.setSpacing(6)
        src_layout.setContentsMargins(12, 10, 12, 10)

        self.src_list = QListWidget(self)
        self.src_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.src_list.setFixedHeight(96)
        src_layout.addWidget(self.src_list)

        src_action_layout = QHBoxLayout()
        self.btn_add_zip = QPushButton("選擇 ZIP", self)
        self.btn_add_zip.clicked.connect(self._choose_zips)
        src_action_layout.addWidget(self.btn_add_zip)

        self.btn_add_more = QPushButton("加入更多", self)
        self.btn_add_more.clicked.connect(self._choose_zips)
        src_action_layout.addWidget(self.btn_add_more)

        self.btn_remove = QPushButton("移除", self)
        self.btn_remove.clicked.connect(self._remove_selected)
        src_action_layout.addWidget(self.btn_remove)

        src_action_layout.addSpacing(12)

        self.lbl_src_count = QLabel("尚未選取 ZIP", self)
        self.lbl_src_count.setStyleSheet("color: #555555; font-weight: 500;")
        src_action_layout.addWidget(self.lbl_src_count)

        src_action_layout.addStretch()
        src_layout.addLayout(src_action_layout)

        # 次要淡色提示文字 (拆行、小字、不搶焦點)
        self.lbl_src_hint = QLabel("若同一批 Google Takeout 有多個分卷，建議一次全部選取，以提高中繼資料配對完整度。", self)
        self.lbl_src_hint.setStyleSheet("color: #777777; font-size: 11px; margin-top: 2px;")
        src_layout.addWidget(self.lbl_src_hint)

        main_layout.addWidget(src_group)

        # 3. 輸出位置區塊
        out_group = QGroupBox("輸出位置", self)
        out_layout = QHBoxLayout(out_group)
        out_layout.setSpacing(8)
        out_layout.setContentsMargins(12, 10, 12, 10)

        self.txt_output = QLineEdit(self)
        self.txt_output.setReadOnly(True)
        self.txt_output.setPlaceholderText("請選擇整理後檔案的存放資料夾...")
        out_layout.addWidget(self.txt_output)

        self.btn_choose_out = QPushButton("選擇", self)
        self.btn_choose_out.setFixedWidth(80)
        self.btn_choose_out.clicked.connect(self._choose_output)
        out_layout.addWidget(self.btn_choose_out)

        main_layout.addWidget(out_group)

        # 4. 安全提示 (固定提示，不可取消)
        lbl_safety = QLabel("✓ 原始 Takeout 不會被移動或刪除", self)
        lbl_safety.setStyleSheet("color: #2e7d32; font-weight: bold; font-size: 12px; margin-left: 4px;")
        main_layout.addWidget(lbl_safety)

        # 5. 主要操作按鈕 (唯一 Primary CTA，置中突顯)
        cta_layout = QHBoxLayout()
        cta_layout.addStretch()
        self.btn_start = QPushButton("開始整理", self)
        self.btn_start.setObjectName("btn_start")
        self.btn_start.setFixedHeight(42)
        self.btn_start.setMinimumWidth(240)
        self.btn_start.setStyleSheet("""
            QPushButton#btn_start {
                font-size: 15px;
                font-weight: bold;
                padding: 6px 20px;
            }
        """)
        self.btn_start.clicked.connect(lambda: self._start_task(analyze_only=False))
        cta_layout.addWidget(self.btn_start)
        cta_layout.addStretch()
        main_layout.addLayout(cta_layout)

        # 6. 處理進度區塊 (現代化 Stepper)
        progress_group = QGroupBox("處理進度", self)
        prog_layout = QVBoxLayout(progress_group)
        prog_layout.setSpacing(6)
        prog_layout.setContentsMargins(12, 10, 12, 10)

        # Stepper 流程狀態指示
        self.lbl_stepper = QLabel(self)
        self._update_stepper(stage=0)
        prog_layout.addWidget(self.lbl_stepper)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        prog_layout.addWidget(self.progress_bar)

        self.lbl_stage = QLabel("就緒", self)
        self.lbl_stage.setStyleSheet("color: #444444; font-size: 12px; margin-top: 2px;")
        prog_layout.addWidget(self.lbl_stage)

        main_layout.addWidget(progress_group)

        # 7. 整理結果區塊 (尚未完成時壓縮高度，完成後展開)
        self.res_group = QGroupBox("整理結果", self)
        self.res_layout = QVBoxLayout(self.res_group)
        self.res_layout.setContentsMargins(12, 10, 12, 10)

        # 尚未完成前顯示簡潔提示
        self.lbl_res_placeholder = QLabel("完成整理後，這裡會顯示整理與驗證結果。", self)
        self.lbl_res_placeholder.setStyleSheet("color: #888888; font-size: 12px;")
        self.res_layout.addWidget(self.lbl_res_placeholder)

        # 完成後展開的詳細內容元件
        self.widget_res_details = QWidget(self)
        details_layout = QVBoxLayout(self.widget_res_details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(8)

        self.lbl_stats_media = QLabel(self)
        self.lbl_stats_media.setStyleSheet("font-size: 13px; font-weight: 500;")
        details_layout.addWidget(self.lbl_stats_media)

        self.lbl_stats_verify = QLabel(self)
        self.lbl_stats_verify.setStyleSheet("font-size: 13px; font-weight: 500;")
        details_layout.addWidget(self.lbl_stats_verify)

        # 快捷動作按鈕
        self.quick_layout = QHBoxLayout()
        self.btn_open_out = QPushButton("開啟整理結果", self)
        self.btn_open_out.clicked.connect(self._open_output_dir)
        self.quick_layout.addWidget(self.btn_open_out)

        self.btn_open_review = QPushButton("開啟人工確認", self)
        self.btn_open_review.clicked.connect(self._open_review_dir)
        self.quick_layout.addWidget(self.btn_open_review)

        self.btn_open_report = QPushButton("查看詳細報告", self)
        self.btn_open_report.clicked.connect(self._open_report_file)
        self.quick_layout.addWidget(self.btn_open_report)
        self.quick_layout.addStretch()

        details_layout.addLayout(self.quick_layout)
        self.res_layout.addWidget(self.widget_res_details)

        # 預設隱藏結果詳細內容
        self.widget_res_details.hide()

        main_layout.addWidget(self.res_group)

    def _update_stepper(self, stage: int, error_stage: int = 0) -> None:
        """
        stage:
            0: 尚未開始
            1: 分析中
            2: 整理中
            3: 驗證中
            4: 完成
        error_stage:
            若大於 0 則在該階段標記 !
        """
        s1 = "○"
        s2 = "○"
        s3 = "○"

        if stage == 1:
            s1 = "●"
        elif stage == 2:
            s1 = "✓"
            s2 = "●"
        elif stage == 3:
            s1 = "✓"
            s2 = "✓"
            s3 = "●"
        elif stage == 4:
            s1 = "✓"
            s2 = "✓"
            s3 = "✓"

        if error_stage == 1:
            s1 = "!"
        elif error_stage == 2:
            s2 = "!"
        elif error_stage == 3:
            s3 = "!"

        html = (
            f"<span style='color: #2e7d32; font-weight: bold;'>{s1}</span> 分析資料"
            f" &nbsp;───────&nbsp; "
            f"<span style='color: #2e7d32; font-weight: bold;'>{s2}</span> 整理檔案"
            f" &nbsp;───────&nbsp; "
            f"<span style='color: #2e7d32; font-weight: bold;'>{s3}</span> 驗證結果"
        )
        self.lbl_stepper.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_stepper.setText(html)

    def _choose_zips(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "選擇 Google Takeout ZIP 檔案",
            "",
            "Takeout ZIP 壓縮檔 (*.zip)",
        )
        if not files:
            return
        
        for f in files:
            p = Path(f).resolve()
            if p not in self.sources and p.is_file() and p.suffix.lower() == ".zip":
                self.sources.append(p)
                size_str = format_file_size(p.stat().st_size)
                item = QListWidgetItem(f"{p.name}    ({size_str})")
                item.setData(Qt.ItemDataRole.UserRole, str(p))
                self.src_list.addItem(item)
        
        self._update_source_status()
        self._update_action_state()

    def _remove_selected(self) -> None:
        selected_items = self.src_list.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            path_str = item.data(Qt.ItemDataRole.UserRole)
            p = Path(path_str)
            if p in self.sources:
                self.sources.remove(p)
            self.src_list.takeItem(self.src_list.row(item))
        self._update_source_status()
        self._update_action_state()

    def _update_source_status(self) -> None:
        count = len(self.sources)
        if count == 0:
            self.lbl_src_count.setText("尚未選取 ZIP")
            self.btn_remove.setEnabled(False)
        elif count == 1:
            self.lbl_src_count.setText("已選取 1 個 ZIP")
            self.btn_remove.setEnabled(True)
        else:
            self.lbl_src_count.setText(f"已選取 {count} 個 ZIP")
            self.btn_remove.setEnabled(True)

    def _choose_output(self) -> None:
        dir_selected = QFileDialog.getExistingDirectory(self, "選擇輸出位置")
        if dir_selected:
            self.output_dir = Path(dir_selected).resolve()
            self.txt_output.setText(str(self.output_dir))
            self.txt_output.setToolTip(str(self.output_dir))
            self._update_action_state()

    def _update_action_state(self) -> None:
        is_running = self.worker is not None and self.worker.isRunning()
        has_sources = len(self.sources) > 0
        has_output = self.output_dir is not None

        can_start = has_sources and has_output and not is_running
        self.btn_start.setEnabled(can_start)
        self.btn_add_zip.setEnabled(not is_running)
        self.btn_add_more.setEnabled(not is_running)
        self.btn_remove.setEnabled(len(self.sources) > 0 and not is_running)
        self.btn_choose_out.setEnabled(not is_running)

    def _start_task(self, analyze_only: bool = False) -> None:
        err = validate_paths(self.sources, self.output_dir)
        if err:
            QMessageBox.warning(self, "路徑檢查", err)
            return

        self._update_action_state()
        self.lbl_res_placeholder.show()
        self.widget_res_details.hide()
        self._update_stepper(stage=1)

        assert self.output_dir is not None
        self.worker = WorkerThread(self.sources, self.output_dir, analyze_only=analyze_only)
        self.worker.stage_changed.connect(self._on_stage_changed)
        self.worker.progress_mode.connect(self._on_progress_mode)
        self.worker.finished_success.connect(self._on_finished_success)
        self.worker.finished_error.connect(self._on_finished_error)
        self.worker.start()
        self._update_action_state()

    def _on_stage_changed(self, text: str, stage_idx: int) -> None:
        self.lbl_stage.setText(text)
        self._update_stepper(stage=stage_idx)

    def _on_progress_mode(self, is_busy: bool) -> None:
        if is_busy:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)

    def _on_finished_success(self, data: dict) -> None:
        self.worker = None
        self._update_action_state()

        manifest = data.get("manifest", {})
        summary = manifest.get("summary", {})
        verification = data.get("verification")
        work_dir = Path(data.get("work_dir", ""))
        self.last_work_dir = work_dir
        self.last_summary = summary

        is_analyze = data.get("analyze_only", False)
        title_msg = "分析完成" if is_analyze else "整理完成"

        review_count = 0
        if not is_analyze and self.output_dir:
            # 支援繁體中文「待人工確認」與舊式「Review」資料夾
            review_dir = self.output_dir / "待人工確認"
            if not review_dir.exists():
                review_dir = self.output_dir / "Review"
            if review_dir.exists():
                review_count = sum(1 for p in review_dir.rglob("*") if p.is_file())
        else:
            review_count = sum(
                1 for r in manifest.get("media_records", [])
                if r.get("planned_output_path", "").startswith("待人工確認/")
                or r.get("planned_output_path", "").startswith("Review/")
            )

        # 展開結果區域
        self.lbl_res_placeholder.hide()
        self.widget_res_details.show()

        # 第一行：媒體統計
        photos = summary.get("photos", 0)
        videos = summary.get("videos", 0)
        matched_json = summary.get("json_matched", 0)
        self.lbl_stats_media.setText(
            f"照片 <b>{photos}</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
            f"影片 <b>{videos}</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
            f"中繼資料 <b>{matched_json}</b>"
        )

        # 第二行：驗證與人工確認
        if verification:
            v_ok = verification.get("verified", 0)
            v_fail = verification.get("failed", 0)
            if verification.get("result") == "PASS":
                v_text = f"<span style='color: #2e7d32;'>✓ 驗證成功 {v_ok}</span>"
            else:
                v_text = f"<span style='color: #c62828;'>⚠ 驗證異常 (失敗 {v_fail} / 成功 {v_ok})</span>"
        else:
            v_text = f"狀態：{title_msg}"

        if review_count > 0:
            r_text = f"<span style='color: #d97706;'>⚠ 需人工確認 {review_count}</span>"
            self.btn_open_review.show()
            self.btn_open_review.setEnabled(True)
        else:
            r_text = "<span style='color: #555555;'>需人工確認 0</span>"
            self.btn_open_review.hide()

        self.lbl_stats_verify.setText(f"{v_text}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{r_text}")

        # 快捷按鈕啟用
        if not is_analyze and self.output_dir and self.output_dir.exists():
            self.btn_open_out.setEnabled(True)

        report_file = work_dir / "report.html"
        self.btn_open_report.setEnabled(report_file.exists())

        self.lbl_stage.setText(f"✓ {title_msg}")

        if verification and verification.get("result") != "PASS":
            QMessageBox.critical(
                self,
                "驗證警示",
                "整理已完成，但完整性驗證發現問題。\n請先查看詳細報告，不要刪除原始 Takeout 檔案！",
            )
        else:
            QMessageBox.information(self, "完成", f"Google Takeout {title_msg}！")

    def _on_finished_error(self, message: str, traceback_str: str, error_stage: int) -> None:
        self.worker = None
        self._update_action_state()
        self.lbl_stage.setText("整理過程發生問題")
        self._update_stepper(stage=error_stage, error_stage=error_stage)

        try:
            log_dir = self.output_dir or Path.cwd()
            err_log = log_dir / "organizer_error.log"
            err_log.write_text(traceback_str, encoding="utf-8")
        except Exception:
            pass

        # 結構化錯誤視窗：上半部繁中簡明摘要，可展開查看 traceback
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle("處理錯誤")
        msg_box.setText(f"處理過程中發生錯誤：\n{message}")
        msg_box.setInformativeText("已將錯誤記錄保存至工作日誌。若需要排查問題，請點擊下方「顯示詳細資料」。")
        msg_box.setDetailedText(traceback_str)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

    def _open_output_dir(self) -> None:
        if self.output_dir and self.output_dir.exists():
            if sys.platform == "win32":
                os.startfile(str(self.output_dir))
            else:
                webbrowser.open(self.output_dir.as_uri())

    def _open_review_dir(self) -> None:
        if self.output_dir:
            review_dir = self.output_dir / "待人工確認"
            if not review_dir.exists():
                review_dir = self.output_dir / "Review"
            if review_dir.exists():
                if sys.platform == "win32":
                    os.startfile(str(review_dir))
                else:
                    webbrowser.open(review_dir.as_uri())
            else:
                QMessageBox.information(self, "人工確認", "本次整理無需要人工確認的項目。")

    def _open_report_file(self) -> None:
        if self.output_dir:
            out_report = self.output_dir / "report.html"
            if out_report.exists():
                webbrowser.open(out_report.resolve().as_uri())
                return
        if self.last_work_dir:
            report_path = self.last_work_dir / "report.html"
            if report_path.exists():
                webbrowser.open(report_path.resolve().as_uri())
                return
        QMessageBox.information(self, "報告", "找不到詳細報告檔案。")

    def closeEvent(self, event: Any) -> None:
        if self.worker is not None and self.worker.isRunning():
            reply = QMessageBox.question(
                self,
                "確認關閉",
                "目前正在整理資料，確定要中止並關閉嗎？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.worker._is_cancelled = True
                self.worker.terminate()
                self.worker.wait(2000)
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

