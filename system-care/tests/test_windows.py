"""Gercek Windows testi (GitHub Actions windows-latest): care_tasks.ps1 salt okunur eylemleri ve uctan uca arayuz.
Hicbir eylem sistemi degistirmez (yalnizca okuma). Kullanim: python -I tests/test_windows.py <system-care klasoru>"""
import json, os, pathlib, subprocess, sys, tempfile, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ROOT = pathlib.Path(sys.argv[1]).resolve()
TMP = pathlib.Path(tempfile.mkdtemp())
os.environ['LOCALAPPDATA'] = str(TMP / 'lad')
os.environ['APPDATA'] = str(TMP / 'ad')
sys.path.insert(0, str(ROOT))
import care_hw as hw  # noqa: E402

RESULTS = []


def check(name, cond, detail=''):
    RESULTS.append((name, bool(cond)))
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' - ' + str(detail)[:600]), flush=True)


def ps(action, **kw):
    cmd = ['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(ROOT / 'care_tasks.ps1'), '-Action', action]
    for k, v in kw.items():
        cmd += ['-' + k, v]
    t0 = time.time()
    env = dict(os.environ); env.pop('PSModulePath', None)       # uygulama da boyle calistirir (sc_base.child_env)
    p = subprocess.run(cmd, capture_output=True, timeout=600, env=env)
    out = p.stdout.decode('utf-8', 'replace').lstrip('﻿')
    lines = out.splitlines()
    bad = []
    for ln in lines:
        if ln.startswith('@@'):
            try:
                json.loads(ln[2:])
            except ValueError:
                bad.append(ln[:200])
    print('  %s: kod %s, %d satir, %.1f sn' % (action, p.returncode, len(lines), time.time() - t0), flush=True)
    if p.returncode not in (0, 3):
        print(out[-1500:], p.stderr.decode('utf-8', 'replace')[-1500:], flush=True)
    return p.returncode, lines, bad


# ---- PowerShell gorev motoru: salt okunur eylemler gercek Windows'ta
for act, ok_codes in (('system-info', (0,)), ('devices', (0,)), ('drivers-list', (0,)), ('dns-list', (0,)), ('vpn-status', (0,)),
                      ('phantom-list', (0,)), ('controller-list', (0,)), ('appx-list', (0,)), ('temp-preview', (0,)), ('sensors', (3,))):
    code, lines, bad = ps(act)
    check('ps.%s' % act, code in ok_codes and not bad, (code, bad, lines[-5:]))

code, lines, bad = ps('hw-inventory')
recs = hw.parse_records(lines, 'hw')
kinds = {r['kind'] for r in recs}
check('ps.hw-inventory', code == 0 and not bad and {'os', 'computer', 'cpu', 'volume'} <= kinds, (code, bad, sorted(kinds)))
secs = hw.inventory_sections(recs)
check('hw.sections', any(t == 'İşletim sistemi' for t, _ in secs) and any(t.startswith('İşlemci') for t, _ in secs), [t for t, _ in secs])
print('  bolumler:', [t for t, _ in secs], flush=True)

code, lines, bad = ps('disk-health')
disks = hw.parse_records(lines, 'disk')
check('ps.disk-health', code == 0 and not bad and len(disks) >= 1 and all(hw.disk_verdict(d)[1] for d in disks), (code, bad, disks[:2]))
for d in disks:
    print('  disk:', d.get('name'), '->', hw.disk_verdict(d), flush=True)

# 4.3: gercek Windows DPAPI — System Care anahtari ve AI Editor'un sakladigi anahtar (ayni entropi) cozulebilmeli
import care_ai as _ai  # noqa: E402
_tok = 'agfoed.5.abcd1234.' + 'Z' * 40
_enc = _ai.protect(_tok)
check('ai.dpapi_roundtrip', _enc.startswith('dpapi:') and _tok not in _enc and _ai.unprotect(_enc) == _tok and _ai.unprotect(_enc, _ai.EDITOR_ENTROPY) == '', _enc[:20])
_edsrc = ROOT.parent / 'ai-editor' / 'src'
if (_edsrc / 'agfo_secrets.py').is_file():
    sys.path.insert(0, str(_edsrc))
    import agfo_secrets as _eds  # noqa: E402
    check('ai.reads_ai_editor_secret', _ai.unprotect(_eds.protect(_tok), _ai.EDITOR_ENTROPY) == _tok)
    sys.path.remove(str(_edsrc))

# 4.4: internet hizi taramasi ve DNS hiz testi (gercek PowerShell 5.1; yalniz okur)
import care_netopt as _no  # noqa: E402
import base64 as _b64n  # noqa: E402
code, lines, bad = ps('net-scan')
_recs = [json.loads(l[2:]) for l in lines if l.startswith('@@')]
_types = {r.get('type') for r in _recs}
check('ps.net-scan', code == 0 and not bad and {'net-adapter', 'dns-probe', 'net-ping', 'net-do'} <= _types, (code, bad, sorted(_types), lines[-8:]))
_probes = [r for r in _recs if r.get('type') == 'dns-probe']
check('ps.net-scan.dns_measured', any(_no.probe_ok(p_) for p_ in _probes), _probes)
_find = _no.analyze(_recs, [])
check('netopt.analyze_real', any(f_['id'] == 'dns' for f_ in _find) and any(f_['id'] == 'wu' for f_ in _find), [f_['id'] for f_ in _find])
_items = _b64n.b64encode(json.dumps([{'server': '1.1.1.1'}, {'server': '8.8.8.8'}, {'server': 'x;calc'}]).encode()).decode()
code, lines, bad = ps('dns-bench', ItemsB64=_items)
_bp = [json.loads(l[2:]) for l in lines if l.startswith('@@')]
check('ps.dns-bench', code == 0 and not bad and sorted(r['server'] for r in _bp) == ['1.1.1.1', '8.8.8.8'] and any(_no.probe_ok(r) for r in _bp), (code, bad, _bp))

code, lines, bad = ps('pnp-list')
pnp = hw.parse_records(lines, 'pnp')
check('ps.pnp-list', code == 0 and not bad and len(pnp) >= 10 and all(r.get('id') for r in pnp), (code, bad, len(pnp)))
groups = hw.pnp_groups(pnp)
check('hw.pnp_groups', len(groups) >= 3, [g[0] for g in groups])

code, lines, bad = ps('overview')
ov = hw.parse_records(lines, 'ov')
keys = {r['key'] for r in ov}
check('ps.overview', code == 0 and not bad and {'uptime', 'memory', 'reboot', 'devices'} <= keys and any(k.startswith('volume:') for k in keys), (code, bad, sorted(keys)))
cards = hw.overview_cards(ov)
check('hw.overview_cards', cards and all(c['title'] and c['state'] in hw.STATE_RANK for c in cards), cards[:3])
for c in cards:
    print('  kart: %-22s %-5s %s | %s' % (c['title'], c['state'], c['value'], c['detail']), flush=True)

code, lines, bad = ps('pnp-action')                        # parametresiz: kurala uygun reddetmeli (yonetici varsa 2, yoksa 740)
check('ps.pnp-action_guard', code in (2, 740), code)


# ---- 4.0 yetki modeli: care_elevated.ps1 arguman aktarimi ve Runner'in UAC yolu (CI zaten yonetici; runas onaysiz gecer)
import base64, queue as _q  # noqa: E402
probe = [sys.executable, '-c', 'import sys, json; print("ARGS=" + json.dumps(sys.argv[1:]))', 'a b', 'q"x', 'c:\\yol bosluk\\', '', 'çğış']
outf = TMP / 'elev.out'
b64 = base64.b64encode(json.dumps(probe).encode('utf-8')).decode('ascii')
_env = dict(os.environ); _env.pop('PSModulePath', None)
pr = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(ROOT / 'care_elevated.ps1'), '-ArgsB64', b64,
                     '-OutFile', str(outf), '-Cwd', str(TMP)], capture_output=True, timeout=120, env=_env)
