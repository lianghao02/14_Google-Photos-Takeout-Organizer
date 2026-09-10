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

## Output Structure

```
<output>/
├── Photos_Archive/
│   └── YYYY/
│       ├── MM/
│       │   └── photo.jpg
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

Run `RUN.bat` for the graphical user interface. Analyze never rewrites EXIF, recompresses images, or transcodes videos.
