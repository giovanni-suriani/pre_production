@echo off
REM Sobe os dois servidores: pre_production (8740) e video_script (8741).
setlocal
cd /d "%~dp0"

start "pre_production (8740)" cmd /k call "run.bat"
start "video_script (8741)" cmd /k call "video_script\run.bat"
