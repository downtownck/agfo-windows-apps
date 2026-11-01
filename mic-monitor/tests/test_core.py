"""AGFO Mic Monitor - mic_core testleri (numpy gerekir; ses aygiti gerekmez).

    python -I tests/test_core.py <mic-monitor klasoru>
"""
import os
import pathlib
import sys
import tempfile
import wave

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))
_TMP = tempfile.mkdtemp(prefix='micmon-test-')
os.environ['LOCALAPPDATA'] = _TMP
import numpy as np  # noqa: E402
import mic_core as core  # noqa: E402

PASSED = []


def test(fn):
    fn()
    PASSED.append(fn.__name__)
    return fn


@test
def settings_roundtrip_and_clean():
    assert core.load_settings() == core.DEFAULT_CONFIG
    c = dict(core.DEFAULT_CONFIG, mode='bogus', buffer_ms='7', input_gain_db=99, monitor_volume=-5,
             record_bits=8, samplerate=12345, channel_mode='left', share_output=1, unknown='x')
    assert core.save_settings(c)
    got = core.load_settings()
    assert got['mode'] == 'auto' and got['buffer_ms'] == 7 and got['input_gain_db'] == 24.0
    assert got['monitor_volume'] == 0 and got['record_bits'] == 24 and got['samplerate'] == 48000
    assert got['channel_mode'] == 'left' and got['share_output'] is True and 'unknown' not in got


@test
def gains():
    assert abs(core.db_to_gain(0) - 1.0) < 1e-9
    assert abs(core.db_to_gain(6) - 1.995) < 0.01
    assert core.monitor_gain(100) == 1.0 and core.monitor_gain(0) == 0.0
    assert core.monitor_gain(80, muted=True) == 0.0
    assert abs(core.monitor_gain(50) - 0.25) < 1e-9
    assert core.peak_dbfs(1.0) == 0.0 and core.peak_dbfs(0) == -120.0


@test
def channel_selection():
    b = np.array([[0.2, 0.6], [-0.4, 0.0]], dtype=np.float32)
    assert np.allclose(core.select_channels(b, 'mix')[:, 0], [0.4, -0.2])
    assert np.allclose(core.select_channels(b, 'left')[:, 0], [0.2, -0.4])
    assert np.allclose(core.select_channels(b, 'right')[:, 0], [0.6, 0.0])
    assert core.select_channels(b, 'stereo').shape == (2, 2)
    mono = b[:, :1]
    assert core.select_channels(mono, 'right').shape == (2, 1)          # mono mikrofonda sag yok: tek kanal
    assert core.select_channels(mono, 'stereo').shape == (2, 2)
    four = np.ones((3, 4), dtype=np.float32)
    assert core.select_channels(four, 'mix').shape == (3, 1)


@test
def fit_output_shapes():
    m = np.array([[0.5], [0.25]], dtype=np.float32)
    o = core.fit_output(m, 2)
    assert o.shape == (2, 2) and np.allclose(o[:, 1], [0.5, 0.25])
    s = np.array([[0.5, -0.5]], dtype=np.float32)
    assert np.allclose(core.fit_output(s, 1), [[0.0]])
    o4 = core.fit_output(s, 4)
    assert o4.shape == (1, 4) and np.allclose(o4[0], [0.5, -0.5, 0, 0])


@test
def pcm_conversion():
    b = np.array([[1.5], [-1.0], [0.0], [0.5]], dtype=np.float32)
    p16 = core.float_to_pcm(b, 16)
    assert len(p16) == 8
    assert np.frombuffer(p16, '<i2').tolist() == [32767, -32767, 0, 16383]
    p24 = core.float_to_pcm(b, 24)
    assert len(p24) == 12
    vals = [int.from_bytes(p24[i:i + 3], 'little', signed=True) for i in range(0, 12, 3)]
    assert vals == [8388607, -8388607, 0, 4194303]


@test
def ring_buffer_passthrough_and_underrun():
    r = core.RingBuffer(2, capacity=1000, target=100)
    data = np.arange(160, dtype=np.float32).reshape(80, 2)
    r.write(data)
    out = np.zeros((50, 2), dtype=np.float32)
    assert r.read(out) == 50 and np.allclose(out, data[:50])
    out = np.zeros((50, 2), dtype=np.float32)
    assert r.read(out) == 30 and np.allclose(out[:30], data[50:]) and not out[30:].any()
    assert r.underruns == 1


