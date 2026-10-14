@echo off
title GlobalExam Bot - Installation LLM local
echo ============================================
echo   Installation llama-cpp-python - CPU local
echo ============================================
echo.

if not exist venv\Scripts\python.exe (
    echo Le venv n'existe pas.
    echo Lance d'abord install.bat.
    pause
    exit /b 1
)

call venv\Scripts\activate

python -m pip install --upgrade pip

echo.
echo Tentative d'installation du wheel CPU precompile officiel...
python -m pip install --upgrade llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

if errorlevel 1 (
    echo.
    echo Le wheel CPU n'a pas fonctionne.
    echo Tentative d'installation standard, qui peut compiler llama.cpp...
    python -m pip install --upgrade llama-cpp-python
)

if errorlevel 1 (
    echo.
    echo ERREUR : llama-cpp-python n'a pas pu etre installe.
    echo Consulte la documentation llama-cpp-python pour ton Python/GPU.
    pause
    exit /b 1
)

echo.
python -c "from llama_cpp import Llama; print('llama-cpp-python : OK')"

echo.
echo Installation du moteur local terminee.
echo Ensuite lance download_qwen25_7b_q4km.bat si tu n'as pas encore le GGUF.
pause
