# -*- coding: utf-8 -*-
"""AGFO System Care — Bloatware sayfasi (Store/AppX + masaustu). App sinifinin parcasi (mixin); paylasilan adlar sc_base'den gelir."""
from sc_base import *  # noqa: F401,F403


class BloatPage:
    # ------------------------------------------------------------------ BLOATWARE (Store/AppX + masaustu)
    BLOAT_FILTERS = ['Önerilen ve dikkat', 'Yalnız önerilen', 'Tümü (korunanlar dahil)']

    def _tab_bloat(self, f):
        head = tk.Frame(f, bg=PANEL); head.pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(head, text='Bloatware temizliği', fg=FG, bg=PANEL, font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.bloat_chips = {}
        for key, text, color in [('rec', 'önerilen', OK_C), ('caution', 'dikkat', WARN), ('other', 'diğer', MUTED), ('protected', 'korunan', MUTED)]:
            v = tk.StringVar(value='— ' + text)
            tk.Label(head, textvariable=v, fg=color, bg=PANEL2, font=('Segoe UI', 9, 'bold'), padx=10, pady=3).pack(side='left', padx=(10, 0))
            self.bloat_chips[key] = (v, text)
        self.label(f, 'Windows ile gelen gereksiz Store uygulamaları ve ön yüklü masaüstü yazılımları. "Önerilen" grubu güvenle kaldırılabilir; '
                      '"Dikkat" grubunu kullanmıyorsanız seçin. Microsoft Store, WinGet, çalışma zamanları ve sürücü yardımcıları korunur. '
                      'Kaldırılan Store uygulamaları Microsoft Store\'dan yeniden kurulabilir.', wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(2, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Tara', self.bloat_scan, 'go')
        self.btn(bar, 'Önerilenleri seç', lambda: self.bloat_tree.set_all(True, lambda i: (self.bloat_tree.payload.get(i) or {}).get('cat') == 'rec'), 'ghost', action=False)
        self.btn(bar, 'Seçimi kaldır', lambda: self.bloat_tree.set_all(False), 'ghost', action=False)
        self.btn(bar, 'Seçilenleri kaldır', self.bloat_remove, 'danger')
        self.bloat_prov = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text='Yeni kullanıcı hesapları için de kaldır (yönetici)', variable=self.bloat_prov).pack(side='left', padx=(10, 0))
        self.bloat_rp = tk.BooleanVar(value=self.admin)
        ttk.Checkbutton(bar, text='Önce geri yükleme noktası', variable=self.bloat_rp).pack(side='left', padx=(10, 0))
        self.bloat_count = tk.StringVar(value='')
        tk.Label(bar, textvariable=self.bloat_count, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(side='right')
        flt = tk.Frame(f, bg=PANEL); flt.pack(fill='x', padx=16, pady=(6, 0))
        tk.Label(flt, text='Göster:', fg=FG, bg=PANEL).pack(side='left')
        self.bloat_filter = ttk.Combobox(flt, state='readonly', width=26, values=self.BLOAT_FILTERS); self.bloat_filter.current(0)
        self.bloat_filter.pack(side='left', padx=6)
        self.bloat_filter.bind('<<ComboboxSelected>>', lambda _e: self._bloat_render())
        tk.Label(flt, text='Ara:', fg=FG, bg=PANEL).pack(side='left', padx=(10, 0))
        self.bloat_q = tk.StringVar()
        ttk.Entry(flt, textvariable=self.bloat_q, width=30).pack(side='left', padx=6)
        self.bloat_q.trace_add('write', lambda *_: self._bloat_render())
        cols = [('pkg', 'Paket / program', 230, 'w'), ('pub', 'Yayıncı', 150, 'w'), ('ver', 'Sürüm', 80, 'w'), ('type', 'Tür', 210, 'w'), ('note', 'Not', 280, 'w')]
        self.bloat_tree = CheckTree(f, cols, first=('Uygulama', 270), on_change=self._bloat_count)
        self.bloat_tree.pack(fill='both', expand=True, padx=16, pady=8)
        self.bloat_groups, self.bloat_sel = {}, None

    def bloat_scan(self):
        store = {}

        def got_appx(job):
            store['appx'] = [d for d in job.data if d.get('type') == 'appx']

        def work(runner, job):
            job.data = core.annotate_programs(core.read_programs())
            return 0

        def done(job):
            self.programs = job.data or self.programs
            self.bloat_groups = core.build_bloat_view(store.get('appx', []), job.data or [])
            for k, (v, text) in self.bloat_chips.items():
                v.set('%d %s' % (len(self.bloat_groups.get(k, [])), text))
            self.bloat_sel = None
            self._bloat_render()
        self.start([Job('Store / ön yüklü uygulamalar', cmd=ps_cmd('appx-list'), on_done=got_appx, show_output=False),
                    Job('Masaüstü bloatware taraması', func=work, on_done=done, cancel_ok=False)])

    @staticmethod
    def _bloat_key(it):
        return (it['kind'], it.get('full') or it.get('name'))

    def _bloat_render(self):
        t = self.bloat_tree
        if self.bloat_sel is None:
            self.bloat_sel = {self._bloat_key(it) for it in self.bloat_groups.get('rec', [])}
        elif t.labels:
            visible = {self._bloat_key(pl) for pl in t.payload.values() if pl}
            checked = {self._bloat_key(pl) for pl in t.checked_payloads() if pl}
            self.bloat_sel = checked | (self.bloat_sel - visible)
        t.clear()
        mode = self.bloat_filter.get()
        cats = {'Önerilen ve dikkat': ('rec', 'caution'), 'Yalnız önerilen': ('rec',)}.get(mode, ('rec', 'caution', 'other', 'protected'))
        q = self.bloat_q.get().strip().lower()
        tags = {'rec': 'st_new', 'caution': 'st_warn', 'other': 'st_ok', 'protected': 'st_old'}
        for cat in cats:
            items = [it for it in self.bloat_groups.get(cat, []) if not q or q in (it['label'] + ' ' + it.get('name', '') + ' ' + it.get('pub', '')).lower()]
            if not items:
                continue
            gid = 'g:' + cat
            t.add(gid, '%s (%d)' % (core.BLOAT_CAT[cat], len(items)), ('', '', '', '', ''), tags=(tags[cat], 'group'), checkable=(cat != 'protected'), open_=(cat != 'protected'))
            for n, it in enumerate(items):
                if it['kind'] == 'appx':
                    typ = 'Store · ön yüklü (tüm kullanıcılar)' if it.get('provisioned') else 'Store uygulaması'
                else:
                    typ = 'Masaüstü programı'
                t.add('%s:%d' % (cat, n), it['label'], (it.get('name', ''), it.get('pub', ''), it.get('ver', ''), typ, it.get('note', '')), parent=gid,
                      checked=self._bloat_key(it) in self.bloat_sel, checkable=(cat != 'protected'), tags=(tags[cat],), payload=it)
        t.refresh_marks()
        self._bloat_count()

    def _bloat_count(self):
        n = len([p for p in self.bloat_tree.checked_payloads() if p])
        self.bloat_count.set('%d seçili' % n if n else '')

    def bloat_remove(self):
        sel = [p for p in self.bloat_tree.checked_payloads() if p and p.get('cat') != 'protected']
        if not sel:
            messagebox.showinfo('Bloatware', 'Önce tarayın ve kaldırılacak uygulamaları işaretleyin.'); return
        appx = [p for p in sel if p['kind'] == 'appx']
        win = [p for p in sel if p['kind'] == 'win32']
        caution = [p for p in sel if p['cat'] == 'caution']
        msg = '%d uygulama kaldırılacak:\n  %s%s' % (len(sel), '\n  '.join(p['label'] for p in sel[:15]), '\n  ...' if len(sel) > 15 else '')
        if caution:
            msg += '\n\nDİKKAT grubundan %d seçim var (ör. %s). Kullanıyorsanız vazgeçin.' % (len(caution), caution[0]['label'])
        if win:
            msg += '\n\nMasaüstü programları kendi kaldırıcılarıyla sırayla kaldırılır (mümkünse sessiz).'
        prov = self.bloat_prov.get()
        if prov and not self.admin:
            msg += '\n\nNot: "yeni kullanıcılar için de" seçeneği yönetici ister; şimdi yalnızca bu kullanıcıdan kaldırılacak.'
        if not messagebox.askyesno('Bloatware kaldırma', msg + '\n\nDevam edilsin mi?'):
            return
        jobs = []
        if self.bloat_rp.get():
            if self.admin:
                jobs.append(Job('Geri yükleme noktası', cmd=ps_cmd('restore-point'), cancel_ok=False))
            else:
                self.write('Geri yükleme noktası yönetici ister; atlandı.\n')
        if appx:
            jobs.append(Job('Store uygulamalarını kaldır (%d)' % len(appx), cmd=ps_cmd('appx-remove', Packages='|'.join(p['full'] for p in appx),
                                                                                    Provisioned='yes' if (prov and self.admin) else 'no'), cancel_ok=False))
        for p in win:
            exe, params = core.build_uninstall(p['prog'], True)
            jobs.append(Job('Kaldır: ' + p['name'], shell=(exe, params), after=self._after_uninstall(p['prog'])))
        jobs[-1].on_done = lambda j: self.bloat_scan()
        self.start(jobs)


register_palette_module(globals())
