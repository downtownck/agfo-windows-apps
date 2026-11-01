"""AGFO Mic Monitor - yanki / reverb testleri (numpy; ses aygiti gerekmez).

    python -I tests/test_fx.py <mic-monitor klasoru>
"""
import pathlib
import sys
import time

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))
import numpy as np  # noqa: E402
import mic_fx as fx  # noqa: E402

SR = 48000
PASSED = []


def test(fn):
    fn()
    PASSED.append(fn.__name__)
    return fn


def run(chain, x, blk):
    return np.concatenate([chain.process(x[i:i + blk]) for i in range(0, len(x), blk)])


def impulse(sec):
    x = np.zeros((int(SR * sec), 2), dtype=np.float32)
    x[0] = 1.0
    return x


ALL = {'fx_echo_on': True, 'fx_echo_ms': 250, 'fx_echo_fb': 50, 'fx_echo_mix': 100,
       'fx_rev_on': True, 'fx_rev_type': 'Salon', 'fx_rev_mix': 100}


@test
def no_added_latency():
    # efekt yalniz islak ses uretir; ilk ornekte sifir -> kuru ses + islak = kuru ses (gecikme yok)
    y = run(fx.FxChain(SR).configure(ALL), impulse(0.2), 480)
    assert np.all(y[0] == 0.0)
    pre = fx.REVERB_PRESETS['Salon']['predelay']
    first = int(np.argmax(np.abs(y[:, 0]) > 1e-7))
    assert first >= int(pre * SR / 1000) - 1, first        # ilk yansima on gecikmeden once gelmez


@test
def echo_repeats_at_delay_and_decays():
    c = fx.FxChain(SR).configure({'fx_echo_on': True, 'fx_echo_ms': 250, 'fx_echo_fb': 50, 'fx_echo_mix': 100, 'fx_echo_tone': 100})
    y = run(c, impulse(1.1), 480)[:, 0]
    d = int(0.25 * SR)
    assert not y[:d].any()
    assert abs(y[d] - 1.0) < 1e-6 and abs(y[2 * d] - 0.5) < 1e-6 and abs(y[3 * d] - 0.25) < 1e-6


@test
def block_size_independent():
    x = (np.random.RandomState(1).randn(SR, 2) * 0.2).astype(np.float32)
    a = run(fx.FxChain(SR).configure(ALL), x, 128)
    b = run(fx.FxChain(SR).configure(ALL), x, 1920)     # en kisa hattan uzun blok: parcalanir
    c = run(fx.FxChain(SR).configure(ALL), x, 333)
    assert np.allclose(a, b, atol=1e-5) and np.allclose(a, c, atol=1e-5)


@test
def reverb_presets_decay_stereo_and_rt60():
    for kind, p in fx.REVERB_PRESETS.items():
        c = fx.FxChain(SR).configure({'fx_rev_on': True, 'fx_rev_type': kind, 'fx_rev_mix': 100})
        y = run(c, impulse(p['time'] * 2.5 + 0.5), 480)
        e = (y ** 2).sum(axis=1)
        sch = np.cumsum(e[::-1])[::-1]
        sch /= sch[0]
        db = 10 * np.log10(sch + 1e-30)
        t5, t35 = int(np.argmax(db < -5)), int(np.argmax(db < -35))
        rt = (t35 - t5) / SR * 2
        assert 0.7 * p['time'] <= rt <= 1.35 * p['time'], (kind, rt)
        assert abs(np.corrcoef(y[:SR // 2, 0], y[:SR // 2, 1])[0, 1]) < 0.3, kind     # genis stereo
        assert np.abs(y[-SR // 10:]).max() < 1e-3, kind                                # sonumlenir


@test
def stable_at_extreme_settings():
    c = fx.FxChain(SR).configure({'fx_echo_on': True, 'fx_echo_ms': 60, 'fx_echo_fb': 85, 'fx_echo_mix': 100,
                                  'fx_echo_tone': 100, 'fx_rev_on': True, 'fx_rev_type': 'Katedral',
                                  'fx_rev_time': 10, 'fx_rev_tone': 100, 'fx_rev_mix': 100})
    x = (np.random.RandomState(2).randn(SR * 10, 2) * 0.3).astype(np.float32)
    y = run(c, x, 480)
    assert np.isfinite(y).all() and np.abs(y[-SR:]).max() < 20.0
    z = run(c, np.zeros((SR * 30, 2), dtype=np.float32), 480)        # girdi kesilince kuyruk soner
    assert np.abs(z[-SR:]).max() < 1e-2


@test
def live_parameter_changes_keep_state():
    c = fx.FxChain(SR).configure(ALL)
    run(c, impulse(0.1), 480)
    rev = c.reverb
    c.configure(dict(ALL, fx_rev_time=3.0, fx_rev_mix=50))
    assert c.reverb is rev and abs(rev.rt60 - 3.0) < 1e-9          # ayni oda: hatlar korunur (kesinti yok)
    c.configure(dict(ALL, fx_rev_type='Oda'))
    assert c.reverb is not rev and c.reverb.kind == 'Oda'
    c.configure({'fx_echo_on': False, 'fx_rev_on': False})
    assert not c.active and not c.process(impulse(0.01)).any()


@test
def fast_enough_for_small_buffers():
    c = fx.FxChain(SR).configure(ALL)
    b = (np.random.RandomState(3).randn(128, 2) * 0.1).astype(np.float32)
    for _ in range(50):
        c.process(b)
    t = time.perf_counter()
    n = 500
    for _ in range(n):
        c.process(b)
    per = (time.perf_counter() - t) / n
    assert per < 0.25 * 128 / SR, per * 1000                     # 2,7 ms blokta %25'ten az islemci


print('OK - %d test gecti: %s' % (len(PASSED), ', '.join(PASSED)))
