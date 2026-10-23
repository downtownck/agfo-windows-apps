# -*- coding: utf-8 -*-
"""AI Editor 2.0: Word bicimlendirme (yazi tipi, boyut, ustu cizili, ust/alt simge, vurgu, baglanti, aralik, girinti),
sayfa yapisi + ust/alt bilgi + sayfa numarasi (DOCX), serit arayuzu, bicim boyacisi, yazim denetimi, tema."""
import os
import pathlib
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
TMP = tempfile.mkdtemp(prefix='agfo-editor-v2-')

import agfo_richdoc as R  # noqa: E402
import agfo_spell as SP  # noqa: E402


def rich_blocks():
    return [
        R.para([R.run('Merhaba ', b=True, font='Georgia', size=16), R.run('dünya', s=True, hl='FFFF00'), R.run('2', va='sup'),
                R.run(' H'), R.run('2', va='sub'), R.run('O'),
                R.run(' site', u=True, color='0563C1', href='https://agfo.app/a?b=1&c=2')],
               align='justify', ls=1.5, sb=6, sa=0, ind=36, fi=-18),
        R.para(text='İkinci başlık', style='h2'),
        R.para([R.run('İlk satır girintili ', size=10.5)], fi=28.3),
        {'t': 'table', 'rows': [[[R.run('a')], [R.run('b', hl='ABCDEF', font='Consolas')]]]},
    ]


PAGE = {'size': 'Letter', 'orient': 'landscape', 'margins': {'t': 50, 'b': 60, 'l': 40, 'r': 30},
        'header': 'AGFO · Denetim raporu', 'footer': 'Gizli', 'pnum': {'pos': 'footer', 'align': 'right', 'fmt': 'n_of_N'}}


