# AGFO BackupSync v2.0 - shared engine / profile functions.
# Windows PowerShell 5.1 compatible. No dependency for Robocopy mode.
$script:AgfoVersion = '2.3.1'
$script:AgfoRoot = Join-Path $env:LOCALAPPDATA 'AGFO-BackupSync'
$script:AgfoAppDir = Join-Path $script:AgfoRoot 'app'
$script:AgfoProfiles = Join-Path $script:AgfoRoot 'profiles'
$script:AgfoLogs = Join-Path $script:AgfoRoot 'logs'
$script:AgfoLast = Join-Path $script:AgfoRoot 'last-profile.txt'
$script:AgfoVersionDir = '.agfo-versions'

function Initialize-Agfo {
    foreach ($folder in @($script:AgfoRoot, $script:AgfoAppDir, $script:AgfoProfiles, $script:AgfoLogs)) {
        if (-not [System.IO.Directory]::Exists($folder)) {
            [void][System.IO.Directory]::CreateDirectory($folder)
        }
    }
}

function New-AgfoProfile {
    return [pscustomobject][ordered]@{
        schema = 2
        profileId = [guid]::NewGuid().ToString('N')
        profileName = 'Synology-UGREEN'
        source = ''
        target = ''
        mode = 'incremental'
        copyRule = 'update'
        threads = 8
        retries = 2
        waitSeconds = 5
        maxDelete = 100
        excludeFiles = '*.tmp;Thumbs.db;desktop.ini'
        excludeDirs = 'WindowsApps;System Volume Information;$RECYCLE.BIN;@eaDir;#recycle;.agfo-versions'
        preventSleep = $true
        verboseLog = $false
        mirrorConsent = $false
        scheduleTime = '02:00'
        scheduleKind = 'daily'
        scheduleDay = 'Monday'
        scheduleWake = $true
        scheduleBattery = $false
        scheduleRetry = $true
        importedFrom = ''
    }
}

function Resolve-AgfoProfile([object]$Raw) {
    $profile = New-AgfoProfile
    if ($null -eq $Raw) { return $profile }
    foreach ($property in $profile.PSObject.Properties) {
        $oldProperty = $Raw.PSObject.Properties[$property.Name]
        if ($null -ne $oldProperty -and $null -ne $oldProperty.Value) {
            $profile.($property.Name) = $oldProperty.Value
        }
    }
    if ([string]::IsNullOrWhiteSpace([string]$profile.profileId)) {
        $profile.profileId = [guid]::NewGuid().ToString('N')
    }
    return $profile
}

function Read-AgfoJson([string]$Path) {
    $json = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
    return ($json | ConvertFrom-Json)
}

function Write-AgfoJson([string]$Path, [object]$Value) {
    $folder = [System.IO.Path]::GetDirectoryName($Path)
    if (-not [System.IO.Directory]::Exists($folder)) {
        [void][System.IO.Directory]::CreateDirectory($folder)
    }
    $tmp = $Path + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
    $utf8 = [System.Text.UTF8Encoding]::new($false)
    $json = ConvertTo-Json -InputObject $Value -Depth 12
    try {
        [System.IO.File]::WriteAllText($tmp, $json, $utf8)
        if ([System.IO.File]::Exists($Path)) {
            [System.IO.File]::Replace($tmp, $Path, $null)
        } else {
            [System.IO.File]::Move($tmp, $Path)
        }
    } finally {
        if ([System.IO.File]::Exists($tmp)) { [System.IO.File]::Delete($tmp) }
    }
}

function Get-AgfoProfilePath([string]$Id) {
    if ($Id -notmatch '^[a-fA-F0-9]{32}$') { throw 'Gecersiz profil kimligi.' }
    return (Join-Path $script:AgfoProfiles ($Id + '.json'))
}

