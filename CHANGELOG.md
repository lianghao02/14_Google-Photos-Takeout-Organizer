# Changelog

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
