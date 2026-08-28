; Inno Setup 스크립트 — packaging 폴더에서 ISCC 로 컴파일
;   ISCC.exe /DAppVersion=0.1.0 installer.iss
; 사전 조건: 저장소 루트\dist\ReclipSubs\  (PyInstaller 결과물) 이 있어야 함

#define AppName "ReclipSubs"
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{9C1E7A42-5B3D-4F8A-A6D2-7E5C0B9A1F30}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=piece101
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\ReclipSubs.exe
UninstallDisplayName={#AppName}
OutputDir=installer_out
OutputBaseFilename=ReclipSubs-Setup-{#AppVersion}
SetupIconFile=..\assets\icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\ReclipSubs\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\ReclipSubs.exe"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\ReclipSubs.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ReclipSubs.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
