# -*- coding: utf-8 -*-
"""AGFO AI Editor 1.3 - PDF duzenleyici sekmesi (sayfa / layout gorunumu).

Sayfalar gercek gorunumleriyle (pdfium) alt alta cizilir; gorunen sayfalar ihtiyac oldukca islenir.
Araclar: Sec/Tasi, Vurgula, Not, Metin, Ustune yaz (beyaz kutu + metin), Resim/Imza, Cerceve, Sil.
Sayfa islemleri: dondur, sil, yukari/asagi tasi, baska PDF ekle, secili sayfalari ayri PDF olarak kaydet.
Form alanlari varsa sag panelde doldurulur. Kaydet her zaman 'Farkli kaydet' ile yeni dosya onerir.
"""
from __future__ import annotations

import io
import os
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

import agfo_pdf as P

GAP = 18          # sayfalar arasi bosluk (piksel)
MARGIN = 24
TOOLS = [('select', '↖ Seç'), ('highlight', '▮ Vurgula'), ('note', '✎ Not'), ('text', 'T Metin'),
         ('whiteout', '⬜ Üstüne yaz'), ('image', '🖼 Resim / imza'), ('box', '▭ Çerçeve'), ('erase', '⌫ Sil')]
TOOL_HINT = {
    'select': 'Katmanı seçmek için tıklayın, taşımak için sürükleyin; Delete siler, çift tıklama metni düzenler.',
    'highlight': 'Vurgulanacak alanı sürükleyerek seçin (gerçek PDF vurgusu olarak kaydedilir).',
    'note': 'Not eklemek istediğiniz yere tıklayın.',
    'text': 'Metin kutusunun alanını sürükleyerek çizin.',
    'whiteout': 'Kapatılacak alanı sürükleyin; beyaz kutunun üstüne yeni metni yazın. Not: alttaki eski metin dosyada kalır '
                '(görsel düzeltmedir, karartma/sansür değildir).',
    'image': 'Resim / imza alanını sürükleyerek çizin, ardından PNG/JPG seçin.',
    'box': 'Çerçeve alanını sürükleyerek çizin.',
    'erase': 'Silmek istediğiniz katmana tıklayın.',
}


