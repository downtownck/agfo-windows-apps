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
check('nav.pages', titles == ['Genel bakış', 'AI asistan', 'Motorlar', 'Temizlik', 'Bloatware', 'Dosya düzeni', 'İnce ayarlar', 'Çalışan uygulamalar', 'Servisler', 'Başlangıç', 'Bakım ve sağlık', 'Programlar',
                              'Uygulama güncellemeleri', 'Uygulama kur', 'İnternet hızı', 'DNS yönetimi', 'VPN', 'Ağ tarayıcı', 'Ağ testleri', 'SSH sunucularım', 'SSH oturumları',
                              'Sistem özeti', 'Aygıt yöneticisi', 'Disk sağlığı', 'Sürücüler', 'Üretici desteği', 'NVIDIA', 'Aygıt temizliği', 'Kol / Gamepad'], titles)
check('nav.last_page', app.tabs.tab(app.tabs.current, 'text') == 'İnce ayarlar', app.tabs.current)
seen = []
app.tabs.bind('<<NotebookTabChanged>>', lambda _e: seen.append(app.tabs.current), add='+')
for i in range(len(titles)):
    app.tabs.select(i)
    pump(0.05)
    check('nav.select.%d' % i, app.tabs.pages[i]['frame'].winfo_ismapped() and sum(p['frame'].winfo_ismapped() for p in app.tabs.pages) == 1)
check('nav.events', len(seen) >= len(titles) - 1, seen)
check('nav.compat', app.tabs.nametowidget(app.tabs.select()) is app.tabs.pages[app.tabs.current]['frame'] and app.tabs.tab(app.tabs.index('Dosya düzeni'), 'text') == 'Dosya düzeni')
idle()
app.tabs.select('İnce ayarlar')
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
app.tabs.select('Dosya düzeni')
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
app.tabs.select('Uygulama kur')
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
    app.tabs.select('Uygulama güncellemeleri')
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
    app.tabs.select('VPN'); pump(0.3)
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
# Tailscale cikis noktalari: UGREEN (Turk IP) / Hetzner (yabanci IP), sahte tailscale.exe
if os.name != 'nt':
    tsj = TMP / 'ts.json'
    def ts_state(active):
        return json.dumps({'BackendState': 'Running', 'Self': {'HostName': 'pc', 'DNSName': 'pc.t.ts.net.', 'TailscaleIPs': ['100.64.0.1']},
                           'Peer': {'a': {'ID': '1', 'HostName': 'ugreen-turkiye', 'DNSName': 'ugreen-turkiye.t.ts.net.', 'OS': 'linux', 'TailscaleIPs': ['100.64.0.2'],
                                          'Online': True, 'ExitNodeOption': True, 'ExitNode': active == 'ugreen'},
                                    'b': {'ID': '2', 'HostName': 'hetzner-cikis', 'DNSName': 'hetzner-cikis.t.ts.net.', 'OS': 'linux', 'TailscaleIPs': ['100.64.0.3'],
                                          'Online': True, 'ExitNodeOption': True, 'ExitNode': active == 'hetzner'}}})
    tsj.write_text(ts_state(None))
    fts = TMP / 'tailscale.exe'
    fts.write_text('#!/bin/sh\necho "ts $*" >> "%s"\ncase "$*" in status*) cat "%s";; esac\nexit 0\n' % (TMP / 'ts.log', tsj))
    fts.chmod(0o755)
    m.vpn.find_tailscale = lambda *a, **k: str(fts)
    app.vpn_src.set('ts'); app._vpn_switch_src()
    t0 = time.time()
    while time.time() - t0 < 10 and not app.ts_tree.get_children():
        pump(0.2)
    check('ts.nodes', sorted(app.ts_tree.get_children()) == ['100.64.0.2', '100.64.0.3'], app.ts_tree.get_children())
    check('ts.info', 'ugreen-turkiye' in app.ts_info.get() and 'hetzner-cikis' in app.ts_info.get())
    app.ts_tree.selection_set('100.64.0.2'); app.vpn_connect(); idle()
    tl = (TMP / 'ts.log').read_text()
    check('ts.use', 'ts set --exit-node=100.64.0.2 --exit-node-allow-lan-access=true' in tl, tl)
    tsj.write_text(ts_state('ugreen')); app.ts_refresh()
    t0 = time.time()
    while time.time() - t0 < 10 and not app._ts_current():
        pump(0.2)
    check('ts.status', app.vpn_status.get().startswith('BAĞLI (Tailscale çıkışı): ugreen-turkiye'), app.vpn_status.get())
    shot('vpn-tailscale')
    app.ts_copy_ugreen()
    check('ts.clipboard', 'set --advertise-exit-node' in app.clipboard_get() and 'docker exec' in app.clipboard_get())
    app.vpn_disconnect(); idle()
    check('ts.clear', 'ts set --exit-node=' in (TMP / 'ts.log').read_text().splitlines()[-1] or 'ts set --exit-node=\n' in (TMP / 'ts.log').read_text())

