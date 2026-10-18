"""AGFO System Care 3.0.0 - acik kaynak motorlari kendi arayuzu icinde calistiran Windows bakim uygulamasi.

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
import agfo_github_update as ghu  # noqa: E402

VERSION = core.VERSION
LOG_DIR = core.LOG_DIR
LOG_RETENTION_DAYS = 30
LOG_WIDGET_MAX_LINES = 6000
LOG_WIDGET_TRIM_LINES = 1500
POLL_MS = 80
BG, PANEL, PANEL2, FG, MUTED, ACCENT = '#0a1425', '#12243b', '#192e48', '#ecf3ff', '#a5b6ce', '#49b3ef'
WARN, OK_C, BAD_C = '#e2b356', '#6fd39b', '#ff8a80'
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
INTERNAL_PS_ACTIONS = ['controller-list','controller-reset','bt-restart','phantom-list','phantom-remove','appx-list','appx-remove','driver-analyze','driver-scan','driver-install','devices','drivers-list','driver-backup','app-scan','app-update','recycle-paths']
ADMIN_ACTIONS = {'controller-reset','bt-restart','phantom-remove','driver-install','driver-backup','component-analyze','component-clean','health-scan','health-repair','restore-point','sdio-scan','sdio-install'}
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
                 after=None, cwd=None, show_output=True):
        self.title, self.cmd, self.shell, self.func = title, cmd, shell, func
        self.on_done, self.cancel_ok, self.tail_dir, self.after = on_done, cancel_ok, tail_dir, after
        self.cwd, self.show_output = cwd, show_output
        self.lines, self.data, self.code, self.logfile = [], [], None, ''


class Runner:
    def __init__(self, post):
        self.post = post
        self.proc = None
        self.stop = threading.Event()

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
                if job.cmd:
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
                                    creationflags=CREATIONFLAGS, cwd=job.cwd or str(BASE))
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
        self.tree.tag_configure('risky', foreground=WARN)
        self.tree.tag_configure('orphan', foreground=BAD_C)
        self.tree.tag_configure('group', font=('Segoe UI', 10, 'bold'))
        self.tree.tag_configure('muted', foreground=MUTED)
        for tg, col in (('st_new', OK_C), ('st_missing', BAD_C), ('st_problem', WARN), ('st_warn', WARN), ('st_old', MUTED), ('st_ok', FG)):
            self.tree.tag_configure(tg, foreground=col)

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


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.admin = core.is_admin()
        self.settings = core.load_settings()
        self.title('AGFO System Care ' + VERSION + (' — Yönetici' if self.admin else ''))
        self.scale = max(1.0, self.winfo_fpixels('1i') / 96.0)
        self.geometry('%dx%d' % (int(1220 * self.scale), int(860 * self.scale)))
        self.minsize(int(980 * self.scale), int(680 * self.scale))
        self.configure(bg=BG)
        self._set_icon()
        self.messages = queue.Queue()
        self.runner = Runner(self.messages.put)
        self.busy = False
        self.in_callback = False
        self.pending = []
        self.progress_active = False
        self.action_buttons = []
        self.engines = {}
        self.programs = []
        self.bb_loaded = False
        self.install_dir = BASE
        self.backup_root = core.APP_DATA_DIR / 'update-backups'
        self.no_restart = False
        self.xi = core.XInputReader()
        self._style()
        self._build()
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        threading.Thread(target=prune_old_logs, daemon=True).start()
        self.after(POLL_MS, self.poll)
        self.after(150, self.refresh_engines)
        self.after(300, self._pad_tick)
        if self.settings.get('auto_update_check', True):
            self.after(2500, lambda: self.gh_check(force=False))

    # ------------------------------------------------------------------ iskelet
    def _set_icon(self):
        ico = BASE / 'assets' / 'agfo.ico'
        if IS_WIN and ico.is_file():
            try:
                self.iconbitmap(default=str(ico))
            except Exception:
                pass

    def _style(self):
        s = ttk.Style(self)
        s.theme_use('clam')
        s.configure('.', background=PANEL, foreground=FG, fieldbackground=PANEL2, font=('Segoe UI', 10))
        s.configure('TNotebook', background=BG, borderwidth=0)
        s.configure('TNotebook.Tab', background=PANEL2, foreground=FG, padding=(16, 9), font=('Segoe UI', 10))
        s.map('TNotebook.Tab', background=[('selected', '#285475')], foreground=[('selected', '#ffffff')])
        s.configure('Card.TFrame', background=PANEL)
        s.configure('Treeview', background='#0e1b2e', fieldbackground='#0e1b2e', foreground=FG, rowheight=int(24 * self.scale), borderwidth=0)
        s.configure('Treeview.Heading', background=PANEL2, foreground=FG, font=('Segoe UI', 9, 'bold'), relief='flat')
        s.map('Treeview', background=[('selected', '#285475')], foreground=[('selected', '#ffffff')])
        s.map('Treeview.Heading', background=[('active', '#285475')])
        s.configure('TCheckbutton', background=PANEL, foreground=FG, indicatorbackground='#0e1b2e', indicatorforeground=FG)
        s.map('TCheckbutton', background=[('active', PANEL)], indicatorbackground=[('selected', '#285475')])
        s.configure('Alt.TCheckbutton', background=PANEL2, foreground=FG, indicatorbackground='#0e1b2e', indicatorforeground=FG)
        s.map('Alt.TCheckbutton', background=[('active', PANEL2)], indicatorbackground=[('selected', '#285475')])
        s.configure('TCombobox', fieldbackground=PANEL2, background=PANEL2, foreground=FG, arrowcolor=FG, selectbackground=PANEL2, selectforeground=FG)
        s.map('TCombobox', fieldbackground=[('readonly', PANEL2)], foreground=[('readonly', FG)], selectbackground=[('readonly', PANEL2)], selectforeground=[('readonly', FG)])
        self.option_add('*TCombobox*Listbox.background', PANEL2)
        self.option_add('*TCombobox*Listbox.foreground', FG)
        self.option_add('*TCombobox*Listbox.selectBackground', '#285475')
        s.configure('TEntry', fieldbackground=PANEL2, foreground=FG, insertcolor=FG)
        s.configure('Vertical.TScrollbar', background=PANEL2, troughcolor=PANEL, arrowcolor=FG)

    def btn(self, parent, text, cmd, kind='normal', action=True, side='left', **kw):
        colors = {'normal': '#285475', 'danger': '#685229', 'ghost': PANEL2, 'go': '#1f6a4a'}
        b = tk.Button(parent, text=text, command=cmd, bg=colors[kind], fg='#ffffff', activebackground=ACCENT, relief='flat',
                      cursor='hand2', padx=12, pady=6, font=('Segoe UI', 9, 'bold'), disabledforeground='#7f8ea3', **kw)
        b.pack(side=side, padx=(0, 6), pady=2)
        if action:
            self.action_buttons.append(b)
        return b

    def label(self, parent, text, muted=True, **kw):
        l = tk.Label(parent, text=text, fg=MUTED if muted else FG, bg=PANEL, font=('Segoe UI', 9), justify='left', anchor='w', **kw)
        return l

    def _build(self):
        top = tk.Frame(self, bg=BG); top.pack(fill='x', padx=22, pady=(16, 6))
        tk.Label(top, text='AGFO  /  SUPERTOOLS', fg=ACCENT, bg=BG, font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        tk.Label(top, text='System Care ' + '.'.join(VERSION.split('.')[:2]), fg=FG, bg=BG, font=('Segoe UI', 22, 'bold')).pack(anchor='w')
        tk.Label(top, text='BleachBit · Bulk Crap Uninstaller · Snappy Driver Installer Origin · WinGet · Windows Update — tek arayüzde',
                 fg=MUTED, bg=BG, font=('Segoe UI', 10)).pack(anchor='w', pady=(2, 0))
        st = tk.Frame(self, bg=PANEL, padx=12, pady=8); st.pack(fill='x', padx=22, pady=8)
        self.status = tk.StringVar(value=('Hazır (yönetici)' if self.admin else 'Hazır (standart kullanıcı)') + ' — işlemler siz başlatmadıkça uygulanmaz.')
        tk.Label(st, textvariable=self.status, fg=FG, bg=PANEL, font=('Segoe UI', 10)).pack(side='left')
        self.cancel_btn = tk.Button(st, text='Durdur', command=self.cancel, relief='flat', bg='#6b2a2a', fg=FG, padx=12, pady=4, state='disabled')
        self.cancel_btn.pack(side='right')
        tk.Button(st, text='Güncelleme…', command=self.open_updater, relief='flat', bg='#1f6a4a', fg='#ffffff', padx=12, pady=4,
                  activebackground=ACCENT, cursor='hand2').pack(side='right', padx=(0, 8))
        if not self.admin:
            tk.Button(st, text='Yönetici olarak yeniden aç', command=self.elevate, relief='flat', bg=PANEL2, fg=FG, padx=12, pady=4).pack(side='right', padx=(0, 8))

        self.gh_banner = tk.Frame(self, bg='#1d4d3a', padx=12, pady=7)   # yeni surum varsa gosterilir
        self.gh_banner_text = tk.StringVar(value='')
        tk.Label(self.gh_banner, textvariable=self.gh_banner_text, fg='#ffffff', bg='#1d4d3a', font=('Segoe UI', 10, 'bold')).pack(side='left')
        for txt, cmd, bg in (('Bu sürümü atla', self.gh_skip, '#2a5f4a'), ('Notlar', self.gh_show_notes, '#2a5f4a'), ('Şimdi güncelle', self.gh_update, '#2f8f5f')):
            tk.Button(self.gh_banner, text=txt, command=cmd, bg=bg, fg='#ffffff', relief='flat', padx=12, pady=3, cursor='hand2',
                      activebackground=ACCENT).pack(side='right', padx=(6, 0))
        self.gh_result = None
        paned = tk.PanedWindow(self, orient='vertical', bg=BG, sashwidth=6, bd=0)
        self.paned = paned
        paned.pack(fill='both', expand=True, padx=22, pady=(0, 16))
        self.tabs = ttk.Notebook(paned)
        paned.add(self.tabs, stretch='always', minsize=int(360 * self.scale))
        for title, builder in [('  Motorlar  ', self._tab_engines), ('  Temizlik  ', self._tab_clean), ('  Programlar  ', self._tab_programs), ('  Bloatware  ', self._tab_bloat),
                               ('  Sürücüler  ', self._tab_drivers), ('  Aygıt temizliği  ', self._tab_phantom), ('  Uygulama güncellemeleri  ', self._tab_apps), ('  Bakım ve sağlık  ', self._tab_maint),
                               ('  Kol / Gamepad  ', self._tab_pad)]:
            f = tk.Frame(self.tabs, bg=PANEL)
            self.tabs.add(f, text=title)
            builder(f)

        bottom = tk.Frame(paned, bg=BG)
        paned.add(bottom, stretch='never', minsize=int(140 * self.scale))
        bar = tk.Frame(bottom, bg=BG); bar.pack(fill='x', pady=(8, 0))
        tk.Label(bar, text='İŞLEM GÜNLÜĞÜ', bg=BG, fg=ACCENT, font=('Segoe UI', 10, 'bold')).pack(side='left')
        tk.Button(bar, text='Günlük klasörünü aç', command=self.open_logs, bg=PANEL2, fg=FG, relief='flat').pack(side='right')
        tk.Button(bar, text='Temizle', command=self.clear_log, bg=PANEL2, fg=FG, relief='flat').pack(side='right', padx=(0, 8))
        self.log = tk.Text(bottom, height=7, bg='#09111e', fg='#dce8fa', insertbackground=FG, relief='flat', font=('Consolas', 9),
                           padx=10, pady=8, wrap='word', undo=False)
        self.log.pack(fill='both', expand=True, pady=(6, 0))
        self.log.configure(state='disabled')
        self.write('AGFO System Care %s — motorlar bu pencerede çalışır; hiçbir işlem web sayfasına yönlendirmez.\n' % VERSION)
        if not self.admin:
            self.write('Not: sürücü kurulumu, SDIO, DISM/SFC ve geri yükleme noktası yönetici ister.\n')

    # ------------------------------------------------------------------ MOTORLAR
    def _tab_engines(self, f):
        self.label(f, 'Açık kaynak motorlar resmî kaynaklarından kurulur ve AGFO arayüzü içinden çalıştırılır. BleachBit, yönetici yetkisi '
                      'gerektirmeyen resmî taşınabilir paketiyle AGFO motor klasörüne kurulur; BCU ve SDIO için WinGet, olmazsa resmî taşınabilir paket kullanılır. '
                      'Kaynak kodları bu pakete dahil değildir; her motor kendi lisansıyla kurulur.', wraplength=int(1000 * self.scale)).pack(fill='x', padx=16, pady=(12, 6))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Durumu yenile', self.refresh_engines, 'ghost')
        self.btn(bar, 'Eksik motorları kur', lambda: self.engine_op('install-missing'), 'go')
        self.btn(bar, 'Seçili motoru kur / güncelle', lambda: self.engine_op('install'))
        self.btn(bar, 'Seçili motoru kaldır', lambda: self.engine_op('uninstall'), 'danger')
        self.btn(bar, 'SDIO klasörünü elle seç', self.pick_sdio_dir, 'ghost')
        cols = [('state', 'Durum', 100, 'w'), ('ver', 'Sürüm', 90, 'w'), ('src', 'Kurulum türü', 190, 'w'), ('lic', 'Lisans', 85, 'w'),
                ('role', 'AGFO içindeki görevi', 330, 'w'), ('path', 'Konum', 380, 'w')]
        self.eng_tree = CheckTree(f, cols, first=('Motor', 270), height=6)
        self.eng_tree.pack(fill='both', expand=True, padx=16, pady=10)

    def refresh_engines(self):
        def work(runner, job):
            job.data = [core.engine_status(self.settings)]
            return 0
        self.start([Job('Motor durumu', func=work, on_done=self._engines_done, cancel_ok=False)], quiet=True)

    def _engines_done(self, job):
        if not job.data:
            return
        self.engines = job.data[0]
        t = self.eng_tree
        t.clear()
        wg = self.engines.get('winget', {}).get('path')
        t.add('winget', 'WinGet (Microsoft)', ('Hazır' if wg else 'YOK', '', 'Windows', 'MIT', 'Uygulama güncellemeleri ve yedek motor kurulumu', wg or 'Microsoft Store > Uygulama Yükleyici'),
              checkable=False, tags=() if wg else ('orphan',))
        for key, meta in core.ENGINES.items():
            e = self.engines.get(key, {})
            path = e.get('path') or e.get('console')
            extra = ''
            if key == 'bcu' and e.get('console'):
                extra = '  (+ BCU-console)'
            t.add(key, meta['name'], ('Kurulu' if path else 'Kurulu değil', e.get('version', ''), e.get('source', ''), meta['license'], meta['role'], (path or '—') + extra),
                  tags=() if path else ('risky',), payload=key)
        self._update_engine_dependent()

    def _update_engine_dependent(self):
        bb = bool(self.engines.get('bleachbit', {}).get('path'))
        self.bb_state.set('BleachBit motoru: ' + ('hazır — ' + self.engines['bleachbit']['path'] if bb else 'kurulu değil (Motorlar sekmesinden kurun)'))
        bcu = self.engines.get('bcu', {})
        self.bcu_state.set('BCU motoru: ' + ('hazır' + (' (konsol motoru ile genişletilmiş tarama kullanılabilir)' if bcu.get('console') else '') if (bcu.get('path') or bcu.get('console')) else 'kurulu değil — yerleşik kayıt taraması kullanılıyor'))
        sd = self.engines.get('sdio', {}).get('path')
        self.sdio_state.set('SDIO motoru: ' + ('hazır — ' + sd if sd else 'kurulu değil (Motorlar sekmesinden kurun)'))

    ENGINE_METHODS = {'bleachbit': ('portable', 'winget'), 'bcu': ('winget', 'portable'), 'sdio': ('winget', 'portable')}

    def _engine_present(self, key, st=None):
        e = (st or self.engines).get(key, {})
        return bool(e.get('path') or e.get('console'))

    def install_engine_job(self, key, upgrade=False):
        """Motoru kurar: once tercih edilen yol, olmazsa digeri. BleachBit icin taşınabilir paket (yönetici gerektirmez) önce gelir:
        BleachBit kurulum programi sessiz kipte /allusers ve yonetici yetkisi ister; WinGet sessiz kurulumu bu yuzden dusebilir."""
        name = core.ENGINES[key]['name']
        admin = self.admin

        def work(runner, job):
            errors = []
            for method in self.ENGINE_METHODS[key]:
                if runner.stop.is_set():
                    return -1
                if method == 'portable':
                    runner.say('[%s] Resmî taşınabilir paket deneniyor (yönetici gerekmez)...' % name)
                    try:
                        path = core.install_portable(key, runner.say, runner.progress_cb('İndiriliyor'), runner.stop.is_set)
                        runner.say('[%s] Hazır: %s' % (name, path))
                        return 0
                    except Exception as e:
                        errors.append('taşınabilir: %s' % e)
                        runner.say('[%s] Taşınabilir kurulum olmadı: %s' % (name, e))
                else:
                    wg = core.find_winget()
                    if not wg:
                        errors.append('WinGet yok')
                        runner.say('[%s] WinGet bulunamadı; atlanıyor.' % name)
                        continue
                    cmd = core.winget_install_cmd(wg, core.ENGINES[key]['winget'], upgrade=upgrade and self._engine_present(key))
                    if key == 'bleachbit':
                        cmd += ['--override', '/S /allusers'] if admin else ['--override', '/S /currentuser']
                    code, lines = runner.run_cmd('WinGet: ' + name, cmd)
                    st = core.engine_status(self.settings)
                    already = (code & 0xFFFFFFFF) in (0x8A15002B, 0x8A150061, 0x8A15010D) if isinstance(code, int) else False
                    if self._engine_present(key, st):
                        e = st.get(key, {})
                        runner.say('[%s] %s: %s' % (name, 'Zaten kurulu, kullanılıyor' if already else 'WinGet ile kuruldu', e.get('path') or e.get('console')))
                        return 0
                    if already or code == 0:
                        regs = core.registry_install_dirs({'bleachbit': r'^BleachBit', 'bcu': r'BCUninstaller|Bulk Crap Uninstaller', 'sdio': r'Snappy Driver'}[key])
                        msg = ('WinGet paketi kurulu sayıyor ama çalıştırılabilir dosya bulunamadı' +
                               (' (kayıtlı konum: %s — kurulum yarım kalmış olabilir; Programlar sekmesinden kaldırıp tekrar kurabilirsiniz)' % ', '.join(regs) if regs else
                                ' ve kayıt defterinde kurulum konumu yok (kurulum yarım kalmış olabilir)'))
                    else:
                        msg = core.winget_code_text(code)
                    errors.append('WinGet: %s' % msg)
                    runner.say('[%s] WinGet kurulumu tamamlanamadı (%s).%s' % (name, msg, '' if admin else ' Yönetici olarak açıp tekrar denemek gerekebilir.'))
            runner.say('[%s] KURULAMADI — %s' % (name, ' | '.join(errors)))
            return 2
        return Job(('Güncelle: ' if upgrade else 'Kur: ') + name, func=work, cancel_ok=True)

    def engine_op(self, op):
        if op == 'install-missing':
            keys = [k for k in core.ENGINES if not self._engine_present(k)]
            if not keys:
                messagebox.showinfo('Motorlar', 'Tüm motorlar zaten kurulu.')
                return
        else:
            keys = [p for p in self.eng_tree.checked_payloads() if p] or [i for i in self.eng_tree.tree.selection() if i in core.ENGINES]
            if not keys:
                messagebox.showinfo('Motorlar', 'Önce listeden bir motor işaretleyin.')
                return
        names = ', '.join(core.ENGINES[k]['name'] for k in keys)
        if op == 'uninstall':
            if not messagebox.askyesno('Motoru kaldır', names + ' kaldırılsın mı?'):
                return
            jobs = []
            for k in keys:
                path = self.engines.get(k, {}).get('path') or self.engines.get(k, {}).get('console') or ''
                folder = core.ENGINE_DIR / {'bleachbit': 'BleachBit', 'bcu': 'BCU', 'sdio': 'SDIO'}[k]
                if path and str(folder).lower() in path.lower():
                    def rm(runner, job, folder=folder):
                        import shutil
                        shutil.rmtree(folder, ignore_errors=True)
                        runner.say('Kaldırıldı: %s' % folder)
                        return 0
                    jobs.append(Job('Kaldır: ' + core.ENGINES[k]['name'], func=rm, cancel_ok=False))
                else:
                    wg = core.find_winget()
                    if wg:
                        jobs.append(Job('Kaldır: ' + core.ENGINES[k]['name'], cmd=core.winget_uninstall_cmd(wg, core.ENGINES[k]['winget']), cancel_ok=False))
        else:
            if not messagebox.askyesno('Motor kurulumu', names + '\n\nMotorlar resmî kaynaklarından kurulur: BleachBit için resmî taşınabilir paket '
                                       '(yönetici gerekmez), diğerleri için WinGet; olmazsa diğer yol denenir. Devam edilsin mi?'):
                return
            jobs = [self.install_engine_job(k, upgrade=(op == 'install' and self._engine_present(k))) for k in keys]
        if not jobs:
            return
        jobs[-1].on_done = lambda j: self.refresh_engines()
        self.start(jobs)

    def pick_sdio_dir(self):
        d = filedialog.askdirectory(title='SDIO klasörünü seçin (SDIO_x64_R*.exe bulunan klasör)')
        if not d:
            return
        self.settings['sdio_dir'] = d
        core.save_settings(self.settings)
        self.refresh_engines()

    # ------------------------------------------------------------------ TEMIZLIK (BleachBit)
    def _tab_clean(self, f):
        self.bb_state = tk.StringVar(value='BleachBit motoru: denetleniyor...')
        tk.Label(f, textvariable=self.bb_state, fg=MUTED, bg=PANEL, font=('Segoe UI', 9)).pack(anchor='w', padx=16, pady=(12, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Temizleyicileri yükle', self.bb_load, 'ghost')
        self.btn(bar, 'Güvenli öneriyi seç', self.bb_preset, 'ghost')
        self.btn(bar, 'Seçimi kaldır', lambda: self.bb_tree.set_all(False), 'ghost', action=False)
        self.btn(bar, 'Önizle (silmez)', lambda: self.bb_run('preview'))
        self.btn(bar, 'Seçilenleri temizle', lambda: self.bb_run('clean'), 'danger')
        self.bb_count = tk.StringVar(value='')
        tk.Label(bar, textvariable=self.bb_count, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(side='right')
        cols = [('opt', 'Kimlik', 260, 'w'), ('note', 'Not', 380, 'w')]
        self.bb_tree = CheckTree(f, cols, first=('Temizleyici / seçenek', 360), on_change=self._bb_count)
        self.bb_tree.pack(fill='both', expand=True, padx=16, pady=8)
        self.bb_summary = tk.StringVar(value='Turuncu satırlar kullanıcı verisini (parola, çerez, oturum) siler veya saatler sürer; güvenli öneriye dahil edilmez.')
        tk.Label(f, textvariable=self.bb_summary, fg=MUTED, bg=PANEL, font=('Segoe UI', 9), anchor='w', justify='left').pack(fill='x', padx=16, pady=(0, 10))

    def _bb_count(self):
        n = len([i for i in self.bb_tree.checked if not self.bb_tree.tree.get_children(i)])
        self.bb_count.set('%d seçenek seçili' % n if n else '')

    def bb_load(self):
        bb = self.engines.get('bleachbit', {}).get('path')
        if not bb:
            if messagebox.askyesno('BleachBit yok', 'BleachBit motoru kurulu değil. Resmî taşınabilir paket şimdi kurulsun mu? (yönetici gerekmez)'):
                self._engine_install_one('bleachbit')
            return
        self.start([Job('BleachBit temizleyicileri', cmd=[bb, '--list-cleaners'], on_done=self._bb_loaded, show_output=False)])

    def _engine_install_one(self, key):
        j = self.install_engine_job(key)
        j.on_done = lambda _j: self.refresh_engines()
        self.start([j])

    def _bb_loaded(self, job):
        cleaners = core.parse_bleachbit_cleaners(job.lines)
        if not cleaners:
            self.write('BleachBit temizleyici listesi okunamadı.\n')
            return
        saved = set(self.settings.get('bb_selected') or [])
        t = self.bb_tree
        t.clear()
        order = sorted(cleaners, key=lambda c: (c not in ('system', 'windows_explorer'), core.bb_label(c).lower()))
        for cl in order:
            t.add('c:' + cl, core.bb_label(cl), (cl, '%d seçenek' % len(cleaners[cl])), tags=('group',))
            for op in cleaners[cl]:
                key = cl + '.' + op
                risky = core.bb_is_risky(cl, op)
                note = 'Dikkat: kullanıcı verisi / çok uzun sürebilir' if risky else ''
                on = (key in saved) if saved else core.bb_default_selected(cl, op)
                t.add('o:' + key, core.bb_label(cl, op), (key, note), parent='c:' + cl, checked=on, tags=('risky',) if risky else (), payload=key)
        t.refresh_marks()
        self.bb_loaded = True
        self._bb_count()
        self.write('BleachBit: %d temizleyici, %d seçenek yüklendi.\n' % (len(cleaners), sum(len(v) for v in cleaners.values())))

    def bb_preset(self):
        if not self.bb_loaded:
            self.bb_load(); return
        self.bb_tree.set_all(True, lambda iid: core.bb_default_selected(*iid[2:].split('.', 1)))

    def bb_run(self, mode):
        bb = self.engines.get('bleachbit', {}).get('path')
        if not bb or not self.bb_loaded:
            self.bb_load(); return
        sel = self.bb_tree.checked_payloads()
        if not sel:
            messagebox.showinfo('Temizlik', 'En az bir seçenek işaretleyin.'); return
        self.settings['bb_selected'] = sel
        core.save_settings(self.settings)
        if mode == 'clean':
            risky = [s for s in sel if core.bb_is_risky(*s.split('.', 1))]
            msg = '%d seçenek temizlenecek. Silinen veriler geri alınamaz.' % len(sel)
            if risky:
                msg += '\n\nDİKKAT — şu seçenekler kullanıcı verisi siler veya çok uzun sürer:\n  ' + '\n  '.join(risky[:12])
            if not messagebox.askyesno('Temizliği onaylayın', msg + '\n\nÖnizleme yaptınız mı? Devam edilsin mi?'):
                return
        flag = '--preview' if mode == 'preview' else '--clean'
        title = 'BleachBit ' + ('önizleme' if mode == 'preview' else 'temizlik')
        self.start([Job(title, cmd=[bb, flag] + sel, on_done=self._bb_done, cancel_ok=(mode == 'preview'))])

    def _bb_done(self, job):
        s = core.parse_bleachbit_summary(job.lines)
        self.bb_summary.set(('Sonuç: ' + ' · '.join(s)) if s else 'Tamamlandı (çıktı günlükte).')

    # ------------------------------------------------------------------ PROGRAMLAR (BCU entegrasyonu)
    def _tab_programs(self, f):
        self.bcu_state = tk.StringVar(value='BCU motoru: denetleniyor...')
        tk.Label(f, textvariable=self.bcu_state, fg=MUTED, bg=PANEL, font=('Segoe UI', 9)).pack(anchor='w', padx=16, pady=(12, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Programları tara', self.prog_scan, 'ghost')
        self.btn(bar, 'BCU motoruyla genişlet', self.prog_bcu_scan, 'ghost')
        self.btn(bar, 'Seçilenleri kaldır', self.prog_uninstall, 'danger')
        self.btn(bar, 'Yetim kayıtları temizle', self.prog_remove_orphans, 'ghost')
        self.btn(bar, 'BCU tam arayüzü', self.prog_open_bcu, 'ghost')
        self.quiet_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text='Mümkünse sessiz kaldır', variable=self.quiet_var).pack(side='left', padx=8)
        flt = tk.Frame(f, bg=PANEL); flt.pack(fill='x', padx=16, pady=(6, 0))
        tk.Label(flt, text='Ara:', fg=FG, bg=PANEL).pack(side='left')
        self.prog_q = tk.StringVar()
        e = ttk.Entry(flt, textvariable=self.prog_q, width=36); e.pack(side='left', padx=6)
        self.prog_filter = ttk.Combobox(flt, state='readonly', width=26, values=['Tümü', 'Sessiz kaldırılabilir', 'Yetim kayıtlar', 'Kullanıcıya özel', 'Son 30 gün', 'Bilinen bloatware'])
        self.prog_filter.current(0); self.prog_filter.pack(side='left', padx=6)
        self.prog_q.trace_add('write', lambda *_: self._prog_render())
        self.prog_filter.bind('<<ComboboxSelected>>', lambda _e: self._prog_render())
        self.prog_count = tk.StringVar(value='')
        tk.Label(flt, textvariable=self.prog_count, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(side='right')
        cols = [('pub', 'Yayıncı', 200, 'w'), ('ver', 'Sürüm', 110, 'w'), ('size', 'Boyut', 80, 'e'), ('date', 'Kurulum', 90, 'w'),
                ('kind', 'Tür', 90, 'w'), ('silent', 'Sessiz', 60, 'center'), ('scope', 'Kapsam', 120, 'w')]
        self.prog_tree = CheckTree(f, cols, first=('Program', 330), on_change=self._prog_count)
        self.prog_tree.pack(fill='both', expand=True, padx=16, pady=8)
        self.label(f, 'Kaldırma sonrası kalan klasörler (artıklar) yalnızca kesin eşleşmeyle bulunur ve onayınızla Geri Dönüşüm Kutusu\'na taşınır. '
                      'Kırmızı satırlar: kaldırıcısı silinmiş yetim kayıtlar.', wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(0, 10))

    def _prog_count(self):
        n = len(self.prog_tree.checked)
        self.prog_count.set(('%d / %d program' % (len(self.prog_tree.labels), len(self.programs))) + (' · %d seçili' % n if n else ''))

    def prog_scan(self, then=None):
        def work(runner, job):
            t0 = time.time()
            job.data = core.annotate_programs(core.read_programs())
            runner.say('Kayıt taraması: %d program, %.2f sn' % (len(job.data), time.time() - t0))
            return 0
        self.start([Job('Program envanteri', func=work, on_done=lambda j: self._prog_loaded(j, then), cancel_ok=False)])

    def _prog_loaded(self, job, then=None):
        keep = {(p['name'], p['version']) for p in self.prog_tree.checked_payloads()} if self.prog_tree.labels else set()
        self.programs = job.data or []
        self._prog_render(keep)
        if then:
            then()

    def _prog_render(self, keep=None):
        if keep is None:
            keep = {(p['name'], p['version']) for p in self.prog_tree.checked_payloads()}
        q = self.prog_q.get().strip().lower()
        mode = self.prog_filter.get()
        cutoff = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
        t = self.prog_tree
        t.clear()
        for i, p in enumerate(self.programs):
            if q and q not in (p['name'] + ' ' + p['publisher']).lower():
                continue
            if mode == 'Sessiz kaldırılabilir' and not p.get('silent'):
                continue
            if mode == 'Yetim kayıtlar' and not p.get('orphan'):
                continue
            if mode == 'Kullanıcıya özel' and p['hive'] != 'HKCU':
                continue
            if mode == 'Son 30 gün' and not (p['date'] and p['date'] >= cutoff):
                continue
            if mode == 'Bilinen bloatware' and not core.classify_win32(p['name']):
                continue
            vals = (p['publisher'], p['version'], core.human_size(p['size_kb']), p['date'], p['kind'], 'evet' if p.get('silent') else '', p['scope'])
            t.add('p%d' % i, p['name'], vals, checked=(p['name'], p['version']) in keep, payload=p, tags=('orphan',) if p.get('orphan') else ())
        self._prog_count()

    def prog_bcu_scan(self):
        con = self.engines.get('bcu', {}).get('console')
        if not con:
            if messagebox.askyesno('BCU motoru yok', 'BCU (Bulk Crap Uninstaller) kurulu değil. Şimdi WinGet ile kurulsun mu?\n'
                                   'Kurulumdan sonra Store uygulamaları, Steam oyunları ve yetim kurulumlar da listelenir.'):
                self._engine_install_one('bcu')
            return
        out = app_data_dir() / 'bcu-export.xml'

        def after(runner, job):
            try:
                rows = core.parse_bcu_export(out.read_text(encoding='utf-8-sig', errors='replace'))
            except OSError:
                rows = []
            job.data = rows
            runner.say('BCU motoru: %d kayıt okundu.' % len(rows))
        j = Job('BCU envanter taraması', cmd=[con, 'export', str(out), '/Q', '/U'], after=after,
                on_done=lambda jb: self._prog_merge(jb))
        if not self.programs:
            self.prog_scan(then=lambda: self.start([j]))
        else:
            self.start([j])

    def _prog_merge(self, job):
        added = core.merge_bcu_programs(self.programs, job.data or [])
        self.write('BCU motoru %d ek uygulama buldu (Store/Steam/yetim vb.).\n' % added)
        self._prog_render()

    def prog_open_bcu(self):
        gui = self.engines.get('bcu', {}).get('path')
        if not gui:
            if messagebox.askyesno('BCU yok', 'BCU kurulu değil. WinGet ile kurulsun mu?'):
                self._engine_install_one('bcu')
            return
        try:
            core.shell_execute(gui, '')
            self.write('BCU masaüstü arayüzü açıldı: %s\n' % gui)
        except OSError as e:
            messagebox.showerror('BCU', str(e))

    def prog_uninstall(self):
        sel = [p for p in self.prog_tree.checked_payloads() if p]
        if not sel:
            messagebox.showinfo('Programlar', 'Kaldırılacak programları işaretleyin.'); return
        orphans = [p for p in sel if p.get('orphan')]
        sel = [p for p in sel if not p.get('orphan')]
        if orphans:
            self.write('%d yetim kayıt atlandı (kaldırıcısı yok); "Yetim kayıtları temizle" kullanın.\n' % len(orphans))
        if not sel:
            return
        quiet = self.quiet_var.get()
        names = '\n  '.join(p['name'] + ('  [sessiz]' if quiet and p.get('silent') else '') for p in sel[:20])
        if not messagebox.askyesno('Kaldırmayı onaylayın', '%d program sırayla kaldırılacak:\n  %s%s\n\nSessiz kaldırıcısı olmayanlar kendi '
                                   'penceresini açar. Devam edilsin mi?' % (len(sel), names, '\n  ...' if len(sel) > 20 else '')):
            return
        jobs = []
        for p in sel:
            exe, params = core.build_uninstall(p, quiet)
            jobs.append(Job('Kaldır: ' + p['name'], shell=(exe, params), after=self._after_uninstall(p), cancel_ok=True))
        jobs[-1].on_done = lambda j: self.prog_scan(then=lambda: self._offer_leftovers(sel))
        self.start(jobs)

    def _after_uninstall(self, p):
        def after(runner, job):
            # NSIS/Inno kaldiricilari kendini kopyalayip asil sureci bitirir: kayit silinene ya da yardimci surec bitene kadar bekle.
            deadline = time.time() + 15 * 60
            time.sleep(1.5)
            waited = False
            while time.time() < deadline and not runner.stop.is_set():
                if not core.registry_key_exists(p):
                    break
                helpers = core.running_uninstall_helpers()
                if not helpers:
                    break
                if not waited:
                    runner.say('Kaldırıcı arka planda sürüyor (%s); bekleniyor...' % ', '.join(sorted(set(helpers))))
                    waited = True
                time.sleep(2)
            gone = not core.registry_key_exists(p)
            p['_removed'] = gone
            runner.say(('Kaldırıldı: ' if gone else 'Kayıt hâlâ mevcut (iptal edilmiş veya yeniden başlatma bekliyor olabilir): ') + p['name'])
        return after

    def _offer_leftovers(self, removed):
        remaining = self.programs
        found = []
        still = {x['name'].lower() for x in remaining}
        for p in removed:
            # BCU'dan gelen (kayit anahtari bilinmeyen) girislerde kaldirma dogrulanamaz: artik onerme.
            if not p.get('_removed') or not p.get('key') or p['name'].lower() in still:
                continue
            for c in core.leftover_candidates(p, remaining):
                found.append((p['name'], c))
        if not found:
            self.write('Artık klasör bulunamadı.\n'); return
        self._leftover_dialog(found)

    def _leftover_dialog(self, found):
        win = tk.Toplevel(self); win.title('Artık klasörler'); win.configure(bg=PANEL); win.transient(self)
        w, h = int(820 * self.scale), int(420 * self.scale)
        win.geometry('%dx%d+%d+%d' % (w, h, self.winfo_rootx() + max(0, (self.winfo_width() - w) // 2), self.winfo_rooty() + max(0, (self.winfo_height() - h) // 3)))
        win.after(50, lambda: (win.grab_set(), win.focus_set()))
        self.label(win, 'Kaldırılan programlardan kalan klasörler. İşaretliler Geri Dönüşüm Kutusu\'na taşınır (geri alınabilir).',
                   wraplength=int(780 * self.scale)).pack(fill='x', padx=14, pady=10)
        ct = CheckTree(win, [('prog', 'Program', 220, 'w')], first=('Klasör', 520), height=10)
        ct.pack(fill='both', expand=True, padx=14)
        for i, (nm, path) in enumerate(found):
            ct.add('l%d' % i, path, (nm,), checked=True, payload=path)
        bar = tk.Frame(win, bg=PANEL); bar.pack(fill='x', padx=14, pady=10)

        def go():
            paths = ct.checked_payloads()
            win.destroy()
            if paths:
                self.start([Job('Artıkları Geri Dönüşüm Kutusu\'na taşı', cmd=ps_cmd('recycle-paths', Paths='|'.join(paths)), cancel_ok=False)])
        tk.Button(bar, text='Taşı', command=go, bg='#685229', fg='#fff', relief='flat', padx=14, pady=6).pack(side='right')
        tk.Button(bar, text='Vazgeç', command=win.destroy, bg=PANEL2, fg=FG, relief='flat', padx=14, pady=6).pack(side='right', padx=8)

    def prog_remove_orphans(self):
        sel = [p for p in self.prog_tree.checked_payloads() if p and p.get('orphan')]
        if not sel:
            sel = [p for p in self.programs if p.get('orphan')]
            if not sel:
                messagebox.showinfo('Yetim kayıtlar', 'Yetim kayıt bulunamadı.'); return
        if not messagebox.askyesno('Yetim kayıtlar', '%d kayıt "Programlar ve Özellikler" listesinden silinecek (önce .reg yedeği alınır):\n  %s\n\nDevam?'
                                   % (len(sel), '\n  '.join(p['name'] for p in sel[:15]))):
            return
        bdir = LOG_DIR / 'registry-backups'

        def work(runner, job):
            bad = 0
            for p in sel:
                ok, msg = core.remove_registry_entry(p, bdir)
                runner.say(('✓ ' if ok else '✗ ') + p['name'] + ' — ' + msg)
                bad += 0 if ok else 1
            return 2 if bad else 0
        self.start([Job('Yetim kayıt temizliği', func=work, cancel_ok=False, on_done=lambda j: self.prog_scan())])

    # ------------------------------------------------------------------ BLOATWARE (Store/AppX + masaustu)
    BLOAT_FILTERS = ['Önerilen ve dikkat', 'Yalnız önerilen', 'Tümü (korunanlar dahil)']

    def _tab_bloat(self, f):
        head = tk.Frame(f, bg=PANEL); head.pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(head, text='Bloatware temizliği', fg=FG, bg=PANEL, font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.bloat_chips = {}
        for key, text, color in [('rec', 'önerilen', OK_C), ('caution', 'dikkat', WARN), ('other', 'diğer', MUTED), ('protected', 'korunan', MUTED)]:
            v = tk.StringVar(value='— ' + text)
            tk.Label(head, textvariable=v, fg=color, bg=PANEL2, font=('Segoe UI', 9, 'bold'), padx=10, pady=3).pack(side='left', padx=(10, 0))
            self.bloat_chips[key] = (v, text)
        self.label(f, 'Windows ile gelen gereksiz Store uygulamaları ve ön yüklü masaüstü yazılımları. "Önerilen" grubu güvenle kaldırılabilir; '
                      '"Dikkat" grubunu kullanmıyorsanız seçin. Microsoft Store, WinGet, çalışma zamanları ve sürücü yardımcıları korunur. '
                      'Kaldırılan Store uygulamaları Microsoft Store\'dan yeniden kurulabilir.', wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(2, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Tara', self.bloat_scan, 'go')
        self.btn(bar, 'Önerilenleri seç', lambda: self.bloat_tree.set_all(True, lambda i: (self.bloat_tree.payload.get(i) or {}).get('cat') == 'rec'), 'ghost', action=False)
        self.btn(bar, 'Seçimi kaldır', lambda: self.bloat_tree.set_all(False), 'ghost', action=False)
        self.btn(bar, 'Seçilenleri kaldır', self.bloat_remove, 'danger')
        self.bloat_prov = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text='Yeni kullanıcı hesapları için de kaldır (yönetici)', variable=self.bloat_prov).pack(side='left', padx=(10, 0))
        self.bloat_rp = tk.BooleanVar(value=self.admin)
        ttk.Checkbutton(bar, text='Önce geri yükleme noktası', variable=self.bloat_rp).pack(side='left', padx=(10, 0))
        self.bloat_count = tk.StringVar(value='')
        tk.Label(bar, textvariable=self.bloat_count, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(side='right')
        flt = tk.Frame(f, bg=PANEL); flt.pack(fill='x', padx=16, pady=(6, 0))
        tk.Label(flt, text='Göster:', fg=FG, bg=PANEL).pack(side='left')
        self.bloat_filter = ttk.Combobox(flt, state='readonly', width=26, values=self.BLOAT_FILTERS); self.bloat_filter.current(0)
        self.bloat_filter.pack(side='left', padx=6)
        self.bloat_filter.bind('<<ComboboxSelected>>', lambda _e: self._bloat_render())
        tk.Label(flt, text='Ara:', fg=FG, bg=PANEL).pack(side='left', padx=(10, 0))
        self.bloat_q = tk.StringVar()
        ttk.Entry(flt, textvariable=self.bloat_q, width=30).pack(side='left', padx=6)
        self.bloat_q.trace_add('write', lambda *_: self._bloat_render())
        cols = [('pkg', 'Paket / program', 230, 'w'), ('pub', 'Yayıncı', 150, 'w'), ('ver', 'Sürüm', 80, 'w'), ('type', 'Tür', 210, 'w'), ('note', 'Not', 280, 'w')]
        self.bloat_tree = CheckTree(f, cols, first=('Uygulama', 270), on_change=self._bloat_count)
        self.bloat_tree.pack(fill='both', expand=True, padx=16, pady=8)
        self.bloat_groups, self.bloat_sel = {}, None

    def bloat_scan(self):
        store = {}

        def got_appx(job):
            store['appx'] = [d for d in job.data if d.get('type') == 'appx']

        def work(runner, job):
            job.data = core.annotate_programs(core.read_programs())
            return 0

        def done(job):
            self.programs = job.data or self.programs
            self.bloat_groups = core.build_bloat_view(store.get('appx', []), job.data or [])
            for k, (v, text) in self.bloat_chips.items():
                v.set('%d %s' % (len(self.bloat_groups.get(k, [])), text))
            self.bloat_sel = None
            self._bloat_render()
        self.start([Job('Store / ön yüklü uygulamalar', cmd=ps_cmd('appx-list'), on_done=got_appx, show_output=False),
                    Job('Masaüstü bloatware taraması', func=work, on_done=done, cancel_ok=False)])

    @staticmethod
    def _bloat_key(it):
        return (it['kind'], it.get('full') or it.get('name'))

    def _bloat_render(self):
        t = self.bloat_tree
        if self.bloat_sel is None:
            self.bloat_sel = {self._bloat_key(it) for it in self.bloat_groups.get('rec', [])}
        elif t.labels:
            visible = {self._bloat_key(pl) for pl in t.payload.values() if pl}
            checked = {self._bloat_key(pl) for pl in t.checked_payloads() if pl}
            self.bloat_sel = checked | (self.bloat_sel - visible)
        t.clear()
        mode = self.bloat_filter.get()
        cats = {'Önerilen ve dikkat': ('rec', 'caution'), 'Yalnız önerilen': ('rec',)}.get(mode, ('rec', 'caution', 'other', 'protected'))
        q = self.bloat_q.get().strip().lower()
        tags = {'rec': 'st_new', 'caution': 'st_warn', 'other': 'st_ok', 'protected': 'st_old'}
        for cat in cats:
            items = [it for it in self.bloat_groups.get(cat, []) if not q or q in (it['label'] + ' ' + it.get('name', '') + ' ' + it.get('pub', '')).lower()]
            if not items:
                continue
            gid = 'g:' + cat
            t.add(gid, '%s (%d)' % (core.BLOAT_CAT[cat], len(items)), ('', '', '', '', ''), tags=(tags[cat], 'group'), checkable=(cat != 'protected'), open_=(cat != 'protected'))
            for n, it in enumerate(items):
                if it['kind'] == 'appx':
                    typ = 'Store · ön yüklü (tüm kullanıcılar)' if it.get('provisioned') else 'Store uygulaması'
                else:
                    typ = 'Masaüstü programı'
                t.add('%s:%d' % (cat, n), it['label'], (it.get('name', ''), it.get('pub', ''), it.get('ver', ''), typ, it.get('note', '')), parent=gid,
                      checked=self._bloat_key(it) in self.bloat_sel, checkable=(cat != 'protected'), tags=(tags[cat],), payload=it)
        t.refresh_marks()
        self._bloat_count()

    def _bloat_count(self):
        n = len([p for p in self.bloat_tree.checked_payloads() if p])
        self.bloat_count.set('%d seçili' % n if n else '')

    def bloat_remove(self):
        sel = [p for p in self.bloat_tree.checked_payloads() if p and p.get('cat') != 'protected']
        if not sel:
            messagebox.showinfo('Bloatware', 'Önce tarayın ve kaldırılacak uygulamaları işaretleyin.'); return
        appx = [p for p in sel if p['kind'] == 'appx']
        win = [p for p in sel if p['kind'] == 'win32']
        caution = [p for p in sel if p['cat'] == 'caution']
        msg = '%d uygulama kaldırılacak:\n  %s%s' % (len(sel), '\n  '.join(p['label'] for p in sel[:15]), '\n  ...' if len(sel) > 15 else '')
        if caution:
            msg += '\n\nDİKKAT grubundan %d seçim var (ör. %s). Kullanıyorsanız vazgeçin.' % (len(caution), caution[0]['label'])
        if win:
            msg += '\n\nMasaüstü programları kendi kaldırıcılarıyla sırayla kaldırılır (mümkünse sessiz).'
        prov = self.bloat_prov.get()
        if prov and not self.admin:
            msg += '\n\nNot: "yeni kullanıcılar için de" seçeneği yönetici ister; şimdi yalnızca bu kullanıcıdan kaldırılacak.'
        if not messagebox.askyesno('Bloatware kaldırma', msg + '\n\nDevam edilsin mi?'):
            return
        jobs = []
        if self.bloat_rp.get():
            if self.admin:
                jobs.append(Job('Geri yükleme noktası', cmd=ps_cmd('restore-point'), cancel_ok=False))
            else:
                self.write('Geri yükleme noktası yönetici ister; atlandı.\n')
        if appx:
            jobs.append(Job('Store uygulamalarını kaldır (%d)' % len(appx), cmd=ps_cmd('appx-remove', Packages='|'.join(p['full'] for p in appx),
                                                                                    Provisioned='yes' if (prov and self.admin) else 'no'), cancel_ok=False))
        for p in win:
            exe, params = core.build_uninstall(p['prog'], True)
            jobs.append(Job('Kaldır: ' + p['name'], shell=(exe, params), after=self._after_uninstall(p['prog'])))
        jobs[-1].on_done = lambda j: self.bloat_scan()
        self.start(jobs)

    # ------------------------------------------------------------------ AYGIT TEMIZLIGI (bagli olmayan aygitlar)
    PH_FILTERS = ['Tümü', '30 günden eski', '1 yıldan eski', 'Tarihi bilinmeyen']

    def _tab_phantom(self, f):
        head = tk.Frame(f, bg=PANEL); head.pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(head, text='Aygıt temizliği', fg=FG, bg=PANEL, font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.ph_chips = {}
        for key, text, color in [('total', 'bağlı olmayan aygıt', ACCENT), ('old30', '30+ gün', OK_C), ('old365', '1+ yıl', OK_C), ('caution', 'dikkat', WARN)]:
            v = tk.StringVar(value='— ' + text)
            tk.Label(head, textvariable=v, fg=color, bg=PANEL2, font=('Segoe UI', 9, 'bold'), padx=10, pady=3).pack(side='left', padx=(10, 0))
            self.ph_chips[key] = (v, text)
        self.label(f, 'Bu bilgisayara bir zamanlar bağlanmış ama şu an bağlı olmayan aygıtlar (eski USB bellekler, telefonlar, yazıcılar, '
                      'COM portları, kaldırılmış donanım). Aygıt Yöneticisi bunları gizler; birikmeleri COM port numaralarını ve sürücü listesini şişirir. '
                      'Kaldırılan aygıt yeniden takılırsa Windows onu yeni aygıt olarak tanır ve sürücüsünü yeniden kurar. '
                      '"Dikkat" (turuncu) satırlar sistem/yazılım aygıtlarıdır; varsayılan olarak seçilmez.', wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(2, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Tara', self.ph_scan, 'go')
        self.btn(bar, '30 günden eskileri seç', lambda: self.ph_tree.set_all(True, lambda i: bool((self.ph_tree.payload.get(i) or {}).get('default'))), 'ghost', action=False)
        self.btn(bar, 'Tümünü seç', lambda: self.ph_tree.set_all(True), 'ghost', action=False)
        self.btn(bar, 'Seçimi kaldır', lambda: self.ph_tree.set_all(False), 'ghost', action=False)
        self.btn(bar, 'Seçilenleri kaldır', self.ph_remove, 'danger')
        self.ph_rp = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text='Önce geri yükleme noktası (24 saat sınırı aşılarak)', variable=self.ph_rp).pack(side='left', padx=(10, 0))
        self.ph_count = tk.StringVar(value='')
        tk.Label(bar, textvariable=self.ph_count, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(side='right')
        flt = tk.Frame(f, bg=PANEL); flt.pack(fill='x', padx=16, pady=(6, 0))
        tk.Label(flt, text='Göster:', fg=FG, bg=PANEL).pack(side='left')
        self.ph_filter = ttk.Combobox(flt, state='readonly', width=22, values=self.PH_FILTERS); self.ph_filter.current(0)
        self.ph_filter.pack(side='left', padx=6)
        self.ph_filter.bind('<<ComboboxSelected>>', lambda _e: self._ph_render())
        tk.Label(flt, text='Ara:', fg=FG, bg=PANEL).pack(side='left', padx=(10, 0))
        self.ph_q = tk.StringVar()
        ttk.Entry(flt, textvariable=self.ph_q, width=30).pack(side='left', padx=6)
        self.ph_q.trace_add('write', lambda *_: self._ph_render())
        cols = [('seen', 'Son görülme', 145, 'w'), ('age', 'Gün', 60, 'e'), ('status', 'Durum', 170, 'w'), ('id', 'Aygıt örnek kimliği', 480, 'w')]
        self.ph_tree = CheckTree(f, cols, first=('Aygıt', 330), on_change=self._ph_count)
        self.ph_tree.pack(fill='both', expand=True, padx=16, pady=8)
        self.ph_groups, self.ph_sel = {}, None

    def ph_scan(self):
        def done(job):
            devs = [d for d in job.data if d.get('type') == 'phantom']
            self.ph_groups, st = core.build_phantom_view(devs)
            for k, (v, text) in self.ph_chips.items():
                v.set('%d %s' % (st.get(k, 0), text))
            self.ph_sel = None
            self._ph_render()
        self.start([Job('Bağlı olmayan aygıtlar', cmd=ps_cmd('phantom-list'), on_done=done, show_output=False)])

    def _ph_render(self):
        t = self.ph_tree
        if self.ph_sel is None:
            self.ph_sel = {d['id'] for g in self.ph_groups.values() for d in g if d['default']}
        elif t.labels:
            visible = {pl['id'] for pl in t.payload.values() if pl}
            self.ph_sel = {pl['id'] for pl in t.checked_payloads() if pl} | (self.ph_sel - visible)
        t.clear()
        mode, q = self.ph_filter.get(), self.ph_q.get().strip().lower()
        for n, (cls, items) in enumerate(self.ph_groups.items()):
            show = []
            for d in items:
                if mode == '30 günden eski' and not (d['age'] is not None and d['age'] >= 30):
                    continue
                if mode == '1 yıldan eski' and not (d['age'] is not None and d['age'] >= 365):
                    continue
                if mode == 'Tarihi bilinmeyen' and d['age'] is not None:
                    continue
                if q and q not in ((d.get('name') or '') + ' ' + d['id'] + ' ' + cls).lower():
                    continue
                show.append(d)
            if not show:
                continue
            gid = 'g%d' % n
            t.add(gid, '%s (%d)' % (cls, len(show)), ('', '', '', ''), tags=('group',), open_=True)
            for m, d in enumerate(show):
                t.add('%s_%d' % (gid, m), d.get('name') or '(adsız aygıt)', (d['seen'] or 'bilinmiyor', '' if d['age'] is None else d['age'],
                      'Dikkat: sistem aygıtı' if d['caution'] else 'Bağlı değil', d['id']), parent=gid, checked=d['id'] in self.ph_sel,
                      tags=('risky',) if d['caution'] else (), payload=d)
        t.refresh_marks()
        self._ph_count()

    def _ph_count(self):
        n = len([p for p in self.ph_tree.checked_payloads() if p])
        self.ph_count.set('%d aygıt seçili' % n if n else '')

    def ph_remove(self):
        sel = [p for p in self.ph_tree.checked_payloads() if p]
        if not sel:
            messagebox.showinfo('Aygıt temizliği', 'Önce tarayın ve kaldırılacak aygıtları işaretleyin.'); return
        if not self.need_admin('phantom-remove'):
            return
        caution = [p for p in sel if p['caution']]
        msg = '%d bağlı olmayan aygıt kaldırılacak.\nAygıtlar yeniden takılırsa Windows onları yeni aygıt olarak tanır.' % len(sel)
        if caution:
            msg += '\n\nDİKKAT: %d sistem/yazılım aygıtı seçili (ör. %s).' % (len(caution), caution[0].get('name') or caution[0]['id'])
        if not messagebox.askyesno('Aygıt temizliği', msg + '\n\nDevam edilsin mi?'):
            return
        jobs = []
        if self.ph_rp.get():
            jobs.append(Job('Geri yükleme noktası', cmd=ps_cmd('restore-point', ForceRestorePoint='yes'), cancel_ok=False))
        jobs.append(Job('Bağlı olmayan aygıtları kaldır (%d)' % len(sel), cmd=ps_cmd('phantom-remove', InstanceIds='|'.join(p['id'] for p in sel)),
                        cancel_ok=False, on_done=lambda j: self.ph_scan()))
        self.start(jobs)

    # ------------------------------------------------------------------ SURUCU MERKEZI (SDIO tarzi gorunum)
    DRV_FILTERS = ['Güncellemeler ve sorunlar', 'Tüm aygıtlar', 'Yalnız güncellemeler', 'Eksik / sorunlu', 'Güncel olanlar']

    def _tab_drivers(self, f):
        # Alt: SDIO motoru (once paketlenir ki agac genisleyince kesilmesin)
        sd = tk.Frame(f, bg=PANEL2, padx=12, pady=8); sd.pack(side='bottom', fill='x', padx=16, pady=(4, 12))
        head = tk.Frame(f, bg=PANEL); head.pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(head, text='Sürücü Merkezi', fg=FG, bg=PANEL, font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.drv_chips = {}
        for key, text, color in [('updates', 'güncelleme', OK_C), ('missing', 'eksik sürücü', BAD_C), ('problem', 'sorunlu', WARN), ('devices', 'aygıt', MUTED)]:
            v = tk.StringVar(value='— ' + text)
            tk.Label(head, textvariable=v, fg=color, bg=PANEL2, font=('Segoe UI', 9, 'bold'), padx=10, pady=3).pack(side='left', padx=(10, 0))
            self.drv_chips[key] = (v, text)
        self.drv_mode = tk.StringVar(value='Taramak için "Aygıtları ve güncellemeleri tara"ya basın.')
        tk.Label(head, textvariable=self.drv_mode, fg=MUTED, bg=PANEL, font=('Segoe UI', 9)).pack(side='right')

        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16, pady=(6, 0))
        self.btn(bar, 'Aygıtları ve güncellemeleri tara', self.drv_scan, 'go')
        self.btn(bar, 'Önerilenleri seç', self.drv_select_recommended, 'ghost', action=False)
        self.btn(bar, 'Seçimi kaldır', lambda: self.drv_tree.set_all(False), 'ghost', action=False)
        self.btn(bar, 'Seçilenleri kur', self.drv_install, 'danger')
        self.btn(bar, 'Sürücüleri yedekle', self.drv_backup, 'ghost')
        self.drv_rp = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text='Önce geri yükleme noktası', variable=self.drv_rp).pack(side='left', padx=(10, 0))
        self.drv_count = tk.StringVar(value='')
        tk.Label(bar, textvariable=self.drv_count, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(side='right')

        flt = tk.Frame(f, bg=PANEL); flt.pack(fill='x', padx=16, pady=(6, 0))
        tk.Label(flt, text='Göster:', fg=FG, bg=PANEL).pack(side='left')
        self.drv_filter = ttk.Combobox(flt, state='readonly', width=26, values=self.DRV_FILTERS); self.drv_filter.current(0)
        self.drv_filter.pack(side='left', padx=6)
        self.drv_filter.bind('<<ComboboxSelected>>', lambda _e: self._drv_render())
        tk.Label(flt, text='Ara:', fg=FG, bg=PANEL).pack(side='left', padx=(10, 0))
        self.drv_q = tk.StringVar()
        ttk.Entry(flt, textvariable=self.drv_q, width=30).pack(side='left', padx=6)
        self.drv_q.trace_add('write', lambda *_: self._drv_render())
        self.drv_wu = tk.BooleanVar(value=True)
        ttk.Checkbutton(flt, text='Windows Update kataloğunu dahil et', variable=self.drv_wu).pack(side='left', padx=(10, 0))

        body = tk.PanedWindow(f, orient='horizontal', bg=PANEL, sashwidth=6, bd=0)
        body.pack(fill='both', expand=True, padx=16, pady=6)
        cols = [('status', 'Durum', 175, 'w'), ('cur', 'Kurulu sürüm', 98, 'w'), ('curd', 'Tarih', 90, 'w'),
                ('new', 'Yeni sürüm', 98, 'w'), ('newd', 'Tarih', 90, 'w'), ('prov', 'Sağlayıcı', 90, 'w'), ('size', 'Boyut', 60, 'e')]
        self.drv_tree = CheckTree(body, cols, first=('Aygıt / aday sürücü', 300), height=12, on_change=self._drv_count)
        body.add(self.drv_tree, stretch='always', minsize=int(560 * self.scale))
        det = tk.Frame(body, bg=PANEL2)
        body.add(det, stretch='never', minsize=int(220 * self.scale), width=int(250 * self.scale))
        tk.Label(det, text='AYRINTI', fg=ACCENT, bg=PANEL2, font=('Segoe UI', 9, 'bold')).pack(anchor='w', padx=10, pady=(8, 2))
        self.drv_detail = tk.Text(det, bg=PANEL2, fg=FG, relief='flat', font=('Segoe UI', 9), wrap='word', padx=10, pady=4, height=8)
        self.drv_detail.pack(fill='both', expand=True)
        self.drv_detail.tag_configure('k', foreground=MUTED)
        self.drv_detail.tag_configure('h', font=('Segoe UI', 10, 'bold'))
        self.drv_detail.insert('end', 'Bir aygıt veya aday sürücü seçin.'); self.drv_detail.configure(state='disabled')
        self.drv_tree.tree.bind('<<TreeviewSelect>>', lambda _e: self._drv_details())
        self.drv_rows, self.drv_unmatched, self.drv_sel = [], [], set()

        self.sdio_state = tk.StringVar(value='SDIO motoru: denetleniyor...')
        top = tk.Frame(sd, bg=PANEL2); top.pack(fill='x')
        tk.Label(top, text='Snappy Driver Installer Origin', fg=FG, bg=PANEL2, font=('Segoe UI', 10, 'bold')).pack(side='left')
        self.btn(top, 'SDIO ile analiz et', lambda: self.sdio_run('scan'), side='left').pack_configure(padx=(12, 6))
        self.btn(top, 'SDIO ile kur', lambda: self.sdio_run('install'), 'danger', side='left')
        self.btn(top, 'Aygıt listesi', self.sdio_show_devices, 'ghost', action=False, side='left')
        self.sdio_toggle = tk.Button(top, text='Seçenekler ▸', command=self._sdio_toggle, bg=PANEL2, fg=ACCENT, relief='flat', cursor='hand2',
                                     activebackground=PANEL2, activeforeground=FG, font=('Segoe UI', 9, 'bold'))
        self.sdio_toggle.pack(side='left', padx=6)
        tk.Label(top, textvariable=self.sdio_state, fg=MUTED, bg=PANEL2, font=('Segoe UI', 9), anchor='e').pack(side='right', fill='x', expand=True)
        self.sdio_opts = sd = tk.Frame(sd, bg=PANEL2)
        self.sdio_cat = {}
        for n, (key, lab) in enumerate(core.SDIO_CATEGORIES):
            v = tk.BooleanVar(value=key in core.SDIO_DEFAULT)
            self.sdio_cat[key] = v
            ttk.Checkbutton(sd, text=lab, variable=v, style='Alt.TCheckbutton').grid(row=1 + n // 3, column=n % 3, sticky='w', padx=(0, 14), pady=1)
        tk.Label(sd, text='Paket:', fg=FG, bg=PANEL2).grid(row=1, column=3, sticky='e', padx=(16, 4))
        self.sdio_pack = ttk.Combobox(sd, state='readonly', width=18, values=[l for _, l in core.SDIO_PACK_FILTERS]); self.sdio_pack.current(0)
        self.sdio_pack.grid(row=1, column=4, sticky='w')
        self.sdio_update = tk.BooleanVar(value=True)
        ttk.Checkbutton(sd, text='SDIO veritabanını güncelle', variable=self.sdio_update, style='Alt.TCheckbutton').grid(row=2, column=3, columnspan=2, sticky='w', padx=(16, 0))
        tk.Label(sd, text='Analiz kurulum yapmaz. Kurulum yalnızca işaretli kategorileri kurar; öncesinde geri yükleme noktası oluşturulur.',
                 fg=MUTED, bg=PANEL2, font=('Segoe UI', 9)).grid(row=3, column=0, columnspan=6, sticky='w', pady=(4, 0))

    def _sdio_toggle(self):
        if self.sdio_opts.winfo_ismapped():
            self.sdio_opts.pack_forget(); self.sdio_toggle.configure(text='Seçenekler ▸')
        else:
            self.sdio_opts.pack(fill='x', pady=(6, 0)); self.sdio_toggle.configure(text='Seçenekler ▾')

    def drv_scan(self):
        inc = 'yes' if self.drv_wu.get() else 'no'
        self.drv_mode.set('Taranıyor…' + (' (Windows Update kataloğu 1–2 dk sürebilir)' if inc == 'yes' else ''))
        self.start([Job('Sürücü analizi', cmd=ps_cmd('driver-analyze', IncludeWU=inc), on_done=self._drv_loaded)])

    def _drv_loaded(self, job):
        devs = [d for d in job.data if d.get('type') == 'dev']
        wus = [d for d in job.data if d.get('type') == 'wu-driver']
        self.drv_rows, self.drv_unmatched, stats = core.build_driver_view(devs, wus)
        self.drv_sel = {(c['wu']['id'], r['dev']['id']) for r in self.drv_rows for c in r['cands'] if core.DRV_STATUS[c['status']][2]}
        for k, (v, text) in self.drv_chips.items():
            v.set('%d %s' % (stats.get(k, 0), text))
        self.drv_mode.set('Son tarama: %s · %d aday sürücü' % (datetime.datetime.now().strftime('%H:%M'), stats['candidates']))
        if not devs:
            self.write('Aygıt listesi alınamadı (günlüğe bakın).\n')
        self._drv_render()

    def _drv_visible(self, r):
        mode = self.drv_filter.get()
        upd = r['best'] in ('missing', 'newer')
        bad = r['state'] in ('missing', 'problem')
        if mode == self.DRV_FILTERS[0] and not (upd or bad):
            return False
        if mode == self.DRV_FILTERS[2] and not upd:
            return False
        if mode == self.DRV_FILTERS[3] and not bad:
            return False
        if mode == self.DRV_FILTERS[4] and (upd or bad):
            return False
        q = self.drv_q.get().strip().lower()
        if q:
            d = r['dev']
            hay = ' '.join([d.get('name', ''), d.get('cls', ''), d.get('provider', ''), ' '.join(d.get('hwids') or [])] + [c['wu'].get('title', '') for c in r['cands']]).lower()
            if q not in hay:
                return False
        return True

    def _drv_render(self):
        t = self.drv_tree
        if t.labels:
            # Gorunen aday satirlarinin isaret durumunu al; suzgecle gizlenmis olanlarin secimini koru.
            visible = {(pl['wu']['id'], pl['dev_id']) for pl in t.payload.values() if pl and pl.get('kind') == 'cand'}
            checked = {(pl['wu']['id'], pl['dev_id']) for pl in t.checked_payloads() if pl and pl.get('kind') == 'cand'}
            self.drv_sel = checked | (self.drv_sel - visible)
        t.clear()
        shown = 0
        for n, r in enumerate(self.drv_rows):
            if not self._drv_visible(r):
                continue
            shown += 1
            d = r['dev']
            label, tag = core.device_label(r)
            best = r['cands'][0] if r['cands'] else None
            pid = 'd%d' % n
            t.add(pid, d.get('name') or '(adsız aygıt)', (label, d.get('ver', '') or '—', d.get('date', ''), best['ver'] if best else '', best['wu'].get('date', '') if best else '',
                  d.get('provider', '') or d.get('maker', ''), ''), tags=(tag, 'group') if r['cands'] else (tag,), checkable=bool(r['cands']),
                  payload=None, open_=bool(r['cands']) and r['best'] in ('missing', 'newer'))
            t.payload[pid] = {'kind': 'dev', 'row': r}
            for m, c in enumerate(r['cands']):
                w = c['wu']
                stl, stag, _ = core.DRV_STATUS[c['status']]
                cid = 'c%d_%d' % (n, m)
                pl = {'kind': 'cand', 'wu': w, 'dev_id': d['id'], 'cand': c, 'row': r}
                t.add(cid, 'Windows Update · ' + w.get('title', ''), (stl, '', '', c['ver'], w.get('date', ''), w.get('provider') or w.get('maker', ''),
                      ('%s MB' % w.get('sizeMB')) if w.get('sizeMB') else ''), parent=pid, checked=(w['id'], d['id']) in self.drv_sel, tags=(stag,), payload=pl)
        q = self.drv_q.get().strip().lower()
        um = [c for c in self.drv_unmatched if not q or q in (c['wu'].get('title', '') + ' ' + c['wu'].get('hwid', '')).lower()]
        if um and self.drv_filter.get() not in (self.DRV_FILTERS[3], self.DRV_FILTERS[4]):
            gid = 'u'
            t.add(gid, 'Aygıtla eşleşmeyen Windows Update sürücüleri (%d)' % len(um), ('Donanım kimliği eşleşmedi', '', '', '', '', '', ''),
                  tags=('st_warn', 'group'), open_=False)
            for m, c in enumerate(um):
                w = c['wu']
                pl = {'kind': 'cand', 'wu': w, 'dev_id': '', 'cand': c, 'row': None}
                t.add('u%d' % m, 'Windows Update · ' + w.get('title', ''), ('Karşılaştırılamadı', '', '', c['ver'], w.get('date', ''), w.get('provider') or w.get('maker', ''),
                      ('%s MB' % w.get('sizeMB')) if w.get('sizeMB') else ''), parent=gid, checked=(w['id'], '') in self.drv_sel, tags=('st_warn',), payload=pl)
        t.refresh_marks()
        self._drv_count()
        if self.drv_rows and not shown and self.drv_filter.get() == self.DRV_FILTERS[0]:
            t.add('none', 'Tüm sürücüler güncel görünüyor — "Tüm aygıtlar" ile listenin tamamını görebilirsiniz.', ('', '', '', '', '', '', ''), checkable=False, tags=('st_ok',))

    def _drv_count(self):
        sel = [p for p in self.drv_tree.checked_payloads() if p and p.get('kind') == 'cand']
        ids = {p['wu']['id'] for p in sel}
        mb = sum(float(p['wu'].get('sizeMB') or 0) for p in {p['wu']['id']: p for p in sel}.values())
        self.drv_count.set(('%d sürücü seçili · %.0f MB' % (len(ids), mb)) if ids else '')

    def drv_select_recommended(self):
        t = self.drv_tree
        t.set_all(True, lambda iid: bool(t.payload.get(iid)) and t.payload[iid].get('kind') == 'cand' and core.DRV_STATUS[t.payload[iid]['cand']['status']][2])

    def _drv_details(self):
        sel = self.drv_tree.tree.selection()
        if not sel:
            return
        p = self.drv_tree.payload.get(sel[0])
        tx = self.drv_detail
        tx.configure(state='normal'); tx.delete('1.0', 'end')

        def kv(k, v):
            if v not in (None, '', []):
                tx.insert('end', k + ': ', 'k'); tx.insert('end', '%s\n' % v)
        if not p:
            tx.insert('end', 'Bir aygıt veya aday sürücü seçin.')
        elif p['kind'] == 'dev':
            r = p['row']; d = r['dev']
            tx.insert('end', (d.get('name') or '(adsız aygıt)') + '\n', 'h')
            kv('Durum', core.device_label(r)[0]); kv('Sınıf', d.get('cls')); kv('Üretici', d.get('maker'))
            code = int(d.get('code') or 0)
            if code:
                kv('Aygıt Yöneticisi kodu', '%d — %s' % (code, core.PROBLEM_CODES.get(code, '')))
            tx.insert('end', '\nKurulu sürücü\n', 'h')
            kv('Sürüm', d.get('ver') or 'yok'); kv('Tarih', d.get('date')); kv('Sağlayıcı', d.get('provider')); kv('INF', d.get('inf'))
            kv('İmzalı', 'evet' if d.get('signed') else ('hayır' if d.get('ver') else ''))
            tx.insert('end', '\nDonanım kimlikleri\n', 'h')
            for h in (d.get('hwids') or [])[:6]:
                tx.insert('end', h + '\n')
            if r['cands']:
                tx.insert('end', '\n%d aday sürücü (altındaki satırlar)\n' % len(r['cands']), 'k')
            else:
                tx.insert('end', '\nWindows Update bu aygıt için sürücü sunmuyor. SDIO analizi daha geniş bir veritabanında arar.\n', 'k')
        else:
            w = p['wu']; c = p['cand']
            tx.insert('end', w.get('title', '') + '\n', 'h')
            kv('Durum', core.DRV_STATUS[c['status']][0]); kv('Yeni sürüm', c.get('ver')); kv('Sürüm tarihi', w.get('date'))
            kv('Sağlayıcı', w.get('provider')); kv('Üretici', w.get('maker')); kv('Model', w.get('model')); kv('Sınıf', w.get('cls'))
            kv('İndirme', ('%s MB' % w.get('sizeMB')) if w.get('sizeMB') else ''); kv('Yeniden başlatma', 'gerekebilir' if w.get('reboot') else 'gerekmez')
            kv('Eşleşme', c.get('match')); kv('Donanım kimliği', w.get('hwid'))
            if p.get('row'):
                d = p['row']['dev']
                tx.insert('end', '\nŞu an kurulu\n', 'h'); kv('Sürüm', d.get('ver') or 'yok'); kv('Tarih', d.get('date')); kv('Sağlayıcı', d.get('provider'))
            kv('Kaynak', 'Microsoft Windows Update (imzalı)')
        tx.configure(state='disabled')

    def drv_install(self):
        sel = [p for p in self.drv_tree.checked_payloads() if p and p.get('kind') == 'cand']
        if not sel:
            messagebox.showinfo('Sürücüler', 'Önce tarayın ve kurulacak sürücüleri işaretleyin (aday satırlarındaki kutular).'); return
        if not self.need_admin('driver-install'):
            return
        uniq = {p['wu']['id']: p for p in sel}
        olds = [p for p in uniq.values() if p['cand']['status'] in ('older', 'current')]
        msg = '%d sürücü Windows Update üzerinden kurulacak:\n  %s' % (len(uniq), '\n  '.join(p['wu']['title'] for p in list(uniq.values())[:12]))
        if olds:
            msg += '\n\nDİKKAT: %d seçim kurulu sürücüyle aynı veya daha eski.' % len(olds)
        if not messagebox.askyesno('Sürücü kurulumu', msg + ('\n\nÖnce geri yükleme noktası oluşturulacak.' if self.drv_rp.get() else '') + '\n\nDevam?'):
            return
        jobs = []
        if self.drv_rp.get():
            jobs.append(Job('Geri yükleme noktası', cmd=ps_cmd('restore-point'), cancel_ok=False))
        jobs.append(Job('Seçili sürücüleri kur', cmd=ps_cmd('driver-install', UpdateIds=','.join(uniq)), cancel_ok=False, on_done=lambda j: self.drv_scan()))
        self.start(jobs)

    def drv_backup(self):
        if not self.need_admin('driver-backup'):
            return
        d = filedialog.askdirectory(title='Sürücü yedeği için klasör seçin')
        if d:
            self.start([Job('Sürücü yedeği', cmd=ps_cmd('driver-backup', BackupPath=d))])

    def sdio_run(self, mode):
        exe = self.engines.get('sdio', {}).get('path')
        if not exe:
            if messagebox.askyesno('SDIO yok', 'SDIO motoru kurulu değil. Şimdi kurulsun mu?'):
                self._engine_install_one('sdio')
            return
        if not self.need_admin('sdio-' + mode):
            return
        cats = {k for k, v in self.sdio_cat.items() if v.get()}
        pack = core.SDIO_PACK_FILTERS[self.sdio_pack.current()][0]
        if mode == 'install':
            if not cats:
                messagebox.showinfo('SDIO', 'En az bir kategori seçin.'); return
            if not messagebox.askyesno('SDIO kurulumu', 'SDIO seçili kategorilerdeki (%s%s) sürücüleri kuracak.\n\n'
                                       '• Önce sistem geri yükleme noktası oluşturulur.\n• Gerekli sürücü paketleri indirilir (yüzlerce MB olabilir).\n'
                                       '• Windows Update sürücüleri genellikle daha güvenlidir; ekran kartı/yonga seti için üretici sürücüsünü tercih edin.\n\nDevam?'
                                       % (', '.join(sorted(cats)), (' · paket: ' + pack) if pack else '')):
                return
        try:
            script = core.write_sdio_script(mode, cats, [pack] if pack else [], update_db=self.sdio_update.get())
        except (OSError, ValueError) as e:
            messagebox.showerror('SDIO', str(e)); return
        d = core.sdio_dirs()
        self.start([Job('SDIO ' + ('analiz' if mode == 'scan' else 'kurulum'), cmd=[exe, '-script:%s' % script], cwd=os.path.dirname(exe),
                        tail_dir=str(d['logs']), cancel_ok=(mode == 'scan'), on_done=lambda j: self._sdio_done(j, mode))])

    def _sdio_done(self, job, mode):
        devs = core.sdio_dirs()['logs'] / 'agfo-devices.txt'
        if devs.is_file():
            self.write('SDIO aygıt/sürücü listesi: %s\n' % devs)
        self.drv_mode.set('SDIO %s bitti — ayrıntı günlükte' % ('analizi' if mode == 'scan' else 'kurulumu'))

    def sdio_show_devices(self):
        devs = core.sdio_dirs()['logs'] / 'agfo-devices.txt'
        if not devs.is_file():
            messagebox.showinfo('SDIO', 'Önce "SDIO ile analiz et" çalıştırın.'); return
        try:
            text = devs.read_text(encoding='utf-8', errors='replace')
        except OSError as e:
            messagebox.showerror('SDIO', str(e)); return
        win = tk.Toplevel(self); win.title('SDIO aygıt listesi'); win.configure(bg=PANEL)
        win.geometry('%dx%d' % (int(900 * self.scale), int(560 * self.scale)))
        tx = tk.Text(win, bg='#09111e', fg='#dce8fa', font=('Consolas', 9), wrap='none')
        tx.pack(fill='both', expand=True)
        tx.insert('1.0', text[:2000000]); tx.configure(state='disabled')

    # ------------------------------------------------------------------ UYGULAMA GUNCELLEMELERI (WinGet)
    def _tab_apps(self, f):
        self.label(f, 'WinGet resmî deposundaki güncellemeler bu listede gösterilir; yalnızca işaretledikleriniz sırayla, sessiz kipte güncellenir.',
                   wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(12, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Güncellemeleri tara', self.apps_scan, 'ghost')
        self.btn(bar, 'Tümünü seç', lambda: self.app_tree.set_all(True), 'ghost', action=False)
        self.btn(bar, 'Seçimi kaldır', lambda: self.app_tree.set_all(False), 'ghost', action=False)
        self.btn(bar, 'Seçilenleri güncelle', self.apps_update, 'danger')
        self.app_count = tk.StringVar(value='')
        tk.Label(bar, textvariable=self.app_count, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(side='right')
        cols = [('id', 'Paket kimliği', 300, 'w'), ('ver', 'Kurulu', 130, 'w'), ('avail', 'Yeni', 130, 'w'), ('state', 'Durum', 160, 'w')]
        self.app_tree = CheckTree(f, cols, first=('Uygulama', 330), on_change=lambda: self.app_count.set('%d seçili' % len(self.app_tree.checked)))
        self.app_tree.pack(fill='both', expand=True, padx=16, pady=8)

    def apps_scan(self):
        wg = self.engines.get('winget', {}).get('path') or core.find_winget()
        if not wg:
            messagebox.showerror('WinGet yok', 'WinGet bulunamadı.'); return
        cmd = [wg, 'upgrade', '--source', 'winget', '--accept-source-agreements', '--disable-interactivity']
        self.start([Job('WinGet güncelleme taraması', cmd=cmd, on_done=self._apps_loaded, show_output=False)])

    def _apps_loaded(self, job):
        rows = core.parse_winget_table(job.lines)
        t = self.app_tree; t.clear()
        for i, r in enumerate(rows):
            t.add('a%d' % i, r['name'], (r['id'], r.get('version', ''), r.get('available', ''), ''), checked=True, payload=r)
        self.write('WinGet: %d güncellenebilir uygulama.\n' % len(rows))
        if not rows:
            tail = [l for l in job.lines if l.strip()][-3:]
            if tail:
                self.write('\n'.join(tail) + '\n')

    def apps_update(self):
        wg = self.engines.get('winget', {}).get('path') or core.find_winget()
        sel = self.app_tree.checked_payloads()
        if not wg or not sel:
            messagebox.showinfo('Güncelleme', 'Önce tarayın ve güncellenecek uygulamaları işaretleyin.'); return
        if not messagebox.askyesno('Güncellemeyi onaylayın', '%d uygulama sırayla güncellenecek. Güncellenen uygulamalar kapanabilir. Devam?' % len(sel)):
            return
        iid_by_id = {self.app_tree.payload[i]['id']: i for i in self.app_tree.labels}
        jobs = []
        for r in sel:
            def done(job, pid=r['id']):
                iid = iid_by_id.get(pid)
                if iid and self.app_tree.tree.exists(iid):
                    self.app_tree.tree.set(iid, 'state', hint(job.code))
            jobs.append(Job('Güncelle: ' + r['name'], cmd=core.winget_install_cmd(wg, r['id'], upgrade=True), on_done=done, cancel_ok=False))
        self.start(jobs)

    # ------------------------------------------------------------------ BAKIM ve SAGLIK
    def _tab_maint(self, f):
        canvas = tk.Frame(f, bg=PANEL); canvas.pack(fill='both', expand=True)
        wrap = int(560 * self.scale)
        for col, (group, actions) in enumerate(ACTIONS.items()):
            colf = tk.Frame(canvas, bg=PANEL); colf.grid(row=0, column=col, sticky='nsew', padx=(16, 8), pady=10)
            canvas.grid_columnconfigure(col, weight=1)
            tk.Label(colf, text=group, fg=ACCENT, bg=PANEL, font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(0, 4))
            for title, action, detail, danger in actions:
                line = tk.Frame(colf, bg=PANEL2, padx=12, pady=9); line.pack(fill='x', pady=4)
                c = tk.Frame(line, bg=PANEL2); c.pack(side='left', fill='x', expand=True)
                tk.Label(c, text=title, fg=FG, bg=PANEL2, font=('Segoe UI', 10, 'bold')).pack(anchor='w')
                tk.Label(c, text=detail + (' Yönetici gerekir.' if action in ADMIN_ACTIONS else ''), fg=MUTED, bg=PANEL2, font=('Segoe UI', 9),
                         wraplength=wrap, justify='left').pack(anchor='w', pady=(3, 0))
                self.btn(line, 'Çalıştır', lambda a=action, d=danger: self.run_ps(a, d), 'danger' if danger else 'normal', side='right')

    def run_ps(self, action, danger):
        if not self.need_admin(action):
            return
        if danger and not messagebox.askyesno('İşlemi onaylayın', DANGER_TEXT.get(action, action) + '\n\nDevam edilsin mi?'):
            return
        no_cancel = action in ('component-clean', 'health-repair', 'restore-point')
        title = next((t for acts in ACTIONS.values() for t, a, _, _ in acts if a == action), action)
        self.start([Job(title, cmd=ps_cmd(action), cancel_ok=not no_cancel)])

    # ------------------------------------------------------------------ KOL / GAMEPAD (3.6.0)
    def _tab_pad(self, f):
        head = tk.Frame(f, bg=PANEL); head.pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(head, text='Kol / Gamepad', fg=FG, bg=PANEL, font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.pad_chips = {}
        for key, text, color in [('total', 'kol bileşeni', ACCENT), ('usb', 'USB', OK_C), ('bluetooth', 'Bluetooth', WARN), ('adapter', 'adaptör', OK_C), ('problem', 'sorunlu', BAD_C)]:
            v = tk.StringVar(value='— ' + text)
            tk.Label(head, textvariable=v, fg=color, bg=PANEL2, font=('Segoe UI', 9, 'bold'), padx=10, pady=3).pack(side='left', padx=(10, 0))
            self.pad_chips[key] = (v, text)
        self.label(f, 'Xbox kolunun bağlantı yolu, sürücü durumu, pili ve canlı tuş/analog testi. Yalnızca Xbox kol/adaptör aygıtlarına dokunulur; fare ve klavye listeye girmez.',
                   wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(2, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Tara', self.pad_scan, 'go')
        self.btn(bar, 'Kol sürücüsünü sıfırla', self.pad_reset, 'danger')
        self.btn(bar, 'Bluetooth hizmetini yeniden başlat', self.pad_bt_restart)
        self.btn(bar, 'FC ayarlarını yedekle ve sıfırla', self.pad_fc_reset, 'danger')
        bar2 = tk.Frame(f, bg=PANEL); bar2.pack(fill='x', padx=16, pady=(2, 0))
        self.btn(bar2, 'Xbox Accessories (firmware)', self.pad_xbox_accessories, 'ghost')
        self.btn(bar2, 'Steam kumanda ayarları', lambda: self.pad_open('steam://settings/controller', 'Steam kumanda ayarları'), 'ghost', action=False)
        self.btn(bar2, 'Oyun kumandaları (joy.cpl)', lambda: self.pad_open('joy.cpl', 'Oyun kumandaları'), 'ghost', action=False)
        self.btn(bar2, 'Bluetooth ayarları', lambda: self.pad_open('ms-settings:bluetooth', 'Bluetooth ayarları'), 'ghost', action=False)
        self.btn(bar2, 'FC ayar klasörü', self.pad_open_fc_dir, 'ghost', action=False)
        body = tk.PanedWindow(f, orient='horizontal', bg=PANEL, sashwidth=6, bd=0)
        body.pack(fill='both', expand=True, padx=16, pady=(6, 8))
        left = tk.Frame(body, bg=PANEL)
        body.add(left, stretch='always', minsize=int(420 * self.scale))
        cols = [('bus', 'Bağlantı', 150, 'w'), ('status', 'Durum', 110, 'w'), ('id', 'Aygıt örnek kimliği', 380, 'w')]
        self.pad_tree = CheckTree(left, cols, first=('Aygıt', 280), height=4)
        self.pad_tree.pack(fill='both', expand=True)
        tk.Label(left, text='TANI', fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(anchor='w', pady=(6, 2))
        self.pad_diag = tk.Text(left, height=6, bg='#0e1b2e', fg=FG, relief='flat', font=('Segoe UI', 9), wrap='word', padx=8, pady=6)
        self.pad_diag.pack(fill='both', expand=True)
        for tag, col in (('bad', BAD_C), ('warn', WARN), ('ok', OK_C), ('info', MUTED)):
            self.pad_diag.tag_configure(tag, foreground=col)
        self.pad_diag.configure(state='disabled')
        right = tk.Frame(body, bg=PANEL)
        body.add(right, stretch='never', minsize=int(420 * self.scale))
        rt = tk.Frame(right, bg=PANEL); rt.pack(fill='x')
        tk.Label(rt, text='CANLI TEST', fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(side='left')
        self.pad_slot = tk.IntVar(value=0)
        tk.Label(rt, text='   XInput yuvası:', fg=MUTED, bg=PANEL, font=('Segoe UI', 9)).pack(side='left')
        for i in range(4):
            tk.Radiobutton(rt, text=str(i + 1), variable=self.pad_slot, value=i, fg=FG, bg=PANEL, selectcolor=PANEL2, activebackground=PANEL,
                           activeforeground=FG, font=('Segoe UI', 9), command=self._pad_slot_changed).pack(side='left')
        self.pad_canvas = GamepadCanvas(right, self.scale * 0.72)
        self.pad_canvas.pack(pady=(2, 2))
        info = tk.Frame(right, bg=PANEL2, padx=10, pady=5); info.pack(fill='x')
        info.grid_columnconfigure(1, weight=1); info.grid_columnconfigure(3, weight=1)
        self.pad_info = {}
        for key, text, r, col, span in (('conn', 'Bağlantı', 0, 0, 1), ('bat', 'Pil', 0, 2, 1), ('pressed', 'Basılı', 1, 0, 1), ('drift', 'Kayma', 1, 2, 1)):
            tk.Label(info, text=text, anchor='w', fg=MUTED, bg=PANEL2, font=('Segoe UI', 9)).grid(row=r, column=col, sticky='w', padx=(0, 6))
            v = tk.StringVar(value='—')
            tk.Label(info, textvariable=v, anchor='w', fg=FG, bg=PANEL2, font=('Consolas', 9)).grid(row=r, column=col + 1, columnspan=span, sticky='w', padx=(0, 12))
            self.pad_info[key] = v
        self.pad_rows, self.pad_stats, self.pad_bt, self.pad_slots_seen = [], {}, {}, None
        self.pad_drift_hits = 0
        self.pad_tick_n = 0
        self.pad_tab = None
        self._pad_render_diag()

    def _pad_selected(self):
        try:
            if self.pad_tab is None:
                self.pad_tab = len(self.tabs.tabs()) - 1
            return self.tabs.index('current') == self.pad_tab
        except tk.TclError:
            return False

    def _pad_slot_changed(self):
        self.pad_drift_hits = 0

    def _pad_tick(self):
        """Canli test: sekme acikken 50 ms, degilken 600 ms araliklarla XInput okunur (yalnizca Windows)."""
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        if not self._pad_selected():
            self.after(600, self._pad_tick); return
        if not self.xi.available():
            self.pad_canvas.show(None, 'Canlı test yalnızca Windows\'ta (XInput) çalışır.')
            self.pad_info['conn'].set('XInput yok')
            self.after(600, self._pad_tick); return
        slot = self.pad_slot.get()
        st = self.xi.state(slot)
        if st:
            self.pad_canvas.show(st, 'L %+6d %+6d   R %+6d %+6d   LT %3d  RT %3d' % (st['lx'], st['ly'], st['rx'], st['ry'], st['lt'], st['rt']))
            self.pad_info['conn'].set('Bağlı (yuva %d, %s)' % (slot + 1, self.xi.name))
            bat = self.xi.battery(slot)
            self.pad_info['bat'].set(core.xinput_battery_text(*bat) if bat else '—')
            self.pad_info['pressed'].set(' '.join(core.xinput_pressed(st['buttons'])) or '—')
            idle = not st['buttons'] and not st['lt'] and not st['rt']
            drifting = idle and (core.stick_drift(st['lx'], st['ly']) or core.stick_drift(st['rx'], st['ry']))
            self.pad_drift_hits = min(200, self.pad_drift_hits + 1) if drifting else max(0, self.pad_drift_hits - 2)
            self.pad_info['drift'].set('Olası kayma (drift)' if self.pad_drift_hits > 60 else 'Yok')
        else:
            self.pad_canvas.show(None, 'Yuva %d boş — kolu bağlayın ya da başka yuvayı seçin.' % (slot + 1))
            for k in ('conn', 'bat', 'pressed', 'drift'):
                self.pad_info[k].set('Bağlı değil' if k == 'conn' else '—')
        self.pad_tick_n += 1
        slots = self.xi.connected_slots() if (self.pad_tick_n % 20 == 0 or self.pad_slots_seen is None) else self.pad_slots_seen   # bos yuva sorgusu pahali: ~1 sn'de bir
        if slots != self.pad_slots_seen:
            self.pad_slots_seen = slots
            self._pad_render_diag()
        self.after(50, self._pad_tick)

    def pad_scan(self):
        def done(job):
            devs = [d for d in job.data if d.get('type') == 'controller']
            bt = [d for d in job.data if d.get('type') == 'bt-radio']
            self.pad_bt = bt[0] if bt else {}
            self.pad_rows, self.pad_stats = core.build_controller_view(devs)
            for k, (v, text) in self.pad_chips.items():
                v.set('%d %s' % (self.pad_stats.get(k, 0), text))
            t = self.pad_tree
            t.clear()
            for i, r in enumerate(self.pad_rows):
                t.add('c%d' % i, r.get('name') or '(adsız aygıt)', (r['bus_text'], ('Sorunlu: ' if r['problem_dev'] else '') + (r.get('status') or '?'), r['id']),
                      checked=r['problem_dev'], tags=('risky',) if r['problem_dev'] else (), payload=r)
            if not self.pad_rows:
                t.add('none', 'Xbox kolu bulunamadı', ('', '', ''), checkable=False)
            t.refresh_marks()
            self._pad_render_diag()
        self.start([Job('Xbox kolları', cmd=ps_cmd('controller-list'), on_done=done, show_output=False)])

    def _pad_render_diag(self):
        slots = self.pad_slots_seen if self.pad_slots_seen is not None else []
        lines = core.controller_advice(self.pad_stats, self.xi.available(), slots, self.pad_bt, bool(core.fc_settings_dirs()))
        if not self.pad_stats:
            lines.insert(0, ('info', '"Tara" ile Xbox kol aygıtlarını listeleyin.'))
        d = self.pad_diag
        d.configure(state='normal'); d.delete('1.0', 'end')
        for level, text in lines:
            d.insert('end', '●  ' + text + '\n', level)
        d.configure(state='disabled')

    def pad_reset(self):
        rows = [p for p in self.pad_tree.checked_payloads() if p] or list(self.pad_rows)
        if not rows:
            messagebox.showinfo('Kol / Gamepad', 'Önce "Tara" ile kol aygıtlarını listeleyin.'); return
        if not self.need_admin('controller-reset'):
            return
        names = '\n'.join('• %s (%s)' % (r.get('name') or r['id'], r['bus_text']) for r in rows[:12])
        if not messagebox.askyesno('Kol sürücüsünü sıfırla', 'Şu aygıtların kaydı kaldırılıp donanım yeniden taranacak:\n\n%s\n\n'
                                   'USB ile bağlıysa ardından kabloyu çıkarıp takın; Bluetooth ise gerekirse yeniden eşleştirin.\nDevam edilsin mi?' % names):
            return
        self.start([Job('Kol sürücüsünü sıfırla (%d)' % len(rows), cmd=ps_cmd('controller-reset', InstanceIds='|'.join(r['id'] for r in rows)),
                        cancel_ok=False, on_done=lambda j: self.pad_scan())])

    def pad_bt_restart(self):
        if not self.need_admin('bt-restart'):
            return
        self.start([Job('Bluetooth hizmetini yeniden başlat', cmd=ps_cmd('bt-restart'), cancel_ok=False, on_done=lambda j: self.pad_scan())])

    def pad_open(self, target, title):
        if not IS_WIN:
            self.write('%s yalnızca Windows\'ta açılır (%s).\n' % (title, target)); return
        try:
            os.startfile(target)
            self.write('%s açıldı.\n' % title)
        except OSError as e:
            self.write('%s açılamadı: %s\n' % (title, e))

    def pad_xbox_accessories(self):
        def work(runner, job):
            if not IS_WIN:
                runner.say('Xbox Accessories yalnızca Windows\'ta açılır.'); return 0
            r = subprocess.run(['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive', '-Command',
                                "(Get-AppxPackage -Name 'Microsoft.XboxDevices' | Select-Object -First 1).PackageFamilyName"],
                               capture_output=True, text=True, timeout=30, creationflags=CREATIONFLAGS)
            fam = (r.stdout or '').strip()
            if fam:
                runner.say('Xbox Accessories açılıyor. Kol USB ile takılıyken "..." > "Güncelleme" ile firmware denetlenir.')
                os.startfile('shell:AppsFolder\\%s!App' % fam)
            else:
                runner.say('Xbox Accessories kurulu değil; Microsoft Store sayfası açılıyor.')
                os.startfile('ms-windows-store://pdp/?productid=9NBLGGH30XJ3')
            return 0
        self.start([Job('Xbox Accessories', func=work, cancel_ok=False)])

    def _pad_fc_dir(self):
        dirs = core.fc_settings_dirs()
        if dirs:
            return dirs[-1]
        picked = filedialog.askdirectory(title='EA SPORTS FC ayar klasörünü seçin (%LOCALAPPDATA%\\EA SPORTS FC xx)')
        return pathlib.Path(picked) if picked else None

    def pad_open_fc_dir(self):
        dirs = core.fc_settings_dirs()
        if not dirs:
            messagebox.showinfo('FC ayar klasörü', 'EA SPORTS FC klasörü bulunamadı (%LOCALAPPDATA%). Oyun bu kullanıcıyla hiç açılmamış olabilir.'); return
        self.pad_open(str(dirs[-1]), dirs[-1].name)

    def pad_fc_reset(self):
        folder = self._pad_fc_dir()
        if not folder:
            return
        files = core.fc_settings_files(folder)
        if not files:
            messagebox.showinfo('FC ayarları', '"%s\\settings" altında Settings dosyası yok.' % folder); return
        if not messagebox.askyesno('FC ayarlarını sıfırla', '%s\n\nŞu dosyalar yedeklenip silinecek; oyun açılışta yenilerini oluşturur '
                                   '(kontrol ve görüntü ayarları varsayılana döner):\n\n%s\n\nOyun KAPALI olmalı. Devam edilsin mi?'
                                   % (folder.name, '\n'.join('• ' + f.name for f in files))):
            return

        def work(runner, job):
            bdir, names = core.fc_reset_settings(folder)
            runner.say('Yedeklendi ve sıfırlandı (%d dosya): %s' % (len(names), ', '.join(names)))
            runner.say('Yedek klasörü: %s  — geri almak için dosyaları settings klasörüne kopyalayın.' % bdir)
            return 0
        self.start([Job('FC ayarlarını yedekle ve sıfırla', func=work, cancel_ok=False)])

    # ------------------------------------------------------------------ GUNCELLEME (paket yukleme)
    def open_updater(self):
        if getattr(self, 'upd_win', None) and self.upd_win.winfo_exists():
            self.upd_win.lift(); return
        win = self.upd_win = tk.Toplevel(self); win.title('AGFO System Care — Güncelleme'); win.configure(bg=PANEL); win.transient(self)
        w, h = int(860 * self.scale), int(620 * self.scale)
        win.geometry('%dx%d+%d+%d' % (w, h, self.winfo_rootx() + max(0, (self.winfo_width() - w) // 2), self.winfo_rooty() + 40))
        top = tk.Frame(win, bg=PANEL); top.pack(fill='x', padx=16, pady=(14, 4))
        tk.Label(top, text='Güncelleme', fg=FG, bg=PANEL, font=('Segoe UI', 13, 'bold')).pack(side='left')
        tk.Label(top, text='Kurulu sürüm: %s' % VERSION, fg=OK_C, bg=PANEL2, font=('Segoe UI', 9, 'bold'), padx=10, pady=3).pack(side='left', padx=10)
        self.label(win, 'Konum: %s\nGüncelleme paketi (.zip) seçin. Paket önce denetlenir (yapı, sürüm, MANIFEST/SHA-256, Python derleme, PowerShell sözdizimi); '
                        'mevcut sürüm yedeklenir, yeni dosyalar yerleştirilir ve uygulama yeniden başlar. Bir adım başarısız olursa önceki sürüm otomatik geri yüklenir. '
                        'Ayarlarınız ve günlükler etkilenmez.' % self.install_dir, wraplength=int(820 * self.scale)).pack(fill='x', padx=16)
        bar = tk.Frame(win, bg=PANEL); bar.pack(fill='x', padx=16, pady=8)
        self.btn(bar, 'GitHub\'da denetle', lambda: self.gh_check(force=True), 'go')
        self.btn(bar, 'Güncelleme paketi seç (.zip)…', self.upd_pick, 'ghost')
        self.upd_apply_btn = self.btn(bar, 'Uygula ve yeniden başlat', self.upd_apply, 'danger', action=False)   # durumu yalnizca denetim sonucu belirler
        self.upd_apply_btn.configure(state='disabled')
        ghf = tk.Frame(win, bg=PANEL); ghf.pack(fill='x', padx=16, pady=(0, 6))
        self.upd_gh_state = tk.StringVar(value='GitHub deposu: %s (etiket: %s*)' % (ghu.GITHUB_REPO, core.GH_PREFIX))
        tk.Label(ghf, textvariable=self.upd_gh_state, fg=MUTED, bg=PANEL, font=('Segoe UI', 9)).pack(side='left')
        self.upd_auto = tk.BooleanVar(value=self.settings.get('auto_update_check', True))

        def _auto():
            self.settings['auto_update_check'] = bool(self.upd_auto.get())
            core.save_settings(self.settings)
        ttk.Checkbutton(ghf, text='Açılışta güncellemeleri denetle', variable=self.upd_auto, command=_auto).pack(side='right')
        self.upd_check = tk.Text(win, height=11, bg='#09111e', fg='#dce8fa', relief='flat', font=('Consolas', 9), padx=10, pady=8, wrap='word')
        self.upd_check.pack(fill='both', expand=True, padx=16)
        for tg, col in (('ok', OK_C), ('fail', BAD_C), ('warn', WARN), ('h', ACCENT)):
            self.upd_check.tag_configure(tg, foreground=col)
        self.upd_check.insert('end', 'Paket seçilmedi.'); self.upd_check.configure(state='disabled')
        low = tk.Frame(win, bg=PANEL); low.pack(fill='x', padx=16, pady=(8, 14))
        tk.Label(low, text='Yedekler (en son %d)' % core.UPDATE_KEEP_BACKUPS, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.upd_bk = ttk.Treeview(low, columns=('ver', 'time'), show='headings', height=3)
        self.upd_bk.heading('ver', text='Sürüm'); self.upd_bk.heading('time', text='Yedek zamanı')
        self.upd_bk.column('ver', width=140); self.upd_bk.column('time', width=220)
        self.upd_bk.pack(side='left', fill='x', expand=True)
        rb = tk.Frame(low, bg=PANEL); rb.pack(side='left', padx=10)
        self.btn(rb, 'Seçili yedeğe dön', self.upd_rollback, 'ghost', side='top')
        self.btn(rb, 'Geçmiş', self.upd_history, 'ghost', action=False, side='top')
        self.upd_info = None
        self._upd_refresh_backups()

    def _upd_refresh_backups(self):
        if not getattr(self, 'upd_bk', None) or not self.upd_bk.winfo_exists():
            return
        self.upd_bk.delete(*self.upd_bk.get_children())
        for b in core.list_backups(self.backup_root):
            self.upd_bk.insert('', 'end', iid=b['path'], values=(b['version'], b['time']))

    def _upd_show(self, lines):
        tx = self.upd_check
        tx.configure(state='normal'); tx.delete('1.0', 'end')
        for text, tag in lines:
            tx.insert('end', text + '\n', tag)
        tx.configure(state='disabled')

    def upd_pick(self):
        path = filedialog.askopenfilename(parent=self.upd_win, title='Güncelleme paketi seçin', filetypes=[('Güncelleme paketi', '*.zip'), ('Tüm dosyalar', '*.*')])
        if not path:
            return
        self.upd_apply_btn.configure(state='disabled')
        stage = core.APP_DATA_DIR / 'update-stage'
        self._upd_show([('Denetleniyor: %s' % path, 'h')])

        def work(runner, job):
            info = core.inspect_update(path, VERSION)
            checks = []
            if info['ok']:
                core.stage_update(path, info, stage)
                checks = core.preflight(stage)
            job.data = [path, info, checks]
            return 0 if info['ok'] and not any(st == 'fail' for _, st, _ in checks) else 2
        self.start([Job('Güncelleme paketi denetimi', func=work, on_done=self._upd_checked, cancel_ok=False)])

    def _upd_checked(self, job):
        path, info, checks = job.data
        L = [('Paket: %s' % path, 'h')]
        if info['version']:
            arrow = '%s → %s' % (VERSION, info['version'])
            L.append(('✓ Sürüm: %s%s' % (arrow, '  (DÜŞÜRME)' if info['downgrade'] else ('  (aynı sürüm, yeniden kurulum)' if info['same'] else '')),
                      'warn' if (info['downgrade'] or info['same']) else 'ok'))
        for e in info['errors']:
            L.append(('✗ ' + e, 'fail'))
        if info['ok']:
            L.append(('✓ Paket yapısı ve dosya yolları güvenli; zorunlu dosyalar mevcut', 'ok'))
            L.append(('✓ %d çalışma dosyası: %s' % (len(info['files']), ', '.join(sorted(info['files'])[:8]) + (' …' if len(info['files']) > 8 else '')), 'ok'))
            if info['manifest']:
                L.append(('✓ MANIFEST.json: tüm dosyaların SHA-256 özetleri doğrulandı', 'ok'))
        for wmsg in info['warnings']:
            L.append(('! ' + wmsg, 'warn'))
        for name, st, det in checks:
            L.append((('✓ ' if st == 'ok' else ('✗ ' if st == 'fail' else '– ')) + name + (('  — ' + det) if det else ''), {'ok': 'ok', 'fail': 'fail'}.get(st, 'warn')))
        ready = info['ok'] and not any(st == 'fail' for _, st, _ in checks)
        L.append(('', None))
        L.append(('Hazır: "Uygula ve yeniden başlat" ile kurabilirsiniz.' if ready else 'Bu paket kurulamaz.', 'ok' if ready else 'fail'))
        self.upd_info = (path, info) if ready else None
        if getattr(self, 'upd_win', None) and self.upd_win.winfo_exists():
            self._upd_show(L)
            self.upd_apply_btn.configure(state='normal' if ready else 'disabled')

    def upd_apply(self):
        if not self.upd_info or self.busy:
            return
        self.upd_apply_btn.configure(state='disabled')
        path, info = self.upd_info
        msg = 'AGFO System Care %s → %s güncellenecek.\nMevcut sürüm yedeklenecek; uygulama yeniden başlatılacak.' % (VERSION, info['version'])
        if info['downgrade']:
            msg += '\n\nDİKKAT: Bu daha ESKİ bir sürüm.'
        if not info['manifest']:
            msg += '\n\nUYARI: Pakette MANIFEST.json yok; dosya bütünlüğü doğrulanamadı. Yalnızca güvendiğiniz kaynaktan gelen paketi kurun.'
        if not messagebox.askyesno('Güncellemeyi uygula', msg + '\n\nDevam edilsin mi?', parent=self.upd_win):
            return
        stage = core.APP_DATA_DIR / 'update-stage'

        def work(runner, job):
            runner.say('Yedekleniyor ve güncelleniyor: %s' % self.install_dir)
            job.data = [core.apply_update(stage, self.install_dir, self.backup_root, VERSION, info['version'])]
            runner.say('Güncellendi. Yedek: %s' % job.data[0])
            import shutil
            shutil.rmtree(stage, ignore_errors=True)
            return 0
        self.start([Job('Güncelleme uygula', func=work, on_done=lambda j: self._upd_done(j, info['version']), cancel_ok=False)])

    def _upd_done(self, job, new_version):
        self._upd_refresh_backups()
        if job.code != 0 or not job.data:
            self._upd_show([('✗ Güncelleme uygulanamadı; önceki sürüm geri yüklendi. Ayrıntı işlem günlüğünde.', 'fail')])
            return
        self.upd_info = None
        self._upd_show([('✓ AGFO System Care %s kuruldu. Uygulama yeniden başlatılıyor…' % new_version, 'ok')])
        self.after(800, self.restart_app)

    def upd_rollback(self):
        sel = self.upd_bk.selection()
        if not sel:
            messagebox.showinfo('Yedekler', 'Listeden bir yedek seçin.', parent=self.upd_win); return
        b = next((x for x in core.list_backups(self.backup_root) if x['path'] == sel[0]), None)
        if not b or not messagebox.askyesno('Önceki sürüme dön', 'Sürüm %s (%s) geri yüklenecek; mevcut sürüm de yedeklenecek. Uygulama yeniden başlatılacak. Devam?'
                                            % (b['version'], b['time']), parent=self.upd_win):
            return

        def work(runner, job):
            target, bdir = core.rollback_update(b['path'], self.install_dir, VERSION)
            job.data = [target]
            runner.say('Geri dönüldü: %s (mevcut sürüm yedeği: %s)' % (target, bdir))
            return 0
        self.start([Job('Önceki sürüme dön', func=work, on_done=lambda j: self._upd_done(j, j.data[0] if j.data else ''), cancel_ok=False)])

    def upd_history(self):
        h = core.update_history(15)
        messagebox.showinfo('Güncelleme geçmişi', '\n'.join(h) if h else 'Henüz güncelleme yapılmadı.', parent=self.upd_win)

    # ------------------------------------------------------------------ GITHUB GUNCELLEME (tek tik)
    def gh_check(self, force=True):
        """Arka planda GitHub surumlerini denetler (is kuyrugunu mesgul etmez)."""
        def work():
            res = ghu.check_for_update(core.GH_PREFIX, VERSION, core.GH_STATE, core.GH_ASSET, force=force,
                                       user_agent='AGFO-System-Care/' + VERSION)
            self.messages.put(('call', lambda: self._gh_checked(res, force)))   # Tk yalnizca ana is parcacigindan
        threading.Thread(target=work, daemon=True).start()

    def _gh_checked(self, res, force):
        st = res.get('status')
        if st == 'update':
            self.gh_result = res
            rel = res['release']
            self.gh_banner_text.set('Yeni sürüm hazır: AGFO System Care %s  (kurulu: %s%s)' % (res['version'], VERSION,
                                    (', yayın: ' + rel['published']) if rel.get('published') else ''))
            if not self.gh_banner.winfo_ismapped():
                self.gh_banner.pack(fill='x', padx=22, pady=(0, 8), before=self.paned)
            self.write('GitHub: yeni sürüm %s mevcut — üstteki "Şimdi güncelle" ile tek tıkla kurabilirsiniz.\n' % res['version'])
        elif force:
            msg = {'current': 'Güncelsiniz (son sürüm %s).' % res.get('version', VERSION), 'none': 'GitHub\'da henüz System Care sürümü yok.',
                   'skipped': 'Sürüm %s atlanmış olarak işaretli.' % res.get('version', ''), 'error': 'Denetlenemedi: %s' % res.get('message', '')}.get(st, st)
            self.write('GitHub güncelleme denetimi: %s\n' % msg)
            if getattr(self, 'upd_gh_state', None):
                try:
                    self.upd_gh_state.set(msg)
                except tk.TclError:
                    pass
        if st == 'update' and getattr(self, 'upd_gh_state', None):
            try:
                self.upd_gh_state.set('Yeni sürüm: %s — "Şimdi güncelle" ile kurun.' % res['version'])
            except tk.TclError:
                pass

    def gh_show_notes(self):
        if not self.gh_result:
            return
        rel = self.gh_result['release']
        messagebox.showinfo('Sürüm %s notları' % self.gh_result['version'], (rel.get('notes') or 'Not eklenmemiş.')[:3000] + '\n\n' + rel.get('url', ''))

    def gh_skip(self):
        if self.gh_result:
            ghu.skip_version(core.GH_STATE, self.gh_result['version'])
            self.write('Sürüm %s atlandı; daha yeni bir sürüm çıkınca yeniden bildirilecek.\n' % self.gh_result['version'])
        self.gh_banner.pack_forget()

    def gh_update(self):
        """Tek tik: indir -> SHA-256 -> paket denetimi -> on kontrol -> yedekle/uygula -> yeniden baslat."""
        res = self.gh_result
        if not res or self.busy:
            if self.busy:
                messagebox.showinfo('Meşgul', 'Bir işlem sürüyor; bitince tekrar deneyin.')
            return
        rel, asset = res['release'], res['asset']
        notes = (rel.get('notes') or '').strip()
        if not messagebox.askyesno('Güncelleme', 'AGFO System Care %s → %s\n\n%s\n\nİndirilip doğrulanacak, mevcut sürüm yedeklenecek ve uygulama '
                                   'yeniden başlatılacak. Devam edilsin mi?' % (VERSION, res['version'], (notes[:800] + ('…' if len(notes) > 800 else '')) or 'Sürüm notu yok.')):
            return
        dest = core.GH_DOWNLOAD_DIR / asset['name']
        stage = core.APP_DATA_DIR / 'update-stage'

        def work(runner, job):
            runner.say('GitHub: %s indiriliyor (%s)' % (asset['name'], rel.get('url', '')))
            sha = ghu.expected_sha256(rel, asset, user_agent='AGFO-System-Care/' + VERSION)
            ghu.download_asset(asset, dest, sha, runner.progress_cb('İndiriliyor'), runner.stop.is_set, user_agent='AGFO-System-Care/' + VERSION)
            runner.say('İndirildi ve SHA-256 doğrulandı (%s…).' % sha[:16])
            info = core.inspect_update(str(dest), VERSION)
            if not info['ok']:
                raise OSError('Paket denetimi başarısız: ' + '; '.join(info['errors']))
            if info['version'] != res['version']:
                raise OSError('Paket sürümü (%s) etiketle (%s) uyuşmuyor.' % (info['version'], res['version']))
            core.stage_update(str(dest), info, stage)
            checks = core.preflight(stage)
            bad = [n + ': ' + d for n, s_, d in checks if s_ == 'fail']
            for n, s_, d in checks:
                runner.say(('✓ ' if s_ == 'ok' else ('✗ ' if s_ == 'fail' else '– ')) + n + (('  ' + d) if d else ''))
            if bad:
                raise OSError('Ön kontrol başarısız: ' + '; '.join(bad))
            runner.say('Yedekleniyor ve kuruluyor: %s' % self.install_dir)
            bdir = core.apply_update(stage, self.install_dir, self.backup_root, VERSION, info['version'])
            import shutil
            shutil.rmtree(stage, ignore_errors=True)
            try:
                dest.unlink()
            except OSError:
                pass
            job.data = [info['version'], bdir]
            runner.say('Kuruldu (yedek: %s).' % bdir)
            return 0

        def done(job):
            if job.code == 0 and job.data:
                self.gh_banner.pack_forget()
                self.write('AGFO System Care %s kuruldu; uygulama yeniden başlatılıyor…\n' % job.data[0])
                self.after(900, self.restart_app)
            else:
                messagebox.showerror('Güncelleme', 'Güncelleme tamamlanamadı; kurulu sürüm değişmedi veya geri yüklendi. Ayrıntı işlem günlüğünde.')
        self.start([Job('GitHub güncellemesi %s' % res['version'], func=work, on_done=done, cancel_ok=True)])

    def restart_app(self):
        if self.no_restart:
            return
        try:
            subprocess.Popen([sys.executable, str(pathlib.Path(self.install_dir) / 'app.pyw')], cwd=str(self.install_dir),
                             creationflags=getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
        except OSError as e:
            messagebox.showerror('Yeniden başlatma', 'Uygulamayı elle yeniden açın: %s' % e)
            return
        self.destroy()

    # ------------------------------------------------------------------ ortak
    def need_admin(self, action):
        if action in ADMIN_ACTIONS and not self.admin:
            if messagebox.askyesno('Yönetici gerekli', 'Bu işlem yönetici yetkisi ister. Uygulama yönetici olarak yeniden açılsın mı?'):
                self.elevate()
            return False
        return True

    def start(self, jobs, quiet=False):
        if self.busy and self.in_callback:
            # Bir isin sonuc geri-cagrisindan baslatilan zincir is: mevcut sira bitince calistir.
            self.pending.extend(jobs)
            return True
        if self.busy:
            if not quiet:
                messagebox.showinfo('Meşgul', 'Bir işlem sürüyor; bitmesini bekleyin veya Durdur\'a basın.')
            return False
        self.busy = True
        self._set_buttons('disabled')
        self.runner.run(jobs)
        return True

    def _set_buttons(self, state):
        # Kapatilan pencerelerin (or. Guncelleme) dugmeleri listeden ayiklanir.
        alive = []
        for b in self.action_buttons:
            try:
                if b.winfo_exists():
                    b.configure(state=state)
                    alive.append(b)
            except tk.TclError:
                pass
        self.action_buttons = alive

    def finish(self):
        self.busy = False
        self.cancel_btn.configure(state='disabled')
        self._set_buttons('normal')

    def cancel(self):
        if not self.busy:
            return
        if not messagebox.askyesno('Durdur', 'Süren işlem (ve sıradaki işler) durdurulsun mu?'):
            return
        self.write('Kullanıcı tarafından durduruluyor...\n')
        self.runner.kill()

    def write(self, msg):
        self.log.configure(state='normal'); self._insert(msg); self._trim(); self.log.see('end'); self.log.configure(state='disabled')

    def _insert(self, msg, progress=False):
        if self.progress_active:
            self.log.delete('end-1l linestart', 'end-1c')
            self.progress_active = False
        self.log.insert('end', msg)
        self.progress_active = progress

    def _trim(self):
        try:
            lines = int(self.log.index('end-1c').split('.')[0])
        except Exception:
            return
        if lines > LOG_WIDGET_MAX_LINES:
            self.log.delete('1.0', '%d.0' % LOG_WIDGET_TRIM_LINES)

    def clear_log(self):
        self.log.configure(state='normal'); self.log.delete('1.0', 'end'); self.progress_active = False; self.log.configure(state='disabled')

    def poll(self):
        items = []
        try:
            while len(items) < 2000:
                items.append(self.messages.get_nowait())
        except queue.Empty:
            pass
        if items:
            self.log.configure(state='normal')
            for kind, val in items:
                if kind == 'line':
                    self._insert(val)
                elif kind == 'progress':
                    self._insert(val, progress=True)
                elif kind == 'status':
                    self.status.set('Çalışıyor: ' + val)
                elif kind == 'cancel_ok':
                    self.cancel_btn.configure(state='normal' if val else 'disabled')
                elif kind == 'jobdone':
                    job = val
                    if job.cmd or job.shell:
                        self._insert('Sonuç: %s — %s%s\n' % (job.code, hint(job.code), ('  ·  günlük: ' + job.logfile) if job.logfile else ''))
                    self.status.set(hint(job.code) + ' — ' + job.title)
                    if job.on_done:
                        self.log.configure(state='disabled')
                        self.in_callback = True
                        try:
                            job.on_done(job)
                        except Exception as e:
                            self.write('Arayüz hatası (%s): %s\n' % (job.title, e))
                        finally:
                            self.in_callback = False
                        self.log.configure(state='normal')
                elif kind == 'call':
                    self.log.configure(state='disabled')
                    try:
                        val()
                    except Exception as e:
                        self.write('Arayüz hatası: %s\n' % e)
                    self.log.configure(state='normal')
                elif kind == 'alldone':
                    self.finish()
                    if self.pending:
                        nxt, self.pending = self.pending, []
                        self.start(nxt)
            self._trim(); self.log.see('end'); self.log.configure(state='disabled')
        self.after(POLL_MS, self.poll)

    def elevate(self):
        if not IS_WIN or self.busy:
            return
        exe = sys.executable
        params = '' if getattr(sys, 'frozen', False) else '"' + str(BASE / 'app.pyw') + '"'
        try:
            result = ctypes.windll.shell32.ShellExecuteW(None, 'runas', exe, params, str(BASE), 1)
            if result <= 32:
                raise OSError('Yönetici izni verilmedi')
            self.destroy()
        except Exception as e:
            messagebox.showerror('Yönetici erişimi', str(e))

    def on_close(self):
        if self.busy:
            if not messagebox.askyesno('İşlem sürüyor', 'Bir işlem sürüyor. Durdurulup uygulama kapatılsın mı?\n'
                                       '(Kurulum/onarım işlemleri arka planda tamamlanabilir.)'):
                return
            self.runner.kill()
        self.destroy()

    def open_logs(self):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        if IS_WIN:
            os.startfile(str(LOG_DIR))


def app_data_dir():
    core.APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return core.APP_DATA_DIR


if __name__ == '__main__':
    App().mainloop()
