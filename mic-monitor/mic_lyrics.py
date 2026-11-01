"""AGFO Mic Monitor - sarki sozu ekrani icin metin ve zamanlama (yalnizca standart kutuphane).

Kaynaklar: duz metin (.txt), zaman damgali soz (.lrc: [dd:ss.xx] satir), Word (.docx; paragraflar).
Zamanlama: LRC'deki damgalar; yoksa satirlar sarki suresine esit dagitilir (bos satirlar kita arasi
sayilir ve kisa tutulur). "Zamanla" modunda prova sirasinda her satirin basinda bir tusa basilir;
Tapper zamanlari toplar ve LRC olarak yazilir.
"""
import pathlib
import re
import xml.etree.ElementTree as ET
import zipfile

LYRIC_TYPES = (('Metin / sarki sozu', '*.txt *.md *.lrc *.docx'), ('Tum dosyalar', '*.*'))
_MD_INLINE = (re.compile(r'!\[[^\]]*\]\([^)]*\)'), re.compile(r'\[([^\]]+)\]\([^)]*\)'),
              re.compile(r'(\*\*|__)(.+?)\1'), re.compile(r'(\*|_)(.+?)\1'), re.compile(r'`([^`]*)`'))
_STAMP = re.compile(r'\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]')
_TAG = re.compile(r'^\[([a-zA-Z#]+):(.*)\]\s*$')


class Lyrics:
    """lines: metin satirlari (bos satir = kita arasi). times: her satirin baslangici (sn) ya da None."""

    def __init__(self, lines, times=None, source=None, timed=False):
        self.lines = list(lines)
        self.times = list(times) if times else None
        self.source = pathlib.Path(source) if source else None
        self.timed = bool(timed and self.times)

    def __len__(self):
        return len(self.lines)

    @property
    def name(self):
        return self.source.name if self.source else '(yapistirilan metin)'

    def ensure_times(self, duration, start=0.0):
        """Zaman yoksa satirlari [start, duration] araligina dagit. Bos satir yarim agirlik alir."""
        if self.timed or not self.lines:
            return self
        self.times = distribute(self.lines, duration, start)
        return self

    def index_at(self, t):
        return current_index(self.times or [], t)

    def progress_at(self, t, end=None):
        """Kesirli konum (yumusak kaydirma icin): satir i ile i+1 arasinda 0..1."""
        times = self.times or []
        i = current_index(times, t)
        if i < 0:
            return -1.0
        nxt = times[i + 1] if i + 1 < len(times) else (end if end and end > times[i] else times[i] + 4.0)
        span = max(1e-3, nxt - times[i])
        return i + min(1.0, max(0.0, (t - times[i]) / span))


# --------------------------------------------------------------------------- okuma
def parse_text(text):
    text = text.replace('\r\n', '\n').replace('\r', '\n').lstrip('﻿')
    lines = [ln.rstrip() for ln in text.split('\n')]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    out = []
    for ln in lines:                              # ardisik bos satirlari tek kita arasina indir
        if not ln.strip() and out and not out[-1].strip():
            continue
        out.append(ln.strip())
    return out


def parse_lrc(text):
    """LRC -> (satirlar, zamanlar). [offset:+/-ms] desteklenir; bir satirda birden cok damga olabilir."""
    offset = 0.0
    entries = []
    for raw in text.replace('\r\n', '\n').replace('\r', '\n').lstrip('﻿').split('\n'):
        raw = raw.strip()
        if not raw:
            continue
        m = _TAG.match(raw)
        if m and not _STAMP.match(raw):
            if m.group(1).lower() == 'offset':
                try:
                    offset = float(m.group(2).strip()) / 1000.0
                except ValueError:
                    pass
            continue
        stamps = list(_STAMP.finditer(raw))
        if not stamps:
            continue
        body = _STAMP.sub('', raw).strip()
        for s in stamps:
            mm, ss, fr = int(s.group(1)), int(s.group(2)), s.group(3)
            frac = int(fr) / (10 ** len(fr)) if fr else 0.0
            entries.append((mm * 60 + ss + frac, body))
    entries.sort(key=lambda e: e[0])
    # LRC'de "+offset" sozleri erkene alir
    return [b for _, b in entries], [max(0.0, t - offset) for t, _ in entries]


