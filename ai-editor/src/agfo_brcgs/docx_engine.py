# -*- coding: utf-8 -*-
"""AGFO AI Editor - resmi BRCGS DOCX sablonunu bozmadan doldurma / okuma.

Kaynak: AGFO BRCGS Report Studio 5.2.1
  includes/class-docx-content-controls.php  (yaprak alan yazimi, korunan tablolar, resmi satir tablolari, NC eylem plani,
                                             duz etiketli hucreler, metin degistirme ve yer tutucu bicimi temizleme)
  includes/class-docx-detailed-section.php  (okuma tarafi)
  includes/class-ajax.php                   (values_from_controls, normalize_import_value, enrich_values_from_docx_tables)

Ilke: sablon yeniden kurulmaz. Yalniz icerik denetimlerinin (w:sdt) metni ve resmi satir tablolarinin veri satirlari
degisir; diger her parca (logolar, ust/alt bilgi, stiller, bolum ayarlari) bayt bayt ayni kalir. lxml kullanilir cunku
ad alani onekleri (w14, w15, mc:Ignorable) korunmazsa Word dosyayi bozuk sayar.

Report Studio'ya gore bilerek eklenenler (hepsi Word uyumlulugu icin):
  * w:showingPlcHdr kaldirilir: kalirsa Word yazilan metni hala yer tutucu sayar (gri gorunur, tiklayinca silinir).
  * tarih denetimine w:fullDate yazilir; acilir listede deger listedeki secenekle eslenir.
  * yinelenen etiketlerde (CLASSIFICATION x8, EXPORTED_TO x6 ...) degerler sirayla dagitilir (PHP hepsine ayni metni yaziyordu).
  * w:t'si olmayan bos denetimlere kosu olusturulur (PHP sessizce atliyordu).
  * NA tablolari (FS/PM/AB, kutu haritasinda NA etiketi olmayan) satir satir doldurulur (PHP'de bu tablolar bos kaliyordu).
"""
from __future__ import annotations

import copy
import datetime
import io
import re
import zipfile

from lxml import etree

from . import boxes as B
from . import data

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
W14_NS = 'http://schemas.microsoft.com/office/word/2010/wordml'
XML_NS = 'http://www.w3.org/XML/1998/namespace'
NS = {'w': W_NS, 'w14': W14_NS}
PARTS_RX = re.compile(r'^word/(document|header\d+|footer\d+)\.xml$')


def w(tag):
    return '{%s}%s' % (W_NS, tag)


def wval(el):
    return el.get(w('val')) if el is not None else None


# ----------------------------------------------------------------------------- metin yardimcilari
def normalize_text(text) -> str:
    t = str(text or '').replace('\xa0', ' ').replace('​', ' ').replace('﻿', ' ')
    return re.sub(r'\s+', ' ', t).strip()


def compact(text) -> str:
    return re.sub(r'[^a-z0-9]+', '', str(text or '').lower())


def node_text(node) -> str:
    return ''.join(t.text or '' for t in node.iter(w('t')))


def sdt_text(sdt) -> str:
    """read_sdt_text(): w:br satir sonu olarak okunur (5.2.0)."""
    content = sdt.find(w('sdtContent'))
    if content is None:
        return ''
    out = []
    for el in content.iter(w('t'), w('br')):
        out.append('\n' if el.tag == w('br') else (el.text or ''))
    return ''.join(out).strip()


def xml_text(value) -> str:
    """Duz metin oldugu gibi yazilir. Report Studio'daki wp_strip_all_tags burada BILEREK yok: "<5 °C ... >2 °C" gibi
    denetim metni iki isaret arasini kaybediyordu. Yalniz XML'de gecersiz karakterler atilir, satir sonlari birlesir."""
    t = str(value if value is not None else '').replace('\r\n', '\n').replace('\r', '\n')
    return re.sub('[^\x09\x0A\x0D\x20-퟿-�\U00010000-\U0010FFFF]', '', t)


_IMPORT_PLACEHOLDER = re.compile(r'^(Click or tap here to enter text\.?|Click or tap to enter a date\.?|Choose an item\.?|Please select|'
                                 r'Select a date|Choose a module|Choose a region|Category|Modules|Result|Scope|Exclusions from Scope)$', re.I)


_PH_ANY = re.compile(r'click or tap|choose an? |choose an item|select a date|enter a date|please select', re.I)


def is_prompt_item(text) -> bool:
    """Acilir listedeki 'Choose an item' / 'Choose a module' / 'Please select' gibi istem secenekleri."""
    t = str(text or '')
    return bool(re.match(r'^\s*(choose\b|please select|select\b|click or tap)', t, re.I)) or bool(_IMPORT_PLACEHOLDER.match(t.strip()))


def is_label_row_control(sdt) -> bool:
    """Satirin tum hucreleri yer tutucu metni bir sutun adi olan denetimlerse (Modules | Result | Scope | Exclusions)
    bu denetimler etikettir, alan degil (Report Studio da bu metinleri yer tutucu sayar)."""
    row = ancestor(sdt, 'tr')
    if row is None:
        return False
    cells = _row_cell_list(row)
    if len(cells) < 2:
        return False
    for c in cells:
        ctrls = [x for x in c.iter(w('sdt'))] if c.tag != w('sdt') else [c]
        holder = ancestor(c, 'sdt')
        if not ctrls and holder is not None and ancestor(holder, 'tr') is row:
            ctrls = [holder]
        if not ctrls:
            return False
        t = normalize_text(node_text(c))
        if not t or _PH_ANY.search(t) or len(t) > 40:
            return False
    return True


def normalize_import_value(value) -> str:
    """class-ajax.php normalize_import_value() (+ sablonlardaki diger yer tutucu metinleri)."""
    v = normalize_text(value)
    if re.match(r'^(NA|N/A|None|No|Not applicable)$', v, re.I):
        return v
    if _IMPORT_PLACEHOLDER.match(v):
        return ''
    return v


# ----------------------------------------------------------------------------- denetim (sdt) bilgisi
def sdt_props(sdt):
    pr = sdt.find(w('sdtPr'))
    tag = wval(pr.find(w('tag'))) if pr is not None else None
    alias = wval(pr.find(w('alias'))) if pr is not None else None
    kind, items, date_fmt = 'rich', [], None
    if pr is not None:
        for name in ('text', 'date', 'dropDownList', 'comboBox', 'picture', 'docPartObj', 'group', 'richText'):
            el = pr.find(w(name))
            if el is not None:
                kind = name
                if name in ('dropDownList', 'comboBox'):
                    for li in el.findall(w('listItem')):
                        txt = li.get(w('displayText')) or li.get(w('value')) or ''
                        items.append({'text': txt, 'value': li.get(w('value')) or '', 'prompt': is_prompt_item(txt) or not txt.strip()})
                if name == 'date':
                    date_fmt = wval(el.find(w('dateFormat')))
                break
        if pr.find('{%s}checkbox' % W14_NS) is not None:
            kind = 'checkbox'
    showing = pr is not None and pr.find(w('showingPlcHdr')) is not None
    return {'tag': tag or '', 'alias': alias or '', 'kind': kind, 'items': items, 'date_format': date_fmt,
            'placeholder_showing': showing}


