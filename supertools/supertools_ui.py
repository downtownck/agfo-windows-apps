# -*- coding: utf-8 -*-
"""Tkinter views for AGFO SuperTools and per-user SSH bookmarks.

The host application supplies .tabs, .msg_queue, ._log, .status_var and
._selected; GUI changes always run on the main thread.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import codecs
import re
from pathlib import Path
import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import supertools_core as diag
import ssh_profiles as sshdata
import ssh_password_vault as sshvault
import ssh_password_transport as sshtransport
from ssh_workspace import SSHWorkspace


class SuperToolsMixin:
    def _build_supertools_tab(self):
        page = self.tab_supertools
        page.columnconfigure(0, weight=1)
        page.rowconfigure(5, weight=1)
        title = ttk.Frame(page, style="White.TFrame")
        title.grid(row=0, column=0, sticky="ew", padx=14, pady=(15, 7))
        ttk.Label(title, text="AGFO SuperTools", style="Section.TLabel").pack(side="left")
        ttk.Label(title, text="Yerel ağ + İnternet · Tek komut / tek sonuç", style="Info.TLabel").pack(side="right")
        form = ttk.Frame(page, style="White.TFrame")
        form.grid(row=1, column=0, sticky="ew", padx=14, pady=5)
        form.columnconfigure(2, weight=1)
        ttk.Label(form, text="Test", style="White.TLabel").grid(row=0, column=0, sticky="w")
        self.diag_tool_var = tk.StringVar(value="DNS MX")
        self.diag_tool_combo = ttk.Combobox(form, state="readonly", width=22, textvariable=self.diag_tool_var,
                                           values=diag.TOOL_OPTIONS)
        self.diag_tool_combo.grid(row=1, column=0, padx=(0, 12), sticky="w", pady=(6, 0))
        ttk.Label(form, text="Komut / alan adı / IP", style="White.TLabel").grid(row=0, column=2, sticky="w")
        self.diag_input_var = tk.StringVar(value="agfocert.com")
        self.diag_entry = ttk.Entry(form, textvariable=self.diag_input_var, font=("Consolas", 11))
        self.diag_entry.grid(row=1, column=2, sticky="ew", pady=(6, 0))
        self.diag_entry.bind("<Return>", lambda _event: self._run_diagnostic())
        self.diag_run_btn = ttk.Button(form, text="Çalıştır", style="Blue.TButton", command=self._run_diagnostic)
        self.diag_run_btn.grid(row=1, column=3, padx=(9, 0), pady=(6, 0))
        ttk.Label(page, text="Tek kutuda örnekler:  mx: agfocert.com    dmarc: agfocert.com    "
                  "tcp: 192.168.1.102:445    smtp: mail.example.com:587",
                  style="Info.TLabel").grid(row=2, column=0, padx=14, sticky="w", pady=(5, 7))
        quick = ttk.Frame(page, style="White.TFrame")
        quick.grid(row=3, column=0, sticky="ew", padx=14, pady=(2, 11))
        for label, tool in (("MX", "DNS MX"), ("SPF", "SPF"), ("DMARC", "DMARC"),
                            ("MTA-STS", "MTA-STS"), ("Mail sağlığı", "Mail Sağlığı"),
                            ("TLS", "TLS Sertifikası"), ("TCP", "TCP Port")):
            ttk.Button(quick, text=label, command=lambda x=tool: self._choose_diag_tool(x)).pack(
                side="left", padx=(0, 5))
        head = ttk.Frame(page, style="White.TFrame")
        head.grid(row=4, column=0, sticky="ew", padx=14)
        ttk.Label(head, text="Test sonucu", style="Section.TLabel").pack(side="left")
        self.diag_status_var = tk.StringVar(value="Hazır · Ağ bağlantısı kuracak testler yalnızca Çalıştır ile başlar.")
        ttk.Label(head, textvariable=self.diag_status_var, style="Info.TLabel", wraplength=610).pack(side="right")
        self.diag_output = scrolledtext.ScrolledText(page, wrap="word", bg="#101b2e", fg="#dcf1ff",
                insertbackground="#ffffff", font=("Consolas", 10), relief="flat", padx=12, pady=12)
        self.diag_output.grid(row=5, column=0, sticky="nsew", padx=14, pady=(8, 10))
        self.diag_output.insert("1.0", "AGFO SuperTools hazır. Bir testi seçip Çalıştır'a basın.\n"
                                "MX, DNS, SPF, DMARC, DKIM, SMTP, TLS, HTTP, TCP, Ping, Traceroute, RDAP.\n"
                                "DKIM örneği: dkim: default:example.com\n"
                                "Dış servislere sorgular yalnızca açık isteğinizle gönderilir.")
        self.diag_output.configure(state="disabled")
        foot = ttk.Frame(page, style="White.TFrame")
        foot.grid(row=6, column=0, sticky="ew", padx=14, pady=(0, 12))
        ttk.Button(foot, text="TXT raporunu kaydet", command=self._save_diagnostic).pack(side="left")
        ttk.Button(foot, text="Sonucu kopyala", command=self._copy_diagnostic).pack(side="left", padx=7)
        ttk.Button(foot, text="Seçili ağ cihazını kullan", command=self._diag_from_selected).pack(side="left")
        self.diag_busy = False
        self.diag_history = []

    def _choose_diag_tool(self, tool):
        self.diag_tool_var.set(tool)
        self.diag_entry.focus_set()

    def _diag_from_selected(self):
        item = self._selected()
        if not item:
            messagebox.showinfo("Cihaz seçimi", "Önce Bulunan cihazlar sekmesinden bir IP seçin.")
            return
        self.diag_tool_var.set("TCP Port")
        self.diag_input_var.set(item.ip + ":445")
        self.tabs.select(self.tab_supertools)

    def _set_diag_output(self, value):
        self.diag_output.configure(state="normal")
        self.diag_output.delete("1.0", "end")
        self.diag_output.insert("1.0", value)
        self.diag_output.configure(state="disabled")

    def _run_diagnostic(self):
        if self.diag_busy:
            return
        tool, target = diag.parse_command(self.diag_input_var.get(), self.diag_tool_var.get())
        try:
            clean = diag.sanitize_target(tool, target)
        except (diag.DiagnosticError, ValueError) as exc:
            messagebox.showwarning("Geçersiz test", str(exc))
            return
        self.diag_busy = True
        self.diag_run_btn.configure(state="disabled")
        self.diag_status_var.set("Test çalışıyor: %s · %s" % (tool, clean))
        self._set_diag_output("[%s] %s çalıştırılıyor...\nHata/yanıt alınana kadar bekleyin." % (time.strftime("%H:%M:%S"), tool))
        def worker():
            try:
                result = diag.run_diagnostic(tool, target)
                self.msg_queue.put(("supertools_result", result))
            except Exception as exc:
                self.msg_queue.put(("supertools_error", str(exc)))
        threading.Thread(target=worker, name="agfo-supertools", daemon=True).start()

    def _receive_diagnostic(self, result: diag.DiagnosticResult):
        self.diag_busy = False
        self.diag_run_btn.configure(state="normal")
        self.diag_status_var.set(("Başarılı" if result.success else "Başarısız / kontrol gerekli") +
                                " · %d ms · %s" % (result.elapsed_ms, result.timestamp))
        header = "%s\n%s\n" % (result.label + " | " + result.target, "-" * 65)
        self._set_diag_output(header + result.content)
        self.diag_history.append(result)
        self.diag_history = self.diag_history[-30:]
        self._log("SuperTools: %s %s -> %s (%d ms)" %
                  (result.label, result.target, "OK" if result.success else "HATA", result.elapsed_ms))

    def _copy_diagnostic(self):
        text = self.diag_output.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set("Test sonucu panoya kopyalandı.")

    def _save_diagnostic(self):
        if not self.diag_history:
            messagebox.showinfo("Rapor", "Önce en az bir test yapın.")
            return
        path = filedialog.asksaveasfilename(title="AGFO SuperTools raporu", defaultextension=".txt",
                  filetypes=[("Metin dosyası", "*.txt")], initialfile="AGFO-SuperTools-Report.txt")
        if not path:
            return
        try:
            sections = ["AGFO SuperTools · Yerel test raporu", "Oluşturma: " + time.strftime("%Y-%m-%d %H:%M:%S")]
            for r in self.diag_history:
                sections.append("\n==== %s | %s | %s | %d ms ====\n%s" % (
                        r.timestamp, r.label, r.target, r.elapsed_ms, r.content))
            Path(path).write_text("\n".join(sections), encoding="utf-8-sig")
        except OSError as exc:
            messagebox.showerror("Rapor", str(exc))
            return
        self.status_var.set("Rapor kaydedildi: " + path)

    def _build_ssh_tab(self):
        page = self.tab_ssh
        page.columnconfigure(1, weight=1)
        page.rowconfigure(1, weight=1)
        heading = ttk.Frame(page, style="White.TFrame")
        heading.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(14, 8))
        ttk.Label(heading, text="SSH Sunucularım", style="Section.TLabel").pack(side="left")
        ttk.Label(heading, text="Parola isteğe bağlı: DPAPI ile 1–24 saat · Anahtar/agent desteği korunur", style="Info.TLabel").pack(side="right")
        left = ttk.Frame(page, style="White.TFrame")
        left.grid(row=1, column=0, sticky="nsw", padx=(14, 10))
        left.columnconfigure(0, weight=1)
        ttk.Label(left, text="Kayıtlı sunucular", style="White.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 7))
        self.ssh_tree = ttk.Treeview(left, columns=("name", "host", "user", "port"),
                                     show="headings", selectmode="browse", height=11)
        for col, title, width in (("name", "Profil", 126), ("host", "Adres", 150),
                                   ("user", "Kullanıcı", 90), ("port", "Port", 54)):
            self.ssh_tree.heading(col, text=title)
            self.ssh_tree.column(col, width=width, stretch=False)
        self.ssh_tree.grid(row=1, column=0, sticky="nsew")
        self.ssh_tree.bind("<<TreeviewSelect>>", lambda _e: self._ssh_selected())
        self.ssh_tree.bind("<Double-Button-1>", lambda _e: self._ssh_open_password())
        action = ttk.Frame(left, style="White.TFrame")
        action.grid(row=2, column=0, sticky="ew", pady=(9, 0))
        ttk.Button(action, text="Yeni", command=self._ssh_new).pack(side="left")
        ttk.Button(action, text="Sil", command=self._ssh_delete).pack(side="left", padx=6)
        ttk.Button(action, text="Ağ listesinden al", command=self._ssh_from_selected).pack(side="left")

        right = ttk.Frame(page, style="White.TFrame")
        right.grid(row=1, column=1, sticky="nsew", padx=(0, 14))
        right.columnconfigure(1, weight=1)
        right.rowconfigure(10, weight=1)
        self.ssh_form_id = None
        self.ssh_name_var = tk.StringVar()
        self.ssh_host_var = tk.StringVar()
        self.ssh_port_var = tk.StringVar(value="22")
        self.ssh_user_var = tk.StringVar(value="ubuntu")
        self.ssh_key_var = tk.StringVar()
        self.ssh_note_var = tk.StringVar()
        fields = (
            ("Profil adı", self.ssh_name_var, 0), ("IP / DNS", self.ssh_host_var, 1),
            ("SSH portu", self.ssh_port_var, 2), ("Kullanıcı", self.ssh_user_var, 3),
        )
        for name, var, row in fields:
            ttk.Label(right, text=name, style="White.TLabel").grid(row=row, column=0, sticky="w", pady=(0, 5))
            ttk.Entry(right, textvariable=var).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=(0, 5))
        ttk.Label(right, text="Özel anahtar (isteğe bağlı)", style="White.TLabel").grid(row=4, column=0, sticky="w")
        key_row = ttk.Frame(right, style="White.TFrame")
        key_row.grid(row=4, column=1, sticky="ew", padx=(8, 0), pady=(0, 6))
        key_row.columnconfigure(0, weight=1)
        ttk.Entry(key_row, textvariable=self.ssh_key_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(key_row, text="Seç", command=self._ssh_choose_key).grid(row=0, column=1, padx=(6, 0))
        ttk.Label(right, text="Not", style="White.TLabel").grid(row=5, column=0, sticky="w")
        ttk.Entry(right, textvariable=self.ssh_note_var).grid(row=5, column=1, sticky="ew", padx=(8, 0), pady=(0, 6))
        buttons = ttk.Frame(right, style="White.TFrame")
        buttons.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(3, 10))
        ttk.Button(buttons, text="Profili kaydet", style="Blue.TButton", command=self._ssh_save).pack(side="left")
        ttk.Button(buttons, text="SSH portunu dene", command=self._ssh_test_port).pack(side="left", padx=5)
        ttk.Button(buttons, text="Dahili SSH / Parola", style="Blue.TButton",
                   command=self._ssh_open_password).pack(side="left", padx=5)
        ttk.Button(buttons, text="OpenSSH (Anahtar)", command=self._ssh_terminal).pack(side="left", padx=5)
        ttk.Button(buttons, text="SSH Oturumları →", command=lambda: self._switch_view("ssh_sessions")).pack(side="left", padx=5)
        auth = ttk.Frame(right, style="White.TFrame")
        auth.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        ttk.Button(auth, text="Bağlantıyı kes", command=self._ssh_disconnect).pack(side="left")
        ttk.Button(auth, text="Bu parolayı unut", command=self._ssh_forget_current).pack(side="left", padx=6)
        ttk.Button(auth, text="Tüm parolaları unut", command=self._ssh_forget_all).pack(side="left")
        self.ssh_remember_var = tk.StringVar(value="Hatırlanan SSH parolası yok.")
        ttk.Label(right, textvariable=self.ssh_remember_var, style="Info.TLabel").grid(
            row=8, column=0, columnspan=2, sticky="w", pady=(0, 5))
        self.ssh_command_var = tk.StringVar(value="uptime && df -h")
        cmd_row = ttk.Frame(right, style="White.TFrame")
        cmd_row.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        cmd_row.columnconfigure(0, weight=1)
        ttk.Label(cmd_row, text="SSH komutu (anahtar/ssh-agent ile; parola istemez):",
                  style="Info.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Entry(cmd_row, textvariable=self.ssh_command_var).grid(row=1, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(cmd_row, text="Çalıştır", command=self._ssh_execute).grid(row=1, column=1, padx=(8, 0), pady=(4, 0))
        self.ssh_output = scrolledtext.ScrolledText(right, wrap="word", bg="#101b2e", fg="#d9e8ff",
              insertbackground="white", font=("Consolas", 9), padx=9, pady=8, height=8)
        self.ssh_output.grid(row=10, column=0, columnspan=2, sticky="nsew")
        self.ssh_output.insert("1.0", "Bir sunucu ekleyin. Hızlı test ve SSH komut çıktısı burada görünür.\n"
                               "Dahili SSH / Parola ile bağlanın; Windows Terminal kullanmanız gerekmez.\n"
                               "Uzak komutlar sunucuda işlem yapabilir; yalnızca güvenli komut kullanın.")
        self.ssh_output.configure(state="disabled")
        footer = ttk.Frame(right, style="White.TFrame")
        footer.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(7, 0))
        ttk.Label(footer, text="Komutlar her SSH sekmesinin kendi giriş alanından gönderilir.",
                  style="Info.TLabel").pack(side="left")
        ttk.Button(footer, text="SSH Oturumları →", style="Blue.TButton",
                   command=lambda: self._switch_view("ssh_sessions")).pack(side="right")
        self.ssh_live_var = tk.StringVar()  # v1.5 compatibility
        self.ssh_hide_input = tk.BooleanVar(value=False)
        self.ssh_connect_busy = False  # Optional Paramiko installation only.
        self._ssh_vault_lock = threading.RLock()
        self._ssh_vault = sshvault.SSHPasswordVault()
        self.ssh_status_var = tk.StringVar(value="Kayıtlı hesaplar yalnızca bu Windows kullanıcısına aittir.")
        ttk.Label(page, textvariable=self.ssh_status_var, style="Info.TLabel", wraplength=1000).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=14, pady=(8, 10))
        self.ssh_corrupt = False
        try:
            self.ssh_profiles = sshdata.load_profiles()
        except ValueError as exc:
            self.ssh_profiles = []
            self.ssh_corrupt = True
            self.ssh_status_var.set(str(exc) + " · Eski dosya korunuyor, düzeltmeden kayıt yapılamaz.")
        self._ssh_refresh()
        try:
            self._ssh_vault.prune()
        except (sshvault.VaultError, OSError) as exc:
            self.ssh_status_var.set("SSH parola kasası okunamadı: " + str(exc))
        self._ssh_update_remember_status()
        self.after(60000, self._ssh_regular_cleanup)

    def _set_ssh_output(self, value):
        self.ssh_output.configure(state="normal")
        self.ssh_output.delete("1.0", "end")
        self.ssh_output.insert("1.0", value)
        self.ssh_output.configure(state="disabled")

    def _ssh_refresh(self):
        self.ssh_tree.delete(*self.ssh_tree.get_children())
        for p in self.ssh_profiles:
            self.ssh_tree.insert("", "end", iid=p.id, values=(p.name, p.host, p.username, str(p.port)))

    def _ssh_selected(self):
        selection = self.ssh_tree.selection()
        if not selection:
            return
        match = next((x for x in self.ssh_profiles if x.id == selection[0]), None)
        if match:
            self.ssh_form_id = match.id
            self.ssh_name_var.set(match.name)
            self.ssh_host_var.set(match.host)
            self.ssh_port_var.set(str(match.port))
            self.ssh_user_var.set(match.username)
            self.ssh_key_var.set(match.key_file)
            self.ssh_note_var.set(match.note)
            self._ssh_update_remember_status()

    def _ssh_new(self):
        self.ssh_tree.selection_remove(*self.ssh_tree.selection())
        self.ssh_form_id = None
        for var in (self.ssh_name_var, self.ssh_host_var, self.ssh_key_var, self.ssh_note_var):
            var.set("")
        self.ssh_port_var.set("22")
        self.ssh_user_var.set("ubuntu")
        self._ssh_update_remember_status()

    def _ssh_from_selected(self):
        item = self._selected()
        if not item:
            messagebox.showinfo("SSH profili", "Önce Bulunan cihazlar sekmesinden bir cihaz seçin.")
            return
        self._ssh_new()
        self.ssh_host_var.set(item.ip)
        self.ssh_name_var.set(item.hostname or "Sunucu " + item.ip)
        self.tabs.select(self.tab_ssh)

    def _ssh_choose_key(self):
        name = filedialog.askopenfilename(title="SSH özel anahtarını seç", filetypes=[("Tüm dosyalar", "*.*")])
        if name:
            self.ssh_key_var.set(name)

    def _ssh_form_profile(self):
        port = int(self.ssh_port_var.get())
        if self.ssh_form_id:
            raw = sshdata.SSHProfile(self.ssh_form_id, self.ssh_name_var.get(), self.ssh_host_var.get(),
                port, self.ssh_user_var.get(), self.ssh_key_var.get(), self.ssh_note_var.get())
            return sshdata.clean_profile(raw)
        return sshdata.new_profile(self.ssh_name_var.get(), self.ssh_host_var.get(), port,
            self.ssh_user_var.get(), self.ssh_key_var.get(), self.ssh_note_var.get())

    def _ssh_save(self):
        if self.ssh_corrupt:
            messagebox.showerror("SSH profilleri", "Önce bozuk ssh-profiles.json dosyasını yedekleyip düzeltin.")
            return
        try:
            profile = self._ssh_form_profile()
            values = [x for x in self.ssh_profiles if x.id != profile.id] + [profile]
            sshdata.save_profiles(values)
        except (ValueError, OSError) as exc:
            messagebox.showerror("SSH profili kaydedilemedi", str(exc))
            return
        self.ssh_profiles = sorted(values, key=lambda x: x.name.lower())
        self.ssh_form_id = profile.id
        self._ssh_refresh()
        self.ssh_tree.selection_set(profile.id)
        self.ssh_status_var.set("Kaydedildi: %s | %s:%s | parola profilde saklanmaz." %
                                (profile.name, profile.host, profile.port))
        self._ssh_update_remember_status()

    def _ssh_delete(self):
        if self.ssh_corrupt:
            return
        selection = self.ssh_tree.selection()
        if not selection:
            return
        value = next((x for x in self.ssh_profiles if x.id == selection[0]), None)
        if not value or not messagebox.askyesno("SSH profili sil", "'%s' profili silinsin mi?\nSSH anahtarları silinmez." % value.name):
            return
        updated = [x for x in self.ssh_profiles if x.id != value.id]
        try:
            sshdata.save_profiles(updated)
        except OSError as exc:
            messagebox.showerror("Profil silinemedi", str(exc))
            return
        self.ssh_profiles = updated
        try:
            self._ssh_vault.forget(value.id)
        except (sshvault.VaultError, OSError) as exc:
            messagebox.showwarning("Şifreli kasa", str(exc))
        self._ssh_refresh()
        self._ssh_new()
        self.ssh_status_var.set("Profil silindi. SSH özel anahtarına dokunulmadı.")

    def _ssh_current(self):
        try:
            return self._ssh_form_profile()
        except (ValueError, diag.DiagnosticError) as exc:
            messagebox.showwarning("SSH bilgileri", str(exc))
            return None

    def _ssh_test_port(self):
        profile = self._ssh_current()
        if not profile:
            return
        self.ssh_status_var.set("SSH TCP testi: " + profile.host)
        def worker():
            try:
                output = sshdata.test_ssh_port(profile)
            except (ConnectionError, ValueError) as exc:
                output = "HATA: " + str(exc)
            self.msg_queue.put(("ssh_result", ("SSH port testi", output)))
        threading.Thread(target=worker, name="agfo-ssh-port", daemon=True).start()

    def _ssh_terminal(self):
        profile = self._ssh_current()
        if not profile:
            return
        try:
            text = sshdata.open_interactive_terminal(profile)
        except (OSError, ValueError) as exc:
            messagebox.showerror("SSH terminali açılamadı", str(exc))
            return
        self.ssh_status_var.set(text)
        self._log("SSH etkileşimli terminal: %s | %s" % (profile.name, profile.host))

    # ---- Secure, on-demand password SSH (v1.5.0) ----
    def _ssh_update_remember_status(self):
        try:
            profile = self._ssh_form_profile() if self.ssh_form_id else None
            with self._ssh_vault_lock:
                expires = self._ssh_vault.expires_at(profile) if profile else None
            if expires:
                until = datetime.fromtimestamp(expires).strftime("%d.%m.%Y %H:%M")
                self.ssh_remember_var.set("Bu hesap için parola Windows DPAPI kasasında: " + until + " tarihine kadar")
            else:
                self.ssh_remember_var.set("Bu hesap için hatırlanan parola yok.")
        except (ValueError, sshvault.VaultError, OSError):
            self.ssh_remember_var.set("Parola kasası okunamıyor veya profil henüz kaydedilmedi.")

    def _ssh_regular_cleanup(self):
        try:
            with self._ssh_vault_lock:
                self._ssh_vault.prune()
            self._ssh_update_remember_status()
        except (sshvault.VaultError, OSError):
            # A broken vault is never overwritten silently.
            pass
        if self.winfo_exists():
            self.after(60000, self._ssh_regular_cleanup)

    def _ssh_forget_current(self):
        profile = self._ssh_current()
        if profile is None or not self.ssh_form_id:
            return
        try:
            with self._ssh_vault_lock:
                forgotten = self._ssh_vault.forget(profile.id)
            self._ssh_update_remember_status()
            self.ssh_status_var.set("Bu hesap için hatırlanan parola silindi." if forgotten else "Bu hesapta saklı parola yok.")
        except (sshvault.VaultError, OSError) as exc:
            messagebox.showerror("Parola kasası", str(exc))

    def _ssh_forget_all(self):
        if not messagebox.askyesno("Parolaları unut", "Bütün SSH profillerinin süreli parola kayıtları silinsin mi?\n"
                                   "Açık SSH oturumları kapatılmaz."):
            return
        try:
            with self._ssh_vault_lock:
                self._ssh_vault.forget_all()
            self._ssh_update_remember_status()
            self.ssh_status_var.set("Şifreli SSH parola kayıtları temizlendi.")
        except (sshvault.VaultError, OSError) as exc:
            messagebox.showerror("Parola kasası", str(exc))

    def _ssh_password_dialog(self, profile, failed=False):
        """Only a transient Tk password Entry; never persist plaintext through Tk settings."""
        from modern_shell import PALETTES
        colors = PALETTES.get(getattr(self, "appearance", "dark"), PALETTES["dark"])
        win = tk.Toplevel(self)
        win.title("AGFO · Güvenli SSH Girişi")
        win.configure(bg=colors["panel"])
        win.resizable(False, False)
        win.geometry("435x315")
        win.transient(self)
        win.grab_set()
        win.columnconfigure(0, weight=1)
        tk.Label(win, text=profile.name, font=("Segoe UI Semibold", 15),
                 fg=colors["text"], bg=colors["panel"]).grid(row=0, column=0, sticky="w", padx=24, pady=(17, 2))
        tk.Label(win, text="%s@%s:%s" % (profile.username, profile.host, profile.port),
                 font=("Consolas", 10), fg=colors["muted"], bg=colors["panel"]).grid(
                     row=1, column=0, sticky="w", padx=24, pady=(0, 13))
        if failed:
            tk.Label(win, text="Önceki parola kabul edilmedi. Yeniden deneyebilirsiniz.",
                     fg="#e78080", bg=colors["panel"], font=("Segoe UI", 9)).grid(
                         row=2, column=0, sticky="w", padx=24)
        tk.Label(win, text="SSH parolası", fg=colors["text"], bg=colors["panel"]).grid(
            row=3, column=0, sticky="w", padx=24, pady=(3, 4))
        field = ttk.Entry(win, show="*", width=48)
        field.grid(row=4, column=0, sticky="ew", padx=24)
        remember = tk.BooleanVar(value=False)
        check = ttk.Checkbutton(win, text="Parolayı geçici olarak hatırla (Windows DPAPI)", variable=remember)
        check.grid(row=5, column=0, sticky="w", padx=24, pady=(12, 5))
        duration = tk.StringVar(value="1 saat")
        select = ttk.Combobox(win, state="disabled", textvariable=duration, width=17,
                              values=("1 saat", "3 saat", "4 saat", "8 saat", "1 gün (24 saat)"))
        select.grid(row=6, column=0, sticky="w", padx=41)
        check.configure(command=lambda: select.configure(state="readonly" if remember.get() else "disabled"))
        tk.Label(win, text="Parola profilde veya komut satırında saklanmaz.",
                 fg=colors["muted"], bg=colors["panel"], font=("Segoe UI", 8)).grid(
                     row=7, column=0, padx=24, pady=(8, 2), sticky="w")
        buttons = ttk.Frame(win)
        buttons.grid(row=8, column=0, sticky="e", padx=24, pady=(12, 8))
        outcome = {"result": None}

        def accept():
            password = field.get()
            if not password:
                messagebox.showwarning("SSH parolası", "Parolayı girin.", parent=win)
                return
            mapping = {"1 saat": 1, "3 saat": 3, "4 saat": 4, "8 saat": 8, "1 gün (24 saat)": 24}
            outcome["result"] = (password, mapping[duration.get()] if remember.get() else 0)
            field.delete(0, "end")
            win.destroy()

        def cancel():
            field.delete(0, "end")
            win.destroy()

        ttk.Button(buttons, text="Vazgeç", command=cancel).pack(side="right")
        ttk.Button(buttons, text="Güvenli bağlan", style="Blue.TButton", command=accept).pack(side="right", padx=(0, 7))
        win.protocol("WM_DELETE_WINDOW", cancel)
        field.bind("<Return>", lambda _e: accept())
        win.after(50, field.focus_set)
        self.wait_window(win)
        return outcome["result"]

    def _ssh_open_password(self, failed=False, profile_override=None):
        if self.ssh_connect_busy:
            return
        profile = profile_override or self._ssh_current()
        if not profile:
            return
        saved = next((p for p in self.ssh_profiles if p.id == profile.id), None)
        if saved is None or saved != profile:
            messagebox.showwarning("SSH profili", "Dahili bağlantıdan önce bu sunucu profilini kaydedin.")
            return
        if os.name != "nt":
            messagebox.showwarning("Windows DPAPI", "Dahili parola önbelleği Windows kullanıcı hesabını gerektirir.")
            return
        if not sshtransport.available():
            if not messagebox.askyesno("SSH kütüphanesi", "Dahili SSH için Paramiko gerekiyor.\n"
                                       "Python paket yöneticisiyle yalnızca bu Windows kullanıcısına kurulsun mu?\n"
                                       "Parola kurulum programına aktarılmaz."):
                return
            self.ssh_connect_busy = True
            self.ssh_status_var.set("Paramiko kuruluyor... İnternet bağlantısı gerekiyor.")
            def install():
                ok, msg = sshtransport.install_optional_dependency()
                self.msg_queue.put(("ssh_lib_installed", (ok, msg)))
            threading.Thread(target=install, daemon=True, name="agfo-paramiko-install").start()
            return
        try:
            with self._ssh_vault_lock:
                cached = None if failed else self._ssh_vault.get(profile)
        except (sshvault.VaultError, OSError) as exc:
            messagebox.showwarning("Parola kasası", "Şifreli parola okunamadı: " + str(exc))
            return
        if cached is None:
            entered = self._ssh_password_dialog(profile, failed=failed)
            if not entered:
                return
            password, remember_hours = entered
            from_cache = False
        else:
            password, remember_hours, from_cache = cached, 0, True
        record = self.ssh_workspace.add_session(profile)
        self._switch_view("ssh_sessions")
        self._ssh_connect_worker(profile, password, remember_hours, from_cache,
                                 retry=int(bool(failed)), session_id=record.id)

    def _ssh_approve_host_key(self, hostname, algorithm, sha256fingerprint):
        import queue as _queue
        confirmation = threading.Event()
        answer = {"accept": False}
        self.msg_queue.put(("ssh_hostkey_prompt", (hostname, algorithm, sha256fingerprint, confirmation, answer)))
        confirmation.wait(120)
        return bool(answer["accept"])

    def _ssh_connect_worker(self, profile, password, remember_hours, from_cache, retry=0, session_id=None):
        """Each SSH worker owns exactly one independently identified connection."""
        if session_id is None:
            return
        self.ssh_status_var.set("SSH bağlantısı kuruluyor: %s:%d" % (profile.host, profile.port))
        def worker():
            session = None
            try:
                session = sshtransport.connect_password(profile, password, self._ssh_approve_host_key)
                record = self.ssh_workspace.get(session_id)
                if record is None or record.cancelled:
                    session.close()
                    return
                remembered = False
                if remember_hours:
                    try:
                        with self._ssh_vault_lock:
                            self._ssh_vault.remember(profile, password, remember_hours)
                        remembered = True
                    except (sshvault.VaultError, OSError, ValueError):
                        self.msg_queue.put(("ssh_vault_warning", "Bağlantı kuruldu ancak parola güvenli kasaya kaydedilemedi."))
                self.msg_queue.put(("ssh_live_connected", (session_id, session, profile.name, remembered)))
                try:
                    session.run_receiver(lambda data: self.msg_queue.put(("ssh_live_data", (session_id, data))))
                finally:
                    self.msg_queue.put(("ssh_live_closed", session_id))
            except Exception as exc:
                if session:
                    session.close()
                authentication_failed = exc.__class__.__name__ == "AuthenticationException"
                if authentication_failed and from_cache:
                    try:
                        with self._ssh_vault_lock:
                            self._ssh_vault.forget(profile.id)
                    except (sshvault.VaultError, OSError):
                        pass
                if authentication_failed:
                    description = "SSH kimlik doğrulaması başarısız. Parola veya sunucu hesabını kontrol edin."
                elif exc.__class__.__name__ == "BadHostKeyException":
                    description = "Sunucunun SSH anahtarı değişmiş! Güvenlik için bağlantı engellendi."
                else:
                    description = "%s: %s" % (exc.__class__.__name__, str(exc)[:350])
                self.msg_queue.put(("ssh_live_error", (session_id, description, authentication_failed, retry, profile)))
        threading.Thread(target=worker, name="agfo-ssh-live-" + session_id[:8], daemon=True).start()

    def _build_ssh_workspace_tab(self):
        self.tab_ssh_sessions.columnconfigure(0, weight=1)
        self.tab_ssh_sessions.rowconfigure(0, weight=1)
        self.ssh_workspace = SSHWorkspace(
            self.tab_ssh_sessions,
            send_callback=self._ssh_send_for_session,
            interrupt_callback=self._ssh_interrupt_session,
            disconnect_callback=self._ssh_disconnect_session,
            remove_callback=self._ssh_remove_session,
            fresh_callback=lambda: self._switch_view("ssh"),
        )
        self.ssh_workspace.grid(row=0, column=0, sticky="nsew")

    def _ssh_send_for_session(self, session_id, text):
        record = self.ssh_workspace.get(session_id)
        if not record or not record.transport or record.closed:
            self.ssh_status_var.set("Bu SSH oturumu bağlı değil.")
            return
        try:
            record.transport.send(text)
        except (sshtransport.SSHTransportError, ValueError, OSError) as exc:
            self.ssh_workspace.append(session_id, "\n[Gönderme hatası: %s]\n" % exc)

    def _ssh_interrupt_session(self, session_id):
        self._ssh_send_for_session(session_id, "\x03")

    def _ssh_disconnect_session(self, session_id):
        record = self.ssh_workspace.get(session_id)
        if not record:
            return
        record.cancelled = True
        if record.transport:
            record.transport.close()
        self.ssh_workspace.set_status(session_id, "Bağlantı kesildi", closed=True)
        self.ssh_workspace.append(session_id, "\n[Bağlantı kullanıcı tarafından kesildi.]\n")

    def _ssh_remove_session(self, session_id):
        record = self.ssh_workspace.get(session_id)
        if record and record.transport:
            record.transport.close()
        self.ssh_workspace.remove(session_id)
        self.ssh_status_var.set("SSH sekmesi kapatıldı; diğer oturumlar açık kaldı.")

    def _ssh_disconnect_all(self):
        if hasattr(self, "ssh_workspace"):
            self.ssh_workspace.close_all()

    def _ssh_handle_hostkey_prompt(self, payload):
        hostname, algorithm, sha256fingerprint, event, answer = payload
        try:
            answer["accept"] = messagebox.askyesno(
                "SSH anahtar kimliği", "YENİ sunucu anahtarı algılandı.\n\n"
                "Sunucu: %s\nAlgoritma: %s\nParmak izi: %s\n\n"
                "Bu parmak izini sunucunun güvenilir yönetim ekranından veya yöneticisinden\n"
                "ayrıca doğruladıysanız kabul edin. Aksi halde Hayır seçin.\n\n"
                "Bu anahtar bu Windows kullanıcısı için saklansın mı?" %
                (hostname, algorithm, sha256fingerprint))
        finally:
            event.set()

    @staticmethod
    def _ssh_safe_terminal_text(value):
        # No terminal emulation: remove escape/control sequences from untrusted server output.
        value = re.sub(r"\x1b\][^\x07\x1b]{0,2048}(?:\x07|\x1b\\)", "", value)
        value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
        return "".join(ch for ch in value if ch == "\n" or ch == "\r" or ch == "\t" or ord(ch) >= 32)

    def _ssh_receive_live(self, session_id, data):
        record = self.ssh_workspace.get(session_id)
        if record is None or record.cancelled:
            return
        content = self._ssh_safe_terminal_text(record.decoder.decode(data))
        self.ssh_workspace.append(session_id, content)

    def _ssh_send_line(self):
        # Compatibility for v1.5's small command input on the profile page.
        command = self.ssh_live_var.get()
        self.ssh_live_var.set("")
        if self.ssh_workspace.focused_id:
            self._ssh_send_for_session(self.ssh_workspace.focused_id, command + "\n")
        else:
            self.ssh_status_var.set("Önce Dahili SSH / Parola ile oturum açın.")

    def _ssh_send_interrupt(self):
        if self.ssh_workspace.focused_id:
            self._ssh_interrupt_session(self.ssh_workspace.focused_id)

    def _ssh_toggle_input(self):
        # Each active SSH ConsolePane owns its own secure input field in v1.6.
        return

    def _ssh_disconnect(self):
        # Button on the original SSH profile screen: disconnect focused session.
        session_id = self.ssh_workspace.focused_id
        if session_id:
            self._ssh_disconnect_session(session_id)
        else:
            self.ssh_status_var.set("Bağlantı kesilecek açık SSH oturumu yok.")

    def _ssh_execute(self):
        profile = self._ssh_current()
        if not profile:
            return
        command = self.ssh_command_var.get().strip()
        try:
            sshdata.build_ssh_argv(profile, command, batch=True, executable="ssh.exe")
        except ValueError as exc:
            messagebox.showwarning("SSH komutu", str(exc))
            return
        if not messagebox.askyesno("SSH uzak komut onayı", "'%s' sunucusunda şu komut çalıştırılsın mı?\n\n%s\n\n"
                       "Komutun sunucuda değişiklik yapabileceğini unutmayın." % (profile.name, command)):
            return
        self.ssh_status_var.set("SSH komutu çalışıyor: %s" % profile.name)
        self._set_ssh_output("SSH komutu başlatıldı. Parola istenmeden kimlik doğrulaması yapılacak...")
        def worker():
            try:
                code, output = sshdata.execute_remote(profile, command)
                text = "SSH çıkış kodu: %s\n\n%s" % (code, output)
            except (OSError, ValueError, TimeoutError) as exc:
                text = "HATA: " + str(exc)
            self.msg_queue.put(("ssh_result", ("SSH komutu: " + profile.name, text)))
        threading.Thread(target=worker, name="agfo-ssh-exec", daemon=True).start()

    def _receive_ssh(self, title, output):
        self._set_ssh_output(title + "\n" + "-" * 65 + "\n" + output)
        self.ssh_status_var.set(title + " tamamlandı; sonuç aşağıda.")
        self._log(title + " sonuçlandı (komut içeriği günlüğe kaydedilmedi).")
