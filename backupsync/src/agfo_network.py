"""Read-only Windows NAS discovery for AGFO BackupSync.

No SMB1 activation, credential guessing, share mounting or remote writes.
A subnet probe is only performed after an explicit GUI action.
"""
from __future__ import annotations

import concurrent.futures
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
from typing import Any

VERSION = '2.3.3'


def _add(items: list[dict[str, Any]], kind: str, path: str, name: str, origin: str,
         state: str = 'Bulundu', selectable: bool = True) -> None:
    path = str(path or '').strip().rstrip('\\')
    if not path:
        return
    # Always use the UNC target for a mapped network drive when possible.
    key = path.casefold()
    if any(str(it['path']).casefold() == key for it in items):
        return
    items.append({'kind': kind, 'path': path, 'name': name,
                  'origin': origin, 'state': state, 'selectable': bool(selectable)})


def _profile_unc_paths() -> list[str]:
    local = os.environ.get('LOCALAPPDATA')
    if not local:
        return []
    folder = Path(local) / 'AGFO-BackupSync' / 'profiles'
    paths: list[str] = []
    for file in list(folder.glob('*.json'))[:300]:
        try:
            data = json.loads(file.read_text(encoding='utf-8-sig'))
            for key in ('source', 'target'):
                value = str(data.get(key, ''))
                if value.startswith('\\\\'):
                    match = re.match(r'^(\\\\[^\\]+\\[^\\]+)', value)
                    if match:
                        paths.append(match.group(1))
        except (OSError, ValueError, TypeError):
            continue
    return sorted(set(paths), key=str.lower)


def _win_mapped_drives() -> list[tuple[str, str]]:
    if sys.platform != 'win32':
        return []
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    mpr = ctypes.WinDLL('mpr', use_last_error=True)
    kernel32.GetLogicalDrives.argtypes = []
    kernel32.GetLogicalDrives.restype = wintypes.DWORD
    kernel32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetDriveTypeW.restype = wintypes.UINT
    mpr.WNetGetConnectionW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    mpr.WNetGetConnectionW.restype = wintypes.DWORD
    mask = int(kernel32.GetLogicalDrives())
    rows: list[tuple[str, str]] = []
    for index in range(26):
        if not (mask & (1 << index)):
            continue
        drive = f'{chr(65 + index)}:'
        if kernel32.GetDriveTypeW(drive + '\\') != 4:  # DRIVE_REMOTE
            continue
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        status = mpr.WNetGetConnectionW(drive, buffer, ctypes.byref(size))
        rows.append((drive, buffer.value if status == 0 else drive + '\\'))
    return rows


def _win_persistent_drives() -> list[tuple[str, str]]:
    if sys.platform != 'win32':
        return []
    import winreg
    rows = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Network') as root:
            index = 0
            while True:
                try:
                    letter = winreg.EnumKey(root, index)
                    index += 1
                except OSError:
                    break
                try:
                    with winreg.OpenKey(root, letter) as key:
                        remote = str(winreg.QueryValueEx(key, 'RemotePath')[0])
                    rows.append((letter.upper() + ':', remote))
                except OSError:
                    continue
    except OSError:
        pass
    return rows



