"""AGFO Mic Monitor - altyapi, hizali vokal kaydi ve karisim testleri (numpy + soundfile; ses aygiti gerekmez).

    python -I tests/test_backing.py <mic-monitor klasoru>
"""
import os
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
os.environ['LOCALAPPDATA'] = tempfile.mkdtemp(prefix='micmon-bg-')
import numpy as np  # noqa: E402
import mic_core as core  # noqa: E402
import mic_engine as eng  # noqa: E402
import mic_backing as mb  # noqa: E402
from fake_sd import FakeSD  # noqa: E402

PASSED = []
TMP = pathlib.Path(tempfile.mkdtemp(prefix='micmon-bgf-'))


def test(fn):
    fn()
    PASSED.append(fn.__name__)
    return fn


def tone_err_db(sr_in, sr_out, f):
    t = np.arange(sr_in) / sr_in
    x = np.stack([np.sin(2 * np.pi * f * t)] * 2, 1).astype(np.float32) * 0.5
    y = mb.resample(x, sr_in, sr_out)
    ref = 0.5 * np.sin(2 * np.pi * f * np.arange(len(y)) / sr_out)
    e = y[2000:-2000, 0] - ref[2000:-2000]
    return len(y), 20 * np.log10(np.sqrt((e ** 2).mean()) / 0.3536)


@test
def resample_accurate_and_fast():
    for sr_in, sr_out in ((44100, 48000), (48000, 44100), (22050, 48000), (96000, 48000), (32000, 48000)):
        n, db = tone_err_db(sr_in, sr_out, 1000)
        assert n == sr_out and db < -75, (sr_in, sr_out, db)
    x = (np.random.RandomState(0).randn(44100 * 60, 2) * 0.1).astype(np.float32)
    t = time.perf_counter()
    mb.resample(x, 44100, 48000)
    assert time.perf_counter() - t < 5.0                     # 1 dakikalik stereo


def make_backing(seconds=1.0, sr=48000, name='altyapi.wav'):
    rs = np.random.RandomState(7)
    data = (rs.randn(int(sr * seconds), 2) * 0.2).astype(np.float32)
    p = mb.write_wav(TMP / name, data, sr, 24)
    return p, data


@test
def backing_loads_formats_and_reads():
    import soundfile as sf
    p, data = make_backing(0.5, 44100)
    bk = mb.BackingTrack(p)
    assert bk.src_sr == 44100 and abs(bk.duration - 0.5) < 1e-3 and not bk.ready
    bk.prepare(48000)
    assert bk.ready and bk.sr == 48000 and len(bk.data) == 24000
    assert bk.read(100) is None                              # calmiyor
    bk.play(from_start=True)
    total = 0
    while bk.playing:
        b = bk.read(1000); total += len(b)
    assert bk.ended and total == 24000
    mono = TMP / 'mono.flac'
    sf.write(str(mono), data[:, 0], 44100)
    assert mb.BackingTrack(mono).src.shape[1] == 2           # mono -> stereo
    if 'MP3' in sf.available_formats():
        mp3 = TMP / 'a.mp3'
        try:
            sf.write(str(mp3), data, 44100, format='MP3')
            assert mb.BackingTrack(mp3).duration > 0.4
        except Exception as e:                               # bazi libsndfile derlemeleri yalniz okur
            print('  (mp3 yazilamadi: %s)' % e)


def cfg(**kw):
    c = dict(core.DEFAULT_CONFIG)
    c.update(kw)
    return c


