"""AGFO Mic Monitor 1.0.2 - GUI'den ve ses surucusunden bagimsiz cekirdek.

Mic Monitor, mikrofonu kulakliktan dusuk gecikmeyle dinletir ve ayni sesi ayni anda WAV olarak kaydeder.
Windows Vista'dan beri "Bu cihazi dinle" ozelligi sesi Windows ses motorundan (karistirici, efektler,
Voice Clarity, Nahimic vb.) gecirdigi icin 50-100+ ms gecikir. Mic Monitor akisi WASAPI ozel modda ve
RAW secenegiyle acar; ses motoru ve efekt katmanlari (APO) atlanir.

Bu modul yalnizca standart kutuphane + numpy kullanir (Linux'ta test edilebilir): ayarlar, sinyal
yardimcilari, halka tampon (iki ayri akis arasinda), WAV yazici ve cihaz adlarina gore uyarilar.
Ses akisinin kendisi mic_engine.py'dedir (sounddevice / PortAudio).
"""
import datetime
import json
import math
import os
import pathlib
import queue
import sys
import threading
import wave

VERSION = '1.0.2'
IS_WIN = sys.platform == 'win32'

LOCALAPPDATA = os.environ.get('LOCALAPPDATA', str(pathlib.Path.home()))
APP_DATA_DIR = pathlib.Path(LOCALAPPDATA) / 'AGFO' / 'MicMonitor'
SETTINGS_FILE = APP_DATA_DIR / 'config.json'
LOG_DIR = APP_DATA_DIR / 'logs'

MODES = ('auto', 'wasapi_exclusive', 'wasapi_shared', 'asio', 'mme')
MODE_LABELS = {
    'auto': 'Otomatik (en dusuk gecikme)',
    'wasapi_exclusive': 'WASAPI ozel mod',
    'wasapi_shared': 'WASAPI paylasimli',
    'asio': 'ASIO',
    'mme': 'MME (uyumluluk, yuksek gecikme)',
}
BUFFER_CHOICES_MS = (3, 5, 10, 20, 40)
CHANNEL_MODES = ('mix', 'left', 'right', 'stereo')
CHANNEL_LABELS = {
    'mix': 'Mono (sol + sag karisik)',
    'left': 'Mono (yalniz sol / 1. kanal)',
    'right': 'Mono (yalniz sag / 2. kanal)',
    'stereo': 'Stereo (iki kanal ayri)',
}

DEFAULT_CONFIG = {
    'input_device': '',        # bos -> Windows varsayilani
    'output_device': '',
    'mode': 'auto',
    'share_output': False,     # True: cikis paylasimli (diger uygulamalarin sesi de duyulur; gecikme biraz artar)
    'buffer_ms': 5,
    'samplerate': 48000,
    'channel_mode': 'mix',
    'input_gain_db': 0.0,      # -12 .. +24
    'monitor_volume': 80,      # 0 .. 100
    'monitor_muted': False,
    'record_dir': '',          # bos -> ~/Music/AGFO Kayitlar
    'record_bits': 24,         # 16 | 24
    'enable_asio': False,      # ASIO surucularini tara (PortAudio ASIO DLL'i; yeniden baslatma gerekir)
    'autostart': False,        # acilista dinlemeyi baslat
    'auto_update_check': True,
}


# --------------------------------------------------------------------------- ayarlar / gunluk
def data_dir():
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return APP_DATA_DIR


