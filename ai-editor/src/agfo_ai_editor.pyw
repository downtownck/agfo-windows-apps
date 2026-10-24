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
import subprocess
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
import agfo_speech as speech  # noqa: E402  # 1.5: seslendirme
import agfo_readaloud as readaloud  # noqa: E402  # 1.6: sesli oku
import agfo_localtts as localtts  # noqa: E402  # 1.7: bu bilgisayardaki ses servisi
import agfo_spell as spell  # noqa: E402  # 2.0: yazim denetimi


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
        # 2.0: Word bicimleri + sayfa yapisi / ust-alt bilgi / sayfa no. gidis-donus, yazim denetimi modulu EXE'de
        import agfo_spell as _sp2
        v2 = [_r.para([_r.run('A', font='Georgia', size=14, s=True, hl='FFFF00'), _r.run('2', va='sup'),
                       _r.run(' b', u=True, color='0563C1', href='https://agfo.app')], ls=1.5, sb=6, ind=36, fi=-18)]
        v2page = {'orient': 'landscape', 'header': 'Üst', 'pnum': {'pos': 'footer', 'align': 'right', 'fmt': 'n'}}
        with open(dp, 'wb') as fh:
            fh.write(_r.docx_bytes(v2, v2page))
        b2, pg2 = _r.read_docx_blocks(dp), _r.read_docx_page(dp)
        os.unlink(dp)
        res['v2_docx'] = (b2[0]['runs'] == _r.merge_runs(v2[0]['runs']) and b2[0].get('ls') == 1.5 and b2[0].get('fi') == -18
                          and pg2['orient'] == 'landscape' and pg2['header'] == 'Üst' and pg2['pnum']['align'] == 'right')
        res['spell'] = _sp2.utf16_map('a😀b')(3) == 2
        if IS_WIN:
            _ws = _sp2.WinSpeller('en-US')
            res['spell_windows'] = {'available': _ws.available, 'error': _ws.error,
                                    'errors': len(_ws.check('This is a smple test')) if _ws.available else None}
        res['ok'] = res['ok'] and res['v2_docx'] and res['spell']
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
        import agfo_speech as _sp   # 1.5: seslendirme modulu EXE'de
        res['speech'] = _sp.markdown_to_speech('# Başlık\n\n- madde') == 'Başlık.\n\nmadde.'
        import agfo_readaloud as _ra  # 1.6: sesli oku
        import agfo_localtts as _lt   # 1.7: bu bilgisayardaki ses servisi
        res['speech'] = res['speech'] and _lt.read_config(os.path.join(tempfile.gettempdir(), 'agfo-yok', '.env')) is None
        res['speech'] = res['speech'] and _ra.group_paragraphs(['a', '', 'b'], False) == [(0, 0), (2, 2)] and \
            [x['title'] for x in _sp.plan_sections('## A\n\n' + 'x. ' * 200 + '\n\n## B\n\n' + 'y. ' * 200)] == ['A', 'B']
        res['ok'] = res['ok'] and res['speech']
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
        # 2.2: BRCGS - sablonlar pakette mi, lxml var mi, 5 sablon yaz -> oku (kutu, alan, NA)
        from agfo_brcgs import boxes as _bb, data as _bd, docx_engine as _be, guide as _bg
        _brs = {}
        for _pf in _bd.PROFILES:
            _secs = _bb.sections_for_profile(_pf)
            _secs[0]['value'] = 'Selftest %s ğüş' % _pf
            _blob, _st = _be.write_report({'profile': _pf, 'values': {'BRC_SITE_CODE': '1234567'}, 'sections': _secs,
                                           'na_clauses': [{'clause_ref': '%s.9' % _bb.chapter_of(_secs[0]['clause']), 'justification': 'x'}]})
            _back = _be.read_report(_blob)
            _brs[_pf] = (_back['profile'] == _pf and _back['values'].get('BRC_SITE_CODE') == '1234567'
                         and _back['sections'][0]['value'] == 'Selftest %s ğüş' % _pf and len(_back['na_clauses']) == 1
                         and _bg.form_for(_pf, _secs[0]['clause']) is not None
                         and _bd.excel_template_path(_pf).is_file())
        res['brcgs'] = _brs
        # 2.3.0: Word gorunumu - PDF'te alan konumlari bulunur (cizici gerekmez), dil dosyasi pakette
        import agfo_docrender as _dr
        import agfo_wordview  # noqa: F401
        from agfo_brcgs import i18n as _bi
        _pp = os.path.join(tempfile.gettempdir(), 'agfo-editor-selftest-anchor.pdf')
        _p.write_simple_pdf(_pp, [['Report', 'Company name Selftest Ltd', 'Scope of audit packing']])
        with open(_pp, 'rb') as _fh:
            _anc = _dr.anchors(_fh.read(), [('A', 'Selftest Ltd'), ('B', 'packing')])
        os.unlink(_pp)
        _brs['wordview'] = [a[0] for a in _anc] == ['A', 'B'] and _bi.guide('Hayır') == 'No'
        # 2.5.0: teknik gozden gecirme kaynaklari pakette (5 standart) ve kontroller calisiyor
        from agfo_brcgs import review as _rv, review_pack as _rp
        _brs['review'] = all(len(_rp.pack(_x)['skill']) > 3000 and len(_rp.pack(_x)['guide']) > 30000 for _x in _bd.PROFILES) and \
            any(f['rule'] == 'clause_claim' for f in _rv.run(
                {'profile': 'fs', 'values': {}, 'sections': [{'clause': '1.1', 'value': 'It meets the requirements of clause 1.1.1.'}],
                 'meta': {}}, []))
        res['renderer'] = _dr.Renderer(os.path.join(tempfile.gettempdir(), 'agfo-selftest-render')).engine or 'none'
        res['ok'] = (res['ok'] and res['rich_docx'] == ['p', 'p', 'p', 'img', 'table'] and tr[0]['runs'][0]['text'] == 'Title'
                     and res['pdf_edit']['ok'] and res['pdf_edit']['layout_translate'] and res['pdf_edit']['font_subset']
                     and all(_brs.values()))
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

# 2.0: iki tema. Renkler modul degiskenidir; tema acilista (ayarlardan) uygulanir, degisiklik yeniden baslatinca gecer.
THEMES = {
    'dark': dict(BG='#0a1425', PANEL='#12243b', PANEL2='#192e48', FG='#ecf3ff', MUTED='#a5b6ce', ACCENT='#49b3ef',
                 WARN='#e2b356', OK_C='#6fd39b', BAD_C='#ff8a80', EDIT_BG='#0e1b2e', SEL_BG='#285475', PRIMARY='#1f6fa3',
                 LINE='#2d4a6c', SEL_FG='#ffffff', BTN_FG='#ffffff', HOVER='#22405f', INACTIVE_SEL='#1d3b57',
                 FOUND='#5a4a1c', NEW_BG='#173a2a', WORK_BG='#4a3f12', READ_BG='#24452c', DEL_BG='#3a1d22', INS_FG='#b9f5cf',
                 HEAD_FG='#ffffff', DESK='#5c6676', RIBBON='#12243b', TITLE_BG='#0a1425'),
    'light': dict(BG='#eef1f5', PANEL='#ffffff', PANEL2='#eef2f7', FG='#1b2430', MUTED='#5b6b80', ACCENT='#1f6fa3',
                  WARN='#9a6b00', OK_C='#1f7a4a', BAD_C='#c0392b', EDIT_BG='#ffffff', SEL_BG='#cfe3f7', PRIMARY='#1f6fa3',
                  LINE='#d5dde8', SEL_FG='#0b2540', BTN_FG='#1b2430', HOVER='#e2ebf5', INACTIVE_SEL='#dfe8f2',
                  FOUND='#ffe58f', NEW_BG='#c9f2d6', WORK_BG='#fff1b8', READ_BG='#d3f5dd', DEL_BG='#fde2e2', INS_FG='#145a32',
                  HEAD_FG='#1f3864', DESK='#dfe4ea', RIBBON='#ffffff', TITLE_BG='#1f4e79'),
}
THEME_LABELS = {'dark': 'Koyu', 'light': 'Açık'}


def apply_theme(name):
    """Renk degiskenlerini temaya gore ayarlar (pencere kurulmadan once cagrilir)."""
    name = name if name in THEMES else 'dark'
    globals().update(THEMES[name])
    globals()['THEME'] = name
    rtext.PAGE_COLORS['desk'] = THEMES[name]['DESK']
    return name


THEME = 'dark'
apply_theme('dark')
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
FONT_SIZES = ('8', '9', '10', '10,5', '11', '12', '14', '16', '18', '20', '22', '24', '26', '28', '36', '48', '72')
HIGHLIGHT_COLORS = (('Sarı', 'FFFF00'), ('Parlak yeşil', '00FF00'), ('Turkuaz', '00FFFF'), ('Pembe', 'FF00FF'), ('Açık gri', 'C0C0C0'),
                    ('Kırmızı', 'FF0000'), ('Koyu sarı', '808000'))
SYMBOLS = (('©', 'Telif'), ('®', 'Tescilli'), ('™', 'Ticari marka'), ('€', 'Avro'), ('₺', 'Türk lirası'), ('°', 'Derece'),
           ('±', 'Artı eksi'), ('×', 'Çarpı'), ('÷', 'Bölü'), ('≤', 'Küçük eşit'), ('≥', 'Büyük eşit'), ('≈', 'Yaklaşık'),
           ('—', 'Uzun tire'), ('–', 'Kısa tire'), ('…', 'Üç nokta'), ('“”', 'Tırnak'), ('‘’', 'Tek tırnak'), ('§', 'Paragraf'),
           ('•', 'Madde işareti'), ('→', 'Ok'), ('✓', 'Onay'), ('µ', 'Mikro'))
CM = 28.3465                       # 1 cm = 28,3465 pt


class Tooltip:
    """Fareyle uzerine gelince kisa aciklama (600 ms)."""
    def __init__(self, widget, text):
        self.w, self.text, self.tip, self.job = widget, text, None, None
        widget.bind('<Enter>', self._schedule, add='+')
        widget.bind('<Leave>', self._hide, add='+')
        widget.bind('<ButtonPress>', self._hide, add='+')

    def _schedule(self, _e=None):
        self._cancel()
        self.job = self.w.after(600, self._show)

    def _cancel(self):
        if self.job:
            try:
                self.w.after_cancel(self.job)
            except (tk.TclError, ValueError):
                pass
            self.job = None

    def _show(self):
        self.job = None
        try:
            x, y = self.w.winfo_rootx() + 8, self.w.winfo_rooty() + self.w.winfo_height() + 4
            self.tip = tk.Toplevel(self.w)
            self.tip.wm_overrideredirect(True)
            self.tip.wm_geometry('+%d+%d' % (x, y))
            tk.Label(self.tip, text=self.text, bg='#ffffe1', fg='#1b1b1b', relief='solid', bd=1, font=('Segoe UI', 9),
                     padx=6, pady=2, wraplength=360, justify='left').pack()
        except tk.TclError:
            self.tip = None

    def _hide(self, _e=None):
        self._cancel()
        if self.tip:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
            self.tip = None


class Doc:
    def __init__(self, frame, text, title, path=None, docfile=None):
        self.id = uuid.uuid4().hex
        self.frame, self.text, self.title = frame, text, title
        self.path = path
        self.docfile = docfile or core.DocFile()
        self.docx_warned = False
        self.speech_script = False   # 1.5: bu sekme AI ile hazirlanmis bir okuma metni mi

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