@test
def vocal_aligned_with_backing_despite_latency():
    """Altyapi cikisa gider, sarkici onu gidis-donus gecikmesiyle (R) mikrofona geri verir.
    Vokal dosyasi altyapiyla ornek ornek ayni noktadan baslamali."""
    _, data = make_backing(1.0, 48000, 'bg48.wav')
    sd = FakeSD()
    e = eng.Engine(sd)
    e.start(cfg(monitor_muted=True))          # sarkici yalniz altyapiyi duyar (kendi sesini degil)
    bk = mb.BackingTrack(TMP / 'bg48.wav'); bk.prepare(48000)
    e.set_backing(bk); e.set_bg_volume(100)
    R = e.roundtrip_frames()
    assert R == 480                                          # FakeSD: giris 5 ms + cikis 5 ms
    cb = sd.opened[-1].callback
    path = e.start_recording(TMP / 'rec', 24, with_backing=True)
    assert path.name.endswith('_vokal.wav')
    blk = 240
    played = []
    out = np.zeros((blk, 2), dtype=np.float32)
    heard = np.zeros((0, 2), dtype=np.float32)
    for k in range(int(48000 * 1.2) // blk):
        # sarkici: R ornek once cikan sesi soyler (ayni hizada mikrofona gelir)
        start = k * blk - R
        if start < 0:
            mic = np.zeros((blk, 2), dtype=np.float32)
            if start + blk > 0:
                mic[-(start + blk):] = heard[:start + blk] if len(heard) >= start + blk else 0
        else:
            mic = heard[start:start + blk]
            if len(mic) < blk:
                mic = np.concatenate([mic, np.zeros((blk - len(mic), 2), np.float32)])
        cb(mic, out, blk, None, None)
        heard = np.concatenate([heard, out.copy()])
        played.append(out.copy())
    rec = e.stop_recording()
    voc, sr = mb.read_wav(rec.path)
    ref = data.mean(axis=1)
    n = min(len(voc), len(ref)) - 10
    assert n > 40000
    assert np.max(np.abs(voc[:n, 0] - ref[:n])) < 1e-4, np.max(np.abs(voc[:n, 0] - ref[:n]))
    e.stop()


@test
def offset_shifts_vocal():
    _, data = make_backing(0.5, 48000, 'bg_off.wav')
    sd = FakeSD()
    e = eng.Engine(sd)
    e.start(cfg())
    bk = mb.BackingTrack(TMP / 'bg_off.wav'); bk.prepare(48000); e.set_backing(bk)
    e.start_recording(TMP / 'rec2', 16, with_backing=True, offset_ms=5)     # +5 ms: 240 ornek daha erken
    cb = sd.opened[-1].callback
    out = np.zeros((480, 2), dtype=np.float32)
    ramp = np.arange(48000, dtype=np.float32)[:, None].repeat(2, 1) / 48000.0
    for k in range(100):
        cb(ramp[k * 480:(k + 1) * 480], out, 480, None, None)
    rec = e.stop_recording()
    voc, _ = mb.read_wav(rec.path)
    assert abs(voc[0, 0] - (480 + 240) / 48000.0) < 1e-3          # R=480 + 240 atildi
    e.stop()


@test
def mix_contains_backing_and_vocal_without_clipping():
    _, data = make_backing(0.5, 48000, 'bg_mix.wav')
    bk = mb.BackingTrack(TMP / 'bg_mix.wav'); bk.prepare(48000)
    voc = (np.sin(2 * np.pi * 440 * np.arange(12000) / 48000) * 0.9).astype(np.float32)[:, None]
    vp = mb.write_wav(TMP / 'Kayit_x_vokal.wav', voc, 48000, 24)
    out = mb.make_mix(vp, bk, 0.5)
    assert out.name == 'Kayit_x_karisim.wav'
    mix, sr = mb.read_wav(out)
    assert sr == 48000 and mix.shape == (24000, 2)
    assert np.abs(mix).max() <= 10 ** (-1 / 20.0) + 1e-3                    # -1 dBFS siniri
    exp = data * 0.5
    exp[:12000] += voc
    pk = np.abs(exp).max()
    if pk > 10 ** (-1 / 20.0):
        exp *= 10 ** (-1 / 20.0) / pk
    assert np.max(np.abs(mix - exp)) < 1e-3
    out2 = mb.make_mix(vp, bk, 0.5, fx_cfg={'fx_rev_on': True, 'fx_rev_type': 'Salon', 'fx_rev_mix': 40})
    mix2, _ = mb.read_wav(out2)
    assert len(mix2) >= 24000 and np.abs(mix2[12000:24000] - mix[12000:]).max() > 1e-3   # reverb kuyrugu karisimda (gerekirse altyapidan uzun)


@test
def loop_plays_seamlessly_and_mix_tiles_with_fade():
    p = mb.write_wav(TMP / 'bed.wav', np.arange(1000, dtype=np.float32)[:, None].repeat(2, 1) / 1000.0, 48000, 24)
    bk = mb.BackingTrack(p); bk.prepare(48000); bk.loop = True
    bk.play(from_start=True)
    got = np.concatenate([bk.read(300) for _ in range(10)])        # 3000 ornek: 3 tur
    exp = np.tile(bk.data, (3, 1))
    assert np.allclose(got, exp) and bk.playing and not bk.ended
    voc = np.zeros((48000 * 3, 1), dtype=np.float32)
    vp = mb.write_wav(TMP / 'L_vokal.wav', voc, 48000, 16)
    out = mb.make_mix(vp, bk, 1.0, loop=True)
    mix, _ = mb.read_wav(out)
    assert len(mix) == len(voc)                                     # vokal boyunca, kisa muzik dongude
    assert np.abs(mix[-10:]).max() < 1e-3 and np.abs(mix[48500:48600]).max() > 0.3   # sonda kapanis, ortada muzik


@test
def stop_before_first_callback_returns_recording():
    _, data = make_backing(0.2, 48000, 'bg_s.wav')
    sd = FakeSD()
    e = eng.Engine(sd)
    e.start(cfg())
    bk = mb.BackingTrack(TMP / 'bg_s.wav'); bk.prepare(48000); e.set_backing(bk)
    e.start_recording(TMP / 'rec3', 16, with_backing=True)
    assert e.recording is not None
    rec = e.stop_recording()
    assert rec is not None and e.recording is None and not bk.playing
    e.stop()


print('OK - %d test gecti: %s' % (len(PASSED), ', '.join(PASSED)))
