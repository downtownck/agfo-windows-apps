"""AGFO System Care - care_core birim testleri (Windows gerektirmez).  python -I tests/test_core.py <agfo-care klasoru>"""
import json
import os
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))
import care_core as c  # noqa: E402

PASSED = []


def test(fn):
    fn()
    PASSED.append(fn.__name__)
    return fn


@test
def winget_table_en():
    out = ['   - ', '   \\ ', 'Name                         Id                        Version      Available    Source',
           '------------------------------------------------------------------------------------------',
           'Mozilla Firefox (x64 en-US)  Mozilla.Firefox           128.0        131.0.2      winget',
           'Notepad++                    Notepad++.Notepad++       8.6.4        8.7          winget',
           'Microsoft Visual C++ 2015-…  Microsoft.VCRedist.2015+… 14.38.33130  14.40.33810  winget',
           '3 upgrades available.']
    r = c.parse_winget_table(out)
    assert [x['id'] for x in r] == ['Mozilla.Firefox', 'Notepad++.Notepad++', 'Microsoft.VCRedist.2015+…'], r
    assert r[0]['version'] == '128.0' and r[0]['available'] == '131.0.2' and r[0]['source'] == 'winget'


@test
def winget_table_tr():
    out = ['Ad                Kimlik              Sürüm   Kullanılabilir Kaynak',
           '--------------------------------------------------------------------',
           '7-Zip 23.01 (x64) 7zip.7zip           23.01   24.08          winget',
           'VLC media player  VideoLAN.VLC        3.0.18  3.0.21         winget',
           '2 yükseltme kullanılabilir.']
    r = c.parse_winget_table(out)
    assert [x['id'] for x in r] == ['7zip.7zip', 'VideoLAN.VLC'], r
    assert r[1]['available'] == '3.0.21'


@test
def winget_table_empty():
    assert c.parse_winget_table(['No installed package found matching input criteria.']) == []


@test
def bleachbit_cleaners():
    lines = ['system.tmp', 'system.logs', 'system.free_disk_space', 'google_chrome.cache', 'google_chrome.passwords',
             'google_chrome.cookies', 'deep_scan.tmp', 'garbage line', 'firefox.cache', 'system.tmp']
    d = c.parse_bleachbit_cleaners(lines)
    assert d == {'system': ['tmp', 'logs', 'free_disk_space'], 'google_chrome': ['cache', 'passwords', 'cookies'],
                 'deep_scan': ['tmp'], 'firefox': ['cache']}, d
    assert c.bb_default_selected('system', 'tmp') and c.bb_default_selected('google_chrome', 'cache')
    for cl, op in [('system', 'free_disk_space'), ('google_chrome', 'passwords'), ('google_chrome', 'cookies'), ('deep_scan', 'tmp')]:
        assert not c.bb_default_selected(cl, op), (cl, op)
    assert c.bb_is_risky('google_chrome', 'passwords') and c.bb_is_risky('system', 'free_disk_space')
    assert c.bb_label('google_chrome') == 'Google Chrome' and c.bb_label('x_y') == 'X Y'


@test
def bleachbit_summary():
    s = c.parse_bleachbit_summary(['Delete 1kB C:\\a', '', 'Disk space to be recovered: 1.2GB', 'Files to be deleted: 345'])
    assert s == ['Delete 1kB C:\\a', 'Disk space to be recovered: 1.2GB', 'Files to be deleted: 345'][-3:] or 'Disk space to be recovered: 1.2GB' in s, s


@test
def split_and_exists():
    assert c.split_command('"C:\\Program Files\\App\\unins000.exe" /SILENT') == ('C:\\Program Files\\App\\unins000.exe', '/SILENT')
    assert c.split_command('C:\\Program Files\\App X\\uninstall.exe /S') == ('C:\\Program Files\\App X\\uninstall.exe', '/S')
    assert c.split_command('MsiExec.exe /X{11111111-2222-3333-4444-555555555555}')[0] == 'MsiExec.exe'
    assert c.uninstaller_exists('MsiExec.exe /X{x}', exists=lambda p: False)
    assert not c.uninstaller_exists('"C:\\gone\\u.exe"', exists=lambda p: False)
    assert c.uninstaller_exists('"C:\\here\\u.exe"', exists=lambda p: True)


@test
def program_values_and_uninstall():
    guid = '{11111111-2222-3333-4444-555555555555}'
    assert c.program_from_values({'DisplayName': 'KB123', 'ReleaseType': 'Update', 'UninstallString': 'x.exe'}, 'k') is None
    assert c.program_from_values({'DisplayName': 'Sys', 'SystemComponent': 1, 'UninstallString': 'x.exe'}, 'k') is None
    assert c.program_from_values({'DisplayName': 'NoUninst'}, 'k') is None
    m = c.program_from_values({'DisplayName': 'Tool', 'WindowsInstaller': 1, 'UninstallString': 'MsiExec.exe /I' + guid,
                               'InstallDate': '20260105', 'EstimatedSize': 2048}, guid)
    assert m['msi'] and m['product_code'] == guid and m['date'] == '2026-01-05' and m['size_kb'] == 2048
    assert c.build_uninstall(m, True) == ('msiexec.exe', '/x %s /passive /norestart' % guid)
    assert c.build_uninstall(m, False) == ('msiexec.exe', '/x %s /norestart' % guid)
    e = c.program_from_values({'DisplayName': 'App', 'UninstallString': '"C:\\A\\unins000.exe"', 'QuietUninstallString': '"C:\\A\\unins000.exe" /VERYSILENT'}, 'App_is1')
    assert c.build_uninstall(e, True) == ('C:\\A\\unins000.exe', '/VERYSILENT')
    assert c.build_uninstall(e, False) == ('C:\\A\\unins000.exe', '')
    c.annotate_programs([e, m], exists=lambda p: False)
    assert e['orphan'] and e['kind'] == 'Yetim kayıt' and not m['orphan'] and m['silent']
    assert c.human_size(2048) == '2.0 MB' and c.human_size(0) == ''


@test
def leftovers_safe():
    t = pathlib.Path(tempfile.mkdtemp())
    env = {'ProgramFiles': str(t / 'PF'), 'ProgramData': str(t / 'PD'), 'APPDATA': str(t / 'AD'), 'LOCALAPPDATA': str(t / 'LA')}
    for d in ['PF/Acme Tool', 'PF/Acme/Acme Tool', 'AD/Acme Tool', 'LA/Programs/Acme Tool', 'PF/Shared', 'PD', 'PF/Other App/Acme Tool']:
        (t / d).mkdir(parents=True, exist_ok=True)
    p = {'name': 'Acme Tool 2.1.0', 'publisher': 'Acme, Inc.', 'location': str(t / 'PF/Acme Tool')}
    remaining = [{'name': 'Other App', 'location': str(t / 'PF/Other App')}, {'name': 'Shared', 'location': ''}]
    got = c.leftover_candidates(p, remaining, env=env)
    exp = {os.path.normpath(str(t / d)) for d in ['PF/Acme Tool', 'PF/Acme/Acme Tool', 'AD/Acme Tool', 'LA/Programs/Acme Tool']}
    assert set(got) == exp, got
    # kok klasorler ve baska programin konumu asla onerilmez
    p2 = {'name': 'PD', 'publisher': '', 'location': str(t / 'PD')}
    assert str(t / 'PD') not in c.leftover_candidates(p2, [], env=env)
    p3 = {'name': 'Nested', 'publisher': '', 'location': str(t / 'PF/Other App')}
    assert c.leftover_candidates(p3, remaining, env=env) == []


@test
def bcu_export_merge():
    xml = ('<?xml version="1.0"?><Root xmlns="urn:x"><Items><ApplicationUninstallerEntry><DisplayName>Steam Game</DisplayName>'
           '<DisplayVersion>1.0</DisplayVersion><Publisher>Valve</Publisher><UninstallString>steam://uninstall/1</UninstallString>'
           '<UninstallerKind>Steam</UninstallerKind></ApplicationUninstallerEntry><ApplicationUninstallerEntry><DisplayName>Tool</DisplayName>'
           '<UninstallString>x</UninstallString><Publisher>p</Publisher></ApplicationUninstallerEntry></Items></Root>')
    rows = c.parse_bcu_export(xml)
    assert [r['DisplayName'] for r in rows] == ['Steam Game', 'Tool'], rows
    progs = [{'name': 'Tool', 'version': '', 'publisher': 'p', 'date': '', 'size_kb': 0, 'uninstall': 'x', 'quiet': '', 'location': '',
              'msi': False, 'product_code': '', 'hive': 'HKLM', 'view': 0, 'key': 'k', 'scope': 'Makine'}]
    assert c.merge_bcu_programs(progs, rows) == 1 and progs[0]['name'] == 'Steam Game' and progs[0]['scope'] == 'BCU: Steam'
    assert c.parse_bcu_export('not xml') == []


@test
def sdio_scripts():
    root = pathlib.Path('C:/ProgramData/AGFO/SDIO')
    s = c.sdio_script('scan', root=root)
    lines = [l for l in s.splitlines() if l and not l.startswith('#')]
    assert 'enableinstall off' in lines and not any(l.split()[0] == 'install' for l in lines), lines
    assert 'restorepoint' not in s and 'get indexes' in lines and lines.index('checkupdates') < lines.index('get indexes') < lines.index('init')
    i = c.sdio_script('install', {'missing', 'newer'}, ['lan'], root=root)
    il = [l for l in i.splitlines() if l and not l.startswith('#')]
    assert 'enableinstall on' in il and 'select missing newer lan' in il
    assert il.index([l for l in il if l.startswith('restorepoint')][0]) < il.index('select missing newer lan') < il.index('install')
    nodb = c.sdio_script('scan', update_db=False, root=root)
    assert 'checkupdates' not in nodb and 'get indexes' not in nodb
    allowed = {'logdir', 'drpdir', 'indexdir', 'extractdir', 'logging', 'verbose', 'enableinstall', 'checkupdates', 'onerror', 'get', 'init',
               'writedevicelist', 'snapshot', 'select', 'restorepoint', 'install', 'echo', 'end'}
    for l in il + lines:
        if l.startswith(':'):
            continue
        assert l.split()[0] in allowed, l   # yalnizca SDIO Reference Manual komutlari
    for bad in [lambda: c.sdio_script('install', set(), root=root), lambda: c.sdio_script('scan', root=pathlib.Path('C:/Users/A B/x'))]:
        try:
            bad()
            raise AssertionError('ValueError bekleniyordu')
        except ValueError:
            pass


@test
def winget_cmds():
    assert c.winget_install_cmd('w', 'BleachBit.BleachBit')[:4] == ['w', 'install', '--id', 'BleachBit.BleachBit']
    assert '--silent' in c.winget_install_cmd('w', 'x', upgrade=True) and c.winget_install_cmd('w', 'x', upgrade=True)[1] == 'upgrade'
    assert set(e['winget'] for e in c.ENGINES.values()) == {'BleachBit.BleachBit', 'Klocman.BulkCrapUninstaller', 'GlennDelahoy.SnappyDriverInstallerOrigin'}


