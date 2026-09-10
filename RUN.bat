@echo off
setlocal
cd /d "%~dp0"

set "PY_EXE="
if exist ".venv\Scripts\python.exe" (
    set "PY_EXE=.venv\Scripts\python.exe"
) else (
    set "PY_EXE=python"
)

"%PY_EXE%" -c "import PySide6" >nul 2>&1
if errorlevel 1 (
    echo [提示] 正在安裝必要套件 (PySide6 / Pillow / pillow-heif)...
    "%PY_EXE%" -m pip install -r requirements.txt
)

"%PY_EXE%" -m google_photos_takeout_organizer.gui
if errorlevel 1 (
    echo.
    echo 執行發生錯誤，請按任意鍵離開...
    pause >nul
)
endlocal
