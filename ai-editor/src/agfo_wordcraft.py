# -*- coding: utf-8 -*-
"""AGFO AI Editor 1.8 - WordCraft koprusu (yalnizca Python standart kutuphanesi).

WordCraft (github.com/storytold/wordcraft, MIT OR Apache-2.0) Word benzeri, acik kaynakli bir kelime
islemcidir: serit, stiller, tablolar, degisiklik izleme, yorumlar, icindekiler, dipnot, adres mektup
birlestirme, DOCX/ODT/RTF/PDF. AI Editor onu belge duzenleyici olarak kullanir:

- Kurulum: resmi, kod imzali Windows "portable" ZIP'i bu modulde sabitlenen surum ve SHA-256 ile
  %LOCALAPPDATA%\\Programs\\AGFO-AI-Editor\\WordCraft\\<surum> altina acilir. Dosya tarayicidan degil bu
  koddan indirildigi icin Mark-of-the-Web tasimaz. ArtCraft adi/logolari degistirilmez; resmi derleme
  oldugu gibi calistirilir.
- Turkce yazim denetimi: LibreOffice'in tr_TR Hunspell sozlugu (MPL 2.0), sabit commit + SHA-256,
  WordCraft'in aradigi %LOCALAPPDATA%\\WordCraft\\dictionaries klasorune.
- Baglanti: WordCraft '--control PORT' ile baslatilir; yalnizca 127.0.0.1'de dinler, her istek
  pencerenin <ayarlar>/control-key.local-PORT dosyasindaki anahtariyla yapilir (docs/control-protocol.md).
- Okuma: document.inspect -> secim, paragraf stilleri, kalin/italik araliklari (UTF-8 bayt ofseti) ->
  Markdown. Degisiklik izlemede silinmis (del) metin kaynaga girmez.
- Yazma: Markdown -> HTML -> edit.paste. Uygulamadan once secim yeniden kurulur ve metninin degismedigi
  dogrulanir; degisiklik izleme acikken revizyonlar 'AGFO AI Editor' yazariyla duser.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

WORDCRAFT_VERSION = '0.10.0'
RELEASE_URL = 'https://github.com/storytold/wordcraft/releases/download/v%s/%s'
# SHA256SUMS.txt (v0.10.0): yalnizca bu ozetlerle eslesen dosya kurulur.
PORTABLE = {
    'x64': ('wordcraft-0.10.0-windows-x64-portable.zip', '141d9458d776b4a664f20fbb0e2cd5619c327e0873abbc01bf4530dc339592fb'),
    'arm64': ('wordcraft-0.10.0-windows-arm64-portable.zip', 'c20a97f30a3e280377f6dc45577b0f559ad7cd686dd8cdcbda27e4a75eedefad'),
    'x86': ('wordcraft-0.10.0-windows-x86-portable.zip', '053d1175ab10d2b4aed025af5fdb82de2c75919c579a8a30ed6cb965b24ae5ed'),
}
DICT_COMMIT = '67032ee957631908098a72edf48dc81cac27e369'   # LibreOffice/dictionaries
DICT_URL = 'https://raw.githubusercontent.com/LibreOffice/dictionaries/%s/tr_TR/%s'
DICT_FILES = {
    'tr_TR.aff': 'a04a227b2ee45574000b876a1afa982e3436d49ebb97a7a796ddc5ec0cc8191b',
    'tr_TR.dic': '48e5352c5770956b24f355265aef7649b25bcb4d933c0b254ea8b419c241f4bd',
}
ALLOWED_HOSTS = ('github.com', 'githubusercontent.com')
AUTHOR = 'AGFO AI Editor'
USER_AGENT = 'AGFO-AI-Editor-WordCraft'
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
MAX_ZIP_BYTES = 400 * 1024 * 1024

HEADING_STYLES = {'Title': 1, 'Heading1': 1, 'Heading2': 2, 'Heading3': 3, 'Heading4': 4, 'Heading5': 5, 'Heading6': 6}


class WordCraftError(Exception):
    pass


# --------------------------------------------------------------------------- yollar
def _local_appdata() -> pathlib.Path:
    return pathlib.Path(os.environ.get('LOCALAPPDATA') or (pathlib.Path.home() / '.local' / 'share'))


def install_root() -> pathlib.Path:
    return _local_appdata() / 'Programs' / 'AGFO-AI-Editor' / 'WordCraft'


def windows_arch() -> str:
    a = (os.environ.get('PROCESSOR_ARCHITEW6432') or os.environ.get('PROCESSOR_ARCHITECTURE') or platform.machine() or '').lower()
    if 'arm64' in a or 'aarch64' in a:
        return 'arm64'
    if a in ('x86', 'i386', 'i686'):
        return 'x86'
    return 'x64'


def installed_exe(version: str = WORDCRAFT_VERSION) -> pathlib.Path | None:
    """Kurulu wordcraft.exe; gelistirme/test icin AGFO_WORDCRAFT_EXE ortam degiskeni oncelikli."""
    env = os.environ.get('AGFO_WORDCRAFT_EXE')
    if env:
        p = pathlib.Path(env)
        return p if p.is_file() else None
    base = install_root() / version
    if not base.is_dir():
        return None
    for p in sorted(base.rglob('wordcraft.exe')):
        return p
    return None


def settings_dir() -> pathlib.Path:
    """WordCraft'in ayar klasoru (control-key dosyasinin yeri); crates/control-key ile ayni kural."""
    prof = os.environ.get('WORDCRAFT_PROFILE_DIR')
    if prof:
        return pathlib.Path(prof)
    if sys.platform == 'win32':
        return pathlib.Path(os.environ.get('APPDATA') or pathlib.Path.home()) / 'WordCraft'
    if sys.platform == 'darwin':
        return pathlib.Path.home() / 'Library' / 'Application Support' / 'WordCraft'
    return pathlib.Path(os.environ.get('XDG_CONFIG_HOME') or pathlib.Path.home() / '.config') / 'wordcraft'


