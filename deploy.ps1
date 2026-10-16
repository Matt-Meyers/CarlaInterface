<#
.SYNOPSIS
  Copy os/home and app to a Linux piano-PC over scp.

.DESCRIPTION
  os/home/<folder>  ->  /home/<user>/<folder>
  app               ->  /home/<user>/CarlaInterface

  Skips app/.venv and __pycache__ (Windows venv is useless on the target).
  -AppOnly / --app-only copies only the app and leaves the overlay untouched.

.EXAMPLE
  .\deploy.ps1 matthew@192.168.44.29
.EXAMPLE
  .\deploy.ps1 matthew@192.168.44.29 --app-only
#>
param(
    [Parameter(Position = 0)]
    [string]$Target,

    [Alias("app-only")]
    [switch]$AppOnly,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Remaining
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($null -ne $Remaining) {
    foreach ($arg in @($Remaining)) {
        if ($arg -eq "--app-only") {
            $AppOnly = $true
        } else {
            Write-Host "Unknown argument: $arg"
            Write-Host "Usage: .\deploy.ps1 user@host [--app-only]"
            exit 1
        }
    }
}

if (-not $Target -or $Target -notmatch "^(?<User>[^@]+)@(?<Host>.+)$") {
    Write-Host "Usage: .\deploy.ps1 user@host [--app-only]"
    Write-Host "Example: .\deploy.ps1 matthew@192.168.44.29"
    Write-Host "         .\deploy.ps1 matthew@192.168.44.29 --app-only"
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

if (-not (Test-Path $appDir) -or (-not $AppOnly -and -not (Test-Path $osHome))) {
    Write-Error $(if ($AppOnly) { "Expected app next to this script." } else { "Expected os\home and app next to this script." })
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
if (-not $AppOnly) {
    Write-Host "  os\home\*  ->  ${remoteHome}/"
}
Write-Host "  app        ->  ${remoteHome}/CarlaInterface/"
Write-Host ""

if (-not $AppOnly) {
    Write-Host "Copying os overlay..."
    Get-ChildItem -Path $osHome -Force | ForEach-Object {
        Invoke-Native -FilePath scp -ArgumentList @(
            "-r",
            (ConvertTo-ScpPath $_.FullName),
            "${Target}:${remoteHome}/"
        )
    }
    Write-Host ""
}

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
$remoteFixParts = [System.Collections.Generic.List[string]]::new()
if (-not $AppOnly) {
    $remoteFixParts.Add("find $remoteHome/startup_scripts -type f -name '*.sh' -exec chmod +x {} +")
}
$remoteFixParts.Add("rm -f $remoteHome/CarlaInterface/assets/sendmidi")
$remoteFixParts.Add("find $remoteHome/CarlaInterface -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true")
Invoke-Native -FilePath ssh -ArgumentList @($Target, ($remoteFixParts -join "; "))

Write-Host ""
if ($AppOnly) {
    Write-Host "Done. App is in $remoteHome/CarlaInterface (overlay left untouched)"
} else {
    Write-Host "Done. Overlay is in $remoteHome; app is in $remoteHome/CarlaInterface"
}
