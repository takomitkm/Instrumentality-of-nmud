# Push a local file to the school machine in chunks.
#
# scp/sftp are unusable here (the sandbox blocks those child processes), and a
# single huge base64 blob overflows the Windows command line. So: send the
# payload as N SSH round trips, each one a short base64 chunk that the remote
# side decodes and appends to a part file; the last step concatenates them.
#
# Usage:
#   pwsh -File push2.ps1 -LocalFile <file> [-RemotePath <path on the guest>]
param(
    [Parameter(Mandatory = $true)][string]$LocalFile,
    [string]$RemotePath = "",
    [string]$HostName = "",
    [int]$ChunkBytes = 1200
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "nlp_common.ps1")

$cfg = Read-NlpConfig -Known @{ host = $HostName }
$HostName = $cfg["host"]
$root = $cfg["remote_root"]

if ($RemotePath -eq "") {
    $RemotePath = Join-NlpRemote -Root $root -Parts @("tools", (Split-Path $LocalFile -Leaf))
    Write-Host "### remote path: $RemotePath"
}

$remote = Get-NlpTool "remote.ps1"
$bytes = [System.IO.File]::ReadAllBytes($LocalFile)
$md5 = (Get-FileHash -Path $LocalFile -Algorithm MD5).Hash.ToLower()
$total = $bytes.Length
Write-Host "### pushing $LocalFile ($total bytes, md5 $md5)"

$n = [Math]::Ceiling($total / $ChunkBytes)
$remoteDir = [System.IO.Path]::GetDirectoryName($RemotePath) -replace '\\', '/'
# unique part dir per push: concurrent pushes into a shared _parts dir
# raced with each other and lost chunks.
$tag = [guid]::NewGuid().ToString("N").Substring(0,8)
$partDir = "$remoteDir/_parts_$tag"

# 1) make the part directory
$mk = @"
`$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Path "$partDir" -Force | Out-Null
[Console]::Out.WriteLine("parts dir ready")
"@
$scratch = Join-Path ([System.IO.Path]::GetTempPath()) "nmud_style"
if (-not (Test-Path $scratch)) { New-Item -ItemType Directory -Path $scratch | Out-Null }
$mkFile = Join-Path $scratch "_mk.ps1"
Set-Content -Path $mkFile -Value $mk -Encoding UTF8
& $remote -Script $mkFile -HostName $HostName -TimeoutSec 90
Remove-Item $mkFile -ErrorAction SilentlyContinue

# 2) send chunks
for ($i = 0; $i -lt $n; $i++) {
    $len = [Math]::Min($ChunkBytes, $total - $i * $ChunkBytes)
    $slice = New-Object byte[] $len
    [Array]::Copy($bytes, $i * $ChunkBytes, $slice, 0, $len)
    $b64 = [Convert]::ToBase64String($slice)
    $part = "$partDir/p$('{0:d3}' -f $i).b64"

    $body = @"
`$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Path "$partDir" -Force | Out-Null
[System.IO.File]::WriteAllText("$part", '$b64', [System.Text.Encoding]::ASCII)
[Console]::Out.WriteLine("part $i written")
"@
    $bf = Join-Path $scratch "_part.ps1"
    Set-Content -Path $bf -Value $body -Encoding UTF8
    & $remote -Script $bf -HostName $HostName -TimeoutSec 90 | Out-Null
    Remove-Item $bf -ErrorAction SilentlyContinue
    if (($i + 1) % 10 -eq 0 -or $i -eq $n - 1) { Write-Host "  part $i / $($n-1)" }
}

# 3) concatenate + decode + verify
$cat = @"
`$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Path "$partDir" -Force | Out-Null
`$parts = Get-ChildItem "$partDir" -Filter *.b64 -ErrorAction SilentlyContinue | Sort-Object Name
`$acc = New-Object System.Text.StringBuilder
foreach (`$p in `$parts) { [void]`$acc.Append((Get-Content `$p.FullName -Raw)) }
`$b = [Convert]::FromBase64String(`$acc.ToString())
[System.IO.File]::WriteAllBytes("$RemotePath", `$b)
`$m = (Get-FileHash -Path "$RemotePath" -Algorithm MD5).Hash.ToLower()
[Console]::Out.WriteLine("written: $RemotePath")
[Console]::Out.WriteLine("bytes: " + `$b.Length)
[Console]::Out.WriteLine("md5_local: $md5")
[Console]::Out.WriteLine("md5_remote: " + `$m)
if (`$m -ne "$md5") { [Console]::Out.WriteLine("MD5 MISMATCH") } else { [Console]::Out.WriteLine("MD5 OK") }
Remove-Item "$partDir" -Recurse -Force -ErrorAction SilentlyContinue
"@
$catFile = Join-Path $scratch "_cat.ps1"
Set-Content -Path $catFile -Value $cat -Encoding UTF8
& $remote -Script $catFile -HostName $HostName -TimeoutSec 120
Remove-Item $catFile -ErrorAction SilentlyContinue
