# -*- coding: utf-8 -*-
"""agfo_brcgs.xlsx_reader testleri: Report Studio 5.2.1 class-xlsx-reader.php + editor.js ice aktarma.

* 5 paketli sablon okunur; kopyalarda yanit hucreleri sayfa XML'i duzenlenerek doldurulur (inlineStr,
  paylasilan metin, zengin metin + fonetik, sayi, mantiksal, _x000D_/CRLF), yeniden okunur ve degerler
  madde/alan anahtarina gore dogrulanir.
* PHP varsa (ve eklenti kaynagi bulunursa) ORIJINAL class-xlsx-reader.php ayni dosyalarda calistirilir ve
  ciktisi Python ile birebir karsilastirilir.
* merge_excel_answers / plan / apply: profil uyusmazligi engeli, bos-doldur vs uzerine-yaz, cakisma sayimi,
  etiketle eslesme, _legacy, _note/_finding, Modul 13 otomatik ekleme.
"""
import copy
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from xml.sax.saxutils import escape

SRC = pathlib.Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))

from agfo_brcgs import coverage as cov  # noqa: E402
from agfo_brcgs import xlsx_reader as xr  # noqa: E402

EXCEL = cov.data_dir() / 'excel'
TEMPLATES = {p: EXCEL / ('AGFO_BRCGS_%s_Rapor_Sablonu.xlsx' % p.upper()) for p in ('fs', 'pm', 'cp', 'ab', 'sd')}
PHP = shutil.which('php')
PLUGIN_DIR = pathlib.Path(os.environ.get(
    'AGFO_BRS_PLUGIN_DIR',
    '/tmp/claude-0/-home-claude/362ddb9d-524b-53b3-91b7-2fdfa939e92b/scratchpad/rs/agfo-brcgs-report-studio'))
READER_PHP = PLUGIN_DIR / 'includes' / 'class-xlsx-reader.php'

PHP_HARNESS = r"""<?php
define('ABSPATH', '/');
class WP_Error { public $c; public $m; function __construct($c, $m) { $this->c = $c; $this->m = $m; } }
function is_wp_error($x) { return $x instanceof WP_Error; }
function sanitize_key($k) { $k = strtolower($k); return preg_replace('/[^a-z0-9_\-]/', '', $k); }
require $argv[1];
$out = array();
foreach (array_slice($argv, 2) as $f) {
    $r = AGFO_BRS_Xlsx_Reader::parse($f);
    $out[] = is_wp_error($r) ? array('error' => $r->c, 'message' => $r->m) : $r;
}
echo json_encode($out, JSON_UNESCAPED_UNICODE);
"""

SHEET_RAPOR = 'xl/worksheets/sheet3.xml'


# ---------------------------------------------------------------------------
# XLSX duzenleme yardimcilari
# ---------------------------------------------------------------------------

def rewrite(src, dst, transform=None, extra=None, drop=()):
    """ZIP'i kopyalar; transform(name, bytes) -> bytes ile parcalari degistirir, extra ekler."""
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            if info.filename in drop:
                continue
            data = zin.read(info.filename)
            if transform:
                data = transform(info.filename, data)
            zout.writestr(info.filename, data)
        for name, data in (extra or {}).items():
            zout.writestr(name, data)
    return dst


def set_cell(xml: str, ref: str, body: str, typ: str) -> str:
    """ref hucresini verilen tip ve govdeyle degistirir (hucre yoksa hata)."""
    rx = re.compile(r'<c r="%s"(?: [^>]*?)?(?:/>|>.*?</c>)' % re.escape(ref), re.S)
    assert rx.search(xml), ref
    t = (' t="%s"' % typ) if typ else ''
    return rx.sub(lambda m: '<c r="%s"%s>%s</c>' % (ref, t, body), xml, count=1)


def inline(text):
    return '<is><t xml:space="preserve">%s</t></is>' % escape(text)


def rapor_rows(path):
    """Rapor sayfasi: {(madde, anahtar): satir no} ve satirlar."""
    with zipfile.ZipFile(path) as zf:
        sheets = xr._sheet_paths(zf)
        cells = xr._read_sheet(zf, sheets['Rapor'], xr._shared_strings(zf))
    index = {}
    for r, row in cells.items():
        if r > 1 and row.get('G'):
            index.setdefault((row.get('A', ''), row['G']), r)
    return index, cells


