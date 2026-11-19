# -*- coding: utf-8 -*-
"""AGFO System Care — Aygit temizligi sayfasi (bagli olmayan aygitlar). App sinifinin parcasi (mixin); paylasilan adlar sc_base'den gelir."""
from sc_base import *  # noqa: F401,F403


class PhantomPage:
    # ------------------------------------------------------------------ AYGIT TEMIZLIGI (bagli olmayan aygitlar)
    PH_FILTERS = ['Tümü', '30 günden eski', '1 yıldan eski', 'Tarihi bilinmeyen']

    def _tab_phantom(self, f):
        head = tk.Frame(f, bg=PANEL); head.pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(head, text='Aygıt temizliği', fg=FG, bg=PANEL, font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.ph_chips = {}
        for key, text, color in [('total', 'bağlı olmayan aygıt', ACCENT), ('old30', '30+ gün', OK_C), ('old365', '1+ yıl', OK_C), ('caution', 'dikkat', WARN)]:
            v = tk.StringVar(value='— ' + text)
            tk.Label(head, textvariable=v, fg=color, bg=PANEL2, font=('Segoe UI', 9, 'bold'), padx=10, pady=3).pack(side='left', padx=(10, 0))
            self.ph_chips[key] = (v, text)
        self.label(f, 'Bu bilgisayara bir zamanlar bağlanmış ama şu an bağlı olmayan aygıtlar (eski USB bellekler, telefonlar, yazıcılar, '
                      'COM portları, kaldırılmış donanım). Aygıt Yöneticisi bunları gizler; birikmeleri COM port numaralarını ve sürücü listesini şişirir. '
                      'Kaldırılan aygıt yeniden takılırsa Windows onu yeni aygıt olarak tanır ve sürücüsünü yeniden kurar. '
                      '"Dikkat" (turuncu) satırlar sistem/yazılım aygıtlarıdır; varsayılan olarak seçilmez.', wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(2, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Tara', self.ph_scan, 'go')
        self.btn(bar, '30 günden eskileri seç', lambda: self.ph_tree.set_all(True, lambda i: bool((self.ph_tree.payload.get(i) or {}).get('default'))), 'ghost', action=False)
        self.btn(bar, 'Tümünü seç', lambda: self.ph_tree.set_all(True), 'ghost', action=False)
        self.btn(bar, 'Seçimi kaldır', lambda: self.ph_tree.set_all(False), 'ghost', action=False)
        self.btn(bar, 'Seçilenleri kaldır', self.ph_remove, 'danger')
        self.ph_rp = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text='Önce geri yükleme noktası (24 saat sınırı aşılarak)', variable=self.ph_rp).pack(side='left', padx=(10, 0))
        self.ph_count = tk.StringVar(value='')
        tk.Label(bar, textvariable=self.ph_count, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(side='right')
        flt = tk.Frame(f, bg=PANEL); flt.pack(fill='x', padx=16, pady=(6, 0))
        tk.Label(flt, text='Göster:', fg=FG, bg=PANEL).pack(side='left')
        self.ph_filter = ttk.Combobox(flt, state='readonly', width=22, values=self.PH_FILTERS); self.ph_filter.current(0)
        self.ph_filter.pack(side='left', padx=6)
        self.ph_filter.bind('<<ComboboxSelected>>', lambda _e: self._ph_render())
        tk.Label(flt, text='Ara:', fg=FG, bg=PANEL).pack(side='left', padx=(10, 0))
        self.ph_q = tk.StringVar()
        ttk.Entry(flt, textvariable=self.ph_q, width=30).pack(side='left', padx=6)
        self.ph_q.trace_add('write', lambda *_: self._ph_render())
        cols = [('seen', 'Son görülme', 145, 'w'), ('age', 'Gün', 60, 'e'), ('status', 'Durum', 170, 'w'), ('id', 'Aygıt örnek kimliği', 480, 'w')]
        self.ph_tree = CheckTree(f, cols, first=('Aygıt', 330), on_change=self._ph_count)
        self.ph_tree.pack(fill='both', expand=True, padx=16, pady=8)
        self.ph_groups, self.ph_sel = {}, None

    def ph_scan(self):
        def done(job):
            devs = [d for d in job.data if d.get('type') == 'phantom']
            self.ph_groups, st = core.build_phantom_view(devs)
            for k, (v, text) in self.ph_chips.items():
                v.set('%d %s' % (st.get(k, 0), text))
            self.ph_sel = None
            self._ph_render()
        self.start([Job('Bağlı olmayan aygıtlar', cmd=ps_cmd('phantom-list'), on_done=done, show_output=False)])

    def _ph_render(self):
        t = self.ph_tree
        if self.ph_sel is None:
            self.ph_sel = {d['id'] for g in self.ph_groups.values() for d in g if d['default']}
        elif t.labels:
            visible = {pl['id'] for pl in t.payload.values() if pl}
            self.ph_sel = {pl['id'] for pl in t.checked_payloads() if pl} | (self.ph_sel - visible)
        t.clear()
        mode, q = self.ph_filter.get(), self.ph_q.get().strip().lower()
        for n, (cls, items) in enumerate(self.ph_groups.items()):
            show = []
            for d in items:
                if mode == '30 günden eski' and not (d['age'] is not None and d['age'] >= 30):
                    continue
                if mode == '1 yıldan eski' and not (d['age'] is not None and d['age'] >= 365):
                    continue
                if mode == 'Tarihi bilinmeyen' and d['age'] is not None:
                    continue
                if q and q not in ((d.get('name') or '') + ' ' + d['id'] + ' ' + cls).lower():
                    continue
                show.append(d)
            if not show:
                continue
            gid = 'g%d' % n
            t.add(gid, '%s (%d)' % (cls, len(show)), ('', '', '', ''), tags=('group',), open_=True)
            for m, d in enumerate(show):
                t.add('%s_%d' % (gid, m), d.get('name') or '(adsız aygıt)', (d['seen'] or 'bilinmiyor', '' if d['age'] is None else d['age'],
                      'Dikkat: sistem aygıtı' if d['caution'] else 'Bağlı değil', d['id']), parent=gid, checked=d['id'] in self.ph_sel,
                      tags=('risky',) if d['caution'] else (), payload=d)
        t.refresh_marks()
        self._ph_count()

    def _ph_count(self):
        n = len([p for p in self.ph_tree.checked_payloads() if p])
        self.ph_count.set('%d aygıt seçili' % n if n else '')

    def ph_remove(self):
        sel = [p for p in self.ph_tree.checked_payloads() if p]
        if not sel:
            messagebox.showinfo('Aygıt temizliği', 'Önce tarayın ve kaldırılacak aygıtları işaretleyin.'); return
        if not self.need_admin('phantom-remove'):
            return
        caution = [p for p in sel if p['caution']]
        msg = '%d bağlı olmayan aygıt kaldırılacak.\nAygıtlar yeniden takılırsa Windows onları yeni aygıt olarak tanır.' % len(sel)
        if caution:
            msg += '\n\nDİKKAT: %d sistem/yazılım aygıtı seçili (ör. %s).' % (len(caution), caution[0].get('name') or caution[0]['id'])
        if not messagebox.askyesno('Aygıt temizliği', msg + '\n\nDevam edilsin mi?'):
            return
        jobs = []
        if self.ph_rp.get():
            jobs.append(Job('Geri yükleme noktası', cmd=ps_cmd('restore-point', ForceRestorePoint='yes'), cancel_ok=False))
        jobs.append(Job('Bağlı olmayan aygıtları kaldır (%d)' % len(sel), cmd=ps_cmd('phantom-remove', InstanceIds='|'.join(p['id'] for p in sel)),
                        cancel_ok=False, on_done=lambda j: self.ph_scan()))
        self.start(jobs)


register_palette_module(globals())
