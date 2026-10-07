#define AppVersion "0.1.0"
[Setup]
AppId={{36E1A6E2-60A5-47D0-A947-11A716ED46B6}
AppName=IFs Model Vetting
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\IFs Model Vetting
DefaultGroupName=IFs Model Vetting
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\release
OutputBaseFilename=IFsModelVetting-Setup-{#AppVersion}-win-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\IFsModelVetting.exe
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
[Files]
Source: "..\dist\IFsModelVetting\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\IFs Model Vetting"; Filename: "{app}\IFsModelVetting.exe"
Name: "{userdesktop}\IFs Model Vetting"; Filename: "{app}\IFsModelVetting.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\IFsModelVetting.exe"; Description: "Open IFs Model Vetting"; Flags: nowait postinstall skipifsilent
