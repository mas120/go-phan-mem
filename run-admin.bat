@echo off
net session >nul 2>&1
if not %errorlevel%==0 (
  echo Requesting Administrator privileges...
  powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
title App Uninstaller (Admin)
cd /d "%~dp0"

set "PY="
where python >nul 2>&1
if not errorlevel 1 set "PY=python"
if not defined PY (
  where py >nul 2>&1
  if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
  echo [ERROR] Python was not found.
  echo Please install Python from https://www.python.org/downloads/
  pause
  exit /b 1
)

%PY% main.py
if errorlevel 1 (
  echo.
  echo [ERROR] Program exited with code %errorlevel%.
  pause
)
