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
                              'Programlar', 'Uygulama güncellemeleri', 'Uygulama kur', 'Kol / Gamepad'], titles)
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
check('busy_free', not app.busy)
app.destroy()
fails = [n for n, ok in RESULTS if not ok]
print('%s gui-nav (%s): %d/%d' % ('PASS' if not fails else 'FAIL', MODE, len(RESULTS) - len(fails), len(RESULTS)))
sys.exit(1 if fails else 0)
