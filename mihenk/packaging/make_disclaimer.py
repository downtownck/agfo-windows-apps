# -*- coding: utf-8 -*-
"""DISCLAIMER.txt'i mihenk_legal.py'den uretir.

Metin tek yerde dursun diye: kurulum betigi bu dosyayi yaziyor, uygulama
ayni metni kendi icinden okuyor. tests/test_i18n.py ikisinin ayni oldugunu
dogruluyor, boylece biri degisip oteki eskimiyor.

    python packaging/make_disclaimer.py
"""
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
WIDTH = 78


def wrap(text: str) -> str:
    import textwrap
    out = []
    for block in text.split('\n\n'):
        out.append('\n'.join(textwrap.wrap(block, WIDTH)))
    return '\n\n'.join(out)


def render(lang: str) -> str:
    """Metni ayri bir surecte alir: dil ice aktarma aninda sabitleniyor."""
    script = ('import sys; sys.path.insert(0, %r)\n'
              'import mihenk_legal as legal\n'
              'sys.stdout.write(legal.heading() + "\\n\\n" + legal.text())\n' % str(ROOT))
    # PYTHONIOENCODING: Windows'ta alt surecin stdout'u cp1252'ye duser ve
    # metindeki Turkce harfler yazilamaz.
    env = dict(os.environ, MIHENK_LANG=lang, MIHENK_DATA_DIR=tempfile.mkdtemp(),
               PYTHONIOENCODING='utf-8')
    done = subprocess.run([sys.executable, '-I', '-c', script], capture_output=True,
                          text=True, encoding='utf-8', env=env)
    if done.returncode:
        raise SystemExit(done.stderr)
    return done.stdout


def build() -> str:
    parts = ['AGFO Mihenk v%s' % version(), '=' * WIDTH, '']
    for lang in ('tr', 'en'):
        head, _, body = render(lang).partition('\n\n')
        parts += [head.upper(), '-' * len(head), '', wrap(body), '', '=' * WIDTH, '']
    return '\n'.join(parts).rstrip() + '\n'


def version() -> str:
    for line in (ROOT / 'mihenk_core.py').read_text(encoding='utf-8').splitlines():
        if line.startswith('VERSION'):
            return line.split('=')[1].strip().strip("'\"")
    return '?'


if __name__ == '__main__':
    target = ROOT / 'DISCLAIMER.txt'
    target.write_text(build(), encoding='utf-8')
    print('yazildi:', target)
