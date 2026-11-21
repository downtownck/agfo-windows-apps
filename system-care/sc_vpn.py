# -*- coding: utf-8 -*-
"""AGFO System Care — VPN sayfasi (WireGuard / VPN Gate / Tailscale). App sinifinin parcasi (mixin); paylasilan adlar sc_base'den gelir."""
from sc_base import *  # noqa: F401,F403


class VpnPage:
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
        self.btn(tsb, 'Hetzner komutunu kopyala (yabancı IP)', lambda: self.ts_copy_script('hetzner'), 'ghost', action=False)
        self.btn(tsb, 'netcup komutunu kopyala (yabancı IP)', lambda: self.ts_copy_script('netcup'), 'ghost', action=False)
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
            r = subprocess.run(ps_cmd('vpn-status'), env=child_env(['powershell.exe']), capture_output=True, text=True, encoding='utf-8', errors='replace',
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
                   'Türkiye\'de yabancı IP: "Hetzner / netcup komutunu kopyala" ile aldığınız komutu ilgili sunucuda (AGFO Root Terminal / SSH) çalıştırın '
                   '(çıkış adları hetzner-cikis, netcup-cikis). '
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
                'Yurt dışı — netcup (yabancı IP)' if 'netcup' in n['name'].lower() else
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

    def ts_copy_script(self, key='hetzner'):
        name, host, what = vpn.EXIT_NODE_SERVERS[key]
        script = vpn.linux_exit_node_script(host)
        title = '%s — %s çıkışı' % (name, what)
        self.clipboard_clear()
        self.clipboard_append(script)
        if messagebox.askyesno(title, 'Komut panoya kopyalandı.\n\nKayıtlı bir SSH sunucusunda (%s) System Care\'den şimdi çalıştırılsın mı?\n\n'
                               'Hayır: komutu kendiniz (AGFO Root Terminal / SSH) çalıştırırsınız.' % name):
            if self.net.run_on_server(script, '%s — çıkış noktası' % name,
                                      'Listeden %s sunucusunu seçin. Bittikten sonra "Yönetim panelini aç" > sunucu > Edit route settings > '
                                      '"Use as exit node" işaretleyin.' % name):
                return
        self.write('%s (Linux) sunucusu için komut panoya kopyalandı. Sunucuda root olarak çalıştırın; çıkan bağlantıyla giriş yapın, '
                   'sonra yönetim panelinde "%s" makinesini çıkış noktası olarak onaylayın.\n' % (name, host))
        messagebox.showinfo(title, '1) %s sunucusunda root olarak (AGFO Root Terminal ya da SSH) panodaki komutu çalıştırın.\n'
                            '2) Tailscale sunucuda yeni kuruluyorsa ekranda çıkan login.tailscale.com bağlantısını açıp aynı hesapla giriş yapın '
                            '(zaten bağlıysa komut yalnızca çıkış noktalığını açar; ad ve DNS ayarı değişmez).\n'
                            '3) "Yönetim panelini aç" > sunucu (%s ya da mevcut adı) > Edit route settings > "Use as exit node" işaretleyin.\n\n'
                            'CyberPanel sunucularında firewalld çalışıyorsa komut, Tailscale belgesindeki gibi maskelemeyi (masquerade) de açar; '
                            'web siteleri ve DNS ayarı etkilenmez.\n\nKomut:\n%s' % (name, host, script))

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


register_palette_module(globals())
