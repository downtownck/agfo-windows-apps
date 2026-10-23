# -*- coding: utf-8 -*-
"""AGFO AI Editor 1.4 - bicimli belge modeli (Tk yok).

Belge = blok listesi:
  {'t': 'p', 'style': 'normal'|'h1'|'h2'|'h3'|'quote', 'list': None|'bullet'|'number', 'level': 0..3,
   'align': None|'center'|'right'|'justify', 'pb': bool (oncesinde sayfa sonu), 'runs': [run, ...]}
  {'t': 'img', 'data': bytes, 'ext': 'png'|'jpeg'|'gif'|'bmp', 'w': pt, 'h': pt, 'align': ...}
  {'t': 'table', 'rows': [[runs, runs, ...], ...]}      (her hucre tek paragraf: run listesi)
run = {'text': str, 'b': bool, 'i': bool, 'u': bool, 'color': 'RRGGBB'|None}
  2.0 (yalniz kullanildiginda bulunur): 'font': aile, 'size': pt, 's': ustu cizili, 'va': 'sup'|'sub',
  'hl': vurgu 'RRGGBB', 'href': baglanti adresi
paragraf 2.0 (istege bagli): 'ls': satir araligi carpani, 'sb'/'sa': oncesi/sonrasi bosluk pt, 'ind': sol girinti pt,
  'fi': ilk satir girintisi pt (eksi = asili)
sayfa (belge duzeyi, DOCX sectPr + ust/alt bilgi): bkz. DEFAULT_PAGE

Donusumler: DOCX <-> bloklar (bicim, liste, tablo, resim), Markdown <-> bloklar (AI'a giden/gelen metin,
.md dosyalari), HTML -> Markdown (AI Manager yanitlari, .html dosyalari), bloklar -> HTML.
AI'a giden Markdown'da resimler ![resim:ID] yer tutucusuyla gider; yanit geri cevrilirken ayni resim yerine konur.
"""
from __future__ import annotations

import base64
import copy
import datetime
import html
import html.parser
import io
import os
import re
import struct
import zipfile
from xml.etree import ElementTree as ET

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
A_NS = 'http://schemas.openxmlformats.org/drawingml/2006/main'
WP_NS = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
PIC_NS = 'http://schemas.openxmlformats.org/drawingml/2006/picture'
V_NS = 'urn:schemas-microsoft-com:vml'
REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'
EMU_PER_PT = 12700
PAGE_W_PT, MARGIN_PT = 595.3, 70.9          # A4, 2,5 cm kenar
CONTENT_W_PT = PAGE_W_PT - 2 * MARGIN_PT
STYLES = ('normal', 'h1', 'h2', 'h3', 'quote')
STYLE_LABELS = {'normal': 'Normal metin', 'h1': 'Başlık 1', 'h2': 'Başlık 2', 'h3': 'Başlık 3', 'quote': 'Alıntı'}
IMG_EXT = {'png': 'image/png', 'jpeg': 'image/jpeg', 'gif': 'image/gif', 'bmp': 'image/bmp'}
RUN_EXTRA = ('font', 'size', 's', 'va', 'hl', 'href')          # 2.0
PARA_EXTRA = ('ls', 'sb', 'sa', 'ind', 'fi')                    # 2.0
PAGE_SIZES = {'A4': (595.3, 841.9), 'A5': (419.5, 595.3), 'Letter': (612.0, 792.0), 'Legal': (612.0, 1008.0)}
PAGE_SIZE_LABELS = {'A4': 'A4 (21 × 29,7 cm)', 'A5': 'A5 (14,8 × 21 cm)', 'Letter': 'Letter (21,6 × 27,9 cm)',
                    'Legal': 'Legal (21,6 × 35,6 cm)'}
MARGIN_PRESETS = {'normal': (70.9, 70.9, 70.9, 70.9), 'narrow': (36.0, 36.0, 36.0, 36.0), 'wide': (72.0, 72.0, 144.0, 144.0),
                  'moderate': (72.0, 72.0, 54.0, 54.0)}
MARGIN_LABELS = {'normal': 'Normal (2,5 cm)', 'narrow': 'Dar (1,27 cm)', 'moderate': 'Orta (2,54 / 1,9 cm)', 'wide': 'Geniş (2,54 / 5,08 cm)'}
DEFAULT_PAGE = {'size': 'A4', 'orient': 'portrait', 'margins': {'t': 70.9, 'b': 70.9, 'l': 70.9, 'r': 70.9},
                'header': '', 'footer': '', 'pnum': None}
# pnum: None | {'pos': 'footer'|'header', 'align': 'left'|'center'|'right', 'fmt': 'n'|'n_of_N'}
HIGHLIGHTS = {'yellow': 'FFFF00', 'green': '00FF00', 'cyan': '00FFFF', 'magenta': 'FF00FF', 'blue': '0000FF', 'red': 'FF0000',
              'darkBlue': '000080', 'darkCyan': '008080', 'darkGreen': '008000', 'darkMagenta': '800080', 'darkRed': '800000',
              'darkYellow': '808000', 'darkGray': '808080', 'lightGray': 'C0C0C0', 'black': '000000'}
HIGHLIGHT_BY_HEX = {v: k for k, v in HIGHLIGHTS.items()}
LINE_SPACINGS = (1.0, 1.15, 1.5, 2.0, 2.5, 3.0)


def w(tag):
    return '{%s}%s' % (W_NS, tag)


# ----------------------------------------------------------------------------- yardimcilar
def run(text, b=False, i=False, u=False, color=None, **extra):
    r = {'text': text, 'b': bool(b), 'i': bool(i), 'u': bool(u), 'color': color}
    for k in RUN_EXTRA:                       # 2.0: yalniz kullanilan ozellikler kayda girer
        v = extra.get(k)
        if v:
            r[k] = v
    return r


def run_extra(r):
    return {k: r[k] for k in RUN_EXTRA if r.get(k)}


def para(runs=None, style='normal', lst=None, level=0, align=None, pb=False, text=None, **extra):
    if text is not None:
        runs = [run(text)]
    p = {'t': 'p', 'style': style, 'list': lst, 'level': level, 'align': align, 'pb': pb, 'runs': runs or []}
    for k in PARA_EXTRA:
        v = extra.get(k)
        if _para_extra_set(k, v):
            p[k] = v
    return p


def _para_extra_set(k, v):
    if v is None or v == '':
        return False
    return True if k in ('sb', 'sa') else bool(v)     # 0 pt oncesi/sonrasi bosluk anlamlidir


def para_extra(b):
    return {k: b[k] for k in PARA_EXTRA if _para_extra_set(k, b.get(k))}


def _run_key(r):
    return (r.get('b', False), r.get('i', False), r.get('u', False), r.get('color')) + tuple(r.get(k) or None for k in RUN_EXTRA)


def merge_runs(runs):
    """Ayni bicimli komsu parcalari birlestirir, bos parcalari atar."""
    out = []
    for r in runs:
        if not r.get('text'):
            continue
        key = _run_key(r)
        if out and _run_key(out[-1]) == key:
            out[-1]['text'] += r['text']
        else:
            out.append(run(r['text'], key[0], key[1], key[2], key[3], **run_extra(r)))
    return out


def normalize_page(page):
    """Eksik/bozuk sayfa ayarini varsayilanlarla tamamlar."""
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULT_PAGE.items()}
    if isinstance(page, dict):
        if page.get('size') in PAGE_SIZES:
            out['size'] = page['size']
        if page.get('orient') in ('portrait', 'landscape'):
            out['orient'] = page['orient']
        m = page.get('margins')
        if isinstance(m, dict):
            for k in 't', 'b', 'l', 'r':
                try:
                    v = float(m.get(k, out['margins'][k]))
                    out['margins'][k] = max(0.0, min(300.0, v))
                except (TypeError, ValueError):
                    pass
        for k in 'header', 'footer':
            if isinstance(page.get(k), str):
                out[k] = page[k]
        pn = page.get('pnum')
        if isinstance(pn, dict) and pn.get('pos') in ('header', 'footer'):
            out['pnum'] = {'pos': pn['pos'], 'align': pn.get('align') if pn.get('align') in ('left', 'center', 'right') else 'center',
                           'fmt': 'n_of_N' if pn.get('fmt') == 'n_of_N' else 'n'}
    return out


