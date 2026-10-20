# Set the school machine up: sync the package, then run the check and the
# install on the guest.
#
#   pwsh -File setup-guest.ps1 [-HostName <name>] [-TimeoutSec 900]
#
# This machine keeps the source only. Everything that needs an interpreter
# lives on the guest, and this script is what makes the guest ready.
param(
    [string]$HostName = "",
    [int]$TimeoutSec = 900
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "nlp_common.ps1")

$cfg = Read-NlpConfig -Known @{ host = $HostName }
$HostName = $cfg["host"]
$root = $cfg["remote_root"]

Write-Host "### syncing the package to $HostName"
& (Get-NlpTool "sync_package.ps1") -HostName $HostName | Out-Null

# The check runs on the guest, so it is pushed there first.
$tmp = Join-NlpRemote -Root $root -Parts @("tmp")
$remoteScript = Join-NlpRemote -Root $tmp -Parts @("setup_env.ps1")
& (Get-NlpTool "push2.ps1") -LocalFile (Get-NlpTool "setup_env.ps1") `
    -RemotePath $remoteScript -HostName $HostName | Out-Null

$runner = @"
`$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
& "$remoteScript" -Root "$root" 2>&1 | ForEach-Object { [Console]::Out.WriteLine([string]`$_) }
[Console]::Out.WriteLine("=== exit code: `$LASTEXITCODE ===")
"@
$scratch = Join-Path ([System.IO.Path]::GetTempPath()) "nmud_style"
if (-not (Test-Path $scratch)) { New-Item -ItemType Directory -Path $scratch | Out-Null }
$rf = Join-Path $scratch "_run_setup_env.ps1"
Set-Content -Path $rf -Value $runner -Encoding UTF8
& (Get-NlpTool "remote.ps1") -Script $rf -HostName $HostName -TimeoutSec $TimeoutSec
Remove-Item $rf -ErrorAction SilentlyContinue

# The self test wrote its result on the guest. Pull it and show it here:
# a Chinese text that travels back over ssh would be decoded in the local
# code page and turn into noise.
$remoteOut = Join-NlpRemote -Root $root -Parts @("tmp", "_selftest_out.txt")
$localOut = Join-Path $scratch "_selftest_out.txt"
try {
    & (Get-NlpTool "pull.ps1") -RemoteFile $remoteOut -LocalFile $localOut | Out-Null
    if (Test-Path $localOut) {
        Write-Host "### the self test produced:"
        foreach ($line in [System.IO.File]::ReadAllLines($localOut, [System.Text.Encoding]::UTF8)) {
            if ($line.Trim() -ne "") { Write-Host ("    " + $line) }
        }
        Remove-Item $localOut -Force -ErrorAction SilentlyContinue
    }
} catch {
    Write-Host "### (the self test output could not be pulled: $($_.Exception.Message))"
}
