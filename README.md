# Google Photos Takeout Organizer

[繁體中文](README.zh-TW.md) | **English**

Safe, local, copy-only organization for Google Photos / Google Takeout ZIPs and folders. It generates a manifest and review report before exporting.

`Takeout → Analyze → Review → Export → Verify`

## 專案概念與開發原因

本工具把 Google Takeout 多分卷中的媒體及 Sidecar 轉成可核對的清冊與分類輸出。開發動機是下載後的檔案時間不一定等於拍攝時間，分卷又可能把媒體和中繼資料拆開，直接按檔案時間歸檔容易分類錯誤。

設計採「分析 → 人工確認 → 複製 → 雜湊驗證」，來源不改寫，輸出不重新壓縮影像或重寫 EXIF。它聚焦 Takeout 的安全歸檔；日期不明確就保留在人工確認區，而非猜一個日期。

**典型流程**：加入同批全部分卷 → 檢查來源與容量 → 整理 → 查看 Review／Unknown-Date → 核對 verification.json。

## Features

- **Copy-Only Safety**: Never modifies, moves, deletes, or overwrites original Takeout archives or folders. Original inputs remain 100% read-only.
- **Live Photo & RAW Pair Binding**: Automatically pairs iPhone Live Photos (`.HEIC` + `.MOV`) and DSLR RAW+JPEG (`.ARW` + `.JPG`). Video pairs inherit timestamps, organize into matching year/month folders, and synchronize filenames during collisions to preserve Live Photo playback.
- **Global Phase-by-Phase Sidecar Matching**: Strict multi-tier matching (Same-Folder Exact ➜ Same Relative Path Cross-Archive ➜ Root Cross-Archive ➜ Stem Fallback) prevents low-priority candidates from stealing sidecars across split ZIPs.
- **日期判斷與低信心保底**: Resolves timestamps in order: `EXIF` ➜ `Google JSON taken time` ➜ `JSON creationTime` ➜ `Filename` ➜ `Folder` ➜ `Filesystem mtime fallback`, ZIP 解壓先還原封存內修改時間；mtime 僅為低信心保底，不等於拍攝時間。無效時間保留 `Unknown-Date`。
- **ZIP Bomb Defense & Legacy Encoding Fix**: Built-in 1000:1 compression ratio limit and symlink filtering prevent archive attacks; automatically recovers legacy CP437/Big5 Chinese filenames when ZIP UTF-8 flags are absent.
- **Interactive HTML5 Report**: Modern Slate/Blue responsive dashboard featuring instant search, 7 categorical filters (Live Photo pairs, duplicates, review items), KPI statistics, and Chinese warning badges.
- **Deduplication & Cryptographic Verification**: Groups exact duplicates via SHA-256 and isolates replicas; verifies byte size and SHA-256 integrity after export.

## Requirements

- Python >= 3.13
- 依賴包含 Pillow、pillow-heif 與 GUI 所需 PySide6；目前實際套件規格見 `requirements.txt`，工作區使用 Python 3.13 專案環境。

Install dependencies:
```powershell
pwsh -NoProfile -File scripts/start_gui.ps1 -NoLaunch
.venv\Scripts\python.exe -s -m pip install --no-deps -e .
```

## CLI Usage

以下指令在專案根目錄、環境設定完成且已執行上方 editable 安裝後使用。inputs／work／output 是範例名稱，需改成實際來源與輸出；來源和輸出不可重疊。start_gui.ps1 -NoLaunch 可能建立環境或安裝缺少套件，不是唯讀檢查。

> [!TIP]
> **Multi-ZIP Recommendation**: If your Google Takeout is split across multiple ZIP files, pass **all ZIP files together** to `analyze`. This enables global cross-archive pairing so media in one volume correctly matches its sidecar JSON located in another volume.

### 1. Analyze & Plan
```powershell
# Analyze a single ZIP or folder
.venv\Scripts\python.exe -B -s -m google_photos_takeout_organizer.cli analyze .\inputs\Takeout-001.zip --work .\work

# Analyze multiple ZIP volumes simultaneously (Recommended for multi-part Takeouts)
.venv\Scripts\python.exe -B -s -m google_photos_takeout_organizer.cli analyze .\inputs\Takeout-001.zip .\inputs\Takeout-002.zip .\inputs\Takeout-003.zip --work .\work
```
Analyze generates `manifest.json`, `summary.json`, and `report.html` in the specified `--work` folder.

### 2. Export
```powershell
.venv\Scripts\python.exe -B -s -m google_photos_takeout_organizer.cli export --manifest .\work\manifest.json --output .\output\GooglePhotos_Archive
```

### 3. Verify
```powershell
.venv\Scripts\python.exe -B -s -m google_photos_takeout_organizer.cli verify --manifest .\output\GooglePhotos_Archive\manifest.json --output .\output\GooglePhotos_Archive
```

## Graphical User Interface (GUI)

A clean, workflow-oriented desktop GUI is included for Windows users without needing command-line knowledge.

