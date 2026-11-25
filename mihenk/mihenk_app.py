# -*- coding: utf-8 -*-
"""AGFO Mihenk - ana pencere, kenar cubugu ve ayarlar ekrani."""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import mihenk_core as core
import mihenk_db as db
import mihenk_scheduler as scheduler
import mihenk_seed as seed
import mihenk_store as store
import mihenk_theme as theme
import mihenk_validate as v
import mihenk_widgets as w
from mihenk_repo import AssetRepo, CalibrationRepo, ImpactRepo, WorkOrderRepo
from mihenk_screens import (AssetsScreen, CalibrationsScreen, DashboardScreen, ImpactsScreen,
                            PartsScreen, PlansScreen, ReportsScreen, RequestsScreen, Screen,
                            WorkOrdersScreen)

NAV = (
    ('dashboard', 'Pano'),
    ('assets', 'Varlıklar'),
    ('plans', 'Planlar'),
    ('requests', 'Talepler'),
    ('work_orders', 'İş emirleri'),
    ('calibrations', 'Kalibrasyon'),
    ('impacts', 'Etki değerlendirmeleri'),
    ('parts', 'Yedek parçalar'),
    ('reports', 'Raporlar'),
    ('settings', 'Ayarlar'),
)

# Acik duran uygulamanin yeni surumu ne siklikta yoklayacagi. Agi yoran sey bu
# degil: mihenk_update.CHECK_INTERVAL (6 saat) gercek istegi zaten sinirliyor.
UPDATE_POLL_MS = 60 * 60 * 1000

VERSIONS = (
    {'version': '2.1.0', 'date': '2026-11-25', 'kind': 'MINOR',
     'summary': 'Açık duran uygulama da yeni sürümü görüyor: güncelleme denetimi artık yalnızca '
                'açılışta değil, çalışırken de periyodik olarak yapılıyor. 2.0.0 ve öncesinde '
                'uygulamayı kapatıp açmadan yeni sürüm fark edilmiyordu.'},
    {'version': '2.0.0', 'date': '2026-11-25', 'kind': 'MAJOR',
     'summary': 'Modern görünüm (ttkbootstrap) ve dört yeni yetenek: plana bağlı kontrol listesi '
                'şablonları ve iş emrinde işaretleme, yedek parça kütüğü ile stok hareketleri, '
                'plan uyumu / MTBF / MTTR / duruş eğilimi / sapma geçmişi göstergeleri, '
                've denetime hazır çıktı (Excel, CSV, yazdırılabilir rapor, veri klasöründe '
                'saklanan sertifika dosyaları).'},
    {'version': '1.1.0', 'date': '2026-11-25', 'kind': 'MINOR',
     'summary': 'İlk açılışta demo veri ya da boş başlangıç soran karşılama penceresi, boş '
                'listelerde yönlendirme ve açılışta sessiz güncelleme denetimi.'},
    {'version': '1.0.0', 'date': '2026-11-25', 'kind': 'MAJOR',
     'summary': 'İlk sürüm. Hiyerarşik varlık kütüğü ve tipe göre özellikler, önleyici bakım ile '
                'kalibrasyon ve doğrulamayı tek tabloda toplayan plan yapısı, talep ve iş emri '
                'akışları, ölçüm noktası tablosundan tolerans değerlendirmesi, uygunsuz sonuçta '
                'otomatik karantina ve etki değerlendirmesi, niyet ve sonuç çiftiyle denetim '
                'günlüğü, SQLite yedekleme ve demo veri seti.'},
)


