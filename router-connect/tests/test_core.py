# -*- coding: utf-8 -*-
"""AGFO Router Connect - cekirdek testleri (Windows, ag ve Wi-Fi karti gerektirmez).

    python -I tests/test_core.py <router-connect klasoru>
"""
import ctypes
import os
import pathlib
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))
os.environ['APPDATA'] = tempfile.mkdtemp()
os.environ['LOCALAPPDATA'] = tempfile.mkdtemp()

import agfo_github_update as ghu  # noqa: E402
import router_core as core  # noqa: E402
import router_history as hist  # noqa: E402
import router_startup as startup  # noqa: E402
import router_store as rstore  # noqa: E402
import router_update as upd  # noqa: E402
import router_wifi as w  # noqa: E402

PASSED = []


def test(fn):
    fn()
    PASSED.append(fn.__name__)
    return fn


NETWORKS_EN = """
Interface name : Wi-Fi
There are 5 networks currently visible.

SSID 1 : Salon-Router
    Network type            : Infrastructure
    Authentication          : WPA2-Personal
    Encryption              : CCMP
    BSSID 1                 : aa:bb:cc:00:00:01
         Signal             : 78%
         Radio type         : 802.11ax
         Band               : 5 GHz
         Channel            : 36
         Basic rates (Mbps) : 6 12 24
         Other rates (Mbps) : 9 18 36 48 54
    BSSID 2                 : aa:bb:cc:00:00:02
         Signal             : 91%
         Radio type         : 802.11n
         Band               : 2.4 GHz
         Channel            : 6
         BSS Load:
             Connected Stations:  3
             Channel Utilization: 40 (15 %)

SSID 2 : Yatak-Odasi
    Network type            : Infrastructure
    BSSID 1                 : de:ad:be:ef:00:10
         Signal             : 45%
         Radio type         : 802.11ac
         Band               : 5 GHz
         Channel            : 100

SSID 3 :
    Network type            : Infrastructure
    BSSID 1                 : 11:22:33:44:55:66
         Signal             : 30%
         Channel            : 1

SSID 4 : Komsu
    BSSID 1                 : 77:88:99:aa:bb:cc
         Signal             : 12%
         Channel            : 11
"""

NETWORKS_TR = """
Arabirim adı : Wi-Fi
Şu anda 2 ağ görülebilir durumda.

SSID 1 : Çalışma Odası
    Ağ türü            : Altyapı
    Kimlik Doğrulama   : WPA2-Kişisel
    BSSID 1            : AA-BB-CC-00-00-0A
         Sinyal             : %67
         Radyo türü         : 802.11ax
         Bant               : 5 GHz
         Kanal              : 48

SSID 2 : Salon-Router
    BSSID 1            : aa:bb:cc:00:00:01
         Sinyal             : %83
         Bant               : 2,4 GHz
         Kanal              : 1
"""

INTERFACES_EN = """
There is 1 interface on the system:

    Name                   : Wi-Fi
    Description            : Intel(R) Wi-Fi 6 AX201 160MHz
    GUID                   : 6f1d8f20-3d1b-4c3b-9d0a-1f2e3d4c5b6a
    Physical address       : 00:11:22:33:44:55
    State                  : connected
    SSID                   : Salon-Router
    BSSID                  : aa:bb:cc:00:00:01
    Network type           : Infrastructure
    Radio type             : 802.11ax
    Authentication         : WPA2-Personal
    Channel                : 36
    Receive rate (Mbps)    : 866
    Signal                 : 78%
    Profile                : Salon-Router
"""

INTERFACES_TR_DISCONNECTED = """
Sistemde 1 arabirim var:

    Ad                     : Wi-Fi
    Açıklama               : Realtek 8822CE
    GUID                   : 11111111-2222-3333-4444-555555555555
    Fiziksel adres         : 00:11:22:33:44:66
    Durum                  : bağlantı kesildi
"""

