@echo off
title KeyFall - Build EXE
color 0B
cd /d "%~dp0"

echo.
echo  ==========================================
echo   KeyFall - Building Standalone EXE
echo  ==========================================
echo.

set PYEXE=C:\Users\Carter\AppData\Local\Programs\Python\Python312\python.exe
set PYDIR=C:\Users\Carter\AppData\Local\Programs\Python\Python312

if not exist "%PYEXE%" (
    echo  ERROR: Python not found at %PYEXE%
    pause & exit /b 1
)

echo  Python: %PYEXE%
echo.

echo  Installing build tools...
"%PYEXE%" -m pip install --user -q setuptools --disable-pip-version-check
"%PYEXE%" -m pip install --user -q "pyinstaller==6.3.0" --disable-pip-version-check
"%PYEXE%" -m pip install --user -q pygame==2.6.1 --only-binary=:all: --disable-pip-version-check
"%PYEXE%" -m pip install --user -q mido --disable-pip-version-check
"%PYEXE%" -m pip install --user -q "numpy==1.26.4" --only-binary=:all: --disable-pip-version-check
"%PYEXE%" -m pip install --user -q python-rtmidi --only-binary=:all: --disable-pip-version-check
echo  Done.
echo.

echo  Cleaning old build...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
echo  Done.
echo.

echo  Building EXE (2-5 minutes)...
echo.

"%PYEXE%" -m PyInstaller ^
    --noconfirm ^
    --onedir ^
    --windowed ^
    --name KeyFall ^
    --distpath "dist" ^
    --workpath "build" ^
    --add-data "game;game" ^
    --add-data "songs;songs" ^
    --add-data "sfx;sfx" ^
    --hidden-import pygame ^
    --hidden-import pygame.mixer ^
    --hidden-import pygame.font ^
    --hidden-import numpy ^
    --hidden-import mido ^
    --hidden-import mido.backends.rtmidi ^
    --collect-all pygame ^
    --collect-all numpy ^
    --exclude-module pygame.tests ^
    --exclude-module pygame.examples ^
    main.py

if %errorlevel% neq 0 (
    echo.
    echo  BUILD FAILED.
    pause & exit /b 1
)

echo.
echo  Copying data into dist\KeyFall...
if exist "songs"      xcopy /s /i /q /y songs      "dist\KeyFall\songs"      >nul
if exist "fluidsynth" xcopy /s /i /q /y fluidsynth "dist\KeyFall\fluidsynth" >nul
if exist "sfx"        xcopy /s /i /q /y sfx        "dist\KeyFall\sfx"        >nul

echo  Copying DLLs...
copy /y "%PYDIR%\python312.dll"      "dist\KeyFall\" >nul 2>&1
copy /y "%PYDIR%\vcruntime140.dll"   "dist\KeyFall\" >nul 2>&1
copy /y "%PYDIR%\vcruntime140_1.dll" "dist\KeyFall\" >nul 2>&1
if exist "dist\KeyFall\_internal" (
    copy /y "%PYDIR%\python312.dll"      "dist\KeyFall\_internal\" >nul 2>&1
    copy /y "%PYDIR%\vcruntime140.dll"   "dist\KeyFall\_internal\" >nul 2>&1
    copy /y "%PYDIR%\vcruntime140_1.dll" "dist\KeyFall\_internal\" >nul 2>&1
)

rmdir /s /q "build"

echo @echo off > "dist\KeyFall\PLAY KeyFall.bat"
echo cd /d "%%~dp0" >> "dist\KeyFall\PLAY KeyFall.bat"
echo KeyFall.exe >> "dist\KeyFall\PLAY KeyFall.bat"

echo.
echo  ==========================================
echo   DONE  -  dist\KeyFall\
echo  ==========================================
echo  Zip and share the dist\KeyFall folder.
echo  Double-click KeyFall.exe to play.
echo.
pause
