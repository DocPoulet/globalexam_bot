@echo off
echo ATTENTION :
echo ceci supprime la session Chromium locale du bot.
echo.
pause

if exist profile (
    rmdir /s /q profile
)

mkdir profile

echo Profil reinitialise.
pause
