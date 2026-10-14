@echo off
setlocal
cd /d "%~dp0"
title GlobalExam Bot - Moteur ancien site NON ADAPTE
 echo.
 echo ATTENTION : le moteur automatique precedent n'est pas compatible
 echo avec la nouvelle interface. Il peut cliquer aux mauvais endroits.
 echo.
 choice /C ON /N /M "Lancer quand meme l'ancien moteur ? (O/N) "
 if errorlevel 2 exit /b 0
 if exist "venv\Scripts\python.exe" (
     "venv\Scripts\python.exe" src\main.py
 ) else (
     echo Lance install.bat avant.
 )
pause
