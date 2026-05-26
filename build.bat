@echo off
echo [1/3] Cleaning old build files...
python clean_build.py

echo [2/3] Running PyInstaller...
pyinstaller --clean --noconfirm VibePet.spec

echo [3/3] Packaging complete!
echo Output directory: dist\
echo Executable file: dist\VibePet.exe
pause
