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
check('busy_free', not app.busy)
app.destroy()
fails = [n for n, ok in RESULTS if not ok]
print('%s gui-nav (%s): %d/%d' % ('PASS' if not fails else 'FAIL', MODE, len(RESULTS) - len(fails), len(RESULTS)))
sys.exit(1 if fails else 0)
