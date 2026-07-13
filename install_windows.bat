@echo off
setlocal enabledelayedexpansion
REM ============================================================
REM  install_windows.bat -- Avvio automatico installer TetraEar
REM ============================================================
REM  Fai doppio clic su questo file (oppure tasto destro >
REM  "Esegui come amministratore"). Si occupa di:
REM    1) chiedere i permessi di amministratore se non li ha gia';
REM    2) installare Python se manca (tramite winget);
REM    3) avviare install_windows.py, che fa tutto il resto.
REM ============================================================

title Installer TetraEar per Windows

REM --- 1) Auto-elevazione a amministratore ------------------
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Richiedo i permessi di amministratore...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

echo ============================================================
echo   Installer TetraEar per Windows
echo ============================================================
echo.

REM --- 2) Cerco un interprete Python gia' presente ----------
set "PYTHON_CMD="

where py >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=py -3"
    goto :python_found
)

where python >nul 2>&1
if %errorlevel% equ 0 (
    REM Su Windows "python" senza installazione apre lo Store: verifichiamo che risponda davvero.
    python --version >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_CMD=python"
        goto :python_found
    )
)

REM --- 3) Python non trovato: lo installo con winget ---------
echo Python non risulta installato. Provo a installarlo con winget...
where winget >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [ERRORE] winget non e' disponibile su questo sistema.
    echo Installa Python 3 manualmente da https://www.python.org/downloads/
    echo ricordandoti di spuntare "Add python.exe to PATH", poi rilancia questo file.
    echo.
    pause
    exit /b 1
)

winget install --id Python.Python.3.12 -e --scope machine ^
    --accept-source-agreements --accept-package-agreements --silent
if %errorlevel% neq 0 (
    echo.
    echo [ERRORE] Installazione di Python fallita. Installalo a mano da python.org e rilancia.
    echo.
    pause
    exit /b 1
)

REM Dopo l'installazione il PATH della sessione corrente non e' aggiornato:
REM cerco python.exe nei percorsi tipici di installazione.
for %%D in (
    "%ProgramFiles%\Python312\python.exe"
    "%ProgramFiles%\Python311\python.exe"
    "%LocalAppData%\Programs\Python\Python312\python.exe"
    "%LocalAppData%\Programs\Python\Python311\python.exe"
) do (
    if exist "%%~D" (
        set "PYTHON_CMD=%%~D"
        goto :python_found
    )
)

REM Ultimo tentativo: il launcher "py" dovrebbe esserci ora.
where py >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=py -3"
    goto :python_found
)

echo.
echo [ATTENZIONE] Python e' stato installato ma non e' ancora nel PATH di questa sessione.
echo Chiudi questa finestra e rilancia install_windows.bat: la seconda volta funzionera'.
echo.
pause
exit /b 1

:python_found
echo Uso Python: %PYTHON_CMD%
echo.
echo Avvio l'installer vero e proprio (install_windows.py)...
echo Tutti i dettagli verranno salvati in install.log
echo.

%PYTHON_CMD% "%~dp0install_windows.py" %*
set "EXITCODE=%errorlevel%"

echo.
if "%EXITCODE%"=="0" (
    echo ============================================================
    echo   Installazione completata. Puoi chiudere questa finestra.
    echo ============================================================
) else (
    echo ============================================================
    echo   L'installer ha segnalato un problema (codice %EXITCODE%^).
    echo   Controlla il file install.log per i dettagli.
    echo ============================================================
)
echo.
pause
exit /b %EXITCODE%
