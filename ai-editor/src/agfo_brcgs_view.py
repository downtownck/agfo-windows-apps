# -*- coding: utf-8 -*-
"""AGFO AI Editor - BRCGS rapor calisma alani (AGFO BRCGS Report Studio 5.2.1 arayuzunun masaustu karsiligi).

  BrcgsExplorer   rapor gezgini: standart / firma agaci, arama, siralama, cop kutusu, yeni rapor, DOCX ice aktar
  BrcgsReportView acilan raporun kendi dunyasi: Rapor bilgisi, sablon alan gruplari (Audit Summary, Audit Results ...
                  resmi sablondan turetilir), Resmi tablolar, Rapor bolumleri (kilavuz kutulari + lamba rozeti + kanit
                  notu + bulgular), NA maddeleri, NC Action Plan, Onizleme, Surum gecmisi, Excel ile calisma, DOCX'e yaz.
Rapor bu bilgisayarda agfo_brcgs.store ile saklanir; DOCX her zaman resmi sablonun uzerine yazilir (agfo_brcgs.docx_engine).
"""
from __future__ import annotations

import copy
import os
import re
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from agfo_brcgs import boxes as B
from agfo_brcgs import data as D
from agfo_brcgs import docx_engine as E
from agfo_brcgs import guide as G
from agfo_brcgs import store as S

try:
    from agfo_brcgs import coverage as COV
except Exception:  # pragma: no cover
    COV = None

NAV_FIXED_HEAD = (('overview', 'ℹ  Rapor bilgisi'),)
NAV_FIXED_TAIL = (('tables', '▦  Resmi tablolar'), ('sections', '☰  Rapor bölümleri'), ('na', '⊘  NA maddeleri'),
                  ('plan', '⚑  NC Action Plan'), ('preview', '👁  Önizleme'), ('history', '⟲  Sürüm geçmişi'))
PLAN_FIELDS = (('clause', 'Madde', 1), ('nc_text', 'Uygunsuzluk detayı', 2), ('correction', 'Düzeltme (correction)', 2),
               ('root_cause', 'Kök neden analizi', 2), ('proposed_preventive_action', 'Önerilen önleyici faaliyet planı', 2),
               ('date_reviewed', 'Gözden geçirme tarihi', 1), ('reviewed_by', 'Gözden geçiren', 1))
IDENTITY_KEYS = {'OWNERCOMPANY', 'COMPANY_NAME', 'SITE_NAME', 'CERTIFIED_SITE_NAME', 'SITE_NAMEAB', 'BRC_SITE_CODE', 'SITE_CODE'}
PLAN_TYPES = ('critical', 'major', 'minor', 'fundamental')
PLAN_TYPE_LABELS = {'critical': 'Critical', 'major': 'Major', 'minor': 'Minor', 'fundamental': 'Fundamental'}


def _colors(app):
    c = dict(app.colors)
    c.setdefault('LINE', '#2d4a6c')
    c.setdefault('SEL_FG', '#ffffff')
    return c


class Scroll(tk.Frame):
    """Dikey kaydirilabilir icerik alani (fare tekerlegiyle)."""

    def __init__(self, master, bg, width=None):
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, **({'width': width} if width else {}))
        self.vs = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vs.set)
        self.vs.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.body = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window(0, 0, window=self.body, anchor='nw')
        self.body.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        for w_ in (self.canvas, self.body):
            w_.bind('<Enter>', lambda e: self._wheel(True))
            w_.bind('<Leave>', lambda e: self._wheel(False))

    def _wheel(self, on):
        if on:
            self.bind_all('<MouseWheel>', self._on_wheel)
            self.bind_all('<Button-4>', lambda e: self.canvas.yview_scroll(-3, 'units'))
            self.bind_all('<Button-5>', lambda e: self.canvas.yview_scroll(3, 'units'))
        else:
            for seq in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                self.unbind_all(seq)

    def _on_wheel(self, e):
        if isinstance(e.widget, tk.Text) and e.widget.winfo_height() < e.widget.winfo_reqheight() + 4:
            return
        self.canvas.yview_scroll(int(-e.delta / 120) * 3 or (-1 if e.delta > 0 else 1), 'units')

    def top(self):
        self.canvas.yview_moveto(0)


