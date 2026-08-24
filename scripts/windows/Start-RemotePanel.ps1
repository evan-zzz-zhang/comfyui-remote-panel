[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,
    [string]$ConfigPath = 'config.toml',
    [string]$PythonPath = '.venv\Scripts\python.exe'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $ProjectRoot).Path
$python = Join-Path $root $PythonPath
$config = Join-Path $root $ConfigPath

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Panel Python was not found. Create the virtual environment first."
}
if (-not (Test-Path -LiteralPath $config -PathType Leaf)) {
    throw "Panel config was not found. Copy config.example.toml and configure it first."
}

try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8190/healthz' -TimeoutSec 1
    if ($health.status -eq 'ok') {
        Write-Output 'already-running'
        exit 0
    }
} catch {
}

$process = Start-Process -FilePath $python `
    -ArgumentList @('-m', 'comfyui_remote_panel', '--config', $config) `
    -WorkingDirectory $root -WindowStyle Hidden -PassThru

for ($attempt = 0; $attempt -lt 20; $attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8190/healthz' -TimeoutSec 1
        if ($health.status -eq 'ok') {
            Write-Output $process.Id
            exit 0
        }
    } catch {
    }
    if ($process.HasExited) {
        break
    }
}

if (-not $process.HasExited) {
    Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
}
throw 'Panel health check failed.'
