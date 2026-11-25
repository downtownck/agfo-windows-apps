# -*- coding: utf-8 -*-
"""Kayit pencereleri: varlik, plan, talep, is emri, kalibrasyon, etki degerlendirmesi."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import mihenk_audit as audit
import mihenk_states as states
import mihenk_theme as theme
import mihenk_validate as v
import mihenk_widgets as w
from mihenk_repo import (AssetRepo, AssetTypes, CalibrationRepo, ImpactRepo, RequestRepo,
                         ScheduleRepo, WorkOrderRepo)


class BaseDialog(tk.Toplevel):
    """Ortak iskelet: baslik serigi, kaydirilabilir govde, alt dugme serigi."""

    width = 820
    height = 640

    def __init__(self, app, title: str):
        super().__init__(app.root)
        self.app = app
        self.conn = app.conn
        self.saved = False
        p = theme.palette()
        self.title(title)
        self.configure(background=p['bg'])
        self.transient(app.root)
        self.resizable(True, True)
        self.minsize(640, 460)

        self.header = ttk.Frame(self, padding=(20, 16, 20, 10))
        self.header.pack(fill='x')
        self.title_label = ttk.Label(self.header, text=title, style='Heading.TLabel')
        self.title_label.pack(side='left')
        self.badge_slot = ttk.Frame(self.header)
        self.badge_slot.pack(side='left', padx=10)

        self.notice = ttk.Label(self, text='', style='Alert.TLabel', wraplength=self.width - 60,
                                justify='left')

        self.area = w.ScrollArea(self)
        self.area.pack(fill='both', expand=True, padx=20)
        self.body = self.area.body

        ttk.Separator(self).pack(fill='x', pady=(10, 0))
        self.footer = ttk.Frame(self, padding=(20, 12))
        self.footer.pack(fill='x')

        self.bind('<Escape>', lambda _e: self.destroy())
        self.protocol('WM_DELETE_WINDOW', self.destroy)

    def show(self) -> None:
        """Pencereyi ana pencerenin ortasina yerlestirip kilitler."""
        self.update_idletasks()
        parent = self.app.root
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.width) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.height) // 3)
        self.geometry('%dx%d+%d+%d' % (self.width, self.height, x, y))
        self.grab_set()
        self.focus_set()

    def set_badge(self, text: str, state: str) -> None:
        for child in self.badge_slot.winfo_children():
            child.destroy()
        w.Badge(self.badge_slot, text, state).pack()

    def warn(self, text: str) -> None:
        """Pencerenin ustunde kalici bir uyari serigi."""
        self.notice.configure(text=text)
        self.notice.pack(fill='x', padx=20, pady=(0, 8), before=self.area)

    def button(self, text: str, command, style='TButton', side='right'):
        btn = ttk.Button(self.footer, text=text, command=command, style=style)
        btn.pack(side=side, padx=(6, 0) if side == 'right' else (0, 6))
        return btn

    def run(self, action, success: str = '') -> bool:
        """Depo cagrisini calistirir; reddedilirse sebebini gosterir."""
        try:
            action()
        except v.MihenkError as exc:
            messagebox.showwarning('Kabul edilmedi', str(exc), parent=self)
            return False
        except Exception as exc:                     # beklenmeyen hata sessizce yutulmaz
            messagebox.showerror('Hata', '%s' % exc, parent=self)
            return False
        self.saved = True
        if success:
            self.app.toast(success)
        return True

    def finish(self, success: str) -> None:
        self.app.refresh()
        self.app.toast(success)
        self.destroy()

    def history(self, entity: str, entity_id: int) -> None:
        """Kaydin denetim gunlugunu govdenin sonuna ekler."""
        rows = audit.for_entity(self.conn, entity, entity_id, limit=30)
        frame = ttk.Frame(self.body)
        frame.pack(fill='both', expand=True, pady=(16, 20))
        ttk.Label(frame, text='Geçmiş', style='Heading.TLabel').pack(anchor='w', pady=(0, 6))
        if not rows:
            ttk.Label(frame, text='Henüz kayıt yok.', style='Muted.TLabel').pack(anchor='w')
            return
        table = w.DataTable(frame, [('created_at', 'Zaman', 140), ('action', 'İşlem', 150),
                                    ('move', 'Geçiş', 200), ('actor', 'Kullanıcı', 120)],
                            height=min(8, len(rows)))
        table.pack(fill='both', expand=True)
        table.set_rows(rows, values=lambda r: (
            v.human(r['created_at'], with_time=True), r['action'],
            ('%s → %s' % (states.label(entity, r['from_state']), states.label(entity, r['to_state'])))
            if r['to_state'] else '', r['actor']))


# ====================================================================== varlik
class AssetDialog(BaseDialog):
    """Varlik kutugu kaydi."""

    def __init__(self, app, asset_id=None):
        self.asset_id = int(asset_id) if asset_id else 0
        self.row = AssetRepo.get(app.conn, self.asset_id) if self.asset_id else None
        super().__init__(app, 'Varlığı düzenle' if self.row else 'Varlık ekle')
        self.attr_widgets = {}

        if self.row:
            self.set_badge(states.label('asset', self.row['status']), self.row['status'])
            if self.row['status'] == 'quarantined':
                self.warn('Bu varlık başarısız bir kalibrasyon sonrası karantinada. Açık her etki '
                          'değerlendirmesi kapanmadan hizmete dönemez.')

        notebook = ttk.Notebook(self.body)
        notebook.pack(fill='both', expand=True, pady=(4, 8))
        general = ttk.Frame(notebook, padding=14)
        attributes = ttk.Frame(notebook, padding=14)
        notebook.add(general, text='Genel')
        notebook.add(attributes, text='Tip özellikleri')
        if self.row:
            lifecycle = ttk.Frame(notebook, padding=14)
            notebook.add(lifecycle, text='Durum ve sayaç')
            self._build_lifecycle(lifecycle)

        self._build_general(general)
        self._build_attributes(attributes)

        if self.row:
            self.history('asset', self.asset_id)
            self.button('Sil', self.delete, style='Danger.TButton', side='left')
        self.button('Kaydet', self.save, style='Accent.TButton')
        self.button('Kapat', self.destroy)
        self.show()

    def _build_general(self, parent) -> None:
        form = w.FormGrid(parent)
        form.pack(fill='both', expand=True)
        row = self.row or {}

        self.code = form.add('Kod', ttk.Entry(form, width=28),
                             'Varlık etiketinde yazan benzersiz tanımlayıcı.')
        self.code.insert(0, row.get('code', ''))
        self.name = form.add('Ad', ttk.Entry(form, width=46))
        self.name.insert(0, row.get('name', ''))

        self.asset_type = form.add('Tip', w.Combo(form, AssetTypes.TYPES,
                                                  value=row.get('asset_type', 'machine')))
        self.asset_type.bind('<<ComboboxSelected>>', lambda _e: self._rebuild_attributes())

        self.measuring = tk.BooleanVar(value=bool(row.get('is_measuring_device', 0)))
        form.add('', ttk.Checkbutton(form, text='Ölçüm cihazı', variable=self.measuring),
                 'Ölçüm cihazları kalibrasyon planı taşır ve etki değerlendirmesi tetikleyebilir.')

        options = [(0, '- yok -')] + AssetRepo.options(self.conn, exclude=self.asset_id)
        self.parent_id = form.add('Üst varlık', w.Combo(form, options, width=40,
                                                        value=row.get('parent_id', 0)))
        self.location = form.add('Konum', ttk.Entry(form, width=46))
        self.location.insert(0, row.get('location_text', ''))

        form.separator('Tanım bilgileri')
        self.manufacturer = form.add('Üretici', ttk.Entry(form, width=36))
        self.manufacturer.insert(0, row.get('manufacturer', ''))
        self.model = form.add('Model', ttk.Entry(form, width=36))
        self.model.insert(0, row.get('model', ''))
        self.serial = form.add('Seri numarası', ttk.Entry(form, width=36))
        self.serial.insert(0, row.get('serial_no', ''))
        self.criticality = form.add('Kritiklik', w.Combo(form, AssetTypes.CRITICALITY, width=20,
                                                         value=row.get('criticality', 2)))
        self.commissioned = form.add('Devreye alma', w.DateEntry(form))
        self.commissioned.set(row.get('commissioned_on'))

        form.separator('Sayaç')
        self.counter_unit = form.add('Sayaç birimi', w.Combo(form, AssetTypes.COUNTER_UNITS, width=22,
                                                             value=row.get('counter_unit', '')),
                                     'Sayaç tabanlı plan bağlayabilmek için gereklidir.')

        form.separator('Notlar')
        self.notes = w.text_box(form, height=4)
        form.add_full(self.notes)
        w.write_text(self.notes, row.get('notes', ''))

    def _build_attributes(self, parent) -> None:
        self.attributes_host = parent
        self._rebuild_attributes()

    def _rebuild_attributes(self) -> None:
        for child in self.attributes_host.winfo_children():
            child.destroy()
        self.attr_widgets = {}
        asset_type = self.asset_type.key()
        definitions = AssetTypes.attributes(asset_type)
        stored = AssetRepo.attributes(self.conn, self.asset_id) if self.asset_id else {}

        if not definitions:
            ttk.Label(self.attributes_host, text='Bu tipin ek özelliği yok.',
                      style='Muted.TLabel').pack(anchor='w')
            return
        ttk.Label(self.attributes_host,
                  text='%s tipinin özellikleri' % AssetTypes.label(asset_type),
                  style='Heading.TLabel').pack(anchor='w', pady=(0, 8))
        form = w.FormGrid(self.attributes_host)
        form.pack(fill='x')
        for definition in definitions:
            key = definition['key']
            if definition['type'] == 'bool':
                var = tk.BooleanVar(value=str(stored.get(key, '0')) == '1')
                form.add(definition['label'], ttk.Checkbutton(form, variable=var))
                self.attr_widgets[key] = var
            else:
                entry = form.add(definition['label'], ttk.Entry(form, width=32))
                entry.insert(0, stored.get(key, ''))
                self.attr_widgets[key] = entry

    def _build_lifecycle(self, parent) -> None:
        row = self.row
        ttk.Label(parent, text='Durum', style='Heading.TLabel').pack(anchor='w')
        open_impacts = ImpactRepo.open_count_for_asset(self.conn, self.asset_id)
        if open_impacts:
            ttk.Label(parent, text='%d etki değerlendirmesi açık.' % open_impacts,
                      style='Alert.TLabel').pack(anchor='w', pady=(4, 0))

        targets = states.next_states('asset', row['status'])
        bar = ttk.Frame(parent)
        bar.pack(fill='x', pady=(8, 4))
        if targets:
            self.transition_choice = w.Combo(bar, [(t, states.label('asset', t)) for t in targets],
                                             width=22)
            self.transition_choice.pack(side='left')
            ttk.Label(bar, text='Gerekçe', style='Muted.TLabel').pack(side='left', padx=(10, 4))
            self.transition_reason = ttk.Entry(bar, width=36)
            self.transition_reason.pack(side='left')
            ttk.Button(bar, text='Durumu değiştir', command=self.change_status).pack(side='left', padx=8)
        else:
            ttk.Label(parent, text='Bu durumdan ileri gidilemez.', style='Muted.TLabel').pack(anchor='w')

        ttk.Separator(parent).pack(fill='x', pady=12)
        ttk.Label(parent, text='Sayaç', style='Heading.TLabel').pack(anchor='w')
        if not row['counter_unit']:
            ttk.Label(parent, text='Bu varlıkta sayaç birimi tanımlı değil.',
                      style='Muted.TLabel').pack(anchor='w', pady=(4, 0))
            return
        line = ttk.Frame(parent)
        line.pack(fill='x', pady=(8, 0))
        self.counter_value = ttk.Entry(line, width=12)
        self.counter_value.insert(0, str(row['counter_value']))
        self.counter_value.pack(side='left')
        ttk.Label(line, text=AssetTypes.COUNTER_UNITS.get(row['counter_unit'], ''),
                  style='Muted.TLabel').pack(side='left', padx=6)
        ttk.Button(line, text='Okumayı kaydet', command=self.record_counter).pack(side='left', padx=8)
        last = v.human(row['counter_read_at'], with_time=True) or 'hiç'
        ttk.Label(parent, text='Son okuma: %s' % last, style='Muted.TLabel').pack(anchor='w', pady=(6, 0))

    def collect(self) -> dict:
        attrs = {}
        for key, widget in self.attr_widgets.items():
            attrs[key] = widget.get() if hasattr(widget, 'get') else ''
        return {
            'code': self.code.get(),
            'name': self.name.get(),
            'asset_type': self.asset_type.key(),
            'is_measuring_device': self.measuring.get(),
            'parent_id': self.parent_id.key(),
            'location_text': self.location.get(),
            'manufacturer': self.manufacturer.get(),
            'model': self.model.get(),
            'serial_no': self.serial.get(),
            'criticality': self.criticality.key(),
            'commissioned_on': self.commissioned.get_raw(),
            'counter_unit': self.counter_unit.key(),
            'notes': w.read_text(self.notes),
            'attr': attrs,
        }

    def save(self) -> None:
        data = self.collect()
        if self.asset_id:
            if self.run(lambda: AssetRepo.update(self.conn, self.asset_id, data)):
                self.finish('Varlık kaydedildi.')
        else:
            holder = {}

            def create():
                holder['id'] = AssetRepo.create(self.conn, data)
            if self.run(create):
                self.finish('Varlık oluşturuldu.')

    def change_status(self) -> None:
        target = self.transition_choice.key()
        reason = self.transition_reason.get()
        if target == 'retired' and not messagebox.askyesno(
                'Onay', 'Bu varlık hurdaya ayrılsın mı? Hurdaya ayrılan varlık geri alınamaz.',
                parent=self):
            return
        if self.run(lambda: AssetRepo.transition(self.conn, self.asset_id, target, reason)):
            self.finish('Varlık durumu değiştirildi.')

    def record_counter(self) -> None:
        value = self.counter_value.get()
        made = {}

        def record():
            made.update(AssetRepo.record_counter(self.conn, self.asset_id, value))
        if self.run(record):
            extra = ''
            if made.get('work_orders') or made.get('calibrations'):
                extra = ' %d kayıt üretildi.' % (made['work_orders'] + made['calibrations'])
            self.finish('Sayaç okuması kaydedildi.' + extra)

    def delete(self) -> None:
        if not messagebox.askyesno('Onay', 'Bu varlık silinsin mi? Bu işlem geri alınamaz.',
                                   parent=self):
            return
        if self.run(lambda: AssetRepo.delete(self.conn, self.asset_id)):
            self.finish('Varlık silindi.')


# ====================================================================== plan
class PlanDialog(BaseDialog):
    """Bakim, kalibrasyon ve dogrulama plani."""

    height = 660

    def __init__(self, app, plan_id=None, asset_id=0):
        self.plan_id = int(plan_id) if plan_id else 0
        self.row = ScheduleRepo.get(app.conn, self.plan_id) if self.plan_id else None
        super().__init__(app, 'Planı düzenle' if self.row else 'Plan ekle')
        row = self.row or {}

        form = w.FormGrid(self.body)
        form.pack(fill='both', expand=True, pady=(4, 10))

        options = AssetRepo.options(self.conn)
        self.asset = form.add('Varlık', w.Combo(form, options or [(0, '- varlık yok -')], width=44,
                                                value=row.get('asset_id', asset_id)))
        self.plan_type = form.add('Plan tipi', w.Combo(form, ScheduleRepo.PLAN_TYPES, width=26,
                                                       value=row.get('plan_type', 'pm')),
                                  'Önleyici plan iş emri üretir. Kalibrasyon ve doğrulama planı '
                                  'kalibrasyon kaydı üretir.')
        self.title_entry = form.add('Başlık', ttk.Entry(form, width=46))
        self.title_entry.insert(0, row.get('title', ''))

        self.basis = form.add('Esas', w.Combo(form, ScheduleRepo.BASES, width=20,
                                              value=row.get('basis', 'time')))
        self.basis.bind('<<ComboboxSelected>>', lambda _e: self._sync_basis())

        interval = ttk.Frame(form)
        self.interval_value = ttk.Entry(interval, width=6)
        self.interval_value.insert(0, str(row.get('interval_value', 1)))
        self.interval_value.pack(side='left')
        self.interval_unit = w.Combo(interval, ScheduleRepo.UNITS, width=10,
                                     value=row.get('interval_unit', 'month'))
        self.interval_unit.pack(side='left', padx=6)
        self.interval_row = form.add('Aralık', interval)

        self.counter_interval = form.add('Sayaç aralığı', ttk.Entry(form, width=10),
                                         'Varlıkta sayaç birimi tanımlı olmalıdır.')
        self.counter_interval.insert(0, str(row.get('counter_interval', 0)))

        window = ttk.Frame(form)
        self.lead_days = ttk.Entry(window, width=6)
        self.lead_days.insert(0, str(row.get('lead_days', 14)))
        self.lead_days.pack(side='left')
        ttk.Label(window, text='gün önce üret', style='Muted.TLabel').pack(side='left', padx=(6, 16))
        self.tolerance_days = ttk.Entry(window, width=6)
        self.tolerance_days.insert(0, str(row.get('tolerance_days', 0)))
        self.tolerance_days.pack(side='left')
        ttk.Label(window, text='gün gecikme tolere edilir', style='Muted.TLabel').pack(side='left', padx=6)
        form.add('Uyarı aralığı', window,
                 'Tolere edilen gecikme yalnızca gecikme raporunu etkiler, vadeyi değiştirmez.')

        self.last_done = form.add('Son yapılma', w.DateEntry(form, with_time=True))
        self.last_done.set(row.get('last_done_at'))
        self.next_due = form.add('Sıradaki vade', w.DateEntry(form, with_time=True),
                                 'Boş bırakılırsa aralıktan hesaplanır.')
        self.next_due.set(row.get('next_due_at'))

        self.assignee = form.add('Varsayılan sorumlu', ttk.Entry(form, width=32))
        self.assignee.insert(0, row.get('assignee', ''))

        self.active = tk.BooleanVar(value=bool(row.get('is_active', 1)))
        form.add('Aktif', ttk.Checkbutton(form, text='Bu plandan kayıt üret', variable=self.active))

        form.separator('Talimatlar')
        self.instructions = w.text_box(form, height=6)
        form.add_full(self.instructions)
        w.write_text(self.instructions, row.get('instructions', ''))

        self._sync_basis()

        if self.row:
            self.history('schedule', self.plan_id)
            self.button('Sil', self.delete, style='Danger.TButton', side='left')
        self.button('Kaydet', self.save, style='Accent.TButton')
        self.button('Kapat', self.destroy)
        self.show()

    def _sync_basis(self) -> None:
        counter = self.basis.key() == 'counter'
        for widget in (self.counter_interval,):
            widget.configure(state='normal' if counter else 'disabled')
        for widget in (self.interval_value, self.interval_unit):
            widget.configure(state='normal' if not counter else 'disabled')
        if counter:
            self.interval_unit.configure(state='disabled')

    def collect(self) -> dict:
        return {
            'asset_id': self.asset.key(),
            'plan_type': self.plan_type.key(),
            'title': self.title_entry.get(),
            'basis': self.basis.key(),
            'interval_value': self.interval_value.get() or 1,
            'interval_unit': self.interval_unit.key(),
            'counter_interval': self.counter_interval.get() or 0,
            'lead_days': self.lead_days.get() or 0,
            'tolerance_days': self.tolerance_days.get() or 0,
            'assignee': self.assignee.get(),
            'is_active': self.active.get(),
            'instructions': w.read_text(self.instructions),
            'last_done_at': self.last_done.get_raw(),
            'next_due_at': self.next_due.get_raw(),
        }

    def save(self) -> None:
        data = self.collect()
        if self.plan_id:
            if self.run(lambda: ScheduleRepo.update(self.conn, self.plan_id, data)):
                self.finish('Plan kaydedildi.')
        elif self.run(lambda: ScheduleRepo.create(self.conn, data)):
            self.finish('Plan oluşturuldu.')

    def delete(self) -> None:
        if not messagebox.askyesno('Onay', 'Bu plan silinsin mi? Üretilmiş kayıtlar kalır.',
                                   parent=self):
            return
        if self.run(lambda: ScheduleRepo.delete(self.conn, self.plan_id)):
            self.finish('Plan silindi.')


# ====================================================================== talep
class RequestDialog(BaseDialog):
    """Arizanin sahadan bildirildigi kisa form."""

    width = 680
    height = 480

    def __init__(self, app, asset_id=0):
        super().__init__(app, 'Arıza bildir')
        form = w.FormGrid(self.body)
        form.pack(fill='both', expand=True, pady=(4, 10))

        options = AssetRepo.options(self.conn)
        self.asset = form.add('Varlık', w.Combo(form, options or [(0, '- varlık yok -')], width=44,
                                                value=asset_id))
        self.summary = form.add('Özet', ttk.Entry(form, width=46), 'Sorun nedir?')
        self.severity = form.add('Önem', w.Combo(form, RequestRepo.SEVERITIES, width=26,
                                                 value='normal'))
        form.separator('Açıklama')
        self.description = w.text_box(form, height=7)
        form.add_full(self.description)

        self.button('Kaydet', self.save, style='Accent.TButton')
        self.button('Kapat', self.destroy)
        self.show()

    def save(self) -> None:
        data = {
            'asset_id': self.asset.key(),
            'summary': self.summary.get(),
            'severity': self.severity.key(),
            'description': w.read_text(self.description),
        }
        if self.run(lambda: RequestRepo.create(self.conn, data)):
            self.finish('Talep kaydedildi.')


# ====================================================================== is emri
class WorkOrderDialog(BaseDialog):
    """Is emri kaydi ve durum gecisleri."""

    height = 700

    def __init__(self, app, work_order_id=None, asset_id=0):
        self.work_order_id = int(work_order_id) if work_order_id else 0
        self.row = WorkOrderRepo.get(app.conn, self.work_order_id) if self.work_order_id else None
        super().__init__(app, ('İş emri #%d' % self.work_order_id) if self.row else 'İş emri ekle')
        row = self.row or {}
        self.locked = bool(row) and row['status'] in ('closed', 'cancelled')

        if self.row:
            self.set_badge(states.label('work_order', row['status']), row['status'])
            if int(row['schedule_id']):
                plan = ScheduleRepo.get(self.conn, int(row['schedule_id']))
                if plan:
                    ttk.Label(self.body, text='Plandan üretildi: %s' % plan['title'],
                              style='Muted.TLabel').pack(anchor='w', pady=(4, 0))

        form = w.FormGrid(self.body)
        form.pack(fill='x', pady=(6, 10))
        options = AssetRepo.options(self.conn)
        self.asset = form.add('Varlık', w.Combo(form, options or [(0, '- varlık yok -')], width=44,
                                                value=row.get('asset_id', asset_id)))
        self.title_entry = form.add('Başlık', ttk.Entry(form, width=46))
        self.title_entry.insert(0, row.get('title', ''))

        classification = ttk.Frame(form)
        self.wo_type = w.Combo(classification, WorkOrderRepo.TYPES, width=16,
                               value=row.get('wo_type', 'corrective'))
        self.wo_type.pack(side='left')
        self.priority = w.Combo(classification, WorkOrderRepo.PRIORITIES, width=12,
                                value=row.get('priority', 'normal'))
        self.priority.pack(side='left', padx=6)
        self.assigned_to = ttk.Entry(classification, width=20)
        self.assigned_to.insert(0, row.get('assigned_to', ''))
        self.assigned_to.pack(side='left', padx=6)
        form.add('Sınıflandırma', classification)

        planned = ttk.Frame(form)
        self.planned_start = w.DateEntry(planned, with_time=True, width=16)
        self.planned_start.pack(side='left')
        self.planned_end = w.DateEntry(planned, with_time=True, width=16)
        self.planned_end.pack(side='left', padx=(10, 0))
        form.add('Planlanan', planned)
        self.planned_start.set(row.get('planned_start'))
        self.planned_end.set(row.get('planned_end'))

        actual = ttk.Frame(form)
        self.actual_start = w.DateEntry(actual, with_time=True, width=16)
        self.actual_start.pack(side='left')
        self.actual_end = w.DateEntry(actual, with_time=True, width=16)
        self.actual_end.pack(side='left', padx=(10, 0))
        form.add('Gerçekleşen', actual)
        self.actual_start.set(row.get('actual_start'))
        self.actual_end.set(row.get('actual_end'))

        effort = ttk.Frame(form)
        self.labor = ttk.Entry(effort, width=7)
        self.labor.insert(0, str(row.get('labor_minutes', 0)))
        self.labor.pack(side='left')
        ttk.Label(effort, text='dk işçilik', style='Muted.TLabel').pack(side='left', padx=(5, 14))
        self.downtime = ttk.Entry(effort, width=7)
        self.downtime.insert(0, str(row.get('downtime_minutes', 0)))
        self.downtime.pack(side='left')
        ttk.Label(effort, text='dk duruş', style='Muted.TLabel').pack(side='left', padx=5)
        form.add('Efor', effort)

        form.separator('Yapılan iş')
        self.work_done = w.text_box(form, height=5)
        form.add_full(self.work_done)
        w.write_text(self.work_done, row.get('work_done', ''))
        form.separator('Kök neden')
        self.root_cause = w.text_box(form, height=3)
        form.add_full(self.root_cause)
        w.write_text(self.root_cause, row.get('root_cause', ''))

        if row.get('hold_reason'):
            ttk.Label(self.body, text='Bekletme gerekçesi: %s' % row['hold_reason'],
                      style='Muted.TLabel', wraplength=700, justify='left').pack(anchor='w')

        if self.locked:
            for widget in (self.asset, self.title_entry, self.wo_type, self.priority,
                           self.assigned_to, self.labor, self.downtime):
                widget.configure(state='disabled')
            self.work_done.configure(state='disabled')
            self.root_cause.configure(state='disabled')
            ttk.Label(self.body, text='Bu iş emri kapalı ve artık düzenlenemez.',
                      style='Muted.TLabel').pack(anchor='w', pady=(6, 0))

        if self.row:
            self._build_transitions()
            self.history('work_order', self.work_order_id)
        if not self.locked:
            self.button('Kaydet', self.save, style='Accent.TButton')
        self.button('Kapat', self.destroy)
        self.show()

    def _build_transitions(self) -> None:
        targets = states.next_states('work_order', self.row['status'])
        if not targets:
            return
        frame = ttk.Frame(self.body)
        frame.pack(fill='x', pady=(14, 4))
        ttk.Label(frame, text='Sonraki duruma geç', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(frame, text='Bir plandan gelen iş emrini tamamlamak, o planı sıradaki vadesine '
                             'ilerletir.', style='Muted.TLabel', wraplength=720,
                  justify='left').pack(anchor='w', pady=(2, 8))
        bar = ttk.Frame(frame)
        bar.pack(fill='x')
        for target in targets:
            needs = states.required_fields('work_order', target)
            text = states.label('work_order', target)
            if needs:
                text += ' (%s)' % ', '.join(needs.values())
            ttk.Button(bar, text=text, command=lambda t=target: self.transition(t)).pack(
                side='left', padx=(0, 6), pady=2)

    def collect(self) -> dict:
        return {
            'asset_id': self.asset.key(),
            'schedule_id': (self.row or {}).get('schedule_id', 0),
            'request_id': (self.row or {}).get('request_id', 0),
            'title': self.title_entry.get(),
            'wo_type': self.wo_type.key(),
            'priority': self.priority.key(),
            'assigned_to': self.assigned_to.get(),
            'planned_start': self.planned_start.get_raw(),
            'planned_end': self.planned_end.get_raw(),
            'actual_start': self.actual_start.get_raw(),
            'actual_end': self.actual_end.get_raw(),
            'labor_minutes': self.labor.get() or 0,
            'downtime_minutes': self.downtime.get() or 0,
            'work_done': w.read_text(self.work_done),
            'root_cause': w.read_text(self.root_cause),
            'hold_reason': (self.row or {}).get('hold_reason', ''),
        }

    def save(self) -> None:
        data = self.collect()
        if self.work_order_id:
            if self.run(lambda: WorkOrderRepo.update(self.conn, self.work_order_id, data)):
                self.finish('İş emri kaydedildi.')
        elif self.run(lambda: WorkOrderRepo.create(self.conn, data)):
            self.finish('İş emri oluşturuldu.')

    def transition(self, target: str) -> None:
        """Gecis once formdaki degerlerle denenir; eksik alan varsa sorulur."""
        data = self.collect()
        if target == 'on_hold':
            reason = _ask_text(self, 'Bekletme gerekçesi', 'Neden bekletiliyor?')
            if reason is None:
                return
            data['hold_reason'] = reason
        if self.work_order_id and not self.locked:
            try:
                WorkOrderRepo.update(self.conn, self.work_order_id, data)
            except v.MihenkError:
                pass                       # kaydedilemeyen alanlar gecisi engellemesin
        if self.run(lambda: WorkOrderRepo.transition(self.conn, self.work_order_id, target, data)):
            self.finish('İş emri %s durumuna alındı.' % states.label('work_order', target).lower())


# ====================================================================== kalibrasyon
class PointsGrid(ttk.Frame):
    """Olcum noktasi tablosu: sapma canli hesaplanir ve renklenir."""

    COLUMNS = ('Etiket', 'Nominal', 'Ölçülen', 'Tolerans (±)', 'Birim', 'Sapma', '')

    def __init__(self, parent, points=None, readonly=False):
        super().__init__(parent)
        self.readonly = readonly
        self.rows = []
        for index, title in enumerate(self.COLUMNS):
            ttk.Label(self, text=title, style='Muted.TLabel').grid(row=0, column=index, sticky='w',
                                                                   padx=3, pady=(0, 4))
        for point in (points or [{}]):
            self.add_row(point)
        if not readonly:
            self.add_button = ttk.Button(self, text='Nokta ekle', style='Ghost.TButton',
                                         command=lambda: self.add_row({}))
            self._place_add_button()

    def _place_add_button(self) -> None:
        self.add_button.grid(row=len(self.rows) + 1, column=0, sticky='w', pady=(6, 0))

    def add_row(self, point: dict) -> None:
        index = len(self.rows) + 1
        state = 'disabled' if self.readonly else 'normal'
        label = ttk.Entry(self, width=18)
        label.insert(0, point.get('label', '') or '')
        nominal = ttk.Entry(self, width=10)
        nominal.insert(0, _fmt(point.get('nominal')))
        measured = ttk.Entry(self, width=10)
        measured.insert(0, _fmt(point.get('measured')))
        tolerance = ttk.Entry(self, width=10)
        tolerance.insert(0, _fmt(point.get('tolerance')))
        unit = ttk.Entry(self, width=8)
        unit.insert(0, point.get('unit', '') or '')
        deviation = ttk.Label(self, text='', width=12, style='Muted.TLabel')

        widgets = (label, nominal, measured, tolerance, unit)
        for column, widget in enumerate(widgets):
            widget.grid(row=index, column=column, padx=3, pady=2, sticky='w')
            widget.configure(state=state)
        deviation.grid(row=index, column=5, padx=3, sticky='w')

        entry = {'label': label, 'nominal': nominal, 'measured': measured,
                 'tolerance': tolerance, 'unit': unit, 'deviation': deviation, 'index': index}
        if not self.readonly:
            remove = ttk.Button(self, text='Kaldır', style='Ghost.TButton', width=7,
                                command=lambda e=entry: self.remove_row(e))
            remove.grid(row=index, column=6, padx=3)
            entry['remove'] = remove
            for widget in (nominal, measured, tolerance):
                widget.bind('<KeyRelease>', lambda _e, item=entry: self.update_row(item))
        self.rows.append(entry)
        self.update_row(entry)
        if not self.readonly and hasattr(self, 'add_button'):
            self._place_add_button()

    def remove_row(self, entry: dict) -> None:
        if len(self.rows) <= 1:
            for key in ('label', 'nominal', 'measured', 'tolerance', 'unit'):
                entry[key].delete(0, 'end')
            self.update_row(entry)
            return
        for key in ('label', 'nominal', 'measured', 'tolerance', 'unit', 'deviation', 'remove'):
            if key in entry:
                entry[key].destroy()
        self.rows.remove(entry)
        self._place_add_button()

    def update_row(self, entry: dict) -> None:
        nominal = v.number(entry['nominal'].get())
        measured = v.number(entry['measured'].get())
        tolerance = v.number(entry['tolerance'].get())
        if nominal is None or measured is None:
            entry['deviation'].configure(text='', foreground=theme.color('muted'))
            return
        deviation = round(measured - nominal, 6)
        text = ('+%g' % deviation) if deviation > 0 else ('%g' % deviation)
        color = theme.color('muted')
        if tolerance is not None:
            color = theme.color('ok') if abs(deviation) <= abs(tolerance) else theme.color('alert')
        entry['deviation'].configure(text=text, foreground=color)

    def collect(self) -> list:
        out = []
        for entry in self.rows:
            out.append({
                'label': entry['label'].get(),
                'nominal': entry['nominal'].get(),
                'measured': entry['measured'].get(),
                'tolerance': entry['tolerance'].get(),
                'unit': entry['unit'].get(),
            })
        return out


def _fmt(value) -> str:
    if value is None or value == '':
        return ''
    return ('%g' % value) if isinstance(value, (int, float)) else str(value)


class CalibrationDialog(BaseDialog):
    """Kalibrasyon ve dogrulama kaydi."""

    width = 900
    height = 720

    def __init__(self, app, record_id):
        self.record_id = int(record_id)
        self.row = CalibrationRepo.get(app.conn, self.record_id)
        kind = CalibrationRepo.RECORD_TYPES.get(self.row['record_type'], 'Kalibrasyon')
        super().__init__(app, '%s kaydı #%d' % (kind, self.record_id))
        row = self.row
        self.locked = row['status'] in ('closed', 'cancelled')
        self.set_badge(states.label('calibration', row['status']), row['status'])

        ttk.Label(self.body, text=AssetRepo.label(self.conn, int(row['asset_id'])),
                  style='Muted.TLabel').pack(anchor='w', pady=(4, 0))

        if row['result'] == 'fail':
            self.warn('Bu kayıt uygunsuz. Varlık otomatik karantinaya alındı ve bir etki '
                      'değerlendirmesi açıldı.')

        form = w.FormGrid(self.body)
        form.pack(fill='x', pady=(8, 6))
        self.performed_at = form.add('Yapılma zamanı', w.DateEntry(form, with_time=True))
        self.performed_at.set(row['performed_at'])
        self.performed_by = form.add('Yapan', ttk.Entry(form, width=32))
        self.performed_by.insert(0, row['performed_by'])

        external = ttk.Frame(form)
        self.external_body = ttk.Entry(external, width=26)
        self.external_body.insert(0, row['external_body'])
        self.external_body.pack(side='left')
        self.accreditation = ttk.Entry(external, width=30)
        self.accreditation.insert(0, row['accreditation_scope'])
        self.accreditation.pack(side='left', padx=6)
        form.add('Dış kuruluş / kapsam', external)

        certificate = ttk.Frame(form)
        self.certificate_no = ttk.Entry(certificate, width=22)
        self.certificate_no.insert(0, row['certificate_no'])
        self.certificate_no.pack(side='left')
        self.certificate_path = ttk.Entry(certificate, width=34)
        self.certificate_path.insert(0, row['certificate_path'])
        self.certificate_path.pack(side='left', padx=6)
        ttk.Button(certificate, text='Dosya…', style='Ghost.TButton',
                   command=self.pick_certificate).pack(side='left')
        form.add('Sertifika', certificate, 'Sertifika dosyasının bilgisayardaki yolu saklanır.')

        self.traceability = form.add('İzlenebilirlik referansı', ttk.Entry(form, width=46))
        self.traceability.insert(0, row['traceability_ref'])

        spec = ttk.Frame(form)
        self.tolerance_spec = ttk.Entry(spec, width=30)
        self.tolerance_spec.insert(0, row['tolerance_spec'])
        self.tolerance_spec.pack(side='left')
        self.uncertainty = ttk.Entry(spec, width=20)
        self.uncertainty.insert(0, row['uncertainty'])
        self.uncertainty.pack(side='left', padx=6)
        form.add('Tolerans / belirsizlik', spec)

        ttk.Label(self.body, text='Ölçüm noktaları', style='Heading.TLabel').pack(anchor='w',
                                                                                   pady=(10, 2))
        ttk.Label(self.body, text='Toleransı girilmemiş bir nokta tek başına uygunluğu kanıtlamaz. '
                                 'Tolerans dışındaki tek bir nokta kaydın tamamını uygunsuz yapar.',
                  style='Muted.TLabel', wraplength=820, justify='left').pack(anchor='w', pady=(0, 6))
        self.points = PointsGrid(self.body, CalibrationRepo.points(row), readonly=self.locked)
        self.points.pack(anchor='w', pady=(0, 10))

        result_form = w.FormGrid(self.body)
        result_form.pack(fill='x')
        self.result = result_form.add(
            'Sonuç', w.Combo(result_form, [('', '- noktalardan türet -')] +
                             list(CalibrationRepo.RESULTS.items()), width=26, value=row['result']),
            'Uygunsuz seçmek varlığı karantinaya alır ve etki değerlendirmesi açar.')
        result_form.separator('Kullanım sınırlaması')
        self.usage_limit = w.text_box(result_form, height=3)
        result_form.add_full(self.usage_limit)
        w.write_text(self.usage_limit, row['usage_limit'])
        result_form.add_full(ttk.Label(result_form,
                                       text='Şartlı bir sonucun kapatılabilmesi için zorunludur.',
                                       style='Muted.TLabel'))
        result_form.separator('Notlar')
        self.notes = w.text_box(result_form, height=4)
        result_form.add_full(self.notes)
        w.write_text(self.notes, row['notes'])

        if self.locked:
            for widget in (self.performed_by, self.external_body, self.accreditation,
                           self.certificate_no, self.certificate_path, self.traceability,
                           self.tolerance_spec, self.uncertainty, self.result):
                widget.configure(state='disabled')
            self.usage_limit.configure(state='disabled')
            self.notes.configure(state='disabled')

        self._build_transitions()
        self.history('calibration', self.record_id)

        if int(row['impact_id']):
            self.button('Etki değerlendirmesi', self.open_impact, side='left')
        if not self.locked:
            self.button('Sonucu kaydet', self.save, style='Accent.TButton')
        self.button('Kapat', self.destroy)
        self.show()

    def _build_transitions(self) -> None:
        targets = states.next_states('calibration', self.row['status'])
        if not targets:
            return
        frame = ttk.Frame(self.body)
        frame.pack(fill='x', pady=(14, 4))
        ttk.Label(frame, text='Sonraki duruma geç', style='Heading.TLabel').pack(anchor='w')
        bar = ttk.Frame(frame)
        bar.pack(fill='x', pady=(6, 0))
        for target in targets:
            ttk.Button(bar, text=states.label('calibration', target),
                       command=lambda t=target: self.transition(t)).pack(side='left', padx=(0, 6))
        if 'closed' in targets and self.row['result'] == 'fail':
            ttk.Label(frame, text='Kapatma, etki değerlendirmesi kapanana kadar engelli.',
                      style='Muted.TLabel').pack(anchor='w', pady=(6, 0))

    def pick_certificate(self) -> None:
        path = filedialog.askopenfilename(parent=self, title='Sertifika dosyası',
                                          filetypes=[('PDF', '*.pdf'), ('Tüm dosyalar', '*.*')])
        if path:
            self.certificate_path.delete(0, 'end')
            self.certificate_path.insert(0, path)

    def collect(self) -> dict:
        return {
            'performed_at': self.performed_at.get_raw(),
            'performed_by': self.performed_by.get(),
            'external_body': self.external_body.get(),
            'accreditation_scope': self.accreditation.get(),
            'certificate_no': self.certificate_no.get(),
            'certificate_path': self.certificate_path.get(),
            'traceability_ref': self.traceability.get(),
            'tolerance_spec': self.tolerance_spec.get(),
            'uncertainty': self.uncertainty.get(),
            'result': self.result.key() or '',
            'usage_limit': w.read_text(self.usage_limit),
            'notes': w.read_text(self.notes),
            'points': self.points.collect(),
        }

    def save(self) -> None:
        data = self.collect()
        derived = v.evaluate_points(v.measurement_points(data['points']))
        if (data['result'] or derived['verdict']) == 'fail' and not messagebox.askyesno(
                'Uygunsuz sonuç',
                'Bu sonuç uygunsuz. Varlık karantinaya alınacak ve etki değerlendirmesi açılacak.\n\n'
                'Devam edilsin mi?', parent=self):
            return
        if self.run(lambda: CalibrationRepo.save_result(self.conn, self.record_id, data)):
            self.finish('Sonuç kaydedildi.')

    def transition(self, target: str) -> None:
        if self.run(lambda: CalibrationRepo.transition(self.conn, self.record_id, target)):
            self.finish('Kayıt %s durumuna alındı.' % states.label('calibration', target).lower())

    def open_impact(self) -> None:
        impact_id = int(self.row['impact_id'])
        self.destroy()
        ImpactDialog(self.app, impact_id)


# ====================================================================== etki degerlendirmesi
class ImpactDialog(BaseDialog):
    """Etki degerlendirmesi."""

    width = 860
    height = 700

    def __init__(self, app, impact_id):
        self.impact_id = int(impact_id)
        self.row = ImpactRepo.get(app.conn, self.impact_id)
        super().__init__(app, 'Etki değerlendirmesi #%d' % self.impact_id)
        row = self.row
        self.closed = row['status'] == 'closed'
        self.set_badge(states.label('impact', row['status']), row['status'])

        asset_label = AssetRepo.label(self.conn, int(row['asset_id']))
        self.warn('%s tolerans dışında ölçüm yaptı. %s ile %s arasında ölçtüğü her şey, bu '
                  'değerlendirme bir karara bağlanana kadar şüphelidir.'
                  % (asset_label, v.human(row['affected_from'], with_time=True) or '?',
                     v.human(row['affected_to'], with_time=True) or '?'))

        record = CalibrationRepo.get(self.conn, int(row['calibration_id'])) if row['calibration_id'] else None
        if record:
            line = ttk.Frame(self.body)
            line.pack(fill='x', pady=(4, 0))
            ttk.Label(line, text='Kaynak kayıt #%d' % record['id'], style='Muted.TLabel').pack(side='left')
            if record['max_deviation'] is not None:
                ttk.Label(line, text='   En büyük sapma: %g' % record['max_deviation'],
                          style='Muted.TLabel').pack(side='left')

        form = w.FormGrid(self.body)
        form.pack(fill='x', pady=(10, 6))
        window = ttk.Frame(form)
        self.affected_from = w.DateEntry(window, with_time=True, width=16)
        self.affected_from.pack(side='left')
        self.affected_to = w.DateEntry(window, with_time=True, width=16)
        self.affected_to.pack(side='left', padx=(10, 0))
        form.add('Etkilenen aralık', window,
                 'Uygunluğu gerçekten kanıtlayan son kayda göre dolduruldu. Yalnızca kanıtla daraltın.')
        self.affected_from.set(row['affected_from'])
        self.affected_to.set(row['affected_to'])

        form.separator('Etkilenen kapsam')
        self.scope = w.text_box(form, height=4)
        form.add_full(self.scope)
        w.write_text(self.scope, row['affected_scope'])
        ttk.Label(self.body, text='Bu aralıkta hangi hatlar, ürünler ve partiler bu cihazdan geçti.',
                  style='Muted.TLabel').pack(anchor='w')

        form2 = w.FormGrid(self.body)
        form2.pack(fill='x')
        form2.separator('Değerlendirme')
        self.evaluation = w.text_box(form2, height=6)
        form2.add_full(self.evaluation)
        w.write_text(self.evaluation, row['evaluation'])
        self.decision = form2.add('Karar', w.Combo(form2, [('', '- seçin -')] +
                                                   list(ImpactRepo.DECISIONS.items()), width=30,
                                                   value=row['decision']))
        form2.separator('Düzeltici faaliyet')
        self.corrective = w.text_box(form2, height=4)
        form2.add_full(self.corrective)
        w.write_text(self.corrective, row['corrective_action'])

        if self.closed:
            for widget in (self.decision,):
                widget.configure(state='disabled')
            for box in (self.scope, self.evaluation, self.corrective):
                box.configure(state='disabled')
            ttk.Label(self.body, text='%s tarihinde %s tarafından kapatıldı.'
                      % (v.human(row['closed_at'], with_time=True), row['closed_by'] or '—'),
                      style='Muted.TLabel').pack(anchor='w', pady=(8, 0))

        self.history('impact', self.impact_id)

        if not self.closed:
            self.button('Değerlendirmeyi kapat', self.close_assessment, style='Accent.TButton')
            self.button('Taslağı kaydet', self.save_draft)
        self.button('Kapat', self.destroy)
        self.show()

    def collect(self) -> dict:
        return {
            'affected_from': self.affected_from.get_raw(),
            'affected_to': self.affected_to.get_raw(),
            'affected_scope': w.read_text(self.scope),
            'evaluation': w.read_text(self.evaluation),
            'decision': self.decision.key() or '',
            'corrective_action': w.read_text(self.corrective),
        }

    def save_draft(self) -> None:
        if self.run(lambda: ImpactRepo.save(self.conn, self.impact_id, self.collect())):
            self.finish('Etki değerlendirmesi kaydedildi.')

    def close_assessment(self) -> None:
        if not messagebox.askyesno('Onay', 'Değerlendirme kapatılsın mı? Kapatma varlığı '
                                           'karantinadan çıkarır ve kayıt düzenlenemez olur.',
                                   parent=self):
            return
        if self.run(lambda: ImpactRepo.close(self.conn, self.impact_id, self.collect())):
            self.finish('Etki değerlendirmesi kapatıldı.')


# ====================================================================== yardimci
def _ask_text(parent, title: str, prompt: str):
    """Tek satirlik metin soran kucuk pencere. Iptal edilirse None doner."""
    box = tk.Toplevel(parent)
    box.title(title)
    box.transient(parent)
    box.configure(background=theme.color('bg'))
    box.resizable(False, False)
    ttk.Label(box, text=prompt).pack(anchor='w', padx=16, pady=(14, 6))
    var = tk.StringVar()
    entry = ttk.Entry(box, textvariable=var, width=46)
    entry.pack(padx=16)
    entry.focus_set()
    answer = {}

    def accept():
        answer['value'] = var.get().strip()
        box.destroy()

    bar = ttk.Frame(box, padding=(16, 12))
    bar.pack(fill='x')
    ttk.Button(bar, text='Tamam', style='Accent.TButton', command=accept).pack(side='right')
    ttk.Button(bar, text='Vazgeç', command=box.destroy).pack(side='right', padx=6)
    box.bind('<Return>', lambda _e: accept())
    box.bind('<Escape>', lambda _e: box.destroy())
    box.update_idletasks()
    box.geometry('+%d+%d' % (parent.winfo_rootx() + 60, parent.winfo_rooty() + 80))
    box.grab_set()
    parent.wait_window(box)
    return answer.get('value')
