@echo off
title KeyFall - Python Diagnostics
cd /d "%~dp0"
echo.
echo  ============ Python Location Diagnostics ============
echo.

py -3.12 --version 2>nul && (
    echo  Python 3.12 found via py launcher
    for /f "tokens=*" %%i in ('py -3.12 -c "import sys; print(sys.executable)"') do (
        echo  Executable: %%i
        for %%d in ("%%i") do echo  Directory:  %%~dpd
    )
    for /f "tokens=*" %%i in ('py -3.12 -c "import sys,os; d=os.path.dirname(sys.executable); print(os.path.exists(os.path.join(d,\"python312.dll\")))"') do echo  python312.dll in exe dir: %%i
    for /f "tokens=*" %%i in ('py -3.12 -c "import sys,os; d=os.path.dirname(sys.executable); print(d)"') do (
        echo.
        echo  Listing DLLs in Python dir:
        dir /b "%%i\*.dll" 2>nul
    )
) || echo  Python 3.12 NOT found via py launcher

echo.
echo  Checking PATH for python:
where python 2>nul || echo  python not in PATH

echo.
echo  Windows\System32 vcruntime:
dir /b "C:\Windows\System32\vcruntime*.dll" 2>nul

echo.
pause
