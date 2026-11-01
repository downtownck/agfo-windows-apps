"""AGFO Mic Monitor - arayuz testi (sahte sounddevice; tkinter + ekran gerekir, Linux'ta xvfb-run ile).

Arayuz kurulur; dinleme baslatilir, canli kazanc/ses degisiklikleri motora gider, cihaz degisince akis
yeniden acilir, kayit baslar/durur, olen akis yeniden acilir, kapanista ayarlar kaydedilir.

    xvfb-run -a python -I tests/test_gui.py <mic-monitor klasoru>
"""
import os
import pathlib
import sys
import tempfile
import wave

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
try:
    import tkinter  # noqa: F401
except ImportError:
    print('SKIP - tkinter yok')
    sys.exit(0)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
TMP = tempfile.mkdtemp(prefix='micmon-gui-')
os.environ['LOCALAPPDATA'] = TMP
import numpy as np  # noqa: E402
from fake_sd import FakeSD  # noqa: E402
import importlib.machinery  # noqa: E402
import importlib.util  # noqa: E402

_loader = importlib.machinery.SourceFileLoader('micmon_app', str(ROOT / 'app.pyw'))
spec = importlib.util.spec_from_loader('micmon_app', _loader)
app_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_mod)
core = app_mod.core

PASSED = []
_box = []
app_mod.messagebox.showerror = lambda *a, **k: _box.append(('error',) + a)
app_mod.messagebox.showinfo = lambda *a, **k: _box.append(('info',) + a)
app_mod.messagebox.askyesno = lambda *a, **k: True


def pump(app, n=5):
    for _ in range(n):
        app.update_idletasks()
        app.update()


sd = FakeSD()
app = app_mod.App(sd=sd)
pump(app)

# cihaz listesi ve uyari (varsayilan cikis hoparlor -> geri besleme uyarisi)
assert app.cmb_in.cget('values')[1] == 'Mikrofon (Realtek(R) Audio)'
assert 'geri besleme' in app.var_warn.get()
app.var_out.set('Kulaklık (Realtek(R) Audio)')
app._changed(restart=False)
assert app.var_warn.get() == ''
PASSED.append('devices_and_warnings')

# dinlemeyi baslat
assert app.start() is True and app.monitoring
assert 'WASAPI ozel mod' in app.var_status.get()
assert sd.opened[-1].kw['device'] == (3, 4)
PASSED.append('start_exclusive')

# canli kazanc / ses: akis yeniden acilmaz, motor parametreleri degisir
n = len(sd.opened)
app.var_gain.set(6.0); app.var_vol.set(100); app._live()
assert len(sd.opened) == n
g, m, ch, oc = app.engine._p
assert abs(g - 1.995) < 0.01 and m == 1.0
app.var_mute.set(True); app._live()
assert app.engine._p[1] == 0.0
app.var_mute.set(False); app._live()
PASSED.append('live_params')

# seviye olcer: geri cagriya ses ver, dongu cizsin
out = np.zeros((480, 2), dtype=np.float32)
app.after_cancel(app._poll_job)                     # zamanlamadan bagimsiz: donguyu elle cagir
app.engine.take_peak(); app.meter = app.meter_hold = -60.0
sd.opened[-1].callback(np.full((480, 2), 0.5, dtype=np.float32), out, 480, None, None)
app._poll()
assert -1.0 < app.meter <= 0.1, app.meter          # 0.5 * 2 kazanc = 1.0 -> 0 dBFS
assert app.var_db.get().strip().endswith('dBFS')
PASSED.append('meter')

# tampon degisince akis yeniden acilir
app.var_buf.set('10 ms'); app._changed(restart=True)
app.after_cancel(app._restart_job); app._restart()
assert sd.opened[-1].kw['latency'] == (0.01, 0.01) and app.monitoring
PASSED.append('restart_on_setting_change')

