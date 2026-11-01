"""AGFO Mic Monitor - ses motoru (sounddevice / PortAudio).

Akis acma sirasi ("Otomatik" kipte), ilk basarili olan kullanilir:
  1. WASAPI ozel mod, giris + cikis tek akista (RAW: Windows ses efektleri / APO'lar atlanir)
  2. WASAPI ozel mod giris + paylasimli cikis (cikisi baska bir uygulama tutuyorsa)
  3. WASAPI paylasimli (RAW), tek akis
  4. WASAPI paylasimli, giris ve cikis ayri akis + halka tampon (farkli saatli cihazlar)
  5. MME (eski API; yuksek gecikme, her yerde calisir)
Her deneme farkli ornekleme hizi / kanal sayisiyla tekrarlanir. Tum denemeler gunluge yazilir.

Ses geri cagrisi yalnizca numpy islemleri yapar; kayit icin bloklar kuyruga atilir (diske yazma ayri
is parcacigindadir). Akis ciddi bir hatayla durursa (cihaz cikarildi, uyku) arayuz yeniden baslatir.
"""
import gc
import os
import sys
import threading

import mic_core as core

IS_WIN = sys.platform == 'win32'
API_WASAPI, API_MME, API_ASIO = 'Windows WASAPI', 'MME', 'ASIO'
STREAM_OPTION_RAW = 1          # PaWasapiStreamOption.eStreamOptionRaw (Windows 8.1+)
HIGH_PRIORITY_CLASS, NORMAL_PRIORITY_CLASS = 0x80, 0x20


class EngineError(Exception):
    pass


_SD = {}


def load_sounddevice(enable_asio=False):
    """PortAudio'yu yukler. ASIO icin ayri DLL secilir; bu yuzden ilk yuklemeden once karar verilmeli."""
    if 'sd' in _SD:
        return _SD['sd']
    if enable_asio and IS_WIN:
        os.environ['SD_ENABLE_ASIO'] = '1'
    import sounddevice as sd
    _SD['sd'] = sd
    return sd


class _WasapiSettings:
    """sounddevice.WasapiSettings + RAW akis secenegi (Windows ses motoru efektlerini atlar)."""

    def __init__(self, sd, exclusive, raw=True, auto_convert=False):
        self._base = sd.WasapiSettings(exclusive=exclusive, auto_convert=auto_convert and not exclusive)
        self._streaminfo = self._base._streaminfo
        if raw:
            try:
                self._streaminfo.streamOption = STREAM_OPTION_RAW
            except Exception:
                pass


class Attempt:
    def __init__(self, api, in_excl=False, out_excl=False, split=False, label=''):
        self.api, self.in_excl, self.out_excl, self.split, self.label = api, in_excl, out_excl, split, label

    def __repr__(self):
        return 'Attempt(%s, in_excl=%s, out_excl=%s, split=%s)' % (self.api, self.in_excl, self.out_excl, self.split)


def plan(mode, share_output, apis):
    """Denenecek akis bicimleri (sirali). apis: mevcut ana bilgisayar API adlari."""
    w = API_WASAPI in apis
    out = []
    if mode == 'asio':
        if API_ASIO in apis:
            out.append(Attempt(API_ASIO, label='ASIO'))
        return out
    if mode == 'mme':
        if API_MME in apis:
            out += [Attempt(API_MME, label='MME'), Attempt(API_MME, split=True, label='MME (ayri akis)')]
        return out
    if mode in ('auto', 'wasapi_exclusive') and w:
        if not share_output:
            out.append(Attempt(API_WASAPI, True, True, label='WASAPI ozel mod'))
        out.append(Attempt(API_WASAPI, True, False, label='WASAPI ozel giris + paylasimli cikis'))
        out.append(Attempt(API_WASAPI, True, False, split=True, label='WASAPI ozel giris + paylasimli cikis (ayri akis)'))
    if mode in ('auto', 'wasapi_shared') and w:
        out.append(Attempt(API_WASAPI, label='WASAPI paylasimli'))
        out.append(Attempt(API_WASAPI, split=True, label='WASAPI paylasimli (ayri akis)'))
    if mode == 'auto':
        if API_MME in apis:
            out += [Attempt(API_MME, label='MME'), Attempt(API_MME, split=True, label='MME (ayri akis)')]
        if not out:                       # Windows disi (gelistirme): varsayilan API
            out.append(Attempt(None, label='varsayilan'))
            out.append(Attempt(None, split=True, label='varsayilan (ayri akis)'))
    return out


