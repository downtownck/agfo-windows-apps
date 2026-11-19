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


def main():
    base = pathlib.Path(sys.executable).resolve().parent
    script = base / 'app.pyw'
    args = sys.argv[1:]
    if args and args[0].lower().endswith('.pyw'):                   # yeniden baslatma: [exe, app.pyw]
        script = pathlib.Path(args.pop(0)).resolve()
    if not script.is_file():
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, 'app.pyw bulunamadı:\n%s\n\nKurulumu yenileyin.' % script, 'AGFO System Care', 0x10)
        return 1
    sys.argv = [str(script)] + args
    sys.path.insert(0, str(script.parent))
    os.chdir(str(script.parent))
    runpy.run_path(str(script), run_name='__main__')
    return 0


if __name__ == '__main__':
    sys.exit(main())
