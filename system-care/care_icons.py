"""AGFO System Care - Uygulama kur sayfasi icin uygulama logolari (GUI'den bagimsiz, test edilebilir).

Logolar pakette dagitilmaz: kullanicinin bilgisayarinda, her uygulamanin kendi sitesinden (tarayicinin sekme
simgesini bulmasi gibi) bir kez indirilir ve %LOCALAPPDATA%\\AGFO\\SystemCare\\app-icons altinda saklanir.
Siralama: apple-touch-icon > boyutu belirtilmis PNG simge > diger simge baglantilari > /favicon.ico.
Pillow (modern gorunumle birlikte gelir) varsa ICO/JPG/WEBP de okunur ve 64 / 20 piksellik kare PNG'ye
cevrilir; yoksa yalnizca PNG kullanilir. Logo bulunamayan uygulamalar icin renkli harf simgesi cizilir.
"""
import hashlib
import html.parser
import io
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request

LARGE, SMALL = 48, 20
MAX_HTML = 600 * 1024
MAX_IMAGE = 700 * 1024
TIMEOUT = 8
RETRY_DAYS = 30
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AGFO-System-Care'
PNG_SIG = b'\x89PNG\r\n\x1a\n'
AVATAR_COLORS = ['#2f7fc1', '#2e9d6a', '#c0392b', '#8e44ad', '#d35400', '#16a085', '#2c3e50', '#b8730c', '#7f8c8d', '#1f5f99',
                 '#a93226', '#117a65']


def cache_dir(app_data_dir):
    return pathlib.Path(app_data_dir) / 'app-icons'


def slug(app_id):
    return re.sub(r'[^A-Za-z0-9._-]+', '_', app_id)[:80] + '-' + hashlib.sha1(app_id.encode('utf-8')).hexdigest()[:6]


def paths(cdir, app_id):
    s = slug(app_id)
    return pathlib.Path(cdir) / (s + '-64.png'), pathlib.Path(cdir) / (s + '-20.png')


def site_url(app):
    site = app.get('site')
    return ('https://' + site.strip('/') + '/') if site else None


# --------------------------------------------------------------------------- harf simgesi
def initials(name):
    words = [w for w in re.split(r'[\s\-_.+]+', name) if w and w[0].isalnum()]
    if not words:
        return '?'
    if len(words) == 1:
        return words[0][:2].upper() if len(words[0]) > 1 and words[0][1].isalnum() else words[0][0].upper()
    return (words[0][0] + words[1][0]).upper()


def avatar_color(app_id):
    return AVATAR_COLORS[int(hashlib.md5(app_id.encode('utf-8')).hexdigest(), 16) % len(AVATAR_COLORS)]


# --------------------------------------------------------------------------- sayfadan simge baglantilari
class _LinkParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.base = None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or '') for k, v in attrs}
        if tag == 'base' and a.get('href') and self.base is None:
            self.base = a['href']
        if tag == 'link' and a.get('href'):
            rel = a.get('rel', '').lower().split()
            if 'icon' in rel or 'apple-touch-icon' in rel or 'apple-touch-icon-precomposed' in rel:
                self.links.append((rel, a.get('sizes', ''), a.get('type', '').lower(), a['href']))
        if tag == 'meta' and a.get('property', '').lower() == 'og:image' and a.get('content'):
            pass                                              # sosyal paylasim gorselleri logo degildir; kullanilmaz


def _size(sizes):
    best = 0
    for m in re.finditer(r'(\d+)\s*x\s*(\d+)', sizes or '', re.I):
        best = max(best, min(int(m.group(1)), int(m.group(2))))
    return 512 if (sizes or '').lower() == 'any' else best


def icon_candidates(page_html, base_url):
    """Sayfadaki simge baglantilari, tercih sirasina gore (mutlak https adresleri)."""
    p = _LinkParser()
    try:
        p.feed(page_html or '')
    except Exception:
        pass
    base = urllib.parse.urljoin(base_url, p.base) if p.base else base_url
    scored = []
    for n, (rel, sizes, typ, href) in enumerate(p.links):
        url = urllib.parse.urljoin(base, href.strip())
        if not url.lower().startswith('https://'):
            continue
        low = url.lower().split('?')[0]
        if typ == 'image/svg+xml' or low.endswith('.svg') or 'mask-icon' in rel:
            continue                                          # tk SVG cizemez
        sz = _size(sizes)
        apple = any(r.startswith('apple-touch-icon') for r in rel)
        score = (2 if apple else 1) * 1000 + min(sz or (180 if apple else 32), 512) - n * 0.01
        if low.endswith('.ico'):
            score -= 300
        scored.append((score, url))
    out = []
    for _s, u in sorted(scored, key=lambda x: -x[0]):
        if u not in out:
            out.append(u)
    fav = urllib.parse.urljoin(base_url, '/favicon.ico')
    if fav not in out:
        out.append(fav)
    return out


