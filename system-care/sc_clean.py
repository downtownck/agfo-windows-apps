# -*- coding: utf-8 -*-
"""AGFO System Care — Temizlik sayfasi (BleachBit). App sinifinin parcasi (mixin); paylasilan adlar sc_base'den gelir."""
from sc_base import *  # noqa: F401,F403


class CleanPage:
    # ------------------------------------------------------------------ TEMIZLIK (BleachBit)
    def _tab_clean(self, f):
        self.bb_state = tk.StringVar(value='BleachBit motoru: denetleniyor...')
        tk.Label(f, textvariable=self.bb_state, fg=MUTED, bg=PANEL, font=('Segoe UI', 9)).pack(anchor='w', padx=16, pady=(12, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Temizleyicileri yükle', self.bb_load, 'ghost')
        self.btn(bar, 'Güvenli öneriyi seç', self.bb_preset, 'ghost')
        self.btn(bar, 'Seçimi kaldır', lambda: self.bb_tree.set_all(False), 'ghost', action=False)
        self.btn(bar, 'Önizle (silmez)', lambda: self.bb_run('preview'))
        self.btn(bar, 'Seçilenleri temizle', lambda: self.bb_run('clean'), 'danger')
        self.bb_count = tk.StringVar(value='')
        tk.Label(bar, textvariable=self.bb_count, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(side='right')
        cols = [('opt', 'Kimlik', 260, 'w'), ('note', 'Not', 380, 'w')]
        self.bb_tree = CheckTree(f, cols, first=('Temizleyici / seçenek', 360), on_change=self._bb_count)
        self.bb_tree.pack(fill='both', expand=True, padx=16, pady=8)
        self.bb_summary = tk.StringVar(value='Turuncu satırlar kullanıcı verisini (parola, çerez, oturum) siler veya saatler sürer; güvenli öneriye dahil edilmez.')
        tk.Label(f, textvariable=self.bb_summary, fg=MUTED, bg=PANEL, font=('Segoe UI', 9), anchor='w', justify='left').pack(fill='x', padx=16, pady=(0, 10))

    def _bb_count(self):
        n = len([i for i in self.bb_tree.checked if not self.bb_tree.tree.get_children(i)])
        self.bb_count.set('%d seçenek seçili' % n if n else '')

    def bb_load(self):
        bb = self.engines.get('bleachbit', {}).get('path')
        if not bb:
            if messagebox.askyesno('BleachBit yok', 'BleachBit motoru kurulu değil. Resmî taşınabilir paket şimdi kurulsun mu? (yönetici gerekmez)'):
                self._engine_install_one('bleachbit')
            return
        self.start([Job('BleachBit temizleyicileri', cmd=[bb, '--list-cleaners'], on_done=self._bb_loaded, show_output=False)])

    def _engine_install_one(self, key):
        j = self.install_engine_job(key)
        j.on_done = lambda _j: self.refresh_engines()
        self.start([j])

    def _bb_loaded(self, job):
        cleaners = core.parse_bleachbit_cleaners(job.lines)
        if not cleaners:
            self.write('BleachBit temizleyici listesi okunamadı.\n')
            return
        saved = set(self.settings.get('bb_selected') or [])
        t = self.bb_tree
        t.clear()
        order = sorted(cleaners, key=lambda c: (c not in ('system', 'windows_explorer'), core.bb_label(c).lower()))
        for cl in order:
            t.add('c:' + cl, core.bb_label(cl), (cl, '%d seçenek' % len(cleaners[cl])), tags=('group',))
            for op in cleaners[cl]:
                key = cl + '.' + op
                risky = core.bb_is_risky(cl, op)
                note = 'Dikkat: kullanıcı verisi / çok uzun sürebilir' if risky else ''
                on = (key in saved) if saved else core.bb_default_selected(cl, op)
                t.add('o:' + key, core.bb_label(cl, op), (key, note), parent='c:' + cl, checked=on, tags=('risky',) if risky else (), payload=key)
        t.refresh_marks()
        self.bb_loaded = True
        self._bb_count()
        self.write('BleachBit: %d temizleyici, %d seçenek yüklendi.\n' % (len(cleaners), sum(len(v) for v in cleaners.values())))

    def bb_preset(self):
        if not self.bb_loaded:
            self.bb_load(); return
        self.bb_tree.set_all(True, lambda iid: core.bb_default_selected(*iid[2:].split('.', 1)))

    def bb_run(self, mode):
        bb = self.engines.get('bleachbit', {}).get('path')
        if not bb or not self.bb_loaded:
            self.bb_load(); return
        sel = self.bb_tree.checked_payloads()
        if not sel:
            messagebox.showinfo('Temizlik', 'En az bir seçenek işaretleyin.'); return
        self.settings['bb_selected'] = sel
        core.save_settings(self.settings)
        if mode == 'clean':
            risky = [s for s in sel if core.bb_is_risky(*s.split('.', 1))]
            msg = '%d seçenek temizlenecek. Silinen veriler geri alınamaz.' % len(sel)
            if risky:
                msg += '\n\nDİKKAT — şu seçenekler kullanıcı verisi siler veya çok uzun sürer:\n  ' + '\n  '.join(risky[:12])
            if not messagebox.askyesno('Temizliği onaylayın', msg + '\n\nÖnizleme yaptınız mı? Devam edilsin mi?'):
                return
        flag = '--preview' if mode == 'preview' else '--clean'
        title = 'BleachBit ' + ('önizleme' if mode == 'preview' else 'temizlik')
        self.start([Job(title, cmd=[bb, flag] + sel, on_done=self._bb_done, cancel_ok=(mode == 'preview'))])

    def _bb_done(self, job):
        s = core.parse_bleachbit_summary(job.lines)
        self.bb_summary.set(('Sonuç: ' + ' · '.join(s)) if s else 'Tamamlandı (çıktı günlükte).')


register_palette_module(globals())
