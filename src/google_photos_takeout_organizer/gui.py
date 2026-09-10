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
from .exporter import SafetyConflictError
from .session import WorkflowState, create_session, is_incomplete_session, load_session, safe_temp_target, save_session, sources_match


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
    cancelled = Signal(dict)
    progress_changed = Signal(str, int, int, str)

    def __init__(self, sources: list[Path], output_dir: Path, analyze_only: bool = False, session: dict | None = None) -> None:
        super().__init__()
        self.sources = sources
        self.output_dir = output_dir
        self.analyze_only = analyze_only
        self._is_cancelled = False
        self.session = session or create_session(sources, output_dir)

    def request_cancel(self) -> None:
        self._is_cancelled = True
        self.session["status"] = WorkflowState.CANCEL_REQUESTED
        save_session(self.output_dir, self.session)

    def _cancelled_result(self, work_dir: Path, manifest: dict | None = None) -> None:
        self.session.update({"status": WorkflowState.CANCELLED, "cancelled": True, "completed": False})
        save_session(self.output_dir, self.session)
        self.progress_mode.emit(False)
        self.cancelled.emit({"manifest": manifest or {}, "work_dir": str(work_dir)})

    def run(self) -> None:
        current_stage = 1
        try:
            work_dir = self.output_dir / ".gpto_work"
            
            manifest_path = work_dir / "manifest.json"
            if not self.session.get("analyze_completed", False):
                current_stage = 1
                self.session.update({"status": WorkflowState.RUNNING_ANALYZE, "current_stage": "ANALYZE", "cancelled": False})
                save_session(self.output_dir, self.session)
                self.stage_changed.emit("正在分析 Takeout 檔案…", 1)
                self.progress_mode.emit(True)
                manifest = analyze(self.sources, work_dir, cancel_requested=lambda: self._is_cancelled)
                self.session["analyze_completed"] = True
                save_session(self.output_dir, self.session)
            else:
                manifest = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
            
            if self.analyze_only:
                self.stage_changed.emit("分析完成", 4)
                self.progress_mode.emit(False)
                self.finished_success.emit({"manifest": manifest, "analyze_only": True, "work_dir": str(work_dir)})
                return

            if self._is_cancelled:
                self._cancelled_result(work_dir, manifest); return

            current_stage = 2
            if self.session.get("export_completed", False):
                export_result = __import__("json").loads((self.output_dir / "manifest.json").read_text(encoding="utf-8"))
            else:
                required = sum(int(record.get("size", 0)) for record in manifest.get("media_records", []))
                required += sum(path.stat().st_size for path in work_dir.rglob("*") if path.is_file())
                if shutil.disk_usage(self.output_dir).free < required:
                    raise RuntimeError("分析完成，但目前剩餘空間不足以安全完成整理。")
                self.session.update({"status": WorkflowState.RUNNING_EXPORT, "current_stage": "EXPORT"})
                save_session(self.output_dir, self.session)
                self.stage_changed.emit("正在整理照片與影片…", 2)
                self.progress_mode.emit(False)
                export_result = export(manifest_path if manifest_path.exists() else self.output_dir / "manifest.json", self.output_dir, self._progress, lambda: self._is_cancelled)
                if export_result.get("export_state") == "CANCELLED":
                    self._cancelled_result(work_dir, export_result); return
                self.session["export_completed"] = True
                save_session(self.output_dir, self.session)

            if self._is_cancelled:
                self._cancelled_result(work_dir, export_result); return

            current_stage = 3
            self.session.update({"status": WorkflowState.RUNNING_VERIFY, "current_stage": "VERIFY"})
            save_session(self.output_dir, self.session)
            self.stage_changed.emit("正在驗證檔案…", 3)
            verify_result = verify(self.output_dir / "manifest.json", self.output_dir, self._progress, lambda: self._is_cancelled)
            if verify_result.get("result") == "CANCELLED":
                self._cancelled_result(work_dir, export_result); return
            self.session.update({"verify_completed": True, "completed": verify_result.get("result") == "PASS", "cancelled": False, "status": WorkflowState.COMPLETED if verify_result.get("result") == "PASS" else WorkflowState.FAILED})
            save_session(self.output_dir, self.session)

            # report is preserved in formal output; temporary data remains until user clears it.
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

            current_stage = 4
            self.stage_changed.emit("整理完成", 4)
            self.progress_mode.emit(False)
            self.finished_success.emit({
                "manifest": export_result,
                "verification": verify_result,
                "analyze_only": False,
                "work_dir": str(work_dir),
            })
        except SafetyConflictError as exc:
            self.session.update({"status": WorkflowState.SAFETY_CONFLICT, "completed": False})
            save_session(self.output_dir, self.session)
            self.progress_mode.emit(False)
            self.finished_error.emit("偵測到既有輸出檔案與預期內容不同。為避免覆寫資料，已停止續作。", "", current_stage)
        except InterruptedError:
            self._cancelled_result(work_dir)
        except Exception as exc:
            import traceback
            tb = traceback.format_exc()
            self.progress_mode.emit(False)
            self.finished_error.emit(str(exc), tb, current_stage)

    def _progress(self, stage: str, current: int, total: int, filename: str) -> None:
        self.progress_changed.emit(stage, current, total, filename)


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
        self.workflow_state = WorkflowState.READY
        self.pending_close = False
        self.setAcceptDrops(True)

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

        self.btn_cancel = QPushButton("取消整理", self)
        self.btn_cancel.clicked.connect(self._request_cancel)
        self.btn_cancel.hide()
        cta_layout.addWidget(self.btn_cancel)

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
        self.lbl_current_file = QLabel("", self)
        self.lbl_current_file.setStyleSheet("color: #666666; font-size: 11px;")
        self.lbl_current_file.setToolTip("")
        prog_layout.addWidget(self.lbl_current_file)

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
        self.btn_next_batch = QPushButton("整理下一批", self)
        self.btn_next_batch.clicked.connect(self._reset_next_batch)
        details_layout.addWidget(self.btn_next_batch)
        self.btn_clear_temp = QPushButton("清除暫存資料", self)
        self.btn_clear_temp.clicked.connect(self._clear_temp)
        details_layout.addWidget(self.btn_clear_temp)
        self.btn_clear_temp.hide()
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
        
        self._add_zip_paths([Path(f) for f in files])

    def _add_zip_paths(self, paths: list[Path]) -> tuple[int, int]:
        added = ignored = 0
        for f in paths:
            p = Path(f).resolve()
            if p not in self.sources and p.is_file() and p.suffix.lower() == ".zip":
                self.sources.append(p)
                size_str = format_file_size(p.stat().st_size)
                item = QListWidgetItem(f"{p.name}    ({size_str})")
                item.setData(Qt.ItemDataRole.UserRole, str(p))
                self.src_list.addItem(item)
                added += 1
            elif p.suffix.lower() != ".zip":
                ignored += 1
        
        self._update_source_status()
        self._update_action_state()
        return added, ignored

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
            self._detect_resume()
            self._update_action_state()

    def _update_action_state(self) -> None:
        is_running = self.worker is not None and self.worker.isRunning()
        has_sources = len(self.sources) > 0
        has_output = self.output_dir is not None

        space_ok = self._disk_preflight_message() is None
        can_start = has_sources and has_output and not is_running and space_ok
        self.btn_start.setEnabled(can_start)
        self.btn_add_zip.setEnabled(not is_running)
        self.btn_add_more.setEnabled(not is_running)
        self.btn_remove.setEnabled(len(self.sources) > 0 and not is_running)
        self.btn_choose_out.setEnabled(not is_running)
        self.btn_cancel.setVisible(is_running)
        self.btn_cancel.setEnabled(is_running)

    def _disk_preflight_message(self) -> str | None:
        if not self.output_dir or not self.sources:
            return None
        try:
            estimate = sum(p.stat().st_size for p in self.sources) * 2.5
            free = shutil.disk_usage(self.output_dir).free
        except OSError:
            return None
        if free < estimate:
            self.lbl_stage.setText("輸出磁碟可用空間可能不足，請改用其他磁碟或清理空間後再試。")
            return "insufficient"
        if free < estimate * 1.2:
            self.lbl_stage.setText(f"可用空間較接近預估需求（約 {format_file_size(int(estimate))}），建議保留更多空間。")
        return None

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
        session = load_session(self.output_dir)
        if not (self.workflow_state == WorkflowState.RESUME_AVAILABLE and session):
            session = create_session(self.sources, self.output_dir)
        self.worker = WorkerThread(self.sources, self.output_dir, analyze_only=analyze_only, session=session)
        self.worker.stage_changed.connect(self._on_stage_changed)
        self.worker.progress_mode.connect(self._on_progress_mode)
        self.worker.finished_success.connect(self._on_finished_success)
        self.worker.finished_error.connect(self._on_finished_error)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.progress_changed.connect(self._on_progress)
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

    def _on_progress(self, stage: str, current: int, total: int, filename: str) -> None:
        self.progress_bar.setRange(0, max(1, total))
        self.progress_bar.setValue(current)
        label = "正在整理照片與影片" if stage == "EXPORT" else "正在驗證檔案"
        self.lbl_stage.setText(f"{label}：{current} / {total}")
        self.lbl_current_file.setText(f"目前：{filename}")
        self.lbl_current_file.setToolTip(filename)

    def _request_cancel(self) -> None:
        if not self.worker:
            return
        reply = QMessageBox.question(self, "確認取消", "目前正在整理資料，確定要取消嗎？\n\n已完成的檔案會保留，原始 Takeout 不會受到影響，之後可以繼續未完成的整理。", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.worker.request_cancel()
            self.workflow_state = WorkflowState.CANCEL_REQUESTED
            self.lbl_stage.setText("正在安全停止，請稍候…")
            self.btn_cancel.setEnabled(False)

    def _on_cancelled(self, data: dict) -> None:
        self.worker = None
        self.workflow_state = WorkflowState.CANCELLED
        self.lbl_stage.setText("整理已取消，可稍後繼續。")
        self._update_action_state()
        if self.pending_close:
            self.close()

    def _detect_resume(self) -> None:
        if not self.output_dir:
            return
        session = load_session(self.output_dir)
        if not is_incomplete_session(session):
            return
        if not sources_match(session):
            QMessageBox.warning(self, "無法續作", "來源 Takeout ZIP 與上次整理工作不同，無法安全繼續。")
            return
        resumed_sources = [Path(str(item["path"])) for item in session["sources"]]
        self.sources = []
        self.src_list.clear()
        self._add_zip_paths(resumed_sources)
        self.workflow_state = WorkflowState.RESUME_AVAILABLE
        reply = QMessageBox.question(self, "偵測到未完成工作", "偵測到上次未完成的整理工作。\n\n選擇「是」繼續上次整理；選擇「否」重新開始（不會刪除既有輸出）。", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes)
        if reply == QMessageBox.StandardButton.Yes:
            self._start_task()
        else:
            self.workflow_state = WorkflowState.READY

    def dragEnterEvent(self, event: Any) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: Any) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        added, ignored = self._add_zip_paths(paths)
        if not added:
            QMessageBox.information(self, "拖曳 ZIP", "僅支援 Google Takeout ZIP 檔案。")
        elif ignored:
            QMessageBox.information(self, "拖曳 ZIP", f"已忽略 {ignored} 個非 ZIP 檔案。")
        event.acceptProposedAction()

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
        self.workflow_state = WorkflowState.COMPLETED if verification and verification.get("result") == "PASS" else WorkflowState.FAILED
        self.btn_next_batch.setVisible(not is_analyze)
        self.btn_clear_temp.setVisible(self.workflow_state == WorkflowState.COMPLETED and safe_temp_target(self.output_dir) is not None)

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
        self.workflow_state = WorkflowState.FAILED
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
        msg_box.setText(message if message.startswith("偵測到既有") else f"處理過程中發生錯誤：\n{message}")
        msg_box.setInformativeText("已將錯誤記錄保存至工作日誌。若需要排查問題，請點擊下方「顯示詳細資料」。")
        msg_box.setDetailedText(traceback_str)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

    def _reset_next_batch(self) -> None:
        self.sources.clear()
        self.src_list.clear()
        self.output_dir = None
        self.txt_output.clear()
        self.last_work_dir = None
        self.last_summary = None
        self.workflow_state = WorkflowState.READY
        self.lbl_stage.setText("就緒")
        self.lbl_current_file.clear()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self._update_stepper(0)
        self.widget_res_details.hide()
        self.lbl_res_placeholder.show()
        self._update_source_status()
        self._update_action_state()

    def _clear_temp(self) -> None:
        if self.workflow_state != WorkflowState.COMPLETED or not self.output_dir:
            return
        target = safe_temp_target(self.output_dir)
        if not target or not target.exists():
            self.btn_clear_temp.hide()
            return
        reply = QMessageBox.question(self, "清除暫存資料", "確定要清除本次整理的暫存資料嗎？\n\n清除後可釋放磁碟空間，但將無法再使用「繼續上次整理」功能。\n已整理完成的照片、影片、中繼資料與驗證報告不會被刪除。", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            shutil.rmtree(target)
        except OSError:
            QMessageBox.warning(self, "清除暫存資料", "部分暫存資料無法刪除，請關閉正在使用的檔案後再試。")
            return
        self.btn_clear_temp.hide()
        self.lbl_stage.setText("✓ 整理完成（暫存資料已清除）")

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
                self, "確認關閉",
                "目前正在整理資料。\n\n若現在停止，已完成檔案會保留，下次可以繼續未完成工作。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.pending_close = True
                self.worker.request_cancel()
                self.lbl_stage.setText("正在安全停止，請稍候…")
                event.ignore()
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
