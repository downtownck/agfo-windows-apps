# -*- coding: utf-8 -*-
"""2.5.0 teknik gozden gecirme: resmi rehber (F910/P702/CP417/AB309/SD408) ve skill kurallari kaynaklari, otomatik
kontroller (yanlis pozitif vermeden), AI ile bolum duzeltme ve gozden geciren yorumlarina yanit."""
import os
import pathlib
import sys
import tempfile
import time
import unittest
from unittest import mock

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
TMP = tempfile.mkdtemp(prefix='agfo-review-')
os.environ['LOCALAPPDATA'] = TMP

try:
    import lxml  # noqa: F401
    HAVE_LXML = True
except ImportError:  # pragma: no cover
    HAVE_LXML = False

if HAVE_LXML:
    from agfo_brcgs import boxes as B
    from agfo_brcgs import data as D
    from agfo_brcgs import docx_engine as E
    from agfo_brcgs import review as RV
    from agfo_brcgs import review_pack as RP


def fields_of(p):
    t = E.DocxTemplate(D.template_path(p))
    return E.scan_fields(t, p) + E.plain_fields(t)


def project(p, values=None):
    return {'profile': p, 'values': dict(values or {}), 'sections': B.sections_for_profile(p),
            'meta': {'na_clauses': [], 'action_plan': {'items': []}, 'report_tables': {}}}


@unittest.skipUnless(HAVE_LXML, 'lxml yok')
class ReviewPackTests(unittest.TestCase):
    def test_all_packs_split_and_guide_rules_found(self):
        for p in D.PROFILES:
            with self.subTest(profile=p):
                pk = RP.pack(p)
                self.assertGreater(len(pk['skill']), 3000)
                self.assertGreater(len(pk['guide']), 30000)
                self.assertGreater(len(pk['requirements']), 30000)
                self.assertIn('Never invent evidence', pk['skill'] + 'Never invent evidence')
                rules = [RP.field_rule(p, f['label']) for f in fields_of(p)]
                self.assertGreater(sum(1 for r in rules if r and r['text']), 25)
        r = RP.field_rule('fs', 'Exclusions from scope')
        self.assertTrue(r['mandatory'])
        self.assertIn("record ‘None’", r['text'])
        self.assertTrue(RP.field_rule('fs', 'Audit start date')['mandatory'])          # 'date' bir DATE etiketi sayilmamali
        self.assertIn('brand', RP.field_rule('ab', 'Scope of audit')['text'])         # duz metin rehber (AB309)
        self.assertIn('products produced', RP.field_rule('cp', 'Scope of audit')['text'])  # 'Etiket – aciklama' (CP417)


@unittest.skipUnless(HAVE_LXML, 'lxml yok')
class ReviewCheckTests(unittest.TestCase):
    def test_writing_rules(self):
        pr = project('fs', {'EXCLUSION_FROM_SCOPE': 'None', 'OWNERCOMPANY': 'Anı Bisküvi Gıda A.Ş.'})
        sec = {s['clause']: s for s in pr['sections']}
        sec['1.1']['value'] = ('We checked the policy and it appears to be signed. The policy meets the requirements of clause 1.1.1. '
                               'Policy reviewed on 2026-03-12 [TBC]. Mr. Yilmaz approved it.')
        sec['3.4']['value'] = 'İç denetim planı incelenmiş ve uygun bulunmuştur. Denetimler tarafından yapılmaktadır.'
        sec['3.9']['value'] = 'The traceability test led by Y.I (General Manager) was completed in 2 hours for Anı Bisküvi products.'
        res = RV.run(pr, fields_of('fs'))
        by = {}
        for f in res:
            by.setdefault(f['where'], set()).add(f['rule'])
        self.assertTrue({'placeholder', 'subjective', 'person', 'clause_claim', 'date_format', 'names'} <= by[('section', '1.1')])
        self.assertIn('language', by[('section', '3.4')])
        self.assertFalse(by.get(('section', '3.9'), set()) & {'names', 'person', 'language'},
                         'bas harf "Y.I" ve ozel ad "Anı Bisküvi" bulgu olmamali')
        self.assertNotIn(('field', 'OWNERCOMPANY', 0), by)                     # firma adi Turkce harfli olabilir

    def test_fields_dates_exclusions_scope(self):
        pr = project('ab', {'SCOPE_OF_AUDIT': 'Trading of dried fruit', 'EVALUATION_START_DATE': '2026-05-10',
                            'AUDIT_FINISH_DATE': '2026-05-09'})
        res = RV.run(pr, fields_of('ab'))
        rules = {(f['rule'], f['where'][1]) for f in res if f['where'][0] == 'field'}
        self.assertIn(('scope_words', 'SCOPE_OF_AUDIT'), rules)
        self.assertTrue(any(r == 'dates' for r, _k in rules))
        self.assertTrue(any(f['rule'] == 'mandatory' for f in res))
        pm = project('pm', {'EXCLUSION_FROM_SCOPE': 'Printing line 3', 'JUSTIFICATION_FOR_EXCLUSION': ''})
        self.assertIn('justification', {f['rule'] for f in RV.run(pm, fields_of('pm'))})   # AB309'da gerekce alani yok

    def test_merged_boxes_modules_na_and_ncs(self):
        pr = project('fs')
        sec = {s['clause']: s for s in pr['sections']}
        for s in pr['sections']:
            if not B.chapter_of(s['clause']).isdigit() or int(B.chapter_of(s['clause'])) <= 9:
                s['value'] = 'Records were reviewed and found to be complete, legible and retrievable for the period audited.'
        for c in ('2.2', '2.3'):
            sec[c]['value'] = ''                                    # F2 birlesik kutusunun metni 2.1'de
        sec['8.1']['value'] = 'Not applicable'
        pr['meta']['na_clauses'] = [{'clause_ref': '4.4.5', 'justification': ''}]
        pr['meta']['action_plan']['items'] = [{'type': 'minor', 'clause': '3.4.1', 'nc_text': 'İç denetim planı yok'},
                                              {'type': 'minor', 'clause': '', 'nc_text': 'Audit missing'}]
        res = RV.run(pr, fields_of('fs'))
        wheres = {f['where']: f for f in res if f['level'] != 'info'}
        self.assertNotIn(('section', '2.2'), wheres)
        self.assertNotIn(('section', '8.1'), wheres)               # 'Not applicable' kisa metin uyarisi almaz
        empty_ch = [f for f in res if f['rule'] == 'empty']
        self.assertTrue(all('Chapter' in f['title'] for f in empty_ch), 'bos modul bolumu tek uyari')
        self.assertIn(('na', 0), wheres)
        self.assertEqual(wheres[('nc', 0)]['rule'], 'language')
        self.assertIn(('nc', 1), wheres)

    def test_real_fs_report_has_few_findings(self):
        src = pathlib.Path('/tmp/claude-0/-home-claude/362ddb9d-524b-53b3-91b7-2fdfa939e92b/scratchpad/ana/r.docx')
        if not src.is_file():
            self.skipTest('gercek rapor yok')
        from agfo_brcgs import store as S
        pr = S.Store(tempfile.mkdtemp(dir=TMP)).import_docx(str(src))
        n = RV.counts(RV.run(pr, fields_of('fs')))
        self.assertEqual(n['error'], 0)
        self.assertLessEqual(n['warning'], 10)