def key_path(port: int) -> pathlib.Path:
    return settings_dir() / ('control-key.local-%d' % int(port))


def dictionary_dir() -> pathlib.Path:
    return _local_appdata() / 'WordCraft' / 'dictionaries'


def dictionary_installed() -> bool:
    d = dictionary_dir()
    return all((d / n).is_file() and (d / n).stat().st_size > 0 for n in DICT_FILES)


# --------------------------------------------------------------------------- indirme / kurulum
def host_allowed(url: str) -> bool:
    from urllib.parse import urlsplit
    u = urlsplit(url or '')
    h = (u.hostname or '').lower()
    return u.scheme == 'https' and any(h == d or h.endswith('.' + d) for d in ALLOWED_HOSTS)


def _open(url, timeout=60):
    import urllib.request

    class Guard(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not host_allowed(newurl):
                raise WordCraftError('İzin verilmeyen yönlendirme engellendi: %s' % newurl)
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    if not host_allowed(url):
        raise WordCraftError('İzin verilmeyen adres: %s' % url)
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    return urllib.request.build_opener(Guard()).open(req, timeout=timeout)


def download(url, dest: pathlib.Path, sha256: str, progress=None, should_stop=None, opener=None, limit=MAX_ZIP_BYTES):
    """URL'yi dest'e indirir; SHA-256 tutmazsa dosyayi siler ve hata firlatir. opener testler icindir."""
    dest = pathlib.Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + '.part')
    h = hashlib.sha256()
    got = 0
    try:
        with (opener or _open)(url) as r, open(tmp, 'wb') as f:
            total = int(r.headers.get('Content-Length') or 0) if getattr(r, 'headers', None) else 0
            while True:
                if should_stop and should_stop():
                    raise WordCraftError('İndirme durduruldu.')
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                got += len(chunk)
                if got > limit:
                    raise WordCraftError('Dosya beklenenden büyük; indirme durduruldu.')
                h.update(chunk)
                f.write(chunk)
                if progress:
                    progress(got, total)
        if h.hexdigest() != sha256.lower():
            raise WordCraftError('SHA-256 tutmuyor (%s); dosya silindi, hiçbir şey kurulmadı.' % dest.name)
        os.replace(tmp, dest)
    except WordCraftError:
        _unlink(tmp)
        raise
    except Exception as e:
        _unlink(tmp)
        raise WordCraftError('İndirilemedi: %s' % e)
    return dest


def _unlink(p):
    try:
        pathlib.Path(p).unlink()
    except OSError:
        pass


def safe_extract(zip_path, target: pathlib.Path) -> None:
    """ZIP'i hedefe acar; mutlak yol, '..' ve suruc harfi iceren girdileri reddeder."""
    target = pathlib.Path(target)
    root = target.resolve()
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            name = info.filename.replace('\\', '/')
            if name.startswith('/') or ':' in name.split('/')[0] or any(part == '..' for part in name.split('/')):
                raise WordCraftError('ZIP içinde güvensiz yol: %s' % info.filename)
            dest = (target / name).resolve()
            if root not in dest.parents and dest != root:
                raise WordCraftError('ZIP içinde güvensiz yol: %s' % info.filename)
        z.extractall(target)


