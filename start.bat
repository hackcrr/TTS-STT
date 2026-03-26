@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

call :load_env_file "%ROOT%\.env"
call :load_env_file "%ROOT%\.env.local"

if not defined FFMPEG_DIR set "FFMPEG_DIR=C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Links"
if not defined TTS_HOST set "TTS_HOST=0.0.0.0"
if not defined TTS_PORT set "TTS_PORT=5000"
if not defined STT_HOST set "STT_HOST=0.0.0.0"
if not defined STT_PORT set "STT_PORT=5001"

if exist "%FFMPEG_DIR%" set "PATH=%PATH%;%FFMPEG_DIR%"

set "PYTHON_CMD="
if exist "C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe" (
    set "PYTHON_CMD=C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe"
) else if exist "C:\Users\Administrator\python" (
    set "PYTHON_CMD=C:\Users\Administrator\python"
) else (
    where py >nul 2>nul
    if !ERRORLEVEL!==0 (
        set "PYTHON_CMD=py -3"
    ) else (
        set "PYTHON_CMD=python"
    )
)

echo ========================================
echo    TTS + STT Launcher
echo ========================================
echo.
echo Python: %PYTHON_CMD%
echo TTS:    http://127.0.0.1:%TTS_PORT%
echo STT:    http://127.0.0.1:%STT_PORT%
echo.

echo [1/2] Starting TTS service...
start "TTS Server" cmd /k "cd /d ""%ROOT%\web"" && %PYTHON_CMD% server.py"

timeout /t 2 /nobreak >nul

echo [2/2] Starting STT service...
start "STT Server" cmd /k "cd /d ""%ROOT%\stt"" && %PYTHON_CMD% server.py"

echo.
pause
exit /b 0

:load_env_file
set "ENV_FILE=%~1"
if not exist "%ENV_FILE%" exit /b 0

for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
    set "KEY=%%~A"
    set "VALUE=%%~B"
    if defined KEY (
        if not "!KEY:~0,1!"=="#" (
            if not defined !KEY! set "!KEY!=!VALUE!"
        )
    )
)
exit /b 0
