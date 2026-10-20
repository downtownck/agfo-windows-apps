"""AGFO Phantom Shot - phantom_core birim testleri (Windows/mss/pynput gerektirmez).

    python -I tests/test_core.py <phantom-shot klasoru>
"""
import json
import os
import pathlib
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))
import phantom_core as c  # noqa: E402

PASSED = []


def test(fn):
    fn()
    PASSED.append(fn.__name__)
    return fn


# ---- saf yardimcilar -------------------------------------------------
@test
def version_tuple_basics():
    assert c.version_tuple('1.2.3') == (1, 2, 3)
    assert c.version_tuple('') == (0,)
    assert c.version_tuple('v10.0') == (10, 0)


@test
def screenshot_name_format():
    n = c.screenshot_name('shot', 'png', now=1_700_000_000.123)
    assert n.startswith('shot_') and n.endswith('.png'), n
    assert c.screenshot_name('x', 'jpeg').endswith('.jpg')
    assert c.screenshot_name('x', 'webp').endswith('.png')  # desteklenmeyen -> png
    assert c.screenshot_name('', 'png').startswith('shot_')  # bos onek -> shot


@test
def is_runtime_file_rules():
    for ok in ('app.pyw', 'phantom_core.py', 'agfo_github_update.py', 'README_TR.md', 'assets/agfo-phantom.ico'):
        assert c._is_runtime_file(ok), ok
    for no in ('config.json', 'MANIFEST.json', 'packaging/x.ps1', 'tests/test_core.py',
               'Baslat.cmd', '__pycache__/x.pyc', '../evil.py', 'assets'):
        assert not c._is_runtime_file(no), no


@test
def resolve_save_dir_nonempty():
    d = c.resolve_save_dir('')
    assert d and os.path.isabs(d), d
    assert c.resolve_save_dir('/tmp/x') == os.path.abspath('/tmp/x')


# ---- paket uretimi + denetimi ---------------------------------------
PKG_FILES = {
    'app.pyw': "# app\nprint('hi')\n",
    'phantom_core.py': "VERSION = '%s'\n# AGFO Phantom Shot\n",
    'agfo_github_update.py': "GITHUB_REPO = 'downtownck/agfo-windows-apps'\n",
    'README_TR.md': '# AGFO Phantom Shot\n',
    'assets/agfo-phantom.ico': 'ICO',
}


def _make_pkg(tmp, version, with_manifest=True, tamper=None):
    """<tmp>/pkg altinda calisma dosyalarini yazar, MANIFEST uretir, <tmp>/pkg.zip olusturur. ZIP yolunu doner."""
    root = pathlib.Path(tmp) / 'pkg'
    root.mkdir(parents=True, exist_ok=True)
    for rel, body in PKG_FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body % version if '%s' in body else body, encoding='utf-8')
    if with_manifest:
        man = c.build_manifest(root, version)
        (root / 'MANIFEST.json').write_text(json.dumps(man, ensure_ascii=False), encoding='utf-8')
    if tamper:
        (root / tamper).write_text('DEGISTIRILDI\n', encoding='utf-8')  # MANIFEST sonrasi degisiklik
    zp = pathlib.Path(tmp) / 'pkg.zip'
    with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob('*')):
            if p.is_file():
                z.write(p, 'phantom-shot/' + p.relative_to(root).as_posix())
    return str(zp)


@test
def inspect_accepts_valid_upgrade():
    with tempfile.TemporaryDirectory() as tmp:
        zp = _make_pkg(tmp, '2.0.0')
        info = c.inspect_update(zp, '1.0.0')
        assert info['ok'], info['errors']
        assert info['version'] == '2.0.0'
        assert info['manifest'] is True
        assert not info['downgrade'] and not info['same']
        assert set(c.UPDATE_REQUIRED) <= set(info['files'])


@test
def inspect_flags_downgrade_and_same():
    with tempfile.TemporaryDirectory() as tmp:
        assert c.inspect_update(_make_pkg(tmp, '0.9.0'), '1.0.0')['downgrade']
    with tempfile.TemporaryDirectory() as tmp:
        assert c.inspect_update(_make_pkg(tmp, '1.0.0'), '1.0.0')['same']


