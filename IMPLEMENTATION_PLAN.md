# 實作計畫

## 目標與驗收條件

- 發布不依賴 PyInstaller EXE 的 Windows 正式版 `v1.2.0`。
- `RUN.bat` 可在未建立 `.venv` 的環境，自動建立虛擬環境、安裝必要套件並啟動 GUI。
- 已建立環境時，使用 `pythonw.exe` 靜默啟動，不留下 CMD 視窗。
- 納入系統列背景整理：按「—」縮至系統列，按「×」安全結束。

## 不做範圍

- 不建立 PyInstaller EXE、Installer 或內嵌 Python 發行包。
- 不修改 Takeout 分析、輸出、驗證與資料安全規則。

## 已確認決策

- 參考 `07_auto-learning-bot` 的自癒啟動概念，但採專案 `.venv`，不下載或保存 Python Embedded Runtime。
- Python 3.13+ 為必要條件；找不到時顯示清楚處置訊息。

## 工作清單

- [x] 建立自癒 PowerShell 啟動器並改接 `RUN.bat`｜PowerShell 語法檢查與 `-NoLaunch` 啟動測試通過。
- [x] 更新版本、使用說明與更新日誌｜文件檢查通過。
- [x] 執行完整 pytest 與啟動器 smoke test｜pytest 18/18、啟動環境檢查通過。
- [ ] 建立提交、推送 `main` 並建立 `v1.2.0` tag｜確認遠端分支與 tag。

## 風險與因應

- 缺少 Python 或網路無法安裝套件：顯示繁中錯誤訊息與具體處置方式，不偽裝啟動成功。
- 首次建置耗時：以可見 PowerShell 視窗顯示進度；已就緒環境則靜默啟動。

## 驗證紀錄

- PowerShell AST 語法檢查：通過。
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\start_gui.ps1 -NoLaunch`：通過。
- `pytest -q`：18/18 通過。

## 剩餘問題

無。
