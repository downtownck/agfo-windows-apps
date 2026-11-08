# AGFO İngilizce / İspanyolca Ses Servisi - Qwen3-TTS (Apache-2.0) bu bilgisayarın NVIDIA ekran kartında.
# Ayrı bir klasöre kurulur, Türkçe (AGFO-Ses-Kur) ve Arapça servislere dokunmaz:  %LOCALAPPDATA%\AGFO\TTS-QWEN
# Kurulumdan sonra servis 127.0.0.1 üzerinde çalışır ve oturum açılınca kendiliğinden başlar.
# AGFO AI Editor 2.14.0 ve üstü: Ses sekmesi › Bu bilgisayar › Yerel ses listesinde "Qwen3-TTS" sesleri.
# Kullanım:  AGFO-Ses-Qwen-Kur.cmd                 kur / güncelle
#            AGFO-Ses-Qwen-Kur.cmd -Boyut 0.6B     daha küçük model (daha hızlı, biraz daha düşük kalite)
#            AGFO-Ses-Qwen-Kur.cmd -Kaldir         kaldır
param([switch]$Kaldir, [ValidateSet('1.7B', '0.6B')][string]$Boyut = '1.7B')

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}

$Src = $PSScriptRoot
$D = Join-Path $env:LOCALAPPDATA 'AGFO\TTS-QWEN'
$Py = Join-Path $D 'venv\Scripts\python.exe'
$Pyw = Join-Path $D 'venv\Scripts\pythonw.exe'
$Startup = [Environment]::GetFolderPath('Startup')
$Lnk = Join-Path $Startup 'AGFO Ses - qwen.lnk'
$Desk = [Environment]::GetFolderPath('Desktop')
$Log = Join-Path $Desk 'agfo-ses-qwen-sonuc.txt'
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
function Refresh-Path {
    $m = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $u = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$m;$u;" + (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links')
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
    winget install --id $id -e --silent --source winget --accept-source-agreements --accept-package-agreements 2>&1 | ForEach-Object { "$_" } | Show
    return ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq -1978335189 -or $LASTEXITCODE -eq -1978335135)
}
function Stop-Service-Here {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*run_ar.py*' -and $_.CommandLine -like '*TTS-QWEN*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

if ($Kaldir) {
    Step 'Kaldırılıyor'
    Stop-Service-Here
    Start-Sleep 1
    if (Test-Path $Lnk) { Remove-Item $Lnk -Force }
    if (Test-Path $D) { Remove-Item $D -Recurse -Force }
    Ok 'İngilizce / İspanyolca ses servisi ve modelleri kaldırıldı.'
    Done 0
}

# ---------------------------------------------------------------- 1. ön kontroller
Step 'Ön kontroller'
foreach ($f in 'ar_server.py', 'run_ar.py') {
    if (-not (Test-Path (Join-Path $Src $f))) { Fail "$f bu klasörde yok ($Src). ZIP'in tamamını çıkarın."; Done 1 }
}
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { Fail 'winget bulunamadı. Microsoft Store''dan "Uygulama Yükleyici"yi güncelleyin.'; Done 1 }
$gpu = $null
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    $gpu = (& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>$null | Select-Object -First 1)
}
if ($gpu) { Ok "Ekran kartı: $gpu" } else { Warn 'NVIDIA ekran kartı bulunamadı; ses işlemcide çok yavaş üretilir.' }
$drive = (Split-Path -Qualifier $env:LOCALAPPDATA).TrimEnd(':')
$freeGB = [math]::Round((Get-PSDrive $drive).Free / 1GB, 1)
if ($freeGB -lt 20) { Fail "$drive`: sürücüsünde $freeGB GB boş; yaklaşık 20 GB gerekir."; Done 1 }
Ok "$drive`: sürücüsünde $freeGB GB boş"

