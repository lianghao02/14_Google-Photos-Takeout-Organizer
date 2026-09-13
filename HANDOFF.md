# HANDOFF

## 目前狀態
**可交付** — v1.1.0 已完整推送，所有功能正常，pytest 17/17 通過。

---

## 本輪目標
發布 v1.1.0：專屬 Icon、純腳本靜默啟動器（解決辦公室 exe 警告）、GUI 小視窗排版修復。

---

## 已完成

### GUI 排版
- QStackedLayout 管理提示卡片與來源清單，解決小視窗文字截斷問題
- A+B+C 綜合方案：最小視窗 820x640、最大內容寬度 840px 置中、QScrollArea 兜底
- 漸進式揭露（Progressive Disclosure）：進度與結果區整理前隱藏
- 視窗層級拖放：ZIP 可直接拖入主視窗（dragEnterEvent / dropEvent）
- 移除過時 resizeEvent 中的手動 setGeometry

### Icon
- 選用提案 C【極簡幾何微量磚】：深藍漸層底、ZIP 拉鍊＋四色相簿圖層
- resources/app_icon.png（1024x1024）、app_icon.ico（16/32/48/64/128/256 多解析度）
- gui.py 的 MainWindow.__init__ 與 main() 以 QIcon 掛載

### 版本升級
- pyproject.toml、__init__.py、service.py 均更新至 1.1.0
- CHANGELOG.md：新增 ## 1.1.0 (2026-09-13) 完整條目

### 啟動器
- RUN.bat：薄啟動器，以 -WindowStyle Hidden 背景靜默引動 scripts/start_gui.ps1
- scripts/start_gui.ps1：智慧偵測 .venv 或系統 Python、套件檢查、pythonw.exe 優先、bootstrap 加入 src 路徑
- UTF-8 BOM 修復：PS1 開頭補齊 BOM，解決 Windows PowerShell 5.1 中文字元解析崩潰（閃退）

### Git 發布
- Commit 44e7d00：fix(launcher): 補齊 UTF-8 BOM
- Commit 3eb8bd8：feat: 發布 v1.1.0 版本
- main 已推送至 origin
- tag v1.1.0 指向 44e7d00，已 force-push 至 remote

---

## 刻意未修改
- build_windows.ps1：PyInstaller 建置腳本保留但使用者不會用（辦公室環境限制）
- Python 語言選型：確認維持 Python（I/O 瓶頸非 CPU、HEIC 生態最成熟）
- 不打包 exe（辦公室電腦 SmartScreen 會跳出警告）

---

## 尚未完成
無。本輪需求全部完成。

---

## 驗證結果

### 已執行
- pytest -v：17/17 通過
- powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\start_gui.ps1：exit code 0，GUI 正常啟動
- RUN.bat 雙擊：靜默啟動，無閃退

### 尚未驗證
- 在全新 Python 環境（無 .venv）下的啟動器自動安裝流程

### 已知風險
- scripts/start_gui.ps1 若以不支援 BOM 的編輯器存檔，可能再次遺失 BOM，導致 PowerShell 5.1 閃退。
  建議使用 VS Code 或 Notepad++，確認存檔編碼為「UTF-8 with BOM」。

---

## Git 狀態
- Commit：44e7d00
- Push：是
- Working Tree：Clean
- Branch：main
- Tag：v1.1.0 -> 44e7d00（已 push）

---

## 下一步
無待辦事項。若需繼續開發，建議評估方向：
1. 批次整理速度優化（HEIC 轉換 I/O 瓶頸）
2. 多語系支援（繁體中文 UI 字串抽離為 i18n 資源）
3. 整理結果報告（HTML 或 CSV 輸出摘要）
