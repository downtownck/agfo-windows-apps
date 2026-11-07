"""2.11: Kaynak belge gezgini - Kaynaklar'a eklenen belgeler (tek tek ve klasorlerle) icin ayri sekme.

Solda: tum belgeler, klasorler (alt klasor agaciyla), tek tek eklenenler, turler, metni olmayanlar. Sagda: siralanabilir liste
(belge, tur, klasor, bolum, metin, boyut, degistirilme) ve ad / icerik aramasi. Listede secilenler AI panelindeki Kaynaklar
sohbetinin kapsami olur; belgenin kendisi uygulamanin veri modeli (app.src_docs, app.src_tree) uzerinde kalir, bu sekme
yalnizca gorunumdur.
"""
from __future__ import annotations

import hashlib
import os
import time
import tkinter as tk
from tkinter import ttk

from agfo_brcgs_view import _colors

KIND_LABELS = {'pdf': 'PDF', 'docx': 'Word', 'doc': 'Word', 'xlsx': 'Excel', 'xlsm': 'Excel', 'pptx': 'PowerPoint',
               'txt': 'Metin', 'md': 'Markdown', 'markdown': 'Markdown', 'csv': 'CSV', 'html': 'HTML', 'htm': 'HTML',
               'eml': 'E-posta', 'json': 'JSON', 'rtf': 'RTF', 'odt': 'ODT'}
SOURCES_TAB = 4        # AI panelinde Kaynaklar sekmesinin sirasi


def kind_label(kind: str) -> str:
    return KIND_LABELS.get((kind or '').lower(), (kind or '?').upper())


def _hid(*parts) -> str:
    return 'n_' + hashlib.sha1('\x00'.join(parts).encode('utf-8')).hexdigest()[:12]


def _fmt_size(n):
    if n is None:
        return '—'
    if n >= 1024 * 1024:
        return '%.1f MB' % (n / 1048576.0)
    if n >= 1024:
        return '%.0f KB' % (n / 1024.0)
    return '%d B' % n


def doc_subfolder(doc: dict) -> str:
    """Klasorle eklenen belgenin klasor icindeki yeri: 'Prosedurler/HACCP' (kok klasorun adi dahil)."""
    name = doc.get('name') or ''
    return name.rsplit('/', 1)[0] if '/' in name else ''


def doc_text(doc: dict) -> str:
    return '\n'.join(u.get('text') or '' for u in doc.get('units') or [])


def matches(doc: dict, query: str, text_lower: str | None = None) -> int:
    """Eslesme sayisi: ad eslesirse en az 1; icerikte arama aciksa (text_lower verilmisse) metindeki gecis sayisi eklenir."""
    q = (query or '').strip().casefold()
    if not q:
        return 1
    n = 1 if q in (doc.get('name') or '').casefold() else 0
    if text_lower is not None:
        n += text_lower.count(q)
    return n


