# -*- coding: utf-8 -*-
"""AGFO AI Editor - yazdiginiz metinlerin ICERIGINI yapay zekayla duzenleyen Windows metin editoru.

- Sekmeli belgeler: .txt / .md / .docx / .html acma-kaydetme, bul-degistir, geri al, otomatik kurtarma.
- AI paneli: Icerik (AI Manager sablonlari + icerik odakli eylemler, sonuc fark gorunumunde onayla uygulanir),
  Ceviri, Sohbet (belge baglamli), Denetim (BRCGS/IFS bulgu, uygunluk, DOF degerlendirme).
- Baglanti: WordPress'teki AGFO AI Manager (anahtarlar sunucuda) ve/veya dogrudan saglayici anahtari (DPAPI).
- GitHub'dan tek tikla guncelleme. AGFO koyu tema.
"""
from __future__ import annotations

import ctypes
import json
import os
import pathlib
import queue
import re
import sys
import threading
import traceback
import uuid

IS_WIN = sys.platform == 'win32'


def _dpi():
    if not IS_WIN:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


BASE = pathlib.Path(getattr(sys, '_MEIPASS', pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import agfo_editor_core as core  # noqa: E402
import agfo_ai_client as ai  # noqa: E402
import agfo_secrets as secrets  # noqa: E402
import agfo_editor_update as upd  # noqa: E402
import agfo_sources as srcs  # noqa: E402
import agfo_pdf  # noqa: E402
import agfo_richdoc as rdoc  # noqa: E402
import agfo_doctranslate as dtr  # noqa: E402
import agfo_trlive as trlive  # noqa: E402


def selftest(out_path: str) -> int:
    """Derlenmis EXE icin GUI'siz duman testi (CI): moduller, fark, docx gidis-donus."""
    res = {'version': core.VERSION, 'ok': False}
    try:
        import tempfile
        ops = core.word_diff('Bu bir deneme metni.', 'Bu daha iyi bir deneme metni.')
        tmp = os.path.join(tempfile.gettempdir(), 'agfo-editor-selftest.docx')
        core.write_docx(tmp, '# Başlık\n\nİlk paragraf.\n\n- madde')
        back = core.read_docx(tmp)
        os.unlink(tmp)
        enc = secrets.protect('deneme')
        res.update(ok=bool(ops) and 'Başlık' in back and secrets.unprotect(enc) == 'deneme',
                   providers=sorted(ai.PROVIDERS), actions=len(core.CONTENT_ACTIONS), docx=back)
        import tkinter  # noqa: F401
        res['tk'] = True
        import pypdf
        import agfo_sources as _s
        tp = os.path.join(tempfile.gettempdir(), 'agfo-editor-selftest.txt')
        with open(tp, 'w', encoding='utf-8') as fh:
            fh.write('Madde 4.11.2 Temizlik doğrulaması')
        ch, _mode = _s.select_context({'t': _s.extract(tp)}, 'temizlik')
        os.unlink(tp)
        res['pypdf'] = pypdf.__version__
        res['ok'] = res['ok'] and bool(ch)
        # 1.3: PDF duzenleyici - pdfium ile cizim + katmanli kaydetme (derlenmis EXE'de DLL'lerin varligini dogrular)
        import agfo_pdf as _p
        pp = os.path.join(tempfile.gettempdir(), 'agfo-editor-selftest.pdf')
        _p.write_simple_pdf(pp, [['Selftest'], ['Two']])
        pr = _p.PdfProject(pp)
        pr.rotate([0], 90)
        pr.add_overlay(0, {'type': 'text', 'rect': (20, 20, 300, 60), 'text': 'Türkçe ğüşİ', 'size': 12, 'whiteout': True})
        img = pr.render(0, 0.5)
        out = pp + '.out.pdf'
        pr.save(out)
        pr.close()
        res['pdf_render'] = list(img.size)
        res['pdf_saved'] = os.path.getsize(out)
        os.unlink(pp)
        os.unlink(out)
        res['ok'] = res['ok'] and img.size[0] > img.size[1] and res['pdf_saved'] > 0
        # 1.3.1: AES sifreli, kisitli PDF (BRCGS gibi) - cryptography paketinin EXE'de oldugunu dogrular
        ep = os.path.join(tempfile.gettempdir(), 'agfo-editor-selftest-aes.pdf')
        _p.write_simple_pdf(pp, [['AES selftest']])
        w = pypdf.PdfWriter(clone_from=pp)
        w.encrypt(user_password='', owner_password='o', algorithm='AES-256', permissions_flag=_p.P_PRINT | _p.P_ANNOTATE)
        with open(ep, 'wb') as fh:
            w.write(fh)
        pr = _p.PdfProject(ep)
        eimg = pr.render(0, 0.5)
        pr.add_overlay(0, {'type': 'highlight', 'rect': (20, 20, 200, 40)})
        pr.save(out)
        pr.close()
        r2 = pypdf.PdfReader(out)
        r2.decrypt('')
        res['pdf_aes'] = {'restrictions': len(pr.restrictions()), 'perms': int(r2.user_access_permissions) & _p.ALL_PERMS}
        for f_ in (pp, ep, out):
            os.unlink(f_)
        res['ok'] = res['ok'] and eimg.size[0] > 0 and r2.is_encrypted and res['pdf_aes']['perms'] == (_p.P_PRINT | _p.P_ANNOTATE)
        # 1.4: bicimli Word (resim, tablo, liste) gidis-donus + PDF metnini yerinde duzenleme + ceviri ayristirma
        import io as _io
        import agfo_richdoc as _r
        import agfo_doctranslate as _t
        from PIL import Image as _Image
        _b = _io.BytesIO()
        _Image.new('RGB', (40, 20), (200, 0, 0)).save(_b, 'PNG')
        blocks = [_r.para(text='Başlık', style='h1'), _r.para([_r.run('kalın', b=True), _r.run(' ğüşİ')]),
                  _r.para(text='madde', lst='number'), _r.image_block(_b.getvalue()),
                  {'t': 'table', 'rows': [[[_r.run('A')], [_r.run('B')]]]}]
        dp = os.path.join(tempfile.gettempdir(), 'agfo-editor-selftest.docx')
        with open(dp, 'wb') as fh:
            fh.write(_r.docx_bytes(blocks))
        back = _r.read_docx_blocks(dp)
        os.unlink(dp)
        res['rich_docx'] = [b['t'] for b in back]
        tr, _st = _t.translate_blocks(blocks, lambda text, ins: text.replace('Başlık', 'Title'), 'English')
        import agfo_pdf_edit as _e
        _p.write_simple_pdf(pp, [['Satir bir', 'Eski metin']])
        pr = _p.PdfProject(pp)
        x, y = _p.user_to_display(80, 752, pr.pages[0]['box'], 0)
        info = pr.find_text_line(0, x, y)
        pr.edit_text(0, info, 'Yeni metin ğüşİ')
        pr.save(out)
        pr.close()
        import agfo_pdf_layout  # noqa: F401  (1.4.6: duzeni koruyan PDF cevirisi)
        pr2 = _p.PdfProject(pp)
        lays = pr2.layouts()
        tdata, _tst = pr2.translated_pdf(lays, ['Line one', 'Old text'][:sum(len(x['paras']) for x in lays)] or ['Line one'])
        pr2.close()
        import pypdfium2 as _pdfium
        _doc = _pdfium.PdfDocument(out)
        _tp = _doc[0].get_textpage()
        edited = _tp.get_text_range(0, _tp.count_chars())
        _tp.close()
        _doc.close()
        _doc = _pdfium.PdfDocument(tdata)
        _tp = _doc[0].get_textpage()
        translated = _tp.get_text_range(0, _tp.count_chars())
        _tp.close()
        _doc.close()
        res['pdf_edit'] = {'font': os.path.basename(_e.pick_font('Helvetica') or ''), 'ok': 'Yeni metin ğüşİ' in edited and 'Eski' not in edited,
                           'layout_translate': 'Line one' in translated and 'Satir bir' not in translated,
                           # 1.4.12: yazi tipi alt kumesi (fontTools pakete girdi mi) - yoksa ceviri PDF'i MB'larca olur
                           'font_subset': len(_e.font_data(_e.pick_font('Helvetica'), 'abc')) < os.path.getsize(_e.pick_font('Helvetica'))}
        os.unlink(pp)
        os.unlink(out)
        res['ok'] = (res['ok'] and res['rich_docx'] == ['p', 'p', 'p', 'img', 'table'] and tr[0]['runs'][0]['text'] == 'Title'
                     and res['pdf_edit']['ok'] and res['pdf_edit']['layout_translate'] and res['pdf_edit']['font_subset'])
    except Exception as e:  # pragma: no cover
        res['error'] = repr(e)
    pathlib.Path(out_path).write_text(json.dumps(res, ensure_ascii=False), encoding='utf-8')
    return 0 if res['ok'] else 1


if len(sys.argv) >= 3 and sys.argv[1] == '--selftest':
    sys.exit(selftest(sys.argv[2]))


def apply_update_main(target: str, pid: int) -> int:
    """Yeni EXE guncelleyici kipinde: eski surum kapaninca kendini hedefe kopyalar ve hedefi acar."""
    import tkinter as tk
    from tkinter import messagebox, ttk
    upd.log_line('Updater %s running from %s, target %s' % (core.VERSION, sys.executable, target))
    root = tk.Tk()
    root.title('AGFO AI Editor')
    root.configure(bg='#12243b')
    root.geometry('420x130')
    root.resizable(False, False)
    tk.Label(root, text='AGFO AI Editor %s kuruluyor…' % core.VERSION, fg='#ecf3ff', bg='#12243b',
             font=('Segoe UI', 11, 'bold')).pack(pady=(20, 8))
    bar = ttk.Progressbar(root, mode='indeterminate', length=340)
    bar.pack()
    bar.start(12)
    q = queue.Queue()

    def work():
        try:
            if not upd.wait_for_pid(pid, 90):
                raise OSError('Eski sürüm 90 saniyede kapanmadı.')
            upd.replace_target(sys.executable, target)
            upd.launch(target)
            upd.log_line('Update applied: %s' % target)
            q.put(None)
        except Exception as e:  # noqa: BLE001 - kullaniciya gosterilir
            upd.log_line('Update failed: %r' % e)
            q.put(e)
    threading.Thread(target=work, daemon=True).start()
    result = {}

    def poll():
        try:
            result['err'] = q.get_nowait()
        except queue.Empty:
            root.after(150, poll)
            return
        bar.stop()
        if result['err'] is not None:
            messagebox.showerror('Güncelleme', 'Güncelleme uygulanamadı: %s\n\nYeni sürüm şu dosyada, doğrudan açabilirsiniz:\n%s'
                                 % (result['err'], sys.executable), parent=root)
        root.destroy()
    root.after(150, poll)
    root.mainloop()
    return 0 if result.get('err') is None else 1


if len(sys.argv) >= 3 and sys.argv[1] == '--apply-update':
    _pid = 0
    if '--wait-pid' in sys.argv:
        try:
            _pid = int(sys.argv[sys.argv.index('--wait-pid') + 1])
        except (ValueError, IndexError):
            _pid = 0
    sys.exit(apply_update_main(sys.argv[2], _pid))

_dpi()
import tkinter as tk  # noqa: E402
import tkinter.font as tkfont  # noqa: E402
from tkinter import colorchooser, filedialog, messagebox, ttk  # noqa: E402

import agfo_richtext as rtext  # noqa: E402

BG, PANEL, PANEL2, FG, MUTED, ACCENT = '#0a1425', '#12243b', '#192e48', '#ecf3ff', '#a5b6ce', '#49b3ef'
WARN, OK_C, BAD_C = '#e2b356', '#6fd39b', '#ff8a80'
EDIT_BG, SEL_BG, PRIMARY = '#0e1b2e', '#285475', '#1f6fa3'
POLL_MS = 80
AUTOSAVE_MS = 45000
UPDATE_CHECK_MS = 30 * 60 * 1000   # 1.4.15: acik kaldikca 30 dk'da bir sessiz guncelleme denetimi
FILETYPES = [('Desteklenen belgeler', '*.txt *.md *.markdown *.docx *.html *.htm *.pdf *.xlsx *.xlsm *.pptx *.eml *.csv'),
             ('Metin', '*.txt'), ('Markdown', '*.md *.markdown'), ('Word belgesi', '*.docx'), ('PDF (metin olarak)', '*.pdf'),
             ('Excel / PowerPoint (metin olarak)', '*.xlsx *.xlsm *.pptx'), ('HTML', '*.html *.htm'), ('Tüm dosyalar', '*.*')]
SAVE_FILETYPES = [('Word belgesi', '*.docx'), ('Markdown', '*.md'), ('Metin', '*.txt'), ('HTML', '*.html')]
TEXT_COLORS = (('Otomatik', None), ('Kırmızı', 'C00000'), ('Koyu mavi', '1F4E79'), ('Mavi', '2E75B6'), ('Yeşil', '2E7D32'),
               ('Turuncu', 'C55A11'), ('Mor', '7030A0'), ('Gri', '595959'))
READ_ONLY_KINDS = ('.xlsx', '.xlsm', '.pptx', '.eml')


class Doc:
    def __init__(self, frame, text, title, path=None, docfile=None):
        self.id = uuid.uuid4().hex
        self.frame, self.text, self.title = frame, text, title
        self.path = path
        self.docfile = docfile or core.DocFile()
        self.docx_warned = False

    @property
    def rich(self) -> bool:
        return self.text.rich

    @property
    def dirty(self) -> bool:
        return self.text.undo.dirty()

    @property
    def saved_text(self):
        return None

    @saved_text.setter
    def saved_text(self, _value):
        """Eski arayuz: belgenin su anki hali 'kaydedilmis' sayilir."""
        self.text.undo.mark_saved()


class App(tk.Tk):
    def __init__(self, files=(), smoke=False):
        super().__init__()
        self.smoke = smoke
        self.settings = core.load_settings()
        self.q = queue.Queue()
        self.jobs = {}
        self.docs = []
        self.pdf_views = {}           # 1.3: PDF duzenleyici sekmeleri (cerceve -> PdfView)
        self.colors = {'BG': BG, 'PANEL': PANEL, 'PANEL2': PANEL2, 'FG': FG, 'MUTED': MUTED, 'ACCENT': ACCENT,
                       'EDIT_BG': EDIT_BG, 'SEL_BG': SEL_BG}
        self.chat_messages = []
        self.manager_info = None
        self.update_result = None
        self.title('AGFO AI Editor %s' % core.VERSION)
        self.configure(bg=BG)
        try:
            self.scale = max(1.0, self.winfo_fpixels('1i') / 96.0)
        except tk.TclError:
            self.scale = 1.0
        self.geometry('%dx%d' % (int(1360 * min(self.scale, 1.25)), int(860 * min(self.scale, 1.25))))
        self.minsize(980, 640)
        self._set_icon()
        self._style()
        self._build()
        self._bind_keys()
        for f in files:
            self.open_path(f)
        if not self.docs:
            self.new_doc()
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        self._timers = {}
        self._timers['poll'] = self.after(POLL_MS, self._poll)
        self._timers['autosave'] = self.after(AUTOSAVE_MS, self._autosave)
        if not smoke:
            self.after(600, self._offer_recovery)
            self.after(900, self._refresh_connection_label)
            self.after(1200, self._restore_sources)
            self._timers['update'] = self.after(5000, self._auto_update_tick)   # 1.4.15: acilista + 30 dk'da bir
            self.after(1500, self._offer_install)

    # ------------------------------------------------------------------ gorunum
    def _set_icon(self):
        ico = BASE / 'assets' / 'agfo-ai-editor.ico'
        try:
            if IS_WIN and ico.exists():
                self.iconbitmap(default=str(ico))
        except tk.TclError:
            pass

    def _style(self):
        s = ttk.Style(self)
        s.theme_use('clam')
        s.configure('.', background=PANEL, foreground=FG, fieldbackground=PANEL2, font=('Segoe UI', 10), bordercolor='#2d4a6c',
                    lightcolor=PANEL2, darkcolor=PANEL2)
        s.configure('TNotebook', background=BG, borderwidth=0, tabmargins=(0, 4, 0, 0))
        s.configure('TNotebook.Tab', background=PANEL2, foreground=MUTED, padding=(11, 7), font=('Segoe UI', 10), borderwidth=0)
        s.map('TNotebook.Tab', background=[('selected', SEL_BG)], foreground=[('selected', '#ffffff')])
        s.configure('Panel.TNotebook', background=PANEL)
        s.configure('TFrame', background=PANEL)
        s.configure('Bg.TFrame', background=BG)
        s.configure('TLabel', background=PANEL, foreground=FG)
        s.configure('Muted.TLabel', background=PANEL, foreground=MUTED, font=('Segoe UI', 9))
        s.configure('TCheckbutton', background=PANEL, foreground=FG, indicatorbackground=EDIT_BG, indicatorforeground=FG)
        s.map('TCheckbutton', background=[('active', PANEL)], indicatorbackground=[('selected', SEL_BG)])
        s.configure('TRadiobutton', background=PANEL, foreground=FG, indicatorbackground=EDIT_BG, indicatorforeground=FG)
        s.map('TRadiobutton', background=[('active', PANEL)], indicatorbackground=[('selected', SEL_BG)])
        s.configure('TCombobox', fieldbackground=PANEL2, background=PANEL2, foreground=FG, arrowcolor=FG,
                    selectbackground=PANEL2, selectforeground=FG)
        s.map('TCombobox', fieldbackground=[('readonly', PANEL2)], foreground=[('readonly', FG)],
              selectbackground=[('readonly', PANEL2)], selectforeground=[('readonly', FG)])
        self.option_add('*TCombobox*Listbox.background', PANEL2)
        self.option_add('*TCombobox*Listbox.foreground', FG)
        self.option_add('*TCombobox*Listbox.selectBackground', SEL_BG)
        self.option_add('*TCombobox*Listbox.font', ('Segoe UI', 10))
        s.configure('TEntry', fieldbackground=PANEL2, foreground=FG, insertcolor=FG)
        s.configure('TSpinbox', fieldbackground=PANEL2, foreground=FG, arrowcolor=FG, insertcolor=FG)
        s.configure('Vertical.TScrollbar', background=PANEL2, troughcolor=EDIT_BG, arrowcolor=MUTED, bordercolor=EDIT_BG,
                    lightcolor=PANEL2, darkcolor=PANEL2, gripcount=0, relief='flat')
        s.map('Vertical.TScrollbar', background=[('active', SEL_BG), ('pressed', SEL_BG)])
        s.configure('Horizontal.TProgressbar', background=ACCENT, troughcolor=PANEL2, bordercolor=PANEL2)
        s.configure('Treeview', background=EDIT_BG, fieldbackground=EDIT_BG, foreground=FG, rowheight=int(22 * self.scale), borderwidth=0)
        s.configure('Treeview.Heading', background=PANEL2, foreground=FG, font=('Segoe UI', 9, 'bold'), relief='flat')
        s.map('Treeview', background=[('selected', SEL_BG)], foreground=[('selected', '#ffffff')])
        s.map('Treeview.Heading', background=[('active', SEL_BG)])
        s.configure('TPanedwindow', background=BG)
        s.configure('Sash', background=BG, sashthickness=6)

    def btn(self, parent, text, cmd, kind='normal', side='left', **kw):
        colors = {'normal': SEL_BG, 'primary': PRIMARY, 'ghost': PANEL2, 'go': '#1f6a4a', 'danger': '#6b2f2f'}
        b = tk.Button(parent, text=text, command=cmd, bg=colors[kind], fg='#ffffff', activebackground=ACCENT, activeforeground='#06111f',
                      relief='flat', cursor='hand2', padx=kw.pop('padx', 11), pady=kw.pop('pady', 5), font=kw.pop('font', ('Segoe UI', 9, 'bold')),
                      disabledforeground='#7f8ea3', bd=0, highlightthickness=0, **kw)
        if side:
            b.pack(side=side, padx=(0, 6), pady=2)
        return b

    def lbl(self, parent, text, muted=False, bg=PANEL, **kw):
        return tk.Label(parent, text=text, fg=MUTED if muted else FG, bg=bg, font=kw.pop('font', ('Segoe UI', 9)),
                        justify='left', anchor='w', **kw)

    def _build(self):
        top = tk.Frame(self, bg=BG)
        top.pack(fill='x', padx=18, pady=(12, 4))
        left = tk.Frame(top, bg=BG)
        left.pack(side='left')
        tk.Label(left, text='AGFO  /  SUPERTOOLS', fg=ACCENT, bg=BG, font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        tk.Label(left, text='AI Editor', fg=FG, bg=BG, font=('Segoe UI', 20, 'bold')).pack(anchor='w')
        tk.Label(left, text='Yazdıklarınızın içeriğini yapay zekâyla düzenleyin · AGFO AI Manager bağlantılı',
                 fg=MUTED, bg=BG, font=('Segoe UI', 9)).pack(anchor='w')
        right = tk.Frame(top, bg=BG)
        right.pack(side='right', anchor='e')
        self.conn_var = tk.StringVar(value='Bağlantı denetleniyor…')
        self.conn_lbl = tk.Label(right, textvariable=self.conn_var, fg=MUTED, bg=PANEL, font=('Segoe UI', 9), padx=10, pady=5)
        self.conn_lbl.pack(side='right')
        self.update_btn = tk.Button(right, text='', command=self.do_update, bg='#1f6a4a', fg='#ffffff', relief='flat', bd=0,
                                    font=('Segoe UI', 9, 'bold'), padx=10, pady=5, cursor='hand2', activebackground=ACCENT,
                                    activeforeground='#ffffff')
        self._update_shown = None      # 1.4.15: dugmesi gosterilen surum (ayni surum icin tekrar bildirim yok)

        bar = tk.Frame(self, bg=PANEL, padx=10, pady=6)
        bar.pack(fill='x', padx=18, pady=(6, 0))
        self.btn(bar, 'Yeni', self.new_doc, 'ghost')
        self.btn(bar, 'Aç', self.open_dialog, 'ghost')
        self.btn(bar, 'Kaydet', self.save, 'ghost')
        self.btn(bar, 'Farklı kaydet', self.save_as, 'ghost')
        tk.Frame(bar, bg='#2d4a6c', width=1, height=24).pack(side='left', padx=6)
        self.btn(bar, '↶ Geri al', lambda: self._text_cmd('edit_undo'), 'ghost')
        self.btn(bar, '↷ Yinele', lambda: self._text_cmd('edit_redo'), 'ghost')
        self.btn(bar, 'Bul / Değiştir', self.toggle_find, 'ghost')
        tk.Frame(bar, bg='#2d4a6c', width=1, height=24).pack(side='left', padx=6)
        self.btn(bar, 'A−', lambda: self.zoom(-1), 'ghost')
        self.btn(bar, 'A+', lambda: self.zoom(1), 'ghost')
        self.btn(bar, 'Ayarlar', self.open_settings, 'normal', side='right')
        self.panel_btn = self.btn(bar, 'AI paneli ⇥', self.toggle_ai_panel, 'ghost', side='right')
        self.more_btn = self.btn(bar, 'Diğer ▾', self.show_more_menu, 'ghost', side='right')

        self.fmt_bar = tk.Frame(self, bg=PANEL, padx=10, pady=4)
        self._build_fmt_bar(self.fmt_bar)
        self.fmt_bar.pack(fill='x', padx=18, pady=(2, 0))

        self.find_bar = tk.Frame(self, bg=PANEL2, padx=10, pady=6)
        self._build_find(self.find_bar)

        st = tk.Frame(self, bg=PANEL, padx=10, pady=4)
        st.pack(fill='x', side='bottom', padx=18, pady=(0, 10))
        self.status_var = tk.StringVar(value='')
        tk.Label(st, textvariable=self.status_var, fg=MUTED, bg=PANEL, font=('Segoe UI', 9)).pack(side='left')
        self.cancel_btn = tk.Button(st, text='Durdur', command=self.cancel_jobs, bg='#6b2f2f', fg='#ffffff', relief='flat', bd=0,
                                    font=('Segoe UI', 8, 'bold'), padx=8, pady=1, cursor='hand2')
        self.busy = ttk.Progressbar(st, mode='indeterminate', length=140)
        self.ai_var = tk.StringVar(value='')
        tk.Label(st, textvariable=self.ai_var, fg=FG, bg=PANEL, font=('Segoe UI', 9)).pack(side='right', padx=(8, 0))

        self.paned = ttk.PanedWindow(self, orient='horizontal')
        self.paned.pack(fill='both', expand=True, padx=18, pady=8)
        self.nb = ttk.Notebook(self.paned)
        self.nb.bind('<<NotebookTabChanged>>', lambda e: (self._update_status(), self._sync_fmt_bar()))
        self.nb.bind('<Button-2>', self._middle_close)
        self.paned.add(self.nb, weight=3)
        side = ttk.Frame(self.paned, padding=(10, 8))
        self.paned.add(side, weight=2)
        self.side_panel = side
        self._build_ai_panel(side)

    # ------------------------------------------------------------------ bicim cubugu (1.4)
    def _build_fmt_bar(self, f):
        self.style_var = tk.StringVar(value=rdoc.STYLE_LABELS['normal'])
        self._style_keys = {v: k for k, v in rdoc.STYLE_LABELS.items()}
        cb = ttk.Combobox(f, textvariable=self.style_var, values=list(rdoc.STYLE_LABELS.values()), width=13, state='readonly')
        cb.pack(side='left', padx=(0, 8))
        cb.bind('<<ComboboxSelected>>', lambda e: self._fmt('style', self._style_keys.get(self.style_var.get(), 'normal')))
        self.fmt_btns = {}

        def fb(key, text, cmd, font=('Segoe UI', 9, 'bold'), tip=None):
            b = self.btn(f, text, cmd, 'ghost', padx=7, pady=3, font=font)
            self.fmt_btns[key] = b
            return b
        fb('b', 'K', lambda: self._fmt('b'), ('Segoe UI', 10, 'bold'))
        fb('i', 'İ', lambda: self._fmt('i'), ('Segoe UI', 10, 'italic'))
        fb('u', 'A', lambda: self._fmt('u'), ('Segoe UI', 10, 'underline'))
        fb('color', 'Renk ▾', self._color_menu)
        tk.Frame(f, bg='#2d4a6c', width=1, height=22).pack(side='left', padx=5)
        fb('bullet', '• Liste', lambda: self._fmt('list', 'bullet'))
        fb('number', '1. Liste', lambda: self._fmt('list', 'number'))
        fb('outdent', '⇤', lambda: self._fmt('level', -1))
        fb('indent', '⇥', lambda: self._fmt('level', 1))
        tk.Frame(f, bg='#2d4a6c', width=1, height=22).pack(side='left', padx=5)
        fb('left', 'Sola', lambda: self._fmt('align', 'left'), ('Segoe UI', 8, 'bold'))
        fb('center', 'Ortala', lambda: self._fmt('align', 'center'), ('Segoe UI', 8, 'bold'))
        fb('right', 'Sağa', lambda: self._fmt('align', 'right'), ('Segoe UI', 8, 'bold'))
        tk.Frame(f, bg='#2d4a6c', width=1, height=22).pack(side='left', padx=5)
        fb('image', '🖼 Resim', self.insert_image)
        fb('table', '▦ Tablo', self.insert_table)
        self.page_btn = self.btn(f, '📄 Sayfa görünümü', self.toggle_page_view, 'ghost', side='right', padx=8, pady=3)
        self.btn(f, '🌐 Belgeyi çevir', self.translate_document, 'ghost', side='right', padx=8, pady=3)
        self.fmt_hint = tk.Label(f, text='', fg=MUTED, bg=PANEL, font=('Segoe UI', 8))
        self.fmt_hint.pack(side='left', padx=8)

    def _fmt(self, what, value=None):
        d = self.cur()
        if not d:
            return
        t = d.text
        if not t.rich:
            if not messagebox.askyesno('Biçimlendirme', 'Bu belge düz metin (.txt). Biçimlendirme için belge Word gibi düzenlenecek; '
                                       'kaydederken .docx seçerseniz biçimler korunur.\n\nDevam edilsin mi?', parent=self):
                return
            t.enable_rich()
            self._place_text(d)
        if what in ('b', 'i', 'u'):
            t.toggle_char(what)
        elif what == 'color':
            t.toggle_char('color', value)
        elif what == 'style':
            t.set_style(value)
        elif what == 'list':
            t.toggle_list(value)
        elif what == 'level':
            t.change_level(value)
        elif what == 'align':
            t.set_align(value)
        t.focus_set()
        self._sync_fmt_bar()

    def _color_menu(self):
        m = tk.Menu(self, tearoff=0)
        for label, val in TEXT_COLORS:
            m.add_command(label=label, command=lambda v=val: self._fmt('color', v))
        m.add_separator()

        def other():
            c = colorchooser.askcolor(parent=self, title='Yazı rengi')
            if c and c[1]:
                self._fmt('color', c[1].lstrip('#').upper())
        m.add_command(label='Diğer renk…', command=other)
        b = self.fmt_btns['color']
        m.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())

    def _sync_fmt_bar(self):
        d = self.cur()
        bar = getattr(self, 'fmt_bar', None)
        if bar is None:
            return
        if not d:
            if bar.winfo_manager():
                bar.pack_forget()
            return
        if not bar.winfo_manager():
            bar.pack(fill='x', padx=18, pady=(2, 0), before=self.paned)
        t = d.text
        try:
            fmt = t.current_format()
        except tk.TclError:
            return
        self.style_var.set(rdoc.STYLE_LABELS.get(fmt.get('style', 'normal'), rdoc.STYLE_LABELS['normal']))
        on = {'b': fmt.get('b'), 'i': fmt.get('i'), 'u': fmt.get('u'), 'bullet': fmt.get('list') == 'bullet',
              'number': fmt.get('list') == 'number', 'left': not fmt.get('align'), 'center': fmt.get('align') == 'center',
              'right': fmt.get('align') == 'right'}
        for k, b in self.fmt_btns.items():
            if k in on:
                b.configure(bg=SEL_BG if on[k] and t.rich else PANEL2)
        self.page_btn.configure(bg=SEL_BG if t.page_mode else PANEL2)
        self.fmt_hint.configure(text='' if t.rich else 'Düz metin (.txt)')

    def toggle_page_view(self):
        on = not self.settings.get('page_view', True)
        self.settings['page_view'] = on
        core.save_settings(self.settings)
        for d in self.docs:
            if d.text.rich:
                d.text.set_page_mode(on)
                self._place_text(d)
        self._sync_fmt_bar()
        self.flash('Sayfa görünümü açık: A4 sayfa genişliği ve kenar boşlukları.' if on else 'Sayfa görünümü kapalı (koyu tema).')

    def _place_text(self, d):
        t, desk = d.text, d.desk
        try:
            avail = desk.winfo_width()
        except tk.TclError:
            return
        if t.page_mode:
            w = int(t.px(rdoc.PAGE_W_PT))
            full = int(t.px(rdoc.MARGIN_PT * 0.9))
            if avail > w + 24:
                if int(t.cget('padx')) != full:
                    t.configure(padx=full)
                t.place_forget()
                t.place(relx=0.5, y=10, anchor='n', width=w, relheight=1, height=-10)
                return
            narrow = int(min(full, max(14, avail * 0.05)))
            if int(t.cget('padx')) != narrow:
                t.configure(padx=narrow)
        t.place_forget()
        t.place(x=0, y=0, relwidth=1, relheight=1)

    def insert_image(self):
        d = self.cur()
        if not d:
            return
        path = filedialog.askopenfilename(parent=self, title='Resim ekle', filetypes=[('Resim', '*.png *.jpg *.jpeg *.gif *.bmp')])
        if not path:
            return
        try:
            with open(path, 'rb') as fh:
                data = fh.read()
            blk = rdoc.image_block(data)
        except (OSError, ValueError) as e:
            messagebox.showerror('Resim', 'Resim eklenemedi: %s' % e, parent=self)
            return
        if not d.text.rich:
            d.text.enable_rich()
        d.text.insert_image('insert', blk)
        d.text.focus_set()

    def insert_table(self):
        d = self.cur()
        if not d:
            return
        win = tk.Toplevel(self)
        win.title('Tablo ekle')
        win.configure(bg=PANEL, padx=14, pady=12)
        win.transient(self)
        rows, cols = tk.IntVar(value=3), tk.IntVar(value=3)
        for r, (lab, var) in enumerate((('Satır', rows), ('Sütun', cols))):
            self.lbl(win, lab).grid(row=r, column=0, sticky='w', pady=3)
            ttk.Spinbox(win, from_=1, to=40, textvariable=var, width=6).grid(row=r, column=1, padx=8, pady=3)

        def ok():
            try:
                rr, cc = max(1, min(40, rows.get())), max(1, min(12, cols.get()))
            except tk.TclError:
                return
            win.destroy()
            if not d.text.rich:
                d.text.enable_rich()
            d.text.insert_table(rr, cc)
            d.text.focus_set()
        self.btn(win, 'Ekle', ok, 'primary', side=None).grid(row=2, column=0, columnspan=2, pady=(10, 0))
        win.bind('<Return>', lambda e: ok())
        win.bind('<Escape>', lambda e: win.destroy())
        self.table_dialog = win
        return win

    def toggle_ai_panel(self):
        """AI panelini gizle / goster (PDF sayfa gorunumu ve okuma icin genis alan)."""
        if str(self.side_panel) in self.paned.panes():
            self.paned.forget(self.side_panel)
            self.panel_btn.configure(text='AI paneli ⇤')
        else:
            self.paned.add(self.side_panel, weight=2)
            self.panel_btn.configure(text='AI paneli ⇥')

    def _build_find(self, f):
        self.find_var, self.repl_var = tk.StringVar(), tk.StringVar()
        self.case_var = tk.BooleanVar(value=False)
        self.lbl(f, 'Bul', bg=PANEL2).pack(side='left')
        e = ttk.Entry(f, textvariable=self.find_var, width=28)
        e.pack(side='left', padx=(4, 10))
        e.bind('<Return>', lambda ev: self.find_next())
        self.find_entry = e
        self.lbl(f, 'Değiştir', bg=PANEL2).pack(side='left')
        ttk.Entry(f, textvariable=self.repl_var, width=28).pack(side='left', padx=(4, 10))
        ttk.Checkbutton(f, text='Büyük/küçük harf', variable=self.case_var, style='TCheckbutton').pack(side='left', padx=(0, 8))
        for t, c in (('Sonraki', self.find_next), ('Önceki', lambda: self.find_next(back=True)), ('Değiştir', self.replace_one),
                     ('Tümünü değiştir', self.replace_all)):
            self.btn(f, t, c, 'normal')
        self.btn(f, '✕', self.toggle_find, 'ghost')
        self.find_info = self.lbl(f, '', muted=True, bg=PANEL2)
        self.find_info.pack(side='left', padx=8)

    # ------------------------------------------------------------------ AI paneli
    def _build_ai_panel(self, side):
        head = tk.Frame(side, bg=PANEL)
        head.pack(fill='x')
        tk.Label(head, text='Yapay zekâ', fg=FG, bg=PANEL, font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.scope_var = tk.StringVar(value='selection')
        sc = tk.Frame(side, bg=PANEL)
        sc.pack(fill='x', pady=(6, 4))
        self.lbl(sc, 'Kapsam:', muted=True).pack(side='left')
        ttk.Radiobutton(sc, text='Seçili metin (yoksa paragraf)', value='selection', variable=self.scope_var).pack(side='left', padx=6)
        ttk.Radiobutton(sc, text='Tüm belge', value='all', variable=self.scope_var).pack(side='left')
        self.ai_nb = ttk.Notebook(side, style='Panel.TNotebook')
        self.ai_nb.pack(fill='both', expand=True, pady=(4, 0))
        self._tab_content(self._ai_tab('İçerik'))
        self._tab_translate(self._ai_tab('Çeviri'))
        self._tab_chat(self._ai_tab('Sohbet'))
        self._tab_audit(self._ai_tab('Denetim'))
        self._tab_sources(self._ai_tab('Kaynaklar'))

    def _ai_tab(self, title):
        f = ttk.Frame(self.ai_nb, padding=(10, 10))
        self.ai_nb.add(f, text=title)
        return f

    def _combo(self, parent, var, values, width=22, readonly=True):
        c = ttk.Combobox(parent, textvariable=var, values=values, width=width, state='readonly' if readonly else 'normal')
        return c

    def _tab_content(self, f):
        self.actions = core.merge_catalog(None)
        self.action_var = tk.StringVar()
        row = tk.Frame(f, bg=PANEL)
        row.pack(fill='x')
        self.lbl(row, 'Eylem', muted=True).pack(anchor='w')
        self.action_combo = self._combo(row, self.action_var, [a[1] for a in self.actions], width=44)
        self.action_combo.pack(fill='x', pady=(2, 4))
        self.action_combo.bind('<<ComboboxSelected>>', lambda e: self._action_changed())
        self.action_desc = self.lbl(f, '', muted=True, wraplength=int(380 * self.scale))
        self.action_desc.pack(fill='x', pady=(0, 8))
        go = tk.Frame(f, bg=PANEL)
        go.pack(fill='x', pady=(0, 8))
        self.btn(go, 'AI ile düzenle   (Ctrl+E)', self.run_selected_action, 'primary', padx=14, pady=7)
        quick = tk.Frame(f, bg=PANEL)
        quick.pack(fill='x', pady=(0, 8))
        self.lbl(quick, 'Hızlı:', muted=True).pack(side='left', padx=(0, 6))
        for key, t in (('content_strengthen', 'Güçlendir'), ('content_flow', 'Akış'), ('proofread', 'Düzelt'),
                       ('shorten', 'Kısalt'), ('critique', 'Eleştir')):
            self.btn(quick, t, lambda k=key: self.run_action_key(k), 'ghost', padx=8)
        grid = tk.Frame(f, bg=PANEL)
        grid.pack(fill='x')
        self.lang_var = tk.StringVar(value=self.settings['language'])
        self.tone_var = tk.StringVar(value=self.settings['tone'])
        self.aud_var = tk.StringVar(value=self.settings['audience'])
        self.len_var = tk.StringVar(value=self.settings['length'])
        for i, (t, var, vals) in enumerate((('Dil', self.lang_var, core.LANGUAGES), ('Ton', self.tone_var, core.TONES),
                                            ('Okuyucu', self.aud_var, core.AUDIENCES), ('Uzunluk', self.len_var, core.LENGTHS))):
            self.lbl(grid, t, muted=True).grid(row=i // 2 * 2, column=i % 2, sticky='w', padx=(0, 8))
            self._combo(grid, var, vals, width=20, readonly=False).grid(row=i // 2 * 2 + 1, column=i % 2, sticky='we', padx=(0, 8), pady=(0, 6))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        self.preserve_var = tk.BooleanVar(value=self.settings.get('preserve_facts', True))
        self.brief_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text='Bilgileri, sayıları ve terimleri koru', variable=self.preserve_var).pack(anchor='w')
        ttk.Checkbutton(f, text='Metni yalnızca brif olarak kullan (yeniden yaz)', variable=self.brief_var).pack(anchor='w', pady=(0, 6))
        self.lbl(f, 'Ek talimat (isteğe bağlı)', muted=True).pack(anchor='w')
        self.extra_txt = self._textbox(f, height=3)
        self.extra_txt.pack(fill='x', pady=(2, 8))
        self.lbl(f, 'Sonuç önce fark görünümünde gösterilir; onaylamadan belgeye yazılmaz (Ctrl+Z ile geri alınır).',
                 muted=True, wraplength=int(380 * self.scale)).pack(fill='x', pady=(6, 0))
        last = self.settings.get('last_action')
        idx = next((i for i, a in enumerate(self.actions) if a[0] == last), 0)
        self.action_combo.current(idx)
        self._action_changed()

    def _textbox(self, parent, height=4, **kw):
        t = tk.Text(parent, height=height, wrap='word', bg=EDIT_BG, fg=FG, insertbackground=FG, relief='flat', bd=0,
                    highlightthickness=1, highlightbackground='#2d4a6c', highlightcolor=ACCENT, font=('Segoe UI', 10),
                    selectbackground=SEL_BG, selectforeground='#ffffff', padx=6, pady=4, undo=True, **kw)
        return t

    def _action_changed(self):
        i = self.action_combo.current()
        if 0 <= i < len(self.actions):
            self.action_desc.configure(text=self.actions[i][2])

    def _tab_translate(self, f):
        self.tr_model_var = tk.StringVar(value='Çeviri modeli: bağlantı denetleniyor…')
        tk.Label(f, textvariable=self.tr_model_var, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold'), anchor='w', justify='left',
                 wraplength=int(380 * self.scale)).pack(fill='x', pady=(0, 4))
        # 1.4.8: is basina ceviri modeli ve ayni anda gonderilen istek sayisi
        mrow = tk.Frame(f, bg=PANEL)
        mrow.pack(fill='x', pady=(0, 6))
        self.tr_choice_var = tk.StringVar()
        self.tr_choices = []                # [(etiket, secim_sozlugu|None)]
        self.tr_choice_combo = ttk.Combobox(mrow, textvariable=self.tr_choice_var, state='readonly', width=42,
                                            postcommand=self._tr_models_lazy)
        self.tr_choice_combo.pack(side='left', fill='x', expand=True)
        self.tr_choice_combo.bind('<<ComboboxSelected>>', lambda e: self._tr_choice_selected())
        self.btn(mrow, '↻', lambda: self.load_translation_models(force=True), 'ghost', padx=8).pack(side='left', padx=(4, 0))
        self._set_tr_choices([])
        self.tr_lang = tk.StringVar(value='English')
        lrow = tk.Frame(f, bg=PANEL)
        lrow.pack(fill='x', pady=(0, 6))
        self.lbl(lrow, 'Hedef dil', muted=True).pack(side='left')
        self._combo(lrow, self.tr_lang, core.LANGUAGES, width=16, readonly=False).pack(side='left', padx=(6, 12))
        self.lbl(lrow, 'Aynı anda', muted=True).pack(side='left')
        self.tr_workers_var = tk.IntVar(value=self.translation_workers())
        ttk.Spinbox(lrow, from_=1, to=6, width=3, textvariable=self.tr_workers_var, state='readonly',
                    command=self._tr_workers_changed).pack(side='left', padx=(6, 0))
        self.lbl(lrow, 'istek', muted=True).pack(side='left', padx=(4, 0))
        self.tr_mode = tk.StringVar(value='replace')
        rrow = tk.Frame(f, bg=PANEL)
        rrow.pack(fill='x', pady=(0, 6))
        ttk.Radiobutton(rrow, text='Yerine koy', value='replace', variable=self.tr_mode).pack(side='left')
        ttk.Radiobutton(rrow, text='Altına ekle (iki dilli)', value='below', variable=self.tr_mode).pack(side='left', padx=(8, 0))
        ttk.Radiobutton(rrow, text='Yeni sekme', value='newtab', variable=self.tr_mode).pack(side='left', padx=(8, 0))
        self.lbl(f, 'Terminoloji / ek not (isteğe bağlı)', muted=True).pack(anchor='w')
        self.tr_extra = self._textbox(f, height=2)
        self.tr_extra.pack(fill='x', pady=(2, 8))
        self.btn(f, 'Seçimi / paragrafı çevir', self.run_translate, 'primary', side=None, padx=14, pady=7).pack(anchor='w')
        box = tk.Frame(f, bg=PANEL2, padx=10, pady=8)
        box.pack(fill='x', pady=(14, 0))
        tk.Label(box, text='Tüm belgeyi çevir (biçim korunur)', fg=FG, bg=PANEL2, font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        self.lbl(box, 'Başlıklar, listeler, tablolar ve resimler yerinde kalır; açık PDF de çevrilebilir.', muted=True, bg=PANEL2,
                 wraplength=int(360 * self.scale)).pack(anchor='w', pady=(0, 4))
        self.doc_tr_out = tk.StringVar(value=self.settings.get('doc_translate_output', 'both'))
        for val, lab in (('pdf', 'PDF: sayfa düzeni korunur (yalnız PDF)'), ('newtab', 'Biçimli yeni belge'),
                         ('compare', 'Yan yana (özgün | çeviri)'), ('both', 'İkisi de (PDF\'de: çevrilmiş PDF + yan yana)')):
            tk.Radiobutton(box, text=lab, value=val, variable=self.doc_tr_out, bg=PANEL2, fg=FG, selectcolor=EDIT_BG,
                           activebackground=PANEL2, activeforeground=FG, font=('Segoe UI', 9), anchor='w',
                           highlightthickness=0, bd=0).pack(anchor='w')
        self.btn(box, '🌐 Belgeyi çevir', self.translate_document, 'primary', side=None, padx=14, pady=6).pack(anchor='w', pady=(6, 0))
        self.lbl(f, 'Model seçilmezse AI Manager\'daki "Çeviri" yönlendirmesi kullanılır. Hızlı modeller ve 3–4 eşzamanlı istek '
                    'uzun belgelerde süreyi belirgin kısaltır; çevrilen paragraflar belgede renkle gösterilir.',
                 muted=True, wraplength=int(380 * self.scale)).pack(fill='x', pady=(10, 0))

    def _tab_chat(self, f):
        self.chat_view = tk.Text(f, wrap='word', bg=EDIT_BG, fg=FG, relief='flat', bd=0, highlightthickness=0, font=('Segoe UI', 10),
                                 padx=8, pady=6, state='disabled', height=12, selectbackground=SEL_BG)
        self.chat_view.tag_configure('u', foreground=ACCENT, font=('Segoe UI', 9, 'bold'), spacing1=8)
        self.chat_view.tag_configure('a', foreground=OK_C, font=('Segoe UI', 9, 'bold'), spacing1=8)
        self.chat_view.tag_configure('e', foreground=BAD_C)
        self.chat_view.tag_configure('body', foreground=FG, lmargin1=4, lmargin2=4, spacing3=4)
        self.chat_view.pack(fill='both', expand=True)
        self.chat_ctx = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text='Belgeyi bağlam olarak gönder (seçim varsa yalnız seçim)', variable=self.chat_ctx).pack(anchor='w', pady=(6, 2))
        self.chat_in = self._textbox(f, height=3)
        self.chat_in.pack(fill='x', pady=(2, 6))
        self.chat_in.bind('<Control-Return>', lambda e: (self.send_chat(), 'break')[1])
        r = tk.Frame(f, bg=PANEL)
        r.pack(fill='x')
        self.btn(r, 'Gönder  (Ctrl+Enter)', self.send_chat, 'primary')
        self.btn(r, 'Yanıtı imlece ekle', self.insert_last_answer, 'ghost')
        self.btn(r, 'Temizle', self.clear_chat, 'ghost')

    def _tab_audit(self, f):
        self.std_var = tk.StringVar(value=core.AUDIT_STANDARDS[0])
        self.lbl(f, 'Standart / şema', muted=True).pack(anchor='w')
        self._combo(f, self.std_var, core.AUDIT_STANDARDS, width=34, readonly=False).pack(anchor='w', pady=(2, 6))
        self.lbl(f, 'Madde no (isteğe bağlı, metni uydurulmaz)', muted=True).pack(anchor='w')
        self.clause_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.clause_var, width=20).pack(anchor='w', pady=(2, 8))
        self.audit_var = tk.StringVar(value=core.AUDIT_ACTIONS[0][0])
        for key, label, _ in core.AUDIT_ACTIONS:
            ttk.Radiobutton(f, text=label, value=key, variable=self.audit_var).pack(anchor='w', pady=1)
        self.btn(f, 'Denetim diliyle düzenle', self.run_audit, 'primary', side=None, padx=14, pady=7).pack(anchor='w', pady=(10, 0))
        self.lbl(f, 'Kayıt numarası, tarih, ölçüm veya madde metni uydurulmaz; yalnız metninizdeki kanıt kullanılır.',
                 muted=True, wraplength=int(380 * self.scale)).pack(fill='x', pady=(10, 0))

    # ------------------------------------------------------------------ kaynaklar (1.2)
    def _tab_sources(self, f):
        self.src_docs = {}            # doc_id -> belge (agfo_sources.extract)
        self.src_answers = {}         # etiket haritalari (atif baglantilari)
        self.src_threads = {}         # 1.2.1: kapsam (secili belgeler) -> ayri sohbet {'messages', 'log'}
        self.src_scope = 'all'
        top = tk.Frame(f, bg=PANEL)
        top.pack(fill='x')
        self.btn(top, '+ Belge ekle', self.add_sources, 'normal')
        self.btn(top, 'Göster', self.show_selected_source, 'ghost')
        self.btn(top, 'Kaldır', self.remove_sources, 'ghost')
        self.src_tree = ttk.Treeview(f, columns=('loc', 'size'), height=3, selectmode='extended')
        self.src_tree.heading('#0', text='Belge')
        self.src_tree.heading('loc', text='Bölüm')
        self.src_tree.heading('size', text='Metin')
        self.src_tree.column('#0', width=int(220 * self.scale), stretch=True)
        self.src_tree.column('loc', width=int(60 * self.scale), anchor='center', stretch=False)
        self.src_tree.column('size', width=int(70 * self.scale), anchor='e', stretch=False)
        self.src_tree.tag_configure('warn', foreground=WARN)
        self.src_tree.pack(fill='x', pady=(4, 2))
        self.src_tree.bind('<Double-1>', lambda e: self.show_selected_source())
        self.src_tree.bind('<<TreeviewSelect>>', lambda e: self._switch_scope())
        self.src_info = self.lbl(f, 'PDF, Word, Excel, PowerPoint, metin ve e-posta dosyaları eklenebilir.', muted=True,
                                 wraplength=int(390 * self.scale))
        self.src_info.pack(fill='x')
        self.mask_var = tk.BooleanVar(value=self.settings.get('mask_sources', True))
        ttk.Checkbutton(f, text='Göndermeden önce e-posta, telefon, kimlik no ve IBAN maskele', variable=self.mask_var,
                        command=self._save_mask).pack(anchor='w', pady=(2, 6))
        self.scope_lbl = tk.Label(f, text='', fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold'), anchor='w', justify='left',
                                  wraplength=int(390 * self.scale))
        self.scope_lbl.pack(fill='x')
        self.lbl(f, 'Soru (listeden belge seçerseniz yalnız o belgeyle, seçmezseniz tümüyle sohbet edilir)', muted=True,
                 wraplength=int(390 * self.scale)).pack(anchor='w')
        self.src_q = self._textbox(f, height=2)
        self.src_q.pack(fill='x', pady=(2, 4))
        self.src_q.bind('<Control-Return>', lambda e: (self.ask_sources(), 'break')[1])
        r = tk.Frame(f, bg=PANEL)
        r.pack(fill='x')
        self.btn(r, 'Sor  (Ctrl+Enter)', self.ask_sources, 'primary')
        self.btn(r, 'Yanıtı imlece ekle', self.insert_source_answer, 'ghost')
        self.btn(r, 'Sohbeti temizle', self.clear_source_thread, 'ghost')
        bottom = tk.Frame(f, bg=PANEL)
        bottom.pack(side='bottom', fill='x', pady=(6, 0))
        g = tk.Frame(bottom, bg=PANEL)
        g.pack(fill='x')
        self.lbl(g, 'Belgelerden içerik üret', muted=True).grid(row=0, column=0, columnspan=2, sticky='w')
        self.create_var = tk.StringVar(value=srcs.CREATE_TYPES[0][1])
        self._combo(g, self.create_var, [c[1] for c in srcs.CREATE_TYPES], width=24).grid(row=1, column=0, sticky='we', padx=(0, 6))
        self.btn(g, 'Üret (yeni sekme)', self.create_from_sources, 'primary', side=None).grid(row=1, column=1, sticky='e')
        g.columnconfigure(0, weight=1)
        self.create_topic = tk.StringVar()
        e = ttk.Entry(bottom, textvariable=self.create_topic)
        e.pack(fill='x', pady=(4, 0))
        self._placeholder(e, self.create_topic, 'Konu / amaç (isteğe bağlı) — ör. "KOBİ\'ler için alerjen yönetimi"')
        self.src_view = tk.Text(f, wrap='word', bg=EDIT_BG, fg=FG, relief='flat', bd=0, highlightthickness=0, font=('Segoe UI', 10),
                                padx=8, pady=6, state='disabled', height=8, selectbackground=SEL_BG, cursor='arrow')
        self.src_view.tag_configure('q', foreground=ACCENT, font=('Segoe UI', 9, 'bold'), spacing1=8)
        self.src_view.tag_configure('body', foreground=FG, spacing3=4)
        self.src_view.tag_configure('meta', foreground=MUTED, font=('Segoe UI', 8))
        self.src_view.tag_configure('err', foreground=BAD_C)
        self.src_view.tag_configure('cite', foreground=ACCENT, underline=True)
        self.src_view.tag_bind('cite', '<Enter>', lambda e: self.src_view.configure(cursor='hand2'))
        self.src_view.tag_bind('cite', '<Leave>', lambda e: self.src_view.configure(cursor='arrow'))
        self.src_view.pack(fill='both', expand=True, pady=(6, 0))
        self.src_last_answer = ''

    def _placeholder(self, entry, var, text):
        def on_in(_e):
            if var.get() == text:
                var.set('')
                entry.configure(foreground=FG)
        def on_out(_e):
            if not var.get():
                var.set(text)
                entry.configure(foreground=MUTED)
        entry.bind('<FocusIn>', on_in)
        entry.bind('<FocusOut>', on_out)
        on_out(None)
        entry._placeholder = text

    def _save_mask(self):
        self.settings['mask_sources'] = bool(self.mask_var.get())
        core.save_settings(self.settings)

    def _src_view_append(self, text, tag='body'):
        v = self.src_view
        v.configure(state='normal')
        v.insert('end', text, tag)
        v.configure(state='disabled')
        v.see('end')

    def _restore_sources(self):
        paths = [p for p in self.settings.get('sources', []) if isinstance(p, str) and os.path.isfile(p)]
        if paths:
            self._load_sources(paths, quiet=True)

    def add_sources(self):
        paths = filedialog.askopenfilenames(parent=self, title='Kaynak belge ekle', filetypes=srcs.FILETYPES)
        if paths:
            self._load_sources(list(paths))

    def _load_sources(self, paths, quiet=False):
        known = {os.path.normcase(d['path']) for d in self.src_docs.values()}
        paths = [p for p in paths if os.path.normcase(os.path.abspath(p)) not in known]
        if not paths:
            return

        def work():
            out = []
            for p in paths:
                try:
                    out.append((p, srcs.load(p), None))
                except (srcs.SourceError, OSError) as e:
                    out.append((p, None, str(e)))
            return out

        def done(ok, res):
            if not ok:
                messagebox.showerror('Kaynaklar', res, parent=self)
                return
            errs = []
            for p, doc, err in res:
                if err:
                    errs.append('%s: %s' % (os.path.basename(p), err))
                    continue
                did = uuid.uuid4().hex[:10]
                self.src_docs[did] = doc
                n_units = len(doc['units'])
                warn = bool(doc.get('empty_pages')) or doc['chars'] == 0
                self.src_tree.insert('', 'end', iid=did, text=('⚠ ' if warn else '') + doc['name'], values=(n_units, '{:,}'.format(doc['chars']).replace(',', '.')),
                                     tags=('warn',) if warn else ())
            self._sync_source_settings()
            self._source_summary()
            self._switch_scope()
            if errs and not quiet:
                messagebox.showwarning('Kaynaklar', 'Okunamayan belgeler:\n\n' + '\n'.join(errs), parent=self)
        self._start_job('Belgeler okunuyor (%d)' % len(paths), work, done)

    def _sync_source_settings(self):
        self.settings['sources'] = [d['path'] for d in self.src_docs.values()][:50]
        core.save_settings(self.settings)

    def _source_summary(self):
        docs = list(self.src_docs.values())
        if not docs:
            self.src_info.configure(text='PDF, Word, Excel, PowerPoint, metin ve e-posta dosyaları eklenebilir.', fg=MUTED)
            return
        total = sum(d['chars'] for d in docs)
        empty = sum(len(d.get('empty_pages') or []) for d in docs)
        txt = '%d belge · %s karakter metin' % (len(docs), '{:,}'.format(total).replace(',', '.'))
        if empty:
            txt += ' · ⚠ %d sayfada metin yok (taranmış olabilir; yazı tanıma 1.3 sürümünde)' % empty
        self.src_info.configure(text=txt, fg=WARN if empty else MUTED)

    def remove_sources(self):
        for iid in self.src_tree.selection():
            self.src_docs.pop(iid, None)
            self.src_tree.delete(iid)
            for k in [k for k in self.src_threads if iid in k.split('|')]:
                self.src_threads.pop(k, None)
        self._sync_source_settings()
        self._source_summary()
        self._switch_scope()

    def show_selected_source(self):
        sel = self.src_tree.selection()
        if sel and sel[0] in self.src_docs:
            doc = self.src_docs[sel[0]]
            body = '\n\n'.join('— %s —\n%s' % (u['loc'], u['text'] or '(bu bölümde metin yok)') for u in doc['units'])
            self.new_doc(body, '📄 ' + doc['name'])

    def open_citation(self, chunk):
        doc = next((d for d in self.src_docs.values() if d['name'] == chunk['name']), None)
        unit_text = chunk['text']
        if doc:
            unit = next((u for u in doc['units'] if u['loc'] == chunk['loc']), None)
            if unit:
                unit_text = unit['text']
        d = self.new_doc(unit_text, '📄 %s — %s' % (chunk['name'], chunk['loc']))
        t = d.text
        pos = t.search(chunk['text'][:60], '1.0', stopindex='end')
        if pos:
            t.tag_add('ai_new', pos, '%s+%dc' % (pos, len(chunk['text'])))
            t.see(pos)
        d.saved_text = unit_text            # yalniz goruntuleme: kaydet sorusu cikmasin
        self.nb.tab(d.frame, text=self._tab_title(d))

    # --- kapsam: secili belgeler ya da tumu; her kapsamin kendi sohbeti var
    def _scope_ids(self):
        sel = [i for i in self.src_tree.selection() if i in self.src_docs]
        return sel or list(self.src_docs)

    def _scope_key(self, ids=None):
        ids = self._scope_ids() if ids is None else ids
        return 'all' if set(ids) == set(self.src_docs) and len(ids) != 1 else '|'.join(sorted(ids))

    def _scope_title(self, ids):
        if not ids:
            return 'Sohbet: belge yok'
        if len(ids) == 1:
            return 'Sohbet: %s' % self.src_docs[ids[0]]['name']
        if set(ids) == set(self.src_docs):
            return 'Sohbet: tüm belgeler (%d)' % len(ids)
        return 'Sohbet: %d seçili belge — %s' % (len(ids), ', '.join(self.src_docs[i]['name'] for i in ids)[:120])

    def _thread(self, key=None):
        key = key or self._scope_key()
        return self.src_threads.setdefault(key, {'messages': [], 'log': []})

    def _switch_scope(self):
        ids = self._scope_ids()
        key = self._scope_key(ids)
        self.src_scope = key
        self.scope_lbl.configure(text=self._scope_title(ids))
        self._render_thread(key)

    def _render_thread(self, key):
        v = self.src_view
        v.configure(state='normal')
        v.delete('1.0', 'end')
        v.configure(state='disabled')
        for entry in self._thread(key)['log']:
            kind = entry[0]
            if kind == 'a':
                self._render_answer(entry[1], entry[2], record=False)
            else:
                self._src_view_append(entry[1], {'q': 'q', 'meta': 'meta', 'err': 'err'}[kind])

    def _log(self, key, kind, text, labels=None):
        th = self._thread(key)
        th['log'].append((kind, text, labels) if kind == 'a' else (kind, text))
        if key == self.src_scope:
            if kind == 'a':
                self._render_answer(text, labels, record=False)
            else:
                self._src_view_append(text, {'q': 'q', 'meta': 'meta', 'err': 'err'}[kind])

    def clear_source_thread(self):
        self.src_threads.pop(self._scope_key(), None)
        self._render_thread(self._scope_key())

    def _source_context(self, query, ids):
        if not self.src_docs:
            messagebox.showinfo('Kaynaklar', 'Önce "+ Belge ekle" ile en az bir belge ekleyin.', parent=self)
            return None
        docs = {i: self.src_docs[i] for i in ids}
        if not any(d['chars'] for d in docs.values()):
            messagebox.showwarning('Kaynaklar', 'Seçili belgelerde okunabilir metin yok (taranmış PDF olabilir). '
                                   'Yazı tanıma (OCR) sonraki sürümde gelecek.', parent=self)
            return None
        chunks, mode = srcs.select_context(docs, query)
        context, labels = srcs.build_context(chunks, mask=bool(self.mask_var.get()))
        return context, labels, mode, chunks

    def ask_sources(self):
        q = self.src_q.get('1.0', 'end-1c').strip()
        if not q:
            return
        ids = self._scope_ids()
        key = self._scope_key(ids)
        th = self._thread(key)
        # onceki soruyu da aramaya kat: "peki ya 5. bolumde?" gibi devam sorulari icin
        prev_q = next((m['content'] for m in reversed(th['messages']) if m['role'] == 'user'), '')
        prep = self._source_context(q + ' ' + prev_q[:200], ids)
        if not prep:
            return
        context, labels, mode, chunks = prep
        self.src_q.delete('1.0', 'end')
        self._log(key, 'q', 'Soru: %s\n' % q)
        history = th['messages'][-8:]
        msgs = history + [{'role': 'user', 'content': srcs.ask_message(q, self.lang_var.get() or 'Türkçe')}]

        def done(ok, res):
            if not ok:
                self._log(key, 'err', res + '\n')
                return
            th['messages'].append({'role': 'user', 'content': q})
            th['messages'].append({'role': 'assistant', 'content': srcs.strip_citations(res['text'])})
            self._log(key, 'a', res['text'], labels)
            self._log(key, 'meta', '%s · %d parça (%s) · %s\n' % (res.get('via', ''), len(chunks),
                      'belgenin tamamı' if mode == 'tam' else 'yerel arama', res.get('model', '')))
        self._start_job('Belgelere soruluyor', ai.run_with_fallback, done, self.backends(), 'chat', msgs, context, 2500)

    def _render_answer(self, text, labels, record=True):
        key = uuid.uuid4().hex[:6]
        self.src_answers[key] = labels
        self.src_last_answer = srcs.strip_citations(text)
        v = self.src_view
        v.configure(state='normal')
        pos = 0
        for m in re.finditer(r'\[(K\d+(?:\s*[,;]\s*K\d+)*)\]', text):
            v.insert('end', text[pos:m.start()], 'body')
            for i, lab in enumerate(re.split(r'\s*[,;]\s*', m.group(1))):
                c = (labels or {}).get(lab)
                if not c:
                    continue
                tag = 'cite_%s_%s' % (key, lab)
                v.tag_configure(tag)
                v.tag_bind(tag, '<Button-1>', lambda e, ch=c: self.open_citation(ch))
                v.insert('end', ('' if i == 0 else ' ') + '[%s]' % srcs.cite_label(c), ('cite', tag))
            pos = m.end()
        v.insert('end', text[pos:].rstrip() + '\n', 'body')
        v.configure(state='disabled')
        v.see('end')

    def insert_source_answer(self):
        d = self.cur()
        if d and self.src_last_answer:
            self._insert_text(d, self.src_last_answer)

    def create_from_sources(self):
        label = self.create_var.get()
        ctype = next((c for c in srcs.CREATE_TYPES if c[1] == label), srcs.CREATE_TYPES[0])
        topic = self.create_topic.get()
        if topic.startswith('Konu / amaç'):
            topic = ''
        if ctype[0] == 'custom' and not topic.strip():
            messagebox.showinfo('İçerik üret', 'Özel içerik için ne üretileceğini "Konu / amaç" kutusuna yazın.', parent=self)
            return
        ids = self._scope_ids()
        key = self._scope_key(ids)
        prep = self._source_context(topic or label, ids)
        if not prep:
            return
        context, labels, mode, chunks = prep
        msg = srcs.create_message(ctype[0], topic, self.lang_var.get() or 'Türkçe', self.aud_var.get(),
                                  self.extra_txt.get('1.0', 'end-1c').strip())
        self._log(key, 'q', 'Üretiliyor: %s%s\n' % (ctype[1], (' — ' + topic) if topic else ''))

        def done(ok, res):
            if not ok:
                self._log(key, 'err', res + '\n')
                return
            text = srcs.append_source_list(core.clean_model_text(res['text']), labels)
            title = (topic or ctype[1])[:40]
            d = self.new_doc(text, '✨ ' + title)
            self._highlight(d)
            note = '%s · %s · %d parça → yeni sekme "%s"' % (res.get('via', ''), res.get('model', ''), len(chunks), title)
            if res.get('truncated'):
                note += ' · ⚠ çıktı sınırında kesildi (AI Manager 17.6+ daha uzun çıktıya izin verir)'
            self._log(key, 'meta', note + '\n')
        self._start_job('İçerik üretiliyor: %s' % ctype[1], ai.run_with_fallback, done, self.backends(), 'chat',
                        [{'role': 'user', 'content': msg}], context, ctype[3])

    # ------------------------------------------------------------------ belgeler
    def _editor_font(self):
        return (self.settings.get('font_family') or 'Segoe UI', int(self.settings.get('font_size', 12)))

    def _rich_font(self):
        fam = self.settings.get('rich_font')
        if not fam:
            fams = {f.lower() for f in tkfont.families(self)}
            fam = next((f for f in ('Calibri', 'Segoe UI', 'Carlito', 'DejaVu Sans') if f.lower() in fams), 'Segoe UI')
        return fam, int(self.settings.get('rich_size', 11))

    def new_doc(self, text='', title=None, path=None, docfile=None, blocks=None, rich=None):
        """rich=None: .txt disindaki her belge bicimli (Word gibi). text bicimli belgede Markdown olarak okunur."""
        if rich is None:
            rich = not (docfile is not None and docfile.kind == 'txt')
        frame = tk.Frame(self.nb, bg=EDIT_BG)
        ys = ttk.Scrollbar(frame, orient='vertical')
        ys.pack(side='right', fill='y')
        desk = tk.Frame(frame, bg=rtext.PAGE_COLORS['desk'], highlightthickness=0, bd=0, width=int(820 * self.scale),
                        height=int(500 * self.scale))
        desk.pack(side='left', fill='both', expand=True)
        fam, size = self._rich_font() if rich else self._editor_font()
        t = rtext.RichText(desk, self.colors, family=fam, size=size, rich=rich,
                           wrap='word' if self.settings.get('wrap', True) or rich else 'none', bg=EDIT_BG, fg=FG,
                           insertbackground=ACCENT, insertwidth=2, relief='flat', bd=0, highlightthickness=0,
                           font=(fam, size), padx=int(28 * self.scale), pady=int(18 * self.scale), spacing1=2, spacing3=6,
                           selectbackground=SEL_BG, selectforeground='#ffffff', inactiveselectbackground='#1d3b57')
        t.configure(yscrollcommand=ys.set)
        ys.configure(command=t.yview)
        base = tkfont.Font(family=self._editor_font()[0], size=self._editor_font()[1])
        t.tag_configure('md_h', foreground='#ffffff', font=(base.actual('family'), int(self._editor_font()[1] * 1.25), 'bold'))
        t.tag_configure('md_mark', foreground=MUTED)
        t.tag_configure('md_li', foreground=FG, lmargin2=int(18 * self.scale))
        t.tag_configure('found', background='#5a4a1c')
        t.tag_configure('ai_new', background='#173a2a')
        t.tag_configure('trwork', background='#4a3f12')
        t.tag_configure('trdone', background='#173a2a')
        if rich:
            t.set_font(zoom=float(self.settings.get('page_zoom', 1.0)))
            t.set_page_mode(bool(self.settings.get('page_view', True)))
        if blocks:
            t.load_blocks(blocks)
        elif text and rich:
            t.load_blocks(rdoc.markdown_to_blocks(text))
        elif text:
            t.undo.recording = False
            t.insert('1.0', text)
            t.undo.recording = True
            t.undo.reset()
        t.mark_set('insert', '1.0')
        t.edit_modified(False)
        title = title or 'Adsız %d' % (len(self.docs) + 1)
        doc = Doc(frame, t, title, path, docfile)
        doc.desk = desk
        if not path and (text or blocks):
            t.undo.saved = -1                       # yeni icerik: kaydedilmemis say
        self.docs.append(doc)
        self.nb.add(frame, text=self._tab_title(doc))
        self.nb.select(frame)
        desk.bind('<Configure>', lambda e, dd=doc: self._place_text(dd))
        self._place_text(doc)
        for ev in ('<KeyRelease>', '<ButtonRelease-1>'):
            t.bind(ev, lambda e: (self._update_status(), self._sync_fmt_bar()), add='+')
        t.bind('<KeyRelease>', lambda e, dd=doc: self._schedule_highlight(dd), add='+')
        self._highlight(doc)
        t.bind('<<Modified>>', lambda e, d=doc: self._on_modified(d))
        t.on_change = lambda d=doc: self._doc_changed(d)
        t.bind('<Button-3>', self._context_menu)
        t.focus_set()
        self._update_status()
        self._sync_fmt_bar()
        return doc

    def _doc_changed(self, d):
        try:
            self.nb.tab(d.frame, text=self._tab_title(d))
        except tk.TclError:
            pass

    def _schedule_highlight(self, doc):
        if getattr(doc, '_hl', None):
            try:
                self.after_cancel(doc._hl)
            except (tk.TclError, ValueError):
                pass
        doc._hl = self.after(350, lambda: self._highlight(doc))

    def _highlight(self, doc):
        """Hafif Markdown vurgusu: '#' basliklari kalin, liste satirlari girintili. Metni degistirmez."""
        doc._hl = None
        if doc not in self.docs or doc.text.rich:
            return
        t = doc.text
        if int(t.index('end-1c').split('.')[0]) > 20000:
            return
        for tag in ('md_h', 'md_mark', 'md_li'):
            t.tag_remove(tag, '1.0', 'end')
        for i, line in enumerate(t.get('1.0', 'end-1c').split('\n'), start=1):
            m = core._HEAD_RX.match(line)
            if m:
                t.tag_add('md_h', '%d.0' % i, '%d.end' % i)
                t.tag_add('md_mark', '%d.0' % i, '%d.%d' % (i, len(m.group(1)) + 1))
            elif core._LIST_RX.match(line):
                t.tag_add('md_li', '%d.0' % i, '%d.end' % i)

    def _tab_title(self, doc):
        return ('● ' if doc.dirty else '') + doc.title

    def _on_modified(self, doc):
        if doc.text.edit_modified():
            doc.text.edit_modified(False)
            try:
                self.nb.tab(doc.frame, text=self._tab_title(doc))
            except tk.TclError:
                pass
            self._update_status()

    def cur(self):
        try:
            frame = self.nametowidget(self.nb.select())
        except (KeyError, tk.TclError):
            return None
        return next((d for d in self.docs if d.frame is frame), None)

    def _text_cmd(self, name):
        d = self.cur()
        if d:
            try:
                getattr(d.text, name)()
            except tk.TclError:
                pass

    def open_dialog(self):
        paths = filedialog.askopenfilenames(parent=self, title='Belge aç', filetypes=FILETYPES)
        for p in paths:
            self.open_path(p)

    def open_path(self, path):
        path = os.path.abspath(path)
        for d in self.docs:
            if d.path and os.path.normcase(d.path) == os.path.normcase(path):
                self.nb.select(d.frame)
                return d
        if os.path.splitext(path)[1].lower() == '.pdf':
            return self.open_pdf(path)
        if os.path.splitext(path)[1].lower() in READ_ONLY_KINDS:
            return self.open_as_text(path)
        blocks = None
        try:
            kind = core.detect_kind(path)
            if kind == 'docx':
                blocks = rdoc.read_docx_blocks(path)
                text, docfile = '', core.DocFile(path, 'docx')
            elif kind == 'html':
                with open(path, 'rb') as fh:
                    raw = core.decode_bytes(fh.read())
                blocks = rdoc.html_to_blocks(raw[0])
                text, docfile = '', core.DocFile(path, 'html')
            else:
                text, docfile = core.read_document(path)
                if kind == 'md':
                    blocks = rdoc.markdown_to_blocks(text, base_dir=os.path.dirname(path)) or [rdoc.para()]
        except Exception as e:
            messagebox.showerror('Açılamadı', '%s\n\n%s' % (path, e), parent=self)
            return None
        cur = self.cur()
        if cur and not cur.path and not cur.dirty and not cur.text.get('1.0', 'end-1c').strip():
            self.close_doc(cur, ask=False)
        d = self.new_doc(text, os.path.basename(path), path, docfile, blocks=blocks)
        core.add_recent(self.settings, path)
        core.save_settings(self.settings)
        if docfile.kind == 'docx':
            n_img = sum(1 for b in blocks or [] if b['t'] == 'img')
            n_tbl = sum(1 for b in blocks or [] if b['t'] == 'table')
            self.flash('Word belgesi biçimleriyle açıldı (%d resim, %d tablo). Üst/alt bilgi, dipnot ve yorumlar bu editörde gösterilmez.'
                       % (n_img, n_tbl), 9000)
        return d

    # ------------------------------------------------------------------ PDF duzenleyici (1.3)
    def open_pdf(self, path):
        import agfo_pdf_view
        path = os.path.abspath(path)
        for v in self.pdf_views.values():
            if os.path.normcase(v.pr.path) == os.path.normcase(path):
                self.nb.select(v)
                return v
        try:
            pr = agfo_pdf.PdfProject(path)
        except Exception as e:
            messagebox.showerror('PDF açılamadı', '%s\n\n%s' % (path, e), parent=self)
            return None
        cur = self.cur()
        if cur and not cur.path and not cur.dirty and not cur.text.get('1.0', 'end-1c').strip():
            self.close_doc(cur, ask=False)
        v = agfo_pdf_view.PdfView(self, self.nb, pr)
        self.pdf_views[v] = v
        self.nb.add(v, text='📄 ' + os.path.basename(path))
        self.nb.select(v)
        core.add_recent(self.settings, path)
        core.save_settings(self.settings)
        if os.path.normcase(path) not in {os.path.normcase(x['path']) for x in self.src_docs.values()}:
            self._load_sources([path], quiet=True)          # sohbet ve icerik uretimi icin Kaynaklar'a da ekle
        self.flash('PDF düzenleyicide açıldı. Kaydet her zaman yeni dosya önerir; özgün dosya korunur.', 8000)
        return v

    def cur_pdf(self):
        try:
            w = self.nametowidget(self.nb.select())
        except (KeyError, tk.TclError):
            return None
        return self.pdf_views.get(w)

    def _pdf_changed(self, v):
        try:
            self.nb.tab(v, text=('● ' if v.pr.dirty else '') + '📄 ' + os.path.basename(v.pr.path))
        except tk.TclError:
            pass
        self._update_status()

    def close_pdf(self, v, ask=True):
        if ask and v.pr.dirty:
            self.nb.select(v)
            ans = messagebox.askyesnocancel('Kaydedilmemiş PDF değişikliği', '"%s" üzerindeki değişiklikler kaydedilsin mi?'
                                            % os.path.basename(v.pr.path), parent=self)
            if ans is None:
                return False
            if ans and not v.save():
                return False
        v.pr.close()
        self.nb.forget(v)
        self.pdf_views.pop(v, None)
        v.destroy()
        if not self.docs and not self.pdf_views and ask:
            self.new_doc()
        return True

    def open_as_text(self, path):
        """1.2.1: PDF / Excel / PowerPoint / e-posta metin olarak acilir (sayfa/slayt basliklariyla).
        Ozgun dosyanin uzerine asla yazilmaz: Kaydet, .docx/.md/.txt olarak 'Farkli kaydet' sorar."""
        for d in self.docs:
            if getattr(d, 'origin', None) and os.path.normcase(d.origin) == os.path.normcase(path):
                self.nb.select(d.frame)
                return d

        def work():
            return srcs.load(path)

        def done(ok, doc):
            if not ok:
                messagebox.showerror('Açılamadı', '%s\n\n%s' % (path, doc), parent=self)
                return
            if not doc['chars']:
                messagebox.showwarning('Metin yok', '%s içinde okunabilir metin bulunamadı (taranmış belge olabilir). '
                                       'Yazı tanıma (OCR) sonraki sürümde gelecek.' % doc['name'], parent=self)
                return
            parts = []
            for u in doc['units']:
                body = u['text'].strip() or '(bu bölümde metin yok — taranmış sayfa olabilir)'
                parts.append('## %s\n\n%s' % (u['loc'], body))
            cur = self.cur()
            if cur and not cur.path and not cur.dirty and not cur.text.get('1.0', 'end-1c').strip():
                self.close_doc(cur, ask=False)
            text = '\n\n'.join(parts)
            d = self.new_doc(text, doc['name'] + ' (metin)')
            d.origin = path
            d.saved_text = text                     # degisiklik yapilana kadar 'kaydedilmedi' sayilmaz
            self.nb.tab(d.frame, text=self._tab_title(d))
            core.add_recent(self.settings, path)
            if os.path.normcase(path) not in {os.path.normcase(x['path']) for x in self.src_docs.values()}:
                did = uuid.uuid4().hex[:10]
                self.src_docs[did] = doc
                self.src_tree.insert('', 'end', iid=did, text=doc['name'], values=(len(doc['units']),
                                     '{:,}'.format(doc['chars']).replace(',', '.')))
                self._sync_source_settings()
                self._source_summary()
            core.save_settings(self.settings)
            empty = len(doc.get('empty_pages') or [])
            self.flash('%s metin olarak açıldı (%d bölüm%s). Kaynaklar sekmesine de eklendi; özgün dosya değiştirilmez.'
                       % (doc['name'], len(doc['units']), ', %d sayfa metinsiz' % empty if empty else ''), 9000)
        self._start_job('Açılıyor: %s' % os.path.basename(path), work, done)
        return None

    def save(self, doc=None):
        if doc is None and self.cur_pdf():
            return self.cur_pdf().save()
        d = doc or self.cur()
        if not d:
            return False
        if not d.path:
            return self.save_as(d)
        if d.docfile.kind == 'docx' and not d.docx_warned:
            ans = messagebox.askyesnocancel(
                'Word belgesi',
                'Başlıklar, kalın/italik, renkler, listeler, tablolar ve resimler korunur. Özgün dosyadaki üst/alt bilgi, dipnot, '
                'yorum, metin kutusu ve özel sayfa düzeni ayarları korunmaz.\n\n'
                'Evet: yeni bir dosyaya kaydet (önerilir)\nHayır: yine de üzerine yaz', parent=self)
            if ans is None:
                return False
            if ans:
                return self.save_as(d, suggest=os.path.splitext(d.path)[0] + ' (AI).docx')
            d.docx_warned = True
        return self._write(d, d.path)

    def save_as(self, doc=None, suggest=None):
        d = doc or self.cur()
        if not d:
            return False
        origin = getattr(d, 'origin', None)
        ext = '.docx' if d.rich else '.txt'
        clean = re.sub(r'[\\/:*?"<>|]+', ' ', d.title).strip(' .') or 'Belge'
        init = suggest or d.path or (os.path.splitext(origin)[0] + '.docx' if origin else clean + ext)
        p = filedialog.asksaveasfilename(parent=self, title='Farklı kaydet', initialfile=os.path.basename(init),
                                         initialdir=os.path.dirname(init) if os.path.dirname(init) else None,
                                         defaultextension=ext, filetypes=SAVE_FILETYPES if d.rich else
                                         [SAVE_FILETYPES[2], SAVE_FILETYPES[1], SAVE_FILETYPES[0], SAVE_FILETYPES[3]])
        if not p:
            return False
        if self._write(d, p):
            d.docx_warned = True
            return True
        return False

    def _write(self, d, path):
        prev = d.docfile if d.path and os.path.normcase(d.path) == os.path.normcase(path) else None
        kind = core.detect_kind(path)
        lost = False
        try:
            if d.rich or kind == 'docx':
                blocks = d.text.get_blocks() if d.rich else rdoc.markdown_to_blocks(d.text.get('1.0', 'end-1c'))
                if kind == 'docx':
                    data = rdoc.docx_bytes(blocks)
                    core._atomic_write(path, lambda f: f.write(data))
                    d.docfile = core.DocFile(path, 'docx')
                elif kind == 'html':
                    data = rdoc.html_document(blocks, os.path.splitext(os.path.basename(path))[0]).encode('utf-8')
                    core._atomic_write(path, lambda f: f.write(data))
                    d.docfile = core.DocFile(path, 'html')
                elif kind == 'md':
                    md, files = rdoc.markdown_file_text(blocks, path)
                    for fp, data in files.items():
                        os.makedirs(os.path.dirname(fp), exist_ok=True)
                        with open(fp, 'wb') as fh:
                            fh.write(data)
                    d.docfile = core.write_document(path, md, prev)
                else:
                    lost = rdoc.has_formatting(blocks)
                    d.docfile = core.write_document(path, rdoc.plain_text(blocks), prev)
            else:
                d.docfile = core.write_document(path, d.text.get('1.0', 'end-1c'), prev)
        except Exception as e:
            messagebox.showerror('Kaydedilemedi', '%s\n\n%s' % (path, e), parent=self)
            return False
        d.path = path
        d.title = os.path.basename(path)
        d.saved_text = None
        core.drop_recovery(d.id)
        core.add_recent(self.settings, path)
        core.save_settings(self.settings)
        self.nb.tab(d.frame, text=self._tab_title(d))
        self.flash('Kaydedildi: %s%s' % (path, ' · ⚠ düz metin: biçimler, tablolar ve resimler dosyaya yazılmadı (Word için .docx seçin)'
                                          if lost else ''), 9000 if lost else 6000)
        self._update_status()
        return True

    def close_doc(self, doc=None, ask=True):
        if doc is None and self.cur_pdf():
            return self.close_pdf(self.cur_pdf(), ask)
        d = doc or self.cur()
        if not d:
            return True
        if ask and d.dirty:
            ans = messagebox.askyesnocancel('Kaydedilmemiş değişiklik', '"%s" kaydedilsin mi?' % d.title, parent=self)
            if ans is None:
                return False
            if ans and not self.save(d):
                return False
        core.drop_recovery(d.id)
        self.nb.forget(d.frame)
        d.frame.destroy()
        self.docs.remove(d)
        if not self.docs and ask:
            self.new_doc()
        return True

    def _middle_close(self, e):
        try:
            idx = self.nb.index('@%d,%d' % (e.x, e.y))
        except tk.TclError:
            return
        frame = self.nametowidget(self.nb.tabs()[idx])
        if frame in self.pdf_views:
            self.close_pdf(frame)
            return
        if frame in getattr(self, 'compare_views', {}):
            self.close_compare(frame)
            return
        d = next((x for x in self.docs if x.frame is frame), None)
        if d:
            self.close_doc(d)

    def on_close(self):
        for v in list(self.pdf_views.values()):
            if not self.close_pdf(v):
                return
        for d in list(self.docs):
            if d.dirty:
                self.nb.select(d.frame)
                if not self.close_doc(d):
                    return
        self.settings.update(language=self.lang_var.get(), tone=self.tone_var.get(), audience=self.aud_var.get(),
                             length=self.len_var.get(), preserve_facts=bool(self.preserve_var.get()))
        core.save_settings(self.settings)
        self.destroy()

    def zoom(self, delta):
        self.settings['font_size'] = max(8, min(36, int(self.settings.get('font_size', 12)) + delta))
        z = float(self.settings.get('page_zoom', 1.0))
        z = max(0.6, min(2.2, round(z * (1.1 if delta > 0 else 1 / 1.1), 2)))
        self.settings['page_zoom'] = z
        for d in self.docs:
            if d.text.rich:
                d.text.set_font(zoom=z)
                self._place_text(d)
            else:
                d.text.configure(font=self._editor_font())
                d.text.set_font(self._editor_font()[0], self._editor_font()[1])
                d.text.tag_configure('md_h', font=(self._editor_font()[0], int(self._editor_font()[1] * 1.25), 'bold'))
        core.save_settings(self.settings)
        self.flash('Yakınlaştırma: %%%d' % round(z * 100))

    def _autosave(self):
        for d in self.docs:
            if d.dirty:
                try:
                    if d.rich:
                        blocks = d.text.get_blocks()
                        core.save_recovery(d.id, d.title, rdoc.blocks_to_markdown(blocks) or ' ', d.path,
                                           blocks=rdoc.blocks_to_json(blocks))
                    else:
                        core.save_recovery(d.id, d.title, d.text.get('1.0', 'end-1c'), d.path)
                except (OSError, tk.TclError):
                    pass
        self._timers['autosave'] = self.after(AUTOSAVE_MS, self._autosave)

    def destroy(self):
        for t in getattr(self, '_timers', {}).values():
            try:
                self.after_cancel(t)
            except (tk.TclError, ValueError):
                pass
        self._timers = {}
        try:
            self.busy.stop()
        except (tk.TclError, AttributeError):
            pass
        super().destroy()

    def _offer_recovery(self):
        items = core.list_recovery()
        if not items:
            return
        names = '\n'.join('• %s (%s)' % (i.get('title') or 'Adsız', i.get('saved', '')) for i in items[:8])
        if messagebox.askyesno('Kurtarılan belgeler', 'Kaydedilmeden kapanan belgeler bulundu:\n\n%s\n\nAçılsın mı? '
                               '(Hayır: kurtarma kayıtları silinir)' % names, parent=self):
            for i in items:
                blocks = None
                if isinstance(i.get('blocks'), list):
                    try:
                        blocks = rdoc.blocks_from_json(i['blocks'])
                    except Exception:
                        blocks = None
                d = self.new_doc(i['text'] if blocks is None else '', (i.get('title') or 'Kurtarılan') + ' (kurtarıldı)',
                                 blocks=blocks, rich=True if blocks is not None else None)
                if i.get('path'):
                    d.path = None
                core.drop_recovery(i.get('id', ''))
        else:
            for i in items:
                core.drop_recovery(i.get('id', ''))

    # ------------------------------------------------------------------ bul / degistir
    def toggle_find(self, replace=False):
        if self.find_bar.winfo_manager():
            self.find_bar.pack_forget()
            d = self.cur()
            if d:
                d.text.tag_remove('found', '1.0', 'end')
                d.text.focus_set()
        else:
            self.find_bar.pack(fill='x', padx=18, pady=(4, 0), before=self.paned)
            d = self.cur()
            if d:
                try:
                    sel = d.text.get('sel.first', 'sel.last')
                    if sel and '\n' not in sel:
                        self.find_var.set(sel)
                except tk.TclError:
                    pass
            self.find_entry.focus_set()

    def find_next(self, back=False):
        d = self.cur()
        pat = self.find_var.get()
        if not d or not pat:
            return False
        t = d.text
        t.tag_remove('found', '1.0', 'end')
        start = t.index('insert') if not back else t.index('insert')
        if back:
            try:
                start = t.index('sel.first')
            except tk.TclError:
                pass
        pos = t.search(pat, start if back else start + ('+1c' if t.tag_ranges('sel') else ''), backwards=back,
                       nocase=not self.case_var.get(), stopindex=None)
        if not pos:
            self.find_info.configure(text='Bulunamadı')
            return False
        end = '%s+%dc' % (pos, len(pat))
        t.tag_remove('sel', '1.0', 'end')
        t.tag_add('sel', pos, end)
        t.tag_add('found', pos, end)
        t.mark_set('insert', end if not back else pos)
        t.see(pos)
        count = self._count(t, pat)
        self.find_info.configure(text='%d eşleşme' % count)
        return True

    def _count(self, t, pat):
        n, idx = 0, '1.0'
        while True:
            idx = t.search(pat, idx, stopindex='end', nocase=not self.case_var.get())
            if not idx:
                return n
            n += 1
            idx = '%s+%dc' % (idx, max(1, len(pat)))
            if n > 100000:
                return n

    def replace_one(self):
        d = self.cur()
        if not d:
            return
        t = d.text
        try:
            sel = t.get('sel.first', 'sel.last')
        except tk.TclError:
            sel = ''
        pat = self.find_var.get()
        if sel and (sel == pat or (not self.case_var.get() and sel.lower() == pat.lower())):
            t.edit_separator()
            start = t.index('sel.first')
            keep = tuple(str(x) for x in t.tag_names(start) if rtext.recorded(str(x)))
            t.undo.begin()
            try:
                t.delete('sel.first', 'sel.last')
                t.insert(start, self.repl_var.get(), keep)
            finally:
                t.undo.end()
            t.mark_set('insert', '%s+%dc' % (start, len(self.repl_var.get())))
            t.edit_separator()
        self.find_next()

    def replace_all(self):
        d = self.cur()
        pat = self.find_var.get()
        if not d or not pat:
            return
        t = d.text
        rep = self.repl_var.get()
        t.edit_separator()
        t.undo.begin()
        n, idx = 0, '1.0'
        try:
            while True:
                idx = t.search(pat, idx, stopindex='end', nocase=not self.case_var.get())
                if not idx:
                    break
                keep = tuple(str(x) for x in t.tag_names(idx) if rtext.recorded(str(x)))
                t.delete(idx, '%s+%dc' % (idx, len(pat)))
                t.insert(idx, rep, keep)
                idx = '%s+%dc' % (idx, len(rep))
                n += 1
        finally:
            t.undo.end()
        t.edit_separator()
        if n:
            self._doc_changed(d)
        self.find_info.configure(text='%d değişiklik' % n)

    # ------------------------------------------------------------------ durum / menuler
    def _update_status(self):
        v = self.cur_pdf() if hasattr(self, 'pdf_views') else None
        if v:
            self.status_var.set(v.status_text())
            return
        d = self.cur()
        if not d:
            self.status_var.set('')
            return
        try:
            line, col = d.text.index('insert').split('.')
        except tk.TclError:
            line, col = '1', '0'
        txt = d.text.get('1.0', 'end-1c')
        st = core.text_stats(txt)
        try:
            sel = d.text.get('sel.first', 'sel.last')
            sel_info = ' · seçim %d kelime' % core.text_stats(sel)['words'] if sel else ''
        except tk.TclError:
            sel_info = ''
        kind = (d.docfile.kind or ('docx' if d.rich else 'txt')).upper() if d.path else ('Biçimli' if d.rich else 'TXT')
        enc = d.docfile.encoding.upper() if d.docfile.kind in ('txt', 'md') and d.path else ''
        pages = ''
        if d.rich and d.text.page_mode:
            pages = ' · ≈%d sayfa' % d.text.page_count()
        if d.rich:
            self.status_var.set('Paragraf %s · %d kelime · %d karakter%s%s · %s%s' % (
                line, st['words'], st['chars'], sel_info, pages, kind, (' · ' + enc) if enc else ''))
            return
        self.status_var.set('Satır %s, Sütun %d · %d kelime · %d karakter%s · %s%s' % (
            line, int(col) + 1, st['words'], st['chars'], sel_info, kind, (' · ' + enc) if enc else ''))

    def flash(self, msg, ms=6000):
        self.ai_var.set(msg)
        token = object()
        self._flash_token = token
        self.after(ms, lambda: self.ai_var.set('') if getattr(self, '_flash_token', None) is token else None)

    def show_more_menu(self):
        m = tk.Menu(self, tearoff=0)
        rec = tk.Menu(m, tearoff=0)
        for p in self.settings.get('recent', [])[:12]:
            rec.add_command(label=p, command=lambda x=p: self.open_path(x))
        if not self.settings.get('recent'):
            rec.add_command(label='(boş)', state='disabled')
        m.add_cascade(label='Son dosyalar', menu=rec)
        m.add_command(label='Sekmeyi kapat  (Ctrl+W)', command=self.close_doc)
        m.add_separator()
        m.add_command(label='Güncellemeleri denetle', command=lambda: self.check_update(silent=False))
        if upd.is_frozen() and IS_WIN:
            if upd.running_installed():
                m.add_command(label='Kaldır…', command=self.uninstall)
            else:
                m.add_command(label='Bu bilgisayara kur…', command=lambda: self.install(ask=True))
        m.add_separator()
        m.add_command(label='Hakkında', command=self.about)
        x = self.more_btn.winfo_rootx()
        y = self.more_btn.winfo_rooty() + self.more_btn.winfo_height()
        m.tk_popup(x, y)

    def _context_menu(self, e):
        d = self.cur()
        if not d:
            return
        m = tk.Menu(self, tearoff=0)
        t = d.text
        here = t.index('@%d,%d' % (e.x, e.y))
        img = t.image_at(here) if t.rich else None
        if img:
            self._image_menu(m, t, img)
            m.tk_popup(e.x_root, e.y_root)
            return
        m.add_command(label='Kes', command=lambda: d.text.event_generate('<<Cut>>'))
        m.add_command(label='Kopyala', command=lambda: d.text.event_generate('<<Copy>>'))
        m.add_command(label='Yapıştır', command=lambda: d.text.event_generate('<<Paste>>'))
        m.add_separator()
        line = int(here.split('.')[0])
        if t.rich and t.para_props(line)['table']:
            t.mark_set('insert', here)
            tm = tk.Menu(m, tearoff=0)
            tm.add_command(label='Alta satır ekle', command=lambda: t.table_add_row(line, True))
            tm.add_command(label='Üste satır ekle', command=lambda: t.table_add_row(line, False))
            tm.add_command(label='Sağa sütun ekle', command=lambda: t.table_add_col(line, here))
            tm.add_separator()
            tm.add_command(label='Satırı sil', command=lambda: t.table_delete_row(line))
            tm.add_command(label='Sütunu sil', command=lambda: t.table_delete_col(line, here))
            tm.add_command(label='Tabloyu sil', command=lambda: t.table_delete(line))
            m.add_cascade(label='Tablo', menu=tm)
        m.add_command(label='Resim ekle…', command=self.insert_image)
        m.add_command(label='Tablo ekle…', command=self.insert_table)
        m.add_separator()
        for key in ('content_strengthen', 'content_flow', 'proofread', 'shorten', 'expand', 'critique'):
            a = core.action_by_key(key)
            m.add_command(label='AI: ' + a['label'], command=lambda k=key: self.run_action_key(k))
        m.add_command(label='AI: Çevir (%s)' % self.tr_lang.get(), command=self.run_translate)
        m.tk_popup(e.x_root, e.y_root)

    def _image_menu(self, m, t, name):
        blk = t.images.get(name) or {}
        sz = tk.Menu(m, tearoff=0)
        for label, w in (('%25', rdoc.CONTENT_W_PT * 0.25), ('%50', rdoc.CONTENT_W_PT * 0.5), ('%75', rdoc.CONTENT_W_PT * 0.75),
                         ('Sayfa genişliği', rdoc.CONTENT_W_PT)):
            sz.add_command(label=label, command=lambda ww=w: t.resize_image(name, ww))
        if blk:
            sz.add_command(label='Özgün boyut', command=lambda: t.resize_image(name, min(rdoc.CONTENT_W_PT, rdoc.image_block(blk['data'])['w'])))
        m.add_cascade(label='Resim boyutu', menu=sz)
        al = tk.Menu(m, tearoff=0)
        line = int(t.index(name).split('.')[0])
        for label, a in (('Sola', 'left'), ('Ortala', 'center'), ('Sağa', 'right')):
            al.add_command(label=label, command=lambda aa=a: (t.mark_set('insert', '%d.0' % line), t.set_align(aa)))
        m.add_cascade(label='Hizala', menu=al)
        m.add_command(label='Resmi değiştir…', command=lambda: self._replace_image(t, name))
        m.add_command(label='Resmi farklı kaydet…', command=lambda: self._save_image(blk))
        m.add_separator()
        m.add_command(label='Resmi kaldır', command=lambda: t.remove_image(name))

    def _replace_image(self, t, name):
        path = filedialog.askopenfilename(parent=self, title='Yeni resim', filetypes=[('Resim', '*.png *.jpg *.jpeg *.gif *.bmp')])
        if not path:
            return
        try:
            with open(path, 'rb') as fh:
                blk = rdoc.image_block(fh.read())
        except (OSError, ValueError) as e:
            messagebox.showerror('Resim', str(e), parent=self)
            return
        idx = t.index(name)
        t.undo.separator()
        t.undo.begin()
        try:
            t.delete(idx)
            t._create_image(idx, blk)
        finally:
            t.undo.end()
        t.changed()

    def _save_image(self, blk):
        if not blk:
            return
        ext = 'jpg' if blk['ext'] == 'jpeg' else blk['ext']
        p = filedialog.asksaveasfilename(parent=self, title='Resmi kaydet', initialfile='resim.' + ext, defaultextension='.' + ext,
                                         filetypes=[('Resim', '*.' + ext)])
        if p:
            with open(p, 'wb') as fh:
                fh.write(blk['data'])

    def about(self):
        messagebox.showinfo('AGFO AI Editor', 'AGFO AI Editor %s\n\nYazdıklarınızın içeriğini yapay zekâyla düzenleyen metin editörü.\n'
                            'Bağlantı: AGFO AI Manager (WordPress) veya doğrudan sağlayıcı.\n\n'
                            'Veri klasörü: %s' % (core.VERSION, core.data_dir()), parent=self)

    def _bind_keys(self):
        b = self.bind_all
        b('<Control-n>', lambda e: (self.new_doc(), 'break')[1])
        b('<Control-o>', lambda e: (self.open_dialog(), 'break')[1])
        b('<Control-s>', lambda e: (self.save(), 'break')[1])
        b('<Control-S>', lambda e: (self.save_as(), 'break')[1])
        b('<Control-w>', lambda e: (self.close_doc(), 'break')[1])
        b('<Control-f>', lambda e: (self.toggle_find(), 'break')[1])
        b('<Control-h>', lambda e: (self.toggle_find(replace=True), 'break')[1])
        b('<Control-e>', lambda e: (self.run_selected_action(), 'break')[1])
        b('<F3>', lambda e: (self.find_next(), 'break')[1])
        b('<Control-plus>', lambda e: self.zoom(1))
        b('<Control-minus>', lambda e: self.zoom(-1))
        b('<Control-Tab>', lambda e: self._cycle_tab(1))

    def _cycle_tab(self, step):
        tabs = self.nb.tabs()
        if tabs:
            i = (self.nb.index('current') + step) % len(tabs)
            self.nb.select(tabs[i])
        return 'break'

    # ------------------------------------------------------------------ is parcaciklari
    def _start_job(self, label, fn, on_done, *args):
        jid = uuid.uuid4().hex
        self.jobs[jid] = on_done
        self.ai_var.set(label + '…')
        self.busy.pack(side='right', padx=(8, 0))
        self.cancel_btn.pack(side='right', padx=(8, 0))
        self.busy.start(12)

        def work():
            try:
                self.q.put((jid, True, fn(*args)))
            except ai.AIError as e:
                self.q.put((jid, False, str(e)))
            except Exception as e:  # beklenmeyen hata: kullaniciya ozet, gunluge ayrinti
                self._log_error(traceback.format_exc())
                self.q.put((jid, False, 'Beklenmeyen hata: %r' % e))
        threading.Thread(target=work, daemon=True).start()
        return jid

    def _log_error(self, text):
        try:
            with open(core.data_dir() / 'error-log.txt', 'a', encoding='utf-8') as f:
                f.write(ai.redact(text) + '\n')
        except OSError:
            pass

    def _poll(self):
        try:
            while True:
                jid, ok, payload = self.q.get_nowait()
                cb = self.jobs.pop(jid, None)
                if not self.jobs:
                    self.busy.stop()
                    self.busy.pack_forget()
                    self.cancel_btn.pack_forget()
                    if self.ai_var.get().endswith('…'):      # yalniz is etiketi silinir; sonuc mesajlari (flash) kalir
                        self.ai_var.set('')
                if cb:
                    try:
                        cb(ok, payload)
                    except Exception:
                        self._log_error(traceback.format_exc())
        except queue.Empty:
            pass
        self._drain_tr_events()
        prog = getattr(self, '_tr_progress', None)
        if prog and self.jobs:
            model = getattr(self, '_tr_model', None)
            self.ai_var.set('Belge çevriliyor… %d / %d parça grubu tamam%s…' % (prog[0], prog[1], (' · ' + model) if model else ''))
        if self._timers:
            self._timers['poll'] = self.after(POLL_MS, self._poll)

    def _drain_tr_events(self):
        events, live = getattr(self, '_tr_events', None), getattr(self, '_tr_live', None)
        if not events:
            return
        n = len(events)
        batch, events[:n] = events[:n], []
        if live:
            for kind, keys in batch:
                live.event(kind, keys)

    def cancel_jobs(self):
        live = getattr(self, '_tr_live', None)
        if live:
            live.finish(800)
            self._tr_live = None
        if getattr(self, '_tr_cancel', None):
            self._tr_cancel.set()
        self.jobs.clear()
        self.busy.stop()
        self.busy.pack_forget()
        self.cancel_btn.pack_forget()
        self.flash('İstek durduruldu; gelen yanıt yok sayılacak.')

    def backends(self):
        return ai.build_backends(self.settings, secrets.unprotect)

    # ------------------------------------------------------------------ AI eylemleri
    def _scope_range(self, d, force_all=False):
        t = d.text
        if not force_all and self.scope_var.get() == 'selection':
            try:
                return t.index('sel.first'), t.index('sel.last'), 'seçim'
            except tk.TclError:
                if t.rich:                       # bicimli belgede paragraf = imlecin satiri
                    line = int(t.index('insert').split('.')[0])
                    tag, lines = t.table_lines(line)
                    if tag:
                        return '%d.0' % lines[0], '%d.end' % lines[-1], 'tablo'
                    start, end = t._content_start(line), '%d.end' % line
                    if t.get(start, end).strip():
                        return start, end, 'paragraf'
                    return '1.0', t.index('end-1c'), 'belge'
                # secim yoksa imlecin bulundugu paragraf
                ins = t.index('insert')
                start = t.search(r'\n\s*\n', ins, backwards=True, regexp=True, stopindex='1.0')
                start = t.index('%s lineend +1c' % start) if start else '1.0'
                start = t.index(start)
                end = t.search(r'\n\s*\n', ins, regexp=True, stopindex='end')
                end = end or t.index('end-1c')
                if t.get(start, end).strip():
                    while t.get(start, start + '+1c') in ('\n', ' ') and t.compare(start, '<', end):
                        start = t.index(start + '+1c')
                    return start, end, 'paragraf'
        return '1.0', t.index('end-1c'), 'belge'

    def _ai_options(self):
        return {'language': self.lang_var.get(), 'tone': self.tone_var.get(), 'audience': self.aud_var.get(), 'length': self.len_var.get(),
                'preserve_facts': bool(self.preserve_var.get()), 'from_scratch': bool(self.brief_var.get()),
                'user_extra': self.extra_txt.get('1.0', 'end-1c').strip()}

    def run_selected_action(self):
        i = self.action_combo.current()
        if 0 <= i < len(self.actions):
            a = self.actions[i]
            self.settings['last_action'] = a[0]
            self.run_action({'key': a[0], 'label': a[1], 'description': a[2], 'template': a[3], 'extra': a[4], 'mode': a[5]})

    def run_action_key(self, key):
        a = core.action_by_key(key)
        if a:
            self.run_action(a)

    def run_action(self, action, options=None, translate_mode=None):
        d = self.cur()
        if not d:
            if hasattr(self, 'pdf_views') and self.cur_pdf():
                if action.get('mode') == 'chat':          # ozet, degerlendirme: PDF metniyle sohbette
                    opts = options or self._ai_options()
                    prompt = core.CHAT_PROMPTS.get(action['key'], 'Bu metni değerlendir.').format(language=opts.get('language', 'Türkçe'))
                    self.ai_nb.select(2)
                    self.send_chat(prompt=prompt, label=action['label'])
                else:
                    messagebox.showinfo(action['label'], 'Bu işlem metni değiştirir; PDF\'de doğrudan yapılamaz.\n\n'
                                        'Önce "Metin olarak aç" ile PDF\'i düzenlenebilir belgeye çevirin ya da '
                                        'Sohbet sekmesinde PDF hakkında soru sorun (belge metni otomatik gönderilir).', parent=self)
            return
        options = options or self._ai_options()
        if action['key'] == 'custom' and not options.get('user_extra'):
            messagebox.showinfo('Özel talimat', 'Önce "Ek talimat" kutusuna ne yapılmasını istediğinizi yazın.', parent=self)
            return
        if action['mode'] == 'chat':
            prompt = core.CHAT_PROMPTS.get(action['key'], 'Bu metni değerlendir.').format(language=options.get('language', 'Türkçe'))
            self.ai_nb.select(2)
            self.send_chat(prompt=prompt, label=action['label'])
            return
        start, end, where = self._scope_range(d)
        images = {}
        if d.rich:
            options = dict(options, rich=True)
            source, images = d.text.markdown(start, end)
        else:
            source = d.text.get(start, end)
        if not source.strip():
            messagebox.showinfo('Metin yok', 'Düzenlenecek metin bulunamadı. Bir bölüm seçin ya da "Tüm belge"yi işaretleyin.', parent=self)
            return
        if len(source) > core.MAX_CHARS:
            messagebox.showwarning('Çok uzun', 'Seçilen metin %d karakter. Tek seferde en fazla %d karakter işlenir; daha küçük bir bölüm seçin.'
                                   % (len(source), core.MAX_CHARS), parent=self)
            return
        ms, me = 'ais_' + uuid.uuid4().hex[:8], 'aie_' + uuid.uuid4().hex[:8]
        d.text.mark_set(ms, start)
        d.text.mark_gravity(ms, 'left')
        d.text.mark_set(me, end)
        d.text.mark_gravity(me, 'right')
        backends = self.backends()

        def done(ok, res):
            if not ok:
                self._clear_marks(d, ms, me)
                self.ai_var.set('')
                messagebox.showerror('Yapay zekâ', res, parent=self)
                return
            self.ai_var.set('Son işlem: %s · %s %s' % (action['label'], res.get('via', ''), ('· ' + res.get('model', '')) if res.get('model') else ''))
            self.review(d, ms, me, source, res, action, translate_mode, images=images)
        self._start_job('%s (%s)' % (action['label'], where), ai.run_with_fallback, done, backends, 'transform', source, action, options)

    def _clear_marks(self, d, *marks):
        for m in marks:
            try:
                d.text.mark_unset(m)
            except tk.TclError:
                pass

    def run_translate(self):
        opts = self._ai_options()
        opts['language'] = self.tr_lang.get() or 'English'
        opts['user_extra'] = self.tr_extra.get('1.0', 'end-1c').strip()
        opts['from_scratch'] = False
        opts['model_choice'] = self.translation_choice()
        action = {'key': 'translate', 'label': 'Çeviri → %s' % opts['language'], 'template': 'translate_polish',
                  'extra': 'Translate into %s.' % opts['language'], 'mode': 'replace', 'description': ''}
        self.run_action(action, opts, translate_mode=self.tr_mode.get())

    # ------------------------------------------------------------------ belge cevirisi (1.4)
    def translate_document(self):
        lang = (self.tr_lang.get() or 'English').strip()
        out = self.doc_tr_out.get() if hasattr(self, 'doc_tr_out') else 'both'
        self.settings['doc_translate_output'] = out
        v, d = self.cur_pdf(), self.cur()
        if not v and not d:
            return
        extra = self.tr_extra.get('1.0', 'end-1c').strip()
        backends = self.backends()
        layouts = None
        live = None
        import agfo_pdf_layout as playout
        if v:
            path, title = v.pr.path, os.path.splitext(os.path.basename(getattr(v.pr, 'display_name', None) or v.pr.path))[0]
            blocks = None
            try:
                layouts = v.pr.layouts()          # sayfa duzeni ana is parcaciginda (pdfium is parcacigi guvenli degil)
            except Exception as e:
                messagebox.showerror('Belge çevirisi', str(e), parent=self)
                return
            if not any(lay['paras'] for lay in layouts):
                messagebox.showinfo('Belge çevirisi', 'PDF\'de okunabilir metin yok (taranmış belge olabilir).', parent=self)
                return
            # okunamayan (Unicode eslemesi bozuk) metin modele gonderilmez; PDF'te yerinde kalir
            blocks = [rdoc.para(text='' if playout.BROKEN_TEXT_RX.search(P['text']) else P['text'])
                      for lay in layouts for P in lay['paras']]
            pdf_map = [(pi, n, v.pr._disp_rect(pi, P['rect'])) for pi, lay in enumerate(layouts) for n, P in enumerate(lay['paras'])]
            live = trlive.TranslationLive(self, view=v, pdf_map=pdf_map)
        else:
            title = os.path.splitext(d.title)[0]
            if d.rich:
                lines = []
                blocks = d.text.get_blocks(lines=lines)
            else:
                blocks = rdoc.markdown_to_blocks(d.text.get('1.0', 'end-1c'))
                lines = trlive.text_block_lines(d.text, blocks)
            live = trlive.TranslationLive(self, text=d.text, lines=lines)
            path = None
            if not any(b['t'] == 'p' and rdoc.runs_text(b['runs']).strip() or b['t'] == 'table' for b in blocks):
                messagebox.showinfo('Belge çevirisi', 'Çevrilecek metin yok.', parent=self)
                return
        cancel = threading.Event()
        self._tr_cancel = cancel
        self._tr_progress = None
        options = self._ai_options()
        options.update(language=lang, rich=True, from_scratch=False, preserve_facts=True, user_extra=extra,
                       model_choice=self.translation_choice(backends))
        workers = self.translation_workers()
        events = []                 # is parcaciklarindan gelen vurgu olaylari; _poll ana is parcaciginda isler
        self._tr_events, self._tr_live = events, live

        notes = []
        models = []                 # gercekten yanit veren modeller (sirayla, tekrar etmeden)
        self._tr_model = None

        def call(text, instruction):
            action = {'key': 'translate_doc', 'label': 'Belge çevirisi', 'template': 'translate_polish', 'extra': instruction,
                      'mode': 'replace', 'description': ''}
            r = ai.run_with_fallback(backends, 'transform', text, action, options)
            if r.get('note') and r['note'] not in notes:
                notes.append(r['note'])
            label = self.model_label(r)
            if label not in models:
                models.append(label)
            self._tr_model = label
            return r['text']

        def progress(i, n):
            self._tr_progress = (i, n)

        def work():
            src = blocks
            try:
                new, stats = dtr.translate_blocks(src, call, lang, progress, cancel.is_set, workers=workers,
                                                  on_event=lambda kind, keys, _got: events.append((kind, keys)))
            except InterruptedError as e:
                raise ai.AIError(str(e))
            return src, new, stats

        def done(ok, res):
            self._tr_progress = None
            self._drain_tr_events()
            if live:
                live.finish()
            self._tr_live = None
            if not ok:
                messagebox.showerror('Belge çevirisi', res, parent=self)
                return
            src, new, stats = res
            used = ', '.join(models) or 'bilinmeyen model'
            self.last_translation_models = list(models)
            extra_note = ''
            if layouts is not None:
                src, new, extra_note = self._pdf_translation_outputs(v, layouts, new, title, lang, out, used)
            else:
                if out in ('newtab', 'both', 'pdf'):
                    self.new_doc(title='%s (%s)' % (title, lang), blocks=new)
                if out in ('compare', 'both'):
                    self.open_compare(src, new, title, 'Özgün', lang, model=used)
            note = 'Çeviri tamam: %d parça, %d istek · Model: %s' % (stats['segments'], stats['batches'], used) + extra_note
            if stats['missing']:
                note += ' · ⚠ %d parça çevrilemedi, özgün haliyle bırakıldı' % stats['missing']
            if notes:
                note += ' · ' + notes[0]
            self.flash(note, 10000)
        self._start_job('Belge çevriliyor → %s · %s · aynı anda %d istek' % (
            lang, self.translation_model_text().replace('Çeviri modeli: ', ''), workers), work, done)

    def _pdf_translation_outputs(self, v, layouts, new, title, lang, out, used):
        """PDF cevirisinin ciktilari. pdf: sayfa duzeni korunmus cevrilmis PDF (PDF duzenleyicide acilir);
        newtab: basliklari, kalinlari ve resimleriyle bicimli belge; compare: yan yana; both: PDF + yan yana."""
        import tempfile
        import agfo_pdf_layout as playout
        texts = [rdoc.runs_text(b['runs']) if b.get('t') == 'p' else '' for b in new]
        pages = v.pr.layout_pages()
        note = ''
        orig_blocks = trans_blocks = None
        if out in ('newtab', 'compare', 'both'):
            orig_blocks = playout.layout_blocks(pages, title, layouts, images=out == 'newtab')
            trans_blocks = playout.layout_blocks(pages, '%s (%s)' % (title, lang), layouts, texts, images=out == 'newtab')
        if out in ('pdf', 'both'):
            self.flash('Çevrilmiş PDF hazırlanıyor (sayfa düzeni korunuyor)…', 4000)
            self.update_idletasks()
            try:
                data, st = v.pr.translated_pdf(layouts, texts)
                folder = os.path.join(tempfile.gettempdir(), 'AGFO AI Editor', 'ceviri')
                os.makedirs(folder, exist_ok=True)
                safe = re.sub(r'[\\/:*?"<>|]+', '_', '%s (%s).pdf' % (title, lang))
                target = os.path.join(folder, safe)
                k = 1
                while os.path.exists(target):
                    try:
                        os.remove(target)
                        break
                    except OSError:
                        k += 1
                        target = os.path.join(folder, safe[:-4] + ' %d.pdf' % k)
                with open(target, 'wb') as f:
                    f.write(data)
                pv = self.open_pdf(target)
                if pv is not None:
                    pv.pr.save_dir = os.path.dirname(v.pr.path)
                note = ' · Çevrilmiş PDF düzenleyicide açıldı (%d sayfa yerinde%s)' % (
                    st['inplace'], ', %d sayfa örtülerek' % st['overlay'] if st['overlay'] else '')
            except Exception as e:                      # PDF kurulamadi: bicimli belgeye dus
                messagebox.showwarning('Çevrilmiş PDF', 'Sayfa düzeni korunarak PDF oluşturulamadı:\n%s\n\nÇeviri biçimli belge olarak açılıyor.' % e,
                                       parent=self)
                if trans_blocks is None:
                    trans_blocks = playout.layout_blocks(pages, '%s (%s)' % (title, lang), layouts, texts)
                self.new_doc(title='%s (%s)' % (title, lang), blocks=trans_blocks)
        if out == 'newtab':
            self.new_doc(title='%s (%s)' % (title, lang), blocks=trans_blocks)
        if out in ('compare', 'both'):
            self.open_compare(orig_blocks, trans_blocks, title, 'Özgün', lang, model=used)
        return orig_blocks, trans_blocks, note

    def open_compare(self, orig, trans, title, left, right, model=''):
        import agfo_compare
        if not hasattr(self, 'compare_views'):
            self.compare_views = {}
        v = agfo_compare.CompareView(self, self.nb, orig, trans, title, left, right, model=model)
        self.compare_views[v] = v
        self.nb.add(v, text='↔ %s' % title[:40])
        self.nb.select(v)
        return v

    def close_compare(self, v):
        self.nb.forget(v)
        getattr(self, 'compare_views', {}).pop(v, None)
        v.destroy()
        if not self.docs and not self.pdf_views and not getattr(self, 'compare_views', None):
            self.new_doc()

    def run_audit(self):
        a = core.audit_action(self.audit_var.get(), self.std_var.get(), self.clause_var.get())
        if a:
            opts = self._ai_options()
            opts['tone'] = 'Profesyonel'
            opts['audience'] = 'Denetçi / akreditasyon kurumu'
            opts['preserve_facts'] = True
            self.run_action(a, opts)

    # ------------------------------------------------------------------ inceleme (fark) penceresi
    def review(self, d, ms, me, source, res, action, translate_mode=None, images=None):
        new = res['text']
        images = images or {}
        win = tk.Toplevel(self)
        win.title('AI önerisi · %s' % action['label'])
        win.configure(bg=PANEL)
        win.transient(self)
        w, h = int(980 * min(self.scale, 1.2)), int(680 * min(self.scale, 1.2))
        win.geometry('%dx%d+%d+%d' % (w, h, self.winfo_rootx() + 60, self.winfo_rooty() + 40))
        ops = core.word_diff(source, new) if action.get('mode') == 'replace' and action['key'] != 'translate' else []
        stats = core.diff_stats(ops) if ops else None
        head = tk.Frame(win, bg=PANEL, padx=14, pady=10)
        head.pack(fill='x')
        tk.Label(head, text=action['label'], fg=FG, bg=PANEL, font=('Segoe UI', 13, 'bold')).pack(anchor='w')
        info = '%s · %s%s' % (res.get('via', ''), res.get('provider', ''), (' · ' + res['model']) if res.get('model') else '')
        if stats:
            info += '   ·   −%d kelime silindi, +%d kelime eklendi, %d kelime aynı' % (stats['deleted'], stats['inserted'], stats['kept'])
        tk.Label(head, text=info, fg=MUTED, bg=PANEL, font=('Segoe UI', 9)).pack(anchor='w')
        if res.get('note'):
            tk.Label(head, text='ℹ ' + res['note'], fg=WARN, bg=PANEL, font=('Segoe UI', 9), wraplength=900, justify='left').pack(anchor='w', pady=(4, 0))
        if res.get('truncated'):
            tk.Label(head, text='⚠ Yanıt çıktı sınırında kesilmiş olabilir; sonunu kontrol edin veya daha küçük bölümlerle çalışın.',
                     fg=WARN, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(anchor='w', pady=(4, 0))
        bar = tk.Frame(win, bg=PANEL, padx=14, pady=10)
        bar.pack(fill='x', side='bottom')
        nb = ttk.Notebook(win, style='Panel.TNotebook')
        nb.pack(fill='both', expand=True, padx=14)
        edit = None
        if ops:
            f1 = tk.Frame(nb, bg=EDIT_BG)
            dv = tk.Text(f1, wrap='word', bg=EDIT_BG, fg=FG, relief='flat', bd=0, highlightthickness=0, font=self._editor_font(),
                         padx=16, pady=12, selectbackground=SEL_BG)
            sb = ttk.Scrollbar(f1, orient='vertical', command=dv.yview)
            dv.configure(yscrollcommand=sb.set)
            sb.pack(side='right', fill='y')
            dv.pack(fill='both', expand=True)
            dv.tag_configure('delete', foreground=BAD_C, overstrike=True, background='#3a1d22')
            dv.tag_configure('insert', foreground='#b9f5cf', background='#173a2a')
            for op, s in ops:
                dv.insert('end', s, op if op != 'equal' else ())
            dv.configure(state='disabled')
            nb.add(f1, text='Değişiklikler')
        f2 = tk.Frame(nb, bg=EDIT_BG)
        edit = tk.Text(f2, wrap='word', bg=EDIT_BG, fg=FG, insertbackground=ACCENT, relief='flat', bd=0, highlightthickness=0,
                       font=self._editor_font(), padx=16, pady=12, undo=True, selectbackground=SEL_BG)
        sb2 = ttk.Scrollbar(f2, orient='vertical', command=edit.yview)
        edit.configure(yscrollcommand=sb2.set)
        sb2.pack(side='right', fill='y')
        edit.pack(fill='both', expand=True)
        edit.insert('1.0', new)
        nb.add(f2, text='Yeni metin (düzenlenebilir)')
        f3 = tk.Frame(nb, bg=EDIT_BG)
        ov = tk.Text(f3, wrap='word', bg=EDIT_BG, fg=MUTED, relief='flat', bd=0, highlightthickness=0, font=self._editor_font(), padx=16, pady=12)
        ov.insert('1.0', source)
        ov.configure(state='disabled')
        ov.pack(fill='both', expand=True)
        nb.add(f3, text='Özgün metin')

        def final_text():
            return edit.get('1.0', 'end-1c')

        def close():
            self._clear_marks(d, ms, me)
            win.destroy()

        def apply(mode):
            if d not in self.docs:
                messagebox.showwarning('Belge kapalı', 'Belge kapatılmış; "Yeni sekmede aç" kullanın.', parent=win)
                return
            t = d.text
            cur_src = t.markdown(ms, me)[0] if t.rich else t.get(ms, me)
            if cur_src != source and not messagebox.askyesno('Metin değişmiş', 'Siz beklerken bu bölüm değiştirildi. Yine de uygulansın mı?', parent=win):
                return
            txt = final_text()
            if t.rich:
                lost = [k for k in images if '![resim:%s]' % k not in txt]
                if lost and mode == 'replace':      # yapay zeka resim yer tutucusunu dusurduyse resmi kaybetme
                    txt = txt.rstrip() + '\n\n' + '\n\n'.join('![resim:%s]' % k for k in lost)
                one = rdoc.markdown_to_blocks(txt, images)
                if mode == 'replace':
                    start, end = t.replace_with_markdown(ms, me, txt, images)
                elif mode == 'append' and len(one) == 1 and one[0]['t'] == 'p' and len(txt) <= 240 and \
                        not one[0].get('list') and one[0].get('style') == 'normal':
                    start = t.index(me)                 # kisa devam: ayni paragrafa ekle
                    t.undo.separator()
                    t.undo.begin()
                    try:
                        end = t.insert_runs(me, [rdoc.run(' ')] + one[0]['runs'])
                        t.refresh_fonts(start, end)
                    finally:
                        t.undo.end()
                else:
                    r = t.insert_markdown_after(me, txt, images)
                    if not r:
                        close()
                        return
                    start, end = r
                t.tag_remove('sel', '1.0', 'end')
                t.tag_add('ai_new', start, end)
                t.see(start)
                self.after(2500, lambda: t.tag_remove('ai_new', '1.0', 'end') if d in self.docs else None)
                self._doc_changed(d)
                close()
                self.flash('Uygulandı. Geri almak için Ctrl+Z.' + (' Yanıtta eksik %d resim belgenin sonuna korundu.' % len(lost) if lost and mode == 'replace' else ''))
                return
            t.undo.begin()
            t.configure(autoseparators=False)
            t.edit_separator()
            if mode == 'replace':
                start = t.index(ms)
                t.delete(ms, me)
                t.insert(start, txt)
                end = t.index('%s+%dc' % (start, len(txt)))
            else:   # 'below' / 'append'
                start = t.index(me)
                sep = '' if mode == 'append' and source.endswith((' ', '\n')) else ('\n\n' if mode == 'below' else ' ' if not txt.startswith('\n') else '')
                if mode == 'append' and not source.endswith('\n'):
                    sep = '\n\n' if '\n' in txt.strip() or len(txt) > 200 else ' '
                t.insert(start, sep + txt)
                start = t.index('%s+%dc' % (start, len(sep)))
                end = t.index('%s+%dc' % (start, len(txt)))
            t.edit_separator()
            t.configure(autoseparators=True)
            t.undo.end()
            t.tag_remove('sel', '1.0', 'end')
            t.tag_add('ai_new', start, end)
            self._highlight(d)
            t.see(start)
            self.after(2500, lambda: t.tag_remove('ai_new', '1.0', 'end') if d in self.docs else None)
            close()
            self.flash('Uygulandı. Geri almak için Ctrl+Z.')

        def newtab():
            title = '%s · %s' % (d.title, action['label'])
            if d.rich:
                self.new_doc(title=title[:60], blocks=rdoc.markdown_to_blocks(final_text(), images) or [rdoc.para()])
            else:
                self.new_doc(final_text(), title[:60])
            close()

        def copy():
            self.clipboard_clear()
            self.clipboard_append(final_text())
            self.flash('Panoya kopyalandı.')

        mode = action.get('mode')
        if translate_mode == 'newtab':
            self.btn(bar, 'Yeni sekmede aç', newtab, 'primary')
        elif translate_mode == 'below':
            self.btn(bar, 'Seçimin altına ekle', lambda: apply('below'), 'primary')
        elif mode == 'append':
            self.btn(bar, 'Metnin devamına ekle', lambda: apply('append'), 'primary')
        else:
            self.btn(bar, 'Uygula (seçimin yerine)', lambda: apply('replace'), 'primary')
        if translate_mode != 'newtab':
            self.btn(bar, 'Yeni sekmede aç', newtab, 'ghost')
        self.btn(bar, 'Kopyala', copy, 'ghost')
        self.btn(bar, 'Vazgeç', close, 'ghost', side='right')
        win.protocol('WM_DELETE_WINDOW', close)
        win.bind('<Escape>', lambda e: close())
        win.button_bar = bar
        self.review_win = win
        return win

    # ------------------------------------------------------------------ sohbet
    def _chat_append(self, who, text, tag):
        v = self.chat_view
        v.configure(state='normal')
        v.insert('end', who + '\n', tag)
        v.insert('end', text.strip() + '\n', 'body' if tag != 'e' else 'e')
        v.configure(state='disabled')
        v.see('end')

    def send_chat(self, prompt=None, label=None):
        text = prompt or self.chat_in.get('1.0', 'end-1c').strip()
        if not text:
            return
        if not prompt:
            self.chat_in.delete('1.0', 'end')
        document = ''
        d = self.cur()
        v = self.cur_pdf() if not d and hasattr(self, 'pdf_views') else None
        if d and (self.chat_ctx.get() or prompt):
            try:
                s0, e0 = d.text.index('sel.first'), d.text.index('sel.last')
            except tk.TclError:
                s0, e0 = '1.0', d.text.index('end-1c')
            document = d.text.markdown(s0, e0)[0] if d.rich else d.text.get(s0, e0)
        elif v and (self.chat_ctx.get() or prompt):
            # 1.4.7: PDF sekmesinde sohbet belgeyi goremiyordu ("Belge metni paylasilmadi")
            try:
                document, pages_note = self.pdf_context_text(v)
            except Exception as e:
                messagebox.showerror('Sohbet', 'PDF metni okunamadı: %s' % e, parent=self)
                return
            if not document.strip():
                messagebox.showinfo('Sohbet', 'Bu PDF\'de okunabilir metin yok (taranmış belge olabilir). '
                                    'Metin tanıma (OCR) yapılmış bir kopya açın.', parent=self)
                return
            label = (label + ' · ' if label else '') + pages_note
        self.chat_messages.append({'role': 'user', 'content': text})
        self._chat_append('Siz' + (' · ' + label if label else ''), text if not prompt else '(%s)' % (label or 'istek'), 'u')
        msgs = list(self.chat_messages)

        def done(ok, res):
            if not ok:
                self.chat_messages.pop()
                self._chat_append('Hata', res, 'e')
                return
            self.chat_messages.append({'role': 'assistant', 'content': res['text']})
            self._chat_append('AI · %s' % (res.get('model') or res.get('via', '')), res['text'], 'a')
        self._start_job(label or 'Sohbet', ai.run_with_fallback, done, self.backends(), 'chat', msgs, document[:core.MAX_CHARS])

    def pdf_context_text(self, v):
        """Acik PDF'in metni (sayfa sayfa, basliklari ve paragraflariyla Markdown). Sayfa listesinde birden cok
        sayfa seciliyse yalniz onlar. Donus: (metin, 'PDF: n sayfa' notu)."""
        import agfo_pdf_layout as playout
        pr = v.pr
        sel = sorted(v.page_list.curselection())
        idx = sel if len(sel) > 1 else list(range(len(pr.pages)))
        pr.require('extract', pr._page_sources(idx))
        parts = []
        lays = []
        for i in idx:
            p = pr.pages[i]
            try:
                lays.append(playout.extract_layout(pr._pdfium_doc(p['src']), p['index']))
            except Exception:
                lays.append(None)
        sizes = [P_['size'] for lay in lays if lay for P_ in lay['paras'] for _ in range(max(1, len(P_['text']) // 20))]
        body = sorted(sizes)[len(sizes) // 2] if sizes else 11.0
        for i, lay in zip(idx, lays):
            if lay and lay['paras']:
                lines = []
                for P_ in lay['paras']:
                    r = P_['size'] / max(1.0, body)
                    lines.append(('# ' if r >= 1.7 else '## ' if r >= 1.35 else '### ' if r >= 1.15 and P_['bold'] else '') + P_['text'])
                text = '\n\n'.join(lines)
            else:
                text = pr.page_text(i).strip()
            if text:
                parts.append('<!-- Sayfa %d -->\n%s' % (i + 1, text))
        doc = '\n\n'.join(parts)
        note = 'PDF: %s sayfa' % (len(idx) if len(idx) == len(pr.pages) else '%s/%d' % (','.join(str(i + 1) for i in idx), len(pr.pages)))
        if len(doc) > core.MAX_CHARS:
            note += ' (ilk %d karakter)' % core.MAX_CHARS
        return doc, note

    def insert_last_answer(self):
        last = next((m['content'] for m in reversed(self.chat_messages) if m['role'] == 'assistant'), '')
        d = self.cur()
        if last and d:
            self._insert_text(d, last)

    def _insert_text(self, d, text):
        """Yapay zeka yanitini imlece ekler; bicimli belgede Markdown bicimiyle."""
        t = d.text
        if t.rich:
            t.insert_markdown('insert', text)
        else:
            t.edit_separator()
            t.insert('insert', text)
            t.edit_separator()
        self._doc_changed(d)

    def clear_chat(self):
        self.chat_messages = []
        self.chat_view.configure(state='normal')
        self.chat_view.delete('1.0', 'end')
        self.chat_view.configure(state='disabled')

    # ------------------------------------------------------------------ baglanti / ayarlar
    def _refresh_connection_label(self):
        backends = self.backends()
        if not backends:
            self.conn_var.set('● Bağlantı yok — Ayarlar')
            self.conn_lbl.configure(fg=WARN)
            return
        b = backends[0]
        if b.kind == 'direct':
            self.conn_var.set('● Doğrudan: %s · %s' % (ai.PROVIDERS[b.provider]['name'], b.model))
            self.conn_lbl.configure(fg=OK_C)
            self._set_translation_model_label()
            return
        self.conn_var.set('● AI Manager denetleniyor…')

        def done(ok, res):
            if ok:
                self.manager_info = res
                host = ai.urllib.parse.urlsplit(b.base).hostname
                model = res.get('text_model') or res.get('model') or ''
                self.conn_var.set('● AI Manager: %s%s' % (host, (' · ' + model) if model else ''))
                self.conn_lbl.configure(fg=OK_C if res.get('text_ready', True) else WARN)
                self._merge_manager_templates(res.get('templates'))
                self._set_translation_model_label()
            else:
                self.conn_var.set('● AI Manager bağlanamadı' + (' (doğrudan yedek hazır)' if len(backends) > 1 else ''))
                self.conn_lbl.configure(fg=WARN if len(backends) > 1 else BAD_C)
        self._start_job('AI Manager bağlantısı', b.info, done)

    # ------------------------------------------------------------------ 1.4.8: ceviri modeli secimi
    SPEED_ICON = {'fast': 'Hızlı', 'normal': 'Dengeli', 'slow': 'Yavaş (düşünen)'}

    def translation_workers(self):
        try:
            return max(1, min(6, int(self.settings.get('translate_workers', 4))))
        except (TypeError, ValueError):
            return 4

    def _tr_workers_changed(self):
        try:
            self.settings['translate_workers'] = max(1, min(6, int(self.tr_workers_var.get())))
            core.save_settings(self.settings)
        except (tk.TclError, ValueError):
            pass

    def translation_choice(self, backends=None):
        """Kayitli secim, ilk baglantinin turune uyuyorsa {'kind','provider','model'}; yoksa None (varsayilan)."""
        ch = self.settings.get('translate_model')
        if not isinstance(ch, dict) or not ch.get('model'):
            return None
        backends = self.backends() if backends is None else backends
        if not backends:
            return None
        b = backends[0]
        if ch.get('kind') != b.kind or (b.kind == 'direct' and ch.get('provider') != b.provider):
            return None
        return {'kind': ch['kind'], 'provider': ch.get('provider') or '', 'model': ch['model']}

    @classmethod
    def speed_of(cls, model_id, reasoning=False):
        low = (model_id or '').lower()
        if reasoning or re.search(r'(^|[/\-_])(r1|o1|o3|o4)([\-_]|$)|reason|think|deepseek-r', low):
            return 'slow'
        if re.search(r'mini|flash|haiku|lite|nano|small|turbo|instant|(^|[\-_/])(7|8|9|12)b([\-_]|$)', low):
            return 'fast'
        return 'normal'

    def _set_tr_choices(self, items, current=None):
        """items: [{'kind','provider','provider_label','model','speed','quality','cost_1k_words'}]."""
        if not hasattr(self, 'tr_choice_combo'):
            return
        b = (self.backends() or [None])[0]
        default = 'Varsayılan: ' + (('AI Manager › Çeviri rotası' + (' (%s)' % current if current else ''))
                                    if b is not None and b.kind == 'manager' else 'Ayarlar\'daki model')
        order = {'fast': 0, 'normal': 1, 'slow': 2}
        items = sorted(items, key=lambda m: (order.get(m.get('speed'), 1), -(m.get('quality') or 0), m['model']))
        self.tr_choices = [(default, None)]
        for m in items:
            extra = []
            if m.get('quality'):
                extra.append('kalite %d' % m['quality'])
            if m.get('cost_1k_words') is not None:
                extra.append('$%.4f/1000 kelime' % m['cost_1k_words'])
            label = '%s · %s · %s%s' % (self.SPEED_ICON.get(m.get('speed'), '●'), m.get('provider_label') or m['provider'], m['model'],
                                     ('  (' + ', '.join(extra) + ')') if extra else '')
            self.tr_choices.append((label, {'kind': m['kind'], 'provider': m['provider'], 'model': m['model']}))
        self.tr_choice_combo.configure(values=[x[0] for x in self.tr_choices])
        ch = self.translation_choice()
        sel = next((lab for lab, c in self.tr_choices if c and ch and c['model'] == ch['model'] and c['provider'] == ch['provider']), None)
        if sel is None and ch:            # liste henuz gelmedi: kayitli secimi yine de goster
            sel = '%s · %s · %s' % (self.SPEED_ICON.get(self.speed_of(ch['model'])), ch['provider'], ch['model'])
        self.tr_choice_var.set(sel or default)

    def _tr_models_lazy(self):
        if len(getattr(self, 'tr_choices', [])) <= 1 and not getattr(self, '_tr_models_loading', False):
            self.load_translation_models()

    def load_translation_models(self, force=False):
        backends = self.backends()
        if not backends:
            return
        b = backends[0]
        self._tr_models_loading = True

        def work():
            if b.kind == 'manager':
                d = b.translation_models()
                cur = d.get('current') or {}
                items = [dict(m, kind='manager') for m in d['models']]
                return items, cur.get('model') or ''
            name = ai.PROVIDERS[b.provider]['name']
            return [{'kind': 'direct', 'provider': b.provider, 'provider_label': name, 'model': mid, 'speed': self.speed_of(mid)}
                    for mid in b.list_models()], b.model

        def done(ok, res):
            self._tr_models_loading = False
            if not ok:
                if force:
                    msg = res
                    if 'bulunamadı' in res or '404' in res:
                        msg = ('Sitedeki AI Manager model seçimini desteklemiyor (17.8.0 gerekli). WordPress › Eklentiler '
                               'ekranından AI Manager\'ı güncelleyin.')
                    messagebox.showwarning('Çeviri modelleri', msg, parent=self)
                return
            items, cur = res
            self._set_tr_choices(items, cur)
            self.flash('%d çeviri modeli listelendi.' % len(items), 4000)
        self._start_job('Çeviri modelleri alınıyor', work, done)

    def _tr_choice_selected(self):
        lab = self.tr_choice_var.get()
        ch = next((c for l2, c in self.tr_choices if l2 == lab), None)
        if ch is None:
            self.settings['translate_model'] = {}
        else:
            self.settings['translate_model'] = dict(ch)
        core.save_settings(self.settings)
        self._set_translation_model_label()

    def translation_model_text(self):
        """Ceviride kullanilacak model: secilen model, AI Manager'in Ceviri rotasi (yoksa varsayilan metin modeli) ya da dogrudan saglayici."""
        backends = self.backends()
        if not backends:
            return 'Çeviri modeli: bağlantı yok'
        ch = self.translation_choice(backends)
        if ch:
            return 'Çeviri modeli: %s · %s (bu bilgisayarda seçildi)' % (
                ai.PROVIDERS.get(ch['provider'], {}).get('name') or ch['provider'], ch['model'])
        b = backends[0]
        if b.kind == 'direct':
            return 'Çeviri modeli: %s · %s (doğrudan)' % (ai.PROVIDERS[b.provider]['name'], b.model or 'varsayılan')
        info = self.manager_info or {}
        if info.get('translation_ready') and info.get('translation_model'):
            return 'Çeviri modeli: %s · %s (AI Manager › Çeviri rotası)' % (info.get('translation_provider') or '?', info['translation_model'])
        if info.get('text_model'):
            return 'Çeviri modeli: %s · %s (AI Manager varsayılan modeli)' % (info.get('text_provider') or '?', info['text_model'])
        return 'Çeviri modeli: AI Manager (bilgi alınamadı)'

    def _set_translation_model_label(self):
        if hasattr(self, 'tr_model_var'):
            self.tr_model_var.set(self.translation_model_text())
        if len(getattr(self, 'tr_choices', [])) <= 1:
            self._set_tr_choices([], (self.manager_info or {}).get('translation_model') if getattr(self, 'manager_info', None) else None)

    @staticmethod
    def model_label(res):
        prov = res.get('provider') or res.get('via') or ''
        model = res.get('model') or ''
        return ' · '.join(x for x in (prov, model) if x) or 'bilinmeyen model'

    def _merge_manager_templates(self, catalog):
        cur_key = self.actions[self.action_combo.current()][0] if self.action_combo.current() >= 0 else None
        self.actions = core.merge_catalog(catalog)
        self.action_combo.configure(values=[a[1] for a in self.actions])
        idx = next((i for i, a in enumerate(self.actions) if a[0] == cur_key), 0)
        self.action_combo.current(idx)

    def open_settings(self):
        SettingsDialog(self)

    # ------------------------------------------------------------------ guncelleme / kurulum
    def _auto_update_tick(self):
        """1.4.15: arka planda sessiz denetim; is gostergesi/iptal dugmesi acmaz, kullaniciyi bolmez."""
        try:
            self._timers['update'] = self.after(UPDATE_CHECK_MS, self._auto_update_tick)
        except tk.TclError:
            return
        if not self.settings.get('auto_update', True):
            return

        # Sonuc, diger isler gibi self.q kuyrugu uzerinden ana iplige doner (Tk is parcacigi guvenli degil).
        jid = 'update-' + uuid.uuid4().hex
        self.jobs[jid] = lambda ok, res: self._apply_update_result(res if ok else {'status': 'error'}, silent=True)

        def work():
            try:
                self.q.put((jid, True, upd.check(force=False)))
            except Exception as e:          # denetim asla uygulamayi bozmaz
                self.q.put((jid, False, repr(e)))
        threading.Thread(target=work, daemon=True).start()

    def _apply_update_result(self, res, silent=True):
        """Denetim sonucunu arayuze uygular: guncelleme varsa dugme kendiliginden gorunur, yoksa gizlenir."""
        st = (res or {}).get('status')
        if st == 'update':
            self.update_result = res
            ver = res['version']
            self.update_btn.configure(text='⬆ Güncelleme var: v%s' % ver)
            if not self.update_btn.winfo_ismapped():
                self.update_btn.pack(side='right', padx=(0, 8))
            if self._update_shown != ver:
                self._update_shown = ver
                self.title('AGFO AI Editor %s  ·  güncelleme var: v%s' % (core.VERSION, ver))
                self.flash('Yeni sürüm hazır: v%s — sağ üstteki "Güncelleme var" düğmesiyle tek tıkla güncelleyin.' % ver, ms=12000)
            return True
        if st in ('current', 'none', 'skipped'):
            self.update_result = None
            self._update_shown = None
            if self.update_btn.winfo_ismapped():
                self.update_btn.pack_forget()
            self.title('AGFO AI Editor %s' % core.VERSION)
        # 'throttled' / 'error': mevcut durum korunur (gosterilen dugme kaybolmaz)
        return False

    def check_update(self, silent=True):
        def done(ok, res):
            if not ok:
                if not silent:
                    messagebox.showerror('Güncelleme', res, parent=self)
                return
            st = res.get('status')
            if self._apply_update_result(res, silent=silent):
                if not silent:
                    self.do_update()
            elif not silent:
                msg = {'current': 'En güncel sürümü kullanıyorsunuz (%s).' % core.VERSION, 'none': 'GitHub\'da henüz yayınlanmış sürüm yok.',
                       'skipped': 'Bu sürüm atlandı.'}.get(st, res.get('message') or st)
                messagebox.showinfo('Güncelleme', msg, parent=self)
        self._start_job('Güncelleme denetimi', lambda: upd.check(force=not silent), done)

    def do_update(self):
        res = self.update_result
        if not res:
            return
        if not upd.is_frozen():
            messagebox.showinfo('Güncelleme', 'Kaynak koddan çalışıyorsunuz; güncelleme yalnızca EXE sürümünde uygulanır.', parent=self)
            return
        notes = (res['release'].get('notes') or '')[:1200]
        if not messagebox.askyesno('Güncelleme v%s' % res['version'], 'Yeni sürüm indirilecek ve uygulama yeniden açılacak.\n\n%s\n\nDevam edilsin mi?'
                                   % notes, parent=self):
            return
        for d in list(self.docs):
            if d.dirty and not self.save(d):
                return

        def done(ok, path):
            if not ok:
                messagebox.showerror('Güncelleme', path, parent=self)
                return
            try:
                proc = upd.apply_update(path)
            except OSError as e:
                upd.log_line('Updater could not start: %r' % e)
                self._update_blocked(path, str(e))
                return
            self.flash('Güncelleyici başlatıldı, denetleniyor…')
            # Guvenlik yazilimi yeni EXE'yi engellerse surec hemen kapanir: kapanmadan once dogrula.
            self.after(2500, lambda: self._confirm_updater(proc, path))
        self._start_job('Güncelleme indiriliyor', upd.download, done, res)

    def _confirm_updater(self, proc, path):
        code = proc.poll()
        if code is None:
            upd.log_line('Updater alive; closing old version.')
            self.destroy()
            return
        upd.log_line('Updater exited early with code %s' % code)
        self._update_blocked(path, 'Güncelleyici hemen kapandı (çıkış kodu %s).' % code)

    def _update_blocked(self, path, reason):
        messagebox.showerror('Güncelleme başlatılamadı',
                             '%s\n\nYeni sürüm indirildi ama Windows ya da bir güvenlik yazılımı onu çalıştırmayı engelledi.\n\n'
                             'Dosya: %s\n\nÇözüm: Trust-AgfoAiEditor.cmd betiğini çalıştırın (dosyayı GitHub ile doğrulayıp güvenli '
                             'işaretler), sonra bu dosyayı çift tıklayıp açın; açılınca kurulu sürümü değiştirmeyi önerir.\n\n'
                             'Uygulama açık kalıyor; çalışmanız kaybolmadı.' % (reason, path), parent=self)

    def _offer_install(self):
        if not (IS_WIN and upd.is_frozen()):
            return
        upd.cleanup_downloads(keep=sys.executable)
        if upd.running_installed():
            return
        inst = upd.installed_exe()
        if inst.exists():
            # Disaridan (Indirilenler / guncelleme klasoru) yeni bir surum acildi: kurulu kopyayi yenile.
            try:
                same = inst.stat().st_size == os.path.getsize(sys.executable) and \
                    upd.file_sha256(inst) == upd.file_sha256(sys.executable)
            except OSError:
                same = False
            if same:
                return
            if messagebox.askyesno('Kurulu sürümü güncelle', 'Bu bilgisayarda kurulu AGFO AI Editor bu sürümle (%s) değiştirilsin mi?\n\n%s'
                                   % (core.VERSION, inst), parent=self):
                try:
                    upd.replace_target(sys.executable, inst, attempts=10)
                    upd.log_line('Installed copy replaced from %s' % sys.executable)
                    messagebox.showinfo('Kurulum', 'Kurulu sürüm güncellendi. Başlat menüsündeki kısayol artık %s sürümünü açar.'
                                        % core.VERSION, parent=self)
                except OSError as e:
                    messagebox.showerror('Kurulum', 'Kurulu sürüm değiştirilemedi (açık olabilir): %s' % e, parent=self)
            return
        if self.settings.get('install_declined'):
            return
        self.install(ask=True)

    def install(self, ask=True):
        if ask:
            ans = messagebox.askyesnocancel('Kurulum', 'AGFO AI Editor bu bilgisayara kurulsun mu?\n\n'
                                            'Kullanıcı klasörünüze kopyalanır, Başlat menüsüne ve masaüstüne kısayol eklenir. '
                                            'Yönetici yetkisi gerekmez.\n\nHayır: bir daha sorma', parent=self)
            if ans is None:
                return
            if ans is False:
                self.settings['install_declined'] = True
                core.save_settings(self.settings)
                return
        try:
            dst = upd.install_self(desktop=True)
        except OSError as e:
            messagebox.showerror('Kurulum', str(e), parent=self)
            return
        messagebox.showinfo('Kurulum', 'Kuruldu: %s\nBaşlat › AGFO › AGFO AI Editor' % dst, parent=self)

    def uninstall(self):
        if messagebox.askyesno('Kaldır', 'Program ve kısayollar kaldırılsın mı? Ayarlarınız ve kurtarma kayıtları korunur.', parent=self):
            for d in list(self.docs):
                if d.dirty and not self.close_doc(d):
                    return
            upd.uninstall()
            self.destroy()


class SettingsDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        s = app.settings
        self.title('Ayarlar')
        self.configure(bg=PANEL)
        self.transient(app)
        self.geometry('+%d+%d' % (app.winfo_rootx() + 120, app.winfo_rooty() + 70))
        nb = ttk.Notebook(self, style='Panel.TNotebook')
        nb.pack(fill='both', expand=True, padx=12, pady=12)
        f = ttk.Frame(nb, padding=14)
        nb.add(f, text='Bağlantı')
        self.mode = tk.StringVar(value=s['mode'])
        for v, t in (('auto', 'Otomatik: önce AI Manager, olmazsa doğrudan anahtar'), ('manager', 'Yalnızca AI Manager (önerilir)'),
                     ('direct', 'Yalnızca doğrudan sağlayıcı')):
            ttk.Radiobutton(f, text=t, value=v, variable=self.mode).pack(anchor='w')
        g1 = tk.LabelFrame(f, text=' AGFO AI Manager (WordPress) ', bg=PANEL, fg=ACCENT, font=('Segoe UI', 9, 'bold'), bd=1, padx=10, pady=8,
                           relief='solid', highlightbackground='#2d4a6c')
        g1.pack(fill='x', pady=(10, 6))
        self.url = tk.StringVar(value=s['manager_url'])
        self.user = tk.StringVar(value=s['manager_user'])
        self.pw = tk.StringVar()
        self.token = tk.StringVar()
        has_pw = bool(s.get('manager_secret'))
        has_tok = bool(s.get('manager_token'))
        self._row(g1, 0, 'Site adresi', ttk.Entry(g1, textvariable=self.url, width=50))
        self._row(g1, 1, 'Bağlantı anahtarı', ttk.Entry(g1, textvariable=self.token, width=50, show='•'))
        app.lbl(g1, ('Kayıtlı (değiştirmek için yapıştırın). ' if has_tok else '') +
                'Önerilen yol: WordPress › AI Manager › 🖊️ AI Editor bağlantısı › "Anahtar oluştur" ve çıkan değerin tamamını '
                'buraya yapıştırın. API anahtarlarınız sitede kalır.', muted=True, wraplength=500).grid(row=2, column=1, sticky='w', pady=(2, 8))
        self._row(g1, 3, 'Kullanıcı adı', ttk.Entry(g1, textvariable=self.user, width=50))
        self._row(g1, 4, 'Uygulama parolası', ttk.Entry(g1, textvariable=self.pw, width=50, show='•'))
        app.lbl(g1, ('Kayıtlı. ' if has_pw else '') + 'İsteğe bağlı: anahtar yoksa WordPress Uygulama Parolası ile de bağlanabilir.',
                muted=True, wraplength=500).grid(row=5, column=1, sticky='w', pady=(2, 6))
        r = tk.Frame(g1, bg=PANEL)
        r.grid(row=6, column=1, sticky='w')
        app.btn(r, 'Bağlantıyı test et', self.test_manager, 'normal')
        self.forget_btn = app.btn(r, 'Kayıtlı bilgileri sil', self.forget_manager, 'ghost')
        self.m_res = app.lbl(g1, '', muted=True, wraplength=500)
        self.m_res.grid(row=7, column=1, sticky='w', pady=(4, 0))

        g2 = tk.LabelFrame(f, text=' Doğrudan sağlayıcı ', bg=PANEL, fg=ACCENT, font=('Segoe UI', 9, 'bold'), bd=1, padx=10, pady=8, relief='solid')
        g2.pack(fill='x', pady=6)
        self.prov = tk.StringVar(value=s['direct_provider'] if s['direct_provider'] in ai.PROVIDERS else 'openai')
        self.prov_names = {v['name']: k for k, v in ai.PROVIDERS.items()}
        self.prov_disp = tk.StringVar(value=ai.PROVIDERS[self.prov.get()]['name'])
        pc = ttk.Combobox(g2, textvariable=self.prov_disp, values=list(self.prov_names), state='readonly', width=30)
        pc.bind('<<ComboboxSelected>>', lambda e: self._prov_changed())
        self._row(g2, 0, 'Sağlayıcı', pc)
        self.model = tk.StringVar(value=s.get('direct_model') or ai.PROVIDERS[self.prov.get()]['default'])
        self.model_cb = ttk.Combobox(g2, textvariable=self.model, values=ai.PROVIDERS[self.prov.get()]['suggest'], width=42)
        self._row(g2, 1, 'Model', self.model_cb)
        self.key = tk.StringVar()
        self._row(g2, 2, 'API anahtarı', ttk.Entry(g2, textvariable=self.key, width=44, show='•'))
        self.key_info = app.lbl(g2, '', muted=True, wraplength=480)
        self.key_info.grid(row=3, column=1, sticky='w')
        r2 = tk.Frame(g2, bg=PANEL)
        r2.grid(row=4, column=1, sticky='w', pady=(4, 0))
        app.btn(r2, 'Modelleri getir', self.fetch_models, 'ghost')
        app.btn(r2, 'Test et', self.test_direct, 'normal')
        self.d_res = app.lbl(g2, '', muted=True, wraplength=480)
        self.d_res.grid(row=5, column=1, sticky='w', pady=(4, 0))
        self._prov_changed(init=True)

        e = ttk.Frame(nb, padding=14)
        nb.add(e, text='Editör')
        self.font_family = tk.StringVar(value=s['font_family'])
        fams = sorted(set(['Segoe UI', 'Calibri', 'Cambria', 'Georgia', 'Consolas', 'Times New Roman', 'Arial']) &
                      set(tkfont.families()) | {'Segoe UI'})
        self._row(e, 0, 'Yazı tipi', ttk.Combobox(e, textvariable=self.font_family, values=fams, width=26))
        self.font_size = tk.IntVar(value=s['font_size'])
        self._row(e, 1, 'Yazı boyutu', ttk.Spinbox(e, from_=8, to=36, textvariable=self.font_size, width=6))
        self.wrap = tk.BooleanVar(value=s['wrap'])
        ttk.Checkbutton(e, text='Satırları pencereye sığdır', variable=self.wrap).grid(row=2, column=1, sticky='w', pady=4)

        u = ttk.Frame(nb, padding=14)
        nb.add(u, text='Güncelleme')
        self.auto_upd = tk.BooleanVar(value=s['auto_update'])
        ttk.Checkbutton(u, text='GitHub\'dan yeni sürümü kendiliğinden denetle (açılışta ve 30 dakikada bir)', variable=self.auto_upd).pack(anchor='w')
        app.lbl(u, 'Sürüm %s · github.com/downtownck/agfo-windows-apps (etiket ai-editor-v*)\nİndirilen dosya SHA-256 ile doğrulanır.' % core.VERSION,
                muted=True).pack(anchor='w', pady=8)
        app.btn(u, 'Şimdi denetle', lambda: app.check_update(silent=False), 'normal', side=None).pack(anchor='w')

        b = tk.Frame(self, bg=PANEL, padx=12, pady=10)
        b.pack(fill='x')
        app.btn(b, 'Kaydet', self.save, 'primary', side='right')
        app.btn(b, 'Vazgeç', self.destroy, 'ghost', side='right')
        self.bind('<Escape>', lambda e: self.destroy())
        self.grab_set()

    def _row(self, parent, r, label, widget):
        tk.Label(parent, text=label, fg=MUTED, bg=PANEL, font=('Segoe UI', 9)).grid(row=r, column=0, sticky='w', padx=(0, 10), pady=3)
        widget.grid(row=r, column=1, sticky='w', pady=3)

    def _prov_changed(self, init=False):
        self.prov.set(self.prov_names.get(self.prov_disp.get(), 'openai'))
        spec = ai.PROVIDERS[self.prov.get()]
        self.model_cb.configure(values=spec['suggest'])
        if not init:
            self.model.set(spec['default'])
        stored = (self.app.settings.get('direct_keys') or {}).get(self.prov.get(), '')
        self.key_info.configure(text='Kayıtlı anahtar var (Windows hesabınıza şifreli). Değiştirmek için yazın.' if stored else
                                'Anahtar Windows DPAPI ile yalnız sizin hesabınızda çözülebilecek şekilde saklanır.')

    def _manager(self):
        pw = self.pw.get().strip() or secrets.unprotect(self.app.settings.get('manager_secret', ''))
        tok = self.token.get().strip() or secrets.unprotect(self.app.settings.get('manager_token', ''))
        return ai.ManagerBackend(self.url.get(), self.user.get(), pw, tok)

    def forget_manager(self):
        for k in ('manager_secret', 'manager_token'):
            self.app.settings[k] = ''
        self.pw.set('')
        self.token.set('')
        core.save_settings(self.app.settings)
        self.m_res.configure(text='Kayıtlı anahtar ve parola silindi.', fg=MUTED)

    def _direct(self):
        key = self.key.get().strip() or secrets.unprotect((self.app.settings.get('direct_keys') or {}).get(self.prov.get(), ''))
        return ai.DirectBackend(self.prov.get(), key, self.model.get())

    def test_manager(self):
        try:
            b = self._manager()
        except ai.AIError as e:
            self.m_res.configure(text=str(e), fg=BAD_C)
            return
        self.m_res.configure(text='Denetleniyor…', fg=MUTED)

        def done(ok, res):
            if not self.winfo_exists():
                return
            if ok and isinstance(res, dict) and 'ok' in res:
                if not res['ok']:
                    self.m_res.configure(text=res['message'], fg=BAD_C)
                    return
                res = res['info']
            if ok:
                t = 'Bağlandı: AI Manager %s · kullanıcı %s · %d şablon · metin: %s%s' % (
                    res.get('plugin_version', '?'), res.get('user', '?'), len(res.get('templates') or {}),
                    res.get('text_provider') or '-', (' / ' + res['text_model']) if res.get('text_model') else '')
                if not res.get('text_ready', True):
                    t += '\n⚠ Sitede metin sağlayıcısı/modeli ayarlı değil (AI Manager › Kontrol Merkezi).'
                self.m_res.configure(text=t, fg=OK_C if res.get('text_ready', True) else WARN)
            else:
                self.m_res.configure(text=res, fg=BAD_C)
        self.app._start_job('AI Manager testi', b.diagnose, done)

    def test_direct(self):
        b = self._direct()
        self.d_res.configure(text='Denetleniyor…', fg=MUTED)

        def done(ok, res):
            if self.winfo_exists():
                self.d_res.configure(text=('Çalışıyor: %s · %s' % (res['provider'], res['model'])) if ok else res, fg=OK_C if ok else BAD_C)
        self.app._start_job('Sağlayıcı testi', b.complete, done, 'Reply with the single word: OK', 'Test', 64)

    def fetch_models(self):
        b = self._direct()

        def done(ok, res):
            if not self.winfo_exists():
                return
            if ok and res:
                self.model_cb.configure(values=res)
                self.d_res.configure(text='%d model bulundu; listeden seçin.' % len(res), fg=OK_C)
            else:
                self.d_res.configure(text=res if not ok else 'Model bulunamadı.', fg=BAD_C)
        self.app._start_job('Model listesi', b.list_models, done)

    def save(self):
        s = self.app.settings
        if self.url.get().strip():
            try:
                s['manager_url'] = ai.ManagerBackend.normalize_url(self.url.get())
            except ai.AIError as e:
                messagebox.showerror('Ayarlar', str(e), parent=self)
                return
        else:
            s['manager_url'] = ''
        s['manager_user'] = self.user.get().strip()
        if self.pw.get().strip():
            s['manager_secret'] = secrets.protect(self.pw.get().strip())
        if self.token.get().strip():
            tok = re.sub(r'\s+', '', self.token.get())
            if not re.match(r'^agfoed\.\d+\.[a-z0-9]{8}\.[A-Za-z0-9]{40}$', tok):
                messagebox.showerror('Ayarlar', 'Bağlantı anahtarı eksik ya da hatalı kopyalanmış. "agfoed." ile başlayan değerin '
                                     'tamamını yapıştırın.', parent=self)
                return
            s['manager_token'] = secrets.protect(tok)
        s['mode'] = self.mode.get()
        s['direct_provider'] = self.prov.get()
        s['direct_model'] = self.model.get().strip()
        if self.key.get().strip():
            keys = dict(s.get('direct_keys') or {})
            keys[self.prov.get()] = secrets.protect(self.key.get().strip())
            s['direct_keys'] = keys
        s['font_family'] = self.font_family.get() or 'Segoe UI'
        try:
            s['font_size'] = max(8, min(36, int(self.font_size.get())))
        except (tk.TclError, ValueError):
            pass
        s['wrap'] = bool(self.wrap.get())
        s['auto_update'] = bool(self.auto_upd.get())
        core.save_settings(s)
        for d in self.app.docs:
            d.text.configure(font=self.app._editor_font(), wrap='word' if s['wrap'] else 'none')
        self.app._refresh_connection_label()
        self.destroy()


# ---------------------------------------------------------------------------- duman testi (CI ekran goruntusu)
SAMPLE = ('# Gıda güvenliği kültürü neden önemlidir?\n\n'
          'Gıda güvenliği kültürü bir şirkette herkesin gıda güvenliğini önemsemesi demektir. Bu çok önemlidir çünkü '
          'gıda güvenliği önemlidir ve müşteriler güvenli ürün ister. Birçok şirket bunu yapıyor ama bazıları yapmıyor.\n\n'
          'BRCGS Issue 9 madde 1.1.2 üst yönetimin gıda güvenliği ve kalite kültürü planını gerektirir. Planda ölçülebilir '
          'hedefler, eylemler ve zaman çizelgesi bulunmalıdır.\n\n'
          '- Çalışan anketleri\n- Eğitim kayıtları\n- Yönetim gözden geçirmesi')


def smoke(out_png: str) -> int:
    """CI: pencereyi kurar, ornek belge + fark penceresi acar, ekran goruntusu alir."""
    app = App(smoke=True)
    sw, sh = app.winfo_screenwidth(), app.winfo_screenheight()
    app.geometry('%dx%d+0+0' % (min(1280, sw), min(800, sh - 40)))
    d = app.cur()
    blocks = rdoc.markdown_to_blocks(SAMPLE)
    try:
        from PIL import Image, ImageDraw
        import io as _io
        im = Image.new('RGB', (640, 220), (234, 242, 250))
        dr = ImageDraw.Draw(im)
        for k, (hgt, col) in enumerate(((120, (31, 111, 163)), (170, (73, 179, 239)), (90, (226, 179, 86)), (150, (111, 211, 155)))):
            dr.rectangle((60 + k * 140, 200 - hgt, 150 + k * 140, 200), fill=col)
        buf = _io.BytesIO()
        im.save(buf, 'PNG')
        blocks.insert(3, rdoc.image_block(buf.getvalue(), 300, 103, align='center'))
    except Exception as e:
        print('image failed', e)
    blocks.append({'t': 'table', 'rows': [[[rdoc.run('Gösterge', b=True)], [rdoc.run('2025', b=True)], [rdoc.run('2026', b=True)]],
                                          [[rdoc.run('Eğitim saati / kişi')], [rdoc.run('6')], [rdoc.run('9')]],
                                          [[rdoc.run('Ramak kala bildirimi')], [rdoc.run('14')], [rdoc.run('41')]]]})
    d.text.load_blocks(blocks)
    d.title = 'gida-guvenligi-kulturu.docx'
    app.nb.tab(d.frame, text=app._tab_title(d))
    d.text.tag_add('sel', '2.0', '2.end')
    d.text.mark_set('insert', '2.5')
    app._sync_fmt_bar()
    app.conn_var.set('● AI Manager: agfocert.com · gpt-5.5')
    app.conn_lbl.configure(fg=OK_C)
    app.chat_messages = [{'role': 'user', 'content': 'Bu yazının en zayıf yeri neresi?'}]
    app._chat_append('Siz', 'Bu yazının en zayıf yeri neresi?', 'u')
    app._chat_append('AI · gpt-5.5', '1. Paragraf döngüsel gerekçe içeriyor ("önemlidir çünkü önemlidir").\n2. "Birçok şirket" iddiası kanıtsız.', 'a')
    app.update()
    shots = []

    def grab(name):
        app.update()
        app.after(300)
        app.update()
        try:
            from PIL import ImageGrab
            x, y = app.winfo_rootx(), app.winfo_rooty()
            img = ImageGrab.grab(bbox=(x, y, x + app.winfo_width(), y + app.winfo_height()), all_screens=True)
            shots.append(img)
        except Exception as e:
            print('grab failed', e)
    grab('main')
    # 1.2: Kaynaklar sekmesi (ornek belge + atifli yanit)
    try:
        import tempfile
        sp = os.path.join(tempfile.gettempdir(), 'BRCGS-Food-9-ornek.txt')
        pathlib.Path(sp).write_text('Madde 4.11.2 Temizlik prosedürleri doğrulanmalı ve sonuçları kayıt altına alınmalıdır.\n\n'
                                    'Madde 5.3.1 Alerjen risk değerlendirmesi yapılmalıdır.', encoding='utf-8')
        doc = srcs.extract(sp)
        doc['name'] = 'BRCGS-Food-9.pdf'
        app.src_docs['smoke'] = doc
        app.src_tree.insert('', 'end', iid='smoke', text=doc['name'], values=(312, '1.048.220'))
        app.src_tree.insert('', 'end', iid='smoke2', text='Denetim-raporu-2026.docx', values=(14, '86.410'))
        app._source_summary()
        app.src_info.configure(text='2 belge · 1.134.630 karakter metin')
        app.src_tree.selection_set('smoke')
        app._switch_scope()
        app._src_view_append('Soru: Temizlik doğrulaması için ne isteniyor?\n', 'q')
        _ctx, labs = srcs.build_context(srcs.chunk_units('smoke', doc))
        app._render_answer('Temizlik prosedürlerinin etkinliği doğrulanmalı ve doğrulama sonuçları kayıt altına alınmalıdır [K1]. '
                           'Raporda bu kayıtların eksik olduğu belirtilmiş.', labs)
        app._src_view_append('AI Manager · 9 parça (yerel arama) · gpt-5.5\n', 'meta')
        app.ai_nb.select(4)
        grab('sources')
        app.ai_nb.select(0)
    except Exception as e:
        print('sources shot failed', e)
    # 1.3: PDF duzenleyici (layout gorunumu)
    try:
        import tempfile
        pp = agfo_pdf.write_simple_pdf(os.path.join(tempfile.gettempdir(), 'BRCGS-denetim-raporu.pdf'), [
            ['Denetim Raporu - Ozet', 'Firma: Ornek Gida A.S.   Standart: BRCGS Food Safety Issue 9', '',
             'Madde 4.11.2 Temizlik prosedurleri dogrulanmali ve kayit altina alinmalidir.',
             'Bulgu: Soguk oda temizlik dogrulama kayitlari son 3 ayda eksik.', '',
             'Madde 5.3.1 Alerjen risk degerlendirmesi yapilmistir.', 'Sonuc: Uygun.'],
            ['Ek 1 - Kanit listesi', 'Temizlik plani rev. 4', 'ATP test sonuclari'], ['Ek 2 - Fotograflar']])
        v = app.open_pdf(pp)
        app.update()
        v.pr.add_overlay(0, {'type': 'highlight', 'rect': (58, 112, 470, 128), 'color': 'ffeb3b'})
        v.pr.add_overlay(0, {'type': 'note', 'rect': (480, 110, 498, 128), 'text': 'Kanit iste'})
        v.pr.add_overlay(0, {'type': 'text', 'rect': (58, 176, 420, 194), 'text': 'Sonuç: Uygun (denetçi onaylı)',
                             'size': 11, 'color': '1f6a4a', 'whiteout': True, 'bold': True})
        v.pr.add_overlay(0, {'type': 'box', 'rect': (52, 108, 500, 130), 'color': 'e03131', 'width': 1.5})
        try:                                       # 1.4: yerinde metin duzenleme (gercek PDF metni)
            bx = v.pr.pages[0]['box']
            hit = None
            for yy in range(int(bx[3]) - 40, 0, -4):
                info = v.pr.find_text_line(0, *agfo_pdf.user_to_display(80, yy, bx, 0))
                if info and info['text'].startswith('Bulgu'):
                    hit = info
                    break
            if hit:
                v.pr.edit_text(0, hit, 'Bulgu: Soğuk oda temizlik doğrulama kayıtları son 3 ayda eksik (2 kayıt bulundu).')
        except Exception as e:
            print('pdf edit failed', e)
        app.toggle_ai_panel()
        v.relayout()
        v.page_list.selection_set(0)
        for _ in range(30):
            app.update()
        try:
            v.tool.set('edit_text')
            v._tool_changed()
            info = v.pr.find_text_line(0, *agfo_pdf.user_to_display(80, 750, v.pr.pages[0]['box'], 0))
            if info:
                a_, b_, c_, d_ = info['drect']
                v._do_hover(v.page_x[0] + (a_ + 30) * v.zoom - v.canvas.canvasx(0),
                            v.page_y[0] + (b_ + d_) / 2 * v.zoom - v.canvas.canvasy(0), 'edit_text')
        except Exception as e:
            print('hover failed', e)
        app.after(400)
        app.update()
        grab('pdf')
    except Exception as e:
        print('pdf shot failed', e)
    # 1.4: yan yana ceviri
    try:
        orig = d.text.get_blocks()
        en = {'Gıda güvenliği kültürü neden önemlidir?': 'Why does food safety culture matter?',
              'Çalışan anketleri': 'Employee surveys', 'Eğitim kayıtları': 'Training records',
              'Yönetim gözden geçirmesi': 'Management review', 'Gösterge': '**Indicator**',
              'Eğitim saati / kişi': 'Training hours / person', 'Ramak kala bildirimi': 'Near-miss reports'}
        segs = dtr.segments(orig)
        done = {}
        for n, (_key, md) in enumerate(segs):
            plain = md.replace('**', '')
            if plain in en:
                done[n] = en[plain]
            elif plain.startswith('Gıda güvenliği kültürü bir'):
                done[n] = ('Food safety culture means that everyone in a company cares about food safety. This is very important '
                           'because food safety is important and customers want safe products.')
            elif plain.startswith('BRCGS'):
                done[n] = ('BRCGS Issue 9 clause 1.1.2 requires senior management to have a food safety and quality culture plan. '
                           'The plan must include measurable objectives, actions and a timeline.')
        trans = dtr.apply(orig, segs, done)
        app.open_compare(orig, trans, 'gida-guvenligi-kulturu', 'Özgün', 'English')
        for _ in range(10):
            app.update()
        grab('compare')
        app.close_compare(app.nametowidget(app.nb.select()))
    except Exception as e:
        print('compare shot failed', e)
    app.nb.select(d.frame)
    ms, me = 'ais_x', 'aie_x'
    d.text.mark_set(ms, '3.0')
    d.text.mark_set(me, '3.end')
    src = d.text.get('3.0', '3.end')
    res = {'text': 'Gıda güvenliği kültürü, bir işletmede yöneticiden sahadaki çalışana kadar herkesin gıda güvenliğini '
                   'günlük kararlarının parçası hâline getirmesidir. Müşteriler ve denetim kuruluşları güvenli ürünün '
                   'tesadüf değil, sistemin sonucu olmasını bekler.',
           'via': 'AI Manager', 'provider': 'OpenAI', 'model': 'gpt-5.5'}
    win = app.review(d, ms, me, src, res, core.action_by_key('content_strengthen'))
    win.geometry('%dx%d+20+20' % (min(1000, sw - 40), min(560, sh - 80)))
    app.update()
    try:
        from PIL import ImageGrab
        app.update()
        app.after(300)
        app.update()
        x, y = win.winfo_rootx(), win.winfo_rooty()
        shots.append(ImageGrab.grab(bbox=(x, y, x + win.winfo_width(), y + win.winfo_height()), all_screens=True))
    except Exception as e:
        print('grab failed', e)
    win.destroy()
    SettingsDialog(app)
    app.update()
    try:
        from PIL import Image
        if shots:
            w = max(s.width for s in shots)
            h = sum(s.height for s in shots) + 16 * (len(shots) - 1)
            sheet = Image.new('RGB', (w, h), BG)
            y = 0
            for s in shots:
                sheet.paste(s, (0, y))
                y += s.height + 16
            sheet.save(out_png)
    except Exception as e:
        print('sheet failed', e)
    print('AGFO EDITOR SMOKE OK: %d docs, %d actions, %d shots' % (len(app.docs), len(app.actions), len(shots)))
    app.destroy()
    return 0


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == '--smoke':
        return smoke(sys.argv[2])
    files = [a for a in sys.argv[1:] if not a.startswith('--') and os.path.isfile(a)]
    try:
        app = App(files)
    except Exception:
        err = traceback.format_exc()
        try:
            with open(core.data_dir() / 'error-log.txt', 'a', encoding='utf-8') as f:
                f.write(ai.redact(err) + '\n')
        except OSError:
            pass
        try:
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror('AGFO AI Editor açılamadı', 'Başlangıç hatası (ayrıntı: %s):\n\n%s'
                                 % (core.data_dir() / 'error-log.txt', err[-1500:]))
            r.destroy()
        except Exception:
            pass
        return 1
    app.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
