# -*- coding: utf-8 -*-
"""AGFO Router Connect - Wi-Fi tarama ve baglanti katmani.

Tarama ve durum okuma `netsh wlan` ile yapilir. Cikti Windows diline gore cevrildigi icin ayristirma yalnizca dilden
bagimsiz isaretlere dayanir: "SSID n :", "BSSID n :", yuzde isareti, GHz, MAC ve GUID bicimleri.
Ayni adli birden cok router icin BSSID sabitleme Windows WLAN API'siyle (WlanConnect) yapilir; olmazsa SSID ile
netsh baglantisina dusulur. Yonetici yetkisi gerekmez.
"""
from __future__ import annotations

import ctypes
import os
import re
import subprocess
import sys
import time

CREATE_NO_WINDOW = 0x08000000
MAC = r'[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}'
GUID_RE = re.compile(r'([0-9A-Fa-f]{8}-(?:[0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12})')
LOCATION_HINT = ('Ağ listesi boş. Wi-Fi\'nin açık olduğundan ve Windows Ayarlar > Gizlilik ve güvenlik > Konum '
                 'bölümünde konum hizmetlerinin (ve masaüstü uygulamalarına izin) açık olduğundan emin olun.')


class WifiError(Exception):
    pass


def _percent(text):
    """"78%" (EN) ve "%78" (TR) bicimlerinden sayiyi okur; yoksa None."""
    m = re.search(r'(\d{1,3})\s*%', text) or re.search(r'%\s*(\d{1,3})', text)
    return min(100, int(m.group(1))) if m else None


def norm_mac(s) -> str:
    return re.sub(r'[^0-9a-f]', '', (s or '').lower())


def fmt_mac(s) -> str:
    h = norm_mac(s)
    return ':'.join(h[i:i + 2] for i in range(0, 12, 2)) if len(h) == 12 else (s or '')


# ------------------------------------------------------------------ netsh
def _oem_encoding() -> str:
    if sys.platform == 'win32':
        try:
            return 'cp%d' % ctypes.windll.kernel32.GetOEMCP()
        except Exception:
            pass
    return 'utf-8'


def decode(data: bytes) -> str:
    for enc in ('utf-8', _oem_encoding(), 'latin-1'):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode('utf-8', 'replace')


def _netsh() -> str:
    root = os.environ.get('SystemRoot')
    if root:
        p = os.path.join(root, 'System32', 'netsh.exe')
        if os.path.exists(p):
            return p
    return 'netsh'


