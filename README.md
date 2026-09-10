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
Output directory: `dist\Google-Photos-Takeout-Organizer-v1.0.0-Windows-x64\`
- Contains `Google Photos Takeout 整理工具.exe` (no console window, standalone PySide6 runtime).
- Fully portable: no Python installation required on the target machine.

### GUI Workflow
1. **① Takeout 檔案**：點擊「選擇 ZIP」或「加入更多」，選取一或多個 Google Takeout 壓縮檔（支援跨卷 Sidecar 配對）。
2. **② 整理到**：點擊「選擇」指定整理目標資料夾。
3. **③ 開始整理**：點擊單一醒目的「開始整理」按鈕，系統將依序自動執行：
   - `分析資料` (Analyze)
   - `整理檔案` (Export, Copy-only)
   - `驗證結果` (Verify, SHA-256)
4. **④ 查看結果與人工確認**：整理完成後可直接點選「開啟整理結果」或「開啟人工確認資料夾」檢視需人工核對之項目。

## Output Structure

```
<output>/
├── Photos_Archive/
│   └── YYYY/
│       ├── MM/
│       │   ├── photo.jpg
│       │   └── photo.jpg.supplemental-metadata.json
│       └── Unknown-Month/
├── Duplicates/
│   └── YYYY/
│       └── MM/
│           └── photo__dup001.jpg
├── Review/            # Files with date conflicts or ambiguous sidecars
├── Unknown-Date/       # Files with no determinable date
├── manifest.json      # Complete trace of all input files, hashes, and destinations
└── verification.json  # Export verification report
```

Copy-only safety guarantee: original inputs are never modified, deleted, moved, or overwritten. EXIF metadata is never rewritten and media files are never recompressed or transcoded.