class SettingsScreen(Screen):
    """Ayarlar, veri bakimi, demo veri ve surum."""

    title = 'Ayarlar'

    def build(self) -> None:
        area = w.ScrollArea(self.body)
        area.pack(fill='both', expand=True)
        host = area.body

        form = w.FormGrid(host)
        form.pack(fill='x', pady=(0, 10))
        values = store.load_settings()

        self.operator = form.add('Operatör adı', ttk.Entry(form, width=32),
                                 'Denetim günlüğüne bu ad yazılır.')
        self.operator.insert(0, values['operator'])
        self.lead_days = form.add('Varsayılan ön uyarı günü', ttk.Entry(form, width=8))
        self.lead_days.insert(0, str(values['default_lead_days']))
        self.date_format = form.add('Tarih biçimi', ttk.Entry(form, width=16),
                                    'Python biçimi, örneğin %Y-%m-%d ya da %d.%m.%Y')
        self.date_format.insert(0, values['date_format'])
        self.theme_choice = form.add('Tema', w.Combo(form, [('light', 'Açık'), ('dark', 'Koyu')],
                                                     width=16, value=values['theme']))
        self.scan_on_start = tk.BooleanVar(value=bool(values['scan_on_start']))
        form.add('Açılışta tarama',
                 ttk.Checkbutton(form, text='Uygulama açılırken vadesi gelen kayıtları üret',
                                 variable=self.scan_on_start))
        self.modern_ui = tk.BooleanVar(value=bool(values['modern_ui']))
        form.add('Modern görünüm',
                 ttk.Checkbutton(form, text='ttkbootstrap çizimini kullan (varsa)',
                                 variable=self.modern_ui))
        self.ui_status = ttk.Label(form, text='', style='Muted.TLabel', wraplength=520,
                                   justify='left')
        form.add_full(self.ui_status)
        self.install_ui = ttk.Button(form, text='Modern görünümü kur',
                                     command=self.install_modern_ui)
        form.add_full(self.install_ui)
        ttk.Button(host, text='Ayarları kaydet', style='Accent.TButton',
                   command=self.save).pack(anchor='w', pady=(0, 16))

        ttk.Separator(host).pack(fill='x', pady=8)
        ttk.Label(host, text='Veri', style='Heading.TLabel').pack(anchor='w', pady=(6, 4))
        self.path_label = ttk.Label(host, text='', style='Muted.TLabel')
        self.path_label.pack(anchor='w')
        bar = ttk.Frame(host)
        bar.pack(anchor='w', pady=(8, 4))
        ttk.Button(bar, text='Klasörü aç', command=self.open_folder).pack(side='left')
        ttk.Button(bar, text='Yedek al', command=self.backup).pack(side='left', padx=6)
        ttk.Button(bar, text='Yedeği geri yükle', command=self.restore).pack(side='left')
        self.health = ttk.Label(host, text='', style='Muted.TLabel', justify='left')
        self.health.pack(anchor='w', pady=(8, 0))

        ttk.Separator(host).pack(fill='x', pady=12)
        ttk.Label(host, text='Demo veri', style='Heading.TLabel').pack(anchor='w', pady=(4, 2))
        ttk.Label(host, text='Birbirine bağlı örnek bir set kurar: sekiz varlık, yedi plan, dört '
                             'talep, iş emirleri ve biri uygunsuz üç kalibrasyon kaydı. Temizlik '
                             'yalnızca kodu DEMO- ile başlayan varlıkları ve onlara bağlı '
                             'kayıtları siler.',
                  style='Muted.TLabel', wraplength=700, justify='left').pack(anchor='w')
        demo_bar = ttk.Frame(host)
        demo_bar.pack(anchor='w', pady=(8, 0))
        self.seed_button = ttk.Button(demo_bar, text='Demo veriyi kur', command=self.seed_demo)
        self.seed_button.pack(side='left')
        ttk.Button(demo_bar, text='Demo veriyi temizle', style='Danger.TButton',
                   command=self.purge_demo).pack(side='left', padx=6)

        ttk.Separator(host).pack(fill='x', pady=12)
        ttk.Label(host, text='Sürüm', style='Heading.TLabel').pack(anchor='w', pady=(4, 2))
        self.update_label = ttk.Label(host, text='', style='Muted.TLabel')
        self.update_label.pack(anchor='w')
        ttk.Button(host, text='Güncellemeleri denetle', command=self.check_updates).pack(
            anchor='w', pady=(6, 10))

        for entry in VERSIONS:
            card = ttk.Frame(host, style='Card.TFrame', padding=(14, 12))
            card.pack(fill='x', pady=4)
            head = ttk.Frame(card, style='Surface.TFrame')
            head.pack(fill='x')
            ttk.Label(head, text=entry['version'], style='SurfaceHeading.TLabel').pack(side='left')
            w.Badge(head, entry['kind'], 'in_progress').pack(side='left', padx=8)
            ttk.Label(head, text=entry['date'], style='SurfaceMuted.TLabel').pack(side='right')
            ttk.Label(card, text=entry['summary'], style='SurfaceMuted.TLabel',
                      wraplength=720, justify='left').pack(anchor='w', pady=(6, 0))

        ttk.Label(host, text='Mihenk v%s · AGFO' % core.VERSION,
                  style='Footer.TLabel').pack(anchor='w', pady=(18, 10))

    def refresh(self) -> None:
        self.path_label.configure(text=str(store.data_dir()))
        counts = db.counts(self.app.conn)
        self.health.configure(text='Kayıtlar: %d varlık · %d plan · %d talep · %d iş emri · '
                                   '%d kalibrasyon · %d etki · %d günlük satırı'
                                   % (counts['asset'], counts['schedule'], counts['request'],
                                      counts['work_order'], counts['calibration'],
                                      counts['impact'], counts['log']))
        self.seed_button.configure(state='disabled' if seed.exists(self.app.conn) else 'normal')
        self.update_label.configure(text='Kurulu sürüm: %s' % core.VERSION)
        self.ui_status.configure(
            text='Çizim: %s — %s. Bileşen yoksa uygulama klasik çizimle sorunsuz çalışır; '
                 'renkler iki yolda da aynıdır.'
                 % ('modern' if theme.engine() == 'ttkbootstrap' else 'klasik',
                    theme.engine_status()))
        can_install = (theme.engine() != 'ttkbootstrap' and not getattr(sys, 'frozen', False)
                       and theme.python_ok())
        self.install_ui.configure(state='normal' if can_install else 'disabled')

    # ------------------------------------------------------------------ islemler
    def save(self) -> None:
        store.save_settings({
            'operator': self.operator.get().strip(),
            'default_lead_days': v.integer(self.lead_days.get(), 0, None, 14),
            'date_format': self.date_format.get().strip() or '%Y-%m-%d',
            'theme': self.theme_choice.key(),
            'scan_on_start': self.scan_on_start.get(),
            'modern_ui': self.modern_ui.get(),
        })
        self.app.apply_theme()
        self.app.refresh()
        self.app.toast('Ayarlar kaydedildi.')

    def install_modern_ui(self) -> None:
        """ttkbootstrap'i uygulamanin kendi klasorune kurar; Python kurulumuna dokunmaz."""
        self.ui_status.configure(text='Modern görünüm bileşeni kuruluyor…')
        self.install_ui.configure(state='disabled')
        target = store.ui_lib_dir()

        def worker():
            command = theme.pip_install_cmd(theme.console_python(), target)
            try:
                done = subprocess.run(command, capture_output=True, text=True, timeout=300)
                message = ('Kuruldu. Değişiklik için uygulamayı yeniden açın.'
                           if done.returncode == 0
                           else 'Kurulamadı: %s' % (done.stderr or done.stdout or '')[-300:])
            except Exception as exc:
                message = 'Kurulamadı: %s' % exc
            try:
                self.after(0, lambda: self.ui_status.configure(text=message))
            except tk.TclError:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def open_folder(self) -> None:
        path = str(store.data_dir())
        try:
            if sys.platform == 'win32':
                os.startfile(path)                                  # noqa: S606
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', path])
            else:
                subprocess.Popen(['xdg-open', path])
        except Exception as exc:
            messagebox.showinfo('Klasör', '%s\n\n(%s)' % (path, exc), parent=self)

    def backup(self) -> None:
        default = 'mihenk-yedek-%s.sqlite3' % v.parse(v.now()).strftime('%Y%m%d-%H%M')
        target = filedialog.asksaveasfilename(
            parent=self, title='Yedek al', initialfile=default,
            initialdir=str(store.backups_dir()), defaultextension='.sqlite3',
            filetypes=[('Mihenk yedeği', '*.sqlite3')])
        if not target:
            return
        try:
            db.backup(self.app.conn, target)
        except Exception as exc:
            messagebox.showerror('Yedek alınamadı', str(exc), parent=self)
            return
        self.app.toast('Yedek alındı: %s' % pathlib.Path(target).name)

    def restore(self) -> None:
        source = filedialog.askopenfilename(parent=self, title='Yedeği geri yükle',
                                            initialdir=str(store.backups_dir()),
                                            filetypes=[('Mihenk yedeği', '*.sqlite3'),
                                                       ('Tüm dosyalar', '*.*')])
        if not source:
            return
        if not messagebox.askyesno(
                'Onay', 'Mevcut kayıtların yerine bu yedek konacak.\n\nŞu anki veritabanının bir '
                        'kopyası .pre-restore uzantısıyla yanında bırakılır. Devam edilsin mi?',
                parent=self):
            return
        try:
            self.app.restore_from(source)
        except Exception as exc:
            messagebox.showerror('Geri yüklenemedi', str(exc), parent=self)
            return
        self.app.refresh()
        self.app.toast('Yedek geri yüklendi.')

    def seed_demo(self) -> None:
        report = {}

        def run():
            report.update(seed.seed(self.app.conn))
        if not self.run(run, ''):
            return
        self.app.refresh()
        if report.get('ok'):
            messagebox.showinfo('Demo veri kuruldu', '\n\n'.join(report['lines']), parent=self)
        else:
            messagebox.showinfo('Demo veri', '\n'.join(report.get('lines', [])), parent=self)

    def purge_demo(self) -> None:
        if not messagebox.askyesno('Onay', 'Kodu DEMO- ile başlayan bütün varlıklar ve onlara '
                                           'bağlı kayıtlar silinsin mi?', parent=self):
            return
        report = {}

        def run():
            report.update(seed.purge(self.app.conn))
        if not self.run(run, ''):
            return
        self.app.refresh()
        messagebox.showinfo('Demo veri', '\n'.join(report.get('lines', [])), parent=self)

    def check_updates(self) -> None:
        """Elle denetim. Isi uygulama kabugu yapar, ekran yalnizca sonucu yazar."""
        self.update_label.configure(text='Denetleniyor…')
        self.app.check_updates(force=True, on_result=self._update_result)

    def _update_result(self, result: dict) -> None:
        status = result.get('status')
        if status == 'update':
            self.update_label.configure(
                text='Yeni sürüm var: v%s — durum çubuğundaki Güncelle düğmesiyle kurulur.'
                     % result.get('version'))
        elif status == 'current':
            self.update_label.configure(text='Kurulu sürüm güncel: %s' % core.VERSION)
        else:
            self.update_label.configure(text='Denetlenemedi: %s'
                                             % result.get('message', 'bilinmeyen hata'))


