# -*- coding: utf-8 -*-
"""Kucuk bir .xlsx yazici (yalnizca standart kutuphane).

Uygulamanin dis bagimliligi olmasin diye openpyxl yerine burasi kullaniliyor.
Yapabildigi kadari: birden cok sayfa, kalin baslik satiri, dondurulmus ust
satir, otomatik filtre, sutun genisligi, sayi ve metin hucreleri. Formul,
grafik ve bicim kurali yok; rapor ciktisi icin fazlasi gerekmiyor.
"""
from __future__ import annotations

import datetime
import pathlib
import re
import zipfile
from mihenk_i18n import t

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
%s
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2">
<font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
</fonts>
<fills count="3">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF2F6FD0"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="3">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""

ILLEGAL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')


def _escape(value: str) -> str:
    value = ILLEGAL.sub('', value)
    return (value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def _column_name(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    name = ''
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _cell(reference: str, value, style: int) -> str:
    if value is None or value == '':
        return ''
    if _is_number(value):
        return '<c r="%s" s="%d"><v>%s</v></c>' % (reference, style, repr(float(value))
                                                   if isinstance(value, float) else value)
    if isinstance(value, bool):
        value = t('evet') if value else t('hayır')
    if isinstance(value, (datetime.date, datetime.datetime)):
        value = value.isoformat(sep=' ')
    return ('<c r="%s" s="%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
            % (reference, style, _escape(str(value))))


def _sheet_xml(sheet: dict) -> str:
    headers = sheet.get('headers') or []
    rows = sheet.get('rows') or []
    widths = sheet.get('widths') or []
    wrap = set(sheet.get('wrap_columns') or ())

    parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
    if widths:
        parts.append('<cols>')
        for index, width in enumerate(widths, start=1):
            parts.append('<col min="%d" max="%d" width="%s" customWidth="1"/>'
                         % (index, index, float(width)))
        parts.append('</cols>')
    parts.append('<sheetData>')

    line = 1
    if headers:
        cells = ''.join(_cell('%s%d' % (_column_name(i), line), text, 1)
                        for i, text in enumerate(headers))
        parts.append('<row r="%d">%s</row>' % (line, cells))
        line += 1
    for row in rows:
        cells = ''.join(_cell('%s%d' % (_column_name(i), line), value,
                              2 if i in wrap else 0)
                        for i, value in enumerate(row))
        parts.append('<row r="%d">%s</row>' % (line, cells))
        line += 1
    parts.append('</sheetData>')

    if headers:
        last = '%s%d' % (_column_name(len(headers) - 1), max(1, line - 1))
        parts.append('<autoFilter ref="A1:%s"/>' % last)
    parts.append('</worksheet>')

    body = ''.join(parts)
    if headers:
        freeze = ('<sheetViews><sheetView workbookViewId="0">'
                  '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
                  '</sheetView></sheetViews>')
        body = body.replace('<sheetData>', freeze + '<sheetData>', 1)
    return body


def _safe_title(title: str, used) -> str:
    """Excel sayfa adi kurallari: 31 karakter, bazi isaretler yasak, benzersiz."""
    name = re.sub(r'[\\/*?:\[\]]', '-', str(title or t('Sayfa'))).strip() or t('Sayfa')
    name = name[:31]
    base, counter = name, 2
    while name.lower() in used:
        suffix = ' (%d)' % counter
        name = base[:31 - len(suffix)] + suffix
        counter += 1
    used.add(name.lower())
    return name


def write(path, sheets) -> pathlib.Path:
    """Calisma kitabini yazar.

    sheets: [{'title': str, 'headers': [...], 'rows': [[...]],
              'widths': [...], 'wrap_columns': (indeks,...)}]
    """
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sheets = [s for s in (sheets or []) if s is not None] or [{'title': t('Boş'), 'headers': [], 'rows': []}]

    used = set()
    for sheet in sheets:
        sheet['_name'] = _safe_title(sheet.get('title'), used)

    overrides = '\n'.join(
        '<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        % (index + 1) for index in range(len(sheets)))

    workbook = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"',
                ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
                '<sheets>']
    rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for index, sheet in enumerate(sheets, start=1):
        workbook.append('<sheet name="%s" sheetId="%d" r:id="rId%d"/>'
                        % (_escape(sheet['_name']), index, index))
        rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>'
                    % (index, index))
    workbook.append('</sheets></workbook>')
    rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                % (len(sheets) + 1))
    rels.append('</Relationships>')

    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as book:
        book.writestr('[Content_Types].xml', CONTENT_TYPES % overrides)
        book.writestr('_rels/.rels', ROOT_RELS)
        book.writestr('xl/workbook.xml', ''.join(workbook))
        book.writestr('xl/_rels/workbook.xml.rels', ''.join(rels))
        book.writestr('xl/styles.xml', STYLES)
        for index, sheet in enumerate(sheets, start=1):
            book.writestr('xl/worksheets/sheet%d.xml' % index, _sheet_xml(sheet))
    return path
