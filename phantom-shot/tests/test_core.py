"""AGFO Phantom Shot - phantom_core birim testleri (Windows/mss/pynput gerektirmez).

    python -I tests/test_core.py <phantom-shot klasoru>
"""
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))
import phantom_core as c  # noqa: E402

PASSED = []


def test(fn):
    fn()
    PASSED.append(fn.__name__)
    return fn


@test
def screenshot_name_format():
    n = c.screenshot_name('shot', 'png', now=1_700_000_000.123)
    assert n.startswith('shot_') and n.endswith('.png'), n
    assert c.screenshot_name('x', 'jpeg').endswith('.jpg')
    assert c.screenshot_name('x', 'webp').endswith('.png')   # desteklenmeyen -> png
    assert c.screenshot_name('', 'png').startswith('shot_')   # bos onek -> shot
    # ayni saniyede iki cagri milisaniye ile farklilasir (bicim denetimi)
    a = c.screenshot_name('s', 'png', now=1_700_000_000.001)
    b = c.screenshot_name('s', 'png', now=1_700_000_000.900)
    assert a != b, (a, b)


@test
def resolve_save_dir_rules():
    d = c.resolve_save_dir('')
    assert d and os.path.isabs(d), d
    assert c.resolve_save_dir('/tmp/x') == os.path.abspath('/tmp/x')


@test
def settings_roundtrip(tmp=None):
    with tempfile.TemporaryDirectory() as td:
        # SETTINGS_FILE'i gecici klasore yonlendir
        orig = c.SETTINGS_FILE
        c.SETTINGS_FILE = pathlib.Path(td) / 'config.json'
        try:
            base = c.load_settings()
            assert base == c.DEFAULT_CONFIG and base is not c.DEFAULT_CONFIG  # kopya
            base['key'] = 'f12'
            base['bilinmeyen'] = 'atilmali'
            assert c.save_settings(base)
            got = c.load_settings()
            assert got['key'] == 'f12'
            assert 'bilinmeyen' not in got          # yalnizca bilinen anahtarlar tutulur
            assert got['format'] == 'png'            # eksikler varsayilandan gelir
        finally:
            c.SETTINGS_FILE = orig


@test
def defaults_have_expected_keys():
    for k in ('save_dir', 'key', 'mouse_button', 'monitor', 'format', 'jpg_quality', 'autostart', 'minimize_to_tray', 'auto_update_check'):
        assert k in c.DEFAULT_CONFIG, k
    assert isinstance(c.VERSION, str) and c.VERSION.count('.') >= 2


def main():
    print('OK - %d test gecti: %s' % (len(PASSED), ', '.join(PASSED)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
