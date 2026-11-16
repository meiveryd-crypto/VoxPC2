@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === VoxPC: сборка VoxPC.exe ===

python --version >nul 2>&1 || (echo Установите Python 3.10+ с python.org ^(галочка "Add to PATH"^) & pause & exit /b 1)

python -m pip install --upgrade pip
python -m pip install -r requirements.txt || (echo Ошибка установки зависимостей & pause & exit /b 1)

python -c "import system; system.save_ico('icon.ico')"

python -m PyInstaller --noconfirm --clean --onefile --windowed --name VoxPC ^
  --icon icon.ico ^
  --add-data "setup_wol.ps1;." ^
  --collect-data customtkinter ^
  --hidden-import pyttsx3.drivers --hidden-import pyttsx3.drivers.sapi5 ^
  --hidden-import pystray._win32 ^
  main.py

echo.
echo Готово: dist\VoxPC.exe
pause
