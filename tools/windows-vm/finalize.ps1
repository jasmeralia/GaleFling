$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

Write-Host 'Starting the VirtIO-FS repository share.'
Start-Service VirtioFsSvc
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    if (Test-Path 'Z:\requirements.txt') {
        break
    }
    Start-Sleep -Seconds 2
}
if (-not (Test-Path 'Z:\requirements.txt')) {
    throw 'The GaleFling repository did not appear at Z:.'
}

Write-Host 'Installing GaleFling Python dependencies.'
$python = 'C:\Program Files\Python312\python.exe'
$venvPython = 'C:\GaleFling-venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    & $python -m venv 'C:\GaleFling-venv'
}
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r 'Z:\requirements.txt' -r 'Z:\requirements-dev.txt'
if ($LASTEXITCODE -ne 0) {
    throw "pip failed with exit code $LASTEXITCODE."
}

Write-Host 'Creating a credential-free local test copy.'
& robocopy.exe 'Z:\' 'C:\GaleFling' /MIR /XD 'Z:\.git' 'Z:\.venv' /XF '.env' 'logs' /NFL /NDL /NJH /NJS /NP /R:1 /W:1
if ($LASTEXITCODE -gt 7) {
    throw "robocopy failed with exit code $LASTEXITCODE."
}

Write-Host 'Installing the built-in OpenSSH Server capability.'
$capability = Get-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0'
if ($capability.State -ne 'Installed') {
    Add-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0' | Out-Null
}
Set-Service sshd -StartupType Automatic
Start-Service sshd
if (-not (Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule `
        -Name 'OpenSSH-Server-In-TCP' `
        -DisplayName 'OpenSSH Server (sshd)' `
        -Enabled True `
        -Direction Inbound `
        -Protocol TCP `
        -Action Allow `
        -LocalPort 22 | Out-Null
}
Set-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -Enabled True -Profile Any
$authorizedKeys = 'C:\ProgramData\ssh\administrators_authorized_keys'
& icacls.exe $authorizedKeys /inheritance:r /grant 'Administrators:F' /grant 'SYSTEM:F' | Out-Null

Write-Host 'Running the credential-free media-processing acceptance test.'
& $venvPython -m pytest 'C:\GaleFling\tests\functional\test_media_processing.py' -q
if ($LASTEXITCODE -ne 0) {
    throw "The media-processing test failed with exit code $LASTEXITCODE."
}

Set-Content -Path 'C:\galefling-finalize-complete.txt' -Value (Get-Date -Format o)
Write-Host 'GALEFLING_VM_READY'
