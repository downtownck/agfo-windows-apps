# -*- coding: utf-8 -*-
"""BRCGS calisma alani arayuzu (xvfb-run ile): gezgin, rapor sekmesi, tum sayfalar, alan/kilavuz/NA/NC/tablo duzenleme,
kaydet, kurtarma taslagi, AI taslagi, Excel plani, DOCX'e yaz -> geri oku, DOCX acarken BRCGS algilama."""
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
TMP = tempfile.mkdtemp(prefix='agfo-brcgs-ui-')
os.environ['LOCALAPPDATA'] = TMP

try:
    import lxml  # noqa: F401
    HAVE_LXML = True
except ImportError:  # pragma: no cover
    HAVE_LXML = False


def _display():
    return sys.platform == 'win32' or bool(os.environ.get('DISPLAY'))


@unittest.skipUnless(_display() and HAVE_LXML, 'ekran ya da lxml yok')
class BrcgsUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.machinery
        import importlib.util
        loader = importlib.machinery.SourceFileLoader('agfo_ai_editor', str(SRC / 'agfo_ai_editor.pyw'))
        spec = importlib.util.spec_from_loader('agfo_ai_editor', loader)
        cls.m = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.m)
        from agfo_brcgs import store as S
        cls.S = S

    def setUp(self):
        self.app = self.m.App(smoke=True)
        self.app.withdraw()
        self.app._brcgs_store = self.S.Store(tempfile.mkdtemp(dir=TMP))

    def tearDown(self):
        for w in list(self.app.winfo_children()):
            if isinstance(w, self.m.tk.Toplevel):
                w.destroy()
        self.app.destroy()

    def pump(self, until=lambda: False, n=60):
        import time
        for _ in range(n):
            self.app.update()
            if until():
                return True
            time.sleep(0.01)
        return False

    def _new(self, profile):
        ex = self.app.open_brcgs()
        self.assertIs(self.app.cur_brcgs(), ex)
        self.assertFalse(self.app.docs, 'boş Adsız belge kapanmalı')
        ex.new_report(profile)
        v = self.app.cur_brcgs()
        self.assertIn(v, self.app.brcgs_views)
        return ex, v

    def test_every_page_renders_for_every_profile(self):
        from agfo_brcgs import data as D
        for p in D.PROFILES:
            with self.subTest(profile=p):
                _ex, v = self._new(p)
                for key in list(v.nav_btns):
                    v.show(key)
                    self.app.update()
                for ch in v.chapters()[:3]:
                    v._set_chapter(ch)
                    v.step(1)
                    v.step(-1)
                    self.app.update()
                self.assertTrue(self.app.close_brcgs_view(v, ask=False))

    def test_edit_save_export_reimport(self):
        ex, v = self._new('cp')
        # sablon alani
        f = next(x for x in v.fields if x['key'] in ('OWNERCOMPANY', 'COMPANY_NAME', 'SITE_NAME', 'CERTIFIED_SITE_NAME'))
        v._set_value(f, 'Örnek Ambalaj A.Ş.')
        self.assertTrue(v.dirty)
        self.assertTrue(self.app.nb.tab(v, 'text').startswith('● '))
        # kilavuz kutusu
        v.show('sections')
        idx, row = v.current_row()
        from agfo_brcgs import guide as G
        form = G.form_for('cp', row['clause'])
        v._answer(row, form['fields'][0]['key'], 'Management review minutes dated 2026-03-12 were reviewed.')
        self.assertIn('Management review minutes', row['value'])
        v._note(row, 'YGG toplantı tutanağı görüldü')
        # NA, NC, tablo
        v._na_add()
        v.project['meta']['na_clauses'][0].update(clause_ref='5.3', justification='No printing on site')
        v._plan_add()
        v.project['meta']['action_plan']['items'][0].update(type='minor', clause='2.1', nc_text='Hazard analysis not reviewed',
                                                            correction='Reviewed')
        for key, _t, cols in v.tables[:1]:
            v._table_add(key, cols)
            v.project['meta']['report_tables'][key][0][cols[0]] = 'Ayşe Yılmaz'
        self.assertTrue(self.app.save())                       # Ctrl+S sekmeye yonlenir
        self.assertFalse(v.dirty)
        self.assertEqual(ex.store.list()[0]['company'], 'Örnek Ambalaj A.Ş.')
        out = os.path.join(TMP, 'cp-out.docx')
        with mock.patch.object(self.m.filedialog if False else __import__('agfo_brcgs_view').filedialog, 'asksaveasfilename',
                               return_value=out), \
                mock.patch.object(__import__('agfo_brcgs_view').messagebox, 'askyesno', return_value=False):
            v.export_docx()
        self.assertTrue(os.path.getsize(out) > 10000)
        back = self.app.brcgs_store().import_docx(out)
        got = {s['clause']: s['value'] for s in back['sections']}
        self.assertIn('Management review minutes', got[row['clause']])
        self.assertEqual(back['meta']['na_clauses'], [{'clause_ref': '5.3', 'justification': 'No printing on site'}])
        self.assertEqual(back['meta']['action_plan']['items'][0]['nc_text'], 'Hazard analysis not reviewed')
        # DOCX acarken algilama
        self.assertEqual(self.app._brcgs_profile_of(out), 'cp')
        self.assertIsNone(self.app._brcgs_profile_of(os.path.join(TMP, 'yok.docx')))

    def test_draft_recovery_and_close_prompts(self):
        _ex, v = self._new('fs')
        uid = v.uid
        v._note(v.project['sections'][0], 'kurtarılacak not')
        self.app._autosave()
        self.assertIsNotNone(self.app.brcgs_store().get_draft(uid))
        # kaydetmeden kapat ("Hayir"): taslak silinir
        with mock.patch.object(self.m.messagebox, 'askyesnocancel', return_value=False):
            self.assertTrue(self.app.close_brcgs_view(v))
        self.assertIsNone(self.app.brcgs_store().get_draft(uid))
        # cokme benzetimi: taslak var, rapor yeniden acilinca geri gelir (smoke: soru sormadan)
        pr = self.app.brcgs_store().get(uid)
        pr['sections'][0]['note'] = 'çökmeden önce'
        import time
        time.sleep(0.01)
        self.app.brcgs_store().save_draft(pr)
        v2 = self.app.open_brcgs_report(uid)
        self.assertTrue(v2.recovered and v2.dirty)
        self.assertEqual(v2.project['sections'][0]['note'], 'çökmeden önce')
        self.assertTrue(v2.save())
        self.assertIsNone(self.app.brcgs_store().get_draft(uid))

    def test_ai_writes_english_report_text_directly(self):
        _ex, v = self._new('sd')
        v.show('sections')
        _i, row = v.current_row()
        from agfo_brcgs import guide as G
        k = G.form_for('sd', row['clause'])['fields'][0]['key']
        v._answer(row, k, 'Prosedür mevcut, 2025 revizyon')
        v._sec_add_nc(row)
        nc = v.project['meta']['action_plan']['items'][0]
        nc['nc_text'] = 'Dağıtım listesi güncel değil'
        calls = []

        def fake(backends, fn, text, action, opts):
            calls.append((text, action['extra']))
            return {'text': 'The site has a documented procedure (revision 2025). Based on the records reviewed, document control was '
                            'verified.\n=== NON-CONFORMITIES ===\n1. The distribution list was not up to date.',
                    'via': 'T', 'provider': 'P', 'model': 'm'}
        with mock.patch.object(self.m.ai, 'run_with_fallback', fake), mock.patch.object(self.app, 'backends', return_value=[]):
            v.ai_draft(row)
            self.assertTrue(self.pump(lambda: G.report_text(row), 300))
        self.assertIn('Prosedür mevcut', calls[0][0])
        self.assertIn('Dağıtım listesi güncel değil', calls[0][0])
        self.assertIn('Do NOT write non-conformity', calls[0][1])
        self.assertTrue(row['value'].startswith('The site has a documented procedure'))
        self.assertNotIn('NON-CONFORMITIES', row['value'])
        self.assertEqual(nc['nc_text'], 'The distribution list was not up to date.')
        self.assertEqual(nc['nc_text_original'], 'Dağıtım listesi güncel değil')
        self.assertEqual(G.struct_of(row)[k], 'Prosedür mevcut, 2025 revizyon')           # kanit kutusu yerinde
        from agfo_brcgs import findings as F
        self.assertEqual(F.closing_lines(v.project, row), ['Minor NC %s: The distribution list was not up to date.' % row['clause']])
        # kanit degisince Ingilizce metin korunur, uyari gorunur
        v._answer(row, k, 'Prosedür mevcut, 2026 revizyon')
        self.assertTrue(row['value'].startswith('The site has'))
        self.assertIn('evidence changed', v._stale_lbl.cget('text'))

    def test_section_na_nc_and_scan_counts(self):
        _ex, v = self._new('cp')
        v.show('sections')
        _i, row = v.current_row()
        v._sec_add_na(row)
        v.project['meta']['na_clauses'][0]['justification'] = 'Not relevant'
        v._sec_add_nc(row)
        v.project['meta']['action_plan']['items'][0].update(type='major', nc_text='Policy not signed')
        row2 = next(r for r in v.project['sections'] if r['clause'] == '2.2')
        row2['value'] = 'Risk assessment reviewed. Minor NC 2.2.2 : Misuse not covered.'
        with mock.patch.object(__import__('agfo_brcgs_view').messagebox, 'showinfo') as info:
            res = v.scan_findings()
        msg = info.call_args[0][1]
        self.assertIn('Critical 0 · Major 1 · Minor 1 · Fundamental 0 · NA 1', msg)
        self.assertEqual(len(res['added']), 1)
        v.show('g:Number of non-conformities')
        payload = v.store.export_payload(v.project)
        self.assertEqual((payload['values']['MAJOR'], payload['values']['MINOR']), ('1', '1'))
        v.show('overview')
        self.app.update()

    def test_excel_plan_fill_and_profile_mismatch(self):
        _ex, v = self._new('fs')
        from agfo_brcgs import guide as G
        row = v.project['sections'][0]
        form = G.form_for('fs', row['clause'])
        k0, k1 = form['fields'][0]['key'], form['fields'][1]['key']
        v._answer(row, k0, 'mevcut metin')
        parsed = {'profile': 'fs', 'rows': [{'clause': row['clause'], 'key': k0, 'value': 'excel metni'},
                                            {'clause': row['clause'], 'key': k1, 'value': 'yeni yanıt'},
                                            {'clause': row['clause'], 'key': '_note', 'value': 'excel notu'},
                                            {'clause': '99.9', 'key': 'x', 'value': 'y'}]}
        plan = v.plan_excel(parsed)
        self.assertEqual((plan['answers'], plan['notes'], plan['conflicts'], plan['skipped']), (2, 1, 1, ['99.9']))
        n = v.apply_excel(parsed, 'x.xlsx', mode='fill')
        self.assertEqual(n, 2)
        st = G.struct_of(row)
        self.assertEqual((st[k0], st[k1], row['note']), ('mevcut metin', 'yeni yanıt', 'excel notu'))
        self.assertFalse(v.dirty)                                 # ice aktarma sonunda kaydedilir
        self.assertTrue(any(r['label'] == 'pre-excel-import' for r in v.store.revisions(v.uid)))
        self.assertIn('error', v.plan_excel({'profile': 'cp', 'rows': parsed['rows']}))

    def test_real_excel_file_import_to_docx(self):
        import test_brcgs_xlsx as TX
        from agfo_brcgs import xlsx_reader as X
        _ex, v = self._new('cp')
        keys = TX.first_field_keys('cp', 3)
        filled = TX.make_filled(tempfile.mkdtemp(dir=TMP), 'cp', [(c, k, ('inline', 'Excel yanıtı %d' % i)) for i, (c, k, _l) in enumerate(keys)])
        vm = __import__('agfo_brcgs_view')
        with mock.patch.object(vm.filedialog, 'askopenfilename', return_value=str(filled)), \
                mock.patch.object(vm.messagebox, 'askokcancel', return_value=True) as ok:
            v.import_excel()
            ok.assert_called_once()
        self.assertEqual(len(X.parse(str(filled))['rows']), 3)
        by = {s['clause']: s for s in v.store.get(v.uid)['sections']}
        for i, (c, _k, _l) in enumerate(keys):
            self.assertIn('Excel yanıtı %d' % i, by[c]['value'])
        blob, _st = v.store.export_docx(v.uid, os.path.join(TMP, 'cp-x.docx'))
        back = self.app.brcgs_store().import_docx(os.path.join(TMP, 'cp-x.docx'))
        self.assertIn('Excel yanıtı 0', {s['clause']: s['value'] for s in back['sections']}[keys[0][0]])

    def test_explorer_side_tree_click_does_not_loop(self):
        # 2.2.0: sol agacta bir ogeye tiklamak refresh -> secim geri yukleme -> <<TreeviewSelect>> -> refresh dongusune giriyordu
        ex = self.app.open_brcgs()
        ex.store.create('fs', values={'OWNERCOMPANY': 'Firma A'})
        ex.refresh()
        calls = []
        orig = ex.refresh
        ex.refresh = lambda: (calls.append(1), orig())
        for iid in ('p_fs', 'all', 'c_0', 'trash', 'grp_std'):
            del calls[:]
            ex.tree_side.selection_set(iid)
            self.pump(n=40)
            self.assertLessEqual(len(calls), 1, iid)
        self.assertEqual(ex.filter, ('all', None))

    def test_explorer_trash_rules(self):
        ex, v = self._new('ab')
        ex.refresh()
        ex.tv.selection_set(v.uid)
        with mock.patch.object(__import__('agfo_brcgs_view').messagebox, 'showinfo') as info:
            ex.trash_selected()                                    # acik rapor cope gitmez
            info.assert_called()
        self.app.close_brcgs_view(v, ask=False)
        ex.tv.selection_set(v.uid)
        ex.trash_selected()
        self.assertEqual([r['id'] for r in ex.store.list('trash')], [v.uid])
        ex.filter = ('trash', None)
        ex.refresh()
        ex.tv.selection_set(v.uid)
        ex.delete_selected(confirm='hayır')
        self.assertEqual(len(ex.store.list('trash')), 1)
        ex.delete_selected(confirm='delete')
        self.assertEqual(ex.store.list('all'), [])


if __name__ == '__main__':
    unittest.main()