def page_dims(page):
    """(genislik, yukseklik) pt - yone gore."""
    page = normalize_page(page)
    w_, h_ = PAGE_SIZES[page['size']]
    return (h_, w_) if page['orient'] == 'landscape' else (w_, h_)


def content_width(page):
    page = normalize_page(page)
    return page_dims(page)[0] - page['margins']['l'] - page['margins']['r']


def runs_text(runs):
    return ''.join(r['text'] for r in runs)


def block_text(b):
    if b['t'] == 'p':
        return runs_text(b['runs'])
    if b['t'] == 'table':
        return '\n'.join('\t'.join(runs_text(c) for c in row) for row in b['rows'])
    return ''


def plain_text(blocks):
    out = []
    n = 0
    for b in blocks:
        if b['t'] == 'p':
            prefix = ''
            if b.get('list') == 'bullet':
                prefix = '  ' * b.get('level', 0) + '• '
            elif b.get('list') == 'number':
                n += 1
                prefix = '  ' * b.get('level', 0) + '%d. ' % n
            if b.get('list') != 'number':
                n = 0
            out.append(prefix + runs_text(b['runs']))
        elif b['t'] == 'table':
            n = 0
            out.append(block_text(b))
        else:
            n = 0
    return '\n'.join(out)


def sniff_image(data: bytes):
    """(ext, genislik_px, yukseklik_px) - PNG/JPEG/GIF/BMP basliklarindan; taninmazsa (None, 0, 0)."""
    if data[:8] == b'\x89PNG\r\n\x1a\n' and len(data) > 24:
        w_, h_ = struct.unpack('>II', data[16:24])
        return 'png', w_, h_
    if data[:6] in (b'GIF87a', b'GIF89a'):
        w_, h_ = struct.unpack('<HH', data[6:10])
        return 'gif', w_, h_
    if data[:2] == b'BM' and len(data) > 26:
        w_, h_ = struct.unpack('<ii', data[18:26])
        return 'bmp', w_, abs(h_)
    if data[:2] == b'\xff\xd8':
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h_, w_ = struct.unpack('>HH', data[i + 5:i + 9])
                return 'jpeg', w_, h_
            seg = struct.unpack('>H', data[i + 2:i + 4])[0]
            i += 2 + seg
        return 'jpeg', 0, 0
    return None, 0, 0


def image_block(data: bytes, w_pt=None, h_pt=None, ext=None, align=None):
    kind, pw, ph = sniff_image(data)
    ext = ext or kind
    if ext not in IMG_EXT:
        raise ValueError('Desteklenmeyen resim biçimi (PNG, JPG, GIF, BMP kullanın).')
    if not w_pt or not h_pt:
        pw, ph = pw or 400, ph or 300
        w_pt, h_pt = pw * 0.75, ph * 0.75                 # 96 dpi varsayimi
        if w_pt > CONTENT_W_PT:
            h_pt, w_pt = h_pt * CONTENT_W_PT / w_pt, CONTENT_W_PT
    return {'t': 'img', 'data': data, 'ext': ext, 'w': float(w_pt), 'h': float(h_pt), 'align': align}


# ----------------------------------------------------------------------------- Markdown
_ESC_RX = re.compile(r'([\\*_`])')


def _esc_inline(s):
    return _ESC_RX.sub(r'\\\1', s).replace('<u>', '&lt;u&gt;').replace('</u>', '&lt;/u&gt;')


def runs_to_md(runs):
    out = []
    for r in merge_runs(runs):
        t = _esc_inline(r['text'])
        lead = len(t) - len(t.lstrip(' '))
        trail = len(t) - len(t.rstrip(' '))
        core_ = t.strip(' ')
        if not core_:
            out.append(t)
            continue
        if r['u'] and not r.get('href'):
            core_ = '<u>%s</u>' % core_
        if r.get('s'):
            core_ = '~~%s~~' % core_
        if r['i']:
            core_ = '*%s*' % core_
        if r['b']:
            core_ = '**%s**' % core_
        if r.get('href'):
            core_ = '[%s](%s)' % (core_, r['href'].replace(')', '%29').replace(' ', '%20'))
        out.append(' ' * lead + core_ + ' ' * trail)
    return ''.join(out)


def blocks_to_markdown(blocks, image_ids=None):
    """image_ids: {id(blok): 'kimlik'} - verilirse resimler ![resim:kimlik] olarak yazilir."""
    lines = []
    prev_list = False
    num = {}
    for b in blocks:
        if b['t'] == 'p':
            text = runs_to_md(b['runs'])
            if b.get('list'):
                ind = '  ' * b.get('level', 0)
                if b['list'] == 'number':
                    num[b.get('level', 0)] = num.get(b.get('level', 0), 0) + 1
                    line = '%s%d. %s' % (ind, num[b.get('level', 0)], text)
                else:
                    line = '%s- %s' % (ind, text)
                if not prev_list and lines:
                    lines.append('')
                lines.append(line)
                prev_list = True
                continue
            num = {}
            prev_list = False
            if lines:
                lines.append('')
            st = b.get('style', 'normal')
            if st in ('h1', 'h2', 'h3'):
                lines.append('#' * int(st[1]) + ' ' + text)
            elif st == 'quote':
                lines.append('> ' + text)
            else:
                if re.match(r'^(#{1,6}\s|>\s|[-*+]\s|\d+[.)]\s|\|)', text):
                    text = '\\' + text
                lines.append(text)
        elif b['t'] == 'img':
            num, prev_list = {}, False
            if lines:
                lines.append('')
            key = (image_ids or {}).get(id(b))
            lines.append('![resim:%s]' % key if key else '![resim]')
        elif b['t'] == 'table':
            num, prev_list = {}, False
            if lines:
                lines.append('')
            for ri, row in enumerate(b['rows']):
                lines.append('| ' + ' | '.join(runs_to_md(c).replace('|', '\\|') for c in row) + ' |')
                if ri == 0:
                    lines.append('|' + '|'.join('---' for _ in row) + '|')
    return '\n'.join(lines)


_MD_LINK = re.compile(r'\[((?:\\.|[^\]\\])+)\]\(((?:https?://|mailto:)[^)\s]+)\)')


def md_inline(text, base=None):
    """Satir ici Markdown (** * ~~ <u> [metin](adres)) -> run listesi. Dengesiz isaretler duz metin kalir."""
    base = base or {}
    if not base.get('_nolink') and _MD_LINK.search(text):          # 2.0: baglantilar
        out, pos = [], 0
        for m in _MD_LINK.finditer(text):
            if m.start() > pos:
                out.extend(md_inline(text[pos:m.start()], dict(base, _nolink=True)))
            for r in md_inline(m.group(1), dict(base, _nolink=True)):
                r['href'] = m.group(2)
                r['u'] = True
                if not r.get('color'):
                    r['color'] = '0563C1'
                out.append(r)
            pos = m.end()
        if pos < len(text):
            out.extend(md_inline(text[pos:], dict(base, _nolink=True)))
        return merge_runs(out)
    if '~~' in text and re.sub(r'\\.', '', text).count('~~') % 2 == 0:   # 2.0: ustu cizili
        out, strike = [], False
        for k, piece in enumerate(text.split('~~')):
            if k:
                strike = not strike
            if piece:
                for r in md_inline(piece, dict(base, _nolink=True)):
                    if strike:
                        r['s'] = True
                    out.append(r)
        return merge_runs(out)
    b0, i0, u0, c0 = base.get('b', False), base.get('i', False), base.get('u', False), base.get('color')
    text = text.replace('&lt;u&gt;', '\x00LU\x00').replace('&lt;/u&gt;', '\x00RU\x00')
    # dengesiz isaretleri kacisla
    plain = re.sub(r'\\.', '', text)
    if plain.count('**') % 2:
        text = text.replace('**', '\\*\\*')
    plain = re.sub(r'\\.', '', text).replace('**', '')
    singles = len(re.findall(r'(?<![*\w])\*(?=\S)|(?<=\S)\*(?![*\w])', plain))
    allow_i = singles % 2 == 0
    out, buf = [], []
    b, i, u = b0, i0, u0
    k = 0

    def flush():
        if buf:
            out.append(run(''.join(buf), b, i, u, c0))
            buf.clear()
    while k < len(text):
        ch = text[k]
        if ch == '\\' and k + 1 < len(text):
            buf.append(text[k + 1])
            k += 2
            continue
        if text.startswith('**', k):
            flush()
            b = not b
            k += 2
            continue
        if ch == '*' and allow_i:
            prev = text[k - 1] if k else ' '
            nxt = text[k + 1] if k + 1 < len(text) else ' '
            if (not i and not nxt.isspace()) or (i and not prev.isspace()):
                flush()
                i = not i
                k += 1
                continue
        if text.startswith('<u>', k):
            flush()
            u = True
            k += 3
            continue
        if text.startswith('</u>', k):
            flush()
            u = u0
            k += 4
            continue
        buf.append(ch)
        k += 1
    flush()
    for r in out:
        r['text'] = r['text'].replace('\x00LU\x00', '<u>').replace('\x00RU\x00', '</u>')
    return merge_runs(out)


