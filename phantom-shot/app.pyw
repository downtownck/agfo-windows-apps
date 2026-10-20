"""AGFO Phantom Shot 1.0.0 - tek tusla sessiz ekran goruntusu (Windows GUI).

Ayar penceresinden klasoru, tetik tusunu/fare tusunu ve bicimi secersiniz. "Baslat" dediginizde arka
planda dinler; secili tusa basildiginda ekran goruntusunu alir ve ekranda HICBIR pencere, bildirim ya
da ses gostermeden kaydeder. Pencereyi sistem tepsisine kucultebilirsiniz (pystray varsa).

Yakalama mss, tus/fare dinleme pynput ile yapilir (ilk acilista kurulmasi onerilir). GitHub'daki
downtownck/agfo-windows-apps deposundan uygulama kendini tek tikla gunceller (yedek + otomatik geri alma).

Gerekli:    pip install pynput mss
Istege bagli: pip install pillow pystray   (jpg + tepsi ikonu icin)
"""
import ctypes
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
import phantom_core as core  # noqa: E402
import agfo_github_update as ghu  # noqa: E402

VERSION = core.VERSION
BG, PANEL, PANEL2, FG, MUTED, ACCENT = '#0a1425', '#12243b', '#192e48', '#ecf3ff', '#a5b6ce', '#49b3ef'
WARN, OK_C, BAD_C = '#e2b356', '#6fd39b', '#ff8a80'
POLL_MS = 90

KEY_CHOICES = (['(yok)'] + ['f%d' % i for i in range(1, 13)]
               + ['print_screen', 'pause', 'scroll_lock', 'insert', 'home', 'end', 'page_up', 'page_down', 'menu']
               + list('abcdefghijklmnopqrstuvwxyz0123456789'))
MOUSE_CHOICES = ['(yok)', 'middle', 'x1', 'x2', 'right']


# =========================================================================== pynput / mss (tembel)
_PYNPUT = {}


def _pynput():
    """pynput.keyboard, pynput.mouse modullerini (keyboard, mouse) dondurur; yoksa (None, None)."""
    if 'kb' not in _PYNPUT:
        try:
            from pynput import keyboard, mouse
            _PYNPUT['kb'], _PYNPUT['ms'] = keyboard, mouse
        except Exception:
            _PYNPUT['kb'] = _PYNPUT['ms'] = None
    return _PYNPUT['kb'], _PYNPUT['ms']


def resolve_key(key_name):
    """config'teki tus adini pynput nesnesine cevirir. Donus: (obj, char) - ikisi de None olabilir."""
    keyboard, _ = _pynput()
    if keyboard is None or not key_name or key_name == '(yok)':
        return None, None
    name = str(key_name).strip().lower()
    special = {'print_screen': 'print_screen', 'pause': 'pause', 'scroll_lock': 'scroll_lock', 'insert': 'insert',
               'home': 'home', 'end': 'end', 'page_up': 'page_up', 'page_down': 'page_down', 'menu': 'menu', 'space': 'space'}
    for i in range(1, 25):
        special['f%d' % i] = 'f%d' % i
    if name in special:
        obj = getattr(keyboard.Key, special[name], None)
        if obj is not None:
            return obj, None
    if len(name) == 1:
        return None, name
    return None, None


def resolve_mouse_button(btn_name):
    _, mouse = _pynput()
    if mouse is None or not btn_name or btn_name == '(yok)':
        return None
    name = str(btn_name).strip().lower()
    mapping = {'left': 'left', 'right': 'right', 'middle': 'middle', 'x1': 'x1', 'x2': 'x2',
               'button8': 'button8', 'button9': 'button9'}
    attr = mapping.get(name)
    return getattr(mouse.Button, attr, None) if attr else None


class Capturer:
    """Tek bir ekran goruntusu alir; ekranda hicbir sey gostermez. mss (gerekli), Pillow (jpg icin) tembel yuklenir."""

    def __init__(self):
        self._lock = threading.Lock()
        self.count = 0
        self.last_path = ''

    def shoot(self, cfg, on_done=None):
        with self._lock:
            try:
                import mss
                import mss.tools
                save_dir = core.resolve_save_dir(cfg.get('save_dir'))
                os.makedirs(save_dir, exist_ok=True)
                fmt = (cfg.get('format') or 'png').lower()
                path = os.path.join(save_dir, core.screenshot_name(cfg.get('prefix', 'shot'), fmt))
                with mss.mss() as sct:
                    monitors = sct.monitors
                    idx = cfg.get('monitor', 0)
                    if not isinstance(idx, int) or idx < 0 or idx >= len(monitors):
                        idx = 0
                    shot = sct.grab(monitors[idx])
                    if fmt in ('jpg', 'jpeg'):
                        try:
                            from PIL import Image
                            img = Image.frombytes('RGB', shot.size, shot.bgra, 'raw', 'BGRX')
                            img.save(path, 'JPEG', quality=int(cfg.get('jpg_quality', 90)))
                        except ImportError:
                            path = path[:-len(fmt)] + 'png'
                            mss.tools.to_png(shot.rgb, shot.size, output=path)
                    else:
                        mss.tools.to_png(shot.rgb, shot.size, output=path)
                self.count += 1
                self.last_path = path
                if on_done:
                    on_done(path, self.count)
            except Exception as e:
                if on_done:
                    on_done(None, self.count, str(e))


