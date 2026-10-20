# Run the nmud_style package on the school machine.
#
#   pwsh -File run_pkg.ps1 [-PyArgs @("--in","x.txt","--out","y.txt")] [-SkipSync]
#
# The package is synced first (only the files that differ are pushed),
# then the guest runs it with the venv python: python -m nmud_style.
param(
    [string]$HostName = "",
    [int]$TimeoutSec = 600,
    [string[]]$PyArgs = @(),
    [switch]$SkipSync
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "nlp_common.ps1")

$cfg = Read-NlpConfig -Known @{ host = $HostName }
$HostName = $cfg["host"]
$root = $cfg["remote_root"]

if (-not $SkipSync) {
    & (Get-NlpTool "sync_package.ps1") -HostName $HostName | Out-Null
}

$python = Join-NlpRemote -Root $root -Parts @(".venv", "Scripts", "python.exe")
$tools = Join-NlpRemote -Root $root -Parts @("tools")

$argList = ""
foreach ($a in $PyArgs) {
    if ($argList -ne "") { $argList += "," }
    $argList += '"' + $a.Replace('"', '\"') + '"'
}

$runner = @"
`$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
`$vp = "$python"
`$env:PYTHONIOENCODING = "utf-8"
`$pyargs = @($argList)
Set-Location "$tools"
[Console]::Out.WriteLine("=== run nmud_style in $tools ===")
& `$vp -m nmud_style @pyargs 2>&1 | ForEach-Object { [Console]::Out.WriteLine([string]`$_) }
[Console]::Out.WriteLine("=== exit code: `$LASTEXITCODE ===")
"@
$scratch = Join-Path ([System.IO.Path]::GetTempPath()) "nmud_style"
if (-not (Test-Path $scratch)) { New-Item -ItemType Directory -Path $scratch | Out-Null }
$rf = Join-Path $scratch "_run_pkg.ps1"
Set-Content -Path $rf -Value $runner -Encoding UTF8
& (Get-NlpTool "remote.ps1") -Script $rf -HostName $HostName -TimeoutSec $TimeoutSec
Remove-Item $rf -ErrorAction SilentlyContinue
