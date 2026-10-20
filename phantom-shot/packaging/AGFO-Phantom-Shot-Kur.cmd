@echo off
rem AGFO Phantom Shot - kurucu / guncelleyici (yonetici gerekmez)
rem GitHub Releases'ten en guncel AGFO-Phantom-Shot.exe dosyasini indirir, SHA-256 ile dogrular,
rem %LOCALAPPDATA%\Programs\AGFO-Phantom-Shot altina kurar, kisayol olusturur ve baslatir.
title AGFO Phantom Shot Kurulum
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$s=[IO.File]::ReadAllText('%~f0'); $i=$s.IndexOf('#AGFO'+'-PS-BEGIN'); iex $s.Substring($i)"
if errorlevel 1 (
  echo.
  echo Kurulum basarisiz. Yukaridaki mesaja bakin.
  pause
  exit /b 1
)
exit /b 0

#AGFO-PS-BEGIN
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}
$repo   = 'downtownck/agfo-windows-apps'
$prefix = 'phantom-shot-v'
$asset  = 'AGFO-Phantom-Shot.exe'
$dir    = Join-Path $env:LOCALAPPDATA 'Programs\AGFO-Phantom-Shot'
$target = Join-Path $dir $asset
$ua     = @{ 'User-Agent' = 'AGFO-Phantom-Shot-Setup'; 'Accept' = 'application/vnd.github+json' }
try {
  Write-Host 'AGFO Phantom Shot kurulum' -ForegroundColor Cyan
  Write-Host 'GitHub''da en guncel surum denetleniyor...'
  $rels = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/releases?per_page=50" -Headers $ua -UseBasicParsing
  $rel = $rels | Where-Object { -not $_.draft -and -not $_.prerelease -and $_.tag_name -match ('^' + $prefix + '(\d+(\.\d+){1,3})$') } |
         Sort-Object { [version]($_.tag_name.Substring($prefix.Length)) } -Descending | Select-Object -First 1
  if (-not $rel) { throw 'GitHub''da AGFO Phantom Shot surumu bulunamadi.' }
  $version = $rel.tag_name.Substring($prefix.Length)
  $exeAsset = $rel.assets | Where-Object { $_.name -eq $asset } | Select-Object -First 1
  if (-not $exeAsset) { throw "Surum $version icinde $asset yok." }

  # Beklenen SHA-256: GitHub asset ozeti, yoksa ayni surumdeki SHA256SUMS.txt.
  $sha = ''
  if ($exeAsset.digest -and $exeAsset.digest -like 'sha256:*') { $sha = $exeAsset.digest.Substring(7).ToLower() }
  if (-not $sha) {
    $sums = $rel.assets | Where-Object { $_.name -eq 'SHA256SUMS.txt' } | Select-Object -First 1
    if (-not $sums) { throw 'Bu surum icin ozet yayinlanmamis; kurulum reddedildi.' }
    $txt = (Invoke-WebRequest -Uri $sums.browser_download_url -Headers @{ 'User-Agent' = $ua['User-Agent'] } -UseBasicParsing).Content
    if ($txt -is [byte[]]) { $txt = [Text.Encoding]::ASCII.GetString($txt) }
    foreach ($line in ($txt -split "`n")) {
      $p = $line.Trim() -split '\s+\*?', 2
      if ($p.Count -eq 2 -and $p[1].Trim() -eq $asset) { $sha = $p[0].ToLower() }
    }
    if ($sha.Length -ne 64) { throw "$asset SHA256SUMS.txt icinde listelenmemis; kurulum reddedildi." }
  }

  if ((Test-Path -LiteralPath $target) -and ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLower() -eq $sha)) {
    Write-Host "AGFO Phantom Shot $version zaten kurulu."
  } else {
    $running = Get-Process -Name 'AGFO-Phantom-Shot' -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path -eq $target }
    if ($running) { throw 'AGFO Phantom Shot calisiyor. Kapatip bu dosyayi tekrar calistirin.' }
    Write-Host ("AGFO Phantom Shot {0} indiriliyor ({1:N1} MB)..." -f $version, ($exeAsset.size / 1MB))
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $tmp = Join-Path $dir ($asset + '.download')
    Invoke-WebRequest -Uri $exeAsset.browser_download_url -OutFile $tmp -Headers @{ 'User-Agent' = $ua['User-Agent'] } -UseBasicParsing
    $got = (Get-FileHash -LiteralPath $tmp -Algorithm SHA256).Hash.ToLower()
    if ($got -ne $sha) { Remove-Item -LiteralPath $tmp -Force; throw 'Ozet uyusmuyor; indirilen dosya silindi, hicbir sey kurulmadi.' }
    Unblock-File -LiteralPath $tmp -ErrorAction SilentlyContinue
    Move-Item -LiteralPath $tmp -Destination $target -Force
    Write-Host "Kuruldu: $dir"
  }

  # Kisayollar: uygulamanin kendi kullandigi ad ve klasorlerle ayni (guncelleyici/kaldirici calismaya devam etsin).
  $sh = New-Object -ComObject WScript.Shell
  $menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'AGFO'
  New-Item -ItemType Directory -Force -Path $menu | Out-Null
  foreach ($lnkPath in @((Join-Path $menu 'AGFO Phantom Shot.lnk'), (Join-Path ([Environment]::GetFolderPath('Desktop')) 'AGFO Phantom Shot.lnk'))) {
    $l = $sh.CreateShortcut($lnkPath)
    $l.TargetPath = $target
    $l.WorkingDirectory = $dir
    $l.IconLocation = $target + ',0'
    $l.Description = 'AGFO Phantom Shot'
    $l.Save()
  }
  Write-Host 'Kisayollar olusturuldu: Baslat menusu > AGFO ve Masaustu.'
  Start-Process -FilePath $target -WorkingDirectory $dir
  Write-Host 'AGFO Phantom Shot baslatildi. Bu pencereyi kapatabilirsiniz.' -ForegroundColor Green
  Start-Sleep -Seconds 3
  exit 0
} catch {
  Write-Host ('HATA: ' + $_.Exception.Message) -ForegroundColor Red
  exit 1
}
