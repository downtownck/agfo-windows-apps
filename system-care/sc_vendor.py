# -*- coding: utf-8 -*-
"""AGFO System Care — 4.1 Uretici destegi ve NVIDIA sayfalari. App sinifinin parcasi (mixin); yardimcilar care_oem'de."""
from sc_base import *  # noqa: F401,F403
import care_oem as oem  # noqa: E402


class VendorPage:
    # ------------------------------------------------------------------ URETICI DESTEGI
    def _tab_oem(self, f):
        head = tk.Frame(f, bg=PANEL); head.pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(head, text='Üretici desteği', fg=FG, bg=PANEL, font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.oem_title = tk.StringVar(value='')
        tk.Label(head, textvariable=self.oem_title, fg=ACCENT, bg=PANEL2, font=('Segoe UI', 9, 'bold'), padx=10, pady=3).pack(side='left', padx=(10, 0))
        self.label(f, 'Bilgisayarın üreticisi, modeli ve seri numarası Windows\'tan okunur; sürücüler üreticinin kendi sitesinden ya da kendi '
                      'güncelleme aracından alınır. Mümkün olan üreticilerde (Dell, ASUS) doğrudan ürün sayfası açılır; diğerlerinde resmî sürücü '
                      'sayfası açılır ve seri numarası/model panoya kopyalanır, sayfadaki arama kutusuna yapıştırmanız yeterli. '
                      'Kendi topladığınız masaüstünde anakart üreticisi kullanılır.', wraplength=int(980 * self.scale)).pack(fill='x', padx=16, pady=(2, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Tanı', self.oem_scan, 'go')
        self.btn(bar, 'Ürün / sürücü sayfasını aç', self.oem_open, 'normal', action=False)
        self.btn(bar, 'Üretici sitesinde ara', lambda: self.oem_open(search=True), 'ghost', action=False)
        self.btn(bar, 'Bilgileri kopyala', self.oem_copy, 'ghost', action=False)
        tf = ttk.Frame(f, style='Card.TFrame'); tf.pack(fill='x', padx=16, pady=(8, 4))
        self.oem_tree = ttk.Treeview(tf, columns=('val',), show='tree', selectmode='browse', height=7)
        self.oem_tree.column('#0', width=int(220 * self.scale), stretch=False); self.oem_tree.column('val', width=int(700 * self.scale))
        self.oem_tree.pack(fill='x')
        tk.Label(f, text='Üreticinin güncelleme araçları', fg=FG, bg=PANEL, font=('Segoe UI', 10, 'bold'), anchor='w').pack(fill='x', padx=16, pady=(10, 2))
        self.oem_tools = tk.Frame(f, bg=PANEL); self.oem_tools.pack(fill='x', padx=16)
        self.oem_info, self.oem_links, self.oem_loaded = None, None, False
        tk.Label(self.oem_tools, text='Önce "Tanı"ya basın.', fg=MUTED, bg=PANEL, font=('Segoe UI', 9)).pack(anchor='w')

    def _vendor_on_tab(self, _e=None):
        try:
            title = self.tabs.tab(self.tabs.current, 'text')
        except Exception:
            return
        if title == 'Üretici desteği' and not self.oem_loaded and IS_WIN and not self.busy:
            self.oem_scan(quiet=True)
        elif title == 'NVIDIA' and not self.nv_loaded and IS_WIN and not self.busy:
            self.nv_scan(quiet=True)

    def oem_scan(self, quiet=False):
        def done(job):
            recs = [r for r in job.data if r.get('type') == 'oem']
            if recs:
                self._oem_set(recs[0])
        self.start([Job('Üretici ve model', cmd=ps_cmd('oem-info'), on_done=done, show_output=False)], quiet=quiet)

    def _oem_set(self, rec):
        self.oem_loaded = True
        info = oem.identify(rec)
        self.oem_info, self.oem_links = info, oem.support_links(info)
        self.oem_title.set('%s · %s' % (info['name'], info['model'] or '?'))
        t = self.oem_tree
        t.delete(*t.get_children())
        rows = [('Üretici', info['maker'] or '-'), ('Destek', info['name'] + (' (anakart üreticisi)' if info['generic'] else '')),
                ('Model', info['model'] or '-'), ('Seri numarası', info['serial'] or 'okunamadı'), ('SKU / ürün numarası', info['sku'] or '-'),
                ('Anakart', info['board'] or '-'), ('Tür', 'Dizüstü' if info['notebook'] else 'Masaüstü / diğer'),
                ('Açılacak sayfa', self.oem_links['direct'] or self.oem_links['drivers'])]
        for i, (k, v) in enumerate(rows):
            t.insert('', 'end', iid='r%d' % i, text=k, values=(v,))
        for w in self.oem_tools.winfo_children():
            w.destroy()
        for name, source, pkg, note in oem.vendor_tools(info):
            row = tk.Frame(self.oem_tools, bg=PANEL2, padx=10, pady=6); row.pack(fill='x', pady=(0, 6))
            tk.Label(row, text=name, fg=FG, bg=PANEL2, font=('Segoe UI', 10, 'bold')).pack(side='left')
            tk.Label(row, text='  ' + note + ('  · Microsoft Store' if source == 'msstore' else '  · WinGet'), fg=MUTED, bg=PANEL2,
                     font=('Segoe UI', 9)).pack(side='left')
            self.mkbtn(row, 'Kur', lambda s=source, p=pkg, n=name: self.oem_install_tool(s, p, n), 'ghost', small=True).pack(side='right')

    def oem_open(self, search=False):
        if not self.oem_links:
            messagebox.showinfo('Üretici desteği', 'Önce "Tanı"ya basın.'); return
        L = self.oem_links
        url = (L['search'] or L['drivers']) if search else (L['direct'] or L['drivers'])
        if not search and not L['direct'] and L['copy']:
            self.clipboard_clear()
            self.clipboard_append(L['copy'])
            messagebox.showinfo('Üretici desteği', '%s panoya kopyalandı:\n%s\n\nAçılan sayfadaki arama kutusuna yapıştırın (Ctrl+V).'
                                % (L['copy_label'].capitalize(), L['copy']))
        self.write('Üretici sayfası: %s\n' % url)
        self._open_url(url)

    def oem_copy(self):
        if not self.oem_info:
            messagebox.showinfo('Üretici desteği', 'Önce "Tanı"ya basın.'); return
        i = self.oem_info
        txt = 'Üretici: %s\nModel: %s\nSeri numarası: %s\nSKU: %s\nAnakart: %s\n' % (i['maker'], i['model'], i['serial'], i['sku'], i['board'])
        self.clipboard_clear()
        self.clipboard_append(txt)
        self.write('Üretici bilgileri panoya kopyalandı.\n')

    def oem_install_tool(self, source, pkg, name):
        wg = self.engines.get('winget', {}).get('path') or core.find_winget()
        if not wg:
            messagebox.showerror('WinGet yok', 'WinGet bulunamadı.'); return
        if not messagebox.askyesno('Üretici aracı', '%s kurulsun mu?\n(%s: %s)' % (name, 'Microsoft Store' if source == 'msstore' else 'WinGet', pkg)):
            return
        self.start([Job('Kur: ' + name, cmd=oem.tool_install_cmd(wg, source, pkg), cancel_ok=False)])

    # ------------------------------------------------------------------ NVIDIA
    def _tab_nvidia(self, f):
        head = tk.Frame(f, bg=PANEL); head.pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(head, text='NVIDIA sürücüsü', fg=FG, bg=PANEL, font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.nv_state = tk.StringVar(value='')
        self.nv_state_lbl = tk.Label(head, textvariable=self.nv_state, fg=ACCENT, bg=PANEL2, font=('Segoe UI', 9, 'bold'), padx=10, pady=3)
        self.nv_state_lbl.pack(side='left', padx=(10, 0))
        self.label(f, 'Ekran kartınıza uygun en yeni NVIDIA sürücüsü NVIDIA\'nın kendi sürücü servisinden bulunur, NVIDIA sunucusundan indirilir, '
                      'dijital imzası doğrulanır (yalnızca NVIDIA Corporation imzalı dosya çalıştırılır) ve sessiz kurulur. "Yalnızca sürücü" seçeneği '
                      'NVIDIA App ve ek bileşenler olmadan yalın kurulum yapar (7-Zip gerekir). Kaldırma: NVIDIA\'nın kendi kaldırıcısı, Windows sürücü '
                      'deposundan paket silme ya da açık kaynak Display Driver Uninstaller (DDU) ile derin temizlik.',
                   wraplength=int(980 * self.scale)).pack(fill='x', padx=16, pady=(2, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Denetle', self.nv_scan, 'go')
        self.btn(bar, 'İndir ve kur', self.nv_install, 'normal')
        self.btn(bar, 'NVIDIA sitesinde aç', self.nv_open_site, 'ghost', action=False)
        self.nv_clean = tk.BooleanVar(value=False)
        self.nv_minimal = tk.BooleanVar(value=False)
        opt = tk.Frame(f, bg=PANEL); opt.pack(fill='x', padx=16, pady=(6, 0))
        ttk.Checkbutton(opt, text='Temiz kurulum (NVIDIA ayarlarını sıfırlar)', variable=self.nv_clean).pack(side='left')
        ttk.Checkbutton(opt, text='Yalnızca sürücü (NVIDIA App olmadan)', variable=self.nv_minimal).pack(side='left', padx=(14, 0))
        ub = tk.Frame(f, bg=PANEL); ub.pack(fill='x', padx=16, pady=(8, 0))
        tk.Label(ub, text='Kaldırma:', fg=FG, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(side='left', padx=(0, 8))
        self.btn(ub, 'NVIDIA kaldırıcısıyla kaldır', lambda: self.nv_uninstall('nvi2'), 'ghost')
        self.btn(ub, 'Sürücü paketlerini Windows\'tan sil', lambda: self.nv_uninstall('packages'), 'ghost')
        self.btn(ub, 'DDU ile derin temizlik…', self.nv_ddu, 'danger')
        tf = ttk.Frame(f, style='Card.TFrame'); tf.pack(fill='both', expand=True, padx=16, pady=8)
        self.nv_tree = ttk.Treeview(tf, columns=('val',), show='tree', selectmode='browse')
        self.nv_tree.column('#0', width=int(300 * self.scale), stretch=False); self.nv_tree.column('val', width=int(700 * self.scale))
        ys = ttk.Scrollbar(tf, orient='vertical', command=self.nv_tree.yview)
        self.nv_tree.configure(yscrollcommand=ys.set)
        self.nv_tree.pack(side='left', fill='both', expand=True); ys.pack(side='right', fill='y')
        self.nv_tree.tag_configure('sec', font=('Segoe UI', 10, 'bold'))
        self.nv_info, self.nv_latest, self.nv_loaded, self.nv_gpu = None, None, False, None

    def nv_scan(self, quiet=False):
        def lookup(runner, job):
            info = self.nv_info or {}
            gpu = next((g for g in info.get('gpus', []) if g.get('nvidia')), None)
            if not gpu:
                runner.say('NVIDIA ekran kartı bulunamadı.')
                return 0
            data = oem.load_nv_data()
            try:                                                    # guncel urun listesi (yoksa paketteki kopya)
                fresh = json.loads(core.fetch_text(oem.NV_DATA_URL, oem.NV_HOSTS))
                if isinstance(fresh, dict) and fresh.get('desktop'):
                    data['gpu'] = fresh
            except Exception as e:                                  # noqa: BLE001
                runner.say('Güncel NVIDIA ürün listesi alınamadı, paketteki kopya kullanılıyor (%s).' % e)
            pfid, kind = oem.nv_pfid(data, gpu['name'], info.get('notebook'))
            if not pfid:
                runner.say('"%s" NVIDIA ürün listesinde bulunamadı; "NVIDIA sitesinde aç" ile elle arayın.' % gpu['name'])
                job.result = {'error': 'model'}
                return 0
            url = oem.nv_lookup_url(pfid, oem.nv_os_id(data, info.get('build'), info.get('x64', True)), True)
            res = oem.nv_parse_lookup(core.fetch_text(url, oem.NV_HOSTS))
            job.result = res or {'error': 'lookup'}
            runner.say('NVIDIA: %s → en yeni sürüm %s' % (gpu['name'], res['version'] if res else 'bulunamadı'))
            return 0

        def info_done(job):
            recs = [r for r in job.data if r.get('type') == 'nvinfo']
            if recs:
                self._nv_set_info(recs[0])
                if any(g.get('nvidia') for g in recs[0].get('gpus', [])):
                    self.start([Job('NVIDIA son sürüm', func=lookup, on_done=lambda j: self._nv_set_latest(getattr(j, 'result', None)), show_output=True)])
        self.start([Job('NVIDIA bilgisi', cmd=ps_cmd('nvidia-info'), on_done=info_done, show_output=False)], quiet=quiet)

    def _nv_set_info(self, rec):
        self.nv_loaded, self.nv_info = True, rec
        self.nv_gpu = next((g for g in rec.get('gpus', []) if g.get('nvidia')), None)
        self._nv_render()

    def _nv_set_latest(self, res):
        self.nv_latest = res if res and not res.get('error') else None
        if res and res.get('error') == 'model':
            self.nv_latest = None
        self._nv_render()

    def _nv_render(self):
        t = self.nv_tree
        t.delete(*t.get_children())
        info = self.nv_info or {}
        t.insert('', 'end', iid='g', text='Ekran kartları', values=('',), open=True, tags=('sec',))
        for i, g in enumerate(info.get('gpus', [])):
            ver = oem.nv_version(g.get('driver')) if g.get('nvidia') else ''
            t.insert('g', 'end', iid='g%d' % i, text=g.get('name') or '?',
                     values=(('NVIDIA sürücüsü %s (%s)' % (ver, g.get('date', ''))) if g.get('nvidia') else ('Sürücü %s' % g.get('driver', '')),))
        cur = oem.nv_version(self.nv_gpu.get('driver')) if self.nv_gpu else ''
        t.insert('', 'end', iid='s', text='Durum', values=('',), open=True, tags=('sec',))
        rows = [('Kurulu sürüm', cur or '-'), ('En yeni sürüm', ('%s — %s (%s)' % (self.nv_latest['version'], self.nv_latest['name'], self.nv_latest['date']))
                                                                    if self.nv_latest else '-'),
                ('Sürücü türü', 'DCH' if info.get('dch') else ('Standart' if self.nv_gpu else '-')), ('Tür', 'Dizüstü' if info.get('notebook') else 'Masaüstü'),
                ('7-Zip (yalın kurulum için)', info.get('sevenzip') or 'kurulu değil'), ('DDU', info.get('ddu') or 'kurulu değil'),
                ('NVIDIA kaldırıcısı', 'var' if info.get('nvi2') else 'yok')]
        for i, (k, v) in enumerate(rows):
            t.insert('s', 'end', iid='s%d' % i, text=k, values=(v,))
        if info.get('apps'):
            t.insert('', 'end', iid='a', text='Kurulu NVIDIA yazılımları', values=('',), open=False, tags=('sec',))
            for i, a in enumerate(info['apps']):
                t.insert('a', 'end', iid='a%d' % i, text=a.get('name', ''), values=(a.get('version', ''),))
        if info.get('packages'):
            t.insert('', 'end', iid='p', text='NVIDIA sürücü paketleri (Windows deposu)', values=('',), open=False, tags=('sec',))
            for i, p in enumerate(info['packages']):
                t.insert('p', 'end', iid='p%d' % i, text=p.get('inf', ''), values=('%s · %s · %s' % (p.get('name', ''), p.get('cls', ''), p.get('ver', '')),))
        if not self.nv_gpu:
            self.nv_state.set('NVIDIA ekran kartı yok' if info else '')
            self.nv_state_lbl.configure(fg=MUTED)
        elif self.nv_latest and cur:
            newer = oem.version_tuple(self.nv_latest['version']) > oem.version_tuple(cur)
            self.nv_state.set(('Güncelleme var: %s → %s' % (cur, self.nv_latest['version'])) if newer else ('Güncel (%s)' % cur))
            self.nv_state_lbl.configure(fg=WARN if newer else OK_C)
        else:
            self.nv_state.set('Kurulu: %s' % (cur or '?'))
            self.nv_state_lbl.configure(fg=ACCENT)

    def nv_open_site(self):
        self._open_url((self.nv_latest or {}).get('details') or oem.NV_DRIVER_PAGE)

    def nv_install(self):
        if not self.nv_gpu:
            messagebox.showinfo('NVIDIA', 'Önce "Denetle"ye basın (NVIDIA ekran kartı bulunmalı).'); return
        if not self.nv_latest:
            messagebox.showinfo('NVIDIA', 'En yeni sürücü bulunamadı. "Denetle"yi tekrarlayın ya da "NVIDIA sitesinde aç" ile elle indirin.'); return
        minimal = self.nv_minimal.get()
        sz = (self.nv_info or {}).get('sevenzip')
        if minimal and not sz:
            if messagebox.askyesno('7-Zip gerekli', 'Yalnızca sürücü kurulumu için sürücü paketinin açılması gerekiyor (7-Zip). 7-Zip kurulsun mu?\n'
                                   'Kurulduktan sonra "Denetle" ve "İndir ve kur"a yeniden basın.'):
                wg = self.engines.get('winget', {}).get('path') or core.find_winget()
                if wg:
                    self.start([Job('Kur: 7-Zip', cmd=core.winget_install_cmd(wg, oem.SEVENZIP_PKG), cancel_ok=False, on_done=lambda j: self.nv_scan())])
            return
        L = self.nv_latest
        cur = oem.nv_version(self.nv_gpu.get('driver'))
        if not messagebox.askyesno('NVIDIA sürücüsü', 'NVIDIA %s sürücüsü indirilip kurulacak (%s).\nKurulu: %s\n\n%s%s\n'
                                   'İndirme birkaç yüz MB olabilir; kurulum sırasında ekran birkaç kez kararabilir. Yönetici onayı (UAC) istenecek.\n\nDevam?'
                                   % (L['version'], L['name'], cur or '-', '• Temiz kurulum: NVIDIA ayarları sıfırlanır.\n' if self.nv_clean.get() else '',
                                      '• Yalnızca sürücü: NVIDIA App ve ek bileşenler kurulmaz.\n' if minimal else '')):
            return
        dest = core.APP_DATA_DIR / 'nvidia' / L['url'].rsplit('/', 1)[-1]
        clean = self.nv_clean.get()

        def download(runner, job):
            if dest.is_file() and dest.stat().st_size > 50 * 1024 * 1024:
                runner.say('Daha önce indirilmiş dosya kullanılıyor: %s' % dest)
                return 0
            runner.say('İndiriliyor: %s' % L['url'])
            core.download(L['url'], dest, oem.NV_HOSTS, progress=runner.progress_cb('NVIDIA sürücüsü'), should_stop=runner.stop.is_set)
            return 0

        def sig_done(job):
            if not dest.is_file():
                self.write('NVIDIA sürücüsü indirilemedi; kurulum yapılmadı.\n'); return
            sig = next((r for r in job.data if r.get('type') == 'sig'), {})
            if sig.get('status') != 'Valid' or 'NVIDIA Corporation' not in sig.get('subject', ''):
                self.write('İmza doğrulanamadı (%s, %s); kurulum yapılmadı.\n' % (sig.get('status'), sig.get('subject')))
                messagebox.showerror('NVIDIA', 'İndirilen dosyanın dijital imzası doğrulanamadı; güvenlik için kurulmadı.\n%s' % dest)
                return
            if minimal:
                ext = core.APP_DATA_DIR / 'nvidia' / ('yalin-' + L['version'])

                def prep(runner, j):
                    cfg = ext / 'setup.cfg'
                    cfg.write_text(oem.strip_setup_cfg(cfg.read_text(encoding='utf-8', errors='replace')), encoding='utf-8')
                    return 0
                self.start([Job('Sürücü paketini aç (yalın)', cmd=oem.nv_extract_cmd(sz, dest, ext), cancel_ok=False),
                            Job('Kurulum ayarı', func=prep, cancel_ok=False),
                            Job('NVIDIA sürücüsünü kur (yalın)', cmd=oem.nv_install_cmd(dest, clean, minimal_setup=ext / 'setup.exe'), cancel_ok=False,
                                admin=True, on_done=lambda j: self._nv_installed(j))])
            else:
                self.start([Job('NVIDIA sürücüsünü kur', cmd=oem.nv_install_cmd(dest, clean), cancel_ok=False, admin=True, on_done=lambda j: self._nv_installed(j))])
        self.start([Job('NVIDIA sürücüsünü indir', func=download),
                    Job('İmza denetimi', cmd=ps_cmd('sig-check', Paths=str(dest)), on_done=sig_done, show_output=True)])

    def _nv_installed(self, job):
        if job.code in (0, 1):                                      # NVIDIA kurucusu: 0 tamam, 1 yeniden baslatma gerekebilir
            self.write('NVIDIA sürücüsü kuruldu (kod %s). Yeniden başlatma önerilir.\n' % job.code)
            messagebox.showinfo('NVIDIA', 'Sürücü kuruldu. Değişikliğin tamamlanması için bilgisayarı yeniden başlatmanız önerilir.')
        else:
            messagebox.showwarning('NVIDIA', 'Kurulum %s koduyla bitti. Ayrıntı işlem günlüğünde.' % job.code)
        self.nv_scan()

    def nv_uninstall(self, mode):
        if not self.nv_info:
            messagebox.showinfo('NVIDIA', 'Önce "Denetle"ye basın.'); return
        if mode == 'nvi2':
            if not self.nv_info.get('nvi2'):
                messagebox.showinfo('NVIDIA', 'NVIDIA kaldırıcısı bulunamadı. "Sürücü paketlerini Windows\'tan sil" ya da DDU kullanın.'); return
            msg, action = 'NVIDIA ekran sürücüsü NVIDIA\'nın kendi kaldırıcısıyla sessizce kaldırılacak.', 'nvidia-uninstall'
        else:
            n = len([p for p in self.nv_info.get('packages', []) if p.get('cls', '').upper() == 'DISPLAY'])
            msg, action = ('%d NVIDIA ekran sürücü paketi Windows sürücü deposundan silinecek (pnputil). Ekran kartı Microsoft Temel Görüntü '
                           'Bağdaştırıcısı ile çalışmaya devam eder; çözünürlük düşebilir.' % n), 'nvidia-remove-packages'
        if not messagebox.askyesno('NVIDIA kaldır', msg + '\n\nYönetici onayı (UAC) istenecek; ardından yeniden başlatma önerilir. Devam?'):
            return
        self.start([Job('NVIDIA kaldır', cmd=ps_cmd(action), cancel_ok=False, on_done=lambda j: self.nv_scan())])

    def nv_ddu(self):
        ddu = (self.nv_info or {}).get('ddu')
        if not ddu:
            if messagebox.askyesno('DDU', 'Display Driver Uninstaller (açık kaynak, MIT) kurulu değil. WinGet ile kurulsun mu?\n'
                                   'Kurulduktan sonra "Denetle" ve "DDU ile derin temizlik"e yeniden basın.'):
                wg = self.engines.get('winget', {}).get('path') or core.find_winget()
                if wg:
                    self.start([Job('Kur: Display Driver Uninstaller', cmd=core.winget_install_cmd(wg, oem.DDU_PKG), cancel_ok=False, on_done=lambda j: self.nv_scan())])
            return
        if not messagebox.askyesno('DDU ile derin temizlik', 'DDU tüm NVIDIA sürücü, ayar ve kalıntılarını (PhysX ve NVIDIA App dahil) temizleyecek, önce '
                                   'geri yükleme noktası oluşturacak ve bilgisayarı YENİDEN BAŞLATACAK.\n\nAçık işlerinizi kaydedin. Yeniden başlatmadan '
                                   'sonra yeni sürücüyü buradan kurabilirsiniz (Windows Update kendiliğinden bir sürücü de kurabilir).\n\nDevam?'):
            return
        self.start([Job('DDU: NVIDIA temizliği', cmd=oem.ddu_cmd(ddu), cancel_ok=False, admin=True)])


register_palette_module(globals())