SST = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
       '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="3" uniqueCount="3">'
       '<si><t>Paylaşılan yanıt</t></si>'
       '<si><r><rPr><b/></rPr><t xml:space="preserve">Zengin </t></r><r><t>metin</t></r>'
       '<rPh sb="0" eb="1"><t>FONETIK</t></rPh></si>'
       '<si><t>  boşluklu  </t></si>'
       '</sst>')


def make_filled(tmpdir, profile, fills, extra_cells=None):
    """fills: [(madde, anahtar, ('inline'|'s'|'n'|'b', deger))] -> doldurulmus kopya yolu."""
    src = TEMPLATES[profile]
    index, _ = rapor_rows(src)
    dst = pathlib.Path(tmpdir) / ('%s_filled_%d.xlsx' % (profile, len(list(pathlib.Path(tmpdir).iterdir()))))

    def tf(name, data):
        if name != SHEET_RAPOR:
            return data
        xml = data.decode('utf-8')
        for clause, key, (kind, val) in fills:
            ref = 'F%d' % index[(clause, key)]
            if kind == 'inline':
                xml = set_cell(xml, ref, inline(val), 'inlineStr')
            elif kind == 's':
                xml = set_cell(xml, ref, '<v>%d</v>' % val, 's')
            elif kind == 'n':
                xml = set_cell(xml, ref, '<v>%s</v>' % val, 'n')
            elif kind == 'b':
                xml = set_cell(xml, ref, '<v>%s</v>' % val, 'b')
        for ref, body, typ in extra_cells or []:
            xml = set_cell(xml, ref, body, typ)
        return xml.encode('utf-8')

    return rewrite(src, dst, tf, extra={'xl/sharedStrings.xml': SST})


def first_field_keys(profile, n):
    """Sablondaki ilk n alan satiri (madde, anahtar, etiket)."""
    _, cells = rapor_rows(TEMPLATES[profile])
    out = []
    for r, row in cells.items():
        k = row.get('G', '')
        if r > 1 and k and not k.startswith('_'):
            out.append((row['A'], k, row.get('D', '')))
        if len(out) >= n:
            break
    return out


# ---------------------------------------------------------------------------
# Testler: okuyucu
# ---------------------------------------------------------------------------

class TemplateParse(unittest.TestCase):
    def test_empty_templates(self):
        for p, path in TEMPLATES.items():
            r = xr.parse(path)
            self.assertEqual(r['schema'], 'AGFO-BRS-XLSX', p)
            self.assertEqual(r['schema_version'], '1')
            self.assertEqual(r['profile'], p)
            self.assertEqual(r['plugin_version'], '5.1.0')
            self.assertEqual(r['rows'], [])
            self.assertEqual(r['meta'], {})
            self.assertEqual(r['skipped_rows'], 0)

    def test_template_keys_match_editor_forms(self):
        """Sablondaki her alan anahtari editorun form alanlarindan biri (guideKey/curated uyumu)."""
        for p, path in TEMPLATES.items():
            _, cells = rapor_rows(path)
            for r, row in cells.items():
                k = row.get('G', '')
                if r == 1 or not k or k.startswith('_'):
                    continue
                d = cov.form_for(p, row['A'])
                self.assertTrue(d and any(f['key'] == k for f in d['fields']), (p, row['A'], k))


