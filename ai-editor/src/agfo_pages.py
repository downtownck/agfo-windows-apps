# -*- coding: utf-8 -*-
"""AGFO AI Editor 2.12 - Sayfa gorunumunde gercek sayfalar.

Belge tek bir Text bileseninde akar; bu modul onu sayfa boyutu oraninda sayfalara boler:
  * Her paragrafin yuksekligi olculur; sayfanin yazi alanina sigmayan paragraf bir sonraki sayfaya gecer
    (Word'deki gibi sayfa sonu paragraf sinirinda). Elle eklenen sayfa sonu (Ctrl+Enter) yeni sayfa baslatir.
  * Yeni sayfanin ilk paragrafina gecici 'pgap_<bosluk>' etiketiyle bosluk verilir: onceki sayfanin alt kenar boslugu +
    sayfalar arasi masa araligi + yeni sayfanin ust kenar boslugu. Son paragrafa 'pgend' ile sayfanin kalani eklenir.
    Bu etiketler kayda, panoya, geri almaya ve kaydedilen dosyaya girmez (agfo_richtext.TRANSIENT).
  * Sayfalar arasindaki araliga ve son sayfanin altina masa renginde ince seritler bindirilir (yazinin ustune
    gelmez; yalnizca kenar bosluklarinin arasindaki bolgeye). Seritlerde sayfa numarasi yazar.
Bir paragraf tek basina bir sayfadan uzunsa bolunmez; o sayfa uzun gorunur (nadir).
"""
from __future__ import annotations

import tkinter as tk

GAP_PT = 14          # sayfalar arasi masa araligi (nokta)
DELAY_MS = 350       # yazarken yeniden sayfalama gecikmesi


def plan_pages(heights, content_h, breaks=()):
    """Paragraf yukseklikleri -> (yeni sayfaya gecen paragraflar (0 tabanli), her sayfanin dolu yuksekligi).

    heights: her paragrafin piksel yuksekligi; content_h: bir sayfanin yazi alani; breaks: oncesinde elle sayfa sonu
    olan paragraflar. Ilk paragraf her zaman 1. sayfanin basidir ve listede yer almaz. used[k], k. sayfada yazinin
    kapladigi yukseklik (sayfanin bos kalan alti = content_h - used[k])."""
    starts, used, cur = [], [], 0.0
    brk = set(breaks)
    for k, h in enumerate(heights):
        if k and (k in brk or (cur > 0 and cur + h > content_h)):
            starts.append(k)
            used.append(cur)
            cur = 0.0
        cur += h
        if cur > content_h:                      # sayfadan uzun tek paragraf: tasan kisim sonraki sayfaya sayilir
            cur = cur % content_h if content_h > 0 else 0.0
    used.append(cur)
    return starts, used


