@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title Camera do Celular (scrcpy)
set "DIR=%LOCALAPPDATA%\Microsoft\WinGet\Packages\Genymobile.scrcpy_Microsoft.Winget.Source_8wekyb3d8bbwe\scrcpy-win64-v4.1"
set "SCRCPY=%DIR%\scrcpy.exe"
set "ADB=%DIR%\adb.exe"

"%ADB%" start-server >nul 2>&1

rem 1) Cabo USB: se o celular estiver plugado com depuracao, usa ele.
"%ADB%" -d get-state >nul 2>&1
if not errorlevel 1 (
    echo Celular encontrado no cabo USB.
    set "DISP=-d"
    goto menu
)

rem 2) Wi-Fi: celular ja pareado, so precisa do Wireless debugging ligado.
rem A porta muda toda vez, entao acha pelo mDNS e conecta.
echo Cabo sem depuracao. Procurando o celular no Wi-Fi...
set "ALVO="
for /L %%T in (1,1,10) do (
    if not defined ALVO (
        for /f "tokens=1-3" %%A in ('"%ADB%" mdns services') do if "%%B"=="_adb-tls-connect._tcp" set "ALVO=%%C"
        if not defined ALVO ping -n 2 127.0.0.1 >nul
    )
)
if not defined ALVO (
    echo.
    echo Celular nao encontrado. Confira no celular:
    echo   Settings ^> Developer options ^> Wireless debugging ligado
    echo   e o celular no mesmo Wi-Fi do PC.
    echo.
    pause
    exit /b
)
"%ADB%" connect %ALVO%
set "DISP=-s %ALVO%"

:menu
echo.

echo  1 - Camera traseira 1080p
echo  2 - Camera frontal 1080p
echo  3 - Traseira 1080p + microfone do celular
echo  4 - Listar resolucoes da camera
echo.
set /p OP="Escolha [1]: "
if "%OP%"=="" set OP=1

set "COMUM=%DISP% --video-source=camera --camera-size=1920x1080 --window-title=Celular --window-borderless"

if "%OP%"=="1" "%SCRCPY%" %COMUM% --camera-facing=back --no-audio
if "%OP%"=="2" "%SCRCPY%" %COMUM% --camera-facing=front --no-audio
if "%OP%"=="3" "%SCRCPY%" %COMUM% --camera-facing=back --audio-source=mic
if "%OP%"=="4" "%SCRCPY%" %DISP% --list-camera-sizes

echo.
pause
