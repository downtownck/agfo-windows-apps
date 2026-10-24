"""2.6.0: iki sutunlu bolum duzenleyici, Ingilizce yazim denetimi, Word gorunumunde geri al ve gezinme."""
from __future__ import annotations

import os
import pathlib
import shutil
import sys
import tempfile
import time
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
TMP = tempfile.mkdtemp(prefix='agfo-v26-')
os.environ['LOCALAPPDATA'] = TMP

try:
    import lxml  # noqa: F401
    HAVE_LXML = True
except ImportError:  # pragma: no cover
    HAVE_LXML = False

if HAVE_LXML:
    from agfo_brcgs import boxes as B
    from agfo_brcgs import data as D
    from agfo_brcgs import store as S
    import agfo_spell
    from test_brcgs_wordview import FakeRenderer


def _display():
    return sys.platform == 'win32' or bool(os.environ.get('DISPLAY'))


@unittest.skipUnless(HAVE_LXML and _display(), 'lxml ve ekran gerekli')
class V26Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.machinery
        import importlib.util
        loader = importlib.machinery.SourceFileLoader('agfo_ai_editor', str(SRC / 'agfo_ai_editor.pyw'))
        spec = importlib.util.spec_from_loader('agfo_ai_editor', loader)
        cls.m = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.m)

    def setUp(self):
        self.app = self.m.App(smoke=True)
        self.app.geometry('1200x800')
        self.app.update()
        self.app._brcgs_store = S.Store(tempfile.mkdtemp(dir=TMP))
        self.app._doc_renderer = FakeRenderer()

    def tearDown(self):
        self.app.destroy()

    def pump(self, until=lambda: False, n=400):
        for _ in range(n):
            self.app.update()
            if until():
                return True
            time.sleep(0.01)
        return False

    def _open_ab(self):
        d = tempfile.mkdtemp(dir=TMP)
        f = os.path.join(d, 'ab.docx')
        shutil.copy(D.template_path('ab'), f)
        v = self.app.open_path(f)
        self.assertTrue(self.pump(lambda: v._word['pdf'] is not None and not v._word['busy']))
        self.assertTrue(self.pump(lambda: v.wordview is not None and v.wordview.doc is not None))
        return v

    def test_section_editor_two_columns_and_spell_check(self):
        self.app._en_speller = agfo_spell.ListSpeller(
            ['the', 'site', 'has', 'a', 'documented', 'procedure'], {'proceduer': ['procedure']})
        ex = self.app.open_brcgs()
        ex.new_report('fs')
        v = self.app.cur_brcgs()
        v.show('sections')
        self.pump(n=10)
        box = v._report_box
        self.assertIsNotNone(box)
        # rapor kutusu sag sutunda: bolum duzenleyici yatay bolunmus
        w, panes = box, None
        while w is not None:
            if w.winfo_class() == 'TPanedwindow':
                panes = w
                break
            w = w.master
        self.assertIsNotNone(panes)
        self.assertEqual(str(panes.cget('orient')), 'horizontal')
        self.assertEqual(len(panes.panes()), 2)
        box.delete('1.0', 'end')
        box.insert('1.0', 'The site has a documented proceduer')
        self.assertEqual(v.spell_check(box), 1)
        rng = box.tag_ranges('spell')
        self.assertEqual(box.get(rng[0], rng[1]), 'proceduer')
        box.delete('1.0', 'end')
        box.insert('1.0', 'The site has a documented procedure')
        self.assertEqual(v.spell_check(box), 0)
        self.assertEqual(box.tag_ranges('spell'), ())
        # yazim denetimi yoksa (ayar kapali / servis yok) sessizce atlanir
        self.app._en_speller = False
        self.assertEqual(v.spell_check(box), 0)

    def test_word_view_undo_field_and_section(self):
        v = self._open_ab()
        self.assertEqual(str(v.undo_btn.cget('state')), 'disabled')
        self.assertFalse(v.undo_last())
        fld = next(a for a in v._word['found'] if a[0][0] == 'BRC_SITE_CODE')
        before = v.project['values'].get('BRC_SITE_CODE')
        v.pick_target(fld[0])
        tgt, ed, finish = v.inline_editor
        ed.delete(0, 'end')
        ed.insert(0, '9998887')
        finish(True)
        self.pump(n=5)
        self.assertEqual(v.project['values']['BRC_SITE_CODE'], '9998887')
        self.assertEqual(str(v.undo_btn.cget('state')), 'normal')
        box = next(a for a in v._word['found'] if a[0][0] in B.detail_tags('ab') and v._target_info(a[0])[0] == 'section')
        clause = v._target_info(box[0])[1]
        row = next(r for r in v.project['sections'] if r['clause'] == clause)
        old = row.get('value')
        v.pick_target(box[0])
        tgt, ed, finish = v.inline_editor
        ed.delete('1.0', 'end')
        ed.insert('1.0', 'Typed by mistake.')
        finish(True)
        self.pump(n=5)
        self.assertEqual(row['value'], 'Typed by mistake.')
        # Ctrl+Z: son degisiklik geri, sonra bir oncekisi
        v.wordview.canvas.focus_force()
        v.wordview.canvas.event_generate('<Control-z>', when='now')
        self.pump(n=5)
        if row['value'] == 'Typed by mistake.':
            v.undo_last()                                    # tus olayi ulasmadiysa (odak yok) ayni adim
        self.assertEqual(row.get('value'), old)
        self.assertTrue(v.undo_last())
        self.assertEqual(v.project['values'].get('BRC_SITE_CODE'), before)
        self.assertEqual(str(v.undo_btn.cget('state')), 'disabled')

    def test_word_view_navigation(self):
        v = self._open_ab()
        wv = v.wordview
        n = len(wv.tops)
        self.assertGreater(n, 1)
        self.pump(n=5)
        self.assertEqual(v.page_total.cget('text'), '/ %d' % n)
        v.page_var.set(str(n))
        v._goto_page()
        self.pump(n=5)
        self.assertEqual(wv.current_page(), n - 1)
        self.assertEqual(v.page_var.get(), str(n))
        v.page_var.set('1')
        v._goto_page()
        self.assertEqual(wv.current_page(), 0)
        # bolume git: o bolumun kutusunun sayfasi
        box = next(a for a in v._word['found'] if v._target_info(a[0])[0] == 'section' and a[1] > 0)
        clause = v._target_info(box[0])[1]
        self.assertTrue(v.word_goto('clause:' + clause))
        self.assertEqual(wv.current_page(), box[1])
        # sol menu Word gorunumundeyken formu acmaz, belgede gezer
        g = next(a for a in v._word['found'] if v._target_info(a[0])[0] == 'field')
        group = v._target_info(g[0])[1][2]
        v.nav_click('overview')
        self.assertEqual(v.page, 'word')
        self.assertEqual(wv.current_page(), 0)
        v.nav_click('g:' + group)
        self.assertEqual(v.page, 'word')
        self.assertEqual(wv.current_page(), g[1])
        # belgede olmayan sayfa (inceleme) formda acilir
        v.nav_click('review')
        self.assertEqual(v.page, 'review')
        # Git listesi tum bolumleri icerir
        self.assertIn('Non-conformities', v._goto_items())
        self.assertTrue(any(i.startswith(clause + ' ') for i in v._goto_items()))


if __name__ == '__main__':
    unittest.main()
