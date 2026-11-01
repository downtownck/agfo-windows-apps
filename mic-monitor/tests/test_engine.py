"""AGFO Mic Monitor - mic_engine testleri, sahte sounddevice ile (ses aygiti / Windows gerekmez).

Dogrulananlar: deneme sirasi ve geri dusme, RAW + ozel mod ayari, geri cagri isleme (kazanc,
dinleme sesi, susturma, kanal), ayri akis + halka tampon, kayit, olen akisin algilanmasi.

    python -I tests/test_engine.py <mic-monitor klasoru>
"""
import os
import pathlib
import sys
import tempfile
import wave

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))
os.environ['LOCALAPPDATA'] = tempfile.mkdtemp(prefix='micmon-eng-')
import numpy as np  # noqa: E402
import mic_core as core  # noqa: E402
import mic_engine as eng  # noqa: E402
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fake_sd import FakeSD  # noqa: E402

PASSED = []


def test(fn):
    fn()
    PASSED.append(fn.__name__)
    return fn


def cfg(**kw):
    c = dict(core.DEFAULT_CONFIG)
    c.update(kw)
    return c


def excl(kw):
    es = kw.get('extra_settings')
    if es is None:
        return False
    if isinstance(es, tuple):
        return any(e is not None and e._streaminfo.flags & 1 for e in es)
    return bool(es._streaminfo.flags & 1)


@test
def plan_order():
    apis = ['MME', 'Windows WASAPI']
    labels = [a.label for a in eng.plan('auto', False, apis)]
    assert labels[0] == 'WASAPI ozel mod' and labels[-1].startswith('MME')
    assert all(not (a.out_excl) for a in eng.plan('auto', True, apis))          # cikis paylasimli istendi
    assert [a.api for a in eng.plan('mme', False, apis)] == ['MME', 'MME']
    assert eng.plan('asio', False, apis) == []
    assert eng.plan('asio', False, apis + ['ASIO'])[0].api == 'ASIO'
    assert eng.plan('auto', False, ['ALSA'])[0].api is None                       # gelistirme makinesi


@test
def exclusive_raw_duplex_first():
    sd = FakeSD()
    e = eng.Engine(sd)
    info = e.start(cfg(input_device='Mikrofon (Realtek(R) Audio)', output_device='Kulaklık (Realtek(R) Audio)'))
    assert info['mode'] == 'WASAPI ozel mod' and info['exclusive'] and info['raw'] and not info['split']
    s = sd.opened[-1]
    ins, outs = s.kw['extra_settings']
    assert ins._streaminfo.flags & 1 and outs._streaminfo.flags & 1
    assert ins._streaminfo.streamOption == eng.STREAM_OPTION_RAW == outs._streaminfo.streamOption
    assert s.kw['device'] == (3, 4)                                   # WASAPI'deki cihazlar
    assert s.kw['latency'] == (0.005, 0.005) and s.kw['blocksize'] == 0
    assert info['latency_ms'] == 10.0
    assert e.alive()
    e.stop()
    assert not e.alive() and not s.active


@test
def falls_back_when_exclusive_refused():
    sd = FakeSD(fail=lambda kw: excl(kw))
    e = eng.Engine(sd)
    info = e.start(cfg())
    assert info['mode'] == 'WASAPI paylasimli' and not info['exclusive']
    s = sd.opened[-1]
    assert s.kw['extra_settings'][0]._streaminfo.streamOption == eng.STREAM_OPTION_RAW   # paylasimlida da RAW
    assert s.kw['extra_settings'][0]._streaminfo.flags & 64                               # auto_convert
    assert any('ozel' in x for x in e.attempt_log)
    e.stop()


@test
def falls_back_to_split_when_duplex_refused():
    sd = FakeSD(fail=lambda kw: kw['kind'] == 'duplex')
    e = eng.Engine(sd)
    info = e.start(cfg())
    assert info['split'] and 'ayri akis' in info['mode']
    assert e.ring is not None and len(e.streams) == 2
    e.stop()


@test
def all_attempts_fail_gives_helpful_error():
    sd = FakeSD(fail=lambda kw: True)
    e = eng.Engine(sd)
    try:
        e.start(cfg())
    except eng.EngineError as err:
        assert 'izin ver' in str(err) and 'Son hata' in str(err)
    else:
        raise AssertionError('hata bekleniyordu')
    assert not e.running