class SpeechExportWindow(tk.Toplevel):
    """1.6: ses dosyasi - bolum plani, secim, cikti bicimi ve bolum bolum ilerleme."""

    def __init__(self, app, backend, doc, sections, what):
        super().__init__(app)
        self.app, self.b, self.doc, self.sections = app, backend, doc, sections
        self.checked = [True] * len(sections)
        self.status = {}             # is parcaciginden gelen durumlar; after() ile tabloya yazilir
        self.cancel = threading.Event()
        self.running = False
        self.title('Ses dosyası oluştur')
        self.configure(bg=PANEL, padx=12, pady=10)
        self.transient(app)
        self.geometry('%dx%d' % (int(720 * app.scale), int(560 * app.scale)))
        tk.Label(self, text='Bölümler (%s · %s)' % (what, doc.title or 'belge'), fg=FG, bg=PANEL,
                 font=('Segoe UI', 11, 'bold'), anchor='w').pack(fill='x')
        app.lbl(self, 'Belge başlıklarına göre bölündü; çok uzun bölümler paragraf sınırında dengeli parçalara ayrıldı. '
                      'Satıra tıklayarak bölümü ekleyin ya da çıkarın.', muted=True, wraplength=int(680 * app.scale)).pack(fill='x', pady=(2, 6))
        self.tree = ttk.Treeview(self, columns=('on', 'title', 'chars', 'dur', 'state'), show='headings', height=12, selectmode='browse')
        for col, lab, w, anchor in (('on', '✓', 34, 'center'), ('title', 'Bölüm', 330, 'w'), ('chars', 'Karakter', 80, 'e'),
                                    ('dur', 'Süre (tahmini)', 100, 'e'), ('state', 'Durum', 150, 'w')):
            self.tree.heading(col, text=lab)
            self.tree.column(col, width=int(w * app.scale), anchor=anchor, stretch=(col == 'title'))
        for i, s in enumerate(sections):
            self.tree.insert('', 'end', iid=str(i), values=('☑', s['title'], '{:,}'.format(s['chars']).replace(',', '.'),
                                                             self._dur(s['seconds']), 'bekliyor'))
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<ButtonRelease-1>', self._toggle_click)
        self.tree.bind('<space>', lambda e: self._toggle(self.tree.focus()))
        sel = tk.Frame(self, bg=PANEL)
        sel.pack(fill='x', pady=(6, 0))
        app.btn(sel, 'Tümünü seç', lambda: self._set_all(True), 'ghost', padx=8)
        app.btn(sel, 'Hiçbirini seçme', lambda: self._set_all(False), 'ghost', padx=8)
        self.total = app.lbl(sel, '', muted=True)
        self.total.pack(side='right')
        opt = tk.Frame(self, bg=PANEL)
        opt.pack(fill='x', pady=(8, 0))
        self.mode = tk.StringVar(value=app.settings.get('speech_export_mode', 'files' if len(sections) > 1 else 'single'))
        for val, lab in (('files', 'Her bölüm ayrı MP3 (+ çalma listesi)'), ('single', 'Tek MP3 dosyası')):
            tk.Radiobutton(opt, text=lab, value=val, variable=self.mode, bg=PANEL, fg=FG, selectcolor=EDIT_BG, activebackground=PANEL,
                           activeforeground=FG, font=('Segoe UI', 9), highlightthickness=0, bd=0).pack(side='left', padx=(0, 14))
        tk.Checkbutton(self, text='Okuma metnini AI ile hazırla (yabancı adlar, sayılar, kısaltmalar)', variable=app.sp_script_var,
                       bg=PANEL, fg=FG, selectcolor=EDIT_BG, activebackground=PANEL, activeforeground=FG, font=('Segoe UI', 9),
                       highlightthickness=0, bd=0, anchor='w').pack(fill='x', pady=(4, 0))
        if getattr(doc, 'speech_script', False):
            app.lbl(self, 'Bu sekme önizlenmiş okuma metni: metin olduğu gibi okunur.', muted=True).pack(fill='x')
        bot = tk.Frame(self, bg=PANEL)
        bot.pack(fill='x', pady=(10, 0))
        self.go_btn = app.btn(bot, '🎧 Oluştur', self.start, 'primary', padx=16, pady=6)
        self.cancel_btn = app.btn(bot, 'Durdur', self.stop, 'ghost', padx=10)
        self.cancel_btn.configure(state='disabled')
        self.open_btn = app.btn(bot, 'Klasörü aç', lambda: app._open_external(self.out_dir), 'ghost', padx=10)
        self.open_btn.configure(state='disabled')
        self.msg = tk.StringVar(value='')
        tk.Label(self, textvariable=self.msg, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9), anchor='w', justify='left',
                 wraplength=int(680 * app.scale)).pack(fill='x', pady=(6, 0))
        self.out_dir = ''
        self.bind('<Escape>', lambda e: None if self.running else self.destroy())
        self._update_total()

    @staticmethod
    def _dur(seconds):
        seconds = int(seconds or 0)
        return '%d:%02d' % (seconds // 60, seconds % 60) if seconds < 3600 else '%d:%02d:%02d' % (seconds // 3600, seconds // 60 % 60, seconds % 60)

    def _toggle_click(self, e):
        if self.tree.identify_region(e.x, e.y) == 'cell':
            self._toggle(self.tree.identify_row(e.y))

    def _toggle(self, iid):
        if self.running or iid in ('', None):
            return
        i = int(iid)
        self.checked[i] = not self.checked[i]
        self.tree.set(iid, 'on', '☑' if self.checked[i] else '☐')
        self._update_total()

    def _set_all(self, on):
        if self.running:
            return
        for i in range(len(self.sections)):
            self.checked[i] = on
            self.tree.set(str(i), 'on', '☑' if on else '☐')
        self._update_total()

    def _update_total(self):
        chosen = [s for s, c in zip(self.sections, self.checked) if c]
        self.total.configure(text='%d / %d bölüm · %s karakter · ~%s' % (len(chosen), len(self.sections),
                             '{:,}'.format(sum(s['chars'] for s in chosen)).replace(',', '.'), self._dur(sum(s['seconds'] for s in chosen))))
        self.go_btn.configure(state='normal' if chosen and not self.running else 'disabled')

    def _ask_target(self, mode):
        app = self.app
        base = re.sub(r'[\\/:*?"<>|]+', '_', os.path.splitext(self.doc.title or 'ses')[0]).strip() or 'ses'
        initial_dir = os.path.dirname(self.doc.path) if self.doc.path else str(pathlib.Path.home())
        if app.smoke and getattr(app, '_test_speech_path', None):
            return app._test_speech_path
        if mode == 'files':
            parent = filedialog.askdirectory(parent=self, title='Bölüm dosyalarının klasörü', initialdir=initial_dir)
            return os.path.join(parent, base + ' - ses') if parent else ''
        return filedialog.asksaveasfilename(parent=self, title='Sesi kaydet', defaultextension='.mp3', initialfile=base + '.mp3',
                                            initialdir=initial_dir, filetypes=[('MP3 ses', '*.mp3')])

    def start(self):
        chosen = [(i, s) for i, s in enumerate(self.sections) if self.checked[i]]
        if not chosen or self.running:
            return
        mode = self.mode.get()
        dest = self._ask_target(mode)
        if not dest:
            return
        app = self.app
        app.settings['speech_export_mode'] = mode
        app._speech_settings_changed()
        ready = bool(getattr(self.doc, 'speech_script', False))
        opts = dict(reading_script=bool(app.sp_script_var.get()) and not ready, script_ready=ready,
                    speed=float(app.settings.get('speech_speed', 1.0)), paragraph_pause_ms=int(app.settings.get('speech_paragraph_pause', 700)))
        index = [i for i, _s in chosen]
        for i in range(len(self.sections)):
            self.tree.set(str(i), 'state', 'bekliyor' if self.checked[i] else '—')
        self.running = True
        self.cancel.clear()
        self.go_btn.configure(state='disabled')
        self.cancel_btn.configure(state='normal')
        self.msg.set('Bölümler sırayla seslendiriliyor…')

        def status(k, state, info):
            self.status[index[k]] = (state, info)

        def work():
            return speech.narrate_sections(self.b, [s for _i, s in chosen], dest, mode=mode, status=status, cancel=self.cancel.is_set, **opts)

        def done(ok, res):
            self.running = False
            self._flush()
            if not self.winfo_exists():
                return
            self.cancel_btn.configure(state='disabled')
            self._update_total()
            if not ok:
                self.msg.set('Durduruldu.' if 'Cancelled' in str(res) else 'Hata: %s' % res)
                return
            secs = (res.get('duration_ms') or 0) / 1000.0
            note = speech.script_note(res.get('scripts') or [])
            where = dest if mode == 'files' else res['paths'][0]
            self.out_dir = dest if mode == 'files' else os.path.dirname(dest)
            text = '✓ %d dosya · %s%s' % (len(res['paths']), self._dur(secs), (' · ' + note) if note else '')
            if res.get('failed'):
                text += ' · %d bölüm hata verdi' % len(res['failed'])
            self.msg.set(text + '\n' + where)
            self.open_btn.configure(state='normal')
            app._sp_last = res['paths'][0]
            app._sp_last_dir = self.out_dir
            app.sp_result_var.set(text)
            app.sp_play_btn.configure(state='normal')
            app.sp_folder_btn.configure(state='normal')
        app._start_job('Ses dosyası', work, done)
        self._poll_status()

    def _flush(self):
        if not self.winfo_exists():
            return
        for i, (state, info) in list(self.status.items()):
            label = {'hazırlanıyor': '… ' + (info or 'hazırlanıyor'), 'tamam': '✓ ' + (info or 'tamam'), 'hata': '✗ hata'}.get(state, state)
            self.tree.set(str(i), 'state', label[:60])
            if state == 'hazırlanıyor':
                self.tree.see(str(i))

    def _poll_status(self):
        if not self.winfo_exists():
            return
        self._flush()
        if self.running:
            self.after(250, self._poll_status)

    def stop(self):
        self.cancel.set()
        self.msg.set('Durduruluyor (sıradaki adımda)…')


class LexiconWindow(tk.Toplevel):
    """1.5: sunucudaki ortak EMA telaffuz sozlugu (AI Manager 17.12+ /editor/lexicon)."""
    SOURCE = {'base': 'Hazır', 'added': 'Eklendi', 'edited': 'Değiştirildi', 'removed': 'Kaldırıldı'}

    def __init__(self, app, backend, word=''):
        super().__init__(app)
        self.app, self.b = app, backend
        self.rows = []
        self.title('Telaffuz sözlüğü' + (' – bu bilgisayar' if getattr(backend, 'kind', '') == 'local' else ''))
        self.configure(bg=PANEL, padx=12, pady=10)
        self.transient(app)
        self.geometry('%dx%d' % (int(640 * app.scale), int(560 * app.scale)))
        top = tk.Frame(self, bg=PANEL)
        top.pack(fill='x')
        app.lbl(top, 'Ara', muted=True).pack(side='left')
        self.q = tk.StringVar()
        e = ttk.Entry(top, textvariable=self.q, width=30)
        e.pack(side='left', padx=(6, 8))
        self.q.trace_add('write', lambda *_: self.render())
        app.btn(top, 'Yenile', self.load, 'ghost', padx=8)
        self.count = app.lbl(top, '', muted=True)
        self.count.pack(side='right')
        self.tree = ttk.Treeview(self, columns=('word', 'reading', 'source'), show='headings', height=14, selectmode='browse')
        for col, lab, w in (('word', 'Kelime', 180), ('reading', 'Okunuş', 260), ('source', 'Kaynak', 100)):
            self.tree.heading(col, text=lab)
            self.tree.column(col, width=int(w * app.scale), anchor='w')
        self.tree.pack(fill='both', expand=True, pady=(8, 8))
        self.tree.bind('<<TreeviewSelect>>', lambda e: self._picked())
        form = tk.Frame(self, bg=PANEL)
        form.pack(fill='x')
        app.lbl(form, 'Kelime (metindeki gibi)', muted=True).grid(row=0, column=0, sticky='w')
        app.lbl(form, 'Okunuş (Türkçe harflerle)', muted=True).grid(row=0, column=1, sticky='w', padx=(8, 0))
        self.word = tk.StringVar(value=word)
        self.reading = tk.StringVar()
        ttk.Entry(form, textvariable=self.word, width=26).grid(row=1, column=0, sticky='we')
        self.reading_entry = ttk.Entry(form, textvariable=self.reading, width=34)
        self.reading_entry.grid(row=1, column=1, sticky='we', padx=(8, 0))
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=2)
        btns = tk.Frame(self, bg=PANEL)
        btns.pack(fill='x', pady=(8, 0))
        app.btn(btns, 'Dinle', self.listen, 'ghost', padx=10)
        self.save_btn = app.btn(btns, 'Kaydet', self.save, 'primary', padx=14)
        self.del_btn = app.btn(btns, 'Sil', self.delete, 'ghost', padx=10)
        self.restore_btn = app.btn(btns, 'Geri al / hazıra dön', self.restore, 'ghost', padx=10)
        self.status = tk.StringVar(value='Yükleniyor…')
        tk.Label(self, textvariable=self.status, fg=MUTED, bg=PANEL, font=('Segoe UI', 9), anchor='w', justify='left',
                 wraplength=int(600 * app.scale)).pack(fill='x', pady=(8, 0))
        self.bind('<Escape>', lambda e: self.destroy())
        self.reading_entry.bind('<Return>', lambda e: self.save())
        if word:
            self.q.set(word)
            self.reading_entry.focus_set()
        self.load()

    def set_word(self, word):
        self.word.set(word)
        self.reading.set('')
        self.q.set(word)
        self.reading_entry.focus_set()

    def _job(self, label, fn, done, *args):
        self.status.set(label + '…')
        self.app._start_job(label, fn, done, *args)

    def load(self, note=None):
        def done(ok, res):
            if not self.winfo_exists():
                return
            if not ok:
                self.status.set(res)
                return
            self.rows = res.get('entries') or []
            can = res.get('can_edit', True)
            for b in (self.save_btn, self.del_btn, self.restore_btn):
                b.configure(state='normal' if can else 'disabled')
            mine = sum(1 for r in self.rows if r.get('source') in ('added', 'edited'))
            self.count.configure(text='%s etkin · %d sizin' % (res.get('active', len(self.rows)), mine))
            self.status.set(note or ('Hazır.' if can else 'Sözlüğü yalnız site yöneticisi değiştirebilir; dinleyebilirsiniz.'))
            self.render()
            w = self.word.get().strip()
            hit = next((r for r in self.rows if r.get('word') == w), None)
            if hit and not self.reading.get().strip():
                self.reading.set(hit.get('reading', ''))
        self._job('Sözlük alınıyor', self.b.lexicon_list, done)

    def render(self):
        if not self.winfo_exists():
            return
        term = self.q.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        shown = 0
        for r in self.rows:
            w, rd = str(r.get('word', '')), str(r.get('reading', ''))
            if term and term not in w.lower() and term not in rd.lower():
                continue
            self.tree.insert('', 'end', iid='r%d' % shown, values=(w, rd, self.SOURCE.get(r.get('source'), r.get('source', ''))))
            shown += 1
            if shown >= 400:
                break

    def _picked(self):
        sel = self.tree.selection()
        if sel:
            w, rd, _src = self.tree.item(sel[0], 'values')
            self.word.set(w)
            self.reading.set(rd)

    def _after_change(self, msg):
        def done(ok, res):
            if not self.winfo_exists():
                return
            if not ok:
                self.status.set(res)
                return
            site = res.get('site') if isinstance(res, dict) else None
            if site is None:
                note = msg + ' Bütün sitelerde geçerli.'
            elif site == 'ok':
                note = msg + ' Bu bilgisayarda ve bütün sitelerde geçerli.'
            elif site == 'none':
                note = msg + ' Bu bilgisayarda geçerli.'
            else:
                note = msg + ' Bu bilgisayarda geçerli; ortak sözlüğe yazılamadı: ' + site
            self.status.set(note)
            self.load(note)
        return done

    def save(self):
        w, rd = self.word.get().strip(), self.reading.get().strip()
        if not w or not rd:
            self.status.set('Kelime ve okunuş gerekli.')
            return
        self._job('Kaydediliyor', self.b.lexicon_change, self._after_change('“%s” → “%s” kaydedildi.' % (w, rd)), 'save', w, rd)

    def delete(self):
        w = self.word.get().strip()
        if w:
            self._job('Siliniyor', self.b.lexicon_change, self._after_change('“%s” sözlükten kaldırıldı.' % w), 'delete', w, '')

    def restore(self):
        w = self.word.get().strip()
        if w:
            self._job('Geri alınıyor', self.b.lexicon_change, self._after_change('“%s” hazır okunuşuna döndü.' % w), 'restore', w, '')

    def listen(self):
        text = self.reading.get().strip() or self.word.get().strip()
        if not text:
            return

        def done(ok, res):
            if not ok:
                self.status.set(res)
                return
            folder = core.data_dir() / 'listen'
            folder.mkdir(exist_ok=True)
            for old in sorted(folder.glob('*.mp3'))[:-10]:
                try:
                    old.unlink()
                except OSError:
                    pass
            path = folder / ('%s.mp3' % uuid.uuid4().hex[:10])
            path.write_bytes(res)
            self.last_listen = str(path)
            self.status.set('“%s” çalınıyor.' % text)
            self.app._open_external(str(path))
        self._job('Örnek ses hazırlanıyor', self.b.lexicon_listen, done, text)