got = outf.read_text(encoding='utf-8-sig').strip() if outf.exists() else ''
check('elev.args_roundtrip', pr.returncode == 0 and got == 'ARGS=' + json.dumps(probe[3:]), (pr.returncode, got, pr.stderr[-400:]))
import sc_base  # noqa: E402
rq = _q.Queue()
rn = sc_base.Runner(rq.put); rn.is_admin = False
sc_base.LOG_DIR = TMP / 'logs'
jb = sc_base.Job('Yonetici testi', cmd=sc_base.ps_cmd('pnp-action'))               # parametresiz -> betik 2 ile reddeder (yonetici olarak)
check('elev.needs', rn.needs_elevation(jb))
rn._run_all([jb])
check('elev.runner_code', jb.code == 2 and any('belirtilmedi' in l for l in jb.lines), (jb.code, jb.lines[-3:]))
jb2 = sc_base.Job('Veri testi', cmd=sc_base.ps_cmd('system-info'), admin=True)
rn._run_all([jb2])
check('elev.runner_lines', jb2.code == 0 and any('Windows' in l for l in jb2.lines), (jb2.code, jb2.lines[:3]))


# ---- 4.1 uretici bilgisi, NVIDIA bilgisi, NVIDIA surucu servisi (cevrim ici), imza denetimi
import care_oem as oem  # noqa: E402
import care_core as core  # noqa: E402
code, lines, bad = ps('oem-info')
o = hw.parse_records(lines, 'oem')
check('ps.oem-info', code == 0 and not bad and o and 'maker' in o[0], (code, o[:1]))
if o:
    inf = oem.identify(o[0]); print('  uretici:', inf['name'], '|', inf['model'], '|', oem.support_links(inf)['drivers'], flush=True)
