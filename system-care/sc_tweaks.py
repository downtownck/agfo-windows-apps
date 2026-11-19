# -*- coding: utf-8 -*-
"""AGFO System Care — Ince ayarlar sayfasi (katalog WinCleaner, MIT). App sinifinin parcasi (mixin); paylasilan adlar sc_base'den gelir."""
from sc_base import *  # noqa: F401,F403


class TweaksPage:
    # ------------------------------------------------------------------ INCE AYARLAR (3.7.0; katalog WinCleaner'dan, MIT)
    TW_FILTERS = ['Tümü', 'Uygulanmamış', 'Uygulanmış', 'Seçili olanlar']

    def _tab_tweaks(self, f):
        head = tk.Frame(f, bg=PANEL); head.pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(head, text='İnce ayarlar', fg=FG, bg=PANEL, font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.tw_chips = {}
        for key, text, color in [('applied', 'uygulanmış', OK_C), ('not', 'uygulanmamış', ACCENT), ('partial', 'kısmen', WARN), ('total', 'ayar', MUTED)]:
            v = tk.StringVar(value='— ' + text)
            tk.Label(head, textvariable=v, fg=color, bg=PANEL2, font=('Segoe UI', 9, 'bold'), padx=10, pady=3).pack(side='left', padx=(10, 0))
            self.tw_chips[key] = (v, text)
        self.label(f, 'Gizlilik, oyun, görünüm, Windows 11 arayüzü, ağ ve hizmet ayarları tek listede. Her değişiklikten önce mevcut değer kaydedilir; '
                      '"Son değişikliği geri al" ve "Geçmiş" ayarları birebir eski hâline döndürür. "Varsayılana döndür" Windows\'un varsayılan değerini yazar. '
                      'Turuncu satırlar kullanımınıza göre sorun çıkarabilir; "Tehlikeli" satırlar yalnızca aşağıdaki izinle uygulanır.',
                   wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(2, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Durumu oku', self.tw_read, 'ghost')
        tk.Label(bar, text='Ön ayar:', fg=FG, bg=PANEL).pack(side='left', padx=(6, 0))
        self.tw_preset = ttk.Combobox(bar, state='readonly', width=24, values=[p['name'] for p in tweaks.cat.PRESETS])
        self.tw_preset.pack(side='left', padx=6)
        self.tw_preset.bind('<<ComboboxSelected>>', lambda _e: self.tw_preset_info())
        self.btn(bar, 'Ön ayarı seç', self.tw_pick_preset, 'ghost', action=False)
        self.btn(bar, 'Seçimi kaldır', lambda: self.tw_tree.set_all(False), 'ghost', action=False)
        self.btn(bar, 'Seçilenleri uygula', lambda: self.tw_apply('apply'), 'go')
        self.btn(bar, 'Seçilenleri varsayılana döndür', lambda: self.tw_apply('default'), 'danger')
        self.tw_count = tk.StringVar(value='')
        tk.Label(bar, textvariable=self.tw_count, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(side='right')
        bar2 = tk.Frame(f, bg=PANEL); bar2.pack(fill='x', padx=16, pady=(4, 0))
        self.btn(bar2, 'Son değişikliği geri al', self.tw_undo_last)
        self.btn(bar2, 'Geçmiş…', self.tw_history, 'ghost', action=False)
        self.btn(bar2, 'Profili dışa aktar', self.tw_export, 'ghost', action=False)
        self.btn(bar2, 'Profili içe aktar', self.tw_import, 'ghost', action=False)
        self.tw_rp = tk.BooleanVar(value=self.admin)
        ttk.Checkbutton(bar2, text='Önce geri yükleme noktası', variable=self.tw_rp).pack(side='left', padx=(10, 0))
        self.tw_danger = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar2, text='Tehlikeli ayarlara izin ver', variable=self.tw_danger).pack(side='left', padx=(10, 0))
        flt = tk.Frame(f, bg=PANEL); flt.pack(fill='x', padx=16, pady=(6, 0))
        tk.Label(flt, text='Göster:', fg=FG, bg=PANEL).pack(side='left')
        self.tw_filter = ttk.Combobox(flt, state='readonly', width=18, values=self.TW_FILTERS); self.tw_filter.current(0)
        self.tw_filter.pack(side='left', padx=6)
        self.tw_filter.bind('<<ComboboxSelected>>', lambda _e: self._tw_render())
        tk.Label(flt, text='Ara:', fg=FG, bg=PANEL).pack(side='left', padx=(10, 0))
        self.tw_q = tk.StringVar()
        ttk.Entry(flt, textvariable=self.tw_q, width=28).pack(side='left', padx=6)
        self.tw_q.trace_add('write', lambda *_: self._tw_render())
        cols = [('state', 'Durum', 120, 'w'), ('risk', 'Risk', 80, 'w'), ('cur', 'Şu an / hedef', 170, 'w'), ('need', 'Gerekir', 170, 'w'), ('desc', 'Açıklama', 420, 'w')]
        self.tw_tree = CheckTree(f, cols, first=('Ayar', 330), height=10, on_change=self._tw_count)
        self.tw_tree.pack(fill='both', expand=True, padx=16, pady=(8, 2))
        self.tw_tree.tree.bind('<<TreeviewSelect>>', lambda _e: self._tw_detail(), add=True)
        self.tw_info = tk.StringVar(value='Bir satır seçin: açıklaması burada görünür.')
        tk.Label(f, textvariable=self.tw_info, fg=MUTED, bg=PANEL, font=('Segoe UI', 9), justify='left', anchor='w',
                 wraplength=int(1100 * self.scale)).pack(fill='x', padx=16)
        dns = tk.Frame(f, bg=PANEL2, padx=10, pady=6); dns.pack(fill='x', padx=16, pady=(6, 10))
        tk.Label(dns, text='DNS', fg=ACCENT, bg=PANEL2, font=('Segoe UI', 9, 'bold')).pack(side='left')
        self.dns_choice = ttk.Combobox(dns, state='readonly', width=34, values=[p[1] for p in tweaks.DNS_PRESETS] + ['Özel adresler…'])
        self.dns_choice.current(0); self.dns_choice.pack(side='left', padx=6)
        self.dns_custom = tk.StringVar()
        ttk.Entry(dns, textvariable=self.dns_custom, width=24).pack(side='left', padx=(0, 6))
        for txt, cmd in (('Bağdaştırıcıları göster', self.dns_list), ('DNS\'i uygula (yönetici)', self.dns_apply), ('DNS önbelleğini temizle', self.dns_flush)):
            b = self.mkbtn(dns, txt, cmd, 'normal', small=True)
            b.pack(side='left', padx=(0, 6)); self.action_buttons.append(b)
        self.dns_state = tk.StringVar(value='')
        tk.Label(dns, textvariable=self.dns_state, fg=FG, bg=PANEL2, font=('Segoe UI', 9), anchor='w').pack(side='left', fill='x', expand=True)
        self.tw_items = [it for it in tweaks.item_by_id().values()]
        self.tw_reads, self.tw_states, self.tw_sel, self.tw_read_once, self.dns_adapters = {}, {}, set(), False, []
        self.tw_build = tweaks.windows_build()
        self._tw_tab = f
        self._tw_render()

    def _tw_on_tab(self, _e=None):
        try:
            if self.tabs.nametowidget(self.tabs.select()) is self._tw_tab and not self.tw_read_once and not self.busy:
                self.tw_read()
        except Exception:
            pass

    def _tw_visible_items(self):
        return [it for it in self.tw_items if tweaks.os_compatible(it, self.tw_build)]

    def _tw_target_text(self, it):
        if it.get('kind') == 'service':
            cur = tweaks.current_text(it, self.tw_reads)
            return '%s → %s' % (cur or '?', tweaks.START_NAME.get(it['start'], it['start']))
        return ''

    def _tw_need_text(self, it):
        need = []
        if tweaks.needs_admin_item(it):
            need.append('yönetici')
        if it.get('reboot'):
            need.append('yeniden başlatma')
        if it.get('explorer'):
            need.append('Gezgin yenileme')
        if it.get('anticheat'):
            need.append('hile koruması uyarısı')
        return ', '.join(need)

    def _tw_render(self):
        t = self.tw_tree
        if t.labels:
            visible = {pl['id'] for pl in t.payload.values() if pl}
            checked = {pl['id'] for pl in t.checked_payloads() if pl}
            self.tw_sel = checked | (self.tw_sel - visible)
        t.clear()
        mode = self.tw_filter.get()
        q = self.tw_q.get().strip().lower()
        tag_of = {'applied': 'st_new', 'partial': 'st_warn', 'missing': 'st_old', 'unknown': 'st_ok', 'not': 'st_ok'}
        items = self._tw_visible_items()
        for key, title in tweaks.CATEGORIES:
            rows = []
            for it in items:
                if it['cat'] != key:
                    continue
                st = self.tw_states.get(it['id'], '')
                if mode == 'Uygulanmamış' and st not in ('not', 'partial'):
                    continue
                if mode == 'Uygulanmış' and st != 'applied':
                    continue
                if mode == 'Seçili olanlar' and it['id'] not in self.tw_sel:
                    continue
                hay = ' '.join((it['name'], it.get('desc', ''), it['id'], it['svc'] if isinstance(it.get('svc'), str) else ''))
                if q and q not in hay.lower():
                    continue
                rows.append((it, st))
            if not rows:
                continue
            gid = 'g:' + key
            t.add(gid, '%s (%d)' % (title, len(rows)), ('', '', '', '', ''), tags=('group',), open_=True)
            for it, st in rows:
                blocked = it['risk'] == 'blocked'
                tags = (tag_of.get(st, 'st_ok'),)
                if it['risk'] in ('caution', 'danger'):
                    tags = tags + ('risky',)
                label = it['name'] + (' [%s]' % tweaks.SERVICE_GROUP.get(it.get('group', ''), it.get('group', '')) if it.get('kind') == 'service' else '')
                t.add('t:' + it['id'], label, (tweaks.STATE_NAME.get(st, '—'), tweaks.RISK_NAME[it['risk']], self._tw_target_text(it),
                                              'değiştirilemez' if blocked else self._tw_need_text(it), it.get('desc', '')),
                      parent=gid, checked=it['id'] in self.tw_sel and not blocked, checkable=not blocked, tags=tags, payload=it)
        t.refresh_marks()
        self._tw_count()
        counts = {'applied': 0, 'not': 0, 'partial': 0}
        for it in items:
            st = self.tw_states.get(it['id'])
            if st in counts:
                counts[st] += 1
        for k, (v, text) in self.tw_chips.items():
            v.set('%d %s' % (len(items) if k == 'total' else counts[k], text) if (self.tw_states or k == 'total') else '— ' + text)

    def _tw_count(self):
        n = len([p for p in self.tw_tree.checked_payloads() if p])
        self.tw_count.set('%d seçili' % n if n else '')

    def _tw_detail(self):
        sel = self.tw_tree.tree.selection()
        it = self.tw_tree.payload.get(sel[0]) if sel else None
        if not it:
            return
        extra = []
        if it.get('kind') == 'service':
            extra.append('Hizmet: %s, önerilen başlangıç: %s' % (it['svc'], tweaks.START_NAME.get(it['start'], it['start'])))
        need = self._tw_need_text(it)
        if need:
            extra.append('Gerekir: ' + need)
        self.tw_info.set('%s — %s%s' % (it['name'], it.get('desc', ''), ('   (' + '; '.join(extra) + ')') if extra else ''))

    def tw_preset_info(self):
        p = next((p for p in tweaks.cat.PRESETS if p['name'] == self.tw_preset.get()), None)
        if p:
            self.tw_info.set('%s: %s (%d ayar, %d hizmet)' % (p['name'], p['desc'], len(p['tweaks']), len(p['services'])))

    def tw_pick_preset(self):
        p = next((p for p in tweaks.cat.PRESETS if p['name'] == self.tw_preset.get()), None)
        if not p:
            messagebox.showinfo('Ön ayar', 'Önce listeden bir ön ayar seçin.'); return
        ids = set(tweaks.preset_items(p['id']))
        known = {it['id'] for it in self._tw_visible_items()}
        self.tw_sel = ids & known
        self.tw_filter.current(0)
        self.tw_tree.clear()
        self._tw_render()
        self.write('Ön ayar "%s": %d ayar işaretlendi (bu Windows sürümüne uymayanlar atlandı). Uygulamak için "Seçilenleri uygula".\n' % (p['name'], len(self.tw_sel)))

    def _plan_file(self, ops, tag):
        d = core.APP_DATA_DIR / 'plans'
        d.mkdir(parents=True, exist_ok=True)
        old = sorted(d.glob('*.json'))
        for p in old[:-20]:
            try:
                p.unlink()
            except OSError:
                pass
        path = d / ('%s-%s.json' % (datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'), tag))
        path.write_text(json.dumps({'ops': ops}, ensure_ascii=False), encoding='utf-8')
        return str(path)

    def tw_read(self):
        items = self._tw_visible_items()
        plan = tweaks.read_plan(items)
        path = self._plan_file(plan, 'read')

        def done(job):
            self.tw_read_once = True
            self.tw_reads = tweaks.reads_by_ref(job.data)
            if not self.tw_reads:
                self.write('İnce ayar durumu okunamadı (kod %s).\n' % job.code)
            self.tw_states = {it['id']: tweaks.item_state(it, self.tw_reads) for it in items} if self.tw_reads else {}
            self._tw_render()
        self.start([Job('İnce ayar durumu', cmd=ps_cmd('tweak-read', PlanFile=path), on_done=done, show_output=False, cancel_ok=True)], quiet=True)

    def tw_apply(self, mode):
        sel = [p for p in self.tw_tree.checked_payloads() if p and p['risk'] != 'blocked']
        if not sel:
            messagebox.showinfo('İnce ayarlar', 'Önce listeden ayar işaretleyin (veya bir ön ayar seçin).'); return
        danger = [p for p in sel if p['risk'] == 'danger']
        if danger and not self.tw_danger.get():
            messagebox.showwarning('Tehlikeli ayar', 'Seçimde tehlikeli ayar var (%s). Uygulamak için önce "Tehlikeli ayarlara izin ver" kutusunu işaretleyin.'
                                   % ', '.join(p['name'] for p in danger[:3]))
            return
        if mode == 'default':
            svc = [p for p in sel if p.get('kind') == 'service' or 'svc' in p]
            sel = [p for p in sel if p not in svc]
            if svc:
                self.write('Hizmetlerin Windows varsayılanı sürüme göre değiştiği için "varsayılana döndür" hizmetlere uygulanmaz; '
                           'hizmet değişikliklerini Geçmiş\'ten geri alın (%d hizmet atlandı).\n' % len(svc))
            if not sel:
                messagebox.showinfo('İnce ayarlar', 'Hizmetler geçmişten geri alınır ("Geçmiş…").'); return
        skipped = []
        if not self.admin and not IS_WIN:
            skipped = [p for p in sel if tweaks.needs_admin_item(p)]
            if skipped:
                rest = [p for p in sel if p not in skipped]
                if not rest:
                    if messagebox.askyesno('Yönetici gerekli', 'Seçilen ayarlar yönetici yetkisi ister. Uygulama yönetici olarak yeniden açılsın mı?'):
                        self.elevate()
                    return
                if not messagebox.askyesno('Yönetici gerekli', '%d ayar yönetici ister ve atlanacak; yalnızca %d kullanıcı ayarı uygulanacak.\n'
                                           'Tümü için uygulamayı yönetici olarak açın. Şimdilik devam edilsin mi?' % (len(skipped), len(rest))):
                    return
                sel = rest
        anti = [p for p in sel if p.get('anticheat')] if mode == 'apply' else []
        if anti and not messagebox.askyesno('Hile koruması uyarısı', 'Şu ayarlar bazı rekabetçi oyunların hile koruması (anti-cheat) tarafından '
                                            'sorun olarak görülebilir:\n  ' + '\n  '.join(p['name'] for p in anti) + '\n\nYine de uygulansın mı?'):
            return
        verb = 'uygulanacak' if mode == 'apply' else 'Windows varsayılanına döndürülecek'
        msg = '%d ayar %s:\n  %s%s' % (len(sel), verb, '\n  '.join(p['name'] for p in sel[:16]), '\n  ...' if len(sel) > 16 else '')
        caution = [p for p in sel if p['risk'] in ('caution', 'danger')]
        if caution and mode == 'apply':
            msg += '\n\nDİKKAT/TEHLİKELİ: %s' % ', '.join(p['name'] for p in caution[:5])
        msg += '\n\nÖnceki değerler kaydedilir; "Son değişikliği geri al" ile birebir geri dönülür.'
        if not messagebox.askyesno('İnce ayarları onaylayın', msg + '\n\nDevam edilsin mi?'):
            return
        plan = tweaks.build_write_plan(sel, mode)
        errs = tweaks.validate_ops(plan)
        if errs:
            messagebox.showerror('Plan hatası', '\n'.join(errs[:6])); return
        self._tw_run(plan, ('Uygula: ' if mode == 'apply' else 'Varsayılana döndür: ') + ', '.join(p['name'] for p in sel[:3]) + (' …' if len(sel) > 3 else ''),
                     rp=self.tw_rp.get())

    def _tw_run(self, plan, title, rp=False, undo_sid=None):
        path = self._plan_file(plan, 'write')
        jobs = []
        if rp:
            if self.admin or IS_WIN:            # 4.0: yonetici degilse UAC ile
                jobs.append(Job('Geri yükleme noktası', cmd=ps_cmd('restore-point'), cancel_ok=False))
            else:
                self.write('Geri yükleme noktası yönetici ister; atlandı.\n')

        def done(job):
            sess = tweaks.record_session(core.APP_DATA_DIR, title, plan, job.data)
            res = tweaks.write_results(job.data)
            ok = sum(1 for r in res if r.get('ok'))
            self.write('İnce ayarlar: %d/%d işlem tamam%s.\n' % (ok, len(plan), '' if sess else ' (geçmişe kaydedilecek değişiklik yok)'))
            if undo_sid and ok == len(plan):
                tweaks.mark_undone(core.APP_DATA_DIR, undo_sid)
            known = tweaks.item_by_id()
            done_ids = {plan[r['ref']].get('item') for r in res if r.get('ok') and isinstance(r.get('ref'), int) and 0 <= r['ref'] < len(plan)}
            touched = [known[i] for i in done_ids if i in known]
            if any(it.get('reboot') for it in touched):
                self.write('Not: bazı ayarlar yeniden başlatmadan sonra etkinleşir.\n')
            if any(it.get('explorer') for it in touched):
                if messagebox.askyesno('Gezgin', 'Görev çubuğu / Gezgin ayarlarının hemen görünmesi için Windows Gezgini yeniden başlatılsın mı?\n'
                                       '(Açık Gezgin pencereleri kapanır.)'):
                    self.start([Job('Gezgini yeniden başlat', cmd=ps_cmd('explorer-restart'), cancel_ok=False)])
            self.tw_read()
        jobs.append(Job(title, cmd=ps_cmd('tweak-write', PlanFile=path), on_done=done, cancel_ok=False, admin=tweaks.needs_admin_ops(plan)))
        self.start(jobs)

    def _tw_undo_session(self, sess):
        ops = tweaks.undo_ops(sess['entries'])
        if not ops:
            messagebox.showinfo('Geri al', 'Bu oturumda geri alınacak başarılı değişiklik yok.'); return
        errs = tweaks.validate_ops(ops)
        if errs:
            messagebox.showerror('Geri alma planı', '\n'.join(errs[:6])); return
        if tweaks.needs_admin_ops(ops) and not self.admin and not IS_WIN:
            if messagebox.askyesno('Yönetici gerekli', 'Bu değişikliği geri almak yönetici yetkisi ister. Uygulama yönetici olarak yeniden açılsın mı?'):
                self.elevate()
            return
        if not messagebox.askyesno('Geri al', 'Şu oturum geri alınacak:\n%s\n\n%d işlem önceki değerlerine döndürülecek. Devam?' % (tweaks.session_summary(sess), len(ops))):
            return
        self._tw_run(ops, 'Geri alma: ' + sess['title'], undo_sid=sess['id'])

    def tw_undo_last(self):
        sessions = [s for s in tweaks.load_journal(core.APP_DATA_DIR) if not s.get('undone') and not s['title'].startswith('Geri alma:')]
        if not sessions:
            messagebox.showinfo('Geri al', 'Geri alınacak bir ince ayar değişikliği yok.'); return
        self._tw_undo_session(sessions[-1])

    def tw_history(self):
        sessions = list(reversed(tweaks.load_journal(core.APP_DATA_DIR)))
        w = tk.Toplevel(self); w.title('İnce ayar geçmişi'); w.configure(bg=PANEL)
        w.geometry('%dx%d' % (int(900 * self.scale), int(420 * self.scale)))
        tk.Label(w, text='Değişiklik oturumları (en yeni üstte). Seçip geri alabilirsiniz; geri alma da kayda geçer.', fg=MUTED, bg=PANEL).pack(fill='x', padx=12, pady=(10, 4))
        lb = tk.Listbox(w, bg=TREE_BG, fg=FG, selectbackground=SEL, selectforeground=SEL_FG, relief='flat', font=('Segoe UI', 9), activestyle='none')
        lb.pack(fill='both', expand=True, padx=12)
        for s in sessions:
            lb.insert('end', tweaks.session_summary(s))
        if not sessions:
            lb.insert('end', 'Henüz kayıtlı değişiklik yok.')
        bar = tk.Frame(w, bg=PANEL); bar.pack(fill='x', padx=12, pady=8)

        def undo():
            i = lb.curselection()
            if not i or not sessions:
                return
            s = sessions[i[0]]
            if s.get('undone'):
                if not messagebox.askyesno('Geri al', 'Bu oturum zaten geri alınmış. Yine de önceki değerlere dönülsün mü?', parent=w):
                    return
            w.destroy()
            self._tw_undo_session(s)
        self.btn(bar, 'Seçili oturumu geri al', undo, 'danger', action=False)
        self.btn(bar, 'Kapat', w.destroy, 'ghost', action=False)

    def tw_export(self):
        ids = [p['id'] for p in self.tw_tree.checked_payloads() if p] or sorted(self.tw_sel)
        if not ids:
            messagebox.showinfo('Profil', 'Dışa aktarmak için önce ayar işaretleyin.'); return
        path = filedialog.asksaveasfilename(title='Profili kaydet', defaultextension='.json', filetypes=[('JSON', '*.json')],
                                            initialfile='agfo-ince-ayar-profili.json')
        if not path:
            return
        pathlib.Path(path).write_text(json.dumps(tweaks.export_profile(ids), ensure_ascii=False, indent=1), encoding='utf-8')
        self.write('Profil kaydedildi (%d ayar): %s\n' % (len(ids), path))

    def tw_import(self):
        path = filedialog.askopenfilename(title='Profil aç', filetypes=[('JSON', '*.json'), ('Tüm dosyalar', '*.*')])
        if not path:
            return
        try:
            ids, unknown = tweaks.import_profile(json.loads(pathlib.Path(path).read_text(encoding='utf-8-sig')))
        except Exception as e:
            messagebox.showerror('Profil', 'Profil okunamadı: %s' % e); return
        known = {it['id'] for it in self._tw_visible_items()}
        self.tw_sel = set(ids) & known
        self.tw_tree.clear()
        self._tw_render()
        self.write('Profil yüklendi: %d ayar işaretlendi%s. Uygulamak için "Seçilenleri uygula".\n'
                   % (len(self.tw_sel), (', %d tanınmayan/desteklenmeyen kayıt atlandı' % (len(unknown) + len(set(ids) - known))) if (unknown or set(ids) - known) else ''))

    # DNS
    def dns_list(self, then=None):
        def done(job):
            self.dns_adapters = [d for d in job.data if d.get('type') == 'dns-adapter']
            if not self.dns_adapters:
                self.dns_state.set('Bağlı fiziksel bağdaştırıcı yok.')
            else:
                self.dns_state.set('  |  '.join('%s: %s' % (a['alias'], ', '.join(a.get('servers') or []) or 'DHCP (%s)' % ', '.join(a.get('current') or []))
                                                for a in self.dns_adapters))
            if then:
                then()
        self.start([Job('DNS bağdaştırıcıları', cmd=ps_cmd('dns-list'), on_done=done, cancel_ok=False)])

    def dns_apply(self):
        choice = self.dns_choice.get()
        preset = next((p for p in tweaks.DNS_PRESETS if p[1] == choice), None)
        if preset:
            servers = preset[2]
        else:
            servers = tweaks.valid_ipv4_list(self.dns_custom.get())
            if not servers:
                messagebox.showerror('DNS', 'Özel adresleri yan kutuya IPv4 olarak yazın (ör. 1.1.1.1, 8.8.8.8; en fazla 4).'); return
        if not self.admin and not IS_WIN:
            if messagebox.askyesno('Yönetici gerekli', 'DNS değiştirmek yönetici ister. Uygulama yönetici olarak yeniden açılsın mı?'):
                self.elevate()
            return

        def go():
            if not self.dns_adapters:
                messagebox.showinfo('DNS', 'Bağlı fiziksel ağ bağdaştırıcısı bulunamadı.'); return
            names = ', '.join(a['alias'] for a in self.dns_adapters)
            if not messagebox.askyesno('DNS', '%s bağdaştırıcılarında DNS "%s" yapılacak. Önceki ayar kaydedilir ve Geçmiş\'ten geri alınabilir. Devam?' % (names, choice if preset else ', '.join(servers))):
                return
            plan = tweaks.dns_plan(self.dns_adapters, servers)
            self._tw_run(plan, 'DNS: ' + (choice if preset else ', '.join(servers)))
        self.dns_list(then=go)

    def dns_flush(self):
        self.start([Job('DNS önbelleğini temizle', cmd=ps_cmd('dns-flush'), cancel_ok=False)])


register_palette_module(globals())
