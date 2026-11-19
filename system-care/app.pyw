# -*- coding: utf-8 -*-
"""AGFO System Care — Windows bakim uygulamasi (Python/tkinter + PowerShell).

4.0: Kod sayfa modullerine bolundu. Bu dosya uygulamanin iskeletidir (pencere, sol menu, gorunum/tema); her sayfa
kendi sc_*.py modulunde bir mixin sinifidir, paylasilan siniflar ve yardimcilar sc_base.py'dedir. Moduller kok klasorde
durur (uygulama ici guncelleyici kok .py dosyalarini kopyalar).
"""
import pathlib as _pl
import sys as _sys
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
from sc_base import *  # noqa: E402,F401,F403
import sc_base  # noqa: E402
from sc_engines import EnginesPage  # noqa: E402
from sc_clean import CleanPage  # noqa: E402
from sc_programs import ProgramsPage  # noqa: E402
from sc_bloat import BloatPage  # noqa: E402
from sc_organizer import OrganizerPage  # noqa: E402
from sc_tweaks import TweaksPage  # noqa: E402
from sc_phantom import PhantomPage  # noqa: E402
from sc_drivers import DriversPage  # noqa: E402
from sc_apps import AppsPage  # noqa: E402
from sc_install import InstallPage  # noqa: E402
from sc_vpn import VpnPage  # noqa: E402
from sc_maint import MaintPage  # noqa: E402
from sc_pad import PadPage  # noqa: E402
from sc_common import CommonMixin  # noqa: E402


class App(EnginesPage, CleanPage, ProgramsPage, BloatPage, OrganizerPage, TweaksPage, PhantomPage, DriversPage, AppsPage, InstallPage, VpnPage, MaintPage, PadPage, CommonMixin, tk.Tk):
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


register_palette_module(globals())


if __name__ == '__main__':
    App().mainloop()
