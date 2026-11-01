"""AGFO Mic Monitor - mikrofonu kulakliktan dusuk gecikmeyle dinleme ve ayni anda kayit (Windows GUI, tek EXE).

Windows'un "Bu cihazi dinle" ozelligi sesi Windows ses motorundan ve efektlerden (Voice Clarity, Nahimic,
iyilestirmeler) gecirdigi icin 50-100+ ms gecikir. Mic Monitor akisi WASAPI ozel modda ve RAW secenegiyle
acar: ses dogrudan mikrofondan kulakliga gider (tipik 6-20 ms). Ayni ses istenirse WAV olarak kaydedilir.

Ses PortAudio (sounddevice) ile islenir; ayrintilar mic_engine.py'de. Uygulama GitHub'daki
downtownck/agfo-windows-apps deposundan kendini tek tikla gunceller (mic_update.py).

Komut satiri: --smoke <rapor.txt> (derleme oz-testi), --apply-update <hedef> --wait-pid <pid> (guncelleyici).
"""
import ctypes
import os
import pathlib
import queue
import subprocess
import sys
import threading
import time

IS_WIN = sys.platform == 'win32'


def _enable_dpi_awareness():
    if not IS_WIN:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


_enable_dpi_awareness()

import tkinter as tk  # noqa: E402
from tkinter import filedialog, messagebox, ttk  # noqa: E402

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import mic_core as core  # noqa: E402
import mic_engine as eng  # noqa: E402
import mic_fx  # noqa: E402
import mic_update as upd  # noqa: E402
import agfo_github_update as ghu  # noqa: E402

VERSION = core.VERSION
FROZEN = bool(getattr(sys, 'frozen', False))
BG, PANEL, PANEL2, FG, MUTED, ACCENT = '#0a1425', '#12243b', '#192e48', '#ecf3ff', '#a5b6ce', '#49b3ef'
WARN, OK_C, BAD_C = '#e2b356', '#6fd39b', '#ff8a80'
POLL_MS = 33
DEFAULT_LABEL = '(Windows varsayilani)'
MISSING_SUFFIX = '  — bagli degil, varsayilan kullaniliyor'
DEVICE_CHECK_S = 1.0          # aygit degisikligi (kulaklik takildi / cikarildi) kontrol araligi
STALL_TICKS = 3               # 3 x 0,5 sn geri cagri gelmezse akis takilmis sayilir
RECOVER_DELAYS_MS = (400, 1500, 4000)
XRUN_LIMIT = 6                # 10 sn'de bu kadar kesinti (cizirti) olursa tampon bir kademe buyutulur
RATE_CHOICES = ('44100', '48000', '96000')


