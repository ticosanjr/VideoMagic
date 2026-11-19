@echo off
chcp 65001 >nul
setlocal
set "PS1=%~dp0VideoFlowGPU.ps1"
if not exist "%PS1%" (
  echo VideoFlowGPU.ps1 is missing. Extract the kit again.
  pause
  exit /b 1
)
if /I "%~1"=="--silent" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -Action Start -Silent
  exit /b %ERRORLEVEL%
)
:run
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
if errorlevel 1 (
  echo.
  echo The installer returned an error. The window will stay open.
  echo Check logs\bootstrap.log and logs\last-error.json.
  pause
  goto run
)
exit /b %ERRORLEVEL%