def install(progress=None, should_stop=None, opener=None, with_dictionary=True, arch=None) -> pathlib.Path:
    """Sabit surumu kurar (kuruluysa dokunmaz). Donus: wordcraft.exe yolu."""
    exe = installed_exe()
    if exe and not os.environ.get('AGFO_WORDCRAFT_EXE'):
        if with_dictionary and not dictionary_installed():
            install_dictionary(progress=progress, should_stop=should_stop, opener=opener)
        return exe
    if os.environ.get('AGFO_WORDCRAFT_EXE'):
        raise WordCraftError('AGFO_WORDCRAFT_EXE gösterdiği dosya yok: %s' % os.environ['AGFO_WORDCRAFT_EXE'])
    name, sha = PORTABLE[arch or windows_arch()]
    root = install_root()
    root.mkdir(parents=True, exist_ok=True)
    zpath = root / name
    download(RELEASE_URL % (WORDCRAFT_VERSION, name), zpath, sha, progress, should_stop, opener)
    work = root / (WORDCRAFT_VERSION + '.new')
    shutil.rmtree(work, ignore_errors=True)
    try:
        safe_extract(zpath, work)
        final = root / WORDCRAFT_VERSION
        shutil.rmtree(final, ignore_errors=True)
        os.replace(work, final)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        _unlink(zpath)
    for old in root.iterdir():                     # eski surum klasorlerini temizle
        if old.is_dir() and old.name != WORDCRAFT_VERSION:
            shutil.rmtree(old, ignore_errors=True)
    exe = installed_exe()
    if not exe:
        raise WordCraftError('Kurulumdan sonra wordcraft.exe bulunamadı.')
    if with_dictionary and not dictionary_installed():
        install_dictionary(progress=progress, should_stop=should_stop, opener=opener)
    return exe


def install_dictionary(progress=None, should_stop=None, opener=None) -> pathlib.Path:
    d = dictionary_dir()
    for name, sha in DICT_FILES.items():
        p = d / name
        if p.is_file() and file_sha256(p) == sha:
            continue
        download(DICT_URL % (DICT_COMMIT, name), p, sha, progress, should_stop, opener, limit=64 * 1024 * 1024)
    return d


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- baslatma
def free_port() -> int:
    s = socket.socket()
    try:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _scrub_env():
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(('_PYI_', '_MEIPASS'))}
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return env


def launch(exe, files=(), port=None, popen=subprocess.Popen, wait=30.0, sleep=time.sleep):
    """WordCraft'i kontrol portuyla baslatir, anahtar dosyasi yazilana kadar bekler. Donus: Client."""
    port = int(port or free_port())
    kp = key_path(port)
    _unlink(kp)                                    # onceki bir oturumdan kalan anahtar okunmasin
    args = [str(exe), '--control', str(port)] + [str(f) for f in files]
    kw = {'env': _scrub_env(), 'close_fds': True, 'cwd': str(pathlib.Path(exe).parent)}
    if sys.platform == 'win32':
        kw['creationflags'] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kw['start_new_session'] = True
        kw['stdout'] = kw['stderr'] = subprocess.DEVNULL
    proc = popen(args, **kw)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if kp.is_file() and kp.stat().st_size >= 32:
            c = Client(port)
            c.process = proc
            return c
        if proc is not None and hasattr(proc, 'poll') and proc.poll() is not None:
            raise WordCraftError('WordCraft açılırken kapandı (çıkış kodu %s). Ekran kartı sürücüsünü güncelleyin; '
                                 'sorun sürerse %s dosyasına bakın.' % (proc.returncode, settings_dir() / 'logs' / 'wordcraft.log'))
        sleep(0.2)
    raise WordCraftError('WordCraft %d sn içinde hazır olmadı.' % int(wait))


