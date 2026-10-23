# -*- coding: utf-8 -*-
"""BRCGS resmi sablon motoru: 5 sablonun hepsinde yaz -> oku gidis-donusu (kayip 0, bozuk 0), tuzak metin,
sablonun dokunulmayan parcalarinin bayt bayt korunmasi, Word uyumlulugu (yer tutucu bayragi, tarih, ad alanlari)."""
import io
import pathlib
import re
import sys
import unittest
import zipfile

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))

try:
    from lxml import etree  # noqa: F401
    HAVE_LXML = True
except ImportError:  # pragma: no cover
    HAVE_LXML = False

if HAVE_LXML:
    from agfo_brcgs import boxes as B
    from agfo_brcgs import data
    from agfo_brcgs import docx_engine as E

TRAP = '3.2 numaralı prosedür incelendi.\n1.1 maddesi gereği kayıtlar tutuluyor.'


def build_project(profile, tpl):
    values = {}
    fields = E.scan_fields(tpl, profile)
    counts = {}
    for f in fields:
        counts[f['key']] = f['repeats']
    expect = {}
    for f in fields:
        if f['kind'] == 'date':
            v = '2026-10-%02d' % (10 + f['occurrence'])
        elif f['kind'] in ('dropDownList', 'comboBox') and f['items']:
            real = [i for i in f['items'] if not i['prompt']]
            v = real[min(f['occurrence'], len(real) - 1)]['text'] if real else 'X'
        else:
            v = 'V_%s_%d ğüşİçö & <x>' % (f['key'], f['occurrence'])
        if counts[f['key']] > 1:
            values.setdefault(f['key'], [''] * counts[f['key']])[f['occurrence']] = v
        else:
            values[f['key']] = v
        expect[(f['key'], f['occurrence'])] = v
    plain = {f['key']: 'P_%s Örnek Sok. No:5 & <x>' % f['key'] for f in E.plain_fields(tpl)}
    values.update(plain)
    sections = B.sections_for_profile(profile)
    for k, s in enumerate(sections):
        s['value'] = 'Metin %s satır bir.\n%s\nSon satır %d.' % (s['clause'], TRAP if k % 3 == 0 else 'Ara satır.', k)
    chapters = sorted({B.chapter_of(u['key']) for u in B.units(profile)}, key=lambda c: int(c) if c.isdigit() else 99)
    na = [{'clause_ref': '%s.9' % chapters[0], 'justification': 'Uygulanmaz: ürün yok'},
          {'clause_ref': '%s.8' % chapters[1], 'justification': 'Tesiste bu süreç yok'}]
    tables = {}
    for kind, (_tbl, cols) in E.official_tables(tpl).items():
        tables[kind] = [{c: 'Ayşe Yılmaz %d-%d' % (r, k) for k, c in enumerate(cols)} for r in range(3)]
    for key, _t, _tbl, cols, _l in E.generic_tables(tpl):
        tables[key] = [{c: 'Konum %d-%d' % (r, k) for k, c in enumerate(cols)} for r in range(2)]
    items = [{'type': 'major', 'clause': '4.4.1', 'nc_text': 'Major NC: 4.4.1 Kapı aralığı', 'correction': 'Kapı onarıldı',
              'root_cause': 'Bakım planı eksik', 'proposed_preventive_action': 'Plan güncellendi', 'date_reviewed': '2026-10-20',
              'reviewed_by': 'C.G. Kara'},
             {'type': 'minor', 'clause': '3.2.1', 'nc_text': 'Doküman revizyonu işlenmemiş', 'correction': 'Revize edildi',
              'root_cause': 'Eğitim', 'proposed_preventive_action': 'Eğitim verildi', 'date_reviewed': '2026-10-21', 'reviewed_by': 'A'},
             {'type': 'minor', 'clause': '5.1.2', 'nc_text': 'Etiket kontrol kaydı eksik', 'correction': 'Kayıt tamamlandı',
              'root_cause': 'Vardiya devri', 'proposed_preventive_action': 'Kontrol listesi', 'date_reviewed': '2026-10-22', 'reviewed_by': 'B'}]
    return {'profile': profile, 'values': values, 'sections': sections, 'na_clauses': na, 'report_tables': tables,
            'action_plan': {'items': items}, '_plain': plain}, expect


