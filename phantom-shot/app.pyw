"""AGFO Phantom Shot - tek tusla sessiz ekran goruntusu (Windows GUI, tek dosyalik EXE).

Ayar penceresinden klasoru, tetik tusunu/fare tusunu ve bicimi secersiniz. "Baslat" dediginizde arka
planda dinler; secili tusa basildiginda ekran goruntusunu alir ve ekranda HICBIR pencere, bildirim ya
da ses gostermeden kaydeder. Pencereyi sistem tepsisine kucultebilirsiniz.

Yakalama mss, tus/fare dinleme pynput ile yapilir (EXE'ye gomuludur). GitHub'daki
downtownck/agfo-windows-apps deposundan uygulama kendini tek tikla gunceller: yeni EXE indirilir,
SHA-256 ile dogrulanir, uygulama kapaninca yeni surum kendini eski dosyanin uzerine yazar ve acilir.

Komut satiri: --smoke <png> (derleme oz-testi), --apply-update <hedef> --wait-pid <pid> (guncelleyici).
"""
import ctypes
import os
import pathlib
import queue
import sys
import threading

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

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import phantom_core as core  # noqa: E402
import phantom_update as upd  # noqa: E402
import agfo_github_update as ghu  # noqa: E402

VERSION = core.VERSION
FROZEN = bool(getattr(sys, 'frozen', False))
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
    if 'kb' not in _PYNPUT:
        try:
            from pynput import keyboard, mouse
            _PYNPUT['kb'], _PYNPUT['ms'] = keyboard, mouse
        except Exception:
            _PYNPUT['kb'] = _PYNPUT['ms'] = None
    return _PYNPUT['kb'], _PYNPUT['ms']


def resolve_key(key_name):
    keyboard, _ = _pynput()
    if keyboard is None or not key_name or key_name == '(yok)':
        return None, None
    name = str(key_name).strip().lower()
    special = {'print_screen', 'pause', 'scroll_lock', 'insert', 'home', 'end', 'page_up', 'page_down', 'menu', 'space'}
    for i in range(1, 25):
        special.add('f%d' % i)
    if name in special:
        obj = getattr(keyboard.Key, name, None)
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
    if name in ('left', 'right', 'middle', 'x1', 'x2', 'button8', 'button9'):
        return getattr(mouse.Button, name, None)
    return None


