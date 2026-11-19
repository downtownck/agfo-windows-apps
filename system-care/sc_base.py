"""AGFO System Care 3.8.0 - acik kaynak motorlari kendi arayuzu icinde calistiran Windows bakim uygulamasi.

Motorlar: BleachBit (temizlik), Bulk Crap Uninstaller (program envanteri/artik), Snappy Driver Installer Origin
(surucu), WinGet (uygulama guncelleme), Windows Update / DISM / SFC / PnPUtil (yerlesik).
Motorlar WinGet ile sessizce kurulur; komut satiri/betik kipinde arka planda calisir; listeler, secimler ve
sonuclar bu pencerede gosterilir. Hicbir islev web sayfasi acmaz.
"""
import ctypes
import datetime
import json
import os
import pathlib
import queue
import subprocess
import sys
import threading
import time

IS_WIN = sys.platform == 'win32'


def _enable_dpi_awareness():
    if not IS_WIN:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


_enable_dpi_awareness()

import tkinter as tk  # noqa: E402
from tkinter import filedialog, messagebox, ttk  # noqa: E402

BASE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import care_core as core  # noqa: E402
import care_tweaks as tweaks  # noqa: E402
import care_theme as theme  # noqa: E402
import care_icons as icons  # noqa: E402
import care_vpn as vpn  # noqa: E402
import net_tools  # noqa: E402  (SuperTools: ag tarayici, ag testleri, SSH)
import agfo_github_update as ghu  # noqa: E402

VERSION = core.VERSION
LOG_DIR = core.LOG_DIR
LOG_RETENTION_DAYS = 30
LOG_WIDGET_MAX_LINES = 6000
LOG_WIDGET_TRIM_LINES = 1500
POLL_MS = 80
# Renk jetonlari (BG, PANEL, PANEL2, FG, MUTED, ACCENT, WARN, OK_C, BAD_C, SEL, TREE_BG, LOG_BG, BTN, NAV_BG ...) secili temadan
# gelir; tema degisince set_palette ile guncellenir. Modern gorunum (ttkbootstrap) kuruluysa ttk bilesenleri onunla cizilir.
_SETTINGS0 = core.load_settings()
TB, TB_STATE = theme.load_ttkbootstrap(theme.ui_lib_dir(core.APP_DATA_DIR), _SETTINGS0.get('modern_ui', True))
if TB is not None:
    ttk = TB  # noqa: F811  (ayni ttk arayuzu: Treeview, Checkbutton, Combobox, Entry, Scrollbar, Frame, Style, Button)
THEME_KEY = theme.DEFAULT


_PALETTE_MODULES = []      # set_palette tum sayfa modullerinin renk jetonlarini birlikte gunceller


def register_palette_module(g):
    """Sayfa modulu kendi globals()'ini kaydeder; renk jetonlari ve THEME_KEY her tema degisiminde orada da guncellenir."""
    if g not in _PALETTE_MODULES:
        _PALETTE_MODULES.append(g)
    g.update(theme.tokens(THEME_KEY))
    g['THEME_KEY'] = THEME_KEY


def set_palette(key):
    global THEME_KEY
    THEME_KEY = key if key in theme.theme_keys() else theme.DEFAULT
    vals = theme.tokens(THEME_KEY)
    globals().update(vals)
    for g in _PALETTE_MODULES:
        g.update(vals)
        g['THEME_KEY'] = THEME_KEY


set_palette(_SETTINGS0.get('theme', theme.DEFAULT))
COLOR_OPTS = ('background', 'foreground', 'activebackground', 'activeforeground', 'selectbackground', 'selectforeground',
              'insertbackground', 'disabledforeground', 'highlightbackground', 'highlightcolor', 'troughcolor')
CREATIONFLAGS = core.CREATIONFLAGS
CHK_ON, CHK_OFF, CHK_MIX = '☑', '☐', '▣'

