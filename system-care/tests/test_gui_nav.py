"""GUI testi (Xvfb): sol menu, sayfa gecisleri, tum renk temalarinin canli uygulanmasi, Dosya duzeni analiz/tasima/geri alma.
Kullanim: xvfb-run -a python tests/test_gui_nav.py <agfo-care klasoru> [classic|modern] [ekran-goruntusu-klasoru]
modern: ttkbootstrap kuruluysa onu kullanir; classic: ayarla kapatir."""
import json
import os
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(sys.argv[1]).resolve()
MODE = sys.argv[2] if len(sys.argv) > 2 else 'classic'
SHOTS = pathlib.Path(sys.argv[3]) if len(sys.argv) > 3 else None
TMP = pathlib.Path(tempfile.mkdtemp())
os.environ['LOCALAPPDATA'] = str(TMP / 'lad')
os.environ['APPDATA'] = str(TMP / 'ad')
setdir = TMP / 'lad' / 'AGFO' / 'SystemCare'
setdir.mkdir(parents=True)
(setdir / 'settings.json').write_text(json.dumps({'auto_update_check': False, 'modern_ui': MODE == 'modern', 'last_page': 'İnce ayarlar'}), encoding='utf-8')
sys.path.insert(0, str(ROOT))
import importlib.machinery, importlib.util  # noqa: E402
loader = importlib.machinery.SourceFileLoader('care_app', str(ROOT / 'app.pyw'))
spec = importlib.util.spec_from_loader('care_app', loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)
import care_theme as theme  # noqa: E402

RESULTS = []


def check(name, cond, detail=''):
    RESULTS.append((name, bool(cond)))
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' - %s' % (detail,)), flush=True)


import care_icons as icons  # noqa: E402
import struct, zlib  # noqa: E402


def make_png(n=64, rgb=(200, 40, 40)):
    raw = b''.join(b'\x00' + bytes(rgb) * n for _ in range(n))
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', n, n, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


FAKE_OK = {'Google.Chrome', 'Mozilla.Firefox', '7zip.7zip', 'VideoLAN.VLC'}


def fake_fetch(app, cdir, get=None):
    if app['id'] in FAKE_OK:
        large, small = icons.paths(cdir, app['id'])
        return icons.save_icon(make_png(), large, small), 'sahte'
    return False, 'sahte: yok'


icons.fetch_icon = fake_fetch
m.icons.fetch_icon = fake_fetch
m.messagebox.askyesno = lambda *a, **k: True
m.messagebox.showinfo = lambda *a, **k: None
m.messagebox.showwarning = lambda *a, **k: None
m.messagebox.showerror = lambda *a, **k: print('showerror', a)
app = m.App()
app.geometry('1280x860+0+0')


def pump(sec=0.3):
    t0 = time.time()
    while time.time() - t0 < sec:
        app.update()
        time.sleep(0.02)