@test
def engine_discovery_fs():
    t = pathlib.Path(tempfile.mkdtemp())
    pk = t / 'Microsoft' / 'WinGet' / 'Packages' / 'GlennDelahoy.SnappyDriverInstallerOrigin_Microsoft.Winget.Source_8wekyb3d8bbwe' / 'SDIO'
    pk.mkdir(parents=True)
    for n in ['SDIO_R888.exe', 'SDIO_x64_R888.exe', 'SDIO_x64_R746.exe']:
        (pk / n).write_text('x')
    old = os.environ.get('LOCALAPPDATA')
    os.environ['LOCALAPPDATA'] = str(t)
    try:
        assert os.path.basename(c.find_sdio({})) == 'SDIO_x64_R888.exe'
        assert c.find_sdio({'sdio_dir': str(t / 'none')}).endswith('SDIO_x64_R888.exe')
    finally:
        if old is None:
            os.environ.pop('LOCALAPPDATA')
        else:
            os.environ['LOCALAPPDATA'] = old



@test
def driver_compare_and_parse():
    assert c.parse_version('Intel - Net - 12.19.1.37') == '12.19.1.37'
    assert c.parse_version('Realtek Semiconductor Corp. - MEDIA - 6.0.9235.1') == '6.0.9235.1'
    assert c.parse_version('No version here') == ''
    assert c.compare_driver('12.19.1.37', '2024-01-01', '12.19.2.45', '2025-01-01') == 'newer'
    assert c.compare_driver('12.19.2.45', '', '12.19.2.45', '') == 'current'
    assert c.compare_driver('6.0.9300.1', '', '6.0.9235.1', '') == 'older'
    assert c.compare_driver('1.2', '', '1.2.0.1', '') == 'newer'         # uzunluk farki
    assert c.compare_driver('', '2020-01-01', '', '2021-05-05') == 'newer'  # surum yoksa tarih
    assert c.compare_driver('', '', '', '') == 'unknown'


@test
def driver_view():
    devs = [
        {'id': 'PCI\\NET1', 'name': 'Intel Ethernet', 'cls': 'Net', 'code': 0, 'hwids': ['PCI\\VEN_8086&DEV_15BC&SUBSYS_1', 'PCI\\VEN_8086&DEV_15BC'], 'compat': ['PCI\\CC_0200'],
         'ver': '12.19.1.37', 'date': '2024-01-01', 'provider': 'Intel'},
        {'id': 'PCI\\X', 'name': 'Bilinmeyen aygıt', 'cls': '', 'code': 28, 'hwids': ['PCI\\VEN_10EC&DEV_8168'], 'compat': [], 'ver': '', 'date': ''},
        {'id': 'USB\\OK', 'name': 'Mouse', 'cls': 'Mouse', 'code': 0, 'hwids': ['HID\\VID_1'], 'compat': [], 'ver': '10.0', 'date': '2006-06-21'},
        {'id': 'ACPI\\BAD', 'name': 'Sensor', 'cls': 'System', 'code': 43, 'hwids': ['ACPI\\S1'], 'compat': [], 'ver': '1.0', 'date': '2020-01-01'},
        {'id': 'USB\\OFF', 'name': 'Phone', 'cls': 'USB', 'code': 45, 'hwids': ['USB\\P'], 'compat': [], 'ver': '1', 'date': ''},
    ]
    wus = [
        {'id': 'u1', 'title': 'Intel - Net - 12.19.2.45', 'hwid': 'pci\\ven_8086&dev_15bc', 'date': '2025-01-01', 'sizeMB': 3},
        {'id': 'u2', 'title': 'Realtek - Net - 10.50.0.1', 'hwid': 'PCI\\VEN_10EC&DEV_8168', 'date': '2023-02-02'},
        {'id': 'u3', 'title': 'Intel - Net - 12.0.0.1', 'hwid': 'PCI\\VEN_8086&DEV_15BC', 'date': '2019-01-01'},
        {'id': 'u4', 'title': 'Generic - 1.0', 'hwid': 'PCI\\CC_0200', 'date': '2024-01-01'},   # yalnizca uyumlu kimlik
        {'id': 'u5', 'title': 'Orphan - 2.0', 'hwid': 'USB\\NOPE', 'date': ''},
    ]
    rows, unmatched, st = c.build_driver_view(devs, wus)
    by = {r['dev']['name']: r for r in rows}
    net = by['Intel Ethernet']
    assert [x['wu']['id'] for x in net['cands']] == ['u1', 'u3', 'u4'], [x['wu']['id'] for x in net['cands']]
    assert [x['status'] for x in net['cands']] == ['newer', 'older', 'worse'] and net['best'] == 'newer'   # HWID varken genel surucu 'daha zayif'
    assert not c.DRV_STATUS['worse'][2] and c.DRV_STATUS['newer'][2] and c.DRV_STATUS['missing'][2]
    unk = by['Bilinmeyen aygıt']
    assert unk['state'] == 'missing' and unk['cands'][0]['status'] == 'missing' and c.device_label(unk)[1] == 'st_missing'
    assert c.device_label(by['Sensor'])[0].startswith('Sorunlu: Aygıt sorun bildirdi')
    assert by['Phone']['state'] == 'ok' and c.device_label(by['Phone'])[1] == 'st_old'   # kod 45 sorun sayilmaz
    assert c.device_label(by['Mouse']) == ('Güncel', 'st_ok')
    assert [u['wu']['id'] for u in unmatched] == ['u5']
    assert st == {'devices': 5, 'updates': 2, 'missing': 1, 'problem': 1, 'candidates': 5}, st
    assert rows[0]['best'] in ('missing', 'newer') and rows[1]['best'] in ('missing', 'newer')   # guncellemeler en ustte
    # yalnizca uyumlu kimlikle eslesen aday da gorunur
    rows2, _, _ = c.build_driver_view([dict(devs[0], hwids=['X'])], [wus[3]])
    assert rows2[0]['cands'][0]['match'] == 'Uyumlu kimlik'


@test
def winget_codes():
    assert c.winget_code_text(-1978335215) == '0x8A150011 — kurulum dosyasının karması bildirimle uyuşmuyor'
    assert c.winget_code_text(0x8A15010C - 2 ** 32).endswith('kurulumu iptal ettiniz')
    assert c.winget_code_text(-1978334967) == '0x8A150109 — kurulumu bitirmek için yeniden başlatın'
    assert c.winget_code_text(5) == '5' and c.winget_code_text(-2147024891).startswith('0x80070005')


@test
def download_sources():
    assert c.host_allowed('https://download.bleachbit.org/get/x.zip', c.ALLOWED_HOSTS['bleachbit'])
    assert not c.host_allowed('http://download.bleachbit.org/x.zip', c.ALLOWED_HOSTS['bleachbit'])          # https zorunlu
    assert not c.host_allowed('https://evilbleachbit.org/x.zip', c.ALLOWED_HOSTS['bleachbit'])             # sonek hilesi
    assert not c.host_allowed('https://bleachbit.org.evil.com/x', c.ALLOWED_HOSTS['bleachbit'])
    assert c.host_allowed('https://objects.githubusercontent.com/a', c.ALLOWED_HOSTS['bcu'])
    html = ('<a href="https://download.bleachbit.org/get/BleachBit-6.0.4-setup.exe">x</a> '
            '<a href="https://download.bleachbit.org/get/BleachBit-6.0.4-portable.zip">p</a> beta: '
            '<a href="https://download.bleachbit.org/get/BleachBit-6.0.5-portable.zip">b</a>')
    # /get/ bir HTML 'indirme basliyor' sayfasidir; dosya /get/ olmadan dogrudan adrestedir (3.1.0 hatasi)
    assert c.bleachbit_portable_url(html) == ('6.0.4', 'https://download.bleachbit.org/BleachBit-6.0.4-portable.zip')  # ilk = kararli
    assert '/get/' not in c.bleachbit_portable_url(None)[1] and c.bleachbit_portable_url(None)[0] == c.BLEACHBIT_FALLBACK
    sums = ('c4cd6bb1f4b163dc28b13cef2995423de69e6776f16387f54943dcc6e7267a6d  BleachBit-6.0.4-setup.exe\n'
            '3425195570e4d191695c45537065dc007a51efd4fd675a47f7b6da6d686a4660  BleachBit-6.0.4-portable.zip\n')
    assert c.parse_sha256sums(sums, 'BleachBit-6.0.4-portable.zip') == c.BLEACHBIT_KNOWN_SHA256['6.0.4']
    assert c.parse_sha256sums(sums, 'nope.zip') is None and c.bleachbit_sums_url('6.0.4') == 'https://download.bleachbit.org/bleachbit-6.0.4-sha256sum.txt'
    rel = {'tag_name': 'v6.3', 'assets': [{'name': 'BCUninstaller_6.3_setup.exe', 'browser_download_url': 'https://github.com/a/s.exe'},
                                         {'name': 'BCUninstaller_6.3_portable.zip', 'browser_download_url': 'https://github.com/a/p.zip', 'digest': 'sha256:ab12'}]}
    assert c.bcu_portable_asset(rel) == ('6.3', 'https://github.com/a/p.zip', 'ab12')
    assert c.bcu_portable_asset({'assets': []}) is None
    page = '<a href="/downloads/sdio/SDIO_1.15.4.809.zip">old</a><a href="https://www.glenn.delahoy.com/downloads/sdio/SDIO_1.16.0.812.zip">new</a>'
    assert c.sdio_zip_url(page) == 'https://www.glenn.delahoy.com/downloads/sdio/SDIO_1.16.0.812.zip'
    assert c.sdio_zip_url('<a href="x.zip">') is None


@test
def safe_extract_and_portable_install():
    import zipfile
    t = pathlib.Path(tempfile.mkdtemp())
    bad = t / 'bad.zip'
    with zipfile.ZipFile(bad, 'w') as z:
        z.writestr('../evil.txt', 'x')
    try:
        c.safe_extract(bad, t / 'X', 'evil.txt'); raise AssertionError('zip-slip reddedilmeliydi')
    except OSError as e:
        assert 'Güvensiz' in str(e)
    assert not (t / 'evil.txt').exists()
    good = t / 'good.zip'
    with zipfile.ZipFile(good, 'w') as z:
        z.writestr('BleachBit-Portable/bleachbit_console.exe', 'exe'); z.writestr('BleachBit-Portable/BleachBit.ini', '[Portable]')
    path = c.safe_extract(good, t / 'BleachBit', 'bleachbit_console.exe')
    assert path.read_text() == 'exe' and not (t / 'BleachBit.new').exists()
    with zipfile.ZipFile(good, 'w') as z:
        z.writestr('BleachBit-Portable/bleachbit_console.exe', 'v2')
    assert c.safe_extract(good, t / 'BleachBit', 'bleachbit_console.exe').read_text() == 'v2'   # guncelleme yerinde
    try:
        c.safe_extract(good, t / 'Other', 'missing.exe'); raise AssertionError
    except OSError:
        assert not (t / 'Other').exists()
    # install_portable uctan uca (sahte sayfa + sahte indirme)
    old = c.ENGINE_DIR
    c.ENGINE_DIR = t / 'engines'
    said = []

    import hashlib, shutil
    good_sha = hashlib.sha256(good.read_bytes()).hexdigest()

    def fake_fetch(url, allowed, **k):
        assert c.host_allowed(url, allowed), url
        if url.endswith('sha256sum.txt'):
            return '%s  BleachBit-6.0.4-portable.zip\n' % good_sha
        return '<a href="https://download.bleachbit.org/get/BleachBit-6.0.4-portable.zip">p</a>'
    got = {}

    def fake_dl(url, dest, allowed, progress=None, should_stop=None, sha256=None):
        got['url'], got['sha'] = url, sha256
        shutil.copy(good, dest)
        return dest, good_sha
    try:
        p = c.install_portable('bleachbit', said.append, fetch=fake_fetch, dl=fake_dl)
        assert p.endswith('bleachbit_console.exe') and pathlib.Path(p).is_file(), p
        assert got == {'url': 'https://download.bleachbit.org/BleachBit-6.0.4-portable.zip', 'sha': good_sha}, got   # dogrudan adres + yayinci ozeti
        # sunucu ZIP yerine HTML dondururse acik hata
        def html_dl(url, dest, allowed, progress=None, should_stop=None, sha256=None):
            pathlib.Path(dest).write_text('<!DOCTYPE html><html>indirme basliyor</html>')
            return dest, 'x'
        try:
            c.install_portable('bleachbit', said.append, fetch=fake_fetch, dl=html_dl); raise AssertionError
        except OSError as e:
            assert 'web sayfası' in str(e), e
        # ozet alinamazsa ve surum bilinmiyorsa kurulmaz
        try:
            c.install_portable('bleachbit', said.append, fetch=lambda u, a, **k: (_ for _ in ()).throw(OSError('yok')) if u.endswith('.txt') else 'BleachBit-9.9.9-portable.zip', dl=fake_dl)
            raise AssertionError
        except OSError as e:
            assert 'doğrulanamayan' in str(e), e
        assert not list((t / 'engines').glob('_*.zip')), 'gecici zip silinmeli'
        assert any('6.0.4' in m for m in said)
    finally:
        c.ENGINE_DIR = old


