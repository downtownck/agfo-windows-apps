"""Safe Windows drive letters for AGFO BackupSync.

UNC SMB shares are mapped with `net use`; local directories use SUBST.
No passwords are accepted, logged, or saved. Mutations are explicit GUI actions.
Backup profiles should use original UNC/local paths, never these aliases.
"""
from __future__ import annotations

import ctypes
import ntpath
import os
import re
import subprocess
import sys
from typing import Any

VERSION = '2.3.3'
_DRIVE = re.compile(r'^[D-Z]:?$', re.I)
_UNC = re.compile(r'^\\\\([^\\/:*?"<>|]+)\\([^\\/:*?"<>|]+)(?:\\(.*))?$')
_DISK_PATH = re.compile(r'^[A-Za-z]:\\')


def _windows_exe(name: str) -> str:
    return ntpath.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', name)


def letter(value: str) -> str:
    value = str(value or '').strip().upper()
    if not _DRIVE.fullmatch(value):
        raise ValueError('Surucu harfi D: ile Z: arasinda olmalidir.')
    return value[0] + ':'


def _clean_path(value: str) -> str:
    path = str(value or '').strip().strip('"').strip()
    if not path or any(ord(c) < 32 for c in path):
        raise ValueError('Yol bos veya kontrol karakterleri iceriyor.')
    if path.startswith('\\\\?\\') or path.startswith('\\\\.\\'):
        raise ValueError('Windows aygit adlari surucu eslemede kullanilamaz.')
    if path.startswith('\\\\'):
        match = _UNC.fullmatch(path)
        if not match or match.group(1) in ('.', '..') or match.group(2) in ('.', '..'):
            raise ValueError('Ag yolu \\\\NAS\\Paylasim seklinde olmalidir.')
        return ntpath.normpath(path)
    if not _DISK_PATH.match(path):
        raise ValueError('Yalnizca C:\\Klasor veya \\\\NAS\\Paylasim yollari kabul edilir.')
    return ntpath.normpath(path)


