# -*- coding: utf-8 -*-
"""AGFO AI Editor - GitHub'dan tek tikla guncelleme, kurulum ve kaldirma (yonetici yetkisi gerekmez).

Uygulama tek dosyalik bir EXE'dir (PyInstaller onefile). Kurulum: kullanicinin
%LOCALAPPDATA%\\Programs\\AGFO-AI-Editor klasorune kopyalanir, Baslat menusu (ve istenirse masaustu)
kisayolu olusturulur. Guncelleme: yeni EXE GitHub Releases'ten indirilir, SHA-256 ile dogrulanir;
uygulama kapandiktan sonra kucuk bir PowerShell betigi dosyayi degistirip uygulamayi yeniden acar.
Alt sureclere PyInstaller ortam degiskenleri (_PYI_*, _MEIPASS2) gecirilmez.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

import agfo_editor_core as core
import agfo_github_update as ghu

GH_PREFIX = 'ai-editor-v'
GH_ASSET = r'AGFO-AI-Editor\.exe'
EXE_NAME = 'AGFO-AI-Editor.exe'
USER_AGENT = 'AGFO-AI-Editor/%s' % core.VERSION
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008


def install_dir() -> pathlib.Path:
    base = os.environ.get('LOCALAPPDATA') or str(pathlib.Path.home())
    return pathlib.Path(base) / 'Programs' / 'AGFO-AI-Editor'


def installed_exe() -> pathlib.Path:
    return install_dir() / EXE_NAME


def is_frozen() -> bool:
    return bool(getattr(sys, 'frozen', False))


def running_installed(executable=None) -> bool:
    exe = pathlib.Path(executable or sys.executable)
    try:
        return is_frozen() and exe.resolve() == installed_exe().resolve()
    except OSError:
        return False


def state_path() -> pathlib.Path:
    return core.data_dir() / 'github-update.json'


def updates_dir() -> pathlib.Path:
    p = core.data_dir() / 'updates'
    p.mkdir(parents=True, exist_ok=True)
    return p


def scrub_env(env=None) -> dict:
    src = os.environ if env is None else env
    out = {k: v for k, v in src.items() if not k.upper().startswith(('_PYI_', '_MEIPASS'))}
    out['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return out


def check(force=False, releases=None) -> dict:
    return ghu.check_for_update(GH_PREFIX, core.VERSION, state_path(), GH_ASSET, force=force,
                                releases=releases, user_agent=USER_AGENT)


def download(result: dict, progress=None, should_stop=None) -> pathlib.Path:
    rel, asset = result['release'], result['asset']
    sha = ghu.expected_sha256(rel, asset, user_agent=USER_AGENT)
    dest = updates_dir() / ('AGFO-AI-Editor-%s.exe' % result['version'])
    ghu.download_asset(asset, dest, sha, progress, should_stop, user_agent=USER_AGENT)
    return dest


def _ps_quote(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def replace_script(new_exe, target_exe, pid: int, relaunch: bool = True) -> str:
    """Uygulama kapaninca EXE'yi degistiren PowerShell betigi (mesajlar Ingilizce: konsol kodlamasi)."""
    lines = [
        "$ErrorActionPreference = 'Stop'",
        "$log = Join-Path $env:LOCALAPPDATA 'AGFO-AI-Editor\\update-last.txt'",
        "function Log($m) { try { Add-Content -LiteralPath $log -Value ((Get-Date -Format s) + ' ' + $m) } catch { } }",
        "try {",
        "  $p = Get-Process -Id %d -ErrorAction SilentlyContinue" % int(pid),
        "  if ($p) { [void]$p.WaitForExit(60000) }",
        "  $new = %s" % _ps_quote(new_exe),
        "  $dst = %s" % _ps_quote(target_exe),
        "  $bak = $dst + '.old'",
        "  [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($dst))",
        "  $ok = $false",
        "  for ($i = 0; $i -lt 40 -and -not $ok; $i++) {",
        "    try {",
        "      if (Test-Path -LiteralPath $dst) { Copy-Item -LiteralPath $dst -Destination $bak -Force }",
        "      Copy-Item -LiteralPath $new -Destination $dst -Force",
        "      $ok = $true",
        "    } catch { Start-Sleep -Milliseconds 750 }",
        "  }",
        "  if (-not $ok) { throw 'File is locked; update could not be applied.' }",
        "  Remove-Item -LiteralPath $bak -Force -ErrorAction SilentlyContinue",
        "  Log ('Updated: ' + $dst)",
    ]
    if relaunch:
        lines += [
            "  Get-ChildItem Env: | Where-Object { $_.Name -like '_PYI_*' -or $_.Name -like '_MEIPASS*' } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }",
            "  $env:PYINSTALLER_RESET_ENVIRONMENT = '1'",
            "  Start-Process -FilePath $dst",
        ]
    lines += [
        "} catch {",
        "  Log ('Update failed: ' + $_.Exception.Message)",
        "  if (Test-Path -LiteralPath ($dst + '.old')) { Copy-Item -LiteralPath ($dst + '.old') -Destination $dst -Force -ErrorAction SilentlyContinue }",
        "}",
        "Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue",
    ]
    return '\r\n'.join(lines) + '\r\n'


