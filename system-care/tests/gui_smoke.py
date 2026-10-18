"""GUI duman testi: gercek Tk penceresi (Xvfb), sahte motorlar, gercek pwsh ile care_tasks.ps1.
Kullanim: python3.12 gui_smoke.py <agfo-care klasoru> <fake bin klasoru> <ekran goruntusu klasoru>"""
import os
import pathlib
import subprocess
import sys
import time

ROOT, FAKE, SHOTS = map(pathlib.Path, sys.argv[1:4])
SHOTS.mkdir(parents=True, exist_ok=True)
os.environ['PATH'] = str(FAKE) + os.pathsep + os.environ['PATH']
sys.path.insert(0, str(ROOT))

import importlib.machinery, importlib.util  # noqa: E402
import care_core as core  # noqa: E402

FAKE_ENGINES = {'winget': {'path': str(FAKE / 'winget')},
                'bleachbit': {'path': str(FAKE / 'bleachbit_console'), 'version': '4.6.2.0'},
                'bcu': {'path': None, 'console': str(FAKE / 'BCU-console'), 'version': '6.3.0.0'},
                'sdio': {'path': str(FAKE / 'SDIO_x64_R888'), 'version': 'R888'}}
TMP = pathlib.Path(os.environ['AGFO_TEST_TMP'])
core.ENGINE_DIR = TMP / 'engines'
BB_PRESENT = {'v': False}


def fake_status(settings=None):
    st = {k: dict(v) for k, v in FAKE_ENGINES.items()}
    real = core.find_bleachbit()          # gercek motor klasoru aramasi
    BB_PRESENT['v'] = bool(real)
    if not real:
        st['bleachbit'] = {'path': None, 'version': '', 'source': ''}
    else:
        st['bleachbit']['source'] = 'AGFO motor klasörü (taşınabilir)'   # zip'ten cikan dosya calistirilamaz; sahte konsol kullanilir
    return st


core.engine_status = fake_status
# Sahte HTTPS: resmi BleachBit sayfasi + tasinabilir ZIP (gercek download()/safe_extract() kodu calisir)
import io, zipfile  # noqa: E402
_zb = io.BytesIO()
with zipfile.ZipFile(_zb, 'w') as _z:
    _z.writestr('BleachBit-Portable/bleachbit_console.exe', 'x'); _z.writestr('BleachBit-Portable/BleachBit.ini', '[Portable]')
ZIP_BYTES = _zb.getvalue()
HTTP_LOG = []


class _Resp(io.BytesIO):
    def __init__(self, b):
        super().__init__(b); self.headers = {'Content-Length': str(len(b))}
    def __enter__(self): return self
    def __exit__(self, *a): return False


def fake_request(url, allowed, accept=None):
    assert core.host_allowed(url, allowed), url
    HTTP_LOG.append(url)
    if url == core.BLEACHBIT_PAGE:
        return _Resp(b'<a href="https://download.bleachbit.org/get/BleachBit-6.0.4-portable.zip">Portable</a>')
    if url == 'https://download.bleachbit.org/get/BleachBit-6.0.4-portable.zip':
        return _Resp(b'<!DOCTYPE html><html>The download will start in a moment.</html>')   # gercek sunucu davranisi
    if url == core.bleachbit_sums_url('6.0.4'):
        import hashlib
        return _Resp(('%s  BleachBit-6.0.4-portable.zip\n' % hashlib.sha256(ZIP_BYTES).hexdigest()).encode())
    if url == 'https://download.bleachbit.org/BleachBit-6.0.4-portable.zip':
        return _Resp(ZIP_BYTES)
    raise OSError('beklenmeyen adres ' + url)


core._request = fake_request
left = TMP / 'leftover' / 'Acme Tool'
left.mkdir(parents=True, exist_ok=True)
PROGS = [
    {'name': 'Acme Tool', 'version': '2.1', 'publisher': 'Acme', 'date': '2026-10-01', 'size_kb': 20480, 'uninstall': '"C:\\A\\unins000.exe"',
     'quiet': '"C:\\A\\unins000.exe" /VERYSILENT', 'location': str(left), 'msi': False, 'product_code': '', 'hive': 'HKLM', 'view': 0,
     'key': 'SOFTWARE\\x\\Acme', 'scope': 'Makine', 'icon': ''},
    {'name': 'Ghost App', 'version': '1.0', 'publisher': 'Nobody', 'date': '', 'size_kb': 0, 'uninstall': '"C:\\gone\\u.exe"', 'quiet': '',
     'location': '', 'msi': False, 'product_code': '', 'hive': 'HKCU', 'view': 0, 'key': 'SOFTWARE\\x\\Ghost', 'scope': 'Kullanici', 'icon': ''},
    {'name': 'McAfee WebAdvisor', 'version': '4.1', 'publisher': 'McAfee, LLC', 'date': '2024-05-05', 'size_kb': 40000, 'uninstall': '"C:\\MW\\uninstall.exe"',
     'quiet': '"C:\\MW\\uninstall.exe" /s', 'location': '', 'msi': False, 'product_code': '', 'hive': 'HKLM', 'view': 0, 'key': 'k4', 'scope': 'Makine', 'icon': ''},
    {'name': 'Zeta MSI', 'version': '5.0', 'publisher': 'Zeta', 'date': '2025-01-01', 'size_kb': 900000, 'uninstall': 'MsiExec.exe /X{11111111-2222-3333-4444-555555555555}',
     'quiet': '', 'location': '', 'msi': True, 'product_code': '{11111111-2222-3333-4444-555555555555}', 'hive': 'HKLM', 'view': 0, 'key': 'k3', 'scope': 'Makine', 'icon': ''},
]
STATE = {'installed': {'Acme Tool', 'Ghost App', 'Zeta MSI', 'McAfee WebAdvisor'}}