def read_docx(path):
    """Word belgesinin paragraflarini sirayla dondurur (bicim yok sayilir)."""
    ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    with zipfile.ZipFile(str(path)) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    paras = []
    for p in root.iter(ns + 'p'):
        parts = []
        for node in p.iter():
            if node.tag == ns + 't' and node.text:
                parts.append(node.text)
            elif node.tag in (ns + 'br', ns + 'cr'):
                parts.append('\n')
            elif node.tag == ns + 'tab':
                parts.append(' ')
        paras.append(''.join(parts))
    return '\n'.join(paras)


def parse_markdown(text):
    """Markdown -> duz satirlar: basliklar, madde imleri, vurgu, baglanti ve kod isaretleri atilir."""
    out = []
    in_code = False
    for ln in text.replace('\r\n', '\n').replace('\r', '\n').lstrip('\ufeff').split('\n'):
        if ln.strip().startswith('```'):
            in_code = not in_code
            continue
        if in_code:
            continue
        ln = re.sub(r'^\s{0,3}(#{1,6}\s+|>\s?|[-*+]\s+|\d+[.)]\s+)', '', ln)
        if re.fullmatch(r'\s*([-*_]\s*){3,}', ln):
            ln = ''
        ln = _MD_INLINE[0].sub('', ln)
        ln = _MD_INLINE[1].sub(r'\1', ln)
        ln = _MD_INLINE[2].sub(r'\2', ln)
        ln = _MD_INLINE[3].sub(r'\2', ln)
        ln = _MD_INLINE[4].sub(r'\1', ln)
        out.append(ln)
    return parse_text('\n'.join(out))


def _read_text_file(path):
    raw = pathlib.Path(path).read_bytes()
    for enc in ('utf-8-sig', 'utf-16', 'cp1254', 'latin-1'):
        try:
            txt = raw.decode(enc)
            if enc == 'utf-16' and not raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
                continue
            return txt
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', 'replace')


def load(path):
    path = pathlib.Path(path)
    ext = path.suffix.lower()
    if ext == '.docx':
        return Lyrics(parse_text(read_docx(path)), source=path)
    text = _read_text_file(path)
    if ext in ('.md', '.markdown'):
        return Lyrics(parse_markdown(text), source=path)
    if ext == '.lrc' or _STAMP.search(text[:2000] or ''):
        lines, times = parse_lrc(text)
        if lines:
            return Lyrics(lines, times, source=path, timed=True)
    return Lyrics(parse_text(text), source=path)


def from_text(text):
    if _STAMP.search(text[:2000] or ''):
        lines, times = parse_lrc(text)
        if lines:
            return Lyrics(lines, times, timed=True)
    return Lyrics(parse_text(text))


# --------------------------------------------------------------------------- zamanlama
def distribute(lines, duration, start=0.0):
    """Satirlari sureye agirlikli dagit: dolu satir 1, bos satir (kita arasi) 0,5 birim."""
    if not lines:
        return []
    w = [1.0 if ln.strip() else 0.5 for ln in lines]
    total = sum(w)
    span = max(1.0, float(duration) - float(start))
    t, out = float(start), []
    for x in w:
        out.append(round(t, 3))
        t += span * x / total
    return out


def current_index(times, t):
    """t aninda soylenen satir (ikili arama). Ilk satirdan once -1."""
    lo, hi = 0, len(times)
    while lo < hi:
        mid = (lo + hi) // 2
        if times[mid] <= t:
            lo = mid + 1
        else:
            hi = mid
    return lo - 1