# ---- Ag araclari (SuperTools): tarayici, SSH profili yerel klasorde, kayitli sunucuda tek komut
net = app.net
app.tabs.select('Ağ tarayıcı'); pump(1.5)
check('net.discovered', net.discovered)
import scanner_core as sc  # noqa: E402
for r in (sc.HostResult('10.0.0.5', True, (22, 445), hostname='ornek-nas', elapsed_ms=4, mac='00:11:22:33:44:55'),
          sc.HostResult('10.0.0.9', False, (), discovery='ARP', verified=False)):
    net._insert_result(r)
check('net.rows', sorted(net.tree.get_children()) == ['10.0.0.5', '10.0.0.9'] and '1 aktif' in net.found_var.get(), net.found_var.get())
shot('net-scan')
check('net.tags', net.tree.item('10.0.0.5', 'tags') == ('smb',) and net.tree.item('10.0.0.9', 'tags') == ('candidate',))
net.tree.selection_set('10.0.0.5')
net._ssh_from_selected(); pump(0.3)
check('net.ssh_from_scan', net.ssh_host_var.get() == '10.0.0.5' and app.tabs.tab(app.tabs.current, 'text') == 'SSH sunucularım')
net.ssh_user_var.set('yonetici'); net._ssh_save(); pump(0.2)
prof_file = TMP / 'lad' / 'AGFO-MultiSubnet-Scanner' / 'ssh-profiles.json'
check('net.profile_local_only', prof_file.is_file() and len(net.ssh_profiles) == 1 and not list(ROOT.rglob('ssh-profiles*.json')), prof_file)
opened, sent = [], []
net._ssh_open_password = lambda failed=False, profile_override=None: opened.append(profile_override)
picked = net.ssh_profiles[0]
net._pick_profile = lambda title, hint='': picked
check('net.run_on_server', net.run_on_server('echo TAMAM', 'Test') and opened == [picked] and net._pending_cmd == {picked.id: 'echo TAMAM'})


class FakeTransport:
    def send(self, text): sent.append(text)
    def close(self): pass


rec = net.ssh_workspace.add_session(picked)
net.msg_queue.put(('ssh_live_connected', (rec.id, FakeTransport(), picked.name, False)))
pump(1.5)
check('net.pending_cmd_sent', sent == ['echo TAMAM\n'] and not net._pending_cmd, sent)
check('net.diag_built', str(net.diag_output.cget('bg')).lower() == m.LOG_BG.lower() and net.diag_tool_combo.get() == 'DNS MX', net.diag_output.cget('bg'))
net._set_diag_output('deneme'); check('net.diag_output', net.diag_output.get('1.0', 'end-1c') == 'deneme')
cur = m.THEME_KEY
alt = next(k for k in theme.theme_keys() if k != cur)
app.apply_theme(alt); pump(0.3)
check('net.retheme', str(net.diag_output.cget('bg')).lower() == m.LOG_BG.lower() and str(net.scope_text.cget('bg')).lower() == m.TREE_BG.lower())
app.apply_theme(cur); pump(0.2)
shot('net-ssh')
net._pending_cmd.clear(); opened.clear()
dlg = app.ts_copy_script(); pump(0.2)       # 4.3.4: pencere — komutu kopyala / okunur betik / SSH ile calistir
check('net.vpn_cmd_dialog', app.clipboard_get() == m.vpn.LINUX_EXIT_NODE_SCRIPT and dlg['text'].get('1.0', 'end-1c') == m.vpn.LINUX_EXIT_NODE_SCRIPT
      and dlg['win'].winfo_exists() and not opened)
dlg['toggle'](); pump(0.1)
check('net.vpn_cmd_readable', 'H=hetzner-cikis' in dlg['text'].get('1.0', 'end-1c'))
app.clipboard_clear(); dlg['copy']()
check('net.vpn_cmd_copy', app.clipboard_get() == m.vpn.LINUX_EXIT_NODE_SCRIPT and 'Kopyalandı' in dlg['status'].get())
dlg['run'](); pump(0.2)
check('net.vpn_hetzner_via_ssh', opened == [picked] and net._pending_cmd.get(picked.id, '') == m.vpn.LINUX_EXIT_NODE_SCRIPT, net._pending_cmd)
net._pending_cmd.clear(); opened.clear()
app.ts_copy_script('netcup')['run'](); pump(0.2)
check('net.vpn_netcup_via_ssh', opened == [picked] and net._pending_cmd.get(picked.id, '') == m.vpn.NETCUP_EXIT_NODE_SCRIPT)
net._pending_cmd.clear(); opened.clear()
app.ts_diag_server()['run'](); pump(0.2)
check('net.vpn_diag_via_ssh', opened == [picked] and net._pending_cmd.get(picked.id, '') == m.vpn.EXIT_NODE_DIAG_CMD)
net._pending_cmd.clear()