PROFILES_EN = """
Profiles on interface Wi-Fi:

Group policy profiles (read only)
---------------------------------
    <None>

User profiles
-------------
    All User Profile     : Salon-Router
    All User Profile     : Yatak-Odasi
"""


@test
def parse_networks_en():
    n = w.parse_networks(NETWORKS_EN)
    assert [x['bssid'] for x in n] == ['aa:bb:cc:00:00:01', 'aa:bb:cc:00:00:02', 'de:ad:be:ef:00:10',
                                       '11:22:33:44:55:66', '77:88:99:aa:bb:cc'], n
    assert n[0]['ssid'] == 'Salon-Router' and n[0]['signal'] == 78 and n[0]['band'] == '5 GHz' and n[0]['channel'] == 36
    assert n[1]['signal'] == 91 and n[1]['band'] == '2.4 GHz' and n[1]['channel'] == 6   # BSS Load "%" signal'i bozmaz
    assert n[3]['ssid'] == ''                                                           # gizli ag listede kalir


@test
def parse_networks_turkish():
    n = w.parse_networks(NETWORKS_TR)
    assert len(n) == 2, n
    assert n[0]['ssid'] == 'Çalışma Odası' and n[0]['signal'] == 67 and n[0]['bssid'] == 'aa:bb:cc:00:00:0a'
    assert n[0]['band'] == '5 GHz' and n[0]['channel'] == 48
    assert n[1]['signal'] == 83 and n[1]['band'] == '2.4 GHz' and n[1]['channel'] == 1   # "2,4 GHz" -> 2.4 GHz


@test
def parse_interfaces():
    d = w.parse_interfaces(INTERFACES_EN)
    assert len(d) == 1
    x = d[0]
    assert (x['name'], x['ssid'], x['bssid'], x['signal'], x['connected']) == \
           ('Wi-Fi', 'Salon-Router', 'aa:bb:cc:00:00:01', 78, True), x
    assert x['guid'] == '6f1d8f20-3d1b-4c3b-9d0a-1f2e3d4c5b6a', x
    t = w.parse_interfaces(INTERFACES_TR_DISCONNECTED)
    assert len(t) == 1 and t[0]['connected'] is False and t[0]['ssid'] == '' and t[0]['name'] == 'Wi-Fi'
    assert t[0]['guid'] == '11111111-2222-3333-4444-555555555555'


@test
def parse_interfaces_windows11_24h2_ap_bssid():
    text = INTERFACES_EN.replace('    BSSID                  :', '    AP BSSID               :')
    x = w.parse_interfaces(text)[0]
    assert x['bssid'] == 'aa:bb:cc:00:00:01' and x['connected'] and x['ssid'] == 'Salon-Router', x
    hidden = INTERFACES_EN.replace('    BSSID                  : aa:bb:cc:00:00:01\n', '')
    y = w.parse_interfaces(hidden)[0]
    assert y['connected'] and y['bssid'] == ''      # konum izni yoksa BSSID gelmeyebilir; baglanti yine de bagli sayilir


@test
def parse_profiles():
    assert w.parse_profiles(PROFILES_EN) == ['Salon-Router', 'Yatak-Odasi']


@test
def mac_helpers():
    assert w.norm_mac('AA-BB-CC-00-00-0A') == 'aabbcc00000a'
    assert w.fmt_mac('AA-BB-CC-00-00-0A') == 'aa:bb:cc:00:00:0a'


NETS = w.parse_networks(NETWORKS_EN)
R_SALON = {'name': 'Salon', 'ssid': 'Salon-Router', 'bssid': ''}
R_YATAK = {'name': 'Yatak', 'ssid': 'Yatak-Odasi', 'bssid': ''}
ROUTERS = [R_SALON, R_YATAK]


@test
def rank_uses_strongest_bssid_per_ssid():
    r = w.rank(ROUTERS, NETS)
    assert [x['router']['name'] for x in r] == ['Salon', 'Yatak']
    assert r[0]['net']['signal'] == 91 and r[0]['net']['bssid'].endswith(':02')


