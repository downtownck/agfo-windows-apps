# -*- coding: utf-8 -*-
"""Hazir calisma ortamini derler (Windows'ta, GitHub Actions): Python'suz kurulum paketi.

1) Uygulama kaynaklarindaki import'lari tarar, yerel moduller disindakileri runtime_deps.py'ye yazar
   (PyInstaller bunlari gomer; uygulama modulleri GOMULMEZ, exe yanindaki dosyalardan yuklenir).
2) PyInstaller --onedir ile 'AGFO System Care.exe' + _internal\\ uretir.
3) Kaynak dosyalari (app.pyw, *.py, care_tasks.ps1, assets, belgeler, kurulum betikleri) exe'nin yanina kopyalar.
Kullanim: python packaging/build_runtime.py <system-care klasoru> <cikti klasoru>
"""
import ast
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(sys.argv[1]).resolve()
OUT = pathlib.Path(sys.argv[2]).resolve()
NAME = 'AGFO System Care'
EXTRA = ['ttkbootstrap', 'PIL', 'PIL.Image', 'PIL.ImageTk', 'paramiko', 'cryptography', 'bcrypt', 'nacl']


def scan_imports():
    local = {p.stem for p in ROOT.glob('*.py')} | {'app'}
    found = set()
    for p in list(ROOT.glob('*.py')) + [ROOT / 'app.pyw']:
        tree = ast.parse(p.read_text(encoding='utf-8'))
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                found |= {a.name for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
                found.add(n.module)
    return sorted(m for m in found if m.split('.')[0] not in local)


def main():
    work = OUT.parent / 'runtime-build'
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    mods = scan_imports() + EXTRA
    deps = ['# Derleme aninda uretildi (build_runtime.py). Elle duzenlemeyin.']
    for m in mods:
        deps.append('try:\n    import %s  # noqa: F401\nexcept Exception:  # noqa: BLE001\n    pass' % m)
    (work / 'runtime_deps.py').write_text('\n'.join(deps) + '\n', encoding='utf-8')
    shutil.copy2(ROOT / 'packaging' / 'runtime_launcher.py', work / 'runtime_launcher.py')
    local = sorted({p.stem for p in ROOT.glob('*.py')})
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed', '--name', NAME,
           '--icon', str(ROOT / 'assets' / 'agfo.ico'), '--distpath', str(OUT), '--workpath', str(work / 'build'), '--specpath', str(work),
           '--collect-all', 'ttkbootstrap', '--collect-submodules', 'paramiko', '--paths', str(work)]
    for m in local:                                                 # uygulama modulleri exe'ye gomulmez (guncellenebilir kalir)
        cmd += ['--exclude-module', m]
    cmd.append(str(work / 'runtime_launcher.py'))
    print(' '.join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=str(work))
    dest = OUT / NAME
    for p in sorted(ROOT.iterdir()):
        if p.is_file() and (p.suffix in ('.py', '.pyw', '.ps1', '.md', '.txt', '.json', '.cmd')):
            shutil.copy2(p, dest / p.name)
    shutil.copytree(ROOT / 'assets', dest / 'assets', dirs_exist_ok=True)
    shutil.copytree(ROOT / 'packaging', dest / 'packaging', dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
    (dest / 'RUNTIME').write_text('python=%d.%d.%d\nmods=%s\n' % (sys.version_info[:3] + (' '.join(EXTRA),)), encoding='utf-8')
    print('Hazir calisma ortami:', dest, flush=True)


if __name__ == '__main__':
    main()
