# Run a PowerShell script on the school machine over SSH.
#
# The guest's default shell is cmd.exe, so nested quoting is painful. We sidestep it
# entirely: PowerShell -EncodedCommand takes ONE base64 token (UTF-16LE script).
#
# Usage:
#   pwsh -File remote.ps1 -Script <local .ps1> [-HostName school-guest] [-TimeoutSec 300]
param(
    [Parameter(Mandatory = $true)][string]$Script,
    [string]$HostName = "",
    [int]$TimeoutSec = 300,
    [string]$OutFile = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "nlp_common.ps1")

$cfg = Read-NlpConfig -Known @{ host = $HostName }
$HostName = $cfg["host"]
$SSH = Get-NlpSsh
$KN = Get-NlpKnownHosts

# The guest's stdin is NUL: a script that asks a question must see EOF
# instead of blocking forever on a session nobody can type into.

# The ssh transcript is transient, so it goes to the temp directory. Writing
# it next to the workspace left hundreds of remote_*.log / remote_*.err files
# behind.
$scratch = Join-Path ([System.IO.Path]::GetTempPath()) "nmud_style"
if (-not (Test-Path $scratch)) { New-Item -ItemType Directory -Path $scratch | Out-Null }

if (-not $OutFile) {
    $OutFile = Join-Path $scratch ("remote_" + [guid]::NewGuid().ToString("N").Substring(0,8) + ".log")
}

$body = Get-Content $Script -Raw
$bytes = [System.Text.Encoding]::Unicode.GetBytes($body)
$b64 = [Convert]::ToBase64String($bytes)

$errFile = [System.IO.Path]::ChangeExtension($OutFile, ".err")
# An empty file as stdin: the guest sees EOF at once, so a script that asks
# a question gives up instead of blocking on a session nobody can type into.
$emptyStdin = Join-Path $scratch "_empty_stdin.txt"
# ascii, no BOM: under Windows PowerShell 5.1 a UTF-8 file starts with a BOM,
# and the guest would read that as the answer instead of seeing EOF
"" | Out-File -FilePath $emptyStdin -Encoding ascii -NoNewline
$args = @(
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=15",
    "-o", "UserKnownHostsFile=$KN",
    "-o", "StrictHostKeyChecking=yes",
    $HostName,
    "powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $b64"
)

$p = Start-Process -FilePath $SSH -ArgumentList $args -NoNewWindow -PassThru `
                   -RedirectStandardInput $emptyStdin `
                   -RedirectStandardOutput $OutFile -RedirectStandardError $errFile
$null = $p.WaitForExit($TimeoutSec * 1000)
if (-not $p.HasExited) {
    try { $p.Kill() } catch {}
    Write-Host "### TIMEOUT after ${TimeoutSec}s"
} else {
    Write-Host "### exit=$($p.ExitCode)"
}

$out = Get-Content $OutFile -Raw -ErrorAction SilentlyContinue
$err = Get-Content $errFile -Raw -ErrorAction SilentlyContinue
if ($out) { Write-Host $out.TrimEnd() }
if ($err) { Write-Host "--- stderr ---"; Write-Host $err.TrimEnd() }
