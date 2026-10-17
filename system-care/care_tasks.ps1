param(
 [Parameter(Mandatory=$true)][ValidateSet('driver-scan','driver-install','devices','drivers-list','driver-backup','app-scan','app-update','temp-preview','temp-clean','component-analyze','component-clean','health-scan','health-repair','system-info','restore-point','recycle-paths','driver-analyze','appx-list','appx-remove','phantom-list','phantom-remove')][string]$Action,
 [string]$BackupPath = '',
 [string]$UpdateIds = '',
 [string]$Paths = '',
 [ValidateSet('yes','no')][string]$IncludeWU = 'yes',
 [string]$Packages = '',
 [ValidateSet('yes','no')][string]$Provisioned = 'no',
 [string]$InstanceIds = '',
 [ValidateSet('yes','no')][string]$ForceRestorePoint = 'no'
)
# AGFO System Care 3.5.0 gorev motoru.
# Insan icin satirlar ASCII Turkce; uygulamanin okudugu kayitlar '@@' onekli tek satir JSON olarak yazilir.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

function IsAdmin { try { $identity=[Security.Principal.WindowsIdentity]::GetCurrent(); $p=[Security.Principal.WindowsPrincipal]::new($identity); return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) } catch { return $false } }
function RequireAdmin { if (-not (IsAdmin)) { Write-Output 'Bu islem icin uygulamayi yonetici olarak baslatin.'; exit 740 } }
function Emit($obj) { Write-Output ('@@'+($obj | ConvertTo-Json -Compress -Depth 4)) }
function WuSession { $session=New-Object -ComObject Microsoft.Update.Session; $session.ClientApplicationID='AGFO System Care'; $searcher=$session.CreateUpdateSearcher(); return @{Session=$session;Searcher=$searcher} }
function FindDriverUpdates {
 $wu=WuSession
 $result=$wu.Searcher.Search("IsInstalled=0 and IsHidden=0 and Type='Driver'")
 return @{WU=$wu;Result=$result}
}
function TempCandidates {
 $roots=@($env:TEMP,(Join-Path $env:LOCALAPPDATA 'Temp')) | Where-Object { $_ } | ForEach-Object { [IO.Path]::GetFullPath($_).TrimEnd('\') } | Sort-Object -Unique
 $cutoff=(Get-Date).AddDays(-7)
 foreach($root in $roots) {
  if(-not (Test-Path -LiteralPath $root -PathType Container)) { continue }
  Get-ChildItem -LiteralPath $root -File -Force -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -lt $cutoff -and -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) }
 }
}
function RunDism {
 param([string[]]$DismArgs)
 RequireAdmin
 & dism.exe @DismArgs
 $code=$LASTEXITCODE
 if($code -eq 3010) { Write-Output 'DISM tamamlandi; degisikliklerin uygulanmasi icin yeniden baslatma gerekli.'; return }
 if($code -ne 0) { throw ('DISM hata: '+$code) }
}
function PendingReboot {
 $keys=@('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending',
         'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired')
 foreach($k in $keys) { if(Test-Path -LiteralPath $k) { return $true } }
 $pfr=Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager' -Name PendingFileRenameOperations -ErrorAction SilentlyContinue
 return [bool]($pfr -and $pfr.PendingFileRenameOperations)
}
function AgfoNative {
 # Kayit anahtari son yazma zamani (DeviceCleanup'in 'son kullanim' olcutu) ve SetupAPI ile aygit kaldirma (pnputil /remove-device yoksa).
 if(-not ('AgfoNative' -as [type])) {
  Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public static class AgfoNative {
  [DllImport("advapi32.dll", CharSet=CharSet.Unicode)] static extern int RegOpenKeyEx(UIntPtr hKey, string sub, int opt, int sam, out UIntPtr res);
  [DllImport("advapi32.dll", CharSet=CharSet.Unicode)] static extern int RegQueryInfoKey(UIntPtr hKey, IntPtr cls, IntPtr clsLen, IntPtr res, IntPtr subKeys, IntPtr maxSub, IntPtr maxCls, IntPtr vals, IntPtr maxValName, IntPtr maxValLen, IntPtr secDesc, out long lastWrite);
  [DllImport("advapi32.dll")] static extern int RegCloseKey(UIntPtr h);
  public static long LastWrite(string sub) {
    UIntPtr h; if (RegOpenKeyEx(new UIntPtr(0x80000002u), sub, 0, 0x20019, out h) != 0) return 0;
    long t; int r = RegQueryInfoKey(h, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, out t);
    RegCloseKey(h); return r == 0 ? t : 0; }
  [StructLayout(LayoutKind.Sequential)] public struct SP_DEVINFO_DATA { public int cbSize; public Guid ClassGuid; public int DevInst; public IntPtr Reserved; }
  [DllImport("setupapi.dll", SetLastError=true)] static extern IntPtr SetupDiCreateDeviceInfoList(IntPtr guid, IntPtr hwnd);
  [DllImport("setupapi.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool SetupDiOpenDeviceInfo(IntPtr set, string id, IntPtr hwnd, int flags, ref SP_DEVINFO_DATA d);
  [DllImport("setupapi.dll", SetLastError=true)] static extern bool SetupDiRemoveDevice(IntPtr set, ref SP_DEVINFO_DATA d);
  [DllImport("setupapi.dll")] static extern bool SetupDiDestroyDeviceInfoList(IntPtr set);
  public static int Remove(string instanceId) {
    IntPtr set = SetupDiCreateDeviceInfoList(IntPtr.Zero, IntPtr.Zero);
    if (set == new IntPtr(-1)) return Marshal.GetLastWin32Error();
    try { SP_DEVINFO_DATA d = new SP_DEVINFO_DATA(); d.cbSize = Marshal.SizeOf(typeof(SP_DEVINFO_DATA));
      if (!SetupDiOpenDeviceInfo(set, instanceId, IntPtr.Zero, 0, ref d)) return Marshal.GetLastWin32Error();
      if (!SetupDiRemoveDevice(set, ref d)) return Marshal.GetLastWin32Error();
      return 0; } finally { SetupDiDestroyDeviceInfoList(set); } }
}
'@
 }
}
function FileTimeDate([long]$ft) { if($ft -gt 0) { try { return [DateTime]::FromFileTimeUtc($ft).ToLocalTime().ToString('yyyy-MM-dd HH:mm') } catch {} } ; return '' }
function SafeDateTime($d) { try { if($d) { return ([datetime]$d).ToString('yyyy-MM-dd HH:mm') } } catch {} ; return '' }
function SafeDate($d) { try { if($d) { return ([datetime]$d).ToString('yyyy-MM-dd') } } catch {} ; return '' }
function IsProtectedPath([string]$p) {
 # Geri donusume tasima icin kesin yasak kokler. Yalnizca bunlarin ALTINDAKI uygulama klasorleri kabul edilir.
 $full=[IO.Path]::GetFullPath($p).TrimEnd('\')
 if($full.Length -lt 8) { return $true }
 $roots=New-Object System.Collections.Generic.List[string]
 foreach($b in @($env:SystemRoot,$env:SystemDrive,$env:ProgramFiles,${env:ProgramFiles(x86)},$env:ProgramData,$env:APPDATA,$env:LOCALAPPDATA,$env:USERPROFILE,$env:PUBLIC)) { if($b) { $roots.Add($b) } }
 foreach($pair in @(@($env:LOCALAPPDATA,'Programs'),@($env:LOCALAPPDATA,'Microsoft'),@($env:USERPROFILE,'Documents'),@($env:USERPROFILE,'Desktop'),@($env:USERPROFILE,'Downloads'),
                    @($env:ProgramFiles,'Common Files'),@(${env:ProgramFiles(x86)},'Common Files'),@($env:ProgramData,'Microsoft'),@($env:APPDATA,'Microsoft'))) {
  if($pair[0]) { $roots.Add((Join-Path $pair[0] $pair[1])) }   # bos ortam degiskeni (or. 32 bit Windows'ta ProgramFiles(x86)) atlanir
 }
 foreach($r in $roots) { if($full -ieq ([IO.Path]::GetFullPath($r).TrimEnd('\'))) { return $true } }
 if($env:SystemRoot -and $full.StartsWith(([IO.Path]::GetFullPath($env:SystemRoot).TrimEnd('\')+'\'),[StringComparison]::OrdinalIgnoreCase)) { return $true }
 return $false
}

switch($Action) {
 'driver-scan' {
  $found=FindDriverUpdates
  $updates=$found.Result.Updates
  Write-Output ('Windows Update: bekleyen surucu guncellemesi: '+$updates.Count)
  for($i=0;$i -lt $updates.Count;$i++) {
   $u=$updates.Item($i)
   $size=[math]::Round(([double]$u.MaxDownloadSize)/1MB,1)
   Write-Output ('[{0}] {1} | {2} MB | Yeniden baslatma: {3}' -f $i,$u.Title,$size,$u.RebootRequired)
   $cls=''; $mdl=''; $mfr=''; $ver=''
   try { $cls=[string]$u.DriverClass; $mdl=[string]$u.DriverModel; $mfr=[string]$u.DriverManufacturer; $ver=SafeDate $u.DriverVerDate } catch {}
   $hw=''; try { $hw=[string]$u.DriverHardwareID } catch {}
   Emit ([ordered]@{type='wu-driver';id=[string]$u.Identity.UpdateID;title=[string]$u.Title;hwid=$hw;cls=$cls;model=$mdl;maker=$mfr;date=$ver;sizeMB=$size;reboot=[bool]$u.RebootRequired})
  }
 }
 'driver-install' {
  RequireAdmin
  $found=FindDriverUpdates; $updates=$found.Result.Updates
  $wanted=@($UpdateIds -split '[,; ]+' | Where-Object { $_ })
  $collection=New-Object -ComObject Microsoft.Update.UpdateColl
  for($i=0;$i -lt $updates.Count;$i++) {
    $u=$updates.Item($i)
    if($wanted.Count -gt 0 -and ($wanted -notcontains [string]$u.Identity.UpdateID)) { continue }
    if(-not $u.EulaAccepted) { $u.AcceptEula() }
    [void]$collection.Add($u)
  }
  if($collection.Count -eq 0) { Write-Output 'Kurulacak (secili) guncelleme yok. Listeyi yeniden tarayin.'; break }
  Write-Output ('Secilen surucu sayisi: '+$collection.Count)
  $downloader=$found.WU.Session.CreateUpdateDownloader(); $downloader.Updates=$collection
  Write-Output 'Microsoft Windows Update uzerinden indirme basladi.'
  $download=$downloader.Download(); Write-Output ('Indirme sonucu: '+$download.ResultCode)
  if($download.ResultCode -notin @(2,3)) { throw 'Surucu indirmesi basarisiz. Kurulum yapilmadi.' }
  $ready=New-Object -ComObject Microsoft.Update.UpdateColl
  for($i=0;$i -lt $collection.Count;$i++) { $u=$collection.Item($i); if($u.IsDownloaded) { [void]$ready.Add($u) } else { Write-Output ('Indirilemedi: '+$u.Title) } }
  if($ready.Count -eq 0) { throw 'Indirilmis surucu yok.' }
  $installer=$found.WU.Session.CreateUpdateInstaller(); $installer.Updates=$ready
  Write-Output 'Windows Update surucu kurulumunu gerceklestiriyor.'
  $r=$installer.Install()
  Write-Output ('Kurulum sonucu: '+$r.ResultCode+'; Yeniden baslatma gerekli: '+$r.RebootRequired)
  for($i=0;$i -lt $ready.Count;$i++) { $ur=$r.GetUpdateResult($i); Write-Output ('{0}: {1} (HRESULT: {2})' -f $ready.Item($i).Title,$ur.ResultCode,$ur.HResult) }
  if($r.ResultCode -notin @(2,3)) { exit 2 }
  if($r.RebootRequired) { exit 3010 }
 }
 'driver-analyze' {
  # SDIO tarzi gorunum icin tek gecis: aygitlar + donanim kimlikleri + mevcut surucu + Windows Update adaylari.
  $drv=@{}
  foreach($d in @(Get-CimInstance Win32_PnPSignedDriver -ErrorAction SilentlyContinue)) { if($d.DeviceID) { $drv[$d.DeviceID.ToUpperInvariant()]=$d } }
  $devs=@(Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue | Where-Object { $_.PNPDeviceID })
  Write-Output ('Aygit: {0} | surucu kaydi: {1}' -f $devs.Count,$drv.Count)
  foreach($e in $devs) {
   $d=$drv[$e.PNPDeviceID.ToUpperInvariant()]
   $rec=[ordered]@{type='dev';id=[string]$e.PNPDeviceID;name=[string]$e.Name;cls=[string]$e.PNPClass;code=[int]$e.ConfigManagerErrorCode;
     maker=[string]$e.Manufacturer;hwids=@($e.HardwareID | Where-Object { $_ });compat=@($e.CompatibleID | Where-Object { $_ });
     ver='';date='';provider='';inf='';signed=$false}
   if($d) { $rec.ver=[string]$d.DriverVersion; $rec.date=(SafeDate $d.DriverDate); $rec.provider=[string]$d.DriverProviderName; $rec.inf=[string]$d.InfName; $rec.signed=[bool]$d.IsSigned }
   Emit $rec
  }
  if($IncludeWU -eq 'yes') {
   Write-Output 'Windows Update surucu katalogu sorgulaniyor (1-2 dakika surebilir)...'
   try {
    $found=FindDriverUpdates; $updates=$found.Result.Updates
    Write-Output ('Windows Update aday surucu: '+$updates.Count)
    for($i=0;$i -lt $updates.Count;$i++) {
     $u=$updates.Item($i)
     $rec=[ordered]@{type='wu-driver';id=[string]$u.Identity.UpdateID;title=[string]$u.Title;hwid='';cls='';model='';maker='';provider='';date='';
       sizeMB=[math]::Round(([double]$u.MaxDownloadSize)/1MB,1);reboot=[bool]$u.RebootRequired}
     try { $rec.hwid=[string]$u.DriverHardwareID; $rec.cls=[string]$u.DriverClass; $rec.model=[string]$u.DriverModel; $rec.maker=[string]$u.DriverManufacturer
           $rec.provider=[string]$u.DriverProvider; $rec.date=(SafeDate $u.DriverVerDate) } catch {}
     Emit $rec
    }
   } catch { Write-Output ('UYARI: Windows Update sorgulanamadi: '+$_.Exception.Message) }
  }
 }
 'appx-list' {
  # Store / on yuklu uygulamalar (gecerli kullanici). Cerceve ve kaynak paketleri listelenmez.
  $prov=@{}
  if(IsAdmin) { try { foreach($pp in @(Get-AppxProvisionedPackage -Online -ErrorAction Stop)) { $prov[[string]$pp.DisplayName]=$true } } catch { Write-Output ('UYARI: hazir (provisioned) paket listesi alinamadi: '+$_.Exception.Message) } }
  $pk=@(Get-AppxPackage -ErrorAction SilentlyContinue | Where-Object { -not $_.IsFramework -and -not $_.IsResourcePackage })
  Write-Output ('Store / on yuklu uygulama: '+$pk.Count)
  foreach($p in $pk) {
   $nr=$false; try { $nr=[bool]$p.NonRemovable } catch {}
   Emit ([ordered]@{type='appx';name=[string]$p.Name;full=[string]$p.PackageFullName;family=[string]$p.PackageFamilyName;publisher=[string]$p.Publisher;
     ver=[string]$p.Version;sig=[string]$p.SignatureKind;nonremovable=$nr;provisioned=[bool]$prov[[string]$p.Name];admin=(IsAdmin)})
  }
 }
 'appx-remove' {
  # Korunan paketler (Store, WinGet, calisma zamanlari, sistem, codec, surucu yardimcilari) arayuzden gelse bile reddedilir.
  $protect='^(Microsoft\.(WindowsStore|StorePurchaseApp|DesktopAppInstaller|Winget\.Source|VCLibs|UI\.Xaml|NET\.|WindowsAppRuntime|Services\.Store\.Engagement|WidgetsPlatformRuntime|SecHealthUI|AAD\.BrokerPlugin|AccountsControl|Windows\.(?!Photos$|DevHome$)|LanguageExperiencePack|MicrosoftEdge|ApplicationCompatibilityEnhancements|OneDriveSync|WindowsTerminal$|WindowsNotepad$|WindowsCalculator$)|Microsoft\.\w+(Image|Video|Media)Extension|MicrosoftWindows\.|windows\.|Windows\.|NcsiUwpApp|AppUp\.IntelGraphicsExperience|RealtekSemiconductorCorp\.|NVIDIACorp\.|AdvancedMicroDevicesInc|DolbyLaboratories\.|WavesAudio\.|SynapticsIncorporated\.|ELANMicroelectronics|IntelCorp\.|Intel\.)'
  $list=@($Packages -split '\|' | Where-Object { $_ -and $_.Trim() })
  if($list.Count -eq 0) { Write-Output 'Kaldirilacak paket yok.'; break }
  $admin=IsAdmin; $ok=0; $fail=0
  if($Provisioned -eq 'yes' -and -not $admin) { Write-Output 'Not: yeni kullanicilar icin kaldirma yonetici ister; yalnizca bu kullanicidan kaldirilacak.' }
  foreach($full in $list) {
   $full=$full.Trim(); $name=($full -split '_')[0]
   if($name -match $protect) { Write-Output ('KORUNAN PAKET, atlandi: '+$name); $fail++; Emit ([ordered]@{type='appx-removed';name=$name;ok=$false;reason='protected'}); continue }
   try {
    Remove-AppxPackage -Package $full -ErrorAction Stop
    Write-Output ('Kaldirildi: '+$name); $ok++
    $provDone=$false
    if($Provisioned -eq 'yes' -and $admin) {
     try { $pp=@(Get-AppxProvisionedPackage -Online -ErrorAction Stop | Where-Object { $_.DisplayName -eq $name })
           foreach($x in $pp) { Remove-AppxProvisionedPackage -Online -PackageName $x.PackageName -ErrorAction Stop | Out-Null; $provDone=$true }
           if($provDone) { Write-Output ('  yeni kullanicilar icin de kaldirildi: '+$name) } }
     catch { Write-Output ('  hazir paket kaldirilamadi: '+$_.Exception.Message) }
    }
    Emit ([ordered]@{type='appx-removed';name=$name;ok=$true;provisioned=$provDone;reason=''})
   } catch { Write-Output ('Kaldirilamadi: '+$name+' ('+$_.Exception.Message+')'); $fail++; Emit ([ordered]@{type='appx-removed';name=$name;ok=$false;reason=$_.Exception.Message}) }
  }
  Write-Output ('Kaldirilan: {0}, basarisiz/atlanan: {1}. Store uygulamalari Microsoft Store''dan yeniden kurulabilir.' -f $ok,$fail)
  if($fail -gt 0) { exit 2 }
 }
 'phantom-list' {
  # Su an bagli olmayan (Aygit Yoneticisi'nde gizli, genellikle kod 45 CM_PROB_PHANTOM) aygitlar.
  $all=@(Get-PnpDevice -ErrorAction SilentlyContinue | Where-Object { -not $_.Present })
  Write-Output ('Bagli olmayan aygit: '+$all.Count)
  $dates=@{}
  if($all.Count -gt 0) {
   try {
    foreach($pr in @($all | Get-PnpDeviceProperty -KeyName 'DEVPKEY_Device_LastArrivalDate','DEVPKEY_Device_LastRemovalDate' -ErrorAction SilentlyContinue)) {
     if($pr.Data) { $dates[$pr.InstanceId+'|'+$pr.KeyName]=SafeDateTime $pr.Data }
    }
   } catch { Write-Output ('UYARI: tarih ozellikleri okunamadi: '+$_.Exception.Message) }
  }
  $native=$true; try { AgfoNative } catch { $native=$false }
  foreach($d in $all) {
   $id=[string]$d.InstanceId
   $lw=''; if($native) { try { $lw=FileTimeDate ([AgfoNative]::LastWrite('SYSTEM\CurrentControlSet\Enum\'+$id)) } catch {} }
   $prob=0; try { $prob=[int]$d.Problem } catch {}
   Emit ([ordered]@{type='phantom';id=$id;name=[string]$d.FriendlyName;cls=[string]$d.Class;status=[string]$d.Status;problem=$prob;
     arrival=[string]$dates[$id+'|DEVPKEY_Device_LastArrivalDate'];removal=[string]$dates[$id+'|DEVPKEY_Device_LastRemovalDate'];regwrite=$lw})
  }
 }
 'phantom-remove' {
  RequireAdmin
  $list=@($InstanceIds -split '\|' | Where-Object { $_ -and $_.Trim() })
  if($list.Count -eq 0) { Write-Output 'Kaldirilacak aygit yok.'; break }
  $build=[int][Environment]::OSVersion.Version.Build
  $usePnputil=$build -ge 19041   # pnputil /remove-device: Windows 10 2004 ve sonrasi
  if(-not $usePnputil) { AgfoNative }
  $ok=0; $fail=0
  foreach($id in $list) {
   $id=$id.Trim()
   $dev=Get-PnpDevice -InstanceId $id -ErrorAction SilentlyContinue
   if(-not $dev) { Write-Output ('Zaten yok: '+$id); Emit ([ordered]@{type='phantom-removed';id=$id;ok=$true;reason='missing'}); continue }
   if($dev.Present) { Write-Output ('BAGLI AYGIT, atlandi: '+$id); $fail++; Emit ([ordered]@{type='phantom-removed';id=$id;ok=$false;reason='present'}); continue }
   if($usePnputil) {
    $out=& pnputil.exe /remove-device "$id" 2>&1 | Out-String
    $code=$LASTEXITCODE
   } else { $code=[AgfoNative]::Remove($id); $out='' }
   if($code -eq 0 -or $code -eq 3010) { Write-Output ('Kaldirildi: '+$dev.FriendlyName+' ['+$id+']'); $ok++; Emit ([ordered]@{type='phantom-removed';id=$id;ok=$true;reason=''}) }
   else { Write-Output ('Kaldirilamadi ('+$code+'): '+$id+' '+$out.Trim()); $fail++; Emit ([ordered]@{type='phantom-removed';id=$id;ok=$false;reason=('kod '+$code)}) }
  }
  Write-Output ('Kaldirilan: {0}, basarisiz/atlanan: {1}. Aygit yeniden takilirsa Windows onu yeni aygit olarak tanir.' -f $ok,$fail)
  if($fail -gt 0) { exit 2 }
 }
 'devices' {
  $bad=@(Get-CimInstance Win32_PnPEntity -Filter 'ConfigManagerErrorCode <> 0' -ErrorAction SilentlyContinue)
  Write-Output ('Sorunlu aygit sayisi: '+$bad.Count)
  foreach($d in $bad) {
   $hw=''; if($d.HardwareID) { $hw=@($d.HardwareID)[0] }
   Write-Output ('- {0} | kod {1} | {2}' -f $d.Name,$d.ConfigManagerErrorCode,$d.PNPDeviceID)
   Emit ([ordered]@{type='device';name=[string]$d.Name;code=[int]$d.ConfigManagerErrorCode;cls=[string]$d.PNPClass;id=[string]$d.PNPDeviceID;hwid=[string]$hw;status=[string]$d.Status})
  }
 }
 'drivers-list' {
  $list=@(Get-CimInstance Win32_PnPSignedDriver -ErrorAction SilentlyContinue | Where-Object { $_.DeviceName })
  Write-Output ('Kurulu aygit surucusu: '+$list.Count)
  foreach($d in $list) {
   Emit ([ordered]@{type='driver';name=[string]$d.DeviceName;cls=[string]$d.DeviceClass;ver=[string]$d.DriverVersion;date=(SafeDate $d.DriverDate);maker=[string]$d.DriverProviderName;inf=[string]$d.InfName;signed=[bool]$d.IsSigned;id=[string]$d.DeviceID})
  }
 }
 'driver-backup' {
  RequireAdmin
  if(-not $BackupPath) { throw 'Yedek klasoru secilmedi.' }
  New-Item -ItemType Directory -Path $BackupPath -Force | Out-Null
  & pnputil.exe /export-driver '*' $BackupPath
  if($LASTEXITCODE -ne 0) { throw 'Surucu yedegi olusturulamadi.' }
  $size=(Get-ChildItem -LiteralPath $BackupPath -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
  Write-Output ('Yedek boyutu: {0:N1} MB -> {1}' -f ($size/1MB),$BackupPath)
 }
 'app-scan' {
  & winget.exe upgrade --source winget --accept-source-agreements --disable-interactivity
  if($LASTEXITCODE -ne 0) { Write-Output ('WinGet sonuc kodu: '+$LASTEXITCODE); exit $LASTEXITCODE }
 }
 'app-update' {
  & winget.exe upgrade --all --source winget --accept-source-agreements --accept-package-agreements --disable-interactivity
  if($LASTEXITCODE -ne 0) { Write-Output ('WinGet guncelleme sonuc kodu: '+$LASTEXITCODE); exit $LASTEXITCODE }
 }
 'temp-preview' {
  $f=@(TempCandidates); $bytes=0L; foreach($item in $f) { $bytes += $item.Length }
  Write-Output ('7 gunden eski, yalnizca kullanici Temp kokundeki dosyalar: '+$f.Count)
  Write-Output ('Tahmini boyut: {0:N1} MB' -f ($bytes/1MB))
  $f | Select-Object -First 35 -ExpandProperty FullName
  if($f.Count -gt 35) { Write-Output ('... ve {0} dosya daha.' -f ($f.Count-35)) }
 }
 'temp-clean' {
  $f=@(TempCandidates); $deleted=0; $bytes=0L; $skipped=0
  foreach($item in $f) {
   try { Remove-Item -LiteralPath $item.FullName -Force -ErrorAction Stop; $deleted++; $bytes+=$item.Length }
   catch { $skipped++ }
  }
  Write-Output ('Silinen: {0} dosya, {1:N1} MB. Atlanan/kilitli: {2}.' -f $deleted,($bytes/1MB),$skipped)
  Write-Output 'Klasorler, sembolik baglantilar, indirilenler, tarayici profilleri ve geri donusum kutusu silinmedi.'
 }
 'component-analyze' { RunDism @('/Online','/Cleanup-Image','/AnalyzeComponentStore') }
 'component-clean'   { RunDism @('/Online','/Cleanup-Image','/StartComponentCleanup') }
 'health-scan'       { RunDism @('/Online','/Cleanup-Image','/ScanHealth') }
 'health-repair' {
  RequireAdmin
  & dism.exe /Online /Cleanup-Image /RestoreHealth
  if($LASTEXITCODE -notin @(0,3010)) { throw ('DISM onarimi basarisiz: '+$LASTEXITCODE) }
  $prev=[Console]::OutputEncoding
  [Console]::OutputEncoding=[System.Text.Encoding]::Unicode
  try { & sfc.exe /scannow | Where-Object { $_ -and $_.Trim() } }
  finally { [Console]::OutputEncoding=$prev }
  $sfc=$LASTEXITCODE
  if($sfc -notin @(0,1,2)) { throw ('SFC hata kodu: '+$sfc) }
  Write-Output ('SFC sonuc kodu: '+$sfc+'; CBS.log ayrintilarina bakin.')
  if(PendingReboot) { exit 3010 }
 }
 'system-info' {
  $os=Get-CimInstance Win32_OperatingSystem
  $cs=Get-CimInstance Win32_ComputerSystem
  Write-Output ('Bilgisayar : {0} ({1} {2})' -f $cs.Name,$cs.Manufacturer,$cs.Model)
  Write-Output ('Windows    : {0} | {1} (derleme {2})' -f $os.Caption,$os.Version,$os.BuildNumber)
  Write-Output ('Son acilis : {0}  (calisma suresi: {1:dd} gun {1:hh} saat)' -f $os.LastBootUpTime,((Get-Date)-$os.LastBootUpTime))
  Write-Output ('Bellek     : {0:N1} GB bos / {1:N1} GB toplam' -f ($os.FreePhysicalMemory/1MB),($os.TotalVisibleMemorySize/1MB))
  Write-Output 'Diskler    :'
  Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object {
   $pct= if($_.Size) { 100*$_.FreeSpace/$_.Size } else { 0 }
   Write-Output ('  {0} {1,-14} {2,8:N1} GB bos / {3,8:N1} GB  (%{4:N0} bos)' -f $_.DeviceID,$_.VolumeName,($_.FreeSpace/1GB),($_.Size/1GB),$pct)
  }
  Write-Output ('Bekleyen yeniden baslatma: '+$(if(PendingReboot){'EVET'}else{'hayir'}))
 }
 'restore-point' {
  RequireAdmin
  $before=@(Get-ComputerRestorePoint -ErrorAction SilentlyContinue).Count
  # Windows 8+ 24 saatte bir noktaya izin verir; ForceRestorePoint=yes iken SystemRestorePointCreationFrequency gecici olarak 0 yapilir ve sonra eski haline getirilir.
  $srKey='HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\SystemRestore'; $prevFreq=$null; $hadFreq=$false
  if($ForceRestorePoint -eq 'yes') {
   $cur=Get-ItemProperty -LiteralPath $srKey -Name SystemRestorePointCreationFrequency -ErrorAction SilentlyContinue
   if($cur) { $hadFreq=$true; $prevFreq=$cur.SystemRestorePointCreationFrequency }
   New-ItemProperty -LiteralPath $srKey -Name SystemRestorePointCreationFrequency -PropertyType DWord -Value 0 -Force | Out-Null
  }
  try { Checkpoint-Computer -Description 'AGFO Care - Bakim oncesi' -RestorePointType 'MODIFY_SETTINGS' -WarningAction SilentlyContinue }
  finally {
   if($ForceRestorePoint -eq 'yes') {
    if($hadFreq) { Set-ItemProperty -LiteralPath $srKey -Name SystemRestorePointCreationFrequency -Value $prevFreq } else { Remove-ItemProperty -LiteralPath $srKey -Name SystemRestorePointCreationFrequency -ErrorAction SilentlyContinue }
   }
  }
  $after=@(Get-ComputerRestorePoint -ErrorAction SilentlyContinue).Count
  if($after -gt $before) { Write-Output 'Sistem geri yukleme noktasi olusturuldu.' }
  else {
   Write-Output 'Yeni nokta OLUSTURULMADI: Sistem Korumasi kapali olabilir veya son 24 saat icinde zaten bir geri yukleme noktasi olusturulmus.'
   exit 2
  }
 }
 'recycle-paths' {
  # Program kaldirma sonrasi artik klasorleri KALICI SILMEZ; Geri Donusum Kutusu'na tasir (geri alinabilir).
  Add-Type -AssemblyName Microsoft.VisualBasic
  $list=@($Paths -split '\|' | Where-Object { $_ -and $_.Trim() })
  if($list.Count -eq 0) { Write-Output 'Tasinacak yol yok.'; break }
  $ok=0; $fail=0
  foreach($p in $list) {
   $p=$p.Trim()
   if(IsProtectedPath $p) { Write-Output ('KORUNAN YOL, atlandi: '+$p); $fail++; Emit ([ordered]@{type='recycle';path=$p;ok=$false;reason='protected'}); continue }
   try {
    if(Test-Path -LiteralPath $p -PathType Container) { [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($p,'OnlyErrorDialogs','SendToRecycleBin') }
    elseif(Test-Path -LiteralPath $p -PathType Leaf) { [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($p,'OnlyErrorDialogs','SendToRecycleBin') }
    else { Write-Output ('Zaten yok: '+$p); Emit ([ordered]@{type='recycle';path=$p;ok=$true;reason='missing'}); continue }
    Write-Output ('Geri donusume tasindi: '+$p); $ok++
    Emit ([ordered]@{type='recycle';path=$p;ok=$true;reason=''})
   } catch { Write-Output ('Tasinamadi: '+$p+' ('+$_.Exception.Message+')'); $fail++; Emit ([ordered]@{type='recycle';path=$p;ok=$false;reason=$_.Exception.Message}) }
  }
  Write-Output ('Tasinan: {0}, basarisiz/atlanan: {1}' -f $ok,$fail)
  if($fail -gt 0) { exit 2 }
 }
}
