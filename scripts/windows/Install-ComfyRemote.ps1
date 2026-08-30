[CmdletBinding()]
param(
    [string]$PythonPath = "python",
    [string]$ConfigPath = "config.toml"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $root

function Test-VenvPython {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $false
    }

    try {
        & $Path -c "import sys,re,json,ssl,pip; ok = sys.version_info >= (3, 11) and sys.version_info.releaselevel == 'final'; raise SystemExit(0 if ok else 1)" > $null 2>&1
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Get-BrokenVenvBackupPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $candidate = Join-Path $Root (".venv.broken-{0}" -f $stamp)
    $counter = 1
    while (Test-Path -LiteralPath $candidate) {
        $candidate = Join-Path $Root (".venv.broken-{0}-{1}" -f $stamp, $counter)
        $counter += 1
    }
    return $candidate
}

Write-Host "Comfy Remote Windows bootstrap"
Write-Host "Project: $root"

try {
    $versionInfo = & $PythonPath -c "import sys,re,json,ssl,venv; ok = sys.version_info >= (3, 11) and sys.version_info.releaselevel == 'final'; print(sys.version.split()[0]); raise SystemExit(0 if ok else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "A stable Python 3.11 or newer release is required. Pre-release alpha/beta/rc builds are not supported."
    }
} catch {
    throw "A healthy stable Python 3.11 or newer release was not found. Install or repair Python, make sure python.exe is on PATH, reopen PowerShell, then run this script again."
}
Write-Host "Python: $versionInfo"

$venvDir = Join-Path $root ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$createVenv = $true

if (Test-Path -LiteralPath $venvDir) {
    Write-Host "Checking existing .venv..."
    if (Test-VenvPython -Path $venvPython) {
        Write-Host "Existing .venv health check: OK"
        $createVenv = $false
    } else {
        $backupPath = Get-BrokenVenvBackupPath -Root $root
        Write-Host "Existing .venv is unhealthy and will be preserved before rebuilding."
        Move-Item -LiteralPath $venvDir -Destination $backupPath
        Write-Host "Backed up unhealthy .venv to: $backupPath"
    }
}

if ($createVenv) {
    Write-Host "Creating .venv..."
    & $PythonPath -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { throw "Failed to create .venv." }

    if (-not (Test-VenvPython -Path $venvPython)) {
        throw "Fresh .venv failed its health check. Repair the base Python installation and run this installer again."
    }
    Write-Host "Fresh .venv health check: OK"
}

Write-Host "Installing Comfy Remote..."
& $venvPython -m pip install -e $root
if ($LASTEXITCODE -ne 0) { throw "Comfy Remote installation failed." }

$installedVersion = & $venvPython -c "import comfyui_remote_panel; print(comfyui_remote_panel.__version__)"
if ($LASTEXITCODE -ne 0) {
    throw "Comfy Remote was installed but could not be imported from .venv."
}
Write-Host "Installed Comfy Remote: $installedVersion"

$config = if ([System.IO.Path]::IsPathRooted($ConfigPath)) { $ConfigPath } else { Join-Path $root $ConfigPath }

Write-Host ""
Write-Host "Starting setup wizard..."
& $venvPython -m comfyui_remote_panel setup --config $config
if ($LASTEXITCODE -ne 0) { throw "Setup did not complete successfully." }

Write-Host ""
Write-Host "Bootstrap complete."
Write-Host "Run diagnostics with:"
Write-Host "  .\.venv\Scripts\comfyui-remote-panel.exe doctor --config `"$ConfigPath`""
