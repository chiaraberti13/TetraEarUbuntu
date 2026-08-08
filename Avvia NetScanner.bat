@echo off
REM ============================================================
REM  Avvia NetScanner.bat -- Pannello passivo Network Info TETRA
REM  Uso:  "Avvia NetScanner.bat" [FREQUENZA_MHz]
REM  Il pannello LIVE gira in WSL (dove c'e' il ricevitore TETRA).
REM  Senza WSL viene mostrato il solo calcolo antenna (offline).
REM ============================================================
setlocal
set "FREQ=%~1"
if "%FREQ%"=="" set "FREQ=392.225"
where wsl >nul 2>nul
if %errorlevel%==0 (
  echo [info] Avvio del pannello Network Info dentro WSL su %FREQ% MHz ...
  echo [info] ^(Live: richiede la catena TELIVE-2 gia' compilata in WSL^)
  wsl -e bash -lic "cd \"$(wslpath -a '%~dp0')\" 2>/dev/null && ./avvia_netscanner.sh %FREQ%"
) else (
  echo [info] WSL non trovato: mostro il calcolo antenna ^(offline^).
  python "%~dp0tetra_netscanner.py" --antenna %FREQ%
  echo.
  echo Per il pannello LIVE installa WSL2 e la catena TELIVE-2:
  echo     python install_telive2_windows.py
)
endlocal
pause
