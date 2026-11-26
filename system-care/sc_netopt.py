# -*- coding: utf-8 -*-
"""AGFO System Care — 4.4 Ag: "Internet hizi" (otomatik tarama + secilip uygulanan oneriler) ve "DNS yonetimi" sayfalari (mixin).

DNS ve Delivery Optimization degisiklikleri Ince ayarlar motoruyla (tweak-write) yapilir: onceki deger kaydedilir ve
Ince ayarlar > Gecmis'ten birebir geri alinir. Baglanti hizi (*SpeedDuplex) degisikligi ayri islemdir; onceki deger gunluge yazilir."""
from sc_base import *  # noqa: F401,F403
import care_netopt as netopt  # noqa: E402

RISK_TAG = {'güvenli': (), 'dikkat': ('risky',), 'tamam': ('st_ok',), 'bilgi': ('muted',)}


class NetOptPage:
    def _netopt_on_tab(self, _e=None):
        try:
            title = self.tabs.tab(self.tabs.current, 'text')
        except Exception:
            return
        if IS_WIN and not self.busy and title == 'DNS yönetimi' and not getattr(self, 'dn_adapters', True):
            self.dn_refresh()

    # ================================================================== İnternet hızı
    def _tab_netspeed(self, f):
        self.ns_records, self.ns_findings = [], []
        self.label(f, 'Bilinen "internet hızlandırma / ping düşürme" adımlarını otomatik denetler: en hızlı DNS (ölçerek), ağ kartının hız / çift '
                      'yön ayarı, Windows Update\'in internet üzerinden paylaşımı, Wi-Fi sinyali, modem ve internet gecikmesi, başlangıç uygulamaları '
                      've interneti kullanan uygulamalar. Önerileri işaretleyip "Seçilenleri uygula"ya basın; DNS ve paylaşım ayarı İnce ayarlar > '
                      'Geçmiş\'ten geri alınır. Windows Update hizmetini kapatmak önerilmez (güvenlik yamaları gelmez).',
                   wraplength=int(880 * self.scale)).pack(fill='x', padx=16, pady=(12, 6))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16, pady=(0, 6))
        self.btn(bar, 'Tara', self.ns_scan, 'go')
        self.btn(bar, 'Seçilenleri uygula', self.ns_apply, 'normal')
        self.btn(bar, 'Yalnız güvenliler', lambda: self.ns_tree.set_all(True, lambda i: (self.ns_tree.payload.get(i) or {}).get('risk') == 'güvenli'
                                                                       and bool((self.ns_tree.payload.get(i) or {}).get('action'))), 'ghost', action=False)
        self.btn(bar, 'DNS yönetimi', lambda: self.tabs.select('DNS yönetimi'), 'ghost', action=False)
        self.btn(bar, 'Geçmiş / geri al', self.tw_history, 'ghost', action=False)
        self.ns_state = tk.StringVar(value='Henüz taranmadı. "Tara" yaklaşık 20-40 saniye sürer (DNS ve ping ölçümü).')
        tk.Label(f, textvariable=self.ns_state, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold'), anchor='w').pack(fill='x', padx=16)
        self.ns_tree = CheckTree(f, [('cur', 'Şu an', 260, 'w'), ('risk', 'Risk', 70, 'w'), ('adv', 'Öneri', 520, 'w')],
                                 first=('Denetim', int(260 * self.scale)), height=8)
        self.ns_tree.pack(fill='both', expand=True, padx=16, pady=6)
        self.ns_tree.tree.bind('<<TreeviewSelect>>', lambda _e: self._ns_show_detail(), add=True)
        self.ns_detail = tk.Text(f, height=4, bg=LOG_BG, fg=LOG_FG, relief='flat', font=('Segoe UI', 9), wrap='word', padx=8, pady=6)
        self.ns_detail.pack(fill='x', padx=16, pady=(0, 12))
        self.ns_detail.configure(state='disabled')

    def _ns_show_detail(self):
        sel = self.ns_tree.tree.selection()
        p = self.ns_tree.payload.get(sel[0]) if sel else None
        txt = ''
        if p:
            txt = '%s\nŞu an: %s\nÖneri: %s' % (p['title'], p.get('current', ''), p.get('advice', ''))
            if p.get('detail'):
                txt += '\n' + p['detail']
        self.ns_detail.configure(state='normal'); self.ns_detail.delete('1.0', 'end'); self.ns_detail.insert('1.0', txt)
        self.ns_detail.configure(state='disabled')

    def ns_scan(self):
        if not IS_WIN:
            messagebox.showinfo('İnternet hızı', 'Bu tarama Windows\'ta çalışır.'); return
        self.ns_state.set('Taranıyor… (DNS sunucuları ve gecikme ölçülüyor)')
        box = {}

        def got_net(job):
            box['net'] = job.data

        def got_start(job):
            try:
                self._st_set(job.data)
            except Exception:
                pass
            self._ns_render(box.get('net') or [], getattr(self, 'st_records', None))
        self.start([Job('İnternet hızı taraması', cmd=ps_cmd('net-scan'), on_done=got_net, cancel_ok=False),
                    Job('Başlangıç uygulamaları', cmd=ps_cmd('startup-list'), on_done=got_start, show_output=False, cancel_ok=False)])

    def _ns_render(self, records, startups=None):
        self.ns_records = list(records or [])
        self.ns_findings = netopt.analyze(self.ns_records, startups)
        t = self.ns_tree
        t.clear()
        for i, fd in enumerate(self.ns_findings):
            t.add('n%d' % i, fd['title'], values=(fd.get('current', ''), fd.get('risk', ''), fd.get('advice', '')),
                  tags=RISK_TAG.get(fd.get('risk'), ()), payload=fd, checked=bool(fd.get('checked')), checkable=bool(fd.get('action')))
        todo = sum(1 for fd in self.ns_findings if fd.get('action') and fd.get('risk') in ('güvenli', 'dikkat'))
        self.ns_state.set('%d denetim · %d uygulanabilir öneri. Satıra tıklayınca ayrıntı aşağıda görünür.' % (len(self.ns_findings), todo))
        self._ns_show_detail()

    def ns_apply(self):
        sel = [p for p in self.ns_tree.checked_payloads() if p and p.get('action')]
        if not sel:
            messagebox.showinfo('İnternet hızı', 'Uygulanacak öneri işaretlenmedi (önce "Tara").'); return
        lines = ['• %s: %s' % (p['title'], p['advice'].split('.')[0]) for p in sel]
        if not messagebox.askyesno('Önerileri uygula', '%d öneri uygulanacak:\n%s\n\nDNS ve paylaşım ayarının önceki değeri kaydedilir (İnce ayarlar > Geçmiş). '
                                   'Yönetici onayı (UAC) istenebilir. Devam?' % (len(sel), '\n'.join(lines))):
            return
        plan, names = [], []
        for p in sel:
            a = p['action']
            if a['kind'] == 'dns':
                plan += tweaks.dns_plan(a['adapters'], a['servers'])
                names.append('DNS: ' + a['label'])
            elif a['kind'] == 'do':
                item = tweaks.item_by_id().get('tweak-delivery-opt')
                if item:
                    plan += tweaks.build_write_plan([item], 'apply')
                    names.append('Windows Update P2P kapat')
        for n, op in enumerate(plan):
            op['ref'] = n
        nics = [p['action'] for p in sel if p['action']['kind'] == 'nic']
        opens = [p['action'] for p in sel if p['action']['kind'] in ('page', 'tool', 'settings')]
        nic_jobs = []
        if nics:
            for a in nics:
                self.write('Bağlantı hızı: %s önceki değer %s → otomatik (%s). Geri almak için Aygıt Yöneticisi > ağ kartı > Gelişmiş > Speed & Duplex.\n'
                           % (a['alias'], a.get('old'), a['value']))
            import care_procs as pr
            items = [{'alias': a['alias'], 'value': a['value']} for a in nics]
            nic_jobs = [Job('Bağlantı hızı: otomatik', cmd=ps_cmd('nic-speed-set', ItemsB64=pr.b64_items(items)), cancel_ok=False, admin=True)]
        for a in opens:
            self._ns_open(a)
        if plan:
            errs = tweaks.validate_ops(plan)
            if errs:
                messagebox.showerror('Plan hatası', '\n'.join(errs[:6])); return
            self._tw_run(plan, 'İnternet hızı: ' + ', '.join(names), after=(lambda: self.start(nic_jobs)) if nic_jobs else None)
        elif nic_jobs:
            self.start(nic_jobs)

    def _ns_open(self, a):
        if a['kind'] == 'page':
            try:
                self.tabs.select(a['page'])
            except Exception:
                pass
        elif a['kind'] == 'tool' and IS_WIN:
            try:
                subprocess.Popen([os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'resmon.exe')])
            except OSError as e:
                self.write('Kaynak İzleyicisi açılamadı: %s\n' % e)
        elif a['kind'] == 'settings' and IS_WIN and str(a.get('uri', '')).startswith('ms-settings:'):
            try:
                os.startfile(a['uri'])
            except OSError as e:
                self.write('Ayar açılamadı: %s\n' % e)

    # ================================================================== DNS yönetimi
    def _tab_dns(self, f):
        self.dn_adapters, self.dn_bench = [], []
        self.label(f, 'Bağlı ağ bağdaştırıcılarının DNS sunucularını görün, hız testiyle karşılaştırın ve seçtiğiniz bağdaştırıcılara uygulayın. '
                      'Değişiklikler İnce ayarlar > Geçmiş\'e kaydedilir, oradan birebir geri alınır. VPN / Tailscale bağdaştırıcılarına dokunulmaz.',
                   wraplength=int(880 * self.scale)).pack(fill='x', padx=16, pady=(12, 6))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16, pady=(0, 4))
        self.btn(bar, 'Yenile', self.dn_refresh, 'normal')
        self.btn(bar, 'Hız testi', self.dn_bench_run, 'go')
        self.btn(bar, 'DNS önbelleğini temizle', lambda: self.start([Job('DNS önbelleğini temizle', cmd=ps_cmd('dns-flush'), cancel_ok=False)]), 'ghost')
        self.btn(bar, 'Geçmiş / geri al', self.tw_history, 'ghost', action=False)
        tk.Label(f, text='Bağdaştırıcılar (uygulanacakları işaretleyin)', fg=FG, bg=PANEL, font=('Segoe UI', 10, 'bold'), anchor='w').pack(fill='x', padx=16, pady=(6, 0))
        self.dn_tree = CheckTree(f, [('mode', 'Ayar', 120, 'w'), ('cur', 'Geçerli DNS', 330, 'w'), ('desc', 'Kart', 380, 'w')],
                                 first=('Bağdaştırıcı', int(220 * self.scale)), height=3)
        self.dn_tree.pack(fill='x', padx=16, pady=4)
        row = tk.Frame(f, bg=PANEL2, padx=10, pady=8); row.pack(fill='x', padx=16, pady=6)
        tk.Label(row, text='Yeni DNS', fg=ACCENT, bg=PANEL2, font=('Segoe UI', 9, 'bold')).pack(side='left')
        self.dn_choice = ttk.Combobox(row, state='readonly', width=30, values=[p[1] for p in tweaks.DNS_PRESETS] + ['Özel adresler…'])
        self.dn_choice.current(1); self.dn_choice.pack(side='left', padx=6)
        self.dn_custom = tk.StringVar()
        ttk.Entry(row, textvariable=self.dn_custom, width=18).pack(side='left', padx=(0, 6))
        row2 = tk.Frame(f, bg=PANEL); row2.pack(fill='x', padx=16, pady=(0, 4))
        self.mkbtn(row2, 'Seçili bağdaştırıcılara uygula', self.dn_apply, 'go', small=True).pack(side='left')
        self.mkbtn(row2, 'Otomatik\'e (DHCP / modem) döndür', lambda: self.dn_apply(dhcp=True), 'ghost', small=True).pack(side='left', padx=8)
        tk.Label(f, text='Hız testi', fg=FG, bg=PANEL, font=('Segoe UI', 10, 'bold'), anchor='w').pack(fill='x', padx=16, pady=(6, 0))
        tk.Label(f, text='Çözümleme = bir sitenin adresini bulma süresi (ortanca, 6 site); DNS seçiminde asıl ölçü budur, düşük olan iyidir. '
                         'Ping yalnız sunucuya ulaşma süresidir. Başarısız 0 olmalı. 3-5 ms fark hissedilmez: "en iyi grup"taki herhangi biri olur; '
                         'arada seçerken zararlı alan adı engeli (Quad9, Cloudflare 1.1.1.2) ya da gizlilik gibi özelliklere bakın.',
                 fg=MUTED, bg=PANEL, font=('Segoe UI', 9), anchor='w', justify='left', wraplength=int(880 * self.scale)).pack(fill='x', padx=16)
        self.dn_btree = CheckTree(f, [('prov', 'Sağlayıcı', 330, 'w'), ('ms', 'Çözümleme', 110, 'e'), ('ping', 'Ping', 80, 'e'), ('fail', 'Başarısız', 80, 'e'),
                                      ('verdict', 'Değerlendirme', 170, 'w')],
                                  first=('Sunucu', int(140 * self.scale)), height=7)
        self.dn_btree.pack(fill='both', expand=True, padx=16, pady=4)
        self.dn_btree.tree.bind('<Double-1>', lambda _e: self._dn_pick_from_bench(), add=True)
        self.dn_state = tk.StringVar(value='"Yenile" bağdaştırıcıları, "Hız testi" DNS sunucularını ölçer. Test satırına çift tıklayınca o DNS seçilir. '
                                         'Özel adres için listeden "Özel adresler…" seçip yan kutuya yazın (ör. 1.1.1.1, 8.8.8.8).')
        tk.Label(f, textvariable=self.dn_state, fg=MUTED, bg=PANEL, font=('Segoe UI', 9), anchor='w', justify='left',
                 wraplength=int(880 * self.scale)).pack(fill='x', padx=16, pady=(0, 12))

    def dn_refresh(self, then=None):
        def done(job):
            self.dn_adapters = [d for d in job.data if d.get('type') == 'dns-adapter']
            t = self.dn_tree
            t.clear()
            for i, a in enumerate(self.dn_adapters):
                mode = 'elle' if a.get('servers') else 'otomatik (DHCP)'
                cur = ', '.join(netopt.describe_server(s) for s in a.get('current') or []) or '—'
                t.add('d%d' % i, a['alias'], values=(mode, cur, a.get('desc', '')), payload=a, checked=True)
            self.dn_state.set('%d bağlı bağdaştırıcı.' % len(self.dn_adapters) if self.dn_adapters else 'Bağlı fiziksel bağdaştırıcı bulunamadı.')
            if then:
                then()
        self.start([Job('DNS bağdaştırıcıları', cmd=ps_cmd('dns-list'), on_done=done, cancel_ok=False)])

    def dn_bench_run(self):
        def go():
            servers = netopt.bench_servers([{'dns_current': a.get('current')} for a in self.dn_adapters])
            import care_procs as pr
            self.dn_state.set('Ölçülüyor: %s' % ', '.join(servers))
            self.start([Job('DNS hız testi', cmd=ps_cmd('dns-bench', ItemsB64=pr.b64_items([{'server': s} for s in servers])),
                            on_done=lambda j: self._dn_render_bench(j.data), cancel_ok=False)])
        if self.dn_adapters:
            go()
        else:
            self.dn_refresh(then=go)

    def _dn_render_bench(self, records):
        self.dn_bench = netopt.dns_ranking(records)
        t = self.dn_btree
        t.clear()
        best_ms = next((p['median'] for p in self.dn_bench if netopt.probe_ok(p)), None)
        for i, p in enumerate(self.dn_bench):
            ok = netopt.probe_ok(p)
            v = netopt.verdict(p, best_ms)
            t.add('b%d' % i, p['server'], values=(netopt.describe_server(p['server']), ('%.0f ms' % p['median']) if p.get('median') is not None else '—',
                                                  ('%.0f ms' % p['ping']) if p.get('ping') is not None else '—', str(p.get('fail', 0)), v),
                  tags=('st_ok',) if v == 'en iyi grup' else (() if ok else ('muted',)), payload=p, checkable=False)
        best = next((p for p in self.dn_bench if netopt.probe_ok(p)), None)
        if best:
            pr_ = netopt.preset_for(best['server'])
            if pr_:
                self.dn_choice.set(pr_[1])
            else:
                self.dn_choice.set('Özel adresler…'); self.dn_custom.set(best['server'])
            self.dn_state.set('En hızlı: %s (%.0f ms) — "Yeni DNS" kutusuna seçildi. Uygulamak için "Seçili bağdaştırıcılara uygula".'
                              % (netopt.describe_server(best['server']), best['median']))
        else:
            self.dn_state.set('DNS testi yanıt alamadı; internet bağlantısını denetleyin.')

    def _dn_pick_from_bench(self):
        sel = self.dn_btree.tree.selection()
        p = self.dn_btree.payload.get(sel[0]) if sel else None
        if not p:
            return
        pr_ = netopt.preset_for(p['server'])
        if pr_:
            self.dn_choice.set(pr_[1])
        else:
            self.dn_choice.set('Özel adresler…'); self.dn_custom.set(p['server'])

    def dn_apply(self, dhcp=False):
        targets = [a for a in self.dn_tree.checked_payloads() if a]
        if not targets:
            messagebox.showinfo('DNS yönetimi', 'Önce "Yenile" ile bağdaştırıcıları getirip uygulanacakları işaretleyin.'); return
        if dhcp:
            servers, label = [], 'Otomatik (DHCP / modem)'
        else:
            choice = self.dn_choice.get()
            preset = next((p for p in tweaks.DNS_PRESETS if p[1] == choice), None)
            if preset:
                servers, label = list(preset[2]), choice
            else:
                servers = tweaks.valid_ipv4_list(self.dn_custom.get())
                if not servers:
                    messagebox.showerror('DNS yönetimi', 'Özel adresleri yan kutuya IPv4 olarak yazın (ör. 1.1.1.1, 8.8.8.8; en fazla 4).'); return
                label = ', '.join(servers)
        if not messagebox.askyesno('DNS yönetimi', '%s bağdaştırıcılarında DNS "%s" yapılacak. Önceki ayar kaydedilir (İnce ayarlar > Geçmiş). Devam?'
                                   % (', '.join(a['alias'] for a in targets), label)):
            return
        plan = tweaks.dns_plan(targets, servers)
        errs = tweaks.validate_ops(plan)
        if errs:
            messagebox.showerror('Plan hatası', '\n'.join(errs[:6])); return
        self._tw_run(plan, 'DNS: ' + label, after=lambda: self.dn_refresh())


register_palette_module(globals())
