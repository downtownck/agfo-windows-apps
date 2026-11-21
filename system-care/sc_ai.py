# -*- coding: utf-8 -*-
"""AGFO System Care — 4.3 AI asistan sayfasi (AGFO AI Manager baglantisi). App sinifinin parcasi (mixin).

Ag cagrilari ayri is parcaciginda yapilir; Runner'i (islem kuyrugunu) mesgul etmez, yani AI yanit verirken diger sayfalar
kullanilabilir. Tk nesnelerine yalniz ana is parcacigindan dokunulur (sonuc self.after ile alinir)."""
from sc_base import *  # noqa: F401,F403
import re  # noqa: E402
import webbrowser  # noqa: E402
import care_ai as ai  # noqa: E402

CTX_TITLES = [('hw', 'Sistem özeti'), ('procs', 'Çalışan uygulamalar'), ('services', 'Servisler'), ('startup', 'Başlangıç'), ('log', 'İşlem günlüğü')]
CTX_LIST_JOB = {'procs': ('proc-list', 'proc'), 'services': ('svc-list', 'svc'), 'startup': ('startup-list', 'startup')}


class AiPage:
    # ------------------------------------------------------------------ sayfa
    def _tab_ai(self, f):
        self.ai_cfg = ai.load_config(self.settings)
        self.ai_history, self.ai_busy, self.ai_result = [], False, None
        head = tk.Frame(f, bg=PANEL); head.pack(fill='x', padx=16, pady=(12, 2))
        tk.Label(head, text='AI asistan', fg=FG, bg=PANEL, font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.ai_state = tk.StringVar(value='')
        tk.Label(head, textvariable=self.ai_state, fg=ACCENT, bg=PANEL2, font=('Segoe UI', 9, 'bold'), padx=10, pady=3).pack(side='left', padx=(10, 0))
        self.label(f, 'AGFO AI Editor gibi AGFO AI Manager\'a bağlanır: API anahtarlarınız WordPress sitenizde kalır, bu bilgisayarda yalnız '
                      'şifreli bir bağlantı anahtarı durur. Seçtiğiniz sistem verisi (donanım, süreçler, servisler, başlangıç, günlük) soruyla '
                      'birlikte gönderilir; göndermeden önce "Gönderilecek veri" ile görebilirsiniz. Kullanıcı adı, bilgisayar adı, e-posta, '
                      'seri no, MAC ve genel IP varsayılan olarak maskelenir. AI yalnız öneri verir; hiçbir işlemi kendisi uygulamaz.',
                   wraplength=int(1060 * self.scale)).pack(fill='x', padx=16, pady=(2, 6))

        # bağlantı
        conn = ttk.Labelframe(f, text=' Bağlantı ', padding=8)
        conn.pack(fill='x', padx=16, pady=(0, 6))
        row = tk.Frame(conn, bg=PANEL); row.pack(fill='x')
        tk.Label(row, text='Site adresi', fg=FG, bg=PANEL).pack(side='left')
        self.ai_url = tk.StringVar(value=self.ai_cfg['url'])
        ttk.Entry(row, textvariable=self.ai_url, width=30).pack(side='left', padx=(6, 12))
        tk.Label(row, text='Bağlantı anahtarı', fg=FG, bg=PANEL).pack(side='left')
        self.ai_token = tk.StringVar(value=self.ai_cfg['token'])
        self.ai_token_entry = ttk.Entry(row, textvariable=self.ai_token, width=34, show='•')
        self.ai_token_entry.pack(side='left', padx=(6, 6))
        self.btn(row, 'Kaydet ve test et', self.ai_save_test, 'go', action=False)
        self.btn(row, 'AI Editor\'ün bağlantısını kullan', self.ai_import_editor, 'ghost', action=False)
        self.btn(row, 'Anahtar oluştur…', self.ai_open_token_page, 'ghost', action=False)
        self.btn(row, 'Bağlantıyı sil', self.ai_forget, 'ghost', action=False)
        self.ai_conn = tk.StringVar(value=self._ai_conn_text())
        tk.Label(conn, textvariable=self.ai_conn, fg=MUTED, bg=PANEL, font=('Segoe UI', 9), anchor='w', justify='left',
                 wraplength=int(1040 * self.scale)).pack(fill='x', pady=(6, 0))

        # bağlam
        ctx = tk.Frame(f, bg=PANEL); ctx.pack(fill='x', padx=16, pady=(2, 0))
        tk.Label(ctx, text='Soruya ekle:', fg=FG, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(side='left')
        self.ai_ctx = {}
        for key, title in CTX_TITLES:
            v = tk.BooleanVar(value=False)
            self.ai_ctx[key] = v
            ttk.Checkbutton(ctx, text=title, variable=v).pack(side='left', padx=(8, 0))
        self.ai_mask = tk.BooleanVar(value=self.ai_cfg.get('mask', True))
        ttk.Checkbutton(ctx, text='Kişisel bilgileri maskele', variable=self.ai_mask).pack(side='left', padx=(16, 0))
        self.btn(ctx, 'Gönderilecek veri…', self.ai_preview, 'ghost', action=False, side='right')

        quick = tk.Frame(f, bg=PANEL); quick.pack(fill='x', padx=16, pady=(6, 0))
        tk.Label(quick, text='Hızlı:', fg=FG, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(side='left', padx=(0, 6))
        self.ai_quick_btns = []
        for title, keys, prompt in ai.QUICK:
            self.ai_quick_btns.append(self.btn(quick, title, lambda k=keys, p=prompt: self.ai_ask(p, k), 'ghost', action=False))

        # sohbet
        box = tk.Frame(f, bg=PANEL); box.pack(fill='both', expand=True, padx=16, pady=8)
        self.ai_text = tk.Text(box, bg=LOG_BG, fg=LOG_FG, insertbackground=FG, relief='flat', font=('Segoe UI', 10), wrap='word',
                               padx=12, pady=10, height=12)
        ys = ttk.Scrollbar(box, orient='vertical', command=self.ai_text.yview)
        self.ai_text.configure(yscrollcommand=ys.set, state='disabled')
        self.ai_text.pack(side='left', fill='both', expand=True); ys.pack(side='right', fill='y')
        self._ai_tags()
        self.theme_hooks.append(self._ai_tags)

        self.ai_actbox = tk.Frame(f, bg=PANEL)          # yanit uygulanabilir oneri dondurunce gorunur
        ah = tk.Frame(self.ai_actbox, bg=PANEL); ah.pack(fill='x')
        tk.Label(ah, text='Önerilen işlemler', fg=FG, bg=PANEL, font=('Segoe UI', 10, 'bold')).pack(side='left')
        self.ai_act_count = tk.StringVar(value='')
        tk.Label(ah, textvariable=self.ai_act_count, fg=MUTED, bg=PANEL, font=('Segoe UI', 9)).pack(side='left', padx=(8, 0))
        self.ai_apply_btn = self.btn(ah, 'Seçilenleri uygula', self.ai_apply, 'go', side='right')
        self.btn(ah, 'Gizle', lambda: self.ai_actbox.pack_forget(), 'ghost', action=False, side='right')
        self.btn(ah, 'Hiçbiri', lambda: self.ai_acts.set_all(False), 'ghost', action=False, side='right')
        self.btn(ah, 'Tümü', lambda: self.ai_acts.set_all(True), 'ghost', action=False, side='right')
        self.btn(ah, 'Yalnız güvenliler', lambda: self.ai_acts.set_all(True, lambda i: (self.ai_acts.payload.get(i) or {}).get('risk') == 'güvenli'),
                 'ghost', action=False, side='right')
        tk.Label(self.ai_actbox, text='İşaretleyip "Seçilenleri uygula"ya basın. Uygulamadan önce liste onaya sunulur; başlangıç ve servis değişiklikleri '
                                      'geri alınabilir (ilgili sayfadan yeniden etkinleştirin). Gri satırlar uygulanamaz: gerekçesi Durum sütununda.',
                 fg=MUTED, bg=PANEL, font=('Segoe UI', 9), anchor='w', justify='left', wraplength=int(1040 * self.scale)).pack(fill='x', pady=(2, 4))
        self.ai_acts = CheckTree(self.ai_actbox, [('act', 'İşlem', 200, 'w'), ('risk', 'Risk', 80, 'w'), ('state', 'Durum', 230, 'w'), ('why', 'Gerekçe', 420, 'w')],
                                 first=('Hedef', int(230 * self.scale)), height=7)
        self.ai_acts.pack(fill='both', expand=True)
        self.ai_actions = []

        inp = tk.Frame(f, bg=PANEL); inp.pack(fill='x', padx=16, pady=(0, 12))
        self.ai_inp = inp
        self.ai_q = tk.Text(inp, height=3, bg=PANEL2, fg=FG, insertbackground=FG, relief='flat', font=('Segoe UI', 10), wrap='word', padx=8, pady=6)
        self.ai_q.pack(side='left', fill='x', expand=True)
        self.ai_q.bind('<Control-Return>', lambda _e: (self.ai_send(), 'break')[1])
        side = tk.Frame(inp, bg=PANEL); side.pack(side='left', padx=(8, 0))
        self.ai_send_btn = self.mkbtn(side, 'Gönder  (Ctrl+Enter)', self.ai_send, 'go')
        self.ai_send_btn.pack(fill='x')
        self.mkbtn(side, 'Yanıtı kopyala', self.ai_copy_last, 'ghost', small=True).pack(fill='x', pady=(4, 0))
        self.mkbtn(side, 'Sohbeti temizle', self.ai_clear, 'ghost', small=True).pack(fill='x', pady=(4, 0))
        self._ai_say('info', 'Bağlantıyı bir kez kurun (üstte), sonra soru yazın ya da "Hızlı" düğmelerinden birini kullanın. '
                             'Diğer sayfalardaki "AI\'ya sor" düğmeleri seçtiğiniz öğeyi buraya getirir.\n')
        self._ai_update_state()

    def _ai_show_actions(self, actions):
        """Onerileri dogrulamak icin gereken listeleri (yoksa) okur, sonra tabloyu doldurur."""
        self.ai_actions = list(actions)
        if not actions:
            self.ai_actbox.pack_forget(); return
        if self.busy and not self.in_callback:          # baska is suruyor: eldeki listelerle dogrula
            self._ai_render_actions(); return
        self._ai_fill(ai.needed_lists(actions), self._ai_render_actions)

    def _ai_pages(self):
        try:
            return [self.tabs.tab(i, 'text') for i in range(len(self.tabs.pages))]
        except Exception:
            return []

    def _ai_render_actions(self):
        acts = ai.validate_actions(self.ai_actions, getattr(self, 'st_records', []), getattr(self, 'sv_records', []),
                                   getattr(self, 'pc_records', []), self._ai_pages())
        t = self.ai_acts
        t.clear()
        for i, a in enumerate(acts):
            tags = () if a['ok'] else ('muted',)
            if a['ok'] and a['risk'] != 'güvenli':
                tags = ('risky',)
            t.add('a%d' % i, a['name'], values=(a['label'], a['risk'], a['note'] or 'uygulanabilir', a['why']), tags=tags, payload=a,
                  checked=a['ok'] and a['risk'] == 'güvenli', checkable=a['ok'])
        n_ok = sum(1 for a in acts if a['ok'])
        self.ai_act_count.set('%d öneri · %d uygulanabilir' % (len(acts), n_ok))
        if not self.ai_actbox.winfo_manager():
            self.ai_actbox.pack(fill='both', padx=16, pady=(0, 8), before=self.ai_inp)

    def ai_apply(self):
        sel = [self.ai_acts.payload[i] for i in self.ai_acts.checked if self.ai_acts.payload.get(i) and self.ai_acts.payload[i]['ok']]
        if not sel:
            messagebox.showinfo('Önerilen işlemler', 'Uygulanacak öneri işaretlenmedi.'); return
        order = list(ai.ACTION_TYPES)
        sel.sort(key=lambda a: order.index(a['type']))
        lines = ['• %s: %s (%s)' % (a['label'], a['name'], a['risk']) for a in sel]
        risky = [a for a in sel if a['risk'] == 'riskli']
        msg = '%d işlem uygulanacak:\n%s%s\n\nYönetici onayı (UAC) istenebilir. Devam?' % (
            len(sel), '\n'.join(lines[:25]) + ('\n…' if len(lines) > 25 else ''),
            '\n\nUYARI: %d işlem AI tarafından "riskli" olarak işaretlendi.' % len(risky) if risky else '')
        if not (messagebox.askyesno if not risky else messagebox.askokcancel)('Önerilen işlemleri uygula', msg):
            return
        jobs, reload = [], set()
        st_on = [r for a in sel if a['type'] == 'startup_enable' for r in a['targets']]
        st_off = [r for a in sel if a['type'] == 'startup_disable' for r in a['targets']]
        for op, recs in (('disable', st_off), ('enable', st_on)):
            if not recs:
                continue
            reload.add('startup')
            user, admin = pr_split(recs)
            if user:
                jobs.append(Job('AI öneri — başlangıç: %s (%d)' % (op, len(user)), cmd=ps_cmd('startup-set', ItemsB64=pr_b64([pr_item(r) for r in user]), Op=op), cancel_ok=False))
            if admin:
                jobs.append(Job('AI öneri — başlangıç (tüm kullanıcılar): %s (%d)' % (op, len(admin)),
                                cmd=ps_cmd('startup-set', ItemsB64=pr_b64([pr_item(r) for r in admin]), Op=op), cancel_ok=False, admin=True))
        for typ, op in ai.SERVICE_OP.items():
            names = [r['name'] for a in sel if a['type'] == typ for r in a['targets']]
            if names:
                reload.add('services')
                jobs.append(Job('AI öneri — servis: %s (%d)' % (op, len(names)), cmd=ps_cmd('svc-action', ItemsB64=pr_b64([{'name': n} for n in names]), Op=op),
                                cancel_ok=False))
        procs = [{'pid': r['pid'], 'name': r['name']} for a in sel if a['type'] == 'process_end' for r in a['targets']]
        if procs:
            reload.add('procs')
            jobs.append(Job('AI öneri — süreç sonlandır (%d)' % len(procs), cmd=ps_cmd('proc-kill', ItemsB64=pr_b64(procs), Op='kill'), cancel_ok=False))
        opens = [a for a in sel if a['kind'] in ('page', 'settings')]
        self._ai_say('info', '  Uygulanıyor: %s\n' % '; '.join('%s — %s' % (a['label'], a['name']) for a in sel))
        self.write('AI önerileri uygulanıyor (%d): %s\n' % (len(sel), '; '.join('%s: %s' % (a['label'], a['name']) for a in sel)))

        def finish():
            for a in opens:
                if a['kind'] == 'settings' and IS_WIN:
                    try:
                        os.startfile(a['targets'][0])
                    except OSError as e:
                        self.write('Ayar açılamadı (%s): %s\n' % (a['name'], e))
            pages = [a for a in opens if a['kind'] == 'page']
            if pages:
                self.tabs.select(pages[0]['targets'][0])
        if not jobs:
            finish(); return

        def after_jobs(_job):
            self._ai_fill(sorted(reload), lambda: (self._ai_render_actions(), finish()), force=True)
        jobs[-1].on_done = after_jobs
        self.start(jobs)

    def _ai_tags(self):
        t = self.ai_text
        t.configure(bg=LOG_BG, fg=LOG_FG)
        t.tag_configure('me', foreground=ACCENT, font=('Segoe UI', 10, 'bold'), spacing1=8)
        t.tag_configure('ai', foreground=LOG_FG, spacing1=4, lmargin1=8, lmargin2=8)
        t.tag_configure('info', foreground=MUTED, font=('Segoe UI', 9))
        t.tag_configure('err', foreground=BAD_C)

    def _ai_say(self, tag, text):
        t = self.ai_text
        t.configure(state='normal')
        t.insert('end', text, tag)
        t.see('end')
        t.configure(state='disabled')

    def _ai_conn_text(self):
        c = self.ai_cfg
        if not c.get('url'):
            return 'Bağlı değil. WordPress › AI Manager › "AI Editor / System Care bağlantısı" sayfasından anahtar oluşturup buraya yapıştırın ' \
                   '(AI Editor bu bilgisayarda kuruluysa "AI Editor\'ün bağlantısını kullan" yeterli).'
        how = 'bağlantı anahtarı ' + ai.mask_secret(c['token']) if c.get('token') else ('uygulama parolası (%s)' % c.get('user') if c.get('user') else 'kimlik yok')
        return 'Site: %s · %s%s' % (c['url'], how, ' · AI Editor\'den alındı' if c.get('source') == 'ai-editor' else '')

    def _ai_update_state(self):
        if self.ai_busy:
            self.ai_state.set('Yanıt bekleniyor…')
        else:
            self.ai_state.set('Bağlı ayarlandı' if self.ai_cfg.get('url') else 'Bağlı değil')
        st = 'disabled' if self.ai_busy else 'normal'
        for b in [self.ai_send_btn] + self.ai_quick_btns:
            try:
                b.configure(state=st)
            except tk.TclError:
                pass

    # ------------------------------------------------------------------ bağlantı
    def _ai_client(self, cfg=None):
        c = cfg or self.ai_cfg
        return ai.ManagerClient(c.get('url', ''), c.get('token', ''), c.get('user', ''), c.get('password', ''))

    def _ai_store(self, cfg, source=''):
        ai.store_config(self.settings, cfg.get('url', ''), cfg.get('token', ''), cfg.get('user', ''), cfg.get('password', ''),
                        self.ai_mask.get(), source)
        core.save_settings(self.settings)
        self.ai_cfg = ai.load_config(self.settings)
        self.ai_conn.set(self._ai_conn_text())
        self._ai_update_state()

    def ai_save_test(self):
        url, token = self.ai_url.get().strip(), re.sub(r'\s+', '', self.ai_token.get())
        if not url or not token:
            messagebox.showinfo('AI asistan', 'Site adresini ve bağlantı anahtarını girin.'); return
        if not ai.TOKEN_RX.match(token):
            if not messagebox.askyesno('AI asistan', 'Anahtar beklenen biçimde değil (agfoed.… ile başlamalı). Yine de denensin mi?'):
                return
        try:
            url = ai.normalize_url(url)
        except ai.AIError as e:
            messagebox.showerror('AI asistan', str(e)); return
        cfg = {'url': url, 'token': token, 'user': '', 'password': ''}
        self._ai_store(cfg)
        self.ai_url.set(url)
        self._ai_test(cfg)

    def _ai_test(self, cfg):
        self.ai_conn.set('Test ediliyor…')
        self._ai_bg(lambda: self._ai_client(cfg).test(), self._ai_test_done)

    def _ai_test_done(self, ok, res):
        if not ok:
            self.ai_conn.set(self._ai_conn_text() + '\nTest başarısız: ' + str(res)); return
        parts = ['AI Manager %s' % res.get('version') if res.get('version') else 'AI Manager']
        if res.get('user'):
            parts.append('kullanıcı: ' + res['user'])
        if res.get('model'):
            parts.append('model: ' + res['model'])
        if not res.get('profile') and res.get('version'):
            parts.append('not: AI Manager 17.16+ System Care istemini kullanır; bu sürüm genel istemle yanıt verir')
        status = ('Bağlantı tamam — ' if res.get('ok') else 'Sorun: %s — ' % res.get('message')) + ' · '.join(parts)
        self.ai_conn.set(self._ai_conn_text() + '\n' + status)
        self.write('AI Manager bağlantı testi: %s\n' % status)

    def ai_import_editor(self):
        cfg = ai.import_ai_editor()
        if not cfg:
            messagebox.showinfo('AI asistan', 'Bu Windows kullanıcısında AGFO AI Editor\'ün AI Manager bağlantısı bulunamadı '
                                              '(AI Editor › Ayarlar › Bağlantı boş ya da AI Editor kurulu değil).'); return
        self.ai_url.set(cfg['url'])
        self.ai_token.set(cfg.get('token', ''))
        self._ai_store(cfg, 'ai-editor')
        self._ai_test(self.ai_cfg)

    def ai_open_token_page(self):
        url = self.ai_url.get().strip()
        try:
            url = ai.normalize_url(url)
        except ai.AIError:
            messagebox.showinfo('AI asistan', 'Önce site adresini yazın (örn. https://agfocert.com).'); return
        webbrowser.open(url + ai.TOKEN_PAGE)

    def ai_forget(self):
        if not messagebox.askyesno('AI asistan', 'Bu bilgisayardaki AI Manager bağlantısı silinsin mi? (Sitedeki anahtarı AI Manager\'dan ayrıca silebilirsiniz.)'):
            return
        self.settings.pop('ai', None)
        core.save_settings(self.settings)
        self.ai_cfg = ai.load_config(self.settings)
        self.ai_url.set(''); self.ai_token.set('')
        self.ai_conn.set(self._ai_conn_text())
        self._ai_update_state()

    # ------------------------------------------------------------------ arka plan
    def _ai_bg(self, fn, done):
        box = {}

        def work():
            try:
                box['res'] = (True, fn())
            except ai.AIError as e:
                box['res'] = (False, str(e))
            except Exception as e:  # beklenmeyen: kullaniciya goster, uygulamayi dusurme
                box['res'] = (False, '%s: %s' % (type(e).__name__, e))
        th = threading.Thread(target=work, daemon=True)
        th.start()

        def poll():
            if 'res' in box:
                done(*box['res'])
            else:
                self.after(150, poll)
        self.after(150, poll)

    # ------------------------------------------------------------------ bağlam verisi
    def _ai_parts(self, keys, extra=None):
        parts = []
        if 'hw' in keys and getattr(self, 'hw_records', None):
            try:
                parts.append(('Sistem özeti', hw_report_text(self)))
            except Exception:
                pass
        if 'procs' in keys:
            parts.append(('Çalışan uygulamalar', ai.procs_context(getattr(self, 'pc_records', []))))
        if 'services' in keys:
            parts.append(('Servisler', ai.services_context(getattr(self, 'sv_records', []))))
        if 'startup' in keys:
            parts.append(('Başlangıç', ai.startup_context(getattr(self, 'st_records', []))))
        if 'log' in keys:
            try:
                parts.append(('İşlem günlüğü', ai.log_context(self.log.get('1.0', 'end'))))
            except tk.TclError:
                pass
        if extra:
            parts.append(extra)
        return parts

    def _ai_missing_jobs(self, keys, force=False):
        """Secilen baglam henuz okunmadiysa (force: her durumda) okuyacak isler (PowerShell, salt okunur)."""
        jobs = []
        if not IS_WIN:
            return jobs
        if 'hw' in keys and not getattr(self, 'hw_records', None) and hasattr(self, 'hw_scan'):
            jobs.append('hw')
        for key, (action, typ) in CTX_LIST_JOB.items():
            attr = {'procs': 'pc_records', 'services': 'sv_records', 'startup': 'st_records'}[key]
            if key in keys and (force or not getattr(self, attr, None)):
                jobs.append(key)
        return jobs

    def _ai_fill(self, keys, then, force=False):
        """Eksik baglam verisini okur, sonra then() cagirir."""
        missing = self._ai_missing_jobs(keys, force)
        if not missing:
            then(); return
        if self.busy and not self.in_callback:
            messagebox.showinfo('AI asistan', 'Başka bir işlem sürüyor; bitince yeniden deneyin ya da ilgili sayfada "Yenile"ye basın.'); return
        if 'hw' in missing:
            missing.remove('hw')
            self.hw_scan(then=lambda: self._ai_fill([k for k in keys if k != 'hw'], then))
            return
        setters = {'procs': self._pc_set, 'services': self._sv_set, 'startup': self._st_set}
        jobs = []
        for i, key in enumerate(missing):
            action, _typ = CTX_LIST_JOB[key]
            last = i == len(missing) - 1

            def done(j, k=key, last=last):
                setters[k](j.data)
                if last:
                    then()
            jobs.append(Job('AI için veri: %s' % dict(CTX_TITLES)[key], cmd=ps_cmd(action), on_done=done, show_output=False))
        self.start(jobs, quiet=True)

    def ai_preview(self):
        keys = [k for k, v in self.ai_ctx.items() if v.get()]
        if not keys:
            messagebox.showinfo('Gönderilecek veri', 'Soruya eklenecek veri seçilmedi; yalnız sorunuz gönderilir.'); return

        def show():
            doc = ai.build_document(self._ai_parts(keys), self.ai_mask.get())
            win = tk.Toplevel(self); win.title('Gönderilecek veri (%d karakter)' % len(doc)); win.configure(bg=PANEL)
            win.geometry('%dx%d' % (int(900 * self.scale), int(600 * self.scale)))
            t = tk.Text(win, bg=LOG_BG, fg=LOG_FG, font=('Consolas', 9), wrap='none', padx=8, pady=8)
            t.pack(fill='both', expand=True)
            t.insert('1.0', doc or '(seçilen sayfalarda henüz veri yok)')
            t.configure(state='disabled')
        self._ai_fill(keys, show)

    # ------------------------------------------------------------------ soru/yanıt
    def ai_send(self):
        q = self.ai_q.get('1.0', 'end').strip()
        if not q:
            return
        self.ai_ask(q, [k for k, v in self.ai_ctx.items() if v.get()], clear_input=True)

    def ai_ask(self, question, keys=(), extra=None, clear_input=False):
        """Soruyu gonderir. keys: eklenecek baglam; extra: (baslik, metin) - orn. secili servisler."""
        if self.ai_busy:
            return
        if not self.ai_cfg.get('url'):
            self._goto_ai()
            messagebox.showinfo('AI asistan', 'Önce AI Manager bağlantısını kurun (site adresi + bağlantı anahtarı).'); return
        keys = list(keys)
        for k in keys:
            if k in self.ai_ctx:
                self.ai_ctx[k].set(True)
        if clear_input:
            self.ai_q.delete('1.0', 'end')

        def go():
            doc = ai.build_document(self._ai_parts(keys, extra), self.ai_mask.get())
            q = ai.mask_private(question) if self.ai_mask.get() else question
            self.ai_history.append({'role': 'user', 'content': q})
            attached = [dict(CTX_TITLES)[k] for k in keys if k in dict(CTX_TITLES)] + ([extra[0]] if extra else [])
            self._ai_say('me', 'Siz: ')
            self._ai_say('ai', question + '\n')
            if attached:
                self._ai_say('info', '  (eklenen veri: %s · %d karakter)\n' % (', '.join(attached), len(doc)))
            self.ai_busy = True
            self._ai_update_state()
            hist = list(self.ai_history)
            self._ai_bg(lambda: self._ai_client().chat(hist, doc), self._ai_done)
        self._ai_fill(keys, go)

    def _ai_done(self, ok, res):
        self.ai_busy = False
        self._ai_update_state()
        if not ok:
            self.ai_history.pop() if self.ai_history and self.ai_history[-1]['role'] == 'user' else None
            self._ai_say('err', 'Hata: %s\n' % res)
            return
        res['text'] = ai.clean_reply(res.get('text', ''))
        self.ai_history.append({'role': 'assistant', 'content': res['text']})
        self.ai_history = self.ai_history[-ai.MAX_TURNS:]
        self.ai_result = res
        self._ai_say('me', 'AI: ')
        self._ai_say('ai', res['text'] + '\n')
        meta = ' · '.join(x for x in (res.get('provider'), res.get('model')) if x)
        acts = res.get('actions') or []
        self._ai_say('info', '  (%s%s%s)\n' % (meta or 'AI Manager', ' · yanıt kısaltıldı' if res.get('truncated') else '',
                                              ' · %d uygulanabilir öneri aşağıda' % len(acts) if acts else ''))
        self._ai_show_actions(acts)

    def ai_copy_last(self):
        if not self.ai_result:
            return
        self.clipboard_clear()
        self.clipboard_append(self.ai_result['text'])

    def ai_clear(self):
        self.ai_history, self.ai_result, self.ai_actions = [], None, []
        self.ai_actbox.pack_forget()
        self.ai_text.configure(state='normal'); self.ai_text.delete('1.0', 'end'); self.ai_text.configure(state='disabled')

    # ------------------------------------------------------------------ diğer sayfalardan
    def _goto_ai(self):
        try:
            self.tabs.select('AI asistan')
        except Exception:
            pass

    def ai_ask_about(self, what, records, fields):
        """'AI'ya sor' dugmeleri: secili satirlari AI sayfasina tasir ve soruyu gonderir."""
        if not records:
            messagebox.showinfo('AI asistan', 'Önce listeden en az bir öğe seçin.'); return
        lines = [' | '.join(str(r.get(k) if r.get(k) is not None else '') for k in fields) for r in records[:30]]
        extra = ('Seçili %s' % what, ' | '.join(fields) + '\n' + '\n'.join(lines))
        self._goto_ai()
        self.ai_ask('Seçtiğim %s nedir, güvenilir mi, gerekli mi? Kapatılması/devre dışı bırakılması sorun çıkarır mı? '
                    'Her biri için kısa öneri ver.' % what, (), extra)

    def ai_explain_log(self):
        self._goto_ai()
        self.ai_ask('İşlem günlüğündeki son hata ya da uyarıyı açıkla: ne anlama geliyor, nedeni ne olabilir, nasıl düzeltirim?', ('log',))


def pr_split(recs):
    import care_procs as pr
    return pr.split_by_admin(recs)


def pr_item(rec):
    import care_procs as pr
    return pr.startup_item(rec)


def pr_b64(items):
    import care_procs as pr
    return pr.b64_items(items)


def hw_report_text(app):
    import care_hw as hw
    return hw.report_text(*app._hw_report_parts())


register_palette_module(globals())
