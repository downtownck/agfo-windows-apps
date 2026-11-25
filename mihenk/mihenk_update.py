# -*- coding: utf-8 -*-
"""AGFO Mihenk - GitHub'dan tek tikla guncelleme (yonetici gerekmez).

Ilk kurulum: Kurulum ZIP'i (Derle-ve-Kur.cmd) EXE'yi kullanicinin bilgisayarinda derler (web filtresi / SmartScreen takilmasin).
Guncelleme sessizdir: yeni EXE GitHub Releases'ten uygulamanin kendi koduyla indirilir (tarayici degil; internetten indirildi
isareti tasimaz), SHA-256 ile dogrulanir; uygulama kapaninca yeni EXE kendini eski dosyanin uzerine kopyalar ve uygulamayi
yeniden acar (pencere ya da konsol gostermez). Kaynaktan calisan surum icin eski ZIP yolu kalir.
Kullanici verisi (%APPDATA%\\AGFO\\Mihenk: kayit veritabani ve ayarlar) korunur. Guven koku GitHub hesabidir; kod imzasi degildir.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import zipfile

import agfo_github_update as ghu
import mihenk_core as core
from mihenk_store import data_dir

GH_PREFIX = 'mihenk-v'
GH_ASSET = r'AGFO-Mihenk-v[0-9.]+-Kurulum\.zip'      # kaynaktan calisirken (eski yol)
GH_ASSET_EXE = r'AGFO-Mihenk\.exe'                      # EXE iken sessiz guncelleme
EXE_NAME = 'AGFO-Mihenk.exe'
USER_AGENT = 'AGFO-Mihenk/%s' % core.VERSION
CHECK_INTERVAL = 6 * 3600

CREATE_NEW_CONSOLE = 0x00000010
CREATE_NEW_PROCESS_GROUP = 0x00000200
DETACHED_PROCESS = 0x00000008


def is_frozen() -> bool:
    return bool(getattr(sys, 'frozen', False))


def asset_pattern() -> str:
    return GH_ASSET_EXE if is_frozen() else GH_ASSET


def install_dir() -> pathlib.Path:
    base = os.environ.get('LOCALAPPDATA') or str(pathlib.Path.home())
    return pathlib.Path(base) / 'Programs' / 'AGFO-Mihenk'


def installed_exe() -> pathlib.Path:
    return install_dir() / EXE_NAME


def state_path() -> pathlib.Path:
    return data_dir() / 'github-update.json'


def updates_dir() -> pathlib.Path:
    p = data_dir() / 'updates'
    p.mkdir(parents=True, exist_ok=True)
    return p


def scrub_env(env=None) -> dict:
    """Alt surece PyInstaller onefile ic degiskenlerini gecirme (yoksa yeni EXE bozuk acilir)."""
    src = os.environ if env is None else env
    out = {k: v for k, v in src.items() if not k.upper().startswith(('_PYI_', '_MEIPASS'))}
    out['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return out


def package_ready(release: dict, asset: dict) -> bool:
    if not asset or not asset.get('url'):
        return False
    if asset.get('sha256'):
        return True
    return ghu.pick_asset(release, r'SHA256SUMS(\.txt)?') is not None


def check(force=False, releases=None) -> dict:
    """Hata firlatmaz. 'update' yalniz paket indirilebilir ve dogrulanabilir oldugunda doner."""
    res = ghu.check_for_update(GH_PREFIX, core.VERSION, state_path(), asset_pattern(), force=force,
                               interval=CHECK_INTERVAL, releases=releases, user_agent=USER_AGENT)
    if res.get('status') == 'update' and not package_ready(res.get('release') or {}, res.get('asset') or {}):
        return {'status': 'error', 'version': res.get('version'),
                'message': 'v%s yayınlanmış ama paket henüz doğrulanamıyor (SHA-256 özeti yok).' % res.get('version')}
    return res


def download(result: dict, progress=None, should_stop=None) -> pathlib.Path:
    rel, asset = result['release'], result['asset']
    sha = ghu.expected_sha256(rel, asset, user_agent=USER_AGENT)
    dest = updates_dir() / (('AGFO-Mihenk-%s.exe' % result['version']) if asset['name'].lower().endswith('.exe')
                            else asset['name'])
    ghu.download_asset(asset, dest, sha, progress, should_stop, user_agent=USER_AGENT)
    return dest


def extract(zip_path) -> pathlib.Path:
    """ZIP'i guvenli bicimde acar (yol disina tasma yok) ve Derle-ve-Kur.cmd'nin klasorunu dondurur."""
    zip_path = pathlib.Path(zip_path)
    out = updates_dir() / zip_path.stem
    if out.exists():
        shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    root = out.resolve()
    with zipfile.ZipFile(zip_path) as z:
        for m in z.infolist():
            target = (out / m.filename).resolve()
            if root != target and root not in target.parents:
                raise ghu.GHUpdateError('Pakette güvensiz yol: %s' % m.filename)
        z.extractall(out)
    for p in out.rglob('Derle-ve-Kur.cmd'):
        return p.parent
    raise ghu.GHUpdateError('Pakette Derle-ve-Kur.cmd yok.')


def run_installer(folder, popen=subprocess.Popen):
    """Derle-ve-Kur.cmd /update'i yeni bir konsolda baslatir (kullanici ilerlemeyi gorur)."""
    cmd = pathlib.Path(folder) / 'Derle-ve-Kur.cmd'
    comspec = os.environ.get('ComSpec') or 'cmd.exe'
    return popen([comspec, '/c', str(cmd), '/update'], cwd=str(folder), env=scrub_env(), close_fds=True,
                 creationflags=CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP)


