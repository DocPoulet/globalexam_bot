@echo off
cd /d "%~dp0"
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" src\community_cli.py status
) else (
    python src\community_cli.py status
)
echo.
pause