# ---- 4.0 Genel bakis ve Donanim (sahte PowerShell kayitlari)
OV = [{'type': 'ov', 'key': 'disks', 'state': 'ok', 'value': '2 disk saglikli'}, {'type': 'ov', 'key': 'devices', 'state': 'warn', 'value': '1 sorunlu aygit'},
      {'type': 'ov', 'key': 'volume:C', 'state': 'bad', 'value': '%5 bos', 'detail': 'C 12 GB bos / 240 GB'},
      {'type': 'ov', 'key': 'defender', 'state': 'ok', 'value': 'Gercek zamanli koruma acik', 'detail': 'Imza yasi: 0 gun'}]
app.tabs.select('Genel bakış'); pump(0.2)
app._ov_render(OV); pump(0.2)
titles_ov = [c['title'] for c in app.ov_cards]
check('ov.cards', titles_ov[:3] == ['Disk sağlığı', 'Aygıtlar', 'Disk C:'] and 'Microsoft Defender' in titles_ov, titles_ov)
check('ov.score', app.ov_score.get() == 'Sağlık puanı: 67 / 100' and 'Gerçek zamanlı koruma açık' in [c['value'] for c in app.ov_cards], app.ov_score.get())
shot('overview')
HW = [{'type': 'hw', 'kind': 'cpu', 'name': 'Ornek CPU 8 Cekirdek', 'cores': 8, 'threads': 16, 'mhz': 3600},
      {'type': 'hw', 'kind': 'ram', 'name': 'DIMM A1', 'size': 17179869184, 'mhz': 3200, 'smbtype': 26, 'maker': 'Ornek'},
      {'type': 'hw', 'kind': 'ram', 'name': 'DIMM B1', 'size': 17179869184, 'mhz': 3200, 'smbtype': 26, 'maker': 'Ornek'},
      {'type': 'hw', 'kind': 'disk', 'name': 'Ornek NVMe 1TB', 'size': 1000204886016, 'media': 4, 'bus': 17, 'health': 0}]
app.tabs.select('Sistem özeti'); pump(0.2)
app._hw_render(HW)
secs = [app.hw_tree.item(i, 'text') for i in app.hw_tree.get_children()]
mem = [app.hw_tree.item(i, 'values')[0] for i in app.hw_tree.get_children('s1')]
check('hw.sections', secs == ['İşlemci', 'Bellek', 'Diskler'] and mem[0].startswith('32.0 GB (2 modül, DDR4)'), (secs, mem))
PNP = [{'type': 'pnp', 'name': 'Ornek Ag Karti', 'cls': 'Net', 'id': 'PCI\\VEN_1', 'code': 0, 'present': True, 'ver': '1.0'},
       {'type': 'pnp', 'name': 'Bilinmeyen aygit', 'cls': '', 'id': 'ACPI\\X1', 'code': 28, 'present': True},
       {'type': 'pnp', 'name': 'Eski USB bellek', 'cls': 'DiskDrive', 'id': 'USBSTOR\\Y', 'code': 0, 'present': False}]
app.tabs.select('Aygıt yöneticisi'); pump(0.2)
app._dm_set(PNP)
groups = [app.dm_tree.item(i, 'text') for i in app.dm_tree.get_children()]
check('dm.groups', groups == ['Diğer aygıtlar (1)', 'Ağ bağdaştırıcıları (1)'] and app.dm_count.get() == '2 aygıt · 1 sorunlu', (groups, app.dm_count.get()))
check('dm.problem_text', app.dm_tree.set('g0_0', 'state') == 'Sürücü yüklü değil')
app.dm_hidden.set(True); app._dm_render()
check('dm.hidden', len(app.dm_tree.get_children()) == 3)
captured = []
real_start, real_admin = app.start, app.admin
app.start = lambda jobs, quiet=False: captured.extend(jobs) or True
app.admin = True
app.dm_tree.selection_set('g0_0'); app.dm_action('disable')
check('dm.action_cmd', captured and '-PnpOp' in captured[0].cmd and 'disable' in captured[0].cmd and 'ACPI\\X1' in captured[0].cmd, captured and captured[0].cmd)
app.start, app.admin = real_start, real_admin
app.tabs.select('Disk sağlığı'); pump(0.2)
app._dh_set([{'type': 'disk', 'name': 'Ornek SSD', 'media': 'SSD', 'bus': 'NVMe', 'size': 512110190592, 'health': 'Healthy', 'temp': 64, 'wear': 3, 'hours': 1200, 'admin': True}])
check('dh.verdict', app.dh_tree.item('d0', 'tags') == ('warn',) and app.dh_tree.set('d0', 'verdict').startswith('Dikkat'), app.dh_tree.set('d0', 'verdict'))
rep_html = __import__('care_hw').report_html(*app._hw_report_parts())
check('hw.report', 'Ornek CPU' in rep_html and 'Sorunlu aygıtlar' in rep_html and 'Ornek SSD' in rep_html and 'text-decoration:none' in rep_html)
shot('devmgr')

