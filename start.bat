@echo off
chcp 65001 >nul
setlocal

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "FFMPEG_DIR=C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Links"
if exist "%FFMPEG_DIR%" set "PATH=%PATH%;%FFMPEG_DIR%"

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PYTHON_CMD=py -3"
) else (
    set "PYTHON_CMD=python"
)

echo ========================================
echo    TTS + STT 服务启动器
echo ========================================
echo.
echo 使用解释器: %PYTHON_CMD%
echo.

echo [1/2] 启动 TTS 服务 (5000)...
start "TTS Server" cmd /k "cd /d ""%ROOT%\web"" && %PYTHON_CMD% server.py"

timeout /t 2 /nobreak >nul

echo [2/2] 启动 STT 服务 (5001)...
start "STT Server" cmd /k "cd /d ""%ROOT%\stt"" && %PYTHON_CMD% server.py"

echo.
echo TTS: http://127.0.0.1:5000
echo STT: http://127.0.0.1:5001
echo.
pause
