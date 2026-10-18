# -*- coding: utf-8 -*-
"""AGFO AI Editor 1.4 - yan yana ceviri gorunumu (ozgun | ceviri).

Iki bicimli metin paneli paragraf paragraf eslenir: biri kaydirilinca digeri ayni paragrafa gelir, bir paragrafa
tiklayinca karsiligi vurgulanir. Ceviri duzenlenebilir sekmede acilabilir ya da iki sutunlu Word tablosu olarak
kaydedilebilir (denetim raporu ekleri ve terminoloji kontrolu icin).
"""
from __future__ import annotations

import bisect
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import agfo_richdoc as R
import agfo_richtext as RT


class CompareView(tk.Frame):
    def __init__(self, app, parent, orig, trans, title, left_label='Özgün', right_label='Çeviri', model=''):
        super().__init__(parent, bg=app.colors['BG'])
        self.app = app
        self.orig, self.trans = orig, trans
        self.title = title
        self.left_label, self.right_label = left_label, right_label
        self.model = model
        self.sync = tk.BooleanVar(value=True)
        self._syncing = False
        c = app.colors
        bar = tk.Frame(self, bg=c['PANEL'], padx=8, pady=5)
        bar.pack(fill='x')
        tk.Label(bar, text='↔ ' + title, fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 10, 'bold')).pack(side='left', padx=(0, 10))
        app.btn(bar, 'Çeviriyi düzenlenebilir sekmede aç', self.open_translation, 'primary', padx=8)
        app.btn(bar, 'İki dilli Word olarak kaydet…', self.save_bilingual, 'ghost', padx=8)
        ttk.Checkbutton(bar, text='Eşzamanlı kaydır', variable=self.sync).pack(side='left', padx=8)
        app.btn(bar, 'Kapat', lambda: app.close_compare(self), 'ghost', side='right', padx=8)
        body = tk.Frame(self, bg=c['BG'])
        body.pack(fill='both', expand=True)
        body.columnconfigure(0, weight=1, uniform='c')
        body.columnconfigure(1, weight=1, uniform='c')
        body.rowconfigure(1, weight=1)
        self.panes = []
        right_head = right_label + ('   ·   çeviren model: ' + model if model else '')
        for col, (label, blocks) in enumerate(((left_label, orig), (right_head, trans))):
            tk.Label(body, text=label, fg=c['MUTED'], bg=c['BG'], font=('Segoe UI', 9, 'bold'), anchor='w').grid(
                row=0, column=col, sticky='we', padx=(4 if col else 0, 0), pady=(4, 2))
            fr = tk.Frame(body, bg=c['EDIT_BG'])
            fr.grid(row=1, column=col, sticky='nsew', padx=(4 if col else 0, 0))
            t = RT.RichText(fr, c, family=app._editor_font()[0], size=max(9, app._editor_font()[1] - 1), wrap='word',
                            relief='flat', bd=0, highlightthickness=0)
            sb = ttk.Scrollbar(fr, orient='vertical', command=t.yview)
            t.configure(yscrollcommand=lambda a, b, s=sb, side=col: (s.set(a, b), self._scrolled(side)))
            sb.pack(side='right', fill='y')
            t.pack(side='left', fill='both', expand=True)
            t.set_page_mode(bool(app.settings.get('page_view', True)))
            t.set_font(zoom=1.0)
            t.configure(padx=int(t.px(26)), pady=int(t.px(20)))
            t.tag_configure('pairhl', background='#fff3bf' if t.page_mode else '#3a3418')
            self._load(t, blocks)
            t.configure(state='disabled', cursor='arrow')
            t.bind('<Button-1>', lambda e, side=col: self._clicked(side, e))
            self.panes.append(t)

    def _load(self, t, blocks):
        t.undo.recording = False
        starts = []
        try:
            for k, b in enumerate(blocks):
                if k:
                    t._call('insert', 'end-1c', '\n')
                line = int(t.index('end-1c').split('.')[0])
                starts.append(line)
                t.insert_blocks('%d.0' % line, [b])
        finally:
            t.undo.recording = True
        t.undo.reset()
        t.pair_lines = starts

    def _pair_at(self, side, index):
        lines = self.panes[side].pair_lines
        ln = int(self.panes[side].index(index).split('.')[0])
        return max(0, bisect.bisect_right(lines, ln) - 1)

    def _scrolled(self, side):
        if not self.sync.get() or self._syncing or len(self.panes) < 2:
            return
        src, dst = self.panes[side], self.panes[1 - side]
        k = self._pair_at(side, '@0,0')
        if k >= len(dst.pair_lines):
            return
        self._syncing = True
        try:
            # kaynaktaki paragrafin ne kadarinin kaydirildigini hedefe de uygula
            top = src.dlineinfo('@0,0')
            dst.yview('%d.0' % dst.pair_lines[k])
            if top:
                info = src.dlineinfo('%d.0' % src.pair_lines[k])
                if info and info[1] < 0:
                    dst.yview_scroll(int(-info[1] / max(1, info[3])), 'units')
        finally:
            self.after_idle(lambda: setattr(self, '_syncing', False))

    def _clicked(self, side, e):
        t = self.panes[side]
        k = self._pair_at(side, '@%d,%d' % (e.x, e.y))
        for s, pane in enumerate(self.panes):
            pane.tag_remove('pairhl', '1.0', 'end')
            if k < len(pane.pair_lines):
                start = pane.pair_lines[k]
                end = pane.pair_lines[k + 1] - 1 if k + 1 < len(pane.pair_lines) else int(pane.index('end-1c').split('.')[0])
                pane.tag_add('pairhl', '%d.0' % start, '%d.end+1c' % end)
                if s != side:
                    pane.see('%d.0' % start)
        _ = t
        return None

    def open_translation(self):
        self.app.new_doc(blocks=self.trans, title='%s (%s)' % (self.title, self.right_label))

    def save_bilingual(self):
        init = '%s - %s.docx' % (self.title, self.right_label)
        p = filedialog.asksaveasfilename(parent=self, title='İki dilli Word belgesi', initialfile=init, defaultextension='.docx',
                                         filetypes=[('Word belgesi', '*.docx')])
        if not p:
            return None
        rows = []
        for a, b in zip(self.orig, self.trans):
            rows.append((self._cell(a), self._cell(b)))
        try:
            data = R.bilingual_docx_bytes(rows, self.left_label, self.right_label + (' (%s)' % self.model if self.model else ''))
            tmp = p + '.agfo-tmp'
            with open(tmp, 'wb') as f:
                f.write(data)
            os.replace(tmp, p)
        except OSError as e:
            messagebox.showerror('Kaydedilemedi', str(e), parent=self)
            return None
        self.app.flash('İki dilli belge kaydedildi: %s' % p, 9000)
        return p

    @staticmethod
    def _cell(b):
        if b['t'] == 'p':
            runs = list(b['runs'])
            if b.get('style') in ('h1', 'h2', 'h3'):
                runs = [dict(r, b=True) for r in runs]
            return runs
        if b['t'] == 'table':
            return [R.run(R.block_text(b).replace('\t', ' | ').replace('\n', ' / '))]
        return [R.run('[resim]', i=True)]
