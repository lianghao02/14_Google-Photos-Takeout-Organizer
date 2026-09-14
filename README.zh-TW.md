# Google 相簿 Takeout 整理工具

**繁體中文** | [English](README.md)

安全、完全在本機執行、只複製不改寫的 Google Photos／Google Takeout 整理工具。它會先建立清冊與人工確認報告，再匯出與驗證整理結果。

`Takeout → 分析 → 人工確認 → 整理 → 驗證`

## 功能

- **Copy-only 安全性**：不移動、不修改、不刪除、不覆寫原始 Takeout ZIP 或資料夾。
- **多 ZIP 跨分卷配對**：可同時加入同批 Takeout 分卷，正確配對跨 ZIP 的照片、影片與 Sidecar JSON。
- **完整 Sidecar 支援**：支援 `.supplemental-metadata.json`、一般 `.json` 與 Takeout 編號命名變體。
- **日期與人工確認**：綜合 EXIF、Sidecar、檔名與資料夾線索；有衝突或不明確時送往 `Review/` 或 `Unknown-Date/`，不猜測日期。
- **重複檔與驗證**：以 SHA-256 分組完全相同的檔案，並於匯出後逐檔驗證大小與雜湊。

## 系統需求

- Windows 10／11
- Python 3.13 以上（64 位元）
- 首次啟動需網路連線，以安裝 `Pillow`、`pillow-heif` 與 `PySide6`

## 啟動方式

在專案資料夾雙擊 **`RUN.bat`**。

- **不打包 EXE**：直接以 Python／`.venv` 執行，降低辦公室防毒軟體誤判的機率。
- **首次自動設定**：啟動器會偵測 Python 3.13+、建立 `.venv`，並安裝 `requirements.txt`。
- **後續靜默啟動**：環境就緒後會使用 `pythonw.exe`，不保留黑色命令列視窗。
- **命令列**：亦可執行 `python -m google_photos_takeout_organizer.gui` 或 `gpto-gui`。

## GUI 操作流程

1. 加入一個或多個 Google Takeout ZIP。多分卷建議一次加入，以完整配對中繼資料。
2. 選擇整理輸出資料夾。
3. 點擊開始整理，工具依序執行「分析 → Copy-only 整理 → SHA-256 驗證」。
4. 完成後可開啟整理結果、人工確認資料夾與詳細報告。

## 大容量 Takeout

- **安全續作**：取消或非正常中斷後，會保留 `.gpto_work/session.json` 與已安全複製的檔案。續作前會核對來源 ZIP 路徑、大小與修改時間；既有檔案只有在大小與 SHA-256 都一致時才會略過。
- **磁碟空間預檢**：開始前以 ZIP 總大小的 2.5 倍估算需求；不足時不會開始整理。
- **拖曳 ZIP**：可直接將一或多個 `.zip` 從檔案總管拖入視窗；重複項目會略過。
- **背景整理**：按「—」縮小到 Windows 右下系統列，整理會持續執行；按「×」則會要求確認並安全停止。
- **清除暫存資料**：僅在驗證成功後顯示，且只會刪除 `.gpto_work`，不會刪除正式輸出、清冊或報告。

## 輸出結構

```text
<output>/
├── Photos_Archive/    # 主要照片與影片歸檔
├── Duplicates/        # 完全相同的重複檔案
├── Review/            # 日期衝突或 Sidecar 不明確的人工確認項目
├── Unknown-Date/      # 無法可靠判定日期的媒體
├── manifest.json      # 來源、雜湊與輸出路徑清冊
└── verification.json  # SHA-256 完整性驗證報告
```

原始 Takeout 永遠不會被改寫、重新壓縮、移動或刪除；照片與影片的 EXIF 也不會被重寫。

## CLI

```powershell
python -m google_photos_takeout_organizer.cli analyze D:\Takeout-001.zip --work work
python -m google_photos_takeout_organizer.cli export --manifest work\manifest.json --output E:\GooglePhotos_Archive
python -m google_photos_takeout_organizer.cli verify --manifest E:\GooglePhotos_Archive\manifest.json --output E:\GooglePhotos_Archive
```
