@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3"

if not defined PYTHON_CMD (
  where python >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
  echo Python runtime not found.
  echo Please install Python or make sure "py" or "python" is in PATH.
  pause
  exit /b 1
)

echo Starting DeepSeek local proxy on 127.0.0.1:50010
call %PYTHON_CMD% deepseek_proxy.py --host 127.0.0.1 --port 50010
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo Proxy exited with code %EXIT_CODE%.
  echo Check the console output for details.
  pause
  exit /b %EXIT_CODE%
)