def _uniq(seq):
    seen, out = set(), []
    for x in seq:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


class Engine:
    def __init__(self, sd=None):
        self.sd = sd
        self.stream = None
        self.streams = ()
        self.ring = None
        self.running = False
        self.died = False
        self.info = {}
        self.attempt_log = []
        self.xruns = 0
        self._peak = 0.0
        self._rec = None
        self._lock = threading.Lock()
        self._p = (1.0, 0.64, 'mix', 2)       # giris kazanci, dinleme kazanci, kanal kipi, cikis kanali
        self.callbacks = 0                    # geri cagri sayaci: akis sessizce durursa (kulaklik takildi) artmaz
        self.out_callbacks = 0
        self._last_progress = None

    # ------------------------------------------------------------ cihazlar
    def _sd(self):
        if self.sd is None:
            self.sd = load_sounddevice()
        return self.sd

    def reinit(self):
        """PortAudio'yu kapatip acar: cihaz listesi ve varsayilanlar Windows'tan yeniden okunur.
        (PortAudio listeyi yalnizca baslarken okur; kulaklik takilinca acilan yeni aygiti ancak boyle gorur.)"""
        self.stop()
        sd = self._sd()
        try:
            sd._terminate()
        except Exception:
            pass
        sd._initialize()

    def host_apis(self):
        sd = self._sd()
        return [h['name'] for h in sd.query_hostapis()]

    def _api_index(self, name):
        sd = self._sd()
        for i, h in enumerate(sd.query_hostapis()):
            if h['name'] == name:
                return i
        return None

    def list_devices(self):
        """Arayuz icin cihaz adlari (WASAPI varsa onun tam adlari) ve varsayilanlar."""
        sd = self._sd()
        devs = sd.query_devices()
        apis = sd.query_hostapis()
        ai = self._api_index(API_WASAPI)
        if ai is None:
            ai = sd.default.hostapi if isinstance(sd.default.hostapi, int) and sd.default.hostapi >= 0 else 0
        api = apis[ai]
        ins = [d['name'] for d in devs if d['hostapi'] == ai and d['max_input_channels'] > 0]
        outs = [d['name'] for d in devs if d['hostapi'] == ai and d['max_output_channels'] > 0]
        di, do = api.get('default_input_device', -1), api.get('default_output_device', -1)
        return {
            'inputs': ins, 'outputs': outs,
            'default_input': devs[di]['name'] if isinstance(di, int) and di >= 0 else '',
            'default_output': devs[do]['name'] if isinstance(do, int) and do >= 0 else '',
            'apis': [a['name'] for a in apis],
        }

    def _find(self, api_name, wanted, kind):
        """api_name icindeki cihaz indeksi; bulunamazsa o API'nin varsayilani."""
        sd = self._sd()
        devs = sd.query_devices()
        if api_name is None:
            ai = sd.default.hostapi if isinstance(sd.default.hostapi, int) and sd.default.hostapi >= 0 else 0
        else:
            ai = self._api_index(api_name)
            if ai is None:
                return None
        key = 'max_input_channels' if kind == 'input' else 'max_output_channels'
        cand = [(i, d) for i, d in enumerate(devs) if d['hostapi'] == ai and d[key] > 0]
        j = core.match_device_name(wanted, [d['name'] for _, d in cand])
        if j is not None:
            return cand[j][0]
        api = sd.query_hostapis(ai)
        di = api.get('default_input_device' if kind == 'input' else 'default_output_device', -1)
        if isinstance(di, int) and di >= 0:
            return di
        return cand[0][0] if cand else None

    # ------------------------------------------------------------ parametreler (canli)
    def set_params(self, input_gain_db=None, monitor_volume=None, muted=None, channel_mode=None, cfg=None):
        g, m, ch, oc = self._p
        if cfg is not None:
            input_gain_db = cfg.get('input_gain_db', 0.0)
            monitor_volume = cfg.get('monitor_volume', 80)
            muted = cfg.get('monitor_muted', False)
            channel_mode = cfg.get('channel_mode', 'mix')
        if input_gain_db is not None:
            g = core.db_to_gain(input_gain_db)
        if monitor_volume is not None or muted is not None:
            vol = monitor_volume if monitor_volume is not None else self.info.get('volume', 80)
            mu = muted if muted is not None else self.info.get('muted', False)
            self.info['volume'], self.info['muted'] = vol, mu
            m = core.monitor_gain(vol, mu)
        if channel_mode is not None and self._rec is None:   # kayit surerken kanal sayisi degismez
            ch = channel_mode
        self._p = (g, m, ch, oc)          # tek atama: geri cagri tutarli bir demet gorur

    def take_peak(self):
        p, self._peak = self._peak, 0.0
        return p

    # ------------------------------------------------------------ geri cagrilar
    def _process(self, indata):
        g, m, ch, oc = self._p
        sig = core.select_channels(indata, ch)
        if g != 1.0:
            sig = sig * g
        p = core.peak(sig)
        if p > self._peak:
            self._peak = p
        rec = self._rec
        if rec is not None:
            rec.push(sig)
        return sig, m, oc

    def _cb_duplex(self, indata, outdata, frames, t, status):
        self.callbacks += 1
        if status:
            self.xruns += 1
        try:
            sig, m, oc = self._process(indata)
            if m <= 0.0:
                outdata.fill(0)
            else:
                outdata[:] = core.fit_output(sig * m, outdata.shape[1])
        except Exception:
            outdata.fill(0)

    def _cb_in(self, indata, frames, t, status):
        self.callbacks += 1
        if status:
            self.xruns += 1
        try:
            sig, m, oc = self._process(indata)
            if self.ring is not None:
                self.ring.write(core.fit_output(sig, self.ring.ch))
        except Exception:
            pass

    def _cb_out(self, outdata, frames, t, status):
        self.out_callbacks += 1
        if status:
            self.xruns += 1
        ring = self.ring
        m = self._p[1]
        if ring is None or m <= 0.0:
            outdata.fill(0)
            if ring is not None:            # okumaya devam: tampon birikmesin
                tmp = outdata.copy()
                ring.read(tmp)
            return
        ring.read(outdata)
        if m != 1.0:
            outdata *= m

    def _finished(self):
        if self.running:
            self.died = True

    # ------------------------------------------------------------ baslat / durdur
    def start(self, cfg):
        self.stop()
        sd = self._sd()
        self.attempt_log = []
        apis = self.host_apis()
        attempts = plan(cfg.get('mode', 'auto'), cfg.get('share_output', False), apis)
        if not attempts:
            raise EngineError('Secilen ses kipi (%s) bu bilgisayarda yok.' % core.MODE_LABELS.get(cfg.get('mode'), cfg.get('mode')))
        lat = max(1, int(cfg.get('buffer_ms', 5))) / 1000.0
        self.set_params(cfg=cfg)
        last = None
        for a in attempts:
            ii = self._find(a.api, cfg.get('input_device'), 'input')
            oi = self._find(a.api, cfg.get('output_device'), 'output')
            if ii is None or oi is None:
                self.attempt_log.append('%s: cihaz yok' % a.label)
                continue
            din, dout = sd.query_devices(ii), sd.query_devices(oi)
            exclusive = a.in_excl or a.out_excl
            rates = _uniq([int(cfg.get('samplerate', 48000)), 48000, 44100]) if exclusive else \
                _uniq([int(din['default_samplerate']), int(dout['default_samplerate']), int(cfg.get('samplerate', 48000))])
            ich_opts = _uniq([min(2, din['max_input_channels']), din['max_input_channels']] if a.in_excl
                             else [min(2, din['max_input_channels'])])
            och_opts = _uniq([min(2, dout['max_output_channels']), dout['max_output_channels']] if a.out_excl
                             else [min(2, dout['max_output_channels'])])
            # surucu cok kucuk tamponu reddederse (ozel modda en kucuk periyot ~3 ms) daha buyugunu dene
            lats = [lat, max(lat * 2, 0.010)] if exclusive and lat < 0.010 else [lat]
            combos = [(sr, ich, och, la) for la in lats for sr in rates for ich in ich_opts for och in och_opts]
            for sr, ich, och, la in combos:
                try:
                    self._open(a, ii, oi, sr, ich, och, la)
                except Exception as e:
                    last = e
                    self.attempt_log.append('%s %d Hz %d/%d kanal %.0f ms: %s' % (a.label, sr, ich, och, la * 1000, str(e).strip()[:160]))
                    self._close_streams()
                    continue
                self.info.update({'mode': a.label, 'samplerate': sr, 'in_ch': ich, 'out_ch': och,
                                  'input': din['name'], 'output': dout['name'], 'exclusive': exclusive,
                                  'raw': a.api == API_WASAPI, 'split': a.split})
                self.info['latency_ms'] = self._latency_ms(sr)
                self.attempt_log.append('OK %s %d Hz %d/%d kanal' % (a.label, sr, ich, och))
                core.log_line('start: ' + ' | '.join(self.attempt_log[-6:]))
                self._priority(True)
                return dict(self.info)
        core.log_line('start failed: ' + ' | '.join(self.attempt_log))
        raise EngineError(_explain(last, self.attempt_log))

    def _settings(self, a, exclusive):
        if a.api == API_WASAPI:
            return _WasapiSettings(self.sd, exclusive=exclusive, raw=True, auto_convert=not exclusive)
        return None

    def _open(self, a, ii, oi, sr, ich, och, lat):
        sd = self.sd
        g, m, ch, _ = self._p
        self._p = (g, m, ch, och)
        self.xruns = 0
        self.died = False
        self._last_progress = None
        ins, outs = self._settings(a, a.in_excl), self._settings(a, a.out_excl)
        if not a.split:
            extra = (ins, outs) if (ins or outs) else None
            s = sd.Stream(device=(ii, oi), samplerate=sr, channels=(ich, och), dtype='float32', latency=(lat, lat),
                          blocksize=0, extra_settings=extra, callback=self._cb_duplex,
                          finished_callback=self._finished)
            self.stream, self.streams = s, (s,)
        else:
            ring_ch = 2 if och >= 2 else 1
            blk = max(32, int(sr * lat))
            self.ring = core.RingBuffer(ring_ch, capacity=sr, target=blk)
            si = sd.InputStream(device=ii, samplerate=sr, channels=ich, dtype='float32', latency=lat, blocksize=0,
                                extra_settings=ins, callback=self._cb_in, finished_callback=self._finished)
            self.streams = (si,)
            so = sd.OutputStream(device=oi, samplerate=sr, channels=och, dtype='float32', latency=lat, blocksize=0,
                                 extra_settings=outs, callback=self._cb_out, finished_callback=self._finished)
            self.streams = (si, so)
            self.stream = si
        for s in self.streams:
            s.start()
        self.running = True
        gc.collect()
        try:
            gc.freeze()                # GC duraksamalari ses is parcacigini geciktirmesin
        except AttributeError:
            pass

    def _latency_ms(self, sr):
        total = 0.0
        parts = []
        for s in self.streams:
            l = s.latency
            if isinstance(l, (tuple, list)):
                parts += [float(l[0]), float(l[1])]
            else:
                parts.append(float(l))
        total = sum(parts) * 1000.0
        if self.ring is not None:
            total += self.ring.target * 1000.0 / sr
        return round(total, 1)

    def _close_streams(self):
        for s in self.streams:
            try:
                s.abort()
            except Exception:
                pass
            try:
                s.close()
            except Exception:
                pass
        self.streams = ()
        self.stream = None
        self.ring = None

    def stop(self):
        was = self.running
        self.running = False
        self.stop_recording()
        self._close_streams()
        if was:
            self._priority(False)
            try:
                gc.unfreeze()
            except AttributeError:
                pass

    def check_progress(self):
        """Arayuz ~0,5 sn'de bir cagirir. Son cagridan beri ses geri cagrilari ilerlediyse True.
        Windows ozel moddaki akisi gecersiz kildiginda (kulaklik takildi, format degisti) PortAudio hata
        bildirmeden geri cagirmayi birakabilir; bunu yalniz bu sayac yakalar."""
        cur = (self.callbacks, self.out_callbacks)
        last, self._last_progress = self._last_progress, cur
        if last is None:
            return True
        if self.ring is None:
            return cur[0] != last[0]
        return cur[0] != last[0] and cur[1] != last[1]

    def alive(self):
        if not self.running:
            return False
        if self.died:
            return False
        try:
            return all(s.active for s in self.streams)
        except Exception:
            return False

    # ------------------------------------------------------------ kayit
    def start_recording(self, record_dir, bits=24):
        if not self.running:
            raise EngineError('Once dinlemeyi baslatin.')
        if self._rec is not None:
            return self._rec.path
        d = core.resolve_record_dir(record_dir)
        ch = 2 if self._p[2] == 'stereo' else 1
        rec = core.WavRecorder(d / core.recording_name(), self.info.get('samplerate', 48000), ch, bits)
        self._rec = rec
        return rec.path

    @property
    def recording(self):
        return self._rec

    def stop_recording(self):
        rec, self._rec = self._rec, None
        if rec is None:
            return None
        rec.close()
        return rec

    # ------------------------------------------------------------ yardimci
    def _priority(self, high):
        if not IS_WIN:
            return
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetPriorityClass(k.GetCurrentProcess(), HIGH_PRIORITY_CLASS if high else NORMAL_PRIORITY_CLASS)
        except Exception:
            pass


