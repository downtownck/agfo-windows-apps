# -*- coding: utf-8 -*-
"""AGFO Mihenk - guncelleme modulu testi.

    python -I tests/test_update.py <mihenk klasoru>
"""
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else '.')
os.environ['MIHENK_DATA_DIR'] = tempfile.mkdtemp()

import mihenk_core as core  # noqa: E402
import mihenk_update as u  # noqa: E402

d = pathlib.Path(tempfile.mkdtemp())
src, tgt = d / 'new.exe', d / 'sub' / 'app.exe'
src.write_bytes(b'NEW')
u.replace_target(src, tgt, sleep=lambda s: None)
assert tgt.read_bytes() == b'NEW' and not (tgt.parent / 'app.exe.new').exists()

tgt.write_bytes(b'OLD')
u.replace_target(src, tgt, sleep=lambda s: None)
assert tgt.read_bytes() == b'NEW'

calls = []


class P:                       # sahte Popen
    def __init__(self, cmd, **kw):
        calls.append(cmd)


u.apply_update(src, popen=P, pid=123, target=tgt)
assert calls[0][1:5] == ['--apply-update', str(tgt), '--wait-pid', '123'], calls
assert u.asset_pattern() == u.GH_ASSET
assert u.GH_PREFIX == 'mihenk-v' and u.EXE_NAME == 'AGFO-Mihenk.exe'
assert u.USER_AGENT.endswith(core.VERSION)

# PyInstaller ic degiskenleri alt surece gecmemeli.
env = u.scrub_env({'_PYI_ONEFILE': '1', '_MEIPASS2': 'x', 'PATH': '/bin'})
assert '_PYI_ONEFILE' not in env and '_MEIPASS2' not in env
assert env['PATH'] == '/bin' and env['PYINSTALLER_RESET_ENVIRONMENT'] == '1'

# Guvensiz yol tasiyan ZIP acilmamali.
import zipfile  # noqa: E402
bad = d / 'bad.zip'
with zipfile.ZipFile(bad, 'w') as z:
    z.writestr('../kacti.txt', 'x')
try:
    u.extract(bad)
    raise AssertionError('guvensiz yol kabul edildi')
except Exception as exc:
    assert 'güvensiz' in str(exc).lower() or 'Derle-ve-Kur' in str(exc), exc

print('MIHENK UPDATE OK')
