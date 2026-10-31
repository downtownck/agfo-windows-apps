param(
  [ValidateSet('auto','gemma3:1b','gemma3:270m')][string]$Model='auto'
)
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$env:OLLAMA_HOST='127.0.0.1:11434'
$env:OLLAMA_NO_CLOUD='1'
$base=Join-Path $env:LOCALAPPDATA 'AGFO\SmartOrganizer'
New-Item -ItemType Directory -Force -Path $base | Out-Null
$log=Join-Path $base ('gemma-install-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.log')
$installer=$null
Start-Transcript -Path $log -Force | Out-Null
try {
  if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem) {
    throw '64-bit Windows 10/11 gerekli.'
  }
  if ($Model -eq 'auto') {
    $ram=(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
    $Model=if($ram -lt 6GB){'gemma3:270m'}else{'gemma3:1b'}
  }
  Write-Host "AGFO Gemma modeli: $Model"
  $cmd=Get-Command ollama.exe -ErrorAction SilentlyContinue
  $exe=if($cmd){$cmd.Source}else{$null}
  if(-not $exe){
    foreach($location in @((Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'),(Join-Path $env:ProgramFiles 'Ollama\ollama.exe'))){
      if(Test-Path -LiteralPath $location){$exe=$location;break}
    }
  }
  if(-not $exe){
    Write-Host 'Ollama resmi Windows yukleyicisi indiriliyor...'
    $installer=Join-Path $env:TEMP ("AGFO-Ollama-"+$PID+".exe")
    Invoke-WebRequest -Uri 'https://ollama.com/download/OllamaSetup.exe' -OutFile $installer -UseBasicParsing -TimeoutSec 1800
    if((Get-Item $installer).Length -lt 1000000){throw 'Indirme eksik.'}
    $sig=Get-AuthenticodeSignature -FilePath $installer
    if($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'Ollama'){
      throw ('Ollama imza dogrulamasi basarisiz: '+$sig.Status)
    }
    $proc=Start-Process -FilePath $installer -ArgumentList '/VERYSILENT','/NORESTART','/SUPPRESSMSGBOXES' -PassThru
    $proc.WaitForExit()
    if($proc.ExitCode -ne 0){throw ('Ollama kurulumu hata: '+$proc.ExitCode)}
    $exe=Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if(-not (Test-Path -LiteralPath $exe)){throw 'ollama.exe bulunamadi. Windows oturumunu yeniden acin.'}
  }
  $ready=$false
  for($i=0;$i -lt 15;$i++){
    try{$null=Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3;$ready=$true;break}catch{Start-Sleep -Seconds 2}
  }
  if(-not $ready){
    $null=Start-Process -FilePath $exe -ArgumentList 'serve' -WindowStyle Hidden -PassThru
    for($i=0;$i -lt 30;$i++){
      try{$null=Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3;$ready=$true;break}catch{Start-Sleep -Seconds 2}
    }
  }
  if(-not $ready){throw 'Ollama yerel API baslamadi.'}
  & $exe pull $Model
  if($LASTEXITCODE -ne 0){throw 'Model indirilemedi.'}
  $models=Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5
  if(-not @($models.models | Where-Object {$_.name -eq $Model -or $_.model -eq $Model}).Count){
    throw 'Model dogrulamasi basarisiz.'
  }
  $settingsPath=Join-Path $base 'settings.json'
  if(Test-Path $settingsPath){
    try{$settings=Get-Content $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json}catch{
      throw 'Var olan ayar dosyasi okunamadi; uzerine yazilmadi.'
    }
    if($settings.ollama_model -and $settings.ollama_model -notin @('qwen2.5:3b','gemma3:1b','gemma3:270m')){
      Write-Warning ('Ozel AI model tercihi korundu: '+$settings.ollama_model)
      $settings=$null
    }else{
      Copy-Item $settingsPath ($settingsPath+'.bak-'+(Get-Date -Format 'yyyyMMddHHmmss'))
    }
  }else{$settings=[pscustomobject]@{ollama_model=$Model;ai_limit='30'}}
  if($settings){
    if($settings.PSObject.Properties['ollama_model']){$settings.ollama_model=$Model}
    else{$settings | Add-Member -NotePropertyName ollama_model -NotePropertyValue $Model}
    $tmp=$settingsPath+'.tmp'
    [IO.File]::WriteAllText($tmp,($settings | ConvertTo-Json -Depth 12),(New-Object Text.UTF8Encoding($false)))
    Move-Item $tmp $settingsPath -Force
  }
  Write-Host "BASARILI - Model: $Model" -ForegroundColor Green
  Write-Host "Smart Organizer'da Hizli analiz et > Yerel AI ile iyilestir."
}catch{
  Write-Host ('HATA: '+$_.Exception.Message) -ForegroundColor Red
  exit 1
}finally{
  if($installer -and (Test-Path $installer)){Remove-Item $installer -Force -ErrorAction SilentlyContinue}
  Stop-Transcript | Out-Null
}