def is_container_sdt(sdt) -> bool:
    """is_table_or_container_sdt(): tablo, birden cok hucre ya da ic ice denetim tasiyan denetim yazilmaz."""
    content = sdt.find(w('sdtContent'))
    if content is None:
        return False
    if next(content.iter(w('tbl')), None) is not None:
        return True
    if sum(1 for _ in content.iter(w('tc'))) > 1:
        return True
    if next(content.iter(w('sdt')), None) is not None:
        return True
    return bool(re.search(r'\b(Major|Minor|Critical)\s*No\.\s*Clause\s*Detail|Proposed preventive action plan|Root cause analysis|'
                          r'GFSI Benchmarked audit history|Additional modules included|Head Office|Details of non-applicable clauses|'
                          r'Clause/Section Ref\s*Justification', normalize_text(sdt_text(sdt)), re.I))


def ancestor(node, tag):
    p = node.getparent()
    while p is not None:
        if p.tag == w(tag):
            return p
        p = p.getparent()
    return None


def direct_rows(tbl):
    return tbl.findall(w('tr'))


def row_cells(tr):
    return tr.findall(w('tc'))


def is_official_nc_or_action_table(tbl) -> bool:
    c = compact(normalize_text(node_text(tbl)))
    if ('nonconformitysummarysheet' in c or 'majornonconformityagainststatementofintent' in c or 'criticalormajor' in c
            or 'proposedpreventiveactionplan' in c or 'rootcauseanalysis' in c
            or 'detailsofnonapplicableclauseswithjustification' in c or ('clausesectionref' in c and 'justification' in c)):
        return True
    rows = direct_rows(tbl)
    if not rows:
        return False
    first = compact(normalize_text(node_text(rows[0])))
    if first in ('major', 'minor'):
        if any(len(row_cells(r)) in (7, 8) for r in rows[1:]):
            return True
    if first == 'critical' or 'fundamentalrequirement' in first or 'majornonconformity' in first:
        if any(4 <= len(row_cells(r)) <= 5 for r in rows[1:]):
            return True
    if 'detailsofnonapplicableclauses' in first or 'nonapplicableclauses' in first:
        for r in rows[1:]:
            rc = compact(normalize_text(node_text(r)))
            if len(row_cells(r)) >= 2 and 'clausesectionref' in rc and 'justification' in rc:
                return True
    return False


def critical_table(tbl) -> bool:
    rows = direct_rows(tbl)
    return bool(rows) and compact(normalize_text(node_text(rows[0]))) == 'critical'


def inside_table_editor(node) -> bool:
    """Resmi satir tablolari, eylem plani ve Critical NC tablosu kendi duzenleyicileriyle doldurulur."""
    tbl = ancestor(node, 'tbl')
    while tbl is not None:
        if official_table_type(tbl) or action_plan_table_type(tbl) or critical_table(tbl):
            return True
        tbl = ancestor(tbl, 'tbl')
    return False


def inside_nc_summary_table(node) -> bool:
    tbl = ancestor(node, 'tbl')
    return tbl is not None and is_official_nc_or_action_table(tbl)


def cell_label(sdt) -> str:
    """Denetimin solundaki hucrenin metni (ayni satirda)."""
    tc = sdt if sdt.tag == w('tc') else ancestor(sdt, 'tc')
    if tc is None:
        tc = next(sdt.iter(w('tc')), None)
    # denetim hucre duzeyindeyse kendisi hucredir
    if sdt.find(w('sdtContent')) is not None and sdt.find(w('sdtContent')).find(w('tc')) is not None:
        tc = sdt
    if tc is None:
        return ''
    row = ancestor(tc, 'tr')
    if row is None:
        return ''
    head = column_header(tc, row)
    if head and not _PH_ANY.search(head):
        return head
    prev = tc.getprevious()
    while prev is not None:
        if prev.tag == w('sdt') or next(prev.iter(w('sdt')), None) is not None:
            prev = prev.getprevious()                     # komsu hucre baska bir alanin degeri: etiket degil
            continue
        txt = normalize_text(node_text(prev))
        if txt and not _IMPORT_PLACEHOLDER.match(txt) and not _PH_ANY.search(txt):
            return txt
        prev = prev.getprevious()
    return ''


def _row_cell_list(tr):
    """Satirin hucreleri (satir/hucre duzeyindeki denetimlerin icindekiler dahil), belge sirasiyla."""
    out = []
    for ch in tr:
        if ch.tag == w('tc'):
            out.append(ch)
        elif ch.tag == w('sdt'):
            c = ch.find(w('sdtContent'))
            if c is not None:
                out.extend(x for x in c.iter(w('tc')) if ancestor(x, 'tc') is None or ancestor(x, 'tc') not in out)
    return out


def column_header(tc, row):
    """Tablo bicimli satirlarda (ustte ayni sayida etiket hucresi olan) sutun basligi."""
    tbl = ancestor(row, 'tbl')
    if tbl is None:
        return ''
    rows = [r for r in tbl.iter(w('tr')) if ancestor(r, 'tbl') is tbl]
    try:
        i = rows.index(row)
    except ValueError:
        return ''
    cells = _row_cell_list(row)
    if tc not in cells or len(cells) < 2:
        return ''
    col = cells.index(tc)
    for prev in reversed(rows[:i]):
        pc = _row_cell_list(prev)
        if len(pc) != len(cells):
            if len(pc) <= 1:
                break
            continue
        texts = [normalize_text(node_text(c)) for c in pc]
        if all(texts) and not any(next(c.iter(w('sdt')), None) is not None and not _IMPORT_PLACEHOLDER.match(t) and False
                                  for c, t in zip(pc, texts)):
            label_like = sum(1 for c in pc if next(c.iter(w('sdt')), None) is None)
            if label_like == len(pc):
                return texts[col]
        break
    return ''


def group_title(sdt) -> str:
    """Denetimin bulundugu en dis tablonun ilk satiri ('Audit Summary', 'Company Profile' ...)."""
    outer = None
    p = sdt.getparent()
    while p is not None:
        if p.tag == w('tbl'):
            outer = p
        p = p.getparent()
    if outer is None:
        return ''
    for r in outer.iter(w('tr')):
        for c in _row_cell_list(r):
            t = normalize_text(node_text(c))
            if t and not _IMPORT_PLACEHOLDER.match(t):
                t = re.sub(r'^\d+\.\s*', '', t)
                return t[:60]
        break
    return ''


# ----------------------------------------------------------------------------- yazma ilkeleri
def _remove_placeholder_flag(node):
    """Yazilan dugumun tum ust denetimlerinden w:showingPlcHdr kaldirilir."""
    p = node
    while p is not None:
        if p.tag == w('sdt'):
            pr = p.find(w('sdtPr'))
            if pr is not None:
                for el in pr.findall(w('showingPlcHdr')):
                    pr.remove(el)
        p = p.getparent()


