"""SuperTools GitHub tek tik guncelleme - Xvfb GUI testi (sahte GitHub; gercek create_update + agfo_updater dogrulamasi).
Kullanim: DISPLAY=:99 python tests/test_github_update_gui.py <supertools klasoru> <gecici klasor>"""
import hashlib, io, os, pathlib, shutil, subprocess, sys, time

ROOT, TMP = pathlib.Path(sys.argv[1]).resolve(), pathlib.Path(sys.argv[2]).resolve()
os.environ['LOCALAPPDATA'] = str(TMP / 'la')
sys.path.insert(0, str(ROOT))
import importlib.machinery, importlib.util  # noqa: E402
import scanner_core as core  # noqa: E402
import agfo_updater as updater  # noqa: E402
import agfo_github_update as ghu  # noqa: E402

RESULTS = []


def check(name, cond, detail=''):
    RESULTS.append((name, bool(cond)))
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' - ' + str(detail)[:400]), flush=True)


# 1.7.1 guncelleme paketi: kaynak kopyasinda surum yukseltilir, uygulamanin kendi create_update araci ile paketlenir
src = TMP / 'src171'
shutil.rmtree(src, ignore_errors=True)
shutil.copytree(ROOT, src, ignore=shutil.ignore_patterns('__pycache__', 'tests'))
sc = (src / 'scanner_core.py').read_text(encoding='utf-8').replace('APP_VERSION = "%s"' % core.APP_VERSION, 'APP_VERSION = "1.7.1"')
(src / 'scanner_core.py').write_text(sc, encoding='utf-8')
pkg = TMP / 'AGFO-SuperTools-v1.7.1.update.zip'
subprocess.run([sys.executable, '-I', str(src / 'packaging' / 'create_update.py'), '--source', str(src), '--output', str(pkg), '--notes', 'Test surumu'], check=True,
               cwd=str(src), stdout=subprocess.DEVNULL)
check('pkg.built_and_valid', updater.inspect_package(pkg, core.APP_VERSION)['version'] == '1.7.1')
check('pkg.contains_github_module', 'agfo_github_update.py' in updater.inspect_package(pkg)['files'])
DATA = pkg.read_bytes()
REL = [{'tag_name': 'supertools-v1.7.1', 'name': 'SuperTools 1.7.1', 'draft': False, 'prerelease': False, 'body': 'Duzeltmeler',
        'html_url': 'https://github.com/downtownck/agfo-windows-apps/releases/tag/supertools-v1.7.1', 'published_at': '2026-10-18T10:00:00Z',
        'assets': [{'name': pkg.name, 'size': len(DATA), 'digest': 'sha256:' + hashlib.sha256(DATA).hexdigest(),
                    'browser_download_url': 'https://github.com/downtownck/agfo-windows-apps/releases/download/supertools-v1.7.1/' + pkg.name}]},
       {'tag_name': 'system-care-v9.9.9', 'draft': False, 'prerelease': False, 'assets': []}]
ghu.fetch_json = lambda url, user_agent='': REL


class R(io.BytesIO):
    def __init__(self, b):
        super().__init__(b); self.headers = {'Content-Length': str(len(b))}
    def __enter__(self): return self
    def __exit__(self, *x): return False


ghu._open = lambda url, **k: R(DATA)

spec = importlib.util.spec_from_file_location('st_app', ROOT / 'app.pyw', loader=importlib.machinery.SourceFileLoader('st_app', str(ROOT / 'app.pyw')))
appmod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(appmod)
asked, launched = [], []
appmod.messagebox.askyesno = lambda *a, **k: (asked.append(a[0]) or True)
appmod.messagebox.showerror = lambda *a, **k: asked.append(('error',) + a)
appmod.messagebox.showinfo = lambda *a, **k: None
app = appmod.ScannerApp()
app._ready_for_update = lambda: True
app._launch_update_runner = lambda action, value: launched.append((action, pathlib.Path(value)))


def pump(sec):
    t0 = time.time()
    while time.time() - t0 < sec:
        app.update(); time.sleep(0.03)


pump(1.0)
check('ui.title_version', '1.7.0' in app.title(), app.title())
# acilista otomatik denetim (4 sn sonra) -> istem penceresi
pump(5.5)
check('auto.check_found', app.gh_result and app.gh_result['version'] == '1.7.1', app.gh_status_var.get())
check('auto.prompt_window', getattr(app, '_gh_prompt_win', None) is not None and app._gh_prompt_win.winfo_exists())
check('ui.button_enabled', str(app.gh_update_btn['state']) == 'normal')
app._gh_prompt_win.destroy()
# bozuk indirme reddedilir
ghu._open = lambda url, **k: R(DATA[:-5] + b'xxxxx')
app._gh_update(confirm=False); pump(2.0)
check('dl.bad_rejected', not launched and 'indirilemedi' in app.gh_status_var.get() and any(isinstance(x, tuple) and x[0] == 'error' for x in asked), app.gh_status_var.get())
ghu._open = lambda url, **k: R(DATA)
app._gh_update(confirm=True); pump(2.5)
check('dl.confirm_asked', 'AGFO güncellemesi' in asked)
check('dl.handed_to_updater', len(launched) == 1 and launched[0][0] == '--apply' and launched[0][1].is_file(), launched)
if launched:
    check('dl.staged_verified', updater.inspect_package(launched[0][1], core.APP_VERSION)['version'] == '1.7.1')
check('dl.download_cleaned', not any((updater.data_folder() / 'updates' / 'download').glob('*')))
# atla
ghu.skip_version(appmod.gh_state_path(), '1.7.1')
r = ghu.check_for_update(appmod.GH_PREFIX, core.APP_VERSION, appmod.gh_state_path(), appmod.GH_ASSET, releases=REL, now=time.time() + 10 ** 6)
check('skip.respected', r['status'] == 'skipped', r)
# gercek agfo_updater ile uctan uca uygulama (gecici kurulum koku)
inst = TMP / 'install'
shutil.rmtree(inst, ignore_errors=True)
shutil.copytree(ROOT, inst, ignore=shutil.ignore_patterns('__pycache__', 'tests', 'packaging', '*.cmd', '*.md'))
res = updater.perform_update(launched[0][1], inst, TMP / 'home')
check('apply.real_updater', res['before'] == '1.7.0' and res['after'] == '1.7.1' and updater.current_version(inst) == '1.7.1', res)
app.destroy()
fails = [n for n, ok in RESULTS if not ok]
print('\nSuperTools GitHub GUI: %d pass, %d fail' % (len(RESULTS) - len(fails), len(fails)))
sys.exit(1 if fails else 0)
