@echo off
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_worker.ps1"
pause
