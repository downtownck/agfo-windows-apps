"""AGFO Mic Monitor - gecikmesiz yanki (echo) ve reverb.

Gecikme yok: kuru ses oldugu gibi gecer, efekt sesi ustune eklenir. Efektlerin kendisi zaten "gec gelen"
sestir (yanki 60 ms+, reverb ilk yansimasi on gecikme kadar sonra) - bu yuzden blok blok islenebilir:
geri besleme hatlarinin hepsi islenen bloktan uzun oldugu icin bir bloktaki her ornek yalnizca onceki
bloklardan gelen veriye bakar ve islem tamamen numpy vektor islemleriyle yapilir (ornek ornek Python
dongusu yok; 48 kHz'de 10 ms'lik blok ~0,1-0,3 ms).

Reverb: erken yansimalar (cok noktali, stereo) + 8 hatli geri beslemeli gecikme agi (FDN, Householder
karisim matrisi, hat basina RT60'a gore kazanc ve tiz sonumleme). Yanki: geri beslemeli, tiz sonumlemeli
stereo gecikme.
"""
import numpy as np

F32 = np.float32
TINY = 1e-20   # denormal sayilari sifirla (Intel'de cok yavaslar)

# Reverb on ayarlari: oda boyutu (hat uzunluklari carpani), RT60 (s), on gecikme (ms), parlaklik (0-100),
# erken yansima seviyesi.
REVERB_PRESETS = {
    'Oda':       dict(size=0.62, time=0.8, predelay=6, tone=55, early=0.8),
    'Studyo':    dict(size=0.80, time=1.3, predelay=12, tone=60, early=0.7),
    'Salon':     dict(size=1.15, time=2.4, predelay=24, tone=50, early=0.6),
    'Katedral':  dict(size=1.50, time=5.0, predelay=40, tone=42, early=0.5),
    'Plaka':     dict(size=0.70, time=1.9, predelay=0, tone=75, early=0.15),
}
REVERB_TYPES = tuple(REVERB_PRESETS)

_FDN_BASE = (1213, 1361, 1489, 1601, 1777, 1913, 2053, 2203)        # 48 kHz'de ornek (asal, birbirine oransiz)
_SIGN_L = np.array([1, -1, 1, -1, 1, -1, 1, -1], dtype=F32)
_SIGN_R = np.array([1, 1, -1, -1, 1, 1, -1, -1], dtype=F32)
_IN_SIGN = np.array([1, 1, -1, 1, -1, -1, 1, -1], dtype=F32)
# erken yansimalar: (ms, kazanc, sol/sag)
_EARLY = ((4.3, 0.84, 0), (7.1, 0.78, 1), (11.9, 0.70, 0), (13.7, 0.66, 1), (19.3, 0.55, 0), (23.1, 0.52, 1),
          (29.7, 0.43, 0), (31.3, 0.40, 1), (41.9, 0.31, 0), (47.3, 0.28, 1), (59.1, 0.20, 0), (67.7, 0.17, 1))


def _tone_coef(tone):
    """Parlaklik 0..100 -> geri besleme icindeki 2 noktali FIR alcak geciren katsayisi (0,5 koyu .. 1,0 parlak)."""
    return float(0.5 + 0.5 * min(100.0, max(0.0, float(tone))) / 100.0)


class Echo:
    MAX_S = 1.5

    def __init__(self, sr, ms=320, feedback=35, mix=30, tone=55):
        self.sr = int(sr)
        self.L = int(self.MAX_S * self.sr) + 8
        self.buf = np.zeros((self.L, 2), dtype=F32)
        self.w = 0
        self.last = np.zeros(2, dtype=F32)
        self.set(ms, feedback, mix, tone)

    def set(self, ms=None, feedback=None, mix=None, tone=None):
        if ms is not None:
            self.D = int(min(self.MAX_S * 1000, max(60.0, float(ms))) * self.sr / 1000.0)
        if feedback is not None:
            self.fb = F32(min(85.0, max(0.0, float(feedback))) / 100.0)
        if mix is not None:
            self.mix = F32(min(100.0, max(0.0, float(mix))) / 100.0)
        if tone is not None:
            self.a = F32(_tone_coef(tone))

    @property
    def max_chunk(self):
        return self.D

    def process(self, x2):
        """x2: (n, 2) kuru ses, n <= D. Donus: (n, 2) islak ses."""
        n = len(x2)
        idx = (self.w - self.D + np.arange(n)) % self.L
        d = self.buf[idx]
        prev = np.empty_like(d)
        prev[0] = self.last
        prev[1:] = d[:-1]
        self.last = d[-1].copy()
        d = self.a * d + (F32(1.0) - self.a) * prev        # her tekrarda tizler biraz soner (analog bant yankisi gibi)
        wr = x2 + self.fb * d
        wr[np.abs(wr) < TINY] = 0.0
        widx = (self.w + np.arange(n)) % self.L
        self.buf[widx] = wr
        self.w = (self.w + n) % self.L
        return d * self.mix


