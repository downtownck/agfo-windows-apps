"""2.11.0: kaynak belge gezgini sekmesi (klasor agaci, turler, ad / icerik aramasi, sohbet kapsami)."""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import time
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
TMP = tempfile.mkdtemp(prefix='agfo-srcx-')
os.environ['LOCALAPPDATA'] = TMP

import agfo_sources_view as SV  # noqa: E402


class PureTests(unittest.TestCase):
    def test_helpers(self):
        self.assertEqual(SV.kind_label('pdf'), 'PDF')
        self.assertEqual(SV.kind_label('docx'), 'Word')
        self.assertEqual(SV.kind_label('xyz'), 'XYZ')
        self.assertEqual(SV.doc_subfolder({'name': 'Kok/Prosedur/HACCP/plan.docx'}), 'Kok/Prosedur/HACCP')
        self.assertEqual(SV.doc_subfolder({'name': 'tek.pdf'}), '')
        doc = {'name': 'Alerjen planı.docx', 'units': [{'text': 'Gluten ve süt. GLUTEN izleme.'}]}
        txt = SV.doc_text(doc).casefold()
        self.assertEqual(SV.matches(doc, 'alerjen'), 1)
        self.assertEqual(SV.matches(doc, 'gluten', txt), 2)
        self.assertEqual(SV.matches(doc, 'gluten'), 0)           # icerikte arama kapali
        self.assertEqual(SV.matches(doc, ''), 1)


def _display():
    return sys.platform == 'win32' or bool(os.environ.get('DISPLAY'))


@unittest.skipUnless(_display(), 'ekran gerekli')
class ExplorerGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.machinery
        import importlib.util
        loader = importlib.machinery.SourceFileLoader('agfo_ai_editor', str(SRC / 'agfo_ai_editor.pyw'))
        spec = importlib.util.spec_from_loader('agfo_ai_editor', loader)
        cls.m = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.m)
        root = pathlib.Path(tempfile.mkdtemp(dir=TMP)) / 'Kalite'
        (root / 'Prosedurler' / 'HACCP').mkdir(parents=True)
        (root / 'Kayitlar').mkdir()
        (root / 'Prosedurler' / 'HACCP' / 'plan.md').write_text('# HACCP planı\n\nKritik kontrol noktası: pastörizasyon.',
                                                               encoding='utf-8')
        (root / 'Prosedurler' / 'alerjen.txt').write_text('Alerjen yönetimi: gluten, süt, fındık.', encoding='utf-8')
        (root / 'Kayitlar' / 'egitim.csv').write_text('ad;konu\nAli;gluten farkındalığı\n', encoding='utf-8')
        cls.root = str(root)
        cls.single = os.path.join(TMP, 'tek-belge.txt')
        pathlib.Path(cls.single).write_text('Tedarikçi onayı prosedürü.', encoding='utf-8')

    def setUp(self):
        self.app = self.m.App(smoke=True)
        self.app.geometry('1400x900')
        self.app.update()

    def tearDown(self):
        self.app.destroy()

    def pump(self, until=lambda: False, n=600):
        for _ in range(n):
            self.app.update()
            if until():
                return True
            time.sleep(0.01)
        return False

    def test_explorer(self):
        app = self.app
        app.add_source_folder(self.root, quiet=True)
        self.assertTrue(self.pump(lambda: len(app.src_docs) == 3))
        app._load_sources([self.single], quiet=True)
        self.assertTrue(self.pump(lambda: len(app.src_docs) == 4))
        v = app.open_sources_explorer()
        self.pump(n=10)
        self.assertIs(app.nametowidget(app.nb.select()), v)
        self.assertEqual(len(v.tv.get_children()), 4)
        side = {v.tree_side.item(i, 'text') for i in self._walk(v.tree_side)}
        self.assertTrue(any(t.startswith('📁  Kalite  (3)') for t in side), side)
        self.assertTrue(any(t.startswith('📂  Prosedurler  (2)') for t in side), side)
        self.assertTrue(any(t.startswith('📂  HACCP  (1)') for t in side), side)
        self.assertTrue(any(t.startswith('📄  Tek tek eklenenler  (1)') for t in side), side)
        # alt klasor secimi: liste suzulur, sohbet kapsami o klasorun belgeleri olur
        sub = next(i for i in self._walk(v.tree_side) if v.tree_side.item(i, 'text').startswith('📂  Prosedurler'))
        v.tree_side.selection_set(sub)
        self.pump(n=10)
        self.assertEqual(len(v.tv.get_children()), 2)
        self.assertEqual(len(app._scope_ids()), 2)
        # tur suzgeci
        kind = next(i for i in self._walk(v.tree_side) if v.tree_side.item(i, 'text').startswith('CSV'))
        v.tree_side.selection_set(kind)
        self.pump(n=10)
        self.assertEqual([v.tv.set(i, 'name') for i in v.tv.get_children()], ['egitim.csv'])
        # arama: ad ve icerik
        v.tree_side.selection_set('all')
        self.pump(n=10)
        v.q.set('gluten')
        v.refresh_list()
        names = sorted(v.tv.set(i, 'name') for i in v.tv.get_children())
        self.assertEqual(names, ['alerjen.txt', 'egitim.csv'])
        v.in_text.set(False)
        v.refresh_list()
        self.assertEqual(len(v.tv.get_children()), 0)
        v.in_text.set(True)
        v.q.set('')
        v.refresh_list()
        # liste secimi -> sohbet kapsami
        one = next(i for i in v.tv.get_children() if v.tv.set(i, 'name') == 'tek-belge.txt')
        v.tv.selection_set(one)
        self.pump(n=10)
        self.assertEqual(app._scope_ids(), [one])
        self.assertIn('tek-belge.txt', app.scope_lbl.cget('text'))
        v.chat_selected()
        self.pump(n=5)
        self.assertEqual(app.ai_nb.index(app.ai_nb.select()), SV.SOURCES_TAB)
        # siralama
        v._sort_by('chars')
        vals = [int(v.tv.set(i, 'chars').replace('.', '')) for i in v.tv.get_children()]
        self.assertEqual(vals, sorted(vals, reverse=True))
        # kaldirma: gezgin ve panel birlikte guncellenir
        v.tv.selection_set(one)
        v.remove_selected()
        self.pump(n=5)
        self.assertEqual(len(app.src_docs), 3)
        self.assertEqual(len(v.tv.get_children()), 3)
        v.remove_folder(self.root)
        self.pump(n=5)
        self.assertEqual(len(app.src_docs), 0)
        self.assertEqual(len(v.tv.get_children()), 0)
        # sekme kapanir
        app.close_tab_frame(v)
        self.pump(n=5)
        self.assertIsNone(app.src_explorer)

    @staticmethod
    def _walk(tv, node=''):
        for c in tv.get_children(node):
            yield c
            yield from ExplorerGuiTests._walk(tv, c)


if __name__ == '__main__':
    unittest.main()