# --------------------------------------------------------------------------- ag
def _get(url, limit, accept):
    if not url.lower().startswith('https://'):
        raise ValueError('yalnizca https')
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': accept})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        if not r.geturl().lower().startswith('https://'):
            raise ValueError('https disina yonlendirme')
        data = r.read(limit + 1)
        if len(data) > limit:
            raise ValueError('cok buyuk')
        return data, (r.headers.get('Content-Type') or '').lower(), r.geturl()


# --------------------------------------------------------------------------- donusturme
def have_pillow():
    try:
        import PIL.Image  # noqa: F401
        return True
    except Exception:
        return False


def png_size(data):
    if data[:8] != PNG_SIG or len(data) < 24:
        return None
    return int.from_bytes(data[16:20], 'big'), int.from_bytes(data[20:24], 'big')


def save_icon(data, out_large, out_small):
    """Gorseli kare PNG'lere cevirir. Donus: True (kaydedildi) / False (desteklenmeyen ya da cok kucuk)."""
    if have_pillow():
        from PIL import Image
        try:
            im = Image.open(io.BytesIO(data))
            if getattr(im, 'format', '') == 'ICO':
                sizes = sorted(im.info.get('sizes') or [im.size], key=lambda s: s[0] * s[1])
                im.size = sizes[-1]                           # ICO icindeki en buyuk kare
            im.load()
            im = im.convert('RGBA')
        except Exception:
            return False
        if min(im.size) < 16:
            return False
        w, h = im.size
        side = max(w, h)
        sq = Image.new('RGBA', (side, side), (0, 0, 0, 0))
        sq.paste(im, ((side - w) // 2, (side - h) // 2))
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.LANCZOS
        out_large.parent.mkdir(parents=True, exist_ok=True)
        sq.resize((LARGE, LARGE), resample).save(out_large, 'PNG')
        sq.resize((SMALL, SMALL), resample).save(out_small, 'PNG')
        return True
    size = png_size(data)
    if not size or min(size) < 16:
        return False
    out_large.parent.mkdir(parents=True, exist_ok=True)
    out_large.write_bytes(data)                               # Pillow yok: arayuz PhotoImage.subsample ile kucultur
    out_small.write_bytes(data)
    return True


# --------------------------------------------------------------------------- dizin (basarisizliklari tekrar tekrar denememek icin)
def load_index(cdir):
    try:
        return json.loads((pathlib.Path(cdir) / 'index.json').read_text(encoding='utf-8'))
    except Exception:
        return {}


def save_index(cdir, idx):
    try:
        pathlib.Path(cdir).mkdir(parents=True, exist_ok=True)
        (pathlib.Path(cdir) / 'index.json').write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding='utf-8')
    except OSError:
        pass


def needs_fetch(app, cdir, idx, now=None):
    if not app.get('site'):
        return False
    large, _small = paths(cdir, app['id'])
    if large.exists():
        return False
    rec = idx.get(app['id'])
    if rec and not rec.get('ok') and (now or time.time()) - rec.get('t', 0) < RETRY_DAYS * 86400:
        return False
    return True


def fetch_icon(app, cdir, get=_get):
    """Tek uygulamanin logosunu indirir. Donus: (ok, aciklama)."""
    base = site_url(app)
    if not base:
        return False, 'site yok'
    large, small = paths(cdir, app['id'])
    try:
        page, _ct, final = get(base, MAX_HTML, 'text/html,*/*;q=0.5')
        cands = icon_candidates(page.decode('utf-8', 'replace'), final or base)
    except Exception as e:
        cands = [urllib.parse.urljoin(base, '/favicon.ico')]
        err = str(e)
    else:
        err = ''
    for url in cands[:5]:
        try:
            data, ct, _f = get(url, MAX_IMAGE, 'image/*')
        except Exception as e:
            err = str(e)
            continue
        if 'text/html' in ct:
            continue
        if save_icon(data, large, small):
            return True, url
        err = 'desteklenmeyen gorsel'
    return False, err or 'simge bulunamadi'
