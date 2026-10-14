@echo off
setlocal
cd /d "%~dp0"
title GlobalExam Bot v0.10.9 - Navigation guidee par URL
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" src\site_v2\guided.py
) else (
    echo Python virtuel absent. Lance install.bat d'abord.
)
pause