def _clean(data):
    out = dict(DEFAULT_CONFIG)
    for k, v in (data or {}).items():
        if k not in DEFAULT_CONFIG:
            continue
        d = DEFAULT_CONFIG[k]
        if isinstance(d, bool):
            v = bool(v)
        elif isinstance(d, (int, float)) and not isinstance(d, bool):
            try:
                v = type(d)(v)
            except (TypeError, ValueError):
                v = d
        elif isinstance(d, str):
            v = '' if v is None else str(v)
        out[k] = v
    if out['mode'] not in MODES:
        out['mode'] = 'auto'
    if out['channel_mode'] not in CHANNEL_MODES:
        out['channel_mode'] = 'mix'
    if out['record_bits'] not in (16, 24):
        out['record_bits'] = 24
    out['buffer_ms'] = min(200, max(1, int(out['buffer_ms'])))
    out['input_gain_db'] = min(24.0, max(-12.0, float(out['input_gain_db'])))
    out['monitor_volume'] = min(100, max(0, int(out['monitor_volume'])))
    if out['samplerate'] not in (44100, 48000, 88200, 96000):
        out['samplerate'] = 48000
    return out


def load_settings():
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            return _clean(data)
    except Exception:
        pass
    return dict(DEFAULT_CONFIG)


def save_settings(data):
    try:
        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_FILE.with_name(SETTINGS_FILE.name + '.new')
        tmp.write_text(json.dumps(_clean(data), ensure_ascii=False, indent=1), encoding='utf-8')
        os.replace(tmp, SETTINGS_FILE)
        return True
    except OSError:
        return False


def log_line(text, name='micmon.log'):
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        p = LOG_DIR / name
        if p.exists() and p.stat().st_size > 256 * 1024:
            os.replace(p, p.with_suffix('.old.log'))
        with open(p, 'a', encoding='utf-8') as f:
            f.write('%s %s\n' % (datetime.datetime.now().isoformat(timespec='seconds'), text))
    except OSError:
        pass


def resolve_record_dir(raw):
    """Bos ise ~/Music (Muzik) / AGFO Kayitlar."""
    raw = (raw or '').strip()
    if raw:
        return pathlib.Path(os.path.expandvars(os.path.expanduser(raw)))
    home = pathlib.Path.home()
    base = home / 'Music'
    if not base.is_dir() and (home / 'Muzik').is_dir():
        base = home / 'Muzik'
    return base / 'AGFO Kayitlar'


def recording_name(now=None):
    now = now or datetime.datetime.now()
    return 'Kayit_%s.wav' % now.strftime('%Y%m%d_%H%M%S')


# --------------------------------------------------------------------------- sinyal yardimcilari
def db_to_gain(db):
    return float(10.0 ** (float(db) / 20.0))


def gain_to_db(g):
    return -120.0 if g <= 1e-6 else 20.0 * math.log10(g)


def monitor_gain(volume, muted=False):
    """0..100 surgu -> dogrusal kazanc (algisal: karesel egri)."""
    if muted:
        return 0.0
    v = min(100, max(0, float(volume))) / 100.0
    return v * v


def select_channels(block, channel_mode):
    """block: (frames, ch) float32. Donus: (frames, 1) ya da (frames, 2)."""
    import numpy as np
    ch = block.shape[1]
    if channel_mode == 'stereo':
        if ch >= 2:
            return block[:, :2]
        return np.repeat(block[:, :1], 2, axis=1)
    if ch == 1:
        return block[:, :1]
    if channel_mode == 'left':
        return block[:, :1]
    if channel_mode == 'right':
        return block[:, 1:2]
    return block[:, :2].mean(axis=1, keepdims=True, dtype=np.float32)


def fit_output(sig, out_channels):
    """(frames, 1|2) -> (frames, out_channels): mono tum kanallara, stereo ilk iki kanala."""
    import numpy as np
    frames, ch = sig.shape
    if ch == out_channels:
        return sig
    out = np.zeros((frames, out_channels), dtype=np.float32)
    if ch == 1:
        out[:] = sig
    elif out_channels == 1:
        out[:, 0] = sig.mean(axis=1)
    else:
        n = min(ch, out_channels)
        out[:, :n] = sig[:, :n]
    return out


def peak(block):
    import numpy as np
    if block.size == 0:
        return 0.0
    return float(np.max(np.abs(block)))


def peak_dbfs(p):
    return -120.0 if p <= 1e-6 else 20.0 * math.log10(p)


