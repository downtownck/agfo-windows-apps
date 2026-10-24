# -*- coding: utf-8 -*-
"""2.3.0 Word gorunumu: DOCX'e bagli rapor (Kaydet dosyanin kendisine yazar, tekrar yazimda buyumez, Word'de degisince
geri okunur), sayfa tiklamasi -> alan/bolum, fare tekerlegi (giris kutularinin ustunde de), acilir liste tekerlekle
degismez, BRCGS DOCX'i acmak dogrudan bagli rapor acar."""
import io
import os
import pathlib
import shutil
import sys
import tempfile
import time
import unittest
import zipfile
from unittest import mock

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
TMP = tempfile.mkdtemp(prefix='agfo-wordview-')
os.environ['LOCALAPPDATA'] = TMP

try:
    import lxml  # noqa: F401
    HAVE_LXML = True
except ImportError:  # pragma: no cover
    HAVE_LXML = False

if HAVE_LXML:
    from agfo_brcgs import data as D
    from agfo_brcgs import docx_engine as E
    from agfo_brcgs import store as S


def _display():
    return sys.platform == 'win32' or bool(os.environ.get('DISPLAY'))


def leaf_texts(blob):
    tpl = E.DocxTemplate(blob)
    W = E.w
    out = []
    for name, sdt in tpl.all_sdts():
        cont = sdt.find(W('sdtContent'))
        if name != 'word/document.xml' or cont is None or next(cont.iter(W('sdt')), None) is not None \
                or next(sdt.iter(W('tbl')), None) is not None:
            continue
        out.append((E.sdt_props(sdt)['tag'], E.sdt_text(sdt)))
    return out


class FakeRenderer:
    """Word yerine: denetim metinlerini sirayla yazan gercek bir PDF uretir (CI'da Word/LibreOffice yok)."""
    engine = 'Fake Word'

    def __init__(self):
        self.calls = 0

    def to_pdf(self, blob):
        import agfo_pdf
        self.calls += 1
        lines = [(t[:60] or '.').replace('\n', ' ') for _tag, t in leaf_texts(blob)]
        pages = [lines[i:i + 30] for i in range(0, len(lines), 30)] or [['empty']]
        p = os.path.join(tempfile.mkdtemp(dir=TMP), 'x.pdf')
        agfo_pdf.write_simple_pdf(p, pages)
        return pathlib.Path(p).read_bytes()

    def close(self):
        pass


