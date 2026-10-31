"""Read official Smart Organizer GitHub Releases; verify SHA-256 before staging.

No network traffic unless the user presses the update button.
"""
from __future__ import annotations
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from urllib import request
from urllib.parse import urlsplit

REPO = 'downtownck/agfo-windows-apps'
API = f'https://api.github.com/repos/{REPO}/releases?per_page=100'
TAG_PREFIX = 'smart-organizer-v'
MAX_BYTES = 120_000_000
ALLOWED_HOSTS = {'github.com', 'api.github.com', 'objects.githubusercontent.com',
                 'release-assets.githubusercontent.com'}


def version_tuple(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', str(value).strip())
    return tuple(map(int, match.groups())) if match else None


def _read(url, max_bytes=MAX_BYTES):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError('Güvenilmeyen güncelleme adresi.')
    req = request.Request(url, headers={'User-Agent': 'AGFO-Smart-Organizer/1.1',
                                        'Accept': 'application/vnd.github+json'})
    with request.urlopen(req, timeout=30) as resp:
        final = urlsplit(resp.geturl())
        if final.scheme != 'https' or final.hostname not in ALLOWED_HOSTS:
            raise ValueError('Güncelleme güvenilmeyen bir adrese yönlendirildi.')
        data = resp.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError('Güncelleme dosyası beklenenden büyük.')
        return data


def check_release(current):
    """Find latest release tagged smart-organizer-vX.Y.Z (not unrelated repo releases)."""
    local = version_tuple(current)
    if local is None:
        raise ValueError('Kurulu uygulama sürümü anlaşılamadı.')
    releases = json.loads(_read(API, 1_000_000))
    if not isinstance(releases, list):
        raise ValueError('GitHub Releases listesi okunamadı.')
    matches = []
    for info in releases:
        if not isinstance(info, dict) or info.get('draft') or info.get('prerelease'):
            continue
        tag = str(info.get('tag_name') or '')
        if not tag.startswith(TAG_PREFIX):
            continue
        version = version_tuple(tag[len(TAG_PREFIX):])
        if version and version > local:
            matches.append((version, tag, info))
    if not matches:
        return None
    version, tag, info = max(matches, key=lambda x: x[0])
    assets = {a['name']: a['browser_download_url'] for a in info.get('assets', [])
              if isinstance(a, dict) and isinstance(a.get('name'), str)
              and isinstance(a.get('browser_download_url'), str)}
    zipname = f'AGFO-Smart-Organizer-v{tag[len(TAG_PREFIX):]}.zip'
    checksum = zipname + '.sha256'
    if zipname not in assets or checksum not in assets:
        raise ValueError('Smart Organizer sürümünde ZIP ve SHA-256 dosyası yok; indirme durduruldu.')
    prefix = f'https://github.com/{REPO}/releases/download/{tag}/'
    if assets[zipname] != prefix + zipname or assets[checksum] != prefix + checksum:
        raise ValueError('Beklenmeyen GitHub güncelleme bağlantısı.')
    return {'version': tag[len(TAG_PREFIX):], 'notes': str(info.get('body') or '')[:1200],
            'zip_url': assets[zipname], 'sha_url': assets[checksum], 'name': zipname}


def _verify_zip(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 150 or sum(x.file_size for x in entries) > 250_000_000:
                raise ValueError('Güncelleme arşivi beklenenden büyük.')
            for entry in entries:
                name = entry.filename.replace('\\', '/')
                parts = name.split('/')
                if (name.startswith('/') or '..' in parts or ':' in name or
                        any(part in ('', '.') for part in parts if part != parts[-1])):
                    raise ValueError('Güncelleme arşivinde güvensiz yol var.')
                if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Güncelleme arşivinde bağlantı dosyası var.')
            if archive.testzip() is not None:
                raise ValueError('Güncelleme ZIP dosyası bozuk.')
            names = set(archive.namelist())
            if not {'organizer_core.py', 'smart_organizer.pyw', 'update_checker.py', 'GUNCELLE-KUR.ps1'} <= names:
                raise ValueError('Güncelleme paketinde gerekli dosyalar eksik.')
    except zipfile.BadZipFile as exc:
        raise ValueError('İndirilen dosya geçerli ZIP değil.') from exc


def download_verified(release, directory):
    """Stage a hash-checked archive; the user must approve installation separately."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    checksum = _read(release['sha_url'], 4096).decode('ascii').strip()
    name = release['name']
    match = re.fullmatch(r'([a-fA-F0-9]{64})(?:\s+\*?' + re.escape(name) + r')?', checksum)
    if not match:
        raise ValueError('SHA-256 dosyası beklenen biçimde değil.')
    data = _read(release['zip_url'])
    if hashlib.sha256(data).hexdigest().lower() != match.group(1).lower():
        raise ValueError('SHA-256 uyuşmazlığı; güncelleme uygulanmadı.')
    _verify_zip(data)
    target = directory / name
    tmp = target.with_suffix('.zip.tmp')
    tmp.write_bytes(data)
    tmp.replace(target)
    target.with_name(name + '.sha256').write_text(match.group(1).lower(), encoding='ascii')
    return target


def launch_install(archive, install_dir, pid):
    """Launch Windows updater after the user's consent; the GUI then exits.

    The helper is copied outside the install directory so it can update itself.
    """
    import os
    import shutil
    import subprocess
    import sys
    if sys.platform != 'win32':
        raise RuntimeError('Otomatik kurulum yalnızca Windows üzerinde çalışır.')
    archive = Path(archive).resolve()
    install_dir = Path(install_dir).resolve()
    if not archive.is_file() or not archive.with_name(archive.name + '.sha256').is_file():
        raise FileNotFoundError('İndirilen güncelleme veya SHA-256 dosyası bulunamadı.')
    expected = archive.with_name(archive.name + '.sha256').read_text(encoding='ascii').strip()
    if not re.fullmatch(r'[0-9a-fA-F]{64}', expected):
        raise ValueError('Güncelleme SHA-256 dosyası geçersiz.')
    if hashlib.sha256(archive.read_bytes()).hexdigest().lower() != expected.lower():
        raise ValueError('Güncelleme ZIP dosyası değişmiş; kurulum iptal edildi.')
    helper = install_dir / 'GUNCELLE-KUR.ps1'
    if not helper.is_file():
        raise FileNotFoundError('Güncelleme yardımcısı bulunamadı.')
    external_helper = archive.parent / ('GUNCELLE-KUR-' + str(pid) + '.ps1')
    shutil.copy2(helper, external_helper)
    subprocess.Popen(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                      '-File', str(external_helper), '-Archive', str(archive),
                      '-InstallDir', str(install_dir), '-WaitPid', str(pid)],
                     creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0),
                     close_fds=True)
