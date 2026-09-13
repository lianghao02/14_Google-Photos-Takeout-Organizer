from __future__ import annotations
import os
import sys
import time
import shutil
import webbrowser
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QFontMetrics, QDragEnterEvent, QDropEvent, QIcon
from PySide6.QtWidgets import (
    QScrollArea,
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedLayout,
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

APP_STYLESHEET = """
QMainWindow, QWidget#centralWidget {
    background-color: #F8FAFC;
    font-family: "Microsoft JhengHei UI", "Segoe UI", sans-serif;
    color: #1E293B;
}

QWidget#contentContainer {
    background-color: transparent;
}
QScrollArea {
    border: none;
    background-color: transparent;
}

QScrollArea > QWidget > QWidget {
    background-color: transparent;
}


QGroupBox {
    font-size: 13px;
    font-weight: bold;
    color: #1E293B;
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    margin-top: 12px;
    padding-top: 16px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    background-color: #FFFFFF;
}

QLineEdit {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 13px;
    color: #1E293B;
    min-height: 24px;
}

QLineEdit:focus {
    border-color: #2563EB;
}

QListWidget {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 4px;
    font-size: 12px;
    color: #1E293B;
}

QListWidget::item {
    padding: 4px 6px;
    border-radius: 4px;
}

QListWidget::item:selected {
    background-color: #EFF6FF;
    color: #1D4ED8;
}

QPushButton {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 500;
    color: #334155;
}

QPushButton:hover {
    background-color: #F1F5F9;
    border-color: #94A3B8;
    color: #0F172A;
}

QPushButton:pressed {
    background-color: #E2E8F0;
}

QPushButton:disabled {
    background-color: #F8FAFC;
    border-color: #E2E8F0;
    color: #94A3B8;
}

/* Primary CTA 按鈕 */
QPushButton#btn_start {
    background-color: #2563EB;
    border: 1px solid #1D4ED8;
    border-radius: 8px;
    color: #FFFFFF;
    font-size: 15px;
    font-weight: bold;
    padding: 8px 24px;
}

QPushButton#btn_start:hover {
    background-color: #1D4ED8;
    border-color: #1E40AF;
}

QPushButton#btn_start:pressed {
    background-color: #1E40AF;
}

QPushButton#btn_start:disabled {
    background-color: #93C5FD;
    border-color: #BFDBFE;
    color: #FFFFFF;
}

/* 取消整理按鈕（白底紅字細邊） */
QPushButton#btn_cancel {
    background-color: #FFFFFF;
    border: 1px solid #DC2626;
    border-radius: 6px;
    color: #DC2626;
    font-weight: 600;
    padding: 6px 16px;
}

QPushButton#btn_cancel:hover {
    background-color: #FEF2F2;
    border-color: #B91C1C;
    color: #B91C1C;
}

QPushButton#btn_cancel:pressed {
    background-color: #FEE2E2;
}

QPushButton#btn_cancel:disabled {
    border-color: #FCA5A5;
    color: #FCA5A5;
    background-color: #FFFFFF;
}

/* 人工確認按鈕（柔和橘色醒目提示） */
QPushButton#btn_open_review {
    background-color: #FFFBEB;
    border: 1px solid #F59E0B;
    border-radius: 6px;
    color: #B45309;
    font-weight: 600;
}

QPushButton#btn_open_review:hover {
    background-color: #FEF3C7;
    border-color: #D97706;
    color: #92400E;
}

/* 進度條收斂 */
QProgressBar {
    background-color: #E2E8F0;
    border: none;
    border-radius: 4px;
    text-align: center;
}

QProgressBar::chunk {
    background-color: #2563EB;
    border-radius: 4px;
}
"""

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


def format_eta_text(remaining_seconds: float) -> str:
    remaining_int = max(0, int(round(remaining_seconds)))
    if remaining_int < 60:
        return "< 1 分鐘"
    hours = remaining_int // 3600
    minutes = (remaining_int % 3600) // 60
    seconds = remaining_int % 60
    if hours > 0:
        return f"{hours} 小時 {minutes} 分"
    elif minutes >= 5:
        return f"{minutes} 分鐘"
    else:
        return f"{minutes} 分 {seconds:02d} 秒"


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
        self.resize(880, 700)
        self.setMinimumSize(820, 640)

        # 載入應用程式與視窗圖示
        icon_path = Path(__file__).resolve().parent / "resources" / "app_icon.png"
        if not icon_path.exists():
            icon_path = Path(__file__).resolve().parent / "resources" / "app_icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.sources: list[Path] = []
        self.output_dir: Path | None = None
        self.worker: WorkerThread | None = None
        self.last_work_dir: Path | None = None
        self.last_summary: dict[str, Any] | None = None
        self.workflow_state = WorkflowState.READY
        self.pending_close = False
        self.setAcceptDrops(True)

        self._current_progress_stage: str | None = None
        self._stage_start_time: float = 0.0
        self._stage_start_current: int = 0
        self._last_progress_time: float = 0.0
        self._last_progress_current: int = 0
        self._smoothed_rate: float = 0.0

        self._init_ui()
        self.setStyleSheet(APP_STYLESHEET)
        self._update_action_state()

    def _init_ui(self) -> None:
        central_widget = QWidget(self)
        central_widget.setObjectName("centralWidget")
        self.setCentralWidget(central_widget)

        # 頂層佈局：內嵌平滑 QScrollArea，小視窗或筆電高縮放比下彈性滾動兜底 (方案 B)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        scroll_area = QScrollArea(central_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        root_layout.addWidget(scroll_area)

        scroll_content = QWidget()
        scroll_area.setWidget(scroll_content)

        # 水平置中外層佈局：全螢幕/寬螢幕時自動將卡片內容約束在 840px 居中 (方案 A)
        outer_layout = QHBoxLayout(scroll_content)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        outer_layout.addStretch(1)

        content_container = QWidget(scroll_content)
        content_container.setObjectName("contentContainer")
        content_container.setMaximumWidth(840)

        main_layout = QVBoxLayout(content_container)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(24, 20, 24, 20)

        # 1. 標題與說明 (Header)
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        lbl_title = QLabel("Google 相簿 Takeout 整理工具", self)
        lbl_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #0F172A;")
        lbl_subtitle = QLabel("安全解析 Takeout 壓縮檔，依拍攝日期與中繼資料自動分類歸檔", self)
        lbl_subtitle.setStyleSheet("color: #64748B; font-size: 13px;")
        header_layout.addWidget(lbl_title)
        header_layout.addWidget(lbl_subtitle)
        main_layout.addLayout(header_layout)

        # 2. 來源檔案區塊
        self.src_group = QGroupBox("來源 Takeout ZIP", self)
        src_layout = QVBoxLayout(self.src_group)
        src_layout.setSpacing(10)
        src_layout.setContentsMargins(16, 14, 16, 14)

        # 來源列表與拖曳空狀態提示卡片 (採用 QStackedLayout 徹底解決小視窗水平截斷問題)
        list_container = QWidget(self)
        self.list_stack = QStackedLayout(list_container)
        self.list_stack.setContentsMargins(0, 0, 0, 0)

        # 現代化虛線拖曳卡片（空狀態時呈現，滿版自適應寬度，支援點擊選檔）
        self.lbl_empty_hint = QLabel(
            "📦  將 Google Takeout ZIP 拖曳至此\n\n或點擊「選擇 ZIP」加入檔案（支援多卷分卷自動合併）",
            self,
        )
        self.lbl_empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty_hint.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_empty_hint.setFixedHeight(120)
        self.lbl_empty_hint.setMinimumHeight(110)
        self.lbl_empty_hint.setStyleSheet("""
            QLabel {
                color: #475569;
                font-size: 13px;
                font-weight: 500;
                background-color: #F8FAFC;
                border: 2px dashed #CBD5E1;
                border-radius: 8px;
            }
            QLabel:hover {
                background-color: #EFF6FF;
                border-color: #3B82F6;
                color: #1D4ED8;
            }
        """)
        self.lbl_empty_hint.mousePressEvent = lambda e: self._choose_zips()

        self.src_list = QListWidget(self)
        self.src_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.src_list.setFixedHeight(120)
        self.src_list.setMinimumHeight(110)

        self.list_stack.addWidget(self.lbl_empty_hint)
        self.list_stack.addWidget(self.src_list)

        src_layout.addWidget(list_container)

        src_action_layout = QHBoxLayout()
        self.btn_add_zip = QPushButton("選擇 ZIP", self)
        self.btn_add_zip.clicked.connect(self._choose_zips)
        src_action_layout.addWidget(self.btn_add_zip)

        self.btn_add_more = QPushButton("加入更多", self)
        self.btn_add_more.clicked.connect(self._choose_zips)
        src_action_layout.addWidget(self.btn_add_more)

        self.btn_remove = QPushButton("移除選取", self)
        self.btn_remove.clicked.connect(self._remove_selected)
        src_action_layout.addWidget(self.btn_remove)

        src_action_layout.addSpacing(12)

        self.lbl_src_count = QLabel("尚未選取 ZIP", self)
        self.lbl_src_count.setStyleSheet("color: #475569; font-weight: 600; font-size: 12px;")
        src_action_layout.addWidget(self.lbl_src_count)

        src_action_layout.addStretch()
        src_layout.addLayout(src_action_layout)

        # 次要淡色提示文字 (拆行、小字、不搶焦點)
        self.lbl_src_hint = QLabel("💡 若同一次匯出有多個分卷 ZIP，建議一次全數選取，以確保跨分卷中繼資料配對最完整。", self)
        self.lbl_src_hint.setStyleSheet("color: #64748B; font-size: 11px; margin-top: 2px;")
        src_layout.addWidget(self.lbl_src_hint)

        main_layout.addWidget(self.src_group)

        # 3. 輸出位置區塊
        out_group = QGroupBox("輸出目標目錄", self)
        out_layout = QVBoxLayout(out_group)
        out_layout.setSpacing(10)
        out_layout.setContentsMargins(16, 14, 16, 14)

        out_input_layout = QHBoxLayout()
        out_input_layout.setSpacing(8)
        self.txt_output = QLineEdit(self)
        self.txt_output.setReadOnly(True)
        self.txt_output.setPlaceholderText("請選擇整理後照片庫的存放目錄...")
        out_input_layout.addWidget(self.txt_output)

        self.btn_choose_out = QPushButton("選擇資料夾", self)
        self.btn_choose_out.setFixedWidth(100)
        self.btn_choose_out.clicked.connect(self._choose_output)
        out_input_layout.addWidget(self.btn_choose_out)
        out_layout.addLayout(out_input_layout)

        # 磁碟空間預檢即時顯示 (未選輸出時預設不顯示)
        self.lbl_disk_info = QLabel("", self)
        self.lbl_disk_info.setStyleSheet("font-size: 12px; color: #64748B;")
        self.lbl_disk_info.hide()
        out_layout.addWidget(self.lbl_disk_info)

        # 安全提示 (整合於輸出卡片底部，明確有安全感)
        lbl_safety = QLabel("✓ 原始 Takeout 壓縮檔安全保留，不會被移動、修改或刪除", self)
        lbl_safety.setStyleSheet("color: #16A34A; font-weight: bold; font-size: 12px;")
        out_layout.addWidget(lbl_safety)

        main_layout.addWidget(out_group)

        # 4. 主要操作按鈕 (唯一 Primary CTA，置中突顯)
        cta_layout = QHBoxLayout()
        cta_layout.addStretch()
        self.btn_start = QPushButton("開始整理照片與影片", self)
        self.btn_start.setObjectName("btn_start")
        self.btn_start.setFixedHeight(46)
        self.btn_start.setMinimumWidth(280)
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.clicked.connect(lambda: self._start_task(analyze_only=False))
        cta_layout.addWidget(self.btn_start)
        cta_layout.addStretch()
        main_layout.addLayout(cta_layout)

        # 5. 處理進度區塊 (平時隱藏，點擊開始整理後即時展現)
        self.progress_group = QGroupBox("處理進度", self)
        prog_layout = QVBoxLayout(self.progress_group)
        prog_layout.setSpacing(10)
        prog_layout.setContentsMargins(16, 14, 16, 14)

        # Stepper 頂部列（含流程指示與右側取消按鈕）
        stepper_bar_layout = QHBoxLayout()
        self.lbl_stepper = QLabel(self)
        self._update_stepper(stage=0)
        stepper_bar_layout.addWidget(self.lbl_stepper)
        stepper_bar_layout.addStretch()

        self.btn_cancel = QPushButton("取消整理", self)
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setFixedHeight(28)
        self.btn_cancel.clicked.connect(self._request_cancel)
        self.btn_cancel.hide()
        stepper_bar_layout.addWidget(self.btn_cancel)
        prog_layout.addLayout(stepper_bar_layout)

        # 第一行：階段名稱與百分比
        self.lbl_stage = QLabel("就緒", self)
        self.lbl_stage.setStyleSheet("color: #1E293B; font-size: 13px; font-weight: 600;")
        prog_layout.addWidget(self.lbl_stage)

        # 第二行：進度條（8px 高度，圓角 4px）
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        prog_layout.addWidget(self.progress_bar)

        # 第三行：左側數量與剩餘時間、下方/右側當前檔案（Middle-Elide）
        prog_detail_layout = QVBoxLayout()
        prog_detail_layout.setSpacing(2)

        self.lbl_prog_stats = QLabel("", self)
        self.lbl_prog_stats.setStyleSheet("color: #475569; font-size: 12px; font-weight: 500;")
        prog_detail_layout.addWidget(self.lbl_prog_stats)

        self.lbl_current_file = QLabel("", self)
        self.lbl_current_file.setStyleSheet("color: #64748B; font-size: 11px;")
        self.lbl_current_file.setToolTip("")
        prog_detail_layout.addWidget(self.lbl_current_file)
        prog_layout.addLayout(prog_detail_layout)

        main_layout.addWidget(self.progress_group)
        self.progress_group.hide()

        # 6. 整理結果區塊 (平時隱藏，整理完成後展開呈現)
        self.res_group = QGroupBox("整理結果", self)
        self.res_layout = QVBoxLayout(self.res_group)
        self.res_layout.setSpacing(10)
        self.res_layout.setContentsMargins(16, 14, 16, 14)

        # 提示文字元件（保留相容性）
        self.lbl_res_placeholder = QLabel("完成整理後，這裡會顯示檔案統計與完整性校驗報告。", self)
        self.lbl_res_placeholder.setStyleSheet("color: #94A3B8; font-size: 12px;")
        self.res_layout.addWidget(self.lbl_res_placeholder)
        self.lbl_res_placeholder.hide()
        self.res_group.hide()

        # 完成後展開的詳細內容元件
        self.widget_res_details = QWidget(self)
        details_layout = QVBoxLayout(self.widget_res_details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(10)

        # Compact summary pills container
        self.summary_pills_layout = QHBoxLayout()
        self.summary_pills_layout.setSpacing(8)
        details_layout.addLayout(self.summary_pills_layout)

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
        self.btn_open_review.setObjectName("btn_open_review")
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

        # 底部留白彈性伸縮，避免視窗拉高時卡片被強行撐大
        main_layout.addStretch(1)

        outer_layout.addWidget(content_container)
        outer_layout.addStretch(1)

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

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)

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
            if hasattr(self, "btn_add_more"):
                self.btn_add_more.setEnabled(False)
            if hasattr(self, "list_stack"):
                self.list_stack.setCurrentIndex(0)
            if hasattr(self, "lbl_empty_hint"):
                self.lbl_empty_hint.show()
            if hasattr(self, "src_list"):
                self.src_list.hide()
        else:
            total_bytes = sum(p.stat().st_size for p in self.sources if p.exists())
            size_str = format_file_size(total_bytes)
            if count == 1:
                self.lbl_src_count.setText(f"已選取 1 個 ZIP（{size_str}）")
            else:
                self.lbl_src_count.setText(f"已選取 {count} 個 ZIP（共 {size_str}）")
            self.btn_remove.setEnabled(True)
            if hasattr(self, "btn_add_more"):
                self.btn_add_more.setEnabled(True)
            if hasattr(self, "list_stack"):
                self.list_stack.setCurrentIndex(1)
            if hasattr(self, "src_list"):
                self.src_list.show()
            if hasattr(self, "lbl_empty_hint"):
                self.lbl_empty_hint.hide()

    def _choose_output(self) -> None:
        dir_selected = QFileDialog.getExistingDirectory(self, "選擇輸出位置")
        if dir_selected:
            self.output_dir = Path(dir_selected).resolve()
            self.txt_output.setText(str(self.output_dir))
            self.txt_output.setToolTip(str(self.output_dir))
            self._detect_resume()
            self._update_action_state()

    def _disk_preflight_message(self) -> str | None:
        if not self.output_dir or not self.sources:
            if hasattr(self, "lbl_disk_info"):
                self.lbl_disk_info.hide()
            return None
        try:
            total_zip_bytes = sum(p.stat().st_size for p in self.sources)
            estimate = total_zip_bytes * 2.5
            free = shutil.disk_usage(self.output_dir).free
        except OSError:
            if hasattr(self, "lbl_disk_info"):
                self.lbl_disk_info.hide()
            return None

        zip_str = format_file_size(total_zip_bytes)
        req_str = format_file_size(int(estimate))
        free_str = format_file_size(free)

        if free < estimate:
            text = (
                f"來源 ZIP：約 {zip_str} · 預估需求：約 {req_str} · 可用空間：{free_str} · "
                f"<span style='color: #DC2626; font-weight: bold;'>✕ 空間不足</span>"
                f"<br><span style='font-size: 10px; color: #94A3B8;'>預估值僅供參考，實際需求會依壓縮比例而不同。</span>"
            )
            self.lbl_disk_info.setText(text)
            self.lbl_disk_info.show()
            return "insufficient"
        elif free < estimate * 1.2:
            text = (
                f"來源 ZIP：約 {zip_str} · 預估需求：約 {req_str} · 可用空間：{free_str} · "
                f"<span style='color: #D97706; font-weight: bold;'>⚠ 空間較接近門檻</span>"
                f"<br><span style='font-size: 10px; color: #94A3B8;'>預估值僅供參考，實際需求會依壓縮比例而不同。</span>"
            )
            self.lbl_disk_info.setText(text)
            self.lbl_disk_info.show()
            return None
        else:
            text = (
                f"來源 ZIP：約 {zip_str} · 預估需求：約 {req_str} · 可用空間：{free_str} · "
                f"<span style='color: #16A34A; font-weight: bold;'>✓ 空間充足</span>"
                f"<br><span style='font-size: 10px; color: #94A3B8;'>預估值僅供參考，實際需求會依壓縮比例而不同。</span>"
            )
            self.lbl_disk_info.setText(text)
            self.lbl_disk_info.show()
            return None

    def _update_action_state(self) -> None:
        is_running = self.worker is not None and self.worker.isRunning()
        has_sources = len(self.sources) > 0
        has_output = self.output_dir is not None

        disk_err = self._disk_preflight_message()
        space_ok = disk_err is None
        can_start = has_sources and has_output and not is_running and space_ok

        self.btn_start.setEnabled(can_start)
        if is_running:
            self.btn_start.setToolTip("正在整理中...")
        elif not has_sources:
            self.btn_start.setToolTip("請先加入 Takeout ZIP。")
        elif not has_output:
            self.btn_start.setToolTip("請先選擇輸出位置。")
        elif not space_ok:
            self.btn_start.setToolTip("輸出磁碟可用空間不足。")
        else:
            self.btn_start.setToolTip("開始整理照片與影片")

        self.btn_add_zip.setEnabled(not is_running)
        self.btn_add_more.setEnabled(not is_running)
        self.btn_remove.setEnabled(len(self.sources) > 0 and not is_running)
        self.btn_choose_out.setEnabled(not is_running)
        self.btn_cancel.setVisible(is_running)
        self.btn_cancel.setEnabled(is_running)

    def _start_task(self, analyze_only: bool = False) -> None:
        err = validate_paths(self.sources, self.output_dir)
        if err:
            QMessageBox.warning(self, "路徑檢查", err)
            return

        self._update_action_state()
        if hasattr(self, "progress_group"):
            self.progress_group.show()
        if hasattr(self, "res_group"):
            self.res_group.hide()
        self.lbl_res_placeholder.hide()
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

        now = time.time()
        if self._current_progress_stage != stage:
            self._current_progress_stage = stage
            self._stage_start_time = now
            self._stage_start_current = current
            self._last_progress_time = now
            self._last_progress_current = current
            self._smoothed_rate = 0.0

        elapsed_total = now - self._stage_start_time
        processed_in_stage = max(0, current - self._stage_start_current)
        remaining = max(0, total - current)

        eta_str = ""
        if remaining == 0:
            eta_str = ""
        elif elapsed_total < 3.0 or processed_in_stage < 3:
            eta_str = " · 預估時間計算中…"
        else:
            # 計算即時速率並以 EMA 平滑處理，避免檔案大小不同造成劇烈晃動
            dt = now - self._last_progress_time
            d_items = current - self._last_progress_current
            if dt >= 0.5 and d_items >= 0:
                instant_rate = d_items / dt
                if self._smoothed_rate <= 0.0:
                    self._smoothed_rate = instant_rate
                else:
                    self._smoothed_rate = (0.7 * self._smoothed_rate) + (0.3 * instant_rate)
                self._last_progress_time = now
                self._last_progress_current = current

            effective_rate = self._smoothed_rate if self._smoothed_rate > 0.0 else (processed_in_stage / max(0.1, elapsed_total))
            if effective_rate > 0.01:
                eta_seconds = remaining / effective_rate
                eta_str = f" · 剩餘約 {format_eta_text(eta_seconds)}"

        pct = int(round((current / max(1, total)) * 100))
        self.lbl_stage.setText(f"{label} · {pct}%")

        stats_text = f"{current:,} / {total:,}{eta_str}"
        if hasattr(self, "lbl_prog_stats"):
            self.lbl_prog_stats.setText(stats_text)

        # 檔名以 Middle-Elide 截斷，避免長檔名撐寬視窗
        name_only = Path(filename).name if filename else ""
        if name_only:
            fm = QFontMetrics(self.lbl_current_file.font())
            avail_width = max(200, self.progress_bar.width() - 40)
            elided = fm.elidedText(f"目前：{name_only}", Qt.TextElideMode.ElideMiddle, avail_width)
            self.lbl_current_file.setText(elided)
        else:
            self.lbl_current_file.setText("")
        self.lbl_current_file.setToolTip(filename)

    def _request_cancel(self) -> None:
        if not self.worker:
            return
        reply = QMessageBox.question(self, "確認取消", "目前正在整理資料，確定要取消嗎？\n\n已完成的檔案會保留，原始 Takeout 不會受到影響，之後可以繼續未完成的整理。", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.worker.request_cancel()
            self.workflow_state = WorkflowState.CANCEL_REQUESTED
            self.lbl_stage.setText("取消已收到，將在目前檔案安全邊界停止…")
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
            if hasattr(self, "lbl_empty_hint") and len(self.sources) == 0:
                self.lbl_empty_hint.setText("放開滑鼠以加入 Takeout ZIP")
                self.lbl_empty_hint.setStyleSheet("""
                    QLabel {
                        color: #1D4ED8;
                        font-weight: bold;
                        font-size: 14px;
                        background-color: #DBEAFE;
                        border: 2px dashed #2563EB;
                        border-radius: 8px;
                    }
                """)

    def dragLeaveEvent(self, event: Any) -> None:
        if hasattr(self, "lbl_empty_hint") and len(self.sources) == 0:
            self.lbl_empty_hint.setText("📦  將 Google Takeout ZIP 拖曳至此\n\n或點擊「選擇 ZIP」加入檔案（支援多卷分卷自動合併）")
            self.lbl_empty_hint.setStyleSheet("""
                    QLabel {
                        color: #475569;
                        font-size: 13px;
                        font-weight: 500;
                        background-color: #F8FAFC;
                        border: 2px dashed #CBD5E1;
                        border-radius: 8px;
                    }
                    QLabel:hover {
                        background-color: #EFF6FF;
                        border-color: #3B82F6;
                        color: #1D4ED8;
                    }
                """)

    def dropEvent(self, event: Any) -> None:
        if hasattr(self, "lbl_empty_hint") and len(self.sources) == 0:
            self.lbl_empty_hint.setText("📦  將 Google Takeout ZIP 拖曳至此\n\n或點擊「選擇 ZIP」加入檔案（支援多卷分卷自動合併）")
            self.lbl_empty_hint.setStyleSheet("""
                    QLabel {
                        color: #475569;
                        font-size: 13px;
                        font-weight: 500;
                        background-color: #F8FAFC;
                        border: 2px dashed #CBD5E1;
                        border-radius: 8px;
                    }
                    QLabel:hover {
                        background-color: #EFF6FF;
                        border-color: #3B82F6;
                        color: #1D4ED8;
                    }
                """)

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
        if hasattr(self, "res_group"):
            self.res_group.show()
        self.lbl_res_placeholder.hide()
        self.widget_res_details.show()

        # 第一行：媒體統計
        photos = summary.get("photos", 0)
        videos = summary.get("videos", 0)
        matched_json = summary.get("json_matched", 0)

        # 建立簡潔的徽章/卡片風格資訊
        pill_style = "background-color: #F1F5F9; border: 1px solid #E2E8F0; border-radius: 6px; padding: 4px 10px; font-size: 12px; color: #334155;"
        self.lbl_stats_media.setText(
            f"<span style='{pill_style}'>照片 <b>{photos:,}</b></span>&nbsp;&nbsp;"
            f"<span style='{pill_style}'>影片 <b>{videos:,}</b></span>&nbsp;&nbsp;"
            f"<span style='{pill_style}'>中繼資料配對 <b>{matched_json:,}</b></span>"
        )

        # 第二行：驗證與人工確認
        if verification:
            v_ok = verification.get("verified", 0)
            v_fail = verification.get("failed", 0)
            if verification.get("result") == "PASS":
                v_pill_style = "background-color: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 6px; padding: 4px 10px; font-size: 12px; color: #166534;"
                v_text = f"<span style='{v_pill_style}'>✓ 完整性驗證通過 ({v_ok:,} 檔)</span>"
            else:
                v_pill_style = "background-color: #FEF2F2; border: 1px solid #FECACA; border-radius: 6px; padding: 4px 10px; font-size: 12px; color: #991B1B;"
                v_text = f"<span style='{v_pill_style}'>⚠ 驗證異常 (失敗 {v_fail:,} / 成功 {v_ok:,})</span>"
        else:
            v_text = f"<span style='{pill_style}'>狀態：{title_msg}</span>"

        if review_count > 0:
            r_pill_style = "background-color: #FFFBEB; border: 1px solid #FDE68A; border-radius: 6px; padding: 4px 10px; font-size: 12px; color: #92400E;"
            r_text = f"<span style='{r_pill_style}'>⚠ 待人工確認 <b>{review_count:,}</b></span>"
            self.btn_open_review.setText(f"開啟人工確認 ({review_count})")
            self.btn_open_review.show()
            self.btn_open_review.setEnabled(True)
        else:
            r_pill_style = "background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 4px 10px; font-size: 12px; color: #64748B;"
            r_text = f"<span style='{r_pill_style}'>✓ 無待確認項目</span>"
            self.btn_open_review.hide()

        self.lbl_stats_verify.setText(f"{v_text}&nbsp;&nbsp;{r_text}")

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
        self._current_progress_stage = None
        self._stage_start_time = 0.0
        self._stage_start_current = 0
        self._last_progress_time = 0.0
        self._last_progress_current = 0
        self._smoothed_rate = 0.0
        self.lbl_stage.setText("就緒")
        if hasattr(self, "lbl_prog_stats"):
            self.lbl_prog_stats.clear()
        self.lbl_current_file.clear()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self._update_stepper(0)
        self.widget_res_details.hide()
        self.lbl_res_placeholder.hide()
        if hasattr(self, "progress_group"):
            self.progress_group.hide()
        if hasattr(self, "res_group"):
            self.res_group.hide()
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

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            # 只要包含任何本地檔案即可接受拖曳
            if any(u.isLocalFile() for u in urls):
                event.acceptProposedAction()
                if hasattr(self, "lbl_empty_hint") and self.lbl_empty_hint.isVisible():
                    self.lbl_empty_hint.setStyleSheet("""
                        QLabel {
                            color: #1D4ED8;
                            font-size: 13px;
                            font-weight: 600;
                            background-color: #EFF6FF;
                            border: 2px dashed #3B82F6;
                            border-radius: 8px;
                        }
                    """)
                return
        event.ignore()

    def dragLeaveEvent(self, event: Any) -> None:
        if hasattr(self, "lbl_empty_hint") and self.lbl_empty_hint.isVisible():
            self.lbl_empty_hint.setStyleSheet("""
                QLabel {
                    color: #475569;
                    font-size: 13px;
                    font-weight: 500;
                    background-color: #F8FAFC;
                    border: 2px dashed #CBD5E1;
                    border-radius: 8px;
                }
                QLabel:hover {
                    background-color: #EFF6FF;
                    border-color: #3B82F6;
                    color: #1D4ED8;
                }
            """)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        if hasattr(self, "lbl_empty_hint"):
            self.lbl_empty_hint.setStyleSheet("""
                QLabel {
                    color: #475569;
                    font-size: 13px;
                    font-weight: 500;
                    background-color: #F8FAFC;
                    border: 2px dashed #CBD5E1;
                    border-radius: 8px;
                }
                QLabel:hover {
                    background-color: #EFF6FF;
                    border-color: #3B82F6;
                    color: #1D4ED8;
                }
            """)
        if event.mimeData().hasUrls():
            paths: list[Path] = []
            for u in event.mimeData().urls():
                if u.isLocalFile():
                    p = Path(u.toLocalFile())
                    paths.append(p)
            if paths:
                event.acceptProposedAction()
                added, ignored = self._add_zip_paths(paths)
                if ignored > 0 and added == 0:
                    QMessageBox.warning(self, "檔案格式不符", "僅支援 Google Takeout ZIP 壓縮檔。")
                return
        event.ignore()

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
                self.lbl_stage.setText("取消已收到，將在目前檔案安全邊界停止…")
                event.ignore()
            else:
                event.ignore()
        else:
            event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    icon_path = Path(__file__).resolve().parent / "resources" / "app_icon.png"
    if not icon_path.exists():
        icon_path = Path(__file__).resolve().parent / "resources" / "app_icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
