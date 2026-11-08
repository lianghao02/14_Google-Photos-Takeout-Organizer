# Google Photos Takeout - Colab 雲端超能相簿工坊套件

本目錄提供專為 **Google One 2TB + Google Colab Pro** 雲端生態量身打造的官方工具組。所有重度運算與相片讀寫 **100% 於 Google 雲端伺服器內部執行**，不消耗本機電腦硬碟與網路頻寬。

---

## 核心筆記本清單

### 0. `00_雲端冒險大廳.ipynb`（🎮 冒險者公會總導航）
- **功能**：Q 版 RPG 遊戲風格的視覺化總導航大廳！呈現「冒險者 HUD」與「任務公告欄」，一鍵直達各個專屬副本，隨開即走、零運算消耗。
- **時機**：日常唯一書籤首頁。

### 1. `01_相簿整理去重.ipynb`（相簿定期增量整理與去重）
- **功能**：自動掃描 Google Takeout 分割壓縮包，執行全域 Sidecar 配對、Live Photo 綁定、SHA-256 增量去重，按年月歸檔進 `Organized_Photos/`，具備**即時動態百分比進度條**，驗證無誤後自動清理 ZIP 釋放 2TB 空間。
- **時機**：每 2 個月收到 Google Takeout 匯出完成通知時執行一次。

### 2. `02_AI人臉與搜圖工作台.ipynb`（私有 AI 智慧相簿超能工坊）
- **功能**：
  1. **👤 人臉辨識與自動人物分群**：採用 InsightFace (buffalo_l) 抽取 512 維人臉向量 + DBSCAN 聚類，自動生成家庭人物相簿。
  2. **🔍 繁體中文自然語言搜圖**：Multilingual CLIP 多模態語義檢索，打字輸入「看海的背影」、「吹蠟燭」0.05 秒精準出圖。
  3. **🎨 現代 HTML5 雙軌操作面板**：
     - **線上互動**：內建 Gradio 現代 HTML5 介面（含相片瀑布流，支援手機瀏覽器連線）。
     - **離線相簿**：一鍵匯出單檔純靜態 `Family_Album.html`，存於 Drive 隨時雙擊秒開！
- **時機**：相簿整理完畢後，隨時點開享受 AI 搜圖與人物分類。

---

## 使用教學

1. **Google Takeout 自動排程**：
   - 至 [Google Takeout](https://takeout.google.com/) 僅勾選「Google 相簿」。
   - 傳送方式選擇「新增至雲端硬碟」，頻率設定「每 2 個月匯出一次，為期 1 年」。
   - 封存檔大小建議選 50 GB。
2. **在 Colab 開啟**：
   - 開啟 [Google Colab](https://colab.research.google.com/)。
   - 切換至「GitHub」分頁，搜尋 `lianghao02/14_Google-Photos-Takeout-Organizer`。
   - 點開 **`00_雲端冒險大廳.ipynb`**，即可進入您的 Q 版專屬軍火庫！
