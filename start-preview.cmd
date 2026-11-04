@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" tools\preview_server.py --open
  if not errorlevel 1 exit /b 0
  echo Trying system Python...
  py -3 tools\preview_server.py --open
) else (
  py -3 tools\preview_server.py --open
)
if errorlevel 1 pause