class App(tk.Tk):
    def __init__(self, sd=None):
        super().__init__()
        self.cfg = core.load_settings()
        self.busy = False
        self.gh_result = None
        self.messages = queue.Queue()
        self.engine = None
        self.engine_error = None
        self.monitoring = False
        self.meter = -60.0
        self.meter_hold = -60.0
        self.hold_until = 0.0
        self.clip_until = 0.0
        self.restarts = []
        self._restart_job = None
        self._last_stats = 0.0
        self._stall = 0
        self._recovering = False
        self._dev_sig = eng.device_signature()
        self._sig_latest = self._dev_sig
        self._dev_checked = 0.0
        self._dev_job = None
        self._auto_buf_at = 0.0
        self._watch_alive = True
        # aygit listesi sorgusu arayuz dongusunu (ve dolayisiyla ses is parcacigini) bekletmesin
        threading.Thread(target=self._device_watch_loop, name='micmon-devwatch', daemon=True).start()
        self._paused_unplug = ''          # kulaklik cikarildigi icin duraklatildi: onceki cikis adi
        self.devices = {'inputs': [], 'outputs': [], 'default_input': '', 'default_output': '', 'apis': []}
        try:
            self.engine = eng.Engine(sd or eng.load_sounddevice(self.cfg.get('enable_asio', False)))
            self.devices = self.engine.list_devices()
        except Exception as e:      # PortAudio yuklenemedi: arayuz yine acilir, hata gosterilir
            self.engine_error = e
            core.log_line('engine load failed: %r' % e)

        self.title('AGFO Mic Monitor ' + VERSION)
        self.scale = max(1.0, self.winfo_fpixels('1i') / 96.0)
        self.configure(bg=BG)
        self.resizable(False, False)
        self._set_icon()
        self._style()
        self._build()
        self._fill_from_cfg()
        self._update_warnings()
        self.protocol('WM_DELETE_WINDOW', self._on_close)
        self._poll_job = self.after(POLL_MS, self._poll)
        if self.cfg.get('auto_update_check', True) and FROZEN:
            # 1.0.3: acilista her seferinde gercekten denetle (6 saatlik onbellek yeni surumu gizliyordu),
            # uygulama acik kaldikca da periyodik denetle
            self.after(2500, lambda: self.gh_check(force=True, silent=True))
            self.after(upd.PERIODIC_CHECK_MS, self._gh_periodic)
        if self.engine_error is not None:
            self._status('Ses kutuphanesi yuklenemedi: %s' % self.engine_error, BAD_C)
        elif self.cfg.get('autostart'):
            self.after(500, self.start)
        if FROZEN:
            self.after(600, self._first_run_install)

    # ---------------------------------------------------------------- stil / iskelet
    def _icon_path(self):
        if FROZEN:
            return pathlib.Path(getattr(sys, '_MEIPASS', '.')) / 'assets' / 'agfo-micmon.ico'
        return pathlib.Path(__file__).resolve().parent / 'assets' / 'agfo-micmon.ico'

    def _set_icon(self):
        ico = self._icon_path()
        if IS_WIN and ico.is_file():
            try:
                self.iconbitmap(default=str(ico))
            except Exception:
                pass

    def _style(self):
        s = ttk.Style(self)
        s.theme_use('clam')
        s.configure('.', background=PANEL, foreground=FG, fieldbackground=PANEL2, font=('Segoe UI', 10))
        s.configure('TCombobox', fieldbackground=PANEL2, background=PANEL2, foreground=FG, arrowcolor=FG)
        s.map('TCombobox', fieldbackground=[('readonly', PANEL2)], foreground=[('readonly', FG)],
              selectbackground=[('readonly', PANEL2)], selectforeground=[('readonly', FG)])
        self.option_add('*TCombobox*Listbox.background', PANEL2)
        self.option_add('*TCombobox*Listbox.foreground', FG)
        self.option_add('*TCombobox*Listbox.selectBackground', '#285475')
        s.configure('TEntry', fieldbackground=PANEL2, foreground=FG, insertcolor=FG)
        s.configure('TCheckbutton', background=PANEL, foreground=FG)
        s.map('TCheckbutton', background=[('active', PANEL)])
        s.configure('Horizontal.TScale', background=PANEL, troughcolor=PANEL2)

    def _btn(self, parent, text, cmd, kind='normal', **kw):
        colors = {'normal': '#285475', 'danger': '#685229', 'ghost': PANEL2, 'go': '#1f6a4a', 'rec': '#7a2a2a'}
        return tk.Button(parent, text=text, command=cmd, bg=colors[kind], fg='#ffffff', activebackground=ACCENT,
                         relief='flat', cursor='hand2', padx=12, pady=6, font=('Segoe UI', 9, 'bold'),
                         disabledforeground='#7f8ea3', **kw)

    def _lbl(self, parent, text, muted=True, **kw):
        return tk.Label(parent, text=text, fg=MUTED if muted else FG, bg=PANEL, font=('Segoe UI', 9),
                        justify='left', anchor='w', **kw)

    def _section(self, title, parent=None):
        f = tk.Frame(parent or self, bg=PANEL, padx=10, pady=8)
        if parent is None:
            f.pack(fill='x', padx=22, pady=(0, 10))
        else:
            parent.add(f, text='  %s  ' % title.capitalize())
            return f                      # sekmenin adi zaten baslik
        tk.Label(f, text=title, fg=ACCENT, bg=PANEL, font=('Segoe UI', 9, 'bold')).grid(row=0, column=0, columnspan=4, sticky='w')
        return f

    def _build(self):
        top = tk.Frame(self, bg=BG); top.pack(fill='x', padx=22, pady=(16, 8))
        tk.Label(top, text='AGFO', fg=ACCENT, bg=BG, font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        tk.Label(top, text='Mic Monitor', fg=FG, bg=BG, font=('Segoe UI', 22, 'bold')).pack(anchor='w')
        tk.Label(top, text='Mikrofonu kulakliktan gecikmesiz dinleyin, ayni anda kaydedin.',
                 fg=MUTED, bg=BG, font=('Segoe UI', 10)).pack(anchor='w', pady=(2, 0))

        self.gh_banner = tk.Frame(self, bg='#1d4d3a', padx=12, pady=7)
        self.gh_banner_text = tk.StringVar(value='')
        tk.Label(self.gh_banner, textvariable=self.gh_banner_text, fg='#ffffff', bg='#1d4d3a',
                 font=('Segoe UI', 10, 'bold')).pack(side='left')
        for txt, cmd, bg in (('Bu surumu atla', self.gh_skip, '#2a5f4a'), ('Notlar', self.gh_show_notes, '#2a5f4a'),
                             ('Simdi guncelle', self.gh_update, '#2f8f5f')):
            tk.Button(self.gh_banner, text=txt, command=cmd, bg=bg, fg='#ffffff', relief='flat', padx=12, pady=3,
                      cursor='hand2', activebackground=ACCENT).pack(side='right', padx=(6, 0))

        pad = {'padx': 6, 'pady': 4}
        # -- cihazlar
        dev = self._section('CIHAZLAR')
        self._lbl(dev, 'Mikrofon (giris):').grid(row=1, column=0, sticky='w', **pad)
        self.var_in = tk.StringVar()
        self.cmb_in = ttk.Combobox(dev, textvariable=self.var_in, width=52, state='readonly')
        self.cmb_in.grid(row=1, column=1, columnspan=2, sticky='we', **pad)
        self._lbl(dev, 'Kulaklik (cikis):').grid(row=2, column=0, sticky='w', **pad)
        self.var_out = tk.StringVar()
        self.cmb_out = ttk.Combobox(dev, textvariable=self.var_out, width=52, state='readonly')
        self.cmb_out.grid(row=2, column=1, columnspan=2, sticky='we', **pad)
        b = tk.Frame(dev, bg=PANEL); b.grid(row=1, column=3, rowspan=2, sticky='ns', **pad)
        self._btn(b, 'Yenile', self.refresh_devices, 'ghost').pack(fill='x', pady=(0, 4))
        self._btn(b, 'Windows ses ayarlari', self.open_sound_panel, 'ghost').pack(fill='x')
        for c in (self.cmb_in, self.cmb_out):
            c.bind('<<ComboboxSelected>>', lambda e: self._changed(restart=True))
        self.var_warn = tk.StringVar(value='')
        tk.Label(dev, textvariable=self.var_warn, fg=WARN, bg=PANEL, font=('Segoe UI', 9), justify='left', anchor='w',
                 wraplength=int(640 * self.scale)).grid(row=3, column=0, columnspan=4, sticky='we', padx=6)

        # -- ses
        snd = self._section('SES')
        self._lbl(snd, 'Mikrofon kazanci:').grid(row=1, column=0, sticky='w', **pad)
        self.var_gain = tk.DoubleVar()
        ttk.Scale(snd, from_=-12, to=24, variable=self.var_gain, length=int(330 * self.scale),
                  command=lambda v: self._live()).grid(row=1, column=1, sticky='w', **pad)
        self.lbl_gain = self._lbl(snd, '', muted=False, width=8); self.lbl_gain.grid(row=1, column=2, sticky='w', **pad)
        self._lbl(snd, 'Dinleme sesi:').grid(row=2, column=0, sticky='w', **pad)
        self.var_vol = tk.DoubleVar()
        ttk.Scale(snd, from_=0, to=100, variable=self.var_vol, length=int(330 * self.scale),
                  command=lambda v: self._live()).grid(row=2, column=1, sticky='w', **pad)
        self.lbl_vol = self._lbl(snd, '', muted=False, width=8); self.lbl_vol.grid(row=2, column=2, sticky='w', **pad)
        self.var_mute = tk.BooleanVar()
        ttk.Checkbutton(snd, text='Dinlemeyi sustur (yalniz kaydet)', variable=self.var_mute,
                        command=self._live).grid(row=2, column=3, sticky='w', **pad)
        self._lbl(snd, 'Seviye:').grid(row=3, column=0, sticky='w', **pad)
        self.meter_w, self.meter_h = int(470 * self.scale), int(16 * self.scale)
        self.cv = tk.Canvas(snd, width=self.meter_w, height=self.meter_h, bg=PANEL2, highlightthickness=0)
        self.cv.grid(row=3, column=1, columnspan=2, sticky='w', **pad)
        self.var_db = tk.StringVar(value='')
        tk.Label(snd, textvariable=self.var_db, fg=MUTED, bg=PANEL, font=('Consolas', 9), width=12,
                 anchor='w').grid(row=3, column=3, sticky='w', **pad)

        # -- sekmeler: efektler / gecikme / kayit (pencere ekrana sigsin)
        s = ttk.Style(self)
        s.configure('TNotebook', background=BG, borderwidth=0)
        s.configure('TNotebook.Tab', background=PANEL2, foreground=MUTED, padding=(12, 5), font=('Segoe UI', 9, 'bold'))
        s.map('TNotebook.Tab', background=[('selected', PANEL)], foreground=[('selected', FG)])
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill='x', padx=22, pady=(0, 10))
        self._build_fx(self._section('EFEKTLER', self.tabs), pad)
        st = self._section('GECIKME', self.tabs)
        self._lbl(st, 'Kip:').grid(row=1, column=0, sticky='w', **pad)
        self.var_mode = tk.StringVar()
        cm = ttk.Combobox(st, textvariable=self.var_mode, width=30, state='readonly',
                          values=[core.MODE_LABELS[m] for m in core.MODES])
        cm.grid(row=1, column=1, sticky='w', **pad)
        self._lbl(st, 'Tampon:').grid(row=1, column=2, sticky='e', **pad)
        self.var_buf = tk.StringVar()
        cb = ttk.Combobox(st, textvariable=self.var_buf, width=8, state='readonly',
                          values=['%d ms' % b for b in core.BUFFER_CHOICES_MS])
        cb.grid(row=1, column=3, sticky='w', **pad)
        self._lbl(st, 'Kanal:').grid(row=2, column=0, sticky='w', **pad)
        self.var_ch = tk.StringVar()
        cc = ttk.Combobox(st, textvariable=self.var_ch, width=30, state='readonly',
                          values=[core.CHANNEL_LABELS[c] for c in core.CHANNEL_MODES])
        cc.grid(row=2, column=1, sticky='w', **pad)
        self._lbl(st, 'Ornekleme:').grid(row=2, column=2, sticky='e', **pad)
        self.var_rate = tk.StringVar()
        cr = ttk.Combobox(st, textvariable=self.var_rate, width=8, state='readonly', values=RATE_CHOICES)
        cr.grid(row=2, column=3, sticky='w', **pad)
        for c in (cm, cb, cr):
            c.bind('<<ComboboxSelected>>', lambda e: self._changed(restart=True))
        cc.bind('<<ComboboxSelected>>', lambda e: self._changed(restart=False))
        self.var_share = tk.BooleanVar()
        self.var_asio = tk.BooleanVar()
        self.var_autostart = tk.BooleanVar()
        ttk.Checkbutton(st, text='Diger uygulamalarin sesi de duyulsun (cikisi paylas; gecikme biraz artar)',
                        variable=self.var_share, command=lambda: self._changed(restart=True)).grid(row=3, column=0, columnspan=4, sticky='w', **pad)
        ttk.Checkbutton(st, text='ASIO suruculerini de tara (ASIO4ALL, FlexASIO, ses karti surucusu; yeniden baslatma gerekir)',
                        variable=self.var_asio, command=self._asio_changed).grid(row=4, column=0, columnspan=4, sticky='w', **pad)
        ttk.Checkbutton(st, text='Acilista dinlemeyi baslat', variable=self.var_autostart,
                        command=lambda: self._changed(restart=False)).grid(row=5, column=0, columnspan=4, sticky='w', **pad)

        # -- kayit
        rc = self._section('KAYIT', self.tabs)
        self._lbl(rc, 'Klasor:').grid(row=1, column=0, sticky='w', **pad)
        self.var_dir = tk.StringVar()
        ttk.Entry(rc, textvariable=self.var_dir, width=44).grid(row=1, column=1, sticky='we', **pad)
        self._btn(rc, 'Gozat…', self._browse, 'ghost').grid(row=1, column=2, **pad)
        self._btn(rc, 'Klasoru ac', self._open_folder, 'ghost').grid(row=1, column=3, **pad)
        self._lbl(rc, 'Bit derinligi:').grid(row=2, column=0, sticky='w', **pad)
        self.var_bits = tk.StringVar()
        cbits = ttk.Combobox(rc, textvariable=self.var_bits, width=8, state='readonly', values=('24 bit', '16 bit'))
        cbits.grid(row=2, column=1, sticky='w', **pad)
        cbits.bind('<<ComboboxSelected>>', lambda e: self._changed(restart=False))

        # -- dugmeler
        btns = tk.Frame(self, bg=BG); btns.pack(fill='x', padx=22, pady=(0, 6))
        self.btn_toggle = self._btn(btns, 'Dinlemeyi baslat', self.toggle, 'go'); self.btn_toggle.pack(side='left', padx=(0, 6))
        self.btn_rec = self._btn(btns, '● Kaydi baslat', self.toggle_record, 'rec'); self.btn_rec.pack(side='left', padx=(0, 6))
        self._btn(btns, 'Guncelleme…', self.open_updater, 'normal').pack(side='right')
        self._btn(btns, 'Ayrintilar', self.show_details, 'ghost').pack(side='right', padx=(0, 6))

        stbar = tk.Frame(self, bg=PANEL, padx=12, pady=8); stbar.pack(fill='x', padx=22, pady=(0, 16))
        self.var_status = tk.StringVar(value='Durdu.')
        self.lbl_status = tk.Label(stbar, textvariable=self.var_status, fg=MUTED, bg=PANEL, font=('Segoe UI', 10, 'bold'),
                                   anchor='w', justify='left', wraplength=int(640 * self.scale))
        self.lbl_status.pack(fill='x')
        self.var_info = tk.StringVar(value='')
        tk.Label(stbar, textvariable=self.var_info, fg=MUTED, bg=PANEL, font=('Segoe UI', 9), anchor='w',
                 justify='left', wraplength=int(640 * self.scale)).pack(fill='x', pady=(2, 0))

    def _scale(self, parent, row, col, label, var, lo, hi, fmt, length=150):
        self._lbl(parent, label).grid(row=row, column=col, sticky='w', padx=6, pady=3)
        fr = tk.Frame(parent, bg=PANEL); fr.grid(row=row, column=col + 1, sticky='w', padx=6, pady=3)
        ttk.Scale(fr, from_=lo, to=hi, variable=var, length=int(length * self.scale),
                  command=lambda v: self._fx_live()).pack(side='left')
        lab = tk.Label(fr, text='', fg=FG, bg=PANEL, font=('Segoe UI', 9), width=7, anchor='w')
        lab.pack(side='left', padx=(6, 0))
        self._fx_labels.append((lab, var, fmt))

    def _build_fx(self, fx, pad):
        """Yanki ve reverb: gecikme eklemez (kuru ses aynen gecer, efekt ustune eklenir)."""
        self._fx_labels = []
        self.var_echo_on = tk.BooleanVar()
        self.var_echo_ms = tk.DoubleVar(); self.var_echo_fb = tk.DoubleVar()
        self.var_echo_mix = tk.DoubleVar(); self.var_echo_tone = tk.DoubleVar()
        self.var_rev_on = tk.BooleanVar(); self.var_rev_type = tk.StringVar()
        self.var_rev_time = tk.DoubleVar(); self.var_rev_mix = tk.DoubleVar()
        self.var_rev_tone = tk.DoubleVar(); self.var_rev_pre = tk.DoubleVar()
        self.var_fx_rec = tk.BooleanVar()
        ttk.Checkbutton(fx, text='Yanki (echo)', variable=self.var_echo_on, command=self._fx_live).grid(row=1, column=0, sticky='w', **pad)
        self._scale(fx, 2, 0, 'Sure:', self.var_echo_ms, 60, 1200, '%d ms')
        self._scale(fx, 2, 2, 'Tekrar:', self.var_echo_fb, 0, 85, '%d %%')
        self._scale(fx, 3, 0, 'Seviye:', self.var_echo_mix, 0, 100, '%d %%')
        self._scale(fx, 3, 2, 'Parlaklik:', self.var_echo_tone, 0, 100, '%d %%')
        ttk.Checkbutton(fx, text='Reverb', variable=self.var_rev_on, command=self._fx_live).grid(row=4, column=0, sticky='w', padx=6, pady=(10, 3))
        cr = ttk.Combobox(fx, textvariable=self.var_rev_type, width=12, state='readonly', values=mic_fx.REVERB_TYPES)
        cr.grid(row=4, column=1, sticky='w', padx=6, pady=(10, 3))
        cr.bind('<<ComboboxSelected>>', lambda e: self._rev_preset())
        self._scale(fx, 5, 0, 'Sure:', self.var_rev_time, 0.3, 8.0, '%.1f sn')
        self._scale(fx, 5, 2, 'On gecikme:', self.var_rev_pre, 0, 100, '%d ms')
        self._scale(fx, 6, 0, 'Seviye:', self.var_rev_mix, 0, 100, '%d %%')
        self._scale(fx, 6, 2, 'Parlaklik:', self.var_rev_tone, 0, 100, '%d %%')
        ttk.Checkbutton(fx, text='Efekti kayda da uygula (kapaliyken kayit kuru kalir; efekt yalniz kulaklikta)',
                        variable=self.var_fx_rec, command=self._fx_live).grid(row=7, column=0, columnspan=4, sticky='w', padx=6, pady=(10, 3))
        self._lbl(fx, 'Efektler gecikme eklemez: kendi sesiniz aninda gelir, yanki / reverb ustune eklenir.').grid(
            row=8, column=0, columnspan=4, sticky='w', padx=6)

    def _rev_preset(self):
        p = mic_fx.REVERB_PRESETS.get(self.var_rev_type.get())
        if p:
            self.var_rev_time.set(p['time']); self.var_rev_pre.set(p['predelay']); self.var_rev_tone.set(p['tone'])
            if not self.var_rev_on.get():
                self.var_rev_on.set(True)
        self._fx_live()

    def _fx_live(self):
        for lab, var, fmt in self._fx_labels:
            try:
                lab.config(text=fmt % float(var.get()))
            except (tk.TclError, ValueError):
                pass
        cfg = self._collect()
        if self.engine is not None:
            self.engine.set_fx(cfg)
        self._save_later()

    # ---------------------------------------------------------------- ayar <-> arayuz
    def _device_values(self):
        ins = [DEFAULT_LABEL] + list(self.devices.get('inputs') or [])
        outs = [DEFAULT_LABEL] + list(self.devices.get('outputs') or [])
        self.cmb_in.config(values=ins)
        self.cmb_out.config(values=outs)
        return ins, outs

    def _fill_from_cfg(self):
        ins, outs = self._device_values()
        c = self.cfg
        for var, name, lst in ((self.var_in, c['input_device'], ins), (self.var_out, c['output_device'], outs)):
            if not name:
                var.set(DEFAULT_LABEL)
            elif name in lst:
                var.set(name)
            else:                       # secilen aygit su an bagli degil: secim korunur, takilinca geri donulur
                var.set(name + MISSING_SUFFIX)
        self.var_gain.set(c['input_gain_db'])
        self.var_vol.set(c['monitor_volume'])
        self.var_mute.set(c['monitor_muted'])
        self.var_mode.set(core.MODE_LABELS[c['mode']])
        self.var_buf.set('%d ms' % c['buffer_ms'])
        self.var_ch.set(core.CHANNEL_LABELS[c['channel_mode']])
        self.var_rate.set(str(c['samplerate']))
        self.var_share.set(c['share_output'])
        self.var_asio.set(c['enable_asio'])
        self.var_autostart.set(c['autostart'])
        self.var_dir.set(c['record_dir'])
        self.var_bits.set('%d bit' % c['record_bits'])
        self.var_echo_on.set(c['fx_echo_on']); self.var_echo_ms.set(c['fx_echo_ms']); self.var_echo_fb.set(c['fx_echo_fb'])
        self.var_echo_mix.set(c['fx_echo_mix']); self.var_echo_tone.set(c['fx_echo_tone'])
        self.var_rev_on.set(c['fx_rev_on']); self.var_rev_type.set(c['fx_rev_type']); self.var_rev_time.set(c['fx_rev_time'])
        self.var_rev_mix.set(c['fx_rev_mix']); self.var_rev_tone.set(c['fx_rev_tone']); self.var_rev_pre.set(c['fx_rev_predelay'])
        self.var_fx_rec.set(c['fx_to_record'])
        for lab, var, fmt in self._fx_labels:
            lab.config(text=fmt % float(var.get()))
        self._labels()

    def _collect(self):
        c = dict(self.cfg)
        vi, vo = (v.replace(MISSING_SUFFIX, '') for v in (self.var_in.get(), self.var_out.get()))
        c['input_device'] = '' if vi == DEFAULT_LABEL else vi
        c['output_device'] = '' if vo == DEFAULT_LABEL else vo
        c['input_gain_db'] = round(float(self.var_gain.get()), 1)
        c['monitor_volume'] = int(round(float(self.var_vol.get())))
        c['monitor_muted'] = bool(self.var_mute.get())
        inv = {v: k for k, v in core.MODE_LABELS.items()}
        c['mode'] = inv.get(self.var_mode.get(), 'auto')
        try:
            c['buffer_ms'] = int(self.var_buf.get().split()[0])
        except (ValueError, IndexError):
            pass
        inv = {v: k for k, v in core.CHANNEL_LABELS.items()}
        c['channel_mode'] = inv.get(self.var_ch.get(), 'mix')
        try:
            c['samplerate'] = int(self.var_rate.get())
        except ValueError:
            pass
        c['share_output'] = bool(self.var_share.get())
        c['enable_asio'] = bool(self.var_asio.get())
        c['autostart'] = bool(self.var_autostart.get())
        c['record_dir'] = self.var_dir.get().strip()
        c['record_bits'] = 16 if self.var_bits.get().startswith('16') else 24
        c['fx_echo_on'] = bool(self.var_echo_on.get()); c['fx_echo_ms'] = int(round(float(self.var_echo_ms.get())))
        c['fx_echo_fb'] = int(round(float(self.var_echo_fb.get()))); c['fx_echo_mix'] = int(round(float(self.var_echo_mix.get())))
        c['fx_echo_tone'] = int(round(float(self.var_echo_tone.get())))
        c['fx_rev_on'] = bool(self.var_rev_on.get()); c['fx_rev_type'] = self.var_rev_type.get() or 'Studyo'
        c['fx_rev_time'] = round(float(self.var_rev_time.get()), 1); c['fx_rev_mix'] = int(round(float(self.var_rev_mix.get())))
        c['fx_rev_tone'] = int(round(float(self.var_rev_tone.get()))); c['fx_rev_predelay'] = int(round(float(self.var_rev_pre.get())))
        c['fx_to_record'] = bool(self.var_fx_rec.get())
        self.cfg = core._clean(c)
        return self.cfg

    def _labels(self):
        g = float(self.var_gain.get())
        self.lbl_gain.config(text='%+.1f dB' % g)
        self.lbl_vol.config(text='%d %%' % int(round(float(self.var_vol.get()))))

    def _live(self):
        """Kazanc / ses / susturma: akisi yeniden acmadan aninda uygulanir."""
        self._labels()
        cfg = self._collect()
        if self.engine is not None:
            self.engine.set_params(cfg=cfg)
        self._save_later()

    def _save_later(self):
        if getattr(self, '_save_job', None):
            self.after_cancel(self._save_job)
        self._save_job = self.after(800, lambda: core.save_settings(self.cfg))

    def _changed(self, restart):
        cfg = self._collect()
        core.save_settings(cfg)
        self._update_warnings()
        if self.engine is not None:
            self.engine.set_params(cfg=cfg)
        if restart and self.monitoring:
            if self.engine.recording is not None:
                self._status('Kayit suruyor: cihaz / kip degisikligi kayit bitince uygulanir.', WARN)
                return
            if self._restart_job:
                self.after_cancel(self._restart_job)
            self._restart_job = self.after(250, self._restart)

    def _restart(self):
        self._restart_job = None
        self.stop(quiet=True)
        self.start()

    def _asio_changed(self):
        self._changed(restart=False)
        if messagebox.askyesno('ASIO', 'ASIO surucusu taramasi uygulama yeniden acildiginda devreye girer. '
                               'Simdi yeniden baslatilsin mi?', parent=self):
            self._relaunch()

    def _relaunch(self):
        self.stop(quiet=True)
        try:
            if FROZEN:
                upd.launch(sys.executable)
            else:
                subprocess.Popen([sys.executable, str(pathlib.Path(__file__).resolve())], close_fds=True)
        except Exception as e:
            messagebox.showerror('Yeniden baslat', str(e)); return
        self.destroy()

    def _update_warnings(self):
        cfg = self.cfg
        i = cfg['input_device'] or self.devices.get('default_input', '')
        o = cfg['output_device'] or self.devices.get('default_output', '')
        w = core.warnings_for(i, o)
        self.var_warn.set('\n'.join('⚠ ' + x for x in w))

    def refresh_devices(self):
        if self.engine is None:
            return
        try:
            was = self.monitoring
            if was:
                self.stop(quiet=True)
            self.engine.reinit()            # PortAudio cihaz listesini yalniz yeniden baslatilinca tazeler
            self.devices = self.engine.list_devices()
            self._dev_sig = eng.device_signature()
            if was:
                self.after(50, lambda: self.start())
        except Exception as e:
            core.log_line('refresh: %r' % e)
        self._fill_from_cfg()
        self._update_warnings()
        self._status('Cihaz listesi yenilendi (%d giris, %d cikis).' % (len(self.devices['inputs']), len(self.devices['outputs'])), MUTED)

    def open_sound_panel(self):
        if IS_WIN:
            try:
                subprocess.Popen(['control', 'mmsys.cpl,,1'], creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except Exception as e:
                messagebox.showerror('Ses ayarlari', str(e))

    def _browse(self):
        d = filedialog.askdirectory(initialdir=str(core.resolve_record_dir(self.var_dir.get())))
        if d:
            self.var_dir.set(d)
            self._changed(restart=False)

    def _open_folder(self):
        d = core.resolve_record_dir(self.var_dir.get())
        try:
            d.mkdir(parents=True, exist_ok=True)
            if IS_WIN:
                os.startfile(str(d))  # noqa
        except Exception as e:
            messagebox.showerror('Klasor', str(e))

    def _status(self, text, color=MUTED):
        self.var_status.set(text)
        self.lbl_status.config(fg=color)

    # ---------------------------------------------------------------- dinleme
    def toggle(self):
        self._paused_unplug = ''
        if self.monitoring:
            self.stop()
        else:
            self.start()

    def start(self, quiet_errors=False):
        if self.engine is None:
            if not quiet_errors:
                messagebox.showerror('Ses', 'Ses kutuphanesi yuklenemedi: %s' % self.engine_error)
            return False
        cfg = self._collect()
        core.save_settings(cfg)
        self._status('Ses akisi aciliyor…', ACCENT)
        self.update_idletasks()
        try:
            info = self.engine.start(cfg)
        except Exception as e:
            self.monitoring = False
            self.btn_toggle.config(text='Dinlemeyi baslat', bg='#1f6a4a')
            self._status('Baslatilamadi.', BAD_C)
            self.var_info.set('')
            if quiet_errors:
                core.log_line('start (auto) failed: %s' % str(e).replace('\n', ' ')[:300])
            else:
                messagebox.showerror('Ses akisi', str(e), parent=self)
            return False
        self.monitoring = True
        self._stall = 0
        self.btn_toggle.config(text='Dinlemeyi durdur', bg='#6b2a2a')
        self._status('Dinleniyor — %s' % info.get('mode', ''), OK_C)
        self._update_info()
        return True

    def stop(self, quiet=False):
        if self.engine is not None and self.engine.recording is not None:
            self.toggle_record()
        if self.engine is not None:
            self.engine.stop()
        self.monitoring = False
        try:
            self.btn_toggle.config(text='Dinlemeyi baslat', bg='#1f6a4a')
            if not quiet:
                self._status('Durdu.', MUTED)
                self.var_info.set('')
        except tk.TclError:
            pass

    def _update_info(self):
        if not self.monitoring or self.engine is None:
            return
        i = self.engine.info
        parts = ['%s' % i.get('mode', ''), '%.1f kHz' % (i.get('samplerate', 0) / 1000.0),
                 'tahmini gecikme ≈ %.0f ms' % i.get('latency_ms', 0)]
        if i.get('raw'):
            parts.append('Windows efektleri atlandi')
        fx = self.engine.fx
        if fx is not None and fx.active:
            names = (['yanki'] if fx.echo is not None else []) + (['reverb (%s)' % fx.reverb.kind] if fx.reverb is not None else [])
            parts.append('efekt: ' + ' + '.join(names))
        parts.append('kesinti: %d' % self.engine.xruns)
        txt = '  ·  '.join(parts)
        rec = self.engine.recording
        if rec is not None:
            s = int(rec.seconds)
            txt += '\n● KAYIT %02d:%02d  —  %s' % (s // 60, s % 60, rec.path.name)
            if rec.error:
                txt += '  (HATA: %s)' % rec.error
            elif rec.dropped_blocks:
                txt += '  (%d blok kaybi: disk yavas)' % rec.dropped_blocks
        self.var_info.set(txt)

    def show_details(self):
        lines = ['AGFO Mic Monitor %s' % VERSION, '']
        if self.engine is None:
            lines.append('Ses kutuphanesi yuklenemedi: %s' % self.engine_error)
        else:
            i = self.engine.info
            if self.monitoring:
                lines += ['Kip: %s' % i.get('mode'), 'Giris: %s (%s kanal)' % (i.get('input'), i.get('in_ch')),
                          'Cikis: %s (%s kanal)' % (i.get('output'), i.get('out_ch')),
                          'Ornekleme: %s Hz' % i.get('samplerate'),
                          'Tahmini gecikme (surucunun bildirdigi giris + cikis): %s ms' % i.get('latency_ms'),
                          'Kesinti (tasma / bosalma): %d' % self.engine.xruns, '']
            lines.append('Ses API\'leri: %s' % ', '.join(self.devices.get('apis') or []))
            if self.engine.attempt_log:
                lines += ['', 'Son baslatma denemeleri:'] + ['  ' + x for x in self.engine.attempt_log[-12:]]
        lines += ['', 'Gunluk: %s' % (core.LOG_DIR / 'micmon.log')]
        messagebox.showinfo('Ayrintilar', '\n'.join(lines), parent=self)

    # ---------------------------------------------------------------- kayit
    def toggle_record(self):
        if self.engine is None:
            return
        if self.engine.recording is not None:
            rec = self.engine.stop_recording()
            self.btn_rec.config(text='● Kaydi baslat', bg='#7a2a2a')
            if rec is not None:
                msg = 'Kaydedildi: %s  (%d sn)' % (rec.path.name, int(rec.seconds))
                if rec.error:
                    self._status('Kayit hatasi: %s' % rec.error, BAD_C)
                else:
                    self._status(msg + ('  —  %d ornek kirpildi, kazanci dusurun' % rec.clipped if rec.clipped > 100 else ''),
                                 WARN if rec.clipped > 100 else OK_C)
            self._update_info()
            return
        if not self.monitoring and not self.start():
            return
        cfg = self._collect()
        try:
            path = self.engine.start_recording(cfg['record_dir'], cfg['record_bits'], wet=cfg['fx_to_record'])
        except Exception as e:
            messagebox.showerror('Kayit', 'Kayit baslatilamadi: %s' % e, parent=self); return
        self.btn_rec.config(text='■ Kaydi durdur', bg='#a33a3a')
        self._status('Kaydediliyor: %s' % path, BAD_C)
        self._update_info()

    # ---------------------------------------------------------------- dongu: seviye olcer, saglik
    def _meter_items(self):
        """Gosterge ogeleri bir kez olusturulur; her karede yalniz koordinatlari degisir (hafif)."""
        if getattr(self, '_mi', None):
            return self._mi
        w, h = self.meter_w, self.meter_h
        mi = {
            'g': self.cv.create_rectangle(0, 0, 0, h, fill='#3fae6a', width=0),
            'y': self.cv.create_rectangle(0, 0, 0, h, fill='#d7b84a', width=0),
            'r': self.cv.create_rectangle(0, 0, 0, h, fill='#d9534f', width=0),
            'hold': self.cv.create_line(0, 0, 0, h, fill='#ffffff'),
            'clip': self.cv.create_rectangle(w - 8, 0, w, h, fill='#ff3b30', width=0, state='hidden'),
        }
        for mark in (-48, -36, -24, -12, -6, -3):
            mx = self._x_of(mark)
            self.cv.create_line(mx, h - 4, mx, h, fill=MUTED)
        self._mi = mi
        return mi

    def _x_of(self, v):
        return int(self.meter_w * (max(-60.0, min(0.0, v)) + 60.0) / 60.0)

    def _draw_meter(self, db):
        h = self.meter_h
        mi = self._meter_items()
        x, y1, y2 = self._x_of(db), self._x_of(-18.0), self._x_of(-6.0)
        self.cv.coords(mi['g'], 0, 0, min(x, y1), h)
        self.cv.coords(mi['y'], y1, 0, max(y1, min(x, y2)), h)
        self.cv.coords(mi['r'], y2, 0, max(y2, x), h)
        hx = self._x_of(self.meter_hold)
        self.cv.coords(mi['hold'], hx, 0, hx, h)
        self.cv.itemconfigure(mi['clip'], state='normal' if time.monotonic() < self.clip_until else 'hidden')

    def _poll(self):
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == 'call':
                    try:
                        payload()
                    except tk.TclError:
                        pass
        except queue.Empty:
            pass
        now = time.monotonic()
        if self.engine is not None and self.monitoring:
            p = self.engine.take_peak()
            db = core.peak_dbfs(p)
            if p >= 0.999:
                self.clip_until = now + 1.5
            self.meter = db if db > self.meter else max(db, self.meter - 1.2)
            if self.meter > self.meter_hold or now > self.hold_until:
                self.meter_hold = self.meter
                self.hold_until = now + 1.2
            self._draw_meter(self.meter)
            self.var_db.set('%5.1f dBFS' % self.meter if self.meter > -60 else ' -inf')
            if now - self._last_stats > 0.5:
                self._last_stats = now
                self._update_info()
                self._check_crackle(now)
                moving = self.engine.check_progress()
                self._stall = 0 if moving else self._stall + 1
                if not self.engine.alive() or self._stall >= STALL_TICKS:
                    if self._stall >= STALL_TICKS:
                        core.log_line('stream stalled (no callbacks for %.1f s)' % (self._stall * 0.5))
                    self._recover()
        elif self.meter > -60:
            self.meter = -60.0; self.meter_hold = -60.0
            self._draw_meter(-60.0); self.var_db.set('')
        if self.engine is not None and now - self._dev_checked >= DEVICE_CHECK_S and not self._recovering:
            self._dev_checked = now
            sig = self._sig_latest
            if sig is not None and self._dev_sig is not None and sig != self._dev_sig and self._dev_job is None:
                # Windows bir takmada birkac degisiklik bildirir: yatisinca bir kez uygula
                self._dev_job = self.after(800, self._devices_changed)
            if sig is not None:
                self._dev_sig = sig
        self._poll_job = self.after(POLL_MS, self._poll)

    def _device_watch_loop(self):
        while self._watch_alive:
            try:
                self._sig_latest = eng.device_signature()
            except Exception:
                pass
            time.sleep(DEVICE_CHECK_S)

    def _check_crackle(self, now):
        """Sik kesinti = duyulan cizirti. Tamponu bir kademe buyutup akisi yeniden acar (kayit yokken)."""
        if not self.monitoring or now - self._auto_buf_at < 12.0:
            return
        if self.engine.xrun_rate(now) < XRUN_LIMIT:
            return
        cur = self.cfg.get('buffer_ms', 5)
        bigger = [b for b in core.BUFFER_CHOICES_MS if b > cur]
        self._auto_buf_at = now
        if not bigger:
            self._status('Cizirti suruyor (tampon zaten en buyuk). "Ayrintilar"a bakin; baska bir kip deneyin.', WARN)
            return
        if self.engine.recording is not None:
            self._status('Cizirti algilandi. Kayit bitince "Tampon"u %d ms yapin.' % bigger[0], WARN)
            return
        core.log_line('crackle: %d xruns/10s at %d ms -> %d ms' % (self.engine.xrun_rate(now), cur, bigger[0]))
        self.var_buf.set('%d ms' % bigger[0])
        self._collect(); core.save_settings(self.cfg)
        self.stop(quiet=True)
        if self.start(quiet_errors=True):
            self._status('Cizirti algilandi: tampon %d ms -> %d ms yapildi (gecikme ≈ %.0f ms).'
                         % (cur, bigger[0], self.engine.info.get('latency_ms', 0)), WARN)
        else:
            self._schedule_recover(0, False)

    def _devices_changed(self):
        """Kulaklik takildi / cikarildi, USB mikrofon baglandi ya da varsayilan aygit degisti."""
        self._dev_job = None
        self._dev_sig = eng.device_signature()
        was = self.monitoring or bool(self._paused_unplug)
        old_out = self.engine.info.get('output', '') if self.monitoring else self._paused_unplug
        recording = was and self.engine.recording is not None
        core.log_line('devices changed; monitoring=%s' % was)
        self.stop(quiet=True)
        before = list(self.devices.get('outputs') or [])
        try:
            self.engine.reinit()
            self.devices = self.engine.list_devices()
        except Exception as e:
            core.log_line('reinit after device change: %r' % e)
        hp = core.pick_new_headphone(before, self.devices.get('outputs'))
        if hp and self.cfg.get('output_device') and self.cfg['output_device'] != hp:
            # Hoparlor (ya da baska bir cikis) secili iken kulaklik takildi: kulakliga gec.
            # Varsayilan secili ise Windows zaten kulakligi varsayilan yapar; ayara dokunulmaz.
            core.log_line('headphone plugged: %s (was %s)' % (hp, self.cfg['output_device']))
            self.cfg['output_device'] = hp
            core.save_settings(self.cfg)
        self._fill_from_cfg()
        self._update_warnings()
        if not was:
            self._status('Ses aygitlari degisti; liste guncellendi.', MUTED)
            return
        target = self.cfg.get('output_device') if self.cfg.get('output_device') in (self.devices.get('outputs') or []) \
            else self.devices.get('default_output', '')
        if core.is_speaker_name(target) and old_out and not core.is_speaker_name(old_out):
            # kulaklik cikarildi, ses hoparlore donecek: mikrofon otmesin diye dinlemeyi duraklat
            self._paused_unplug = old_out
            self._status('Kulaklik cikarildi: hoparlorden geri besleme olmasin diye dinleme duraklatildi. '
                         'Kulaklik takilinca kendiliginden devam eder.' + (' Kayit kaydedildi.' if recording else ''), WARN)
            core.log_line('paused: output fell back to speaker (%s)' % target)
            return
        self._paused_unplug = ''
        if self.start(quiet_errors=True):
            new_out = self.engine.info.get('output', '')
            msg = 'Ses aygitlari degisti; dinleme yeniden baslatildi'
            msg += (': %s' % new_out) if new_out and new_out != old_out else '.'
            if recording:
                msg += ' Kayit durduruldu ve kaydedildi; yeni kayit icin tekrar basin.'
            self._status(msg, WARN)
        else:
            self._schedule_recover(0, recording)

    def _recover(self):
        """Akis durdu ya da takildi (kulaklik takildi, cihaz cikarildi, uyku): PortAudio yeniden baslatilir ve
        akis artan bekleme ile (0,4 / 1,5 / 4 sn) yeniden acilir. 60 sn icinde 6'dan fazla olursa durur."""
        if self._recovering:
            return
        now = time.monotonic()
        self.restarts = [t for t in self.restarts if now - t < 60] + [now]
        core.log_line('stream died/stalled; recover #%d' % len(self.restarts))
        recording = self.engine.recording is not None
        self.stop(quiet=True)
        if len(self.restarts) > 6:
            self._status('Ses akisi tekrar tekrar durdu. Aygit bagli mi? "Yenile" ile listeyi tazeleyip yeniden baslatin.', BAD_C)
            return
        self._schedule_recover(0, recording)

    def _schedule_recover(self, n, recording):
        self._recovering = True
        self._status('Ses akisi kesildi; yeniden aciliyor…', WARN)
        self.after(RECOVER_DELAYS_MS[n], lambda: self._try_recover(n, recording))

    def _try_recover(self, n, recording):
        try:
            self.engine.reinit()
            self.devices = self.engine.list_devices()
            self._fill_from_cfg()
            self._update_warnings()
        except Exception as e:
            core.log_line('reinit: %r' % e)
        self._dev_sig = eng.device_signature()
        if self.start(quiet_errors=True):
            self._recovering = False
            self._status('Ses akisi kesildi ve yeniden acildi: %s.' % self.engine.info.get('output', '')
                         + (' Kayit durduruldu; dosya kaydedildi.' if recording else ''), WARN)
            return
        if n + 1 < len(RECOVER_DELAYS_MS):
            self._schedule_recover(n + 1, recording)
        else:
            self._recovering = False
            self._status('Ses akisi yeniden acilamadi. "Ayrintilar" ile nedenini gorun; "Dinlemeyi baslat" ile tekrar deneyin.', BAD_C)

    # ---------------------------------------------------------------- ilk acilista kurulum (EXE)
    def _first_run_install(self):
        try:
            if pathlib.Path(sys.executable).resolve() == upd.installed_exe().resolve():
                return  # zaten Programs altindan calisiyor
        except OSError:
            return
        if not messagebox.askyesno('Kurulum', 'AGFO Mic Monitor bu bilgisayara kurulsun mu?\n\n'
                                   'Program %s klasorune kopyalanir; Baslat menusu ve masaustu kisayolu olusturulur. '
                                   'Yonetici gerekmez.' % upd.install_dir(), parent=self):
            return

        def fn(post):
            try:
                dst = upd.install_self(desktop=True)
                post(lambda: self._reopen_installed(dst))
            except Exception as e:
                post(lambda: messagebox.showwarning('Kurulum', 'Kurulamadi: %s\nUygulama buradan calismaya devam ediyor.' % e, parent=self))
        self._run_bg(fn)

    def _reopen_installed(self, dst):
        messagebox.showinfo('Kuruldu', 'Kuruldu: %s\nKurulu surum aciliyor.' % dst, parent=self)
        try:
            upd.launch(dst)
        except Exception:
            pass
        self.stop(); self.destroy()

    # ---------------------------------------------------------------- GitHub guncelleme
    def gh_check(self, force=True, silent=False):
        def fn(post):
            res = upd.check(force=force)
            post(lambda: self._gh_checked(res, force, silent))
        self._run_bg(fn)

    def _gh_periodic(self):
        if self.cfg.get('auto_update_check', True) and not self.busy:
            self.gh_check(force=False, silent=True)
        self.after(upd.PERIODIC_CHECK_MS, self._gh_periodic)

    def _gh_checked(self, res, force, silent=False):
        st = res.get('status')
        if st == 'update':
            self.gh_result = res
            rel = res['release']
            self.gh_banner_text.set('Yeni surum hazir: Mic Monitor %s  (kurulu: %s%s)' %
                                    (res['version'], VERSION, (', yayin: ' + rel['published']) if rel.get('published') else ''))
            if not self.gh_banner.winfo_ismapped():
                self.gh_banner.pack(fill='x', padx=22, pady=(0, 8), after=self.winfo_children()[0])
            if silent:
                core.log_line('update available: %s' % res['version'])
        elif force and not silent:
            msg = {'current': 'Guncelsiniz (son surum %s).' % res.get('version', VERSION),
                   'none': "GitHub'da henuz Mic Monitor surumu yok.",
                   'skipped': 'Surum %s atlanmis olarak isaretli.' % res.get('version', ''),
                   'error': 'Denetlenemedi: %s' % res.get('message', '')}.get(st, st)
            messagebox.showinfo('GitHub guncelleme', msg)
            if getattr(self, 'upd_state', None):
                try:
                    self.upd_state.set(msg)
                except tk.TclError:
                    pass

    def gh_show_notes(self):
        if not self.gh_result:
            return
        rel = self.gh_result['release']
        messagebox.showinfo('Surum %s notlari' % self.gh_result['version'],
                            (rel.get('notes') or 'Not eklenmemis.')[:3000] + '\n\n' + rel.get('url', ''))

    def gh_skip(self):
        if self.gh_result:
            ghu.skip_version(upd.state_path(), self.gh_result['version'])
        self.gh_banner.pack_forget()

    def gh_update(self):
        res = self.gh_result
        if not res or self.busy:
            if self.busy:
                messagebox.showinfo('Mesgul', 'Bir islem suruyor; bitince tekrar deneyin.')
            return
        if not FROZEN:
            messagebox.showinfo('Guncelleme', 'Tek tikla guncelleme yalnizca derlenmis (EXE) surumde calisir. '
                                'Kaynaktan calistiriyorsunuz; GitHub\'dan yeni surumu elle kurabilirsiniz.')
            return
        rel = res['release']
        notes = (rel.get('notes') or '').strip()
        if not messagebox.askyesno('Guncelleme', 'AGFO Mic Monitor %s -> %s\n\n%s\n\nIndirilip dogrulanacak, uygulama '
                                   'kapanip yeni surumle yeniden acilacak. Devam edilsin mi?'
                                   % (VERSION, res['version'], (notes[:800] + ('…' if len(notes) > 800 else '')) or 'Surum notu yok.')):
            return
        self.busy = True
        self.var_status.set('Guncelleme indiriliyor…'); self.lbl_status.config(fg=ACCENT)

        def fn(post):
            try:
                new_exe = upd.download(res)
                proc = upd.apply_update(new_exe)
                import time as _t
                _t.sleep(2)
                if proc.poll() is not None:   # guvenlik yazilimi guncelleyiciyi hemen kapattiysa
                    raise OSError('Guncelleyici baslatilamadi (guvenlik yazilimi engellemis olabilir).')
                post(self._gh_update_launched)
            except Exception as e:
                post(lambda: self._gh_update_fail(str(e)))
        self._run_bg(fn)

    def _gh_update_launched(self):
        # Guncelleyici ayakta; bu surum kapanmali ki dosya serbest kalsin.
        self.var_status.set('Yeni surum kuruluyor; uygulama kapaniyor…')
        self.stop()
        self.after(400, self.destroy)

    def _gh_update_fail(self, msg):
        self.busy = False
        self.var_status.set('Guncelleme basarisiz.'); self.lbl_status.config(fg=BAD_C)
        messagebox.showerror('Guncelleme', 'Guncelleme tamamlanamadi; kurulu surum degismedi.\n\n%s' % msg)

    def open_updater(self):
        if getattr(self, 'upd_win', None) and self.upd_win.winfo_exists():
            self.upd_win.lift(); return
        win = self.upd_win = tk.Toplevel(self); win.title('AGFO Mic Monitor — Guncelleme'); win.configure(bg=PANEL); win.transient(self)
        w, h = int(620 * self.scale), int(300 * self.scale)
        win.geometry('%dx%d+%d+%d' % (w, h, self.winfo_rootx() + 40, self.winfo_rooty() + 40))
        tk.Label(win, text='Guncelleme', fg=FG, bg=PANEL, font=('Segoe UI', 13, 'bold')).pack(anchor='w', padx=16, pady=(14, 2))
        tk.Label(win, text='Kurulu surum: %s' % VERSION, fg=OK_C, bg=PANEL, font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=16)
        note = ('GitHub\'daki %s deposundan yeni surum denetlenir. "Simdi guncelle" yeni EXE\'yi indirir, '
                'SHA-256 ile dogrular, uygulama kapaninca yerine koyar ve yeniden acar. Ayarlariniz (config.json) korunur.' % ghu.GITHUB_REPO)
        self._lbl(win, note, wraplength=int(580 * self.scale)).pack(fill='x', padx=16, pady=(6, 8))
        bar = tk.Frame(win, bg=PANEL); bar.pack(fill='x', padx=16)
        self._btn(bar, "GitHub'da denetle", lambda: self.gh_check(force=True), 'go').pack(side='left', padx=(0, 6))
        self._btn(bar, 'Simdi guncelle', self.gh_update, 'normal').pack(side='left', padx=(0, 6))
        self._btn(bar, 'Bu bilgisayardan kaldir', self._uninstall, 'danger').pack(side='right')
        self.upd_state = tk.StringVar(value='Hazir.' if FROZEN else 'Kaynaktan calisiyor — tek tikla guncelleme yalnizca EXE surumunde.')
        tk.Label(win, textvariable=self.upd_state, fg=MUTED, bg=PANEL, font=('Segoe UI', 9), anchor='w',
                 wraplength=int(580 * self.scale), justify='left').pack(fill='x', padx=16, pady=(10, 4))
        self.upd_auto = tk.BooleanVar(value=self.cfg.get('auto_update_check', True))

        def _auto():
            self.cfg['auto_update_check'] = bool(self.upd_auto.get()); core.save_settings(self.cfg)
        ttk.Checkbutton(win, text='Acilista guncellemeleri denetle', variable=self.upd_auto, command=_auto).pack(anchor='w', padx=16, pady=(6, 10))

    def _uninstall(self):
        if not FROZEN:
            messagebox.showinfo('Kaldir', 'Kaldirma yalnizca kurulu EXE surumunde gecerli.'); return
        if not messagebox.askyesno('Kaldir', 'AGFO Mic Monitor bu bilgisayardan kaldirilsin mi?\n\n'
                                   'Program dosyasi ve kisayollar silinir; ayarlariniz (config.json) ve gunlukler korunur. '
                                   'Uygulama kapanacak.', parent=self.upd_win):
            return
        try:
            upd.uninstall()
        except Exception as e:
            messagebox.showerror('Kaldir', 'Kaldirilamadi: %s' % e, parent=self.upd_win); return
        self.stop(); self.destroy()


    # ---------------------------------------------------------------- kapanis
    def destroy(self):
        self._watch_alive = False
        for job in (getattr(self, '_poll_job', None), getattr(self, '_save_job', None), self._restart_job, self._dev_job):
            try:
                if job:
                    self.after_cancel(job)
            except Exception:
                pass
        super().destroy()

    def _on_close(self):
        if self.engine is not None and self.engine.recording is not None:
            if not messagebox.askyesno('Kayit suruyor', 'Kayit durdurulup dosya kaydedilsin ve uygulama kapansin mi?', parent=self):
                return
        try:
            core.save_settings(self._collect())
        except Exception:
            pass
        self.stop(quiet=True)
        self.destroy()


# =========================================================================== komut satiri / giris
def smoke(report_path):
    """Derleme oz-testi: PortAudio yuklenir, ses API'leri ve cihazlar listelenir, RAW WASAPI ayari
    olusturulur, GUI kurulur. Ses aygiti olmayan derleme makinesinde de calisir."""
    lines = []
    try:
        import numpy  # noqa: F401
        sd = eng.load_sounddevice(False)
        lines.append('portaudio: %s' % (sd.get_portaudio_version()[1],))
        apis = [h['name'] for h in sd.query_hostapis()]
        lines.append('apis: %s' % ', '.join(apis))
        if IS_WIN and eng.API_WASAPI not in apis:
            raise RuntimeError('WASAPI yok')
        if eng.API_WASAPI in apis:
            s = eng._WasapiSettings(sd, exclusive=True, raw=True)
            assert int(s._streaminfo.streamOption) == eng.STREAM_OPTION_RAW
            assert int(s._streaminfo.flags) & 1
            lines.append('wasapi raw settings: ok')
        sig = eng.device_signature()
        if IS_WIN and sig is None:
            raise RuntimeError('aygit izleme (winmm) calismadi')
        lines.append('device watch: %s' % ('ok %d out / %d in' % (len(sig[0]), len(sig[1])) if sig else 'n/a'))
        app = App(sd=sd)
        app.withdraw()
        app.update_idletasks()
        app.update()
        lines.append('devices: %d in, %d out' % (len(app.devices['inputs']), len(app.devices['outputs'])))
        w = mic_fx.FxChain(48000).configure({'fx_echo_on': True, 'fx_rev_on': True}).process(numpy.zeros((480, 2), dtype='float32'))
        assert w.shape == (480, 2)
        lines.append('effects: ok')
        r = core.RingBuffer(2, 4800, 240)
        r.write(numpy.zeros((256, 2), dtype='float32'))
        app.destroy()
        lines.append('AGFO MIC MONITOR SMOKE OK')
        rc = 0
    except Exception as e:
        lines.append('SMOKE FAIL: %r' % e)
        rc = 1
    try:
        pathlib.Path(report_path).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    except OSError:
        pass
    print('\n'.join(lines))
    return rc


def apply_update_main(target, pid):
    """Yeni EXE guncelleyici kipinde: eski surum kapaninca kendini hedefe kopyalar ve hedefi acar."""
    root = tk.Tk()
    root.title('AGFO Mic Monitor')
    root.configure(bg=PANEL)
    root.geometry('420x120')
    root.resizable(False, False)
    try:
        ico = pathlib.Path(getattr(sys, '_MEIPASS', '.')) / 'assets' / 'agfo-micmon.ico'
        if IS_WIN and ico.is_file():
            root.iconbitmap(default=str(ico))
    except Exception:
        pass
    tk.Label(root, text='AGFO Mic Monitor %s kuruluyor…' % VERSION, fg=FG, bg=PANEL,
             font=('Segoe UI', 11, 'bold')).pack(pady=(20, 8))
    pb = ttk.Progressbar(root, mode='indeterminate', length=340); pb.pack(); pb.start(12)
    q = queue.Queue()

    def work():
        try:
            if not upd.wait_for_pid(pid, 90):
                raise OSError('Eski surum 90 saniyede kapanmadi.')
            upd.replace_target(sys.executable, target)
            upd.launch(target)
            upd.log_line('Update applied: %s' % target)
            q.put(None)
        except Exception as e:
            upd.log_line('Update failed: %r' % e)
            q.put(e)
    threading.Thread(target=work, daemon=True).start()
    out = {}

    def poll():
        try:
            out['err'] = q.get_nowait()
        except queue.Empty:
            root.after(150, poll); return
        pb.stop()
        if out['err'] is not None:
            messagebox.showerror('Guncelleme', 'Guncelleme uygulanamadi: %s\n\nYeni surum su dosyada, dogrudan acabilirsiniz:\n%s'
                                 % (out['err'], sys.executable), parent=root)
        root.destroy()
    root.after(150, poll)
    root.mainloop()
    return 0 if out.get('err') is None else 1


def main():
    argv = sys.argv
    if len(argv) >= 3 and argv[1] == '--smoke':
        return smoke(argv[2])
    if len(argv) >= 3 and argv[1] == '--apply-update':
        pid = 0
        if '--wait-pid' in argv:
            try:
                pid = int(argv[argv.index('--wait-pid') + 1])
            except (ValueError, IndexError):
                pid = 0
        return apply_update_main(argv[2], pid)
    App().mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
