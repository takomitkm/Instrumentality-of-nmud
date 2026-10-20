# Pull a file back from the school machine: remote side base64-encodes it,
# local side decodes. Pure PowerShell on both ends, no argv quoting games.
#
# Usage:
#   pwsh -File pull.ps1 -RemoteFile <path on the guest> [-LocalFile <path here>]
param(
    [Parameter(Mandatory = $true)][string]$RemoteFile,
    [string]$LocalFile = "",
    [string]$HostName = "",
    [int]$TimeoutSec = 180
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "nlp_common.ps1")

$cfg = Read-NlpConfig -Known @{ host = $HostName }
$HostName = $cfg["host"]
$SSH = Get-NlpSsh
$KN = Get-NlpKnownHosts

if ($LocalFile -eq "") {
    $LocalFile = Join-Path $PSScriptRoot (Split-Path $RemoteFile -Leaf)
    Write-Host "### local path: $LocalFile"
}

$body = @"
`$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
`$b = [System.IO.File]::ReadAllBytes("$RemoteFile")
[Console]::Out.WriteLine([Convert]::ToBase64String(`$b))
"@
$bodyB64 = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($body))

$scratch = Join-Path ([System.IO.Path]::GetTempPath()) "nmud_style"
if (-not (Test-Path $scratch)) { New-Item -ItemType Directory -Path $scratch | Out-Null }
$outFile = Join-Path $scratch ("_pull_" + [guid]::NewGuid().ToString("N").Substring(0,8) + ".txt")
$errFile = [System.IO.Path]::ChangeExtension($outFile, ".err")
$emptyStdin = Join-Path $scratch "_empty_stdin.txt"
# ascii, no BOM: under Windows PowerShell 5.1 a UTF-8 file starts with a BOM
"" | Out-File -FilePath $emptyStdin -Encoding ascii -NoNewline
$args = @(
    "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
    "-o", "UserKnownHostsFile=$KN", "-o", "StrictHostKeyChecking=yes",
    $HostName,
    "powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $bodyB64"
)
$p = Start-Process -FilePath $SSH -ArgumentList $args -NoNewWindow -PassThru `
                   -RedirectStandardInput $emptyStdin `
                   -RedirectStandardOutput $outFile -RedirectStandardError $errFile
$null = $p.WaitForExit($TimeoutSec * 1000)
if (-not $p.HasExited) { try { $p.Kill() } catch {}; Write-Host "TIMEOUT"; exit 1 }

$raw = Get-Content $outFile -Raw
if (-not $raw) {
    Write-Host "no output; stderr:"
    Get-Content $errFile -Raw | Write-Host
    exit 1
}
$b64 = ($raw -split "`r?`n" | Where-Object { $_ -match '^[A-Za-z0-9+/=]+$' }) -join ""
[System.IO.File]::WriteAllBytes($LocalFile, [Convert]::FromBase64String($b64))
Write-Host "pulled $((Get-Item $LocalFile).Length) bytes -> $LocalFile"
Remove-Item $outFile, $errFile -ErrorAction SilentlyContinue