@unittest.skipUnless(HAVE_LXML, 'lxml yok')
class BrcgsDocxRoundTrip(unittest.TestCase):
    maxDiff = None

    def _roundtrip(self, profile):
        tpl = E.DocxTemplate(data.template_path(profile))
        project, expect = build_project(profile, tpl)
        blob, stats = E.write_report(project)
        back = E.read_report(blob)
        return tpl, project, expect, blob, stats, back

    def test_all_profiles_roundtrip(self):
        for p in data.PROFILES:
            with self.subTest(profile=p):
                tpl, project, expect, blob, stats, back = self._roundtrip(p)
                self.assertEqual(back['profile'], p)
                # alanlar
                got_fields = E.scan_fields(E.DocxTemplate(blob), p)
                lost = []
                for f in got_fields:
                    want = expect.get((f['key'], f['occurrence']))
                    if want is None:
                        continue
                    if f['kind'] == 'date':
                        d = E.parse_date(want)
                        ok = E.format_date(d, f['date_format']) == f['value']
                    else:
                        ok = E.normalize_text(want) == f['value']
                    if not ok:
                        lost.append((f['key'], f['occurrence'], want, f['value']))
                self.assertEqual(lost, [], 'alan kaybı')
                # denetimsiz etiketli hucreler (Company name / Site name / Address / Country)
                self.assertTrue(project['_plain'])
                self.assertEqual({k: back['values'].get(k) for k in project['_plain']}, project['_plain'])
                self.assertEqual({f['key']: f['value'] for f in E.plain_fields(E.DocxTemplate(blob))}, project['_plain'])
                self.assertEqual(len(got_fields), len(expect))
                # bolumler (kutusuz maddeler haric): kayip 0, bozuk 0
                want_sec = {s['clause']: s['value'] for s in project['sections']}
                got_sec = {s['clause']: s['value'] for s in back['sections']}
                unmapped = set(B.unmapped_clauses(p)) | set(stats['skipped'])
                bad = [(c, want_sec[c][:40], got_sec.get(c, '<yok>')[:40]) for c in want_sec
                       if c not in unmapped and got_sec.get(c) != want_sec[c]]
                self.assertEqual(bad, [], 'bölüm kaybı/bozulma')
                # NA maddeleri
                self.assertEqual(sorted((n['clause_ref'], n['justification']) for n in back['na_clauses']),
                                 sorted((n['clause_ref'], n['justification']) for n in project['na_clauses']))
                # resmi tablolar
                for kind, rows in project['report_tables'].items():
                    self.assertEqual(back['report_tables'].get(kind), rows, kind)
                # eylem plani
                majors = [a for a in back['action_plan']['items'] if a['type'] == 'major']
                minors = [a for a in back['action_plan']['items'] if a['type'] == 'minor']
                self.assertEqual([(a['clause'], a['nc_text'], a['correction']) for a in majors],
                                 [('4.4.1', 'Kapı aralığı', 'Kapı onarıldı')])
                self.assertEqual([a['clause'] for a in minors], ['3.2.1', '5.1.2'])

    def test_untouched_parts_are_byte_identical_and_word_markers(self):
        for p in data.PROFILES:
            with self.subTest(profile=p):
                tpl, project, expect, blob, stats, back = self._roundtrip(p)
                src = zipfile.ZipFile(data.template_path(p))
                out = zipfile.ZipFile(io.BytesIO(blob))
                self.assertEqual(src.namelist(), out.namelist())
                for name in src.namelist():
                    if name == 'word/document.xml':
                        continue
                    self.assertEqual(src.read(name), out.read(name), name)
                doc = out.read('word/document.xml').decode('utf-8')
                head_src = src.read('word/document.xml').decode('utf-8')[:3000]
                root_tag = re.search(r'<w:document[^>]*>', head_src).group(0)
                self.assertIn(root_tag, doc)                                  # tum ad alani bildirimleri ve mc:Ignorable aynen
                self.assertTrue(doc.startswith('<?xml version'))
                # doldurulan alanlarda yer tutucu bayragi kalmamali
                t2 = E.DocxTemplate(blob)
                for _n, sdt in t2.all_sdts():
                    pr = E.sdt_props(sdt)
                    if pr['tag'] in ('OWNERCOMPANY', 'BRC_SITE_CODE') and pr['placeholder_showing']:
                        self.fail('yer tutucu bayrağı kaldı: %s' % pr['tag'])
                    if pr['kind'] == 'date' and not pr['placeholder_showing']:
                        el = sdt.find(E.w('sdtPr')).find(E.w('date'))
                        self.assertRegex(el.get(E.w('fullDate')) or '', r'^2026-10-\d\dT00:00:00Z$')

    def test_trap_text_never_splits_and_empty_project_keeps_template(self):
        p = 'fs'
        secs = B.sections_for_profile(p)
        for s in secs:
            if s['clause'] in ('3.1', '3.2', '3.3'):
                s['value'] = 'Gövde %s.\n3.2 numaralı prosedür incelendi.\n3.3 Kayıtlar düzgün.' % s['clause']
        merged = B.merge_for_export(p, secs)
        f31 = next(r for r in merged['rows'] if r['tag'] == 'F3_1')
        self.assertEqual(f31['merged_from'], ['3.1', '3.2', '3.3'])
        split = {r['clause']: r['value'] for r in B.split_import(p, [{'tag': 'F3_1', 'value': f31['value']}])}
        for c in ('3.1', '3.2', '3.3'):
            self.assertEqual(split[c], 'Gövde %s.\n3.2 numaralı prosedür incelendi.\n3.3 Kayıtlar düzgün.' % c)
        # baslik yoksa metin bolunmez, ilk birime gider
        whole = B.split_import(p, [{'tag': 'F3_1', 'value': 'Başlıksız metin\n3.2 numaralı prosedür'}])
        self.assertEqual([(r['clause'], r['value']) for r in whole], [('3.1', 'Başlıksız metin\n3.2 numaralı prosedür')])
        # bos proje: belge degismez
        blob, _st = E.write_report({'profile': p, 'values': {}, 'sections': B.sections_for_profile(p)})
        self.assertEqual(zipfile.ZipFile(io.BytesIO(blob)).read('word/document.xml'),
                         zipfile.ZipFile(data.template_path(p)).read('word/document.xml'))

    def test_template_profile_detection_and_scan_labels(self):
        for p in data.PROFILES:
            tpl = E.DocxTemplate(data.template_path(p))
            self.assertEqual(E.detect_profile(tpl), p)
            fields = E.scan_fields(tpl, p)
            self.assertGreater(len(fields), 60)
            self.assertFalse([f for f in fields if E._PH_ANY.search(f['label']) or not f['label'].strip()])
            keys = {f['key'] for f in fields}
            self.assertFalse([k for k in keys if k.startswith('ADDITIONAL_MODULES_TABLE_')], 'başlık etiketleri alan sayılmamalı')
            self.assertFalse(keys & B.detail_tags(p), 'detaylı rapor kutuları form alanı olmamalı')

    def test_every_box_written_with_long_multiparagraph_text(self):
        # 2.2.1: kutuya 'Root cause analysis ...' yazilinca ayni tablo NC ozet tablosu sanilip sonraki kutular yazilmiyordu
        # (gercek FS raporunda 3.7'den sonra 3.8-3.11 bos kaliyordu). NC tablolari artik bundled sablonun yapisindan belirlenir.
        para = ('Corrective action request form FRM.021 was checked. Root cause analysis is done with 5 whys; proposed preventive '
                'action plan reviewed. Clause/section ref and justification recorded.')
        for p in data.PROFILES:
            with self.subTest(profile=p):
                secs = B.sections_for_profile(p)
                for s in secs:
                    # gercek raporlardaki gibi bos satirlarla ayrilmis paragraflar (hata yalniz bu bicimde tetikleniyordu)
                    s['value'] = '\n'.join(('%s %s line %d' % (s['clause'], para, k)) if k % 3 != 1 else '' for k in range(14))
                blob, st = E.write_report({'profile': p, 'values': {}, 'sections': secs})
                want = {r['tag'] for r in B.merge_for_export(p, secs)['rows']}
                missed = [E.sdt_props(x)['tag'] for _n, x in E.DocxTemplate(blob).all_sdts()
                          if E.sdt_props(x)['tag'] in want and E.sdt_props(x)['placeholder_showing']]
                self.assertEqual(missed, [])

    def test_section_skeleton_matches_box_spec(self):
        expected_units = {'fs': 94, 'pm': 76, 'cp': 46, 'sd': 156, 'ab': 29}          # docs/report-box-specification.md
        for p, n in expected_units.items():
            secs = B.sections_for_profile(p)
            self.assertEqual(len(secs), n, p)
            self.assertEqual([s['clause'] for s in secs], [s['clause'] for s in B.sort_sections([dict(x) for x in secs])])


if __name__ == '__main__':
    unittest.main()
