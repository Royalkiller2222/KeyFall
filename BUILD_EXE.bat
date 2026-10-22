@echo off
setlocal
title KeyFall - Build EXE
color 0B
cd /d "%~dp0"

echo.
echo  ==========================================
echo   KeyFall - Building Standalone EXE
echo  ==========================================
echo.

set "PYEXE="
py -3.12 --version >nul 2>&1
if not errorlevel 1 set "PYEXE=py -3.12"
if not defined PYEXE (
    py -3.11 --version >nul 2>&1
    if not errorlevel 1 set "PYEXE=py -3.11"
)
if not defined PYEXE (
    echo  ERROR: Python 3.12 or 3.11 not found. Install Python 3.12 from python.org
    pause & exit /b 1
)

echo  Installing build tools...
%PYEXE% -m pip install --user -q -r requirements-build.txt --disable-pip-version-check
if errorlevel 1 ( echo  Could not install build tools. & pause & exit /b 1 )

if not exist "fluidsynth\pianos\piano.sf2" %PYEXE% setup_audio.py

echo  Building (2-5 minutes)...
echo.
%PYEXE% build_release.py %*
if errorlevel 1 ( echo. & echo  BUILD FAILED. & pause & exit /b 1 )

echo.
echo  ==========================================
echo   DONE  -  dist\KeyFall\KeyFall.exe
echo  ==========================================
echo  Your savegame and any songs you added in dist\KeyFall were kept.
echo  To publish a release on GitHub, run RELEASE.bat instead.
echo.
pause