def fmt_stamp(t):
    t = max(0.0, float(t))
    m = int(t // 60)
    s = t - m * 60
    return '[%02d:%05.2f]' % (m, s)


def to_lrc(lines, times, title=None):
    head = ['[ti:%s]' % title] if title else []
    head.append('[re:AGFO Mic Monitor]')
    return '\n'.join(head + ['%s%s' % (fmt_stamp(t), ln) for ln, t in zip(lines, times)]) + '\n'


class Tapper:
    """Prova sirasinda her satir basinda tap(t) cagrilir. Bos satirlar (kita arasi) atlanir:
    zamanlari bir sonraki dolu satirdan hemen once olarak doldurulur."""

    def __init__(self, lines):
        self.lines = list(lines)
        self.targets = [i for i, ln in enumerate(self.lines) if ln.strip()]
        self.taps = []

    @property
    def next_index(self):
        return self.targets[len(self.taps)] if len(self.taps) < len(self.targets) else None

    @property
    def done(self):
        return len(self.taps) >= len(self.targets)

    def tap(self, t):
        if self.done:
            return None
        if self.taps and t < self.taps[-1]:
            t = self.taps[-1]
        self.taps.append(float(t))
        return self.targets[len(self.taps) - 1]

    def undo(self):
        if self.taps:
            self.taps.pop()

    def times(self):
        """Son vurulan satira kadar tum satirlarin zamani. Kita aralari (bos satir) iki komsunun ortasi."""
        n = len(self.taps)
        if not n:
            return []
        tap_at = {self.targets[k]: self.taps[k] for k in range(n)}
        last_line = self.targets[n - 1]
        out = []
        for i in range(last_line + 1):
            if i in tap_at:
                out.append(tap_at[i])
                continue
            prev = next((tap_at[j] for j in range(i - 1, -1, -1) if j in tap_at), 0.0)
            nxt = next((tap_at[j] for j in range(i + 1, last_line + 1) if j in tap_at), prev)
            out.append(round((prev + nxt) / 2.0, 3))
        return out


def save_lrc(lyrics_lines, times, path, title=None):
    path = pathlib.Path(path)
    path.write_text(to_lrc(lyrics_lines[:len(times)], times, title), encoding='utf-8')
    return path


def lrc_path_for(lyrics, backing_path=None):
    """Zamanlamanin yazilacagi yer: soz dosyasinin yaninda ayni ad .lrc; yapistirilan metinde altyapinin yani."""
    if lyrics.source is not None:
        return lyrics.source.with_suffix('.lrc')
    if backing_path:
        return pathlib.Path(backing_path).with_suffix('.lrc')
    return None


def find_for_backing(backing_path):
    """Altyapi ile ayni adli soz dosyasi (once .lrc, sonra .txt / .docx)."""
    p = pathlib.Path(backing_path)
    for ext in ('.lrc', '.txt', '.docx'):
        c = p.with_suffix(ext)
        if c.is_file():
            return c
    return None


# --------------------------------------------------------------------------- prompter (konusma)
def paragraphs(lines):
    """Prompter kipi: her dolu satir bir paragraf; bos satirlar yalniz ayiricidir."""
    return [ln for ln in lines if ln.strip()]


def split_sentences(text):
    """Ekrana sigmayan uzun paragraf icin cumlelere bol (nokta / soru / unlem / uc nokta sonrasi)."""
    parts = re.split(r'(?<=[.!?…])\s+', text.strip())
    return [p for p in parts if p]


def build_sections(paras, fits):
    """Paragraflari ekrana sigan bolumlere grupla. fits(list_of_paragraphs) -> bool (olcum arayuzde).
    Tek basina sigmayan paragraf cumlelere bolunur; tek cumle de sigmazsa oldugu gibi kendi bolumu olur."""
    units = []
    for p in paras:
        if fits([p]):
            units.append(p)
        else:
            units.extend(split_sentences(p) or [p])
    sections, cur = [], []
    for u in units:
        if cur and not fits(cur + [u]):
            sections.append(cur)
            cur = [u]
        else:
            cur.append(u)
    if cur:
        sections.append(cur)
    return sections


def audacity_labels(marks):
    """[(saniye, etiket)] -> Audacity etiket dosyasi metni (Dosya > Ice aktar > Etiketler)."""
    return ''.join('%.6f\t%.6f\t%s\n' % (t, t, lab.replace('\t', ' ').replace('\n', ' ')) for t, lab in marks)
