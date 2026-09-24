@echo off
REM Sobe o pre_production. Cria o venv na primeira vez.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [i] criando venv...
  py -3 -m venv .venv || python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

start "" http://127.0.0.1:8740
cd src
"..\.venv\Scripts\python.exe" app.py
