@echo off
chcp 65001 >nul
setlocal
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
cd /d "D:\360\src"
set "PY=C:\Python314\python.exe"
if not exist "%PY%" goto nopy
if not exist "D:\360\src\logInt.py" goto noprog
echo Starting logInt (cwd D:\360\src) ...
"%PY%" "D:\360\src\logInt.py" %*
set "RC=%ERRORLEVEL%"
echo.
echo Exit code: %RC%
pause
exit /b %RC%
:nopy
echo [ERROR] Project Python not found: %PY%
pause
exit /b 1
:noprog
echo [ERROR] logInt.py not found: D:\360\src\logInt.py
pause
exit /b 1