def _explain(err, log):
    text = ' '.join(log).lower()
    msg = 'Ses akisi acilamadi.'
    if 'exclusive' in text or 'ozel' in text:
        msg += (' Ozel mod reddedildiyse: Ses ayarlari > Kayit > Mikrofon > Ozellikler > Gelismis sekmesinde '
                '"Uygulamalarin bu aygiti ozel olarak denetlemesine izin ver" secenegini acin; mikrofonu kullanan '
                'baska bir programi (Zoom, Teams, tarayici) kapatin.')
    if 'invalid device' in text or 'unanticipated host error' in text:
        msg += ' Cihaz cikarilmis ya da baska bir uygulama tarafindan kilitlenmis olabilir.'
    if err is not None:
        msg += '\n\nSon hata: %s' % str(err).strip()[:300]
    return msg


# --------------------------------------------------------------------------- aygit degisikligi algilama
def device_signature():
    """Windows'taki etkin ses aygitlarinin ve varsayilanlarin ozeti (winmm; PortAudio'dan bagimsiz, ucuz).

    Kulaklik takilip cikarildiginda, USB mikrofon baglandiginda ya da varsayilan aygit degistiginde degisir.
    Windows disinda None doner (degisiklik izlenmez)."""
    if not IS_WIN:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        winmm = ctypes.windll.winmm

        class OUTCAPS(ctypes.Structure):
            _fields_ = [('wMid', wintypes.WORD), ('wPid', wintypes.WORD), ('vDriverVersion', wintypes.UINT),
                        ('szPname', wintypes.WCHAR * 32), ('dwFormats', wintypes.DWORD), ('wChannels', wintypes.WORD),
                        ('wReserved1', wintypes.WORD), ('dwSupport', wintypes.DWORD)]

        class INCAPS(ctypes.Structure):
            _fields_ = [('wMid', wintypes.WORD), ('wPid', wintypes.WORD), ('vDriverVersion', wintypes.UINT),
                        ('szPname', wintypes.WCHAR * 32), ('dwFormats', wintypes.DWORD), ('wChannels', wintypes.WORD),
                        ('wReserved1', wintypes.WORD)]

        outs, ins = [], []
        for i in range(winmm.waveOutGetNumDevs()):
            c = OUTCAPS()
            if winmm.waveOutGetDevCapsW(i, ctypes.byref(c), ctypes.sizeof(c)) == 0:
                outs.append(c.szPname)
        for i in range(winmm.waveInGetNumDevs()):
            c = INCAPS()
            if winmm.waveInGetDevCapsW(i, ctypes.byref(c), ctypes.sizeof(c)) == 0:
                ins.append(c.szPname)
        DRVM_MAPPER_PREFERRED_GET = 0x2015
        WAVE_MAPPER = ctypes.c_void_p(-1 & 0xFFFFFFFFFFFFFFFF)
        pref = []
        for fn in (winmm.waveOutMessage, winmm.waveInMessage):
            dev, flags = wintypes.DWORD(0xFFFFFFFF), wintypes.DWORD(0)
            fn.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p]
            fn(WAVE_MAPPER, DRVM_MAPPER_PREFERRED_GET, ctypes.byref(dev), ctypes.byref(flags))
            pref.append(int(dev.value))
        return (tuple(outs), tuple(ins), tuple(pref))
    except Exception as e:
        core.log_line('device_signature: %r' % e)
        return None