# kayit
recdir = pathlib.Path(TMP) / 'rec'
app.var_dir.set(str(recdir)); app._changed(restart=False)
app.toggle_record()
assert app.engine.recording is not None and 'Kaydi durdur' in app.btn_rec.cget('text')
for _ in range(50):
    sd.opened[-1].callback(np.full((480, 2), 0.1, dtype=np.float32), out, 480, None, None)
app._update_info()
assert 'KAYIT' in app.var_info.get()
app.toggle_record()
files = list(recdir.glob('Kayit_*.wav'))
assert len(files) == 1
with wave.open(str(files[0])) as w:
    assert w.getnframes() == 24000 and w.getsampwidth() == 3
assert 'Kaydedildi' in app.var_status.get()
PASSED.append('record_toggle')



def wait_for(cond, secs=8.0):
    import time as _t
    end = _t.monotonic() + secs
    while _t.monotonic() < end:
        pump(app, 1)
        if cond():
            return True
        _t.sleep(0.02)
    return False


def feed():
    sd.opened[-1].callback(np.zeros((480, 2), dtype=np.float32), out, 480, None, None)


# olen akis yeniden acilir (PortAudio yeniden baslatilir, kisa beklemeyle)
sd.opened[-1].finished()
n, inits = len(sd.opened), sd.inits
app._last_stats = 0; app._poll()
assert not app.monitoring and 'yeniden aciliyor' in app.var_status.get()
assert wait_for(lambda: app.monitoring), app.var_status.get()
assert len(sd.opened) > n and sd.inits > inits and "yeniden acildi" in app.var_status.get(), (len(sd.opened), n, sd.inits, inits, app.var_status.get())
PASSED.append('recover_dead_stream')

# sessizce takilan akis (Windows ozel mod akisini gecersiz kildi, PortAudio hata vermedi): sayac yakalar
n = len(sd.opened)
feed(); app._last_stats = 0; app._poll()              # ilerleme var
for _ in range(app_mod.STALL_TICKS):
    app._last_stats = 0; app._poll()                  # geri cagri yok
assert wait_for(lambda: app.monitoring and len(sd.opened) > n), app.var_status.get()
PASSED.append('recover_stalled_stream')

# kulaklik takildi: cikis acikca Hoparlor seciliyken yeni kulaklik aygitina gecilir
SIG = {'v': ('a',)}
app_mod.eng.device_signature = lambda: SIG['v']
app._dev_sig = SIG['v']
app.var_out.set('Hoparlör (Realtek(R) Audio)'); app._changed(restart=False)
app._restart()
assert app.engine.info['output'] == 'Hoparlör (Realtek(R) Audio)'
sd.plug('Kulaklık (USB Audio)')
SIG['v'] = ('b',)
app._sig_latest = SIG['v']
app._dev_checked = 0; app._poll()
assert wait_for(lambda: app.monitoring and app.engine.info.get('output') == 'Kulaklık (USB Audio)'), app.var_status.get()
assert core.load_settings()['output_device'] == 'Kulaklık (USB Audio)'
assert 'Kulaklık (USB Audio)' in app.var_status.get()
PASSED.append('headphone_plug_switches')

# kulaklik cikarildi: hoparlore dusmek yerine dinleme duraklar (geri besleme olmasin)
sd.unplug('Kulaklık (USB Audio)', new_default='Hoparlör (Realtek(R) Audio)')
SIG['v'] = ('c',)
app._sig_latest = SIG['v']
app._dev_checked = 0; app._poll()
assert wait_for(lambda: app._dev_job is None and not app.monitoring and app._paused_unplug), app.var_status.get()
assert 'duraklatildi' in app.var_status.get()
assert app.var_out.get().endswith(app_mod.MISSING_SUFFIX)          # secim korunur
PASSED.append('headphone_unplug_pauses')

# tekrar takildi: kendiliginden devam
sd.plug('Kulaklık (USB Audio)')
SIG['v'] = ('d',)
app._sig_latest = SIG['v']
app._dev_checked = 0; app._poll()
assert wait_for(lambda: app.monitoring), app.var_status.get()
assert app.engine.info['output'] == 'Kulaklık (USB Audio)' and not app._paused_unplug
assert app.var_out.get() == 'Kulaklık (USB Audio)'
PASSED.append('headphone_replug_resumes')
app.var_out.set('Kulaklık (Realtek(R) Audio)'); app._changed(restart=False)

