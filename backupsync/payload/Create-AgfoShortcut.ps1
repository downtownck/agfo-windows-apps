# Creates a normal Windows shortcut without extra Python modules.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$LinkPath,
    [Parameter(Mandatory=$true)][string]$ExePath,
    [string]$ExeArgs = '',
    [string]$Description = 'AGFO BackupSync v2.3.0'
)
$ErrorActionPreference='Stop'
$parent=[System.IO.Path]::GetDirectoryName($LinkPath)
[void][System.IO.Directory]::CreateDirectory($parent)
$shell=New-Object -ComObject WScript.Shell
$shortcut=$shell.CreateShortcut($LinkPath)
$shortcut.TargetPath=$ExePath
$shortcut.Arguments=$ExeArgs
$shortcut.WorkingDirectory=[System.IO.Path]::GetDirectoryName($ExePath)
$shortcut.IconLocation=$ExePath + ',0'
$shortcut.Description=$Description
$shortcut.Save()