def cleanup_downloads(keep=None) -> None:
    for f in updates_dir().iterdir():
        if keep is not None and f.resolve() == pathlib.Path(keep).resolve():
            continue
        try:
            shutil.rmtree(f) if f.is_dir() else f.unlink()
        except OSError:
            pass


# ------------------------------------------------------------------ sessiz EXE guncelleme
def log_line(text: str) -> None:
    import datetime
    try:
        with open(data_dir() / 'update-log.txt', 'a', encoding='utf-8') as f:
            f.write('%s %s\n' % (datetime.datetime.now().isoformat(timespec='seconds'), text))
    except OSError:
        pass


def wait_for_pid(pid: int, timeout: float = 90.0) -> bool:
    """Windows: surec bitene kadar bekler (OpenProcess + WaitForSingleObject)."""
    if sys.platform != 'win32' or pid <= 0:
        return True
    import ctypes
    h = ctypes.windll.kernel32.OpenProcess(0x00100000, False, int(pid))      # SYNCHRONIZE
    if not h:
        return True          # surec zaten yok
    try:
        return ctypes.windll.kernel32.WaitForSingleObject(h, int(timeout * 1000)) == 0
    finally:
        ctypes.windll.kernel32.CloseHandle(h)


def replace_target(source, target, attempts: int = 80, delay: float = 0.5, sleep=None) -> None:
    """source'u target'in uzerine kopyalar; kilit kalkana kadar dener; yarim dosya birakmaz."""
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


def launch(exe, minimized=False, popen=subprocess.Popen):
    args = [str(exe)] + (['--minimized'] if minimized else [])
    return popen(args, env=scrub_env(), close_fds=True, cwd=str(pathlib.Path(exe).parent),
                 creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)


def apply_update(new_exe, minimized=False, popen=subprocess.Popen, pid=None, target=None):
    """Yeni EXE'yi guncelleyici kipinde baslatir: eski surum kapaninca kendini hedefe kopyalar ve hedefi acar.
    Cagiran, donen surecin ayakta kaldigini dogrulamali (guvenlik yazilimi engellediyse hemen kapanir)."""
    if not is_frozen() and target is None:
        raise OSError('Sessiz güncelleme yalnızca derlenmiş EXE için uygulanabilir.')
    target = pathlib.Path(target or sys.executable)
    pid = os.getpid() if pid is None else pid
    log_line('Starting updater %s -> %s (pid %s)' % (new_exe, target, pid))
    cmd = [str(new_exe), '--apply-update', str(target), '--wait-pid', str(int(pid))] + (['--minimized'] if minimized else [])
    return popen(cmd, env=scrub_env(), close_fds=True, cwd=str(pathlib.Path(new_exe).parent),
                 creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)


def apply_update_main(target, pid, minimized=False) -> int:
    """Guncelleyici kipi (penceresiz): eski surum kapaninca kendini hedefe kopyalar ve hedefi acar."""
    try:
        if not wait_for_pid(pid, 90):
            raise OSError('Eski sürüm 90 saniyede kapanmadı.')
        replace_target(sys.executable, target)
        launch(target, minimized)
        log_line('Update applied: %s' % target)
        return 0
    except Exception as e:
        log_line('Update failed: %r' % e)
        if sys.platform == 'win32':
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, 'Güncelleme uygulanamadı: %s\n\nYeni sürüm şu dosyada, doğrudan açabilirsin:\n%s'
                                                 % (e, sys.executable), 'AGFO Mihenk', 0x10)
            except Exception:
                pass
        return 1
