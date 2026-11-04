@echo off
title Building localCAI.exe
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3.10+ is needed to BUILD the exe: https://www.python.org/downloads/ & pause & exit /b 1)
echo [1/3] Installing build tools (PyInstaller, pywebview)...
python -m pip install --upgrade --quiet pyinstaller pywebview || (echo pip install failed & pause & exit /b 1)
echo [2/3] Building localCAI.exe (takes a minute or two)...
python -m PyInstaller --noconfirm --clean --onefile --windowed --name localCAI ^
  --icon assets\logo.ico ^
  --add-data "assets\logo.ico;assets" ^
  --add-data "localcai\webui\static;localcai\webui\static" ^
  --add-data "localcai\extension;localcai\extension" ^
  --collect-all webview ^
  packaging\exe_entry.py || (echo Build failed & pause & exit /b 1)
copy /y dist\localCAI.exe localCAI.exe >nul
echo [3/3] Done: %CD%\localCAI.exe
echo Double-click localCAI.exe to start. You can move it anywhere (your chats stay in %USERPROFILE%\.localcai).
pause