# ============================================================================= gezgin
class BrcgsExplorer(tk.Frame):
    COLS = (('title', 'Rapor adı', 340), ('profile', 'Standart', 200), ('company', 'Firma', 220), ('site_code', 'Site kodu', 90),
            ('filled', 'Bölüm', 80), ('size', 'Boyut', 70), ('updated_at', 'Güncellendi', 130))

    def __init__(self, app, master, store=None):
        self.app = app
        self.c = _colors(app)
        super().__init__(master, bg=self.c['PANEL'])
        self.store = store or S.Store()
        self.filter = ('all', None)
        self.sort = ('updated_at', True)
        self._build()
        self.refresh()

    def _build(self):
        c = self.c
        top = tk.Frame(self, bg=c['PANEL'], padx=12, pady=8)
        top.pack(fill='x')
        self.q = tk.StringVar()
        e = ttk.Entry(top, textvariable=self.q, width=26)
        e.pack(side='right')
        e.bind('<KeyRelease>', lambda ev: self.refresh())
        tk.Label(top, text='🔍', fg=c['MUTED'], bg=c['PANEL']).pack(side='right', padx=(10, 2))
        self.app.btn(top, '⤓ DOCX içe aktar', self.import_docx, 'ghost', side='right')
        self.new_btn = self.app.btn(top, '＋ Yeni rapor ▾', self.new_menu, 'primary', side='right')
        tk.Label(top, text='📋  BRCGS Report Studio', fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 13, 'bold')).pack(side='left')
        tk.Label(top, text='  FS · PM · CP · AB · SD', fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 9)).pack(side='left')
        body = ttk.PanedWindow(self, orient='horizontal')
        body.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        side = tk.Frame(body, bg=c['PANEL'])
        self.tree_side = ttk.Treeview(side, show='tree', selectmode='browse', height=20)
        self.tree_side.pack(fill='both', expand=True)
        self.tree_side.bind('<<TreeviewSelect>>', self._side_pick)
        body.add(side, weight=1)
        main = tk.Frame(body, bg=c['PANEL'])
        body.add(main, weight=5)
        self.tv = ttk.Treeview(main, columns=[k for k, _l, _w in self.COLS], show='headings', selectmode='extended')
        for key, label, width in self.COLS:
            self.tv.heading(key, text=label, command=lambda k=key: self._sort_by(k))
            self.tv.column(key, width=width, anchor='w' if key in ('title', 'profile', 'company') else 'center')
        ys = ttk.Scrollbar(main, orient='vertical', command=self.tv.yview)
        self.tv.configure(yscrollcommand=ys.set)
        ys.pack(side='right', fill='y')
        self.tv.pack(fill='both', expand=True)
        self.tv.bind('<Double-1>', lambda e: self.open_selected())
        self.tv.bind('<Return>', lambda e: self.open_selected())
        self.tv.bind('<F2>', lambda e: self.rename_selected())
        self.tv.bind('<Delete>', lambda e: self.trash_selected())
        self.tv.bind('<Button-3>', self._context)
        self.info = tk.Label(self, text='', fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 9), anchor='w')
        self.info.pack(fill='x', padx=12, pady=(0, 6))

    # ---- veri
    def rows(self):
        kind, val = self.filter
        status = 'trash' if kind == 'trash' else 'active'
        rows = self.store.list(status, self.q.get())
        if kind == 'profile':
            rows = [r for r in rows if r['profile'] == val]
        elif kind == 'company':
            rows = [r for r in rows if (r['company'] or '—') == val]
        key, rev = self.sort
        rows.sort(key=lambda r: (str(r.get(key) or '').lower() if key not in ('size', 'filled') else r.get(key) or 0), reverse=rev)
        return rows

    def refresh(self):
        all_rows = self.store.list('active')
        trash = self.store.list('trash')
        sel = self.tree_side.selection()
        self.tree_side.delete(*self.tree_side.get_children())
        self.tree_side.insert('', 'end', iid='all', text='📁  Tüm raporlar  (%d)' % len(all_rows), open=True)
        st = self.tree_side.insert('', 'end', iid='grp_std', text='STANDARTLAR', open=True)
        for p in D.PROFILES:
            n = sum(1 for r in all_rows if r['profile'] == p)
            self.tree_side.insert(st, 'end', iid='p_' + p, text='%s  (%d)' % (D.PROFILE_LABELS[p], n))
        fm = self.tree_side.insert('', 'end', iid='grp_firm', text='FİRMALAR', open=True)
        firms = {}
        for r in all_rows:
            firms[r['company'] or '—'] = firms.get(r['company'] or '—', 0) + 1
        for k, (name, n) in enumerate(sorted(firms.items(), key=lambda x: x[0].lower())):
            self.tree_side.insert(fm, 'end', iid='c_%d' % k, text='%s  (%d)' % (name, n), values=(name,))
        self.tree_side.insert('', 'end', iid='trash', text='🗑  Çöp kutusu  (%d)' % len(trash))
        if sel and self.tree_side.exists(sel[0]):
            self.tree_side.selection_set(sel[0])
        self.tv.delete(*self.tv.get_children())
        rows = self.rows()
        for r in rows:
            size = r['size']
            size = '%.1f KB' % (size / 1024.0) if size >= 1024 else '%d B' % size
            self.tv.insert('', 'end', iid=r['id'], values=(r['title'], D.PROFILE_LABELS.get(r['profile'], r['profile']), r['company'] or '-',
                                                          r['site_code'] or '-', '%d/%d' % (r['filled'], r['sections']), size,
                                                          r['updated_at'][:16]))
        self.info.configure(text='%d rapor · çift tık: aç · F2: yeniden adlandır · Delete: çöp kutusu · sağ tık: diğer işlemler · '
                                 'Raporlar bu bilgisayarda saklanır: %s' % (len(rows), self.store.root))

    def _side_pick(self, _e=None):
        sel = self.tree_side.selection()
        if not sel:
            return
        iid = sel[0]
        new = self.filter
        if iid in ('all', 'grp_std', 'grp_firm'):
            new = ('all', None)
        elif iid == 'trash':
            new = ('trash', None)
        elif iid.startswith('p_'):
            new = ('profile', iid[2:])
        elif iid.startswith('c_'):
            new = ('company', self.tree_side.item(iid, 'values')[0])
        # refresh() secimi geri yukler ve bu yeniden <<TreeviewSelect>> uretir: suzgec degismediyse yenileme yok,
        # yoksa sonsuz dongu olur (2.2.0: sol agaca tiklayinca pencere donuyordu)
        if new != self.filter:
            self.filter = new
            self.refresh()

    def _sort_by(self, key):
        cur, rev = self.sort
        self.sort = (key, not rev if cur == key else key in ('updated_at', 'size', 'filled'))
        self.refresh()

    def selected(self):
        return list(self.tv.selection())

    # ---- islemler
    def new_menu(self):
        m = tk.Menu(self, tearoff=0)
        for p in D.PROFILES:
            m.add_command(label=D.PROFILE_LABELS[p], command=lambda x=p: self.new_report(x))
        b = self.new_btn
        m.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())

    def new_report(self, profile):
        pr = self.store.create(profile, title='Yeni BRCGS Raporu - %s' % S.now()[:10])
        self.refresh()
        self.app.open_brcgs_report(pr['id'])

    def import_docx(self):
        paths = filedialog.askopenfilenames(parent=self, title='Doldurulmuş ya da boş BRCGS raporu (DOCX)',
                                            filetypes=[('Word belgesi', '*.docx')])
        last = None
        for p in paths:
            try:
                last = self.store.import_docx(p)
            except Exception as e:
                messagebox.showerror('DOCX içe aktar', '%s\n\n%s' % (os.path.basename(p), e), parent=self)
        self.refresh()
        if last:
            self.app.open_brcgs_report(last['id'])

    def open_selected(self):
        for uid in self.selected()[:3]:
            if self.filter[0] == 'trash':
                messagebox.showinfo('Çöp kutusu', 'Açmak için önce raporu geri yükleyin (sağ tık › Geri yükle).', parent=self)
                return
            self.app.open_brcgs_report(uid)

    def rename_selected(self):
        sel = self.selected()
        if not sel:
            return
        pr = self.store.get(sel[0])
        win = tk.Toplevel(self)
        win.title('Yeniden adlandır')
        win.configure(bg=self.c['PANEL'], padx=14, pady=12)
        win.transient(self)
        var = tk.StringVar(value=pr['title'])
        e = ttk.Entry(win, textvariable=var, width=60)
        e.pack(fill='x')
        e.select_range(0, 'end')
        e.focus_set()

        def ok():
            try:
                self.store.rename(sel[0], var.get())
            except ValueError as ex:
                messagebox.showerror('Yeniden adlandır', str(ex), parent=win)
                return
            win.destroy()
            self.refresh()
            self.app.brcgs_title_changed(sel[0], var.get())
        e.bind('<Return>', lambda ev: ok())
        win.bind('<Escape>', lambda ev: win.destroy())
        self.app.btn(win, 'Tamam', ok, 'primary', side=None).pack(anchor='e', pady=(10, 0))
        self.rename_dialog = win

    def duplicate_selected(self):
        for uid in self.selected():
            self.store.duplicate(uid)
        self.refresh()

    def trash_selected(self):
        sel = self.selected()
        if not sel:
            return
        if self.filter[0] == 'trash':
            return self.delete_selected()
        for uid in sel:
            if self.app.brcgs_view_for(uid):
                messagebox.showinfo('Çöp kutusu', 'Açık bir rapor çöp kutusuna taşınamaz; önce sekmesini kapatın.', parent=self)
                return
        for uid in sel:
            self.store.set_status(uid, 'trash')
        self.refresh()
        self.app.flash('%d rapor çöp kutusuna taşındı (geri alınabilir).' % len(sel))

    def restore_selected(self):
        for uid in self.selected():
            self.store.set_status(uid, 'active')
        self.refresh()

    def delete_selected(self, confirm=None):
        sel = self.selected()
        if not sel:
            return
        if confirm is None:
            from tkinter import simpledialog
            confirm = simpledialog.askstring('Kalıcı sil', '%d rapor ve tüm sürümleri kalıcı olarak silinecek.\nOnaylamak için SIL yazın:'
                                             % len(sel), parent=self)
        if (confirm or '').strip().upper() != 'SIL':
            return
        for uid in sel:
            self.store.delete_forever(uid)
        self.refresh()

    def export_selected(self):
        sel = self.selected()
        if sel:
            v = self.app.open_brcgs_report(sel[0])
            if v:
                v.export_docx()

    def _context(self, e):
        iid = self.tv.identify_row(e.y)
        if iid and iid not in self.tv.selection():
            self.tv.selection_set(iid)
        m = tk.Menu(self, tearoff=0)
        if self.filter[0] == 'trash':
            m.add_command(label='Geri yükle', command=self.restore_selected)
            m.add_command(label='Kalıcı sil…', command=self.delete_selected)
        else:
            m.add_command(label='Aç  (Enter)', command=self.open_selected)
            m.add_command(label='Yeniden adlandır  (F2)', command=self.rename_selected)
            m.add_command(label='Kopyasını oluştur', command=self.duplicate_selected)
            m.add_command(label='DOCX\'e yaz…', command=self.export_selected)
            m.add_separator()
            m.add_command(label='Çöp kutusuna taşı  (Delete)', command=self.trash_selected)
        m.tk_popup(e.x_root, e.y_root)


