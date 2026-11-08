# AGFO Arapça Ses Servisi - kurulu Arapça modelleri (SILMA, Habibi) AGFO AI Editor'e bağlar.
# Denemelerde kurulan sanal ortamları kullanır, yeni model indirmez:
#   SILMA   %LOCALAPPDATA%\AGFO\TTS-AR       (AGFO-Arapca-Dene.cmd ile kurulmuş olmalı)
#   Habibi  %LOCALAPPDATA%\AGFO\TTS-HABIBI   (AGFO-Arapca-Karsilastir.cmd ile kurulmuş olmalı)
# Her biri için 127.0.0.1 üzerinde ayrı bir servis açılır ve oturum açılınca kendiliğinden başlar.
# Editör servisleri bu klasörlerdeki .env dosyalarından bulur: Ses sekmesi › Bu bilgisayar › Yerel ses.
# Kullanım:  AGFO-Arapca-Servis-Kur.cmd           kur / güncelle
#            AGFO-Arapca-Servis-Kur.cmd -Kaldir   servisleri kaldır (modeller ve sanal ortamlar kalır)
param([switch]$Kaldir)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

$Src = $PSScriptRoot
$Base = Join-Path $env:LOCALAPPDATA 'AGFO'
$Startup = [Environment]::GetFolderPath('Startup')
$Desk = [Environment]::GetFolderPath('Desktop')
$Log = Join-Path $Desk 'agfo-arapca-servis-sonuc.txt'
try { Start-Transcript -Path $Log -Force | Out-Null } catch {}

function Step($t) { Write-Host "`n== $t" -ForegroundColor Cyan }
function Ok($t)   { Write-Host "  [tamam] $t" -ForegroundColor Green }
function Warn($t) { Write-Host "  [uyarı] $t" -ForegroundColor Yellow }
function Fail($t) { Write-Host "  [hata]  $t" -ForegroundColor Red }
function Done($code) {
    try { Stop-Transcript | Out-Null } catch {}
    Write-Host "`nÇıktı kaydedildi: $Log  (sorun olursa bu dosyayı Claude'a gönderin)" -ForegroundColor Cyan
    exit $code
}
trap { Fail $_.Exception.Message; Done 1 }
function Show { process { Write-Host "  $_" } }
function Find-Exe($name) {
    $m = [Environment]::GetEnvironmentVariable('Path', 'Machine'); $u = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$m;$u;" + (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links')
    $c = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return $c.Source }
    $hit = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages') -Recurse -Filter "$name.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($hit) { return $hit.FullName }
    return $null
}
function Stop-Engine($dir) {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*run_ar.py*' -and $_.CommandLine -like "*$dir*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
function Read-Env($dir) {
    $h = [ordered]@{}
    $f = Join-Path $dir '.env'
    if (Test-Path $f) {
        Get-Content $f -Encoding UTF8 | ForEach-Object { if ($_ -match '^\s*([^#=]+?)\s*=\s*(.*)$') { $h[$matches[1]] = $matches[2].Trim() } }
    }
    return $h
}
function Free-Port($start, $taken) {
    $p = $start
    while ($p -lt $start + 40) {
        if ($taken -notcontains "$p") {
            $free = $false
            try { $l = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, $p); $l.Start(); $l.Stop(); $free = $true } catch {}
            if ($free) { return "$p" }
        }
        $p++
    }
    return "$start"
}

$Engines = @(
    @{ Id = 'silma';  Dir = (Join-Path $Base 'TTS-AR');     Label = 'SILMA (Arapça)';  Port = 8770; Probe = 'import silma_tts.api' },
    @{ Id = 'habibi'; Dir = (Join-Path $Base 'TTS-HABIBI'); Label = 'Habibi (Arapça)'; Port = 8780; Probe = 'import habibi_tts, f5_tts.infer.utils_infer' }
)

