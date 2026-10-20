$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$root=Split-Path -Parent $PSScriptRoot
$dest=Join-Path $env:LOCALAPPDATA 'Programs\AGFO Phantom Shot'
$required=@('app.pyw','phantom_core.py','agfo_github_update.py','README_TR.md')
$optional=@('assets\agfo-phantom.ico')
foreach($file in $required) { if(-not (Test-Path -LiteralPath (Join-Path $root $file) -PathType Leaf)){throw "Dosya bulunamadi: $file"} }

function FindPython {
 foreach($name in @('py','python')) {
  $c=Get-Command $name -ErrorAction SilentlyContinue
  if(-not $c){continue}
  if($name -eq 'py') { $candidate= & py -3 -c 'import sys, tkinter; print(sys.executable)' 2>$null }
  else { $candidate= & python -c 'import sys, tkinter; print(sys.executable)' 2>$null }
  if($LASTEXITCODE -eq 0 -and $candidate) { $candidatePath = @($candidate)[-1].Trim(); if(Test-Path -LiteralPath $candidatePath -PathType Leaf) {return $candidatePath} }
 }
 return $null
}
$python=FindPython
if(-not $python) { throw 'Python 3 ve tkinter gerekli. Python kurun: https://www.python.org/downloads/windows/ (kurucu Pythonu otomatik indirmez).' }

# Gerekli paketler (yakalama + tus dinleme) ve istege bagli paketler (jpg + tepsi ikonu).
Write-Host 'Gerekli paketler kuruluyor: mss, pynput ...'
& $python -m pip install --user --upgrade mss pynput 2>&1 | Out-Host
if($LASTEXITCODE -ne 0) { Write-Warning 'mss/pynput kurulamadi; uygulama ilk acilista uyari verebilir. Internet/pip erisimini kontrol edin.' }
& $python -m pip install --user --upgrade pillow pystray 2>&1 | Out-Host   # istege bagli; basarisiz olursa sorun degil

# Calisan eski surum varsa kapat (dosyalar kilitli kalmasin, yeni surum aninda devreye girsin).
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
 Where-Object { $_.CommandLine -and $_.CommandLine -like '*AGFO Phantom Shot\app.pyw*' } |
 ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

New-Item -ItemType Directory -Path (Join-Path $dest 'assets') -Force | Out-Null
foreach($file in ($required + $optional)){
 $src=Join-Path $root $file
 if(-not (Test-Path -LiteralPath $src -PathType Leaf)) { continue }
 $target=Join-Path $dest $file
 Copy-Item -LiteralPath $src -Destination $target -Force
 Unblock-File -LiteralPath $target -ErrorAction SilentlyContinue   # Internet'ten indirilen ZIP'in Zone.Identifier isaretini kaldir
}
Set-Content -LiteralPath (Join-Path $dest 'VERSION') -Value '1.0.0' -Encoding ASCII

$pythonW=Join-Path (Split-Path $python -Parent) 'pythonw.exe'
if(-not (Test-Path $pythonW)) { $pythonW=$python }
$menu=Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\AGFO'
New-Item -ItemType Directory -Path $menu -Force | Out-Null
$link=Join-Path $menu 'AGFO Phantom Shot.lnk'
$ico=Join-Path $dest 'assets\agfo-phantom.ico'
$sc=(New-Object -ComObject WScript.Shell).CreateShortcut($link)
$sc.TargetPath=$pythonW; $sc.Arguments='"'+(Join-Path $dest 'app.pyw')+'"'; $sc.WorkingDirectory=$dest
if(Test-Path -LiteralPath $ico) { $sc.IconLocation=$ico+',0' }
$sc.Description='AGFO Phantom Shot 1.0.0'; $sc.Save()
Write-Host ('Kurulum tamamlandi: '+$dest)
Start-Process -FilePath $pythonW -ArgumentList ('"'+(Join-Path $dest 'app.pyw')+'"') -WorkingDirectory $dest
