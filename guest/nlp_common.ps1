# Shared bits for the nmud probe scripts: the config file, interactive
# prompts, and locating sibling scripts without hardcoded paths.
#
# The config file lives next to these scripts (remote.cfg). It is created on
# first use from the answers, so no absolute path is written down in code.
#   host         - ssh alias or host name of the school machine
#   remote_root  - the project folder on that machine (holds tools\ and out\)

$script:NLPCfgPath = Join-Path $PSScriptRoot "remote.cfg"

if ($PSVersionTable.PSVersion.Major -lt 7) {
    # Windows PowerShell 5.1 autoloads its cmdlets from PSModulePath. An
    # environment that also has PowerShell 7 puts 7.x module folders on
    # that path, and 5.1 then loads the wrong copy and finds no cmdlet at
    # all ("Get-FileHash is not recognized"). Keep only the 5.1 folders.
    $folders = @(
        "$env:USERPROFILE\Documents\WindowsPowerShell\Modules",
        "$env:ProgramFiles\WindowsPowerShell\Modules",
        "$env:SystemRoot\system32\WindowsPowerShell\v1.0\Modules"
    ) | Where-Object { $_ -and (Test-Path $_) }
    if ($folders.Count -gt 0) { $env:PSModulePath = $folders -join ";" }
}

function Read-NlpConfig {
    # Returns the config as a hashtable. Keys already supplied in $Known
    # are not asked for again.
    param([hashtable]$Known = @{})

    $cfg = @{}
    if (Test-Path $script:NLPCfgPath) {
        foreach ($line in Get-Content $script:NLPCfgPath -Encoding UTF8) {
            $t = $line.Trim()
            if ($t -eq "" -or $t.StartsWith("#")) { continue }
            $i = $t.IndexOf("=")
            if ($i -lt 1) { continue }
            $cfg[$t.Substring(0, $i).Trim()] = $t.Substring($i + 1).Trim()
        }
    }

    $dirty = $false
    $prompts = [ordered]@{
        host        = "school machine: ssh alias or host name"
        remote_root = "project folder on the school machine (holds tools\ and out\)"
    }
    foreach ($k in $prompts.Keys) {
        if ($Known.ContainsKey($k) -and $Known[$k] -ne "") {
            $cfg[$k] = $Known[$k]
            continue
        }
        if ($cfg.ContainsKey($k) -and $cfg[$k] -ne "") { continue }
        $ans = Read-Host $prompts[$k]
        if ($ans -eq "") { $ans = $k }
        $cfg[$k] = $ans
        $dirty = $true
    }

    if ($dirty) {
        $text = ($cfg.GetEnumerator() | Sort-Object Name |
                 ForEach-Object { "$($_.Name)=$($_.Value)" }) -join "`n"
        Set-Content -Path $script:NLPCfgPath -Value $text -Encoding UTF8
        Write-Host "### wrote $script:NLPCfgPath"
    }
    return $cfg
}

function Get-NlpTool {
    # A sibling script of these helpers.
    param([Parameter(Mandatory = $true)][string]$Name)
    $p = Join-Path $PSScriptRoot $Name
    if (-not (Test-Path $p)) { throw "missing helper: $p" }
    return $p
}

function Get-NlpSsh {
    # The ssh client: found on PATH, else the system copy.
    $c = Get-Command ssh.exe -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $fallback = Join-Path $env:SystemRoot "System32\OpenSSH\ssh.exe"
    if (Test-Path $fallback) { return $fallback }
    throw "ssh.exe not found on PATH and not in $fallback"
}

function Get-NlpKnownHosts {
    # The host key file, unless the config says otherwise.
    $p = Join-Path $env:USERPROFILE ".ssh\known_hosts"
    return $p
}

function Join-NlpRemote {
    # Join pieces of a path on the school machine. The plain Join-Path
    # would need the remote drive to exist on this machine, which it does
    # not.
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string[]]$Parts
    )
    $p = $Root.TrimEnd('\', '/')
    foreach ($x in $Parts) { $p = $p + "\" + $x.TrimStart('\', '/') }
    return $p
}

function Get-NlpRemotePath {
    # A path on the school machine, under the configured root.
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Relative
    )
    return (Join-NlpRemote -Root $Root -Parts @($Relative))
}
