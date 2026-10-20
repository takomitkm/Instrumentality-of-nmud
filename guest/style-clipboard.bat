@echo off
REM One click: take the clipboard, lay it out in the nmud style on the
REM school machine, put the result back into the clipboard.
REM
REM   style-clipboard.bat            use the config (remote.cfg)
REM   style-clipboard.bat -TimeoutSec 600
REM
REM Exit codes of the script: 0 = clipboard updated, 1 = failed,
REM 2 = the clipboard was empty.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0style-clipboard.ps1" %*
if errorlevel 2 goto nothing
if errorlevel 1 goto failed
echo.
echo The clipboard now holds the nmud layout. This window closes in 4s.
timeout /t 4 /nobreak >nul 2>&1
goto done
:nothing
echo.
echo The clipboard was empty - nothing was done.
goto done
:failed
echo.
echo FAILED - the message above says what went wrong
pause
:done
endlocal
