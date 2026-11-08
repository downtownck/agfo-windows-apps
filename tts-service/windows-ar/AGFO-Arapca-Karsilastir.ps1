# AGFO Arapça ses karşılaştırması - Mısırlı dinleyiciler için aksan seçenekleri.
#   Habibi-TTS: Mısır (EGY) ve Fusha (MSA) modelleri (Apache-2.0), ayrı klasöre: %LOCALAPPDATA%\AGFO\TTS-HABIBI
#   SILMA: önceki denemedeki model, bu kez Mısırlı bir referans sesle (kurulu ise)
# Sesler: Masaüstü\AGFO-Arapca-Karsilastirma
# Kullanım:  AGFO-Arapca-Karsilastir.cmd           kur + karşılaştırma seslerini üret
#            AGFO-Arapca-Karsilastir.cmd -Kaldir   Habibi kurulumunu kaldır
param([switch]$Kaldir, [int]$Adim = 32)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}

$Src = $PSScriptRoot
$D = Join-Path $env:LOCALAPPDATA 'AGFO\TTS-HABIBI'
$Py = Join-Path $D 'venv\Scripts\python.exe'
$SilmaD = Join-Path $env:LOCALAPPDATA 'AGFO\TTS-AR'
$SilmaPy = Join-Path $SilmaD 'venv\Scripts\python.exe'
$Desk = [Environment]::GetFolderPath('Desktop')
$Out = Join-Path $Desk 'AGFO-Arapca-Karsilastirma'
$Log = Join-Path $Desk 'agfo-arapca-karsilastir-sonuc.txt'
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
function Quiet { process { if ($_ -notmatch '^\s*\d+%\||RemoteException|Redirects are currently not supported|^\s*warnings\.warn|torchaudio\\_backend|UserWarning|FutureWarning') { $_ } } }
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

if ($Kaldir) {
    Step 'Kaldırılıyor'
    if (Test-Path $D) { Remove-Item $D -Recurse -Force }
    Ok 'Habibi kurulumu kaldırıldı (SILMA ve masaüstündeki sesler duruyor).'
    Done 0
}

# ---------------------------------------------------------------- 1. ön kontroller ve araçlar
Step 'Ön kontroller'
if (-not (Test-Path (Join-Path $Src 'karsilastir.py'))) { Fail "karsilastir.py bu klasörde yok ($Src). ZIP'in tamamını çıkarın."; Done 1 }
$gpu = $null
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    $gpu = (& nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>$null | Select-Object -First 1)
}
if ($gpu) { Ok "Ekran kartı: $gpu" } else { Warn 'NVIDIA ekran kartı bulunamadı; işlemcide çok yavaş olur.' }
$ffmpeg = Find-Exe 'ffmpeg'
if (-not $ffmpeg) { Write-Host '  ffmpeg kuruluyor…'; [void](Winget-Install 'Gyan.FFmpeg'); $ffmpeg = Find-Exe 'ffmpeg' }
$uv = Find-Exe 'uv'
if (-not $uv) { Write-Host '  uv kuruluyor…'; [void](Winget-Install 'astral-sh.uv'); $uv = Find-Exe 'uv' }
if (-not $ffmpeg -or -not $uv) { Fail 'ffmpeg ya da uv kurulamadı; bilgisayarı yeniden başlatıp tekrar deneyin.'; Done 1 }
Ok "ffmpeg ve uv hazır"

