; Inno Setup script for CaseCraft Studio.
; Build: ISCC.exe /DAppVersion=1.1.0 desktop\installer.iss    (desktop\build.ps1 does this)
; Input: dist\CaseCraftStudio\ (PyInstaller one-folder build). Output: dist\CaseCraftStudio-Setup-<ver>.exe

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "CaseCraft Studio"
#define AppExe "CaseCraftStudio.exe"
#define SrcDir "..\dist\CaseCraftStudio"

[Setup]
AppId={{6E2B4A3C-7D41-4F0B-9C5E-CA5ECAF7B10D}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=CaseCraft Studio
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Per-user install: no administrator rights needed
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\dist
OutputBaseFilename=CaseCraftStudio-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
CloseApplications=yes
RestartApplications=no
; Refuse to install over a running copy (files would be locked)
AppMutex=Local\CaseCraftStudio.SingleInstance

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "assoc"; Description: "Open .casecraft project files with {#AppName}"; GroupDescription: "File associations:"

[InstallDelete]
; Remove the previous build's files so stale modules never mix with new ones
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Classes\.casecraft"; ValueType: string; ValueName: ""; ValueData: "CaseCraftStudio.Project"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\CaseCraftStudio.Project"; ValueType: string; ValueName: ""; ValueData: "CaseCraft project"; Flags: uninsdeletekey; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\CaseCraftStudio.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\CaseCraftStudio.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: assoc

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Code]
const
  WebView2Key = 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  WebView2KeyUser = 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function HasWebView2(): Boolean;
var
  V: String;
begin
  Result := (RegQueryStringValue(HKLM, WebView2Key, 'pv', V) and (V <> '') and (V <> '0.0.0.0')) or
            (RegQueryStringValue(HKCU, WebView2KeyUser, 'pv', V) and (V <> '') and (V <> '0.0.0.0'));
end;

function InitializeSetup(): Boolean;
var
  ErrCode: Integer;
begin
  Result := True;
  if not HasWebView2() then
  begin
    // SuppressibleMsgBox: silent installs (/SUPPRESSMSGBOXES) take the default answer instead of blocking
    if SuppressibleMsgBox('CaseCraft Studio needs the Microsoft Edge WebView2 Runtime, which is not installed.' + #13#10#13#10 +
              'Open the Microsoft download page now? (Setup will continue; install WebView2 before starting the app.)',
              mbConfirmation, MB_YESNO, IDNO) = IDYES then
      ShellExec('open', 'https://go.microsoft.com/fwlink/p/?LinkId=2124703', '', '', SW_SHOWNORMAL, ewNoWait, ErrCode);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir, LogDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\CaseCraft Studio');
    LogDir := ExpandConstant('{localappdata}\CaseCraft Studio');
    // Silent uninstalls keep user data (default answer IDNO) instead of blocking on the question
    if (DirExists(DataDir) or DirExists(LogDir)) and not UninstallSilent() then
      if SuppressibleMsgBox('Also delete your CaseCraft Studio settings, saved devices and autosave?' + #13#10 +
                '(Your .casecraft project files are not affected.)', mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
      begin
        DelTree(DataDir, True, True, True);
        DelTree(LogDir, True, True, True);
      end;
  end;
end;
