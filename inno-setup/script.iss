; Inno Setup script for shairport-sync-windows
; This is a direct spiritual successor to the uxplay-windows script.iss


; --- Basic Application Info ---
AppName=shairport-sync-windows
AppVersion=1.0.0
; {app} will be 'C:\Program Files (x86)\shairport-sync-windows'
DefaultDirName={autopf}\shairport-sync-windows
DefaultGroupName=Shairport Sync Windows
AppPublisher=shairport-sync-windows
AppPublisherURL=https://github.com/mikebrady/shairport-sync
AppSupportURL=https://github.com/mikebrady/shairport-sync
AppUpdatesURL=https://github.com/mikebrady/shairport-sync
AllowNoIcons=yes
LicenseFile=LICENSE.md
InfoBeforeFile=README.md
InfoAfterFile=README.md

; --- Installer Appearance ---
OutputBaseFilename=shairport-sync-windows-setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
;SetupIconFile=icon.ico
UninstallDisplayIcon={app}\shairport-sync-windows.exe

; --- Privileges ---
; Admin is required for Bonjour service installation
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

; --- AppId (Critical for upgrades) ---
; This is a new, unique GUID for shairport-sync-windows.
AppId={{5E9A68A1-1936-4074-8A8B-3B9B978B4A5D}}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"


Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; --- Python Tray App (from PyInstaller 'dist' dir) ---
Source: "dist\shairport-sync-windows.exe"; DestDir: "{app}"; Flags: ignoreversion
;Source: "dist\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

; --- Core Program & DLLs (from MSYS2 'build' dir) ---
Source: "build\*.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "build\*.dll"; DestDir: "{app}"; Flags: ignoreversion

; --- Bonjour DLL (from mDNSResponder SDK) ---
; This is installed as a system service by the [Code] section,
; but we also place a copy in the app dir, following the uxplay model.
Source: "mDNSResponder\bin\dnssd.dll"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\shairport-sync-windows"; Filename: "{app}\shairport-sync-windows.exe"
Name: "{group}\{cm:UninstallProgram,shairport-sync-windows}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\shairport-sync-windows"; Filename: "{app}\shairport-sync-windows.exe"; Tasks: desktopicon


; Run the tray icon after installation is complete
Filename: "{app}\shairport-sync-windows.exe"; Description: "{cm:LaunchProgram,shairport-sync-windows}"; Flags: nowait postinstall skipifsilent


; Clean up the config directory on uninstall
Type: filesandordirs; Name: "{userappdata}\shairport-sync-windows"

[Code]
//
// THIS ENTIRE [Code] SECTION IS REUSED FROM UXPLAY-WINDOWS
// It ensures Apple's Bonjour mDNS service is installed.
// This is critical for shairport-sync to be discoverable.
//
var
BonjourUrl: String;
BonjourDownloaded: Boolean;

function InitializeSetup(): Boolean;
begin
BonjourUrl := 'https://download.info.apple.com/Mac_OS_X/061-8609.20100612.BnaS2/BonjourPSSetup.exe';
BonjourDownloaded := False;
Result := True;
end;

function IsBonjourInstalled: Boolean;
begin
Result := RegKeyExists(HKLM, 'SOFTWARE\Apple Inc.\Bonjour');
end;

procedure InstallBonjour;
var
TempPath: String;
BonjourSetupPath: String;
ResultCode: Integer;
begin
TempPath := ExpandConstant('{tmp}');
BonjourSetupPath := TempPath + '\BonjourPSSetup.exe';

if not BonjourDownloaded then
begin
WizardForm.StatusLabel.Caption := 'Downloading Bonjour...';
if not DownloadFile(BonjourUrl, BonjourSetupPath) then
begin
MsgBox('Failed to download Bonjour. Please install it manually from Apple''s website.', mbError, MB_OK);
exit;
end;
BonjourDownloaded := True;
end;

WizardForm.StatusLabel.Caption := 'Installing Bonjour...';
if not Exec(BonjourSetupPath, '/q', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
begin
MsgBox('Bonjour installation failed. Code: ' + IntToStr(ResultCode), mbError, MB_OK);
end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
Result := True;
if (CurPageID = wpReady) and (not IsBonjourInstalled) then
begin
InstallBonjour;
end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
if (CurStep = ssInstall) and (not IsBonjourInstalled) then
begin
InstallBonjour;
end;
end;

function DownloadFile(const Url, FilePath: String): Boolean;
var
WinHttp: Variant;
Stream: Variant;
begin
Result := False;
try
WinHttp := CreateOleObject('WinHttp.WinHttpRequest.5.1');
WinHttp.Open('GET', Url, False);
WinHttp.Send;
if WinHttp.Status = 200 then
begin
Stream := CreateOleObject('ADODB.Stream');
Stream.Type := 1; // adTypeBinary
Stream.Open;
Stream.Write(WinHttp.ResponseBody);
Stream.SaveToFile(FilePath, 2); // adSaveCreateOverWrite
Stream.Close;
Result := True;
end;
except
MsgBox('Error during download: ' + GetExceptionMessage, mbError, MB_OK);
end;
end;

// --- Process Management ---
// We must kill the processes on uninstall to avoid file-in-use errors.

procedure KillProcess(ExeName: String);
var
ResultCode: Integer;
begin
Exec(ExpandConstant('{sys}\taskkill.exe'), '/f /im ' + ExeName, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure InitializeUninstall();
begin
// Kill both the tray wrapper and the core server executable
KillProcess('shairport-sync-windows.exe');
KillProcess('shairport-sync.exe');
end;
