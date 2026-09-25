@echo off
rem ==========================================================================
rem  install.bat - установка AutoSkrin из исходного кода.
rem  Находит Python 3.10+ (при необходимости ставит через winget), создаёт
rem  виртуальное окружение .venv, ставит зависимости и делает ярлык на рабочем столе.
rem  Параметр /quiet - без ярлыка и вопросов (используется build_installer.bat).
rem ==========================================================================
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
set "QUIET="
if /i "%~1"=="/quiet" set "QUIET=1"

echo ==============================================
echo    Установка AutoSkrin из исходного кода
echo ==============================================
echo.

rem --- 1. Ищем Python 3.10 или новее ---
set "PY="
call :try_python py -3
if not defined PY call :try_python python
if not defined PY call :try_python "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY call :install_python
if not defined PY goto :no_python
echo Используется Python: %PY%
echo.

rem --- 2. Виртуальное окружение и зависимости ---
if not exist ".venv\Scripts\python.exe" (
    echo Создаю виртуальное окружение .venv ...
    %PY% -m venv .venv || goto :error
)
echo Устанавливаю библиотеки, это займёт 1-2 минуты ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt || goto :error
echo.
if defined QUIET exit /b 0

rem --- 3. Ярлык на рабочем столе ---
set "APPDIR=%~dp0"
if "%APPDIR:~-1%"=="\" set "APPDIR=%APPDIR:~0,-1%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=$env:APPDIR; $q=[char]34; $w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'AutoSkrin.lnk')); $s.TargetPath=Join-Path $d '.venv\Scripts\pythonw.exe'; $s.Arguments=$q + (Join-Path $d 'main.py') + $q; $s.WorkingDirectory=$d; $s.IconLocation=Join-Path $d 'assets\icon.ico'; $s.Save()"
if errorlevel 1 (
    echo Не удалось создать ярлык - программу можно запускать файлом run.bat
) else (
    echo Ярлык AutoSkrin создан на рабочем столе.
)

echo.
echo ==============================================
echo    Готово! AutoSkrin установлен.
echo ==============================================
choice /c YN /m "Запустить AutoSkrin сейчас"
if errorlevel 2 exit /b 0
start "" ".venv\Scripts\pythonw.exe" "%~dp0main.py"
exit /b 0

rem --------------------------------------------------------------------------
:try_python
rem Проверяет, что команда запускает Python версии 3.10+
%* -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=%*"
exit /b 0

:install_python
where winget >nul 2>nul || exit /b 0
echo Python 3.10+ не найден. Устанавливаю Python 3.12 через winget ...
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
call :try_python "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
exit /b 0

:no_python
echo.
echo Python 3.10 или новее не найден и не был установлен автоматически.
echo Установите Python с сайта https://www.python.org/downloads/
echo При установке отметьте галочку "Add python.exe to PATH", затем запустите install.bat снова.
start "" "https://www.python.org/downloads/"
if not defined QUIET pause
exit /b 1

:error
echo.
echo ОШИБКА: установка не завершена. Проверьте подключение к интернету и попробуйте снова.
if not defined QUIET pause
exit /b 1
