@echo off
rem Démarre LanguageTool et le moteur, chacun dans sa fenêtre.
rem --- À régler si besoin ---
set LT_DOSSIER=C:\LanguageTool\LanguageTool-6.6
set LT_PORT=8081
set MOTEUR_PORT=8001
rem --------------------------

cd /d "%~dp0"

if not exist "%LT_DOSSIER%\languagetool-server.jar" (
  echo LanguageTool introuvable dans %LT_DOSSIER%
  echo Corrige LT_DOSSIER en haut de demarrer.bat.
  pause
  exit /b 1
)

start "LanguageTool" /d "%LT_DOSSIER%" cmd /k java -cp languagetool-server.jar org.languagetool.server.HTTPServer --port %LT_PORT%
start "Moteur" cmd /k python -m moteur --port %MOTEUR_PORT%
