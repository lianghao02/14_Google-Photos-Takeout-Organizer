@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"

if exist ".venv\Scripts\python.exe" (
    set "PY_EXE=.venv\Scripts\python.exe"
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo 找不到可用的 Python。
        echo 請先安裝 Python 3.13，或直接使用 Windows Portable 版本。
        echo.
        pause
        exit /b 1
    )
    python --version >nul 2>&1
    if errorlevel 1 (
        echo 找不到可用的 Python。
        echo 請先安裝 Python 3.13，或直接使用 Windows Portable 版本。
        echo.
        pause
        exit /b 1
    )
    set "PY_EXE=python"
)

"%PY_EXE%" -c "import PySide6, PIL, pillow_heif" >nul 2>&1
if errorlevel 1 (
    echo.
    echo 缺少必要 Python 套件。
    echo.
    echo 請在本專案資料夾執行：
    echo.
    echo python -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

"%PY_EXE%" -m google_photos_takeout_organizer.gui
if errorlevel 1 pause

endlocal