code, lines, bad = ps('nvidia-info')
nvr = hw.parse_records(lines, 'nvinfo')
check('ps.nvidia-info', code == 0 and not bad and nvr and isinstance(nvr[0].get('gpus'), list) and nvr[0]['gpus'], (code, nvr[:1]))
data = oem.load_nv_data(ROOT / 'assets' / 'nvidia-data.json')
pf, _k = oem.nv_pfid(data, 'NVIDIA GeForce RTX 4070', False)
try:
    res = oem.nv_parse_lookup(core.fetch_text(oem.nv_lookup_url(pf, oem.nv_os_id(data, 26100)), oem.NV_HOSTS))
except Exception as e:                                              # noqa: BLE001
    res = {'error': str(e)}
print('  NVIDIA servis:', res, flush=True)
check('nv.lookup_online', res and 'studio' not in res.get('name', '').lower() and res.get('version') and oem.version_tuple(res['version']) >= (500,) and core.host_allowed(res['url'], oem.NV_HOSTS), res)
code, lines, bad = ps('sig-check', Paths=os.path.join(os.environ['SystemRoot'], 'explorer.exe'))
sg = hw.parse_records(lines, 'sig')
check('ps.sig-check', code == 0 and sg and sg[0]['status'] == 'Valid' and 'Microsoft' in sg[0]['subject'], sg)


# ---- 4.1.1 Lenovo otomatik guncelleme: LSUClient modulu PowerShell Galerisi'nden kurulabiliyor mu (bu VM Lenovo degil; tarama hatasi beklenir)
code, lines, bad = ps('lenovo-scan')
envc = dict(os.environ); envc.pop('PSModulePath', None)
probe_ps = ("$m=Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'WindowsPowerShell\\Modules'; $env:PSModulePath=$m+';'+$env:PSModulePath; "
            "Import-Module LSUClient -ErrorAction Stop; $n=@(Get-LSUpdate -Model 20XW -All -ErrorAction Stop).Count; 'LSU_ALL=' + $n")
chk = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', probe_ps], capture_output=True, env=envc, timeout=600)
outp = chk.stdout.decode('utf-8', 'replace')
print('  lenovo-scan kod', code, '|', ' / '.join(lines[-2:]), '| ThinkPad 20XW katalogu:', outp.strip()[-80:], chk.stderr.decode('utf-8', 'replace')[-300:], flush=True)
import re as _re
mm = _re.search(r'LSU_ALL=(\d+)', outp)
check('lsu.catalog_works', mm and int(mm.group(1)) > 5 and not bad, (code, outp[-300:]))
code, lines, bad = ps('dell-scan')
check('ps.dell-scan_missing', code == 3 and any('kurulu degil' in l for l in lines), (code, lines[-3:]))


