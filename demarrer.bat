@echo off
rem Met à jour le dépôt depuis GitHub, puis démarre LanguageTool et le moteur, chacun dans sa fenêtre.
rem --- À régler si besoin ---
set LT_DOSSIER=C:\LanguageTool\LanguageTool-6.6
set LT_PORT=8081
set MOTEUR_PORT=8001
rem --------------------------

rem PIÈGE : demarrer.bat fait partie du dépôt, et cmd.exe lit un .bat ligne par ligne,
rem par décalage dans le fichier. Si « git pull » le modifie pendant qu'il tourne,
rem cmd lirait la suite au mauvais endroit. On se copie donc dans %TEMP% et on
rem exécute la copie (argument --copie pour ne pas boucler) : la copie, elle, n'est
rem jamais touchée par git. Le .bat d'origine ne reprend jamais la main (exit /b).
rem Si la copie échoue, on continue directement, sans mise à jour.
chcp 65001 >nul
if /i "%~1"=="--copie" goto :copie_en_cours
copy /y "%~f0" "%TEMP%\demarrer_copie.bat" >nul 2>&1
if errorlevel 1 goto :copie_impossible
call "%TEMP%\demarrer_copie.bat" --copie "%~dp0"
exit /b %errorlevel%

:copie_impossible
echo Mise a jour sautee : copie de demarrer.bat impossible.
set MAJ_SAUTEE=1
cd /d "%~dp0"
goto :suite

:copie_en_cours
cd /d "%~2"
if errorlevel 1 goto :depot_introuvable
goto :maj
:depot_introuvable
echo Dossier du depot introuvable.
pause
exit /b 1

:maj

rem --- Mise à jour (jamais destructive : pas de reset ni de stash) ---
where git >nul 2>&1
if errorlevel 1 (
  echo Mise a jour sautee : git introuvable.
  goto :version
)
set "BRANCHE="
for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "BRANCHE=%%b"
if not defined BRANCHE (
  echo Mise a jour sautee : ce dossier n'est pas un depot git.
  goto :version
)
if /i not "%BRANCHE%"=="main" (
  echo Mise a jour sautee : branche %BRANCHE% ^(il faut main^).
  goto :version
)
set "MODIF="
for /f "delims=" %%s in ('git status --porcelain -uno 2^>nul') do set "MODIF=1"
if defined MODIF (
  echo Mise a jour sautee : modifications locales.
  goto :version
)
set "AVANT="
for /f %%h in ('git rev-parse HEAD 2^>nul') do set "AVANT=%%h"
echo Mise a jour depuis GitHub...
git pull --ff-only
if errorlevel 1 (
  echo Mise a jour impossible ^(pas d'Internet ou erreur git^) : demarrage avec la version actuelle.
  goto :version
)
set "APRES="
for /f %%h in ('git rev-parse HEAD 2^>nul') do set "APRES=%%h"
if "%AVANT%"=="%APRES%" goto :version
git diff --quiet %AVANT% %APRES% -- pyproject.toml
if errorlevel 1 (
  echo pyproject.toml a change : installation des dependances...
  if defined DEMARRER_ESSAI (
    echo [essai] python -m pip install -e .
  ) else (
    python -m pip install -e .
    if errorlevel 1 echo Installation des dependances echouee : le moteur pourrait ne pas demarrer.
  )
)

:version
echo Version :
git log -1 --oneline 2>nul

:suite
if defined DEMARRER_ESSAI (
  echo [essai] LanguageTool et moteur non lances.
  exit /b 0
)

if not exist "%LT_DOSSIER%\languagetool-server.jar" (
  echo LanguageTool introuvable dans %LT_DOSSIER%
  echo Corrige LT_DOSSIER en haut de demarrer.bat.
  pause
  exit /b 1
)

start "LanguageTool" /d "%LT_DOSSIER%" cmd /k java -cp languagetool-server.jar org.languagetool.server.HTTPServer --port %LT_PORT%
start "Moteur" cmd /k python -m moteur --port %MOTEUR_PORT%
