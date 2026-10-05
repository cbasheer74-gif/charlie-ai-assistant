; CHARLIE v1.2.4 — Production Windows Installer — Inno Setup configuration

#define AppName "CHARLIE"
#ifndef AppVersion
  #define AppVersion "1.2.4"
#endif
#ifndef AppNumericVersion
  #define AppNumericVersion "1.2.4.0"
#endif
#define AppPublisher "Anees Chaudhary"
#define AppURL "https://charlie.app"
#define AppExeName "CHARLIE.exe"
#define AppId "{{B2E5F1A0-3D4C-4F8E-9A1B-7C6D5E4F3A2B}"
#ifndef OutputBaseFilename
  #define OutputBaseFilename "Charlie-AI-Desktop-" + AppVersion + "-Setup"
#endif

[Setup]
SourceDir={#SourcePath}
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/support
AppUpdatesURL={#AppURL}/download
DefaultDirName={userpf}\{#AppName}
DefaultGroupName={#AppName}
UsePreviousAppDir=no
PrivilegesRequired=lowest
OutputDir=release
OutputBaseFilename={#OutputBaseFilename}
SetupIconFile={#SourcePath}\config\charlie.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
LicenseFile=LICENSE
WizardStyle=modern
WizardSizePercent=120
VersionInfoVersion={#AppNumericVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription=CHARLIE AI Desktop Assistant
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppNumericVersion}
VersionInfoProductTextVersion={#AppVersion}
VersionInfoCopyright=Copyright (C) 2026 {#AppPublisher}
MinVersion=10.0
CloseApplications=yes
RestartApplications=no
; SignTool=signtool
; SignedUninstaller=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "startupicon"; Description: "Start {#AppName} with &Windows"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
Source: "dist\CHARLIE\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Comment: "Launch {#AppName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon; Comment: "Launch {#AppName}"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExeName}"""; Flags: uninsdeletevalue; Tasks: startupicon
Root: HKCU; Subkey: "Software\{#AppPublisher}\{#AppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\{#AppPublisher}\{#AppName}"; ValueType: string; ValueName: "Version"; ValueData: "{#AppVersion}"; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\*.log"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  UserDataDir: String;
  Res: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    UserDataDir := ExpandConstant('{userappdata}\CHARLIE');
    if DirExists(UserDataDir) then
    begin
      Res := MsgBox(
        'Do you want to remove your CHARLIE user data?' + #13#10 +
        'Choose No to keep profiles, memory, settings and license data.',
        mbConfirmation, MB_YESNO);
      if Res = IDYES then
        DelTree(UserDataDir, True, True, True);
    end;
  end;
end;
