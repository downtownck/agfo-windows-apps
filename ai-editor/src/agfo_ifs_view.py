# -*- coding: utf-8 -*-
"""AGFO AI Editor - IFS auditXpress (.ifs) rapor sekmesi.

Sol menu: rapor alanlari (bolumler), Kontrol listesi, Denetim ekibi, Ozet. Kontrol listesinde her madde icin puan,
English explanation, Explanation, Note ve maddenin ic alanlari (metin, evet/hayir, kod listesi, tekrarli satirlar).
auditXpress'in kendi kayitlarina bagli secimler (CCP secici, kapsamlar) gosterilir ama degistirilmez.
Kayit: dosya bire bir ayni bicimde yazilir; hash ayara gore korunur ya da bosaltilir; onceki hali yedeklenir.
"""
from __future__ import annotations

import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import agfo_ifs as I
from agfo_brcgs_view import Scroll, _colors

HASH_MODES = [('keep', 'Hash: koru'), ('clear', 'Hash: boşalt')]
LONG_HINTS = ('Description', 'Summary', 'Information', 'Text', 'Details', 'Reason', 'Explanation', 'Address', 'Running',
              'Claims', 'Methodology', 'Analysis', 'Parameters', 'Measures', 'Info')
EN_INSTRUCTION = ('Translate the auditor\'s text into clear, factual English for an official IFS audit report (auditXpress). '
                  'Keep every fact, number, document code, version and date exactly; objective audit language; no additions.')
EXPL_INSTRUCTION = (
    'Write the English explanation of IFS requirement "{title}" for an official IFS {std} audit report in auditXpress. '
    'The requirement text, if given, is context only: do not copy or paraphrase it, and do not claim compliance it does not show. '
    'Use only the auditor\'s evidence below (often Turkish or notes): describe what was verified and how (documents, records, '
    'observation, interviews), with document titles, codes, versions and dates exactly as given (dates DD/MM/YYYY). '
    'Objective, factual, third person ("the company"), complete sentences, no headings, no bullet list unless the evidence is a list. '
    '{score_rule} Do not invent evidence, records, numbers or conclusions; if something is missing, do not fill it in.')
SCORE_RULES = {
    'A': 'The requirement is scored A: state how it is fulfilled.',
    'B': 'The requirement is scored B (almost full compliance): describe what was found and the small deviation precisely.',
    'C': 'The requirement is scored C (part of the requirement is not implemented): describe the deviation precisely.',
    'D': 'The requirement is scored D (not implemented): describe the deviation precisely, starting with "Deviation:".',
    'NA': 'The requirement is scored N/A: give the reason why it is not applicable.',
}


