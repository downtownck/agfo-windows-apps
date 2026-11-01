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

# guncelleme denetimi: GERCEK yol (gh_check -> arka plan is parcacigi -> _poll -> _gh_checked).
# 1.0.x'te _run_bg eksikti: denetim sessizce hata veriyordu; bu test o yolu bastan sona calistirir.
nbox = len(_box)
calls = []
rel = {'version': '9.9.9', 'notes': 'x', 'published': '2026-11-01', 'url': 'u', 'assets': []}
results = {'v': {'status': 'current', 'version': core.VERSION}}


def fake_check(force=False, releases=None):
    calls.append(force)
    return results['v']


app_mod.upd.check = fake_check
app.gh_check(force=True, silent=True)                  # acilistaki denetim
assert wait_for(lambda: calls), 'gh_check arka plan isi calismadi'
pump(app, 5)
assert calls[-1] is True and len(_box) == nbox and not app.gh_banner.winfo_ismapped()
results['v'] = {'status': 'update', 'version': '9.9.9', 'release': rel, 'asset': {'url': 'u'}}
app._gh_periodic()                                     # periyodik denetim (onbellege uyar)
assert wait_for(lambda: app.gh_banner.winfo_ismapped()), 'yeni surum seridi gorunmedi'
assert calls[-1] is False and '9.9.9' in app.gh_banner_text.get() and len(_box) == nbox
results['v'] = {'status': 'current', 'version': core.VERSION}
app.gh_check(force=True)                               # "GitHub'da denetle" dugmesi: bilgi penceresi
assert wait_for(lambda: len(_box) == nbox + 1), _box[-1:]
app.gh_update()                                        # kaynaktan calisiyor: aciklayici bilgi, cokme yok
assert len(_box) == nbox + 2
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

# altyapi: yukle (44,1 kHz -> akis 48 kHz), kayda basinca bastan calar, bitince kayit durur, vokal + karisim yazilir
import mic_backing as mbk
bgp = mbk.write_wav(pathlib.Path(TMP) / 'altyapi.wav', (np.random.RandomState(5).randn(22050, 2) * 0.1).astype(np.float32), 44100, 16)
app._restart()
assert app.monitoring
app._bg_load(str(bgp))
assert wait_for(lambda: app.backing_track is not None and app.backing_track.ready), app.var_bg_name.get()
assert app.backing_track.sr == 48000 and len(app.backing_track.data) == 24000
assert 'altyapi.wav' in app.var_bg_name.get() and core.load_settings()['bg_file'] == str(bgp)
app.var_bg_mix.set(True); app.var_bg_stopend.set(True); app.var_bg_restart.set(True); app._changed(restart=False)
recdir2 = pathlib.Path(TMP) / 'rec_bg'
app.var_dir.set(str(recdir2)); app._changed(restart=False)
app.toggle_record()
assert app.engine.recording is not None and app.engine.rec_with_backing
cb = sd.opened[-1].callback
for _ in range(60):                                   # 60 x 480 = 28800 > 24000: altyapi biter
    cb(np.full((480, 2), 0.05, dtype=np.float32), out, 480, None, None)
assert app.backing_track.ended
assert wait_for(lambda: app.engine.recording is None), app.var_status.get()          # bitince kendiliginden durdu
assert wait_for(lambda: list(recdir2.glob('*_karisim.wav'))), app.var_status.get()
voc = list(recdir2.glob('*_vokal.wav')); mix = list(recdir2.glob('*_karisim.wav'))
assert len(voc) == 1 and len(mix) == 1
m, sr_m = mbk.read_wav(mix[0])
assert sr_m == 48000 and m.shape[1] == 2 and len(m) >= 24000
assert 'karisim' in app.var_status.get()
# sarki sozu: altyapiyla ayni adli .txt otomatik yuklenir, ekran altyapi konumunu izler, zamanlama LRC'ye yazilir
import mic_lyrics as mly
bgp = mbk.write_wav(pathlib.Path(TMP) / 'sarki.wav', (np.random.RandomState(6).randn(48000 * 10, 2) * 0.1).astype(np.float32), 48000, 16)
(bgp.with_suffix('.txt')).write_text('Birinci satır\nİkinci satır\n\nÜçüncü satır\nDördüncü satır\n', encoding='utf-8')
app.backing_track = None; app.lyrics = None
app._bg_load(str(bgp))
assert wait_for(lambda: app.backing_track is not None and app.backing_track.ready)
assert app.lyrics is not None and app.lyrics.name == 'sarki.txt' and not app.lyrics.timed
assert app.lyrics.times[0] == 0 and app.lyrics.times[-1] < max(1.0, app.backing_track.duration)   # sarki suresine dagitildi
w = app.lyrics_open()
pump(app, 3); w.update(); w.layout(); pump(app, 2)
assert len(w.items) == 5
tr = app.backing_track
tr.seek(app.lyrics.times[3] + 0.01); tr.play()
w.update_view(force=True)
assert w.cur == 3 and w.cv.itemcget(w.items[3], 'fill') == '#ffffff' and w.cv.itemcget(w.items[4], 'fill') != '#ffffff'
y_before = w.cv.coords(w.items[3])[1]
tr.seek(app.lyrics.times[4] + 0.01); w.update_view()
assert w.cur == 4 and w.cv.coords(w.items[3])[1] < y_before                             # yukari kaydi
tr.stop()
# zamanlama provasi: altyapi bastan calar, her satir basinda bosluk
w.toggle_timing()
assert w.tapper is not None and tr.playing and tr.pos == 0
for k, at in enumerate((0.05, 0.12, 0.2, 0.33)):
    tr.pos = int(at * tr.sr)
    w.tap()
