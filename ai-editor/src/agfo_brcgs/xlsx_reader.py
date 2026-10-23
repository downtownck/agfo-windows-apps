# -*- coding: utf-8 -*-
"""AGFO AI Editor - BRCGS cevrimdisi Excel formu okuyucu ve ice aktarma birlestirmesi, birebir port.

Kaynak: AGFO BRCGS Report Studio v5.2.1
  includes/class-xlsx-reader.php  AGFO_BRS_Xlsx_Reader::parse() / parse_upload()  -> parse() / parse_upload()
  includes/class-ajax.php         parse_xlsx(): sonucu oldugu gibi editore dondurur (yazma yok)
  assets/editor.js                planExcelImport / applyExcelImport / addModuleRows / makeModuleRow /
                                  compareClauses / normLabel  -> plan_excel_import / apply_excel_import /
                                  merge_excel_answers

Yalnizca standart kutuphane: .xlsx bir ZIP icindeki XML parcalaridir (zipfile + xml.etree).
PHP'nin WP_Error donusleri burada XlsxError istisnasidir (ayni kod + Turkce mesaj).

Birlestirme kurallari (editor.js):
  * Excel'in profili (marker 'profile') acik raporun profilinden farkliysa ice aktarma ENGELLENIR.
  * Dolu yanit yoksa ice aktarma engellenir.
  * Her yanit alt maddenin form alanina once 'Alan anahtari' ile, olmazsa normalize soru metniyle eslesir;
    eslesmezse '_legacy' (Onceden yazilmis metin) kutusuna "soru: yanit" olarak eklenir.
  * '_note' -> bolum kanit notu, '_finding' -> bolum bulgusu.
  * Raporda olmayan modul maddesi (FS Modul 13) yanitlanmissa modul rapora eklenir; diger
    raporda olmayan maddeler atlanir.
  * Cakisma: raporda zaten farkli (bos olmayan) metin. mode='fill' yalniz bos kutulari doldurur,
    mode='overwrite' Excel'dekini yazar. Bos Excel hucresi raporda hicbir seyi silmez.
"""
from __future__ import annotations

import copy
import functools
import math
import os
import re
import zipfile
import xml.etree.ElementTree as ET

from . import coverage as cov

MAX_UPLOAD_BYTES = 10485760   # 10 MB dosya
MAX_PART_BYTES = 41943040     # 40 MB acilmis XML parcasi (zip-bomb korumasi)
MAX_ROWS = 20000              # sayfa basina satir
MAX_CELLS = 200000            # sayfa basina dolu hucre
MAX_SHEETS = 32               # calisma kitabindaki sayfa

MODULE_SHEETS = ('Modül 13 FSMA',)

NS_MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
NS_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
NS_PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'

HEADERS = {
    'clause': 'madde',
    'label': 'kılavuzun istediği bilgi',
    'value': 'yanıt',
    'key': 'alan anahtarı',
}