class PdfView(tk.Frame):
    def __init__(self, app, parent, project: P.PdfProject):
        super().__init__(parent, bg=app_bg(app))
        self.app = app
        self.pr = project
        self.zoom = 1.0
        self.tool = tk.StringVar(value='select')
        self.hcolor = tk.StringVar(value='Sarı')
        self.text_color = '000000'
        self.page_imgs = {}          # i -> PhotoImage
        self.ov_imgs = []            # katman onizleme goruntuleri (referans)
        self.page_y = []             # her sayfanin ust kenari (kanvas)
        self.page_x = []
        self.selected = None         # (sayfa, overlay)
        self.drag = None
        self._render_queue = []
        self.auto_fit = True          # kullanici yakinlastirana kadar sayfa genisligine sigdir
        self._fit_job = None
        self._build()
        self.relayout()

    # ------------------------------------------------------------------ arayuz
    def _build(self):
        a = self.app
        PANEL, PANEL2, FG, MUTED, EDIT_BG = a.colors['PANEL'], a.colors['PANEL2'], a.colors['FG'], a.colors['MUTED'], a.colors['EDIT_BG']
        bar1 = tk.Frame(self, bg=PANEL, padx=8, pady=4)
        bar1.pack(fill='x')
        self.tool_btns = {}
        for key, label in TOOLS:
            b = tk.Radiobutton(bar1, text=label, value=key, variable=self.tool, indicatoron=False, command=self._tool_changed,
                               bg=PANEL2, fg='#ffffff', selectcolor=a.colors['SEL_BG'], activebackground=a.colors['ACCENT'],
                               relief='flat', bd=0, padx=9, pady=4, font=('Segoe UI', 9, 'bold'), cursor='hand2')
            b.pack(side='left', padx=(0, 4))
            self.tool_btns[key] = b
        ttk.Combobox(bar1, textvariable=self.hcolor, values=list(P.HIGHLIGHT_COLORS), width=8, state='readonly').pack(side='left', padx=(6, 4))
        a.btn(bar1, 'Yazı rengi', self._pick_text_color, 'ghost', padx=8)
        a.btn(bar1, 'Kaydet…', self.save, 'primary', side='right')
        bar2 = tk.Frame(self, bg=PANEL, padx=8, pady=3)
        bar2.pack(fill='x')
        for txt, cmd in (('⟲', lambda: self.rotate(-90)), ('⟳', lambda: self.rotate(90)), ('Sayfayı sil', self.delete_pages),
                         ('▲', lambda: self.move(-1)), ('▼', lambda: self.move(1)), ('PDF ekle…', self.insert_pdf),
                         ('Seçili sayfaları ayır…', self.extract_pages)):
            a.btn(bar2, txt, cmd, 'ghost', padx=8)
        tk.Frame(bar2, bg='#2d4a6c', width=1, height=22).pack(side='left', padx=6)
        a.btn(bar2, '↶', self.undo, 'ghost', padx=8)
        a.btn(bar2, '↷', self.redo, 'ghost', padx=8)
        a.btn(bar2, '−', lambda: self._manual_zoom(1 / 1.2), 'ghost', padx=8)
        self.zoom_lbl = tk.Label(bar2, text='100%', fg=MUTED, bg=PANEL, font=('Segoe UI', 9), width=5)
        self.zoom_lbl.pack(side='left')
        a.btn(bar2, '+', lambda: self._manual_zoom(1.2), 'ghost', padx=8)
        a.btn(bar2, 'Sığdır', self.fit_width, 'ghost', padx=8)
        a.btn(bar2, 'Metin olarak aç', self.open_text, 'ghost', side='right', padx=8)
        a.btn(bar2, 'Sayfa metnini al', self.page_text_to_editor, 'ghost', side='right', padx=8)
        self.hint = tk.Label(self, text=TOOL_HINT['select'], fg=MUTED, bg=PANEL, font=('Segoe UI', 8), anchor='w', padx=10)
        self.hint.pack(fill='x')

        body = tk.Frame(self, bg=EDIT_BG)
        body.pack(fill='both', expand=True)
        left = tk.Frame(body, bg=PANEL, width=120)
        left.pack(side='left', fill='y')
        tk.Label(left, text='Sayfalar', fg=MUTED, bg=PANEL, font=('Segoe UI', 8, 'bold')).pack(anchor='w', padx=6, pady=(4, 0))
        self.page_list = tk.Listbox(left, selectmode='extended', bg=EDIT_BG, fg=FG, selectbackground=a.colors['SEL_BG'],
                                    highlightthickness=0, bd=0, width=14, font=('Segoe UI', 9), activestyle='none', exportselection=False)
        self.page_list.pack(fill='both', expand=True, padx=4, pady=4)
        self.page_list.bind('<<ListboxSelect>>', self._list_selected)
        self.form_frame = None
        if self.pr.fields:
            self._build_form(body)
        cv_wrap = tk.Frame(body, bg=EDIT_BG)
        cv_wrap.pack(side='left', fill='both', expand=True)
        self.canvas = tk.Canvas(cv_wrap, bg='#3a4656', highlightthickness=0, bd=0)
        ys = ttk.Scrollbar(cv_wrap, orient='vertical', command=self._yview)
        xs = ttk.Scrollbar(cv_wrap, orient='horizontal', command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        ys.pack(side='right', fill='y')
        xs.pack(side='bottom', fill='x')
        self.canvas.pack(side='left', fill='both', expand=True)
        c = self.canvas
        c.bind('<Configure>', self._on_configure)
        c.bind('<ButtonPress-1>', self._press)
        c.bind('<B1-Motion>', self._motion)
        c.bind('<ButtonRelease-1>', self._release)
        c.bind('<Double-Button-1>', self._double)
        c.bind('<MouseWheel>', self._wheel)
        c.bind('<Button-4>', lambda e: self._scroll(-3))
        c.bind('<Button-5>', lambda e: self._scroll(3))
        c.bind('<Delete>', lambda e: self.delete_selected())
        c.bind('<Control-z>', lambda e: self.undo())
        c.bind('<Control-y>', lambda e: self.redo())

    def _build_form(self, body):
        a = self.app
        f = tk.Frame(body, bg=a.colors['PANEL'], width=260, padx=8, pady=6)
        f.pack(side='right', fill='y')
        f.pack_propagate(False)
        tk.Label(f, text='Form alanları', fg=a.colors['FG'], bg=a.colors['PANEL'], font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        tk.Label(f, text='Değerler kaydedilen PDF\'ye yazılır.', fg=a.colors['MUTED'], bg=a.colors['PANEL'],
                 font=('Segoe UI', 8), wraplength=240, justify='left').pack(anchor='w', pady=(0, 6))
        inner = tk.Frame(f, bg=a.colors['PANEL'])
        inner.pack(fill='both', expand=True)
        self.form_vars = {}
        for name, info in list(self.pr.fields.items())[:60]:
            tk.Label(inner, text=name[:40], fg=a.colors['MUTED'], bg=a.colors['PANEL'], font=('Segoe UI', 8)).pack(anchor='w')
            if info['type'] == 'check':
                var = tk.BooleanVar(value=info['value'] not in ('', '/Off', 'Off'))
                ttk.Checkbutton(inner, variable=var, command=lambda n=name, v=var: self.pr.set_field(n, '/Yes' if v.get() else '/Off')).pack(anchor='w')
            else:
                var = tk.StringVar(value=info['value'])
                w = ttk.Combobox(inner, textvariable=var, values=info['options']) if info['type'] == 'choice' and info['options'] \
                    else ttk.Entry(inner, textvariable=var)
                w.pack(fill='x', pady=(0, 4))
                w.bind('<FocusOut>', lambda e, n=name, v=var: self._field_changed(n, v.get()))
                w.bind('<Return>', lambda e, n=name, v=var: self._field_changed(n, v.get()))
            self.form_vars[name] = var
        self.form_frame = f

    def _field_changed(self, name, value):
        if self.pr.form_values.get(name, self.pr.fields.get(name, {}).get('value')) != value:
            self.pr.set_field(name, value)
            self._changed()

    # ------------------------------------------------------------------ yerlesim + cizim
    def relayout(self):
        """Sayfa konumlarini hesaplar, kanvasi yeniden kurar; goruntuler ihtiyac oldukca islenir."""
        c = self.canvas
        c.delete('all')
        self.page_imgs.clear()
        self.ov_imgs.clear()
        self.page_y, self.page_x = [], []
        width = max((self.pr.display_size(i)[0] for i in range(len(self.pr.pages))), default=595) * self.zoom
        y = MARGIN
        for i in range(len(self.pr.pages)):
            w, h = (v * self.zoom for v in self.pr.display_size(i))
            x = MARGIN + (width - w) / 2
            self.page_x.append(x)
            self.page_y.append(y)
            c.create_rectangle(x + 3, y + 3, x + w + 3, y + h + 3, fill='#1b2230', outline='', tags=('shadow',))
            c.create_rectangle(x, y, x + w, y + h, fill='#ffffff', outline='#8899aa', tags=('page', 'p%d' % i))
            c.create_text(x + w / 2, y + h / 2, text='Sayfa %d' % (i + 1), fill='#99a3b0', font=('Segoe UI', 12), tags=('ph%d' % i,))
            y += h + GAP
        c.configure(scrollregion=(0, 0, width + 2 * MARGIN, y + MARGIN))
        self._refresh_list()
        self._schedule_render()
        for i in range(len(self.pr.pages)):
            self._draw_overlays(i)
        self.app._update_status()

    def _refresh_list(self):
        sel = set(self.page_list.curselection())
        self.page_list.delete(0, 'end')
        for i, p in enumerate(self.pr.pages):
            extra = []
            if p['rot']:
                extra.append('↻%d' % p['rot'])
            if p['overlays']:
                extra.append('✎%d' % len(p['overlays']))
            src = '' if p['src'] == self.pr.path else ' +'
            self.page_list.insert('end', '%3d%s  %s' % (i + 1, src, ' '.join(extra)))
        for i in sel:
            if i < len(self.pr.pages):
                self.page_list.selection_set(i)

    def _visible_pages(self):
        c = self.canvas
        top, bottom = c.canvasy(0), c.canvasy(c.winfo_height() or 800)
        out = []
        for i, y in enumerate(self.page_y):
            h = self.pr.display_size(i)[1] * self.zoom
            if y + h >= top - 400 and y <= bottom + 400:
                out.append(i)
        return out

    def _schedule_render(self):
        self._render_queue = [i for i in self._visible_pages() if i not in self.page_imgs]
        if self._render_queue and not getattr(self, '_render_pending', False):
            self._render_pending = True
            self.after(10, self._render_next)

    def _render_next(self):
        self._render_pending = False
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        if not self._render_queue:
            return
        i = self._render_queue.pop(0)
        if i < len(self.pr.pages) and i not in self.page_imgs:
            try:
                from PIL import ImageTk
                img = self.pr.render(i, self.zoom * 1.0)
                ph = ImageTk.PhotoImage(img)
                self.page_imgs[i] = ph
                c = self.canvas
                c.delete('ph%d' % i)
                c.create_image(self.page_x[i], self.page_y[i], image=ph, anchor='nw', tags=('img', 'img%d' % i))
                c.tag_raise('ov%d' % i)
            except Exception as e:  # bozuk sayfa: yer tutucuda hata yaz
                self.canvas.itemconfigure('ph%d' % i, text='Sayfa %d gösterilemedi: %s' % (i + 1, str(e)[:60]))
        if self._render_queue:
            self._render_pending = True
            self.after(1, self._render_next)

    def _draw_overlays(self, i):
        from PIL import Image, ImageTk
        c = self.canvas
        c.delete('ov%d' % i)
        x0, y0, z = self.page_x[i], self.page_y[i], self.zoom
        for ov in self.pr.pages[i]['overlays']:
            a, b, cc, d = ov['rect']
            X1, Y1, X2, Y2 = x0 + a * z, y0 + b * z, x0 + cc * z, y0 + d * z
            w, h = max(1, int(X2 - X1)), max(1, int(Y2 - Y1))
            t = ov['type']
            if t == 'highlight':
                rgb = P.hex_rgb(ov.get('color', 'ffeb3b'))
                ph = ImageTk.PhotoImage(Image.new('RGBA', (w, h), rgb + (110,)))
                self.ov_imgs.append(ph)
                c.create_image(X1, Y1, image=ph, anchor='nw', tags=('ov', 'ov%d' % i))
            elif t == 'note':
                c.create_rectangle(X1, Y1, X1 + 18, Y1 + 18, fill='#ffd43b', outline='#e67700', tags=('ov', 'ov%d' % i))
                c.create_text(X1 + 9, Y1 + 9, text='✎', fill='#5c3c00', font=('Segoe UI', 9, 'bold'), tags=('ov', 'ov%d' % i))
            elif t in ('text', 'whiteout'):
                img = P.render_text_image(ov.get('text', ''), cc - a, d - b, ov.get('size', 11), ov.get('color', '000000'),
                                          ov.get('whiteout', False), ov.get('bold', False), dpi=72 * z)
                ph = ImageTk.PhotoImage(img.resize((w, h)))
                self.ov_imgs.append(ph)
                c.create_image(X1, Y1, image=ph, anchor='nw', tags=('ov', 'ov%d' % i))
            elif t == 'image':
                img = Image.open(io.BytesIO(ov['data'])).convert('RGBA').resize((w, h))
                ph = ImageTk.PhotoImage(img)
                self.ov_imgs.append(ph)
                c.create_image(X1, Y1, image=ph, anchor='nw', tags=('ov', 'ov%d' % i))
            elif t == 'box':
                c.create_rectangle(X1, Y1, X2, Y2, outline='#' + ov.get('color', 'e03131'), width=max(1, ov.get('width', 1.5) * z),
                                   tags=('ov', 'ov%d' % i))
            if self.selected and self.selected[1] is ov:
                c.create_rectangle(X1 - 2, Y1 - 2, X2 + 2, Y2 + 2, outline='#49b3ef', dash=(4, 2), width=2, tags=('ov', 'ov%d' % i))

    def _on_configure(self, e):
        if self.auto_fit and e.width > 200:
            if self._fit_job:
                self.after_cancel(self._fit_job)
            self._fit_job = self.after(120, lambda: self.fit_width(auto=True))
        self._schedule_render()

    # ------------------------------------------------------------------ gezinme
    def _yview(self, *args):
        self.canvas.yview(*args)
        self._schedule_render()
        self.app._update_status()

    def _scroll(self, units):
        self.canvas.yview_scroll(units, 'units')
        self._schedule_render()
        self.app._update_status()

    def _wheel(self, e):
        if e.state & 0x0004:     # Ctrl + teker: yakinlastir
            self.auto_fit = False
            self.set_zoom(self.zoom * (1.1 if e.delta > 0 else 1 / 1.1))
        else:
            self._scroll(-1 * int(e.delta / 120) * 3 if e.delta else 0)

    def set_zoom(self, z):
        z = max(0.25, min(4.0, z))
        frac = self.canvas.yview()[0] if self.page_y else 0
        self.zoom = z
        self.zoom_lbl.configure(text='%d%%' % round(z * 100))
        self.relayout()
        self.canvas.yview_moveto(frac)
        self._schedule_render()

    def _manual_zoom(self, k):
        self.auto_fit = False
        self.set_zoom(self.zoom * k)

    def fit_width(self, auto=False):
        self._fit_job = None
        if not auto:
            self.auto_fit = True
        w = self.canvas.winfo_width()
        if w < 50:
            return
        maxw = max((self.pr.display_size(i)[0] for i in range(len(self.pr.pages))), default=595)
        z = max(0.25, min(4.0, (w - 2 * MARGIN - 4) / maxw))
        if abs(z - self.zoom) > 0.01:
            self.set_zoom(z)

    def current_page(self):
        mid = self.canvas.canvasy((self.canvas.winfo_height() or 600) / 3)
        cur = 0
        for i, y in enumerate(self.page_y):
            if y <= mid:
                cur = i
        return cur

    def goto(self, i):
        if 0 <= i < len(self.page_y):
            total = float(self.canvas.cget('scrollregion').split()[3]) or 1
            self.canvas.yview_moveto(max(0, (self.page_y[i] - 8) / total))
            self._schedule_render()

    def _list_selected(self, _e=None):
        sel = self.page_list.curselection()
        if sel:
            self.goto(sel[0])

    def selected_pages(self):
        sel = list(self.page_list.curselection())
        return sel or [self.current_page()]

    # ------------------------------------------------------------------ fare
    def _hit(self, e):
        cx, cy = self.canvas.canvasx(e.x), self.canvas.canvasy(e.y)
        for i, (x, y) in enumerate(zip(self.page_x, self.page_y)):
            w, h = (v * self.zoom for v in self.pr.display_size(i))
            if x <= cx <= x + w and y <= cy <= y + h:
                return i, (cx - x) / self.zoom, (cy - y) / self.zoom, cx, cy
        return None, None, None, cx, cy

    def _press(self, e):
        self.canvas.focus_set()
        i, px, py, cx, cy = self._hit(e)
        tool = self.tool.get()
        self.drag = None
        if i is None:
            return
        if tool in ('select', 'erase'):
            ov = self.pr.overlay_at(i, px, py)
            if tool == 'erase':
                if ov:
                    self.pr.remove_overlay(i, ov)
                    self._changed(i)
                return
            prev = self.selected
            self.selected = (i, ov) if ov else None
            if prev:
                self._draw_overlays(prev[0])
            if ov:
                was_dirty = self.pr.dirty
                self.pr.snapshot()
                self.drag = {'mode': 'move', 'page': i, 'ov': ov, 'start': (px, py), 'rect': ov['rect'], 'moved': False,
                             'was_dirty': was_dirty}
                self._draw_overlays(i)
            return
        if tool == 'note':
            self._add_note(i, px, py)
            return
        self.drag = {'mode': 'rect', 'page': i, 'start': (px, py), 'cstart': (cx, cy)}
        self.canvas.delete('rubber')
        self.canvas.create_rectangle(cx, cy, cx, cy, outline='#49b3ef', dash=(3, 2), width=2, tags=('rubber',))

    def _motion(self, e):
        d = self.drag
        if not d:
            return
        i = d['page']
        cx, cy = self.canvas.canvasx(e.x), self.canvas.canvasy(e.y)
        if d['mode'] == 'rect':
            x1, y1 = d['cstart']
            self.canvas.coords('rubber', x1, y1, cx, cy)
        elif d['mode'] == 'move':
            px, py = (cx - self.page_x[i]) / self.zoom, (cy - self.page_y[i]) / self.zoom
            dx, dy = px - d['start'][0], py - d['start'][1]
            a, b, c, dd = d['rect']
            W, H = self.pr.display_size(i)
            dx = max(-a, min(W - c, dx))
            dy = max(-b, min(H - dd, dy))
            d['ov']['rect'] = (a + dx, b + dy, c + dx, dd + dy)
            d['moved'] = True
            self._draw_overlays(i)

    def _release(self, e):
        d, self.drag = self.drag, None
        self.canvas.delete('rubber')
        if not d:
            return
        i = d['page']
        if d['mode'] == 'move':
            if not d['moved']:          # yalniz secim: bos snapshot'i geri al
                self.pr.undo_stack.pop()
                self.pr.dirty = d['was_dirty']
            else:
                self._changed(i)
            return
        cx, cy = self.canvas.canvasx(e.x), self.canvas.canvasy(e.y)
        W, H = self.pr.display_size(i)
        px = max(0, min(W, (cx - self.page_x[i]) / self.zoom))
        py = max(0, min(H, (cy - self.page_y[i]) / self.zoom))
        rect = P.norm_rect((d['start'][0], d['start'][1], px, py))
        if rect[2] - rect[0] < 6 or rect[3] - rect[1] < 6:
            if self.tool.get() in ('text', 'whiteout', 'image', 'box'):
                rect = (rect[0], rect[1], min(W, rect[0] + 220), min(H, rect[1] + 40))
            else:
                return
        self._create_overlay(i, rect)

    def _double(self, e):
        i, px, py, _cx, _cy = self._hit(e)
        if i is None:
            return
        ov = self.pr.overlay_at(i, px, py)
        if ov and ov['type'] in ('text', 'whiteout', 'note', 'highlight'):
            res = TextDialog.ask(self, 'Metni düzenle', ov.get('text', ''), ov.get('size', 11), ov.get('bold', False),
                                 simple=ov['type'] in ('note', 'highlight'))
            if res is not None:
                self.pr.snapshot()
                ov['text'], ov['size'], ov['bold'] = res
                self._changed(i)

    # ------------------------------------------------------------------ katman olusturma
    def _create_overlay(self, i, rect):
        tool = self.tool.get()
        if tool == 'highlight':
            self.pr.add_overlay(i, {'type': 'highlight', 'rect': rect, 'color': P.HIGHLIGHT_COLORS.get(self.hcolor.get(), 'ffeb3b')})
        elif tool == 'box':
            self.pr.add_overlay(i, {'type': 'box', 'rect': rect, 'color': 'e03131', 'width': 1.5})
        elif tool in ('text', 'whiteout'):
            res = TextDialog.ask(self, 'Üstüne yaz' if tool == 'whiteout' else 'Metin ekle', '', 11, False)
            if res is None:
                return
            text, size, bold = res
            self.pr.add_overlay(i, {'type': 'text', 'rect': rect, 'text': text, 'size': size, 'bold': bold,
                                    'color': self.text_color, 'whiteout': tool == 'whiteout'})
        elif tool == 'image':
            path = filedialog.askopenfilename(parent=self, title='Resim / imza seç', filetypes=[('Resim', '*.png *.jpg *.jpeg')])
            if not path:
                return
            try:
                from PIL import Image
                with open(path, 'rb') as f:
                    data = f.read()
                im = Image.open(io.BytesIO(data))
                iw, ih = im.size
            except Exception as e:
                messagebox.showerror('Resim', 'Resim açılamadı: %s' % e, parent=self)
                return
            a, b, c, d = rect          # en-boy oranini koru, alana sigdir
            bw, bh = c - a, d - b
            k = min(bw / iw, bh / ih)
            nw, nh = iw * k, ih * k
            rect = (a, b, a + nw, b + nh)
            self.pr.add_overlay(i, {'type': 'image', 'rect': rect, 'data': data})
        self._changed(i)

    def _add_note(self, i, px, py):
        res = TextDialog.ask(self, 'Not ekle', '', 11, False, simple=True)
        if res is None or not res[0].strip():
            return
        self.pr.add_overlay(i, {'type': 'note', 'rect': (px, py, px + 18, py + 18), 'text': res[0]})
        self._changed(i)

    def _pick_text_color(self):
        c = colorchooser.askcolor(color='#' + self.text_color, parent=self, title='Yazı rengi')
        if c and c[1]:
            self.text_color = c[1].lstrip('#')

    def _tool_changed(self):
        self.hint.configure(text=TOOL_HINT.get(self.tool.get(), ''))
        self.canvas.configure(cursor='arrow' if self.tool.get() == 'select' else 'crosshair')

    def delete_selected(self):
        if self.selected:
            i, ov = self.selected
            self.selected = None
            self.pr.remove_overlay(i, ov)
            self._changed(i)

    def _changed(self, i=None):
        self.pr.dirty = True
        if i is None:
            self.relayout()
        else:
            self._draw_overlays(i)
            self._refresh_list()
        self.app._pdf_changed(self)

    # ------------------------------------------------------------------ sayfa islemleri
    def rotate(self, deg):
        self.pr.rotate(self.selected_pages(), deg)
        self.selected = None
        self._changed()

    def delete_pages(self):
        idx = self.selected_pages()
        if not messagebox.askyesno('Sayfa sil', '%d sayfa silinsin mi? (Geri al ile dönebilirsiniz.)' % len(idx), parent=self):
            return
        try:
            self.pr.delete(idx)
        except P.PdfError as e:
            messagebox.showwarning('Sayfa sil', str(e), parent=self)
            return
        self.page_list.selection_clear(0, 'end')
        self.selected = None
        self._changed()

    def move(self, delta):
        new = self.pr.move(self.selected_pages(), delta)
        self.selected = None
        self._changed()
        self.page_list.selection_clear(0, 'end')
        for i in new:
            self.page_list.selection_set(i)
        if new:
            self.goto(new[0])

    def insert_pdf(self):
        path = filedialog.askopenfilename(parent=self, title='Eklenecek PDF', filetypes=[('PDF', '*.pdf')])
        if not path:
            return
        sel = self.page_list.curselection()
        at = (max(sel) + 1) if sel else None
        try:
            n = self.pr.insert_pdf(path, at)
        except (P.PdfError, OSError) as e:
            messagebox.showerror('PDF ekle', str(e), parent=self)
            return
        self._changed()
        self.app.flash('%d sayfa eklendi: %s' % (n, os.path.basename(path)))

    def extract_pages(self):
        idx = sorted(self.selected_pages())
        name = '%s (sayfa %s).pdf' % (os.path.splitext(os.path.basename(self.pr.path))[0],
                                      ('%d' % (idx[0] + 1)) if len(idx) == 1 else '%d-%d' % (idx[0] + 1, idx[-1] + 1))
        out = filedialog.asksaveasfilename(parent=self, title='Seçili sayfaları ayrı PDF olarak kaydet', initialfile=name,
                                           initialdir=os.path.dirname(self.pr.path), defaultextension='.pdf', filetypes=[('PDF', '*.pdf')])
        if not out:
            return
        if os.path.normcase(os.path.abspath(out)) == os.path.normcase(self.pr.path):
            messagebox.showwarning('Kaydet', 'Açık olan özgün PDF\'nin üzerine sayfa ayırma yapılamaz; başka bir ad seçin.', parent=self)
            return
        try:
            self.pr.save(out, pages=idx)
        except Exception as e:
            messagebox.showerror('Kaydet', str(e), parent=self)
            return
        self.app.flash('%d sayfa kaydedildi: %s' % (len(idx), out), 9000)

    def undo(self):
        if self.pr.undo():
            self.selected = None
            self._changed()

    def redo(self):
        if self.pr.redo():
            self.selected = None
            self._changed()

    # ------------------------------------------------------------------ kaydet + metin
    def save(self):
        out = filedialog.asksaveasfilename(parent=self, title='PDF\'yi kaydet', initialfile=os.path.basename(P.suggest_name(self.pr.path)),
                                           initialdir=os.path.dirname(self.pr.path), defaultextension='.pdf', filetypes=[('PDF', '*.pdf')])
        if not out:
            return False
        if os.path.normcase(os.path.abspath(out)) == os.path.normcase(self.pr.path):
            if not messagebox.askyesno('Üzerine yaz', 'Özgün PDF\'nin üzerine yazılsın mı? Bu geri alınamaz.\n\n%s' % out, parent=self):
                return False
        try:
            self.pr.save(out)
        except Exception as e:
            messagebox.showerror('Kaydedilemedi', str(e), parent=self)
            return False
        self.app._pdf_changed(self)
        self.app.flash('PDF kaydedildi: %s' % out, 9000)
        return True

    def open_text(self):
        self.app.open_as_text(self.pr.path)

    def page_text_to_editor(self):
        i = self.current_page() if not self.page_list.curselection() else self.page_list.curselection()[0]
        text = self.pr.page_text(i).strip()
        if not text:
            messagebox.showinfo('Sayfa metni', 'Bu sayfada metin katmanı yok (taranmış olabilir).', parent=self)
            return
        self.app.new_doc(text, '%s — s. %d' % (os.path.basename(self.pr.path), i + 1))
        self.app.flash('Sayfa metni yeni sekmede. Çeviri, özet ve düzenleme için sağdaki AI panelini kullanın.')

    def status_text(self):
        return 'PDF · sayfa %d / %d · %%%d · %s%s' % (self.current_page() + 1, len(self.pr.pages), round(self.zoom * 100),
                                                     os.path.basename(self.pr.path), ' · kaydedilmedi' if self.pr.dirty else '')


class TextDialog(tk.Toplevel):
    def __init__(self, master, title, text, size, bold, simple=False):
        super().__init__(master)
        self.title(title)
        self.configure(bg='#12243b')
        self.transient(master.winfo_toplevel())
        self.result = None
        self.txt = tk.Text(self, width=48, height=6, wrap='word', bg='#0e1b2e', fg='#ecf3ff', insertbackground='#49b3ef',
                           font=('Segoe UI', 10), relief='flat', padx=6, pady=6)
        self.txt.pack(padx=12, pady=(12, 6), fill='both', expand=True)
        self.txt.insert('1.0', text)
        row = tk.Frame(self, bg='#12243b')
        row.pack(fill='x', padx=12)
        self.size = tk.IntVar(value=size)
        self.bold = tk.BooleanVar(value=bold)
        if not simple:
            tk.Label(row, text='Boyut', fg='#a5b6ce', bg='#12243b').pack(side='left')
            ttk.Spinbox(row, from_=6, to=72, textvariable=self.size, width=5).pack(side='left', padx=(4, 10))
            ttk.Checkbutton(row, text='Kalın', variable=self.bold).pack(side='left')
        b = tk.Frame(self, bg='#12243b')
        b.pack(fill='x', padx=12, pady=10)
        tk.Button(b, text='Tamam', command=self._ok, bg='#1f6fa3', fg='#ffffff', relief='flat', padx=14, pady=4).pack(side='right')
        tk.Button(b, text='Vazgeç', command=self.destroy, bg='#192e48', fg='#ffffff', relief='flat', padx=14, pady=4).pack(side='right', padx=6)
        self.bind('<Escape>', lambda e: self.destroy())
        self.txt.focus_set()

    def _ok(self):
        try:
            size = max(6, min(72, int(self.size.get())))
        except (tk.TclError, ValueError):
            size = 11
        self.result = (self.txt.get('1.0', 'end-1c'), size, bool(self.bold.get()))
        self.destroy()

    @classmethod
    def ask(cls, master, title, text='', size=11, bold=False, simple=False):
        hook = getattr(master.app, 'dialog_hook', None)      # testler icin
        if hook:
            return hook(title, text, size, bold)
        d = cls(master, title, text, size, bold, simple)
        d.grab_set()
        master.wait_window(d)
        return d.result


def app_bg(app):
    return app.colors['EDIT_BG']