if ($Kaldir) {
    Step 'Kaldırılıyor'
    foreach ($e in $Engines) {
        Stop-Engine $e.Dir
        $lnk = Join-Path $Startup ("AGFO Arapça Ses - {0}.lnk" -f $e.Id)
        if (Test-Path $lnk) { Remove-Item $lnk -Force }
        foreach ($f in '.env', 'ar_server.py', 'run_ar.py') { $p = Join-Path $e.Dir $f; if (Test-Path $p) { Remove-Item $p -Force } }
    }
    Ok 'Arapça ses servisleri kaldırıldı. Modeller ve sanal ortamlar duruyor (silmek için deneme betiklerini -Kaldir ile çalıştırın).'
    Done 0
}

Step 'Ön kontroller'
foreach ($f in 'ar_server.py', 'run_ar.py') {
    if (-not (Test-Path (Join-Path $Src $f))) { Fail "$f bu klasörde yok ($Src). ZIP'in tamamını çıkarın."; Done 1 }
}
$ffmpeg = Find-Exe 'ffmpeg'
$uv = Find-Exe 'uv'
if (-not $ffmpeg -or -not $uv) { Fail 'ffmpeg ya da uv bulunamadı; önce AGFO-Arapca-Dene.cmd ile denemeyi kurun.'; Done 1 }
$found = @($Engines | Where-Object { Test-Path (Join-Path $_.Dir 'venv\Scripts\python.exe') })
if (-not $found) { Fail 'Kurulu Arapça model yok. Önce AGFO-Arapca-Dene.cmd (SILMA) ya da AGFO-Arapca-Karsilastir.cmd (Habibi) çalıştırın.'; Done 1 }
Ok ('Bulunan modeller: ' + (($found | ForEach-Object { $_.Label }) -join ', '))

$utf8 = New-Object Text.UTF8Encoding($false)
$takenPorts = @()
$egySrc = @(
    (Join-Path $Base 'TTS-HABIBI\venv\Lib\site-packages\habibi_tts\assets\EGY.mp3'),
    (Join-Path $Desk 'AGFO-Arapca-Karsilastirma\habibi\referans-egy.mp3')
) | Where-Object { Test-Path $_ } | Select-Object -First 1
$ok = 0

