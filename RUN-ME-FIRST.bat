@echo off
chcp 65001 >nul
title Compare100 - Get Images
color 0B
cls
echo.
echo  ===========================================================
echo    COMPARE100 - COPY YOUR IMAGES INTO THE SITE
echo  ===========================================================
echo.
echo   This copies the images your site needs out of your
echo   WordPress uploads folder.
echo.
echo   Nothing to install. Windows does this on its own.
echo.
echo  -----------------------------------------------------------
echo.
echo    NOW DO THIS:
echo.
echo    1. Find the folder you extracted from uploads.zip
echo       (the one with 2020, 2025, 2026 inside it)
echo.
echo    2. DRAG that folder into this black window.
echo       Windows types the path in for you.
echo.
echo    3. Press ENTER.
echo.
echo  -----------------------------------------------------------
echo.

set "SRC="
set /p SRC=  Drag the folder here, then press Enter:

REM strip quotes Windows adds when you drag
set "SRC=%SRC:"=%"

if not defined SRC (
  echo.
  echo  Nothing was entered. Close this and try again.
  echo.
  pause
  exit /b 1
)

if not exist "%SRC%" (
  echo.
  echo  Cannot find that folder:
  echo    %SRC%
  echo.
  echo  Drag the FOLDER itself, not a file inside it.
  echo.
  pause
  exit /b 1
)

echo.
echo  Working. This takes a minute or two...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0get-images.ps1" -Source "%SRC%"

echo.
echo  ===========================================================
echo    FINISHED
echo  ===========================================================
echo.
echo    If anything was MISSING there is now a file called
echo    images-missing.txt in this folder. Send it to Claude.
echo.
echo    Otherwise your images are in. Next step:
echo    open START-HERE.txt and do STEP 2.
echo.
pause
