# -*- coding: utf-8 -*-
"""AGFO System Care 4.3 — AGFO AI Manager baglantisi (AGFO AI Editor ile ayni yol).

AI Manager (WordPress eklentisi, 17.5+) sitedeki API anahtarlariyla calisir; System Care yalniz bir *baglanti anahtari*
(agfoed.…) ile /wp-json/agfo-ai/v1/editor/chat ucuna baglanir. AI Manager 17.16+ 'profile=system_care' ile Windows bakim
asistani istemini kullanir; daha eski surumler ayni ucta 'instruction' ile yine dogru rolde yanit verir.

Gizlilik: anahtar Windows DPAPI ile kullanici hesabina bagli sifrelenir (%LOCALAPPDATA%\\AGFO\\SystemCare\\settings.json);
depoya ya da baska bilgisayara gitmez. Gonderilecek sistem verisi gondermeden once gosterilir ve varsayilan olarak
kullanici adi, bilgisayar adi, e-posta, seri no, MAC ve genel IP adresleri maskelenir.
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    import care_core as _core
    VERSION = _core.VERSION
except Exception:  # testler / tek basina kullanim
    _core = None
    VERSION = '0'

USER_AGENT = 'AGFO-System-Care/%s' % VERSION
TIMEOUT = 150
PROFILE = 'system_care'
TOKEN_PAGE = '/wp-admin/admin.php?page=agfo-ai-editor'
TOKEN_RX = re.compile(r'^agfoed\.\d{1,12}\.[a-z0-9]{8}\.[A-Za-z0-9]{40}$')
MAX_DOCUMENT = 58000            # AI Manager ucu 60.000 karakter sinirli
MAX_MESSAGE = 19000
MAX_TURNS = 12
INSTRUCTION = ('AGFO System Care (Windows bakım uygulaması) içinden soruluyor: Windows bakım ve sorun giderme uzmanı olarak, '
               'yalnız verilen sistem verisine dayanarak kısa ve uygulanabilir yanıt ver; her öneride risk düzeyini '
               '(güvenli / dikkat / riskli) ve geri alınıp alınamayacağını belirt; kritik sistem servislerini ve güvenlik '
               'yazılımını kapatmayı önerme.')

SC_ENTROPY = b'AGFO-System-Care/AI/1'
EDITOR_ENTROPY = b'AGFO-AI-Editor/1'          # AI Editor'un agfo_secrets.py ile ayni (ayni kullanici cozebilir)
PREFIX, TEST_PREFIX = 'dpapi:', 'plain:'


class AIError(Exception):
    pass


# --------------------------------------------------------------------------- DPAPI
def _dpapi(data: bytes, protect: bool, entropy: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]

    def blob(b):
        buf = ctypes.create_string_buffer(b, len(b))
        return BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    src, _k1 = blob(data)
    ent, _k2 = blob(entropy)
    out = BLOB()
    if protect:
        ok = crypt32.CryptProtectData(ctypes.byref(src), 'AGFO System Care', ctypes.byref(ent), None, None, 0x01, ctypes.byref(out))
    else:
        ok = crypt32.CryptUnprotectData(ctypes.byref(src), None, ctypes.byref(ent), None, None, 0x01, ctypes.byref(out))
    if not ok:
        raise OSError('DPAPI işlemi başarısız (kod %d).' % ctypes.GetLastError())
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


def protect(secret: str, entropy: bytes = SC_ENTROPY) -> str:
    if not secret:
        return ''
    raw = secret.encode('utf-8')
    if sys.platform == 'win32':
        return PREFIX + base64.b64encode(_dpapi(raw, True, entropy)).decode('ascii')
    return TEST_PREFIX + base64.b64encode(raw).decode('ascii')   # yalniz Windows disi testler


def unprotect(stored: str, entropy: bytes = SC_ENTROPY) -> str:
    if not stored or not isinstance(stored, str):
        return ''
    try:
        if stored.startswith(PREFIX):
            if sys.platform != 'win32':
                return ''
            return _dpapi(base64.b64decode(stored[len(PREFIX):]), False, entropy).decode('utf-8')
        if stored.startswith(TEST_PREFIX):
            return base64.b64decode(stored[len(TEST_PREFIX):]).decode('utf-8')
    except (OSError, ValueError, UnicodeDecodeError):
        return ''
    return ''


def mask_secret(secret: str) -> str:
    if not secret:
        return ''
    return '•' * 8 + secret[-4:] if len(secret) > 8 else '•' * len(secret)


# --------------------------------------------------------------------------- ayarlar
def load_config(settings: dict) -> dict:
    ai = settings.get('ai') if isinstance(settings.get('ai'), dict) else {}
    return {'url': str(ai.get('url') or ''), 'token': unprotect(ai.get('token') or ''),
            'user': str(ai.get('user') or ''), 'password': unprotect(ai.get('password') or ''),
            'mask': ai.get('mask', True) is not False, 'source': str(ai.get('source') or '')}


def store_config(settings: dict, url='', token='', user='', password='', mask=True, source='') -> dict:
    """Ayarlara sifreli yazar (diske yazmak cagiranin isi: core.save_settings)."""
    settings['ai'] = {'url': (url or '').strip(), 'token': protect(re.sub(r'\s+', '', token or '')),
                      'user': (user or '').strip(), 'password': protect(re.sub(r'\s+', '', password or '')),
                      'mask': bool(mask), 'source': source}
    return settings


def editor_settings_path() -> pathlib.Path:
    base = os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_DATA_HOME') or str(pathlib.Path.home() / '.local' / 'share')
    return pathlib.Path(base) / 'AGFO-AI-Editor' / 'settings.json'


def import_ai_editor(path=None) -> dict:
    """Ayni bilgisayardaki AGFO AI Editor'un AI Manager baglantisini okur. Bulunamazsa {}."""
    p = pathlib.Path(path or editor_settings_path())
    try:
        d = json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    if not isinstance(d, dict) or not str(d.get('manager_url') or '').strip():
        return {}
    out = {'url': str(d.get('manager_url')).strip(), 'token': unprotect(d.get('manager_token') or '', EDITOR_ENTROPY),
           'user': str(d.get('manager_user') or '').strip(), 'password': unprotect(d.get('manager_secret') or '', EDITOR_ENTROPY)}
    if not out['token'] and not (out['user'] and out['password']):
        return {}
    return out