# --------------------------------------------------------------------------- istemci
class Client:
    """Satir basina bir JSON istek/yanit. Is parcaciklarindan cagrilabilir (kilitli)."""

    def __init__(self, port, key=None, timeout=20.0):
        self.port = int(port)
        self._key = key
        self.timeout = timeout
        self._sock = None
        self._file = None
        self._id = 0
        self._lock = threading.Lock()
        self.process = None

    def key(self) -> str:
        if self._key:
            return self._key
        try:
            k = key_path(self.port).read_text(encoding='ascii').strip()
        except OSError:
            raise WordCraftError('WordCraft kapalı ya da anahtar dosyası yok.')
        if not k:
            raise WordCraftError('WordCraft anahtar dosyası boş.')
        return k

    def close(self):
        for o in (self._file, self._sock):
            try:
                if o:
                    o.close()
            except OSError:
                pass
        self._sock = self._file = None

    def _connect(self):
        self.close()
        try:
            self._sock = socket.create_connection(('127.0.0.1', self.port), timeout=self.timeout)
        except OSError:
            raise WordCraftError('WordCraft\'a bağlanılamadı; pencere kapatılmış olabilir.')
        self._file = self._sock.makefile('rwb')
        self._send({'method': 'auth', 'key': self.key()})

    def _send(self, msg):
        self._id += 1
        msg = dict(msg, id=self._id)
        self._file.write((json.dumps(msg, ensure_ascii=False) + '\n').encode('utf-8'))
        self._file.flush()
        line = self._file.readline()
        if not line:
            raise ConnectionError('bağlantı kapandı')
        r = json.loads(line.decode('utf-8'))
        if not r.get('ok'):
            err = r.get('error') or 'bilinmeyen hata'
            if err == 'unauthorized':
                self.close()
                raise WordCraftError('WordCraft anahtarı reddetti (pencere yeniden açılmış olabilir).')
            raise WordCraftError(err)
        return r.get('result')

    def call(self, method, params=None):
        with self._lock:
            for attempt in (0, 1):
                try:
                    if self._file is None:
                        self._connect()
                    msg = {'method': method}
                    if params is not None:
                        msg['params'] = params
                    return self._send(msg)
                except (OSError, ConnectionError, ValueError):
                    self.close()
                    if attempt:
                        raise WordCraftError('WordCraft yanıt vermiyor; pencere kapatılmış olabilir.')

    def execute(self, command, params=None):
        return self.call('engine.execute', {'command': command, 'params': params or {}})

    def alive(self) -> bool:
        try:
            self.call('ui.inspect')
            return True
        except WordCraftError:
            return False

    # -- yuksek seviye
    def inspect(self) -> dict:
        return self.call('document.inspect') or {}

    def setup(self, interface_language='tr', author=AUTHOR):
        """Baglantidan hemen sonra: arayuz dili ve AI revizyonlarinin yazari."""
        for m, p in (('ui.language', {'value': interface_language}), ('file.setAuthor', {'name': author})):
            try:
                self.execute(m, p)
            except WordCraftError:
                pass

    def new_document(self, html=None, turkish=True):
        self.execute('file.new', {'template': 'blank'})
        if turkish:
            self.set_language_all('tr-TR', default=True)
        if html:
            self.execute('edit.paste', {'html': html})

    def open(self, path):
        return self.execute('file.open', {'path': str(path)})

    def set_language_all(self, lang='tr-TR', default=False):
        try:
            self.execute('select.all')
            self.execute('review.language', {'lang': lang, 'default': bool(default)})
            self.execute('select.collapse')
        except WordCraftError:
            pass

    def capture(self, scope='selection') -> dict:
        """AI'ya gidecek metni alir. scope: 'selection' (yoksa imlecin paragrafi) | 'all'.
        Donus: {'markdown', 'text', 'anchor', 'focus', 'where', 'name'}"""
        if scope == 'all':
            self.execute('select.all')
        info = self.inspect()
        sel = info.get('selection') or {}
        anchor, focus = sel.get('anchor'), sel.get('focus')
        where = 'belge' if scope == 'all' else 'seçim'
        if anchor and focus and anchor == focus and scope != 'all':
            self.execute('select.paragraph')
            info = self.inspect()
            sel = info.get('selection') or {}
            anchor, focus = sel.get('anchor'), sel.get('focus')
            where = 'paragraf'
        text = sel.get('text') or ''
        md = selection_markdown(info) if anchor and focus else ''
        return {'markdown': md or text, 'text': text, 'anchor': anchor, 'focus': focus, 'where': where,
                'name': info.get('name') or ''}

    def apply(self, cap: dict, html: str, mode='replace', track=True, verify=True) -> dict:
        """AI sonucunu uygular. mode: 'replace' | 'below' | 'append'. Secim degismisse WordCraftError."""
        a, f = cap.get('anchor'), cap.get('focus')
        if not a or not f:
            raise WordCraftError('Hedef aralık bilinmiyor.')
        self.execute('select.range', {'anchor': a, 'focus': f})
        if verify:
            now = (self.call('document.selection') or {}).get('text', '')
            if _norm(now) != _norm(cap.get('text', '')):
                raise WordCraftError('Siz beklerken WordCraft\'taki bu bölüm değişti; öneri uygulanmadı. '
                                     'Metni yeniden seçip işlemi tekrarlayın.')
        self.execute('file.setAuthor', {'name': AUTHOR})
        if track:
            self.execute('review.trackChanges', {'value': True})
        if mode in ('below', 'append'):
            end = max(a, f, key=_pos_key)
            self.execute('select.range', {'anchor': end, 'focus': end})
        return self.execute('edit.paste', {'html': html}) or {}

    def document_markdown(self) -> str:
        info = self.inspect()
        return blocks_markdown(info.get('blocks') or [])


