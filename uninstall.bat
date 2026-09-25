<# : batch portion
@echo off
rem =========================================================================
rem  AutoSkrin-Uninstall.bat - полное удаление AutoSkrin (любой версии).
rem  Это гибрид bat + PowerShell: bat-часть лишь запускает PowerShell-код ниже.
rem  Параметры для автоматического запуска:
rem    /y         - не спрашивать подтверждение
rem    /settings  - удалить также настройки и журнал
rem    /source    - удалить также папки с исходным кодом (установка через install.bat)
rem =========================================================================
chcp 65001 >nul
set "AUTOSKRIN_SELF=%~f0"
set "AUTOSKRIN_ARGS=%*"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-Expression ([System.IO.File]::ReadAllText($env:AUTOSKRIN_SELF))"
exit /b %errorlevel%
#>

# ---------------------------------------------------------------------------
# PowerShell-часть: поиск и удаление всех установок AutoSkrin
# ---------------------------------------------------------------------------
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$AppKeyName = '{6F2B8C1E-4A7D-4E59-9B3A-2C5D8E1F0A37}_is1'   # AppId из установщика
$Options = " $($env:AUTOSKRIN_ARGS) ".ToLower()
$AutoYes = $Options.Contains(' /y ')
$AlsoSettings = $Options.Contains(' /settings ')
$AlsoSource = $Options.Contains(' /source ')
$Errors = 0

function Say([string]$Text, [string]$Color = 'Gray') { Write-Host $Text -ForegroundColor $Color }

function Ask([string]$Question) {
    # Буква Y в русской раскладке даёт «Н», поэтому понимаем и её
    $answer = (Read-Host "$Question  [Y - да / N - нет]").Trim().ToLower()
    return @('y', 'yes', 'д', 'да', 'н') -contains $answer
}

function Remove-Safely([string]$Path, [string]$What) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    try {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
        Say "  удалено: $What" 'Green'
    } catch {
        Say "  не удалось удалить $What ($Path): $($_.Exception.Message)" 'Red'
        $global:Errors++
    }
}

Say '=============================================' 'Cyan'
Say '   Удаление AutoSkrin' 'Cyan'
Say '=============================================' 'Cyan'
Say ''

