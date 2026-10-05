@echo off
title GlobalExam Bot v0.6

if not exist venv\Scripts\python.exe (
    echo Le projet n'est pas installe.
    echo Lance install.bat d'abord.
    pause
    exit /b 1
)

call venv\Scripts\activate
python src\main.py
pause
