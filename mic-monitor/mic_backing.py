"""AGFO Mic Monitor - altyapi (backing track) calma, hizali vokal kaydi ve karisim.

Altyapi, mikrofonla AYNI ses akisindan calinir: ozel modda kulaklik cikisini Mic Monitor tuttugu icin
baska bir programdan calinan altyapi duyulmazdi; ayrica ayni akista oldugu icin vokal ornek duzeyinde
hizalanabilir. Kayit, altyapinin ilk ornegi cikisa yazildigi geri cagride baslar. Sarkici altyapiyi
cikis gecikmesi kadar gec duyar, sesi de giris gecikmesi kadar gec gelir: vokal dosyasindan bu gidis-donus
gecikmesi kadar ornek atilir (artı/eksi elle ince ayar) ve vokal altyapiyla ayni noktadan baslar.

Dosya okuma: soundfile (libsndfile: WAV, FLAC, OGG, MP3, AIFF). Ornekleme hizi donusumu numpy ile,
pencereli sinc (Kaiser, 48 nokta, cok fazli) - ek kutuphane gerekmez.
"""
import os
import pathlib
import threading
import wave

import numpy as np

import mic_core as core

F32 = np.float32
SUPPORTED = (('Ses dosyalari', '*.wav *.mp3 *.flac *.ogg *.aif *.aiff'), ('Tum dosyalar', '*.*'))


# --------------------------------------------------------------------------- ornekleme hizi donusumu
def _kernel(d, cutoff, half, beta=8.0):
    w = np.i0(beta * np.sqrt(np.clip(1.0 - (d / (half + 1)) ** 2, 0.0, 1.0))) / np.i0(beta)
    return cutoff * np.sinc(cutoff * d) * w


def resample(x, sr_in, sr_out, taps=48):
    """x: (n, ch) float32 -> (round(n*sr_out/sr_in), ch). Pencereli sinc (Kaiser, 48 nokta, ~-85 dB).

    Hizlar oransal (44100/48000 = 147/160): L faz icin cekirdek bir kez hesaplanir, her faz bir matris
    carpimiyla islenir (4 dakikalik stereo sarki ~1 sn)."""
    from math import gcd
    sr_in, sr_out = int(sr_in), int(sr_out)
    if sr_in == sr_out or len(x) == 0:
        return x.astype(F32, copy=False)
    g = gcd(sr_in, sr_out)
    M, L = sr_in // g, sr_out // g                       # cikis ornegi t -> giris konumu t*M/L
    n_out = int(round(len(x) * sr_out / float(sr_in)))
    half = taps // 2
    cutoff = min(1.0, sr_out / float(sr_in)) * 0.94       # orneklemeyi dusururken ortusmeyi onle
    k = np.arange(-half + 1, half + 1)
    if L > 4096:                                          # olagan disi oran: dogrudan (yavas ama dogru)
        return _resample_direct(x, sr_in, sr_out, k, half, cutoff, n_out)
    pad = half + 2
    xp = np.concatenate([np.zeros((pad, x.shape[1]), F32), x.astype(F32, copy=False),
                         np.zeros((pad + M + taps, x.shape[1]), F32)])
    out = np.empty((n_out, x.shape[1]), dtype=F32)
    cols = [np.ascontiguousarray(xp[:, c]) for c in range(x.shape[1])]
    for j in range(L):                                    # faz j: t = q*L + j
        if j >= n_out:
            break
        base_j, frac_num = divmod(j * M, L)
        h = _kernel(frac_num / float(L) - k, cutoff, half).astype(F32)       # (taps,)
        q = (n_out - 1 - j) // L + 1
        start = base_j + k[0] + pad
        for c, col in enumerate(cols):
            win = np.lib.stride_tricks.as_strided(col[start:], shape=(q, taps),
                                                  strides=(col.strides[0] * M, col.strides[0]), writeable=False)
            out[j::L, c] = win @ h
    return out


def _resample_direct(x, sr_in, sr_out, k, half, cutoff, n_out, chunk=65536):
    ratio = sr_out / float(sr_in)
    pad = np.zeros((half + 2, x.shape[1]), dtype=F32)
    xp = np.concatenate([pad, x.astype(F32, copy=False), pad])
    out = np.empty((n_out, x.shape[1]), dtype=F32)
    for s in range(0, n_out, chunk):
        t = np.arange(s, min(n_out, s + chunk), dtype=np.float64)
        pos = t / ratio
        base = np.floor(pos).astype(np.int64)
        h = _kernel((pos - base)[:, None] - k[None, :], cutoff, half).astype(F32)
        idx = base[:, None] + k[None, :] + half + 2
        for c in range(x.shape[1]):
            out[s:s + len(t), c] = (xp[idx, c] * h).sum(axis=1)
    return out


