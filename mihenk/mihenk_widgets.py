# -*- coding: utf-8 -*-
"""Yeniden kullanilan arayuz parcalari: kart, rozet, tablo, tarih kutusu, form satiri."""
from __future__ import annotations

import calendar
import datetime
import tkinter as tk
from tkinter import ttk

import mihenk_theme as theme
import mihenk_validate as v

MONTHS = ('Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
          'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık')
WEEKDAYS = ('Pt', 'Sa', 'Ça', 'Pe', 'Cu', 'Ct', 'Pz')


class Card(ttk.Frame):
    """Panodaki sayi karti: buyuk deger, altinda etiket."""

    def __init__(self, parent, label: str, value='0', alert=False, on_click=None):
        super().__init__(parent, style='Card.TFrame', padding=(16, 14))
        p = theme.palette()
        self.configure(borderwidth=0)
        self._stripe = tk.Frame(self, width=3, background=p['alert'] if alert else p['accent'])
        self._stripe.pack(side='left', fill='y', padx=(0, 12))
        box = ttk.Frame(self, style='Surface.TFrame')
        box.pack(side='left', fill='both', expand=True)
        self.value = ttk.Label(box, text=str(value),
                               style='MetricAlert.TLabel' if alert else 'Metric.TLabel')
        self.value.pack(anchor='w')
        self.label = ttk.Label(box, text=label, style='SurfaceMuted.TLabel')
        self.label.pack(anchor='w', pady=(2, 0))
        if on_click:
            for widget in (self, box, self.value, self.label):
                widget.bind('<Button-1>', lambda _e: on_click())
                widget.configure(cursor='hand2')

    def set_value(self, value, alert=False) -> None:
        self.value.configure(text=str(value), style='MetricAlert.TLabel' if alert else 'Metric.TLabel')
        self._stripe.configure(background=theme.color('alert') if alert else theme.color('accent'))


class Badge(tk.Label):
    """Durum rozeti."""

    def __init__(self, parent, text: str, state: str = 'normal', surface=False):
        fg, bg = theme.tone(state)
        super().__init__(parent, text=' %s ' % text, background=bg, foreground=fg,
                         font=(theme.fonts(parent)['small'][0], 9, 'bold'), padx=6, pady=1,
                         bd=0, highlightthickness=0)

    def set(self, text: str, state: str) -> None:
        fg, bg = theme.tone(state)
        self.configure(text=' %s ' % text, background=bg, foreground=fg)