# ---------------------------------------------------------------- 2. araçlar
Step 'Araçlar (ffmpeg, uv)'
$ffmpeg = Find-Exe 'ffmpeg'
if (-not $ffmpeg) { Write-Host '  ffmpeg kuruluyor…'; [void](Winget-Install 'Gyan.FFmpeg'); $ffmpeg = Find-Exe 'ffmpeg' }
if (-not $ffmpeg) { Fail 'ffmpeg kurulamadı; bilgisayarı yeniden başlatıp tekrar deneyin.'; Done 1 }
Ok "ffmpeg: $ffmpeg"
$uv = Find-Exe 'uv'
if (-not $uv) { Write-Host '  uv kuruluyor…'; [void](Winget-Install 'astral-sh.uv'); $uv = Find-Exe 'uv' }
if (-not $uv) { Fail 'uv kurulamadı; bilgisayarı yeniden başlatıp tekrar deneyin.'; Done 1 }
Ok "uv: $uv"

# ---------------------------------------------------------------- 3. Python ve paketler
Step 'Python 3.12 ve paketler (ilk kurulumda yaklaşık 4 GB indirilir)'
Stop-Service-Here
New-Item -ItemType Directory -Force -Path $D, (Join-Path $D 'hf'), (Join-Path $D 'cache'), (Join-Path $D 'data\voices') | Out-Null
$env:UV_NO_CONFIG = '1'
& $uv python install 3.12 2>&1 | ForEach-Object { "$_" } | Show
if (-not (Test-Path $Py)) {
    & $uv venv --python 3.12 (Join-Path $D 'venv') 2>&1 | ForEach-Object { "$_" } | Show
    if (-not (Test-Path $Py)) { Fail 'Sanal ortam oluşturulamadı.'; Done 1 }
}
if ($gpu) { $idx = 'https://download.pytorch.org/whl/cu126' } else { $idx = 'https://download.pytorch.org/whl/cpu' }
Write-Host "  PyTorch 2.8 ($idx)…"
& $uv pip install --python $Py torch==2.8.0 torchaudio==2.8.0 torchvision==0.23.0 --index-url $idx 2>&1 | ForEach-Object { "$_" } | Show
if ($LASTEXITCODE -ne 0) { Fail 'PyTorch kurulamadı.'; Done 1 }
$utf8 = New-Object Text.UTF8Encoding($false)
$cons = Join-Path $D 'constraints.txt'
[IO.File]::WriteAllText($cons, "torch==2.8.0`ntorchaudio==2.8.0`ntorchvision==0.23.0`n", $utf8)
# qwen-tts'in demo arayuzu (gradio) gerekmez; paket bagimliliksiz kurulur, gerekenler ayrica eklenir
Write-Host '  Qwen3-TTS ve bağımlılıkları…'
& $uv pip install --python $Py --no-deps qwen-tts 2>&1 | ForEach-Object { "$_" } | Show
if ($LASTEXITCODE -ne 0) { Fail 'qwen-tts indirilemedi.'; Done 1 }
& $uv pip install --python $Py -c $cons transformers==4.57.3 accelerate==1.12.0 librosa soundfile sox onnxruntime einops `
    huggingface_hub hf_xet 'numpy<2.3' fastapi 'uvicorn[standard]' num2words 2>&1 | ForEach-Object { "$_" } | Show
if ($LASTEXITCODE -ne 0) { Fail 'Bağımlılıklar kurulamadı.'; Done 1 }
# qwen_tts ice aktarilirken SoX ve flash-attn uyarilari yazar; zararsizdir, yalniz son satir (surum) alinir
$probe = ((& $Py -c "import torch, qwen_tts; print('AGFO-PROBE', torch.__version__, 'cuda' if torch.cuda.is_available() else 'cpu')" 2>&1 |
          ForEach-Object { "$_" } | Where-Object { $_ -match '^AGFO-PROBE ' }) -join ' ') -replace '^AGFO-PROBE ', ''
if ($probe -notmatch '\d+\.\d+') { Fail "Paketler yüklenemedi: $probe"; Done 1 }
Ok "torch $probe"
if ($gpu -and $probe -notmatch 'cuda') { Warn 'PyTorch ekran kartını görmüyor; NVIDIA sürücüsünü güncelleyin.' }

# ---------------------------------------------------------------- 4. modeller
Step "Qwen3-TTS $Boyut modelleri indiriliyor (hazır sesler + kendi sesiniz için klon modeli)"
$env:HF_HOME = Join-Path $D 'hf'
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = '1'
$env:PYTHONIOENCODING = 'utf-8'
# Modeller dogrudan models\<ad> klasorune indirilir: Hugging Face onbellegi Windows'ta sembolik baglanti ister ve
# Gelistirici Modu kapaliyken yarida kalabilir (WinError 1314). Yarim kalan indirme kaldigi yerden surer.
$Models = Join-Path $D 'models'
$env:AGFO_MODELS = $Models
$dl = "import os`nfrom huggingface_hub import snapshot_download as s`nfor k in ('CustomVoice', 'Base'):`n    r = 'Qwen3-TTS-12Hz-$Boyut-' + k`n    print('  ', r, flush=True); s('Qwen/' + r, local_dir=os.path.join(os.environ['AGFO_MODELS'], r))`nprint('ok')"
$res = & $Py -c $dl 2>&1 | ForEach-Object { "$_" } | Where-Object { $_ -notmatch 'it/s\]|B/s\]|RemoteException|^\s*$' }
$res | Show
if (($res -join ' ') -notmatch '\bok\b') { Fail 'Modeller indirilemedi (ayrıntı yukarıda).'; Done 1 }
Ok "Modeller hazır: $Models"
# onceki surumun Hugging Face onbellegindeki kopyalari artik gerekmez
foreach ($old in 'models--Qwen--Qwen3-TTS-12Hz-1.7B-CustomVoice', 'models--Qwen--Qwen3-TTS-12Hz-1.7B-Base', 'models--Qwen--Qwen3-TTS-12Hz-0.6B-CustomVoice', 'models--Qwen--Qwen3-TTS-12Hz-0.6B-Base') {
    $op = Join-Path $D "hf\hub\$old"
    if (Test-Path $op) { Remove-Item $op -Recurse -Force -ErrorAction SilentlyContinue }
}

