@echo off
echo Suppression du profil Chromium local...
pause
if exist profile rmdir /s /q profile
mkdir profile
echo Profil reinitialise.
pause
