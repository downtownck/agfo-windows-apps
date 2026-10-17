"""Self-contained AGFO BackupSync installer, compiled by PyInstaller on Windows.

Installs code only to C:\agfo-backutil. User profiles/logs stay in LocalAppData.
The installer is bundled as an exe by packaging/build_windows.ps1.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from tkinter import messagebox, ttk
import uuid

VERSION = '2.3.1'
INSTALL_DIR = Path(r'C:\agfo-backutil')
APP_EXE = 'AGFO-BackupSync.exe'
SETUP_EXE = 'AGFO-BackupSync-Setup.exe'
UNINSTALL_KEY = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\AGFOBackupSync'
AUTOSTART_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
AUTOSTART_NAME = 'AGFOBackupSync'
SHORTCUT_NAME = 'AGFO BackupSync.lnk'


FROZEN_ENV_PREFIXES = ('_PYI_', '_MEIPASS')


def scrub_frozen_env(env=None) -> dict[str, str]:
    """PyInstaller onefile ortam degiskenlerini (_PYI_*, _MEIPASS2) cikarilmis kopya dondurur.

    Bu degiskenler alt surece gecerse, ayni (onefile) exe kendini 'cocuk surec' sanip baska bir
    _MEI klasorunden python312.dll yuklemeye calisir: 'Failed to load Python DLL' hatasi (v2.3.0, v2.3.1'de duzeltildi).
    PYINSTALLER_RESET_ENVIRONMENT=1, PyInstaller 6.9+ derlenmis alt exe'ye bastan baslamasini soyler.
    """
    src = os.environ if env is None else env
    out = {k: v for k, v in src.items() if not k.upper().startswith(FROZEN_ENV_PREFIXES)}
    out['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return out


def sanitize_process_env() -> None:
    """Calisan surecin ortamini temizler; boylece ShellExecute/explorer/PowerShell ile acilan her
    alt surec (GUI -> AGFO-BackupSync.exe, kurucu, kisayol) temiz baslar. DLL arama dizinini de sifirlar."""
    for key in [k for k in os.environ if k.upper().startswith(FROZEN_ENV_PREFIXES)]:
        try:
            del os.environ[key]
        except KeyError:
            pass
    os.environ['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    if sys.platform == 'win32' and getattr(sys, 'frozen', False):
        try:
            ctypes.windll.kernel32.SetDllDirectoryW(None)
        except (AttributeError, OSError):
            pass


def payload_dir() -> Path:
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'payload'


def payload_files(folder: Path) -> dict[str, str]:
    file = folder / 'manifest.json'
    manifest = json.loads(file.read_text(encoding='utf-8'))
    if manifest.get('version') != VERSION:
        raise RuntimeError('Paket versiyonu beklenenden farkli.')
    hashes = manifest.get('files')
    if not isinstance(hashes, dict) or not hashes:
        raise RuntimeError('Paket dosya listesi eksik.')
    for name, expected in hashes.items():
        if not isinstance(name, str) or not name or '/' in name or '\\' in name or name.startswith('.'):
            raise RuntimeError('Gecersiz kurulum dosyasi: ' + str(name))
        actual = hashlib.sha256((folder / name).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError('Paket dosyasinin butunlugu bozuk: ' + name)
    required = {APP_EXE, 'AGFO-BackupSync-GUI.ps1', 'AGFO-BackupSync-Core.ps1',
                'AGFO-BackupSync-Worker.ps1', 'AGFO-Guvenli-Baslat.ps1',
                'Create-AgfoShortcut.ps1'}
    if not required.issubset(hashes):
        raise RuntimeError('Paket dosyasi eksik: ' + ', '.join(sorted(required - hashes.keys())))
    return hashes


def _admin() -> bool:
    if sys.platform != 'win32':
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def _powershell() -> str:
    return str(Path(os.environ.get('SystemRoot', r'C:\Windows')) /
               'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe')


def _shortcut(link: Path, target: Path, args: str = '', description: str = '') -> None:
    cmd = [_powershell(), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
           '-File', str(INSTALL_DIR / 'Create-AgfoShortcut.ps1'),
           '-LinkPath', str(link), '-ExePath', str(target),
           '-ExeArgs', args, '-Description', description]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=scrub_frozen_env(),
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if proc.returncode:
        raise RuntimeError('Baslat menusu kisayolu olusturulamadi: ' +
                           ((proc.stderr or proc.stdout)[-1600:]))


def _start_menu_dir() -> Path:
    programdata = os.environ.get('ProgramData', r'C:\ProgramData')
    return Path(programdata) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'AGFO'


def _public_desktop() -> Path:
    return Path(os.environ.get('PUBLIC', r'C:\Users\Public')) / 'Desktop'


def _set_registry(autostart: bool) -> None:
    import winreg
    exe = str(INSTALL_DIR / APP_EXE)
    with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
        entries = {
            'DisplayName': 'AGFO BackupSync',
            'DisplayVersion': VERSION,
            'Publisher': 'AGFOCERT',
            'InstallLocation': str(INSTALL_DIR),
            'DisplayIcon': exe,
            'UninstallString': '"' + str(INSTALL_DIR / SETUP_EXE) + '" --uninstall',
            'NoModify': 1,
            'NoRepair': 1,
        }
        for field, val in entries.items():
            typ = winreg.REG_DWORD if isinstance(val, int) else winreg.REG_SZ
            winreg.SetValueEx(key, field, 0, typ, val)
    with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, AUTOSTART_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
        if autostart:
            winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ,
                              '"' + exe + '" --tray-only')
        else:
            try:
                winreg.DeleteValue(key, AUTOSTART_NAME)
            except FileNotFoundError:
                pass


def _set_shortcuts(desktop: bool) -> None:
    menu = _start_menu_dir() / SHORTCUT_NAME
    _shortcut(menu, INSTALL_DIR / APP_EXE, '', 'AGFO BackupSync - NAS yedekleme ve ag kesfi')
    shortcut = _public_desktop() / SHORTCUT_NAME
    if desktop:
        _shortcut(shortcut, INSTALL_DIR / APP_EXE, '', 'AGFO BackupSync')
    else:
        shortcut.unlink(missing_ok=True)


def install(desktop: bool, autostart: bool, on_step=lambda msg: None) -> None:
    if sys.platform != 'win32' or not _admin():
        raise PermissionError('C:\\agfo-backutil kurulumu icin Windows yonetici izni gerekir.')
    on_step('Paket dosyalari dogrulaniyor...')
    source = payload_dir()
    hashes = payload_files(source)
    # Keep user data in %LOCALAPPDATA%; do not touch profiles/logs, old scheduled tasks.
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    staging = INSTALL_DIR / ('.setup-' + uuid.uuid4().hex[:8])
    rollback = Path(tempfile.mkdtemp(prefix='AGFOBackupSyncRollback-'))
    changed: list[tuple[Path, Path | None]] = []
    try:
        staging.mkdir()
        for name in hashes:
            shutil.copy2(source / name, staging / name)
        # Include the setup executable for the uninstall entry in Windows Settings.
        if getattr(sys, 'frozen', False):
            shutil.copy2(sys.executable, staging / SETUP_EXE)
        else:
            # Developer mode is not an installable release.
            raise RuntimeError('Gercek Windows setup.exe kullanilmalidir.')
        on_step('Program dosyalari yerlestiriliyor...')
        for file in staging.iterdir():
            dest = INSTALL_DIR / file.name
            old = None
            if dest.exists():
                old = rollback / file.name
                shutil.copy2(dest, old)
            # os.replace is atomic on the same volume. If exe is running, Windows
            # typically blocks replacement and tells us to close the tray process.
            try:
                os.replace(file, dest)
            except PermissionError as exc:
                raise PermissionError(f'{dest.name} kilitli. Bildirim alanindaki AGFO uygulamasini kapatip tekrar kurun.') from exc
            changed.append((dest, old))
        on_step('Baslat menusu ve Windows kaydi olusturuluyor...')
        _set_shortcuts(desktop)
        _set_registry(autostart)
    except Exception:
        for dest, old in reversed(changed):
            try:
                if old is not None and old.exists():
                    os.replace(old, dest)
                else:
                    dest.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(rollback, ignore_errors=True)
    on_step('Kurulum tamamlandi.')


def _remove_registry_and_links() -> None:
    import winreg
    for file in (_start_menu_dir() / SHORTCUT_NAME, _public_desktop() / SHORTCUT_NAME):
        try:
            file.unlink(missing_ok=True)
        except OSError:
            pass
    try:
        _start_menu_dir().rmdir()
    except OSError:
        pass
    try:
        winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_KEY)
    except OSError:
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, AUTOSTART_NAME)
    except OSError:
        pass


def uninstall() -> str:
    if sys.platform != 'win32' or not _admin():
        raise PermissionError('Kaldirma icin Windows yonetici izni gerekir.')
    # Do not touch %LOCALAPPDATA%/AGFO-BackupSync: profiles, logs and archive
    # references must remain available for re-install or recovery.
    _remove_registry_and_links()
    names = set()
    try:
        names.update(payload_files(payload_dir()).keys())
    except (OSError, ValueError, RuntimeError):
        names.update({APP_EXE, 'AGFO-BackupSync-Core.ps1', 'AGFO-BackupSync-GUI.ps1',
                      'AGFO-BackupSync-Test.ps1', 'AGFO-BackupSync-Worker.ps1',
                      'AGFO-Guvenli-Baslat.ps1', 'Create-AgfoShortcut.ps1',
                      'README-v2.0.txt', 'README-v2.1.txt', 'README-v2.2.txt'})
    names.update({SETUP_EXE, 'manifest.json'})
    pending = []
    for name in names:
        file = INSTALL_DIR / name
        try:
            file.unlink(missing_ok=True)
        except PermissionError:
            # The currently executing setup.exe cannot be removed immediately.
            if sys.platform == 'win32':
                ok = ctypes.windll.kernel32.MoveFileExW(str(file), None, 0x00000004)
                if ok:
                    pending.append(name)
                else:
                    pending.append(name + ' (elle temizlenmeli)')
    try:
        INSTALL_DIR.rmdir()
    except OSError:
        pass
    return ('Kaldirma tamamlandi. Profiller ve loglar korundu. ' +
            ('Yeniden baslatmada temizlenecek: ' + ', '.join(pending) if pending else ''))


def detect_options() -> tuple[bool, bool]:
    """Guncellemede mevcut tercihleri korur: masaustu kisayolu ve oturum acilisinda baslatma."""
    desktop = (_public_desktop() / SHORTCUT_NAME).exists()
    autostart = True
    if sys.platform == 'win32':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, AUTOSTART_KEY, 0, winreg.KEY_READ) as key:
                winreg.QueryValueEx(key, AUTOSTART_NAME)
        except OSError:
            autostart = False
    return desktop, autostart


def relaunch_unelevated() -> None:
    """Yonetici olarak calisan kurucudan uygulamayi NORMAL kullanici yetkisiyle acar (explorer uzerinden)."""
    exe = INSTALL_DIR / APP_EXE
    if sys.platform == 'win32' and exe.is_file():
        windir = os.environ.get('SystemRoot', r'C:\Windows')
        subprocess.Popen([str(Path(windir) / 'explorer.exe'), str(exe)], close_fds=True,
                         env=scrub_frozen_env())


def run_update(on_step=lambda msg: None, install_fn=None, detect_fn=detect_options, relaunch_fn=relaunch_unelevated,
               retries: int = 25, delay: float = 1.2, sleep=time.sleep) -> tuple[bool, bool]:
    """Sessiz guncelleme: tercihleri koru, tepsi uygulamasinin kapanmasini bekle (kilit), kur, yeniden ac."""
    install_fn = install_fn or install
    desktop, autostart = detect_fn()
    for attempt in range(retries):
        try:
            install_fn(desktop, autostart, on_step)
            break
        except PermissionError as exc:
            if 'kilitli' in str(exc) and attempt < retries - 1:
                on_step('Calisan AGFO uygulamasinin kapanmasi bekleniyor...')
                sleep(delay)
                continue
            raise
    relaunch_fn()
    return desktop, autostart


def update_main() -> int:
    root = tk.Tk()
    root.title('AGFO BackupSync - Guncelleme v' + VERSION)
    root.geometry('520x170')
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=20)
    frame.pack(fill=tk.BOTH, expand=True)
    ttk.Label(frame, text='AGFO BackupSync v' + VERSION + ' kuruluyor', font=('Segoe UI', 14, 'bold')).pack(anchor='w')
    status = tk.StringVar(value='Hazirlaniyor...')
    ttk.Label(frame, textvariable=status, wraplength=470).pack(anchor='w', pady=(12, 0))
    bar = ttk.Progressbar(frame, mode='indeterminate')
    bar.pack(fill=tk.X, pady=(12, 0))
    bar.start(12)
    outcome = {}

    def work():
        try:
            run_update(lambda msg: outcome.__setitem__('step', msg))
            outcome['ok'] = True
        except Exception as exc:
            outcome['error'] = str(exc)

    def poll():
        if 'step' in outcome:
            status.set(outcome.pop('step'))
        if outcome.get('ok'):
            bar.stop()
            status.set('Guncelleme tamamlandi. Uygulama yeniden aciliyor...')
            root.after(2500, root.destroy)
            return
        if 'error' in outcome:
            bar.stop()
            status.set('HATA: ' + outcome['error'])
            messagebox.showerror('Guncelleme hatasi', outcome['error'] + '\n\nOnceki dosyalar geri yuklendi. Kurulumu daha sonra tekrar deneyebilirsiniz.')
            root.destroy()
            return
        root.after(200, poll)
    import threading
    threading.Thread(target=work, daemon=True).start()
    root.after(200, poll)
    root.mainloop()
    return 0 if outcome.get('ok') else 1


def main() -> int:
    sanitize_process_env()
    if '--update' in sys.argv:
        return update_main()
    is_uninstall = '--uninstall' in sys.argv
    root = tk.Tk()
    root.title('AGFO BackupSync - ' + ('Kaldirma' if is_uninstall else 'Kurulum') + ' v' + VERSION)
    root.geometry('560x335')
    root.resizable(False, False)
    root.configure(bg='#f5f8fc')
    frame = ttk.Frame(root, padding=22)
    frame.pack(fill=tk.BOTH, expand=True)
    ttk.Label(frame, text='AGFO BackupSync v' + VERSION,
              font=('Segoe UI', 18, 'bold')).pack(anchor='w', pady=(0, 9))
    if is_uninstall:
        ttk.Label(frame, text='Yalnizca uygulama kodu kaldirilir; yedek profilleri ve loglar silinmez.',
                  wraplength=510).pack(anchor='w', pady=(0, 16))
    else:
        ttk.Label(frame, text='Kurulum klasoru: C:\\agfo-backutil',
                  font=('Segoe UI', 11, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='Windows Baslat menusu kisayolu otomatik olusturulur.',
                  wraplength=510).pack(anchor='w', pady=(8, 17))
    opt_desktop = tk.BooleanVar(value=True)
    opt_autostart = tk.BooleanVar(value=True)
    if not is_uninstall:
        ttk.Checkbutton(frame, text='Masaustune kisayol ekle', variable=opt_desktop).pack(anchor='w', pady=5)
        ttk.Checkbutton(frame, text='Oturum acildiginda tepsi simgesini baslat (tum kullanicilar)',
                        variable=opt_autostart).pack(anchor='w', pady=5)
    status = tk.StringVar(value='Hazir. Mevcut profiller ve zamanli gorevler korunacak.')
    ttk.Label(frame, textvariable=status, wraplength=500).pack(anchor='w', pady=(19, 7))
    buttons = ttk.Frame(frame)
    buttons.pack(anchor='e', fill=tk.X, pady=8)
    action = ttk.Button(buttons, text='Kaldir' if is_uninstall else 'Kur')
    action.pack(side=tk.RIGHT, padx=(8, 0))
    ttk.Button(buttons, text='Vazgec', command=root.destroy).pack(side=tk.RIGHT)

    def do_action() -> None:
        action.configure(state='disabled')
        root.update_idletasks()
        try:
            if is_uninstall:
                if not messagebox.askyesno('Kaldirmayi onayla',
                                           'AGFO BackupSync kaldirilsin mi? Profiller ve loglar korunacak.'):
                    return
                status.set(uninstall())
            else:
                install(opt_desktop.get(), opt_autostart.get(),
                        lambda msg: (status.set(msg), root.update_idletasks()))
                messagebox.showinfo('AGFO BackupSync',
                                    'Kurulum tamamlandi. Baslat > AGFO > AGFO BackupSync yolundan acabilirsiniz.\n\n'
                                    'Bildirim alani simgesi Windows acilisinda otomatik baslayabilir.')
            action.configure(text='Tamam', command=root.destroy)
        except Exception as exc:
            status.set('HATA: ' + str(exc))
            messagebox.showerror('Kurulum hatasi', str(exc))
        finally:
            action.configure(state='normal')
    action.configure(command=do_action)
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
