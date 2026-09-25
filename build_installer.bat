@echo off
rem ==========================================================================
rem  build_installer.bat - сборка установщика AutoSkrin-Setup.exe на своём ПК.
rem  Результат появится в папке dist:
rem    dist\AutoSkrin-Setup.exe      - установщик
rem    dist\AutoSkrin-Portable.zip   - переносная версия без установки
rem ==========================================================================
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    call "%~dp0install.bat" /quiet || goto :error
)
echo Устанавливаю PyInstaller ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check pyinstaller || goto :error

rem Inno Setup нужен для создания установщика; без него соберётся только ZIP
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=1"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=1"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=1"
if not defined ISCC (
    where winget >nul 2>nul && (
        echo Устанавливаю Inno Setup через winget ...
        winget install -e --id JRSoftware.InnoSetup --accept-package-agreements --accept-source-agreements
    )
)

".venv\Scripts\python.exe" tools\build.py || goto :error
echo.
echo Готово! Файлы находятся в папке dist.
explorer "%~dp0dist"
pause
exit /b 0

:error
echo.
echo ОШИБКА сборки - подробности выше.
pause
exit /b 1
