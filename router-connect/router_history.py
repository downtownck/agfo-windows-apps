# -*- coding: utf-8 -*-
"""AGFO Router Connect - daha once baglanilan ag gecmisi (evdeki router'lari otomatik bulmak icin).

Uc kaynak birlestirilir (hicbiri yonetici yetkisi gerektirmez; okunamayan kaynak sessizce atlanir):
  1) Windows'ta kayitli Wi-Fi profilleri (`netsh wlan show profiles`)
  2) Ag listesi kaydi (HKLM\\...\\NetworkList): son baglanma zamani ve varsayilan ag gecidinin (router) MAC adresi
  3) WLAN-AutoConfig olay gunlugu: baglanma zaman cizelgesi (olay 8001)
"Ayni ev" olcutu: gecmiste baglanilmis olup su an menzilde gorunen aglar. Evde olmayan (kafe, is yeri) aglar
menzilde gorunmedigi icin onerilmez; listede yine de gri olarak gosterilir.
"""
from __future__ import annotations

import datetime as dt
import re
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

import router_wifi as wifi

NET_LIST = r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\NetworkList'
WLAN_LOG = 'Microsoft-Windows-WLAN-AutoConfig/Operational'
NAMETYPE_WIRELESS = 0x47
MIN_SIGNAL = 30          # bu degerin altindaki (zayif / komsu) aglar otomatik eklenmez


def parse_systemtime(raw):
    """Kayit defterindeki 16 baytlik SYSTEMTIME -> datetime (yerel saat); gecersizse None."""
    try:
        y, mo, _dow, d, h, mi, s, _ms = struct.unpack('<8H', bytes(raw)[:16])
        return dt.datetime(y, mo, d, h, mi, s)
    except (struct.error, ValueError, TypeError):
        return None


def registry_entries(profiles: list, signatures: list) -> list:
    """profiles: [{'guid','name','description','nametype','last','created'}], signatures: [{'guid','gateway_mac'}]
    -> [{'ssid','last','gateway_mac'}] (yalniz kablosuz profiller)."""
    gw = {s['guid'].lower(): s.get('gateway_mac', '') for s in signatures}
    out = []
    for p in profiles:
        if p.get('nametype') != NAMETYPE_WIRELESS:
            continue
        ssid = (p.get('description') or p.get('name') or '').strip()
        if ssid:
            out.append({'ssid': ssid, 'last': p.get('last'), 'gateway_mac': gw.get(p['guid'].lower(), '')})
    return out


def collect_registry() -> list:
    """HKLM NetworkList'ten kablosuz ag gecmisi; Windows disinda ya da hata durumunda []."""
    if sys.platform != 'win32':
        return []
    try:
        import winreg
        profiles, sigs = [], []

        def subkeys(path):
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as k:
                i = 0
                while True:
                    try:
                        yield winreg.EnumKey(k, i)
                    except OSError:
                        return
                    i += 1

        def value(path, name):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as k:
                    return winreg.QueryValueEx(k, name)[0]
            except OSError:
                return None

        for g in subkeys(NET_LIST + '\\Profiles'):
            p = NET_LIST + '\\Profiles\\' + g
            profiles.append({'guid': g, 'name': value(p, 'ProfileName'), 'description': value(p, 'Description'),
                             'nametype': value(p, 'NameType'), 'last': parse_systemtime(value(p, 'DateLastConnected') or b'')})
        for g in subkeys(NET_LIST + '\\Signatures\\Unmanaged'):
            p = NET_LIST + '\\Signatures\\Unmanaged\\' + g
            mac = value(p, 'DefaultGatewayMac')
            sigs.append({'guid': value(p, 'ProfileGuid') or '',
                         'gateway_mac': wifi.fmt_mac(bytes(mac).hex()) if mac else ''})
        return registry_entries(profiles, [s for s in sigs if s['guid']])
    except Exception:
        return []