# Bakim & saglik sekmesi (care_tasks.ps1 eylemleri; sozlesme testi bu sozlugu okur)
ACTIONS = {
 'Windows Bakımı': [
  ('Geçici dosyaları analiz et','temp-preview','Yalnızca kullanıcı Temp alanında 7 günden eski dosyalar.',False),
  ('Geçici dosyaları temizle','temp-clean','Önizlemedeki dosyaları siler; kilitli dosyaları atlar.',True),
  ('Bileşen deposunu analiz et','component-analyze','Windows bileşen deposu durumunu DISM ile inceler.',False),
  ('Bileşen deposunu temizle','component-clean','DISM StartComponentCleanup; ResetBase kullanılmaz.',True),
 ],
 'Sistem Sağlığı': [
  ('Sistem bilgileri','system-info','Windows sürümü, bellek, disk boş alanları ve bekleyen yeniden başlatma durumu.',False),
  ('Windows sistem dosyalarını tara','health-scan','DISM ScanHealth ile sorunları denetler.',False),
  ('Windows onarımını çalıştır','health-repair','Önce DISM RestoreHealth, ardından SFC ScanNow.',True),
  ('Geri yükleme noktası oluştur','restore-point','Sistem Koruması etkinse geri yükleme noktası oluşturur.',True),
 ],
}
# Sekme ici dugmelerin kullandigi diger care_tasks.ps1 eylemleri
INTERNAL_PS_ACTIONS = ['lenovo-scan','lenovo-install','dell-scan','dell-install','oem-info','nvidia-info','nvidia-uninstall','nvidia-remove-packages','sig-check','hw-inventory','disk-health','pnp-list','pnp-action','overview','sensors','vpn-status','tweak-read','tweak-write','dns-list','dns-flush','explorer-restart','controller-list','controller-reset','bt-restart','phantom-list','phantom-remove','appx-list','appx-remove','driver-analyze','driver-scan','driver-install','devices','drivers-list','driver-backup','app-scan','app-update','recycle-paths']
ADMIN_ACTIONS = {'lenovo-install','dell-install','nvidia-uninstall','nvidia-remove-packages','pnp-action','controller-reset','bt-restart','phantom-remove','driver-install','driver-backup','component-analyze','component-clean','health-scan','health-repair','restore-point','sdio-scan','sdio-install'}
DANGER_TEXT = {
 'temp-clean':'7 günden eski Temp dosyaları kalıcı olarak silinir. Önizleme yapmanız önerilir.',
 'component-clean':'Windows bileşen deposu temizlenecek. Bu işlem zaman alabilir.',
 'health-repair':'DISM ve SFC sistem dosyalarını onarmaya çalışır. İnternet gerekebilir.',
 'restore-point':'Windows Sistem Koruması etkin değilse işlem hata verebilir.'}
EXIT_HINTS = {
 0:'Başarılı', 1:'Hata / kısmi sonuç', 2:'Hata / kısmi sonuç',
 740:'Yönetici yetkisi gerekli — "Yönetici olarak yeniden aç" düğmesini kullanın',
 1223:'Kullanıcı iptal etti', 3010:'Başarılı — yeniden başlatma gerekli', 1641:'Başarılı — yeniden başlatma başlatıldı',
 -1:'Durduruldu', -2:'Başlatılamadı',
}


def hint(code):
    if code in EXIT_HINTS:
        return EXIT_HINTS[code]
    if isinstance(code, int) and (code & 0xFFFFFFFF) >= 0x80000000:
        return 'Hata ' + core.winget_code_text(code)
    return 'Başarılı' if code == 0 else 'Hata / kısmi sonuç (kod %s)' % code


def prune_old_logs():
    try:
        cutoff = time.time() - LOG_RETENTION_DAYS * 86400
        for p in LOG_DIR.glob('*.log'):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink()
            except OSError:
                pass
    except Exception:
        pass


def child_env(cmd):
    """Windows PowerShell 5.1 alt sureci: PowerShell 7'den miras kalan PSModulePath 5.1 modullerini bozar (Get-AuthenticodeSignature vb.)."""
    try:
        exe = os.path.basename(str(cmd[0])).lower()
    except (IndexError, TypeError):
        return None
    if exe not in ('powershell.exe', 'powershell'):
        return None
    env = os.environ.copy()
    env.pop('PSModulePath', None)
    return env


def ps_cmd(action, **kw):
    cmd = ['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
           '-File', str(BASE / 'care_tasks.ps1'), '-Action', action]
    for k, v in kw.items():
        if v:
            cmd.extend(['-' + k, v])
    return cmd


# =========================================================================== is calistirici
class Job:
    """Tek bir arka plan isi. kind: 'proc' (cikti yakalanir), 'shell' (ShellExecuteEx, GUI kaldiricilar), 'func'."""

    def __init__(self, title, cmd=None, shell=None, func=None, on_done=None, cancel_ok=True, tail_dir=None,
                 after=None, cwd=None, show_output=True, admin=False):
        self.admin = admin                      # 4.0: uygulama yonetici degilse bu is tek basina UAC ile yonetici olarak calisir
        self.title, self.cmd, self.shell, self.func = title, cmd, shell, func
        self.on_done, self.cancel_ok, self.tail_dir, self.after = on_done, cancel_ok, tail_dir, after
        self.cwd, self.show_output = cwd, show_output
        self.lines, self.data, self.code, self.logfile = [], [], None, ''


