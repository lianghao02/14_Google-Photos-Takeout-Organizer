@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (".venv\Scripts\python.exe" -m google_photos_takeout_organizer.gui) else (python -m google_photos_takeout_organizer.gui)
endlocal
