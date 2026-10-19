# -*- coding: utf-8 -*-
"""AGFO AI Editor 1.4 - bicimli metin duzenleyici (Tk Text uzerine).

Tk'nin kendi geri al yigini bicimleri ve resimleri geri getirmez; bu yuzden Text komutu Tcl duzeyinde
yonlendirilir (insert / delete / image create / tag add-remove) ve her degisiklik bicimleriyle birlikte
kaydedilir. Geri al / yinele bicim, liste, tablo ve resimleri de geri getirir.

Belge yapisi Text icinde:
  * her satir bir paragraftir; paragraf etiketleri (h1, li_b, tbl ...) satirin tamamina ve satir sonuna uygulanir;
    bir satirin bicimi, satir sonu karakterindeki etiketlerden okunur.
  * karakter etiketleri: b, i, u, c_RRGGBB; yazi tipi etiketi F_<stil>_<b><i> bunlardan turetilir.
  * liste isaretleri ("• ", "1. ") satir basinda 'lm' etiketli gercek metindir.
  * tablo satirlari: hucreler sekme (\\t) ile ayrilir; 'tbl' + 'tb_<n>' etiketleri.
  * resimler: kendi satirinda gomulu goruntu; veriler self.images[ad] icinde.
"""
from __future__ import annotations

import io
import re
import time
import tkinter as tk
import uuid
from tkinter import font as tkfont

import agfo_richdoc as R

STYLE_TAGS = ('h1', 'h2', 'h3', 'quote')
LIST_TAGS = ('li_b', 'li_n')
LEVEL_TAGS = ('lvl0', 'lvl1', 'lvl2', 'lvl3')
ALIGN_TAGS = ('al_center', 'al_right', 'al_justify')
PARA_FIXED = set(STYLE_TAGS + LIST_TAGS + LEVEL_TAGS + ALIGN_TAGS + ('tbl', 'pb'))
CHAR_FIXED = {'b', 'i', 'u'}
TRANSIENT = {'sel', 'found', 'ai_new', 'hover', 'md_h', 'md_mark', 'md_li', 'fmt_flash', 'pairhl', 'trwork', 'trdone'}
ERR_MARK = '\x01AGFOERR\x01'
ERR_MARK_TCL = '\\x01AGFOERR\\x01'
BULLETS = ('• ', '◦ ', '▪ ', '▫ ')
STYLE_SCALE = {'normal': 1.0, 'h1': 1.6, 'h2': 1.35, 'h3': 1.15, 'quote': 1.0}
PAGE_COLORS = {'bg': '#ffffff', 'fg': '#1b1b1b', 'sel': '#b9d7f7', 'insert': '#1b1b1b', 'h1': '#1f3864', 'h2': '#2f5496',
               'quote': '#4a4a4a', 'marker': '#55606e', 'tbl': '#f2f5f9', 'desk': '#5c6676'}


def is_para_tag(t):
    return t in PARA_FIXED or t.startswith('tb_')


def is_char_tag(t):
    return t in CHAR_FIXED or t.startswith('c_')


def recorded(t):
    return t not in TRANSIENT and not t.startswith('ais_') and not t.startswith('aie_')


class _LineTrack(list):
    """get_blocks icin: eklenen her blogun satir araligini yan listeye yazar."""
    def __init__(self, lines):
        super().__init__()
        self.lines = lines
        self.line = 0

    def append(self, blk):
        super().append(blk)
        if self.lines is not None:
            self.lines.append([self.line, self.line])

    def extend_last(self, ln):
        if self.lines is not None and self.lines:
            self.lines[-1][1] = ln


