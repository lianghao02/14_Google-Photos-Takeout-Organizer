@echo off
setlocal
cd /d "%~dp0"

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
set "VENV_PYW=%~dp0.venv\Scripts\pythonw.exe"

rem 環境齊全時直接靜默啟動；缺 Python 或套件時交給啟動器修復。
if exist "%VENV_PYW%" if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import PySide6, PIL, pillow_heif" >/dev/null 2>&1
    if not errorlevel 1 (
        set "PYTHONPATH=%~dp0src"
        start "" "%VENV_PYW%" -m google_photos_takeout_organizer.gui
        goto :done
    )
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_gui.ps1"
:done
endlocal
exit /b
