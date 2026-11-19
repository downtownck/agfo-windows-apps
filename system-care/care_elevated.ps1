param(
 [Parameter(Mandatory=$true)][string]$ArgsB64,
 [Parameter(Mandatory=$true)][string]$OutFile,
 [string]$Cwd = ''
)
# AGFO System Care 4.0 yonetici yardimcisi: uygulama normal kullaniciyla calisir; yonetici isteyen TEK bir islem icin
# Windows UAC onayi alinir ve bu betik o komutu yonetici olarak calistirip ciktisini OutFile'a yazar (uygulama canli izler).
# Komut, degistirilemeyen surec komut satirindan (base64 JSON) okunur; dosyadan okunmaz.
$ErrorActionPreference = 'Stop'
$enc = [Text.UTF8Encoding]::new($false)
function QuoteArg([string]$a) {
 if ($a -eq '') { return '""' }
 if ($a -notmatch '[\s"]') { return $a }
 $r = '"'; $bs = 0
 foreach ($ch in $a.ToCharArray()) {
  if ($ch -eq '\') { $bs++; continue }
  if ($ch -eq '"') { $r += ('\' * ($bs * 2 + 1)) + '"'; $bs = 0; continue }
  $r += ('\' * $bs) + $ch; $bs = 0
 }
 return $r + ('\' * ($bs * 2)) + '"'
}
$w = [IO.StreamWriter]::new($OutFile, $false, $enc)
$w.AutoFlush = $true
$code = 1
try {
 $parsed = ConvertFrom-Json ($enc.GetString([Convert]::FromBase64String($ArgsB64)))
 $argv = @()
 foreach ($x in $parsed) { $argv += [string]$x }               # PS 5.1 diziyi tek nesne olarak dondurur; foreach elemanlara acar
 if ($argv.Count -lt 1) { throw 'komut yok' }
 if ($Cwd -and (Test-Path -LiteralPath $Cwd -PathType Container)) { Set-Location -LiteralPath $Cwd }
 $psi = [Diagnostics.ProcessStartInfo]::new([string]$argv[0])
 $rest = @(); if ($argv.Count -gt 1) { $rest = $argv[1..($argv.Count - 1)] }
 $psi.Arguments = (@($rest | ForEach-Object { QuoteArg ([string]$_) })) -join ' '
 $psi.UseShellExecute = $false
 $psi.CreateNoWindow = $true
 $psi.RedirectStandardOutput = $true
 $psi.RedirectStandardError = $true
 $psi.StandardOutputEncoding = $enc
 $psi.StandardErrorEncoding = $enc
 if ($Cwd) { $psi.WorkingDirectory = $Cwd }
 $p = [Diagnostics.Process]::Start($psi)
 $err = $p.StandardError.ReadToEndAsync()
 while ($null -ne ($line = $p.StandardOutput.ReadLine())) { $w.WriteLine($line) }
 $p.WaitForExit()
 $e = $err.Result
 if ($e) { $w.WriteLine($e.TrimEnd()) }
 $code = $p.ExitCode
} catch {
 $w.WriteLine('HATA (yonetici yardimcisi): ' + $_.Exception.Message)
 $code = 1
} finally { $w.Close() }
exit $code
