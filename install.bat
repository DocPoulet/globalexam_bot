@echo off
title GlobalExam Bot v0.6 - Installation
echo =====================================
echo     GlobalExam Bot v0.6
echo =====================================
echo.
python -m venv venv
call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
echo.
echo Installation terminee.
pause
