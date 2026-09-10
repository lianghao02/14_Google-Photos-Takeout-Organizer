# Google Photos Takeout Organizer

Safe, local, copy-only organization for Google Photos / Google Takeout ZIPs and folders. It generates a manifest and review report before exporting.

`Takeout → Analyze → Review → Export → Verify`

## Features

- **Copy-Only Safety**: Never modifies, moves, deletes, or overwrites original Takeout archives or folders. Original inputs remain 100% read-only.
- **Multi-ZIP Cross-Archive Pooling**: Allows inputting all ZIP parts from a Takeout batch at once, accurately pairing media with sidecars across split volumes.
- **Full Takeout Sidecar Support**: Supports `.supplemental-metadata.json`, standard `.json`, and Takeout numbered naming variants (e.g. `DSCF0787(1).AVI` ↔ `DSCF0787.AVI.supplemental-metadata(1).json`).
- **Date Resolution & Conflict Review**: Combines EXIF, Sidecar JSON, filename timestamps, and directory hints. Ambiguous dates or conflicts route safely to `Review/` or `Unknown-Date/` without guessing.
- **HEIC / Live Photo / Video Support**: Extracts EXIF metadata from photos (including Apple HEIC with safe fallback) and safely organizes video formats (`.mp4`, `.mov`, `.avi`, etc.).
- **Deduplication & Collision Protection**: Groups exact byte duplicates via SHA-256 (one primary in `Photos_Archive/YYYY/MM`, replicas in `Duplicates/YYYY/MM`).
- **Cryptographic Verification**: Built-in SHA-256 and size verification ensures the exported archive is byte-for-byte identical to the sources.

## Requirements

- Python >= 3.13
- Dependencies: `Pillow>=10.0`, `pillow-heif>=1.7.0`

Install dependencies:
```powershell
pip install -r requirements.txt
```

## CLI Usage

> [!TIP]
> **Multi-ZIP Recommendation**: If your Google Takeout is split across multiple ZIP files, pass **all ZIP files together** to `analyze`. This enables global cross-archive pairing so media in one volume correctly matches its sidecar JSON located in another volume.

### 1. Analyze & Plan
```powershell
# Analyze a single ZIP or folder
python -m google_photos_takeout_organizer.cli analyze D:\Takeout-001.zip --work work

# Analyze multiple ZIP volumes simultaneously (Recommended for multi-part Takeouts)
python -m google_photos_takeout_organizer.cli analyze D:\Takeout-001.zip D:\Takeout-002.zip D:\Takeout-003.zip --work work
```
Analyze generates `manifest.json`, `summary.json`, and `report.html` in the specified `--work` folder.

### 2. Export
```powershell
python -m google_photos_takeout_organizer.cli export --manifest work\manifest.json --output E:\GooglePhotos_Archive
```

### 3. Verify
```powershell
python -m google_photos_takeout_organizer.cli verify --manifest E:\GooglePhotos_Archive\manifest.json --output E:\GooglePhotos_Archive
```

## Graphical User Interface (GUI)

A clean, workflow-oriented desktop GUI is included for Windows users without needing command-line knowledge.

### Running via Python / Repository
Double-click `RUN.bat` or run:
```powershell
python -m google_photos_takeout_organizer.gui
# or via registered script:
gpto-gui
```

### Windows Portable (免安裝綠色版)
A standalone portable distribution for Windows x64 can be built using:
```powershell
.\build_windows.ps1
```
Output directory: `dist\Google-Photos-Takeout-Organizer-v1.0.1-Windows-x64\`
- Contains `Google Photos Takeout 整理工具.exe` (no console window, standalone PySide6 runtime).
- Fully portable: no Python installation required on the target machine.

### GUI Workflow
1. **來源檔案**：點擊「選擇 ZIP」或「加入更多」，選取一或多個 Google Takeout 壓縮檔（支援跨分卷中繼資料配對）。
2. **輸出位置**：點擊「選擇」指定整理目標資料夾。
3. **安全特性**：內建固定保證「✓ 原始 Takeout 不會被移動或刪除」。
4. **開始整理**：點擊中央醒目的「開始整理」主要按鈕，系統將依序自動執行：
   - `分析資料` (Analyze)
   - `整理檔案` (Export, Copy-only)
   - `驗證結果` (Verify, SHA-256)
5. **整理結果與快捷動作**：完成後展開完整統計卡片，並可直接點擊「開啟整理結果」、「開啟人工確認」或「查看詳細報告」。

### 大容量 Takeout 工作流程

- **中斷後繼續整理**：取消或意外中斷後保留 `.gpto_work/session.json` 與已安全複製的輸出；再次選取同一輸出位置時會核對 ZIP 路徑、大小及修改時間。既有同名輸出只有在 size 與 SHA-256 完全相同時才跳過，否則停止以避免覆寫。
- **磁碟空間檢查**：開始前以來源 ZIP 總大小的 2.5 倍估算需求；空間不足會阻擋開始，接近門檻則顯示警告。
- **拖曳 ZIP**：可直接從檔案總管拖入一或多個 `.zip`；重複項目會忽略。
- **清除暫存資料**：僅在驗證通過後顯示，且只會刪除輸出根目錄下的 `.gpto_work`，不會刪除正式輸出、manifest 或驗證報告。

## Output Structure

```
<output>/
├── Photos_Archive/    # 主要照片與影片歸檔
│   └── YYYY/
│       ├── MM/
│       │   ├── photo.jpg
│       │   └── photo.jpg.supplemental-metadata.json
│       └── Unknown-Month/
├── Duplicates/        # 內容相同之重複檔案
│   └── YYYY/
│       └── MM/
│           └── photo__dup001.jpg
├── Review/            # 待人工確認（日期衝突、多重中繼資料）
│   ├── Date-Conflict/
│   └── Ambiguous-Sidecar/
├── Unknown-Date/       # 未判定日期
├── manifest.json      # 完整整理清冊（來源、雜湊、對應路徑）
└── verification.json  # 匯出完整性驗證報告 (SHA-256)
```

Copy-only safety guarantee: original inputs are never modified, deleted, moved, or overwritten. EXIF metadata is never rewritten and media files are never recompressed or transcoded.