def _run(command: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    if sys.platform != 'win32':
        raise RuntimeError('Surucu esleme sadece Windows icindir.')
    result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                            text=True, encoding='oem', errors='replace', timeout=timeout,
                            shell=False, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        explanation = (result.stderr or result.stdout or '').strip()[-1100:]
        raise RuntimeError('Windows surucu esleme hatasi (%d): %s. Gerekirse once Windows Dosya Gezgini ile NAS oturumu acin.' %
                           (result.returncode, explanation))
    return result


def _subst_drives() -> list[dict[str, str]]:
    if sys.platform != 'win32':
        return []
    try:
        result = subprocess.run([_windows_exe('subst.exe')], stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, encoding='oem',
                                errors='replace', timeout=8,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode:
        return []
    mappings = []
    for entry in result.stdout.splitlines():
        found = re.match(r'^\s*([A-Za-z]):\\:\s*=>\s*(.+?)\s*$', entry)
        if found:
            mappings.append({'letter': found.group(1).upper() + ':',
                             'kind': 'SUBST', 'target': found.group(2).strip(),
                             'state': 'Oturum boyunca'})
    return mappings


def _windows_drive_mask() -> int:
    if sys.platform != 'win32':
        return 0
    return int(ctypes.windll.kernel32.GetLogicalDrives())


def mappings() -> list[dict[str, str]]:
    if sys.platform != 'win32':
        return []
    from agfo_network import _win_mapped_drives, _win_persistent_drives
    rows: dict[str, dict[str, str]] = {}
    for drive, remote in _win_persistent_drives():
        try:
            d = letter(drive)
            rows[d] = {'letter': d, 'kind': 'SMB', 'target': remote,
                       'state': 'Kayitli (baglanti bekleyebilir)'}
        except ValueError:
            pass
    for drive, remote in _win_mapped_drives():
        try:
            d = letter(drive)
            if remote.startswith('\\\\'):
                rows[d] = {'letter': d, 'kind': 'SMB', 'target': remote, 'state': 'Bagli'}
        except ValueError:
            pass
    for row in _subst_drives():
        rows[row['letter']] = row
    return [rows[key] for key in sorted(rows)]


def available_letters() -> list[str]:
    used = {row['letter'] for row in mappings()}
    mask = _windows_drive_mask()
    for char in 'DEFGHIJKLMNOPQRSTUVWXYZ':
        if mask & (1 << (ord(char) - 65)):
            used.add(char + ':')
    return [c + ':' for c in 'DEFGHIJKLMNOPQRSTUVWXYZ' if c + ':' not in used]


def resolve_mapping_path(raw_path: str, known: list[dict[str, str]] | None = None) -> str:
    """Resolve SMB drive aliases before deciding on net use vs. SUBST."""
    path = _clean_path(raw_path)
    if path.startswith('\\\\'):
        return path
    letter_code = path[:2].upper()
    entries = known if known is not None else mappings()
    remote = next((row['target'] for row in entries if row['letter'] == letter_code and
                   row['kind'] == 'SMB' and row['target'].startswith('\\\\')), None)
    if remote:
        suffix = path[2:].lstrip('\\')
        return _clean_path(ntpath.join(remote, suffix)) if suffix else _clean_path(remote)
    if next((row for row in entries if row['letter'] == letter_code and row['kind'] == 'SUBST'), None):
        # Avoid nested mappings with reboot-dependent SUBST aliases.
        base = next(row['target'] for row in entries if row['letter'] == letter_code and row['kind'] == 'SUBST')
        suffix = path[2:].lstrip('\\')
        return _clean_path(ntpath.join(base, suffix)) if suffix else _clean_path(base)
    return path


def mapping_plan(raw_path: str, requested_letter: str, persistent: bool = True,
                 known: list[dict[str, str]] | None = None) -> dict[str, Any]:
    drive = letter(requested_letter)
    target = resolve_mapping_path(raw_path, known)
    if target.startswith('\\\\'):
        return {'letter': drive, 'target': target, 'kind': 'SMB',
                'persistent': bool(persistent),
                'command': [_windows_exe('net.exe'), 'use', drive, target,
                            '/persistent:yes' if persistent else '/persistent:no']}
    if persistent:
        raise ValueError('SUBST yerel klasor eslemesi oturumluk kullanilir. Kalici baglanti icin SMB paylasimi secin.')
    if not _DISK_PATH.match(target):
        raise ValueError('SUBST yalnizca yerel klasorle calisir.')
    if target[:2].upper() == drive:
        raise ValueError('Klasor kendi harfine SUBST ile baglanamaz.')
    return {'letter': drive, 'target': target, 'kind': 'SUBST',
            'persistent': False, 'command': [_windows_exe('subst.exe'), drive, target]}


def list_drives() -> dict[str, Any]:
    if sys.platform != 'win32':
        return {'ok': False, 'mappings': [], 'free_letters': [],
                'message': 'Surucu yonetimi yalnizca Windows 10/11 uzerindedir.'}
    rows = mappings()
    return {'ok': True, 'mappings': rows,
            'free_letters': available_letters(), 'message': '%d esleme bulundu.' % len(rows)}


def map_drive(raw_path: str, requested_letter: str, persistent: bool = True) -> dict[str, Any]:
    if sys.platform != 'win32':
        raise RuntimeError('Surucu esleme sadece Windows icindir.')
    drive = letter(requested_letter)
    # Never overwrite existing physical disks, offline persistent SMB, or SUBST.
    if drive not in available_letters():
        raise ValueError('%s kullaniliyor veya Windows tarafindan ayrilmis. Baska bir harf secin.' % drive)
    plan = mapping_plan(raw_path, drive, persistent)
    if plan['kind'] == 'SUBST' and not os.path.isdir(plan['target']):
        raise ValueError('Yerel klasor bulunamadi: ' + plan['target'])
    _run(plan['command'])
    return {'ok': True, 'message': '%s harfi %s yoluna %s ile baglandi.' %
            (drive, plan['target'], plan['kind']), 'mapping': plan}


def unmap_drive(requested_letter: str) -> dict[str, Any]:
    if sys.platform != 'win32':
        raise RuntimeError('Surucu esleme sadece Windows icindir.')
    drive = letter(requested_letter)
    row = next((item for item in mappings() if item['letter'] == drive), None)
    if row is None:
        raise ValueError('Bu harf AGFO tarafindan yonetilebilecek SMB/SUBST eslemesi degil: ' + drive)
    if row['kind'] == 'SMB':
        _run([_windows_exe('net.exe'), 'use', drive, '/delete', '/yes'])
    elif row['kind'] == 'SUBST':
        _run([_windows_exe('subst.exe'), drive, '/d'])
    else:
        raise ValueError('Bu surucu turu kaldirilamaz.')
    return {'ok': True, 'message': drive + ' eslemesi kaldirildi. NAS dosyalari silinmedi.'}