# --------------------------------------------------------------------------- gizlilik maskesi
_EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
_MAC = re.compile(r'\b[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}\b')
_IPV4 = re.compile(r'\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b')
_SERIAL = re.compile(r'(?im)\b(seri(?:\s*no|\s*numarası)?|serial\s*(?:number|no)?|serialnumber|uuid|product\s*key|ürün\s*anahtarı)(\s*[:=]\s*|\t+|\s{2,})(\S+)')
_USERPATH = re.compile(r'(?i)([A-Z]:\\Users\\)([^\\/\s"\']+)')
_TOKENLIKE = re.compile(r'agfoed\.[^\s"\']+|\b(sk-[A-Za-z0-9_-]{6})[A-Za-z0-9_-]+|\bAIza[0-9A-Za-z_-]{10,}')


def _private_ip(a, b) -> bool:
    return a in (10, 127) or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31) or (a == 169 and b == 254) or (a == 100 and 64 <= b <= 127)


def mask_private(text: str, user=None, computer=None) -> str:
    """Kisisel/tanimlayici bilgileri <..> yer tutucularina cevirir. Yerel ag IP'leri (192.168.x, 10.x, Tailscale 100.64/10) kalir:
    sorun gidermede gerekir ve disaridan erisilemez."""
    if not text:
        return ''
    user = os.environ.get('USERNAME', '') if user is None else user
    computer = os.environ.get('COMPUTERNAME', '') if computer is None else computer
    s = _TOKENLIKE.sub('<anahtar>', text)
    s = _USERPATH.sub(lambda m: m.group(1) + '<kullanıcı>', s)
    s = _EMAIL.sub('<e-posta>', s)
    s = _MAC.sub('<MAC>', s)
    s = _SERIAL.sub(lambda m: m.group(1) + m.group(2) + '<gizli>', s)

    def ip(m):
        a, b, c, d = (int(x) for x in m.groups())
        if max(a, b, c, d) > 255 or _private_ip(a, b) or a == 0 or a >= 224:
            return m.group(0)
        return '<genel IP>'
    s = _IPV4.sub(ip, s)
    for word, label in sorted(((computer, '<bilgisayar>'), (user, '<kullanıcı>')), key=lambda x: -len(x[0] or '')):
        if word and len(word) >= 3:
            s = re.sub(r'(?i)(?<![A-Za-z0-9])' + re.escape(word) + r'(?![A-Za-z0-9])', label, s)
    return s