### Launch with RUN.bat

Double-click **`RUN.bat`** in the project folder to open the desktop GUI.

- **No packaged EXE**: Runs through Python / `.venv`, reducing false-positive antivirus warnings in managed office environments.
- **First-run setup**: Detects Python 3.13+, creates `.venv`, and installs `requirements.txt`. An internet connection is required only for this setup.
- **Quiet subsequent launches**: Uses `pythonw.exe` after setup, so no console window remains open.
- **命令列啟動**：環境就緒後使用 `.venv\Scripts\python.exe -B -s -m google_photos_takeout_organizer.gui`，避免套用全域 Python。

### GUI Workflow
1. Add one or more Takeout ZIP files. Multi-part exports are pooled for cross-archive sidecar matching.
2. Select an output directory.
3. Original Takeout archives are never moved, changed, or deleted.
4. Start the guided workflow: Analyze → Export (copy-only) → Verify (SHA-256).
5. Open the organized output, review folder, or detailed report after completion.

### Large-library workflow

- **Safe resume**: Interrupted work keeps `.gpto_work/session.json` and completed output. Resume verifies source ZIP path, size, and modification time. Existing files are skipped only when both size and SHA-256 match.
- **Disk preflight**: Estimates required capacity at 2.5× the total source ZIP size before starting.
- **Drag and drop**: Drop one or more `.zip` files directly into the window; duplicate inputs are ignored.
- **Clear temporary data**: Available only after successful verification; it removes only `.gpto_work`, never formal output, manifests, or reports.
- **Background work**: Minimize with “—” to the Windows system tray while work continues. Close with “×” to safely stop work after confirmation.

## Output Structure

```
<output>/
├── Photos_Archive/    # Primary photo and video archive
│   └── YYYY/
│       ├── MM/
│       │   ├── photo.jpg
│       │   └── photo.jpg.supplemental-metadata.json
│       └── Unknown-Month/
├── Duplicates/        # Byte-identical duplicates
│   └── YYYY/
│       └── MM/
│           └── photo__dup001.jpg
├── Review/            # Manual review (date conflicts or ambiguous sidecars)
│   ├── Date-Conflict/
│   └── Ambiguous-Sidecar/
├── Unknown-Date/       # Media with no reliable date
├── manifest.json      # Full manifest: sources, hashes, and output paths
└── verification.json  # Export integrity report (SHA-256)
```

Copy-only safety guarantee: original inputs are never modified, deleted, moved, or overwritten. EXIF metadata is never rewritten and media files are never recompressed or transcoded.

## 已知 Bug、限制與疑難排解

以下區分已確認問題、功能限制及待驗證項目；歷史修正不代表舊發行包已自動更新，也不代表本次文件更新重新完成所有功能測試。

| 狀態 | 情境 | 處理方式 |
|---|---|---|
| 資料限制 | Sidecar 缺失、跨分卷未完整加入或日期來源互相矛盾。 | 加入同批全部分卷，檢查 Review／Unknown-Date；雜湊一致只證明內容完整，不證明日期判讀正確。 |
| 容量限制 | ZIP 大小的 2.5 倍只是容量預估。 | 處理中持續確認可用空間；高壓縮率、大量重複輸出與其他程式寫入會影響實際需求。 |
| 續作限制 | 續作要求來源路徑、大小與修改時間符合先前工作階段。 | 保留原來源和工作資料，不任意搬動 .gpto_work；先查清差異再續作。 |

日期來源優先序、UTC+8 日期衝突與 GUI／啟動相容性的歷史修正見 [CHANGELOG.md](CHANGELOG.md)。目前工作區以 Python 3.13 專案環境驗證；規格允許較新版本，不代表每個版本與乾淨電腦已實測。

### 問題回報

請提供使用版本／啟動方式、作業系統與相關環境、重現步驟、預期及實際結果，以及去識別的錯誤訊息或最小樣本。先保留現場與來源資料；不要附真實案件、完整帳號、密碼、Token 或 API Key。版本修正以對應原始碼與發行包為準。

## 2026-10-16 修正狀態

v1.3.1 修補版包含跨 ZIP 同名檔案誤配、成對名稱衝突與 ZIP 時間保底修正。既有 v1.3.0 下載包不包含這些修正。升級後請從來源 ZIP 使用新的工作目錄重新分析；舊 manifest 與解壓快取不會自動更正。發布方式維持 RUN.bat＋Python 3.13+，首次安裝相依套件需要網路，並非獨立 EXE。


### Windows 首次安裝路徑限制

首次安裝 PySide6 時，套件內部檔名可能使完整路徑超過未啟用長路徑支援的 Windows 限制。若安裝訊息出現 Long Path 或深層檔案找不到，請將整個專案複製到較短的資料夾後再執行 RUN.bat；中文與空白本身可用。不需要變更系統設定，既有來源 ZIP 也不需搬移。首次安裝仍需要網路。
