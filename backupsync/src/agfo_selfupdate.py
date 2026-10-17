"""AGFO BackupSync - GitHub'dan tek tik guncelleme (tepsi uygulamasi tarafindan kullanilir).

Akis: GitHub Releases'te 'backupsync-v*' etiketli en yeni surum denetlenir -> AGFO-BackupSync-Setup.exe
indirilir ve GitHub SHA-256 ozetiyle (veya surumdeki SHA256SUMS.txt) dogrulanir -> kurulum programi
'--update' sessiz kipinde yonetici onayiyla baslatilir, tepsi uygulamasi dosya kilidini birakmak icin kapanir.
Kurulum programi bitince uygulamayi normal kullanici yetkisiyle yeniden acar.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

import agfo_github_update as ghu
from agfo_installer import VERSION, INSTALL_DIR, APP_EXE

GH_PREFIX = 'backupsync-v'
GH_ASSET = r'AGFO-BackupSync-Setup\.exe'
UPDATE_ARGS = '--update'
USER_AGENT = 'AGFO-BackupSync/' + VERSION


def data_dir() -> Path:
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'AGFO-BackupSync'


def state_path() -> Path:
    return data_dir() / 'updates' / 'github-update.json'


def installed_mode(executable: str | None = None, frozen: bool | None = None) -> bool:
    """Yalnizca kurulu (C:\\agfo-backutil) ve derlenmis tepsi uygulamasi kendini gunceller."""
    frozen = getattr(sys, 'frozen', False) if frozen is None else frozen
    exe = Path(executable or sys.executable)
    try:
        return bool(frozen) and exe.resolve().parent == INSTALL_DIR.resolve() and exe.name.lower() == APP_EXE.lower()
    except OSError:
        return False


def check(force: bool = False, releases=None, now=None) -> dict:
    return ghu.check_for_update(GH_PREFIX, VERSION, state_path(), GH_ASSET, force=force, releases=releases,
                                user_agent=USER_AGENT, now=now)


def download_setup(result: dict, progress=None, should_stop=None) -> Path:
    rel, asset = result['release'], result['asset']
    sha = ghu.expected_sha256(rel, asset, user_agent=USER_AGENT)
    dest = data_dir() / 'updates' / ('AGFO-BackupSync-Setup-%s.exe' % result['version'])
    ghu.download_asset(asset, dest, sha, progress, should_stop, user_agent=USER_AGENT)
    return dest


def launch_setup(setup: Path, shell_execute=None) -> None:
    """Kurulum programini yonetici onayiyla '--update' kipinde baslatir. Hata halinde OSError."""
    if shell_execute is None:
        if sys.platform != 'win32':
            raise OSError('Yalnizca Windows')
        import ctypes
        shell_execute = ctypes.windll.shell32.ShellExecuteW
        from agfo_installer import sanitize_process_env
        sanitize_process_env()      # kurucu temiz ortamla baslasin (PyInstaller _PYI_* sizmasi)
    code = shell_execute(None, 'runas', str(setup), UPDATE_ARGS, str(Path(setup).parent), 1)
    if int(code) <= 32:
        raise OSError('Kurulum baslatilamadi veya yonetici onayi verilmedi (kod %s).' % code)


def cleanup_old_downloads(keep: Path | None = None) -> None:
    folder = data_dir() / 'updates'
    for f in folder.glob('AGFO-BackupSync-Setup-*.exe'):
        if keep is None or f.resolve() != Path(keep).resolve():
            try:
                f.unlink()
            except OSError:
                pass