class FilledParse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='agfo-brs-xlsx-')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_values_per_clause_and_key(self):
        for p in TEMPLATES:
            f = first_field_keys(p, 6)
            fills = [
                (f[0][0], f[0][1], ('inline', 'Politika 2025-01-10 tarihinde imzalanmış.')),
                (f[1][0], f[1][1], ('s', 0)),
                (f[2][0], f[2][1], ('s', 1)),
                (f[3][0], f[3][1], ('n', '42')),
                (f[4][0], f[4][1], ('b', '1')),
                (f[5][0], f[5][1], ('inline', '  Satır 1\r\nSatır 2_x000D_\rSon  ')),
                (f[0][0], '_note', ('inline', 'Kanıt notu')),
                (f[0][0], '_finding', ('inline', 'Minor NC 1.1.1 - örnek')),
            ]
            path = make_filled(self.tmp, p, fills)
            r = xr.parse(path)
            got = {(x['clause'], x['key']): x['value'] for x in r['rows']}
            self.assertEqual(got, {
                (f[0][0], f[0][1]): 'Politika 2025-01-10 tarihinde imzalanmış.',
                (f[1][0], f[1][1]): 'Paylaşılan yanıt',
                (f[2][0], f[2][1]): 'Zengin metin',
                (f[3][0], f[3][1]): '42',
                (f[4][0], f[4][1]): 'TRUE',
                (f[5][0], f[5][1]): 'Satır 1\nSatır 2\nSon',
                (f[0][0], '_note'): 'Kanıt notu',
                (f[0][0], '_finding'): 'Minor NC 1.1.1 - örnek',
            }, p)
            row0 = next(x for x in r['rows'] if x['key'] == f[0][1])
            self.assertEqual(row0['sheet'], 'Rapor')
            self.assertEqual(row0['label'], f[0][2])
            self.assertIsInstance(row0['row'], int)

    def test_skipped_rows_meta_and_module_sheet(self):
        f = first_field_keys('fs', 1)[0]
        index, _ = rapor_rows(TEMPLATES['fs'])
        r_no = index[(f[0], f[1])]

        def tf(name, data):
            xml = data.decode('utf-8')
            if name == SHEET_RAPOR:
                xml = set_cell(xml, 'F%d' % r_no, inline('madde yok'), 'inlineStr')
                xml = set_cell(xml, 'A%d' % r_no, inline('   '), 'inlineStr')  # bos madde -> skipped
            if name == 'xl/worksheets/sheet1.xml':  # Talimat: denetim bilgileri
                xml = set_cell(xml, 'C15', inline(' ACME A.Ş. '), 'inlineStr')
                xml = set_cell(xml, 'C17', '<v>46000</v>', '')
            if name == 'xl/worksheets/sheet4.xml':  # Modul 13 sayfasinda bir yanit
                rows = re.findall(r'<row r="(\d+)"[^>]*>(.*?)</row>', xml, re.S)
                for rn, body in rows:
                    if '13.1.1' in body and 'inlineStr' in body and int(rn) > 1 and '_clause' not in body \
                            and '_note' not in body and '_finding' not in body:
                        xml = set_cell(xml, 'F%s' % rn, inline('Aydınlatma yeterli'), 'inlineStr')
                        break
            return xml.encode('utf-8')

        path = rewrite(TEMPLATES['fs'], pathlib.Path(self.tmp) / 'fs_meta.xlsx', tf)
        r = xr.parse(path)
        self.assertEqual(r['skipped_rows'], 1)
        self.assertEqual(r['meta'], {'Firma': 'ACME A.Ş.', 'Denetim tarihi': '46000'})
        mod = [x for x in r['rows'] if x['sheet'] == 'Modül 13 FSMA']
        self.assertEqual(len(mod), 1)
        self.assertEqual((mod[0]['clause'], mod[0]['value']), ('13.1.1', 'Aydınlatma yeterli'))

    def test_errors(self):
        bad = pathlib.Path(self.tmp) / 'bad.xlsx'
        bad.write_bytes(b'not a zip')
        with self.assertRaises(xr.XlsxError) as e:
            xr.parse(bad)
        self.assertEqual(e.exception.code, 'agfo_brs_xlsx_open')

        no_rapor = rewrite(TEMPLATES['pm'], pathlib.Path(self.tmp) / 'norapor.xlsx',
                           lambda n, d: d.replace(b'name="Rapor"', b'name="Rapor2"') if n == 'xl/workbook.xml' else d)
        with self.assertRaises(xr.XlsxError) as e:
            xr.parse(no_rapor)
        self.assertEqual(e.exception.code, 'agfo_brs_xlsx_sheet')

        dtd = rewrite(TEMPLATES['pm'], pathlib.Path(self.tmp) / 'dtd.xlsx',
                      lambda n, d: b'<!DOCTYPE x>' + d if n == SHEET_RAPOR else d)
        with self.assertRaises(xr.XlsxError) as e:
            xr.parse(dtd)
        self.assertEqual(e.exception.code, 'agfo_brs_xlsx_dtd')

        no_wb = rewrite(TEMPLATES['pm'], pathlib.Path(self.tmp) / 'nowb.xlsx', drop=('xl/workbook.xml',))
        with self.assertRaises(xr.XlsxError) as e:
            xr.parse(no_wb)
        self.assertEqual(e.exception.code, 'agfo_brs_xlsx_wb')

        no_header = rewrite(TEMPLATES['pm'], pathlib.Path(self.tmp) / 'nohdr.xlsx',
                            lambda n, d: d.replace('Alan anahtar&#305;'.encode(), b'X') if n == SHEET_RAPOR else d)
        with self.assertRaises(xr.XlsxError) as e:
            xr.parse(no_header)
        self.assertEqual(e.exception.code, 'agfo_brs_xlsx_header')

        with self.assertRaises(xr.XlsxError) as e:
            xr.parse_upload(TEMPLATES['pm'], 'rapor.xls')
        self.assertEqual(e.exception.code, 'agfo_brs_xlsx_ext')
        self.assertEqual(xr.parse_upload(TEMPLATES['pm'])['file_name'], TEMPLATES['pm'].name)

    def test_helpers(self):
        for n in (1, 26, 27, 52, 702, 703, 16384):
            self.assertEqual(xr.col_index(xr.col_letters(n)), n)
        self.assertEqual(xr.col_letters(28), 'AB')
        self.assertEqual([xr.php_intval(s) for s in ('12', ' 7', '12abc', '1e3', '3.9', 'abc', '', '-4')],
                         [12, 7, 12, 1000, 3, 0, 0, -4])
        self.assertEqual(xr.sanitize_key(' F-S_9!İ'), 'f-s_9')
        self.assertEqual(xr.php_trim('\xa0 a \n'), '\xa0 a')

    def test_cells_without_refs(self):
        """r niteligi olmayan satir/hucreler: PHP'deki gibi sirayla numaralanir."""
        def tf(name, data):
            if name != SHEET_RAPOR:
                return data
            xml = data.decode('utf-8')
            row = ('<row><c t="inlineStr">%s</c><c/><c/><c/><c/><c t="inlineStr">%s</c><c t="inlineStr">%s</c></row>'
                   % (inline('9.9'), inline('cevap'), inline('ozel')))
            return xml.replace('</sheetData>', row + '</sheetData>').encode('utf-8')
        path = rewrite(TEMPLATES['ab'], pathlib.Path(self.tmp) / 'noref.xlsx', tf)
        r = xr.parse(path)
        self.assertEqual([(x['clause'], x['key'], x['value']) for x in r['rows']], [('9.9', 'ozel', 'cevap')])


