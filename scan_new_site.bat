@echo off
setlocal
cd /d "%~dp0"
title GlobalExam Bot v0.10.1 - Analyse nouvelle interface
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" src\scan_new_site.py
) else (
    echo Environnement Python absent. Lance install.bat.
    pause
    exit /b 1
)
pause
