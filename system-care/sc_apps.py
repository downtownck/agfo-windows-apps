# -*- coding: utf-8 -*-
"""AGFO System Care — Uygulama guncellemeleri sayfasi (WinGet). App sinifinin parcasi (mixin); paylasilan adlar sc_base'den gelir."""
from sc_base import *  # noqa: F401,F403


class AppsPage:
    # ------------------------------------------------------------------ UYGULAMA GUNCELLEMELERI (WinGet)
    def _tab_apps(self, f):
        self.label(f, 'WinGet resmî deposundaki güncellemeler bu listede gösterilir; yalnızca işaretledikleriniz sırayla güncellenir. Sessiz güncelleme '
                      'başarısız olursa uygulamanın kendi kurulum penceresiyle bir kez daha denenir; yeni sürümü farklı kurulum türüyle gelenler için '
                      '"kaldırıp yeniden kur" önerilir. Güncellenecek uygulamaları kapatmanız önerilir.',
                   wraplength=int(1100 * self.scale)).pack(fill='x', padx=16, pady=(12, 4))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Güncellemeleri tara', self.apps_scan, 'ghost')
        self.btn(bar, 'Tümünü seç', lambda: self.app_tree.set_all(True), 'ghost', action=False)
        self.btn(bar, 'Seçimi kaldır', lambda: self.app_tree.set_all(False), 'ghost', action=False)
        self.btn(bar, 'Seçilenleri güncelle', self.apps_update, 'danger')
        self.apps_reinstall_btn = self.btn(bar, 'Kaldırıp yeniden kur', self.apps_reinstall, 'ghost')
        self.app_count = tk.StringVar(value='')
        tk.Label(bar, textvariable=self.app_count, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).pack(side='right')
        cols = [('id', 'Paket kimliği', 240, 'w'), ('ver', 'Kurulu', 110, 'w'), ('avail', 'Yeni', 110, 'w'), ('state', 'Durum', 150, 'w'),
                ('why', 'Ayrıntı', 420, 'w')]
        self.app_tree = CheckTree(f, cols, first=('Uygulama', 300), on_change=lambda: self.app_count.set('%d seçili' % len(self.app_tree.checked)))
        self.app_tree.pack(fill='both', expand=True, padx=16, pady=8)
        self.app_reinstall = {}

    def apps_scan(self):
        wg = self.engines.get('winget', {}).get('path') or core.find_winget()
        if not wg:
            messagebox.showerror('WinGet yok', 'WinGet bulunamadı.'); return
        cmd = [wg, 'upgrade', '--source', 'winget', '--accept-source-agreements', '--disable-interactivity']
        self.start([Job('WinGet güncelleme taraması', cmd=cmd, on_done=self._apps_loaded, show_output=False)])

    def _apps_loaded(self, job):
        rows = core.parse_winget_table(job.lines)
        t = self.app_tree; t.clear()
        self.app_reinstall = {}
        for i, r in enumerate(rows):
            t.add('a%d' % i, r['name'], (r['id'], r.get('version', ''), r.get('available', ''), '', ''), checked=True, payload=r)
        t._changed()
        self.write('WinGet: %d güncellenebilir uygulama.\n' % len(rows))
        if not rows:
            tail = [l for l in job.lines if l.strip()][-3:]
            if tail:
                self.write('\n'.join(tail) + '\n')

    def _app_row(self, pid):
        for iid, pl in self.app_tree.payload.items():
            if pl and pl.get('id') == pid:
                return iid
        return None

    def _app_set(self, pid, state, why=''):
        iid = self._app_row(pid)
        if iid and self.app_tree.tree.exists(iid):
            self.app_tree.tree.set(iid, 'state', state)
            self.app_tree.tree.set(iid, 'why', why)
            self.app_tree.tree.item(iid, tags=(('st_new',) if state in ('Güncellendi', 'Zaten güncel olabilir') else ('st_warn',) if state != 'Başarısız' else ('orphan',)))

    def apps_update(self):
        wg = self.engines.get('winget', {}).get('path') or core.find_winget()
        sel = [p for p in self.app_tree.checked_payloads() if p]
        if not wg or not sel:
            messagebox.showinfo('Güncelleme', 'Önce tarayın ve güncellenecek uygulamaları işaretleyin.'); return
        if not messagebox.askyesno('Güncellemeyi onaylayın', '%d uygulama sırayla güncellenecek. Açık olan uygulamaları kapatmanız önerilir; '
                                   'sessiz güncelleme olmazsa uygulamanın kendi kurulum penceresi açılabilir. Devam?' % len(sel)):
            return
        jobs = []
        for r in sel:
            def work(runner, job, r=r):
                code, lines = runner.run_cmd('WinGet (sessiz): ' + r['name'], core.winget_upgrade_cmd(wg, r['id']))
                step = core.upgrade_next_step(code, lines, False)
                if step == 'interactive' and not runner.stop.is_set():
                    runner.say('[%s] Sessiz güncelleme olmadı (%s); kurulum penceresiyle tekrar deneniyor...' % (r['name'], core.winget_failure_reason(code, lines)))
                    code, lines = runner.run_cmd('WinGet (pencereli): ' + r['name'], core.winget_upgrade_cmd(wg, r['id'], interactive=True))
                    step = core.upgrade_next_step(code, lines, True)
                job.data = [(step, core.winget_failure_reason(code, lines))]
                return 0 if step in ('ok', 'uptodate') else (code or 1)

            def done(job, r=r):
                step, why = job.data[0] if job.data else ('fail', hint(job.code))
                state = {'ok': 'Güncellendi', 'uptodate': 'Zaten güncel olabilir', 'running': 'Uygulama açık', 'reinstall': 'Yeniden kurulmalı'}.get(step, 'Başarısız')
                self._app_set(r['id'], state, '' if step == 'ok' else why)
                if step == 'reinstall':
                    self.app_reinstall[r['id']] = r
                if step == 'running':
                    self.write('[%s] Uygulama açık olduğu için güncellenemedi; kapatıp tekrar deneyin.\n' % r['name'])
            jobs.append(Job('Güncelle: ' + r['name'], func=work, on_done=done, cancel_ok=True))

        def summary(job):
            if self.app_reinstall:
                names = ', '.join(v['name'] for v in self.app_reinstall.values())
                self.write('Kaldırıp yeniden kurulması gerekenler: %s — "Kaldırıp yeniden kur" düğmesini kullanabilirsiniz.\n' % names)
        jobs.append(Job('Güncelleme özeti', func=lambda runner, job: 0, on_done=summary, cancel_ok=False, show_output=False))
        self.start(jobs)

    def apps_reinstall(self):
        wg = self.engines.get('winget', {}).get('path') or core.find_winget()
        sel = [p for p in self.app_tree.checked_payloads() if p and p['id'] in self.app_reinstall] or list(self.app_reinstall.values())
        if not wg or not sel:
            messagebox.showinfo('Kaldırıp yeniden kur', 'Bu işlem yalnızca güncellemede "Yeniden kurulmalı" diye işaretlenen uygulamalar içindir.'); return
        if not messagebox.askyesno('Kaldırıp yeniden kur', 'Şu uygulamalar kaldırılıp en yeni sürümleri kurulacak:\n  %s\n\n'
                                   'Çoğu uygulama ayarlarını korur, ancak bazıları ayarlarını sıfırlayabilir. Devam?' % '\n  '.join(p['name'] for p in sel)):
            return
        jobs = []
        for r in sel:
            def work(runner, job, r=r):
                code, lines = runner.run_cmd('Kaldır (sessiz): ' + r['name'], core.winget_uninstall_cmd(wg, r['id']))
                if code != 0 and not runner.stop.is_set():
                    runner.say('[%s] Sessiz kaldırma olmadı (%s); kaldırıcının kendi penceresiyle deneniyor...' % (r['name'], core.winget_failure_reason(code, lines)))
                    code, lines = runner.run_cmd('Kaldır (pencereli): ' + r['name'], core.winget_uninstall_cmd(wg, r['id'], interactive=True))
                if code == 0:
                    code, lines = runner.run_cmd('Kur: ' + r['name'], core.winget_install_cmd(wg, r['id']))
                    job.data = [('ok' if code == 0 else 'fail', '' if code == 0 else 'kurulamadı: ' + core.winget_failure_reason(code, lines))]
                    return code
                why_un = core.winget_failure_reason(code, lines)
                runner.say('[%s] Eski sürüm kaldırılamadı (%s); en yeni sürüm üzerine kurulmaya çalışılıyor...' % (r['name'], why_un))
                code, lines = runner.run_cmd('Üzerine kur: ' + r['name'], core.winget_force_install_cmd(wg, r['id']))
                if code == 0:
                    job.data = [('ok', 'eski sürüm kaldırılamadı, yeni sürüm üzerine kuruldu; Programlar\'da iki kayıt görünürse eskisini oradan kaldırın')]
                    return 0
                adm = '' if self.admin else ' — uygulamayı "Yönetici olarak yeniden aç" ile açıp tekrar deneyin'
                job.data = [('fail', 'kaldırılamadı (%s), üzerine de kurulamadı (%s)%s' % (why_un, core.winget_failure_reason(code, lines), adm))]
                return code or 1

            def done(job, r=r):
                step, why = job.data[0] if job.data else ('fail', hint(job.code))
                self._app_set(r['id'], 'Güncellendi' if step == 'ok' else 'Başarısız', why)
                if step == 'ok':
                    self.app_reinstall.pop(r['id'], None)
            jobs.append(Job('Yeniden kur: ' + r['name'], func=work, on_done=done, cancel_ok=False))
        self.start(jobs)


register_palette_module(globals())
