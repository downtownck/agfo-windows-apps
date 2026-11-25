# -*- coding: utf-8 -*-
"""Gorunum: renk paleti, yazi tipleri ve ttk bicemleri.

Acik ve koyu iki palet. Butun ekranlar rengi buradan alir; hicbir ekran kendi
rengini yazmaz, boylece tema degisince her yer birlikte doner.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

LIGHT = {
    'bg': '#f4f5f7',
    'surface': '#ffffff',
    'surface_alt': '#fafbfc',
    'sidebar': '#1f2733',
    'sidebar_text': '#aeb9c7',
    'sidebar_active': '#2b3442',
    'border': '#dde1e6',
    'text': '#1b2027',
    'muted': '#6b7480',
    'accent': '#2f6fd0',
    'accent_text': '#ffffff',
    'ok': '#1f7a3d',
    'ok_bg': '#e6f4ea',
    'warn': '#9a5b00',
    'warn_bg': '#fdf2e0',
    'alert': '#b3261e',
    'alert_bg': '#fcebea',
    'info': '#1d5c8f',
    'info_bg': '#e8f0f8',
    'neutral': '#45505e',
    'neutral_bg': '#eef0f3',
    'row_alt': '#f7f8fa',
    'selection': '#dbe8fb',
}

DARK = {
    'bg': '#151a21',
    'surface': '#1d242d',
    'surface_alt': '#222a34',
    'sidebar': '#11161c',
    'sidebar_text': '#8f9bab',
    'sidebar_active': '#1d242d',
    'border': '#2e3742',
    'text': '#e6eaef',
    'muted': '#97a2b0',
    'accent': '#5a9bf0',
    'accent_text': '#0f141a',
    'ok': '#6fd38d',
    'ok_bg': '#1b3325',
    'warn': '#e2a856',
    'warn_bg': '#352a17',
    'alert': '#f08279',
    'alert_bg': '#3a1f1d',
    'info': '#79b4ef',
    'info_bg': '#1b2b3a',
    'neutral': '#b4bdc8',
    'neutral_bg': '#262e38',
    'row_alt': '#1a212a',
    'selection': '#27374a',
}

# Durum anahtari -> (yazi rengi anahtari, zemin rengi anahtari)
TONES = {
    'active': ('ok', 'ok_bg'),
    'pass': ('ok', 'ok_bg'),
    'completed': ('ok', 'ok_bg'),
    'closed': ('ok', 'ok_bg'),
    'quarantined': ('alert', 'alert_bg'),
    'fail': ('alert', 'alert_bg'),
    'rejected': ('alert', 'alert_bg'),
    'high': ('alert', 'alert_bg'),
    'stops_production': ('alert', 'alert_bg'),
    'open': ('warn', 'warn_bg'),
    'on_hold': ('warn', 'warn_bg'),
    'conditional': ('warn', 'warn_bg'),
    'out_of_service': ('warn', 'warn_bg'),
    'in_progress': ('info', 'info_bg'),
    'assigned': ('info', 'info_bg'),
    'triaged': ('info', 'info_bg'),
    'converted': ('info', 'info_bg'),
    'result_entered': ('info', 'info_bg'),
    'new': ('neutral', 'neutral_bg'),
    'planned': ('neutral', 'neutral_bg'),
    'normal': ('neutral', 'neutral_bg'),
    'low': ('neutral', 'neutral_bg'),
    'retired': ('muted', 'neutral_bg'),
    'cancelled': ('muted', 'neutral_bg'),
}

_PALETTE = dict(LIGHT)
_MODE = 'light'


def palette() -> dict:
    """Yururlukteki renk paleti."""
    return _PALETTE


def mode() -> str:
    return _MODE


def color(key: str) -> str:
    return _PALETTE.get(key, _PALETTE['text'])


def tone(state: str) -> tuple:
    """Bir durum anahtarinin (yazi, zemin) rengi."""
    fg_key, bg_key = TONES.get(state, ('neutral', 'neutral_bg'))
    return _PALETTE[fg_key], _PALETTE[bg_key]


def enable_dpi_awareness() -> None:
    """Windows'ta yuksek DPI ekranlarda bulanik arayuzu onler."""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def fonts(root) -> dict:
    """Uygulamanin yazi tipleri. Windows'ta Segoe UI, yoksa sistem varsayilani."""
    family = 'Segoe UI'
    available = set(tkfont.families(root))
    if family not in available:
        for candidate in ('DejaVu Sans', 'Noto Sans', 'Helvetica', 'TkDefaultFont'):
            if candidate in available or candidate == 'TkDefaultFont':
                family = candidate
                break
    return {
        'body': (family, 10),
        'body_bold': (family, 10, 'bold'),
        'small': (family, 9),
        'tiny': (family, 8),
        'heading': (family, 15, 'bold'),
        'title': (family, 20, 'bold'),
        'metric': (family, 24, 'bold'),
        'mono': ('Consolas' if 'Consolas' in available else 'TkFixedFont', 10),
    }


