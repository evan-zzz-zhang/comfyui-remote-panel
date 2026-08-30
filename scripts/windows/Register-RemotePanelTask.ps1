[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,
    [string]$ConfigPath = 'config.toml',
    [string]$PythonPath = '.venv\Scripts\python.exe',
    [string]$TaskName = 'ComfyUI Remote Panel'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $ProjectRoot).Path
$pythonCandidate = if ([System.IO.Path]::IsPathRooted($PythonPath)) { $PythonPath } else { Join-Path $root $PythonPath }
$configCandidate = if ([System.IO.Path]::IsPathRooted($ConfigPath)) { $ConfigPath } else { Join-Path $root $ConfigPath }
$python = (Resolve-Path -LiteralPath $pythonCandidate).Path
$config = (Resolve-Path -LiteralPath $configCandidate).Path
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

$pythonw = Join-Path (Split-Path -Parent $python) 'pythonw.exe'
$launcher = if (Test-Path -LiteralPath $pythonw) { $pythonw } else { $python }

$action = New-ScheduledTaskAction `
    -Execute $launcher `
    -Argument ('-m comfyui_remote_panel start --config \"{0}\"' -f $config) `
    -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description 'Starts ComfyUI Remote Panel at sign-in using the same background launcher as the CLI.' `
    -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Milliseconds 500
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
