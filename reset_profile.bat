@echo off
echo ATTENTION : suppression de la session Chromium locale.
pause
if exist profile rmdir /s /q profile
mkdir profile
echo Profil reinitialise.
pause