SCREENS = {
    'dashboard': DashboardScreen,
    'assets': AssetsScreen,
    'plans': PlansScreen,
    'requests': RequestsScreen,
    'work_orders': WorkOrdersScreen,
    'calibrations': CalibrationsScreen,
    'impacts': ImpactsScreen,
    'parts': PartsScreen,
    'reports': ReportsScreen,
    'settings': SettingsScreen,
}


class MihenkApp:
    """Pencere kabugu: kenar cubugu, ekranlar ve durum serigi."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings = store.load_settings()
        self.conn = db.connect(store.db_path())
        self.screens = {}
        self.current = None
        self._toast_job = None
        self._update_poll = None

        theme.apply(root, self.settings['theme'], store.ui_lib_dir(),
                    self.settings.get('modern_ui', True))
        root.title('%s %s' % (core.APP_NAME, core.VERSION))
        self._set_icon()
        root.minsize(1060, 680)
        self._restore_geometry()
        root.protocol('WM_DELETE_WINDOW', self.close)

        container = ttk.Frame(root)
        container.pack(fill='both', expand=True)

        self.sidebar = ttk.Frame(container, style='Sidebar.TFrame', width=214)
        self.sidebar.pack(side='left', fill='y')
        self.sidebar.pack_propagate(False)
        self._build_sidebar()

        right = ttk.Frame(container)
        right.pack(side='left', fill='both', expand=True)
        self.content = ttk.Frame(right)
        self.content.pack(fill='both', expand=True)

        status = ttk.Frame(right, style='Status.TFrame', padding=(16, 7))
        status.pack(fill='x')
        self.status_label = ttk.Label(status, text='', style='Status.TLabel')
        self.status_label.pack(side='left')
        self.counts_label = ttk.Label(status, text='', style='Status.TLabel')
        self.counts_label.pack(side='right')
        # Guncelleme bulununca gorunur; bulunmadikca yer kaplamaz.
        self.update_button = ttk.Button(status, text='', style='Accent.TButton',
                                        command=self.install_pending_update)
        self.pending_update = None

        for name, cls in SCREENS.items():
            screen = cls(self.content, self)
            self.screens[name] = screen

        self.go(self.settings.get('last_screen') or 'dashboard')
        self.root.after(200, self._startup_scan)
        self.root.after(400, self._first_run)
        self.root.after(2500, lambda: self.check_updates(force=False))
        self._schedule_update_poll()

    # ------------------------------------------------------------------ kabuk
    def _set_icon(self) -> None:
        path = pathlib.Path(__file__).resolve().parent / 'assets' / 'agfo-mihenk.ico'
        if sys.platform == 'win32' and path.exists():
            try:
                self.root.iconbitmap(default=str(path))
            except tk.TclError:
                pass

    def _restore_geometry(self) -> None:
        saved = str(self.settings.get('window') or '')
        if saved and saved.count('+') >= 1 and 'x' in saved:
            try:
                self.root.geometry(saved)
                return
            except tk.TclError:
                pass
        self.root.geometry('1240x780')

    def _build_sidebar(self) -> None:
        for child in self.sidebar.winfo_children():
            child.destroy()
        brand = ttk.Frame(self.sidebar, style='Sidebar.TFrame', padding=(18, 20, 18, 16))
        brand.pack(fill='x')
        ttk.Label(brand, text='Mihenk', style='SidebarBrand.TLabel').pack(anchor='w')
        ttk.Label(brand, text='Ekipman bakımı ve kalibrasyon', style='SidebarVersion.TLabel',
                  wraplength=170, justify='left').pack(anchor='w', pady=(2, 0))

        self.nav_buttons = {}
        for name, label in NAV:
            button = ttk.Button(self.sidebar, text=label, style='Nav.TButton',
                                command=lambda n=name: self.go(n))
            button.pack(fill='x')
            self.nav_buttons[name] = button

        footer = ttk.Frame(self.sidebar, style='Sidebar.TFrame', padding=(18, 10))
        footer.pack(side='bottom', fill='x')
        ttk.Label(footer, text='v%s' % core.VERSION, style='SidebarVersion.TLabel').pack(anchor='w')

    def go(self, name: str) -> None:
        """Ekran degistirir."""
        if name not in self.screens:
            name = 'dashboard'
        if self.current:
            self.screens[self.current].pack_forget()
        self.current = name
        for key, button in self.nav_buttons.items():
            button.configure(style='NavActive.TButton' if key == name else 'Nav.TButton')
        screen = self.screens[name]
        screen.pack(fill='both', expand=True)
        screen.refresh()
        store.save_settings({'last_screen': name})

    def refresh(self) -> None:
        """Acik ekrani ve durum serigini tazeler."""
        if self.current:
            self.screens[self.current].refresh()
        open_impacts = ImpactRepo.count(self.conn, 'open')
        parts = ['%d varlık' % AssetRepo.count(self.conn),
                 '%d açık iş emri' % WorkOrderRepo.count(self.conn, open_only=True),
                 '%d açık kalibrasyon' % CalibrationRepo.count(self.conn, open_only=True)]
        if open_impacts:
            parts.append('%d açık etki' % open_impacts)
        self.counts_label.configure(text='  ·  '.join(parts))

    def toast(self, message: str) -> None:
        """Durum serigine gecici bir not yazar."""
        self.status_label.configure(text=message)
        if self._toast_job:
            self.root.after_cancel(self._toast_job)
        self._toast_job = self.root.after(8000, lambda: self.status_label.configure(text=''))

    def run(self, action, success: str = '') -> bool:
        """Depo cagrisini calistirir, reddi anlasilir bicimde gosterir."""
        try:
            action()
        except v.MihenkError as exc:
            messagebox.showwarning('Kabul edilmedi', str(exc), parent=self.root)
            return False
        except Exception as exc:
            messagebox.showerror('Hata', str(exc), parent=self.root)
            return False
        if success:
            self.toast(success)
        return True

    def apply_theme(self) -> None:
        """Tema degisince butun bicemleri ve tablolari yeniler."""
        self.settings = store.load_settings()
        theme.apply(self.root, self.settings['theme'], store.ui_lib_dir(),
                    self.settings.get('modern_ui', True))
        self._build_sidebar()
        for name, screen in self.screens.items():
            for child in screen.winfo_children():
                _refresh_tables(child)
            if name == self.current:
                self.nav_buttons[name].configure(style='NavActive.TButton')

    def restore_from(self, source) -> None:
        """Yedegi geri yukler ve baglantiyi yeniden acar."""
        path = store.db_path()
        db.restore(self.conn, source, path)
        self.conn = db.connect(path)
        for screen in self.screens.values():
            screen.conn = self.conn

    def _startup_scan(self) -> None:
        if not self.settings.get('scan_on_start'):
            self.refresh()
            return
        try:
            made = scheduler.scan(self.conn)
        except Exception as exc:
            self.toast('Açılış taraması yapılamadı: %s' % exc)
            self.refresh()
            return
        self.refresh()
        total = made['work_orders'] + made['calibrations']
        if total:
            self.toast('Açılış taraması: %d iş emri, %d kalibrasyon kaydı üretildi.'
                       % (made['work_orders'], made['calibrations']))

    # ------------------------------------------------------------------ guncelleme
    def _schedule_update_poll(self) -> None:
        """Acik duran uygulama da yeni surumu gorsun.

        Yalnizca acilista bakmak yetmiyor: uygulama gun boyu acik kalirsa
        aradan cikan surumu hic fark etmiyor. Saatte bir yoklaniyor; modulun
        kendi alti saatlik araligi yururlukte oldugu icin aga gercekte alti
        saatte bir cikiliyor.
        """
        self._update_poll = self.root.after(UPDATE_POLL_MS, self._poll_updates)

    def _poll_updates(self) -> None:
        if self.pending_update is None:          # zaten bulduysak tekrar sormaya gerek yok
            self.check_updates(force=False)
        self._schedule_update_poll()

    def check_updates(self, force=False, on_result=None) -> None:
        """GitHub Releases'i arka planda denetler; arayuzu bloke etmez.

        force=False acilista calisir ve modulun kendi araligina (6 saat) uyar,
        yani her acilista ag istegi yapilmaz.
        """
        def worker():
            try:
                import mihenk_update as updater
                result = updater.check(force=force)
            except Exception as exc:
                result = {'status': 'error', 'message': str(exc)}
            try:
                self.root.after(0, lambda: self._update_checked(result, on_result))
            except tk.TclError:
                pass                     # pencere bu arada kapandiysa sessizce birak

        threading.Thread(target=worker, daemon=True).start()

    def _update_checked(self, result: dict, on_result=None) -> None:
        if result.get('status') == 'update':
            self.pending_update = result
            self.update_button.configure(text='Güncelle: v%s' % result.get('version'))
            if not self.update_button.winfo_manager():
                self.update_button.pack(side='right', padx=(0, 14))
            self.toast('Yeni sürüm yayınlandı: v%s' % result.get('version'))
        if on_result:
            on_result(result)

    def install_pending_update(self) -> None:
        """Durum serigindeki Guncelle dugmesi: indirir ve kurar."""
        result = self.pending_update
        if not result:
            return
        if not messagebox.askyesno('Güncelleme', 'v%s indirilip kurulsun mu?\n\nKayıtlarınıza '
                                                 'dokunulmaz.' % result.get('version'),
                                   parent=self.root):
            return
        self.update_button.configure(state='disabled', text='İndiriliyor…')

        def worker():
            try:
                import mihenk_update as updater
                path = updater.download(result)
                if updater.is_frozen():
                    updater.apply_update(path)
                    message = 'Yeni sürüm uygulanıyor, uygulama birazdan yeniden açılacak.'
                else:
                    folder = updater.extract(path)
                    updater.run_installer(folder)
                    message = 'Kurulum penceresi açıldı.'
            except Exception as exc:
                message = 'Güncelleme uygulanamadı: %s' % exc
            try:
                self.root.after(0, lambda: self._install_finished(message))
            except tk.TclError:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _install_finished(self, message: str) -> None:
        self.update_button.configure(state='normal',
                                     text='Güncelle: v%s' % (self.pending_update or {}).get('version', ''))
        self.toast(message)

    def should_offer_first_run(self) -> bool:
        """Karsilama penceresi gosterilmeli mi: daha once sorulmamis ve kutuk bos."""
        if store.setting('first_run_done'):
            return False
        if AssetRepo.count(self.conn) > 0:
            store.save_settings({'first_run_done': True})      # dolu kutuga bir daha sorma
            return False
        return True

    def _first_run(self) -> None:
        """Kutuk bosken ve daha once sorulmamissa karsilama penceresini acar."""
        if not self.should_offer_first_run():
            return
        self.go('dashboard')
        from mihenk_dialogs import WelcomeDialog
        dialog = WelcomeDialog(self)
        self.root.wait_window(dialog)
        self.settings = store.load_settings()
        if dialog.choice == 'demo':
            self.toast('Demo veri kuruldu. Ayarlar ekranından tek tıkla temizlenir.')
        self.refresh()

    def close(self) -> None:
        try:
            if self._update_poll:
                self.root.after_cancel(self._update_poll)
        except Exception:
            pass
        try:
            store.save_settings({'window': self.root.winfo_geometry()})
            self.conn.close()
        except Exception:
            pass
        self.root.destroy()


def _refresh_tables(widget) -> None:
    """Tema degisiminden sonra tablolarin satir renklerini tazeler."""
    if isinstance(widget, w.DataTable):
        widget.refresh_tags()
    for child in widget.winfo_children():
        _refresh_tables(child)


def main() -> int:
    theme.enable_dpi_awareness()
    root = tk.Tk()
    app = MihenkApp(root)
    if '--minimized' in sys.argv:
        root.iconify()
    root.mainloop()
    del app
    return 0


if __name__ == '__main__':
    sys.exit(main())