def parse_events(xml_text: str) -> list:
    """`wevtutil qe ... /f:xml` ciktisi -> [{'ssid','profile','time'}] (olay 8001 = baglanti kuruldu)."""
    text = re.sub(r'\sxmlns="[^"]+"', '', xml_text or '')
    text = re.sub(r'<\?xml[^>]*\?>', '', text)
    try:
        root = ET.fromstring('<r>' + text + '</r>')
    except ET.ParseError:
        return []
    out = []
    for ev in root.iter('Event'):
        data = {d.get('Name'): (d.text or '') for d in ev.iter('Data')}
        ssid = (data.get('SSID') or data.get('ProfileName') or '').strip()
        tc = ev.find('./System/TimeCreated')
        when = None
        if tc is not None and tc.get('SystemTime'):
            try:
                s = tc.get('SystemTime').replace('Z', '+00:00')
                s = re.sub(r'(\.\d{6})\d+', r'\1', s)
                when = dt.datetime.fromisoformat(s).astimezone().replace(tzinfo=None)
            except ValueError:
                when = None
        if ssid:
            out.append({'ssid': ssid, 'profile': data.get('ProfileName', ssid), 'time': when})
    return out


def collect_events(limit=1000, run=subprocess.run) -> list:
    """WLAN-AutoConfig gunlugunden son baglantilar; okunamazsa (yetki/kapali gunluk) []."""
    if sys.platform != 'win32':
        return []
    try:
        p = run(['wevtutil', 'qe', WLAN_LOG, '/q:*[System[(EventID=8001)]]', '/c:%d' % limit, '/rd:true', '/f:xml'],
                capture_output=True, timeout=30, creationflags=wifi.CREATE_NO_WINDOW)
        if p.returncode:
            return []
        return parse_events(wifi.decode(p.stdout or b''))
    except Exception:
        return []


def discover(profiles: list, registry: list, events: list, nets: list, min_signal: int = MIN_SIGNAL) -> list:
    """Gecmiste baglanilan aglari menzil bilgisiyle birlestirir.

    Her kayit: ssid, saved, last, count, gateway_mac, signal, bssid, band, visible, gw_match, suggest.
    Sirali: onerilenler (guclu sinyal ustte), sonra menzildekiler, sonra gecmis aglar (son baglanma yeni ustte)."""
    by = {}

    def ent(ssid):
        return by.setdefault(ssid, {'ssid': ssid, 'saved': False, 'last': None, 'count': 0, 'gateway_mac': '',
                                    'signal': None, 'bssid': '', 'band': '', 'visible': False, 'gw_match': False,
                                    'suggest': False})

    def newer(a, b):
        return b if a is None or (b is not None and b > a) else a

    for name in profiles:
        if name:
            ent(name)['saved'] = True
    for r in registry:
        e = ent(r['ssid'])
        e['last'] = newer(e['last'], r.get('last'))
        e['gateway_mac'] = r.get('gateway_mac') or e['gateway_mac']
    for ev in events:
        e = ent(ev['ssid'])
        e['count'] += 1
        e['last'] = newer(e['last'], ev.get('time'))
    for n in nets:
        e = by.get(n['ssid'])
        if e and (e['signal'] is None or n['signal'] > e['signal']):
            e.update(signal=n['signal'], bssid=n['bssid'], band=n.get('band', ''), visible=True)
    for e in by.values():
        if e['visible'] and e['gateway_mac']:
            # Router'in WLAN BSSID'si ile ag gecidi MAC'i genellikle yalniz son baytta ayrilir
            e['gw_match'] = wifi.norm_mac(e['bssid'])[:10] == wifi.norm_mac(e['gateway_mac'])[:10]
        e['suggest'] = bool(e['visible'] and e['signal'] >= min_signal)
    far = dt.datetime.min
    return sorted(by.values(), key=lambda e: (not e['suggest'], not e['visible'], -(e['signal'] or 0),
                                              -(e['last'] or far).timestamp() if e['last'] else 0))


def gather(run_scan=None, run_profiles=None, reg=None, ev=None) -> list:
    """Tarar, gecmisi toplar, birlestirir (arka plan parcaciginda cagrilir)."""
    nets, _ = (run_scan or wifi.scan)()
    try:
        profs = (run_profiles or wifi.profiles)()
    except wifi.WifiError:
        profs = []
    return discover(profs, (reg or collect_registry)(), (ev or collect_events)(), nets)
