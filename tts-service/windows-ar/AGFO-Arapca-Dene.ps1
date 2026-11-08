# AGFO Arapça ses denemesi - SILMA TTS (Apache-2.0, Arapça + İngilizce) bu bilgisayarın NVIDIA ekran kartında.
# Ayrı bir klasöre kurulur, Türkçe ses servisine (AGFO-Ses-Kur) dokunmaz:  %LOCALAPPDATA%\AGFO\TTS-AR
# Kullanım:  AGFO-Arapca-Dene.cmd                                   kur + örnek sesleri üret
#            AGFO-Arapca-Dene.cmd -Ses C:\kayit.wav -SesMetni "..."  kendi referans sesinizle
#            AGFO-Arapca-Dene.cmd -Kaldir                            kaldır
param([switch]$Kaldir, [string]$Ses = '', [string]$SesMetni = '', [int]$Adim = 16)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}

$Src = $PSScriptRoot
$D = Join-Path $env:LOCALAPPDATA 'AGFO\TTS-AR'
$Py = Join-Path $D 'venv\Scripts\python.exe'
$Desk = [Environment]::GetFolderPath('Desktop')
$Log = Join-Path $Desk 'agfo-arapca-dene-sonuc.txt'
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

if ($Kaldir) {
    Step 'Kaldırılıyor'
    if (Test-Path $D) { Remove-Item $D -Recurse -Force }
    Ok 'Arapça deneme ortamı kaldırıldı (masaüstündeki örnek sesler duruyor).'
    Done 0
}

# ---------------------------------------------------------------- 1. ön kontroller
Step 'Ön kontroller'
if (-not (Test-Path (Join-Path $Src 'dene_arapca.py'))) { Fail "dene_arapca.py bu klasörde yok ($Src). ZIP'in tamamını çıkarın."; Done 1 }
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { Fail 'winget bulunamadı. Microsoft Store''dan "Uygulama Yükleyici"yi güncelleyin.'; Done 1 }
$gpu = $null
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    $gpu = (& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>$null | Select-Object -First 1)
}
if ($gpu) { Ok "Ekran kartı: $gpu" } else { Warn 'NVIDIA ekran kartı bulunamadı; deneme işlemcide çok yavaş olur.' }
$drive = (Split-Path -Qualifier $env:LOCALAPPDATA).TrimEnd(':')
$freeGB = [math]::Round((Get-PSDrive $drive).Free / 1GB, 1)
if ($freeGB -lt 10) { Fail "$drive`: sürücüsünde $freeGB GB boş; yaklaşık 10 GB gerekir."; Done 1 }
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
Step 'Python 3.12 ve paketler (ilk kurulumda yaklaşık 5 GB indirilir)'
New-Item -ItemType Directory -Force -Path $D, (Join-Path $D 'hf') | Out-Null
Copy-Item (Join-Path $Src 'dene_arapca.py') (Join-Path $D 'dene_arapca.py') -Force
$env:UV_NO_CONFIG = '1'
& $uv python install 3.12 2>&1 | ForEach-Object { "$_" } | Show
if (-not (Test-Path $Py)) {
    & $uv venv --python 3.12 (Join-Path $D 'venv') 2>&1 | ForEach-Object { "$_" } | Show
    if (-not (Test-Path $Py)) { Fail 'Sanal ortam oluşturulamadı.'; Done 1 }
}
if ($gpu) { $idx = 'https://download.pytorch.org/whl/cu126' } else { $idx = 'https://download.pytorch.org/whl/cpu' }
# torchaudio 2.9 ses okumayı torchcodec'e devretti (Windows'ta ayrı FFmpeg DLL'leri ister); 2.8 sabitlenir
Write-Host "  PyTorch 2.8 ($idx)…"
& $uv pip install --python $Py torch==2.8.0 torchaudio==2.8.0 torchvision==0.23.0 --index-url $idx 2>&1 | ForEach-Object { "$_" } | Show
if ($LASTEXITCODE -ne 0) { Fail 'PyTorch kurulamadı.'; Done 1 }
$cons = Join-Path $D 'constraints.txt'
[IO.File]::WriteAllText($cons, "torch==2.8.0`ntorchaudio==2.8.0`ntorchvision==0.23.0`n", (New-Object Text.UTF8Encoding($false)))
# silma-tts bagimliliklari: nemo_text_processing (pynini) Windows'ta kurulamaz; yerine sayilar num2words ile yaziya cevrilir
Write-Host '  SILMA TTS ve bağımlılıkları…'
& $uv pip install --python $Py --no-deps silma-tts 2>&1 | ForEach-Object { "$_" } | Show
if ($LASTEXITCODE -ne 0) { Fail 'silma-tts indirilemedi.'; Done 1 }
$ort = $(if ($gpu) { 'onnxruntime-gpu' } else { 'onnxruntime' })
& $uv pip install --python $Py -c $cons --extra-index-url $idx --index-strategy unsafe-best-match `
    cached_path click 'ema_pytorch>=0.5.2' 'hydra-core>=1.3.0' librosa matplotlib 'numpy<=1.26.4' pydub safetensors soundfile tomli `
    torchdiffeq 'tqdm>=4.65.0' transformers transformers_stream_generator unidecode vocos 'x_transformers>=1.31.14' num2words $ort 2>&1 |
    ForEach-Object { "$_" } | Show