# ---- 4.1 Uretici destegi ve NVIDIA (sahte kayitlar)
app.tabs.select('Üretici desteği'); pump(0.2)
app._oem_set({'type': 'oem', 'maker': 'Dell Inc.', 'model': 'Latitude 5420', 'serial': 'ORNEK12', 'sku': '0A12', 'board_maker': 'Dell Inc.', 'board': '0X1Y2Z', 'notebook': True})
vals = {app.oem_tree.item(i, 'text'): app.oem_tree.item(i, 'values')[0] for i in app.oem_tree.get_children()}
check('oem.render', app.oem_title.get() == 'Dell · Latitude 5420' and vals['Açılacak sayfa'].endswith('/servicetag/ORNEK12/drivers') and vals['Tür'] == 'Dizüstü', vals)
tools = [w for w in app.oem_tools.winfo_children()]
check('oem.tools', len(tools) == 2, len(tools))
opened = []
app._open_url = lambda u: opened.append(u)
app.oem_open(); app.oem_open(search=True)
check('oem.open', opened[0].endswith('/servicetag/ORNEK12/drivers') and 'site%3Adell.com' in opened[1], opened)
app._oem_set({'type': 'oem', 'maker': 'HP', 'model': 'HP ProBook 450 G8 Notebook PC', 'serial': '5CDORNEK', 'notebook': True})
app.oem_open()
check('oem.copy_serial', app.clipboard_get() == '5CDORNEK' and opened[-1].startswith('https://support.hp.com/'), opened[-1])
app.tabs.select('NVIDIA'); pump(0.2)
NVI = {'type': 'nvinfo', 'gpus': [{'name': 'Intel(R) UHD Graphics', 'driver': '31.0.101.4502', 'nvidia': False},
                                  {'name': 'NVIDIA GeForce RTX 4060 Laptop GPU', 'driver': '32.0.15.6094', 'date': '2024-09-10', 'nvidia': True}],
       'notebook': True, 'dch': True, 'build': 26100, 'x64': True, 'nvi2': True, 'sevenzip': '', 'ddu': '',
       'apps': [{'name': 'NVIDIA Graphics Driver 560.94', 'version': '560.94'}], 'packages': [{'inf': 'oem12.inf', 'name': 'NVIDIA GeForce RTX 4060 Laptop GPU', 'cls': 'DISPLAY', 'ver': '32.0.15.6094'}]}
app._nv_set_info(NVI)
check('nv.current', app.nv_state.get() == 'Kurulu: 560.94', app.nv_state.get())
app._nv_set_latest({'version': '581.57', 'url': 'https://us.download.nvidia.com/x.exe', 'name': 'GeForce Game Ready Driver', 'date': '2025-10-16', 'details': ''})
check('nv.update_available', app.nv_state.get() == 'Güncelleme var: 560.94 → 581.57', app.nv_state.get())
secs = [app.nv_tree.item(i, 'text') for i in app.nv_tree.get_children()]
check('nv.tree', secs == ['Ekran kartları', 'Durum', 'Kurulu NVIDIA yazılımları', 'NVIDIA sürücü paketleri (Windows deposu)'], secs)
captured = []
real_start = app.start
app.start = lambda jobs, quiet=False: captured.extend(jobs) or True
app.nv_uninstall('packages')
check('nv.uninstall_cmd', captured and 'nvidia-remove-packages' in captured[0].cmd, captured and captured[0].cmd)
captured.clear(); app.nv_minimal.set(True); app.nv_install()
check('nv.minimal_needs_7zip', captured and '7zip.7zip' in captured[0].cmd, captured and captured[0].cmd)
captured.clear(); app.nv_minimal.set(False); app.nv_install()
check('nv.install_chain', [j.title for j in captured] == ['NVIDIA sürücüsünü indir', 'İmza denetimi'] and 'sig-check' in captured[1].cmd, [j.title for j in captured])
captured.clear(); app.nv_ddu()
check('nv.ddu_install', captured and 'Wagnardsoft.DisplayDriverUninstaller' in captured[0].cmd)
app.start = real_start
shot('nvidia')

