"""Repair/create a PC-local Python build venv for AGFO BackupSync.

Only Python's standard library is used. Designed to be called by build_windows.ps1.
The CLI accepts ONLY the expected %LOCALAPPDATA% build venv, to prevent a bad
path or a redirected cloud folder from being deleted accidentally.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

CHECK_CODE = (
    'import json,sys;'
    'print(json.dumps({' 
    '"prefix":sys.prefix,"base_prefix":sys.base_prefix,'
    '"executable":sys.executable,"version":list(sys.version_info[:2])}))'
)


def normalized(path: str | Path) -> str:
    return os.path.normcase(os.path.realpath(os.fspath(path)))


def venv_python(folder: Path) -> Path:
    if os.name == 'nt':
        return folder / 'Scripts' / 'python.exe'
    return folder / 'bin' / 'python'


def run_command(arguments: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(arguments, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, errors='replace', timeout=timeout)


def output_detail(result: subprocess.CompletedProcess) -> str:
    result_text = '\n'.join(part.strip() for part in
                            (result.stdout, result.stderr) if part and part.strip())
    return result_text[-5000:] if result_text else '(komut cikti uretmedi)'


def verify_venv(folder: Path, base_prefix: str, version: tuple[int, int]) -> tuple[bool, str]:
    executable = venv_python(folder)
    if not (folder / 'pyvenv.cfg').is_file() or not executable.is_file():
        return False, 'pyvenv.cfg veya sanal ortam Python calistiricisi bulunamadi.'
    try:
        result = run_command([str(executable), '-c', CHECK_CODE], timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, 'Sanal ortam Python baslatilamadi: ' + str(exc)
    if result.returncode:
        return False, 'Sanal ortam Python hata verdi: ' + output_detail(result)
    try:
        line = result.stdout.strip().splitlines()[-1]
        info = json.loads(line)
    except (IndexError, ValueError, TypeError):
        return False, 'Sanal ortam Python beklenen tanilama bilgisini dondurmedi: ' + output_detail(result)
    if normalized(info.get('prefix', '')) != normalized(folder):
        return False, f"Yanlis ortam: prefix={info.get('prefix')!r}, beklenen={str(folder)!r}"
    if normalized(info.get('base_prefix', '')) != normalized(base_prefix):
        return False, f"Temel Python baska bir kuruluma ait: {info.get('base_prefix')!r}; beklenen={base_prefix!r}"
    if normalized(info.get('executable', '')) != normalized(executable):
        return False, f"Sanal ortam python.exe yolu farkli: {info.get('executable')!r}"
    if tuple(info.get('version', ())) != version:
        return False, f"Python surumu uyusmuyor: {info.get('version')!r}, beklenen={version!r}"
    return True, 'Python yorumlayicisi dogru sanal ortamda calisiyor.'


def pip_available(executable: Path) -> tuple[bool, str]:
    try:
        response = run_command([str(executable), '-m', 'pip', '--version'], timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return response.returncode == 0, output_detail(response)


def prepare_build_environment(folder: Path, *, interpreter: str | None = None,
                              printer=print) -> Path:
    """Create or repair environment; return venv interpreter path.

    Existing venvs are NOT deleted unless the runtime check actually fails.
    No global Python packages or settings are changed.
    """
    folder = Path(folder).absolute()
    current_python = interpreter or sys.executable
    selected = run_command([str(current_python), '-c', CHECK_CODE], timeout=30)
    if selected.returncode:
        raise RuntimeError('Secilen Python calismadi: ' + output_detail(selected))
    try:
        info = json.loads(selected.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError) as exc:
        raise RuntimeError('Temel Python tanilama yaniti gecersiz.') from exc
    base_prefix = info['base_prefix']
    version = tuple(info['version'])
    printer('Secilen temel Python: ' + str(current_python))
    printer('Python surumu: ' + '.'.join(str(n) for n in version))
    printer('Sanal ortam konumu: ' + str(folder))
    if folder.is_symlink():
        raise RuntimeError('Sanal ortam klasoru sembolik bag; guvenlik icin silinmiyor.')
    valid, message = verify_venv(folder, base_prefix, version)
    printer('Mevcut ortam kontrolu: ' + message)
    if not valid:
        if folder.is_dir():
            printer('Eski/uyumsuz ortami bu bilgisayarda yeniden olusturuyorum...')
            shutil.rmtree(folder)
        elif folder.exists():
            raise RuntimeError('Sanal ortam konumunda klasor yerine dosya var: ' + str(folder))
        folder.parent.mkdir(parents=True, exist_ok=True)
        creation = run_command([str(current_python), '-m', 'venv', str(folder)], timeout=180)
        if creation.returncode:
            raise RuntimeError('Python -m venv basarisiz (kod ' + str(creation.returncode) + '):\n' + output_detail(creation))
        valid, message = verify_venv(folder, base_prefix, version)
        printer('Yeni ortam kontrolu: ' + message)
        if not valid:
            raise RuntimeError('Yeni ortam Python calismiyor: ' + message)
    executable = venv_python(folder)
    pip_ok, pip_detail = pip_available(executable)
    if not pip_ok:
        printer('Sanal ortamda pip bulunamadi; ensurepip ile yerel onarim deneniyor.')
        try:
            repair = run_command([str(executable), '-m', 'ensurepip', '--upgrade'], timeout=180)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError('ensurepip baslatilamadi: ' + str(exc)) from exc
        if repair.returncode:
            raise RuntimeError('ensurepip ile pip kurulumu basarisiz:\n' + output_detail(repair)
                               + '\nIlk kontrol: ' + pip_detail)
        pip_ok, pip_detail = pip_available(executable)
    if not pip_ok:
        raise RuntimeError('Sanal ortam Python calisiyor ama pip kullanilamiyor: ' + pip_detail)
    printer('Python sanal ortam BASARILI. ' + pip_detail.splitlines()[-1])
    return executable


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--venv', required=True)
    args = parser.parse_args()
    local = os.environ.get('LOCALAPPDATA')
    if not local:
        print('HATA: LOCALAPPDATA bulunamadi; kullaniciya ozel derleme alani olusturulamiyor.')
        return 2
    expected = Path(local) / 'AGFO-BackupSync' / 'build-cache' / 'venv'
    # Refuse dangerous unexpected folders; no deletion outside our dedicated cache.
    if normalized(args.venv) != normalized(expected):
        print('HATA: Sanal ortam klasoru guvenlik nedeniyle reddedildi.')
        print('Beklenen: ' + str(expected))
        print('Gelen:    ' + args.venv)
        return 2
    try:
        prepare_build_environment(expected)
        return 0
    except Exception as exc:
        print('HATA: ' + str(exc))
        print('Temel Python: ' + sys.executable)
        print('Sistem Python surumu: ' + sys.version.replace('\n', ' '))
        return 1


if __name__ == '__main__':
    sys.exit(main())