# sik kesinti (cizirti): tampon bir kademe buyur, akis yeniden acilir
app._restart()
assert app.cfg['buffer_ms'] == 10
cb = sd.opened[-1].callback
import time as _time
now = _time.monotonic()
app.engine.xrun_rate(now)
for _ in range(app_mod.XRUN_LIMIT):
    cb(np.zeros((480, 2), dtype=np.float32), out, 480, None, 'output underflow')
app._auto_buf_at = 0
app._check_crackle(now + 1)
assert app.cfg['buffer_ms'] == 20 and app.monitoring and sd.opened[-1].kw['latency'] == (0.02, 0.02)
assert 'Cizirti algilandi' in app.var_status.get() and core.load_settings()['buffer_ms'] == 20
PASSED.append('crackle_raises_buffer')
app.var_buf.set('10 ms'); app._changed(restart=False)

# guncelleme denetimi: sessiz kipte yeni surum serit gosterir, 'guncel' sonucu pencere acmaz
nbox = len(_box)
app._gh_checked({'status': 'current', 'version': core.VERSION}, True, silent=True)
assert len(_box) == nbox and not app.gh_banner.winfo_ismapped()
rel = {'version': '9.9.9', 'notes': 'x', 'published': '2026-11-01', 'url': 'u', 'assets': []}
app._gh_checked({'status': 'update', 'version': '9.9.9', 'release': rel, 'asset': {'url': 'u'}}, True, silent=True)
pump(app, 2)
assert app.gh_banner.winfo_ismapped() and '9.9.9' in app.gh_banner_text.get() and len(_box) == nbox
app._gh_checked({'status': 'current', 'version': core.VERSION}, True)          # elle denetim: bilgi penceresi
assert len(_box) == nbox + 1
app.gh_banner.pack_forget()
PASSED.append('update_check_silent_and_manual')

# efektler: canli acilip kapanir, oda tipi on ayarlari surgulere yansir, ayar kaydedilir
app.var_rev_type.set('Katedral'); app._rev_preset()
assert app.var_rev_on.get() and abs(app.var_rev_time.get() - 5.0) < 1e-9 and app.engine.fx.reverb.kind == 'Katedral'
app.var_echo_on.set(True); app.var_echo_ms.set(400); app._fx_live()
assert app.engine.fx.echo is not None and app.engine.fx.echo.D == int(0.4 * app.engine.info['samplerate'])
app._update_info()
assert 'efekt: yanki + reverb (Katedral)' in app.var_info.get()
app.var_echo_on.set(False); app.var_rev_on.set(False); app._fx_live()
assert app.engine.fx is None
app._save_job and app.after_cancel(app._save_job)
core.save_settings(app.cfg)
assert core.load_settings()['fx_rev_type'] == 'Katedral' and core.load_settings()['fx_echo_ms'] == 400
PASSED.append('effects_live')

# durdur + kapat: ayarlar kaydedilir
app.stop()
assert not app.monitoring and not sd.opened[-1].active
app._on_close()
saved = core.load_settings()
assert saved['output_device'] == 'Kulaklık (Realtek(R) Audio)' and saved['buffer_ms'] == 10
assert saved['input_gain_db'] == 6.0 and saved['monitor_volume'] == 100
PASSED.append('stop_close_saves')

# PortAudio yuklenemezse arayuz yine acilir ve hatayi gosterir
class Broken:
    def query_hostapis(self, *a):
        raise OSError('PortAudio library not found')


app2 = app_mod.App(sd=Broken())
pump(app2, 2)
assert app2.engine is not None                        # motor nesnesi var ama listeleme hata verdi
app2.destroy()
assert not [b for b in _box if b[0] == 'error'], _box
PASSED.append('broken_portaudio_still_opens')

print('OK - %d test gecti: %s' % (len(PASSED), ', '.join(PASSED)))
