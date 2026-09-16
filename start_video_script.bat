@echo off
REM Sobe SO o video_script (porta 8741), sem o pre_production da 8740.
REM
REM Montar e conduzir episodio nao precisa do 8740 pra nada -- aquele so
REM entra depois de gravado (corte, diarizacao, legenda). Subir os dois pra
REM usar um so e porta ocupada e uma janela a mais pra fechar.
REM
REM E um atalho pro video_script\run.bat, nao uma copia: quem sabe criar o
REM venv e achar o app.py continua sendo um arquivo so, la dentro.
setlocal
cd /d "%~dp0"

call "video_script\run.bat"