def _win_active_smb_connections() -> list[tuple[str, str]]:
    """Windows SMB 2/3 sessions, including un-mapped Explorer UNC shares."""
    if sys.platform != 'win32':
        return []
    expression = (
        '[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); '
        'Get-SmbConnection -ErrorAction SilentlyContinue | '
        'Select-Object ServerName,ShareName | ConvertTo-Json -Compress'
    )
    try:
        completed = subprocess.run([
            'powershell.exe', '-NoProfile', '-NonInteractive', '-Command', expression
        ], capture_output=True, encoding='utf-8', errors='replace', timeout=9,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if completed.returncode or not completed.stdout.strip():
            return []
        payload = json.loads(completed.stdout.strip().lstrip('\ufeff'))
        rows = payload if isinstance(payload, list) else [payload]
        return [(str(item.get('ServerName', '')), str(item.get('ShareName', '')))
                for item in rows if isinstance(item, dict) and
                item.get('ServerName') and item.get('ShareName')]
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        return []

def known_items() -> tuple[list[dict[str, Any]], list[str]]:
    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    if sys.platform == 'win32':
        try:
            for drive, share in _win_mapped_drives():
                _add(items, 'Bagli ag surucusu', share, f'{drive} -> {share}',
                     'Windows ag surucusu', 'Bagli')
        except OSError as exc:
            warnings.append('Ag suruculeri: ' + str(exc))
        try:
            for drive, share in _win_persistent_drives():
                _add(items, 'Kayitli ag surucusu', share, f'{drive} -> {share}',
                     'Windows kalici baglanti', 'Baglanti dogrulanmadi')
        except OSError as exc:
            warnings.append('Kayitli suruculer: ' + str(exc))
        for server, share in _win_active_smb_connections():
            if share.endswith('$'):
                continue
            remote = chr(92) * 2 + server + chr(92) + share
            _add(items, 'Aktif SMB', remote, remote, 'Windows SMB oturumu', 'Bagli')
    else:
        warnings.append('Windows ag surucusu kesfi yalnizca Windows uzerinde calisir.')
    for path in _profile_unc_paths():
        _add(items, 'Profildeki SMB', path, path, 'AGFO yedek profili',
             'Baglanti dogrulanmadi')
    return items, warnings


def _private_networks() -> list[ipaddress.IPv4Network]:
    addresses: list[str] = []
    if sys.platform == 'win32':
        command = [
            'powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
            'Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | '
            'Where-Object {$_.AddressState -eq "Preferred"} | '
            'Select-Object -ExpandProperty IPAddress | ConvertTo-Json -Compress'
        ]
        try:
            proc = subprocess.run(command, capture_output=True, text=True, timeout=9,
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if proc.returncode == 0 and proc.stdout.strip():
                output = json.loads(proc.stdout)
                addresses += output if isinstance(output, list) else [str(output)]
        except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
            pass
    if not addresses:
        try:
            addresses += socket.gethostbyname_ex(socket.gethostname())[2]
        except OSError:
            pass
    result: list[ipaddress.IPv4Network] = []
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if not isinstance(ip, ipaddress.IPv4Address):
            continue
        if not (ip in ipaddress.ip_network('10.0.0.0/8') or
                ip in ipaddress.ip_network('172.16.0.0/12') or
                ip in ipaddress.ip_network('192.168.0.0/16')):
            continue
        subnet = ipaddress.ip_network(f'{ip}/24', strict=False)
        if subnet not in result:
            result.append(subnet)
    # Bounded: never enumerate an unbounded enterprise network or VPN range.
    return result[:2]


def _has_smb(ip: str, timeout: float = 0.45) -> bool:
    try:
        with socket.create_connection((ip, 445), timeout=timeout):
            return True
    except OSError:
        return False


def _scan_smb_hosts(networks: list[ipaddress.IPv4Network]) -> list[str]:
    candidates = [str(ip) for net in networks for ip in net.hosts()]
    found = []
    if not candidates:
        return found
    with concurrent.futures.ThreadPoolExecutor(max_workers=48) as pool:
        matches = pool.map(_has_smb, candidates)
        found = [ip for ip, ok in zip(candidates, matches) if ok]
    return found[:80]


def _win_net_shares(server: str) -> tuple[list[str], str]:
    """Level 1 NetShareEnum, read-only; no credentials requested or stored."""
    if sys.platform != 'win32':
        return [], 'Windows disinda SMB paylasim sorgulama kapali.'

    class SHARE_INFO_1(ctypes.Structure):
        _fields_ = [('name', wintypes.LPWSTR), ('kind', wintypes.DWORD),
                    ('remark', wintypes.LPWSTR)]

    netapi = ctypes.WinDLL('Netapi32', use_last_error=True)
    netapi.NetShareEnum.argtypes = [wintypes.LPWSTR, wintypes.DWORD,
                                    ctypes.POINTER(ctypes.c_void_p), wintypes.DWORD,
                                    ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
                                    ctypes.POINTER(wintypes.DWORD)]
    netapi.NetShareEnum.restype = wintypes.DWORD
    netapi.NetApiBufferFree.argtypes = [ctypes.c_void_p]
    netapi.NetApiBufferFree.restype = wintypes.DWORD
    buffer = ctypes.c_void_p()
    entries, total, resume = wintypes.DWORD(0), wintypes.DWORD(0), wintypes.DWORD(0)
    try:
        code = netapi.NetShareEnum('\\\\' + server, 1, ctypes.byref(buffer), 0xFFFFFFFF,
                                   ctypes.byref(entries), ctypes.byref(total), ctypes.byref(resume))
        if code not in (0, 234):
            return [], f'Paylasim listesi icin Windows erisimi yetersiz olabilir (kod {code}).'
        if not buffer.value:
            return [], ''
        ptr = ctypes.cast(buffer, ctypes.POINTER(SHARE_INFO_1))
        names = [str(ptr[i].name) for i in range(min(entries.value, 300))
                 if ptr[i].name and (ptr[i].kind & 0xFF) == 0
                 and not str(ptr[i].name).endswith('$')]
        return sorted(set(names), key=str.lower), ''
    finally:
        if buffer.value:
            netapi.NetApiBufferFree(buffer)


def discover(mode: str = 'known') -> dict[str, Any]:
    if mode not in ('known', 'scan'):
        raise ValueError('Invalid discovery mode')
    items, warnings = known_items()
    if mode == 'scan':
        if sys.platform != 'win32':
            warnings.append('Yerel ag SMB taramasi sadece Windows icindir.')
        else:
            networks = _private_networks()
            if not networks:
                warnings.append('Ozel IPv4 agi bulunamadi; tarama yapilmadi.')
            else:
                warnings.append('Taranan yerel ag: ' + ', '.join(map(str, networks)))
                hosts = _scan_smb_hosts(networks)
                for ip in hosts:
                    shares, err = _win_net_shares(ip)
                    for name in shares:
                        path = '\\\\' + ip + '\\' + name
                        _add(items, 'SMB paylasimi', path, name, f'SMB sunucu: {ip}',
                             'Goruldu; erisimi test edin')
                    _add(items, 'SMB sunucusu', '\\\\' + ip,
                         ip + (' (paylasim listesi alinamadi)' if not shares else ''),
                         'TCP/445', 'SMB acik; paylasim secin', False)
                    if err and len(warnings) < 12:
                        warnings.append(f'{ip}: {err}')
                if not hosts:
                    warnings.append('SMB portu acik yeni cihaz bulunamadi.')
    items.sort(key=lambda it: (not it['selectable'], it['kind'], it['name'].casefold()))
    return {
        'version': VERSION,
        'mode': mode,
        'generatedUtc': datetime.now(timezone.utc).isoformat(),
        'items': items,
        'warnings': warnings[:12]
    }


def write_result(result: dict[str, Any], output_path: str) -> None:
    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + '.tmp')
    try:
        temp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()