@test
def download_verify():
    import hashlib, io
    data = b'A' * 700000
    good = hashlib.sha256(data).hexdigest()

    class Resp(io.BytesIO):
        def __init__(self, b, length=None):
            super().__init__(b); self.headers = {'Content-Length': str(length if length is not None else len(b))}
        def __enter__(self): return self
        def __exit__(self, *a): return False
    old = c._request
    t = pathlib.Path(tempfile.mkdtemp())
    seen = []
    try:
        c._request = lambda url, allowed, accept=None: Resp(data)
        dest, dg = c.download('https://download.bleachbit.org/x.zip', t / 'x.zip', c.ALLOWED_HOSTS['bleachbit'], progress=lambda d, n: seen.append((d, n)), sha256=good)
        assert dest.read_bytes() == data and dg == good and seen[-1] == (len(data), len(data))
        try:
            c.download('https://download.bleachbit.org/y.zip', t / 'y.zip', c.ALLOWED_HOSTS['bleachbit'], sha256='0' * 64); raise AssertionError
        except OSError as e:
            assert 'SHA-256' in str(e) and not (t / 'y.zip').exists() and not (t / 'y.zip.part').exists()
        c._request = lambda url, allowed, accept=None: Resp(b'', length=c.MAX_DOWNLOAD + 1)
        try:
            c.download('https://download.bleachbit.org/z.zip', t / 'z.zip', c.ALLOWED_HOSTS['bleachbit']); raise AssertionError
        except OSError as e:
            assert 'büyük' in str(e) and not (t / 'z.zip.part').exists()
    finally:
        c._request = old
    try:
        c.fetch_text('https://example.com/', c.ALLOWED_HOSTS['bleachbit']); raise AssertionError
    except OSError as e:
        assert 'İzin verilmeyen' in str(e)


@test
def registry_discovery():
    t = pathlib.Path(tempfile.mkdtemp())
    (t / 'BB').mkdir(); (t / 'BB' / 'bleachbit_console.exe').write_text('x'); (t / 'U').mkdir()
    progs = [{'name': 'BleachBit', 'location': '', 'uninstall': '"%s"' % (t / 'U' / 'uninstall.exe'), 'icon': '"%s",0' % (t / 'BB' / 'bleachbit.exe')},
             {'name': 'Not BleachBit', 'location': str(t / 'BB'), 'uninstall': '', 'icon': ''}]
    assert c.registry_install_dirs(r'^BleachBit', progs) == [str(t / 'U'), str(t / 'BB')]
    # html sha mismatch -> acik mesaj
    import io
    class R(io.BytesIO):
        headers = {'Content-Length': '30'}
        def __enter__(self): return self
        def __exit__(self, *a): return False
    old = c._request
    c._request = lambda url, allowed, accept=None: R(b'<!DOCTYPE html><html></html>  ')
    try:
        c.download('https://download.bleachbit.org/x.zip', t / 'x.zip', c.ALLOWED_HOSTS['bleachbit'], sha256='0' * 64); raise AssertionError
    except OSError as e:
        assert 'web sayfası' in str(e)
    finally:
        c._request = old


@test
def bloatware_catalog():
    cases = {'king.com.CandyCrushSaga': 'rec', 'Microsoft.BingNews': 'rec', 'Clipchamp.Clipchamp': 'rec', 'Microsoft.MicrosoftOfficeHub': 'rec',
             'Microsoft.549981C3F5F10': 'rec', 'Microsoft.ZuneMusic': 'caution', 'Microsoft.GamingApp': 'caution', 'Microsoft.Xbox.TCUI': 'caution',
             'Microsoft.YourPhone': 'caution', 'SpotifyAB.SpotifyMusic': 'caution', 'Microsoft.Windows.Photos': 'caution', 'Microsoft.Windows.DevHome': 'caution',
             'Microsoft.WindowsStore': 'protected', 'Microsoft.DesktopAppInstaller': 'protected', 'Microsoft.VCLibs.140.00.UWPDesktop': 'protected',
             'Microsoft.UI.Xaml.2.8': 'protected', 'Microsoft.SecHealthUI': 'protected', 'Microsoft.HEVCVideoExtension': 'protected',
             'Microsoft.Windows.ShellExperienceHost': 'protected', 'MicrosoftWindows.Client.WebExperience': 'protected', 'Microsoft.WindowsTerminal': 'protected',
             'RealtekSemiconductorCorp.RealtekAudioControl': 'protected', 'NVIDIACorp.NVIDIAControlPanel': 'protected', 'Contoso.SomeApp': 'other'}
    for n, exp in cases.items():
        assert c.classify_appx(n)[0] == exp, (n, c.classify_appx(n), exp)
    assert c.classify_win32('McAfee WebAdvisor')[0] == 'rec' and c.classify_win32('McAfee LiveSafe')[0] == 'rec'
    assert c.classify_win32('Norton 360')[0] == 'caution' and c.classify_win32('Microsoft 365 - tr-tr')[0] == 'caution'
    assert c.classify_win32('Notepad++') is None and c.classify_win32('Microsoft 365 Apps for enterprise - en-us') is None
    assert c.appx_publisher('CN=Microsoft Corporation, O=Microsoft Corporation, L=Redmond, S=Washington, C=US') == 'Microsoft Corporation'
    assert c.appx_publisher('CN=ADEE2BB7-1234') == 'ADEE2BB7-1234'
    appx = [{'name': 'king.com.CandyCrushSaga', 'full': 'k_1', 'sig': 'Store'}, {'name': 'Contoso.App', 'full': 'c_1', 'sig': 'Store'},
            {'name': 'Microsoft.BingWeather', 'full': 'w_1', 'sig': 'Store'}, {'name': 'Microsoft.WindowsStore', 'full': 's_1', 'sig': 'Store'},
            {'name': 'Foo.Locked', 'full': 'f_1', 'sig': 'Store', 'nonremovable': True}, {'name': 'Microsoft.Something', 'full': 'x_1', 'sig': 'System'}]
    progs = [{'name': 'McAfee WebAdvisor', 'publisher': 'McAfee', 'version': '4', 'orphan': False}, {'name': 'Notepad++', 'publisher': 'x', 'orphan': False},
             {'name': 'WildTangent Games', 'publisher': 'WT', 'orphan': True}]
    g = c.build_bloat_view(appx, progs)
    assert [i['name'] for i in g['rec']] == ['king.com.CandyCrushSaga', 'McAfee WebAdvisor'] and g['rec'][1]['kind'] == 'win32'
    assert [i['name'] for i in g['caution']] == ['Microsoft.BingWeather'] and [i['name'] for i in g['other']] == ['Contoso.App']
    assert {i['name'] for i in g['protected']} == {'Microsoft.WindowsStore', 'Foo.Locked', 'Microsoft.Something'}   # NonRemovable + System imzali


def _mkpkg(path, files, prefix='agfo-care/', manifest=True, version='9.9.0', tamper=None):
    import hashlib, zipfile
    files = dict(files)
    files.setdefault('care_core.py', "# AGFO System Care\nVERSION = '%s'\n" % version)
    files.setdefault('app.pyw', 'print("app %s")\n' % version)
    files.setdefault('care_tasks.ps1', "param()\n'ok'\n")
    with zipfile.ZipFile(path, 'w') as z:
        for rel, data in files.items():
            z.writestr(prefix + rel, data)
        z.writestr(prefix + 'tests/test_x.py', 'x')
        z.writestr(prefix + 'Baslat.cmd', 'x')
        if manifest:
            man = {'app': 'agfo-system-care', 'version': version,
                   'files': {r: hashlib.sha256(d.encode() if isinstance(d, str) else d).hexdigest() for r, d in files.items() if c._is_runtime_file(r)}}
            if tamper:
                man['files'][tamper] = '0' * 64
            z.writestr(prefix + 'MANIFEST.json', json.dumps(man))
    return path


@test
def update_inspect():
    t = pathlib.Path(tempfile.mkdtemp())
    ok = c.inspect_update(_mkpkg(t / 'ok.zip', {'assets/agfo.ico': 'ico', 'README_TR.md': 'r', 'new_module.py': 'X = 1\n'}), '3.3.0')
    assert ok['ok'] and ok['version'] == '9.9.0' and ok['manifest'] is True and not ok['downgrade'] and not ok['errors'], ok
    assert set(ok['files']) == {'app.pyw', 'care_core.py', 'care_tasks.ps1', 'assets/agfo.ico', 'README_TR.md', 'new_module.py'}, ok['files']  # tests/, .cmd haric
    flat = c.inspect_update(_mkpkg(t / 'flat.zip', {}, prefix=''), '3.3.0')
    assert flat['ok'] and flat['prefix'] == ''
    old = c.inspect_update(_mkpkg(t / 'old.zip', {}, version='3.1.0'), '3.3.0')
    assert old['ok'] and old['downgrade']
    nom = c.inspect_update(_mkpkg(t / 'nom.zip', {}, manifest=False), '3.3.0')
    assert nom['ok'] and nom['manifest'] is False and nom['warnings']
    bad = c.inspect_update(_mkpkg(t / 'tamper.zip', {}, tamper='app.pyw'), '3.3.0')
    assert not bad['ok'] and 'SHA-256' in bad['errors'][0]
    import zipfile
    with zipfile.ZipFile(t / 'slip.zip', 'w') as z:
        z.writestr('agfo-care/app.pyw', 'x'); z.writestr('../evil.py', 'x')
    assert not c.inspect_update(t / 'slip.zip', '1')['ok']
    with zipfile.ZipFile(t / 'other.zip', 'w') as z:
        z.writestr('x/readme.txt', 'x')
    assert 'app.pyw yok' in c.inspect_update(t / 'other.zip', '1')['errors'][0]
    with zipfile.ZipFile(t / 'miss.zip', 'w') as z:
        z.writestr('a/app.pyw', 'x'); z.writestr('a/care_core.py', "# AGFO System Care\nVERSION = '9'\n")
    assert 'care_tasks.ps1' in c.inspect_update(t / 'miss.zip', '1')['errors'][0]
    (t / 'junk.zip').write_text('not a zip')
    assert not c.inspect_update(t / 'junk.zip', '1')['ok']
    assert c.version_tuple('3.10.0') > c.version_tuple('3.9.9')


