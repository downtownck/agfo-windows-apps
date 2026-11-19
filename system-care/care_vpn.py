"""AGFO System Care - VPN sayfasi (WireGuard) icin GUI'den bagimsiz yardimcilar (test edilebilir).

WireGuard for Windows (acik kaynak, resmi istemci) motor olarak kullanilir; System Care onun belgelenmis komut
satiri arayuzunu kullanir:  wireguard.exe /installtunnelservice <yol>  ve  /uninstalltunnelservice <ad>.
Tunel yapilandirmalari WireGuard'in kendi klasorune (Program Files\\WireGuard\\Data\\Configurations) kopyalanir;
WireGuard yoneticisi bunlari DPAPI ile sifreler (.conf.dpapi). Ozel anahtar System Care'in klasorlerinde tutulmaz.
Yapilandirma dosyalari VPN saglayicisindan (Proton VPN, Mullvad ...) ya da kendi sunucunuzdan gelir.
"""
import os
import pathlib
import re

WG_PKG = 'WireGuard.WireGuard'
NAME_RX = re.compile(r'^[A-Za-z0-9_=+.\-]{1,32}$')
COUNTRIES = {
    'AL': 'Arnavutluk', 'AR': 'Arjantin', 'AT': 'Avusturya', 'AU': 'Avustralya', 'BA': 'Bosna-Hersek', 'BE': 'Belçika', 'BG': 'Bulgaristan',
    'BR': 'Brezilya', 'CA': 'Kanada', 'CH': 'İsviçre', 'CL': 'Şili', 'CO': 'Kolombiya', 'CY': 'Kıbrıs', 'CZ': 'Çekya', 'DE': 'Almanya',
    'DK': 'Danimarka', 'EE': 'Estonya', 'EG': 'Mısır', 'ES': 'İspanya', 'FI': 'Finlandiya', 'FR': 'Fransa', 'GB': 'Birleşik Krallık',
    'UK': 'Birleşik Krallık', 'GE': 'Gürcistan', 'GR': 'Yunanistan', 'HK': 'Hong Kong', 'HR': 'Hırvatistan', 'HU': 'Macaristan',
    'ID': 'Endonezya', 'IE': 'İrlanda', 'IL': 'İsrail', 'IN': 'Hindistan', 'IS': 'İzlanda', 'IT': 'İtalya', 'JP': 'Japonya', 'KR': 'Güney Kore',
    'LT': 'Litvanya', 'LU': 'Lüksemburg', 'LV': 'Letonya', 'MD': 'Moldova', 'MK': 'Kuzey Makedonya', 'MX': 'Meksika', 'MY': 'Malezya',
    'NG': 'Nijerya', 'NL': 'Hollanda', 'NO': 'Norveç', 'NZ': 'Yeni Zelanda', 'PE': 'Peru', 'PH': 'Filipinler', 'PL': 'Polonya',
    'PT': 'Portekiz', 'RO': 'Romanya', 'RS': 'Sırbistan', 'SE': 'İsveç', 'SG': 'Singapur', 'SI': 'Slovenya', 'SK': 'Slovakya',
    'TH': 'Tayland', 'TR': 'Türkiye', 'TW': 'Tayvan', 'UA': 'Ukrayna', 'AE': 'BAE', 'US': 'ABD', 'VN': 'Vietnam', 'ZA': 'Güney Afrika',
}
# Proton / Mullvad dosya adlarinda ulke kodu disinda gecen iki harfli parcalar
_NOT_COUNTRY = {'WG', 'VP', 'SC', 'TOR', 'P2P', 'FREE', 'IS'}


def country_name(code):
    return COUNTRIES.get((code or '').upper(), '')


def country_from_name(name):
    """Dosya adindan ulke kodu: 'NL-FREE#12', 'mullvad-de-fra-wg-001', 'wg-US-NY-5', 'ProtonVPN_JP-3'. Bulunamazsa ''."""
    stem = re.sub(r'\.conf(\.dpapi)?$', '', pathlib.Path(name).name, flags=re.I)
    tokens = [t for t in re.split(r'[^A-Za-z]+', stem) if t]
    for t in tokens:
        u = t.upper()
        if len(t) == 2 and u in COUNTRIES and u not in _NOT_COUNTRY:
            return 'GB' if u == 'UK' else u
    return ''


def tunnel_name(filename, taken=()):
    """WireGuard tunel adi: dosya adindan, en fazla 32 izinli karakter, cakismazsa ayni."""
    stem = re.sub(r'\.conf(\.dpapi)?$', '', pathlib.Path(filename).name, flags=re.I)
    base = re.sub(r'[^A-Za-z0-9_=+.\-]+', '-', stem).strip('-.') or 'tunel'
    base = base[:32]
    name, n = base, 2
    low = {t.lower() for t in taken}
    while name.lower() in low:
        suffix = '-%d' % n
        name = base[:32 - len(suffix)] + suffix
        n += 1
    return name


