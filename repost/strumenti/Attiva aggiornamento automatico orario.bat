@echo off
rem Configura sul PC del concessionario l'aggiornamento automatico ogni ora (7:00 - 23:00) in modalità invisibile.
chcp 65001 >nul
cd /d "%~dp0"
set "VBS_PATH=%~dp0avvia_silenzioso.vbs"

echo ===========================================================================
echo   CONFIGURAZIONE AGGIORNAMENTO AUTOMATICO ORARIO (PC CONCESSIONARIO)
echo ===========================================================================
echo.
echo Assicurarsi che Python e Pillow siano installati...
python -m pip install --quiet Pillow >nul 2>nul || py -3 -m pip install --quiet Pillow >nul 2>nul

echo Registrazione attivita pianificata "RepostAutoScout24_Orario" (ogni 60 minuti dalle 07:00)...
schtasks /Create /F /TN "RepostAutoScout24_Orario" /TR "wscript.exe \"%VBS_PATH%\"" /SC HOURLY /MO 1 /ST 07:00

if %errorlevel%==0 (
  echo.
  echo [OK] Attivita pianificata creata con successo!
  echo      Il sistema aggiornera annunci e cartella Drive ogni ora in background
  echo      senza aprire alcuna finestra sullo schermo del concessionario.
) else (
  echo.
  echo [!] Errore durante la creazione dell'attivita pianificata.
)
echo.
pause
