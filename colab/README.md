# Google Photos Takeout - Colab 雲端超能相簿工坊套件

本目錄提供專為 **Google One 2TB + Google Colab Pro** 雲端生態量身打造的官方工具組。所有重度運算與相片讀寫 **100% 於 Google 雲端伺服器內部執行**，不消耗本機電腦硬碟與網路頻寬。

---

## 🎮 總導航入口（AI 雲端工具箱）

👉 **[AI 雲端工具箱 (Google Colab Hub)](https://lianghao02.github.io/Project-Hub/colab.html)**  
*(建議加入瀏覽器書籤，隨時一鍵開啟各項雲端工具)*

---

## 核心筆記本清單

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

### 3. `03_老照片畫質修復與超解析度.ipynb`（老照片五官重建與 4K 放大）
- **功能**：
  1. **✨ 模糊人臉五官重建**：採用 GFPGAN v1.4 清晰面部修復模型，自動修復老舊、失焦、泛黃照片中的臉孔五官與皮膚細節。
  2. **🔍 全圖 4 倍超解析度**：結合 Real-ESRGAN 4x+ 演算法，去除掃描噪點與壓縮雜訊，無損放大至 4K 高畫質。
  3. **🖼️ 互動雙模式**：支援 Gradio 網頁介面即時單張 Before/After 對比，亦可指定 Google Drive 年份相簿進行全自動批次修復，結果保存至 `Restored/`，原始照片 100% 唯讀保全。
- **時機**：處理早期低解析度數位相片、手機老照片或實體紙本翻拍掃描檔時隨時使用。

---

## 使用教學

1. **Google Takeout 自動排程**：
   - 至 [Google Takeout](https://takeout.google.com/) 僅勾選「Google 相簿」。
   - 傳送方式選擇「新增至雲端硬碟」，頻率設定「每 2 個月匯出一次，為期 1 年」。
   - 封存檔大小建議選 **10 GB**（若使用高磁碟空間 Colab 執行階段再選 50 GB，避免單卷複製至本地 SSD 時空間吃緊）。
2. **在 Colab 開啟**：
   - 直接點開 **[AI 雲端工具箱網頁](https://lianghao02.github.io/Project-Hub/colab.html)**，點擊對應卡片按鈕即可在新分頁開啟筆記本！
