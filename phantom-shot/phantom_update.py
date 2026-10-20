# -*- coding: utf-8 -*-
"""AGFO Phantom Shot - GitHub'dan tek tikla guncelleme, kurulum ve kaldirma (yonetici gerekmez).

Uygulama tek dosyalik bir EXE'dir (PyInstaller onefile). Guncelleme: yeni EXE GitHub Releases'ten
indirilir, SHA-256 ile dogrulanir; uygulama kapandiktan sonra yeni EXE kendini eski dosyanin uzerine
kopyalar ve uygulamayi yeniden acar. Alt sureclere PyInstaller ortam degiskenleri (_PYI_*, _MEIPASS2)
gecirilmez. Guven koku GitHub hesabidir; kod imzasi degildir.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import phantom_core as core
import agfo_github_update as ghu

GH_PREFIX = 'phantom-shot-v'
GH_ASSET = r'AGFO-Phantom-Shot\.exe'
EXE_NAME = 'AGFO-Phantom-Shot.exe'
USER_AGENT = 'AGFO-Phantom-Shot/%s' % core.VERSION
CHECK_INTERVAL = 6 * 3600

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


def install_dir() -> pathlib.Path:
    base = os.environ.get('LOCALAPPDATA') or str(pathlib.Path.home())
    return pathlib.Path(base) / 'Programs' / 'AGFO-Phantom-Shot'


def installed_exe() -> pathlib.Path:
    return install_dir() / EXE_NAME


def is_frozen() -> bool:
    return bool(getattr(sys, 'frozen', False))


def state_path() -> pathlib.Path:
    return core.data_dir() / 'github-update.json'


def updates_dir() -> pathlib.Path:
    p = core.data_dir() / 'updates'
    p.mkdir(parents=True, exist_ok=True)
    return p


def log_path() -> pathlib.Path:
    return core.data_dir() / 'update-log.txt'


def log_line(text: str) -> None:
    import datetime
    try:
        with open(log_path(), 'a', encoding='utf-8') as f:
            f.write('%s %s\n' % (datetime.datetime.now().isoformat(timespec='seconds'), text))
    except OSError:
        pass


def scrub_env(env=None) -> dict:
    """Alt surece PyInstaller onefile ic degiskenlerini gecirme (yoksa yeni EXE bozuk acilir)."""
    src = os.environ if env is None else env
    out = {k: v for k, v in src.items() if not k.upper().startswith(('_PYI_', '_MEIPASS'))}
    out['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return out


def package_ready(release: dict, asset: dict) -> bool:
    """Guncelleme gercekten kurulabilir mi: EXE var ve SHA-256 ozeti (GitHub ozeti ya da SHA256SUMS.txt) yayinlanmis."""
    if not asset or not asset.get('url'):
        return False
    if asset.get('sha256'):
        return True
    return ghu.pick_asset(release, r'SHA256SUMS(\.txt)?') is not None


def check(force=False, releases=None) -> dict:
    """Hata firlatmaz. 'update' yalniz paket indirilebilir ve dogrulanabilir oldugunda doner."""
    res = ghu.check_for_update(GH_PREFIX, core.VERSION, state_path(), GH_ASSET, force=force,
                               interval=CHECK_INTERVAL, releases=releases, user_agent=USER_AGENT)
    if res.get('status') == 'update' and not package_ready(res.get('release') or {}, res.get('asset') or {}):
        return {'status': 'error', 'version': res.get('version'),
                'message': 'v%s yayınlanmış ama güncelleme paketi henüz hazır değil (SHA-256 özeti yok).'
                           % res.get('version')}
    return res


def download(result: dict, progress=None, should_stop=None) -> pathlib.Path:
    rel, asset = result['release'], result['asset']
    sha = ghu.expected_sha256(rel, asset, user_agent=USER_AGENT)
    dest = updates_dir() / ('AGFO-Phantom-Shot-%s.exe' % result['version'])
    ghu.download_asset(asset, dest, sha, progress, should_stop, user_agent=USER_AGENT)
    return dest


def file_sha256(path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def wait_for_pid(pid: int, timeout: float = 90.0) -> bool:
    """Windows: sureç bitene kadar bekler (OpenProcess + WaitForSingleObject)."""
    if sys.platform != 'win32' or pid <= 0:
        return True
    import ctypes
    SYNCHRONIZE = 0x00100000
    h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
    if not h:
        return True          # sureç zaten yok
    try:
        return ctypes.windll.kernel32.WaitForSingleObject(h, int(timeout * 1000)) == 0
    finally:
        ctypes.windll.kernel32.CloseHandle(h)


def replace_target(source, target, attempts: int = 80, delay: float = 0.5, sleep=None) -> None:
    """source'u target'in uzerine kopyalar; kilit kalkana kadar dener; yarim dosya birakmaz."""
    import shutil
    import time
    sleep = sleep or time.sleep
    source, target = pathlib.Path(source), pathlib.Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + '.new')
    shutil.copyfile(source, tmp)
    last = None
    for _ in range(attempts):
        try:
            os.replace(tmp, target)
            return
        except OSError as e:          # eski EXE henuz kilitli (onefile ust sureci kapaniyor)
            last = e
            sleep(delay)
    try:
        tmp.unlink()
    except OSError:
        pass
    raise OSError('Eski sürüm dosyası serbest kalmadı: %s' % last)


def launch(exe, popen=subprocess.Popen):
    return popen([str(exe)], env=scrub_env(), close_fds=True, cwd=str(pathlib.Path(exe).parent),
                 creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)


def apply_update(new_exe, popen=subprocess.Popen, pid=None, target=None):
    """Yeni EXE'yi guncelleyici kipinde baslatir: eski surum kapaninca kendini hedefe kopyalar ve hedefi acar.

    Cagiran, donen surecin ayakta kaldigini dogrulamali (guvenlik yazilimi engellediyse hemen kapanir)
    ve ancak ondan sonra kapanmalidir."""
    if not is_frozen() and target is None:
        raise OSError('Güncelleme yalnızca derlenmiş EXE için uygulanabilir.')
    target = pathlib.Path(target or sys.executable)
    pid = os.getpid() if pid is None else pid
    log_line('Starting updater %s -> %s (pid %s)' % (new_exe, target, pid))
    return popen([str(new_exe), '--apply-update', str(target), '--wait-pid', str(int(pid))],
                 env=scrub_env(), close_fds=True, cwd=str(pathlib.Path(new_exe).parent),
                 creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)


def cleanup_downloads(keep=None) -> None:
    for f in updates_dir().glob('AGFO-Phantom-Shot-*.exe'):
        if keep is None or f.resolve() != pathlib.Path(keep).resolve():
            try:
                f.unlink()
            except OSError:
                pass


def _powershell() -> str:
    root = os.environ.get('SystemRoot', r'C:\Windows')
    return str(pathlib.Path(root) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe')


def _ps_quote(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def shortcut_script(target_exe, desktop: bool) -> str:
    lines = [
        "$ErrorActionPreference = 'Stop'",
        "$shell = New-Object -ComObject WScript.Shell",
        "$exe = %s" % _ps_quote(target_exe),
        "$menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'AGFO'",
        "[void][System.IO.Directory]::CreateDirectory($menu)",
        "$targets = @((Join-Path $menu 'AGFO Phantom Shot.lnk'))",
    ]
    if desktop:
        lines.append("$targets += (Join-Path ([Environment]::GetFolderPath('Desktop')) 'AGFO Phantom Shot.lnk')")
    lines += [
        "foreach ($t in $targets) {",
        "  $l = $shell.CreateShortcut($t); $l.TargetPath = $exe; $l.WorkingDirectory = [System.IO.Path]::GetDirectoryName($exe)",
        "  $l.Description = 'AGFO Phantom Shot'; $l.IconLocation = $exe + ',0'; $l.Save()",
        "}",
    ]
    return '\r\n'.join(lines) + '\r\n'


def install_self(desktop: bool = True, run=subprocess.run) -> pathlib.Path:
    """Calisan EXE'yi kullanici klasorune kurar ve kisayol olusturur (yonetici gerekmez)."""
    if not is_frozen():
        raise OSError('Kurulum yalnızca derlenmiş EXE ile yapılabilir.')
    import shutil
    import tempfile
    dst = installed_exe()
    dst.parent.mkdir(parents=True, exist_ok=True)
    if pathlib.Path(sys.executable).resolve() != dst.resolve():
        shutil.copy2(sys.executable, dst)
    fd, path = tempfile.mkstemp(prefix='agfo-phantom-lnk-', suffix='.ps1')
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
        "Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath('Programs')) 'AGFO\\AGFO Phantom Shot.lnk') -Force",
        "Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath('Desktop')) 'AGFO Phantom Shot.lnk') -Force",
        "Remove-Item -LiteralPath %s -Recurse -Force" % _ps_quote(install_dir()),
    ]
    return '\r\n'.join(lines) + '\r\n'


def uninstall(popen=subprocess.Popen) -> None:
    """Program dosyasini ve kisayollari kaldirir; ayarlar (config.json) ve gunlukler korunur."""
    import tempfile
    fd, path = tempfile.mkstemp(prefix='agfo-phantom-', suffix='.ps1')
    with os.fdopen(fd, 'w', encoding='utf-8-sig') as f:
        f.write(uninstall_script())
    popen([_powershell(), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden', '-File', path],
          env=scrub_env(), close_fds=True, creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS)
