# Run a Python script on the school machine, encoding-safe.
#
# The previous approach wrote the script to disk with Set-Content -Encoding UTF8
# from a PowerShell file that itself had been read as GBK, so the Chinese
# literals inside the script arrived mangled. This writes the script as
# base64 (ASCII-safe) and has the guest decode it as UTF-8.
#
# Usage:
#   pwsh -File runpy.ps1 -Script <local .py> [-PyArgs @("--in","x.txt")] [-TimeoutSec 900]
param(
    [Parameter(Mandatory = $true)][string]$Script,
    [string]$HostName = "",
    [int]$TimeoutSec = 600,
    [string[]]$PyArgs = @(),
    [switch]$SkipPush
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "nlp_common.ps1")

$cfg = Read-NlpConfig -Known @{ host = $HostName }
$HostName = $cfg["host"]
$root = $cfg["remote_root"]

$name = [System.IO.Path]::GetFileName($Script)
$remote = Join-NlpRemote -Root $root -Parts @("tools", $name)
$python = Join-NlpRemote -Root $root -Parts @(".venv", "Scripts", "python.exe")

$push = Get-NlpTool "push2.ps1"
$remoteHelper = Get-NlpTool "remote.ps1"
if (-not $SkipPush) {
    & $push -LocalFile $Script -RemotePath $remote -HostName $HostName | Out-Null

    # Push the sibling modules the script imports, so the guest never runs a
    # stale copy of a shared helper.
    $src = Get-Content $Script -Raw
    $here = Split-Path $Script -Parent
    foreach ($m in [regex]::Matches($src, '(?m)^\s*(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)')) {
        $name = $m.Groups[1].Value
        $sib = Join-Path $here ($name + ".py")
        if ((Test-Path $sib) -and ($sib -ne $Script)) {
            $dest = Join-NlpRemote -Root $root -Parts @("tools", ($name + ".py"))
            Write-Host "### pushing dependency $name"
            & $push -LocalFile $sib -RemotePath $dest -HostName $HostName | Out-Null
        }
    }
} else {
    # The guest runs the copy it already has. Push the script yourself when
    # you change it.
    Write-Host "### using the copy on the guest: $remote"
}

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
[Console]::Out.WriteLine("=== run $remote ===")
& `$vp "$remote" @pyargs 2>&1 | ForEach-Object { [Console]::Out.WriteLine([string]`$_) }
[Console]::Out.WriteLine("=== exit code: `$LASTEXITCODE ===")
"@
$scratch = Join-Path ([System.IO.Path]::GetTempPath()) "nmud_style"
if (-not (Test-Path $scratch)) { New-Item -ItemType Directory -Path $scratch | Out-Null }
$rf = Join-Path $scratch "_runner.ps1"
Set-Content -Path $rf -Value $runner -Encoding UTF8
& $remoteHelper -Script $rf -HostName $HostName -TimeoutSec $TimeoutSec
Remove-Item $rf -ErrorAction SilentlyContinue
