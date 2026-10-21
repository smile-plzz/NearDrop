@echo off
setlocal
cd /d "%~dp0"
title NearDrop - Local sharing
if not exist "runtime\python.exe" (
  echo NearDrop runtime is missing. Extract the ENTIRE download before opening this launcher.
  pause
  exit /b 1
)
"runtime\python.exe" "app\server.py"
if errorlevel 1 pause
