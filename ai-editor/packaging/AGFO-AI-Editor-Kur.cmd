@echo off
rem AGFO AI Editor - installer / updater (no admin rights needed)
rem Downloads the latest AGFO-AI-Editor.exe from GitHub Releases, verifies SHA-256,
rem installs to %LOCALAPPDATA%\Programs\AGFO-AI-Editor, creates shortcuts and starts it.
title AGFO AI Editor Setup
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$s=[IO.File]::ReadAllText('%~f0'); $i=$s.IndexOf('#AGFO'+'-PS-BEGIN'); iex $s.Substring($i)"
if errorlevel 1 (
  echo.
  echo Setup failed. See the message above.
  pause
  exit /b 1
)
exit /b 0

#AGFO-PS-BEGIN
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}
$repo   = 'downtownck/agfo-windows-apps'
$prefix = 'ai-editor-v'
$asset  = 'AGFO-AI-Editor.exe'
$dir    = Join-Path $env:LOCALAPPDATA 'Programs\AGFO-AI-Editor'
$target = Join-Path $dir $asset
$ua     = @{ 'User-Agent' = 'AGFO-AI-Editor-Setup'; 'Accept' = 'application/vnd.github+json' }
try {
  Write-Host 'AGFO AI Editor setup' -ForegroundColor Cyan
  Write-Host 'Checking the latest version on GitHub...'
  $rels = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/releases?per_page=50" -Headers $ua -UseBasicParsing
  $rel = $rels | Where-Object { -not $_.draft -and -not $_.prerelease -and $_.tag_name -match ('^' + $prefix + '(\d+(\.\d+){1,3})$') } |
         Sort-Object { [version]($_.tag_name.Substring($prefix.Length)) } -Descending | Select-Object -First 1
  if (-not $rel) { throw 'No AGFO AI Editor release found on GitHub.' }
  $version = $rel.tag_name.Substring($prefix.Length)
  $exeAsset = $rel.assets | Where-Object { $_.name -eq $asset } | Select-Object -First 1
  if (-not $exeAsset) { throw "Release $version has no $asset." }

  # Expected SHA-256: GitHub asset digest, otherwise SHA256SUMS.txt from the same release.
  $sha = ''
  if ($exeAsset.digest -and $exeAsset.digest -like 'sha256:*') { $sha = $exeAsset.digest.Substring(7).ToLower() }
  if (-not $sha) {
    $sums = $rel.assets | Where-Object { $_.name -eq 'SHA256SUMS.txt' } | Select-Object -First 1
    if (-not $sums) { throw 'No checksum published for this release; refusing to install.' }
    $txt = (Invoke-WebRequest -Uri $sums.browser_download_url -Headers @{ 'User-Agent' = $ua['User-Agent'] } -UseBasicParsing).Content
    if ($txt -is [byte[]]) { $txt = [Text.Encoding]::ASCII.GetString($txt) }
    foreach ($line in ($txt -split "`n")) {
      $p = $line.Trim() -split '\s+\*?', 2
      if ($p.Count -eq 2 -and $p[1].Trim() -eq $asset) { $sha = $p[0].ToLower() }
    }
    if ($sha.Length -ne 64) { throw "$asset is not listed in SHA256SUMS.txt; refusing to install." }
  }

  if ((Test-Path -LiteralPath $target) -and ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLower() -eq $sha)) {
    Write-Host "AGFO AI Editor $version is already installed."
  } else {
    $running = Get-Process -Name 'AGFO-AI-Editor' -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path -eq $target }
    if ($running) { throw 'AGFO AI Editor is running. Close it and run this file again.' }
    Write-Host ("Downloading AGFO AI Editor {0} ({1:N1} MB)..." -f $version, ($exeAsset.size / 1MB))
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $tmp = Join-Path $dir ($asset + '.download')
    Invoke-WebRequest -Uri $exeAsset.browser_download_url -OutFile $tmp -Headers @{ 'User-Agent' = $ua['User-Agent'] } -UseBasicParsing
    $got = (Get-FileHash -LiteralPath $tmp -Algorithm SHA256).Hash.ToLower()
    if ($got -ne $sha) { Remove-Item -LiteralPath $tmp -Force; throw 'Checksum mismatch; the download was deleted and nothing was installed.' }
    Unblock-File -LiteralPath $tmp -ErrorAction SilentlyContinue
    Move-Item -LiteralPath $tmp -Destination $target -Force
    Write-Host "Installed to $dir"
  }

  # Shortcuts: same names and folders the app itself uses, so its updater and uninstaller keep working.
  $sh = New-Object -ComObject WScript.Shell
  $menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'AGFO'
  New-Item -ItemType Directory -Force -Path $menu | Out-Null
  foreach ($lnkPath in @((Join-Path $menu 'AGFO AI Editor.lnk'), (Join-Path ([Environment]::GetFolderPath('Desktop')) 'AGFO AI Editor.lnk'))) {
    $l = $sh.CreateShortcut($lnkPath)
    $l.TargetPath = $target
    $l.WorkingDirectory = $dir
    $l.IconLocation = $target + ',0'
    $l.Description = 'AGFO AI Editor'
    $l.Save()
  }
  Write-Host 'Shortcuts created: Start menu > AGFO, and Desktop.'
  Start-Process -FilePath $target -WorkingDirectory $dir
  Write-Host 'AGFO AI Editor started. You can close this window.' -ForegroundColor Green
  Start-Sleep -Seconds 3
  exit 0
} catch {
  Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
  exit 1
}
