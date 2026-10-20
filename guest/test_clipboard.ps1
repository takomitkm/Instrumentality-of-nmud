# Round trip test of the one click flow: the clipboard in, the nmud style
# out, and the original clipboard back where it was.
#
#   pwsh -File test_clipboard.ps1 [-HostName <name>]
#
# The clipboard of the person running this is saved first and restored at
# the end, so the test costs nothing but the two seconds it runs.
#
# No Chinese in this file: Windows PowerShell reads a .ps1 as ANSI, and the
# sample text travels as base64 instead.
param(
    [string]$HostName = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "nlp_common.ps1")

$cfg = Read-NlpConfig -Known @{ host = $HostName }
$HostName = $cfg["host"]

$before = Get-Clipboard -Raw
Write-Host "### saved the clipboard ($($before.Length) chars)"

$sampleB64 = "5LuK5aSp5Lmw5LqG5Liq5paw546p5YW377yM6JOd6Imy55qE77yM5Lya5Y+R5YWJ77yM5YyA6YCf55qEc2hha2Ugc2hha2XjgIIK56ys5LqM5q615Lmf5pyJ5qCH54K577yM5q+U5aaC6L+Z5qC377yf"
$sample = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($sampleB64))
try {
    Set-Clipboard -Value $sample
    Write-Host "### running the flow"
    & (Get-NlpTool "style-clipboard.ps1") -HostName $HostName
    $rc = $LASTEXITCODE
    Write-Host "### exit code: $rc"
    Write-Host "### the clipboard now holds:"
    Get-Clipboard -Raw
} finally {
    Set-Clipboard -Value $before
    Write-Host "### the original clipboard is back"
}

if ($rc -ne 0) { exit $rc }
exit 0
