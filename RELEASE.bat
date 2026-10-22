@echo off
setlocal
title KeyFall - Publish a release
color 0B
cd /d "%~dp0"

echo.
echo  ==========================================
echo   KeyFall - Publish a GitHub release
echo  ==========================================
echo.
echo  This tags your current commit and pushes it. GitHub then builds the
echo  EXE, runs the self-test, and publishes the zip on the Releases page.
echo.

git --version >nul 2>&1
if errorlevel 1 ( echo  Git is not installed. & pause & exit /b 1 )

git diff --quiet
if errorlevel 1 goto dirty
git diff --cached --quiet
if errorlevel 1 goto dirty

set "LAST="
for /f "delims=" %%t in ('git describe --tags --abbrev^=0 2^>nul') do set "LAST=%%t"
if defined LAST ( echo  Latest release: %LAST% ) else ( echo  No releases yet. )
echo.
set "VER="
set /p "VER= Version for the new release, e.g. 1.1.0 or 1.1.0-beta.1: "
if not defined VER ( echo  Cancelled. & pause & exit /b 1 )
if /i not "%VER:~0,1%"=="v" set "VER=v%VER%"

git rev-parse -q --verify "refs/tags/%VER%" >nul
if not errorlevel 1 ( echo  %VER% already exists - pick a new version. & pause & exit /b 1 )

echo.
echo  Pushing your commits...
git push origin HEAD
if errorlevel 1 ( echo  Push failed. & pause & exit /b 1 )
git tag -a "%VER%" -m "KeyFall %VER%"
if errorlevel 1 ( pause & exit /b 1 )
git push origin "%VER%"
if errorlevel 1 ( echo  Could not push the tag. & git tag -d "%VER%" >nul & pause & exit /b 1 )

echo.
echo  Released %VER%. GitHub is building it now - about 10 minutes:
echo    https://github.com/Royalkiller2222/KeyFall/actions
echo  The download will appear at:
echo    https://github.com/Royalkiller2222/KeyFall/releases
echo.
pause
exit /b 0

:dirty
echo  You have uncommitted changes. Commit them first, so the release
echo  contains exactly what is on GitHub:
echo.
git status --short
echo.
pause
exit /b 1