# ---------------------------------------------------------------- 2. Habibi-TTS
Step 'Habibi-TTS (ilk kurulumda birkaç GB indirilir)'
New-Item -ItemType Directory -Force -Path $D, (Join-Path $D 'hf'), $Out | Out-Null
Copy-Item (Join-Path $Src 'karsilastir.py') (Join-Path $D 'karsilastir.py') -Force
$env:UV_NO_CONFIG = '1'
& $uv python install 3.12 2>&1 | ForEach-Object { "$_" } | Show
if (-not (Test-Path $Py)) {
    & $uv venv --python 3.12 (Join-Path $D 'venv') 2>&1 | ForEach-Object { "$_" } | Show
    if (-not (Test-Path $Py)) { Fail 'Sanal ortam oluşturulamadı.'; Done 1 }
}
if ($gpu) { $idx = 'https://download.pytorch.org/whl/cu126' } else { $idx = 'https://download.pytorch.org/whl/cpu' }
& $uv pip install --python $Py torch==2.8.0 torchaudio==2.8.0 torchvision==0.23.0 --index-url $idx 2>&1 | ForEach-Object { "$_" } | Show
if ($LASTEXITCODE -ne 0) { Fail 'PyTorch kurulamadı.'; Done 1 }
$cons = Join-Path $D 'constraints.txt'
[IO.File]::WriteAllText($cons, "torch==2.8.0`ntorchaudio==2.8.0`ntorchvision==0.23.0`n", (New-Object Text.UTF8Encoding($false)))
& $uv pip install --python $Py -c $cons --extra-index-url $idx --index-strategy unsafe-best-match habibi-tts 2>&1 | ForEach-Object { "$_" } | Show
if ($LASTEXITCODE -ne 0) {
    Warn 'Tam kurulum olmadı; Windows''ta sorun çıkaran isteğe bağlı paketler olmadan yeniden deneniyor…'
    & $uv pip install --python $Py --no-deps habibi-tts f5-tts 2>&1 | ForEach-Object { "$_" } | Show
    & $uv pip install --python $Py -c $cons --extra-index-url $idx --index-strategy unsafe-best-match `
        accelerate cached_path click datasets 'ema_pytorch>=0.5.2' 'hydra-core>=1.3.0' librosa matplotlib pydub pypinyin rjieba `
        safetensors soundfile tomli torchdiffeq 'tqdm>=4.65.0' transformers transformers_stream_generator unidecode vocos wandb `
        'x_transformers>=1.31.14' 2>&1 | ForEach-Object { "$_" } | Show
    if ($LASTEXITCODE -ne 0) { Fail 'Habibi-TTS kurulamadı.'; Done 1 }
}
$probe = ((& $Py -c "import torch, habibi_tts, f5_tts.infer.utils_infer; print(torch.__version__, 'cuda' if torch.cuda.is_available() else 'cpu')" 2>&1 | Quiet) -join ' ')
if ($LASTEXITCODE -ne 0) { Fail "Paketler yüklenemedi: $probe"; Done 1 }
Ok "torch $probe"

Step 'Habibi sesleri (Mısır ve Fusha modelleri; ilk seferde model dosyaları iner)'
$env:HF_HOME = Join-Path $D 'hf'
$env:PYTHONIOENCODING = 'utf-8'
$env:Path = (Split-Path $ffmpeg) + ';' + $env:Path
& $Py (Join-Path $D 'karsilastir.py') --cikti (Join-Path $Out 'habibi') --ffmpeg $ffmpeg --adim "$Adim" 2>&1 | ForEach-Object { "$_" } | Quiet | Show
$habOk = ($LASTEXITCODE -eq 0)
if (-not $habOk) { Warn 'Habibi seslerinin bir kısmı üretilemedi (ayrıntı yukarıda).' }

# ---------------------------------------------------------------- 3. SILMA, Mısırlı referans sesle
Step 'SILMA, Mısırlı referans sesle'
$egy = Join-Path $Out 'habibi\referans-egy.mp3'
if ((Test-Path $SilmaPy) -and (Test-Path (Join-Path $SilmaD 'dene_arapca.py')) -and (Test-Path $egy)) {
    Copy-Item (Join-Path $Src 'dene_arapca.py') (Join-Path $SilmaD 'dene_arapca.py') -Force -ErrorAction SilentlyContinue
    $env:HF_HOME = Join-Path $SilmaD 'hf'
    $egyText = 'ايه الكلام. بقولك ايه. استخدم صوتي في المحادثات. استخدمه هيعجبك اوي.'
    & $SilmaPy (Join-Path $SilmaD 'dene_arapca.py') --ses $egy --ses-metni $egyText --cikti (Join-Path $Out 'silma-misirli-ses') `
        --ffmpeg $ffmpeg --adim 32 2>&1 | ForEach-Object { "$_" } | Quiet | Where-Object { $_ -notmatch '^\s*(Input text|Text chunk|Generating audio|Converting ref|Using cached|Audio is below|vocab|token|model)\b' } | Show
} else {
    Warn 'SILMA denemesi kurulu değil ya da Mısırlı referans ses üretilemedi; bu adım atlandı.'
}

Step 'Bitti'
Write-Host "  Sesler: $Out"
Write-Host '    habibi\A-misir-modeli-fusha-metin.mp3   Mısır modeli, Fusha denetim metni (Mısır aksanlı Fusha)'
Write-Host '    habibi\B-misir-modeli-misir-agzi.mp3    Mısır modeli, aynı içerik Mısır ağzıyla'
Write-Host '    habibi\C-fusha-modeli.mp3               Fusha modeli'
Write-Host '    silma-misirli-ses\*.mp3                 SILMA, Mısırlı referans sesle'
Write-Host '  Mısırlı arkadaşlara dinletin; hangisinin seçildiğini bana yazın.'
Done 0