# ---- 4.1.1 Uretici otomatik guncelleme (Lenovo / Dell / diger)
app.tabs.select('Üretici desteği'); pump(0.2)
app._oem_set({'type': 'oem', 'maker': 'LENOVO', 'model': '82XF', 'family': 'IdeaPad Slim 5 16IAH8', 'serial': 'PFORNEK1', 'notebook': True})
check('auto.lenovo_mode', 'LSUClient' in app.oem_auto_note.get() and app.oem_scan_btn.cget('text') == 'Lenovo güncellemelerini tara')
LSU = [{'type': 'lsu', 'id': 'n3xyz01w', 'title': 'Intel Graphics Driver', 'category': 'Display and Video Graphics', 'ptype': 'Driver', 'version': '31.0.101.5', 'severity': 'Recommended', 'unattended': True},
       {'type': 'lsu', 'id': 'kycn40ww', 'title': 'BIOS Update', 'category': 'BIOS/UEFI', 'ptype': 'BIOS', 'version': 'KYCN40WW', 'severity': 'Critical', 'unattended': True},
       {'type': 'lsu', 'id': 'manual1', 'title': 'Lenovo Hotkeys', 'category': 'Software', 'ptype': 'Application', 'version': '1.0', 'severity': 'Optional', 'unattended': False}]
app._oem_set_updates(LSU, 'lenovo')
checked = [p['id'] for p in app.oem_upd.checked_payloads() if p]
check('auto.lenovo_default_selection', checked == ['n3xyz01w'], checked)
captured = []
real_start = app.start
app.start = lambda jobs, quiet=False: captured.extend(jobs) or True
app.oem_auto_install()
check('auto.lenovo_install_cmd', captured and 'lenovo-install' in captured[0].cmd and 'n3xyz01w' in captured[0].cmd and captured[0].cmd[-1] == 'no', captured and captured[0].cmd)
captured.clear()
app._oem_set({'type': 'oem', 'maker': 'Dell Inc.', 'model': 'Latitude 5420', 'serial': 'ORNEK12'})
app.oem_auto_scan()
check('auto.dell_scan', captured and 'dell-scan' in captured[0].cmd)
captured.clear(); app.oem_bios.set(True); app.oem_auto_install()
check('auto.dell_install', captured and 'dell-install' in captured[0].cmd and captured[0].cmd[-1] == 'yes', captured and captured[0].cmd)
app.oem_bios.set(False)
app.start = real_start
app._oem_set({'type': 'oem', 'maker': 'HP', 'model': 'HP ProBook 450 G8', 'serial': '5CDORNEK'})
check('auto.other_mode', app.oem_scan_btn.cget('text') == 'Windows Update sürücülerini tara')
shot('oem-auto')

# ---- 4.2 Calisan uygulamalar / Servisler / Baslangic (sahte kayitlar)
app.tabs.select('Çalışan uygulamalar'); pump(0.2)
PROCS = [{'type': 'proc', 'pid': 4120, 'name': 'chrome', 'cpu': 4.5, 'mem': 734003200, 'title': 'Google Chrome', 'company': 'Google LLC', 'path': 'C:\\Program Files\\Google\\Chrome\\chrome.exe', 'session': 1},
         {'type': 'proc', 'pid': 880, 'name': 'lsass', 'cpu': 0.1, 'mem': 20971520, 'title': '', 'company': '', 'path': '', 'session': 0},
         {'type': 'proc', 'pid': 5000, 'name': 'notepad', 'cpu': 0.0, 'mem': 15728640, 'title': 'Adsız - Not Defteri', 'company': 'Microsoft', 'path': 'C:\\Windows\\notepad.exe', 'session': 1}]