_MD_IMG = re.compile(r'^!\[([^\]]*)\](?:\(([^)]*)\))?\s*$')
_MD_TABLE_SEP = re.compile(r'^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$')


def _split_row(line):
    s = line.strip()
    if s.startswith('|'):
        s = s[1:]
    if s.endswith('|') and not s.endswith('\\|'):
        s = s[:-1]
    cells = re.split(r'(?<!\\)\|', s)
    return [c.strip().replace('\\|', '|') for c in cells]


def markdown_to_blocks(md, images=None, base_dir=None):
    """Markdown -> bloklar. images: {'kimlik': img_blok}; base_dir: ![](yol) dosyalari icin klasor.
    Bos satir paragraf ayirir; bos olmayan her satir ayri paragraftir (PDF/AI metninin satir yapisi korunur)."""
    images = images or {}
    blocks = []
    lines = (md or '').replace('\r\n', '\n').replace('\r', '\n').split('\n')
    k = 0
    while k < len(lines):
        line = lines[k]
        s = line.strip()
        if not s:
            k += 1
            continue
        m = _MD_IMG.match(s)
        if m:
            alt, src = m.group(1), m.group(2)
            img = None
            if alt.startswith('resim:') and alt[6:] in images:
                img = copy.copy(images[alt[6:]])
            elif src:
                img = _load_image_ref(src, base_dir)
            if img:
                blocks.append(img)
            k += 1
            continue
        if s.startswith('|') and k + 1 < len(lines) and _MD_TABLE_SEP.match(lines[k + 1].strip()):
            rows = [_split_row(s)]
            k += 2
            while k < len(lines) and lines[k].strip().startswith('|'):
                rows.append(_split_row(lines[k]))
                k += 1
            ncol = max(len(r) for r in rows)
            blocks.append({'t': 'table', 'rows': [[md_inline(c) for c in r + [''] * (ncol - len(r))] for r in rows]})
            continue
        hm = re.match(r'^(#{1,6})\s+(.*)$', s)
        if hm:
            lvl = min(3, len(hm.group(1)))
            blocks.append(para(md_inline(hm.group(2).strip().rstrip('#').rstrip()), 'h%d' % lvl))
            k += 1
            continue
        if s.startswith('> ') or s == '>':
            blocks.append(para(md_inline(s[2:].strip()), 'quote'))
            k += 1
            continue
        lm = re.match(r'^(\s*)([-*+•]|\d+[.)])\s+(.*)$', line)
        if lm:
            level = min(3, len(lm.group(1).replace('\t', '  ')) // 2)
            kind = 'number' if lm.group(2)[0].isdigit() else 'bullet'
            blocks.append(para(md_inline(lm.group(3).strip()), lst=kind, level=level))
            k += 1
            continue
        if s.startswith('\\') and len(s) > 1 and s[1] in '#>-*+|0123456789':
            s = s[1:]
        blocks.append(para(md_inline(s)))
        k += 1
    return blocks


def _load_image_ref(src, base_dir):
    src = src.strip().split(' ')[0].strip('<>')
    try:
        if src.startswith('data:'):
            data = base64.b64decode(src.split(',', 1)[1])
        else:
            p = src if os.path.isabs(src) else os.path.join(base_dir or '.', src)
            with open(p, 'rb') as f:
                data = f.read()
        return image_block(data)
    except Exception:
        return None


def markdown_file_text(blocks, md_path):
    """.md dosyasina yazilacak metin; resimler '<ad>_resimler/' klasorune dosya olarak yazilir."""
    folder = os.path.splitext(os.path.basename(md_path))[0] + '_resimler'
    ids, files = {}, {}
    n = 0
    for b in blocks:
        if b['t'] == 'img':
            n += 1
            name = 'resim%d.%s' % (n, 'jpg' if b['ext'] == 'jpeg' else b['ext'])
            ids[id(b)] = name
            files[name] = b['data']
    md = blocks_to_markdown(blocks, ids)
    md = re.sub(r'!\[resim:([^\]]+)\]', lambda m: '![%s](%s/%s)' % (m.group(1), folder, m.group(1)), md)
    return md, {os.path.join(os.path.dirname(os.path.abspath(md_path)), folder, k): v for k, v in files.items()}


# ----------------------------------------------------------------------------- HTML
class _HtmlToMd(html.parser.HTMLParser):
    BLOCK = {'p', 'div', 'section', 'article', 'header', 'footer', 'main', 'aside', 'figure', 'figcaption', 'address', 'center'}

    def __init__(self, images):
        super().__init__(convert_charrefs=True)
        self.out = []          # bitmis satirlar
        self.cur = []          # gecerli paragraf parcalari
        self.prefix = ''
        self.lists = []
        self.skip = 0
        self.images = images
        self.table = None      # [[cell_text,...],...]
        self.cell = None
        self.pre = 0

    def _flush(self):
        text = re.sub(r'[ \t\r\n]+', ' ', ''.join(self.cur)).strip() if not self.pre else ''.join(self.cur).strip('\n')
        if self.cell is not None:
            if text:
                self.cell.append(text)
        elif text:
            if not self.prefix and re.match(r'^(#{1,6}\s|>\s|[-+]\s|\d+[.)]\s|\|)', text):
                text = '\\' + text
            self.out.append(self.prefix + text)
        self.cur = []
        self.prefix = ''

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style', 'head', 'title', 'noscript'):
            self.skip += 1
            return
        if self.skip:
            return
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self._flush()
            self.prefix = '#' * min(3, int(tag[1])) + ' '
        elif tag == 'blockquote':
            self._flush()
            self.prefix = '> '
        elif tag in ('ul', 'ol'):
            self._flush()
            self.lists.append([tag, 0])
        elif tag == 'li':
            self._flush()
            depth = max(0, len(self.lists) - 1)
            if self.lists and self.lists[-1][0] == 'ol':
                self.lists[-1][1] += 1
                self.prefix = '  ' * depth + '%d. ' % self.lists[-1][1]
            else:
                self.prefix = '  ' * depth + '- '
        elif tag in self.BLOCK or tag == 'pre':
            self._flush()
            if tag == 'pre':
                self.pre += 1
        elif tag == 'br':
            if self.cell is not None:
                self.cur.append(' ')
            else:
                self._flush()
        elif tag in ('strong', 'b'):
            self.cur.append('**')
        elif tag in ('em', 'i'):
            self.cur.append('*')
        elif tag == 'u':
            self.cur.append('<u>')
        elif tag == 'table':
            self._flush()
            self.table = []
        elif tag == 'tr' and self.table is not None:
            self.table.append([])
        elif tag in ('td', 'th') and self.table is not None:
            self._flush()
            self.cell = []
            if tag == 'th':
                self.cur.append('**')
                self._th = True
        elif tag == 'img':
            src = a.get('src') or ''
            if src.startswith('data:image'):
                try:
                    blk = image_block(base64.b64decode(src.split(',', 1)[1]))
                    key = 'h%d' % (len(self.images) + 1)
                    self.images[key] = blk
                    self._flush()
                    self.out.append('![resim:%s]' % key)
                except Exception:
                    pass
            elif a.get('alt'):
                self.cur.append('[%s]' % a['alt'])

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'head', 'title', 'noscript'):
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in ('strong', 'b'):
            self.cur.append('**')
        elif tag in ('em', 'i'):
            self.cur.append('*')
        elif tag == 'u':
            self.cur.append('</u>')
        elif tag in ('ul', 'ol'):
            self._flush()
            if self.lists:
                self.lists.pop()
        elif tag in ('td', 'th') and self.cell is not None:
            if tag == 'th' and getattr(self, '_th', False):
                self.cur.append('**')
                self._th = False
            self._flush()
            if self.table:
                self.table[-1].append(' '.join(self.cell).replace('|', '\\|'))
            self.cell = None
        elif tag == 'table' and self.table is not None:
            rows = [r for r in self.table if r]
            self.table = None
            if rows:
                ncol = max(len(r) for r in rows)
                rows = [r + [''] * (ncol - len(r)) for r in rows]
                self.out.append('| ' + ' | '.join(rows[0]) + ' |')
                self.out.append('|' + '|'.join('---' for _ in rows[0]) + '|')
                for r in rows[1:]:
                    self.out.append('| ' + ' | '.join(r) + ' |')
        elif tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'li', 'pre') or tag in self.BLOCK:
            self._flush()
            if tag == 'pre':
                self.pre = max(0, self.pre - 1)

    def handle_data(self, data):
        if self.skip:
            return
        self.cur.append(data.replace('*', '\\*') if not self.pre else data)


