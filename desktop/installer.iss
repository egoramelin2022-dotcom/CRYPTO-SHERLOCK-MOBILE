#define MyAppName "CRYPTO SHERLOCK"
#define MyAppVersion "0.3.0"
#define MyAppPublisher "CRYPTO SHERLOCK"

[Setup]
AppId={{A0D37D86-ED90-4C56-8D4A-7C1D7F64F3A2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\CRYPTO SHERLOCK
DefaultGroupName=CRYPTO SHERLOCK
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
OutputDir=..\dist\installer
OutputBaseFilename=CRYPTO-SHERLOCK-Setup-{#MyAppVersion}
Compression=lzma2/fast
SolidCompression=no
WizardStyle=modern
UninstallDisplayIcon={app}\CRYPTO-SHERLOCK.exe
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\CRYPTO-SHERLOCK\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\CRYPTO SHERLOCK"; Filename: "{app}\CRYPTO-SHERLOCK.exe"
Name: "{autodesktop}\CRYPTO SHERLOCK"; Filename: "{app}\CRYPTO-SHERLOCK.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CRYPTO-SHERLOCK.exe"; Description: "Launch CRYPTO SHERLOCK"; Flags: postinstall nowait skipifsilent