# --------------------------------------------------------------------------- sistem verisi -> metin
def _clip(s, n):
    s = re.sub(r'\s+', ' ', str(s or '')).strip()
    return s if len(s) <= n else s[:n - 1] + '…'


def procs_context(recs, limit=45) -> str:
    rows = sorted((r for r in recs or [] if isinstance(r, dict)), key=lambda r: (-(r.get('cpu') or 0), -(r.get('mem') or 0)))[:limit]
    if not rows:
        return ''
    out = ['ÇALIŞAN SÜREÇLER (işlemci ve belleğe göre ilk %d / %d):' % (len(rows), len(recs)), 'ad | işlemci % | bellek MB | yayıncı | pencere | yol']
    for r in rows:
        out.append(' | '.join([_clip(r.get('name'), 40), '%.1f' % (r.get('cpu') or 0), '%d' % round((r.get('mem') or 0) / 1048576),
                               _clip(r.get('company'), 40), _clip(r.get('title'), 50), _clip(r.get('path'), 90)]))
    return '\n'.join(out)


def services_context(recs, limit=120) -> str:
    """Microsoft disi servisler ve 'otomatik ama durmus' olanlar oncelikli (asil ilgi cekenler)."""
    recs = [r for r in recs or [] if isinstance(r, dict)]
    if not recs:
        return ''
    try:
        import care_procs as pr
        third = [r for r in recs if not pr.is_microsoft_path(r.get('path') or '')]
    except Exception:
        third = recs
    auto_stopped = [r for r in recs if (r.get('start') or '').lower().startswith('auto') and r.get('state') != 'Running']
    seen, rows = set(), []
    for r in third + auto_stopped:
        k = r.get('name')
        if k in seen:
            continue
        seen.add(k)
        rows.append(r)
    rows = rows[:limit]
    running = sum(1 for r in recs if r.get('state') == 'Running')
    out = ['SERVİSLER: toplam %d, çalışan %d. Aşağıda Microsoft dışı ve "otomatik ama durmuş" olanlar (%d):' % (len(recs), running, len(rows)),
           'ad | görünen ad | durum | başlangıç | yol']
    for r in rows:
        start = (r.get('start') or '') + (' (gecikmeli)' if r.get('delayed') else '')
        out.append(' | '.join([_clip(r.get('name'), 40), _clip(r.get('display'), 60), r.get('state') or '', start, _clip(r.get('path'), 90)]))
    return '\n'.join(out)


def startup_context(recs) -> str:
    recs = [r for r in recs or [] if isinstance(r, dict)]
    if not recs:
        return ''
    out = ['BAŞLANGIÇ ÖĞELERİ (%d, %d etkin):' % (len(recs), sum(1 for r in recs if r.get('enabled'))), 'ad | durum | konum | komut']
    for r in recs[:150]:
        out.append(' | '.join([_clip(r.get('name'), 50), 'etkin' if r.get('enabled') else 'devre dışı', r.get('scope') or '', _clip(r.get('command'), 120)]))
    return '\n'.join(out)