def _neutralize_run(t):
    run = t.getparent()
    while run is not None and run.tag != w('r'):
        run = run.getparent()
    if run is None:
        return
    rpr = run.find(w('rPr'))
    if rpr is not None:
        for child in list(rpr):
            if child.tag in (w('rStyle'), w('b'), w('bCs'), w('color'), w('highlight'), w('shd')):
                rpr.remove(child)
    # Sablonda bazi kutularin paragrafi 'Heading3' stilinde (F908 F3_1, F3_5_2): yer tutucu grisi kalkinca baslik mavisi
    # metne gecer. Word'de yazinca denetimin kendi bicimi uygulanir; burada rengi acikca 'auto' yaparak ayni sonucu veririz.
    par = run.getparent()
    while par is not None and par.tag != w('p'):
        par = par.getparent()
    ps = par.find(w('pPr') + '/' + w('pStyle')) if par is not None else None
    if ps is not None and str(wval(ps) or '').lower().startswith(('heading', 'baslik', 'başlık')):
        if rpr is None:
            rpr = etree.Element(w('rPr'))
            run.insert(0, rpr)
        col = etree.Element(w('color'))
        col.set(w('val'), 'auto')
        anchor = rpr.find(w('sz'))
        if anchor is None:
            anchor = rpr.find(w('szCs'))
        if anchor is not None:
            anchor.addprevious(col)
        else:
            rpr.append(col)
        for tag in ('b', 'bCs'):
            el = etree.SubElement(rpr, w(tag))
            el.set(w('val'), '0')
            rpr.remove(el)
            (rpr.find(w('i')) if rpr.find(w('i')) is not None else rpr.find(w('color'))).addprevious(el)


def _set_text(t, value):
    """set_node_text(): cok satirli metin ayni kosu icinde w:br ile ayrilir (5.2.0)."""
    text = xml_text(value)
    lines = text.split('\n')
    t.text = lines[0]
    t.set('{%s}space' % XML_NS, 'preserve')
    after = t
    for line in lines[1:]:
        br = etree.Element(w('br'))
        after.addnext(br)
        nt = etree.Element(w('t'))
        nt.set('{%s}space' % XML_NS, 'preserve')
        nt.text = line
        br.addnext(nt)
        after = nt


def _clear_extra_text(nodes):
    for t in nodes:
        t.text = ''
    # onceki yazimdan kalan w:br'leri de kaldir (yeniden yazimda satirlar cogalmasin)


def _ensure_text_node(container):
    """w:t yoksa kosu/paragraf olustur."""
    t = next(container.iter(w('t')), None)
    if t is not None:
        return t
    r = next(container.iter(w('r')), None)
    if r is None:
        p = next(container.iter(w('p')), None)
        if p is None:
            tc = next(container.iter(w('tc')), None)
            host = tc if tc is not None else container
            p = etree.SubElement(host, w('p'))
        r = etree.SubElement(p, w('r'))
    t = etree.SubElement(r, w('t'))
    return t


def _strip_brs(container):
    for br in list(container.iter(w('br'))):
        if br.get(w('type')) in (None, 'textWrapping'):
            br.getparent().remove(br)


def replace_sdt_text(sdt, value):
    content = sdt.find(w('sdtContent'))
    if content is None:
        return False
    _strip_brs(content)
    nodes = list(content.iter(w('t')))
    t = nodes[0] if nodes else _ensure_text_node(content)
    for extra in nodes[1:]:
        extra.text = ''
    _set_text(t, value)
    _neutralize_run(t)
    _remove_placeholder_flag(sdt)
    return True


def replace_cell_text(cell, value):
    _strip_brs(cell)
    nodes = list(cell.iter(w('t')))
    if nodes:
        t = nodes[0]
        for extra in nodes[1:]:
            extra.text = ''
    else:
        p = cell.find(w('p'))
        if p is None:
            p = etree.SubElement(cell, w('p'))
        r = etree.SubElement(p, w('r'))
        t = etree.SubElement(r, w('t'))
    _set_text(t, value)
    _neutralize_run(t)
    _remove_placeholder_flag(cell)


_DATE_INPUT = ('%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d', '%d.%m.%y')


def parse_date(value):
    v = str(value or '').strip()
    for f in _DATE_INPUT:
        try:
            return datetime.datetime.strptime(v, f).date()
        except ValueError:
            continue
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})T', v)
    if m:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def format_date(d, word_fmt) -> str:
    """Word dateFormat (dd/MM/yyyy, yyyy-MM-dd, d MMMM yyyy ...) -> metin."""
    f = word_fmt or 'yyyy-MM-dd'
    months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    out, i = [], 0
    tokens = (('yyyy', lambda: '%04d' % d.year), ('yy', lambda: '%02d' % (d.year % 100)), ('MMMM', lambda: months[d.month - 1]),
              ('MMM', lambda: months[d.month - 1][:3]), ('MM', lambda: '%02d' % d.month), ('M', lambda: str(d.month)),
              ('dddd', lambda: d.strftime('%A')), ('dd', lambda: '%02d' % d.day), ('d', lambda: str(d.day)))
    while i < len(f):
        for tok, fn in tokens:
            if f.startswith(tok, i):
                out.append(fn())
                i += len(tok)
                break
        else:
            if f[i] == "'":
                j = f.find("'", i + 1)
                j = len(f) if j < 0 else j
                out.append(f[i + 1:j])
                i = j + 1
            else:
                out.append(f[i])
                i += 1
    return ''.join(out)


def write_leaf(sdt, value, props=None):
    """Bir yaprak denetime deger yazar (tur bilgisine gore)."""
    props = props or sdt_props(sdt)
    text = '' if value is None else str(value)
    pr = sdt.find(w('sdtPr'))
    if props['kind'] == 'date' and text.strip():
        d = parse_date(text)
        if d is not None:
            el = pr.find(w('date'))
            el.set(w('fullDate'), d.strftime('%Y-%m-%dT00:00:00Z'))
            text = format_date(d, props['date_format'])
    elif props['kind'] in ('dropDownList', 'comboBox') and text.strip():
        for it in props['items']:
            if text.strip() in (it['text'], it['value']):
                text = it['text']
                break
    if not text.strip():
        return False                                   # bos deger: sablondaki yer tutucu kalir
    return replace_sdt_text(sdt, text)


# ----------------------------------------------------------------------------- belge
class DocxTemplate:
    """Bir DOCX paketini acar; parcalar lxml agaci olarak duzenlenir, yalniz degisenler yeniden yazilir."""

    def __init__(self, path_or_bytes):
        if isinstance(path_or_bytes, (bytes, bytearray)):
            raw = path_or_bytes
        else:
            with open(path_or_bytes, 'rb') as fh:
                raw = fh.read()
        self.raw = bytes(raw)
        self.zip = zipfile.ZipFile(io.BytesIO(self.raw))
        self.trees = {}
        parser = etree.XMLParser(remove_blank_text=False, huge_tree=True, resolve_entities=False)
        for name in self.zip.namelist():
            if PARTS_RX.match(name):
                self.trees[name] = etree.fromstring(self.zip.read(name), parser)
        self.changed = set()

    @property
    def document(self):
        return self.trees['word/document.xml']

    def parts(self):
        names = ['word/document.xml'] + sorted(n for n in self.trees if n != 'word/document.xml')
        return [(n, self.trees[n]) for n in names if n in self.trees]

    def all_sdts(self):
        for name, root in self.parts():
            for sdt in root.iter(w('sdt')):
                yield name, sdt

    def save(self, path=None) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as out:
            for info in self.zip.infolist():
                if info.filename in self.changed:
                    data_ = etree.tostring(self.trees[info.filename], xml_declaration=True, encoding='UTF-8', standalone=True)
                else:
                    data_ = self.zip.read(info.filename)
                ni = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                ni.compress_type = info.compress_type if info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) else zipfile.ZIP_DEFLATED
                ni.external_attr = info.external_attr
                out.writestr(ni, data_)
        blob = buf.getvalue()
        if path:
            import os
            import tempfile
            d = os.path.dirname(os.path.abspath(path))
            fd, tmp = tempfile.mkstemp(prefix='.agfo-', suffix='.docx', dir=d)
            with os.fdopen(fd, 'wb') as fh:
                fh.write(blob)
            os.replace(tmp, path)
        return blob


