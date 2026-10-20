# AGFO erkek ses denemesi (Windows, ekran kartı)
# Aynı Türkçe metni EMA (bu bilgisayardaki AGFO Ses Servisi), Chatterbox Multilingual ve isteğe bağlı Piper "Cem" ile
# seslendirir; MP3'leri Masaüstü\agfo-ses-deneme klasörüne koyar. Çalışan ses servisine dokunmaz.
# Önce AGFO-Ses-Kur.cmd ile servis kurulmuş olmalı.
# Kullanım:  AGFO-Ses-Dene.cmd                          (sorular sorar)
#            AGFO-Ses-Dene.cmd -Referans C:\ses\ben.m4a  (Chatterbox bu sesi taklit eder)
#            AGFO-Ses-Dene.cmd -Kaldir                   (deneme ortamını siler, ~6 GB)
param([string]$Referans = '', [string]$HfToken = '', [switch]$Kaldir, [switch]$Sorma)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}
function Show { process { Write-Host "  $_" } }

$Src = $PSScriptRoot
$T = Join-Path $env:LOCALAPPDATA 'AGFO\TTS'
$B = Join-Path $env:LOCALAPPDATA 'AGFO\TTS-deneme'
$Py = Join-Path $B 'venv\Scripts\python.exe'
$Desk = [Environment]::GetFolderPath('Desktop')
$Out = Join-Path $Desk 'agfo-ses-deneme'
$Log = Join-Path $Desk 'agfo-ses-deneme-sonuc.txt'
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

function Find-Exe($name) {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links')
    $c = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return $c.Source }
    $hit = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages') -Recurse -Filter "$name.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($hit) { return $hit.FullName }
    return $null
}

if ($Kaldir) {
    Step 'Deneme ortamı siliniyor'
    if (Test-Path $B) { Remove-Item $B -Recurse -Force }
    Ok "Silindi: $B (ses servisi ve deneme MP3'leri yerinde)"
    Done 0
}

# ---------------------------------------------------------------- 1. ön kontroller
Step 'Ön kontroller'
if (-not (Test-Path (Join-Path $Src 'bench_win.py'))) { Fail "bench_win.py bu klasörde yok ($Src)."; Done 1 }
$envMap = @{}
if (Test-Path (Join-Path $T '.env')) {
    Get-Content (Join-Path $T '.env') -Encoding UTF8 | ForEach-Object { if ($_ -match '^\s*([^#=]+?)\s*=\s*(.*)$') { $envMap[$matches[1]] = $matches[2].Trim() } }
}
if (-not $envMap['AGFO_TTS_TOKEN']) { Fail 'Önce AGFO-Ses-Kur.cmd ile ses servisini kurun.'; Done 1 }
$ffmpeg = $envMap['AGFO_TTS_FFMPEG']
if (-not $ffmpeg -or -not (Test-Path $ffmpeg)) { $ffmpeg = Find-Exe 'ffmpeg' }
$uv = Find-Exe 'uv'
if (-not $uv -or -not $ffmpeg) { Fail 'uv veya ffmpeg bulunamadı; AGFO-Ses-Kur.cmd''yi yeniden çalıştırın.'; Done 1 }
$gpu = $null
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    $gpu = (& nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>$null | Select-Object -First 1)
}
if ($gpu) { Ok "Ekran kartı: $gpu" } else { Warn 'Ekran kartı yok; Chatterbox işlemcide çok yavaş çalışır.' }
$drive = (Split-Path -Qualifier $env:LOCALAPPDATA).TrimEnd(':')
$freeGB = [math]::Round((Get-PSDrive $drive).Free / 1GB, 1)
if ($freeGB -lt 10) { Fail "$drive`: sürücüsünde $freeGB GB boş; deneme için yaklaşık 10 GB gerekir."; Done 1 }
Ok "$freeGB GB boş"

# ---------------------------------------------------------------- 2. sorular
if (-not $Sorma) {
    if (-not $Referans) {
        Write-Host ''
        Write-Host '  Chatterbox, verdiğiniz kısa bir kaydın sesini taklit eder. Erkek ses için 10-25 saniyelik, gürültüsüz,'
        Write-Host '  Türkçe bir erkek konuşma kaydı gerekir (örneğin Windows Ses Kaydedici ile kendi sesiniz). Yalnız kendi'
        Write-Host '  sesinizi ya da sahibinin izin verdiği bir kaydı kullanın. Boş bırakırsanız yerleşik ses denenir.'
        $Referans = (Read-Host '  Referans ses dosyasının yolu (boş: yok)').Trim('"', ' ')
    }
    if (-not $HfToken) {
        Write-Host ''
        Write-Host '  Piper "Cem" için Hugging Face onayı ve okuma (Read) token''ı gerekir. Onay gelmediyse boş bırakın.'
        $sec = Read-Host '  Hugging Face token (boş: atla)' -AsSecureString
        $HfToken = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
    }
}