class DataTable(ttk.Frame):
    """Treeview sarmalayicisi: siralama, cift tikla acma, satir renklendirme."""

    def __init__(self, parent, columns, on_open=None, on_select=None, height=14):
        super().__init__(parent, style='Surface.TFrame')
        self._columns = list(columns)        # (anahtar, baslik, genislik, hizalama)
        self._on_open = on_open
        self._on_select = on_select
        self._rows = {}
        self._sort_key = None
        self._sort_desc = False

        keys = [c[0] for c in self._columns]
        self.tree = ttk.Treeview(self, columns=keys, show='headings', height=height,
                                 selectmode='browse')
        for column in self._columns:
            key, title, width = column[0], column[1], column[2]
            anchor = column[3] if len(column) > 3 else 'w'
            self.tree.heading(key, text=title, anchor=anchor,
                              command=lambda k=key: self._sort_by(k))
            self.tree.column(key, width=width, anchor=anchor, stretch=(width >= 180))
        bar = ttk.Scrollbar(self, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.pack(side='left', fill='both', expand=True)
        bar.pack(side='right', fill='y')

        self.tree.bind('<Double-1>', self._opened)
        self.tree.bind('<Return>', self._opened)
        self.tree.bind('<<TreeviewSelect>>', self._selected)
        self.refresh_tags()

    def refresh_tags(self) -> None:
        """Tema degisince satir renklerini yeniden tanimlar."""
        p = theme.palette()
        self.tree.tag_configure('odd', background=p['row_alt'])
        self.tree.tag_configure('even', background=p['surface'])
        self.tree.tag_configure('alert', foreground=p['alert'])
        self.tree.tag_configure('muted', foreground=p['muted'])
        self.tree.tag_configure('ok', foreground=p['ok'])

    def set_rows(self, rows, key='id', values=None, tag_of=None) -> None:
        """Satirlari yeniler. values(row) kolon metinlerini, tag_of(row) rengi verir."""
        selected = self.selected_id()
        self.tree.delete(*self.tree.get_children())
        self._rows = {}
        if self._sort_key:
            rows = sorted(rows, key=lambda r: _sort_value(r.get(self._sort_key)),
                          reverse=self._sort_desc)
        for index, row in enumerate(rows):
            row_id = str(row.get(key))
            cells = values(row) if values else [row.get(c[0], '') for c in self._columns]
            tags = ['odd' if index % 2 else 'even']
            extra = tag_of(row) if tag_of else None
            if extra:
                tags.append(extra)
            self.tree.insert('', 'end', iid=row_id, values=cells, tags=tuple(tags))
            self._rows[row_id] = row
        if selected and selected in self._rows:
            self.tree.selection_set(selected)
            self.tree.see(selected)

    def selected_id(self):
        picked = self.tree.selection()
        return picked[0] if picked else None

    def selected_row(self):
        picked = self.selected_id()
        return self._rows.get(picked) if picked else None

    def row_count(self) -> int:
        return len(self._rows)

    def _sort_by(self, key) -> None:
        if self._sort_key == key:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_key, self._sort_desc = key, False
        rows = list(self._rows.values())
        self.set_rows(rows)

    def _opened(self, _event=None):
        if self._on_open and self.selected_row():
            self._on_open(self.selected_row())
        return 'break'

    def _selected(self, _event=None):
        if self._on_select:
            self._on_select(self.selected_row())


def _sort_value(value):
    """Karisik tipleri karsilastirilabilir hale getirir."""
    if value is None:
        return (1, '')
    if isinstance(value, (int, float)):
        return (0, float(value))
    return (0, str(value).lower())


class DateEntry(ttk.Frame):
    """Tarih kutusu: elle yazilabilir, yanindaki dugme takvim acar."""

    def __init__(self, parent, with_time=False, width=18):
        super().__init__(parent)
        self.with_time = with_time
        self.var = tk.StringVar()
        self.entry = ttk.Entry(self, textvariable=self.var, width=width)
        self.entry.pack(side='left')
        ttk.Button(self, text='Takvim', style='Ghost.TButton', width=7,
                   command=self.open_calendar).pack(side='left', padx=(4, 0))
        ttk.Button(self, text='Şimdi', style='Ghost.TButton', width=6,
                   command=self.set_now).pack(side='left')

    def get(self):
        """Kayit bicimine cevrilmis deger; bos ise None."""
        return v.stamp(self.var.get())

    def get_raw(self) -> str:
        return self.var.get().strip()

    def set(self, value) -> None:
        parsed = v.parse(value)
        if not parsed:
            self.var.set('')
            return
        self.var.set(parsed.strftime('%Y-%m-%d %H:%M' if self.with_time else '%Y-%m-%d'))

    def set_now(self) -> None:
        self.set(v.now())

    def clear(self) -> None:
        self.var.set('')

    def open_calendar(self) -> None:
        CalendarPopup(self)


class CalendarPopup(tk.Toplevel):
    """Kucuk ay takvimi."""

    def __init__(self, owner: DateEntry):
        super().__init__(owner)
        self.owner = owner
        self.transient(owner.winfo_toplevel())
        self.title('Tarih seç')
        self.resizable(False, False)
        self.configure(background=theme.color('surface'))

        current = v.parse(owner.var.get()) or datetime.datetime.now()
        self.year, self.month = current.year, current.month
        self.picked_time = current.strftime('%H:%M') if owner.with_time else '00:00'

        head = ttk.Frame(self, style='Surface.TFrame', padding=(8, 8, 8, 4))
        head.pack(fill='x')
        ttk.Button(head, text='‹', width=3, command=self.prev_month).pack(side='left')
        self.title_label = ttk.Label(head, text='', style='SurfaceHeading.TLabel', width=16,
                                     anchor='center')
        self.title_label.pack(side='left', padx=6)
        ttk.Button(head, text='›', width=3, command=self.next_month).pack(side='left')

        self.grid_frame = ttk.Frame(self, style='Surface.TFrame', padding=(8, 0, 8, 8))
        self.grid_frame.pack(fill='both', expand=True)

        if owner.with_time:
            foot = ttk.Frame(self, style='Surface.TFrame', padding=(8, 0, 8, 8))
            foot.pack(fill='x')
            ttk.Label(foot, text='Saat', style='SurfaceMuted.TLabel').pack(side='left')
            self.time_var = tk.StringVar(value=self.picked_time)
            ttk.Entry(foot, textvariable=self.time_var, width=7).pack(side='left', padx=6)
        else:
            self.time_var = None

        self.draw()
        self.bind('<Escape>', lambda _e: self.destroy())
        self.update_idletasks()
        x = owner.winfo_rootx()
        y = owner.winfo_rooty() + owner.winfo_height() + 2
        self.geometry('+%d+%d' % (x, y))
        self.grab_set()

    def prev_month(self) -> None:
        self.month -= 1
        if self.month < 1:
            self.month, self.year = 12, self.year - 1
        self.draw()

    def next_month(self) -> None:
        self.month += 1
        if self.month > 12:
            self.month, self.year = 1, self.year + 1
        self.draw()

    def draw(self) -> None:
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self.title_label.configure(text='%s %d' % (MONTHS[self.month - 1], self.year))
        for index, name in enumerate(WEEKDAYS):
            ttk.Label(self.grid_frame, text=name, style='SurfaceMuted.TLabel', width=4,
                      anchor='center').grid(row=0, column=index, padx=1, pady=(0, 2))
        today = datetime.date.today()
        for week_index, week in enumerate(calendar.Calendar(firstweekday=0).monthdayscalendar(
                self.year, self.month), start=1):
            for day_index, day in enumerate(week):
                if not day:
                    continue
                style = 'Accent.TButton' if (day, self.month, self.year) == (
                    today.day, today.month, today.year) else 'TButton'
                ttk.Button(self.grid_frame, text=str(day), width=4, style=style,
                           command=lambda d=day: self.choose(d)).grid(
                    row=week_index, column=day_index, padx=1, pady=1)

    def choose(self, day: int) -> None:
        clock = (self.time_var.get().strip() if self.time_var else '') or '00:00'
        if len(clock) == 5 and clock[2] == ':':
            stamp = '%04d-%02d-%02d %s' % (self.year, self.month, day, clock)
        else:
            stamp = '%04d-%02d-%02d 00:00' % (self.year, self.month, day)
        self.owner.set(stamp)
        self.destroy()


class FormGrid(ttk.Frame):
    """Etiket + alan satirlarini duzenli hizalar."""

    def __init__(self, parent, label_width=22, surface=False):
        super().__init__(parent, style='Surface.TFrame' if surface else 'TFrame')
        self.label_width = label_width
        self.surface = surface
        self._row = 0
        self.columnconfigure(1, weight=1)

    def add(self, label: str, widget, hint: str = '', span=False):
        """Bir satir ekler ve alani geri dondurur."""
        style = 'Surface.TLabel' if self.surface else 'TLabel'
        muted = 'SurfaceMuted.TLabel' if self.surface else 'Muted.TLabel'
        ttk.Label(self, text=label, style=style, width=self.label_width, anchor='w').grid(
            row=self._row, column=0, sticky='nw', pady=5, padx=(0, 10))
        widget.grid(row=self._row, column=1, sticky='ew' if span else 'w', pady=5)
        self._row += 1
        if hint:
            ttk.Label(self, text=hint, style=muted, wraplength=460, justify='left').grid(
                row=self._row, column=1, sticky='w', pady=(0, 4))
            self._row += 1
        return widget

    def add_full(self, widget):
        """Iki kolonu da kaplayan bir satir."""
        widget.grid(row=self._row, column=0, columnspan=2, sticky='ew', pady=6)
        self._row += 1
        return widget

    def separator(self, text: str = '') -> None:
        if text:
            style = 'SurfaceHeading.TLabel' if self.surface else 'Heading.TLabel'
            ttk.Label(self, text=text, style=style).grid(row=self._row, column=0, columnspan=2,
                                                         sticky='w', pady=(14, 4))
        else:
            ttk.Separator(self).grid(row=self._row, column=0, columnspan=2, sticky='ew', pady=10)
        self._row += 1


class ScrollArea(ttk.Frame):
    """Dikey kaydirilabilir alan. Icerik .body icine yerlestirilir."""

    def __init__(self, parent, surface=False):
        super().__init__(parent)
        background = theme.color('surface' if surface else 'bg')
        self.canvas = tk.Canvas(self, background=background, highlightthickness=0, bd=0)
        bar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.body = ttk.Frame(self, style='Surface.TFrame' if surface else 'TFrame')
        self._window = self.canvas.create_window((0, 0), window=self.body, anchor='nw')
        self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        bar.pack(side='right', fill='y')
        self.body.bind('<Configure>', self._resize_body)
        self.canvas.bind('<Configure>', self._resize_canvas)
        self.canvas.bind('<Enter>', lambda _e: self._bind_wheel(True))
        self.canvas.bind('<Leave>', lambda _e: self._bind_wheel(False))

    def _resize_body(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _resize_canvas(self, event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)

    def _bind_wheel(self, attach: bool) -> None:
        if attach:
            self.canvas.bind_all('<MouseWheel>', self._wheel)
            self.canvas.bind_all('<Button-4>', self._wheel)
            self.canvas.bind_all('<Button-5>', self._wheel)
        else:
            self.canvas.unbind_all('<MouseWheel>')
            self.canvas.unbind_all('<Button-4>')
            self.canvas.unbind_all('<Button-5>')

    def _wheel(self, event) -> None:
        if getattr(event, 'num', None) == 4:
            step = -1
        elif getattr(event, 'num', None) == 5:
            step = 1
        else:
            step = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(step, 'units')


def text_box(parent, height=4, width=52) -> tk.Text:
    """Tema ile uyumlu cok satirli metin kutusu."""
    p = theme.palette()
    widget = tk.Text(parent, height=height, width=width, wrap='word', relief='flat',
                     background=p['surface'], foreground=p['text'], insertbackground=p['text'],
                     highlightthickness=1, highlightbackground=p['border'],
                     highlightcolor=p['accent'], padx=6, pady=5,
                     font=theme.fonts(parent)['body'])
    return widget


def read_text(widget: tk.Text) -> str:
    return widget.get('1.0', 'end').strip()


def write_text(widget: tk.Text, value) -> None:
    state = str(widget.cget('state'))
    widget.configure(state='normal')
    widget.delete('1.0', 'end')
    widget.insert('1.0', value or '')
    widget.configure(state=state)


class Combo(ttk.Combobox):
    """Anahtar/etiket ciftleriyle calisan acilir liste."""

    def __init__(self, parent, pairs, width=28, value=None):
        self._pairs = []
        super().__init__(parent, state='readonly', width=width)
        self.set_pairs(pairs, value)

    def set_pairs(self, pairs, value=None) -> None:
        """pairs: (anahtar, etiket) listesi ya da sozluk."""
        if isinstance(pairs, dict):
            pairs = list(pairs.items())
        self._pairs = [(key, str(label)) for key, label in pairs]
        self.configure(values=[label for _k, label in self._pairs])
        self.set_key(value if value is not None else (self._pairs[0][0] if self._pairs else None))

    def set_key(self, key) -> None:
        for index, (candidate, label) in enumerate(self._pairs):
            if str(candidate) == str(key):
                self.current(index)
                return
        if self._pairs:
            self.current(0)

    def key(self):
        index = self.current()
        if index < 0 or index >= len(self._pairs):
            return None
        return self._pairs[index][0]