class ModelTests(unittest.TestCase):
    def test_docx_roundtrip_character_and_paragraph_formatting(self):
        path = os.path.join(TMP, 'v2.docx')
        with open(path, 'wb') as fh:
            fh.write(R.docx_bytes(rich_blocks(), PAGE))
        back = R.read_docx_blocks(path)
        want = rich_blocks()
        self.assertEqual(back[0]['runs'], R.merge_runs(want[0]['runs']))
        for k in R.PARA_EXTRA:
            self.assertEqual(back[0].get(k), want[0].get(k), k)
        self.assertEqual(back[1]['style'], 'h2')
        self.assertEqual(back[2]['runs'][0]['size'], 10.5)
        self.assertEqual(back[2]['fi'], 28.3)
        self.assertEqual(back[3]['rows'][0][1][0]['hl'], 'ABCDEF')
        self.assertEqual(back[3]['rows'][0][1][0]['font'], 'Consolas')

    def test_docx_page_setup_header_footer_and_page_number(self):
        path = os.path.join(TMP, 'v2-page.docx')
        with open(path, 'wb') as fh:
            fh.write(R.docx_bytes([R.para(text='x')], PAGE))
        self.assertEqual(R.read_docx_page(path), R.normalize_page(PAGE))
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            doc = z.read('word/document.xml').decode()
            ftr = z.read('word/footer1.xml').decode()
            ct = z.read('[Content_Types].xml').decode()
            rels = z.read('word/_rels/document.xml.rels').decode()
        self.assertIn('word/header1.xml', names)
        self.assertIn('w:orient="landscape"', doc)
        self.assertIn('<w:pgSz w:w="15840" w:h="12240"', doc)          # Letter yatay, twip
        self.assertIn('w:top="1000"', doc)
        self.assertIn(' PAGE ', ftr)
        self.assertIn(' NUMPAGES ', ftr)
        self.assertIn('wordprocessingml.footer+xml', ct)
        self.assertIn('relationships/footer', rels)
        z = zipfile.ZipFile(__import__('io').BytesIO(R.docx_bytes(rich_blocks())))
        rels = z.read('word/_rels/document.xml.rels').decode()
        self.assertIn('TargetMode="External"', rels)
        self.assertIn('a?b=1&amp;c=2', rels)                              # baglanti adresi XML kacisli

    def test_default_page_and_old_call_signature(self):
        data = R.docx_bytes([R.para(text='x')])                          # 1.x cagrisi: A4, normal kenarlar
        path = os.path.join(TMP, 'v2-default.docx')
        with open(path, 'wb') as fh:
            fh.write(data)
        self.assertEqual(R.read_docx_page(path), R.normalize_page(None))
        with zipfile.ZipFile(path) as z:
            self.assertNotIn('word/header1.xml', z.namelist())

    def test_normalize_page_rejects_bad_values(self):
        p = R.normalize_page({'size': 'X', 'orient': 'diag', 'margins': {'t': 'abc', 'l': -5, 'r': 9999}, 'pnum': {'pos': 'side'}})
        self.assertEqual(p['size'], 'A4')
        self.assertEqual(p['orient'], 'portrait')
        self.assertEqual(p['margins']['t'], 70.9)
        self.assertEqual(p['margins']['l'], 0.0)
        self.assertEqual(p['margins']['r'], 300.0)
        self.assertIsNone(p['pnum'])

    def test_markdown_strike_and_links(self):
        md = R.blocks_to_markdown([R.para([R.run('eski', s=True), R.run(' '), R.run('AGFO', href='https://agfo.app', u=True)])])
        self.assertEqual(md, '~~eski~~ [AGFO](https://agfo.app)')
        runs = R.markdown_to_blocks(md)[0]['runs']
        self.assertTrue(runs[0]['s'])
        self.assertEqual(runs[-1]['href'], 'https://agfo.app')
        # dengesiz ~~ ve adres olmayan koseli parantez duz metin kalir
        self.assertEqual(R.runs_text(R.md_inline('a ~~ b')), 'a ~~ b')
        self.assertEqual(R.runs_text(R.md_inline('[not](link)')), '[not](link)')

    def test_html_output_carries_new_formatting(self):
        h = R.blocks_to_html(rich_blocks())
        for frag in ("font-family:'Georgia'", 'font-size:16pt', 'background:#FFFF00', '<s>', '<sup>2</sup>', '<sub>2</sub>',
                     'href="https://agfo.app/a?b=1&amp;c=2"', 'line-height', 'text-indent:-18pt', 'margin-left:36pt'):
            self.assertIn(frag, h)

    def test_has_formatting_sees_new_properties(self):
        self.assertTrue(R.has_formatting([R.para([R.run('x', hl='FFFF00')])]))
        self.assertTrue(R.has_formatting([R.para([R.run('x')], ls=2.0)]))
        self.assertFalse(R.has_formatting([R.para([R.run('x')])]))


class SpellModuleTests(unittest.TestCase):
    def test_utf16_offsets(self):
        conv = SP.utf16_map('a😀bc')
        self.assertEqual(conv(0), 0)
        self.assertEqual(conv(3), 2)                                     # emoji 2 UTF-16 birimi
        self.assertEqual(SP.utf16_map('çğış')(3), 3)

    def test_list_speller(self):
        sp = SP.ListSpeller(['gıda', 'güvenliği'], {'kültürüu': ['kültürü']})
        self.assertEqual(sp.check('Gıda güvenliği kültürüu'), [(15, 8, 'suggest', '')])
        self.assertEqual(sp.suggest('kültürüu'), ['kültürü'])
        sp.ignore('kültürüu')
        self.assertEqual(sp.check('kültürüu'), [])

    @unittest.skipUnless(sys.platform == 'win32', 'Windows yazim denetimi API')
    def test_windows_spell_api(self):
        sp = SP.WinSpeller('en-US')
        if not sp.available:                                              # sunucu Windows'unda dil bileseni olmayabilir
            self.skipTest(sp.error)
        errs = sp.check('This is a smple sentence.')
        self.assertTrue(any(e[0] == 10 and e[1] == 5 for e in errs), errs)
        self.assertIn('simple', [w.lower() for w in sp.suggest('smple')])
        tr = SP.WinSpeller('tr-TR')
        self.assertTrue(tr.available or 'dil' in tr.error.lower())


