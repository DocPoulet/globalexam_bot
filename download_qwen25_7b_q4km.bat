@echo off
title GlobalExam Bot - Telechargement Qwen 2.5 7B Q4_K_M
echo =========================================================
echo  Telechargement du modele local Qwen 2.5 7B GGUF
echo  Aucun curl necessaire
echo =========================================================
echo.

if exist venv\Scripts\python.exe (
    echo Utilisation du Python du venv...
    venv\Scripts\python.exe download_model.py
) else (
    echo Venv absent, tentative avec Python systeme...
    python download_model.py
)

if errorlevel 1 (
    echo.
    echo Le telechargement a echoue.
    echo Verifie ta connexion Internet puis relance ce fichier.
    pause
    exit /b 1
)

echo.
echo Telechargement termine.
pause
