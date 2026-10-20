@echo off
REM Set the school machine up: check what it is missing and install it.
REM
REM   setup-guest.bat
REM   setup-guest.bat -TimeoutSec 900
REM
REM The package is pushed to the guest first, then the guest checks its own
REM environment (the virtual environment, jieba, the data files) and
REM installs what is missing. Nothing is installed on this machine.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0guest\setup-guest.ps1" %*
echo.
echo This window closes in 10s.
timeout /t 10 /nobreak >nul 2>&1
endlocal