@test
def update_apply_and_rollback():
    t = pathlib.Path(tempfile.mkdtemp())
    inst = t / 'install'; (inst / 'assets').mkdir(parents=True)
    (inst / 'app.pyw').write_text('old app'); (inst / 'care_core.py').write_text("VERSION = '3.3.0'"); (inst / 'care_tasks.ps1').write_text('old ps')
    (inst / 'assets' / 'agfo.ico').write_text('old ico'); (inst / 'legacy.py').write_text('old module'); (inst / 'VERSION').write_text('3.3.0')
    (inst / '__pycache__').mkdir(); (inst / '__pycache__' / 'x.pyc').write_text('c')
    pkg = _mkpkg(t / 'u.zip', {'assets/agfo.ico': 'new ico', 'app.pyw': 'print(1)\n'})
    info = c.inspect_update(pkg, '3.3.0')
    stage = c.stage_update(pkg, info, t / 'stage')
    checks = c.preflight(stage, ps_parser=False)
    assert all(s != 'fail' for _, s, _ in checks) and any(n.startswith('Python derleme: app.pyw') for n, _, _ in checks), checks
    bk = t / 'backups'
    b1 = c.apply_update(stage, inst, bk, '3.3.0', '9.9.0')
    assert (inst / 'app.pyw').read_text() == 'print(1)\n' and (inst / 'assets' / 'agfo.ico').read_text() == 'new ico'
    assert (inst / 'VERSION').read_text() == '9.9.0' and not (inst / 'legacy.py').exists() and not (inst / '__pycache__').exists()
    assert not (inst / 'tests').exists() and not (inst / 'Baslat.cmd').exists()
    assert (pathlib.Path(b1) / 'legacy.py').read_text() == 'old module'
    bl = c.list_backups(bk)
    assert len(bl) == 1 and bl[0]['version'] == '3.3.0'
    # sozdizimi hatali paket on kontrolde yakalanir
    broken = _mkpkg(t / 'b.zip', {'app.pyw': 'def x(:\n'}, version='9.9.1')
    st2 = c.stage_update(broken, c.inspect_update(broken, '9.9.0'), t / 'stage2')
    assert any(s == 'fail' for _, s, _ in c.preflight(st2, ps_parser=False))
    # yarida kesilen kurulum otomatik geri alinir
    pkg3 = _mkpkg(t / 'u3.zip', {'app.pyw': 'print(3)\n', 'extra.py': 'E=1\n'}, version='9.9.2')
    st3 = c.stage_update(pkg3, c.inspect_update(pkg3, '9.9.0'), t / 'stage3')
    try:
        c.apply_update(st3, inst, bk, '9.9.0', '9.9.2', fail_after=2); raise AssertionError
    except OSError as e:
        assert 'geri yüklendi' in str(e)
    assert (inst / 'app.pyw').read_text() == 'print(1)\n' and not (inst / 'extra.py').exists() and (inst / 'VERSION').read_text() == '9.9.0'
    # surume geri donus (once mevcut surum yedeklenir)
    target, b2 = c.rollback_update(bl[0]['path'], inst, '9.9.0')
    assert target == '3.3.0' and (inst / 'app.pyw').read_text() == 'old app' and (inst / 'legacy.py').read_text() == 'old module'
    assert (inst / 'VERSION').read_text() == '3.3.0' and any(b['version'] == '9.9.0' for b in c.list_backups(bk))
    # en fazla 3 yedek tutulur
    for i in range(4):
        pk = _mkpkg(t / ('r%d.zip' % i), {}, version='9.9.%d' % (10 + i))
        s_ = c.stage_update(pk, c.inspect_update(pk, '3.3.0'), t / ('s%d' % i))
        import time as _t; _t.sleep(1.05)
        c.apply_update(s_, inst, bk, 'v%d' % i, '9.9.%d' % (10 + i))
    assert len(c.list_backups(bk)) == c.UPDATE_KEEP_BACKUPS
    man = c.build_manifest(inst)
    assert man['app'] == 'agfo-system-care' and 'app.pyw' in man['files'] and 'VERSION' not in man['files']


@test
def phantom_view():
    import datetime as dt
    today = dt.date(2026, 10, 17)
    devs = [{'id': 'USBSTOR\\DISK&VEN_SANDISK\\1', 'name': 'SanDisk USB', 'cls': 'DiskDrive', 'arrival': '2025-01-02 10:00', 'removal': '2025-01-03 11:00', 'regwrite': ''},
            {'id': 'USB\\VID_1&PID_2\\X', 'name': 'Telefon', 'cls': 'WPD', 'arrival': '', 'removal': '', 'regwrite': '2026-10-10 09:00'},
            {'id': 'SWD\\PRINTENUM\\{A}', 'name': 'Eski yazıcı', 'cls': 'PrintQueue', 'arrival': '2024-01-01 00:00', 'removal': '', 'regwrite': ''},
            {'id': 'ROOT\\LEGACY_X\\0000', 'name': 'Legacy', 'cls': 'LegacyDriver', 'arrival': '', 'removal': '', 'regwrite': ''},
            {'id': 'ACPI\\PNP0A08\\1', 'name': 'PCI Bus', 'cls': 'System', 'arrival': '2020-01-01 00:00', 'removal': '', 'regwrite': ''}]
    g, st = c.build_phantom_view(devs, today)
    flat = {d['name']: d for items in g.values() for d in items}
    assert flat['SanDisk USB']['seen'] == '2025-01-03 11:00' and flat['SanDisk USB']['age'] == 652 and flat['SanDisk USB']['default']
    assert flat['Telefon']['age'] == 7 and not flat['Telefon']['default']                 # 30 gunden yeni
    assert flat['Eski yazıcı']['caution'] and not flat['Eski yazıcı']['default']          # SWD\ yazilim aygiti
    assert flat['Legacy']['age'] is None and flat['Legacy']['caution']                   # ROOT\
    assert flat['PCI Bus']['caution'] and not flat['PCI Bus']['default']                 # System sinifi
    assert st == {'total': 5, 'old30': 3, 'old365': 3, 'caution': 3}, st
    assert list(g) == sorted(g, key=str.lower)
    g2, _ = c.build_phantom_view([{'id': 'USB\\F', 'cls': 'USB', 'regwrite': '2099-01-01 00:00'}], today)
    assert g2['USB'][0]['age'] == 0                                                      # gelecek tarih negatif olmaz

@test
def controller_detection():
    cases = [({'id': 'USB\\VID_045E&PID_0B12\\3039', 'name': 'Xbox Controller', 'cls': 'XnaComposite'}, True, 'usb'),
             ({'id': 'HID\\VID_045E&PID_0B12&IG_00\\7&1', 'name': 'HID-compliant game controller', 'cls': 'HIDClass'}, True, 'usb'),
             ({'id': 'BTHLEDEVICE\\{00001812-0000-1000-8000-00805F9B34FB}_DEV_VID&02045E_PID&0B13_REV&0509_F4F2\\8&1', 'name': 'Bluetooth LE', 'cls': 'HIDClass'}, True, 'bluetooth'),
             ({'id': 'HID\\{00001812-0000-1000-8000-00805F9B34FB}_DEV_VID&02045E_PID&0B13\\9&1', 'name': 'XINPUT device', 'cls': 'HIDClass'}, True, 'bluetooth'),
             ({'id': 'USB\\VID_045E&PID_02FE\\X1', 'name': 'Wireless Adapter', 'cls': 'Net'}, True, 'adapter'),
             ({'id': 'XBOXGIP\\7EED8A1B', 'name': 'Controller', 'cls': 'XboxComposite'}, True, 'adapter'),
             ({'id': 'HID\\VID_045E&PID_07A5&MI_00\\8&2', 'name': 'Microsoft Wireless Mouse', 'cls': 'Mouse'}, False, 'usb'),     # Microsoft fare: asla
             ({'id': 'USB\\VID_045E&PID_0745\\5&3', 'name': 'Microsoft Keyboard', 'cls': 'Keyboard'}, False, 'usb'),
             ({'id': 'USB\\VID_046D&PID_C52B\\6&4', 'name': 'Logitech Receiver', 'cls': 'USB'}, False, 'other'),
             ({'id': 'ROOT\\X\\0', 'name': 'Xbox Game Bar helper', 'cls': 'System'}, True, 'other')]                         # adinda Xbox
    for d, xb, bus in cases:
        assert c.controller_is_xbox(d) is xb, d
        assert c.controller_bus(d['id']) == bus, (d, c.controller_bus(d['id']))


@test
def controller_view_and_advice():
    devs = [{'id': 'USB\\VID_045E&PID_0B12\\1', 'name': 'Xbox Controller', 'cls': 'XnaComposite', 'status': 'OK', 'problem': 0},
            {'id': 'USB\\VID_045E&PID_0B12\\1', 'name': 'Xbox Controller', 'cls': 'XnaComposite', 'status': 'OK', 'problem': 0},       # yinelenen
            {'id': 'HID\\{00001812-0000-1000-8000-00805F9B34FB}_DEV_VID&02045E_PID&0B13\\2', 'name': 'BT input', 'cls': 'HIDClass', 'status': 'Error', 'problem': 10},
            {'id': 'HID\\VID_045E&PID_07A5\\3', 'name': 'Microsoft Mouse', 'cls': 'Mouse', 'status': 'OK', 'problem': 0}]
    rows, st = c.build_controller_view(devs)
    assert [r['name'] for r in rows] == ['BT input', 'Xbox Controller'], rows                     # sorunlu once
    assert st == {'total': 2, 'usb': 1, 'bluetooth': 1, 'adapter': 0, 'problem': 1}, st
    assert rows[0]['problem_dev'] and rows[0]['bus_text'] == 'Bluetooth' and not rows[1]['problem_dev']
    lv = lambda adv: [l for l, _ in adv]
    a = c.controller_advice({'total': 0}, True, [])
    assert lv(a)[0] == 'bad' and 'görünmüyor' in a[0][1] and a[-1][0] == 'info'
    a = c.controller_advice({'total': 1, 'bluetooth': 1, 'usb': 0}, True, [0], {'service': 'Stopped'})
    txt = ' '.join(x for _, x in a)
    assert 'Steam Input' in txt and 'bthserv' in txt and 'yuvası: 1' in txt, a
    a = c.controller_advice({'total': 2, 'usb': 1, 'bluetooth': 1, 'problem': 1}, True, [])
    txt = ' '.join(x for _, x in a)
    assert 'sürücüsünde sorun' in txt and 'USB kablo' in txt and 'Steam Input' not in txt and 'hiçbir XInput yuvasında' in txt, a
    a = c.controller_advice({'total': 1, 'adapter': 1}, False, [], fc_found=False)
    txt = ' '.join(x for _, x in a)
    assert 'Wireless Adapter' in txt and 'yalnızca Windows' in txt and 'FC ayar klasörü bulunamadı' in txt, a


@test
def xinput_helpers():
    assert c.xinput_pressed(0x1000 | 0x0100 | 0x0001) == ['DPAD_UP', 'LB', 'A']
    assert c.xinput_pressed(0) == []
    assert c.xinput_battery_text(1, 0) == 'Kablolu (USB)'
    assert c.xinput_battery_text(2, 1) == 'Alkalin pil · düşük'
    assert c.xinput_battery_text(0, 0) == 'Bağlı değil' and c.xinput_battery_text(7, 0) == 'Bilinmiyor'
    assert not c.stick_drift(3000, -3000) and c.stick_drift(9000, 0) and c.stick_drift(-6000, 6000)
    xr = c.XInputReader()
    if not c.IS_WIN:
        assert not xr.available() and xr.state(0) is None and xr.battery(0) is None and xr.connected_slots() == []


