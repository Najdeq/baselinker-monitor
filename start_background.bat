@echo off
SET SCRIPT_DIR=%~dp0

FOR /F "tokens=*" %%i IN ('where pythonw 2^>nul') DO (
    SET PYTHONW=%%i
    GOTO :found
)
echo [BLAD] Nie znaleziono pythonw.exe – zainstaluj Python z python.org
pause & exit /b 1

:found
echo [INFO] Uruchamiam monitor + panel webowy w tle...
START "" "%PYTHONW%" "%SCRIPT_DIR%price_monitor.py"
timeout /t 3 >nul
echo [OK] Gotowe! Otwieram panel...
start http://localhost:5000
echo.
echo Panel: http://localhost:5000
echo Logi:  %SCRIPT_DIR%monitor.log
echo Zatrzymanie: Menedzer zadan → pythonw.exe → Zakoncz zadanie
pause
