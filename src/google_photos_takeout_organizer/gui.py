from __future__ import annotations
import os
import sys
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
    stage_changed = Signal(str)
    progress_mode = Signal(bool)
    finished_success = Signal(dict)
    finished_error = Signal(str, str)

    def __init__(self, sources: list[Path], output_dir: Path, analyze_only: bool = False) -> None:
        super().__init__()
        self.sources = sources
        self.output_dir = output_dir
        self.analyze_only = analyze_only
        self._is_cancelled = False

    def run(self) -> None:
        try:
            work_dir = self.output_dir / ".gpto_work"
            
            self.stage_changed.emit("正在分析資料...")
            self.progress_mode.emit(True)
            manifest = analyze(self.sources, work_dir)
            
            if self.analyze_only:
                self.stage_changed.emit("分析完成")
                self.progress_mode.emit(False)
                self.finished_success.emit({"manifest": manifest, "analyze_only": True, "work_dir": str(work_dir)})
                return

            if self._is_cancelled:
                return

            self.stage_changed.emit("正在整理檔案...")
            export_result = export(work_dir / "manifest.json", self.output_dir)

            if self._is_cancelled:
                return

            self.stage_changed.emit("正在驗證結果...")
            verify_result = verify(self.output_dir / "manifest.json", self.output_dir)

            self.stage_changed.emit("整理完成")
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
            self.finished_error.emit(str(exc), tb)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Google 相簿 Takeout 整理工具")
        self.resize(780, 680)

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
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(14, 14, 14, 14)

        # 標題與說明
        header_layout = QVBoxLayout()
        lbl_title = QLabel("Google 相簿 Takeout 整理工具", self)
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        lbl_subtitle = QLabel("將 Google Takeout 照片安全整理成依日期分類的資料夾", self)
        lbl_subtitle.setStyleSheet("color: #666; font-size: 12px;")
        header_layout.addWidget(lbl_title)
        header_layout.addWidget(lbl_subtitle)
        main_layout.addLayout(header_layout)

        # ① Takeout 來源檔案
        src_group = QGroupBox("① Takeout 來源檔案", self)
        src_layout = QVBoxLayout(src_group)

        self.src_list = QListWidget(self)
        self.src_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.src_list.setFixedHeight(120)
        src_layout.addWidget(self.src_list)

        src_bottom_layout = QHBoxLayout()
        self.btn_add_zip = QPushButton("選擇 ZIP", self)
        self.btn_add_zip.clicked.connect(self._choose_zips)
        src_bottom_layout.addWidget(self.btn_add_zip)

        self.btn_add_more = QPushButton("加入更多", self)
        self.btn_add_more.clicked.connect(self._choose_zips)
        src_bottom_layout.addWidget(self.btn_add_more)

        self.btn_remove = QPushButton("移除", self)
        self.btn_remove.clicked.connect(self._remove_selected)
        src_bottom_layout.addWidget(self.btn_remove)

        src_bottom_layout.addStretch()

        self.lbl_src_status = QLabel("尚未選取檔案", self)
        self.lbl_src_status.setStyleSheet("color: #666;")
        src_bottom_layout.addWidget(self.lbl_src_status)

        src_layout.addLayout(src_bottom_layout)
        main_layout.addWidget(src_group)

        # ② 整理到 (輸出位置)
        out_group = QGroupBox("② 整理到", self)
        out_layout = QHBoxLayout(out_group)

        self.txt_output = QLineEdit(self)
        self.txt_output.setReadOnly(True)
        self.txt_output.setPlaceholderText("請選擇整理後檔案的存放資料夾...")
        out_layout.addWidget(self.txt_output)

        self.btn_choose_out = QPushButton("選擇", self)
        self.btn_choose_out.clicked.connect(self._choose_output)
        out_layout.addWidget(self.btn_choose_out)

        main_layout.addWidget(out_group)

        # 安全提示
        lbl_safety = QLabel("☑ 原始 Takeout 不會被移動或刪除", self)
        lbl_safety.setStyleSheet("color: #2e7d32; font-weight: bold; margin: 4px 0;")
        main_layout.addWidget(lbl_safety)

        # 主要 CTA 操作按鈕 (置中突顯)
        cta_layout = QHBoxLayout()
        cta_layout.addStretch()
        self.btn_start = QPushButton("開始整理", self)
        self.btn_start.setFixedHeight(40)
        self.btn_start.setMinimumWidth(220)
        self.btn_start.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.btn_start.clicked.connect(lambda: self._start_task(analyze_only=False))
        cta_layout.addWidget(self.btn_start)
        cta_layout.addStretch()
        main_layout.addLayout(cta_layout)

        # 處理進度
        progress_group = QGroupBox("處理進度", self)
        prog_layout = QVBoxLayout(progress_group)

        self.lbl_stage = QLabel("就緒", self)
        self.lbl_stage.setStyleSheet("font-weight: 500;")
        prog_layout.addWidget(self.lbl_stage)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        prog_layout.addWidget(self.progress_bar)

        self.lbl_steps = QLabel("分析資料  ○      整理檔案  ○      驗證結果  ○", self)
        self.lbl_steps.setStyleSheet("color: #666;")
        prog_layout.addWidget(self.lbl_steps)

        main_layout.addWidget(progress_group)

        # 整理結果
        res_group = QGroupBox("整理結果", self)
        res_layout = QVBoxLayout(res_group)

        self.txt_summary = QTextEdit(self)
        self.txt_summary.setReadOnly(True)
        self.txt_summary.setFixedHeight(100)
        self.txt_summary.setPlaceholderText("完成整理後，將在此顯示照片、影片、中繼資料與驗證統計...")
        res_layout.addWidget(self.txt_summary)

        # 完成後快速操作
        quick_layout = QHBoxLayout()
        self.btn_open_out = QPushButton("開啟整理結果", self)
        self.btn_open_out.setEnabled(False)
        self.btn_open_out.clicked.connect(self._open_output_dir)
        quick_layout.addWidget(self.btn_open_out)

        self.btn_open_review = QPushButton("開啟人工確認", self)
        self.btn_open_review.setEnabled(False)
        self.btn_open_review.clicked.connect(self._open_review_dir)
        quick_layout.addWidget(self.btn_open_review)

        self.btn_open_report = QPushButton("查看詳細報告", self)
        self.btn_open_report.setEnabled(False)
        self.btn_open_report.clicked.connect(self._open_report_file)
        quick_layout.addWidget(self.btn_open_report)
        quick_layout.addStretch()

        res_layout.addLayout(quick_layout)
        main_layout.addWidget(res_group)


    def _choose_zips(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "選擇 Google Takeout ZIP 檔案",
            "",
            "Takeout ZIP 壓縮檔 (*.zip)",
        )
        if not files:
            return
        
        added_count = 0
        for f in files:
            p = Path(f).resolve()
            if p not in self.sources and p.is_file() and p.suffix.lower() == ".zip":
                self.sources.append(p)
                size_str = format_file_size(p.stat().st_size)
                item = QListWidgetItem(f"{p.name} ({size_str})")
                item.setData(Qt.ItemDataRole.UserRole, str(p))
                self.src_list.addItem(item)
                added_count += 1
        
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

    def _clear_all(self) -> None:
        self.sources.clear()
        self.src_list.clear()
        self._update_source_status()
        self._update_action_state()

    def _update_source_status(self) -> None:
        count = len(self.sources)
        if count == 0:
            self.lbl_src_status.setText("尚未選取任何 Takeout ZIP")
            self.lbl_src_status.setStyleSheet("color: #666;")
        elif count == 1:
            self.lbl_src_status.setText(
                "已選取 1 個 Takeout ZIP。（提示：如果這批 Google Takeout 有多個分卷，建議一次選取所有 ZIP，以提高中繼資料配對完整度。）"
            )
            self.lbl_src_status.setStyleSheet("color: #b78103;")
        else:
            self.lbl_src_status.setText(f"已選取 {count} 個 Takeout ZIP。")
            self.lbl_src_status.setStyleSheet("color: #2e7d32; font-weight: bold;")

    def _choose_output(self) -> None:
        dir_selected = QFileDialog.getExistingDirectory(self, "選擇輸出資料夾")
        if dir_selected:
            self.output_dir = Path(dir_selected).resolve()
            self.txt_output.setText(str(self.output_dir))
            self._update_action_state()

    def _update_action_state(self) -> None:
        is_running = self.worker is not None and self.worker.isRunning()
        has_sources = len(self.sources) > 0
        has_output = self.output_dir is not None

        can_start = has_sources and has_output and not is_running
        self.btn_start.setEnabled(can_start)
        self.btn_add_zip.setEnabled(not is_running)
        self.btn_add_more.setEnabled(not is_running)
        self.btn_remove.setEnabled(not is_running)
        self.btn_choose_out.setEnabled(not is_running)

    def _start_task(self, analyze_only: bool = False) -> None:
        err = validate_paths(self.sources, self.output_dir)
        if err:
            QMessageBox.warning(self, "路徑檢查", err)
            return

        self._update_action_state()
        self.txt_summary.clear()
        self.btn_open_out.setEnabled(False)
        self.btn_open_review.setEnabled(False)
        self.btn_open_report.setEnabled(False)
        self.lbl_steps.setText("分析資料  ●      整理檔案  ○      驗證結果  ○")

        assert self.output_dir is not None
        self.worker = WorkerThread(self.sources, self.output_dir, analyze_only=analyze_only)
        self.worker.stage_changed.connect(self._on_stage_changed)
        self.worker.progress_mode.connect(self._on_progress_mode)
        self.worker.finished_success.connect(self._on_finished_success)
        self.worker.finished_error.connect(self._on_finished_error)
        self.worker.start()
        self._update_action_state()

    def _on_stage_changed(self, text: str) -> None:
        self.lbl_stage.setText(text)
        if "分析" in text:
            self.lbl_steps.setText("分析資料  ●      整理檔案  ○      驗證結果  ○")
        elif "整理" in text and "完成" not in text:
            self.lbl_steps.setText("分析資料  ✓      整理檔案  ●      驗證結果  ○")
        elif "驗證" in text:
            self.lbl_steps.setText("分析資料  ✓      整理檔案  ✓      驗證結果  ●")
        elif "完成" in text:
            self.lbl_steps.setText("分析資料  ✓      整理檔案  ✓      驗證結果  ✓")

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
            review_dir = self.output_dir / "Review"
            if review_dir.exists():
                review_count = sum(1 for p in review_dir.rglob("*") if p.is_file())
        else:
            review_count = sum(
                1 for r in manifest.get("media_records", [])
                if r.get("planned_output_path", "").startswith("Review/")
            )

        lines = [
            f"照片 {summary.get('photos', 0)}       影片 {summary.get('videos', 0)}       中繼資料 {summary.get('json_matched', 0)}",
        ]

        if verification:
            v_ok = verification.get("verified", 0)
            v_fail = verification.get("failed", 0)
            if verification.get("result") == "PASS":
                lines.append(f"✓ 驗證成功 {v_ok}             ⚠ 需確認 {review_count}")
            else:
                lines.append(f"⚠ 驗證異常 (失敗 {v_fail} / 成功 {v_ok})     需確認 {review_count}")
        else:
            lines.append(f"狀態：{title_msg}             需確認 {review_count}")

        if summary.get("unknown_date", 0) > 0:
            lines.append(f"無法判定日期：{summary.get('unknown_date', 0)}")

        self.txt_summary.setText("\n".join(lines))


        if not is_analyze and self.output_dir and self.output_dir.exists():
            self.btn_open_out.setEnabled(True)
        if review_count > 0:
            self.btn_open_review.setEnabled(True)
        else:
            self.btn_open_review.setEnabled(False)

        report_file = work_dir / "report.html"
        if report_file.exists():
            self.btn_open_report.setEnabled(True)

        if verification and verification.get("result") != "PASS":
            QMessageBox.critical(
                self,
                "驗證警示",
                "整理已完成，但完整性驗證發現問題。\n請先查看詳細報告，不要刪除原始 Takeout 檔案！",
            )
        else:
            QMessageBox.information(self, "完成", f"Google Takeout {title_msg}！")

    def _on_finished_error(self, message: str, traceback_str: str) -> None:
        self.worker = None
        self._update_action_state()
        self.lbl_stage.setText("處理失敗")

        try:
            log_dir = self.output_dir or Path.cwd()
            err_log = log_dir / "organizer_error.log"
            err_log.write_text(traceback_str, encoding="utf-8")
        except Exception:
            pass

        QMessageBox.critical(
            self,
            "處理錯誤",
            f"處理過程中發生錯誤：\n{message}\n\n已將詳細錯誤記錄保存至工作日誌。",
        )

    def _open_output_dir(self) -> None:
        if self.output_dir and self.output_dir.exists():
            if sys.platform == "win32":
                os.startfile(str(self.output_dir))
            else:
                webbrowser.open(self.output_dir.as_uri())

    def _open_review_dir(self) -> None:
        if self.output_dir:
            review_dir = self.output_dir / "Review"
            if review_dir.exists():
                if sys.platform == "win32":
                    os.startfile(str(review_dir))
                else:
                    webbrowser.open(review_dir.as_uri())
            else:
                QMessageBox.information(self, "人工確認", "本次整理無需要人工確認的項目。")

    def _open_report_file(self) -> None:
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