# ---- 4.2 surecler / servisler / baslangic (gercek Windows)
import care_procs as pr  # noqa: E402
code, lines, bad = ps('proc-list')
procs = hw.parse_records(lines, 'proc')
check('ps.proc-list', code == 0 and not bad and len(procs) > 20 and any(p['name'].lower().startswith('python') for p in procs), (code, len(procs)))
victim = subprocess.Popen(['ping', '-n', '300', '127.0.0.1'], stdout=subprocess.DEVNULL)
time.sleep(1)
code, lines, bad = ps('proc-kill', ItemsB64=pr.b64_items([{'pid': victim.pid, 'name': 'PING'}, {'pid': 4, 'name': 'System'}]), Op='kill')
time.sleep(1)
check('ps.proc-kill', victim.poll() is not None and any('Kritik' in l for l in lines), (code, victim.poll(), lines[-4:]))
code, lines, bad = ps('svc-list')
svcs = hw.parse_records(lines, 'svc')
check('ps.svc-list', code == 0 and not bad and len(svcs) > 100 and any(s['name'] == 'Winmgmt' and s['state'] == 'Running' for s in svcs), (code, len(svcs)))
code, lines, bad = ps('svc-action', ItemsB64=pr.b64_items([{'name': 'Winmgmt'}]), Op='stop')
check('ps.svc-action_guard', any('Kritik servis' in l for l in lines), lines[-3:])
import winreg  # noqa: E402
rk = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run')
winreg.SetValueEx(rk, 'AGFOTestBaslangic', 0, winreg.REG_SZ, '"C:\\Windows\\notepad.exe" /x')
try:
    code, lines, bad = ps('startup-list')
    st = [r for r in hw.parse_records(lines, 'startup') if r['name'] == 'AGFOTestBaslangic']
    check('ps.startup-list', code == 0 and not bad and st and st[0]['enabled'] and st[0]['scope'] == 'hkcu-run', st)
    code, lines, bad = ps('startup-set', ItemsB64=pr.b64_items([{'scope': 'hkcu-run', 'name': 'AGFOTestBaslangic'}]), Op='disable')
    code2, lines2, _b = ps('startup-list')
    st2 = [r for r in hw.parse_records(lines2, 'startup') if r['name'] == 'AGFOTestBaslangic']
    ps('startup-set', ItemsB64=pr.b64_items([{'scope': 'hkcu-run', 'name': 'AGFOTestBaslangic'}]), Op='enable')
    code3, lines3, _b = ps('startup-list')
    st3 = [r for r in hw.parse_records(lines3, 'startup') if r['name'] == 'AGFOTestBaslangic']
    check('ps.startup-set', code == 0 and st2 and st2[0]['enabled'] is False and st3 and st3[0]['enabled'] is True, (code, st2, st3))
finally:
    winreg.DeleteValue(rk, 'AGFOTestBaslangic')
    try:
        ak = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run', 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(ak, 'AGFOTestBaslangic')
    except OSError:
        pass

# ---- Uctan uca arayuz: gercek PowerShell ile Genel bakis, Sistem ozeti, Aygit yoneticisi, Disk sagligi
setdir = TMP / 'lad' / 'AGFO' / 'SystemCare'
setdir.mkdir(parents=True)
(setdir / 'settings.json').write_text(json.dumps({'auto_update_check': False, 'modern_ui': False, 'last_page': 'Motorlar'}), encoding='utf-8')
import importlib.machinery, importlib.util  # noqa: E402
loader = importlib.machinery.SourceFileLoader('care_app', str(ROOT / 'app.pyw'))
spec = importlib.util.spec_from_loader('care_app', loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)
m.messagebox.showinfo = lambda *a, **k: None
m.messagebox.showerror = lambda *a, **k: print('showerror', a, flush=True)
m.messagebox.askyesno = lambda *a, **k: False
app = m.App()


def pump(sec=0.3):
    t0 = time.time()
    while time.time() - t0 < sec:
        app.update()
        time.sleep(0.02)


def idle(timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        pump(0.2)
        if not app.busy:
            return True
    return False


pump(1.0); idle()
for i in range(len(app.tabs.pages)):
    app.tabs.select(i); pump(0.05)
check('gui.all_pages', len(app.tabs.pages) == 29, len(app.tabs.pages))
idle()
app.tabs.select('Genel bakış'); pump(0.3)
if not app.ov_loaded:
    idle(); app.ov_refresh()
check('gui.overview', idle() and app.ov_loaded and len(app.ov_cards) >= 5 and app.ov_score.get().startswith('Sağlık puanı'), (app.ov_score.get(), len(app.ov_cards)))
app.tabs.select('Sistem özeti'); app.hw_scan()
check('gui.hwinfo', idle() and len(app.hw_tree.get_children()) >= 4, len(app.hw_tree.get_children()))
app.tabs.select('Aygıt yöneticisi'); app.dm_scan()
check('gui.devmgr', idle() and len(app.dm_records) >= 10 and len(app.dm_tree.get_children()) >= 3, len(app.dm_records))
app.tabs.select('Disk sağlığı'); app.dh_scan()
check('gui.diskhealth', idle() and len(app.dh_tree.get_children()) >= 1, len(app.dh_records))
rep = hw.report_html(*app._hw_report_parts())
check('gui.report', 'İşletim sistemi' in rep and len(rep) > 2000, len(rep))
check('gui.not_busy', not app.busy)
app.destroy()
fails = [n for n, ok in RESULTS if not ok]
print('%s windows: %d/%d' % ('PASS' if not fails else 'FAIL', len(RESULTS) - len(fails), len(RESULTS)))
sys.exit(1 if fails else 0)