@test
def rank_bssid_pinned():
    pinned = {'name': 'Salon-5G', 'ssid': 'Salon-Router', 'bssid': 'AA-BB-CC-00-00-01'}
    r = w.rank([pinned], NETS)
    assert len(r) == 1 and r[0]['net']['signal'] == 78
    assert w.rank([{'name': 'x', 'ssid': 'Yok', 'bssid': ''}], NETS) == []


def cur(ssid, bssid, sig):
    return {'name': 'Wi-Fi', 'guid': '', 'ssid': ssid, 'bssid': bssid, 'signal': sig, 'connected': bool(ssid)}


@test
def decide_connects_when_disconnected():
    d = w.decide(ROUTERS, NETS, cur('', '', None))
    assert d['action'] == 'connect' and d['target']['router'] is R_SALON


@test
def decide_leaves_other_networks_alone_unless_forced():
    other = cur('Telefon', 'aa:aa:aa:aa:aa:aa', 60)
    assert w.decide(ROUTERS, NETS, other)['reason'] == 'other_network'
    assert w.decide(ROUTERS, NETS, other, force=True)['action'] == 'connect'


@test
def decide_keeps_best_and_respects_margin():
    # Yatak'ta bagli (%45), Salon %91 -> fark 46 >= esik: gec
    d = w.decide(ROUTERS, NETS, cur('Yatak-Odasi', 'de:ad:be:ef:00:10', 45), margin=10)
    assert d['action'] == 'connect' and d['target']['router'] is R_SALON
    # Salon'da bagli ve en iyi: dokunma
    assert w.decide(ROUTERS, NETS, cur('Salon-Router', 'aa:bb:cc:00:00:02', 91))['action'] == 'keep'
    # Fark esigin altindaysa (gidip gelme onlemi) gecme; zorla ise gec
    near = cur('Yatak-Odasi', 'de:ad:be:ef:00:10', 85)
    d = w.decide(ROUTERS, NETS, near, margin=10)
    assert d['action'] == 'keep' and d['reason'] == 'within_margin'
    assert w.decide(ROUTERS, NETS, near, margin=10, force=True)['action'] == 'connect'


@test
def decide_none_when_no_router_visible():
    d = w.decide([{'name': 'x', 'ssid': 'Yok', 'bssid': ''}], NETS, cur('', '', None))
    assert d['action'] == 'none' and d['reason'] == 'no_router'


@test
def decide_with_pinned_same_ssid_routers():
    a = {'name': 'A', 'ssid': 'Ev', 'bssid': 'aa:aa:aa:aa:aa:01'}
    b = {'name': 'B', 'ssid': 'Ev', 'bssid': 'aa:aa:aa:aa:aa:02'}
    nets = [{'ssid': 'Ev', 'bssid': 'aa:aa:aa:aa:aa:01', 'signal': 40, 'band': '', 'channel': 1},
            {'ssid': 'Ev', 'bssid': 'aa:aa:aa:aa:aa:02', 'signal': 80, 'band': '', 'channel': 6}]
    d = w.decide([a, b], nets, cur('Ev', 'aa:aa:aa:aa:aa:01', 40))
    assert d['action'] == 'connect' and d['target']['router'] is b


class FakeRun:
    def __init__(self, replies):
        self.calls, self.replies = [], list(replies)

    def __call__(self, args):
        self.calls.append(list(args))
        return self.replies.pop(0) if self.replies else (0, '')


@test
def connect_via_netsh_verifies():
    run = FakeRun([(0, 'Connection request was completed successfully.')])
    iface = {'name': 'Wi-Fi', 'guid': ''}
    ok, msg = w.connect('Salon-Router', iface=iface, run=run, current_fn=lambda: cur('Salon-Router', 'aa:bb:cc:00:00:02', 90),
                        wait=1, sleep=lambda s: None)
    assert ok, msg
    assert run.calls == [['connect', 'name=Salon-Router', 'ssid=Salon-Router', 'interface=Wi-Fi']], run.calls


