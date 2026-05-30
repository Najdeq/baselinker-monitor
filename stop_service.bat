@echo off
:: Zatrzymuje usługę BaseLinker Monitor
SET SERVICE_NAME=BaseLinkerMonitor
SET SCRIPT_DIR=%~dp0

NET SESSION >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Uruchom jako Administrator!
    pause
    exit /b 1
)

echo Zatrzymywanie uslug %SERVICE_NAME%...
"%SCRIPT_DIR%nssm.exe" stop %SERVICE_NAME%
echo Gotowe.
pause