@test
def fc_settings_reset():
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        for name in ('EA SPORTS FC 9', 'EA SPORTS FC 27', 'EA SPORTS FC 26', 'Other'):
            (base / name).mkdir()
        (base / 'EA SPORTS FC 27' / 'settings').mkdir()
        assert [p.name for p in c.fc_settings_dirs(base)] == ['EA SPORTS FC 9', 'EA SPORTS FC 26', 'EA SPORTS FC 27']
        assert c.fc_settings_dirs(base / 'yok') == []
        fc = base / 'EA SPORTS FC 27'
        assert c.fc_reset_settings(fc) == (None, [])
        (fc / 'settings' / 'Settings_A').write_text('a1')
        (fc / 'settings' / 'settingsB').write_text('b22')
        (fc / 'settings' / 'buttonDataSetupV2.ini').write_text('keep')
        assert [f.name for f in c.fc_settings_files(fc)] == ['Settings_A', 'settingsB']
        bdir, names = c.fc_reset_settings(fc, stamp='20261018-2200')
        assert names == ['Settings_A', 'settingsB'] and bdir.name == 'settings_backup_20261018-2200'
        assert (bdir / 'Settings_A').read_text() == 'a1' and (bdir / 'settingsB').read_text() == 'b22'
        assert sorted(p.name for p in (fc / 'settings').iterdir()) == ['buttonDataSetupV2.ini']
        (fc / 'settings' / 'Settings_A').write_text('a2')
        bdir2, _ = c.fc_reset_settings(fc, stamp='20261018-2200')                                     # ayni saniye: ezmez
        assert bdir2.name == 'settings_backup_20261018-2200-2' and (bdir / 'Settings_A').read_text() == 'a1'


@test
def controller_contract():
    """PowerShell ValidateSet, uygulama eylem listeleri ve iki taraftaki Xbox olcutu (urun kimlikleri) uyumlu."""
    ps = (ROOT / 'care_tasks.ps1').read_text(encoding='utf-8')
    app = (ROOT / 'app.pyw').read_text(encoding='utf-8')
    for act in ('controller-list', 'controller-reset', 'bt-restart'):
        assert "'%s'" % act in ps.split('[string]$Action')[0] and (" '%s' {" % act) in ps, act
        assert "'%s'" % act in app.split('INTERNAL_PS_ACTIONS = ')[1].split('\n')[0], act
    adm = app.split('ADMIN_ACTIONS = ')[1].split('\n')[0]
    assert "'controller-reset'" in adm and "'bt-restart'" in adm and "'controller-list'" not in adm
    import re
    pids = set(re.search(r"\$pids='([0-9A-F|]+)'", ps).group(1).split('|'))
    assert pids == c.XBOX_PIDS | c.XBOX_ADAPTER_PIDS, pids ^ (c.XBOX_PIDS | c.XBOX_ADAPTER_PIDS)
    assert 'IsXboxDevice $dev' in ps.split(" 'controller-reset' {")[1].split(" 'bt-restart' {")[0]       # sifirlama Xbox olmayanı reddeder


# --------------------------------------------------------------------------- 3.7.0 ince ayarlar
import care_tweaks as tw  # noqa: E402
import care_catalog as cc  # noqa: E402


@test
def tweak_catalog_integrity():
    ids = [t['id'] for t in cc.TWEAKS] + [s['id'] for s in cc.SERVICES]
    assert len(ids) == len(set(ids)), 'yinelenen kimlik'
    cats = {k for k, _ in tw.CATEGORIES}
    for t in cc.TWEAKS:
        assert t['cat'] in cats and t['risk'] in tw.RISK_NAME and t['name'] and t['desc'], t['id']
        kinds = [k for k in ('reg', 'task', 'svc', 'power') if k in t]
        assert len(kinds) == 1, t['id']
        for r in t.get('reg', ()):
            assert r['hive'] in tw.VALID_HIVES and r['kind'] in tw.VALID_KINDS and not r['path'].startswith('\\'), (t['id'], r)
            assert 'on' in r and 'off' in r, t['id']
        for mode in ('apply', 'default'):
            assert not tw.validate_ops(tw.build_write_plan([dict(t, kind='tweak')], mode)), (t['id'], mode)
    for s in cc.SERVICES:
        assert s['start'] in tw.VALID_STARTS and s['risk'] in tw.RISK_NAME, s
    blocked = {s['svc'] for s in cc.SERVICES if s['risk'] == 'blocked'}
    assert {'RpcSs', 'DcomLaunch', 'WinDefend'} <= blocked
    known = set(ids)
    for p in cc.PRESETS:
        assert p['tweaks'] or p['services']
        assert set(p['tweaks']) | set(p['services']) <= known, p['id']
        assert not set(p['services']) & {s['id'] for s in cc.SERVICES if s['risk'] in ('blocked', 'danger')}, p['id']
    assert len({a['id'].lower() for a in cc.INSTALL_APPS}) == len(cc.INSTALL_APPS) and len(cc.INSTALL_APPS) > 100
    assert not any('bcdedit' in repr(t).lower() or 'netsh' in repr(t).lower() for t in cc.TWEAKS)   # serbest komutlar alinmadi


@test
def tweak_os_gate_and_admin():
    by = tw.item_by_id()
    cop = by['tweak-disable-copilot']
    assert tw.os_compatible(cop, 22631) and not tw.os_compatible(cop, 19045) and tw.os_compatible(cop, 0)
    assert tw.needs_admin_item(by['tweak-game-dvr']) and not tw.needs_admin_item(by['tweak-game-mode'])
    assert tw.needs_admin_item(by['svc-diagtrack']) and tw.needs_admin_item(by['tweak-task-ceip'])
    assert tw.preset_items('preset-gamer') and tw.preset_items('yok') == []


@test
def tweak_state_detection():
    by = tw.item_by_id()
    gm = by['tweak-game-mode']                                         # iki HKCU DWord, on=1
    plan = tw.read_plan([gm, by['svc-diagtrack'], by['tweak-task-ceip'], by['tweak-ultimate-perf']])
    refs = [p['ref'] for p in plan]
    assert len(refs) == len(set(refs)) and {p['t'] for p in plan} == {'reg', 'svc', 'task', 'power'}
    def rd(vals):
        out = [{'type': 'read', 'ref': p['ref'], 'key_exists': True, 'exists': v is not None, 'value': v} for p, v in zip([p for p in plan if p['t'] == 'reg'], vals)]
        return tw.reads_by_ref(out)
    assert tw.item_state(gm, rd(['1', '1'])) == 'applied'
    assert tw.item_state(gm, rd(['1', '0'])) == 'partial'
    assert tw.item_state(gm, rd([None, '0'])) == 'not'
    assert tw.item_state(gm, {}) == 'unknown'
    svc = by['svc-diagtrack']
    r = tw.reads_by_ref([{'type': 'read', 'ref': 'svc|diagtrack', 'exists': True, 'start': 'Disabled'}])
    assert tw.item_state(svc, r) == 'applied' and tw.current_text(svc, r) == 'Devre dışı'
    r = tw.reads_by_ref([{'type': 'read', 'ref': 'svc|diagtrack', 'exists': False, 'start': ''}])
    assert tw.item_state(svc, r) == 'missing'
    up = by['tweak-ultimate-perf']
    assert tw.item_state(up, {'power': {'active': 'E9A42B02-D5DF-448D-AA00-03F14749EB61'}}) == 'applied'
    assert tw.item_state(up, {'power': {'active': tw.BALANCED_PLAN}}) == 'not'
    nag = by['tweak-nagle-ack']                                        # tum alt anahtarlar
    key = [p for p in tw.read_plan([nag])][0]['ref']
    assert tw.item_state(nag, {key: {'subs': [{'exists': True, 'value': '1'}, {'exists': True, 'value': '1'}]}}) == 'applied'
    assert tw.item_state(nag, {key: {'subs': [{'exists': True, 'value': '1'}, {'exists': False}]}}) == 'not'
    assert tw.item_state(nag, {key: {'subs': []}}) == 'not'
    st = by['tweak-start-iris']                                        # optional + deleteValueOnEnable
    plan2 = tw.read_plan([st])
    reads = {}
    for p, r in zip(plan2, st['reg']):
        reads[p['ref']] = {'key_exists': True, 'exists': r['on'] is not None, 'value': r['on']}
    assert tw.item_state(st, reads) == 'applied'
    opt = [p['ref'] for p, r in zip(plan2, st['reg']) if r.get('optional')][0]
    reads[opt] = {'key_exists': True, 'exists': True, 'value': '1'}
    assert tw.item_state(st, reads) == 'applied'                        # istege bagli girdi durumu bozmaz


@test
def tweak_write_plan_and_undo():
    by = tw.item_by_id()
    items = [by['tweak-game-dvr'], by['tweak-classic-context-menu'], by['svc-diagtrack'], by['tweak-task-ceip'], by['tweak-ultimate-perf'], by['tweak-nagle-ack']]
    plan = tw.build_write_plan(items, 'apply')
    assert [o['ref'] for o in plan] == list(range(len(plan))) and not tw.validate_ops(plan)
    assert tw.needs_admin_ops(plan) and not tw.needs_admin_ops(tw.build_write_plan([by['tweak-game-mode']], 'apply'))
    dflt = tw.build_write_plan(items, 'default')
    cm = [o for o in dflt if o['item'] == 'tweak-classic-context-menu'][0]
    assert cm['delkey'].startswith('Software\\Classes\\CLSID\\{') and cm['value'] is None
    assert not [o for o in dflt if o['t'] == 'svc']                     # hizmetlerin katalog varsayilani yok
    assert [o['guid'] for o in dflt if o['t'] == 'power'] == [tw.BALANCED_PLAN]
    assert [o['enabled'] for o in dflt if o['t'] == 'task'] == [True] and [o['enabled'] for o in plan if o['t'] == 'task'] == [False]
    before = {}
    for o in plan:
        if o['t'] == 'reg' and o['item'] == 'tweak-game-dvr':
            before[o['ref']] = {'key_exists': False, 'exists': False, 'created_root': 'SOFTWARE\\Policies\\Microsoft\\Windows\\GameDVR'}
        elif o['t'] == 'reg' and o['item'] == 'tweak-classic-context-menu':
            before[o['ref']] = {'key_exists': False, 'exists': False, 'created_root': 'Software\\Classes\\CLSID\\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}'}
        elif o['t'] == 'reg':
            before[o['ref']] = {'subs': [{'path': o['path'] + '\\{A}', 'key_exists': True, 'exists': True, 'value': '2', 'kind': 'DWord'},
                                         {'path': o['path'] + '\\{B}', 'key_exists': True, 'exists': False}]}
        elif o['t'] == 'svc':
            before[o['ref']] = {'exists': True, 'start': 'AutomaticDelayed'}
        elif o['t'] == 'task':
            before[o['ref']] = {'exists': True, 'enabled': True}
        elif o['t'] == 'power':
            before[o['ref']] = {'active': tw.BALANCED_PLAN}
    records = [{'type': 'write', 'ref': o['ref'], 'ok': True, 'before': before[o['ref']]} for o in plan]
    records[-1]['ok'] = False                                           # basarisiz islem geri alinmaz
    with tempfile.TemporaryDirectory() as d:
        sess = tw.record_session(d, 'Uygula: test', plan, records + ['gurultu', {'type': 'read'}][1:])
        assert sess and len(tw.load_journal(d)) == 1 and 'Uygula: test' in tw.session_summary(sess)
        undo = tw.undo_ops(sess['entries'])
        assert not tw.validate_ops(undo), tw.validate_ops(undo)
        kinds = [o['t'] for o in undo]
        assert kinds[0] == 'power' and kinds.count('reg') >= 2           # ters sira
        dvr = [o for o in undo if o['t'] == 'reg' and 'GameDVR' in o['path']][0]
        assert dvr['value'] is None and dvr['prune'] == 'SOFTWARE\\Policies\\Microsoft\\Windows\\GameDVR' and dvr['item'] == 'tweak-game-dvr'
        assert [o['start'] for o in undo if o['t'] == 'svc'] == ['AutomaticDelayed']
        assert [o['enabled'] for o in undo if o['t'] == 'task'] == [True]
        assert not [o for o in undo if 'Interfaces' in o.get('path', '')]   # basarisiz alt-anahtar islemi atlandi
        records[-1]['ok'] = True
        sess2 = tw.record_session(d, 'ikinci', plan, records)
        sub = [o for o in tw.undo_ops(sess2['entries']) if 'Interfaces' in o.get('path', '')]
        assert {(o['path'][-3:], o['value']) for o in sub} == {('{A}', '2'), ('{B}', None)}, sub
        assert sess2['id'] != sess['id'] and len(tw.load_journal(d)) == 2
        tw.mark_undone(d, sess['id'])
        assert tw.load_journal(d)[0]['undone'] is True
        assert tw.record_session(d, 'hepsi hata', plan, [dict(r, ok=False) for r in records]) is None
    # varsayilana donus (silme) oncesi deger yoksa geri alma bos; deger varsa yazilir
    op = {'t': 'reg', 'hive': 'HKCU', 'path': 'Software\\X', 'name': 'V', 'kind': 'DWord', 'value': None}
    assert tw.undo_ops([{'op': op, 'ok': True, 'before': {'key_exists': True, 'exists': False}}]) == []
    assert tw.undo_ops([{'op': op, 'ok': True, 'before': {'key_exists': False, 'exists': False}}]) == []
    u = tw.undo_ops([{'op': op, 'ok': True, 'before': {'key_exists': True, 'exists': True, 'value': 'abc', 'kind': 'String'}}])
    assert u[0]['value'] == 'abc' and u[0]['kind'] == 'String'


