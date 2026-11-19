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


def set_palette(key):
    globals().update(theme.tokens(key if key in theme.theme_keys() else theme.DEFAULT))


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
INTERNAL_PS_ACTIONS = ['vpn-status','tweak-read','tweak-write','dns-list','dns-flush','explorer-restart','controller-list','controller-reset','bt-restart','phantom-list','phantom-remove','appx-list','appx-remove','driver-analyze','driver-scan','driver-install','devices','drivers-list','driver-backup','app-scan','app-update','recycle-paths']
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
        self.navlist = tk.Frame(nav, bg=NAV_BG)
        self.navlist.pack(fill='x', pady=(6, 0))

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
        global THEME_KEY
        THEME_KEY = self.settings.get('theme') if self.settings.get('theme') in theme.theme_keys() else theme.DEFAULT
        set_palette(THEME_KEY)
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
        self.theme_hooks = []
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
        if TB is not None:
            s = ttk.Style()
            theme.register_themes(s)
            s.theme_use(theme.tb_name(THEME_KEY))
            s.configure('.', font=('Segoe UI', 10))
        else:
            s = ttk.Style(self)
            s.theme_use('clam')
            s.configure('.', background=PANEL, foreground=FG, fieldbackground=PANEL2, font=('Segoe UI', 10),
                        bordercolor=BORDER, lightcolor=PANEL2, darkcolor=PANEL2, troughcolor=PANEL)
            s.configure('Treeview', background=TREE_BG, fieldbackground=TREE_BG, foreground=FG, borderwidth=0)
            s.configure('Treeview.Heading', background=PANEL2, foreground=FG, relief='flat')
            s.map('Treeview.Heading', background=[('active', SEL)], foreground=[('active', SEL_FG)])
            s.configure('TCheckbutton', background=PANEL, foreground=FG, indicatorbackground=TREE_BG, indicatorforeground=FG)
            s.map('TCheckbutton', background=[('active', PANEL)], indicatorbackground=[('selected', SEL)])
            s.configure('TRadiobutton', background=PANEL, foreground=FG, indicatorbackground=TREE_BG, indicatorforeground=FG)
            s.map('TRadiobutton', background=[('active', PANEL)], indicatorbackground=[('selected', SEL)])
            s.configure('TCombobox', fieldbackground=PANEL2, background=PANEL2, foreground=FG, arrowcolor=FG, selectbackground=PANEL2, selectforeground=FG)
            s.map('TCombobox', fieldbackground=[('readonly', PANEL2)], foreground=[('readonly', FG)], selectbackground=[('readonly', PANEL2)], selectforeground=[('readonly', FG)])
            s.configure('TEntry', fieldbackground=PANEL2, foreground=FG, insertcolor=FG)
            s.configure('Vertical.TScrollbar', background=PANEL2, troughcolor=PANEL, arrowcolor=FG)
            s.configure('TButton', background=BTN_GHOST, foreground=FG, padding=(12, 6), relief='flat')
        s.map('Treeview', background=[('selected', SEL)], foreground=[('selected', SEL_FG)])
        s.configure('Treeview', rowheight=int(24 * self.scale))
        s.configure('Treeview.Heading', font=('Segoe UI', 9, 'bold'))
        s.configure('Card.TFrame', background=PANEL)
        # Ag araclari (SuperTools sayfalari) stil adlari: ayni tema jetonlari
        for name in ('White.TFrame', 'Page.TFrame'):
            s.configure(name, background=PANEL)
        for name, fg, font in (('White.TLabel', FG, ('Segoe UI', 10)), ('Info.TLabel', MUTED, ('Segoe UI', 9)), ('Small.TLabel', MUTED, ('Segoe UI', 9)),
                               ('Section.TLabel', FG, ('Segoe UI', 11, 'bold')), ('Heading.TLabel', FG, ('Segoe UI', 16, 'bold')),
                               ('Status.TLabel', ACCENT, ('Segoe UI', 9)), ('Metric.TLabel', FG, ('Segoe UI', 20, 'bold'))):
            s.configure(name, background=PANEL, foreground=fg, font=font)
        s.configure('Blue.TButton', background=BTN, foreground=BTN_FG, font=('Segoe UI', 9, 'bold'), padding=(12, 6))
        s.map('Blue.TButton', background=[('active', ACCENT), ('disabled', PANEL2)], foreground=[('disabled', MUTED)])
        s.configure('SSH.TNotebook', background=PANEL, borderwidth=0)
        s.configure('SSH.TNotebook.Tab', background=PANEL2, foreground=FG, padding=(12, 6))
        s.map('SSH.TNotebook.Tab', background=[('selected', SEL)], foreground=[('selected', SEL_FG)])
        s.configure('Alt.TCheckbutton', background=PANEL2, foreground=FG)
        s.map('Alt.TCheckbutton', background=[('active', PANEL2)])
        self.option_add('*TCombobox*Listbox.background', PANEL2)
        self.option_add('*TCombobox*Listbox.foreground', FG)
        self.option_add('*TCombobox*Listbox.selectBackground', SEL)
        self.option_add('*TCombobox*Listbox.selectForeground', SEL_FG)

    # dugme turu -> (ttkbootstrap bootstyle, klasik gorunum jetonu)
    KIND = {'normal': ('primary', 'BTN'), 'go': ('success', 'BTN_GO'), 'danger': ('danger', 'BTN_DANGER'),
            'ghost': ('secondary-outline', 'BTN_GHOST'), 'stop': ('danger-outline', 'STOP_BG')}

    def mkbtn(self, parent, text, cmd, kind='normal', small=False, **kw):
        if TB is not None:
            return ttk.Button(parent, text=text, command=cmd, bootstyle=self.KIND[kind][0], cursor='hand2', **kw)
        tok = self.KIND[kind][1]
        g = globals()
        return tk.Button(parent, text=text, command=cmd, bg=g[tok], fg=g[tok + '_FG'], activebackground=ACCENT, activeforeground=g[tok + '_FG'],
                         relief='flat', cursor='hand2', padx=10 if small else 12, pady=3 if small else 6, font=('Segoe UI', 9, 'bold'),
                         disabledforeground=DISABLED_FG, bd=0, highlightthickness=0, **kw)

    def btn(self, parent, text, cmd, kind='normal', action=True, side='left', **kw):
        b = self.mkbtn(parent, text, cmd, kind, **kw)
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
        tk.Label(top, text='Temizlik · programlar · sürücüler · ince ayarlar · dosya düzeni · VPN ve ağ araçları — BleachBit, BCU, SDIO, WinGet, Tailscale ve Windows araçları tek arayüzde',
                 fg=MUTED, bg=BG, font=('Segoe UI', 10)).pack(anchor='w', pady=(2, 0))
        st = tk.Frame(self, bg=PANEL, padx=12, pady=8); st.pack(fill='x', padx=22, pady=8)
        self.status = tk.StringVar(value=('Hazır (yönetici)' if self.admin else 'Hazır (standart kullanıcı)') + ' — işlemler siz başlatmadıkça uygulanmaz.')
        tk.Label(st, textvariable=self.status, fg=FG, bg=PANEL, font=('Segoe UI', 10)).pack(side='left')
        self.cancel_btn = self.mkbtn(st, 'Durdur', self.cancel, 'stop', small=True, state='disabled')
        self.cancel_btn.pack(side='right')
        self.mkbtn(st, 'Güncelleme…', self.open_updater, 'go', small=True).pack(side='right', padx=(0, 8))
        if not self.admin:
            self.mkbtn(st, 'Yönetici olarak yeniden aç', self.elevate, 'ghost', small=True).pack(side='right', padx=(0, 8))

        self.gh_banner = tk.Frame(self, bg=BANNER_BG, padx=12, pady=7)   # yeni surum varsa gosterilir
        self.gh_banner_text = tk.StringVar(value='')
        tk.Label(self.gh_banner, textvariable=self.gh_banner_text, fg=BANNER_BG_FG, bg=BANNER_BG, font=('Segoe UI', 10, 'bold')).pack(side='left')
        for txt, cmd, kind in (('Bu sürümü atla', self.gh_skip, 'ghost'), ('Notlar', self.gh_show_notes, 'ghost'), ('Şimdi güncelle', self.gh_update, 'go')):
            self.mkbtn(self.gh_banner, txt, cmd, kind, small=True).pack(side='right', padx=(6, 0))
        self.gh_result = None
        main = tk.Frame(self, bg=BG)
        self.main = main
        main.pack(fill='both', expand=True, padx=22, pady=(0, 16))
        nav = tk.Frame(main, bg=NAV_BG, width=int(220 * self.scale))
        nav.pack(side='left', fill='y', padx=(0, 10))
        nav.pack_propagate(False)
        paned = tk.PanedWindow(main, orient='vertical', bg=BG, sashwidth=6, bd=0)
        self.paned = paned
        paned.pack(side='left', fill='both', expand=True)
        self.tabs = NavBook(paned, nav)
        paned.add(self.tabs, stretch='always', minsize=int(360 * self.scale))
        self.net = net_tools.NetTools(self, self._net_colors)
        for group, pages in self.nav_pages():
            self.tabs.add_group(group)
            for title, builder in pages:
                f = tk.Frame(self.tabs, bg=PANEL)
                self.tabs.add(f, text=title)
                builder(f)
        self._build_appearance(nav)
        self.tabs.bind('<<NotebookTabChanged>>', self._tw_on_tab, add='+')
        self.tabs.bind('<<NotebookTabChanged>>', self._remember_page, add='+')
        self.tabs.bind('<<NotebookTabChanged>>', self._inst_on_tab, add='+')
        self.tabs.bind('<<NotebookTabChanged>>', lambda _e: self.net.on_tab(), add='+')
        self.theme_hooks.append(self.net.retheme)
        self._open_last_page()

        bottom = tk.Frame(paned, bg=BG)
        paned.add(bottom, stretch='never', minsize=int(140 * self.scale))
        bar = tk.Frame(bottom, bg=BG); bar.pack(fill='x', pady=(8, 0))
        tk.Label(bar, text='İŞLEM GÜNLÜĞÜ', bg=BG, fg=ACCENT, font=('Segoe UI', 10, 'bold')).pack(side='left')
        self.mkbtn(bar, 'Günlük klasörünü aç', self.open_logs, 'ghost', small=True).pack(side='right')
        self.mkbtn(bar, 'Temizle', self.clear_log, 'ghost', small=True).pack(side='right', padx=(0, 8))
        self.log = tk.Text(bottom, height=7, bg=LOG_BG, fg=LOG_FG, insertbackground=FG, relief='flat', font=('Consolas', 9),
                           padx=10, pady=8, wrap='word', undo=False)
        self.log.pack(fill='both', expand=True, pady=(6, 0))
        self.log.configure(state='disabled')
        self.write('AGFO System Care %s — motorlar bu pencerede çalışır; hiçbir işlem web sayfasına yönlendirmez.\n' % VERSION)
        if not self.admin:
            self.write('Not: sürücü kurulumu, SDIO, DISM/SFC ve geri yükleme noktası yönetici ister.\n')

    # ------------------------------------------------------------------ gezinme ve gorunum
    def nav_pages(self):
        return [('Genel', [('Motorlar', self._tab_engines)]),
                ('Temizlik', [('Temizlik', self._tab_clean), ('Bloatware', self._tab_bloat), ('Dosya düzeni', self._tab_organizer)]),
                ('Sistem', [('İnce ayarlar', self._tab_tweaks), ('Sürücüler', self._tab_drivers), ('Aygıt temizliği', self._tab_phantom),
                            ('Bakım ve sağlık', self._tab_maint)]),
                ('Uygulamalar', [('Programlar', self._tab_programs), ('Uygulama güncellemeleri', self._tab_apps), ('Uygulama kur', self._tab_install)]),
                ('Ağ', [('VPN', self._tab_vpn), ('Ağ tarayıcı', lambda f: self.net.build_scan(f)), ('Ağ testleri', lambda f: self.net.build_diag(f)),
                        ('SSH sunucularım', lambda f: self.net.build_ssh(f)), ('SSH oturumları', lambda f: self.net.build_sessions(f))]),
                ('Donanım', [('Kol / Gamepad', self._tab_pad)])]

    def _remember_page(self, _e=None):
        try:
            title = self.tabs.tab(self.tabs.current, 'text')
        except Exception:
            return
        if self.settings.get('last_page') != title:
            self.settings['last_page'] = title
            core.save_settings(self.settings)

    def _open_last_page(self):
        title = self.settings.get('last_page')
        try:
            self.tabs.select(title if title else 0)
        except tk.TclError:
            self.tabs.select(0)

    def _build_appearance(self, nav):
        box = tk.Frame(nav, bg=NAV_BG)
        box.pack(side='bottom', fill='x', padx=14, pady=12)
        tk.Label(box, text='GÖRÜNÜM', bg=NAV_BG, fg=NAV_MUTED, font=('Segoe UI', 8, 'bold'), anchor='w').pack(fill='x')
        tk.Label(box, text='Renk teması', bg=NAV_BG, fg=NAV_FG, font=('Segoe UI', 9), anchor='w').pack(fill='x', pady=(4, 2))
        self.theme_box = ttk.Combobox(box, state='readonly', values=[t['label'] for t in theme.THEMES], width=18)
        self.theme_box.set(theme.theme_by_key(THEME_KEY)['label'])
        self.theme_box.pack(fill='x')
        self.theme_box.bind('<<ComboboxSelected>>', lambda _e: self.apply_theme(theme.label_to_key(self.theme_box.get())))
        self.ui_state = tk.StringVar(value='Modern görünüm: ' + TB_STATE)
        tk.Label(box, textvariable=self.ui_state, bg=NAV_BG, fg=NAV_MUTED, font=('Segoe UI', 8), anchor='w', justify='left',
                 wraplength=int(185 * self.scale)).pack(fill='x', pady=(6, 2))
        if TB is None and theme.python_ok() and self.settings.get('modern_ui', True):
            self.ui_btn = self.btn(box, 'Modern görünümü kur', self.install_modern_ui, 'normal', side='top')
        elif TB is None and not self.settings.get('modern_ui', True):
            self.btn(box, 'Modern görünümü aç', lambda: self.set_modern_ui(True), 'ghost', side='top', action=False)
        elif TB is not None:
            self.btn(box, 'Klasik görünüme dön', lambda: self.set_modern_ui(False), 'ghost', side='top', action=False)

    def set_modern_ui(self, on):
        self.settings['modern_ui'] = bool(on)
        core.save_settings(self.settings)
        if self.busy:
            messagebox.showinfo('Görünüm', 'Değişiklik uygulama yeniden açıldığında geçerli olur.')
            return
        if messagebox.askyesno('Görünüm', 'Görünüm değişikliği için uygulama yeniden açılsın mı?'):
            self.restart_app()

    def apply_theme(self, key):
        global THEME_KEY
        if key == THEME_KEY or key not in theme.theme_keys():
            return
        rev = {}
        for name, val in theme.tokens(THEME_KEY).items():
            if isinstance(val, str) and val.startswith('#'):
                rev.setdefault(val.lower(), name)
        snap = []

        def walk(w):
            for opt in COLOR_OPTS:
                try:
                    v = str(w.cget(opt)).lower()
                except (tk.TclError, ValueError):
                    continue
                if v in rev:
                    snap.append((w, opt, rev[v]))
            for c in w.winfo_children():
                walk(c)
        walk(self)
        THEME_KEY = key
        set_palette(key)
        self._style()                                      # ttkbootstrap: theme_use tum ttk bilesenlerini yeniden cizer
        g = globals()
        for w, opt, tok in snap:                           # tk bilesenleri: eski jetonun yeni rengi
            try:
                w.configure(**{opt: g[tok]})
            except tk.TclError:
                pass
        for ct in CheckTree.INSTANCES:
            ct.retheme()
        for hook in self.theme_hooks:
            try:
                hook()
            except tk.TclError:
                pass
        self.tabs.refresh_nav()
        self.configure(bg=BG)
        self.settings['theme'] = key
        core.save_settings(self.settings)
        self.write('Renk teması: %s\n' % theme.theme_by_key(key)['label'])

    def install_modern_ui(self):
        if not theme.python_ok():
            messagebox.showinfo('Modern görünüm', 'Modern görünüm Python 3.10 veya üstünü ister.'); return
        lib = theme.ui_lib_dir(core.APP_DATA_DIR)
        if not messagebox.askyesno('Modern görünüm', 'ttkbootstrap %s (ve gerektirdiği Pillow) PyPI\'den indirilip yalnızca System Care\'in kendi klasörüne kurulacak:\n%s\n\n'
                                   'Python kurulumunuza dokunulmaz; internet gerekir. Devam edilsin mi?' % (theme.TB_VERSION, lib)):
            return

        def done(job):
            if job.code == 0:
                self.ui_state.set('Modern görünüm: kuruldu — yeniden açınca etkin')
                if messagebox.askyesno('Modern görünüm', 'Kurulum tamamlandı. Uygulama yeniden açılsın mı?'):
                    self.restart_app()
            else:
                self.write('Modern görünüm bileşeni kurulamadı (%s). Klasik görünüm kullanılmaya devam ediyor.\n' % hint(job.code))
        self.start([Job('Modern görünüm bileşeni (ttkbootstrap)', cmd=theme.pip_install_cmd(theme.console_python(), lib), on_done=done, cancel_ok=True)])

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
        self.mkbtn(bar, 'Taşı', go, 'danger').pack(side='right')
        self.mkbtn(bar, 'Vazgeç', win.destroy, 'ghost').pack(side='right', padx=8)

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

    # ------------------------------------------------------------------ DOSYA DUZENI (Smart Organizer cekirdegi, organizer_core.py)
    ORG_FILTERS = ('Tümü', 'Bekliyor', 'Kabul', 'Red', 'Taşındı', 'Hata')

    def _tab_organizer(self, f):
        head = tk.Frame(f, bg=PANEL); head.pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(head, text='Dosya düzeni', fg=FG, bg=PANEL, font=('Segoe UI', 12, 'bold')).pack(side='left')
        tk.Label(head, text='Planla → düzenle → onayla → taşı', fg=MUTED, bg=PANEL, font=('Segoe UI', 9)).pack(side='left', padx=(12, 0))
        try:
            import organizer_core as org
        except Exception as e:                         # Python 3.8/3.9 vb.
            self.org = None
            self.label(f, 'Dosya düzeni bu Python sürümünde açılamadı: %s' % e).pack(fill='x', padx=16, pady=8)
            return
        self.org = org
        self.label(f, 'Masaüstü ve Belgeler klasörünün doğrudan altındaki dosya, klasör ve kısayolları sınıflandırır, "%s" altında kategori klasörlerine '
                      'taşımayı önerir. Siz onaylamadan hiçbir şey taşınmaz, üzerine yazma ve silme yapılmaz; "Son taşımayı geri al" her şeyi eski yerine döndürür. '
                      'Yerel AI (Ollama + Gemma) isteğe bağlıdır; dosya içeriği bilgisayardan çıkmaz.' % org.APP_FOLDER,
                   wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(2, 4))
        self.org_roots = org.standard_roots()
        self.org_items, self.org_by_id = [], {}
        self.org_state = org.app_state_dir()
        self.org_journal = org.MoveJournal(self.org_state / 'moves.sqlite3')
        try:
            oset = json.loads((self.org_state / 'settings.json').read_text(encoding='utf-8'))
        except Exception:
            oset = {}
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.org_desktop, self.org_docs = tk.BooleanVar(value=True), tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text='Masaüstü', variable=self.org_desktop).pack(side='left', padx=(0, 8))
        ttk.Checkbutton(bar, text='Belgeler', variable=self.org_docs).pack(side='left', padx=(0, 10))
        self.btn(bar, '1  Analiz et', self.org_scan, 'go')
        self.btn(bar, '2  Yerel AI ile iyileştir', self.org_ai, 'normal')
        tk.Label(bar, text='Model:', fg=FG, bg=PANEL).pack(side='left', padx=(8, 2))
        self.org_model = ttk.Combobox(bar, width=16, values=[oset.get('ollama_model', 'gemma3:1b')])
        self.org_model.set(oset.get('ollama_model', 'gemma3:1b'))
        self.org_model.pack(side='left')
        self.btn(bar, 'Modelleri bul', self.org_models, 'ghost')
        tk.Label(bar, text='En çok:', fg=FG, bg=PANEL).pack(side='left', padx=(6, 2))
        self.org_limit = tk.StringVar(value=str(oset.get('ai_limit', '30')))
        ttk.Entry(bar, width=5, textvariable=self.org_limit).pack(side='left')
        flt = tk.Frame(f, bg=PANEL); flt.pack(fill='x', padx=16, pady=(6, 0))
        tk.Label(flt, text='Ara:', fg=FG, bg=PANEL).pack(side='left')
        self.org_q = tk.StringVar()
        ttk.Entry(flt, textvariable=self.org_q, width=30).pack(side='left', padx=6)
        self.org_q.trace_add('write', lambda *_: self._org_render())
        tk.Label(flt, text='Durum:', fg=FG, bg=PANEL).pack(side='left', padx=(10, 0))
        self.org_filter = ttk.Combobox(flt, state='readonly', width=12, values=self.ORG_FILTERS); self.org_filter.current(0)
        self.org_filter.pack(side='left', padx=6)
        self.org_filter.bind('<<ComboboxSelected>>', lambda _e: self._org_render())
        self.btn(flt, 'Hedefi değiştir', self.org_edit, 'ghost', action=False, side='right')
        self.btn(flt, 'Klasörü göster', self.org_open, 'ghost', action=False, side='right')
        tf = ttk.Frame(f, style='Card.TFrame'); tf.pack(fill='both', expand=True, padx=16, pady=(8, 4))
        cols = ('source', 'kind', 'folder', 'dest', 'conf', 'decision')
        self.org_tree = ttk.Treeview(tf, columns=cols, show='tree headings', selectmode='extended', height=8)
        self.org_tree.heading('#0', text='Dosya / kısayol'); self.org_tree.column('#0', width=280, stretch=True)
        for key, title, w, anc in (('source', 'Konum', 90, 'center'), ('kind', 'Tür', 70, 'w'), ('folder', 'Kategori', 120, 'w'),
                                   ('dest', 'Önerilen hedef', 360, 'w'), ('conf', 'Güven', 60, 'center'), ('decision', 'Karar', 80, 'center')):
            self.org_tree.heading(key, text=title); self.org_tree.column(key, width=w, anchor=anc, stretch=(key == 'dest'))
        ys = ttk.Scrollbar(tf, orient='vertical', command=self.org_tree.yview)
        self.org_tree.configure(yscrollcommand=ys.set)
        self.org_tree.pack(side='left', fill='both', expand=True); ys.pack(side='right', fill='y')
        self.org_tree.bind('<<TreeviewSelect>>', lambda _e: self._org_preview())
        self.org_tree.bind('<Double-1>', lambda _e: self.org_edit())
        self._org_tags()
        self.theme_hooks.append(self._org_tags)
        cmd = tk.Frame(f, bg=PANEL); cmd.pack(fill='x', padx=16, pady=(4, 0))
        self.btn(cmd, 'Seçilenleri kabul et', lambda: self.org_decide('Kabul', False), 'ghost', action=False)
        self.btn(cmd, 'Seçilenleri reddet', lambda: self.org_decide('Red', False), 'ghost', action=False)
        self.btn(cmd, 'Tümünü kabul et', lambda: self.org_decide('Kabul', True), 'ghost', action=False)
        self.btn(cmd, 'Tümünü reddet', lambda: self.org_decide('Red', True), 'ghost', action=False)
        self.btn(cmd, '3  Onaylananları taşı', self.org_move, 'danger', side='right')
        self.btn(cmd, 'Son taşımayı geri al', self.org_undo, 'normal', side='right')
        self.org_summary = tk.StringVar(value='Tarama yapılmadı.')
        tk.Label(f, textvariable=self.org_summary, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold'), anchor='w').pack(fill='x', padx=16, pady=(4, 0))
        self.org_info = tk.StringVar(value='Bir satır seçin: kaynak, öneri nedeni ve içerik örneği burada görünür. Hedefi çift tıklayarak değiştirebilirsiniz.')
        tk.Label(f, textvariable=self.org_info, fg=MUTED, bg=PANEL, font=('Segoe UI', 9), anchor='w', justify='left',
                 wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(2, 10))

    def _org_tags(self):
        for tg, col in (('Kabul', OK_C), ('Red', BAD_C), ('Taşındı', MUTED), ('Hata', WARN)):
            self.org_tree.tag_configure(tg, foreground=col)

    def _org_save_settings(self):
        try:
            self.org_state.mkdir(parents=True, exist_ok=True)
            (self.org_state / 'settings.json').write_text(json.dumps({'ollama_model': self.org_model.get().strip(), 'ai_limit': self.org_limit.get().strip()},
                                                                     ensure_ascii=False, indent=2), encoding='utf-8')
        except OSError:
            pass

    def _org_selected(self):
        return [self.org_by_id[i] for i in self.org_tree.selection() if i in self.org_by_id]

    def _org_render(self):
        if not getattr(self, 'org', None):
            return
        t = self.org_tree
        keep = set(t.selection())
        t.delete(*t.get_children())
        need, q = self.org_filter.get(), self.org_q.get().strip().casefold()
        for it in self.org_items:
            if need != 'Tümü' and it.decision != need:
                continue
            if q and q not in (it.path.name + ' ' + it.folder + ' ' + str(it.path)).casefold():
                continue
            src = 'Masaüstü' if it.path.parent == self.org_roots.get('Masaüstü') else 'Belgeler'
            t.insert('', 'end', iid=it.item_id, text=it.path.name,
                     values=(src, 'Klasör' if it.is_dir else (it.path.suffix.lower() or 'Dosya'), it.category,
                             '%s / %s / %s' % (it.root, self.org.APP_FOLDER, it.folder), '%d%%' % int(it.confidence * 100), it.decision),
                     tags=(it.decision,))
        sel = tuple(i for i in keep if t.exists(i))
        if sel:
            t.selection_set(sel)
        c = {k: sum(1 for x in self.org_items if x.decision == k) for k in self.ORG_FILTERS[1:]}
        self.org_summary.set('Toplam %d  ·  Bekliyor %d  ·  Kabul %d  ·  Red %d  ·  Taşındı %d  ·  Hata %d' %
                             (len(self.org_items), c['Bekliyor'], c['Kabul'], c['Red'], c['Taşındı'], c['Hata']) if self.org_items else 'Tarama yapılmadı.')

    def _org_preview(self):
        sel = self._org_selected()
        if not sel:
            return
        it = sel[0]
        txt = 'Kaynak: %s  ·  Öneri nedeni: %s  ·  Hedef: %s' % (it.path, it.reason, it.target(self.org_roots))
        if it.snippet:
            txt += '\nİçerik örneği: ' + it.snippet[:500].replace('\n', ' ')
        if len(sel) > 1:
            txt += '\nToplam %d öğe seçili.' % len(sel)
        self.org_info.set(txt)

    def org_scan(self):
        labels = [n for n, v in (('Masaüstü', self.org_desktop), ('Belgeler', self.org_docs)) if v.get()]
        if not labels:
            messagebox.showwarning('Dosya düzeni', 'En az bir kaynak (Masaüstü / Belgeler) seçin.'); return
        if any(it.decision == 'Kabul' for it in self.org_items) and not messagebox.askyesno('Planı yenile', 'Uygulanmamış onaylar kaybolacak. Yeniden taransın mı?'):
            return
        org = self.org

        def work(runner, job):
            last = [0]

            def prog(n):
                if n - last[0] >= 100:
                    last[0] = n
                    runner.say('%d öğe incelendi...' % n)
            items, warnings = org.scan(self.org_roots, labels, progress=prog)
            job.data = [(items, warnings)]
            runner.say('Tarama tamamlandı: %d öğe.' % len(items))
            return 0

        def done(job):
            if not job.data:
                return
            self.org_items, warnings = job.data[0]
            self.org_by_id = {it.item_id: it for it in self.org_items}
            self._org_render()
            if warnings:
                messagebox.showwarning('Tarama notları', '\n'.join(warnings[:12]))
        self.start([Job('Dosya düzeni: analiz', func=work, on_done=done, cancel_ok=False)])

    def org_models(self):
        org = self.org

        def work(runner, job):
            try:
                job.data = [org.list_ollama_models()]
                runner.say('Ollama modelleri: %s' % (', '.join(job.data[0][:6]) or 'yok (KUR-GEMMA.cmd ile kurulabilir)'))
                return 0
            except RuntimeError as e:
                runner.say('Ollama: %s' % e)
                return 1

        def done(job):
            if job.data:
                models = job.data[0]
                self.org_model.configure(values=models)
                chosen = org.pick_ollama_model(self.org_model.get().strip(), models) if models else None
                if chosen and chosen != self.org_model.get().strip():
                    self.org_model.set(chosen)
                    self._org_save_settings()
        self.start([Job('Ollama modelleri', func=work, on_done=done, cancel_ok=False)])

    def org_ai(self):
        org = self.org
        cand = [i for i in self.org_items if i.decision == 'Bekliyor' and i.confidence < 0.90 and not i.is_dir]
        if not cand:
            messagebox.showinfo('Yerel AI', 'AI ile incelenecek bekleyen / belirsiz öğe yok. Önce analiz edin.'); return
        try:
            limit = int(self.org_limit.get())
            assert 1 <= limit <= 200
        except (ValueError, AssertionError):
            messagebox.showerror('Yerel AI', 'Öğe sınırı 1-200 arasında olmalı.'); return
        model = self.org_model.get().strip()
        if not model:
            messagebox.showerror('Yerel AI', 'Ollama model adını girin.'); return
        cand = cand[:limit]
        self._org_save_settings()

        def work(runner, job):
            try:
                models = org.list_ollama_models()
            except RuntimeError as e:
                runner.say('Ollama: %s' % e); return 1
            if not models:
                runner.say('Ollama çalışıyor ama model yok. Smart Organizer klasöründeki KUR-GEMMA.cmd ile Gemma kurulabilir.'); return 1
            sel = org.pick_ollama_model(model, models)
            changed, results = 0, []
            for n, it in enumerate(cand, 1):
                if runner.stop.is_set():
                    break
                runner.say('Yerel AI %d/%d: %s' % (n, len(cand), it.path.name[:40]))
                try:
                    results.append((it, org.ollama_refine(it, model=sel)))
                    changed += 1
                except Exception as e:
                    runner.say('  %s: %s' % (it.path.name, e))
                    if changed == 0 and n == 1:
                        break
            job.data = [results]
            return 0

        def done(job):
            for it, (cat, conf, reason) in (job.data[0] if job.data else []):
                it.category, it.folder, it.confidence, it.reason = cat, cat, conf, reason
            self._org_render()
            self.write('Yerel AI: %d öneri güncellendi.\n' % len(job.data[0] if job.data else []))
        self.start([Job('Dosya düzeni: yerel AI', func=work, on_done=done, cancel_ok=True)])

    def org_decide(self, decision, all_items):
        items = self.org_items if all_items else self._org_selected()
        if not items and not all_items:
            messagebox.showinfo('Seçim', 'Önce bir veya daha fazla öğe seçin.'); return
        n = 0
        for it in items:
            if it.decision in ('Bekliyor', 'Kabul', 'Red', 'Hata'):
                it.decision = decision; n += 1
        self._org_render()
        self.write('Dosya düzeni: %d karar güncellendi.\n' % n)

    def org_edit(self):
        sel = [it for it in self._org_selected() if it.decision != 'Taşındı']
        if not sel:
            messagebox.showinfo('Hedef', 'Önce düzenlenecek öğeyi seçin.'); return
        org = self.org
        w = tk.Toplevel(self); w.title('Hedef klasörü düzenle'); w.configure(bg=PANEL); w.transient(self); w.resizable(False, False)
        rv, fv = tk.StringVar(value=sel[0].root), tk.StringVar(value=sel[0].folder)
        body = tk.Frame(w, bg=PANEL, padx=20, pady=16); body.pack(fill='both', expand=True)
        tk.Label(body, text='Hedef ana konum', fg=FG, bg=PANEL).pack(anchor='w')
        ttk.Combobox(body, textvariable=rv, values=list(self.org_roots), state='readonly').pack(fill='x', pady=(4, 12))
        tk.Label(body, text='Alt klasör (ör. Denetimler/BRCGS/2026)', fg=FG, bg=PANEL).pack(anchor='w')
        ttk.Entry(body, textvariable=fv, width=48).pack(fill='x', pady=(4, 4))
        tk.Label(body, text='Öğeler “%s” altında düzenlenir.' % org.APP_FOLDER, fg=MUTED, bg=PANEL).pack(anchor='w')

        def save():
            try:
                folder = org.valid_subfolder(fv.get())
                if rv.get() not in self.org_roots:
                    raise ValueError('Geçersiz ana konum')
            except ValueError as e:
                messagebox.showerror('Hedef geçersiz', str(e), parent=w); return
            for it in sel:
                it.root, it.folder = rv.get(), folder
                it.category = folder.split('/')[0]
                it.reason += ' | Hedef kullanıcı tarafından düzenlendi'
            w.destroy()
            self._org_render()
        bar = tk.Frame(body, bg=PANEL); bar.pack(fill='x', pady=(14, 0))
        self.btn(bar, 'Uygula', save, 'normal', action=False, side='right')
        self.btn(bar, 'İptal', w.destroy, 'ghost', action=False, side='right')
        w.bind('<Return>', lambda _e: save()); w.bind('<Escape>', lambda _e: w.destroy())

    def org_open(self):
        sel = self._org_selected()
        if not sel:
            messagebox.showinfo('Klasör', 'Önce bir öğe seçin.'); return
        if IS_WIN:
            subprocess.Popen(['explorer', '/select,%s' % sel[0].path])
        else:
            messagebox.showinfo('Klasör', str(sel[0].path.parent))

    def org_move(self):
        approved = [it for it in self.org_items if it.decision == 'Kabul']
        if not approved:
            messagebox.showinfo('Taşı', 'Taşınacak kabul edilmiş öğe yok.'); return
        roots = sorted({it.root for it in approved})
        if not messagebox.askyesno('Toplu taşıma onayı', '%d dosya/klasör taşınacak.\n\nHedef: %s / %s\n\nKısayolların taşınması masaüstü simgelerini kaldırır; hedefleri değişmez. '
                                   'OneDrive kullanıyorsanız eşitleme de olabilir.\n\nÜzerine yazma ve silme yapılmaz; geri alma kaydı tutulur. Devam?'
                                   % (len(approved), ', '.join(roots), self.org.APP_FOLDER), icon='warning'):
            return
        org = self.org

        def work(runner, job):
            count, errors, batch = org.execute_approved(approved, self.org_roots, self.org_journal,
                                                        progress=lambda n: runner.say('%d/%d taşındı...' % (n, len(approved))) if n % 25 == 0 else None)
            for e in errors[:20]:
                runner.say('  HATA: %s' % e)
            runner.say('Taşınan: %d, hata: %d (işlem %s)' % (count, len(errors), batch[:8]))
            return 0 if not errors else 2
        self.start([Job('Dosya düzeni: taşı', func=work, on_done=lambda j: self._org_render(), cancel_ok=False)])

    def org_undo(self):
        batch = self.org_journal.latest_batch()
        if not batch:
            messagebox.showinfo('Geri al', 'Geri alınabilecek taşıma kaydı yok.'); return
        if not messagebox.askyesno('Son taşımayı geri al', 'Son taşımadaki tüm öğeler eski konumlarına döndürülecek. Özgün konumda aynı adlı öğe varsa atlanır. Devam?'):
            return

        def work(runner, job):
            count, errors = self.org_journal.undo(batch)
            for e in errors[:20]:
                runner.say('  HATA: %s' % e)
            runner.say('Geri alınan: %d, hata: %d' % (count, len(errors)))
            return 0 if not errors else 2

        def done(job):
            self.org_items, self.org_by_id = [], {}
            self._org_render()
        self.start([Job('Dosya düzeni: geri al', func=work, on_done=done, cancel_ok=False)])

    # ------------------------------------------------------------------ INCE AYARLAR (3.7.0; katalog WinCleaner'dan, MIT)
    TW_FILTERS = ['Tümü', 'Uygulanmamış', 'Uygulanmış', 'Seçili olanlar']

    def _tab_tweaks(self, f):
        head = tk.Frame(f, bg=PANEL); head.pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(head, text='İnce ayarlar', fg=FG, bg=PANEL, font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.tw_chips = {}
        for key, text, color in [('applied', 'uygulanmış', OK_C), ('not', 'uygulanmamış', ACCENT), ('partial', 'kısmen', WARN), ('total', 'ayar', MUTED)]:
            v = tk.StringVar(value='— ' + text)
            tk.Label(head, textvariable=v, fg=color, bg=PANEL2, font=('Segoe UI', 9, 'bold'), padx=10, pady=3).pack(side='left', padx=(10, 0))
            self.tw_chips[key] = (v, text)
        self.label(f, 'Gizlilik, oyun, görünüm, Windows 11 arayüzü, ağ ve hizmet ayarları tek listede. Her değişiklikten önce mevcut değer kaydedilir; '
                      '"Son değişikliği geri al" ve "Geçmiş" ayarları birebir eski hâline döndürür. "Varsayılana döndür" Windows\'un varsayılan değerini yazar. '
                      'Turuncu satırlar kullanımınıza göre sorun çıkarabilir; "Tehlikeli" satırlar yalnızca aşağıdaki izinle uygulanır.',
                   wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(2, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Durumu oku', self.tw_read, 'ghost')
        tk.Label(bar, text='Ön ayar:', fg=FG, bg=PANEL).pack(side='left', padx=(6, 0))
        self.tw_preset = ttk.Combobox(bar, state='readonly', width=24, values=[p['name'] for p in tweaks.cat.PRESETS])
        self.tw_preset.pack(side='left', padx=6)
        self.tw_preset.bind('<<ComboboxSelected>>', lambda _e: self.tw_preset_info())
        self.btn(bar, 'Ön ayarı seç', self.tw_pick_preset, 'ghost', action=False)
        self.btn(bar, 'Seçimi kaldır', lambda: self.tw_tree.set_all(False), 'ghost', action=False)
        self.btn(bar, 'Seçilenleri uygula', lambda: self.tw_apply('apply'), 'go')
        self.btn(bar, 'Seçilenleri varsayılana döndür', lambda: self.tw_apply('default'), 'danger')
        self.tw_count = tk.StringVar(value='')
        tk.Label(bar, textvariable=self.tw_count, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(side='right')
        bar2 = tk.Frame(f, bg=PANEL); bar2.pack(fill='x', padx=16, pady=(4, 0))
        self.btn(bar2, 'Son değişikliği geri al', self.tw_undo_last)
        self.btn(bar2, 'Geçmiş…', self.tw_history, 'ghost', action=False)
        self.btn(bar2, 'Profili dışa aktar', self.tw_export, 'ghost', action=False)
        self.btn(bar2, 'Profili içe aktar', self.tw_import, 'ghost', action=False)
        self.tw_rp = tk.BooleanVar(value=self.admin)
        ttk.Checkbutton(bar2, text='Önce geri yükleme noktası', variable=self.tw_rp).pack(side='left', padx=(10, 0))
        self.tw_danger = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar2, text='Tehlikeli ayarlara izin ver', variable=self.tw_danger).pack(side='left', padx=(10, 0))
        flt = tk.Frame(f, bg=PANEL); flt.pack(fill='x', padx=16, pady=(6, 0))
        tk.Label(flt, text='Göster:', fg=FG, bg=PANEL).pack(side='left')
        self.tw_filter = ttk.Combobox(flt, state='readonly', width=18, values=self.TW_FILTERS); self.tw_filter.current(0)
        self.tw_filter.pack(side='left', padx=6)
        self.tw_filter.bind('<<ComboboxSelected>>', lambda _e: self._tw_render())
        tk.Label(flt, text='Ara:', fg=FG, bg=PANEL).pack(side='left', padx=(10, 0))
        self.tw_q = tk.StringVar()
        ttk.Entry(flt, textvariable=self.tw_q, width=28).pack(side='left', padx=6)
        self.tw_q.trace_add('write', lambda *_: self._tw_render())
        cols = [('state', 'Durum', 120, 'w'), ('risk', 'Risk', 80, 'w'), ('cur', 'Şu an / hedef', 170, 'w'), ('need', 'Gerekir', 170, 'w'), ('desc', 'Açıklama', 420, 'w')]
        self.tw_tree = CheckTree(f, cols, first=('Ayar', 330), height=10, on_change=self._tw_count)
        self.tw_tree.pack(fill='both', expand=True, padx=16, pady=(8, 2))
        self.tw_tree.tree.bind('<<TreeviewSelect>>', lambda _e: self._tw_detail(), add=True)
        self.tw_info = tk.StringVar(value='Bir satır seçin: açıklaması burada görünür.')
        tk.Label(f, textvariable=self.tw_info, fg=MUTED, bg=PANEL, font=('Segoe UI', 9), justify='left', anchor='w',
                 wraplength=int(1100 * self.scale)).pack(fill='x', padx=16)
        dns = tk.Frame(f, bg=PANEL2, padx=10, pady=6); dns.pack(fill='x', padx=16, pady=(6, 10))
        tk.Label(dns, text='DNS', fg=ACCENT, bg=PANEL2, font=('Segoe UI', 9, 'bold')).pack(side='left')
        self.dns_choice = ttk.Combobox(dns, state='readonly', width=34, values=[p[1] for p in tweaks.DNS_PRESETS] + ['Özel adresler…'])
        self.dns_choice.current(0); self.dns_choice.pack(side='left', padx=6)
        self.dns_custom = tk.StringVar()
        ttk.Entry(dns, textvariable=self.dns_custom, width=24).pack(side='left', padx=(0, 6))
        for txt, cmd in (('Bağdaştırıcıları göster', self.dns_list), ('DNS\'i uygula (yönetici)', self.dns_apply), ('DNS önbelleğini temizle', self.dns_flush)):
            b = self.mkbtn(dns, txt, cmd, 'normal', small=True)
            b.pack(side='left', padx=(0, 6)); self.action_buttons.append(b)
        self.dns_state = tk.StringVar(value='')
        tk.Label(dns, textvariable=self.dns_state, fg=FG, bg=PANEL2, font=('Segoe UI', 9), anchor='w').pack(side='left', fill='x', expand=True)
        self.tw_items = [it for it in tweaks.item_by_id().values()]
        self.tw_reads, self.tw_states, self.tw_sel, self.tw_read_once, self.dns_adapters = {}, {}, set(), False, []
        self.tw_build = tweaks.windows_build()
        self._tw_tab = f
        self._tw_render()

    def _tw_on_tab(self, _e=None):
        try:
            if self.tabs.nametowidget(self.tabs.select()) is self._tw_tab and not self.tw_read_once and not self.busy:
                self.tw_read()
        except Exception:
            pass

    def _tw_visible_items(self):
        return [it for it in self.tw_items if tweaks.os_compatible(it, self.tw_build)]

    def _tw_target_text(self, it):
        if it.get('kind') == 'service':
            cur = tweaks.current_text(it, self.tw_reads)
            return '%s → %s' % (cur or '?', tweaks.START_NAME.get(it['start'], it['start']))
        return ''

    def _tw_need_text(self, it):
        need = []
        if tweaks.needs_admin_item(it):
            need.append('yönetici')
        if it.get('reboot'):
            need.append('yeniden başlatma')
        if it.get('explorer'):
            need.append('Gezgin yenileme')
        if it.get('anticheat'):
            need.append('hile koruması uyarısı')
        return ', '.join(need)

    def _tw_render(self):
        t = self.tw_tree
        if t.labels:
            visible = {pl['id'] for pl in t.payload.values() if pl}
            checked = {pl['id'] for pl in t.checked_payloads() if pl}
            self.tw_sel = checked | (self.tw_sel - visible)
        t.clear()
        mode = self.tw_filter.get()
        q = self.tw_q.get().strip().lower()
        tag_of = {'applied': 'st_new', 'partial': 'st_warn', 'missing': 'st_old', 'unknown': 'st_ok', 'not': 'st_ok'}
        items = self._tw_visible_items()
        for key, title in tweaks.CATEGORIES:
            rows = []
            for it in items:
                if it['cat'] != key:
                    continue
                st = self.tw_states.get(it['id'], '')
                if mode == 'Uygulanmamış' and st not in ('not', 'partial'):
                    continue
                if mode == 'Uygulanmış' and st != 'applied':
                    continue
                if mode == 'Seçili olanlar' and it['id'] not in self.tw_sel:
                    continue
                hay = ' '.join((it['name'], it.get('desc', ''), it['id'], it['svc'] if isinstance(it.get('svc'), str) else ''))
                if q and q not in hay.lower():
                    continue
                rows.append((it, st))
            if not rows:
                continue
            gid = 'g:' + key
            t.add(gid, '%s (%d)' % (title, len(rows)), ('', '', '', '', ''), tags=('group',), open_=True)
            for it, st in rows:
                blocked = it['risk'] == 'blocked'
                tags = (tag_of.get(st, 'st_ok'),)
                if it['risk'] in ('caution', 'danger'):
                    tags = tags + ('risky',)
                label = it['name'] + (' [%s]' % tweaks.SERVICE_GROUP.get(it.get('group', ''), it.get('group', '')) if it.get('kind') == 'service' else '')
                t.add('t:' + it['id'], label, (tweaks.STATE_NAME.get(st, '—'), tweaks.RISK_NAME[it['risk']], self._tw_target_text(it),
                                              'değiştirilemez' if blocked else self._tw_need_text(it), it.get('desc', '')),
                      parent=gid, checked=it['id'] in self.tw_sel and not blocked, checkable=not blocked, tags=tags, payload=it)
        t.refresh_marks()
        self._tw_count()
        counts = {'applied': 0, 'not': 0, 'partial': 0}
        for it in items:
            st = self.tw_states.get(it['id'])
            if st in counts:
                counts[st] += 1
        for k, (v, text) in self.tw_chips.items():
            v.set('%d %s' % (len(items) if k == 'total' else counts[k], text) if (self.tw_states or k == 'total') else '— ' + text)

    def _tw_count(self):
        n = len([p for p in self.tw_tree.checked_payloads() if p])
        self.tw_count.set('%d seçili' % n if n else '')

    def _tw_detail(self):
        sel = self.tw_tree.tree.selection()
        it = self.tw_tree.payload.get(sel[0]) if sel else None
        if not it:
            return
        extra = []
        if it.get('kind') == 'service':
            extra.append('Hizmet: %s, önerilen başlangıç: %s' % (it['svc'], tweaks.START_NAME.get(it['start'], it['start'])))
        need = self._tw_need_text(it)
        if need:
            extra.append('Gerekir: ' + need)
        self.tw_info.set('%s — %s%s' % (it['name'], it.get('desc', ''), ('   (' + '; '.join(extra) + ')') if extra else ''))

    def tw_preset_info(self):
        p = next((p for p in tweaks.cat.PRESETS if p['name'] == self.tw_preset.get()), None)
        if p:
            self.tw_info.set('%s: %s (%d ayar, %d hizmet)' % (p['name'], p['desc'], len(p['tweaks']), len(p['services'])))

    def tw_pick_preset(self):
        p = next((p for p in tweaks.cat.PRESETS if p['name'] == self.tw_preset.get()), None)
        if not p:
            messagebox.showinfo('Ön ayar', 'Önce listeden bir ön ayar seçin.'); return
        ids = set(tweaks.preset_items(p['id']))
        known = {it['id'] for it in self._tw_visible_items()}
        self.tw_sel = ids & known
        self.tw_filter.current(0)
        self.tw_tree.clear()
        self._tw_render()
        self.write('Ön ayar "%s": %d ayar işaretlendi (bu Windows sürümüne uymayanlar atlandı). Uygulamak için "Seçilenleri uygula".\n' % (p['name'], len(self.tw_sel)))

    def _plan_file(self, ops, tag):
        d = core.APP_DATA_DIR / 'plans'
        d.mkdir(parents=True, exist_ok=True)
        old = sorted(d.glob('*.json'))
        for p in old[:-20]:
            try:
                p.unlink()
            except OSError:
                pass
        path = d / ('%s-%s.json' % (datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'), tag))
        path.write_text(json.dumps({'ops': ops}, ensure_ascii=False), encoding='utf-8')
        return str(path)

    def tw_read(self):
        items = self._tw_visible_items()
        plan = tweaks.read_plan(items)
        path = self._plan_file(plan, 'read')

        def done(job):
            self.tw_read_once = True
            self.tw_reads = tweaks.reads_by_ref(job.data)
            if not self.tw_reads:
                self.write('İnce ayar durumu okunamadı (kod %s).\n' % job.code)
            self.tw_states = {it['id']: tweaks.item_state(it, self.tw_reads) for it in items} if self.tw_reads else {}
            self._tw_render()
        self.start([Job('İnce ayar durumu', cmd=ps_cmd('tweak-read', PlanFile=path), on_done=done, show_output=False, cancel_ok=True)], quiet=True)

    def tw_apply(self, mode):
        sel = [p for p in self.tw_tree.checked_payloads() if p and p['risk'] != 'blocked']
        if not sel:
            messagebox.showinfo('İnce ayarlar', 'Önce listeden ayar işaretleyin (veya bir ön ayar seçin).'); return
        danger = [p for p in sel if p['risk'] == 'danger']
        if danger and not self.tw_danger.get():
            messagebox.showwarning('Tehlikeli ayar', 'Seçimde tehlikeli ayar var (%s). Uygulamak için önce "Tehlikeli ayarlara izin ver" kutusunu işaretleyin.'
                                   % ', '.join(p['name'] for p in danger[:3]))
            return
        if mode == 'default':
            svc = [p for p in sel if p.get('kind') == 'service' or 'svc' in p]
            sel = [p for p in sel if p not in svc]
            if svc:
                self.write('Hizmetlerin Windows varsayılanı sürüme göre değiştiği için "varsayılana döndür" hizmetlere uygulanmaz; '
                           'hizmet değişikliklerini Geçmiş\'ten geri alın (%d hizmet atlandı).\n' % len(svc))
            if not sel:
                messagebox.showinfo('İnce ayarlar', 'Hizmetler geçmişten geri alınır ("Geçmiş…").'); return
        skipped = []
        if not self.admin:
            skipped = [p for p in sel if tweaks.needs_admin_item(p)]
            if skipped:
                rest = [p for p in sel if p not in skipped]
                if not rest:
                    if messagebox.askyesno('Yönetici gerekli', 'Seçilen ayarlar yönetici yetkisi ister. Uygulama yönetici olarak yeniden açılsın mı?'):
                        self.elevate()
                    return
                if not messagebox.askyesno('Yönetici gerekli', '%d ayar yönetici ister ve atlanacak; yalnızca %d kullanıcı ayarı uygulanacak.\n'
                                           'Tümü için uygulamayı yönetici olarak açın. Şimdilik devam edilsin mi?' % (len(skipped), len(rest))):
                    return
                sel = rest
        anti = [p for p in sel if p.get('anticheat')] if mode == 'apply' else []
        if anti and not messagebox.askyesno('Hile koruması uyarısı', 'Şu ayarlar bazı rekabetçi oyunların hile koruması (anti-cheat) tarafından '
                                            'sorun olarak görülebilir:\n  ' + '\n  '.join(p['name'] for p in anti) + '\n\nYine de uygulansın mı?'):
            return
        verb = 'uygulanacak' if mode == 'apply' else 'Windows varsayılanına döndürülecek'
        msg = '%d ayar %s:\n  %s%s' % (len(sel), verb, '\n  '.join(p['name'] for p in sel[:16]), '\n  ...' if len(sel) > 16 else '')
        caution = [p for p in sel if p['risk'] in ('caution', 'danger')]
        if caution and mode == 'apply':
            msg += '\n\nDİKKAT/TEHLİKELİ: %s' % ', '.join(p['name'] for p in caution[:5])
        msg += '\n\nÖnceki değerler kaydedilir; "Son değişikliği geri al" ile birebir geri dönülür.'
        if not messagebox.askyesno('İnce ayarları onaylayın', msg + '\n\nDevam edilsin mi?'):
            return
        plan = tweaks.build_write_plan(sel, mode)
        errs = tweaks.validate_ops(plan)
        if errs:
            messagebox.showerror('Plan hatası', '\n'.join(errs[:6])); return
        self._tw_run(plan, ('Uygula: ' if mode == 'apply' else 'Varsayılana döndür: ') + ', '.join(p['name'] for p in sel[:3]) + (' …' if len(sel) > 3 else ''),
                     rp=self.tw_rp.get())

    def _tw_run(self, plan, title, rp=False, undo_sid=None):
        path = self._plan_file(plan, 'write')
        jobs = []
        if rp:
            if self.admin:
                jobs.append(Job('Geri yükleme noktası', cmd=ps_cmd('restore-point'), cancel_ok=False))
            else:
                self.write('Geri yükleme noktası yönetici ister; atlandı.\n')

        def done(job):
            sess = tweaks.record_session(core.APP_DATA_DIR, title, plan, job.data)
            res = tweaks.write_results(job.data)
            ok = sum(1 for r in res if r.get('ok'))
            self.write('İnce ayarlar: %d/%d işlem tamam%s.\n' % (ok, len(plan), '' if sess else ' (geçmişe kaydedilecek değişiklik yok)'))
            if undo_sid and ok == len(plan):
                tweaks.mark_undone(core.APP_DATA_DIR, undo_sid)
            known = tweaks.item_by_id()
            done_ids = {plan[r['ref']].get('item') for r in res if r.get('ok') and isinstance(r.get('ref'), int) and 0 <= r['ref'] < len(plan)}
            touched = [known[i] for i in done_ids if i in known]
            if any(it.get('reboot') for it in touched):
                self.write('Not: bazı ayarlar yeniden başlatmadan sonra etkinleşir.\n')
            if any(it.get('explorer') for it in touched):
                if messagebox.askyesno('Gezgin', 'Görev çubuğu / Gezgin ayarlarının hemen görünmesi için Windows Gezgini yeniden başlatılsın mı?\n'
                                       '(Açık Gezgin pencereleri kapanır.)'):
                    self.start([Job('Gezgini yeniden başlat', cmd=ps_cmd('explorer-restart'), cancel_ok=False)])
            self.tw_read()
        jobs.append(Job(title, cmd=ps_cmd('tweak-write', PlanFile=path), on_done=done, cancel_ok=False))
        self.start(jobs)

    def _tw_undo_session(self, sess):
        ops = tweaks.undo_ops(sess['entries'])
        if not ops:
            messagebox.showinfo('Geri al', 'Bu oturumda geri alınacak başarılı değişiklik yok.'); return
        errs = tweaks.validate_ops(ops)
        if errs:
            messagebox.showerror('Geri alma planı', '\n'.join(errs[:6])); return
        if tweaks.needs_admin_ops(ops) and not self.admin:
            if messagebox.askyesno('Yönetici gerekli', 'Bu değişikliği geri almak yönetici yetkisi ister. Uygulama yönetici olarak yeniden açılsın mı?'):
                self.elevate()
            return
        if not messagebox.askyesno('Geri al', 'Şu oturum geri alınacak:\n%s\n\n%d işlem önceki değerlerine döndürülecek. Devam?' % (tweaks.session_summary(sess), len(ops))):
            return
        self._tw_run(ops, 'Geri alma: ' + sess['title'], undo_sid=sess['id'])

    def tw_undo_last(self):
        sessions = [s for s in tweaks.load_journal(core.APP_DATA_DIR) if not s.get('undone') and not s['title'].startswith('Geri alma:')]
        if not sessions:
            messagebox.showinfo('Geri al', 'Geri alınacak bir ince ayar değişikliği yok.'); return
        self._tw_undo_session(sessions[-1])

    def tw_history(self):
        sessions = list(reversed(tweaks.load_journal(core.APP_DATA_DIR)))
        w = tk.Toplevel(self); w.title('İnce ayar geçmişi'); w.configure(bg=PANEL)
        w.geometry('%dx%d' % (int(900 * self.scale), int(420 * self.scale)))
        tk.Label(w, text='Değişiklik oturumları (en yeni üstte). Seçip geri alabilirsiniz; geri alma da kayda geçer.', fg=MUTED, bg=PANEL).pack(fill='x', padx=12, pady=(10, 4))
        lb = tk.Listbox(w, bg=TREE_BG, fg=FG, selectbackground=SEL, selectforeground=SEL_FG, relief='flat', font=('Segoe UI', 9), activestyle='none')
        lb.pack(fill='both', expand=True, padx=12)
        for s in sessions:
            lb.insert('end', tweaks.session_summary(s))
        if not sessions:
            lb.insert('end', 'Henüz kayıtlı değişiklik yok.')
        bar = tk.Frame(w, bg=PANEL); bar.pack(fill='x', padx=12, pady=8)

        def undo():
            i = lb.curselection()
            if not i or not sessions:
                return
            s = sessions[i[0]]
            if s.get('undone'):
                if not messagebox.askyesno('Geri al', 'Bu oturum zaten geri alınmış. Yine de önceki değerlere dönülsün mü?', parent=w):
                    return
            w.destroy()
            self._tw_undo_session(s)
        self.btn(bar, 'Seçili oturumu geri al', undo, 'danger', action=False)
        self.btn(bar, 'Kapat', w.destroy, 'ghost', action=False)

    def tw_export(self):
        ids = [p['id'] for p in self.tw_tree.checked_payloads() if p] or sorted(self.tw_sel)
        if not ids:
            messagebox.showinfo('Profil', 'Dışa aktarmak için önce ayar işaretleyin.'); return
        path = filedialog.asksaveasfilename(title='Profili kaydet', defaultextension='.json', filetypes=[('JSON', '*.json')],
                                            initialfile='agfo-ince-ayar-profili.json')
        if not path:
            return
        pathlib.Path(path).write_text(json.dumps(tweaks.export_profile(ids), ensure_ascii=False, indent=1), encoding='utf-8')
        self.write('Profil kaydedildi (%d ayar): %s\n' % (len(ids), path))

    def tw_import(self):
        path = filedialog.askopenfilename(title='Profil aç', filetypes=[('JSON', '*.json'), ('Tüm dosyalar', '*.*')])
        if not path:
            return
        try:
            ids, unknown = tweaks.import_profile(json.loads(pathlib.Path(path).read_text(encoding='utf-8-sig')))
        except Exception as e:
            messagebox.showerror('Profil', 'Profil okunamadı: %s' % e); return
        known = {it['id'] for it in self._tw_visible_items()}
        self.tw_sel = set(ids) & known
        self.tw_tree.clear()
        self._tw_render()
        self.write('Profil yüklendi: %d ayar işaretlendi%s. Uygulamak için "Seçilenleri uygula".\n'
                   % (len(self.tw_sel), (', %d tanınmayan/desteklenmeyen kayıt atlandı' % (len(unknown) + len(set(ids) - known))) if (unknown or set(ids) - known) else ''))

    # DNS
    def dns_list(self, then=None):
        def done(job):
            self.dns_adapters = [d for d in job.data if d.get('type') == 'dns-adapter']
            if not self.dns_adapters:
                self.dns_state.set('Bağlı fiziksel bağdaştırıcı yok.')
            else:
                self.dns_state.set('  |  '.join('%s: %s' % (a['alias'], ', '.join(a.get('servers') or []) or 'DHCP (%s)' % ', '.join(a.get('current') or []))
                                                for a in self.dns_adapters))
            if then:
                then()
        self.start([Job('DNS bağdaştırıcıları', cmd=ps_cmd('dns-list'), on_done=done, cancel_ok=False)])

    def dns_apply(self):
        choice = self.dns_choice.get()
        preset = next((p for p in tweaks.DNS_PRESETS if p[1] == choice), None)
        if preset:
            servers = preset[2]
        else:
            servers = tweaks.valid_ipv4_list(self.dns_custom.get())
            if not servers:
                messagebox.showerror('DNS', 'Özel adresleri yan kutuya IPv4 olarak yazın (ör. 1.1.1.1, 8.8.8.8; en fazla 4).'); return
        if not self.admin:
            if messagebox.askyesno('Yönetici gerekli', 'DNS değiştirmek yönetici ister. Uygulama yönetici olarak yeniden açılsın mı?'):
                self.elevate()
            return

        def go():
            if not self.dns_adapters:
                messagebox.showinfo('DNS', 'Bağlı fiziksel ağ bağdaştırıcısı bulunamadı.'); return
            names = ', '.join(a['alias'] for a in self.dns_adapters)
            if not messagebox.askyesno('DNS', '%s bağdaştırıcılarında DNS "%s" yapılacak. Önceki ayar kaydedilir ve Geçmiş\'ten geri alınabilir. Devam?' % (names, choice if preset else ', '.join(servers))):
                return
            plan = tweaks.dns_plan(self.dns_adapters, servers)
            self._tw_run(plan, 'DNS: ' + (choice if preset else ', '.join(servers)))
        self.dns_list(then=go)

    def dns_flush(self):
        self.start([Job('DNS önbelleğini temizle', cmd=ps_cmd('dns-flush'), cancel_ok=False)])

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
        self.sdio_toggle = self.mkbtn(top, 'Seçenekler ▸', self._sdio_toggle, 'ghost', small=True)
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
        tx = tk.Text(win, bg=LOG_BG, fg=LOG_FG, font=('Consolas', 9), wrap='none')
        tx.pack(fill='both', expand=True)
        tx.insert('1.0', text[:2000000]); tx.configure(state='disabled')

    # ------------------------------------------------------------------ UYGULAMA GUNCELLEMELERI (WinGet)
    def _tab_apps(self, f):
        self.label(f, 'WinGet resmî deposundaki güncellemeler bu listede gösterilir; yalnızca işaretledikleriniz sırayla güncellenir. Sessiz güncelleme '
                      'başarısız olursa uygulamanın kendi kurulum penceresiyle bir kez daha denenir; yeni sürümü farklı kurulum türüyle gelenler için '
                      '"kaldırıp yeniden kur" önerilir. Güncellenecek uygulamaları kapatmanız önerilir.',
                   wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(12, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Güncellemeleri tara', self.apps_scan, 'ghost')
        self.btn(bar, 'Tümünü seç', lambda: self.app_tree.set_all(True), 'ghost', action=False)
        self.btn(bar, 'Seçimi kaldır', lambda: self.app_tree.set_all(False), 'ghost', action=False)
        self.btn(bar, 'Seçilenleri güncelle', self.apps_update, 'danger')
        self.apps_reinstall_btn = self.btn(bar, 'Kaldırıp yeniden kur', self.apps_reinstall, 'ghost')
        self.app_count = tk.StringVar(value='')
        tk.Label(bar, textvariable=self.app_count, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(side='right')
        cols = [('id', 'Paket kimliği', 240, 'w'), ('ver', 'Kurulu', 110, 'w'), ('avail', 'Yeni', 110, 'w'), ('state', 'Durum', 150, 'w'),
                ('why', 'Ayrıntı', 420, 'w')]
        self.app_tree = CheckTree(f, cols, first=('Uygulama', 300), on_change=lambda: self.app_count.set('%d seçili' % len(self.app_tree.checked)))
        self.app_tree.pack(fill='both', expand=True, padx=16, pady=8)
        self.app_reinstall = {}

    def apps_scan(self):
        wg = self.engines.get('winget', {}).get('path') or core.find_winget()
        if not wg:
            messagebox.showerror('WinGet yok', 'WinGet bulunamadı.'); return
        cmd = [wg, 'upgrade', '--source', 'winget', '--accept-source-agreements', '--disable-interactivity']
        self.start([Job('WinGet güncelleme taraması', cmd=cmd, on_done=self._apps_loaded, show_output=False)])

    def _apps_loaded(self, job):
        rows = core.parse_winget_table(job.lines)
        t = self.app_tree; t.clear()
        self.app_reinstall = {}
        for i, r in enumerate(rows):
            t.add('a%d' % i, r['name'], (r['id'], r.get('version', ''), r.get('available', ''), '', ''), checked=True, payload=r)
        t._changed()
        self.write('WinGet: %d güncellenebilir uygulama.\n' % len(rows))
        if not rows:
            tail = [l for l in job.lines if l.strip()][-3:]
            if tail:
                self.write('\n'.join(tail) + '\n')

    def _app_row(self, pid):
        for iid, pl in self.app_tree.payload.items():
            if pl and pl.get('id') == pid:
                return iid
        return None

    def _app_set(self, pid, state, why=''):
        iid = self._app_row(pid)
        if iid and self.app_tree.tree.exists(iid):
            self.app_tree.tree.set(iid, 'state', state)
            self.app_tree.tree.set(iid, 'why', why)
            self.app_tree.tree.item(iid, tags=(('st_new',) if state in ('Güncellendi', 'Zaten güncel olabilir') else ('st_warn',) if state != 'Başarısız' else ('orphan',)))

    def apps_update(self):
        wg = self.engines.get('winget', {}).get('path') or core.find_winget()
        sel = [p for p in self.app_tree.checked_payloads() if p]
        if not wg or not sel:
            messagebox.showinfo('Güncelleme', 'Önce tarayın ve güncellenecek uygulamaları işaretleyin.'); return
        if not messagebox.askyesno('Güncellemeyi onaylayın', '%d uygulama sırayla güncellenecek. Açık olan uygulamaları kapatmanız önerilir; '
                                   'sessiz güncelleme olmazsa uygulamanın kendi kurulum penceresi açılabilir. Devam?' % len(sel)):
            return
        jobs = []
        for r in sel:
            def work(runner, job, r=r):
                code, lines = runner.run_cmd('WinGet (sessiz): ' + r['name'], core.winget_upgrade_cmd(wg, r['id']))
                step = core.upgrade_next_step(code, lines, False)
                if step == 'interactive' and not runner.stop.is_set():
                    runner.say('[%s] Sessiz güncelleme olmadı (%s); kurulum penceresiyle tekrar deneniyor...' % (r['name'], core.winget_failure_reason(code, lines)))
                    code, lines = runner.run_cmd('WinGet (pencereli): ' + r['name'], core.winget_upgrade_cmd(wg, r['id'], interactive=True))
                    step = core.upgrade_next_step(code, lines, True)
                job.data = [(step, core.winget_failure_reason(code, lines))]
                return 0 if step in ('ok', 'uptodate') else (code or 1)

            def done(job, r=r):
                step, why = job.data[0] if job.data else ('fail', hint(job.code))
                state = {'ok': 'Güncellendi', 'uptodate': 'Zaten güncel olabilir', 'running': 'Uygulama açık', 'reinstall': 'Yeniden kurulmalı'}.get(step, 'Başarısız')
                self._app_set(r['id'], state, '' if step == 'ok' else why)
                if step == 'reinstall':
                    self.app_reinstall[r['id']] = r
                if step == 'running':
                    self.write('[%s] Uygulama açık olduğu için güncellenemedi; kapatıp tekrar deneyin.\n' % r['name'])
            jobs.append(Job('Güncelle: ' + r['name'], func=work, on_done=done, cancel_ok=True))

        def summary(job):
            if self.app_reinstall:
                names = ', '.join(v['name'] for v in self.app_reinstall.values())
                self.write('Kaldırıp yeniden kurulması gerekenler: %s — "Kaldırıp yeniden kur" düğmesini kullanabilirsiniz.\n' % names)
        jobs.append(Job('Güncelleme özeti', func=lambda runner, job: 0, on_done=summary, cancel_ok=False, show_output=False))
        self.start(jobs)

    def apps_reinstall(self):
        wg = self.engines.get('winget', {}).get('path') or core.find_winget()
        sel = [p for p in self.app_tree.checked_payloads() if p and p['id'] in self.app_reinstall] or list(self.app_reinstall.values())
        if not wg or not sel:
            messagebox.showinfo('Kaldırıp yeniden kur', 'Bu işlem yalnızca güncellemede "Yeniden kurulmalı" diye işaretlenen uygulamalar içindir.'); return
        if not messagebox.askyesno('Kaldırıp yeniden kur', 'Şu uygulamalar kaldırılıp en yeni sürümleri kurulacak:\n  %s\n\n'
                                   'Çoğu uygulama ayarlarını korur, ancak bazıları ayarlarını sıfırlayabilir. Devam?' % '\n  '.join(p['name'] for p in sel)):
            return
        jobs = []
        for r in sel:
            def work(runner, job, r=r):
                code, lines = runner.run_cmd('Kaldır (sessiz): ' + r['name'], core.winget_uninstall_cmd(wg, r['id']))
                if code != 0 and not runner.stop.is_set():
                    runner.say('[%s] Sessiz kaldırma olmadı (%s); kaldırıcının kendi penceresiyle deneniyor...' % (r['name'], core.winget_failure_reason(code, lines)))
                    code, lines = runner.run_cmd('Kaldır (pencereli): ' + r['name'], core.winget_uninstall_cmd(wg, r['id'], interactive=True))
                if code == 0:
                    code, lines = runner.run_cmd('Kur: ' + r['name'], core.winget_install_cmd(wg, r['id']))
                    job.data = [('ok' if code == 0 else 'fail', '' if code == 0 else 'kurulamadı: ' + core.winget_failure_reason(code, lines))]
                    return code
                why_un = core.winget_failure_reason(code, lines)
                runner.say('[%s] Eski sürüm kaldırılamadı (%s); en yeni sürüm üzerine kurulmaya çalışılıyor...' % (r['name'], why_un))
                code, lines = runner.run_cmd('Üzerine kur: ' + r['name'], core.winget_force_install_cmd(wg, r['id']))
                if code == 0:
                    job.data = [('ok', 'eski sürüm kaldırılamadı, yeni sürüm üzerine kuruldu; Programlar\'da iki kayıt görünürse eskisini oradan kaldırın')]
                    return 0
                adm = '' if self.admin else ' — uygulamayı "Yönetici olarak yeniden aç" ile açıp tekrar deneyin'
                job.data = [('fail', 'kaldırılamadı (%s), üzerine de kurulamadı (%s)%s' % (why_un, core.winget_failure_reason(code, lines), adm))]
                return code or 1

            def done(job, r=r):
                step, why = job.data[0] if job.data else ('fail', hint(job.code))
                self._app_set(r['id'], 'Güncellendi' if step == 'ok' else 'Başarısız', why)
                if step == 'ok':
                    self.app_reinstall.pop(r['id'], None)
            jobs.append(Job('Yeniden kur: ' + r['name'], func=work, on_done=done, cancel_ok=False))
        self.start(jobs)

    # ------------------------------------------------------------------ UYGULAMA KUR (WinGet katalogu; liste ve buyuk simge gorunumu)
    INST_FILTERS = ['Tümü', 'Kurulu olmayanlar', 'Kurulu olanlar']
    TILE_W, TILE_H = 168, 120

    def _tab_install(self, f):
        self.label(f, 'Sık kullanılan uygulamalar WinGet resmî deposundan sessiz kurulur veya kaldırılır. "Kurulu olanları denetle" bu bilgisayardaki durumu işler. '
                      'Logolar uygulamaların kendi sitelerinden bir kez indirilir ve bu bilgisayarda saklanır.', wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(12, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Kurulu olanları denetle', self.inst_scan, 'ghost')
        self.btn(bar, 'Seçimi kaldır', self.inst_clear, 'ghost', action=False)
        self.btn(bar, 'Seçilenleri kur', lambda: self.inst_run('install'), 'go')
        self.btn(bar, 'Seçilenleri kaldır', lambda: self.inst_run('uninstall'), 'danger')
        self.inst_count = tk.StringVar(value='')
        tk.Label(bar, textvariable=self.inst_count, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(side='right')
        flt = tk.Frame(f, bg=PANEL); flt.pack(fill='x', padx=16, pady=(6, 0))
        tk.Label(flt, text='Göster:', fg=FG, bg=PANEL).pack(side='left')
        self.inst_filter = ttk.Combobox(flt, state='readonly', width=20, values=self.INST_FILTERS); self.inst_filter.current(0)
        self.inst_filter.pack(side='left', padx=6)
        self.inst_filter.bind('<<ComboboxSelected>>', lambda _e: self._inst_refresh())
        tk.Label(flt, text='Ara:', fg=FG, bg=PANEL).pack(side='left', padx=(10, 0))
        self.inst_q = tk.StringVar()
        ttk.Entry(flt, textvariable=self.inst_q, width=26).pack(side='left', padx=6)
        self.inst_q.trace_add('write', lambda *_: self._inst_refresh())
        self.inst_view = tk.StringVar(value=self.settings.get('install_view', 'grid'))
        for val, txt in (('list', 'Liste'), ('grid', 'Büyük simgeler')):
            ttk.Radiobutton(flt, text=txt, value=val, variable=self.inst_view, command=self._inst_switch_view).pack(side='right', padx=(8, 0))
        tk.Label(flt, text='Görünüm:', fg=FG, bg=PANEL).pack(side='right', padx=(10, 0))
        self.inst_holder = tk.Frame(f, bg=PANEL)
        self.inst_holder.pack(fill='both', expand=True, padx=16, pady=8)
        cols = [('id', 'WinGet kimliği', 260, 'w'), ('state', 'Durum', 150, 'w'), ('desc', 'Açıklama', 460, 'w')]
        self.inst_tree = CheckTree(self.inst_holder, cols, first=('Uygulama', 300), on_change=self._inst_count_update)
        # buyuk simge gorunumu: kaydirilabilir tuval icinde kutucuklar
        self.inst_gridf = tk.Frame(self.inst_holder, bg=PANEL)
        self.inst_canvas = tk.Canvas(self.inst_gridf, bg=PANEL, highlightthickness=0, bd=0)
        gys = ttk.Scrollbar(self.inst_gridf, orient='vertical', command=self.inst_canvas.yview)
        self.inst_canvas.configure(yscrollcommand=gys.set)
        gys.pack(side='right', fill='y'); self.inst_canvas.pack(side='left', fill='both', expand=True)
        self.inst_inner = tk.Frame(self.inst_canvas, bg=PANEL)
        self.inst_canvas.create_window((0, 0), window=self.inst_inner, anchor='nw', tags=('inner',))
        self.inst_inner.bind('<Configure>', lambda _e: self.inst_canvas.configure(scrollregion=self.inst_canvas.bbox('all')))
        self.inst_canvas.bind('<Configure>', self._inst_canvas_resized)
        for w in (self.inst_canvas, self.inst_inner):
            w.bind('<MouseWheel>', self._inst_wheel)
            w.bind('<Button-4>', lambda _e: self.inst_canvas.yview_scroll(-3, 'units'))
            w.bind('<Button-5>', lambda _e: self.inst_canvas.yview_scroll(3, 'units'))
        self.inst_ids, self.inst_result, self.inst_sel, self.inst_scanned = set(), {}, set(), False
        self.inst_tiles, self.inst_cols = {}, 0
        self.inst_img_l, self.inst_img_s = {}, {}
        self.inst_icon_dir = icons.cache_dir(core.APP_DATA_DIR)
        self.inst_icon_q = queue.Queue()
        self.inst_icon_busy = False
        self.theme_hooks.append(self._inst_paint_all)
        self._inst_load_cached_icons()
        self._inst_switch_view(initial=True)
        self._inst_tab = f

    # --- secim ve sayim
    def _inst_on_tab(self, _e=None):
        # Logolar yalnizca sayfa buyuk simge gorunumunde acildiginda indirilir (acilista ag trafigi yok).
        try:
            if self.tabs.nametowidget(self.tabs.select()) is self._inst_tab and self.inst_view.get() == 'grid':
                self.inst_fetch_icons()
        except Exception:
            pass

    def _inst_count_update(self):
        n = len(self._inst_selected_ids())
        self.inst_count.set('%d seçili' % n if n else '')

    def _inst_sync_from_tree(self):
        t = self.inst_tree
        if t.labels:
            visible = {pl['id'] for pl in t.payload.values() if pl}
            checked = {pl['id'] for pl in t.checked_payloads() if pl}
            self.inst_sel = checked | (self.inst_sel - visible)

    def _inst_selected_ids(self):
        if self.inst_view.get() == 'list':
            self._inst_sync_from_tree()
        return set(self.inst_sel)

    def inst_clear(self):
        self.inst_sel = set()
        self.inst_tree.set_all(False)
        self._inst_paint_all()
        self._inst_count_update()

    def _inst_visible_apps(self):
        mode, q = self.inst_filter.get(), self.inst_q.get().strip().lower()
        out = []
        for catname, apps in tweaks.install_groups().items():
            rows = []
            for a in apps:
                inst = self.inst_scanned and tweaks.is_installed(a['id'], self.inst_ids)
                if mode == 'Kurulu olmayanlar' and inst:
                    continue
                if mode == 'Kurulu olanlar' and not inst:
                    continue
                if q and q not in (a['name'] + ' ' + a['id'] + ' ' + a['desc']).lower():
                    continue
                rows.append((a, inst))
            if rows:
                out.append((catname, rows))
        return out

    def _inst_state(self, a):
        if a['id'] in self.inst_result:
            return self.inst_result[a['id']]
        if not self.inst_scanned:
            return ''
        return 'Kurulu' if tweaks.is_installed(a['id'], self.inst_ids) else 'Kurulu değil'

    def _inst_switch_view(self, initial=False):
        view = self.inst_view.get()
        if not initial:
            if view == 'grid':
                self._inst_sync_from_tree()
            self.settings['install_view'] = view
            core.save_settings(self.settings)
        if view == 'grid':
            self.inst_tree.pack_forget()
            self.inst_gridf.pack(fill='both', expand=True)
            if not initial:
                self.inst_fetch_icons()
        else:
            self.inst_gridf.pack_forget()
            self.inst_tree.pack(fill='both', expand=True)
        self._inst_refresh()

    def _inst_refresh(self):
        if self.inst_view.get() == 'grid':
            self._inst_render_grid()
        else:
            self._inst_render()
        self._inst_count_update()

    # --- liste gorunumu
    def _inst_render(self):
        t = self.inst_tree
        self._inst_sync_from_tree()
        t.clear()
        mode, q = self.inst_filter.get(), self.inst_q.get().strip()
        for n, (catname, rows) in enumerate(self._inst_visible_apps()):
            gid = 'g%d' % n
            t.add(gid, '%s (%d)' % (catname, len(rows)), ('', '', ''), tags=('group',), open_=bool(q) or mode != 'Tümü')
            for a, inst in rows:
                iid = t.add('i:' + a['id'], a['name'], (a['id'], self._inst_state(a), a['desc']), parent=gid, checked=a['id'] in self.inst_sel,
                            tags=('st_new',) if inst else (), payload=a)
                img = self.inst_img_s.get(a['id'])
                if img is not None:
                    t.tree.item(iid, image=img)
        t.refresh_marks()

    # --- buyuk simge gorunumu
    def _inst_wheel(self, e):
        self.inst_canvas.yview_scroll(int(-e.delta / 120) * 3 if e.delta else 0, 'units')

    def _inst_canvas_resized(self, e):
        self.inst_canvas.itemconfigure('inner', width=e.width)
        cols = max(1, int(e.width // int((self.TILE_W + 10) * self.scale)))
        if cols != self.inst_cols and self.inst_view.get() == 'grid':
            self.inst_cols = cols
            self._inst_render_grid()

    def _inst_render_grid(self):
        for w in self.inst_inner.winfo_children():
            w.destroy()
        self.inst_tiles = {}
        cols = self.inst_cols or max(1, int(max(self.inst_canvas.winfo_width(), 900) // int((self.TILE_W + 10) * self.scale)))
        groups = self._inst_visible_apps()
        if not groups:
            tk.Label(self.inst_inner, text='Bu süzgeçle eşleşen uygulama yok.', fg=MUTED, bg=PANEL).pack(anchor='w', pady=10)
        for catname, rows in groups:
            tk.Label(self.inst_inner, text='%s  (%d)' % (catname, len(rows)), fg=ACCENT, bg=PANEL, font=('Segoe UI', 10, 'bold'),
                     anchor='w').pack(fill='x', pady=(10, 4))
            grid = tk.Frame(self.inst_inner, bg=PANEL)
            grid.pack(fill='x')
            for i, (a, inst) in enumerate(rows):
                self._inst_tile(grid, a, inst).grid(row=i // cols, column=i % cols, padx=(0, 10), pady=(0, 10), sticky='nw')
        self.inst_canvas.yview_moveto(0)

    def _inst_tile(self, parent, a, inst):
        w, h = int(self.TILE_W * self.scale), int(self.TILE_H * self.scale)
        tile = tk.Frame(parent, bg=PANEL2, width=w, height=h, cursor='hand2', highlightthickness=2, highlightbackground=PANEL2)
        tile.pack_propagate(False)
        img = self.inst_img_l.get(a['id'])
        if img is not None:
            icon = tk.Label(tile, image=img, bg=PANEL2, cursor='hand2')
        else:
            sz = int(48 * self.scale)
            icon = tk.Canvas(tile, width=sz, height=sz, bg=PANEL2, highlightthickness=0, cursor='hand2')
            col = icons.avatar_color(a['id'])
            r = int(10 * self.scale)
            for x0, y0, x1, y1, st in ((0, 0, 2 * r, 2 * r, 90), (sz - 2 * r, 0, sz, 2 * r, 0), (0, sz - 2 * r, 2 * r, sz, 180), (sz - 2 * r, sz - 2 * r, sz, sz, 270)):
                icon.create_arc(x0, y0, x1, y1, start=st, extent=90, fill=col, outline=col)
            icon.create_rectangle(r, 0, sz - r, sz, fill=col, outline=col)
            icon.create_rectangle(0, r, sz, sz - r, fill=col, outline=col)
            icon.create_text(sz // 2, sz // 2, text=icons.initials(a['name']), fill='#ffffff', font=('Segoe UI', 14, 'bold'))
        icon.pack(pady=(int(12 * self.scale), 4))
        name = tk.Label(tile, text=a['name'], bg=PANEL2, fg=FG, font=('Segoe UI', 9, 'bold'), wraplength=w - 16, justify='center', cursor='hand2')
        name.pack()
        state = self._inst_state(a)
        st = tk.Label(tile, text=('✓ ' + state) if inst else state, bg=PANEL2, fg=OK_C if inst else MUTED, font=('Segoe UI', 8), cursor='hand2')
        st.pack()
        mark = tk.Label(tile, text='', bg=PANEL2, fg=ACCENT, font=('Segoe UI', 11, 'bold'))
        mark.place(relx=1.0, x=-6, y=4, anchor='ne')
        for wd in (tile, icon, name, st, mark):
            wd.bind('<Button-1>', lambda _e, i=a['id']: self._inst_toggle(i))
            wd.bind('<MouseWheel>', self._inst_wheel)
            wd.bind('<Button-4>', lambda _e: self.inst_canvas.yview_scroll(-3, 'units'))
            wd.bind('<Button-5>', lambda _e: self.inst_canvas.yview_scroll(3, 'units'))
        tip = '%s\n%s\n%s' % (a['name'], a['id'], a['desc'])
        for wd in (tile, icon, name):
            wd.bind('<Enter>', lambda _e, t=tip: self.inst_count.set(t.split('\n')[2][:90]))
            wd.bind('<Leave>', lambda _e: self._inst_count_update())
        self.inst_tiles[a['id']] = {'tile': tile, 'widgets': (icon, name, st), 'mark': mark, 'state': st, 'inst': inst}
        self._inst_paint(a['id'])
        return tile

    def _inst_paint(self, aid):
        t = self.inst_tiles.get(aid)
        if not t:
            return
        sel = aid in self.inst_sel
        bg = NAV_SEL if sel else PANEL2
        try:
            t['tile'].configure(bg=bg, highlightbackground=ACCENT if sel else PANEL2)
            for wd in t['widgets']:
                wd.configure(bg=bg)
            t['mark'].configure(bg=bg, text='✔' if sel else '')
            t['state'].configure(fg=OK_C if t['inst'] else MUTED)
        except tk.TclError:
            pass

    def _inst_paint_all(self):
        for aid in list(self.inst_tiles):
            self._inst_paint(aid)
        try:
            self.inst_canvas.configure(bg=PANEL)
        except tk.TclError:
            pass

    def _inst_toggle(self, aid):
        (self.inst_sel.discard if aid in self.inst_sel else self.inst_sel.add)(aid)
        self._inst_paint(aid)
        self._inst_count_update()

    # --- logolar
    def _inst_photo(self, path, target):
        img = tk.PhotoImage(file=str(path))
        w = img.width()
        if w > target * 1.5:
            f = max(1, round(w / target))
            img = img.subsample(f, f)
        return img

    def _inst_load_cached_icons(self):
        for a in tweaks.cat.INSTALL_APPS:
            large, small = icons.paths(self.inst_icon_dir, a['id'])
            if large.exists() and a['id'] not in self.inst_img_l:
                try:
                    self.inst_img_l[a['id']] = self._inst_photo(large, int(48 * self.scale))
                    self.inst_img_s[a['id']] = self._inst_photo(small, int(18 * self.scale))
                except tk.TclError:
                    pass

    def inst_fetch_icons(self):
        if self.inst_icon_busy:
            return
        idx = icons.load_index(self.inst_icon_dir)
        todo = [a for a in tweaks.cat.INSTALL_APPS if icons.needs_fetch(a, self.inst_icon_dir, idx)]
        if not todo:
            return
        self.inst_icon_busy = True
        self.write('Uygulama logoları indiriliyor (%d uygulama, her biri kendi sitesinden; bir kez yapılır)...\n' % len(todo))
        cdir, q = self.inst_icon_dir, self.inst_icon_q

        def worker():
            import concurrent.futures
            ok = 0
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                futs = {ex.submit(icons.fetch_icon, a, cdir): a for a in todo}
                for fu in concurrent.futures.as_completed(futs):
                    a = futs[fu]
                    try:
                        good, info = fu.result()
                    except Exception as e:
                        good, info = False, str(e)
                    idx[a['id']] = {'ok': good, 't': time.time(), 'src': info[:200]}
                    ok += 1 if good else 0
                    q.put(('icon', a['id'], good))
            icons.save_index(cdir, idx)
            q.put(('done', ok, len(todo)))
        threading.Thread(target=worker, daemon=True).start()
        self.after(250, self._inst_icon_poll)

    def _inst_icon_poll(self):
        changed, finished = False, False
        try:
            while True:
                msg = self.inst_icon_q.get_nowait()
                if msg[0] == 'icon' and msg[2]:
                    changed = True
                elif msg[0] == 'done':
                    finished = True
                    self.inst_icon_busy = False
                    self.write('Logolar: %d / %d uygulama için bulundu; bulunamayanlar harf simgesiyle gösterilir.\n' % (msg[1], msg[2]))
        except queue.Empty:
            pass
        if changed:
            self._inst_load_cached_icons()
            self._inst_icons_dirty = True
        now = time.time()
        if getattr(self, '_inst_icons_dirty', False) and (finished or now - getattr(self, '_inst_icons_drawn', 0) > 2.5):
            self._inst_icons_dirty = False
            self._inst_icons_drawn = now
            y = self.inst_canvas.yview()[0] if self.inst_view.get() == 'grid' else 0
            self._inst_refresh()
            if self.inst_view.get() == 'grid':
                self.inst_canvas.yview_moveto(y)
        if not finished:
            self.after(400, self._inst_icon_poll)

    # --- WinGet
    def inst_scan(self):
        wg = self.engines.get('winget', {}).get('path') or core.find_winget()
        if not wg:
            messagebox.showerror('WinGet yok', 'WinGet bulunamadı (Microsoft Store > Uygulama Yükleyici).'); return

        def done(job):
            rows = core.parse_winget_table(job.lines)
            self.inst_ids = tweaks.installed_ids(rows)
            self.inst_scanned = True
            self.inst_result = {}
            n = sum(1 for a in tweaks.cat.INSTALL_APPS if tweaks.is_installed(a['id'], self.inst_ids))
            self.write('WinGet: katalogdaki %d uygulamadan %d tanesi kurulu.\n' % (len(tweaks.cat.INSTALL_APPS), n))
            self._inst_refresh()
        self.start([Job('WinGet kurulu uygulamalar', cmd=[wg, 'list', '--source', 'winget', '--accept-source-agreements', '--disable-interactivity'],
                        on_done=done, show_output=False)])

    def inst_run(self, op):
        wg = self.engines.get('winget', {}).get('path') or core.find_winget()
        ids = self._inst_selected_ids()
        sel = [a for a in tweaks.cat.INSTALL_APPS if a['id'] in ids]
        if not wg:
            messagebox.showerror('WinGet yok', 'WinGet bulunamadı.'); return
        if not sel:
            messagebox.showinfo('Uygulama kur', 'Önce uygulama seçin (listede işaretleyin ya da kutucuğa tıklayın).'); return
        verb = 'kurulacak' if op == 'install' else 'kaldırılacak'
        if not messagebox.askyesno('Onaylayın', '%d uygulama sırayla %s:\n  %s%s\n\nDevam?' % (len(sel), verb, '\n  '.join(a['name'] for a in sel[:15]), '\n  ...' if len(sel) > 15 else '')):
            return
        jobs = []
        for a in sel:
            def done(job, aid=a['id']):
                ok = job.code == 0 or (isinstance(job.code, int) and (job.code & 0xFFFFFFFF) in (0x8A15002B, 0x8A150061))
                self.inst_result[aid] = ('Kuruldu' if op == 'install' else 'Kaldırıldı') if ok else hint(job.code)
                iid = 'i:' + aid
                if self.inst_tree.tree.exists(iid):
                    self.inst_tree.tree.set(iid, 'state', self.inst_result[aid])
                t = self.inst_tiles.get(aid)
                if t:
                    try:
                        t['state'].configure(text=self.inst_result[aid])
                    except tk.TclError:
                        pass
            cmd = core.winget_install_cmd(wg, a['id']) if op == 'install' else core.winget_uninstall_cmd(wg, a['id'])
            jobs.append(Job(('Kur: ' if op == 'install' else 'Kaldır: ') + a['name'], cmd=cmd, on_done=done, cancel_ok=True))
        self.start(jobs)

    # ------------------------------------------------------------------ VPN (WireGuard; 3.11.0)
    def _tab_vpn(self, f):
        head = tk.Frame(f, bg=PANEL); head.pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(head, text='VPN — farklı ülke IP\'leri', fg=FG, bg=PANEL, font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.vpn_wg_state = tk.StringVar(value='')
        tk.Label(head, textvariable=self.vpn_wg_state, fg=MUTED, bg=PANEL, font=('Segoe UI', 9)).pack(side='left', padx=(12, 0))
        self.label(f, 'Açık kaynak WireGuard ile bağlanır (bilinen en hızlı VPN protokolü). Ülke başına bir WireGuard yapılandırma dosyası (.conf) ekleyin: '
                      'Proton VPN (hesap > İndirmeler > WireGuard yapılandırması; ücretsiz katmanda birkaç ülke, ücretli katmanda 100+ ülke), '
                      'Mullvad (hesap > WireGuard yapılandırması) ya da kendi sunucunuz. Yapılandırmalar WireGuard\'ın kendi şifreli klasöründe saklanır. '
                      'Hız için size yakın ve gecikmesi düşük sunucuyu seçin; "En hızlıya bağlan" seçili ülkedeki en düşük gecikmeli sunucuyu bulur. '
                      'Hesap istemeyen seçenek: "Ücretsiz sunucular (VPN Gate)" — Tsukuba Üniversitesi\'nin gönüllü sunucuları (OpenVPN; hız değişkendir).',
                   wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(2, 6))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Yapılandırma ekle…', self.vpn_import, 'ghost')
        self.btn(bar, 'Bağlan', self.vpn_connect, 'go')
        self.btn(bar, 'Bağlantıyı kes', self.vpn_disconnect, 'danger')
        self.btn(bar, 'Gecikmeyi ölç', self.vpn_ping_all, 'ghost', action=False)
        self.btn(bar, 'En hızlıya bağlan', self.vpn_fastest, 'normal')
        self.btn(bar, 'Seçileni sil', self.vpn_remove, 'ghost')
        self.vpn_install_btn = self.btn(bar, 'WireGuard\'ı kur', self.vpn_install_wg, 'normal')
        flt = tk.Frame(f, bg=PANEL); flt.pack(fill='x', padx=16, pady=(6, 0))
        tk.Label(flt, text='Ülke:', fg=FG, bg=PANEL).pack(side='left')
        self.vpn_country = ttk.Combobox(flt, state='readonly', width=24, values=['Tümü'])
        self.vpn_country.set('Tümü'); self.vpn_country.pack(side='left', padx=6)
        self.vpn_country.bind('<<ComboboxSelected>>', lambda _e: self._vpn_refresh())
        self.btn(flt, 'Görünen IP\'yi denetle', self.vpn_check_ip, 'ghost', action=False)
        self.vpn_gate_btn = self.btn(flt, 'Sunucu listesini yenile', lambda: self.vpn_gate_fetch(force=True), 'ghost', action=False)
        self.vpn_src = tk.StringVar(value=self.settings.get('vpn_source', 'own'))
        for val, txt in (('gate', 'Ücretsiz (VPN Gate)'), ('own', 'WireGuard dosyalarım'), ('ts', 'Kendi çıkışlarım (Tailscale)')):
            ttk.Radiobutton(flt, text=txt, value=val, variable=self.vpn_src, command=self._vpn_switch_src).pack(side='right', padx=(8, 0))
        self.vpn_holder = tk.Frame(f, bg=PANEL); self.vpn_holder.pack(fill='both', expand=True, padx=16, pady=(8, 4))
        gf = ttk.Frame(self.vpn_holder, style='Card.TFrame')
        self.vpn_gate_frame = gf
        self.gate_tree = ttk.Treeview(gf, columns=('country', 'speed', 'ping', 'sessions', 'uptime', 'operator'), show='headings', selectmode='browse', height=8)
        for key, title, w in (('country', 'Ülke', 170), ('speed', 'Hız (Mbps)', 100), ('ping', 'Gecikme', 90), ('sessions', 'Oturum', 70),
                              ('uptime', 'Açık (gün)', 90), ('operator', 'Gönüllü işletmeci', 300)):
            self.gate_tree.heading(key, text=title); self.gate_tree.column(key, width=w, anchor='w')
        gys = ttk.Scrollbar(gf, orient='vertical', command=self.gate_tree.yview)
        self.gate_tree.configure(yscrollcommand=gys.set)
        self.gate_tree.pack(side='left', fill='both', expand=True); gys.pack(side='right', fill='y')
        self.gate_tree.bind('<Double-1>', lambda _e: self.vpn_connect())
        self.gate_tree.tag_configure('on', foreground=OK_C)
        self.vpn_gate, self.gate_ping, self.gate_proc, self.gate_active = [], {}, None, None
        self.gate_dir = core.APP_DATA_DIR / 'vpngate'
        # Tailscale cikis noktalari: yurt disinda Turk IP'si (Turkiye'deki bilgisayar) / Turkiye'de yabanci IP (Hetzner)
        tsf = tk.Frame(self.vpn_holder, bg=PANEL)
        self.vpn_ts_frame = tsf
        tsb = tk.Frame(tsf, bg=PANEL); tsb.pack(fill='x', pady=(0, 6))
        self.btn(tsb, 'Tailscale\'e giriş yap', self.ts_login, 'ghost', action=False)
        self.ts_adv_btn = self.btn(tsb, 'Bu bilgisayarı çıkış noktası yap', self.ts_toggle_advertise, 'ghost', action=False)
        self.btn(tsb, 'UGREEN ayarını kopyala (Türk IP)', self.ts_copy_ugreen, 'ghost', action=False)
        self.btn(tsb, 'Hetzner komutunu kopyala (yabancı IP)', self.ts_copy_script, 'ghost', action=False)
        self.btn(tsb, 'Yönetim panelini aç', lambda: self._open_url(vpn.TS_ADMIN_URL), 'ghost', action=False)
        self.ts_info = tk.StringVar(value='')
        tk.Label(tsf, textvariable=self.ts_info, fg=MUTED, bg=PANEL, font=('Segoe UI', 9), anchor='w', justify='left',
                 wraplength=int(1080 * self.scale)).pack(fill='x', pady=(0, 6))
        tst = ttk.Frame(tsf, style='Card.TFrame'); tst.pack(fill='both', expand=True)
        self.ts_tree = ttk.Treeview(tst, columns=('loc', 'os', 'ip', 'state'), show='tree headings', selectmode='browse', height=7)
        self.ts_tree.heading('#0', text='Çıkış noktası'); self.ts_tree.column('#0', width=240, stretch=True)
        for key, title, w in (('loc', 'Konum', 200), ('os', 'Sistem', 100), ('ip', 'Tailscale IP', 140), ('state', 'Durum', 160)):
            self.ts_tree.heading(key, text=title); self.ts_tree.column(key, width=w, anchor='w')
        tys = ttk.Scrollbar(tst, orient='vertical', command=self.ts_tree.yview)
        self.ts_tree.configure(yscrollcommand=tys.set)
        self.ts_tree.pack(side='left', fill='both', expand=True); tys.pack(side='right', fill='y')
        self.ts_tree.bind('<Double-1>', lambda _e: self.vpn_connect())
        self.ts_tree.tag_configure('on', foreground=OK_C); self.ts_tree.tag_configure('off', foreground=MUTED)
        self.ts_exe, self.ts_status, self.ts_ping = vpn.find_tailscale(), None, {}
        tf = ttk.Frame(self.vpn_holder, style='Card.TFrame')
        self.vpn_own_frame = tf
        self.vpn_tree = ttk.Treeview(tf, columns=('country', 'server', 'ping', 'state'), show='tree headings', selectmode='browse', height=8)
        self.vpn_tree.heading('#0', text='Tünel'); self.vpn_tree.column('#0', width=260, stretch=True)
        for key, title, w in (('country', 'Ülke', 170), ('server', 'Sunucu', 300), ('ping', 'Gecikme', 90), ('state', 'Durum', 130)):
            self.vpn_tree.heading(key, text=title); self.vpn_tree.column(key, width=w, anchor='w')
        ys = ttk.Scrollbar(tf, orient='vertical', command=self.vpn_tree.yview)
        self.vpn_tree.configure(yscrollcommand=ys.set)
        self.vpn_tree.pack(side='left', fill='both', expand=True); ys.pack(side='right', fill='y')
        self.vpn_tree.bind('<Double-1>', lambda _e: self.vpn_connect())
        self.vpn_own_frame.pack(fill='both', expand=True)
        self._vpn_tags(); self.theme_hooks.append(self._vpn_tags)
        self.vpn_status = tk.StringVar(value='Durum okunmadı.')
        tk.Label(f, textvariable=self.vpn_status, fg=ACCENT, bg=PANEL, font=('Segoe UI', 10, 'bold'), anchor='w', justify='left',
                 wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(4, 2))
        self.vpn_ip = tk.StringVar(value='Görünen IP: denetlenmedi')
        tk.Label(f, textvariable=self.vpn_ip, fg=MUTED, bg=PANEL, font=('Segoe UI', 9), anchor='w').pack(fill='x', padx=16, pady=(0, 10))
        self.vpn_meta_file = core.APP_DATA_DIR / 'vpn-tunnels.json'
        self.vpn_tunnels = self._vpn_load()
        self.vpn_running, self.vpn_ping, self.vpn_dump = {}, {}, {}
        self.vpn_wg = vpn.find_wireguard()
        self.vpn_q = queue.Queue()
        self._vpn_tab = f
        self._vpn_wg_label()
        self._vpn_render()
        if 'vpn_source' not in self.settings and not self.vpn_tunnels:
            self.vpn_src.set('ts')                             # varsayilan: kendi cikislariniz (UGREEN = Turk IP, Hetzner = yabanci IP)
        self._gate_restore()
        self._vpn_switch_src(initial=True)
        self.after(500, self._vpn_poll)

    def _vpn_tags(self):
        self.vpn_tree.tag_configure('on', foreground=OK_C)
        self.vpn_tree.tag_configure('off', foreground=FG)

    def _vpn_load(self):
        try:
            data = json.loads(self.vpn_meta_file.read_text(encoding='utf-8'))
            return [t for t in data if isinstance(t, dict) and vpn.NAME_RX.match(t.get('name', ''))]
        except Exception:
            return []

    def _vpn_save(self):
        try:
            self.vpn_meta_file.parent.mkdir(parents=True, exist_ok=True)
            self.vpn_meta_file.write_text(json.dumps(self.vpn_tunnels, ensure_ascii=False, indent=1), encoding='utf-8')
        except OSError:
            pass

    def _vpn_wg_label(self):
        self.vpn_wg = vpn.find_wireguard()
        self.vpn_wg_state.set('WireGuard: ' + ('kurulu' if self.vpn_wg else 'kurulu değil — "WireGuard\'ı kur" ile resmî istemciyi kurun'))
        try:
            if self.vpn_wg:
                self.vpn_install_btn.pack_forget()
        except tk.TclError:
            pass

    def _vpn_active(self):
        return next((n for n, st in self.vpn_running.items() if st == 'Running'), None)

    def _vpn_render(self):
        t = self.vpn_tree
        keep = t.selection()
        t.delete(*t.get_children())
        codes = sorted({x.get('country', '') for x in self.vpn_tunnels if x.get('country')}, key=lambda c: vpn.country_name(c))
        labels = ['Tümü'] + ['%s (%s)' % (vpn.country_name(c), c) for c in codes]
        own = self.vpn_src.get() == 'own'
        if own:
            self.vpn_country.configure(values=labels)
            if self.vpn_country.get() not in labels:
                self.vpn_country.set('Tümü')
        want = self.vpn_country.get() if own else 'Tümü'
        active = self._vpn_active()
        for x in sorted(self.vpn_tunnels, key=lambda x: (vpn.country_name(x.get('country', '')) or 'zz', self.vpn_ping.get(x['name'], 9999), x['name'])):
            c = x.get('country', '')
            if want != 'Tümü' and not want.endswith('(%s)' % c):
                continue
            p = self.vpn_ping.get(x['name'])
            on = x['name'] == active
            t.insert('', 'end', iid=x['name'], text=x['name'], tags=('on' if on else 'off',),
                     values=('%s %s' % (c, vpn.country_name(c)) if c else '—', x.get('endpoint', ''), ('%d ms' % p) if isinstance(p, int) else ('yanıt yok' if p == -1 else ''),
                             'Bağlı' if on else ('Kurulu (durdu)' if x['name'] in self.vpn_running else '')))
        sel = [i for i in keep if t.exists(i)]
        if sel:
            t.selection_set(sel)
        if active:
            meta = next((x for x in self.vpn_tunnels if x['name'] == active), {})
            d = self.vpn_dump.get(active) or {}
            extra = ''
            if d.get('handshake'):
                ago = max(0, int(time.time()) - d['handshake'])
                extra = ' · son el sıkışma %d sn önce · ↓ %s ↑ %s' % (ago, vpn.human_bytes(d['rx']), vpn.human_bytes(d['tx']))
            self.vpn_status.set('BAĞLI: %s%s%s' % (active, (' — ' + vpn.country_name(meta.get('country', ''))) if meta.get('country') else '', extra))
        elif self.gate_active:
            self._gate_status_line()
        elif self.vpn_src.get() == 'gate':
            self._gate_render()
        elif self.vpn_src.get() == 'ts':
            self._ts_render()
        else:
            hint_ = ' — eklenmiş tünel yok; "Yapılandırma ekle…" ile .conf ekleyin ya da "Ücretsiz sunucular (VPN Gate)"u seçin.' if not self.vpn_tunnels else '.'
            self.vpn_status.set('Bağlı değil' + hint_)

    def _vpn_selected(self):
        sel = self.vpn_tree.selection()
        return next((x for x in self.vpn_tunnels if sel and x['name'] == sel[0]), None)

    def _vpn_need(self, admin=True):
        if not self.vpn_wg:
            if messagebox.askyesno('WireGuard gerekli', 'Bu işlem resmî WireGuard istemcisini ister. Şimdi kurulsun mu?'):
                self.vpn_install_wg()
            return False
        if admin and not self.admin:
            if messagebox.askyesno('Yönetici gerekli', 'VPN tünelini kurmak/kaldırmak yönetici yetkisi ister. Uygulama yönetici olarak yeniden açılsın mı?'):
                self.elevate()
            return False
        return True

    def vpn_install_wg(self):
        wg = self.engines.get('winget', {}).get('path') or core.find_winget()
        if not wg:
            messagebox.showerror('WinGet yok', 'WinGet bulunamadı.'); return
        self.start([Job('Kur: WireGuard', cmd=core.winget_install_cmd(wg, vpn.WG_PKG), on_done=lambda j: self._vpn_wg_label(), cancel_ok=False)])

    def vpn_import(self):
        if not self._vpn_need():
            return
        paths = filedialog.askopenfilenames(title='WireGuard yapılandırmaları (.conf)', filetypes=[('WireGuard', '*.conf'), ('Tüm dosyalar', '*.*')])
        if not paths:
            return
        cdir = vpn.config_dir(self.vpn_wg)
        added, errors = [], []
        for p in paths:
            try:
                text = pathlib.Path(p).read_text(encoding='utf-8-sig')
                info = vpn.parse_conf(text)
                name = vpn.tunnel_name(p, [x['name'] for x in self.vpn_tunnels])
                cdir.mkdir(parents=True, exist_ok=True)
                (cdir / (name + '.conf')).write_text(text, encoding='utf-8')
                self.vpn_tunnels.append({'name': name, 'country': vpn.country_from_name(p), 'endpoint': info['endpoint'], 'host': info['host'],
                                         'full': info['full_tunnel'], 'added': time.strftime('%Y-%m-%d')})
                added.append(name)
            except Exception as e:
                errors.append('%s: %s' % (pathlib.Path(p).name, e))
        self._vpn_save()
        if added and self.vpn_src.get() != 'own':
            self.vpn_src.set('own')                            # eklenen yapilandirmalar gorunsun
            self._vpn_switch_src()
        self._vpn_render()
        self.write('VPN: %d yapılandırma eklendi%s.\n' % (len(added), (' ; hatalı: ' + ' | '.join(errors)) if errors else ''))
        nocountry = [x['name'] for x in self.vpn_tunnels if x['name'] in added and not x.get('country')]
        if nocountry:
            self.write('Ülkesi dosya adından anlaşılamayanlar: %s (dosya adına ülke kodu ekleyip yeniden ekleyebilirsiniz, ör. DE-sunucu.conf).\n' % ', '.join(nocountry))
        if added and any(not x.get('full', True) for x in self.vpn_tunnels if x['name'] in added):
            self.write('Not: bazı yapılandırmalar tüm trafiği değil yalnızca belirli adresleri tünelden geçiriyor (AllowedIPs); ülke değişimi için 0.0.0.0/0 olmalı.\n')

    def _vpn_switch_jobs(self, target):
        jobs = []
        if target and self._ts_current():
            jobs.append(Job('Tailscale çıkışını kapat', cmd=vpn.ts_clear_cmd(self.ts_exe), cancel_ok=False))
        active = self._vpn_active()
        for name, _st in list(self.vpn_running.items()):
            if name != target:
                jobs.append(Job('VPN kes: ' + name, cmd=vpn.uninstall_cmd(self.vpn_wg, name), cancel_ok=False))
        if target and target != active:
            path = vpn.stored_config(vpn.config_dir(self.vpn_wg), target)
            if not path:
                messagebox.showerror('VPN', 'Tünelin yapılandırması WireGuard klasöründe bulunamadı. Yeniden ekleyin.'); return None
            jobs.append(Job('VPN bağlan: ' + target, cmd=vpn.install_cmd(self.vpn_wg, path), cancel_ok=False))
        jobs.append(Job('VPN durumu', cmd=ps_cmd('vpn-status'), on_done=self._vpn_status_done, cancel_ok=False, show_output=False))
        return jobs

    def vpn_connect(self, target=None):
        if self.vpn_src.get() == 'gate' and target is None:
            return self.vpn_gate_connect()
        if self.vpn_src.get() == 'ts' and target is None:
            return self.ts_use()
        x = target or self._vpn_selected()
        if not x:
            messagebox.showinfo('VPN', 'Listeden bir tünel seçin.'); return
        if not self._vpn_need():
            return
        jobs = self._vpn_switch_jobs(x['name'])
        if jobs:
            jobs[-1].on_done = lambda j: (self._vpn_status_done(j), self.after(2500, self.vpn_check_ip))
            self.start(jobs)

    def vpn_disconnect(self):
        if self._ts_current():
            self.ts_clear()
            if not self.gate_running() and not self.vpn_running:
                return
        if self.gate_running():
            self.vpn_gate_stop()
            if not self.vpn_running:
                return
        if not self.vpn_running:
            self.write('VPN: kurulu tünel yok.\n'); return
        if not self._vpn_need():
            return
        jobs = self._vpn_switch_jobs(None)
        if jobs:
            jobs[-1].on_done = lambda j: (self._vpn_status_done(j), self.after(1500, self.vpn_check_ip))
            self.start(jobs)

    def vpn_remove(self):
        x = self._vpn_selected()
        if not x:
            messagebox.showinfo('VPN', 'Silinecek tüneli seçin.'); return
        if not messagebox.askyesno('Tüneli sil', '"%s" tüneli ve WireGuard\'daki yapılandırması silinsin mi?' % x['name']):
            return
        if not self._vpn_need():
            return

        def work(runner, job):
            if x['name'] in self.vpn_running:
                runner.run_cmd('VPN kes: ' + x['name'], vpn.uninstall_cmd(self.vpn_wg, x['name']))
            cdir = vpn.config_dir(self.vpn_wg)
            for ext in ('.conf', '.conf.dpapi'):
                try:
                    (cdir / (x['name'] + ext)).unlink()
                except OSError:
                    pass
            return 0

        def done(job):
            self.vpn_tunnels = [t for t in self.vpn_tunnels if t['name'] != x['name']]
            self._vpn_save()
            self.vpn_running.pop(x['name'], None)
            self._vpn_render()
        self.start([Job('VPN sil: ' + x['name'], func=work, on_done=done, cancel_ok=False)])

    def _vpn_status_done(self, job):
        self.vpn_running = {d['name']: d.get('status', '') for d in job.data if d.get('type') == 'vpn'}
        self.vpn_dump = {d['name']: vpn.parse_wg_dump(d.get('dump', '')) for d in job.data if d.get('type') == 'vpn'}
        self._vpn_render()

    # arka plan: durum (sayfa acikken 6 sn'de bir), gecikme ve IP denetimi kendi is parcaciginda; Runner'i mesgul etmez
    def _vpn_bg(self, kind, fn):
        def run():
            try:
                self.vpn_q.put((kind, fn()))
            except Exception as e:
                self.vpn_q.put((kind + '-err', str(e)))
        threading.Thread(target=run, daemon=True).start()

    def _vpn_status_bg(self):
        def fn():
            r = subprocess.run(ps_cmd('vpn-status'), capture_output=True, text=True, encoding='utf-8', errors='replace',
                               timeout=20, creationflags=CREATIONFLAGS)
            return [json.loads(l[2:]) for l in r.stdout.splitlines() if l.startswith('@@')]
        self._vpn_bg('status', fn)

    def _vpn_poll(self):
        try:
            while True:
                kind, val = self.vpn_q.get_nowait()
                if kind == 'status':
                    self.vpn_running = {d['name']: d.get('status', '') for d in val if d.get('type') == 'vpn'}
                    self.vpn_dump = {d['name']: vpn.parse_wg_dump(d.get('dump', '')) for d in val if d.get('type') == 'vpn'}
                    self._vpn_render()
                elif kind == 'gate-list':
                    self.vpn_gate = val
                    self.write('VPN Gate: %d ücretsiz sunucu listelendi.\n' % len(val))
                    self._vpn_refresh()
                elif kind == 'gate-list-err':
                    self.write('VPN Gate listesi alınamadı: %s\n' % val[:200])
                    self.vpn_status.set('VPN Gate listesi alınamadı (site erişilemiyor olabilir). "Sunucu listesini yenile" ile tekrar deneyin.')
                elif kind == 'ts-status':
                    self.ts_status = val
                    self._vpn_refresh() if self.vpn_src.get() == 'ts' else None
                elif kind == 'ts-status-err':
                    self.ts_status = {'state': 'NoState', 'error': val, 'nodes': [], 'current': None, 'self': '', 'self_ip': '', 'advertising': False}
                    if self.vpn_src.get() == 'ts':
                        self._ts_render()
                elif kind == 'ts-ping':
                    self.ts_ping.update(val)
                    self._ts_render()
                    cb = getattr(self, '_ts_after_ping', None)
                    self._ts_after_ping = None
                    if cb:
                        cb()
                elif kind == 'gate-ping':
                    self.gate_ping.update(val)
                    self._gate_render()
                    cb = getattr(self, '_gate_after_ping', None)
                    self._gate_after_ping = None
                    if cb:
                        cb()
                elif kind == 'ping':
                    self.vpn_ping.update(val)
                    self._vpn_render()
                    cb = getattr(self, '_vpn_after_ping', None)
                    self._vpn_after_ping = None
                    if cb:
                        cb()
                elif kind == 'ip':
                    ip, code, cname = val
                    self.vpn_ip.set('Görünen IP: %s — %s' % (ip, cname or code or 'ülke bilinmiyor'))
                elif kind == 'ip-err':
                    self.vpn_ip.set('Görünen IP denetlenemedi: %s' % val[:120])
        except queue.Empty:
            pass
        try:
            visible = self.tabs.nametowidget(self.tabs.select()) is self._vpn_tab
        except Exception:
            visible = False
        now = time.time()
        if visible and self.vpn_src.get() == 'ts' and self.ts_exe and now - getattr(self, '_ts_last', 0) > 5:
            self._ts_last = now
            self.ts_refresh()
        if self.gate_active and now - getattr(self, '_gate_last_log', 0) > 1.5:
            self._gate_last_log = now
            self._gate_check_log()
        if visible and IS_WIN and now - getattr(self, '_vpn_last_status', 0) > 6:
            self._vpn_last_status = now
            self._vpn_status_bg()
        self.after(700, self._vpn_poll)

    def vpn_ping_all(self, names=None, then=None):
        if self.vpn_src.get() == 'gate' and names is None:
            return self.vpn_gate_ping(self._gate_visible()[:40])
        if self.vpn_src.get() == 'ts' and names is None:
            return self.ts_ping_all()
        items = [x for x in self.vpn_tunnels if names is None or x['name'] in names]
        if not items:
            messagebox.showinfo('VPN', 'Önce yapılandırma ekleyin.'); return
        self.vpn_status.set('Gecikme ölçülüyor (%d sunucu)...' % len(items))
        self._vpn_after_ping = then

        def fn():
            import concurrent.futures

            def one(x):
                try:
                    r = subprocess.run(vpn.ping_cmd(x['host'], IS_WIN), capture_output=True, text=True, errors='replace', timeout=10,
                                       creationflags=CREATIONFLAGS)
                    ms = vpn.parse_ping_ms(r.stdout.splitlines())
                except Exception:
                    ms = None
                return x['name'], (ms if ms is not None else -1)
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                return dict(ex.map(one, items))
        self._vpn_bg('ping', fn)

    def vpn_fastest(self):
        if self.vpn_src.get() == 'gate':
            return self.vpn_gate_fastest()
        if self.vpn_src.get() == 'ts':
            return self.ts_fastest()
        want = self.vpn_country.get()
        names = [x['name'] for x in self.vpn_tunnels if want == 'Tümü' or want.endswith('(%s)' % x.get('country', ''))]
        if not names:
            messagebox.showinfo('VPN', 'Bu ülke için yapılandırma yok.'); return
        if not self._vpn_need():
            return

        def pick():
            ok = [(self.vpn_ping[n], n) for n in names if isinstance(self.vpn_ping.get(n), int) and self.vpn_ping[n] >= 0]
            if not ok:
                messagebox.showwarning('VPN', 'Sunucuların hiçbiri ping yanıtı vermedi; listeden elle seçip bağlanın.'); return
            best = min(ok)[1]
            self.write('VPN: en düşük gecikme %s (%d ms); bağlanılıyor.\n' % (best, min(ok)[0]))
            self.vpn_connect(next(x for x in self.vpn_tunnels if x['name'] == best))
        self.vpn_ping_all(names, then=pick)

    # --- Tailscale cikis noktalari
    def _ts_current(self):
        return (self.ts_status or {}).get('current')

    def _open_url(self, url):
        import webbrowser
        webbrowser.open(url)

    def ts_refresh(self):
        self.ts_exe = vpn.find_tailscale()
        if not self.ts_exe:
            self.ts_status = None
            self._ts_render()
            return
        exe = self.ts_exe

        def fn():
            r = subprocess.run([exe, 'status', '--json'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15,
                               creationflags=CREATIONFLAGS)
            if not r.stdout.strip().startswith('{'):
                raise RuntimeError((r.stderr or r.stdout).strip()[:200] or 'Tailscale yanıt vermedi')
            return vpn.parse_ts_status(r.stdout)
        self._vpn_bg('ts-status', fn)

    def _ts_render(self):
        t = self.ts_tree
        keep = t.selection()
        t.delete(*t.get_children())
        st = self.ts_status or {}
        if not self.ts_exe:
            self.ts_info.set('Tailscale kurulu değil. "Bağlan"a basınca kurulur. Kurulum sonrası "Tailscale\'e giriş yap" ile Google/Microsoft hesabınızla '
                             'giriş yapın (kişisel kullanım ücretsiz).')
        else:
            how = ('Yurt dışında Türk IP\'si: "UGREEN ayarını kopyala" ile aldığınız Docker projesini NAS\'ta oluşturun (çıkış adı ugreen-turkiye). '
                   'Türkiye\'de yabancı IP: "Hetzner komutunu kopyala" ile aldığınız komutu sunucuda (AGFO Root Terminal / SSH) çalıştırın (çıkış adı hetzner-cikis). '
                   'Her yeni çıkış noktasını bir kez "Yönetim panelini aç" > makine > Edit route settings > "Use as exit node" ile onaylayın.')
            oth = [o for o in (st.get('others') or []) if o['os'] in ('linux', '')]
            extra = ''
            if oth and not (st.get('nodes') or []):
                extra = (' Tailnet\'te çıkış noktası olmayan makineler: %s. Sunucuda "sudo tailscale set --advertise-exit-node" çalıştırıp '
                         'yönetim panelinde "Use as exit node" onaylayın.' % ', '.join(
                             '%s (%s)' % (o['name'], 'çevrimiçi' if o['online'] else 'çevrimdışı') for o in oth[:5]))
            self.ts_info.set('Bu bilgisayar: %s (%s) — Tailscale %s%s. %s%s' % (st.get('self') or '?', st.get('self_ip') or '-',
                             vpn.TS_STATE_NAME.get(st.get('state'), st.get('state') or 'okunmadı'),
                             ' · çıkış noktası olarak yayınlanıyor' if st.get('advertising') else '', how, extra))
            try:
                self.ts_adv_btn.configure(text='Bu bilgisayarın çıkış noktalığını kapat' if st.get('advertising') else 'Bu bilgisayarı çıkış noktası yap')
            except tk.TclError:
                pass
        nodes = st.get('nodes') or []
        codes = sorted({n['cc'] for n in nodes if n['cc']}, key=lambda c: vpn.country_name(c) or c)
        labels = ['Tümü'] + ['%s (%s)' % (vpn.country_name(c) or c, c) for c in codes]
        if self.vpn_src.get() == 'ts':
            self.vpn_country.configure(values=labels)
            if self.vpn_country.get() not in labels:
                self.vpn_country.set('Tümü')
        want = self.vpn_country.get()
        for n in nodes:
            if want != 'Tümü' and not want.endswith('(%s)' % n['cc']):
                continue
            loc = ', '.join(x for x in (n['city'], n['country']) if x) or (
                'Türkiye — UGREEN NAS (Türk IP)' if any(k in n['name'].lower() for k in ('ugreen', 'nas', 'dxp', 'dh2', 'dh4')) else
                'Yurt dışı — Hetzner (yabancı IP)' if 'hetzner' in n['name'].lower() else
                'kendi sunucunuz / NAS' if n['os'] == 'linux' else 'kendi cihazınız')
            p = self.ts_ping.get(n['ip'])
            state = 'ÇIKIŞ (kullanılıyor)' if n['active'] else ('çevrimiçi' if n['online'] else 'çevrimdışı')
            if isinstance(p, int) and p >= 0:
                state += ' · %d ms' % p
            t.insert('', 'end', iid=n['ip'] or n['id'], text=n['name'], values=(loc, n['os'], n['ip'], state),
                     tags=('on',) if n['active'] else (() if n['online'] else ('off',)))
        sel = [i for i in keep if t.exists(i)]
        if sel:
            t.selection_set(sel)
        cur = st.get('current')
        if cur:
            self.vpn_status.set('BAĞLI (Tailscale çıkışı): %s%s' % (cur['name'], (' — ' + ', '.join(x for x in (cur['city'], cur['country']) if x)) if cur['mullvad'] else ''))
        elif self.vpn_src.get() == 'ts' and not self._vpn_active() and not self.gate_active:
            if self.ts_exe and st.get('state') == 'Running':
                self.vpn_status.set('Çıkış noktası kullanılmıyor (normal internet).' + ('' if nodes else ' Henüz onaylı çıkış noktası yok — yukarıdaki adımlara bakın.'))
            elif self.ts_exe:
                self.vpn_status.set('Tailscale %s — "Tailscale\'e giriş yap"a basın.' % vpn.TS_STATE_NAME.get(st.get('state'), 'okunmadı'))
            else:
                self.vpn_status.set('Tailscale kurulu değil.')

    def _ts_need(self):
        self.ts_exe = vpn.find_tailscale()
        if not self.ts_exe:
            if messagebox.askyesno('Tailscale gerekli', 'Kendi çıkış noktalarınız için açık kaynak istemcili Tailscale kurulsun mu? (Kişisel kullanım ücretsiz.)'):
                wg = self.engines.get('winget', {}).get('path') or core.find_winget()
                if wg:
                    self.start([Job('Kur: Tailscale', cmd=core.winget_install_cmd(wg, vpn.TS_PKG), on_done=lambda j: self.ts_refresh(), cancel_ok=False)])
            return False
        return True

    def ts_login(self):
        if not self._ts_need():
            return
        self.write('Tailscale: tarayıcıda giriş sayfası açılacak; girişten sonra bu sayfa kendiliğinden güncellenir.\n')
        self.start([Job('Tailscale giriş', cmd=vpn.ts_up_cmd(self.ts_exe), on_done=lambda j: self.ts_refresh(), cancel_ok=True)])

    def _ts_selected(self):
        sel = self.ts_tree.selection()
        nodes = (self.ts_status or {}).get('nodes') or []
        return next((n for n in nodes if sel and (n['ip'] or n['id']) == sel[0]), None)

    def ts_use(self, node=None):
        if not self._ts_need():
            return
        n = node or self._ts_selected()
        if not n:
            messagebox.showinfo('Tailscale', 'Listeden bir çıkış noktası seçin.'); return
        if not n['online']:
            messagebox.showwarning('Tailscale', '%s şu an çevrimdışı; o bilgisayarın açık ve Tailscale\'in çalışıyor olması gerekir.' % n['name']); return
        jobs = []
        if self.gate_running():
            self.vpn_gate_stop(quiet=True)
        if self.vpn_running and self.vpn_wg:
            for name in list(self.vpn_running):
                jobs.append(Job('VPN kes: ' + name, cmd=vpn.uninstall_cmd(self.vpn_wg, name), cancel_ok=False))
            self.vpn_running = {}

        def done(job):
            if job.code == 0:
                self.write('Tailscale: çıkış noktası %s.\n' % n['name'])
            self.ts_refresh()
            self.after(2500, self.vpn_check_ip)
        jobs.append(Job('Tailscale çıkışı: ' + n['name'], cmd=vpn.ts_use_cmd(self.ts_exe, n['ip']), on_done=done, cancel_ok=False))
        self.start(jobs)

    def ts_clear(self):
        def done(job):
            self.ts_refresh()
            self.after(1500, self.vpn_check_ip)
        self.start([Job('Tailscale çıkışını kapat', cmd=vpn.ts_clear_cmd(self.ts_exe), on_done=done, cancel_ok=False)])

    def ts_toggle_advertise(self):
        if not self._ts_need():
            return
        on = not (self.ts_status or {}).get('advertising')
        if on and not messagebox.askyesno('Çıkış noktası', 'Bu bilgisayar Tailscale ağınızdaki diğer cihazlarınız için internet çıkışı olacak '
                                          '(onlar bu bilgisayarın IP\'siyle görünür). Bilgisayarın açık kalması gerekir. Devam?'):
            return

        def done(job):
            if job.code == 0 and on:
                self.write('Bu bilgisayar çıkış noktası olarak yayınlandı. Yönetim panelinde bir kez onaylayın (Edit route settings > Use as exit node).\n')
            self.ts_refresh()
        self.start([Job('Tailscale çıkış noktası ' + ('aç' if on else 'kapat'), cmd=vpn.ts_advertise_cmd(self.ts_exe, on), on_done=done, cancel_ok=False)])

    def ts_copy_script(self):
        self.clipboard_clear()
        self.clipboard_append(vpn.LINUX_EXIT_NODE_SCRIPT)
        if messagebox.askyesno('Hetzner — yabancı IP çıkışı', 'Komut panoya kopyalandı.\n\nKayıtlı bir SSH sunucusunda (Hetzner) System Care\'den '
                               'şimdi çalıştırılsın mı?\n\nHayır: komutu kendiniz (AGFO Root Terminal / SSH) çalıştırırsınız.'):
            if self.net.run_on_server(vpn.LINUX_EXIT_NODE_SCRIPT, 'Hetzner — çıkış noktası',
                                      'Bittikten sonra "Yönetim panelini aç" > sunucu > Edit route settings > "Use as exit node" işaretleyin.'):
                return
        self.write('Hetzner (Linux) sunucusu için komut panoya kopyalandı. Sunucuda root olarak çalıştırın; çıkan bağlantıyla giriş yapın, '
                   'sonra yönetim panelinde "hetzner-cikis" makinesini çıkış noktası olarak onaylayın.\n')
        messagebox.showinfo('Hetzner — yabancı IP çıkışı', '1) Hetzner sunucusunda root olarak (AGFO Root Terminal ya da SSH) panodaki komutu çalıştırın.\n'
                            '2) Tailscale sunucuda yeni kuruluyorsa ekranda çıkan login.tailscale.com bağlantısını açıp aynı hesapla giriş yapın '
                            '(zaten bağlıysa komut yalnızca çıkış noktalığını açar; ad ve DNS ayarı değişmez).\n'
                            '3) "Yönetim panelini aç" > sunucu (hetzner-cikis ya da mevcut adı) > Edit route settings > "Use as exit node" işaretleyin.\n\n'
                            'Komut:\n%s' % vpn.LINUX_EXIT_NODE_SCRIPT)

    def ts_copy_ugreen(self):
        if messagebox.askyesno('UGREEN NAS — Türk IP çıkışı', 'UGREEN NAS Tailscale yönetim panelinde zaten görünüyor mu?\n\n'
                               'Evet: mevcut kuruluma çıkış noktalığını açan tek satırlık SSH komutu kopyalanır.\n'
                               'Hayır: sıfırdan kurulum için Docker Compose ayarı kopyalanır.'):
            self.clipboard_clear()
            self.clipboard_append(vpn.NAS_EXIT_NODE_CMD)
            self.write('UGREEN NAS için SSH komutu panoya kopyalandı.\n')
            if messagebox.askyesno('UGREEN NAS — Türk IP çıkışı', 'Komut panoya kopyalandı.\n\nKayıtlı bir SSH sunucusu (NAS) üzerinde System Care\'den '
                                   'şimdi çalıştırılsın mı?\n\nHayır: komutu kendiniz çalıştırırsınız.'):
                self.net.run_on_server(vpn.NAS_EXIT_NODE_CMD, 'UGREEN NAS — çıkış noktası',
                                       'Önce UGOS > Denetim Masası > Terminal > SSH\'yi açın. Bağlandıktan sonra "TAMAM" yazısını görünce '
                                       '"Yönetim panelini aç" > NAS > Edit route settings > "Use as exit node" işaretleyin.')
                return
            messagebox.showinfo('UGREEN NAS — mevcut Tailscale',
                                '1) UGOS > Denetim Masası > Terminal > SSH\'yi açın.\n'
                                '2) Windows\'ta PowerShell: ssh <NAS kullanıcı adınız>@<NAS yerel IP\'si> ve parolanızla girin.\n'
                                '3) Panodaki komutu yapıştırın (sağ tık), Enter; sudo parola sorarsa aynı parolayı girin.\n'
                                '   "TAMAM" yazmalı. "TAILSCALE BULUNAMADI" yazarsa çıktıyı bize gönderin.\n'
                                '4) "Yönetim panelini aç" > NAS makinesi > Edit route settings > "Use as exit node" > Save.\n\n'
                                'Makinenin adı ve ayarları değişmez; NAS listede "çıkış noktası" olarak görünür.')
            return
        self.clipboard_clear()
        self.clipboard_append(vpn.UGREEN_COMPOSE)
        self.write('UGREEN NAS için Docker Compose ayarı panoya kopyalandı.\n')
        messagebox.showinfo('UGREEN NAS — Türk IP çıkışı',
                            '1) UGREEN NAS\'ta Docker uygulamasını açın > Proje > Oluştur.\n'
                            '2) Proje adı: tailscale-cikis; yol olarak paylaşılan bir klasör seçin (ör. /docker/tailscale).\n'
                            '3) Compose alanına panodaki ayarı yapıştırın ve projeyi başlatın.\n'
                            '4) Kapsayıcı (tailscale-cikis) > Günlük: çıkan login.tailscale.com bağlantısını açıp aynı Tailscale hesabıyla giriş yapın.\n'
                            '5) "Yönetim panelini aç" > ugreen-turkiye > Edit route settings > "Use as exit node" işaretleyin.\n\n'
                            'Sonra bu listede "ugreen-turkiye" görünür; yurt dışındayken seçip Bağlan\'a basın.')

    def ts_ping_all(self, nodes=None, then=None):
        nodes = [n for n in (nodes if nodes is not None else (self.ts_status or {}).get('nodes') or []) if n['online'] and n['ip']]
        if not nodes:
            messagebox.showinfo('Tailscale', 'Çevrimiçi çıkış noktası yok.'); return
        self._ts_after_ping = then

        def fn():
            import concurrent.futures

            def one(n):
                try:
                    r = subprocess.run(vpn.ping_cmd(n['ip'], IS_WIN), capture_output=True, text=True, errors='replace', timeout=10, creationflags=CREATIONFLAGS)
                    ms = vpn.parse_ping_ms(r.stdout.splitlines())
                except Exception:
                    ms = None
                return n['ip'], (ms if ms is not None else -1)
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                return dict(ex.map(one, nodes))
        self._vpn_bg('ts-ping', fn)

    def ts_fastest(self):
        want = self.vpn_country.get()
        nodes = [n for n in (self.ts_status or {}).get('nodes') or [] if n['online'] and (want == 'Tümü' or want.endswith('(%s)' % n['cc']))]
        if not nodes:
            messagebox.showinfo('Tailscale', 'Çevrimiçi çıkış noktası yok.'); return

        def pick():
            ok = [n for n in nodes if isinstance(self.ts_ping.get(n['ip']), int) and self.ts_ping[n['ip']] >= 0]
            best = min(ok, key=lambda n: self.ts_ping[n['ip']]) if ok else nodes[0]
            self.ts_use(best)
        self.ts_ping_all(nodes, then=pick)

    # --- VPN Gate (ucretsiz gonullu sunucular, OpenVPN)
    def _vpn_refresh(self):
        src = self.vpn_src.get()
        if src == 'gate':
            self._gate_render()
        elif src == 'ts':
            self._ts_render()
        else:
            self._vpn_render()

    def _vpn_switch_src(self, initial=False):
        gate = self.vpn_src.get() == 'gate'
        if not initial:
            self.settings['vpn_source'] = self.vpn_src.get()
            core.save_settings(self.settings)
        self.vpn_country.set('Tümü')
        src = self.vpn_src.get()
        frames = {'gate': self.vpn_gate_frame, 'own': self.vpn_own_frame, 'ts': self.vpn_ts_frame}
        for k, fr in frames.items():
            if k != src:
                fr.pack_forget()
        frames[src].pack(fill='both', expand=True)
        if gate and not self.vpn_gate:
            self.vpn_gate_fetch(force=False)
        if src == 'ts':
            self.ts_refresh()
        self._vpn_refresh()

    def gate_running(self):
        return self.gate_proc is not None and self.gate_proc.poll() is None or (self.gate_active is not None and self.gate_proc is None)

    def _gate_visible(self):
        want = self.vpn_country.get()
        return [g for g in self.vpn_gate if want == 'Tümü' or want.endswith('(%s)' % g['cc'])]

    def _gate_render(self):
        t = self.gate_tree
        keep = t.selection()
        t.delete(*t.get_children())
        codes = sorted({g['cc'] for g in self.vpn_gate if g['cc']}, key=lambda c: vpn.country_name(c) or c)
        labels = ['Tümü'] + ['%s (%s)' % (vpn.country_name(c) or c, c) for c in codes]
        self.vpn_country.configure(values=labels)
        if self.vpn_country.get() not in labels:
            self.vpn_country.set('Tümü')
        act = (self.gate_active or {}).get('ip')
        for g in self._gate_visible():
            p = self.gate_ping.get(g['ip'])
            ptxt = ('%d ms' % p) if isinstance(p, int) and p >= 0 else ('yanıt yok' if p == -1 else '')
            t.insert('', 'end', iid=g['ip'], tags=('on',) if g['ip'] == act else (),
                     values=('%s %s' % (g['cc'], g['country']), '%.1f' % g['mbps'], ptxt, g['sessions'], g['uptime_days'], g['operator']))
        sel = [i for i in keep if t.exists(i)]
        if sel:
            t.selection_set(sel)
        if self.gate_active:
            self._gate_status_line()
        elif self.vpn_src.get() == 'gate' and not self._vpn_active() and not self._ts_current():
            self.vpn_status.set('Bağlı değil — %d ücretsiz sunucu. Ülke seçip "En hızlıya bağlan"a basın.' % len(self._gate_visible()) if self.vpn_gate
                                else 'VPN Gate sunucu listesi alınıyor...')

    def _gate_status_line(self):
        a = self.gate_active or {}
        st = {'connected': 'BAĞLI', 'connecting': 'BAĞLANIYOR…', 'error': 'BAĞLANAMADI'}.get(a.get('state'), '')
        self.vpn_status.set('%s (VPN Gate): %s %s — %s · %.1f Mbps%s' % (st, a.get('cc', ''), a.get('country', ''), a.get('ip', ''), a.get('mbps', 0),
                            ' — başka bir sunucu deneyin' if a.get('state') == 'error' else ''))

    def vpn_gate_fetch(self, force=False):
        cache = self.gate_dir / 'list.csv'
        if not force and cache.exists() and time.time() - cache.stat().st_mtime < 3600:
            try:
                self.vpn_gate = vpn.parse_vpngate(cache.read_text(encoding='utf-8'))
                self._vpn_refresh()
                return
            except Exception:
                pass
        self.vpn_status.set('VPN Gate sunucu listesi alınıyor...')
        gdir = self.gate_dir

        def fn():
            import urllib.request
            req = urllib.request.Request(vpn.VPNGATE_URL, headers={'User-Agent': 'AGFO-System-Care'})
            with urllib.request.urlopen(req, timeout=25) as r:
                data = r.read(12 * 1024 * 1024).decode('utf-8', 'replace')
            servers = vpn.parse_vpngate(data)
            gdir.mkdir(parents=True, exist_ok=True)
            (gdir / 'list.csv').write_text(data, encoding='utf-8')
            return servers
        self._vpn_bg('gate-list', fn)

    def vpn_gate_ping(self, items, then=None):
        if not items:
            messagebox.showinfo('VPN Gate', 'Listede sunucu yok; "Sunucu listesini yenile"yi deneyin.'); return
        self.vpn_status.set('Gecikme ölçülüyor (%d sunucu)...' % len(items))
        self._gate_after_ping = then

        def fn():
            import concurrent.futures

            def one(g):
                try:
                    r = subprocess.run(vpn.ping_cmd(g['ip'], IS_WIN), capture_output=True, text=True, errors='replace', timeout=10, creationflags=CREATIONFLAGS)
                    ms = vpn.parse_ping_ms(r.stdout.splitlines())
                except Exception:
                    ms = None
                return g['ip'], (ms if ms is not None else -1)
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
                return dict(ex.map(one, items))
        self._vpn_bg('gate-ping', fn)

    def vpn_gate_fastest(self):
        cands = sorted(self._gate_visible(), key=lambda g: -g['mbps'])[:12]
        if not cands:
            messagebox.showinfo('VPN Gate', 'Bu ülke için ücretsiz sunucu yok.'); return

        def pick():
            ok = [g for g in cands if isinstance(self.gate_ping.get(g['ip']), int) and self.gate_ping[g['ip']] >= 0]
            pool = ok or cands
            best = max(pool, key=lambda g: g['mbps'] / (1 + (self.gate_ping.get(g['ip'], 300) if self.gate_ping.get(g['ip'], -1) >= 0 else 300) / 100.0))
            self.write('VPN Gate: %s %s seçildi (%.1f Mbps, %s).\n' % (best['cc'], best['ip'], best['mbps'],
                       ('%d ms' % self.gate_ping[best['ip']]) if best['ip'] in self.gate_ping and self.gate_ping[best['ip']] >= 0 else 'ping yanıtı yok'))
            self.vpn_gate_connect(best)
        self.vpn_gate_ping(cands, then=pick)

    def _gate_need(self):
        exe = vpn.find_openvpn()
        if not exe:
            if messagebox.askyesno('OpenVPN gerekli', 'Ücretsiz sunucular OpenVPN ile bağlanır. Resmî açık kaynak OpenVPN istemcisi kurulsun mu?'):
                wg = self.engines.get('winget', {}).get('path') or core.find_winget()
                if wg:
                    self.start([Job('Kur: OpenVPN', cmd=core.winget_install_cmd(wg, vpn.OVPN_PKG), cancel_ok=False)])
            return None
        if not self.admin:
            if messagebox.askyesno('Yönetici gerekli', 'VPN bağlantısı yönetici yetkisi ister. Uygulama yönetici olarak yeniden açılsın mı?'):
                self.elevate()
            return None
        return exe

    def vpn_gate_connect(self, g=None):
        if g is None:
            sel = self.gate_tree.selection()
            g = next((x for x in self.vpn_gate if sel and x['ip'] == sel[0]), None)
            if not g:
                messagebox.showinfo('VPN Gate', 'Listeden bir sunucu seçin (ya da "En hızlıya bağlan").'); return
        exe = self._gate_need()
        if not exe:
            return
        try:
            text, _remote = vpn.vpngate_ovpn(g['config'])
        except ValueError as e:
            messagebox.showerror('VPN Gate', 'Bu sunucunun yapılandırması kullanılamıyor: %s' % e); return
        self.vpn_gate_stop(quiet=True)
        if self._ts_current():
            subprocess.run(vpn.ts_clear_cmd(self.ts_exe), creationflags=CREATIONFLAGS, timeout=30, capture_output=True)
        if self.vpn_running and self.vpn_wg:                  # WireGuard tuneli aciksa once kapat (tek VPN)
            for name in list(self.vpn_running):
                subprocess.run(vpn.uninstall_cmd(self.vpn_wg, name), creationflags=CREATIONFLAGS, timeout=30)
            self.vpn_running = {}
        self.gate_dir.mkdir(parents=True, exist_ok=True)
        auth = self.gate_dir / 'auth.txt'
        auth.write_text('vpn\nvpn\n', encoding='ascii')       # VPN Gate'in herkese acik ortak kimligi
        cfg = self.gate_dir / 'current.ovpn'
        cfg.write_text(vpn.finalize_ovpn(text, auth), encoding='utf-8')
        log = self.gate_dir / 'openvpn.log'
        try:
            log.unlink()
        except OSError:
            pass
        try:
            self.gate_proc = subprocess.Popen(vpn.openvpn_cmd(exe, cfg, log), creationflags=CREATIONFLAGS, cwd=str(self.gate_dir),
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            messagebox.showerror('VPN Gate', 'OpenVPN başlatılamadı: %s' % e); return
        self.gate_active = dict({k: g[k] for k in ('ip', 'cc', 'country', 'mbps')}, state='connecting', pid=self.gate_proc.pid, t=time.time())
        self.settings['vpngate_active'] = self.gate_active
        core.save_settings(self.settings)
        self.write('VPN Gate: %s %s sunucusuna bağlanılıyor (OpenVPN)...\n' % (g['cc'], g['ip']))
        self._gate_render()

    def _gate_check_log(self):
        a = self.gate_active
        if not a:
            return
        try:
            text = (self.gate_dir / 'openvpn.log').read_text(encoding='utf-8', errors='replace')[-20000:]
        except OSError:
            text = ''
        st = vpn.openvpn_state(text)
        dead = self.gate_proc is not None and self.gate_proc.poll() is not None
        if dead and st != 'error':
            st = 'error'
        if st == 'connecting' and time.time() - a.get('t', 0) > 45:
            st = 'error'
        if st != a.get('state'):
            a['state'] = st
            if st == 'connected':
                self.write('VPN Gate: bağlandı (%s %s).\n' % (a['cc'], a['ip']))
                self.after(1500, self.vpn_check_ip)
            elif st == 'error':
                tail = [l for l in text.splitlines() if l.strip()][-3:]
                self.write('VPN Gate: bağlantı kurulamadı. %s\n' % (' | '.join(tail)[:300]))
                self.vpn_gate_stop(quiet=True, keep_state=True)
            self._vpn_refresh()

    def vpn_gate_stop(self, quiet=False, keep_state=False):
        pid = (self.gate_active or {}).get('pid')
        if self.gate_proc is not None and self.gate_proc.poll() is None:
            try:
                self.gate_proc.terminate()
                self.gate_proc.wait(timeout=8)
            except Exception:
                pass
        elif pid and IS_WIN:
            subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], creationflags=CREATIONFLAGS, capture_output=True, timeout=15)
        self.gate_proc = None
        if not keep_state:
            self.gate_active = None
        elif self.gate_active:
            self.gate_active['pid'] = None
        self.settings.pop('vpngate_active', None)
        core.save_settings(self.settings)
        if not quiet:
            self.write('VPN Gate bağlantısı kesildi.\n')
            self.after(1500, self.vpn_check_ip)
        self._vpn_refresh()

    def _gate_restore(self):
        """Onceki oturumdan kalan OpenVPN sureci (uygulama kapatilip acildiysa) hala calisiyorsa izlemeye devam et."""
        a = self.settings.get('vpngate_active')
        if not (a and a.get('pid') and IS_WIN):
            return
        try:
            out = subprocess.run(['tasklist', '/FI', 'PID eq %d' % int(a['pid']), '/NH'], capture_output=True, text=True, errors='replace',
                                 creationflags=CREATIONFLAGS, timeout=10).stdout
        except Exception:
            out = ''
        if 'openvpn' in out.lower():
            self.gate_active = dict(a, state='connecting', t=time.time() - 60)
        else:
            self.settings.pop('vpngate_active', None)
            core.save_settings(self.settings)

    def vpn_check_ip(self):
        self.vpn_ip.set('Görünen IP denetleniyor...')

        def fn():
            import urllib.request
            req = urllib.request.Request(vpn.IP_CHECK_URL, headers={'User-Agent': 'AGFO-System-Care', 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=8) as r:
                return vpn.parse_ipinfo(r.read(64 * 1024).decode('utf-8', 'replace'))
        self._vpn_bg('ip', fn)

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
        self.pad_diag = tk.Text(left, height=6, bg=TREE_BG, fg=FG, relief='flat', font=('Segoe UI', 9), wrap='word', padx=8, pady=6)
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
                self.pad_tab = self.tabs.index('Kol / Gamepad')
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
        self.upd_check = tk.Text(win, height=11, bg=LOG_BG, fg=LOG_FG, relief='flat', font=('Consolas', 9), padx=10, pady=8, wrap='word')
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
                self.gh_banner.pack(fill='x', padx=22, pady=(0, 8), before=self.main)
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

    def _net_colors(self):
        g = globals()
        return {k: g[k] for k in ('BG', 'PANEL', 'PANEL2', 'FG', 'MUTED', 'ACCENT', 'WARN', 'OK_C', 'BAD_C', 'SEL', 'SEL_FG', 'TREE_BG', 'LOG_BG', 'LOG_FG')}

    def on_close(self):
        try:
            self.net.close()
        except Exception:
            pass
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