# --- 1. Что установлено ------------------------------------------------------
$installs = @()
$uninstallRoots = @(
    @{ Path = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall'; AllUsers = $false },
    @{ Path = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall'; AllUsers = $true },
    @{ Path = 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'; AllUsers = $true }
)
foreach ($root in $uninstallRoots) {
    $key = Join-Path $root.Path $AppKeyName
    if (Test-Path -LiteralPath $key) {
        $info = Get-ItemProperty -LiteralPath $key
        $installs += [pscustomobject]@{
            Key         = $key
            Uninstaller = ([string]$info.UninstallString).Trim().Trim('"')
            Location    = ([string]$info.InstallLocation).TrimEnd('\')
            Version     = [string]$info.DisplayVersion
            AllUsers    = $root.AllUsers
        }
    }
}

# Версии из исходного кода (install.bat): ярлык на рабочем столе и автозапуск указывают на main.py
$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$desktopLink = Join-Path $desktop 'AutoSkrin.lnk'
$sourceDirs = @()
if (Test-Path -LiteralPath $desktopLink) {
    $link = $shell.CreateShortcut($desktopLink)
    if ($link.Arguments -match '"?([^"]*main\.py)"?') { $sourceDirs += Split-Path -Parent $Matches[1] }
}
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$autorun = (Get-ItemProperty -LiteralPath $runKey -Name 'AutoSkrin' -ErrorAction SilentlyContinue).AutoSkrin
if ($autorun -and $autorun -match '"([^"]*main\.py)"') { $sourceDirs += Split-Path -Parent $Matches[1] }
$sourceDirs = @($sourceDirs | Where-Object { $_ -and (Test-Path -LiteralPath (Join-Path $_ 'main.py')) } | Select-Object -Unique)

$settingsDir = Join-Path $env:APPDATA 'AutoSkrin'
$startMenuDir = Join-Path ([Environment]::GetFolderPath('Programs')) 'AutoSkrin'

if (-not $installs -and -not $sourceDirs -and -not (Test-Path -LiteralPath $desktopLink) -and
    -not $autorun -and -not (Test-Path -LiteralPath $startMenuDir) -and -not (Test-Path -LiteralPath $settingsDir)) {
    Say 'AutoSkrin на этом компьютере не найден.' 'Yellow'
    Say 'Переносную версию (ZIP) удаляют простым удалением её папки.'
    if (-not $AutoYes) { Read-Host 'Нажмите Enter, чтобы закрыть окно' | Out-Null }
    exit 0
}

Say 'Найдено:' 'White'
foreach ($i in $installs) {
    $scope = if ($i.AllUsers) { 'для всех пользователей' } else { 'для текущего пользователя' }
    Say "  • AutoSkrin $($i.Version) ($scope): $($i.Location)"
}
foreach ($dir in $sourceDirs) { Say "  • AutoSkrin из исходного кода: $dir" }
if ($autorun) { Say '  • автозапуск вместе с Windows' }
if (Test-Path -LiteralPath $settingsDir) { Say "  • настройки и журнал: $settingsDir" }
Say ''
Say 'Сделанные скриншоты и документы Word удалены НЕ будут.' 'Yellow'
Say ''

if (-not $AutoYes -and -not (Ask 'Удалить AutoSkrin?')) {
    Say 'Отменено, ничего не удалено.'
    Read-Host 'Нажмите Enter, чтобы закрыть окно' | Out-Null
    exit 0
}

# --- 2. Закрываем запущенную программу ------------------------------------------
Get-Process -Name 'AutoSkrin' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
if ($sourceDirs) {
    Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' or Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $cmd = $_.CommandLine; $cmd -and ($sourceDirs | Where-Object { $cmd.Contains($_) }) } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
Start-Sleep -Seconds 1

# --- 3. Установленные версии: штатный деинсталлятор ---------------------------------
foreach ($i in $installs) {
    Say "Удаляю AutoSkrin $($i.Version) из $($i.Location) ..." 'White'
    if ($i.Uninstaller -and (Test-Path -LiteralPath $i.Uninstaller)) {
        try {
            $params = @{ FilePath = $i.Uninstaller; ArgumentList = '/SILENT /SUPPRESSMSGBOXES /NORESTART'; Wait = $true }
            if ($i.AllUsers) { $params.Verb = 'RunAs' }   # установка «для всех» — нужны права администратора
            Start-Process @params
            # Деинсталлятор перезапускает себя из временной папки — ждём, пока он закончит
            $deadline = (Get-Date).AddMinutes(3)
            while ((Test-Path -LiteralPath $i.Key) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 1 }
        } catch {
            Say "  не удалось запустить деинсталлятор: $($_.Exception.Message)" 'Red'
        }
    }
    if (Test-Path -LiteralPath $i.Key) {
        # Деинсталлятора нет или он не сработал — убираем вручную то, что можем
        if ($i.Location) { Remove-Safely $i.Location 'папка программы' }
        Remove-Safely $i.Key 'запись в списке программ Windows'
    } else {
        Say '  программа удалена' 'Green'
    }
}

# --- 4. Версии из исходного кода --------------------------------------------------
foreach ($dir in $sourceDirs) {
    if ($AlsoSource -or (-not $AutoYes -and (Ask "Удалить папку с исходным кодом «$dir»?"))) {
        Remove-Safely $dir 'папка с исходным кодом'
    } else {
        Remove-Safely (Join-Path $dir '.venv') 'виртуальное окружение Python (.venv)'
        Say "  папка с исходным кодом оставлена: $dir"
    }
}

# --- 5. Остатки: ярлыки, автозапуск, временные файлы -------------------------------
Remove-Safely $desktopLink 'ярлык на рабочем столе'
Remove-Safely $startMenuDir 'папка в меню «Пуск»'
if (Get-ItemProperty -LiteralPath $runKey -Name 'AutoSkrin' -ErrorAction SilentlyContinue) {
    try {
        Remove-ItemProperty -LiteralPath $runKey -Name 'AutoSkrin' -ErrorAction Stop
        Say '  удалено: автозапуск вместе с Windows' 'Green'
    } catch { Say "  не удалось убрать автозапуск: $($_.Exception.Message)" 'Red'; $Errors++ }
}
Remove-Safely (Join-Path $env:TEMP 'AutoSkrin') 'временные файлы'

# --- 6. Настройки ------------------------------------------------------------------
if (Test-Path -LiteralPath $settingsDir) {
    if ($AlsoSettings -or (-not $AutoYes -and (Ask 'Удалить также настройки и журнал программы?'))) {
        Remove-Safely $settingsDir 'настройки и журнал'
    } else {
        Say "  настройки оставлены: $settingsDir"
    }
}

Say ''
if ($Errors -eq 0) {
    Say 'Готово! AutoSkrin удалён.' 'Green'
} else {
    Say "Готово, но с ошибками: $Errors. Подробности выше." 'Yellow'
}
if (-not $AutoYes) { Read-Host 'Нажмите Enter, чтобы закрыть окно' | Out-Null }
exit $(if ($Errors -eq 0) { 0 } else { 1 })