if ($LASTEXITCODE -ne 0) { Fail 'Bağımlılıklar kurulamadı.'; Done 1 }
& $uv pip install --python $Py --no-deps catt_tashkeel==1.0.2 2>&1 | ForEach-Object { "$_" } | Show
# nemo_text_processing yerine bos bir normalizer (metin oldugu gibi gecer)
$site = ((& $Py -c "import sysconfig; print(sysconfig.get_paths()['purelib'])") -join '').Trim()
$stub = Join-Path $site 'nemo_text_processing\text_normalization'
New-Item -ItemType Directory -Force -Path $stub | Out-Null
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText((Join-Path $site 'nemo_text_processing\__init__.py'), "# AGFO: Windows icin bos yer tutucu (pynini Windows'ta yok)`n", $utf8)
[IO.File]::WriteAllText((Join-Path $stub '__init__.py'), "", $utf8)
[IO.File]::WriteAllText((Join-Path $stub 'normalize.py'), "class Normalizer:`n    def __init__(self, *a, **k):`n        pass`n`n    def normalize(self, text, *a, **k):`n        return text`n", $utf8)
$probe = ((& $Py -c "import torch, silma_tts.api; print(torch.__version__, 'cuda' if torch.cuda.is_available() else 'cpu')" 2>&1) -join ' ')
if ($LASTEXITCODE -ne 0) { Fail "Paketler yüklenemedi: $probe"; Done 1 }
Ok "torch $probe"
if ($gpu -and $probe -notmatch 'cuda') { Warn 'PyTorch ekran kartını görmüyor; NVIDIA sürücüsünü güncelleyin. Deneme işlemcide yapılacak.' }

# ---------------------------------------------------------------- 4. deneme
Step 'Örnek sesler üretiliyor (ilk seferde ses modeli indirilir)'
$env:HF_HOME = Join-Path $D 'hf'
$env:AGFO_TTS_FFMPEG = $ffmpeg
$env:PYTHONIOENCODING = 'utf-8'
$env:Path = (Split-Path $ffmpeg) + ';' + $env:Path          # pydub ffmpeg'i PATH'te arar
$Out = Join-Path $Desk 'AGFO-Arapca-Deneme'        # OneDrive'a tasinmis masaustu de dogru bulunur
$pyArgs = @((Join-Path $D 'dene_arapca.py'), '--ffmpeg', $ffmpeg, '--adim', "$Adim", '--cikti', $Out)
if ($Ses) {
    if (-not (Test-Path $Ses)) { Fail "Referans ses bulunamadı: $Ses"; Done 1 }
    $pyArgs += @('--ses', $Ses)
    if ($SesMetni) { $pyArgs += @('--ses-metni', $SesMetni) }
}
& $Py @pyArgs 2>&1 | ForEach-Object { "$_" } | Where-Object { $_ -notmatch '^\s*\d+%\|' -and $_ -notmatch 'RemoteException|Redirects are currently not supported|^\s*warnings\.warn|torchaudio\\_backend' } | Show
if ($LASTEXITCODE -ne 0) { Fail 'Deneme tamamlanamadı (ayrıntı yukarıda).'; Done 1 }

Step 'Bitti'
Write-Host "  Sesleri dinleyin: $Out"
Write-Host '  Beğenirseniz Arapça ses, AGFO Ses Servisi''ne ikinci dil olarak eklenecek (editörde ve AI Manager''da seçilebilir).'
Write-Host '  Kendi sesinizle: AGFO-Arapca-Dene.cmd -Ses C:\kayit.wav -SesMetni "kayıttaki cümle"'
Write-Host '  Kaldırmak için: AGFO-Arapca-Dene.cmd -Kaldir'
Done 0