def log_context(text, limit=12000) -> str:
    text = (text or '').strip()
    if not text:
        return ''
    if len(text) > limit:
        text = '…\n' + text[-limit:]
    return 'İŞLEM GÜNLÜĞÜ (son kısım):\n' + text


def build_document(parts, mask=True, user=None, computer=None) -> str:
    """parts: [(baslik, metin)] -> AI Manager'a gidecek tek belge (sinirli ve istege gore maskeli)."""
    blocks = []
    for title, body in parts:
        body = (body or '').strip()
        if body:
            blocks.append('=== %s ===\n%s' % (title, body))
    doc = '\n\n'.join(blocks)
    if mask:
        doc = mask_private(doc, user, computer)
    if len(doc) > MAX_DOCUMENT:
        doc = doc[:MAX_DOCUMENT - 40] + '\n… (veri kısaltıldı)'
    return doc


# --------------------------------------------------------------------------- HTTP
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _request(url, method='GET', headers=None, payload=None, timeout=TIMEOUT):
    data = None
    hdrs = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}
    hdrs.update(headers or {})
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        hdrs['Content-Type'] = 'application/json; charset=utf-8'
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl.create_default_context()), _NoRedirect())
        with op.open(req, timeout=timeout) as r:
            return r.status, r.read(8 * 1024 * 1024), dict(r.headers)
    except urllib.error.HTTPError as e:
        try:
            body = e.read(1024 * 1024)
        except Exception:
            body = b''
        return e.code, body, dict(e.headers or {})
    except urllib.error.URLError as e:
        reason = getattr(e, 'reason', e)
        if isinstance(reason, ssl.SSLError):
            raise AIError('Güvenli bağlantı kurulamadı (SSL): %s' % reason)
        raise AIError('Sunucuya ulaşılamadı: %s' % reason)
    except (TimeoutError, OSError) as e:
        raise AIError('Bağlantı zaman aşımına uğradı veya kesildi: %s' % e)


def _json(body):
    try:
        return json.loads((body or b'').decode('utf-8', 'replace'))
    except ValueError:
        return None


def _err(decoded, status) -> str:
    msg = ''
    if isinstance(decoded, dict):
        e = decoded.get('error')
        msg = str(e.get('message') or '') if isinstance(e, dict) else (e if isinstance(e, str) else '')
        msg = msg or str(decoded.get('message') or '')
    msg = re.sub(r'\s+', ' ', msg).strip()[:400]
    return msg or 'HTTP %s' % status


def normalize_url(url: str) -> str:
    url = (url or '').strip().rstrip('/')
    for suffix in ('/wp-admin', '/wp-json'):
        if url.lower().endswith(suffix):
            url = url[:-len(suffix)]
    if url and not re.match(r'^https?://', url, re.I):
        url = 'https://' + url
    u = urllib.parse.urlsplit(url)
    if not u.hostname:
        raise AIError('Geçerli bir site adresi girin (örn. https://agfocert.com).')
    if u.scheme.lower() == 'http' and u.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise AIError('Güvenlik için site adresi https:// ile başlamalı (anahtar açık ağda gönderilmez).')
    return url


