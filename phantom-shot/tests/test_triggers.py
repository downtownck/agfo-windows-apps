"""AGFO Phantom Shot 1.3.0 - tetik/kanca mantigi (sahte pynput ile; Windows gerektirmez).

    python -I tests/test_triggers.py <phantom-shot klasoru>

Dogrulanan: kanca geri cagrisi yakalama yapmaz, yalnizca kuyruga yazar; basili tutulan tus tek goruntu;
baska tuslar etkilenmez; tetik tusu istenirse diger programlara iletilmez; PrintScreen yalnizca birakmada.
"""
import importlib.machinery
import importlib.util
import pathlib
import sys
import types

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))

try:
    import tkinter  # noqa: F401
except ImportError:
    print('SKIP - tkinter yok')
    raise SystemExit(0)


class Suppressed(Exception):
    pass


class FakeKbListener:
    def __init__(self, win32_event_filter=None, on_press=None, on_release=None):
        self.filter = win32_event_filter
        self.started = False

    def start(self):
        self.started = True

    def is_alive(self):
        return self.started

    def stop(self):
        self.started = False

    def suppress_event(self):
        raise Suppressed()


class FakeMsListener(FakeKbListener):
    def __init__(self, on_click=None):
        super().__init__()
        self.on_click = on_click


keyboard = types.SimpleNamespace(Listener=FakeKbListener, Key=types.SimpleNamespace())
mouse = types.SimpleNamespace(Listener=FakeMsListener, Button=types.SimpleNamespace(middle='MID', x1='X1', x2='X2', right='R'))
pynput = types.ModuleType('pynput')
pynput.keyboard, pynput.mouse = keyboard, mouse
sys.modules['pynput'] = pynput
sys.modules['pynput.keyboard'] = keyboard
sys.modules['pynput.mouse'] = mouse

loader = importlib.machinery.SourceFileLoader('phantom_app', str(ROOT / 'app.pyw'))
spec = importlib.util.spec_from_loader('phantom_app', loader)
app = importlib.util.module_from_spec(spec)
loader.exec_module(app)
app.IS_WIN = True                                    # Windows kanca yolunu sina
core = app.core

PASSED = []


def test(fn):
    fn()
    PASSED.append(fn.__name__)
    return fn


class Data:
    def __init__(self, vk):
        self.vkCode = vk


def make(cfg):
    fired = []
    t = app.Triggers(dict(core.DEFAULT_CONFIG, **cfg), lambda: fired.append(1))
    t.start()
    return t, fired


def send(t, msg, vk):
    try:
        return ('pass', t.kb.filter(msg, Data(vk)))
    except Suppressed:
        return ('suppressed', None)


@test
def other_keys_untouched():
    t, fired = make({'key': 'f9'})
    assert send(t, core.WM_KEYDOWN, 0x41) == ('pass', True)
    assert fired == []


@test
def hold_key_one_shot_and_blocked():
    t, fired = make({'key': 'f9', 'block_key': True})
    assert send(t, core.WM_KEYDOWN, 0x78)[0] == 'suppressed'
    for _ in range(20):                                  # otomatik tekrar
        send(t, core.WM_KEYDOWN, 0x78)
    send(t, core.WM_KEYUP, 0x78)
    assert len(fired) == 1, fired


@test
def not_blocked_when_disabled():
    t, fired = make({'key': 'f9', 'block_key': False, 'min_interval_ms': 0})
    assert send(t, core.WM_KEYDOWN, 0x78) == ('pass', False)   # sisteme gider, pynput geri cagrisi yok
    send(t, core.WM_KEYUP, 0x78)
    send(t, core.WM_SYSKEYDOWN, 0x78)                          # Alt basiliyken de calisir
    assert len(fired) == 2


@test
def print_screen_release_only():
    t, fired = make({'key': 'print_screen', 'min_interval_ms': 0})
    send(t, core.WM_KEYUP, core.VK_SNAPSHOT)                   # Windows yalnizca birakma bildirdi
    assert len(fired) == 1
    send(t, core.WM_KEYDOWN, core.VK_SNAPSHOT)
    send(t, core.WM_KEYUP, core.VK_SNAPSHOT)                   # normal basis/birakma: tek goruntu
    assert len(fired) == 2


@test
def letter_trigger_by_vk():
    t, fired = make({'key': 'q', 'min_interval_ms': 0})
    send(t, core.WM_KEYDOWN, 0x51)
    assert len(fired) == 1


@test
def mouse_button_debounced():
    t, fired = make({'key': '', 'mouse_button': 'middle', 'min_interval_ms': 0})
    t.ms.on_click(0, 0, 'MID', True)
    t.ms.on_click(0, 0, 'MID', True)                           # birakmadan ikinci basis bildirimi
    t.ms.on_click(0, 0, 'MID', False)
    t.ms.on_click(0, 0, 'X1', True)                            # baska tus
    assert len(fired) == 1


@test
def capturer_queue_is_nonblocking():
    import time
    cap = app.Capturer()
    t0 = time.perf_counter()
    for _ in range(50):
        cap.request({'monitor': 0})
    assert time.perf_counter() - t0 < 0.05                     # kanca hic beklemez
    cap.close()


print('OK - %d test gecti: %s' % (len(PASSED), ', '.join(PASSED)))