@test
def connect_reports_missing_profile():
    run = FakeRun([(1, 'There is no profile "X" assigned to the specified interface.\n')])
    ok, msg = w.connect('X', run=run, current_fn=lambda: None, wait=0, sleep=lambda s: None)
    assert not ok and 'profil' in msg.lower()


@test
def connect_pinned_then_verified():
    seen = []
    ok, msg = w.connect('Ev', 'aa:aa:aa:aa:aa:02', iface={'name': 'Wi-Fi', 'guid': 'g'}, run=FakeRun([]),
                        pin=lambda *a: seen.append(a) or True,
                        current_fn=lambda: cur('Ev', 'aa:aa:aa:aa:aa:02', 80), wait=1, sleep=lambda s: None)
    assert ok and seen == [('g', 'Ev', 'Ev', 'aa:aa:aa:aa:aa:02')], (ok, msg, seen)


@test
def connect_pinned_falls_back_to_netsh():
    run = FakeRun([(0, 'ok')])
    ok, msg = w.connect('Ev', 'aa:aa:aa:aa:aa:02', iface={'name': 'Wi-Fi', 'guid': 'g'}, run=run, pin=lambda *a: False,
                        current_fn=lambda: cur('Ev', 'aa:aa:aa:aa:aa:03', 70), wait=0, sleep=lambda s: None)
    assert run.calls and run.calls[0][0] == 'connect'      # SSID ile netsh denendi
    assert not ok                                           # istenen BSSID'ye baglanilamadigi icin dogrulama basarisiz


@test
def scan_requests_fresh_scan_and_parses():
    slept, asked = [], []
    nets, raw = w.scan(run=lambda a: (0, NETWORKS_EN), scan_request=lambda: asked.append(1) or True,
                       sleep=slept.append, wait=2.5)
    assert len(nets) == 5 and slept == [2.5] and asked
    slept.clear()
    w.scan(force=False, run=lambda a: (0, NETWORKS_EN), scan_request=lambda: True, sleep=slept.append)
    assert slept == []


@test
def decode_handles_oem_and_utf8():
    assert w.decode('Çalışma'.encode('utf-8')) == 'Çalışma'
    assert isinstance(w.decode(b'\xe7a\xfd\xfdma'), str)


@test
def wlan_structs_match_windows_layout():
    assert ctypes.sizeof(w.GUID) == 16
    assert ctypes.sizeof(w.DOT11_SSID) == 36
    assert ctypes.sizeof(w.WLAN_INTERFACE_INFO) == 16 + 256 * ctypes.sizeof(ctypes.c_wchar) + 4
    lst = w.build_bssid_list('AA-BB-CC-00-00-0A')
    assert ctypes.sizeof(w.DOT11_BSSID_LIST) == 20 and lst.Size == 20
    assert (lst.Type, lst.Revision, lst.uNumOfEntries) == (0x80, 1, 1)
    assert bytes(lst.BSSIDs) == bytes.fromhex('aabbcc00000a')
    g = w.guid_from_string('{6f1d8f20-3d1b-4c3b-9d0a-1f2e3d4c5b6a}')
    assert g.Data1 == 0x6f1d8f20 and g.Data2 == 0x3d1b and bytes(g.Data4) == bytes.fromhex('9d0a1f2e3d4c5b6a'.replace('-', ''))
    s = w.build_ssid('Salon')
    assert s.uSSIDLength == 5 and bytes(s.ucSSID[:5]) == b'Salon'
    for bad in ('zz', '', '12:34'):
        try:
            w.build_bssid_list(bad)
        except ValueError:
            continue
        raise AssertionError('gecersiz BSSID kabul edildi: ' + bad)
    if sys.platform != 'win32':
        assert w.request_scan() is False and w.connect_pinned('g', 'p', 's', 'aa:aa:aa:aa:aa:aa') is False