# ----------------------------------------------------------------------------- tarama (form semasi)
def detect_profile(tpl: DocxTemplate, filename='') -> str:
    tags = {sdt_props(s)['tag'] for _n, s in tpl.all_sdts()}
    best, score = '', 0
    for p in data.PROFILES:
        n = len(tags & B.detail_tags(p))
        if n > score:
            best, score = p, n
    return best or data.profile_from_template_name(filename) or 'pm'


def _readable(alias) -> bool:
    """Sablon yazarinin verdigi ad okunabilir mi ('Company Name' evet, 'ATFNAME' hayir)."""
    a = str(alias or '').strip()
    return bool(a) and (' ' in a or (any(c.islower() for c in a) and not a.isupper())) and '_' not in a


import functools as _ft


@_ft.lru_cache(maxsize=None)
def label_tags(profile):
    """Paketteki ozgun sablonda baslik/etiket satiri olan denetimlerin etiketleri. Dolu belgede bu karar verilemez
    (kisa degerlerle dolu bir satir da etiket satirina benzer), bu yuzden her zaman ozgun sablondan alinir."""
    tpl = DocxTemplate(data.template_path(profile))
    return frozenset(sdt_props(s)['tag'] for _n, s in tpl.all_sdts() if sdt_props(s)['tag'] and is_label_row_control(s))


def scan_fields(tpl: DocxTemplate, profile):
    """Formda gosterilecek yaprak alanlar (Detayli rapor kutulari, NA, NC/eylem plani tablolari ve kapsayicilar haric).
    Donus: [{'key','tag','alias','kind','items','label','group','occurrence','date_format','value'}] belge sirasiyla.
    key = etiket (yoksa ad); ayni etiket birden cok kez geciyorsa occurrence 0,1,2..."""
    p = data.norm_profile(profile)
    skip = B.detail_tags(p) | B.na_tags(p)
    labels = label_tags(p)
    seen = {}
    out = []
    for _name, sdt in tpl.all_sdts():
        pr = sdt_props(sdt)
        key = pr['tag'] or pr['alias']
        if not key or pr['tag'] in skip or pr['kind'] in ('docPartObj', 'picture', 'group'):
            continue
        if is_container_sdt(sdt) or inside_nc_summary_table(sdt) or inside_table_editor(sdt) or pr['tag'] in labels:
            continue
        n = seen.get(key, 0)
        seen[key] = n + 1
        value = '' if pr['placeholder_showing'] else normalize_import_value(sdt_text(sdt))
        near = cell_label(sdt)
        if _PH_ANY.search(near or ''):
            near = ''
        label = near or (pr['alias'] if _readable(pr['alias']) else '') or pr['alias'] or key
        out.append(dict(pr, key=key, occurrence=n, label=label, hint=pr['alias'] if pr['alias'] and pr['alias'].lower() != label.lower() else '',
                        group=group_title(sdt) or 'Diğer', value=value))
    counts = seen
    for f in out:
        f['repeats'] = counts[f['key']]
    return out


# ----------------------------------------------------------------------------- yazma: alanlar
def _values_for_key(values, key, alias):
    for k in (key, alias):
        if k and k in values:
            return values[k]
    return None


def write_fields(tpl: DocxTemplate, values, profile):
    """Yaprak alanlari yazar. values[key] str ya da (yinelenen etiket icin) list olabilir.
    Tek metin cok satirliysa ve etiket yineleniyorsa satirlar sirayla dagitilir."""
    p = data.norm_profile(profile)
    skip = B.detail_tags(p) | B.na_tags(p)
    labels = label_tags(p)
    occ = {}
    totals = {}
    leaves = []
    for name, sdt in tpl.all_sdts():
        pr = sdt_props(sdt)
        key = pr['tag'] or pr['alias']
        if not key or pr['tag'] in skip:
            continue
        if is_container_sdt(sdt) or inside_nc_summary_table(sdt) or pr['tag'] in labels:
            continue
        leaves.append((name, sdt, pr, key))
        totals[key] = totals.get(key, 0) + 1
    n_written = 0
    for name, sdt, pr, key in leaves:
        v = _values_for_key(values, pr['tag'], pr['alias'])
        if v is None:
            continue
        i = occ.get(key, 0)
        occ[key] = i + 1
        if isinstance(v, (list, tuple)):
            v = v[i] if i < len(v) else ''
        elif totals[key] > 1 and '\n' in str(v):
            lines = [x for x in str(v).split('\n') if x.strip()]
            v = lines[i] if i < len(lines) else ''
        if write_leaf(sdt, v, pr):
            tpl.changed.add(name)
            n_written += 1
    if _write_plain_labeled_cells(tpl, values):
        n_written += 1
    return n_written


def _plain_label_map(values):
    def pick(keys):
        for k in keys:
            v = values.get(k)
            if isinstance(v, str) and v.strip():
                return v
        return ''
    m = {'companyname': pick(('OWNERCOMPANY', 'COMPANY_NAME')),
         'sitename': pick(('SITE_NAME', 'SITE', 'LOCATION_NAME')),
         'siteaddress': pick(('SITE_ADDRESS', 'CERTIFIED_SITE_ADDRESS', 'ADDRESS', 'COMPANY_ADDRESS')),
         'certifiedsiteaddress': pick(('CERTIFIED_SITE_ADDRESS', 'SITE_ADDRESS', 'ADDRESS', 'COMPANY_ADDRESS')),
         'address': pick(('ADDRESS', 'SITE_ADDRESS', 'CERTIFIED_SITE_ADDRESS', 'COMPANY_ADDRESS')),
         'country': pick(('COUNTRY', 'SITE_COUNTRY'))}
    return {k: v for k, v in m.items() if v.strip()}


PLAIN_LABELS = ('companyname', 'sitename', 'siteaddress', 'certifiedsiteaddress', 'address', 'country')
PLAIN_KEYS = {'companyname': 'OWNERCOMPANY', 'sitename': 'SITE_NAME', 'siteaddress': 'SITE_ADDRESS',
              'certifiedsiteaddress': 'CERTIFIED_SITE_ADDRESS', 'address': 'ADDRESS', 'country': 'COUNTRY'}


def plain_fields(tpl: DocxTemplate):
    """Icerik denetimi olmayan etiketli hucreler (CP/AB/SD 'Company name', 'Site name', 'Address', 'Country' ...) form alani
    olarak: scan_fields ile ayni sozluk bicimi, kind='plain'. Yazma _write_plain_labeled_cells ile, okuma read_report ile yapilir."""
    out, seen = [], set()
    for label, target in plain_labeled_cells(tpl):
        key = PLAIN_KEYS[label]
        if key in seen:
            continue
        seen.add(key)
        row = target.getparent()
        cells = row_cells(row)
        i = cells.index(target) if target in cells else 0
        shown = normalize_text(node_text(cells[i - 1])) if i > 0 else label
        out.append({'key': key, 'tag': '', 'alias': '', 'kind': 'plain', 'items': [], 'date_format': '', 'placeholder_showing': False,
                    'occurrence': 0, 'repeats': 1, 'label': shown or label, 'hint': '', 'group': group_title(target) or 'Diğer',
                    'value': normalize_import_value(node_text(target))})
    return out


