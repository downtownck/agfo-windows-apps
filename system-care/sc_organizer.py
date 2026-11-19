# -*- coding: utf-8 -*-
"""AGFO System Care — Dosya duzeni sayfasi (Smart Organizer cekirdegi). App sinifinin parcasi (mixin); paylasilan adlar sc_base'den gelir."""
from sc_base import *  # noqa: F401,F403


class OrganizerPage:
    # ------------------------------------------------------------------ DOSYA DUZENI (Smart Organizer cekirdegi, organizer_core.py)
    ORG_FILTERS = ('Tümü', 'Bekliyor', 'Kabul', 'Red', 'Taşındı', 'Hata')

    def _tab_organizer(self, f):
        head = tk.Frame(f, bg=PANEL); head.pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(head, text='Dosya düzeni', fg=FG, bg=PANEL, font=('Segoe UI', 12, 'bold')).pack(side='left')
        tk.Label(head, text='Planla → düzenle → onayla → taşı', fg=MUTED, bg=PANEL, font=('Segoe UI', 9)).pack(side='left', padx=(12, 0))
        try:
            import organizer_core as org
        except Exception as e:                         # Python 3.8/3.9 vb.
            self.org = None
            self.label(f, 'Dosya düzeni bu Python sürümünde açılamadı: %s' % e).pack(fill='x', padx=16, pady=8)
            return
        self.org = org
        self.label(f, 'Masaüstü ve Belgeler klasörünün doğrudan altındaki dosya, klasör ve kısayolları sınıflandırır, "%s" altında kategori klasörlerine '
                      'taşımayı önerir. Siz onaylamadan hiçbir şey taşınmaz, üzerine yazma ve silme yapılmaz; "Son taşımayı geri al" her şeyi eski yerine döndürür. '
                      'Yerel AI (Ollama + Gemma) isteğe bağlıdır; dosya içeriği bilgisayardan çıkmaz.' % org.APP_FOLDER,
                   wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(2, 4))
        self.org_roots = org.standard_roots()
        self.org_items, self.org_by_id = [], {}
        self.org_state = org.app_state_dir()
        self.org_journal = org.MoveJournal(self.org_state / 'moves.sqlite3')
        try:
            oset = json.loads((self.org_state / 'settings.json').read_text(encoding='utf-8'))
        except Exception:
            oset = {}
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.org_desktop, self.org_docs = tk.BooleanVar(value=True), tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text='Masaüstü', variable=self.org_desktop).pack(side='left', padx=(0, 8))
        ttk.Checkbutton(bar, text='Belgeler', variable=self.org_docs).pack(side='left', padx=(0, 10))
        self.btn(bar, '1  Analiz et', self.org_scan, 'go')
        self.btn(bar, '2  Yerel AI ile iyileştir', self.org_ai, 'normal')
        tk.Label(bar, text='Model:', fg=FG, bg=PANEL).pack(side='left', padx=(8, 2))
        self.org_model = ttk.Combobox(bar, width=16, values=[oset.get('ollama_model', 'gemma3:1b')])
        self.org_model.set(oset.get('ollama_model', 'gemma3:1b'))
        self.org_model.pack(side='left')
        self.btn(bar, 'Modelleri bul', self.org_models, 'ghost')
        tk.Label(bar, text='En çok:', fg=FG, bg=PANEL).pack(side='left', padx=(6, 2))
        self.org_limit = tk.StringVar(value=str(oset.get('ai_limit', '30')))
        ttk.Entry(bar, width=5, textvariable=self.org_limit).pack(side='left')
        flt = tk.Frame(f, bg=PANEL); flt.pack(fill='x', padx=16, pady=(6, 0))
        tk.Label(flt, text='Ara:', fg=FG, bg=PANEL).pack(side='left')
        self.org_q = tk.StringVar()
        ttk.Entry(flt, textvariable=self.org_q, width=30).pack(side='left', padx=6)
        self.org_q.trace_add('write', lambda *_: self._org_render())
        tk.Label(flt, text='Durum:', fg=FG, bg=PANEL).pack(side='left', padx=(10, 0))
        self.org_filter = ttk.Combobox(flt, state='readonly', width=12, values=self.ORG_FILTERS); self.org_filter.current(0)
        self.org_filter.pack(side='left', padx=6)
        self.org_filter.bind('<<ComboboxSelected>>', lambda _e: self._org_render())
        self.btn(flt, 'Hedefi değiştir', self.org_edit, 'ghost', action=False, side='right')
        self.btn(flt, 'Klasörü göster', self.org_open, 'ghost', action=False, side='right')
        tf = ttk.Frame(f, style='Card.TFrame'); tf.pack(fill='both', expand=True, padx=16, pady=(8, 4))
        cols = ('source', 'kind', 'folder', 'dest', 'conf', 'decision')
        self.org_tree = ttk.Treeview(tf, columns=cols, show='tree headings', selectmode='extended', height=8)
        self.org_tree.heading('#0', text='Dosya / kısayol'); self.org_tree.column('#0', width=280, stretch=True)
        for key, title, w, anc in (('source', 'Konum', 90, 'center'), ('kind', 'Tür', 70, 'w'), ('folder', 'Kategori', 120, 'w'),
                                   ('dest', 'Önerilen hedef', 360, 'w'), ('conf', 'Güven', 60, 'center'), ('decision', 'Karar', 80, 'center')):
            self.org_tree.heading(key, text=title); self.org_tree.column(key, width=w, anchor=anc, stretch=(key == 'dest'))
        ys = ttk.Scrollbar(tf, orient='vertical', command=self.org_tree.yview)
        self.org_tree.configure(yscrollcommand=ys.set)
        self.org_tree.pack(side='left', fill='both', expand=True); ys.pack(side='right', fill='y')
        self.org_tree.bind('<<TreeviewSelect>>', lambda _e: self._org_preview())
        self.org_tree.bind('<Double-1>', lambda _e: self.org_edit())
        self._org_tags()
        self.theme_hooks.append(self._org_tags)
        cmd = tk.Frame(f, bg=PANEL); cmd.pack(fill='x', padx=16, pady=(4, 0))
        self.btn(cmd, 'Seçilenleri kabul et', lambda: self.org_decide('Kabul', False), 'ghost', action=False)
        self.btn(cmd, 'Seçilenleri reddet', lambda: self.org_decide('Red', False), 'ghost', action=False)
        self.btn(cmd, 'Tümünü kabul et', lambda: self.org_decide('Kabul', True), 'ghost', action=False)
        self.btn(cmd, 'Tümünü reddet', lambda: self.org_decide('Red', True), 'ghost', action=False)
        self.btn(cmd, '3  Onaylananları taşı', self.org_move, 'danger', side='right')
        self.btn(cmd, 'Son taşımayı geri al', self.org_undo, 'normal', side='right')
        self.org_summary = tk.StringVar(value='Tarama yapılmadı.')
        tk.Label(f, textvariable=self.org_summary, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold'), anchor='w').pack(fill='x', padx=16, pady=(4, 0))
        self.org_info = tk.StringVar(value='Bir satır seçin: kaynak, öneri nedeni ve içerik örneği burada görünür. Hedefi çift tıklayarak değiştirebilirsiniz.')
        tk.Label(f, textvariable=self.org_info, fg=MUTED, bg=PANEL, font=('Segoe UI', 9), anchor='w', justify='left',
                 wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(2, 10))

    def _org_tags(self):
        for tg, col in (('Kabul', OK_C), ('Red', BAD_C), ('Taşındı', MUTED), ('Hata', WARN)):
            self.org_tree.tag_configure(tg, foreground=col)

    def _org_save_settings(self):
        try:
            self.org_state.mkdir(parents=True, exist_ok=True)
            (self.org_state / 'settings.json').write_text(json.dumps({'ollama_model': self.org_model.get().strip(), 'ai_limit': self.org_limit.get().strip()},
                                                                     ensure_ascii=False, indent=2), encoding='utf-8')
        except OSError:
            pass

    def _org_selected(self):
        return [self.org_by_id[i] for i in self.org_tree.selection() if i in self.org_by_id]

    def _org_render(self):
        if not getattr(self, 'org', None):
            return
        t = self.org_tree
        keep = set(t.selection())
        t.delete(*t.get_children())
        need, q = self.org_filter.get(), self.org_q.get().strip().casefold()
        for it in self.org_items:
            if need != 'Tümü' and it.decision != need:
                continue
            if q and q not in (it.path.name + ' ' + it.folder + ' ' + str(it.path)).casefold():
                continue
            src = 'Masaüstü' if it.path.parent == self.org_roots.get('Masaüstü') else 'Belgeler'
            t.insert('', 'end', iid=it.item_id, text=it.path.name,
                     values=(src, 'Klasör' if it.is_dir else (it.path.suffix.lower() or 'Dosya'), it.category,
                             '%s / %s / %s' % (it.root, self.org.APP_FOLDER, it.folder), '%d%%' % int(it.confidence * 100), it.decision),
                     tags=(it.decision,))
        sel = tuple(i for i in keep if t.exists(i))
        if sel:
            t.selection_set(sel)
        c = {k: sum(1 for x in self.org_items if x.decision == k) for k in self.ORG_FILTERS[1:]}
        self.org_summary.set('Toplam %d  ·  Bekliyor %d  ·  Kabul %d  ·  Red %d  ·  Taşındı %d  ·  Hata %d' %
                             (len(self.org_items), c['Bekliyor'], c['Kabul'], c['Red'], c['Taşındı'], c['Hata']) if self.org_items else 'Tarama yapılmadı.')

    def _org_preview(self):
        sel = self._org_selected()
        if not sel:
            return
        it = sel[0]
        txt = 'Kaynak: %s  ·  Öneri nedeni: %s  ·  Hedef: %s' % (it.path, it.reason, it.target(self.org_roots))
        if it.snippet:
            txt += '\nİçerik örneği: ' + it.snippet[:500].replace('\n', ' ')
        if len(sel) > 1:
            txt += '\nToplam %d öğe seçili.' % len(sel)
        self.org_info.set(txt)

    def org_scan(self):
        labels = [n for n, v in (('Masaüstü', self.org_desktop), ('Belgeler', self.org_docs)) if v.get()]
        if not labels:
            messagebox.showwarning('Dosya düzeni', 'En az bir kaynak (Masaüstü / Belgeler) seçin.'); return
        if any(it.decision == 'Kabul' for it in self.org_items) and not messagebox.askyesno('Planı yenile', 'Uygulanmamış onaylar kaybolacak. Yeniden taransın mı?'):
            return
        org = self.org

        def work(runner, job):
            last = [0]

            def prog(n):
                if n - last[0] >= 100:
                    last[0] = n
                    runner.say('%d öğe incelendi...' % n)
            items, warnings = org.scan(self.org_roots, labels, progress=prog)
            job.data = [(items, warnings)]
            runner.say('Tarama tamamlandı: %d öğe.' % len(items))
            return 0

        def done(job):
            if not job.data:
                return
            self.org_items, warnings = job.data[0]
            self.org_by_id = {it.item_id: it for it in self.org_items}
            self._org_render()
            if warnings:
                messagebox.showwarning('Tarama notları', '\n'.join(warnings[:12]))
        self.start([Job('Dosya düzeni: analiz', func=work, on_done=done, cancel_ok=False)])

    def org_models(self):
        org = self.org

        def work(runner, job):
            try:
                job.data = [org.list_ollama_models()]
                runner.say('Ollama modelleri: %s' % (', '.join(job.data[0][:6]) or 'yok (KUR-GEMMA.cmd ile kurulabilir)'))
                return 0
            except RuntimeError as e:
                runner.say('Ollama: %s' % e)
                return 1

        def done(job):
            if job.data:
                models = job.data[0]
                self.org_model.configure(values=models)
                chosen = org.pick_ollama_model(self.org_model.get().strip(), models) if models else None
                if chosen and chosen != self.org_model.get().strip():
                    self.org_model.set(chosen)
                    self._org_save_settings()
        self.start([Job('Ollama modelleri', func=work, on_done=done, cancel_ok=False)])

    def org_ai(self):
        org = self.org
        cand = [i for i in self.org_items if i.decision == 'Bekliyor' and i.confidence < 0.90 and not i.is_dir]
        if not cand:
            messagebox.showinfo('Yerel AI', 'AI ile incelenecek bekleyen / belirsiz öğe yok. Önce analiz edin.'); return
        try:
            limit = int(self.org_limit.get())
            assert 1 <= limit <= 200
        except (ValueError, AssertionError):
            messagebox.showerror('Yerel AI', 'Öğe sınırı 1-200 arasında olmalı.'); return
        model = self.org_model.get().strip()
        if not model:
            messagebox.showerror('Yerel AI', 'Ollama model adını girin.'); return
        cand = cand[:limit]
        self._org_save_settings()

        def work(runner, job):
            try:
                models = org.list_ollama_models()
            except RuntimeError as e:
                runner.say('Ollama: %s' % e); return 1
            if not models:
                runner.say('Ollama çalışıyor ama model yok. Smart Organizer klasöründeki KUR-GEMMA.cmd ile Gemma kurulabilir.'); return 1
            sel = org.pick_ollama_model(model, models)
            changed, results = 0, []
            for n, it in enumerate(cand, 1):
                if runner.stop.is_set():
                    break
                runner.say('Yerel AI %d/%d: %s' % (n, len(cand), it.path.name[:40]))
                try:
                    results.append((it, org.ollama_refine(it, model=sel)))
                    changed += 1
                except Exception as e:
                    runner.say('  %s: %s' % (it.path.name, e))
                    if changed == 0 and n == 1:
                        break
            job.data = [results]
            return 0

        def done(job):
            for it, (cat, conf, reason) in (job.data[0] if job.data else []):
                it.category, it.folder, it.confidence, it.reason = cat, cat, conf, reason
            self._org_render()
            self.write('Yerel AI: %d öneri güncellendi.\n' % len(job.data[0] if job.data else []))
        self.start([Job('Dosya düzeni: yerel AI', func=work, on_done=done, cancel_ok=True)])

    def org_decide(self, decision, all_items):
        items = self.org_items if all_items else self._org_selected()
        if not items and not all_items:
            messagebox.showinfo('Seçim', 'Önce bir veya daha fazla öğe seçin.'); return
        n = 0
        for it in items:
            if it.decision in ('Bekliyor', 'Kabul', 'Red', 'Hata'):
                it.decision = decision; n += 1
        self._org_render()
        self.write('Dosya düzeni: %d karar güncellendi.\n' % n)

    def org_edit(self):
        sel = [it for it in self._org_selected() if it.decision != 'Taşındı']
        if not sel:
            messagebox.showinfo('Hedef', 'Önce düzenlenecek öğeyi seçin.'); return
        org = self.org
        w = tk.Toplevel(self); w.title('Hedef klasörü düzenle'); w.configure(bg=PANEL); w.transient(self); w.resizable(False, False)
        rv, fv = tk.StringVar(value=sel[0].root), tk.StringVar(value=sel[0].folder)
        body = tk.Frame(w, bg=PANEL, padx=20, pady=16); body.pack(fill='both', expand=True)
        tk.Label(body, text='Hedef ana konum', fg=FG, bg=PANEL).pack(anchor='w')
        ttk.Combobox(body, textvariable=rv, values=list(self.org_roots), state='readonly').pack(fill='x', pady=(4, 12))
        tk.Label(body, text='Alt klasör (ör. Denetimler/BRCGS/2026)', fg=FG, bg=PANEL).pack(anchor='w')
        ttk.Entry(body, textvariable=fv, width=48).pack(fill='x', pady=(4, 4))
        tk.Label(body, text='Öğeler “%s” altında düzenlenir.' % org.APP_FOLDER, fg=MUTED, bg=PANEL).pack(anchor='w')

        def save():
            try:
                folder = org.valid_subfolder(fv.get())
                if rv.get() not in self.org_roots:
                    raise ValueError('Geçersiz ana konum')
            except ValueError as e:
                messagebox.showerror('Hedef geçersiz', str(e), parent=w); return
            for it in sel:
                it.root, it.folder = rv.get(), folder
                it.category = folder.split('/')[0]
                it.reason += ' | Hedef kullanıcı tarafından düzenlendi'
            w.destroy()
            self._org_render()
        bar = tk.Frame(body, bg=PANEL); bar.pack(fill='x', pady=(14, 0))
        self.btn(bar, 'Uygula', save, 'normal', action=False, side='right')
        self.btn(bar, 'İptal', w.destroy, 'ghost', action=False, side='right')
        w.bind('<Return>', lambda _e: save()); w.bind('<Escape>', lambda _e: w.destroy())

    def org_open(self):
        sel = self._org_selected()
        if not sel:
            messagebox.showinfo('Klasör', 'Önce bir öğe seçin.'); return
        if IS_WIN:
            subprocess.Popen(['explorer', '/select,%s' % sel[0].path])
        else:
            messagebox.showinfo('Klasör', str(sel[0].path.parent))

    def org_move(self):
        approved = [it for it in self.org_items if it.decision == 'Kabul']
        if not approved:
            messagebox.showinfo('Taşı', 'Taşınacak kabul edilmiş öğe yok.'); return
        roots = sorted({it.root for it in approved})
        if not messagebox.askyesno('Toplu taşıma onayı', '%d dosya/klasör taşınacak.\n\nHedef: %s / %s\n\nKısayolların taşınması masaüstü simgelerini kaldırır; hedefleri değişmez. '
                                   'OneDrive kullanıyorsanız eşitleme de olabilir.\n\nÜzerine yazma ve silme yapılmaz; geri alma kaydı tutulur. Devam?'
                                   % (len(approved), ', '.join(roots), self.org.APP_FOLDER), icon='warning'):
            return
        org = self.org

        def work(runner, job):
            count, errors, batch = org.execute_approved(approved, self.org_roots, self.org_journal,
                                                        progress=lambda n: runner.say('%d/%d taşındı...' % (n, len(approved))) if n % 25 == 0 else None)
            for e in errors[:20]:
                runner.say('  HATA: %s' % e)
            runner.say('Taşınan: %d, hata: %d (işlem %s)' % (count, len(errors), batch[:8]))
            return 0 if not errors else 2
        self.start([Job('Dosya düzeni: taşı', func=work, on_done=lambda j: self._org_render(), cancel_ok=False)])

    def org_undo(self):
        batch = self.org_journal.latest_batch()
        if not batch:
            messagebox.showinfo('Geri al', 'Geri alınabilecek taşıma kaydı yok.'); return
        if not messagebox.askyesno('Son taşımayı geri al', 'Son taşımadaki tüm öğeler eski konumlarına döndürülecek. Özgün konumda aynı adlı öğe varsa atlanır. Devam?'):
            return

        def work(runner, job):
            count, errors = self.org_journal.undo(batch)
            for e in errors[:20]:
                runner.say('  HATA: %s' % e)
            runner.say('Geri alınan: %d, hata: %d' % (count, len(errors)))
            return 0 if not errors else 2

        def done(job):
            self.org_items, self.org_by_id = [], {}
            self._org_render()
        self.start([Job('Dosya düzeni: geri al', func=work, on_done=done, cancel_ok=False)])


register_palette_module(globals())