# --------------------------------------------------------------------------- altyapi
class BackingTrack:
    def __init__(self, path):
        import soundfile as sf
        self.path = pathlib.Path(path)
        data, sr = sf.read(str(self.path), dtype='float32', always_2d=True)
        if data.shape[1] == 1:
            data = np.repeat(data, 2, axis=1)
        elif data.shape[1] > 2:
            data = data[:, :2]
        self.src = np.ascontiguousarray(data, dtype=F32)
        self.src_sr = int(sr)
        self.data = None
        self.sr = None
        self.pos = 0
        self.playing = False
        self.ended = False
        self.loop = False                  # fon muzigi: sona gelince bastan devam
        self._lock = threading.Lock()

    @property
    def name(self):
        return self.path.name

    @property
    def duration(self):
        return len(self.src) / float(self.src_sr)

    @property
    def ready(self):
        return self.data is not None

    def prepare(self, sr):
        """Akisin ornekleme hizina donusturur (birkac saniye surebilir; arka planda cagirin)."""
        sr = int(sr)
        if self.sr == sr and self.data is not None:
            return
        data = resample(self.src, self.src_sr, sr)
        with self._lock:
            old_sr = self.sr or self.src_sr
            self.pos = int(self.pos * sr / float(old_sr))
            self.data, self.sr = data, sr

    def position(self):
        sr = self.sr or self.src_sr
        return self.pos / float(sr)

    def seek(self, seconds):
        sr = self.sr or self.src_sr
        self.pos = max(0, min(int(seconds * sr), len(self.data) if self.data is not None else len(self.src)))
        self.ended = False

    def play(self, from_start=False):
        if from_start:
            self.pos = 0
        self.ended = False
        self.playing = True

    def stop(self):
        self.playing = False

    def read(self, n):
        """Ses is parcacigindan: (n, 2) ya da calmiyorsa None."""
        data = self.data
        if not self.playing or data is None:
            return None
        p = self.pos
        if self.loop and len(data):
            p %= len(data)
            out = data[p:p + n]
            while len(out) < n:                      # sona geldi: bastan devam (dikissiz)
                out = np.concatenate([out, data[:n - len(out)]])
            self.pos = (p + n) % len(data)
            return out
        out = data[p:p + n]
        if len(out) < n:
            out = np.concatenate([out, np.zeros((n - len(out), 2), dtype=F32)])
        if p + n >= len(data):                    # son ornek cikti: altyapi bitti
            self.playing = False
            self.ended = True
        self.pos = p + n
        return out


# --------------------------------------------------------------------------- WAV okuma / yazma / karisim
def read_wav(path):
    """16/24/32 bit PCM WAV -> (n, ch) float32, sr."""
    with wave.open(str(path), 'rb') as w:
        ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if sw == 2:
        a = np.frombuffer(raw, '<i2').astype(F32) / 32768.0
    elif sw == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3)
        i = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16))
        i = np.where(i & 0x800000, i - 0x1000000, i)
        a = i.astype(F32) / 8388608.0
    elif sw == 4:
        a = np.frombuffer(raw, '<i4').astype(F32) / 2147483648.0
    else:
        raise ValueError('Desteklenmeyen WAV ornek boyutu: %d' % sw)
    return a.reshape(-1, ch), sr


def write_wav(path, data, sr, bits=24):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.part')
    with wave.open(str(tmp), 'wb') as w:
        w.setnchannels(data.shape[1])
        w.setsampwidth(bits // 8)
        w.setframerate(int(sr))
        for s in range(0, len(data), 262144):
            w.writeframesraw(core.float_to_pcm(data[s:s + 262144], bits))
    os.replace(tmp, path)
    return path


def mix_path_for(vocal_path):
    p = pathlib.Path(vocal_path)
    stem = p.stem[:-len('_vokal')] if p.stem.endswith('_vokal') else p.stem
    return p.with_name(stem + '_karisim.wav')


def make_mix(vocal_path, backing, backing_gain, fx_cfg=None, bits=24, out_path=None, loop=False):
    """Altyapi + vokal karisimi. Vokal kuru kaydedildiyse kulaklikta duyulan efektler (yanki/reverb)
    karisimda da uygulanir. Tepe -1 dBFS'yi asarsa tum karisim olceklenir (kirpilma olmaz)."""
    voc, sr = read_wav(vocal_path)
    if backing.sr != sr or backing.data is None:
        backing.prepare(sr)
    bg = backing.data * F32(backing_gain)
    v2 = core.fit_output(voc, 2)
    if fx_cfg and (fx_cfg.get('fx_echo_on') or fx_cfg.get('fx_rev_on')):
        import mic_fx
        chain = mic_fx.FxChain(sr).configure(fx_cfg)
        tail = int(sr * 4)                                   # efekt kuyrugu kesilmesin
        v2 = np.concatenate([v2, np.zeros((tail, 2), dtype=F32)])
        wet = np.concatenate([chain.process(v2[s:s + 4800]) for s in range(0, len(v2), 4800)])
        v2 = v2 + wet
        # kuyrugun sessiz kismini kirp
        nz = np.nonzero(np.abs(v2).max(axis=1) > 1e-4)[0]
        v2 = v2[:max(len(voc), (nz[-1] + 1) if len(nz) else 0)]
    if loop and len(bg):
        # fon muzigi: vokal (efekt kuyruguyla) boyunca dongude, sonda 2 sn yumusak kapanis
        need = len(v2)
        reps = int(np.ceil(need / float(len(bg)))) if need else 1
        bg = np.tile(bg, (max(1, reps), 1))[:max(need, 1)]
        fade = min(len(bg), int(2.0 * sr))
        if fade:
            bg[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=F32)[:, None]
    n = max(len(bg), len(v2))
    mix = np.zeros((n, 2), dtype=F32)
    mix[:len(bg)] += bg
    mix[:len(v2)] += v2
    pk = float(np.abs(mix).max()) if n else 0.0
    limit = 10 ** (-1 / 20.0)
    if pk > limit:
        mix *= F32(limit / pk)
    return write_wav(out_path or mix_path_for(vocal_path), mix, sr, bits)