def fake_read_programs():
    import copy
    return [copy.deepcopy(p) for p in PROGS if p['name'] in STATE['installed']]


core.read_programs = fake_read_programs
core.uninstaller_exists = (lambda cmd, exists=None: 'gone' not in cmd)
_launched = []


def fake_shell_execute(exe, params='', verb=None, cwd=None, show=1):
    _launched.append((exe, params))
    return subprocess.Popen(['sh', '-c', 'sleep 0.3'])


def fake_wait(handle, should_stop=lambda: False):
    code = handle.wait()
    STATE['installed'].discard('Acme Tool')
    return code


core.shell_execute = fake_shell_execute
core.wait_handle = fake_wait
core.registry_key_exists = lambda p: p['name'] in STATE['installed']
core.running_uninstall_helpers = lambda: []
_orig_left = core.leftover_candidates
core.leftover_candidates = lambda p, rem, **kw: [str(left)] if p['name'] == 'Acme Tool' else []

spec = importlib.util.spec_from_file_location('agfo_app', ROOT / 'app.pyw', loader=importlib.machinery.SourceFileLoader('agfo_app', str(ROOT / 'app.pyw')))
app_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_mod)
mb = app_mod.messagebox
ASKED = []
mb.askyesno = lambda title, msg, **k: (ASKED.append(title) or True)
mb.showinfo = lambda *a, **k: ASKED.append(('info',) + a)
mb.showerror = lambda *a, **k: ASKED.append(('error',) + a)
app_mod.filedialog.askdirectory = lambda **k: str(TMP / 'backup')

app = app_mod.App()
app.admin = True
RESULTS = []


def check(name, cond, detail=''):
    RESULTS.append((name, bool(cond), detail))
    print(('PASS ' if cond else 'FAIL ') + name + ((' - ' + str(detail)) if not cond else ''), flush=True)


