@echo off
title Start VibePet
echo Starting VibePet...

if exist "dist\VibePet.exe" (
    start "" dist\VibePet.exe
) else if exist "dist\VibePet\VibePet.exe" (
    cd dist\VibePet
    start "" VibePet.exe
) else (
    start "" pythonw main.py
)

exit
