"""AGFO Mic Monitor - prompter / sarki sozu ekrani (tkinter penceresi).

PROMPTER kipi (konusma kaydi): metin ekrana sigan bolumlere ayrilir; BOSLUK / PageDown / Asagi / Sag ile
sonraki, PageUp / Yukari / Sol ile onceki bolum (sunum kumandalari da bu tuslari gonderir). "● Kayit"
geri sayimdan sonra kaydi baslatir; kayit sirasinda her bolum gecisi isaretlenir (WAV icine bolum isareti
+ Audacity etiket dosyasi).

SARKI SOZU kipi:

Sozler altyapinin calma konumuna gore yumusakca kayar: o an soylenen satir ekranin ust ucte birinde,
beyaz ve kalin; sonraki satir acik, digerleri soluk. Tam ekran (F11) ya da ikinci monitore tasinabilir.
"Zamanla": altyapi bastan calar, her satirin basinda BOSLUK tusuna basilir; zamanlama LRC olarak
kaydedilir ve sonraki kayitlarda sozler sizin temponuzla akar.

Her karede tum satirlar tek bir canvas.move ile kaydirilir (hafif; ses is parcacigini bekletmez).
"""
import pathlib
import tkinter as tk

import mic_core as core
import mic_lyrics as ly

BG = '#05080f'
CUR, NEXT, DIM, TAPC = '#ffffff', '#9fb4d0', '#4a5a72', '#e2b356'
ACCENT, MUTED = '#49b3ef', '#a5b6ce'


class LyricsWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title('AGFO Mic Monitor — Sarki sozu')
        self.configure(bg=BG)
        sc = getattr(app, 'scale', 1.0)
        self.geometry('%dx%d' % (int(900 * sc), int(620 * sc)))
        self.minsize(int(420 * sc), int(300 * sc))
        self.font_size = int(app.cfg.get('lyrics_font', 40))
        self.items = []
        self.centers = []
        self.offset = None
        self.cur = None
        self.tapper = None
        self.full = False
        self.sections = []
        self.sec = 0
        self.counting = 0

        bar = tk.Frame(self, bg='#0d1626', padx=8, pady=5)
        bar.pack(fill='x')
        self.bar = bar

        def b(text, cmd):
            w = tk.Button(bar, text=text, command=cmd, bg='#1b2c45', fg='#ffffff', relief='flat', padx=10, pady=3,
                          activebackground=ACCENT, cursor='hand2', font=('Segoe UI', 9, 'bold'))
            w.pack(side='left', padx=(0, 5))
            return w
        b('A−', lambda: self.set_font(self.font_size - 4))
        b('A+', lambda: self.set_font(self.font_size + 4))
        self.btn_mode = b('', self.toggle_mode)
        b('Tam ekran (F11)', self.toggle_full)
        self.btn_time = b('Zamanla', self.toggle_timing)
        self.btn_rec = b('● Kayit', self.toggle_record)
        self.btn_rec.config(bg='#7a2a2a')
        self.var_rec = tk.StringVar(value='')
        tk.Label(bar, textvariable=self.var_rec, fg='#ff6b6b', bg='#0d1626', font=('Segoe UI', 11, 'bold')).pack(side='right', padx=8)
        self.var_info = tk.StringVar(value='')
        tk.Label(bar, textvariable=self.var_info, fg=MUTED, bg='#0d1626', font=('Segoe UI', 9), anchor='w').pack(
            side='left', padx=8, fill='x', expand=True)

        self.cv = tk.Canvas(self, bg=BG, highlightthickness=0)
        self.cv.pack(fill='both', expand=True)
        self.cv.bind('<Configure>', lambda e: self.layout())
        for key in ('<space>', '<Return>', '<Next>', '<Down>', '<Right>'):
            self.bind(key, lambda e: self.forward())
        for key in ('<Prior>', '<Up>', '<Left>'):
            self.bind(key, lambda e: self.back())
        self.bind('<Home>', lambda e: self.goto(0))
        self.bind('<BackSpace>', lambda e: self.untap())
        self.bind('<F11>', lambda e: self.toggle_full())
        self.bind('<Escape>', lambda e: self.escape())
        self.bind('<plus>', lambda e: self.set_font(self.font_size + 4))
        self.bind('<KP_Add>', lambda e: self.set_font(self.font_size + 4))
        self.bind('<minus>', lambda e: self.set_font(self.font_size - 4))
        self.bind('<KP_Subtract>', lambda e: self.set_font(self.font_size - 4))
        self.protocol('WM_DELETE_WINDOW', self.close)
        self._mode_ui()
        self.layout()
        self.focus_set()

    # ---------------------------------------------------------------- kip
    @property
    def prompter(self):
        return bool(self.app.cfg.get('prompter_mode'))

    def _mode_ui(self):
        self.btn_mode.config(text='Kip: Prompter (konusma)' if self.prompter else 'Kip: Sarki sozu (muzige bagli)')
        if self.prompter:
            self.btn_time.pack_forget()
        elif not self.btn_time.winfo_ismapped():
            self.btn_time.pack(side='left', padx=(0, 5), before=self.btn_rec)

    def toggle_mode(self):
        if self.tapper is not None:
            self.finish_timing()
        self.app.cfg['prompter_mode'] = not self.prompter
        core.save_settings(self.app.cfg)
        self._mode_ui()
        self.layout()

    def forward(self):
        if self.prompter:
            self.goto(self.sec + 1)
        else:
            self.tap()

    def back(self):
        if self.prompter:
            self.goto(self.sec - 1)

    def goto(self, k):
        if not self.prompter or not self.sections:
            return
        k = max(0, min(len(self.sections) - 1, int(k)))
        if k == self.sec and self.items:
            return
        self.sec = k
        self._draw_section()
        self.app.prompter_mark(k, self.section_label(k))

    def section_label(self, k):
        words = ' '.join(self.sections[k]).split()
        head = ' '.join(words[:6]) + ('…' if len(words) > 6 else '')
        return 'Bolum %d: %s' % (k + 1, head)

    # ---------------------------------------------------------------- prompter yerlesimi
    def _layout_prompter(self, L):
        w, h = max(200, self.cv.winfo_width()), max(150, self.cv.winfo_height())
        fnt = ('Segoe UI', self.font_size, 'bold')
        probe = self.cv.create_text(0, 0, text='', font=fnt, width=int(w * 0.9), anchor='nw')

        def fits(paras):
            self.cv.itemconfigure(probe, text='\n\n'.join(paras))
            bb = self.cv.bbox(probe)
            return (bb[3] - bb[1] if bb else 0) <= h * 0.80
        self.sections = ly.build_sections(ly.paragraphs(L.lines), fits)
        self.cv.delete(probe)
        self.sec = max(0, min(self.sec, len(self.sections) - 1))
        self._draw_section()

    def _draw_section(self):
        self.cv.delete('all')
        self.items = []
        if not self.sections:
            return
        w, h = max(200, self.cv.winfo_width()), max(150, self.cv.winfo_height())
        fnt = ('Segoe UI', self.font_size, 'bold')
        it = self.cv.create_text(w // 2, int(h * 0.06), text='\n\n'.join(self.sections[self.sec]), fill=CUR, font=fnt,
                                 width=int(w * 0.9), justify='left', anchor='n', tags=('ly',))
        self.items = [it]
        nxt = ''
        if self.sec + 1 < len(self.sections):
            nxt = '→ ' + ' '.join(' '.join(self.sections[self.sec + 1]).split()[:8]) + '…'
        self.cv.create_text(int(w * 0.05), h - 10, text=nxt, fill=DIM, font=('Segoe UI', max(11, self.font_size // 3)),
                            anchor='sw', width=int(w * 0.75))
        self.cv.create_text(w - 12, h - 10, text='%d / %d' % (self.sec + 1, len(self.sections)), fill=MUTED,
                            font=('Segoe UI', max(11, self.font_size // 3), 'bold'), anchor='se')
        self._info()

    # ---------------------------------------------------------------- yerlesim
    @property
    def lyrics(self):
        return self.app.lyrics

    def layout(self):
        self.cv.delete('all')
        self.items, self.centers = [], []
        self.offset, self.cur = None, None
        L = self.lyrics
        w = max(200, self.cv.winfo_width())
        if L is None or not len(L):
            self.cv.create_text(w // 2, max(60, self.cv.winfo_height() // 2), text='Soz yuklenmedi.\n"Soz ac…" ya da "Yapistir…"',
                                fill=DIM, font=('Segoe UI', 18), justify='center')
            self.var_info.set('')
            return
        if self.prompter:
            self._layout_prompter(L)
            return
        fnt = ('Segoe UI', self.font_size, 'bold')
        y = 0
        gap = int(self.font_size * 0.45)
        for ln in L.lines:
            it = self.cv.create_text(w // 2, y, text=ln or '·', fill=DIM, font=fnt, width=int(w * 0.92),
                                     justify='center', anchor='n', tags=('ly',))
            bb = self.cv.bbox(it) or (0, y, 0, y + self.font_size)
            h = bb[3] - bb[1]
            if not ln:                                   # kita arasi: kucuk bosluk
                self.cv.itemconfigure(it, text='', font=('Segoe UI', max(8, self.font_size // 3)))
                h = int(self.font_size * 0.6)
            self.items.append(it)
            self.centers.append(y + h / 2.0)
            y += h + gap
        self._info()
        self.update_view(force=True)

    def set_font(self, size):
        self.font_size = max(16, min(120, int(size)))
        self.app.cfg['lyrics_font'] = self.font_size
        core.save_settings(self.app.cfg)
        self.layout()

    def _info(self):
        L = self.lyrics
        rec = self.app.engine.recording if self.app.engine is not None else None
        if rec is not None:
            s = int(rec.elapsed)
            self.var_rec.set('● KAYIT %02d:%02d' % (s // 60, s % 60))
        else:
            self.var_rec.set('')
        if self.counting:
            self.var_info.set('Kayit %d sn sonra basliyor…' % self.counting)
        elif self.prompter and L is not None:
            self.var_info.set('Bolum %d/%d · ileri: Bosluk / PageDown · geri: PageUp' % (self.sec + 1, max(1, len(self.sections))))
        elif self.tapper is not None:
            n, total = len(self.tapper.taps), len(self.tapper.targets)
            self.var_info.set('ZAMANLAMA %d/%d — her satirin basinda BOSLUK (geri: Backspace, bitir: Esc)' % (n, total))
        elif L is not None and L.timed:
            self.var_info.set('%s — zamanli (LRC)' % L.name)
        elif L is not None:
            self.var_info.set('%s — sarki suresine esit dagitildi; daha iyi eslesme icin "Zamanla"' % L.name)

    # ---------------------------------------------------------------- her kare
    def update_view(self, force=False):
        L = self.lyrics
        if L is None or not self.items:
            return
        if self.prompter:
            rec = self.app.engine.recording if self.app.engine is not None else None
            on = rec is not None
            if on != getattr(self, '_rec_shown', None) or on:
                self._rec_shown = on
                self.btn_rec.config(text='■ Durdur' if on else '● Kayit', bg='#a33a3a' if on else '#7a2a2a')
                if on and int(rec.elapsed) != getattr(self, '_rec_sec', -1):
                    self._rec_sec = int(rec.elapsed)
                    self._info()
                elif not on:
                    self._info()
            return
        if self.tapper is not None:
            nxt = self.tapper.next_index
            idx = (nxt if nxt is not None else len(self.items) - 1)
            f = float(idx)
        else:
            t = self.app.lyrics_time()
            f = 0.0 if (t is None or not L.times) else max(0.0, L.progress_at(t, end=self.app.lyrics_end()))
            idx = int(f)
        i = min(int(f), len(self.centers) - 1)
        frac = f - i
        c = self.centers[i] + (self.centers[min(i + 1, len(self.centers) - 1)] - self.centers[i]) * frac
        anchor = self.cv.winfo_height() * 0.36
        target = anchor - c
        if self.offset is None:
            self.cv.move('ly', 0, target)
        elif abs(target - self.offset) > 0.3:
            self.cv.move('ly', 0, target - self.offset)
        self.offset = target
        if idx != self.cur or force:
            self.cur = idx
            for k, it in enumerate(self.items):
                col = CUR if k == idx else (NEXT if k == idx + 1 else DIM)
                if self.tapper is not None and k == idx:
                    col = TAPC
                self.cv.itemconfigure(it, fill=col)

    # ---------------------------------------------------------------- zamanlama
    def toggle_timing(self):
        if self.tapper is not None:
            self.finish_timing()
            return
        L = self.lyrics
        if L is None or not len(L):
            self.var_info.set('Once soz yukleyin.')
            return
        if not self.app.timing_start():
            self.var_info.set('Zamanlama icin altyapi gerekli (Altyapi sekmesi > Sec…).')
            return
        self.tapper = ly.Tapper(L.lines)
        self.btn_time.config(text='Bitir ve kaydet', bg='#7a5a1a')
        self._info()
        self.update_view(force=True)
        self.focus_set()

    def tap(self):
        if self.tapper is None:
            return
        t = self.app.lyrics_time()
        if t is None:
            return
        self.tapper.tap(t)
        self._info()
        self.update_view(force=True)
        if self.tapper.done:
            self.finish_timing()

    def untap(self):
        if self.tapper is not None:
            self.tapper.undo()
            self._info()
            self.update_view(force=True)

    def finish_timing(self):
        tp, self.tapper = self.tapper, None
        self.btn_time.config(text='Zamanla', bg='#1b2c45')
        if tp is None or not tp.taps:
            self._info()
            return
        times = tp.times()
        L = self.lyrics
        if len(times) < len(L.lines):                   # kalan satirlar: son vurustan sarki sonuna dagit
            rest = L.lines[len(times):]
            end = max(times[-1] + 2.0, self.app.lyrics_end() or (times[-1] + 3.0 * len(rest)))
            extra = ly.distribute(['x'] + rest, end, start=times[-1])[1:]
            times = times + extra
        path = self.app.save_lyrics_timing(L.lines, times)
        self.var_info.set('Zamanlama kaydedildi: %s' % (path.name if path else '(kaydedilemedi)'))
        self.layout()

    # ---------------------------------------------------------------- kayit
    def toggle_record(self):
        if self.counting:
            return
        eng = self.app.engine
        if eng is not None and eng.recording is not None:
            self.app.toggle_record()
            self._info()
            return
        if self.prompter:
            self.goto_silent(0)
        n = int(self.app.cfg.get('prompter_countdown', 3))
        self._countdown(n)

    def goto_silent(self, k):
        self.sec = k
        self._draw_section()

    def _countdown(self, n):
        self.cv.delete('count')
        if n <= 0:
            self.counting = 0
            self.app.prompter_record_start(self.sec if self.prompter else None,
                                           self.section_label(self.sec) if (self.prompter and self.sections) else None)
            self._info()
            self.focus_set()
            return
        self.counting = n
        w, h = max(200, self.cv.winfo_width()), max(150, self.cv.winfo_height())
        self.cv.create_text(w // 2, h // 2, text=str(n), fill=TAPC, font=('Segoe UI', max(60, self.font_size * 3), 'bold'),
                            tags=('count',))
        self._info()
        self.after(1000, lambda: self._countdown(n - 1))

    # ---------------------------------------------------------------- pencere
    def toggle_full(self):
        self.full = not self.full
        self.attributes('-fullscreen', self.full)
        if self.full:
            self.bar.pack_forget()
        else:
            self.bar.pack(fill='x', before=self.cv)
        self.after(50, self.layout)

    def escape(self):
        if self.tapper is not None:
            self.finish_timing()
        elif self.full:
            self.toggle_full()

    def close(self):
        if self.tapper is not None:
            self.finish_timing()
        self.app.lyrics_win = None
        self.destroy()
