"""AGFO System Care - care_core birim testleri (Windows gerektirmez).  python -I tests/test_core.py <agfo-care klasoru>"""
import json
import os
import pathlib
import sys
import tempfile

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

print('PASS core: %d test (%s)' % (len(PASSED), ', '.join(PASSED)))