@test
def store_roundtrip_and_limits():
    p = pathlib.Path(tempfile.mkdtemp()) / 'config.json'
    s = rstore.Store(p)
    assert s.routers == [] and s.settings['auto'] is False
    r = s.add('Salon-Router', '', 'Salon')
    assert r and s.add('Salon-Router', '', 'baska') is None            # ayni kayit tekrar eklenmez
    assert s.add('Ev', 'AA-BB-CC-00-00-0A') and s.add('Ev', 'aa:bb:cc:00:00:0a') is None
    s.set('interval', 5)
    s.set('margin', 999)
    s.set('auto', True)
    s2 = rstore.Store(p)
    assert [x['name'] for x in s2.routers] == ['Salon', 'Ev'] and s2.routers[1]['bssid'] == 'AA-BB-CC-00-00-0A'
    assert s2.settings['interval'] == 30 and s2.settings['margin'] == 40 and s2.settings['auto'] is True
    s2.rename(s2.routers[0], '  Salon Router  ')
    assert rstore.Store(p).routers[0]['name'] == 'Salon Router'
    s2.remove(s2.routers[0])
    assert len(rstore.Store(p).routers) == 1
    p.write_text('{bozuk', encoding='utf-8')                            # bozuk dosya: .bak'tan kurtarilir
    assert len(rstore.Store(p).routers) == 2          # son kayittan onceki yedek (2 router) geri yuklenir


@test
def update_package_ready_and_prefix():
    asset = {'name': 'AGFO-Router-Connect-v1.0.1-Kurulum.zip', 'url': 'https://github.com/x', 'sha256': ''}
    assert upd.package_ready({'assets': []}, asset) is False
    assert upd.package_ready({'assets': [{'name': 'SHA256SUMS.txt', 'url': 'https://github.com/s'}]}, asset) is True
    assert upd.package_ready({}, dict(asset, sha256='ab' * 32)) is True
    import re
    assert re.fullmatch(upd.GH_ASSET, 'AGFO-Router-Connect-v1.0.1-Kurulum.zip')
    assert not re.fullmatch(upd.GH_ASSET, 'AGFO-Router-Connect.exe')
    assert upd.GH_PREFIX == 'router-connect-v' and core.VERSION.count('.') == 2


@test
def update_check_offers_newer_release():
    rel = {'tag_name': 'router-connect-v9.9.9', 'draft': False, 'prerelease': False, 'body': 'notlar',
           'assets': [{'name': 'AGFO-Router-Connect-v9.9.9-Kurulum.zip',
                       'browser_download_url': 'https://github.com/downtownck/agfo-windows-apps/releases/download/x/y.zip',
                       'digest': 'sha256:' + 'cd' * 32, 'size': 10}]}
    res = upd.check(force=True, releases=[rel])
    assert res['status'] == 'update' and res['version'] == '9.9.9', res
    assert upd.check(force=True, releases=[])['status'] in ('none', 'current')


@test
def update_extract_blocks_path_escape():
    d = pathlib.Path(tempfile.mkdtemp())
    good = d / 'good.zip'
    with zipfile.ZipFile(good, 'w') as z:
        z.writestr('AGFO-Router-Connect-v1.0.0/Derle-ve-Kur.cmd', '@echo off')
    folder = upd.extract(good)
    assert (folder / 'Derle-ve-Kur.cmd').exists()
    bad = d / 'bad.zip'
    with zipfile.ZipFile(bad, 'w') as z:
        z.writestr('../evil.txt', 'x')
    try:
        upd.extract(bad)
    except ghu.GHUpdateError:
        pass
    else:
        raise AssertionError('yol disina tasma engellenmedi')
    nocmd = d / 'nocmd.zip'
    with zipfile.ZipFile(nocmd, 'w') as z:
        z.writestr('a/readme.txt', 'x')
    try:
        upd.extract(nocmd)
    except ghu.GHUpdateError:
        pass
    else:
        raise AssertionError('Derle-ve-Kur.cmd yoklugu yakalanmadi')


