# AGFO Ses Servisi - Windows kurulumu (EMA Lightning, Türkçe TTS)
# Sunucudaki AGFO TTS Service'in aynısını bu bilgisayarda, yalnız bu bilgisayardan erişilebilen
# 127.0.0.1 adresinde çalıştırır. NVIDIA ekran kartı varsa onu kullanır.
# Kurulum yeri: %LOCALAPPDATA%\AGFO\TTS   (yönetici izni gerekmez)
# Kullanım:  AGFO-Ses-Kur.cmd            kur / güncelle
#            AGFO-Ses-Kur.cmd -Kaldir    kaldır
param([switch]$Kaldir, [switch]$CpuOnly)

$ErrorActionPreference = 'Continue'   # yerel komutların stderr çıktısı PS 5.1'de hata sayılmasın
$ProgressPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

$Src = $PSScriptRoot
$D = Join-Path $env:LOCALAPPDATA 'AGFO\TTS'
$Py = Join-Path $D 'venv\Scripts\python.exe'
$Pyw = Join-Path $D 'venv\Scripts\pythonw.exe'
$Lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'AGFO Ses Servisi.lnk'
$Desk = [Environment]::GetFolderPath('Desktop')
$Log = Join-Path $Desk 'agfo-ses-kur-sonuc.txt'
try { Start-Transcript -Path $Log -Force | Out-Null } catch {}

function Step($t) { Write-Host "`n== $t" -ForegroundColor Cyan }
function Ok($t)   { Write-Host "  [tamam] $t" -ForegroundColor Green }
function Warn($t) { Write-Host "  [uyarı] $t" -ForegroundColor Yellow }
function Fail($t) { Write-Host "  [hata]  $t" -ForegroundColor Red }
function Done($code) {
    try { Stop-Transcript | Out-Null } catch {}
    Write-Host "`nÇıktı kaydedildi: $Log" -ForegroundColor Cyan
    exit $code
}
trap { Fail $_.Exception.Message; Done 1 }

