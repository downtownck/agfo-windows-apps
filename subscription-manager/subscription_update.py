# -*- coding: utf-8 -*-
"""AGFO Subscription Manager - GitHub'dan tek tikla guncelleme (yonetici gerekmez).

Uygulama EXE'si kullanicinin bilgisayarinda derlenir (SmartScreen uyarisi olmasin diye).
Guncelleme: yeni surumun Kurulum ZIP'i GitHub Releases'ten indirilir, SHA-256 ile dogrulanir,
gecici klasore acilir ve Derle-ve-Kur.cmd /update calistirilir; betik eski EXE'yi kapatip yenisini
derler, kurar ve acar. Kullanici verisi (%APPDATA%\\AGFO\\SubscriptionManager) korunur.
Alt surece PyInstaller ortam degiskenleri gecirilmez. Guven koku GitHub hesabidir.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import zipfile

import agfo_github_update as ghu
import subscription_core as core

GH_PREFIX = 'subscription-manager-v'
GH_ASSET = r'AGFO-Subscription-Manager-v[0-9.]+-Kurulum\.zip'
USER_AGENT = 'AGFO-Subscription-Manager/%s' % core.VERSION
CHECK_INTERVAL = 6 * 3600

CREATE_NEW_CONSOLE = 0x00000010
CREATE_NEW_PROCESS_GROUP = 0x00000200


def data_dir() -> pathlib.Path:
    base = os.environ.get('APPDATA') or os.path.join(os.path.expanduser('~'), '.config')
    p = pathlib.Path(base) / 'AGFO' / 'SubscriptionManager'
    p.mkdir(parents=True, exist_ok=True)
    return p


def state_path() -> pathlib.Path:
    return data_dir() / 'github-update.json'


def updates_dir() -> pathlib.Path:
    p = data_dir() / 'updates'
    p.mkdir(parents=True, exist_ok=True)
    return p


def scrub_env(env=None) -> dict:
    """Alt surece PyInstaller onefile ic degiskenlerini gecirme (yoksa yeni EXE bozuk acilir)."""
    src = os.environ if env is None else env
    out = {k: v for k, v in src.items() if not k.upper().startswith(('_PYI_', '_MEIPASS'))}
    out['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return out


def package_ready(release: dict, asset: dict) -> bool:
    if not asset or not asset.get('url'):
        return False
    if asset.get('sha256'):
        return True
    return ghu.pick_asset(release, r'SHA256SUMS(\.txt)?') is not None


def check(force=False, releases=None) -> dict:
    """Hata firlatmaz. 'update' yalniz paket indirilebilir ve dogrulanabilir oldugunda doner."""
    res = ghu.check_for_update(GH_PREFIX, core.VERSION, state_path(), GH_ASSET, force=force,
                               interval=CHECK_INTERVAL, releases=releases, user_agent=USER_AGENT)
    if res.get('status') == 'update' and not package_ready(res.get('release') or {}, res.get('asset') or {}):
        return {'status': 'error', 'version': res.get('version'),
                'message': 'v%s yayınlanmış ama paket henüz doğrulanamıyor (SHA-256 özeti yok).' % res.get('version')}
    return res


def download(result: dict, progress=None, should_stop=None) -> pathlib.Path:
    rel, asset = result['release'], result['asset']
    sha = ghu.expected_sha256(rel, asset, user_agent=USER_AGENT)
    dest = updates_dir() / asset['name']
    ghu.download_asset(asset, dest, sha, progress, should_stop, user_agent=USER_AGENT)
    return dest


def extract(zip_path) -> pathlib.Path:
    """ZIP'i guvenli bicimde acar (yol disina tasma yok) ve Derle-ve-Kur.cmd'nin klasorunu dondurur."""
    zip_path = pathlib.Path(zip_path)
    out = updates_dir() / zip_path.stem
    if out.exists():
        shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    root = out.resolve()
    with zipfile.ZipFile(zip_path) as z:
        for m in z.infolist():
            target = (out / m.filename).resolve()
            if root != target and root not in target.parents:
                raise ghu.GHUpdateError('Pakette güvensiz yol: %s' % m.filename)
        z.extractall(out)
    for p in out.rglob('Derle-ve-Kur.cmd'):
        return p.parent
    raise ghu.GHUpdateError('Pakette Derle-ve-Kur.cmd yok.')


def run_installer(folder, popen=subprocess.Popen):
    """Derle-ve-Kur.cmd /update'i yeni bir konsolda baslatir (kullanici ilerlemeyi gorur)."""
    cmd = pathlib.Path(folder) / 'Derle-ve-Kur.cmd'
    comspec = os.environ.get('ComSpec') or 'cmd.exe'
    return popen([comspec, '/c', str(cmd), '/update'], cwd=str(folder), env=scrub_env(), close_fds=True,
                 creationflags=CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP)


def cleanup_downloads(keep=None) -> None:
    for f in updates_dir().iterdir():
        if keep is not None and f.resolve() == pathlib.Path(keep).resolve():
            continue
        try:
            shutil.rmtree(f) if f.is_dir() else f.unlink()
        except OSError:
            pass
