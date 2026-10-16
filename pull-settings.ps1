<#
.SYNOPSIS
  Copy ci_settings from a Linux piano-PC onto os/home.

.DESCRIPTION
  /home/<user>/ci_settings  ->  os/home/ci_settings

  Pulls only .carxp and .xml files (Carla projects and JACK patchbays).
  Plugin leftovers such as sfizz .sfz/.scl links are skipped.

  Downloads into a staging folder first, then replaces the local copy so a
  failed transfer does not wipe what is already here.

.EXAMPLE
  .\pull-settings.ps1 matthew@192.168.44.29
#>
param(
    [Parameter(Position = 0)]
    [string]$Target
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $Target -or $Target -notmatch "^(?<User>[^@]+)@(?<Host>.+)$") {
    Write-Host "Usage: .\pull-settings.ps1 user@host"
    Write-Host "Example: .\pull-settings.ps1 matthew@192.168.44.29"
    exit 1
}

$remoteUser = $Matches["User"]
$remoteHome = "/home/$remoteUser"
$root = $PSScriptRoot
$osHome = Join-Path $root "os\home"
$dest = Join-Path $osHome "ci_settings"
$staging = Join-Path $root ".ci_settings_pull"

foreach ($cmd in @("scp", "ssh")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Error "$cmd not found. Install the Windows OpenSSH Client optional feature."
        exit 1
    }
}

if (-not (Test-Path $osHome)) {
    Write-Error "Expected os\home next to this script."
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

Write-Host "Pulling ci_settings from $Target"
Write-Host "  ${remoteHome}/ci_settings  ->  os\home\ci_settings"
Write-Host ""

Write-Host "Checking remote folder..."
Invoke-Native -FilePath ssh -ArgumentList @($Target, "test -d ${remoteHome}/ci_settings")

if (Test-Path $staging) {
    Remove-Item -LiteralPath $staging -Recurse -Force
}
New-Item -ItemType Directory -Path $staging | Out-Null

try {
    $remotePrefix = "${remoteHome}/ci_settings"
    $findCmd = "find $remotePrefix -type f \( -iname '*.carxp' -o -iname '*.xml' \) -print"
    Write-Host ""
    Write-Host "Listing .carxp and .xml files..."
    Write-Host "  ssh $Target $findCmd"
    $remoteFiles = @(& ssh $Target $findCmd | Where-Object { $_ -and $_.Trim() })
    if ($LASTEXITCODE -ne 0) {
        throw "ssh failed with exit code $LASTEXITCODE"
    }
    if (-not $remoteFiles) {
        throw "No .carxp or .xml files under $remotePrefix"
    }

    $pulled = Join-Path $staging "ci_settings"
    Write-Host ""
    Write-Host "Downloading $($remoteFiles.Count) files..."
    foreach ($remoteFile in $remoteFiles) {
        $remoteFile = $remoteFile.Trim()
        if (-not $remoteFile.StartsWith("$remotePrefix/")) {
            throw "Unexpected path: $remoteFile"
        }
        $rel = $remoteFile.Substring($remotePrefix.Length + 1).Replace("/", "\")
        $localFile = Join-Path $pulled $rel
        $localDir = Split-Path $localFile -Parent
        if (-not (Test-Path $localDir)) {
            New-Item -ItemType Directory -Path $localDir | Out-Null
        }
        Invoke-Native -FilePath scp -ArgumentList @(
            "${Target}:${remoteFile}",
            (ConvertTo-ScpPath $localFile)
        )
    }

    if (-not (Test-Path $pulled)) {
        throw "scp finished but ${staging}\ci_settings is missing."
    }

    Write-Host ""
    Write-Host "Replacing os\home\ci_settings..."
    if (Test-Path $dest) {
        Remove-Item -LiteralPath $dest -Recurse -Force
    }
    Move-Item -LiteralPath $pulled -Destination $dest
}
finally {
    if (Test-Path $staging) {
        Remove-Item -LiteralPath $staging -Recurse -Force
    }
}

Write-Host ""
Write-Host "Done. ci_settings is in os\home\ci_settings"
