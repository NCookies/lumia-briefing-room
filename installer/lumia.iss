; 루미아 브리핑룸 설치기 (plan-deploy.md D6)
;
; 직접 컴파일하지 말고 python tools/build_installer.py 로 만든다 — 버전과 경로를 거기서 넘긴다.
; 관리자 권한 없이 사용자 영역에 설치하고, 제거할 때 자동 시작 레지스트리 값을 지운다.
; 클립 폴더(기본 %USERPROFILE%\Videos\LumiaBriefingRoom)는 어떤 경우에도 건드리지 않는다.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\LumiaBriefingRoom"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif
#ifndef AppIcon
  #define AppIcon "..\build\icon.ico"
#endif
#ifndef NoticesFile
  #define NoticesFile "..\THIRD_PARTY_NOTICES.md"
#endif

#define AppName "루미아 브리핑룸"
#define AppId "LumiaBriefingRoom"
#define AppExe "LumiaBriefingRoom.exe"
#define AppPublisher "Lumia Briefing Room"

[Setup]
AppId={{8F3C1A54-6D2E-4B77-9C10-2E4B6A9D7F31}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\LumiaBriefingRoom
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=LumiaBriefingRoom-{#AppVersion}-setup
SetupIconFile={#AppIcon}
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; 관리자 권한을 요구하지 않는다 — {autopf} 가 %LOCALAPPDATA%\Programs 로 풀린다.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; 앱이 쓰는 이름 있는 뮤텍스. 실행 중이면 닫아 달라고 알린다(재설치·업데이트 설치 경로).
AppMutex=LumiaBriefingRoom.SingleInstance
CloseApplications=yes
RestartApplications=no
WizardStyle=modern

[Languages]
Name: "korean"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"; GroupDescription: "추가 작업:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#NoticesFile}"; DestDir: "{app}"; DestName: "THIRD_PARTY_NOTICES.md"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{#AppName} 제거"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; 설치 때는 아무것도 쓰지 않는다(자동 시작은 앱이 설정에 따라 스스로 등록한다).
; 제거할 때 남아 있으면 로그인마다 없는 exe 를 실행하려 하므로 값을 지운다.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "LumiaBriefingRoom"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "{#AppName} 실행"; Flags: nowait postinstall skipifsilent
; 앱 안 업데이트(plan-deploy.md D9)가 /SILENT /RELAUNCH=1 로 실행하면 끝난 뒤 앱을 다시 띄운다. 다른 무인 설치(/VERYSILENT 검증 등)는 띄우지 않는다.
Filename: "{app}\{#AppExe}"; Parameters: "--start-server"; Flags: nowait; Check: RelaunchRequested

[Code]
function PinWindow(hWnd: LongInt; hWndInsertAfter: LongInt; X, Y, cx, cy: Integer; uFlags: Cardinal): Boolean; external 'SetWindowPos@user32.dll stdcall';
function GetActiveWindow: LongInt; external 'GetActiveWindow@user32.dll stdcall';

// 앱 안 업데이트(조용한 설치)는 브라우저가 앞에 있는 채로 시작돼 설치 진행 창이 뒤에 가려진다 — 포커스를 뺏지 않고 맨 위에 띄운다.
// (실측: 창은 0.6초 만에 뜨지만 앞은 계속 브라우저였고, 이 처리를 하면 TOPMOST 로 보인다.)
procedure ShowProgressOnTop;
begin
  if WizardSilent then
  begin
    PinWindow(GetActiveWindow, -1, 0, 0, 0, 0, $0003);
    PinWindow(WizardForm.Handle, -1, 0, 0, 0, 0, $0003);
  end;
end;

procedure InitializeWizard;
begin
  ShowProgressOnTop;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then ShowProgressOnTop;
end;

function RelaunchRequested: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;

// 제거할 때 설정·로그를 지울지 묻는다. 클립은 묻지도, 지우지도 않는다.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\LumiaBriefingRoom');
    // 무인 제거(/VERYSILENT)에서는 묻지 않고 남겨 둔다 — 물어보면 대화상자에서 멈춘다.
    if DirExists(DataDir) and (not UninstallSilent) then
    begin
      if MsgBox('설정과 로그도 삭제하시겠습니까?' + #13#10 + #13#10 + DataDir + #13#10 + #13#10 +
                '저장된 클립은 이 폴더에 없으며 지워지지 않습니다.',
                mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
