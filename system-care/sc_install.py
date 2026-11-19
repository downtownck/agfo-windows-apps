# -*- coding: utf-8 -*-
"""AGFO System Care — Uygulama kur sayfasi (WinGet katalogu). App sinifinin parcasi (mixin); paylasilan adlar sc_base'den gelir."""
from sc_base import *  # noqa: F401,F403


class InstallPage:
    # ------------------------------------------------------------------ UYGULAMA KUR (WinGet katalogu; liste ve buyuk simge gorunumu)
    INST_FILTERS = ['Tümü', 'Kurulu olmayanlar', 'Kurulu olanlar']
    TILE_W, TILE_H = 168, 120

    def _tab_install(self, f):
        self.label(f, 'Sık kullanılan uygulamalar WinGet resmî deposundan sessiz kurulur veya kaldırılır. "Kurulu olanları denetle" bu bilgisayardaki durumu işler. '
                      'Logolar uygulamaların kendi sitelerinden bir kez indirilir ve bu bilgisayarda saklanır.', wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(12, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Kurulu olanları denetle', self.inst_scan, 'ghost')
        self.btn(bar, 'Seçimi kaldır', self.inst_clear, 'ghost', action=False)
        self.btn(bar, 'Seçilenleri kur', lambda: self.inst_run('install'), 'go')
        self.btn(bar, 'Seçilenleri kaldır', lambda: self.inst_run('uninstall'), 'danger')
        self.inst_count = tk.StringVar(value='')
        tk.Label(bar, textvariable=self.inst_count, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(side='right')
        flt = tk.Frame(f, bg=PANEL); flt.pack(fill='x', padx=16, pady=(6, 0))
        tk.Label(flt, text='Göster:', fg=FG, bg=PANEL).pack(side='left')
        self.inst_filter = ttk.Combobox(flt, state='readonly', width=20, values=self.INST_FILTERS); self.inst_filter.current(0)
        self.inst_filter.pack(side='left', padx=6)
        self.inst_filter.bind('<<ComboboxSelected>>', lambda _e: self._inst_refresh())
        tk.Label(flt, text='Ara:', fg=FG, bg=PANEL).pack(side='left', padx=(10, 0))
        self.inst_q = tk.StringVar()
        ttk.Entry(flt, textvariable=self.inst_q, width=26).pack(side='left', padx=6)
        self.inst_q.trace_add('write', lambda *_: self._inst_refresh())
        self.inst_view = tk.StringVar(value=self.settings.get('install_view', 'grid'))
        for val, txt in (('list', 'Liste'), ('grid', 'Büyük simgeler')):
            ttk.Radiobutton(flt, text=txt, value=val, variable=self.inst_view, command=self._inst_switch_view).pack(side='right', padx=(8, 0))
        tk.Label(flt, text='Görünüm:', fg=FG, bg=PANEL).pack(side='right', padx=(10, 0))
        self.inst_holder = tk.Frame(f, bg=PANEL)
        self.inst_holder.pack(fill='both', expand=True, padx=16, pady=8)
        cols = [('id', 'WinGet kimliği', 260, 'w'), ('state', 'Durum', 150, 'w'), ('desc', 'Açıklama', 460, 'w')]
        self.inst_tree = CheckTree(self.inst_holder, cols, first=('Uygulama', 300), on_change=self._inst_count_update)
        # buyuk simge gorunumu: kaydirilabilir tuval icinde kutucuklar
        self.inst_gridf = tk.Frame(self.inst_holder, bg=PANEL)
        self.inst_canvas = tk.Canvas(self.inst_gridf, bg=PANEL, highlightthickness=0, bd=0)
        gys = ttk.Scrollbar(self.inst_gridf, orient='vertical', command=self.inst_canvas.yview)
        self.inst_canvas.configure(yscrollcommand=gys.set)
        gys.pack(side='right', fill='y'); self.inst_canvas.pack(side='left', fill='both', expand=True)
        self.inst_inner = tk.Frame(self.inst_canvas, bg=PANEL)
        self.inst_canvas.create_window((0, 0), window=self.inst_inner, anchor='nw', tags=('inner',))
        self.inst_inner.bind('<Configure>', lambda _e: self.inst_canvas.configure(scrollregion=self.inst_canvas.bbox('all')))
        self.inst_canvas.bind('<Configure>', self._inst_canvas_resized)
        for w in (self.inst_canvas, self.inst_inner):
            w.bind('<MouseWheel>', self._inst_wheel)
            w.bind('<Button-4>', lambda _e: self.inst_canvas.yview_scroll(-3, 'units'))
            w.bind('<Button-5>', lambda _e: self.inst_canvas.yview_scroll(3, 'units'))
        self.inst_ids, self.inst_result, self.inst_sel, self.inst_scanned = set(), {}, set(), False
        self.inst_tiles, self.inst_cols = {}, 0
        self.inst_img_l, self.inst_img_s = {}, {}
        self.inst_icon_dir = icons.cache_dir(core.APP_DATA_DIR)
        self.inst_icon_q = queue.Queue()
        self.inst_icon_busy = False
        self.theme_hooks.append(self._inst_paint_all)
        self._inst_load_cached_icons()
        self._inst_switch_view(initial=True)
        self._inst_tab = f

    # --- secim ve sayim
    def _inst_on_tab(self, _e=None):
        # Logolar yalnizca sayfa buyuk simge gorunumunde acildiginda indirilir (acilista ag trafigi yok).
        try:
            if self.tabs.nametowidget(self.tabs.select()) is self._inst_tab and self.inst_view.get() == 'grid':
                self.inst_fetch_icons()
        except Exception:
            pass

    def _inst_count_update(self):
        n = len(self._inst_selected_ids())
        self.inst_count.set('%d seçili' % n if n else '')

    def _inst_sync_from_tree(self):
        t = self.inst_tree
        if t.labels:
            visible = {pl['id'] for pl in t.payload.values() if pl}
            checked = {pl['id'] for pl in t.checked_payloads() if pl}
            self.inst_sel = checked | (self.inst_sel - visible)

    def _inst_selected_ids(self):
        if self.inst_view.get() == 'list':
            self._inst_sync_from_tree()
        return set(self.inst_sel)

    def inst_clear(self):
        self.inst_sel = set()
        self.inst_tree.set_all(False)
        self._inst_paint_all()
        self._inst_count_update()

    def _inst_visible_apps(self):
        mode, q = self.inst_filter.get(), self.inst_q.get().strip().lower()
        out = []
        for catname, apps in tweaks.install_groups().items():
            rows = []
            for a in apps:
                inst = self.inst_scanned and tweaks.is_installed(a['id'], self.inst_ids)
                if mode == 'Kurulu olmayanlar' and inst:
                    continue
                if mode == 'Kurulu olanlar' and not inst:
                    continue
                if q and q not in (a['name'] + ' ' + a['id'] + ' ' + a['desc']).lower():
                    continue
                rows.append((a, inst))
            if rows:
                out.append((catname, rows))
        return out

    def _inst_state(self, a):
        if a['id'] in self.inst_result:
            return self.inst_result[a['id']]
        if not self.inst_scanned:
            return ''
        return 'Kurulu' if tweaks.is_installed(a['id'], self.inst_ids) else 'Kurulu değil'

    def _inst_switch_view(self, initial=False):
        view = self.inst_view.get()
        if not initial:
            if view == 'grid':
                self._inst_sync_from_tree()
            self.settings['install_view'] = view
            core.save_settings(self.settings)
        if view == 'grid':
            self.inst_tree.pack_forget()
            self.inst_gridf.pack(fill='both', expand=True)
            if not initial:
                self.inst_fetch_icons()
        else:
            self.inst_gridf.pack_forget()
            self.inst_tree.pack(fill='both', expand=True)
        self._inst_refresh()

    def _inst_refresh(self):
        if self.inst_view.get() == 'grid':
            self._inst_render_grid()
        else:
            self._inst_render()
        self._inst_count_update()

    # --- liste gorunumu
    def _inst_render(self):
        t = self.inst_tree
        self._inst_sync_from_tree()
        t.clear()
        mode, q = self.inst_filter.get(), self.inst_q.get().strip()
        for n, (catname, rows) in enumerate(self._inst_visible_apps()):
            gid = 'g%d' % n
            t.add(gid, '%s (%d)' % (catname, len(rows)), ('', '', ''), tags=('group',), open_=bool(q) or mode != 'Tümü')
            for a, inst in rows:
                iid = t.add('i:' + a['id'], a['name'], (a['id'], self._inst_state(a), a['desc']), parent=gid, checked=a['id'] in self.inst_sel,
                            tags=('st_new',) if inst else (), payload=a)
                img = self.inst_img_s.get(a['id'])
                if img is not None:
                    t.tree.item(iid, image=img)
        t.refresh_marks()

    # --- buyuk simge gorunumu
    def _inst_wheel(self, e):
        self.inst_canvas.yview_scroll(int(-e.delta / 120) * 3 if e.delta else 0, 'units')

    def _inst_canvas_resized(self, e):
        self.inst_canvas.itemconfigure('inner', width=e.width)
        cols = max(1, int(e.width // int((self.TILE_W + 10) * self.scale)))
        if cols != self.inst_cols and self.inst_view.get() == 'grid':
            self.inst_cols = cols
            self._inst_render_grid()

    def _inst_render_grid(self):
        for w in self.inst_inner.winfo_children():
            w.destroy()
        self.inst_tiles = {}
        cols = self.inst_cols or max(1, int(max(self.inst_canvas.winfo_width(), 900) // int((self.TILE_W + 10) * self.scale)))
        groups = self._inst_visible_apps()
        if not groups:
            tk.Label(self.inst_inner, text='Bu süzgeçle eşleşen uygulama yok.', fg=MUTED, bg=PANEL).pack(anchor='w', pady=10)
        for catname, rows in groups:
            tk.Label(self.inst_inner, text='%s  (%d)' % (catname, len(rows)), fg=ACCENT, bg=PANEL, font=('Segoe UI', 10, 'bold'),
                     anchor='w').pack(fill='x', pady=(10, 4))
            grid = tk.Frame(self.inst_inner, bg=PANEL)
            grid.pack(fill='x')
            for i, (a, inst) in enumerate(rows):
                self._inst_tile(grid, a, inst).grid(row=i // cols, column=i % cols, padx=(0, 10), pady=(0, 10), sticky='nw')
        self.inst_canvas.yview_moveto(0)

    def _inst_tile(self, parent, a, inst):
        w, h = int(self.TILE_W * self.scale), int(self.TILE_H * self.scale)
        tile = tk.Frame(parent, bg=PANEL2, width=w, height=h, cursor='hand2', highlightthickness=2, highlightbackground=PANEL2)
        tile.pack_propagate(False)
        img = self.inst_img_l.get(a['id'])
        if img is not None:
            icon = tk.Label(tile, image=img, bg=PANEL2, cursor='hand2')
        else:
            sz = int(48 * self.scale)
            icon = tk.Canvas(tile, width=sz, height=sz, bg=PANEL2, highlightthickness=0, cursor='hand2')
            col = icons.avatar_color(a['id'])
            r = int(10 * self.scale)
            for x0, y0, x1, y1, st in ((0, 0, 2 * r, 2 * r, 90), (sz - 2 * r, 0, sz, 2 * r, 0), (0, sz - 2 * r, 2 * r, sz, 180), (sz - 2 * r, sz - 2 * r, sz, sz, 270)):
                icon.create_arc(x0, y0, x1, y1, start=st, extent=90, fill=col, outline=col)
            icon.create_rectangle(r, 0, sz - r, sz, fill=col, outline=col)
            icon.create_rectangle(0, r, sz, sz - r, fill=col, outline=col)
            icon.create_text(sz // 2, sz // 2, text=icons.initials(a['name']), fill='#ffffff', font=('Segoe UI', 14, 'bold'))
        icon.pack(pady=(int(12 * self.scale), 4))
        name = tk.Label(tile, text=a['name'], bg=PANEL2, fg=FG, font=('Segoe UI', 9, 'bold'), wraplength=w - 16, justify='center', cursor='hand2')
        name.pack()
        state = self._inst_state(a)
        st = tk.Label(tile, text=('✓ ' + state) if inst else state, bg=PANEL2, fg=OK_C if inst else MUTED, font=('Segoe UI', 8), cursor='hand2')
        st.pack()
        mark = tk.Label(tile, text='', bg=PANEL2, fg=ACCENT, font=('Segoe UI', 11, 'bold'))
        mark.place(relx=1.0, x=-6, y=4, anchor='ne')
        for wd in (tile, icon, name, st, mark):
            wd.bind('<Button-1>', lambda _e, i=a['id']: self._inst_toggle(i))
            wd.bind('<MouseWheel>', self._inst_wheel)
            wd.bind('<Button-4>', lambda _e: self.inst_canvas.yview_scroll(-3, 'units'))
            wd.bind('<Button-5>', lambda _e: self.inst_canvas.yview_scroll(3, 'units'))
        tip = '%s\n%s\n%s' % (a['name'], a['id'], a['desc'])
        for wd in (tile, icon, name):
            wd.bind('<Enter>', lambda _e, t=tip: self.inst_count.set(t.split('\n')[2][:90]))
            wd.bind('<Leave>', lambda _e: self._inst_count_update())
        self.inst_tiles[a['id']] = {'tile': tile, 'widgets': (icon, name, st), 'mark': mark, 'state': st, 'inst': inst}
        self._inst_paint(a['id'])
        return tile

    def _inst_paint(self, aid):
        t = self.inst_tiles.get(aid)
        if not t:
            return
        sel = aid in self.inst_sel
        bg = NAV_SEL if sel else PANEL2
        try:
            t['tile'].configure(bg=bg, highlightbackground=ACCENT if sel else PANEL2)
            for wd in t['widgets']:
                wd.configure(bg=bg)
            t['mark'].configure(bg=bg, text='✔' if sel else '')
            t['state'].configure(fg=OK_C if t['inst'] else MUTED)
        except tk.TclError:
            pass

    def _inst_paint_all(self):
        for aid in list(self.inst_tiles):
            self._inst_paint(aid)
        try:
            self.inst_canvas.configure(bg=PANEL)
        except tk.TclError:
            pass

    def _inst_toggle(self, aid):
        (self.inst_sel.discard if aid in self.inst_sel else self.inst_sel.add)(aid)
        self._inst_paint(aid)
        self._inst_count_update()

    # --- logolar
    def _inst_photo(self, path, target):
        img = tk.PhotoImage(file=str(path))
        w = img.width()
        if w > target * 1.5:
            f = max(1, round(w / target))
            img = img.subsample(f, f)
        return img

    def _inst_load_cached_icons(self):
        for a in tweaks.cat.INSTALL_APPS:
            large, small = icons.paths(self.inst_icon_dir, a['id'])
            if large.exists() and a['id'] not in self.inst_img_l:
                try:
                    self.inst_img_l[a['id']] = self._inst_photo(large, int(48 * self.scale))
                    self.inst_img_s[a['id']] = self._inst_photo(small, int(18 * self.scale))
                except tk.TclError:
                    pass

    def inst_fetch_icons(self):
        if self.inst_icon_busy:
            return
        idx = icons.load_index(self.inst_icon_dir)
        todo = [a for a in tweaks.cat.INSTALL_APPS if icons.needs_fetch(a, self.inst_icon_dir, idx)]
        if not todo:
            return
        self.inst_icon_busy = True
        self.write('Uygulama logoları indiriliyor (%d uygulama, her biri kendi sitesinden; bir kez yapılır)...\n' % len(todo))
        cdir, q = self.inst_icon_dir, self.inst_icon_q

        def worker():
            import concurrent.futures
            ok = 0
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                futs = {ex.submit(icons.fetch_icon, a, cdir): a for a in todo}
                for fu in concurrent.futures.as_completed(futs):
                    a = futs[fu]
                    try:
                        good, info = fu.result()
                    except Exception as e:
                        good, info = False, str(e)
                    idx[a['id']] = {'ok': good, 't': time.time(), 'src': info[:200]}
                    ok += 1 if good else 0
                    q.put(('icon', a['id'], good))
            icons.save_index(cdir, idx)
            q.put(('done', ok, len(todo)))
        threading.Thread(target=worker, daemon=True).start()
        self.after(250, self._inst_icon_poll)

    def _inst_icon_poll(self):
        changed, finished = False, False
        try:
            while True:
                msg = self.inst_icon_q.get_nowait()
                if msg[0] == 'icon' and msg[2]:
                    changed = True
                elif msg[0] == 'done':
                    finished = True
                    self.inst_icon_busy = False
                    self.write('Logolar: %d / %d uygulama için bulundu; bulunamayanlar harf simgesiyle gösterilir.\n' % (msg[1], msg[2]))
        except queue.Empty:
            pass
        if changed:
            self._inst_load_cached_icons()
            self._inst_icons_dirty = True
        now = time.time()
        if getattr(self, '_inst_icons_dirty', False) and (finished or now - getattr(self, '_inst_icons_drawn', 0) > 2.5):
            self._inst_icons_dirty = False
            self._inst_icons_drawn = now
            y = self.inst_canvas.yview()[0] if self.inst_view.get() == 'grid' else 0
            self._inst_refresh()
            if self.inst_view.get() == 'grid':
                self.inst_canvas.yview_moveto(y)
        if not finished:
            self.after(400, self._inst_icon_poll)

    # --- WinGet
    def inst_scan(self):
        wg = self.engines.get('winget', {}).get('path') or core.find_winget()
        if not wg:
            messagebox.showerror('WinGet yok', 'WinGet bulunamadı (Microsoft Store > Uygulama Yükleyici).'); return

        def done(job):
            rows = core.parse_winget_table(job.lines)
            self.inst_ids = tweaks.installed_ids(rows)
            self.inst_scanned = True
            self.inst_result = {}
            n = sum(1 for a in tweaks.cat.INSTALL_APPS if tweaks.is_installed(a['id'], self.inst_ids))
            self.write('WinGet: katalogdaki %d uygulamadan %d tanesi kurulu.\n' % (len(tweaks.cat.INSTALL_APPS), n))
            self._inst_refresh()
        self.start([Job('WinGet kurulu uygulamalar', cmd=[wg, 'list', '--source', 'winget', '--accept-source-agreements', '--disable-interactivity'],
                        on_done=done, show_output=False)])

    def inst_run(self, op):
        wg = self.engines.get('winget', {}).get('path') or core.find_winget()
        ids = self._inst_selected_ids()
        sel = [a for a in tweaks.cat.INSTALL_APPS if a['id'] in ids]
        if not wg:
            messagebox.showerror('WinGet yok', 'WinGet bulunamadı.'); return
        if not sel:
            messagebox.showinfo('Uygulama kur', 'Önce uygulama seçin (listede işaretleyin ya da kutucuğa tıklayın).'); return
        verb = 'kurulacak' if op == 'install' else 'kaldırılacak'
        if not messagebox.askyesno('Onaylayın', '%d uygulama sırayla %s:\n  %s%s\n\nDevam?' % (len(sel), verb, '\n  '.join(a['name'] for a in sel[:15]), '\n  ...' if len(sel) > 15 else '')):
            return
        jobs = []
        for a in sel:
            def done(job, aid=a['id']):
                ok = job.code == 0 or (isinstance(job.code, int) and (job.code & 0xFFFFFFFF) in (0x8A15002B, 0x8A150061))
                self.inst_result[aid] = ('Kuruldu' if op == 'install' else 'Kaldırıldı') if ok else hint(job.code)
                iid = 'i:' + aid
                if self.inst_tree.tree.exists(iid):
                    self.inst_tree.tree.set(iid, 'state', self.inst_result[aid])
                t = self.inst_tiles.get(aid)
                if t:
                    try:
                        t['state'].configure(text=self.inst_result[aid])
                    except tk.TclError:
                        pass
            cmd = core.winget_install_cmd(wg, a['id']) if op == 'install' else core.winget_uninstall_cmd(wg, a['id'])
            jobs.append(Job(('Kur: ' if op == 'install' else 'Kaldır: ') + a['name'], cmd=cmd, on_done=done, cancel_ok=True))
        self.start(jobs)


register_palette_module(globals())