app._pc_set(PROCS)
check('pc.windowed', [app.pc_tree.item(i, 'text') for i in app.pc_tree.get_children()] == ['chrome'], [app.pc_tree.item(i, 'text') for i in app.pc_tree.get_children()])
app.pc_hide_sys.set(False); app.pc_windowed.set(False); app._pc_render()
check('pc.all', len(app.pc_tree.get_children()) == 3 and app.pc_tree.item('p880', 'tags') == ('crit',))
captured = []
real_start = app.start
app.start = lambda jobs, quiet=False: captured.extend(jobs) or True
app.pc_tree.selection_set(('p4120', 'p880')); app.pc_kill(False)
import base64 as _b64, json as _json
sent = _json.loads(_b64.b64decode(captured[0].cmd[captured[0].cmd.index('-ItemsB64') + 1])) if captured else []
check('pc.kill_skips_critical', sent == [{'pid': 4120, 'name': 'chrome'}] and captured[0].cmd[-1] == 'kill' and not captured[0].admin, sent)
captured.clear()
app.tabs.select('Servisler'); pump(0.2)
app._sv_set([{'type': 'svc', 'name': 'Spooler', 'display': 'Yazdırma Biriktiricisi', 'state': 'Running', 'start': 'Auto', 'account': 'LocalSystem', 'path': 'C:\\Windows\\System32\\spoolsv.exe'},
             {'type': 'svc', 'name': 'RpcSs', 'display': 'Uzak Yordam Çağrısı (RPC)', 'state': 'Running', 'start': 'Auto', 'path': 'C:\\Windows\\system32\\svchost.exe -k rpcss'},
             {'type': 'svc', 'name': 'OrnekGuncelleme', 'display': 'Ornek Updater', 'state': 'Stopped', 'start': 'Auto', 'delayed': True, 'path': '"C:\\Program Files\\Ornek\\upd.exe"'}])
check('sv.render', app.sv_count.get() == '3 gösteriliyor · 2 çalışıyor / 3' and app.sv_tree.set('s2', 'start') == 'Otomatik (gecikmeli)', (app.sv_count.get(), app.sv_tree.set('s2', 'start')))
app.sv_tree.selection_set(('s0', 's1')); app.sv_action('disabled')
svs = _json.loads(_b64.b64decode(captured[0].cmd[captured[0].cmd.index('-ItemsB64') + 1])) if captured else []
check('sv.disable_skips_critical', svs == [{'name': 'Spooler'}] and 'svc-action' in captured[0].cmd and captured[0].cmd[-1] == 'disabled', svs)
captured.clear()
app.sv_third.set(True); app._sv_render()
check('sv.third_party', [app.sv_tree.set(i, 'name') for i in app.sv_tree.get_children()] == ['OrnekGuncelleme'])
app.tabs.select('Başlangıç'); pump(0.2)
app._st_set([{'type': 'startup', 'scope': 'hkcu-run', 'name': 'OneDrive', 'command': '"C:\\Users\\u\\OneDrive.exe" /background', 'enabled': True},
             {'type': 'startup', 'scope': 'hklm-run', 'name': 'OrnekTray', 'command': 'C:\\Program Files\\Ornek\\tray.exe', 'enabled': True},
             {'type': 'startup', 'scope': 'user-folder', 'name': 'Eski.lnk', 'command': 'C:\\Eski\\e.exe', 'enabled': False}])
check('st.render', app.st_count.get() == '3 öğe · 2 etkin' and app.st_tree.set('st2', 'state') == 'Devre dışı', app.st_count.get())
app.st_tree.selection_set(('st0', 'st1')); app.st_set('disable')
check('st.split_admin', len(captured) == 2 and not captured[0].admin and captured[1].admin and all(j.cmd[-1] == 'disable' for j in captured), [(j.title, j.admin) for j in captured])
app.start = real_start
shot('services')

# ---- 4.3 AI asistan (AI Manager): sahte istemciyle, ag yok
import care_ai as _ai
CALLS = []


def _fake_chat(self, messages, document='', max_tokens=2400):
    CALLS.append({'base': self.base, 'token': self.token, 'messages': messages, 'document': document})
    return {'text': '**Öneri:** OrnekTray güvenle kapatılabilir.', 'provider': 'OpenAI', 'model': 'gpt-test', 'truncated': False}


_ai.ManagerClient.chat = _fake_chat
app.tabs.select('AI asistan'); pump(0.2)
check('ai.page', app.tabs.tab(app.tabs.current, 'text') == 'AI asistan' and 'Bağlı değil' in app.ai_conn.get(), app.ai_conn.get())
app.ai_url.set('agfo.example'); app.ai_token.set('agfoed.5.abcd1234.' + 'A' * 40)
app._ai_test = lambda cfg: None
app.ai_save_test()
stored = json.loads((pathlib.Path(os.environ['LOCALAPPDATA']) / 'AGFO' / 'SystemCare' / 'settings.json').read_text(encoding='utf-8')).get('ai', {})
check('ai.saved_encrypted', stored.get('url') == 'https://agfo.example' and 'agfoed' not in json.dumps(stored) and app.ai_cfg['token'].startswith('agfoed.5.'), stored)
os.environ['USERNAME'] = 'ornekkul'
app.st_tree.selection_set(('st1',))
app.ai_ask_about('başlangıç öğeleri', app._st_sel(), ['name', 'enabled', 'scope', 'command'])
for _ in range(40):
    pump(0.05)
    if not app.ai_busy and CALLS:
        break