def parse_conf(text):
    """WireGuard .conf ozeti. Hata varsa ValueError. Ozel anahtarin kendisi dondurulmez."""
    sect, iface, peers = None, {}, []
    for raw in (text or '').splitlines():
        line = raw.split('#', 1)[0].strip() if not raw.strip().startswith('#') else ''
        if not line:
            continue
        m = re.match(r'^\[(\w+)\]$', line)
        if m:
            sect = m.group(1).lower()
            if sect == 'peer':
                peers.append({})
            continue
        if '=' not in line:
            raise ValueError('anlaşılmayan satır: %s' % line[:40])
        k, v = [x.strip() for x in line.split('=', 1)]
        (iface if sect == 'interface' else peers[-1] if sect == 'peer' and peers else {})[k.lower()] = v
    if not iface.get('privatekey'):
        raise ValueError('[Interface] PrivateKey yok')
    if not peers or not peers[0].get('publickey') or not peers[0].get('endpoint'):
        raise ValueError('[Peer] PublicKey / Endpoint yok')
    ep = peers[0]['endpoint']
    m = re.match(r'^\[?([^\]]+?)\]?:(\d+)$', ep)
    if not m:
        raise ValueError('Endpoint biçimi geçersiz: %s' % ep)
    allowed = [a.strip() for a in peers[0].get('allowedips', '').split(',') if a.strip()]
    return {'address': iface.get('address', ''), 'dns': iface.get('dns', ''), 'endpoint': ep, 'host': m.group(1), 'port': int(m.group(2)),
            'allowed': allowed, 'full_tunnel': any(a in ('0.0.0.0/0', '::/0') for a in allowed), 'peers': len(peers)}


def find_wireguard(env=None, exists=os.path.isfile):
    env = env or os.environ
    for base in (env.get('ProgramFiles', r'C:\Program Files'), env.get('ProgramW6432', ''), env.get('ProgramFiles(x86)', '')):
        if base:
            p = os.path.join(base, 'WireGuard', 'wireguard.exe')
            if exists(p):
                return p
    return None


def config_dir(wireguard_exe):
    return pathlib.Path(wireguard_exe).parent / 'Data' / 'Configurations'


def stored_config(cdir, name):
    """WireGuard yoneticisi .conf'u .conf.dpapi'ye cevirebilir; hangisi varsa."""
    for ext in ('.conf.dpapi', '.conf'):
        p = pathlib.Path(cdir) / (name + ext)
        if p.exists():
            return p
    return None


def install_cmd(wg, path):
    return [wg, '/installtunnelservice', str(path)]


def uninstall_cmd(wg, name):
    return [wg, '/uninstalltunnelservice', name]


def parse_ping_ms(lines):
    """ping ciktisindan ortalama ms (dil bagimsiz: son '= NNms'). Yanit yoksa None."""
    text = '\n'.join(lines or [])
    vals = re.findall(r'=\s*(\d+)\s*ms', text, re.I)
    if vals:
        return int(vals[-1])
    m = re.search(r'(?:time|süre)[=<]\s*(\d+(?:[.,]\d+)?)\s*ms', text, re.I)
    return int(float(m.group(1).replace(',', '.'))) if m else None


def ping_cmd(host, windows=True):
    return ['ping', '-n', '2', '-w', '1500', host] if windows else ['ping', '-c', '2', '-W', '2', host]


def parse_wg_dump(text):
    """'wg show <ad> dump' ciktisi: son el sikisma (unix sn) ve aktarim (bayt)."""
    rows = [l.split('\t') for l in (text or '').splitlines() if l.strip()]
    out = {'handshake': 0, 'rx': 0, 'tx': 0}
    for r in rows[1:]:
        if len(r) >= 7:
            try:
                out['handshake'] = max(out['handshake'], int(r[4]))
                out['rx'] += int(r[5])
                out['tx'] += int(r[6])
            except ValueError:
                pass
    return out


def human_bytes(n):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024 or unit == 'TB':
            return ('%d %s' % (n, unit)) if unit == 'B' else ('%.1f %s' % (n, unit))
        n /= 1024.0
    return ''


IP_CHECK_URL = 'https://ifconfig.co/json'


def parse_ipinfo(data):
    """ifconfig.co/json -> (ip, ulke kodu, ulke adi)."""
    import json
    d = json.loads(data) if isinstance(data, (str, bytes)) else data
    code = (d.get('country_iso') or d.get('country_code') or '').upper()
    return d.get('ip', ''), code, country_name(code) or d.get('country', '')
