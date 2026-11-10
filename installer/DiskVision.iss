[Setup]
AppId=DiskVision.Local.Windows
AppName=DiskVision
AppVersion=1.0.0
DefaultDirName={localappdata}\Programs\DiskVision
DefaultGroupName=DiskVision
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=DiskVision-Setup
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
MinVersion=10.0
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\DiskVision.exe

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "..\dist\DiskVision\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\DiskVision"; Filename: "{app}\DiskVision.exe"

[Run]
Filename: "{app}\DiskVision.exe"; Description: "Abrir DiskVision"; Flags: nowait postinstall skipifsilent