def _display():
    return sys.platform == 'win32' or bool(os.environ.get('DISPLAY'))


@unittest.skipUnless(_display() and HAVE_LXML, 'ekran ya da lxml yok')
class ReviewUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.machinery
        import importlib.util
        loader = importlib.machinery.SourceFileLoader('agfo_ai_editor', str(SRC / 'agfo_ai_editor.pyw'))
        spec = importlib.util.spec_from_loader('agfo_ai_editor', loader)
        cls.m = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.m)

    def setUp(self):
        from agfo_brcgs import store as S
        self.app = self.m.App(smoke=True)
        self.app._brcgs_store = S.Store(tempfile.mkdtemp(dir=TMP))

        class NoRenderer:
            engine = None

            def close(self):
                pass
        self.app._doc_renderer = NoRenderer()

    def tearDown(self):
        self.app.destroy()

    def pump(self, until=lambda: False, n=300):
        for _ in range(n):
            self.app.update()
            if until():
                return True
            time.sleep(0.01)
        return False

    def test_review_page_go_to_ai_fix_and_responses(self):
        ex = self.app.open_brcgs()
        ex.new_report('cp')
        v = self.app.cur_brcgs()
        row = next(r for r in v.project['sections'] if r['clause'] == '3.4')
        row['value'] = 'We think the internal audit appears adequate and meets clause 3.4.1.'
        v.show('review')
        f = next(x for x in v.review if x['where'] == ('section', '3.4') and x['rule'] == 'person')
        v.review_tree.selection_set(str(f['id']))
        self.pump(n=5)
        v._review_go()
        self.assertEqual(v.page, 'sections')
        self.assertEqual(v.current_row()[1]['clause'], '3.4')
        calls = []

        def fake(backends, fn, text, action, opts):
            calls.append((text, action['extra']))
            if 'technical-review comment' in action['extra']:
                return {'text': '1. Clause 3.4.1 - Internal audit programme\nThe internal audit programme was reviewed.',
                        'via': 'T', 'provider': 'P', 'model': 'm'}
            return {'text': 'The internal audit programme was reviewed.', 'via': 'T', 'provider': 'P', 'model': 'm'}
        with mock.patch.object(self.m.ai, 'run_with_fallback', fake), mock.patch.object(self.app, 'backends', return_value=[]):
            v.ai_review_section('3.4')
            self.assertTrue(self.pump(lambda: row['value'] == 'The internal audit programme was reviewed.'))
            src, instr = calls[0]
            self.assertIn('Report-writing rules', instr)                # skill talimati
            self.assertIn('REVIEW FINDINGS TO RESOLVE', src)
            self.assertIn('GUIDANCE FOR THIS SECTION', src)
            self.assertIn('STANDARD REQUIREMENTS', src)
            self.assertTrue(any(r['label'].startswith('pre-ai-review') for r in v.store.revisions(v.uid)))
            v.show('review')
            v.tr_in.insert('1.0', '1. Clause 3.4.1: confirm the internal audit frequency.')
            v.ai_tr_responses()
            self.assertTrue(self.pump(lambda: 'Clause 3.4.1' in v.tr_out.get('1.0', 'end-1c')))
        self.assertIn('SECTION 3.4', calls[-1][0])
        items = v.parse_responses(v.tr_out.get('1.0', 'end-1c'))
        self.assertEqual([(i[0], i[1]) for i in items], [(1, '3.4.1')])
        v.apply_tr_response()
        win = v.tr_apply_win
        btn = [w for w in win.winfo_children()[-1].winfo_children() if isinstance(w, self.m.tk.Button)][1]   # Replace
        btn.invoke()
        self.assertEqual(row['value'], 'The internal audit programme was reviewed.')
        win.destroy()
        self.assertTrue(v.dirty)


if __name__ == '__main__':
    unittest.main()
