@echo off
chcp 65001 >nul
setlocal
set "PYTHONUTF8=1"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Python environment not found. Run setup.ps1 first.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\manage_admin_token.py"
if errorlevel 1 pause
endlocal
