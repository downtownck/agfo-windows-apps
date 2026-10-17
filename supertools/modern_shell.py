# -*- coding: utf-8 -*-
"""AGFO SuperTools native Windows shell: IObit-inspired visual language.

Visual-only layer for the existing Tkinter app. Network scans, diagnostics,
SSH and update operations continue to use their original handlers.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

PALETTES = {
    "dark": {
        "bg": "#0b1024", "side": "#111a33", "panel": "#171f3b",
        "panel_alt": "#1e294b", "input": "#11192f", "line": "#2b395a",
        "text": "#f2f6ff", "muted": "#a4b3d2", "accent": "#63b1ff",
        "accent_deep": "#216adb", "accent_text": "#08152f", "hover": "#25365a",
        "selected": "#2b4c7e", "good": "#49dfb6", "warn": "#edc888",
        "console": "#090f21", "table": "#111a32", "header": "#263456",
    },
    "light": {
        "bg": "#eff3fa", "side": "#152545", "panel": "#ffffff",
        "panel_alt": "#f4f7fc", "input": "#f3f7fc", "line": "#dce4f1",
        "text": "#1d2c49", "muted": "#5e718d", "accent": "#146de2",
        "accent_deep": "#105ac1", "accent_text": "#ffffff", "hover": "#e5edfc",
        "selected": "#cde2ff", "good": "#168767", "warn": "#9b641f",
        "console": "#0e1930", "table": "#ffffff", "header": "#e9f0fb",
    },
}

NAV_ITEMS = (
    ("dashboard", "◉", "Genel Bakış"),
    ("scan", "◎", "Ağ Tarayıcı"),
    ("supertools", "⌘", "SuperTools"),
    ("ssh", "▣", "SSH Sunucularım"),
    ("ssh_sessions", "▤", "SSH Oturumları"),
    ("logs", "≡", "Dahili Terminal"),
    ("updates", "↻", "Güncelleme Merkezi"),
)


def rgb(value):
    return tuple(int(value[i:i+2], 16) for i in (1, 3, 5))


def mix(a, b, t):
    aa, bb = rgb(a), rgb(b)
    return "#" + "".join("%02x" % round(x * (1 - t) + y * t) for x, y in zip(aa, bb))


class ModernShell:
    def _modern_style(self):
        p = PALETTES[self.appearance]
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        for key, bg in (("TFrame", p["bg"]), ("Page.TFrame", p["bg"]),
                        ("White.TFrame", p["panel"]), ("Card.TFrame", p["panel"]),
                        ("CardAlt.TFrame", p["panel_alt"])):
            style.configure(key, background=bg)
        styles = {
            "TLabel": (p["bg"], p["text"], ("Segoe UI", 10)),
            "White.TLabel": (p["panel"], p["text"], ("Segoe UI", 10)),
            "Small.TLabel": (p["bg"], p["muted"], ("Segoe UI", 9)),
            "Info.TLabel": (p["panel"], p["muted"], ("Segoe UI", 9)),
            "Heading.TLabel": (p["bg"], p["text"], ("Segoe UI Semibold", 20)),
            "Section.TLabel": (p["panel"], p["text"], ("Segoe UI Semibold", 11)),
            "Status.TLabel": (p["bg"], p["accent"], ("Segoe UI", 9)),
            "Metric.TLabel": (p["panel"], p["text"], ("Segoe UI Semibold", 26)),
            "MetricCaption.TLabel": (p["panel"], p["muted"], ("Segoe UI", 9)),
        }
        for name, (bg, fg, font) in styles.items():
            style.configure(name, background=bg, foreground=fg, font=font)
        style.configure("TButton", foreground=p["text"], background=p["panel_alt"],
                        bordercolor=p["line"], borderwidth=1, padding=(12, 9),
                        font=("Segoe UI Semibold", 9), focuscolor=p["panel_alt"])
        style.map("TButton", background=[("active", p["hover"]), ("disabled", p["panel_alt"])],
                  foreground=[("disabled", p["muted"])])
        style.configure("Blue.TButton", foreground=p["accent_text"], background=p["accent"],
                        borderwidth=0, padding=(17, 11), font=("Segoe UI Semibold", 10))
        style.map("Blue.TButton", background=[("active", p["accent_deep"]), ("disabled", p["line"])],
                  foreground=[("active", "#ffffff"), ("disabled", p["muted"])])
        style.configure("Treeview", background=p["table"], foreground=p["text"],
                        fieldbackground=p["table"], rowheight=35, borderwidth=0,
                        font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background=p["header"], foreground=p["text"],
                        relief="flat", padding=(10, 10), font=("Segoe UI Semibold", 9))
        style.map("Treeview", background=[("selected", p["selected"])],
                  foreground=[("selected", p["text"])])
        style.configure("Horizontal.TProgressbar", background=p["accent"],
                        troughcolor=p["input"], borderwidth=0)
        style.configure("TCheckbutton", background=p["panel"], foreground=p["text"],
                        font=("Segoe UI", 9), focuscolor=p["panel"])
        style.map("TCheckbutton", background=[("active", p["panel"])],
                  foreground=[("disabled", p["muted"])])
        style.configure("TEntry", fieldbackground=p["input"], foreground=p["text"],
                        bordercolor=p["line"], insertcolor=p["text"], padding=(9, 7))
        style.configure("TCombobox", fieldbackground=p["input"], foreground=p["text"],
                        background=p["panel_alt"], arrowcolor=p["text"], padding=(8, 7))
        style.map("TCombobox", fieldbackground=[("readonly", p["input"])],
                  foreground=[("readonly", p["text"])])
        style.configure("TScrollbar", background=p["panel_alt"], troughcolor=p["panel"],
                        arrowcolor=p["text"], borderwidth=0)
        style.configure("TSeparator", background=p["line"])
        style.configure("Hidden.TNotebook", background=p["panel"], borderwidth=0,
                        padding=0, tabmargins=(0, 0, 0, 0))
        # Keep ttk.Notebook's tab switching API, hide tabs; the sidebar owns navigation.
        style.layout("Hidden.TNotebook.Tab", [])
        style.configure("SSH.TNotebook", background=p["panel"], borderwidth=0)
        style.configure("SSH.TNotebook.Tab", background=p["panel_alt"], foreground=p["text"],
                        padding=(15, 9), font=("Segoe UI Semibold", 9))
        style.map("SSH.TNotebook.Tab", background=[("selected", p["selected"])],
                  foreground=[("selected", p["text"])])
        # Toolbar styles use the native ttk engine; no web runtime or extra packages.
        self.configure(bg=p["bg"])

    def _modern_build_ui(self):
        self.nav_buttons = {}
        self._nav_page = "dashboard"
        p = PALETTES[self.appearance]
        self.sidebar = tk.Frame(self, bg=p["side"], width=235, bd=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self._make_sidebar()

        self.stage = tk.Frame(self, bg=p["bg"])
        self.stage.pack(side="left", fill="both", expand=True)
        self._make_topbar()

        foot = ttk.Frame(self.stage, style="Page.TFrame", padding=(23, 7, 23, 13))
        foot.pack(side="bottom", fill="x")
        self.status_var = tk.StringVar(value="Hazır · Ağ önerileri okunuyor…")
        ttk.Label(foot, textvariable=self.status_var, style="Status.TLabel").pack(side="left", expand=True, fill="x")
        ttk.Label(foot, text="Yalnızca yetkili olduğunuz ağları inceleyin.", style="Small.TLabel").pack(side="right")

        content = ttk.Frame(self.stage, style="Page.TFrame", padding=(21, 12, 21, 0))
        content.pack(fill="both", expand=True)
        self.tabs = ttk.Notebook(content, style="Hidden.TNotebook")
        self.tabs.pack(fill="both", expand=True)
        self.tab_dashboard = ttk.Frame(self.tabs, style="Page.TFrame")
        self.tab_devices = ttk.Frame(self.tabs, style="Page.TFrame")
        self.tab_logs = ttk.Frame(self.tabs, style="White.TFrame")
        self.tab_supertools = ttk.Frame(self.tabs, style="White.TFrame")
        self.tab_ssh = ttk.Frame(self.tabs, style="White.TFrame")
        self.tab_ssh_sessions = ttk.Frame(self.tabs, style="White.TFrame")
        self.tab_updates = ttk.Frame(self.tabs, style="White.TFrame")
        for label, frame in (("Genel Bakış", self.tab_dashboard),
                             ("Ağ Tarayıcı", self.tab_devices),
                             ("SuperTools", self.tab_supertools),
                             ("SSH Sunucularım", self.tab_ssh),
                             ("SSH Oturumları", self.tab_ssh_sessions),
                             ("Dahili Terminal", self.tab_logs),
                             ("Güncelleme Merkezi", self.tab_updates)):
            self.tabs.add(frame, text=label)
        self._pages = dict(dashboard=self.tab_dashboard, scan=self.tab_devices,
                           supertools=self.tab_supertools, ssh=self.tab_ssh,
                           ssh_sessions=self.tab_ssh_sessions,
                           logs=self.tab_logs, updates=self.tab_updates)
        self.found_var = tk.StringVar(value="0 cihaz")
        self._make_dashboard()
        self._make_scanner()
        self._make_logs()
        self._build_supertools_tab()
        self._build_ssh_tab()
        self._build_ssh_workspace_tab()
        self._build_update_center()
        self._log("AGFO SuperTools v%s hazır. Ağ testleri kullanıcı başlatınca çalışır." % self._app_version())
        self.tabs.bind("<<NotebookTabChanged>>", self._on_tab_switch)
        self._switch_view("dashboard")

        self._modern_apply_palette()

    def _app_version(self):
        import scanner_core
        return scanner_core.APP_VERSION

    def _make_sidebar(self):
        p = PALETTES[self.appearance]
        brand = tk.Frame(self.sidebar, bg=p["side"])
        brand.pack(fill="x", padx=21, pady=(25, 27))
        mark = tk.Label(brand, text="A", bg=p["accent"], fg=p["accent_text"],
                        font=("Segoe UI Semibold", 18), width=2, height=1)
        mark.pack(side="left", padx=(0, 11))
        text = tk.Frame(brand, bg=p["side"])
        text.pack(side="left")
        tk.Label(text, text="AGFO", bg=p["side"], fg="white",
                 font=("Segoe UI Semibold", 15)).pack(anchor="w")
        tk.Label(text, text="SUPERTOOLS", bg=p["side"], fg="#95a8ce",
                 font=("Segoe UI", 8)).pack(anchor="w")
        self._sidebar_heading("WORKSPACE")
        for key, icon, label in NAV_ITEMS[:5]:
            self._nav_button(key, icon, label)
        self._sidebar_heading("SYSTEM", pad=(26, 11))
        for key, icon, label in NAV_ITEMS[5:]:
            self._nav_button(key, icon, label)
        tk.Frame(self.sidebar, bg=p["side"]).pack(fill="both", expand=True)
        tk.Frame(self.sidebar, bg="#2b3958", height=1).pack(fill="x", padx=17)
        self.sidebar_footer = tk.Frame(self.sidebar, bg=p["side"])
        self.sidebar_footer.pack(fill="x", padx=17, pady=17)
        self.sidebar_version = tk.Label(self.sidebar_footer, text="●  Local workspace", bg=p["side"],
                    fg="#6ee1bc", anchor="w", font=("Segoe UI", 9))
        self.sidebar_version.pack(fill="x")
        tk.Label(self.sidebar_footer, text="AGFO  •  v" + self._app_version(),
                 bg=p["side"], fg="#8a9cc1", font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 0))

    def _sidebar_heading(self, title, pad=(0, 11)):
        p = PALETTES[self.appearance]
        label = tk.Label(self.sidebar, text=title, bg=p["side"], fg="#7184ad",
                         font=("Segoe UI Semibold", 8), anchor="w")
        label.pack(fill="x", padx=23, pady=pad)

    def _nav_button(self, key, icon, caption):
        p = PALETTES[self.appearance]
        frame = tk.Frame(self.sidebar, bg=p["side"])
        frame.pack(fill="x", padx=12, pady=2)
        btn = tk.Button(frame, text="%s    %s" % (icon, caption), cursor="hand2", anchor="w",
                        bg=p["side"], fg="#b2c2e2", activeforeground="white",
                        activebackground="#263961", relief="flat", bd=0, highlightthickness=0,
                        padx=15, pady=12, font=("Segoe UI Semibold", 10),
                        command=lambda k=key: self._switch_view(k))
        btn.pack(fill="x")
        btn.bind("<Enter>", lambda _e, b=btn, k=key: b.configure(bg="#263456") if self._nav_page != k else None)
        btn.bind("<Leave>", lambda _e, b=btn, k=key: b.configure(
            bg=PALETTES[self.appearance]["accent_deep"] if self._nav_page == k else PALETTES[self.appearance]["side"]))
        self.nav_buttons[key] = btn

    def _make_topbar(self):
        p = PALETTES[self.appearance]
        self.topbar = tk.Frame(self.stage, bg=p["bg"], height=76)
        self.topbar.pack(fill="x", padx=24, pady=(12, 2))
        self.topbar.pack_propagate(False)
        heading = tk.Frame(self.topbar, bg=p["bg"])
        heading.pack(side="left", fill="y")
        self.location_label = tk.Label(heading, text="CONTROL CENTER  /  OVERVIEW", bg=p["bg"],
                         fg=p["accent"], font=("Segoe UI Semibold", 8), anchor="w")
        self.location_label.pack(anchor="w", pady=(1, 2))
        self.page_title_label = tk.Label(heading, text="Genel Bakış", bg=p["bg"], fg=p["text"],
                                       font=("Segoe UI Semibold", 19))
        self.page_title_label.pack(anchor="w")
        self.theme_btn = tk.Button(self.topbar, text="☀  Açık tema", command=self._modern_toggle_appearance,
            bg=p["panel_alt"], fg=p["text"], activebackground=p["hover"],
            activeforeground=p["text"], bd=0, relief="flat", padx=15, pady=10,
            cursor="hand2", font=("Segoe UI Semibold", 9))
        self.theme_btn.pack(side="right", pady=7)
        self.version_chip = tk.Label(self.topbar, text="v" + self._app_version(),
            bg=p["panel"], fg=p["muted"], font=("Segoe UI", 9), padx=12, pady=11)
        self.version_chip.pack(side="right", padx=(0, 11), pady=7)

    def _switch_view(self, key):
        if key not in getattr(self, "_pages", {}):
            return
        self.tabs.select(self._pages[key])
        self._refresh_navigation(key)

    def _refresh_navigation(self, key):
        self._nav_page = key
        for name, button in self.nav_buttons.items():
            if name == key:
                button.configure(bg="#246bcc", fg="white")
            else:
                button.configure(bg="#111a33", fg="#b2c2e2")
        title = next((cap for k, ic, cap in NAV_ITEMS if k == key), "SuperTools")
        self.page_title_label.configure(text=title)
        self.location_label.configure(text="CONTROL CENTER  /  " + key.upper())
        if key == "dashboard":
            self._update_dashboard()

    def _on_tab_switch(self, _event=None):
        # Process only the *current* tab after queued Tk events have settled.
        # Do not select a second tab here: that caused stale TabChanged events
        # to override quick page changes immediately after a theme switch.
        self.after_idle(self._sync_navigation_to_selected_tab)

    def _sync_navigation_to_selected_tab(self):
        if not hasattr(self, "_pages"):
            return
        current = self.tabs.select()
        for name, frame in self._pages.items():
            if str(frame) == current:
                self._refresh_navigation(name)
                return

    def _make_dashboard(self):
        outer = self.tab_dashboard
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)
        p = PALETTES[self.appearance]
        self.dashboard_canvas = tk.Canvas(outer, bg=p["bg"], bd=0, highlightthickness=0)
        self.dashboard_canvas.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(outer, orient="vertical", command=self.dashboard_canvas.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.dashboard_canvas.configure(yscrollcommand=scroll.set)
        page = ttk.Frame(self.dashboard_canvas, style="Page.TFrame")
        self.dashboard_body = page
        dashboard_window = self.dashboard_canvas.create_window(0, 0, window=page, anchor="nw")
        page.bind("<Configure>", lambda _e: self.dashboard_canvas.configure(
            scrollregion=self.dashboard_canvas.bbox("all")))
        self.dashboard_canvas.bind("<Configure>", lambda e: self.dashboard_canvas.itemconfigure(
            dashboard_window, width=e.width))
        self.bind_all("<MouseWheel>", self._dashboard_scroll, add="+")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(4, weight=1)
        self.hero = tk.Frame(page, bg=p["panel"], highlightthickness=1, highlightbackground=p["line"])
        self.hero.grid(row=0, column=0, sticky="ew", pady=(0, 17))
        self.hero.columnconfigure(0, weight=1)
        htext = tk.Frame(self.hero, bg=p["panel"])
        htext.grid(row=0, column=0, sticky="nsew", padx=(27, 4), pady=(17, 15))
        self.hero_textbox = htext
        self.hero_eyebrow = tk.Label(htext, text="◉  SMART NETWORK MANAGEMENT", bg=p["panel"],
            fg=p["accent"], font=("Segoe UI Semibold", 9), anchor="w")
        self.hero_eyebrow.pack(anchor="w")
        self.hero_title = tk.Label(htext, text="Ağınız ve sunucularınız,\ntek bir kontrol merkezinde.",
            bg=p["panel"], fg=p["text"], justify="left", anchor="w",
            font=("Segoe UI Semibold", 21))
        self.hero_title.pack(anchor="w", pady=(10, 6))
        self.hero_descr = tk.Label(htext, text="Cihazları keşfedin, DNS ve e-posta testleri yapın,\nSSH sunucularınıza hızla ulaşın.",
            bg=p["panel"], fg=p["muted"], justify="left", anchor="w",
            font=("Segoe UI", 10))
        self.hero_descr.pack(anchor="w")
        hero_actions = tk.Frame(htext, bg=p["panel"])
        hero_actions.pack(anchor="w", pady=(17, 0))
        self.dashboard_scan_btn = ttk.Button(hero_actions, text="Ağ Taramasını Başlat  →",
            style="Blue.TButton", command=self._dashboard_scan)
        self.dashboard_scan_btn.pack(side="left")
        ttk.Button(hero_actions, text="DNS / Mail Testi", command=lambda: self._switch_view("supertools")).pack(
            side="left", padx=(11, 0))

        self.scan_orb = tk.Canvas(self.hero, width=250, height=216, bg=p["panel"],
                        borderwidth=0, highlightthickness=0, cursor="hand2")
        self.scan_orb.grid(row=0, column=1, sticky="e", padx=(0, 25))
        self.scan_orb.bind("<Button-1>", lambda _e: self._dashboard_scan())
        self.scan_orb.bind("<Configure>", lambda _e: self._draw_orb())

        head = ttk.Frame(page, style="Page.TFrame")
        head.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(head, text="Anlık çalışma özeti", style="Heading.TLabel").pack(side="left")
        ttk.Label(head, text="Son oturumdaki tarama sonuçları", style="Small.TLabel").pack(side="right")

        stats = ttk.Frame(page, style="Page.TFrame")
        stats.grid(row=2, column=0, sticky="ew", pady=(0, 19))
        for col in range(3):
            stats.columnconfigure(col, weight=1, uniform="metrics")
        self.dashboard_active = tk.StringVar(value="0")
        self.dashboard_smb = tk.StringVar(value="0")
        self.dashboard_ssh = tk.StringVar(value="0")
        self.metric_cards = []
        for i, (symbol, var, title, hint, accent) in enumerate((
            ("◎", self.dashboard_active, "Aktif cihaz", "Ağ keşfi", "#58b0ff"),
            ("▣", self.dashboard_smb, "SMB cihazı", "445 erişimi", "#52dec1"),
            ("⌘", self.dashboard_ssh, "SSH profili", "Kayıtlı hesaplar", "#c9a9ff"),
        )):
            card = tk.Frame(stats, bg=p["panel"], highlightthickness=1, highlightbackground=p["line"])
            card.grid(row=0, column=i, sticky="ew", padx=(0, 10) if i < 2 else 0, ipady=5)
            self.metric_cards.append(card)
            top = tk.Frame(card, bg=p["panel"])
            top.pack(fill="x", padx=17, pady=(12, 2))
            ico = tk.Label(top, text=symbol, bg=p["panel_alt"], fg=accent,
                           font=("Segoe UI Semibold", 16), width=3, height=2)
            ico.pack(side="right")
            text = tk.Frame(top, bg=p["panel"])
            text.pack(side="left")
            ttk.Label(text, textvariable=var, style="Metric.TLabel").pack(anchor="w")
            ttk.Label(text, text=title, style="Section.TLabel").pack(anchor="w")
            ttk.Label(card, text=hint, style="Info.TLabel").pack(anchor="w", padx=18, pady=(1, 8))

        bar = ttk.Frame(page, style="Page.TFrame")
        bar.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(bar, text="Araçlar", style="Heading.TLabel").pack(side="left")
        ttk.Label(bar, text="Hızlı erişim", style="Small.TLabel").pack(side="right")
        quick = ttk.Frame(page, style="Page.TFrame")
        quick.grid(row=4, column=0, sticky="nsew")
        for i in range(3):
            quick.columnconfigure(i, weight=1, uniform="quick")
        self.quick_panels = []
        for i, (icon, title, desc, name, action) in enumerate((
            ("⊞", "SuperTools", "DNS, MX, SPF, DMARC ve TLS\ntestlerini tek kutudan çalıştırın.",
             "Testleri aç  →", lambda: self._switch_view("supertools")),
            ("▣", "SSH Sunucularım", "Hetzner, CyberPanel ve NAS\nsunucularınıza hızlı bağlantı.",
             "Sunucularımı aç  →", lambda: self._switch_view("ssh")),
            ("↻", "Güncelleme Merkezi", "İmzalanmamış paketlerin bütünlük\nkontrolleri ve güvenli geri dönüş.",
             "Güncellemeler  →", lambda: self._switch_view("updates")),
        )):
            card = tk.Frame(quick, bg=p["panel"], highlightthickness=1, highlightbackground=p["line"])
            card.grid(row=0, column=i, sticky="nsew", padx=(0, 10) if i < 2 else 0)
            self.quick_panels.append(card)
            iconlabel = tk.Label(card, text=icon, bg=p["panel_alt"], fg=p["accent"],
                      font=("Segoe UI", 18), width=3, height=2)
            iconlabel.pack(anchor="w", padx=16, pady=(14, 8))
            tk.Label(card, text=title, bg=p["panel"], fg=p["text"],
                     font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=16)
            tk.Label(card, text=desc, bg=p["panel"], fg=p["muted"], justify="left",
                     font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(7, 10))
            ttk.Button(card, text=name, command=action).pack(anchor="w", padx=16, pady=(0, 14))

    def _dashboard_scroll(self, event):
        if hasattr(self, "tab_dashboard") and self.tabs.select() == str(self.tab_dashboard):
            offset = int(-event.delta / 120) if event.delta else 0
            if offset:
                self.dashboard_canvas.yview_scroll(offset * 2, "units")

    def _draw_orb(self):
        p = PALETTES[self.appearance]
        c = self.scan_orb
        c.delete("all")
        w = max(210, c.winfo_width())
        h = max(210, c.winfo_height())
        x, y = w//2, h//2
        for r, stroke, width in ((104, p["line"], 1), (93, mix(p["panel"], p["accent"], .15), 17),
                                  (78, p["accent"], 3), (70, mix(p["panel"], p["accent"], .12), 1)):
            c.create_oval(x-r, y-r, x+r, y+r, outline=stroke, width=width)
        for start, extent in ((19, 53), (101, 64), (201, 55), (283, 50)):
            c.create_arc(x-93, y-93, x+93, y+93, start=start, extent=extent,
                         outline="#78ceff", width=13, style=tk.ARC)
        c.create_oval(x-63, y-63, x+63, y+63, fill=p["panel_alt"], outline=p["line"], width=1)
        c.create_text(x, y-6, text="SCAN", fill=p["text"], font=("Segoe UI Semibold", 19))
        c.create_text(x, y+21, text="AĞ TARAMA", fill=p["accent"], font=("Segoe UI Semibold", 8))

    def _dashboard_scan(self):
        self._switch_view("scan")
        self._start_scan()

    def _update_dashboard(self):
        if not hasattr(self, "dashboard_active"):
            return
        values = tuple(getattr(self, "results", {}).values())
        self.dashboard_active.set(str(sum(bool(x.verified) for x in values)))
        self.dashboard_smb.set(str(sum(x.verified and 445 in x.open_ports for x in values)))
        self.dashboard_ssh.set(str(len(getattr(self, "ssh_profiles", []))))

    def _make_scanner(self):
        page = self.tab_devices
        page.rowconfigure(0, weight=1)
        page.columnconfigure(1, weight=1)
        left = ttk.Frame(page, style="White.TFrame", padding=16)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 14))
        left.configure(width=321)
        left.grid_propagate(False)
        left.columnconfigure(0, weight=1)
        ttk.Label(left, text="Tarama alanı", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        p = PALETTES[self.appearance]
        self.scope_text = tk.Text(left, height=4, width=31, font=("Consolas", 10),
                                  bg=p["input"], fg=p["text"], insertbackground=p["text"],
                                  bd=0, relief="flat", wrap="none", padx=10, pady=9)
        self.scope_text.grid(row=1, column=0, sticky="ew", pady=(12, 7))
        ttk.Label(left, text="Satır, virgül veya boşlukla ayır. /24 = 254 IP.",
                  style="Info.TLabel").grid(row=2, column=0, sticky="w")
        actions = ttk.Frame(left, style="White.TFrame")
        actions.grid(row=3, column=0, sticky="ew", pady=(12, 6))
        ttk.Button(actions, text="Ağ önerilerini yenile", command=self._discover_async).pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="Seçileni ekle", command=self._add_suggestion).pack(side="left", padx=(5, 0))
        self.suggestions = tk.Listbox(left, height=4, font=("Segoe UI", 9), bg=p["input"],
                               fg=p["text"], selectbackground=p["selected"], selectforeground=p["text"],
                               borderwidth=0, highlightthickness=0, exportselection=False)
        self.suggestions.grid(row=4, column=0, sticky="ew", pady=(2, 10))
        self.suggestions.bind("<Double-Button-1>", lambda event: self._add_suggestion())
        ttk.Separator(left).grid(row=5, column=0, sticky="ew", pady=(6, 15))
        ttk.Label(left, text="Tarama ayarları", style="Section.TLabel").grid(row=6, column=0, sticky="w")
        self.extended_var = tk.BooleanVar(value=False)
        self.dns_var = tk.BooleanVar(value=False)
        self.discovery_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(left, text="Geniş servis taraması (SSH, FTP, NFS, rsync)",
                        variable=self.extended_var).grid(row=7, column=0, sticky="w", pady=(11, 7))
        ttk.Checkbutton(left, text="Bulunan cihazların DNS adını sorgula",
                        variable=self.dns_var).grid(row=8, column=0, sticky="w", pady=(0, 7))
        ttk.Checkbutton(left, text="ARP + SSDP/mDNS keşfi",
                        variable=self.discovery_var).grid(row=9, column=0, sticky="w", pady=(0, 10))
        opts = ttk.Frame(left, style="White.TFrame")
        opts.grid(row=10, column=0, sticky="ew", pady=(0, 14))
        ttk.Label(opts, text="İşçi sayısı:", style="White.TLabel").grid(row=0, column=0, sticky="w")
        self.workers_var = tk.StringVar(value="48")
        tk.Spinbox(opts, from_=4, to=96, width=4, textvariable=self.workers_var,
                   bg=p["input"], fg=p["text"], buttonbackground=p["panel_alt"],
                   insertbackground=p["text"], relief="flat", font=("Segoe UI", 10)).grid(
                       row=0, column=1, padx=(6, 8))
        ttk.Label(opts, text="ms:", style="White.TLabel").grid(row=0, column=2)
        self.timeout_var = tk.StringVar(value="650")
        tk.Spinbox(opts, from_=100, to=2500, increment=50, width=5, textvariable=self.timeout_var,
                   bg=p["input"], fg=p["text"], buttonbackground=p["panel_alt"],
                   insertbackground=p["text"], relief="flat", font=("Segoe UI", 10)).grid(
                       row=0, column=3, padx=(5, 0))
        btns = ttk.Frame(left, style="White.TFrame")
        btns.grid(row=11, column=0, sticky="ew", pady=(0, 13))
        self.start_btn = ttk.Button(btns, text="Taramayı Başlat", style="Blue.TButton", command=self._start_scan)
        self.start_btn.pack(side="left", expand=True, fill="x")
        self.stop_btn = ttk.Button(btns, text="Durdur", command=self._stop_scan, state="disabled")
        self.stop_btn.pack(side="left", padx=(7, 0))
        self.progress = ttk.Progressbar(left, orient="horizontal", mode="determinate", maximum=100)
        self.progress.grid(row=12, column=0, sticky="ew", pady=(0, 8))
        self.progress_label_var = tk.StringVar(value="Hazır")
        ttk.Label(left, textvariable=self.progress_label_var, style="Info.TLabel",
                  wraplength=276, justify="left").grid(row=13, column=0, sticky="w")
        ttk.Label(left, text="NAT / istemci yalıtımı bazı ağları gizleyebilir.", style="Info.TLabel",
                  wraplength=276).grid(row=14, column=0, sticky="w", pady=(13, 0))
        left.rowconfigure(15, weight=1)
        ttk.Button(left, text="Windows ağ / rota bilgileri", command=self._network_details).grid(
            row=16, column=0, sticky="ew", pady=(7, 0))

        right = ttk.Frame(page, style="White.TFrame", padding=14)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)
        head = ttk.Frame(right, style="White.TFrame")
        head.grid(row=0, column=0, sticky="ew", pady=(2, 8))
        ttk.Label(head, text="Bulunan cihazlar", style="Section.TLabel").pack(side="left")
        ttk.Label(head, textvariable=self.found_var, style="Info.TLabel").pack(side="right")
        ttk.Label(right, text="ICMP/TCP ile doğrulananlar ve ARP adayları farklı renkle gösterilir.",
                  style="Info.TLabel").grid(row=1, column=0, sticky="w", pady=(0, 10))
        table = ttk.Frame(right, style="White.TFrame")
        table.grid(row=2, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        columns = ("ip", "hostname", "mac", "services", "ping", "proof", "state", "ms")
        self.tree = ttk.Treeview(table, columns=columns, show="headings", selectmode="browse")
        headings = {"ip":"IP adresi", "hostname":"DNS adı", "mac":"MAC adresi",
                    "services":"Açık servisler", "ping":"Ping", "proof":"Bulgu",
                    "state":"Durum", "ms":"Süre (ms)"}
        widths = {"ip":126,"hostname":144,"mac":137,"services":180,
                  "ping":60,"proof":110,"state":84,"ms":80}
        for col in columns:
            self.tree.heading(col, text=headings[col], command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=widths[col], stretch=col in ("hostname", "services"), anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        xscroll.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.bind("<Double-Button-1>", self._double_click)
        self.tree.bind("<Button-3>", self._context_menu)
        tools = ttk.Frame(right, style="White.TFrame")
        tools.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        for caption, handler in (("SMB klasörünü aç", self._open_smb),
            ("Paylaşımları sorgula", self._show_shares), ("SMB ile bağlan", self._smb_login_dialog),
            ("Web arayüzü", self._open_web), ("UNC kopyala", self._copy_unc),
            ("CSV kaydet", self._export_csv)):
            ttk.Button(tools, text=caption, command=handler).pack(side="left", padx=(0, 5), pady=3)

    def _make_logs(self):
        self.tab_logs.rowconfigure(1, weight=1)
        self.tab_logs.columnconfigure(0, weight=1)
        header = ttk.Frame(self.tab_logs, style="White.TFrame", padding=(18, 16, 18, 6))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="Dahili Terminal / Günlük", style="Section.TLabel").pack(side="left")
        ttk.Label(header, text="Bütün işlemler sessizce çalışır", style="Info.TLabel").pack(side="right")
        p = PALETTES[self.appearance]
        import tkinter.scrolledtext as scrolledtext
        self.console = scrolledtext.ScrolledText(self.tab_logs, wrap="word", bg=p["console"],
                  fg="#dbe9ff", insertbackground="white", font=("Consolas", 10),
                  relief="flat", padx=15, pady=15, state="disabled")
        self.console.grid(row=1, column=0, sticky="nsew", padx=15, pady=(7, 10))
        toolbar = ttk.Frame(self.tab_logs, style="White.TFrame", padding=(15, 0, 15, 13))
        toolbar.grid(row=2, column=0, sticky="ew")
        ttk.Button(toolbar, text="Günlüğü kopyala", command=self._copy_log).pack(side="left")
        ttk.Button(toolbar, text="Ekranı temizle", command=self._clear_log).pack(side="left", padx=8)

    def _modern_toggle_appearance(self):
        self.appearance = "light" if self.appearance == "dark" else "dark"
        self._modern_style()
        self._modern_apply_palette()
        self._save_settings()

    def _modern_apply_palette(self):
        p = PALETTES[self.appearance]
        self.dashboard_canvas.configure(bg=p["bg"])
        for widget, color in ((self.sidebar, p["side"]), (self.stage, p["bg"]),
                               (self.topbar, p["bg"]), (self.sidebar_footer, p["side"]),
                               (self.hero, p["panel"]), (self.hero_textbox, p["panel"])):
            widget.configure(bg=color)
        for widget in self.sidebar.winfo_children():
            if isinstance(widget, tk.Frame):
                widget.configure(bg=p["side"])
        for widget in self.topbar.winfo_children():
            if isinstance(widget, tk.Frame):
                widget.configure(bg=p["bg"])
        self.theme_btn.configure(text=("☀  Açık tema" if self.appearance == "dark" else "☾  Koyu tema"),
            bg=p["panel_alt"], fg=p["text"], activebackground=p["hover"], activeforeground=p["text"])
        self.page_title_label.configure(bg=p["bg"], fg=p["text"])
        self.location_label.configure(bg=p["bg"], fg=p["accent"])
        self.version_chip.configure(bg=p["panel"], fg=p["muted"])
        self.hero.configure(highlightbackground=p["line"])
        for child in (self.hero_eyebrow, self.hero_title, self.hero_descr):
            child.configure(bg=p["panel"], fg=p["accent"] if child == self.hero_eyebrow else
                            p["muted"] if child == self.hero_descr else p["text"])
        self.scan_orb.configure(bg=p["panel"])
        self._draw_orb()
        for container in (self.hero_textbox,):
            for child in container.winfo_children():
                if isinstance(child, tk.Frame):
                    child.configure(bg=p["panel"])
        for card in self.metric_cards + self.quick_panels:
            card.configure(bg=p["panel"], highlightbackground=p["line"])
            for child in card.winfo_children():
                if isinstance(child, tk.Frame):
                    child.configure(bg=p["panel"])
                    for grandchild in child.winfo_children():
                        if isinstance(grandchild, tk.Frame):
                            grandchild.configure(bg=p["panel"])
                if isinstance(child, tk.Label):
                    child.configure(bg=p["panel"], fg=p["text"] if child.cget("font").find("Semibold") >= 0 else p["muted"])
        for field in (self.scope_text, self.suggestions):
            field.configure(bg=p["input"], fg=p["text"])
        self.scope_text.configure(insertbackground=p["text"])
        self.suggestions.configure(selectbackground=p["selected"], selectforeground=p["text"])
        # Keep code/console output dark in either mode for legibility.
        for field in (self.console, self.diag_output, self.ssh_output):
            field.configure(bg=p["console"], fg="#dceaff", insertbackground="#ffffff")
        self.update_preview.configure(bg=p["input"], fg=p["text"], insertbackground=p["text"])
        self.tree.tag_configure("smb", background=p["panel_alt"], foreground=p["good"])
        self.tree.tag_configure("other", background=p["table"], foreground=p["text"])
        self.tree.tag_configure("candidate", background=p["panel_alt"], foreground=p["warn"])
        # The sidebar stays dark in both modes to preserve brand hierarchy.
        for widget in self.sidebar_footer.winfo_children():
            if isinstance(widget, tk.Label):
                widget.configure(bg=p["side"])
        for key, widget in self.nav_buttons.items():
            widget.configure(bg="#246bcc" if key == self._nav_page else "#111a33",
                             fg="white" if key == self._nav_page else "#b2c2e2")