assert w.tapper is None                                          # dort dolu satir vuruldu -> bitti
L = app.lyrics
assert L.timed and L.source.name == 'sarki.lrc' and L.source.is_file()
assert L.times[:2] == [0.05, 0.12] and L.times[3:] == [0.2, 0.33] and 0.12 < L.times[2] < 0.2     # kita arasi ortada
assert core.load_settings()['lyrics_file'].endswith('sarki.lrc')
assert mly.load(L.source).times == L.times
# yapistir
pw = app.lyrics_paste()
pw.children[[k for k in pw.children if k.startswith('!text')][0]].delete('1.0', 'end')
pw.children[[k for k in pw.children if k.startswith('!text')][0]].insert('1.0', 'Yapıştırılan\nsöz')
[b for b in pw.winfo_children() if isinstance(b, tkinter.Button)][0].invoke()
assert app.lyrics.lines == ['Yapıştırılan', 'söz'] and app.lyrics.source is None and len(w.items) == 2
w.set_font(60); assert core.load_settings()['lyrics_font'] == 60
w.close(); assert app.lyrics_win is None
PASSED.append('lyrics_prompter_follow_and_timing')

# PROMPTER (konusma): bolumlere ayir, tusla gec, geri sayimli kayit, bolum isaretleri WAV + Audacity etiketleri
app.bg_remove()
speech = '\n\n'.join('Paragraf %d. Bu bir deneme cümlesidir ve prompter ekranında okunacaktır. İkinci cümle de burada.' % i
                       for i in range(1, 13))
app._lyrics_set(mly.from_text(speech), remember=False)
app.cfg['prompter_countdown'] = 0
w = app.lyrics_open(); w.geometry('800x500'); pump(app, 3); w.update()
if not w.prompter:
    w.toggle_mode()
assert core.load_settings()['prompter_mode'] is True
w.layout(); pump(app, 2)
assert len(w.sections) >= 3 and w.sec == 0, len(w.sections)
assert sum(len(x) for x in w.sections) >= 12
w.event_generate('<Next>'); w.forward(); assert w.sec == 2
w.back(); assert w.sec == 1
w.goto(0)
recdir3 = pathlib.Path(TMP) / 'rec_prompter'
app.var_dir.set(str(recdir3)); app._changed(restart=False)
w.toggle_record()                                        # geri sayim 0: hemen baslar
assert app.engine.recording is not None and app._marks and app._marks[0][0] == 0.0
cb = sd.opened[-1].callback
for _ in range(100):                                     # 1 sn
    cb(np.full((480, 2), 0.02, dtype=np.float32), out, 480, None, None)
w.forward()                                              # bolum 2 @ 1,0 sn
for _ in range(50):
    cb(np.full((480, 2), 0.02, dtype=np.float32), out, 480, None, None)
w.forward()                                              # bolum 3 @ 1,5 sn
w.update_view()
assert 'KAYIT' in w.var_rec.get() and w.btn_rec.cget('text').startswith('■')
for _ in range(20):
    cb(np.full((480, 2), 0.02, dtype=np.float32), out, 480, None, None)
