# -*- coding: utf-8 -*-
"""AGFO Mihenk - EXE oz-denetimi (`AGFO-Mihenk.exe --selftest [dosya]`).

Derleme sirasinda ve yayin oncesi calisir: tkinter/Tcl-Tk EXE'nin icinde gercekten var mi,
sqlite3 yaziyor mu, modullerin hepsi aciliyor mu. Sonuc cikis kodu (0 = tamam) ve istege
bagli bir dosyadir (pencereli EXE konsola yazamaz).
"""
import pathlib
import sys
import tempfile
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

        import mihenk_theme as theme

        import mihenk_core
        import mihenk_db as db
        import mihenk_app  # noqa: F401
        import mihenk_checklist  # noqa: F401
        import mihenk_export  # noqa: F401
        import mihenk_i18n
        import mihenk_legal  # noqa: F401
        import mihenk_parts  # noqa: F401
        import mihenk_reports  # noqa: F401
        import mihenk_seed  # noqa: F401
        import mihenk_update  # noqa: F401
        import mihenk_xlsx  # noqa: F401
        from mihenk_repo import AssetRepo

        # Veritabani gercekten yazilabiliyor mu: gecici dosyada tam bir tur.
        probe = pathlib.Path(tempfile.mkdtemp()) / 'selftest.sqlite3'
        conn = db.connect(probe)
        try:
            status = db.table_status(conn)
            if not all(status.values()):
                raise RuntimeError('eksik tablo: %s' % [k for k, ok in status.items() if not ok])
            AssetRepo.create(conn, {'code': 'SELFTEST-1', 'name': 'Oz denetim'})
            if AssetRepo.count(conn) != 1:
                raise RuntimeError('yazma denemesi basarisiz')
        finally:
            conn.close()

        # Modern gorunum pakete girdi mi. Modulu ice aktarmak yetmiyor:
        # ttkbootstrap cizimi kendi PNG varliklarini okur ve bunlar pakete
        # girmemisse hata ancak stiller kurulurken, yani kullanici uygulamayi
        # ilk actiginda cikar. Bu yuzden burada tema gercekten uygulaniyor.
        try:
            import ttkbootstrap
            tb = getattr(ttkbootstrap, '__version__', '?')
        except ImportError:
            tb = '-'

        probe = tkinter.Tk()
        probe.withdraw()
        try:
            theme.apply(probe, 'light', None, tb != '-')
            ui = 'modern' if theme.engine() == 'ttkbootstrap' else 'classic'
            drawing = theme.engine_status()
        finally:
            probe.destroy()
        if tb != '-' and ui != 'modern':
            # Bileşen kurulu ama cizim yapilamiyor: bozuk paket. Sessizce
            # klasige dusup gecer not vermek yerine derleme burada durur.
            raise RuntimeError('ttkbootstrap %s kurulu ama cizim uygulanamadi: %s' % (tb, drawing))

        # Ceviri EXE'ye girdi mi: sozluk bosalirsa uygulama sessizce Turkce
        # calisir, bu yuzden sayi burada acikca yaziliyor.
        langs = '%d/%s' % (len(mihenk_i18n.EN), ','.join(sorted(mihenk_i18n.LANGUAGES)))

        msg = 'OK %s tcl=%s sqlite=%s ui=%s ttkbootstrap=%s i18n=%s frozen=%s python=%s' % (
            mihenk_core.VERSION, tcl, __import__('sqlite3').sqlite_version, ui, tb, langs,
            bool(getattr(sys, 'frozen', False)), sys.version.split()[0])
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