@test
def inspect_rejects_tampered_manifest():
    with tempfile.TemporaryDirectory() as tmp:
        zp = _make_pkg(tmp, '2.0.0', tamper='app.pyw')
        info = c.inspect_update(zp, '1.0.0')
        assert not info['ok'] and any('SHA-256' in e for e in info['errors']), info


@test
def inspect_rejects_other_app():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp) / 'pkg'; root.mkdir()
        (root / 'app.pyw').write_text('# app\n', encoding='utf-8')
        (root / 'phantom_core.py').write_text("VERSION = '2.0.0'\n# baska uygulama\n", encoding='utf-8')
        (root / 'agfo_github_update.py').write_text('x=1\n', encoding='utf-8')
        zp = pathlib.Path(tmp) / 'p.zip'
        with zipfile.ZipFile(zp, 'w') as z:
            for p in root.rglob('*'):
                z.write(p, p.relative_to(root).as_posix())
        info = c.inspect_update(str(zp), '1.0.0')
        assert not info['ok'], 'AGFO Phantom Shot imzasi olmayan paket kabul edildi'


# ---- uygulama + geri alma -------------------------------------------
@test
def apply_and_rollback_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        install = pathlib.Path(tmp) / 'install'
        stage = pathlib.Path(tmp) / 'stage'
        backups = pathlib.Path(tmp) / 'backups'
        install.mkdir(); (install / 'assets').mkdir()
        (install / 'app.pyw').write_text('ESKI app\n', encoding='utf-8')
        (install / 'phantom_core.py').write_text("VERSION = '1.0.0'\n# AGFO Phantom Shot\n", encoding='utf-8')
        (install / 'agfo_github_update.py').write_text('old=1\n', encoding='utf-8')
        stage.mkdir()
        (stage / 'app.pyw').write_text('YENI app\n', encoding='utf-8')
        (stage / 'phantom_core.py').write_text("VERSION = '2.0.0'\n# AGFO Phantom Shot\n", encoding='utf-8')
        (stage / 'agfo_github_update.py').write_text('new=1\n', encoding='utf-8')

        bdir = c.apply_update(str(stage), str(install), str(backups), '1.0.0', '2.0.0')
        assert (install / 'app.pyw').read_text() == 'YENI app\n'
        assert (install / 'VERSION').read_text() == '2.0.0'
        assert pathlib.Path(bdir).is_dir()
        assert c.list_backups(str(backups))[0]['version'] == '1.0.0'

        target, _ = c.rollback_update(bdir, str(install), '2.0.0')
        assert target == '1.0.0'
        assert (install / 'app.pyw').read_text() == 'ESKI app\n'
        assert (install / 'VERSION').read_text() == '1.0.0'


@test
def apply_auto_restores_on_failure():
    with tempfile.TemporaryDirectory() as tmp:
        install = pathlib.Path(tmp) / 'install'
        stage = pathlib.Path(tmp) / 'stage'
        backups = pathlib.Path(tmp) / 'backups'
        install.mkdir()
        (install / 'app.pyw').write_text('ESKI\n', encoding='utf-8')
        (install / 'phantom_core.py').write_text("VERSION = '1.0.0'\n", encoding='utf-8')
        stage.mkdir()
        (stage / 'app.pyw').write_text('YENI\n', encoding='utf-8')
        (stage / 'phantom_core.py').write_text("VERSION = '2.0.0'\n", encoding='utf-8')
        try:
            c.apply_update(str(stage), str(install), str(backups), '1.0.0', '2.0.0', fail_after=1)
            assert False, 'hata bekleniyordu'
        except OSError:
            pass
        # yapay hata sonrasi eski surum geri gelmis olmali
        assert (install / 'app.pyw').read_text() == 'ESKI\n', 'otomatik geri alma calismadi'


def main():
    print('OK - %d test gecti: %s' % (len(PASSED), ', '.join(PASSED)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