def plain_labeled_cells(tpl: DocxTemplate):
    """Denetimi olmayan etiket/deger hucre ciftleri: [(etiket, hedef_hucre)]."""
    out = []
    # ayni bilgi icin icerik denetimi varsa (FS/PM OWNERCOMPANY) duz hucre kullanilmaz: FS'de 'Company name' satirinin
    # yanindaki hucre bir deger yuvasi degil, 'Site code' etiketidir
    has_control = {sdt_props(s)['tag'] for _n, s in tpl.all_sdts()}
    for row in tpl.document.iter(w('tr')):
        if inside_nc_summary_table(row):
            continue
        cells = row_cells(row)
        for i in range(len(cells) - 1):
            label = compact(normalize_text(node_text(cells[i])))
            if label not in PLAIN_LABELS or PLAIN_KEYS[label] in has_control:
                continue
            target = cells[i + 1]
            if next(target.iter(w('sdt')), None) is not None:
                continue
            out.append((label, target))
    return out


def _write_plain_labeled_cells(tpl, values):
    m = _plain_label_map(values)
    changed = False
    for label, target in plain_labeled_cells(tpl):
        v = m.get(label, '')
        if not v.strip() or normalize_text(v) == normalize_text(node_text(target)):
            continue
        replace_cell_text(target, v)
        tpl.changed.add('word/document.xml')
        changed = True
    return changed


# ----------------------------------------------------------------------------- yazma: detayli rapor kutulari
def write_boxes(tpl: DocxTemplate, rows):
    """merge_for_export() satirlarini (ve NA kutu satirlarini) resmi etiketlere yazar; kapsayici/NC tablosu atlanir."""
    by_tag = {}
    for r in rows:
        v = str(r.get('value') or '')
        if r.get('tag') and v.strip():
            by_tag[str(r['tag'])] = v
    upper = {k.upper(): v for k, v in by_tag.items()}
    n = 0
    for name, sdt in tpl.all_sdts():
        tag = sdt_props(sdt)['tag']
        if not tag:
            continue
        v = by_tag.get(tag, upper.get(tag.upper()))
        if v is None:
            continue
        if is_container_sdt(sdt) or inside_nc_summary_table(sdt):
            continue
        if replace_sdt_text(sdt, v):
            tpl.changed.add(name)
            n += 1
    return n


# ----------------------------------------------------------------------------- NA tablolari (satir satir)
def _is_na_table(tbl) -> bool:
    rows = direct_rows(tbl)
    if not rows:
        return False
    first = compact(normalize_text(node_text(rows[0])))
    allc = compact(normalize_text(node_text(tbl)))
    return ('nonapplicableclauses' in first or 'detailsofnonapplicable' in first) or \
        ('clausesectionref' in allc and 'justification' in allc and len(rows) <= 6)


def na_tables(tpl: DocxTemplate, profile):
    """[(bolum, tablo)] - NA etiketi kutu haritasinda olmayan NA tablolari; bolum = belge sirasinda
    tablodan once gelen son detayli kutunun bolumu."""
    p = data.norm_profile(profile)
    dtags = B.detail_tags(p)
    leaf_na = B.na_tags(p)
    out, chapter = [], None
    doc = tpl.document
    for el in doc.iter(w('sdt'), w('tbl')):
        if el.tag == w('sdt'):
            tag = sdt_props(el)['tag']
            if tag in dtags:
                bx = B.box_by_tag(p, tag)
                if bx:
                    chapter = B.chapter_of(bx['clause'])
            continue
        if chapter is None or not _is_na_table(el):
            continue
        if any(sdt_props(s)['tag'] in leaf_na for s in el.iter(w('sdt'))):
            continue                                    # yaprak NA etiketi var: kutu satiri olarak yazilir
        if ancestor(el, 'tbl') is not None:
            continue
        out.append((chapter, el))
    # ayni bolum icin ilk tablo kullanilir
    seen, uniq = set(), []
    for ch, t in out:
        if ch not in seen:
            seen.add(ch)
            uniq.append((ch, t))
    return uniq


def _na_data_rows(tbl):
    rows = direct_rows(tbl)
    out = []
    for i, r in enumerate(rows):
        if i == 0:
            continue
        cells = row_cells(r)
        if len(cells) != 2:
            continue
        c = compact(normalize_text(node_text(r)))
        if 'clausesectionref' in c or 'justification' in c:
            continue
        out.append(r)
    return out


def write_na_tables(tpl: DocxTemplate, profile, na_clauses):
    by_ch = {}
    for row in na_clauses or []:
        ref = B.normalize_clause(row.get('clause_ref'))
        if ref:
            by_ch.setdefault(B.chapter_of(ref), []).append((ref, str(row.get('justification') or '').strip()))
    n = 0
    for ch, tbl in na_tables(tpl, profile):
        items = by_ch.get(ch)
        if not items:
            continue
        data_rows = _na_data_rows(tbl)
        if not data_rows:
            continue
        template_row = copy.deepcopy(data_rows[0])
        anchor = data_rows[0]
        parent = anchor.getparent()
        idx = parent.index(anchor)
        for r in data_rows:
            r.getparent().remove(r)
        for k, (ref, just) in enumerate(items):
            nr = copy.deepcopy(template_row)
            cells = row_cells(nr)
            replace_cell_text(cells[0], ref)
            replace_cell_text(cells[1], just)
            parent.insert(idx + k, nr)
        _remove_placeholder_flag(tbl)
        tpl.changed.add('word/document.xml')
        n += len(items)
    return n


# ----------------------------------------------------------------------------- resmi satir tablolari
def official_table_type(tbl) -> str:
    c = compact(normalize_text(node_text(tbl)))
    if 'presentataudit' in c and 'openingmeeting' in c and 'closingmeeting' in c:
        return 'present_at_audit'
    if 'keypersonnel' in c and 'openingmeeting' in c and 'closingmeeting' in c:
        return 'present_at_audit'
    if ('gfsibenchmarkedaudithistory' in c or 'gfsipostfarmgateaudithistory' in c or 'gfsiaudithistory' in c) and 'announced' in c:
        return 'gfsi_history'
    if 'auditteamattendance' in c and ('starttimeendtime' in c or 'auditatestarttime' in c):
        return 'audit_team'
    if 'auditdurationperday' in c and 'starttime' in c and 'finishtime' in c:
        return 'audit_duration_days'
    return ''


TABLE_COLUMNS = {
    'gfsi_history': ['date', 'scheme', 'announced', 'outcome'],
    'audit_team': ['first_name', 'second_name', 'auditor_number', 'role', 'audit_date', 'start_time', 'end_time', 'presence',
                   'professional_recognition'],
    'audit_duration_days': ['audit_day', 'date', 'start_time', 'finish_time'],
}
TABLE_LABELS = {
    'present_at_audit': 'Present at audit', 'gfsi_history': 'GFSI audit history', 'audit_team': 'Audit team attendance',
    'audit_duration_days': 'Audit duration per day',
}
COLUMN_LABELS = {
    'name': 'Name', 'job_title': 'Job title', 'name_job_title': 'Name / Job title', 'opening_meeting': 'Opening meeting',
    'site_inspection': 'Site inspection', 'procedure_review': 'Procedure review', 'closing_meeting': 'Closing meeting',
    'date': 'Date', 'scheme': 'Scheme / standard', 'announced': 'Announced / unannounced', 'outcome': 'Pass / fail',
    'first_name': 'First name', 'second_name': 'Second name', 'auditor_number': 'Auditor number', 'role': 'Role',
    'audit_date': 'Audit date', 'start_time': 'Start time', 'end_time': 'End time', 'presence': 'Presence',
    'professional_recognition': 'Professional recognition', 'audit_day': 'Audit day', 'finish_time': 'Finish time',
}