# ---------------------------------------------------------------- 5. servis
Step 'Servis'
foreach ($f in 'ar_server.py', 'run_ar.py') { Copy-Item (Join-Path $Src $f) (Join-Path $D $f) -Force }
$envMap = [ordered]@{}
$envFile = Join-Path $D '.env'
if (Test-Path $envFile) {
    Get-Content $envFile -Encoding UTF8 | ForEach-Object { if ($_ -match '^\s*([^#=]+?)\s*=\s*(.*)$') { $envMap[$matches[1]] = $matches[2].Trim() } }
}
if (-not $envMap['AGFO_TTS_TOKEN']) {
    $bytes = New-Object byte[] 24
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $envMap['AGFO_TTS_TOKEN'] = -join ($bytes | ForEach-Object { $_.ToString('x2') })
}
if (-not $envMap['AGFO_TTS_PORT']) {
    $p = 8790
    while ($p -lt 8830) {
        $free = $false
        try { $l = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, $p); $l.Start(); $l.Stop(); $free = $true } catch {}
        if ($free) { break }
        $p++
    }
    $envMap['AGFO_TTS_PORT'] = "$p"
}
$envMap['AGFO_TTS_ENGINE'] = 'qwen'
$envMap['AGFO_TTS_LANG'] = 'en'
$envMap['AGFO_TTS_LABEL'] = 'Qwen3-TTS (İngilizce, İspanyolca)'
$envMap['AGFO_TTS_QWEN_SIZE'] = $Boyut
$envMap['AGFO_TTS_QWEN_DIR'] = $Models
$envMap['AGFO_TTS_FFMPEG'] = $ffmpeg
$envMap['AGFO_TTS_CACHE_DIR'] = (Join-Path $D 'cache')
$envMap['AGFO_TTS_DATA_DIR'] = (Join-Path $D 'data')
$envMap['HF_HOME'] = (Join-Path $D 'hf')
$envMap['HF_HUB_OFFLINE'] = '1'
$lines = @('# AGFO İngilizce / İspanyolca Ses Servisi (Qwen3-TTS) - AGFO AI Editor adresi ve anahtarı buradan okur')
foreach ($k in $envMap.Keys) { $lines += "$k=$($envMap[$k])" }
[IO.File]::WriteAllLines($envFile, $lines, $utf8)
$readme = "Kendi sesinizi eklemek için bu klasöre 5-15 saniyelik gürültüsüz bir kayıt (ad.wav) ve kayıttaki cümlenin yazısını (ad.txt) koyun.`r`n" +
          "İspanyolca okuyacak ses için İspanyolca, İngilizce için İngilizce bir kayıt en iyi sonucu verir. Sesi kullanılan kişinin izni gerekir.`r`n"