class RichText(tk.Text):
    """Bicimli metin. rich=False ise (duz .txt) ayni geri al sistemiyle duz metin duzenleyici gibi calisir."""

    def __init__(self, master, colors, family='Segoe UI', size=12, rich=True, **kw):
        kw['undo'] = False
        super().__init__(master, **kw)
        self.colors = colors
        self.rich = rich
        self.family, self.size = family, size
        self.zoom = 1.0
        self.page_mode = False
        self.images = {}          # gomulu resim adi -> img blogu (data, ext, w, h, align)
        self._photos = {}         # ad -> PhotoImage (cop toplanmasin)
        self._fonts = {}
        self._tb_seq = 0
        self.typing_fmt = None    # (imlec, {'b':..}) - secim yokken arac cubugundan secilen bicim
        self.clip = None          # (duz_metin, bloklar) - ic pano
        self.on_change = None
        self.undo = UndoManager(self)
        self._orig = self._w + '_agfo'
        self.tk.call('rename', self._w, self._orig)
        # Python komutu hata FIRLATMAZ (Tkinter firlatilan hatayi saklayip mainloop'u durdurur); hatayi isaretli metin
        # olarak doner, Tcl sarmalayici bunu gercek Tcl hatasina cevirir. Boylece Tk'nin 'catch' kullanan baglari ve
        # Python'daki try/except TclError dogru calisir, uygulama cokmez.
        self._py = self._w + '_agfo_py'
        self.tk.createcommand(self._py, self._dispatch_safe)
        self.tk.call('proc', self._w, 'args',
                     'set r [%s {*}$args]\n'
                     'if {[string first "%s" $r] == 0} {return -code error [string range $r %d end]}\n'
                     'return $r' % (self._py, ERR_MARK_TCL, len(ERR_MARK)))
        self.configure_tags()
        self.rich = False
        if rich:
            self.enable_rich()

    def enable_rich(self):
        """Duz metin belgesini bicimli duzenlemeye acar (klavye kisayollari, liste/tablo davranisi)."""
        if self.rich:
            return
        self.rich = True
        self.bind('<KeyPress>', self._on_key)
        self.bind('<Return>', self._on_return)
        self.bind('<KP_Enter>', self._on_return)
        self.bind('<BackSpace>', self._on_backspace)
        self.bind('<Delete>', self._on_delete)
        self.bind('<Tab>', self._on_tab)
        self.bind('<Shift-Tab>', lambda e: self._on_tab(e, back=True))
        self.bind('<ISO_Left_Tab>', lambda e: self._on_tab(e, back=True))
        for k, tag in (('b', 'b'), ('i', 'i'), ('u', 'u')):
            self.bind('<Control-%s>' % k, lambda e, t=tag: (self.toggle_char(t), 'break')[1])
            self.bind('<Control-%s>' % k.upper(), lambda e, t=tag: (self.toggle_char(t), 'break')[1])
        self.bind('<<Paste>>', self._on_paste)
        self.bind('<<Copy>>', self._on_copy, add='+')
        self.bind('<<Cut>>', self._on_cut)
        self.bind('<ButtonRelease-1>', lambda e: self._clear_typing(), add='+')

    # ================================================================ Tcl yonlendirme
    def _call(self, *args):
        r = self.tk.call((self._orig,) + args)
        return r if isinstance(r, (str, tuple, int, float)) else str(r)

    def _dispatch_safe(self, *args):
        try:
            return self._dispatch(*args)
        except tk.TclError as e:
            return ERR_MARK + str(e)
        except Exception as e:  # beklenmeyen hata: editor calismaya devam etsin
            import traceback
            self._last_error = traceback.format_exc()
            return ERR_MARK + 'AGFO editor: %r' % (e,)

    def _dispatch(self, op, *args):
        if op == 'insert' and self.undo.recording:
            return self._rec_insert(*args)
        if op == 'delete' and self.undo.recording:
            return self._rec_delete(*args)
        if op == 'replace' and self.undo.recording and len(args) >= 3:
            self.undo.begin()
            try:
                s = self._call('index', args[0])
                self._rec_delete(args[0], args[1])
                return self._rec_insert(s, *args[2:])
            finally:
                self.undo.end()
        if op == 'image' and args and args[0] == 'create' and self.undo.recording:
            idx = self._norm(args[1])
            name = self._call('image', 'create', idx, *args[2:])
            self.undo.record(('ins', idx, self._call('index', idx + '+1c'), self._dump(idx, idx + '+1c')))
            return name
        if op == 'tag' and args and args[0] in ('add', 'remove') and len(args) >= 3 and recorded(str(args[1])) and self.undo.recording:
            return self._rec_tag(args[0], str(args[1]), args[2:])
        if op == 'edit' and args:
            sub = args[0]
            if sub == 'undo':
                self.undo.undo()
                return ''
            if sub == 'redo':
                self.undo.redo()
                return ''
            if sub == 'separator':
                self.undo.separator()
                return ''
            if sub == 'reset':
                self.undo.reset()
                return ''
        return self._call(op, *args)

    def _norm(self, index):
        idx = self._call('index', index)
        if self._call('compare', idx, '>=', 'end'):
            idx = self._call('index', 'end-1c')
        return idx

    def _rec_insert(self, index, *args):
        idx = self._norm(index)
        total = sum(len(str(args[k])) for k in range(0, len(args), 2))
        self._call('insert', idx, *args)
        if total:
            end = self._call('index', '%s+%dc' % (idx, total))
            self.undo.record(('ins', idx, end, self._dump(idx, end)))
        return ''

    def _rec_delete(self, i1, i2=None, *more):
        if more:
            self.undo.reset()
            return self._call('delete', i1, i2, *more)
        s = self._call('index', i1)
        e = self._call('index', i2) if i2 is not None else self._call('index', s + '+1c')
        last = self._call('index', 'end-1c')
        if self._call('compare', e, '>', last):
            e = last
        if not self._call('compare', s, '<', e):
            return ''
        content = self._dump(s, e)
        self._call('delete', s, e)
        self.undo.record(('del', s, e, content))
        return ''

    def _rec_tag(self, sub, name, rng):
        rng = list(rng)
        if len(rng) % 2:
            rng.append(None)
        self.undo.begin()
        try:
            for k in range(0, len(rng), 2):
                s = self._call('index', rng[k])
                e = self._call('index', rng[k + 1]) if rng[k + 1] is not None else self._call('index', s + '+1c')
                if not self._call('compare', s, '<', e):
                    continue
                before = self._tag_ranges_in(name, s, e)
                self._call('tag', sub, name, s, e)
                if (sub == 'add' and before == [(s, e)]) or (sub == 'remove' and not before):
                    continue                       # degisiklik yok
                self.undo.record(('tag', sub, name, s, e, before))
        finally:
            self.undo.end()
        return ''

    def _tag_ranges_in(self, name, s, e):
        out = []
        pos = s
        while True:
            r = self._call('tag', 'nextrange', name, pos, e)
            if not r:
                break
            a, b = str(r[0]), str(r[1])
            if self._call('compare', a, '<', s):
                a = s
            if self._call('compare', b, '>', e):
                b = e
            out.append((a, b))
            pos = b
            if not self._call('compare', pos, '<', e):
                break
        # aralik baslangicindan once baslayip icine uzanan etiket
        if not out or self._call('compare', out[0][0], '>', s):
            if name in [str(t) for t in self._call('tag', 'names', s)]:
                r = self._call('tag', 'prevrange', name, s + '+1c')
                if r:
                    b = str(r[1])
                    b = e if self._call('compare', b, '>', e) else b
                    out.insert(0, (s, b))
        return out

    def _dump(self, s, e):
        """[('t', metin, etiketler) | ('i', resim_adi, etiketler)] - etiketler kayitli olanlar."""
        active = {str(t) for t in self._call('tag', 'names', s) if recorded(str(t))}
        raw = self._call('dump', '-text', '-tag', '-image', s, e)
        items = []
        raw = list(raw) if isinstance(raw, (tuple, list)) else list(self.tk.splitlist(raw))
        for k in range(0, len(raw), 3):
            kind, val = str(raw[k]), raw[k + 1]
            val = str(val)
            if kind == 'tagon':
                if recorded(val):
                    active.add(val)
            elif kind == 'tagoff':
                active.discard(val)
            elif kind == 'text':
                items.append(('t', val, tuple(sorted(active))))
            elif kind == 'image':
                items.append(('i', val, tuple(sorted(active))))
        return items

    def _restore(self, index, items):
        """Kayitli icerigi (metin + etiket + resim) index'e yazar; kayit tutmaz."""
        pos = self._call('index', index)
        for kind, val, tags in items:
            if kind == 't':
                self._call('insert', pos, val, tags)
                pos = self._call('index', '%s+%dc' % (pos, len(val)))
            else:
                photo = self._photos.get(val)
                if photo is None:
                    continue
                self._call('image', 'create', pos, '-image', photo, '-name', val, '-align', 'baseline', '-padx', 2)
                for t in tags:
                    self._call('tag', 'add', t, pos)
                pos = self._call('index', pos + '+1c')
        return pos

    def destroy(self):
        try:
            super().destroy()
        finally:
            for cmd in (lambda: self.tk.call('rename', self._w, ''), lambda: self.tk.deletecommand(self._py)):
                try:
                    cmd()
                except tk.TclError:
                    pass

    def changed(self):
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass

    # ================================================================ gorunum
    def px(self, pt):
        return self.winfo_fpixels('%fp' % (pt * self.zoom))

    def font_tag(self, style, b, i):
        b, i = bool(b), bool(i)
        name = 'F_%s_%d%d' % (style, int(b), int(i))
        if name not in self._fonts:
            self._fonts[name] = (style, b, i)
            self._apply_font(name)
            self._call('tag', 'lower', name)
        return name

    def _apply_font(self, name):
        style, b, i = self._fonts[name]
        size = max(6, round(self.size * STYLE_SCALE.get(style, 1.0) * self.zoom))
        weight = 'bold' if b or style in ('h1', 'h2', 'h3') else 'normal'
        slant = 'italic' if i or style == 'quote' else 'roman'
        objs = self.__dict__.setdefault('_font_objs', {})
        f = objs.get(name)
        if f is None:
            f = objs[name] = tkfont.Font(self, family=self.family, size=size, weight=weight, slant=slant)
        else:
            f.configure(family=self.family, size=size, weight=weight, slant=slant)
        self._call('tag', 'configure', name, '-font', f)

    def set_font(self, family=None, size=None, zoom=None):
        self.family = family or self.family
        self.size = size or self.size
        if zoom:
            self.zoom = zoom
        self.configure(font=(self.family, max(6, round(self.size * self.zoom))))
        for name in self._fonts:
            self._apply_font(name)
        self.configure_tags()
        self._resize_images()

    def configure_tags(self):
        c = self.colors
        page = self.page_mode
        tc = self.tag_configure
        base = self.px(14)
        tc('h1', foreground=PAGE_COLORS['h1'] if page else '#ffffff', spacing1=self.px(16), spacing3=self.px(6))
        tc('h2', foreground=PAGE_COLORS['h2'] if page else '#e6f1ff', spacing1=self.px(12), spacing3=self.px(4))
        tc('h3', foreground=PAGE_COLORS['h1'] if page else '#dce9fb', spacing1=self.px(9), spacing3=self.px(3))
        tc('quote', foreground=PAGE_COLORS['quote'] if page else c['MUTED'], lmargin1=self.px(30), lmargin2=self.px(30),
           rmargin=self.px(30))
        for k, t in enumerate(LEVEL_TAGS):
            tc(t, lmargin1=base * (k + 0.6), lmargin2=base * (k + 0.6) + self.px(13))
        tc('li_b', spacing3=self.px(2))
        tc('li_n', spacing3=self.px(2))
        tc('lm', foreground=PAGE_COLORS['marker'] if page else c['ACCENT'])
        tc('al_center', justify='center')
        tc('al_right', justify='right')
        tc('al_justify')
        tc('b')
        tc('i')
        tc('tbl', background=PAGE_COLORS['tbl'] if page else '#13263d', spacing1=self.px(2), spacing3=self.px(2), lmargin1=self.px(4),
           lmargin2=self.px(4))
        tc('pb', spacing1=self.px(28))
        tc('u', underline=True)
        for t in self.tag_names():
            if t.startswith('c_'):
                self._color_tag(t[2:])
            elif t.startswith('tb_'):
                self._table_tabs(t)
        for t in ('lm', 'tbl'):
            self._call('tag', 'lower', t)
        for t in STYLE_TAGS + LEVEL_TAGS + ALIGN_TAGS + ('li_b', 'li_n', 'pb', 'u'):
            self._call('tag', 'raise', t)
        for t in ('trdone', 'trwork', 'found', 'ai_new', 'sel'):
            try:
                self._call('tag', 'raise', t)
            except tk.TclError:
                pass

    def _color_tag(self, hexc):
        name = 'c_' + hexc
        col = '#' + hexc
        if not self.page_mode:
            r, g, b = (int(hexc[k:k + 2], 16) for k in (0, 2, 4))
            if 0.299 * r + 0.587 * g + 0.114 * b < 110:       # koyu tema: koyu yazi rengini aciklastir
                col = '#%02x%02x%02x' % tuple(min(255, int(v + (255 - v) * 0.55)) for v in (r, g, b))
        self.tag_configure(name, foreground=col)
        return name

    def _table_tabs(self, tag):
        r = self.tag_ranges(tag)
        ncol = 1
        if r:
            line = self.get(r[0], '%s lineend' % r[0])
            ncol = line.count('\t') + 1
        width = self.px(R.CONTENT_W_PT) - self.px(8)
        step = max(40, width / ncol)
        self.tag_configure(tag, tabs=tuple(int(step * (k + 1)) for k in range(max(1, ncol - 1))) or (int(step),))

    def set_page_mode(self, on):
        self.page_mode = bool(on)
        c = self.colors
        if on:
            self.configure(bg=PAGE_COLORS['bg'], fg=PAGE_COLORS['fg'], insertbackground=PAGE_COLORS['insert'],
                           selectbackground=PAGE_COLORS['sel'], selectforeground='#000000', inactiveselectbackground='#d5e3f3',
                           padx=int(self.px(R.MARGIN_PT * 0.9)), pady=int(self.px(R.MARGIN_PT * 0.7)), spacing3=int(self.px(6)))
            self.tag_configure('found', background='#ffe58f')
            self.tag_configure('ai_new', background='#c9f2d6')
            self.tag_configure('trwork', background='#fff1b8')       # cevriliyor
            self.tag_configure('trdone', background='#d3f5dd')       # cevrildi
        else:
            self.configure(bg=c['EDIT_BG'], fg=c['FG'], insertbackground=c['ACCENT'], selectbackground=c['SEL_BG'],
                           selectforeground='#ffffff', inactiveselectbackground='#1d3b57', padx=int(28 * self.zoom),
                           pady=18, spacing3=int(self.px(6)))
            self.tag_configure('found', background='#5a4a1c')
            self.tag_configure('ai_new', background='#173a2a')
            self.tag_configure('trwork', background='#4a3f12')
            self.tag_configure('trdone', background='#173a2a')
        self.configure_tags()

    # ================================================================ satir/paragraf yardimcilari
    def lines(self, s='insert', e=None):
        a = int(self.index(s).split('.')[0])
        b = int(self.index(e or s).split('.')[0])
        if e is not None and self.compare(e, '==', '%d.0' % b) and b > a:
            b -= 1                               # secim sonraki satirin basinda bitiyorsa o satiri katma
        return range(a, b + 1)

    def para_tags(self, line):
        return {str(t) for t in self.tag_names('%d.end' % line) if is_para_tag(str(t))}

    def para_props(self, line):
        tags = self.para_tags(line)
        style = next((s for s in STYLE_TAGS if s in tags), 'normal')
        lst = 'bullet' if 'li_b' in tags else 'number' if 'li_n' in tags else None
        level = next((k for k, t in enumerate(LEVEL_TAGS) if t in tags), 0)
        align = next((a[3:] for a in ALIGN_TAGS if a in tags), None)
        return {'style': style, 'list': lst, 'level': level, 'align': align, 'pb': 'pb' in tags,
                'table': next((t for t in tags if t.startswith('tb_')), None)}

    def _para_tagset(self, props):
        tags = set()
        if props.get('style') in STYLE_TAGS:
            tags.add(props['style'])
        if props.get('list'):
            tags.add('li_b' if props['list'] == 'bullet' else 'li_n')
            tags.add(LEVEL_TAGS[min(3, props.get('level') or 0)])
        if props.get('align') in ('center', 'right', 'justify'):
            tags.add('al_' + props['align'])
        if props.get('pb'):
            tags.add('pb')
        if props.get('table'):
            tags.update(('tbl', props['table']))
        return tags

    def set_para_tags(self, line, tags):
        s, e = '%d.0' % line, '%d.end+1c' % line
        if int(self.index('end-1c').split('.')[0]) == line:
            e = '%d.end' % line
            for t in self.para_tags(line) - tags:
                self.tag_remove(t, '%d.end' % line)
            for t in tags:
                self.tag_add(t, '%d.end' % line)
        for t in self.para_tags(line) | {t for t in self.tag_names(s) if is_para_tag(str(t))}:
            if t not in tags:
                self.tag_remove(t, s, e)
        for t in tags:
            self.tag_add(t, s, e)

    def normalize_lines(self, lines):
        """Satir sonundaki paragraf etiketlerini satirin tamamina yayar (yapistirma/silme sonrasi)."""
        for ln in lines:
            self.set_para_tags(ln, self.para_tags(ln))

    def char_fmt_at(self, index):
        tags = {str(t) for t in self.tag_names(index)}
        return {'b': 'b' in tags, 'i': 'i' in tags, 'u': 'u' in tags,
                'color': next((t[2:] for t in tags if t.startswith('c_')), None)}

    def _char_tags(self, fmt):
        tags = []
        if fmt.get('b'):
            tags.append('b')
        if fmt.get('i'):
            tags.append('i')
        if fmt.get('u'):
            tags.append('u')
        if fmt.get('color'):
            tags.append(self._color_tag(fmt['color'].upper()))
        return tags

    def refresh_fonts(self, s='1.0', e='end'):
        """F_ yazi tipi etiketlerini b/i ve paragraf stiline gore yeniden kurar (yalniz farkli olanlar)."""
        for ln in self.lines(s, self.index(e + '-1c') if self.compare(e, '>', s) else s):
            style = self.para_props(ln)['style']
            ls, le = '%d.0' % ln, '%d.end+1c' % ln
            items = self._dump(ls, le)
            pos = ls
            for kind, val, tags in items:
                n = len(val) if kind == 't' else 1
                end = self._call('index', '%s+%dc' % (pos, n))
                if kind == 't':
                    want = self.font_tag(style, 'b' in tags, 'i' in tags)
                    have = [t for t in tags if t.startswith('F_')]
                    if have != [want]:
                        for t in have:
                            self.tag_remove(t, pos, end)
                        self.tag_add(want, pos, end)
                pos = end

    # ================================================================ yazma
    def _clear_typing(self):
        self.typing_fmt = None

    def typing_tags(self, index='insert'):
        """Imlecte yazilacak karakterin etiketleri: bicim (onceki karakterden) + paragraf + yazi tipi."""
        line = int(self.index(index).split('.')[0])
        if self.typing_fmt and self.compare(self.typing_fmt[0], '==', index):
            fmt = self.typing_fmt[1]
        else:
            self.typing_fmt = None
            col = int(self.index(index).split('.')[1])
            src = index + '-1c' if col > 0 and 'lm' not in self.tag_names(index + '-1c') else index
            fmt = self.char_fmt_at(src) if self.get(src) not in ('\n', '') else {}
            if 'lm' in self.tag_names(src):
                fmt = {}
        props = self.para_props(line)
        tags = self._char_tags(fmt) + sorted(self.para_tags(line))
        tags.append(self.font_tag(props['style'], fmt.get('b'), fmt.get('i')))
        return tuple(tags)

    def _on_key(self, e):
        ch = e.char
        if not ch or ord(ch[0]) < 32 or ch == '\x7f':
            if e.keysym in ('Left', 'Right', 'Up', 'Down', 'Home', 'End', 'Prior', 'Next'):
                self.typing_fmt = None
            return None
        ctrl, alt = bool(e.state & 0x4), bool(e.state & 0x20000) or bool(e.state & 0x8 and e.state & 0x4)
        if ctrl and not alt:
            return None
        self._type_text(ch)
        return 'break'

    def _type_text(self, ch):
        try:
            s, en = self.index('sel.first'), self.index('sel.last')
            self.undo.separator()
            self.delete(s, en)
            self.mark_set('insert', s)
        except tk.TclError:
            pass
        tags = self.typing_tags()
        idx = self.index('insert')
        self.insert(idx, ch, tags)
        self.mark_set('insert', '%s+%dc' % (idx, len(ch)))
        if self.typing_fmt:
            self.typing_fmt = (self.index('insert'), self.typing_fmt[1])
        self.see('insert')
        self.changed()

    def _on_return(self, e=None):
        try:
            s, en = self.index('sel.first'), self.index('sel.last')
            self.delete(s, en)
            self.mark_set('insert', s)
        except tk.TclError:
            pass
        line = int(self.index('insert').split('.')[0])
        props = self.para_props(line)
        content = self._content_start(line)
        self.undo.begin()
        try:
            if props['list'] and not self.get(content, '%d.end' % line).strip():
                self._set_list_line(line, None)            # bos liste ogesinde Enter: listeden cik
            elif props['table'] and self.compare('insert', '==', '%d.end' % line):
                ncol = self.get('%d.0' % line, '%d.end' % line).count('\t') + 1
                tags = tuple(sorted(self.para_tags(line))) + (self.font_tag('normal', False, False),)
                self.insert('%d.end' % line, '\n' + '\t' * (ncol - 1), tags)
                self.mark_set('insert', '%d.0' % (line + 1))
            else:
                tags = tuple(sorted(self.para_tags(line)))
                at_end = self.compare('insert', '==', '%d.end' % line)
                self.insert('insert', '\n', tags)
                new = line + 1
                if at_end and props['style'] in ('h1', 'h2', 'h3'):
                    p = dict(props)
                    p['style'] = 'normal'
                    p['pb'] = False
                    self.set_para_tags(new, self._para_tagset(p))
                elif props['pb']:
                    p = dict(props)
                    p['pb'] = False
                    self.set_para_tags(new, self._para_tagset(p))
                if props['list']:
                    self._insert_marker(new, props)
                    self.mark_set('insert', self._content_start(new))
                    self.renumber()
                self.refresh_fonts('%d.0' % line, '%d.end' % new)
        finally:
            self.undo.end()
        self.undo.separator()
        self.see('insert')
        self.changed()
        return 'break'

    def _content_start(self, line):
        r = self.tag_nextrange('lm', '%d.0' % line, '%d.end' % line)
        return r[1] if r and self.compare(r[0], '==', '%d.0' % line) else '%d.0' % line

    def _on_backspace(self, e=None):
        if self.tag_ranges('sel'):
            return None
        idx = self.index('insert')
        line, col = map(int, idx.split('.'))
        props = self.para_props(line)
        if props['list'] and self.compare(idx, '==', self._content_start(line)) and col > 0:
            self.undo.begin()
            try:
                self._set_list_line(line, None)
                self.renumber()
            finally:
                self.undo.end()
            self.changed()
            return 'break'
        if col == 0 and line > 1:
            prev = self.para_props(line - 1)
            if self.para_props(line)['table'] or prev['table']:
                if self.para_props(line)['table'] != prev['table']:
                    self.mark_set('insert', '%d.end' % (line - 1))
                    return 'break'
            self.undo.begin()
            try:
                keep = self._para_tagset(prev)
                marker = self.tag_nextrange('lm', '%d.0' % line, '%d.end' % line)
                if marker and self.compare(marker[0], '==', '%d.0' % line):
                    self.delete(marker[0], marker[1])
                self.delete('%d.end' % (line - 1))
                self.set_para_tags(line - 1, keep)
                self.refresh_fonts('%d.0' % (line - 1), '%d.end' % (line - 1))
                self.renumber()
            finally:
                self.undo.end()
            self.changed()
            return 'break'
        if col > 0 and 'lm' in self.tag_names(idx + '-1c'):
            return 'break'
        return None

    def _on_delete(self, e=None):
        if self.tag_ranges('sel'):
            return None
        idx = self.index('insert')
        line = int(idx.split('.')[0])
        if self.compare(idx, '==', '%d.end' % line) and self.compare(idx, '<', 'end-1c'):
            nxt = self.para_props(line + 1)
            if nxt['table'] != self.para_props(line)['table']:
                return 'break'
            self.undo.begin()
            try:
                keep = self._para_tagset(self.para_props(line))
                marker = self.tag_nextrange('lm', '%d.0' % (line + 1), '%d.end' % (line + 1))
                if marker and self.compare(marker[0], '==', '%d.0' % (line + 1)):
                    self.delete(marker[0], marker[1])
                self.delete(idx)
                self.set_para_tags(line, keep)
                self.refresh_fonts('%d.0' % line, '%d.end' % line)
                self.renumber()
            finally:
                self.undo.end()
            self.changed()
            return 'break'
        return None

    def _on_tab(self, e=None, back=False):
        line = int(self.index('insert').split('.')[0])
        props = self.para_props(line)
        if props['table']:
            text = self.get('insert', 'insert lineend') if not back else self.get('insert linestart', 'insert')
            if not back:
                k = text.find('\t')
                if k >= 0:
                    self.mark_set('insert', 'insert+%dc' % (k + 1))
                elif self.para_props(line + 1)['table'] == props['table']:
                    self.mark_set('insert', '%d.0' % (line + 1))
            else:
                k = text.rfind('\t', 0, max(0, len(text) - 1))
                self.mark_set('insert', 'insert linestart+%dc' % (k + 1) if k >= 0 else 'insert linestart')
            return 'break'
        if props['list']:
            self.change_level(-1 if back else 1)
            return 'break'
        if back:
            return 'break'
        self._type_text('\t')
        return 'break'

    # ================================================================ pano
    def _on_copy(self, e=None):
        try:
            s, en = self.index('sel.first'), self.index('sel.last')
        except tk.TclError:
            return None
        self.clip = (self.get(s, en), self.get_blocks(s, en))
        return None

    def _on_cut(self, e=None):
        try:
            s, en = self.index('sel.first'), self.index('sel.last')
        except tk.TclError:
            return 'break'
        self._on_copy()
        self.clipboard_clear()
        self.clipboard_append(self.get(s, en))
        self.undo.separator()
        self.undo.begin()
        try:
            self.delete(s, en)
            self.normalize_lines([int(s.split('.')[0])])
            self.renumber()
        finally:
            self.undo.end()
        self.changed()
        return 'break'

    def _on_paste(self, e=None):
        try:
            text = self.clipboard_get()
        except tk.TclError:
            return 'break'
        self.undo.separator()
        self.undo.begin()
        try:
            try:
                s, en = self.index('sel.first'), self.index('sel.last')
                self.delete(s, en)
                self.mark_set('insert', s)
            except tk.TclError:
                pass
            if self.clip and self.clip[0] == text and self.clip[1]:
                self.insert_blocks('insert', self.clip[1])
            else:
                self.insert_plain('insert', text)
        finally:
            self.undo.end()
        self.undo.separator()
        self.see('insert')
        self.changed()
        return 'break'

    def insert_plain(self, index, text):
        """Duz metni imlecteki bicim ve paragraf stiliyle ekler; yeni satirlar ayni paragraf stilini alir."""
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        idx = self.index(index)
        tags = self.typing_tags(idx)
        line = int(idx.split('.')[0])
        self.insert(idx, text, tags)
        end = self.index('%s+%dc' % (idx, len(text)))
        self.mark_set('insert', end)
        last = int(end.split('.')[0])
        self.normalize_lines(range(line, last + 1))
        self.refresh_fonts('%d.0' % line, '%d.end' % last)
        return end

    # ================================================================ bicimlendirme komutlari
    def selection_or_word(self):
        try:
            return self.index('sel.first'), self.index('sel.last')
        except tk.TclError:
            return None

    def toggle_char(self, attr, value=None):
        """attr: 'b'|'i'|'u'|'color'. Secim varsa secime, yoksa yazilacak metne uygulanir."""
        rng = self.selection_or_word()
        if not rng:
            idx = self.index('insert')
            fmt = dict(self.typing_fmt[1]) if self.typing_fmt and self.compare(self.typing_fmt[0], '==', idx) else \
                self.char_fmt_at(idx + '-1c' if int(idx.split('.')[1]) else idx)
            fmt[attr] = value if attr == 'color' else not fmt.get(attr)
            self.typing_fmt = (idx, fmt)
            return
        s, e = rng
        self.undo.separator()
        self.undo.begin()
        try:
            if attr == 'color':
                for t in self.tag_names():
                    if str(t).startswith('c_'):
                        self.tag_remove(t, s, e)
                if value:
                    self.tag_add(self._color_tag(value.upper()), s, e)
            else:
                on = not self._all_have(attr, s, e)
                (self.tag_add if on else self.tag_remove)(attr, s, e)
                self.refresh_fonts(s, e)
        finally:
            self.undo.end()
        self.undo.separator()
        self.changed()

    def _all_have(self, tag, s, e):
        items = self._dump(s, e)
        txt = [it for it in items if it[0] == 't' and it[1].strip('\n')]
        return bool(txt) and all(tag in it[2] for it in txt)

    def current_format(self):
        idx = self.index('insert')
        if self.typing_fmt and self.compare(self.typing_fmt[0], '==', idx):
            fmt = dict(self.typing_fmt[1])
        else:
            fmt = self.char_fmt_at(idx + '-1c' if int(idx.split('.')[1]) else idx)
        fmt.update(self.para_props(int(idx.split('.')[0])))
        return fmt

    def _sel_lines(self):
        rng = self.selection_or_word()
        return self.lines(rng[0], rng[1]) if rng else self.lines('insert')

    def set_style(self, style):
        self.undo.separator()
        self.undo.begin()
        try:
            for ln in self._sel_lines():
                p = self.para_props(ln)
                if p['table']:
                    continue
                if style != 'normal' and p['list']:
                    self._set_list_line(ln, None)
                    p = self.para_props(ln)
                p['style'] = style
                self.set_para_tags(ln, self._para_tagset(p))
                self.refresh_fonts('%d.0' % ln, '%d.end' % ln)
        finally:
            self.undo.end()
        self.changed()

    def set_align(self, align):
        self.undo.separator()
        self.undo.begin()
        try:
            for ln in self._sel_lines():
                p = self.para_props(ln)
                p['align'] = None if align == 'left' else align
                self.set_para_tags(ln, self._para_tagset(p))
        finally:
            self.undo.end()
        self.changed()

    def toggle_list(self, kind):
        lines = list(self._sel_lines())
        all_same = all(self.para_props(ln)['list'] == kind for ln in lines)
        self.undo.separator()
        self.undo.begin()
        try:
            for ln in lines:
                if self.para_props(ln)['table'] or self.image_at_line(ln):
                    continue
                self._set_list_line(ln, None if all_same else kind)
            self.renumber()
        finally:
            self.undo.end()
        self.changed()

    def _set_list_line(self, line, kind, level=None):
        p = self.para_props(line)
        marker = self.tag_nextrange('lm', '%d.0' % line, '%d.end' % line)
        if marker and self.compare(marker[0], '==', '%d.0' % line):
            self.delete(marker[0], marker[1])
        p['list'] = kind
        if kind:
            p['style'] = 'normal'
            p['level'] = p['level'] if level is None else level
        else:
            p['level'] = 0
        self.set_para_tags(line, self._para_tagset(p))
        if kind:
            self._insert_marker(line, p)
        self.refresh_fonts('%d.0' % line, '%d.end' % line)

    def _insert_marker(self, line, props):
        text = BULLETS[min(3, props.get('level') or 0)] if props['list'] == 'bullet' else '1. '
        tags = ('lm',) + tuple(sorted(self._para_tagset(props))) + (self.font_tag('normal', False, False),)
        self.insert('%d.0' % line, text, tags)

    def change_level(self, delta):
        self.undo.separator()
        self.undo.begin()
        try:
            for ln in self._sel_lines():
                p = self.para_props(ln)
                if not p['list']:
                    continue
                self._set_list_line(ln, p['list'], max(0, min(3, p['level'] + delta)))
            self.renumber()
        finally:
            self.undo.end()
        self.changed()

    def renumber(self):
        """Numarali listelerdeki "N. " isaretlerini ve madde isaretlerini duzeltir."""
        last = int(self.index('end-1c').split('.')[0])
        counters = {}
        for ln in range(1, last + 1):
            p = self.para_props(ln)
            if p['list'] != 'number':
                if p['list'] != 'bullet':
                    counters = {}
                if p['list'] == 'bullet':
                    want = BULLETS[min(3, p['level'])]
                    self._fix_marker(ln, want)
                continue
            lvl = p['level']
            counters = {k: v for k, v in counters.items() if k <= lvl}
            counters[lvl] = counters.get(lvl, 0) + 1
            self._fix_marker(ln, '%d. ' % counters[lvl])

    def _fix_marker(self, ln, want):
        r = self.tag_nextrange('lm', '%d.0' % ln, '%d.end' % ln)
        if not r or self.compare(r[0], '!=', '%d.0' % ln):
            return
        if self.get(r[0], r[1]) != want:
            tags = tuple(str(t) for t in self.tag_names(r[0]) if recorded(str(t)))
            ins = self.compare('insert', '>=', r[1]) and self.compare('insert', '<=', '%d.end' % ln)
            off = len(self.get(r[1], 'insert')) if ins else None
            self.delete(r[0], r[1])
            self.insert('%d.0' % ln, want, tags)
            if off is not None:
                self.mark_set('insert', '%d.%d' % (ln, len(want) + off))

    # ================================================================ resim ve tablo
    def image_at_line(self, line):
        items = self._dump('%d.0' % line, '%d.end' % line)
        return next((it[1] for it in items if it[0] == 'i'), None)

    def image_at(self, index):
        for kind, val, _t in self._dump(index, index + '+1c'):
            if kind == 'i':
                return val
        return None

    def _photo(self, blk):
        from PIL import Image, ImageTk
        im = Image.open(io.BytesIO(blk['data']))
        im.load()
        if im.mode not in ('RGB', 'RGBA'):
            im = im.convert('RGBA')
        maxw = self.px(R.CONTENT_W_PT)
        w = max(8, min(maxw, self.px(blk['w'])))
        h = max(8, w * blk['h'] / max(1.0, blk['w']))
        im = im.resize((int(w), int(h)), Image.LANCZOS)
        return ImageTk.PhotoImage(im, master=self)

    def insert_image(self, index, blk):
        """Resmi index'in bulundugu paragraftan sonra kendi satirina ekler."""
        self.undo.separator()
        self.undo.begin()
        try:
            line = int(self.index(index).split('.')[0])
            if self.get('%d.0' % line, '%d.end' % line).strip() or self.image_at_line(line):
                tags = tuple(sorted(self.para_tags(line)))
                self.insert('%d.end' % line, '\n', tags)
                line += 1
                self.set_para_tags(line, self._para_tagset({'align': blk.get('align')}))
            name = self._create_image('%d.0' % line, blk)
            self.set_para_tags(line, self._para_tagset({'align': blk.get('align')}))
            self.mark_set('insert', '%d.end' % line)
        finally:
            self.undo.end()
        self.undo.separator()
        self.changed()
        return name

    def _create_image(self, index, blk):
        name = 'img' + uuid.uuid4().hex[:10]
        blk = dict(blk)
        self.images[name] = blk
        photo = self._photo(blk)
        self._photos[name] = photo
        real = str(self.image_create(index, image=photo, name=name, align='baseline', padx=2))
        if real != name:
            self.images[real] = blk
            self._photos[real] = photo
        return real

    def resize_image(self, name, w_pt):
        blk = self.images.get(name)
        if not blk:
            return
        old = (blk['w'], blk['h'])
        ratio = blk['h'] / max(1.0, blk['w'])
        new = (float(w_pt), float(w_pt) * ratio)
        self._set_image_size(name, new)
        self.undo.record(('imgsize', name, old, new))
        self.undo.separator()
        self.changed()

    def _set_image_size(self, name, size):
        blk = self.images[name]
        blk['w'], blk['h'] = size
        photo = self._photo(blk)
        self._photos[name] = photo
        try:
            self._call('image', 'configure', name, '-image', photo)
        except tk.TclError:
            pass

    def _resize_images(self):
        for name in list(self.images):
            try:
                self._call('image', 'cget', name, '-image')
            except tk.TclError:
                continue
            self._set_image_size(name, (self.images[name]['w'], self.images[name]['h']))

    def remove_image(self, name):
        try:
            idx = self.index(name)
        except tk.TclError:
            return False
        line = int(idx.split('.')[0])
        self.undo.separator()
        self.undo.begin()
        try:
            only = not self.get('%d.0' % line, '%d.end' % line).strip() and self.compare('%d.0' % line, '==', idx) \
                and self.compare('%d.end' % line, '==', idx + '+1c')
            if only and self.compare('%d.end' % line, '<', 'end-1c'):
                self.delete('%d.0' % line, '%d.0' % (line + 1))
            else:
                self.delete(idx)
        finally:
            self.undo.end()
        self.undo.separator()
        self.changed()
        return True

    def insert_table(self, rows, cols, index='insert'):
        self._tb_seq += 1
        tag = 'tb_%s' % uuid.uuid4().hex[:6]
        blk = {'t': 'table', 'rows': [[[R.run('')] for _ in range(cols)] for _ in range(rows)]}
        self.undo.separator()
        self.undo.begin()
        try:
            line = int(self.index(index).split('.')[0])
            if self.get('%d.0' % line, '%d.end' % line).strip() or self.image_at_line(line):
                self.insert('%d.end' % line, '\n', tuple(sorted(self.para_tags(line))))
                line += 1
                self.set_para_tags(line, set())
            self.insert_blocks('%d.0' % line, [blk], table_tag=tag)
            self.mark_set('insert', '%d.0' % line)
        finally:
            self.undo.end()
        self.undo.separator()
        self.changed()

    # ================================================================ blok <-> metin
    def load_blocks(self, blocks):
        rec = self.undo.recording
        self.undo.recording = False
        try:
            self._call('delete', '1.0', 'end')
            self.images.clear()
            self._photos.clear()
            self.insert_blocks('1.0', blocks)
        finally:
            self.undo.recording = rec
        self.undo.reset()
        self.mark_set('insert', '1.0')

    def insert_blocks(self, index, blocks, table_tag=None):
        """Bloklari index'e ekler. index satir ortasindaysa satir bolunur. Son blok mevcut satir sonunu kullanir
        (satir bossa) ya da kendi satir sonunu ekler. Donus: eklenen son konum."""
        if not blocks:
            return self.index(index)
        idx = self.index(index)
        line, col = map(int, idx.split('.'))
        if col > 0:
            if len(blocks) == 1 and blocks[0]['t'] == 'p':
                return self.insert_runs(idx, blocks[0]['runs'])
            self.insert(idx, '\n', tuple(sorted(self.para_tags(line))))
            line += 1
        first_line = line
        line_empty = not self.get('%d.0' % line, '%d.end' % line) and not self.image_at_line(line)
        pos = '%d.0' % line
        tables = {}
        for k, b in enumerate(blocks):
            last = k == len(blocks) - 1
            if b['t'] == 'table':
                tag = table_tag if table_tag and len(blocks) == 1 else 'tb_%s' % uuid.uuid4().hex[:6]
                tables[tag] = True
                for ri, row in enumerate(b['rows']):
                    props = {'table': tag}
                    ptags = tuple(sorted(self._para_tagset(props)))
                    for ci, cell in enumerate(row):
                        if ci:
                            self.insert(pos, '\t', ptags + (self.font_tag('normal', False, False),))
                            pos = self.index(pos + '+1c')
                        pos = self._ins_runs(pos, cell, ptags, 'normal')
                    if not (last and ri == len(b['rows']) - 1 and line_empty):
                        self.insert(pos, '\n', ptags)
                        pos = self.index(pos + '+1c')
                    else:
                        self.set_para_tags(int(pos.split('.')[0]), set(ptags))
                continue
            if b['t'] == 'img':
                props = {'align': b.get('align')}
                ptags = tuple(sorted(self._para_tagset(props)))
                self._create_image(pos, b)
                for t in ptags:
                    self.tag_add(t, pos)
                pos = self.index(pos + '+1c')
            else:
                props = {'style': b.get('style', 'normal'), 'list': b.get('list'), 'level': b.get('level', 0),
                         'align': b.get('align'), 'pb': b.get('pb')}
                ptags = tuple(sorted(self._para_tagset(props)))
                if b.get('list'):
                    mk = BULLETS[min(3, b.get('level', 0))] if b['list'] == 'bullet' else '1. '
                    self.insert(pos, mk, ('lm',) + ptags + (self.font_tag('normal', False, False),))
                    pos = self.index(pos + '+%dc' % len(mk))
                pos = self._ins_runs(pos, b['runs'], ptags, props['style'])
            if last and line_empty:
                self.set_para_tags(int(pos.split('.')[0]), set(ptags))
            else:
                self.insert(pos, '\n', ptags)
                pos = self.index(pos + '+1c')
        for tag in tables:
            self._table_tabs(tag)
        if any(b['t'] == 'p' and b.get('list') for b in blocks):
            self.renumber()
        self.mark_set('insert', pos if not line_empty else self.index(pos))
        _ = first_line
        return pos

    def _ins_runs(self, pos, runs, ptags, style):
        for r in runs:
            if not r.get('text'):
                continue
            tags = tuple(self._char_tags(r)) + ptags + (self.font_tag(style, r.get('b'), r.get('i')),)
            text = r['text'].replace('\n', ' ')
            self.insert(pos, text, tags)
            pos = self.index('%s+%dc' % (pos, len(text)))
        return pos

    def insert_runs(self, index, runs):
        """Satir icine bicimli parcalari ekler (paragraf stili satirdan gelir)."""
        idx = self.index(index)
        line = int(idx.split('.')[0])
        p = self.para_props(line)
        ptags = tuple(sorted(self.para_tags(line)))
        end = self._ins_runs(idx, runs, ptags, p['style'])
        self.mark_set('insert', end)
        return end

    def get_blocks(self, s='1.0', e='end-1c', lines=None):
        """lines: liste verilirse her blok icin (ilk_satir, son_satir) eklenir (canli ceviri vurgusu icin)."""
        s, e = self.index(s), self.index(e)
        out = _LineTrack(lines)
        if self.compare(e, '<', s):
            s, e = e, s
        first, last = int(s.split('.')[0]), int(e.split('.')[0])
        table_open = None
        for ln in range(first, last + 1):
            out.line = ln
            ls = s if ln == first else '%d.0' % ln
            le = e if ln == last else '%d.end' % ln
            props = self.para_props(ln)
            items = self._dump(ls, le) if self.compare(ls, '<', le) else []
            if props['table']:
                cells = [[]]
                for kind, val, tags in items:
                    if kind != 't':
                        continue
                    parts = val.split('\t')
                    for k, part in enumerate(parts):
                        if k:
                            cells.append([])
                        if part:
                            cells[-1].append(self._run_from(part, tags))
                cells = [R.merge_runs(c) for c in cells]
                if table_open is not None and table_open[0] == props['table']:
                    table_open[1]['rows'].append(cells)
                    out.extend_last(ln)
                else:
                    blk = {'t': 'table', 'rows': [cells]}
                    out.append(blk)
                    table_open = (props['table'], blk)
                continue
            table_open = None
            cur = []
            pb = props['pb']
            for kind, val, tags in items:
                if kind == 'i':
                    if R.runs_text(cur).strip():
                        out.append(self._para_block(cur, props, pb))
                        pb = False
                    cur = []
                    blk = self.images.get(val)
                    if blk:
                        b = dict(blk)
                        b['align'] = props['align']
                        out.append(b)
                    continue
                if 'lm' in tags:
                    continue
                cur.append(self._run_from(val, tags))
            only_img = items and all(it[0] == 'i' or not it[1].strip() for it in items) and any(it[0] == 'i' for it in items)
            if not only_img and (cur or not items or not out or out[-1]['t'] != 'img'):
                out.append(self._para_block(cur, props, pb))
        return list(out)

    def flash_lines(self, tag, first, last):
        """Gecici vurgu (geri alma kaydina ve belgeye girmez)."""
        self._call('tag', 'add', tag, '%d.0' % first, '%d.end+1c' % last)

    def _run_from(self, text, tags):
        return R.run(text, 'b' in tags, 'i' in tags, 'u' in tags, next((t[2:] for t in tags if t.startswith('c_')), None))

    @staticmethod
    def _para_block(runs, props, pb):
        return R.para(R.merge_runs(runs), props['style'], props['list'], props['level'], props['align'], pb)

    def markdown(self, s='1.0', e='end-1c', image_ids=None):
        blocks = self.get_blocks(s, e)
        ids = image_ids if image_ids is not None else {}
        n = len(ids)
        for b in blocks:
            if b['t'] == 'img' and id(b) not in ids:
                n += 1
                ids[id(b)] = str(n)
        return R.blocks_to_markdown(blocks, ids), {v: b for b in blocks for k, v in ids.items() if k == id(b)}

    def replace_with_markdown(self, s, e, md, images=None):
        """s..e araligini Markdown'dan kurulan bloklarla degistirir (tek geri al adimi)."""
        blocks = R.markdown_to_blocks(md, images or {})
        self.undo.separator()
        self.undo.begin()
        try:
            s = self.index(s)
            line_start = self.compare(s, '==', '%s linestart' % s)
            whole_end = self.compare(e, '==', '%s lineend' % e)
            self.delete(s, e)
            if not blocks:
                end = s
            elif len(blocks) == 1 and blocks[0]['t'] == 'p':
                if line_start and whole_end:
                    ln = int(s.split('.')[0])
                    b = blocks[0]
                    old = self.para_props(ln)
                    if b.get('style', 'normal') != 'normal' or b.get('list'):
                        props = {'style': b.get('style'), 'list': b.get('list'), 'level': b.get('level', 0), 'align': old['align']}
                        marker = self.tag_nextrange('lm', '%d.0' % ln, '%d.end' % ln)
                        if marker and self.compare(marker[0], '==', '%d.0' % ln):
                            self.delete(marker[0], marker[1])
                        self.set_para_tags(ln, self._para_tagset(props))
                        if b.get('list'):
                            self._insert_marker(ln, props)
                        s = self._content_start(ln)
                end = self.insert_runs(s, blocks[0]['runs'])
                self.refresh_fonts(s, end)
            else:
                end = self.insert_blocks(s, blocks)
            self.renumber()
        finally:
            self.undo.end()
        self.undo.separator()
        self.changed()
        return s, end

    def insert_markdown_after(self, index, md, images=None):
        """Markdown'u index'in paragrafindan sonra yeni paragraflar olarak ekler. (bas, son) dondurur."""
        blocks = R.markdown_to_blocks(md, images or {})
        if not blocks:
            return None
        self.undo.separator()
        self.undo.begin()
        try:
            line = int(self.index(index).split('.')[0])
            if self.para_props(line)['table']:
                while self.para_props(line + 1)['table'] == self.para_props(line)['table'] and \
                        self.compare('%d.0' % (line + 1), '<', 'end-1c'):
                    line += 1
            self.insert('%d.end' % line, '\n', ())
            self.set_para_tags(line + 1, set())
            start = '%d.0' % (line + 1)
            end = self.insert_blocks(start, blocks)
            self.refresh_fonts(start, end)
        finally:
            self.undo.end()
        self.undo.separator()
        self.changed()
        return start, end

    def insert_markdown(self, index, md, images=None):
        """Imlece Markdown ekler: tek paragrafsa satir icine, degilse bloklar halinde."""
        blocks = R.markdown_to_blocks(md, images or {})
        if not blocks:
            return None
        self.undo.separator()
        self.undo.begin()
        try:
            start = self.index(index)
            end = self.insert_blocks(start, blocks)
            self.refresh_fonts(start, end)
        finally:
            self.undo.end()
        self.undo.separator()
        self.changed()
        return start, end

    # ---------------------------------------------------------------- tablo islemleri
    def table_lines(self, line):
        tag = self.para_props(line)['table']
        if not tag:
            return None, []
        r = self.tag_ranges(tag)
        a, b = int(str(r[0]).split('.')[0]), int(str(r[-1]).split('.')[0])
        if self.compare(str(r[-1]), '==', '%d.0' % b):
            b -= 1
        return tag, list(range(a, b + 1))

    def _cell_index(self, line, index):
        return self.get('%d.0' % line, index).count('\t')

    def table_add_row(self, line, below=True):
        tag, lines = self.table_lines(line)
        if not tag:
            return
        ncol = self.get('%d.0' % line, '%d.end' % line).count('\t') + 1
        tags = tuple(sorted(self.para_tags(line))) + (self.font_tag('normal', False, False),)
        self.undo.separator()
        self.undo.begin()
        try:
            if below:
                self.insert('%d.end' % line, '\n' + '\t' * (ncol - 1), tags)
                self.mark_set('insert', '%d.0' % (line + 1))
            else:
                self.insert('%d.0' % line, '\t' * (ncol - 1) + '\n', tags)
                self.mark_set('insert', '%d.0' % line)
        finally:
            self.undo.end()
        self.changed()

    def table_delete_row(self, line):
        tag, lines = self.table_lines(line)
        if not tag:
            return
        self.undo.separator()
        self.undo.begin()
        try:
            if len(lines) == 1:
                self.table_delete(line)
                return
            if line == lines[-1]:
                self.delete('%d.end' % (line - 1), '%d.end' % line)
            else:
                self.delete('%d.0' % line, '%d.0' % (line + 1))
        finally:
            self.undo.end()
        self.changed()

    def table_add_col(self, line, index='insert'):
        tag, lines = self.table_lines(line)
        if not tag:
            return
        col = self._cell_index(line, index)
        self.undo.separator()
        self.undo.begin()
        try:
            for ln in lines:
                cells = self.get('%d.0' % ln, '%d.end' % ln).split('\t')
                at = '%d.%d' % (ln, sum(len(c) + 1 for c in cells[:min(col, len(cells) - 1) + 1]) - 1)
                tags = tuple(sorted(self.para_tags(ln))) + (self.font_tag('normal', False, False),)
                self.insert(at, '\t', tags)
            self._table_tabs(tag)
        finally:
            self.undo.end()
        self.changed()

    def table_delete_col(self, line, index='insert'):
        tag, lines = self.table_lines(line)
        if not tag:
            return
        col = self._cell_index(line, index)
        ncol = self.get('%d.0' % line, '%d.end' % line).count('\t') + 1
        if ncol <= 1:
            return self.table_delete(line)
        self.undo.separator()
        self.undo.begin()
        try:
            for ln in lines:
                text = self.get('%d.0' % ln, '%d.end' % ln)
                cells = text.split('\t')
                if col >= len(cells):
                    continue
                start = sum(len(c) + 1 for c in cells[:col])
                if col == len(cells) - 1:
                    self.delete('%d.%d' % (ln, start - 1), '%d.end' % ln)
                else:
                    self.delete('%d.%d' % (ln, start), '%d.%d' % (ln, start + len(cells[col]) + 1))
            self._table_tabs(tag)
        finally:
            self.undo.end()
        self.changed()

    def table_delete(self, line):
        tag, lines = self.table_lines(line)
        if not tag:
            return
        self.undo.separator()
        self.undo.begin()
        try:
            a, b = lines[0], lines[-1]
            if self.compare('%d.end' % b, '<', 'end-1c'):
                self.delete('%d.0' % a, '%d.0' % (b + 1))
            elif a > 1:
                keep = self._para_tagset(self.para_props(a - 1))
                self.delete('%d.end' % (a - 1), '%d.end' % b)
                self.set_para_tags(a - 1, keep)
            else:
                self.delete('%d.0' % a, '%d.end' % b)
                self.set_para_tags(a, set())
        finally:
            self.undo.end()
        self.changed()

    def plain(self):
        return R.plain_text(self.get_blocks()) if self.rich else self.get('1.0', 'end-1c')

    def page_count(self):
        try:
            h = self._call('count', '-ypixels', '1.0', 'end')
            h = int(h[0] if isinstance(h, tuple) else h)
        except (tk.TclError, TypeError):
            return 1
        usable = self.px(841.9 - 2 * R.MARGIN_PT)
        return max(1, int((h or 0) / max(1.0, usable)) + 1)