def idle(timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        pump(0.1)
        if not app.busy:
            return True
    return False


def shot(name):
    if SHOTS:
        SHOTS.mkdir(parents=True, exist_ok=True)
        pump(0.4)
        os.system('import -window root -crop %dx%d+%d+%d %s' % (app.winfo_width(), app.winfo_height(), app.winfo_rootx(), app.winfo_rooty(),
                                                              SHOTS / ('%s-%s.png' % (MODE, name))))


pump(1.0)
idle()
check('mode', (m.TB is not None) == (MODE == 'modern'), m.TB_STATE)
titles = [p['title'] for p in app.tabs.pages]
check('nav.pages', titles == ['Motorlar', 'Temizlik', 'Bloatware', 'Dosya düzeni', 'İnce ayarlar', 'Sürücüler', 'Aygıt temizliği', 'Bakım ve sağlık',
                              'Programlar', 'Uygulama güncellemeleri', 'Uygulama kur', 'VPN', 'Kol / Gamepad'], titles)
check('nav.last_page', app.tabs.tab(app.tabs.current, 'text') == 'İnce ayarlar', app.tabs.current)
seen = []
app.tabs.bind('<<NotebookTabChanged>>', lambda _e: seen.append(app.tabs.current), add='+')
for i in range(len(titles)):
    app.tabs.select(i)
    pump(0.05)
    check('nav.select.%d' % i, app.tabs.pages[i]['frame'].winfo_ismapped() and sum(p['frame'].winfo_ismapped() for p in app.tabs.pages) == 1)
check('nav.events', len(seen) >= len(titles) - 1, seen)
check('nav.compat', app.tabs.nametowidget(app.tabs.select()) is app.tabs.pages[app.tabs.current]['frame'] and app.tabs.tab(3, 'text') == 'Dosya düzeni')
idle()
app.tabs.select(4)
shot('ince-ayarlar-agfo-gece')

for key in theme.theme_keys()[1:] + [theme.DEFAULT]:
    app.theme_box.set(theme.theme_by_key(key)['label'])
    app.theme_box.event_generate('<<ComboboxSelected>>')
    pump(0.15)
    tok = theme.tokens(key)
    ok = (m.THEME_KEY == key and app.log.cget('bg').lower() == tok['LOG_BG'] and app.cget('bg').lower() == tok['BG']
          and app.tabs.pages[app.tabs.current]['lab'].cget('bg').lower() == tok['NAV_SEL']
          and app.tabs.pages[0]['lab'].cget('bg').lower() == tok['NAV_BG']
          and str(app.tw_tree.tree.tag_configure('st_new', 'foreground')).lower() == tok['OK_C'])
    check('theme.%s' % key, ok, (m.THEME_KEY, app.log.cget('bg'), tok['LOG_BG'], app.cget('bg'), tok['BG']))
    if key in ('agfo-acik', 'nord-dark', 'catppuccin-light'):
        shot('ince-ayarlar-' + key)
check('theme.saved', json.loads((setdir / 'settings.json').read_text(encoding='utf-8')).get('theme') == theme.DEFAULT)

# Dosya duzeni: gecici Masaustu / Belgeler
desk, docs = TMP / 'Desktop', TMP / 'Documents'
for d in (desk, docs):
    d.mkdir()
(desk / 'fatura_2026_ekim.pdf').write_bytes(b'%PDF-1.4 fatura')
(desk / 'tatil.jpg').write_bytes(b'\xff\xd8\xff')
(docs / 'BRCGS denetim raporu.docx').write_bytes(b'PK')
app.org_roots = {'Masaüstü': desk, 'Belgeler': docs}
app.tabs.select(3)
app.org_scan()
check('org.scan_idle', idle())
names = sorted(it.path.name for it in app.org_items)
check('org.scan', names == ['BRCGS denetim raporu.docx', 'fatura_2026_ekim.pdf', 'tatil.jpg'], names)
check('org.rows', len(app.org_tree.get_children()) == 3)
shot('dosya-duzeni')
app.org_tree.selection_set([it.item_id for it in app.org_items if it.path.name == 'tatil.jpg'])
app.org_decide('Kabul', False)
app.org_move()
check('org.move_idle', idle())
moved = [it for it in app.org_items if it.decision == 'Taşındı']
check('org.moved', len(moved) == 1 and not (desk / 'tatil.jpg').exists() and moved[0].target(app.org_roots).exists(), [it.decision for it in app.org_items])
app.org_undo()
check('org.undo', idle() and (desk / 'tatil.jpg').exists() and app.org_items == [])
# Uygulama kur: buyuk simge gorunumu, logolar, secim esitlemesi
app.tabs.select(10)
pump(0.5)
check('inst.default_grid', app.inst_view.get() == 'grid' and app.inst_gridf.winfo_ismapped())
t0 = time.time()
while app.inst_icon_busy and time.time() - t0 < 30:
    pump(0.2)
pump(0.6)
import care_catalog as cc  # noqa: E402
check('inst.tiles', len(app.inst_tiles) == len(cc.INSTALL_APPS), len(app.inst_tiles))
check('inst.icons', set(app.inst_img_l) == FAKE_OK, sorted(app.inst_img_l))
idx = icons.load_index(app.inst_icon_dir)
check('inst.index', idx.get('Google.Chrome', {}).get('ok') is True and idx.get('Brave.Brave', {}).get('ok') is False
      and 'Microsoft.WindowsTerminal' not in idx)                                # sitesi olmayan denenmez
app._inst_toggle('Google.Chrome'); app._inst_toggle('Brave.Brave'); app._inst_toggle('Brave.Brave')
check('inst.toggle', app.inst_sel == {'Google.Chrome'} and app.inst_count.get() == '1 seçili', (app.inst_sel, app.inst_count.get()))
shot('uygulama-kur-grid')
app.inst_q.set('chrome'); pump(0.3)
check('inst.search_grid', set(app.inst_tiles) == {'Google.Chrome'}, sorted(app.inst_tiles))
app.inst_q.set(''); pump(0.2)
app.inst_view.set('list'); app._inst_switch_view(); pump(0.3)
check('inst.list_sync', [p['id'] for p in app.inst_tree.checked_payloads() if p] == ['Google.Chrome'])
check('inst.list_icon', str(app.inst_tree.tree.item('i:Google.Chrome', 'image')) not in ('', '()'))
app.inst_tree.set_checked('i:Mozilla.Firefox', True)
app.inst_view.set('grid'); app._inst_switch_view(); pump(0.3)
check('inst.grid_sync', app.inst_sel == {'Google.Chrome', 'Mozilla.Firefox'}, app.inst_sel)
app.theme_box.set('AGFO Açık'); app.theme_box.event_generate('<<ComboboxSelected>>'); pump(0.3)
tok = theme.tokens('agfo-acik')
check('inst.theme_tiles', app.inst_tiles['Google.Chrome']['tile'].cget('bg').lower() == tok['NAV_SEL']
      and app.inst_tiles['Brave.Brave']['tile'].cget('bg').lower() == tok['PANEL2'])
shot('uygulama-kur-grid-acik')
# Uygulama guncellemeleri: sessiz basarisiz -> pencereli deneme; farkli kurulum turu -> kaldirip yeniden kur
if os.name != 'nt':
    fw = TMP / 'winget'
    fw.write_text("""#!/bin/sh
case "$*" in
  *"upgrade --source"*)
    echo 'Name          Id                 Version  Available Source'
    echo '---------------------------------------------------------'
    echo 'Opera Stable  Opera.Opera        140.0    140.1     winget'
    echo 'WordCraft     ArtCraft.WordCraft 0.10.0   0.18.1    winget'
    echo 'skywork       Skywork.Desktop    1.1.0    2.4.0     winget'
    echo '3 upgrades available.'; exit 0;;
  *"upgrade"*"--interactive"*) echo 'Successfully installed'; exit 0;;
  *"upgrade"*"Skywork.Desktop"*) echo 'No applicable upgrade found.'; echo 'A newer package version is available in a configured source, but it does not apply to your system or requirements.'; exit 43;;
  *"upgrade"*"Opera.Opera"*) echo 'Installer failed with exit code: 1603'; exit 67;;
  *"upgrade"*"ArtCraft.WordCraft"*) echo 'A newer version was found, but the install technology is different from the current version installed. Please uninstall the package and install the newer version.'; exit 1;;
  *"uninstall"*"Skywork.Desktop"*) echo 'Uninstall failed with exit code: 1603'; exit 67;;
  *"install"*"Skywork.Desktop"*"--force"*) echo 'Successfully installed'; exit 0;;
  *"install"*"Skywork.Desktop"*) exit 5;;
  *"uninstall"*|*"install"*) echo ok; exit 0;;
esac
exit 9
""")
    fw.chmod(0o755)
    app.engines = {'winget': {'path': str(fw)}}
    app.tabs.select(9)
    app.apps_scan(); idle()
    at = app.app_tree
    ids = [at.payload[i]['id'] for i in at.labels]
    check('upd.rows', ids == ['Opera.Opera', 'ArtCraft.WordCraft', 'Skywork.Desktop'], ids)
    app.apps_update(); check('upd.idle', idle(60))
    st = {at.payload[i]['id']: (at.tree.set(i, 'state'), at.tree.set(i, 'why')) for i in at.labels}
    check('upd.opera_interactive', st['Opera.Opera'][0] == 'Güncellendi' and '--interactive' in app.log.get('1.0', 'end'), st)
    check('upd.wordcraft_reinstall', st['ArtCraft.WordCraft'][0] == 'Yeniden kurulmalı' and 'kaldırıp yeniden' in st['ArtCraft.WordCraft'][1]
          and 'ArtCraft.WordCraft' in app.app_reinstall, st)
    check('upd.skywork_reinstall', st['Skywork.Desktop'][0] == 'Yeniden kurulmalı' and 'Skywork.Desktop' in app.app_reinstall, st)
    app.apps_reinstall(); check('upd.reinstall_idle', idle(60))
    st = {at.payload[i]['id']: at.tree.set(i, 'state') for i in at.labels}
    check('upd.reinstalled', st['ArtCraft.WordCraft'] == 'Güncellendi' and st['Skywork.Desktop'] == 'Güncellendi' and not app.app_reinstall, st)
    lt = app.log.get('1.0', 'end')
    why = {at.payload[i]['id']: at.tree.set(i, 'why') for i in at.labels}
    check('upd.skywork_fallbacks', 'uninstall --id Skywork.Desktop' in lt and '--interactive' in lt.split('uninstall --id Skywork.Desktop', 2)[-1]
          and '--force' in lt and 'üzerine kuruldu' in why['Skywork.Desktop'], why['Skywork.Desktop'])
    shot('guncellemeler')
# VPN: sahte WireGuard ile ice aktarma, ulke, gecikme, en hizliya baglanma, silme
if os.name != 'nt':
    wgd = TMP / 'WireGuard'; wgd.mkdir()
    fwg = wgd / 'wireguard.exe'
    fwg.write_text('#!/bin/sh\necho "wireguard $*" >> "%s"\nexit 0\n' % (TMP / 'wg.log'))
    fwg.chmod(0o755)
    fping = TMP / 'fakeping'
    fping.write_text('#!/bin/sh\ncase "$1" in 10.0.0.1) echo "Average = 40ms";; 10.0.0.2) echo "Average = 12ms";; *) echo "Request timed out.";; esac\n')
    fping.chmod(0o755)
    m.vpn.ping_cmd = lambda host, windows=True: [str(fping), host]
    confs = []
    for fname, ip in (('DE-fra-1.conf', '10.0.0.1'), ('de-ber-2.conf', '10.0.0.2'), ('US-NY#5.conf', '10.0.0.3'), ('bozuk.conf', None)):
        pth = TMP / fname
        pth.write_text(('[Interface]\nPrivateKey = a2V5\nAddress = 10.9.0.2/32\n[Peer]\nPublicKey = cHVi\nAllowedIPs = 0.0.0.0/0\nEndpoint = %s:51820\n' % ip) if ip else 'yok')
        confs.append(str(pth))
    app.vpn_wg = str(fwg); app.admin = True
    m.filedialog.askopenfilenames = lambda **k: confs
    app.tabs.select(11); pump(0.3)
    app.vpn_import(); pump(0.2)
    names = sorted(t['name'] for t in app.vpn_tunnels)
    check('vpn.import', names == ['DE-fra-1', 'US-NY-5', 'de-ber-2'] and (wgd / 'Data' / 'Configurations' / 'DE-fra-1.conf').exists(), names)
    check('vpn.countries', {t['name']: t['country'] for t in app.vpn_tunnels} == {'DE-fra-1': 'DE', 'de-ber-2': 'DE', 'US-NY-5': 'US'})
    check('vpn.country_filter', 'Almanya (DE)' in app.vpn_country.cget('values') and 'ABD (US)' in app.vpn_country.cget('values'))
    app.vpn_country.set('Almanya (DE)'); app._vpn_render()
    check('vpn.filter_rows', sorted(app.vpn_tree.get_children()) == ['DE-fra-1', 'de-ber-2'])
    app.vpn_fastest()
    t0 = time.time()
    while time.time() - t0 < 15 and 'wireguard /installtunnelservice' not in ((TMP / 'wg.log').read_text() if (TMP / 'wg.log').exists() else ''):
        pump(0.2)
    idle()
    wl = (TMP / 'wg.log').read_text() if (TMP / 'wg.log').exists() else ''
    check('vpn.fastest', app.vpn_ping.get('de-ber-2') == 12 and app.vpn_ping.get('DE-fra-1') == 40 and 'de-ber-2.conf' in wl and 'DE-fra-1.conf' not in wl, (app.vpn_ping, wl))
    app.vpn_running = {'de-ber-2': 'Running'}; app._vpn_render()
    check('vpn.status_line', app.vpn_status.get().startswith('BAĞLI: de-ber-2') and 'Almanya' in app.vpn_status.get(), app.vpn_status.get())
    shot('vpn')
    app.vpn_connect(next(t for t in app.vpn_tunnels if t['name'] == 'US-NY-5')); idle()
    wl = (TMP / 'wg.log').read_text()
    check('vpn.switch', 'uninstalltunnelservice de-ber-2' in wl and wl.rfind('US-NY-5.conf') > wl.rfind('uninstalltunnelservice de-ber-2'), wl)
    app.vpn_country.set('Tümü'); app._vpn_render()
    app.vpn_tree.selection_set('DE-fra-1'); app.vpn_remove(); idle()
    check('vpn.remove', 'DE-fra-1' not in [t['name'] for t in app.vpn_tunnels] and not (wgd / 'Data' / 'Configurations' / 'DE-fra-1.conf').exists())
    saved = json.loads((setdir / 'vpn-tunnels.json').read_text(encoding='utf-8'))
    check('vpn.saved', sorted(t['name'] for t in saved) == ['US-NY-5', 'de-ber-2'] and not any('PrivateKey' in json.dumps(t) or 'a2V5' in json.dumps(t) for t in saved))
# VPN Gate: onbellekteki liste, ulke suzgeci, en hizliya baglan (sahte OpenVPN), kesme
if os.name != 'nt':
    import base64
    ov = base64.b64encode(b'client\ndev tun\nproto udp\nremote 10.1.0.1 1194\nauth-user-pass\nup /tmp/x.sh\n').decode()
    rows = ['%s,%s,%d,9,%d,Japan,%s,5,86400000,1,1,2weeks,Op%d,,%s' % ('h%d' % i, ip, 1000 - i, sp, cc, i, ov)
            for i, (ip, sp, cc) in enumerate((('10.0.0.1', 90000000, 'JP'), ('10.0.0.2', 40000000, 'JP'), ('10.0.0.3', 70000000, 'KR')))]
    gl = '*vpn_servers\n#HostName,IP,Score,Ping,Speed,CountryLong,CountryShort,NumVpnSessions,Uptime,TotalUsers,TotalTraffic,LogType,Operator,Message,OpenVPN_ConfigData_Base64\n' + '\n'.join(rows) + '\n*\n'
    app.gate_dir.mkdir(parents=True, exist_ok=True)
    (app.gate_dir / 'list.csv').write_text(gl, encoding='utf-8')
    fov = TMP / 'openvpn'
    fov.write_text('#!/bin/sh\nwhile [ $# -gt 0 ]; do [ "$1" = "--log" ] && L="$2"; [ "$1" = "--config" ] && C="$2"; shift; done\n'
                   'cp "$C" "%s"; echo "Initialization Sequence Completed" > "$L"; sleep 30\n' % (TMP / 'used.ovpn'))
    fov.chmod(0o755)
    m.vpn.find_openvpn = lambda *a, **k: str(fov)
    app.vpn_src.set('gate'); app._vpn_switch_src(); pump(0.3)
    check('gate.list', sorted(app.gate_tree.get_children()) == ['10.0.0.1', '10.0.0.2', '10.0.0.3'], app.gate_tree.get_children())
    check('gate.countries', 'Japonya (JP)' in app.vpn_country.cget('values') and 'Güney Kore (KR)' in app.vpn_country.cget('values'), app.vpn_country.cget('values'))
    app.vpn_country.set('Japonya (JP)'); app._vpn_refresh()
    check('gate.filter', sorted(app.gate_tree.get_children()) == ['10.0.0.1', '10.0.0.2'])
    app.vpn_fastest()
    t0 = time.time()
    while time.time() - t0 < 15 and not (app.gate_active and app.gate_active.get('state') == 'connected'):
        pump(0.2)
    check('gate.connected', app.gate_active and app.gate_active['ip'] == '10.0.0.1' and app.gate_active['state'] == 'connected', app.gate_active)
    used = (TMP / 'used.ovpn').read_text() if (TMP / 'used.ovpn').exists() else ''
    check('gate.sanitized', 'up /tmp/x.sh' not in used and 'auth-user-pass "' in used and (app.gate_dir / 'auth.txt').read_text() == 'vpn\nvpn\n', used)
    check('gate.status', app.vpn_status.get().startswith('BAĞLI (VPN Gate): JP'), app.vpn_status.get())
    check('gate.saved', json.loads((setdir / 'settings.json').read_text(encoding='utf-8')).get('vpngate_active', {}).get('ip') == '10.0.0.1')
    shot('vpn-gate')
    app.vpn_disconnect(); pump(0.3)
    check('gate.stopped', app.gate_proc is None and app.gate_active is None and 'vpngate_active' not in json.loads((setdir / 'settings.json').read_text(encoding='utf-8')))
check('busy_free', not app.busy)
app.destroy()
fails = [n for n, ok in RESULTS if not ok]
print('%s gui-nav (%s): %d/%d' % ('PASS' if not fails else 'FAIL', MODE, len(RESULTS) - len(fails), len(RESULTS)))
sys.exit(1 if fails else 0)
