# -*- coding: utf-8 -*-
"""AGFO System Care — Kol / Gamepad sayfasi. App sinifinin parcasi (mixin); paylasilan adlar sc_base'den gelir."""
from sc_base import *  # noqa: F401,F403


class PadPage:
    # ------------------------------------------------------------------ KOL / GAMEPAD (3.6.0)
    def _tab_pad(self, f):
        head = tk.Frame(f, bg=PANEL); head.pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(head, text='Kol / Gamepad', fg=FG, bg=PANEL, font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.pad_chips = {}
        for key, text, color in [('total', 'kol bileşeni', ACCENT), ('usb', 'USB', OK_C), ('bluetooth', 'Bluetooth', WARN), ('adapter', 'adaptör', OK_C), ('problem', 'sorunlu', BAD_C)]:
            v = tk.StringVar(value='— ' + text)
            tk.Label(head, textvariable=v, fg=color, bg=PANEL2, font=('Segoe UI', 9, 'bold'), padx=10, pady=3).pack(side='left', padx=(10, 0))
            self.pad_chips[key] = (v, text)
        self.label(f, 'Xbox kolunun bağlantı yolu, sürücü durumu, pili ve canlı tuş/analog testi. Yalnızca Xbox kol/adaptör aygıtlarına dokunulur; fare ve klavye listeye girmez.',
                   wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(2, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Tara', self.pad_scan, 'go')
        self.btn(bar, 'Kol sürücüsünü sıfırla', self.pad_reset, 'danger')
        self.btn(bar, 'Bluetooth hizmetini yeniden başlat', self.pad_bt_restart)
        self.btn(bar, 'FC ayarlarını yedekle ve sıfırla', self.pad_fc_reset, 'danger')
        bar2 = tk.Frame(f, bg=PANEL); bar2.pack(fill='x', padx=16, pady=(2, 0))
        self.btn(bar2, 'Xbox Accessories (firmware)', self.pad_xbox_accessories, 'ghost')
        self.btn(bar2, 'Steam kumanda ayarları', lambda: self.pad_open('steam://settings/controller', 'Steam kumanda ayarları'), 'ghost', action=False)
        self.btn(bar2, 'Oyun kumandaları (joy.cpl)', lambda: self.pad_open('joy.cpl', 'Oyun kumandaları'), 'ghost', action=False)
        self.btn(bar2, 'Bluetooth ayarları', lambda: self.pad_open('ms-settings:bluetooth', 'Bluetooth ayarları'), 'ghost', action=False)
        self.btn(bar2, 'FC ayar klasörü', self.pad_open_fc_dir, 'ghost', action=False)
        body = tk.PanedWindow(f, orient='horizontal', bg=PANEL, sashwidth=6, bd=0)
        body.pack(fill='both', expand=True, padx=16, pady=(6, 8))
        left = tk.Frame(body, bg=PANEL)
        body.add(left, stretch='always', minsize=int(420 * self.scale))
        cols = [('bus', 'Bağlantı', 150, 'w'), ('status', 'Durum', 110, 'w'), ('id', 'Aygıt örnek kimliği', 380, 'w')]
        self.pad_tree = CheckTree(left, cols, first=('Aygıt', 280), height=4)
        self.pad_tree.pack(fill='both', expand=True)
        tk.Label(left, text='TANI', fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(anchor='w', pady=(6, 2))
        self.pad_diag = tk.Text(left, height=6, bg=TREE_BG, fg=FG, relief='flat', font=('Segoe UI', 9), wrap='word', padx=8, pady=6)
        self.pad_diag.pack(fill='both', expand=True)
        for tag, col in (('bad', BAD_C), ('warn', WARN), ('ok', OK_C), ('info', MUTED)):
            self.pad_diag.tag_configure(tag, foreground=col)
        self.pad_diag.configure(state='disabled')
        right = tk.Frame(body, bg=PANEL)
        body.add(right, stretch='never', minsize=int(420 * self.scale))
        rt = tk.Frame(right, bg=PANEL); rt.pack(fill='x')
        tk.Label(rt, text='CANLI TEST', fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(side='left')
        self.pad_slot = tk.IntVar(value=0)
        tk.Label(rt, text='   XInput yuvası:', fg=MUTED, bg=PANEL, font=('Segoe UI', 9)).pack(side='left')
        for i in range(4):
            tk.Radiobutton(rt, text=str(i + 1), variable=self.pad_slot, value=i, fg=FG, bg=PANEL, selectcolor=PANEL2, activebackground=PANEL,
                           activeforeground=FG, font=('Segoe UI', 9), command=self._pad_slot_changed).pack(side='left')
        self.pad_canvas = GamepadCanvas(right, self.scale * 0.72)
        self.pad_canvas.pack(pady=(2, 2))
        info = tk.Frame(right, bg=PANEL2, padx=10, pady=5); info.pack(fill='x')
        info.grid_columnconfigure(1, weight=1); info.grid_columnconfigure(3, weight=1)
        self.pad_info = {}
        for key, text, r, col, span in (('conn', 'Bağlantı', 0, 0, 1), ('bat', 'Pil', 0, 2, 1), ('pressed', 'Basılı', 1, 0, 1), ('drift', 'Kayma', 1, 2, 1)):
            tk.Label(info, text=text, anchor='w', fg=MUTED, bg=PANEL2, font=('Segoe UI', 9)).grid(row=r, column=col, sticky='w', padx=(0, 6))
            v = tk.StringVar(value='—')
            tk.Label(info, textvariable=v, anchor='w', fg=FG, bg=PANEL2, font=('Consolas', 9)).grid(row=r, column=col + 1, columnspan=span, sticky='w', padx=(0, 12))
            self.pad_info[key] = v
        self.pad_rows, self.pad_stats, self.pad_bt, self.pad_slots_seen = [], {}, {}, None
        self.pad_drift_hits = 0
        self.pad_tick_n = 0
        self.pad_tab = None
        self._pad_render_diag()

    def _pad_selected(self):
        try:
            if self.pad_tab is None:
                self.pad_tab = self.tabs.index('Kol / Gamepad')
            return self.tabs.index('current') == self.pad_tab
        except tk.TclError:
            return False

    def _pad_slot_changed(self):
        self.pad_drift_hits = 0

    def _pad_tick(self):
        """Canli test: sekme acikken 50 ms, degilken 600 ms araliklarla XInput okunur (yalnizca Windows)."""
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        if not self._pad_selected():
            self.after(600, self._pad_tick); return
        if not self.xi.available():
            self.pad_canvas.show(None, 'Canlı test yalnızca Windows\'ta (XInput) çalışır.')
            self.pad_info['conn'].set('XInput yok')
            self.after(600, self._pad_tick); return
        slot = self.pad_slot.get()
        st = self.xi.state(slot)
        if st:
            self.pad_canvas.show(st, 'L %+6d %+6d   R %+6d %+6d   LT %3d  RT %3d' % (st['lx'], st['ly'], st['rx'], st['ry'], st['lt'], st['rt']))
            self.pad_info['conn'].set('Bağlı (yuva %d, %s)' % (slot + 1, self.xi.name))
            bat = self.xi.battery(slot)
            self.pad_info['bat'].set(core.xinput_battery_text(*bat) if bat else '—')
            self.pad_info['pressed'].set(' '.join(core.xinput_pressed(st['buttons'])) or '—')
            idle = not st['buttons'] and not st['lt'] and not st['rt']
            drifting = idle and (core.stick_drift(st['lx'], st['ly']) or core.stick_drift(st['rx'], st['ry']))
            self.pad_drift_hits = min(200, self.pad_drift_hits + 1) if drifting else max(0, self.pad_drift_hits - 2)
            self.pad_info['drift'].set('Olası kayma (drift)' if self.pad_drift_hits > 60 else 'Yok')
        else:
            self.pad_canvas.show(None, 'Yuva %d boş — kolu bağlayın ya da başka yuvayı seçin.' % (slot + 1))
            for k in ('conn', 'bat', 'pressed', 'drift'):
                self.pad_info[k].set('Bağlı değil' if k == 'conn' else '—')
        self.pad_tick_n += 1
        slots = self.xi.connected_slots() if (self.pad_tick_n % 20 == 0 or self.pad_slots_seen is None) else self.pad_slots_seen   # bos yuva sorgusu pahali: ~1 sn'de bir
        if slots != self.pad_slots_seen:
            self.pad_slots_seen = slots
            self._pad_render_diag()
        self.after(50, self._pad_tick)

    def pad_scan(self):
        def done(job):
            devs = [d for d in job.data if d.get('type') == 'controller']
            bt = [d for d in job.data if d.get('type') == 'bt-radio']
            self.pad_bt = bt[0] if bt else {}
            self.pad_rows, self.pad_stats = core.build_controller_view(devs)
            for k, (v, text) in self.pad_chips.items():
                v.set('%d %s' % (self.pad_stats.get(k, 0), text))
            t = self.pad_tree
            t.clear()
            for i, r in enumerate(self.pad_rows):
                t.add('c%d' % i, r.get('name') or '(adsız aygıt)', (r['bus_text'], ('Sorunlu: ' if r['problem_dev'] else '') + (r.get('status') or '?'), r['id']),
                      checked=r['problem_dev'], tags=('risky',) if r['problem_dev'] else (), payload=r)
            if not self.pad_rows:
                t.add('none', 'Xbox kolu bulunamadı', ('', '', ''), checkable=False)
            t.refresh_marks()
            self._pad_render_diag()
        self.start([Job('Xbox kolları', cmd=ps_cmd('controller-list'), on_done=done, show_output=False)])

    def _pad_render_diag(self):
        slots = self.pad_slots_seen if self.pad_slots_seen is not None else []
        lines = core.controller_advice(self.pad_stats, self.xi.available(), slots, self.pad_bt, bool(core.fc_settings_dirs()))
        if not self.pad_stats:
            lines.insert(0, ('info', '"Tara" ile Xbox kol aygıtlarını listeleyin.'))
        d = self.pad_diag
        d.configure(state='normal'); d.delete('1.0', 'end')
        for level, text in lines:
            d.insert('end', '●  ' + text + '\n', level)
        d.configure(state='disabled')

    def pad_reset(self):
        rows = [p for p in self.pad_tree.checked_payloads() if p] or list(self.pad_rows)
        if not rows:
            messagebox.showinfo('Kol / Gamepad', 'Önce "Tara" ile kol aygıtlarını listeleyin.'); return
        if not self.need_admin('controller-reset'):
            return
        names = '\n'.join('• %s (%s)' % (r.get('name') or r['id'], r['bus_text']) for r in rows[:12])
        if not messagebox.askyesno('Kol sürücüsünü sıfırla', 'Şu aygıtların kaydı kaldırılıp donanım yeniden taranacak:\n\n%s\n\n'
                                   'USB ile bağlıysa ardından kabloyu çıkarıp takın; Bluetooth ise gerekirse yeniden eşleştirin.\nDevam edilsin mi?' % names):
            return
        self.start([Job('Kol sürücüsünü sıfırla (%d)' % len(rows), cmd=ps_cmd('controller-reset', InstanceIds='|'.join(r['id'] for r in rows)),
                        cancel_ok=False, on_done=lambda j: self.pad_scan())])

    def pad_bt_restart(self):
        if not self.need_admin('bt-restart'):
            return
        self.start([Job('Bluetooth hizmetini yeniden başlat', cmd=ps_cmd('bt-restart'), cancel_ok=False, on_done=lambda j: self.pad_scan())])

    def pad_open(self, target, title):
        if not IS_WIN:
            self.write('%s yalnızca Windows\'ta açılır (%s).\n' % (title, target)); return
        try:
            os.startfile(target)
            self.write('%s açıldı.\n' % title)
        except OSError as e:
            self.write('%s açılamadı: %s\n' % (title, e))

    def pad_xbox_accessories(self):
        def work(runner, job):
            if not IS_WIN:
                runner.say('Xbox Accessories yalnızca Windows\'ta açılır.'); return 0
            r = subprocess.run(['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive', '-Command',
                                "(Get-AppxPackage -Name 'Microsoft.XboxDevices' | Select-Object -First 1).PackageFamilyName"],
                               capture_output=True, text=True, timeout=30, creationflags=CREATIONFLAGS)
            fam = (r.stdout or '').strip()
            if fam:
                runner.say('Xbox Accessories açılıyor. Kol USB ile takılıyken "..." > "Güncelleme" ile firmware denetlenir.')
                os.startfile('shell:AppsFolder\\%s!App' % fam)
            else:
                runner.say('Xbox Accessories kurulu değil; Microsoft Store sayfası açılıyor.')
                os.startfile('ms-windows-store://pdp/?productid=9NBLGGH30XJ3')
            return 0
        self.start([Job('Xbox Accessories', func=work, cancel_ok=False)])

    def _pad_fc_dir(self):
        dirs = core.fc_settings_dirs()
        if dirs:
            return dirs[-1]
        picked = filedialog.askdirectory(title='EA SPORTS FC ayar klasörünü seçin (%LOCALAPPDATA%\\EA SPORTS FC xx)')
        return pathlib.Path(picked) if picked else None

    def pad_open_fc_dir(self):
        dirs = core.fc_settings_dirs()
        if not dirs:
            messagebox.showinfo('FC ayar klasörü', 'EA SPORTS FC klasörü bulunamadı (%LOCALAPPDATA%). Oyun bu kullanıcıyla hiç açılmamış olabilir.'); return
        self.pad_open(str(dirs[-1]), dirs[-1].name)

    def pad_fc_reset(self):
        folder = self._pad_fc_dir()
        if not folder:
            return
        files = core.fc_settings_files(folder)
        if not files:
            messagebox.showinfo('FC ayarları', '"%s\\settings" altında Settings dosyası yok.' % folder); return
        if not messagebox.askyesno('FC ayarlarını sıfırla', '%s\n\nŞu dosyalar yedeklenip silinecek; oyun açılışta yenilerini oluşturur '
                                   '(kontrol ve görüntü ayarları varsayılana döner):\n\n%s\n\nOyun KAPALI olmalı. Devam edilsin mi?'
                                   % (folder.name, '\n'.join('• ' + f.name for f in files))):
            return

        def work(runner, job):
            bdir, names = core.fc_reset_settings(folder)
            runner.say('Yedeklendi ve sıfırlandı (%d dosya): %s' % (len(names), ', '.join(names)))
            runner.say('Yedek klasörü: %s  — geri almak için dosyaları settings klasörüne kopyalayın.' % bdir)
            return 0
        self.start([Job('FC ayarlarını yedekle ve sıfırla', func=work, cancel_ok=False)])


register_palette_module(globals())
