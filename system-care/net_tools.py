# -*- coding: utf-8 -*-
"""System Care > Ag: SuperTools'un ag tarayicisi, ag testleri (DNS / e-posta / TLS / TCP) ve SSH sayfalari.

Kayitlar (SSH profilleri, Windows DPAPI parola kasasi, bilinen sunucu anahtarlari, tarama ayarlari) yalnizca bu
bilgisayarda, SuperTools ile ayni %LOCALAPPDATA%\\AGFO-MultiSubnet-Scanner klasorunde kalir. Hicbiri koda, pakete
ya da depoya girmez; iki uygulama ayni dosyalari kullandigi icin tasima/kopyalama da gerekmez.

scanner_core, supertools_core, ssh_* ve supertools_ui modulleri supertools/ klasorundekilerle bayt bayt aynidir
(testler denetler). Bu dosya yalnizca System Care'e baglayan katmandir.
"""
from __future__ import annotations

import csv
import ipaddress
import json
import os
import queue
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
import webbrowser

import scanner_core as core
from supertools_ui import SuperToolsMixin


def settings_path() -> Path:
    base = os.environ.get('LOCALAPPDATA', '').strip() or str(Path.home() / '.agfo-tools')
    return Path(base) / 'AGFO-MultiSubnet-Scanner' / 'settings.json'


def safe_start_process(argv, timeout=None):
    return core.hidden_run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)


