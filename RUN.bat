@echo off
setlocal
cd /d "%~dp0"
start "" /b powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0scripts\start_gui.ps1"
endlocal
exit /b

