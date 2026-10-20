# Make the guest's copy of the nmud_style package match the local one.
#
#   pwsh -File sync_package.ps1 [-HostName <name>] [-Force]
#
# Only the files whose md5 differs are pushed, so a normal run costs one
# ssh round trip and transfers nothing. The files the guest has that the
# local package does not have are listed, not deleted: the guest is not
# this script's to clean out.
param(
    [string]$HostName = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "nlp_common.ps1")

$cfg = Read-NlpConfig -Known @{ host = $HostName }
$HostName = $cfg["host"]
$root = $cfg["remote_root"]

$local = Join-Path (Split-Path $PSScriptRoot -Parent) "nmud_style"
if (-not (Test-Path $local)) { throw "the package is missing: $local" }
$remoteDir = Join-NlpRemote -Root $root -Parts @("tools", "nmud_style")

# 1) what does the guest have? One round trip.
$list = @"
`$ErrorActionPreference = "SilentlyContinue"
`$dir = "$remoteDir"
if (Test-Path `$dir) {
    Get-ChildItem `$dir -Recurse -File | ForEach-Object {
        `$rel = `$_.FullName.Substring(`$dir.Length + 1).Replace('\', '/')
        `$md5 = (Get-FileHash `$_.FullName -Algorithm MD5).Hash.ToLower()
        [Console]::Out.WriteLine("MD5 `$rel `$md5")
    }
}
"@
$scratch = Join-Path ([System.IO.Path]::GetTempPath()) "nmud_style"
if (-not (Test-Path $scratch)) { New-Item -ItemType Directory -Path $scratch | Out-Null }
$listFile = Join-Path $scratch "_list_pkg.ps1"
Set-Content -Path $listFile -Value $list -Encoding UTF8
$out = & (Get-NlpTool "remote.ps1") -Script $listFile -HostName $HostName -TimeoutSec 120 *>&1
Remove-Item $listFile -ErrorAction SilentlyContinue

$remoteMd5 = @{}
foreach ($line in ($out | Out-String).Split("`n")) {
    if ($line -match "MD5\s+(\S+)\s+([0-9a-f]{32})") {
        $remoteMd5[$Matches[1]] = $Matches[2]
    }
}
Write-Host "### the guest has $($remoteMd5.Count) files"

# 2) push the ones that differ
$push = Get-NlpTool "push2.ps1"
$pushed = 0
foreach ($f in Get-ChildItem $local -Recurse -File) {
    # The byte code cache is not source: it changes with every run and
    # belongs to the interpreter that made it.
    if ($f.Extension -eq ".pyc") { continue }
    if ($f.DirectoryName -match "__pycache__") { continue }
    $rel = $f.FullName.Substring($local.Length + 1).Replace('\', '/')
    $md5 = (Get-FileHash $f.FullName -Algorithm MD5).Hash.ToLower()
    if (-not $Force -and $remoteMd5.ContainsKey($rel) -and $remoteMd5[$rel] -eq $md5) {
        continue
    }
    $dest = Join-NlpRemote -Root $remoteDir -Parts @($rel.Replace('/', '\'))
    Write-Host "### pushing $rel"
    & $push -LocalFile $f.FullName -RemotePath $dest -HostName $HostName | Out-Null
    $pushed++
}

# 3) what the guest has that the local package does not have
foreach ($rel in $remoteMd5.Keys) {
    if (-not (Test-Path (Join-Path $local ($rel.Replace('/', '\'))))) {
        Write-Host "### only on the guest: $rel"
    }
}

if ($pushed -eq 0) {
    Write-Host "### the guest is up to date"
} else {
    Write-Host "### pushed $pushed file(s)"
}
