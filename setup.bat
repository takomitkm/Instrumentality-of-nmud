@echo off
REM Find a python, then let setup_env.py check this device and install
REM whatever the generator is missing.
setlocal
set "SCRIPT=%~dp0setup_env.py"

py -3 "%SCRIPT%" %*
if not errorlevel 1 goto done

python "%SCRIPT%" %*
if not errorlevel 1 goto done

echo [setup] no python found. Install Python 3.9 or newer, then run this again.
timeout /t 8 /nobreak >nul
exit /b 1

:done
if not errorlevel 1 goto reallydone
timeout /t 8 /nobreak >nul
exit /b 1

:reallydone
endlocal & exit /b 0
