# -*- coding: utf-8 -*-
"""BRCGS rapor deposu: olustur/kaydet, veri kaybi korumasi, surumler (25), cop kutusu, DOCX ice/dis aktarma."""
import pathlib
import sys
import tempfile
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))

try:
    import lxml  # noqa: F401
    HAVE_LXML = True
except ImportError:  # pragma: no cover
    HAVE_LXML = False

if HAVE_LXML:
    from agfo_brcgs import boxes as B
    from agfo_brcgs import store as S


@unittest.skipUnless(HAVE_LXML, 'lxml yok')
class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='brs-store-')
        self.st = S.Store(self.tmp)

    def test_create_save_list_and_guard(self):
        pr = self.st.create('cp', values={'BRC_SITE_CODE': '1234567', 'OWNERCOMPANY': 'XYZ CP A.Ş.'})
        self.assertEqual(pr['title'], 'XYZ CP A.Ş. CP Audit Report')
        self.assertEqual(len(pr['sections']), 46)
        self.assertEqual(self.st.list()[0]['site_code'], '1234567')
        for s in pr['sections']:
            s['value'] = 'Uzun denetim metni. ' * 20
        pr = self.st.save(pr)
        self.assertGreater(pr['text_score'], 4000)
        wiped = dict(pr, sections=[dict(s, value='') for s in pr['sections']])
        with self.assertRaises(S.GuardError):
            self.st.save(wiped)
        self.assertTrue(self.st.get(pr['id'])['sections'][0]['value'])        # kayitli veri yerinde
        self.st.save(wiped, force=True)
        self.assertFalse(self.st.get(pr['id'])['sections'][0]['value'])

    def test_revisions_cap_and_restore(self):
        pr = self.st.create('fs')
        for k in range(30):
            pr['sections'][0]['value'] = 'sürüm %d' % k
            pr = self.st.save(pr)
        revs = self.st.revisions(pr['id'])
        self.assertEqual(len(revs), S.REVISION_LIMIT)
        older = next(r for r in revs if r['filled'] == 1)
        back = self.st.restore_revision(pr['id'], revs[-1]['id'])
        self.assertTrue(back['sections'][0]['value'].startswith('sürüm'))
        self.assertTrue(older)

    def test_trash_delete_rules_and_duplicate(self):
        pr = self.st.create('sd', title='Depo raporu')
        with self.assertRaises(ValueError):
            self.st.delete_forever(pr['id'])
        dup = self.st.duplicate(pr['id'])
        self.assertEqual(dup['title'], 'Depo raporu (kopya)')
        self.st.set_status(pr['id'], 'trash')
        self.assertEqual([r['id'] for r in self.st.list('trash')], [pr['id']])
        self.st.delete_forever(pr['id'])
        self.assertEqual([r['id'] for r in self.st.list('all')], [dup['id']])
        with self.assertRaises(KeyError):
            self.st.get('../../etc/passwd')

    def test_docx_export_import_roundtrip(self):
        pr = self.st.create('pm', values={'OWNERCOMPANY': 'Gürsa Oluklu', 'EVALUATION_START_DATE': '2026-10-12'})
        for s in pr['sections'][:10]:
            s['value'] = 'Madde %s için yazılan metin.' % s['clause']
        pr['meta']['na_clauses'] = [{'clause_ref': '4.9', 'justification': 'Yok'}]
        pr['meta']['action_plan']['items'] = [{'type': 'minor', 'clause': '3.1.1', 'nc_text': 'Kayıt eksik', 'correction': 'Tamam'}]
        pr = self.st.save(pr)
        out = pathlib.Path(self.tmp) / 'out.docx'
        self.st.export_docx(pr['id'], str(out))
        imp = self.st.import_docx(str(out))
        self.assertEqual(imp['profile'], 'pm')
        self.assertEqual(imp['company'], 'Gürsa Oluklu')
        self.assertEqual(imp['title'], 'Gürsa Oluklu PM Audit Report')
        got = {s['clause']: s['value'] for s in imp['sections'] if s['value']}
        want = {s['clause']: s['value'] for s in pr['sections'][:10]}
        self.assertEqual({k: got.get(k) for k in want}, want)
        # sablonun kendi on-dolu kutulari (P703 bolum 7: 'Not applicable') okunur, uydurma metin eklenmez
        self.assertEqual({v for k, v in got.items() if k not in want}, {'Not applicable'})
        self.assertEqual(imp['meta']['na_clauses'], [{'clause_ref': '4.9', 'justification': 'Yok'}])
        self.assertEqual(imp['meta']['action_plan']['items'][0]['nc_text'], 'Kayıt eksik')

    def test_scan_preview_and_check(self):
        pr = self.st.create('fs')
        pr['sections'][3]['value'] = 'Gözlem.\nMinor NC 3.4.2: iç denetim planı güncel değil.\nNormal satır.'
        items = S.scan_action_plan(pr)
        self.assertEqual([(i['clause'], i['type']) for i in items], [('3.4.2', 'minor')])
        txt = S.preview_text(pr)
        self.assertIn('== DETAILED REPORT ==', txt)
        chk = S.export_check(pr)
        self.assertEqual(chk['units_filled'], 1)
        self.assertEqual(chk['units_total'], len(B.sections_for_profile('fs')))


if __name__ == '__main__':
    unittest.main()
