param(
 [Parameter(Mandatory=$true)][ValidateSet('driver-scan','driver-install','devices','drivers-list','driver-backup','app-scan','app-update','temp-preview','temp-clean','component-analyze','component-clean','health-scan','health-repair','system-info','restore-point','recycle-paths','driver-analyze','appx-list','appx-remove','phantom-list','phantom-remove','controller-list','controller-reset','bt-restart','tweak-read','tweak-write','dns-list','dns-flush','explorer-restart','vpn-status','hw-inventory','disk-health','pnp-list','pnp-action','overview','sensors','oem-info','nvidia-info','nvidia-uninstall','nvidia-remove-packages','sig-check','lenovo-scan','lenovo-install','dell-scan','dell-install','proc-list','proc-kill','svc-list','svc-action','startup-list','startup-set')][string]$Action,
 [string]$BackupPath = '',
 [string]$UpdateIds = '',
 [string]$Paths = '',
 [ValidateSet('yes','no')][string]$IncludeWU = 'yes',
 [string]$Packages = '',
 [ValidateSet('yes','no')][string]$Provisioned = 'no',
 [string]$InstanceIds = '',
 [ValidateSet('yes','no')][string]$ForceRestorePoint = 'no',
 [string]$PlanFile = '',
 [ValidateSet('','enable','disable','restart','remove')][string]$PnpOp = '',
 [ValidateSet('yes','no')][string]$IncludeBios = 'no',
 [string]$ItemsB64 = '',
 [ValidateSet('','start','stop','restart','auto','manual','disabled','enable','disable','kill','killtree')][string]$Op = ''
)
# AGFO System Care 4.0 gorev motoru.
# Insan icin satirlar ASCII Turkce; uygulamanin okudugu kayitlar '@@' onekli tek satir JSON olarak yazilir.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
# Windows PowerShell 5.1: PowerShell 7 modul yollari (PSModulePath'te ya da sistem ortaminda) 5.1'in Security / PackageManagement
# modullerini golgeleyip yuklenemez hale getirir. Yalnizca 5.1 yollari birakilir.
if ($PSVersionTable.PSEdition -ne 'Core') {
 $keep = @(($env:PSModulePath -split ';') | Where-Object { $_ -and $_ -notmatch '(?<!Windows)PowerShell\\(7|Modules)' -and $_ -notmatch '\\Documents\\PowerShell\\' })
 $sys = Join-Path $PSHOME 'Modules'
 if ($keep -notcontains $sys) { $keep += $sys }
 $usr = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'WindowsPowerShell\Modules'   # Install-Module -Scope CurrentUser buraya kurar
 if ($keep -notcontains $usr) { $keep = @($usr) + $keep }
 $env:PSModulePath = ($keep | Select-Object -Unique) -join ';'
}
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
function IsXboxDevice($d) {
 # Yalnizca Xbox kol / Xbox kablosuz adaptoru (Microsoft VID 045E + bilinen urun kimlikleri). Microsoft fare/klavye eslesmez.
 # care_core.controller_is_xbox ile ayni olcut.
 $id=[string]$d.InstanceId; $n=[string]$d.FriendlyName; $c=[string]$d.Class
 if($n -match 'Xbox') { return $true }
 if($c -eq 'XboxComposite' -or $c -eq 'XnaComposite') { return $true }
 if($id -match '^(?i)XBOXGIP\\') { return $true }
 $pids='02D1|02DD|02E0|02E3|02EA|02FD|02FF|0B00|0B05|0B12|0B13|0B20|0B22|02E6|02FE|0719|091E|02A9'
 if($id -match ('(?i)VID_045E&PID_('+$pids+')')) { return $true }
 if($id -match ('(?i)VID&02045E_PID&('+$pids+')')) { return $true }
 return $false
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

# ---------------------------------------------------------------- Ince ayarlar (3.7.0)
# Plan dosyasi: {"ops":[...]} (care_tweaks.py uretir). Kayit defteri .NET API ile 64 bit gorunumde okunur/yazilir
# (32 bit Python'dan acilan powershell'de HKLM\SOFTWARE yonlendirmesi olmasin diye).
function EmitD($obj) { Write-Output ('@@'+($obj | ConvertTo-Json -Compress -Depth 8)) }
function ReadPlan {
 if(-not $PlanFile -or -not (Test-Path -LiteralPath $PlanFile -PathType Leaf)) { Write-Output 'Plan dosyasi bulunamadi.'; exit 2 }
 $doc=ConvertFrom-Json ([IO.File]::ReadAllText($PlanFile,[Text.Encoding]::UTF8))
 return @($doc.ops)
}
function BaseKey([string]$hive) {
 $view=[Microsoft.Win32.RegistryView]::Default
 if([Environment]::Is64BitOperatingSystem) { $view=[Microsoft.Win32.RegistryView]::Registry64 }
 switch($hive) {
  'HKCU' { $h=[Microsoft.Win32.RegistryHive]::CurrentUser }
  'HKLM' { $h=[Microsoft.Win32.RegistryHive]::LocalMachine }
  'HKU'  { $h=[Microsoft.Win32.RegistryHive]::Users }
  default { throw ('gecersiz kayit kovani: '+$hive) }
 }
 return [Microsoft.Win32.RegistryKey]::OpenBaseKey($h,$view)
}
function CheckRegPath([string]$path) { if(-not $path -or $path.StartsWith('\') -or $path.Contains('..')) { throw ('gecersiz kayit yolu: '+$path) } }
function RegState([string]$hive,[string]$path,[string]$name) {
 CheckRegPath $path
 $st=[ordered]@{path=$path;key_exists=$false;exists=$false;value=$null;kind=''}
 $b=BaseKey $hive
 try {
  $k=$b.OpenSubKey($path,$false)
  if($null -eq $k) { return $st }
  try {
   $st.key_exists=$true
   if(@($k.GetValueNames()) -contains $name) {
    $st.exists=$true
    $raw=$k.GetValue($name,$null,[Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
    $st.kind=[string]$k.GetValueKind($name)
    switch($st.kind) {
     'DWord'       { $st.value=[string][BitConverter]::ToUInt32([BitConverter]::GetBytes([int32]$raw),0) }
     'QWord'       { $st.value=[string][BitConverter]::ToUInt64([BitConverter]::GetBytes([int64]$raw),0) }
     'Binary'      { $st.value=[Convert]::ToBase64String([byte[]]$raw) }
     'MultiString' { $st.value=@([string[]]$raw) }
     default       { $st.value=[string]$raw }
    }
   }
  } finally { $k.Close() }
 } finally { $b.Close() }
 return $st
}
function RegSubPaths([string]$hive,[string]$path) {
 CheckRegPath $path
 $b=BaseKey $hive
 try {
  $k=$b.OpenSubKey($path,$false)
  if($null -eq $k) { return @() }
  try { return @($k.GetSubKeyNames() | ForEach-Object { $path+'\'+$_ }) } finally { $k.Close() }
 } finally { $b.Close() }
}
function RegFirstMissing([string]$hive,[string]$path) {
 # Yazma oncesi: olusturulacak en ust anahtar (geri almada bosalirsa buraya kadar temizlenir).
 $b=BaseKey $hive
 try {
  $acc=''
  foreach($p in $path.Split('\')) {
   if($acc) { $acc=$acc+'\'+$p } else { $acc=$p }
   $k=$b.OpenSubKey($acc,$false)
   if($null -eq $k) { return $acc }
   $k.Close()
  }
  return ''
 } finally { $b.Close() }
}
function RegToValue([string]$kind,$value) {
 switch($kind) {
  'DWord'       { return [BitConverter]::ToInt32([BitConverter]::GetBytes([uint32]::Parse([string]$value)),0) }
  'QWord'       { return [BitConverter]::ToInt64([BitConverter]::GetBytes([uint64]::Parse([string]$value)),0) }
  'Binary'      { return [Convert]::FromBase64String([string]$value) }
  'MultiString' { return [string[]]@($value) }
  default       { return [string]$value }
 }
}
function RegPrune($b,[string]$path,[string]$root) {
 if(-not $path.StartsWith($root,[StringComparison]::OrdinalIgnoreCase)) { return }
 $cur=$path
 while($cur.Length -ge $root.Length) {
  $k=$b.OpenSubKey($cur,$false)
  if($null -ne $k) {
   $empty=($k.ValueCount -eq 0 -and $k.SubKeyCount -eq 0); $k.Close()
   if(-not $empty) { return }
   $b.DeleteSubKey($cur,$false)
  }
  if($cur -ieq $root) { return }
  $i=$cur.LastIndexOf('\'); if($i -lt 0) { return }
  $cur=$cur.Substring(0,$i)
 }
}
function RegApply([string]$hive,[string]$path,[string]$name,[string]$kind,$value,[string]$delkey,[string]$prune) {
 CheckRegPath $path
 $b=BaseKey $hive
 try {
  if($delkey) {
   if(-not $delkey.StartsWith('Software\Classes\CLSID\{',[StringComparison]::OrdinalIgnoreCase)) { throw ('anahtar silmeye izin yok: '+$delkey) }
   $p=$b.OpenSubKey($delkey,$false)
   if($null -ne $p) { $p.Close(); $b.DeleteSubKeyTree($delkey,$false) }
   return
  }
  if($null -eq $value) {
   $k=$b.OpenSubKey($path,$true)
   if($null -ne $k) { try { $k.DeleteValue($name,$false) } finally { $k.Close() } }
   if($prune) { RegPrune $b $path $prune }
   return
  }
  $k=$b.CreateSubKey($path)
  if($null -eq $k) { throw ('anahtar olusturulamadi: '+$path) }
  try { $k.SetValue($name,(RegToValue $kind $value),[Microsoft.Win32.RegistryValueKind]$kind) } finally { $k.Close() }
 } finally { $b.Close() }
}
function SvcState([string]$name) {
 $st=[ordered]@{exists=$false;start=''}
 $b=BaseKey 'HKLM'
 try {
  $k=$b.OpenSubKey('SYSTEM\CurrentControlSet\Services\'+$name,$false)
  if($null -ne $k) {
   try {
    $s=$k.GetValue('Start',$null)
    if($null -ne $s) {
     $st.exists=$true
     $d=[int]$k.GetValue('DelayedAutostart',0)
     switch([int]$s) { 0 { $st.start='Boot' } 1 { $st.start='System' } 2 { if($d -eq 1) { $st.start='AutomaticDelayed' } else { $st.start='Automatic' } } 3 { $st.start='Manual' } 4 { $st.start='Disabled' } default { $st.start=[string]$s } }
    }
   } finally { $k.Close() }
  }
 } finally { $b.Close() }
 return $st
}
function SvcSet([string]$name,[string]$start) {
 $map=@{Automatic='auto';AutomaticDelayed='delayed-auto';Manual='demand';Disabled='disabled'}
 if(-not $map.ContainsKey($start)) { throw ('gecersiz baslangic turu: '+$start) }
 if($name -notmatch '^[A-Za-z0-9_.\-]+$') { throw ('gecersiz hizmet adi: '+$name) }
 $ErrorActionPreference='Continue'   # sc.exe stderr satiri istisnaya donmesin; sonuc LASTEXITCODE ile denetlenir
 $out=& sc.exe config $name start= $map[$start] 2>&1
 if($LASTEXITCODE -ne 0) { throw ('sc config kod '+$LASTEXITCODE+': '+(($out | Out-String).Trim())) }
 if($start -eq 'Disabled') { try { Stop-Service -Name $name -Force -ErrorAction Stop -WarningAction SilentlyContinue } catch {} }
}
function TaskParts([string]$p) { $i=$p.LastIndexOf('\'); return @($p.Substring(0,$i+1),$p.Substring($i+1)) }
function TaskState([string]$p) {
 $st=[ordered]@{exists=$false;enabled=$null}
 $tp,$tn=TaskParts $p
 try { $t=Get-ScheduledTask -TaskPath $tp -TaskName $tn -ErrorAction Stop; $st.exists=$true; $st.enabled=([string]$t.State -ne 'Disabled') } catch {}
 return $st
}
function TaskSet([string]$p,[bool]$enabled) {
 if(-not $p.StartsWith('\Microsoft\Windows\')) { throw ('gorev yoluna izin yok: '+$p) }
 $tp,$tn=TaskParts $p
 if($enabled) { Enable-ScheduledTask -TaskPath $tp -TaskName $tn -ErrorAction Stop | Out-Null }
 else { Disable-ScheduledTask -TaskPath $tp -TaskName $tn -ErrorAction Stop | Out-Null }
}
$GuidRx='[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}'
function PowerActive {
 $o=(& powercfg.exe /getactivescheme 2>$null | Out-String)
 $m=[regex]::Match($o,$GuidRx)
 if($m.Success) { return $m.Value.ToLower() }
 return ''
}
function PowerSet([string]$guid) {
 if($guid -notmatch ('^'+$GuidRx+'$')) { throw ('gecersiz guc plani: '+$guid) }
 $list=(& powercfg.exe /list 2>$null | Out-String)
 if($list -notmatch [regex]::Escape($guid)) {
  # Ultimate Performance gizli sablondur: ayni GUID ile kopyalanir ki durum tespiti kesin olsun.
  if($guid -ieq 'e9a42b02-d5df-448d-aa00-03f14749eb61') { & powercfg.exe /duplicatescheme $guid $guid | Out-Null; if($LASTEXITCODE -ne 0) { throw ('powercfg duplicatescheme kod '+$LASTEXITCODE) } }
  else { throw ('guc plani bulunamadi: '+$guid) }
 }
 & powercfg.exe /setactive $guid | Out-Null
 if($LASTEXITCODE -ne 0) { throw ('powercfg setactive kod '+$LASTEXITCODE) }
}
function DnsState($a) {
 $guid=[string]$a.InterfaceGuid
 $static=@()
 $b=BaseKey 'HKLM'
 try {
  $k=$b.OpenSubKey('SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\'+$guid,$false)
  if($null -ne $k) { try { $ns=[string]$k.GetValue('NameServer',''); if($ns) { $static=@($ns -split '[,\s]+' | Where-Object { $_ }) } } finally { $k.Close() } }
 } finally { $b.Close() }
 $cur=@()
 try { $cur=@((Get-DnsClientServerAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -ErrorAction Stop).ServerAddresses) } catch {}
 return [ordered]@{alias=[string]$a.Name;guid=$guid;desc=[string]$a.InterfaceDescription;servers=$static;current=$cur}
}
function DnsAdapterByAlias([string]$alias) { return (Get-NetAdapter -Name $alias -ErrorAction Stop | Select-Object -First 1) }
function DnsSet([string]$alias,$servers) {
 $list=@($servers | Where-Object { $_ })
 foreach($s in $list) { if($s -notmatch '^\d{1,3}(\.\d{1,3}){3}$') { throw ('gecersiz DNS adresi: '+$s) } }
 if($list.Count -eq 0) { Set-DnsClientServerAddress -InterfaceAlias $alias -ResetServerAddresses -ErrorAction Stop }
 else { Set-DnsClientServerAddress -InterfaceAlias $alias -ServerAddresses ([string[]]$list) -ErrorAction Stop }
}
function OpNeedsAdmin($op) {
 if(@('svc','task','dns') -contains [string]$op.t) { return $true }
 return ([string]$op.t -eq 'reg' -and @('HKLM','HKU') -contains [string]$op.hive)
}

# ---- 4.0 donanim / genel bakis yardimcilari (yalnizca okuma; surucu kurmaz, yonetici gerekmez — disk sayaclari haric)
function Cim([string]$cls,[string]$ns='root\cimv2',[string]$filter='') {
 if(-not $ns) { $ns='root\cimv2' }
 try { if($filter) { return @(Get-CimInstance -Namespace $ns -ClassName $cls -Filter $filter -ErrorAction Stop) } else { return @(Get-CimInstance -Namespace $ns -ClassName $cls -ErrorAction Stop) } } catch { return @() }
}
function Txt($v) { if($null -eq $v) { return '' } ; return ([string]$v).Trim() }
function U16([object]$arr) { if(-not $arr) { return '' } ; return (-join ($arr | Where-Object { $_ -gt 0 } | ForEach-Object { [char]$_ })).Trim() }
function HwRec([string]$kind,[string]$name,$props) { $r=[ordered]@{type='hw';kind=$kind;name=$name}; foreach($k in $props.Keys) { $r[$k]=$props[$k] }; EmitD $r }

# ---- 4.1.1 uretici otomatik guncelleme: Lenovo (LSUClient, MIT, PowerShell Galerisi) ve Dell (Dell Command | Update CLI)
function EnsureLSUClient {
 if (Get-Module -ListAvailable -Name LSUClient) { Import-Module LSUClient -ErrorAction Stop; return }
 Write-Output 'LSUClient modulu (acik kaynak, MIT) PowerShell Galerisi''nden bu kullaniciya kuruluyor...'
 [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
 if (-not (Get-PackageProvider -ListAvailable -Name NuGet -ErrorAction SilentlyContinue | Where-Object { $_.Version -ge [version]'2.8.5.201' })) {
  Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Scope CurrentUser -Force | Out-Null
 }
 Install-Module -Name LSUClient -Scope CurrentUser -Force -AllowClobber -Repository PSGallery -ErrorAction Stop
 Import-Module LSUClient -ErrorAction Stop
}
function LsuRec($u) {
 $un=$false; try { $un=[bool]$u.Installer.Unattended } catch {}
 return [ordered]@{type='lsu';id=[string]$u.ID;title=[string]$u.Title;category=[string]$u.Category;ptype=[string]$u.Type;version=[string]$u.Version;severity=[string]$u.Severity;reboot=[string]$u.RebootType;unattended=$un;date=[string]$u.ReleaseDate}
}
function FindDcu {
 foreach($b in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) { if(-not $b) { continue }; $e=Join-Path $b 'Dell\CommandUpdate\dcu-cli.exe'; if(Test-Path -LiteralPath $e) { return $e } }
 return ''
}

# ---- 4.2 surecler / servisler / baslangic
function ItemsFromB64 { if(-not $ItemsB64) { return @() }; $e=[Text.UTF8Encoding]::new($false); $o=ConvertFrom-Json ($e.GetString([Convert]::FromBase64String($ItemsB64))); $r=@(); foreach($x in $o) { $r+=$x }; return $r }
$StartupApprovedKeys = @{
 'hkcu-run'='HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run'
 'hklm-run'='HKLM:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run'
 'hklm-run32'='HKLM:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run32'
 'user-folder'='HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder'
 'common-folder'='HKLM:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder'
}
function StartupEnabled([string]$scope,[string]$name) {
 try { $v=(Get-ItemProperty -LiteralPath $StartupApprovedKeys[$scope] -Name $name -ErrorAction Stop).$name; if($v -is [byte[]] -and $v.Length -gt 0) { return (($v[0] -band 1) -eq 0) } } catch {}
 return $true
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
 'controller-list' {
  # Xbox kollari ve bilesenleri (su an bagli olanlar) + Bluetooth radyo/hizmet durumu.
  $all=@(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { IsXboxDevice $_ })
  Write-Output ('Xbox kol bileseni: '+$all.Count)
  foreach($d in $all) {
   $prob=0; try { $prob=[int]$d.Problem } catch {}
   Write-Output ('- {0} | {1} | {2}' -f $d.FriendlyName,$d.Status,$d.InstanceId)
   Emit ([ordered]@{type='controller';id=[string]$d.InstanceId;name=[string]$d.FriendlyName;cls=[string]$d.Class;status=[string]$d.Status;problem=$prob})
  }
  $radios=@(Get-PnpDevice -Class Bluetooth -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -match '^(USB|PCI)\\' })
  $svc=Get-Service bthserv -ErrorAction SilentlyContinue
  $sv=''; if($svc) { $sv=[string]$svc.Status }
  Write-Output ('Bluetooth radyosu: {0} | bthserv: {1}' -f $radios.Count,$sv)
  Emit ([ordered]@{type='bt-radio';count=$radios.Count;ok=@($radios | Where-Object { $_.Status -eq 'OK' }).Count;service=$sv})
 }
 'controller-reset' {
  # Kol surucusunu sifirla: aygit kaydini kaldir ve donanimi yeniden tara. Yalnizca Xbox aygitlari kabul edilir.
  RequireAdmin
  $list=@($InstanceIds -split '\|' | Where-Object { $_ -and $_.Trim() })
  if($list.Count -eq 0) { Write-Output 'Sifirlanacak aygit yok.'; break }
  $build=[int][Environment]::OSVersion.Version.Build
  $usePnputil=$build -ge 19041
  if(-not $usePnputil) { AgfoNative }
  $ok=0; $fail=0
  foreach($id in $list) {
   $id=$id.Trim()
   $dev=Get-PnpDevice -InstanceId $id -ErrorAction SilentlyContinue
   if(-not $dev) { Write-Output ('Bulunamadi: '+$id); $fail++; Emit ([ordered]@{type='controller-reset';id=$id;ok=$false;reason='missing'}); continue }
   if(-not (IsXboxDevice $dev)) { Write-Output ('XBOX AYGITI DEGIL, atlandi: '+$id); $fail++; Emit ([ordered]@{type='controller-reset';id=$id;ok=$false;reason='not-xbox'}); continue }
   if($usePnputil) { $out=& pnputil.exe /remove-device "$id" 2>&1 | Out-String; $code=$LASTEXITCODE }
   else { $code=[AgfoNative]::Remove($id); $out='' }
   if($code -eq 0 -or $code -eq 3010) { Write-Output ('Kaldirildi: '+$dev.FriendlyName+' ['+$id+']'); $ok++; Emit ([ordered]@{type='controller-reset';id=$id;ok=$true;reason=''}) }
   else { Write-Output ('Kaldirilamadi ('+$code+'): '+$id+' '+$out.Trim()); $fail++; Emit ([ordered]@{type='controller-reset';id=$id;ok=$false;reason=('kod '+$code)}) }
  }
  Write-Output 'Donanim yeniden taraniyor...'
  if($usePnputil) { & pnputil.exe /scan-devices 2>&1 | Out-String | Write-Output }
  else { try { $null=(Get-CimInstance -Namespace root\cimv2 -ClassName Win32_PnPEntity -ErrorAction SilentlyContinue | Select-Object -First 1) } catch {} }
  Write-Output ('Sifirlanan: {0}, basarisiz/atlanan: {1}. USB ise kabloyu cikarip takin; Bluetooth ise gerekirse yeniden eslestirin.' -f $ok,$fail)
  if($fail -gt 0) { exit 2 }
 }
 'bt-restart' {
  # Bluetooth destek hizmetini yeniden baslatir; eslestirmeler silinmez.
  RequireAdmin
  $svc=Get-Service bthserv -ErrorAction SilentlyContinue
  if(-not $svc) { Write-Output 'Bluetooth destek hizmeti (bthserv) bu bilgisayarda yok.'; exit 2 }
  Restart-Service bthserv -Force
  Start-Sleep -Seconds 2
  $st=[string](Get-Service bthserv).Status
  Write-Output ('bthserv: '+$st+'. Eslestirmeler korunur; kol birkac saniye icinde yeniden baglanir.')
  Emit ([ordered]@{type='bt-service';status=$st})
  if($st -ne 'Running') { exit 2 }
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
 'tweak-read' {
  $ops=ReadPlan
  foreach($op in $ops) {
   $rec=[ordered]@{type='read';ref=[string]$op.ref}
   try {
    switch([string]$op.t) {
     'reg' {
      if($op.sub) { $rec.subs=@(RegSubPaths $op.hive $op.path | ForEach-Object { RegState $op.hive $_ $op.name }) }
      else { $st=RegState $op.hive $op.path $op.name; foreach($k in $st.Keys) { $rec[$k]=$st[$k] } }
     }
     'svc'   { $st=SvcState $op.name; foreach($k in $st.Keys) { $rec[$k]=$st[$k] } }
     'task'  { $st=TaskState $op.path; foreach($k in $st.Keys) { $rec[$k]=$st[$k] } }
     'power' { $rec.active=PowerActive }
     default { throw ('bilinmeyen okuma: '+$op.t) }
    }
   } catch { $rec.error=$_.Exception.Message }
   EmitD $rec
  }
  Write-Output ('Okunan ayar: '+$ops.Count)
 }
 'tweak-write' {
  $ops=ReadPlan
  foreach($op in $ops) { if(OpNeedsAdmin $op) { RequireAdmin; break } }
  $ok=0; $fail=0
  foreach($op in $ops) {
   $rec=[ordered]@{type='write';ref=$op.ref;ok=$false}
   try {
    switch([string]$op.t) {
     'reg' {
      $paths=@($op.path)
      if($op.sub) { $paths=@(RegSubPaths $op.hive $op.path) }
      $befores=@()
      foreach($p in $paths) {
       $bf=RegState $op.hive $p $op.name
       if($null -ne $op.value -and -not $op.delkey -and -not $bf.key_exists) { $bf.created_root=RegFirstMissing $op.hive $p }
       $befores+= ,$bf
       RegApply $op.hive $p $op.name ([string]$op.kind) $op.value ([string]$op.delkey) ([string]$op.prune)
      }
      if($op.sub) { $rec.before=[ordered]@{subs=$befores} } else { $rec.before=$befores[0] }
     }
     'svc' {
      $bf=SvcState $op.name
      if(-not $bf.exists) { throw ('hizmet bu sistemde yok: '+$op.name) }
      $rec.before=$bf; SvcSet $op.name $op.start
     }
     'task' {
      $bf=TaskState $op.path
      if(-not $bf.exists) { throw ('gorev bu sistemde yok: '+$op.path) }
      $rec.before=$bf; TaskSet $op.path ([bool]$op.enabled)
     }
     'power' { $rec.before=[ordered]@{active=PowerActive}; PowerSet $op.guid }
     'dns' {
      $a=DnsAdapterByAlias $op.alias
      $st=DnsState $a
      $rec.before=[ordered]@{servers=$st.servers}
      DnsSet $op.alias $op.servers
     }
     default { throw ('bilinmeyen islem: '+$op.t) }
    }
    $rec.ok=$true; $ok++
    Write-Output ('Tamam: '+$op.label+' ('+$op.t+')')
   } catch {
    $rec.error=$_.Exception.Message; $fail++
    Write-Output ('BASARISIZ: '+$op.label+' ('+$op.t+'): '+$_.Exception.Message)
   }
   EmitD $rec
  }
  Write-Output ('Uygulanan islem: {0}, basarisiz: {1}' -f $ok,$fail)
  if($fail -gt 0) { exit 2 }
 }
 'dns-list' {
  $n=0
  foreach($a in @(Get-NetAdapter -Physical -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq 'Up' })) {
   $st=DnsState $a; $st.type='dns-adapter'; EmitD $st; $n++
   $mode='DHCP'; if(@($st.servers).Count) { $mode='elle: '+(@($st.servers) -join ', ') }
   Write-Output ('{0}: {1} (gecerli: {2})' -f $st.alias,$mode,(@($st.current) -join ', '))
  }
  if($n -eq 0) { Write-Output 'Bagli fiziksel ag bagdastiricisi bulunamadi.' }
 }
 'dns-flush' {
  & ipconfig.exe /flushdns
  if($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
 }
 'explorer-restart' {
  Get-Process -Name explorer -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 2
  if(-not (Get-Process -Name explorer -ErrorAction SilentlyContinue)) { Start-Process -FilePath (Join-Path $env:SystemRoot 'explorer.exe') }
  Write-Output 'Gezgin yeniden baslatildi.'
 }
 'vpn-status' {
  # WireGuard tunel hizmetleri (WireGuardTunnel$<ad>) ve calisanlarin el sikisma / aktarim bilgisi (wg.exe yonetici ister).
  $wgDir=Join-Path $env:ProgramFiles 'WireGuard'
  $wgExe=Join-Path $wgDir 'wg.exe'
  $n=0
  foreach($svc in @(Get-Service -Name 'WireGuardTunnel$*' -ErrorAction SilentlyContinue)) {
   $name=$svc.Name.Substring('WireGuardTunnel$'.Length)
   $rec=[ordered]@{type='vpn';name=$name;status=[string]$svc.Status;dump=''}
   if($svc.Status -eq 'Running' -and (IsAdmin) -and (Test-Path -LiteralPath $wgExe)) {
    try { $ErrorActionPreference='Continue'; $rec.dump=((& $wgExe show $name dump 2>$null) -join "`n") } catch {} finally { $ErrorActionPreference='Stop' }
   }
   EmitD $rec; $n++
   Write-Output ('Tunel: {0} ({1})' -f $name,$svc.Status)
  }
  if($n -eq 0) { Write-Output 'Kurulu WireGuard tuneli yok.' }
 }
 'hw-inventory' {
  # Everest/AIDA64 tarzi ozet: tum bilgi Windows'un kendi WMI/CIM verisinden (ek surucu yok).
  foreach($o in (Cim Win32_OperatingSystem)) { HwRec 'os' (Txt $o.Caption) ([ordered]@{version=(Txt $o.Version);build=(Txt $o.BuildNumber);arch=(Txt $o.OSArchitecture);installed=(SafeDate $o.InstallDate);boot=(SafeDateTime $o.LastBootUpTime);ram_total=[int64]$o.TotalVisibleMemorySize*1KB;ram_free=[int64]$o.FreePhysicalMemory*1KB}) }
  foreach($c in (Cim Win32_ComputerSystem)) { HwRec 'computer' (Txt $c.Name) ([ordered]@{maker=(Txt $c.Manufacturer);model=(Txt $c.Model);domain=(Txt $c.Domain);ram=[int64]$c.TotalPhysicalMemory;pctype=[int]$c.PCSystemType}) }
  foreach($b in (Cim Win32_BaseBoard)) { HwRec 'board' (Txt $b.Product) ([ordered]@{maker=(Txt $b.Manufacturer);version=(Txt $b.Version)}) }
  foreach($b in (Cim Win32_BIOS)) { HwRec 'bios' (Txt $b.SMBIOSBIOSVersion) ([ordered]@{maker=(Txt $b.Manufacturer);date=(SafeDate $b.ReleaseDate)}) }
  foreach($p in (Cim Win32_Processor)) { HwRec 'cpu' (Txt $p.Name) ([ordered]@{maker=(Txt $p.Manufacturer);cores=[int]$p.NumberOfCores;threads=[int]$p.NumberOfLogicalProcessors;mhz=[int]$p.MaxClockSpeed;socket=(Txt $p.SocketDesignation);l2=[int]$p.L2CacheSize;l3=[int]$p.L3CacheSize;load=[int]$p.LoadPercentage;virt=[bool]$p.VirtualizationFirmwareEnabled}) }
  foreach($m in (Cim Win32_PhysicalMemory)) { HwRec 'ram' (Txt $m.DeviceLocator) ([ordered]@{size=[int64]$m.Capacity;mhz=[int]$m.ConfiguredClockSpeed;speed=[int]$m.Speed;maker=(Txt $m.Manufacturer);part=(Txt $m.PartNumber);bank=(Txt $m.BankLabel);smbtype=[int]$m.SMBIOSMemoryType}) }
  foreach($g in (Cim Win32_VideoController)) { HwRec 'gpu' (Txt $g.Name) ([ordered]@{driver=(Txt $g.DriverVersion);date=(SafeDate $g.DriverDate);vram=[int64]$g.AdapterRAM;res=('{0}x{1}' -f $g.CurrentHorizontalResolution,$g.CurrentVerticalResolution);hz=[int]$g.CurrentRefreshRate}) }
  $pd=Cim MSFT_PhysicalDisk 'root\Microsoft\Windows\Storage'
  if($pd.Count) { foreach($d in $pd) { HwRec 'disk' (Txt $d.FriendlyName) ([ordered]@{size=[int64]$d.Size;media=[int]$d.MediaType;bus=[int]$d.BusType;health=[int]$d.HealthStatus;serial=''}) } }
  else { foreach($d in (Cim Win32_DiskDrive)) { HwRec 'disk' (Txt $d.Model) ([ordered]@{size=[int64]$d.Size;media=0;bus=0;health=0;serial=''}) } }
  foreach($v in (Cim Win32_LogicalDisk '' 'DriveType=3')) { HwRec 'volume' (Txt $v.DeviceID) ([ordered]@{label=(Txt $v.VolumeName);fs=(Txt $v.FileSystem);size=[int64]$v.Size;free=[int64]$v.FreeSpace}) }
  foreach($n in (Cim Win32_NetworkAdapter '' 'PhysicalAdapter=True')) { HwRec 'net' (Txt $n.Name) ([ordered]@{maker=(Txt $n.Manufacturer);speed=[int64]$n.Speed;connected=([int]$n.NetConnectionStatus -eq 2);conn=(Txt $n.NetConnectionID)}) }
  foreach($a in (Cim Win32_SoundDevice)) { HwRec 'audio' (Txt $a.Name) ([ordered]@{maker=(Txt $a.Manufacturer);status=(Txt $a.Status)}) }
  foreach($m in (Cim WmiMonitorID 'root\wmi')) { HwRec 'monitor' (U16 $m.UserFriendlyName) ([ordered]@{maker=(U16 $m.ManufacturerName);year=[int]$m.YearOfManufacture}) }
  foreach($b in (Cim Win32_Battery)) {
   $full=0; $design=0
   foreach($f in (Cim BatteryFullChargedCapacity 'root\wmi')) { $full=[int64]$f.FullChargedCapacity }
   foreach($f in (Cim BatteryStaticData 'root\wmi')) { $design=[int64]$f.DesignedCapacity }
   HwRec 'battery' (Txt $b.Name) ([ordered]@{charge=[int]$b.EstimatedChargeRemaining;status=[int]$b.BatteryStatus;full=$full;design=$design})
  }
  Write-Output 'Donanim bilgisi okundu.'
 }
 'disk-health' {
  # SMART benzeri saglik: Windows depolama sayaclari (sicaklik, asinma, calisma saati, hata). Sayaclarin bir kismi yonetici ister.
  $admin=IsAdmin
  foreach($d in @(Get-PhysicalDisk -ErrorAction SilentlyContinue)) {
   $rec=[ordered]@{type='disk';name=(Txt $d.FriendlyName);serial=(Txt $d.SerialNumber);media=(Txt $d.MediaType);bus=(Txt $d.BusType);size=[int64]$d.Size;health=(Txt $d.HealthStatus);op=((@($d.OperationalStatus) | ForEach-Object { [string]$_ }) -join ', ');temp=$null;tempmax=$null;wear=$null;hours=$null;rerr=$null;werr=$null;admin=[bool]$admin}
   try {
    $c=$d | Get-StorageReliabilityCounter -ErrorAction Stop
    if($c) { $rec.temp=$c.Temperature; $rec.tempmax=$c.TemperatureMax; $rec.wear=$c.Wear; $rec.hours=$c.PowerOnHours; $rec.rerr=$c.ReadErrorsUncorrected; $rec.werr=$c.WriteErrorsUncorrected }
   } catch {}
   EmitD $rec
   Write-Output ('Disk: {0} — {1}' -f $rec.name,$rec.health)
  }
 }
 'pnp-list' {
  # Aygit yoneticisi: takili tum aygitlar (sorun kodu, sinif, surucu bilgisi).
  $drv=@{}
  foreach($d in (Cim Win32_PnPSignedDriver)) { if($d.DeviceID) { $drv[[string]$d.DeviceID]=$d } }
  $n=0
  foreach($e in (Cim Win32_PnPEntity)) {
   $id=[string]$e.PNPDeviceID; $s=$drv[$id]
   EmitD ([ordered]@{type='pnp';name=(Txt $e.Name);cls=(Txt $e.PNPClass);id=$id;code=[int]$e.ConfigManagerErrorCode;status=(Txt $e.Status);maker=(Txt $e.Manufacturer);present=[bool]$e.Present;ver=$(if($s){Txt $s.DriverVersion}else{''});date=$(if($s){SafeDate $s.DriverDate}else{''});inf=$(if($s){Txt $s.InfName}else{''});provider=$(if($s){Txt $s.DriverProviderName}else{''})})
   $n++
  }
  Write-Output ('Aygit sayisi: '+$n)
 }
 'pnp-action' {
  RequireAdmin
  $ids=@($InstanceIds -split '\|' | Where-Object { $_ })
  if(-not $ids.Count -or -not $PnpOp) { Write-Output 'Aygit ya da islem belirtilmedi.'; exit 2 }
  $fail=0
  foreach($id in $ids) {
   try {
    switch($PnpOp) {
     'enable'  { Enable-PnpDevice -InstanceId $id -Confirm:$false -ErrorAction Stop }
     'disable' { Disable-PnpDevice -InstanceId $id -Confirm:$false -ErrorAction Stop }
     'restart' { Disable-PnpDevice -InstanceId $id -Confirm:$false -ErrorAction Stop; Start-Sleep -Milliseconds 800; Enable-PnpDevice -InstanceId $id -Confirm:$false -ErrorAction Stop }
     'remove'  { $o=& pnputil.exe /remove-device $id 2>&1; if($LASTEXITCODE -ne 0) { throw ($o -join ' ') } }
    }
    Write-Output ('Tamam: {0} ({1})' -f $id,$PnpOp)
    Emit ([ordered]@{type='pnpres';id=$id;op=$PnpOp;ok=$true})
   } catch { $fail++; Write-Output ('HATA: {0} — {1}' -f $id,$_.Exception.Message); Emit ([ordered]@{type='pnpres';id=$id;op=$PnpOp;ok=$false;err=[string]$_.Exception.Message}) }
  }
  if($fail) { exit 1 }
 }
 'overview' {
  # Genel bakis kartlari: her kayit {type='ov';key;state=ok|warn|bad|info;value;detail}
  function Ov([string]$key,[string]$state,[string]$value,[string]$detail='') { Emit ([ordered]@{type='ov';key=$key;state=$state;value=$value;detail=$detail}) }
  $os=@(Cim Win32_OperatingSystem)[0]
  if($os) {
   $up=(Get-Date)-$os.LastBootUpTime
   Ov 'uptime' $(if($up.TotalDays -gt 14){'warn'}else{'ok'}) ('{0:N0} gun {1} saat' -f [math]::Floor($up.TotalDays),$up.Hours) (SafeDateTime $os.LastBootUpTime)
   $pct=[math]::Round(100*(1-$os.FreePhysicalMemory/[double]$os.TotalVisibleMemorySize))
   Ov 'memory' $(if($pct -ge 90){'bad'}elseif($pct -ge 80){'warn'}else{'ok'}) ('%{0} dolu' -f $pct) ('{0:N1} / {1:N1} GB' -f (($os.TotalVisibleMemorySize-$os.FreePhysicalMemory)/1MB),($os.TotalVisibleMemorySize/1MB))
  }
  foreach($v in (Cim Win32_LogicalDisk '' 'DriveType=3')) {
   if(-not $v.Size) { continue }
   $free=100*$v.FreeSpace/$v.Size
   Ov ('volume:'+$v.DeviceID) $(if($free -lt 7){'bad'}elseif($free -lt 15){'warn'}else{'ok'}) ('%{0:N0} bos' -f $free) ('{0} {1:N0} GB bos / {2:N0} GB' -f $v.DeviceID,($v.FreeSpace/1GB),($v.Size/1GB))
  }
  Ov 'reboot' $(if(PendingReboot){'warn'}else{'ok'}) $(if(PendingReboot){'Yeniden baslatma bekliyor'}else{'Gerekmiyor'})
  try {
   $mp=Get-MpComputerStatus -ErrorAction Stop
   $sig=[int]$mp.AntivirusSignatureAge
   $st= if(-not $mp.RealTimeProtectionEnabled) {'bad'} elseif($sig -gt 7) {'warn'} else {'ok'}
   Ov 'defender' $st $(if($mp.RealTimeProtectionEnabled){'Gercek zamanli koruma acik'}else{'Gercek zamanli koruma KAPALI'}) ('Imza yasi: {0} gun' -f $sig)
  } catch { Ov 'defender' 'info' 'Okunamadi' 'Baska bir antivirus kullaniliyor olabilir' }
  try {
   $off=@(Get-NetFirewallProfile -ErrorAction Stop | Where-Object { -not $_.Enabled } | ForEach-Object { [string]$_.Name })
   Ov 'firewall' $(if($off.Count){'bad'}else{'ok'}) $(if($off.Count){'Kapali profil: '+($off -join ', ')}else{'Tum profiller acik'})
  } catch { Ov 'firewall' 'info' 'Okunamadi' }
  try {
   $bl=@(Get-BitLockerVolume -MountPoint $env:SystemDrive -ErrorAction Stop)[0]
   Ov 'bitlocker' $(if([string]$bl.ProtectionStatus -eq 'On'){'ok'}else{'info'}) $(if([string]$bl.ProtectionStatus -eq 'On'){'Sistem diski sifreli'}else{'Sistem diski sifreli degil'})
  } catch { Ov 'bitlocker' 'info' $(if(IsAdmin){'Okunamadi'}else{'Yonetici gerekir'}) }
  try {
   $hf=@(Get-HotFix -ErrorAction Stop | Where-Object { $_.InstalledOn } | Sort-Object InstalledOn -Descending)[0]
   if($hf) { $age=((Get-Date)-[datetime]$hf.InstalledOn).Days; Ov 'winupdate' $(if($age -gt 45){'warn'}else{'ok'}) ('Son guncelleme {0} gun once' -f $age) ('{0} ({1})' -f $hf.HotFixID,(SafeDate $hf.InstalledOn)) }
  } catch { Ov 'winupdate' 'info' 'Okunamadi' }
  $bad=@(Cim Win32_PnPEntity '' 'ConfigManagerErrorCode <> 0')
  Ov 'devices' $(if($bad.Count){'warn'}else{'ok'}) $(if($bad.Count){'{0} sorunlu aygit' -f $bad.Count}else{'Sorunlu aygit yok'})
  try {
   $dd=@(Get-PhysicalDisk -ErrorAction Stop)
   $nh=@($dd | Where-Object { [string]$_.HealthStatus -ne 'Healthy' })
   Ov 'disks' $(if($nh.Count){'bad'}else{'ok'}) $(if($nh.Count){'{0} disk saglikli degil' -f $nh.Count}else{'{0} disk saglikli' -f $dd.Count})
  } catch { Ov 'disks' 'info' 'Okunamadi' }
  Write-Output 'Genel bakis okundu.'
 }
 'sensors' {
  # Istege bagli: LibreHardwareMonitor calisiyorsa WMI saglayicisindan (root\LibreHardwareMonitor) sicaklik / fan / voltaj okunur.
  $hw=@{}
  foreach($h in (Cim Hardware 'root\LibreHardwareMonitor')) { $hw[[string]$h.Identifier]=[string]$h.Name }
  $n=0
  foreach($x in (Cim Sensor 'root\LibreHardwareMonitor')) {
   if(@('Temperature','Fan','Voltage','Load','Power','Clock') -notcontains [string]$x.SensorType) { continue }
   $hname=$hw[[string]$x.Parent]; if(-not $hname) { $hname=[string]$x.Parent }
   Emit ([ordered]@{type='sensor';hardware=$hname;name=(Txt $x.Name);stype=[string]$x.SensorType;value=[double]$x.Value})
   $n++
  }
  if(-not $n) { Write-Output 'Sensor verisi yok: LibreHardwareMonitor calismiyor ya da WMI saglayicisi kapali.'; exit 3 }
  Write-Output ('Sensor sayisi: '+$n)
 }
 'oem-info' {
  # Uretici destegi: model, seri numarasi, SKU, anakart (ozel toplama masaustu icin), dizustu mu.
  $cs=@(Cim Win32_ComputerSystem)[0]; $bios=@(Cim Win32_BIOS)[0]; $bb=@(Cim Win32_BaseBoard)[0]; $csp=@(Cim Win32_ComputerSystemProduct)[0]
  $ch=@(Cim Win32_SystemEnclosure)[0]
  $nb=$false; if($ch -and $ch.ChassisTypes) { foreach($t in @($ch.ChassisTypes)) { if(@(8,9,10,11,12,14,18,21,30,31,32) -contains [int]$t) { $nb=$true } } }
  EmitD ([ordered]@{type='oem';maker=(Txt $cs.Manufacturer);model=(Txt $cs.Model);family=(Txt $csp.Version);sku=(Txt $cs.SystemSKUNumber);serial=(Txt $bios.SerialNumber);board_maker=(Txt $bb.Manufacturer);board=(Txt $bb.Product);bios=(Txt $bios.SMBIOSBIOSVersion);notebook=$nb})
  Write-Output ('Uretici: {0} | Model: {1}' -f (Txt $cs.Manufacturer),(Txt $cs.Model))
 }
 'nvidia-info' {
  # NVIDIA: GPU, surucu surumu, DCH, NVIDIA kaldiricisi, NVIDIA programlari ve surucu paketleri; 7-Zip ve DDU yollari.
  $os=@(Cim Win32_OperatingSystem)[0]
  $ch=@(Cim Win32_SystemEnclosure)[0]
  $nb=$false; if($ch -and $ch.ChassisTypes) { foreach($t in @($ch.ChassisTypes)) { if(@(8,9,10,11,12,14,18,21,30,31,32) -contains [int]$t) { $nb=$true } } }
  $dch=$false; try { $dch=[bool](Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\nvlddmkm' -Name 'DCHUVen' -ErrorAction Stop) } catch {}
  $nvi2=Test-Path -LiteralPath (Join-Path $env:ProgramFiles 'NVIDIA Corporation\Installer2\InstallerCore\NVI2.DLL')
  $sz=''; try { $sz=[string](Get-ItemProperty -Path 'HKLM:\SOFTWARE\7-Zip' -Name Path -ErrorAction Stop).Path; if($sz) { $sz=Join-Path $sz '7z.exe' } } catch {}
  if(-not $sz -or -not (Test-Path -LiteralPath $sz)) { $c=Join-Path $env:ProgramFiles '7-Zip\7z.exe'; $sz=$(if(Test-Path -LiteralPath $c){$c}else{''}) }
  $ddu=''
  $roots=@('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall','HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall','HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall')
  $apps=@()
  foreach($r in $roots) {
   foreach($k in @(Get-ChildItem -LiteralPath $r -ErrorAction SilentlyContinue)) {
    try { $p=Get-ItemProperty -LiteralPath $k.PSPath -ErrorAction Stop } catch { continue }
    $dn=[string]$p.DisplayName; if(-not $dn) { continue }
    if($dn -eq 'Display Driver Uninstaller') { $loc=[string]$p.InstallLocation; if(-not $loc -and $p.DisplayIcon) { $loc=Split-Path ([string]$p.DisplayIcon).Trim('"') -Parent }; if($loc) { $e=Join-Path $loc 'Display Driver Uninstaller.exe'; if(Test-Path -LiteralPath $e) { $ddu=$e } } }
    if([string]$p.Publisher -like 'NVIDIA*') { $apps+=[ordered]@{name=$dn;version=[string]$p.DisplayVersion} }
   }
  }
  if(-not $ddu) { $e=Join-Path $env:ProgramFiles 'Display Driver Uninstaller\Display Driver Uninstaller.exe'; if(Test-Path -LiteralPath $e) { $ddu=$e } }
  $gpus=@()
  foreach($g in (Cim Win32_VideoController)) { $gpus+=[ordered]@{name=(Txt $g.Name);driver=(Txt $g.DriverVersion);date=(SafeDate $g.DriverDate);pnp=(Txt $g.PNPDeviceID);nvidia=([string]$g.PNPDeviceID -match 'VEN_10DE')} }
  $pk=@()
  foreach($d in (Cim Win32_PnPSignedDriver)) { if([string]$d.DriverProviderName -like 'NVIDIA*' -and $d.InfName) { $pk+=[ordered]@{inf=[string]$d.InfName;name=(Txt $d.DeviceName);cls=(Txt $d.DeviceClass);ver=(Txt $d.DriverVersion)} } }
  EmitD ([ordered]@{type='nvinfo';gpus=$gpus;notebook=$nb;dch=$dch;build=[int]$os.BuildNumber;x64=[Environment]::Is64BitOperatingSystem;nvi2=$nvi2;sevenzip=$sz;ddu=$ddu;apps=$apps;packages=$pk})
  Write-Output ('Ekran kartlari: {0}' -f (($gpus | ForEach-Object { $_.name }) -join ', '))
 }
 'nvidia-uninstall' {
  # NVIDIA'nin kendi kaldiricisi (belgelenmis sessiz parametreler): Display.Driver -silent -n
  RequireAdmin
  $dll=Join-Path $env:ProgramFiles 'NVIDIA Corporation\Installer2\InstallerCore\NVI2.DLL'
  if(-not (Test-Path -LiteralPath $dll)) { Write-Output 'NVIDIA kaldiricisi (NVI2) bulunamadi; "Surucu paketlerini sil" ya da DDU kullanin.'; exit 2 }
  $p=Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\rundll32.exe') -ArgumentList ('"'+$dll+'",UninstallPackage Display.Driver'),'-silent','-n' -Wait -PassThru
  Write-Output ('NVIDIA kaldiricisi cikis kodu: '+$p.ExitCode+' (yeniden baslatma gerekebilir)')
  exit $p.ExitCode
 }
 'nvidia-remove-packages' {
  # Windows surucu deposundaki NVIDIA ekran surucu paketlerini kaldirir (pnputil); aygit Microsoft Temel Goruntu Bagdastiricisina doner.
  RequireAdmin
  $infs=@(Cim Win32_PnPSignedDriver | Where-Object { [string]$_.DriverProviderName -like 'NVIDIA*' -and [string]$_.DeviceClass -eq 'DISPLAY' -and $_.InfName } | ForEach-Object { [string]$_.InfName } | Sort-Object -Unique)
  if(-not $infs.Count) { Write-Output 'Kaldirilacak NVIDIA ekran surucu paketi yok.'; exit 0 }
  $fail=0
  foreach($inf in $infs) {
   if($inf -notmatch '^oem\d+\.inf$') { Write-Output ('Atlandi (oem paketi degil): '+$inf); continue }
   $o=& pnputil.exe /delete-driver $inf /uninstall /force 2>&1
   Write-Output ($o -join "`n")
   if($LASTEXITCODE -ne 0) { $fail++ }
  }
  Write-Output 'Yeniden baslatma onerilir.'
  if($fail) { exit 1 }
 }
 'sig-check' {
  # Indirilen dosyanin Authenticode imzasi (yalnizca gecerli ve beklenen yayinciysa calistirilir).
  # Get-AuthenticodeSignature yuklenemezse (bozuk modul yolu) ayni denetim WinVerifyTrust ile yapilir.
  foreach($f in @($Paths -split '\|' | Where-Object { $_ })) {
   $status=''; $subject=''
   try {
    $s=Get-AuthenticodeSignature -LiteralPath $f -ErrorAction Stop
    $status=[string]$s.Status; if($s.SignerCertificate) { $subject=[string]$s.SignerCertificate.Subject }
   } catch {
    try { $subject=[string]([Security.Cryptography.X509Certificates.X509Certificate]::CreateFromSignedFile($f)).Subject } catch { $subject='' }
    if(-not ('AgfoTrust' -as [type])) {
     Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public static class AgfoTrust {
 [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct FILE_INFO { public uint cbStruct; public string path; public IntPtr hFile; public IntPtr known; }
 [StructLayout(LayoutKind.Sequential)] struct DATA { public uint cbStruct; public IntPtr policy; public IntPtr sip; public uint ui; public uint revoke; public uint choice; public IntPtr file; public uint state; public IntPtr hState; public IntPtr url; public uint prov; public uint ctx; public IntPtr sig; }
 [DllImport("wintrust.dll", CharSet=CharSet.Unicode)] static extern int WinVerifyTrust(IntPtr hwnd, ref Guid action, ref DATA data);
 public static int Check(string path) {
  var fi = new FILE_INFO(); fi.cbStruct = (uint)Marshal.SizeOf(typeof(FILE_INFO)); fi.path = path;
  IntPtr pfi = Marshal.AllocHGlobal(Marshal.SizeOf(fi)); Marshal.StructureToPtr(fi, pfi, false);
  var d = new DATA(); d.cbStruct = (uint)Marshal.SizeOf(typeof(DATA)); d.ui = 2; d.revoke = 0; d.choice = 1; d.file = pfi; d.state = 0;
  var g = new Guid("00AAC56B-CD44-11d0-8CC2-00C04FC295EE");
  try { return WinVerifyTrust(IntPtr.Zero, ref g, ref d); } finally { Marshal.FreeHGlobal(pfi); }
 }
}
'@
    }
    $rc=[AgfoTrust]::Check($f)
    $status=$(if($rc -eq 0){'Valid'}elseif(-not $subject){'NotSigned'}else{'HashMismatch'})
   }
   EmitD ([ordered]@{type='sig';path=$f;status=$status;subject=$subject})
   Write-Output ('Imza: {0} — {1}' -f $status,$(if($subject){$subject}else{'-'}))
  }
 }
 'lenovo-scan' {
  # Lenovo: bu bilgisayara uygun, kurulu olmayan surucu/BIOS/yazilim paketleri (Lenovo'nun kendi katalogundan).
  EnsureLSUClient
  $n=0
  foreach($u in @(Get-LSUpdate -ErrorAction Stop)) { EmitD (LsuRec $u); $n++ }
  Write-Output ('Lenovo guncellemesi: '+$n)
 }
 'lenovo-install' {
  # Secili paketler (yalnizca sessiz kurulabilenler) kurulur; BIOS istege bagli.
  RequireAdmin
  EnsureLSUClient
  $ids=@($UpdateIds -split ',' | Where-Object { $_ })
  $all=@(Get-LSUpdate -ErrorAction Stop | Where-Object { $_.Installer.Unattended })
  if($IncludeBios -ne 'yes') { $all=@($all | Where-Object { [string]$_.Type -ne 'BIOS' -and [string]$_.Category -notmatch 'BIOS|UEFI' }) }
  if($ids.Count) { $all=@($all | Where-Object { $ids -contains [string]$_.ID }) }
  if(-not $all.Count) { Write-Output 'Kurulacak (sessiz kurulabilen) Lenovo guncellemesi yok.'; exit 0 }
  Write-Output ('Kurulacak paket: '+$all.Count)
  $fail=0
  foreach($r in @($all | Install-LSUpdate -Verbose 4>&1)) {
   if($r -is [System.Management.Automation.VerboseRecord]) { Write-Output ([string]$r.Message); continue }
   $ok=$false; try { $ok=[bool]$r.Success } catch {}
   if(-not $ok) { $fail++ }
   EmitD ([ordered]@{type='lsures';id=[string]$r.ID;title=[string]$r.Title;ok=$ok;pending=[string]$r.PendingAction;reason=[string]$r.FailureReason})
   Write-Output ('{0}: {1}' -f [string]$r.Title,$(if($ok){'tamam'}else{'HATA '+[string]$r.FailureReason}))
  }
  if($fail) { exit 1 }
 }
 'dell-scan' {
  $dcu=FindDcu
  if(-not $dcu) { Write-Output 'Dell Command | Update kurulu degil.'; exit 3 }
  $log=Join-Path $env:TEMP 'agfo-dcu-scan'
  & $dcu /scan ('-outputLog='+$log+'.log') ('-report='+$log) 2>&1 | ForEach-Object { Write-Output ([string]$_) }
  $code=$LASTEXITCODE
  foreach($x in @(Get-ChildItem -LiteralPath $log -Filter *.xml -ErrorAction SilentlyContinue)) {
   try { [xml]$doc=Get-Content -LiteralPath $x.FullName -Raw; foreach($u in @($doc.updates.update)) { EmitD ([ordered]@{type='dcu';name=[string]$u.name;version=[string]$u.version;category=[string]$u.category;urgency=[string]$u.urgency;size=[string]$u.size}) } } catch {}
  }
  exit $code
 }
 'dell-install' {
  RequireAdmin
  $dcu=FindDcu
  if(-not $dcu) { Write-Output 'Dell Command | Update kurulu degil.'; exit 3 }
  $args2=@('/applyUpdates','-silent','-reboot=disable','-outputLog='+(Join-Path $env:TEMP 'agfo-dcu-apply.log'))
  if($IncludeBios -ne 'yes') { $args2+='-updateType=driver,firmware,application,utility,others' }
  & $dcu @args2 2>&1 | ForEach-Object { Write-Output ([string]$_) }
  exit $LASTEXITCODE
 }
 'proc-list' {
  # Calisan surecler: CPU (1 sn ornekleme), bellek, pencere basligi, yol, yayinci, oturum.
  $cores=[Environment]::ProcessorCount
  $t0=@{}; foreach($p in @(Get-Process -ErrorAction SilentlyContinue)) { try { $t0[$p.Id]=$p.TotalProcessorTime.TotalMilliseconds } catch {} }
  Start-Sleep -Milliseconds 1000
  $n=0
  foreach($p in @(Get-Process -ErrorAction SilentlyContinue)) {
   $cpu=0.0; try { if($t0.ContainsKey($p.Id)) { $cpu=[math]::Round(($p.TotalProcessorTime.TotalMilliseconds-$t0[$p.Id])/(10.0*$cores),1) } } catch {}
   $path=''; $company=''; $desc=''
   try { $path=[string]$p.Path } catch {}
   try { $company=[string]$p.Company; $desc=[string]$p.Description } catch {}
   EmitD ([ordered]@{type='proc';pid=$p.Id;name=[string]$p.ProcessName;cpu=[math]::Max(0,$cpu);mem=[int64]$p.WorkingSet64;title=[string]$p.MainWindowTitle;path=$path;company=$company;desc=$desc;session=[int]$p.SessionId})
   $n++
  }
  Write-Output ('Surec sayisi: '+$n)
 }
 'proc-kill' {
  # Secili surecleri sonlandirir (kill: yalniz surec, killtree: alt surecleriyle). Kritik surecler reddedilir.
  $crit=@('system','idle','registry','smss','csrss','wininit','winlogon','services','lsass','lsaiso','svchost','fontdrvhost','dwm','memory compression','secure system','msmpeng')
  $fail=0
  foreach($x in (ItemsFromB64)) {
   $id=[int]$x.pid
   try { $p=Get-Process -Id $id -ErrorAction Stop } catch { Write-Output ('Zaten kapanmis: '+$id); continue }
   if($crit -contains $p.ProcessName.ToLower() -or $id -le 4) { Write-Output ('Kritik surec, atlandi: {0} ({1})' -f $p.ProcessName,$id); continue }
   if($x.name -and $p.ProcessName -ne [string]$x.name) { Write-Output ('PID baska bir surece gecmis, atlandi: '+$id); continue }
   try {
    if($Op -eq 'killtree') { $o=& taskkill.exe /PID $id /T /F 2>&1; if($LASTEXITCODE -ne 0) { throw ($o -join ' ') } }
    else { Stop-Process -Id $id -Force -ErrorAction Stop }
    Write-Output ('Sonlandirildi: {0} ({1})' -f $p.ProcessName,$id)
    Emit ([ordered]@{type='killres';pid=$id;ok=$true})
   } catch { $fail++; Write-Output ('HATA: {0} ({1}) — {2}' -f $p.ProcessName,$id,$_.Exception.Message); Emit ([ordered]@{type='killres';pid=$id;ok=$false;denied=([string]$_.Exception.Message -match 'erisim|Access|denied|reddedildi')}) }
  }
  if($fail) { exit 1 }
 }
 'svc-list' {
  $n=0
  foreach($v in (Cim Win32_Service)) {
   $delayed=$false; try { $delayed=[bool](Get-ItemProperty -LiteralPath ('HKLM:\SYSTEM\CurrentControlSet\Services\'+$v.Name) -Name DelayedAutostart -ErrorAction Stop).DelayedAutostart } catch {}
   EmitD ([ordered]@{type='svc';name=[string]$v.Name;display=[string]$v.DisplayName;state=[string]$v.State;start=[string]$v.StartMode;delayed=$delayed;account=[string]$v.StartName;path=[string]$v.PathName;desc=[string]$v.Description;pid=[int]$v.ProcessId})
   $n++
  }
  Write-Output ('Servis sayisi: '+$n)
 }
 'svc-action' {
  RequireAdmin
  $crit=@('rpcss','dcomlaunch','rpceptmapper','lsm','samss','eventlog','plugplay','winmgmt','bfe','mpssvc','windefend','cryptsvc','dnscache','dhcp','nsi','profsvc','power','brokerinfrastructure','coremessagingregistrar','systemeventsbroker','gpsvc','schedule','usermanager','staterepository','trustedinstaller')
  $fail=0
  foreach($x in (ItemsFromB64)) {
   $name=[string]$x.name
   if($crit -contains $name.ToLower() -and @('stop','disabled','restart') -contains $Op) { Write-Output ('Kritik servis, atlandi: '+$name); continue }
   try {
    switch($Op) {
     'start'    { Start-Service -Name $name -ErrorAction Stop }
     'stop'     { Stop-Service -Name $name -Force -ErrorAction Stop }
     'restart'  { Restart-Service -Name $name -Force -ErrorAction Stop }
     'auto'     { Set-Service -Name $name -StartupType Automatic -ErrorAction Stop }
     'manual'   { Set-Service -Name $name -StartupType Manual -ErrorAction Stop }
     'disabled' { Set-Service -Name $name -StartupType Disabled -ErrorAction Stop }
     default    { throw 'gecersiz islem' }
    }
    Write-Output ('Tamam: {0} ({1})' -f $name,$Op)
   } catch { $fail++; Write-Output ('HATA: {0} ({1}) — {2}' -f $name,$Op,$_.Exception.Message) }
  }
  if($fail) { exit 1 }
 }
 'startup-list' {
  # Baslangic: Run anahtarlari ve baslangic klasorleri; etkin/devre disi durumu Gorev Yoneticisi'nin StartupApproved kaydindan.
  $src=@(
   @('hkcu-run','HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'),
   @('hklm-run','HKLM:\Software\Microsoft\Windows\CurrentVersion\Run'),
   @('hklm-run32','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run'))
  $n=0
  foreach($s in $src) {
   try { $key=Get-Item -LiteralPath $s[1] -ErrorAction Stop } catch { continue }
   foreach($nm in $key.GetValueNames()) {
    if(-not $nm) { continue }
    $cmd=[string]$key.GetValue($nm,'',[Microsoft.Win32.RegistryValueOptions]::None)
    EmitD ([ordered]@{type='startup';scope=$s[0];name=$nm;command=$cmd;enabled=(StartupEnabled $s[0] $nm)})
    $n++
   }
  }
  $folders=@(@('user-folder',[Environment]::GetFolderPath('Startup')),@('common-folder',[Environment]::GetFolderPath('CommonStartup')))
  $sh=$null; try { $sh=New-Object -ComObject WScript.Shell } catch {}
  foreach($f in $folders) {
   if(-not $f[1] -or -not (Test-Path -LiteralPath $f[1])) { continue }
   foreach($i in @(Get-ChildItem -LiteralPath $f[1] -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -ne 'desktop.ini' })) {
    $cmd=$i.FullName
    if($sh -and $i.Extension -eq '.lnk') { try { $l=$sh.CreateShortcut($i.FullName); $cmd=('"{0}" {1}' -f $l.TargetPath,$l.Arguments).Trim() } catch {} }
    EmitD ([ordered]@{type='startup';scope=$f[0];name=$i.Name;command=$cmd;enabled=(StartupEnabled $f[0] $i.Name)})
    $n++
   }
  }
  Write-Output ('Baslangic ogesi: '+$n)
 }
 'startup-set' {
  # Gorev Yoneticisi ile ayni: StartupApproved degeri 02.. (etkin) / 03.. + zaman (devre disi). Kayit silinmez.
  $fail=0
  foreach($x in (ItemsFromB64)) {
   $scope=[string]$x.scope; $name=[string]$x.name; $key=$StartupApprovedKeys[$scope]
   if(-not $key) { Write-Output ('Bilinmeyen konum: '+$scope); $fail++; continue }
   if($scope -like 'hklm*' -or $scope -like 'common*') { if(-not (IsAdmin)) { Write-Output ('Yonetici gerekir: '+$name); $fail++; continue } }
   try {
    if(-not (Test-Path -LiteralPath $key)) { New-Item -Path $key -Force | Out-Null }
    $b=New-Object byte[] 12
    if($Op -eq 'disable') { $b[0]=3; [BitConverter]::GetBytes([DateTime]::UtcNow.ToFileTimeUtc()).CopyTo($b,4) } else { $b[0]=2 }
    New-ItemProperty -LiteralPath $key -Name $name -PropertyType Binary -Value $b -Force | Out-Null
    Write-Output ('{0}: {1}' -f $name,$(if($Op -eq 'disable'){'devre disi'}else{'etkin'}))
   } catch { $fail++; Write-Output ('HATA: {0} — {1}' -f $name,$_.Exception.Message) }
  }
  if($fail) { exit 1 }
 }
}