pump(0.3)
txt = app.ai_text.get('1.0', 'end')
check('ai.chat_roundtrip', CALLS and CALLS[0]['base'] == 'https://agfo.example' and 'OrnekTray' in CALLS[0]['document'] and 'Öneri: OrnekTray' in txt
      and '**' not in txt and 'gpt-test' in txt, (len(CALLS), txt[-300:]))
CALLS.clear()
app.ai_ask('Bu süreçler normal mi? ornekkul kullanıcısıyım', ('procs',))
for _ in range(40):
    pump(0.05)
    if not app.ai_busy and CALLS:
        break
check('ai.context_masked', CALLS and 'chrome' in CALLS[0]['document'] and '<kullanıcı>' in CALLS[0]['messages'][-1]['content']
      and len(CALLS[0]['messages']) == 3 and app.ai_ctx['procs'].get(), CALLS[0]['messages'] if CALLS else None)
check('ai.no_runner', not app.busy)
# 4.3.1: uygulanabilir oneriler — secilebilir liste, dogrulama, onayla uygulama
ACTS = [{'type': 'startup_disable', 'name': 'OrnekTray', 'risk': 'güvenli', 'why': 'gereksiz'},
        {'type': 'startup_disable', 'name': 'OneDrive', 'risk': 'dikkat', 'why': 'eşitleme'},
        {'type': 'startup_disable', 'name': 'Eski.lnk', 'risk': 'güvenli', 'why': 'x'},
        {'type': 'service_disabled', 'name': 'RpcSs', 'risk': 'güvenli', 'why': 'yanlış öneri'},
        {'type': 'service_manual', 'name': 'OrnekGuncelleme', 'risk': 'güvenli', 'why': 'gecikmeli'},
        {'type': 'process_end', 'name': 'chrome', 'risk': 'dikkat', 'why': 'bellek'},
        {'type': 'open_page', 'name': 'NVIDIA', 'risk': 'güvenli', 'why': 'sürücü'},
        {'type': 'startup_disable', 'name': 'Yok Boyle', 'risk': 'güvenli', 'why': 'x'}]


def _fake_chat2(self, messages, document='', max_tokens=4000, actions=True):
    CALLS.append({'messages': messages})
    return {'text': 'Önerilerim aşağıda.', 'actions': [dict(a) for a in ACTS], 'provider': 'OpenAI', 'model': 'gpt-test', 'truncated': False}


_ai.ManagerClient.chat = _fake_chat2
CALLS.clear()
app.ai_ask('Açılışı hızlandır', ('startup',))
for _ in range(60):
    pump(0.05)
    if not app.ai_busy and CALLS and app.ai_acts.labels:
        break
pump(0.2)
P = app.ai_acts.payload
rows = {P[i]['name']: P[i] for i in P}
check('ai.actions_listed', app.ai_actbox.winfo_manager() == 'pack' and len(P) == 8 and app.ai_act_count.get() == '8 öneri · 5 uygulanabilir', (app.ai_act_count.get(), len(P)))
check('ai.actions_validated', rows['OrnekTray']['ok'] and not rows['Eski.lnk']['ok'] and rows['Eski.lnk']['note'] == 'zaten devre dışı'
      and not rows['RpcSs']['ok'] and 'gerekli' in rows['RpcSs']['note'] and not rows['Yok Boyle']['ok'] and rows['chrome']['ok'] and rows['NVIDIA']['ok'],
      {k: (v['ok'], v['note']) for k, v in rows.items()})
checked = sorted(P[i]['name'] for i in app.ai_acts.checked)
check('ai.default_checked_safe_only', checked == ['NVIDIA', 'OrnekGuncelleme', 'OrnekTray'], checked)
captured = []
app.start = lambda jobs, quiet=False: captured.extend(jobs) or True
import tkinter.messagebox as _mb
_ask = _mb.askyesno
asked = []
sc_ai_mod = sys.modules['sc_ai']
sc_ai_mod.messagebox.askyesno = lambda t, m: asked.append(m) or True
app.ai_apply()
cmds = [(j.title, j.cmd[j.cmd.index('-Action') + 1] if '-Action' in j.cmd else '', j.admin) for j in captured]
st_items = _json.loads(_b64.b64decode(captured[0].cmd[captured[0].cmd.index('-ItemsB64') + 1])) if captured else []
check('ai.apply_jobs', len(captured) == 2 and captured[0].admin and st_items == [{'scope': 'hklm-run', 'name': 'OrnekTray'}]
      and 'svc-action' in captured[1].cmd and captured[1].cmd[-1] == 'manual' and asked and 'OrnekTray' in asked[0], (cmds, asked))
