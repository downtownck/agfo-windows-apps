#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ProfilePath,
    [switch]$Preview,
    [string]$RestoreRun = '',
    [string]$RestoreTarget = '',
    [string]$LogPath = '',
    [string]$StatusPath = '',
    [string]$CancelPath = ''
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'AGFO-BackupSync-Core.ps1')
$exitCode = Invoke-AgfoJob $ProfilePath ([bool]$Preview) $RestoreRun $RestoreTarget $LogPath $StatusPath $CancelPath
exit ([int]$exitCode)
