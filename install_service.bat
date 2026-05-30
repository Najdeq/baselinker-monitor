@echo off
:: ============================================================
:: BaseLinker Monitor – Instalator usługi Windows
:: ============================================================
:: Wymaga NSSM (Non-Sucking Service Manager) - darmowe narzędzie
:: Pobierz z: https://nssm.cc/download
:: Wypakuj nssm.exe do tego samego folderu co ten plik
:: Następnie uruchom install_service.bat jako Administrator
:: ============================================================

SET SERVICE_NAME=BaseLinkerMonitor
SET SCRIPT_DIR=%~dp0
SET PYTHON_PATH=

:: Znajdź Pythona automatycznie
FOR /F "tokens=*" %%i IN ('where python 2^>nul') DO (
    IF NOT DEFINED PYTHON_PATH SET PYTHON_PATH=%%i
)

IF NOT DEFINED PYTHON_PATH (
    echo [BLAD] Python nie znaleziony w PATH.
    echo Zainstaluj Python z https://python.org i zaznacz "Add to PATH"
    pause
    exit /b 1
)

echo [INFO] Python znaleziony: %PYTHON_PATH%

:: Sprawdź czy nssm.exe istnieje
IF NOT EXIST "%SCRIPT_DIR%nssm.exe" (
    echo [BLAD] Nie znaleziono nssm.exe w folderze skryptu.
    echo Pobierz z https://nssm.cc/download i wypakuj nssm.exe tutaj:
    echo %SCRIPT_DIR%
    pause
    exit /b 1
)

:: Sprawdź czy uruchomiono jako Administrator
NET SESSION >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [BLAD] Uruchom ten plik jako Administrator!
    echo Kliknij prawym przyciskiem na install_service.bat → Uruchom jako administrator
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Instalacja uslug Windows: %SERVICE_NAME%
echo ============================================================
echo.

:: Zatrzymaj i usuń starą usługę jeśli istnieje
"%SCRIPT_DIR%nssm.exe" stop %SERVICE_NAME% 2>nul
"%SCRIPT_DIR%nssm.exe" remove %SERVICE_NAME% confirm 2>nul

:: Zainstaluj nową usługę
"%SCRIPT_DIR%nssm.exe" install %SERVICE_NAME% "%PYTHON_PATH%" "%SCRIPT_DIR%price_monitor.py"

:: Konfiguracja usługi
"%SCRIPT_DIR%nssm.exe" set %SERVICE_NAME% DisplayName "BaseLinker Monitor Cen"
"%SCRIPT_DIR%nssm.exe" set %SERVICE_NAME% Description "Monitoruje ceny konkurencji w BaseLinker i wysyla alerty na Discord"
"%SCRIPT_DIR%nssm.exe" set %SERVICE_NAME% AppDirectory "%SCRIPT_DIR%"
"%SCRIPT_DIR%nssm.exe" set %SERVICE_NAME% AppStdout "%SCRIPT_DIR%monitor.log"
"%SCRIPT_DIR%nssm.exe" set %SERVICE_NAME% AppStderr "%SCRIPT_DIR%monitor_error.log"
"%SCRIPT_DIR%nssm.exe" set %SERVICE_NAME% AppRotateFiles 1
"%SCRIPT_DIR%nssm.exe" set %SERVICE_NAME% AppRotateBytes 5242880
"%SCRIPT_DIR%nssm.exe" set %SERVICE_NAME% Start SERVICE_AUTO_START

:: Ustaw zmienne środowiskowe dla usługi (wczytaj z .env)
IF EXIST "%SCRIPT_DIR%.env" (
    FOR /F "usebackq tokens=1,2 delims==" %%A IN ("%SCRIPT_DIR%.env") DO (
        IF NOT "%%A"=="" IF NOT "%%B"=="" (
            "%SCRIPT_DIR%nssm.exe" set %SERVICE_NAME% AppEnvironmentExtra "%%A=%%B"
        )
    )
    echo [INFO] Wczytano konfiguracje z .env
) ELSE (
    echo [UWAGA] Brak pliku .env - upewnij sie ze zmienne BL_API_TOKEN i DISCORD_WEBHOOK_URL sa ustawione
)

:: Uruchom usługę
"%SCRIPT_DIR%nssm.exe" start %SERVICE_NAME%

echo.
echo ============================================================
IF %ERRORLEVEL% EQU 0 (
    echo  [OK] Usluga "%SERVICE_NAME%" zainstalowana i uruchomiona!
    echo.
    echo  Sprawdz status:   services.msc → BaseLinker Monitor Cen
    echo  Podglad logow:    monitor.log (w tym folderze)
    echo  Zatrzymanie:      stop_service.bat
) ELSE (
    echo  [BLAD] Cos poszlo nie tak. Sprawdz monitor_error.log
)
echo ============================================================
echo.
pause
