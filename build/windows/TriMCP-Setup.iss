; TriMCP Inno Setup Script
; Implements Phase 5 / Section 6.2 Wizard Flow

[Setup]
AppName=TriMCP
AppVersion=1.0.0
DefaultDirName={autopf}\TriMCP
DefaultGroupName=TriMCP
OutputDir=Output
OutputBaseFilename=TriMCP-Setup
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin

[Files]
; Core application files
Source: "trimcp-launch.exe"; DestDir: "{app}"; Flags: ignoreversion
; Embedded Python
Source: "assets\python\*"; DestDir: "{app}\python"; Flags: ignoreversion recursesubdirs createallsubdirs
; Models and Wheels
Source: "assets\models\*"; DestDir: "{app}\models"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\wheels\*"; DestDir: "{app}\wheels"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{userappdata}\TriMCP"
Name: "{userappdata}\TriMCP\logs"

[Code]
var
  ModePage: TInputOptionWizardPage;
  DockerCheckPage: TOutputMsgWizardPage;
  ServerAddressPage: TInputQueryWizardPage;
  CloudSignInPage: TOutputMsgWizardPage;
  HardwarePage: TInputOptionWizardPage;
  BridgesPage: TInputOptionWizardPage;

procedure InitializeWizard;
begin
  // Screen 2: Mode Selection
  ModePage := CreateInputOptionPage(wpWelcome,
    'Mode Selection', 'Choose how you want to connect to TriMCP.',
    'Select the deployment mode that matches your organization''s setup:',
    True, False);
  ModePage.Add('Local - Just for me. Data stays on this computer. (Requires Docker)');
  ModePage.Add('Office Shared - Connect to my company''s TriMCP server.');
  ModePage.Add('Cloud - Connect to a cloud TriMCP deployment.');
  ModePage.Values[0] := True; // Default to Local

  // Screen 3a: Docker Desktop Check (Local Path)
  DockerCheckPage := CreateOutputMsgPage(ModePage.ID,
    'Docker Desktop Check', 'Checking prerequisites for Local mode.',
    'Local mode requires Docker Desktop to run the local database stack.' + #13#10#13#10 +
    'If Docker Desktop is not installed, please download and install it from docker.com before continuing.');

  // Screen 3b: Server Address (Multi-User Path)
  ServerAddressPage := CreateInputQueryPage(DockerCheckPage.ID,
    'Server Address', 'Enter your Office Shared server details.',
    'Please enter the URL provided by your IT administrator:');
  ServerAddressPage.Add('Server URL:', False);

  // Screen 3c: Sign In (Cloud Path)
  CloudSignInPage := CreateOutputMsgPage(ServerAddressPage.ID,
    'Cloud Authentication', 'Sign in to your Cloud deployment.',
    'Authentication will be handled securely via your web browser on first launch.' + #13#10#13#10 +
    'You will be prompted to sign in with your Microsoft work or school account.');

  // Screen 4: Hardware Acceleration
  HardwarePage := CreateInputOptionPage(CloudSignInPage.ID,
    'Hardware Acceleration', 'Configure AI inference hardware.',
    'TriMCP auto-detects your hardware for optimal performance. You can override this below:',
    True, False);
  HardwarePage.Add('Use Recommended (Auto-detected GPU/NPU)');
  HardwarePage.Add('CPU Only (Slowest, most compatible)');
  HardwarePage.Values[0] := True;

  // Screen 5: Document Bridges (optional)
  BridgesPage := CreateInputOptionPage(HardwarePage.ID,
    'Document Bridges', 'Connect to your document libraries?',
    'Select the services you want to connect. You can configure these later.',
    False, False);
  BridgesPage.Add('Microsoft SharePoint / OneDrive');
  BridgesPage.Add('Google Workspace / Drive');
  BridgesPage.Add('Dropbox');
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  
  // Branching logic based on Mode Selection
  if PageID = DockerCheckPage.ID then
    Result := (ModePage.SelectedValueIndex <> 0); // Skip if NOT Local
    
  if PageID = ServerAddressPage.ID then
    Result := (ModePage.SelectedValueIndex <> 1); // Skip if NOT Office Shared
    
  if PageID = CloudSignInPage.ID then
    Result := (ModePage.SelectedValueIndex <> 2); // Skip if NOT Cloud
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  // Update Next button text if needed
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  AppDataDir: String;
  ModeStr: String;
  EnvContent: TArrayOfString;
begin
  if CurStep = ssPostInstall then
  begin
    AppDataDir := ExpandConstant('{userappdata}\TriMCP');
    
    // Write mode.txt
    if ModePage.SelectedValueIndex = 0 then ModeStr := 'local'
    else if ModePage.SelectedValueIndex = 1 then ModeStr := 'multiuser'
    else ModeStr := 'cloud';
    
    SaveStringToFile(AppDataDir + '\mode.txt', ModeStr, False);
    
    // Write .env
    SetArrayLength(EnvContent, 3);
    EnvContent[0] := 'TRIMCP_MODE=' + ModeStr;
    
    if ModeStr = 'multiuser' then
      EnvContent[1] := 'TRIMCP_SERVER_URL=' + ServerAddressPage.Values[0]
    else
      EnvContent[1] := 'TRIMCP_SERVER_URL=';
      
    if HardwarePage.SelectedValueIndex = 1 then
      EnvContent[2] := 'TRIMCP_BACKEND=cpu'
    else
      EnvContent[2] := 'TRIMCP_BACKEND=auto';
      
    SaveStringsToFile(AppDataDir + '\.env', EnvContent, False);
  end;
end;

[Run]
; Launch Claude Desktop or Cursor instructions could go here
Filename: "{app}\trimcp-launch.exe"; Description: "Launch TriMCP Background Service"; Flags: nowait postinstall skipifsilent
