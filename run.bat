@echo off
rem run.bat - запуск AutoSkrin из исходного кода (без окна консоли)
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Программа ещё не установлена - запускаю install.bat
    call "%~dp0install.bat"
    exit /b
)
start "" ".venv\Scripts\pythonw.exe" "%~dp0main.py" %*
