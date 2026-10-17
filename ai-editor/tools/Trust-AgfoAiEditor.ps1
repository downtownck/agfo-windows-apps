#requires -Version 5.1
<#
.SYNOPSIS
  Marks AGFO AI Editor as trusted on this PC - but only genuine builds published on GitHub.

.DESCRIPTION
  1. Finds AGFO-AI-Editor.exe copies (installed folder, Downloads, update cache, or -Path).
  2. Downloads the official SHA-256 list of every "ai-editor-v*" release from
     github.com/downtownck/agfo-windows-apps and compares each file against it.
  3. Only files whose hash matches a published release are unblocked (the "downloaded from the
     internet" mark is removed). Anything else is reported and left untouched.
  4. Reports Smart App Control and Microsoft Defender status for the file.
  Optional (admin, asked for UAC): -AddDefenderExclusion adds a Defender exclusion for the
  exact verified EXE path only (not a folder, not a process name).

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\Trust-AgfoAiEditor.ps1
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\Trust-AgfoAiEditor.ps1 -AddDefenderExclusion -Launch
#>
[CmdletBinding()]
param(
    [string[]]$Path,
    [switch]$AddDefenderExclusion,
    [switch]$Launch
)
$ErrorActionPreference = 'Stop'
$Repo = 'downtownck/agfo-windows-apps'
$ExeName = 'AGFO-AI-Editor.exe'

function Say([string]$Text, [string]$Color = 'Gray') { Write-Host $Text -ForegroundColor $Color }
function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return (New-Object Security.Principal.WindowsPrincipal $id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

Say 'AGFO AI Editor - trust check' 'Cyan'

# ---------------------------------------------------------------- 1. candidate files
$candidates = New-Object System.Collections.Generic.List[string]
$installed = Join-Path $env:LOCALAPPDATA "Programs\AGFO-AI-Editor\$ExeName"
$candidates.Add($installed)
$downloads = Join-Path $env:USERPROFILE 'Downloads'
if (Test-Path -LiteralPath $downloads) {
    Get-ChildItem -LiteralPath $downloads -Filter 'AGFO-AI-Editor*.exe' -File -ErrorAction SilentlyContinue | ForEach-Object { $candidates.Add($_.FullName) }
}
$cache = Join-Path $env:LOCALAPPDATA 'AGFO-AI-Editor\updates'
if (Test-Path -LiteralPath $cache) {
    Get-ChildItem -LiteralPath $cache -Filter 'AGFO-AI-Editor-*.exe' -File -ErrorAction SilentlyContinue | ForEach-Object { $candidates.Add($_.FullName) }
}
foreach ($p in @($Path)) { if ($p) { $candidates.Add([IO.Path]::GetFullPath($p)) } }
$files = @($candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Sort-Object -Unique)
if (-not $files.Count) {
    Say "No $ExeName found. Use -Path to point at the file." 'Yellow'
    exit 2
}

# ---------------------------------------------------------------- 2. official hashes from GitHub
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch { }
$headers = @{ 'User-Agent' = 'AGFO-Trust-Script'; 'Accept' = 'application/vnd.github+json' }
Say 'Reading published releases from GitHub...'
try {
    $releases = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases?per_page=100" -Headers $headers -TimeoutSec 30
} catch {
    Say ('Could not reach GitHub: ' + $_.Exception.Message) 'Red'
    Say 'Nothing was changed. Check the internet connection and run again.' 'Yellow'
    exit 3
}
$official = @{}
foreach ($r in @($releases)) {
    if ($r.draft -or -not ($r.tag_name -like 'ai-editor-v*')) { continue }
    $version = $r.tag_name -replace '^ai-editor-v', ''
    $asset = @($r.assets) | Where-Object { $_.name -eq $ExeName } | Select-Object -First 1
    if (-not $asset) { continue }
    $sha = ''
    if ($asset.digest -and ([string]$asset.digest).StartsWith('sha256:')) { $sha = ([string]$asset.digest).Substring(7).ToLowerInvariant() }
    if (-not $sha) {
        $sums = @($r.assets) | Where-Object { $_.name -eq 'SHA256SUMS.txt' } | Select-Object -First 1
        if ($sums) {
            try {
                $text = Invoke-RestMethod -Uri $sums.browser_download_url -Headers @{ 'User-Agent' = 'AGFO-Trust-Script' } -TimeoutSec 30
                foreach ($line in ([string]$text -split "`n")) {
                    if ($line -match '^\s*([0-9a-fA-F]{64})\s+\*?(\S+)\s*$' -and $Matches[2] -eq $ExeName) { $sha = $Matches[1].ToLowerInvariant() }
                }
            } catch { }
        }
    }
    if ($sha) { $official[$sha] = $version }
}
if (-not $official.Count) {
    Say 'No published AGFO AI Editor build with a SHA-256 digest was found on GitHub. Nothing was changed.' 'Red'
    exit 4
}
Say ('Published builds known: ' + (($official.Values | Sort-Object -Unique) -join ', '))

# ---------------------------------------------------------------- 3. verify + unblock
$trusted = New-Object System.Collections.Generic.List[string]
foreach ($f in $files) {
    $hash = (Get-FileHash -LiteralPath $f -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($official.ContainsKey($hash)) {
        $hadMark = $false
        try { $hadMark = [bool](Get-Item -LiteralPath $f -Stream 'Zone.Identifier' -ErrorAction SilentlyContinue) } catch { }
        try { Unblock-File -LiteralPath $f }
        catch { try { Remove-Item -LiteralPath $f -Stream 'Zone.Identifier' -ErrorAction SilentlyContinue } catch { } }
        $state = 'already unblocked'
        if ($hadMark) { $state = 'internet mark removed' }
        Say ("OK      v{0}  {1}  ({2})" -f $official[$hash], $f, $state) 'Green'
        $trusted.Add($f)
    } else {
        Say ("SKIPPED {0}`n        SHA-256 {1} does not match any published release - not touched." -f $f, $hash) 'Yellow'
    }
}

# ---------------------------------------------------------------- 4. Smart App Control / Defender report
try {
    $sac = (Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy' -Name 'VerifiedAndReputablePolicyState' -ErrorAction Stop).VerifiedAndReputablePolicyState
    switch ($sac) {
        1 { Say 'Smart App Control: ON. It blocks unsigned apps and cannot be bypassed for a single file.' 'Yellow'
            Say '  Until the EXE is code-signed, the only option is: Windows Security > App & browser control > Smart App Control > Off.' 'Yellow' }
        2 { Say 'Smart App Control: evaluation mode (may start blocking unsigned apps).' 'Yellow' }
        default { Say 'Smart App Control: off.' }
    }
} catch { Say 'Smart App Control: not present on this Windows version.' }

$defenderHit = $false
if (Get-Command Get-MpThreatDetection -ErrorAction SilentlyContinue) {
    try {
        $hits = @(Get-MpThreatDetection -ErrorAction SilentlyContinue | Where-Object { ($_.Resources -join ' ') -match 'AGFO-AI-Editor' })
        if ($hits.Count) {
            $defenderHit = $true
            $names = @($hits | ForEach-Object { (Get-MpThreat -ThreatID $_.ThreatID -ErrorAction SilentlyContinue).ThreatName } | Where-Object { $_ } | Sort-Object -Unique)
            Say ('Microsoft Defender flagged AGFO AI Editor: ' + ($names -join ', ')) 'Yellow'
            Say '  This is a common false positive for unsigned Python (PyInstaller) apps.' 'Yellow'
            Say '  If it was quarantined: Windows Security > Virus & threat protection > Protection history > select it > Actions > Restore / Allow.' 'Yellow'
        }
    } catch { }
}

if ($AddDefenderExclusion -and $trusted.Count) {
    if (-not (Test-Admin)) {
        Say 'Administrator rights are needed for the Defender exclusion; asking Windows (UAC)...' 'Cyan'
        $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $PSCommandPath + '"'), '-AddDefenderExclusion')
        foreach ($t in $trusted) { $argList += @('-Path', ('"' + $t + '"')) }
        Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList $argList -Verb RunAs -Wait
    } else {
        foreach ($t in $trusted) {
            Add-MpPreference -ExclusionPath $t
            Say ('Defender exclusion added for this exact file: ' + $t) 'Green'
        }
    }
} elseif ($defenderHit -and -not $AddDefenderExclusion) {
    Say '  Or run this script again with -AddDefenderExclusion (only the verified EXE file is excluded).' 'Yellow'
}

Say ''
Say ('Done. Verified and unblocked: {0} file(s).' -f $trusted.Count) 'Cyan'
if ($Launch -and (Test-Path -LiteralPath $installed) -and ($trusted -contains $installed)) {
    Get-ChildItem Env: | Where-Object { $_.Name -like '_PYI_*' -or $_.Name -like '_MEIPASS*' } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
    Start-Process -FilePath $installed
}
if (-not $trusted.Count) { exit 1 }
