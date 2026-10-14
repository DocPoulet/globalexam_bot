@echo off
setlocal
cd /d "%~dp0"
title GlobalExam Bot - Serveur communautaire local

echo ==========================================================
echo  Serveur communautaire V0.10.14 - test LOCAL uniquement
echo ==========================================================
echo.
if not exist "server\.env" (
  echo ERREUR : server\.env absent.
  echo Copie server\.env.example en server\.env, puis remplace le mot de passe.
  pause
  exit /b 1
)

where docker >nul 2>nul
if errorlevel 1 (
  echo Docker est absent. Installe et demarre Docker Desktop.
  pause
  exit /b 1
)

docker compose --env-file server/.env -f server/compose.yaml up -d --build
if errorlevel 1 (
  echo Impossible de demarrer PostgreSQL/API.
  pause
  exit /b 1
)

docker compose --env-file server/.env -f server/compose.yaml run --rm api python -m server.admin init-db
if errorlevel 1 (
  echo Echec initialisation PostgreSQL.
  pause
  exit /b 1
)

echo.
echo API locale : http://127.0.0.1:8000/healthz
echo Upload desactive par defaut. Le bot n'envoie aucune contribution.
pause
