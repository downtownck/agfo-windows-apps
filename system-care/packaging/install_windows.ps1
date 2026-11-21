$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$root=Split-Path -Parent $PSScriptRoot
$dest=Join-Path $env:LOCALAPPDATA 'Programs\AGFO System Care'
$files=@('app.pyw','care_elevated.ps1','sc_apps.py','sc_hardware.py','care_hw.py','sc_vendor.py','care_oem.py','sc_procs.py','care_procs.py','sc_ai.py','care_ai.py','sc_base.py','sc_bloat.py','sc_clean.py','sc_common.py','sc_drivers.py','sc_engines.py','sc_install.py','sc_maint.py','sc_organizer.py','sc_pad.py','sc_phantom.py','sc_programs.py','sc_tweaks.py','sc_vpn.py','care_core.py','care_tweaks.py','care_catalog.py','care_theme.py','care_icons.py','care_vpn.py','organizer_core.py','net_tools.py','scanner_core.py','supertools_core.py','supertools_ui.py','ssh_profiles.py','ssh_password_vault.py','ssh_password_transport.py','ssh_workspace.py','agfo_github_update.py','care_tasks.ps1','assets\agfo.ico','assets\nvidia-data.json','README_TR.md','THIRD_PARTY_LICENSES.txt')
# Surum care_core.py'den okunur (elle yazilan surum eskiyordu).
$version=([regex]::Match((Get-Content -LiteralPath (Join-Path $root 'care_core.py') -Raw -Encoding UTF8),"(?m)^VERSION = '([0-9.]+)'")).Groups[1].Value
foreach($file in $files) { if(-not (Test-Path -LiteralPath (Join-Path $root $file) -PathType Leaf)){throw "Dosya bulunamadi: $file"} }
# 4.0: hazir calisma ortami (Python gerekmez). Paketin icinde 'AGFO System Care.exe' + _internal varsa onlar kurulur.
$exeName='AGFO System Care.exe'
$runtime=Test-Path -LiteralPath (Join-Path $root $exeName) -PathType Leaf
Get-Process -Name 'AGFO System Care' -ErrorAction SilentlyContinue | Where-Object { $_.Path -like (Join-Path $dest '*') } | Stop-Process -Force -ErrorAction SilentlyContinue
if($runtime) {
 Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -and $_.CommandLine -like '*AGFO System Care\app.pyw*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
 New-Item -ItemType Directory -Path $dest -Force | Out-Null
 if(Test-Path -LiteralPath (Join-Path $dest '_internal')) { Remove-Item -LiteralPath (Join-Path $dest '_internal') -Recurse -Force }
 Copy-Item -Path (Join-Path $root '*') -Destination $dest -Recurse -Force
 Get-ChildItem -LiteralPath $dest -Recurse -File | Unblock-File -ErrorAction SilentlyContinue
 Set-Content -LiteralPath (Join-Path $dest 'VERSION') -Value $version -Encoding ASCII
 $exe=Join-Path $dest $exeName
 $menu=Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\AGFO'
 New-Item -ItemType Directory -Path $menu -Force | Out-Null
 $sc=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $menu 'AGFO System Care.lnk'))
 $sc.TargetPath=$exe;$sc.Arguments='';$sc.WorkingDirectory=$dest;$sc.IconLocation=$exe+',0';$sc.Description=('AGFO System Care '+$version);$sc.Save()
 Write-Host ('Kurulum tamamlandi (Python gerekmez): '+$dest)
 Start-Process -FilePath $exe -WorkingDirectory $dest
 exit 0
}
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
Set-Content -LiteralPath (Join-Path $dest 'VERSION') -Value $version -Encoding ASCII
# Modern gorunum (istege bagli): ttkbootstrap yalnizca System Care'in kendi klasorune kurulur (Python kurulumuna dokunulmaz).
# Olmazsa klasik gorunum kullanilir; uygulama icinden (sol alt: Gorunum) sonradan kurulabilir.
$uiLib=Join-Path $env:LOCALAPPDATA 'AGFO\SystemCare\ui-lib'
try {
 $ErrorActionPreference='Continue'
 $pyOk=@(& $python -c "import sys; print(1 if sys.version_info >= (3, 10) else 0)" 2>$null)[-1]
 if($pyOk -eq '1' -and -not (Test-Path -LiteralPath (Join-Path $uiLib 'ttkbootstrap'))) {
  Write-Host 'Modern gorunum bileseni (ttkbootstrap 2.2.7) kuruluyor...'
  & $python -m pip install --disable-pip-version-check --no-input --upgrade --target $uiLib 'ttkbootstrap==2.2.7' *> $null
  if($LASTEXITCODE -ne 0) { Write-Host 'Modern gorunum kurulamadi; klasik gorunum kullanilacak.' }
 }
} catch { Write-Host ('Modern gorunum atlandi: '+$_.Exception.Message) }
finally { $ErrorActionPreference='Stop' }
$pythonW=Join-Path (Split-Path $python -Parent) 'pythonw.exe'
if(-not (Test-Path $pythonW)) { $pythonW=$python }
$menu=Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\AGFO'
New-Item -ItemType Directory -Path $menu -Force | Out-Null
$link=Join-Path $menu 'AGFO System Care.lnk'
$sc=(New-Object -ComObject WScript.Shell).CreateShortcut($link)
$sc.TargetPath=$pythonW;$sc.Arguments='"'+(Join-Path $dest 'app.pyw')+'"';$sc.WorkingDirectory=$dest;$sc.IconLocation=(Join-Path $dest 'assets\agfo.ico')+',0';$sc.Description=('AGFO System Care '+$version);$sc.Save()
Write-Host ('Kurulum tamamlandi: '+$dest)
Start-Process -FilePath $pythonW -ArgumentList ('"'+(Join-Path $dest 'app.pyw')+'"') -WorkingDirectory $dest
