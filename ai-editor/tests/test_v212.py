"""2.12.0: sayfa gorunumunde gercek sayfalar, metin islemleri, sag tik menuleri."""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import time
import tkinter as tk
import unittest
from unittest import mock

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
TMP = tempfile.mkdtemp(prefix='agfo-212-')
os.environ['LOCALAPPDATA'] = TMP

import agfo_pages as PG  # noqa: E402
import agfo_textops as TO  # noqa: E402


class PlanTests(unittest.TestCase):
    def test_plan_pages(self):
        starts, used = PG.plan_pages([300, 300, 300, 300], 700)
        self.assertEqual(starts, [2])
        self.assertEqual(used, [600, 600])
        starts, used = PG.plan_pages([100, 100, 100], 700, breaks=[1])       # elle sayfa sonu
        self.assertEqual(starts, [1])
        starts, _ = PG.plan_pages([1500, 100], 700)                           # sayfadan uzun paragraf bolunmez
        self.assertEqual(starts, [])
        self.assertEqual(PG.plan_pages([], 700), ([], [0.0]))


class TextOpsPureTests(unittest.TestCase):
    def test_turkish_case(self):
        self.assertEqual(TO.tr_upper('istanbul ılık'), 'İSTANBUL ILIK')
        self.assertEqual(TO.tr_lower('İSTANBUL ILIK'), 'istanbul ılık')
        self.assertEqual(TO.title_case('alerjen yönetimi ve hat temizliği'), 'Alerjen Yönetimi ve Hat Temizliği')
        self.assertEqual(TO.title_case('iç denetim'), 'İç Denetim')
        self.assertEqual(TO.sentence_case('BU BİR CÜMLE. İKİNCİSİ!'), 'Bu bir cümle. İkincisi!')
        self.assertEqual(TO.toggle_case('aB'), 'Ab')
        for _k, (_l, fn) in TO.CASE_OPS.items():
            self.assertEqual(len(fn('Straße İi')), len('Straße İi'))

    def test_turkish_sort_and_lines(self):
        lines = ['şeker', 'Çay', 'su', 'cam', 'ılık', 'ışık', 'iç', 'zeytin', 'öğle', 'ot', 'madde 10', 'madde 2']
        order = TO.order_lines(lines, 'sort_az')
        self.assertEqual([lines[k] for k in order],
                         ['cam', 'Çay', 'ılık', 'ışık', 'iç', 'madde 2', 'madde 10', 'ot', 'öğle', 'su', 'şeker', 'zeytin'])
        self.assertEqual(TO.order_lines(['a', 'b', 'a ', '', 'b'], 'dedupe'), [0, 1, 3])
        self.assertEqual(TO.order_lines(['a', '', 'b', '  '], 'drop_empty'), [0, 2])
        self.assertEqual(TO.order_lines(['a', 'b'], 'reverse'), [1, 0])

    def test_text_transforms(self):
        self.assertEqual(TO.squeeze_spaces('a   b \t\nc  '), 'a b\nc')
        self.assertEqual(TO.join_wrapped('Bu bir uzun cüm-\nle ve\ndevamı.\n\n- madde\n- ikinci'),
                         'Bu bir uzun cümle ve devamı.\n\n- madde\n- ikinci')
        self.assertEqual(TO.smart_quotes('"Evet" dedi \'tamam\''), '“Evet” dedi ‘tamam’')
        self.assertEqual(TO.straight_quotes('“Evet”'), '"Evet"')
        self.assertEqual(TO.number_lines('elma\n- armut\n\nkiraz'), '1. elma\n2. armut\n\n3. kiraz')
        self.assertEqual(TO.strip_markers('1. elma\n- armut'), 'elma\narmut')
        st = TO.stats('Bir iki üç. Dört beş!\n\nAltı.')
        self.assertEqual((st['words'], st['sentences'], st['paragraphs']), (6, 3, 2))


def _display():
    return sys.platform == 'win32' or bool(os.environ.get('DISPLAY'))


