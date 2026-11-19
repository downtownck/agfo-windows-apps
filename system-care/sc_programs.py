# -*- coding: utf-8 -*-
"""AGFO System Care — Programlar sayfasi (BCU entegrasyonu). App sinifinin parcasi (mixin); paylasilan adlar sc_base'den gelir."""
from sc_base import *  # noqa: F401,F403


class ProgramsPage:
    # ------------------------------------------------------------------ PROGRAMLAR (BCU entegrasyonu)
    def _tab_programs(self, f):
        self.bcu_state = tk.StringVar(value='BCU motoru: denetleniyor...')
        tk.Label(f, textvariable=self.bcu_state, fg=MUTED, bg=PANEL, font=('Segoe UI', 9)).pack(anchor='w', padx=16, pady=(12, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Programları tara', self.prog_scan, 'ghost')
        self.btn(bar, 'BCU motoruyla genişlet', self.prog_bcu_scan, 'ghost')
        self.btn(bar, 'Seçilenleri kaldır', self.prog_uninstall, 'danger')
        self.btn(bar, 'Yetim kayıtları temizle', self.prog_remove_orphans, 'ghost')
        self.btn(bar, 'BCU tam arayüzü', self.prog_open_bcu, 'ghost')
        self.quiet_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text='Mümkünse sessiz kaldır', variable=self.quiet_var).pack(side='left', padx=8)
        flt = tk.Frame(f, bg=PANEL); flt.pack(fill='x', padx=16, pady=(6, 0))
        tk.Label(flt, text='Ara:', fg=FG, bg=PANEL).pack(side='left')
        self.prog_q = tk.StringVar()
        e = ttk.Entry(flt, textvariable=self.prog_q, width=36); e.pack(side='left', padx=6)
        self.prog_filter = ttk.Combobox(flt, state='readonly', width=26, values=['Tümü', 'Sessiz kaldırılabilir', 'Yetim kayıtlar', 'Kullanıcıya özel', 'Son 30 gün', 'Bilinen bloatware'])
        self.prog_filter.current(0); self.prog_filter.pack(side='left', padx=6)
        self.prog_q.trace_add('write', lambda *_: self._prog_render())
        self.prog_filter.bind('<<ComboboxSelected>>', lambda _e: self._prog_render())
        self.prog_count = tk.StringVar(value='')
        tk.Label(flt, textvariable=self.prog_count, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(side='right')
        cols = [('pub', 'Yayıncı', 200, 'w'), ('ver', 'Sürüm', 110, 'w'), ('size', 'Boyut', 80, 'e'), ('date', 'Kurulum', 90, 'w'),
                ('kind', 'Tür', 90, 'w'), ('silent', 'Sessiz', 60, 'center'), ('scope', 'Kapsam', 120, 'w')]
        self.prog_tree = CheckTree(f, cols, first=('Program', 330), on_change=self._prog_count)
        self.prog_tree.pack(fill='both', expand=True, padx=16, pady=8)
        self.label(f, 'Kaldırma sonrası kalan klasörler (artıklar) yalnızca kesin eşleşmeyle bulunur ve onayınızla Geri Dönüşüm Kutusu\'na taşınır. '
                      'Kırmızı satırlar: kaldırıcısı silinmiş yetim kayıtlar.', wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(0, 10))

    def _prog_count(self):
        n = len(self.prog_tree.checked)
        self.prog_count.set(('%d / %d program' % (len(self.prog_tree.labels), len(self.programs))) + (' · %d seçili' % n if n else ''))

    def prog_scan(self, then=None):
        def work(runner, job):
            t0 = time.time()
            job.data = core.annotate_programs(core.read_programs())
            runner.say('Kayıt taraması: %d program, %.2f sn' % (len(job.data), time.time() - t0))
            return 0
        self.start([Job('Program envanteri', func=work, on_done=lambda j: self._prog_loaded(j, then), cancel_ok=False)])

    def _prog_loaded(self, job, then=None):
        keep = {(p['name'], p['version']) for p in self.prog_tree.checked_payloads()} if self.prog_tree.labels else set()
        self.programs = job.data or []
        self._prog_render(keep)
        if then:
            then()

    def _prog_render(self, keep=None):
        if keep is None:
            keep = {(p['name'], p['version']) for p in self.prog_tree.checked_payloads()}
        q = self.prog_q.get().strip().lower()
        mode = self.prog_filter.get()
        cutoff = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
        t = self.prog_tree
        t.clear()
        for i, p in enumerate(self.programs):
            if q and q not in (p['name'] + ' ' + p['publisher']).lower():
                continue
            if mode == 'Sessiz kaldırılabilir' and not p.get('silent'):
                continue
            if mode == 'Yetim kayıtlar' and not p.get('orphan'):
                continue
            if mode == 'Kullanıcıya özel' and p['hive'] != 'HKCU':
                continue
            if mode == 'Son 30 gün' and not (p['date'] and p['date'] >= cutoff):
                continue
            if mode == 'Bilinen bloatware' and not core.classify_win32(p['name']):
                continue
            vals = (p['publisher'], p['version'], core.human_size(p['size_kb']), p['date'], p['kind'], 'evet' if p.get('silent') else '', p['scope'])
            t.add('p%d' % i, p['name'], vals, checked=(p['name'], p['version']) in keep, payload=p, tags=('orphan',) if p.get('orphan') else ())
        self._prog_count()

    def prog_bcu_scan(self):
        con = self.engines.get('bcu', {}).get('console')
        if not con:
            if messagebox.askyesno('BCU motoru yok', 'BCU (Bulk Crap Uninstaller) kurulu değil. Şimdi WinGet ile kurulsun mu?\n'
                                   'Kurulumdan sonra Store uygulamaları, Steam oyunları ve yetim kurulumlar da listelenir.'):
                self._engine_install_one('bcu')
            return
        out = app_data_dir() / 'bcu-export.xml'

        def after(runner, job):
            try:
                rows = core.parse_bcu_export(out.read_text(encoding='utf-8-sig', errors='replace'))
            except OSError:
                rows = []
            job.data = rows
            runner.say('BCU motoru: %d kayıt okundu.' % len(rows))
        j = Job('BCU envanter taraması', cmd=[con, 'export', str(out), '/Q', '/U'], after=after,
                on_done=lambda jb: self._prog_merge(jb))
        if not self.programs:
            self.prog_scan(then=lambda: self.start([j]))
        else:
            self.start([j])

    def _prog_merge(self, job):
        added = core.merge_bcu_programs(self.programs, job.data or [])
        self.write('BCU motoru %d ek uygulama buldu (Store/Steam/yetim vb.).\n' % added)
        self._prog_render()

    def prog_open_bcu(self):
        gui = self.engines.get('bcu', {}).get('path')
        if not gui:
            if messagebox.askyesno('BCU yok', 'BCU kurulu değil. WinGet ile kurulsun mu?'):
                self._engine_install_one('bcu')
            return
        try:
            core.shell_execute(gui, '')
            self.write('BCU masaüstü arayüzü açıldı: %s\n' % gui)
        except OSError as e:
            messagebox.showerror('BCU', str(e))

    def prog_uninstall(self):
        sel = [p for p in self.prog_tree.checked_payloads() if p]
        if not sel:
            messagebox.showinfo('Programlar', 'Kaldırılacak programları işaretleyin.'); return
        orphans = [p for p in sel if p.get('orphan')]
        sel = [p for p in sel if not p.get('orphan')]
        if orphans:
            self.write('%d yetim kayıt atlandı (kaldırıcısı yok); "Yetim kayıtları temizle" kullanın.\n' % len(orphans))
        if not sel:
            return
        quiet = self.quiet_var.get()
        names = '\n  '.join(p['name'] + ('  [sessiz]' if quiet and p.get('silent') else '') for p in sel[:20])
        if not messagebox.askyesno('Kaldırmayı onaylayın', '%d program sırayla kaldırılacak:\n  %s%s\n\nSessiz kaldırıcısı olmayanlar kendi '
                                   'penceresini açar. Devam edilsin mi?' % (len(sel), names, '\n  ...' if len(sel) > 20 else '')):
            return
        jobs = []
        for p in sel:
            exe, params = core.build_uninstall(p, quiet)
            jobs.append(Job('Kaldır: ' + p['name'], shell=(exe, params), after=self._after_uninstall(p), cancel_ok=True))
        jobs[-1].on_done = lambda j: self.prog_scan(then=lambda: self._offer_leftovers(sel))
        self.start(jobs)

    def _after_uninstall(self, p):
        def after(runner, job):
            # NSIS/Inno kaldiricilari kendini kopyalayip asil sureci bitirir: kayit silinene ya da yardimci surec bitene kadar bekle.
            deadline = time.time() + 15 * 60
            time.sleep(1.5)
            waited = False
            while time.time() < deadline and not runner.stop.is_set():
                if not core.registry_key_exists(p):
                    break
                helpers = core.running_uninstall_helpers()
                if not helpers:
                    break
                if not waited:
                    runner.say('Kaldırıcı arka planda sürüyor (%s); bekleniyor...' % ', '.join(sorted(set(helpers))))
                    waited = True
                time.sleep(2)
            gone = not core.registry_key_exists(p)
            p['_removed'] = gone
            runner.say(('Kaldırıldı: ' if gone else 'Kayıt hâlâ mevcut (iptal edilmiş veya yeniden başlatma bekliyor olabilir): ') + p['name'])
        return after

    def _offer_leftovers(self, removed):
        remaining = self.programs
        found = []
        still = {x['name'].lower() for x in remaining}
        for p in removed:
            # BCU'dan gelen (kayit anahtari bilinmeyen) girislerde kaldirma dogrulanamaz: artik onerme.
            if not p.get('_removed') or not p.get('key') or p['name'].lower() in still:
                continue
            for c in core.leftover_candidates(p, remaining):
                found.append((p['name'], c))
        if not found:
            self.write('Artık klasör bulunamadı.\n'); return
        self._leftover_dialog(found)

    def _leftover_dialog(self, found):
        win = tk.Toplevel(self); win.title('Artık klasörler'); win.configure(bg=PANEL); win.transient(self)
        w, h = int(820 * self.scale), int(420 * self.scale)
        win.geometry('%dx%d+%d+%d' % (w, h, self.winfo_rootx() + max(0, (self.winfo_width() - w) // 2), self.winfo_rooty() + max(0, (self.winfo_height() - h) // 3)))
        win.after(50, lambda: (win.grab_set(), win.focus_set()))
        self.label(win, 'Kaldırılan programlardan kalan klasörler. İşaretliler Geri Dönüşüm Kutusu\'na taşınır (geri alınabilir).',
                   wraplength=int(780 * self.scale)).pack(fill='x', padx=14, pady=10)
        ct = CheckTree(win, [('prog', 'Program', 220, 'w')], first=('Klasör', 520), height=10)
        ct.pack(fill='both', expand=True, padx=14)
        for i, (nm, path) in enumerate(found):
            ct.add('l%d' % i, path, (nm,), checked=True, payload=path)
        bar = tk.Frame(win, bg=PANEL); bar.pack(fill='x', padx=14, pady=10)

        def go():
            paths = ct.checked_payloads()
            win.destroy()
            if paths:
                self.start([Job('Artıkları Geri Dönüşüm Kutusu\'na taşı', cmd=ps_cmd('recycle-paths', Paths='|'.join(paths)), cancel_ok=False)])
        self.mkbtn(bar, 'Taşı', go, 'danger').pack(side='right')
        self.mkbtn(bar, 'Vazgeç', win.destroy, 'ghost').pack(side='right', padx=8)

    def prog_remove_orphans(self):
        sel = [p for p in self.prog_tree.checked_payloads() if p and p.get('orphan')]
        if not sel:
            sel = [p for p in self.programs if p.get('orphan')]
            if not sel:
                messagebox.showinfo('Yetim kayıtlar', 'Yetim kayıt bulunamadı.'); return
        if not messagebox.askyesno('Yetim kayıtlar', '%d kayıt "Programlar ve Özellikler" listesinden silinecek (önce .reg yedeği alınır):\n  %s\n\nDevam?'
                                   % (len(sel), '\n  '.join(p['name'] for p in sel[:15]))):
            return
        bdir = LOG_DIR / 'registry-backups'

        def work(runner, job):
            bad = 0
            for p in sel:
                ok, msg = core.remove_registry_entry(p, bdir)
                runner.say(('✓ ' if ok else '✗ ') + p['name'] + ' — ' + msg)
                bad += 0 if ok else 1
            return 2 if bad else 0
        self.start([Job('Yetim kayıt temizliği', func=work, cancel_ok=False, on_done=lambda j: self.prog_scan())])


register_palette_module(globals())
