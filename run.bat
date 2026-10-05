@echo off
title GlobalExam Bot v0.7.3
if not exist venv\Scripts\python.exe (
    echo Lance install.bat d'abord.
    pause
    exit /b 1
)
call venv\Scripts\activate
python src\main.py
pause