class UndoManager:
    """Gruplu geri al/yinele. Islemler: ('ins', s, e, icerik) ('del', s, e, icerik) ('tag', alt, ad, s, e, onceki)
    ('imgsize', ad, eski, yeni). Ardisik tek karakter yazma/silme ayni grupta birlesir (kelime sinirinda ayrilir)."""

    LIMIT = 1500

    def __init__(self, t):
        self.t = t
        self.stack, self.redo_stack = [], []
        self.depth = 0
        self.recording = True
        self.force_new = True
        self.serial = 0
        self.saved = 0
        self._last_time = 0

    def state(self):
        return self.stack[-1][0] if self.stack else 0

    def mark_saved(self):
        self.saved = self.state()
        self.force_new = True

    def dirty(self):
        return self.state() != self.saved

    def _new_group(self):
        self.serial += 1
        self.stack.append([self.serial, []])
        if len(self.stack) > self.LIMIT:
            del self.stack[:len(self.stack) - self.LIMIT]

    def begin(self):
        if self.depth == 0:
            self._new_group()
            self.redo_stack.clear()
        self.depth += 1

    def end(self):
        self.depth = max(0, self.depth - 1)
        if self.depth == 0:
            if self.stack and not self.stack[-1][1]:
                self.stack.pop()
            self.force_new = True

    def separator(self):
        if self.depth == 0:
            self.force_new = True

    def reset(self):
        self.stack.clear()
        self.redo_stack.clear()
        self.depth = 0
        self.force_new = True
        self.saved = 0

    def record(self, op):
        if not self.recording:
            return
        self.redo_stack.clear()
        if self.depth > 0 and self.stack:
            self.stack[-1][1].append(op)
            return
        now = time.monotonic()
        if not self.force_new and self.stack and self._mergeable(op, now):
            self.stack[-1][1].append(op)
        else:
            self._new_group()
            self.stack[-1][1].append(op)
        self.force_new = op[0] not in ('ins', 'del') or not self._single(op)
        self._last_time = now

    @staticmethod
    def _single(op):
        return len(op[3]) == 1 and op[3][0][0] == 't' and len(op[3][0][1]) == 1

    def _mergeable(self, op, now):
        last = self.stack[-1][1][-1] if self.stack[-1][1] else None
        if not last or last[0] != op[0] or not self._single(op) or not self._single(last) or now - self._last_time > 2.0:
            return False
        t = self.t
        if op[0] == 'ins':
            ch, prev = op[3][0][1], last[3][0][1]
            if ch in ' \n\t' and prev not in ' \n\t':
                return False
            return t._call('compare', op[1], '==', last[2])
        return t._call('compare', op[2], '==', last[1]) or t._call('compare', op[1], '==', last[1])

    def _apply(self, op, inverse):
        t = self.t
        kind = op[0]
        if kind == 'imgsize':
            t._set_image_size(op[1], op[2] if inverse else op[3])
            return None
        if kind == 'tag':
            _k, sub, name, s, e, before = op
            add = (sub == 'add') != inverse
            if inverse:
                t._call('tag', 'remove', name, s, e)
                for a, b in before:
                    t._call('tag', 'add', name, a, b)
            else:
                t._call('tag', 'add' if add else 'remove', name, s, e)
            return s
        _k, s, e, content = op
        if (kind == 'ins') == inverse:
            t._call('delete', s, e)
            return s
        t._restore(s, content)
        return e

    def undo(self):
        if not self.stack:
            return False
        sid, ops = self.stack.pop()
        self.recording = False
        pos = None
        try:
            for op in reversed(ops):
                p = self._apply(op, True)
                pos = p or pos
        finally:
            self.recording = True
        self.redo_stack.append([sid, ops])
        self.force_new = True
        self._after(pos)
        return True

    def redo(self):
        if not self.redo_stack:
            return False
        sid, ops = self.redo_stack.pop()
        self.recording = False
        pos = None
        try:
            for op in ops:
                p = self._apply(op, False)
                pos = p or pos
        finally:
            self.recording = True
        self.stack.append([sid, ops])
        self.force_new = True
        self._after(pos)
        return True

    def _after(self, pos):
        t = self.t
        if pos:
            try:
                t.mark_set('insert', pos)
                t.see('insert')
            except tk.TclError:
                pass
        t.changed()
