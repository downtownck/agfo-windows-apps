# -*- coding: utf-8 -*-
"""AGFO AI Editor 2.9 - Video projesi penceresi (Ses sekmesi > Video (MOV)).

1. Ozet ve sahne plani (AI; kac gorsel gerektigine AI karar verir) - ozet, karakter kartlari, sahneler duzenlenebilir.
2. Her sahne: baslik, gorsel tarifi, kendi gorselini secme, onceki sahneyle birlestirme, ikiye bolme.
3. Videoyu olustur: ses paragraf paragraf, altyazi goruntuye yakili, gorseli olmayan sahnede yer tutucu kart; .mov.
"""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import agfo_ai_client as ai
import agfo_editor_core as core
import agfo_video as V
from agfo_brcgs_view import _colors


class VideoProjectWindow(tk.Toplevel):
    def __init__(self, app, backend, doc=None, md=None, what='belge', proj=None):
        """Belgeden (doc + md) ya da 2.10: editorden bagimsiz, kayitli bir proje dosyasindan (proj) acilir. Proje
        dosyasi metni, plani, gorselleri ve uretilmis sesleri tasir; kalinan yerden devam edilir."""
        super().__init__(app)
        self.app, self.backend, self.doc = app, backend, doc
        self.P = _colors(app)
        self.geometry('1180x780')
        self.minsize(900, 600)
        self.cancel_flag = False
        self.busy = False
        if proj is None:
            paras = V.paragraphs_from_markdown(md)
            base = str(core.data_dir() / 'video')
            folder = V.project_dir_for(doc.path, doc.title, base)
            proj = V.load_project(folder)
            if proj is None or proj.get('paragraphs') != paras:
                old = proj
                key = (old or {}).get('style_key') or app.settings.get('video_style') or V.DEFAULT_STYLE_KEY
                proj = V.new_project(folder, os.path.splitext(doc.title)[0], paras, key)
                if old and old.get('paragraphs') != paras:
                    app.flash('Metin değiştiği için sahne planı yeniden kuruldu.')
            if doc.path:
                proj['source'] = doc.path
        self.title('Sesli çizgi roman — %s' % (proj.get('title') or os.path.basename(proj['folder'])))
        self.proj = proj
        V.remember_project(app.settings, proj['folder'])
        core.save_settings(app.settings)
        self.what = what
        self._build()
        self._fill()
        V.save_project(self.proj)

    # ------------------------------------------------------------------ arayuz
    def _build(self):
        app = self.app
        P = self.P
        self.configure(bg=P['PANEL'])
        top = tk.Frame(self, bg=P['PANEL'], padx=12, pady=8)
        top.pack(fill='x')
        tk.Label(top, text='🎬 Sesli çizgi roman', fg=P['FG'], bg=P['PANEL'], font=('Segoe UI', 13, 'bold')).pack(side='left')
        app.btn(top, 'Klasörü aç', lambda: app._open_external(self.proj['folder']), 'ghost', side='right')
        self.render_btn = app.btn(top, '🎬 Videoyu oluştur (MOV)', self.render, 'primary', side='right')
        self.plan_btn = app.btn(top, '✨ Özet ve sahne planı çıkar (AI)', self.make_plan, 'normal', side='right')
        self.preset_var = tk.StringVar(value=V.style_of(self.proj)['label'])
        pb = ttk.Combobox(top, textvariable=self.preset_var, values=[v['label'] for v in V.STYLES.values()], state='readonly',
                          width=22)
        pb.pack(side='right', padx=6)
        pb.bind('<<ComboboxSelected>>', lambda e: self.change_style())
        tk.Label(top, text='Tarz', fg=P['MUTED'], bg=P['PANEL'], font=('Segoe UI', 9)).pack(side='right')
        self.draft_var = tk.BooleanVar(value=bool(self.proj.get('draft')))
        tk.Checkbutton(top, text='Taslak (yer tutuculara sahne notu)', variable=self.draft_var, command=self._draft_changed,
                       bg=P['PANEL'], fg=P['FG'], selectcolor=P.get('EDIT_BG', P['PANEL']), activebackground=P['PANEL'],
                       activeforeground=P['FG'], font=('Segoe UI', 9), highlightthickness=0, bd=0).pack(side='right', padx=8)
        self.info = tk.Label(self, text='', fg=P['MUTED'], bg=P['PANEL'], font=('Segoe UI', 9), anchor='w', padx=12)
        self.info.pack(fill='x')
        self.status = tk.Label(self, text='', fg=P['ACCENT'], bg=P['PANEL'], font=('Segoe UI', 9), anchor='w', padx=12)
        self.status.pack(fill='x')
        body = ttk.PanedWindow(self, orient='horizontal')
        body.pack(fill='both', expand=True, padx=8, pady=8)
        left = tk.Frame(body, bg=P['PANEL'])
        body.add(left, weight=2)
        tk.Label(left, text='Özet', fg=P['FG'], bg=P['PANEL'], font=('Segoe UI', 10, 'bold'), anchor='w').pack(fill='x')
        self.summary = self._text(left, 4)
        self.summary.pack(fill='x')
        tk.Label(left, text='Tarz cümlesi (bütün karelerde aynı; görsel promptlarının başı)', fg=P['FG'], bg=P['PANEL'],
                 font=('Segoe UI', 10, 'bold'), anchor='w').pack(fill='x', pady=(8, 0))
        self.style_var = tk.StringVar()
        ttk.Entry(left, textvariable=self.style_var).pack(fill='x')
        tk.Label(left, text='Karakterler (her satır: Ad: görünüm — tüm karelerde aynı kalır)', fg=P['FG'], bg=P['PANEL'],
                 font=('Segoe UI', 10, 'bold'), anchor='w').pack(fill='x', pady=(8, 0))
        self.chars = self._text(left, 4)
        self.chars.pack(fill='x')
        tk.Label(left, text='Kareler (her kare bir görsel; sayısına AI karar verir)', fg=P['FG'], bg=P['PANEL'], font=('Segoe UI', 10, 'bold'),
                 anchor='w').pack(fill='x', pady=(8, 0))
        self.tree = ttk.Treeview(left, columns=('paras', 'secs', 'img'), show='tree headings', selectmode='browse', height=12)
        for col, txt, w in (('#0', 'Sahne', 260), ('paras', 'Paragraf', 80), ('secs', 'Süre ≈', 70), ('img', 'Görsel', 110)):
            self.tree.heading(col, text=txt)
            self.tree.column(col, width=w, stretch=(col == '#0'))
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', lambda e: self._pick())
        right = tk.Frame(body, bg=P['PANEL'], padx=8)
        body.add(right, weight=3)
        self.detail = right

    def _text(self, parent, rows):
        P = self.P
        return tk.Text(parent, height=rows, wrap='word', bg=P['EDIT_BG'], fg=P['FG'], insertbackground=P['ACCENT'], relief='flat',
                       bd=0, highlightthickness=1, highlightbackground=P['LINE'], font=('Segoe UI', 10), padx=6, pady=4, undo=True)

    def _fill(self):
        plan = self.proj['plan']
        self.style_var.set(plan.get('style') or V.DEFAULT_STYLE)
        for w, val in ((self.summary, plan.get('summary', '')),
                       (self.chars, '\n'.join('%s: %s' % (c['name'], c['look']) for c in plan.get('characters', [])))):
            w.delete('1.0', 'end')
            w.insert('1.0', val)
        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        paras = self.proj['paragraphs']
        for i, s in enumerate(plan['scenes']):
            secs = s.get('seconds') or V.est_seconds(paras, s['start'], s['end'])
            img = os.path.basename(s['image']) if s.get('image') else 'yer tutucu'
            self.tree.insert('', 'end', iid=str(i), text='%d. %s' % (i + 1, s['title']),
                             values=('%d–%d' % (s['start'] + 1, s['end'] + 1) if s['end'] > s['start'] else str(s['start'] + 1),
                                     '%d sn' % round(secs), img))
        total = V.est_seconds(paras, 0, len(paras) - 1)
        self.info.configure(text='%d paragraf · %d sahne · ≈ %d:%02d · plan: %s · %s' % (
            len(paras), len(plan['scenes']), total // 60, total % 60,
            'AI' if self.proj.get('planned_by') == 'ai' else 'otomatik', self.proj['folder']))
        pick = sel[0] if sel and self.tree.exists(sel[0]) else ('0' if plan['scenes'] else None)
        if pick:
            self.tree.selection_set(pick)
            self._pick()

    def _collect_texts(self):
        """Ozet ve karakter kutularindaki elle yapilan duzeltmeleri plana yazar."""
        plan = self.proj['plan']
        plan['summary'] = self.summary.get('1.0', 'end-1c').strip()
        plan['style'] = self.style_var.get().strip() or V.DEFAULT_STYLE
        chars = []
        for line in self.chars.get('1.0', 'end-1c').splitlines():
            if ':' in line:
                n, look = line.split(':', 1)
                if n.strip():
                    chars.append({'name': n.strip(), 'look': look.strip()})
        plan['characters'] = chars

    def _pick(self):
        sel = self.tree.selection()
        for w in self.detail.winfo_children():
            w.destroy()
        if not sel:
            return
        i = int(sel[0])
        s = self.proj['plan']['scenes'][i]
        P, app = self.P, self.app
        tk.Label(self.detail, text='Sahne %d' % (i + 1), fg=P['ACCENT'], bg=P['PANEL'], font=('Segoe UI', 10, 'bold'),
                 anchor='w').pack(fill='x')
        tvar = tk.StringVar(value=s['title'])
        e = ttk.Entry(self.detail, textvariable=tvar)
        e.pack(fill='x')
        tvar.trace_add('write', lambda *_a: (s.__setitem__('title', tvar.get()), self._refresh_row(i)))
        tk.Label(self.detail, text='Görsel tarifi (AI görsel üretimi bunu kullanacak; İngilizce önerilir)', fg=P['MUTED'],
                 bg=P['PANEL'], font=('Segoe UI', 9), anchor='w').pack(fill='x', pady=(8, 0))
        vis = self._text(self.detail, 4)
        vis.insert('1.0', s.get('visual', ''))
        vis.pack(fill='x')
        vis.bind('<KeyRelease>', lambda ev: s.__setitem__('visual', vis.get('1.0', 'end-1c')))
        srow = tk.Frame(self.detail, bg=P['PANEL'])
        srow.pack(fill='x', pady=(6, 0))
        tk.Label(srow, text='Çekim', fg=P['MUTED'], bg=P['PANEL'], font=('Segoe UI', 9)).pack(side='left')
        shot = tk.StringVar(value=s.get('shot', ''))
        cb = ttk.Combobox(srow, textvariable=shot, values=['', 'wide', 'medium', 'close-up', 'extreme close-up',
                                                         'over-the-shoulder', "bird's-eye"], width=18)
        cb.pack(side='left', padx=6)
        shot.trace_add('write', lambda *_a: s.__setitem__('shot', shot.get()))
        tk.Label(self.detail, text='Karakterler: %s' % (', '.join(s['characters']) or '—'), fg=P['MUTED'], bg=P['PANEL'],
                 font=('Segoe UI', 9), anchor='w').pack(fill='x', pady=(4, 0))
        ph = tk.Frame(self.detail, bg=P['PANEL'])
        ph.pack(fill='x', pady=(8, 0))
        tk.Label(ph, text='Görsel promptu (tarz + çekim + sahne + karakterlerin sabit görünümü)', fg=P['MUTED'], bg=P['PANEL'],
                 font=('Segoe UI', 9), anchor='w').pack(side='left')
        self.prompt_box = pr = self._text(self.detail, 5)

        def copy():
            self._collect_texts()
            self.clipboard_clear()
            self.clipboard_append(V.compose_prompt(self.proj, s))
            app.flash('Görsel promptu kopyalandı.')

        def reset():
            s['prompt'] = ''
            self._collect_texts()
            pr.delete('1.0', 'end')
            pr.insert('1.0', V.compose_prompt(self.proj, s))
        app.btn(ph, 'Kopyala', copy, 'ghost', side='right')
        app.btn(ph, 'Otomatiğe dön', reset, 'ghost', side='right')
        pr.insert('1.0', V.compose_prompt(self.proj, s))
        pr.pack(fill='x')

        def edited(_e=None):
            txt = pr.get('1.0', 'end-1c').strip()
            s['prompt'] = '' if txt == V.compose_prompt(self.proj, dict(s, prompt='')).strip() else txt
        pr.bind('<KeyRelease>', edited)
        row = tk.Frame(self.detail, bg=P['PANEL'])
        row.pack(fill='x', pady=8)
        app.btn(row, '🖼 Kendi görselimi seç…', lambda: self.choose_image(i), 'normal')
        if s.get('image'):
            app.btn(row, 'Görseli kaldır', lambda: self.clear_image(i), 'ghost')
        app.btn(row, '👁 Kareyi önizle', lambda: self.preview(i), 'ghost')
        app.btn(row, '⤒ Öncekiyle birleştir', lambda: self.merge(i), 'ghost')
        app.btn(row, '✂ İkiye böl', lambda: self.split(i), 'ghost')
        tk.Label(self.detail, text='Bu sahnede okunan metin', fg=P['FG'], bg=P['PANEL'], font=('Segoe UI', 10, 'bold'),
                 anchor='w').pack(fill='x', pady=(6, 0))
        txt = self._text(self.detail, 12)
        txt.insert('1.0', '\n\n'.join(self.proj['paragraphs'][s['start']:s['end'] + 1]))
        txt.configure(state='disabled')
        txt.pack(fill='both', expand=True)

    def _refresh_row(self, i):
        s = self.proj['plan']['scenes'][i]
        if self.tree.exists(str(i)):
            self.tree.item(str(i), text='%d. %s' % (i + 1, s['title']))

    def _save(self):
        self._collect_texts()
        V.save_project(self.proj)

    def change_style(self):
        key = next((k for k, v in V.STYLES.items() if v['label'] == self.preset_var.get()), V.DEFAULT_STYLE_KEY)
        if key == self.proj.get('style_key'):
            return
        self._collect_texts()
        V.set_style(self.proj, key)
        self.app.settings['video_style'] = key
        core.save_settings(self.app.settings)
        V.save_project(self.proj)
        self._fill()
        self.app.flash('Tarz: %s. Görsel promptları bu tarzla yazılır; kare sayısı ve çekimlerin tarza uyması için '
                       '"Özet ve sahne planı çıkar"ı yeniden çalıştırın.' % V.STYLES[key]['label'], 9000)

    def _draft_changed(self):
        self.proj['draft'] = bool(self.draft_var.get())
        V.save_project(self.proj)

    def preview(self, i):
        """Kare videodaki gibi: gorsel (ya da yer tutucu) + tarzin cerceve katmani."""
        self._collect_texts()
        try:
            out = V.preview_frame(self.proj, i)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror('Önizleme', str(e), parent=self)
            return None
        if not self.app.smoke:
            self.app._open_external(out)
        return out

    # ------------------------------------------------------------------ sahne islemleri
    def choose_image(self, i):
        p = filedialog.askopenfilename(parent=self, title='Sahne görseli', filetypes=[('Görsel', '*.png *.jpg *.jpeg *.webp *.bmp')])
        if not p:
            return
        V.set_image(self.proj, i, p)
        self._save()
        self._fill()

    def clear_image(self, i):
        self.proj['plan']['scenes'][i]['image'] = ''
        self._save()
        self._fill()

    def merge(self, i):
        if V.merge_scene(self.proj['plan'], i):
            self._save()
            self.tree.selection_set(str(max(0, i - 1)))
            self._fill()

    def split(self, i):
        if V.split_scene(self.proj['plan'], i):
            self._save()
            self._fill()
        else:
            self.app.flash('Tek paragraflık sahne bölünemez.')

    # ------------------------------------------------------------------ AI plan
    def make_plan(self):
        if self.busy:
            return
        paras = self.proj['paragraphs']
        if any(s.get('image') for s in self.proj['plan']['scenes']) and not self.app.smoke and not messagebox.askyesno(
                'Sahne planı', 'Yeni plan mevcut sahnelerin yerini alır; seçtiğiniz görseller sahnelerden ayrılır. Devam edilsin mi?',
                parent=self):
            return
        lang = self.app.lang_var.get() or 'Türkçe'
        key = self.proj.get('style_key') or V.DEFAULT_STYLE_KEY
        prompt = V.PLAN_SYSTEM + '\n\n' + V.plan_prompt(paras, lang, style_key=key)
        backends = self.app.backends()
        self._busy('AI özet ve sahne planı çıkarıyor…')

        def work():
            res = ai.run_with_fallback(backends, 'chat', [{'role': 'user', 'content': prompt}], '', 6000)
            return res, V.parse_plan(res.get('text', ''), len(paras), key)

        def done(ok, res):
            self._idle()
            if not ok:
                messagebox.showerror('Sahne planı', res, parent=self)
                return
            res, plan = res
            if plan is None:
                messagebox.showwarning('Sahne planı', 'AI yanıtı okunamadı; otomatik plan korunuyor. Bir kez daha deneyin.', parent=self)
                return
            self.proj['plan'] = plan
            self.proj['planned_by'] = 'ai'
            V.save_project(self.proj)
            self._fill()
            self.app.flash('Sahne planı: %d sahne, %d karakter · %s' % (len(plan['scenes']), len(plan['characters']),
                                                                         res.get('model') or res.get('via', '')), 8000)
        self.app._start_job('Video: sahne planı', work, done)

    # ------------------------------------------------------------------ uretim
    def _busy(self, msg):
        self.busy = True
        self.status.configure(text=msg)
        for b in (self.render_btn, self.plan_btn):
            b.configure(state='disabled')

    def _idle(self, msg=''):
        self.busy = False
        self.status.configure(text=msg)
        for b in (self.render_btn, self.plan_btn):
            try:
                b.configure(state='normal')
            except tk.TclError:
                pass

    def _ffmpeg(self):
        tools = str(core.data_dir() / 'tools' / 'ffmpeg')
        ff, fp = V.find_ffmpeg(tools)
        if ff:
            return ff, fp, None
        if not V.IS_WIN:
            messagebox.showerror('ffmpeg', 'ffmpeg bulunamadı. Sisteminize ffmpeg kurun.', parent=self)
            return None, None, None
        if not messagebox.askyesno('ffmpeg gerekli', 'Video için açık kaynak ffmpeg gerekiyor (bir kez, yaklaşık 150 MB indirilir; '
                                   'GitHub · BtbN derlemesi). İndirilsin mi?', parent=self):
            return None, None, None
        return None, None, tools

    def render(self):
        if self.busy:
            return
        self._save()
        ff, fp, download_to = self._ffmpeg()
        if not ff and not download_to:
            return
        st = self.app.settings
        speed = float(st.get('speech_speed', 1.0))
        gap = int(st.get('speech_paragraph_pause', 700))
        script = bool(st.get('readaloud_script', False))
        b = self.backend or self.app._speech_backend('Video')
        if not b:
            return
        self.backend = b
        voice_key = '%s|%.2f|%s' % (type(b).__name__, speed, script)
        q = queue.Queue()
        self.cancel_flag = False
        self._busy('Hazırlanıyor…')
        self.cancel_btn = self.app.btn(self.status.master, '■ Durdur', self._cancel, 'ghost')

        def speak(text):
            audio, _secs = b.speech_quick(text, reading_script=script, speed=speed, pause_ms=300, paragraph_pause_ms=gap)
            return audio

        def work():
            try:
                f, p = ff, fp
                if not f:
                    f, p = V.download_ffmpeg(download_to, progress=lambda m: q.put(('msg', m)), cancel=lambda: self.cancel_flag)
                out = V.render(self.proj, speak, f, p, gap_ms=gap, voice_key=voice_key, status=lambda m: q.put(('msg', m)),
                               cancel=lambda: self.cancel_flag)
                q.put(('ok', out))
            except V.Cancelled:
                q.put(('cancel', ''))
            except Exception as e:  # noqa: BLE001
                q.put(('err', str(e)))
        threading.Thread(target=work, daemon=True).start()

        def poll():
            try:
                while True:
                    kind, val = q.get_nowait()
                    if kind == 'msg':
                        self.status.configure(text=val)
                        continue
                    self._done(kind, val)
                    return
            except queue.Empty:
                pass
            if self.winfo_exists():
                self.after(150, poll)
        self.after(150, poll)

    def _cancel(self):
        self.cancel_flag = True
        self.status.configure(text='Durduruluyor…')

    def _done(self, kind, val):
        try:
            self.cancel_btn.destroy()
        except (tk.TclError, AttributeError):
            pass
        if kind == 'ok':
            self.last = val
            self._idle('Video hazır: %s' % val)
            self._fill()
            P = self.P
            row = tk.Frame(self, bg=P['PANEL'], padx=12, pady=4)
            row.pack(fill='x', before=self.status)
            self.app.btn(row, '▶ Videoyu aç', lambda: self.app._open_external(val), 'primary')
            self.app.btn(row, 'Klasörü aç', lambda: self.app._open_external(self.proj['folder']), 'ghost')
            self.app.flash('Video hazır (altyazı görüntüde; subs.srt de klasörde).', 8000)
        elif kind == 'cancel':
            self._idle('Durduruldu. Hazırlanan sesler klasörde kalır; bir dahaki sefer yeniden üretilmez.')
        else:
            self._idle('')
            messagebox.showerror('Video', val, parent=self)