def run_netsh(args, timeout=25, run=subprocess.run):
    """('wlan' alt komutu) -> (cikis kodu, metin)."""
    cmd = [_netsh(), 'wlan'] + [str(a) for a in args]
    try:
        p = run(cmd, capture_output=True, timeout=timeout,
                creationflags=CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
    except FileNotFoundError:
        raise WifiError('netsh bulunamadı (uygulama yalnızca Windows\'ta çalışır).')
    except subprocess.TimeoutExpired:
        raise WifiError('netsh zaman aşımına uğradı.')
    return p.returncode, decode(p.stdout or b'') + decode(p.stderr or b'')


# ------------------------------------------------------------------ parsers
def parse_networks(text: str) -> list:
    """`netsh wlan show networks mode=bssid` -> [{'ssid','bssid','signal','band','channel'}] (BSSID basina bir kayit)."""
    out, ssid, cur = [], '', None
    for line in text.splitlines():
        m = re.match(r'^\s*SSID\s+\d+\s*:\s*(.*?)\s*$', line)
        if m:
            ssid, cur = m.group(1), None
            continue
        m = re.match(r'^\s*BSSID\s+\d+\s*:\s*(%s)' % MAC, line)
        if m:
            cur = {'ssid': ssid, 'bssid': fmt_mac(m.group(1)), 'signal': None, 'band': '', 'channel': None}
            out.append(cur)
            continue
        if cur is None:
            continue
        if cur['signal'] is None:
            pct = _percent(line)
            if pct is not None:
                cur['signal'] = pct
                continue
        if not cur['band']:
            m = re.search(r'(\d(?:[.,]\d)?)\s*GHz', line, re.I)
            if m:
                cur['band'] = m.group(1).replace(',', '.') + ' GHz'
                continue
        if cur['channel'] is None and cur['signal'] is not None:
            m = re.match(r'^\s*[^:%]+:\s*(\d{1,3})\s*$', line)
            if m:
                cur['channel'] = int(m.group(1))
    return [n for n in out if n['signal'] is not None]


def parse_interfaces(text: str) -> list:
    """`netsh wlan show interfaces` -> [{'name','guid','ssid','bssid','signal','connected'}]."""
    res = []
    for chunk in re.split(r'\n\s*\n', text.replace('\r', '')):
        kv = []
        for line in chunk.splitlines():
            m = re.match(r'^\s{2,}([^:]+?)\s*:\s*(.*?)\s*$', line)
            if m:
                kv.append((m.group(1), m.group(2)))
        if len(kv) < 3:
            continue
        d = {'name': kv[0][1], 'guid': '', 'ssid': '', 'bssid': '', 'signal': None}
        for k, v in kv:
            if k.upper() == 'SSID':
                d['ssid'] = v
            elif k.upper().endswith('BSSID') and re.match(MAC, v):      # Windows 11 24H2: "AP BSSID"
                d['bssid'] = fmt_mac(v)
            elif d['signal'] is None and _percent(v) is not None:
                d['signal'] = _percent(v)
            elif not d['guid']:
                g = GUID_RE.search(v)
                if g and len(v) <= 40:
                    d['guid'] = g.group(1)
        d['connected'] = bool(d['ssid'])
        res.append(d)
    return res


def parse_profiles(text: str) -> list:
    names = []
    for line in text.splitlines():
        m = re.match(r'^\s+[^:]+:\s*(\S.*?)\s*$', line)
        if m:
            names.append(m.group(1))
    return names


# ------------------------------------------------------------------ WLAN API (ctypes)
class GUID(ctypes.Structure):
    _fields_ = [('Data1', ctypes.c_uint32), ('Data2', ctypes.c_uint16), ('Data3', ctypes.c_uint16),
                ('Data4', ctypes.c_ubyte * 8)]


class DOT11_SSID(ctypes.Structure):
    _fields_ = [('uSSIDLength', ctypes.c_uint32), ('ucSSID', ctypes.c_ubyte * 32)]


class WLAN_INTERFACE_INFO(ctypes.Structure):
    _fields_ = [('InterfaceGuid', GUID), ('strInterfaceDescription', ctypes.c_wchar * 256), ('isState', ctypes.c_uint32)]


class WLAN_INTERFACE_INFO_LIST(ctypes.Structure):
    _fields_ = [('dwNumberOfItems', ctypes.c_uint32), ('dwIndex', ctypes.c_uint32),
                ('InterfaceInfo', WLAN_INTERFACE_INFO * 1)]


class DOT11_BSSID_LIST(ctypes.Structure):
    _fields_ = [('Type', ctypes.c_ubyte), ('Revision', ctypes.c_ubyte), ('Size', ctypes.c_uint16),
                ('uNumOfEntries', ctypes.c_uint32), ('uTotalNumOfEntries', ctypes.c_uint32),
                ('BSSIDs', ctypes.c_ubyte * 6)]


class WLAN_CONNECTION_PARAMETERS(ctypes.Structure):
    _fields_ = [('wlanConnectionMode', ctypes.c_uint32), ('strProfile', ctypes.c_wchar_p),
                ('pDot11Ssid', ctypes.POINTER(DOT11_SSID)), ('pDesiredBssidList', ctypes.POINTER(DOT11_BSSID_LIST)),
                ('dot11BssType', ctypes.c_uint32), ('dwFlags', ctypes.c_uint32)]


def guid_from_string(s: str) -> GUID:
    h = s.strip('{}').replace('-', '')
    if len(h) != 32:
        raise ValueError('GUID biçimi geçersiz')
    g = GUID()
    g.Data1 = int(h[0:8], 16)
    g.Data2 = int(h[8:12], 16)
    g.Data3 = int(h[12:16], 16)
    for i in range(8):
        g.Data4[i] = int(h[16 + 2 * i:18 + 2 * i], 16)
    return g


def build_bssid_list(bssid: str) -> DOT11_BSSID_LIST:
    h = norm_mac(bssid)
    if len(h) != 12:
        raise ValueError('BSSID biçimi geçersiz')
    lst = DOT11_BSSID_LIST()
    lst.Type = 0x80          # NDIS_OBJECT_TYPE_DEFAULT
    lst.Revision = 1         # DOT11_BSSID_LIST_REVISION_1
    lst.Size = ctypes.sizeof(DOT11_BSSID_LIST)
    lst.uNumOfEntries = 1
    lst.uTotalNumOfEntries = 1
    for i in range(6):
        lst.BSSIDs[i] = int(h[2 * i:2 * i + 2], 16)
    return lst


def build_ssid(ssid: str) -> DOT11_SSID:
    raw = ssid.encode('utf-8')[:32]
    d = DOT11_SSID()
    d.uSSIDLength = len(raw)
    for i, b in enumerate(raw):
        d.ucSSID[i] = b
    return d


class _Wlan:
    """WlanOpenHandle ... WlanCloseHandle sarmalayicisi (yalniz Windows)."""

    def __enter__(self):
        if sys.platform != 'win32':
            raise WifiError('WLAN API yalnızca Windows\'ta var.')
        self.api = ctypes.WinDLL('wlanapi.dll')
        self.handle = ctypes.c_void_p()
        negotiated = ctypes.c_uint32()
        self.api.WlanOpenHandle.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32),
                                            ctypes.POINTER(ctypes.c_void_p)]
        rc = self.api.WlanOpenHandle(2, None, ctypes.byref(negotiated), ctypes.byref(self.handle))
        if rc:
            raise WifiError('WlanOpenHandle hata %d' % rc)
        return self

    def __exit__(self, *a):
        try:
            self.api.WlanCloseHandle(self.handle, None)
        except Exception:
            pass

    def interfaces(self):
        self.api.WlanEnumInterfaces.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                                ctypes.POINTER(ctypes.POINTER(WLAN_INTERFACE_INFO_LIST))]
        lst = ctypes.POINTER(WLAN_INTERFACE_INFO_LIST)()
        rc = self.api.WlanEnumInterfaces(self.handle, None, ctypes.byref(lst))
        if rc:
            raise WifiError('WlanEnumInterfaces hata %d' % rc)
        try:
            n = lst.contents.dwNumberOfItems
            base = ctypes.addressof(lst.contents.InterfaceInfo)
            size = ctypes.sizeof(WLAN_INTERFACE_INFO)
            # Bellek WlanFreeMemory ile serbest birakilacagi icin GUID'ler kopyalanir.
            return [GUID.from_buffer_copy(WLAN_INTERFACE_INFO.from_address(base + i * size).InterfaceGuid)
                    for i in range(n)]
        finally:
            self.api.WlanFreeMemory.argtypes = [ctypes.c_void_p]
            self.api.WlanFreeMemory(lst)