@unittest.skipUnless(PHP and READER_PHP.is_file(), 'php veya orijinal class-xlsx-reader.php yok')
class PhpParity(unittest.TestCase):
    def test_same_output_as_php(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix='agfo-brs-xlsx-php-'))
        try:
            files = [str(p) for p in TEMPLATES.values()]
            for p in TEMPLATES:
                f = first_field_keys(p, 4)
                files.append(str(make_filled(tmp, p, [
                    (f[0][0], f[0][1], ('inline', 'Bir')), (f[1][0], f[1][1], ('s', 1)),
                    (f[2][0], f[2][1], ('s', 2)), (f[3][0], f[3][1], ('inline', 'x\r\ny_x000D_')),
                    (f[0][0], '_note', ('inline', 'not')), (f[0][0], '_finding', ('n', '1.50'))])))
            bad = tmp / 'bad.xlsx'
            bad.write_bytes(b'xx')
            files.append(str(bad))
            files.append(str(rewrite(TEMPLATES['pm'], tmp / 'nr.xlsx', lambda n, d: d.replace(
                b'name="Rapor"', b'name="R"') if n == 'xl/workbook.xml' else d)))
            (tmp / 'h.php').write_text(PHP_HARNESS, 'utf-8')
            out = subprocess.run([PHP, str(tmp / 'h.php'), str(READER_PHP)] + files,
                                 capture_output=True, check=True).stdout
            php = json.loads(out)
            py = []
            for f in files:
                try:
                    py.append(cov.php_json_roundtrip(xr.parse(f)))
                except xr.XlsxError as e:
                    py.append({'error': e.code, 'message': e.message})
            self.assertEqual(py, php)
            self.assertGreaterEqual(sum(len(x.get('rows', [])) for x in py), 30)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Testler: editor.js ice aktarma birlestirmesi
# ---------------------------------------------------------------------------

def fs_fields(clause):
    return cov.form_for('fs', clause)['fields']


