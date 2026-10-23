# -*- coding: utf-8 -*-
"""Bolum bazinda NC/NA, tarama ve sayim, DOCX kapanis satirlari, NC sayac alanlari, Ingilizce kilavuz metinleri."""
import pathlib
import sys
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
    from agfo_brcgs import data as D
    from agfo_brcgs import docx_engine as E
    from agfo_brcgs import findings as F
    from agfo_brcgs import guide as G
    from agfo_brcgs import i18n


def project(profile='cp'):
    return {'profile': profile, 'values': {}, 'sections': B.sections_for_profile(profile),
            'meta': {'na_clauses': [], 'action_plan': {'items': []}, 'report_tables': {}}}


@unittest.skipUnless(HAVE_LXML, 'lxml yok')
class FindingsTests(unittest.TestCase):
    def test_scan_real_report_format(self):
        pr = project()
        sec = {s['clause']: s for s in pr['sections']}
        sec['2.2']['value'] = ('Risk değerlendirmesi incelendi. Minor NC 2.2.2 : Yanlış kullanım tedbirleri yazılmamış.\n'
                               'İç denetimlerde toplam üç uygunsuzluk kaydedilmiştir.\n'
                               'The 10 minor non-conformities raised at last year’s audit have been resolved.')
        sec['3.4']['value'] = ('Plan was seen.Minor NC Ref. 3.4.1: Programme not risk based.\n'
                               'Major non-conformity 3.4.2 - Audits overdue. Critical NC 3.4.3: No records')
        res = F.scan(pr)
        self.assertEqual([(i['type'], i['clause'], i['section'], i['nc_text']) for i in res['added']],
                         [('minor', '2.2.2', '2.2', 'Yanlış kullanım tedbirleri yazılmamış.'),
                          ('minor', '3.4.1', '3.4', 'Programme not risk based.'),
                          ('major', '3.4.2', '3.4', 'Audits overdue.'),
                          ('critical', '3.4.3', '3.4', 'No records')])
        self.assertEqual(F.scan(pr)['existing'], 4)                     # ikinci tarama cogaltmaz
        c = F.counts(pr)
        self.assertEqual((c['critical'], c['major'], c['minor'], c['total']), (1, 1, 2, 4))
        self.assertEqual(F.count_text(c, 'cp'), 'Critical 1 · Major 1 · Minor 2 · Fundamental 0 · NA 0')

    def test_box_paragraphs_import_as_lines(self):
        from lxml import etree
        ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
        sdt = etree.fromstring('<w:sdt xmlns:w="%s"><w:sdtContent><w:p><w:r><w:t>First paragraph.</w:t></w:r></w:p>'
                               '<w:p><w:r><w:t>Second</w:t><w:br/><w:t>line.</w:t></w:r></w:p></w:sdtContent></w:sdt>' % ns)
        self.assertEqual(E.sdt_text(sdt), 'First paragraph.\nSecond\nline.')

    def test_section_membership_longest_prefix(self):
        secs = [{'clause': '3.5'}, {'clause': '3.5.1'}, {'clause': '3.10'}]
        self.assertEqual(F.section_for_clause(secs, '3.5.1.2'), '3.5.1')
        self.assertEqual(F.section_for_clause(secs, '3.5.2'), '3.5')
        self.assertEqual(F.section_for_clause(secs, '3.1'), None)         # 3.10 ile karismaz
        self.assertEqual(F.section_for_clause(secs, '3.10.4'), '3.10')

    def test_closing_lines(self):
        pr = project()
        sec = {s['clause']: s for s in pr['sections']}
        sec['1.1']['value'] = 'The site has a policy.'
        sec['2.4']['value'] = 'Supplier approval was reviewed.'
        sec['4.9']['value'] = ''
        pr['meta']['action_plan']['items'] = [{'type': 'minor', 'clause': '2.4.1', 'nc_text': 'Score above maximum.'}]
        pr['meta']['na_clauses'] = [{'clause_ref': '4.9.2', 'justification': 'No own vehicles'},
                                    {'clause_ref': '5.3', 'justification': 'No product samples are retained.'}]
        self.assertEqual(F.closing_lines(pr, sec['1.1']), [])                       # sabit 'NC yok' cumlesi yok
        self.assertEqual(F.closing_lines(pr, sec['2.4']), ['Minor NC Ref. 2.4.1: Score above maximum.'])
        self.assertEqual(F.closing_lines(pr, sec['4.9']), [])                       # alt madde NA: yalniz NA tablosu
        self.assertEqual(F.closing_lines(pr, sec['5.3']), ['N/A: No product samples are retained.'])
        self.assertEqual(F.with_closing(pr, sec['2.4']), 'Supplier approval was reviewed.\nMinor NC Ref. 2.4.1: Score above maximum.')
        # metinde zaten varsa eklenmez (eski bicim de taninir)
        sec['2.4']['value'] += '\nMinor NC 2.4.1: Score above maximum.'
        self.assertEqual(F.closing_lines(pr, sec['2.4']), [])

    def test_count_fields_written_to_docx(self):
        pr = project('cp')
        pr['sections'][0]['value'] = 'x'
        pr['meta']['action_plan']['items'] = [{'type': 'minor', 'clause': '1.1.2', 'nc_text': 'a'},
                                              {'type': 'minor', 'clause': '2.2.1', 'nc_text': 'b'},
                                              {'type': 'major', 'clause': '3.4.1', 'nc_text': 'c'}]
        from agfo_brcgs import store as S
        payload = S.Store.export_payload(pr)
        self.assertEqual({k: payload['values'][k] for k in ('CRITICAL', 'MAJOR', 'MINOR', 'FUNDAMENTAL')},
                         {'CRITICAL': '0', 'MAJOR': '1', 'MINOR': '2', 'FUNDAMENTAL': '0'})
        blob, _st = E.write_report(payload)
        vals = {f['key']: f['value'] for f in E.scan_fields(E.DocxTemplate(blob), 'cp')}
        self.assertEqual((vals['MAJOR'], vals['MINOR']), ('1', '2'))
        # AB sablonunda Fundamental sayaci yok: degerlere eklenmez
        self.assertNotIn('FUNDAMENTAL', S.Store.export_payload(project('ab'))['values'])
        self.assertEqual(S.Store.export_payload(project('ab'))['values']['MINOR'], '0')

    def test_guide_is_english_and_keys_unchanged(self):
        import re
        tr = re.compile('[çğıöşüÇĞİÖŞÜ]')
        bad = []
        for p in D.PROFILES:
            for s in B.sections_for_profile(p):
                f = G.form_for(p, s['clause'])
                for fd in f['fields']:
                    for txt in [G.label_of(fd), i18n.guide(fd.get('hint') or '')] + \
                               [i18n.guide(G.option_label(o)) for o in fd.get('options') or []]:
                        if tr.search(txt):
                            bad.append((p, s['clause'], txt[:60]))
                for d in (f.get('rule') or {}).get('should_not_include') or []:
                    if tr.search(i18n.guide(d)):
                        bad.append((p, s['clause'], d[:60]))
        self.assertEqual(bad, [])
        # anahtarlar Turkce veriden turer; Excel sablonlarindaki anahtarlar hala cozulur
        f = G.form_for('pm', '3.2')
        self.assertTrue(f['fields'][0]['key'])

    def test_report_text_override_and_stale(self):
        row = dict(B.sections_for_profile('pm')[0])
        k = G.form_for('pm', row['clause'])['fields'][0]['key']
        G.set_answer('pm', row, k, 'Politika görüldü')
        self.assertIn('Politika görüldü', row['value'])
        G.set_report_text('pm', row, 'The policy was reviewed.')
        self.assertEqual(row['value'], 'The policy was reviewed.')
        G.set_answer('pm', row, k, 'Politika görüldü, imzalı')
        self.assertEqual(row['value'], 'The policy was reviewed.')        # Ingilizce metin korunur
        self.assertTrue(row['flags']['report_stale'])
        G.set_report_text('pm', row, '')
        self.assertIn('Politika görüldü, imzalı', row['value'])           # bosaltinca kutulardan kurulan metne doner


if __name__ == '__main__':
    unittest.main()
