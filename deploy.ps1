<#
.SYNOPSIS
  Copy os/home and app to a Linux piano-PC over scp.

.DESCRIPTION
  os/home/<folder>  ->  /home/<user>/<folder>
  app               ->  /home/<user>/CarlaInterface

  Skips app/.venv and __pycache__ (Windows venv is useless on the target).

.EXAMPLE
  .\deploy.ps1 matthew@192.168.44.29
#>
param(
    [Parameter(Position = 0)]
    [string]$Target
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $Target -or $Target -notmatch "^(?<User>[^@]+)@(?<Host>.+)$") {
    Write-Host "Usage: .\deploy.ps1 user@host"
    Write-Host "Example: .\deploy.ps1 matthew@192.168.44.29"
    exit 1
}

$remoteUser = $Matches["User"]
$remoteHome = "/home/$remoteUser"
$root = $PSScriptRoot
$osHome = Join-Path $root "os\home"
$appDir = Join-Path $root "app"

foreach ($cmd in @("scp", "ssh")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Error "$cmd not found. Install the Windows OpenSSH Client optional feature."
        exit 1
    }
}

if (-not (Test-Path $osHome) -or -not (Test-Path $appDir)) {
    Write-Error "Expected os\home and app next to this script."
    exit 1
}

function ConvertTo-ScpPath([string]$Path) {
    $Path.Replace("\", "/")
}

function Invoke-Native {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$ArgumentList
    )
    Write-Host "  $FilePath $($ArgumentList -join ' ')"
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath failed with exit code $LASTEXITCODE"
    }
}

Write-Host "Deploying to $Target"
Write-Host "  os\home\*  ->  ${remoteHome}/"
Write-Host "  app        ->  ${remoteHome}/CarlaInterface/"
Write-Host ""

Write-Host "Copying os overlay..."
Get-ChildItem -Path $osHome -Force | ForEach-Object {
    Invoke-Native -FilePath scp -ArgumentList @(
        "-r",
        (ConvertTo-ScpPath $_.FullName),
        "${Target}:${remoteHome}/"
    )
}

Write-Host ""
Write-Host "Copying app as CarlaInterface..."
Invoke-Native -FilePath ssh -ArgumentList @($Target, "mkdir -p ${remoteHome}/CarlaInterface")

$appItems = Get-ChildItem -Path $appDir -Force | Where-Object {
    $_.Name -notin @(".venv", "__pycache__")
}
if (-not $appItems) {
    Write-Error "Nothing to copy from app\ (after excluding .venv and __pycache__)."
    exit 1
}

$appCopyArgs = [System.Collections.Generic.List[string]]::new()
$appCopyArgs.Add("-r")
foreach ($item in $appItems) {
    $appCopyArgs.Add((ConvertTo-ScpPath $item.FullName))
}
$appCopyArgs.Add("${Target}:${remoteHome}/CarlaInterface/")
Invoke-Native -FilePath scp -ArgumentList $appCopyArgs.ToArray()

Write-Host ""
Write-Host "Fixing remote execute bits..."
$remoteFix = "find $remoteHome/startup_scripts -type f -name '*.sh' -exec chmod +x {} +; " +
    "if [ -f $remoteHome/CarlaInterface/assets/sendmidi ]; then chmod +x $remoteHome/CarlaInterface/assets/sendmidi; fi; " +
    "find $remoteHome/CarlaInterface -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true"
Invoke-Native -FilePath ssh -ArgumentList @($Target, $remoteFix)

Write-Host ""
Write-Host "Done. Overlay is in $remoteHome; app is in $remoteHome/CarlaInterface"
