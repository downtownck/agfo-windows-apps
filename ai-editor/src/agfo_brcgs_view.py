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
from agfo_brcgs import findings as F
from agfo_brcgs import guide as G
from agfo_brcgs import i18n as I18N
from agfo_brcgs import review as RV
from agfo_brcgs import review_pack as RP
from agfo_brcgs import store as S
import agfo_wordview as WV

try:
    from agfo_brcgs import coverage as COV
except Exception:  # pragma: no cover
    COV = None

NAV_FIXED_HEAD = (('overview', 'ℹ  Report information'),)
NAV_FIXED_TAIL = (('tables', '▦  Official tables'), ('sections', '☰  Report sections'), ('na', '⊘  NA clauses'),
                  ('plan', '⚑  NC Action Plan'), ('review', '✔  Technical review'), ('preview', '👁  Preview'),
                  ('history', '⟲  Version history'))
PLAN_FIELDS = (('clause', 'Clause', 1), ('nc_text', 'Non-conformity details', 2), ('correction', 'Correction', 2),
               ('root_cause', 'Root cause analysis', 2), ('proposed_preventive_action', 'Proposed preventive action plan', 2),
               ('date_reviewed', 'Date reviewed', 1), ('reviewed_by', 'Reviewed by', 1))
IDENTITY_KEYS = {'OWNERCOMPANY', 'COMPANY_NAME', 'SITE_NAME', 'CERTIFIED_SITE_NAME', 'SITE_NAMEAB', 'BRC_SITE_CODE', 'SITE_CODE'}
PLAN_TYPES = ('critical', 'major', 'minor', 'fundamental')
PLAN_TYPE_LABELS = {'critical': 'Critical', 'major': 'Major', 'minor': 'Minor', 'fundamental': 'Fundamental'}


def _colors(app):
    c = dict(app.colors)
    c.setdefault('LINE', '#2d4a6c')
    c.setdefault('SEL_FG', '#ffffff')
    return c


PLAIN_TAG = '#plain'


def word_targets(blob):
    """Word gorunumunde tiklanabilir/duzenlenebilir hedefler, belge sirasinda: [((etiket, sira), gorunen_metin)].
    Yaprak icerik denetimleri + denetimsiz etiketli hucreler (CP/AB/SD 'Company name', 'Address' ...; bos ise etiketi)."""
    tpl = E.DocxTemplate(blob)
    W = E.w
    plain = {}
    for label, cell in E.plain_labeled_cells(tpl):
        plain[cell] = E.PLAIN_KEYS[label]
    label_cells = {}
    for cell, key in plain.items():
        row = cell.getparent()
        cells = E.row_cells(row)
        i = cells.index(cell) if cell in cells else 0
        if i > 0:
            label_cells[cell] = cells[i - 1]
    targets, seen, done = [], {}, set()
    for el in tpl.document.iter(W('sdt'), W('tc')):
        if el.tag == W('tc'):
            if el in plain and plain[el] not in done:
                done.add(plain[el])
                txt = E.node_text(el).strip() or E.node_text(label_cells.get(el, el))
                targets.append(((PLAIN_TAG, plain[el]), txt))
            continue
        cont = el.find(W('sdtContent'))
        if cont is None or next(cont.iter(W('sdt')), None) is not None or next(el.iter(W('tbl')), None) is not None:
            continue
        tag = E.sdt_props(el)['tag']
        occ = seen.get(tag, 0)
        seen[tag] = occ + 1
        targets.append(((tag, occ), E.sdt_text(el)))
    return targets


SCROLLERS = []          # (canvas, kaydirma) - fare tekerlegi icin kayitli alanlar


def _scrollable_under(widget):
    w_ = widget
    while w_ is not None:
        for cv, fn in SCROLLERS:
            if w_ is cv:
                return fn
        w_ = getattr(w_, 'master', None)
    return None


def _text_can_scroll(t, down):
    try:
        top, bot = t.yview()
    except tk.TclError:
        return False
    return (bot < 0.999) if down else (top > 0.001)


def install_wheel(root):
    """Tek, genel tekerlek isleyicisi (2.3.0). Eskiden kaydirma alani <Enter>'da tekerlegi baglayip <Leave>'de cozuyordu;
    Tk fare bir giris kutusuna/etikete gecince ust cerceveye <Leave> gonderdigi icin tekerlek surekli kopuyordu.
    Simdi imlecin altindaki pencereden yukari cikilip kayitli kaydirma alani bulunur. Kendi icerigi tasan bir metin
    kutusu once kendisi kayar; ucuna gelince sayfa kaymaya devam eder."""
    if getattr(root, '_agfo_wheel', False):
        return
    root._agfo_wheel = True

    def on_wheel(e, delta=None):
        d = delta if delta is not None else (e.delta if e.delta else 0)
        if not d:
            return None
        try:
            w_ = root.winfo_containing(e.x_root, e.y_root)
        except (KeyError, tk.TclError):
            w_ = None
        if w_ is None:
            # imlec altindaki pencere bulunamadiysa (Windows tekerlegi odaktaki pencereye de gonderebilir) olayin penceresi
            w_ = e.widget if isinstance(e.widget, tk.Misc) else None
        if w_ is None:
            return None
        fn = _scrollable_under(w_)
        if fn is None:
            return None
        down = d < 0
        if isinstance(w_, tk.Text) and _text_can_scroll(w_, down):
            return None                                     # metin kutusu kendi sinifi ile kayar
        steps = int(-d / 120) if abs(d) >= 120 else (-1 if d > 0 else 1)
        fn(steps * 3)
        return 'break'
    root.bind_all('<MouseWheel>', on_wheel, add='+')
    root.bind_all('<Button-4>', lambda e: on_wheel(e, 120), add='+')
    root.bind_all('<Button-5>', lambda e: on_wheel(e, -120), add='+')

    # acilir liste: tekerlek secili degeri degistirmez; kayitli bir alandaysa sayfayi kaydirir
    def combo_wheel(e, delta=None):
        if _scrollable_under(e.widget) is None:
            return 'break'
        on_wheel(e, delta)
        return 'break'
    for seq, dl in (('<MouseWheel>', None), ('<Button-4>', 120), ('<Button-5>', -120)):
        root.bind_class('TCombobox', seq, lambda e, d=dl: combo_wheel(e, d))


class Scroll(tk.Frame):
    """Dikey kaydirilabilir icerik alani (fare tekerlegi: install_wheel). Odaklanan alan gorunur alana kaydirilir."""

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
        entry = (self.canvas, lambda n: self.canvas.yview_scroll(n, 'units'))
        SCROLLERS.append(entry)
        self.bind('<Destroy>', lambda e: (SCROLLERS.remove(entry) if e.widget is self and entry in SCROLLERS else None), add='+')
        install_wheel(self.winfo_toplevel())
        # klavye ile (Tab) gelinen alan gorunur olsun
        self.body.bind_class('AgfoScrollFocus', '<FocusIn>', self._focus_in)
        self.after_idle(self._tag_children)

    def _tag_children(self):
        try:
            stack = [self.body]
            while stack:
                w_ = stack.pop()
                stack.extend(w_.winfo_children())
                tags = w_.bindtags()
                if 'AgfoScrollFocus' not in tags:
                    w_.bindtags(tags + ('AgfoScrollFocus',))
        except tk.TclError:
            pass

    def _focus_in(self, e):
        w_ = e.widget
        try:
            if not str(w_).startswith(str(self.body)):
                return
            self.canvas.update_idletasks()
            y = w_.winfo_rooty() - self.body.winfo_rooty()
            h = w_.winfo_height()
            total = max(1, self.body.winfo_height())
            view_top = self.canvas.canvasy(0)
            view_h = self.canvas.winfo_height()
            if y < view_top or y + h > view_top + view_h:
                self.canvas.yview_moveto(max(0, (y - 40)) / total)
        except tk.TclError:
            pass

    def top(self):
        self.canvas.yview_moveto(0)