class ManagerClient:
    """AI Manager /editor/* uclari icin istemci (AGFO AI Editor'un ManagerBackend'inin System Care surumu)."""

    def __init__(self, url: str, token: str = '', user: str = '', password: str = '', request=_request, sleep=time.sleep):
        self.base = normalize_url(url)
        self.token = re.sub(r'\s+', '', token or '')
        self.user = (user or '').strip()
        self.password = re.sub(r'\s+', '', password or '')
        self._request, self._sleep = request, sleep
        self._style = None
        self.server = {}

    def configured(self) -> bool:
        return bool(self.base and (self.token or (self.user and self.password)))

    def auth_headers(self) -> dict:
        if self.token:
            return {'X-AGFO-Editor-Token': self.token}
        if self.user and self.password:
            basic = base64.b64encode(('%s:%s' % (self.user, self.password)).encode('utf-8')).decode('ascii')
            return {'Authorization': 'Basic ' + basic, 'X-AGFO-Editor-Auth': basic}
        return {}

    def _url(self, route, style):
        if style == 'query':
            return self.base + '/?rest_route=' + urllib.parse.quote('/agfo-ai/v1' + route, safe='/')
        return self.base + '/wp-json/agfo-ai/v1' + route

    def call(self, route, payload=None, timeout=TIMEOUT, auth=True):
        if auth and not self.configured():
            raise AIError('AI Manager bağlantısı ayarlanmamış: site adresini ve bağlantı anahtarını girin.')
        headers = self.auth_headers()
        styles = [self._style] if self._style else ['pretty', 'query']
        last = (0, None)
        for style in styles:
            for attempt in range(4):
                status, body, rh = self._request(self._url(route, style), 'POST' if payload is not None else 'GET', headers, payload, timeout)
                decoded = _json(body)
                if status in (429, 502, 503, 504, 529) and attempt < 3 and not (isinstance(decoded, dict) and decoded.get('code') == 'agfo_content_config'):
                    wait = 0.0
                    for k, v in (rh or {}).items():
                        if k.lower() == 'retry-after':
                            try:
                                wait = float(v)
                            except ValueError:
                                pass
                    self._sleep(min(30.0, wait or 2.0 * (2 ** attempt)))
                    continue
                break
            if 300 <= status < 400:
                loc = next((v for k, v in (rh or {}).items() if k.lower() == 'location'), '')
                t = urllib.parse.urlsplit(loc)
                hint = '%s://%s' % (t.scheme, t.netloc) if t.netloc else loc
                raise AIError('Site adresi yönlendiriliyor (%s → %s). Site adresi olarak %s yazın.' % (self.base, hint or '?', hint or 'yönlendirilen adresi'))
            if status == 404 and style == 'pretty' and not isinstance(decoded, dict):
                last = (status, decoded)
                continue
            if 200 <= status < 300 and isinstance(decoded, dict):
                self._style = style
                return decoded
            last = (status, decoded)
            break
        status, decoded = last
        code = decoded.get('code') if isinstance(decoded, dict) else ''
        if status == 401:
            if code == 'agfo_editor_token_invalid':
                raise AIError('Bağlantı anahtarı geçersiz veya silinmiş. WordPress › AI Manager › AI Editor / System Care bağlantısı '
                              'sayfasından yeni anahtar oluşturup tamamını yapıştırın.')
            raise AIError('Kimlik doğrulanamadı (%s). Bağlantı anahtarını kontrol edin.' % (code or 'HTTP 401'))
        if status == 403:
            raise AIError('Bu anahtarın sahibi olan WordPress kullanıcısının AI Manager yetkisi yok: ' + _err(decoded, status))
        if status == 404 and code in ('rest_no_route', ''):
            raise AIError('Sitede AI Manager ucu bulunamadı. AGFO AI Manager 17.5.0 veya üstü kurulu ve etkin olmalı.')
        raise AIError('AI Manager: ' + _err(decoded, status))

    def ping(self) -> dict:
        self.server = self.call('/editor/ping', timeout=30, auth=False)
        return self.server

    def info(self) -> dict:
        return self.call('/editor/info', timeout=30)

    def test(self) -> dict:
        """{'ok', 'message', 'version', 'profile', 'model'}"""
        out = {'ok': False, 'message': '', 'version': '', 'profile': False, 'model': '', 'user': ''}
        try:
            p = self.ping()
            out['version'] = str(p.get('plugin_version') or '')
            out['profile'] = PROFILE in (p.get('profiles') or [])
        except AIError as e:
            out['message'] = str(e)
        try:
            info = self.info()
        except AIError as e:
            out['message'] = str(e)
            return out
        out['version'] = out['version'] or str(info.get('plugin_version') or '')
        out['user'] = str(info.get('user') or '')
        out['model'] = ' / '.join(x for x in (str(info.get('text_provider') or ''), str(info.get('text_model') or '')) if x)
        if info.get('text_ready') is False:
            out['message'] = 'Bağlantı tamam, ama AI Manager\'da metin sağlayıcısı/modeli seçilmemiş (AI Manager › Ayarlar).'
            return out
        out['ok'] = True
        return out

    def chat(self, messages, document='', max_tokens=2400) -> dict:
        msgs = []
        for m in (messages or [])[-MAX_TURNS:]:
            role = 'assistant' if m.get('role') == 'assistant' else 'user'
            content = str(m.get('content') or '').strip()[:MAX_MESSAGE]
            if content:
                msgs.append({'role': role, 'content': content})
        if not msgs or msgs[-1]['role'] != 'user':
            raise AIError('Bir soru yazın.')
        payload = {'messages': msgs, 'document': (document or '')[:MAX_DOCUMENT], 'profile': PROFILE, 'instruction': INSTRUCTION,
                   'max_output_tokens': int(max(256, min(8000, max_tokens)))}
        d = self.call('/editor/chat', payload, timeout=240 if max_tokens > 3000 else TIMEOUT)
        text = d.get('text') if isinstance(d.get('text'), str) else ''
        if not text.strip():
            raise AIError('AI Manager boş yanıt döndürdü.')
        return {'text': clean_reply(text), 'provider': str(d.get('provider') or ''), 'model': str(d.get('model') or ''),
                'truncated': bool(d.get('truncated'))}