class Runner:
    def __init__(self, post):
        self.post = post
        self.proc = None
        self.stop = threading.Event()
        self.is_admin = True                    # App kurulunca gercek deger atanir; True iken hicbir is ayrica yukseltilmez

    def needs_elevation(self, job):
        """4.0 yetki modeli: uygulama normal kullaniciyla calisir; yonetici isteyen is (ADMIN_ACTIONS ya da admin=True) tek basina UAC ister."""
        if self.is_admin or not job.cmd or not IS_WIN:
            return False
        if job.admin:
            return True
        cmd = [str(x) for x in job.cmd]
        if any(x.lower().endswith('care_tasks.ps1') for x in cmd) and '-Action' in cmd:
            i = cmd.index('-Action')
            return i + 1 < len(cmd) and cmd[i + 1] in ADMIN_ACTIONS
        return False

    def run(self, jobs):
        self.stop.clear()
        threading.Thread(target=self._run_all, args=(jobs,), daemon=True).start()

    def _run_all(self, jobs):
        for i, job in enumerate(jobs):
            if self.stop.is_set():
                break
            self.post(('status', '%s (%d/%d)' % (job.title, i + 1, len(jobs)) if len(jobs) > 1 else job.title))
            self.post(('cancel_ok', job.cancel_ok))
            self.post(('line', '\n[%s] %s başlatıldı\n' % (datetime.datetime.now().strftime('%H:%M:%S'), job.title)))
            try:
                if job.cmd and self.needs_elevation(job):
                    job.code = self._proc_elevated(job)
                elif job.cmd:
                    job.code = self._proc(job)
                elif job.shell:
                    exe, params = job.shell
                    self.post(('line', '> %s %s\n' % (exe, params)))
                    h = core.shell_execute(exe, params, cwd=job.cwd)
                    job.code = core.wait_handle(h, self.stop.is_set)
                elif job.func:
                    job.code = job.func(self, job)
                if job.after and not self.stop.is_set():
                    job.after(self, job)
            except Exception as e:
                job.code = -2
                self.post(('line', 'HATA: %s\n' % e))
            if self.stop.is_set() and job.code is None:
                job.code = -1
            self.post(('jobdone', job))
        self.post(('alldone', None))

    def say(self, text):
        self.post(('line', text if text.endswith('\n') else text + '\n'))

    def run_cmd(self, title, cmd, show_output=True):
        """Bir func isinin icinden alt komut calistirir (ciktisi ayni gunluge akar). Donus: (cikis kodu, satirlar)."""
        sub = Job(title, cmd=cmd, show_output=show_output)
        self.post(('line', '> ' + ' '.join(map(str, cmd)) + '\n'))
        try:
            code = self._proc(sub)
        except OSError as e:
            self.say('Başlatılamadı: %s' % e)
            return -2, []
        return code, sub.lines

    def progress_cb(self, label):
        def cb(done, total):
            if total:
                self.post(('progress', '%s: %.1f / %.1f MB (%%%d)' % (label, done / 1048576, total / 1048576, done * 100 // total)))
            else:
                self.post(('progress', '%s: %.1f MB' % (label, done / 1048576)))
        return cb

    def _tail(self, job, since, done):
        """SDIO gibi GUI alt sistemli motorlar stdout yazmaz; gunluk klasorundeki en yeni dosyayi canli izle."""
        pos, cur = 0, None
        while not done.is_set():
            p = core.newest_file(job.tail_dir, since)
            if p and p != cur:
                cur, pos = p, 0
            if cur:
                try:
                    with open(cur, 'rb') as f:
                        f.seek(pos)
                        chunk = f.read()
                        pos = f.tell()
                    if chunk:
                        for l in chunk.decode('utf-8', 'replace').replace('\x00', '').splitlines():
                            if l.strip():
                                job.lines.append(l)
                                self.post(('line', 'SDIO | ' + l.rstrip() + '\n'))
                except OSError:
                    pass
            done.wait(1.0)

    def _proc(self, job):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        safe = ''.join(c if c.isalnum() or c in '-_' else '-' for c in job.title)[:40]
        job.logfile = str(LOG_DIR / (datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + safe + '.log'))
        started = time.time()
        tail_done = threading.Event()
        with open(job.logfile, 'w', encoding='utf-8', buffering=1) as f:
            f.write('# ' + ' '.join(map(str, job.cmd)) + '\n')
            proc = subprocess.Popen(job.cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    creationflags=CREATIONFLAGS, cwd=job.cwd or str(BASE), env=child_env(job.cmd))
            self.proc = proc
            if job.tail_dir:
                threading.Thread(target=self._tail, args=(job, started - 2, tail_done), daemon=True).start()
            buf, first = b'', True
            try:
                while True:
                    chunk = proc.stdout.read1(65536) if hasattr(proc.stdout, 'read1') else proc.stdout.read(4096)
                    if not chunk:
                        break
                    if first:
                        first = False
                        if chunk.startswith(b'\xef\xbb\xbf'):
                            chunk = chunk[3:]
                    buf += chunk
                    while True:
                        nl = buf.find(b'\n')
                        if nl < 0:
                            break
                        raw, buf = buf[:nl], buf[nl + 1:]
                        self._emit_line(job, f, raw)
                    if b'\r' in buf:
                        segs = buf.split(b'\r')
                        shown = next((s for s in reversed(segs) if s.strip()), b'')
                        buf = b'\r' + shown + (b'\r' if not segs[-1] else b'')
                        text = shown.decode('utf-8', 'replace').replace('\x00', '').strip()
                        if text and job.show_output:
                            self.post(('progress', text))
                if buf.strip(b'\r \t'):
                    self._emit_line(job, f, buf)
                code = proc.wait()
            finally:
                proc.stdout.close()
                tail_done.set()
                self.proc = None
        return code

    def _proc_elevated(self, job):
        """Isi care_elevated.ps1 ile UAC onayli yonetici olarak calistirir; cikti dosyasini canli izler (ayni @@ veri ayrisimi)."""
        import base64
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        safe = ''.join(c if c.isalnum() or c in '-_' else '-' for c in job.title)[:40]
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        job.logfile = str(LOG_DIR / (stamp + '-' + safe + '.log'))
        out = LOG_DIR / ('.elevated-%s-%d.out' % (stamp, os.getpid()))
        b64 = base64.b64encode(json.dumps([str(x) for x in job.cmd]).encode('utf-8')).decode('ascii')
        cwd = job.cwd or str(BASE)
        params = '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "%s" -ArgsB64 %s -OutFile "%s" -Cwd "%s"' % (
            BASE / 'care_elevated.ps1', b64, out, cwd)
        self.post(('line', 'Yönetici onayı (UAC) isteniyor: %s\n' % job.title))
        started = time.time()
        tail_done = threading.Event()
        with open(job.logfile, 'w', encoding='utf-8', buffering=1) as f:
            f.write('# [yonetici] ' + ' '.join(map(str, job.cmd)) + '\n')
            try:
                h = core.shell_execute('powershell.exe', params, verb='runas', cwd=cwd, show=0)
            except OSError as e:
                self.post(('line', 'Yönetici olarak başlatılamadı: %s\n' % e))
                return 1223 if 'iptal' in str(e) else -2
            if job.tail_dir:
                threading.Thread(target=self._tail, args=(job, started - 2, tail_done), daemon=True).start()
            k32 = ctypes.windll.kernel32
            pos, buf, first = 0, b'', True

            def pump():
                nonlocal pos, buf, first
                try:
                    with open(out, 'rb') as fh:
                        fh.seek(pos)
                        chunk = fh.read()
                        pos = fh.tell()
                except OSError:
                    return
                if first and chunk:
                    first = False
                    if chunk.startswith(b'\xef\xbb\xbf'):
                        chunk = chunk[3:]
                buf += chunk
                while b'\n' in buf:
                    raw, buf = buf.split(b'\n', 1)
                    self._emit_line(job, f, raw.rstrip(b'\r'))
            try:
                while k32.WaitForSingleObject(h, 300) == 0x102:      # WAIT_TIMEOUT
                    pump()
                    if self.stop.is_set():
                        self.post(('line', 'Durdurma istendi; yönetici işlemi arka planda tamamlanabilir.\n'))
                        return -1
                pump()
                if buf.strip():
                    self._emit_line(job, f, buf)
                code = ctypes.c_ulong()
                k32.GetExitCodeProcess(h, ctypes.byref(code))
                return int(code.value)
            finally:
                k32.CloseHandle(h)
                tail_done.set()
                try:
                    out.unlink()
                except OSError:
                    pass

    def _emit_line(self, job, f, raw):
        line = raw.decode('utf-8', 'replace').replace('\x00', '')
        if '\r' in line:
            segs = [s for s in line.split('\r') if s.strip()]
            line = segs[-1] if segs else ''
        line = line.rstrip()
        if line.startswith('@@'):
            try:
                job.data.append(json.loads(line[2:]))
                return
            except ValueError:
                line = 'Uyarı: okunamayan veri satırı: ' + line[2:200]
        job.lines.append(line)
        f.write(line + '\n')
        if job.show_output:
            self.post(('line', line + '\n'))

    def kill(self):
        self.stop.set()
        proc = self.proc
        if not proc or proc.poll() is not None:
            return
        try:
            if IS_WIN:
                subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], creationflags=CREATIONFLAGS,
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            else:
                proc.kill()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


# =========================================================================== isaretlenebilir liste
class CheckTree(ttk.Frame):
    """#0 sutununda onay kutusu olan Treeview. Ust dugumler (gruplar) cocuklarini topluca isaretler.
    Tiklama: #0 hucresi; Bosluk: secili satirlar. Sutun basligina tiklayinca siralar."""

    def __init__(self, master, columns, first=('Ad', 320), height=14, on_change=None):
        super().__init__(master, style='Card.TFrame')
        self.cols = [c[0] for c in columns]
        self.tree = ttk.Treeview(self, columns=self.cols, show='tree headings', selectmode='extended', height=height)
        self.tree.heading('#0', text=first[0], command=lambda: self.sort('#0'))
        self.tree.column('#0', width=first[1], stretch=True)
        for n, (key, title, width, anchor) in enumerate(columns):
            self.tree.heading(key, text=title, command=lambda k=key: self.sort(k))
            self.tree.column(key, width=width, minwidth=40, anchor=anchor, stretch=(n == len(columns) - 1))
        ys = ttk.Scrollbar(self, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=ys.set)
        self.tree.pack(side='left', fill='both', expand=True)
        ys.pack(side='right', fill='y')
        self.checked = set()
        self.labels = {}
        self.payload = {}
        self.on_change = on_change
        self._sort_rev = {}
        self.tree.bind('<Button-1>', self._click, add=True)
        self.tree.bind('<space>', self._space)
        self.retheme()
        CheckTree.INSTANCES.append(self)

    INSTANCES = []

    def retheme(self):
        try:
            self.tree.tag_configure('risky', foreground=WARN)
            self.tree.tag_configure('orphan', foreground=BAD_C)
            self.tree.tag_configure('group', font=('Segoe UI', 10, 'bold'))
            self.tree.tag_configure('muted', foreground=MUTED)
            for tg, col in (('st_new', OK_C), ('st_missing', BAD_C), ('st_problem', WARN), ('st_warn', WARN), ('st_old', MUTED), ('st_ok', FG)):
                self.tree.tag_configure(tg, foreground=col)
        except tk.TclError:
            pass

    def clear(self):
        self.tree.delete(*self.tree.get_children())
        self.checked.clear(); self.labels.clear(); self.payload.clear()
        self._changed()

    def add(self, iid, label, values=(), parent='', checked=False, tags=(), payload=None, checkable=True, open_=False):
        self.labels[iid] = (label, checkable)
        self.payload[iid] = payload
        self.tree.insert(parent, 'end', iid=iid, text=self._text(iid, checked), values=values, tags=tags, open=open_)
        if checked and checkable:
            self.checked.add(iid)
        return iid

    def _text(self, iid, on):
        label, checkable = self.labels[iid]
        if not checkable:
            return '   ' + label
        kids = self.tree.get_children(iid) if self.tree.exists(iid) else ()
        if kids:
            n = sum(1 for k in kids if k in self.checked)
            mark = CHK_ON if n == len(kids) else (CHK_MIX if n else CHK_OFF)
        else:
            mark = CHK_ON if on else CHK_OFF
        return mark + '  ' + label

    def refresh_marks(self, iids=None):
        for iid in (iids or list(self.labels)):
            if self.tree.exists(iid):
                self.tree.item(iid, text=self._text(iid, iid in self.checked))

    def set_checked(self, iid, on):
        kids = self.tree.get_children(iid)
        targets = list(kids) if kids else [iid]
        for t in targets:
            if not self.labels.get(t, ('', False))[1]:
                continue
            (self.checked.add if on else self.checked.discard)(t)
        parent = self.tree.parent(iid)
        self.refresh_marks(targets + [iid] + ([parent] if parent else []))
        self._changed()

    def toggle(self, iid):
        kids = self.tree.get_children(iid)
        if kids:
            on = not all(k in self.checked for k in kids)
        else:
            on = iid not in self.checked
        self.set_checked(iid, on)

    def set_all(self, on, predicate=None):
        for iid, (label, checkable) in self.labels.items():
            if not checkable or self.tree.get_children(iid):
                continue
            want = on and (predicate(iid) if predicate else True)
            (self.checked.add if want else self.checked.discard)(iid)
        self.refresh_marks()
        self._changed()

    def _click(self, ev):
        if self.tree.identify_region(ev.x, ev.y) != 'tree':
            return
        if self.tree.identify_column(ev.x) != '#0':
            return
        iid = self.tree.identify_row(ev.y)
        if not iid:
            return
        # genisletme okuna tiklanirsa sadece ac/kapa
        elem = self.tree.identify_element(ev.x, ev.y)
        if 'indicator' in str(elem):
            return
        self.toggle(iid)
        return 'break'

    def _space(self, _ev):
        for iid in self.tree.selection():
            self.toggle(iid)
        return 'break'

    def checked_payloads(self):
        return [self.payload[i] for i in self.tree_order() if i in self.checked]

    def tree_order(self):
        out = []

        def walk(p):
            for c in self.tree.get_children(p):
                out.append(c)
                walk(c)
        walk('')
        return out

    def sort(self, key):
        rev = self._sort_rev.get(key, False)
        self._sort_rev[key] = not rev

        def val(i):
            v = self.labels[i][0] if key == '#0' else self.tree.set(i, key)
            p = self.payload.get(i)
            if key == 'size' and isinstance(p, dict):
                return p.get('size_kb', 0) or 0
            return str(v).lower()
        for parent in [''] + [i for i in self.labels if self.tree.get_children(i)]:
            kids = list(self.tree.get_children(parent))
            kids.sort(key=val, reverse=rev)
            for n, k in enumerate(kids):
                self.tree.move(k, parent, n)

    def _changed(self):
        if self.on_change:
            self.on_change()


# =========================================================================== ana pencere
class NavBook(tk.Frame):
    """Sol menulu sayfa kabi. ttk.Notebook'un uygulamada kullanilan arayuzunu (add / select / tab / index /
    <<NotebookTabChanged>>) taklit eder; menu satirlari gruplar halinde nav cercevesine dizilir."""

    def __init__(self, master, nav):
        super().__init__(master, bg=PANEL)
        self.nav = nav
        self.pages = []
        self.current = None
        # 4.1: menu uzadi (23 sayfa) -> kaydirilabilir liste (fare tekerlegi); kucuk ekranlarda alttaki sayfalar kaybolmaz
        self.navcanvas = tk.Canvas(nav, bg=NAV_BG, highlightthickness=0, bd=0, height=120)
        self.navcanvas.pack(side='top', fill='both', expand=True, pady=(6, 0))
        self.navlist = tk.Frame(self.navcanvas, bg=NAV_BG)
        self._navwin = self.navcanvas.create_window(0, 0, window=self.navlist, anchor='nw')
        self.navlist.bind('<Configure>', lambda _e: self.navcanvas.configure(scrollregion=self.navcanvas.bbox('all')))
        self.navcanvas.bind('<Configure>', lambda e: self.navcanvas.itemconfigure(self._navwin, width=e.width))
        self.navcanvas.bind('<Enter>', lambda _e: self._wheel(True))
        self.navcanvas.bind('<Leave>', lambda _e: self._wheel(False))

    def _wheel(self, on):
        c = self.navcanvas
        if not on:
            for seq in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                c.unbind_all(seq)
            return

        def scroll(e):
            if c.winfo_height() >= self.navlist.winfo_reqheight():
                return
            step = -1 if (getattr(e, 'num', 0) == 4 or getattr(e, 'delta', 0) > 0) else 1
            c.yview_scroll(step * 2, 'units')
        for seq in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            c.bind_all(seq, scroll)

    def ensure_visible(self, i):
        """Secili menu satiri gorunur alanda degilse liste kaydirilir."""
        try:
            row = self.pages[i]['row']
            self.navcanvas.update_idletasks()
            total = max(1, self.navlist.winfo_reqheight())
            top, h = row.winfo_y(), self.navcanvas.winfo_height()
            y0 = self.navcanvas.canvasy(0)
            if top < y0 or top + row.winfo_height() > y0 + h:
                self.navcanvas.yview_moveto(max(0.0, (top - h / 3) / total))
        except (tk.TclError, IndexError):
            pass

    def add_group(self, title):
        tk.Label(self.navlist, text=title.upper(), bg=NAV_BG, fg=NAV_MUTED, font=('Segoe UI', 8, 'bold'), anchor='w').pack(fill='x', padx=16, pady=(8, 1))

    def add(self, frame, text='', **_kw):
        idx = len(self.pages)
        row = tk.Frame(self.navlist, bg=NAV_BG, cursor='hand2')
        row.pack(fill='x', padx=6, pady=1)
        bar = tk.Frame(row, bg=NAV_BG, width=4)
        bar.pack(side='left', fill='y')
        lab = tk.Label(row, text=text.strip(), bg=NAV_BG, fg=NAV_FG, font=('Segoe UI', 10), anchor='w', padx=12, pady=4, cursor='hand2')
        lab.pack(side='left', fill='x', expand=True)
        for w in (row, bar, lab):
            w.bind('<Button-1>', lambda _e, i=idx: self.select(i))
            w.bind('<Enter>', lambda _e, i=idx: self._hover(i, True))
            w.bind('<Leave>', lambda _e, i=idx: self._hover(i, False))
        self.pages.append({'frame': frame, 'title': text.strip(), 'row': row, 'bar': bar, 'lab': lab})

    def _index(self, which):
        if isinstance(which, int):
            return which
        if which == 'current':
            return self.current
        name = str(which)
        for i, p in enumerate(self.pages):
            if str(p['frame']) == name or p['title'] == name:
                return i
        raise tk.TclError('sayfa yok: %s' % which)

    def index(self, which):
        return self._index(which)

    def tab(self, which, option=None):
        p = self.pages[self._index(which)]
        return p['title'] if option == 'text' else {'text': p['title']}

    def select(self, which=None):
        if which is None:
            return str(self.pages[self.current]['frame']) if self.current is not None else ''
        i = self._index(which)
        if not 0 <= i < len(self.pages) or i == self.current:
            return
        if self.current is not None:
            self.pages[self.current]['frame'].pack_forget()
        self.current = i
        self.pages[i]['frame'].pack(fill='both', expand=True)
        self.refresh_nav()
        self.ensure_visible(i)
        self.event_generate('<<NotebookTabChanged>>')

    def _paint(self, i, bg, fg, bar, bold):
        p = self.pages[i]
        for w in (p['row'], p['lab']):
            w.configure(bg=bg)
        p['lab'].configure(fg=fg, font=('Segoe UI', 10, 'bold' if bold else 'normal'))
        p['bar'].configure(bg=bar)

    def _hover(self, i, on):
        if i != self.current:
            self._paint(i, PANEL2 if on else NAV_BG, NAV_FG, NAV_BG if not on else PANEL2, False)

    def refresh_nav(self):
        for i in range(len(self.pages)):
            if i == self.current:
                self._paint(i, NAV_SEL, NAV_SEL_FG, ACCENT, True)
            else:
                self._paint(i, NAV_BG, NAV_FG, NAV_BG, False)


# =========================================================================== kaydirilabilir sayfa
def make_scroll(parent, bg):
    """Uzun sayfalar icin dikey kaydirilabilir ic cerceve (fare tekerlegi imlec sayfadayken calisir). Donus: ic cerceve."""
    canvas = tk.Canvas(parent, bg=bg, highlightthickness=0, bd=0)
    sb = ttk.Scrollbar(parent, orient='vertical', command=canvas.yview)
    canvas.configure(yscrollcommand=sb.set)
    sb.pack(side='right', fill='y')
    canvas.pack(side='left', fill='both', expand=True)
    inner = tk.Frame(canvas, bg=bg)
    win = canvas.create_window(0, 0, window=inner, anchor='nw')
    inner.bind('<Configure>', lambda _e: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>', lambda e: canvas.itemconfigure(win, width=e.width))

    def scroll(e):
        if canvas.winfo_height() >= inner.winfo_reqheight():
            return
        canvas.yview_scroll((-1 if (getattr(e, 'num', 0) == 4 or getattr(e, 'delta', 0) > 0) else 1) * 3, 'units')

    def on(_e):
        for seq in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            canvas.bind_all(seq, scroll)

    def off(_e):
        for seq in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            canvas.unbind_all(seq)
    canvas.bind('<Enter>', on)
    canvas.bind('<Leave>', off)
    inner._scroll_canvas = canvas
    return inner


# =========================================================================== canli kol gorseli
class GamepadCanvas(tk.Canvas):
    """XInput durumunu cizen kol gorseli (taban olcu 500x280, DPI olcegiyle buyur)."""
    IDLE, PRESSED = '#24405f', ACCENT
    FACE = {'Y': '#e8c547', 'X': '#4f8cff', 'B': '#ff6b6b', 'A': '#4fd18b'}

    def __init__(self, master, scale=1.0):
        self.k = scale
        super().__init__(master, width=int(500 * scale), height=int(280 * scale), bg='#0e1b2e', highlightthickness=0)
        self.it = {}
        self._draw()

    def _p(self, *v):
        return [x * self.k for x in v]

    def _draw(self):
        it, p = self.it, self._p
        body = '#16304d'
        self.create_oval(*p(30, 70, 220, 250), fill=body, outline='#2b4a6e', width=2)
        self.create_oval(*p(280, 70, 470, 250), fill=body, outline='#2b4a6e', width=2)
        self.create_rectangle(*p(125, 70, 375, 225), fill=body, outline='')
        self.create_line(*p(125, 70, 375, 70), fill='#2b4a6e', width=2)
        for side, x0 in (('LT', 50), ('RT', 310)):
            self.create_rectangle(*p(x0, 22, x0 + 140, 40), outline='#2b4a6e')
            self.create_text(*p(x0 + 70, 12), text=side, fill=MUTED, font=('Segoe UI', 8, 'bold'))
        it['LT'] = self.create_rectangle(*p(50, 22, 50, 40), fill=ACCENT, outline='')
        it['RT'] = self.create_rectangle(*p(450, 22, 450, 40), fill=ACCENT, outline='')
        it['LB'] = self.create_rectangle(*p(60, 48, 180, 60), fill=self.IDLE, outline='')
        it['RB'] = self.create_rectangle(*p(320, 48, 440, 60), fill=self.IDLE, outline='')
        self.create_text(*p(120, 54), text='LB', fill=FG, font=('Segoe UI', 7, 'bold'))
        self.create_text(*p(380, 54), text='RB', fill=FG, font=('Segoe UI', 7, 'bold'))
        self.create_oval(*p(60, 95, 140, 175), fill='#0b1626', outline='#2b4a6e', width=2)
        self.create_oval(*p(280, 160, 360, 240), fill='#0b1626', outline='#2b4a6e', width=2)
        it['LS'] = self.create_oval(*p(88, 123, 112, 147), fill=MUTED, outline='')
        it['RS'] = self.create_oval(*p(308, 188, 332, 212), fill=MUTED, outline='')
        for k, box in {'DPAD_UP': (160, 160, 180, 180), 'DPAD_DOWN': (160, 200, 180, 220), 'DPAD_LEFT': (140, 180, 160, 200), 'DPAD_RIGHT': (180, 180, 200, 200)}.items():
            it[k] = self.create_rectangle(*p(*box), fill=self.IDLE, outline='')
        self.create_rectangle(*p(160, 180, 180, 200), fill=self.IDLE, outline='')
        for k, (cx, cy) in {'Y': (390, 105), 'X': (360, 135), 'B': (420, 135), 'A': (390, 165)}.items():
            it[k] = self.create_oval(*p(cx - 14, cy - 14, cx + 14, cy + 14), fill=self.IDLE, outline=self.FACE[k], width=2)
            self.create_text(*p(cx, cy), text=k, fill=FG, font=('Segoe UI', 9, 'bold'))
        it['BACK'] = self.create_oval(*p(215, 115, 235, 135), fill=self.IDLE, outline='')
        it['START'] = self.create_oval(*p(265, 115, 285, 135), fill=self.IDLE, outline='')
        self.create_text(*p(225, 146), text='view', fill=MUTED, font=('Segoe UI', 7))
        self.create_text(*p(275, 146), text='menu', fill=MUTED, font=('Segoe UI', 7))
        it['msg'] = self.create_text(*p(250, 268), text='', fill=MUTED, font=('Segoe UI', 9))

    def show(self, st, message=''):
        it, p = self.it, self._p
        self.itemconfig(it['msg'], text=message)
        b = st['buttons'] if st else 0
        for k in ('LB', 'RB', 'BACK', 'START', 'DPAD_UP', 'DPAD_DOWN', 'DPAD_LEFT', 'DPAD_RIGHT'):
            self.itemconfig(it[k], fill=self.PRESSED if b & dict(core.XINPUT_BUTTONS)[k] else self.IDLE)
        for k in ('A', 'B', 'X', 'Y'):
            self.itemconfig(it[k], fill=self.FACE[k] if b & dict(core.XINPUT_BUTTONS)[k] else self.IDLE)
        lx, ly, rx, ry = ((st['lx'], st['ly'], st['rx'], st['ry']) if st else (0, 0, 0, 0))
        ox, oy = lx / 32768 * 26, -ly / 32768 * 26
        self.coords(it['LS'], *p(88 + ox, 123 + oy, 112 + ox, 147 + oy))
        ox, oy = rx / 32768 * 26, -ry / 32768 * 26
        self.coords(it['RS'], *p(308 + ox, 188 + oy, 332 + ox, 212 + oy))
        self.itemconfig(it['LS'], fill=OK_C if b & 0x0040 else MUTED)
        self.itemconfig(it['RS'], fill=OK_C if b & 0x0080 else MUTED)
        lt, rt = (st['lt'], st['rt']) if st else (0, 0)
        self.coords(it['LT'], *p(50, 22, 50 + 140 * lt / 255, 40))
        self.coords(it['RT'], *p(450 - 140 * rt / 255, 22, 450, 40))


def app_data_dir():
    core.APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return core.APP_DATA_DIR
