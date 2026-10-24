# AI 업무자동화 코치 — Windows 설치 스크립트
# 사용법 (PowerShell 에 붙여넣기):
#   irm https://raw.githubusercontent.com/hi8735/ai-automation-kit/main/install/install.ps1 | iex
#
# 하는 일: C:\ai-kit 폴더에 (1) uv(파이썬 관리 도구) (2) 코치 앱 (3) 키트 를 설치하고
#          바탕화면에 "AI 업무자동화 코치" 바로가기를 만든 뒤 실행한다. 관리자 권한 불필요.
# 다시 실행하면 최신 버전으로 업데이트된다. 내 기록(results, inputs, report, automations, outputs)은 건드리지 않는다.

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$AppZip = if ($env:AI_KIT_APP_ZIP) { $env:AI_KIT_APP_ZIP } else { 'https://github.com/hi8735/ai-automation-kit/releases/latest/download/ai-automation-kit-app.zip' }
$UserDirs = @('results', 'inputs', 'report', 'automations', 'outputs')

function Step($n, $msg) { Write-Host ""; Write-Host "[$n/5] $msg" -ForegroundColor Cyan }
function Fail($msg) {
  Write-Host ""
  Write-Host "설치를 마치지 못했어요: $msg" -ForegroundColor Red
  Write-Host "이 창의 내용을 캡처해서 모임 채팅방에 올려주세요. 바로 도와드릴게요." -ForegroundColor Yellow
  throw $msg
}

