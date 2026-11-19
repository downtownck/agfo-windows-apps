# -*- coding: utf-8 -*-
"""Isolated, tabbed SSH consoles with optional top/bottom split view.

Tk widgets are only touched from the UI thread. Worker threads use app.msg_queue.
No passwords, keystrokes or terminal output are saved to disk by this module.
"""
from __future__ import annotations

import codecs
from collections import deque
from dataclasses import dataclass, field
import tkinter as tk
from tkinter import ttk, scrolledtext
import uuid


MAX_OUTPUT_CHARS = 140_000


@dataclass
class SessionRecord:
    id: str
    profile: object
    label: str
    status: str = "Bağlanıyor..."
    transport: object = None
    chunks: deque = field(default_factory=deque)
    chars: int = 0
    decoder: object = field(default_factory=lambda: codecs.getincrementaldecoder("utf-8")("replace"))
    closed: bool = False
    cancelled: bool = False

    def append(self, value: str) -> None:
        if not value:
            return
        self.chunks.append(value[-MAX_OUTPUT_CHARS:])
        self.chars += len(self.chunks[-1])
        while self.chars > MAX_OUTPUT_CHARS:
            removed = self.chunks.popleft()
            self.chars -= len(removed)

    def snapshot(self):
        return "".join(self.chunks)


class SessionBook:
    """Small non-GUI session registry; one identifier per SSH connection."""
    def __init__(self):
        self.entries: dict[str, SessionRecord] = {}
        self.order: list[str] = []

    def create(self, profile) -> SessionRecord:
        session_id = uuid.uuid4().hex
        number = 1
        taken = {r.label for r in self.entries.values()}
        label = profile.name
        while label in taken:
            number += 1
            label = profile.name + " #%d" % number
        record = SessionRecord(session_id, profile, label)
        self.entries[session_id] = record
        self.order.append(session_id)
        return record

    def get(self, session_id):
        return self.entries.get(session_id)

    def remove(self, session_id):
        record = self.entries.pop(session_id, None)
        if record:
            record.cancelled = True
            record.closed = True
            if session_id in self.order:
                self.order.remove(session_id)
        return record

    def close_all(self):
        records = list(self.entries.values())
        for record in records:
            record.cancelled = True
            record.closed = True
            if record.transport:
                record.transport.close()
        self.entries.clear()
        self.order.clear()