def request_scan() -> bool:
    """Tum Wi-Fi kartlarindan yeni tarama ister (en iyi cabayla; hata firlatmaz). Sonuc birkac saniye sonra hazir olur."""
    try:
        with _Wlan() as w:
            guids = w.interfaces()
            w.api.WlanScan.argtypes = [ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.c_void_p, ctypes.c_void_p,
                                       ctypes.c_void_p]
            ok = False
            for g in guids:
                ok = (w.api.WlanScan(w.handle, ctypes.byref(g), None, None, None) == 0) or ok
            return ok
    except Exception:
        return False


def connect_pinned(guid: str, profile: str, ssid: str, bssid: str) -> bool:
    """Belirli bir BSSID'ye (router'a) baglanmayi dener. Basarisizsa False doner, hata firlatmaz."""
    try:
        g = guid_from_string(guid)
        ssid_s, lst = build_ssid(ssid), build_bssid_list(bssid)
        params = WLAN_CONNECTION_PARAMETERS()
        params.wlanConnectionMode = 0              # wlan_connection_mode_profile
        params.strProfile = profile
        params.pDot11Ssid = ctypes.pointer(ssid_s)
        params.pDesiredBssidList = ctypes.pointer(lst)
        params.dot11BssType = 1                    # dot11_BSS_type_infrastructure
        params.dwFlags = 0
        with _Wlan() as w:
            w.api.WlanConnect.argtypes = [ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(WLAN_CONNECTION_PARAMETERS),
                                          ctypes.c_void_p]
            return w.api.WlanConnect(w.handle, ctypes.byref(g), ctypes.byref(params), None) == 0
    except Exception:
        return False


# ------------------------------------------------------------------ high level
def scan(force=True, wait=3.0, run=run_netsh, scan_request=request_scan, sleep=time.sleep):
    """Gorunen aglar: [{'ssid','bssid','signal','band','channel'}]. Gerekirse once taze tarama ister."""
    if force and scan_request():
        sleep(wait)
    rc, out = run(['show', 'networks', 'mode=bssid'])
    return parse_networks(out), out


