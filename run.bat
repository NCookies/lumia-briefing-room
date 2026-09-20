@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m lumia_briefing_room.cli.app --open-ui %*
if errorlevel 1 pause