class SourcesExplorer(tk.Frame):
    COLS = (('name', 'Belge', 240), ('kind', 'Tür', 70), ('folder', 'Klasör', 170), ('units', 'Bölüm', 55),
            ('chars', 'Metin', 80), ('size', 'Boyut', 70), ('mtime', 'Değiştirilme', 125), ('hits', 'Eşleşme', 65))

    def __init__(self, app, master):
        self.app = app
        self.c = _colors(app)
        super().__init__(master, bg=self.c['PANEL'])
        self.filter = ('all', None)
        self.sort = ('name', False)
        self._stat = {}             # did -> (boyut, degistirilme)
        self._text = {}             # did -> kucuk harf metin (icerik aramasi)
        self._nodes = {}            # sol agac dugumu -> suzgec
        self._syncing = False
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ arayuz
    def _build(self):
        c = self.c
        head = tk.Frame(self, bg=c['PANEL'], padx=12, pady=8)
        head.pack(fill='x')
        tk.Label(head, text='📚  Kaynak Belgeler', fg=c['FG'], bg=c['PANEL'], font=('Segoe UI', 13, 'bold')).pack(side='left')
        tk.Label(head, text='  seçtikleriniz Kaynaklar sohbetinin kapsamı olur', fg=c['MUTED'], bg=c['PANEL'],
                 font=('Segoe UI', 9)).pack(side='left')
        top = tk.Frame(self, bg=c['PANEL'], padx=12, pady=4)
        top.pack(fill='x')
        self.q = tk.StringVar()
        self.in_text = tk.BooleanVar(value=bool(self.app.settings.get('src_search_text', True)))
        e = ttk.Entry(top, textvariable=self.q, width=24)
        e.pack(side='right', fill='x', expand=True)
        e.bind('<KeyRelease>', lambda ev: self.refresh_list())
        self.search_entry = e
        tk.Label(top, text='🔍', fg=c['MUTED'], bg=c['PANEL']).pack(side='right', padx=(10, 2))
        ttk.Checkbutton(top, text='İçerikte de ara', variable=self.in_text, command=self._in_text_changed).pack(side='right', padx=6)
        self.app.btn(top, '＋ Belge ekle', self.app.add_sources, 'primary')
        self.app.btn(top, '📁 Klasör ekle', self.app.add_source_folder, 'normal')
        self.app.btn(top, 'Kaldır', self.remove_selected, 'ghost')
        self.info = tk.Label(self, text='', fg=c['MUTED'], bg=c['PANEL'], font=('Segoe UI', 9), anchor='w', justify='left')
        self.info.pack(side='bottom', fill='x', padx=12, pady=(0, 6))
        self.info.bind('<Configure>', lambda e: self.info.configure(wraplength=max(200, e.width - 10)))
        body = ttk.PanedWindow(self, orient='horizontal')
        body.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        self.body = body
        side = tk.Frame(body, bg=c['PANEL'])
        self.tree_side = ttk.Treeview(side, show='tree', selectmode='browse', height=20)
        sys_ = ttk.Scrollbar(side, orient='vertical', command=self.tree_side.yview)
        self.tree_side.configure(yscrollcommand=sys_.set)
        sys_.pack(side='right', fill='y')
        self.tree_side.pack(fill='both', expand=True)
        self.tree_side.bind('<<TreeviewSelect>>', self._side_pick)
        self.tree_side.bind('<Button-3>', self._side_context)
        body.add(side, weight=1)
        main = tk.Frame(body, bg=c['PANEL'])
        body.add(main, weight=5)
        self.tv = ttk.Treeview(main, columns=[k for k, _l, _w in self.COLS], show='headings', selectmode='extended')
        for key, label, width in self.COLS:
            self.tv.heading(key, text=label, command=lambda k=key: self._sort_by(k))
            self.tv.column(key, width=int(width * getattr(self.app, 'scale', 1)),
                           anchor='w' if key in ('name', 'folder') else ('e' if key in ('chars', 'size') else 'center'),
                           stretch=key in ('name', 'folder'))
        self.tv.tag_configure('warn', foreground=c.get('WARN', '#e2b356'))
        ys = ttk.Scrollbar(main, orient='vertical', command=self.tv.yview)
        xs = ttk.Scrollbar(main, orient='horizontal', command=self.tv.xview)
        self.tv.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        xs.pack(side='bottom', fill='x')
        ys.pack(side='right', fill='y')
        self.tv.pack(fill='both', expand=True)
        self._sash_done = False
        body.bind('<Configure>', self._initial_sash, add='+')
        self.tv.bind('<Double-1>', lambda e: self.show_selected())
        self.tv.bind('<Return>', lambda e: self.show_selected())
        self.tv.bind('<Delete>', lambda e: self.remove_selected())
        self.tv.bind('<Button-3>', self._context)
        self.tv.bind('<<TreeviewSelect>>', lambda e: self._sync_scope())

    def _initial_sash(self, e=None):
        """Sol agacin ilk genisligi; pencere gercek boyutunu alinca bir kez (o ana kadar genislik 1 px olur)."""
        if self._sash_done or self.body.winfo_width() < 400:
            return
        self._sash_done = True
        want = min(int(240 * getattr(self.app, 'scale', 1)), self.body.winfo_width() // 3)
        self.after_idle(lambda: self.body.sashpos(0, want) if self.body.winfo_exists() else None)

    # ------------------------------------------------------------------ veri
    def docs(self) -> dict:
        return self.app.src_docs

    def _stat_of(self, did, doc):
        if did not in self._stat:
            try:
                st = os.stat(doc['path'])
                self._stat[did] = (st.st_size, st.st_mtime)
            except OSError:
                self._stat[did] = (None, None)
        return self._stat[did]

    def _text_of(self, did, doc):
        if did not in self._text:
            self._text[did] = doc_text(doc).casefold()
        return self._text[did]

    def _in_filter(self, doc) -> bool:
        kind, val = self.filter
        if kind == 'all':
            return True
        if kind == 'single':
            return not doc.get('folder')
        if kind == 'kind':
            return kind_label(doc.get('kind')) == val
        if kind == 'warn':
            return bool(doc.get('empty_pages')) or doc.get('chars', 0) == 0
        if kind == 'folder':
            root, sub = val
            if os.path.normcase(doc.get('folder') or '') != os.path.normcase(root):
                return False
            here = doc_subfolder(doc)
            return not sub or here == sub or here.startswith(sub + '/')
        return True

    def rows(self):
        q = self.q.get().strip()
        deep = bool(self.in_text.get())
        out = []
        for did, doc in self.docs().items():
            if not self._in_filter(doc):
                continue
            hits = matches(doc, q, self._text_of(did, doc) if (q and deep) else None)
            if q and not hits:
                continue
            size, mtime = self._stat_of(did, doc)
            out.append({'id': did, 'name': doc['name'].rsplit('/', 1)[-1], 'kind': kind_label(doc.get('kind')),
                        'folder': doc_subfolder(doc) or ('—' if not doc.get('folder') else ''), 'units': len(doc['units']),
                        'chars': doc.get('chars', 0), 'size': size, 'mtime': mtime, 'hits': hits if q else None,
                        'warn': bool(doc.get('empty_pages')) or doc.get('chars', 0) == 0})
        key, rev = self.sort
        num = key in ('units', 'chars', 'size', 'mtime', 'hits')
        out.sort(key=lambda r: (r[key] or 0) if num else str(r[key] or '').casefold(), reverse=rev)
        return out

    # ------------------------------------------------------------------ cizim
    def refresh(self):
        """Sol agaci ve listeyi yeniden kurar (belge eklenince / kaldirilinca uygulama cagirir)."""
        alive = set(self.docs())
        for cache in (self._stat, self._text):
            for k in [k for k in cache if k not in alive]:
                cache.pop(k, None)
        self._build_side()
        self.refresh_list()

    def _build_side(self):
        docs = list(self.docs().values())
        ts = self.tree_side
        sel = ts.selection()
        ts.delete(*ts.get_children())
        self._nodes = {'all': ('all', None)}
        ts.insert('', 'end', iid='all', text='📚  Tüm belgeler  (%d)' % len(docs), open=True)
        folders = list(getattr(self.app, 'src_folders', {}).values())
        if folders:
            fg = ts.insert('', 'end', iid='grp_dir', text='KLASÖRLER', open=True)
            self._nodes['grp_dir'] = ('all', None)
            for f in folders:
                root = f['root']
                mine = [d for d in docs if os.path.normcase(d.get('folder') or '') == os.path.normcase(root)]
                rid = _hid('dir', root)
                ts.insert(fg, 'end', iid=rid, text='📁  %s  (%d)' % (os.path.basename(root.rstrip('\\/')) or root, len(mine)),
                          open=False)
                self._nodes[rid] = ('folder', (root, ''))
                counts = {}
                for d in mine:
                    parts = doc_subfolder(d).split('/')[1:]          # kok adini at
                    for i in range(1, len(parts) + 1):
                        counts['/'.join(parts[:i])] = counts.get('/'.join(parts[:i]), 0) + 1
                rootname = (mine[0]['name'].split('/', 1)[0]) if mine else os.path.basename(root.rstrip('\\/'))
                for sub in sorted(counts, key=lambda s: s.casefold()):
                    parent = rid if '/' not in sub else _hid('sub', root, sub.rsplit('/', 1)[0])
                    nid = _hid('sub', root, sub)
                    if not ts.exists(parent):
                        parent = rid
                    ts.insert(parent, 'end', iid=nid, text='📂  %s  (%d)' % (sub.rsplit('/', 1)[-1], counts[sub]))
                    self._nodes[nid] = ('folder', (root, rootname + '/' + sub))
        singles = [d for d in docs if not d.get('folder')]
        if singles:
            ts.insert('', 'end', iid='single', text='📄  Tek tek eklenenler  (%d)' % len(singles))
            self._nodes['single'] = ('single', None)
        kinds = {}
        for d in docs:
            kinds[kind_label(d.get('kind'))] = kinds.get(kind_label(d.get('kind')), 0) + 1
        if kinds:
            kg = ts.insert('', 'end', iid='grp_kind', text='TÜRLER', open=True)
            self._nodes['grp_kind'] = ('all', None)
            for k in sorted(kinds, key=str.casefold):
                nid = _hid('kind', k)
                ts.insert(kg, 'end', iid=nid, text='%s  (%d)' % (k, kinds[k]))
                self._nodes[nid] = ('kind', k)
        warn = sum(1 for d in docs if d.get('empty_pages') or d.get('chars', 0) == 0)
        if warn:
            ts.insert('', 'end', iid='warn', text='⚠  Metni eksik olanlar  (%d)' % warn)
            self._nodes['warn'] = ('warn', None)
        # secili dugum kaybolduysa (belge kaldirildi) tumune don
        pick = next((i for i in sel if ts.exists(i)), None)
        if pick is None:
            self.filter = ('all', None)
            pick = 'all'
        self._syncing = True
        try:
            ts.selection_set(pick)
        finally:
            self.after_idle(self._end_sync)

    def _end_sync(self):
        self._syncing = False

    def refresh_list(self):
        keep = set(self.tv.selection())
        self.tv.delete(*self.tv.get_children())
        rows = self.rows()
        for r in rows:
            self.tv.insert('', 'end', iid=r['id'], tags=('warn',) if r['warn'] else (), values=(
                ('⚠ ' if r['warn'] else '') + r['name'], r['kind'], r['folder'], r['units'],
                '{:,}'.format(r['chars']).replace(',', '.'), _fmt_size(r['size']),
                time.strftime('%Y-%m-%d %H:%M', time.localtime(r['mtime'])) if r['mtime'] else '—',
                '' if r['hits'] is None else r['hits']))
        cols = [k for k, _l, _w in self.COLS if k != 'hits' or self.q.get().strip()]
        self.tv.configure(displaycolumns=cols)          # eslesme sutunu yalniz aramada
        again = [i for i in keep if self.tv.exists(i)]
        if again:
            self._syncing = True
            self.tv.selection_set(again)
            self.after_idle(self._end_sync)
        total = len(self.docs())
        chars = sum(r['chars'] for r in rows)
        q = self.q.get().strip()
        head = ('%d / %d belge' % (len(rows), total)) if len(rows) != total else '%d belge' % total
        if not total:
            txt = 'Henüz belge yok. “＋ Belge ekle” ya da “📁 Klasör ekle” ile ekleyin (OneDrive / Google Drive klasörleri de olur).'
        else:
            txt = '%s · %s karakter metin%s · çift tık: metni göster · sağ tık: daha fazla · Delete: Kaynaklar\'dan kaldır' % (
                head, '{:,}'.format(chars).replace(',', '.'), (' · “%s” %s' % (q, 'adda ve içerikte' if self.in_text.get()
                                                                                    else 'adda')) if q else '')
        self.info.configure(text=txt)

    # ------------------------------------------------------------------ olaylar
    def _in_text_changed(self):
        self.app.settings['src_search_text'] = bool(self.in_text.get())
        self.refresh_list()

    def _side_pick(self, _e=None):
        if self._syncing:
            return
        sel = self.tree_side.selection()
        if not sel:
            return
        new = self._nodes.get(sel[0], ('all', None))
        if new != self.filter:
            self.filter = new
            self.tv.selection_remove(*self.tv.selection())
            self.refresh_list()
            self._sync_scope(all_visible=True)

    def _sort_by(self, key):
        cur, rev = self.sort
        self.sort = (key, not rev if cur == key else key in ('units', 'chars', 'size', 'mtime', 'hits'))
        self.refresh_list()

    def selected(self):
        return [i for i in self.tv.selection() if i in self.docs()]

    def _sync_scope(self, all_visible=False):
        """Listede secilenler (ya da sol agacta secilen klasorun / turun belgeleri) Kaynaklar sohbetinin kapsami olur."""
        if self._syncing:
            return
        ids = self.selected()
        if not ids and all_visible and self.filter[0] != 'all':
            ids = list(self.tv.get_children())
        st = self.app.src_tree
        st.selection_remove(*st.selection())
        live = [i for i in ids if st.exists(i)]
        if live:
            st.selection_set(live)
            st.see(live[0])
        self.app._switch_scope()

    def _context(self, e):
        row = self.tv.identify_row(e.y)
        if row and row not in self.tv.selection():
            self.tv.selection_set(row)
        ids = self.selected()
        m = tk.Menu(self, tearoff=0)
        st = 'normal' if ids else 'disabled'
        m.add_command(label='Bu belgelerle sohbet et (Kaynaklar)', command=self.chat_selected, state=st)
        m.add_command(label='Metni göster', command=self.show_selected, state='normal' if len(ids) == 1 else 'disabled')
        m.add_command(label='Özgün dosyayı editörde aç', command=self.open_original, state=st)
        m.add_command(label='Dosya konumunu aç', command=self.open_location, state='normal' if len(ids) == 1 else 'disabled')
        m.add_command(label='Yolu kopyala', command=self.copy_paths, state=st)
        m.add_separator()
        m.add_command(label='Kaynaklar\'dan kaldır (dosya silinmez)', command=self.remove_selected, state=st)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def _side_context(self, e):
        node = self.tree_side.identify_row(e.y)
        f = self._nodes.get(node)
        if not f or f[0] != 'folder' or f[1][1]:
            return
        root = f[1][0]
        m = tk.Menu(self, tearoff=0)
        m.add_command(label='Klasörü yeniden tara (yeni / değişen belgeler)', command=lambda: self.app.add_source_folder(root))
        m.add_command(label='Klasörü aç', command=lambda: self.app._open_external(root))
        m.add_command(label='Klasörü Kaynaklar\'dan kaldır', command=lambda: self.remove_folder(root))
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    # ------------------------------------------------------------------ islemler
    def chat_selected(self):
        self._sync_scope(all_visible=True)
        app = self.app
        if str(app.side_panel) not in app.paned.panes():
            app.toggle_ai_panel()
        app.ai_nb.select(SOURCES_TAB)
        try:
            app.src_q.focus_set()
        except tk.TclError:
            pass

    def show_selected(self):
        ids = self.selected()
        if len(ids) != 1:
            return None
        st = self.app.src_tree
        st.selection_set(ids[0])
        return self.app.show_selected_source()

    def open_original(self):
        last = None
        for i in self.selected():
            last = self.app.open_path(self.docs()[i]['path'])
        return last

    def open_location(self):
        ids = self.selected()
        if ids:
            self.app._open_external(os.path.dirname(self.docs()[ids[0]]['path']))

    def copy_paths(self):
        paths = [self.docs()[i]['path'] for i in self.selected()]
        if paths:
            self.clipboard_clear()
            self.clipboard_append('\n'.join(paths))
            self.app.flash('%d yol kopyalandı.' % len(paths))

    def remove_selected(self):
        ids = self.selected()
        if not ids:
            return
        st = self.app.src_tree
        st.selection_set([i for i in ids if st.exists(i)])
        self.app.remove_sources()

    def remove_folder(self, root):
        fid = self.app._folder_iid(root)
        if self.app.src_tree.exists(fid):
            self.app._remove_folder(fid)
            self.app._source_summary()
            self.app._switch_scope()
            self.app.sources_changed()