try:
    import tkinter as tk
    import agfo_richtext as RT
    HAVE_TK = bool(os.environ.get('DISPLAY')) or sys.platform == 'win32'
except Exception:  # pragma: no cover
    HAVE_TK = False

COLORS = {'EDIT_BG': '#0e1b2e', 'FG': '#ecf3ff', 'ACCENT': '#49b3ef', 'SEL_BG': '#285475', 'MUTED': '#a5b6ce', 'BG': '#0a1425',
          'PANEL': '#12243b', 'PANEL2': '#192e48'}


@unittest.skipUnless(HAVE_TK, 'ekran yok')
class RichTextV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.t = RT.RichText(self.root, COLORS)
        self.t.pack()

    def tearDown(self):
        self.t.destroy()

    def test_load_get_roundtrip_with_new_formatting(self):
        t = self.t
        t.load_blocks(rich_blocks())
        got = t.get_blocks()
        want = rich_blocks()
        self.assertEqual(got[0]['runs'], R.merge_runs(want[0]['runs']))
        self.assertEqual({k: got[0].get(k) for k in R.PARA_EXTRA}, {k: want[0].get(k) for k in R.PARA_EXTRA})
        self.assertEqual(got[3]['rows'][0][1][0]['font'], 'Consolas')
        t.set_page_mode(True)
        t.set_font(zoom=1.4)
        self.assertEqual(t.get_blocks()[0]['runs'], got[0]['runs'])        # gorunum degisimi icerigi bozmaz

    def test_value_formats_and_undo(self):
        t = self.t
        t.load_blocks([R.para(text='ikinci satır')])
        t.tag_add('sel', '1.0', '1.6')
        t.toggle_char('font', 'Courier New')
        t.toggle_char('size', 20)
        t.toggle_char('hl', '00FF00')
        t.toggle_char('sup')
        r = t.get_blocks()[0]['runs'][0]
        self.assertEqual((r['font'], r['size'], r['hl'], r['va']), ('Courier New', 20, '00FF00', 'sup'))
        t.toggle_char('sub')                                              # ust simge -> alt simge
        self.assertEqual(t.get_blocks()[0]['runs'][0]['va'], 'sub')
        t.toggle_char('s')
        self.assertTrue(t.get_blocks()[0]['runs'][0]['s'])
        for _ in range(2):                                                # ustu cizili, alt simge geri alinir
            t.edit_undo()
        self.assertEqual(t.get_blocks()[0]['runs'][0].get('va'), 'sup')
        self.assertNotIn('s', t.get_blocks()[0]['runs'][0])
        for _ in range(4):
            t.edit_undo()
        self.assertEqual(t.get_blocks()[0]['runs'], [R.run('ikinci satır')])

    def test_typing_formats_without_selection(self):
        t = self.t
        t.load_blocks([R.para(text='ab')])
        t.mark_set('insert', '1.2')
        t.toggle_char('size', 18)
        t.toggle_char('font', 'Georgia')
        t._type_text('X')
        runs = t.get_blocks()[0]['runs']
        self.assertEqual(runs[-1], R.run('X', font='Georgia', size=18))

    def test_painter_clear_and_paragraph_extras(self):
        t = self.t
        t.load_blocks([R.para([R.run('kaynak', b=True, font='Georgia', size=14)], align='center', ls=2.0, sa=12),
                       R.para(text='hedef paragraf')])
        t.mark_set('insert', '1.2')
        fmt = t.copy_format()
        t.tag_add('sel', '2.0', '2.end')
        self.assertTrue(t.apply_format(fmt))
        b = t.get_blocks()[1]
        self.assertEqual(b['runs'], [R.run('hedef paragraf', b=True, font='Georgia', size=14)])
        self.assertEqual((b['align'], b['ls'], b['sa']), ('center', 2.0, 12))
        t.clear_formatting()
        b = t.get_blocks()[1]
        self.assertEqual(b, R.para(text='hedef paragraf'))
        t.edit_undo()
        self.assertEqual(t.get_blocks()[1]['align'], 'center')

    def test_indent_steps_and_list_levels(self):
        t = self.t
        t.load_blocks([R.para(text='düz'), R.para(text='madde', lst='bullet')])
        t.mark_set('insert', '1.1')
        t.indent(1)
        t.indent(1)
        self.assertEqual(t.get_blocks()[0]['ind'], 72)
        t.indent(-1)
        self.assertEqual(t.get_blocks()[0]['ind'], 36)
        t.indent(-1)
        self.assertNotIn('ind', t.get_blocks()[0])
        t.mark_set('insert', '2.3')
        t.indent(1)
        self.assertEqual(t.get_blocks()[1]['level'], 1)                  # listede duzey

    def test_links_and_page_break(self):
        t = self.t
        opened = []
        t.on_link = opened.append
        t.load_blocks([R.para(text='bağlantı burada')])
        t.tag_add('sel', '1.0', '1.8')
        t.insert_link('agfo.app')
        r = t.get_blocks()[0]['runs'][0]
        self.assertEqual((r['text'], r['href'], r['u']), ('bağlantı', 'https://agfo.app', True))
        self.assertEqual(t.link_at('1.3'), 'https://agfo.app')
        t.tag_remove('sel', '1.0', 'end')
        t.mark_set('insert', '1.3')
        self.assertTrue(t.remove_link())
        self.assertEqual(t.get_blocks()[0]['runs'], [R.run('bağlantı burada')])
        t.mark_set('insert', '1.9')
        t.insert_page_break()
        b = t.get_blocks()
        self.assertEqual([R.runs_text(x['runs']) for x in b], ['bağlantı ', 'burada'])
        self.assertTrue(b[1]['pb'])
        t.edit_undo()
        self.assertEqual(len(t.get_blocks()), 1)

    def test_page_setup_changes_widths(self):
        t = self.t
        w0 = t.content_w_pt()
        t.set_page_setup({'orient': 'landscape'})
        self.assertGreater(t.content_w_pt(), w0 + 200)
        self.assertEqual(t.page['orient'], 'landscape')