@test
def tweak_validate_rejects():
    bad = [{'t': 'reg', 'hive': 'HKCR', 'path': 'x', 'name': 'a', 'kind': 'DWord', 'value': '1'},
           {'t': 'reg', 'hive': 'HKLM', 'path': '..\\x', 'name': 'a', 'kind': 'DWord', 'value': '1'},
           {'t': 'reg', 'hive': 'HKLM', 'path': 'SOFTWARE\\X', 'name': 'a', 'kind': 'Weird', 'value': '1'},
           {'t': 'reg', 'hive': 'HKCU', 'path': 'Software\\X', 'name': '', 'value': None, 'delkey': 'Software\\Microsoft'},
           {'t': 'reg', 'hive': 'HKCU', 'path': 'Software\\X\\Y', 'name': 'a', 'value': None, 'prune': 'Software\\Z'},
           {'t': 'svc', 'name': 'a b', 'start': 'Manual'}, {'t': 'svc', 'name': 'DiagTrack', 'start': 'Boot'},
           {'t': 'task', 'path': '\\Other\\T', 'enabled': False}, {'t': 'power', 'guid': 'nope'},
           {'t': 'dns', 'alias': 'Ethernet', 'servers': ['1.1.1.999']}, {'t': 'cmd', 'line': 'format c:'}]
    for b in bad:
        assert tw.validate_ops([b]), b
    assert tw.valid_ipv4_list('1.1.1.1, 8.8.8.8') == ['1.1.1.1', '8.8.8.8']
    assert tw.valid_ipv4_list('1.1.1.1;300.1.1.1') is None and tw.valid_ipv4_list('') is None and tw.valid_ipv4_list('1.1.1.1 ' * 5) is None
    p = tw.dns_plan([{'alias': 'Ethernet', 'guid': '{G}'}, {'alias': 'Wi-Fi'}], ['1.1.1.1'])
    assert [o['ref'] for o in p] == [0, 1] and not tw.validate_ops(p) and tw.needs_admin_ops(p)
    u = tw.undo_ops([{'op': p[0], 'ok': True, 'before': {'servers': []}}])
    assert u == [{'t': 'dns', 'alias': 'Ethernet', 'guid': '{G}', 'servers': [], 'item': 'dns', 'label': 'Geri al: DNS: Ethernet', 'ref': 0}], u


@test
def tweak_profiles_and_install():
    prof = tw.export_profile(['tweak-game-mode', 'svc-diagtrack', 'yok'])
    assert prof['items'] == ['tweak-game-mode', 'svc-diagtrack']
    assert tw.import_profile(json.loads(json.dumps(prof))) == (['tweak-game-mode', 'svc-diagtrack'], [])
    ids, unk = tw.import_profile({'tweakIds': ['tweak-game-mode', 'tweak-disable-hpet'], 'serviceIds': ['svc-sysmain']})   # WinCleaner profili
    assert ids == ['tweak-game-mode', 'svc-sysmain'] and unk == ['tweak-disable-hpet']
    for bad in ([], {'x': 1}):
        try:
            tw.import_profile(bad)
            raise AssertionError('kabul edilmemeliydi')
        except ValueError:
            pass
    rows = c.parse_winget_table(['Name               Id                         Version  Source',
                                 '------------------------------------------------------------',
                                 'Google Chrome      Google.Chrome              131.0    winget',
                                 'Microsoft Visual…  Microsoft.VisualStudioCo…  1.95     winget'])
    ids = tw.installed_ids(rows)
    assert tw.is_installed('Google.Chrome', ids) and tw.is_installed('Microsoft.VisualStudioCode', ids) and not tw.is_installed('Mozilla.Firefox', ids)
    g = tw.install_groups()
    assert sum(len(v) for v in g.values()) == len(cc.INSTALL_APPS) and 'Tarayıcılar' in g


@test
def tweak_contract_and_packaging():
    ps = (ROOT / 'care_tasks.ps1').read_text(encoding='utf-8')
    app = (ROOT / 'app.pyw').read_text(encoding='utf-8')
    head = ps.split('[string]$Action')[0]
    for act in ('tweak-read', 'tweak-write', 'dns-list', 'dns-flush', 'explorer-restart'):
        assert "'%s'" % act in head and (" '%s' {" % act) in ps, act
        assert "'%s'" % act in app.split('INTERNAL_PS_ACTIONS = ')[1].split('\n')[0], act
    assert '[string]$PlanFile' in ps and 'RequireAdmin' in ps.split(" 'tweak-write' {")[1].split(" 'dns-list' {")[0]
    assert "StartsWith('Software\\Classes\\CLSID\\{'" in ps and "StartsWith('\\Microsoft\\Windows\\')" in ps    # PS tarafi da sinirlar
    assert 'RegistryView]::Registry64' in ps
    for name in ('care_tweaks.py', 'care_catalog.py'):
        assert c._is_runtime_file(name), name
    man = c.build_manifest(ROOT)
    assert 'care_tweaks.py' in man['files'] and 'care_catalog.py' in man['files'] and man['version'] == c.VERSION
    inst = (ROOT / 'packaging' / 'install_windows.ps1').read_text(encoding='utf-8')
    assert "'care_tweaks.py'" in inst and "'care_catalog.py'" in inst and c.VERSION not in inst.split('$files=')[0]
    assert "('İnce ayarlar', self._tab_tweaks)" in app and "('Uygulama kur', self._tab_install)" in app


# --------------------------------------------------------------------------- 3.8.0 temalar, sol menu, dosya duzeni
import care_theme as th  # noqa: E402


@test
def theme_palettes_and_contrast():
    keys = th.theme_keys()
    assert len(keys) == len(set(keys)) >= 10 and th.DEFAULT in keys and keys[0] == th.DEFAULT
    labels = [t['label'] for t in th.THEMES]
    assert len(labels) == len(set(labels))
    for t in th.THEMES:
        assert set(t['colors']) == set(th.COLOR_KEYS) and t['type'] in ('dark', 'light'), t['key']
        tok = th.tokens(t['key'])
        assert th.contrast(tok['FG'], tok['PANEL']) >= 4.5, t['key']
        assert th.contrast(tok['MUTED'], tok['PANEL']) >= 4.4, (t['key'], tok['MUTED'])
        assert th.contrast(tok['NAV_FG'], tok['NAV_BG']) >= 4.4, t['key']
        for k in ('WARN', 'OK_C', 'BAD_C', 'ACCENT'):
            assert th.contrast(tok[k], tok['PANEL']) >= 2.9, (t['key'], k)
        for k in ('BTN', 'BTN_GO', 'BTN_DANGER'):
            assert th.contrast(tok[k + '_FG'], tok[k]) >= 2.5, (t['key'], k)
        colors = [v for v in tok.values() if isinstance(v, str) and v.startswith('#')]
        assert len(colors) == len(set(colors)), t['key']                 # tema degisiminde jeton geri bulunabilsin
        assert tok['DARK'] == (t['type'] == 'dark')
    assert th.label_to_key('Nord Koyu') == 'nord-dark' and th.label_to_key('yok') == th.DEFAULT
    assert th.theme_by_key('yok')['key'] == th.DEFAULT
    assert th.tb_name('agfo-gece') == 'agfo-gece' and th.tb_name('nord-dark') == 'agfo-nord-dark'
    assert th.ensure_contrast('#777777', '#ffffff', 4.5) != '#777777' and th.contrast(th.ensure_contrast('#777777', '#ffffff', 4.5), '#ffffff') >= 4.5
    assert th.mix('#000000', '#ffffff', 0.5) in ('#808080', '#7f7f7f')


@test
def theme_loader_and_pip():
    import types
    assert th.python_ok((3, 10)) and not th.python_ok((3, 9))
    mod, state = th.load_ttkbootstrap('/yok', enabled=False)
    assert mod is None and 'kapalı' in state
    with tempfile.TemporaryDirectory() as d:
        mod, state = th.load_ttkbootstrap(d)                              # bu ortamda kurulu olmayabilir: hata vermez
        assert (mod is None) == (not state.startswith('etkin')), state
    cmd = th.pip_install_cmd('python.exe', 'C:/x/ui-lib')
    assert cmd[1:4] == ['-m', 'pip', 'install'] and '--target' in cmd and cmd[-1] == 'ttkbootstrap==' + th.TB_VERSION
    with tempfile.TemporaryDirectory() as d:
        w = pathlib.Path(d) / 'pythonw.exe'; w.write_text('')
        assert th.console_python(str(w)) == str(w)
        (pathlib.Path(d) / 'python.exe').write_text('')
        assert th.console_python(str(w)).endswith('python.exe')
    assert str(th.ui_lib_dir('/a')).replace('\\', '/').endswith('/a/ui-lib')