class IfsReportView(tk.Frame):
    def __init__(self, app, master, report):
        self.app = app
        self.c = _colors(app)
        super().__init__(master, bg=self.c['PANEL'])
        self.report = report
        self.dirty = False
        self.page = None
        self.current_uid = None
        self.filter_var = tk.StringVar(value='Tümü')
        self.search_var = tk.StringVar()
        self.hash_var = tk.StringVar(value=dict(HASH_MODES).get(app.settings.get('ifs_hash_mode', 'keep'), HASH_MODES[0][1]))
        self._build()
        self.show('checklist')

    # ------------------------------------------------------------------ cerceve
    def tab_text(self):
        return ('● ' if self.dirty else '') + '🧾 ' + (self.report.company() or os.path.basename(self.report.path or 'IFS'))[:34]

    def mark_dirty(self, on=True):
        if self.dirty != on:
            self.dirty = on
            try:
                self.app.nb.tab(self, text=self.tab_text())
            except tk.TclError:
                pass
        self._sync_status()

    def _sync_status(self):
        cnt = self.report.counts()
        filled = sum(v for k, v in cnt.items() if k)
        txt = '%s · %d / %d madde puanlı · D: %d · %s' % (
            os.path.basename(self.report.path or ''), filled, filled + cnt[''], cnt['D'], 'kaydedilmedi' if self.dirty else 'kaydedildi')
        try:
            self.status.configure(text=txt, fg=self.c.get('WARN', '#e2b356') if self.dirty else self.c['MUTED'])
        except (tk.TclError, AttributeError):
            pass

    def _build(self):
        c = self.c
        top = tk.Frame(self, bg=c['PANEL'], padx=12, pady=8)
        top.pack(fill='x')
        tk.Label(top, text=self.report.title(), fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 13, 'bold')).pack(side='left')
        self.status = tk.Label(top, text='', fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 9))
        self.status.pack(side='left', padx=12)
        self.app.btn(top, 'Kaydet', self.save, 'primary', side='right')
        self.app.btn(top, 'Farklı kaydet…', self.save_as, 'ghost', side='right')
        hb = ttk.Combobox(top, textvariable=self.hash_var, values=[m[1] for m in HASH_MODES], state='readonly', width=13)
        hb.pack(side='right', padx=6)
        hb.bind('<<ComboboxSelected>>', lambda e: self._save_hash_mode())
        body = tk.Frame(self, bg=c['PANEL'])
        body.pack(fill='both', expand=True)
        self.nav = tk.Frame(body, bg=c['PANEL2'], width=210)
        self.nav.pack(side='left', fill='y')
        self.nav.pack_propagate(False)
        self.nav_btns = {}
        items = [(g, t) for g, t, _k in I.GROUPS] + [('checklist', 'Kontrol listesi'), ('team', 'Denetim ekibi'), ('overview', 'Özet')]
        for key, label in items:
            b = tk.Button(self.nav, text=label, anchor='w', command=lambda k=key: self.show(k), bg=c['PANEL2'], fg=c['FG'],
                          relief='flat', bd=0, padx=12, pady=6, font=('Segoe UI', 10), activebackground=c['SEL_BG'],
                          cursor='hand2')
            b.pack(fill='x')
            self.nav_btns[key] = b
        self.main = tk.Frame(body, bg=c['PANEL'])
        self.main.pack(side='left', fill='both', expand=True)
        self._sync_status()

    def _save_hash_mode(self):
        mode = next((k for k, lab in HASH_MODES if lab == self.hash_var.get()), 'keep')
        self.app.settings['ifs_hash_mode'] = mode
        try:
            import agfo_editor_core as core
            core.save_settings(self.app.settings)
        except Exception:
            pass

    def hash_mode(self):
        return next((k for k, lab in HASH_MODES if lab == self.hash_var.get()), 'keep')

    def show(self, page):
        self.page = page
        for k, b in self.nav_btns.items():
            b.configure(bg=self.c['SEL_BG'] if k == page else self.c['PANEL2'])
        for w in self.main.winfo_children():
            w.destroy()
        if page == 'checklist':
            self._page_checklist()
        elif page == 'team':
            self._page_team()
        elif page == 'overview':
            self._page_overview()
        else:
            self._page_fields(page)

    # ------------------------------------------------------------------ alan cizimi (rapor alanlari ve ic alanlar ortak)
    def _label(self, parent, text, muted=False, bold=False):
        return tk.Label(parent, text=text, fg=self.c['MUTED'] if muted else self.c['FG'], bg=parent.cget('bg'), anchor='w',
                        justify='left', font=('Segoe UI', 9, 'bold') if bold else ('Segoe UI', 9), wraplength=620)

    def _text(self, parent, value, rows=3, on_change=None):
        c = self.c
        t = tk.Text(parent, height=rows, wrap='word', bg=c['EDIT_BG'], fg=c['FG'], insertbackground=c['ACCENT'], relief='flat',
                    bd=0, highlightthickness=1, highlightbackground=c['LINE'], highlightcolor=c['ACCENT'],
                    font=('Segoe UI', 10), padx=6, pady=4, undo=True)
        t.insert('1.0', value or '')
        t.edit_modified(False)
        if on_change:
            def changed(_e=None, tt=t):
                if tt.edit_modified():
                    tt.edit_modified(False)
                    on_change(tt.get('1.0', 'end-1c'))
            t.bind('<<Modified>>', changed)
        return t

    def render_field(self, parent, key, holder, on_change=None, pair_lookup=None):
        """holder: {'answer': ...}. Turune gore kutu; degisiklik holder'a yazilir."""
        c = self.c
        value = holder.get('answer')
        kind = I.field_kind(key, value)
        row = tk.Frame(parent, bg=parent.cget('bg'))
        row.pack(fill='x', pady=(6, 0))
        head = tk.Frame(row, bg=row.cget('bg'))
        head.pack(fill='x')
        self._label(head, I.label_of(key), bold=True).pack(side='left')
        changed = on_change or (lambda: self.mark_dirty())

        def put(v):
            holder['answer'] = v
            changed()
        if kind == 'str':
            long = I.is_en(key) or any(h in key for h in LONG_HINTS) or len(str(value or '')) > 60 or '\n' in str(value or '')
            if long:
                t = self._text(row, value, rows=3 if len(str(value or '')) < 300 else 6, on_change=put)
                t.pack(fill='x')
                widget = t
            else:
                var = tk.StringVar(value=value or '')
                e = ttk.Entry(row, textvariable=var)
                e.pack(fill='x')
                var.trace_add('write', lambda *_a, vv=var: put(vv.get()))
                widget = e
            if I.is_en(key) and pair_lookup is not None:
                src = pair_lookup(I.pair_of(key))
                if src is not None:
                    self.app.btn(head, '✨ EN', lambda w=widget, s=src: self.ai_translate_into(w, s, put), 'ghost', side='right')
            return widget
        if kind == 'yesno':
            var = tk.StringVar(value=value or '')
            cb = ttk.Combobox(row, textvariable=var, values=list(I.YES_NO), state='readonly', width=10)
            cb.pack(anchor='w')
            cb.bind('<<ComboboxSelected>>', lambda e, vv=var: put(vv.get()))
            return cb
        if kind == 'codes':
            var = tk.StringVar(value=', '.join(value or []))
            e = ttk.Entry(row, textvariable=var)
            e.pack(fill='x')
            var.trace_add('write', lambda *_a, vv=var: put([x.strip() for x in vv.get().split(',') if x.strip()]))
            self._label(row, 'Kodlar, virgülle ayrılır (auditXpress kodları, ör. "en, ar").', muted=True).pack(fill='x')
            return e
        if kind == 'group':
            self._render_group(row, key, holder, changed, pair_lookup)
            return None
        n = len(value) if isinstance(value, list) else (1 if value else 0)
        self._label(row, '%s — auditXpress\'te seçilir; editör korur, değiştirmez.' %
                    ('%d seçim' % n if n else 'seçim yok'), muted=True).pack(fill='x')
        return None

    def _render_group(self, row, key, holder, changed, pair_lookup):
        c = self.c
        items = holder.get('answer')
        if not isinstance(items, list):
            return
        box = tk.Frame(row, bg=c['PANEL'], highlightthickness=1, highlightbackground=c['LINE'], padx=8, pady=4)
        box.pack(fill='x', pady=(2, 0))

        def redraw():
            for w in box.winfo_children():
                w.destroy()
            for i, it in enumerate(items):
                card = tk.Frame(box, bg=c['PANEL2'], padx=8, pady=4)
                card.pack(fill='x', pady=3)
                bar = tk.Frame(card, bg=c['PANEL2'])
                bar.pack(fill='x')
                self._label(bar, '%d.' % (i + 1), bold=True).pack(side='left')
                self.app.btn(bar, '×', lambda k=i: remove(k), 'ghost', side='right')
                qs = dict(it.get('rootQuestions') or {})
                qs.update(it.get('subQuestions') or {})

                def lookup(k, q=qs):
                    h = q.get(k)
                    return h if isinstance(h, dict) else None
                for k, h in qs.items():
                    if isinstance(h, dict):
                        self.render_field(card, k, h, changed, lookup)
            self.app.btn(box, '+ Satır ekle', add, 'ghost', side=None).pack(anchor='w', pady=(4, 2))

        def add():
            tpl = I.group_template(key, items)
            if tpl is None:
                messagebox.showinfo('IFS', 'Bu listenin yapısı bilinmiyor; satırı auditXpress\'te ekleyin.', parent=self)
                return
            items.append(I.new_group_item(tpl))
            changed()
            redraw()

        def remove(k):
            if not self.app.smoke and not messagebox.askyesno('Satırı sil', '%d. satır silinsin mi?' % (k + 1), parent=self):
                return
            del items[k]
            changed()
            redraw()
        redraw()

    # ------------------------------------------------------------------ rapor alanlari
    def _page_fields(self, gid):
        c = self.c
        title = next((t for g, t, _k in I.GROUPS if g == gid), gid)
        head = tk.Frame(self.main, bg=c['PANEL'], padx=14, pady=8)
        head.pack(fill='x')
        tk.Label(head, text=title, fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.app.btn(head, '✨ Boş EN alanlarını doldur', lambda: self.ai_fill_en(gid), 'ghost', side='right')
        sc = Scroll(self.main, c['PANEL'])
        sc.pack(fill='both', expand=True, padx=14)
        q = self.report.questions
        for key in self.report.question_keys(gid):
            self.render_field(sc.body, key, q[key], pair_lookup=lambda k: q.get(k))
        tk.Frame(sc.body, bg=c['PANEL'], height=20).pack()

    # ------------------------------------------------------------------ kontrol listesi
    FILTERS = ['Tümü', 'Puansız', 'A', 'B', 'C', 'D', 'NA', 'Açıklaması eksik', 'İç alanlı']

    def _visible_requirements(self):
        f, s = self.filter_var.get(), self.search_var.get().strip().lower()
        out = []
        for r in self.report.requirements():
            sid = r.score_id
            if f == 'Puansız' and sid:
                continue
            if f in ('A', 'B', 'C', 'D', 'NA') and sid != f:
                continue
            if f == 'Açıklaması eksik' and not (r.needs_explanation() or (sid and not r.answers.get('englishExplanationText'))):
                continue
            if f == 'İç alanlı' and not r.fields:
                continue
            if s:
                hay = ' '.join([r.title(), r.answers.get('englishExplanationText') or '', r.answers.get('explanationText') or '',
                                r.answers.get('note') or '']).lower()
                if s not in hay:
                    continue
            out.append(r)
        return out

    def _page_checklist(self):
        c = self.c
        split = ttk.PanedWindow(self.main, orient='horizontal')
        split.pack(fill='both', expand=True)
        left = tk.Frame(split, bg=c['PANEL'], padx=8, pady=8)
        split.add(left, weight=2)
        bar = tk.Frame(left, bg=c['PANEL'])
        bar.pack(fill='x')
        cb = ttk.Combobox(bar, textvariable=self.filter_var, values=self.FILTERS, state='readonly', width=16)
        cb.pack(side='left')
        cb.bind('<<ComboboxSelected>>', lambda e: self._fill_tree())
        e = ttk.Entry(bar, textvariable=self.search_var)
        e.pack(side='left', fill='x', expand=True, padx=(6, 0))
        e.bind('<KeyRelease>', lambda ev: self._fill_tree())
        if not self.report.dictionary:
            self._label(left, 'Bu standart için madde numarası sözlüğü yok; maddeler dosyadaki sırayla gösterilir.',
                        muted=True).pack(fill='x', pady=(6, 0))
        elif not any(e.get('text') for e in self.report.dictionary.values()):
            tip = tk.Frame(left, bg=c['PANEL'])
            tip.pack(fill='x', pady=(6, 0))
            self._label(tip, 'Madde metinleri yok (IFS metni pakete konmaz). Kontrol listesini bir kez içe aktarın; '
                        'yalnız bu bilgisayarda saklanır.', muted=True).pack(side='left', fill='x', expand=True)
            self.app.btn(tip, 'Madde metinlerini içe aktar…', self.import_texts, 'ghost', side='right')
        self.tree = ttk.Treeview(left, columns=('score', 'en'), show='tree headings', selectmode='browse')
        self.tree.heading('#0', text='Madde')
        self.tree.heading('score', text='Puan')
        self.tree.heading('en', text='EN')
        self.tree.column('score', width=50, anchor='center', stretch=False)
        self.tree.column('en', width=36, anchor='center', stretch=False)
        self.tree.pack(fill='both', expand=True, pady=(6, 0))
        self.tree.bind('<<TreeviewSelect>>', lambda e: self._tree_pick())
        self.editor = tk.Frame(split, bg=c['PANEL'])
        split.add(self.editor, weight=3)

        def sash(tries=[0]):
            w = split.winfo_width()
            if w < 50 and tries[0] < 20:
                tries[0] += 1
                split.after(30, sash)
                return
            try:
                split.sashpos(0, int(w * 0.36))
            except tk.TclError:
                pass
        split.after_idle(sash)
        self._fill_tree()
        first = self.current_uid or (self.tree.get_children() or [None])[0]
        if first and self.tree.exists(first):
            self.tree.selection_set(first)
            self.tree.see(first)
        self._edit_requirement(first)

    def _fill_tree(self):
        if not hasattr(self, 'tree'):
            return
        try:
            self.tree.delete(*self.tree.get_children())
        except tk.TclError:
            return
        for r in self._visible_requirements():
            en = '✓' if (r.answers.get('englishExplanationText') or '').strip() else ('!' if r.needs_explanation() else '')
            self.tree.insert('', 'end', iid=r.uuid, text=r.title(), values=(r.score_id or '–', en))

    def _tree_pick(self):
        sel = self.tree.selection()
        if sel and sel[0] != self.current_uid:
            self._edit_requirement(sel[0])

    def _refresh_row(self, uid):
        r = self.report.requirement(uid)
        if r is None or not hasattr(self, 'tree') or not self.tree.exists(uid):
            return
        en = '✓' if (r.answers.get('englishExplanationText') or '').strip() else ('!' if r.needs_explanation() else '')
        self.tree.item(uid, values=(r.score_id or '–', en))

    def _edit_requirement(self, uid):
        c = self.c
        for w in self.editor.winfo_children():
            w.destroy()
        self.current_uid = uid
        self.expl_boxes = {}
        r = self.report.requirement(uid) if uid else None
        if r is None:
            self._label(self.editor, 'Madde seçin.', muted=True).pack(padx=14, pady=14)
            return
        nav = tk.Frame(self.editor, bg=c['PANEL'], padx=12, pady=6)
        nav.pack(fill='x', side='bottom')
        self.app.btn(nav, '← Önceki', lambda: self.step(-1), 'ghost')
        self.app.btn(nav, 'Sonraki →', lambda: self.step(1), 'ghost', side='right')
        sc = Scroll(self.editor, c['PANEL'])
        sc.pack(fill='both', expand=True, padx=12, pady=(8, 0))
        b = sc.body
        tk.Label(b, text=r.title(), fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 12, 'bold'), anchor='w', justify='left',
                 wraplength=640).pack(fill='x')
        e = r.entry()
        if e.get('section'):
            self._label(b, e['section'], muted=True).pack(fill='x')
        if e.get('text'):
            req = tk.Frame(b, bg=c['PANEL2'], padx=10, pady=8)
            req.pack(fill='x', pady=(6, 0))
            tk.Label(req, text='Requirement' + ('  ·  KO' if e.get('ko') else ''), fg=c['ACCENT'], bg=c['PANEL2'],
                     font=('Segoe UI', 9, 'bold'), anchor='w').pack(fill='x')
            tk.Label(req, text=e['text'], fg=c['FG'], bg=c['PANEL2'], font=('Segoe UI', 9), anchor='w', justify='left',
                     wraplength=640).pack(fill='x')
        self._label(b, 'Kimlik %s · sıra %d' % (r.uuid, r.index + 1), muted=True).pack(fill='x', pady=(4, 0))
        srow = tk.Frame(b, bg=c['PANEL'])
        srow.pack(fill='x', pady=(8, 0))
        self._label(srow, 'Puan', bold=True).pack(side='left')
        sv = tk.StringVar(value=r.score_id)
        scb = ttk.Combobox(srow, textvariable=sv, values=[''] + [s for s, _v in I.SCORES], state='readonly', width=6)
        scb.pack(side='left', padx=8)
        scb.bind('<<ComboboxSelected>>', lambda e: self.set_score(uid, sv.get()))
        self.score_note = self._label(srow, self._score_note(r), muted=True)
        self.score_note.pack(side='left', padx=6)
        lang = self.report.report_language()
        for field, label in (('englishExplanationText', 'English explanation'),
                             ('explanationText', 'Explanation (rapor dili: %s) — kanıtınızı buraya da yazabilirsiniz' % (lang or '?')),
                             ('note', 'Note (iç not)')):
            h = tk.Frame(b, bg=c['PANEL'])
            h.pack(fill='x', pady=(10, 0))
            self._label(h, label, bold=True).pack(side='left')
            if field == 'englishExplanationText':
                self.app.btn(h, '✨ AI: İngilizce açıklamayı yaz', lambda: self.ai_explanation(uid), 'primary', side='right')
            t = self._text(b, r.answers.get(field) or '', rows=6 if field == 'englishExplanationText' else 4,
                           on_change=lambda v, f=field: self._set_text(uid, f, v))
            t.pack(fill='x')
            self.expl_boxes[field] = t
        if r.fields:
            tk.Label(b, text='Maddenin iç alanları', fg=c['ACCENT'], bg=c['PANEL'], font=('Segoe UI', 10, 'bold'),
                     anchor='w').pack(fill='x', pady=(14, 0))
            fields = r.fields

            def lookup(k):
                h = fields.get(k)
                return h if isinstance(h, dict) else None
            for k, h in fields.items():
                if isinstance(h, dict):
                    self.render_field(b, k, h, on_change=lambda: (self.mark_dirty(), self._refresh_row(uid)), pair_lookup=lookup)
        tk.Frame(b, bg=c['PANEL'], height=20).pack()

    def _score_note(self, r):
        if r.is_ko and r.score_id == 'D':
            return '⚠ KO maddesinde D: denetim başarısız sayılır.'
        if r.score_id in I.CORRECTION_SCORES:
            return 'Düzeltme gerekir (auditXpress\'te düzeltici faaliyet açılır).'
        if r.score_id == 'NA':
            return 'N/A: gerekçe English explanation\'da yazılmalı.'
        return ''

    def _set_text(self, uid, field, value):
        self.report.set_text(uid, field, value)
        self.mark_dirty()
        self._refresh_row(uid)

    def set_score(self, uid, sid):
        self.report.set_score(uid, sid)
        self.mark_dirty()
        self._refresh_row(uid)
        r = self.report.requirement(uid)
        try:
            self.score_note.configure(text=self._score_note(r))
        except (tk.TclError, AttributeError):
            pass

    def step(self, d):
        kids = list(self.tree.get_children())
        if not kids:
            return
        i = kids.index(self.current_uid) if self.current_uid in kids else -1
        j = max(0, min(len(kids) - 1, i + d))
        self.tree.selection_set(kids[j])
        self.tree.see(kids[j])

    def select_requirement(self, uid):
        if self.page != 'checklist':
            self.show('checklist')
        if not self.tree.exists(uid):
            self.filter_var.set('Tümü')
            self.search_var.set('')
            self._fill_tree()
        self.tree.selection_set(uid)
        self.tree.see(uid)
        self._edit_requirement(uid)

    # ------------------------------------------------------------------ ekip ve ozet (salt okunur)
    def _page_team(self):
        c = self.c
        sc = Scroll(self.main, c['PANEL'])
        sc.pack(fill='both', expand=True, padx=14, pady=8)
        b = sc.body
        tk.Label(b, text='Denetim ekibi ve süre', fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 12, 'bold'), anchor='w').pack(fill='x')
        at = self.report.module.get('auditTimes') or {}
        self._label(b, 'Başlangıç %s · bitiş %s · toplam %s dk (auditXpress hesaplar)' % (
            at.get('startDate') or '–', at.get('endDate') or '–', at.get('auditTimeInMinutes') or 0)).pack(fill='x', pady=(4, 8))
        for a in (self.report.module.get('auditors') or {}).values():
            ad = a.get('auditorData') or {}
            logs = list((a.get('timeLog') or {}).values())
            self._label(b, '%s %s — %s' % (ad.get('firstName', ''), ad.get('lastName', ''), ad.get('role', '')), bold=True).pack(fill='x')
            for lg in logs:
                self._label(b, '   %s  %s–%s %s' % (lg.get('date', ''), lg.get('from', ''), lg.get('to', ''), lg.get('comment', '')),
                            muted=True).pack(fill='x')
        self._label(b, 'Ekip, zaman kaydı ve kapsamlar auditXpress\'teki kayıtlara bağlıdır; burada gösterilir, değiştirilmez.',
                    muted=True).pack(fill='x', pady=(10, 0))

    def _page_overview(self):
        c = self.c
        sc = Scroll(self.main, c['PANEL'])
        sc.pack(fill='both', expand=True, padx=14, pady=8)
        b = sc.body
        tk.Label(b, text='Özet', fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 12, 'bold'), anchor='w').pack(fill='x')
        cnt = self.report.counts()
        self._label(b, '   '.join('%s: %d' % (k or 'Puansız', cnt[k]) for k in ('A', 'B', 'C', 'D', 'NA', ''))).pack(fill='x', pady=4)
        res = (self.report.module.get('result') or {}).get('overall') or {}
        if res:
            self._label(b, 'auditXpress son hesabı: %s %% · %s (editör puanları değiştirince auditXpress yeniden hesaplar)' % (
                res.get('percent', ''), res.get('level') or res.get('id') or ''), muted=True).pack(fill='x')
        todo = [r for r in self.report.requirements() if r.needs_explanation()]
        self._label(b, 'Açıklaması eksik (B / C / D / NA): %d' % len(todo), bold=True).pack(fill='x', pady=(12, 2))
        for r in todo[:60]:
            self.app.btn(b, '→ %s (%s)' % (r.title()[:70], r.score_id), lambda u=r.uuid: self.select_requirement(u), 'ghost',
                         side=None).pack(anchor='w')
        self._label(b, 'Hash: %s. auditXpress dosyanın değiştirildiğini hash ile anlıyorsa, son kaydı auditXpress\'te yapın.' % (
            'özgün hash korunuyor' if self.hash_mode() == 'keep' else 'hash alanları boşaltılıyor'), muted=True).pack(fill='x', pady=(14, 0))

    # ------------------------------------------------------------------ AI
    def ai_explanation(self, uid):
        r = self.report.requirement(uid)
        if r is None:
            return
        a = r.answers
        parts = []
        req_text = r.entry().get('text')
        if req_text:
            parts.append('IFS requirement %s (for context only; do not repeat it):\n%s' % (r.number(), req_text))
        if (a.get('explanationText') or '').strip():
            parts.append('Explanation / evidence (auditor):\n' + a['explanationText'].strip())
        if (a.get('note') or '').strip():
            parts.append('Auditor note:\n' + a['note'].strip())
        inner = []
        for k, h in r.fields.items():
            v = h.get('answer') if isinstance(h, dict) else None
            txt = _flat(v)
            if txt:
                inner.append('- %s: %s' % (I.label_of(k), txt))
        if inner:
            parts.append('Answers in the requirement\'s fields:\n' + '\n'.join(inner))
        if (a.get('englishExplanationText') or '').strip():
            parts.append('Current English explanation (improve it, keep its facts):\n' + a['englishExplanationText'].strip())
        if len(parts) == (1 if req_text else 0):          # madde metni kanit degildir
            messagebox.showinfo('IFS', 'Önce Explanation ya da Note kutusuna kanıtı (Türkçe olabilir) yazın.', parent=self)
            return
        instr = EXPL_INSTRUCTION.format(title=r.title(), std=self.report.standard_name(),
                                        score_rule=SCORE_RULES.get(r.score_id, 'The requirement has no score yet: describe the evidence only.'))

        def put(text, model):
            if self.report.requirement(uid) is None:
                return
            self.report.set_text(uid, 'englishExplanationText', text)
            self.mark_dirty()
            self._refresh_row(uid)
            box = getattr(self, 'expl_boxes', {}).get('englishExplanationText') if self.current_uid == uid else None
            if box is not None and box.winfo_exists():
                box.delete('1.0', 'end')
                box.insert('1.0', text)
                box.edit_modified(False)
            self.app.flash('İngilizce açıklama yazıldı · %s' % model)
        self.app.brcgs_ai_call('IFS: English explanation', instr, '\n\n'.join(parts), put)

    def ai_translate_into(self, widget, src_holder, put):
        src = _flat(src_holder.get('answer'))
        if not src:
            messagebox.showinfo('IFS', 'Çevrilecek (yerel dildeki) alan boş.', parent=self)
            return

        def done(text, model):
            put(text)
            try:
                if isinstance(widget, tk.Text):
                    widget.delete('1.0', 'end')
                    widget.insert('1.0', text)
                    widget.edit_modified(False)
                elif widget is not None:
                    widget.delete(0, 'end')
                    widget.insert(0, text)
            except tk.TclError:
                pass
        self.app.brcgs_ai_call('IFS: İngilizce', EN_INSTRUCTION, src, done)

    def ai_fill_en(self, gid):
        """Bolumdeki bos _en alanlarini yerel dildeki eslerinden sirayla cevirir."""
        q = self.report.questions
        todo = [k for k in self.report.question_keys(gid)
                if I.is_en(k) and not _flat(q[k].get('answer')) and _flat((q.get(I.pair_of(k)) or {}).get('answer'))]
        if not todo:
            self.app.flash('Bu bölümde doldurulacak boş EN alanı yok (yerel dildeki eşi dolu olanlar çevrilir).')
            return

        def nxt():
            if not todo:
                if self.page == gid:
                    self.show(gid)
                self.app.flash('EN alanları dolduruldu.')
                return
            k = todo.pop(0)

            def done(text, model, key=k):
                q[key]['answer'] = text
                self.mark_dirty()
                nxt()
            self.app.brcgs_ai_call('IFS: %s' % I.label_of(k), EN_INSTRUCTION, _flat(q[I.pair_of(k)]['answer']), done)
        nxt()

    def import_texts(self):
        p = filedialog.askopenfilename(parent=self, title='IFS kontrol listesi (madde no + metin, sekmeyle ayrılmış)',
                                       filetypes=[('Metin', '*.txt *.tsv *.csv'), ('Tümü', '*.*')])
        if not p:
            return False
        try:
            n = I.import_requirement_texts(self.report, p)
        except I.IfsError as e:
            messagebox.showerror('Madde metinleri', str(e), parent=self)
            return False
        self.app.flash('%d madde metni içe aktarıldı (yalnız bu bilgisayarda saklanır).' % n, 7000)
        self.show('checklist')
        return True

    # ------------------------------------------------------------------ kayit
    def save(self):
        if not self.report.path:
            return self.save_as()
        return self._write(self.report.path)

    def save_as(self):
        init = self.report.path or 'rapor.ifs'
        p = filedialog.asksaveasfilename(parent=self, title='IFS dosyasını kaydet', defaultextension='.ifs',
                                         initialdir=os.path.dirname(init) or None, initialfile=os.path.basename(init),
                                         filetypes=[('auditXpress', '*.ifs')])
        return self._write(p) if p else False

    def _write(self, path):
        try:
            import agfo_editor_core as core
            backups = str(core.data_dir() / 'ifs-backups')
        except Exception:
            backups = None
        try:
            self.report.save(path, hash_mode=self.hash_mode(), backup_dir=backups)
        except OSError as e:
            messagebox.showerror('Kaydedilemedi', '%s\n\n%s' % (path, e), parent=self)
            return False
        self.mark_dirty(False)
        self.app.flash('Kaydedildi: %s · %s. Önceki hali yedeklendi.' % (
            path, 'özgün hash korundu' if self.hash_mode() == 'keep' else 'hash alanları boşaltıldı'), 8000)
        return True


def _flat(v):
    """Alan degerini duz metne cevirir (tekrarli satirlar dahil) - AI kaynagi ve bosluk kontrolu icin."""
    if v is None:
        return ''
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, list):
        out = []
        for x in v:
            if isinstance(x, dict) and ('rootQuestions' in x or 'subQuestions' in x):
                qs = dict(x.get('rootQuestions') or {})
                qs.update(x.get('subQuestions') or {})
                vals = [_flat((h or {}).get('answer')) for h in qs.values() if isinstance(h, dict)]
                vals = [s for s in vals if s]
                if vals:
                    out.append('; '.join(vals))
            elif isinstance(x, str):
                out.append(x)
        return '\n'.join('• ' + s for s in out) if len(out) > 1 else (out[0] if out else '')
    return str(v)
