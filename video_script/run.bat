@echo off
REM Sobe o video_script (porta 8741). Usa o MESMO venv do pre_production
REM (..\.venv) -- as dependencias sao as mesmas (fastapi+uvicorn), e um
REM segundo venv aqui seria so mais uma coisa pra lembrar de atualizar.
setlocal
cd /d "%~dp0"

if not exist "..\.venv\Scripts\python.exe" (
  echo [i] criando o venv do pre_production...
  pushd ..
  py -3 -m venv .venv || python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  popd
)

start "" http://127.0.0.1:8741
"..\.venv\Scripts\python.exe" app.py
