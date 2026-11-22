# -*- coding: utf-8 -*-
"""AGFO Router Connect - EXE oz-denetimi (`AGFO-Router-Connect.exe --selftest [dosya]`).

Derleme sirasinda ve yayin oncesi calisir: tkinter/Tcl-Tk EXE'nin icinde gercekten var mi, modullerin hepsi aciliyor mu.
Sonuc cikis kodu (0 = tamam) ve istege bagli bir dosyadir (pencereli EXE konsola yazamaz)."""
import sys
import traceback


def run(argv) -> int:
    out = None
    if '--selftest' in argv:
        i = argv.index('--selftest')
        if i + 1 < len(argv):
            out = argv[i + 1]
    try:
        import tkinter
        from tkinter import ttk
        root = tkinter.Tk()
        tcl = root.tk.call('info', 'patchlevel')
        ttk.Style(root)
        root.destroy()
        import router_app  # noqa: F401
        import router_history  # noqa: F401
        import router_update  # noqa: F401
        import router_core
        msg = 'OK %s tcl=%s frozen=%s python=%s' % (router_core.VERSION, tcl, bool(getattr(sys, 'frozen', False)),
                                                    sys.version.split()[0])
        code = 0
    except BaseException:
        msg = 'FAIL\n' + traceback.format_exc()
        code = 1
    if out:
        try:
            with open(out, 'w', encoding='utf-8') as f:
                f.write(msg + '\n')
        except OSError:
            pass
    return code
