# -*- coding: utf-8 -*-
"""Ana ekranlar: pano, varliklar, planlar, talepler, is emirleri, kalibrasyon, etki."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import mihenk_export as export
import mihenk_reports as reports
import mihenk_scheduler as scheduler
import mihenk_states as states
import mihenk_store as store
import mihenk_theme as theme
import mihenk_validate as v
import mihenk_widgets as w
from mihenk_dialogs import (AssetDialog, CalibrationDialog, ExportDialog, ImpactDialog,
                            PartDialog, PlanDialog, RequestDialog, WorkOrderDialog, _open_path)
from mihenk_parts import PartRepo
from mihenk_repo import (AssetRepo, AssetTypes, CalibrationRepo, ImpactRepo, RequestRepo,
                         ScheduleRepo, WorkOrderRepo)
from mihenk_i18n import t

ALL = ('', t('- hepsi -'))


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

    def set_hint(self, text: str = '') -> None:
        """Liste bosken ne yapilmasi gerektigini soyleyen tek satir."""
        if not hasattr(self, '_hint'):
            self._hint = ttk.Label(self, text='', style='Muted.TLabel', wraplength=820,
                                   justify='left')
        if text:
            self._hint.configure(text=text)
            if not self._hint.winfo_manager():
                self._hint.pack(anchor='w', pady=(10, 0))
        else:
            self._hint.pack_forget()

    def open_dialog(self, factory) -> None:
        """Pencereyi acar ve kapandiginda ekrani tazeler."""
        dialog = factory()
        self.wait_window(dialog)
        self.app.refresh()

    def run(self, action, success: str) -> bool:
        return self.app.run(action, success)


# ====================================================================== pano
class DashboardScreen(Screen):
    title = t('Pano')

    def build(self) -> None:
        ttk.Button(self.actions, text=t('Taramayı çalıştır'), style='Accent.TButton',
                   command=self.run_scan).pack(side='right')

        cards = ttk.Frame(self.body)
        cards.pack(fill='x', pady=(0, 14))
        self.cards = {}
        definitions = (
            ('assets', t('Aktif varlık'), lambda: self.app.go('assets')),
            ('work_orders', t('Açık iş emri'), lambda: self.app.go('work_orders')),
            ('calibrations', t('Açık kalibrasyon kaydı'), lambda: self.app.go('calibrations')),
            ('impacts', t('Açık etki değerlendirmesi'), lambda: self.app.go('impacts')),
            ('overdue', t('Geciken plan'), lambda: self.app.go('plans')),
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

        ttk.Label(panes, text=t('Açık etki değerlendirmeleri'), style='Heading.TLabel').grid(
            row=0, column=0, sticky='w', pady=(0, 6))
        self.impact_table = w.DataTable(
            panes, [('asset', t('Varlık'), 190), ('window', t('Etkilenen aralık'), 230),
                    ('opened', t('Açılma'), 90)],
            on_open=lambda row: self.open_dialog(lambda: ImpactDialog(self.app, row['id'])),
            height=6, autosize=True)
        self.impact_table.grid(row=1, column=0, sticky='nsew', padx=(0, 12))

        ttk.Label(panes, text=t('Sayaç baskısı'), style='Heading.TLabel').grid(
            row=0, column=1, sticky='w', pady=(0, 6))
        self.counter_table = w.DataTable(
            panes, [('asset', t('Varlık'), 130), ('plan', t('Plan'), 170), ('remaining', t('Kalan'), 70, 'e')],
            height=6, autosize=True)
        self.counter_table.grid(row=1, column=1, sticky='nsew')

        lower = ttk.Frame(self.body)
        lower.pack(fill='both', expand=True, pady=(14, 0))
        lower.columnconfigure(0, weight=1)
        lower.columnconfigure(1, weight=1)
        lower.rowconfigure(1, weight=1)

        ttk.Label(lower, text=t('Geciken planlar'), style='Heading.TLabel').grid(
            row=0, column=0, sticky='w', pady=(0, 6))
        self.overdue_table = w.DataTable(
            lower, [('asset', t('Varlık'), 165), ('plan', t('Plan'), 175), ('type', t('Tip'), 100),
                    ('due', t('Vade'), 95)],
            on_open=lambda row: self.open_dialog(lambda: PlanDialog(self.app, row['id'])), height=7)
        self.overdue_table.grid(row=1, column=0, sticky='nsew', padx=(0, 12))

        ttk.Label(lower, text=t('Yaklaşanlar'), style='Heading.TLabel').grid(
            row=0, column=1, sticky='w', pady=(0, 6))
        self.upcoming_table = w.DataTable(
            lower, [('asset', t('Varlık'), 160), ('plan', t('Plan'), 185), ('due', t('Vade'), 95)],
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
                text=t('Son tarama: %s — %d iş emri, %d kalibrasyon kaydı, %d plan atlandı.')
                     % (v.human(last['at'], with_time=True), last['work_orders'],
                        last['calibrations'], last['skipped']))
        else:
            self.scan_label.configure(text=t('Tarama henüz çalışmadı.'))

    def run_scan(self) -> None:
        made = {}

        def scan():
            made.update(scheduler.scan(self.app.conn))
        if self.run(scan, ''):
            self.app.refresh()
            self.app.toast(t('Tarama bitti: %d iş emri, %d kalibrasyon kaydı, %d plan atlandı.')
                           % (made['work_orders'], made['calibrations'], made['skipped']))


# ====================================================================== varliklar
class AssetsScreen(Screen):
    title = t('Varlıklar')

    def build(self) -> None:
        ttk.Button(self.actions, text=t('Varlık ekle'), style='Accent.TButton',
                   command=lambda: self.open_dialog(lambda: AssetDialog(self.app))).pack(side='right')

        self.search = tk.StringVar()
        entry = ttk.Entry(self.toolbar, textvariable=self.search, width=28)
        entry.pack(side='left')
        entry.bind('<KeyRelease>', lambda _e: self.refresh())
        ttk.Label(self.toolbar, text=t('Ara'), style='Muted.TLabel').pack(side='left', padx=(6, 16))

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
            [('code', t('Kod'), 125), ('name', t('Ad'), 220), ('type', t('Tip'), 120),
             ('location', t('Konum'), 170), ('status', t('Durum'), 175), ('plans', t('Plan'), 55, 'e'),
             ('next_due', t('Sıradaki vade'), 115)],
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
                status += t('  · %d açık etki') % open_impacts
            return (row['code'], row['name'], AssetTypes.label(row['asset_type']),
                    row['location_text'], status, len(plans), v.human(due))

        def tag(row):
            if row['status'] == 'quarantined':
                return 'alert'
            if row['status'] in ('retired', 'out_of_service'):
                return 'muted'
            return None

        self.table.set_rows(rows, values=cells, tag_of=tag)
        self.count_label.configure(text=t('%d varlık') % len(rows))
        self.set_hint(t('Kütük boş. Sağ üstteki Varlık ekle ile başlayın; ölçüm cihazları için '
                      '"Ölçüm cihazı" kutusunu işaretleyin, kalibrasyon planı ancak öyle '
                      'bağlanabilir.') if not rows and not self.search.get().strip() else '')


# ====================================================================== planlar
class PlansScreen(Screen):
    title = t('Planlar')

    def build(self) -> None:
        ttk.Button(self.actions, text=t('Plan ekle'), style='Accent.TButton',
                   command=lambda: self.open_dialog(lambda: PlanDialog(self.app))).pack(side='right')

        self.kind = w.Combo(self.toolbar, [ALL] + list(ScheduleRepo.PLAN_TYPES.items()), width=22)
        self.kind.pack(side='left', padx=(0, 8))
        self.kind.bind('<<ComboboxSelected>>', lambda _e: self.refresh())
        self.only_active = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.toolbar, text=t('Yalnızca aktif'), variable=self.only_active,
                        command=self.refresh).pack(side='left', padx=(0, 12))

        ttk.Button(self.toolbar, text=t('Duraklat / etkinleştir'), command=self.toggle).pack(side='left')
        self.count_label = ttk.Label(self.toolbar, text='', style='Muted.TLabel')
        self.count_label.pack(side='right')

        self.table = w.DataTable(
            self.body,
            [('title', t('Plan'), 240), ('asset', t('Varlık'), 220), ('type', t('Tip'), 130),
             ('interval', t('Aralık'), 130), ('last', t('Son yapılma'), 110),
             ('due', t('Sıradaki vade'), 120), ('active', t('Aktif'), 60, 'center')],
            on_open=lambda row: self.open_dialog(lambda: PlanDialog(self.app, row['id'])))
        self.table.pack(fill='both', expand=True)

    def refresh(self) -> None:
        conn = self.app.conn
        rows = ScheduleRepo.query(conn, plan_type=self.kind.key() or '',
                                  is_active=True if self.only_active.get() else None)
        now = v.parse(v.now())

        def cells(row):
            if row['basis'] == 'counter':
                interval = t('her %d birim') % int(row['counter_interval'])
                due = t('%d değerinde') % int(row['next_due_counter'])
            else:
                interval = '%d %s' % (int(row['interval_value']),
                                      ScheduleRepo.UNITS.get(row['interval_unit'], ''))
                due = v.human(row['next_due_at'])
            return (row['title'], AssetRepo.label(conn, int(row['asset_id'])),
                    ScheduleRepo.PLAN_TYPES.get(row['plan_type'], row['plan_type']), interval,
                    v.human(row['last_done_at']) or '—', due, t('evet') if row['is_active'] else t('hayır'))

        def tag(row):
            if not row['is_active']:
                return 'muted'
            due = v.parse(row['next_due_at'])
            if due and (now - due).days > int(row['tolerance_days']):
                return 'alert'
            return None

        self.table.set_rows(rows, values=cells, tag_of=tag)
        self.count_label.configure(text=t('%d plan') % len(rows))
        self.set_hint(t('Henüz plan yok. Bir varlığa plan bağlayın: önleyici plan iş emri, '
                      'kalibrasyon ve doğrulama planı kalibrasyon kaydı üretir.')
                      if not rows else '')

    def toggle(self) -> None:
        row = self.table.selected_row()
        if not row:
            messagebox.showinfo(t('Seçim yok'), t('Önce bir plan seçin.'), parent=self)
            return
        target = not bool(row['is_active'])
        if self.run(lambda: ScheduleRepo.set_active(self.app.conn, row['id'], target),
                    t('Plan %s.') % (t('etkinleştirildi') if target else t('duraklatıldı'))):
            self.app.refresh()


# ====================================================================== talepler
class RequestsScreen(Screen):
    title = t('Talepler')

    def build(self) -> None:
        ttk.Button(self.actions, text=t('Arıza bildir'), style='Accent.TButton',
                   command=lambda: self.open_dialog(lambda: RequestDialog(self.app))).pack(side='right')

        self.status = w.Combo(self.toolbar, [ALL] + list(states.states('request').items()), width=20)
        self.status.pack(side='left', padx=(0, 12))
        self.status.bind('<<ComboboxSelected>>', lambda _e: self.refresh())

        ttk.Button(self.toolbar, text=t('Değerlendir'), command=lambda: self.move('triaged')).pack(side='left')
        ttk.Button(self.toolbar, text=t('Reddet'), command=self.reject).pack(side='left', padx=6)
        ttk.Button(self.toolbar, text=t('İş emri oluştur'), style='Accent.TButton',
                   command=self.convert).pack(side='left')
        ttk.Button(self.toolbar, text=t('Kapat'), command=lambda: self.move('closed')).pack(side='left', padx=6)

        self.count_label = ttk.Label(self.toolbar, text='', style='Muted.TLabel')
        self.count_label.pack(side='right')

        self.table = w.DataTable(
            self.body,
            [('reported', t('Bildirim'), 130), ('asset', t('Varlık'), 200), ('summary', t('Özet'), 300),
             ('severity', t('Önem'), 130), ('status', t('Durum'), 130), ('wo', t('İş emri'), 80, 'e')],
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
        self.count_label.configure(text=t('%d talep') % len(rows))
        self.set_hint(t('Talep yok. Sahadan gelen bir arızayı buraya bildirin; değerlendirildikten '
                      'sonra iş emrine dönüştürülür.') if not rows else '')

    def selected(self):
        row = self.table.selected_row()
        if not row:
            messagebox.showinfo(t('Seçim yok'), t('Önce bir talep seçin.'), parent=self)
        return row

    def open_row(self, row) -> None:
        if int(row['work_order_id']):
            self.open_dialog(lambda: WorkOrderDialog(self.app, int(row['work_order_id'])))
            return
        detail = row['description'] or t('(açıklama yok)')
        extra = ''
        if row['rejection_reason']:
            extra = t('\n\nRet gerekçesi: %s') % row['rejection_reason']
        messagebox.showinfo(row['summary'], detail + extra, parent=self)

    def move(self, target: str) -> None:
        row = self.selected()
        if not row:
            return
        if self.run(lambda: RequestRepo.transition(self.app.conn, row['id'], target),
                    t('Talep güncellendi.')):
            self.app.refresh()

    def reject(self) -> None:
        row = self.selected()
        if not row:
            return
        from mihenk_dialogs import _ask_text
        reason = _ask_text(self.app.root, t('Ret gerekçesi'), 'Talep neden reddediliyor?')
        if not reason:
            return
        if self.run(lambda: RequestRepo.transition(self.app.conn, row['id'], 'rejected',
                                                   {'rejection_reason': reason}),
                    t('Talep reddedildi.')):
            self.app.refresh()

    def convert(self) -> None:
        row = self.selected()
        if not row:
            return
        made = {}

        def convert():
            made['id'] = RequestRepo.convert(self.app.conn, row['id'])
        if self.run(convert, t('Talepten iş emri oluşturuldu.')):
            self.app.refresh()
            self.open_dialog(lambda: WorkOrderDialog(self.app, made['id']))


# ====================================================================== is emirleri
class WorkOrdersScreen(Screen):
    title = t('İş emirleri')

    def build(self) -> None:
        ttk.Button(self.actions, text=t('İş emri ekle'), style='Accent.TButton',
                   command=lambda: self.open_dialog(lambda: WorkOrderDialog(self.app))).pack(side='right')

        self.status = w.Combo(self.toolbar, [('', t('- açık olanlar -'))] +
                              list(states.states('work_order').items()), width=20)
        self.status.pack(side='left', padx=(0, 8))
        self.status.bind('<<ComboboxSelected>>', lambda _e: self.refresh())
        self.kind = w.Combo(self.toolbar, [ALL] + list(WorkOrderRepo.TYPES.items()), width=16)
        self.kind.pack(side='left', padx=(0, 8))
        self.kind.bind('<<ComboboxSelected>>', lambda _e: self.refresh())
        self.show_all = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.toolbar, text=t('Kapananları da göster'), variable=self.show_all,
                        command=self.refresh).pack(side='left')

        self.count_label = ttk.Label(self.toolbar, text='', style='Muted.TLabel')
        self.count_label.pack(side='right')

        self.table = w.DataTable(
            self.body,
            [('id', '#', 50, 'e'), ('title', t('İş emri'), 260), ('asset', t('Varlık'), 200),
             ('type', t('Tip'), 110), ('priority', t('Öncelik'), 90), ('assigned', t('Sorumlu'), 140),
             ('planned', t('Planlanan'), 110), ('status', t('Durum'), 120)],
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
        self.count_label.configure(text=t('%d iş emri') % len(rows))
        self.set_hint(t('Açık iş emri yok. Planlar vadesi geldiğinde kendiliğinden üretir; '
                      'Pano\'daki Taramayı çalıştır düğmesi bunu elle tetikler.')
                      if not rows else '')


# ====================================================================== kalibrasyon
class CalibrationsScreen(Screen):
    title = t('Kalibrasyon ve doğrulama')

    def build(self) -> None:
        ttk.Button(self.actions, text=t('Kayıt oluştur'), style='Accent.TButton',
                   command=self.create_record).pack(side='right')

        self.status = w.Combo(self.toolbar, [('', t('- açık olanlar -'))] +
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
        ttk.Checkbutton(self.toolbar, text=t('Kapananları da göster'), variable=self.show_all,
                        command=self.refresh).pack(side='left')

        self.count_label = ttk.Label(self.toolbar, text='', style='Muted.TLabel')
        self.count_label.pack(side='right')

        self.table = w.DataTable(
            self.body,
            [('id', '#', 50, 'e'), ('asset', t('Varlık'), 230), ('type', t('Tip'), 110),
             ('performed', t('Yapılma'), 110), ('result', t('Sonuç'), 100),
             ('deviation', t('En büyük sapma'), 120, 'e'), ('certificate', t('Sertifika'), 150),
             ('status', t('Durum'), 120)],
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
        self.count_label.configure(text=t('%d kayıt') % len(rows))
        self.set_hint(t('Açık kalibrasyon kaydı yok. Kalibrasyon planı vadesi gelince kayıt üretir; '
                      'plan dışı bir ölçüm için Kayıt oluştur düğmesini kullanın.')
                      if not rows else '')

    def create_record(self) -> None:
        """Plan disi kalibrasyon kaydi acar."""
        options = AssetRepo.options(self.app.conn)
        if not options:
            messagebox.showinfo(t('Varlık yok'), t('Önce bir varlık ekleyin.'), parent=self)
            return
        picker = tk.Toplevel(self.app.root)
        picker.title(t('Kayıt oluştur'))
        picker.transient(self.app.root)
        picker.configure(background=theme.color('bg'))
        picker.resizable(False, False)

        form = w.FormGrid(picker, label_width=18)
        form.pack(fill='x', padx=18, pady=(16, 6))
        asset = form.add(t('Varlık'), w.Combo(form, options, width=40))
        kind = form.add(t('Kayıt tipi'), w.Combo(form, CalibrationRepo.RECORD_TYPES, width=24))
        spec = form.add(t('Tolerans şartnamesi'), ttk.Entry(form, width=40))

        made = {}

        def create():
            data = {'asset_id': asset.key(), 'record_type': kind.key(),
                    'tolerance_spec': spec.get()}

            def action():
                made['id'] = CalibrationRepo.create(self.app.conn, data)
            if self.run(action, t('Kayıt oluşturuldu.')):
                picker.destroy()

        bar = ttk.Frame(picker, padding=(18, 10))
        bar.pack(fill='x')
        ttk.Button(bar, text=t('Oluştur'), style='Accent.TButton', command=create).pack(side='right')
        ttk.Button(bar, text=t('Vazgeç'), command=picker.destroy).pack(side='right', padx=6)
        picker.grab_set()
        self.wait_window(picker)
        self.app.refresh()
        if made.get('id'):
            self.open_dialog(lambda: CalibrationDialog(self.app, made['id']))


# ====================================================================== etki
class ImpactsScreen(Screen):
    title = t('Etki değerlendirmeleri')
    subtitle = (t('Açık her değerlendirme, ilgili varlığı hizmet dışında tutar. '
                'Kapatma bir karar gerektirir.'))

    def build(self) -> None:
        self.status = w.Combo(self.toolbar, [('open', t('Açık')), ('closed', t('Kapalı')), ALL], width=18)
        self.status.pack(side='left')
        self.status.bind('<<ComboboxSelected>>', lambda _e: self.refresh())
        self.count_label = ttk.Label(self.toolbar, text='', style='Muted.TLabel')
        self.count_label.pack(side='right')

        self.table = w.DataTable(
            self.body,
            [('id', '#', 50, 'e'), ('asset', t('Varlık'), 230), ('window', t('Etkilenen aralık'), 280),
             ('decision', t('Karar'), 180), ('opened', t('Açılma'), 110), ('status', t('Durum'), 100)],
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
        self.count_label.configure(text=t('%d değerlendirme') % len(rows))
        self.set_hint(t('Etki değerlendirmesi yok. Bu kayıtlar elle açılmaz: bir kalibrasyon '
                      'uygunsuz çıktığında kendiliğinden açılır.') if not rows else '')


# ====================================================================== yedek parcalar
class PartsScreen(Screen):
    title = t('Yedek parçalar')

    def build(self) -> None:
        ttk.Button(self.actions, text=t('Parça ekle'), style='Accent.TButton',
                   command=lambda: self.open_dialog(lambda: PartDialog(self.app))).pack(side='right')

        self.search = tk.StringVar()
        entry = ttk.Entry(self.toolbar, textvariable=self.search, width=26)
        entry.pack(side='left')
        entry.bind('<KeyRelease>', lambda _e: self.refresh())
        ttk.Label(self.toolbar, text=t('Ara'), style='Muted.TLabel').pack(side='left', padx=(6, 16))

        self.low_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.toolbar, text=t('Yalnızca düşük stok'), variable=self.low_only,
                        command=self.refresh).pack(side='left')
        self.show_passive = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.toolbar, text=t('Pasifleri de göster'), variable=self.show_passive,
                        command=self.refresh).pack(side='left', padx=(12, 0))

        self.count_label = ttk.Label(self.toolbar, text='', style='Muted.TLabel')
        self.count_label.pack(side='right')

        self.table = w.DataTable(
            self.body,
            [('code', t('Kod'), 130), ('name', t('Ad'), 250), ('stock', t('Stok'), 100, 'e'),
             ('min', t('Asgari'), 90, 'e'), ('unit', t('Birim'), 80), ('location', t('Konum'), 160),
             ('supplier', t('Tedarikçi'), 170), ('value', t('Stok değeri'), 110, 'e')],
            on_open=lambda row: self.open_dialog(lambda: PartDialog(self.app, row['id'])))
        self.table.pack(fill='both', expand=True)

    def refresh(self) -> None:
        conn = self.app.conn
        rows = PartRepo.query(conn, search=self.search.get().strip(),
                              low_only=self.low_only.get(),
                              active_only=not self.show_passive.get())

        def cells(row):
            return (row['code'], row['name'], _num(row['stock']), _num(row['min_stock']),
                    row['unit'], row['location_text'], row['supplier'],
                    _num(float(row['stock']) * float(row['unit_cost'])))

        def tag(row):
            if not int(row['is_active']):
                return 'muted'
            if float(row['min_stock']) > 0 and float(row['stock']) <= float(row['min_stock']):
                return 'alert'
            return None

        self.table.set_rows(rows, values=cells, tag_of=tag)
        low = PartRepo.count(conn, low_only=True)
        text = t('%d parça') % len(rows)
        if low:
            text += t('  ·  %d düşük stok') % low
        text += t('  ·  stok değeri %s') % _num(PartRepo.stock_value(conn))
        self.count_label.configure(text=text)
        self.set_hint(t('Yedek parça kütüğü boş. Parça ekleyin; iş emri penceresinden kullanım '
                      'işlediğinizde stok kendiliğinden düşer.')
                      if not rows and not self.search.get().strip() else '')


# ====================================================================== raporlar
class ReportsScreen(Screen):
    title = t('Raporlar')
    subtitle = t('Göstergeler seçilen dönemdeki kayıtlardan hesaplanır; tahmin ya da örnekleme yok.')

    def build(self) -> None:
        ttk.Button(self.actions, text=t('Dışa aktar'), style='Accent.TButton',
                   command=self.export).pack(side='right')
        ttk.Button(self.actions, text=t('Yazdırılabilir rapor'),
                   command=self.print_report).pack(side='right', padx=6)

        ttk.Label(self.toolbar, text=t('Dönem'), style='Muted.TLabel').pack(side='left', padx=(0, 6))
        self.period = w.Combo(self.toolbar, reports.PERIODS, width=16,
                              value=store.setting('report_period', '365'))
        self.period.pack(side='left')
        self.period.bind('<<ComboboxSelected>>', lambda _e: self.period_changed())

        area = w.ScrollArea(self.body)
        area.pack(fill='both', expand=True)
        host = area.body

        cards = ttk.Frame(host)
        cards.pack(fill='x', pady=(0, 14))
        self.cards = {}
        for index, (key, label) in enumerate((
                ('compliance', t('Plan uyumu')), ('conformity', t('Kalibrasyon uygunluğu')),
                ('downtime', t('Toplam duruş (saat)')), ('labour', t('Toplam işçilik (saat)')),
                ('parts', t('Düşük stok kalemi')))):
            card = w.Card(cards, label, '—')
            card.grid(row=0, column=index, sticky='nsew', padx=(0 if index == 0 else 8, 0))
            cards.columnconfigure(index, weight=1)
            self.cards[key] = card

        self.detail = ttk.Label(host, text='', style='Muted.TLabel', wraplength=900,
                                justify='left')
        self.detail.pack(anchor='w', pady=(0, 14))

        ttk.Label(host, text=t('Varlık güvenilirliği'), style='Heading.TLabel').pack(anchor='w')
        ttk.Label(host, text=t('MTBF iki arızası olmayan varlıkta hesaplanamaz; o satırda boş kalır. '
                             'Sıfır yazmak yanıltıcı olurdu.'),
                  style='Muted.TLabel').pack(anchor='w', pady=(2, 6))
        self.reliability = w.DataTable(
            host, [('code', t('Kod'), 120), ('name', t('Varlık'), 230), ('failures', t('Arıza'), 70, 'e'),
                   ('mtbf', t('MTBF (saat)'), 110, 'e'), ('mttr', t('MTTR (saat)'), 110, 'e'),
                   ('downtime', t('Duruş (dk)'), 100, 'e')], height=10, autosize=True)
        self.reliability.pack(fill='x')

        ttk.Label(host, text=t('Aya göre duruş ve işçilik'), style='Heading.TLabel').pack(
            anchor='w', pady=(16, 6))
        self.monthly = w.DataTable(
            host, [('month', t('Ay'), 110), ('downtime', t('Duruş (dk)'), 110, 'e'),
                   ('labour', t('İşçilik (dk)'), 110, 'e'), ('orders', t('İş emri'), 90, 'e'),
                   ('bar', '', 300)], height=12, autosize=True)
        self.monthly.pack(fill='x')

        ttk.Label(host, text=t('Geciken planlar'), style='Heading.TLabel').pack(
            anchor='w', pady=(16, 6))
        self.ageing = w.DataTable(
            host, [('asset', t('Varlık'), 220), ('plan', t('Plan'), 250), ('due', t('Vade'), 110),
                   ('days', t('Gecikme (gün)'), 120, 'e')], height=10, autosize=True)
        self.ageing.pack(fill='x')

        ttk.Label(host, text=t('Sapma geçmişi'), style='Heading.TLabel').pack(
            anchor='w', pady=(16, 6))
        picker = ttk.Frame(host)
        picker.pack(fill='x', pady=(0, 6))
        ttk.Label(picker, text=t('Ölçüm cihazı'), style='Muted.TLabel').pack(side='left',
                                                                          padx=(0, 6))
        self.device = w.Combo(picker, [(0, t('- seçin -'))], width=40)
        self.device.pack(side='left')
        self.device.bind('<<ComboboxSelected>>', lambda _e: self.refresh_deviation())
        self.deviation = w.DataTable(
            host, [('at', t('Tarih'), 150), ('deviation', t('En büyük sapma'), 140, 'e'),
                   ('result', t('Sonuç'), 120), ('bar', '', 300)], height=10, autosize=True)
        self.deviation.pack(fill='x', pady=(0, 16))

    def period_changed(self) -> None:
        store.save_settings({'report_period': self.period.key()})
        self.refresh()

    def days(self) -> int:
        return int(self.period.key() or 0)

    def refresh(self) -> None:
        conn = self.app.conn
        days = self.days()
        data = reports.summary(conn, days)

        compliance = data['compliance']
        self.cards['compliance'].set_value(
            ('%%%s' % compliance['rate']) if compliance['rate'] is not None else '—',
            alert=compliance['rate'] is not None and compliance['rate'] < 80)
        conformity = data['conformity']
        self.cards['conformity'].set_value(
            ('%%%s' % conformity['rate']) if conformity['rate'] is not None else '—',
            alert=bool(conformity['counts']['fail']))
        self.cards['downtime'].set_value(round(data['downtime_total'] / 60.0, 1))
        self.cards['labour'].set_value(round(data['labour_total'] / 60.0, 1))
        self.cards['parts'].set_value(data['parts_low'], alert=bool(data['parts_low']))

        self.detail.configure(
            text=t('Plan uyumu: %d iş emrinden %d tanesi zamanında kapandı, %d tanesi geç kaldı, '
                 '%d tanesi hâlâ açık.    Kalibrasyon: %d kayıttan %d uygun, %d şartlı, '
                 '%d uygunsuz.')
                 % (compliance['total'], compliance['on_time'], compliance['late'],
                    compliance['open'], conformity['total'], conformity['counts']['pass'],
                    conformity['counts']['conditional'], conformity['counts']['fail']))

        rows = [item for item in reports.asset_reliability(conn, days) if item['failures']]
        self.reliability.set_rows(
            [{'id': item['asset']['id'], **item} for item in rows],
            values=lambda r: (r['asset']['code'], r['asset']['name'], r['failures'],
                              r['mtbf_hours'] if r['mtbf_hours'] is not None else '—',
                              r['mttr_hours'] if r['mttr_hours'] is not None else '—',
                              r['downtime_minutes']),
            tag_of=lambda r: 'alert' if r['failures'] >= 3 else None)

        downtime = dict((month, (minutes, count))
                        for month, minutes, count in reports.downtime_by_month(conn, days))
        labour = dict((month, (minutes, count))
                      for month, minutes, count in reports.labour_by_month(conn, days))
        months = sorted(set(downtime) | set(labour))
        peak = max([downtime.get(m, (0, 0))[0] for m in months] or [0]) or 1
        self.monthly.set_rows(
            [{'id': m, 'month': m} for m in months],
            values=lambda r: (r['month'], downtime.get(r['month'], (0, 0))[0],
                              labour.get(r['month'], (0, 0))[0],
                              downtime.get(r['month'], (0, 0))[1] or labour.get(r['month'], (0, 0))[1],
                              _bar(downtime.get(r['month'], (0, 0))[0], peak)))

        ageing = reports.overdue_ageing(conn)
        self.ageing.set_rows(
            [{'id': item['plan']['id'], **item} for item in ageing],
            values=lambda r: (AssetRepo.label(conn, int(r['plan']['asset_id'])),
                              r['plan']['title'], v.human(r['plan']['next_due_at']), r['days']),
            tag_of=lambda r: 'alert' if r['days'] > 30 else None)

        devices = [(int(a['id']), AssetRepo.label(conn, int(a['id'])))
                   for a in AssetRepo.query(conn, measuring=True)]
        current = self.device.key()
        self.device.set_pairs(devices or [(0, t('- ölçüm cihazı yok -'))], current)
        self.refresh_deviation()

    def refresh_deviation(self) -> None:
        asset_id = self.device.key()
        if not asset_id:
            self.deviation.set_rows([])
            return
        history = reports.deviation_history(self.app.conn, asset_id)
        peak = max([abs(d) for _at, d, _r in history] or [0]) or 1
        rows = [{'id': '%s-%d' % (at, index), 'at': at, 'deviation': deviation, 'result': result}
                for index, (at, deviation, result) in enumerate(history)]
        self.deviation.set_rows(
            rows,
            values=lambda r: (v.human(r['at'], with_time=True), r['deviation'],
                              CalibrationRepo.RESULTS.get(r['result'], ''),
                              _bar(abs(r['deviation']), peak)),
            tag_of=lambda r: 'alert' if r['result'] == 'fail' else None)

    # ------------------------------------------------------------------ cikti
    def export(self) -> None:
        ExportDialog(self.app, self.days())
        self.app.refresh()

    def print_report(self) -> None:
        target = store.exports_dir() / export.default_name('mihenk-rapor', '.html')
        made = {}

        def build():
            made['path'] = export.to_html(self.app.conn, target, days=self.days())
        if not self.run(build, ''):
            return
        _open_path(made['path'], self)
        self.app.toast(t('Rapor hazırlandı: %s') % made['path'].name)


def _bar(value, peak, width=24) -> str:
    """Metin tabanli cubuk: tabloda ek bir cizim katmani gerektirmez."""
    try:
        filled = int(round(width * float(value) / float(peak)))
    except (TypeError, ValueError, ZeroDivisionError):
        return ''
    filled = max(0, min(width, filled))
    return '█' * filled


def _num(value) -> str:
    try:
        return '%g' % float(value)
    except (TypeError, ValueError):
        return '0'