@test
def organizer_bundle_and_nav_contract():
    app = (ROOT / 'app.pyw').read_text(encoding='utf-8')
    src = ROOT.parent / 'smart-organizer' / 'organizer_core.py'
    if src.is_file():                                                   # depoda: Smart Organizer cekirdegiyle birebir ayni
        assert src.read_bytes() == (ROOT / 'organizer_core.py').read_bytes()
    import organizer_core as oc
    assert oc.APP_FOLDER and callable(oc.scan) and callable(oc.execute_approved)
    for name in ('care_theme.py', 'organizer_core.py'):
        assert c._is_runtime_file(name)
        assert name in c.build_manifest(ROOT)['files']
    inst = (ROOT / 'packaging' / 'install_windows.ps1').read_text(encoding='utf-8')
    assert "'care_theme.py'" in inst and "'organizer_core.py'" in inst and 'ttkbootstrap==' + th.TB_VERSION in inst and '--target $uiLib' in inst
    order = ['Motorlar', 'Temizlik', 'Bloatware', 'Dosya düzeni', 'İnce ayarlar', 'Sürücüler', 'Aygıt temizliği', 'Bakım ve sağlık',
             'Programlar', 'Uygulama güncellemeleri', 'Uygulama kur', 'VPN', 'Kol / Gamepad']
    nav = app.split('def nav_pages(self):')[1].split('def _remember_page')[0]
    pos = [nav.index("('%s'," % t) for t in order]
    assert pos == sorted(pos), 'sol menu sirasi'
    assert 'ttk.Notebook(' not in app and 'class NavBook(tk.Frame)' in app
    import re
    raw = [l for l in app.splitlines() if re.search(r'(?<![\w.])tk\.Button\(', l)]
    assert len(raw) == 1 and 'return tk.Button(' in raw[0], raw                                 # tum dugmeler mkbtn uzerinden


# --------------------------------------------------------------------------- 3.9.0 uygulama logolari
import care_icons as ic  # noqa: E402


@test
def icons_parse_and_fetch():
    page = """<html><head><base href="/sub/"><link rel="icon" href="fav-16.png" sizes="16x16">
      <link rel="shortcut icon" href="/favicon.ico"><link rel="mask-icon" href="/m.svg">
      <link rel="icon" type="image/svg+xml" href="/v.svg"><link rel="apple-touch-icon" href="https://cdn.x.com/a180.png">
      <link rel="icon" href="/i192.png" sizes="192x192"><link rel="icon" href="http://insecure/i.png"></head></html>"""
    c_ = ic.icon_candidates(page, 'https://ornek.com/')
    assert c_[0] == 'https://cdn.x.com/a180.png' and c_[1] == 'https://ornek.com/i192.png', c_
    assert 'https://ornek.com/sub/fav-16.png' in c_ and not [u for u in c_ if u.endswith('.svg') or u.startswith('http:')]
    assert c_.index('https://ornek.com/favicon.ico') > c_.index('https://ornek.com/sub/fav-16.png')
    assert ic.icon_candidates('', 'https://a.com/x/') == ['https://a.com/favicon.ico']
    assert ic.initials('Google Chrome') == 'GC' and ic.initials('7-Zip') == '7Z' and ic.initials('VLC') == 'VL' and ic.initials('') == '?'
    assert ic.avatar_color('a') == ic.avatar_color('a') and ic.avatar_color('a') in ic.AVATAR_COLORS
    assert ic.site_url({'site': 'www.google.com/chrome'}) == 'https://www.google.com/chrome/' and ic.site_url({'site': None}) is None
    import struct, zlib
    def png(n):
        raw = b''.join(b'\x00' + b'\x10\x20\x30' * n for _ in range(n))
        ch = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
        return b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', n, n, 8, 2, 0, 0, 0)) + ch(b'IDAT', zlib.compress(raw)) + ch(b'IEND', b'')
    assert ic.png_size(png(32)) == (32, 32) and ic.png_size(b'GIF89a') is None
    calls = []

    def get(url, limit, accept):
        calls.append(url)
        if url == 'https://ornek.com/':
            return page.encode(), 'text/html', url
        if url == 'https://cdn.x.com/a180.png':
            return b'<html>engelli</html>', 'text/html', url              # HTML donen aday atlanir
        if url == 'https://ornek.com/i192.png':
            return png(48), 'image/png', url
        raise OSError('yok')
    with tempfile.TemporaryDirectory() as d:
        app = {'id': 'Ornek.App', 'name': 'Ornek', 'site': 'ornek.com'}
        idx = ic.load_index(d)
        assert ic.needs_fetch(app, d, idx) and not ic.needs_fetch({'id': 'X', 'site': None}, d, idx)
        ok, src = ic.fetch_icon(app, d, get=get)
        assert ok and src == 'https://ornek.com/i192.png' and calls[:3] == ['https://ornek.com/', 'https://cdn.x.com/a180.png', 'https://ornek.com/i192.png']
        large, small = ic.paths(d, 'Ornek.App')
        assert large.exists() and small.exists() and not ic.needs_fetch(app, d, idx)
        app2 = {'id': 'Bos.App', 'name': 'Bos', 'site': 'bos.com'}
        ok, why = ic.fetch_icon(app2, d, get=lambda *a: (_ for _ in ()).throw(OSError('ag yok')))
        assert not ok and 'ag yok' in why
        idx['Bos.App'] = {'ok': False, 't': time.time()}
        ic.save_index(d, idx)
        assert not ic.needs_fetch(app2, d, ic.load_index(d))                    # 30 gun yeniden denenmez
        assert ic.needs_fetch(app2, d, {'Bos.App': {'ok': False, 't': time.time() - 31 * 86400}})
        assert not ic.save_icon(png(8), pathlib.Path(d) / 'k.png', pathlib.Path(d) / 'k2.png')   # cok kucuk
    for bad in ('http://a.com/x.png', 'ftp://a'):
        try:
            ic._get(bad, 10, '*/*')
            raise AssertionError('kabul edilmemeli')
        except ValueError:
            pass
    sites = [a.get('site') for a in cc.INSTALL_APPS]
    assert all('site' in a for a in cc.INSTALL_APPS) and sum(1 for s_ in sites if s_) > 140
    assert not [s_ for s_ in sites if s_ and (s_.startswith(('http://', 'https://')) or ' ' in s_ or s_.startswith('github.com'))]
    assert c._is_runtime_file('care_icons.py') and 'care_icons.py' in c.build_manifest(ROOT)['files']
    assert "'care_icons.py'" in (ROOT / 'packaging' / 'install_windows.ps1').read_text(encoding='utf-8')


# --------------------------------------------------------------------------- 3.10.0 guncelleme kurtarma + GitHub uygulamalari
@test
def winget_upgrade_recovery():
    ns = c.upgrade_next_step
    assert ns(0, [], False) == 'ok' and ns(3010, [], False) == 'ok' and ns(-1978334967, [], False) == 'ok'        # 0x8A150109: yeniden baslat
    assert ns(-1978335189, [], False) == 'uptodate'                                                                 # 0x8A15002B
    assert ns(-1978334975, [], False) == 'running'                                                                  # 0x8A150101
    assert ns(1603, [], False) == 'interactive' and ns(1603, [], True) == 'fail'
    assert ns(-1978334968, [], False) == 'interactive'                                                              # 0x8A150108 yayinci hatasi
    assert ns(-1978335215, [], False) == 'fail'                                                                     # 0x8A150011 karma
    assert ns(-1978334956, [], False) == 'reinstall'                                                                # 0x8A150114
    msg = ['A newer version was found, but the install technology is different from the current version installed. Please uninstall the package and install the newer version.']
    assert ns(-1978335188, msg, False) == 'reinstall'
    assert 'kaldırıp yeniden kurmak' in c.winget_failure_reason(-1978335188, msg)
    na = ['No applicable upgrade found.', 'A newer package version is available in a configured source, but it does not apply to your system or requirements.']
    assert ns(-1978335189, na, False) == 'reinstall' and 'eşleşmiyor' in c.winget_failure_reason(-1978335189, na)   # Skywork vakasi
    assert ns(-1978335189, ['No applicable upgrade found.'], False) == 'uptodate'
    r = c.winget_failure_reason(1603, ['   ██████▒▒▒  10.0 MB / 20.0 MB', 'Installer failed with exit code: 1603', '> komut'])
    assert '1603' in r and 'Installer failed' in r and '██' not in r and '> komut' not in r, r
    cmd = c.winget_upgrade_cmd('wg', 'Opera.Opera')
    assert cmd[1] == 'upgrade' and '--silent' in cmd and '--interactive' not in cmd
    u = c.winget_uninstall_cmd('wg', 'Skywork.SkyworkDesktop', interactive=True)
    assert u[1] == 'uninstall' and '--silent' not in u and u[-1] == '--interactive'
    assert '--silent' in c.winget_uninstall_cmd('wg', 'X') and c.winget_force_install_cmd('wg', 'X')[-1] == '--force'
    cmd = c.winget_upgrade_cmd('wg', 'Opera.Opera', interactive=True)
    assert '--silent' not in cmd and cmd[-1] == '--interactive' and '--exact' in cmd
    for h in (0x8A150109, 0x8A15002B, 0x8A150101, 0x8A150108, 0x8A150011, 0x8A150114):
        assert (h - (1 << 32)) & 0xFFFFFFFF == h


@test
def install_catalog_github_additions():
    ids = [a['id'] for a in cc.INSTALL_APPS]
    assert len(ids) == len(set(i.lower() for i in ids)) and len(ids) >= 250
    for must in ('Flow-Launcher.Flow-Launcher', 'LocalSend.LocalSend', 'Ollama.Ollama', 'Devolutions.UniGetUI', 'VSCodium.VSCodium', 'FilesCommunity.Files'):
        assert must in ids, must
    assert 'MartiCliment.UniGetUI' not in ids                                  # winget-pkgs'te yalnizca on surum kaldi
    cats = {a['cat'] for a in cc.INSTALL_APPS}
    assert 'Yapay zekâ' in cats and all(a['desc'] and a['name'] for a in cc.INSTALL_APPS)
    assert not [a for a in cc.INSTALL_APPS if a['id'] in ('Logitech.GHUB', 'valinet.ExplorerPatcher', '2dust.v2rayN')]


# --------------------------------------------------------------------------- 3.11.0 VPN (WireGuard)
import care_vpn as vp  # noqa: E402
c_vpn = vp

CONF = """[Interface]
# Bouncing = 0
PrivateKey = aGVsbG8gd29ybGQgaGVsbG8gd29ybGQgaGVsbG8gd28=
Address = 10.2.0.2/32
DNS = 10.2.0.1

[Peer]
# NL-FREE#12
PublicKey = c2VydmVyIGtleSBzZXJ2ZXIga2V5IHNlcnZlciBrZXk=
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = 185.107.56.1:51820
"""


@test
def vpn_conf_and_names():
    i = vp.parse_conf(CONF)
    assert i['host'] == '185.107.56.1' and i['port'] == 51820 and i['full_tunnel'] and i['dns'] == '10.2.0.1' and 'privatekey' not in i
    assert vp.parse_conf(CONF.replace('0.0.0.0/0, ::/0', '10.0.0.0/8'))['full_tunnel'] is False
    assert vp.parse_conf(CONF.replace('185.107.56.1:51820', '[2a02::1]:51820'))['host'] == '2a02::1'
    for bad in (CONF.replace('PrivateKey', 'X'), CONF.replace('Endpoint = 185.107.56.1:51820', ''), 'rastgele metin', CONF.replace(':51820', '')):
        try:
            vp.parse_conf(bad)
            raise AssertionError('kabul edilmemeli: %r' % bad[:30])
        except ValueError:
            pass
    assert vp.country_from_name('NL-FREE#12.conf') == 'NL' and vp.country_from_name('mullvad-de-fra-wg-001.conf') == 'DE'
    assert vp.country_from_name('wg-US-NY-5.conf') == 'US' and vp.country_from_name('ProtonVPN_JP-3.conf') == 'JP'
    assert vp.country_from_name('uk-lon-wg-101.conf') == 'GB' and vp.country_from_name('evim.conf') == '' and vp.country_from_name('wg-is-12.conf') == ''
    assert vp.country_name('TR') == 'Türkiye' and vp.country_name('xx') == ''
    assert vp.tunnel_name('NL-FREE#12.conf') == 'NL-FREE-12'
    assert vp.tunnel_name('NL-FREE#12.conf', ['nl-free-12']) == 'NL-FREE-12-2'
    long = vp.tunnel_name('a' * 50 + '.conf', ['a' * 32])
    assert len(long) <= 32 and vp.NAME_RX.match(long) and long.endswith('-2')
    assert vp.NAME_RX.match(vp.tunnel_name('çok garip ad!!.conf'))