@test
def ring_buffer_wraps_and_bounds_latency():
    r = core.RingBuffer(1, capacity=256, target=64)
    out = np.zeros((48, 1), dtype=np.float32)
    total_written = 0
    for i in range(200):                       # giris cikistan biraz hizli (saat kaymasi)
        blk = np.full((50, 1), i, dtype=np.float32)
        r.write(blk); total_written += 50
        r.read(out)
        assert r.fill <= 64 * 2 + 50, r.fill    # gecikme birikmez
    assert r.dropped > 0
    # sarma dogrulugu: ardisik yazilan degerler sirayla okunur
    r2 = core.RingBuffer(1, capacity=10, target=4)
    got = []
    for k in range(20):
        r2.write(np.array([[float(k)]], dtype=np.float32))
        o = np.zeros((1, 1), dtype=np.float32)
        r2.read(o); got.append(float(o[0, 0]))
    assert got == [float(k) for k in range(20)]


@test
def wav_recorder_writes_valid_file():
    with tempfile.TemporaryDirectory() as td:
        for bits in (16, 24):
            p = pathlib.Path(td) / ('t%d.wav' % bits)
            rec = core.WavRecorder(p, 48000, 2, bits)
            for _ in range(10):
                rec.push(np.full((480, 2), 0.25, dtype=np.float32))
            rec.push(np.ones((10, 2), dtype=np.float32))
            rec.close()
            assert rec.error is None and rec.frames == 4810 and rec.clipped == 20
            with wave.open(str(p)) as w:
                assert w.getnchannels() == 2 and w.getsampwidth() == bits // 8
                assert w.getframerate() == 48000 and w.getnframes() == 4810
            assert abs(rec.seconds - 4810 / 48000) < 1e-9


@test
def device_warnings():
    assert core.is_bluetooth_name('Kulaklık (WILLEN Hands-Free)')
    assert core.is_bluetooth_name('HUAWEI FreeClip')
    assert not core.is_bluetooth_name('Mikrofon (Realtek(R) Audio)')
    assert core.is_speaker_name('Hoparlör (Realtek(R) Audio)')
    assert not core.is_speaker_name('Kulaklık (Realtek(R) Audio)')
    w = core.warnings_for('Mikrofon (Realtek(R) Audio)', 'Hoparlör (Realtek(R) Audio)')
    assert len(w) == 1 and 'geri besleme' in w[0]
    assert len(core.warnings_for('Mikrofon (Realtek(R) Audio)', 'JBL TUNE500BT Hands-Free')) == 1
    assert core.warnings_for('Mikrofon (Realtek(R) Audio)', 'Kulaklık (Realtek(R) Audio)') == []


@test
def headphone_detection():
    assert core.is_headphone_name('Kulaklık (Realtek(R) Audio)') and core.is_headphone_name('Headphones (USB Audio)')
    assert not core.is_headphone_name('Kulaklık (WILLEN Hands-Free)')          # Bluetooth: otomatik gecilmez
    assert not core.is_headphone_name('NVIDIA High Definition Audio (DELL U2720Q)')
    before = ['Hoparlör (Realtek(R) Audio)']
    assert core.pick_new_headphone(before, before + ['Kulaklık (Realtek(R) Audio)']) == 'Kulaklık (Realtek(R) Audio)'
    assert core.pick_new_headphone(before, before + ['DELL U2720Q (NVIDIA High Definition Audio)']) is None
    assert core.pick_new_headphone(before, before) is None


@test
def device_name_matching():
    names = ['Mikrofon (Realtek(R) Audio)', 'Stereo Mix (Realtek(R) Audio)']
    assert core.match_device_name('Mikrofon (Realtek(R) Audio)', names) == 0
    mme = ['Mikrofon (Realtek(R) Audio)'[:31], 'Stereo Mix (Realtek(R) Audio)'[:31]]
    assert core.match_device_name('Stereo Mix (Realtek(R) Audio)', mme) == 1
    assert core.match_device_name('', names) is None
    assert core.match_device_name('Yok', names) is None


@test
def record_dir_and_name():
    assert core.resolve_record_dir('').name == 'AGFO Kayitlar'
    assert str(core.resolve_record_dir('/tmp/x')) == '/tmp/x' or os.name == 'nt'
    import datetime
    assert core.recording_name(datetime.datetime(2026, 11, 1, 18, 5, 9)) == 'Kayit_20261101_180509.wav'


print('OK - %d test gecti: %s' % (len(PASSED), ', '.join(PASSED)))