# ---------------------------------------------------------------- 3. ortam
Step 'Deneme ortamı (ilk seferde yaklaşık 5-6 GB indirilir)'
New-Item -ItemType Directory -Force -Path $B, $Out, (Join-Path $B 'hf'), (Join-Path $B 'model') | Out-Null
$env:UV_NO_CONFIG = '1'
& $uv python install 3.11 2>&1 | ForEach-Object { "$_" } | Show
if (-not (Test-Path $Py)) { & $uv venv --python 3.11 (Join-Path $B 'venv') 2>&1 | ForEach-Object { "$_" } | Show }
if (-not (Test-Path $Py)) { Fail 'Sanal ortam oluşturulamadı.'; Done 1 }
$idx = $(if ($gpu) { 'https://download.pytorch.org/whl/cu124' } else { 'https://download.pytorch.org/whl/cpu' })
& $uv pip install --python $Py --index-url https://pypi.org/simple --extra-index-url $idx --index-strategy unsafe-best-match chatterbox-tts==0.1.7 soundfile 2>&1 | ForEach-Object { "$_" } | Show
if ($LASTEXITCODE -ne 0) { Fail 'Chatterbox kurulamadı.'; Done 1 }
$probe = & $Py -c "import torch; print(torch.__version__, 'cuda' if torch.cuda.is_available() else 'cpu')" 2>$null
Ok "torch $probe"

# ---------------------------------------------------------------- 4. referans ses
$ref = ''
if ($Referans) {
    if (-not (Test-Path $Referans)) { Warn "Referans dosyası yok: $Referans - yerleşik ses denenecek." }
    else {
        $ref = Join-Path $B 'referans.wav'
        & $ffmpeg -loglevel error -y -i $Referans -ac 1 -ar 24000 -t 25 $ref
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $ref)) { Warn 'Referans ses dönüştürülemedi; yerleşik ses denenecek.'; $ref = '' }
        else { Ok 'Referans ses hazır (en çok 25 sn)' }
    }
}

# ---------------------------------------------------------------- 5. Piper Cem (isteğe bağlı)
$piper = ''
if ($HfToken) {
    Step 'Piper "Cem"'
    $h = @{ Authorization = "Bearer $HfToken" }
    try {
        $info = Invoke-RestMethod 'https://huggingface.co/api/models/dcx514ai/piper_tts_turkish_high' -Headers $h -ErrorAction Stop
        $files = @($info.siblings | ForEach-Object { $_.rfilename })
        Write-Host ('  Dosyalar: ' + ($files -join ', '))
        $onnx = $files | Where-Object { $_ -like '*.onnx' -and $_ -notlike '*.q8.onnx' } | Select-Object -First 1
        if (-not $onnx) { $onnx = $files | Where-Object { $_ -like '*.onnx' } | Select-Object -First 1 }
        $conf = $files | Where-Object { $_ -like '*.onnx.json' -or $_ -like '*config.json' } | Select-Object -First 1
        if (-not $onnx -or -not $conf) { Warn 'Bu depoda Piper model/yapılandırma çifti bulunamadı; dosya listesini Claude''a gönderin.' }
        else {
            $m = Join-Path $B ('model\' + (Split-Path $onnx -Leaf))
            foreach ($f in @($onnx, $conf)) {
                $dst = Join-Path $B ('model\' + (Split-Path $f -Leaf))
                Invoke-WebRequest "https://huggingface.co/dcx514ai/piper_tts_turkish_high/resolve/main/$f" -Headers $h -OutFile $dst -UseBasicParsing -ErrorAction Stop
            }
            if ((Split-Path $conf -Leaf) -ne ((Split-Path $onnx -Leaf) + '.json')) {
                Copy-Item (Join-Path $B ('model\' + (Split-Path $conf -Leaf))) "$m.json" -Force
            }
            & $uv pip install --python $Py piper-tts 2>&1 | ForEach-Object { "$_" } | Show
            if ($LASTEXITCODE -eq 0) { $piper = $m; Ok 'Piper Cem hazır' } else { Warn 'piper-tts kurulamadı; atlanıyor.' }
        }
    } catch { Warn "Piper Cem indirilemedi (onay henüz verilmemiş olabilir): $($_.Exception.Message)" }
}

# ---------------------------------------------------------------- 6. deneme
Step 'Seslendirme (Chatterbox ilk seferde ~2 GB model indirir)'
$env:HF_HOME = Join-Path $B 'hf'
$env:PYTHONIOENCODING = 'utf-8'
$a1 = $(if ($ref) { $ref } else { '-' }); $a2 = $(if ($piper) { $piper } else { '-' })
& $Py (Join-Path $Src 'bench_win.py') $Out $a1 $a2 2>&1 | ForEach-Object { "$_" } | Show
Step 'Bitti'
Write-Host "  Dosyalar: $Out"
Get-ChildItem $Out -Filter *.mp3 | ForEach-Object { Write-Host "   - $($_.Name)" }
Start-Process explorer.exe $Out
Write-Host '  Dinleyip hangisini beğendiğinizi yazın; bu çıktı dosyasını da gönderin.'
Write-Host '  Deneme ortamını silmek için:  AGFO-Ses-Dene.cmd -Kaldir'
Done 0