@unittest.skipUnless(HAVE_LXML, 'lxml yok')
class LinkedDocxStoreTests(unittest.TestCase):
    def test_link_save_idempotent_backup_reload(self):
        d = tempfile.mkdtemp(dir=TMP)
        st = S.Store(os.path.join(d, 'store'))
        f = os.path.join(d, 'cp report.docx')
        shutil.copy(D.template_path('cp'), f)
        pr = st.import_docx(f, link=True)
        self.assertEqual(st.find_linked(f), pr['id'])
        pr['values']['OWNERCOMPANY'] = 'Örnek A.Ş.'
        pr['sections'][0]['value'] = 'The policy was reviewed.\n\nSigned by the general manager.'
        sizes = []
        for _ in range(3):
            st.write_linked(pr)
            pr = st.save(pr)
            sizes.append(len(zipfile.ZipFile(f).read('word/document.xml')))
        self.assertEqual(sizes[1], sizes[2], 'ayni dosyaya tekrar yazim belgeyi buyutmemeli')
        self.assertEqual(len(os.listdir(os.path.join(d, 'store', 'docx-backups', pr['id']))), 3)
        back = E.read_report(f)
        self.assertEqual(back['values']['OWNERCOMPANY'], 'Örnek A.Ş.')
        self.assertEqual(back['sections'][0]['value'], 'The policy was reviewed.\n\nSigned by the general manager.')
        # ust/alt bilgi, logo, stiller: document.xml disindaki parcalar bayt bayt ayni
        src = zipfile.ZipFile(D.template_path('cp'))
        out = zipfile.ZipFile(f)
        self.assertEqual([n for n in src.namelist() if n != 'word/document.xml' and src.read(n) != out.read(n)], [])
        # Word'de degistirilip kaydedildi
        pay = S.Store.export_payload(pr)
        pay['sections'][1]['value'] = 'Changed in Word.'
        blob, _st = E.write_report(pay, template=pathlib.Path(f).read_bytes())
        time.sleep(0.01)
        pathlib.Path(f).write_bytes(blob)
        self.assertNotEqual(S.file_sig(f), pr['meta']['linked_sig'])
        pr = st.reload_linked(pr)
        self.assertEqual(pr['sections'][1]['value'], 'Changed in Word.')
        self.assertEqual(pr['sections'][0]['value'], 'The policy was reviewed.\n\nSigned by the general manager.')
        self.assertEqual(pr['meta']['linked_sig'], S.file_sig(f))

    def test_anchors_follow_document_order(self):
        import agfo_docrender as R
        pr = {'profile': 'fs', 'values': {'OWNERCOMPANY': 'Firma Bir'}, 'sections': []}
        from agfo_brcgs import boxes as B
        pr['sections'] = B.sections_for_profile('fs')
        for s in pr['sections']:
            s['value'] = 'Text of %s' % s['clause']
        blob, _ = E.write_report(pr)
        targets = leaf_texts(blob)
        pdf = FakeRenderer().to_pdf(blob)
        found = R.anchors(pdf, targets)
        tags = [t for t, *_r in found]
        self.assertIn('OWNERCOMPANY', tags)
        self.assertGreaterEqual(len(set(tags) & B.detail_tags('fs')), 80)
        pages = [p for _t, p, _x, _y in found]
        self.assertEqual(pages, sorted(pages))                     # sira bozulmaz
        # tiklama: F3_9 baslangicinin hemen alti -> F3_9
        a = next(x for x in found if x[0] == 'F3_9')
        self.assertEqual(R.nearest_anchor(found, a[1], a[2] + 20, a[3] + 4), 'F3_9')


