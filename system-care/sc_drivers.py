# -*- coding: utf-8 -*-
"""AGFO System Care — Suruculer sayfasi (SDIO tarzi gorunum). App sinifinin parcasi (mixin); paylasilan adlar sc_base'den gelir."""
from sc_base import *  # noqa: F401,F403


class DriversPage:
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


register_palette_module(globals())