# =========================================================================== ana pencere
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg = core.load_settings()
        self.cap = Capturer()
        self.kb_listener = None
        self.ms_listener = None
        self.running = False
        self.busy = False
        self.tray_icon = None
        self.install_dir = BASE
        self.backup_root = core.APP_DATA_DIR / 'update-backups'
        self.gh_result = None
        self.messages = queue.Queue()

        self.title('AGFO Phantom Shot ' + VERSION)
        self.scale = max(1.0, self.winfo_fpixels('1i') / 96.0)
        self.configure(bg=BG)
        self.resizable(False, False)
        self._set_icon()
        self._style()
        self._build()
        self._fill_from_cfg()
        self.protocol('WM_DELETE_WINDOW', self._on_close)
        self.after(POLL_MS, self._poll)
        if self.cfg.get('auto_update_check', True):
            self.after(2500, lambda: self.gh_check(force=False))
        if self.cfg.get('autostart'):
            self.after(400, self.start)

    # ---------------------------------------------------------------- stil / iskelet
    def _set_icon(self):
        ico = BASE / 'assets' / 'agfo-phantom.ico'
        if IS_WIN and ico.is_file():
            try:
                self.iconbitmap(default=str(ico))
            except Exception:
                pass

    def _style(self):
        s = ttk.Style(self)
        s.theme_use('clam')
        s.configure('.', background=PANEL, foreground=FG, fieldbackground=PANEL2, font=('Segoe UI', 10))
        s.configure('Card.TFrame', background=PANEL)
        s.configure('TCombobox', fieldbackground=PANEL2, background=PANEL2, foreground=FG, arrowcolor=FG)
        s.map('TCombobox', fieldbackground=[('readonly', PANEL2)], foreground=[('readonly', FG)],
              selectbackground=[('readonly', PANEL2)], selectforeground=[('readonly', FG)])
        self.option_add('*TCombobox*Listbox.background', PANEL2)
        self.option_add('*TCombobox*Listbox.foreground', FG)
        self.option_add('*TCombobox*Listbox.selectBackground', '#285475')
        s.configure('TSpinbox', fieldbackground=PANEL2, foreground=FG, arrowcolor=FG)
        s.configure('TEntry', fieldbackground=PANEL2, foreground=FG, insertcolor=FG)
        s.configure('TCheckbutton', background=PANEL, foreground=FG)
        s.map('TCheckbutton', background=[('active', PANEL)])
        s.configure('TRadiobutton', background=PANEL, foreground=FG)
        s.map('TRadiobutton', background=[('active', PANEL)])
        s.configure('Treeview', background='#0e1b2e', fieldbackground='#0e1b2e', foreground=FG, borderwidth=0)
        s.configure('Treeview.Heading', background=PANEL2, foreground=FG, font=('Segoe UI', 9, 'bold'), relief='flat')

    def _btn(self, parent, text, cmd, kind='normal', **kw):
        colors = {'normal': '#285475', 'danger': '#685229', 'ghost': PANEL2, 'go': '#1f6a4a'}
        b = tk.Button(parent, text=text, command=cmd, bg=colors[kind], fg='#ffffff', activebackground=ACCENT,
                      relief='flat', cursor='hand2', padx=12, pady=6, font=('Segoe UI', 9, 'bold'),
                      disabledforeground='#7f8ea3', **kw)
        return b

    def _lbl(self, parent, text, muted=True, **kw):
        return tk.Label(parent, text=text, fg=MUTED if muted else FG, bg=PANEL, font=('Segoe UI', 9),
                        justify='left', anchor='w', **kw)

    def _build(self):
        top = tk.Frame(self, bg=BG); top.pack(fill='x', padx=22, pady=(16, 4))
        tk.Label(top, text='AGFO', fg=ACCENT, bg=BG, font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        tk.Label(top, text='Phantom Shot', fg=FG, bg=BG, font=('Segoe UI', 22, 'bold')).pack(anchor='w')
        tk.Label(top, text='Tek tusla sessiz ekran goruntusu — ekranda hicbir sey gostermez.',
                 fg=MUTED, bg=BG, font=('Segoe UI', 10)).pack(anchor='w', pady=(2, 0))

        # GitHub guncelleme bandi
        self.gh_banner = tk.Frame(self, bg='#1d4d3a', padx=12, pady=7)
        self.gh_banner_text = tk.StringVar(value='')
        tk.Label(self.gh_banner, textvariable=self.gh_banner_text, fg='#ffffff', bg='#1d4d3a',
                 font=('Segoe UI', 10, 'bold')).pack(side='left')
        for txt, cmd, bg in (('Bu surumu atla', self.gh_skip, '#2a5f4a'), ('Notlar', self.gh_show_notes, '#2a5f4a'),
                             ('Simdi guncelle', self.gh_update, '#2f8f5f')):
            tk.Button(self.gh_banner, text=txt, command=cmd, bg=bg, fg='#ffffff', relief='flat', padx=12, pady=3,
                      cursor='hand2', activebackground=ACCENT).pack(side='right', padx=(6, 0))

        frm = tk.Frame(self, bg=PANEL); frm.pack(fill='both', expand=True, padx=22, pady=12)
        pad = {'padx': 8, 'pady': 5}

        self._lbl(frm, 'Kayit klasoru:').grid(row=0, column=0, sticky='w', **pad)
        self.var_dir = tk.StringVar()
        ttk.Entry(frm, textvariable=self.var_dir, width=40).grid(row=0, column=1, sticky='we', **pad)
        self._btn(frm, 'Gozat…', self._browse, 'ghost').grid(row=0, column=2, **pad)

        self._lbl(frm, 'Tetik tusu:').grid(row=1, column=0, sticky='w', **pad)
        self.var_key = tk.StringVar()
        ttk.Combobox(frm, textvariable=self.var_key, values=KEY_CHOICES, width=18, state='readonly').grid(row=1, column=1, sticky='w', **pad)

        self._lbl(frm, 'Fare tusu:').grid(row=2, column=0, sticky='w', **pad)
        self.var_mouse = tk.StringVar()
        ttk.Combobox(frm, textvariable=self.var_mouse, values=MOUSE_CHOICES, width=18, state='readonly').grid(row=2, column=1, sticky='w', **pad)

        self._lbl(frm, 'Ekran (0=hepsi):').grid(row=3, column=0, sticky='w', **pad)
        self.var_monitor = tk.StringVar(value='0')
        ttk.Spinbox(frm, from_=0, to=8, textvariable=self.var_monitor, width=5).grid(row=3, column=1, sticky='w', **pad)

        self._lbl(frm, 'Bicim:').grid(row=4, column=0, sticky='w', **pad)
        fmt = tk.Frame(frm, bg=PANEL); fmt.grid(row=4, column=1, columnspan=2, sticky='w', **pad)
        self.var_fmt = tk.StringVar(value='png')
        ttk.Radiobutton(fmt, text='PNG', variable=self.var_fmt, value='png').pack(side='left')
        ttk.Radiobutton(fmt, text='JPG', variable=self.var_fmt, value='jpg').pack(side='left', padx=(8, 0))
        tk.Label(fmt, text='kalite:', fg=MUTED, bg=PANEL, font=('Segoe UI', 9)).pack(side='left', padx=(12, 2))
        self.var_quality = tk.StringVar(value='90')
        ttk.Spinbox(fmt, from_=10, to=100, textvariable=self.var_quality, width=5).pack(side='left')

        self._lbl(frm, 'Dosya oneki:').grid(row=5, column=0, sticky='w', **pad)
        self.var_prefix = tk.StringVar(value='shot')
        ttk.Entry(frm, textvariable=self.var_prefix, width=18).grid(row=5, column=1, sticky='w', **pad)

        self.var_autostart = tk.BooleanVar()
        self.var_tray = tk.BooleanVar()
        ttk.Checkbutton(frm, text='Acilista dinlemeye basla', variable=self.var_autostart).grid(row=6, column=1, columnspan=2, sticky='w', **pad)
        self.chk_tray = ttk.Checkbutton(frm, text='Kapatinca sistem tepsisine kucult (pystray gerekli)', variable=self.var_tray)
        self.chk_tray.grid(row=7, column=1, columnspan=2, sticky='w', **pad)
        frm.columnconfigure(1, weight=1)

        btns = tk.Frame(self, bg=BG); btns.pack(fill='x', padx=22, pady=(0, 6))
        self.btn_toggle = self._btn(btns, 'Baslat', self.toggle, 'go'); self.btn_toggle.pack(side='left', padx=(0, 6))
        self._btn(btns, 'Ayarlari kaydet', self._save_notify, 'normal').pack(side='left', padx=(0, 6))
        self._btn(btns, 'Klasoru ac', self._open_folder, 'ghost').pack(side='left', padx=(0, 6))
        self._btn(btns, 'Guncelleme…', self.open_updater, 'normal').pack(side='right')

        stbar = tk.Frame(self, bg=PANEL, padx=12, pady=8); stbar.pack(fill='x', padx=22, pady=(0, 16))
        self.var_status = tk.StringVar(value='Durdu — islem baslatmadikca hicbir sey yakalanmaz.')
        self.lbl_status = tk.Label(stbar, textvariable=self.var_status, fg=MUTED, bg=PANEL, font=('Segoe UI', 10), anchor='w')
        self.lbl_status.pack(side='left')

    def _fill_from_cfg(self):
        self.var_dir.set(self.cfg.get('save_dir') or '')
        self.var_key.set(self.cfg.get('key') or '(yok)')
        self.var_mouse.set(self.cfg.get('mouse_button') or '(yok)')
        self.var_monitor.set(str(self.cfg.get('monitor', 0)))
        self.var_fmt.set(self.cfg.get('format', 'png'))
        self.var_quality.set(str(self.cfg.get('jpg_quality', 90)))
        self.var_prefix.set(self.cfg.get('prefix', 'shot'))
        self.var_autostart.set(bool(self.cfg.get('autostart', False)))
        self.var_tray.set(bool(self.cfg.get('minimize_to_tray', True)))

    # ---------------------------------------------------------------- ayar / dosya
    def _collect(self):
        self.cfg['save_dir'] = self.var_dir.get().strip()
        self.cfg['key'] = self.var_key.get()
        self.cfg['mouse_button'] = '' if self.var_mouse.get() == '(yok)' else self.var_mouse.get()
        self.cfg['format'] = self.var_fmt.get()
        self.cfg['prefix'] = self.var_prefix.get().strip() or 'shot'
        try:
            self.cfg['monitor'] = int(self.var_monitor.get())
        except ValueError:
            self.cfg['monitor'] = 0
        try:
            self.cfg['jpg_quality'] = int(self.var_quality.get())
        except ValueError:
            self.cfg['jpg_quality'] = 90
        self.cfg['autostart'] = bool(self.var_autostart.get())
        self.cfg['minimize_to_tray'] = bool(self.var_tray.get())
        if self.cfg['key'] == '(yok)':
            self.cfg['key'] = ''

    def _save(self):
        self._collect()
        return core.save_settings(self.cfg)

    def _save_notify(self):
        if self._save():
            self.var_status.set('Ayarlar kaydedildi.')
            self.lbl_status.config(fg=MUTED)

    def _browse(self):
        d = filedialog.askdirectory(initialdir=core.resolve_save_dir(self.var_dir.get()), title='Kayit klasoru sec')
        if d:
            self.var_dir.set(d)

    def _open_folder(self):
        d = core.resolve_save_dir(self.var_dir.get())
        os.makedirs(d, exist_ok=True)
        try:
            os.startfile(d)  # Windows
        except AttributeError:
            messagebox.showinfo('Klasor', d)

    # ---------------------------------------------------------------- dinleme
    def toggle(self):
        self.stop() if self.running else self.start()

    def start(self):
        if self.running:
            return
        self._save()
        keyboard, mouse = _pynput()
        if keyboard is None:
            messagebox.showerror('Eksik paket', 'pynput ve mss gerekli:\n\n    pip install pynput mss\n\nKurup tekrar deneyin.')
            return
        try:
            import mss  # noqa: F401
        except Exception:
            messagebox.showerror('Eksik paket', 'mss gerekli:\n\n    pip install mss')
            return
        key_obj, key_char = resolve_key(self.cfg.get('key'))
        mouse_btn = resolve_mouse_button(self.cfg.get('mouse_button'))
        if key_obj is None and key_char is None and mouse_btn is None:
            messagebox.showwarning('Tetik yok', 'En az bir tetik tusu veya fare tusu secin.')
            return

        def on_done(path, count, err=None):
            def upd():
                if path:
                    self.var_status.set('Alindi (%d): %s' % (count, os.path.basename(path)))
                    self.lbl_status.config(fg=OK_C)
                else:
                    self.var_status.set('Hata: %s' % (err or 'yakalama basarisiz'))
                    self.lbl_status.config(fg=BAD_C)
            self.messages.put(('call', upd))

        def on_press(k):
            try:
                if key_obj is not None and k == key_obj:
                    self.cap.shoot(self.cfg, on_done)
                elif key_char is not None and getattr(k, 'char', None) == key_char:
                    self.cap.shoot(self.cfg, on_done)
            except Exception:
                pass

        def on_click(x, y, button, pressed):
            if pressed and mouse_btn is not None and button == mouse_btn:
                self.cap.shoot(self.cfg, on_done)

        if key_obj is not None or key_char is not None:
            self.kb_listener = keyboard.Listener(on_press=on_press)
            self.kb_listener.daemon = True
            self.kb_listener.start()
        if mouse_btn is not None:
            self.ms_listener = mouse.Listener(on_click=on_click)
            self.ms_listener.daemon = True
            self.ms_listener.start()

        self.running = True
        self.btn_toggle.config(text='Durdur', bg='#6b2a2a')
        trig = []
        if self.cfg.get('key'):
            trig.append(self.cfg['key'])
        if self.cfg.get('mouse_button'):
            trig.append('fare:' + self.cfg['mouse_button'])
        self.var_status.set('Dinleniyor  (%s)' % ', '.join(trig))
        self.lbl_status.config(fg=OK_C)

    def stop(self):
        for l in (self.kb_listener, self.ms_listener):
            try:
                if l is not None:
                    l.stop()
            except Exception:
                pass
        self.kb_listener = self.ms_listener = None
        self.running = False
        self.btn_toggle.config(text='Baslat', bg='#1f6a4a')
        self.var_status.set('Durdu')
        self.lbl_status.config(fg=MUTED)

    # ---------------------------------------------------------------- Tk kuyrugu
    def _poll(self):
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == 'call':
                    try:
                        payload()
                    except tk.TclError:
                        pass
        except queue.Empty:
            pass
        self.after(POLL_MS, self._poll)

    def _run_bg(self, fn):
        """fn(post) arka planda calisir; post(callable) ana is parcacigina is yollar."""
        def post(cb):
            self.messages.put(('call', cb))
        threading.Thread(target=lambda: fn(post), daemon=True).start()

    # ---------------------------------------------------------------- GitHub tek-tik guncelleme
    def gh_check(self, force=True):
        def fn(post):
            res = ghu.check_for_update(core.GH_PREFIX, VERSION, core.GH_STATE, core.GH_ASSET, force=force,
                                       user_agent='AGFO-Phantom-Shot/' + VERSION)
            post(lambda: self._gh_checked(res, force))
        self._run_bg(fn)

    def _gh_checked(self, res, force):
        st = res.get('status')
        if st == 'update':
            self.gh_result = res
            rel = res['release']
            self.gh_banner_text.set('Yeni surum hazir: Phantom Shot %s  (kurulu: %s%s)' %
                                    (res['version'], VERSION, (', yayin: ' + rel['published']) if rel.get('published') else ''))
            if not self.gh_banner.winfo_ismapped():
                self.gh_banner.pack(fill='x', padx=22, pady=(0, 8), after=self.winfo_children()[0])
        elif force:
            msg = {'current': 'Guncelsiniz (son surum %s).' % res.get('version', VERSION),
                   'none': "GitHub'da henuz Phantom Shot surumu yok.",
                   'skipped': 'Surum %s atlanmis olarak isaretli.' % res.get('version', ''),
                   'error': 'Denetlenemedi: %s' % res.get('message', '')}.get(st, st)
            messagebox.showinfo('GitHub guncelleme', msg)
            if getattr(self, 'upd_gh_state', None):
                try:
                    self.upd_gh_state.set(msg)
                except tk.TclError:
                    pass

    def gh_show_notes(self):
        if not self.gh_result:
            return
        rel = self.gh_result['release']
        messagebox.showinfo('Surum %s notlari' % self.gh_result['version'],
                            (rel.get('notes') or 'Not eklenmemis.')[:3000] + '\n\n' + rel.get('url', ''))

    def gh_skip(self):
        if self.gh_result:
            ghu.skip_version(core.GH_STATE, self.gh_result['version'])
        self.gh_banner.pack_forget()

    def gh_update(self):
        res = self.gh_result
        if not res or self.busy:
            if self.busy:
                messagebox.showinfo('Mesgul', 'Bir islem suruyor; bitince tekrar deneyin.')
            return
        rel, asset = res['release'], res['asset']
        notes = (rel.get('notes') or '').strip()
        if not messagebox.askyesno('Guncelleme', 'AGFO Phantom Shot %s -> %s\n\n%s\n\nIndirilip dogrulanacak, mevcut surum '
                                   'yedeklenecek ve uygulama yeniden baslatilacak. Devam edilsin mi?'
                                   % (VERSION, res['version'], (notes[:800] + ('…' if len(notes) > 800 else '')) or 'Surum notu yok.')):
            return
        dest = core.GH_DOWNLOAD_DIR / asset['name']
        stage = core.APP_DATA_DIR / 'update-stage'
        self.busy = True

        def fn(post):
            try:
                sha = ghu.expected_sha256(rel, asset, user_agent='AGFO-Phantom-Shot/' + VERSION)
                ghu.download_asset(asset, dest, sha, None, None, user_agent='AGFO-Phantom-Shot/' + VERSION)
                info = core.inspect_update(str(dest), VERSION)
                if not info['ok']:
                    raise OSError('Paket denetimi basarisiz: ' + '; '.join(info['errors']))
                if info['version'] != res['version']:
                    raise OSError('Paket surumu (%s) etiketle (%s) uyusmuyor.' % (info['version'], res['version']))
                core.stage_update(str(dest), info, stage)
                checks = core.preflight(stage)
                bad = [n + ': ' + d for n, s_, d in checks if s_ == 'fail']
                if bad:
                    raise OSError('On kontrol basarisiz: ' + '; '.join(bad))
                bdir = core.apply_update(stage, self.install_dir, self.backup_root, VERSION, info['version'])
                import shutil
                shutil.rmtree(stage, ignore_errors=True)
                try:
                    dest.unlink()
                except OSError:
                    pass
                post(lambda: self._gh_update_done(info['version'], bdir))
            except Exception as e:
                post(lambda: self._gh_update_fail(str(e)))
        self._run_bg(fn)

    def _gh_update_done(self, new_version, bdir):
        self.busy = False
        self.gh_banner.pack_forget()
        self.var_status.set('Phantom Shot %s kuruldu; yeniden baslatiliyor…' % new_version)
        self.after(900, self.restart_app)

    def _gh_update_fail(self, msg):
        self.busy = False
        messagebox.showerror('Guncelleme', 'Guncelleme tamamlanamadi; kurulu surum degismedi veya geri yuklendi.\n\n%s' % msg)

    # ---------------------------------------------------------------- guncelleme penceresi (elle ZIP + yedekler)
    def open_updater(self):
        if getattr(self, 'upd_win', None) and self.upd_win.winfo_exists():
            self.upd_win.lift(); return
        win = self.upd_win = tk.Toplevel(self); win.title('AGFO Phantom Shot — Guncelleme'); win.configure(bg=PANEL); win.transient(self)
        w, h = int(780 * self.scale), int(560 * self.scale)
        win.geometry('%dx%d+%d+%d' % (w, h, self.winfo_rootx() + 40, self.winfo_rooty() + 40))
        top = tk.Frame(win, bg=PANEL); top.pack(fill='x', padx=16, pady=(14, 4))
        tk.Label(top, text='Guncelleme', fg=FG, bg=PANEL, font=('Segoe UI', 13, 'bold')).pack(side='left')
        tk.Label(top, text='Kurulu surum: %s' % VERSION, fg=OK_C, bg=PANEL2, font=('Segoe UI', 9, 'bold'), padx=10, pady=3).pack(side='left', padx=10)
        self._lbl(win, 'Konum: %s\nGitHub\'da denetleyip tek tikla guncelleyebilir ya da elle bir guncelleme paketi (.zip) secebilirsiniz. '
                       'Paket once denetlenir (yapi, surum, MANIFEST/SHA-256, Python/PowerShell on kontrol); mevcut surum yedeklenir, '
                       'yeni dosyalar yerlestirilir ve uygulama yeniden baslar. Bir adim basarisiz olursa onceki surum otomatik geri '
                       'yuklenir. Ayarlariniz (config.json) ve gunlukler etkilenmez.' % self.install_dir,
                  wraplength=int(740 * self.scale)).pack(fill='x', padx=16)
        bar = tk.Frame(win, bg=PANEL); bar.pack(fill='x', padx=16, pady=8)
        self._btn(bar, "GitHub'da denetle", lambda: self.gh_check(force=True), 'go').pack(side='left', padx=(0, 6))
        self._btn(bar, 'Guncelleme paketi sec (.zip)…', self.upd_pick, 'ghost').pack(side='left', padx=(0, 6))
        self.upd_apply_btn = self._btn(bar, 'Uygula ve yeniden baslat', self.upd_apply, 'danger'); self.upd_apply_btn.pack(side='left')
        self.upd_apply_btn.configure(state='disabled')
        ghf = tk.Frame(win, bg=PANEL); ghf.pack(fill='x', padx=16, pady=(0, 6))
        self.upd_gh_state = tk.StringVar(value='GitHub deposu: %s (etiket: %s*)' % (ghu.GITHUB_REPO, core.GH_PREFIX))
        tk.Label(ghf, textvariable=self.upd_gh_state, fg=MUTED, bg=PANEL, font=('Segoe UI', 9)).pack(side='left')
        self.upd_auto = tk.BooleanVar(value=self.cfg.get('auto_update_check', True))

        def _auto():
            self.cfg['auto_update_check'] = bool(self.upd_auto.get())
            core.save_settings(self.cfg)
        ttk.Checkbutton(ghf, text='Acilista guncellemeleri denetle', variable=self.upd_auto, command=_auto).pack(side='right')
        self.upd_check = tk.Text(win, height=9, bg='#09111e', fg='#dce8fa', relief='flat', font=('Consolas', 9), padx=10, pady=8, wrap='word')
        self.upd_check.pack(fill='both', expand=True, padx=16)
        for tg, col in (('ok', OK_C), ('fail', BAD_C), ('warn', WARN), ('h', ACCENT)):
            self.upd_check.tag_configure(tg, foreground=col)
        self.upd_check.insert('end', 'Paket secilmedi.'); self.upd_check.configure(state='disabled')
        low = tk.Frame(win, bg=PANEL); low.pack(fill='x', padx=16, pady=(8, 14))
        tk.Label(low, text='Yedekler (en son %d)' % core.UPDATE_KEEP_BACKUPS, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.upd_bk = ttk.Treeview(low, columns=('ver', 'time'), show='headings', height=3)
        self.upd_bk.heading('ver', text='Surum'); self.upd_bk.heading('time', text='Yedek zamani')
        self.upd_bk.column('ver', width=120); self.upd_bk.column('time', width=200)
        self.upd_bk.pack(side='left', fill='x', expand=True)
        rb = tk.Frame(low, bg=PANEL); rb.pack(side='left', padx=10)
        self._btn(rb, 'Secili yedege don', self.upd_rollback, 'ghost').pack(side='top', pady=2)
        self._btn(rb, 'Gecmis', self.upd_history, 'ghost').pack(side='top', pady=2)
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
        path = filedialog.askopenfilename(parent=self.upd_win, title='Guncelleme paketi secin',
                                          filetypes=[('Guncelleme paketi', '*.zip'), ('Tum dosyalar', '*.*')])
        if not path:
            return
        self.upd_apply_btn.configure(state='disabled')
        stage = core.APP_DATA_DIR / 'update-stage'
        self._upd_show([('Denetleniyor: %s' % path, 'h')])

        def fn(post):
            info = core.inspect_update(path, VERSION)
            checks = []
            if info['ok']:
                try:
                    core.stage_update(path, info, stage)
                    checks = core.preflight(stage)
                except Exception as e:
                    info['ok'] = False
                    info['errors'].append(str(e))
            post(lambda: self._upd_checked(path, info, checks))
        self._run_bg(fn)

    def _upd_checked(self, path, info, checks):
        L = [('Paket: %s' % path, 'h')]
        if info['version']:
            arrow = '%s → %s' % (VERSION, info['version'])
            L.append(('✓ Surum: %s%s' % (arrow, '  (DUSURME)' if info['downgrade'] else ('  (ayni surum)' if info['same'] else '')),
                      'warn' if (info['downgrade'] or info['same']) else 'ok'))
        for e in info['errors']:
            L.append(('✗ ' + e, 'fail'))
        if info['ok']:
            L.append(('✓ Paket yapisi ve dosya yollari guvenli; zorunlu dosyalar mevcut', 'ok'))
            L.append(('✓ %d calisma dosyasi' % len(info['files']), 'ok'))
            if info['manifest']:
                L.append(('✓ MANIFEST.json: tum dosyalarin SHA-256 ozetleri dogrulandi', 'ok'))
        for wmsg in info['warnings']:
            L.append(('! ' + wmsg, 'warn'))
        for name, st, det in checks:
            L.append((('✓ ' if st == 'ok' else ('✗ ' if st == 'fail' else '– ')) + name + (('  — ' + det) if det else ''),
                      {'ok': 'ok', 'fail': 'fail'}.get(st, 'warn')))
        ready = info['ok'] and not any(st == 'fail' for _, st, _ in checks)
        L.append(('', None))
        L.append(('Hazir: "Uygula ve yeniden baslat" ile kurabilirsiniz.' if ready else 'Bu paket kurulamaz.', 'ok' if ready else 'fail'))
        self.upd_info = (path, info) if ready else None
        if getattr(self, 'upd_win', None) and self.upd_win.winfo_exists():
            self._upd_show(L)
            self.upd_apply_btn.configure(state='normal' if ready else 'disabled')

    def upd_apply(self):
        if not self.upd_info or self.busy:
            return
        path, info = self.upd_info
        msg = 'AGFO Phantom Shot %s → %s guncellenecek.\nMevcut surum yedeklenecek; uygulama yeniden baslatilacak.' % (VERSION, info['version'])
        if info['downgrade']:
            msg += '\n\nDIKKAT: Bu daha ESKI bir surum.'
        if not info['manifest']:
            msg += '\n\nUYARI: Pakette MANIFEST.json yok; dosya butunlugu dogrulanamadi. Yalnizca guvendiginiz kaynaktan gelen paketi kurun.'
        if not messagebox.askyesno('Guncellemeyi uygula', msg + '\n\nDevam edilsin mi?', parent=self.upd_win):
            return
        self.upd_apply_btn.configure(state='disabled')
        self.busy = True
        stage = core.APP_DATA_DIR / 'update-stage'

        def fn(post):
            try:
                bdir = core.apply_update(stage, self.install_dir, self.backup_root, VERSION, info['version'])
                import shutil
                shutil.rmtree(stage, ignore_errors=True)
                post(lambda: self._upd_done(info['version'], bdir, None))
            except Exception as e:
                post(lambda: self._upd_done(None, None, str(e)))
        self._run_bg(fn)

    def _upd_done(self, new_version, bdir, err):
        self.busy = False
        self._upd_refresh_backups()
        if err or not new_version:
            self._upd_show([('✗ Guncelleme uygulanamadi; onceki surum geri yuklendi.%s' % (('  ' + err) if err else ''), 'fail')])
            return
        self.upd_info = None
        self._upd_show([('✓ AGFO Phantom Shot %s kuruldu. Uygulama yeniden baslatiliyor…' % new_version, 'ok')])
        self.after(800, self.restart_app)

    def upd_rollback(self):
        sel = self.upd_bk.selection()
        if not sel:
            messagebox.showinfo('Yedekler', 'Listeden bir yedek secin.', parent=self.upd_win); return
        b = next((x for x in core.list_backups(self.backup_root) if x['path'] == sel[0]), None)
        if not b or not messagebox.askyesno('Onceki surume don', 'Surum %s (%s) geri yuklenecek; mevcut surum de yedeklenecek. '
                                            'Uygulama yeniden baslatilacak. Devam?' % (b['version'], b['time']), parent=self.upd_win):
            return
        self.busy = True

        def fn(post):
            try:
                target, bdir = core.rollback_update(b['path'], self.install_dir, VERSION)
                post(lambda: self._upd_done(target, bdir, None))
            except Exception as e:
                post(lambda: self._upd_done(None, None, str(e)))
        self._run_bg(fn)

    def upd_history(self):
        h = core.update_history(15)
        messagebox.showinfo('Guncelleme gecmisi', '\n'.join(h) if h else 'Henuz guncelleme yapilmadi.', parent=self.upd_win)

    def restart_app(self):
        try:
            exe = sys.executable
            # pythonw varsa penceresiz baslat
            if IS_WIN and exe.lower().endswith('python.exe'):
                cand = str(pathlib.Path(exe).with_name('pythonw.exe'))
                if os.path.isfile(cand):
                    exe = cand
            subprocess.Popen([exe, str(pathlib.Path(self.install_dir) / 'app.pyw')], cwd=str(self.install_dir),
                             creationflags=getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
        except OSError as e:
            messagebox.showerror('Yeniden baslatma', 'Uygulamayi elle yeniden acin: %s' % e)
            return
        self.stop()
        self.destroy()

    # ---------------------------------------------------------------- tepsi / kapanis
    def _on_close(self):
        if self.var_tray.get():
            try:
                import pystray  # noqa: F401
                from PIL import Image  # noqa: F401
                self._hide_to_tray()
                return
            except Exception:
                pass
        self.stop()
        self.destroy()

    def _hide_to_tray(self):
        import pystray
        from PIL import Image
        self.withdraw()
        if self.tray_icon is not None:
            return
        img = Image.new('RGB', (64, 64), (20, 32, 52))
        for x in range(16, 48):
            for y in range(22, 42):
                img.putpixel((x, y), (73, 179, 239))

        def _show(icon=None, item=None):
            self.after(0, self._restore)

        def _quit(icon=None, item=None):
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None
            self.after(0, self._really_quit)

        menu = pystray.Menu(pystray.MenuItem('Goster', _show, default=True), pystray.MenuItem('Cikis', _quit))
        self.tray_icon = pystray.Icon('AGFO Phantom Shot', img, 'AGFO Phantom Shot', menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _restore(self):
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None
        self.deiconify(); self.lift()

    def _really_quit(self):
        self.stop()
        self.destroy()


def main():
    App().mainloop()


if __name__ == '__main__':
    main()