function Save-AgfoProfile([object]$Profile) {
    $p = Resolve-AgfoProfile $Profile
    if ([string]::IsNullOrWhiteSpace([string]$p.profileName)) { throw 'Profil adi bos olamaz.' }
    if (@('incremental', 'versioned', 'mirror') -cnotcontains [string]$p.mode) { throw 'Gecersiz aktarim modu.' }
    if (@('update', 'missing', 'newer') -cnotcontains [string]$p.copyRule) { throw 'Gecersiz kopyalama kurali.' }
    $p.schema = 2
    $path = Get-AgfoProfilePath ([string]$p.profileId)
    Write-AgfoJson $path $p
    return $path
}

function Read-AgfoProfile([string]$Path) {
    if (-not [System.IO.File]::Exists($Path)) { throw "Profil bulunamadi: $Path" }
    $p = Resolve-AgfoProfile (Read-AgfoJson $Path)
    if (@('incremental', 'versioned', 'mirror') -cnotcontains [string]$p.mode) { throw 'Profil modu taninmiyor.' }
    if ([string]$p.profileId -notmatch '^[a-fA-F0-9]{32}$') { throw 'Bozuk profil kimligi.' }
    return $p
}

function Get-AgfoProfiles {
    Initialize-Agfo
    $output = @()
    foreach ($item in @(Get-ChildItem -LiteralPath $script:AgfoProfiles -Filter '*.json' -File -ErrorAction SilentlyContinue)) {
        try {
            $p = Read-AgfoProfile $item.FullName
            $output += [pscustomobject]@{ Name = [string]$p.profileName; Path = $item.FullName; Id = [string]$p.profileId }
        } catch { }
    }
    return @($output | Sort-Object Name)
}

function Import-AgfoV1Profiles {
    Initialize-Agfo
    $legacy = Join-Path $env:LOCALAPPDATA 'AGFO-NAS-Copy\profiles'
    if (-not [System.IO.Directory]::Exists($legacy)) { return 0 }
    $count = 0
    $imports = @((Get-AgfoProfiles) | ForEach-Object { $_.Path })
    foreach ($item in @(Get-ChildItem -LiteralPath $legacy -Filter '*.json' -File -ErrorAction SilentlyContinue)) {
        try {
            # Never overwrite imported or v2 profiles on repeated imports.
            $already = $false
            foreach ($file in $imports) {
                try { if ((Read-AgfoProfile $file).importedFrom -eq $item.FullName) { $already = $true; break } }
                catch { }
            }
            if ($already) { continue }
            $old = Read-AgfoJson $item.FullName
            $p = New-AgfoProfile
            $p.profileName = ([string]$old.profileName + ' (v1 aktarildi)').Trim()
            $p.source = [string]$old.source
            $p.target = [string]$old.target
            $p.copyRule = switch ([string]$old.mode) { 'missing' { 'missing' } 'newer' { 'newer' } default { 'update' } }
            $p.threads = [int]$old.threads
            $p.retries = [int]$old.retries
            $p.waitSeconds = [int]$old.waitSeconds
            $p.verboseLog = [bool]$old.verboseLog
            $p.preventSleep = [bool]$old.preventSleep
            if (-not [string]::IsNullOrWhiteSpace([string]$old.excludeFiles)) { $p.excludeFiles = [string]$old.excludeFiles }
            $defaultDirs = @(Split-AgfoPatterns $p.excludeDirs)
            $oldDirs = @(Split-AgfoPatterns ([string]$old.excludeDirs))
            $p.excludeDirs = ((@($defaultDirs) + @($oldDirs) | Select-Object -Unique) -join ';')
            $p.importedFrom = $item.FullName
            # v1 jobs are imported as NON-DELETE incremental copies, not as mirror jobs.
            $imports += (Save-AgfoProfile $p)
            $count++
        } catch { }
    }
    return $count
}

function Split-AgfoPatterns([string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) { return @() }
    return @([regex]::Split($Value, '[;\r\n]+') | ForEach-Object { $_.Trim() } | Where-Object { $_.Length -gt 0 })
}