class Reverb:
    def __init__(self, sr, kind='Studyo', time=None, mix=25, tone=None, predelay=None):
        self.sr = int(sr)
        p = dict(REVERB_PRESETS.get(kind, REVERB_PRESETS['Studyo']))
        self.kind = kind if kind in REVERB_PRESETS else 'Studyo'
        scale = self.sr / 48000.0 * p['size']
        self.D = [max(256, int(b * scale)) for b in _FDN_BASE]
        self.lines = [np.zeros(d, dtype=F32) for d in self.D]
        self.pos = [0] * 8
        self.last = np.zeros(8, dtype=F32)
        self.early_gain = F32(p['early'])
        # giris gecmisi (on gecikme + erken yansimalar icin)
        self.H = int(0.25 * self.sr) + 4096
        self.hist = np.zeros(self.H, dtype=F32)
        self.hw = 0
        self.taps = [(int(ms * self.sr / 1000.0), F32(g), side) for ms, g, side in _EARLY]
        self.set(time=p['time'] if time is None else time, mix=mix, tone=p['tone'] if tone is None else tone,
                 predelay=p['predelay'] if predelay is None else predelay)

    def set(self, time=None, mix=None, tone=None, predelay=None):
        if time is not None:
            self.rt60 = min(10.0, max(0.2, float(time)))
            # tiz sonumleme de enerji aldigi icin olculen sure ~%80'de kaliyordu: 1,25 ile dengelenir
            rt = self.rt60 * 1.25
            self.g = np.array([10.0 ** (-3.0 * d / (self.sr * rt)) for d in self.D], dtype=F32)
        if mix is not None:
            self.mix = F32(min(100.0, max(0.0, float(mix))) / 100.0)
        if tone is not None:
            self.a = F32(_tone_coef(tone))
        if predelay is not None:
            self.pre = int(min(120.0, max(0.0, float(predelay))) * self.sr / 1000.0)

    @property
    def max_chunk(self):
        return min(self.D)

    def process(self, x2):
        n = len(x2)
        mono = x2.mean(axis=1).astype(F32)
        widx = (self.hw + np.arange(n)) % self.H
        self.hist[widx] = mono
        self.hw = (self.hw + n) % self.H
        # on gecikmeli giris + erken yansimalar (ileri beslemeli: her gecikme olabilir)
        base = self.hw - n
        dry_in = self._delayed_from(base, n, self.pre)
        el = np.zeros(n, dtype=F32)
        er = np.zeros(n, dtype=F32)
        for d, g, side in self.taps:
            v = self._delayed_from(base, n, self.pre + d) * g
            if side:
                er += v
            else:
                el += v
        early = (el + er) * F32(0.5)
        fdn_in = (dry_in + early * F32(0.5)) * F32(0.35)
        # FDN: her hattin cikisi (n <= hat uzunlugu -> hepsi onceki bloklardan)
        outs = np.empty((8, n), dtype=F32)
        for i in range(8):
            L, p = self.D[i], self.pos[i]
            idx = (p + np.arange(n)) % L
            outs[i] = self.lines[i][idx]
        prev = np.empty_like(outs)
        prev[:, 0] = self.last
        prev[:, 1:] = outs[:, :-1]
        self.last = outs[:, -1].copy()
        damped = (self.a * outs + (F32(1.0) - self.a) * prev) * self.g[:, None]
        fb = damped - (F32(2.0 / 8.0)) * damped.sum(axis=0, keepdims=True)     # Householder: enerjiyi korur
        fb += _IN_SIGN[:, None] * fdn_in[None, :]
        fb[np.abs(fb) < TINY] = 0.0
        for i in range(8):
            L, p = self.D[i], self.pos[i]
            idx = (p + np.arange(n)) % L
            self.lines[i][idx] = fb[i]
            self.pos[i] = (p + n) % L
        k = F32(0.5)
        wl = (_SIGN_L[:, None] * outs).sum(axis=0) * k + el * self.early_gain
        wr = (_SIGN_R[:, None] * outs).sum(axis=0) * k + er * self.early_gain
        return np.stack([wl, wr], axis=1) * self.mix

    def _delayed_from(self, base, n, delay):
        idx = (base - delay + np.arange(n)) % self.H
        return self.hist[idx]


class FxChain:
    """Kuru sese eklenecek islak sesi uretir. Bloklar, en kisa geri besleme hattindan buyukse parcalanir."""

    def __init__(self, sr):
        self.sr = int(sr)
        self.echo = None
        self.reverb = None

    @property
    def active(self):
        return self.echo is not None or self.reverb is not None

    def configure(self, cfg):
        c = cfg
        if c.get('fx_echo_on'):
            args = dict(ms=c.get('fx_echo_ms', 320), feedback=c.get('fx_echo_fb', 35),
                        mix=c.get('fx_echo_mix', 30), tone=c.get('fx_echo_tone', 55))
            if self.echo is None:
                self.echo = Echo(self.sr, **args)
            else:
                self.echo.set(**args)
        else:
            self.echo = None
        if c.get('fx_rev_on'):
            kind = c.get('fx_rev_type', 'Studyo')
            args = dict(time=c.get('fx_rev_time'), mix=c.get('fx_rev_mix', 25), tone=c.get('fx_rev_tone'),
                        predelay=c.get('fx_rev_predelay'))
            if self.reverb is None or self.reverb.kind != kind:
                self.reverb = Reverb(self.sr, kind, **args)      # oda tipi degisti: hatlar yeniden kurulur
            else:
                self.reverb.set(**args)
        else:
            self.reverb = None
        return self

    def process(self, x2):
        """x2: (n, 2) kuru. Donus: (n, 2) islak (kuru icermez)."""
        echo, rev = self.echo, self.reverb     # GUI nesneyi degistirebilir: yerel kopya
        n = len(x2)
        out = np.zeros((n, 2), dtype=F32)
        if echo is None and rev is None:
            return out
        lim = min([m.max_chunk for m in (echo, rev) if m is not None])
        s = 0
        while s < n:
            e = min(n, s + lim)
            blk = x2[s:e]
            if echo is not None:
                out[s:e] += echo.process(blk)
            if rev is not None:
                # yankinin islak sesi de reverb'e girer (dogal "yanki odada" etkisi)
                src = blk + out[s:e] if echo is not None else blk
                out[s:e] += rev.process(src)
            s = e
        return out
