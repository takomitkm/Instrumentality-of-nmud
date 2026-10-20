# Run a PowerShell script on the school machine by pushing it first.
# (The -EncodedCommand route overflows the command line for long scripts.)
#
# Usage:
#   pwsh -File runps.ps1 -Script <local .ps1> [-TimeoutSec 900]
param(
    [Parameter(Mandatory = $true)][string]$Script,
    [string]$HostName = "",
    [int]$TimeoutSec = 900
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "nlp_common.ps1")

$cfg = Read-NlpConfig -Known @{ host = $HostName }
$HostName = $cfg["host"]
$root = $cfg["remote_root"]

$name = [System.IO.Path]::GetFileName($Script)
$remote = Join-NlpRemote -Root $root -Parts @("tools", $name)

$push = Get-NlpTool "push2.ps1"
$remoteHelper = Get-NlpTool "remote.ps1"
& $push -LocalFile $Script -RemotePath $remote -HostName $HostName | Out-Null

$runner = @"
`$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
`$ProgressPreference = "SilentlyContinue"
[Console]::Out.WriteLine("=== run $remote ===")
& powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$remote" 2>&1 |
    ForEach-Object { [Console]::Out.WriteLine([string]`$_) }
[Console]::Out.WriteLine("=== exit code: `$LASTEXITCODE ===")
"@
$scratch = Join-Path ([System.IO.Path]::GetTempPath()) "nmud_style"
if (-not (Test-Path $scratch)) { New-Item -ItemType Directory -Path $scratch | Out-Null }
$rf = Join-Path $scratch "_runner.ps1"
Set-Content -Path $rf -Value $runner -Encoding UTF8
& $remoteHelper -Script $rf -HostName $HostName -TimeoutSec $TimeoutSec
Remove-Item $rf -ErrorAction SilentlyContinue
