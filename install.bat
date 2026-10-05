@echo off
title GlobalExam Bot v0.8 - Installation
echo =====================================
echo       GlobalExam Bot v0.8
echo =====================================
echo.

if exist venv (
    echo Un environnement virtuel existe deja.
    echo S'il vient d'un autre PC et pose probleme, supprime le dossier venv.
    echo.
)

if not exist venv\Scripts\python.exe (
    python -m venv venv
)

call venv\Scripts\activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium

echo.
echo Installation terminee.
pause