def html_to_markdown(fragment, images=None):
    """HTML -> bu modulun Markdown lehcesi (baslik #, kalin **, italik *, alti cizili <u>, tablo |).
    images sozlugune data: URI resimleri eklenir ve ![resim:kimlik] yazilir."""
    if images is None:
        images = {}
    if not fragment or '<' not in fragment:
        return html.unescape(fragment or '').strip()
    p = _HtmlToMd(images)
    p.feed(fragment)
    p.close()
    p._flush()
    out = []
    for line in p.out:
        is_list = bool(re.match(r'^\s*(-|\d+\.)\s', line))
        if out and not (is_list and re.match(r'^\s*(-|\d+\.)\s', out[-1])) and not (line.startswith('|') and out[-1].startswith('|')):
            out.append('')
        out.append(line)
    text = '\n'.join(out)
    text = re.sub(r'\*\*\s*\*\*', '', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def _runs_html(runs):
    out = []
    for r in merge_runs(runs):
        t = html.escape(r['text']).replace('\t', '&emsp;')
        css = []
        if r['color']:
            css.append('color:#%s' % r['color'])
        if r.get('hl'):
            css.append('background:#%s' % r['hl'])
        if r.get('font'):
            css.append("font-family:'%s'" % html.escape(r['font'], quote=True).replace("'", ''))
        if r.get('size'):
            css.append('font-size:%gpt' % r['size'])
        if css:
            t = '<span style="%s">%s</span>' % (';'.join(css), t)
        if r.get('s'):
            t = '<s>%s</s>' % t
        if r.get('va') in ('sup', 'sub'):
            t = '<%s>%s</%s>' % (r['va'], t, r['va'])
        if r['u']:
            t = '<u>%s</u>' % t
        if r['i']:
            t = '<em>%s</em>' % t
        if r['b']:
            t = '<strong>%s</strong>' % t
        if r.get('href'):
            t = '<a href="%s">%s</a>' % (html.escape(r['href'], quote=True), t)
        out.append(t)
    return ''.join(out)


def blocks_to_html(blocks):
    out = []
    open_list = []
    for b in blocks:
        want = (b.get('list'), b.get('level', 0)) if b['t'] == 'p' and b.get('list') else None
        while open_list and (not want or len(open_list) > want[1] + 1 or (len(open_list) == want[1] + 1 and open_list[-1] != want[0])):
            out.append('</%s>' % ('ol' if open_list.pop() == 'number' else 'ul'))
        if want:
            while len(open_list) < want[1] + 1:
                open_list.append(want[0])
                out.append('<%s>' % ('ol' if want[0] == 'number' else 'ul'))
            out.append('<li>%s</li>' % _runs_html(b['runs']))
            continue
        style = ' style="text-align:%s"' % b['align'] if b.get('align') else ''
        if b['t'] == 'p' and para_extra(b):                    # 2.0: aralik ve girintiler
            css = []
            if b.get('align'):
                css.append('text-align:%s' % b['align'])
            if b.get('ls'):
                css.append('line-height:%g' % (b['ls'] * 1.15))
            if b.get('sb') is not None:
                css.append('margin-top:%gpt' % b['sb'])
            if b.get('sa') is not None:
                css.append('margin-bottom:%gpt' % b['sa'])
            if b.get('ind'):
                css.append('margin-left:%gpt' % b['ind'])
            if b.get('fi'):
                css.append('text-indent:%gpt' % b['fi'])
            style = ' style="%s"' % ';'.join(css)
        if b['t'] == 'p':
            tag = {'h1': 'h1', 'h2': 'h2', 'h3': 'h3', 'quote': 'blockquote'}.get(b.get('style'), 'p')
            out.append('<%s%s>%s</%s>' % (tag, style, _runs_html(b['runs']) or '<br>', tag))
        elif b['t'] == 'img':
            out.append('<p%s><img src="data:%s;base64,%s" width="%d" height="%d" alt=""></p>'
                       % (style, IMG_EXT[b['ext']], base64.b64encode(b['data']).decode('ascii'),
                          round(b['w'] * 4 / 3), round(b['h'] * 4 / 3)))
        elif b['t'] == 'table':
            rows = ''.join('<tr>%s</tr>' % ''.join('<td>%s</td>' % _runs_html(c) for c in row) for row in b['rows'])
            out.append('<table>%s</table>' % rows)
    while open_list:
        out.append('</%s>' % ('ol' if open_list.pop() == 'number' else 'ul'))
    return '\n'.join(out)


def html_document(blocks, title):
    return ('<!doctype html>\n<html lang="tr"><head><meta charset="utf-8"><title>%s</title>'
            '<style>body{font-family:Calibri,"Segoe UI",Arial,sans-serif;max-width:800px;margin:40px auto;line-height:1.5;color:#1a1a1a}'
            'table{border-collapse:collapse}td{border:1px solid #999;padding:4px 8px;vertical-align:top}'
            'blockquote{border-left:3px solid #999;margin-left:0;padding-left:12px;color:#444}img{max-width:100%%;height:auto}</style>'
            '</head><body>\n%s\n</body></html>\n') % (html.escape(title), blocks_to_html(blocks))


def html_to_blocks(text):
    images = {}
    md = html_to_markdown(text, images)
    return markdown_to_blocks(md, images)


# ----------------------------------------------------------------------------- DOCX okuma
def _int_attr(el, name):
    if el is None:
        return None
    v = el.get(w(name))
    try:
        return int(float(v)) if v not in (None, '') else None
    except ValueError:
        return None


def _on(el):
    """<w:b/>, <w:b w:val="true"/> -> True; val=0/false/none -> False."""
    if el is None:
        return False
    v = (el.get(w('val')) or '').lower()
    return v not in ('0', 'false', 'off', 'none')


class _DocxReader:
    def __init__(self, z):
        self.z = z
        self.rels = self._rels('word/_rels/document.xml.rels')
        self.heading_styles, self.style_rpr, self.style_list = self._styles()
        self.num_fmt = self._numbering()

    def _xml(self, name):
        try:
            info = self.z.getinfo(name)
        except KeyError:
            return None
        if info.file_size > 80 * 1024 * 1024:
            raise ValueError('DOCX içeriği çok büyük.')
        return ET.fromstring(self.z.read(info))

    def _rels(self, name):
        root = self._xml(name)
        out = {}
        if root is not None:
            for r in root:
                out[r.get('Id')] = (r.get('Target') or '', r.get('TargetMode') or '')
        return out

    def _styles(self):
        heads, rprs, lists = {}, {}, set()
        root = self._xml('word/styles.xml')
        if root is None:
            return heads, rprs, lists
        for st in root.iter(w('style')):
            sid = st.get(w('styleId')) or ''
            name_el = st.find(w('name'))
            name = (name_el.get(w('val')) if name_el is not None else sid or '').lower().replace(' ', '')
            ppr = st.find(w('pPr'))
            outline = ppr.find(w('outlineLvl')) if ppr is not None else None
            m = re.match(r'(heading|başlık|baslik)([1-9])$', name)
            if name == 'title':
                heads[sid] = 'h1'
            elif m:
                heads[sid] = 'h%d' % min(3, int(m.group(2)))
            elif outline is not None and (outline.get(w('val')) or '').isdigit() and int(outline.get(w('val'))) < 9:
                heads[sid] = 'h%d' % min(3, int(outline.get(w('val'))) + 1)
            elif 'quote' in name or 'alıntı' in name:
                heads[sid] = 'quote'
            if ppr is not None and ppr.find(w('numPr')) is not None:
                lists.add(sid)
            rpr = st.find(w('rPr'))
            if rpr is not None and st.get(w('type')) == 'character':
                rprs[sid] = rpr
        return heads, rprs, lists

    def _numbering(self):
        root = self._xml('word/numbering.xml')
        fmts = {}
        if root is None:
            return fmts
        abstract = {}
        for an in root.iter(w('abstractNum')):
            lv = {}
            for lvl in an.iter(w('lvl')):
                f = lvl.find(w('numFmt'))
                lv[lvl.get(w('ilvl'))] = (f.get(w('val')) if f is not None else 'bullet')
            abstract[an.get(w('abstractNumId'))] = lv
        for n in root.iter(w('num')):
            a = n.find(w('abstractNumId'))
            if a is not None:
                fmts[n.get(w('numId'))] = abstract.get(a.get(w('val')), {})
        return fmts

    def image(self, rid, cx=None, cy=None):
        target = self.rels.get(rid, ('', ''))
        if not target[0] or target[1] == 'External':
            return None
        path = target[0].lstrip('/')
        path = path if path.startswith('word/') else 'word/' + path
        path = os.path.normpath(path).replace('\\', '/')
        try:
            data = self.z.read(path)
        except KeyError:
            return None
        kind = sniff_image(data)[0]
        if kind is None:
            return None             # EMF/WMF vb. desteklenmez
        try:
            return image_block(data, cx / EMU_PER_PT if cx else None, cy / EMU_PER_PT if cy else None)
        except ValueError:
            return None

    def para_props(self, p):
        style, lst, level, align, pb = 'normal', None, 0, None, False
        ppr = p.find(w('pPr'))
        if ppr is not None:
            ps = ppr.find(w('pStyle'))
            sid = ps.get(w('val')) if ps is not None else ''
            style = self.heading_styles.get(sid, 'normal')
            num = ppr.find(w('numPr'))
            if num is not None or sid in self.style_list:
                ilvl = num.find(w('ilvl')) if num is not None else None
                numid = num.find(w('numId')) if num is not None else None
                level = int(ilvl.get(w('val')) or 0) if ilvl is not None else 0
                nid = numid.get(w('val')) if numid is not None else None
                if nid != '0':
                    fmt = self.num_fmt.get(nid, {}).get(str(level), 'bullet')
                    lst = 'bullet' if fmt in ('bullet', 'none') else 'number'
            elif 'list' in sid.lower():
                lst = 'bullet'
            pb = _on(ppr.find(w('pageBreakBefore'))) if ppr.find(w('pageBreakBefore')) is not None else False
            jc = ppr.find(w('jc'))
            if jc is not None:
                v = jc.get(w('val'))
                align = {'center': 'center', 'right': 'right', 'end': 'right', 'both': 'justify', 'distribute': 'justify'}.get(v)
        extra = {}
        if ppr is not None:                                   # 2.0: aralik ve girintiler
            sp = ppr.find(w('spacing'))
            if sp is not None:
                for key, attr in (('sb', 'before'), ('sa', 'after')):
                    v = _int_attr(sp, attr)
                    if v is not None and sp.get(w(attr + 'Autospacing')) not in ('1', 'true', 'on'):
                        extra[key] = round(v / 20.0, 1)
                ln = _int_attr(sp, 'line')
                rule = sp.get(w('lineRule')) or 'auto'
                if ln and rule == 'auto':
                    mult = round(ln / 240.0, 2)
                    if abs(mult - 1.15) > 0.01 and mult > 0:
                        extra['ls'] = mult
            ind = ppr.find(w('ind'))
            if ind is not None and not lst:
                left = _int_attr(ind, 'left')
                if left is None:
                    left = _int_attr(ind, 'start')
                if left and style != 'quote':
                    extra['ind'] = round(left / 20.0, 1)
                fl, hg = _int_attr(ind, 'firstLine'), _int_attr(ind, 'hanging')
                if hg:
                    extra['fi'] = -round(hg / 20.0, 1)
                elif fl:
                    extra['fi'] = round(fl / 20.0, 1)
        out = {'style': style, 'list': lst, 'level': min(level, 3), 'align': align, 'pb': pb}
        out.update(extra)
        return out

    def run_fmt(self, r):
        rpr = r.find(w('rPr'))
        f = {'b': False, 'i': False, 'u': False, 'color': None}
        if rpr is None:
            return f
        rs = rpr.find(w('rStyle'))
        base = self.style_rpr.get(rs.get(w('val'))) if rs is not None else None
        for src in (base, rpr):
            if src is None:
                continue
            el = src.find(w('strike'))                         # 2.0
            if el is None:
                el = src.find(w('dstrike'))
            if el is not None:
                f['s'] = _on(el)
            fn = src.find(w('rFonts'))
            if fn is not None:
                fam = fn.get(w('ascii')) or fn.get(w('hAnsi'))
                if fam:
                    f['font'] = fam
            sz = src.find(w('sz'))
            v = _int_attr(sz, 'val') if sz is not None else None
            if v and 2 <= v <= 3276:
                f['size'] = v / 2.0 if v % 2 else v // 2
            va = src.find(w('vertAlign'))
            if va is not None:
                f['va'] = {'superscript': 'sup', 'subscript': 'sub'}.get(va.get(w('val')))
            hl = src.find(w('highlight'))
            if hl is not None and hl.get(w('val')) not in (None, 'none'):
                f['hl'] = HIGHLIGHTS.get(hl.get(w('val')), 'FFFF00')
            shd = src.find(w('shd'))
            if shd is not None and 'hl' not in f:
                fill = (shd.get(w('fill')) or '').upper()
                if re.match(r'^[0-9A-F]{6}$', fill) and fill != 'FFFFFF':
                    f['hl'] = fill
            for k, tag in (('b', 'b'), ('i', 'i')):
                el = src.find(w(tag))
                if el is not None:
                    f[k] = _on(el)
            u = src.find(w('u'))
            if u is not None:
                f['u'] = (u.get(w('val')) or 'single') != 'none'
            c = src.find(w('color'))
            if c is not None:
                v = (c.get(w('val')) or '').upper()
                f['color'] = v if re.match(r'^[0-9A-F]{6}$', v) and v != '000000' else None
        return f

    def paragraph(self, p, blocks):
        """Paragrafi bloklara ekler; satir/sayfa sonlari ve satir ici resimler paragrafi boler."""
        props = self.para_props(p)
        cur = para(style=props['style'], lst=props['list'], level=props['level'], align=props['align'], pb=props['pb'],
                   **{k: props.get(k) for k in PARA_EXTRA})
        link = [None]

        def push():
            cur['runs'] = merge_runs(cur['runs'])
            blocks.append(dict(cur))

        def new_para(pb=False):
            push()
            cur['runs'] = []
            cur['pb'] = pb
            if cur['list']:     # bolunen liste ogesinin devami duz paragraf olsun
                cur['list'] = None

        def walk(node):
            for ch in node:
                tag = ch.tag
                if tag == w('r'):
                    fmt = self.run_fmt(ch)
                    if link[0]:
                        fmt['href'] = link[0]
                    ext = {k: fmt.get(k) for k in RUN_EXTRA}
                    for el in ch:
                        if el.tag == w('t') and el.text:
                            cur['runs'].append(run(el.text, fmt['b'], fmt['i'], fmt['u'], fmt['color'], **ext))
                        elif el.tag == w('tab'):
                            cur['runs'].append(run('\t', fmt['b'], fmt['i'], fmt['u'], fmt['color'], **ext))
                        elif el.tag in (w('br'), w('cr')):
                            if el.get(w('type')) == 'page':
                                new_para(pb=True)
                            else:
                                new_para()
                        elif el.tag == w('noBreakHyphen'):
                            cur['runs'].append(run('-'))
                        elif el.tag == w('sym'):
                            cur['runs'].append(run('•'))
                        elif el.tag in (w('drawing'), '{%s}AlternateContent' % 'http://schemas.openxmlformats.org/markup-compatibility/2006'):
                            for blip in el.iter('{%s}blip' % A_NS):
                                rid = blip.get('{%s}embed' % R_NS)
                                ext = next(el.iter('{%s}extent' % WP_NS), None)
                                cx = int(ext.get('cx')) if ext is not None and (ext.get('cx') or '').isdigit() else None
                                cy = int(ext.get('cy')) if ext is not None and (ext.get('cy') or '').isdigit() else None
                                img = self.image(rid, cx, cy)
                                if img:
                                    self._emit_image(img, cur, blocks, props)
                                break
                        elif el.tag == w('pict'):
                            for idata in el.iter('{%s}imagedata' % V_NS):
                                img = self.image(idata.get('{%s}id' % R_NS))
                                if img:
                                    self._emit_image(img, cur, blocks, props)
                                break
                elif tag == w('hyperlink'):
                    rid = ch.get('{%s}id' % R_NS)
                    tgt = self.rels.get(rid, ('', '')) if rid else ('', '')
                    href = tgt[0] if tgt[1] == 'External' and re.match(r'^(https?://|mailto:)', tgt[0], re.I) else None
                    old = link[0]
                    link[0] = href or old
                    walk(ch)
                    link[0] = old
                elif tag in (w('ins'), w('smartTag'), w('fldSimple'), w('customXml'), w('sdtContent'), w('sdt')):
                    walk(ch)
                elif tag == w('del') or tag == w('pPr'):
                    continue
                elif tag == '{http://schemas.openxmlformats.org/markup-compatibility/2006}AlternateContent':
                    walk(ch)
        walk(p)
        cur['runs'] = merge_runs(cur['runs'])
        if cur['runs'] or not blocks or blocks[-1]['t'] != 'img' or cur.get('pb'):
            blocks.append(dict(cur))

    def _emit_image(self, img, cur, blocks, props):
        if runs_text(cur['runs']).strip():
            cur['runs'] = merge_runs(cur['runs'])
            blocks.append(dict(cur))
            cur['runs'] = []
            cur['list'] = None
        img['align'] = props['align']
        blocks.append(img)

    def table(self, tbl, blocks):
        rows = []
        for tr in tbl.findall(w('tr')):
            row = []
            for tc in tr.findall(w('tc')):
                cell_blocks = []
                for ch in tc:
                    if ch.tag == w('p'):
                        self.paragraph(ch, cell_blocks)
                    elif ch.tag == w('tbl'):
                        self.table(ch, cell_blocks)
                runs = []
                for b in cell_blocks:
                    if b['t'] == 'p' and b['runs']:
                        if runs:
                            runs.append(run(' '))
                        runs.extend(b['runs'])
                    elif b['t'] == 'table':
                        if runs:
                            runs.append(run(' '))
                        runs.append(run(block_text(b).replace('\n', ' / ').replace('\t', ' | ')))
                row.append(merge_runs(runs))
            if row:
                rows.append(row)
        if rows:
            ncol = max(len(r) for r in rows)
            blocks.append({'t': 'table', 'rows': [r + [[] for _ in range(ncol - len(r))] for r in rows]})

    def body(self, node, blocks):
        for ch in node:
            if ch.tag == w('p'):
                self.paragraph(ch, blocks)
            elif ch.tag == w('tbl'):
                self.table(ch, blocks)
            elif ch.tag in (w('sdt'), w('sdtContent'), w('customXml')):
                self.body(ch, blocks)


def read_docx_blocks(path):
    with zipfile.ZipFile(path) as z:
        rd = _DocxReader(z)
        root = rd._xml('word/document.xml')
        if root is None:
            raise ValueError('Geçerli bir Word belgesi değil (document.xml yok).')
        body = root.find(w('body'))
        blocks = []
        if body is not None:
            rd.body(body, blocks)
    # bas/son bos paragraflari ve ust uste ikiden fazla bos paragrafi sadelestir
    out = []
    for b in blocks:
        empty = b['t'] == 'p' and not runs_text(b['runs']).strip() and not b.get('pb')
        if empty and (not out or (out[-1]['t'] == 'p' and not runs_text(out[-1]['runs']).strip())):
            continue
        out.append(b)
    while out and out[-1]['t'] == 'p' and not runs_text(out[-1]['runs']).strip():
        out.pop()
    return out or [para()]


def _hf_text(rd, node):
    """Ust/alt bilgi metni; PAGE alanlari {sayfa} olarak isaretlenir."""
    if node is None:
        return '', False
    paras, has_page = [], False
    for p in node.iter(w('p')):
        parts, infld = [], False
        for el in p.iter():
            if el.tag == w('fldSimple') and 'PAGE' in (el.get(w('instr')) or '').upper().split():
                has_page = True
            elif el.tag == w('instrText') and (el.text or '').strip().upper().startswith(('PAGE', 'NUMPAGES')):
                has_page = True
            elif el.tag == w('fldChar'):
                infld = el.get(w('fldCharType')) in ('begin', 'separate')
            elif el.tag == w('t') and el.text and not infld:
                parts.append(el.text)
        paras.append(''.join(parts))
    return '\n'.join(x for x in paras if x.strip()).strip(), has_page


def read_docx_page(path):
    """DOCX'ten sayfa ayari (boyut, yon, kenar bosluklari, ust/alt bilgi, sayfa no)."""
    page = normalize_page(None)
    try:
        with zipfile.ZipFile(path) as z:
            rd = _DocxReader(z)
            root = rd._xml('word/document.xml')
            body = root.find(w('body')) if root is not None else None
            sect = body.find(w('sectPr')) if body is not None else None
            if sect is None:
                return page
            sz = sect.find(w('pgSz'))
            if sz is not None:
                pw, ph = _int_attr(sz, 'w'), _int_attr(sz, 'h')
                if pw and ph:
                    land = sz.get(w('orient')) == 'landscape' or pw > ph
                    a, b = sorted((pw / 20.0, ph / 20.0))
                    best = min(PAGE_SIZES, key=lambda k: abs(PAGE_SIZES[k][0] - a) + abs(PAGE_SIZES[k][1] - b))
                    if abs(PAGE_SIZES[best][0] - a) + abs(PAGE_SIZES[best][1] - b) < 20:
                        page['size'] = best
                    page['orient'] = 'landscape' if land else 'portrait'
            mar = sect.find(w('pgMar'))
            if mar is not None:
                for k, attr in (('t', 'top'), ('b', 'bottom'), ('l', 'left'), ('r', 'right')):
                    v = _int_attr(mar, attr)
                    if v is not None:
                        page['margins'][k] = round(abs(v) / 20.0, 1)
            for kind in ('header', 'footer'):
                ref = None
                for el in sect.findall(w(kind + 'Reference')):
                    if el.get(w('type')) in (None, 'default'):
                        ref = el
                if ref is None:
                    continue
                tgt = rd.rels.get(ref.get('{%s}id' % R_NS), ('', ''))[0]
                if not tgt:
                    continue
                name = tgt.lstrip('/')
                name = name if name.startswith('word/') else 'word/' + name
                txt, has_page = _hf_text(rd, rd._xml(name))
                if has_page and not page['pnum']:
                    align = 'center'
                    node = rd._xml(name)
                    jc = next(node.iter(w('jc')), None) if node is not None else None
                    if jc is not None:
                        align = {'right': 'right', 'end': 'right', 'left': 'left', 'start': 'left'}.get(jc.get(w('val')), 'center')
                    fmt = 'n_of_N' if node is not None and any(
                        'NUMPAGES' in ((e.get(w('instr')) or '') + (e.text or '')).upper()
                        for e in node.iter() if e.tag in (w('fldSimple'), w('instrText'))) else 'n'
                    page['pnum'] = {'pos': kind, 'align': align, 'fmt': fmt}
                    # numaranin cevresindeki "Sayfa ... / ..." kalintilarini at
                    txt = re.sub(r'(?i)^\s*(sayfa|page)?\s*[/]?\s*(/|of|\s)*\s*$', '', txt).strip()
                page[kind] = txt
    except (zipfile.BadZipFile, KeyError, ET.ParseError, ValueError, OSError):
        pass
    return page


# ----------------------------------------------------------------------------- DOCX yazma
def _xml_text(s):
    return html.escape(s, quote=False)


def _run_xml(r):
    # sema sirasi: rStyle rFonts b bCs i iCs strike color sz szCs highlight u vertAlign
    rpr = ''
    if r.get('href'):
        rpr += '<w:rStyle w:val="Hyperlink"/>'
    if r.get('font'):
        f = html.escape(r['font'], quote=True)
        rpr += '<w:rFonts w:ascii="%s" w:hAnsi="%s" w:cs="%s" w:eastAsia="%s"/>' % (f, f, f, f)
    if r.get('b'):
        rpr += '<w:b/><w:bCs/>'
    if r.get('i'):
        rpr += '<w:i/><w:iCs/>'
    if r.get('s'):
        rpr += '<w:strike/>'
    if r.get('color'):
        rpr += '<w:color w:val="%s"/>' % r['color']
    if r.get('size'):
        hp = max(2, min(3276, int(round(float(r['size']) * 2))))
        rpr += '<w:sz w:val="%d"/><w:szCs w:val="%d"/>' % (hp, hp)
    hl = r.get('hl')
    if hl:
        name = HIGHLIGHT_BY_HEX.get(hl.upper())
        rpr += '<w:highlight w:val="%s"/>' % name if name else '<w:shd w:val="clear" w:color="auto" w:fill="%s"/>' % hl.upper()
    if r.get('u'):
        rpr += '<w:u w:val="single"/>'
    if r.get('va') in ('sup', 'sub'):
        rpr += '<w:vertAlign w:val="%s"/>' % ('superscript' if r['va'] == 'sup' else 'subscript')
    rpr = '<w:rPr>%s</w:rPr>' % rpr if rpr else ''
    parts = []
    for k, piece in enumerate(r['text'].split('\t')):
        if k:
            parts.append('<w:tab/>')
        if piece:
            parts.append('<w:t xml:space="preserve">%s</w:t>' % _xml_text(piece))
    return '<w:r>%s%s</w:r>' % (rpr, ''.join(parts))


class _DocxWriter:
    def __init__(self):
        self.media = {}         # zip yolu -> bytes
        self.rels = []          # (rId, tip, hedef)
        self.nums = []          # (numId, abstract)
        self.pic_id = 0
        self.content_w = CONTENT_W_PT

    def rel(self, typ, target):
        rid = 'rId%d' % (len(self.rels) + 10)
        self.rels.append((rid, typ, target))
        return rid

    def new_num(self, kind):
        nid = len(self.nums) + 1
        self.nums.append((nid, 0 if kind == 'bullet' else 1))
        return nid

    def para_xml(self, b, num_id=None):
        ppr = ''
        st = {'h1': 'Heading1', 'h2': 'Heading2', 'h3': 'Heading3', 'quote': 'Quote'}.get(b.get('style'))
        if b.get('list'):
            st = 'ListParagraph'
        if st:
            ppr += '<w:pStyle w:val="%s"/>' % st
        if b.get('pb'):
            ppr += '<w:pageBreakBefore/>'
        if b.get('list') and num_id:
            ppr += '<w:numPr><w:ilvl w:val="%d"/><w:numId w:val="%d"/></w:numPr>' % (b.get('level', 0), num_id)
        # sema sirasi: ... numPr spacing ind jc
        sp = ''
        if b.get('sb') is not None and b.get('sb') != '':
            sp += ' w:before="%d"' % int(round(float(b['sb']) * 20))
        if b.get('sa') is not None and b.get('sa') != '':
            sp += ' w:after="%d"' % int(round(float(b['sa']) * 20))
        if b.get('ls'):
            sp += ' w:line="%d" w:lineRule="auto"' % int(round(float(b['ls']) * 240))
        if sp:
            ppr += '<w:spacing%s/>' % sp
        if (b.get('ind') or b.get('fi')) and not b.get('list'):
            ind = ' w:left="%d"' % int(round(float(b.get('ind') or 0) * 20))
            fi = float(b.get('fi') or 0)
            if fi > 0:
                ind += ' w:firstLine="%d"' % int(round(fi * 20))
            elif fi < 0:
                ind += ' w:hanging="%d"' % int(round(-fi * 20))
            ppr += '<w:ind%s/>' % ind
        if b.get('align'):
            ppr += '<w:jc w:val="%s"/>' % {'justify': 'both'}.get(b['align'], b['align'])
        ppr = '<w:pPr>%s</w:pPr>' % ppr if ppr else ''
        return '<w:p>%s%s</w:p>' % (ppr, self.runs_xml(b['runs']))

    def runs_xml(self, runs):
        out, k = [], 0
        runs = merge_runs(runs)
        while k < len(runs):
            href = runs[k].get('href')
            if not href:
                out.append(_run_xml(runs[k]))
                k += 1
                continue
            grp = []
            while k < len(runs) and runs[k].get('href') == href:
                grp.append(runs[k])
                k += 1
            rid = self.link_rel(href)
            out.append('<w:hyperlink r:id="%s" w:history="1">%s</w:hyperlink>' % (rid, ''.join(_run_xml(r) for r in grp)))
        return ''.join(out)

    def link_rel(self, href):
        for rid, typ, tgt, *_ in self.rels:
            if typ.endswith('/hyperlink') and tgt == href:
                return rid
        rid = 'rId%d' % (len(self.rels) + 10)
        self.rels.append((rid, 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink', href, 'External'))
        return rid

    def image_xml(self, b):
        self.pic_id += 1
        n = self.pic_id
        name = 'media/image%d.%s' % (n, b['ext'])
        self.media['word/' + name] = b['data']
        rid = self.rel('http://schemas.openxmlformats.org/officeDocument/2006/relationships/image', name)
        cx, cy = int(b['w'] * EMU_PER_PT), int(b['h'] * EMU_PER_PT)
        jc = '<w:pPr><w:jc w:val="%s"/></w:pPr>' % {'justify': 'both'}.get(b['align'], b['align']) if b.get('align') else ''
        return ('<w:p>%s<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
                '<wp:extent cx="%d" cy="%d"/><wp:docPr id="%d" name="Resim %d"/>'
                '<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
                '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
                '<pic:pic><pic:nvPicPr><pic:cNvPr id="%d" name="image%d.%s"/><pic:cNvPicPr/></pic:nvPicPr>'
                '<pic:blipFill><a:blip r:embed="%s"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
                '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
                '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'
                % (jc, cx, cy, n, n, n, n, b['ext'], rid, cx, cy))

    def table_xml(self, b):
        ncol = max((len(r) for r in b['rows']), default=1)
        colw = int(self.content_w * 20 / ncol)
        grid = ''.join('<w:gridCol w:w="%d"/>' % colw for _ in range(ncol))
        rows = []
        for row in b['rows']:
            cells = ''.join('<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/></w:tcPr>%s</w:tc>'
                            % (colw, self.para_xml(para(c))) for c in row + [[] for _ in range(ncol - len(row))])
            rows.append('<w:tr>%s</w:tr>' % cells)
        borders = ''.join('<w:%s w:val="single" w:sz="4" w:space="0" w:color="808080"/>' % s
                          for s in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'))
        return ('<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="0" w:type="auto"/><w:tblBorders>%s</w:tblBorders>'
                '<w:tblLook w:val="04A0"/></w:tblPr><w:tblGrid>%s</w:tblGrid>%s</w:tbl>' % (borders, grid, ''.join(rows)))

    def body_xml(self, blocks):
        out = []
        num_id, prev_kind = None, None
        for k, b in enumerate(blocks):
            if b['t'] == 'p' and b.get('list'):
                if b['list'] != prev_kind:
                    num_id = self.new_num(b['list'])
                    prev_kind = b['list']
                out.append(self.para_xml(b, num_id))
                continue
            prev_kind = None
            if b['t'] == 'p':
                out.append(self.para_xml(b))
            elif b['t'] == 'img':
                out.append(self.image_xml(b))
            elif b['t'] == 'table':
                out.append(self.table_xml(b))
                nxt = blocks[k + 1] if k + 1 < len(blocks) else None
                if nxt is None or nxt['t'] == 'table':
                    out.append('<w:p/>')
        return ''.join(out) or '<w:p/>'


def _numbering_xml(nums):
    def lvls(bullet):
        out = []
        for i in range(9):
            if bullet:
                ch = '•◦▪'[i % 3]
                out.append('<w:lvl w:ilvl="%d"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="%s"/>'
                           '<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="%d" w:hanging="360"/></w:pPr>'
                           '<w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/></w:rPr></w:lvl>' % (i, ch, 720 * (i + 1)))
            else:
                fmt = ['decimal', 'lowerLetter', 'lowerRoman'][i % 3]
                out.append('<w:lvl w:ilvl="%d"><w:start w:val="1"/><w:numFmt w:val="%s"/><w:lvlText w:val="%%%d."/>'
                           '<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="%d" w:hanging="360"/></w:pPr></w:lvl>'
                           % (i, fmt, i + 1, 720 * (i + 1)))
        return ''.join(out)
    body = ('<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="hybridMultilevel"/>%s</w:abstractNum>'
            '<w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="hybridMultilevel"/>%s</w:abstractNum>') % (lvls(True), lvls(False))
    body += ''.join('<w:num w:numId="%d"><w:abstractNumId w:val="%d"/>%s</w:num>'
                    % (nid, ab, '<w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride>' if ab == 1 else '')
                    for nid, ab in nums)
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:numbering xmlns:w="%s">%s</w:numbering>' % (W_NS, body)


STYLES_XML = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="%s">'
              '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri" w:eastAsia="Calibri"/>'
              '<w:sz w:val="22"/><w:szCs w:val="22"/><w:lang w:val="tr-TR"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>'
              '<w:spacing w:after="160" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
              '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
              '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
              '<w:pPr><w:keepNext/><w:spacing w:before="360" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr>'
              '<w:rPr><w:b/><w:color w:val="1F3864"/><w:sz w:val="34"/></w:rPr></w:style>'
              '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
              '<w:pPr><w:keepNext/><w:spacing w:before="240" w:after="100"/><w:outlineLvl w:val="1"/></w:pPr>'
              '<w:rPr><w:b/><w:color w:val="2F5496"/><w:sz w:val="28"/></w:rPr></w:style>'
              '<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
              '<w:pPr><w:keepNext/><w:spacing w:before="200" w:after="80"/><w:outlineLvl w:val="2"/></w:pPr>'
              '<w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>'
              '<w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/><w:basedOn w:val="Normal"/><w:qFormat/>'
              '<w:pPr><w:ind w:left="720" w:right="720"/></w:pPr><w:rPr><w:i/><w:color w:val="404040"/></w:rPr></w:style>'
              '<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/>'
              '<w:pPr><w:spacing w:after="60"/><w:ind w:left="720"/><w:contextualSpacing/></w:pPr></w:style>'
              '<w:style w:type="character" w:styleId="Hyperlink"><w:name w:val="Hyperlink"/><w:uiPriority w:val="99"/>'
              '<w:unhideWhenUsed/><w:rPr><w:color w:val="0563C1"/><w:u w:val="single"/></w:rPr></w:style>'
              '<w:style w:type="paragraph" w:styleId="Header"><w:name w:val="header"/><w:basedOn w:val="Normal"/>'
              '<w:pPr><w:tabs><w:tab w:val="center" w:pos="4536"/><w:tab w:val="right" w:pos="9072"/></w:tabs><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr></w:style>'
              '<w:style w:type="paragraph" w:styleId="Footer"><w:name w:val="footer"/><w:basedOn w:val="Normal"/>'
              '<w:pPr><w:tabs><w:tab w:val="center" w:pos="4536"/><w:tab w:val="right" w:pos="9072"/></w:tabs><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr></w:style>'
              '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:tblPr><w:tblCellMar>'
              '<w:left w:w="108" w:type="dxa"/><w:right w:w="108" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>'
              '</w:styles>') % W_NS


def _hf_xml(kind, text, pnum):
    """header1.xml / footer1.xml - metin satirlari + istege bagli PAGE alani."""
    tag = 'hdr' if kind == 'header' else 'ftr'
    style = 'Header' if kind == 'header' else 'Footer'
    paras = []
    lines = [x for x in (text or '').split('\n')] if (text or '').strip() else []
    with_num = pnum and pnum.get('pos') == kind

    def field(instr):
        return ('<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> %s </w:instrText></w:r>'
                '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>' % instr)
    for ln in lines:
        paras.append('<w:p><w:pPr><w:pStyle w:val="%s"/><w:jc w:val="center"/></w:pPr>%s</w:p>'
                     % (style, _run_xml(run(ln)) if ln else ''))
    if with_num:
        num = field('PAGE')
        if pnum.get('fmt') == 'n_of_N':
            num += _run_xml(run(' / ')) + field('NUMPAGES')
        paras.append('<w:p><w:pPr><w:pStyle w:val="%s"/><w:jc w:val="%s"/></w:pPr>%s</w:p>' % (style, pnum.get('align', 'center'), num))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:%s xmlns:w="%s" xmlns:r="%s">%s</w:%s>'
            % (tag, W_NS, R_NS, ''.join(paras) or '<w:p/>', tag))


def docx_bytes(blocks, page=None):
    page = normalize_page(page)
    wr = _DocxWriter()
    wr.content_w = content_width(page)
    body = wr.body_xml(blocks)
    pw, ph = page_dims(page)
    m = page['margins']
    parts, refs = {}, ''
    for kind in ('header', 'footer'):
        if page[kind].strip() or (page['pnum'] and page['pnum']['pos'] == kind):
            name = '%s1.xml' % kind
            parts['word/' + name] = _hf_xml(kind, page[kind], page['pnum'])
            rid = wr.rel('http://schemas.openxmlformats.org/officeDocument/2006/relationships/' + kind, name)
            refs += '<w:%sReference w:type="default" r:id="%s"/>' % (kind, rid)
    sect = ('<w:sectPr>%s<w:pgSz w:w="%d" w:h="%d"%s/>'
            '<w:pgMar w:top="%d" w:right="%d" w:bottom="%d" w:left="%d" w:header="708" w:footer="708" w:gutter="0"/>'
            '</w:sectPr>') % (refs, round(pw * 20), round(ph * 20), ' w:orient="landscape"' if page['orient'] == 'landscape' else '',
                              round(m['t'] * 20), round(m['r'] * 20), round(m['b'] * 20), round(m['l'] * 20))
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="%s" xmlns:r="%s" xmlns:wp="%s" xmlns:a="%s" xmlns:pic="%s"><w:body>%s%s'
           '</w:body></w:document>') % (W_NS, R_NS, WP_NS, A_NS, PIC_NS, body, sect)
    exts = sorted({b.rsplit('.', 1)[1] for b in wr.media})
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          + ''.join('<Default Extension="%s" ContentType="%s"/>' % (e, IMG_EXT[e]) for e in exts) +
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
          '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
          '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
          + ''.join('<Override PartName="/%s" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.%s+xml"/>'
                    % (n, 'header' if 'header' in n else 'footer') for n in sorted(parts)) +
          '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="%s">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '</Relationships>') % REL_NS
    doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="%s">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
                '%s</Relationships>') % (REL_NS, ''.join(
                    '<Relationship Id="%s" Type="%s" Target="%s"%s/>' % (r[0], r[1], html.escape(r[2], quote=True),
                                                                        ' TargetMode="External"' if len(r) > 3 else '')
                    for r in wr.rels))
    now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    core_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:creator>AGFO AI Editor</dc:creator>'
                '<dcterms:created xsi:type="dcterms:W3CDTF">%s</dcterms:created>'
                '<dcterms:modified xsi:type="dcterms:W3CDTF">%s</dcterms:modified></cp:coreProperties>') % (now, now)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', ct)
        z.writestr('_rels/.rels', rels)
        z.writestr('word/document.xml', doc)
        z.writestr('word/_rels/document.xml.rels', doc_rels)
        z.writestr('word/styles.xml', STYLES_XML)
        z.writestr('word/numbering.xml', _numbering_xml(wr.nums))
        z.writestr('docProps/core.xml', core_xml)
        for name, data in parts.items():
            z.writestr(name, data)
        for name, data in wr.media.items():
            z.writestr(name, data, compress_type=zipfile.ZIP_STORED)
    return buf.getvalue()


def bilingual_docx_bytes(pairs, left_title, right_title):
    """Yan yana ceviri: iki sutunlu tablo (ozgun | ceviri), her satir bir paragraf."""
    rows = [[[run(left_title, b=True)], [run(right_title, b=True)]]]
    for a, b in pairs:
        rows.append([a, b])
    return docx_bytes([{'t': 'table', 'rows': rows}])


# ----------------------------------------------------------------------------- JSON (kurtarma)
def blocks_to_json(blocks):
    out = []
    for b in blocks:
        b = dict(b)
        if b['t'] == 'img':
            b['data'] = base64.b64encode(b['data']).decode('ascii')
        out.append(b)
    return out


def blocks_from_json(items):
    out = []
    for b in items or []:
        b = dict(b)
        if b.get('t') == 'img':
            b['data'] = base64.b64decode(b['data'])
        out.append(b)
    return out


def has_formatting(blocks):
    for b in blocks:
        if b['t'] in ('img', 'table'):
            return True
        if b.get('style', 'normal') != 'normal' or b.get('list') or b.get('align'):
            return True
        if para_extra(b):
            return True
        if any(r['b'] or r['i'] or r['u'] or r['color'] or run_extra(r) for r in b['runs']):
            return True
    return False
