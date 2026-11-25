; Inno Setup script - builds Mostafa-MultiWidget-Setup.exe from the PyInstaller output in dist\Mostafa-MultiWidget
#define AppName "Mostafa-MultiWidget"
#define AppVersion "1.1.1"
#define AppExe "Mostafa-MultiWidget.exe"
; The build step may have produced the program under its new or its old folder name; accept both.
#if DirExists("dist\Mostafa-MultiWidget")
  #define BuildDir "Mostafa-MultiWidget"
  #define BuiltExe "Mostafa-MultiWidget.exe"
  #define SetupName "Mostafa-MultiWidget-Setup"
#else
  #define BuildDir "MyIPWidget"
  #define BuiltExe "MyIPWidget.exe"
  #define SetupName "MyIPWidget-Setup"
#endif

[Setup]
AppId={{D5FE5497-F778-4CD9-90BC-1B35C2F9D6DC}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Mostafa Mandegari
AppCopyright=Copyright (c) Mostafa Mandegari
VersionInfoVersion={#AppVersion}
VersionInfoCompany=Mostafa Mandegari
VersionInfoDescription={#AppName} Setup
DefaultDirName={autopf}\Mostafa-MultiWidget
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer_output
OutputBaseFilename={#SetupName}
SetupIconFile=assets\images\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "startup"; Description: "Start {#AppName} when Windows starts"

[Files]
Source: "dist\{#BuildDir}\*"; DestDir: "{app}"; Excludes: "{#BuiltExe}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "dist\{#BuildDir}\{#BuiltExe}"; DestDir: "{app}"; DestName: "{#AppExe}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; The value name must match APP_NAME in ipcore.py so the in-app switch sees the same entry.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"""; Flags: uninsdeletevalue; Tasks: startup

[InstallDelete]
Type: files; Name: "{app}\MyIPWidget.exe"
Type: files; Name: "{autoprograms}\MyIP Widget.lnk"
Type: files; Name: "{autodesktop}\MyIP Widget.lnk"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