def current(run=run_netsh):
    """Ilk Wi-Fi kartinin durumu (bagliysa bagli olan oncelikli); kart yoksa None."""
    rc, out = run(['show', 'interfaces'])
    ifs = parse_interfaces(out)
    for d in ifs:
        if d['connected']:
            return d
    return ifs[0] if ifs else None


def profiles(run=run_netsh) -> list:
    rc, out = run(['show', 'profiles'])
    return parse_profiles(out)


def connect(ssid, bssid='', iface=None, profile=None, run=run_netsh, pin=connect_pinned, current_fn=None,
            wait=12.0, sleep=time.sleep):
    """(ok, mesaj). BSSID verilmisse once sabitli baglanti, olmazsa SSID ile netsh. Sonucu dogrular."""
    current_fn = current_fn or (lambda: current(run))
    profile = profile or ssid
    note = ''

    def verified():
        end = time.time() + wait
        while True:
            c = current_fn()
            if c and c.get('connected') and c['ssid'] == ssid and (not bssid or norm_mac(c['bssid']) == norm_mac(bssid)):
                return True
            if time.time() >= end:
                return False
            sleep(1.0)

    if bssid and iface and iface.get('guid'):
        if pin(iface['guid'], profile, ssid, bssid):
            if verified():
                return True, 'Bağlandı (BSSID sabitlendi): %s' % fmt_mac(bssid)
            note = ' (BSSID sabitleme sonuç vermedi, SSID ile denendi)'
        else:
            note = ' (BSSID sabitleme kullanılamadı, SSID ile denendi)'
    args = ['connect', 'name=%s' % profile, 'ssid=%s' % ssid]
    if iface and iface.get('name'):
        args.append('interface=%s' % iface['name'])
    rc, out = run(args)
    if rc != 0:
        txt = out.strip().splitlines()[0] if out.strip() else 'netsh hata kodu %d' % rc
        return False, '%s — Bu ağın Windows\'ta kayıtlı profili olmalı (bir kez normal yoldan bağlanıp parolayı kaydedin).' % txt
    if verified():
        return True, 'Bağlandı: %s%s' % (ssid, note)
    return False, 'Bağlantı isteği gönderildi ama %s\'e bağlanılamadı (parola/sinyal?)%s' % (ssid, note)


# ------------------------------------------------------------------ router secimi (saf mantik)
def match_nets(router: dict, networks: list) -> list:
    out = []
    for n in networks:
        if n['ssid'] != router.get('ssid'):
            continue
        if router.get('bssid') and norm_mac(n['bssid']) != norm_mac(router['bssid']):
            continue
        out.append(n)
    return out


def rank(routers: list, networks: list) -> list:
    """Menzildeki router'lar, en guclu sinyalden zayife: [{'router','net'}]."""
    res = []
    for r in routers:
        m = match_nets(r, networks)
        if m:
            res.append({'router': r, 'net': max(m, key=lambda n: n['signal'])})
    res.sort(key=lambda x: -x['net']['signal'])
    return res


def current_router(routers: list, cur):
    if not cur or not cur.get('ssid'):
        return None
    for r in routers:
        if r.get('bssid') and r['ssid'] == cur['ssid'] and norm_mac(r['bssid']) == norm_mac(cur.get('bssid')):
            return r
    for r in routers:
        if not r.get('bssid') and r['ssid'] == cur['ssid']:
            return r
    return None


def decide(routers: list, networks: list, cur, margin=10, force=False) -> dict:
    """action: 'connect' | 'keep' | 'none'. Otomatik kipte (force=False) baska bir agdayken dokunulmaz,
    ve gecis icin sinyal farki en az `margin` puan olmalidir (gidip gelmeyi onler)."""
    ranked = rank(routers, networks)
    base = {'ranked': ranked, 'target': None, 'me': current_router(routers, cur)}
    if not ranked:
        return dict(base, action='none', reason='no_router')
    best = ranked[0]
    me = base['me']
    if me is None:
        if cur and cur.get('ssid') and not force:
            return dict(base, action='none', reason='other_network')
        return dict(base, action='connect', reason='not_on_router', target=best)
    if best['router'] == me:
        return dict(base, action='keep', reason='already_best')
    cur_sig = cur.get('signal')
    if cur_sig is None:
        mine = [x for x in ranked if x['router'] == me]
        cur_sig = mine[0]['net']['signal'] if mine else 0
    delta = best['net']['signal'] - cur_sig
    if (force and delta > 0) or delta >= max(1, margin):
        return dict(base, action='connect', reason='stronger', target=best, delta=delta)
    return dict(base, action='keep', reason='within_margin', delta=delta)
