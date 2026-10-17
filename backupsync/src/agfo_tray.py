"""AGFO BackupSync Windows notification-area companion (Python, PyInstaller)."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import ctypes

APPNAME = 'AGFO BackupSync'
ROOT = Path(r'C:\agfo-backutil') if sys.platform == 'win32' else Path(__file__).parent


def _log_error(message: str) -> None:
    root = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'AGFO-BackupSync' / 'logs'
    try:
        root.mkdir(parents=True, exist_ok=True)
        with (root / 'tray-last-error.txt').open('a', encoding='utf-8') as file:
            file.write(message + '\n')
    except OSError:
        pass


def _powershell() -> str:
    system = os.environ.get('SystemRoot', r'C:\Windows')
    path = Path(system) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'
    return str(path)


def _child_env() -> dict[str, str]:
    from agfo_installer import scrub_frozen_env
    return scrub_frozen_env()


def launch_gui() -> bool:
    path = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else ROOT
    script = path / 'AGFO-Guvenli-Baslat.ps1'
    if not script.is_file():
        _log_error('Missing GUI script: ' + str(script))
        return False
    try:
        subprocess.Popen([_powershell(), '-NoProfile', '-ExecutionPolicy', 'Bypass',
                          '-STA', '-WindowStyle', 'Hidden', '-File', str(script)],
                         cwd=str(path), close_fds=True, env=_child_env(),
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return True
    except OSError as exc:
        _log_error('GUI start failed: ' + str(exc))
        return False


def open_folder(name: str) -> None:
    folder = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'AGFO-BackupSync' / name
    folder.mkdir(parents=True, exist_ok=True)
    try:
        os.startfile(str(folder))  # type: ignore[attr-defined]
    except OSError as exc:
        _log_error('Folder open failed: ' + str(exc))


def _one_instance() -> bool:
    """Return True if this process owns the single tray instance."""
    if sys.platform != 'win32':
        return True
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel32.CreateMutexW(None, False, r'Local\AGFO_BackupSync_Tray')
    if not handle:
        return True
    # Keep the handle alive until exit; losing this reference would release the mutex.
    global _MUTEX_HANDLE
    _MUTEX_HANDLE = handle
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


def start_tray(show_gui: bool) -> int:
    if sys.platform != 'win32':
        print('Tray requires Windows.')
        return 3
    if not _one_instance():
        if show_gui:
            launch_gui()
        return 0
    try:
        import pystray
        from PIL import Image
    except ImportError as exc:
        _log_error('Missing tray library: ' + str(exc))
        return 4
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    iconfile = root / 'assets' / 'agfo-tray.png'
    try:
        picture = Image.open(iconfile).convert('RGBA')
    except OSError as exc:
        _log_error('Icon error: ' + str(exc))
        return 5

    def open_ui(icon, item=None) -> None:
        if not launch_gui():
            try:
                icon.notify('Acilis hatasi. logs/tray-last-error.txt dosyasina bakin.', APPNAME)
            except Exception:
                pass

    def quit_tray(icon, item=None) -> None:
        stop_checks.set()
        icon.stop()

    # ---- GitHub'dan tek tik guncelleme
    upd = {'result': None, 'busy': False}
    stop_checks = threading.Event()

    def notify(message: str) -> None:
        try:
            icon.notify(message, APPNAME)
        except Exception:
            pass

    def do_check(force: bool) -> None:
        try:
            import agfo_selfupdate as su
            res = su.check(force=force)
        except Exception as exc:
            _log_error('Update check: ' + repr(exc))
            return
        if res.get('status') == 'update':
            first = upd['result'] is None or upd['result'].get('version') != res['version']
            upd['result'] = res
            try:
                icon.update_menu()
            except Exception:
                pass
            if first or force:
                notify('Yeni surum v%s hazir. Simgeye sag tiklayip "Guncelle" secin.' % res['version'])
        elif force:
            notify({'current': 'Guncelsiniz (son surum v%s).' % res.get('version', ''), 'none': 'GitHub\'da henuz surum yok.',
                    'skipped': 'v%s atlanmis.' % res.get('version', ''), 'error': 'Denetlenemedi: %s' % res.get('message', '')}.get(res.get('status'), ''))

    def check_loop() -> None:
        if stop_checks.wait(20):
            return
        while True:
            do_check(False)
            if stop_checks.wait(12 * 3600):
                return

    def update_now(icon, item=None) -> None:
        res = upd['result']
        if not res or upd['busy']:
            return
        import agfo_selfupdate as su
        if not su.installed_mode():
            notify('Bu kopya kurulu surum degil; C:\\agfo-backutil kurulumu guncellenebilir.')
            return
        upd['busy'] = True

        def work() -> None:
            try:
                notify('v%s indiriliyor ve dogrulaniyor...' % res['version'])
                setup = su.download_setup(res)
                su.cleanup_old_downloads(keep=setup)
                su.launch_setup(setup)
                notify('Kurulum baslatildi. Uygulama guncellemeden sonra yeniden acilacak.')
                stop_checks.set()
                icon.stop()          # exe kilidini birak; kurulum programi bekler
            except Exception as exc:
                _log_error('Update: ' + repr(exc))
                notify('Guncelleme yapilamadi: %s' % exc)
            finally:
                upd['busy'] = False
        threading.Thread(target=work, daemon=True).start()

    menu = pystray.Menu(
        pystray.MenuItem(lambda item: ('Guncelle: v%s (tek tik)' % upd['result']['version']) if upd['result'] else 'Guncelle',
                         update_now, visible=lambda item: bool(upd['result'])),
        pystray.MenuItem('Yedekleme yoneticisini ac', open_ui, default=True),
        pystray.MenuItem('Kayitlari ac', lambda icon, item: open_folder('logs')),
        pystray.MenuItem('Profilleri ac', lambda icon, item: open_folder('profiles')),
        pystray.MenuItem('Guncellemeleri denetle', lambda icon, item: threading.Thread(target=do_check, args=(True,), daemon=True).start()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('Bildirim alanindan cik', quit_tray)
    )
    from agfo_installer import VERSION as _VERSION
    icon = pystray.Icon('AGFO-BackupSync', picture, 'AGFO BackupSync v' + _VERSION, menu)
    if show_gui:
        threading.Thread(target=launch_gui, daemon=True).start()
    threading.Thread(target=check_loop, daemon=True).start()
    icon.run()
    return 0


def probe_path(path: str) -> dict:
    try:
        if os.path.isdir(path):
            # Permission test: directory enumeration, not a write test.
            with os.scandir(path) as entries:
                next(entries, None)
            return {'path': path, 'ok': True, 'message': 'Klasor okunabilir (yazma izni test edilmedi).'}
        return {'path': path, 'ok': False, 'message': 'Klasor bulunamadi veya baglanti yok.'}
    except OSError as exc:
        return {'path': path, 'ok': False, 'message': str(exc)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--tray-only', action='store_true')
    parser.add_argument('--discover', choices=('known', 'scan'))
    parser.add_argument('--probe', default='')
    parser.add_argument('--output', default='')
    parser.add_argument('--drive-list', action='store_true')
    parser.add_argument('--drive-map', default='')
    parser.add_argument('--drive-unmap', default='')
    parser.add_argument('--letter', default='')
    parser.add_argument('--persistent', action='store_true')
    args = parser.parse_args(argv)
    try:
        from agfo_installer import sanitize_process_env
        sanitize_process_env()
    except Exception as exc:  # temizlik basarisiz olsa da tepsi calismaya devam eder
        _log_error('Env sanitize: ' + repr(exc))
    if args.drive_list or args.drive_map or args.drive_unmap:
        if not args.output:
            return 2
        try:
            from agfo_drives import list_drives, map_drive, unmap_drive
            from agfo_network import write_result
            if args.drive_list:
                result = list_drives()
            elif args.drive_map:
                result = map_drive(args.drive_map, args.letter, args.persistent)
            else:
                result = unmap_drive(args.drive_unmap)
            write_result(result, args.output)
            return 0 if result.get('ok') else 8
        except Exception as exc:
            _log_error('Drive manager: ' + repr(exc))
            from agfo_network import write_result
            write_result({'ok': False, 'message': str(exc)}, args.output)
            return 8
    if args.discover or args.probe:
        if not args.output:
            return 2
        try:
            from agfo_network import discover, write_result
            payload = discover(args.discover) if args.discover else probe_path(args.probe)
            write_result(payload, args.output)
            return 0
        except Exception as exc:
            _log_error('Discovery/probe: ' + repr(exc))
            try:
                from agfo_network import write_result
                write_result({'items': [], 'warnings': [str(exc)], 'ok': False}, args.output)
            except Exception:
                pass
            return 7
    return start_tray(not args.tray_only)


if __name__ == '__main__':
    raise SystemExit(main())
