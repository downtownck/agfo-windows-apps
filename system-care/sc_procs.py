# -*- coding: utf-8 -*-
"""AGFO System Care — 4.2 Calisan uygulamalar, Servisler ve Baslangic sayfalari. App sinifinin parcasi (mixin)."""
from sc_base import *  # noqa: F401,F403
import care_procs as pr  # noqa: E402


def _tree(parent, cols, first, height=16):
    tf = ttk.Frame(parent, style='Card.TFrame')
    tf.pack(fill='both', expand=True, padx=16, pady=8)
    t = ttk.Treeview(tf, columns=[c[0] for c in cols], show='tree headings', selectmode='extended', height=height)
    t.heading('#0', text=first[0]); t.column('#0', width=first[1], stretch=True)
    for k, title, w, anchor in cols:
        t.heading(k, text=title); t.column(k, width=w, anchor=anchor, stretch=k in ('path', 'cmd', 'title'))
    ys = ttk.Scrollbar(tf, orient='vertical', command=t.yview)
    t.configure(yscrollcommand=ys.set)
    t.pack(side='left', fill='both', expand=True); ys.pack(side='right', fill='y')
    return t


class ProcsPage:
    def _procs_on_tab(self, _e=None):
        try:
            title = self.tabs.tab(self.tabs.current, 'text')
        except Exception:
            return
        if not IS_WIN or self.busy:
            return
        if title == 'Çalışan uygulamalar' and not self.pc_records:
            self.pc_refresh(quiet=True)
        elif title == 'Servisler' and not self.sv_records:
            self.sv_refresh(quiet=True)
        elif title == 'Başlangıç' and not self.st_records:
            self.st_refresh(quiet=True)

    def _open_location(self, path):
        path = pr.command_exe(path) if path else ''
        if not path:
            messagebox.showinfo('Dosya konumu', 'Bu öğenin dosya yolu okunamadı (yönetici gerekebilir).'); return
        if IS_WIN:
            subprocess.Popen(['explorer.exe', '/select,', os.path.expandvars(path)])

    # ------------------------------------------------------------------ CALISAN UYGULAMALAR
    def _tab_procs(self, f):
        head = tk.Frame(f, bg=PANEL); head.pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(head, text='Çalışan uygulamalar', fg=FG, bg=PANEL, font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.pc_count = tk.StringVar(value='')
        tk.Label(head, textvariable=self.pc_count, fg=ACCENT, bg=PANEL2, font=('Segoe UI', 9, 'bold'), padx=10, pady=3).pack(side='left', padx=(10, 0))
        self.label(f, 'Açık uygulamalar ve arka plan süreçleri; işlemci (son 1 sn) ve bellek kullanımına göre sıralı. Seçip "Sonlandır" ile kapatabilirsiniz: '
                      'kaydedilmemiş işler kaybolur. Windows\'un kritik süreçleri (csrss, lsass, svchost, dwm…) listede görünür ama sonlandırılamaz. '
                      'Başka kullanıcıya ya da sisteme ait bir süreç için yönetici onayı (UAC) istenir.', wraplength=int(980 * self.scale)).pack(fill='x', padx=16, pady=(2, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Yenile', self.pc_refresh, 'go')
        self.btn(bar, 'Sonlandır', lambda: self.pc_kill(False), 'danger')
        self.btn(bar, 'Alt süreçleriyle sonlandır', lambda: self.pc_kill(True), 'ghost')
        self.btn(bar, 'Dosya konumunu aç', lambda: self._open_location(self._pc_sel()[0].get('path') if self._pc_sel() else ''), 'ghost', action=False)
        self.btn(bar, 'AI\'ya sor', lambda: self.ai_ask_about('süreçler', self._pc_sel(), ['name', 'company', 'title', 'path']), 'ghost', action=False)
        flt = tk.Frame(f, bg=PANEL); flt.pack(fill='x', padx=16, pady=(6, 0))
        self.pc_windowed = tk.BooleanVar(value=True)
        self.pc_hide_sys = tk.BooleanVar(value=True)
        self.pc_auto = tk.BooleanVar(value=False)
        ttk.Checkbutton(flt, text='Yalnız pencereli uygulamalar', variable=self.pc_windowed, command=self._pc_render).pack(side='left')
        ttk.Checkbutton(flt, text='Windows süreçlerini gizle', variable=self.pc_hide_sys, command=self._pc_render).pack(side='left', padx=(12, 0))
        ttk.Checkbutton(flt, text='10 sn\'de bir yenile', variable=self.pc_auto, command=self._pc_auto_tick).pack(side='left', padx=(12, 0))
        tk.Label(flt, text='Ara:', fg=FG, bg=PANEL).pack(side='left', padx=(14, 0))
        self.pc_q = tk.StringVar()
        ttk.Entry(flt, textvariable=self.pc_q, width=26).pack(side='left', padx=6)
        self.pc_q.trace_add('write', lambda *_: self._pc_render())
        self.pc_tree = _tree(f, [('pid', 'PID', 70, 'e'), ('cpu', 'İşlemci %', 80, 'e'), ('mem', 'Bellek', 90, 'e'), ('title', 'Pencere', 260, 'w'),
                                 ('company', 'Yayıncı', 160, 'w'), ('path', 'Yol', 300, 'w')], ('Ad', int(200 * self.scale)))
        self.pc_tree.tag_configure('crit', foreground=MUTED)
        self.pc_records, self.pc_items = [], {}

    def pc_refresh(self, quiet=False):
        self.start([Job('Süreç listesi', cmd=ps_cmd('proc-list'), on_done=lambda j: self._pc_set(j.data), show_output=False)], quiet=quiet)

    def _pc_set(self, records):
        self.pc_records = [r for r in records if r.get('type') == 'proc']
        self._pc_render()

    def _pc_render(self):
        t = self.pc_tree
        keep = {self.pc_items[i].get('pid') for i in t.selection() if i in self.pc_items}
        t.delete(*t.get_children())
        self.pc_items = {}
        rows = pr.filter_procs(self.pc_records, self.pc_q.get(), self.pc_windowed.get(), self.pc_hide_sys.get())
        total_mem = sum(r.get('mem') or 0 for r in self.pc_records)
        self.pc_count.set('%d gösteriliyor · %d süreç · %s bellek' % (len(rows), len(self.pc_records), pr.human_mb(total_mem)) if self.pc_records else '')
        for r in rows:
            iid = 'p%d' % r['pid']
            t.insert('', 'end', iid=iid, text=r.get('name', ''), tags=('crit',) if pr.is_critical_proc(r) else (),
                     values=(r['pid'], '%.1f' % (r.get('cpu') or 0), pr.human_mb(r.get('mem')), r.get('title', ''), r.get('company', ''), r.get('path', '')))
            self.pc_items[iid] = r
            if r['pid'] in keep:
                t.selection_add(iid)

    def _pc_sel(self):
        return [self.pc_items[i] for i in self.pc_tree.selection() if i in self.pc_items]

    def _pc_auto_tick(self):
        if not self.pc_auto.get():
            return
        try:
            title = self.tabs.tab(self.tabs.current, 'text')
        except Exception:
            title = ''
        if title == 'Çalışan uygulamalar' and not self.busy and IS_WIN:
            self.pc_refresh(quiet=True)
        self.after(10000, self._pc_auto_tick)

    def pc_kill(self, tree=False):
        sel = self._pc_sel()
        if not sel:
            messagebox.showinfo('Çalışan uygulamalar', 'Önce listeden süreç seçin.'); return
        crit = [r for r in sel if pr.is_critical_proc(r)]
        sel = [r for r in sel if not pr.is_critical_proc(r)]
        if crit:
            messagebox.showwarning('Kritik süreç', 'Windows\'un çalışması için gerekli olduğundan sonlandırılmayacak: %s'
                                   % ', '.join(sorted({r['name'] for r in crit})))
        if not sel:
            return
        names = ', '.join(sorted({r['name'] for r in sel}))[:300]
        if not messagebox.askyesno('Sonlandır', '%d süreç%s sonlandırılacak:\n%s\n\nKaydedilmemiş işler kaybolabilir. Devam?'
                                   % (len(sel), ' (alt süreçleriyle)' if tree else '', names)):
            return
        items = pr.b64_items([{'pid': r['pid'], 'name': r['name']} for r in sel])
        op = 'killtree' if tree else 'kill'

        def done(job):
            denied = [r for r in job.data if r.get('type') == 'killres' and not r.get('ok') and r.get('denied')]
            if denied and not self.admin and IS_WIN and messagebox.askyesno('Yönetici gerekli', '%d süreç için erişim reddedildi (başka kullanıcıya ya da sisteme ait). '
                                                                         'Yönetici olarak tekrar denensin mi?' % len(denied)):
                self.start([Job('Süreç sonlandır (yönetici)', cmd=ps_cmd('proc-kill', ItemsB64=items, Op=op), admin=True, cancel_ok=False,
                                on_done=lambda j: self.pc_refresh(quiet=True))])
            else:
                self.pc_refresh(quiet=True)
        self.start([Job('Süreç sonlandır', cmd=ps_cmd('proc-kill', ItemsB64=items, Op=op), cancel_ok=False, on_done=done)])

    # ------------------------------------------------------------------ SERVISLER
    def _tab_services(self, f):
        head = tk.Frame(f, bg=PANEL); head.pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(head, text='Servisler', fg=FG, bg=PANEL, font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.sv_count = tk.StringVar(value='')
        tk.Label(head, textvariable=self.sv_count, fg=ACCENT, bg=PANEL2, font=('Segoe UI', 9, 'bold'), padx=10, pady=3).pack(side='left', padx=(10, 0))
        self.label(f, 'Tüm Windows servisleri. Başlatma, durdurma ve başlangıç türünü değiştirme yönetici onayı (UAC) ister. Windows\'un çalışması için gerekli '
                      'servisler (RPC, olay günlüğü, güvenlik duvarı, Defender, DNS istemcisi…) durdurulamaz ya da devre dışı bırakılamaz. Emin olmadığınız '
                      'bir servisi "Devre dışı" yerine "El ile" yapın: gerektiğinde Windows yine başlatabilir.', wraplength=int(980 * self.scale)).pack(fill='x', padx=16, pady=(2, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Yenile', self.sv_refresh, 'go')
        self.btn(bar, 'Başlat', lambda: self.sv_action('start'), 'normal')
        self.btn(bar, 'Durdur', lambda: self.sv_action('stop'), 'danger')
        self.btn(bar, 'Yeniden başlat', lambda: self.sv_action('restart'), 'ghost')
        tk.Label(bar, text='  Başlangıç:', fg=FG, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(side='left')
        self.btn(bar, 'Otomatik', lambda: self.sv_action('auto'), 'ghost')
        self.btn(bar, 'El ile', lambda: self.sv_action('manual'), 'ghost')
        self.btn(bar, 'Devre dışı', lambda: self.sv_action('disabled'), 'ghost')
        self.btn(bar, 'AI\'ya sor', lambda: self.ai_ask_about('servisler', [self.sv_items[i] for i in self.sv_tree.selection() if i in self.sv_items],
                                                     ['name', 'display', 'state', 'start', 'path']), 'ghost', action=False)
        flt = tk.Frame(f, bg=PANEL); flt.pack(fill='x', padx=16, pady=(6, 0))
        self.sv_running = tk.BooleanVar(value=False)
        self.sv_third = tk.BooleanVar(value=False)
        ttk.Checkbutton(flt, text='Yalnız çalışanlar', variable=self.sv_running, command=self._sv_render).pack(side='left')
        ttk.Checkbutton(flt, text='Microsoft dışı', variable=self.sv_third, command=self._sv_render).pack(side='left', padx=(12, 0))
        tk.Label(flt, text='Ara:', fg=FG, bg=PANEL).pack(side='left', padx=(14, 0))
        self.sv_q = tk.StringVar()
        ttk.Entry(flt, textvariable=self.sv_q, width=26).pack(side='left', padx=6)
        self.sv_q.trace_add('write', lambda *_: self._sv_render())
        self.sv_tree = _tree(f, [('name', 'Servis adı', 160, 'w'), ('state', 'Durum', 100, 'w'), ('start', 'Başlangıç', 130, 'w'), ('account', 'Hesap', 170, 'w'),
                                 ('path', 'Yol', 320, 'w')], ('Görünen ad', int(280 * self.scale)))
        self.sv_tree.tag_configure('crit', foreground=MUTED)
        self.sv_tree.tag_configure('run', foreground=OK_C)
        self.sv_records, self.sv_items = [], {}

    def sv_refresh(self, quiet=False):
        self.start([Job('Servis listesi', cmd=ps_cmd('svc-list'), on_done=lambda j: self._sv_set(j.data), show_output=False)], quiet=quiet)

    def _sv_set(self, records):
        self.sv_records = [r for r in records if r.get('type') == 'svc']
        self._sv_render()

    def _sv_render(self):
        t = self.sv_tree
        t.delete(*t.get_children())
        self.sv_items = {}
        rows = pr.filter_services(self.sv_records, self.sv_q.get(), self.sv_running.get(), self.sv_third.get())
        self.sv_count.set('%d gösteriliyor · %d çalışıyor / %d' % (len(rows), sum(1 for r in self.sv_records if r.get('state') == 'Running'), len(self.sv_records))
                          if self.sv_records else '')
        for i, r in enumerate(rows):
            iid = 's%d' % i
            start = pr.SVC_START.get(r.get('start'), r.get('start', '')) + (' (gecikmeli)' if r.get('delayed') and r.get('start') == 'Auto' else '')
            tags = ('crit',) if pr.is_critical_service(r) else (('run',) if r.get('state') == 'Running' else ())
            t.insert('', 'end', iid=iid, text=r.get('display') or r.get('name'), tags=tags,
                     values=(r.get('name', ''), pr.SVC_STATE.get(r.get('state'), r.get('state', '')), start, r.get('account', ''), r.get('path', '')))
            self.sv_items[iid] = r

    def sv_action(self, op):
        sel = [self.sv_items[i] for i in self.sv_tree.selection() if i in self.sv_items]
        if not sel:
            messagebox.showinfo('Servisler', 'Önce listeden servis seçin.'); return
        if op in ('stop', 'disabled', 'restart'):
            crit = [r for r in sel if pr.is_critical_service(r)]
            if crit:
                messagebox.showwarning('Kritik servis', 'Windows için gerekli olduğundan bu işlem yapılmayacak: %s' % ', '.join(r['name'] for r in crit))
                sel = [r for r in sel if not pr.is_critical_service(r)]
        if not sel:
            return
        words = {'start': 'başlatılacak', 'stop': 'durdurulacak', 'restart': 'yeniden başlatılacak', 'auto': 'başlangıç türü Otomatik yapılacak',
                 'manual': 'başlangıç türü El ile yapılacak', 'disabled': 'DEVRE DIŞI bırakılacak'}
        if not messagebox.askyesno('Servisler', '%d servis %s:\n%s\n\nYönetici onayı (UAC) istenebilir. Devam?'
                                   % (len(sel), words[op], '\n'.join('• %s (%s)' % (r.get('display'), r['name']) for r in sel[:10]))):
            return
        self.start([Job('Servis: %s (%d)' % (op, len(sel)), cmd=ps_cmd('svc-action', ItemsB64=pr.b64_items([{'name': r['name']} for r in sel]), Op=op),
                        cancel_ok=False, on_done=lambda j: self.sv_refresh(quiet=True))])

    # ------------------------------------------------------------------ BASLANGIC
    def _tab_startup(self, f):
        head = tk.Frame(f, bg=PANEL); head.pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(head, text='Başlangıç uygulamaları', fg=FG, bg=PANEL, font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.st_count = tk.StringVar(value='')
        tk.Label(head, textvariable=self.st_count, fg=ACCENT, bg=PANEL2, font=('Segoe UI', 9, 'bold'), padx=10, pady=3).pack(side='left', padx=(10, 0))
        self.label(f, 'Windows açılırken kendiliğinden başlayan uygulamalar (Run kayıtları ve Başlangıç klasörleri). Devre dışı bırakma Görev Yöneticisi ile aynı '
                      'yöntemle yapılır: kayıt silinmez, istediğiniz zaman yeniden etkinleştirebilirsiniz. "Tüm kullanıcılar" öğeleri yönetici onayı (UAC) ister. '
                      'Değişiklik bir sonraki oturum açılışında geçerli olur.', wraplength=int(980 * self.scale)).pack(fill='x', padx=16, pady=(2, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Yenile', self.st_refresh, 'go')
        self.btn(bar, 'Devre dışı bırak', lambda: self.st_set('disable'), 'danger')
        self.btn(bar, 'Etkinleştir', lambda: self.st_set('enable'), 'normal')
        self.btn(bar, 'Dosya konumunu aç', lambda: self._open_location(self._st_sel()[0].get('command') if self._st_sel() else ''), 'ghost', action=False)
        self.btn(bar, 'Görev Yöneticisi', lambda: subprocess.Popen(['taskmgr.exe', '/7', '/startup']) if IS_WIN else None, 'ghost', action=False)
        self.btn(bar, 'AI\'ya sor', lambda: self.ai_ask_about('başlangıç öğeleri', self._st_sel(), ['name', 'enabled', 'scope', 'command']), 'ghost', action=False)
        self.st_tree = _tree(f, [('state', 'Durum', 110, 'w'), ('loc', 'Konum', 210, 'w'), ('cmd', 'Komut', 460, 'w')], ('Ad', int(240 * self.scale)))
        self.st_tree.tag_configure('off', foreground=MUTED)
        self.st_tree.tag_configure('on', foreground=OK_C)
        self.st_records, self.st_items = [], {}

    def st_refresh(self, quiet=False):
        self.start([Job('Başlangıç listesi', cmd=ps_cmd('startup-list'), on_done=lambda j: self._st_set(j.data), show_output=False)], quiet=quiet)

    def _st_set(self, records):
        self.st_records = [r for r in records if r.get('type') == 'startup']
        t = self.st_tree
        t.delete(*t.get_children())
        self.st_items = {}
        on = 0
        for i, r in enumerate(sorted(self.st_records, key=lambda r: (not r.get('enabled'), (r.get('name') or '').casefold()))):
            iid = 'st%d' % i
            on += bool(r.get('enabled'))
            t.insert('', 'end', iid=iid, text=r.get('name', ''), tags=('on',) if r.get('enabled') else ('off',),
                     values=('Etkin' if r.get('enabled') else 'Devre dışı', pr.STARTUP_LOC.get(r.get('scope'), r.get('scope', '')), r.get('command', '')))
            self.st_items[iid] = r
        self.st_count.set('%d öğe · %d etkin' % (len(self.st_records), on) if self.st_records else 'Başlangıç öğesi yok')

    def _st_sel(self):
        return [self.st_items[i] for i in self.st_tree.selection() if i in self.st_items]

    def st_set(self, op):
        sel = self._st_sel()
        if not sel:
            messagebox.showinfo('Başlangıç', 'Önce listeden öğe seçin.'); return
        user, admin = pr.split_by_admin(sel)
        jobs = []
        if user:
            jobs.append(Job('Başlangıç: %s (%d)' % (op, len(user)), cmd=ps_cmd('startup-set', ItemsB64=pr.b64_items([pr.startup_item(r) for r in user]), Op=op),
                            cancel_ok=False))
        if admin:
            jobs.append(Job('Başlangıç (tüm kullanıcılar): %s (%d)' % (op, len(admin)),
                            cmd=ps_cmd('startup-set', ItemsB64=pr.b64_items([pr.startup_item(r) for r in admin]), Op=op), cancel_ok=False, admin=True))
        jobs[-1].on_done = lambda j: self.st_refresh(quiet=True)
        self.start(jobs)


register_palette_module(globals())
