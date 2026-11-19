# -*- coding: utf-8 -*-
"""AGFO System Care — hazir calisma ortami baslaticisi (PyInstaller ile 'AGFO System Care.exe' olur).

Python, tkinter, ttkbootstrap, Pillow ve Paramiko bu exe'nin icindedir; uygulamanin kendisi (app.pyw ve modulleri)
exe'nin yaninda duz dosya olarak durur. Boylece uygulama ici guncelleme eskisi gibi yalnizca bu dosyalari degistirir,
kullanicinin Python kurmasi gerekmez.
"""
import os
import pathlib
import runpy
import sys

import runtime_deps  # noqa: F401  (derleme aninda uretilir: uygulamanin kullandigi standart/ucuncu taraf moduller gomulsun)


def _diag_dir():
    d = pathlib.Path(os.environ.get('LOCALAPPDATA') or pathlib.Path.home()) / 'AGFO' / 'SystemCare'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _report(text):
    """Penceresiz exe'de hata gorunmez: launcher-error.log'a (ve oz-denetim dosyasina) yazilir."""
    try:
        (_diag_dir() / 'launcher-error.log').write_text(text, encoding='utf-8')
        st = os.environ.get('AGFO_SELFTEST')
        if st:
            pathlib.Path(st).write_text('FAIL launcher\n' + text, encoding='utf-8')
    except OSError:
        pass


def main():
    if os.environ.get('AGFO_SELFTEST'):                          # oz-denetimde takilirsa tum is parcaciklarinin yigini dokulur
        import faulthandler
        main._hang = open(_diag_dir() / 'launcher-hang.log', 'w', encoding='utf-8')  # noqa: SIM115
        faulthandler.dump_traceback_later(150, exit=True, file=main._hang)
    base = pathlib.Path(sys.executable).resolve().parent
    script = base / 'app.pyw'
    args = sys.argv[1:]
    if args and args[0].lower().endswith('.pyw'):                   # yeniden baslatma: [exe, app.pyw]
        script = pathlib.Path(args.pop(0)).resolve()
    if not script.is_file():
        _report('app.pyw bulunamadi: %s' % script)
        if os.environ.get('AGFO_SELFTEST'):
            return 1
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, 'app.pyw bulunamadı:\n%s\n\nKurulumu yenileyin.' % script, 'AGFO System Care', 0x10)
        return 1
    sys.argv = [str(script)] + args
    sys.path.insert(0, str(script.parent))
    os.chdir(str(script.parent))
    try:
        runpy.run_path(str(script), run_name='__main__')
    except SystemExit:
        raise
    except BaseException:                                           # noqa: BLE001
        import traceback
        _report(traceback.format_exc())
        if not os.environ.get('AGFO_SELFTEST'):
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, 'AGFO System Care başlatılamadı. Ayrıntı:\n%s' % (_diag_dir() / 'launcher-error.log'),
                                             'AGFO System Care', 0x10)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
