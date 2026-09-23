@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" tools\dev_run.py %*
if errorlevel 1 pause