_HEADER_MAP = {
    'audit_duration_days': (('auditday', 'audit_day'), ('auditdate', 'date'), ('date', 'date'), ('starttime', 'start_time'),
                            ('finishtime', 'finish_time'), ('endtime', 'finish_time')),
    'gfsi_history': (('date', 'date'), ('scheme', 'scheme'), ('announced', 'announced'), ('pass', 'outcome'), ('outcome', 'outcome')),
    'present_at_audit': (('namejobtitle', 'name_job_title'), ('jobtitle', 'job_title'), ('title', 'job_title'), ('name', 'name'),
                         ('opening', 'opening_meeting'), ('siteinspection', 'site_inspection'), ('inspection', 'site_inspection'),
                         ('procedure', 'procedure_review'), ('closing', 'closing_meeting')),
    'audit_team': (('firstname', 'first_name'), ('secondname', 'second_name'), ('surname', 'second_name'),
                   ('auditornumber', 'auditor_number'), ('role', 'role'), ('auditdate', 'audit_date'), ('starttime', 'start_time'),
                   ('endtime', 'end_time'), ('presence', 'presence'), ('remote', 'presence'), ('physical', 'presence'),
                   ('professional', 'professional_recognition'), ('recognition', 'professional_recognition')),
}


def _header_columns(kind, tbl):
    """Sutunlari tablonun kendi baslik satirindan cikarir (SD406 suresi 3 sutunlu: Audit Date / Start / Finish)."""
    rows = direct_rows(tbl)
    head = next((r for r in rows if _looks_header(r) or (len(_row_cell_list(r)) >= 3 and not row_cells(r))), None)
    if head is None:
        return []
    cols = []
    for cell in _row_cell_list(head):
        c = compact(normalize_text(node_text(cell)))
        cols.append(next((key for word, key in _HEADER_MAP[kind] if word in c), ''))
    data = next((r for r in rows[rows.index(head) + 1:] if len(row_cells(r)) == len(cols)), None)
    return cols if cols and data is not None and any(cols) else []


def official_table_columns(kind, tbl):
    if kind in TABLE_COLUMNS:
        cols = _header_columns(kind, tbl)
        return cols if cols else list(TABLE_COLUMNS[kind])
    if kind == 'present_at_audit':
        cols = _header_columns(kind, tbl)
        if cols and all(cols):
            return cols
        rows = direct_rows(tbl)
        head = compact(normalize_text(node_text(rows[0]))) if rows else ''
        has_site, has_job = 'siteinspection' in head, 'jobtitle' in head
        for r in rows:
            n = len(row_cells(r))
            if n == 5:
                if has_job and not has_site:
                    return ['name', 'job_title', 'opening_meeting', 'procedure_review', 'closing_meeting']
                return ['name_job_title', 'opening_meeting', 'site_inspection', 'procedure_review', 'closing_meeting']
            if n == 6:
                return ['name', 'job_title', 'opening_meeting', 'site_inspection', 'procedure_review', 'closing_meeting']
    return []


_HEAD_WORDS = ('namejobtitle', 'jobtitle', 'openingmeeting', 'siteinspection', 'procedurereview', 'closingmeeting', 'schemestandard',
               'announced', 'auditornumber', 'starttime', 'finishtime', 'endtime', 'auditday', 'firstname', 'secondname')


def _looks_header(row) -> bool:
    """Baslik satiri: en az iki sutun basligi sozcugu ayni satirda (tek sozcuk veri satirinda da gecebilir)."""
    c = compact(normalize_text(node_text(row)))
    return sum(1 for x in _HEAD_WORDS if x in c) >= 2


def _data_start(rows, expected):
    for i, r in enumerate(rows):
        if len(row_cells(r)) != expected or _looks_header(r):
            continue
        return i
    return -1


def generic_tables(tpl: DocxTemplate):
    """Resmi listede olmayan, basligi etiket denetimlerinden olusan ve altinda duz veri satirlari olan tablolar
    (Consultant, Company Locations, Additional Locations ...). Donus: [(anahtar, baslik, tablo, kolonlar, etiketler)].
    Anahtar = tabloyu saran denetimin etiketi ya da baslik denetimlerinin ilk etiketi; sablondan turetilir."""
    out, seen = [], set()
    for tbl in tpl.document.iter(w('tbl')):
        if official_table_type(tbl) or action_plan_table_type(tbl) or critical_table(tbl) or is_official_nc_or_action_table(tbl):
            continue
        rows = direct_rows(tbl)
        for i, r in enumerate(rows):
            cells = _row_cell_list(r)
            if len(cells) < 2:
                continue
            ctrls = []
            for c in cells:
                inner = list(c.iter(w('sdt')))
                holder = ancestor(c, 'sdt')
                ctrls.append(inner[0] if inner else (holder if holder is not None and ancestor(holder, 'tr') is r else None))
            if not all(x is not None and is_label_row_control(x) for x in ctrls):
                continue
            data_rows = [x for x in rows[i + 1:] if len(row_cells(x)) == len(cells) and next(x.iter(w('sdt')), None) is None]
            if not data_rows:
                continue
            labels = [normalize_text(node_text(c)) for c in cells]
            tags = [sdt_props(x)['tag'] for x in ctrls]
            holder = ancestor(tbl, 'sdt')
            key = (sdt_props(holder)['tag'] if holder is not None else '') or tags[0] or 'TABLE'
            if key in seen:
                continue
            seen.add(key)
            title = normalize_text(node_text(rows[0])) if i > 0 else (sdt_props(holder)['alias'] if holder is not None else key)
            cols = [compact(l) or ('c%d' % k) for k, l in enumerate(labels)]
            out.append(('table:' + key, title[:60] or key, tbl, cols, labels))
            break
    return out


def write_generic_tables(tpl: DocxTemplate, report_tables):
    n = 0
    for key, _title, tbl, cols, _labels in generic_tables(tpl):
        items = _normalize_items((report_tables or {}).get(key), cols)
        if not items:
            continue
        rows = direct_rows(tbl)
        start = next(k for k, r in enumerate(rows) if len(row_cells(r)) == len(cols) and next(r.iter(w('sdt')), None) is None)
        _replace_rows(tbl, start, copy.deepcopy(rows[start]), cols, items)
        _remove_placeholder_flag(tbl)
        tpl.changed.add('word/document.xml')
        n += 1
    return n


def official_tables(tpl: DocxTemplate):
    """{tur: (tablo, kolonlar)} - her turden ilk tablo."""
    out = {}
    for tbl in tpl.document.iter(w('tbl')):
        kind = official_table_type(tbl)
        if not kind or kind in out:
            continue
        cols = official_table_columns(kind, tbl)
        if cols:
            out[kind] = (tbl, cols)
    return out


def _normalize_items(items, columns):
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        row, has = {}, False
        for col in columns:
            v = str(it.get(col) or '')
            if col == 'name_job_title' and not v.strip():
                name, job = str(it.get('name') or '').strip(), str(it.get('job_title') or '').strip()
                v = (name + (' / ' + job if job else '')).strip()
            row[col] = v
            has = has or bool(v.strip())
        if has:
            out.append(row)
    return out