@test
def duplex_callback_gain_volume_mute_channels():
    sd = FakeSD()
    e = eng.Engine(sd)
    e.start(cfg(input_gain_db=6.0206, monitor_volume=50, channel_mode='left'))
    cb = sd.opened[-1].callback
    ind = np.array([[0.1, 0.9], [-0.2, 0.0]], dtype=np.float32)
    out = np.zeros((2, 2), dtype=np.float32)
    cb(ind, out, 2, None, None)
    assert np.allclose(out[:, 0], [0.05, -0.1], atol=1e-4) and np.allclose(out[:, 0], out[:, 1])   # x2 kazanc, x0.25 ses
    assert abs(e.take_peak() - 0.4) < 1e-3 and e.take_peak() == 0.0
    e.set_params(muted=True)
    cb(ind, out, 2, None, None)
    assert not out.any()
    e.set_params(muted=False, monitor_volume=100, channel_mode='stereo', input_gain_db=0)
    cb(ind, out, 2, None, None)
    assert np.allclose(out, ind)
    cb(ind, out, 2, None, 'input overflow')
    assert e.xruns == 1
    e.stop()


@test
def split_path_carries_audio():
    sd = FakeSD(fail=lambda kw: kw['kind'] == 'duplex')
    e = eng.Engine(sd)
    e.start(cfg(monitor_volume=100))
    si, so = sd.opened[-2], sd.opened[-1]
    assert si.kind == 'input' and so.kind == 'output'
    blk = np.full((240, 2), 0.3, dtype=np.float32)
    for _ in range(4):
        si.callback(blk, 240, None, None)
    out = np.zeros((240, 2), dtype=np.float32)
    so.callback(out, 240, None, None)
    assert np.allclose(out, 0.3)
    e.set_params(muted=True)
    so.callback(out, 240, None, None)
    assert not out.any()
    e.stop()


@test
def recording_from_callback():
    sd = FakeSD()
    e = eng.Engine(sd)
    e.start(cfg(monitor_muted=True))
    with tempfile.TemporaryDirectory() as td:
        path = e.start_recording(td, 16)
        cb = sd.opened[-1].callback
        out = np.zeros((480, 2), dtype=np.float32)
        for _ in range(100):
            cb(np.full((480, 2), 0.5, dtype=np.float32), out, 480, None, None)
        e.set_params(channel_mode='stereo')                 # kayit surerken kanal kipi degismez
        cb(np.full((480, 2), 0.5, dtype=np.float32), out, 480, None, None)
        rec = e.stop_recording()
        assert rec.frames == 48480 and rec.error is None
        with wave.open(str(path)) as w:
            assert w.getnchannels() == 1 and w.getnframes() == 48480 and w.getframerate() == 48000
        assert not out.any()                                # susturulmusken kulakliga ses gitmez, kayit surer
    e.stop()


@test
def died_stream_detected():
    sd = FakeSD()
    e = eng.Engine(sd)
    e.start(cfg())
    assert e.alive()
    sd.opened[-1].finished()                                # cihaz cikarildi
    assert not e.alive()
    e.stop()
    e.start(cfg())
    assert e.alive()
    sd.opened[-1].active = False
    assert not e.alive()
    e.stop()


@test
def device_list_uses_wasapi_names():
    e = eng.Engine(FakeSD())
    d = e.list_devices()
    assert d['inputs'] == ['Mikrofon (Realtek(R) Audio)']
    assert d['outputs'] == ['Kulaklık (Realtek(R) Audio)', 'Hoparlör (Realtek(R) Audio)']
    assert d['default_output'] == 'Hoparlör (Realtek(R) Audio)'


@test
def exclusive_retries_larger_buffer():
    sd = FakeSD(fail=lambda kw: excl(kw) and kw['latency'][0] < 0.006)
    e = eng.Engine(sd)
    info = e.start(cfg(buffer_ms=3))
    assert info['mode'] == 'WASAPI ozel mod' and sd.opened[-1].kw['latency'] == (0.01, 0.01)
    e.stop()


@test
def progress_and_reinit():
    sd = FakeSD()
    e = eng.Engine(sd)
    e.start(cfg())
    cb = sd.opened[-1].callback
    out = np.zeros((4, 2), dtype=np.float32)
    assert e.check_progress()                         # ilk cagri: referans
    assert not e.check_progress()                     # geri cagri gelmedi
    cb(np.zeros((4, 2), dtype=np.float32), out, 4, None, None)
    assert e.check_progress()
    sd.plug('Kulaklık (USB Audio)')
    assert 'Kulaklık (USB Audio)' not in e.list_devices()['outputs']     # PortAudio eski listeyi tutar
    e.reinit()
    assert not e.running and sd.inits == 1
    d = e.list_devices()
    assert 'Kulaklık (USB Audio)' in d['outputs'] and d['default_output'] == 'Kulaklık (USB Audio)'
    assert eng.device_signature() is None or os.name == 'nt'


print('OK - %d test gecti: %s' % (len(PASSED), ', '.join(PASSED)))