# 한글 사용자 이름 경로를 피하려고 C:\ai-kit 을 쓴다.
# C:\ 바로 아래 폴더는 기본적으로 같은 PC 의 다른 계정도 고칠 수 있으므로, 만든 뒤 나만 쓸 수 있게 권한을 좁힌다.
# 이미 있는데 다른 사람이 만든 폴더면 쓰지 않고 내 사용자 폴더로 대신한다.
$Me = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
function New-PrivateSecurity {
  # 나(현재 사용자), SYSTEM, Administrators 만 전체 권한, 상속 없음
  $sec = New-Object System.Security.AccessControl.DirectorySecurity
  $sec.SetAccessRuleProtection($true, $false)
  $inh = [System.Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
  $prop = [System.Security.AccessControl.PropagationFlags]::None
  foreach ($sid in @($Me, (New-Object System.Security.Principal.SecurityIdentifier 'S-1-5-18'), (New-Object System.Security.Principal.SecurityIdentifier 'S-1-5-32-544'))) {
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', $inh, $prop, 'Allow')
    $sec.AddAccessRule($rule)
  }
  return $sec
}
function Use-Root($path) {
  $myName = $Me.Translate([System.Security.Principal.NTAccount]).Value
  if (-not (Test-Path $path)) {
    # 만드는 순간부터 제한된 권한으로 만든다 (만든 뒤 잠그는 사이의 틈을 없앤다)
    $sec = New-PrivateSecurity
    if ($PSVersionTable.PSEdition -eq 'Desktop') { [System.IO.Directory]::CreateDirectory($path, $sec) | Out-Null }
    else { [System.IO.FileSystemAclExtensions]::Create([System.IO.DirectoryInfo]::new($path), $sec) }
    return ((Get-Acl $path).Owner -eq $myName)
  }
  # 이미 있는 폴더: 먼저 잠그고(다른 계정이 더는 못 쓰게), 그다음 모든 파일이 내 것인지 확인한다
  if ((Get-Acl $path).Owner -ne $myName) { return $false }
  & icacls $path /inheritance:r /grant:r "*$($Me.Value):(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" | Out-Null
  if ($LASTEXITCODE -ne 0) { return $false }
  if (Get-ChildItem -Force $path) { & icacls "$path\*" /reset /T /C /Q | Out-Null }
  $foreign = Get-ChildItem -Recurse -Force $path -ErrorAction SilentlyContinue |
    Where-Object { (Get-Acl $_.FullName).Owner -ne $myName } | Select-Object -First 1
  return (-not $foreign)
}
$Root = 'C:\ai-kit'
$ok = $false
try { $ok = Use-Root $Root } catch { $ok = $false }
if (-not $ok) {
  $Root = Join-Path $env:LOCALAPPDATA 'ai-kit'
  New-Item -ItemType Directory -Force -Path $Root | Out-Null
}

$env:UV_PYTHON_INSTALL_DIR = Join-Path $Root 'python'
$env:UV_CACHE_DIR = Join-Path $Root 'cache'
$env:UV_PYTHON_PREFERENCE = 'only-managed'
$Uv = Join-Path $Root 'bin\uv.exe'

Write-Host ""
Write-Host "AI 업무자동화 코치를 설치할게요. 설치 위치: $Root" -ForegroundColor Green
Write-Host "처음엔 3~5분 걸릴 수 있어요. 창을 닫지 말고 기다려주세요."

Step 1 '준비 도구(uv) 설치'
# 기존 uv 를 믿지 않고 매번 새로 받는다
$UvDir = Join-Path $Root 'bin'
if (Test-Path $UvDir) { Remove-Item -Recurse -Force $UvDir }
if ($true) {
  try {
    $env:UV_INSTALL_DIR = Join-Path $Root 'bin'
    $env:UV_NO_MODIFY_PATH = '1'
    # uv 설치 스크립트 안의 exit 이 이 창을 닫지 않도록 별도 PowerShell 에서 실행한다 (환경변수는 이어받는다)
    & powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex" | Out-Null
  } catch { Fail "uv 설치 실패 — $($_.Exception.Message)" }
  if (-not (Test-Path $Uv)) { Fail "uv 를 찾을 수 없어요 ($Uv). 회사 PC 라면 보안 프로그램이 막았을 수 있어요." }
}

Step 2 '코치 앱 내려받기'
$Tmp = Join-Path $Root '_download'
if (Test-Path $Tmp) { Remove-Item -Recurse -Force $Tmp }
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null
try {
  Invoke-WebRequest -UseBasicParsing -Uri $AppZip -OutFile (Join-Path $Tmp 'app.zip')
  Expand-Archive -Force -Path (Join-Path $Tmp 'app.zip') -DestinationPath $Tmp
} catch { Fail "내려받기 실패 — 인터넷 연결을 확인해 주세요. ($($_.Exception.Message))" }

Step 3 '앱과 키트 설치'
$AppDir = Join-Path $Root 'app'
$Ws = Join-Path $Root 'workspace'
if (Test-Path $AppDir) { Remove-Item -Recurse -Force $AppDir }
Copy-Item -Recurse -Force (Join-Path $Tmp 'ai-automation-kit-app\app') $AppDir
New-Item -ItemType Directory -Force -Path $Ws | Out-Null
Get-ChildItem -Force (Join-Path $Tmp 'ai-automation-kit-app\kit') | ForEach-Object {
  $dest = Join-Path $Ws $_.Name
  if ($UserDirs -contains $_.Name -and (Test-Path $dest)) {
    # 내 기록 폴더는 없는 파일(README 등)만 채운다
    Get-ChildItem -Force $_.FullName | ForEach-Object {
      $f = Join-Path $dest $_.Name
      if (-not (Test-Path $f)) { Copy-Item -Recurse $_.FullName $f }
    }
  } else {
    if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
    Copy-Item -Recurse -Force $_.FullName $dest
  }
}
Remove-Item -Recurse -Force $Tmp

Step 4 '파이썬과 필요한 부품 설치 (처음엔 조금 걸려요)'
& $Uv sync --project $AppDir --frozen --quiet
if ($LASTEXITCODE -ne 0) { Fail "부품 설치 실패 (uv sync)" }

Step 5 '바탕화면 바로가기 만들기'
$Start = Join-Path $Root 'start.cmd'
@"
@echo off
chcp 65001 >nul
title AI Coach - close this window to stop
set "UV_PYTHON_INSTALL_DIR=$Root\python"
set "UV_CACHE_DIR=$Root\cache"
set "UV_PYTHON_PREFERENCE=only-managed"
set "PYTHONUTF8=1"
"$Uv" run --project "$AppDir" --frozen --quiet python "$AppDir\server.py" --workspace "$Ws" --open
if errorlevel 1 pause
"@ | Set-Content -Encoding ASCII -Path $Start

try {
  $Desktop = [Environment]::GetFolderPath('Desktop')
  $Shell = New-Object -ComObject WScript.Shell
  $Lnk = $Shell.CreateShortcut((Join-Path $Desktop 'AI 업무자동화 코치.lnk'))
  $Lnk.TargetPath = $Start
  $Lnk.WorkingDirectory = $Root
  $Lnk.IconLocation = "$env:SystemRoot\System32\shell32.dll,13"
  $Lnk.Save()
  Write-Host "  바탕화면에 'AI 업무자동화 코치' 아이콘을 만들었어요."
} catch { Write-Host "  바로가기는 만들지 못했어요. 다음부터는 $Start 를 더블클릭하세요." -ForegroundColor Yellow }

Write-Host ""
Write-Host "설치 완료! 코치를 켤게요. 브라우저가 열리면 Claude 계정으로 로그인하세요." -ForegroundColor Green
Write-Host "다음부터는 바탕화면의 'AI 업무자동화 코치' 아이콘을 더블클릭하면 돼요."
Start-Process -FilePath $Start -WorkingDirectory $Root
