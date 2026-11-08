# Google Photos Takeout - Colab 雲端自動化增量整理

本目錄提供在 **Google Colab** 雲端環境中自動整理 Google Takeout 相簿的官方筆記本範本，專為具備 **Google One 2TB** 空間之使用者量身打造。

---

## 核心設計理念

1. **雲端內部直通**：直接掛載 Google Drive，相片資料完全在 Google 內部伺服器串流傳輸，本機電腦 0 下載、0 上傳。
2. **繼承成熟演算法**：完全引用本專案成熟之全域 Sidecar 配對、Live Photo 成對綁定、五層日期保底與 SHA-256 完整性校驗。
3. **智慧增量去重**：遇到內容重複之照片自動略過，不重複消耗 2TB 空間。
4. **安全防禦清理**：只有在輸出驗證 100% 通過（`status: OK`）的前提下，才會安全刪除原始 Takeout ZIP 壓縮檔與解壓暫存區。

---

## 檔案說明

- **`Google_Photos_Takeout_Organizer.ipynb`**：Colab 互動式執行筆記本。

---

## 使用教學

1. **Google Takeout 設定**：
   - 至 [Google Takeout](https://takeout.google.com/) 僅勾選「Google 相簿」。
   - 傳送方式選擇「新增至雲端硬碟」，頻率設定「每 2 個月匯出一次，為期 1 年」。
   - 封存檔大小建議選 50 GB。
2. **上傳至 Colab**：
   - 開啟 [Google Colab](https://colab.research.google.com/)。
   - 選擇「上傳筆記本」，將 `Google_Photos_Takeout_Organizer.ipynb` 上傳（或存於 Google Drive 後開啟）。
3. **執行整理**：
   - 收到 Google 打包完成通知後，在 Colab 點擊「執行階段」➜「全部執行」。
   - 程式將自動建立目錄、分析配對、增量去重歸檔，並在校驗成功後自動釋放 ZIP 空間。
