@echo off
setlocal

set "SRC_DIR=%~dp0"
set "TARGET_DIR=%USERPROFILE%\.codex"

if not exist "%TARGET_DIR%" (
  mkdir "%TARGET_DIR%"
)

if exist "%TARGET_DIR%\config.toml" copy /Y "%TARGET_DIR%\config.toml" "%TARGET_DIR%\config.toml.bak" >nul
if exist "%TARGET_DIR%\auth.json" copy /Y "%TARGET_DIR%\auth.json" "%TARGET_DIR%\auth.json.bak" >nul

copy /Y "%SRC_DIR%config.toml" "%TARGET_DIR%\config.toml" >nul
copy /Y "%SRC_DIR%auth.json" "%TARGET_DIR%\auth.json" >nul

echo Config files copied to %TARGET_DIR%
echo Existing files were backed up to .bak when present.
pause