def float_to_pcm(block, bits):
    """float32 [-1,1] (frames, ch) -> kucuk-endian PCM bayt dizisi (16 ya da 24 bit), kirpilarak."""
    import numpy as np
    x = np.clip(block, -1.0, 1.0)
    if bits == 16:
        return (x * 32767.0).astype('<i2').tobytes()
    i = (x * 8388607.0).astype('<i4').reshape(-1)
    b = i.view(np.uint8).reshape(-1, 4)[:, :3]
    return b.tobytes()


# --------------------------------------------------------------------------- halka tampon
class RingBuffer:
    """Iki ayri ses akisi (giris / cikis) arasinda tek ureticili - tek tuketicili tampon.

    1.0.2: Hedef doluluk, gelen giris ve istenen cikis bloklarinin en buyugune gore kendini ayarlar
    (surucu 10 ms'lik bloklar verip 3 ms'lik isterse 5 ms'lik sabit hedef surekli bosalip cizirti yapiyordu).
    Tampon bosalirsa cikis, hedef yeniden dolana kadar sessiz kalir (aralikli bos bloklar yerine tek
    kisa bosluk). Giris ve cikis farkli saatle calisip tampon sisince fazlasi atilir (gecikme birikmez).
    """

    def __init__(self, channels, capacity, target):
        import numpy as np
        self.ch = channels
        self.cap = int(capacity)
        self.target = int(target)
        self.buf = np.zeros((self.cap, channels), dtype=np.float32)
        self.r = 0
        self.w = 0
        self.fill = 0
        self.lock = threading.Lock()
        self.underruns = 0
        self.dropped = 0
        self.max_w = 0
        self.max_r = 0
        self.primed = False

    def effective_target(self):
        # cikis henuz okumadiysa okuma blogunu yazma blogu kadar varsay (baslangicta gereksiz atmayi onler)
        return min(self.cap // 2, max(self.target, self.max_w + (self.max_r or self.max_w)))

    def write(self, data):
        n = len(data)
        with self.lock:
            if n > self.max_w:
                self.max_w = n
            if n >= self.cap:
                data = data[-self.cap:]
                n = len(data)
            first = min(n, self.cap - self.w)
            self.buf[self.w:self.w + first] = data[:first]
            if n > first:
                self.buf[:n - first] = data[first:]
            self.w = (self.w + n) % self.cap
            self.fill += n
            tgt = self.effective_target()
            high = tgt + 2 * self.max_w
            if self.fill > min(high, self.cap):
                drop = self.fill - tgt
                self.r = (self.r + drop) % self.cap
                self.fill -= drop
                self.dropped += drop

    def read(self, out):
        n = len(out)
        with self.lock:
            if n > self.max_r:
                self.max_r = n
            if not self.primed:
                if self.fill < self.effective_target():
                    out[:] = 0.0
                    return 0
                self.primed = True
            take = min(n, self.fill)
            first = min(take, self.cap - self.r)
            out[:first] = self.buf[self.r:self.r + first]
            if take > first:
                out[first:take] = self.buf[:take - first]
            if take < n:
                out[take:] = 0.0
                self.underruns += 1
                self.primed = False          # yeniden dolana kadar bekle
            self.r = (self.r + take) % self.cap
            self.fill -= take
        return take


# --------------------------------------------------------------------------- WAV kaydedici
class WavRecorder:
    """Ses geri cagrisi bloklari kuyruga atar (engellemez); ayri is parcacigi diske yazar."""

    def __init__(self, path, samplerate, channels, bits=24):
        self.path = pathlib.Path(path)
        self.samplerate = int(samplerate)
        self.channels = int(channels)
        self.bits = 24 if bits == 24 else 16
        self.q = queue.Queue(maxsize=4096)
        self.frames = 0
        self.dropped_blocks = 0
        self.clipped = 0
        self.error = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._w = wave.open(str(self.path), 'wb')
        self._w.setnchannels(self.channels)
        self._w.setsampwidth(self.bits // 8)
        self._w.setframerate(self.samplerate)
        self._t = threading.Thread(target=self._loop, name='micmon-wav', daemon=True)
        self._t.start()

    def push(self, block):
        """Ses is parcacigindan: kopya alir ve kuyruga koyar; kuyruk doluysa blogu sayar ve atar."""
        try:
            self.q.put_nowait(block.copy())
        except queue.Full:
            self.dropped_blocks += 1

    def _loop(self):
        import numpy as np
        while True:
            b = self.q.get()
            if b is None:
                break
            try:
                if self.error is None:
                    self.clipped += int(np.count_nonzero(np.abs(b) >= 0.999))
                    self._w.writeframesraw(float_to_pcm(b, self.bits))
                    self.frames += len(b)
            except Exception as e:  # disk dolu vb.
                self.error = e
                log_line('wav write failed: %r' % e)
        try:
            self._w.close()
        except Exception as e:
            self.error = self.error or e

    @property
    def seconds(self):
        return self.frames / float(self.samplerate or 1)

    def close(self, timeout=10.0):
        self.q.put(None)
        self._t.join(timeout)
        return self.path


# --------------------------------------------------------------------------- cihaz adlarina gore uyarilar
_BT_HINTS = ('hands-free', 'handsfree', 'bluetooth', 'airpods', 'buds', 'freeclip', 'headset (', ' bt')
_SPEAKER_HINTS = ('speaker', 'hoparl', 'hoparlör', 'lautsprecher', 'haut-parleur', 'altavoces')


def is_bluetooth_name(name):
    n = ' ' + (name or '').lower()
    return any(h in n for h in _BT_HINTS)


_HEADPHONE_HINTS = ('kulakl', 'headphone', 'headset', 'kopfh', 'casque', 'auricul', 'cuffi')


def is_headphone_name(name):
    n = (name or '').lower()
    return any(h in n for h in _HEADPHONE_HINTS) and not is_bluetooth_name(name)


def pick_new_headphone(before, after):
    """Yeni beliren (kablolu/USB) kulaklik cikisi; yoksa None. HDMI/monitor ve Bluetooth secilmez."""
    old = set(before or ())
    for n in after or ():
        if n not in old and is_headphone_name(n):
            return n
    return None


def is_speaker_name(name):
    n = (name or '').lower()
    return any(h in n for h in _SPEAKER_HINTS) and 'headphone' not in n and 'kulakl' not in n


def warnings_for(input_name, output_name):
    out = []
    if is_bluetooth_name(output_name):
        out.append('Cikis bir Bluetooth cihaz: Bluetooth 150-250 ms gecikme ekler, hicbir yazilim bunu dusuremez. '
                   'Kablolu kulaklik kullanin.')
    if is_bluetooth_name(input_name):
        out.append('Giris Bluetooth mikrofonu (Hands-Free): ses telefon kalitesine duser ve gecikir.')
    if is_speaker_name(output_name):
        out.append('Cikis hoparlor: mikrofon hoparlor sesini geri alip otebilir (geri besleme). Kulaklik takin '
                   'ya da dinleme sesini dusuk tutun. (Bazi Realtek suruculeri takili kulakligi da "Hoparlor" '
                   'adiyla gosterir; kulaklikta ses varsa bu uyariyi yok sayin.)')
    return out


def match_device_name(wanted, names):
    """Kayitli cihaz adini listede bul: tam eslesme, sonra MME'nin 31 karakterle kestigi adlar icin onek."""
    wanted = (wanted or '').strip()
    if not wanted:
        return None
    for i, n in enumerate(names):
        if n == wanted:
            return i
    for i, n in enumerate(names):
        if n and (wanted.startswith(n) or n.startswith(wanted)):
            return i
    low = wanted.lower()
    for i, n in enumerate(names):
        if n and (low.startswith(n.lower()) or n.lower().startswith(low)):
            return i
    return None
