@echo off
REM One click: the clipboard in, the nmud style out, back into the clipboard.
REM The work happens on the school machine: this machine keeps the source
REM only, the interpreter and jieba live on the guest.
REM
REM   nmud-style.bat                use the config (guest/remote.cfg)
REM   nmud-style.bat -TimeoutSec 600
REM
REM Exit codes of the script: 0 = clipboard updated, 1 = failed,
REM 2 = the clipboard was empty.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0guest\style-clipboard.ps1" %*
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
timeout /t 8 /nobreak >nul 2>&1
:done
endlocal
