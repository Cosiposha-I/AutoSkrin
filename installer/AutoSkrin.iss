; ---------------------------------------------------------------------------
; Установщик AutoSkrin (Inno Setup 6, https://jrsoftware.org/isinfo.php)
;
; Обычно собирается автоматически командой:  python tools\build.py
; Вручную (после PyInstaller):               iscc /DMyAppVersion=1.1.1 installer\AutoSkrin.iss
;
; Всё настраивается в мастере установки:
;   * для кого ставить: только для себя (без прав администратора) или для всех;
;   * куда ставить (любая папка);
;   * состав: только программа или программа + исходный код на Python;
;   * папка в меню «Пуск» (или без неё), ярлык на рабочем столе, автозапуск;
;   * настройки программы: куда сохранять скриншоты (папка и/или документ Word),
;     что снимать, формат, интервалы, порог, уведомления, трей;
;   * при обновлении — оставить текущие настройки или заменить их;
;   * при удалении — удалить ли настройки программы.
;
; Тихая установка (для администраторов), пример:
;   AutoSkrin-Setup.exe /VERYSILENT /CURRENTUSER /DIR="D:\Программы\AutoSkrin"
;       /COMPONENTS="main,source" /TASKS="desktopicon,autorun"
;       /SHOTSDIR="D:\Лекции" /SAVETODOCX=1 /DOCX="D:\Лекции\Конспект.docx"
;       /CAPTURE=region /FORMAT=jpg /INTERVAL=1 /THRESHOLD=1 /MININTERVAL=5
;       /NOTIFY=1 /AUTOSTARTMON=0 /TRAY=1 /KEEPSETTINGS=1
; Все параметры описаны в README.md.
; ---------------------------------------------------------------------------

#define MyAppName "AutoSkrin"
#ifndef MyAppVersion
  #define MyAppVersion "1.1.1"
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
; Показываем все страницы мастера: пользователь сам решает, куда и что ставить
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=no
AllowNoIcons=yes
; По умолчанию — установка только для себя (без прав администратора);
; в первом окне можно выбрать установку для всех пользователей
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
OutputDir=..\dist
OutputBaseFilename={#MyAppName}-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=120
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
russian.TypeFull=Полная установка (программа и исходный код)
english.TypeFull=Full installation (program and source code)
russian.TypeCompact=Только программа
english.TypeCompact=Program only
russian.TypeCustom=Выборочная установка
english.TypeCustom=Custom installation
russian.CompMain=Программа AutoSkrin
english.CompMain=AutoSkrin program
russian.CompSource=Исходный код на Python (для разработчиков)
english.CompSource=Python source code (for developers)
russian.AutorunTask=Запускать {#MyAppName} при входе в Windows (свёрнутым в трей)
english.AutorunTask=Start {#MyAppName} when Windows starts (minimized to tray)
russian.OtherTasks=Дополнительно:
english.OtherTasks=Other:
russian.ShortcutManual=Инструкция {#MyAppName}
english.ShortcutManual={#MyAppName} manual
russian.OpenManual=Открыть инструкцию
english.OpenManual=Open the manual
russian.SavePageTitle=Куда сохранять скриншоты
english.SavePageTitle=Where to save screenshots
russian.SavePageDescription=Это начальные настройки — их можно менять в любой момент в окне программы.
english.SavePageDescription=These are initial settings — you can change them at any time in the program window.
russian.KeepSettings=Оставить текущие настройки программы (найдены от прошлой установки)
english.KeepSettings=Keep current program settings (found from a previous installation)
russian.SaveToFolder=Сохранять скриншоты файлами PNG/JPG в папку:
english.SaveToFolder=Save screenshots as PNG/JPG files to a folder:
russian.SaveToDocx=Добавлять скриншоты в документ Word (конспект, который заполняется сам):
english.SaveToDocx=Append screenshots to a Word document (self-filling notes):
russian.Browse=Обзор...
english.Browse=Browse...
russian.BrowseFolderPrompt=Выберите папку для скриншотов:
english.BrowseFolderPrompt=Choose a folder for screenshots:
russian.BrowseDocxPrompt=Документ Word для скриншотов
english.BrowseDocxPrompt=Word document for screenshots
russian.DocxFilter=Документ Word (*.docx)|*.docx
english.DocxFilter=Word document (*.docx)|*.docx
russian.DefaultDocName=Конспект.docx
english.DefaultDocName=Notes.docx
russian.CaptureLabel=Что снимать:
english.CaptureLabel=What to capture:
russian.CaptureRegion=Только выбранную область
english.CaptureRegion=Selected region only
russian.CaptureScreen=Весь экран (монитор с областью)
english.CaptureScreen=Whole screen (monitor with the region)
russian.CaptureAll=Все мониторы целиком
english.CaptureAll=All monitors
russian.FormatLabel=Формат файлов:
english.FormatLabel=File format:
russian.FormatPng=PNG (без потерь)
english.FormatPng=PNG (lossless)
russian.FormatJpg=JPG (меньше размер)
english.FormatJpg=JPG (smaller files)
russian.DetectPageTitle=Как замечать изменения
english.DetectPageTitle=Change detection
russian.DetectPageDescription=Это начальные настройки — их можно менять в любой момент в окне программы.
english.DetectPageDescription=These are initial settings — you can change them at any time in the program window.
russian.IntervalLabel=Интервал проверки, сек:
english.IntervalLabel=Check interval, sec:
russian.ThresholdLabel=Порог чувствительности, % пикселей:
english.ThresholdLabel=Sensitivity threshold, % of pixels:
russian.MinIntervalLabel=Мин. интервал между снимками, сек:
english.MinIntervalLabel=Min. interval between shots, sec:
russian.NotifyCheck=Уведомление в трее при каждом скриншоте
english.NotifyCheck=Tray notification for every screenshot
russian.AutoStartCheck=Запускать мониторинг сразу при старте программы
english.AutoStartCheck=Start monitoring as soon as the program starts
russian.TrayCheck=Сворачивать в трей при закрытии окна
english.TrayCheck=Minimize to tray when the window is closed
russian.ErrNoTarget=Выберите, куда сохранять скриншоты: папку и/или документ Word.
english.ErrNoTarget=Choose where to save screenshots: a folder and/or a Word document.
russian.ErrNoFolder=Укажите папку для скриншотов.
english.ErrNoFolder=Specify a folder for screenshots.
russian.ErrDocx=Документ Word должен иметь расширение .docx.
english.ErrDocx=The Word document must have the .docx extension.
russian.ErrNumber=Введите числа, например 1 или 0,5.
english.ErrNumber=Enter numbers, e.g. 1 or 0.5.
russian.ReadySettings=Настройки программы:
english.ReadySettings=Program settings:
russian.ReadyKeep=останутся прежними
english.ReadyKeep=kept unchanged
russian.ReadyFolder=Папка для скриншотов:
english.ReadyFolder=Screenshot folder:
russian.ReadyDocx=Документ Word:
english.ReadyDocx=Word document:
russian.UninstallDeleteSettings=Удалить также настройки и журнал AutoSkrin? Сделанные скриншоты и документы не удаляются.
english.UninstallDeleteSettings=Also delete AutoSkrin settings and log? Your screenshots and documents are not deleted.

[Types]
Name: "full"; Description: "{cm:TypeFull}"
Name: "compact"; Description: "{cm:TypeCompact}"
Name: "custom"; Description: "{cm:TypeCustom}"; Flags: iscustom

[Components]
Name: "main"; Description: "{cm:CompMain}"; Types: full compact custom; Flags: fixed
Name: "source"; Description: "{cm:CompSource}"; Types: full

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autorun"; Description: "{cm:AutorunTask}"; GroupDescription: "{cm:OtherTasks}"; Flags: unchecked

[InstallDelete]
; При обновлении удаляем файлы старой версии, чтобы не осталось лишнего
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\source"

[Files]
Source: "..\dist\AutoSkrin\*"; DestDir: "{app}"; Components: main; Flags: ignoreversion recursesubdirs createallsubdirs
; Исходный код (по желанию)
Source: "..\*.py"; DestDir: "{app}\source"; Components: source; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}\source"; Components: source; Flags: ignoreversion
Source: "..\*.bat"; DestDir: "{app}\source"; Components: source; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}\source"; Components: source; Flags: ignoreversion
Source: "..\assets\*"; DestDir: "{app}\source\assets"; Components: source; Flags: ignoreversion
Source: "..\installer\AutoSkrin.iss"; DestDir: "{app}\source\installer"; Components: source; Flags: ignoreversion
Source: "..\tools\*.py"; DestDir: "{app}\source\tools"; Components: source; Flags: ignoreversion
Source: "..\tests\*.py"; DestDir: "{app}\source\tests"; Components: source; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[INI]
; Ярлык «Инструкция» в меню «Пуск» (ссылка на README)
Filename: "{group}\{cm:ShortcutManual}.url"; Section: "InternetShortcut"; Key: "URL"; String: "{#MyAppURL}#readme"; Check: not WizardNoIcons

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"" --minimized"; Flags: uninsdeletevalue; Tasks: autorun
; Автозапуск можно включить и в самой программе — при удалении убираем его в любом случае
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "{#MyAppName}"; Flags: uninsdeletevalue dontcreatekey

[UninstallDelete]
Type: files; Name: "{app}\defaults.json"
Type: files; Name: "{group}\{cm:ShortcutManual}.url"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
Filename: "{#MyAppURL}#readme"; Description: "{cm:OpenManual}"; Flags: postinstall shellexec skipifsilent unchecked nowait

[Code]
// ===========================================================================
// Страницы мастера с настройками программы.
// Выбранные значения записываются в файл defaults.json в папке программы;
// программа берёт их при первом запуске (или один раз заменяет ими текущие
// настройки, если пользователь снял галочку «Оставить текущие настройки»).
// ===========================================================================

var
  SavePage, DetectPage: TWizardPage;
  KeepCheck, FolderCheck, DocxCheck, NotifyCheck, AutoStartCheck, TrayCheck: TNewCheckBox;
  FolderEdit, DocxEdit, IntervalEdit, ThresholdEdit, MinIntervalEdit: TNewEdit;
  FolderButton, DocxButton: TNewButton;
  CaptureCombo, FormatCombo: TNewComboBox;
  HasExistingSettings: Boolean;
  InitialFolder, InitialDocx: String;

{ ---------- параметры командной строки вида /ИМЯ=значение ---------- }

function GetParam(const Name, DefaultValue: String): String;
var
  I: Integer;
  Prefix, P: String;
begin
  Result := DefaultValue;
  Prefix := '/' + Uppercase(Name) + '=';
  for I := 1 to ParamCount do
  begin
    P := ParamStr(I);
    if Pos(Prefix, Uppercase(P)) = 1 then
      Result := Copy(P, Length(Prefix) + 1, Length(P));
  end;
end;

function GetBoolParam(const Name: String; DefaultValue: Boolean): Boolean;
var
  V: String;
begin
  V := Lowercase(Trim(GetParam(Name, '')));
  if V = '' then
    Result := DefaultValue
  else
    Result := (V = '1') or (V = 'yes') or (V = 'true') or (V = 'on');
end;

{ ---------- вспомогательные функции ---------- }

function DefaultPicturesDir: String;
begin
  Result := ExpandConstant('{%USERPROFILE}') + '\Pictures';
  if not DirExists(Result) then
    Result := ExpandConstant('{%USERPROFILE}');
  Result := Result + '\{#MyAppName}';
end;

function NormalizeNumber(const S: String): String;
begin
  Result := Trim(S);
  StringChangeEx(Result, ',', '.', True);
end;

function IsValidNumber(const S: String): Boolean;
var
  I, Dots: Integer;
  N: String;
begin
  N := NormalizeNumber(S);
  Result := (Length(N) > 0) and (N[1] <> '.') and (N[Length(N)] <> '.');
  Dots := 0;
  for I := 1 to Length(N) do
  begin
    if N[I] = '.' then
      Dots := Dots + 1
    else if (N[I] < '0') or (N[I] > '9') then
      Result := False;
  end;
  if Dots > 1 then
    Result := False;
end;

{ Строка JSON: всё, что не ASCII, записывается как \uXXXX — файл остаётся ASCII }
function JsonString(const S: String): String;
var
  I: Integer;
  C: Char;
begin
  Result := '"';
  for I := 1 to Length(S) do
  begin
    C := S[I];
    if C = '\' then
      Result := Result + '\\'
    else if C = '"' then
      Result := Result + '\"'
    else if (Ord(C) < 32) or (Ord(C) > 126) then
      Result := Result + Format('\u%.4x', [Ord(C)])
    else
      Result := Result + C;
  end;
  Result := Result + '"';
end;

function JsonBool(B: Boolean): String;
begin
  if B then
    Result := 'true'
  else
    Result := 'false';
end;

function KeepSelected: Boolean;
begin
  Result := HasExistingSettings and KeepCheck.Checked;
end;

{ ---------- создание элементов на страницах ---------- }

function AddCheck(Page: TWizardPage; const Caption: String; Top: Integer; Checked: Boolean): TNewCheckBox;
begin
  Result := TNewCheckBox.Create(Page);
  Result.Parent := Page.Surface;
  Result.Caption := Caption;
  Result.Left := 0;
  Result.Top := Top;
  Result.Width := Page.SurfaceWidth;
  Result.Height := ScaleY(17);
  Result.Checked := Checked;
end;

procedure AddLabel(Page: TWizardPage; const Caption: String; Top: Integer);
var
  L: TNewStaticText;
begin
  L := TNewStaticText.Create(Page);
  L.Parent := Page.Surface;
  L.Caption := Caption;
  L.Left := 0;
  L.Top := Top + ScaleY(3);
end;

function AddEdit(Page: TWizardPage; const Text: String; Left, Top, Width: Integer): TNewEdit;
begin
  Result := TNewEdit.Create(Page);
  Result.Parent := Page.Surface;
  Result.Left := Left;
  Result.Top := Top;
  Result.Width := Width;
  Result.Text := Text;
end;

function AddButton(Page: TWizardPage; const Caption: String; Top: Integer): TNewButton;
begin
  Result := TNewButton.Create(Page);
  Result.Parent := Page.Surface;
  Result.Caption := Caption;
  Result.Width := ScaleX(90);
  Result.Height := ScaleY(23);
  Result.Left := Page.SurfaceWidth - Result.Width;
  Result.Top := Top;
end;

function AddCombo(Page: TWizardPage; Left, Top: Integer): TNewComboBox;
begin
  Result := TNewComboBox.Create(Page);
  Result.Parent := Page.Surface;
  Result.Style := csDropDownList;
  Result.Left := Left;
  Result.Top := Top;
  Result.Width := Page.SurfaceWidth - Left;
end;

{ ---------- обработчики ---------- }

procedure UpdateControls(Sender: TObject);
var
  Editable: Boolean;
begin
  Editable := not KeepSelected;
  FolderCheck.Enabled := Editable;
  FolderEdit.Enabled := Editable and FolderCheck.Checked;
  FolderButton.Enabled := FolderEdit.Enabled;
  DocxCheck.Enabled := Editable;
  DocxEdit.Enabled := Editable and DocxCheck.Checked;
  DocxButton.Enabled := DocxEdit.Enabled;
  CaptureCombo.Enabled := Editable;
  FormatCombo.Enabled := Editable;
end;

procedure FolderButtonClick(Sender: TObject);
var
  Dir: String;
begin
  Dir := FolderEdit.Text;
  if BrowseForFolder(CustomMessage('BrowseFolderPrompt'), Dir, True) then
    FolderEdit.Text := Dir;
end;

procedure DocxButtonClick(Sender: TObject);
var
  FileName: String;
begin
  FileName := DocxEdit.Text;
  if GetSaveFileName(CustomMessage('BrowseDocxPrompt'), FileName, ExtractFileDir(FileName),
                     CustomMessage('DocxFilter'), 'docx') then
    DocxEdit.Text := FileName;
end;

{ ---------- страница 1: куда сохранять ---------- }

procedure CreateSavePage;
var
  Top, LabelWidth: Integer;
  Capture, Fmt: String;
begin
  SavePage := CreateCustomPage(wpSelectTasks, CustomMessage('SavePageTitle'),
                               CustomMessage('SavePageDescription'));
  Top := 0;
  KeepCheck := AddCheck(SavePage, CustomMessage('KeepSettings'), Top, GetBoolParam('KEEPSETTINGS', True));
  KeepCheck.Visible := HasExistingSettings;
  KeepCheck.OnClick := @UpdateControls;
  if HasExistingSettings then
    Top := Top + ScaleY(28);

  FolderCheck := AddCheck(SavePage, CustomMessage('SaveToFolder'), Top, GetBoolParam('SAVETOFOLDER', True));
  FolderCheck.OnClick := @UpdateControls;
  Top := Top + ScaleY(22);
  InitialFolder := DefaultPicturesDir;
  FolderEdit := AddEdit(SavePage, GetParam('SHOTSDIR', InitialFolder), ScaleX(18), Top + ScaleY(1),
                        SavePage.SurfaceWidth - ScaleX(18) - ScaleX(100));
  FolderButton := AddButton(SavePage, CustomMessage('Browse'), Top);
  FolderButton.OnClick := @FolderButtonClick;
  Top := Top + ScaleY(34);

  DocxCheck := AddCheck(SavePage, CustomMessage('SaveToDocx'), Top, GetBoolParam('SAVETODOCX', False));
  DocxCheck.OnClick := @UpdateControls;
  Top := Top + ScaleY(22);
  InitialDocx := InitialFolder + '\' + CustomMessage('DefaultDocName');
  DocxEdit := AddEdit(SavePage, GetParam('DOCX', InitialDocx), ScaleX(18), Top + ScaleY(1),
                      SavePage.SurfaceWidth - ScaleX(18) - ScaleX(100));
  DocxButton := AddButton(SavePage, CustomMessage('Browse'), Top);
  DocxButton.OnClick := @DocxButtonClick;
  Top := Top + ScaleY(40);

  LabelWidth := ScaleX(150);
  AddLabel(SavePage, CustomMessage('CaptureLabel'), Top);
  CaptureCombo := AddCombo(SavePage, LabelWidth, Top);
  CaptureCombo.Items.Add(CustomMessage('CaptureRegion'));
  CaptureCombo.Items.Add(CustomMessage('CaptureScreen'));
  CaptureCombo.Items.Add(CustomMessage('CaptureAll'));
  Capture := Lowercase(GetParam('CAPTURE', 'region'));
  if Capture = 'screen' then
    CaptureCombo.ItemIndex := 1
  else if Capture = 'all' then
    CaptureCombo.ItemIndex := 2
  else
    CaptureCombo.ItemIndex := 0;
  Top := Top + ScaleY(30);

  AddLabel(SavePage, CustomMessage('FormatLabel'), Top);
  FormatCombo := AddCombo(SavePage, LabelWidth, Top);
  FormatCombo.Items.Add(CustomMessage('FormatPng'));
  FormatCombo.Items.Add(CustomMessage('FormatJpg'));
  Fmt := Lowercase(GetParam('FORMAT', 'png'));
  if (Fmt = 'jpg') or (Fmt = 'jpeg') then
    FormatCombo.ItemIndex := 1
  else
    FormatCombo.ItemIndex := 0;
end;

{ ---------- страница 2: как замечать изменения ---------- }

procedure CreateDetectPage;
var
  Top, EditLeft: Integer;
begin
  DetectPage := CreateCustomPage(SavePage.ID, CustomMessage('DetectPageTitle'),
                                 CustomMessage('DetectPageDescription'));
  EditLeft := ScaleX(260);
  Top := 0;
  AddLabel(DetectPage, CustomMessage('IntervalLabel'), Top);
  IntervalEdit := AddEdit(DetectPage, GetParam('INTERVAL', '1'), EditLeft, Top, ScaleX(70));
  Top := Top + ScaleY(30);
  AddLabel(DetectPage, CustomMessage('ThresholdLabel'), Top);
  ThresholdEdit := AddEdit(DetectPage, GetParam('THRESHOLD', '1'), EditLeft, Top, ScaleX(70));
  Top := Top + ScaleY(30);
  AddLabel(DetectPage, CustomMessage('MinIntervalLabel'), Top);
  MinIntervalEdit := AddEdit(DetectPage, GetParam('MININTERVAL', '5'), EditLeft, Top, ScaleX(70));
  Top := Top + ScaleY(40);
  NotifyCheck := AddCheck(DetectPage, CustomMessage('NotifyCheck'), Top, GetBoolParam('NOTIFY', True));
  Top := Top + ScaleY(24);
  AutoStartCheck := AddCheck(DetectPage, CustomMessage('AutoStartCheck'), Top, GetBoolParam('AUTOSTARTMON', False));
  Top := Top + ScaleY(24);
  TrayCheck := AddCheck(DetectPage, CustomMessage('TrayCheck'), Top, GetBoolParam('TRAY', True));
end;

{ ---------- запись выбранных настроек для программы ---------- }

procedure WriteInstallerDefaults;
var
  Json, NL: String;
  Capture, Fmt: String;
begin
  NL := #13#10;
  case CaptureCombo.ItemIndex of
    1: Capture := 'screen';
    2: Capture := 'all';
  else
    Capture := 'region';
  end;
  if FormatCombo.ItemIndex = 1 then
    Fmt := 'jpg'
  else
    Fmt := 'png';

  Json := '{' + NL;
  { При установке «для всех» папки по умолчанию не записываем — у каждого пользователя свои }
  if not IsAdminInstallMode or (CompareText(FolderEdit.Text, InitialFolder) <> 0) then
    Json := Json + '  "save_dir": ' + JsonString(Trim(FolderEdit.Text)) + ',' + NL;
  if not IsAdminInstallMode or (CompareText(DocxEdit.Text, InitialDocx) <> 0) then
    Json := Json + '  "docx_path": ' + JsonString(Trim(DocxEdit.Text)) + ',' + NL;
  Json := Json +
    '  "save_to_folder": ' + JsonBool(FolderCheck.Checked) + ',' + NL +
    '  "save_to_docx": ' + JsonBool(DocxCheck.Checked) + ',' + NL +
    '  "capture_mode": ' + JsonString(Capture) + ',' + NL +
    '  "image_format": ' + JsonString(Fmt) + ',' + NL +
    '  "interval_sec": ' + NormalizeNumber(IntervalEdit.Text) + ',' + NL +
    '  "threshold_percent": ' + NormalizeNumber(ThresholdEdit.Text) + ',' + NL +
    '  "min_interval_sec": ' + NormalizeNumber(MinIntervalEdit.Text) + ',' + NL +
    '  "notifications_enabled": ' + JsonBool(NotifyCheck.Checked) + ',' + NL +
    '  "autostart_monitoring": ' + JsonBool(AutoStartCheck.Checked) + ',' + NL +
    '  "minimize_to_tray": ' + JsonBool(TrayCheck.Checked) + ',' + NL +
    '  "apply_to_existing": ' + JsonBool(HasExistingSettings and not KeepCheck.Checked) + ',' + NL +
    '  "install_id": ' + JsonString(GetDateTimeString('yyyymmddhhnnss', '-', ':')) + NL +
    '}' + NL;
  if not SaveStringToFile(ExpandConstant('{app}\defaults.json'), Json, False) then
    Log('Не удалось записать defaults.json');
end;

{ ---------- события мастера ---------- }

procedure InitializeWizard;
begin
  HasExistingSettings := FileExists(ExpandConstant('{userappdata}\{#MyAppName}\settings.json'));
  CreateSavePage;
  CreateDetectPage;
  UpdateControls(nil);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = DetectPage.ID) and KeepSelected;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = SavePage.ID) and not KeepSelected then
  begin
    if not FolderCheck.Checked and not DocxCheck.Checked then
    begin
      MsgBox(CustomMessage('ErrNoTarget'), mbError, MB_OK);
      Result := False;
    end
    else if FolderCheck.Checked and (Trim(FolderEdit.Text) = '') then
    begin
      MsgBox(CustomMessage('ErrNoFolder'), mbError, MB_OK);
      Result := False;
    end
    else if DocxCheck.Checked and (Lowercase(ExtractFileExt(Trim(DocxEdit.Text))) <> '.docx') then
    begin
      MsgBox(CustomMessage('ErrDocx'), mbError, MB_OK);
      Result := False;
    end;
  end
  else if CurPageID = DetectPage.ID then
  begin
    if not IsValidNumber(IntervalEdit.Text) or not IsValidNumber(ThresholdEdit.Text)
       or not IsValidNumber(MinIntervalEdit.Text) then
    begin
      MsgBox(CustomMessage('ErrNumber'), mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
  MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
var
  S: String;
begin
  S := '';
  if MemoDirInfo <> '' then S := S + MemoDirInfo + NewLine + NewLine;
  if MemoTypeInfo <> '' then S := S + MemoTypeInfo + NewLine + NewLine;
  if MemoComponentsInfo <> '' then S := S + MemoComponentsInfo + NewLine + NewLine;
  if MemoGroupInfo <> '' then S := S + MemoGroupInfo + NewLine + NewLine;
  if MemoTasksInfo <> '' then S := S + MemoTasksInfo + NewLine + NewLine;
  S := S + CustomMessage('ReadySettings') + NewLine;
  if KeepSelected then
    S := S + Space + CustomMessage('ReadyKeep') + NewLine
  else
  begin
    if FolderCheck.Checked then
      S := S + Space + CustomMessage('ReadyFolder') + ' ' + FolderEdit.Text + NewLine;
    if DocxCheck.Checked then
      S := S + Space + CustomMessage('ReadyDocx') + ' ' + DocxEdit.Text + NewLine;
    S := S + Space + CustomMessage('CaptureLabel') + ' ' + CaptureCombo.Items[CaptureCombo.ItemIndex] + NewLine;
    S := S + Space + CustomMessage('FormatLabel') + ' ' + FormatCombo.Items[FormatCombo.ItemIndex] + NewLine;
    S := S + Space + CustomMessage('IntervalLabel') + ' ' + IntervalEdit.Text + NewLine;
    S := S + Space + CustomMessage('ThresholdLabel') + ' ' + ThresholdEdit.Text + NewLine;
    S := S + Space + CustomMessage('MinIntervalLabel') + ' ' + MinIntervalEdit.Text + NewLine;
  end;
  Result := S;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    WriteInstallerDefaults;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  SettingsDir: String;
  DeleteIt: Boolean;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;
  SettingsDir := ExpandConstant('{userappdata}\{#MyAppName}');
  if not DirExists(SettingsDir) then
    Exit;
  if UninstallSilent then
    DeleteIt := GetBoolParam('DELETESETTINGS', False)
  else
    DeleteIt := MsgBox(CustomMessage('UninstallDeleteSettings'), mbConfirmation,
                       MB_YESNO or MB_DEFBUTTON2) = IDYES;
  if DeleteIt then
    DelTree(SettingsDir, True, True, True);
end;
