# -*- coding: utf-8 -*-
"""Kayit pencereleri: varlik, plan, talep, is emri, kalibrasyon, etki degerlendirmesi."""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import mihenk_audit as audit
import mihenk_export as export
import mihenk_states as states
import mihenk_store as store
import mihenk_theme as theme
import mihenk_validate as v
import mihenk_widgets as w
from mihenk_checklist import STATES as CHECK_STATES
from mihenk_checklist import ChecklistTemplate, WorkOrderChecklist
from mihenk_parts import REASONS as PART_REASONS
from mihenk_parts import UNITS as PART_UNITS
from mihenk_parts import PartRepo
from mihenk_repo import (AssetRepo, AssetTypes, CalibrationRepo, ImpactRepo, RequestRepo,
                         ScheduleRepo, WorkOrderRepo)
import mihenk_i18n as i18n
import mihenk_legal as legal
from mihenk_i18n import t


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
        """Pencereyi ana pencerenin ortasina yerlestirip kilitler.

        Istenen boyut ekrana sigmiyorsa kirpilir; kucuk ekranda dugme serigi
        gorunmez olmasin.
        """
        self.update_idletasks()
        parent = self.app.root
        width = min(self.width, max(560, parent.winfo_screenwidth() - 80))
        height = min(self.height, max(420, parent.winfo_screenheight() - 90))
        x = max(0, parent.winfo_rootx() + (parent.winfo_width() - width) // 2)
        y = max(0, parent.winfo_rooty() + (parent.winfo_height() - height) // 3)
        self.geometry('%dx%d+%d+%d' % (width, height, x, y))
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
            messagebox.showwarning(t('Kabul edilmedi'), str(exc), parent=self)
            return False
        except Exception as exc:                     # beklenmeyen hata sessizce yutulmaz
            messagebox.showerror(t('Hata'), '%s' % exc, parent=self)
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
        ttk.Label(frame, text=t('Geçmiş'), style='Heading.TLabel').pack(anchor='w', pady=(0, 6))
        if not rows:
            ttk.Label(frame, text=t('Henüz kayıt yok.'), style='Muted.TLabel').pack(anchor='w')
            return
        table = w.DataTable(frame, [('created_at', t('Zaman'), 140), ('action', t('İşlem'), 150),
                                    ('move', t('Geçiş'), 200), ('actor', t('Kullanıcı'), 120)],
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
        super().__init__(app, t('Varlığı düzenle') if self.row else t('Varlık ekle'))
        self.attr_widgets = {}

        if self.row:
            self.set_badge(states.label('asset', self.row['status']), self.row['status'])
            if self.row['status'] == 'quarantined':
                self.warn(t('Bu varlık başarısız bir kalibrasyon sonrası karantinada. Açık her etki '
                          'değerlendirmesi kapanmadan hizmete dönemez.'))

        notebook = ttk.Notebook(self.body)
        notebook.pack(fill='both', expand=True, pady=(4, 8))
        general = ttk.Frame(notebook, padding=14)
        attributes = ttk.Frame(notebook, padding=14)
        notebook.add(general, text='Genel')
        notebook.add(attributes, text=t('Tip özellikleri'))
        if self.row:
            lifecycle = ttk.Frame(notebook, padding=14)
            notebook.add(lifecycle, text=t('Durum ve sayaç'))
            self._build_lifecycle(lifecycle)

        self._build_general(general)
        self._build_attributes(attributes)

        if self.row:
            self.history('asset', self.asset_id)
            self.button(t('Sil'), self.delete, style='Danger.TButton', side='left')
        self.button(t('Kaydet'), self.save, style='Accent.TButton')
        self.button(t('Kapat'), self.destroy)
        self.show()

    def _build_general(self, parent) -> None:
        form = w.FormGrid(parent)
        form.pack(fill='both', expand=True)
        row = self.row or {}

        self.code = form.add(t('Kod'), ttk.Entry(form, width=28),
                             t('Varlık etiketinde yazan benzersiz tanımlayıcı.'))
        self.code.insert(0, row.get('code', ''))
        self.name = form.add(t('Ad'), ttk.Entry(form, width=46))
        self.name.insert(0, row.get('name', ''))

        self.asset_type = form.add(t('Tip'), w.Combo(form, AssetTypes.TYPES,
                                                  value=row.get('asset_type', 'machine')))
        self.asset_type.bind('<<ComboboxSelected>>', lambda _e: self._rebuild_attributes())

        self.measuring = tk.BooleanVar(value=bool(row.get('is_measuring_device', 0)))
        form.add('', ttk.Checkbutton(form, text=t('Ölçüm cihazı'), variable=self.measuring),
                 t('Ölçüm cihazları kalibrasyon planı taşır ve etki değerlendirmesi tetikleyebilir.'))

        options = [(0, t('- yok -'))] + AssetRepo.options(self.conn, exclude=self.asset_id)
        self.parent_id = form.add(t('Üst varlık'), w.Combo(form, options, width=40,
                                                        value=row.get('parent_id', 0)))
        self.location = form.add(t('Konum'), ttk.Entry(form, width=46))
        self.location.insert(0, row.get('location_text', ''))

        form.separator(t('Tanım bilgileri'))
        self.manufacturer = form.add(t('Üretici'), ttk.Entry(form, width=36))
        self.manufacturer.insert(0, row.get('manufacturer', ''))
        self.model = form.add(t('Model'), ttk.Entry(form, width=36))
        self.model.insert(0, row.get('model', ''))
        self.serial = form.add(t('Seri numarası'), ttk.Entry(form, width=36))
        self.serial.insert(0, row.get('serial_no', ''))
        self.criticality = form.add(t('Kritiklik'), w.Combo(form, AssetTypes.CRITICALITY, width=20,
                                                         value=row.get('criticality', 2)))
        self.commissioned = form.add(t('Devreye alma'), w.DateEntry(form))
        self.commissioned.set(row.get('commissioned_on'))

        form.separator(t('Sayaç'))
        self.counter_unit = form.add(t('Sayaç birimi'), w.Combo(form, AssetTypes.COUNTER_UNITS, width=22,
                                                             value=row.get('counter_unit', '')),
                                     t('Sayaç tabanlı plan bağlayabilmek için gereklidir.'))

        form.separator(t('Notlar'))
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
            ttk.Label(self.attributes_host, text=t('Bu tipin ek özelliği yok.'),
                      style='Muted.TLabel').pack(anchor='w')
            return
        ttk.Label(self.attributes_host,
                  text=t('%s tipinin özellikleri') % AssetTypes.label(asset_type),
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
        ttk.Label(parent, text=t('Durum'), style='Heading.TLabel').pack(anchor='w')
        open_impacts = ImpactRepo.open_count_for_asset(self.conn, self.asset_id)
        if open_impacts:
            ttk.Label(parent, text=t('%d etki değerlendirmesi açık.') % open_impacts,
                      style='Alert.TLabel').pack(anchor='w', pady=(4, 0))

        targets = states.next_states('asset', row['status'])
        bar = ttk.Frame(parent)
        bar.pack(fill='x', pady=(8, 4))
        if targets:
            self.transition_choice = w.Combo(bar, [(t, states.label('asset', t)) for t in targets],
                                             width=22)
            self.transition_choice.pack(side='left')
            ttk.Label(bar, text=t('Gerekçe'), style='Muted.TLabel').pack(side='left', padx=(10, 4))
            self.transition_reason = ttk.Entry(bar, width=36)
            self.transition_reason.pack(side='left')
            ttk.Button(bar, text=t('Durumu değiştir'), command=self.change_status).pack(side='left', padx=8)
        else:
            ttk.Label(parent, text=t('Bu durumdan ileri gidilemez.'), style='Muted.TLabel').pack(anchor='w')

        ttk.Separator(parent).pack(fill='x', pady=12)
        ttk.Label(parent, text=t('Sayaç'), style='Heading.TLabel').pack(anchor='w')
        if not row['counter_unit']:
            ttk.Label(parent, text=t('Bu varlıkta sayaç birimi tanımlı değil.'),
                      style='Muted.TLabel').pack(anchor='w', pady=(4, 0))
            return
        line = ttk.Frame(parent)
        line.pack(fill='x', pady=(8, 0))
        self.counter_value = ttk.Entry(line, width=12)
        self.counter_value.insert(0, str(row['counter_value']))
        self.counter_value.pack(side='left')
        ttk.Label(line, text=AssetTypes.COUNTER_UNITS.get(row['counter_unit'], ''),
                  style='Muted.TLabel').pack(side='left', padx=6)
        ttk.Button(line, text=t('Okumayı kaydet'), command=self.record_counter).pack(side='left', padx=8)
        last = v.human(row['counter_read_at'], with_time=True) or t('hiç')
        ttk.Label(parent, text=t('Son okuma: %s') % last, style='Muted.TLabel').pack(anchor='w', pady=(6, 0))

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
                self.finish(t('Varlık kaydedildi.'))
        else:
            holder = {}

            def create():
                holder['id'] = AssetRepo.create(self.conn, data)
            if self.run(create):
                self.finish(t('Varlık oluşturuldu.'))

    def change_status(self) -> None:
        target = self.transition_choice.key()
        reason = self.transition_reason.get()
        if target == 'retired' and not messagebox.askyesno(
                t('Onay'), t('Bu varlık hurdaya ayrılsın mı? Hurdaya ayrılan varlık geri alınamaz.'),
                parent=self):
            return
        if self.run(lambda: AssetRepo.transition(self.conn, self.asset_id, target, reason)):
            self.finish(t('Varlık durumu değiştirildi.'))

    def record_counter(self) -> None:
        value = self.counter_value.get()
        made = {}

        def record():
            made.update(AssetRepo.record_counter(self.conn, self.asset_id, value))
        if self.run(record):
            extra = ''
            if made.get('work_orders') or made.get('calibrations'):
                extra = t(' %d kayıt üretildi.') % (made['work_orders'] + made['calibrations'])
            self.finish(t('Sayaç okuması kaydedildi.') + extra)

    def delete(self) -> None:
        if not messagebox.askyesno(t('Onay'), t('Bu varlık silinsin mi? Bu işlem geri alınamaz.'),
                                   parent=self):
            return
        if self.run(lambda: AssetRepo.delete(self.conn, self.asset_id)):
            self.finish(t('Varlık silindi.'))


# ====================================================================== plan
class PlanDialog(BaseDialog):
    """Bakim, kalibrasyon ve dogrulama plani; kontrol listesi sablonu dahil."""

    width = 880
    height = 720

    def __init__(self, app, plan_id=None, asset_id=0):
        self.plan_id = int(plan_id) if plan_id else 0
        self.row = ScheduleRepo.get(app.conn, self.plan_id) if self.plan_id else None
        super().__init__(app, t('Planı düzenle') if self.row else t('Plan ekle'))
        row = self.row or {}

        notebook = ttk.Notebook(self.body)
        notebook.pack(fill='both', expand=True, pady=(4, 8))
        general = ttk.Frame(notebook, padding=14)
        checklist = ttk.Frame(notebook, padding=14)
        notebook.add(general, text=t('Plan'))
        notebook.add(checklist, text=t('Kontrol listesi'))

        ttk.Label(checklist, text=t('Bu plandan üretilen her iş emri bu listeyi taşır. Liste sonradan '
                                  'değişirse eski iş emirleri değişmez; her biri kendi anını tutar.'),
                  style='Muted.TLabel', wraplength=700, justify='left').pack(anchor='w',
                                                                              pady=(0, 10))
        ttk.Label(checklist, text=t('Kritik işaretli bir adım tamamlanmadan iş emri kapatılamaz.'),
                  style='Muted.TLabel', wraplength=700, justify='left').pack(anchor='w',
                                                                              pady=(0, 10))
        existing = ChecklistTemplate.items(self.conn, self.plan_id) if self.plan_id else []
        self.checklist = ChecklistEditor(checklist, existing)
        self.checklist.pack(anchor='w', fill='x')

        form = w.FormGrid(general)
        form.pack(fill='both', expand=True)

        options = AssetRepo.options(self.conn)
        self.asset = form.add(t('Varlık'), w.Combo(form, options or [(0, t('- varlık yok -'))], width=44,
                                                value=row.get('asset_id', asset_id)))
        self.plan_type = form.add(t('Plan tipi'), w.Combo(form, ScheduleRepo.PLAN_TYPES, width=26,
                                                       value=row.get('plan_type', 'pm')),
                                  t('Önleyici plan iş emri üretir. Kalibrasyon ve doğrulama planı '
                                  'kalibrasyon kaydı üretir.'))
        self.title_entry = form.add(t('Başlık'), ttk.Entry(form, width=46))
        self.title_entry.insert(0, row.get('title', ''))

        self.basis = form.add(t('Esas'), w.Combo(form, ScheduleRepo.BASES, width=20,
                                              value=row.get('basis', 'time')))
        self.basis.bind('<<ComboboxSelected>>', lambda _e: self._sync_basis())

        interval = ttk.Frame(form)
        self.interval_value = ttk.Entry(interval, width=6)
        self.interval_value.insert(0, str(row.get('interval_value', 1)))
        self.interval_value.pack(side='left')
        self.interval_unit = w.Combo(interval, ScheduleRepo.UNITS, width=10,
                                     value=row.get('interval_unit', 'month'))
        self.interval_unit.pack(side='left', padx=6)
        self.interval_row = form.add(t('Aralık'), interval)

        self.counter_interval = form.add(t('Sayaç aralığı'), ttk.Entry(form, width=10),
                                         t('Varlıkta sayaç birimi tanımlı olmalıdır.'))
        self.counter_interval.insert(0, str(row.get('counter_interval', 0)))

        window = ttk.Frame(form)
        self.lead_days = ttk.Entry(window, width=6)
        self.lead_days.insert(0, str(row.get('lead_days', 14)))
        self.lead_days.pack(side='left')
        ttk.Label(window, text=t('gün önce üret'), style='Muted.TLabel').pack(side='left', padx=(6, 16))
        self.tolerance_days = ttk.Entry(window, width=6)
        self.tolerance_days.insert(0, str(row.get('tolerance_days', 0)))
        self.tolerance_days.pack(side='left')
        ttk.Label(window, text=t('gün gecikme tolere edilir'), style='Muted.TLabel').pack(side='left', padx=6)
        form.add(t('Uyarı aralığı'), window,
                 t('Tolere edilen gecikme yalnızca gecikme raporunu etkiler, vadeyi değiştirmez.'))

        self.last_done = form.add(t('Son yapılma'), w.DateEntry(form, with_time=True))
        self.last_done.set(row.get('last_done_at'))
        self.next_due = form.add(t('Sıradaki vade'), w.DateEntry(form, with_time=True),
                                 t('Boş bırakılırsa aralıktan hesaplanır.'))
        self.next_due.set(row.get('next_due_at'))

        self.assignee = form.add(t('Varsayılan sorumlu'), ttk.Entry(form, width=32))
        self.assignee.insert(0, row.get('assignee', ''))

        self.active = tk.BooleanVar(value=bool(row.get('is_active', 1)))
        form.add(t('Aktif'), ttk.Checkbutton(form, text=t('Bu plandan kayıt üret'), variable=self.active))

        form.separator(t('Talimatlar'))
        self.instructions = w.text_box(form, height=6)
        form.add_full(self.instructions)
        w.write_text(self.instructions, row.get('instructions', ''))

        self._sync_basis()

        if self.row:
            self.history('schedule', self.plan_id)
            self.button(t('Sil'), self.delete, style='Danger.TButton', side='left')
        self.button(t('Kaydet'), self.save, style='Accent.TButton')
        self.button(t('Kapat'), self.destroy)
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
        items = self.checklist.collect()
        if self.plan_id:
            def update():
                ScheduleRepo.update(self.conn, self.plan_id, data)
                ChecklistTemplate.save(self.conn, self.plan_id, items)
            if self.run(update):
                self.finish(t('Plan kaydedildi.'))
            return
        made = {}

        def create():
            made['id'] = ScheduleRepo.create(self.conn, data)
            ChecklistTemplate.save(self.conn, made['id'], items)
        if self.run(create):
            self.finish(t('Plan oluşturuldu.'))

    def delete(self) -> None:
        if not messagebox.askyesno(t('Onay'), t('Bu plan silinsin mi? Üretilmiş kayıtlar kalır.'),
                                   parent=self):
            return
        if self.run(lambda: ScheduleRepo.delete(self.conn, self.plan_id)):
            self.finish(t('Plan silindi.'))


# ====================================================================== talep
class RequestDialog(BaseDialog):
    """Arizanin sahadan bildirildigi kisa form."""

    width = 680
    height = 480

    def __init__(self, app, asset_id=0):
        super().__init__(app, t('Arıza bildir'))
        form = w.FormGrid(self.body)
        form.pack(fill='both', expand=True, pady=(4, 10))

        options = AssetRepo.options(self.conn)
        self.asset = form.add(t('Varlık'), w.Combo(form, options or [(0, t('- varlık yok -'))], width=44,
                                                value=asset_id))
        self.summary = form.add(t('Özet'), ttk.Entry(form, width=46), 'Sorun nedir?')
        self.severity = form.add(t('Önem'), w.Combo(form, RequestRepo.SEVERITIES, width=26,
                                                 value='normal'))
        form.separator(t('Açıklama'))
        self.description = w.text_box(form, height=7)
        form.add_full(self.description)

        self.button(t('Kaydet'), self.save, style='Accent.TButton')
        self.button(t('Kapat'), self.destroy)
        self.show()

    def save(self) -> None:
        data = {
            'asset_id': self.asset.key(),
            'summary': self.summary.get(),
            'severity': self.severity.key(),
            'description': w.read_text(self.description),
        }
        if self.run(lambda: RequestRepo.create(self.conn, data)):
            self.finish(t('Talep kaydedildi.'))


# ====================================================================== is emri
class WorkOrderDialog(BaseDialog):
    """Is emri kaydi, kontrol listesi, kullanilan parcalar ve durum gecisleri."""

    width = 960
    height = 860

    def __init__(self, app, work_order_id=None, asset_id=0):
        self.work_order_id = int(work_order_id) if work_order_id else 0
        self.row = WorkOrderRepo.get(app.conn, self.work_order_id) if self.work_order_id else None
        super().__init__(app, (t('İş emri #%d') % self.work_order_id) if self.row else t('İş emri ekle'))
        row = self.row or {}
        self.is_new = not bool(self.row)
        self.locked = bool(row) and row['status'] in ('closed', 'cancelled')

        if self.row:
            self.set_badge(states.label('work_order', row['status']), row['status'])
            if int(row['schedule_id']):
                plan = ScheduleRepo.get(self.conn, int(row['schedule_id']))
                if plan:
                    ttk.Label(self.body, text=t('Plandan üretildi: %s') % plan['title'],
                              style='Muted.TLabel').pack(anchor='w', pady=(4, 0))

        form = w.FormGrid(self.body)
        form.pack(fill='x', pady=(6, 10))
        options = AssetRepo.options(self.conn)
        self.asset = form.add(t('Varlık'), w.Combo(form, options or [(0, t('- varlık yok -'))], width=44,
                                                value=row.get('asset_id', asset_id)))
        self.title_entry = form.add(t('Başlık'), ttk.Entry(form, width=46))
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
        form.add(t('Sınıflandırma'), classification)

        planned = ttk.Frame(form)
        self.planned_start = w.DateEntry(planned, with_time=True, width=16)
        self.planned_start.pack(side='left')
        self.planned_end = w.DateEntry(planned, with_time=True, width=16)
        self.planned_end.pack(side='left', padx=(10, 0))
        form.add(t('Planlanan'), planned)
        self.planned_start.set(row.get('planned_start'))
        self.planned_end.set(row.get('planned_end'))

        actual = ttk.Frame(form)
        self.actual_start = w.DateEntry(actual, with_time=True, width=16)
        self.actual_start.pack(side='left')
        self.actual_end = w.DateEntry(actual, with_time=True, width=16)
        self.actual_end.pack(side='left', padx=(10, 0))
        form.add(t('Gerçekleşen'), actual)
        self.actual_start.set(row.get('actual_start'))
        self.actual_end.set(row.get('actual_end'))

        effort = ttk.Frame(form)
        self.labor = ttk.Entry(effort, width=7)
        self.labor.insert(0, str(row.get('labor_minutes', 0)))
        self.labor.pack(side='left')
        ttk.Label(effort, text=t('dk işçilik'), style='Muted.TLabel').pack(side='left', padx=(5, 14))
        self.downtime = ttk.Entry(effort, width=7)
        self.downtime.insert(0, str(row.get('downtime_minutes', 0)))
        self.downtime.pack(side='left')
        ttk.Label(effort, text=t('dk duruş'), style='Muted.TLabel').pack(side='left', padx=5)
        form.add(t('Efor'), effort)

        form.separator(t('Yapılan iş'))
        self.work_done = w.text_box(form, height=5)
        form.add_full(self.work_done)
        w.write_text(self.work_done, row.get('work_done', ''))
        form.separator(t('Kök neden'))
        self.root_cause = w.text_box(form, height=3)
        form.add_full(self.root_cause)
        w.write_text(self.root_cause, row.get('root_cause', ''))

        if row.get('hold_reason'):
            ttk.Label(self.body, text=t('Bekletme gerekçesi: %s') % row['hold_reason'],
                      style='Muted.TLabel', wraplength=700, justify='left').pack(anchor='w')

        if not self.is_new:
            self._build_checklist()
            self._build_parts()

        if self.locked:
            for widget in (self.asset, self.title_entry, self.wo_type, self.priority,
                           self.assigned_to, self.labor, self.downtime):
                widget.configure(state='disabled')
            self.work_done.configure(state='disabled')
            self.root_cause.configure(state='disabled')
            ttk.Label(self.body, text=t('Bu iş emri kapalı ve artık düzenlenemez.'),
                      style='Muted.TLabel').pack(anchor='w', pady=(6, 0))

        if self.row:
            self._build_transitions()
            self.history('work_order', self.work_order_id)
        if not self.locked:
            self.button(t('Kaydet'), self.save, style='Accent.TButton')
        self.button(t('Kapat'), self.destroy)
        self.show()

    def _build_checklist(self) -> None:
        progress = WorkOrderChecklist.progress(self.conn, self.work_order_id)
        ttk.Separator(self.body).pack(fill='x', pady=12)
        head = ttk.Frame(self.body)
        head.pack(fill='x')
        ttk.Label(head, text=t('Kontrol listesi'), style='Heading.TLabel').pack(side='left')
        if progress['total']:
            text = t('%d adımdan %d tamamlandı') % (progress['total'], progress['done'])
            if progress['failed']:
                text += ', %d uygunsuz' % progress['failed']
            ttk.Label(head, text='   ' + text,
                      style='Alert.TLabel' if progress['critical_open'] else 'Muted.TLabel').pack(
                side='left')
        self.checklist = ChecklistPanel(self.body, self.conn, self.work_order_id,
                                        readonly=self.locked)
        self.checklist.pack(fill='x', pady=(8, 0))

    def _build_parts(self) -> None:
        ttk.Separator(self.body).pack(fill='x', pady=12)
        ttk.Label(self.body, text=t('Kullanılan parçalar'), style='Heading.TLabel').pack(anchor='w')
        used = PartRepo.used_on_work_order(self.conn, self.work_order_id)
        if used:
            table = w.DataTable(self.body, [('code', t('Kod'), 120), ('name', t('Parça'), 240),
                                            ('qty', t('Miktar'), 90, 'e'), ('cost', 'Tutar', 90, 'e'),
                                            ('at', t('Zaman'), 140)],
                                height=min(6, len(used)))
            table.pack(fill='x', pady=(8, 4))
            table.set_rows(used, values=lambda r: (
                r['code'], r['name'],
                '%s %s' % (_num(abs(float(r['delta']))), r['unit']),
                _num(abs(float(r['delta'])) * float(r['unit_cost'])),
                v.human(r['created_at'], with_time=True)))
            ttk.Label(self.body, text=t('Toplam parça maliyeti: %s')
                      % _num(PartRepo.work_order_cost(self.conn, self.work_order_id)),
                      style='Muted.TLabel').pack(anchor='w')
        else:
            ttk.Label(self.body, text=t('Henüz parça kullanılmadı.'),
                      style='Muted.TLabel').pack(anchor='w', pady=(6, 0))

        if self.locked:
            return
        options = PartRepo.options(self.conn)
        bar = ttk.Frame(self.body)
        bar.pack(fill='x', pady=(8, 0))
        if not options:
            ttk.Label(bar, text=t('Kütükte aktif parça yok. Yedek parçalar ekranından ekleyin.'),
                      style='Muted.TLabel').pack(side='left')
            return
        self.part_choice = w.Combo(bar, options, width=40)
        self.part_choice.pack(side='left')
        self.part_qty = ttk.Entry(bar, width=8)
        self.part_qty.insert(0, '1')
        self.part_qty.pack(side='left', padx=6)
        ttk.Button(bar, text=t('Parça kullan'), command=self.consume_part).pack(side='left')

    def consume_part(self) -> None:
        part_id, quantity = self.part_choice.key(), self.part_qty.get()
        if self.run(lambda: PartRepo.consume(self.conn, part_id, quantity, self.work_order_id)):
            self.finish(t('Parça kullanımı kaydedildi.'))

    def _build_transitions(self) -> None:
        targets = states.next_states('work_order', self.row['status'])
        if not targets:
            return
        frame = ttk.Frame(self.body)
        frame.pack(fill='x', pady=(14, 4))
        ttk.Label(frame, text=t('Sonraki duruma geç'), style='Heading.TLabel').pack(anchor='w')
        ttk.Label(frame, text=t('Bir plandan gelen iş emrini tamamlamak, o planı sıradaki vadesine '
                             'ilerletir.'), style='Muted.TLabel', wraplength=720,
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
                self.finish(t('İş emri kaydedildi.'))
        elif self.run(lambda: WorkOrderRepo.create(self.conn, data)):
            self.finish(t('İş emri oluşturuldu.'))

    def transition(self, target: str) -> None:
        """Gecis once formdaki degerlerle denenir; eksik alan varsa sorulur."""
        data = self.collect()
        if target == 'on_hold':
            reason = _ask_text(self, t('Bekletme gerekçesi'), 'Neden bekletiliyor?')
            if reason is None:
                return
            data['hold_reason'] = reason
        if self.work_order_id and not self.locked:
            if getattr(self, 'checklist', None) and not self.checklist.save():
                return                     # eksik olcum degeri varsa once o duzelsin
            try:
                WorkOrderRepo.update(self.conn, self.work_order_id, data)
            except v.MihenkError:
                pass                       # kaydedilemeyen alanlar gecisi engellemesin
            if target == 'completed':
                summary = WorkOrderChecklist.summary_text(self.conn, self.work_order_id)
                if summary and summary not in (data.get('work_done') or ''):
                    data['work_done'] = ((data.get('work_done') or '').rstrip() + '\n\n'
                                         + 'Kontrol listesi:\n' + summary).strip()
        if self.run(lambda: WorkOrderRepo.transition(self.conn, self.work_order_id, target, data)):
            self.finish(t('İş emri %s durumuna alındı.') % states.label('work_order', target).lower())


# ====================================================================== kalibrasyon
class PointsGrid(ttk.Frame):
    """Olcum noktasi tablosu: sapma canli hesaplanir ve renklenir."""

    COLUMNS = ('Etiket', t('Nominal'), t('Ölçülen'), t('Tolerans (±)'), t('Birim'), t('Sapma'), '')

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
            self.add_button = ttk.Button(self, text=t('Nokta ekle'), style='Ghost.TButton',
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
            remove = ttk.Button(self, text=t('Kaldır'), style='Ghost.TButton', width=7,
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
        kind = CalibrationRepo.RECORD_TYPES.get(self.row['record_type'], t('Kalibrasyon'))
        super().__init__(app, t('%s kaydı #%d') % (kind, self.record_id))
        row = self.row
        self.locked = row['status'] in ('closed', 'cancelled')
        self.set_badge(states.label('calibration', row['status']), row['status'])

        ttk.Label(self.body, text=AssetRepo.label(self.conn, int(row['asset_id'])),
                  style='Muted.TLabel').pack(anchor='w', pady=(4, 0))

        if row['result'] == 'fail':
            self.warn(t('Bu kayıt uygunsuz. Varlık otomatik karantinaya alındı ve bir etki '
                      'değerlendirmesi açıldı.'))

        form = w.FormGrid(self.body)
        form.pack(fill='x', pady=(8, 6))
        self.performed_at = form.add(t('Yapılma zamanı'), w.DateEntry(form, with_time=True))
        self.performed_at.set(row['performed_at'])
        self.performed_by = form.add(t('Yapan'), ttk.Entry(form, width=32))
        self.performed_by.insert(0, row['performed_by'])

        external = ttk.Frame(form)
        self.external_body = ttk.Entry(external, width=26)
        self.external_body.insert(0, row['external_body'])
        self.external_body.pack(side='left')
        self.accreditation = ttk.Entry(external, width=30)
        self.accreditation.insert(0, row['accreditation_scope'])
        self.accreditation.pack(side='left', padx=6)
        form.add(t('Dış kuruluş / kapsam'), external)

        certificate = ttk.Frame(form)
        self.certificate_no = ttk.Entry(certificate, width=22)
        self.certificate_no.insert(0, row['certificate_no'])
        self.certificate_no.pack(side='left')
        self.certificate_path = ttk.Entry(certificate, width=30)
        self.certificate_path.insert(0, row['certificate_path'])
        self.certificate_path.pack(side='left', padx=6)
        ttk.Button(certificate, text='Dosya…', style='Ghost.TButton',
                   command=self.pick_certificate).pack(side='left')
        if export.certificate_exists(row['certificate_path']):
            ttk.Button(certificate, text=t('Aç'), style='Ghost.TButton', width=4,
                       command=self.open_certificate).pack(side='left')
        form.add(t('Sertifika'), certificate,
                 t('Seçilen dosya Mihenk veri klasörüne kopyalanır; özgün dosya taşınsa bile '
                 'kayıt boşa düşmez.'))
        if row['certificate_path'] and not export.certificate_exists(row['certificate_path']):
            ttk.Label(self.body, text=t('Sertifika dosyası bulunamıyor: %s') % row['certificate_path'],
                      style='Alert.TLabel', wraplength=800, justify='left').pack(anchor='w')

        self.traceability = form.add(t('İzlenebilirlik referansı'), ttk.Entry(form, width=46))
        self.traceability.insert(0, row['traceability_ref'])

        spec = ttk.Frame(form)
        self.tolerance_spec = ttk.Entry(spec, width=30)
        self.tolerance_spec.insert(0, row['tolerance_spec'])
        self.tolerance_spec.pack(side='left')
        self.uncertainty = ttk.Entry(spec, width=20)
        self.uncertainty.insert(0, row['uncertainty'])
        self.uncertainty.pack(side='left', padx=6)
        form.add(t('Tolerans / belirsizlik'), spec)

        ttk.Label(self.body, text=t('Ölçüm noktaları'), style='Heading.TLabel').pack(anchor='w',
                                                                                   pady=(10, 2))
        ttk.Label(self.body, text=t('Toleransı girilmemiş bir nokta tek başına uygunluğu kanıtlamaz. '
                                 'Tolerans dışındaki tek bir nokta kaydın tamamını uygunsuz yapar.'),
                  style='Muted.TLabel', wraplength=820, justify='left').pack(anchor='w', pady=(0, 6))
        self.points = PointsGrid(self.body, CalibrationRepo.points(row), readonly=self.locked)
        self.points.pack(anchor='w', pady=(0, 10))

        result_form = w.FormGrid(self.body)
        result_form.pack(fill='x')
        self.result = result_form.add(
            t('Sonuç'), w.Combo(result_form, [('', t('- noktalardan türet -'))] +
                             list(CalibrationRepo.RESULTS.items()), width=26, value=row['result']),
            t('Uygunsuz seçmek varlığı karantinaya alır ve etki değerlendirmesi açar.'))
        result_form.separator(t('Kullanım sınırlaması'))
        self.usage_limit = w.text_box(result_form, height=3)
        result_form.add_full(self.usage_limit)
        w.write_text(self.usage_limit, row['usage_limit'])
        result_form.add_full(ttk.Label(result_form,
                                       text=t('Şartlı bir sonucun kapatılabilmesi için zorunludur.'),
                                       style='Muted.TLabel'))
        result_form.separator(t('Notlar'))
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
            self.button(t('Etki değerlendirmesi'), self.open_impact, side='left')
        if not self.locked:
            self.button('Sonucu kaydet', self.save, style='Accent.TButton')
        self.button(t('Kapat'), self.destroy)
        self.show()

    def _build_transitions(self) -> None:
        targets = states.next_states('calibration', self.row['status'])
        if not targets:
            return
        frame = ttk.Frame(self.body)
        frame.pack(fill='x', pady=(14, 4))
        ttk.Label(frame, text=t('Sonraki duruma geç'), style='Heading.TLabel').pack(anchor='w')
        bar = ttk.Frame(frame)
        bar.pack(fill='x', pady=(6, 0))
        for target in targets:
            ttk.Button(bar, text=states.label('calibration', target),
                       command=lambda t=target: self.transition(t)).pack(side='left', padx=(0, 6))
        if 'closed' in targets and self.row['result'] == 'fail':
            ttk.Label(frame, text=t('Kapatma, etki değerlendirmesi kapanana kadar engelli.'),
                      style='Muted.TLabel').pack(anchor='w', pady=(6, 0))

    def pick_certificate(self) -> None:
        path = filedialog.askopenfilename(parent=self, title=t('Sertifika dosyası'),
                                          filetypes=[('PDF', '*.pdf'), (t('Tüm dosyalar'), '*.*')])
        if path:
            self.certificate_path.delete(0, 'end')
            self.certificate_path.insert(0, path)

    def open_certificate(self) -> None:
        target = export.certificate_path(self.row['certificate_path'])
        try:
            if sys.platform == 'win32':
                os.startfile(str(target))                      # noqa: S606
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', str(target)])
            else:
                subprocess.Popen(['xdg-open', str(target)])
        except Exception as exc:
            messagebox.showinfo(t('Sertifika'), '%s\n\n(%s)' % (target, exc), parent=self)

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
                t('Uygunsuz sonuç'),
                t('Bu sonuç uygunsuz. Varlık karantinaya alınacak ve etki değerlendirmesi açılacak.\n\n'
                'Devam edilsin mi?'), parent=self):
            return
        if self.run(lambda: CalibrationRepo.save_result(self.conn, self.record_id, data)):
            self.finish(t('Sonuç kaydedildi.'))

    def transition(self, target: str) -> None:
        if self.run(lambda: CalibrationRepo.transition(self.conn, self.record_id, target)):
            self.finish(t('Kayıt %s durumuna alındı.') % states.label('calibration', target).lower())

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
        super().__init__(app, t('Etki değerlendirmesi #%d') % self.impact_id)
        row = self.row
        self.closed = row['status'] == 'closed'
        self.set_badge(states.label('impact', row['status']), row['status'])

        asset_label = AssetRepo.label(self.conn, int(row['asset_id']))
        self.warn(t('%s tolerans dışında ölçüm yaptı. %s ile %s arasında ölçtüğü her şey, bu '
                  'değerlendirme bir karara bağlanana kadar şüphelidir.')
                  % (asset_label, v.human(row['affected_from'], with_time=True) or '?',
                     v.human(row['affected_to'], with_time=True) or '?'))

        record = CalibrationRepo.get(self.conn, int(row['calibration_id'])) if row['calibration_id'] else None
        if record:
            line = ttk.Frame(self.body)
            line.pack(fill='x', pady=(4, 0))
            ttk.Label(line, text=t('Kaynak kayıt #%d') % record['id'], style='Muted.TLabel').pack(side='left')
            if record['max_deviation'] is not None:
                ttk.Label(line, text=t('   En büyük sapma: %g') % record['max_deviation'],
                          style='Muted.TLabel').pack(side='left')

        form = w.FormGrid(self.body)
        form.pack(fill='x', pady=(10, 6))
        window = ttk.Frame(form)
        self.affected_from = w.DateEntry(window, with_time=True, width=16)
        self.affected_from.pack(side='left')
        self.affected_to = w.DateEntry(window, with_time=True, width=16)
        self.affected_to.pack(side='left', padx=(10, 0))
        form.add(t('Etkilenen aralık'), window,
                 t('Uygunluğu gerçekten kanıtlayan son kayda göre dolduruldu. Yalnızca kanıtla daraltın.'))
        self.affected_from.set(row['affected_from'])
        self.affected_to.set(row['affected_to'])

        form.separator(t('Etkilenen kapsam'))
        self.scope = w.text_box(form, height=4)
        form.add_full(self.scope)
        w.write_text(self.scope, row['affected_scope'])
        ttk.Label(self.body, text=t('Bu aralıkta hangi hatlar, ürünler ve partiler bu cihazdan geçti.'),
                  style='Muted.TLabel').pack(anchor='w')

        form2 = w.FormGrid(self.body)
        form2.pack(fill='x')
        form2.separator(t('Değerlendirme'))
        self.evaluation = w.text_box(form2, height=6)
        form2.add_full(self.evaluation)
        w.write_text(self.evaluation, row['evaluation'])
        self.decision = form2.add(t('Karar'), w.Combo(form2, [('', t('- seçin -'))] +
                                                   list(ImpactRepo.DECISIONS.items()), width=30,
                                                   value=row['decision']))
        form2.separator(t('Düzeltici faaliyet'))
        self.corrective = w.text_box(form2, height=4)
        form2.add_full(self.corrective)
        w.write_text(self.corrective, row['corrective_action'])

        if self.closed:
            for widget in (self.decision,):
                widget.configure(state='disabled')
            for box in (self.scope, self.evaluation, self.corrective):
                box.configure(state='disabled')
            ttk.Label(self.body, text=t('%s tarihinde %s tarafından kapatıldı.')
                      % (v.human(row['closed_at'], with_time=True), row['closed_by'] or '—'),
                      style='Muted.TLabel').pack(anchor='w', pady=(8, 0))

        self.history('impact', self.impact_id)

        if not self.closed:
            self.button(t('Değerlendirmeyi kapat'), self.close_assessment, style='Accent.TButton')
            self.button(t('Taslağı kaydet'), self.save_draft)
        self.button(t('Kapat'), self.destroy)
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
            self.finish(t('Etki değerlendirmesi kaydedildi.'))

    def close_assessment(self) -> None:
        if not messagebox.askyesno(t('Onay'), t('Değerlendirme kapatılsın mı? Kapatma varlığı '
                                           'karantinadan çıkarır ve kayıt düzenlenemez olur.'),
                                   parent=self):
            return
        if self.run(lambda: ImpactRepo.close(self.conn, self.impact_id, self.collect())):
            self.finish(t('Etki değerlendirmesi kapatıldı.'))


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
    ttk.Button(bar, text=t('Vazgeç'), command=box.destroy).pack(side='right', padx=6)
    box.bind('<Return>', lambda _e: accept())
    box.bind('<Escape>', lambda _e: box.destroy())
    box.update_idletasks()
    box.geometry('+%d+%d' % (parent.winfo_rootx() + 60, parent.winfo_rooty() + 80))
    box.grab_set()
    parent.wait_window(box)
    return answer.get('value')


# ====================================================================== ilk acilis
class WelcomeDialog(tk.Toplevel):
    """Ilk acilista cikan karsilama.

    Bos bir kutukle karsilasan biri uygulamanin ne yaptigini goremez, ozellikle
    de asil ayirt edici davranisi olan karantina kilidini. Burada demo setiyle
    baslamayi teklif ediyoruz; sessizce veri basmak yerine soruyoruz, cunku
    gercek kayit girecek kisi de ayni yerden temiz baslayabilmeli.
    """

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.choice = None
        p = theme.palette()
        self.title(t('Mihenk\'e hoş geldiniz'))
        self.configure(background=p['bg'])
        self.transient(app.root)
        self.resizable(False, False)

        head = ttk.Frame(self, padding=(28, 24, 28, 6))
        head.pack(fill='x')
        ttk.Label(head, text='Mihenk', style='Title.TLabel').pack(anchor='w')
        ttk.Label(head, text=t('Ekipman bakımı, kalibrasyon ve doğrulama takibi'),
                  style='Muted.TLabel').pack(anchor='w', pady=(2, 0))

        body = ttk.Frame(self, padding=(28, 6, 28, 10))
        body.pack(fill='both', expand=True)
        ttk.Label(body, text=t('Kütük şu anda boş. İki şekilde başlayabilirsiniz.'),
                  style='TLabel').pack(anchor='w', pady=(0, 14))

        demo = ttk.Frame(body, style='Card.TFrame', padding=(16, 14))
        demo.pack(fill='x', pady=(0, 10))
        ttk.Label(demo, text=t('Demo veriyle başla'), style='SurfaceHeading.TLabel').pack(anchor='w')
        ttk.Label(demo, text=t('Bir dolum hattının sekiz varlığı, yedi planı, dört talebi ve üç '
                             'kalibrasyon kaydı kurulur. Kayıtlardan biri bilerek uygunsuzdur: '
                             'varlığı karantinaya almış ve bir etki değerlendirmesi açmıştır, '
                             'böylece uygulamanın asıl kuralını çalışırken görürsünüz.\n\n'
                             'Bütün demo varlıklarının kodu DEMO- ile başlar ve Ayarlar '
                             'ekranından tek tıkla temizlenir; kendi kayıtlarınıza dokunmaz.'),
                  style='SurfaceMuted.TLabel', wraplength=520, justify='left').pack(anchor='w',
                                                                                     pady=(6, 0))

        empty = ttk.Frame(body, style='Card.TFrame', padding=(16, 14))
        empty.pack(fill='x')
        ttk.Label(empty, text=t('Boş başla'), style='SurfaceHeading.TLabel').pack(anchor='w')
        ttk.Label(empty, text=t('Doğrudan kendi ekipmanınızı girersiniz. Önce Varlıklar ekranından '
                              'bir varlık, sonra ona bir plan ekleyin; planlar vadesi geldiğinde '
                              'iş emri ya da kalibrasyon kaydı üretir.'),
                  style='SurfaceMuted.TLabel', wraplength=520, justify='left').pack(anchor='w',
                                                                                     pady=(6, 0))

        foot = ttk.Frame(self, padding=(28, 14, 28, 20))
        foot.pack(fill='x')
        ttk.Button(foot, text=t('Demo veriyle başla'), style='Accent.TButton',
                   command=self.start_demo).pack(side='right')
        ttk.Button(foot, text=t('Boş başla'), command=self.start_empty).pack(side='right', padx=8)
        ttk.Label(foot, text=t('Bu pencere yalnızca ilk açılışta çıkar.'),
                  style='Muted.TLabel').pack(side='left')

        self.bind('<Escape>', lambda _e: self.start_empty())
        self.protocol('WM_DELETE_WINDOW', self.start_empty)
        self.update_idletasks()
        parent = app.root
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        y = parent.winfo_rooty() + 90
        self.geometry('+%d+%d' % (x, y))
        self.grab_set()
        self.focus_set()

    def start_demo(self) -> None:
        import mihenk_seed as seed
        report = {}
        try:
            report = seed.seed(self.app.conn)
        except Exception as exc:
            messagebox.showerror(t('Demo veri kurulamadı'), str(exc), parent=self)
            self._finish('error')
            return
        self._finish('demo')
        if report.get('ok'):
            messagebox.showinfo(t('Demo veri kuruldu'), '\n\n'.join(report['lines']),
                                parent=self.app.root)

    def start_empty(self) -> None:
        self._finish('empty')

    def _finish(self, choice: str) -> None:
        self.choice = choice
        store.save_settings({'first_run_done': True})
        self.destroy()
        self.app.refresh()


class LanguageDialog(tk.Toplevel):
    """Ilk acilista cikan dil secimi.

    Sorumluluk reddinden once geliyor: kullanici neyi kabul ettigini kendi
    dilinde okumali. Secim kaydedilip uygulama yeniden baslatiliyor, cunku
    menu ve tablo basliklari moduller yuklenirken kuruluyor.

    Iki dil adi da kendi dilinde yaziliyor ("Türkçe", "English") ve pencerenin
    basligi iki dilde; secimi yapacak kisi henuz hangi dili gordugunu secmedi.
    """

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.chosen = None
        p = theme.palette()
        self.title('Dil / Language')
        self.configure(background=p['bg'])
        self.transient(app.root)
        self.resizable(False, False)

        head = ttk.Frame(self, padding=(28, 24, 28, 4))
        head.pack(fill='x')
        ttk.Label(head, text='Mihenk', style='Title.TLabel').pack(anchor='w')
        ttk.Label(head, text='Dil / Language', style='Muted.TLabel').pack(anchor='w', pady=(2, 0))

        body = ttk.Frame(self, padding=(28, 10, 28, 4))
        body.pack(fill='both', expand=True)
        for code, label in i18n.LANGUAGES.items():
            ttk.Button(body, text=label, width=26,
                       style='Accent.TButton' if code == i18n.language() else 'TButton',
                       command=lambda c=code: self._pick(c)).pack(anchor='w', pady=4)

        foot = ttk.Frame(self, padding=(28, 10, 28, 20))
        foot.pack(fill='x')
        ttk.Label(foot, text='Sonradan Ayarlar ekranından değiştirilebilir.\n'
                             'You can change this later on the Settings screen.',
                  style='Muted.TLabel', justify='left').pack(anchor='w')

        self.bind('<Escape>', lambda _e: self._pick(i18n.language()))
        self.protocol('WM_DELETE_WINDOW', lambda: self._pick(i18n.language()))
        self.update_idletasks()
        parent = app.root
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        y = parent.winfo_rooty() + 120
        self.geometry('+%d+%d' % (x, y))
        self.grab_set()
        self.focus_set()

    def _pick(self, code: str) -> None:
        self.chosen = code
        store.save_settings({'language': code, 'language_asked': True})
        self.destroy()


class DisclaimerDialog(tk.Toplevel):
    """Ilk acilista cikan sorumluluk reddi.

    Karsilama penceresinden once gelir ve onaylanmadan kapanmaz: kapatma
    dugmesi ve Escape uygulamadan cikar. Ucretsiz dagitilan bir yazilimda
    kullanicinin neyi kabul ettigini bir kez gormesi, sonradan "yazmiyordu"
    demesinden iyidir.

    Kurulum betigi de ayni metni yaziyor, ama EXE elden ele de gecebilir;
    o yuzden onay burada da soruluyor.
    """

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.agreed = False
        p = theme.palette()
        self.title(legal.heading())
        self.configure(background=p['bg'])
        self.transient(app.root)
        self.resizable(False, False)

        head = ttk.Frame(self, padding=(28, 24, 28, 6))
        head.pack(fill='x')
        ttk.Label(head, text=legal.heading(), style='Title.TLabel').pack(anchor='w')
        ttk.Label(head, text=t('Mihenk ücretsizdir. Kullanmadan önce lütfen okuyun.'),
                  style='Muted.TLabel').pack(anchor='w', pady=(2, 0))

        body = ttk.Frame(self, padding=(28, 6, 28, 10))
        body.pack(fill='both', expand=True)
        card = ttk.Frame(body, style='Card.TFrame', padding=(16, 14))
        card.pack(fill='both', expand=True)
        ttk.Label(card, text=legal.text(), style='SurfaceMuted.TLabel',
                  wraplength=560, justify='left').pack(anchor='w')

        self.ticked = tk.BooleanVar(value=False)
        check = ttk.Checkbutton(body, variable=self.ticked, command=self._sync,
                                text=t('Okudum, kabul ediyorum.'))
        check.pack(anchor='w', pady=(14, 0))

        foot = ttk.Frame(self, padding=(28, 14, 28, 20))
        foot.pack(fill='x')
        self.ok = ttk.Button(foot, text=t('Kabul ediyorum'), style='Accent.TButton',
                             state='disabled', command=self._accept)
        self.ok.pack(side='right')
        ttk.Button(foot, text=t('Kabul etmiyorum, çık'),
                   command=self._decline).pack(side='right', padx=8)

        self.bind('<Escape>', lambda _e: self._decline())
        self.protocol('WM_DELETE_WINDOW', self._decline)
        self.update_idletasks()
        parent = app.root
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        y = parent.winfo_rooty() + 70
        self.geometry('+%d+%d' % (x, y))
        self.grab_set()
        self.focus_set()

    def _sync(self) -> None:
        self.ok.configure(state='normal' if self.ticked.get() else 'disabled')

    def _accept(self) -> None:
        legal.accept()
        self.agreed = True
        self.destroy()

    def _decline(self) -> None:
        self.agreed = False
        self.destroy()


# ====================================================================== kontrol listesi
class ChecklistEditor(ttk.Frame):
    """Plan sablonunun adim listesi: satir ekle, kaldir, sirala."""

    def __init__(self, parent, items=None):
        super().__init__(parent)
        self.rows = []
        headers = (t('Sıra'), t('Adım'), t('Ölçüm ister'), t('Birim'), t('Kritik'), '')
        for index, text in enumerate(headers):
            ttk.Label(self, text=text, style='Muted.TLabel').grid(
                row=0, column=index, sticky='w', padx=3, pady=(0, 4))
        for item in (items or []):
            self.add_row(item)
        self.add_button = ttk.Button(self, text=t('Adım ekle'), style='Ghost.TButton',
                                     command=lambda: self.add_row({}))
        self._place_button()

    def _place_button(self) -> None:
        if not hasattr(self, 'add_button'):
            return                      # ilk satirlar kurulurken dugme henuz yok
        self.add_button.grid(row=len(self.rows) + 1, column=0, columnspan=2, sticky='w',
                             pady=(6, 0))

    def add_row(self, item: dict) -> None:
        line = len(self.rows) + 1
        order = ttk.Label(self, text=str(line), style='Muted.TLabel', width=4)
        text = ttk.Entry(self, width=46)
        text.insert(0, item.get('text', '') or '')
        needs = tk.BooleanVar(value=bool(item.get('needs_value')))
        needs_box = ttk.Checkbutton(self, variable=needs)
        unit = ttk.Entry(self, width=9)
        unit.insert(0, item.get('unit', '') or '')
        critical = tk.BooleanVar(value=bool(item.get('is_critical')))
        critical_box = ttk.Checkbutton(self, variable=critical)

        entry = {'order': order, 'text': text, 'needs': needs, 'needs_box': needs_box,
                 'unit': unit, 'critical': critical, 'critical_box': critical_box}
        remove = ttk.Button(self, text=t('Kaldır'), style='Ghost.TButton', width=7,
                            command=lambda e=entry: self.remove_row(e))
        entry['remove'] = remove
        for column, widget in enumerate((order, text, needs_box, unit, critical_box, remove)):
            widget.grid(row=line, column=column, padx=3, pady=2, sticky='w')
        self.rows.append(entry)
        self._place_button()

    def remove_row(self, entry: dict) -> None:
        for key in ('order', 'text', 'needs_box', 'unit', 'critical_box', 'remove'):
            entry[key].destroy()
        self.rows.remove(entry)
        for index, row in enumerate(self.rows, start=1):
            for column, key in enumerate(('order', 'text', 'needs_box', 'unit',
                                          'critical_box', 'remove')):
                row[key].grid(row=index, column=column, padx=3, pady=2, sticky='w')
            row['order'].configure(text=str(index))
        self._place_button()

    def collect(self) -> list:
        return [{'text': row['text'].get(), 'needs_value': row['needs'].get(),
                 'unit': row['unit'].get(), 'is_critical': row['critical'].get()}
                for row in self.rows]


class ChecklistPanel(ttk.Frame):
    """Is emrindeki kontrol listesi: her adim isaretlenir, deger ve not alir."""

    def __init__(self, parent, conn, work_order_id, readonly=False):
        super().__init__(parent)
        self.conn = conn
        self.work_order_id = int(work_order_id)
        self.readonly = readonly
        self.rows = []
        self.build()

    def build(self) -> None:
        for child in self.winfo_children():
            child.destroy()
        self.rows = []
        items = WorkOrderChecklist.items(self.conn, self.work_order_id)
        if not items:
            ttk.Label(self, text=t('Bu iş emrinde kontrol listesi yok. Plana bir şablon '
                                 'tanımlarsanız sonraki iş emirleri onu taşır.'),
                      style='Muted.TLabel', wraplength=700, justify='left').grid(
                row=0, column=0, columnspan=6, sticky='w')
            if not self.readonly:
                ttk.Button(self, text=t('Adım ekle'), style='Ghost.TButton',
                           command=self.add_item).grid(row=1, column=0, sticky='w', pady=(8, 0))
            return

        headers = (t('Adım'), t('Durum'), t('Değer'), t('Birim'), t('Not'), '')
        for index, text in enumerate(headers):
            ttk.Label(self, text=text, style='Muted.TLabel').grid(
                row=0, column=index, sticky='w', padx=3, pady=(0, 4))

        for line, item in enumerate(items, start=1):
            label = ttk.Label(self, text=('%d. %s' % (item['position'], item['text'])),
                              wraplength=330, justify='left')
            if int(item['is_critical']):
                label.configure(style='Alert.TLabel')
            state = Combo_state(self, item['state'], readonly=self.readonly)
            value = ttk.Entry(self, width=12)
            value.insert(0, item['value'] or '')
            unit = ttk.Label(self, text=item['unit'] or '', style='Muted.TLabel', width=8)
            note = ttk.Entry(self, width=28)
            note.insert(0, item['note'] or '')
            stamp = ttk.Label(self, text=v.human(item['checked_at'], with_time=True) or '',
                              style='Muted.TLabel', width=16)
            if self.readonly:
                value.configure(state='disabled')
                note.configure(state='disabled')
            for column, widget in enumerate((label, state, value, unit, note, stamp)):
                widget.grid(row=line, column=column, padx=3, pady=2, sticky='w')
            self.rows.append({'id': int(item['id']), 'state': state, 'value': value,
                              'note': note, 'critical': int(item['is_critical'])})

        if not self.readonly:
            bar = ttk.Frame(self)
            bar.grid(row=len(items) + 1, column=0, columnspan=6, sticky='w', pady=(8, 0))
            ttk.Button(bar, text=t('Listeyi kaydet'), command=self.save).pack(side='left')
            ttk.Button(bar, text=t('Tümünü uygun işaretle'), style='Ghost.TButton',
                       command=self.mark_all).pack(side='left', padx=6)
            ttk.Button(bar, text=t('Adım ekle'), style='Ghost.TButton',
                       command=self.add_item).pack(side='left')

    def collect(self) -> list:
        return [{'id': row['id'], 'state': row['state'].key(), 'value': row['value'].get(),
                 'note': row['note'].get()} for row in self.rows]

    def save(self) -> bool:
        try:
            WorkOrderChecklist.save_all(self.conn, self.work_order_id, self.collect())
        except v.MihenkError as exc:
            messagebox.showwarning(t('Kabul edilmedi'), str(exc), parent=self)
            return False
        self.build()
        return True

    def mark_all(self) -> None:
        for row in self.rows:
            if row['state'].key() == 'pending':
                row['state'].set_key('ok')

    def add_item(self) -> None:
        text = _ask_text(self.winfo_toplevel(), t('Adım ekle'), t('Sahada çıkan adımı yazın:'))
        if not text:
            return
        try:
            WorkOrderChecklist.add_item(self.conn, self.work_order_id, text)
        except v.MihenkError as exc:
            messagebox.showwarning(t('Kabul edilmedi'), str(exc), parent=self)
            return
        self.build()


def Combo_state(parent, value, readonly=False):
    """Kontrol adimi durum secici."""
    combo = w.Combo(parent, CHECK_STATES, width=13, value=value)
    if readonly:
        combo.configure(state='disabled')
    return combo


# ====================================================================== yedek parca
class PartDialog(BaseDialog):
    """Yedek parca kaydi ve stok hareketleri."""

    width = 760
    height = 620

    def __init__(self, app, part_id=None):
        self.part_id = int(part_id) if part_id else 0
        self.row = PartRepo.get(app.conn, self.part_id) if self.part_id else None
        super().__init__(app, t('Parçayı düzenle') if self.row else t('Parça ekle'))
        row = self.row or {}

        form = w.FormGrid(self.body)
        form.pack(fill='x', pady=(4, 10))
        self.code = form.add(t('Kod'), ttk.Entry(form, width=26))
        self.code.insert(0, row.get('code', ''))
        self.name = form.add(t('Ad'), ttk.Entry(form, width=46))
        self.name.insert(0, row.get('name', ''))
        self.unit = form.add(t('Birim'), w.Combo(form, [(u, u) for u in PART_UNITS], width=14,
                                              value=row.get('unit', 'adet')))

        stock_line = ttk.Frame(form)
        if self.row:
            ttk.Label(stock_line, text='%s %s' % (_num(row.get('stock')), row.get('unit', '')),
                      style='Heading.TLabel').pack(side='left')
            ttk.Label(stock_line, text=t('  (stok yalnızca hareketle değişir)'),
                      style='Muted.TLabel').pack(side='left')
            self.opening = None
        else:
            self.opening = ttk.Entry(stock_line, width=10)
            self.opening.insert(0, '0')
            self.opening.pack(side='left')
            ttk.Label(stock_line, text=t('  açılış stoğu'), style='Muted.TLabel').pack(side='left')
        form.add(t('Stok'), stock_line)

        self.min_stock = form.add(t('Asgari stok'), ttk.Entry(form, width=10),
                                  t('Bu seviyenin altına düşünce panoda uyarı çıkar. '
                                  '0 yazarsanız uyarı verilmez.'))
        self.min_stock.insert(0, _num(row.get('min_stock', 0)))
        self.location = form.add(t('Konum'), ttk.Entry(form, width=36))
        self.location.insert(0, row.get('location_text', ''))
        self.supplier = form.add(t('Tedarikçi'), ttk.Entry(form, width=36))
        self.supplier.insert(0, row.get('supplier', ''))
        self.unit_cost = form.add(t('Birim maliyet'), ttk.Entry(form, width=12))
        self.unit_cost.insert(0, _num(row.get('unit_cost', 0)))
        self.active = tk.BooleanVar(value=bool(row.get('is_active', 1)))
        form.add(t('Aktif'), ttk.Checkbutton(form, text=t('Listelerde görünsün'), variable=self.active))
        form.separator(t('Notlar'))
        self.notes = w.text_box(form, height=3)
        form.add_full(self.notes)
        w.write_text(self.notes, row.get('notes', ''))

        if self.row:
            self._build_movements()
            self.button(t('Sil'), self.delete, style='Danger.TButton', side='left')
        self.button(t('Kaydet'), self.save, style='Accent.TButton')
        self.button(t('Kapat'), self.destroy)
        self.show()

    def _build_movements(self) -> None:
        ttk.Separator(self.body).pack(fill='x', pady=12)
        ttk.Label(self.body, text=t('Stok hareketi'), style='Heading.TLabel').pack(anchor='w')
        bar = ttk.Frame(self.body)
        bar.pack(fill='x', pady=(8, 4))
        self.move_amount = ttk.Entry(bar, width=10)
        self.move_amount.pack(side='left')
        self.move_reason = w.Combo(bar, {k: lbl for k, lbl in PART_REASONS.items()
                                         if k != 'consume'}, width=22, value='receive')
        self.move_reason.pack(side='left', padx=6)
        self.move_note = ttk.Entry(bar, width=24)
        self.move_note.pack(side='left', padx=(0, 6))
        ttk.Button(bar, text=t('Hareketi kaydet'), command=self.record_movement).pack(side='left')
        ttk.Label(self.body, text=t('Giriş için artı, çıkış için eksi bir sayı yazın. '
                                  'İş emrinde kullanım, iş emri penceresinden işlenir.'),
                  style='Muted.TLabel').pack(anchor='w')

        rows = PartRepo.movements(self.conn, part_id=self.part_id, limit=40)
        if rows:
            table = w.DataTable(self.body, [('created_at', t('Zaman'), 140), ('delta', t('Değişim'), 90, 'e'),
                                            ('balance', t('Bakiye'), 90, 'e'), ('reason', t('Gerekçe'), 220),
                                            ('wo', t('İş emri'), 80), ('actor', t('Kullanıcı'), 120)],
                                height=min(8, len(rows)))
            table.pack(fill='both', expand=True, pady=(8, 0))
            table.set_rows(rows, values=lambda r: (
                v.human(r['created_at'], with_time=True), _num(r['delta']), _num(r['balance']),
                PartRepo.reason_text(r),
                ('#%d' % int(r['work_order_id'])) if int(r['work_order_id']) else '',
                r['actor']), tag_of=lambda r: 'alert' if float(r['delta']) < 0 else 'ok')

    def collect(self) -> dict:
        return {
            'code': self.code.get(), 'name': self.name.get(), 'unit': self.unit.key(),
            'min_stock': self.min_stock.get(), 'location_text': self.location.get(),
            'supplier': self.supplier.get(), 'unit_cost': self.unit_cost.get(),
            'is_active': self.active.get(), 'notes': w.read_text(self.notes),
            'stock': self.opening.get() if self.opening is not None else 0,
        }

    def save(self) -> None:
        data = self.collect()
        if self.part_id:
            if self.run(lambda: PartRepo.update(self.conn, self.part_id, data)):
                self.finish(t('Parça kaydedildi.'))
        elif self.run(lambda: PartRepo.create(self.conn, data)):
            self.finish(t('Parça oluşturuldu.'))

    def record_movement(self) -> None:
        amount = self.move_amount.get()
        reason = self.move_reason.key()
        note = self.move_note.get()
        if self.run(lambda: PartRepo.move(self.conn, self.part_id, amount, reason, 0, note)):
            self.finish(t('Stok hareketi kaydedildi.'))

    def delete(self) -> None:
        if not messagebox.askyesno(t('Onay'), t('Bu parça silinsin mi?'), parent=self):
            return
        if self.run(lambda: PartRepo.delete(self.conn, self.part_id)):
            self.finish(t('Parça silindi.'))


def _num(value) -> str:
    try:
        return '%g' % float(value)
    except (TypeError, ValueError):
        return '0'


# ====================================================================== disa aktarim
class ExportDialog(BaseDialog):
    """Denetime hazir cikti: hangi tablolar, hangi bicim."""

    width = 700
    height = 620

    def __init__(self, app, days=365):
        super().__init__(app, t('Dışa aktar'))
        self.days = int(days or 0)

        ttk.Label(self.body, text=t('Hangi tablolar'), style='Heading.TLabel').pack(anchor='w',
                                                                                  pady=(4, 2))
        ttk.Label(self.body, text=t('Excel çıktısında her tablo ayrı bir sayfaya, CSV çıktısında '
                                  'ayrı bir dosyaya gider.'),
                  style='Muted.TLabel', wraplength=620, justify='left').pack(anchor='w',
                                                                              pady=(0, 8))
        box = ttk.Frame(self.body)
        box.pack(fill='x')
        self.choices = {}
        for index, (key, label, _builder) in enumerate(export.ALL_TABLES):
            var = tk.BooleanVar(value=True)
            ttk.Checkbutton(box, text=label, variable=var).grid(
                row=index // 2, column=index % 2, sticky='w', padx=(0, 24), pady=2)
            self.choices[key] = var

        bar = ttk.Frame(self.body)
        bar.pack(fill='x', pady=(10, 0))
        ttk.Button(bar, text=t('Hepsini seç'), style='Ghost.TButton',
                   command=lambda: self._set_all(True)).pack(side='left')
        ttk.Button(bar, text=t('Hiçbirini seçme'), style='Ghost.TButton',
                   command=lambda: self._set_all(False)).pack(side='left', padx=6)

        ttk.Separator(self.body).pack(fill='x', pady=14)
        ttk.Label(self.body, text=t('Sertifika dosyaları'), style='Heading.TLabel').pack(anchor='w')
        stored = sum(1 for r in CalibrationRepo.query(self.conn)
                     if export.certificate_exists(r['certificate_path']))
        missing = sum(1 for r in CalibrationRepo.query(self.conn)
                      if r['certificate_path'] and not export.certificate_exists(r['certificate_path']))
        text = t('Veri klasöründe %d sertifika dosyası duruyor.') % stored
        if missing:
            text += t('  %d kayıtta dosya yolu var ama dosya bulunamıyor.') % missing
        ttk.Label(self.body, text=text,
                  style='Alert.TLabel' if missing else 'Muted.TLabel').pack(anchor='w', pady=(4, 0))
        self.copy_certificates = tk.BooleanVar(value=bool(stored))
        ttk.Checkbutton(self.body, text=t('Sertifika dosyalarını da çıktı klasörüne kopyala'),
                        variable=self.copy_certificates).pack(anchor='w', pady=(6, 0))

        ttk.Separator(self.body).pack(fill='x', pady=14)
        self.status = ttk.Label(self.body, text='', style='Muted.TLabel', wraplength=620,
                                justify='left')
        self.status.pack(anchor='w')

        self.button(t('Excel kitabı'), self.to_xlsx, style='Accent.TButton')
        self.button(t('CSV klasörü'), self.to_csv)
        self.button(t('Yazdırılabilir rapor'), self.to_html)
        self.button(t('Kapat'), self.destroy, side='left')
        self.show()

    def _set_all(self, value: bool) -> None:
        for var in self.choices.values():
            var.set(value)

    def keys(self) -> list:
        return [key for key, var in self.choices.items() if var.get()]

    def _copy_certificates(self, folder) -> int:
        if not self.copy_certificates.get():
            return 0
        import shutil
        target = pathlib.Path(folder) / 'sertifikalar'
        target.mkdir(parents=True, exist_ok=True)
        count = 0
        for record in CalibrationRepo.query(self.conn):
            source = export.certificate_path(record['certificate_path'])
            if not str(source) or not source.exists():
                continue
            shutil.copy2(source, target / source.name)
            count += 1
        return count

    def to_xlsx(self) -> None:
        keys = self.keys()
        if not keys:
            messagebox.showinfo(t('Seçim yok'), t('En az bir tablo seçin.'), parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self, title=t('Excel kitabı'), defaultextension='.xlsx',
            initialfile=export.default_name('mihenk-kayitlar', '.xlsx'),
            initialdir=str(store.exports_dir()), filetypes=[(t('Excel kitabı'), '*.xlsx')])
        if not path:
            return
        made = {}

        def build():
            made['path'] = export.to_xlsx(self.conn, path, keys, self.days)
            made['certificates'] = self._copy_certificates(pathlib.Path(path).parent)
        if not self.run(build):
            return
        self._done(made)

    def to_csv(self) -> None:
        keys = self.keys()
        if not keys:
            messagebox.showinfo(t('Seçim yok'), t('En az bir tablo seçin.'), parent=self)
            return
        folder = filedialog.askdirectory(parent=self, title=t('CSV klasörü'),
                                         initialdir=str(store.exports_dir()))
        if not folder:
            return
        target = pathlib.Path(folder) / export.default_name('mihenk-csv', '')
        made = {}

        def build():
            files = export.to_csv(self.conn, target, keys, self.days)
            made['path'] = target
            made['files'] = len(files)
            made['certificates'] = self._copy_certificates(target)
        if not self.run(build):
            return
        self._done(made)

    def to_html(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self, title=t('Yazdırılabilir rapor'), defaultextension='.html',
            initialfile=export.default_name('mihenk-rapor', '.html'),
            initialdir=str(store.exports_dir()), filetypes=[(t('HTML raporu'), '*.html')])
        if not path:
            return
        made = {}

        def build():
            made['path'] = export.to_html(self.conn, path, self.keys(), self.days)
            made['certificates'] = self._copy_certificates(pathlib.Path(path).parent)
        if not self.run(build):
            return
        self._done(made, open_it=True)

    def _done(self, made: dict, open_it=False) -> None:
        path = made.get('path')
        text = t('Hazır: %s') % path
        if made.get('files'):
            text += '  (%d dosya)' % made['files']
        if made.get('certificates'):
            text += t('  ·  %d sertifika kopyalandı') % made['certificates']
        self.status.configure(text=text)
        self.app.toast(t('Dışa aktarıldı: %s') % pathlib.Path(str(path)).name)
        if open_it and path:
            _open_path(path, self)


def _open_path(path, parent=None) -> None:
    """Dosyayi isletim sisteminin varsayilan uygulamasiyla acar."""
    try:
        if sys.platform == 'win32':
            os.startfile(str(path))                        # noqa: S606
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', str(path)])
        else:
            subprocess.Popen(['xdg-open', str(path)])
    except Exception as exc:
        messagebox.showinfo(t('Dosya'), '%s\n\n(%s)' % (path, exc), parent=parent)
