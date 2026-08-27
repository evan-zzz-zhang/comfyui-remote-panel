[CmdletBinding()]
param(
    [string]$PythonPath = "python",
    [string]$ConfigPath = "config.toml"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $root

Write-Host "Comfy Remote Windows bootstrap"
Write-Host "Project: $root"

try {
    $versionInfo = & $PythonPath -c "import sys; ok = sys.version_info >= (3, 11) and sys.version_info.releaselevel == 'final'; print(sys.version.split()[0]); raise SystemExit(0 if ok else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "A stable Python 3.11 or newer release is required. Pre-release alpha/beta/rc builds are not supported."
    }
} catch {
    throw "A stable Python 3.11 or newer release was not found. Install a stable Python release, make sure python.exe is on PATH, reopen PowerShell, then run this script again."
}
Write-Host "Python: $versionInfo"

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    $venvOk = & $venvPython -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) and sys.version_info.releaselevel == 'final' else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "Existing .venv uses an unsupported pre-release/old Python. Delete .venv and rerun this installer with a stable Python 3.11 or newer release."
    }
} else {
    Write-Host "Creating .venv..."
    & $PythonPath -m venv (Join-Path $root ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Failed to create .venv." }
}

Write-Host "Installing Comfy Remote..."
& $venvPython -m pip install -e $root
if ($LASTEXITCODE -ne 0) { throw "Comfy Remote installation failed." }

Write-Host ""
Write-Host "Starting setup wizard..."
& $venvPython -m comfyui_remote_panel setup --config (Join-Path $root $ConfigPath)
if ($LASTEXITCODE -ne 0) { throw "Setup did not complete successfully." }

Write-Host ""
Write-Host "Bootstrap complete."
Write-Host "Run diagnostics with:"
Write-Host "  .\.venv\Scripts\comfyui-remote-panel.exe doctor --config `"$ConfigPath`""
