"""AGFO Smart Desktop Organizer — Windows GUI, standard Python tkinter."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from collections import Counter
from update_checker import check_release, download_verified, launch_install
from tkinter import filedialog, messagebox, simpledialog, ttk

from organizer_core import (
    APP_FOLDER, CATEGORIES, TOPIC_FOLDERS, MoveJournal, PlanItem, app_state_dir,
    validate_destination_root, create_topic_folders,
    execute_approved, AICategoryError, list_ollama_models, pick_ollama_model, ollama_refine, scan, standard_roots, valid_subfolder,
)

VERSION = '1.1.1'
BG = '#F4F7FB'
TEXT = '#17283D'
BLUE = '#2363A5'
MUTED = '#52667E'


def set_dpi_awareness():
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (OSError, AttributeError):
            pass


class FolderDialog(tk.Toplevel):
    def __init__(self, parent, folder):
        super().__init__(parent)
        self.title('Önerilen alt klasörü düzenle')
        self.geometry('630x260')
        self.resizable(False, False)
        self.transient(parent)
        self.result = None
        self.folder_var = tk.StringVar(value=folder)
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Seçilen hedef kök (bu pencerede değişmez):').pack(anchor='w')
        ttk.Label(frame, text=str(parent.destination_root or 'HENÜZ SEÇİLMEDİ'),
                  foreground=MUTED, wraplength=580).pack(anchor='w', pady=(4, 14))
        ttk.Label(frame, text='Alt klasör (ör. BRCGS/2026 veya IAS)').pack(anchor='w')
        ttk.Combobox(frame, textvariable=self.folder_var,
                     values=parent.folder_choices()).pack(fill='x', pady=(4, 5))
        ttk.Label(frame, text='Genel Belgeler/Denetimler klasörleri otomatik oluşturulmaz.',
                  foreground=MUTED).pack(anchor='w')
        actions = ttk.Frame(frame)
        actions.pack(fill='x', pady=(20, 0))
        ttk.Button(actions, text='İptal', command=self.destroy).pack(side='right', padx=(8, 0))
        ttk.Button(actions, text='Uygula', style='Primary.TButton', command=self.save).pack(side='right')
        self.bind('<Return>', lambda e: self.save())
        self.bind('<Escape>', lambda e: self.destroy())
        self.wait_visibility()
        self.grab_set()
        self.focus_set()

    def save(self):
        try:
            folder = valid_subfolder(self.folder_var.get())
            if folder.split('/')[0] == 'İncelenecek':
                raise ValueError('Gerçek bir konu/proje klasörü seçin.')
            self.result = folder
            self.destroy()
        except ValueError as exc:
            messagebox.showerror('Hedef geçersiz', str(exc), parent=self)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f'AGFO Smart Desktop Organizer  •  v{VERSION}')
        self.geometry('1320x790')
        self.minsize(980, 610)
        self.configure(bg=BG)
        self.roots = standard_roots()
        self.items: list[PlanItem] = []
        self.by_id: dict[str, PlanItem] = {}
        self.q = queue.Queue()
        self.busy = False
        self.state = app_state_dir()
        self.journal = MoveJournal(self.state / 'moves.sqlite3')
        self.settings_path = self.state / 'settings.json'
        self.latest_release = None
        self.pending_update = None
        self.settings = self._load_settings()
        self.destination_root = None
        saved_destination = self.settings.get('destination_root')
        if saved_destination:
            try:
                self.destination_root = validate_destination_root(saved_destination, self.roots)
                self.roots['Hedef'] = self.destination_root
            except (OSError, ValueError):
                pass  # Old/invalid destination is never silently reused.
        self.destination_var = tk.StringVar(value=str(self.destination_root or 'HEDEF SEÇİLMEDİ — taşımaya izin verilmez'))
        self.custom_folders = set(self.settings.get('custom_folders', []))
        self.hidden_folders = set(self.settings.get('hidden_folders', []))
        self.desktop_var = tk.BooleanVar(value=True)
        self.docs_var = tk.BooleanVar(value=True)
        self.ai_model = tk.StringVar(value=self.settings.get('ollama_model', 'gemma3:1b'))
        self.ai_limit = tk.StringVar(value=str(self.settings.get('ai_limit', '30')))
        self.filter_var = tk.StringVar(value='')
        self.status_filter = tk.StringVar(value='Tümü')
        self.summary_var = tk.StringVar(value='Tarama yapılmadı.')
        self.progress_var = tk.StringVar(value='Hazır.')
        self.preview_var = tk.StringVar(value='İncelemek için bir öğe seçin.')
        self._setup_styles()
        self._build_ui()
        self.filter_var.trace_add('write', lambda *_: self.refresh())
        self.after(110, self._poll_queue)
        self.after(500, self.find_models)

    def _load_settings(self):
        try:
            return json.loads(self.settings_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_settings(self):
        self.state.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(json.dumps({
            'ollama_model': self.ai_model.get().strip(),
            'ai_limit': self.ai_limit.get().strip(),
            'custom_folders': sorted(self.custom_folders),
            'hidden_folders': sorted(self.hidden_folders),
            'destination_root': str(self.destination_root) if self.destination_root else None,
        }, ensure_ascii=False, indent=2), encoding='utf-8')

    def _setup_styles(self):
        style = ttk.Style()
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10), background=BG, foreground=TEXT)
        style.configure('TFrame', background=BG)
        style.configure('TLabel', background=BG, foreground=TEXT)
        style.configure('Heading.TLabel', font=('Segoe UI Semibold', 19), foreground=TEXT)
        style.configure('Sub.TLabel', foreground=MUTED)
        style.configure('Primary.TButton', background=BLUE, foreground='white', padding=(13, 9), font=('Segoe UI Semibold', 10))
        style.map('Primary.TButton', background=[('active', '#164B82'), ('disabled', '#A5B5C7')])
        style.configure('TButton', padding=(10, 8))
        style.configure('Treeview', rowheight=30, font=('Segoe UI', 9), background='white', fieldbackground='white')
        style.configure('Treeview.Heading', font=('Segoe UI Semibold', 9), background='#E7EFF8', padding=(7, 9))
        style.map('Treeview', background=[('selected', '#CDE4FB')], foreground=[('selected', TEXT)])

    def _build_ui(self):
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill='both', expand=True)
        header = ttk.Frame(outer)
        header.pack(fill='x', pady=(0, 12))
        ttk.Label(header, text='AGFO Smart Organizer', style='Heading.TLabel').pack(side='left')
        ttk.Label(header, text='Planla → Düzenle → Onayla → Taşı', style='Sub.TLabel').pack(side='left', padx=(18, 0), pady=(10, 0))
        ttk.Button(header, text='GitHub güncelleme', command=self.check_updates).pack(side='right')

        toolbar = ttk.Frame(outer)
        toolbar.pack(fill='x', pady=(0, 12))
        ttk.Checkbutton(toolbar, text='Masaüstü', variable=self.desktop_var).pack(side='left', padx=(0, 13))
        ttk.Checkbutton(toolbar, text='Belgeler', variable=self.docs_var).pack(side='left', padx=(0, 13))
        self.scan_btn = ttk.Button(toolbar, text='1  Hızlı analiz et', style='Primary.TButton', command=self.start_scan)
        self.scan_btn.pack(side='left', padx=(0, 9))
        self.ai_btn = ttk.Button(toolbar, text='2  Yerel AI ile iyileştir', command=self.start_ai)
        self.ai_btn.pack(side='left', padx=(0, 11))
        ttk.Label(toolbar, text='Ollama modeli:').pack(side='left')
        self.model_combo = ttk.Combobox(toolbar, width=16, textvariable=self.ai_model)
        self.model_combo.pack(side='left', padx=5)
        self.models_btn = ttk.Button(toolbar, text='Modelleri bul', command=self.find_models)
        self.models_btn.pack(side='left', padx=(2, 4))
        ttk.Label(toolbar, text='En çok:').pack(side='left', padx=(6, 2))
        ttk.Entry(toolbar, width=5, textvariable=self.ai_limit).pack(side='left')

        destination_bar = ttk.Frame(outer)
        destination_bar.pack(fill='x', pady=(0, 12))
        ttk.Label(destination_bar, text='HEDEF KÖK KLASÖRÜ:').pack(side='left', padx=(0, 8))
        ttk.Entry(destination_bar, textvariable=self.destination_var,
                  state='readonly').pack(side='left', fill='x', expand=True, padx=(0, 8))
        ttk.Button(destination_bar, text='Hedef klasörü seç...',
                   style='Primary.TButton', command=self.choose_destination).pack(side='left', padx=(0, 7))
        ttk.Button(destination_bar, text='20 ana klasörü oluştur',
                   command=self.create_topics).pack(side='left')

        controls = ttk.Frame(outer)
        controls.pack(fill='x', pady=(0, 10))
        ttk.Label(controls, text='Dosya ara:').pack(side='left')
        ttk.Entry(controls, width=33, textvariable=self.filter_var).pack(side='left', padx=(7, 14))
        ttk.Label(controls, text='Durum:').pack(side='left')
        filters = ('Tümü', 'Bekliyor', 'Kabul', 'Red', 'Taşındı', 'Hata')
        status = ttk.Combobox(controls, width=14, state='readonly', values=filters, textvariable=self.status_filter)
        status.pack(side='left', padx=(7, 8))
        status.bind('<<ComboboxSelected>>', lambda e: self.refresh())
        ttk.Button(controls, text='Hedefi değiştir', command=self.edit_selected).pack(side='right', padx=(6, 0))
        ttk.Button(controls, text='Kaynağı aç', command=self.open_folder).pack(side='right')
        ttk.Button(controls, text='Hedefi aç', command=self.open_target).pack(side='right', padx=(0, 6))
        ttk.Button(controls, text='Klasör planı', command=self.show_folder_plan).pack(side='right', padx=(0, 6))
        ttk.Button(controls, text='Klasörleri yönet', command=self.manage_folders).pack(side='right', padx=(0, 6))

        tree_frame = ttk.Frame(outer)
        tree_frame.pack(fill='both', expand=True)
        columns = ('name', 'source', 'kind', 'folder', 'destination', 'confidence', 'decision')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='headings', selectmode='extended')
        headers = {'name': 'Dosya / kısayol', 'source': 'Konum', 'kind': 'Tür',
                   'folder': 'Kategori', 'destination': 'Önerilen hedef', 'confidence': 'Güven', 'decision': 'Karar'}
        widths = {'name': 260, 'source': 95, 'kind': 75, 'folder': 115,
                  'destination': 405, 'confidence': 65, 'decision': 90}
        for key in columns:
            self.tree.heading(key, text=headers[key], command=lambda col=key: self.sort_column(col))
            self.tree.column(key, width=widths[key], minwidth=60, stretch=(key in ('name', 'destination')),
                             anchor='center' if key in ('confidence', 'decision', 'source') else 'w')
        yscroll = ttk.Scrollbar(tree_frame, orient='vertical', command=self.tree.yview)
        xscroll = ttk.Scrollbar(tree_frame, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        yscroll.grid(row=0, column=1, sticky='ns')
        xscroll.grid(row=1, column=0, sticky='ew')
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)
        self.tree.tag_configure('accepted', foreground='#146A3D')
        self.tree.tag_configure('rejected', foreground='#A24A42')
        self.tree.tag_configure('moved', foreground='#5B6678')
        self.tree.tag_configure('warning', foreground='#A56518')
        self.tree.bind('<<TreeviewSelect>>', lambda _: self.update_preview())
        self.tree.bind('<Double-1>', lambda _: self.edit_selected())

        commands = ttk.Frame(outer)
        commands.pack(fill='x', pady=(11, 6))
        ttk.Button(commands, text='Seçilenleri kabul et', command=lambda: self.set_decision('Kabul', False)).pack(side='left', padx=(0, 7))
        ttk.Button(commands, text='Seçilenleri reddet', command=lambda: self.set_decision('Red', False)).pack(side='left', padx=(0, 17))
        ttk.Button(commands, text='TÜMÜNÜ kabul et', command=lambda: self.set_decision('Kabul', True)).pack(side='left', padx=(0, 7))
        ttk.Button(commands, text='TÜMÜNÜ reddet', command=lambda: self.set_decision('Red', True)).pack(side='left')
        self.apply_btn = ttk.Button(commands, text='3  ONAYLANANLARI TAŞI', style='Primary.TButton', command=self.apply_moves)
        self.apply_btn.pack(side='right')
        ttk.Button(commands, text='Son taşımayı geri al', command=self.undo_last).pack(side='right', padx=(0, 9))
        ttk.Button(commands, text='Hedef ana klasörü aç', command=self.open_managed_root).pack(side='right', padx=(0, 9))

        summary = ttk.Frame(outer)
        summary.pack(fill='x', pady=(3, 8))
        ttk.Label(summary, textvariable=self.summary_var, font=('Segoe UI Semibold', 10)).pack(side='left')
        ttk.Label(summary, textvariable=self.progress_var, style='Sub.TLabel').pack(side='right')
        detail = ttk.LabelFrame(outer, text='Öğe bilgisi / içerik örneği', padding=7)
        detail.pack(fill='x', pady=(0, 3))
        self.preview = tk.Text(detail, height=4, wrap='word', bg='white', relief='flat', fg=TEXT,
                               font=('Segoe UI', 9), state='disabled')
        self.preview.pack(fill='x')
        self._set_preview('İncelemek için bir öğe seçin. Hedefi çift tıklayarak veya Hedefi değiştir ile düzenleyebilirsiniz.')
        ttk.Label(outer, text='Taşıma yalnızca yukarıda seçtiğiniz köke yapılır. DOC-COP / çöp klasörleri hedef olamaz.',
                  foreground=MUTED).pack(anchor='w', pady=(3, 0))

    def _set_preview(self, value):
        self.preview.configure(state='normal')
        self.preview.delete('1.0', 'end')
        self.preview.insert('1.0', value)
        self.preview.configure(state='disabled')

    def update_preview(self):
        selected = self.selected_items()
        if not selected:
            self._set_preview('İncelemek için bir öğe seçin.')
            return
        item = selected[0]
        if item.folder == 'İncelenecek':
            target = 'BELİRSİZ — kullanıcı konu klasörü seçene kadar taşınmaz'
        elif not self.destination_root:
            target = 'HEDEF KÖK SEÇİLMEDİ'
        else:
            try:
                target = str(item.target(self.roots))
            except ValueError as exc:
                target = f'GEÇERSİZ: {exc}'
        text = f'Kaynak: {item.path}\nÖneri nedeni: {item.reason} | Hedef: {target}'
        if item.snippet:
            text += '\nİçerik örneği: ' + item.snippet[:700].replace('\n', ' ')
        if len(selected) > 1:
            text += f'\nToplam {len(selected)} öğe seçili.'
        self._set_preview(text)

    def selected_items(self):
        return [self.by_id[i] for i in self.tree.selection() if i in self.by_id]

    def _worker(self, kind, fn):
        if self.busy:
            return
        self.busy = True
        self.progress_var.set('İşlem sürüyor...')
        self.scan_btn.configure(state='disabled')
        self.ai_btn.configure(state='disabled')
        self.models_btn.configure(state='disabled')
        self.apply_btn.configure(state='disabled')
        def work():
            try:
                result = fn()
                self.q.put((kind, result))
            except Exception as exc:
                self.q.put(('error', str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == 'progress':
                    self.progress_var.set(str(payload))
                    continue
                if kind == 'model_selected':
                    self.ai_model.set(str(payload))
                    self._save_settings()
                    continue
                self.busy = False
                self.scan_btn.configure(state='normal')
                self.ai_btn.configure(state='normal')
                self.models_btn.configure(state='normal')
                self.apply_btn.configure(state='normal')
                if kind == 'updates':
                    self.latest_release = payload
                    if payload:
                        self.show_text_window('Yeni GitHub sürümü', f"Yeni sürüm: {payload['version']}\n\n{payload['notes']}")
                        self.after(250, self.download_update)
                    else:
                        messagebox.showinfo('GitHub güncelleme', 'En güncel sürüm yüklü veya yeni yayın yok.')
                elif kind == 'update_download':
                    self.pending_update = payload
                    self.progress_var.set(f'Güncelleme indirildi: {payload}')
                    self.after(250, self.install_update)
                elif kind == 'models':
                    models, at_start, failure = payload
                    self.model_combo.configure(values=models)
                    if failure:
                        self.progress_var.set(failure)
                    elif models:
                        current = self.ai_model.get().strip()
                        # Do not replace an explicit edit made while the model scan was running.
                        if current == at_start:
                            chosen = pick_ollama_model(current, models)
                            if chosen != current:
                                self.ai_model.set(chosen)
                                self._save_settings()
                        self.progress_var.set('Ollama modelleri: ' + ', '.join(models[:5]))
                    else:
                        self.progress_var.set('Ollama çalışıyor ancak hiç model indirilmemiş. KUR-GEMMA.cmd çalıştırın.')
                elif kind == 'scan':
                    self.items, warnings = payload
                    for item in self.items:
                        if item.folder in self.hidden_folders:
                            item.category = item.folder = 'İncelenecek'
                            item.reason = 'Bu klasör kullanıcı tarafından gizlendi'
                    self.by_id = {it.item_id: it for it in self.items}
                    self.refresh()
                    self.progress_var.set(f'Tarama tamamlandı: {len(self.items)} öğe')
                    if warnings:
                        messagebox.showwarning('Tarama notları', '\n'.join(warnings[:12]))
                elif kind == 'ai':
                    updated, warnings = payload
                    self.refresh()
                    self.progress_var.set(f'AI: {updated} öneri güncellendi')
                    if warnings:
                        messagebox.showwarning('AI notları', '\n'.join(warnings[:5]))
                elif kind == 'move':
                    count, errors, batch = payload
                    self.refresh()
                    self.progress_var.set(f'{count} öğe taşındı; {len(errors)} hata')
                    self.show_move_result(count, errors, batch)
                elif kind == 'undo':
                    count, errors = payload
                    self.progress_var.set(f'{count} öğe geri alındı; {len(errors)} hata')
                    messagebox.showinfo('Geri alma sonucu', f'Geri alınan: {count}\nHata: {len(errors)}\n\n' + '\n'.join(errors[:12]))
                    # Clear stale suggestions after restoring source paths.
                    self.items = []
                    self.by_id.clear()
                    self.refresh()
                elif kind == 'error':
                    self.progress_var.set('İşlem başarısız.')
                    messagebox.showerror('Hata', str(payload))
        except queue.Empty:
            pass
        self.after(110, self._poll_queue)

    def start_scan(self):
        labels = [name for name, flag in [('Masaüstü', self.desktop_var), ('Belgeler', self.docs_var)] if flag.get()]
        if not labels:
            messagebox.showwarning('Kaynak seçimi', 'En az bir kaynak konum seçin.')
            return
        if any(it.decision == 'Kabul' for it in self.items):
            if not messagebox.askyesno('Planı yenile', 'Henüz uygulanmamış onaylar kaybolacak. Yeniden taransın mı?'):
                return
        self._worker('scan', lambda: scan(self.roots, labels,
                     progress=lambda n: self.q.put(('progress', f'{n} öğe incelendi...'))))

    def find_models(self):
        if self.busy:
            return
        selected = self.ai_model.get().strip()
        def work():
            try:
                return list_ollama_models(), selected, None
            except RuntimeError as exc:
                return [], selected, str(exc)
        self._worker('models', work)

    def start_ai(self):
        candidates = [i for i in self.items if i.decision == 'Bekliyor' and i.confidence < 0.90 and not i.is_dir]
        if not candidates:
            messagebox.showinfo('AI', 'AI ile incelenecek bekleyen/belirsiz öğe bulunamadı. Önce tarama yapın.')
            return
        try:
            limit = int(self.ai_limit.get())
            if not 1 <= limit <= 200:
                raise ValueError()
        except ValueError:
            messagebox.showerror('AI', 'AI öğe sınırı 1-200 arasında olmalıdır.')
            return
        model = self.ai_model.get().strip()
        if not model:
            messagebox.showerror('AI', 'Ollama model adını girin.')
            return
        candidates = candidates[:limit]
        self._save_settings()
        def work():
            try:
                models = list_ollama_models()
            except RuntimeError as exc:
                return 0, [str(exc)]
            if not models:
                return 0, ['Ollama çalışıyor fakat hiç model indirilmemiş. KUR-GEMMA.cmd çalıştırın.']
            selected = pick_ollama_model(model, models)
            if selected != model:
                self.q.put(('model_selected', selected))
                self.q.put(('progress', f'{model} yüklü değil; kurulu {selected} modeli seçildi.'))
            changed = 0
            warnings = []
            invalid_count = 0
            for n, item in enumerate(candidates, 1):
                self.q.put(('progress', f'Yerel AI: {n}/{len(candidates)} — {item.path.name[:30]}'))
                try:
                    cat, conf, reason = ollama_refine(item, model=selected)
                    # Worker changes objects; main UI reads after completion only.
                    # Prefer user topical folder over generic model response.
                    from organizer_core import topical_folder
                    topic = topical_folder(item.path.stem, item.snippet)
                    choice = topic or cat
                    if choice in self.hidden_folders:
                        choice = 'İncelenecek'
                    if 'Hedef kullanıcı tarafından düzenlendi' in item.reason:
                        continue  # Respect the user's explicit folder selection.
                    item.category = choice
                    item.folder = choice if choice in TOPIC_FOLDERS or choice in self.custom_folders else 'İncelenecek'
                    item.confidence = conf
                    item.reason = reason if item.folder != 'İncelenecek' else reason + ' | Konu belirsiz; dosya yerinde kalır'
                    changed += 1
                    invalid_count = 0
                except AICategoryError as exc:
                    invalid_count += 1
                    if len(warnings) < 3:
                        warnings.append(f'{item.path.name}: {exc}')
                    if invalid_count >= 3:
                        warnings.append('Model art arda 3 geçersiz yanıt verdi; CPU üzerinde daha fazla zaman '
                                        'harcamamak için AI analizi durduruldu. Önceki öneriler korundu.')
                        break
                except Exception as exc:
                    warnings.append(f'{item.path.name}: {exc}')
                    # Connection/model errors affect all subsequent files.
                    if changed == 0 and n == 1:
                        break
            return changed, warnings
        self._worker('ai', work)

    def sort_column(self, column):
        if self.busy:
            return
        direction = getattr(self, '_sort_direction', (None, False))
        reverse = not direction[1] if direction[0] == column else False
        self._sort_direction = (column, reverse)
        # Re-order visible entries without changing approvals or internal plan.
        rows = [(self.tree.set(iid, column), iid) for iid in self.tree.get_children('')]
        if column == 'confidence':
            rows.sort(key=lambda p: float(p[0].replace('%', '') or '0'), reverse=reverse)
        else:
            rows.sort(key=lambda p: p[0].casefold(), reverse=reverse)
        for rank, (_, iid) in enumerate(rows):
            self.tree.move(iid, '', rank)

    def refresh(self):
        selection = set(self.tree.selection())
        needle = self.filter_var.get().strip().casefold()
        required = self.status_filter.get()
        self.tree.delete(*self.tree.get_children())
        for item in self.items:
            if required != 'Tümü' and item.decision != required:
                continue
            if needle and needle not in (item.path.name + ' ' + item.folder + ' ' + str(item.path)).casefold():
                continue
            label = 'Masaüstü' if item.path.parent == self.roots['Masaüstü'] else 'Belgeler'
            if item.folder == 'İncelenecek':
                target = 'İncelenecek — dosya yerinde kalacak'
            elif not self.destination_root:
                target = 'ÖNCE HEDEF KÖK KLASÖRÜ SEÇİN'
            else:
                try:
                    target = str(item.target(self.roots).parent)
                except ValueError as exc:
                    target = 'GEÇERSİZ: ' + str(exc)
            tag = {'Kabul': 'accepted', 'Red': 'rejected', 'Taşındı': 'moved', 'Hata': 'warning'}.get(item.decision, '')
            self.tree.insert('', 'end', iid=item.item_id, values=(
                item.path.name, label, 'Klasör' if item.is_dir else (item.path.suffix.lower() or 'Dosya'),
                item.category, target, f'{int(item.confidence*100)}%', item.decision), tags=(tag,))
        keep = tuple(i for i in selection if self.tree.exists(i))
        if keep:
            self.tree.selection_set(keep)
        counts = {status: sum(x.decision == status for x in self.items) for status in
                  ('Bekliyor', 'Kabul', 'Red', 'Taşındı', 'Hata')}
        self.summary_var.set('Toplam {total}   •   Bekliyor {Bekliyor}   •   Kabul {Kabul}   •   Red {Red}   •   Taşındı {Taşındı}   •   Hata {Hata}'.format(total=len(self.items), **counts))
        self.update_preview()

    def set_decision(self, decision, all_items):
        if self.busy:
            return
        # ALL means whole current plan, including filtered-out rows.
        candidates = self.items if all_items else self.selected_items()
        changed = 0
        skipped = 0
        for item in candidates:
            if item.decision in ('Bekliyor', 'Kabul', 'Red', 'Hata'):
                if decision == 'Kabul' and item.folder == 'İncelenecek':
                    skipped += 1
                    continue
                item.decision = decision
                changed += 1
        if not candidates and not all_items:
            messagebox.showinfo('Seçim', 'Önce bir veya daha fazla öğe seçin.')
        self.refresh()
        self.progress_var.set(f'{changed} karar güncellendi. {skipped} belirsiz öğe kabul edilmedi.')

    def folder_choices(self):
        return sorted((set(TOPIC_FOLDERS) | self.custom_folders |
                       {it.folder for it in self.items if it.decision != 'Taşındı' and it.folder != 'İncelenecek'})
                      - self.hidden_folders)

    def manage_folders(self):
        """Manage proposed folders only; never rename or delete physical folders."""
        if self.busy:
            return
        dialog = tk.Toplevel(self)
        dialog.title('Klasörleri yönet - yalnızca taşıma planı')
        dialog.geometry('630x510')
        dialog.transient(self)
        frame = ttk.Frame(dialog, padding=14)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Bu ekran diskteki klasörleri silmez. Yalnızca önerileri değiştirir.',
                  foreground=MUTED).pack(anchor='w', pady=(0, 9))
        box = tk.Listbox(frame, height=18, font=('Segoe UI', 10), exportselection=False)
        box.pack(fill='both', expand=True)
        def selected():
            sel = box.curselection()
            return box.get(sel[0]).split('   (')[0] if sel else None
        def reload_list():
            old = selected()
            box.delete(0, 'end')
            counts = Counter(it.folder for it in self.items if it.decision != 'Taşındı')
            for folder in self.folder_choices():
                box.insert('end', f'{folder}   ({counts.get(folder, 0)} öğe)')
            for i in range(box.size()):
                if old and box.get(i).startswith(old + '   ('):
                    box.selection_set(i)
                    break
        def add():
            name = simpledialog.askstring('Yeni klasör', 'Yeni öneri klasörü adı:', parent=dialog)
            if name is None:
                return
            try:
                name = valid_subfolder(name)
            except ValueError as exc:
                messagebox.showerror('Geçersiz ad', str(exc), parent=dialog)
                return
            self.custom_folders.add(name)
            self.hidden_folders.discard(name)
            self._save_settings()
            reload_list()
        def remap(merge=False):
            old = selected()
            if not old:
                messagebox.showinfo('Klasör seçin', 'Önce listeden bir klasör seçin.', parent=dialog)
                return
            new = simpledialog.askstring('Klasörleri birleştir' if merge else 'Yeniden adlandır',
                                         'Yeni hedef klasör adı:', initialvalue='' if merge else old,
                                         parent=dialog)
            if new is None:
                return
            try:
                new = valid_subfolder(new)
            except ValueError as exc:
                messagebox.showerror('Geçersiz ad', str(exc), parent=dialog)
                return
            if new == old:
                return
            count = 0
            for item in self.items:
                if item.decision == 'Taşındı':
                    continue
                if item.folder == old or item.folder.startswith(old + '/'):
                    item.folder = new + item.folder[len(old):]
                    item.category = item.folder.split('/')[0]
                    item.reason += ' | Klasör kullanıcı tarafından değiştirildi'
                    count += 1
            self.custom_folders.add(new)
            self.hidden_folders.discard(new)
            self.hidden_folders.add(old)
            self.custom_folders.discard(old)
            self._save_settings()
            self.refresh()
            reload_list()
            self.progress_var.set(f'{count} öğenin hedefi değiştirildi.')
        def hide():
            old = selected()
            if not old:
                return
            if old == 'İncelenecek':
                messagebox.showinfo('Klasör', 'İncelenecek klasörü gizlenemez.', parent=dialog)
                return
            if not messagebox.askyesno('Klasörü plandan kaldır',
                                       f'{old} önerilerden gizlensin mi? Bu klasöre planlanan dosyalar '
                                       'İncelenecek klasörüne yönlendirilecek. Diskte dosya silinmez.', parent=dialog):
                return
            self.hidden_folders.add(old)
            self.custom_folders.discard(old)
            for item in self.items:
                if item.decision != 'Taşındı' and (item.folder == old or item.folder.startswith(old + '/')):
                    item.folder = item.category = 'İncelenecek'
                    item.reason += ' | Klasör plandan kaldırıldı'
            self._save_settings()
            self.refresh()
            reload_list()
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x', pady=(10, 0))
        ttk.Button(buttons, text='Yeni', command=add).pack(side='left', padx=(0, 5))
        ttk.Button(buttons, text='Yeniden adlandır', command=lambda: remap(False)).pack(side='left', padx=(0, 5))
        ttk.Button(buttons, text='Birleştir', command=lambda: remap(True)).pack(side='left', padx=(0, 5))
        ttk.Button(buttons, text='Plandan kaldır', command=hide).pack(side='left')
        ttk.Button(buttons, text='Kapat', command=dialog.destroy).pack(side='right')
        reload_list()

    def edit_selected(self):
        if self.busy:
            return
        selected = [it for it in self.selected_items() if it.decision != 'Taşındı']
        if not selected:
            messagebox.showinfo('Hedef', 'Önce düzenlenecek öğeyi/öğeleri seçin.')
            return
        dialog = FolderDialog(self, selected[0].folder)
        self.wait_window(dialog)
        if not dialog.result:
            return
        folder = dialog.result
        for item in selected:
            item.folder = folder
            item.category = folder.split('/')[0]
            item.reason += ' | Hedef kullanıcı tarafından düzenlendi'
        self.refresh()
        self.progress_var.set(f'{len(selected)} öğenin hedefi güncellendi.')

    def open_folder(self):
        items = self.selected_items()
        if not items:
            messagebox.showinfo('Klasör', 'Önce bir öğe seçin.')
            return
        item = items[0]
        folder = item.path.parent
        try:
            if sys.platform == 'win32':
                subprocess.Popen(['explorer', f'/select,{item.path}'])
            else:
                messagebox.showinfo('Klasör', str(folder))
        except OSError as exc:
            messagebox.showerror('Klasör', str(exc))

    def open_path(self, path):
        try:
            if sys.platform == 'win32':
                os.startfile(str(path))
            else:
                messagebox.showinfo('Klasör konumu', str(path))
        except OSError as exc:
            messagebox.showerror('Klasör açılamadı', str(exc))

    def choose_destination(self):
        if self.busy:
            return
        chosen = filedialog.askdirectory(parent=self, title='Dosyaların taşınacağı ANA klasörü seçin',
                                         initialdir=str(self.destination_root or Path.home()), mustexist=True)
        if not chosen:
            return
        try:
            base = validate_destination_root(chosen, self.roots)
        except (OSError, ValueError) as exc:
            messagebox.showerror('Hedef kök reddedildi', str(exc), parent=self)
            return
        if self.destination_root == base:
            return
        if self.items and not messagebox.askyesno('Hedef değişikliği',
                'Hedef kök değişirse mevcut plan temizlenecek ve yeniden tarama gerekecek. '
                'Önceden taşınan dosyalara dokunulmaz. Devam edilsin mi?', parent=self):
            return
        self.destination_root = base
        self.roots['Hedef'] = base
        self.destination_var.set(str(base))
        self.items = []
        self.by_id.clear()
        self._save_settings()
        self.refresh()
        self.progress_var.set('Hedef seçildi. Şimdi Hızlı analiz et ile yeni plan oluşturun.')

    def create_topics(self):
        if self.busy:
            return
        if not self.destination_root:
            messagebox.showwarning('Hedef seçilmedi', 'Önce Hedef klasörü seç... düğmesini kullanın.')
            return
        if not messagebox.askyesno('20 ana klasörü oluştur',
                f'Şu konumda 20 ana klasör oluşturulsun mu?\n\n{self.destination_root}\n\n'
                + ', '.join(TOPIC_FOLDERS) + '\n\nDosyalar taşınmaz, mevcut klasörler silinmez.',
                parent=self):
            return
        try:
            created = create_topic_folders(self.roots)
        except (OSError, ValueError) as exc:
            messagebox.showerror('Klasör oluşturulamadı', str(exc), parent=self)
            return
        messagebox.showinfo('Klasörler hazır', f'{len(created)} ana klasör kontrol edildi/oluşturuldu.\n{self.destination_root}', parent=self)
        self.open_path(self.destination_root)

    def open_managed_root(self):
        if not self.destination_root:
            messagebox.showwarning('Hedef seçilmedi', 'Önce Hedef klasörü seç... düğmesini kullanın.')
            return
        self.open_path(self.destination_root)

    def open_target(self):
        selected = self.selected_items()
        if not selected:
            self.open_managed_root()
            return
        if selected[0].folder == 'İncelenecek':
            messagebox.showinfo('Konu belirsiz', 'Bu dosyaya önce bir konu/proje klasörü seçin.')
            return
        if not self.destination_root:
            messagebox.showwarning('Hedef seçilmedi', 'Önce Hedef klasörü seç... düğmesini kullanın.')
            return
        try:
            parent = selected[0].target(self.roots).parent
        except ValueError as exc:
            messagebox.showerror('Hedef', str(exc))
            return
        if parent.is_dir():
            self.open_path(parent)
        else:
            messagebox.showinfo('Önerilen hedef (henüz yok)', str(parent))

    def show_folder_plan(self):
        window = tk.Toplevel(self)
        window.title('20 ana klasör - gerçek hedef ağacı')
        window.geometry('1000x680')
        outer = ttk.Frame(window, padding=12)
        outer.pack(fill='both', expand=True)
        root_text = str(self.destination_root or 'HEDEF SEÇİLMEDİ — dosyalar taşınamaz')
        ttk.Label(outer, text='Hedef kök: ' + root_text, wraplength=920).pack(anchor='w', pady=(0, 8))
        ttk.Label(outer, text='Aşağıdaki 20 klasör sizin çalışma yapınızdır. '
                  'Sıfır öğeli klasörler taşıma sırasında kendiliğinden oluşturulmaz.',
                  foreground=MUTED).pack(anchor='w', pady=(0, 8))
        tree = ttk.Treeview(outer, columns=('count', 'path'), show='tree headings')
        tree.heading('#0', text='Klasör / Dosya')
        tree.heading('count', text='Öğe')
        tree.heading('path', text='Gerçek hedef yolu')
        tree.column('#0', width=255)
        tree.column('count', width=60, anchor='center')
        tree.column('path', width=610)
        tree.pack(fill='both', expand=True)
        approved = [it for it in self.items if it.decision in ('Bekliyor', 'Kabul')]
        base_node = tree.insert('', 'end', text='HEDEF KÖK', values=('', root_text), open=True)
        folder_names = [f for f in TOPIC_FOLDERS if f not in self.hidden_folders]
        additional = {it.folder.split('/')[0] for it in approved if it.folder != 'İncelenecek'}
        folder_names += sorted((self.custom_folders | additional) - set(folder_names) - self.hidden_folders)
        for folder in folder_names:
            members = [it for it in approved if it.folder == folder or it.folder.startswith(folder + '/')]
            folder_path = str(self.destination_root / folder) if self.destination_root else '(hedef seçilmedi)'
            branch = tree.insert(base_node, 'end', text=folder,
                                 values=(len(members), folder_path), open=False)
            for item in members:
                path = str(item.target(self.roots)) if self.destination_root else '(hedef seçilmedi)'
                tree.insert(branch, 'end', text=item.path.name, values=(item.decision, path))
        review = [it for it in approved if it.folder == 'İncelenecek']
        if review:
            branch = tree.insert('', 'end', text='İNCELENECEK — TAŞINMAZ',
                                 values=(len(review), 'Mevcut konumda kalır'), open=False)
            for item in review:
                tree.insert(branch, 'end', text=item.path.name, values=('Bekliyor', str(item.path)))
        ttk.Button(outer, text='Kapat', command=window.destroy).pack(pady=(10, 0))

    def show_text_window(self, title, content):
        window = tk.Toplevel(self)
        window.title(title)
        window.geometry('990x550')
        area = tk.Text(window, wrap='none', font=('Consolas', 10))
        area.pack(fill='both', expand=True, padx=12, pady=12)
        area.insert('1.0', content)
        area.configure(state='disabled')
        ttk.Button(window, text='Kapat', command=window.destroy).pack(pady=(0, 12))

    def show_move_result(self, count, errors, batch):
        moved = [it for it in self.items if it.decision == 'Taşındı']
        targets = sorted({str(it.target(self.roots).parent) for it in moved})
        lines = [f'Taşınan: {count} | Hata: {len(errors)} | İşlem: {batch[:8]}', '',
                 'OLUŞTURULAN / KULLANILAN HEDEF KLASÖRLER:', *targets,
                 '', 'TAŞINAN DOSYALAR:',
                 *(f'{it.path.name}  ->  {it.target(self.roots)}' for it in moved),
                 '', 'HATALAR:', *errors]
        self.show_text_window('Taşıma sonucu ve gerçek hedef yolları', '\n'.join(lines))
        if targets and messagebox.askyesno('Hedef klasörü aç',
                                            'Taşıma tamamlandı. İlk hedef klasör Windows Explorer ile açılsın mı?'):
            self.open_path(Path(targets[0]))

    def check_updates(self):
        if self.busy:
            return
        self._worker('updates', lambda: check_release(VERSION))

    def install_update(self):
        archive = self.pending_update
        if not archive:
            return
        if not messagebox.askyesno('Güncellemeyi kur',
                                   f'Doğrulanan sürüm indirildi:\n{archive}\n\n'
                                   'Uygulama kapanacak; eski program dosyaları yedeklenip yenileri kurulacak. '
                                   'Ayarlar, Ollama ve taşıma geçmişi korunur.\n\n'
                                   'Şimdi kuruluma geçilsin mi?'):
            self.open_path(archive.parent)
            return
        try:
            app_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
            launch_install(archive, app_dir, os.getpid())
        except Exception as exc:
            messagebox.showerror('Güncelleme başlatılamadı', str(exc))
            return
        self.destroy()

    def download_update(self):
        release = self.latest_release
        if not release:
            return
        if not messagebox.askyesno('GitHub güncelleme',
                                   f"{release['version']} doğrulanmış ZIP olarak indirilsin mi?\n"
                                   'Uygulama dosyalarına otomatik müdahale edilmez.'):
            return
        self._worker('update_download', lambda: download_verified(release, self.state / 'updates'))

    def apply_moves(self):
        if self.busy:
            return
        approved = [it for it in self.items if it.decision == 'Kabul']
        if not approved:
            messagebox.showinfo('Uygula', 'Taşınacak kabul edilmiş öğe bulunmuyor.')
            return
        try:
            if not self.destination_root:
                raise ValueError('Önce Hedef klasörü seç... düğmesiyle gerçek hedef kökü seçin.')
            validate_destination_root(self.destination_root, self.roots)
            planned = [(it, it.target(self.roots)) for it in approved]
        except (OSError, ValueError) as exc:
            messagebox.showerror('Taşıma durduruldu', str(exc))
            return
        preview = '\n'.join(f'{it.path.name}  ->  {dst}' for it, dst in planned[:7])
        if len(planned) > 7:
            preview += f'\n... ve {len(planned)-7} dosya daha (Klasör planı ekranında tamamını görebilirsiniz)'
        question = (f'{len(planned)} dosya/klasör taşınacak.\n\n'
                    f'SEÇİLEN HEDEF KÖK:\n{self.destination_root}\n\n'
                    f'İLK HEDEFLER:\n{preview}\n\n'
                    'Kısayollar taşınırsa masaüstü simgeleri kaybolabilir. '
                    'OneDrive hedeflerinde eşitleme yapılabilir.\n\n'
                    'Dosyaların üzerine yazılmaz; geri alma kaydı tutulur.\n\n'
                    'BU HEDEF KÖKE TAŞIMAYI ONAYLIYOR MUSUNUZ?')
        if not messagebox.askyesno('Gerçek hedefleri onaylayın', question, icon='warning'):
            return
        self._worker('move', lambda: execute_approved(
            approved, self.roots, self.journal,
            progress=lambda n: self.q.put(('progress', f'{n}/{len(approved)} taşındı...'))))

    def undo_last(self):
        if self.busy:
            return
        batch = self.journal.latest_batch()
        if not batch:
            messagebox.showinfo('Geri al', 'Geri alınabilecek kayıt bulunmuyor.')
            return
        if not messagebox.askyesno('Son taşımayı geri al',
                                  'Son taşımada kaydedilen bütün öğeler eski konumlarına döndürülecek. '
                                  'Özgün konumda aynı adlı bir öğe varsa atlanacaktır. Devam edilsin mi?'):
            return
        self._worker('undo', lambda: self.journal.undo(batch))


def main():
    set_dpi_awareness()
    app = App()
    app.mainloop()


if __name__ == '__main__':
    main()