@test
def vpn_tools_and_parsers():
    assert vp.parse_ping_ms(['Minimum = 20ms, Maximum = 31ms, Average = 25ms']) == 25
    assert vp.parse_ping_ms(['En az = 20ms, En çok = 31ms, Ortalama = 24ms']) == 24
    assert vp.parse_ping_ms(['64 bytes from 1.1.1.1: icmp_seq=1 ttl=57 time=12.4 ms']) == 12
    assert vp.parse_ping_ms(['Request timed out.', 'İstek zaman aşımına uğradı.']) is None
    dump = 'priv\tpub\t51820\toff\npeerkey\t(none)\t1.2.3.4:51820\t0.0.0.0/0\t1795110000\t2048\t1024\toff\n'
    assert vp.parse_wg_dump(dump) == {'handshake': 1795110000, 'rx': 2048, 'tx': 1024} and vp.parse_wg_dump('') == {'handshake': 0, 'rx': 0, 'tx': 0}
    assert vp.human_bytes(512) == '512 B' and vp.human_bytes(3 * 1048576) == '3.0 MB'
    assert vp.parse_ipinfo('{"ip": "185.107.56.9", "country": "Netherlands", "country_iso": "NL"}') == ('185.107.56.9', 'NL', 'Hollanda')
    assert vp.install_cmd('wg.exe', 'C:/x/a.conf.dpapi') == ['wg.exe', '/installtunnelservice', 'C:/x/a.conf.dpapi']
    assert vp.uninstall_cmd('wg.exe', 'a') == ['wg.exe', '/uninstalltunnelservice', 'a']
    assert vp.ping_cmd('h')[:3] == ['ping', '-n', '2'] and vp.ping_cmd('h', False)[:3] == ['ping', '-c', '2']
    env = {'ProgramFiles': r'C:\PF'}
    assert vp.find_wireguard(env, exists=lambda p: p.endswith('wireguard.exe')).replace('\\', '/').endswith('PF/WireGuard/wireguard.exe')
    assert vp.find_wireguard(env, exists=lambda p: False) is None
    with tempfile.TemporaryDirectory() as d:
        assert vp.stored_config(d, 'a') is None
        (pathlib.Path(d) / 'a.conf').write_text('x')
        assert vp.stored_config(d, 'a').name == 'a.conf'
        (pathlib.Path(d) / 'a.conf.dpapi').write_bytes(b'x')
        assert vp.stored_config(d, 'a').name == 'a.conf.dpapi'                 # WireGuard sifreledikten sonra
    assert str(vp.config_dir(r'C:/PF/WireGuard/wireguard.exe')).replace('\\', '/').endswith('WireGuard/Data/Configurations')
    ps = (ROOT / 'care_tasks.ps1').read_text(encoding='utf-8')
    app = (ROOT / 'app.pyw').read_text(encoding='utf-8')
    assert "'vpn-status'" in ps.split('[string]$Action')[0] and " 'vpn-status' {" in ps and "'vpn-status'" in app.split('INTERNAL_PS_ACTIONS = ')[1].split('\n')[0]
    assert c._is_runtime_file('care_vpn.py') and "'care_vpn.py'" in (ROOT / 'packaging' / 'install_windows.ps1').read_text(encoding='utf-8')



@test
def vpngate_parse_and_sanitize():
    import base64
    ovpn = """###############################
# VPN Gate
dev tun
proto udp
remote 219.100.37.10 1194
client
cipher AES-128-CBC
auth-user-pass
script-security 2
up /tmp/evil.sh
route-up "calc.exe"
plugin evil.dll
log C:/Windows/x.log
<ca>
-----BEGIN CERTIFICATE-----
up this-line-is-inside-a-block
-----END CERTIFICATE-----
</ca>
"""
    b64 = base64.b64encode(ovpn.encode()).decode()
    csvtext = ('*vpn_servers\n#HostName,IP,Score,Ping,Speed,CountryLong,CountryShort,NumVpnSessions,Uptime,TotalUsers,TotalTraffic,LogType,Operator,Message,OpenVPN_ConfigData_Base64\n'
               'public-vpn-1,219.100.37.10,500000,9,120000000,Japan,JP,12,864000000,100,1,2weeks,Daiyuu Nobori,,%s\n'
               'vpn2,1.2.3.4,900000,20,50000000,Korea Republic of,KR,3,172800000,5,1,2weeks,Gonullu,,%s\n'
               'bos,5.6.7.8,1,1,1,X,XX,0,0,0,0,,,,\n*\n') % (b64, b64)
    lst = c_vpn.parse_vpngate(csvtext)
    assert [g['ip'] for g in lst] == ['1.2.3.4', '219.100.37.10'] and lst[1]['mbps'] == 120.0 and lst[1]['country'] == 'Japonya'
    assert lst[1]['uptime_days'] == 10.0 and lst[0]['cc'] == 'KR' and lst[0]['country'] == 'Güney Kore'
    try:
        c_vpn.parse_vpngate('<html>engelli</html>')
        raise AssertionError('kabul edilmemeli')
    except ValueError:
        pass
    text, remote = c_vpn.vpngate_ovpn(b64)
    assert remote == '219.100.37.10' and 'client' in text and 'remote 219.100.37.10 1194' in text
    for bad in ('script-security', 'up /tmp', 'route-up', 'plugin', 'log C:'):
        assert bad not in text, bad
    assert 'up this-line-is-inside-a-block' in text                         # sertifika blogu bozulmaz
    final = c_vpn.finalize_ovpn(text, r'C:\Users\a b\AppData\auth.txt')
    assert 'auth-user-pass "C:/Users/a b/AppData/auth.txt"' in final and '{AUTH_FILE}' not in final
    try:
        c_vpn.vpngate_ovpn(base64.b64encode(b'dev tun\nproto udp\n').decode())
        raise AssertionError('istemci olmayan kabul edilmemeli')
    except ValueError:
        pass
    assert c_vpn.openvpn_state('x\nInitialization Sequence Completed\n') == 'connected'
    assert c_vpn.openvpn_state('Initialization Sequence Completed\n...\nSIGTERM[soft,exit-with-notification]') == 'error'
    assert c_vpn.openvpn_state('AUTH_FAILED') == 'error' and c_vpn.openvpn_state('TLS: Initial packet') == 'connecting'
    cmd = c_vpn.openvpn_cmd('openvpn.exe', 'c.ovpn', 'o.log')
    assert cmd[:3] == ['openvpn.exe', '--config', 'c.ovpn'] and '--log' in cmd and '--auth-nocache' in cmd
    assert c_vpn.find_openvpn({'ProgramFiles': r'C:\PF'}, exists=lambda p: True).replace('\\', '/').endswith('PF/OpenVPN/bin/openvpn.exe')
    assert c_vpn.VPNGATE_URL.startswith('https://') and c_vpn.OVPN_PKG == 'OpenVPNTechnologies.OpenVPN'



@test
def tailscale_exit_nodes():
    st = {'BackendState': 'Running', 'Self': {'HostName': 'DESKTOP-L3', 'DNSName': 'desktop-l3.tail1234.ts.net.', 'TailscaleIPs': ['100.64.0.1', 'fd7a::1']},
          'Peer': {
              'k1': {'ID': 'n1', 'HostName': 'ugreen-turkiye', 'DNSName': 'ugreen-turkiye.tail1234.ts.net.', 'OS': 'linux', 'TailscaleIPs': ['100.64.0.2', 'fd7a::2'],
                     'Online': True, 'ExitNode': False, 'ExitNodeOption': True},
              'k2': {'ID': 'n2', 'HostName': 'hetzner-cikis', 'DNSName': 'hetzner-cikis.tail1234.ts.net.', 'OS': 'linux', 'TailscaleIPs': ['100.64.0.3'],
                     'Online': True, 'ExitNode': True, 'ExitNodeOption': True},
              'k3': {'ID': 'n3', 'HostName': 'telefon', 'OS': 'android', 'TailscaleIPs': ['100.64.0.4'], 'Online': True, 'ExitNodeOption': False},
              'k4': {'ID': 'n4', 'HostName': 'es-mad-wg-001.mullvad.ts.net', 'DNSName': 'es-mad-wg-001.mullvad.ts.net.', 'OS': 'linux',
                     'TailscaleIPs': ['100.70.0.9'], 'Online': True, 'ExitNodeOption': True, 'Location': {'Country': 'Spain', 'CountryCode': 'ES', 'City': 'Madrid'}},
              'k5': {'ID': 'n5', 'HostName': 'eski-pc', 'DNSName': 'eski-pc.tail1234.ts.net.', 'TailscaleIPs': ['100.64.0.5'], 'Online': False, 'ExitNodeOption': True}}}
    r = c_vpn.parse_ts_status(json.dumps(st))
    assert r['state'] == 'Running' and r['self'] == 'desktop-l3' and r['self_ip'] == '100.64.0.1' and not r['advertising']
    assert [n['name'] for n in r['nodes']] == ['hetzner-cikis', 'ugreen-turkiye', 'es-mad-wg-001', 'eski-pc'], [n['name'] for n in r['nodes']]
    assert r['current']['name'] == 'hetzner-cikis' and r['nodes'][1]['ip'] == '100.64.0.2'
    es = r['nodes'][2]
    assert es['mullvad'] and es['cc'] == 'ES' and es['country'] == 'İspanya' and es['city'] == 'Madrid'
    assert c_vpn.parse_ts_status({})['nodes'] == [] and c_vpn.parse_ts_status({'Self': {'PrimaryRoutes': ['0.0.0.0/0', '::/0']}})['advertising']
    assert c_vpn.ts_use_cmd('ts', '100.64.0.2') == ['ts', 'set', '--exit-node=100.64.0.2', '--exit-node-allow-lan-access=true']
    assert c_vpn.ts_clear_cmd('ts') == ['ts', 'set', '--exit-node='] and c_vpn.ts_advertise_cmd('ts', True)[-1] == '--advertise-exit-node=true'
    assert 'advertise-exit-node' in c_vpn.UGREEN_COMPOSE and 'hostname: ugreen-turkiye' in c_vpn.UGREEN_COMPOSE and '/dev/net/tun' in c_vpn.UGREEN_COMPOSE
    assert 'network_mode: host' in c_vpn.UGREEN_COMPOSE and 'restart: unless-stopped' in c_vpn.UGREEN_COMPOSE
    assert '--advertise-exit-node' in c_vpn.LINUX_EXIT_NODE_SCRIPT and 'hetzner-cikis' in c_vpn.LINUX_EXIT_NODE_SCRIPT and 'ip_forward = 1' in c_vpn.LINUX_EXIT_NODE_SCRIPT
    assert c_vpn.find_tailscale({'ProgramFiles': r'C:\PF'}, exists=lambda p: True).replace('\\', '/').endswith('PF/Tailscale/tailscale.exe')
    assert c_vpn.TS_PKG == 'Tailscale.Tailscale'


print('PASS core: %d test (%s)' % (len(PASSED), ', '.join(PASSED)))
