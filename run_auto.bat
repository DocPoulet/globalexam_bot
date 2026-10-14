@echo off
setlocal
cd /d "%~dp0"
title GlobalExam Bot v0.10.12 - AutoPilot hybride
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" src\main.py
) else (
    echo Environnement Python absent. Lance install.bat d'abord.
)
pause