def wait_idle(timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        app.update()
        if not app.busy and not app.pending and app.messages.empty():
            for _ in range(5):
                app.update(); time.sleep(0.02)
            if not app.busy:
                return True
        time.sleep(0.03)
    return False


def shot(tab_index, name):
    app.tabs.select(tab_index)
    for _ in range(10):
        app.update(); time.sleep(0.03)
    wid = app.winfo_id()
    subprocess.run(['import', '-window', 'root', '-crop', '%dx%d+%d+%d' % (app.winfo_width(), app.winfo_height(), app.winfo_rootx(), app.winfo_rooty()),
                    str(SHOTS / (name + '.png'))], check=False)


def logtext():
    return app.log.get('1.0', 'end')


app.geometry('1220x860+0+0')
for _ in range(20):
    app.update(); time.sleep(0.03)
wait_idle()
# 1 Motorlar
t = app.eng_tree
check('engines.rows', set(t.labels) == {'winget', 'bleachbit', 'bcu', 'sdio'}, list(t.labels))
check('engines.bb_missing_initially', t.tree.set('bleachbit', 'state') == 'Kurulu değil', t.tree.set('bleachbit', 'state'))
app.engine_op('install-missing'); wait_idle(60)
check('engines.bb_portable_installed', BB_PRESENT['v'] and t.tree.set('bleachbit', 'state') == 'Kurulu'
      and 'taşınabilir' in t.tree.set('bleachbit', 'src'), (t.tree.item('bleachbit', 'values'), logtext()[-800:]))
check('engines.bb_no_winget_needed', 'winget install --id BleachBit' not in logtext() and HTTP_LOG[:3] == [core.BLEACHBIT_PAGE, core.bleachbit_sums_url('6.0.4'), 'https://download.bleachbit.org/BleachBit-6.0.4-portable.zip']
      and 'yayıncı özetiyle doğrulandı' in logtext(), HTTP_LOG)
check('engines.bb_path_in_engine_dir', str(core.ENGINE_DIR / 'BleachBit') in (core.find_bleachbit() or ''), core.find_bleachbit())
# Tasinabilir paket ulasilamazsa WinGet'e duser
core.install_portable_orig = core.install_portable
core.install_portable = lambda *a, **k: (_ for _ in ()).throw(OSError('ağ yok'))
import shutil  # noqa: E402
shutil.rmtree(core.ENGINE_DIR / 'BleachBit', ignore_errors=True)
app.refresh_engines(); wait_idle()
t.set_checked('bleachbit', True)
app.engine_op('install'); wait_idle(60)
check('engines.bb_fallback_winget', 'Taşınabilir kurulum olmadı: ağ yok' in logtext() and 'winget install --id BleachBit.BleachBit' in logtext()
      and '--override /S /allusers' in logtext() and 'çalıştırılabilir dosya bulunamadı' in logtext() and 'KURULAMADI' in logtext(), logtext()[-900:])
# Kullanicinin gordugu durum: WinGet 0x8A15002B ('uygulanabilir guncelleme yok') = BleachBit zaten kurulu.
REG_FOUND = {'v': False}
_fs = core.engine_status


def status_with_registry(settings=None):
    st = _fs(settings)
    if REG_FOUND['v']:
        st['bleachbit'] = {'path': str(FAKE / 'bleachbit_console'), 'version': '6.0.4.0', 'source': 'Sistem kurulumu'}
    return st


core.engine_status = status_with_registry
_orig_run_cmd = app_mod.Runner.run_cmd
app_mod.Runner.run_cmd = lambda self, title, cmd, show_output=True: (-1978335189, [])   # Linux'ta 32 bit cikis kodu uretilemez
core.install_portable = lambda *a, **k: (_ for _ in ()).throw(OSError('File is not a zip file'))
app.refresh_engines(); wait_idle()
t.set_checked('bleachbit', True)
app.engine_op('install'); wait_idle(30)
check('engines.already_installed_not_found_explained', 'paketi kurulu sayıyor ama çalıştırılabilir dosya bulunamadı' in logtext() and 'uygulanabilir güncelleme yok' not in logtext().split('KURULAMADI')[-1], logtext()[-700:])
REG_FOUND['v'] = True
t.set_checked('bleachbit', True)
app.engine_op('install'); wait_idle(30)
check('engines.already_installed_used', 'Zaten kurulu, kullanılıyor' in logtext() and t.tree.set('bleachbit', 'state') == 'Kurulu', logtext()[-500:])
REG_FOUND['v'] = False
app_mod.Runner.run_cmd = _orig_run_cmd
core.engine_status = _fs
core.install_portable = core.install_portable_orig
app.refresh_engines(); wait_idle()
app.engine_op('install-missing'); wait_idle(60)
check('engines.bb_reinstalled_portable', t.tree.set('bleachbit', 'state') == 'Kurulu', t.tree.item('bleachbit', 'values'))
t.set_checked('bleachbit', False)
check('engines.no_web', 'webbrowser' not in (ROOT / 'app.pyw').read_text() and 'webbrowser' not in (ROOT / 'care_core.py').read_text())
shot(0, '1-motorlar')
# engine install flow (winget fake) -> refresh chained
t.set_checked('sdio', True)
app.engine_op('install')
wait_idle()
check('engines.install_chain', 'Güncelle: Snappy Driver Installer Origin' in logtext() and 'Motor durumu' in logtext().split('Güncelle: Snappy')[-1], logtext()[-600:])

# 2 Temizlik
app.bb_load(); wait_idle()
bt = app.bb_tree
check('bb.loaded', 'o:system.tmp' in bt.labels and 'c:google_chrome' in bt.labels, len(bt.labels))
check('bb.default_safe', 'o:system.tmp' in bt.checked and 'o:google_chrome.cache' in bt.checked and 'o:google_chrome.passwords' not in bt.checked
      and 'o:system.free_disk_space' not in bt.checked, sorted(bt.checked))
bt.toggle('c:google_chrome')
check('bb.group_toggle', all(k in bt.checked for k in bt.tree.get_children('c:google_chrome')))
app.bb_preset()
check('bb.preset_resets', 'o:google_chrome.passwords' not in bt.checked and 'o:google_chrome.cache' in bt.checked)
app.bb_run('preview'); wait_idle()
check('bb.preview_args', '--preview' in logtext() and 'Disk space to be recovered' in app.bb_summary.get(), app.bb_summary.get())
check('bb.preview_selected_only', 'ARGS: --preview' in logtext() and 'passwords' not in logtext().split('ARGS: --preview')[-1].split('\n')[0], logtext()[-400:])
shot(1, '2-temizlik')
app.bb_run('clean'); wait_idle()
check('bb.clean_confirm', 'Temizliği onaylayın' in ASKED and 'ARGS: --clean' in logtext())

# 3 Programlar
app.prog_scan(); wait_idle()
pt = app.prog_tree
check('prog.loaded', len(pt.labels) == 4, len(pt.labels))
ghost = [i for i in pt.labels if pt.payload[i]['name'] == 'Ghost App'][0]
check('prog.orphan_tag', 'orphan' in pt.tree.item(ghost, 'tags'))
app.prog_q.set('zeta'); app.update()
check('prog.search', [pt.payload[i]['name'] for i in pt.labels] == ['Zeta MSI'])
app.prog_q.set(''); app.prog_filter.set('Yetim kayıtlar'); app._prog_render()
check('prog.filter_orphan', [pt.payload[i]['name'] for i in pt.labels] == ['Ghost App'])
app.prog_filter.set('Bilinen bloatware'); app._prog_render()
check('prog.filter_bloat', [pt.payload[i]['name'] for i in pt.labels] == ['McAfee WebAdvisor'], [pt.payload[i]['name'] for i in pt.labels])
app.prog_filter.set('Tümü'); app._prog_render()
pt.sort('size')
check('prog.sort_size', [pt.payload[i]['name'] for i in pt.tree.get_children('')][0] == 'Ghost App')
shot(2, '3-programlar')
acme = [i for i in pt.labels if pt.payload[i]['name'] == 'Acme Tool'][0]
pt.set_checked(acme, True); pt.set_checked([i for i in pt.labels if pt.payload[i]['name'] == 'Ghost App'][0], True)
app.prog_uninstall()
# chain: uninstall -> rescan -> leftover dialog
t0 = time.time()
dlg = None
while time.time() - t0 < 20:
    app.update(); time.sleep(0.05)
    tops = [w for w in app.winfo_children() if w.winfo_class() == 'Toplevel']
    if tops:
        dlg = tops[0]; break
check('prog.uninstall_quiet', _launched and _launched[0] == ('C:\\A\\unins000.exe', '/VERYSILENT'), _launched)
check('prog.orphan_skipped', 'yetim kayıt atlandı' in logtext())
check('prog.rescan_after', len(app.programs) == 3, [p['name'] for p in app.programs])
check('prog.leftover_dialog', dlg is not None)
if dlg:
    subprocess.run(['import', '-window', 'root', str(SHOTS / '3b-artiklar.png')], check=False)
    go = [w for w in dlg.winfo_children() if isinstance(w, app_mod.tk.Frame)][-1].winfo_children()[0]
    go.invoke(); wait_idle(90)
    check('prog.recycle_called', 'recycle-paths' in logtext() or 'Geri Dönüşüm' in logtext(), logtext()[-500:])

# 3c Bloatware
_launched.clear()
app.bloat_scan(); wait_idle(30)
bl = app.bloat_tree
def rows(cat): return [bl.payload[i]['name'] for i in bl.tree.get_children('g:' + cat)] if bl.tree.exists('g:' + cat) else []
check('bloat.groups', rows('rec') == ['king.com.CandyCrushSaga', 'Microsoft.BingNews', 'McAfee WebAdvisor'] and rows('caution') == ['Microsoft.GamingApp'], (rows('rec'), rows('caution')))
check('bloat.chips', [app.bloat_chips[k][0].get() for k in ('rec', 'caution', 'other', 'protected')] == ['3 önerilen', '1 dikkat', '1 diğer', '2 korunan'],
      [v.get() for v, _ in app.bloat_chips.values()])
check('bloat.default_rec_checked', all(i in bl.checked for i in bl.tree.get_children('g:rec')) and not any(i in bl.checked for i in bl.tree.get_children('g:caution')))
check('bloat.protected_hidden_default', not bl.tree.exists('g:protected'))
app.bloat_filter.set('Tümü (korunanlar dahil)'); app._bloat_render()
prot = bl.tree.get_children('g:protected')
check('bloat.protected_not_checkable', len(prot) == 2 and not bl.labels['g:protected'][1] and all(not bl.labels[i][1] for i in prot))
bl.toggle('g:protected'); bl.set_all(True)
check('bloat.protected_never_selected', not any(i in bl.checked for i in prot))
bl.set_all(False); app.bloat_filter.set('Önerilen ve dikkat'); app._bloat_render()
check('bloat.selection_kept_over_filter', app.bloat_count.get() == '', app.bloat_count.get())
app.bloat_tree.set_all(True, lambda i: (bl.payload.get(i) or {}).get('cat') == 'rec')
news = [i for i in bl.tree.get_children('g:rec') if bl.payload[i]['name'] == 'Microsoft.BingNews'][0]
bl.set_checked(news, False)
app.bloat_q.set('candy'); app.update()
check('bloat.search', [bl.labels[i][0] for i in bl.tree.get_children('g:rec')] == ['King oyunları (Candy Crush vb.)'])
app.bloat_q.set(''); app.update()
check('bloat.selection_kept_over_search', app.bloat_count.get() == '2 seçili', app.bloat_count.get())
shot(3, '3c-bloatware')
app.bloat_prov.set(True)
ASKED.clear()
app.bloat_remove(); wait_idle(40)
lt = logtext()
pk = lt.split('PACKAGES=')[-1].split('\n')[0]
check('bloat.remove_only_checked_appx', pk == 'king.com.CandyCrushSaga_1.2_x86__kgqvnymyfvs32', pk)
check('bloat.provisioned_flag', 'PROVISIONED=yes' in lt, lt[-400:])
check('bloat.restore_point_first', lt.rfind('Geri yükleme noktası başlatıldı') < lt.rfind('Store uygulamalarını kaldır'), lt[-800:])
check('bloat.win32_uninstaller', ('C:\\MW\\uninstall.exe', '/s') in _launched, _launched)
check('bloat.confirmed', 'Bloatware kaldırma' in ASKED)
check('bloat.rescan_after', lt.rfind('Masaüstü bloatware taraması başlatıldı') > lt.rfind('Kaldır: McAfee WebAdvisor'))

# 4 Surucu Merkezi
app.drv_scan(); wait_idle(30)
dt = app.drv_tree
names = {dt.labels[i][0]: i for i in dt.labels}
check('drv.chips', app.drv_chips['updates'][0].get() == '2 güncelleme' and app.drv_chips['missing'][0].get() == '1 eksik sürücü'
      and app.drv_chips['problem'][0].get() == '1 sorunlu' and app.drv_chips['devices'][0].get() == '5 aygıt', [v.get() for v, _ in app.drv_chips.values()])
net = names.get('Intel(R) Ethernet I219-V')
check('drv.device_row', net and dt.tree.set(net, 'status') == 'Güncelleme var' and dt.tree.set(net, 'cur') == '12.19.1.37' and dt.tree.set(net, 'new') == '12.19.2.45'
      and 'st_new' in dt.tree.item(net, 'tags'), net and dt.tree.item(net, 'values'))
kids = dt.tree.get_children(net) if net else ()
check('drv.candidates_like_sdio', len(kids) == 3 and [dt.tree.set(k, 'status') for k in kids] == ['Daha yeni sürüm', 'Daha eski sürüm', 'Daha zayıf eşleşme (genel uyumlu sürücü)'],
      [dt.tree.set(k, 'status') for k in kids])
check('drv.default_checked_recommended', kids and kids[0] in dt.checked and kids[1] not in dt.checked and kids[2] not in dt.checked)
unk = names.get('Bilinmeyen aygıt')
check('drv.missing_device', unk and dt.tree.set(unk, 'status').startswith('Sürücü eksik') and dt.tree.get_children(unk)[0] in dt.checked)
check('drv.filter_default_hides_ok', 'HID uyumlu fare' not in names and 'Sensör' in names, list(names))
check('drv.unmatched_group', 'u' in dt.labels and len(dt.tree.get_children('u')) == 1)
check('drv.count_label', app.drv_count.get().startswith('2 sürücü seçili'), app.drv_count.get())
dt.tree.selection_set(net); app.update()
det = app.drv_detail.get('1.0', 'end')
check('drv.details_device', 'Kurulu sürücü' in det and 'PCI\\VEN_8086&DEV_15BC' in det and 'oem12.inf' in det, det[:300])
dt.tree.selection_set(kids[0]); app.update()
det = app.drv_detail.get('1.0', 'end')
check('drv.details_candidate', 'Daha yeni sürüm' in det and 'Şu an kurulu' in det and '12.19.1.37' in det, det[:300])
app.drv_filter.set('Tüm aygıtlar'); app._drv_render()
names2 = {dt.labels[i][0] for i in dt.labels}
check('drv.filter_all', 'HID uyumlu fare' in names2)
check('drv.selection_kept_over_filter', app.drv_count.get().startswith('2 sürücü seçili'), app.drv_count.get())
app.drv_q.set('realtek'); app.update()
check('drv.search', {dt.labels[i][0] for i in dt.tree.get_children('')} == {'Bilinmeyen aygıt'}, [dt.labels[i][0] for i in dt.tree.get_children('')])
app.drv_q.set(''); app.drv_filter.set('Güncellemeler ve sorunlar'); app._drv_render()
shot(4, '4-surucu-merkezi')
app.drv_install(); wait_idle(30)
lt = logtext()
check('drv.restore_point_first', lt.rfind('Geri yükleme noktası başlatıldı') < lt.rfind('Seçili sürücüleri kur başlatıldı'), lt[-900:])
ids = lt.split('UPDATEIDS=')[-1].split('\n')[0]
check('drv.install_only_checked', set(ids.split(',')) == {'wu-intel-new', 'wu-realtek'}, ids)
check('drv.rescan_after_install', lt.rfind('Sürücü analizi başlatıldı') > lt.rfind('Seçili sürücüleri kur başlatıldı'))
app.sdio_cat['newer'].set(False)
app.sdio_run('scan'); wait_idle(30)
check('sdio.scan_tail', 'SDIO | AGFO: aygitlar taraniyor' in logtext() or 'SDIO | ' in logtext(), logtext()[-600:])
scr = core.sdio_dirs()['root'] / 'agfo-scan.txt'
check('sdio.script_written', scr.is_file() and 'select missing better' in scr.read_text() and 'enableinstall off' in scr.read_text())
app.sdio_run('install'); wait_idle(30)
ins = (core.sdio_dirs()['root'] / 'agfo-install.txt').read_text()
check('sdio.install_script', 'restorepoint' in ins and 'select missing better' in ins and '\ninstall\n' in ins)


# 4b Aygit temizligi
app.ph_scan(); wait_idle(30)
pht = app.ph_tree
ph_rows = {pht.labels[i][0]: i for i in pht.labels if pht.payload.get(i)}
check('ph.rows', set(ph_rows) == {'SanDisk Ultra USB Device', 'Galaxy S10', 'USB Serial Port (COM7)', 'HP LaserJet (eski)'}, list(ph_rows))
check('ph.chips', app.ph_chips['total'][0].get() == '4 bağlı olmayan aygıt' and app.ph_chips['caution'][0].get() == '1 dikkat', [v.get() for v, _ in app.ph_chips.values()])
check('ph.default_old_selected', ph_rows['SanDisk Ultra USB Device'] in pht.checked and ph_rows['USB Serial Port (COM7)'] in pht.checked
      and ph_rows['Galaxy S10'] not in pht.checked and ph_rows['HP LaserJet (eski)'] not in pht.checked)
check('ph.caution_tag', 'risky' in pht.tree.item(ph_rows['HP LaserJet (eski)'], 'tags'))
app.ph_filter.set('1 yıldan eski'); app._ph_render()
names_old = {pht.labels[i][0] for i in pht.labels if pht.payload.get(i)}
check('ph.filter_year', names_old == {'SanDisk Ultra USB Device', 'USB Serial Port (COM7)', 'HP LaserJet (eski)'}, names_old)
app.ph_filter.set('Tümü'); app._ph_render()
check('ph.selection_kept', app.ph_count.get() == '2 aygıt seçili', app.ph_count.get())
app.ph_q.set('com7'); app.update()
check('ph.search', [pht.labels[i][0] for i in pht.labels if pht.payload.get(i)] == ['USB Serial Port (COM7)'])
app.ph_q.set(''); app.update()
shot(5, '4b-aygit-temizligi')
app.ph_remove(); wait_idle(30)
lt = logtext()
ids = lt.split('INSTANCEIDS=')[-1].split('\n')[0].split('|')
check('ph.remove_only_checked', set(ids) == {'USBSTOR\\DISK&VEN_SANDISK&PROD_ULTRA\\4C53', 'FTDIBUS\\VID_0403+PID_6001\\0000'}, ids)
check('ph.force_restore_point_first', 'FORCE=yes' in lt and lt.rfind('Geri yükleme noktası başlatıldı') < lt.rfind('Bağlı olmayan aygıtları kaldır'), lt[-600:])
check('ph.rescan_after', lt.rfind('Bağlı olmayan aygıtlar başlatıldı') > lt.rfind('Bağlı olmayan aygıtları kaldır'))

# 5 Uygulamalar
app.apps_scan(); wait_idle()
at = app.app_tree
check('apps.rows', [at.payload[i]['id'] for i in at.labels] == ['Mozilla.Firefox', '7zip.7zip'], [at.payload[i]['id'] for i in at.labels])
at.set_checked(list(at.labels)[1], False)
app.apps_update(); wait_idle()
check('apps.update_selected', 'upgrade --id Mozilla.Firefox' in logtext() and 'upgrade --id 7zip.7zip' not in logtext())
check('apps.state_col', at.tree.set(list(at.labels)[0], 'state') == 'Başarılı', at.tree.set(list(at.labels)[0], 'state'))
shot(6, '5-uygulamalar')

# 6 Bakim (gercek pwsh)
os.environ['TEMP'] = str(TMP / 'temp'); (TMP / 'temp').mkdir(exist_ok=True)
app.run_ps('temp-preview', False); wait_idle(60)
check('maint.temp_preview_real_ps', '7 gunden eski' in logtext(), logtext()[-300:])
shot(7, '6-bakim')

# 6b Kol / Gamepad (3.6.0)
check('pad.tab_present', app.tabs.tab(8, 'text').strip() == 'Kol / Gamepad', app.tabs.tab(8, 'text'))
app.tabs.select(8)
for _ in range(30):
    app.update(); time.sleep(0.02)
check('pad.live_test_no_xinput_msg', 'yalnızca Windows' in app.pad_canvas.itemcget(app.pad_canvas.it['msg'], 'text') and app.pad_info['conn'].get() == 'XInput yok',
      app.pad_canvas.itemcget(app.pad_canvas.it['msg'], 'text'))
app.pad_scan(); wait_idle(30)
pt = app.pad_tree
pad_rows = {pt.payload[i]['name']: i for i in pt.labels if pt.payload.get(i)}
check('pad.rows_xbox_only', set(pad_rows) == {'Xbox Wireless Controller', 'Bluetooth XINPUT compatible input device', 'Xbox Controller'}, list(pad_rows))
check('pad.chips', [app.pad_chips[k][0].get() for k in ('total', 'usb', 'bluetooth', 'problem')] == ['3 kol bileşeni', '1 USB', '2 Bluetooth', '1 sorunlu'],
      [v.get() for v, _ in app.pad_chips.values()])
check('pad.bus_column', pt.tree.set(pad_rows['Xbox Controller'], 'bus') == 'USB kablo' and pt.tree.set(pad_rows['Xbox Wireless Controller'], 'bus') == 'Bluetooth')
check('pad.problem_first_and_checked', list(pt.labels)[0] == pad_rows['Bluetooth XINPUT compatible input device'] and pt.checked == {pad_rows['Bluetooth XINPUT compatible input device']}
      and 'risky' in pt.tree.item(pad_rows['Bluetooth XINPUT compatible input device'], 'tags'), (list(pt.labels), pt.checked))
diag = app.pad_diag.get('1.0', 'end')
check('pad.diag', 'sürücüsünde sorun var' in diag and 'USB kablo ile bağlı' in diag and 'XInput gerekir' in diag, diag)
app.pad_reset(); wait_idle(30)
lt = logtext()
rid = lt.split('RESETIDS=')[-1].split('\n')[0].split('|')
check('pad.reset_only_checked', rid == ['HID\\{00001812-0000-1000-8000-00805F9B34FB}_DEV_VID&02045E_PID&0B13_REV&0509\\9&1'], rid)
check('pad.rescan_after_reset', lt.rfind('Xbox kolları başlatıldı') > lt.rfind('Kol sürücüsünü sıfırla'))
pt.set_all(False)
app.pad_reset(); wait_idle(30)
rid = logtext().split('RESETIDS=')[-1].split('\n')[0].split('|')
check('pad.reset_all_when_none_checked', len(rid) == 3 and not any('PID_07A5' in r for r in rid), rid)
app.pad_bt_restart(); wait_idle(30)
check('pad.bt_restart', 'bthserv: Running' in logtext() and logtext().rfind('Xbox kolları başlatıldı') > logtext().rfind('Bluetooth hizmetini yeniden başlat'))
lad = TMP / 'lad'
for name in ('EA SPORTS FC 26', 'EA SPORTS FC 27'):
    (lad / name / 'settings').mkdir(parents=True, exist_ok=True)
(lad / 'EA SPORTS FC 27' / 'settings' / 'Settings_abc').write_text('controls=1')
(lad / 'EA SPORTS FC 27' / 'settings' / 'profile.ini').write_text('keep')
core.LOCALAPPDATA = str(lad)
app.pad_fc_reset(); wait_idle(30)
backs = list((lad / 'EA SPORTS FC 27').glob('settings_backup_*'))
check('pad.fc_reset_newest_backed_up', len(backs) == 1 and (backs[0] / 'Settings_abc').read_text() == 'controls=1'
      and not (lad / 'EA SPORTS FC 27' / 'settings' / 'Settings_abc').exists() and (lad / 'EA SPORTS FC 27' / 'settings' / 'profile.ini').exists()
      and not list((lad / 'EA SPORTS FC 26').glob('settings_backup_*')), (backs, logtext()[-400:]))
check('pad.fc_reset_logged', 'Yedeklendi ve sıfırlandı (1 dosya): Settings_abc' in logtext(), logtext()[-400:])
n_info = len([a for a in ASKED if isinstance(a, tuple) and a[0] == 'info'])
app.pad_fc_reset(); wait_idle(10)
check('pad.fc_reset_nothing_left', len([a for a in ASKED if isinstance(a, tuple) and a[0] == 'info']) == n_info + 1)
app.pad_open('joy.cpl', 'Oyun kumandaları')
check('pad.open_non_windows_safe', 'yalnızca Windows' in logtext().strip().splitlines()[-1], logtext()[-200:])
shot(8, '7-kol-gamepad')

# 7 Guncelleme (paket yukleme) - gercek paketten turetilmis 3.3.1 paketi bir kurulum kopyasina uygulanir
import shutil, zipfile  # noqa: E402
inst = TMP / 'install'
shutil.copytree(ROOT, inst, ignore=shutil.ignore_patterns('tests', '__pycache__', '*.cmd', 'packaging', 'regression*.json', 'MANIFEST.json'))
(inst / 'VERSION').write_text(core.VERSION)
app.install_dir, app.backup_root, app.no_restart = inst, TMP / 'update-backups', True


def make_pkg(path, ver, marker, tamper=False):
    src = TMP / ('pkgsrc-' + ver)
    shutil.rmtree(src, ignore_errors=True)
    shutil.copytree(ROOT, src, ignore=shutil.ignore_patterns('__pycache__'))
    cc = (src / 'care_core.py').read_text(encoding='utf-8').replace("VERSION = '%s'" % core.VERSION, "VERSION = '%s'" % ver)
    (src / 'care_core.py').write_text(cc, encoding='utf-8')
    (src / 'app.pyw').write_text((src / 'app.pyw').read_text(encoding='utf-8') + '\n# %s\n' % marker, encoding='utf-8')
    man = core.build_manifest(src)
    if tamper:
        (src / 'care_tasks.ps1').write_text((src / 'care_tasks.ps1').read_text(encoding='utf-8') + '\n# kotu niyetli degisiklik\n', encoding='utf-8')
    (src / 'MANIFEST.json').write_text(json.dumps(man), encoding='utf-8')
    with zipfile.ZipFile(path, 'w') as z:
        for f in src.rglob('*'):
            if f.is_file():
                z.write(f, 'agfo-care/' + f.relative_to(src).as_posix())
    return path


import json  # noqa: E402
good_pkg = make_pkg(TMP / 'AGFO-System-Care-v3.3.1.zip', '3.3.1', 'AGFO_UPDATE_MARKER_331')
bad_pkg = make_pkg(TMP / 'tampered.zip', '3.3.2', 'X', tamper=True)
app.open_updater(); app.update()
check('upd.dialog', app.upd_win.winfo_exists() and str(app.upd_apply_btn['state']) == 'disabled')
app_mod.filedialog.askopenfilename = lambda **k: str(bad_pkg)
app.upd_pick(); wait_idle(60)
txt = app.upd_check.get('1.0', 'end')
check('upd.tampered_rejected', 'SHA-256 uyuşmuyor' in txt and 'care_tasks.ps1' in txt and str(app.upd_apply_btn['state']) == 'disabled', txt[:400])
app_mod.filedialog.askopenfilename = lambda **k: str(good_pkg)
app.upd_pick(); wait_idle(90)
txt = app.upd_check.get('1.0', 'end')
check('upd.checks_pass', all(k in txt for k in ['%s → 3.3.1' % core.VERSION, 'MANIFEST.json: tüm dosyaların SHA-256', 'Python derleme: app.pyw',
                                                  'Python derleme: care_core.py', 'PowerShell sözdizimi: care_tasks.ps1', 'Hazır']) and '✗' not in txt, txt[:900])
check('upd.apply_enabled_only_after_check', str(app.upd_apply_btn['state']) == 'normal')
app.refresh_engines(); wait_idle()
check('upd.apply_not_reenabled_by_other_jobs', str(app.upd_apply_btn['state']) == 'normal' and app.upd_info is not None)
subprocess.run(['import', '-window', 'root', str(SHOTS / '7-guncelleme.png')], check=False)
ASKED.clear()
app.upd_apply(); wait_idle(60)
check('upd.applied', 'AGFO_UPDATE_MARKER_331' in (inst / 'app.pyw').read_text(encoding='utf-8') and (inst / 'VERSION').read_text() == '3.3.1'
      and "VERSION = '3.3.1'" in (inst / 'care_core.py').read_text(encoding='utf-8'), (inst / 'VERSION').read_text())
check('upd.no_tests_in_install', not (inst / 'tests').exists() and not (inst / 'MANIFEST.json').exists() and not (inst / 'Baslat.cmd').exists())
bks = core.list_backups(app.backup_root)
check('upd.backup_made', len(bks) == 1 and bks[0]['version'] == core.VERSION and 'AGFO_UPDATE_MARKER' not in (pathlib.Path(bks[0]['path']) / 'app.pyw').read_text(encoding='utf-8'))
check('upd.backup_listed', app.upd_bk.get_children() == (bks[0]['path'],))
check('upd.confirmed', 'Güncellemeyi uygula' in ASKED)
check('upd.history', any('GÜNCELLENDİ' in l and '3.3.1' in l for l in core.update_history()))
app.upd_bk.selection_set(bks[0]['path'])
app.upd_rollback(); wait_idle(60)
check('upd.rollback', 'AGFO_UPDATE_MARKER_331' not in (inst / 'app.pyw').read_text(encoding='utf-8') and (inst / 'VERSION').read_text() == core.VERSION
      and any(b['version'] == core.VERSION for b in core.list_backups(app.backup_root)), [b['version'] for b in core.list_backups(app.backup_root)])
# 7b GitHub tek tik guncelleme (sahte GitHub API + indirme; gercek dogrulama/uygulama kodu)
import hashlib, io  # noqa: E402
ghu = app_mod.ghu
_v = [int(x) for x in core.VERSION.split('.')]
NEXT = '%d.%d.%d' % (_v[0], _v[1], _v[2] + 1)
pkg341 = make_pkg(TMP / ('AGFO-System-Care-v%s.zip' % NEXT), NEXT, 'AGFO_GH_MARKER_NEXT')
PKG = pkg341.read_bytes()
GH = {'digest': 'sha256:' + hashlib.sha256(PKG).hexdigest()}
RELS = lambda: [{'tag_name': 'system-care-v' + NEXT, 'name': 'System Care ' + NEXT, 'draft': False, 'prerelease': False, 'body': 'Hata düzeltmeleri',
                 'html_url': 'https://github.com/downtownck/agfo-windows-apps/releases/tag/system-care-v' + NEXT, 'published_at': '2026-10-18T09:00:00Z',
                 'assets': [{'name': 'AGFO-System-Care-v%s.zip' % NEXT, 'size': len(PKG), 'digest': GH['digest'],
                             'browser_download_url': 'https://github.com/downtownck/agfo-windows-apps/releases/download/system-care-v%s/AGFO-System-Care-v%s.zip' % (NEXT, NEXT)}]},
                {'tag_name': 'supertools-v9.0.0', 'draft': False, 'prerelease': False, 'assets': []}]
ghu.fetch_json = lambda url, user_agent='': RELS()


class _R(io.BytesIO):
    def __init__(self, b):
        super().__init__(b); self.headers = {'Content-Length': str(len(b))}
    def __enter__(self): return self
    def __exit__(self, *x): return False


ghu._open = lambda url, **k: _R(PKG)
app.gh_check(force=True)
for _ in range(60):
    app.update(); time.sleep(0.05)
check('gh.banner_shown', app.gh_banner.winfo_ismapped() and NEXT in app.gh_banner_text.get(), app.gh_banner_text.get())
subprocess.run(['import', '-window', 'root', '-crop', '%dx%d+%d+%d' % (app.winfo_width(), app.winfo_height(), app.winfo_rootx(), app.winfo_rooty()),
                str(SHOTS / '8-github-bandi.png')], check=False)
# once bozuk indirme: SHA tutmaz -> kurulum degismez
ghu._open = lambda url, **k: _R(PKG[:-10] + b'xxxxxxxxxx')
ver_before = (inst / 'VERSION').read_text()
app.gh_update(); wait_idle(60)
check('gh.bad_download_rejected', (inst / 'VERSION').read_text() == ver_before and 'SHA-256' in logtext() and app.gh_banner.winfo_ismapped(), logtext()[-500:])
ghu._open = lambda url, **k: _R(PKG)
app.gh_update(); wait_idle(90)
check('gh.one_click_applied', 'AGFO_GH_MARKER_NEXT' in (inst / 'app.pyw').read_text(encoding='utf-8') and (inst / 'VERSION').read_text() == NEXT
      and (inst / 'agfo_github_update.py').is_file(), (inst / 'VERSION').read_text())
check('gh.banner_hidden_after', not app.gh_banner.winfo_ismapped())
check('gh.download_cleaned', not any(core.GH_DOWNLOAD_DIR.glob('*.part')) and not (core.GH_DOWNLOAD_DIR / ('AGFO-System-Care-v%s.zip' % NEXT)).exists())
st = ghu.load_state(core.GH_STATE)
check('gh.state_saved', st.get('last_result', {}).get('version') == NEXT)
app.upd_win.destroy()
app.refresh_engines(); wait_idle()
check('upd.closed_dialog_no_crash', not app.busy and all(b.winfo_exists() for b in app.action_buttons))

# Durdur
app.start([app_mod.Job('uzun', cmd=['sh', '-c', 'for i in $(seq 1 100); do echo $i; sleep 0.1; done'])])
for _ in range(20):
    app.update(); time.sleep(0.05)
check('cancel.enabled', str(app.cancel_btn['state']) == 'normal')
app.cancel(); wait_idle(20)
check('cancel.stopped', not app.busy and 'Durduruldu' in logtext() or '-1' in logtext().split('uzun başlatıldı')[-1] or 'Sonuç: -' in logtext().split('uzun başlatıldı')[-1], logtext()[-300:])
check('ui.buttons_reenabled', all(str(b['state']) == 'normal' for b in app.action_buttons))
app.destroy()
fails = [r for r in RESULTS if not r[1]]
print('\nGUI: %d pass, %d fail' % (len(RESULTS) - len(fails), len(fails)))
sys.exit(1 if fails else 0)
