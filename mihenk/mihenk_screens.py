# -*- coding: utf-8 -*-
"""Ana ekranlar: pano, varliklar, planlar, talepler, is emirleri, kalibrasyon, etki."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import mihenk_scheduler as scheduler
import mihenk_states as states
import mihenk_theme as theme
import mihenk_validate as v
import mihenk_widgets as w
from mihenk_dialogs import (AssetDialog, CalibrationDialog, ImpactDialog, PlanDialog,
                            RequestDialog, WorkOrderDialog)
from mihenk_repo import (AssetRepo, AssetTypes, CalibrationRepo, ImpactRepo, RequestRepo,
                         ScheduleRepo, WorkOrderRepo)

ALL = ('', '- hepsi -')


class Screen(ttk.Frame):
    """Ekranlarin ortak iskeleti: baslik, arac serigi, govde."""

    title = ''
    subtitle = ''

    def __init__(self, parent, app):
        super().__init__(parent, padding=(24, 18, 24, 12))
        self.app = app
        self.conn = app.conn

        head = ttk.Frame(self)
        head.pack(fill='x')
        self.title_label = ttk.Label(head, text=self.title, style='Title.TLabel')
        self.title_label.pack(side='left')
        self.actions = ttk.Frame(head)
        self.actions.pack(side='right')
        if self.subtitle:
            ttk.Label(self, text=self.subtitle, style='Muted.TLabel').pack(anchor='w', pady=(2, 0))

        self.toolbar = ttk.Frame(self)
        self.toolbar.pack(fill='x', pady=(12, 8))
        self.body = ttk.Frame(self)
        self.body.pack(fill='both', expand=True)
        self.build()

    def build(self) -> None:
        """Alt siniflar icerigi burada kurar."""

    def refresh(self) -> None:
        """Alt siniflar veriyi burada tazeler."""

    def open_dialog(self, factory) -> None:
        """Pencereyi acar ve kapandiginda ekrani tazeler."""
        dialog = factory()
        self.wait_window(dialog)
        self.app.refresh()

    def run(self, action, success: str) -> bool:
        return self.app.run(action, success)


# ====================================================================== pano
class DashboardScreen(Screen):
    title = 'Pano'

    def build(self) -> None:
        ttk.Button(self.actions, text='Taramayı çalıştır', style='Accent.TButton',
                   command=self.run_scan).pack(side='right')

        cards = ttk.Frame(self.body)
        cards.pack(fill='x', pady=(0, 14))
        self.cards = {}
        definitions = (
            ('assets', 'Aktif varlık', lambda: self.app.go('assets')),
            ('work_orders', 'Açık iş emri', lambda: self.app.go('work_orders')),
            ('calibrations', 'Açık kalibrasyon kaydı', lambda: self.app.go('calibrations')),
            ('impacts', 'Açık etki değerlendirmesi', lambda: self.app.go('impacts')),
            ('overdue', 'Geciken plan', lambda: self.app.go('plans')),
        )
        for index, (key, label, jump) in enumerate(definitions):
            card = w.Card(cards, label, '0', on_click=jump)
            card.grid(row=0, column=index, sticky='nsew', padx=(0 if index == 0 else 8, 0))
            cards.columnconfigure(index, weight=1)
            self.cards[key] = card

        panes = ttk.Frame(self.body)
        panes.pack(fill='both', expand=True)
        panes.columnconfigure(0, weight=3)
        panes.columnconfigure(1, weight=2)
        panes.rowconfigure(1, weight=1)

        ttk.Label(panes, text='Açık etki değerlendirmeleri', style='Heading.TLabel').grid(
            row=0, column=0, sticky='w', pady=(0, 6))
        self.impact_table = w.DataTable(
            panes, [('asset', 'Varlık', 190), ('window', 'Etkilenen aralık', 230),
                    ('opened', 'Açılma', 90)],
            on_open=lambda row: self.open_dialog(lambda: ImpactDialog(self.app, row['id'])), height=5)
        self.impact_table.grid(row=1, column=0, sticky='nsew', padx=(0, 12))

        ttk.Label(panes, text='Sayaç baskısı', style='Heading.TLabel').grid(
            row=0, column=1, sticky='w', pady=(0, 6))
        self.counter_table = w.DataTable(
            panes, [('asset', 'Varlık', 130), ('plan', 'Plan', 170), ('remaining', 'Kalan', 70, 'e')],
            height=5)
        self.counter_table.grid(row=1, column=1, sticky='nsew')

        lower = ttk.Frame(self.body)
        lower.pack(fill='both', expand=True, pady=(14, 0))
        lower.columnconfigure(0, weight=1)
        lower.columnconfigure(1, weight=1)
        lower.rowconfigure(1, weight=1)

        ttk.Label(lower, text='Geciken planlar', style='Heading.TLabel').grid(
            row=0, column=0, sticky='w', pady=(0, 6))
        self.overdue_table = w.DataTable(
            lower, [('asset', 'Varlık', 165), ('plan', 'Plan', 175), ('type', 'Tip', 100),
                    ('due', 'Vade', 95)],
            on_open=lambda row: self.open_dialog(lambda: PlanDialog(self.app, row['id'])), height=7)
        self.overdue_table.grid(row=1, column=0, sticky='nsew', padx=(0, 12))

        ttk.Label(lower, text='Yaklaşanlar', style='Heading.TLabel').grid(
            row=0, column=1, sticky='w', pady=(0, 6))
        self.upcoming_table = w.DataTable(
            lower, [('asset', 'Varlık', 160), ('plan', 'Plan', 185), ('due', 'Vade', 95)],
            on_open=lambda row: self.open_dialog(lambda: PlanDialog(self.app, row['id'])), height=7)
        self.upcoming_table.grid(row=1, column=1, sticky='nsew')

        self.scan_label = ttk.Label(self.body, text='', style='Muted.TLabel')
        self.scan_label.pack(anchor='w', pady=(12, 0))

    def refresh(self) -> None:
        conn = self.app.conn
        self.conn = conn
        open_impacts = ImpactRepo.count(conn, 'open')
        overdue_count = ScheduleRepo.count_due(conn, overdue_only=True)
        self.cards['assets'].set_value(AssetRepo.count(conn, 'active'))
        self.cards['work_orders'].set_value(WorkOrderRepo.count(conn, open_only=True))
        self.cards['calibrations'].set_value(CalibrationRepo.count(conn, open_only=True))
        self.cards['impacts'].set_value(open_impacts, alert=bool(open_impacts))
        self.cards['overdue'].set_value(overdue_count, alert=bool(overdue_count))

        impacts = ImpactRepo.query(conn, status='open')
        self.impact_table.set_rows(impacts, values=lambda r: (
            AssetRepo.label(conn, int(r['asset_id'])),
            '%s – %s' % (v.human(r['affected_from'], with_time=True),
                         v.human(r['affected_to'], with_time=True)),
            v.human(r['opened_at'])), tag_of=lambda _r: 'alert')

        pressure = scheduler.counter_pressure(conn)
        self.counter_table.set_rows(
            [{'id': item['plan']['id'], **item} for item in pressure],
            values=lambda r: (r['asset']['code'], r['plan']['title'],
                              ('%+d' % -r['remaining']) if r['remaining'] <= 0 else str(r['remaining'])),
            tag_of=lambda r: 'alert' if r['remaining'] <= 0 else None)

        plan_types = ScheduleRepo.PLAN_TYPES
        self.overdue_table.set_rows(scheduler.overdue(conn), values=lambda r: (
            AssetRepo.label(conn, int(r['asset_id'])), r['title'],
            plan_types.get(r['plan_type'], r['plan_type']), v.human(r['next_due_at'])),
            tag_of=lambda _r: 'alert')
        self.upcoming_table.set_rows(scheduler.upcoming(conn), values=lambda r: (
            AssetRepo.label(conn, int(r['asset_id'])), r['title'], v.human(r['next_due_at'])))

        last = scheduler.last_scan()
        if last:
            self.scan_label.configure(
                text='Son tarama: %s — %d iş emri, %d kalibrasyon kaydı, %d plan atlandı.'
                     % (v.human(last['at'], with_time=True), last['work_orders'],
                        last['calibrations'], last['skipped']))
        else:
            self.scan_label.configure(text='Tarama henüz çalışmadı.')

    def run_scan(self) -> None:
        made = {}

        def scan():
            made.update(scheduler.scan(self.app.conn))
        if self.run(scan, ''):
            self.app.refresh()
            self.app.toast('Tarama bitti: %d iş emri, %d kalibrasyon kaydı, %d plan atlandı.'
                           % (made['work_orders'], made['calibrations'], made['skipped']))


# ====================================================================== varliklar
class AssetsScreen(Screen):
    title = 'Varlıklar'

    def build(self) -> None:
        ttk.Button(self.actions, text='Varlık ekle', style='Accent.TButton',
                   command=lambda: self.open_dialog(lambda: AssetDialog(self.app))).pack(side='right')

        self.search = tk.StringVar()
        entry = ttk.Entry(self.toolbar, textvariable=self.search, width=28)
        entry.pack(side='left')
        entry.bind('<KeyRelease>', lambda _e: self.refresh())
        ttk.Label(self.toolbar, text='Ara', style='Muted.TLabel').pack(side='left', padx=(6, 16))

        self.status = w.Combo(self.toolbar, [ALL] + list(AssetTypes.STATUSES.items()), width=18)
        self.status.pack(side='left', padx=(0, 8))
        self.status.bind('<<ComboboxSelected>>', lambda _e: self.refresh())
        self.kind = w.Combo(self.toolbar, [ALL] + list(AssetTypes.TYPES.items()), width=18)
        self.kind.pack(side='left')
        self.kind.bind('<<ComboboxSelected>>', lambda _e: self.refresh())

        self.count_label = ttk.Label(self.toolbar, text='', style='Muted.TLabel')
        self.count_label.pack(side='right')

        self.table = w.DataTable(
            self.body,
            [('code', 'Kod', 125), ('name', 'Ad', 220), ('type', 'Tip', 120),
             ('location', 'Konum', 170), ('status', 'Durum', 175), ('plans', 'Plan', 55, 'e'),
             ('next_due', 'Sıradaki vade', 115)],
            on_open=lambda row: self.open_dialog(lambda: AssetDialog(self.app, row['id'])))
        self.table.pack(fill='both', expand=True)

    def refresh(self) -> None:
        conn = self.app.conn
        rows = AssetRepo.query(conn, status=self.status.key() or '',
                               asset_type=self.kind.key() or '',
                               search=self.search.get().strip())

        def cells(row):
            plans = ScheduleRepo.query(conn, asset_id=int(row['id']), is_active=True)
            due = ''
            for plan in plans:
                when = plan['next_due_at']
                if when and (not due or when < due):
                    due = when
            open_impacts = ImpactRepo.open_count_for_asset(conn, int(row['id']))
            status = states.label('asset', row['status'])
            if open_impacts:
                status += '  · %d açık etki' % open_impacts
            return (row['code'], row['name'], AssetTypes.label(row['asset_type']),
                    row['location_text'], status, len(plans), v.human(due))

        def tag(row):
            if row['status'] == 'quarantined':
                return 'alert'
            if row['status'] in ('retired', 'out_of_service'):
                return 'muted'
            return None

        self.table.set_rows(rows, values=cells, tag_of=tag)
        self.count_label.configure(text='%d varlık' % len(rows))


# ====================================================================== planlar
class PlansScreen(Screen):
    title = 'Planlar'

    def build(self) -> None:
        ttk.Button(self.actions, text='Plan ekle', style='Accent.TButton',
                   command=lambda: self.open_dialog(lambda: PlanDialog(self.app))).pack(side='right')

        self.kind = w.Combo(self.toolbar, [ALL] + list(ScheduleRepo.PLAN_TYPES.items()), width=22)
        self.kind.pack(side='left', padx=(0, 8))
        self.kind.bind('<<ComboboxSelected>>', lambda _e: self.refresh())
        self.only_active = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.toolbar, text='Yalnızca aktif', variable=self.only_active,
                        command=self.refresh).pack(side='left', padx=(0, 12))

        ttk.Button(self.toolbar, text='Duraklat / etkinleştir', command=self.toggle).pack(side='left')
        self.count_label = ttk.Label(self.toolbar, text='', style='Muted.TLabel')
        self.count_label.pack(side='right')

        self.table = w.DataTable(
            self.body,
            [('title', 'Plan', 240), ('asset', 'Varlık', 220), ('type', 'Tip', 130),
             ('interval', 'Aralık', 130), ('last', 'Son yapılma', 110),
             ('due', 'Sıradaki vade', 120), ('active', 'Aktif', 60, 'center')],
            on_open=lambda row: self.open_dialog(lambda: PlanDialog(self.app, row['id'])))
        self.table.pack(fill='both', expand=True)

    def refresh(self) -> None:
        conn = self.app.conn
        rows = ScheduleRepo.query(conn, plan_type=self.kind.key() or '',
                                  is_active=True if self.only_active.get() else None)
        now = v.parse(v.now())

        def cells(row):
            if row['basis'] == 'counter':
                interval = 'her %d birim' % int(row['counter_interval'])
                due = '%d değerinde' % int(row['next_due_counter'])
            else:
                interval = '%d %s' % (int(row['interval_value']),
                                      ScheduleRepo.UNITS.get(row['interval_unit'], ''))
                due = v.human(row['next_due_at'])
            return (row['title'], AssetRepo.label(conn, int(row['asset_id'])),
                    ScheduleRepo.PLAN_TYPES.get(row['plan_type'], row['plan_type']), interval,
                    v.human(row['last_done_at']) or '—', due, 'evet' if row['is_active'] else 'hayır')

        def tag(row):
            if not row['is_active']:
                return 'muted'
            due = v.parse(row['next_due_at'])
            if due and (now - due).days > int(row['tolerance_days']):
                return 'alert'
            return None

        self.table.set_rows(rows, values=cells, tag_of=tag)
        self.count_label.configure(text='%d plan' % len(rows))

    def toggle(self) -> None:
        row = self.table.selected_row()
        if not row:
            messagebox.showinfo('Seçim yok', 'Önce bir plan seçin.', parent=self)
            return
        target = not bool(row['is_active'])
        if self.run(lambda: ScheduleRepo.set_active(self.app.conn, row['id'], target),
                    'Plan %s.' % ('etkinleştirildi' if target else 'duraklatıldı')):
            self.app.refresh()


# ====================================================================== talepler
class RequestsScreen(Screen):
    title = 'Talepler'

    def build(self) -> None:
        ttk.Button(self.actions, text='Arıza bildir', style='Accent.TButton',
                   command=lambda: self.open_dialog(lambda: RequestDialog(self.app))).pack(side='right')

        self.status = w.Combo(self.toolbar, [ALL] + list(states.states('request').items()), width=20)
        self.status.pack(side='left', padx=(0, 12))
        self.status.bind('<<ComboboxSelected>>', lambda _e: self.refresh())

        ttk.Button(self.toolbar, text='Değerlendir', command=lambda: self.move('triaged')).pack(side='left')
        ttk.Button(self.toolbar, text='Reddet', command=self.reject).pack(side='left', padx=6)
        ttk.Button(self.toolbar, text='İş emri oluştur', style='Accent.TButton',
                   command=self.convert).pack(side='left')
        ttk.Button(self.toolbar, text='Kapat', command=lambda: self.move('closed')).pack(side='left', padx=6)

        self.count_label = ttk.Label(self.toolbar, text='', style='Muted.TLabel')
        self.count_label.pack(side='right')

        self.table = w.DataTable(
            self.body,
            [('reported', 'Bildirim', 130), ('asset', 'Varlık', 200), ('summary', 'Özet', 300),
             ('severity', 'Önem', 130), ('status', 'Durum', 130), ('wo', 'İş emri', 80, 'e')],
            on_open=self.open_row)
        self.table.pack(fill='both', expand=True)

    def refresh(self) -> None:
        conn = self.app.conn
        rows = RequestRepo.query(conn, status=self.status.key() or '')
        self.table.set_rows(rows, values=lambda r: (
            v.human(r['reported_at'], with_time=True), AssetRepo.label(conn, int(r['asset_id'])),
            r['summary'], RequestRepo.SEVERITIES.get(r['severity'], r['severity']),
            states.label('request', r['status']),
            ('#%d' % int(r['work_order_id'])) if int(r['work_order_id']) else ''),
            tag_of=lambda r: 'alert' if r['severity'] == 'stops_production' and r['status'] == 'open'
            else ('muted' if r['status'] in ('closed', 'rejected') else None))
        self.count_label.configure(text='%d talep' % len(rows))

    def selected(self):
        row = self.table.selected_row()
        if not row:
            messagebox.showinfo('Seçim yok', 'Önce bir talep seçin.', parent=self)
        return row

    def open_row(self, row) -> None:
        if int(row['work_order_id']):
            self.open_dialog(lambda: WorkOrderDialog(self.app, int(row['work_order_id'])))
            return
        detail = row['description'] or '(açıklama yok)'
        extra = ''
        if row['rejection_reason']:
            extra = '\n\nRet gerekçesi: %s' % row['rejection_reason']
        messagebox.showinfo(row['summary'], detail + extra, parent=self)

    def move(self, target: str) -> None:
        row = self.selected()
        if not row:
            return
        if self.run(lambda: RequestRepo.transition(self.app.conn, row['id'], target),
                    'Talep güncellendi.'):
            self.app.refresh()

    def reject(self) -> None:
        row = self.selected()
        if not row:
            return
        from mihenk_dialogs import _ask_text
        reason = _ask_text(self.app.root, 'Ret gerekçesi', 'Talep neden reddediliyor?')
        if not reason:
            return
        if self.run(lambda: RequestRepo.transition(self.app.conn, row['id'], 'rejected',
                                                   {'rejection_reason': reason}),
                    'Talep reddedildi.'):
            self.app.refresh()

    def convert(self) -> None:
        row = self.selected()
        if not row:
            return
        made = {}

        def convert():
            made['id'] = RequestRepo.convert(self.app.conn, row['id'])
        if self.run(convert, 'Talepten iş emri oluşturuldu.'):
            self.app.refresh()
            self.open_dialog(lambda: WorkOrderDialog(self.app, made['id']))


# ====================================================================== is emirleri
class WorkOrdersScreen(Screen):
    title = 'İş emirleri'

    def build(self) -> None:
        ttk.Button(self.actions, text='İş emri ekle', style='Accent.TButton',
                   command=lambda: self.open_dialog(lambda: WorkOrderDialog(self.app))).pack(side='right')

        self.status = w.Combo(self.toolbar, [('', '- açık olanlar -')] +
                              list(states.states('work_order').items()), width=20)
        self.status.pack(side='left', padx=(0, 8))
        self.status.bind('<<ComboboxSelected>>', lambda _e: self.refresh())
        self.kind = w.Combo(self.toolbar, [ALL] + list(WorkOrderRepo.TYPES.items()), width=16)
        self.kind.pack(side='left', padx=(0, 8))
        self.kind.bind('<<ComboboxSelected>>', lambda _e: self.refresh())
        self.show_all = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.toolbar, text='Kapananları da göster', variable=self.show_all,
                        command=self.refresh).pack(side='left')

        self.count_label = ttk.Label(self.toolbar, text='', style='Muted.TLabel')
        self.count_label.pack(side='right')

        self.table = w.DataTable(
            self.body,
            [('id', '#', 50, 'e'), ('title', 'İş emri', 260), ('asset', 'Varlık', 200),
             ('type', 'Tip', 110), ('priority', 'Öncelik', 90), ('assigned', 'Sorumlu', 140),
             ('planned', 'Planlanan', 110), ('status', 'Durum', 120)],
            on_open=lambda row: self.open_dialog(lambda: WorkOrderDialog(self.app, row['id'])))
        self.table.pack(fill='both', expand=True)

    def refresh(self) -> None:
        conn = self.app.conn
        status = self.status.key() or ''
        rows = WorkOrderRepo.query(conn, status=status, wo_type=self.kind.key() or '',
                                   open_only=(not status and not self.show_all.get()))
        now = v.parse(v.now())

        def cells(row):
            return (row['id'], row['title'], AssetRepo.label(conn, int(row['asset_id'])),
                    WorkOrderRepo.TYPES.get(row['wo_type'], row['wo_type']),
                    WorkOrderRepo.PRIORITIES.get(row['priority'], row['priority']),
                    row['assigned_to'] or '—', v.human(row['planned_start']) or '—',
                    states.label('work_order', row['status']))

        def tag(row):
            if row['status'] in ('closed', 'cancelled'):
                return 'muted'
            planned = v.parse(row['planned_start'])
            if planned and planned < now and row['status'] not in ('completed',):
                return 'alert'
            return None

        self.table.set_rows(rows, values=cells, tag_of=tag)
        self.count_label.configure(text='%d iş emri' % len(rows))


# ====================================================================== kalibrasyon
class CalibrationsScreen(Screen):
    title = 'Kalibrasyon ve doğrulama'

    def build(self) -> None:
        ttk.Button(self.actions, text='Kayıt oluştur', style='Accent.TButton',
                   command=self.create_record).pack(side='right')

        self.status = w.Combo(self.toolbar, [('', '- açık olanlar -')] +
                              list(states.states('calibration').items()), width=20)
        self.status.pack(side='left', padx=(0, 8))
        self.status.bind('<<ComboboxSelected>>', lambda _e: self.refresh())
        self.kind = w.Combo(self.toolbar, [ALL] + list(CalibrationRepo.RECORD_TYPES.items()), width=16)
        self.kind.pack(side='left', padx=(0, 8))
        self.kind.bind('<<ComboboxSelected>>', lambda _e: self.refresh())
        self.result = w.Combo(self.toolbar, [ALL] + list(CalibrationRepo.RESULTS.items()), width=16)
        self.result.pack(side='left', padx=(0, 8))
        self.result.bind('<<ComboboxSelected>>', lambda _e: self.refresh())
        self.show_all = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.toolbar, text='Kapananları da göster', variable=self.show_all,
                        command=self.refresh).pack(side='left')

        self.count_label = ttk.Label(self.toolbar, text='', style='Muted.TLabel')
        self.count_label.pack(side='right')

        self.table = w.DataTable(
            self.body,
            [('id', '#', 50, 'e'), ('asset', 'Varlık', 230), ('type', 'Tip', 110),
             ('performed', 'Yapılma', 110), ('result', 'Sonuç', 100),
             ('deviation', 'En büyük sapma', 120, 'e'), ('certificate', 'Sertifika', 150),
             ('status', 'Durum', 120)],
            on_open=lambda row: self.open_dialog(lambda: CalibrationDialog(self.app, row['id'])))
        self.table.pack(fill='both', expand=True)

    def refresh(self) -> None:
        conn = self.app.conn
        status = self.status.key() or ''
        rows = CalibrationRepo.query(conn, status=status, record_type=self.kind.key() or '',
                                     result=self.result.key() or '',
                                     open_only=(not status and not self.show_all.get()))

        def cells(row):
            deviation = '' if row['max_deviation'] is None else ('%g' % row['max_deviation'])
            return (row['id'], AssetRepo.label(conn, int(row['asset_id'])),
                    CalibrationRepo.RECORD_TYPES.get(row['record_type'], row['record_type']),
                    v.human(row['performed_at']) or '—',
                    CalibrationRepo.RESULTS.get(row['result'], '—'), deviation,
                    row['certificate_no'] or '—', states.label('calibration', row['status']))

        def tag(row):
            if row['result'] == 'fail':
                return 'alert'
            if row['status'] in ('closed', 'cancelled'):
                return 'muted'
            return None

        self.table.set_rows(rows, values=cells, tag_of=tag)
        self.count_label.configure(text='%d kayıt' % len(rows))

    def create_record(self) -> None:
        """Plan disi kalibrasyon kaydi acar."""
        options = AssetRepo.options(self.app.conn)
        if not options:
            messagebox.showinfo('Varlık yok', 'Önce bir varlık ekleyin.', parent=self)
            return
        picker = tk.Toplevel(self.app.root)
        picker.title('Kayıt oluştur')
        picker.transient(self.app.root)
        picker.configure(background=theme.color('bg'))
        picker.resizable(False, False)

        form = w.FormGrid(picker, label_width=18)
        form.pack(fill='x', padx=18, pady=(16, 6))
        asset = form.add('Varlık', w.Combo(form, options, width=40))
        kind = form.add('Kayıt tipi', w.Combo(form, CalibrationRepo.RECORD_TYPES, width=24))
        spec = form.add('Tolerans şartnamesi', ttk.Entry(form, width=40))

        made = {}

        def create():
            data = {'asset_id': asset.key(), 'record_type': kind.key(),
                    'tolerance_spec': spec.get()}

            def action():
                made['id'] = CalibrationRepo.create(self.app.conn, data)
            if self.run(action, 'Kayıt oluşturuldu.'):
                picker.destroy()

        bar = ttk.Frame(picker, padding=(18, 10))
        bar.pack(fill='x')
        ttk.Button(bar, text='Oluştur', style='Accent.TButton', command=create).pack(side='right')
        ttk.Button(bar, text='Vazgeç', command=picker.destroy).pack(side='right', padx=6)
        picker.grab_set()
        self.wait_window(picker)
        self.app.refresh()
        if made.get('id'):
            self.open_dialog(lambda: CalibrationDialog(self.app, made['id']))


# ====================================================================== etki
class ImpactsScreen(Screen):
    title = 'Etki değerlendirmeleri'
    subtitle = ('Açık her değerlendirme, ilgili varlığı hizmet dışında tutar. '
                'Kapatma bir karar gerektirir.')

    def build(self) -> None:
        self.status = w.Combo(self.toolbar, [('open', 'Açık'), ('closed', 'Kapalı'), ALL], width=18)
        self.status.pack(side='left')
        self.status.bind('<<ComboboxSelected>>', lambda _e: self.refresh())
        self.count_label = ttk.Label(self.toolbar, text='', style='Muted.TLabel')
        self.count_label.pack(side='right')

        self.table = w.DataTable(
            self.body,
            [('id', '#', 50, 'e'), ('asset', 'Varlık', 230), ('window', 'Etkilenen aralık', 280),
             ('decision', 'Karar', 180), ('opened', 'Açılma', 110), ('status', 'Durum', 100)],
            on_open=lambda row: self.open_dialog(lambda: ImpactDialog(self.app, row['id'])))
        self.table.pack(fill='both', expand=True)

    def refresh(self) -> None:
        conn = self.app.conn
        rows = ImpactRepo.query(conn, status=self.status.key() or '')
        self.table.set_rows(rows, values=lambda r: (
            r['id'], AssetRepo.label(conn, int(r['asset_id'])),
            '%s – %s' % (v.human(r['affected_from'], with_time=True),
                         v.human(r['affected_to'], with_time=True)),
            ImpactRepo.DECISIONS.get(r['decision'], '—'), v.human(r['opened_at']),
            states.label('impact', r['status'])),
            tag_of=lambda r: 'alert' if r['status'] == 'open' else 'muted')
        self.count_label.configure(text='%d değerlendirme' % len(rows))
