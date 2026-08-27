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
    $version = & $PythonPath -c "import sys; print('.'.join(map(str, sys.version_info[:3]))); raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.11 or newer is required."
    }
} catch {
    throw "Python 3.11 or newer was not found. Install Python, reopen PowerShell, then run this script again."
}
Write-Host "Python: $version"

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
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