# ============================================================================= rapor
class BrcgsReportView(tk.Frame):
    def __init__(self, app, master, store, uid):
        self.app = app
        self.c = _colors(app)
        super().__init__(master, bg=self.c['PANEL'])
        self.store = store
        self.project = store.get(uid)
        store.mark_opened(uid)
        self.dirty = False
        self.recovered = False
        self._assembled_lbl = None
        self.sec_badges = {}
        draft = store.get_draft(uid)
        if draft and str(draft.get('draft_at') or '') >= str(self.project.get('updated_at') or ''):
            if app.smoke or messagebox.askyesno('Kaydedilmemiş değişiklikler', '"%s" raporunda %s tarihli kaydedilmemiş değişiklikler var '
                                                '(program beklenmedik kapanmış olabilir).\n\nGeri getirilsin mi? Hayır derseniz son kayıt açılır.'
                                                % (self.project['title'], draft['draft_at'][:16]), parent=app):
                draft.pop('draft_at', None)
                self.project = draft
                self.recovered = True
            else:
                store.drop_draft(uid)
        self.page = 'overview'
        self.chapter = None
        self.section_pos = 0
        p = self.project['profile']
        self.template = E.DocxTemplate(D.template_path(p))
        self.fields = E.scan_fields(self.template, p)
        # denetimsiz etiketli hucreler (Company name / Site name / Address / Country): kendi grubunun basina, belge sirasiyla
        for f in reversed(E.plain_fields(self.template)):
            pos = next((k for k, x in enumerate(self.fields) if x['group'] == f['group']), len(self.fields))
            self.fields.insert(pos, f)
        self.groups = []
        for f in self.fields:
            if f['group'] not in self.groups:
                self.groups.append(f['group'])
        self.field_labels = {f['key']: f['label'] for f in self.fields}
        self.tables = [(k, E.TABLE_LABELS[k], cols) for k, (_t, cols) in E.official_tables(self.template).items()] + \
                      [(k, title, cols) for k, title, _t, cols, _l in E.generic_tables(self.template)]
        self.table_col_labels = {k: labels for k, _t, _tb, _c, labels in E.generic_tables(self.template)}
        self._build()
        self.show('overview')
        if self.recovered:
            self.mark_dirty()

    def autosave(self):
        if self.dirty:
            try:
                self.store.save_draft(self.project)
            except OSError:
                pass

    # ------------------------------------------------------------------ iskelet
    @property
    def uid(self):
        return self.project['id']

    def tab_text(self):
        return ('● ' if self.dirty else '') + '📋 ' + (self.project['title'] or 'BRCGS raporu')[:40]

    def _build(self):
        c = self.c
        top = tk.Frame(self, bg=c['PANEL'], padx=12, pady=8)
        top.pack(fill='x')
        self.app.btn(top, 'Kaydet ve kapat', self.save_and_close, 'ghost', side='right')
        self.app.btn(top, '📄 DOCX\'e yaz', self.export_docx, 'normal', side='right')
        self.app.btn(top, '💾 Kaydet', self.save, 'primary', side='right')
        self.state_lbl = tk.Label(top, text='● Kayıtlı', fg=c.get('OK_C', '#6fd39b'), bg=c['PANEL'], font=('Segoe UI', 9, 'bold'))
        self.state_lbl.pack(side='right', padx=10)
        self.title_lbl = tk.Label(top, text='', fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 12, 'bold'), anchor='w')
        self.title_lbl.pack(side='left')
        self.sub_lbl = tk.Label(top, text='', fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 9), anchor='w')
        self.sub_lbl.pack(side='left', padx=10, fill='x', expand=True)
        body = tk.Frame(self, bg=c['PANEL'])
        body.pack(fill='both', expand=True)
        self.nav = tk.Frame(body, bg=c['PANEL2'], width=210)
        self.nav.pack(side='left', fill='y')
        self.nav.pack_propagate(False)
        self.main = tk.Frame(body, bg=c['PANEL'])
        self.main.pack(side='left', fill='both', expand=True)
        self.nav_btns = {}
        items = list(NAV_FIXED_HEAD) + [('g:' + g, '▸  ' + g) for g in self.groups] + list(NAV_FIXED_TAIL)
        for key, label in items:
            b = tk.Button(self.nav, text=label, anchor='w', command=lambda k=key: self.show(k), bg=c['PANEL2'], fg=c['FG'], relief='flat',
                          bd=0, activebackground=c['SEL_BG'], activeforeground=c['SEL_FG'], font=('Segoe UI', 9), padx=12, pady=4,
                          cursor='hand2', wraplength=190, justify='left', highlightthickness=0)
            b.pack(fill='x')
            self.nav_btns[key] = b
        self._refresh_header()

    def _refresh_header(self):
        p = self.project
        self.title_lbl.configure(text=p['title'])
        self.sub_lbl.configure(text='%s · %s · %d bölüm' % (D.PROFILE_LABELS[p['profile']], p.get('company') or 'firma yok',
                                                             len(p['sections'])))
        for k, b in self.nav_btns.items():
            on = k == self.page or (k.startswith('g:') and self.page == k)
            b.configure(bg=self.c['SEL_BG'] if on else self.c['PANEL2'], fg=self.c['SEL_FG'] if on else self.c['FG'])
        counts = {'sections': len(p['sections']), 'na': len(p['meta']['na_clauses']), 'plan': len(p['meta']['action_plan'].get('items') or [])}
        for k, n in counts.items():
            base = dict(NAV_FIXED_TAIL)[k]
            self.nav_btns[k].configure(text='%s  (%d)' % (base, n))

    def mark_dirty(self, *_a):
        if not self.dirty:
            self.dirty = True
            self.state_lbl.configure(text='● Kaydedilmedi', fg=self.c.get('WARN', '#e2b356'))
            self.app.brcgs_dirty_changed(self)

    def _mark_clean(self):
        self.dirty = False
        self.state_lbl.configure(text='● Kayıtlı', fg=self.c.get('OK_C', '#6fd39b'))
        self.app.brcgs_dirty_changed(self)

    def show(self, page):
        self.page = page
        for w_ in self.main.winfo_children():
            w_.destroy()
        self._refresh_header()
        fn = {'overview': self._page_overview, 'tables': self._page_tables, 'sections': self._page_sections, 'na': self._page_na,
              'plan': self._page_plan, 'preview': self._page_preview, 'history': self._page_history}.get(page)
        if fn:
            fn()
        elif page.startswith('g:'):
            self._page_fields(page[2:])
        self._autowrap(self.main)

    def _autowrap(self, root):
        """Sabit wraplength (>=600) verilen etiketler kapsayicinin gercek genisligine gore kaydirilir (dar pencerede kesilmez)."""
        stack = [root]
        while stack:
            w_ = stack.pop()
            stack.extend(w_.winfo_children())
            if isinstance(w_, tk.Label):
                try:
                    if int(str(w_.cget('wraplength')) or 0) >= 600:
                        master = w_.master

                        def fit(_e=None, l=w_, m=master):
                            try:
                                others = sum(x.winfo_width() for x in m.winfo_children() if x is not l and x.winfo_manager() == 'pack'
                                             and x.pack_info().get('side') in ('left', 'right'))
                                l.configure(wraplength=max(200, m.winfo_width() - others - 28))
                            except tk.TclError:
                                pass
                        master.bind('<Configure>', fit, add='+')
                except (tk.TclError, ValueError):
                    pass

    # ------------------------------------------------------------------ yardimcilar
    def _scroll(self):
        sc = Scroll(self.main, self.c['PANEL'])
        sc.pack(fill='both', expand=True)
        return sc.body

    def _block(self, parent, title, hint=''):
        c = self.c
        f = tk.Frame(parent, bg=c['PANEL'], highlightthickness=1, highlightbackground=c['LINE'], padx=14, pady=10)
        f.pack(fill='x', padx=14, pady=(10, 0))
        if title:
            tk.Label(f, text=title, fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 11, 'bold'), anchor='w').pack(fill='x')
        if hint:
            tk.Label(f, text=hint, fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 9), anchor='w', justify='left',
                     wraplength=900).pack(fill='x', pady=(2, 6))
        return f

    def _text(self, parent, value, rows=3, on_change=None, width=80):
        c = self.c
        t = tk.Text(parent, height=rows, width=width, wrap='word', bg=c['EDIT_BG'], fg=c['FG'], insertbackground=c['ACCENT'],
                    relief='flat', bd=0, highlightthickness=1, highlightbackground=c['LINE'], highlightcolor=c['ACCENT'],
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

    # ------------------------------------------------------------------ Rapor bilgisi
    def coverage_totals(self):
        tot = {'green': 0, 'yellow': 0, 'red': 0, 'total': 0, 'filled': 0}
        p = self.project['profile']
        for row in self.project['sections']:
            text = str(row.get('value') or '')
            if text.strip():
                tot['filled'] += 1
            if COV is None:
                continue
            cv = COV.section_coverage(p, row['clause'], row.get('coverage_parent'), row.get('title'))
            if not cv or not cv.get('coverage_items'):
                continue
            s = COV.summary(cv, text, row.get('note') or '')
            for k in ('green', 'yellow', 'red', 'total'):
                tot[k] += int(s.get(k) or 0)
        return tot

    def _page_overview(self):
        c = self.c
        body = self._scroll()
        t = self.coverage_totals()
        pct = round(t['green'] * 100 / t['total']) if t['total'] else 0
        cards = tk.Frame(body, bg=c['PANEL'])
        cards.pack(fill='x', padx=14, pady=(12, 0))
        for k, (val, label, note) in enumerate(((len(self.project['sections']), 'Bölümler', '%d bölümde metin var' % t['filled']),
                                                ('%d/%d' % (t['green'], t['total']), 'Kapsam yeşil', '%%%d rapor metninde eşleşti' % pct),
                                                (t['yellow'], 'Kanıt notunda', 'yalnız kanıt notunda bulundu'),
                                                (t['red'], 'Eksik', 'henüz eşleşme yok'))):
            f = tk.Frame(cards, bg=c['PANEL'], highlightthickness=1, highlightbackground=c['LINE'], padx=14, pady=10)
            f.grid(row=0, column=k, sticky='nsew', padx=(0 if k == 0 else 8, 0))
            cards.columnconfigure(k, weight=1)
            tk.Label(f, text=str(val), fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 18, 'bold'), anchor='w').pack(fill='x')
            tk.Label(f, text=label, fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 10, 'bold'), anchor='w').pack(fill='x')
            tk.Label(f, text=note, fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 8), anchor='w').pack(fill='x')
        blk = self._block(body, 'Dosya bilgisi')
        grid = tk.Frame(blk, bg=c['PANEL'])
        grid.pack(fill='x')
        self.title_var = tk.StringVar(value=self.project['title'])
        p = self.project
        items = (('Rapor adı', None), ('Standart profili', D.PROFILE_LABELS[p['profile']]), ('Kayıt kimliği', p['id']),
                 ('Kaynak', p.get('source_file') or p.get('origin') or ''), ('Oluşturuldu', p.get('created_at') or ''),
                 ('Son kayıt', p.get('updated_at') or ''))
        for k, (label, val) in enumerate(items):
            r, col = divmod(k, 3)
            cell = tk.Frame(grid, bg=c['PANEL'])
            cell.grid(row=r, column=col, sticky='ew', padx=(0, 12), pady=4)
            grid.columnconfigure(col, weight=1)
            tk.Label(cell, text=label, fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 9), anchor='w').pack(fill='x')
            if val is None:
                e = ttk.Entry(cell, textvariable=self.title_var)
                e.pack(fill='x')
                self.title_var.trace_add('write', lambda *a: self._title_changed())
            else:
                e = ttk.Entry(cell)
                e.insert(0, val)
                e.configure(state='readonly')
                e.pack(fill='x')
        tk.Label(blk, text='Rapor bu bilgisayarda saklanır (%s). Her kayıttan önce geri dönülebilir bir sürüm anlık görüntüsü alınır; '
                           'son 25 sürüm saklanır. DOCX her zaman resmi BRCGS şablonunun üzerine yazılır, şablon yeniden kurulmaz.'
                           % self.store.root, fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 8), anchor='w', justify='left',
                 wraplength=900).pack(fill='x', pady=(6, 0))
        mods = B.optional_modules(p['profile'])
        if mods:
            mb = self._block(body, 'Ek modüller', 'İsteğe bağlı modüller yalnızca eklendiği raporlarda görünür. Eklenen maddeler "Rapor '
                                                 'bölümleri"nde ayrı bölüm olarak listelenir ve resmi şablondaki modül kutularına yazılır. '
                                                 'Boş bırakılan maddeler rapora yazılmaz.')
            have = {s['clause'] for s in p['sections']}
            for mod, info in mods.items():
                units = B.module_units(p['profile'], mod)
                present = sum(1 for u in units if u in have)
                row = tk.Frame(mb, bg=c['PANEL'])
                row.pack(fill='x', pady=2)
                tk.Label(row, text=info.get('title') or mod, fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 9, 'bold')).pack(side='left')
                if present < len(units):
                    self.app.btn(row, ('Bu rapora ekle (%d madde)' if not present else 'Eksik maddeleri ekle (%d/%%d)' % present)
                                 % len(units), lambda m=mod: self.add_module(m), 'normal', side='right')
                else:
                    tk.Label(row, text='Raporda · %d madde' % len(units), fg=c.get('OK_C', '#6fd39b'), bg=c['PANEL']).pack(side='right')
        xb = self._block(body, 'Excel ile çalışma', 'Denetçi rapor bölümlerini çevrimdışı Excel formunda doldurabilir. Form, buradaki alt madde '
                                                   'sorularının aynısını içerir. Doldurulan dosyayı içe aktardığınızda yanıtlar ilgili kutulara '
                                                   'yerleşir; boş hücreler mevcut metni silmez ve içe aktarmadan önce sürüm kaydı alınır.')
        xr = tk.Frame(xb, bg=c['PANEL'])
        xr.pack(anchor='w')
        self.app.btn(xr, '⤓ %s Excel şablonunu kaydet…' % D.PROFILE_SHORT[p['profile']], self.save_excel_template, 'ghost')
        self.app.btn(xr, '⤒ Excel\'den içe aktar…', self.import_excel, 'primary')
        hb = self._block(body, 'Bölüm doluluk haritası', 'Tıklayınca bölüme gider. Koyu: dolu · orta: kısmen · açık: boş')
        flow = tk.Frame(hb, bg=c['PANEL'])
        flow.pack(fill='x')
        per_row = 12
        for i, row in enumerate(p['sections']):
            n = len(str(row.get('value') or '').strip())
            bg = c['SEL_BG'] if n > 400 else (c['PANEL2'] if n > 40 else c['PANEL'])
            b = tk.Button(flow, text=row['clause'], width=7, command=lambda k=i: self.jump_to(k), bg=bg, fg=c['FG'], relief='flat', bd=0,
                          highlightthickness=1, highlightbackground=c['LINE'], font=('Segoe UI', 8), cursor='hand2')
            b.grid(row=i // per_row, column=i % per_row, padx=2, pady=2)

    def _title_changed(self):
        v = self.title_var.get().strip()
        if v and v != self.project['title']:
            self.project['title'] = v
            self.title_lbl.configure(text=v)
            self.mark_dirty()

    def add_module(self, mod, prepared=None):
        have = {s['clause'] for s in self.project['sections']}
        added = 0
        for key in B.module_units(self.project['profile'], mod):
            if key in have:
                continue
            self.project['sections'].append((prepared or {}).get(key) or B.module_row(self.project['profile'], key))
            added += 1
        if added:
            self.project['sections'] = B.sort_sections(self.project['sections'])
            self.mark_dirty()
            if prepared is None:
                self.show(self.page)
        return added

    def jump_to(self, index):
        row = self.project['sections'][index]
        self.chapter = B.chapter_of(row['clause'])
        rows = self.chapter_rows(self.chapter)
        self.section_pos = next((k for k, (i, _r) in enumerate(rows) if i == index), 0)
        self.show('sections')

    # ------------------------------------------------------------------ sablon alan gruplari
    def _value_of(self, f):
        v = self.project['values'].get(f['key'])
        if f['repeats'] > 1:
            if isinstance(v, list):
                return v[f['occurrence']] if f['occurrence'] < len(v) else ''
            if isinstance(v, str) and '\n' in v:
                lines = [x for x in v.split('\n') if x.strip()]
                return lines[f['occurrence']] if f['occurrence'] < len(lines) else ''
            return v if (v and f['occurrence'] == 0) else ''
        return v if isinstance(v, str) else ('' if v is None else str(v))

    def _set_value(self, f, value):
        vals = self.project['values']
        if f['repeats'] > 1:
            cur = vals.get(f['key'])
            if not isinstance(cur, list):
                cur = [self._value_of(dict(f, occurrence=i)) for i in range(f['repeats'])]
            while len(cur) < f['repeats']:
                cur.append('')
            if cur[f['occurrence']] == value:
                return
            cur[f['occurrence']] = value
            vals[f['key']] = cur
        else:
            if vals.get(f['key'], '') == value:
                return
            vals[f['key']] = value
        if f['key'] in IDENTITY_KEYS:
            self.project['company'] = S.company_of(vals)
            self.project['site_code'] = S.site_code_of(vals)
        self.mark_dirty()

    def _page_fields(self, group):
        c = self.c
        body = self._scroll()
        fields = [f for f in self.fields if f['group'] == group]
        blk = self._block(body, group, 'Alanlar resmi DOCX içerik denetimlerinden okunmuştur (etiket, tür ve açılır liste seçenekleri '
                                       'şablondan gelir). Tarih: YYYY-AA-GG ya da GG.AA.YYYY.')
        grid = tk.Frame(blk, bg=c['PANEL'])
        grid.pack(fill='x')
        grid.columnconfigure(1, weight=1)
        for r, f in enumerate(fields):
            label = f['label'] + ('  #%d' % (f['occurrence'] + 1) if f['repeats'] > 1 else '')
            lab = tk.Label(grid, text=label, fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 9), anchor='w', justify='left', wraplength=260)
            lab.grid(row=r, column=0, sticky='nw', padx=(0, 12), pady=3)
            val = self._value_of(f)
            if f['kind'] in ('dropDownList', 'comboBox'):
                opts = [i['text'] for i in f['items'] if not i.get('prompt')]
                var = tk.StringVar(value=val)
                cb = ttk.Combobox(grid, textvariable=var, values=[''] + opts, state='readonly' if f['kind'] == 'dropDownList' else 'normal')
                cb.grid(row=r, column=1, sticky='ew', pady=3)
                var.trace_add('write', lambda *a, ff=f, vv=var: self._set_value(ff, vv.get()))
            elif f['kind'] == 'date':
                var = tk.StringVar(value=val)
                e = ttk.Entry(grid, textvariable=var, width=16)
                e.grid(row=r, column=1, sticky='w', pady=3)
                hint = tk.Label(grid, text='', fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 8))
                hint.grid(row=r, column=2, sticky='w')

                def date_changed(*_a, ff=f, vv=var, hh=hint):
                    v = vv.get().strip()
                    d = E.parse_date(v)
                    hh.configure(text=('Word\'de: ' + E.format_date(d, ff['date_format'])) if d else ('tarih değil' if v else ''))
                    self._set_value(ff, v)
                var.trace_add('write', date_changed)
                date_changed()
            elif f['kind'] == 'text' or len(val) < 60 and not re.search(r'scope|description|profile|changes|justification|comments|'
                                                                        r'rationale|claims|reason|address', f['key'], re.I):
                var = tk.StringVar(value=val)
                ttk.Entry(grid, textvariable=var).grid(row=r, column=1, sticky='ew', pady=3)
                var.trace_add('write', lambda *a, ff=f, vv=var: self._set_value(ff, vv.get()))
            else:
                t = self._text(grid, val, rows=3, on_change=lambda v, ff=f: self._set_value(ff, v))
                t.grid(row=r, column=1, columnspan=2, sticky='ew', pady=3)
            if f.get('hint') and f['hint'] != f['label']:
                lab.configure(text=label + '\n' + f['hint'])

    # ------------------------------------------------------------------ resmi tablolar
    def _page_tables(self):
        c = self.c
        body = self._scroll()
        if not self.tables:
            self._block(body, 'Resmi tablolar', 'Bu şablonda satır satır doldurulan resmi tablo yok.')
            return
        rt = self.project['meta']['report_tables']
        for key, title, cols in self.tables:
            blk = self._block(body, title, 'Resmi şablondaki tabloya satır satır yazılır; başlık satırları ve biçim korunur. Boş bırakılan '
                                           'tablo şablondaki haliyle kalır.')
            labels = self.table_col_labels.get(key) or [E.COLUMN_LABELS.get(cname, cname) for cname in cols]
            rows = rt.setdefault(key, [])
            grid = tk.Frame(blk, bg=c['PANEL'])
            grid.pack(fill='x')
            for k, lab in enumerate(labels):
                tk.Label(grid, text=lab, fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 8, 'bold'), anchor='w',
                         wraplength=140).grid(row=0, column=k, sticky='w', padx=2)
                grid.columnconfigure(k, weight=1)
            for r, item in enumerate(rows):
                for k, cname in enumerate(cols):
                    var = tk.StringVar(value=str(item.get(cname) or ''))
                    ttk.Entry(grid, textvariable=var).grid(row=r + 1, column=k, sticky='ew', padx=2, pady=1)
                    var.trace_add('write', lambda *a, it=item, cn=cname, vv=var: (it.__setitem__(cn, vv.get()), self.mark_dirty()))
                tk.Button(grid, text='✕', command=lambda kk=key, rr=r: self._table_del(kk, rr), bg=c['PANEL'], fg=c.get('BAD_C', '#ff8a80'),
                          relief='flat', bd=0, cursor='hand2').grid(row=r + 1, column=len(cols), padx=4)
            self.app.btn(blk, '＋ Satır', lambda kk=key, cc=cols: self._table_add(kk, cc), 'ghost', side=None).pack(anchor='w', pady=(6, 0))

    def _table_add(self, key, cols):
        self.project['meta']['report_tables'].setdefault(key, []).append({cname: '' for cname in cols})
        self.mark_dirty()
        self.show('tables')

    def _table_del(self, key, r):
        del self.project['meta']['report_tables'][key][r]
        self.mark_dirty()
        self.show('tables')

    # ------------------------------------------------------------------ rapor bolumleri
    def chapters(self):
        seen = []
        for row in self.project['sections']:
            ch = B.chapter_of(row['clause'])
            if ch not in seen:
                seen.append(ch)
        return sorted(seen, key=lambda x: int(x) if x.isdigit() else 999)

    def chapter_rows(self, ch):
        return [(i, r) for i, r in enumerate(self.project['sections']) if B.chapter_of(r['clause']) == ch]

    def badge(self, row):
        if COV is None:
            return ''
        cv = COV.section_coverage(self.project['profile'], row['clause'], row.get('coverage_parent'), row.get('title'))
        if not cv:
            return 'manuel'
        return COV.badge_text(COV.summary(cv, str(row.get('value') or ''), row.get('note') or ''))

    def current_row(self):
        rows = self.chapter_rows(self.chapter)
        if not rows:
            return None, None
        self.section_pos = max(0, min(self.section_pos, len(rows) - 1))
        return rows[self.section_pos]

    def _page_sections(self):
        c = self.c
        if not self.project['sections']:
            self._block(self.main, 'Bu raporda bölüm yok')
            return
        chs = self.chapters()
        if self.chapter not in chs:
            self.chapter, self.section_pos = chs[0], 0
        top = tk.Frame(self.main, bg=c['PANEL'], padx=14, pady=8)
        top.pack(fill='x')
        tk.Label(top, text='Rapor bölümü rehberi', fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 11, 'bold')).pack(side='left')
        ctitle = B.chapter_title(self.project['profile'], self.chapter)
        tk.Label(top, text='  Bölüm %s%s' % (self.chapter, (' · ' + ctitle) if ctitle else ''), fg=c['MUTED'], bg=c['PANEL'],
                 font=('Segoe UI', 9)).pack(side='left')
        chips = tk.Frame(top, bg=c['PANEL'])
        chips.pack(side='right')
        for ch in chs:
            on = ch == self.chapter
            tk.Button(chips, text=ch, width=3, command=lambda x=ch: self._set_chapter(x), bg=c['SEL_BG'] if on else c['PANEL2'],
                      fg=c['SEL_FG'] if on else c['FG'], relief='flat', bd=0, cursor='hand2', font=('Segoe UI', 8, 'bold')
                      ).pack(side='left', padx=1)
        body = ttk.PanedWindow(self.main, orient='horizontal')
        body.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        left = tk.Frame(body, bg=c['PANEL2'])
        body.add(left, weight=1)
        ls = Scroll(left, c['PANEL2'], width=250)
        ls.pack(fill='both', expand=True)
        self.sec_badges = {}
        for pos, (i, row) in enumerate(self.chapter_rows(self.chapter)):
            on = pos == self.section_pos
            f = tk.Frame(ls.body, bg=c['SEL_BG'] if on else c['PANEL2'], padx=8, pady=5, cursor='hand2')
            f.pack(fill='x', pady=1)
            fg = c['SEL_FG'] if on else c['FG']
            l1 = tk.Label(f, text=row['clause'], fg=fg, bg=f['bg'], font=('Segoe UI', 9, 'bold'), anchor='w')
            l1.pack(fill='x')
            l2 = tk.Label(f, text=(row.get('title') or 'Başlıksız')[:110], fg=fg, bg=f['bg'], font=('Segoe UI', 8), anchor='w',
                          justify='left', wraplength=210)
            l2.pack(fill='x')
            filled, total = G.fill_counts(self.project['profile'], row)
            l3 = tk.Label(f, text='%d/%d · %s' % (filled, total, self.badge(row)), fg=c['MUTED'] if not on else fg, bg=f['bg'],
                          font=('Segoe UI', 7), anchor='w')
            l3.pack(fill='x')
            self.sec_badges[i] = l3
            for w_ in (f, l1, l2, l3):
                w_.bind('<Button-1>', lambda e, p=pos: self._set_pos(p))
        right = tk.Frame(body, bg=c['PANEL'])
        body.add(right, weight=4)
        self._section_editor(right)

    def _set_chapter(self, ch):
        self.chapter, self.section_pos = ch, 0
        self.show('sections')

    def _set_pos(self, pos):
        self.section_pos = pos
        self.show('sections')

    def step(self, delta):
        rows = self.chapter_rows(self.chapter)
        pos = self.section_pos + delta
        chs = self.chapters()
        if pos < 0:
            k = chs.index(self.chapter)
            if k > 0:
                self.chapter = chs[k - 1]
                pos = len(self.chapter_rows(self.chapter)) - 1
            else:
                pos = 0
        elif pos >= len(rows):
            k = chs.index(self.chapter)
            if k + 1 < len(chs):
                self.chapter, pos = chs[k + 1], 0
            else:
                pos = len(rows) - 1
        self.section_pos = pos
        self.show('sections')

    def _box_banner(self, parent, row):
        c = self.c
        p = self.project['profile']
        note = B.export_note(p, row['clause'])
        f = tk.Frame(parent, bg=c['PANEL2'], padx=10, pady=6)
        f.pack(fill='x', pady=(0, 8))
        if note['warning']:
            tk.Label(f, text='⚠  Resmi şablonda bu madde için kutu yok. Metni yazabilirsiniz, ancak DOCX dışa aktarımında bu bölüm yazılmaz.',
                     fg=c.get('WARN', '#e2b356'), bg=c['PANEL2'], font=('Segoe UI', 9), anchor='w', justify='left', wraplength=800).pack(fill='x')
            return
        bx = B.box_by_tag(p, note['tag']) or {}
        if not note['merged']:
            tk.Label(f, text='🗎  Resmi rapor kutusu: %s %s   [%s]' % (bx.get('clause', ''), bx.get('title', ''), note['tag']), fg=c['FG'],
                     bg=c['PANEL2'], font=('Segoe UI', 9), anchor='w', justify='left', wraplength=800).pack(fill='x')
        else:
            others = [k for k in note['siblings'] if k != row['clause']]
            tk.Label(f, text='⊕  Birleşik kutu: %s — bu bölüm dışa aktarımda %s ile birlikte tek kutuda birleştirilir. Sıra: %s'
                     % (note['tag'], ', '.join(others[:12]) + (' …' if len(others) > 12 else ''), ' → '.join(note['siblings'][:14]) +
                        (' …' if len(note['siblings']) > 14 else '')), fg=c['FG'], bg=c['PANEL2'], font=('Segoe UI', 9), anchor='w',
                     justify='left', wraplength=800).pack(fill='x')

    def _section_editor(self, parent):
        c = self.c
        p = self.project['profile']
        idx, row = self.current_row()
        if row is None:
            return
        body = Scroll(parent, c['PANEL'])
        body.pack(fill='both', expand=True)
        b = body.body
        head = tk.Frame(b, bg=c['PANEL'], padx=6, pady=6)
        head.pack(fill='x')
        tk.Label(head, text=row['clause'], fg=c['ACCENT'], bg=c['PANEL'], font=('Segoe UI', 13, 'bold')).pack(side='left')
        std = D.standard(p).get('sections') or {}
        full = (std.get(row['clause']) or {}).get('title') or row.get('title') or ''
        tk.Label(head, text='  ' + full[:300], fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 9), anchor='w', justify='left',
                 wraplength=760).pack(side='left', fill='x')
        wrap = tk.Frame(b, bg=c['PANEL'], padx=6)
        wrap.pack(fill='x')
        self._box_banner(wrap, row)
        u = B.unit(p, row['clause']) or {}
        if u.get('requirement'):
            rq = tk.Frame(wrap, bg=c['PANEL2'], padx=10, pady=6)
            rq.pack(fill='x', pady=(0, 8))
            refs = ' · '.join(x for x in (u.get('regulation'), ('BRCGS: ' + u['brcgs_ref']) if u.get('brcgs_ref') else '') if x)
            tk.Label(rq, text='Modül maddesi %s   %s' % (row['clause'], refs), fg=c['FG'], bg=c['PANEL2'], font=('Segoe UI', 9, 'bold'),
                     anchor='w').pack(fill='x')
            tk.Label(rq, text=u['requirement'].replace(' • ', '\n• '), fg=c['FG'], bg=c['PANEL2'], font=('Segoe UI', 9), anchor='w',
                     justify='left', wraplength=780).pack(fill='x')
        form = G.form_for(p, row['clause'])
        struct = G.struct_of(row)
        self._assembled_lbl = None
        if form:
            fb = tk.Frame(wrap, bg=c['PANEL'], highlightthickness=1, highlightbackground=c['ACCENT'], padx=10, pady=8)
            fb.pack(fill='x')
            hh = tk.Frame(fb, bg=c['PANEL'])
            hh.pack(fill='x')
            tk.Label(hh, text='%s için kılavuzun istediği bilgiler' % row['clause'], fg=c['FG'], bg=c['PANEL'],
                     font=('Segoe UI', 10, 'bold')).pack(side='left')
            rule = form.get('rule') or {}
            if form['rule_exact'] and rule.get('minimum_words'):
                tk.Label(hh, text='En az ~%s kelime beklenir' % rule['minimum_words'], fg=c['MUTED'], bg=c['PANEL'],
                         font=('Segoe UI', 8)).pack(side='right')
            if str(struct.get(G.LEGACY_KEY) or '').strip():
                tk.Label(fb, text='Önceden yazılmış metin (aşağıdaki kutulara taşıyıp burayı boşaltabilirsiniz)', fg=c['MUTED'],
                         bg=c['PANEL'], font=('Segoe UI', 9), anchor='w').pack(fill='x', pady=(6, 0))
                self._text(fb, struct[G.LEGACY_KEY], rows=5, on_change=lambda v: self._answer(row, G.LEGACY_KEY, v)).pack(fill='x')
            for k, fd in enumerate(form['fields']):
                tk.Label(fb, text='%d   %s' % (k + 1, fd.get('label') or fd['key']), fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 9, 'bold'),
                         anchor='w', justify='left', wraplength=780).pack(fill='x', pady=(8, 2))
                raw = str(struct.get(fd['key']) or '')
                if fd.get('type') == 'select' and fd.get('options'):
                    opts = fd['options']
                    labels = [''] + [str(G.option_label(o)) for o in opts]
                    values = [''] + [str(G.option_value(o)) for o in opts]
                    var = tk.StringVar(value=labels[values.index(raw)] if raw in values else raw)
                    cb = ttk.Combobox(fb, textvariable=var, values=labels, state='readonly', width=40)
                    cb.pack(anchor='w')
                    var.trace_add('write', lambda *a, ff=fd, vv=var, ll=labels, va=values: self._answer(
                        row, ff['key'], va[ll.index(vv.get())] if vv.get() in ll else vv.get()))
                elif fd.get('type') in ('text', 'date', 'number'):
                    var = tk.StringVar(value=raw)
                    ttk.Entry(fb, textvariable=var).pack(fill='x')
                    var.trace_add('write', lambda *a, ff=fd, vv=var: self._answer(row, ff['key'], vv.get()))
                else:
                    self._text(fb, raw, rows=int(fd.get('rows') or 2) + 1,
                               on_change=lambda v, ff=fd: self._answer(row, ff['key'], v)).pack(fill='x')
                if fd.get('hint'):
                    tk.Label(fb, text=fd['hint'], fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 8), anchor='w').pack(fill='x')
            if rule.get('should_not_include'):
                tk.Label(fb, text='Yazmayın: ' + ' · '.join(rule['should_not_include']), fg=c.get('BAD_C', '#ff8a80'), bg=c['PANEL'],
                         font=('Segoe UI', 8), anchor='w', justify='left', wraplength=780).pack(fill='x', pady=(8, 0))
            pv = tk.Frame(wrap, bg=c['PANEL'])
            pv.pack(fill='x', pady=(8, 0))
            tk.Label(pv, text='▾ Rapora yazılacak metin (kutulardan otomatik)', fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 9),
                     anchor='w').pack(fill='x')
            self._assembled_lbl = tk.Label(pv, text=row.get('value') or '—', fg=c['FG'], bg=c['PANEL2'], font=('Consolas', 9), anchor='w',
                                           justify='left', wraplength=780, padx=8, pady=6)
            self._assembled_lbl.pack(fill='x')
        else:
            if COV is not None:
                exp = COV.guide_expectations(p, row['clause']) or {}
                lines = [x for x in (exp.get('expected_content') or []) if x]
                if lines:
                    tk.Label(wrap, text='Kılavuz beklentisi:\n• ' + '\n• '.join(lines), fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 9),
                             anchor='w', justify='left', wraplength=780).pack(fill='x')
            tk.Label(wrap, text='Rapor bölümü metni', fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 9), anchor='w').pack(fill='x',
                                                                                                                         pady=(8, 2))
            self._text(wrap, row.get('value') or '', rows=12, on_change=lambda v: self._free_text(row, v)).pack(fill='x')
        ai = tk.Frame(wrap, bg=c['PANEL'])
        ai.pack(fill='x', pady=(8, 0))
        self.app.btn(ai, '✨ AI: Türkçe notlardan İngilizce rapor metni', lambda: self.ai_draft(row), 'ghost', side='left')
        tk.Label(wrap, text='Denetim kanıtları / hatırlatma notları', fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 9),
                 anchor='w').pack(fill='x', pady=(10, 2))
        self._text(wrap, row.get('note') or '', rows=4, on_change=lambda v: self._note(row, v)).pack(fill='x')
        tk.Label(wrap, text='Bu bölümdeki bulgular (NC / gözlem)', fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 9),
                 anchor='w').pack(fill='x', pady=(10, 2))
        fnd = self.project['meta'].setdefault('section_findings', {})
        self._text(wrap, fnd.get(row['clause']) or '', rows=3, on_change=lambda v: self._finding(row, v)).pack(fill='x')
        nav = tk.Frame(wrap, bg=c['PANEL'])
        nav.pack(fill='x', pady=12)
        self.app.btn(nav, '← Önceki', lambda: self.step(-1), 'ghost')
        self.app.btn(nav, 'Bölümü kaydet', self.save, 'primary')
        self.app.btn(nav, 'Sonraki →', lambda: self.step(1), 'ghost', side='right')

    def _refresh_badge(self, row):
        idx = self.project['sections'].index(row)
        lbl = self.sec_badges.get(idx) if hasattr(self, 'sec_badges') else None
        if lbl is not None:
            try:
                filled, total = G.fill_counts(self.project['profile'], row)
                lbl.configure(text='%d/%d · %s' % (filled, total, self.badge(row)))
            except tk.TclError:
                pass

    def _answer(self, row, key, value):
        G.set_answer(self.project['profile'], row, key, value)
        if self._assembled_lbl is not None:
            try:
                self._assembled_lbl.configure(text=row['value'] or '—')
            except tk.TclError:
                pass
        self._refresh_badge(row)
        self.mark_dirty()

    def _free_text(self, row, value):
        row['value'] = value
        flags = row.setdefault('flags', {})
        flags.pop('struct', None)
        self._refresh_badge(row)
        self.mark_dirty()

    def _note(self, row, value):
        row['note'] = value
        self._refresh_badge(row)
        self.mark_dirty()

    def _finding(self, row, value):
        self.project['meta'].setdefault('section_findings', {})[row['clause']] = value
        self.mark_dirty()

    def ai_draft(self, row):
        """Kilavuz yanitlari + kanit notlarindan BRCGS raporu dilinde Ingilizce taslak; fark penceresinde onayla."""
        p = self.project['profile']
        st = G.struct_of(row)
        form = G.form_for(p, row['clause'])
        parts = []
        if form:
            for fd in form['fields']:
                v = str(st.get(fd['key']) or '').strip()
                if v:
                    parts.append('- %s: %s' % (fd.get('report_label') or fd.get('label') or fd['key'], v))
        if str(st.get(G.LEGACY_KEY) or '').strip():
            parts.append(str(st[G.LEGACY_KEY]))
        if not form and str(row.get('value') or '').strip():
            parts.append(str(row['value']))
        if str(row.get('note') or '').strip():
            parts.append('Evidence notes: ' + str(row['note']))
        if not parts:
            messagebox.showinfo('AI', 'Önce kılavuz kutularına ya da kanıt notuna bir şey yazın.', parent=self)
            return
        src = '\n'.join(parts)
        self.app.brcgs_ai_draft(self, row, src)

    def apply_ai_text(self, row, text):
        """AI metni bolumun rapor metni olur. Kilavuz kutularindaki yanitlar kaybolmaz: kanit notuna 'soru: yanit' olarak tasinir
        (aksi halde rapor metni = AI metni + ayni yanitlar olur, icerik iki kez yazilirdi)."""
        p = self.project['profile']
        flags = row.setdefault('flags', {})
        st = G.struct_of(row)
        form = G.form_for(p, row['clause'])
        moved = []
        if form:
            for fd in form['fields']:
                v = str(st.get(fd['key']) or '').strip()
                if v:
                    moved.append('%s: %s' % (fd.get('report_label') or fd.get('label') or fd['key'], v))
            old_legacy = str(st.get(G.LEGACY_KEY) or '').strip()
            if old_legacy and old_legacy != text.strip():
                moved.insert(0, old_legacy)
            if moved:
                note = str(row.get('note') or '').rstrip()
                row['note'] = (note + '\n\n' if note else '') + 'Kılavuz yanıtları (AI metninden önce):\n' + '\n'.join(moved)
            flags['struct'] = {G.LEGACY_KEY: text}
            row['value'] = G.assemble_text(p, row, flags['struct'])
        else:
            flags.pop('struct', None)
            row['value'] = text
        self.mark_dirty()
        self.show('sections')

    # ------------------------------------------------------------------ NA
    def _page_na(self):
        c = self.c
        body = self._scroll()
        rows = self.project['meta']['na_clauses']
        blk = self._block(body, 'Not Applicable maddeleri', 'Kapsam dışı bırakılan maddeler ve gerekçeleri ilgili bölümün resmi NA tablosuna/kutusuna '
                                                          'yazılır (madde numarasının ilk hanesi bölümü belirler).')
        grid = tk.Frame(blk, bg=c['PANEL'])
        grid.pack(fill='x')
        grid.columnconfigure(1, weight=1)
        for r, item in enumerate(rows):
            var = tk.StringVar(value=item.get('clause_ref') or '')
            ttk.Entry(grid, textvariable=var, width=12).grid(row=r, column=0, sticky='nw', padx=(0, 8), pady=2)
            var.trace_add('write', lambda *a, it=item, vv=var: (it.__setitem__('clause_ref', vv.get()), self.mark_dirty()))
            self._text(grid, item.get('justification') or '', rows=2,
                       on_change=lambda v, it=item: (it.__setitem__('justification', v), self.mark_dirty())).grid(row=r, column=1, sticky='ew',
                                                                                                             pady=2)
            tk.Button(grid, text='✕', command=lambda rr=r: self._na_del(rr), bg=c['PANEL'], fg=c.get('BAD_C', '#ff8a80'), relief='flat',
                      bd=0, cursor='hand2').grid(row=r, column=2, padx=4)
        if not rows:
            tk.Label(blk, text='Henüz NA maddesi yok.', fg=c['MUTED'], bg=c['PANEL']).pack(anchor='w')
        self.app.btn(blk, '＋ Satır', self._na_add, 'ghost', side=None).pack(anchor='w', pady=(6, 0))

    def _na_add(self):
        self.project['meta']['na_clauses'].append({'clause_ref': '', 'justification': ''})
        self.mark_dirty()
        self.show('na')

    def _na_del(self, r):
        del self.project['meta']['na_clauses'][r]
        self.mark_dirty()
        self.show('na')

    # ------------------------------------------------------------------ NC eylem plani
    def _page_plan(self):
        c = self.c
        body = self._scroll()
        items = self.project['meta']['action_plan'].setdefault('items', [])
        blk = self._block(body, 'NC Action Plan', 'Critical / Major satırları resmi Major (ve varsa Critical) tablosuna, Minor satırları Minor '
                                                 'tablosuna satır satır yazılır. "Bölümlerden tara" bölüm metinlerindeki NC satırlarını alır.')
        bar = tk.Frame(blk, bg=c['PANEL'])
        bar.pack(fill='x', pady=(0, 6))
        self.app.btn(bar, 'Bölümlerden tara', self._plan_scan, 'ghost')
        self.app.btn(bar, '＋ Satır', self._plan_add, 'ghost')
        if not items:
            tk.Label(blk, text='Henüz uygunsuzluk kaydı yok.', fg=c['MUTED'], bg=c['PANEL']).pack(anchor='w')
        for i, it in enumerate(items):
            f = tk.Frame(blk, bg=c['PANEL'], highlightthickness=1, highlightbackground=c['LINE'], padx=10, pady=6)
            f.pack(fill='x', pady=4)
            hr = tk.Frame(f, bg=c['PANEL'])
            hr.pack(fill='x')
            tk.Label(hr, text='#%d' % (i + 1), fg=c['ACCENT'], bg=c['PANEL'], font=('Segoe UI', 10, 'bold')).pack(side='left')
            tv = tk.StringVar(value=PLAN_TYPE_LABELS.get(str(it.get('type') or 'minor').lower(), 'Minor'))
            ttk.Combobox(hr, textvariable=tv, values=[PLAN_TYPE_LABELS[t] for t in PLAN_TYPES], state='readonly', width=12).pack(side='left',
                                                                                                                         padx=8)
            tv.trace_add('write', lambda *a, x=it, vv=tv: (x.__setitem__('type', vv.get().lower()), self.mark_dirty()))
            tk.Button(hr, text='✕ Sil', command=lambda k=i: self._plan_del(k), bg=c['PANEL'], fg=c.get('BAD_C', '#ff8a80'), relief='flat',
                      bd=0, cursor='hand2').pack(side='right')
            grid = tk.Frame(f, bg=c['PANEL'])
            grid.pack(fill='x')
            grid.columnconfigure(1, weight=1)
            for r, (key, label, rows) in enumerate(PLAN_FIELDS):
                tk.Label(grid, text=label, fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 9), anchor='w').grid(row=r, column=0, sticky='nw',
                                                                                                             padx=(0, 10), pady=2)
                val = str(it.get(key) or (it.get('detail') if key == 'nc_text' else '') or '')
                if rows == 1:
                    var = tk.StringVar(value=val)
                    ttk.Entry(grid, textvariable=var).grid(row=r, column=1, sticky='ew', pady=2)
                    var.trace_add('write', lambda *a, x=it, k=key, vv=var: (x.__setitem__(k, vv.get()), self.mark_dirty()))
                else:
                    self._text(grid, val, rows=2, on_change=lambda v, x=it, k=key: (x.__setitem__(k, v), self.mark_dirty())
                               ).grid(row=r, column=1, sticky='ew', pady=2)

    def _plan_add(self):
        self.project['meta']['action_plan'].setdefault('items', []).append({'type': 'minor', 'clause': '', 'nc_text': ''})
        self.mark_dirty()
        self.show('plan')

    def _plan_del(self, k):
        del self.project['meta']['action_plan']['items'][k]
        self.mark_dirty()
        self.show('plan')

    def _plan_scan(self):
        found = S.scan_action_plan(self.project)
        if not found:
            messagebox.showinfo('NC tarama', 'Bölüm metinlerinde "NC / non-conformity / uygunsuzluk" geçen satır bulunamadı.', parent=self)
            return
        items = self.project['meta']['action_plan'].setdefault('items', [])
        have = {(str(i.get('clause')), str(i.get('nc_text') or i.get('detail') or '').strip()) for i in items}
        new = [x for x in found if (x['clause'], x['nc_text']) not in have]
        items.extend(new)
        self.mark_dirty()
        self.show('plan')
        self.app.flash('%d uygunsuzluk satırı eklendi (%d zaten vardı).' % (len(new), len(found) - len(new)))

    # ------------------------------------------------------------------ onizleme / gecmis
    def _page_preview(self):
        c = self.c
        blk = self._block(self.main, 'Rapor önizlemesi', 'Ekrandaki güncel hâl (kaydedilmemiş değişiklikler dahil). DOCX çıktısı resmi şablonla '
                                                        'aynı sırayı izler.')
        t = tk.Text(self.main, wrap='word', bg=c['EDIT_BG'], fg=c['FG'], relief='flat', font=('Consolas', 9), padx=10, pady=8)
        t.pack(fill='both', expand=True, padx=14, pady=10)
        t.insert('1.0', S.preview_text(self.project, self.field_labels))
        t.configure(state='disabled')
        bar = tk.Frame(blk, bg=c['PANEL'])
        bar.pack(fill='x')
        self.app.btn(bar, 'Kopyala', lambda: (self.clipboard_clear(), self.clipboard_append(t.get('1.0', 'end-1c')),
                                              self.app.flash('Önizleme panoya kopyalandı.')), 'ghost')
        self.app.btn(bar, 'Editörde aç', lambda: self.app.new_doc(t.get('1.0', 'end-1c'), title=self.project['title'] + ' (önizleme)',
                                                                  rich=False), 'ghost')

    def _page_history(self):
        c = self.c
        body = self._scroll()
        blk = self._block(body, 'Sürüm geçmişi', 'Her kayıttan önce otomatik anlık görüntü alınır. Son %d sürüm saklanır. Geri dönmek de bir '
                                                'sürüm kaydı oluşturur.' % S.REVISION_LIMIT)
        revs = self.store.revisions(self.uid)
        if not revs:
            tk.Label(blk, text='Henüz sürüm yok (ilk kayıttan sonra oluşur).', fg=c['MUTED'], bg=c['PANEL']).pack(anchor='w')
        for r in revs:
            row = tk.Frame(blk, bg=c['PANEL'])
            row.pack(fill='x', pady=1)
            tk.Label(row, text='%s   ·   %s   ·   %d dolu bölüm   ·   %.1f KB' % (r['created_at'], r.get('label') or '', r.get('filled') or 0,
                                                                              r['size'] / 1024.0), fg=c['FG'], bg=c['PANEL'],
                     font=('Segoe UI', 9), anchor='w').pack(side='left')
            self.app.btn(row, 'Bu sürüme dön', lambda rid=r['id']: self.restore_revision(rid), 'ghost', side='right')

    def restore_revision(self, rid):
        if self.dirty and not messagebox.askyesno('Sürüme dön', 'Kaydedilmemiş değişiklikler kaybolacak. Devam edilsin mi?', parent=self):
            return
        self.project = self.store.restore_revision(self.uid, rid)
        self._mark_clean()
        self.show('history')
        self.app.flash('Sürüm geri yüklendi.')

    # ------------------------------------------------------------------ kaydet / disa aktar
    def save(self, force=False):
        try:
            self.project = self.store.save(self.project, force=force)
        except S.GuardError as e:
            if messagebox.askyesno('Kayıt durduruldu', '%s\n\nYine de üzerine yazılsın mı? (Önceki hâl sürüm geçmişinde kalır.)' % e,
                                   icon='warning', parent=self):
                return self.save(force=True)
            return False
        except OSError as e:
            messagebox.showerror('Kaydedilemedi', str(e), parent=self)
            return False
        self._mark_clean()
        self._refresh_header()
        self.app.flash('Rapor kaydedildi: %s' % self.project['title'])
        return True

    def save_and_close(self):
        if self.save() is not False:
            self.app.close_brcgs_view(self, ask=False)

    def export_docx(self):
        if self.dirty and not self.save():
            return
        chk = S.export_check(self.project)
        clean = re.sub(r'[\\/:*?"<>|]+', ' ', self.project['title']).strip(' .') or 'BRCGS raporu'
        path = filedialog.asksaveasfilename(parent=self, title='DOCX\'e yaz (resmi şablon)', initialfile=clean + '.docx',
                                            defaultextension='.docx', filetypes=[('Word belgesi', '*.docx')])
        if not path:
            return
        try:
            _blob, st = self.store.export_docx(self.project, path)
        except Exception as e:
            messagebox.showerror('DOCX yazılamadı', str(e), parent=self)
            return
        msg = ['Resmi şablon dolduruldu: %s' % os.path.basename(path), '',
               '%d alan · %d rapor kutusu · %d NA satırı · %d tablo · %d NC satırı' % (st['fields'], st['boxes'], st['na_rows'], st['tables'],
                                                                                   st['actions'] + st['critical']),
               'Dolu bölüm: %d / %d' % (chk['units_filled'], chk['units_total'])]
        if chk['merged_boxes']:
            msg.append('Birleştirilen kutular: ' + ', '.join('%s (%s)' % (t, '+'.join(v[:4]) + ('…' if len(v) > 4 else ''))
                                                           for t, v in list(chk['merged_boxes'].items())[:6]))
        if chk['skipped']:
            msg.append('⚠ Şablonda kutusu olmadığı için yazılmayan maddeler: ' + ', '.join(chk['skipped']))
        msg += ['', 'Dosya Word\'de açılsın mı?']
        if messagebox.askyesno('DOCX\'e yazıldı', '\n'.join(msg), parent=self):
            self.app._open_external(path)

    # ------------------------------------------------------------------ Excel
    def save_excel_template(self):
        src = D.excel_template_path(self.project['profile'])
        path = filedialog.asksaveasfilename(parent=self, title='Excel şablonunu kaydet', initialfile=src.name, defaultextension='.xlsx',
                                            filetypes=[('Excel', '*.xlsx')])
        if path:
            shutil.copyfile(str(src), path)
            self.app.flash('Excel şablonu kaydedildi: %s' % path)

    def import_excel(self):
        path = filedialog.askopenfilename(parent=self, title='Doldurulmuş Excel formu', filetypes=[('Excel', '*.xlsx')])
        if not path:
            return
        try:
            from agfo_brcgs import xlsx_reader as X
            parsed = X.parse(path)
        except Exception as e:
            messagebox.showerror('Excel içe aktarılamadı', str(e), parent=self)
            return
        self.apply_excel(parsed, os.path.basename(path))

    def plan_excel(self, parsed):
        """editor.js planExcelImport(): her Excel yanitini bir alt madde kutusuna esler; henuz hicbir sey degismez."""
        plan = {'items': [], 'skipped': [], 'legacy': 0, 'conflicts': 0, 'clauses': set(), 'answers': 0, 'notes': 0, 'new_rows': {},
                'add_modules': set()}
        pp = self.project['profile']
        xp = D.norm_profile(parsed.get('profile')) if parsed.get('profile') else ''
        if xp and xp != pp:
            plan['error'] = ('Bu Excel %s standardı için hazırlanmış; açık rapor ise %s. Doğru şablonu kullanın veya ilgili raporu açın.'
                             % (xp.upper(), pp.upper()))
            return plan
        rows = parsed.get('rows') or []
        if not rows:
            plan['error'] = 'Excel dosyasında doldurulmuş yanıt bulunamadı. Sarı "Yanıt" sütununun doldurulduğundan emin olun.'
            return plan
        by_clause = {s['clause']: s for s in self.project['sections']}
        skipped = []

        def norm(s):
            return re.sub(r'[.:;,]+$', '', re.sub(r'\s+', ' ', str(s or '').replace('I', 'ı').lower())).strip()
        for x in rows:
            clause = str(x.get('clause'))
            row = by_clause.get(clause)
            u = B.unit(pp, clause)
            if row is None and u and u.get('optional_module'):
                row = plan['new_rows'].setdefault(clause, B.module_row(pp, clause))
                plan['add_modules'].add(str(u['optional_module']))
            if row is None:
                if clause not in skipped:
                    skipped.append(clause)
                continue
            value = str(x.get('value') or '')
            item = {'row': row, 'clause': clause, 'value': value, 'kind': '', 'key': x.get('key')}
            if x.get('key') == '_note':
                item['kind'], item['existing'] = 'note', str(row.get('note') or '')
                plan['notes'] += 1
            elif x.get('key') == '_finding':
                item['kind'] = 'finding'
                item['existing'] = str((self.project['meta'].get('section_findings') or {}).get(clause) or '')
                plan['notes'] += 1
            else:
                form = G.form_for(pp, clause)
                fields = form['fields'] if form else []
                match = next((f for f in fields if f['key'] == x.get('key')), None)
                if match is None and x.get('label'):
                    match = next((f for f in fields if norm(f.get('label')) == norm(x['label'])), None)
                if match is not None:
                    item['kind'], item['key'] = 'field', match['key']
                    item['existing'] = str(G.struct_of(row).get(match['key']) or '')
                else:
                    item['kind'], item['key'], item['label'], item['existing'] = 'legacy', G.LEGACY_KEY, x.get('label') or x.get('key'), ''
                    plan['legacy'] += 1
                plan['answers'] += 1
            if item['existing'].strip() and item['existing'].strip() != value.strip() and item['kind'] != 'legacy':
                plan['conflicts'] += 1
            plan['clauses'].add(clause)
            plan['items'].append(item)
        plan['skipped'] = skipped
        return plan

    def apply_excel(self, parsed, name='', mode=None):
        plan = self.plan_excel(parsed)
        if plan.get('error'):
            messagebox.showerror('Excel içe aktarılamadı', plan['error'], parent=self)
            return 0
        if mode is None:
            lines = ['%s' % name, '', '%d alt madde, %d yanıt, %d not / bulgu' % (len(plan['clauses']), plan['answers'], plan['notes'])]
            if plan['conflicts']:
                lines.append('⚠ %d kutuda raporda zaten farklı bir metin var.' % plan['conflicts'])
            if plan['legacy']:
                lines.append('⚠ %d yanıtın sorusu artık formda yok; ilgili maddenin "Önceden yazılmış metin" kutusuna eklenecek.' % plan['legacy'])
            for m in plan['add_modules']:
                lines.append('%s bu rapora eklenecek.' % (B.optional_modules(self.project['profile']).get(m) or {}).get('title', m))
            if plan['skipped']:
                lines.append('Raporda olmayan maddeler atlanacak: ' + ', '.join(plan['skipped'][:20]))
            lines += ['', 'Excel\'de boş bırakılan hücreler rapordaki metni değiştirmez. İçe aktarmadan önce sürüm kaydı alınır.']
            if plan['conflicts']:
                lines += ['', 'Evet: Excel\'dekiler üzerine yazsın · Hayır: yalnız boş kutuları doldur · İptal: vazgeç']
                ans = messagebox.askyesnocancel('Excel içe aktarma özeti', '\n'.join(lines), parent=self)
                if ans is None:
                    return 0
                mode = 'overwrite' if ans else 'fill'
            else:
                if not messagebox.askokcancel('Excel içe aktarma özeti', '\n'.join(lines), parent=self):
                    return 0
                mode = 'fill'
        for m in plan['add_modules']:
            self.add_module(m, plan['new_rows'])
        written, kept, changed = 0, 0, {}

        def take(existing):
            return mode == 'overwrite' or not str(existing or '').strip()
        for it in plan['items']:
            row = it['row']
            if it['kind'] == 'note':
                if take(row.get('note')):
                    if str(row.get('note') or '') != it['value']:
                        row['note'] = it['value']
                        written += 1
                else:
                    kept += 1
                continue
            if it['kind'] == 'finding':
                fnd = self.project['meta'].setdefault('section_findings', {})
                if take(fnd.get(row['clause'])):
                    if str(fnd.get(row['clause']) or '') != it['value']:
                        fnd[row['clause']] = it['value']
                        written += 1
                else:
                    kept += 1
                continue
            flags = row.setdefault('flags', {})
            st = flags.get('struct') if isinstance(flags.get('struct'), dict) else G.struct_of(row)
            flags['struct'] = st
            if it['kind'] == 'legacy':
                add = ((it.get('label') + ': ') if it.get('label') else '') + it['value']
                prev = str(st.get(G.LEGACY_KEY) or '')
                if add not in prev:
                    st[G.LEGACY_KEY] = prev + '\n\n' + add if prev else add
                    written += 1
            elif take(st.get(it['key'])):
                if str(st.get(it['key']) or '') != it['value']:
                    st[it['key']] = it['value']
                    written += 1
            else:
                kept += 1
            changed[row['clause']] = row
        for row in changed.values():
            row['value'] = G.assemble_text(self.project['profile'], row, row['flags']['struct'])
        if not written:
            self.app.flash('Excel\'deki yanıtlar raporla aynı; değişiklik yok.' + (' (%d dolu kutu korundu)' % kept if kept else ''))
            return 0
        self.mark_dirty()
        self.store.snapshot(self.uid, 'pre-excel-import')
        self.save()
        self.show(self.page)
        self.app.flash('Excel içe aktarıldı: %d kutu güncellendi%s' % (written, (', %d dolu kutu korundu.' % kept) if kept else '.'))
        return written
