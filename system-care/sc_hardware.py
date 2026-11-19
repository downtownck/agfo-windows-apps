# -*- coding: utf-8 -*-
"""AGFO System Care — 4.0 Genel bakis ve Donanim sayfalari (Sistem ozeti, Aygit yoneticisi, Disk sagligi).
App sinifinin parcasi (mixin); paylasilan adlar sc_base'den, ayristirma/rapor care_hw'den gelir."""
from sc_base import *  # noqa: F401,F403
import care_hw as hw  # noqa: E402

STATE_COLORS = lambda: {'ok': OK_C, 'warn': WARN, 'bad': BAD_C, 'info': MUTED}  # noqa: E731  (tema degisince guncel jetonlar)
CRITICAL_PNP = {'System', 'Processor', 'DiskDrive', 'SCSIAdapter', 'HDC', 'Computer', 'Volume', 'Firmware', 'SecurityDevices'}


class HardwarePage:
    # ------------------------------------------------------------------ GENEL BAKIS
    def _tab_overview(self, f):
        head = tk.Frame(f, bg=PANEL); head.pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(head, text='Genel bakış', fg=FG, bg=PANEL, font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.ov_score = tk.StringVar(value='')
        self.ov_score_lbl = tk.Label(head, textvariable=self.ov_score, fg=ACCENT, bg=PANEL2, font=('Segoe UI', 10, 'bold'), padx=10, pady=3)
        self.ov_score_lbl.pack(side='left', padx=(12, 0))
        self.ov_when = tk.StringVar(value='')
        tk.Label(head, textvariable=self.ov_when, fg=MUTED, bg=PANEL, font=('Segoe UI', 9)).pack(side='left', padx=(10, 0))
        self.label(f, 'Bilgisayarın durumu tek ekranda: diskler, aygıtlar, güvenlik, güncellemeler, bellek. Kırmızı = hemen bakın, turuncu = dikkat. '
                      'Karttaki düğme ilgili sayfayı ya da Windows ayarını açar. Okuma salt okunurdur, hiçbir şeyi değiştirmez.',
                   wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(2, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Yenile', self.ov_refresh, 'go')
        self.btn(bar, 'Donanım raporunu kaydet…', self.hw_save_report, 'ghost', action=False)
        self.ov_grid = tk.Frame(f, bg=PANEL); self.ov_grid.pack(fill='both', expand=True, padx=16, pady=8)
        self.ov_records, self.ov_loaded, self.ov_cards = [], False, []
        tk.Label(self.ov_grid, text='Durum henüz okunmadı. "Yenile"ye basın.', fg=MUTED, bg=PANEL, font=('Segoe UI', 10)).grid(row=0, column=0, sticky='w')
        self.theme_hooks.append(lambda: self._ov_render(self.ov_records) if self.ov_loaded else None)

    def _hw_on_tab(self, _e=None):
        """Genel bakis ilk acildiginda (Windows'ta) kendiliginden okunur; baska is surerken beklemez."""
        try:
            title = self.tabs.tab(self.tabs.current, 'text')
        except Exception:
            return
        if title == 'Genel bakış' and not self.ov_loaded and IS_WIN and not self.busy:
            self.ov_refresh(quiet=True)

    def ov_refresh(self, quiet=False):
        def done(job):
            if job.data:
                self._ov_render(job.data)
        self.start([Job('Genel bakış', cmd=ps_cmd('overview'), on_done=done, show_output=False)], quiet=quiet)

    def _ov_extra_cards(self):
        out = []
        try:
            v = self.vpn_status.get()
            if v:
                out.append({'key': 'vpn', 'state': 'ok' if v.startswith('BAĞLI') else 'info', 'value': v.split(' — ')[0][:60], 'detail': ''})
        except (AttributeError, tk.TclError):
            pass
        return out

    def _ov_action(self, key):
        pages = {'disks': 'Disk sağlığı', 'devices': 'Aygıt yöneticisi', 'vpn': 'VPN'}
        if key.startswith('volume:'):
            return 'Temizle', lambda: self.tabs.select('Temizlik')
        if key in pages:
            return 'Aç', lambda p=pages[key]: self.tabs.select(p)
        uris = {'defender': 'windowsdefender:', 'winupdate': 'ms-settings:windowsupdate', 'firewall': 'ms-settings:windowsdefender',
                'bitlocker': 'ms-settings:deviceencryption'}
        if key in uris:
            return 'Ayarlar', lambda u=uris[key]: self._ov_open(u)
        return None, None

    def _ov_open(self, uri):
        if IS_WIN:
            try:
                os.startfile(uri)
            except OSError as e:
                messagebox.showerror('Windows ayarı', str(e))

    def _ov_render(self, records):
        self.ov_records, self.ov_loaded = list(records), True
        cards = hw.overview_cards(records, self._ov_extra_cards())
        self.ov_cards = cards
        for w in self.ov_grid.winfo_children():
            w.destroy()
        colors = STATE_COLORS()
        cols = 3
        for c in range(cols):
            self.ov_grid.columnconfigure(c, weight=1, uniform='ov')
        for i, card in enumerate(cards):
            box = tk.Frame(self.ov_grid, bg=PANEL2, padx=0, pady=0)
            box.grid(row=i // cols, column=i % cols, sticky='nsew', padx=(0, 8), pady=(0, 8))
            tk.Frame(box, bg=colors.get(card['state'], MUTED), width=5).pack(side='left', fill='y')
            inner = tk.Frame(box, bg=PANEL2, padx=10, pady=8); inner.pack(side='left', fill='both', expand=True)
            tk.Label(inner, text=card['title'], fg=MUTED, bg=PANEL2, font=('Segoe UI', 9), anchor='w').pack(fill='x')
            tk.Label(inner, text=card['value'] or '-', fg=colors.get(card['state'], FG) if card['state'] in ('bad', 'warn') else FG, bg=PANEL2,
                     font=('Segoe UI', 11, 'bold'), anchor='w', justify='left', wraplength=int(300 * self.scale)).pack(fill='x')
            if card.get('detail'):
                tk.Label(inner, text=card['detail'], fg=MUTED, bg=PANEL2, font=('Segoe UI', 8), anchor='w', justify='left',
                         wraplength=int(300 * self.scale)).pack(fill='x')
            cap, fn = self._ov_action(card['key'])
            if cap:
                self.mkbtn(inner, cap, fn, 'ghost', small=True).pack(anchor='w', pady=(6, 0))
        score = hw.overview_score(cards)
        self.ov_score.set('Sağlık puanı: %d / 100' % score)
        self.ov_score_lbl.configure(fg=OK_C if score >= 85 else WARN if score >= 60 else BAD_C)
        self.ov_when.set('Son okuma: ' + datetime.datetime.now().strftime('%H:%M'))

    # ------------------------------------------------------------------ SISTEM OZETI (Everest tarzi)
    def _tab_hwinfo(self, f):
        head = tk.Frame(f, bg=PANEL); head.pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(head, text='Sistem özeti', fg=FG, bg=PANEL, font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.hw_state = tk.StringVar(value='')
        tk.Label(head, textvariable=self.hw_state, fg=MUTED, bg=PANEL, font=('Segoe UI', 9)).pack(side='left', padx=(12, 0))
        self.label(f, 'İşlemci, anakart/BIOS, bellek modülleri, ekran kartı, diskler, ağ, ses, monitör ve pil. Bilgiler Windows\'un kendi WMI verisinden '
                      'okunur; sürücü kurulmaz, yönetici gerekmez. Sıcaklık ve fan hızı için "Sensörleri etkinleştir" (isteğe bağlı).',
                   wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(2, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Oku', self.hw_scan, 'go')
        self.btn(bar, 'Raporu kaydet (HTML)…', self.hw_save_report, 'ghost', action=False)
        self.btn(bar, 'Metni kopyala', self.hw_copy_report, 'ghost', action=False)
        self.btn(bar, 'Sensörleri oku', self.hw_read_sensors, 'ghost')
        self.btn(bar, 'Sensörleri etkinleştir…', self.hw_enable_sensors, 'ghost')
        tf = ttk.Frame(f, style='Card.TFrame'); tf.pack(fill='both', expand=True, padx=16, pady=8)
        self.hw_tree = ttk.Treeview(tf, columns=('val',), show='tree headings', selectmode='browse')
        self.hw_tree.heading('#0', text='Özellik'); self.hw_tree.column('#0', width=int(300 * self.scale), stretch=False)
        self.hw_tree.heading('val', text='Değer'); self.hw_tree.column('val', width=int(700 * self.scale), stretch=True)
        ys = ttk.Scrollbar(tf, orient='vertical', command=self.hw_tree.yview)
        self.hw_tree.configure(yscrollcommand=ys.set)
        self.hw_tree.pack(side='left', fill='both', expand=True); ys.pack(side='right', fill='y')
        self.hw_tree.tag_configure('sec', font=('Segoe UI', 10, 'bold'))
        self.hw_records, self.hw_sensors = [], {}

    def hw_scan(self, then=None):
        def done(job):
            if job.data:
                self._hw_render(job.data)
            if then:
                then()
        self.start([Job('Donanım bilgisi', cmd=ps_cmd('hw-inventory'), on_done=done, show_output=False)])

    def _hw_render(self, records):
        self.hw_records = list(records)
        t = self.hw_tree
        t.delete(*t.get_children())
        sections = hw.inventory_sections(records)
        for n, (title, rows) in enumerate(sections):
            sid = 's%d' % n
            t.insert('', 'end', iid=sid, text=title, values=('',), open=True, tags=('sec',))
            for m, (k, v) in enumerate(rows):
                t.insert(sid, 'end', iid='%s_%d' % (sid, m), text=k, values=(v,))
        if self.hw_sensors:
            self._hw_render_sensors()
        self.hw_state.set('%d bölüm · %s' % (len(sections), datetime.datetime.now().strftime('%H:%M')))

    def _hw_render_sensors(self):
        t = self.hw_tree
        if t.exists('sens'):
            t.delete('sens')
        t.insert('', 0, iid='sens', text='Sensörler (LibreHardwareMonitor)', values=('',), open=True, tags=('sec',))
        for i, (hwname, items) in enumerate(self.hw_sensors.items()):
            hid = 'sens_%d' % i
            t.insert('sens', 'end', iid=hid, text=hwname, values=('',), open=True)
            for j, (name, st, txt) in enumerate(items):
                t.insert(hid, 'end', iid='%s_%d' % (hid, j), text='%s (%s)' % (name, st), values=(txt,))

    def hw_read_sensors(self):
        def done(job):
            if job.code == 3 or not job.data:
                messagebox.showinfo('Sensörler', 'Sensör verisi okunamadı. LibreHardwareMonitor çalışıyor olmalı (sistem tepsisinde açık kalabilir). '
                                    'Kurulu değilse "Sensörleri etkinleştir…" ile kurun.')
                return
            self.hw_sensors = hw.parse_sensors(job.data)
            self._hw_render_sensors()
        self.start([Job('Sensörler', cmd=ps_cmd('sensors'), on_done=done, show_output=False)])

    def hw_enable_sensors(self):
        if not messagebox.askyesno('Sensörleri etkinleştir', 'Sıcaklık, fan hızı ve voltaj için açık kaynak LibreHardwareMonitor (WinGet) kurulacak.\n\n'
                                   'Bilmeniz gerekenler:\n'
                                   '• Donanıma erişmek için PawnIO çekirdek sürücüsünü kurmanızı isteyebilir. Eski WinRing0 sürücüsünü Microsoft Defender '
                                   'güvenlik açığı nedeniyle engelliyor; PawnIO onun güvenli yerine geçen sürücüdür.\n'
                                   '• Bazı çok oyunculu oyunların hile önleme sistemleri PawnIO yüklü bilgisayarlarda sorun çıkarabiliyor.\n'
                                   '• System Care sensörleri yalnızca okur; LibreHardwareMonitor açıkken "Sensörleri oku" çalışır.\n\n'
                                   'Kurulsun mu?'):
            return
        wg = self.engines.get('winget', {}).get('path') or core.find_winget()
        if not wg:
            messagebox.showerror('WinGet yok', 'WinGet bulunamadı.'); return

        def done(job):
            if job.code == 0:
                messagebox.showinfo('Sensörler', 'LibreHardwareMonitor kuruldu. Başlat menüsünden açın (yönetici olarak), sonra burada "Sensörleri oku"ya basın.')
        self.start([Job('Kur: LibreHardwareMonitor', cmd=core.winget_install_cmd(wg, hw.LHM_PKG), on_done=done, cancel_ok=False)])

    def _hw_report_parts(self):
        groups = hw.pnp_groups(getattr(self, 'dm_records', []), only_problems=True)
        return hw.inventory_sections(self.hw_records), getattr(self, 'dh_records', []), groups, getattr(self, 'ov_cards', [])

    def hw_save_report(self):
        if not self.hw_records:
            if messagebox.askyesno('Donanım raporu', 'Önce donanım bilgisinin okunması gerekiyor. Şimdi okunsun mu?'):
                self.hw_scan(then=self.hw_save_report)
            return
        path = filedialog.asksaveasfilename(title='Donanım raporunu kaydet', defaultextension='.html', initialfile='AGFO-Donanim-Raporu.html',
                                            filetypes=[('HTML', '*.html'), ('Metin', '*.txt')])
        if not path:
            return
        parts = self._hw_report_parts()
        text = hw.report_text(*parts) if path.lower().endswith('.txt') else hw.report_html(*parts)
        try:
            pathlib.Path(path).write_text(text, encoding='utf-8')
        except OSError as e:
            messagebox.showerror('Donanım raporu', str(e)); return
        self.write('Donanım raporu kaydedildi: %s\n' % path)

    def hw_copy_report(self):
        if not self.hw_records:
            messagebox.showinfo('Donanım raporu', 'Önce "Oku"ya basın.'); return
        self.clipboard_clear()
        self.clipboard_append(hw.report_text(*self._hw_report_parts()))
        self.write('Donanım raporu (metin) panoya kopyalandı.\n')

    # ------------------------------------------------------------------ AYGIT YONETICISI
    def _tab_devmgr(self, f):
        head = tk.Frame(f, bg=PANEL); head.pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(head, text='Aygıt yöneticisi', fg=FG, bg=PANEL, font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.dm_count = tk.StringVar(value='')
        tk.Label(head, textvariable=self.dm_count, fg=ACCENT, bg=PANEL2, font=('Segoe UI', 9, 'bold'), padx=10, pady=3).pack(side='left', padx=(10, 0))
        self.label(f, 'Windows Aygıt Yöneticisi\'nin okunur hali: sorunlu aygıtlar en üstte ve turuncu. Etkinleştirme, devre dışı bırakma, yeniden '
                      'başlatma ve kaldırma yönetici ister. Kaldırılan aygıt, donanım yeniden tarandığında ya da bilgisayar yeniden başlatıldığında '
                      'Windows tarafından yeniden tanınır. Sürücü güncellemesi için Sürücüler sayfasını kullanın.',
                   wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(2, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Tara', self.dm_scan, 'go')
        self.btn(bar, 'Etkinleştir', lambda: self.dm_action('enable'), 'normal')
        self.btn(bar, 'Devre dışı bırak', lambda: self.dm_action('disable'), 'ghost')
        self.btn(bar, 'Yeniden başlat', lambda: self.dm_action('restart'), 'ghost')
        self.btn(bar, 'Kaldır', lambda: self.dm_action('remove'), 'danger')
        self.btn(bar, 'Sürücüler sayfası', lambda: self.tabs.select('Sürücüler'), 'ghost', action=False)
        self.btn(bar, 'Windows Aygıt Yöneticisi', lambda: self._ov_open('devmgmt.msc'), 'ghost', action=False)
        flt = tk.Frame(f, bg=PANEL); flt.pack(fill='x', padx=16, pady=(6, 0))
        self.dm_only_bad = tk.BooleanVar(value=False)
        self.dm_hidden = tk.BooleanVar(value=False)
        ttk.Checkbutton(flt, text='Yalnız sorunlu aygıtlar', variable=self.dm_only_bad, command=self._dm_render).pack(side='left')
        ttk.Checkbutton(flt, text='Bağlı olmayanları da göster', variable=self.dm_hidden, command=self._dm_render).pack(side='left', padx=(12, 0))
        tk.Label(flt, text='Ara:', fg=FG, bg=PANEL).pack(side='left', padx=(14, 0))
        self.dm_q = tk.StringVar()
        ttk.Entry(flt, textvariable=self.dm_q, width=30).pack(side='left', padx=6)
        self.dm_q.trace_add('write', lambda *_: self._dm_render())
        tf = ttk.Frame(f, style='Card.TFrame'); tf.pack(fill='both', expand=True, padx=16, pady=8)
        cols = (('state', 'Durum', 210), ('ver', 'Sürücü sürümü', 130), ('date', 'Tarih', 90), ('provider', 'Sağlayıcı', 150), ('id', 'Örnek kimliği', 330))
        self.dm_tree = ttk.Treeview(tf, columns=[c[0] for c in cols], show='tree headings', selectmode='extended')
        self.dm_tree.heading('#0', text='Aygıt'); self.dm_tree.column('#0', width=int(320 * self.scale), stretch=True)
        for k, t, w in cols:
            self.dm_tree.heading(k, text=t); self.dm_tree.column(k, width=int(w * self.scale), stretch=k == 'id', anchor='w')
        ys = ttk.Scrollbar(tf, orient='vertical', command=self.dm_tree.yview)
        self.dm_tree.configure(yscrollcommand=ys.set)
        self.dm_tree.pack(side='left', fill='both', expand=True); ys.pack(side='right', fill='y')
        self.dm_tree.tag_configure('bad', foreground=WARN)
        self.dm_tree.tag_configure('off', foreground=MUTED)
        self.dm_tree.tag_configure('grp', font=('Segoe UI', 10, 'bold'))
        self.dm_records, self.dm_items = [], {}

    def dm_scan(self):
        def done(job):
            self._dm_set(job.data)
        self.start([Job('Aygıt listesi', cmd=ps_cmd('pnp-list'), on_done=done, show_output=False)])

    def _dm_set(self, records):
        self.dm_records = [r for r in records if r.get('type') == 'pnp']
        self._dm_render()

    def _dm_render(self):
        t = self.dm_tree
        t.delete(*t.get_children())
        self.dm_items = {}
        groups = hw.pnp_groups(self.dm_records, show_hidden=self.dm_hidden.get(), only_problems=self.dm_only_bad.get(), query=self.dm_q.get())
        nbad = sum(1 for r in self.dm_records if r.get('code') and r.get('present') is not False)
        self.dm_count.set('%d aygıt · %d sorunlu' % (sum(1 for r in self.dm_records if r.get('present') is not False), nbad) if self.dm_records else '')
        for n, (title, items) in enumerate(groups):
            gid = 'g%d' % n
            bad = any(r.get('code') for r in items)
            t.insert('', 'end', iid=gid, text='%s (%d)' % (title, len(items)), values=('', '', '', '', ''), open=bad or bool(self.dm_q.get().strip()),
                     tags=('grp', 'bad') if bad else ('grp',))
            for m, r in enumerate(items):
                iid = '%s_%d' % (gid, m)
                if r.get('code'):
                    state, tag = hw.pnp_problem(r.get('code')), ('bad',)
                elif r.get('present') is False:
                    state, tag = 'Bağlı değil', ('off',)
                else:
                    state, tag = 'Çalışıyor', ()
                t.insert(gid, 'end', iid=iid, text=r.get('name') or '(adsız aygıt)',
                         values=(state, r.get('ver', ''), r.get('date', ''), r.get('provider', ''), r.get('id', '')), tags=tag)
                self.dm_items[iid] = r

    def dm_action(self, op):
        sel = [self.dm_items[i] for i in self.dm_tree.selection() if i in self.dm_items]
        if not sel:
            messagebox.showinfo('Aygıt yöneticisi', 'Önce "Tara"ya basıp listeden aygıt seçin.'); return
        if not self.need_admin('pnp-action'):
            return
        names = {'enable': 'etkinleştirilecek', 'disable': 'devre dışı bırakılacak', 'restart': 'yeniden başlatılacak', 'remove': 'kaldırılacak'}
        msg = '%d aygıt %s:\n\n%s' % (len(sel), names[op], '\n'.join('• ' + (r.get('name') or r.get('id', '')) for r in sel[:8]))
        if len(sel) > 8:
            msg += '\n…'
        crit = [r for r in sel if r.get('cls') in CRITICAL_PNP]
        if crit and op in ('disable', 'remove', 'restart'):
            msg += ('\n\nDİKKAT: seçimde sistem için kritik aygıt var (%s). Bilgisayar yanıt vermeyebilir ya da açılmayabilir. '
                    'Ne yaptığınızdan emin değilseniz Hayır deyin.' % (crit[0].get('name') or crit[0].get('cls')))
        if not messagebox.askyesno('Aygıt yöneticisi', msg + '\n\nDevam edilsin mi?'):
            return
        self.start([Job('Aygıt: %s (%d)' % (op, len(sel)), cmd=ps_cmd('pnp-action', InstanceIds='|'.join(r['id'] for r in sel), PnpOp=op),
                        cancel_ok=False, on_done=lambda j: self.dm_scan())])

    # ------------------------------------------------------------------ DISK SAGLIGI
    def _tab_diskhealth(self, f):
        head = tk.Frame(f, bg=PANEL); head.pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(head, text='Disk sağlığı', fg=FG, bg=PANEL, font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.dh_state = tk.StringVar(value='')
        tk.Label(head, textvariable=self.dh_state, fg=MUTED, bg=PANEL, font=('Segoe UI', 9)).pack(side='left', padx=(12, 0))
        self.label(f, 'Windows\'un depolama sağlık sayaçları (SMART benzeri): genel durum, sıcaklık, SSD aşınması, çalışma saati ve düzeltilemeyen '
                      'hatalar. Sıcaklık ve aşınma sayaçları çoğu diskte yönetici ister. "Kötü" ya da "Dikkat" görürseniz önce yedek alın.',
                   wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(2, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Tara', self.dh_scan, 'go')
        tf = ttk.Frame(f, style='Card.TFrame'); tf.pack(fill='both', expand=True, padx=16, pady=8)
        cols = (('kind', 'Tür', 120), ('size', 'Boyut', 90), ('verdict', 'Durum', 420), ('temp', 'Sıcaklık', 80), ('wear', 'Aşınma', 70), ('hours', 'Çalışma (saat)', 110))
        self.dh_tree = ttk.Treeview(tf, columns=[c[0] for c in cols], show='tree headings', selectmode='browse', height=6)
        self.dh_tree.heading('#0', text='Disk'); self.dh_tree.column('#0', width=int(260 * self.scale))
        for k, t, w in cols:
            self.dh_tree.heading(k, text=t); self.dh_tree.column(k, width=int(w * self.scale), anchor='w', stretch=k == 'verdict')
        self.dh_tree.pack(fill='both', expand=True)
        for st, col in STATE_COLORS().items():
            self.dh_tree.tag_configure(st, foreground=col)
        self.dh_records = []

    def dh_scan(self):
        def done(job):
            self._dh_set(job.data)
        self.start([Job('Disk sağlığı', cmd=ps_cmd('disk-health'), on_done=done, show_output=False)])

    def _dh_set(self, records):
        self.dh_records = [r for r in records if r.get('type') == 'disk']
        t = self.dh_tree
        t.delete(*t.get_children())
        for st, col in STATE_COLORS().items():
            t.tag_configure(st, foreground=col)
        worst = 'ok'
        for i, d in enumerate(self.dh_records):
            st, txt = hw.disk_verdict(d)
            if hw.STATE_RANK[st] < hw.STATE_RANK[worst]:
                worst = st
            t.insert('', 'end', iid='d%d' % i, text=d.get('name') or 'Disk', tags=(st,),
                     values=(' · '.join(x for x in (d.get('media', ''), d.get('bus', '')) if x and x != 'Unspecified'), hw.fmt_bytes(d.get('size'), 1000), txt,
                             ('%s °C' % d['temp']) if d.get('temp') else '-', ('%%%s' % d['wear']) if d.get('wear') else '-',
                             d.get('hours') if d.get('hours') else '-'))
        self.dh_state.set(('%d disk · en kötü: %s' % (len(self.dh_records), {'ok': 'sağlıklı', 'warn': 'dikkat', 'bad': 'kötü', 'info': 'bilinmiyor'}[worst]))
                          if self.dh_records else 'Disk bulunamadı')


register_palette_module(globals())