function Normalize-AgfoPath([string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) { throw 'Kaynak veya hedef yolu bos.' }
    $p = $Value.Trim().Trim('"').Trim()
    if ($p -notmatch '^(?:[A-Za-z]:\\|\\\\[^\\]+\\[^\\]+(?:\\|$))') {
        throw "Yalnizca mutlak disk veya UNC yolu kabul edilir: $p"
    }
    if ($p -match '^[A-Za-z]:\\$') { return $p }
    return $p.TrimEnd([char]92)
}

function Test-AgfoWithin([string]$Path, [string]$Parent) {
    $a = (Normalize-AgfoPath $Path).TrimEnd([char]92)
    $b = (Normalize-AgfoPath $Parent).TrimEnd([char]92)
    if ([string]::Equals($a, $b, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    return $a.StartsWith(($b + '\'), [System.StringComparison]::OrdinalIgnoreCase)
}

function Test-AgfoRoot([string]$Path) {
    $p = Normalize-AgfoPath $Path
    return (($p -match '^[A-Za-z]:\\$') -or ($p -match '^\\\\[^\\]+\\[^\\]+$'))
}

function Get-AgfoPathRoot([string]$Path) {
    $p = Normalize-AgfoPath $Path
    if ($p -match '^(\\\\[^\\]+\\[^\\]+)') { return $Matches[1] }
    if ($p -match '^([A-Za-z]:\\)') { return $Matches[1] }
    throw "Yol koku hesaplanamadi: $Path"
}

function Validate-AgfoPaths([object]$Profile, [bool]$CheckOnline = $true, [bool]$RequireConsent = $true, [bool]$CheckOtherJobs = $true) {
    $src = Normalize-AgfoPath ([string]$Profile.source)
    $dst = Normalize-AgfoPath ([string]$Profile.target)
    if ((Test-AgfoWithin $dst $src) -or (Test-AgfoWithin $src $dst)) {
        throw 'Kaynak ve hedef ayni klasor veya birbirinin alt klasoru olamaz.'
    }
    if (([string]$Profile.mode -eq 'mirror') -and (Test-AgfoRoot $dst)) {
        throw 'Surumlu esitleme hedefi bir disk veya SMB paylasiminin kok dizini olamaz. Hedefte alt klasor kullanin.'
    }
    if (([string]$Profile.mode -eq 'mirror') -and $RequireConsent -and (-not [bool]$Profile.mirrorConsent)) {
        throw 'Surumlu esitleme icin acik onay kutusunu isaretleyin ve profili kaydedin.'
    }
    if ([string]$Profile.mode -eq 'mirror' -and $CheckOtherJobs) {
        # A mirror must never purge the destination of another profile.
        foreach ($other in @(Get-AgfoProfiles)) {
            if ([string]$other.Id -eq [string]$Profile.profileId) { continue }
            try {
                $otherP = Read-AgfoProfile ([string]$other.Path)
                if (-not [string]::IsNullOrWhiteSpace([string]$otherP.target)) {
                    $otherTarget = Normalize-AgfoPath ([string]$otherP.target)
                    if ((Test-AgfoWithin $dst $otherTarget) -or (Test-AgfoWithin $otherTarget $dst)) {
                        throw ('Bu esitleme hedefi baska profilin hedefiyle cakismaktadir: ' + [string]$otherP.profileName)
                    }
                }
            } catch {
                if ([string]$_.Exception.Message -like 'Bu esitleme hedefi*') { throw }
            }
        }
    }
    if ($CheckOnline) {
        if (-not (Test-Path -LiteralPath $src -PathType Container)) { throw "Kaynak klasore erisilemiyor: $src" }
        if (Test-Path -LiteralPath $dst -PathType Leaf) { throw 'Hedef bir klasor degil, dosya.' }
        $root = Get-AgfoPathRoot $dst
        if (-not (Test-Path -LiteralPath $root -PathType Container)) { throw "Hedef disk/paylasim erisilemiyor: $root" }
        if ([string]$Profile.mode -eq 'mirror') {
            # Fail closed for a temporarily empty or inaccessible source.
            $first = Get-ChildItem -LiteralPath $src -Force -ErrorAction Stop | Select-Object -First 1
            if ($null -eq $first) { throw 'Kaynak bos: otomatik esitleme hedefe dokunmadan engellendi.' }
        }
    }
    return [pscustomobject]@{ Source = $src; Target = $dst }
}

function Get-AgfoArchiveRoot([object]$Profile) {
    $target = Normalize-AgfoPath ([string]$Profile.target)
    return (Join-Path $target (Join-Path $script:AgfoVersionDir ([string]$Profile.profileId)))
}

function Quote-AgfoArg([string]$Value) {
    if ($Value.Length -eq 0) { return '""' }
    if ($Value -notmatch '[\s"]') { return $Value }
    $result = New-Object System.Text.StringBuilder
    [void]$result.Append('"')
    $slashes = 0
    foreach ($ch in $Value.ToCharArray()) {
        if ($ch -eq [char]92) { $slashes++; continue }
        if ($ch -eq [char]34) {
            if ($slashes) { [void]$result.Append(('\' * ($slashes * 2))) }
            [void]$result.Append('\"')
            $slashes = 0
            continue
        }
        if ($slashes) { [void]$result.Append(('\' * $slashes)); $slashes = 0 }
        [void]$result.Append($ch)
    }
    if ($slashes) { [void]$result.Append(('\' * ($slashes * 2))) }
    [void]$result.Append('"')
    return $result.ToString()
}

function Join-AgfoArgs([string[]]$Arguments) {
    return (($Arguments | ForEach-Object { Quote-AgfoArg ([string]$_) }) -join ' ')
}

function Find-AgfoExe([string]$Name) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd -and $cmd.Source) { return [string]$cmd.Source }
    if ($Name -ieq 'rclone.exe') {
        $candidates = @(
            (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\rclone.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\rclone\rclone.exe'),
            (Join-Path ${env:ProgramFiles} 'rclone\rclone.exe')
        )
        foreach ($candidate in $candidates) {
            if ($candidate -and [System.IO.File]::Exists($candidate)) { return $candidate }
        }
        $pkgDir = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
        if ([System.IO.Directory]::Exists($pkgDir)) {
            $found = Get-ChildItem -LiteralPath $pkgDir -Recurse -Filter 'rclone.exe' -File -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($found) { return $found.FullName }
        }
    }
    return ''
}

function New-AgfoEngineCommand([object]$Profile, [object]$Paths, [string]$LogPath, [string]$RunId, [bool]$Preview, [bool]$ForTest = $false) {
    $mode = [string]$Profile.mode
    $rule = [string]$Profile.copyRule
    $threads = [Math]::Max(1, [Math]::Min(32, [int]$Profile.threads))
    $retries = [Math]::Max(0, [Math]::Min(20, [int]$Profile.retries))
    $wait = [Math]::Max(0, [Math]::Min(120, [int]$Profile.waitSeconds))
    $files = @(Split-AgfoPatterns ([string]$Profile.excludeFiles))
    $dirs = @(Split-AgfoPatterns ([string]$Profile.excludeDirs))
    if ($mode -eq 'incremental') {
        $exe = if ($ForTest) { 'robocopy.exe' } else { Find-AgfoExe 'robocopy.exe' }
        if (-not $exe) { throw 'Robocopy bu Windows kurulumunda bulunamadi.' }
        $args = @($Paths.Source, $Paths.Target, '/E', '/Z', '/FFT', '/XJ',
            '/COPY:DAT', '/DCOPY:DA', '/XA:E', ('/MT:' + $threads),
            ('/R:' + $retries), ('/W:' + $wait), '/NP', '/BYTES', ('/UNILOG:' + $LogPath))
        if ($rule -eq 'missing') { $args += @('/XC', '/XN', '/XO') }
        if ($rule -eq 'newer') { $args += '/XO' }
        if ($Preview) { $args += '/L' }
        if ([bool]$Profile.verboseLog) { $args += @('/FP', '/TS', '/V') }
        if ($files.Count) { $args += '/XF'; $args += $files }
        if ($dirs.Count) { $args += '/XD'; $args += $dirs }
        return [pscustomobject]@{ Exe = $exe; Args = [string[]]$args; Encoding = 'Unicode'; Archive = '' }
    }
    if ($mode -cnotin @('versioned','mirror')) { throw 'Taninmayan aktarim modu.' }
    $exe = if ($ForTest) { 'rclone.exe' } else { Find-AgfoExe 'rclone.exe' }
    if (-not $exe) { throw 'rclone kurulu degil. Motorlar sekmesinden winget ile kurun.' }
    $archive = Join-Path (Get-AgfoArchiveRoot $Profile) $RunId
    $verb = if ($mode -eq 'mirror') { 'sync' } else { 'copy' }
    $args = @($verb, $Paths.Source, $Paths.Target, '--backup-dir', $archive,
        '--log-file', $LogPath, '--log-level', 'INFO', '--stats', '30s',
        '--stats-log-level', 'INFO', '--transfers', ([string][Math]::Min(16, $threads)),
        '--checkers', '8', '--retries', ([string][Math]::Max(1, $retries)),
        '--low-level-retries', '2', '--modify-window', '2s', '--skip-links',
        '--exclude', '/.agfo-versions/**', '--exclude', '/.agfo-versions/',
        '--exclude', '/.agfo-restores/**', '--exclude', '/.agfo-restores/')
    if ($rule -eq 'missing') { $args += '--ignore-existing' }
    if ($rule -eq 'newer') { $args += '--update' }
    # --ignore-existing + sync would prevent updating files, but can still archive target extras.
    # For mirror, enforce normal comparison to avoid misleading sync results.
    if ($mode -eq 'mirror') {
        if ($rule -ne 'update') { throw 'Surumlu esitlemede kopyalama kurali "eksik ve degisenler" olmalidir.' }
        $limit = [Math]::Max(1, [Math]::Min(100000, [int]$Profile.maxDelete))
        $args += @('--max-delete', [string]$limit)
    }
    if ($Preview) { $args += '--dry-run' }
    foreach ($f in $files) { $args += '--exclude'; $args += $f }
    foreach ($dir in $dirs) {
        $d = $dir.Trim('/').Trim('\')
        if ($d) {
            $args += '--exclude'; $args += ('**/' + $d + '/**')
            $args += '--exclude'; $args += ('/' + $d + '/**')
        }
    }
    return [pscustomobject]@{ Exe = $exe; Args = [string[]]$args; Encoding = 'UTF8'; Archive = $archive }
}

function New-AgfoRestoreCommand([object]$Profile, [string]$RunPath, [string]$RestoreTarget, [string]$LogPath, [bool]$Preview, [bool]$ForTest = $false) {
    $run = Normalize-AgfoPath $RunPath
    $dest = Normalize-AgfoPath $RestoreTarget
    $root = Get-AgfoArchiveRoot $Profile
    $parent = [System.IO.Path]::GetDirectoryName($run)
    if (-not [string]::Equals($parent, $root, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Yalnizca bu profilin arsivlenmis calistirma klasoru geri yuklenebilir.'
    }
    if (-not $ForTest -and -not (Test-Path -LiteralPath $run -PathType Container)) { throw 'Secilen arsiv klasoru bulunamadi.' }
    if ((Test-AgfoWithin $dest ([string]$Profile.source)) -or (Test-AgfoWithin $dest ([string]$Profile.target)) -or
        (Test-AgfoWithin ([string]$Profile.source) $dest) -or (Test-AgfoWithin ([string]$Profile.target) $dest)) {
        throw 'Geri yukleme hedefi canli kaynak veya yedek klasoru ile cakismamali.'
    }
    if (-not $ForTest) {
        if (Test-Path -LiteralPath $dest) { throw 'Geri yukleme hedefi yeni, henuz bulunmayan bir klasor olmalidir.' }
        if (-not (Test-Path -LiteralPath (Get-AgfoPathRoot $dest) -PathType Container)) { throw 'Geri yukleme hedef diski/paylasimi erisilemiyor.' }
    }
    $exe = if ($ForTest) { 'rclone.exe' } else { Find-AgfoExe 'rclone.exe' }
    if (-not $exe) { throw 'Geri yukleme icin rclone kurulmalidir.' }
    $args = @('copy', $run, $dest, '--log-file', $LogPath, '--log-level', 'INFO',
        '--stats', '30s', '--transfers', '4', '--checkers', '8', '--retries', '2',
        '--low-level-retries', '2', '--skip-links', '--ignore-existing')
    if ($Preview) { $args += '--dry-run' }
    return [pscustomobject]@{ Exe = $exe; Args = [string[]]$args; Encoding = 'UTF8'; Archive = $run }
}

function Acquire-AgfoLock([string]$Target) {
    $hashAlg = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Target.ToUpperInvariant())
        $hash = [System.BitConverter]::ToString($hashAlg.ComputeHash($bytes)).Replace('-', '').Substring(0, 28)
    } finally { $hashAlg.Dispose() }
    $lock = [System.Threading.Mutex]::new($false, ('Local\AGFO_BackupSync_' + $hash))
    try {
        $owns = $lock.WaitOne(0, $false)
        if (-not $owns) { $lock.Dispose(); throw 'Bu hedef icin baska bir AGFO aktarimi calisiyor.' }
    } catch [System.Threading.AbandonedMutexException] {
        # An aborted task handed the lock to this worker.
    }
    return $lock
}

function Set-AgfoPreventSleep([bool]$Enabled) {
    if (-not ('AgfoBackupPowerState' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class AgfoBackupPowerState {
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern uint SetThreadExecutionState(uint state);
}
'@ | Out-Null
    }
    if ($Enabled) { [void][AgfoBackupPowerState]::SetThreadExecutionState([uint32]2147483649) }
    else { [void][AgfoBackupPowerState]::SetThreadExecutionState([uint32]2147483648) }
}

function Invoke-AgfoJob([string]$ProfilePath, [bool]$Preview, [string]$RunPath, [string]$RestoreTarget, [string]$LogPath, [string]$StatusPath, [string]$CancelPath) {
    Initialize-Agfo
    $now = Get-Date
    $runId = $now.ToString('yyyyMMdd_HHmmss_fff') + '_' + [guid]::NewGuid().ToString('N').Substring(0, 6)
    if (-not $LogPath) { $LogPath = Join-Path $script:AgfoLogs ($runId + '.log') }
    if (-not $StatusPath) { $StatusPath = Join-Path $script:AgfoLogs ($runId + '.result.json') }
    if (-not $CancelPath) { $CancelPath = $StatusPath + '.cancel' }
    $result = [ordered]@{
        version = $script:AgfoVersion; id = $runId; profilePath = $ProfilePath
        name = ''; mode = ''; preview = $Preview; started = $now.ToString('o'); finished = ''
        source = ''; target = ''; archivedTo = ''; restore = $false
        state = 'failed'; exitCode = 9; message = ''; log = $LogPath
    }
    $lock = $null
    $sleepEnabled = $false
    $process = $null
    $returnCode = 9
    try {
        $profile = Read-AgfoProfile $ProfilePath
        $result.name = [string]$profile.profileName
        $result.mode = [string]$profile.mode
        $result.source = [string]$profile.source
        $result.target = [string]$profile.target
        $isRestore = -not [string]::IsNullOrWhiteSpace($RunPath)
        $result.restore = $isRestore
        if ($isRestore) {
            $command = New-AgfoRestoreCommand $profile $RunPath $RestoreTarget $LogPath $Preview
            $result.target = $RestoreTarget
            $result.source = $RunPath
            $result.archivedTo = $RunPath
        } else {
            $paths = Validate-AgfoPaths $profile $true (-not $Preview)
            $command = New-AgfoEngineCommand $profile $paths $LogPath $runId $Preview
            $result.archivedTo = [string]$command.Archive
        }
        $lock = Acquire-AgfoLock (Normalize-AgfoPath ([string]$profile.target))
        if ([bool]$profile.preventSleep) {
            try { Set-AgfoPreventSleep $true; $sleepEnabled = $true } catch { }
        }
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $command.Exe
        $psi.Arguments = Join-AgfoArgs $command.Args
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $psi
        if (-not $process.Start()) { throw 'Aktarim motoru baslatilamadi.' }
        $cancelled = $false
        while (-not $process.WaitForExit(800)) {
            if ([System.IO.File]::Exists($CancelPath)) {
                $cancelled = $true
                try { $process.Kill() } catch { }
                break
            }
        }
        $process.WaitForExit()
        if ($cancelled) {
            $result.state = 'cancelled'
            $result.exitCode = 130
            $result.message = 'Kullanici islemi durdurdu. Degismeyen dosyalar tekrar kopyalanmaz.'
            $returnCode = 130
        } else {
            $code = [int]$process.ExitCode
            $result.exitCode = $code
            if (-not $isRestore -and [string]$profile.mode -eq 'incremental') {
                if ($code -lt 8) {
                    $result.state = 'completed'
                    $result.message = if ($Preview) { 'Onizleme tamamlandi.' } else { 'Robocopy islemi tamamlandi (kritik dosya hatasi yok).' }
                    $returnCode = 0
                } elseif (($code -band 16) -ne 0) {
                    $result.state = 'failed'
                    $result.message = 'Robocopy kritik hata verdi; log ve paylasim erisimini kontrol edin.'
                    $returnCode = 16
                } else {
                    $result.state = 'partial'
                    $result.message = 'Bazi dosya/klasorler atlandi; diger dosyalar islendi. FAILED/ERROR satirlarina bakin.'
                    $returnCode = 8
                }
            } else {
                if ($code -eq 0) {
                    $result.state = 'completed'
                    $result.message = if ($Preview) { 'rclone onizlemesi tamamlandi.' } else { 'rclone islemi tamamlandi.' }
                    $returnCode = 0
                } else {
                    $result.state = 'partial'
                    $result.message = 'rclone sorun raporladi. Detaylar logda; arsivdeki dosyalar korunur.'
                    $returnCode = 8
                }
            }
        }
    } catch {
        $result.state = 'failed'
        $result.exitCode = 9
        $result.message = [string]$_.Exception.Message
        $returnCode = 9
        try {
            $errorPath = if ([System.IO.File]::Exists($LogPath)) { $LogPath + '.startup-error.txt' } else { $LogPath }
            [System.IO.File]::WriteAllText($errorPath,
                ([string]$_.Exception.ToString()), [System.Text.Encoding]::UTF8)
        } catch { }
    } finally {
        if ($process) { $process.Dispose() }
        if ($sleepEnabled) { try { Set-AgfoPreventSleep $false } catch { } }
        if ($lock) { try { $lock.ReleaseMutex() } catch { }; $lock.Dispose() }
        $result.finished = (Get-Date).ToString('o')
        try { Write-AgfoJson $StatusPath $result } catch { }
    }
    return $returnCode
}
