# One click: take the clipboard, lay it out in the nmud style on the school
# machine, and put the result back into the clipboard.
#
#   style-clipboard.ps1 [-HostName <name>] [-TimeoutSec <seconds>]
#
# The text is sent to the guest as a file, the guest runs the nmud_style
# package on it, and the styled text comes back. An empty clipboard is
# left alone.
#
# Exit codes: 0 = clipboard updated, 1 = failed, 2 = clipboard was empty.
#
# Every run uses its own file names on the guest. A file left over from an
# earlier run must never be published as if it were this run's result.

param(
    [string]$HostName = "",
    [int]$TimeoutSec = 300
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "nlp_common.ps1")

$cfg = Read-NlpConfig -Known @{ host = $HostName }
$HostName = $cfg["host"]
$root = $cfg["remote_root"]
$tmp = Join-NlpRemote -Root $root -Parts @("tmp")
$scratch = Join-Path ([System.IO.Path]::GetTempPath()) "nmud_style"
if (-not (Test-Path $scratch)) { New-Item -ItemType Directory -Path $scratch | Out-Null }
$utf8 = New-Object System.Text.UTF8Encoding $false

# 1) the clipboard in
$text = ""
try { $text = Get-Clipboard -Raw } catch { $text = "" }
if ($null -eq $text) { $text = "" }
if ($text.Trim() -eq "") {
    Write-Host "clipboard is empty - nothing to do"
    exit 2
}

$tag = "{0}_{1}" -f (Get-Date -Format "yyyyMMdd_HHmmss"), (Get-Random -Maximum 9999)
$remoteIn = Join-NlpRemote -Root $tmp -Parts @("clip_in_$tag.txt")
$remoteOut = Join-NlpRemote -Root $tmp -Parts @("clip_out_$tag.txt")
$localIn = Join-Path $scratch "clip_in_$tag.txt"
$localOut = Join-Path $scratch "clip_out_$tag.txt"
[System.IO.File]::WriteAllText($localIn, $text, $utf8)
Write-Host ("### clipboard: {0} chars" -f $text.Length)

# 2) to the guest, run the tool, and back
$remoteHelper = Get-NlpTool "remote.ps1"
try {
    & (Get-NlpTool "push2.ps1") -LocalFile $localIn -RemotePath $remoteIn -HostName $HostName | Out-Null
    # *>&1 also captures the information stream: the helpers report with
    # Write-Host, and that is the text the checks below look at
    $log = & (Get-NlpTool "run_pkg.ps1") -HostName $HostName -TimeoutSec $TimeoutSec `
                   -PyArgs @("--in", $remoteIn, "--out", $remoteOut, "--quiet") *>&1
    $logText = ($log | Out-String)

    # The guest has to have said it wrote the file, and exited 0
    if ($logText -notmatch [regex]::Escape("wrote $remoteOut")) {
        Write-Host "FAILED: the guest did not produce $remoteOut"
        Write-Host $logText
        exit 1
    }
    if ($logText -notmatch "=== exit code: 0 ===") {
        Write-Host "FAILED: the guest run did not finish cleanly"
        Write-Host $logText
        exit 1
    }

    & (Get-NlpTool "pull.ps1") -RemoteFile $remoteOut -LocalFile $localOut | Out-Null
} catch {
    Write-Host "FAILED: $($_.Exception.Message)"
    if ($logText) { Write-Host $logText }
    exit 1
} finally {
    # The guest's scratch files go away either way
    $clean = @"
`$ErrorActionPreference = "SilentlyContinue"
Remove-Item "$remoteIn" -Force -ErrorAction SilentlyContinue
Remove-Item "$remoteOut" -Force -ErrorAction SilentlyContinue
"@
    $cleanFile = Join-Path $scratch "_clip_clean.ps1"
    # ascii: the guest reads a pushed .ps1 as ANSI, and the BOM a 5.1
    # UTF-8 file would carry is one more thing to trip over
    Set-Content -Path $cleanFile -Value $clean -Encoding ascii
    & $remoteHelper -Script $cleanFile -HostName $HostName -TimeoutSec 60 | Out-Null
    Remove-Item $cleanFile, $localIn -ErrorAction SilentlyContinue
}

if (-not (Test-Path $localOut)) {
    Write-Host "FAILED: the result never came back"
    exit 1
}

# 3) the clipboard out
$result = [System.IO.File]::ReadAllText($localOut, $utf8)
if ($result.Trim() -eq "") {
    Write-Host "FAILED: the guest returned an empty result"
    exit 1
}
Set-Clipboard -Value $result
Remove-Item $localOut -ErrorAction SilentlyContinue
Write-Host ("### clipboard updated: {0} chars" -f $result.Length)
Write-Host $result
exit 0