def apply(root: tk.Misc, requested: str = 'light') -> dict:
    """Temayi kurar ve palete doner. Her tema degisiminde yeniden cagrilir."""
    global _PALETTE, _MODE
    _MODE = 'dark' if requested == 'dark' else 'light'
    _PALETTE = dict(DARK if _MODE == 'dark' else LIGHT)

    p = _PALETTE
    f = fonts(root)
    style = ttk.Style(root)
    try:
        style.theme_use('clam')
    except tk.TclError:
        pass

    root.configure(background=p['bg'])
    root.option_add('*Font', f['body'])

    style.configure('.', background=p['bg'], foreground=p['text'], font=f['body'],
                    bordercolor=p['border'], focuscolor=p['accent'])
    style.configure('TFrame', background=p['bg'])
    style.configure('TLabel', background=p['bg'], foreground=p['text'])
    style.configure('Muted.TLabel', background=p['bg'], foreground=p['muted'], font=f['small'])
    style.configure('Title.TLabel', background=p['bg'], foreground=p['text'], font=f['title'])
    style.configure('Heading.TLabel', background=p['bg'], foreground=p['text'], font=f['heading'])
    style.configure('Alert.TLabel', background=p['bg'], foreground=p['alert'], font=f['body_bold'])

    # --- yuzeyler
    style.configure('Surface.TFrame', background=p['surface'])
    style.configure('Surface.TLabel', background=p['surface'], foreground=p['text'])
    style.configure('SurfaceMuted.TLabel', background=p['surface'], foreground=p['muted'], font=f['small'])
    style.configure('SurfaceHeading.TLabel', background=p['surface'], foreground=p['text'], font=f['heading'])
    style.configure('Metric.TLabel', background=p['surface'], foreground=p['text'], font=f['metric'])
    style.configure('MetricAlert.TLabel', background=p['surface'], foreground=p['alert'], font=f['metric'])
    style.configure('Card.TFrame', background=p['surface'], relief='flat')
    style.configure('CardAlert.TFrame', background=p['surface'], relief='flat')

    # --- kenar cubugu
    style.configure('Sidebar.TFrame', background=p['sidebar'])
    style.configure('SidebarBrand.TLabel', background=p['sidebar'], foreground='#ffffff',
                    font=(f['heading'][0], 16, 'bold'))
    style.configure('SidebarVersion.TLabel', background=p['sidebar'], foreground=p['sidebar_text'],
                    font=f['tiny'])
    style.configure('Nav.TButton', background=p['sidebar'], foreground=p['sidebar_text'],
                    font=f['body'], borderwidth=0, relief='flat', anchor='w', padding=(16, 10))
    style.map('Nav.TButton',
              background=[('active', p['sidebar_active'])],
              foreground=[('active', '#ffffff')])
    style.configure('NavActive.TButton', background=p['sidebar_active'], foreground='#ffffff',
                    font=f['body_bold'], borderwidth=0, relief='flat', anchor='w', padding=(16, 10))
    style.map('NavActive.TButton', background=[('active', p['sidebar_active'])],
              foreground=[('active', '#ffffff')])

    # --- dugmeler
    style.configure('TButton', background=p['surface'], foreground=p['text'], font=f['body'],
                    borderwidth=1, relief='flat', padding=(12, 6))
    style.map('TButton', background=[('active', p['surface_alt']), ('disabled', p['bg'])],
              foreground=[('disabled', p['muted'])])
    style.configure('Accent.TButton', background=p['accent'], foreground=p['accent_text'],
                    font=f['body_bold'], borderwidth=0, padding=(14, 7))
    style.map('Accent.TButton', background=[('active', p['info']), ('disabled', p['neutral_bg'])],
              foreground=[('disabled', p['muted'])])
    style.configure('Danger.TButton', background=p['surface'], foreground=p['alert'],
                    font=f['body'], borderwidth=1, padding=(12, 6))
    style.map('Danger.TButton', background=[('active', p['alert_bg'])])
    style.configure('Ghost.TButton', background=p['bg'], foreground=p['accent'], font=f['body'],
                    borderwidth=0, padding=(8, 4))
    style.map('Ghost.TButton', background=[('active', p['bg'])], foreground=[('active', p['info'])])

    # --- girdiler
    for name in ('TEntry', 'TSpinbox'):
        style.configure(name, fieldbackground=p['surface'], background=p['surface'],
                        foreground=p['text'], bordercolor=p['border'], insertcolor=p['text'],
                        borderwidth=1, padding=5)
        style.map(name, bordercolor=[('focus', p['accent'])])
    style.configure('TCombobox', fieldbackground=p['surface'], background=p['surface'],
                    foreground=p['text'], bordercolor=p['border'], arrowcolor=p['muted'],
                    borderwidth=1, padding=4)
    style.map('TCombobox', fieldbackground=[('readonly', p['surface'])],
              bordercolor=[('focus', p['accent'])])
    root.option_add('*TCombobox*Listbox.background', p['surface'])
    root.option_add('*TCombobox*Listbox.foreground', p['text'])
    root.option_add('*TCombobox*Listbox.selectBackground', p['accent'])
    root.option_add('*TCombobox*Listbox.selectForeground', p['accent_text'])

    style.configure('TCheckbutton', background=p['bg'], foreground=p['text'])
    style.map('TCheckbutton', background=[('active', p['bg'])])
    style.configure('Surface.TCheckbutton', background=p['surface'], foreground=p['text'])
    style.map('Surface.TCheckbutton', background=[('active', p['surface'])])
    style.configure('TRadiobutton', background=p['bg'], foreground=p['text'])

    # --- tablo
    row_height = 26
    style.configure('Treeview', background=p['surface'], fieldbackground=p['surface'],
                    foreground=p['text'], rowheight=row_height, borderwidth=0, font=f['body'])
    style.map('Treeview', background=[('selected', p['selection'])],
              foreground=[('selected', p['text'])])
    style.configure('Treeview.Heading', background=p['surface_alt'], foreground=p['muted'],
                    font=f['small'], relief='flat', padding=(8, 6))
    style.map('Treeview.Heading', background=[('active', p['neutral_bg'])])

    style.configure('TNotebook', background=p['bg'], borderwidth=0, tabmargins=(0, 4, 0, 0))
    style.configure('TNotebook.Tab', background=p['bg'], foreground=p['muted'],
                    padding=(14, 7), borderwidth=0, font=f['body'])
    style.map('TNotebook.Tab', background=[('selected', p['surface'])],
              foreground=[('selected', p['text'])])

    style.configure('TSeparator', background=p['border'])
    style.configure('Vertical.TScrollbar', background=p['surface_alt'], troughcolor=p['bg'],
                    bordercolor=p['bg'], arrowcolor=p['muted'], borderwidth=0)
    style.configure('Horizontal.TScrollbar', background=p['surface_alt'], troughcolor=p['bg'],
                    bordercolor=p['bg'], arrowcolor=p['muted'], borderwidth=0)
    style.configure('Horizontal.TProgressbar', background=p['accent'], troughcolor=p['neutral_bg'],
                    borderwidth=0)

    style.configure('Status.TFrame', background=p['surface'])
    style.configure('Status.TLabel', background=p['surface'], foreground=p['muted'], font=f['small'])
    style.configure('Footer.TLabel', background=p['bg'], foreground=p['muted'], font=f['tiny'])

    return p
