; Установщик PGL Mocap для Windows (Inno Setup 6).
; Собирается в CI:  iscc /DAppVer=1.1.0 /DBuildNum=12 installer\pgl_mocap.iss
; Ожидает собранную программу в dist\PGL Mocap\

#ifndef AppVer
  #define AppVer "1.0.0"
#endif
#ifndef BuildNum
  #define BuildNum "0"
#endif

#define AppName "PGL Mocap"
#define AppExe  "PGL Mocap.exe"
#define FwRule  "PGL Mocap"

[Setup]
AppId={{E874C5AA-5D6A-4D1F-A221-84F036D90E38}
AppName={#AppName}
AppVersion={#AppVer}.{#BuildNum}
AppVerName={#AppName} {#AppVer} (сборка {#BuildNum})
AppPublisher=PGL
AppPublisherURL=https://github.com/4007079-ship-it/PGL-Mocap
AppSupportURL=https://github.com/4007079-ship-it/PGL-Mocap
AppUpdatesURL=https://github.com/4007079-ship-it/PGL-Mocap/releases
VersionInfoVersion={#AppVer}.{#BuildNum}
VersionInfoProductName={#AppName}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=PGL_Mocap_Setup
SetupIconFile=..\assets\pgl_mocap.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
PrivilegesRequired=admin
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
ru.DesktopIcon=Создать значок на рабочем столе
en.DesktopIcon=Create a desktop shortcut
ru.Firewall=Разрешить в брандмауэре Windows (нужно для NDI и приёма данных по сети)
en.Firewall=Allow in Windows Firewall (needed for NDI and network data)
ru.LaunchApp=Запустить PGL Mocap
en.LaunchApp=Launch PGL Mocap
ru.Readme=Инструкция PGL Mocap
en.Readme=PGL Mocap manual

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"
Name: "firewall"; Description: "{cm:Firewall}"

[Files]
Source: "..\dist\PGL Mocap\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; при обновлении убираем старые библиотеки, чтобы не смешивались версии
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{autoprograms}\{cm:Readme}"; Filename: "{app}\README.md"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; правило брандмауэра: сначала удаляем старое (если было), потом добавляем входящее и исходящее
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#FwRule}"""; Flags: runhidden; Tasks: firewall
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""{#FwRule}"" dir=in action=allow program=""{app}\{#AppExe}"" enable=yes profile=any"; Flags: runhidden; Tasks: firewall
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""{#FwRule}"" dir=out action=allow program=""{app}\{#AppExe}"" enable=yes profile=any"; Flags: runhidden; Tasks: firewall
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#FwRule}"""; Flags: runhidden; RunOnceId: "DelFwRule"

; Настройки пользователя (%APPDATA%\PGL Mocap) при удалении и обновлении не трогаются.