def project_fs():
    return {'profile': 'fs', 'section_findings': {}, 'detailed': [
        {'clause': '1.1', 'title': 'A', 'value': '', 'note': '', 'flags': {}},
        {'clause': '1.2', 'title': 'B', 'value': 'Eski serbest metin', 'note': 'mevcut not', 'flags': {}},
        {'clause': '2.1', 'title': 'C', 'value': '', 'note': '', 'flags': None},
    ]}


def xrow(clause, key, value, label=''):
    return {'sheet': 'Rapor', 'row': 2, 'clause': clause, 'key': key, 'label': label, 'value': value}


class Merge(unittest.TestCase):
    def test_profile_mismatch_blocks(self):
        proj = project_fs()
        new, res = xr.merge_excel_answers(proj, {'profile': 'pm', 'rows': [xrow('1.1', 'x', 'y')]})
        self.assertIn('PM standardı için hazırlanmış', res['error'])
        self.assertEqual(new, proj)
        _, res = xr.merge_excel_answers(proj, {'profile': 'fs', 'rows': []})
        self.assertIn('doldurulmuş yanıt bulunamadı', res['error'])
        # profil yoksa engel yok
        _, res = xr.merge_excel_answers(proj, {'profile': '', 'rows': [xrow('1.1', fs_fields('1.1')[0]['key'], 'v')]})
        self.assertNotIn('error', res)

    def test_fill_into_empty_and_assemble(self):
        f = fs_fields('1.1')
        proj = project_fs()
        parsed = {'profile': 'fs', 'rows': [xrow('1.1', f[1]['key'], 'İkinci'), xrow('1.1', f[0]['key'], 'Birinci')]}
        new, res = xr.merge_excel_answers(proj, parsed, 'fill')
        self.assertEqual(proj, project_fs())  # girdi degismedi
        self.assertEqual((res['written'], res['kept']), (2, 0))
        row = new['detailed'][0]
        self.assertEqual(row['flags']['struct'], {f[1]['key']: 'İkinci', f[0]['key']: 'Birinci'})
        self.assertEqual(row['value'], 'Birinci\n\nİkinci')  # kilavuz sirasi
        self.assertEqual(res['summary']['modes'], ['fill'])
        self.assertEqual(res['summary']['answers'], 2)

    def test_conflict_fill_vs_overwrite(self):
        f = fs_fields('1.1')
        proj = project_fs()
        proj['detailed'][0]['flags'] = {'struct': {f[0]['key']: 'Raporda var'}}
        parsed = {'profile': 'fs', 'rows': [xrow('1.1', f[0]['key'], 'Excel'), xrow('1.1', f[1]['key'], 'Yeni')]}
        plan = xr.plan_excel_import(copy.deepcopy(proj), parsed)
        self.assertEqual(plan['conflicts'], 1)
        new, res = xr.merge_excel_answers(proj, parsed, 'fill')
        self.assertEqual((res['written'], res['kept']), (1, 1))
        self.assertEqual(new['detailed'][0]['flags']['struct'][f[0]['key']], 'Raporda var')
        self.assertEqual(res['summary']['modes'], ['fill', 'overwrite'])
        new, res = xr.merge_excel_answers(proj, parsed, 'overwrite')
        self.assertEqual((res['written'], res['kept']), (2, 0))
        self.assertEqual(new['detailed'][0]['flags']['struct'][f[0]['key']], 'Excel')
        # ayni metin (bosluk farki) cakisma sayilmaz, yazim da olmaz
        proj['detailed'][0]['flags'] = {'struct': {f[0]['key']: 'Excel'}}
        plan = xr.plan_excel_import(copy.deepcopy(proj), {'profile': 'fs', 'rows': [xrow('1.1', f[0]['key'], ' Excel ')]})
        self.assertEqual(plan['conflicts'], 0)

    def test_label_fallback_legacy_note_finding(self):
        f = fs_fields('1.1')
        proj = project_fs()
        lab = f[2]['label'].upper().replace('I', 'I') + ' :'
        parsed = {'profile': 'fs', 'rows': [
            xrow('1.1', 'eski_anahtar', 'Etiketle', label=f[2]['label'] + '.'),
            xrow('1.2', 'yok', 'Kayıp soru yanıtı', label='Artık olmayan soru'),
            xrow('1.2', '_note', 'Excel notu'),
            xrow('1.1', '_finding', 'Minor NC'),
            xrow('9.9', 'x', 'atlanir'),
        ]}
        new, res = xr.merge_excel_answers(proj, parsed, 'fill')
        self.assertEqual(new['detailed'][0]['flags']['struct'][f[2]['key']], 'Etiketle')
        r12 = new['detailed'][1]
        self.assertEqual(r12['flags']['struct']['_legacy'], 'Eski serbest metin\n\nArtık olmayan soru: Kayıp soru yanıtı')
        self.assertEqual(r12['note'], 'mevcut not')  # fill: dolu not korunur
        self.assertEqual(new['section_findings'], {'1.1': 'Minor NC'})
        self.assertEqual(res['summary']['skipped_clauses'], ['9.9'])
        self.assertEqual(res['summary']['legacy'], 1)
        self.assertEqual(res['summary']['notes'], 2)
        self.assertEqual(res['summary']['conflicts'], 1)  # not farkli
        self.assertTrue(r12['value'].startswith('Eski serbest metin\n\nArtık olmayan soru'))
        # ikinci kez uygulamak eski metni cogaltmaz
        again, res2 = xr.merge_excel_answers(new, parsed, 'overwrite')
        self.assertEqual(again['detailed'][1]['flags']['struct']['_legacy'], r12['flags']['struct']['_legacy'])
        self.assertEqual(again['detailed'][1]['note'], 'Excel notu')
        self.assertEqual(xr.norm_label(lab), xr.norm_label(f[2]['label'].upper()))

    def test_module_13_added(self):
        proj = project_fs()
        units = xr.module_units('13', xr.box_map_for('fs'))
        self.assertEqual(len(units), 72)
        self.assertEqual(units[0], '13.1.1')
        d = cov.form_for('fs', '13.1.1')
        key = d['fields'][0]['key'] if d else 'k'
        new, res = xr.merge_excel_answers(proj, {'profile': 'fs', 'rows': [xrow('13.1.1', key, 'Aydınlatma yeterli')]})
        self.assertEqual(res['added_rows'], 72)
        self.assertEqual(len(new['detailed']), 3 + 72)
        clauses = [r['clause'] for r in new['detailed']]
        self.assertEqual(clauses[:4], ['1.1', '1.2', '2.1', '13.1.1'])
        self.assertEqual([r['sort_order'] for r in new['detailed']], list(range(75)))
        m = new['detailed'][3]
        self.assertEqual(m['flags']['unit_source'], 'module13')
        self.assertEqual(m['sdt_index'], 'box_fs_13_1_1')
        self.assertTrue(m['tag'].startswith('FSMAF'))
        self.assertIn('Aydınlatma yeterli', m['value'])
        self.assertEqual(res['summary']['add_modules'][0]['units'], 72)

    def test_end_to_end_from_filled_template(self):
        tmp = tempfile.mkdtemp(prefix='agfo-brs-e2e-')
        try:
            f = first_field_keys('pm', 3)
            path = make_filled(tmp, 'pm', [(c, k, ('inline', 'Yanıt %d' % i)) for i, (c, k, _) in enumerate(f)])
            parsed = xr.parse_upload(path)
            proj = {'profile': 'pm', 'section_findings': {},
                    'detailed': [{'clause': c, 'value': '', 'note': '', 'flags': {}} for c in sorted({x[0] for x in f})]}
            new, res = xr.merge_excel_answers(proj, parsed, 'fill')
            self.assertEqual(res['written'], 3)
            got = {}
            for r in new['detailed']:
                got.update(r['flags']['struct'])
            self.assertEqual(got, {k: 'Yanıt %d' % i for i, (_, k, _) in enumerate(f)})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_compare_and_norm_label(self):
        import functools
        keys = ['10.1', '2', '2.10', '2.9', '1.1.1', '1', 'x']
        self.assertEqual(sorted(keys[:-1], key=functools.cmp_to_key(xr.compare_clauses)),
                         ['1', '1.1.1', '2', '2.9', '2.10', '10.1'])
        self.assertEqual(xr.compare_clauses('x', '1'), 1)
        self.assertEqual(xr.compare_clauses('1', 'x'), 1)  # NaN: her iki yon 1 (orijinal)
        self.assertEqual(xr.norm_label('  İÇERİK   VE  Işık:. '), 'içerik ve ışık:.')
        self.assertEqual(xr.norm_label('Soru  metni ;'), 'soru metni')


if __name__ == '__main__':
    unittest.main()
