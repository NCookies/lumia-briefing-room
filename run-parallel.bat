@echo off
rem 설치판(또는 run.bat)과 동시에 띄우는 개발판: 설정·로그·전송 기록·클립 폴더를 "LumiaBriefingRoom-dev" 로 따로 쓴다.
cd /d "%~dp0"
set LUMIA_PROFILE=dev
".venv\Scripts\python.exe" -m lumia_briefing_room.cli.app --open-ui %*
if errorlevel 1 pause