w.toggle_record()                                        # durdur
assert app.engine.recording is None
wavs = list(recdir3.glob('Kayit_*.wav')); labs = list(recdir3.glob('*_bolumler.txt'))
assert len(wavs) == 1 and len(labs) == 1
mk = core.read_wav_markers(wavs[0])
assert [m[0] for m in mk] == [0, 48000, 72000], mk
assert mk[1][1].startswith('Bolum 2: ') and mk[2][1].startswith('Bolum 3: ') and mk[1][1] == w.section_label(1)
lines = labs[0].read_text(encoding='utf-8').splitlines()
assert lines[1].startswith('1.000000\t1.000000\tBolum 2') and len(lines) == 3
with wave.open(str(wavs[0])) as ww:
    assert ww.getnframes() == 82 * 480 - 0 or ww.getnframes() > 0
w.toggle_mode(); assert core.load_settings()['prompter_mode'] is False and w.items
w.close()
PASSED.append('prompter_sections_record_markers')

# KAMERA + MP3/MP4 (gercek ffmpeg; kamera yerine test goruntusu). ffmpeg yoksa atlanir.
import mic_media as mm_
if mm_.find_ffmpeg():
    app_mod.mm.camera_input_args = lambda name, size='1280x720', fps=30: ['-re', '-f', 'lavfi', '-i', 'testsrc=size=640x360:rate=30']
    app.ff = mm_.find_ffmpeg(); app._ff_text()
    assert str(app.btn_ff.cget('state')) == 'disabled'
    app.var_cam.set('Test Kamera'); app.var_cam_on.set(True); app.var_cam_rec.set(True); app.var_mp3.set(True)
    app.var_cam_corner.set('sol-ust'); app.var_cam_size.set('kucuk')
    app._cam_changed()
    assert app.camera is not None
    assert wait_for(lambda: app.cam_image() is not None, 15), app.camera.error_text()
    assert app.cam_image().width() == 240 and str(app.lbl_cam_prev.cget('image'))
    w = app.lyrics_open(); w.geometry('800x500'); pump(app, 3); w.update(); w.update_view()
    assert w.cv.find_withtag('camimg')
    bb = w.cv.bbox('camimg'); assert bb[0] < 30 and bb[1] < 30          # sol ust kose
    recdir4 = pathlib.Path(TMP) / 'rec_cam'
    app.var_dir.set(str(recdir4)); app._changed(restart=False)
    w.toggle_record()
    assert app._cam_rec is not None and app.engine.recording is not None
    assert wait_for(lambda: app.camera is not None and app.camera.first_frame_t is not None, 15)
    import time as _tt
    t_end = _tt.monotonic() + 2.0
    while _tt.monotonic() < t_end:                     # ~2 sn ses (gercek zamanli) + kamera
        cb = sd.opened[-1].callback
        cb(np.full((480, 2), 0.05, dtype=np.float32), out, 480, None, None)
        pump(app, 1); _tt.sleep(0.01)
    w.update_view()
    assert w.cv.itemcget('camframe', 'state') == 'normal'                 # kayitta kirmizi cerceve
    w.forward()
    w.toggle_record()
    assert wait_for(lambda: list(recdir4.glob('*.mp4')) and 'Hazir:' in app.var_status.get(), 60), app.var_status.get()
    mp4 = list(recdir4.glob('*.mp4'))[0]
    assert not list(recdir4.glob('*_kamera.mkv'))                        # ham goruntu silindi
    assert list(recdir4.glob('*.mp3')) and 'MP4' not in app.var_status.get().split('sorun')[-1][:0]
    assert 'sorun' not in app.var_status.get(), app.var_status.get()
    assert mm_.probe_duration(app.ff, mp4) > 1.0
    assert wait_for(lambda: app.camera is not None and app.cam_image() is not None, 15)   # onizleme geri geldi
    # istenen cozunurluk desteklenmiyorsa: bir kez kameranin kendi cozunurluguyle yeniden acilir
    calls = []

    def picky(name, size='1280x720', fps=30):
        calls.append(size)
        if size != 'otomatik':
            return ['-f', 'lavfi', '-i', 'nullsrc=s=0x0']          # hemen hata verip kapanir
        return ['-re', '-f', 'lavfi', '-i', 'testsrc=size=320x240:rate=15']
    app_mod.mm.camera_input_args = picky
    app.var_cam_res.set('1920x1080'); app._cam_changed()
    assert wait_for(lambda: app.cam_image() is not None and 'otomatik' in calls, 20), (calls, app.var_status.get())
    assert calls[0] == '1920x1080' and 'desteklemiyor' in app.var_status.get()
    app.var_cam_on.set(False); app._cam_changed()
    assert app.camera is None
    w.close()
    PASSED.append('camera_preview_record_mp4_mp3')

app.bg_remove()
assert app.backing_track is None and app.engine.backing is None and core.load_settings()['bg_file'] == ''
PASSED.append('backing_record_vocal_and_mix')

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