class ConsolePane(ttk.Frame):
    def __init__(self, master, workspace, *, split=False):
        super().__init__(master, style="White.TFrame")
        self.workspace = workspace
        self.session_id = None
        self.split = split
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(self, style="White.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(4, 5))
        toolbar.columnconfigure(0, weight=1)
        self.status = tk.StringVar(value="Oturum seçilmedi")
        if split:
            self.choice = tk.StringVar()
            self.selector = ttk.Combobox(toolbar, state="readonly", textvariable=self.choice, width=27)
            self.selector.grid(row=0, column=0, sticky="w")
            self.selector.bind("<<ComboboxSelected>>", self._on_selection)
            ttk.Label(toolbar, textvariable=self.status, style="Info.TLabel").grid(row=0, column=1, padx=10)
        else:
            self.selector = None
            ttk.Label(toolbar, textvariable=self.status, style="Info.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(toolbar, text="Bağlantıyı kes", command=self._disconnect).grid(row=0, column=2, padx=4)
        ttk.Button(toolbar, text="Sekmeyi kapat", command=self._remove).grid(row=0, column=3, padx=4)
        self.output = scrolledtext.ScrolledText(self, wrap="word", bg="#101b2e", fg="#dceaff",
             insertbackground="white", font=("Consolas", 10), relief="flat", padx=10, pady=8)
        self.output.grid(row=1, column=0, sticky="nsew")
        self.output.configure(state="disabled")
        line = ttk.Frame(self, style="White.TFrame")
        line.grid(row=2, column=0, sticky="ew", pady=(5, 3))
        line.columnconfigure(0, weight=1)
        self.entry_var = tk.StringVar()
        self.entry = ttk.Entry(line, textvariable=self.entry_var)
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.entry.bind("<Return>", lambda _e: self._send())
        self.entry.bind("<FocusIn>", lambda _e: self.workspace.set_focused(self.session_id))
        ttk.Button(line, text="Gönder", command=self._send).grid(row=0, column=1, padx=(0, 5))
        ttk.Button(line, text="Ctrl+C", command=self._interrupt).grid(row=0, column=2, padx=(0, 5))
        self.hidden = tk.BooleanVar(value=False)
        ttk.Checkbutton(line, text="Girişi gizle", variable=self.hidden,
                        command=self._toggle_hidden).grid(row=0, column=3)

    def _on_selection(self, _event=None):
        name = self.choice.get()
        for session_id in self.workspace.book.order:
            record = self.workspace.book.get(session_id)
            if record and self.workspace.display_name(record) == name:
                self.workspace.set_pane_session(self, session_id)
                return

    def _send(self):
        if self.session_id:
            command = self.entry_var.get()
            self.entry_var.set("")
            self.workspace.send_callback(self.session_id, command + "\n")

    def _interrupt(self):
        if self.session_id:
            self.workspace.interrupt_callback(self.session_id)

    def _disconnect(self):
        if self.session_id:
            self.workspace.disconnect_callback(self.session_id)

    def _remove(self):
        if self.session_id:
            self.workspace.remove_callback(self.session_id)

    def _toggle_hidden(self):
        self.entry.configure(show="*" if self.hidden.get() else "")

    def show_record(self, record):
        self.session_id = record.id if record else None
        self.entry_var.set("")
        self.hidden.set(False)
        self._toggle_hidden()
        self.status.set((record.status + "  ·  " + record.label) if record else "Bir SSH oturumu seçin")
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        if record:
            self.output.insert("end", record.snapshot())
        self.output.see("end")
        self.output.configure(state="disabled")
        self.entry.configure(state="normal" if record and not record.closed and record.transport else "disabled")

    def append(self, value):
        self.output.configure(state="normal")
        self.output.insert("end", value)
        if int(self.output.index("end-1c").split(".")[0]) > 2300:
            self.output.delete("1.0", "500.0")
        self.output.see("end")
        self.output.configure(state="disabled")

    def update_state(self, record):
        if record and self.session_id == record.id:
            self.status.set(record.status + "  ·  " + record.label)
            self.entry.configure(state="normal" if not record.closed and record.transport else "disabled")


class SSHWorkspace(ttk.Frame):
    """Notebook for each connection; alternative splitter renders two simultaneously."""
    def __init__(self, master, *, send_callback, interrupt_callback, disconnect_callback,
                 remove_callback, fresh_callback):
        super().__init__(master, style="White.TFrame")
        self.book = SessionBook()
        self.send_callback = send_callback
        self.interrupt_callback = interrupt_callback
        self.disconnect_callback = disconnect_callback
        self.remove_callback = remove_callback
        self.fresh_callback = fresh_callback
        self.focused_id = None
        self.pages: dict[str, ttk.Frame] = {}
        self.panes: dict[str, ConsolePane] = {}
        self.split_mode = False
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        head = ttk.Frame(self, style="White.TFrame")
        head.grid(row=0, column=0, sticky="ew", padx=12, pady=10)
        ttk.Label(head, text="SSH Oturumları", style="Section.TLabel").pack(side="left")
        ttk.Button(head, text="+ Yeni oturum", command=self.fresh_callback).pack(side="left", padx=(18, 4))
        self.mode_button = ttk.Button(head, text="Alt alta iki oturum", command=self.toggle_split)
        self.mode_button.pack(side="left", padx=4)
        self.note = ttk.Label(head, text="Oturumlar ve komutlar birbirinden bağımsızdır.", style="Info.TLabel")
        self.note.pack(side="right")
        self.notebook = ttk.Notebook(self, style="SSH.TNotebook")
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_selected)
        self.paned = ttk.PanedWindow(self, orient="vertical")
        self.top = ConsolePane(self.paned, self, split=True)
        self.bottom = ConsolePane(self.paned, self, split=True)
        self.paned.add(self.top, weight=1)
        self.paned.add(self.bottom, weight=1)
        self.empty = ttk.Frame(self.notebook, style="White.TFrame")
        ttk.Label(self.empty, text="SSH Sunucularım bölümünden 'Dahili SSH / Parola' ile bir oturum açın.",
                  style="Info.TLabel").pack(expand=True)
        self.notebook.add(self.empty, text="Başlangıç")

    def display_name(self, record):
        return "%s · %s" % (record.label, record.profile.host)

    def set_focused(self, session_id):
        if session_id:
            self.focused_id = session_id

    def add_session(self, profile):
        record = self.book.create(profile)
        record.append("Bağlantı kuruluyor: %s@%s:%s\n" %
                      (profile.username, profile.host, profile.port))
        if self.empty is not None:
            self.notebook.forget(self.empty)
            self.empty.destroy()
            self.empty = None
        page = ttk.Frame(self.notebook, style="White.TFrame")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(0, weight=1)
        pane = ConsolePane(page, self)
        pane.grid(row=0, column=0, sticky="nsew", padx=7, pady=7)
        pane.show_record(record)
        self.pages[record.id] = page
        self.panes[record.id] = pane
        self.notebook.add(page, text=record.label)
        self.notebook.select(page)
        self.focused_id = record.id
        self._refresh_split_choices()
        if self.split_mode:
            available = self.book.order
            for current in (self.top, self.bottom):
                if current.session_id is None:
                    other = self.bottom if current is self.top else self.top
                    next_id = next((sid for sid in available if sid != other.session_id), None)
                    if next_id:
                        self.set_pane_session(current, next_id)
        return record

    def get(self, session_id):
        return self.book.get(session_id)

    def _on_tab_selected(self, _event=None):
        if self.split_mode:
            return
        selected = self.notebook.select()
        for session_id, page in self.pages.items():
            if str(page) == selected:
                self.focused_id = session_id
                return

    def _refresh_split_choices(self):
        names = [self.display_name(self.book.entries[sid]) for sid in self.book.order]
        for pane in (self.top, self.bottom):
            if pane.selector is not None:
                pane.selector.configure(values=names)
                rec = self.book.get(pane.session_id)
                pane.choice.set(self.display_name(rec) if rec else "")

    def set_pane_session(self, pane, session_id):
        if not self.book.get(session_id):
            return
        # The two visible sides should not accidentally mirror the same connection.
        other = self.bottom if pane is self.top else self.top
        if other.session_id == session_id:
            self._refresh_split_choices()
            return
        pane.show_record(self.book.get(session_id))
        pane.choice.set(self.display_name(self.book.get(session_id)))
        self.focused_id = session_id

    def toggle_split(self):
        self.split_mode = not self.split_mode
        if self.split_mode:
            self.notebook.grid_remove()
            self.paned.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))
            ordered = self.book.order
            a = self.focused_id if self.focused_id in ordered else (ordered[0] if ordered else None)
            b = next((sid for sid in ordered if sid != a), None)
            self.top.show_record(self.book.get(a))
            self.bottom.show_record(self.book.get(b))
            self._refresh_split_choices()
            self.mode_button.configure(text="Sekme görünümüne dön")
        else:
            self.paned.grid_remove()
            self.notebook.grid()
            target = self.focused_id
            if target in self.pages:
                self.notebook.select(self.pages[target])
            self.mode_button.configure(text="Alt alta iki oturum")

    def set_status(self, session_id, status, *, transport=None, closed=None):
        record = self.get(session_id)
        if record is None or (record.cancelled and transport is not None):
            if transport:
                transport.close()
            return False
        record.status = status
        if transport is not None:
            record.transport = transport
        if closed is not None:
            record.closed = closed
        for pane in (self.panes.get(session_id), self.top, self.bottom):
            if pane:
                pane.update_state(record)
        return True

    def append(self, session_id, text):
        record = self.get(session_id)
        if record is None:
            return
        record.append(text)
        for pane in (self.panes.get(session_id), self.top, self.bottom):
            if pane and pane.session_id == session_id:
                pane.append(text)

    def remove(self, session_id):
        record = self.book.remove(session_id)
        if record is None:
            return None
        page = self.pages.pop(session_id, None)
        self.panes.pop(session_id, None)
        if page:
            self.notebook.forget(page)
            page.destroy()
        if self.top.session_id == session_id:
            self.top.show_record(None)
        if self.bottom.session_id == session_id:
            self.bottom.show_record(None)
        if self.focused_id == session_id:
            self.focused_id = self.book.order[-1] if self.book.order else None
        if not self.book.order and self.empty is None:
            self.empty = ttk.Frame(self.notebook, style="White.TFrame")
            ttk.Label(self.empty, text="Henüz açık bir SSH oturumu yok.", style="Info.TLabel").pack(expand=True)
            self.notebook.add(self.empty, text="Başlangıç")
        self._refresh_split_choices()
        if self.split_mode:
            current = self.book.order
            for pane in (self.top, self.bottom):
                if not pane.session_id:
                    other = self.bottom if pane is self.top else self.top
                    alternative = next((sid for sid in current if sid != other.session_id), None)
                    if alternative:
                        self.set_pane_session(pane, alternative)
        return record

    def close_all(self):
        self.book.close_all()
