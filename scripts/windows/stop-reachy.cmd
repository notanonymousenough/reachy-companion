@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-reachy.ps1" -PauseIfInteractive %*
exit /b %errorlevel%
