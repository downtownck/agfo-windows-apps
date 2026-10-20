"""AGFO Phantom Shot - phantom_update saf fonksiyon testleri (Windows/frozen gerektirmez).

    python -I tests/test_update.py <phantom-shot klasoru>
"""
import hashlib
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))
import phantom_update as u  # noqa: E402

PASSED = []


def test(fn):
    fn()
    PASSED.append(fn.__name__)
    return fn


@test
def constants_sane():
    assert u.GH_PREFIX == 'phantom-shot-v'
    assert u.EXE_NAME == 'AGFO-Phantom-Shot.exe'
    assert u.GH_ASSET.replace('\\', '') == 'AGFO-Phantom-Shot.exe'
    assert str(u.installed_exe()).endswith(u.EXE_NAME)
    assert u.install_dir().name == 'AGFO-Phantom-Shot'


@test
def scrub_env_drops_pyinstaller_vars():
    env = {'PATH': '/x', '_PYI_SPLASH': '1', '_MEIPASS2': 'c:/t', 'FOO': 'bar'}
    out = u.scrub_env(env)
    assert '_PYI_SPLASH' not in out and '_MEIPASS2' not in out
    assert out['PATH'] == '/x' and out['FOO'] == 'bar'
    assert out['PYINSTALLER_RESET_ENVIRONMENT'] == '1'


@test
def package_ready_logic():
    assert not u.package_ready({}, {})
    assert not u.package_ready({}, {'url': 'x'})                      # ozet yok
    assert u.package_ready({}, {'url': 'x', 'sha256': 'a' * 64})      # GitHub ozeti var
    rel = {'assets': [{'name': 'SHA256SUMS.txt', 'url': 'u'}]}
    assert u.package_ready(rel, {'url': 'x'})                         # SHA256SUMS var


@test
def file_sha256_matches():
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / 'f.bin'
        p.write_bytes(b'phantom')
        assert u.file_sha256(p) == hashlib.sha256(b'phantom').hexdigest()


@test
def replace_target_copies_over():
    with tempfile.TemporaryDirectory() as td:
        src = pathlib.Path(td) / 'new.exe'; src.write_bytes(b'YENI')
        dst = pathlib.Path(td) / 'app' / 'cur.exe'; dst.parent.mkdir(); dst.write_bytes(b'ESKI')
        u.replace_target(src, dst)
        assert dst.read_bytes() == b'YENI'
        assert not dst.with_name(dst.name + '.new').exists()   # gecici dosya birakilmaz


@test
def replace_target_retries_then_fails_cleanly():
    with tempfile.TemporaryDirectory() as td:
        src = pathlib.Path(td) / 'new.exe'; src.write_bytes(b'YENI')
        dst = pathlib.Path(td) / 'cur.exe'; dst.write_bytes(b'ESKI')
        calls = {'n': 0}

        def boom(*a):
            calls['n'] += 1
        import os as _os
        orig = _os.replace

        def always_fail(a, b):
            raise OSError('kilitli')
        _os.replace = always_fail
        try:
            u.replace_target(src, dst, attempts=3, delay=0, sleep=boom)
            assert False, 'hata bekleniyordu'
        except OSError as e:
            assert 'serbest' in str(e)
            assert calls['n'] == 3                 # her denemede bekledi
            assert not dst.with_name(dst.name + '.new').exists()
        finally:
            _os.replace = orig


def main():
    print('OK - %d test gecti: %s' % (len(PASSED), ', '.join(PASSED)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
