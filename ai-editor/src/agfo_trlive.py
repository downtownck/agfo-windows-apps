# -*- coding: utf-8 -*-
"""AGFO AI Editor 1.4.8 - belge cevirisinde canli vurgu.

Ceviri is parcaciklarindan gelen olaylar ('start' / 'done', parca anahtarlari) ana is parcaciginda islenir:
cevrilen paragraflar sari, cevrilmis olanlar yesil vurgulanir; is bitince vurgular kisa sure sonra kalkar.
Vurgular gecicidir: geri alma kaydina, belgeye ve kaydedilen dosyaya girmez. Kullanici kaydirmadikca ekran,
cevrilmekte olan en ustteki paragrafi izler.
"""
from __future__ import annotations

import tkinter as tk


class TranslationLive:
    def __init__(self, app, text=None, lines=None, view=None, pdf_map=None):
        self.app = app
        self.text, self.lines = text, lines or []
        self.view, self.pdf_map = view, pdf_map or []
        self.working = set()
        self.follow = True
        self._last_view = None
        self.finished = False

    # -- olaylar (ana is parcacigi)
    def event(self, kind, keys):
        if self.finished:
            return
        idxs = sorted({k[0] for k in keys})
        state = 'work' if kind == 'start' else 'done'
        if kind == 'start':
            self.working.update(idxs)
        else:
            self.working.difference_update(idxs)
        try:
            for bi in idxs:
                self._mark(bi, state)
            if kind == 'start' and self.working:
                self._follow(min(self.working))
        except tk.TclError:          # sekme kapatildi
            self.finished = True

    def _mark(self, bi, state):
        if self.text is not None:
            rng = self.lines[bi] if bi < len(self.lines) else None
            if not rng:
                return
            s, e = '%d.0' % rng[0], '%d.end+1c' % rng[1]
            if state == 'work':
                self.text.tag_add('trwork', s, e)
            else:
                self.text.tag_remove('trwork', s, e)
                self.text.tag_add('trdone', s, e)
        elif self.view is not None and bi < len(self.pdf_map) and self.pdf_map[bi]:
            i, n, drect = self.pdf_map[bi]
            self.view.set_tr_mark(i, n, drect, state)

    def _user_scrolled(self, cur):
        if self._last_view is not None and abs(cur - self._last_view) > 1e-4:
            self.follow = False
        return not self.follow

    def _follow(self, bi):
        if not self.follow:
            return
        if self.text is not None:
            if self._user_scrolled(self.text.yview()[0]):
                return
            rng = self.lines[bi] if bi < len(self.lines) else None
            if rng and self.text.dlineinfo('%d.0' % rng[0]) is None:
                self.text.see('%d.0' % rng[0])
            self._last_view = self.text.yview()[0]
        elif self.view is not None and bi < len(self.pdf_map) and self.pdf_map[bi]:
            c = self.view.canvas
            if self._user_scrolled(c.yview()[0]):
                return
            i, _n, drect = self.pdf_map[bi]
            self.view.follow_page(i, drect[1])
            self._last_view = c.yview()[0]

    def finish(self, delay=2500):
        """Vurgular kisa bir sure sonra kalkar (iptal/hata dahil)."""
        if self.finished:
            return
        self.finished = True

        def clear():
            try:
                if self.text is not None:
                    self.text.tag_remove('trwork', '1.0', 'end')
                    self.text.tag_remove('trdone', '1.0', 'end')
                if self.view is not None:
                    self.view.clear_tr_marks()
            except tk.TclError:
                pass
        try:
            if self.text is not None:
                self.text.tag_remove('trwork', '1.0', 'end')
            self.app.after(delay, clear)
        except tk.TclError:
            pass


def text_block_lines(t, blocks):
    """Duz metin belgesinde her blogun satiri (aranarak, yaklasik). Bulunamayan blok icin None."""
    import agfo_richdoc as R
    out, pos = [], '1.0'
    for b in blocks:
        if b.get('t') == 'p':
            probe = R.runs_text(b['runs']).strip()
        elif b.get('t') == 'table':
            probe = next((R.runs_text(c).strip() for row in b['rows'] for c in row if R.runs_text(c).strip()), '')
        else:
            probe = ''
        probe = probe[:30]
        idx = t.search(probe, pos, stopindex='end') if probe else ''
        if idx:
            ln = int(idx.split('.')[0])
            out.append([ln, ln])
            pos = '%d.0' % (ln + 1)
        else:
            out.append(None)
    return out