def _display_available():
    return sys.platform == 'win32' or bool(os.environ.get('DISPLAY'))


@unittest.skipUnless(_display_available(), 'ekran yok (xvfb-run ile calistirin)')
class GuiV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.machinery
        import importlib.util
        loader = importlib.machinery.SourceFileLoader('agfo_ai_editor_v2', str(SRC / 'agfo_ai_editor.pyw'))
        spec = importlib.util.spec_from_loader('agfo_ai_editor_v2', loader)
        cls.m = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.m)

    def setUp(self):
        self.app = self.m.App(smoke=True)
        self.app.withdraw()
        self.app.update()

    def tearDown(self):
        for w in list(self.app.winfo_children()):
            if isinstance(w, self.m.tk.Toplevel):
                w.destroy()
        self.app.destroy()

    def test_ribbon_tabs_and_no_wordcraft(self):
        app = self.app
        self.assertEqual(set(app.ribbon_pages), {'home', 'insert', 'layout', 'view', 'ai'})
        for key in ('layout', 'insert', 'home'):
            app.select_ribbon(key, save=False)
            app.update()
            self.assertTrue(app.ribbon_pages[key].winfo_manager())
            self.assertEqual(sum(1 for p in app.ribbon_pages.values() if p.winfo_manager()), 1)
        for key in ('b', 'i', 'u', 's', 'sup', 'sub', 'hl', 'color', 'clear', 'bullet', 'number', 'justify', 'table', 'image', 'link',
                    'pagebreak', 'pnum', 'margins', 'orient', 'psize', 'painter'):
            self.assertIn(key, app.fmt_btns)
        self.assertFalse(hasattr(app, 'wc_target'))
        self.assertFalse(any('wordcraft' in n.lower() for n in dir(app)))
        self.assertTrue(app.update_btn)                                   # 1.4.15 guncelleme dugmesi duruyor
        self.assertEqual(app.ai_nb.index('end'), 6)                       # Icerik, Ceviri, Sohbet, Denetim, Kaynaklar, Ses

    def test_ribbon_formatting_commands_and_docx_save(self):
        app = self.app
        d = app.cur()
        t = d.text
        t.load_blocks([R.para(text='Başlık metni'), R.para(text='gövde metni burada')])
        t.tag_add('sel', '2.0', '2.5')
        app.font_var.set('Georgia')
        app._fmt('font', 'Georgia')
        app._fmt('size', '14,5')
        app._fmt('hl', 'FFFF00')
        app._fmt('s')
        app._fmt('grow', 1)
        r = t.get_blocks()[1]['runs'][0]
        self.assertEqual((r['font'], r['size'], r['hl'], r['s']), ('Georgia', 16, 'FFFF00', True))
        t.tag_remove('sel', '1.0', 'end')
        t.mark_set('insert', '1.2')
        app._fmt('style', 'h1')
        app._fmt('align', 'justify')
        app._fmt('spacing', {'ls': 1.5, 'sb': 12})
        app._sync_fmt_bar()
        self.assertEqual(app.style_var.get(), R.STYLE_LABELS['h1'])
        self.assertTrue(app.fmt_btns['justify']._on)
        app.set_page(orient='landscape', margins={'t': 36, 'b': 36, 'l': 36, 'r': 36})
        self.assertTrue(d.dirty)
        self.assertIn('Yatay', app.page_info.cget('text'))
        win = app.header_footer_dialog()
        boxes = [w for w in win.winfo_children() if isinstance(w, self.m.tk.Text)]
        boxes[0].insert('1.0', 'Üst metin')
        win.ok()
        self.assertEqual(t.page['header'], 'Üst metin')
        app._fmt('pagebreak')
        out = os.path.join(TMP, 'gui-v2.docx')
        with mock.patch.object(self.m.filedialog, 'asksaveasfilename', return_value=out):
            self.assertTrue(app.save_as(d))
        back = R.read_docx_blocks(out)
        self.assertEqual(back[0]['style'], 'h1')
        self.assertEqual(back[0]['ls'], 1.5)
        self.assertEqual(back[0]['align'], 'justify')
        self.assertTrue(back[1]['pb'])                                    # imlecte sayfa sonu
        self.assertEqual(back[2]['runs'][0]['font'], 'Georgia')
        pg = R.read_docx_page(out)
        self.assertEqual((pg['orient'], pg['header'], pg['margins']['l']), ('landscape', 'Üst metin', 36.0))
        # yeniden acinca sayfa yapisi geri gelir
        app.close_doc(d, ask=False)
        d2 = app.open_path(out)
        self.assertEqual(d2.text.page['orient'], 'landscape')
        self.assertEqual(d2.text.page['header'], 'Üst metin')

    def test_paragraph_and_link_dialogs(self):
        app = self.app
        t = app.cur().text
        t.load_blocks([R.para(text='paragraf metni')])
        t.mark_set('insert', '1.3')
        win = app.paragraph_dialog()
        spins = [w for w in win.winfo_children() if isinstance(w, self.m.ttk.Spinbox)]
        spins[0].delete(0, 'end')
        spins[0].insert(0, '1,27')                                        # sol girinti cm
        win.ok()
        self.assertAlmostEqual(t.get_blocks()[0]['ind'], 36.0, places=0)
        t.tag_add('sel', '1.0', '1.8')
        win = app.insert_link()
        ents = [w for w in win.winfo_children() if isinstance(w, self.m.ttk.Entry)]
        ents[-1].insert(0, 'https://agfocert.com')
        win.ok()
        self.assertEqual(t.get_blocks()[0]['runs'][0]['href'], 'https://agfocert.com')

    def test_format_painter_flow(self):
        app = self.app
        d = app.cur()
        t = d.text
        t.load_blocks([R.para([R.run('kaynak', b=True, color='C00000')]), R.para(text='hedef')])
        t.mark_set('insert', '1.2')
        app.format_painter()
        self.assertTrue(app.fmt_btns['painter']._on)
        t.tag_add('sel', '2.0', '2.end')
        app._painter_release(d)
        self.assertEqual(t.get_blocks()[1]['runs'], [R.run('hedef', b=True, color='C00000')])
        self.assertIsNone(app._painter)
        self.assertFalse(app.fmt_btns['painter']._on)

    def test_spellcheck_marks_suggests_and_replaces(self):
        app = self.app
        d = app.cur()
        t = d.text
        app.speller = SP.ListSpeller(['gıda', 'güvenliği', 'kültürü', 'önemlidir'], {'kültürüu': ['kültürü']})
        app.settings['spellcheck'] = True
        t.load_blocks([R.para(text='Gıda güvenliği kültürüu önemlidir'), R.para(text='• yok', lst='bullet')])
        app.spell_full(d)
        self.assertTrue(self._pump(lambda: t.tag_ranges('spell')))
        self.assertEqual(t.get(*t.tag_ranges('spell')[:2]), 'kültürüu')
        err = app.spell_error_at(t, '1.18')
        self.assertEqual(err[2], 'kültürüu')
        app.spell_replace(d, err[0], err[1], 'kültürü')
        self.assertEqual(R.runs_text(t.get_blocks()[0]['runs']), 'Gıda güvenliği kültürü önemlidir')
        self.assertFalse(t.tag_ranges('spell') and t.compare(t.tag_ranges('spell')[0], '<', '2.0'))
        self.assertNotIn('spell', [str(x) for x in t.tag_names('2.0')])  # 'spell' kayda/undo'ya girmez
        t.edit_undo()
        self.assertIn('kültürüu', R.runs_text(t.get_blocks()[0]['runs']))
        app.settings['spellcheck'] = True
        app.toggle_spell()                                                # kapat
        self.assertFalse(t.tag_ranges('spell'))

    def _pump(self, until, n=200):
        import time
        for _ in range(n):
            self.app.update()
            if until():
                return True
            time.sleep(0.01)
        return False

    def test_theme_restart_starts_clean_process(self):
        """2.0.1: yeniden baslatilan surec PyInstaller ortamini (_MEI klasoru) devralmamali."""
        calls = []
        with mock.patch.dict(os.environ, {'_PYI_APPLICATION_HOME_DIR': r'C:\\Temp\\_MEI1', '_MEIPASS2': 'x'}), \
                mock.patch.object(self.m.subprocess, 'Popen', lambda *a, **k: calls.append((a, k))):
            self.app.restart()
        self.assertEqual(len(calls), 1)
        env = calls[0][1]['env']
        self.assertNotIn('_PYI_APPLICATION_HOME_DIR', env)
        self.assertNotIn('_MEIPASS2', env)
        self.assertEqual(env['PYINSTALLER_RESET_ENVIRONMENT'], '1')
        self.app = self.m.App(smoke=True)                                 # tearDown icin yeni pencere
        self.app.withdraw()

    def test_theme_palettes(self):
        m = self.m
        self.assertEqual(set(m.THEMES['dark']), set(m.THEMES['light']))
        try:
            m.apply_theme('light')
            self.assertEqual(m.PANEL, '#ffffff')
            self.assertEqual(m.rtext.PAGE_COLORS['desk'], m.THEMES['light']['DESK'])
        finally:
            m.apply_theme('dark')
        self.assertEqual(m.apply_theme('unknown'), 'dark')
        with mock.patch.object(self.m.messagebox, 'askyesno', return_value=False), mock.patch.object(self.m.core, 'save_settings'):
            self.app.set_theme('light')
        self.assertEqual(self.app.settings['ui_theme'], 'light')


if __name__ == '__main__':
    unittest.main()
