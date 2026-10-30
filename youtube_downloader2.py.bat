@echo off
title YouTube Downloader Launcher
color 0A

:: ========================================
:: PATHS - Change these if needed
:: ========================================
set "PROJECT_DIR=%~dp0"
set "POT_SERVER_DIR=I:\Python Project\bgutil-ytdlp-pot-provider\server"

if not exist "%POT_SERVER_DIR%" (
    if exist "%PROJECT_DIR%bgutil-ytdlp-pot-provider\server" (
        set "POT_SERVER_DIR=%PROJECT_DIR%bgutil-ytdlp-pot-provider\server"
    )
)

echo.
echo ========================================================
echo   YouTube Downloader - Auto Launcher
echo ========================================================
echo.

cd /d "%PROJECT_DIR%"

:: ========================================
:: STEP 1: Install / Update Python dependencies
:: ========================================
echo [1/4] Installing and updating Python dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -U yt-dlp bgutil-ytdlp-pot-provider pillow
if errorlevel 1 (
    echo    [WARN] Pip install returned a warning or error.
    echo    [INFO] Continuing with existing installed packages...
) else (
    echo    [OK] Python dependencies are ready.
)
echo.

:: ========================================
:: STEP 2: Start POT Token server
:: ========================================
echo [2/4] Checking POT Token server...

if not exist "%POT_SERVER_DIR%" (
    echo    [WARN] Server folder not found: %POT_SERVER_DIR%
    echo    [INFO] Continuing without POT server.
    goto :RUN_PYTHON
)

cd /d "%POT_SERVER_DIR%"

:: Check Node.js
where node >nul 2>&1
if errorlevel 1 (
    echo    [WARN] Node.js is not installed!
    echo    [INFO] Install it from https://nodejs.org and run again.
    goto :RUN_PYTHON
)

:: Build server if needed
if not exist "build\main.js" (
    echo    Building server for the first time...
    call npm install
    call npx tsc
    echo    [OK] Server built successfully.
)

:: Start server in minimized window
echo    Starting POT server in background...
start "POT Server" /MIN cmd /c "node build/main.js"
timeout /t 3 /nobreak >nul
echo    [OK] POT server is running.
echo.

:RUN_PYTHON

:: ========================================
:: STEP 3: Run main Python script
:: ========================================
echo [3/4] Launching downloader...
echo ========================================================
echo.

cd /d "%PROJECT_DIR%"

if exist "youtube_downloader2.py" (
    python youtube_downloader2.py
) else if exist "youtube_downloader2.py" (
    python youtube_downloader2.py
) else if exist "youtube_downloader2.py" (
    python youtube_downloader2.py
) else if exist "youtube_downloader2.py" (
    python youtube_downloader2.py
) else (
    echo    [ERROR] No python script found in %PROJECT_DIR%
    pause
    exit /b 1
)

:: ========================================
:: STEP 4: Cleanup
:: ========================================
echo.
echo ========================================================
echo [4/4] Shutting down POT server...
taskkill /FI "WINDOWTITLE eq POT Server*" /F >nul 2>&1
echo Done.
echo.

pause