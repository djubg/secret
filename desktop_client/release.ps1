param(
    [Parameter(Mandatory = $true)]
    [string]$Version,
    [string]$Notes = "",
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$PythonExe = "python",
    [switch]$SkipBuild,
    [switch]$SkipChecksum
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Step([string]$Message) {
    Write-Host "[release] $Message" -ForegroundColor Cyan
}

function Assert-File([string]$PathValue) {
    if (-not (Test-Path $PathValue)) {
        throw "Required file not found: $PathValue"
    }
}

function Convert-ToHashtable($Value) {
    if ($null -eq $Value) {
        return $null
    }
    if ($Value -is [System.Collections.IDictionary]) {
        $ht = @{}
        foreach ($key in $Value.Keys) {
            $ht[$key] = Convert-ToHashtable $Value[$key]
        }
        return $ht
    }
    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {
        $arr = @()
        foreach ($item in $Value) {
            $arr += ,(Convert-ToHashtable $item)
        }
        return $arr
    }
    if ($Value -is [psobject] -and $Value.PSObject.Properties.Count -gt 0) {
        $ht = @{}
        foreach ($prop in $Value.PSObject.Properties) {
            $ht[$prop.Name] = Convert-ToHashtable $prop.Value
        }
        return $ht
    }
    return $Value
}

$desktopRoot = $PSScriptRoot
$repoRoot = (Resolve-Path (Join-Path $desktopRoot "..")).Path
$versionFile = Join-Path $desktopRoot "config\version.py"
$checksumTool = Join-Path $desktopRoot "tools\generate_checksums.py"
$buildScript = Join-Path $desktopRoot "build_exe.ps1"
$distDir = Join-Path $desktopRoot "dist"
$downloadsDir = Join-Path $repoRoot "server\app\static\downloads"
$releasesFile = Join-Path $repoRoot "server\app\static\releases.json"

Assert-File $versionFile
Assert-File $buildScript
Assert-File $checksumTool

if ([string]::IsNullOrWhiteSpace($Notes)) {
    $Notes = "Release $Version"
}

Write-Step "Updating desktop_client/config/version.py to $Version"
$versionContent = Get-Content $versionFile -Raw -Encoding UTF8
$versionContent = [Regex]::Replace(
    $versionContent,
    "APP_VERSION\s*=\s*""[^""]*""",
    "APP_VERSION = `"$Version`""
)
Set-Content -Path $versionFile -Value $versionContent -Encoding UTF8

if (-not $SkipChecksum) {
    Write-Step "Generating checksums"
    Push-Location $desktopRoot
    try {
        & $PythonExe $checksumTool
    }
    finally {
        Pop-Location
    }
}

if (-not $SkipBuild) {
    Write-Step "Cleaning previous build/dist folders"
    Remove-Item -Recurse -Force (Join-Path $desktopRoot "build"), $distDir -ErrorAction SilentlyContinue

    Write-Step "Building NovaDesktop.exe and NovaEngine.exe"
    Push-Location $desktopRoot
    try {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $buildScript -PythonExe $PythonExe
    }
    finally {
        Pop-Location
    }
}

$desktopExe = Join-Path $distDir "NovaDesktop.exe"
$engineExe = Join-Path $distDir "NovaEngine.exe"
$engineDir = Join-Path $distDir "engine"
Assert-File $desktopExe
Assert-File $engineExe
Assert-File $engineDir

Write-Step "Creating update zip"
New-Item -ItemType Directory -Force -Path $downloadsDir | Out-Null
$zipFile = Join-Path $downloadsDir "desktop_client_$Version.zip"
if (Test-Path $zipFile) {
    Remove-Item -Force $zipFile
}
Compress-Archive -Path (Join-Path $distDir "*") -DestinationPath $zipFile -Force

Write-Step "Updating server/app/static/releases.json"
$releasePayload = @{}
if (Test-Path $releasesFile) {
    $raw = Get-Content $releasesFile -Raw -Encoding UTF8
    if (-not [string]::IsNullOrWhiteSpace($raw)) {
        $parsed = $raw | ConvertFrom-Json -Depth 20
        if ($null -ne $parsed) {
            $releasePayload = Convert-ToHashtable $parsed
        }
    }
}

$downloadUrl = "$($BaseUrl.TrimEnd('/'))/static/downloads/desktop_client_$Version.zip"
$latest = @{
    version = $Version
    download_url = $downloadUrl
    entry_exe = "NovaDesktop.exe"
    notes = $Notes
}
$releasePayload["latest"] = $latest

$jsonOut = $releasePayload | ConvertTo-Json -Depth 20
Set-Content -Path $releasesFile -Value $jsonOut -Encoding UTF8

Write-Host ""
Write-Host "Release ready." -ForegroundColor Green
Write-Host "Version:     $Version"
Write-Host "Desktop EXE: $desktopExe"
Write-Host "Engine EXE:  $engineExe"
Write-Host "ZIP:         $zipFile"
Write-Host "URL:         $downloadUrl"
Write-Host "Updated:     $releasesFile"
