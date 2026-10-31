"""Build reproducible-source Windows release ZIP and SHA-256 file.

Run from smart-organizer directory after PyInstaller creates dist/AGFO-Smart-Organizer.exe.
"""
from __future__ import annotations
import hashlib
import re
import sys
import zipfile
from pathlib import Path

FILES = ('organizer_core.py', 'smart_organizer.pyw', 'update_checker.py',
         'GUNCELLE-KUR.ps1', 'Baslat.bat', 'EXE-OLUSTUR.bat',
         'KUR-GEMMA.cmd', 'AGFO-Ollama-Gemma-Kur.ps1',
         'README.md', 'GEMMA-KURULUM.md', 'LICENSE')


def build(root: Path, version: str, include_exe: bool = True) -> Path:
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Version must be X.Y.Z')
    source = (root / 'smart_organizer.pyw').read_text(encoding='utf-8')
    if f"VERSION = '{version}'" not in source:
        raise ValueError('Tag version and source VERSION differ')
    paths = {name: root / name for name in FILES}
    if include_exe:
        paths['AGFO-Smart-Organizer.exe'] = root / 'dist' / 'AGFO-Smart-Organizer.exe'
    for name, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(f'Missing release asset: {name}')
    target_dir = root / 'dist' / 'release'
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f'AGFO-Smart-Organizer-v{version}.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=8) as z:
        for name, path in paths.items():
            z.write(path, name)
    sha = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_name(target.name + '.sha256').write_text(sha + '  ' + target.name + '\n', encoding='ascii')
    return target


if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    ver = sys.argv[1] if len(sys.argv) > 1 else '1.1.1'
    print(build(root, ver))