@unittest.skipUnless(_display(), 'ekran gerekli')
class GuiTests(unittest.TestCase):
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
        self.app.geometry('1400x900')
        self.app.update()
        self.app.settings['page_view'] = True

    def tearDown(self):
        self.app.destroy()

    def pump(self, until=lambda: False, n=200):
        for _ in range(n):
            self.app.update()
            if until():
                return True
            time.sleep(0.01)
        return False

    def long_doc(self, n=30):
        body = '\n\n'.join('## %d. Bölüm\n\nAlerjen yönetimi, çapraz bulaşma ve hat temizliği konularında prosedür '
                           'gereklilikleri burada açıklanır; her bölüm birkaç satır sürer ve sayfa dolunca sonraki sayfaya '
                           'geçilir.' % i for i in range(1, n + 1))
        return self.app.new_doc(text='# Deneme\n\n' + body, title='Uzun.md')

    def test_pagination(self):
        d = self.long_doc()
        self.assertTrue(self.pump(lambda: d.pages.count() > 2))
        t = d.text
        n_pages = d.pages.count()
        tags = set(t.tag_names())
        self.assertTrue(any(x.startswith('pgap_') for x in tags))
        # sayfa araliklari kayda girmez: bicimli bloklar etiketlerden etkilenmez
        blocks = t.get_blocks()
        self.assertFalse(any('pgap' in repr(b) for b in blocks))
        self.assertIn('Sayfa 1 / %d' % n_pages, self.app.status_var.get())
        # her sayfanin yuksekligi ayni (sayfa boyu oraninda)
        page_h, content_h, top, bottom, gap = d.pages.metrics()
        ys = [int(t._call('count', '-ypixels', '1.0', '%d.0' % L)) for L in d.pages.starts[:3]]
        free = d.pages.free
        prev_end = 0
        for k, y in enumerate(ys):
            self.assertLessEqual(y - prev_end, content_h + 1)                   # sayfaya sigan yazi
            prev_end = y + free[k] + bottom + gap + top
        # sayfa gorunumu kapaninca etiketler kalkar
        self.app.toggle_page_view()
        self.pump(n=10)
        self.assertFalse(any(x.startswith('pgap_') for x in t.tag_names() if t.tag_ranges(x)))
        self.app.toggle_page_view()
        self.assertTrue(self.pump(lambda: d.pages.count() == n_pages))
        # elle sayfa sonu yeni sayfa baslatir
        t.mark_set('insert', '5.0')
        t.insert_page_break()
        self.assertTrue(self.pump(lambda: d.pages.count() == n_pages + 1, n=300))

    def test_case_keeps_formatting(self):
        d = self.app.new_doc(text='normal **kalın kısım** son', title='a.md')
        t = d.text
        t.tag_add('sel', '1.0', 'end-1c')
        self.app.text_op('case', 'upper')
        self.assertEqual(t.get('1.0', 'end-1c'), 'NORMAL KALIN KISIM SON')
        idx = t.search('KALIN', '1.0')
        self.assertIn('b', t.tag_names(idx))
        self.assertNotIn('b', t.tag_names('1.0'))
        t.edit_undo()
        self.assertEqual(t.get('1.0', 'end-1c'), 'normal kalın kısım son')

    def test_sort_lines_keep_formatting(self):
        d = self.app.new_doc(text='zeytin\n\n**çay**\n\nelma', title='b.md')
        t = d.text
        before = [ln for ln in t.get('1.0', 'end-1c').split('\n') if ln]
        self.app.text_op('lines', 'sort_az')
        after = [ln for ln in t.get('1.0', 'end-1c').split('\n') if ln]
        self.assertEqual(sorted(before, key=TO.tr_key), after)
        idx = t.search('çay', '1.0')
        self.assertIn('b', t.tag_names(idx))
        self.app.text_op('lines', 'drop_empty')
        self.assertEqual(t.get('1.0', 'end-1c'), 'çay\nelma\nzeytin')

    def test_text_op_and_insert_date(self):
        d = self.app.new_doc(text='a    b', title='c.md')
        t = d.text
        t.mark_set('insert', '1.0')
        self.app.text_op('text', 'squeeze')
        self.assertEqual(t.get('1.0', 'end-1c'), 'a b')
        t.mark_set('insert', 'end')
        self.app.insert_text_at_cursor(' ' + TO.now_text('date'))
        self.assertTrue(t.get('1.0', 'end-1c').startswith('a b '))
        with mock.patch.object(self.m.messagebox, 'showinfo'):
            st = self.app.text_stats_dialog()
        self.assertEqual(st['words'], 2 + len(TO.now_text('date').split('.')))

    def _menus(self, fn, event):
        posted = []
        with mock.patch.object(tk.Menu, 'tk_popup', lambda self, x, y, entry='': posted.append(self)):
            fn(event)
        return posted

    @staticmethod
    def _labels(menu):
        out = []
        end = menu.index('end')
        for k in range(0, (end or 0) + 1):
            if menu.type(k) in ('command', 'cascade'):
                out.append(menu.entrycget(k, 'label'))
        return out

    def test_context_menus(self):
        app = self.app
        d = app.new_doc(text='Bir paragraf.', title='m.md')
        ev = mock.Mock(x=5, y=5, x_root=10, y_root=10, widget=d.text)
        menus = self._menus(app._context_menu, ev)
        labels = self._labels(menus[0])
        for want in ('Tümünü seç  (Ctrl+A)', 'Biçim', 'Metin işlemleri'):
            self.assertIn(want, labels)
        # sekme menusu
        app.update()
        x, y = 30, 10
        menus = self._menus(app._tab_context, mock.Mock(x=x, y=y, x_root=0, y_root=0))
        self.assertTrue(menus and 'Diğerlerini kapat' in self._labels(menus[0]))
        # genel giris kutusu menusu
        ent = app.find_entry
        menus = self._menus(app._generic_context, mock.Mock(widget=ent, x_root=0, y_root=0))
        self.assertTrue(menus and 'Yapıştır' in self._labels(menus[0]))
        # salt okunur yanit alani: ozel eklemeler
        menus = self._menus(app._generic_context, mock.Mock(widget=app.src_view, x_root=0, y_root=0))
        self.assertIn('Yanıtı imlece ekle', self._labels(menus[0]))
        # editorun kendisinde genel menu acilmaz (kendi menusu var)
        self.assertEqual(self._menus(app._generic_context, mock.Mock(widget=d.text, x_root=0, y_root=0)), [])
        # kaynak listesi
        menus = self._menus(app._src_tree_context, mock.Mock(y=1, x_root=0, y_root=0))
        self.assertIn('📁 Klasör ekle…', self._labels(menus[0]))

    def test_close_others(self):
        app = self.app
        a = app.new_doc(text='a', title='a.md')
        b = app.new_doc(text='b', title='b.md')
        for x in (a, b):
            x.text.undo.saved = len(x.text.undo.stack)
        tabs = [app.nametowidget(t) for t in app.nb.tabs()]
        app._close_frames([f for f in tabs if f is not b.frame])
        self.pump(n=5)
        self.assertEqual([app.nametowidget(t) for t in app.nb.tabs()], [b.frame])


if __name__ == '__main__':
    unittest.main()