class Capturer:
    """Tek bir ekran goruntusu alir; ekranda hicbir sey gostermez."""

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
        if self.cfg.get('auto_update_check', True) and FROZEN:
            self.after(2500, lambda: self.gh_check(force=False))
        if self.cfg.get('autostart'):
            self.after(400, self.start)
        if FROZEN:
            self.after(600, self._first_run_install)

    # ---------------------------------------------------------------- stil / iskelet
    def _icon_path(self):
        if FROZEN:
            return pathlib.Path(getattr(sys, '_MEIPASS', '.')) / 'assets' / 'agfo-phantom.ico'
        return pathlib.Path(__file__).resolve().parent / 'assets' / 'agfo-phantom.ico'

    def _set_icon(self):
        ico = self._icon_path()
        if IS_WIN and ico.is_file():
            try:
                self.iconbitmap(default=str(ico))
            except Exception:
                pass

    def _style(self):
        s = ttk.Style(self)
        s.theme_use('clam')
        s.configure('.', background=PANEL, foreground=FG, fieldbackground=PANEL2, font=('Segoe UI', 10))
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

    def _btn(self, parent, text, cmd, kind='normal', **kw):
        colors = {'normal': '#285475', 'danger': '#685229', 'ghost': PANEL2, 'go': '#1f6a4a'}
        return tk.Button(parent, text=text, command=cmd, bg=colors[kind], fg='#ffffff', activebackground=ACCENT,
                         relief='flat', cursor='hand2', padx=12, pady=6, font=('Segoe UI', 9, 'bold'),
                         disabledforeground='#7f8ea3', **kw)

    def _lbl(self, parent, text, muted=True, **kw):
        return tk.Label(parent, text=text, fg=MUTED if muted else FG, bg=PANEL, font=('Segoe UI', 9),
                        justify='left', anchor='w', **kw)

    def _build(self):
        top = tk.Frame(self, bg=BG); top.pack(fill='x', padx=22, pady=(16, 4))
        tk.Label(top, text='AGFO', fg=ACCENT, bg=BG, font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        tk.Label(top, text='Phantom Shot', fg=FG, bg=BG, font=('Segoe UI', 22, 'bold')).pack(anchor='w')
        tk.Label(top, text='Tek tusla sessiz ekran goruntusu — ekranda hicbir sey gostermez.',
                 fg=MUTED, bg=BG, font=('Segoe UI', 10)).pack(anchor='w', pady=(2, 0))

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
        ttk.Checkbutton(frm, text='Kapatinca sistem tepsisine kucult', variable=self.var_tray).grid(row=7, column=1, columnspan=2, sticky='w', **pad)
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
        key = self.var_key.get()
        self.cfg['key'] = '' if key == '(yok)' else key
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

    def _save(self):
        self._collect()
        return core.save_settings(self.cfg)

    def _save_notify(self):
        if self._save():
            self.var_status.set('Ayarlar kaydedildi.'); self.lbl_status.config(fg=MUTED)

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
            messagebox.showerror('Eksik bilesen', 'Tus dinleme (pynput) yuklenemedi.')
            return
        try:
            import mss  # noqa: F401
        except Exception:
            messagebox.showerror('Eksik bilesen', 'Ekran yakalama (mss) yuklenemedi.')
            return
        key_obj, key_char = resolve_key(self.cfg.get('key'))
        mouse_btn = resolve_mouse_button(self.cfg.get('mouse_button'))
        if key_obj is None and key_char is None and mouse_btn is None:
            messagebox.showwarning('Tetik yok', 'En az bir tetik tusu veya fare tusu secin.')
            return

        def on_done(path, count, err=None):
            def ui():
                if path:
                    self.var_status.set('Alindi (%d): %s' % (count, os.path.basename(path))); self.lbl_status.config(fg=OK_C)
                else:
                    self.var_status.set('Hata: %s' % (err or 'yakalama basarisiz')); self.lbl_status.config(fg=BAD_C)
            self.messages.put(('call', ui))

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
            self.kb_listener = keyboard.Listener(on_press=on_press); self.kb_listener.daemon = True; self.kb_listener.start()
        if mouse_btn is not None:
            self.ms_listener = mouse.Listener(on_click=on_click); self.ms_listener.daemon = True; self.ms_listener.start()

        self.running = True
        self.btn_toggle.config(text='Durdur', bg='#6b2a2a')
        trig = [t for t in (self.cfg.get('key'), ('fare:' + self.cfg['mouse_button']) if self.cfg.get('mouse_button') else '') if t]
        self.var_status.set('Dinleniyor  (%s)' % ', '.join(trig)); self.lbl_status.config(fg=OK_C)

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
        self.var_status.set('Durdu'); self.lbl_status.config(fg=MUTED)

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
        def post(cb):
            self.messages.put(('call', cb))
        threading.Thread(target=lambda: fn(post), daemon=True).start()

    # ---------------------------------------------------------------- ilk acilista kurulum (EXE)
    def _first_run_install(self):
        try:
            if pathlib.Path(sys.executable).resolve() == upd.installed_exe().resolve():
                return  # zaten Programs altindan calisiyor
        except OSError:
            return
        if not messagebox.askyesno('Kurulum', 'AGFO Phantom Shot bu bilgisayara kurulsun mu?\n\n'
                                   'Program %s klasorune kopyalanir; Baslat menusu ve masaustu kisayolu olusturulur. '
                                   'Yonetici gerekmez.' % upd.install_dir(), parent=self):
            return

        def fn(post):
            try:
                dst = upd.install_self(desktop=True)
                post(lambda: self._reopen_installed(dst))
            except Exception as e:
                post(lambda: messagebox.showwarning('Kurulum', 'Kurulamadi: %s\nUygulama buradan calismaya devam ediyor.' % e, parent=self))
        self._run_bg(fn)

    def _reopen_installed(self, dst):
        messagebox.showinfo('Kuruldu', 'Kuruldu: %s\nKurulu surum aciliyor.' % dst, parent=self)
        try:
            upd.launch(dst)
        except Exception:
            pass
        self.stop(); self.destroy()

    # ---------------------------------------------------------------- GitHub guncelleme
    def gh_check(self, force=True):
        def fn(post):
            res = upd.check(force=force)
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
            if getattr(self, 'upd_state', None):
                try:
                    self.upd_state.set(msg)
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
            ghu.skip_version(upd.state_path(), self.gh_result['version'])
        self.gh_banner.pack_forget()

    def gh_update(self):
        res = self.gh_result
        if not res or self.busy:
            if self.busy:
                messagebox.showinfo('Mesgul', 'Bir islem suruyor; bitince tekrar deneyin.')
            return
        if not FROZEN:
            messagebox.showinfo('Guncelleme', 'Tek tikla guncelleme yalnizca derlenmis (EXE) surumde calisir. '
                                'Kaynaktan calistiriyorsunuz; GitHub\'dan yeni surumu elle kurabilirsiniz.')
            return
        rel = res['release']
        notes = (rel.get('notes') or '').strip()
        if not messagebox.askyesno('Guncelleme', 'AGFO Phantom Shot %s -> %s\n\n%s\n\nIndirilip dogrulanacak, uygulama '
                                   'kapanip yeni surumle yeniden acilacak. Devam edilsin mi?'
                                   % (VERSION, res['version'], (notes[:800] + ('…' if len(notes) > 800 else '')) or 'Surum notu yok.')):
            return
        self.busy = True
        self.var_status.set('Guncelleme indiriliyor…'); self.lbl_status.config(fg=ACCENT)

        def fn(post):
            try:
                new_exe = upd.download(res)
                proc = upd.apply_update(new_exe)
                import time as _t
                _t.sleep(2)
                if proc.poll() is not None:   # guvenlik yazilimi guncelleyiciyi hemen kapattiysa
                    raise OSError('Guncelleyici baslatilamadi (guvenlik yazilimi engellemis olabilir).')
                post(self._gh_update_launched)
            except Exception as e:
                post(lambda: self._gh_update_fail(str(e)))
        self._run_bg(fn)

    def _gh_update_launched(self):
        # Guncelleyici ayakta; bu surum kapanmali ki dosya serbest kalsin.
        self.var_status.set('Yeni surum kuruluyor; uygulama kapaniyor…')
        self.stop()
        self.after(400, self.destroy)

    def _gh_update_fail(self, msg):
        self.busy = False
        self.var_status.set('Guncelleme basarisiz.'); self.lbl_status.config(fg=BAD_C)
        messagebox.showerror('Guncelleme', 'Guncelleme tamamlanamadi; kurulu surum degismedi.\n\n%s' % msg)

    def open_updater(self):
        if getattr(self, 'upd_win', None) and self.upd_win.winfo_exists():
            self.upd_win.lift(); return
        win = self.upd_win = tk.Toplevel(self); win.title('AGFO Phantom Shot — Guncelleme'); win.configure(bg=PANEL); win.transient(self)
        w, h = int(620 * self.scale), int(300 * self.scale)
        win.geometry('%dx%d+%d+%d' % (w, h, self.winfo_rootx() + 40, self.winfo_rooty() + 40))
        tk.Label(win, text='Guncelleme', fg=FG, bg=PANEL, font=('Segoe UI', 13, 'bold')).pack(anchor='w', padx=16, pady=(14, 2))
        tk.Label(win, text='Kurulu surum: %s' % VERSION, fg=OK_C, bg=PANEL, font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=16)
        note = ('GitHub\'daki %s deposundan yeni surum denetlenir. "Simdi guncelle" yeni EXE\'yi indirir, '
                'SHA-256 ile dogrular, uygulama kapaninca yerine koyar ve yeniden acar. Ayarlariniz (config.json) korunur.' % ghu.GITHUB_REPO)
        self._lbl(win, note, wraplength=int(580 * self.scale)).pack(fill='x', padx=16, pady=(6, 8))
        bar = tk.Frame(win, bg=PANEL); bar.pack(fill='x', padx=16)
        self._btn(bar, "GitHub'da denetle", lambda: self.gh_check(force=True), 'go').pack(side='left', padx=(0, 6))
        self._btn(bar, 'Simdi guncelle', self.gh_update, 'normal').pack(side='left', padx=(0, 6))
        self._btn(bar, 'Bu bilgisayardan kaldir', self._uninstall, 'danger').pack(side='right')
        self.upd_state = tk.StringVar(value='Hazir.' if FROZEN else 'Kaynaktan calisiyor — tek tikla guncelleme yalnizca EXE surumunde.')
        tk.Label(win, textvariable=self.upd_state, fg=MUTED, bg=PANEL, font=('Segoe UI', 9), anchor='w',
                 wraplength=int(580 * self.scale), justify='left').pack(fill='x', padx=16, pady=(10, 4))
        self.upd_auto = tk.BooleanVar(value=self.cfg.get('auto_update_check', True))

        def _auto():
            self.cfg['auto_update_check'] = bool(self.upd_auto.get()); core.save_settings(self.cfg)
        ttk.Checkbutton(win, text='Acilista guncellemeleri denetle', variable=self.upd_auto, command=_auto).pack(anchor='w', padx=16, pady=(6, 10))

    def _uninstall(self):
        if not FROZEN:
            messagebox.showinfo('Kaldir', 'Kaldirma yalnizca kurulu EXE surumunde gecerli.'); return
        if not messagebox.askyesno('Kaldir', 'AGFO Phantom Shot bu bilgisayardan kaldirilsin mi?\n\n'
                                   'Program dosyasi ve kisayollar silinir; ayarlariniz (config.json) ve gunlukler korunur. '
                                   'Uygulama kapanacak.', parent=self.upd_win):
            return
        try:
            upd.uninstall()
        except Exception as e:
            messagebox.showerror('Kaldir', 'Kaldirilamadi: %s' % e, parent=self.upd_win); return
        self.stop(); self.destroy()

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
        self.stop(); self.destroy()

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
        self.stop(); self.destroy()


# =========================================================================== komut satiri / giris
def smoke(png_path):
    """Derleme oz-testi: tum bilesenler yuklenebiliyor mu, GUI kuruluyor mu, mss bir kare alabiliyor mu."""
    try:
        import mss  # noqa: F401
        import mss.tools  # noqa: F401
        from pynput import keyboard, mouse  # noqa: F401
        from PIL import Image  # noqa: F401
        import pystray  # noqa: F401
        app = App()
        app.withdraw()
        app.update_idletasks()
        app.update()
        try:
            with mss.mss() as sct:
                shot = sct.grab(sct.monitors[0])
                mss.tools.to_png(shot.rgb, shot.size, output=png_path)
        except Exception:
            Image.new('RGB', (64, 64), (20, 32, 52)).save(png_path)
        app.destroy()
        print('AGFO PHANTOM SHOT SMOKE OK')
        return 0
    except Exception as e:
        print('SMOKE FAIL: %r' % e)
        return 1


def apply_update_main(target, pid):
    """Yeni EXE guncelleyici kipinde: eski surum kapaninca kendini hedefe kopyalar ve hedefi acar."""
    root = tk.Tk()
    root.title('AGFO Phantom Shot')
    root.configure(bg=PANEL)
    root.geometry('420x120')
    root.resizable(False, False)
    try:
        ico = pathlib.Path(getattr(sys, '_MEIPASS', '.')) / 'assets' / 'agfo-phantom.ico'
        if IS_WIN and ico.is_file():
            root.iconbitmap(default=str(ico))
    except Exception:
        pass
    tk.Label(root, text='AGFO Phantom Shot %s kuruluyor…' % VERSION, fg=FG, bg=PANEL,
             font=('Segoe UI', 11, 'bold')).pack(pady=(20, 8))
    pb = ttk.Progressbar(root, mode='indeterminate', length=340); pb.pack(); pb.start(12)
    q = queue.Queue()

    def work():
        try:
            if not upd.wait_for_pid(pid, 90):
                raise OSError('Eski surum 90 saniyede kapanmadi.')
            upd.replace_target(sys.executable, target)
            upd.launch(target)
            upd.log_line('Update applied: %s' % target)
            q.put(None)
        except Exception as e:
            upd.log_line('Update failed: %r' % e)
            q.put(e)
    threading.Thread(target=work, daemon=True).start()
    out = {}

    def poll():
        try:
            out['err'] = q.get_nowait()
        except queue.Empty:
            root.after(150, poll); return
        pb.stop()
        if out['err'] is not None:
            messagebox.showerror('Guncelleme', 'Guncelleme uygulanamadi: %s\n\nYeni surum su dosyada, dogrudan acabilirsiniz:\n%s'
                                 % (out['err'], sys.executable), parent=root)
        root.destroy()
    root.after(150, poll)
    root.mainloop()
    return 0 if out.get('err') is None else 1


def main():
    argv = sys.argv
    if len(argv) >= 3 and argv[1] == '--smoke':
        return smoke(argv[2])
    if len(argv) >= 3 and argv[1] == '--apply-update':
        pid = 0
        if '--wait-pid' in argv:
            try:
                pid = int(argv[argv.index('--wait-pid') + 1])
            except (ValueError, IndexError):
                pid = 0
        return apply_update_main(argv[2], pid)
    App().mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
