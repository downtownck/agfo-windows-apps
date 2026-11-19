# -*- coding: utf-8 -*-
"""AGFO System Care — Motorlar sayfasi (BleachBit / BCU / SDIO motor durumu ve kurulumu). App sinifinin parcasi (mixin); paylasilan adlar sc_base'den gelir."""
from sc_base import *  # noqa: F401,F403


class EnginesPage:
    # ------------------------------------------------------------------ MOTORLAR
    def _tab_engines(self, f):
        self.label(f, 'Açık kaynak motorlar resmî kaynaklarından kurulur ve AGFO arayüzü içinden çalıştırılır. BleachBit, yönetici yetkisi '
                      'gerektirmeyen resmî taşınabilir paketiyle AGFO motor klasörüne kurulur; BCU ve SDIO için WinGet, olmazsa resmî taşınabilir paket kullanılır. '
                      'Kaynak kodları bu pakete dahil değildir; her motor kendi lisansıyla kurulur.', wraplength=int(1000 * self.scale)).pack(fill='x', padx=16, pady=(12, 6))
        bar = tk.Frame(f, bg=PANEL); bar.pack(fill='x', padx=16)
        self.btn(bar, 'Durumu yenile', self.refresh_engines, 'ghost')
        self.btn(bar, 'Eksik motorları kur', lambda: self.engine_op('install-missing'), 'go')
        self.btn(bar, 'Seçili motoru kur / güncelle', lambda: self.engine_op('install'))
        self.btn(bar, 'Seçili motoru kaldır', lambda: self.engine_op('uninstall'), 'danger')
        self.btn(bar, 'SDIO klasörünü elle seç', self.pick_sdio_dir, 'ghost')
        cols = [('state', 'Durum', 100, 'w'), ('ver', 'Sürüm', 90, 'w'), ('src', 'Kurulum türü', 190, 'w'), ('lic', 'Lisans', 85, 'w'),
                ('role', 'AGFO içindeki görevi', 330, 'w'), ('path', 'Konum', 380, 'w')]
        self.eng_tree = CheckTree(f, cols, first=('Motor', 270), height=6)
        self.eng_tree.pack(fill='both', expand=True, padx=16, pady=10)

    def refresh_engines(self):
        def work(runner, job):
            job.data = [core.engine_status(self.settings)]
            return 0
        self.start([Job('Motor durumu', func=work, on_done=self._engines_done, cancel_ok=False)], quiet=True)

    def _engines_done(self, job):
        if not job.data:
            return
        self.engines = job.data[0]
        t = self.eng_tree
        t.clear()
        wg = self.engines.get('winget', {}).get('path')
        t.add('winget', 'WinGet (Microsoft)', ('Hazır' if wg else 'YOK', '', 'Windows', 'MIT', 'Uygulama güncellemeleri ve yedek motor kurulumu', wg or 'Microsoft Store > Uygulama Yükleyici'),
              checkable=False, tags=() if wg else ('orphan',))
        for key, meta in core.ENGINES.items():
            e = self.engines.get(key, {})
            path = e.get('path') or e.get('console')
            extra = ''
            if key == 'bcu' and e.get('console'):
                extra = '  (+ BCU-console)'
            t.add(key, meta['name'], ('Kurulu' if path else 'Kurulu değil', e.get('version', ''), e.get('source', ''), meta['license'], meta['role'], (path or '—') + extra),
                  tags=() if path else ('risky',), payload=key)
        self._update_engine_dependent()

    def _update_engine_dependent(self):
        bb = bool(self.engines.get('bleachbit', {}).get('path'))
        self.bb_state.set('BleachBit motoru: ' + ('hazır — ' + self.engines['bleachbit']['path'] if bb else 'kurulu değil (Motorlar sekmesinden kurun)'))
        bcu = self.engines.get('bcu', {})
        self.bcu_state.set('BCU motoru: ' + ('hazır' + (' (konsol motoru ile genişletilmiş tarama kullanılabilir)' if bcu.get('console') else '') if (bcu.get('path') or bcu.get('console')) else 'kurulu değil — yerleşik kayıt taraması kullanılıyor'))
        sd = self.engines.get('sdio', {}).get('path')
        self.sdio_state.set('SDIO motoru: ' + ('hazır — ' + sd if sd else 'kurulu değil (Motorlar sekmesinden kurun)'))

    ENGINE_METHODS = {'bleachbit': ('portable', 'winget'), 'bcu': ('winget', 'portable'), 'sdio': ('winget', 'portable')}

    def _engine_present(self, key, st=None):
        e = (st or self.engines).get(key, {})
        return bool(e.get('path') or e.get('console'))

    def install_engine_job(self, key, upgrade=False):
        """Motoru kurar: once tercih edilen yol, olmazsa digeri. BleachBit icin taşınabilir paket (yönetici gerektirmez) önce gelir:
        BleachBit kurulum programi sessiz kipte /allusers ve yonetici yetkisi ister; WinGet sessiz kurulumu bu yuzden dusebilir."""
        name = core.ENGINES[key]['name']
        admin = self.admin

        def work(runner, job):
            errors = []
            for method in self.ENGINE_METHODS[key]:
                if runner.stop.is_set():
                    return -1
                if method == 'portable':
                    runner.say('[%s] Resmî taşınabilir paket deneniyor (yönetici gerekmez)...' % name)
                    try:
                        path = core.install_portable(key, runner.say, runner.progress_cb('İndiriliyor'), runner.stop.is_set)
                        runner.say('[%s] Hazır: %s' % (name, path))
                        return 0
                    except Exception as e:
                        errors.append('taşınabilir: %s' % e)
                        runner.say('[%s] Taşınabilir kurulum olmadı: %s' % (name, e))
                else:
                    wg = core.find_winget()
                    if not wg:
                        errors.append('WinGet yok')
                        runner.say('[%s] WinGet bulunamadı; atlanıyor.' % name)
                        continue
                    cmd = core.winget_install_cmd(wg, core.ENGINES[key]['winget'], upgrade=upgrade and self._engine_present(key))
                    if key == 'bleachbit':
                        cmd += ['--override', '/S /allusers'] if admin else ['--override', '/S /currentuser']
                    code, lines = runner.run_cmd('WinGet: ' + name, cmd)
                    st = core.engine_status(self.settings)
                    already = (code & 0xFFFFFFFF) in (0x8A15002B, 0x8A150061, 0x8A15010D) if isinstance(code, int) else False
                    if self._engine_present(key, st):
                        e = st.get(key, {})
                        runner.say('[%s] %s: %s' % (name, 'Zaten kurulu, kullanılıyor' if already else 'WinGet ile kuruldu', e.get('path') or e.get('console')))
                        return 0
                    if already or code == 0:
                        regs = core.registry_install_dirs({'bleachbit': r'^BleachBit', 'bcu': r'BCUninstaller|Bulk Crap Uninstaller', 'sdio': r'Snappy Driver'}[key])
                        msg = ('WinGet paketi kurulu sayıyor ama çalıştırılabilir dosya bulunamadı' +
                               (' (kayıtlı konum: %s — kurulum yarım kalmış olabilir; Programlar sekmesinden kaldırıp tekrar kurabilirsiniz)' % ', '.join(regs) if regs else
                                ' ve kayıt defterinde kurulum konumu yok (kurulum yarım kalmış olabilir)'))
                    else:
                        msg = core.winget_code_text(code)
                    errors.append('WinGet: %s' % msg)
                    runner.say('[%s] WinGet kurulumu tamamlanamadı (%s).%s' % (name, msg, '' if admin else ' Yönetici olarak açıp tekrar denemek gerekebilir.'))
            runner.say('[%s] KURULAMADI — %s' % (name, ' | '.join(errors)))
            return 2
        return Job(('Güncelle: ' if upgrade else 'Kur: ') + name, func=work, cancel_ok=True)

    def engine_op(self, op):
        if op == 'install-missing':
            keys = [k for k in core.ENGINES if not self._engine_present(k)]
            if not keys:
                messagebox.showinfo('Motorlar', 'Tüm motorlar zaten kurulu.')
                return
        else:
            keys = [p for p in self.eng_tree.checked_payloads() if p] or [i for i in self.eng_tree.tree.selection() if i in core.ENGINES]
            if not keys:
                messagebox.showinfo('Motorlar', 'Önce listeden bir motor işaretleyin.')
                return
        names = ', '.join(core.ENGINES[k]['name'] for k in keys)
        if op == 'uninstall':
            if not messagebox.askyesno('Motoru kaldır', names + ' kaldırılsın mı?'):
                return
            jobs = []
            for k in keys:
                path = self.engines.get(k, {}).get('path') or self.engines.get(k, {}).get('console') or ''
                folder = core.ENGINE_DIR / {'bleachbit': 'BleachBit', 'bcu': 'BCU', 'sdio': 'SDIO'}[k]
                if path and str(folder).lower() in path.lower():
                    def rm(runner, job, folder=folder):
                        import shutil
                        shutil.rmtree(folder, ignore_errors=True)
                        runner.say('Kaldırıldı: %s' % folder)
                        return 0
                    jobs.append(Job('Kaldır: ' + core.ENGINES[k]['name'], func=rm, cancel_ok=False))
                else:
                    wg = core.find_winget()
                    if wg:
                        jobs.append(Job('Kaldır: ' + core.ENGINES[k]['name'], cmd=core.winget_uninstall_cmd(wg, core.ENGINES[k]['winget']), cancel_ok=False))
        else:
            if not messagebox.askyesno('Motor kurulumu', names + '\n\nMotorlar resmî kaynaklarından kurulur: BleachBit için resmî taşınabilir paket '
                                       '(yönetici gerekmez), diğerleri için WinGet; olmazsa diğer yol denenir. Devam edilsin mi?'):
                return
            jobs = [self.install_engine_job(k, upgrade=(op == 'install' and self._engine_present(k))) for k in keys]
        if not jobs:
            return
        jobs[-1].on_done = lambda j: self.refresh_engines()
        self.start(jobs)

    def pick_sdio_dir(self):
        d = filedialog.askdirectory(title='SDIO klasörünü seçin (SDIO_x64_R*.exe bulunan klasör)')
        if not d:
            return
        self.settings['sdio_dir'] = d
        core.save_settings(self.settings)
        self.refresh_engines()


register_palette_module(globals())