# ============================================================================= gezgin
class BrcgsExplorer(tk.Frame):
    COLS = (('title', 'Report name', 340), ('profile', 'Standard', 200), ('company', 'Company', 220), ('site_code', 'Site code', 90),
            ('filled', 'Sections', 80), ('size', 'Size', 70), ('updated_at', 'Updated', 130))

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
        self.app.btn(top, '⤓ Open DOCX', self.import_docx, 'ghost', side='right')
        self.new_btn = self.app.btn(top, '＋ New report ▾', self.new_menu, 'primary', side='right')
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
        self.tree_side.insert('', 'end', iid='all', text='📁  All reports  (%d)' % len(all_rows), open=True)
        st = self.tree_side.insert('', 'end', iid='grp_std', text='STANDARDS', open=True)
        for p in D.PROFILES:
            n = sum(1 for r in all_rows if r['profile'] == p)
            self.tree_side.insert(st, 'end', iid='p_' + p, text='%s  (%d)' % (D.PROFILE_LABELS[p], n))
        fm = self.tree_side.insert('', 'end', iid='grp_firm', text='COMPANIES', open=True)
        firms = {}
        for r in all_rows:
            firms[r['company'] or '—'] = firms.get(r['company'] or '—', 0) + 1
        for k, (name, n) in enumerate(sorted(firms.items(), key=lambda x: x[0].lower())):
            self.tree_side.insert(fm, 'end', iid='c_%d' % k, text='%s  (%d)' % (name, n), values=(name,))
        self.tree_side.insert('', 'end', iid='trash', text='🗑  Trash  (%d)' % len(trash))
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
        self.info.configure(text='%d reports · double-click: open · F2: rename · Delete: move to trash · right-click: more · '
                                 'Reports are stored on this computer: %s' % (len(rows), self.store.root))

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
        pr = self.store.create(profile, title='New BRCGS report - %s' % S.now()[:10])
        self.refresh()
        self.app.open_brcgs_report(pr['id'])

    def import_docx(self):
        paths = filedialog.askopenfilenames(parent=self, title='Open a filled or blank BRCGS report (DOCX); Save writes back into it',
                                            filetypes=[('Word document', '*.docx')])
        last = None
        for p in paths:
            try:
                uid = self.store.find_linked(p)
                last = self.store.get(uid) if uid else self.store.import_docx(p, link=True)
            except Exception as e:
                messagebox.showerror('Import DOCX', '%s\n\n%s' % (os.path.basename(p), e), parent=self)
        self.refresh()
        if last:
            self.app.open_brcgs_report(last['id'])

    def open_selected(self):
        for uid in self.selected()[:3]:
            if self.filter[0] == 'trash':
                messagebox.showinfo('Trash', 'Restore the report first to open it (right-click › Restore).', parent=self)
                return
            self.app.open_brcgs_report(uid)

    def rename_selected(self):
        sel = self.selected()
        if not sel:
            return
        pr = self.store.get(sel[0])
        win = tk.Toplevel(self)
        win.title('Rename')
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
                messagebox.showerror('Rename', str(ex), parent=win)
                return
            win.destroy()
            self.refresh()
            self.app.brcgs_title_changed(sel[0], var.get())
        e.bind('<Return>', lambda ev: ok())
        win.bind('<Escape>', lambda ev: win.destroy())
        self.app.btn(win, 'OK', ok, 'primary', side=None).pack(anchor='e', pady=(10, 0))
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
                messagebox.showinfo('Trash', 'An open report cannot be moved to the trash; close its tab first.', parent=self)
                return
        for uid in sel:
            self.store.set_status(uid, 'trash')
        self.refresh()
        self.app.flash('%d report(s) moved to the trash (can be restored).' % len(sel))

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
            confirm = simpledialog.askstring('Delete permanently', '%d report(s) and all their versions will be deleted permanently.\nType DELETE to confirm:'
                                             % len(sel), parent=self)
        if (confirm or '').strip().upper() != 'DELETE':
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
            m.add_command(label='Restore', command=self.restore_selected)
            m.add_command(label='Delete permanently…', command=self.delete_selected)
        else:
            m.add_command(label='Open  (Enter)', command=self.open_selected)
            m.add_command(label='Rename  (F2)', command=self.rename_selected)
            m.add_command(label='Duplicate', command=self.duplicate_selected)
            m.add_command(label='Write DOCX…', command=self.export_selected)
            m.add_separator()
            m.add_command(label='Move to trash  (Delete)', command=self.trash_selected)
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
        self._report_box = self._closing_lbl = self._stale_lbl = None
        self.sec_badges = {}
        draft = store.get_draft(uid)
        if draft and str(draft.get('draft_at') or '') >= str(self.project.get('updated_at') or ''):
            if app.smoke or messagebox.askyesno('Unsaved changes', '"%s" has unsaved changes from %s '
                                                '(the program may have closed unexpectedly).\n\nRestore them? No opens the last saved version.'
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
        self.form_page = 'overview'
        self.wordview = None
        self._word = {'key': None, 'pdf': None, 'found': [], 'busy': False, 'error': None, 'pending': None, 'deferred': False}
        self.inline_editor = None
        self._field_widgets = {}
        self.review = None
        self._build()
        self.show('word' if self.app.doc_renderer().engine else 'overview')
        if self.recovered:
            self.mark_dirty()
        self.after(400, self.check_linked)

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
        return ('● ' if self.dirty else '') + '📋 ' + (self.project['title'] or 'BRCGS report')[:40]

    def _build(self):
        c = self.c
        top = tk.Frame(self, bg=c['PANEL'], padx=12, pady=8)
        top.pack(fill='x')
        self.app.btn(top, 'Save and close', self.save_and_close, 'ghost', side='right')
        self.open_word_btn = self.app.btn(top, 'Open in Word', self.open_in_word, 'ghost', side='right')
        self.export_btn = self.app.btn(top, '📄 Save as DOCX…', self.export_docx, 'normal', side='right')
        self.app.btn(top, '💾 Save', self.save, 'primary', side='right')
        sw = tk.Frame(top, bg=c['PANEL'])
        sw.pack(side='right', padx=(0, 14))
        self.mode_btns = {}
        for key, label in (('word', '📄 Word view'), ('form', '✎ Form')):
            b = tk.Button(sw, text=label, command=lambda k=key: self.set_mode(k), relief='flat', bd=0, highlightthickness=0, padx=12, pady=4,
                          cursor='hand2', font=('Segoe UI', 9, 'bold'), activebackground=c['ACCENT'])
            b.pack(side='left')
            self.mode_btns[key] = b
        self.state_lbl = tk.Label(top, text='● Saved', fg=c.get('OK_C', '#6fd39b'), bg=c['PANEL'], font=('Segoe UI', 9, 'bold'))
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
        linked = (p.get('meta') or {}).get('linked_docx')
        self.sub_lbl.configure(text='%s · %s · %d sections%s' % (D.PROFILE_LABELS[p['profile']], p.get('company') or 'no company',
                                                               len(p['sections']), ('   ·   🔗 ' + os.path.basename(linked)) if linked else ''))
        self.export_btn.configure(text='📄 Save a copy as DOCX…' if linked else '📄 Save as DOCX…')
        word = self.page == 'word'
        for k, b in self.mode_btns.items():
            on = (k == 'word') == word
            b.configure(bg=self.c['SEL_BG'] if on else self.c['PANEL2'], fg=self.c['SEL_FG'] if on else self.c['FG'])
        for k, b in self.nav_btns.items():
            on = k == self.page or (k.startswith('g:') and self.page == k)
            b.configure(bg=self.c['SEL_BG'] if on else self.c['PANEL2'], fg=self.c['SEL_FG'] if on else self.c['FG'])
        counts = {'sections': len(p['sections']), 'na': len(p['meta']['na_clauses']), 'plan': len(p['meta']['action_plan'].get('items') or [])}
        if getattr(self, 'review', None) is not None:
            rc = RV.counts(self.review)
            counts['review'] = rc['error'] + rc['warning']
        for k, n in counts.items():
            base = dict(NAV_FIXED_TAIL)[k]
            self.nav_btns[k].configure(text='%s  (%d)' % (base, n))

    def mark_dirty(self, *_a):
        if not self.dirty:
            self.dirty = True
            self.state_lbl.configure(text='● Unsaved', fg=self.c.get('WARN', '#e2b356'))
            self.app.brcgs_dirty_changed(self)

    def _mark_clean(self):
        self.dirty = False
        self.state_lbl.configure(text='● Saved', fg=self.c.get('OK_C', '#6fd39b'))
        self.app.brcgs_dirty_changed(self)

    def show(self, page):
        self.page = page
        for w_ in self.main.winfo_children():
            w_.destroy()
        self._refresh_header()
        if page != 'word':
            self.form_page = page
        self.wordview = None
        fn = {'overview': self._page_overview, 'tables': self._page_tables, 'sections': self._page_sections, 'na': self._page_na,
              'plan': self._page_plan, 'preview': self._page_preview, 'history': self._page_history, 'word': self._page_word,
              'review': self._page_review}.get(page)
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

    # ------------------------------------------------------------------ Word gorunumu (2.3.0)
    def set_mode(self, mode):
        if mode == 'word':
            self.show('word')
        else:
            self.show(self.form_page if self.form_page != 'word' else 'overview')

    def _render_input(self):
        """(anahtar, sablon_baytlari, yuk) - anahtar degismediyse sayfalar yeniden cizilmez."""
        import hashlib
        import json
        payload = S.Store.export_payload(copy.deepcopy(self.project))
        linked = self.project['meta'].get('linked_docx')
        template = None
        if linked and os.path.isfile(linked):
            try:
                with open(linked, 'rb') as fh:
                    template = fh.read()
            except OSError:
                template = None
        h = hashlib.sha1(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode('utf-8'))
        h.update(hashlib.sha1(template).digest() if template else b'bundled')
        return h.hexdigest(), template, payload

    def _page_word(self):
        c = self.c
        bar = tk.Frame(self.main, bg=c['PANEL'], padx=10, pady=6)
        bar.pack(fill='x')
        ren = self.app.doc_renderer()
        self.word_status = tk.Label(bar, text='', fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 9), anchor='w')
        self.app.btn(bar, '⟳ Refresh', lambda: self.refresh_word(force=True), 'ghost', side='right')
        self.app.btn(bar, '＋', lambda: self.wordview and self.wordview.set_zoom(self.wordview.zoom * 1.15), 'ghost', side='right')
        self.app.btn(bar, '－', lambda: self.wordview and self.wordview.set_zoom(self.wordview.zoom / 1.15), 'ghost', side='right')
        self.app.btn(bar, 'Fit width', lambda: self.wordview and self.wordview.fit(), 'ghost', side='right')
        self.word_status.pack(side='left', fill='x', expand=True)
        self.word_hover = tk.Label(self.main, text='Click a field or report box on the page to edit it here. Tab: next field · Enter: done · '
                                                   'Esc: cancel', fg=c['MUTED'],
                                   bg=c['PANEL2'], font=('Segoe UI', 8), anchor='w', padx=10)
        self.word_hover.pack(fill='x')
        self.wordview = WV.WordView(self.main, c, on_pick=self.pick_target, on_hover=self._hover_target,
                                    wheel_register=lambda cv, fn: self._register_wheel(cv, fn))
        self.wordview.pack(fill='both', expand=True)
        if not ren.engine:
            self.wordview.message('Word view needs Microsoft Word (or LibreOffice) on this computer to draw the pages exactly as '
                                  'Word shows them.\n\nYou can still fill the report in Form view; Save writes the DOCX.')
            self.word_status.configure(text='No renderer found')
            return
        self.refresh_word()

    def _register_wheel(self, canvas, fn):
        entry = (canvas, fn)
        SCROLLERS.append(entry)
        canvas.bind('<Destroy>', lambda e: (SCROLLERS.remove(entry) if entry in SCROLLERS else None), add='+')
        install_wheel(canvas.winfo_toplevel())

    def refresh_word(self, force=False):
        st = self._word
        if self.wordview is None:
            return
        key, template, payload = self._render_input()
        if not force and st['key'] == key and st['pdf']:
            self.wordview.set_document(st['pdf'], st['found'])
            self.word_status.configure(text='Drawn by %s · %d pages' % (self.app.doc_renderer().engine, len(self.wordview.sizes)))
            return
        if st['pdf'] and self.wordview.doc is None:
            self.wordview.set_document(st['pdf'], st['found'])          # eski hal, yenisi gelene kadar
        elif not st['pdf']:
            self.wordview.message('Drawing the pages with %s…' % self.app.doc_renderer().engine)
        self.word_status.configure(text='Updating with %s…' % self.app.doc_renderer().engine)
        if st['busy']:
            st['pending'] = (key, template, payload)
            return
        self._start_render(key, template, payload)

    def _start_render(self, key, template, payload):
        import queue
        import threading
        st = self._word
        st['busy'] = True
        q = queue.Queue()
        ren = self.app.doc_renderer()

        def work():
            try:
                blob, _st = E.write_report(payload, template=template)
                pdf = ren.to_pdf(blob)
                import agfo_docrender as R
                q.put(('ok', key, pdf, R.anchors(pdf, word_targets(blob), with_rect=True)))
            except Exception as e:  # noqa: BLE001
                q.put(('err', key, str(e), None))
        threading.Thread(target=work, daemon=True).start()

        def poll():
            try:
                kind, k, a, b = q.get_nowait()
            except queue.Empty:
                self.after(120, poll)
                return
            st['busy'] = False
            if kind == 'ok':
                st.update(key=k, pdf=a, found=b, error=None)
                if self.wordview is not None and self.winfo_exists() and self.wordview.editor is not None:
                    st['deferred'] = True                   # yazarken sayfa degismesin; duzenleyici kapaninca
                elif self.wordview is not None and self.winfo_exists():
                    self.wordview.set_document(a, b)
                    self.word_status.configure(text='Drawn by %s · %d pages · %s' % (
                        self.app.doc_renderer().engine, len(self.wordview.sizes),
                        ('linked file: ' + os.path.basename(self.project['meta']['linked_docx']))
                        if self.project['meta'].get('linked_docx') else 'official template'))
            else:
                st['error'] = a
                if self.wordview is not None and self.winfo_exists():
                    if not st['pdf']:
                        self.wordview.message('The pages could not be drawn:\n%s\n\nForm view still works.' % a)
                    self.word_status.configure(text='Drawing failed: %s' % a[:160])
            if st['pending']:
                nxt, st['pending'] = st['pending'], None
                if nxt[0] != st['key']:
                    self._start_render(*nxt)
        self.after(120, poll)

    def _target_info(self, target):
        """(sayfa, odak, etiket) - Word gorunumunde tiklanan alanin formdaki yeri."""
        tag, occ = target if isinstance(target, tuple) else (target, 0)
        p = self.project['profile']
        if tag == PLAIN_TAG:
            f = next((x for x in self.fields if x['kind'] == 'plain' and x['key'] == occ), None)
            if f is not None:
                return 'field', (f['key'], 0, f['group']), f['label']
            return 'overview', None, ''
        if not hasattr(self, '_tag_sections'):
            m = {}
            for row in self.project['sections']:
                note = B.export_note(p, row['clause'])
                if note.get('tag') and note['tag'] not in m:
                    m[note['tag']] = row['clause']
            self._tag_sections = m
            self._field_by_tag = {}
            for f in self.fields:
                if f.get('tag'):
                    self._field_by_tag.setdefault((f['tag'], f['occurrence']), f)
        if tag in self._tag_sections:
            c = self._tag_sections[tag]
            row = next((r for r in self.project['sections'] if r['clause'] == c), None)
            return 'section', c, '%s %s' % (c, (row or {}).get('title') or '')
        f = self._field_by_tag.get((tag, occ)) or self._field_by_tag.get((tag, 0))
        if f is not None:
            return 'field', (f['key'], f['occurrence'], f['group']), f['label']
        up = str(tag or '').upper()
        if tag in B.na_tags(p) or up.endswith('NAC') or 'NON_APPLICABLE' in up:
            return 'na', None, 'Not applicable clauses'
        if up.startswith('NON_CONFORMITY') or 'NONCONFORM' in up or 'CRITICAL' in up:
            return 'plan', None, 'NC Action Plan'
        if '_TABLE' in up or tag in self._table_tags():
            return 'tables', None, 'Official tables'
        return 'overview', None, ''

    def _table_tags(self):
        """Resmi ve genel tablolarin icindeki denetim etiketleri (ATFNAME, GFSIHOUTCOME ...): tiklama 'Official tables'."""
        if getattr(self, '_tbl_tags', None) is None:
            tags = set()
            tbls = [t for _k, (t, _c) in E.official_tables(self.template).items()] + \
                   [t for _k, _ti, t, _c, _l in E.generic_tables(self.template)]
            for t in tbls:
                for sdt in t.iter(E.w('sdt')):
                    tags.add(E.sdt_props(sdt)['tag'])
            self._tbl_tags = tags
        return self._tbl_tags

    # ---- yerinde duzenleme (2.4.0)
    def _field_of(self, target):
        tag, occ = target
        if tag == PLAIN_TAG:
            return next((x for x in self.fields if x['kind'] == 'plain' and x['key'] == occ), None)
        self._target_info(target)                       # onbellekleri kurar
        return self._field_by_tag.get((tag, occ)) or self._field_by_tag.get((tag, 0))

    def _box_text(self, tag):
        """Kutuda Word'de gorunen metin (birlesik kutularda madde basliklariyla, NC satirlari dahil)."""
        p = self.project['profile']
        rows = B.merge_for_export(p, F.export_sections(self.project))['rows']
        return next((r['value'] for r in rows if r['tag'] == tag), '')

    def inline_edit(self, target, region):
        kind, focus, label = self._target_info(target)
        wv = self.wordview
        c = self.c
        page, rect = region[1], region[4]
        if kind == 'field':
            f = self._field_of(target)
            if f is None:
                return False
            counted = {v: k for k, v in F.COUNT_KEYS.items()}
            if f['key'] in counted:
                self.app.flash('%s is counted from the non-conformity list; add or remove NCs to change it.' % f['label'], 7000)
                self.show('plan')
                return True
            value = self._value_of(f)
            multiline = f['kind'] in ('rich',) and (len(value) > 60 or re.search(
                r'scope|description|profile|changes|justification|comments|rationale|claims|reason|address', f['key'], re.I))
        elif kind == 'section':
            tag = target[0]
            value = self._box_text(tag)
            multiline = True
        else:
            return False
        frame = tk.Frame(wv.canvas, bg=c['ACCENT'], padx=2, pady=2)
        head = tk.Frame(frame, bg=c['PANEL'])
        head.pack(fill='x')
        tk.Label(head, text=label[:70], fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 8, 'bold'), anchor='w').pack(side='left', padx=4)
        result = {'done': False}

        def finish(save, nxt=0):
            if result['done']:
                return 'break'
            result['done'] = True
            if save:
                self._commit_inline(target, kind, focus, get(), page, rect, value)
            wv.close_editor()
            self._apply_deferred_render()
            if nxt:
                self.after(30, lambda: self._edit_next(target, nxt))
            return 'break'
        tk.Button(head, text='✕', command=lambda: finish(False), bg=c['PANEL'], fg=c['MUTED'], relief='flat', bd=0, cursor='hand2',
                  highlightthickness=0).pack(side='right', padx=2)
        tk.Button(head, text='✓ Done', command=lambda: finish(True), bg=c['PANEL'], fg=c['ACCENT'], relief='flat', bd=0, cursor='hand2',
                  font=('Segoe UI', 8, 'bold'), highlightthickness=0).pack(side='right', padx=2)
        tk.Button(head, text='Form…', command=lambda: (finish(True), self.open_in_form(target)), bg=c['PANEL'], fg=c['MUTED'],
                  relief='flat', bd=0, cursor='hand2', font=('Segoe UI', 8), highlightthickness=0).pack(side='right', padx=2)
        if kind == 'field' and f['kind'] in ('dropDownList', 'comboBox'):
            opts = [i['text'] for i in f['items'] if not i.get('prompt')]
            var = tk.StringVar(value=value)
            ed = ttk.Combobox(frame, textvariable=var, values=[''] + opts, state='readonly' if f['kind'] == 'dropDownList' else 'normal')
            ed.pack(fill='both', expand=True)
            ed.bind('<<ComboboxSelected>>', lambda e: finish(True))

            def get():
                return var.get()
            min_h = 24
        elif multiline:
            ed = tk.Text(frame, wrap='word', bg='#ffffff', fg='#111111', insertbackground='#111111', relief='flat', bd=0,
                         font=('Segoe UI', 10), padx=6, pady=4, undo=True)
            ed.insert('1.0', value)
            ed.pack(fill='both', expand=True)
            ed.bind('<Control-Return>', lambda e: finish(True))

            def get():
                return ed.get('1.0', 'end-1c')
            min_h = 90 if kind == 'field' else 160
        else:
            var = tk.StringVar(value=value)
            ed = ttk.Entry(frame, textvariable=var)
            ed.pack(fill='both', expand=True)
            ed.bind('<Return>', lambda e: finish(True))
            ed.select_range(0, 'end')

            def get():
                return var.get()
            min_h = 24
        ed.bind('<Escape>', lambda e: finish(False))
        ed.bind('<Tab>', lambda e: finish(True, 1))
        ed.bind('<Shift-Tab>', lambda e: finish(True, -1))
        wv.on_editor_click_away = lambda: finish(True)
        is_combo = kind == 'field' and f['kind'] in ('dropDownList', 'comboBox')
        wv.show_editor(frame, page, rect, min_w=320 if (multiline or is_combo) else 240, min_h=min_h,
                       max_h=440 if kind == 'section' else 220)
        ed.focus_set()
        if is_combo:
            ed.after(80, lambda: ed.winfo_exists() and ed.event_generate('<Down>'))      # liste hemen acik
        self.inline_editor = (target, ed, finish)
        return True

    def _commit_inline(self, target, kind, focus, text, page, rect, old):
        if text == old:
            return
        p = self.project['profile']
        if kind == 'field':
            f = self._field_of(target)
            if f['kind'] == 'date' and text.strip() and not E.parse_date(text):
                messagebox.showwarning('Date', '"%s" is not a date (YYYY-MM-DD or DD.MM.YYYY).' % text, parent=self)
                return
            self._set_value(f, text)
        else:
            tag = target[0]
            note = B.export_note(p, focus)
            if note.get('merged'):
                parts = {r['clause']: r['value'] for r in B.split_import(p, [{'tag': tag, 'value': text}])}
                clauses = note['siblings']
            else:
                parts, clauses = {focus: text}, [focus]
            for cl in clauses:
                row = next((r for r in self.project['sections'] if r['clause'] == cl), None)
                if row is None:
                    continue
                G.set_report_text(p, row, parts.get(cl, ''))
            self.mark_dirty()
        self.wordview.patch(page, rect, text)
        self._schedule_rerender()

    def _edit_next(self, target, step):
        wv = self.wordview
        if wv is None:
            return
        order = [a for a in wv.found if len(a) >= 5 and self._target_info(a[0])[0] in ('field', 'section')]
        k = next((i for i, a in enumerate(order) if a[0] == target), None)
        if k is None or not (0 <= k + step < len(order)):
            return
        nxt = order[k + step]
        self.inline_edit(nxt[0], nxt)

    def _schedule_rerender(self):
        if getattr(self, '_rerender_job', None):
            self.after_cancel(self._rerender_job)
        self._rerender_job = self.after(700, self._rerender_now)

    def _rerender_now(self):
        self._rerender_job = None
        if self.page == 'word' and self.wordview is not None:
            self.refresh_word()

    def _apply_deferred_render(self):
        st = self._word
        if st.get('deferred') and self.wordview is not None and self.wordview.editor is None:
            st['deferred'] = False
            self.wordview.set_document(st['pdf'], st['found'])

    def _hover_target(self, target):
        if target is None:
            text = 'Click a field or report box on the page to edit it here. Tab: next field · Enter: done · Esc: cancel'
        else:
            kind, _f, label = self._target_info(target)
            text = ('Click to edit: %s' % label) if kind in ('field', 'section') else \
                ('Click to open %s in the form' % ({'na': 'NA clauses', 'plan': 'NC Action Plan', 'tables': 'Official tables'}
                                                   .get(kind, 'this part')))
        try:
            if self.word_hover.cget('text') != text:
                self.word_hover.configure(text=text)
        except tk.TclError:
            pass

    def pick_target(self, target, region=None):
        """Word gorunumunde tiklama: alan/kutu ise yerinde duzenleyici, degilse formdaki sayfasi."""
        if region is None and self.wordview is not None:
            region = self.wordview.region_of(target)
        if region is not None and self.page == 'word' and self.inline_edit(target, region):
            return
        self.open_in_form(target)

    def open_in_form(self, target):
        kind, focus, _label = self._target_info(target)
        if kind == 'section':
            idx = next(i for i, r in enumerate(self.project['sections']) if r['clause'] == focus)
            self.jump_to(idx)
        elif kind == 'field':
            key, occ, group = focus
            self.show('g:' + group)
            w_ = self._field_widgets.get((key, occ))
            if w_ is not None:
                self.after(60, lambda: (w_.focus_set(), w_.event_generate('<FocusIn>')))
        else:
            self.show(kind)

    def open_in_word(self):
        linked = self.project['meta'].get('linked_docx')
        if not linked:
            if messagebox.askyesno('Open in Word', 'This report is not linked to a DOCX file yet. Save it as a DOCX now? '
                                                   'The report will be linked to that file.', parent=self):
                self.export_docx()
            return
        if self.dirty and not self.save():
            return
        self.app._open_external(linked)
        self.app.flash('Opened in Word. When you save there and come back, the changes are loaded here.', 8000)

    def check_linked(self):
        """Bagli DOCX disarida (Word'de) degistirildiyse raporu dosyadan gunceller."""
        meta = self.project.get('meta') or {}
        path = meta.get('linked_docx')
        if not path or not self.winfo_exists():
            return
        sig = S.file_sig(path)
        if sig is None or sig == meta.get('linked_sig'):
            return
        if getattr(self, '_asking_reload', False):
            return
        if self.dirty:
            self._asking_reload = True
            try:
                ok = messagebox.askyesno('File changed in Word', '"%s" was changed outside AGFO (for example in Word).\n\nLoad the '
                                         'file\'s version? Your unsaved changes here are kept in the version history.'
                                         % os.path.basename(path), parent=self)
            finally:
                self._asking_reload = False
            if not ok:
                meta['linked_sig'] = sig                    # bu degisiklik icin bir daha sorma
                return
        try:
            self.store.save(self.project, force=True)
            self.project = self.store.reload_linked(self.project)
            self.project = self.store.save(self.project, force=True)
        except Exception as e:
            messagebox.showerror('Could not load the file', str(e), parent=self)
            return
        if hasattr(self, '_tag_sections'):
            del self._tag_sections
        self._mark_clean()
        self.show(self.page)
        self.app.flash('Loaded the changes made to %s.' % os.path.basename(path), 8000)

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
        nc = F.counts(self.project)
        for k, (val, label, note) in enumerate(((len(self.project['sections']), 'Sections', '%d with report text' % t['filled']),
                                                ('%d/%d' % (t['green'], t['total']), 'Coverage green', '%d%% matched in the report text' % pct),
                                                (t['yellow'], 'In evidence notes', 'found only in the evidence notes'),
                                                (t['red'], 'Missing', 'no match yet'),
                                                (nc['total'], 'Non-conformities', F.count_text(nc, self.project['profile'])))):
            f = tk.Frame(cards, bg=c['PANEL'], highlightthickness=1, highlightbackground=c['LINE'], padx=14, pady=10)
            f.grid(row=0, column=k, sticky='nsew', padx=(0 if k == 0 else 8, 0))
            cards.columnconfigure(k, weight=1)
            tk.Label(f, text=str(val), fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 18, 'bold'), anchor='w').pack(fill='x')
            tk.Label(f, text=label, fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 10, 'bold'), anchor='w').pack(fill='x')
            tk.Label(f, text=note, fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 8), anchor='w').pack(fill='x')
        sb = tk.Frame(body, bg=c['PANEL'])
        sb.pack(fill='x', padx=14, pady=(8, 0))
        self.app.btn(sb, '⚑ Scan non-conformities and NA', self.scan_findings, 'normal')
        tk.Label(sb, text='Finds "Minor NC Ref. 2.2.2: …" statements in the section texts and counts NC by type and NA clauses.', fg=c['MUTED'],
                 bg=c['PANEL'], font=('Segoe UI', 8)).pack(side='left', padx=8)
        blk = self._block(body, 'File information')
        grid = tk.Frame(blk, bg=c['PANEL'])
        grid.pack(fill='x')
        self.title_var = tk.StringVar(value=self.project['title'])
        p = self.project
        items = (('Report name', None), ('Standard', D.PROFILE_LABELS[p['profile']]), ('Record ID', p['id']),
                 ('Source', p.get('source_file') or p.get('origin') or ''), ('Created', p.get('created_at') or ''),
                 ('Last saved', p.get('updated_at') or ''))
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
        tk.Label(blk, text='The report is stored on this computer (%s). A snapshot you can return to is taken before every save; '
                           'the last 25 versions are kept. The DOCX is always written onto the official BRCGS template; the template is never rebuilt.'
                           % self.store.root, fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 8), anchor='w', justify='left',
                 wraplength=900).pack(fill='x', pady=(6, 0))
        mods = B.optional_modules(p['profile'])
        if mods:
            mb = self._block(body, 'Additional modules', 'Optional modules appear only in reports they are added to. Their clauses are listed as separate sections under "Report '
                                                 'sections" and written into the module boxes of the official template. '
                                                 'Clauses left empty are not written to the report.')
            have = {s['clause'] for s in p['sections']}
            for mod, info in mods.items():
                units = B.module_units(p['profile'], mod)
                present = sum(1 for u in units if u in have)
                row = tk.Frame(mb, bg=c['PANEL'])
                row.pack(fill='x', pady=2)
                tk.Label(row, text=info.get('title') or mod, fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 9, 'bold')).pack(side='left')
                if present < len(units):
                    self.app.btn(row, ('Add to this report (%d clauses)' if not present else 'Add missing clauses (%d/%%d)' % present)
                                 % len(units), lambda m=mod: self.add_module(m), 'normal', side='right')
                else:
                    tk.Label(row, text='In the report · %d clauses' % len(units), fg=c.get('OK_C', '#6fd39b'), bg=c['PANEL']).pack(side='right')
        xb = self._block(body, 'Working with Excel', 'The auditor can fill the report sections offline in the Excel form. The form contains the same '
                                                   'sub-clause questions as here. When you import the filled file the answers go into the matching boxes; '
                                                   'empty cells never clear existing text, and a version snapshot is taken before importing.')
        xr = tk.Frame(xb, bg=c['PANEL'])
        xr.pack(anchor='w')
        self.app.btn(xr, '⤓ Save %s Excel template…' % D.PROFILE_SHORT[p['profile']], self.save_excel_template, 'ghost')
        self.app.btn(xr, '⤒ Import from Excel…', self.import_excel, 'primary')
        hb = self._block(body, 'Section fill map', 'Click to open a section. Dark: filled · medium: partly · light: empty')
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
        blk = self._block(body, group, 'Fields are read from the official DOCX content controls (labels, types and drop-down options '
                                       'come from the template). Dates: YYYY-MM-DD or DD.MM.YYYY.')
        grid = tk.Frame(blk, bg=c['PANEL'])
        grid.pack(fill='x')
        grid.columnconfigure(1, weight=1)
        counted = {v: k for k, v in F.COUNT_KEYS.items()}
        nc = F.counts(self.project)
        for r, f in enumerate(fields):
            label = f['label'] + ('  #%d' % (f['occurrence'] + 1) if f['repeats'] > 1 else '')
            if f['key'] in counted:
                tk.Label(grid, text=label, fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 9), anchor='w').grid(row=r, column=0, sticky='nw',
                                                                                                             padx=(0, 12), pady=3)
                tk.Label(grid, text='%d   (counted from the non-conformity list; written on export)' % nc[counted[f['key']]], fg=c['FG'],
                         bg=c['PANEL'], font=('Segoe UI', 9), anchor='w').grid(row=r, column=1, sticky='w', pady=3)
                continue
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
                    hh.configure(text=('In Word: ' + E.format_date(d, ff['date_format'])) if d else ('not a date' if v else ''))
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
        self._field_widgets = {}
        for r, f in enumerate(fields):
            sl = grid.grid_slaves(row=r, column=1)
            if sl:
                self._field_widgets[(f['key'], f['occurrence'])] = sl[0]

    # ------------------------------------------------------------------ resmi tablolar
    def _page_tables(self):
        c = self.c
        body = self._scroll()
        if not self.tables:
            self._block(body, 'Official tables', 'This template has no official tables filled row by row.')
            return
        rt = self.project['meta']['report_tables']
        for key, title, cols in self.tables:
            blk = self._block(body, title, 'Written row by row into the table of the official template; header rows and formatting are kept. A table left '
                                           'empty stays as it is in the template.')
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
            self.app.btn(blk, '＋ Row', lambda kk=key, cc=cols: self._table_add(kk, cc), 'ghost', side=None).pack(anchor='w', pady=(6, 0))

    def _table_add(self, key, cols):
        self.project['meta']['report_tables'].setdefault(key, []).append({cname: '' for cname in cols})
        self.mark_dirty()
        self.show('tables')

    def _table_del(self, key, r):
        if not self.app.smoke and not messagebox.askyesno('Remove', 'Remove this table row? (It can be restored from the version history after saving.)', parent=self):
            return
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
            return 'manual'
        sm = COV.summary(cv, str(row.get('value') or ''), row.get('note') or '')
        g, y, r, tot = (int(sm.get(k) or 0) for k in ('green', 'yellow', 'red', 'total'))
        if not tot:
            return 'manual'
        return '%d/%d' % (g, tot) + (' +%d evidence' % y if y else '') + (' · %d missing' % r if r else ' · complete')

    def current_row(self):
        rows = self.chapter_rows(self.chapter)
        if not rows:
            return None, None
        self.section_pos = max(0, min(self.section_pos, len(rows) - 1))
        return rows[self.section_pos]

    def _page_sections(self):
        c = self.c
        if not self.project['sections']:
            self._block(self.main, 'This report has no sections')
            return
        chs = self.chapters()
        if self.chapter not in chs:
            self.chapter, self.section_pos = chs[0], 0
        top = tk.Frame(self.main, bg=c['PANEL'], padx=14, pady=8)
        top.pack(fill='x')
        tk.Label(top, text='Report section guide', fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 11, 'bold')).pack(side='left')
        ctitle = B.chapter_title(self.project['profile'], self.chapter)
        tk.Label(top, text='  Section %s%s' % (self.chapter, (' · ' + ctitle) if ctitle else ''), fg=c['MUTED'], bg=c['PANEL'],
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
            l2 = tk.Label(f, text=(row.get('title') or 'Untitled')[:110], fg=fg, bg=f['bg'], font=('Segoe UI', 8), anchor='w',
                          justify='left', wraplength=210)
            l2.pack(fill='x')
            filled, total = G.fill_counts(self.project['profile'], row)
            l3 = tk.Label(f, text='%d/%d answered · %s' % (filled, total, self.badge(row)), fg=c['MUTED'] if not on else fg, bg=f['bg'],
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
            tk.Label(f, text='⚠  The official template has no box for this clause. You can write the text, but it is not written to the DOCX.',
                     fg=c.get('WARN', '#e2b356'), bg=c['PANEL2'], font=('Segoe UI', 9), anchor='w', justify='left', wraplength=800).pack(fill='x')
            return
        bx = B.box_by_tag(p, note['tag']) or {}
        if not note['merged']:
            tk.Label(f, text='🗎  Official report box: %s %s   [%s]' % (bx.get('clause', ''), bx.get('title', ''), note['tag']), fg=c['FG'],
                     bg=c['PANEL2'], font=('Segoe UI', 9), anchor='w', justify='left', wraplength=800).pack(fill='x')
        else:
            others = [k for k in note['siblings'] if k != row['clause']]
            tk.Label(f, text='⊕  Merged box: %s — on export this section is combined with %s in one box. Order: %s'
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
        note = B.export_note(p, row['clause'])
        if note.get('merged') and not str(row.get('value') or '').strip():
            holder = next((c_ for c_ in note['siblings'] if str((next((r for r in self.project['sections'] if r['clause'] == c_), {})
                                                                     ).get('value') or '').strip()), None)
            if holder and holder != row['clause']:
                hb = tk.Frame(wrap, bg=c['PANEL2'], padx=10, pady=6)
                hb.pack(fill='x', pady=(0, 8))
                tk.Label(hb, text='The text of this merged box is written under %s. You can keep it there, or move this clause\'s '
                                  'part here with its heading.' % holder, fg=c.get('WARN', '#e2b356'), bg=c['PANEL2'],
                         font=('Segoe UI', 9), anchor='w', justify='left', wraplength=700).pack(side='left', fill='x', expand=True)
                idx_ = next(i for i, r in enumerate(self.project['sections']) if r['clause'] == holder)
                self.app.btn(hb, 'Open %s' % holder, lambda k=idx_: self.jump_to(k), 'ghost', side='right')
        u = B.unit(p, row['clause']) or {}
        if u.get('requirement'):
            rq = tk.Frame(wrap, bg=c['PANEL2'], padx=10, pady=6)
            rq.pack(fill='x', pady=(0, 8))
            refs = ' · '.join(x for x in (u.get('regulation'), ('BRCGS: ' + u['brcgs_ref']) if u.get('brcgs_ref') else '') if x)
            tk.Label(rq, text='Module clause %s   %s' % (row['clause'], refs), fg=c['FG'], bg=c['PANEL2'], font=('Segoe UI', 9, 'bold'),
                     anchor='w').pack(fill='x')
            tk.Label(rq, text=u['requirement'].replace(' • ', '\n• '), fg=c['FG'], bg=c['PANEL2'], font=('Segoe UI', 9), anchor='w',
                     justify='left', wraplength=780).pack(fill='x')
        form = G.form_for(p, row['clause'])
        struct = G.struct_of(row)
        self._report_box = None
        self._closing_lbl = None
        self._stale_lbl = None
        if form:
            fb = tk.Frame(wrap, bg=c['PANEL'], highlightthickness=1, highlightbackground=c['ACCENT'], padx=10, pady=8)
            fb.pack(fill='x')
            hh = tk.Frame(fb, bg=c['PANEL'])
            hh.pack(fill='x')
            tk.Label(hh, text='Evidence the guideline expects for %s' % row['clause'], fg=c['FG'], bg=c['PANEL'],
                     font=('Segoe UI', 10, 'bold')).pack(side='left')
            rule = form.get('rule') or {}
            if form['rule_exact'] and rule.get('minimum_words'):
                tk.Label(hh, text='At least ~%s words expected' % rule['minimum_words'], fg=c['MUTED'], bg=c['PANEL'],
                         font=('Segoe UI', 8)).pack(side='right')
            tk.Label(fb, text='Enter the audit evidence in any language; the AI button turns it into English report text.',
                     fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 8), anchor='w').pack(fill='x', pady=(2, 0))
            if str(struct.get(G.LEGACY_KEY) or '').strip():
                tk.Label(fb, text='Previously written text (move it into the boxes below and clear this one if you like)', fg=c['MUTED'],
                         bg=c['PANEL'], font=('Segoe UI', 9), anchor='w').pack(fill='x', pady=(6, 0))
                self._text(fb, struct[G.LEGACY_KEY], rows=5, on_change=lambda v: self._answer(row, G.LEGACY_KEY, v)).pack(fill='x')
            for k, fd in enumerate(form['fields']):
                tk.Label(fb, text='%d   %s' % (k + 1, G.label_of(fd)), fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 9, 'bold'),
                         anchor='w', justify='left', wraplength=780).pack(fill='x', pady=(8, 2))
                raw = str(struct.get(fd['key']) or '')
                if fd.get('type') == 'select' and fd.get('options'):
                    opts = fd['options']
                    labels = [''] + [I18N.guide(G.option_label(o)) for o in opts]
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
                    tk.Label(fb, text=I18N.guide(fd['hint']), fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 8), anchor='w').pack(fill='x')
            if rule.get('should_not_include'):
                tk.Label(fb, text='Do not write: ' + ' · '.join(I18N.guide(x) for x in rule['should_not_include']), fg=c.get('BAD_C', '#ff8a80'),
                         bg=c['PANEL'], font=('Segoe UI', 8), anchor='w', justify='left', wraplength=780).pack(fill='x', pady=(8, 0))
        elif COV is not None:
            exp = COV.guide_expectations(p, row['clause']) or {}
            lines = [I18N.guide(x) for x in (exp.get('expected_content') or []) if x]
            if lines:
                tk.Label(wrap, text='The guideline expects:\n• ' + '\n• '.join(lines), fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 9),
                         anchor='w', justify='left', wraplength=780).pack(fill='x')
        tk.Label(wrap, text='Audit evidence / reminder notes (not exported)', fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 9),
                 anchor='w').pack(fill='x', pady=(10, 2))
        self._text(wrap, row.get('note') or '', rows=4, on_change=lambda v: self._note(row, v)).pack(fill='x')
        # ---- Ingilizce rapor metni (DOCX'e giden)
        rt = tk.Frame(wrap, bg=c['PANEL'])
        rt.pack(fill='x', pady=(12, 2))
        tk.Label(rt, text='Report text (English) — written to the official report', fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 10, 'bold'),
                 anchor='w').pack(side='left')
        self.ai_btn = self.app.btn(rt, '✨ AI: write English report text from the evidence', lambda: self.ai_draft(row), 'primary', side='right')
        self._stale_lbl = tk.Label(wrap, text='', fg=c.get('WARN', '#e2b356'), bg=c['PANEL'], font=('Segoe UI', 8), anchor='w')
        self._stale_lbl.pack(fill='x')
        self._report_box = self._text(wrap, row.get('value') or '', rows=8, on_change=lambda v: self._report_edit(row, v))
        self._report_box.pack(fill='x')
        tk.Label(wrap, text='You can edit this text. Clearing it returns to the text built from the evidence boxes.', fg=c['MUTED'],
                 bg=c['PANEL'], font=('Segoe UI', 8), anchor='w').pack(fill='x')
        self._section_findings(wrap, row)
        self._closing_lbl = tk.Label(wrap, text='', fg=c['MUTED'], bg=c['PANEL2'], font=('Consolas', 9), anchor='w', justify='left',
                                     wraplength=780, padx=8, pady=6)
        self._closing_lbl.pack(fill='x', pady=(8, 0))
        self._refresh_closing(row)
        old = str((self.project['meta'].get('section_findings') or {}).get(row['clause']) or '').strip()
        if old:
            tk.Label(wrap, text='Findings notes (from an earlier version or Excel; not exported)', fg=c['MUTED'], bg=c['PANEL'],
                     font=('Segoe UI', 9), anchor='w').pack(fill='x', pady=(10, 2))
            self._text(wrap, old, rows=3, on_change=lambda v: self._finding(row, v)).pack(fill='x')
        nav = tk.Frame(wrap, bg=c['PANEL'])
        nav.pack(fill='x', pady=12)
        self.app.btn(nav, '← Previous', lambda: self.step(-1), 'ghost')
        self.app.btn(nav, 'Save section', self.save, 'primary')
        self.app.btn(nav, 'Next →', lambda: self.step(1), 'ghost', side='right')
        self._show_stale(row)

    # ---- bolum bazinda NA / NC
    def _section_findings(self, parent, row):
        c = self.c
        clause = row['clause']
        box = tk.Frame(parent, bg=c['PANEL'], highlightthickness=1, highlightbackground=c['LINE'], padx=10, pady=8)
        box.pack(fill='x', pady=(12, 0))
        hdr = tk.Frame(box, bg=c['PANEL'])
        hdr.pack(fill='x')
        tk.Label(hdr, text='Not applicable in this section', fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 10, 'bold')).pack(side='left')
        self.app.btn(hdr, '＋ NA clause', lambda: self._sec_add_na(row), 'ghost', side='right')
        nas = F.section_nas(self.project, clause)
        if not nas:
            tk.Label(box, text='None. Add the sub-clauses that are not applicable at this site, with the justification.', fg=c['MUTED'],
                     bg=c['PANEL'], font=('Segoe UI', 8), anchor='w').pack(fill='x')
        for na in nas:
            r = tk.Frame(box, bg=c['PANEL'])
            r.pack(fill='x', pady=2)
            var = tk.StringVar(value=na.get('clause_ref') or '')
            ttk.Entry(r, textvariable=var, width=10).pack(side='left', anchor='n')
            var.trace_add('write', lambda *a, it=na, vv=var: (it.__setitem__('clause_ref', vv.get()), self._findings_changed(row)))
            tk.Button(r, text='✕', command=lambda it=na: self._sec_del_na(row, it), bg=c['PANEL'], fg=c.get('BAD_C', '#ff8a80'),
                      relief='flat', bd=0, cursor='hand2', highlightthickness=0).pack(side='right', anchor='n', padx=4)
            t = self._text(r, na.get('justification') or '', rows=2,
                           on_change=lambda v, it=na: (it.__setitem__('justification', v), self._findings_changed(row)))
            t.pack(side='left', fill='x', expand=True, padx=(8, 0))
        box2 = tk.Frame(parent, bg=c['PANEL'], highlightthickness=1, highlightbackground=c['LINE'], padx=10, pady=8)
        box2.pack(fill='x', pady=(8, 0))
        hdr = tk.Frame(box2, bg=c['PANEL'])
        hdr.pack(fill='x')
        ncs = F.section_ncs(self.project, clause)
        sc = {t: sum(1 for i in ncs if F.nc_type(i) == t) for t in F.TYPES}
        tk.Label(hdr, text='Non-conformities in this section', fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 10, 'bold')).pack(side='left')
        tk.Label(hdr, text='   ' + ' · '.join('%s %d' % (F.TYPE_LABELS[t], sc[t]) for t in self._nc_types()), fg=c['MUTED'], bg=c['PANEL'],
                 font=('Segoe UI', 9)).pack(side='left')
        self.app.btn(hdr, '＋ Non-conformity', lambda: self._sec_add_nc(row), 'ghost', side='right')
        if not ncs:
            tk.Label(box2, text='None. The AI text then ends with a conformity statement for this clause.', fg=c['MUTED'], bg=c['PANEL'],
                     font=('Segoe UI', 8), anchor='w').pack(fill='x')
        for it in ncs:
            r = tk.Frame(box2, bg=c['PANEL'])
            r.pack(fill='x', pady=3)
            top = tk.Frame(r, bg=c['PANEL'])
            top.pack(fill='x')
            tv = tk.StringVar(value=F.TYPE_LABELS[F.nc_type(it)])
            ttk.Combobox(top, textvariable=tv, values=[F.TYPE_LABELS[t] for t in self._nc_types()], state='readonly', width=12).pack(side='left')
            tv.trace_add('write', lambda *a, x=it, vv=tv: (x.__setitem__('type', vv.get().lower()), self._findings_changed(row)))
            tk.Label(top, text='  Clause', fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 9)).pack(side='left')
            cv = tk.StringVar(value=it.get('clause') or clause)
            ttk.Entry(top, textvariable=cv, width=10).pack(side='left', padx=(4, 0))
            cv.trace_add('write', lambda *a, x=it, vv=cv: (x.__setitem__('clause', vv.get()), self._findings_changed(row)))
            tk.Button(top, text='✕ Remove', command=lambda x=it: self._sec_del_nc(row, x), bg=c['PANEL'], fg=c.get('BAD_C', '#ff8a80'),
                      relief='flat', bd=0, cursor='hand2', highlightthickness=0).pack(side='right')
            self._text(r, F.nc_detail(it), rows=2, on_change=lambda v, x=it: (x.__setitem__('nc_text', v), self._findings_changed(row))
                       ).pack(fill='x', pady=(2, 0))
        if ncs:
            tk.Label(box2, text='Correction, root cause and preventive action are entered on the NC Action Plan page.', fg=c['MUTED'],
                     bg=c['PANEL'], font=('Segoe UI', 8), anchor='w').pack(fill='x', pady=(4, 0))

    def _nc_types(self):
        keys = E.field_keys(self.project['profile'])
        return [t for t in F.TYPES if F.COUNT_KEYS[t] in keys or t != 'fundamental']

    def _sec_add_na(self, row):
        self.project['meta'].setdefault('na_clauses', []).append({'clause_ref': row['clause'], 'justification': '', 'section': row['clause']})
        self.mark_dirty()
        self.show('sections')

    def _sec_del_na(self, row, item):
        if not self.app.smoke and not messagebox.askyesno('Remove', 'Remove this NA clause? (It can be restored from the version history after saving.)', parent=self):
            return
        self.project['meta']['na_clauses'].remove(item)
        self.mark_dirty()
        self.show('sections')

    def _sec_add_nc(self, row):
        self.project['meta'].setdefault('action_plan', {}).setdefault('items', []).append(
            {'type': 'minor', 'clause': row['clause'], 'nc_text': '', 'section': row['clause'], 'correction': '', 'root_cause': '',
             'proposed_preventive_action': '', 'date_reviewed': '', 'reviewed_by': ''})
        self.mark_dirty()
        self.show('sections')

    def _sec_del_nc(self, row, item):
        if not self.app.smoke and not messagebox.askyesno('Remove', 'Remove this non-conformity? (It can be restored from the version history after saving.)', parent=self):
            return
        self.project['meta']['action_plan']['items'].remove(item)
        self.mark_dirty()
        self.show('sections')

    def _findings_changed(self, row):
        self.mark_dirty()
        self._refresh_closing(row)
        self._refresh_header()

    def _refresh_closing(self, row):
        if self._closing_lbl is None:
            return
        lines = F.closing_lines(self.project, row)
        try:
            self._closing_lbl.configure(text='Added at the end of this section on export:\n' + '\n'.join(lines) if lines else
                                        'Nothing is added on export (empty section, or the text already states it).')
        except tk.TclError:
            pass

    def _show_stale(self, row):
        if self._stale_lbl is None:
            return
        flags = row.get('flags') or {}
        msg = ''
        if G.report_text(row) and flags.get('report_stale'):
            msg = '⚠ The evidence changed after this text was written. Press the AI button again to update it, or edit it here.'
        elif G.report_text(row):
            msg = 'English report text (written by AI or edited). The evidence boxes above stay as your source.'
        try:
            self._stale_lbl.configure(text=msg)
        except tk.TclError:
            pass

    def _set_report_box(self, text):
        if self._report_box is None:
            return
        try:
            self._report_box.delete('1.0', 'end')
            self._report_box.insert('1.0', text or '')
            self._report_box.edit_modified(False)
        except tk.TclError:
            pass

    def _refresh_badge(self, row):
        idx = self.project['sections'].index(row)
        lbl = self.sec_badges.get(idx) if hasattr(self, 'sec_badges') else None
        if lbl is not None:
            try:
                filled, total = G.fill_counts(self.project['profile'], row)
                lbl.configure(text='%d/%d answered · %s' % (filled, total, self.badge(row)))
            except tk.TclError:
                pass

    def _answer(self, row, key, value):
        G.set_answer(self.project['profile'], row, key, value)
        if not G.report_text(row):
            self._set_report_box(row['value'])
        self._show_stale(row)
        self._refresh_closing(row)
        self._refresh_badge(row)
        self.mark_dirty()

    def _report_edit(self, row, value):
        p = self.project['profile']
        if G.form_for(p, row['clause']) or G.report_text(row):
            built = G.assemble_text(p, row, G.struct_of(row)) if isinstance((row.get('flags') or {}).get('struct'), dict) else ''
            if value.strip() and value != built:
                G.set_report_text(p, row, value)
            elif not value.strip():
                G.set_report_text(p, row, '')
                self._set_report_box(row['value'])
        else:
            row['value'] = value
        self._show_stale(row)
        self._refresh_closing(row)
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
        if G.report_text(row):
            row.setdefault('flags', {})['report_stale'] = True
            self._show_stale(row)
        self._refresh_badge(row)
        self.mark_dirty()

    def _finding(self, row, value):
        self.project['meta'].setdefault('section_findings', {})[row['clause']] = value
        self.mark_dirty()

    def ai_source(self, row):
        """AI'ya giden kanit: kilavuz sorulari (Ingilizce) + yanitlar + onceki metin + kanit notu."""
        p = self.project['profile']
        st = G.struct_of(row)
        form = G.form_for(p, row['clause'])
        parts = []
        if form:
            for fd in form['fields']:
                v = str(st.get(fd['key']) or '').strip()
                if v:
                    parts.append('- %s: %s' % (G.report_label_of(fd), G.display_value(fd, v) if fd.get('type') == 'select' else v))
        if str(st.get(G.LEGACY_KEY) or '').strip():
            parts.append(str(st[G.LEGACY_KEY]))
        if not form and str(row.get('value') or '').strip() and not G.report_text(row):
            parts.append(str(row['value']))
        if str(row.get('note') or '').strip():
            parts.append('Evidence notes: ' + str(row['note']))
        return '\n'.join(parts)

    def ai_draft(self, row):
        """Kanitlardan Ingilizce rapor metni; AI dogrudan rapor metni kutusuna yazar (onizleme penceresi yok)."""
        src = self.ai_source(row)
        if not src.strip():
            messagebox.showinfo('AI', 'Enter the audit evidence in the boxes or the evidence notes first.', parent=self)
            return
        ncs = [it for it in F.section_ncs(self.project, row['clause']) if F.nc_detail(it)]
        self.app.brcgs_ai_draft(self, row, src, ncs)

    def apply_ai_result(self, row, text, nc_texts=None):
        """AI sonucu: rapor metni olur; NC detaylari Ingilizceye cevrildiyse NC listesine yazilir. Kanit kutulari degismez."""
        p = self.project['profile']
        G.set_report_text(p, row, text)
        if nc_texts:
            ncs = [it for it in F.section_ncs(self.project, row['clause']) if F.nc_detail(it)]
            if len(nc_texts) == len(ncs):
                for it, en in zip(ncs, nc_texts):
                    if en.strip():
                        it.setdefault('nc_text_original', F.nc_detail(it))
                        it['nc_text'] = en.strip()
        self.mark_dirty()
        if self.page == 'sections' and self.current_row()[1] is row:
            self.show('sections')

    # ------------------------------------------------------------------ NA
    def _page_na(self):
        c = self.c
        body = self._scroll()
        rows = self.project['meta']['na_clauses']
        blk = self._block(body, 'Not applicable clauses', 'Excluded clauses and their justifications are written to the official NA table/box of the matching '
                                                          'section (the first digit of the clause number decides the section). They can also be added on each section page.')
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
            tk.Label(blk, text='No NA clauses yet.', fg=c['MUTED'], bg=c['PANEL']).pack(anchor='w')
        self.app.btn(blk, '＋ Row', self._na_add, 'ghost', side=None).pack(anchor='w', pady=(6, 0))

    def _na_add(self):
        self.project['meta']['na_clauses'].append({'clause_ref': '', 'justification': ''})
        self.mark_dirty()
        self.show('na')

    def _na_del(self, r):
        if not self.app.smoke and not messagebox.askyesno('Remove', 'Remove this NA clause? (It can be restored from the version history after saving.)', parent=self):
            return
        del self.project['meta']['na_clauses'][r]
        self.mark_dirty()
        self.show('na')

    # ------------------------------------------------------------------ NC eylem plani
    def _page_plan(self):
        c = self.c
        body = self._scroll()
        items = self.project['meta']['action_plan'].setdefault('items', [])
        blk = self._block(body, 'NC Action Plan', 'Critical / Major rows go to the official Major (and Critical, if present) table, Minor rows to the Minor '
                                                 'table, row by row. "Scan section texts" picks up "Minor NC Ref. 2.2.2: …" statements written in the sections.')
        bar = tk.Frame(blk, bg=c['PANEL'])
        bar.pack(fill='x', pady=(0, 6))
        self.app.btn(bar, 'Scan section texts', self.scan_findings, 'ghost')
        self.app.btn(bar, '＋ Row', self._plan_add, 'ghost')
        if not items:
            tk.Label(blk, text='No non-conformities yet.', fg=c['MUTED'], bg=c['PANEL']).pack(anchor='w')
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
            tk.Button(hr, text='✕ Remove', command=lambda k=i: self._plan_del(k), bg=c['PANEL'], fg=c.get('BAD_C', '#ff8a80'), relief='flat',
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
        if not self.app.smoke and not messagebox.askyesno('Remove', 'Remove this non-conformity? (It can be restored from the version history after saving.)', parent=self):
            return
        del self.project['meta']['action_plan']['items'][k]
        self.mark_dirty()
        self.show('plan')

    def scan_findings(self, quiet=False):
        """Bolum metinlerindeki 'Minor NC 2.2.2: ...' kaliplarini NC listesine ekler, NC/NA sayilarini turune gore gosterir."""
        res = F.scan(self.project)
        if res['added']:
            self.mark_dirty()
        c = res['counts']
        per = {}
        for row in self.project['sections']:
            ncs = [i for i in F.section_ncs(self.project, row['clause']) if F.nc_detail(i)]
            nas = F.section_nas(self.project, row['clause'])
            if ncs or nas:
                per[row['clause']] = ', '.join(['%s %s' % (F.TYPE_LABELS[F.nc_type(i)], F.norm_clause(i.get('clause'))) for i in ncs] +
                                               ['NA %s' % F.norm_clause(n.get('clause_ref')) for n in nas])
        msg = ['Non-conformities: ' + F.count_text(c, self.project['profile']),
               '%d new NC statement(s) found in the section texts, %d already listed.' % (len(res['added']), res['existing'])]
        if any(k in E.field_keys(self.project['profile']) for k in F.COUNT_KEYS.values()):
            msg.append('The non-conformity count fields of the report are filled from these numbers on export.')
        if per:
            msg += ['', 'By section:'] + ['%s — %s' % (k, v) for k, v in list(per.items())[:30]]
        self.show(self.page)
        if not quiet:
            messagebox.showinfo('Scan non-conformities', '\n'.join(msg), parent=self)
        return res

    # ------------------------------------------------------------------ onizleme / gecmis
    def _page_preview(self):
        c = self.c
        blk = self._block(self.main, 'Report preview', 'Current state on screen (including unsaved changes), with the lines added on export. The DOCX follows the '
                                                        'order of the official template.')
        t = tk.Text(self.main, wrap='word', bg=c['EDIT_BG'], fg=c['FG'], relief='flat', font=('Consolas', 9), padx=10, pady=8)
        t.pack(fill='both', expand=True, padx=14, pady=10)
        t.insert('1.0', S.preview_text(self.project, self.field_labels))
        t.configure(state='disabled')
        bar = tk.Frame(blk, bg=c['PANEL'])
        bar.pack(fill='x')
        self.app.btn(bar, 'Copy', lambda: (self.clipboard_clear(), self.clipboard_append(t.get('1.0', 'end-1c')),
                                              self.app.flash('Preview copied to the clipboard.')), 'ghost')
        self.app.btn(bar, 'Open in editor', lambda: self.app.new_doc(t.get('1.0', 'end-1c'), title=self.project['title'] + ' (preview)',
                                                                  rich=False), 'ghost')

    # ------------------------------------------------------------------ teknik gozden gecirme (2.5.0)
    LEVEL_ICON = {'error': '⛔', 'warning': '⚠', 'info': 'ℹ'}

    def run_review(self):
        self.review = RV.run(self.project, self.fields)
        return self.review

    def _where_label(self, where):
        kind = where[0]
        if kind == 'field':
            f = next((x for x in self.fields if x['key'] == where[1] and x['occurrence'] == where[2]), None)
            return 'Field · %s' % (f['label'] if f else where[1])
        if kind == 'section':
            row = next((r for r in self.project['sections'] if r['clause'] == where[1]), None)
            return '%s %s' % (where[1], ((row or {}).get('title') or '')[:48])
        if kind == 'na':
            na = (self.project['meta'].get('na_clauses') or [])[where[1]]
            return 'NA %s' % (na.get('clause_ref') or '?')
        if kind == 'nc':
            it = self.project['meta']['action_plan']['items'][where[1]]
            return 'NC %s' % (it.get('clause') or '?')
        return 'Report'

    def _page_review(self):
        c = self.c
        found = self.run_review()
        n = RV.counts(found)
        top = tk.Frame(self.main, bg=c['PANEL'], padx=14, pady=8)
        top.pack(fill='x')
        tk.Label(top, text='Technical review', fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 12, 'bold')).pack(side='left')
        tk.Label(top, text='   against %s and the technical-review rules' % RV.guide_name(self.project['profile']), fg=c['MUTED'],
                 bg=c['PANEL'], font=('Segoe UI', 9)).pack(side='left')
        self.app.btn(top, '⟳ Check again', lambda: self.show('review'), 'ghost', side='right')
        self.show_info = getattr(self, 'show_info', tk.BooleanVar(value=False))
        ttk.Checkbutton(top, text='Show info', variable=self.show_info, command=lambda: self.show('review')).pack(side='right', padx=8)
        chips = tk.Frame(self.main, bg=c['PANEL'], padx=14)
        chips.pack(fill='x')
        for lvl, label, col in (('error', 'errors', c.get('BAD_C', '#ff8a80')), ('warning', 'warnings', c.get('WARN', '#e2b356')),
                                ('info', 'info', c['MUTED'])):
            tk.Label(chips, text='%s %d %s' % (self.LEVEL_ICON[lvl], n[lvl], label), fg=col, bg=c['PANEL'],
                     font=('Segoe UI', 10, 'bold')).pack(side='left', padx=(0, 16))
        if not n['error'] and not n['warning']:
            tk.Label(chips, text='No errors or warnings. Check the info items and the coverage before submitting.', fg=c['MUTED'],
                     bg=c['PANEL'], font=('Segoe UI', 9)).pack(side='left')
        body = ttk.PanedWindow(self.main, orient='vertical')
        body.pack(fill='both', expand=True, padx=8, pady=8)
        upper = tk.Frame(body, bg=c['PANEL'])
        body.add(upper, weight=3)
        cols = ('where', 'title', 'source')
        tv = ttk.Treeview(upper, columns=cols, show='tree headings', selectmode='browse', height=12)
        tv.heading('#0', text='')
        tv.column('#0', width=34, stretch=False)
        for k, lab, w in (('where', 'Where', 260), ('title', 'Finding', 560), ('source', 'Rule', 120)):
            tv.heading(k, text=lab)
            tv.column(k, width=w, anchor='w')
        ys = ttk.Scrollbar(upper, orient='vertical', command=tv.yview)
        tv.configure(yscrollcommand=ys.set)
        ys.pack(side='right', fill='y')
        tv.pack(fill='both', expand=True)
        shown = [f for f in found if f['level'] != 'info' or self.show_info.get()]
        for f in shown:
            tv.insert('', 'end', iid=str(f['id']), text=self.LEVEL_ICON[f['level']],
                      values=(self._where_label(f['where']), f['title'], f['source']))
        self.review_tree = tv
        lower = tk.Frame(body, bg=c['PANEL'])
        body.add(lower, weight=2)
        nb = ttk.Notebook(lower)
        nb.pack(fill='both', expand=True)
        det = tk.Frame(nb, bg=c['PANEL'], padx=10, pady=8)
        nb.add(det, text='Selected finding')
        self.review_detail = det
        tr = tk.Frame(nb, bg=c['PANEL'], padx=10, pady=8)
        nb.add(tr, text='Reviewer comments → responses')
        self._review_responses_ui(tr)
        tv.bind('<<TreeviewSelect>>', lambda e: self._review_select())
        tv.bind('<Double-1>', lambda e: self._review_go())
        tv.bind('<Return>', lambda e: self._review_go())
        if shown:
            tv.selection_set(str(shown[0]['id']))
            tv.focus(str(shown[0]['id']))
        else:
            tk.Label(det, text='Nothing to show.', fg=c['MUTED'], bg=c['PANEL']).pack(anchor='w')
        self.review_nb = nb

    def _review_current(self):
        sel = self.review_tree.selection() if getattr(self, 'review_tree', None) else ()
        if not sel:
            return None
        return next((f for f in self.review if str(f['id']) == sel[0]), None)

    def _review_select(self):
        c = self.c
        f = self._review_current()
        for w_ in self.review_detail.winfo_children():
            w_.destroy()
        if f is None:
            return
        d = self.review_detail
        tk.Label(d, text='%s  %s' % (self.LEVEL_ICON[f['level']], f['title']), fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 10, 'bold'),
                 anchor='w', justify='left', wraplength=900).pack(fill='x')
        tk.Label(d, text=self._where_label(f['where']) + '   ·   ' + f['source'], fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 8),
                 anchor='w').pack(fill='x')
        if f.get('detail'):
            tk.Label(d, text=f['detail'], fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 9), anchor='w', justify='left',
                     wraplength=900).pack(fill='x', pady=(6, 0))
        bar = tk.Frame(d, bg=c['PANEL'])
        bar.pack(fill='x', pady=(10, 0))
        self.app.btn(bar, '→ Go to', self._review_go, 'primary')
        if f['where'][0] == 'section':
            self.app.btn(bar, '✨ AI: revise this section by the rules', lambda: self.ai_review_section(f['where'][1]), 'ghost')
        self._autowrap(d)

    def _review_go(self):
        f = self._review_current()
        if f is None:
            return
        w = f['where']
        if w[0] == 'section':
            idx = next((i for i, r in enumerate(self.project['sections']) if r['clause'] == w[1]), None)
            if idx is not None:
                self.jump_to(idx)
        elif w[0] == 'field':
            fld = next((x for x in self.fields if x['key'] == w[1] and x['occurrence'] == w[2]), None)
            if fld is not None:
                self.show('g:' + fld['group'])
                wid = self._field_widgets.get((fld['key'], fld['occurrence']))
                if wid is not None:
                    self.after(60, lambda: (wid.focus_set(), wid.event_generate('<FocusIn>')))
        elif w[0] == 'na':
            self.show('na')
        elif w[0] == 'nc':
            self.show('plan')

    def _section_review_source(self, row):
        p = self.project['profile']
        parts = ['CURRENT REPORT TEXT:\n' + (row.get('value') or '(empty)')]
        ev = self.ai_source(row)
        if ev.strip():
            parts.append('AUDITOR EVIDENCE (guide answers and notes, may be Turkish):\n' + ev)
        ncs = [F.nc_line(it) for it in F.section_ncs(self.project, row['clause']) if F.nc_detail(it)]
        if ncs:
            parts.append('NON-CONFORMITIES RAISED BY THE AUDITOR IN THIS SECTION (added automatically after the text):\n' + '\n'.join(ncs))
        nas = ['%s - %s' % (n.get('clause_ref'), n.get('justification')) for n in F.section_nas(self.project, row['clause'])]
        if nas:
            parts.append('NOT APPLICABLE CLAUSES:\n' + '\n'.join(nas))
        g = RV.section_guidance(p, row['clause'], row.get('title') or '')
        if not g and COV is not None:
            exp = COV.guide_expectations(p, row['clause']) or {}
            g = '\n'.join('- ' + I18N.guide(x) for x in (exp.get('expected_content') or []) + (exp.get('must_include') or []) if x)
        if g:
            parts.append('%s GUIDANCE FOR THIS SECTION:\n%s' % (RV.guide_name(p), g))
        req = RV.requirement_text(p, row['clause'])
        if req:
            parts.append('STANDARD REQUIREMENTS (scope only; do not copy into the report):\n' + req)
        probs = [f for f in RV.run(self.project, self.fields) if f['where'] == ('section', row['clause']) and f['level'] != 'info']
        if probs:
            parts.append('REVIEW FINDINGS TO RESOLVE:\n' + '\n'.join('- %s. %s' % (f['title'], f['detail']) for f in probs))
        return '\n\n'.join(parts)

    def ai_review_section(self, clause):
        p = self.project['profile']
        row = next((r for r in self.project['sections'] if r['clause'] == clause), None)
        if row is None:
            return
        if not str(row.get('value') or '').strip() and not self.ai_source(row).strip():
            messagebox.showinfo('AI', 'This section has no report text or evidence to revise.', parent=self)
            return
        instruction = (RP.pack(p)['skill'][:9000] + '\n\n---\nTASK: Revise the report text of section %s "%s" so that it follows the '
                       'report-writing rules above and the %s guidance, and resolves the review findings. Use ONLY facts present in '
                       'the current report text and the auditor evidence; never invent evidence, dates, codes or results. Keep every '
                       'verified fact. Do not add non-conformities and do not write NC lines (they are added automatically). Write in '
                       'English. Return ONLY the revised report text - no headings, no notes, no markdown.'
                       % (clause, row.get('title') or '', RV.guide_name(p)))
        src = self._section_review_source(row)
        before = row.get('value') or ''

        def done(text, model):
            if not text or row not in self.project['sections']:
                return
            self.store.snapshot(self.uid, 'pre-ai-review-%s' % clause, self.project)
            G.set_report_text(p, row, text)
            self.mark_dirty()
            self._last_ai_undo = (row, before)
            if self.page == 'review':
                self.show('review')
            self.app.flash('%s revised by %s following the review rules. The previous text is in the version history.' % (clause, model),
                           9000)
        self.app.brcgs_ai_call('BRCGS review %s' % clause, instruction, src, done)

    # ---- teknik gozden gecirici yorumlarina yanitlar
    def _review_responses_ui(self, parent):
        c = self.c
        tk.Label(parent, text='Paste the certification body\'s technical-review comments (numbered). The AI answers each one in the '
                              'review format, using only this report\'s text and evidence.', fg=c['MUTED'], bg=c['PANEL'],
                 font=('Segoe UI', 9), anchor='w', justify='left', wraplength=900).pack(fill='x')
        row_ = tk.Frame(parent, bg=c['PANEL'])
        row_.pack(fill='both', expand=True, pady=(6, 0))
        self.tr_in = self._text(row_, (self.project['meta'].get('flags') or {}).get('tr_comments') or '', rows=8, width=50,
                                on_change=lambda v: (self.project['meta'].setdefault('flags', {}).__setitem__('tr_comments', v),
                                                     self.mark_dirty()))
        self.tr_in.pack(side='left', fill='both', expand=True)
        right = tk.Frame(row_, bg=c['PANEL'])
        right.pack(side='left', fill='both', expand=True, padx=(8, 0))
        self.tr_out = self._text(right, (self.project['meta'].get('flags') or {}).get('tr_responses') or '', rows=8, width=50,
                                 on_change=lambda v: (self.project['meta'].setdefault('flags', {}).__setitem__('tr_responses', v),
                                                      self.mark_dirty()))
        self.tr_out.pack(fill='both', expand=True)
        bar = tk.Frame(parent, bg=c['PANEL'])
        bar.pack(fill='x', pady=(6, 0))
        self.app.btn(bar, '✨ Draft responses', self.ai_tr_responses, 'primary')
        self.app.btn(bar, 'Copy responses', lambda: (self.clipboard_clear(), self.clipboard_append(self.tr_out.get('1.0', 'end-1c')),
                                                     self.app.flash('Responses copied.')), 'ghost')
        self.app.btn(bar, 'Apply a response to its section…', self.apply_tr_response, 'ghost')

    @staticmethod
    def parse_responses(text):
        """'[n]. Clause [X.X.X] - [konu]' bloklari -> [(n, madde, konu, metin)]."""
        out = []
        rx = re.compile(r'^\s*(\d+)\.\s*Clause\s+([\d.]+?)\.?\s*[-–—:]\s*(.*)$', re.M)
        ms = list(rx.finditer(text or ''))
        for k, m in enumerate(ms):
            end = ms[k + 1].start() if k + 1 < len(ms) else len(text)
            out.append((int(m.group(1)), m.group(2), m.group(3).strip(), text[m.end():end].strip()))
        return out

    def ai_tr_responses(self):
        p = self.project['profile']
        comments = self.tr_in.get('1.0', 'end-1c').strip()
        if not comments:
            messagebox.showinfo('Technical review', 'Paste the reviewer\'s comments on the left first.', parent=self)
            return
        refs = []
        for m in re.finditer(r'\b(\d{1,2}(?:\.\d{1,2}){1,3})\b', comments):
            sec = F.section_for_clause(self.project['sections'], m.group(1))
            if sec and sec not in refs:
                refs.append(sec)
        parts = ['TECHNICAL REVIEWER COMMENTS:\n' + comments]
        for sec in refs[:12]:
            row = next(r for r in self.project['sections'] if r['clause'] == sec)
            block = ['SECTION %s %s - CURRENT REPORT TEXT:\n%s' % (sec, row.get('title') or '', F.with_closing(self.project, row) or '(empty)')]
            ev = self.ai_source(row)
            if ev.strip():
                block.append('AUDITOR EVIDENCE:\n' + ev)
            parts.append('\n'.join(block))
        if not refs:
            fields = ['%s: %s' % (f['label'], self._value_of(f)) for f in self.fields if self._value_of(f)]
            parts.append('REPORT FIELDS:\n' + '\n'.join(fields[:120]))
        instruction = (RP.pack(p)['skill'][:9000] + '\n\n---\nTASK: Answer every numbered technical-review comment above, in order, '
                       'using ONLY the report text and auditor evidence supplied. For each item write the heading line exactly as '
                       '"[n]. Clause [X.X.X] - [short subject]" followed by report-ready paragraph(s) in English. When the evidence '
                       'does not contain the requested detail, write "No records were provided for [subject]." Never invent '
                       'evidence and never create, strengthen or weaken a non-conformity. No notes, no markdown.')
        src = '\n\n'.join(parts)

        def done(text, model):
            self.tr_out.delete('1.0', 'end')
            self.tr_out.insert('1.0', text)
            self.project['meta'].setdefault('flags', {})['tr_responses'] = text
            self.mark_dirty()
            self.app.flash('%d responses drafted by %s.' % (len(self.parse_responses(text)), model), 8000)
        self.app.brcgs_ai_call('BRCGS technical-review responses', instruction, src, done)

    def apply_tr_response(self):
        items = self.parse_responses(self.tr_out.get('1.0', 'end-1c'))
        if not items:
            messagebox.showinfo('Responses', 'No responses in the "[n]. Clause X.X.X - subject" format were found.', parent=self)
            return
        win = tk.Toplevel(self)
        win.title('Apply a response to its section')
        win.configure(bg=self.c['PANEL'], padx=12, pady=10)
        win.transient(self)
        lb = tk.Listbox(win, height=min(14, len(items)), width=90)
        for n, cl, subj, _t in items:
            sec = F.section_for_clause(self.project['sections'], cl)
            lb.insert('end', '%d. Clause %s - %s   →  section %s' % (n, cl, subj[:50], sec or '(none)'))
        lb.pack(fill='both', expand=True)
        lb.selection_set(0)

        def apply(mode):
            sel = lb.curselection()
            if not sel:
                return
            n, cl, subj, txt = items[sel[0]]
            sec = F.section_for_clause(self.project['sections'], cl)
            row = next((r for r in self.project['sections'] if r['clause'] == sec), None)
            if row is None:
                messagebox.showinfo('Responses', 'Clause %s is not a section of this report.' % cl, parent=win)
                return
            self.store.snapshot(self.uid, 'pre-tr-response-%s' % sec, self.project)
            cur = str(row.get('value') or '').rstrip()
            G.set_report_text(self.project['profile'], row, txt if mode == 'replace' or not cur else cur + '\n\n' + txt)
            self.mark_dirty()
            self.app.flash('Response %d applied to section %s (%s).' % (n, sec, 'replaced' if mode == 'replace' else 'appended'))
        bar = tk.Frame(win, bg=self.c['PANEL'])
        bar.pack(fill='x', pady=(8, 0))
        self.app.btn(bar, 'Append to the section text', lambda: apply('append'), 'primary')
        self.app.btn(bar, 'Replace the section text', lambda: apply('replace'), 'ghost')
        self.app.btn(bar, 'Close', win.destroy, 'ghost', side='right')
        self.tr_apply_win = win

    def _page_history(self):
        c = self.c
        body = self._scroll()
        blk = self._block(body, 'Version history', 'A snapshot is taken automatically before every save. The last %d versions are kept. Returning to a version also '
                                                'creates a snapshot.' % S.REVISION_LIMIT)
        revs = self.store.revisions(self.uid)
        if not revs:
            tk.Label(blk, text='No versions yet (created after the first save).', fg=c['MUTED'], bg=c['PANEL']).pack(anchor='w')
        for r in revs:
            row = tk.Frame(blk, bg=c['PANEL'])
            row.pack(fill='x', pady=1)
            tk.Label(row, text='%s   ·   %s   ·   %d filled sections   ·   %.1f KB' % (r['created_at'], r.get('label') or '', r.get('filled') or 0,
                                                                              r['size'] / 1024.0), fg=c['FG'], bg=c['PANEL'],
                     font=('Segoe UI', 9), anchor='w').pack(side='left')
            self.app.btn(row, 'Return to this version', lambda rid=r['id']: self.restore_revision(rid), 'ghost', side='right')

    def restore_revision(self, rid):
        if self.dirty and not messagebox.askyesno('Return to version', 'Unsaved changes will be lost. Continue?', parent=self):
            return
        self.project = self.store.restore_revision(self.uid, rid)
        self._mark_clean()
        self.show('history')
        self.app.flash('Version restored.')

    # ------------------------------------------------------------------ kaydet / disa aktar
    def save(self, force=False):
        wrote_err = None
        if (self.project.get('meta') or {}).get('linked_docx'):
            try:
                self.store.write_linked(self.project)
            except PermissionError:
                wrote_err = ('The file is open in Word, so it could not be updated:\n%s\n\nClose it in Word and save again. '
                             'Your changes are saved in the report.' % self.project['meta']['linked_docx'])
            except Exception as e:
                wrote_err = 'The linked DOCX could not be updated:\n%s' % e
        try:
            self.project = self.store.save(self.project, force=force)
        except S.GuardError as e:
            if messagebox.askyesno('Save stopped', '%s\n\nOverwrite anyway? (The previous state stays in the version history.)' % e,
                                   icon='warning', parent=self):
                return self.save(force=True)
            return False
        except OSError as e:
            messagebox.showerror('Could not save', str(e), parent=self)
            return False
        self._mark_clean()
        self._refresh_header()
        if wrote_err:
            messagebox.showwarning('Linked DOCX', wrote_err, parent=self)
        else:
            linked = self.project['meta'].get('linked_docx')
            self.app.flash('Report saved: %s%s' % (self.project['title'], (' → ' + os.path.basename(linked)) if linked else ''))
        return True

    def save_and_close(self):
        if self.save() is not False:
            self.app.close_brcgs_view(self, ask=False)

    def export_docx(self):
        if self.dirty and not self.save():
            return
        chk = S.export_check(self.project)
        clean = re.sub(r'[\\/:*?"<>|]+', ' ', self.project['title']).strip(' .') or 'BRCGS report'
        path = filedialog.asksaveasfilename(parent=self, title='Write DOCX (official template)', initialfile=clean + '.docx',
                                            defaultextension='.docx', filetypes=[('Word document', '*.docx')])
        if not path:
            return
        try:
            _blob, st = self.store.export_docx(self.project, path)
        except Exception as e:
            messagebox.showerror('Could not write the DOCX', str(e), parent=self)
            return
        msg = ['Official template filled: %s' % os.path.basename(path), '',
               '%d fields · %d report boxes · %d NA rows · %d tables · %d NC rows' % (st['fields'], st['boxes'], st['na_rows'], st['tables'],
                                                                                   st['actions'] + st['critical']),
               'Filled sections: %d / %d' % (chk['units_filled'], chk['units_total'])]
        if chk['merged_boxes']:
            msg.append('Merged boxes: ' + ', '.join('%s (%s)' % (t, '+'.join(v[:4]) + ('…' if len(v) > 4 else ''))
                                                           for t, v in list(chk['merged_boxes'].items())[:6]))
        if chk['skipped']:
            msg.append('⚠ Not written because the template has no box for them: ' + ', '.join(chk['skipped']))
        if not self.project['meta'].get('linked_docx'):
            self.project['meta']['linked_docx'] = os.path.abspath(path)
            self.project['meta']['linked_sig'] = S.file_sig(path)
            self.project = self.store.save(self.project, force=True)
            self._refresh_header()
            msg += ['', 'The report is now linked to this file: Save writes straight into it.']
        msg += ['', 'Open the file in Word?']
        if messagebox.askyesno('DOCX written', '\n'.join(msg), parent=self):
            self.app._open_external(path)

    # ------------------------------------------------------------------ Excel
    def save_excel_template(self):
        src = D.excel_template_path(self.project['profile'])
        path = filedialog.asksaveasfilename(parent=self, title='Save Excel template', initialfile=src.name, defaultextension='.xlsx',
                                            filetypes=[('Excel', '*.xlsx')])
        if path:
            shutil.copyfile(str(src), path)
            self.app.flash('Excel template saved: %s' % path)

    def import_excel(self):
        path = filedialog.askopenfilename(parent=self, title='Filled Excel form', filetypes=[('Excel', '*.xlsx')])
        if not path:
            return
        try:
            from agfo_brcgs import xlsx_reader as X
            parsed = X.parse(path)
        except Exception as e:
            messagebox.showerror('Excel import failed', str(e), parent=self)
            return
        self.apply_excel(parsed, os.path.basename(path))

    def plan_excel(self, parsed):
        """editor.js planExcelImport(): her Excel yanitini bir alt madde kutusuna esler; henuz hicbir sey degismez."""
        plan = {'items': [], 'skipped': [], 'legacy': 0, 'conflicts': 0, 'clauses': set(), 'answers': 0, 'notes': 0, 'new_rows': {},
                'add_modules': set()}
        pp = self.project['profile']
        xp = D.norm_profile(parsed.get('profile')) if parsed.get('profile') else ''
        if xp and xp != pp:
            plan['error'] = ('This Excel form is for the %s standard but the open report is %s. Use the right template or open the matching report.'
                             % (xp.upper(), pp.upper()))
            return plan
        rows = parsed.get('rows') or []
        if not rows:
            plan['error'] = 'No filled answers were found in the Excel file. Make sure the yellow answer column is filled.'
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
            messagebox.showerror('Excel import failed', plan['error'], parent=self)
            return 0
        if mode is None:
            lines = ['%s' % name, '', '%d sub-clauses, %d answers, %d notes / findings' % (len(plan['clauses']), plan['answers'], plan['notes'])]
            if plan['conflicts']:
                lines.append('⚠ %d boxes already contain different text in the report.' % plan['conflicts'])
            if plan['legacy']:
                lines.append('⚠ The question of %d answers is no longer on the form; they will be added to the "previously written text" box of the clause.' % plan['legacy'])
            for m in plan['add_modules']:
                lines.append('%s will be added to this report.' % (B.optional_modules(self.project['profile']).get(m) or {}).get('title', m))
            if plan['skipped']:
                lines.append('Clauses not in the report will be skipped: ' + ', '.join(plan['skipped'][:20]))
            lines += ['', 'Empty Excel cells do not change the report text. A version snapshot is taken before importing.']
            if plan['conflicts']:
                lines += ['', 'Yes: Excel overwrites · No: fill empty boxes only · Cancel: stop']
                ans = messagebox.askyesnocancel('Excel import summary', '\n'.join(lines), parent=self)
                if ans is None:
                    return 0
                mode = 'overwrite' if ans else 'fill'
            else:
                if not messagebox.askokcancel('Excel import summary', '\n'.join(lines), parent=self):
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
            self.app.flash('The Excel answers match the report; nothing changed.' + (' (%d filled boxes kept)' % kept if kept else ''))
            return 0
        self.mark_dirty()
        self.store.snapshot(self.uid, 'pre-excel-import')
        self.save()
        self.show(self.page)
        self.app.flash('Excel imported: %d boxes updated%s' % (written, (', %d filled boxes kept.' % kept) if kept else '.'))
        return written
