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


# --------------------------------------------------------------------------- VPN Gate (Tsukuba Universitesi, ucretsiz gonullu sunucular; OpenVPN)
VPNGATE_URL = 'https://www.vpngate.net/api/iphone/'
OVPN_PKG = 'OpenVPNTechnologies.OpenVPN'
# Internetten gelen yapilandirma yonetici yetkisiyle calisacagi icin komut/betik calistirabilen yonergeler atilir.
_OVPN_DROP = re.compile(r'^\s*(script-security|up|down|route-up|route-pre-down|ipchange|tls-verify|auth-user-pass-verify|client-connect|'
                        r'client-disconnect|learn-address|plugin|management\S*|log|log-append|status|writepid|cd|chroot|daemon|'
                        r'iproute|up-restart|setenv-safe|setenv|config|dhcp-pre-release|win-sys)(\s|$)', re.I)


def parse_vpngate(text):
    """VPN Gate CSV listesi -> sunucular (puan sirasina gore)."""
    import csv
    import io
    lines = [l for l in (text or '').splitlines() if l and not l.startswith('*')]
    if not lines or not lines[0].startswith('#'):
        raise ValueError('VPN Gate listesi tanınmadı')
    lines[0] = lines[0][1:]
    out = []
    for r in csv.DictReader(io.StringIO('\n'.join(lines))):
        try:
            cfg = (r.get('OpenVPN_ConfigData_Base64') or '').strip()
            if not cfg:
                continue
            cc = (r.get('CountryShort') or '').upper()
            out.append({'host': r.get('HostName', ''), 'ip': r.get('IP', ''), 'score': int(r.get('Score') or 0), 'ping': int(r.get('Ping') or 0),
                        'mbps': round(int(r.get('Speed') or 0) / 1e6, 1), 'cc': cc, 'country': country_name(cc) or r.get('CountryLong', ''),
                        'sessions': int(r.get('NumVpnSessions') or 0), 'uptime_days': round(int(r.get('Uptime') or 0) / 86400000.0, 1),
                        'operator': (r.get('Operator') or '').strip()[:60], 'config': cfg})
        except (ValueError, TypeError):
            continue
    out.sort(key=lambda s: -s['score'])
    return out


def vpngate_ovpn(b64):
    """Base64 yapilandirmayi cozer ve guvenli hale getirir. Donus: (metin, uzak sunucu). Gecersizse ValueError."""
    import base64
    try:
        text = base64.b64decode(b64).decode('utf-8', 'replace')
    except Exception:
        raise ValueError('yapılandırma çözülemedi')
    keep, remote, in_block = [], '', None
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r'^<(/?)([\w-]+)>$', s)
        if m:
            in_block = None if m.group(1) else m.group(2)
            keep.append(s)
            continue
        if in_block:                                         # <ca>, <cert>, <key> ... icerigi
            keep.append(line.rstrip())
            continue
        if not s or s.startswith(('#', ';')):
            continue
        if _OVPN_DROP.match(s):
            continue
        if s.lower().startswith('remote '):
            remote = remote or s.split()[1]
        if s.lower().split()[0] == 'auth-user-pass':
            keep.append('auth-user-pass {AUTH_FILE}')           # VPN Gate ortak kimligi (vpn/vpn) dosyadan verilir; istem acilmaz
            continue
        keep.append(s)
    if not remote or not any(l.strip().lower() == 'client' for l in keep):
        raise ValueError('istemci yapılandırması değil')
    return '\n'.join(keep) + '\n', remote


def finalize_ovpn(text, auth_file):
    """auth-user-pass yer tutucusunu gercek dosya yoluyla degistirir (OpenVPN yolunda ters bolu yerine / kullanilir)."""
    return text.replace('{AUTH_FILE}', '"%s"' % str(auth_file).replace('\\', '/'))


def find_openvpn(env=None, exists=os.path.isfile):
    env = env or os.environ
    for base in (env.get('ProgramFiles', r'C:\Program Files'), env.get('ProgramW6432', '')):
        if base:
            p = os.path.join(base, 'OpenVPN', 'bin', 'openvpn.exe')
            if exists(p):
                return p
    return None


def openvpn_cmd(exe, cfg, log):
    return [exe, '--config', str(cfg), '--log', str(log), '--verb', '3', '--auth-nocache', '--connect-retry-max', '2',
            '--data-ciphers', 'AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305:AES-128-CBC:AES-256-CBC']


def openvpn_state(log_text):
    t = log_text or ''
    ok = t.rfind('Initialization Sequence Completed')
    bad = max(t.rfind('AUTH_FAILED'), t.rfind('Exiting due to fatal error'), t.rfind('SIGTERM'))
    if bad > ok:
        return 'error'
    return 'connected' if ok >= 0 else 'connecting'