captured.clear(); asked.clear()
app.ai_acts.set_all(False); app.ai_acts.set_checked([i for i in P if P[i]['name'] == 'chrome'][0], True)
app.ai_apply()
kill = _json.loads(_b64.b64decode(captured[0].cmd[captured[0].cmd.index('-ItemsB64') + 1])) if captured else []
check('ai.apply_kill', kill == [{'pid': 4120, 'name': 'chrome'}] and captured[0].cmd[-1] == 'kill', kill)
sc_ai_mod.messagebox.askyesno = _ask
app.start = real_start
captured.clear()
shot('ai')

# ---- 4.4 Internet hizi + DNS yonetimi (sahte tarama kayitlari; PowerShell yok)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from net_fixture import NET_SCAN  # noqa: E402
import base64 as _b64x
app.tabs.select('İnternet hızı'); pump(0.2)
app._ns_render(NET_SCAN, [{'enabled': True}] * 3)
NP = app.ns_tree.payload
ids = {NP[i]['id']: i for i in NP}
check('ns.findings', {'dns', 'nic-Ethernet', 'do', 'ping-internet', 'startup', 'procs', 'wu'} <= set(ids) and 'uygulanabilir' in app.ns_state.get(), list(ids))
check('ns.default_checked', sorted(NP[i]['id'] for i in app.ns_tree.checked) == ['dns', 'do'])
app.ns_tree.tree.selection_set((ids['dns'],)); pump(0.1)
check('ns.detail', 'Test (ortanca' in app.ns_detail.get('1.0', 'end'))
runs, started = [], []
real_tw, real_start2 = app._tw_run, app.start
app._tw_run = lambda plan, title, rp=False, undo_sid=None, after=None: runs.append((plan, title, after))
app.start = lambda jobs, quiet=False: started.extend(jobs) or True
import tkinter.messagebox as _mbx
_ask2 = _mbx.askyesno
sys.modules['sc_netopt'].messagebox.askyesno = lambda *a, **k: True
app.ns_tree.set_checked(ids['nic-Ethernet'], True)
app.ns_apply()
plan, title, after = runs[0] if runs else ([], '', None)
dns_ops = [o for o in plan if o.get('t') == 'dns']
check('ns.apply_plan', dns_ops and dns_ops[0]['alias'] == 'Ethernet' and dns_ops[0]['servers'] == ['1.1.1.1', '1.0.0.1']
      and any(o.get('item') == 'tweak-delivery-opt' for o in plan) and [o['ref'] for o in plan] == list(range(len(plan)))
      and not m.tweaks.validate_ops(plan) and 'İnternet hızı' in title, (plan, title))
check('ns.nic_after_tweaks', after is not None and not started)
if after:
    after()
nic = started[0] if started else None
check('ns.nic_job', nic is not None and nic.admin and 'nic-speed-set' in nic.cmd
      and json.loads(_b64x.b64decode(nic.cmd[nic.cmd.index('-ItemsB64') + 1])) == [{'alias': 'Ethernet', 'value': '0'}])
runs.clear(); started.clear()
shot('netspeed')
# DNS yonetimi
app.tabs.select('DNS yönetimi'); pump(0.2)
app.dn_adapters = [{'type': 'dns-adapter', 'alias': 'Ethernet', 'guid': '{A}', 'desc': 'Realtek', 'servers': [], 'current': ['192.168.1.1']}]
app.dn_tree.clear(); app.dn_tree.add('d0', 'Ethernet', values=('otomatik (DHCP)', '192.168.1.1', 'Realtek'), payload=app.dn_adapters[0], checked=True)
app._dn_render_bench([r for r in NET_SCAN if r['type'] == 'dns-probe'])
check('dns.bench_best', app.dn_choice.get() == 'Cloudflare 1.1.1.1' and 'En hızlı' in app.dn_state.get()
      and len(app.dn_btree.payload) == 4)
app.dn_apply()
check('dns.apply', runs and runs[0][0][0]['servers'] == ['1.1.1.1', '1.0.0.1'] and runs[0][0][0]['alias'] == 'Ethernet' and runs[0][2] is not None, runs)
runs.clear()
app.dn_apply(dhcp=True)
check('dns.dhcp', runs and runs[0][0][0]['servers'] == [] and 'DHCP' in runs[0][1])
sys.modules['sc_netopt'].messagebox.askyesno = _ask2
app._tw_run, app.start = real_tw, real_start2
shot('dns')

check('busy_free', not app.busy)
app.destroy()
fails = [n for n, ok in RESULTS if not ok]
print('%s gui-nav (%s): %d/%d' % ('PASS' if not fails else 'FAIL', MODE, len(RESULTS) - len(fails), len(RESULTS)))
sys.exit(1 if fails else 0)