class XlsxError(Exception):
    """WP_Error karsiligi: .code (ornek 'agfo_brs_xlsx_sheet') ve Turkce mesaj."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# PHP davranis yardimcilari
# ---------------------------------------------------------------------------

_PHP_WS = ' \t\n\r\0\x0b'
_PHP_NUM = re.compile(r'[ \t\n\r\x0b\x0c]*([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)')
_PHP_INT_MAX = 9223372036854775807


def php_trim(s: str) -> str:
    """PHP trim(): yalniz ' \\t\\n\\r\\0\\x0B'."""
    return s.strip(_PHP_WS)


def php_intval(s: str) -> int:
    """PHP 8 (int) "string": bastaki sayisal kisim ('12abc' -> 12, '1e3' -> 1000, 'abc' -> 0)."""
    m = _PHP_NUM.match(s)
    if not m:
        return 0
    num = m.group(1)
    if re.fullmatch(r'[+-]?[0-9]+', num):
        return max(-_PHP_INT_MAX - 1, min(_PHP_INT_MAX, int(num)))
    f = float(num)
    if math.isnan(f) or math.isinf(f):
        return 0
    return max(-_PHP_INT_MAX - 1, min(_PHP_INT_MAX, int(f)))


def sanitize_key(key) -> str:
    """WordPress sanitize_key(): ASCII kucuk harf, [a-z0-9_-] disindakiler silinir."""
    key = str(key)
    key = ''.join(chr(ord(c) + 32) if 'A' <= c <= 'Z' else c for c in key)
    return re.sub(r'[^a-z0-9_\-]', '', key)


def _lower(s: str) -> str:
    """mb_strtolower(s, 'UTF-8') (tam Unicode eslemesi)."""
    return s.lower()


# ---------------------------------------------------------------------------
# XML yardimcilari (SimpleXML davranisi)
# ---------------------------------------------------------------------------

def _q(name: str) -> str:
    return '{%s}%s' % (NS_MAIN, name)


def _children(node, ns: str) -> list:
    """$node->children(ns): yalniz o ad alanindaki dogrudan cocuklar."""
    pre = '{%s}' % ns
    return [c for c in node if isinstance(c.tag, str) and c.tag.startswith(pre)]


def _local(el) -> str:
    return el.tag.split('}', 1)[1] if '}' in el.tag else el.tag


def _first(node, name: str):
    """$kids->name: ana ad alaninda bu adla ilk cocuk (yoksa None)."""
    for c in node:
        if c.tag == _q(name):
            return c
    return None


def _text(el) -> str:
    """(string) $el: yalniz dogrudan metin dugumleri (alt elemanlarin metni haric, CDATA dahil)."""
    return (el.text or '') + ''.join(c.tail or '' for c in el)


def _attr(el, name: str) -> str:
    """self::attr(): on eksiz nitelik."""
    v = el.get(name)
    return v if v is not None else ''


def _rich_text(node) -> str:
    """<si> / <is> metni: duz <t>, ya da <r><t> parcalari birlesik. Fonetik (rPh) atlanir."""
    t = _first(node, 't')
    r = _first(node, 'r')
    if t is not None and r is None:
        return _text(t)
    out = ''
    for child in _children(node, NS_MAIN):
        name = _local(child)
        if name == 't':
            out += _text(child)
        if name == 'r':
            rt = _first(child, 't')
            if rt is not None:
                out += _text(rt)
    return out


# ---------------------------------------------------------------------------
# ZIP / parca okuma
# ---------------------------------------------------------------------------

def _load_part(zf: zipfile.ZipFile, name: str):
    try:
        info = zf.getinfo(name)
    except KeyError:
        raise XlsxError('agfo_brs_xlsx_part', 'Excel dosyasında beklenen bölüm yok: ' + name) from None
    if info.file_size > MAX_PART_BYTES:
        raise XlsxError('agfo_brs_xlsx_big', 'Excel dosyası işlenemeyecek kadar büyük.')
    try:
        raw = zf.read(name)
    except Exception:  # bozuk sikistirma, CRC vb.
        raise XlsxError('agfo_brs_xlsx_part', 'Excel bölümü okunamadı: ' + name) from None
    if re.search(rb'<!DOCTYPE', raw[:2048], re.I):
        raise XlsxError('agfo_brs_xlsx_dtd', 'Excel dosyası beklenmeyen bir yapı içeriyor.')
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        raise XlsxError('agfo_brs_xlsx_xml', 'Excel bölümü çözümlenemedi: ' + name) from None


def _sheet_paths(zf) -> dict:
    """sayfa adi -> zip yolu (workbook.xml + iliskileri)."""
    try:
        wb = _load_part(zf, 'xl/workbook.xml')
    except XlsxError:
        wb = None
    rels = _load_part(zf, 'xl/_rels/workbook.xml.rels') if wb is not None else None
    if wb is None:
        raise XlsxError('agfo_brs_xlsx_wb', 'Dosya bir Excel çalışma kitabı değil (xl/workbook.xml yok).')
    targets = {}
    for rel in _children(rels, NS_PKG):
        rid, target = _attr(rel, 'Id'), _attr(rel, 'Target')
        if rid == '' or target == '':
            continue
        target = target.lstrip('/')
        if not target.startswith('xl/'):
            target = 'xl/' + target
        targets[rid] = target
    sheets = None
    for c in _children(wb, NS_MAIN):
        if _local(c) == 'sheets':
            sheets = c
            break
    if sheets is None:
        raise XlsxError('agfo_brs_xlsx_wb', 'Çalışma kitabında sayfa listesi yok.')
    out = {}
    for sheet in _children(sheets, NS_MAIN):
        name = _attr(sheet, 'name')
        rid = sheet.get('{%s}id' % NS_REL) or ''
        if name != '' and rid in targets:
            out[name] = targets[rid]
    return out


def _shared_strings(zf) -> list:
    if 'xl/sharedStrings.xml' not in zf.namelist():
        return []
    xml = _load_part(zf, 'xl/sharedStrings.xml')
    return [_rich_text(si) for si in _children(xml, NS_MAIN)]


_REF_RX = re.compile(r'^([A-Z]{1,3})[0-9]+$')


def col_index(letters: str) -> int:
    """'A' -> 1, 'AA' -> 27."""
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n


def col_letters(n: int) -> str:
    """1 -> 'A', 27 -> 'AA'."""
    s = ''
    while n > 0:
        m = (n - 1) % 26
        s = chr(65 + m) + s
        n = (n - 1) // 26
    return s


def _read_sheet(zf, path: str, shared: list) -> dict:
    """satir no -> {sutun harfi -> metin} (yalniz bos olmayan hucreler, belge sirasiyla)."""
    xml = _load_part(zf, path)
    out = {}
    sheet_data = None
    for c in _children(xml, NS_MAIN):
        if _local(c) == 'sheetData':
            sheet_data = c
            break
    if sheet_data is None:
        return out
    count = cells = 0
    next_row = 1
    for row in _children(sheet_data, NS_MAIN):
        count += 1
        if count > MAX_ROWS:
            raise XlsxError('agfo_brs_xlsx_rows', 'Bir Excel sayfası %d satır sınırını aşıyor.' % MAX_ROWS)
        rnum = php_intval(_attr(row, 'r')) if _attr(row, 'r') != '' else next_row
        next_row = rnum + 1
        next_col = 1
        for c in _children(row, NS_MAIN):
            m = _REF_RX.match(_attr(c, 'r'))
            if m:
                col = m.group(1)
                next_col = col_index(col) + 1
            else:
                col = col_letters(next_col)
                next_col += 1
            typ = _attr(c, 't')
            v = _first(c, 'v')
            if typ == 'inlineStr':
                is_ = _first(c, 'is')
                val = _rich_text(is_) if is_ is not None else ''
            elif typ == 's':
                idx = php_intval(_text(v)) if v is not None else -1
                val = shared[idx] if 0 <= idx < len(shared) else ''
            elif typ == 'b':
                val = 'TRUE' if (v is not None and _text(v) == '1') else 'FALSE'
            else:
                val = _text(v) if v is not None else ''
            if val != '':
                cells += 1
                if cells > MAX_CELLS:
                    raise XlsxError('agfo_brs_xlsx_cells',
                                    'Bir Excel sayfası %d dolu hücre sınırını aşıyor.' % MAX_CELLS)
                out.setdefault(rnum, {})[col] = val
    return out


def _locate_header(cells: dict):
    """Ilk 10 satirda baslik satiri: ({'clause','value','key'[,'label']: sutun}, satir) ya da None."""
    for r, row in cells.items():
        if r > 10:
            break
        found = {}
        for col, text in row.items():
            t = _lower(php_trim(text))
            for key, want in HEADERS.items():
                if t == want:
                    found[key] = col
        if 'key' in found and 'value' in found and 'clause' in found:
            return found, int(r)
    return None


def _clean_value(text: str) -> str:
    text = text.replace('\r\n', '\n').replace('\r', '\n').replace('_x000D_', '')
    return php_trim(text)


_ADDR_RX = re.compile(r'^([A-Z]{1,3})([0-9]+)$')


# ---------------------------------------------------------------------------
# Genel API: parse
# ---------------------------------------------------------------------------

def parse(path) -> dict:
    """AGFO_BRS_Xlsx_Reader::parse(): doldurulmus sablonu okur. Hata durumunda XlsxError.

    Donus: {schema, schema_version, profile, standard, plugin_version, meta{}, rows[], skipped_rows}
    rows ogesi: {sheet, row, clause, key, label, value}
    """
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError, ValueError):
        raise XlsxError('agfo_brs_xlsx_open',
                        'Dosya açılamadı. Geçerli bir .xlsx dosyası olduğundan emin olun.') from None
    with zf:
        sheets = _sheet_paths(zf)
        if len(sheets) > MAX_SHEETS:
            raise XlsxError('agfo_brs_xlsx_sheets', 'Excel dosyasında çok fazla sayfa var (en fazla %d). '
                                                    'AGFO şablonunu kullanın.' % MAX_SHEETS)
        shared = _shared_strings(zf)

        marker = {}  # gizli '_agfo' isaret sayfasi (istege bagli)
        if '_agfo' in sheets:
            for row in _read_sheet(zf, sheets['_agfo'], shared).values():
                k = php_trim(row['A']) if 'A' in row else ''
                if k != '':
                    marker[k] = php_trim(row['B']) if 'B' in row else ''

        if 'Rapor' not in sheets:
            raise XlsxError('agfo_brs_xlsx_sheet', '"Rapor" sayfası bulunamadı. Bu dosya AGFO rapor şablonu '
                                                   'değil ya da sayfa adı değiştirilmiş.')
        rapor = _read_sheet(zf, sheets['Rapor'], shared)
        rapor_header = _locate_header(rapor)
        if not rapor_header:
            raise XlsxError('agfo_brs_xlsx_header',
                            '"Rapor" sayfasında başlık satırı (Madde / Yanıt / Alan anahtarı) bulunamadı.')
        answer_sheets = {'Rapor': (rapor, rapor_header)}
        for module_sheet in MODULE_SHEETS:
            if module_sheet not in sheets:
                continue
            mc = _read_sheet(zf, sheets[module_sheet], shared)
            mh = _locate_header(mc)
            if mh:  # basliksiz modul sayfasi katki vermez
                answer_sheets[module_sheet] = (mc, mh)

        meta = {}  # denetim bilgileri: hucre adresleri isaret sayfasindan
        meta_sheet = marker.get('meta_sheet', 'Talimat')
        if meta_sheet in sheets:
            try:
                mcells = _read_sheet(zf, sheets[meta_sheet], shared)
            except XlsxError:
                mcells = None
            if mcells is not None:
                for k, addr in marker.items():
                    if not k.startswith('meta:'):
                        continue
                    m = _ADDR_RX.match(addr)
                    if not m:
                        continue
                    val = php_trim(mcells.get(php_intval(m.group(2)), {}).get(m.group(1), ''))
                    if val != '':
                        meta[k[5:]] = val

    rows, skipped = [], 0
    for sheet_name, (cells, header) in answer_sheets.items():
        cols, header_row = header
        for r, row in cells.items():
            if r <= header_row:
                continue
            key = php_trim(row[cols['key']]) if cols['key'] in row else ''
            clause = php_trim(row[cols['clause']]) if cols['clause'] in row else ''
            value = _clean_value(row[cols['value']]) if cols['value'] in row else ''
            if key == '' or key == '_clause':
                continue
            if value == '':
                continue
            if clause == '':
                skipped += 1
                continue
            rows.append({
                'sheet': sheet_name,
                'row': int(r),
                'clause': clause,
                'key': key,
                'label': php_trim(row[cols['label']]) if 'label' in cols and cols['label'] in row else '',
                'value': value,
            })

    return {
        'schema': marker.get('schema', ''),
        'schema_version': marker.get('schema_version', ''),
        'profile': sanitize_key(marker['profile']) if 'profile' in marker else '',
        'standard': marker.get('standard', ''),
        'plugin_version': marker.get('plugin_version', ''),
        'meta': meta,
        'rows': rows,
        'skipped_rows': skipped,
    }


def parse_upload(path, name=None) -> dict:
    """parse_upload(): uzanti ve boyut denetimi + parse; sonuca 'file_name' eklenir.

    Not: WordPress sanitize_file_name() port edilmedi; ad yalnizca os.path.basename ile alinir.
    """
    name = os.path.basename(str(name if name is not None else path))
    if not re.search(r'\.xlsx$', name, re.I):
        raise XlsxError('agfo_brs_xlsx_ext', 'Yalnızca .xlsx dosyaları kabul edilir. Excel\'de '
                                             '"Farklı kaydet → Excel Çalışma Kitabı (.xlsx)" kullanın.')
    try:
        size = os.path.getsize(path)
    except OSError:
        raise XlsxError('agfo_brs_xlsx_invalid', 'Geçersiz yükleme.') from None
    if size > MAX_UPLOAD_BYTES:
        raise XlsxError('agfo_brs_xlsx_size', 'Excel dosyası 10 MB sınırını aşıyor.')
    result = parse(path)
    result['file_name'] = name
    return result


# ---------------------------------------------------------------------------
# editor.js ice aktarma birlestirmesi
# ---------------------------------------------------------------------------

def compare_clauses(a, b) -> int:
    """compareClauses: noktali parcalar parseInt ile sayisal karsilastirilir (NaN -> 1)."""
    x, y = cov.js_str(a).split('.'), cov.js_str(b).split('.')
    for i in range(max(len(x), len(y))):
        p = _js_parse_int((x[i] if i < len(x) else '') or '0')
        q = _js_parse_int((y[i] if i < len(y) else '') or '0')
        if p != q:
            return -1 if p < q else 1
    return 0


def _js_parse_int(s: str) -> float:
    m = re.match('[' + cov._JS_WS_CHARS + r']*([+-]?[0-9]+)', s)
    return float(int(m.group(1))) if m else float('nan')


def norm_label(s) -> str:
    """normLabel: tr yerel kucuk harf, bosluk katlama, sondaki .:;, temizligi, trim."""
    s = cov._or_str(s)
    s = s.replace('İ', 'i').replace('İ', 'i').replace('I', 'ı').lower()  # toLocaleLowerCase('tr')
    s = cov._JS_WS_RUN.sub(' ', s)
    s = re.sub(r'[.:;,]+\Z', '', s)
    return cov.js_trim(s)


def box_map_for(profile) -> dict:
    """boxMap(): agfoBrs.boxes[profil] (yoksa normalize profil, yoksa {})."""
    maps = cov.all_box_maps()
    bm = cov._jget(maps, profile) if isinstance(profile, str) else None
    if not cov._truthy(bm):
        bm = cov._jget(maps, cov.normalize_profile(profile))
    return bm if cov._truthy(bm) else {}


def _bm_part(bm, name) -> dict:
    v = cov._jget(bm, name)
    return v if cov._truthy(v) else {}


def row_by_clause(project, clause):
    """rowByClause: === ile ilk satir."""
    for row in project.get('detailed') or []:
        if row.get('clause') == clause:
            return row
    return None


def make_module_row(project, key, box_map) -> dict:
    """makeModuleRow: rapora eklenecek bos modul satiri."""
    u = cov._jget(_bm_part(box_map, 'optional'), key) or {}
    tag = cov._jget(_bm_part(box_map, 'units'), key) or ''
    module = cov.js_str(u.get('module')) if 'module' in u else 'undefined'
    return {
        'clause': key, 'title': u.get('title') or key, 'value': '', 'note': '', 'sort_order': 0,
        'tag': tag, 'part': 'report-box',
        'sdt_index': 'box_' + cov.normalize_profile(project.get('profile')) + '_' + key.replace('.', '_'),
        'coverage_parent': '', 'source_key': '', 'flags': {'box': tag, 'unit_source': 'module' + module},
    }


def module_units(module, box_map) -> list:
    """moduleUnits: modulun birim anahtarlari, madde sirasiyla."""
    opt = _bm_part(box_map, 'optional')
    keys = [k for k in cov.js_keys(opt) if (cov._jget(opt, k) or {}).get('module') == cov.js_str(module)]
    return sorted(keys, key=functools.cmp_to_key(compare_clauses))


def add_module_rows(project, module, prepared, box_map) -> int:
    """addModuleRows: modulun eksik birimlerini rapora ekler, siralar; eklenen sayisi."""
    added = 0
    for key in module_units(module, box_map):
        if row_by_clause(project, key):
            continue
        project['detailed'].append((prepared or {}).get(key) or make_module_row(project, key, box_map))
        added += 1
    if added:
        project['detailed'].sort(key=functools.cmp_to_key(lambda a, b: compare_clauses(a.get('clause'),
                                                                                       b.get('clause'))))
        for i, r in enumerate(project['detailed']):
            r['sort_order'] = i
    return added


def plan_excel_import(project, parsed, box_map=None) -> dict:
    """planExcelImport: her Excel yanitini bir alt madde girisine eslestirir; rapor DEGISMEZ.

    project: {'profile', 'detailed': [satir], 'section_findings': {madde: metin}}
    Donus plani: {'error'?, 'items', 'skipped_clauses', 'legacy', 'conflicts', 'clauses', 'answers',
                  'notes', 'new_rows', 'add_modules'}
    """
    plan = {'items': [], 'skipped_clauses': [], 'legacy': 0, 'conflicts': 0, 'clauses': {}, 'answers': 0,
            'notes': 0}
    xp = cov.normalize_profile(parsed.get('profile')) if cov._truthy(parsed.get('profile')) else ''
    pp = cov.normalize_profile(project.get('profile'))
    if xp and xp != pp:
        plan['error'] = ('Bu Excel ' + xp.upper() + ' standardı için hazırlanmış; açık rapor ise ' + pp.upper() +
                         '. Doğru şablonu kullanın veya ilgili raporu açın.')
        return plan
    rows = parsed.get('rows') or []
    if not rows:
        plan['error'] = ('Excel dosyasında doldurulmuş yanıt bulunamadı. Sarı "Yanıt" sütununun '
                         'doldurulduğundan emin olun.')
        return plan
    bm = box_map if box_map is not None else box_map_for(project.get('profile'))
    optional = _bm_part(bm, 'optional')
    skipped = {}
    plan['new_rows'] = {}
    plan['add_modules'] = {}
    findings = project.get('section_findings') or {}
    for x in rows:
        xc = cov.js_str(x.get('clause'))
        row = row_by_clause(project, xc)
        opt = cov._jget(optional, xc)
        if not row and cov._truthy(opt):
            # Raporda henuz olmayan modul maddesi Excel'de yanitlanmis.
            row = plan['new_rows'].get(xc) or plan['new_rows'].setdefault(xc, make_module_row(project, xc, bm))
            plan['add_modules'][cov.js_str(opt.get('module'))] = True
        if not row:
            skipped[xc] = True
            continue
        value = cov._or_str(x.get('value'))
        item = {'row': row, 'clause': row.get('clause'), 'value': value, 'kind': '', 'key': x.get('key')}
        if x.get('key') == '_note':
            item['kind'] = 'note'
            item['existing'] = cov._or_str(row.get('note'))
            plan['notes'] += 1
        elif x.get('key') == '_finding':
            item['kind'] = 'finding'
            item['existing'] = cov._or_str(findings.get(row.get('clause')))
            plan['notes'] += 1
        else:
            d = cov.form_for(project.get('profile'), row.get('clause'))
            fields = d['fields'] if d else []
            match = next((f for f in fields if f.get('key') == x.get('key')), None)
            if match is None and cov._truthy(x.get('label')):
                nl = norm_label(x.get('label'))
                match = next((f for f in fields if norm_label(f.get('label')) == nl), None)
            if match is not None:
                item['kind'] = 'field'
                item['key'] = match.get('key')
                item['existing'] = cov._or_str(cov.struct_of(row).get(match.get('key')))
            else:
                # Soru artik bu alt maddenin formunda yok: yanit eski metin olarak saklanir.
                item['kind'] = 'legacy'
                item['key'] = cov.LEGACY_KEY
                item['label'] = x.get('label') if cov._truthy(x.get('label')) else x.get('key')
                item['existing'] = ''
                plan['legacy'] += 1
            plan['answers'] += 1
        ex = cov.js_trim(item['existing'])
        if ex and ex != cov.js_trim(value) and item['kind'] != 'legacy':
            plan['conflicts'] += 1
        plan['clauses'][row.get('clause')] = True
        plan['items'].append(item)
    plan['skipped_clauses'] = cov.js_keys(skipped)
    return plan


def apply_excel_import(project, plan, mode, box_map=None) -> dict:
    """applyExcelImport: plani rapora uygular (project YERINDE degisir, orijinaldeki gibi).

    mode: 'fill' (yalniz bos kutular) | 'overwrite' (Excel'deki yazilir).
    Donus: {'written', 'kept', 'changed': [madde...], 'added_rows'}. written == 0 ise orijinal kaydetmez
    (yine de bellekteki satirlarin 'value'su yeniden derlenmis olabilir - bkz. rapor notu).
    """
    bm = box_map if box_map is not None else box_map_for(project.get('profile'))
    changed, written, kept, added = {}, 0, 0, 0
    for m in cov.js_keys(plan.get('add_modules') or {}):
        added += add_module_rows(project, m, plan.get('new_rows'), bm)

    def take(existing):
        return mode == 'overwrite' or not cov.js_trim(cov._or_str(existing))

    findings = project.setdefault('section_findings', {})
    for it in plan['items']:
        row = it['row']
        if it['kind'] == 'note':
            if take(row.get('note')):
                if cov._or_str(row.get('note')) != it['value']:
                    row['note'] = it['value']
                    written += 1
            else:
                kept += 1
            changed[row.get('clause')] = row
            continue
        if it['kind'] == 'finding':
            cur = findings.get(row.get('clause'))
            if take(cur):
                if cov._or_str(cur) != it['value']:
                    findings[row.get('clause')] = it['value']
                    written += 1
            else:
                kept += 1
            continue
        flags = row.get('flags')
        struct = flags['struct'] if cov._truthy(flags) and cov._truthy(flags.get('struct')) else cov.struct_of(row)
        if not cov._truthy(row.get('flags')):
            row['flags'] = {}
        row['flags']['struct'] = struct
        if it['kind'] == 'legacy':
            add = (cov.js_str(it['label']) + ': ' if cov._truthy(it.get('label')) else '') + it['value']
            prev = cov._or_str(struct.get(cov.LEGACY_KEY))
            if add not in prev:
                struct[cov.LEGACY_KEY] = prev + '\n\n' + add if prev else add
                written += 1
        elif take(struct.get(it['key'])):
            if cov._or_str(struct.get(it['key'])) != it['value']:
                struct[it['key']] = it['value']
                written += 1
        else:
            kept += 1
        changed[row.get('clause')] = row

    for c in cov.js_keys(changed):
        row = changed[c]
        flags = row.get('flags')
        if cov._truthy(flags) and cov._truthy(flags.get('struct')):
            row['value'] = cov.assemble_text(project.get('profile'), row, flags['struct'])
    return {'written': written, 'kept': kept, 'changed': cov.js_keys(changed), 'added_rows': added}


def import_summary(plan, parsed, box_map=None, profile=None) -> dict:
    """excelImportDialog'un gosterdigi veri (HTML yerine)."""
    bm = box_map if box_map is not None else box_map_for(profile)
    mods = _bm_part(bm, 'modules')
    add_mods = []
    for m in cov.js_keys(plan.get('add_modules') or {}):
        info = cov._jget(mods, m) or {}
        add_mods.append({'module': m, 'title': info.get('title') or ('Module ' + m),
                         'units': len(module_units(m, bm))})
    return {
        'file_name': parsed.get('file_name') or '',
        'plugin_version': parsed.get('plugin_version') or '',
        'meta': parsed.get('meta') or {},
        'clauses': len(plan.get('clauses') or {}),
        'answers': plan.get('answers', 0),
        'notes': plan.get('notes', 0),
        'conflicts': plan.get('conflicts', 0),
        'legacy': plan.get('legacy', 0),
        'add_modules': add_mods,
        'skipped_clauses': list(plan.get('skipped_clauses') or []),
        'skipped_rows': parsed.get('skipped_rows') or 0,
        # Cakisma yoksa yalniz 'fill' ("Ice aktar") sunulur; varsa 'fill' ve 'overwrite'.
        'modes': ['fill', 'overwrite'] if plan.get('conflicts') else ['fill'],
    }


def merge_excel_answers(project, parsed, mode='fill', box_map=None):
    """Saf birlestirme: plan + uygula, girdi project'e dokunmadan.

    Donus: (yeni_project, sonuc). sonuc = {'error'} (engellendi: profil uyusmazligi / bos dosya)
    ya da {'written', 'kept', 'changed', 'added_rows', 'summary'}.
    """
    new = copy.deepcopy(project)
    plan = plan_excel_import(new, parsed, box_map)
    if plan.get('error'):
        return new, {'error': plan['error']}
    summ = import_summary(plan, parsed, box_map, new.get('profile'))
    res = apply_excel_import(new, plan, mode, box_map)
    res['summary'] = summ
    return new, res
