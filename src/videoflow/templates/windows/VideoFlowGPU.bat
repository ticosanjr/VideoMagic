@echo off
chcp 65001 >nul
setlocal
set "PS1=%~dp0VideoFlowGPU.ps1"
if not exist "%PS1%" (
  echo VideoFlowGPU.ps1 is missing. Download the kit again.
  pause
  exit /b 1
)
if /I "%~1"=="--silent" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -Action Start -Silent
  exit /b %ERRORLEVEL%
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
if errorlevel 1 pause
exit /b %ERRORLEVEL%