@test
def update_runner_scrubs_pyinstaller_env_and_passes_update_flag():
    env = upd.scrub_env({'_PYI_APPLICATION_HOME_DIR': 'x', '_MEIPASS2': 'y', 'PATH': 'p'})
    assert '_PYI_APPLICATION_HOME_DIR' not in env and '_MEIPASS2' not in env and env['PATH'] == 'p'
    got = {}
    upd.run_installer(tempfile.mkdtemp(), popen=lambda cmd, **kw: got.update(cmd=cmd, kw=kw))
    assert got['cmd'][-1] == '/update' and got['cmd'][-2].endswith('Derle-ve-Kur.cmd')


@test
def startup_script_and_toggle():
    s = startup.create_script(r"C:\Users\x'y\AGFO-Router-Connect.exe")
    assert "--minimized" in s and "x''y" in s and 'Startup' in s
    try:
        startup.set_enabled(True, r'C:\yok\yok.exe')
    except OSError:
        pass
    else:
        raise AssertionError('olmayan EXE icin hata beklenirdi')
    lnk = startup.startup_dir() / startup.LNK_NAME
    lnk.parent.mkdir(parents=True, exist_ok=True)
    lnk.write_text('x')
    assert startup.is_enabled()
    startup.set_enabled(False, None)
    assert not startup.is_enabled()
    startup.set_enabled(False, None)         # olmayan kisayolu kaldirmak hata vermez


@test
def installer_files_are_consistent():
    for name in ('Derle-ve-Kur.cmd', 'Kaldir.cmd', 'Baslat.cmd', 'Sadece-Derle.cmd', 'packaging/build_local.ps1',
                 'packaging/python_runtime.ps1', 'assets/agfo-router.ico', 'app.pyw'):
        assert (ROOT / name).exists(), name
    for name in ('Derle-ve-Kur.cmd', 'Kaldir.cmd', 'Baslat.cmd', 'Sadece-Derle.cmd', 'packaging/build_local.ps1'):
        raw = (ROOT / name).read_bytes()
        assert all(b < 128 for b in raw), name + ' ASCII olmali (Windows kabuk iletileri yalnizca Ingilizce)'
    ps = (ROOT / 'packaging/build_local.ps1').read_text()
    for mod in ('router_app', 'router_core', 'router_update', 'router_wifi', 'router_store', 'router_startup',
                'router_history', 'router_selftest', 'agfo_github_update'):
        assert "'%s'" % mod in ps, mod + ' PyInstaller hidden-import listesinde yok'
    low = ' '.join(p.read_text(encoding='utf-8', errors='replace').lower() for p in ROOT.rglob('*')
                   if p.is_file() and p.suffix in ('.py', '.pyw', '.cmd', '.ps1', '.md'))
    assert ('stag' + 'ing') not in low


EVENTS_XML = """<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event"><System><EventID>8001</EventID>
<TimeCreated SystemTime="2026-11-20T18:30:15.1234567Z"/></System><EventData><Data Name="InterfaceGuid">{x}</Data>
<Data Name="ProfileName">Salon-Router</Data><Data Name="SSID">Salon-Router</Data></EventData></Event>
<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event"><System><EventID>8001</EventID>
<TimeCreated SystemTime="2026-11-18T07:00:00.000Z"/></System><EventData><Data Name="ProfileName">Kafe 2</Data>
<Data Name="SSID">Kafe</Data></EventData></Event>
<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event"><System><EventID>8001</EventID>
<TimeCreated SystemTime="2026-11-19T07:00:00Z"/></System><EventData><Data Name="SSID">Salon-Router</Data></EventData></Event>"""


