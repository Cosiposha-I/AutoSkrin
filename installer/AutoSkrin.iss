; ---------------------------------------------------------------------------
; Установщик AutoSkrin (Inno Setup 6, https://jrsoftware.org/isinfo.php)
;
; Обычно собирается автоматически командой:  python tools\build.py
; Вручную (после PyInstaller):               iscc /DMyAppVersion=1.0.0 installer\AutoSkrin.iss
;
; Установщик:
;   * не требует прав администратора (ставит программу в папку пользователя),
;     но по желанию можно установить «для всех пользователей»;
;   * создаёт ярлыки в меню «Пуск» и на рабочем столе;
;   * по желанию включает автозапуск вместе с Windows;
;   * закрывает запущенную программу при обновлении/удалении.
; ---------------------------------------------------------------------------

#define MyAppName "AutoSkrin"
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppExeName "AutoSkrin.exe"
#define MyAppURL "https://github.com/Cosiposha-I/AutoSkrin"

[Setup]
AppId={{6F2B8C1E-4A7D-4E59-9B3A-2C5D8E1F0A37}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppName}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename={#MyAppName}-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
MinVersion=10.0
; Мьютекс создаёт сама программа (main.py) — так установщик видит, что она запущена
AppMutex=AutoSkrinSingleInstanceMutex
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=auto

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
russian.AutorunTask=Запускать {#MyAppName} при входе в Windows (свёрнутым в трей)
english.AutorunTask=Start {#MyAppName} when Windows starts (minimized to tray)
russian.OtherTasks=Дополнительно:
english.OtherTasks=Other:

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autorun"; Description: "{cm:AutorunTask}"; GroupDescription: "{cm:OtherTasks}"; Flags: unchecked

[InstallDelete]
; При обновлении удаляем библиотеки старой версии, чтобы не осталось лишних файлов
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\AutoSkrin\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"" --minimized"; Flags: uninsdeletevalue; Tasks: autorun
; Автозапуск можно включить и в самой программе — при удалении убираем его в любом случае
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "{#MyAppName}"; Flags: uninsdeletevalue dontcreatekey

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