@unittest.skipUnless(_display() and HAVE_LXML, 'ekran ya da lxml yok')
class WordViewUiTests(unittest.TestCase):
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

    def test_open_brcgs_docx_word_view_click_and_save_back(self):
        d = tempfile.mkdtemp(dir=TMP)
        f = os.path.join(d, 'ab.docx')
        shutil.copy(D.template_path('ab'), f)
        v = self.app.open_path(f)                                   # soru sormadan bagli rapor olarak acilir
        self.assertEqual(type(v).__name__, 'BrcgsReportView')
        self.assertEqual(v.page, 'word')
        self.assertEqual(v.project['meta']['linked_docx'], os.path.abspath(f))
        self.assertTrue(self.pump(lambda: v._word['pdf'] is not None and not v._word['busy']))
        self.assertGreater(len(v._word['found']), 20)
        self.assertIsNotNone(v.wordview.doc)
        # ayni dosyayi tekrar acmak yeni rapor olusturmaz
        self.assertIs(self.app.open_path(f), v)
        self.assertEqual(len(self.app.brcgs_store().list()), 1)
        # tiklama -> bolum
        from agfo_brcgs import boxes as B
        (tag, occ), page, x, y = next(a for a in v._word['found'] if a[0][0] in B.detail_tags('ab'))
        kind, focus, _label = v._target_info((tag, occ))
        self.assertEqual(kind, 'section')
        v.pick_target((tag, occ))
        self.pump(n=10)
        self.assertEqual(v.page, 'sections')
        self.assertEqual(v.current_row()[1]['clause'], focus)
        # alan tiklamasi -> alan odakta
        fld = next(a for a in v._word['found'] if a[0][0] == 'BRC_SITE_CODE')
        v.show('word')
        v.pick_target(fld[0])
        self.pump(n=20)
        self.assertTrue(v.page.startswith('g:'))
        self.assertIs(self.app.focus_get() or self.app.focus_lastfor(), v._field_widgets[('BRC_SITE_CODE', 0)])
        # duzenle -> kaydet -> dosyaya yazildi; Word gorunumu yeniden cizilir
        f_ = next(x for x in v.fields if x['key'] == 'BRC_SITE_CODE')
        v._set_value(f_, '7654321')
        calls = self.app._doc_renderer.calls
        self.assertTrue(v.save())
        self.assertEqual(E.read_report(f)['values']['BRC_SITE_CODE'], '7654321')
        v.set_mode('word')
        self.assertTrue(self.pump(lambda: self.app._doc_renderer.calls > calls and not v._word['busy']))
        # Word'de degisti -> pencere odaga donunce yuklenir
        pay = S.Store.export_payload(v.project)
        pay['values']['BRC_SITE_CODE'] = '1112223'
        blob, _ = E.write_report(pay, template=pathlib.Path(f).read_bytes())
        time.sleep(0.01)
        pathlib.Path(f).write_bytes(blob)
        v.check_linked()
        self.assertEqual(v.project['values']['BRC_SITE_CODE'], '1112223')
        self.assertFalse(v.dirty)

    def test_mouse_wheel_scrolls_over_inputs_and_combobox_keeps_value(self):
        # xvfb-run varsayilan ekrani 640x480: pencere ekrana sigmali, yoksa ekran disindaki noktada pencere bulunmaz
        self.app.minsize(1, 1)
        self.app.geometry('%dx%d+0+0' % (min(1200, self.app.winfo_screenwidth()), min(800, self.app.winfo_screenheight() - 20)))
        self.pump(n=10)
        ex = self.app.open_brcgs()
        ex.new_report('fs')
        v = self.app.cur_brcgs()
        v.show('sections')                                          # uzun sayfa: kilavuz kutulari + NA/NC
        self.pump(n=30)
        import tkinter as tk
        from tkinter import ttk
        canvas = [c for c in self._walk(v.main) if isinstance(c, tk.Canvas)][-1]  # bolum duzenleyicisinin kaydirma alani
        self.assertLess(canvas.yview()[1], 1.0, 'sayfa tasmali')
        editor = [w for w in self._walk(canvas) if w.winfo_ismapped()]
        entry = next(w for w in editor if isinstance(w, tk.Text) and w.winfo_ismapped())
        v._sec_add_nc(v.current_row()[1])
        self.pump(n=20)
        canvas = [c for c in self._walk(v.main) if isinstance(c, tk.Canvas)][-1]

        def visible():
            top = max(canvas.winfo_rooty(), self.app.winfo_rooty())
            bot = min(canvas.winfo_rooty() + canvas.winfo_height(), self.app.winfo_rooty() + self.app.winfo_height(),
                      self.app.winfo_screenheight())
            return [w for w in self._walk(canvas) if w.winfo_ismapped() and top + 5 < w.winfo_rooty() < bot - 30]
        def bring_nc_row_into_view():
            combo_ = next(w for w in self._walk(canvas) if isinstance(w, ttk.Combobox))
            canvas.yview_moveto(1.0)
            self.pump(n=10)
            return combo_

        def wheel_up_over(kind):
            bring_nc_row_into_view()
            before = canvas.yview()[0]
            self.assertGreater(before, 0.0)
            w_ = next(w for w in visible() if isinstance(w, kind))
            x, y = w_.winfo_rootx() + 5, w_.winfo_rooty() + 5
            self.assertIs(self.app.winfo_containing(x, y), w_)
            combo_ = next(w for w in self._walk(canvas) if isinstance(w, ttk.Combobox))
            val = combo_.get()
            w_.event_generate('<MouseWheel>', delta=120, x=5, y=5, rootx=x, rooty=y)     # yukari
            self.pump(n=5)
            self.assertEqual(combo_.get(), val, 'tekerlek acilir listenin degerini degistirmemeli')
            self.assertLess(canvas.yview()[0], before, 'tekerlek %s ustunde sayfayi kaydirmali' % kind.__name__)
        wheel_up_over(ttk.Combobox)
        wheel_up_over(tk.Text)                                          # tasmayan metin kutusu: sayfa kayar

    def _walk(self, w):
        out = [w]
        for ch in w.winfo_children():
            out += self._walk(ch)
        return out


if __name__ == '__main__':
    unittest.main()
