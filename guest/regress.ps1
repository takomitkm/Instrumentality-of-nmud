# Regression: run every guest tool with the current path logic and compare
# the result with the json that is already on the guest. Same bytes means the
# change touched nothing but the paths.
#
#   pwsh -File regress.ps1
param(
    [string]$HostName = "",
    [int]$TimeoutSec = 2400
)

$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "nlp_common.ps1")

$cfg = Read-NlpConfig -Known @{ host = $HostName }
$HostName = $cfg["host"]
$root = $cfg["remote_root"]
$tmp = Join-NlpRemote -Root $root -Parts @("tmp")
$out = Join-NlpRemote -Root $root -Parts @("out")

$cases = @(
    @{ script = "nmud_style.py";       name = "nmud_style.json";        args = @("--report") },
    @{ script = "nmud_rules.py";       name = "nmud_rules.json";        args = @("--out") },
    @{ script = "generative_model.py"; name = "generative_model.json";  args = @("--out") },
    @{ script = "integrity.py";        name = "integrity_report.json";  args = @("--out") },
    @{ script = "style_gen.py";        name = "style_gen.json";         args = @("--out") }
)

$runner = Get-NlpTool "runpy.ps1"
$remoteHelper = Get-NlpTool "remote.ps1"

foreach ($c in $cases) {
    $dest = Join-NlpRemote -Root $tmp -Parts @("regress_" + $c.name)
    $pyArgs = @($c.args[0], $dest)
    Write-Output "########## $($c.script) ##########"
    & $runner -Script (Join-Path $PSScriptRoot $c.script) -HostName $HostName `
               -TimeoutSec $TimeoutSec -PyArgs $pyArgs 2>&1 |
        Select-String -Pattern "=== exit code|Traceback|Error:" |
        ForEach-Object { $_.Line }
}

# compare on the guest: the files never come back to this machine
# (the name list is built here: an escaped variable inside a $( ) inside a
# here-string is not valid code)
$names = "'" + (($cases | ForEach-Object { $_.name }) -join "','") + "'"
$cmp = @"
`$tmp = "$tmp"
`$out = "$out"
`$names = @($names)
foreach (`$n in `$names) {
    `$a = Join-Path `$tmp ("regress_" + `$n)
    `$b = Join-Path `$out `$n
    if (-not (Test-Path `$a)) { Write-Output ("MISSING " + `$a); continue }
    `$ma = (Get-FileHash `$a -Algorithm MD5).Hash.ToLower()
    `$mb = (Get-FileHash `$b -Algorithm MD5).Hash.ToLower()
    if (`$ma -eq `$mb) {
        Write-Output ("SAME  {0,-26} {1} bytes" -f `$n, (Get-Item `$b).Length)
    } else {
        Write-Output ("DIFF  {0,-26} new {1} B / old {2} B" -f `$n, (Get-Item `$a).Length, (Get-Item `$b).Length)
    }
    Remove-Item `$a -Force -ErrorAction SilentlyContinue
}
"@
$cmpFile = Join-Path ([System.IO.Path]::GetTempPath()) "nmud_style\_regress_cmp.ps1"
Set-Content -Path $cmpFile -Value $cmp -Encoding UTF8
& $remoteHelper -Script $cmpFile -HostName $HostName -TimeoutSec 180 |
    Select-String -Pattern "SAME |DIFF |MISSING" | ForEach-Object { $_.Line }
Remove-Item $cmpFile -ErrorAction SilentlyContinue
