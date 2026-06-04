; Inno Setup installer definition for 3.ThucTheNgay.
;
; Build through scripts\build_windows_installer.ps1 so AppVersion, SourceDir, and
; OutputDir are injected from the current project checkout.

#ifndef AppVersion
#define AppVersion "0.1.0"
#endif

#ifndef SourceDir
#define SourceDir "..\..\dist\ThucTheNgay"
#endif

#ifndef OutputDir
#define OutputDir "..\..\dist\installer"
#endif

#define AppName "ThucTheNgay"
#define AppPublisher "3.ThucTheNgay"
#define AppExeName "ThucTheNgay.exe"

[Setup]
AppId={{4F523B19-52FC-49D9-A887-7C8993766F8E}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=ThucTheNgay-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
PrivilegesRequired=admin
SetupLogging=yes
UninstallDisplayIcon={app}\{#AppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
