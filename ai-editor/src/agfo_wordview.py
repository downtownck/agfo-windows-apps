# -*- coding: utf-8 -*-
"""AGFO AI Editor - Word gorunumu: DOCX'in Word'de cizilmis sayfalari (PDF -> resim), surekli kaydirma, yakinlastirma,
tiklanan yerdeki alana gitme.

Sayfalar yalniz gorunur olanlar icin cizilir (uzun raporda bellek ve hiz). Fare tekerlegi kaydirir, Ctrl+tekerlek
yakinlastirir. Tiklama: on_pick(hedef) - hedef, anchors() ile bulunan alan/kutu.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

PAD = 14


class WordView(tk.Frame):
    def __init__(self, master, colors, on_pick=None, on_hover=None, wheel_register=None):
        self.c = colors
        super().__init__(master, bg=colors['PANEL2'])
        self.on_pick = on_pick
        self.on_hover = on_hover
        self.doc = None
        self.pdf = None
        self.found = []
        self.zoom = 1.0
        self.fit_width = True
        self.sizes = []            # sayfa boyutlari (nokta)
        self.tops = []             # tuvaldeki sayfa ust konumlari (piksel)
        self.images = {}           # sayfa -> PhotoImage
        self.items = {}
        self.canvas = tk.Canvas(self, bg=colors['PANEL2'], highlightthickness=0, bd=0, cursor='hand2')
        self.vs = ttk.Scrollbar(self, orient='vertical', command=self._yview)
        self.canvas.configure(yscrollcommand=self.vs.set)
        self.vs.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.canvas.bind('<Configure>', self._on_resize)
        self.canvas.bind('<Button-1>', self._click)
        self.canvas.bind('<Motion>', self._motion)
        self.canvas.bind('<Control-MouseWheel>', self._ctrl_wheel)
        self.canvas.bind('<Control-Button-4>', lambda e: self.set_zoom(self.zoom * 1.1))
        self.canvas.bind('<Control-Button-5>', lambda e: self.set_zoom(self.zoom / 1.1))
        self.msg = None
        if wheel_register:
            wheel_register(self.canvas, lambda n: self._scroll(n))
        self._resize_job = None
        self._last_width = 0

    # ---------------------------------------------------------------- belge
    def message(self, text):
        self.canvas.delete('all')
        self.images.clear()
        self.items.clear()
        w = max(300, self.canvas.winfo_width())
        self.msg = self.canvas.create_text(w // 2, 80, text=text, fill=self.c['MUTED'], font=('Segoe UI', 10), width=w - 80,
                                           justify='center')

    def set_document(self, pdf_bytes, found=()):
        import pypdfium2 as pdfium
        keep = self.canvas.yview()[0] if self.doc is not None else 0.0
        self.close_doc()
        self.pdf = pdf_bytes
        self.doc = pdfium.PdfDocument(pdf_bytes)
        self.sizes = [self.doc[i].get_size() for i in range(len(self.doc))]
        self.found = list(found)
        self._layout()
        self.canvas.yview_moveto(keep)
        self._draw_visible()

    def close_doc(self):
        self.images.clear()
        self.items.clear()
        self.canvas.delete('all')
        if self.doc is not None:
            try:
                self.doc.close()
            except Exception:
                pass
        self.doc = None

    def destroy(self):
        self.close_doc()
        super().destroy()

    # ---------------------------------------------------------------- yerlesim
    def scale(self):
        if not self.sizes:
            return 1.0
        if self.fit_width:
            w = max(200, self.canvas.winfo_width() - 2 * PAD)
            return w / max(s[0] for s in self.sizes)
        return self.zoom * 96 / 72.0

    def _layout(self):
        self.canvas.delete('all')
        self.images.clear()
        self.items.clear()
        k = self.scale()
        y = PAD
        self.tops = []
        width = max(int(s[0] * k) for s in self.sizes) + 2 * PAD if self.sizes else 0
        for i, (pw, ph) in enumerate(self.sizes):
            self.tops.append(y)
            x = max(PAD, (max(width, self.canvas.winfo_width()) - int(pw * k)) // 2)
            self.canvas.create_rectangle(x + 3, y + 3, x + int(pw * k) + 3, y + int(ph * k) + 3, fill='#000000', outline='',
                                         stipple='gray50', tags=('shadow',))
            self.canvas.create_rectangle(x, y, x + int(pw * k), y + int(ph * k), fill='#ffffff', outline='#c8c8c8', tags=('page%d' % i,))
            y += int(ph * k) + PAD
        self.canvas.configure(scrollregion=(0, 0, max(width, self.canvas.winfo_width()), y))
        self._k = k

    def _page_x(self, i):
        pw = self.sizes[i][0] * self._k
        width = max(int(s[0] * self._k) for s in self.sizes) + 2 * PAD
        return max(PAD, (max(width, self.canvas.winfo_width()) - int(pw)) // 2)

    def _draw_visible(self):
        if self.doc is None:
            return
        top = self.canvas.canvasy(0)
        bot = top + self.canvas.winfo_height()
        want = set()
        for i, t in enumerate(self.tops):
            h = self.sizes[i][1] * self._k
            if t + h >= top - 600 and t <= bot + 600:
                want.add(i)
        for i in list(self.images):
            if i not in want:
                self.canvas.delete(self.items.pop(i, None) or '')
                del self.images[i]
        from PIL import ImageTk
        for i in sorted(want):
            if i in self.images:
                continue
            page = self.doc[i]
            try:
                pil = page.render(scale=self._k, may_draw_forms=True).to_pil()
            finally:
                page.close()
            img = ImageTk.PhotoImage(pil)
            self.images[i] = img
            self.items[i] = self.canvas.create_image(self._page_x(i), self.tops[i], image=img, anchor='nw')

    def _on_resize(self, e):
        if self.fit_width and self.doc is not None and abs(e.width - self._last_width) > 4:
            self._last_width = e.width
            if self._resize_job:
                self.after_cancel(self._resize_job)
            self._resize_job = self.after(150, self._relayout)
        elif self.doc is not None:
            self._draw_visible()

    def _relayout(self):
        self._resize_job = None
        frac = self.canvas.yview()[0]
        self._layout()
        self.canvas.yview_moveto(frac)
        self._draw_visible()

    def _yview(self, *a):
        self.canvas.yview(*a)
        self._draw_visible()

    def _scroll(self, n):
        self.canvas.yview_scroll(n, 'units')
        self._draw_visible()

    def set_zoom(self, z):
        self.fit_width = False
        self.zoom = max(0.4, min(3.0, z))
        self._relayout()

    def fit(self):
        self.fit_width = True
        self._relayout()

    def _ctrl_wheel(self, e):
        self.set_zoom(self.zoom * (1.1 if e.delta > 0 else 1 / 1.1))
        return 'break'

    # ---------------------------------------------------------------- tiklama
    def point_at(self, e):
        """Ekran noktasi -> (sayfa, x, y) PDF noktasi."""
        if self.doc is None:
            return None
        cy, cx = self.canvas.canvasy(e.y), self.canvas.canvasx(e.x)
        for i, t in enumerate(self.tops):
            h = self.sizes[i][1] * self._k
            if t <= cy <= t + h:
                return i, (cx - self._page_x(i)) / self._k, (cy - t) / self._k
        return None

    def target_at(self, e):
        import agfo_docrender as R
        pt = self.point_at(e)
        if pt is None:
            return None
        return R.nearest_anchor(self.found, *pt)

    def _click(self, e):
        t = self.target_at(e)
        if t is not None and self.on_pick:
            self.on_pick(t)

    def _motion(self, e):
        if self.on_hover:
            self.on_hover(self.target_at(e))

    def scroll_to_page(self, i):
        if 0 <= i < len(self.tops):
            total = float(self.canvas.cget('scrollregion').split()[3] or 1)
            self.canvas.yview_moveto(max(0, self.tops[i] - PAD) / total)
            self._draw_visible()