def _powershell() -> str:
    root = os.environ.get('SystemRoot', r'C:\Windows')
    return str(pathlib.Path(root) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe')


def _run_detached_script(script_text: str, popen=subprocess.Popen) -> None:
    fd, path = tempfile.mkstemp(prefix='agfo-editor-', suffix='.ps1')
    with os.fdopen(fd, 'w', encoding='utf-8-sig') as f:
        f.write(script_text)
    popen([_powershell(), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden', '-File', path],
          env=scrub_env(), close_fds=True, creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS)


def apply_update(new_exe, popen=subprocess.Popen) -> pathlib.Path:
    """Calisan EXE'yi uygulama kapaninca yenisiyle degistirir. Cagiran uygulama hemen kapanmalidir.

    Not: onefile EXE'de dosyayi tutan ust surec, Python sureci kapaninca biraz sonra cikar; betik
    kilit kalkana kadar ~30 sn yeniden dener."""
    if not is_frozen():
        raise OSError('Güncelleme yalnızca derlenmiş EXE için uygulanabilir.')
    target = pathlib.Path(sys.executable)
    _run_detached_script(replace_script(new_exe, target, os.getpid()), popen)
    return target


def shortcut_script(target_exe, desktop: bool) -> str:
    lines = [
        "$ErrorActionPreference = 'Stop'",
        "$shell = New-Object -ComObject WScript.Shell",
        "$exe = %s" % _ps_quote(target_exe),
        "$menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'AGFO'",
        "[void][System.IO.Directory]::CreateDirectory($menu)",
        "$targets = @((Join-Path $menu 'AGFO AI Editor.lnk'))",
    ]
    if desktop:
        lines.append("$targets += (Join-Path ([Environment]::GetFolderPath('Desktop')) 'AGFO AI Editor.lnk')")
    lines += [
        "foreach ($t in $targets) {",
        "  $l = $shell.CreateShortcut($t); $l.TargetPath = $exe; $l.WorkingDirectory = [System.IO.Path]::GetDirectoryName($exe)",
        "  $l.Description = 'AGFO AI Editor'; $l.IconLocation = $exe + ',0'; $l.Save()",
        "}",
    ]
    return '\r\n'.join(lines) + '\r\n'


def install_self(desktop: bool = True, run=subprocess.run) -> pathlib.Path:
    """Calisan EXE'yi kullanici klasorune kurar ve kisayol olusturur (yonetici gerekmez)."""
    if not is_frozen():
        raise OSError('Kurulum yalnızca derlenmiş EXE ile yapılabilir.')
    import shutil
    dst = installed_exe()
    dst.parent.mkdir(parents=True, exist_ok=True)
    if pathlib.Path(sys.executable).resolve() != dst.resolve():
        shutil.copy2(sys.executable, dst)
    fd, path = tempfile.mkstemp(prefix='agfo-editor-lnk-', suffix='.ps1')
    with os.fdopen(fd, 'w', encoding='utf-8-sig') as f:
        f.write(shortcut_script(dst, desktop))
    try:
        proc = run([_powershell(), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', path],
                   capture_output=True, text=True, timeout=60, env=scrub_env(), creationflags=CREATE_NO_WINDOW)
        if proc.returncode:
            raise OSError('Kısayol oluşturulamadı: ' + (proc.stderr or proc.stdout or '')[-400:])
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    return dst


def uninstall_script() -> str:
    lines = [
        "$ErrorActionPreference = 'SilentlyContinue'",
        "Start-Sleep -Seconds 2",
        "Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath('Programs')) 'AGFO\\AGFO AI Editor.lnk') -Force",
        "Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath('Desktop')) 'AGFO AI Editor.lnk') -Force",
        "Remove-Item -LiteralPath %s -Recurse -Force" % _ps_quote(install_dir()),
        "Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force",
    ]
    return '\r\n'.join(lines) + '\r\n'


def uninstall(popen=subprocess.Popen) -> None:
    """Program dosyasini ve kisayollari kaldirir; ayarlar ve kurtarma kayitlari korunur."""
    _run_detached_script(uninstall_script(), popen)


def cleanup_downloads(keep=None) -> None:
    for f in updates_dir().glob('AGFO-AI-Editor-*.exe'):
        if keep is None or f.resolve() != pathlib.Path(keep).resolve():
            try:
                f.unlink()
            except OSError:
                pass
