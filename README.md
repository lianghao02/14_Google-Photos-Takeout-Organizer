# Google Photos Takeout Organizer

[繁體中文](README.zh-TW.md) | **English**

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

### Launch with RUN.bat

Double-click **`RUN.bat`** in the project folder to open the desktop GUI.

- **No packaged EXE**: Runs through Python / `.venv`, reducing false-positive antivirus warnings in managed office environments.
- **First-run setup**: Detects Python 3.13+, creates `.venv`, and installs `requirements.txt`. An internet connection is required only for this setup.
- **Quiet subsequent launches**: Uses `pythonw.exe` after setup, so no console window remains open.
- **Command line**: You may also run `python -m google_photos_takeout_organizer.gui` or `gpto-gui`.

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