foreach ($e in $found) {
    Step ("Servis: {0}" -f $e.Label)
    $D = $e.Dir
    $Py = Join-Path $D 'venv\Scripts\python.exe'
    $Pyw = Join-Path $D 'venv\Scripts\pythonw.exe'
    Stop-Engine $D
    $cons = Join-Path $D 'constraints.txt'
    $consArgs = @(); if (Test-Path $cons) { $consArgs = @('-c', $cons) }
    & $uv pip install --python $Py @consArgs fastapi 'uvicorn[standard]' num2words soundfile 2>&1 | ForEach-Object { "$_" } | Show
    if ($LASTEXITCODE -ne 0) { Fail 'Servis paketleri kurulamadı.'; continue }
    $probe = ((& $Py -c ($e.Probe + "; print('ok')") 2>&1) -join ' ')
    if ($probe -notmatch 'ok') { Fail "Model paketleri yüklenemedi: $probe"; continue }
    foreach ($f in 'ar_server.py', 'run_ar.py') { Copy-Item (Join-Path $Src $f) (Join-Path $D $f) -Force }
    New-Item -ItemType Directory -Force -Path (Join-Path $D 'data\voices'), (Join-Path $D 'cache') | Out-Null
    if ($e.Id -eq 'silma' -and $egySrc) { Copy-Item $egySrc (Join-Path $D 'data\misirli.mp3') -Force; Ok 'SILMA için Mısırlı deneme sesi eklendi' }

    $envMap = Read-Env $D
    if (-not $envMap['AGFO_TTS_TOKEN']) {
        $bytes = New-Object byte[] 24
        [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
        $envMap['AGFO_TTS_TOKEN'] = -join ($bytes | ForEach-Object { $_.ToString('x2') })
    }
    if (-not $envMap['AGFO_TTS_PORT']) { $envMap['AGFO_TTS_PORT'] = Free-Port $e.Port $takenPorts }
    $takenPorts += $envMap['AGFO_TTS_PORT']
    $envMap['AGFO_TTS_ENGINE'] = $e.Id
    $envMap['AGFO_TTS_LANG'] = 'ar'
    $envMap['AGFO_TTS_LABEL'] = $e.Label
    $envMap['AGFO_TTS_FFMPEG'] = $ffmpeg
    $envMap['AGFO_TTS_CACHE_DIR'] = (Join-Path $D 'cache')
    $envMap['AGFO_TTS_DATA_DIR'] = (Join-Path $D 'data')
    $envMap['HF_HOME'] = (Join-Path $D 'hf')
    if (-not $envMap['AGFO_TTS_NFE']) { $envMap['AGFO_TTS_NFE'] = '32' }
    $lines = @("# AGFO Arapça Ses Servisi ($($e.Label)) - AGFO AI Editor adresi ve anahtarı buradan okur")
    foreach ($k in $envMap.Keys) { $lines += "$k=$($envMap[$k])" }
    [IO.File]::WriteAllLines((Join-Path $D '.env'), $lines, $utf8)
    $Api = "http://127.0.0.1:$($envMap['AGFO_TTS_PORT'])"
    $hdr = @{ 'X-AGFO-Token' = $envMap['AGFO_TTS_TOKEN'] }

    $sh = New-Object -ComObject WScript.Shell
    $s = $sh.CreateShortcut((Join-Path $Startup ("AGFO Arapça Ses - {0}.lnk" -f $e.Id)))
    $s.TargetPath = $Pyw
    $s.Arguments = '"' + (Join-Path $D 'run_ar.py') + '"'
    $s.WorkingDirectory = $D
    $s.Description = "AGFO Arapça Ses Servisi ($($e.Label))"
    $s.Save()
    Ok 'Oturum açılınca kendiliğinden başlayacak'

    Start-Process -FilePath $Pyw -ArgumentList ('"' + (Join-Path $D 'run_ar.py') + '"') -WorkingDirectory $D
    $health = $null
    for ($i = 0; $i -lt 60 -and -not $health; $i++) {
        Start-Sleep 2
        try { $health = Invoke-RestMethod "$Api/health" -Headers $hdr -TimeoutSec 5 -ErrorAction Stop } catch {}
    }
    if (-not $health) {
        Fail 'Servis yanıt vermedi. Kayıt dosyasının son satırları:'
        Get-Content (Join-Path $D 'service.log') -Tail 20 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
        continue
    }
    Ok "Servis çalışıyor: $Api (aygıt: $($health.device) $($health.gpu), ses: $($health.voices))"
    $vs = Invoke-RestMethod "$Api/voices" -Headers $hdr -TimeoutSec 10
    foreach ($v in $vs.voices) { Write-Host ("    ses: {0}  ({1})" -f $v.name, $v.id) }

    Write-Host '  Deneme seslendirmesi (model ilk kez belleğe yükleniyor)…'
    $body = @{ text = 'مرحبا، هذا اختبار لخدمة الصوت العربية في محرر AGFO.'; voice = $vs.default } | ConvertTo-Json
    $out = Join-Path $Desk ("agfo-arapca-servis-{0}.mp3" -f $e.Id)
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try {
        $r = Invoke-WebRequest "$Api/tts" -Method Post -Headers $hdr -ContentType 'application/json; charset=utf-8' `
             -Body ([Text.Encoding]::UTF8.GetBytes($body)) -OutFile $out -PassThru -UseBasicParsing -TimeoutSec 900 -ErrorAction Stop
        Ok ("Deneme: {0} sn ses, {1} sn'de üretildi - {2}" -f $r.Headers['X-AGFO-Seconds'], [math]::Round($sw.Elapsed.TotalSeconds, 1), $out)
        $ok++
    } catch {
        Fail "Deneme seslendirmesi başarısız: $($_.Exception.Message)"
        Get-Content (Join-Path $D 'service.log') -Tail 20 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
    }
}

Step 'Bitti'
if (-not $ok) { Fail 'Hiçbir servis denemeyi geçemedi.'; Done 1 }
Write-Host '  AGFO AI Editor 2.14.0 ve üstü: Ses sekmesi › Ses servisi › Bu bilgisayar › Yerel ses listesinden Arapça sesi seçin.'
Write-Host "  Kendi sesinizi eklemek için: 5-15 sn'lik kayıt (ad.wav) ve yazısı (ad.txt) -> <model klasörü>\data\voices"
Write-Host '  Kaldırmak için: AGFO-Arapca-Servis-Kur.cmd -Kaldir'
Done 0