function Refresh-Path {
    $m = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $u = [Environment]::GetEnvironmentVariable('Path', 'User')
    $links = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links'
    $env:Path = "$m;$u;$links"
}
function Find-Exe($name) {
    Refresh-Path
    $c = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return $c.Source }
    $hit = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages') -Recurse -Filter "$name.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($hit) { return $hit.FullName }
    return $null
}
function Winget-Install($id) {
    winget install --id $id -e --silent --accept-source-agreements --accept-package-agreements
    return ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq -1978335189 -or $LASTEXITCODE -eq -1978335135)
}
function Stop-Service-Process {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*run_local.py*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
function Read-Env {
    $h = @{}
    $f = Join-Path $D '.env'
    if (Test-Path $f) {
        Get-Content $f -Encoding UTF8 | ForEach-Object {
            if ($_ -match '^\s*([^#=]+?)\s*=\s*(.*)$') { $h[$matches[1]] = $matches[2].Trim() }
        }
    }
    return $h
}

# ---------------------------------------------------------------- kaldırma
if ($Kaldir) {
    Step 'Kaldırılıyor'
    Stop-Service-Process
    if (Test-Path $Lnk) { Remove-Item $Lnk -Force }
    if (Test-Path $D) {
        $keep = Join-Path $env:TEMP ('agfo-tts-sozluk-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json')
        $custom = Join-Path $D 'data\lexicon.custom.json'
        if (Test-Path $custom) { Copy-Item $custom $keep; Ok "Size özel sözlük yedeklendi: $keep" }
        Remove-Item $D -Recurse -Force
    }
    Ok 'AGFO Ses Servisi kaldırıldı.'
    Done 0
}

# ---------------------------------------------------------------- 1. ön kontroller
Step 'Ön kontroller'
foreach ($f in 'server.py', 'lexicon.json', 'run_local.py') {
    if (-not (Test-Path (Join-Path $Src $f))) { Fail "$f bu klasörde yok ($Src). ZIP'in tamamını aynı klasöre çıkarın."; Done 1 }
}
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Fail 'winget bulunamadı. Microsoft Store''dan "Uygulama Yükleyici"yi (App Installer) güncelleyip tekrar deneyin.'; Done 1
}
Ok 'winget var'
$gpu = $null
if (-not $CpuOnly -and (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    $gpu = (& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>$null | Select-Object -First 1)
}
if ($gpu) { Ok "Ekran kartı: $gpu" } else { Warn 'NVIDIA ekran kartı kullanılmayacak; servis işlemcide çalışır (daha yavaş).' }
$drive = (Split-Path -Qualifier $env:LOCALAPPDATA).TrimEnd(':')
$freeGB = [math]::Round((Get-PSDrive $drive).Free / 1GB, 1)
$needGB = $(if ($gpu) { 8 } else { 3 })
if ($freeGB -lt $needGB) { Fail "$drive`: sürücüsünde $freeGB GB boş; yaklaşık $needGB GB gerekir."; Done 1 }
Ok "$drive`: sürücüsünde $freeGB GB boş (gereken ~$needGB GB)"

# ---------------------------------------------------------------- 2. araçlar
Step 'Araçlar (ffmpeg, uv)'
$ffmpeg = Find-Exe 'ffmpeg'
if (-not $ffmpeg) {
    Write-Host '  ffmpeg kuruluyor…'
    if (-not (Winget-Install 'Gyan.FFmpeg')) { Fail "ffmpeg kurulamadı (winget kodu $LASTEXITCODE)"; Done 1 }
    $ffmpeg = Find-Exe 'ffmpeg'
}
if (-not $ffmpeg) { Fail 'ffmpeg kuruldu ama bulunamadı; bilgisayarı yeniden başlatıp betiği tekrar çalıştırın.'; Done 1 }
Ok "ffmpeg: $ffmpeg"
$uv = Find-Exe 'uv'
if (-not $uv) {
    Write-Host '  uv kuruluyor…'
    if (-not (Winget-Install 'astral-sh.uv')) { Fail "uv kurulamadı (winget kodu $LASTEXITCODE)"; Done 1 }
    $uv = Find-Exe 'uv'
}
if (-not $uv) { Fail 'uv kuruldu ama bulunamadı; bilgisayarı yeniden başlatıp betiği tekrar çalıştırın.'; Done 1 }
Ok "uv: $uv"

# ---------------------------------------------------------------- 3. dosyalar
Step 'Servis dosyaları'
Stop-Service-Process
New-Item -ItemType Directory -Force -Path $D, (Join-Path $D 'data'), (Join-Path $D 'cache'), (Join-Path $D 'hf') | Out-Null
foreach ($f in 'server.py', 'lexicon.json', 'run_local.py') { Copy-Item (Join-Path $Src $f) (Join-Path $D $f) -Force }
Ok "Kurulum klasörü: $D"

# ---------------------------------------------------------------- 4. Python ve paketler
Step 'Python 3.12 ve paketler (ilk kurulumda birkaç GB indirilir)'
$env:UV_NO_CONFIG = '1'
& $uv python install 3.12
if (-not (Test-Path $Py)) {
    & $uv venv --python 3.12 (Join-Path $D 'venv')
    if (-not (Test-Path $Py)) { Fail 'Sanal ortam oluşturulamadı.'; Done 1 }
}
if ($gpu) { $torchIndex = 'https://download.pytorch.org/whl/cu126' } else { $torchIndex = 'https://download.pytorch.org/whl/cpu' }
Write-Host "  PyTorch ($torchIndex)…"
& $uv pip install --python $Py torch --index-url $torchIndex
if ($LASTEXITCODE -ne 0) { Fail 'PyTorch kurulamadı.'; Done 1 }
& $uv pip install --python $Py ema-lightning fastapi 'uvicorn[standard]' soundfile numpy
if ($LASTEXITCODE -ne 0) { Fail 'Paketler kurulamadı.'; Done 1 }
$probe = & $Py -c "import torch, ema_lightning; print(torch.__version__, 'cuda' if torch.cuda.is_available() else 'cpu')" 2>$null
if ($LASTEXITCODE -ne 0) { Fail 'Python paketleri yüklenemedi.'; Done 1 }
Ok "torch $probe"
if ($gpu -and $probe -notmatch 'cuda') { Warn 'PyTorch ekran kartını görmüyor; NVIDIA sürücüsünü güncelleyin. Servis şimdilik işlemcide çalışacak.' }

# ---------------------------------------------------------------- 5. ayarlar
Step 'Ayarlar'
$envMap = Read-Env
if (-not $envMap['AGFO_TTS_TOKEN']) {
    $bytes = New-Object byte[] 24
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $envMap['AGFO_TTS_TOKEN'] = -join ($bytes | ForEach-Object { $_.ToString('x2') })
}
if (-not $envMap['AGFO_TTS_PORT']) {
    $port = 8765
    while ($port -lt 8800) {
        $busy = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if (-not $busy) { break }
        $port++
    }
    $envMap['AGFO_TTS_PORT'] = "$port"
}
$envMap['AGFO_TTS_FFMPEG'] = $ffmpeg
$envMap['AGFO_TTS_THREADS'] = "$([Environment]::ProcessorCount)"
$envMap['AGFO_TTS_CACHE_DIR'] = (Join-Path $D 'cache')
$envMap['AGFO_TTS_DATA_DIR'] = (Join-Path $D 'data')
$envMap['HF_HOME'] = (Join-Path $D 'hf')
$lines = @('# AGFO Ses Servisi ayarları - AGFO AI Editor bu dosyadan adresi ve anahtarı okur')
foreach ($k in ($envMap.Keys | Sort-Object)) { $lines += "$k=$($envMap[$k])" }
[IO.File]::WriteAllLines((Join-Path $D '.env'), $lines, (New-Object Text.UTF8Encoding($false)))
$Port = $envMap['AGFO_TTS_PORT']; $Token = $envMap['AGFO_TTS_TOKEN']
$Api = "http://127.0.0.1:$Port"
Ok "Adres: $Api (yalnız bu bilgisayardan)"

# ---------------------------------------------------------------- 6. otomatik başlatma
Step 'Oturum açılınca otomatik başlatma'
$sh = New-Object -ComObject WScript.Shell
$s = $sh.CreateShortcut($Lnk)
$s.TargetPath = $Pyw
$s.Arguments = '"' + (Join-Path $D 'run_local.py') + '"'
$s.WorkingDirectory = $D
$s.Description = 'AGFO Ses Servisi (EMA Lightning)'
$s.Save()
Ok "Başlangıç kısayolu: $Lnk"

# ---------------------------------------------------------------- 7. başlat ve bekle
Step 'Servis başlatılıyor (ilk açılışta ses modeli indirilir)'
Start-Process -FilePath $Pyw -ArgumentList ('"' + (Join-Path $D 'run_local.py') + '"') -WorkingDirectory $D
$hdr = @{ 'X-AGFO-Token' = $Token }
$health = $null
for ($i = 0; $i -lt 200 -and -not $health; $i++) {
    Start-Sleep 3
    try { $health = Invoke-RestMethod "$Api/health" -Headers $hdr -TimeoutSec 5 -ErrorAction Stop } catch {}
    if ($i % 10 -eq 9) { Write-Host "  … bekleniyor ($([int](($i + 1) * 3)) sn)" }
}
if (-not $health) {
    Fail 'Servis 10 dakikada yanıt vermedi. Kayıt dosyasının son satırları:'
    Get-Content (Join-Path $D 'service.log') -Tail 25 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
    Done 1
}
Ok "Servis $($health.version) çalışıyor - aygıt: $($health.device), sözlük: $($health.lexicon_entries) kelime"

# ---------------------------------------------------------------- 8. deneme
Step 'Deneme'
$sample = 'Merhaba, ben AGFO ses servisi. Bu ses şu anda kendi bilgisayarınızda üretildi. Chicago''daki HACCP denetimi on beş dakika sürdü.'
foreach ($n in 1, 2) {
    $body = @{ text = $sample; speed = 1.0; seed = $n } | ConvertTo-Json
    $out = Join-Path $Desk 'agfo-ses-deneme.mp3'
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try {
        $r = Invoke-WebRequest "$Api/tts" -Method Post -Headers $hdr -ContentType 'application/json; charset=utf-8' `
             -Body ([Text.Encoding]::UTF8.GetBytes($body)) -OutFile $out -PassThru -UseBasicParsing -TimeoutSec 600 -ErrorAction Stop
        $sw.Stop()
        $sec = $r.Headers['X-AGFO-Seconds']
        Ok ("Deneme ${n}: {0} sn ses, {1} sn'de üretildi" -f $sec, [math]::Round($sw.Elapsed.TotalSeconds, 1))
    } catch { Fail "Deneme seslendirmesi başarısız: $($_.Exception.Message)"; Done 1 }
}
Write-Host "  Dinleyin: $out"
Write-Host '  (İlk deneme modeli ısıttığı için yavaştır; ikincisi gerçek hızı gösterir.)'

Step 'Bitti'
Write-Host '  AGFO AI Editor 1.7.0 bu servisi kendiliğinden bulur: Ses sekmesi › Ses servisi › Bu bilgisayar.'
Write-Host '  Sunucudaki ortak sözlüğü almak için editörde "Sözlüğü siteden eşitle" düğmesini kullanın.'
Write-Host '  Kaldırmak için:  AGFO-Ses-Kur.cmd -Kaldir'
Done 0