def clean_reply(text: str) -> str:
    """Model bazen Markdown dondurur; duz metin kutusunda okunur hale getir."""
    s = (text or '').replace('\r\n', '\n').strip()
    s = re.sub(r'^```[a-zA-Z]*\s*\n?|\n?```$', '', s)
    s = re.sub(r'(?m)^#{1,6}\s*', '', s)
    s = re.sub(r'\*\*(.+?)\*\*', r'\1', s)
    s = re.sub(r'(?m)^\s*[*•]\s+', '- ', s)
    s = re.sub(r'<[^>]{1,40}>', lambda m: m.group(0) if m.group(0).startswith(('<kullanıcı', '<bilgisayar', '<gizli', '<e-posta', '<MAC', '<genel', '<anahtar')) else '', s)
    return re.sub(r'\n{3,}', '\n\n', s).strip()


QUICK = [
    ('Bilgisayarımı değerlendir', ('hw', 'procs', 'startup'),
     'Ekteki sistem verisine bakarak bilgisayarın genel durumunu değerlendir. Önce en önemli 3 sorunu, sonra yapılabilecekleri sırala.'),
    ('Açılışı hızlandır', ('startup',),
     'Başlangıç öğelerini incele. Hangileri güvenle devre dışı bırakılabilir, hangileri kalmalı? Her biri için kısa gerekçe ver.'),
    ('Servisleri incele', ('services',),
     'Servis listesini incele: şüpheli, gereksiz ya da hatalı görünen servisler var mı? "Otomatik ama durmuş" olanlar sorun mu?'),
    ('Yavaşlığın nedeni ne?', ('procs', 'hw'),
     'Bilgisayar yavaş. Çalışan süreçlere ve donanım bilgisine bakarak olası nedenleri ve çözümleri sırala.'),
    ('Günlükteki hatayı açıkla', ('log',),
     'İşlem günlüğündeki son hata ya da uyarıyı açıkla: ne anlama geliyor, nedeni ne olabilir, nasıl düzeltirim?'),
]
