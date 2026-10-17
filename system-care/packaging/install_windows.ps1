$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$root=Split-Path -Parent $PSScriptRoot
$dest=Join-Path $env:LOCALAPPDATA 'Programs\AGFO System Care'
$files=@('app.pyw','care_core.py','agfo_github_update.py','care_tasks.ps1','assets\agfo.ico','README_TR.md')
foreach($file in $files) { if(-not (Test-Path -LiteralPath (Join-Path $root $file) -PathType Leaf)){throw "Dosya bulunamadi: $file"} }
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
# Calisan eski surum varsa kapat (dosyalar kilitli kalmasin, yeni surum aninda devreye girsin).
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
 Where-Object { $_.CommandLine -and $_.CommandLine -like '*AGFO System Care\app.pyw*' } |
 ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Path (Join-Path $dest 'assets') -Force | Out-Null
foreach($file in $files){
 $target=Join-Path $dest $file
 Copy-Item -LiteralPath (Join-Path $root $file) -Destination $target -Force
 Unblock-File -LiteralPath $target -ErrorAction SilentlyContinue   # Internet'ten indirilen ZIP'in Zone.Identifier isaretini kaldir
}
Set-Content -LiteralPath (Join-Path $dest 'VERSION') -Value '3.5.0' -Encoding ASCII
$pythonW=Join-Path (Split-Path $python -Parent) 'pythonw.exe'
if(-not (Test-Path $pythonW)) { $pythonW=$python }
$menu=Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\AGFO'
New-Item -ItemType Directory -Path $menu -Force | Out-Null
$link=Join-Path $menu 'AGFO System Care.lnk'
$sc=(New-Object -ComObject WScript.Shell).CreateShortcut($link)
$sc.TargetPath=$pythonW;$sc.Arguments='"'+(Join-Path $dest 'app.pyw')+'"';$sc.WorkingDirectory=$dest;$sc.IconLocation=(Join-Path $dest 'assets\agfo.ico')+',0';$sc.Description='AGFO System Care 3.5.0';$sc.Save()
Write-Host ('Kurulum tamamlandi: '+$dest)
Start-Process -FilePath $pythonW -ArgumentList ('"'+(Join-Path $dest 'app.pyw')+'"') -WorkingDirectory $dest