class NetTools(SuperToolsMixin, tk.Frame):
    """Gorunmez bir tk.Frame: SuperTools'un mixin'i bu nesne uzerinde calisir, sayfalar System Care'in NavBook sayfalarina kurulur.
    Ayri bir nesne oldugu icin SuperTools'un yontem adlari System Care'in App sinifiyla cakismaz."""

    PAGE_KEYS = ('scan', 'supertools', 'ssh', 'ssh_sessions')

    def __init__(self, app, colors):
        tk.Frame.__init__(self, app)
        self.app = app
        self.colors = colors                     # () -> {'PANEL':..., 'FG':..., ...} guncel tema jetonlari
        self.tabs = app.tabs
        self.results: dict[str, core.HostResult] = {}
        self.msg_queue: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.running = False
        self.network_suggestions = []
        self.discovered = False
        self.save_path = settings_path()
        self.options = self._read_settings()
        self.appearance = self.options.get('appearance', 'dark')
        self.status_var = tk.StringVar(value='Hazır · ağ testleri yalnızca siz başlatınca çalışır.')
        self.found_var = tk.StringVar(value='0 cihaz')
        self._pages = {}
        self._pending_cmd = {}                   # profil kimligi -> baglaninca gonderilecek komut
        self._start_time = time.monotonic()
        self.after(100, self._poll_queue)

    # ------------------------------------------------------------------ System Care baglantilari
    def _log(self, message, focus=False):
        self.app.write('[Ağ] %s\n' % str(message).rstrip())

    def _switch_view(self, key):
        page = self._pages.get(key)
        if page is not None:
            self.tabs.select(page)

    def _ssh_dialog_colors(self):
        c = self.colors()
        return {'panel': c['PANEL'], 'text': c['FG'], 'muted': c['MUTED']}

    def _status_bar(self, page, row, columnspan=1):
        tk.Label(page, textvariable=self.status_var, fg=self.colors()['ACCENT'], bg=self.colors()['PANEL'], font=('Segoe UI', 9),
                 anchor='w', justify='left').grid(row=row, column=0, columnspan=columnspan, sticky='ew', padx=14, pady=(0, 8))

    def build_scan(self, page):
        self.tab_devices = self._pages['scan'] = page
        self._make_scanner()
        self._load_options()

    def build_diag(self, page):
        self.tab_supertools = self._pages['supertools'] = page
        self._build_supertools_tab()
        self._status_bar(page, 7)

    def build_ssh(self, page):
        self.tab_ssh = self._pages['ssh'] = page
        self._build_ssh_tab()

    def build_sessions(self, page):
        self.tab_ssh_sessions = self._pages['ssh_sessions'] = page
        self._build_ssh_workspace_tab()
        self.retheme()

    def on_tab(self):
        """Ag tarayici ilk kez acildiginda Windows arayuz/rota onerilerini okur (acilisi yavaslatmaz)."""
        try:
            current = self.tabs.select()
        except tk.TclError:
            return
        if not self.discovered and 'scan' in self._pages and current == str(self._pages['scan']):
            self.discovered = True
            self._discover_async()

    def retheme(self):
        c = self.colors()
        for w in (getattr(self, 'scope_text', None), getattr(self, 'suggestions', None)):
            if w is not None:
                w.configure(bg=c['TREE_BG'], fg=c['FG'])
        if hasattr(self, 'scope_text'):
            self.scope_text.configure(insertbackground=c['FG'])
            self.suggestions.configure(selectbackground=c['SEL'], selectforeground=c['SEL_FG'])
            for sp in self.spinboxes:
                sp.configure(bg=c['TREE_BG'], fg=c['FG'], buttonbackground=c['PANEL2'], insertbackground=c['FG'])
            self.tree.tag_configure('smb', foreground=c['OK_C'])
            self.tree.tag_configure('other', foreground=c['FG'])
            self.tree.tag_configure('candidate', foreground=c['WARN'])

        def walk(w):
            for ch in w.winfo_children():
                if isinstance(ch, tk.Text) and ch is not getattr(self, 'scope_text', None):
                    ch.configure(bg=c['LOG_BG'], fg=c['LOG_FG'], insertbackground=c['LOG_FG'])
                elif isinstance(ch, tk.Label) and str(ch.cget('textvariable')) == str(self.status_var):
                    ch.configure(bg=c['PANEL'], fg=c['ACCENT'])
                walk(ch)
        for page in self._pages.values():
            walk(page)

    def close(self):
        self.cancel.set()
        self._ssh_disconnect_all()
        self._save_settings()

    # ------------------------------------------------------------------ kayitli sunucuda tek komut (VPN sayfasi kullanir)
    def run_on_server(self, command, title, hint=''):
        """Kayitli bir SSH profiliyle oturum acar ve baglaninca komutu oturuma gonderir (onayla). Parola her zamanki gibi sorulur."""
        if not getattr(self, 'ssh_profiles', None):
            messagebox.showinfo(title, 'Kayıtlı SSH sunucusu yok. Ağ > SSH sunucularım sayfasında sunucuyu ekleyip kaydedin, sonra yeniden deneyin.' +
                                ('\n\n' + hint if hint else ''))
            self._switch_view('ssh')
            return False
        profile = self._pick_profile(title, hint)
        if profile is None:
            return False
        if not messagebox.askyesno(title, '"%s" (%s@%s) sunucusunda şu komut çalıştırılsın mı?\n\n%s\n\n'
                                   'sudo parola sorarsa SSH oturumları sayfasında "Girişi gizle"yi işaretleyip parolayı gönderin.'
                                   % (profile.name, profile.username, profile.host, command)):
            return False
        self._pending_cmd[profile.id] = command
        self._ssh_open_password(profile_override=profile)
        return True

    def _pick_profile(self, title, hint=''):
        c = self.colors()
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=c['PANEL'])
        win.transient(self.app)
        win.resizable(False, False)
        tk.Label(win, text='Komutun çalışacağı sunucuyu seçin', fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 11, 'bold')).pack(anchor='w', padx=18, pady=(14, 4))
        if hint:
            tk.Label(win, text=hint, fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 9), justify='left', wraplength=420).pack(anchor='w', padx=18)
        lb = tk.Listbox(win, height=min(8, max(3, len(self.ssh_profiles))), width=56, bg=c['TREE_BG'], fg=c['FG'], selectbackground=c['SEL'],
                        selectforeground=c['SEL_FG'], highlightthickness=0, borderwidth=0, exportselection=False, font=('Segoe UI', 10))
        for p in self.ssh_profiles:
            lb.insert('end', '%s  —  %s@%s:%s' % (p.name, p.username, p.host, p.port))
        lb.pack(fill='x', padx=18, pady=10)
        lb.selection_set(0)
        out = {'p': None}

        def ok(_e=None):
            sel = lb.curselection()
            if sel:
                out['p'] = self.ssh_profiles[sel[0]]
            win.destroy()
        bar = tk.Frame(win, bg=c['PANEL']); bar.pack(fill='x', padx=18, pady=(0, 14))
        ttk.Button(bar, text='Vazgeç', command=win.destroy).pack(side='right')
        ttk.Button(bar, text='Seç', command=ok).pack(side='right', padx=(0, 6))
        lb.bind('<Double-Button-1>', ok)
        win.bind('<Return>', ok)
        win.bind('<Escape>', lambda _e: win.destroy())
        win.grab_set()
        self.wait_window(win)
        return out['p']

    # ------------------------------------------------------------------ ag tarayici sayfasi
    def _make_scanner(self):
        c = self.colors()
        page = self.tab_devices
        page.rowconfigure(1, weight=1)
        page.columnconfigure(1, weight=1)
        head = ttk.Frame(page, style='White.TFrame')
        head.grid(row=0, column=0, columnspan=2, sticky='ew', padx=14, pady=(12, 6))
        ttk.Label(head, text='Ağ tarayıcı — yerel ağdaki cihazlar', style='Section.TLabel').pack(side='left')
        ttk.Label(head, text='Yalnızca yetkili olduğunuz ağları inceleyin.', style='Info.TLabel').pack(side='right')
        left = ttk.Frame(page, style='White.TFrame', padding=(14, 4, 8, 8))
        left.grid(row=1, column=0, sticky='nsw')
        left.columnconfigure(0, weight=1)
        ttk.Label(left, text='Tarama alanı', style='Section.TLabel').grid(row=0, column=0, sticky='w')
        self.scope_text = tk.Text(left, height=4, width=31, font=('Consolas', 10), bg=c['TREE_BG'], fg=c['FG'], insertbackground=c['FG'],
                                  bd=0, relief='flat', wrap='none', padx=8, pady=6)
        self.scope_text.grid(row=1, column=0, sticky='ew', pady=(8, 4))
        ttk.Label(left, text='Satır, virgül veya boşlukla ayırın. /24 = 254 IP.', style='Info.TLabel').grid(row=2, column=0, sticky='w')
        actions = ttk.Frame(left, style='White.TFrame')
        actions.grid(row=3, column=0, sticky='ew', pady=(8, 4))
        ttk.Button(actions, text='Ağ önerilerini yenile', command=self._discover_async).pack(side='left', fill='x', expand=True)
        ttk.Button(actions, text='Seçileni ekle', command=self._add_suggestion).pack(side='left', padx=(5, 0))
        self.suggestions = tk.Listbox(left, height=4, font=('Segoe UI', 9), bg=c['TREE_BG'], fg=c['FG'], selectbackground=c['SEL'],
                                      selectforeground=c['SEL_FG'], borderwidth=0, highlightthickness=0, exportselection=False)
        self.suggestions.grid(row=4, column=0, sticky='ew', pady=(2, 8))
        self.suggestions.bind('<Double-Button-1>', lambda _e: self._add_suggestion())
        ttk.Label(left, text='Tarama ayarları', style='Section.TLabel').grid(row=5, column=0, sticky='w', pady=(4, 0))
        self.extended_var = tk.BooleanVar(value=False)
        self.dns_var = tk.BooleanVar(value=False)
        self.discovery_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(left, text='Geniş servis taraması (SSH, FTP, NFS, rsync)', variable=self.extended_var).grid(row=6, column=0, sticky='w', pady=(6, 3))
        ttk.Checkbutton(left, text='Bulunan cihazların DNS adını sorgula', variable=self.dns_var).grid(row=7, column=0, sticky='w', pady=(0, 3))
        ttk.Checkbutton(left, text='ARP + SSDP/mDNS keşfi', variable=self.discovery_var).grid(row=8, column=0, sticky='w', pady=(0, 6))
        opts = ttk.Frame(left, style='White.TFrame')
        opts.grid(row=9, column=0, sticky='ew', pady=(0, 8))
        ttk.Label(opts, text='İşçi sayısı:', style='White.TLabel').grid(row=0, column=0, sticky='w')
        self.workers_var = tk.StringVar(value='48')
        self.timeout_var = tk.StringVar(value='650')
        self.spinboxes = []
        for col, (var, lo, hi, inc, w) in enumerate(((self.workers_var, 4, 96, 1, 4), (self.timeout_var, 100, 2500, 50, 5))):
            if col:
                ttk.Label(opts, text='ms:', style='White.TLabel').grid(row=0, column=2, padx=(6, 0))
            sp = tk.Spinbox(opts, from_=lo, to=hi, increment=inc, width=w, textvariable=var, bg=c['TREE_BG'], fg=c['FG'],
                            buttonbackground=c['PANEL2'], insertbackground=c['FG'], relief='flat', font=('Segoe UI', 10))
            sp.grid(row=0, column=1 + col * 2, padx=(5, 0))
            self.spinboxes.append(sp)
        btns = ttk.Frame(left, style='White.TFrame')
        btns.grid(row=10, column=0, sticky='ew', pady=(0, 8))
        self.start_btn = ttk.Button(btns, text='Taramayı başlat', style='Blue.TButton', command=self._start_scan)
        self.start_btn.pack(side='left', expand=True, fill='x')
        self.stop_btn = ttk.Button(btns, text='Durdur', command=self._stop_scan, state='disabled')
        self.stop_btn.pack(side='left', padx=(6, 0))
        self.progress = ttk.Progressbar(left, orient='horizontal', mode='determinate', maximum=100)
        self.progress.grid(row=11, column=0, sticky='ew', pady=(0, 6))
        self.progress_label_var = tk.StringVar(value='Hazır')
        ttk.Label(left, textvariable=self.progress_label_var, style='Info.TLabel', wraplength=280, justify='left').grid(row=12, column=0, sticky='w')
        ttk.Label(left, text='NAT / istemci yalıtımı bazı ağları gizleyebilir.', style='Info.TLabel', wraplength=280).grid(row=13, column=0, sticky='w', pady=(8, 0))
        left.rowconfigure(14, weight=1)
        ttk.Button(left, text='Windows ağ / rota bilgileri', command=self._network_details).grid(row=15, column=0, sticky='ew', pady=(6, 0))

        right = ttk.Frame(page, style='White.TFrame', padding=(6, 4, 14, 8))
        right.grid(row=1, column=1, sticky='nsew')
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)
        rh = ttk.Frame(right, style='White.TFrame')
        rh.grid(row=0, column=0, sticky='ew', pady=(0, 4))
        ttk.Label(rh, text='Bulunan cihazlar', style='Section.TLabel').pack(side='left')
        ttk.Label(rh, textvariable=self.found_var, style='Info.TLabel').pack(side='right')
        ttk.Label(right, text='ICMP/TCP ile doğrulananlar ve ARP adayları farklı renkle gösterilir. Çift tık: SMB ya da web arayüzü.',
                  style='Info.TLabel').grid(row=1, column=0, sticky='w', pady=(0, 6))
        table = ttk.Frame(right, style='Card.TFrame')
        table.grid(row=2, column=0, sticky='nsew')
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        columns = ('ip', 'hostname', 'mac', 'services', 'ping', 'proof', 'state', 'ms')
        self.tree = ttk.Treeview(table, columns=columns, show='headings', selectmode='browse')
        headings = {'ip': 'IP adresi', 'hostname': 'DNS adı', 'mac': 'MAC adresi', 'services': 'Açık servisler', 'ping': 'Ping',
                    'proof': 'Bulgu', 'state': 'Durum', 'ms': 'Süre (ms)'}
        widths = {'ip': 120, 'hostname': 140, 'mac': 130, 'services': 170, 'ping': 55, 'proof': 105, 'state': 75, 'ms': 70}
        for col in columns:
            self.tree.heading(col, text=headings[col], command=lambda cc=col: self._sort_by(cc))
            self.tree.column(col, width=widths[col], stretch=col in ('hostname', 'services'), anchor='w')
        self.tree.grid(row=0, column=0, sticky='nsew')
        ys = ttk.Scrollbar(table, orient='vertical', command=self.tree.yview)
        ys.grid(row=0, column=1, sticky='ns')
        xs = ttk.Scrollbar(table, orient='horizontal', command=self.tree.xview)
        xs.grid(row=1, column=0, sticky='ew')
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tree.bind('<Double-Button-1>', self._double_click)
        self.tree.bind('<Button-3>', self._context_menu)
        self.tree.tag_configure('smb', foreground=c['OK_C'])
        self.tree.tag_configure('other', foreground=c['FG'])
        self.tree.tag_configure('candidate', foreground=c['WARN'])
        tools = ttk.Frame(right, style='White.TFrame')
        tools.grid(row=3, column=0, sticky='ew', pady=(8, 0))
        for caption, handler in (('SMB klasörünü aç', self._open_smb), ('Paylaşımları sorgula', self._show_shares),
                                 ('SMB ile bağlan', self._smb_login_dialog), ('Web arayüzü', self._open_web),
                                 ('SSH profili yap', self._ssh_from_selected), ('UNC kopyala', self._copy_unc), ('CSV kaydet', self._export_csv)):
            ttk.Button(tools, text=caption, command=handler).pack(side='left', padx=(0, 5), pady=2)
        self._status_bar(page, 2, columnspan=2)

    # ------------------------------------------------------------------ SuperTools app.pyw'den (tarama, SMB, CSV) — davranis ayni
    def _read_settings(self) -> dict:
        try:
            data = json.loads(self.save_path.read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _load_options(self):
        self.scope_text.delete('1.0', 'end')
        self.scope_text.insert('1.0', self.options.get('scope', '\n'.join(core.DEFAULT_SCOPES)))
        self.workers_var.set(str(self.options.get('workers', '48')))
        self.timeout_var.set(str(self.options.get('timeout_ms', '650')))
        self.extended_var.set(bool(self.options.get('extended', False)))
        self.dns_var.set(bool(self.options.get('dns', False)))
        self.discovery_var.set(bool(self.options.get('discovery', True)))

    def _save_settings(self):
        if not hasattr(self, 'scope_text'):
            return
        data = dict(self.options)                     # SuperTools'un kendi alanlari (gorunum vb.) korunur
        data.update({'version': core.APP_VERSION, 'scope': self.scope_text.get('1.0', 'end-1c'), 'workers': self.workers_var.get(),
                     'timeout_ms': self.timeout_var.get(), 'extended': bool(self.extended_var.get()), 'dns': bool(self.dns_var.get()),
                     'discovery': bool(self.discovery_var.get()), 'appearance': self.appearance})
        try:
            self.save_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.save_path.with_suffix('.tmp')
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(temp, self.save_path)
            self.options = data
        except OSError:
            pass

    def _discover_async(self):
        self.status_var.set('Windows arayüzleri ve rota tablosu sorgulanıyor...')

        def discover():
            self.msg_queue.put(('suggestions', core.discover_windows_networks()))
        threading.Thread(target=discover, name='agfo-dhcp-suggest', daemon=True).start()

    def _add_suggestion(self):
        selected = self.suggestions.curselection()
        if not selected:
            messagebox.showinfo('Ağ önerisi', 'Lütfen listeden bir ağ seçin.')
            return
        cidr = self.network_suggestions[selected[0]][0]
        current = self.scope_text.get('1.0', 'end-1c')
        scopes = [x.strip() for x in current.replace(',', '\n').splitlines()]
        if cidr not in scopes:
            self.scope_text.insert('end', ('\n' if current.strip() else '') + cidr)
        self._save_settings()
        self.status_var.set('Ağ tarama listesine eklendi: ' + cidr)

    def _start_scan(self):
        if self.running:
            return
        try:
            addresses, networks = core.parse_target_ranges(self.scope_text.get('1.0', 'end-1c'))
            workers = int(self.workers_var.get())
            timeout_ms = int(self.timeout_var.get())
            if not 1 <= workers <= 96 or not 100 <= timeout_ms <= 2500:
                raise ValueError('Eşzamanlı işlem 1-96, zaman aşımı 100-2500 ms olmalı.')
        except (ValueError, TypeError) as exc:
            messagebox.showerror('Geçersiz tarama ayarı', str(exc))
            return
        self._save_settings()
        self._clear_results()
        self._log('Tarama başladı: %s IP, %s CIDR, %s işçi, %s ms zaman aşımı.' % (len(addresses), len(networks), workers, timeout_ms))
        self.running = True
        self.cancel.clear()
        self.start_btn.configure(state='disabled')
        self.stop_btn.configure(state='normal')
        self.progress.configure(value=0)
        self.progress_label_var.set('0 / %s IP' % len(addresses))
        self.status_var.set('%s ağda %s IPv4 adresi taranıyor...' % (len(networks), len(addresses)))
        self._start_time = time.monotonic()
        extended, dns, discovery = bool(self.extended_var.get()), bool(self.dns_var.get()), bool(self.discovery_var.get())

        def report(completed, total, found):
            self.msg_queue.put(('progress', (completed, total, found)))

        def work():
            try:
                hints = {}
                if discovery and not self.cancel.is_set():
                    self.msg_queue.put(('log', 'ARP önbelleği ve SSDP/mDNS ile adaylar aranıyor...'))
                    hints = core.discover_neighbor_candidates(addresses, self.cancel)
                    self.msg_queue.put(('log', '%s ağ adayı bulundu. Önce bunlar sınanacak.' % len(hints)))
                found = core.scan_targets(addresses, extended, timeout_ms, workers, self.cancel, report, dns, hints)
                self.msg_queue.put(('done', (found, self.cancel.is_set(), len(addresses))))
            except Exception as exc:
                self.msg_queue.put(('scan_error', str(exc)))
        threading.Thread(target=work, name='agfo-scan-manager', daemon=True).start()

    def _stop_scan(self):
        if self.running:
            self.cancel.set()
            self.stop_btn.configure(state='disabled')
            self.status_var.set('Tarama durduruluyor; devam eden kısa ağ testleri tamamlanıyor...')
        self._log('Kullanıcı taramayı durdurdu.')

    def _poll_queue(self):
        try:
            for _ in range(160):
                kind, payload = self.msg_queue.get_nowait()
                self._handle(kind, payload)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self._poll_queue)

    def _handle(self, kind, payload):
        if kind == 'suggestions':
            self.network_suggestions = payload
            self.suggestions.delete(0, 'end')
            for cidr, source in payload:
                self.suggestions.insert('end', cidr + '  (' + source + ')')
            if not self.running:
                self.status_var.set('%s ağ önerisi hazır. Bir ya da daha fazla ağı tarayabilirsiniz.' % len(payload))
        elif kind == 'log':
            self._log(payload)
        elif kind == 'progress':
            done, total, result = payload
            self.progress.configure(value=done * 100.0 / max(1, total))
            self.progress_label_var.set('%s / %s IP tarandı' % (done, total))
            if result:
                self._insert_result(result)
        elif kind == 'done':
            found, cancelled, total = payload
            self.running = False
            self.start_btn.configure(state='normal')
            self.stop_btn.configure(state='disabled')
            elapsed = time.monotonic() - self._start_time
            verified = sum(1 for r in self.results.values() if r.verified)
            possible = len(self.results) - verified
            self.status_var.set('%s: %s aktif, %s aday (%.1f sn).' % ('Durduruldu' if cancelled else 'Tarama bitti', verified, possible, elapsed))
            self._log('Tarama %s. %d aktif cihaz, %d ARP/multicast adayı (doğrulanmadı). %.1f sn.' %
                      ('durduruldu' if cancelled else 'tamamlandı', verified, possible, elapsed))
            self._sort_by('ip', force_ascending=True)
            self._save_settings()
        elif kind == 'scan_error':
            self.running = False
            self.start_btn.configure(state='normal')
            self.stop_btn.configure(state='disabled')
            self.status_var.set('Tarama hatası: ' + payload)
            self._log('HATA: ' + payload)
            messagebox.showerror('Tarama hatası', payload)
        elif kind == 'shares':
            ip, result, authenticated = payload
            self._text_dialog('SMB paylaşımları: ' + ip, result.text)
            if result.access_denied:
                self.status_var.set('%s: Paylaşım listesi için NAS yetkisi gerekiyor.' % ip)
                if not authenticated and messagebox.askyesno('SMB erişim izni', 'SMB servisi açık fakat paylaşım listesi okunamıyor (hata 5).\n'
                                                             'NAS kullanıcısıyla bağlanmayı denemek ister misiniz?'):
                    self._smb_login_dialog(ip)
        elif kind == 'smb_connected':
            ip, share, result = payload
            self._log('SMB oturumu başarılı: %s\\%s' % (ip, core.validate_smb_share(share) if share else ''))
            self.status_var.set('NAS oturumu açıldı: ' + ip)
            if share:
                self._open_smb_path(ip, share)
            else:
                self.msg_queue.put(('shares', (ip, result, True)))
        elif kind == 'smb_error':
            self._log(payload)
            self.status_var.set('SMB girişi başarısız.')
            messagebox.showwarning('NAS bağlantısı', payload)
        elif kind == 'diagnostic':
            self._text_dialog('Windows ağ / rota bilgileri', payload)
        elif kind == 'supertools_result':
            self._receive_diagnostic(payload)
        elif kind == 'supertools_error':
            self.diag_busy = False
            self.diag_run_btn.configure(state='normal')
            self.diag_status_var.set('Beklenmeyen test hatası')
            self._set_diag_output('HATA: ' + payload)
            self._log('Ağ testi çalışma hatası: ' + payload)
        elif kind == 'ssh_result':
            self._receive_ssh(*payload)
        elif kind == 'ssh_lib_installed':
            self.ssh_connect_busy = False
            success, note = payload
            self.ssh_status_var.set(note)
            if success:
                self.after(80, self._ssh_open_password)
            else:
                messagebox.showwarning('Dahili SSH kütüphanesi', note)
        elif kind == 'ssh_hostkey_prompt':
            self._ssh_handle_hostkey_prompt(payload)
        elif kind == 'ssh_live_connected':
            session_id, transport, label, remembered = payload
            if self.ssh_workspace.set_status(session_id, 'Bağlı', transport=transport, closed=False):
                self.ssh_workspace.append(session_id, '\n[Bağlandı: %s]\n' % label)
                self._ssh_update_remember_status()
                self.ssh_status_var.set('SSH bağlantısı kuruldu: ' + label + (' · Parola geçici şifreli kasaya kaydedildi.' if remembered else ''))
                self._log('Dahili SSH bağlantısı: ' + label + ' (parola kaydedilmedi)')
                record = self.ssh_workspace.get(session_id)
                cmd = self._pending_cmd.pop(getattr(getattr(record, 'profile', None), 'id', None), None)
                if cmd:
                    self.after(700, lambda s=session_id, c=cmd: self._ssh_send_for_session(s, c + '\n'))
                    self._log('Komut oturuma gönderildi: ' + label)
        elif kind == 'ssh_live_data':
            self._ssh_receive_live(*payload)
        elif kind == 'ssh_live_closed':
            if self.ssh_workspace.get(payload):
                self.ssh_workspace.set_status(payload, 'Kapandı', closed=True)
                self.ssh_workspace.append(payload, '\n[Uzak SSH oturumu kapandı.]\n')
        elif kind == 'ssh_vault_warning':
            messagebox.showwarning('SSH parola kasası', payload)
        elif kind == 'ssh_live_error':
            session_id, description, auth_error, retry, profile = payload
            record = self.ssh_workspace.get(session_id)
            if record and not record.cancelled:
                self.ssh_workspace.set_status(session_id, 'Bağlantı hatası', closed=True)
                self.ssh_workspace.append(session_id, '\n[Bağlantı kurulamadı: %s]\n' % description)
                self.ssh_status_var.set(description)
                self._ssh_update_remember_status()
                if auth_error and retry == 0 and messagebox.askyesno('SSH parola hatası', description + '\n\nYeni bir sekmede yeniden denemek ister misiniz?'):
                    self.after(100, lambda p=profile: self._ssh_open_password(failed=True, profile_override=p))
                elif not auth_error:
                    self._pending_cmd.pop(getattr(profile, 'id', None), None)
                    messagebox.showwarning('SSH bağlantısı', description + '\n\nSSH kapalı olabilir: NAS/sunucu ayarlarında SSH hizmetini açın '
                                           've adres/port bilgisini denetleyin.')

    def _result_values(self, r):
        return (r.ip, r.hostname or '-', r.mac or '-', r.services, 'Evet' if r.ping else 'Hayır', r.detected_via or '-',
                'Aktif' if r.verified else 'Aday', str(r.elapsed_ms) if r.verified else '-')

    def _insert_result(self, result):
        previous = self.results.get(result.ip)
        if previous and (previous.verified or not result.verified):
            return
        self.results[result.ip] = result
        tag = 'candidate' if not result.verified else ('smb' if 445 in result.open_ports else 'other')
        if previous:
            self.tree.item(result.ip, values=self._result_values(result), tags=(tag,))
        else:
            self.tree.insert('', 'end', iid=result.ip, values=self._result_values(result), tags=(tag,))
        verified = sum(1 for r in self.results.values() if r.verified)
        self.found_var.set('%s aktif · %s aday' % (verified, len(self.results) - verified))

    def _clear_results(self):
        self.results.clear()
        self.tree.delete(*self.tree.get_children())
        self.found_var.set('0 cihaz')

    def _sort_by(self, column, force_ascending=False):
        rows = list(self.tree.get_children())
        if column == 'ip':
            rows.sort(key=lambda r: int(ipaddress.IPv4Address(r)))
        else:
            index = list(self.tree['columns']).index(column)
            rows.sort(key=lambda r: str(self.tree.item(r, 'values')[index]).lower())
        if not force_ascending and getattr(self, '_last_sort', '') == column:
            rows.reverse()
            self._last_sort = ''
        else:
            self._last_sort = column
        for idx, row in enumerate(rows):
            self.tree.move(row, '', idx)

    def _selected(self):
        current = self.tree.selection() if hasattr(self, 'tree') else ()
        if not current:
            messagebox.showinfo('Cihaz seçimi', 'Önce Ağ tarayıcı sayfasındaki tablodan bir cihaz seçin.')
            return None
        return self.results.get(current[0])

    def _double_click(self, _event=None):
        sel = self._selected()
        if sel:
            (self._launch_smb if 445 in sel.open_ports else self._launch_web)(sel)

    def _context_menu(self, event):
        row = self.tree.identify_row(event.y)
        if not row:
            return
        self.tree.selection_set(row)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label='SMB / Explorer', command=self._open_smb)
        menu.add_command(label='Web yönetimi', command=self._open_web)
        menu.add_command(label='SMB paylaşımlarını sorgula', command=self._show_shares)
        menu.add_command(label='NAS hesabıyla bağlan', command=self._smb_login_dialog)
        menu.add_command(label='SSH profili yap', command=self._ssh_from_selected)
        menu.add_command(label='Ağ testinde kullan (TCP)', command=self._diag_from_selected)
        menu.add_separator()
        menu.add_command(label='IP kopyala', command=self._copy_ip)
        menu.add_command(label='UNC kopyala', command=self._copy_unc)
        menu.tk_popup(event.x_root, event.y_root)

    def _launch_smb(self, result):
        if 445 not in result.open_ports and not messagebox.askyesno('SMB yanıtı yok', 'SMB (445) açık görünmüyor. Yine de Explorer açılsın mı?'):
            return
        target = '\\\\' + result.ip
        try:
            if os.name == 'nt':
                subprocess.Popen(['explorer.exe', target])
            else:
                self.clipboard_clear()
                self.clipboard_append(target)
        except OSError as exc:
            messagebox.showerror('Explorer hatası', str(exc))

    def _open_smb(self):
        item = self._selected()
        if item:
            self._launch_smb(item)

    def _launch_web(self, result):
        ports = result.open_ports
        if 443 in ports:
            url = 'https://' + result.ip
        elif 80 in ports:
            url = 'http://' + result.ip
        else:
            preferred = next((p for p in (8443, 5001, 9443, 9999, 8080, 5000) if p in ports), None)
            if not preferred:
                messagebox.showinfo('Web servisi', 'Bu cihazda web portu tespit edilmedi.')
                return
            url = '%s://%s:%s' % ('https' if preferred in (8443, 5001, 9443) else 'http', result.ip, preferred)
        webbrowser.open(url)

    def _open_web(self):
        item = self._selected()
        if item:
            self._launch_web(item)

    def _copy_ip(self):
        item = self._selected()
        if item:
            self.clipboard_clear()
            self.clipboard_append(item.ip)
            self.status_var.set('IP kopyalandı: ' + item.ip)

    def _copy_unc(self):
        item = self._selected()
        if item:
            self.clipboard_clear()
            self.clipboard_append('\\\\' + item.ip)
            self.status_var.set('UNC kopyalandı: \\\\' + item.ip)

    def _show_shares(self):
        item = self._selected()
        if not item:
            return
        if 445 not in item.open_ports:
            messagebox.showinfo('SMB servisi', 'Bu cihazda 445/TCP açık görünmüyor.')
            return
        self.status_var.set('SMB paylaşımları sorgulanıyor: ' + item.ip)

        def read():
            self.msg_queue.put(('shares', (item.ip, core.query_windows_shares(item.ip), False)))
        threading.Thread(target=read, name='agfo-smb-enum', daemon=True).start()

    def _open_smb_path(self, ip, share):
        target = '\\\\' + ip + '\\' + core.validate_smb_share(share)
        try:
            if os.name == 'nt':
                subprocess.Popen(['explorer.exe', target], **core.hidden_process_options())
            else:
                self.clipboard_clear()
                self.clipboard_append(target)
        except OSError as exc:
            messagebox.showerror('Explorer hatası', str(exc))

    def _smb_login_dialog(self, ip=''):
        if not ip:
            item = self._selected()
            if not item:
                return
            ip = item.ip
            if 445 not in item.open_ports:
                messagebox.showinfo('SMB', 'Seçilen cihazda SMB servisi doğrulanmadı.')
                return
        c = self.colors()
        dlg = tk.Toplevel(self)
        dlg.title('SMB ile bağlan: ' + ip)
        dlg.transient(self.app)
        dlg.resizable(False, False)
        dlg.configure(bg=c['PANEL'])
        pane = ttk.Frame(dlg, style='White.TFrame', padding=20)
        pane.pack(fill='both', expand=True)
        ttk.Label(pane, text='\\\\' + ip, style='Section.TLabel').grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 12))
        entries = []
        for row, (cap, show) in enumerate((('Paylaşım adı', ''), ('NAS kullanıcısı', ''), ('NAS parolası', '*')), start=1):
            ttk.Label(pane, text=cap, style='White.TLabel').grid(row=row, column=0, sticky='w', pady=5)
            e = ttk.Entry(pane, width=32, show=show)
            e.grid(row=row, column=1, sticky='ew', padx=(12, 0), pady=5)
            entries.append(e)
        share_entry, user_entry, pw_entry = entries
        ttk.Label(pane, text='Paylaşım boşsa listeyi sorgular. Liste kapalıysa ör. Backup yazın.\n'
                  'Parola dosyaya ve günlüğe kaydedilmez. Windows oturumu açık kalabilir.', style='Info.TLabel', justify='left').grid(
            row=4, column=0, columnspan=2, sticky='w', pady=(11, 10))
        buttons = ttk.Frame(pane, style='White.TFrame')
        buttons.grid(row=5, column=0, columnspan=2, sticky='e')
        ttk.Button(buttons, text='Vazgeç', command=dlg.destroy).pack(side='left', padx=(0, 8))

        def go():
            share, username, password = share_entry.get().strip(), user_entry.get().strip(), pw_entry.get()
            try:
                if share:
                    core.validate_smb_share(share)
                if not share and not username:
                    messagebox.showinfo('Bilgi gerekli', 'Paylaşım adı ya da NAS kullanıcı adı girin.', parent=dlg)
                    return
            except ValueError as exc:
                messagebox.showerror('SMB paylaşımı', str(exc), parent=dlg)
                return
            pw_entry.delete(0, 'end')
            dlg.destroy()
            if not username:
                self._open_smb_path(ip, share)
                return
            self._log('NAS hesabıyla bağlantı isteniyor: %s (%s)' % (ip, share or 'paylaşım listesi'))

            def connect():
                try:
                    code = core.connect_smb_session(ip, share, username, password)
                    if code:
                        self.msg_queue.put(('smb_error', 'SMB %s: %s' % (ip, core.explain_smb_error(code))))
                        return
                    result = core.query_windows_shares(ip) if not share else core.ShareQueryResult('')
                    self.msg_queue.put(('smb_connected', (ip, share, result)))
                except (OSError, ValueError) as exc:
                    self.msg_queue.put(('smb_error', 'SMB bağlantısı: ' + str(exc)))
            threading.Thread(target=connect, name='agfo-smb-login', daemon=True).start()
        ttk.Button(buttons, text='Bağlan / Aç', style='Blue.TButton', command=go).pack(side='left')
        dlg.bind('<Return>', lambda _e: go())
        dlg.bind('<Escape>', lambda _e: dlg.destroy())
        share_entry.focus_set()
        dlg.grab_set()

    def _text_dialog(self, title, content, size=(800, 500)):
        c = self.colors()
        dlg = tk.Toplevel(self)
        dlg.title(title)
        dlg.geometry('%sx%s' % size)
        dlg.configure(background=c['PANEL'])
        text = scrolledtext.ScrolledText(dlg, wrap='word', bg=c['LOG_BG'], fg=c['LOG_FG'], font=('Consolas', 10), relief='flat', padx=14, pady=14)
        text.insert('1.0', content)
        text.configure(state='disabled')
        text.pack(fill='both', expand=True, padx=13, pady=13)
        dlg._details_text = text
        ttk.Button(dlg, text='Kapat', command=dlg.destroy).pack(pady=(0, 12))
        return dlg

    def _network_details(self):
        self.status_var.set('Windows ağ / rota bilgileri okunuyor...')

        def gather():
            pieces = ['Windows ağ aralıkları / otomatik öneriler', '-' * 55]
            for cidr, source in core.discover_windows_networks():
                pieces.append('%-22s %s' % (cidr, source))
            if os.name == 'nt':
                for command in (['route.exe', 'print', '-4'], ['net.exe', 'use'], ['arp.exe', '-a']):
                    pieces.extend(('', '> ' + ' '.join(command), '-' * 55))
                    try:
                        proc = safe_start_process(command, timeout=7)
                        pieces.append(core.decode_windows_net_output(proc.stdout))
                        if proc.stderr:
                            pieces.append(core.decode_windows_net_output(proc.stderr))
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        pieces.append(str(exc))
            else:
                pieces.append('Rota, ARP ve bağlı sürücü teşhisi yalnız Windows\'ta çalışır.')
            self.msg_queue.put(('diagnostic', '\n'.join(pieces)))
        threading.Thread(target=gather, name='agfo-net-diagnostic', daemon=True).start()

    def _export_csv(self):
        if not self.results:
            messagebox.showinfo('CSV', 'Önce bir tarama yapın.')
            return
        filename = filedialog.asksaveasfilename(title='Bulunan cihazları kaydet', defaultextension='.csv', filetypes=[('CSV', '*.csv')],
                                                initialfile='AGFO-Ag-Tarama-Sonuclari.csv')
        if not filename:
            return
        try:
            with open(filename, 'w', newline='', encoding='utf-8-sig') as handle:
                writer = csv.writer(handle, delimiter=';')
                writer.writerow(('IP', 'DNS adı', 'MAC', 'Durum', 'Ping', 'Servisler', 'Portlar', 'Bulgu', 'Süre (ms)'))
                for item in sorted(self.results.values(), key=lambda r: int(ipaddress.IPv4Address(r.ip))):
                    writer.writerow((item.ip, item.hostname, item.mac, 'Aktif' if item.verified else 'Aday (doğrulanmadı)',
                                     'Evet' if item.ping else 'Hayır', item.services, ','.join(map(str, item.open_ports)),
                                     item.detected_via, item.elapsed_ms if item.verified else ''))
            self.status_var.set('CSV kaydedildi: ' + filename)
        except OSError as exc:
            messagebox.showerror('CSV hatası', str(exc))
