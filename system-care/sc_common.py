# -*- coding: utf-8 -*-
"""AGFO System Care — Guncelleme (paket + GitHub) ve ortak yardimcilar: is kuyrugu, gunluk, durum. App sinifinin parcasi (mixin); paylasilan adlar sc_base'den gelir."""
from sc_base import *  # noqa: F401,F403


class CommonMixin:
    # ------------------------------------------------------------------ GUNCELLEME (paket yukleme)
    def open_updater(self):
        if getattr(self, 'upd_win', None) and self.upd_win.winfo_exists():
            self.upd_win.lift(); return
        win = self.upd_win = tk.Toplevel(self); win.title('AGFO System Care — Güncelleme'); win.configure(bg=PANEL); win.transient(self)
        w, h = int(860 * self.scale), int(620 * self.scale)
        win.geometry('%dx%d+%d+%d' % (w, h, self.winfo_rootx() + max(0, (self.winfo_width() - w) // 2), self.winfo_rooty() + 40))
        top = tk.Frame(win, bg=PANEL); top.pack(fill='x', padx=16, pady=(14, 4))
        tk.Label(top, text='Güncelleme', fg=FG, bg=PANEL, font=('Segoe UI', 13, 'bold')).pack(side='left')
        tk.Label(top, text='Kurulu sürüm: %s' % VERSION, fg=OK_C, bg=PANEL2, font=('Segoe UI', 9, 'bold'), padx=10, pady=3).pack(side='left', padx=10)
        self.label(win, 'Konum: %s\nGüncelleme paketi (.zip) seçin. Paket önce denetlenir (yapı, sürüm, MANIFEST/SHA-256, Python derleme, PowerShell sözdizimi); '
                        'mevcut sürüm yedeklenir, yeni dosyalar yerleştirilir ve uygulama yeniden başlar. Bir adım başarısız olursa önceki sürüm otomatik geri yüklenir. '
                        'Ayarlarınız ve günlükler etkilenmez.' % self.install_dir, wraplength=int(820 * self.scale)).pack(fill='x', padx=16)
        bar = tk.Frame(win, bg=PANEL); bar.pack(fill='x', padx=16, pady=8)
        self.btn(bar, 'GitHub\'da denetle', lambda: self.gh_check(force=True), 'go')
        self.btn(bar, 'Güncelleme paketi seç (.zip)…', self.upd_pick, 'ghost')
        self.upd_apply_btn = self.btn(bar, 'Uygula ve yeniden başlat', self.upd_apply, 'danger', action=False)   # durumu yalnizca denetim sonucu belirler
        self.upd_apply_btn.configure(state='disabled')
        ghf = tk.Frame(win, bg=PANEL); ghf.pack(fill='x', padx=16, pady=(0, 6))
        self.upd_gh_state = tk.StringVar(value='GitHub deposu: %s (etiket: %s*)' % (ghu.GITHUB_REPO, core.GH_PREFIX))
        tk.Label(ghf, textvariable=self.upd_gh_state, fg=MUTED, bg=PANEL, font=('Segoe UI', 9)).pack(side='left')
        self.upd_auto = tk.BooleanVar(value=self.settings.get('auto_update_check', True))

        def _auto():
            self.settings['auto_update_check'] = bool(self.upd_auto.get())
            core.save_settings(self.settings)
        ttk.Checkbutton(ghf, text='Açılışta güncellemeleri denetle', variable=self.upd_auto, command=_auto).pack(side='right')
        self.upd_check = tk.Text(win, height=11, bg=LOG_BG, fg=LOG_FG, relief='flat', font=('Consolas', 9), padx=10, pady=8, wrap='word')
        self.upd_check.pack(fill='both', expand=True, padx=16)
        for tg, col in (('ok', OK_C), ('fail', BAD_C), ('warn', WARN), ('h', ACCENT)):
            self.upd_check.tag_configure(tg, foreground=col)
        self.upd_check.insert('end', 'Paket seçilmedi.'); self.upd_check.configure(state='disabled')
        low = tk.Frame(win, bg=PANEL); low.pack(fill='x', padx=16, pady=(8, 14))
        tk.Label(low, text='Yedekler (en son %d)' % core.UPDATE_KEEP_BACKUPS, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.upd_bk = ttk.Treeview(low, columns=('ver', 'time'), show='headings', height=3)
        self.upd_bk.heading('ver', text='Sürüm'); self.upd_bk.heading('time', text='Yedek zamanı')
        self.upd_bk.column('ver', width=140); self.upd_bk.column('time', width=220)
        self.upd_bk.pack(side='left', fill='x', expand=True)
        rb = tk.Frame(low, bg=PANEL); rb.pack(side='left', padx=10)
        self.btn(rb, 'Seçili yedeğe dön', self.upd_rollback, 'ghost', side='top')
        self.btn(rb, 'Geçmiş', self.upd_history, 'ghost', action=False, side='top')
        self.upd_info = None
        self._upd_refresh_backups()

    def _upd_refresh_backups(self):
        if not getattr(self, 'upd_bk', None) or not self.upd_bk.winfo_exists():
            return
        self.upd_bk.delete(*self.upd_bk.get_children())
        for b in core.list_backups(self.backup_root):
            self.upd_bk.insert('', 'end', iid=b['path'], values=(b['version'], b['time']))

    def _upd_show(self, lines):
        tx = self.upd_check
        tx.configure(state='normal'); tx.delete('1.0', 'end')
        for text, tag in lines:
            tx.insert('end', text + '\n', tag)
        tx.configure(state='disabled')

    def upd_pick(self):
        path = filedialog.askopenfilename(parent=self.upd_win, title='Güncelleme paketi seçin', filetypes=[('Güncelleme paketi', '*.zip'), ('Tüm dosyalar', '*.*')])
        if not path:
            return
        self.upd_apply_btn.configure(state='disabled')
        stage = core.APP_DATA_DIR / 'update-stage'
        self._upd_show([('Denetleniyor: %s' % path, 'h')])

        def work(runner, job):
            info = core.inspect_update(path, VERSION)
            checks = []
            if info['ok']:
                core.stage_update(path, info, stage)
                checks = core.preflight(stage)
            job.data = [path, info, checks]
            return 0 if info['ok'] and not any(st == 'fail' for _, st, _ in checks) else 2
        self.start([Job('Güncelleme paketi denetimi', func=work, on_done=self._upd_checked, cancel_ok=False)])

    def _upd_checked(self, job):
        path, info, checks = job.data
        L = [('Paket: %s' % path, 'h')]
        if info['version']:
            arrow = '%s → %s' % (VERSION, info['version'])
            L.append(('✓ Sürüm: %s%s' % (arrow, '  (DÜŞÜRME)' if info['downgrade'] else ('  (aynı sürüm, yeniden kurulum)' if info['same'] else '')),
                      'warn' if (info['downgrade'] or info['same']) else 'ok'))
        for e in info['errors']:
            L.append(('✗ ' + e, 'fail'))
        if info['ok']:
            L.append(('✓ Paket yapısı ve dosya yolları güvenli; zorunlu dosyalar mevcut', 'ok'))
            L.append(('✓ %d çalışma dosyası: %s' % (len(info['files']), ', '.join(sorted(info['files'])[:8]) + (' …' if len(info['files']) > 8 else '')), 'ok'))
            if info['manifest']:
                L.append(('✓ MANIFEST.json: tüm dosyaların SHA-256 özetleri doğrulandı', 'ok'))
        for wmsg in info['warnings']:
            L.append(('! ' + wmsg, 'warn'))
        for name, st, det in checks:
            L.append((('✓ ' if st == 'ok' else ('✗ ' if st == 'fail' else '– ')) + name + (('  — ' + det) if det else ''), {'ok': 'ok', 'fail': 'fail'}.get(st, 'warn')))
        ready = info['ok'] and not any(st == 'fail' for _, st, _ in checks)
        L.append(('', None))
        L.append(('Hazır: "Uygula ve yeniden başlat" ile kurabilirsiniz.' if ready else 'Bu paket kurulamaz.', 'ok' if ready else 'fail'))
        self.upd_info = (path, info) if ready else None
        if getattr(self, 'upd_win', None) and self.upd_win.winfo_exists():
            self._upd_show(L)
            self.upd_apply_btn.configure(state='normal' if ready else 'disabled')

    def upd_apply(self):
        if not self.upd_info or self.busy:
            return
        self.upd_apply_btn.configure(state='disabled')
        path, info = self.upd_info
        msg = 'AGFO System Care %s → %s güncellenecek.\nMevcut sürüm yedeklenecek; uygulama yeniden başlatılacak.' % (VERSION, info['version'])
        if info['downgrade']:
            msg += '\n\nDİKKAT: Bu daha ESKİ bir sürüm.'
        if not info['manifest']:
            msg += '\n\nUYARI: Pakette MANIFEST.json yok; dosya bütünlüğü doğrulanamadı. Yalnızca güvendiğiniz kaynaktan gelen paketi kurun.'
        if not messagebox.askyesno('Güncellemeyi uygula', msg + '\n\nDevam edilsin mi?', parent=self.upd_win):
            return
        stage = core.APP_DATA_DIR / 'update-stage'

        def work(runner, job):
            runner.say('Yedekleniyor ve güncelleniyor: %s' % self.install_dir)
            job.data = [core.apply_update(stage, self.install_dir, self.backup_root, VERSION, info['version'])]
            runner.say('Güncellendi. Yedek: %s' % job.data[0])
            import shutil
            shutil.rmtree(stage, ignore_errors=True)
            return 0
        self.start([Job('Güncelleme uygula', func=work, on_done=lambda j: self._upd_done(j, info['version']), cancel_ok=False)])

    def _upd_done(self, job, new_version):
        self._upd_refresh_backups()
        if job.code != 0 or not job.data:
            self._upd_show([('✗ Güncelleme uygulanamadı; önceki sürüm geri yüklendi. Ayrıntı işlem günlüğünde.', 'fail')])
            return
        self.upd_info = None
        self._upd_show([('✓ AGFO System Care %s kuruldu. Uygulama yeniden başlatılıyor…' % new_version, 'ok')])
        self.after(800, self.restart_app)

    def upd_rollback(self):
        sel = self.upd_bk.selection()
        if not sel:
            messagebox.showinfo('Yedekler', 'Listeden bir yedek seçin.', parent=self.upd_win); return
        b = next((x for x in core.list_backups(self.backup_root) if x['path'] == sel[0]), None)
        if not b or not messagebox.askyesno('Önceki sürüme dön', 'Sürüm %s (%s) geri yüklenecek; mevcut sürüm de yedeklenecek. Uygulama yeniden başlatılacak. Devam?'
                                            % (b['version'], b['time']), parent=self.upd_win):
            return

        def work(runner, job):
            target, bdir = core.rollback_update(b['path'], self.install_dir, VERSION)
            job.data = [target]
            runner.say('Geri dönüldü: %s (mevcut sürüm yedeği: %s)' % (target, bdir))
            return 0
        self.start([Job('Önceki sürüme dön', func=work, on_done=lambda j: self._upd_done(j, j.data[0] if j.data else ''), cancel_ok=False)])

    def upd_history(self):
        h = core.update_history(15)
        messagebox.showinfo('Güncelleme geçmişi', '\n'.join(h) if h else 'Henüz güncelleme yapılmadı.', parent=self.upd_win)

    # ------------------------------------------------------------------ GITHUB GUNCELLEME (tek tik)
    def gh_check(self, force=True):
        """Arka planda GitHub surumlerini denetler (is kuyrugunu mesgul etmez)."""
        def work():
            res = ghu.check_for_update(core.GH_PREFIX, VERSION, core.GH_STATE, core.GH_ASSET, force=force,
                                       user_agent='AGFO-System-Care/' + VERSION)
            self.messages.put(('call', lambda: self._gh_checked(res, force)))   # Tk yalnizca ana is parcacigindan
        threading.Thread(target=work, daemon=True).start()

    def _gh_checked(self, res, force):
        st = res.get('status')
        if st == 'update':
            self.gh_result = res
            rel = res['release']
            self.gh_banner_text.set('Yeni sürüm hazır: AGFO System Care %s  (kurulu: %s%s)' % (res['version'], VERSION,
                                    (', yayın: ' + rel['published']) if rel.get('published') else ''))
            if not self.gh_banner.winfo_ismapped():
                self.gh_banner.pack(fill='x', padx=22, pady=(0, 8), before=self.main)
            self.write('GitHub: yeni sürüm %s mevcut — üstteki "Şimdi güncelle" ile tek tıkla kurabilirsiniz.\n' % res['version'])
        elif force:
            msg = {'current': 'Güncelsiniz (son sürüm %s).' % res.get('version', VERSION), 'none': 'GitHub\'da henüz System Care sürümü yok.',
                   'skipped': 'Sürüm %s atlanmış olarak işaretli.' % res.get('version', ''), 'error': 'Denetlenemedi: %s' % res.get('message', '')}.get(st, st)
            self.write('GitHub güncelleme denetimi: %s\n' % msg)
            if getattr(self, 'upd_gh_state', None):
                try:
                    self.upd_gh_state.set(msg)
                except tk.TclError:
                    pass
        if st == 'update' and getattr(self, 'upd_gh_state', None):
            try:
                self.upd_gh_state.set('Yeni sürüm: %s — "Şimdi güncelle" ile kurun.' % res['version'])
            except tk.TclError:
                pass

    def gh_show_notes(self):
        if not self.gh_result:
            return
        rel = self.gh_result['release']
        messagebox.showinfo('Sürüm %s notları' % self.gh_result['version'], (rel.get('notes') or 'Not eklenmemiş.')[:3000] + '\n\n' + rel.get('url', ''))

    def gh_skip(self):
        if self.gh_result:
            ghu.skip_version(core.GH_STATE, self.gh_result['version'])
            self.write('Sürüm %s atlandı; daha yeni bir sürüm çıkınca yeniden bildirilecek.\n' % self.gh_result['version'])
        self.gh_banner.pack_forget()

    def gh_update(self):
        """Tek tik: indir -> SHA-256 -> paket denetimi -> on kontrol -> yedekle/uygula -> yeniden baslat."""
        res = self.gh_result
        if not res or self.busy:
            if self.busy:
                messagebox.showinfo('Meşgul', 'Bir işlem sürüyor; bitince tekrar deneyin.')
            return
        rel, asset = res['release'], res['asset']
        notes = (rel.get('notes') or '').strip()
        if not messagebox.askyesno('Güncelleme', 'AGFO System Care %s → %s\n\n%s\n\nİndirilip doğrulanacak, mevcut sürüm yedeklenecek ve uygulama '
                                   'yeniden başlatılacak. Devam edilsin mi?' % (VERSION, res['version'], (notes[:800] + ('…' if len(notes) > 800 else '')) or 'Sürüm notu yok.')):
            return
        dest = core.GH_DOWNLOAD_DIR / asset['name']
        stage = core.APP_DATA_DIR / 'update-stage'

        def work(runner, job):
            runner.say('GitHub: %s indiriliyor (%s)' % (asset['name'], rel.get('url', '')))
            sha = ghu.expected_sha256(rel, asset, user_agent='AGFO-System-Care/' + VERSION)
            ghu.download_asset(asset, dest, sha, runner.progress_cb('İndiriliyor'), runner.stop.is_set, user_agent='AGFO-System-Care/' + VERSION)
            runner.say('İndirildi ve SHA-256 doğrulandı (%s…).' % sha[:16])
            info = core.inspect_update(str(dest), VERSION)
            if not info['ok']:
                raise OSError('Paket denetimi başarısız: ' + '; '.join(info['errors']))
            if info['version'] != res['version']:
                raise OSError('Paket sürümü (%s) etiketle (%s) uyuşmuyor.' % (info['version'], res['version']))
            core.stage_update(str(dest), info, stage)
            checks = core.preflight(stage)
            bad = [n + ': ' + d for n, s_, d in checks if s_ == 'fail']
            for n, s_, d in checks:
                runner.say(('✓ ' if s_ == 'ok' else ('✗ ' if s_ == 'fail' else '– ')) + n + (('  ' + d) if d else ''))
            if bad:
                raise OSError('Ön kontrol başarısız: ' + '; '.join(bad))
            runner.say('Yedekleniyor ve kuruluyor: %s' % self.install_dir)
            bdir = core.apply_update(stage, self.install_dir, self.backup_root, VERSION, info['version'])
            import shutil
            shutil.rmtree(stage, ignore_errors=True)
            try:
                dest.unlink()
            except OSError:
                pass
            job.data = [info['version'], bdir]
            runner.say('Kuruldu (yedek: %s).' % bdir)
            return 0

        def done(job):
            if job.code == 0 and job.data:
                self.gh_banner.pack_forget()
                self.write('AGFO System Care %s kuruldu; uygulama yeniden başlatılıyor…\n' % job.data[0])
                self.after(900, self.restart_app)
            else:
                messagebox.showerror('Güncelleme', 'Güncelleme tamamlanamadı; kurulu sürüm değişmedi veya geri yüklendi. Ayrıntı işlem günlüğünde.')
        self.start([Job('GitHub güncellemesi %s' % res['version'], func=work, on_done=done, cancel_ok=True)])

    def restart_app(self):
        if self.no_restart:
            return
        try:
            subprocess.Popen([sys.executable, str(pathlib.Path(self.install_dir) / 'app.pyw')], cwd=str(self.install_dir),
                             creationflags=getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
        except OSError as e:
            messagebox.showerror('Yeniden başlatma', 'Uygulamayı elle yeniden açın: %s' % e)
            return
        self.destroy()

    # ------------------------------------------------------------------ ortak
    def need_admin(self, action):
        if action in ADMIN_ACTIONS and not self.admin and IS_WIN:
            return True                     # 4.0: uygulama yeniden acilmaz; is calisirken Windows UAC onayi ister
        if action in ADMIN_ACTIONS and not self.admin:
            if messagebox.askyesno('Yönetici gerekli', 'Bu işlem yönetici yetkisi ister. Uygulama yönetici olarak yeniden açılsın mı?'):
                self.elevate()
            return False
        return True

    def start(self, jobs, quiet=False):
        if self.busy and self.in_callback:
            # Bir isin sonuc geri-cagrisindan baslatilan zincir is: mevcut sira bitince calistir.
            self.pending.extend(jobs)
            return True
        if self.busy:
            if not quiet:
                messagebox.showinfo('Meşgul', 'Bir işlem sürüyor; bitmesini bekleyin veya Durdur\'a basın.')
            return False
        self.busy = True
        self._set_buttons('disabled')
        self.runner.run(jobs)
        return True

    def _set_buttons(self, state):
        # Kapatilan pencerelerin (or. Guncelleme) dugmeleri listeden ayiklanir.
        alive = []
        for b in self.action_buttons:
            try:
                if b.winfo_exists():
                    b.configure(state=state)
                    alive.append(b)
            except tk.TclError:
                pass
        self.action_buttons = alive

    def finish(self):
        self.busy = False
        self.cancel_btn.configure(state='disabled')
        self._set_buttons('normal')

    def cancel(self):
        if not self.busy:
            return
        if not messagebox.askyesno('Durdur', 'Süren işlem (ve sıradaki işler) durdurulsun mu?'):
            return
        self.write('Kullanıcı tarafından durduruluyor...\n')
        self.runner.kill()

    def write(self, msg):
        self.log.configure(state='normal'); self._insert(msg); self._trim(); self.log.see('end'); self.log.configure(state='disabled')

    def _insert(self, msg, progress=False):
        if self.progress_active:
            self.log.delete('end-1l linestart', 'end-1c')
            self.progress_active = False
        self.log.insert('end', msg)
        self.progress_active = progress

    def _trim(self):
        try:
            lines = int(self.log.index('end-1c').split('.')[0])
        except Exception:
            return
        if lines > LOG_WIDGET_MAX_LINES:
            self.log.delete('1.0', '%d.0' % LOG_WIDGET_TRIM_LINES)

    def clear_log(self):
        self.log.configure(state='normal'); self.log.delete('1.0', 'end'); self.progress_active = False; self.log.configure(state='disabled')

    def poll(self):
        items = []
        try:
            while len(items) < 2000:
                items.append(self.messages.get_nowait())
        except queue.Empty:
            pass
        if items:
            self.log.configure(state='normal')
            for kind, val in items:
                if kind == 'line':
                    self._insert(val)
                elif kind == 'progress':
                    self._insert(val, progress=True)
                elif kind == 'status':
                    self.status.set('Çalışıyor: ' + val)
                elif kind == 'cancel_ok':
                    self.cancel_btn.configure(state='normal' if val else 'disabled')
                elif kind == 'jobdone':
                    job = val
                    if job.cmd or job.shell:
                        self._insert('Sonuç: %s — %s%s\n' % (job.code, hint(job.code), ('  ·  günlük: ' + job.logfile) if job.logfile else ''))
                    self.status.set(hint(job.code) + ' — ' + job.title)
                    if job.on_done:
                        self.log.configure(state='disabled')
                        self.in_callback = True
                        try:
                            job.on_done(job)
                        except Exception as e:
                            self.write('Arayüz hatası (%s): %s\n' % (job.title, e))
                        finally:
                            self.in_callback = False
                        self.log.configure(state='normal')
                elif kind == 'call':
                    self.log.configure(state='disabled')
                    try:
                        val()
                    except Exception as e:
                        self.write('Arayüz hatası: %s\n' % e)
                    self.log.configure(state='normal')
                elif kind == 'alldone':
                    self.finish()
                    if self.pending:
                        nxt, self.pending = self.pending, []
                        self.start(nxt)
            self._trim(); self.log.see('end'); self.log.configure(state='disabled')
        self.after(POLL_MS, self.poll)

    def elevate(self):
        if not IS_WIN or self.busy:
            return
        exe = sys.executable
        params = '' if getattr(sys, 'frozen', False) else '"' + str(BASE / 'app.pyw') + '"'
        try:
            result = ctypes.windll.shell32.ShellExecuteW(None, 'runas', exe, params, str(BASE), 1)
            if result <= 32:
                raise OSError('Yönetici izni verilmedi')
            self.destroy()
        except Exception as e:
            messagebox.showerror('Yönetici erişimi', str(e))

    def _net_colors(self):
        g = globals()
        return {k: g[k] for k in ('BG', 'PANEL', 'PANEL2', 'FG', 'MUTED', 'ACCENT', 'WARN', 'OK_C', 'BAD_C', 'SEL', 'SEL_FG', 'TREE_BG', 'LOG_BG', 'LOG_FG')}

    def on_close(self):
        try:
            self.net.close()
        except Exception:
            pass
        if self.busy:
            if not messagebox.askyesno('İşlem sürüyor', 'Bir işlem sürüyor. Durdurulup uygulama kapatılsın mı?\n'
                                       '(Kurulum/onarım işlemleri arka planda tamamlanabilir.)'):
                return
            self.runner.kill()
        self.destroy()

    def open_logs(self):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        if IS_WIN:
            os.startfile(str(LOG_DIR))


register_palette_module(globals())
