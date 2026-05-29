@echo off
echo [1/3] Cleaning old build files...
python clean_build.py
echo.

echo Choose packaging mode:
echo   [1] Folder Mode (Recommended: avoids antivirus lockups, faster startup)
echo   [2] Single-File Mode (Requires disabling antivirus or whitelisting directory)
set /p mode="Enter choice [1 or 2]: "

if "%mode%"=="2" (
    echo [2/3] Running PyInstaller in Single-File Mode...
    pyinstaller --clean --noconfirm VibePet.spec
    echo [3/3] Packaging complete!
    echo Output directory: dist\
    echo Executable file: dist\VibePet.exe
) else (
    echo [2/3] Running PyInstaller in Folder Mode...
    pyinstaller --clean --noconfirm VibePet_onedir.spec
    echo [3/3] Packaging complete!
    echo Output directory: dist\VibePet\
    echo Executable file: dist\VibePet\VibePet.exe
)
pause