@test
def history_parsers():
    import struct
    st = struct.pack('<8H', 2026, 11, 6, 20, 18, 30, 15, 0)
    assert hist.parse_systemtime(st) == __import__('datetime').datetime(2026, 11, 20, 18, 30, 15)
    assert hist.parse_systemtime(b'\x00' * 16) is None and hist.parse_systemtime(b'') is None
    ev = hist.parse_events(EVENTS_XML)
    assert [e['ssid'] for e in ev] == ['Salon-Router', 'Kafe', 'Salon-Router'] and ev[0]['time'] is not None
    assert hist.parse_events('bozuk <xml') == [] and hist.parse_events('') == []
    reg = hist.registry_entries(
        [{'guid': '{A}', 'name': 'Salon-Router 2', 'description': 'Salon-Router', 'nametype': 0x47, 'last': None},
         {'guid': '{B}', 'name': 'Ofis LAN', 'description': 'Ofis LAN', 'nametype': 6, 'last': None}],
        [{'guid': '{a}', 'gateway_mac': 'aa:bb:cc:00:00:09'}])
    assert reg == [{'ssid': 'Salon-Router', 'last': None, 'gateway_mac': 'aa:bb:cc:00:00:09'}], reg   # kablolu ag elenir
    assert hist.collect_events(run=lambda *a, **k: (_ for _ in ()).throw(OSError('x'))) == []


@test
def history_discover_finds_home_routers():
    import datetime as D
    reg = [{'ssid': 'Salon-Router', 'last': D.datetime(2026, 11, 21), 'gateway_mac': 'aa:bb:cc:00:00:09'},
           {'ssid': 'Kafe', 'last': D.datetime(2026, 10, 1), 'gateway_mac': ''}]
    ev = hist.parse_events(EVENTS_XML)
    nets = w.parse_networks(NETWORKS_EN) + [{'ssid': 'Bilinmeyen', 'bssid': 'aa:aa:aa:aa:aa:aa', 'signal': 99,
                                             'band': '', 'channel': 1}]
    res = hist.discover(['Salon-Router', 'Yatak-Odasi', 'Komsu'], reg, ev, nets)
    by = {r['ssid']: r for r in res}
    assert 'Bilinmeyen' not in by                                  # gecmiste hic baglanilmamis ag onerilmez
    assert by['Salon-Router']['suggest'] and by['Salon-Router']['signal'] == 91 and by['Salon-Router']['count'] == 2
    assert by['Salon-Router']['gw_match'] is True                  # ag gecidi MAC'i router ailesiyle eslesiyor
    assert by['Yatak-Odasi']['suggest'] and by['Yatak-Odasi']['saved'] and by['Yatak-Odasi']['count'] == 0
    assert by['Komsu']['visible'] and not by['Komsu']['suggest']   # cok zayif sinyal: otomatik eklenmez
    assert not by['Kafe']['visible'] and not by['Kafe']['suggest'] and not by['Kafe']['saved']
    assert [r['ssid'] for r in res][:2] == ['Salon-Router', 'Yatak-Odasi'] and res[-1]['ssid'] == 'Kafe'
    assert hist.discover([], [], [], nets) == []
    got = hist.gather(run_scan=lambda: (nets, ''), run_profiles=lambda: ['Yatak-Odasi'], reg=lambda: [], ev=lambda: [])
    assert [g['ssid'] for g in got] == ['Yatak-Odasi']


@test
def selftest_module_and_entry():
    out = pathlib.Path(tempfile.mkdtemp()) / 'st.txt'
    try:
        import tkinter  # noqa: F401
        have_tk = True
    except ImportError:
        have_tk = False
    import router_selftest as st
    code = st.run(['app.pyw', '--selftest', str(out)])
    text = out.read_text(encoding='utf-8')
    if have_tk:
        assert code == 0 and text.startswith('OK ' + core.VERSION), text
    else:
        assert code == 1 and text.startswith('FAIL'), text      # tkinter yoksa net hata (dosyaya yazilir)
    app = (ROOT / 'app.pyw').read_text(encoding='utf-8')
    assert "'--selftest' in sys.argv" in app and app.index('--selftest') < app.index('from router_app import main')


print('AGFO ROUTER CONNECT CORE OK: %d tests' % len(PASSED))
