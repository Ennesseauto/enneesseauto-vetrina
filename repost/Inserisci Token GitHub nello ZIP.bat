@echo off
chcp 65001 >nul
title Inserisci Chiave GitHub nel Pacchetto ZIP Concessionario
cd /d "%~dp0"
python "strumenti\crea_pacchetto_zip.py" --chiedi-token
pause
