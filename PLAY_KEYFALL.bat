@echo off
title KeyFall
color 0B
cd /d "%~dp0"

echo.
echo  KeyFall
echo.

REM Find Python 3.12 or 3.11
set PYEXE=
py -3.12 --version >nul 2>&1
if %errorlevel% equ 0 set PYEXE=py -3.12

if "%PYEXE%"=="" (
    py -3.11 --version >nul 2>&1
    if %errorlevel% equ 0 set PYEXE=py -3.11
)
if "%PYEXE%"=="" (
    echo  No Python found. Install Python 3.12 from python.org
    pause
    exit /b 1
)

echo  Using: & %PYEXE% --version
echo.

REM Delete venv if one exists from old installs
if exist "venv\" rmdir /s /q venv

REM Only install packages if the flag file is missing (first run or after reset)
if not exist ".packages_installed" (
    echo  First run - installing packages...
    %PYEXE% -m pip install --user --quiet "pygame==2.6.1" --only-binary=:all: --disable-pip-version-check
    %PYEXE% -m pip install --user --quiet mido --disable-pip-version-check
    %PYEXE% -m pip install --user --quiet numpy --only-binary=:all: --disable-pip-version-check
    %PYEXE% -m pip install --user --quiet python-rtmidi --only-binary=:all: --disable-pip-version-check
    echo installed > .packages_installed
    echo  Packages installed.
    echo.
)

if not exist "songs\" mkdir songs

REM Download soundfont only if missing
set RUN_SETUP=0
if not exist "fluidsynth\.setup_done" set RUN_SETUP=1
if not exist "fluidsynth\pianos\piano.sf2" set RUN_SETUP=1

if "%RUN_SETUP%"=="1" (
    echo  Downloading soundfont ^(first run only^)...
    %PYEXE% setup_audio.py
    echo.
)

echo  Starting...
echo.
%PYEXE% main.py

echo.
if exist "keyfall_crash.txt" (
    echo  CRASH LOG:
    type keyfall_crash.txt
)
echo.
echo  Press any key to close.
pause >nul
REM To force package reinstall: delete .packages_installed
REM To force soundfont redownload: delete fluidsynth\.setup_done