class PageDecor:
    """Bir belgenin sayfa gorunumu bezemesi. app._place_text sonrasi ve her degisiklikte schedule() cagrilir."""

    def __init__(self, text, desk, desk_color, label_color='#d8dee6'):
        self.t, self.desk = text, desk
        self.desk_color, self.label_color = desk_color, label_color
        self.starts = []           # yeni sayfaya gecen satir numaralari (1 tabanli, Text satiri)
        self.free = [0]            # her sayfanin bos kalan alt kismi (piksel)
        self._gap_tags = []        # pgap_<bosluk> etiketleri
        self.page_h = 0
        self._job = None
        self._draw_job = None
        self._strips = []          # [(cerceve, etiket)]
        self._sig = None
        self.enabled = False
        self.on_update = None      # sayfalama bitince (durum cubugu)
        text.bind('<Configure>', lambda e: self.schedule(), add='+')
        text.bind('<KeyRelease>', lambda e: self.schedule(), add='+')
        self._poll()

    # ---------------------------------------------------------------- olcum
    def _pads(self):
        t = self.t
        top = int(float(t.cget('pady')))
        return top, top

    def metrics(self):
        """(sayfa yuksekligi, yazi alani, ust bosluk, alt bosluk, aralik) piksel."""
        t = self.t
        import agfo_richdoc as R
        w_pt, h_pt = R.page_dims(t.page)
        width = max(1, t.winfo_width())
        page_w = t.px(w_pt)
        scale = min(1.0, width / page_w) if page_w else 1.0   # dar pencerede sayfa genisligi kuculur, oran korunur
        page_h = int(t.px(h_pt) * scale) if scale < 1.0 else int(t.px(h_pt))
        top, bottom = self._pads()
        return page_h, max(40, page_h - top - bottom), top, bottom, int(t.px(GAP_PT))

    def _clear_tags(self):
        call = self.t._call
        for tag in ['pgend'] + list(self._gap_tags):
            try:
                call('tag', 'remove', tag, '1.0', 'end')
            except tk.TclError:
                pass

    def paginate(self):
        self._job = None
        t = self.t
        if not self.enabled or not t.winfo_exists():
            return
        call = t._call
        self._clear_tags()
        page_h, content_h, top, bottom, gap = self.metrics()
        self.page_h = page_h
        try:
            call('count', '-update', '-ypixels', '1.0', 'end')
            n = int(str(call('index', 'end-1c')).split('.')[0])
        except tk.TclError:
            return
        heights, breaks = [], []
        for line in range(1, n + 1):
            try:
                h = call('count', '-ypixels', '%d.0' % line, '%d.0' % (line + 1))
                h = int(h[0] if isinstance(h, tuple) else (h or 0))
            except (tk.TclError, ValueError):
                h = 0
            if line == n:                       # son satir: 'end' sinirinda olcum bos donebilir
                try:
                    info = call('count', '-ypixels', '%d.0' % line, 'end')
                    h = max(h, int(info[0] if isinstance(info, tuple) else (info or 0)))
                except (tk.TclError, ValueError):
                    pass
            heights.append(h)
            if line > 1 and 'pb' in {str(x) for x in call('tag', 'names', '%d.0' % line)}:
                breaks.append(line - 1)
        starts, used = plan_pages(heights, content_h, breaks)
        self.starts = [k + 1 for k in starts]
        self.free = [max(0, int(content_h - u)) for u in used]       # her sayfanin bos kalan alti
        # sayfa basi bosluklari farkli (onceki sayfanin bos kalan alti + alt bosluk + aralik + ust bosluk):
        # ayni bosluga sahip sayfa baslari ayni etiketi paylasir
        groups = {}
        for k, line in enumerate(self.starts):
            groups.setdefault(self.free[k] + bottom + gap + top, []).append(line)
        for name in self._gap_tags:
            call('tag', 'delete', name)
        self._gap_tags = []
        for space, lines in groups.items():
            name = 'pgap_%d' % space
            self._gap_tags.append(name)
            call('tag', 'configure', name, '-spacing1', space)
            for line in lines:
                call('tag', 'add', name, '%d.0' % line, '%d.0 lineend' % line)
            call('tag', 'raise', name)
        call('tag', 'configure', 'pgend', '-spacing3', self.free[-1])
        call('tag', 'add', 'pgend', '%d.0' % n, '%d.0 lineend' % n)
        call('tag', 'raise', 'pgend')
        self.draw()
        if self.on_update:
            try:
                self.on_update()
            except Exception:
                pass

    def schedule(self, delay=DELAY_MS):
        if not self.enabled:
            return
        if self._job:
            try:
                self.t.after_cancel(self._job)
            except (tk.TclError, ValueError):
                pass
        try:
            self._job = self.t.after(delay, self.paginate)
        except tk.TclError:
            self._job = None

    def _poll(self):
        """Geri al / yinele / bicim degisiklikleri de yakalansin diye: belge imzasi degistiyse yeniden sayfala."""
        t = self.t
        try:
            if not t.winfo_exists():
                return
        except tk.TclError:
            return
        if self.enabled:
            try:
                sig = (len(t.undo.stack), len(t.undo.redo_stack), t._call('index', 'end'), t.zoom)
            except (tk.TclError, AttributeError):
                sig = None
            if sig != self._sig:
                self._sig = sig
                self.schedule(150)
        t.after(900, self._poll)

    # ---------------------------------------------------------------- acma / kapama
    def set_enabled(self, on):
        self.enabled = bool(on)
        if self.enabled:
            self.schedule(10)
        else:
            self._clear_tags()
            self.starts = []
            self._hide_strips(0)

    # ---------------------------------------------------------------- cizim
    def draw_soon(self):
        if self._draw_job is None:
            try:
                self._draw_job = self.t.after_idle(self.draw)
            except tk.TclError:
                self._draw_job = None

    def _strip(self, k):
        while len(self._strips) <= k:
            f = tk.Frame(self.desk, bg=self.desk_color, highlightthickness=0, bd=0)
            lb = tk.Label(f, text='', bg=self.desk_color, fg=self.label_color, font=('Segoe UI', 8))
            lb.place(relx=1.0, rely=0.5, anchor='e', x=-6)
            for w in (f, lb):
                w.bind('<MouseWheel>', self._wheel)
                w.bind('<Button-4>', self._wheel)
                w.bind('<Button-5>', self._wheel)
            self._strips.append((f, lb))
        return self._strips[k]

    def _hide_strips(self, start):
        for f, _lb in self._strips[start:]:
            f.place_forget()

    def _wheel(self, e):
        n = -1 if (getattr(e, 'delta', 0) > 0 or getattr(e, 'num', 0) == 4) else 1
        self.t.yview_scroll(n * 3, 'units')
        return 'break'

    def page_of(self, index='insert'):
        """1 tabanli sayfa numarasi."""
        try:
            line = int(str(self.t.index(index)).split('.')[0])
        except tk.TclError:
            return 1
        return 1 + sum(1 for s in self.starts if s <= line)

    def count(self):
        return len(self.starts) + 1

    def draw(self):
        self._draw_job = None
        t = self.t
        if not self.enabled:
            self._hide_strips(0)
            return
        try:
            tx, ty, tw, th = t.winfo_x(), t.winfo_y(), t.winfo_width(), t.winfo_height()
        except tk.TclError:
            return
        _page_h, _content_h, top, bottom, gap = self.metrics()
        k = 0
        total = self.count()
        for num, line in enumerate(self.starts, start=2):
            info = t.dlineinfo('%d.0' % line)
            if not info:
                continue
            y = info[1] + self.free[num - 2] + bottom      # onceki sayfanin bos kalan alti ve alt kenar boslugundan sonra
            y0, y1 = max(0, y), min(th, y + gap)
            if y1 <= y0:
                continue
            f, lb = self._strip(k)
            k += 1
            lb.configure(text='%d / %d' % (num, total) if y1 - y0 >= 12 else '')
            f.place(x=tx, y=ty + y0, width=tw, height=y1 - y0)
            f.lift(t)
        # son sayfanin alti: belge bittikten sonra kalan beyaz alan masa rengine boyanir
        info = t.dlineinfo('end-1c')
        if info:
            y = info[1] + info[3] + bottom
            if y < th:
                f, lb = self._strip(k)
                k += 1
                lb.configure(text='')
                f.place(x=tx, y=ty + max(0, y), width=tw, height=th - max(0, y))
                f.lift(t)
        self._hide_strips(k)
