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


@test
def key_vk_layout_independent():
    assert c.key_vk('f9') == 0x78 and c.key_vk('F12') == 0x7B and c.key_vk('f24') == 0x87
    assert c.key_vk('a') == c.key_vk('A') == 0x41                 # buyuk/kucuk harf ayni tus
    assert c.key_vk('5') == 0x35
    assert c.key_vk('print_screen') == c.VK_SNAPSHOT
    assert c.key_vk('(yok)') is None and c.key_vk('') is None and c.key_vk('ğ') is None and c.key_vk('f25') is None


@test
def trigger_gate_debounce():
    t = [0.0]
    g = c.TriggerGate(250, clock=lambda: t[0])
    assert g.press() is True                       # ilk basis
    assert g.press() is False                      # basili tutma: otomatik tekrar yok sayilir
    t[0] = 1.0
    assert g.press() is False                      # hala basili
    assert g.release() is False
    t[0] = 1.1
    assert g.press() is True                       # yeni basis
    g.release()
    t[0] = 1.2
    assert g.press() is False                      # 250 ms icinde ikinci basis (titreme) tek sayilir
    g.release()
    t[0] = 2.0
    assert g.release(release_only=True) is True    # PrintScreen: yalnizca birakma gelirse tetik
    assert g.press() is False                      # hemen ardindan gelen basis cift sayilmaz (min aralik)


@test
def defaults_130():
    assert c.DEFAULT_CONFIG['autostart'] is True
    assert c.DEFAULT_CONFIG['block_key'] is True
    assert c.DEFAULT_CONFIG['start_with_windows'] is False


def main():
    print('OK - %d test gecti: %s' % (len(PASSED), ', '.join(PASSED)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
