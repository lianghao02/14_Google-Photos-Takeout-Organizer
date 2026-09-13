# Changelog

## 1.1.0 (2026-09-13)

- **專屬應用程式圖示 (Icon)**：採用「極簡幾何微量磚」風格，為 Windows 桌面整合多解析度 `.ico` 與高畫質 PNG，視窗與執行檔皆具備專業辨識度。
- **UI/UX 響應式排版全面升級**：
  - 引進 `QStackedLayout`，徹底解決小視窗與初次啟動時拖曳提示虛線框被截斷的佈局問題。
  - 實作方案 A + B + C 綜合佈局：限制安全最小視窗大小（820x640）、內容置中收斂、內嵌平滑滾動兜底保護。
  - 導入漸進式揭露（Progressive Disclosure），整理前隱藏空白進度與結果卡片，保持畫面透氣與視覺聚焦。
  - 支援視窗與提示卡片直接拖放 ZIP 檔案加入整理。
- **大容量 Takeout 安全 Session 與中斷續作**：
  - 支援 session 型安全斷點續作與合作式取消機制（Cooperative Cancellation）。
  - 輸出目標與 Sidecar SHA-256 衝突防護，避免覆寫已存在之不一致檔案。
  - 新增動態預估剩餘時間（ETA）與檔名 Middle-Elide 截斷提示。
  - 磁碟空間預檢機制（自動評估 2.5 倍解壓與整理容量）。
  - 驗證通過後提供「清除暫存資料」安全按鈕，可一鍵釋放工作目錄磁碟空間。
- **啟動器與可攜性加固**：
  - 修正 `RUN.bat` 與 `start_gui.ps1` 跨環境啟動鏈，強制 UTF-8 編碼與路徑防護，消除 CMD 閃退問題。

## 1.0.1

- 修正 EXIF DateTimeOriginal 讀取方式（透過 Exif IFD 精確獲取真實拍攝時間，避免誤取檔案修改時間）。
- 修正 UTC 與本地時間（UTC+8）跨日時間差比對邏輯，消除假性日期衝突。
- 修正 Review 路由邏輯，確保待人工確認檔案依衝突類型分流，避免誤入未判定日期目錄。
- 匯出時全面支援 Sidecar JSON 隨媒體檔案以 Copy-only 方式同步保存。
- 全新 Windows 桌面繁體中文圖形介面 (PySide6)，採單視窗工作流程引導與流程 Stepper。
- 提供 Windows x64 免安裝綠色版 (Portable) 單一目錄發布包（無 CMD 黑色控制台視窗）。
- 強化 RUN.bat 自動偵測依賴與執行錯誤停留機制。
- 包含自動化 GUI 流程完整端到端 Smoke Test，經由真實 Takeout ZIP 回歸驗證通過。

## 1.0.0

- 正式完成 v1.0.0 發布，經由真實 Google Photos Takeout 多分卷（約 3GB、1,932 檔案樣本）完整驗證。
- 支援 Google Photos Takeout ZIP 檔案安全分析、歸檔預演與匯出規劃。
- 支援同批多個 Takeout ZIP 分卷集中輸入與跨分卷池化處理（Cross-Archive Pooling）。
- 正式支援 Takeout 主流 `.supplemental-metadata.json` Sidecar 檔名與各類 Takeout 編號變體（如 `DSCF0787(1).AVI` 對應 `DSCF0787.AVI.supplemental-metadata(1).json`）。
- 整合 EXIF、Sidecar JSON、檔名及目錄結構日期解析，具備多來源比對與日期衝突安全審閱分流機制。
- 支援 Apple HEIC 格式影像尺寸與 EXIF 拍攝時間萃取，並包含安全 Fallback 機制。
- Copy-only 安全檔案匯出模式，原始 Takeout 輸入資料嚴格維持唯讀無損。
- 內建 SHA-256 與檔案大小逐檔完整性驗證工具。
- 支援完全相同檔案之 SHA-256 去重與同名碰撞安全編號保護。
- 完整支援中文檔名、中文相簿路徑與各類長檔名。
- CLI 新增 `--version` 參數查詢。

## 0.1.0

- Initial safe Analyze, Export, Verify MVP.