def _replace_rows(tbl, start, template_row, columns, items):
    rows = direct_rows(tbl)
    for r in rows[start:]:
        tbl.remove(r)
    if not items:
        blank = copy.deepcopy(template_row)
        for c in row_cells(blank):
            replace_cell_text(c, '')
        tbl.append(blank)
        return
    for item in items:
        r = copy.deepcopy(template_row)
        for i, c in enumerate(row_cells(r)):
            col = columns[i] if i < len(columns) else ''
            replace_cell_text(c, item.get(col, '') if col else '')
        tbl.append(r)


def write_report_tables(tpl: DocxTemplate, report_tables):
    n = 0
    for kind, (tbl, cols) in official_tables(tpl).items():
        items = _normalize_items((report_tables or {}).get(kind), cols)
        if not items:
            continue                                     # bos tablo sablondaki haliyle kalir
        rows = direct_rows(tbl)
        start = _data_start(rows, len(cols))
        if start < 0:
            continue
        _replace_rows(tbl, start, copy.deepcopy(rows[start]), cols, items)
        _remove_placeholder_flag(tbl)
        tpl.changed.add('word/document.xml')
        n += 1
    return n


# ----------------------------------------------------------------------------- NC eylem plani
AP8 = ['no', 'clause', 'detail', 'correction', 'preventive_action', 'root_cause', 'date_reviewed', 'reviewed_by']
AP7 = AP8[1:]
AP_LABELS = {'no': 'No.', 'clause': 'Clause', 'detail': 'Detail', 'correction': 'Correction',
             'preventive_action': 'Proposed preventive action plan', 'root_cause': 'Root cause analysis',
             'date_reviewed': 'Date reviewed', 'reviewed_by': 'Reviewed by'}
_NC_PREFIX = re.compile(r'^\s*(?:minor|major|critical|fundamental)\s*(?:nc|non[-\s]?conformit(?:y|ies)|nonconformit(?:y|ies))\s*[:：;,.\-–—]*\s*', re.I)


def action_plan_table_type(tbl) -> str:
    c = compact(normalize_text(node_text(tbl)))
    if 'clausedetailcorrection' in c and 'proposedpreventiveactionplan' in c and 'rootcauseanalysis' in c:
        if 'minor' in c:
            return 'minor'
        if 'major' in c:
            return 'major'
    rows = direct_rows(tbl)
    if len(rows) >= 2:
        first = compact(normalize_text(node_text(rows[0])))
        if first in ('major', 'minor') and any(len(row_cells(r)) in (7, 8) for r in rows[1:]):
            return first
    return ''


def _ap_columns_from_cells(cells):
    cols = []
    for cell in cells:
        label = normalize_text(node_text(cell)).lower()
        c = compact(label)
        if re.match(r'^no\.?$', label.strip()) or c == 'no':
            cols.append('no')
        elif 'clause' in c:
            cols.append('clause')
        elif 'detail' in c:
            cols.append('detail')
        elif 'correction' in c and 'corrective' not in c:
            cols.append('correction')
        elif 'proposedpreventiveactionplan' in c or 'preventiveactionplan' in c:
            cols.append('preventive_action')
        elif 'rootcauseanalysis' in c:
            cols.append('root_cause')
        elif 'datereviewed' in c or c == 'date':
            cols.append('date_reviewed')
        elif 'reviewedby' in c:
            cols.append('reviewed_by')
        else:
            cols.append('')
    return cols


def _ap_layout(tbl):
    """(baslangic_satiri, sablon_satir, kolonlar) ya da None - fill_action_plan_table() ile ayni karar."""
    rows = direct_rows(tbl)
    header = -1
    for i, r in enumerate(rows):
        c = compact(normalize_text(node_text(r)))
        if 'clause' in c and 'detail' in c and 'correction' in c and 'rootcauseanalysis' in c:
            header = i
            break
    if header >= 0:
        cells = row_cells(rows[header])
        if len(cells) >= 6:
            cols = _ap_columns_from_cells(cells)
        else:
            cols = []
            for r in rows[header + 1:]:
                n = len(row_cells(r))
                if n == 8:
                    cols = list(AP8)
                    break
                if n == 7:
                    cols = list(AP7)
                    break
        tpl_row = next((r for r in rows[header + 1:] if len(row_cells(r)) >= len(cols)), None) if cols else None
        if not cols or tpl_row is None:
            return None
        return header + 1, tpl_row, cols
    for i, r in enumerate(rows[1:], start=1):
        n = len(row_cells(r))
        if n == 8:
            return i, r, list(AP8)
        if n == 7:
            return i, r, list(AP7)
    return None


def action_plan_tables(tpl: DocxTemplate):
    """{'major': (tablo, duzen), 'minor': ...} - her turden ilk resmi tablo."""
    out = {}
    for tbl in tpl.document.iter(w('tbl')):
        kind = action_plan_table_type(tbl)
        if not kind or kind in out:
            continue
        lay = _ap_layout(tbl)
        if lay:
            out[kind] = (tbl, lay)
    return out


def clean_nc_text(text) -> str:
    t = _NC_PREFIX.sub('', str(text or '').strip())
    # Report Studio'daki desen geri izleyip "4.4.1 Kapi" -> "1 Kapi" yapiyordu; madde numarasi tam eslesmeli
    t = re.sub(r'^\s*\d{1,2}(?:\.\d{1,2}){1,4}(?![\d])(?:\s*(?::|：|;|,|-|–|—|\))|\.(?!\d)|\s)\s*', '', t)
    return t.strip()


def nc_clause_text(item) -> str:
    for k in ('detected_clause', 'clause'):
        m = re.match(r'^\d{1,2}(?:\.\d{1,2}){0,4}', str(item.get(k) or '').strip())
        if m:
            return m.group(0)
    text = _NC_PREFIX.sub('', str(item.get('nc_text') or item.get('detail') or ''))
    m = re.match(r'^\s*(\d{1,2}(?:\.\d{1,2}){1,4})\s*(?::|：|;|,|\.|-|–|—|\)|\s)', text)
    if m:
        return m.group(1)
    return str(item.get('clause') or '')


def action_item_values(item, idx):
    prev = item.get('proposed_preventive_action') or item.get('preventive_action') or item.get('corrective_action') or ''
    return {'no': str(idx + 1), 'clause': nc_clause_text(item), 'detail': clean_nc_text(item.get('nc_text') or item.get('detail') or ''),
            'correction': item.get('correction') or '', 'preventive_action': prev, 'root_cause': item.get('root_cause') or '',
            'date_reviewed': item.get('date_reviewed') or item.get('due_date') or '',
            'reviewed_by': item.get('reviewed_by') or item.get('responsible') or ''}


def write_action_plan(tpl: DocxTemplate, items):
    items = [i for i in (items or []) if isinstance(i, dict)]
    if not items:
        return 0
    n = 0
    for kind, (tbl, (start, tpl_row, cols)) in action_plan_tables(tpl).items():
        rows_for = [i for i in items if (str(i.get('type') or 'minor').lower() in (('major', 'critical', 'fundamental')
                                                                                 if kind == 'major' else (kind,)))]
        if not rows_for:
            continue
        template_row = copy.deepcopy(tpl_row)
        _replace_rows(tbl, start, template_row, cols, [action_item_values(it, k) for k, it in enumerate(rows_for)])
        _remove_placeholder_flag(tbl)
        tpl.changed.add('word/document.xml')
        n += len(rows_for)
    return n