class App(tk.Tk):
    def __init__(self, files=(), smoke=False):
        super().__init__()
        self.smoke = smoke
        self.settings = core.load_settings()
        apply_theme(self.settings.get('ui_theme'))          # 2.0: tema renkleri pencere kurulmadan once
        self.speller = None                                  # 2.0: yazim denetimi (agfo_spell)
        self._painter = None
        self.q = queue.Queue()
        self.jobs = {}
        self.docs = []
        self.pdf_views = {}           # 1.3: PDF duzenleyici sekmeleri (cerceve -> PdfView)
        self.brcgs_views = {}         # 2.2: BRCGS rapor sekmeleri (BrcgsReportView)
        self.brcgs_explorer = None    # 2.2: BRCGS rapor gezgini sekmesi
        self.colors = {'BG': BG, 'PANEL': PANEL, 'PANEL2': PANEL2, 'FG': FG, 'MUTED': MUTED, 'ACCENT': ACCENT,
                       'EDIT_BG': EDIT_BG, 'SEL_BG': SEL_BG, 'LINE': LINE, 'SEL_FG': SEL_FG, 'THEME': THEME}
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
        self.bind('<FocusIn>', lambda e: self._brcgs_focus_check() if e.widget is self else None, add='+')
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
        s.configure('.', background=PANEL, foreground=FG, fieldbackground=PANEL2, font=('Segoe UI', 10), bordercolor=LINE,
                    lightcolor=PANEL2, darkcolor=PANEL2)
        s.configure('TNotebook', background=BG, borderwidth=0, tabmargins=(0, 4, 0, 0))
        s.configure('TNotebook.Tab', background=PANEL2, foreground=MUTED, padding=(11, 7), font=('Segoe UI', 10), borderwidth=0)
        s.map('TNotebook.Tab', background=[('selected', SEL_BG)], foreground=[('selected', SEL_FG)])
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
        s.map('Treeview', background=[('selected', SEL_BG)], foreground=[('selected', SEL_FG)])
        s.map('Treeview.Heading', background=[('active', SEL_BG)])
        s.configure('TPanedwindow', background=BG)
        s.configure('Sash', background=BG, sashthickness=6)

    def btn(self, parent, text, cmd, kind='normal', side='left', **kw):
        colors = {'normal': SEL_BG, 'primary': PRIMARY, 'ghost': PANEL2, 'go': '#1f6a4a', 'danger': '#6b2f2f'}
        fgs = {'normal': SEL_FG, 'ghost': BTN_FG}
        b = tk.Button(parent, text=text, command=cmd, bg=colors[kind], fg=fgs.get(kind, '#ffffff'), activebackground=ACCENT,
                      activeforeground='#06111f' if THEME == 'dark' else '#ffffff',
                      relief='flat', cursor='hand2', padx=kw.pop('padx', 11), pady=kw.pop('pady', 5), font=kw.pop('font', ('Segoe UI', 9, 'bold')),
                      disabledforeground='#7f8ea3', bd=0, highlightthickness=0, **kw)
        if side:
            b.pack(side=side, padx=(0, 6), pady=2)
        return b

    def lbl(self, parent, text, muted=False, bg=None, **kw):
        return tk.Label(parent, text=text, fg=MUTED if muted else FG, bg=PANEL if bg is None else bg, font=kw.pop('font', ('Segoe UI', 9)),
                        justify='left', anchor='w', **kw)

    # ------------------------------------------------------------------ 2.0: baslik cubugu + serit (Giris / Ekle / Duzen / Gorunum / AI)
    RIBBON_TABS = (('home', 'Giriş'), ('insert', 'Ekle'), ('layout', 'Düzen'), ('view', 'Görünüm'), ('ai', 'Yapay zekâ'))

    def _build(self):
        top = tk.Frame(self, bg=TITLE_BG)
        top.pack(fill='x')
        self.title_bar = top
        tfg = '#ffffff'
        tk.Label(top, text='AGFO', fg='#7fd1ff' if THEME == 'dark' else '#cfe8ff', bg=TITLE_BG,
                 font=('Segoe UI', 10, 'bold')).pack(side='left', padx=(14, 4), pady=6)
        tk.Label(top, text='AI Editor', fg=tfg, bg=TITLE_BG, font=('Segoe UI', 10)).pack(side='left', padx=(0, 14))

        def qbtn(text, cmd, tip):
            b = tk.Button(top, text=text, command=cmd, bg=TITLE_BG, fg=tfg, activebackground=ACCENT, activeforeground='#ffffff',
                          relief='flat', bd=0, highlightthickness=0, cursor='hand2', font=('Segoe UI', 11), padx=7, pady=1)
            b.pack(side='left')
            Tooltip(b, tip)
            return b
        qbtn('💾', self.save, 'Kaydet (Ctrl+S)')
        qbtn('↶', lambda: self._text_cmd('edit_undo'), 'Geri al (Ctrl+Z)')
        qbtn('↷', lambda: self._text_cmd('edit_redo'), 'Yinele (Ctrl+Y)')
        tk.Frame(top, bg='#3d5f86' if THEME == 'dark' else '#4a76a3', width=1, height=20).pack(side='left', padx=10)
        # serit sekmeleri: Dosya menu acar, digerleri serit sayfasini degistirir
        self.more_btn = tk.Button(top, text='Dosya', command=self.show_more_menu, bg=TITLE_BG, fg=tfg, relief='flat', bd=0,
                                  highlightthickness=0, activebackground=ACCENT, activeforeground='#ffffff', cursor='hand2',
                                  font=('Segoe UI', 10), padx=12, pady=6)
        self.more_btn.pack(side='left')
        self.rtab_btns = {}
        for key, label in self.RIBBON_TABS:
            b = tk.Button(top, text=label, command=lambda k=key: self.select_ribbon(k), bg=TITLE_BG, fg=tfg, relief='flat', bd=0,
                          highlightthickness=0, activebackground=ACCENT, activeforeground='#ffffff', cursor='hand2',
                          font=('Segoe UI', 10), padx=12, pady=6)
            b.pack(side='left')
            self.rtab_btns[key] = b
        right = tk.Frame(top, bg=TITLE_BG)
        right.pack(side='right', padx=(0, 10))
        self.settings_btn = tk.Button(right, text='⚙', command=self.open_settings, bg=TITLE_BG, fg=tfg, relief='flat', bd=0,
                                      highlightthickness=0, activebackground=ACCENT, cursor='hand2', font=('Segoe UI', 12), padx=8)
        self.settings_btn.pack(side='right')
        Tooltip(self.settings_btn, 'Ayarlar')
        self.panel_btn = tk.Button(right, text='AI paneli ⇥', command=self.toggle_ai_panel, bg=TITLE_BG, fg=tfg, relief='flat', bd=0,
                                   highlightthickness=0, activebackground=ACCENT, cursor='hand2', font=('Segoe UI', 9), padx=8)
        self.panel_btn.pack(side='right')
        self.brcgs_btn = tk.Button(right, text='📋 BRCGS reports', command=self.open_brcgs, bg=TITLE_BG, fg=tfg, relief='flat', bd=0,
                                   highlightthickness=0, activebackground=ACCENT, cursor='hand2', font=('Segoe UI', 9), padx=8)
        self.brcgs_btn.pack(side='right')
        Tooltip(self.brcgs_btn, 'BRCGS audit reports: fill the official template like a form; it opens in Word in its original format')
        self.conn_var = tk.StringVar(value='Bağlantı denetleniyor…')
        self.conn_lbl = tk.Label(right, textvariable=self.conn_var, fg=MUTED, bg=PANEL, font=('Segoe UI', 9), padx=10, pady=3)
        self.conn_lbl.pack(side='right', padx=8, pady=4)
        self.update_btn = tk.Button(right, text='', command=self.do_update, bg='#1f6a4a', fg='#ffffff', relief='flat', bd=0,
                                    font=('Segoe UI', 9, 'bold'), padx=10, pady=3, cursor='hand2', activebackground=ACCENT,
                                    activeforeground='#ffffff')
        self._update_shown = None      # 1.4.15: dugmesi gosterilen surum (ayni surum icin tekrar bildirim yok)

        self.fmt_bar = tk.Frame(self, bg=RIBBON, highlightthickness=1, highlightbackground=LINE)
        self._build_fmt_bar(self.fmt_bar)
        self.fmt_bar.pack(fill='x')

        self.find_bar = tk.Frame(self, bg=PANEL2, padx=10, pady=6)
        self._build_find(self.find_bar)

        st = tk.Frame(self, bg=PANEL, padx=10, pady=3)
        st.pack(fill='x', side='bottom')
        self.status_var = tk.StringVar(value='')
        tk.Label(st, textvariable=self.status_var, fg=MUTED, bg=PANEL, font=('Segoe UI', 9)).pack(side='left')
        self.cancel_btn = tk.Button(st, text='Durdur', command=self.cancel_jobs, bg='#6b2f2f', fg='#ffffff', relief='flat', bd=0,
                                    font=('Segoe UI', 8, 'bold'), padx=8, pady=1, cursor='hand2')
        self.busy = ttk.Progressbar(st, mode='indeterminate', length=140)
        self.zoom_lbl = tk.Label(st, text='', fg=MUTED, bg=PANEL, font=('Segoe UI', 9))
        self.zoom_lbl.pack(side='right', padx=(8, 0))
        self.ai_var = tk.StringVar(value='')
        tk.Label(st, textvariable=self.ai_var, fg=FG, bg=PANEL, font=('Segoe UI', 9)).pack(side='right', padx=(8, 0))

        self.paned = ttk.PanedWindow(self, orient='horizontal')
        self.paned.pack(fill='both', expand=True, padx=8, pady=(6, 4))
        self.nb = ttk.Notebook(self.paned)
        self.nb.bind('<<NotebookTabChanged>>', lambda e: (self._update_status(), self._sync_fmt_bar(), self._brcgs_panel_auto(),
                                                          self._brcgs_focus_check()))
        self.nb.bind('<Button-2>', self._middle_close)
        self.paned.add(self.nb, weight=3)
        side = ttk.Frame(self.paned, padding=(10, 8))
        self.paned.add(side, weight=2)
        self.side_panel = side
        self._build_ai_panel(side)
        self.select_ribbon(self.settings.get('ribbon_tab') or 'home', save=False)
        self._sync_zoom_label()

    def select_ribbon(self, key, save=True):
        if key not in self.ribbon_pages:
            key = 'home'
        self.ribbon_tab = key
        for k, page in self.ribbon_pages.items():
            if k == key:
                page.pack(fill='x', padx=6, pady=(4, 2))
            else:
                page.pack_forget()
        for k, b in self.rtab_btns.items():
            on = k == key
            b.configure(bg=RIBBON if on else TITLE_BG, fg=(ACCENT if THEME == 'dark' else '#1f4e79') if on else '#ffffff')
        if save and self.settings.get('ribbon_tab') != key:
            self.settings['ribbon_tab'] = key
            core.save_settings(self.settings)

    # ---- serit yardimcilari
    def _group(self, page, title):
        outer = tk.Frame(page, bg=RIBBON)
        outer.pack(side='left', fill='y', padx=(0, 2))
        body = tk.Frame(outer, bg=RIBBON)
        body.pack(side='top', fill='both', expand=True, padx=6)
        tk.Label(outer, text=title, fg=MUTED, bg=RIBBON, font=('Segoe UI', 8)).pack(side='bottom', pady=(1, 0))
        tk.Frame(page, bg=LINE, width=1).pack(side='left', fill='y', pady=4, padx=4)
        return body

    def _rrow(self, body):
        r = tk.Frame(body, bg=RIBBON)
        r.pack(side='top', anchor='w', pady=1)
        return r

    def rbtn(self, parent, text, cmd, key=None, tip=None, font=None, big=False, width=None):
        b = tk.Button(parent, text=text, command=cmd, bg=RIBBON, fg=FG, activebackground=HOVER, activeforeground=FG, relief='flat',
                      bd=0, highlightthickness=0, cursor='hand2', font=font or ('Segoe UI', 9), padx=6 if not big else 8,
                      pady=2 if not big else 6, compound='top' if big else None, width=width)
        b.pack(side='left', padx=1)
        b.bind('<Enter>', lambda e, w=b: w.configure(bg=HOVER) if not getattr(w, '_on', False) else None)
        b.bind('<Leave>', lambda e, w=b: w.configure(bg=SEL_BG if getattr(w, '_on', False) else RIBBON))
        if tip:
            Tooltip(b, tip)
        if key:
            self.fmt_btns[key] = b
        return b

    def _set_on(self, b, on):
        b._on = bool(on)
        b.configure(bg=SEL_BG if on else RIBBON, fg=SEL_FG if on else FG)

    def _popup(self, m, widget):
        m.tk_popup(widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height())

    # ------------------------------------------------------------------ serit sayfalari
    def _build_fmt_bar(self, f):
        self.fmt_btns = {}
        self.style_var = tk.StringVar(value=rdoc.STYLE_LABELS['normal'])
        self._style_keys = {v: k for k, v in rdoc.STYLE_LABELS.items()}
        self.ribbon_pages = {}
        for key, _label in self.RIBBON_TABS:
            self.ribbon_pages[key] = tk.Frame(f, bg=RIBBON)
        self._page_home(self.ribbon_pages['home'])
        self._page_insert(self.ribbon_pages['insert'])
        self._page_layout(self.ribbon_pages['layout'])
        self._page_view(self.ribbon_pages['view'])
        self._page_ai(self.ribbon_pages['ai'])
        self.fmt_hint = tk.Label(f, text='', fg=WARN, bg=RIBBON, font=('Segoe UI', 8))

    def _page_home(self, pg):
        g = self._group(pg, 'Pano')
        r = self._rrow(g)
        self.rbtn(r, '📋\nYapıştır', lambda: self._edit_event('<<Paste>>'), tip='Yapıştır (Ctrl+V)', big=True).configure(padx=4)
        col = tk.Frame(r, bg=RIBBON)
        col.pack(side='left')
        for text, ev, tip in (('✂ Kes', '<<Cut>>', 'Kes (Ctrl+X)'), ('⧉ Kopyala', '<<Copy>>', 'Kopyala (Ctrl+C)')):
            b = tk.Button(col, text=text, command=lambda e=ev: self._edit_event(e), bg=RIBBON, fg=FG, relief='flat', bd=0,
                          highlightthickness=0, activebackground=HOVER, cursor='hand2', font=('Segoe UI', 9), anchor='w', padx=6)
            b.pack(side='top', fill='x')
            Tooltip(b, tip)
        fp = tk.Button(col, text='🖌 Biçim boyacısı', command=self.format_painter, bg=RIBBON, fg=FG, relief='flat', bd=0,
                       highlightthickness=0, activebackground=HOVER, cursor='hand2', font=('Segoe UI', 9), anchor='w', padx=6)
        fp.pack(side='top', fill='x')
        Tooltip(fp, 'Biçimi kopyala: imleçteki biçimi alır, sonra seçtiğiniz metne uygular (çift tık: birden çok kez)')
        fp.bind('<Double-Button-1>', lambda e: (self.format_painter(sticky=True), 'break')[1])
        self.fmt_btns['painter'] = fp

        g = self._group(pg, 'Yazı tipi')
        r = self._rrow(g)
        self.font_var = tk.StringVar(value='')
        self.font_cb = ttk.Combobox(r, textvariable=self.font_var, values=self._font_families(), width=16)
        self.font_cb.pack(side='left', padx=(2, 4))
        self.font_cb.bind('<<ComboboxSelected>>', lambda e: self._fmt('font', self.font_var.get()))
        self.font_cb.bind('<Return>', lambda e: (self._fmt('font', self.font_var.get()), 'break')[1])
        self.size_var = tk.StringVar(value='11')
        self.size_cb = ttk.Combobox(r, textvariable=self.size_var, values=FONT_SIZES, width=4)
        self.size_cb.pack(side='left', padx=(0, 2))
        self.size_cb.bind('<<ComboboxSelected>>', lambda e: self._fmt('size', self.size_var.get()))
        self.size_cb.bind('<Return>', lambda e: (self._fmt('size', self.size_var.get()), 'break')[1])
        self.rbtn(r, 'A⁺', lambda: self._fmt('grow', 1), tip='Yazı tipini büyüt')
        self.rbtn(r, 'A⁻', lambda: self._fmt('grow', -1), tip='Yazı tipini küçült')
        r = self._rrow(g)
        self.rbtn(r, 'K', lambda: self._fmt('b'), 'b', 'Kalın (Ctrl+B)', ('Segoe UI', 10, 'bold'), width=2)
        self.rbtn(r, 'İ', lambda: self._fmt('i'), 'i', 'İtalik (Ctrl+I)', ('Segoe UI', 10, 'italic'), width=2)
        self.rbtn(r, 'A', lambda: self._fmt('u'), 'u', 'Altı çizili (Ctrl+U)', ('Segoe UI', 10, 'underline'), width=2)
        self.rbtn(r, 'abc', lambda: self._fmt('s'), 's', 'Üstü çizili', ('Segoe UI', 9, 'overstrike'))
        self.rbtn(r, 'x₂', lambda: self._fmt('sub'), 'sub', 'Alt simge (Ctrl+=)', ('Segoe UI', 10))
        self.rbtn(r, 'x²', lambda: self._fmt('sup'), 'sup', 'Üst simge', ('Segoe UI', 10))
        self.rbtn(r, '🖍 ▾', self._highlight_menu, 'hl', 'Metin vurgu rengi')
        self.rbtn(r, 'A ▾', self._color_menu, 'color', 'Yazı rengi', ('Segoe UI', 10, 'bold'))
        self.rbtn(r, '⌫ Temizle', lambda: self._fmt('clear'), 'clear', 'Tüm biçimi temizle (karakter + paragraf). Ctrl+Boşluk: yalnız karakter')

        g = self._group(pg, 'Paragraf')
        r = self._rrow(g)
        self.rbtn(r, '• ≡', lambda: self._fmt('list', 'bullet'), 'bullet', 'Madde işaretleri')
        self.rbtn(r, '1. ≡', lambda: self._fmt('list', 'number'), 'number', 'Numaralandırma')
        self.rbtn(r, '⇤', lambda: self._fmt('indent', -1), 'outdent', 'Girintiyi azalt (Shift+Tab listede)')
        self.rbtn(r, '⇥', lambda: self._fmt('indent', 1), 'indent', 'Girintiyi artır (Tab listede)')
        self.rbtn(r, '¶ Paragraf…', self.paragraph_dialog, tip='Girintiler ve aralıklar')
        r = self._rrow(g)
        self.rbtn(r, '⯇≡', lambda: self._fmt('align', 'left'), 'left', 'Sola hizala (Ctrl+L)')
        self.rbtn(r, '≡', lambda: self._fmt('align', 'center'), 'center', 'Ortala', ('Segoe UI', 11))
        self.rbtn(r, '≡⯈', lambda: self._fmt('align', 'right'), 'right', 'Sağa hizala (Ctrl+R)')
        self.rbtn(r, '☰', lambda: self._fmt('align', 'justify'), 'justify', 'İki yana yasla (Ctrl+J)', ('Segoe UI', 11))
        self.rbtn(r, '↕ ▾', self._spacing_menu, 'spacing', 'Satır ve paragraf aralığı')

        g = self._group(pg, 'Stiller')
        r = self._rrow(g)
        self.style_btns = {}
        gallery = (('normal', 'Normal', ('Segoe UI', 9)), ('h1', 'Başlık 1', ('Segoe UI', 11, 'bold')),
                   ('h2', 'Başlık 2', ('Segoe UI', 10, 'bold')), ('h3', 'Başlık 3', ('Segoe UI', 9, 'bold')),
                   ('quote', 'Alıntı', ('Segoe UI', 9, 'italic')))
        for key, label, font in gallery:
            b = tk.Button(r, text=label, command=lambda k=key: self._fmt('style', k), bg=PANEL2, fg=FG, relief='flat', bd=0,
                          highlightthickness=1, highlightbackground=LINE, activebackground=HOVER, cursor='hand2', font=font,
                          padx=4, pady=10)
            b.pack(side='left', padx=1, pady=2)
            self.style_btns[key] = b

        g = self._group(pg, 'Düzenleme')
        r = self._rrow(g)
        self.rbtn(r, '🔍 Bul', self.toggle_find, tip='Bul (Ctrl+F)')
        r = self._rrow(g)
        self.rbtn(r, '⇄ Değiştir', lambda: self.toggle_find(replace=True), tip='Değiştir (Ctrl+H)')
        r = self._rrow(g)
        self.rbtn(r, '▭ Tümünü seç', self.select_all, tip='Tümünü seç (Ctrl+A)')

    def _page_insert(self, pg):
        g = self._group(pg, 'Tablolar ve görseller')
        r = self._rrow(g)
        self.rbtn(r, '▦\nTablo', self.insert_table, 'table', 'Tablo ekle', big=True)
        self.rbtn(r, '🖼\nResim', self.insert_image, 'image', 'Resim ekle', big=True)
        g = self._group(pg, 'Bağlantılar')
        r = self._rrow(g)
        self.rbtn(r, '🔗\nBağlantı', self.insert_link, 'link', 'Bağlantı ekle (Ctrl+K). Ctrl+tık bağlantıyı açar', big=True)
        g = self._group(pg, 'Sayfalar')
        r = self._rrow(g)
        self.rbtn(r, '⤓\nSayfa sonu', lambda: self._fmt('pagebreak'), 'pagebreak', 'Sayfa sonu (Ctrl+Enter)', big=True)
        g = self._group(pg, 'Üst bilgi ve alt bilgi')
        r = self._rrow(g)
        self.rbtn(r, '▔\nÜst bilgi', lambda: self.header_footer_dialog('header'), tip='Her sayfanın üstündeki metin', big=True)
        self.rbtn(r, '▁\nAlt bilgi', lambda: self.header_footer_dialog('footer'), tip='Her sayfanın altındaki metin', big=True)
        self.rbtn(r, '#\nSayfa numarası ▾', self._page_number_menu, 'pnum', 'Sayfa numarası ekle', big=True)
        g = self._group(pg, 'Simgeler')
        r = self._rrow(g)
        self.rbtn(r, 'Ω\nSimge ▾', self._symbol_menu, 'symbol', 'Özel karakter ekle', big=True)

    def _page_layout(self, pg):
        g = self._group(pg, 'Sayfa yapısı')
        r = self._rrow(g)
        self.rbtn(r, '▣\nKenar boşlukları ▾', self._margins_menu, 'margins', 'Kenar boşlukları', big=True)
        self.rbtn(r, '⇅\nYönlendirme ▾', self._orient_menu, 'orient', 'Dikey / yatay', big=True)
        self.rbtn(r, '▯\nBoyut ▾', self._size_menu, 'psize', 'Kâğıt boyutu', big=True)
        g = self._group(pg, 'Paragraf')
        r = self._rrow(g)
        self.rbtn(r, '⇤ Girinti azalt', lambda: self._fmt('indent', -1))
        self.rbtn(r, '⇥ Girinti artır', lambda: self._fmt('indent', 1))
        r = self._rrow(g)
        self.rbtn(r, '¶ Girintiler ve aralıklar…', self.paragraph_dialog)
        self.rbtn(r, '↕ Aralık ▾', self._spacing_menu)
        self.page_info = tk.Label(pg, text='', fg=MUTED, bg=RIBBON, font=('Segoe UI', 9), justify='left')
        self.page_info.pack(side='left', padx=10)

    def _page_view(self, pg):
        g = self._group(pg, 'Görünüm')
        r = self._rrow(g)
        self.page_btn = self.rbtn(r, '📄\nSayfa görünümü', self.toggle_page_view, tip='Sayfa genişliğinde beyaz sayfa', big=True)
        g = self._group(pg, 'Yakınlaştır')
        r = self._rrow(g)
        self.rbtn(r, '🔍−', lambda: self.zoom(-1), tip='Uzaklaştır (Ctrl+-)')
        self.rbtn(r, '🔍+', lambda: self.zoom(1), tip='Yakınlaştır (Ctrl++)')
        r = self._rrow(g)
        self.rbtn(r, '%100', self.zoom_reset, tip='Yakınlaştırmayı sıfırla')
        g = self._group(pg, 'Yazım')
        r = self._rrow(g)
        self.spell_btn = self.rbtn(r, 'abc✓\nYazım denetimi', self.toggle_spell, tip='Türkçe yazım denetimi (kırmızı işaret, sağ tık öneriler)',
                                   big=True)
        g = self._group(pg, 'Pencere')
        r = self._rrow(g)
        self.rbtn(r, '⇥\nAI paneli', self.toggle_ai_panel, tip='Yapay zekâ panelini göster / gizle', big=True)
        self.rbtn(r, '◐\nTema ▾', self._theme_menu, tip='Koyu / açık tema', big=True)

    def _page_ai(self, pg):
        g = self._group(pg, 'Metin')
        r = self._rrow(g)
        for key in ('content_strengthen', 'proofread', 'shorten'):
            a = core.action_by_key(key)
            if a:
                self.rbtn(r, a['label'], lambda k=key: self.run_action_key(k), tip='Seçili metin (yoksa paragraf)')
        r = self._rrow(g)
        for key in ('content_flow', 'expand', 'critique'):
            a = core.action_by_key(key)
            if a:
                self.rbtn(r, a['label'], lambda k=key: self.run_action_key(k), tip='Seçili metin (yoksa paragraf)')
        g = self._group(pg, 'Çeviri')
        r = self._rrow(g)
        self.rbtn(r, '🌐\nBelgeyi çevir', self.translate_document, tip='Tüm belgeyi yan yana karşılaştırmalı çevir', big=True)
        self.rbtn(r, 'Aあ\nSeçimi çevir', self.run_translate, tip='Seçili metni çevir', big=True)
        g = self._group(pg, 'Ses')
        r = self._rrow(g)
        self.rbtn(r, '🔊\nSesli oku', self.read_aloud, tip='Sesli oku / duraklat (F9)', big=True)
        self.rbtn(r, '🎧\nSesli kitap', lambda: self._ai_panel_tab(5), tip='Ses sekmesi: MP3 / sesli kitap dışa aktarımı', big=True)
        g = self._group(pg, 'Panel')
        r = self._rrow(g)
        for idx, (icon, label) in enumerate((('✨', 'İçerik'), ('🌐', 'Çeviri'), ('💬', 'Sohbet'), ('✔', 'Denetim'), ('📚', 'Kaynaklar'))):
            self.rbtn(r, '%s\n%s' % (icon, label), lambda i=idx: self._ai_panel_tab(i), big=True)

    def _ai_panel_tab(self, idx):
        if str(self.side_panel) not in self.paned.panes():
            self.toggle_ai_panel()
        try:
            self.ai_nb.select(idx)
        except tk.TclError:
            pass

    def _edit_event(self, ev):
        d = self.cur()
        if d:
            d.text.focus_set()
            d.text.event_generate(ev)

    def select_all(self):
        d = self.cur()
        if d:
            d.text.tag_add('sel', '1.0', 'end-1c')
            d.text.focus_set()

    def _font_families(self):
        try:
            fams = sorted({f for f in tkfont.families(self) if not f.startswith('@')}, key=str.lower)
        except tk.TclError:
            fams = []
        common = [f for f in ('Calibri', 'Cambria', 'Arial', 'Times New Roman', 'Georgia', 'Segoe UI', 'Verdana', 'Tahoma',
                              'Garamond', 'Consolas', 'Courier New') if f in fams]
        return common + ['—'] + [f for f in fams if f not in common] if common else fams

    # ------------------------------------------------------------------ bicim komutlari
    def _ensure_rich(self, d):
        t = d.text
        if t.rich:
            return True
        if not messagebox.askyesno('Biçimlendirme', 'Bu belge düz metin (.txt). Biçimlendirme için belge Word gibi düzenlenecek; '
                                   'kaydederken .docx seçerseniz biçimler korunur.\n\nDevam edilsin mi?', parent=self):
            return False
        t.enable_rich()
        self._place_text(d)
        return True

    def _fmt(self, what, value=None):
        d = self.cur()
        if not d:
            return
        t = d.text
        if not self._ensure_rich(d):
            return
        if what in ('b', 'i', 'u', 's', 'sup', 'sub'):
            t.toggle_char(what)
        elif what in ('color', 'hl'):
            t.toggle_char(what, value)
        elif what == 'font':
            value = (value or '').strip()
            if value and value != '—':
                t.toggle_char('font', value)
        elif what == 'size':
            try:
                v = float(str(value).replace(',', '.'))
            except (TypeError, ValueError):
                return
            v = max(1.0, min(400.0, v))
            t.toggle_char('size', int(v) if v == int(v) else v)
        elif what == 'grow':
            cur = float(t.current_format().get('size') or 11)
            sizes = [float(x.replace(',', '.')) for x in FONT_SIZES]
            nxt = [x for x in sizes if x > cur] if value > 0 else [x for x in sizes if x < cur]
            new = (nxt[0] if value > 0 else nxt[-1]) if nxt else cur
            t.toggle_char('size', int(new) if new == int(new) else new)
        elif what == 'clear':
            t.clear_formatting()
        elif what == 'style':
            t.set_style(value)
        elif what == 'list':
            t.toggle_list(value)
        elif what == 'level':
            t.change_level(value)
        elif what == 'indent':
            t.indent(value)
        elif what == 'align':
            t.set_align(value)
        elif what == 'spacing':
            t.set_para_extra(**value)
        elif what == 'pagebreak':
            t.insert_page_break()
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
        self._popup(m, self.fmt_btns['color'])

    def _highlight_menu(self):
        m = tk.Menu(self, tearoff=0)
        for label, val in HIGHLIGHT_COLORS:
            m.add_command(label=label, command=lambda v=val: self._fmt('hl', v))
        m.add_separator()
        m.add_command(label='Vurgu yok', command=lambda: self._fmt('hl', None))
        self._popup(m, self.fmt_btns['hl'])

    def _spacing_menu(self):
        d = self.cur()
        if not d or not self._ensure_rich(d):
            return
        fmt = d.text.current_format()
        cur = float(fmt.get('ls') or 1.15)
        m = tk.Menu(self, tearoff=0)
        for v in rdoc.LINE_SPACINGS:
            m.add_command(label=('✓ ' if abs(v - cur) < 0.01 else '    ') + ('%g' % v).replace('.', ','),
                          command=lambda x=v: self._fmt('spacing', {'ls': None if abs(x - 1.15) < 0.001 else x}))
        m.add_separator()
        sb, sa = fmt.get('sb'), fmt.get('sa')
        if sb:
            m.add_command(label='Paragraftan önceki boşluğu kaldır', command=lambda: self._fmt('spacing', {'sb': None}))
        else:
            m.add_command(label='Paragraftan önce boşluk ekle (12 nk)', command=lambda: self._fmt('spacing', {'sb': 12}))
        if sa is not None and sa == 0:
            m.add_command(label='Paragraftan sonra boşluk ekle (8 nk)', command=lambda: self._fmt('spacing', {'sa': None}))
        else:
            m.add_command(label='Paragraftan sonraki boşluğu kaldır', command=lambda: self._fmt('spacing', {'sa': 0}))
        m.add_separator()
        m.add_command(label='Satır aralığı seçenekleri…', command=self.paragraph_dialog)
        self._popup(m, self.fmt_btns.get('spacing') or self.fmt_bar)

    def _symbol_menu(self):
        d = self.cur()
        if not d:
            return
        m = tk.Menu(self, tearoff=0)
        for ch, name in SYMBOLS:
            m.add_command(label='%s   %s' % (ch, name), command=lambda c=ch: self._insert_symbol(c))
        self._popup(m, self.fmt_btns['symbol'])

    def _insert_symbol(self, ch):
        d = self.cur()
        if not d:
            return
        t = d.text
        if t.rich:
            t._type_text(ch)
        else:
            t.insert('insert', ch)
        t.focus_set()

    def format_painter(self, sticky=False):
        """Bicim boyacisi: ilk tik imlecteki bicimi alir; sonraki fare birakisinda secime uygular."""
        d = self.cur()
        if not d or not d.text.rich:
            return
        b = self.fmt_btns.get('painter')
        if getattr(self, '_painter', None):
            self._painter = None
            if b:
                self._set_on(b, False)
            self.flash('Biçim boyacısı kapatıldı.')
            return
        self._painter = {'fmt': d.text.copy_format(), 'sticky': sticky}
        if b:
            self._set_on(b, True)
        d.text.configure(cursor='pencil')
        self.flash('Biçim alındı. Uygulamak için metni fareyle seçin%s.' % (' (Esc ile bitir)' if sticky else ''), 9000)

    def _painter_release(self, d):
        p = getattr(self, '_painter', None)
        if not p or d is not self.cur():
            return
        if d.text.apply_format(p['fmt']):
            if not p['sticky']:
                self._painter = None
                d.text.configure(cursor='xterm')
                b = self.fmt_btns.get('painter')
                if b:
                    self._set_on(b, False)
            self._sync_fmt_bar()

    def _painter_cancel(self, e=None):
        if getattr(self, '_painter', None):
            self._painter = None
            b = self.fmt_btns.get('painter')
            if b:
                self._set_on(b, False)
            d = self.cur()
            if d:
                d.text.configure(cursor='xterm')

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
            bar.pack(fill='x', before=self.paned)
        t = d.text
        try:
            fmt = t.current_format()
        except tk.TclError:
            return
        style = fmt.get('style', 'normal')
        self.style_var.set(rdoc.STYLE_LABELS.get(style, rdoc.STYLE_LABELS['normal']))
        for k, b in self.style_btns.items():
            on = k == style and t.rich
            b.configure(bg=SEL_BG if on else PANEL2, fg=SEL_FG if on else FG, highlightbackground=ACCENT if on else LINE)
        on = {'b': fmt.get('b'), 'i': fmt.get('i'), 'u': fmt.get('u'), 's': fmt.get('s'), 'sup': fmt.get('va') == 'sup',
              'sub': fmt.get('va') == 'sub', 'bullet': fmt.get('list') == 'bullet',
              'number': fmt.get('list') == 'number', 'left': not fmt.get('align'), 'center': fmt.get('align') == 'center',
              'right': fmt.get('align') == 'right', 'justify': fmt.get('align') == 'justify'}
        for k, b in self.fmt_btns.items():
            if k in on:
                self._set_on(b, on[k] and t.rich)
        if self.focus_get() not in (self.font_cb, self.size_cb):
            self.font_var.set(fmt.get('font') or t.family)
            sz = fmt.get('size') or 11
            self.size_var.set(('%g' % sz).replace('.', ','))
        self._set_on(self.page_btn, t.page_mode)
        self._set_on(self.spell_btn, bool(self.settings.get('spellcheck', True)) and getattr(self, 'speller', None) is not None
                     and self.speller.available)
        self.fmt_hint.configure(text='' if t.rich else 'Düz metin (.txt) — biçimlendirme için bir düğmeye basın')
        if t.rich:
            self.fmt_hint.place_forget()
        else:
            self.fmt_hint.place(relx=1.0, rely=1.0, anchor='se', x=-8, y=-2)
        self._sync_page_info(d)

    def _sync_page_info(self, d):
        if not getattr(self, 'page_info', None):
            return
        pg = d.text.page
        m = pg['margins']
        cm = lambda v: ('%.2f' % (v / CM)).rstrip('0').rstrip('.').replace('.', ',')  # noqa: E731
        parts = ['%s · %s' % (pg['size'], 'Yatay' if pg['orient'] == 'landscape' else 'Dikey'),
                 'Kenar: üst %s, alt %s, sol %s, sağ %s cm' % (cm(m['t']), cm(m['b']), cm(m['l']), cm(m['r']))]
        extra = []
        if pg['header'].strip():
            extra.append('üst bilgi')
        if pg['footer'].strip():
            extra.append('alt bilgi')
        if pg['pnum']:
            extra.append('sayfa no.')
        if extra:
            parts.append('Var: ' + ', '.join(extra) + ' (Word / PDF çıktısında her sayfada)')
        self.page_info.configure(text='\n'.join(parts))

    def toggle_page_view(self):
        on = not self.settings.get('page_view', True)
        self.settings['page_view'] = on
        core.save_settings(self.settings)
        for d in self.docs:
            if d.text.rich:
                d.text.set_page_mode(on)
                self._place_text(d)
        self._sync_fmt_bar()
        self.flash('Sayfa görünümü açık: sayfa genişliği ve kenar boşlukları.' if on else 'Sayfa görünümü kapalı (tam genişlik).')

    def _place_text(self, d):
        t, desk = d.text, d.desk
        try:
            avail = desk.winfo_width()
        except tk.TclError:
            return
        if t.page_mode:
            w = int(t.px(rdoc.page_dims(t.page)[0]))
            full = int(t.px(t.page['margins']['l'] * 0.9))
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

    # ------------------------------------------------------------------ 2.0: sayfa yapisi
    def _page_changed(self, d, page, msg=None):
        t = d.text
        t.set_page_setup(page)
        if t.page_mode:
            t.set_page_mode(True)
        self._place_text(d)
        t.undo.saved = -1                       # sayfa ayari degisti: kaydedilmemis say
        self._doc_changed(d)
        self._sync_fmt_bar()
        if msg:
            self.flash(msg)

    def set_page(self, **kw):
        d = self.cur()
        if not d or not self._ensure_rich(d):
            return
        page = rdoc.normalize_page(d.text.page)
        for k, v in kw.items():
            page[k] = v
        self._page_changed(d, page)

    def _margins_menu(self):
        d = self.cur()
        if not d:
            return
        m = tk.Menu(self, tearoff=0)
        cur = tuple(round(v, 1) for v in (d.text.page['margins'][k] for k in 'tblr'))
        for key, label in rdoc.MARGIN_LABELS.items():
            t_, b_, l_, r_ = rdoc.MARGIN_PRESETS[key]
            mark = '✓ ' if tuple(round(v, 1) for v in (t_, b_, l_, r_)) == cur else '    '
            m.add_command(label=mark + label, command=lambda a=(t_, b_, l_, r_): self.set_page(
                margins={'t': a[0], 'b': a[1], 'l': a[2], 'r': a[3]}))
        m.add_separator()
        m.add_command(label='Özel kenar boşlukları…', command=self.page_setup_dialog)
        self._popup(m, self.fmt_btns['margins'])

    def _orient_menu(self):
        d = self.cur()
        if not d:
            return
        m = tk.Menu(self, tearoff=0)
        for key, label in (('portrait', 'Dikey'), ('landscape', 'Yatay')):
            m.add_command(label=('✓ ' if d.text.page['orient'] == key else '    ') + label, command=lambda k=key: self.set_page(orient=k))
        self._popup(m, self.fmt_btns['orient'])

    def _size_menu(self):
        d = self.cur()
        if not d:
            return
        m = tk.Menu(self, tearoff=0)
        for key, label in rdoc.PAGE_SIZE_LABELS.items():
            m.add_command(label=('✓ ' if d.text.page['size'] == key else '    ') + label, command=lambda k=key: self.set_page(size=k))
        m.add_separator()
        m.add_command(label='Sayfa yapısı…', command=self.page_setup_dialog)
        self._popup(m, self.fmt_btns['psize'])

    def _page_number_menu(self):
        d = self.cur()
        if not d:
            return
        m = tk.Menu(self, tearoff=0)
        pn = d.text.page.get('pnum')
        opts = (('Sayfanın altı · ortada', {'pos': 'footer', 'align': 'center'}), ('Sayfanın altı · sağda', {'pos': 'footer', 'align': 'right'}),
                ('Sayfanın altı · solda', {'pos': 'footer', 'align': 'left'}), ('Sayfanın üstü · sağda', {'pos': 'header', 'align': 'right'}),
                ('Sayfanın üstü · ortada', {'pos': 'header', 'align': 'center'}))
        fmt = (pn or {}).get('fmt', 'n')
        for label, o in opts:
            on = pn and pn['pos'] == o['pos'] and pn['align'] == o['align']
            m.add_command(label=('✓ ' if on else '    ') + label, command=lambda x=o: self.set_page(pnum=dict(x, fmt=fmt)))
        m.add_separator()
        if pn:
            m.add_command(label=('✓ ' if fmt == 'n_of_N' else '    ') + 'Biçim: "Sayfa 1 / 5"',
                          command=lambda: self.set_page(pnum=dict(pn, fmt='n' if fmt == 'n_of_N' else 'n_of_N')))
            m.add_command(label='Sayfa numarasını kaldır', command=lambda: self.set_page(pnum=None))
        self._popup(m, self.fmt_btns['pnum'])

    def _dialog(self, title):
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=PANEL, padx=16, pady=12)
        win.transient(self)
        win.resizable(False, False)
        win.bind('<Escape>', lambda e: win.destroy())
        self.last_dialog = win
        return win

    def page_setup_dialog(self):
        d = self.cur()
        if not d or not self._ensure_rich(d):
            return
        page = rdoc.normalize_page(d.text.page)
        win = self._dialog('Sayfa yapısı')
        vars_ = {}
        self.lbl(win, 'Kenar boşlukları (cm)', font=('Segoe UI', 10, 'bold')).grid(row=0, column=0, columnspan=4, sticky='w', pady=(0, 6))
        for k, (key, label) in enumerate((('t', 'Üst'), ('b', 'Alt'), ('l', 'Sol'), ('r', 'Sağ'))):
            v = tk.StringVar(value=('%.2f' % (page['margins'][key] / CM)).replace('.', ','))
            vars_[key] = v
            self.lbl(win, label).grid(row=1 + k // 2, column=(k % 2) * 2, sticky='w', pady=3)
            ttk.Spinbox(win, from_=0, to=10, increment=0.1, textvariable=v, width=7).grid(row=1 + k // 2, column=(k % 2) * 2 + 1,
                                                                                         sticky='w', padx=(6, 14), pady=3)
        self.lbl(win, 'Yönlendirme').grid(row=3, column=0, sticky='w', pady=(10, 3))
        ov = tk.StringVar(value=page['orient'])
        of = tk.Frame(win, bg=PANEL)
        of.grid(row=3, column=1, columnspan=3, sticky='w', pady=(10, 3))
        ttk.Radiobutton(of, text='Dikey', value='portrait', variable=ov).pack(side='left', padx=(6, 10))
        ttk.Radiobutton(of, text='Yatay', value='landscape', variable=ov).pack(side='left')
        self.lbl(win, 'Kâğıt boyutu').grid(row=4, column=0, sticky='w', pady=3)
        labels = list(rdoc.PAGE_SIZE_LABELS.values())
        sv = tk.StringVar(value=rdoc.PAGE_SIZE_LABELS[page['size']])
        ttk.Combobox(win, textvariable=sv, values=labels, state='readonly', width=24).grid(row=4, column=1, columnspan=3, sticky='w',
                                                                                         padx=6, pady=3)

        def ok():
            try:
                marg = {k: max(0.0, min(10.0, float(v.get().replace(',', '.')))) * CM for k, v in vars_.items()}
            except ValueError:
                messagebox.showerror('Sayfa yapısı', 'Kenar boşlukları sayı olmalı (ör. 2,5).', parent=win)
                return
            size = next((k for k, lab in rdoc.PAGE_SIZE_LABELS.items() if lab == sv.get()), 'A4')
            win.destroy()
            page.update(margins=marg, orient=ov.get(), size=size)
            self._page_changed(d, page, 'Sayfa yapısı güncellendi.')
        bf = tk.Frame(win, bg=PANEL)
        bf.grid(row=5, column=0, columnspan=4, sticky='e', pady=(12, 0))
        self.btn(bf, 'Tamam', ok, 'primary', side='right')
        self.btn(bf, 'Vazgeç', win.destroy, 'ghost', side='right')
        win.bind('<Return>', lambda e: ok())
        return win

    def header_footer_dialog(self, focus='header'):
        d = self.cur()
        if not d or not self._ensure_rich(d):
            return
        page = rdoc.normalize_page(d.text.page)
        win = self._dialog('Üst bilgi ve alt bilgi')
        boxes = {}
        for r, (key, label) in enumerate((('header', 'Üst bilgi (her sayfanın üstü)'), ('footer', 'Alt bilgi (her sayfanın altı)'))):
            self.lbl(win, label, font=('Segoe UI', 10, 'bold')).grid(row=r * 2, column=0, columnspan=3, sticky='w', pady=(6 if r else 0, 3))
            tb = self._textbox(win, height=2, width=60)
            tb.insert('1.0', page[key])
            tb.grid(row=r * 2 + 1, column=0, columnspan=3, sticky='we')
            boxes[key] = tb
        self.lbl(win, 'Sayfa numarası', font=('Segoe UI', 10, 'bold')).grid(row=4, column=0, sticky='w', pady=(10, 3))
        pn = page.get('pnum') or {}
        pos = tk.StringVar(value=pn.get('pos', 'none'))
        al = tk.StringVar(value=pn.get('align', 'center'))
        nf = tk.BooleanVar(value=pn.get('fmt') == 'n_of_N')
        f1 = tk.Frame(win, bg=PANEL)
        f1.grid(row=5, column=0, columnspan=3, sticky='w')
        for val, lab in (('none', 'Yok'), ('footer', 'Altta'), ('header', 'Üstte')):
            ttk.Radiobutton(f1, text=lab, value=val, variable=pos).pack(side='left', padx=(0, 10))
        tk.Frame(f1, bg=LINE, width=1, height=18).pack(side='left', padx=8)
        for val, lab in (('left', 'Sol'), ('center', 'Orta'), ('right', 'Sağ')):
            ttk.Radiobutton(f1, text=lab, value=val, variable=al).pack(side='left', padx=(0, 8))
        ttk.Checkbutton(win, text='"1 / 5" biçiminde (toplam sayfa ile)', variable=nf).grid(row=6, column=0, columnspan=3, sticky='w', pady=4)
        self.lbl(win, 'Üst/alt bilgi ve sayfa numarası, Word (.docx) dosyasında her sayfaya yazılır; editörde sayfa bölünmesi yaklaşıktır.',
                 muted=True, wraplength=int(460 * self.scale)).grid(row=7, column=0, columnspan=3, sticky='w', pady=(6, 0))

        def ok():
            page['header'] = boxes['header'].get('1.0', 'end-1c').strip()
            page['footer'] = boxes['footer'].get('1.0', 'end-1c').strip()
            page['pnum'] = None if pos.get() == 'none' else {'pos': pos.get(), 'align': al.get(), 'fmt': 'n_of_N' if nf.get() else 'n'}
            win.destroy()
            self._page_changed(d, page, 'Üst / alt bilgi güncellendi.')
        bf = tk.Frame(win, bg=PANEL)
        bf.grid(row=8, column=0, columnspan=3, sticky='e', pady=(12, 0))
        self.btn(bf, 'Tamam', ok, 'primary', side='right')
        self.btn(bf, 'Vazgeç', win.destroy, 'ghost', side='right')
        boxes.get(focus, boxes['header']).focus_set()
        win.ok = ok
        return win

    def paragraph_dialog(self):
        d = self.cur()
        if not d or not self._ensure_rich(d):
            return
        t = d.text
        fmt = t.current_format()
        win = self._dialog('Paragraf')
        cmf = lambda v: ('%.2f' % (float(v or 0) / CM)).rstrip('0').rstrip('.').replace('.', ',') or '0'  # noqa: E731
        self.lbl(win, 'Genel', font=('Segoe UI', 10, 'bold')).grid(row=0, column=0, sticky='w')
        self.lbl(win, 'Hizalama').grid(row=1, column=0, sticky='w', pady=3)
        align_labels = {'left': 'Sola', 'center': 'Ortala', 'right': 'Sağa', 'justify': 'İki yana yasla'}
        av = tk.StringVar(value=align_labels.get(fmt.get('align') or 'left'))
        ttk.Combobox(win, textvariable=av, values=list(align_labels.values()), state='readonly', width=16).grid(row=1, column=1, sticky='w',
                                                                                                             padx=6)
        self.lbl(win, 'Girinti', font=('Segoe UI', 10, 'bold')).grid(row=2, column=0, sticky='w', pady=(10, 0))
        self.lbl(win, 'Sol (cm)').grid(row=3, column=0, sticky='w', pady=3)
        ind = tk.StringVar(value=cmf(fmt.get('ind')))
        ttk.Spinbox(win, from_=0, to=15, increment=0.25, textvariable=ind, width=7).grid(row=3, column=1, sticky='w', padx=6)
        self.lbl(win, 'Özel').grid(row=4, column=0, sticky='w', pady=3)
        fi_val = float(fmt.get('fi') or 0)
        kinds = {'none': '(yok)', 'first': 'İlk satır', 'hang': 'Asılı'}
        kv = tk.StringVar(value=kinds['first' if fi_val > 0 else 'hang' if fi_val < 0 else 'none'])
        ttk.Combobox(win, textvariable=kv, values=list(kinds.values()), state='readonly', width=10).grid(row=4, column=1, sticky='w', padx=6)
        fiv = tk.StringVar(value=cmf(abs(fi_val)) if fi_val else '1,25')
        ttk.Spinbox(win, from_=0, to=10, increment=0.25, textvariable=fiv, width=7).grid(row=4, column=2, sticky='w')
        self.lbl(win, 'Aralık', font=('Segoe UI', 10, 'bold')).grid(row=5, column=0, sticky='w', pady=(10, 0))
        self.lbl(win, 'Önce (nk)').grid(row=6, column=0, sticky='w', pady=3)
        sbv = tk.StringVar(value=('%g' % fmt['sb']) if fmt.get('sb') is not None else '0')
        ttk.Spinbox(win, from_=0, to=200, increment=6, textvariable=sbv, width=7).grid(row=6, column=1, sticky='w', padx=6)
        self.lbl(win, 'Sonra (nk)').grid(row=7, column=0, sticky='w', pady=3)
        sav = tk.StringVar(value=('%g' % fmt['sa']) if fmt.get('sa') is not None else '8')
        ttk.Spinbox(win, from_=0, to=200, increment=6, textvariable=sav, width=7).grid(row=7, column=1, sticky='w', padx=6)
        self.lbl(win, 'Satır aralığı').grid(row=8, column=0, sticky='w', pady=3)
        lsv = tk.StringVar(value=('%g' % float(fmt.get('ls') or 1.15)).replace('.', ','))
        ttk.Combobox(win, textvariable=lsv, values=[('%g' % v).replace('.', ',') for v in rdoc.LINE_SPACINGS], width=7).grid(
            row=8, column=1, sticky='w', padx=6)

        def num(var, lo, hi):
            v = float(var.get().replace(',', '.'))
            return max(lo, min(hi, v))

        def ok():
            try:
                left = num(ind, 0, 15) * CM
                fi = num(fiv, 0, 10) * CM
                sb, sa, ls = num(sbv, 0, 1584), num(sav, 0, 1584), num(lsv, 0.5, 5)
            except ValueError:
                messagebox.showerror('Paragraf', 'Değerler sayı olmalı (ör. 1,25).', parent=win)
                return
            kind = next((k for k, v in kinds.items() if v == kv.get()), 'none')
            fi = fi if kind == 'first' else -fi if kind == 'hang' else 0
            align = next((k for k, v in align_labels.items() if v == av.get()), 'left')
            win.destroy()
            t.undo.separator()
            t.undo.begin()
            try:
                t.set_para_extra(ind=round(left, 1) or None, fi=round(fi, 1) or None, sb=(sb or None) if not fmt.get('sb') else sb,
                                 sa=None if abs(sa - 8) < 0.01 else sa, ls=None if abs(ls - 1.15) < 0.001 else ls)
                t.set_align(align)
            finally:
                t.undo.end()
            t.focus_set()
            self._sync_fmt_bar()
        bf = tk.Frame(win, bg=PANEL)
        bf.grid(row=9, column=0, columnspan=3, sticky='e', pady=(12, 0))
        self.btn(bf, 'Tamam', ok, 'primary', side='right')
        self.btn(bf, 'Vazgeç', win.destroy, 'ghost', side='right')
        win.bind('<Return>', lambda e: ok())
        win.ok = ok
        return win

    def insert_link(self):
        d = self.cur()
        if not d or not self._ensure_rich(d):
            return
        t = d.text
        try:
            sel = t.get('sel.first', 'sel.last')
        except tk.TclError:
            sel = ''
        cur = t.link_at('insert')
        win = self._dialog('Bağlantı')
        self.lbl(win, 'Görüntülenecek metin').grid(row=0, column=0, sticky='w', pady=3)
        tv = tk.StringVar(value=sel)
        te = ttk.Entry(win, textvariable=tv, width=44, state='disabled' if sel else 'normal')
        te.grid(row=0, column=1, padx=6, pady=3)
        self.lbl(win, 'Adres').grid(row=1, column=0, sticky='w', pady=3)
        uv = tk.StringVar(value=cur or ('' if not re.match(r'^(https?://|www\.)', sel) else sel))
        ue = ttk.Entry(win, textvariable=uv, width=44)
        ue.grid(row=1, column=1, padx=6, pady=3)

        def ok():
            url = uv.get().strip()
            if not url:
                return
            win.destroy()
            t.insert_link(url, None if sel else (tv.get().strip() or None))
            t.focus_set()

        def remove():
            win.destroy()
            t.remove_link()
        bf = tk.Frame(win, bg=PANEL)
        bf.grid(row=2, column=0, columnspan=2, sticky='e', pady=(10, 0))
        self.btn(bf, 'Tamam', ok, 'primary', side='right')
        self.btn(bf, 'Vazgeç', win.destroy, 'ghost', side='right')
        if cur:
            self.btn(bf, 'Bağlantıyı kaldır', remove, 'danger', side='left')
        win.bind('<Return>', lambda e: ok())
        ue.focus_set()
        win.ok = ok
        return win

    def open_link(self, url):
        import webbrowser
        if re.match(r'^(https?://|mailto:)', url or '', re.I):
            webbrowser.open(url)

    def _theme_menu(self):
        m = tk.Menu(self, tearoff=0)
        cur = self.settings.get('ui_theme', 'dark')
        for key, label in THEME_LABELS.items():
            m.add_command(label=('✓ ' if cur == key else '    ') + label, command=lambda k=key: self.set_theme(k))
        m.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    def set_theme(self, key):
        if self.settings.get('ui_theme', 'dark') == key:
            return
        self.settings['ui_theme'] = key
        core.save_settings(self.settings)
        if messagebox.askyesno('Tema', '%s tema bir sonraki açılışta uygulanır.\n\nŞimdi yeniden başlatılsın mı? '
                               '(Kaydedilmemiş belgeler için sorulur.)' % THEME_LABELS[key], parent=self):
            self.restart()

    def restart(self):
        files = [d.path for d in self.docs if d.path]
        self.on_close()
        try:
            if self.winfo_exists():
                return                          # kullanici kapatmayi iptal etti
        except tk.TclError:
            pass
        args = [sys.executable] + ([] if upd.is_frozen() else [os.path.abspath(sys.argv[0])]) + files
        # 2.0.1: PyInstaller ortam degiskenleri yeni surece GECMEMELI; yoksa yeni pencere eski surecin gecici klasorunu
        # (_MEI...) kullanir, eski surec kapaninca o klasor silinir ve "base_library.zip bulunamadi" hatasi cikar.
        subprocess.Popen(args, env=upd.scrub_env(), close_fds=True,
                         creationflags=(upd.DETACHED_PROCESS | upd.CREATE_NEW_PROCESS_GROUP) if IS_WIN else 0)

    def zoom_reset(self):
        self.settings['page_zoom'] = 1.0
        for d in self.docs:
            if d.text.rich:
                d.text.set_font(zoom=1.0)
                self._place_text(d)
        core.save_settings(self.settings)
        self._sync_zoom_label()

    def _sync_zoom_label(self):
        try:
            self.zoom_lbl.configure(text='%%%d' % round(float(self.settings.get('page_zoom', 1.0)) * 100))
        except (tk.TclError, AttributeError):
            pass

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
        self._panel_auto_hidden = False                     # elle secim otomatik gizlemeyi iptal eder
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
        self._tab_speech(self._ai_tab('Ses'))   # 1.5

    # ------------------------------------------------------------------ 1.5: Ses (EMA seslendirme)
    def _tab_speech(self, f):
        self.sp_state_var = tk.StringVar(value='Seslendirme: AI Manager bağlantısı denetleniyor…')
        self.sp_state_lbl = tk.Label(f, textvariable=self.sp_state_var, fg=MUTED, bg=PANEL, font=('Segoe UI', 9, 'bold'), anchor='w',
                                     justify='left', wraplength=int(380 * self.scale))
        self.sp_state_lbl.pack(fill='x', pady=(0, 6))
        # 1.7: ses servisi secimi
        svc = tk.Frame(f, bg=PANEL)
        svc.pack(fill='x', pady=(0, 6))
        self.lbl(svc, 'Ses servisi', muted=True).pack(side='left')
        self.sp_service_var = tk.StringVar(value=self._speech_mode())
        ttk.Radiobutton(svc, text='Site (AI Manager)', value='site', variable=self.sp_service_var,
                        command=self._speech_service_changed).pack(side='left', padx=(6, 4))
        ttk.Radiobutton(svc, text='Bu bilgisayar', value='local', variable=self.sp_service_var,
                        command=self._speech_service_changed).pack(side='left', padx=(0, 8))
        self.sp_sync_btn = self.btn(svc, 'Sözlüğü siteden eşitle', self.sync_local_lexicon, 'ghost', padx=8)
        row = tk.Frame(f, bg=PANEL)
        row.pack(fill='x', pady=(0, 4))
        self.lbl(row, 'Hız', muted=True).pack(side='left')
        self.sp_speed_var = tk.DoubleVar(value=float(self.settings.get('speech_speed', 1.0)))
        ttk.Spinbox(row, from_=0.7, to=1.4, increment=0.05, width=5, textvariable=self.sp_speed_var, format='%.2f',
                    command=self._speech_settings_changed).pack(side='left', padx=(6, 12))
        self.lbl(row, 'Paragraf arası (ms)', muted=True).pack(side='left')
        self.sp_ppause_var = tk.IntVar(value=int(self.settings.get('speech_paragraph_pause', 700)))
        ttk.Spinbox(row, from_=0, to=3000, increment=50, width=6, textvariable=self.sp_ppause_var,
                    command=self._speech_settings_changed).pack(side='left', padx=(6, 0))

        # 1.6: Sesli oku
        ra = tk.Frame(f, bg=PANEL2, padx=10, pady=8)
        ra.pack(fill='x', pady=(8, 0))
        tk.Label(ra, text='Sesli oku', fg=FG, bg=PANEL2, font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        self.lbl(ra, 'Seçimi ya da imleçten başlayarak belgeyi paragraf paragraf okur; okunan paragraf vurgulanır. '
                     'Sıradaki paragraflar arka planda hazırlanır.', muted=True, bg=PANEL2,
                 wraplength=int(360 * self.scale)).pack(anchor='w', pady=(0, 6))
        rrow = tk.Frame(ra, bg=PANEL2)
        rrow.pack(fill='x')
        self.ra_play_btn = self.btn(rrow, '▶ Sesli oku  (F9)', self.read_aloud, 'primary', padx=12, pady=6)
        self.ra_pause_btn = self.btn(rrow, '⏸ Duraklat', self.read_aloud_pause, 'ghost', padx=10)
        self.ra_stop_btn = self.btn(rrow, '■ Durdur', self.read_aloud_stop, 'ghost', padx=10)
        self.ra_pause_btn.configure(state='disabled')
        self.ra_stop_btn.configure(state='disabled')
        self.ra_script_var = tk.BooleanVar(value=bool(self.settings.get('readaloud_script', False)))
        tk.Checkbutton(ra, text='Okurken AI okuma metni kullan (yabancı adlar, sayılar; başlaması birkaç saniye gecikir)',
                       variable=self.ra_script_var, command=self._speech_settings_changed, bg=PANEL2, fg=FG, selectcolor=EDIT_BG,
                       activebackground=PANEL2, activeforeground=FG, font=('Segoe UI', 9), anchor='w', justify='left',
                       wraplength=int(340 * self.scale), highlightthickness=0, bd=0).pack(anchor='w', pady=(6, 0))
        self.ra_state_var = tk.StringVar(value='')
        tk.Label(ra, textvariable=self.ra_state_var, fg=ACCENT, bg=PANEL2, font=('Segoe UI', 9), anchor='w').pack(fill='x', pady=(4, 0))

        # 1.6: Ses dosyasi (bolum plani)
        fx = tk.Frame(f, bg=PANEL2, padx=10, pady=8)
        fx.pack(fill='x', pady=(10, 0))
        tk.Label(fx, text='Ses dosyası', fg=FG, bg=PANEL2, font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        self.lbl(fx, 'Belge önce başlıklara, uzun bölümler paragraf sınırında dengeli parçalara ayrılır. Bölümleri görüp seçer, '
                     'tek MP3 ya da bölüm başına MP3 alırsınız.', muted=True, bg=PANEL2,
                 wraplength=int(360 * self.scale)).pack(anchor='w', pady=(0, 6))
        self.sp_script_var = tk.BooleanVar(value=bool(self.settings.get('speech_script', True)))
        tk.Checkbutton(fx, text='Okuma metnini AI ile hazırla (yabancı adlar, sayılar, kısaltmalar)', variable=self.sp_script_var,
                       command=self._speech_settings_changed, bg=PANEL2, fg=FG, selectcolor=EDIT_BG, activebackground=PANEL2,
                       activeforeground=FG, font=('Segoe UI', 9), anchor='w', highlightthickness=0, bd=0).pack(anchor='w')
        go = tk.Frame(fx, bg=PANEL2)
        go.pack(fill='x', pady=(6, 0))
        self.btn(go, '🎧 Ses dosyası oluştur…', self.narrate_current, 'primary', padx=12, pady=6)
        self.btn(go, 'Okuma metnini önizle', self.preview_reading_script, 'ghost', padx=10)
        self.sp_result_var = tk.StringVar(value='')
        tk.Label(fx, textvariable=self.sp_result_var, fg=OK_C, bg=PANEL2, font=('Segoe UI', 9), anchor='w', justify='left',
                 wraplength=int(360 * self.scale)).pack(fill='x', pady=(4, 2))
        res = tk.Frame(fx, bg=PANEL2)
        res.pack(fill='x')
        self.sp_play_btn = self.btn(res, 'Dinle', lambda: self._open_external(getattr(self, '_sp_last', '')), 'ghost', padx=10)
        self.sp_folder_btn = self.btn(res, 'Klasörü aç', lambda: self._open_external(getattr(self, '_sp_last_dir', '') or
                                                                                    os.path.dirname(getattr(self, '_sp_last', '') or '')), 'ghost', padx=10)
        self.sp_play_btn.configure(state='disabled')
        self.sp_folder_btn.configure(state='disabled')

        box = tk.Frame(f, bg=PANEL2, padx=10, pady=8)
        box.pack(fill='x', pady=(10, 0))
        tk.Label(box, text='Telaffuz sözlüğü', fg=FG, bg=PANEL2, font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        self.lbl(box, 'Yanlış okunan bir adı seçip sağ tıklayın ya da aşağıdan ekleyin. Kayıt sunucudaki ortak listeye yazılır '
                      've hemen geçerli olur; “Bu bilgisayar” seçiliyken bu bilgisayardaki sözlüğe de yazılır.', muted=True, bg=PANEL2, wraplength=int(360 * self.scale)).pack(anchor='w', pady=(0, 6))
        brow = tk.Frame(box, bg=PANEL2)
        brow.pack(fill='x')
        self.btn(brow, 'Seçili kelimeyi ekle…', self.add_selection_to_lexicon, 'ghost', padx=10)
        self.btn(brow, 'Sözlüğü aç…', self.open_lexicon, 'ghost', padx=10)
        if self._speech_mode() == 'local':      # 1.7: yerel servis site baglantisini beklemeden denetlenir
            self.after(300, self._sync_speech_tab)
        else:
            self.sp_sync_btn.configure(state='disabled')

    def _speech_settings_changed(self):
        try:
            self.settings['speech_script'] = bool(self.sp_script_var.get())
            self.settings['speech_speed'] = max(0.7, min(1.4, round(float(self.sp_speed_var.get()), 2)))
            self.settings['speech_paragraph_pause'] = max(0, min(3000, int(self.sp_ppause_var.get())))
            self.settings['readaloud_script'] = bool(self.ra_script_var.get())
            core.save_settings(self.settings)
        except (tk.TclError, ValueError, OSError):
            pass

    # ------------------------------------------------------------------ 1.7: ses servisi (site / bu bilgisayar)
    def _local_tts_config(self):
        if hasattr(self, '_test_local_cfg'):
            return self._test_local_cfg
        return localtts.read_config()

    def _speech_mode(self):
        mode = self.settings.get('speech_service')
        if mode in ('site', 'local'):
            return mode
        return 'local' if self._local_tts_config() else 'site'

    def _speech_service_changed(self):
        self.settings['speech_service'] = self.sp_service_var.get()
        try:
            core.save_settings(self.settings)
        except OSError:
            pass
        self._sync_speech_tab()

    def _site_backend(self):
        for b in self.backends():
            if getattr(b, 'kind', '') == 'manager':
                return b
        return None

    def _local_backend(self, title=None):
        if hasattr(self, '_test_local_backend'):
            return self._test_local_backend
        cfg = self._local_tts_config()
        if not cfg:
            if title:
                messagebox.showinfo(title, 'Bu bilgisayarda AGFO Ses Servisi kurulu değil. AGFO-Ses-Kur.cmd ile kurun ya da '
                                           'Ses sekmesinde “Site (AI Manager)”ı seçin.', parent=self)
            return None
        return localtts.LocalSpeechBackend(cfg['endpoint'], cfg['token'], site=self._site_backend())

    def _speech_backend(self, title):
        """Secili ses servisi: bu bilgisayar ya da sitedeki AI Manager."""
        if self._speech_mode() == 'local':
            return self._local_backend(title)
        return self._manager_backend(title)

    def sync_local_lexicon(self):
        title = 'Sözlüğü eşitle'
        b = self._local_backend(title)
        if not b:
            return
        if b.site is None:
            messagebox.showinfo(title, 'Ortak sözlük sitedeki AI Manager üzerinden alınır; Ayarlar › Bağlantı bölümünden sitenizi ekleyin.',
                                parent=self)
            return

        def done(ok, res):
            if not ok:
                messagebox.showerror(title, res, parent=self)
                return
            msg = 'Sözlük eşitlendi: %d kelime eklendi/güncellendi, %d kaldırıldı, %d zaten aynıydı.' % (
                res['added'], res['removed'], res['same'])
            if res['errors']:
                msg += ' %d kelimede hata: %s' % (len(res['errors']), '; '.join(res['errors'][:3]))
            self.flash(msg, 9000)
            self.sp_result_var.set(msg)
        self._start_job('Sözlük eşitleniyor', b.sync_from_site, done)

    def _sync_speech_tab(self):
        if not hasattr(self, 'sp_state_var'):
            return
        local = self._speech_mode() == 'local'
        try:
            self.sp_sync_btn.configure(state='normal' if local else 'disabled')
        except (AttributeError, tk.TclError):
            pass
        if local:
            b = self._local_backend()
            if b is None:
                self.sp_state_var.set('● Bu bilgisayarda ses servisi kurulu değil: AGFO-Ses-Kur.cmd ile kurun.')
                self.sp_state_lbl.configure(fg=WARN)
                return
            self.sp_state_var.set('● Bu bilgisayardaki ses servisi denetleniyor…')
            self.sp_state_lbl.configure(fg=MUTED)

            def done(ok, res):
                if self._speech_mode() != 'local':
                    return
                if ok:
                    dev = str(res.get('device') or 'cpu')
                    where = 'ekran kartında' if dev.startswith('cuda') else 'işlemcide'
                    self.sp_state_var.set('● EMA Lightning bu bilgisayarda hazır (%s, %s kelimelik sözlük)' % (where, res.get('lexicon_entries', '?')))
                    self.sp_state_lbl.configure(fg=OK_C)
                else:
                    self.sp_state_var.set('● ' + str(res))
                    self.sp_state_lbl.configure(fg=WARN)
            self._start_job('Ses servisi denetleniyor', b.health, done)
            return
        info = (self.manager_info or {}).get('speech') if isinstance(self.manager_info, dict) else None
        if not isinstance(info, dict):
            self.sp_state_var.set('Seslendirme için sitede AGFO AI Manager 17.12.0 veya üstü gerekir.')
            self.sp_state_lbl.configure(fg=WARN)
            return
        if info.get('speech_ready'):
            self.sp_state_var.set('● EMA Lightning hazır (sitedeki AI Manager üzerinden)')
            self.sp_state_lbl.configure(fg=OK_C)
        else:
            self.sp_state_var.set('● Sitede EMA servis token’ı yok: AI Manager › Sağlayıcılar › EMA Lightning')
            self.sp_state_lbl.configure(fg=WARN)
        if 'speech_script' not in self.settings and 'reading_script_default' in info:
            self.sp_script_var.set(bool(info.get('reading_script_default')))

    def _manager_backend(self, title):
        for b in self.backends():
            if getattr(b, 'kind', '') == 'manager':
                return b
        messagebox.showinfo(title, 'Bu özellik sitenizdeki AGFO AI Manager üzerinden çalışır. Ayarlar › Bağlantı bölümünden '
                                   'AI Manager site adresini ve bağlantı anahtarını girin.', parent=self)
        return None

    def _speech_source(self, title):
        """(metin, belge, kapsam etiketi) ya da None."""
        d = self.cur()
        if not d:
            messagebox.showinfo(title, 'Seslendirme metin belgelerinde yapılır. PDF için önce “Metin olarak aç”ı kullanın.', parent=self)
            return None
        start, end, what = self._scope_range(d)
        raw = d.text.markdown(start, end)[0] if d.rich else d.text.get(start, end)
        text = speech.markdown_to_speech(raw)
        if not text.strip():
            messagebox.showinfo(title, 'Seslendirilecek metin bulunamadı.', parent=self)
            return None
        return text, d, what

    def preview_reading_script(self):
        title = 'Okuma metni'
        b = self._manager_backend(title)
        src = b and self._speech_source(title)
        if not src:
            return
        text, d, what = src

        def done(ok, res):
            if not ok:
                messagebox.showerror(title, res, parent=self)
                return
            nd = self.new_doc(text=res.get('text', ''), title='Okuma metni – ' + (d.title or 'belge'))
            if nd is not None:
                nd.speech_script = True
            note = '%d/%d bölüm hazırlandı (%s)' % (res.get('rewritten', 0), res.get('chunks', 0), res.get('model', ''))
            if res.get('kept_original'):
                note += '; %d bölüm özgün bırakıldı' % res['kept_original']
            self.flash('Okuma metni yeni sekmede: ' + note + '. Düzeltip bu sekmeden “Ses dosyası oluştur” ya da “Sesli oku”yu kullanın.', 12000)
        self._start_job('Okuma metni hazırlanıyor (%s)' % what, b.speech_script, done, text)

    def narrate_current(self):
        """1.6: bolum planini gosteren 'Ses dosyasi olustur' penceresi."""
        title = 'Ses dosyası oluştur'
        b = self._speech_backend(title)
        if not b:
            return None
        d = self.cur()
        if not d:
            messagebox.showinfo(title, 'Ses dosyası metin belgelerinden oluşturulur. PDF için önce “Metin olarak aç”ı kullanın.', parent=self)
            return None
        start, end, what = self._scope_range(d, force_all=self.scope_var.get() == 'all')
        try:
            d.text.index('sel.first')
        except tk.TclError:
            if what == 'paragraf':                  # secim yoksa tum belge (tek paragrafin dosyasi pek istenmez)
                start, end, what = '1.0', d.text.index('end-1c'), 'belge'
        md = d.text.markdown(start, end)[0] if d.rich else d.text.get(start, end)
        sections = speech.plan_sections(md)
        if not sections:
            messagebox.showinfo(title, 'Seslendirilecek metin bulunamadı.', parent=self)
            return None
        win = getattr(self, 'export_win', None)
        if win is not None and win.winfo_exists():
            win.destroy()
        self.export_win = SpeechExportWindow(self, b, d, sections, what)
        return self.export_win

    # ------------------------------------------------------------------ 1.6: Sesli oku
    def read_aloud(self):
        ses = getattr(self, 'ra_session', None)
        if ses is not None and not ses.done:
            self.read_aloud_pause()
            return
        title = 'Sesli oku'
        b = self._speech_backend(title)
        d = b and self.cur()
        if not d:
            if b:
                messagebox.showinfo(title, 'Sesli okuma metin belgelerinde yapılır.', parent=self)
            return
        info = (self.manager_info or {}).get('speech') if isinstance(self.manager_info, dict) else None
        if getattr(b, 'kind', '') == 'manager' and isinstance(info, dict) and not info.get('quick'):
            messagebox.showinfo(title, 'Sesli okuma için sitede AGFO AI Manager 17.13.0 veya üstü gerekir.', parent=self)
            return
        t = d.text
        try:
            first_line, last_line = int(t.index('sel.first').split('.')[0]), int(t.index('sel.last').split('.')[0])
        except tk.TclError:
            first_line, last_line = int(t.index('insert').split('.')[0]), int(t.index('end-1c').split('.')[0])
        lines = t.get('1.0', 'end-1c').split('\n')
        segments = []
        for a, z in readaloud.group_paragraphs(lines, d.rich):
            if z + 1 < first_line or a + 1 > last_line:
                continue
            s0, e0 = '%d.0' % (a + 1), '%d.end' % (z + 1)
            raw = t.markdown(s0, e0)[0] if d.rich else t.get(s0, e0)
            texts = readaloud.split_piece(speech.markdown_to_speech(raw))
            if not texts:
                continue
            i = len(segments)
            t.mark_set('ra_s%d' % i, s0)
            t.mark_gravity('ra_s%d' % i, 'left')
            t.mark_set('ra_e%d' % i, e0)
            segments.append({'id': i, 'texts': texts})
        if not segments:
            messagebox.showinfo(title, 'Okunacak metin bulunamadı.', parent=self)
            return
        self._speech_settings_changed()
        ready = bool(getattr(d, 'speech_script', False))
        opts = {'reading_script': bool(self.ra_script_var.get()) and not ready, 'script_ready': ready,
                'speed': float(self.settings.get('speech_speed', 1.0)), 'pause_ms': 280, 'paragraph_pause_ms': 0}
        key = '%s-%.2f' % ('hazir' if ready else ('ai' if opts['reading_script'] else 'sozluk'), opts['speed'])
        cache = core.data_dir() / 'readaloud' / key
        self._prune_readaloud_cache()
        t.tag_configure('readaloud', background=READ_BG, foreground=FG)
        self.ra_doc = d
        self.ra_count = len(segments)
        self.ra_session = readaloud.ReadAloud(segments, lambda text: b.speech_quick(text, **opts), str(cache),
                                              player=getattr(self, '_test_player', None),
                                              on_segment=self._ra_segment, on_state=self._ra_state)
        self.ra_play_btn.configure(text='⏯ Duraklat / sürdür  (F9)')
        self.ra_pause_btn.configure(state='normal')
        self.ra_stop_btn.configure(state='normal')
        self.ra_session.start()
        self._ra_tick()

    def _ra_tick(self):
        ses = getattr(self, 'ra_session', None)
        if ses is None or ses.done:
            return
        try:
            ses.tick()
        except Exception:
            self._log_error(traceback.format_exc())
            ses.stop()
            return
        self._timers['readaloud'] = self.after(150, self._ra_tick)

    def _ra_segment(self, i):
        d = getattr(self, 'ra_doc', None)
        if d is None or not d.text.winfo_exists():
            return
        t = d.text
        t.tag_remove('readaloud', '1.0', 'end')
        try:
            t.tag_add('readaloud', 'ra_s%d' % i, 'ra_e%d' % i)
            t.see('ra_e%d' % i)
            t.see('ra_s%d' % i)
        except tk.TclError:
            pass

    def _ra_state(self, state, msg=''):
        self.ra_state_var.set(msg)
        if state in ('bitti', 'hata', 'durdu'):
            d = getattr(self, 'ra_doc', None)
            if d is not None and d.text.winfo_exists():
                d.text.tag_remove('readaloud', '1.0', 'end')
                for i in range(getattr(self, 'ra_count', 0)):
                    for m in ('ra_s%d' % i, 'ra_e%d' % i):
                        try:
                            d.text.mark_unset(m)
                        except tk.TclError:
                            pass
            self.ra_play_btn.configure(text='▶ Sesli oku  (F9)')
            self.ra_pause_btn.configure(state='disabled', text='⏸ Duraklat')
            self.ra_stop_btn.configure(state='disabled')
            if state == 'hata':
                self.flash('Sesli okuma durdu: ' + msg, 10000)
        elif state == 'duraklatıldı':
            self.ra_pause_btn.configure(text='▶ Sürdür')
        elif state == 'okuyor':
            self.ra_pause_btn.configure(text='⏸ Duraklat')

    def read_aloud_pause(self):
        ses = getattr(self, 'ra_session', None)
        if ses is not None and not ses.done:
            ses.toggle_pause()

    def read_aloud_stop(self):
        ses = getattr(self, 'ra_session', None)
        if ses is not None and not ses.done:
            ses.stop()

    def _prune_readaloud_cache(self, keep_days=7):
        import time as _time
        root = core.data_dir() / 'readaloud'
        if not root.exists():
            return
        limit = _time.time() - keep_days * 86400
        for p in root.glob('*/*'):
            try:
                if p.stat().st_mtime < limit:
                    p.unlink()
            except OSError:
                pass

    def _open_external(self, path):
        if not path:
            return
        try:
            if IS_WIN:
                os.startfile(path)  # noqa: S606 - kullanicinin kendi dosyasi
        except OSError as e:
            messagebox.showerror('Aç', str(e), parent=self)

    def add_selection_to_lexicon(self):
        d = self.cur()
        word = ''
        if d:
            try:
                word = d.text.get('sel.first', 'sel.last').strip()
            except tk.TclError:
                word = ''
        if len(word) > 80 or '\n' in word:
            word = ''
        self.open_lexicon(word=word)

    def open_lexicon(self, word=''):
        b = self._speech_backend('Telaffuz sözlüğü')
        if not b:
            return None
        win = getattr(self, 'lexicon_win', None)
        if win is not None and win.winfo_exists() and getattr(win.b, 'kind', '') != getattr(b, 'kind', ''):
            win.destroy()
        if win is not None and win.winfo_exists():
            win.lift()
            if word:
                win.set_word(word)
            return win
        self.lexicon_win = LexiconWindow(self, b, word)
        return self.lexicon_win

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
                    highlightthickness=1, highlightbackground=LINE, highlightcolor=ACCENT, font=('Segoe UI', 10),
                    selectbackground=SEL_BG, selectforeground=SEL_FG, padx=6, pady=4, undo=True, **kw)
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
        self.tr_lang = tk.StringVar(value='Türkçe')   # 1.4.15: çeviri hedefi varsayılan Türkçe
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

    def new_doc(self, text='', title=None, path=None, docfile=None, blocks=None, rich=None, page=None):
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
                           selectbackground=SEL_BG, selectforeground=SEL_FG, inactiveselectbackground=INACTIVE_SEL)
        t.configure(yscrollcommand=ys.set)
        ys.configure(command=t.yview)
        base = tkfont.Font(family=self._editor_font()[0], size=self._editor_font()[1])
        t.tag_configure('md_h', foreground=HEAD_FG, font=(base.actual('family'), int(self._editor_font()[1] * 1.25), 'bold'))
        t.tag_configure('md_mark', foreground=MUTED)
        t.tag_configure('md_li', foreground=FG, lmargin2=int(18 * self.scale))
        t.tag_configure('found', background=FOUND)
        t.tag_configure('ai_new', background=NEW_BG)
        t.tag_configure('trwork', background=WORK_BG)
        t.tag_configure('trdone', background=NEW_BG)
        t.on_link = self.open_link                           # 2.0: Ctrl+tik baglantiyi acar
        if page:
            t.set_page_setup(page)
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
        t.bind('<ButtonRelease-1>', lambda e, dd=doc: self._painter_release(dd), add='+')     # 2.0: bicim boyacisi
        t.bind('<Escape>', self._painter_cancel, add='+')
        t.bind('<Control-k>', lambda e: (self.insert_link(), 'break')[1])
        t.bind('<Control-K>', lambda e: (self.insert_link(), 'break')[1])
        t.bind('<KeyRelease>', lambda e, dd=doc: self._schedule_highlight(dd), add='+')
        t.bind('<KeyRelease>', lambda e, dd=doc: self._spell_typed(dd), add='+')
        self._highlight(doc)
        t.bind('<<Modified>>', lambda e, d=doc: self._on_modified(d))
        t.on_change = lambda d=doc: self._doc_changed(d)
        t.bind('<Button-3>', self._context_menu)
        t.focus_set()
        self._update_status()
        self._sync_fmt_bar()
        self.spell_full(doc)
        return doc

    # ------------------------------------------------------------------ 2.0: yazim denetimi
    SPELL_BATCH = 60                 # her adimda denetlenen satir

    def _spell_on(self):
        return bool(self.settings.get('spellcheck', True))

    def _ensure_speller(self, quiet=True):
        if self.speller is None:
            if self.smoke:
                return None
            try:
                self.speller = spell.create(self.settings.get('spell_lang') or 'tr-TR')
            except Exception as e:                 # beklenmeyen COM hatasi: editor calismaya devam etsin
                self._log_error('spell: %r' % (e,))
                return None
            if not self.speller.available and not quiet:
                messagebox.showinfo('Yazım denetimi', self.speller.error, parent=self)
        return self.speller if self.speller and self.speller.available else None

    def toggle_spell(self):
        on = not self._spell_on()
        if on and self._ensure_speller(quiet=False) is None:
            self.settings['spellcheck'] = False
            core.save_settings(self.settings)
            self._sync_fmt_bar()
            return
        self.settings['spellcheck'] = on
        core.save_settings(self.settings)
        for d in self.docs:
            if on:
                self.spell_full(d)
            else:
                d.text.tag_remove('spell', '1.0', 'end')
        self._sync_fmt_bar()
        self.flash('Yazım denetimi açık: hatalı kelimeler kırmızıyla işaretlenir, sağ tıkla öneri alın.' if on else 'Yazım denetimi kapalı.')

    def spell_full(self, d):
        """Belgenin tamamini arka planda parca parca denetler."""
        if not self._spell_on() or self._ensure_speller() is None:
            return
        d._spell_pos = 1
        if not getattr(d, '_spell_job', None):
            d._spell_job = self.after(300, lambda: self._spell_step(d))

    def _spell_step(self, d):
        d._spell_job = None
        if d not in self.docs or not self._spell_on() or self.speller is None:
            return
        t = d.text
        try:
            last = int(t.index('end-1c').split('.')[0])
        except tk.TclError:
            return
        a = getattr(d, '_spell_pos', 1)
        b = min(last, a + self.SPELL_BATCH - 1)
        self.spell_lines(d, a, b)
        if b < last:
            d._spell_pos = b + 1
            d._spell_job = self.after(15, lambda: self._spell_step(d))

    def spell_lines(self, d, first, last):
        sp = self.speller
        if sp is None or not sp.available:
            return
        t = d.text
        for ln in range(first, last + 1):
            s0, e0 = '%d.0' % ln, '%d.end' % ln
            try:
                text = t.get(s0, e0)
            except tk.TclError:
                return
            t.tag_remove('spell', s0, e0)
            if not text.strip():
                continue
            try:
                errs = sp.check(text)
            except Exception as e:
                self._log_error('spell check: %r' % (e,))
                return
            for st, n, _act, _rep in errs:
                a, b = '%d.%d' % (ln, st), '%d.%d' % (ln, st + n)
                names = set(str(x) for x in t.tag_names(a))
                if 'lm' in names or any(x.startswith('ln_') for x in names):
                    continue                      # liste isareti ve baglantilar denetlenmez
                t.tag_add('spell', a, b)

    def _spell_typed(self, d):
        """Yazarken: imlecin bulundugu ve komsu satirlari kisa gecikmeyle denetler."""
        if not self._spell_on() or self.speller is None:
            return
        if getattr(d, '_spell_line_job', None):
            try:
                self.after_cancel(d._spell_line_job)
            except (tk.TclError, ValueError):
                pass

        def run():
            d._spell_line_job = None
            if d not in self.docs:
                return
            try:
                ln = int(d.text.index('insert').split('.')[0])
                last = int(d.text.index('end-1c').split('.')[0])
            except tk.TclError:
                return
            self.spell_lines(d, max(1, ln - 1), min(last, ln + 1))
        d._spell_line_job = self.after(450, run)

    def spell_error_at(self, t, index):
        if 'spell' not in [str(x) for x in t.tag_names(index)]:
            return None
        r = t.tag_prevrange('spell', index + '+1c')
        if not r:
            return None
        return str(r[0]), str(r[1]), t.get(r[0], r[1])

    def spell_replace(self, d, s0, e0, word):
        t = d.text
        keep = tuple(str(x) for x in t.tag_names(s0) if rtext.recorded(str(x)))
        t.undo.separator()
        t.undo.begin()
        try:
            t.delete(s0, e0)
            t.insert(s0, word, keep)
        finally:
            t.undo.end()
        t.undo.separator()
        t.changed()
        ln = int(s0.split('.')[0])
        self.spell_lines(d, ln, ln)

    def spell_add(self, d, word):
        if self.speller:
            self.speller.add(word)
        for x in self.docs:
            self.spell_full(x)

    def spell_ignore(self, d, word):
        if self.speller:
            self.speller.ignore(word)
        for x in self.docs:
            self.spell_full(x)


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
        if os.path.splitext(path)[1].lower() == '.docx':
            prof = self._brcgs_profile_of(path)
            if prof:
                # 2.3.0: BRCGS raporu dogrudan Word gorunumunde acilir ve bu dosyaya baglanir (ice/disa aktarma yok)
                return self.open_brcgs_docx(path)
        try:
            kind = core.detect_kind(path)
            page = None
            if kind == 'docx':
                blocks = rdoc.read_docx_blocks(path)
                page = rdoc.read_docx_page(path)            # 2.0: sayfa yapisi, ust/alt bilgi, sayfa no.
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
        d = self.new_doc(text, os.path.basename(path), path, docfile, blocks=blocks, page=page)
        core.add_recent(self.settings, path)
        core.save_settings(self.settings)
        if docfile.kind == 'docx':
            n_img = sum(1 for b in blocks or [] if b['t'] == 'img')
            n_tbl = sum(1 for b in blocks or [] if b['t'] == 'table')
            self.flash('Word belgesi biçimleriyle açıldı (%d resim, %d tablo). Sayfa yapısı ve üst/alt bilgi korunur; dipnot ve yorumlar '
                       'bu editörde gösterilmez.' % (n_img, n_tbl), 9000)
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
        if not self.nb.tabs() and ask:
            self.new_doc()
        return True

    # ------------------------------------------------------------------ BRCGS Report Studio (2.2)
    def brcgs_store(self):
        if getattr(self, '_brcgs_store', None) is None:
            from agfo_brcgs import store as brs
            self._brcgs_store = brs.Store()
        return self._brcgs_store

    def _brcgs_ready(self):
        try:
            import lxml  # noqa: F401
            return True
        except ImportError:
            messagebox.showerror('BRCGS reports', 'The lxml component is missing from this installation, so BRCGS reports cannot open. Please update the application.',
                                 parent=self)
            return False

    def _drop_blank_doc(self):
        """Acilista gelen tek bos 'Adsiz' belge, yeni sekme acilinca kapatilir (PDF acarken oldugu gibi)."""
        if len(self.docs) == 1:
            d = self.docs[0]
            if not d.path and not d.dirty and not d.text.get('1.0', 'end-1c').strip():
                self.close_doc(d, ask=False)

    def open_brcgs(self):
        """Rapor gezgini sekmesi (tek ornek)."""
        if self.brcgs_explorer is not None:
            self.brcgs_explorer.refresh()
            self.nb.select(self.brcgs_explorer)
            return self.brcgs_explorer
        if not self._brcgs_ready():
            return None
        import agfo_brcgs_view
        v = agfo_brcgs_view.BrcgsExplorer(self, self.nb, self.brcgs_store())
        self.brcgs_explorer = v
        self.nb.add(v, text='📋 BRCGS reports')
        self.nb.select(v)
        self._drop_blank_doc()
        return v

    def _brcgs_panel_auto(self):
        """BRCGS sekmelerinde AI paneli yer kaplamasin: sekmeye gelince gizlenir, belgeye donunce geri acilir."""
        shown = str(self.side_panel) in self.paned.panes()
        on_brcgs = self.cur_brcgs() is not None
        if on_brcgs and shown:
            self.paned.forget(self.side_panel)
            self.panel_btn.configure(text='AI paneli ⇤')
            self._panel_auto_hidden = True
        elif not on_brcgs and not shown and getattr(self, '_panel_auto_hidden', False):
            self.paned.add(self.side_panel, weight=2)
            self.panel_btn.configure(text='AI paneli ⇥')
            self._panel_auto_hidden = False

    def brcgs_view_for(self, uid):
        return next((v for v in self.brcgs_views if v.uid == uid), None)

    def _brcgs_profile_of(self, path):
        try:
            import zipfile
            with zipfile.ZipFile(path) as z:
                xml = z.read('word/document.xml')
            if b'w:sdt' not in xml or not any(t in xml for t in (b'w:val="OWNERCOMPANY"', b'w:val="BRC_SITE_CODE"', b'BRCGS')):
                return None
            from agfo_brcgs import docx_engine as bre
            return bre.detect_profile(bre.DocxTemplate(path))
        except Exception:
            return None

    def open_brcgs_docx(self, path):
        """BRCGS DOCX'i acar: bu dosyaya bagli rapor varsa onu (dosya Word'de degistiyse gunceller), yoksa dosyayi baglayarak
        yeni rapor olusturur. Kaydet dogrudan bu dosyaya yazar."""
        if not self._brcgs_ready():
            return None
        uid = self.brcgs_store().find_linked(path)
        if uid:
            v = self.open_brcgs_report(uid)
            if v is not None:
                v.check_linked()
            return v
        return self.import_brcgs_docx(path, link=True)

    def doc_renderer(self):
        if getattr(self, '_doc_renderer', None) is None:
            import agfo_docrender
            self._doc_renderer = agfo_docrender.Renderer(core.data_dir() / 'render-cache')
        return self._doc_renderer

    def _brcgs_focus_check(self, _e=None):
        """Pencere odaga donunce (or. Word'den) bagli DOCX degismis mi bak."""
        import time
        now = time.time()
        if now - getattr(self, '_brcgs_focus_t', 0) < 1.5:
            return
        self._brcgs_focus_t = now
        v = self.cur_brcgs()
        if v is not None and v is not self.brcgs_explorer:
            self.after(150, v.check_linked)

    def import_brcgs_docx(self, path, link=False):
        if not self._brcgs_ready():
            return None
        try:
            pr = self.brcgs_store().import_docx(path, link=link)
        except Exception as e:
            messagebox.showerror('BRCGS report', '%s\n\n%s' % (os.path.basename(path), e), parent=self)
            return None
        if self.brcgs_explorer is not None:
            self.brcgs_explorer.refresh()
        v = self.open_brcgs_report(pr['id'])
        self.flash(('BRCGS report opened from %s (%d filled sections). Save writes straight into this file.' if link else
                    'BRCGS report imported from %s (%d filled sections). The original DOCX is unchanged.')
                   % (os.path.basename(path), sum(1 for s_ in pr['sections'] if str(s_.get('value') or '').strip())), 9000)
        return v

    def cur_brcgs(self):
        try:
            w = self.nametowidget(self.nb.select())
        except (KeyError, tk.TclError):
            return None
        return w if w in self.brcgs_views or w is self.brcgs_explorer else None

    def open_brcgs_report(self, uid):
        v = self.brcgs_view_for(uid)
        if v:
            self.nb.select(v)
            return v
        if not self._brcgs_ready():
            return None
        import agfo_brcgs_view
        try:
            v = agfo_brcgs_view.BrcgsReportView(self, self.nb, self.brcgs_store(), uid)
        except Exception as e:
            self._log_error(traceback.format_exc())
            messagebox.showerror('Could not open the report', str(e), parent=self)
            return None
        self.brcgs_views[v] = v
        self.nb.add(v, text=v.tab_text())
        self.nb.select(v)
        self._drop_blank_doc()
        return v

    def brcgs_dirty_changed(self, v):
        try:
            if v in self.brcgs_views:
                self.nb.tab(v, text=v.tab_text())
        except tk.TclError:
            pass
        if self.brcgs_explorer is not None and not v.dirty:
            self.brcgs_explorer.refresh()

    def brcgs_title_changed(self, uid, title):
        v = self.brcgs_view_for(uid)
        if v:
            v.project['title'] = title
            v._refresh_header()
            self.brcgs_dirty_changed(v)

    def close_brcgs_view(self, v, ask=True):
        if v is self.brcgs_explorer:
            self.nb.forget(v)
            v.destroy()
            self.brcgs_explorer = None
        else:
            if ask and v.dirty:
                self.nb.select(v)
                ans = messagebox.askyesnocancel('Unsaved changes', 'Save the report "%s"?' % v.project['title'], parent=self)
                if ans is None:
                    return False
                if ans and not v.save():
                    return False
                if not ans:
                    v.store.drop_draft(v.uid)
            self.nb.forget(v)
            self.brcgs_views.pop(v, None)
            v.destroy()
            if self.brcgs_explorer is not None:
                self.brcgs_explorer.refresh()
        if not self.nb.tabs():
            self.new_doc()
        return True

    BRCGS_NC_MARK = '=== NON-CONFORMITIES ==='

    @staticmethod
    def brcgs_skill_rules(profile, limit=3800):
        """Teknik gozden gecirme skill'inin yazim kurallari (rapor yazimi, kanit/dokuman referansi, standarda ozel bolumler)."""
        try:
            from agfo_brcgs import review_pack as brp
        except Exception:
            return ''
        keep = ('report-writing', 'evidence and document', 'specific', 'applicability', 'non-conformities', 'scope', 'reporting')
        lines, n = [], 0
        for head, rule in brp.skill_rules(profile):
            if not any(k in head.lower() for k in keep):
                continue
            ln = '- ' + rule
            if n + len(ln) > limit:
                break
            lines.append(ln)
            n += len(ln) + 1
        return '\n'.join(lines)

    def brcgs_ai_call(self, label, instruction, src, on_text, language='English'):
        """Genel BRCGS AI cagrisi (arka planda); on_text(metin, model) ana is parcaciginda."""
        try:
            backends = self.backends()
        except Exception as e:
            messagebox.showerror('AI', str(e), parent=self)
            return None
        action = {'key': 'brcgs_review', 'label': label, 'template': 'custom', 'extra': instruction, 'mode': 'replace', 'description': ''}
        options = self._ai_options()
        options.update(language=language, rich=False, from_scratch=False, preserve_facts=True, user_extra=instruction)

        def work():
            return ai.run_with_fallback(backends, 'transform', src, action, options)

        def done(ok, r):
            if not ok:
                messagebox.showerror('AI', r, parent=self)
                return
            on_text((r.get('text') or '').strip(), self.model_label(r))
        return self._start_job(label, work, done)

    def brcgs_ai_prompt(self, profile, row, ncs):
        from agfo_brcgs import data as brd
        clause, title = row['clause'], row.get('title') or ''
        text = ('You are writing the "%s %s" section of an official BRCGS %s audit report. Turn the auditor\'s evidence below '
                '(often Turkish, sometimes fragmentary notes or answers to guideline questions) into clear, factual English audit '
                'report prose: complete connected paragraphs, passive voice, objective audit language, the audited organisation '
                'referred to as "the company". Keep every fact, number, document code, issue/revision and date exactly; write dates '
                'as DD.MM.YYYY and document references as "Document Title" (Code, Rev. XX, DD.MM.YYYY) using only the elements that '
                'are evidenced. Use job titles or functions instead of personal names. Do not invent evidence, results or conformity '
                'statements the evidence does not support; do not repeat the guideline questions or the Standard wording; do not '
                'write "meets / compliant with / in accordance with Clause X"; do not use "appears", "seems", "probably", "likely" '
                'or "may". Do NOT write non-conformity statements or NC references: they are added automatically after your text. '
                'No headings, bullet points, clause number at the start or markdown.'
                % (clause, title, brd.PROFILE_LABELS.get(profile, 'Global Standard')))
        if ncs:
            text += (' End with a sentence summarising how the requirements of this clause are met apart from the non-conformity '
                     'listed after the text.')
        else:
            text += (' No non-conformity was raised in this section, so end with one clause-specific conformity statement in the '
                     'style of BRCGS audit reports, based only on the evidence, e.g. "Records sampled during the audit were found to be '
                     'complete, legible, appropriately authorised where required and readily retrievable." or "The traceability system '
                     'complies with the legal requirements of the countries of sale."')
        rules = self.brcgs_skill_rules(profile)
        if rules:
            text += '\n\nReport-writing rules of the certification body (follow them):\n' + rules
        if ncs:
            text += (' After the report text, write a line containing exactly "%s" and then translate each of the %d non-conformity '
                     'statements listed at the end of the input into concise English audit wording, one per line, in the same order, '
                     'without numbering, type or clause.' % (self.BRCGS_NC_MARK, len(ncs)))
        return text

    @classmethod
    def brcgs_split_ai(cls, out, n):
        """AI ciktisi -> (rapor metni, [NC cevirileri]); isaret yoksa ya da sayi tutmazsa NC'ler bos."""
        out = (out or '').strip()
        if cls.BRCGS_NC_MARK in out:
            body, tail = out.split(cls.BRCGS_NC_MARK, 1)
            lines = [re.sub(r'^\s*(?:[-•*]|\d+[.)])\s*', '', x).strip() for x in tail.splitlines() if x.strip()]
            return body.strip(), (lines if len(lines) == n else [])
        return out, []

    def brcgs_ai_draft(self, view, row, src, ncs=()):
        """Kanitlar -> Ingilizce rapor metni; sonuc dogrudan bolumun rapor metnine yazilir (on izleme penceresi yok)."""
        from agfo_brcgs import findings as brf
        try:
            backends = self.backends()
        except Exception as e:
            messagebox.showerror('AI', str(e), parent=self)
            return
        ncs = list(ncs)
        instruction = self.brcgs_ai_prompt(view.project['profile'], row, ncs)
        if ncs:
            src = src + '\n\nNon-conformity statements to translate:\n' + '\n'.join(
                '%d. %s' % (k + 1, brf.nc_detail(it)) for k, it in enumerate(ncs))
        action = {'key': 'brcgs_draft', 'label': 'BRCGS report text', 'template': 'custom', 'extra': instruction, 'mode': 'replace',
                  'description': ''}
        options = self._ai_options()
        options.update(language='English', rich=False, from_scratch=False, preserve_facts=True, user_extra=instruction)

        def work():
            return ai.run_with_fallback(backends, 'transform', src, action, options)

        def done(ok, r):
            if not ok:
                messagebox.showerror('AI', r, parent=self)
                return
            body, nc_texts = self.brcgs_split_ai(r.get('text') or '', len(ncs))
            if not body or view not in self.brcgs_views or row not in view.project['sections']:
                return
            view.apply_ai_result(row, body, nc_texts)
            self.flash('%s: English report text written (%s)%s.' % (row['clause'], self.model_label(r),
                                                                   ' and %d NC statements translated' % len(nc_texts) if nc_texts else ''))
        self._start_job('BRCGS %s report text' % row['clause'], work, done)

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
        if doc is None and self.cur_brcgs() is not None:
            v = self.cur_brcgs()
            return v.save() if v is not self.brcgs_explorer else False
        d = doc or self.cur()
        if not d:
            return False
        if not d.path:
            return self.save_as(d)
        if d.docfile.kind == 'docx' and not d.docx_warned:
            ans = messagebox.askyesnocancel(
                'Word belgesi',
                'Yazı tipleri, biçimler, listeler, tablolar, resimler, bağlantılar, sayfa yapısı ve üst/alt bilgi metni korunur. '
                'Özgün dosyadaki dipnot, yorum, metin kutusu, bölüm (section) ve özel stil ayarları korunmaz.\n\n'
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
                    data = rdoc.docx_bytes(blocks, d.text.page if d.rich else None)
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
        if doc is None and self.cur_brcgs() is not None:
            return self.close_brcgs_view(self.cur_brcgs(), ask)
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
        if not self.nb.tabs() and ask:
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
        if frame in self.brcgs_views or frame is self.brcgs_explorer:
            self.close_brcgs_view(frame)
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
        for v in list(self.brcgs_views):
            if v.dirty and not self.close_brcgs_view(v):
                return
        for d in list(self.docs):
            if d.dirty:
                self.nb.select(d.frame)
                if not self.close_doc(d):
                    return
        self.settings.update(language=self.lang_var.get(), tone=self.tone_var.get(), audience=self.aud_var.get(),
                             length=self.len_var.get(), preserve_facts=bool(self.preserve_var.get()))
        core.save_settings(self.settings)
        self.read_aloud_stop()
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
        self._sync_zoom_label()
        self.flash('Yakınlaştırma: %%%d' % round(z * 100))

    def _autosave(self):
        for v in list(getattr(self, 'brcgs_views', {})):
            v.autosave()
        for d in self.docs:
            if d.dirty:
                try:
                    if d.rich:
                        blocks = d.text.get_blocks()
                        core.save_recovery(d.id, d.title, rdoc.blocks_to_markdown(blocks) or ' ', d.path,
                                           blocks=rdoc.blocks_to_json(blocks), page=d.text.page)
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
        r = getattr(self, '_doc_renderer', None)
        if r is not None:
            try:
                r.close()                               # arka plandaki gorunmez Word'u kapat
            except Exception:
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
                                 blocks=blocks, rich=True if blocks is not None else None,
                                 page=i.get('page') if isinstance(i.get('page'), dict) else None)
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
        m.add_command(label='Yeni  (Ctrl+N)', command=self.new_doc)
        m.add_command(label='Aç…  (Ctrl+O)', command=self.open_dialog)
        m.add_command(label='Kaydet  (Ctrl+S)', command=self.save)
        m.add_command(label='Farklı kaydet…  (Ctrl+Shift+S)', command=self.save_as)
        m.add_separator()
        m.add_command(label='BRCGS reports…', command=self.open_brcgs)
        m.add_separator()
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
        m.add_command(label='Ayarlar…', command=self.open_settings)
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
        err = self.spell_error_at(t, here) if self._spell_on() and self.speller else None
        if err:                                             # 2.0: yazim onerileri
            s0, e0, word = err
            sugg = self.speller.suggest(word) if self.speller else []
            for w_ in sugg[:7]:
                m.add_command(label=w_, font=('Segoe UI', 9, 'bold'), command=lambda x=w_: self.spell_replace(d, s0, e0, x))
            if not sugg:
                m.add_command(label='(öneri yok)', state='disabled')
            m.add_command(label='Sözlüğe ekle: “%s”' % word, command=lambda: self.spell_add(d, word))
            m.add_command(label='Tümünü yoksay', command=lambda: self.spell_ignore(d, word))
            m.add_separator()
        url = t.link_at(here) if t.rich else None
        if url:
            m.add_command(label='Bağlantıyı aç: %s' % (url if len(url) < 60 else url[:57] + '…'), command=lambda: self.open_link(url))
            m.add_command(label='Bağlantıyı düzenle…', command=lambda: (t.mark_set('insert', here), self.insert_link()))
            m.add_command(label='Bağlantıyı kaldır', command=lambda: (t.mark_set('insert', here), t.remove_link(here)))
            m.add_separator()
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
        if t.rich:
            m.add_command(label='Bağlantı…  (Ctrl+K)', command=self.insert_link)
            m.add_command(label='Paragraf…', command=self.paragraph_dialog)
            m.add_command(label='Biçimi temizle', command=lambda: self._fmt('clear'))
        m.add_separator()
        for key in ('content_strengthen', 'content_flow', 'proofread', 'shorten', 'expand', 'critique'):
            a = core.action_by_key(key)
            m.add_command(label='AI: ' + a['label'], command=lambda k=key: self.run_action_key(k))
        m.add_command(label='AI: Çevir (%s)' % self.tr_lang.get(), command=self.run_translate)
        try:
            picked = t.get('sel.first', 'sel.last').strip()
        except tk.TclError:
            picked = ''
        if picked and len(picked) <= 80 and '\n' not in picked:
            m.add_separator()
            m.add_command(label='Telaffuz sözlüğüne ekle: “%s”…' % picked, command=lambda w=picked: self.open_lexicon(word=w))
        m.tk_popup(e.x_root, e.y_root)

    def _image_menu(self, m, t, name):
        blk = t.images.get(name) or {}
        sz = tk.Menu(m, tearoff=0)
        cw = t.content_w_pt()
        for label, w in (('%25', cw * 0.25), ('%50', cw * 0.5), ('%75', cw * 0.75), ('Sayfa genişliği', cw)):
            sz.add_command(label=label, command=lambda ww=w: t.resize_image(name, ww))
        if blk:
            sz.add_command(label='Özgün boyut', command=lambda: t.resize_image(name, min(cw, rdoc.image_block(blk['data'])['w'])))
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
        b('<F9>', lambda e: (self.read_aloud(), 'break')[1])     # 1.6: sesli oku / duraklat
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
        sp_prog = getattr(self, '_sp_progress', None)
        if sp_prog and self.jobs:
            self.ai_var.set('Seslendirme: ' + sp_prog)
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
            for kind, keys, res in batch:
                live.event(kind, keys, res)

    def cancel_jobs(self):
        live = getattr(self, '_tr_live', None)
        if live:
            live.finish(800)
            self._tr_live = None
        if getattr(self, '_tr_cancel', None):
            self._tr_cancel.set()
        if getattr(self, '_sp_cancel', None):
            self._sp_cancel.set()
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
        opts['language'] = self.tr_lang.get() or 'Türkçe'
        opts['user_extra'] = self.tr_extra.get('1.0', 'end-1c').strip()
        opts['from_scratch'] = False
        opts['model_choice'] = self.translation_choice()
        action = {'key': 'translate', 'label': 'Çeviri → %s' % opts['language'], 'template': 'translate_polish',
                  'extra': 'Translate into %s.' % opts['language'], 'mode': 'replace', 'description': ''}
        self.run_action(action, opts, translate_mode=self.tr_mode.get())

    # ------------------------------------------------------------------ belge cevirisi (1.4)
    def translate_document(self):
        lang = (self.tr_lang.get() or 'Türkçe').strip()
        out = self.doc_tr_out.get() if hasattr(self, 'doc_tr_out') else 'both'
        self.settings['doc_translate_output'] = out
        v, d = self.cur_pdf(), self.cur()
        if not v and not d:
            return
        extra = self.tr_extra.get('1.0', 'end-1c').strip()
        backends = self.backends()
        layouts = None
        live = live_doc = None
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
            path = None
            if not any(b['t'] == 'p' and rdoc.runs_text(b['runs']).strip() or b['t'] == 'table' for b in blocks):
                messagebox.showinfo('Belge çevirisi', 'Çevrilecek metin yok.', parent=self)
                return
            live = trlive.TranslationLive(self, text=d.text, lines=lines)
            if out in ('newtab', 'both', 'pdf'):
                live_doc, live = self._live_translation_tab(title, lang, blocks) or (None, live)
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
                                                  on_event=lambda kind, keys, got: events.append((kind, keys, got)))
            except InterruptedError as e:
                raise ai.AIError(str(e))
            return src, new, stats

        def done(ok, res):
            self._tr_progress = None
            self._drain_tr_events()
            if live:
                live.finish()
            self._tr_live = None
            alive = live_doc is not None and live_doc in self.docs
            if alive:
                live_doc.text.configure(state='normal')
            if not ok:
                if alive:
                    live_doc.text.undo.reset()
                    live_doc.text.undo.saved = -1
                    self._doc_changed(live_doc)
                    res = '%s\n\nŞimdiye kadar çevrilen bölümler "%s" sekmesinde duruyor.' % (res, live_doc.title)
                messagebox.showerror('Belge çevirisi', res, parent=self)
                return
            src, new, stats = res
            used = ', '.join(models) or 'bilinmeyen model'
            self.last_translation_models = list(models)
            extra_note = ''
            if layouts is not None:
                src, new, extra_note = self._pdf_translation_outputs(v, layouts, new, title, lang, out, used)
            else:
                if alive:                                   # 2.1: canli sekme zaten cevrildi; farkliysa son haline getirilir
                    if live_doc.text.get_blocks() != new:
                        live_doc.text.load_blocks(new)
                    live_doc.text.undo.reset()
                    live_doc.text.undo.saved = -1
                    self._doc_changed(live_doc)
                elif out in ('newtab', 'both', 'pdf'):
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

    def _live_translation_tab(self, title, lang, blocks):
        """2.1: ceviri sekmesi hemen acilir (ozgun metnin kopyasi); her parca cevrilince yerine yazilir.
        Ozgun belge degismez. Sekme ceviri bitene kadar salt okunurdur. Esleme kurulamazsa None (eski davranis)."""
        import copy
        doc = self.new_doc(title='%s (%s)' % (title, lang), blocks=copy.deepcopy(blocks), rich=True)
        t = doc.text
        lines = []
        got = t.get_blocks(lines=lines)
        if len(got) != len(blocks) or any(g['t'] != b['t'] for g, b in zip(got, blocks)):
            self.close_doc(doc, ask=False)
            return None

        def apply(key, md):
            rng = lines[key[0]] if key[0] < len(lines) else None
            if not rng:
                return
            runs = rdoc.md_inline(md)
            t.configure(state='normal')
            rec = t.undo.recording
            t.undo.recording = False
            try:
                if len(key) == 1:
                    t.replace_line_runs(rng[0], runs)
                else:
                    t.replace_line_runs(rng[0] + key[1], runs, cell=key[2])
            finally:
                t.undo.recording = rec
                t.configure(state='disabled')
        t.configure(state='disabled')
        self.flash('Çeviri bu sekmede parça parça beliriyor; özgün belge değişmez.', 9000)
        return doc, trlive.TranslationLive(self, text=t, lines=lines, apply=apply)

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
        if not self.nb.tabs():
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
            dv.tag_configure('delete', foreground=BAD_C, overstrike=True, background=DEL_BG)
            dv.tag_configure('insert', foreground=INS_FG, background=NEW_BG)
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
                self._sync_speech_tab()
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
            if not self.update_btn.winfo_manager():
                # 2.2.0: baslik cubugunda once yerlestirilen once yer alir; dar pencerede kirpilan son dugme olmasin
                first = next((w_ for w_ in self.update_btn.master.pack_slaves() if w_ is not self.update_btn), None)
                self.update_btn.pack(side='right', padx=(0, 8), **({'before': first} if first is not None else {}))
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
                           relief='solid', highlightbackground=LINE)
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
