#requires -Version 5.1
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'AGFO-BackupSync-Core.ps1')
$script:Tests = 0
function Check([bool]$Ok, [string]$Message) {
    $script:Tests++
    if (-not $Ok) { throw ('TEST FAILED: ' + $Message) }
}

$p = New-AgfoProfile
$p.profileName = 'Test'
$p.source = 'D:\Source Data'
$p.target = '\\UGREEN\BackupShare\AGFO-Archive'
$paths = Validate-AgfoPaths $p $false
Check ($paths.Source -eq 'D:\Source Data') 'path normalization'
Check ($paths.Target -eq '\\UGREEN\BackupShare\AGFO-Archive') 'UNC normalization'
Check (Test-AgfoWithin 'D:\Source Data\Sub' 'D:\Source Data') 'nested path detection'
Check (-not (Test-AgfoWithin 'D:\Source Data2' 'D:\Source Data')) 'prefix is not nested'
Check (Test-AgfoRoot '\\UGREEN\BackupShare') 'UNC share root detection'
Check (Test-AgfoRoot 'D:\') 'drive root detection'

$cmd = New-AgfoEngineCommand $p $paths 'C:\Logs\copy.log' 'run001' $false $true
Check ($cmd.Exe -eq 'robocopy.exe') 'native engine'
Check ($cmd.Args -contains '/E') 'recursive Robocopy'
Check ($cmd.Args -contains '/Z') 'resume switch'
Check (-not ($cmd.Args -contains '/MIR')) 'NO unsafe mirror switch'
Check (-not ($cmd.Args -contains '/PURGE')) 'NO unsafe purge switch'
Check (-not ($cmd.Args -contains '/256')) 'long paths are not disabled'
Check ($cmd.Args -contains '/XA:E') 'skip EFS encrypted files'
$dryCmd = New-AgfoEngineCommand $p $paths 'C:\Logs\dry.log' 'run002' $true $true
Check ($dryCmd.Args -contains '/L') 'Robocopy dry run'

$p.mode = 'versioned'
$v = New-AgfoEngineCommand $p $paths 'C:\Logs\rclone.log' 'run003' $false $true
Check ($v.Args[0] -eq 'copy') 'versioned copy mode'
Check ($v.Args -contains '--backup-dir') 'version archive argument'
Check ($v.Args -contains '/.agfo-versions/**') 'archive exclusion'
Check ($v.Args -notcontains '--ignore-errors') 'do not delete after errors'
Check ($v.Args -notcontains '--dry-run') 'real mode not dry run'
Check (([string]$v.Archive).Contains('.agfo-versions')) 'archive path'
$vdry = New-AgfoEngineCommand $p $paths 'C:\Logs\rclone.log' 'run004' $true $true
Check ($vdry.Args -contains '--dry-run') 'rclone preview'

$p.mode = 'mirror'
$p.mirrorConsent = $false
$blocked = $false
try { $null = Validate-AgfoPaths $p $false $true $false } catch { $blocked = $true }
Check $blocked 'mirror requires authorization'
$p.mirrorConsent = $true
$paths = Validate-AgfoPaths $p $false $true $false
$mirror = New-AgfoEngineCommand $p $paths 'C:\Logs\mirror.log' 'run005' $false $true
Check ($mirror.Args[0] -eq 'sync') 'mirror via rclone sync'
Check ($mirror.Args -contains '--max-delete') 'mirror deletion cap'
Check ($mirror.Args -contains '--backup-dir') 'mirror archive protection'
Check ($mirror.Args -notcontains '--ignore-errors') 'safe when source has errors'

$p.target = '\\UGREEN\BackupShare'
$blocked = $false
try { $null = Validate-AgfoPaths $p $false $true $false } catch { $blocked = $true }
Check $blocked 'mirror share-root blocked'
$p.target = '\\UGREEN\BackupShare\AGFO-Archive'
$archive = Join-Path (Get-AgfoArchiveRoot $p) '20261017_120000_001_a1b2c3'
$restore = New-AgfoRestoreCommand $p $archive 'C:\AGFO-Restore\20261017_120000_001_a1b2c3' 'C:\Logs\restore.log' $true $true
Check ($restore.Args -contains '--dry-run') 'restore preview'
Check ($restore.Args[0] -eq 'copy') 'restore copy-only'

$nestedP = New-AgfoProfile
$nestedP.source = 'C:\Data'
$nestedP.target = 'C:\Data\Backup'
$blocked = $false
try { $null = Validate-AgfoPaths $nestedP $false } catch { $blocked = $true }
Check $blocked 'destination inside source blocked'

# v2.3.3: saving an EXISTING profile/status file (File.Replace) must work (was: "path is not of a legal form").
$jsonDir = Join-Path ([System.IO.Path]::GetTempPath()) ('agfo-test-' + [guid]::NewGuid().ToString('N'))
try {
    $jsonFile = Join-Path $jsonDir 'p.json'
    Write-AgfoJson $jsonFile ([pscustomobject]@{ n = 1 })
    Write-AgfoJson $jsonFile ([pscustomobject]@{ n = 2 })
    Check ((Read-AgfoJson $jsonFile).n -eq 2) 'overwrite existing JSON'
    Check (@(Get-ChildItem -LiteralPath $jsonDir -File).Count -eq 1) 'no temp/backup files left'
    $saved = New-AgfoProfile
    $saved.profileName = 'Resave'
    $savedPath = Save-AgfoProfile $saved
    $saved.threads = 4
    $null = Save-AgfoProfile $saved
    Check ((Read-AgfoProfile $savedPath).threads -eq 4) 'resave existing profile'
    Remove-Item -LiteralPath $savedPath -Force
} finally { Remove-Item -LiteralPath $jsonDir -Recurse -Force -ErrorAction SilentlyContinue }

Write-Host ('PASS: ' + $script:Tests + ' defensive checks') -ForegroundColor Green