# ----------------------------------------------------------------------------- Critical NC tablosu (FS/PM/CP/AB/SD ana tablo)
def critical_tables(tpl: DocxTemplate):
    """Ilk 'Critical' tablosu (modul tablolari haric): (tablo, baslangic, sablon_satir, kolonlar)."""
    for tbl in tpl.document.iter(w('tbl')):
        if not critical_table(tbl):
            continue
        cont = ancestor(tbl, 'sdt')
        tag = sdt_props(cont)['tag'] if cont is not None else ''
        if tag and 'MODULE' in tag.upper():
            continue
        rows = direct_rows(tbl)
        for i, r in enumerate(rows[1:], start=1):
            cells = row_cells(r)
            if len(cells) < 2:
                continue
            heads = [compact(normalize_text(node_text(c))) for c in cells]
            if any(h in ('refnumber', 'no', 'clause', 'detail') for h in heads) and i + 1 < len(rows):
                cols = []
                for h in heads:
                    cols.append('no' if h in ('refnumber', 'no', 'number') else 'clause' if 'clause' in h else
                                'detail' if 'detail' in h else 'correction' if 'correction' in h else '')
                return tbl, i + 1, rows[i + 1], cols
            cols = ['no', 'clause', 'detail'][:len(cells)] if len(cells) <= 3 else []
            if cols:
                return tbl, i, r, cols
        return None
    return None


def write_critical(tpl: DocxTemplate, items):
    crit = [i for i in (items or []) if isinstance(i, dict) and str(i.get('type') or '').lower() in ('critical', 'fundamental')]
    found = critical_tables(tpl)
    if not crit or not found:
        return 0
    tbl, start, tpl_row, cols = found
    _replace_rows(tbl, start, copy.deepcopy(tpl_row), cols, [action_item_values(it, k) for k, it in enumerate(crit)])
    _remove_placeholder_flag(tbl)
    tpl.changed.add('word/document.xml')
    return len(crit)


# ----------------------------------------------------------------------------- tam yazim / tam okuma
def write_report(project, out_path=None, template=None):
    """Projeyi resmi sablona yazar ve DOCX baytlarini dondurur.
    project: {'profile', 'values', 'sections', 'na_clauses', 'action_plan': {'items': [...]}, 'report_tables': {...}}"""
    p = data.norm_profile(project.get('profile'))
    tpl = DocxTemplate(template or data.template_path(p))
    merged = B.merge_for_export(p, project.get('sections') or [])
    na_rows = B.na_rows_for_export(p, project.get('na_clauses') or [])
    stats = {'fields': write_fields(tpl, project.get('values') or {}, p),
             'boxes': write_boxes(tpl, merged['rows'] + na_rows),
             'na_rows': write_na_tables(tpl, p, project.get('na_clauses') or []),
             'tables': write_report_tables(tpl, project.get('report_tables') or {}) +
             write_generic_tables(tpl, project.get('report_tables') or {}),
             'actions': write_action_plan(tpl, (project.get('action_plan') or {}).get('items') or []),
             'critical': write_critical(tpl, (project.get('action_plan') or {}).get('items') or [])}
    blob = tpl.save(out_path)
    stats['skipped'] = merged['skipped']
    stats['merged'] = merged['merged']
    return blob, stats


def _read_rows(tbl, start, cols):
    out = []
    for r in direct_rows(tbl)[start:]:
        cells = row_cells(r)
        item = {}
        for i, c in enumerate(cells):
            if i < len(cols) and cols[i]:
                item[cols[i]] = normalize_import_value(node_text(c))
        if any(v for v in item.values()):
            out.append(item)
    return out


def read_report(path_or_bytes, filename=''):
    """Dolu (ya da bos) resmi raporu okur: {'profile','values','sections','na_clauses','report_tables','action_plan'}."""
    tpl = DocxTemplate(path_or_bytes)
    p = detect_profile(tpl, filename)
    dtags, ntags = B.detail_tags(p), B.na_tags(p)
    values, detailed, na = {}, [], []
    fields = scan_fields(tpl, p)
    counts = {}
    for f in fields:
        counts[f['key']] = f['repeats']
    for f in fields:
        if counts[f['key']] > 1:
            lst = values.setdefault(f['key'], [''] * counts[f['key']])
            lst[f['occurrence']] = f['value']
        elif f['value'] or f['key'] not in values:
            values[f['key']] = f['value']
    for _n, sdt in tpl.all_sdts():
        pr = sdt_props(sdt)
        if pr['tag'] in dtags:
            v = '' if pr['placeholder_showing'] else sdt_text(sdt)
            if B.is_placeholder(v):
                v = ''
            detailed.append({'tag': pr['tag'], 'value': v})
        elif pr['tag'] in ntags and not pr['placeholder_showing']:
            for line in sdt_text(sdt).split('\n'):
                line = line.strip()
                if not line or B.is_placeholder(line):
                    continue
                m = re.match(r'^(\d+(?:\.\d+)*)\s*(?:[-–—:]\s*(.*))?$', line)
                if m:
                    na.append({'clause_ref': m.group(1), 'justification': (m.group(2) or '').strip()})
    for ch, tbl in na_tables(tpl, p):
        for r in _na_data_rows(tbl):
            cells = row_cells(r)
            ref, just = normalize_import_value(node_text(cells[0])), normalize_import_value(node_text(cells[1]))
            if ref and not B.is_placeholder(ref):
                na.append({'clause_ref': B.normalize_clause(ref) or ref, 'justification': just})
    for label, target in plain_labeled_cells(tpl):
        v = normalize_import_value(node_text(target))
        key = PLAIN_KEYS[label]
        if v and not values.get(key):
            values[key] = v
    tables = {}
    for kind, (tbl, cols) in official_tables(tpl).items():
        rows = direct_rows(tbl)
        start = _data_start(rows, len(cols))
        if start >= 0:
            items = _read_rows(tbl, start, cols)
            if items:
                tables[kind] = items
    for key, _title, tbl, cols, _labels in generic_tables(tpl):
        rows = direct_rows(tbl)
        start = next((k for k, r in enumerate(rows) if len(row_cells(r)) == len(cols) and next(r.iter(w('sdt')), None) is None), -1)
        if start >= 0:
            items = _read_rows(tbl, start, cols)
            if items:
                tables[key] = items
    actions = []
    for kind, (tbl, (start, _t, cols)) in action_plan_tables(tpl).items():
        for it in _read_rows(tbl, start, cols):
            it.pop('no', None)
            if it.get('clause') or it.get('detail'):
                it['type'] = kind
                it['nc_text'] = it.pop('detail', '')
                actions.append(it)
    found = critical_tables(tpl)
    if found:
        tbl, start, _r, cols = found
        for it in _read_rows(tbl, start, cols):
            it.pop('no', None)
            if it.get('clause') or it.get('detail'):
                it['type'] = 'critical'
                it['nc_text'] = it.pop('detail', '')
                actions.append(it)
    sections = B.merge_imported(p, detailed)
    return {'profile': p, 'values': values, 'sections': sections, 'na_clauses': na, 'report_tables': tables,
            'action_plan': {'items': actions}}
