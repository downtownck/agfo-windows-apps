"""AGFO Phantom Shot 1.3.0 - GUI'den bagimsiz cekirdek (yalnizca standart kutuphane).

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

VERSION = '1.3.0'
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
    'autostart': True,       # acilista dinlemeye hemen basla (1.3.0: varsayilan acik; durdurulmus uygulama hic yakalamaz)
    'start_with_windows': False,   # 1.3.0: Windows oturumu acilinca tepside, dinlemede baslat
    'block_key': True,       # 1.3.0: tetik tusu diger programlara iletilmez (F9/PrintScreen baska islem acmaz)
    'min_interval_ms': 250,  # 1.3.0: basili tutulan tusun tekrarlari ve cift basislar tek goruntu sayilir
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


# --------------------------------------------------------------------------- 1.3.0: tus kodlari ve tetik kapisi
# Tetik, klavye duzeninden bagimsiz Windows sanal tus koduyla (VK) eslesir: Turkce Q/F klavyede, Shift/Ctrl
# basiliyken ya da CapsLock acikken de ayni tus ayni kodu verir (1.2.0 karakterle eslesiyordu; 'a' secip Shift'e
# basili iken ya da farkli duzende tetiklenmiyordu).
_VK_NAMED = {'print_screen': 0x2C, 'pause': 0x13, 'scroll_lock': 0x91, 'insert': 0x2D, 'home': 0x24, 'end': 0x23,
             'page_up': 0x21, 'page_down': 0x22, 'menu': 0x5D, 'space': 0x20}
VK_SNAPSHOT = 0x2C
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105


def key_vk(name):
    """Tetik adi -> sanal tus kodu (yoksa None). f1-f24, adli ozel tuslar, tek harf/rakam."""
    n = str(name or '').strip().lower()
    if not n or n == '(yok)':
        return None
    if n in _VK_NAMED:
        return _VK_NAMED[n]
    if n.startswith('f') and n[1:].isdigit() and 1 <= int(n[1:]) <= 24:
        return 0x70 + int(n[1:]) - 1
    if len(n) == 1 and ('a' <= n <= 'z' or '0' <= n <= '9'):
        return ord(n.upper())
    return None


class TriggerGate:
    """Basili tutulan tusun otomatik tekrarlarini ve cok hizli ardisik basislari tek tetige indirir.

    press() True donerse bir goruntu alinmalidir. release() tus birakilinca cagrilir. PrintScreen gibi bazi
    tuslarda Windows yalnizca 'birakma' bildirebilir; bu durumda release_only=True ile birakma tetik sayilir."""

    def __init__(self, min_interval_ms=250, clock=None):
        self.min_interval = max(0, int(min_interval_ms or 0)) / 1000.0
        self.clock = clock or time.monotonic
        self.down = False
        self.last = None

    def _fire(self):
        now = self.clock()
        if self.last is not None and now - self.last < self.min_interval:
            return False
        self.last = now
        return True

    def press(self):
        if self.down:             # otomatik tekrar
            return False
        self.down = True
        return self._fire()

    def release(self, release_only=False):
        was = self.down
        self.down = False
        if release_only and not was:
            return self._fire()
        return False


def log_line(text, name='phantom.log'):
    """Kisa tanilama gunlugu (yakalama hatalari, dinleyici yeniden baslatma). 256 KB'de bir dondurulur."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        p = LOG_DIR / name
        if p.exists() and p.stat().st_size > 256 * 1024:
            os.replace(p, p.with_suffix('.old'))
        with open(p, 'a', encoding='utf-8') as f:
            f.write('%s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), text))
    except OSError:
        pass
