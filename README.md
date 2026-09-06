# Google Photos Takeout Organizer

Safe local, copy-only organization for Google Photos / Google Takeout ZIPs and folders. It creates a manifest and review report before export.

`Takeout → Analyze → Review → Export → Verify`

Takeout sidecar JSON and EXIF may contain complementary capture dates. Conflicts are marked for review. Exact duplicates require identical SHA-256 hashes: one deterministic primary goes to `Photos_Archive/YYYY/MM`; identical copies remain in `Duplicates/YYYY/MM`. Unknown dates stay unknown.

Keep an independently verified original Takeout copy: an organized archive has a different role and cannot promise every Google metadata detail is recovered.

```powershell
python -m google_photos_takeout_organizer.cli analyze D:\Takeout.zip --work work
python -m google_photos_takeout_organizer.cli export --manifest work\manifest.json --output E:\GooglePhotos_Backup
python -m google_photos_takeout_organizer.cli verify --manifest E:\GooglePhotos_Backup\manifest.json --output E:\GooglePhotos_Backup
```

Run `RUN.bat` for the Tkinter GUI. Analyze never exports, moves, deletes, rewrites EXIF, recompresses images, or transcodes video.
