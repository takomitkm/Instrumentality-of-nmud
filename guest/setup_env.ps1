# Check this school machine and install what the generator is missing.
#
# This script runs ON the guest (the local side pushes it there):
#
#   pwsh -File setup_env.ps1 -Root <the project folder on the guest>
#
# What it looks at:
#   * the virtual environment (.venv) and its python
#   * jieba, the segmenter the generator needs
#   * the nmud_style package and the data files inside it
#   * a self test: restyle one sentence and look at the result
#
# Nothing outside the project folder is touched.

param(
    # the project folder on the guest: the one that holds tools\ and out\
    [Parameter(Mandatory = $true)]
    [string]$Root
)

$ErrorActionPreference = "Continue"

function Say([string]$m) { [Console]::Out.WriteLine($m) }

$venv = Join-Path $Root ".venv"
$python = Join-Path $venv "Scripts\python.exe"
$tools = Join-Path $Root "tools"
$pkg = Join-Path $tools "nmud_style"

Say "=== nmud-style environment check ==="
Say "machine : $env:COMPUTERNAME"
Say "root    : $Root"

# 1) the virtual environment
if (-not (Test-Path $python)) {
    Say "need    : the virtual environment ($python) is MISSING"
    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $cmd) { $cmd = Get-Command py.exe -ErrorAction SilentlyContinue }
    if (-not $cmd) {
        Say "result  : no python on this machine, install python 3.9+ first"
        exit 1
    }
    Say "         creating it with $($cmd.Source)"
    & $cmd.Source -m venv $venv
    if (-not (Test-Path $python)) {
        Say "result  : the virtual environment could not be created"
        exit 1
    }
} else {
    Say "need    : the virtual environment  ok"
}

Say ("python  : " + ((& $python -c "import sys; print(sys.version.split()[0])") | Out-String).Trim())

# 2) the packages the generator needs
$missing = @()
& $python -c "import jieba" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { $missing += "jieba" }
if ($missing.Count -eq 0) {
    Say "need    : jieba  ok"
} else {
    Say "need    : jieba  MISSING"
    Say "         installing: " + ($missing -join " ")
    & $python -m pip install --disable-pip-version-check @missing
    & $python -c "import jieba" 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Say "result  : jieba could not be installed"
        Say "         (behind a proxy? try: $python -m pip install jieba --proxy http://127.0.0.1:7897)"
        exit 1
    }
    Say "need    : jieba  installed"
}

# 3) the package and its data
$need = @{
    "the package"      = (Join-Path $pkg "engine.py")
    "the cli"          = (Join-Path $pkg "cli.py")
    "the corpus"       = (Join-Path $pkg "data\nmud.txt")
    "the fitted params" = (Join-Path $pkg "data\nmud_style_params.json")
}
$bad = 0
foreach ($k in $need.Keys) {
    if (Test-Path $need[$k]) {
        Say "need    : $k  ok"
    } else {
        Say "need    : $k  MISSING ($($need[$k]))"
        $bad++
    }
}
if ($bad -gt 0) {
    Say "result  : run the sync first (the package comes from this repo)"
    exit 1
}

# 4) the self test
# The guest reads a pushed .ps1 as ANSI, so nothing in here may be Chinese.
# The test sentence travels as base64 and is decoded as UTF-8.
$tmp = Join-Path $Root "tmp"
if (-not (Test-Path $tmp)) { New-Item -ItemType Directory -Path $tmp -Force | Out-Null }
$in = Join-Path $tmp "_selftest_in.txt"
$out = Join-Path $tmp "_selftest_out.txt"
$utf8 = New-Object System.Text.UTF8Encoding $false
$b64 = "5LuK5aSp5Lmw5LqG5Liq5paw546p5YW377yM6JOd6Imy55qE77yM5Lya5Y+R5YWJ44CC"
[System.IO.File]::WriteAllBytes($in, [Convert]::FromBase64String($b64))
Push-Location $tools
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
& $python -m nmud_style --in $in --out $out --quiet 2>&1 | ForEach-Object { Say ([string]$_) }
$rc = $LASTEXITCODE
Pop-Location

if ($rc -eq 0 -and (Test-Path $out)) {
    $text = [System.IO.File]::ReadAllText($out, [System.Text.Encoding]::UTF8)
    # Only ascii goes back over ssh: the local side reads the file itself,
    # and a ssh transcript decoded in the local code page would turn the
    # Chinese into noise.
    $lines = 0
    foreach ($line in $text.Split("`n")) { if ($line.Trim() -ne "") { $lines++ } }
    Say "result  : the self test wrote $lines lines, $($text.Length) chars"
    Say "result  : the text is in $out"
    Say "result  : ready, the guest can restyle text"
    exit 0
}
Say "result  : the self test failed"
Remove-Item $in -Force -ErrorAction SilentlyContinue
exit 1
