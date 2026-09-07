@echo off
title DS Movies - MP4 to DPG converter
cd /d "%~dp0"

echo ================================================================
echo    DS Movies  -  MP4 to DPG converter for Nintendo DS / R4
echo ================================================================
echo.

REM On a plain double-click, make sure a Movies folder exists to drop videos into
if "%~1"=="" if not exist "%~dp0Movies" mkdir "%~dp0Movies"

if "%~1"=="" (
  echo Converting every video in the "Movies" folder...
) else (
  echo Converting the item^(s^) you dropped on this file...
)
echo.

REM Find Python (try 'python', then the 'py' launcher)
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (where py >nul 2>nul && set "PY=py")

if not defined PY (
  echo Python 3 was not found.
  echo Install it from https://www.python.org/downloads/ and tick
  echo    "Add python.exe to PATH" during setup, then run this again.
  echo.
  pause
  exit /b 1
)

%PY% "%~dp0dpg-convert.py" %*

echo.
echo ================================================================
echo    Done. Your .dpg files are in the "Movies" folder
echo    (or next to any videos you dragged onto this file).
echo    Copy them to your R4 card and open them in Moonshell.
echo ================================================================
echo.
pause
