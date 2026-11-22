# -*- coding: utf-8 -*-
"""AGFO Router Connect - Windows acilisinda kucultulmus baslatma (Baslangic klasoru kisayolu; yonetici gerekmez)."""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

LNK_NAME = 'AGFO Router Connect.lnk'
CREATE_NO_WINDOW = 0x08000000


def startup_dir() -> pathlib.Path:
    base = os.environ.get('APPDATA') or str(pathlib.Path.home())
    return pathlib.Path(base) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'Startup'


def is_enabled() -> bool:
    return (startup_dir() / LNK_NAME).exists()


def _q(s) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def create_script(exe) -> str:
    return '\r\n'.join([
        "$ErrorActionPreference = 'Stop'",
        "$dir = [Environment]::GetFolderPath('Startup')",
        "[void][System.IO.Directory]::CreateDirectory($dir)",
        "$exe = %s" % _q(exe),
        "$l = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $dir %s))" % _q(LNK_NAME),
        "$l.TargetPath = $exe; $l.Arguments = '--minimized'; $l.WorkingDirectory = [System.IO.Path]::GetDirectoryName($exe)",
        "$l.Description = 'AGFO Router Connect'; $l.IconLocation = $exe + ',0'; $l.Save()",
    ]) + '\r\n'


def _powershell() -> str:
    root = os.environ.get('SystemRoot', r'C:\Windows')
    return str(pathlib.Path(root) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe')


def set_enabled(enabled: bool, exe, run=subprocess.run) -> None:
    """Acilista baslatmayi acar/kapatir. Hata durumunda OSError firlatir."""
    lnk = startup_dir() / LNK_NAME
    if not enabled:
        try:
            lnk.unlink()
        except FileNotFoundError:
            pass
        return
    if not exe or not pathlib.Path(exe).exists():
        raise OSError('Kurulu uygulama bulunamadı. Önce Derle-ve-Kur.cmd ile kurun.')
    import tempfile
    fd, path = tempfile.mkstemp(prefix='agfo-router-startup-', suffix='.ps1')
    with os.fdopen(fd, 'w', encoding='utf-8-sig') as f:
        f.write(create_script(exe))
    try:
        p = run([_powershell(), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', path],
                capture_output=True, text=True, timeout=60,
                creationflags=CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        if p.returncode:
            raise OSError('Kısayol oluşturulamadı: ' + (p.stderr or p.stdout or '')[-300:])
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