def _norm(s: str) -> str:
    return ' '.join((s or '').split())


def _pos_key(p):
    return (list(p.get('path') or []), int(p.get('off') or 0))


# --------------------------------------------------------------------------- Markdown
def _runs_markdown(text: str, runs, start: int = 0, end: int | None = None) -> str:
    """Bir paragrafin [start, end) bayt araligini kalin/italik isaretleriyle verir; silinmis (del) metni atlar."""
    raw = text.encode('utf-8')
    end = len(raw) if end is None else min(end, len(raw))
    cuts = {start, end}
    for r in runs or []:
        for k in ('start', 'end'):
            v = int(r.get(k, 0))
            if start < v < end:
                cuts.add(v)
    pts = sorted(cuts)
    out = []
    for s, e in zip(pts, pts[1:]):
        props = {}
        for r in runs or []:
            if int(r.get('start', 0)) <= s and e <= int(r.get('end', 0)):
                props.update(r.get('props') or {})
        if 'del' in props:                         # deger revizyon numarasidir; 0 da silinmis demektir
            continue
        seg = raw[s:e].decode('utf-8', errors='ignore')
        if not seg:
            continue
        b, i = bool(props.get('bold')), bool(props.get('italic'))
        if (b or i) and seg.strip():
            lead = seg[:len(seg) - len(seg.lstrip())]
            trail = seg[len(seg.rstrip()):]
            core_ = seg.strip()
            mark = '***' if b and i else '**' if b else '*'
            seg = lead + mark + core_ + mark + trail
        out.append(seg)
    return ''.join(out)


def _block_markdown(b, start=0, end=None) -> str:
    if b.get('type') == 'table':
        cells = b.get('cells') or []
        if not cells:
            return ''
        w = max(len(r) for r in cells)
        rows = [[(c or '').replace('|', '\\|').replace('\n', ' ') for c in r] + [''] * (w - len(r)) for r in cells]
        lines = ['| ' + ' | '.join(rows[0]) + ' |', '|' + '---|' * w]
        lines += ['| ' + ' | '.join(r) + ' |' for r in rows[1:]]
        return '\n'.join(lines)
    body = _runs_markdown(b.get('text') or '', b.get('runs'), start, end)
    if not body.strip():
        return ''
    style = b.get('style') or ''
    lvl = HEADING_STYLES.get(style)
    if lvl:
        return '#' * lvl + ' ' + body.strip().replace('**', '')
    if b.get('list'):
        indent = '  ' * int((b.get('list') or {}).get('level') or 0)
        return indent + '- ' + body.strip()
    return body


def blocks_markdown(blocks) -> str:
    parts = [_block_markdown(b) for b in blocks]
    return _join(parts, blocks)


def _join(parts, blocks):
    out = []
    prev_list = False
    for md, b in zip(parts, blocks):
        if not md:
            continue
        is_list = md.lstrip().startswith('- ') and bool(b.get('list'))
        if out:
            out.append('\n' if (is_list and prev_list) else '\n\n')
        out.append(md)
        prev_list = is_list
    return ''.join(out)


def selection_markdown(info: dict) -> str:
    """document.inspect sonucundaki secimi Markdown'a cevirir. Govde (body) disindaki secimlerde ya da
    tablo hucresi icindeki secimde '' doner (cagiran duz metne duser)."""
    sel = info.get('selection') or {}
    a, f = sel.get('anchor'), sel.get('focus')
    if not a or not f or a.get('story') != 'body' or f.get('story') != 'body':
        return ''
    s, e = sorted((a, f), key=_pos_key)
    sp, ep = list(s.get('path') or []), list(e.get('path') or [])
    if len(sp) != 1 or len(ep) != 1:
        return ''
    blocks = info.get('blocks') or []
    first, last = sp[0], ep[0]
    chosen, parts = [], []
    for b in blocks:
        i = b.get('index')
        if i is None or i < first or i > last:
            continue
        if b.get('type') == 'table':
            md = _block_markdown(b)
        else:
            bs = int(s.get('off') or 0) if i == first else 0
            be = int(e.get('off') or 0) if i == last else None
            if i == last and be == 0 and last > first:
                continue                            # secim sonraki paragrafin basinda bitiyor
            md = _block_markdown(b, bs, be)
        chosen.append(b)
        parts.append(md)
    return _join(parts, chosen)
