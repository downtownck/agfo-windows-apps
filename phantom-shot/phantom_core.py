"""AGFO Phantom Shot 1.1.0 - GUI'den bagimsiz cekirdek (yalnizca standart kutuphane).

Phantom Shot, belirlenen bir klavye ya da fare tusuna basildiginda ekran goruntusunu alip
ayarlanan klasore kaydeder; ekranda hicbir pencere, bildirim ya da ses gostermez. Yakalamanin
kendisi (mss) ve tus dinleme (pynput) GUI tarafindadir; bu cekirdek ayar yonetimi ve ortak
yardimcilar icerir (yalnizca standart kutuphane ile test edilebilir).

Dagitim: tek dosyalik EXE (PyInstaller onefile). Guncelleme phantom_update.py uzerinden
GitHub Releases'ten yeni EXE indirilip dogrulanarak yapilir (bkz. agfo_github_update.py).
"""
import json
import os
import pathlib
import subprocess
import sys
import time

VERSION = '1.1.0'
IS_WIN = sys.platform == 'win32'
CREATIONFLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

LOCALAPPDATA = os.environ.get('LOCALAPPDATA', str(pathlib.Path.home()))
APP_DATA_DIR = pathlib.Path(LOCALAPPDATA) / 'AGFO' / 'PhantomShot'
SETTINGS_FILE = APP_DATA_DIR / 'config.json'
LOG_DIR = APP_DATA_DIR / 'logs'

# config.json varsayilanlari (kullanici verisi; EXE'nin yaninda degil APP_DATA_DIR'a yazilir).
DEFAULT_CONFIG = {
    'save_dir': '',          # bos -> ~/Pictures/PhantomShots
    'key': 'f9',             # tetik tusu adi; '(yok)'/bos -> klavye dinlenmez
    'mouse_button': '',      # 'middle' / 'x1' / 'x2' / 'right' / bos
    'monitor': 0,            # 0=tum ekranlar, 1=birincil, 2=ikincil...
    'prefix': 'shot',
    'format': 'png',         # png | jpg
    'jpg_quality': 90,
    'autostart': False,      # acilista dinlemeye hemen basla
    'minimize_to_tray': True,
    'auto_update_check': True,
}


def data_dir():
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return APP_DATA_DIR


def load_settings():
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            out = dict(DEFAULT_CONFIG)
            out.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})
            return out
    except Exception:
        pass
    return dict(DEFAULT_CONFIG)


def save_settings(data):
    try:
        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        clean = {k: v for k, v in (data or {}).items() if k in DEFAULT_CONFIG}
        tmp = SETTINGS_FILE.with_name(SETTINGS_FILE.name + '.new')
        tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding='utf-8')
        os.replace(tmp, SETTINGS_FILE)
        return True
    except OSError:
        return False


def resolve_save_dir(raw):
    """Bos ise ~/Pictures(Resimler)/PhantomShots; aksi halde mutlak yol."""
    raw = (raw or '').strip()
    if not raw:
        pics = pathlib.Path.home() / 'Pictures'
        if not pics.is_dir():
            alt = pathlib.Path.home() / 'Resimler'
            pics = alt if alt.is_dir() else pathlib.Path.home()
        raw = str(pics / 'PhantomShots')
    return os.path.abspath(os.path.expanduser(raw))


def screenshot_name(prefix='shot', fmt='png', now=None):
    """Zaman damgali, cakismayan dosya adi (milisaniye dahil)."""
    now = now or time.time()
    lt = time.localtime(now)
    ms = int((now - int(now)) * 1000)
    base = (prefix or 'shot').strip() or 'shot'
    ext = (fmt or 'png').lower().lstrip('.')
    if ext == 'jpeg':
        ext = 'jpg'
    if ext not in ('png', 'jpg'):
        ext = 'png'
    return '%s_%s_%03d.%s' % (base, time.strftime('%Y%m%d_%H%M%S', lt), ms, ext)