[IO.File]::WriteAllText((Join-Path $D 'data\voices\BENIOKU.txt'), $readme, $utf8)

$sh = New-Object -ComObject WScript.Shell
$s = $sh.CreateShortcut($Lnk)
$s.TargetPath = $Pyw
$s.Arguments = '"' + (Join-Path $D 'run_ar.py') + '"'
$s.WorkingDirectory = $D
$s.Description = 'AGFO İngilizce / İspanyolca Ses Servisi (Qwen3-TTS)'
$s.Save()
Ok 'Oturum açılınca kendiliğinden başlayacak'

Start-Process -FilePath $Pyw -ArgumentList ('"' + (Join-Path $D 'run_ar.py') + '"') -WorkingDirectory $D
$Api = "http://127.0.0.1:$($envMap['AGFO_TTS_PORT'])"
$hdr = @{ 'X-AGFO-Token' = $envMap['AGFO_TTS_TOKEN'] }
$health = $null
for ($i = 0; $i -lt 60 -and -not $health; $i++) {
    Start-Sleep 2
    try { $health = Invoke-RestMethod "$Api/health" -Headers $hdr -TimeoutSec 5 -ErrorAction Stop } catch {}
}
if (-not $health) {
    Fail 'Servis yanıt vermedi. Kayıt dosyasının son satırları:'
    Get-Content (Join-Path $D 'service.log') -Tail 25 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
    Done 1
}
Ok "Servis çalışıyor: $Api (aygıt: $($health.device) $($health.gpu), $($health.voices) ses)"

# ---------------------------------------------------------------- 6. deneme sesleri
Step 'Deneme sesleri (model ilk kez belleğe yükleniyor)'
$samples = @(
    @{ n = 'ingilizce'; t = 'Hello. This is the English voice of the AGFO editor. The audit report will be shared with the site within ten working days.' },
    @{ n = 'ispanyolca'; t = 'Hola. Esta es la voz en español del editor de AGFO. El informe de auditoría se compartirá con el centro en un plazo de diez días hábiles.' }
)
$okCount = 0
foreach ($smp in $samples) {
    $body = @{ text = $smp.t; voice = 'aiden' } | ConvertTo-Json
    $out = Join-Path $Desk ("agfo-ses-qwen-{0}.mp3" -f $smp.n)
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try {
        $r = Invoke-WebRequest "$Api/tts" -Method Post -Headers $hdr -ContentType 'application/json; charset=utf-8' `
             -Body ([Text.Encoding]::UTF8.GetBytes($body)) -OutFile $out -PassThru -UseBasicParsing -TimeoutSec 900 -ErrorAction Stop
        Ok ("{0}: {1} sn ses, {2} sn'de üretildi - {3}" -f $smp.n, $r.Headers['X-AGFO-Seconds'], [math]::Round($sw.Elapsed.TotalSeconds, 1), $out)
        $okCount++
    } catch {
        Fail "$($smp.n) deneme seslendirmesi başarısız: $($_.Exception.Message)"
        Get-Content (Join-Path $D 'service.log') -Tail 25 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
    }
}
if (-not $okCount) { Done 1 }
if ($gpu) {
    $mem = (& nvidia-smi --query-gpu=memory.used --format=csv,noheader 2>$null | Select-Object -First 1)
    if ($mem) { Write-Host "  Ekran kartı belleği (toplam kullanım): $mem" }
}

Step 'Bitti'
Write-Host '  AGFO AI Editor 2.14.0 ve üstü: Ses sekmesi › Ses servisi › Bu bilgisayar › Yerel ses › "Qwen3-TTS · …"'
Write-Host '  Hazır sesler: Aiden ve Ryan (anadili İngilizce), Serena, Vivian ve diğerleri. Metnin dili (İngilizce/İspanyolca) kendiliğinden seçilir.'
Write-Host "  Kendi sesiniz (ör. İspanyolca bir anlatıcı): ad.wav + ad.txt -> $D\data\voices  (izinli kayıt)"
Write-Host '  Kaldırmak için: AGFO-Ses-Qwen-Kur.cmd -Kaldir'
Done 0
