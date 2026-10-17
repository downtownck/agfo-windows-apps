# -*- coding: utf-8 -*-
"""AGFO Multi-Subnet Scanner - Windows Tkinter desktop UI (stdlib only)."""
from __future__ import annotations

import csv
import shutil
import uuid
import ipaddress
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import webbrowser

from modern_shell import ModernShell, PALETTES

import scanner_core as core
import agfo_updater as updater
import agfo_github_update as ghu
from supertools_ui import SuperToolsMixin

BLUE = "#66b0ff"
BG = "#0b1126"
PANEL = "#151f3b"
INK = "#f1f6ff"
MUTED = "#a1b0d0"
BORDER = "#2d3958"
GREEN = "#31d7a2"
GH_PREFIX = "supertools-v"
GH_ASSET = r"AGFO-SuperTools-v\d+(?:\.\d+)+\.update\.zip"


def gh_state_path() -> Path:
    return updater.data_folder() / "updates" / "github-update.json"


def resource_path(relative: str) -> Path:
    base = getattr(sys, "_MEIPASS", str(Path(__file__).resolve().parent))
    return Path(base) / relative


def user_settings_path() -> Path:
    base = os.environ.get("LOCALAPPDATA", "").strip() or str(Path.home() / ".agfo-tools")
    return Path(base) / "AGFO-MultiSubnet-Scanner" / "settings.json"


def safe_start_process(argv: list[str], timeout=None):
    return core.hidden_run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=timeout, check=False)


class ScannerApp(ModernShell, SuperToolsMixin, tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AGFO SuperTools / Multi-Subnet Scanner v" + core.APP_VERSION)
        self.geometry("1510x900")
        self.minsize(1090, 720)
        self.configure(background=BG)
        self._configure_icon()
        self.results: dict[str, core.HostResult] = {}
        self.msg_queue: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.running = False
        self.network_suggestions: list[tuple[str, str]] = []
        self.scan_hint_count = 0
        self.save_path = user_settings_path()
        self.options = self._read_settings()
        self.appearance = self.options.get("appearance", "dark")
        if self.appearance not in ("light", "dark"):
            self.appearance = "dark"
        self._style()
        self._build_ui()
        self._load_options()
        self.after(100, self._poll_queue)
        self.after(300, self._discover_async)
        self.gh_result = None
        if ghu.load_state(gh_state_path()).get("auto", True):
            self.after(4000, lambda: self._gh_check(False))
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _configure_icon(self):
        try:
            iconfile = resource_path("assets/agfo-scanner.ico")
            if os.name == "nt" and iconfile.is_file():
                self.iconbitmap(str(iconfile))
            else:
                pngfile = resource_path("assets/agfo-scanner.png")
                if pngfile.is_file():
                    self._icon_img = tk.PhotoImage(file=str(pngfile))
                    self.iconphoto(True, self._icon_img)
        except Exception:
            pass

    def _style(self):
        self._modern_style()

    def _build_ui(self):
        self._modern_build_ui()

    def _build_update_center(self):
        page = self.tab_updates
        page.columnconfigure(0, weight=1)
        page.rowconfigure(5, weight=1)
        ttk.Label(page, text="Uygulama güncellemeleri", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", padx=17, pady=(18, 7))
        ttk.Label(page, text="Kurulu sürüm: " + core.APP_VERSION +
                  "  |  Yeni AGFO .update.zip paketlerini burada doğrulayarak kurabilirsiniz.",
                  style="Info.TLabel").grid(row=1, column=0, sticky="w", padx=17)
        pick = ttk.Frame(page, style="White.TFrame")
        pick.grid(row=2, column=0, sticky="ew", padx=17, pady=(15, 8))
        self.update_path_var = tk.StringVar(value="Henüz güncelleme ZIP'i seçilmedi.")
        gh = ttk.Frame(page, style="White.TFrame")
        gh.grid(row=9, column=0, sticky="ew", padx=17, pady=(0, 14))
        ttk.Label(gh, text="GitHub güncellemeleri", style="Section.TLabel").pack(side="top", anchor="w")
        ghb = ttk.Frame(gh, style="White.TFrame")
        ghb.pack(fill="x", pady=(6, 0))
        ttk.Button(ghb, text="GitHub'da denetle", command=lambda: self._gh_check(True)).pack(side="left")
        self.gh_update_btn = ttk.Button(ghb, text="Şimdi indir ve güncelle", style="Blue.TButton",
                                        command=self._gh_update, state="disabled")
        self.gh_update_btn.pack(side="left", padx=(8, 0))
        self.gh_auto_var = tk.BooleanVar(value=ghu.load_state(gh_state_path()).get("auto", True))
        ttk.Checkbutton(ghb, text="Açılışta denetle", variable=self.gh_auto_var, command=self._gh_set_auto).pack(side="left", padx=(12, 0))
        self.gh_status_var = tk.StringVar(value="Depo: %s (etiket %s*)" % (ghu.GITHUB_REPO, GH_PREFIX))
        ttk.Label(gh, textvariable=self.gh_status_var, style="Info.TLabel", wraplength=880).pack(side="top", anchor="w", pady=(6, 0))
        ttk.Button(pick, text="Güncelleme ZIP'i seç", command=self._choose_update).pack(side="left")
        ttk.Label(pick, textvariable=self.update_path_var, style="Info.TLabel",
                  wraplength=620).pack(side="left", padx=12)
        toolbar = ttk.Frame(page, style="White.TFrame")
        toolbar.grid(row=3, column=0, sticky="ew", padx=17, pady=5)
        self.update_apply = ttk.Button(toolbar, text="Doğrulanan paketi yükle ve yeniden başlat",
                                       style="Blue.TButton", command=self._apply_update, state="disabled")
        self.update_apply.pack(side="left")
        ttk.Button(toolbar, text="Yeniden doğrula", command=self._verify_update).pack(side="left", padx=(8, 0))
        ttk.Label(page, text="Paket bilgisi / Değişiklikler", style="Section.TLabel").grid(
            row=4, column=0, sticky="w", padx=17, pady=(13, 3))
        self.update_preview = scrolledtext.ScrolledText(page, wrap="word", height=7,
                       bg="#f7f9fd", fg=INK, font=("Consolas", 10), padx=9, pady=8)
        self.update_preview.grid(row=5, column=0, sticky="nsew", padx=17, pady=(0, 10))
        self.update_preview.insert("1.0", "Bir .update.zip seçin. Tam kurulum ZIP'leri burada kullanılmaz.")
        self.update_preview.configure(state="disabled")
        backups = ttk.Frame(page, style="White.TFrame")
        backups.grid(row=6, column=0, sticky="ew", padx=17, pady=(4, 8))
        ttk.Label(backups, text="Önceki sürümler / Geri dönüş", style="Section.TLabel").pack(side="top", anchor="w")
        self.backup_combo = ttk.Combobox(backups, state="readonly", width=70)
        self.backup_combo.pack(side="top", pady=(8, 0), fill="x")
        restore_actions = ttk.Frame(backups, style="White.TFrame")
        restore_actions.pack(fill="x", pady=(5, 0))
        ttk.Button(restore_actions, text="Listeyi yenile", command=self._refresh_backups).pack(side="left")
        ttk.Button(restore_actions, text="Seçilen yedeğe geri dön", command=self._restore_backup).pack(
            side="left", padx=(8, 0))
        self.update_status_var = tk.StringVar(value="Güncelleme geçmişi okunuyor...")
        ttk.Label(page, textvariable=self.update_status_var, style="Info.TLabel", wraplength=900).grid(
            row=7, column=0, sticky="w", padx=17, pady=(0, 4))
        ttk.Label(page, text="Güvenlik: SHA-256 yalnızca ZIP bütünlüğünü denetler, yayıncı imzası değildir. "
                  "Sadece güvendiğiniz AGFO güncelleme paketlerini açın. GitHub güncellemeleri yalnızca "
                  "downtownck/agfo-windows-apps sürümlerinden, GitHub SHA-256 özetiyle doğrulanarak ve sizin onayınızla indirilir.",
                  style="Info.TLabel", wraplength=880, justify="left").grid(
            row=8, column=0, sticky="w", padx=17, pady=(3, 16))
        self.verified_zip = None
        self.verified_manifest = None
        self._refresh_backups()
        self._refresh_update_status()

    def _set_update_preview(self, text):
        self.update_preview.configure(state="normal")
        self.update_preview.delete("1.0", "end")
        self.update_preview.insert("1.0", text)
        self.update_preview.configure(state="disabled")

    def _choose_update(self):
        filename = filedialog.askopenfilename(
            title="AGFO güncelleme ZIP'i seç", filetypes=[("AGFO update ZIP", "*.zip"), ("Tüm dosyalar", "*.*")])
        if filename:
            self.update_path_var.set(filename)
            self._verify_update()

    def _verify_update(self):
        self.verified_zip = None
        self.verified_manifest = None
        self.update_apply.configure(state="disabled")
        name = self.update_path_var.get()
        if not name.lower().endswith(".zip") or not Path(name).is_file():
            self._set_update_preview("Önce geçerli bir .update.zip seçin.")
            return
        try:
            info = updater.inspect_package(Path(name), core.APP_VERSION)
        except (updater.UpdateError, OSError) as exc:
            self._set_update_preview("Doğrulama reddedildi: " + str(exc))
            self._log("Güncelleme paketi reddedildi: " + str(exc))
            return
        self.verified_zip = Path(name)
        self.verified_manifest = info
        text = ("HEDEF SÜRÜM: %s     MEVCUT: %s\n" % (info["version"], core.APP_VERSION) +
                "DOSYALAR: %d      SHA-256: tüm dosyalar doğrulandı\n\n" % len(info["files"]) +
                "DEĞİŞİKLİKLER\n" + info.get("notes", "") + "\n\n" +
                "Paket içeriği:\n" + "\n".join("- " + x for x in info["files"]))
        self._set_update_preview(text)
        self.update_apply.configure(state="normal")
        self._log("AGFO güncellemesi doğrulandı: " + info["version"])

    def _refresh_backups(self):
        self._saved_backups = updater.list_backups()
        descriptions = ["v%s | %s | %s" % (b["version"], b["created"][:19],
                                            Path(b["folder"]).name) for b in self._saved_backups]
        self.backup_combo["values"] = descriptions
        self.backup_combo.set(descriptions[0] if descriptions else "Henüz geri dönüş yedeği yok.")

    def _refresh_update_status(self):
        path = updater.data_folder() / "updates" / "last-result.json"
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
            message = ("Son güncelleme (%s): %s — %s" %
                       (result.get("time", "")[:19], result.get("status", ""), result.get("message", "")))
        except (OSError, ValueError):
            message = "Henüz güncelleme çalıştırılmadı. Kurulum yolu: C:\\agfo-backutil\\MultiSubnetScanner"
        self.update_status_var.set(message)

    def _ready_for_update(self):
        if getattr(self, "diag_busy", False):
            messagebox.showwarning("Güncelleme", "SuperTools testi tamamlanmadan güncelleme başlatılamaz.")
            return False
        if self.running:
            messagebox.showwarning("Güncelleme", "Önce devam eden ağ taramasını tamamlayın veya durdurun.")
            return False
        app_dir = Path(__file__).resolve().parent
        if getattr(sys, "frozen", False):
            messagebox.showwarning("Güncelleme", "Tek EXE modunda güncelleme için tam kurulum paketini kullanın.")
            return False
        if os.path.normcase(str(app_dir)) != os.path.normcase(str(updater.INSTALL_ROOT)):
            messagebox.showwarning("Güncelleme", "Önce Kur-ve-Baslat.cmd ile C:\\agfo-backutil klasörüne kurun. "
                                   "Taşınabilir uygulama güncellenemez.")
            return False
        if not (app_dir / "agfo_updater.py").is_file():
            messagebox.showwarning("Güncelleme", "Güncelleyici dosyası eksik; tam kurulum yapın.")
            return False
        return True

    def _launch_update_runner(self, action, value):
        """Copy the stable runner outside the install tree before closing the GUI."""
        if not self._ready_for_update():
            return
        home = updater.data_folder()
        work = home / "updates" / "pending"
        work.mkdir(parents=True, exist_ok=True)
        runner = work / ("runner-" + uuid.uuid4().hex + ".py")
        shutil.copy2(Path(__file__).resolve().parent / "agfo_updater.py", runner)
        arguments = [sys.executable, "-B", str(runner), action, str(value),
                     "--parent-pid", str(os.getpid()), "--pythonw", sys.executable]
        try:
            if os.name == "nt":
                # An actual write test is safer than os.access with Windows ACLs.
                install = updater.INSTALL_ROOT
                probe = install / (".agfo-permission-" + uuid.uuid4().hex)
                try:
                    with probe.open("xb") as stream:
                        stream.write(b"ok")
                    writable = True
                except OSError:
                    writable = False
                finally:
                    probe.unlink(missing_ok=True)
                if not writable:
                    import ctypes
                    args = subprocess.list2cmdline(arguments[1:])
                    code = ctypes.windll.shell32.ShellExecuteW(None, "runas", arguments[0], args, None, 1)
                    if code <= 32:
                        raise OSError("Yönetici onayı verilmedi veya güncelleyici başlatılamadı (kod %s)." % code)
                else:
                    subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            else:
                subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        except Exception as exc:
            runner.unlink(missing_ok=True)
            messagebox.showerror("Güncelleme başlatılamadı", str(exc))
            return
        self._log("Güncelleyici başlatıldı, arayüz kapatılıyor. İşlem sonrası yeniden açılacak.")
        self._close()

    # ---------------------------------------------------------------- GitHub (tek tik guncelleme)
    def _gh_set_auto(self):
        st = ghu.load_state(gh_state_path())
        st["auto"] = bool(self.gh_auto_var.get())
        ghu.save_state(gh_state_path(), st)

    def _gh_check(self, force=True):
        def work():
            res = ghu.check_for_update(GH_PREFIX, core.APP_VERSION, gh_state_path(), GH_ASSET, force=force,
                                       user_agent="AGFO-SuperTools/" + core.APP_VERSION)
            self.msg_queue.put(("gh", lambda: self._gh_checked(res, force)))
        if force:
            self.gh_status_var.set("GitHub denetleniyor…")
        threading.Thread(target=work, daemon=True).start()

    def _gh_checked(self, res, force):
        st = res.get("status")
        if st == "update":
            self.gh_result = res
            self.gh_update_btn.configure(state="normal")
            rel = res["release"]
            self.gh_status_var.set("Yeni sürüm hazır: v%s (kurulu v%s%s). \"Şimdi indir ve güncelle\" ile tek tıkla kurun." %
                                   (res["version"], core.APP_VERSION, (", yayın " + rel["published"]) if rel.get("published") else ""))
            self.status_var.set("Yeni SuperTools sürümü: v%s — Güncelleme Merkezi" % res["version"])
            self._log("GitHub: yeni sürüm v%s mevcut." % res["version"])
            if not force and not getattr(self, "_gh_prompted", False):
                self._gh_prompted = True
                self._gh_prompt(res)
            return
        msg = {"current": "Güncelsiniz (son sürüm v%s)." % res.get("version", core.APP_VERSION),
               "none": "GitHub'da henüz SuperTools sürümü yok.",
               "skipped": "v%s atlanmış olarak işaretli." % res.get("version", ""),
               "error": "Denetlenemedi: %s" % res.get("message", ""), "throttled": ""}.get(st, st)
        if force or st == "error":
            if msg:
                self.gh_status_var.set(msg)
                self._log("GitHub güncelleme denetimi: " + msg)

    def _gh_prompt(self, res):
        win = tk.Toplevel(self)
        win.title("AGFO SuperTools güncellemesi")
        win.transient(self)
        win.configure(background=BG)
        notes = (res["release"].get("notes") or "").strip()
        ttk.Label(win, text="Yeni sürüm: v%s   (kurulu: v%s)" % (res["version"], core.APP_VERSION), style="Section.TLabel").pack(anchor="w", padx=16, pady=(14, 6))
        box = scrolledtext.ScrolledText(win, wrap="word", height=8, width=70, font=("Segoe UI", 9))
        box.insert("1.0", notes or "Sürüm notu yok.")
        box.configure(state="disabled")
        box.pack(fill="both", expand=True, padx=16)
        row = ttk.Frame(win)
        row.pack(fill="x", padx=16, pady=12)

        def now():
            win.destroy()
            self._gh_update(confirm=False)

        def skip():
            ghu.skip_version(gh_state_path(), res["version"])
            self.gh_status_var.set("v%s atlandı; daha yeni sürümde yeniden bildirilecek." % res["version"])
            win.destroy()
        ttk.Button(row, text="Şimdi güncelle", style="Blue.TButton", command=now).pack(side="right")
        ttk.Button(row, text="Sonra", command=win.destroy).pack(side="right", padx=(0, 8))
        ttk.Button(row, text="Bu sürümü atla", command=skip).pack(side="left")
        self._gh_prompt_win = win

    def _gh_update(self, confirm=True):
        """Tek tik: indir -> GitHub SHA-256 -> agfo_updater.inspect_package -> mevcut guncelleyici (yedek/geri alma)."""
        res = self.gh_result
        if not res or not self._ready_for_update():
            return
        if confirm and not messagebox.askyesno("AGFO güncellemesi",
                "v%s sürümü GitHub'dan indirilip doğrulanacak ve kurulacak.\n\n"
                "Önce dosyalar yedeklenir; uygulama kapanır ve güncellenir.\nDevam edilsin mi?" % res["version"]):
            return
        rel, asset = res["release"], res["asset"]
        work_dir = updater.data_folder() / "updates" / "download"
        dest = work_dir / asset["name"]
        self.gh_update_btn.configure(state="disabled")
        self.gh_status_var.set("İndiriliyor: %s" % asset["name"])

        def progress(done, total):
            text = "İndiriliyor: %.1f / %.1f MB" % (done / 1048576, total / 1048576) if total else "İndiriliyor: %.1f MB" % (done / 1048576)
            self.msg_queue.put(("gh", lambda: self.gh_status_var.set(text)))

        def work():
            try:
                sha = ghu.expected_sha256(rel, asset, user_agent="AGFO-SuperTools/" + core.APP_VERSION)
                ghu.download_asset(asset, dest, sha, progress, user_agent="AGFO-SuperTools/" + core.APP_VERSION)
                self.msg_queue.put(("gh", lambda: self._gh_downloaded(dest, res)))
            except Exception as exc:
                err = str(exc)
                self.msg_queue.put(("gh", lambda: self._gh_failed(err)))
        threading.Thread(target=work, daemon=True).start()

    def _gh_failed(self, err):
        self.gh_status_var.set("Güncelleme indirilemedi: " + err)
        self._log("GitHub güncellemesi başarısız: " + err, focus=True)
        self.gh_update_btn.configure(state="normal")
        messagebox.showerror("Güncelleme", "Güncelleme indirilemedi veya doğrulanamadı:\n" + err)

    def _gh_downloaded(self, dest, res):
        try:
            info = updater.inspect_package(dest, core.APP_VERSION)
            if info["version"] != res["version"]:
                raise updater.UpdateError("Paket sürümü (%s) etiketle (%s) uyuşmuyor." % (info["version"], res["version"]))
            work = updater.data_folder() / "updates" / "pending"
            work.mkdir(parents=True, exist_ok=True)
            staged = work / ("agfo-" + uuid.uuid4().hex + ".update.zip")
            shutil.copy2(dest, staged)
            updater.inspect_package(staged, core.APP_VERSION)
            dest.unlink(missing_ok=True)
        except (updater.UpdateError, OSError) as exc:
            self._gh_failed(str(exc))
            return
        self.gh_status_var.set("v%s doğrulandı (SHA-256 + paket manifesti). Güncelleyici başlatılıyor…" % info["version"])
        self._log("GitHub güncellemesi doğrulandı: v%s" % info["version"])
        self._launch_update_runner("--apply", staged)

    def _apply_update(self):
        if self.verified_zip is None or self.verified_manifest is None:
            return
        if not self._ready_for_update():
            return
        if not messagebox.askyesno("AGFO güncellemesi",
            "v%s sürümüne güncellensin mi?\n\n"
            "Önce dosyalar yedeklenir; uygulama kapanır ve güncellenir.\n"
            "Yönetici onayı gerekirse uygulamayı Başlat menüsünden yeniden açın.\n"
            "Sadece güvendiğiniz ZIP'leri kullanın." % self.verified_manifest["version"]):
            return
        try:
            # Re-check before staging: the file may have changed since selection.
            updater.inspect_package(self.verified_zip, core.APP_VERSION)
            work = updater.data_folder() / "updates" / "pending"
            work.mkdir(parents=True, exist_ok=True)
            staged = work / ("agfo-" + uuid.uuid4().hex + ".update.zip")
            shutil.copy2(self.verified_zip, staged)
            updater.inspect_package(staged, core.APP_VERSION)
        except (updater.UpdateError, OSError) as exc:
            messagebox.showerror("Güncelleme doğrulaması", str(exc))
            return
        self._launch_update_runner("--apply", staged)

    def _restore_backup(self):
        index = self.backup_combo.current()
        if index < 0 or index >= len(self._saved_backups):
            messagebox.showinfo("Geri dönüş", "Geçerli bir yedek seçin.")
            return
        item = self._saved_backups[index]
        if not self._ready_for_update():
            return
        if not messagebox.askyesno("Geri dönüş onayı",
            "Seçilen v%s yedeğine geri dönülsün mü?\n\n"
            "Mevcut sürüm de güvenlik amacıyla ayrı yedeklenecek.\n"
            "Uygulama kapanıp tekrar açılacak." % item["version"]):
            return
        self._launch_update_runner("--restore", Path(item["folder"]))

    def _read_settings(self) -> dict:
        try:
            data = json.loads(self.save_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _load_options(self):
        self.scope_text.insert("1.0", self.options.get("scope", "\n".join(core.DEFAULT_SCOPES)))
        self.workers_var.set(str(self.options.get("workers", "48")))
        old_timeout = str(self.options.get("timeout_ms", "650"))
        self.timeout_var.set("650" if (not self.options.get("version") and old_timeout == "300") else old_timeout)
        self.extended_var.set(bool(self.options.get("extended", False)))
        self.dns_var.set(bool(self.options.get("dns", False)))
        self.discovery_var.set(bool(self.options.get("discovery", True)))

    def _save_settings(self):
        data = {"version": core.APP_VERSION, "scope": self.scope_text.get("1.0", "end-1c"),
                "workers": self.workers_var.get(), "timeout_ms": self.timeout_var.get(),
                "extended": bool(self.extended_var.get()), "dns": bool(self.dns_var.get()),
                "discovery": bool(self.discovery_var.get()), "appearance": self.appearance}
        try:
            self.save_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.save_path.with_suffix(".tmp")
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp, self.save_path)
        except OSError:
            pass

    def _discover_async(self):
        self.status_var.set("Windows arayüzleri ve rota tablosu sorgulanıyor...")
        def discover():
            result = core.discover_windows_networks()
            self.msg_queue.put(("suggestions", result))
        threading.Thread(target=discover, name="agfo-dhcp-suggest", daemon=True).start()

    def _add_suggestion(self):
        selected = self.suggestions.curselection()
        if not selected:
            messagebox.showinfo("Ağ önerisi", "Lütfen listeden bir ağ seçin.")
            return
        cidr = self.network_suggestions[selected[0]][0]
        current = self.scope_text.get("1.0", "end-1c")
        scopes = [x.strip() for x in current.replace(",", "\n").splitlines()]
        if cidr not in scopes:
            self.scope_text.insert("end", ("\n" if current.strip() else "") + cidr)
        self._save_settings()
        self.status_var.set("Ağ tarama listesine eklendi: " + cidr)

    def _start_scan(self):
        if self.running:
            return
        try:
            text = self.scope_text.get("1.0", "end-1c")
            addresses, networks = core.parse_target_ranges(text)
            workers = int(self.workers_var.get())
            timeout_ms = int(self.timeout_var.get())
            if not 1 <= workers <= 96 or not 100 <= timeout_ms <= 2500:
                raise ValueError("Eşzamanlı işlem 1-96, zaman aşımı 100-2500 ms olmalı.")
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Geçersiz tarama ayarı", str(exc))
            return
        self._save_settings()
        self._clear_results()
        self._log("Tarama başladı: %s IP, %s CIDR, %s işçi, %s ms zaman aşımı." %
                  (len(addresses), len(networks), workers, timeout_ms))
        self.running = True
        self.cancel.clear()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress.configure(value=0)
        self.progress_label_var.set("0 / %s IP" % len(addresses))
        self.status_var.set("%s ağda %s IPv4 adresi taranıyor..." % (len(networks), len(addresses)))
        self._start_time = time.monotonic()

        def report(completed, total, found):
            self.msg_queue.put(("progress", (completed, total, found)))

        # Snapshot checkbox values in UI thread; avoid reading Tk vars in workers.
        extended = bool(self.extended_var.get())
        dns = bool(self.dns_var.get())
        discovery = bool(self.discovery_var.get())
        def work_snapshot():
            try:
                hints = {}
                if discovery and not self.cancel.is_set():
                    self.msg_queue.put(("log", "ARP önbelleği ve SSDP/mDNS ile adaylar aranıyor..."))
                    hints = core.discover_neighbor_candidates(addresses, self.cancel)
                    self.msg_queue.put(("log", "%s ağ adayı bulundu. Önce bunlar sınanacak." % len(hints)))
                found = core.scan_targets(addresses, extended, timeout_ms,
                                          workers, self.cancel, report, dns, hints)
                self.msg_queue.put(("done", (found, self.cancel.is_set(), len(addresses))))
            except Exception as exc:
                self.msg_queue.put(("scan_error", str(exc)))
        threading.Thread(target=work_snapshot, name="agfo-scan-manager", daemon=True).start()

    def _stop_scan(self):
        if self.running:
            self.cancel.set()
            self.stop_btn.configure(state="disabled")
            self.status_var.set("Tarama durduruluyor; devam eden kısa ağ testleri tamamlanıyor...")
        self._log("Kullanıcı taramayı durdurdu.")

    def _poll_queue(self):
        try:
            for _ in range(160):
                kind, payload = self.msg_queue.get_nowait()
                if kind == "suggestions":
                    self.network_suggestions = payload
                    self.suggestions.delete(0, "end")
                    for cidr, source in payload:
                        self.suggestions.insert("end", cidr + "  (" + source + ")")
                    if not self.running:
                        self.status_var.set("%s ağ önerisi hazır. Bir veya daha fazla ağ tarayabilirsiniz." % len(payload))
                elif kind == "log":
                    self._log(payload)
                elif kind == "progress":
                    done, total, result = payload
                    self.progress.configure(value=done * 100.0 / max(1, total))
                    self.progress_label_var.set("%s / %s IP tarandı" % (done, total))
                    if result:
                        self._insert_result(result)
                        if result.verified:
                            self._log("%s | ICMP=%s | TCP=%s | %s" %
                                      (result.ip, "evet" if result.ping else "hayır",
                                       result.services, result.discovery or "aktif tarama"))
                        else:
                            self._log("ADAY %s | Kaynak: %s | MAC: %s | Cihaz etkinliği doğrulanmadı." %
                                      (result.ip, result.discovery, result.mac or "?"))
                elif kind == "done":
                    found, cancelled, total = payload
                    self.running = False
                    self.start_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                    elapsed = time.monotonic() - self._start_time
                    verified = sum(1 for r in self.results.values() if r.verified)
                    possible = len(self.results) - verified
                    self.status_var.set("%s: %s aktif, %s aday (%.1f sn)." %
                                        ("Durduruldu" if cancelled else "Tarama bitti", verified, possible, elapsed))
                    self._log("Tarama %s. %d aktif cihaz, %d ARP/multicast adayı (doğrulanmadı). %.1f sn." %
                              ("durduruldu" if cancelled else "tamamlandı", verified, possible, elapsed))
                    self._log("NOT: NAT, farklı VLAN veya yalıtılmış Wi-Fi arkasındaki cihazlar görülemeyebilir.")
                    self._sort_by("ip", force_ascending=True)
                    self._save_settings()
                elif kind == "gh":
                    payload()
                elif kind == "scan_error":
                    self.running = False
                    self.start_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                    self.status_var.set("Tarama hatası: " + payload)
                    self._log("HATA: " + payload, focus=True)
                    messagebox.showerror("Tarama hatası", payload)
                elif kind == "shares":
                    ip, result, authenticated = payload
                    self._log("SMB: %s\n%s" % (ip, result.text), focus=True)
                    if result.access_denied:
                        self.status_var.set("%s: Paylaşım listesi için NAS yetkisi gerekiyor." % ip)
                        if not authenticated and messagebox.askyesno(
                                "SMB erişim izni", "SMB servisi açık fakat paylaşım listesi\n"
                                "okunamıyor (hata 5). NAS kullanıcısıyla\n"
                                "bağlanmayı denemek ister misiniz?"):
                            self._smb_login_dialog(ip)
                elif kind == "smb_connected":
                    ip, share, result = payload
                    self._log("SMB oturumu başarılı: %s\\%s" % (ip, core.validate_smb_share(share)), focus=True)
                    self.status_var.set("NAS oturumu açıldı: " + ip)
                    if share:
                        self._open_smb_path(ip, share)
                    else:
                        self.msg_queue.put(("shares", (ip, result, True)))
                elif kind == "smb_error":
                    self._log(payload, focus=True)
                    self.status_var.set("SMB giriş başarısız.")
                    messagebox.showwarning("NAS bağlantısı", payload)
                elif kind == "diagnostic":
                    self._log(payload, focus=True)
                elif kind == "supertools_result":
                    self._receive_diagnostic(payload)
                elif kind == "supertools_error":
                    self.diag_busy = False
                    self.diag_run_btn.configure(state="normal")
                    self.diag_status_var.set("Beklenmeyen test hatası")
                    self._set_diag_output("HATA: " + payload)
                    self._log("SuperTools çalışma hatası: " + payload)
                elif kind == "ssh_result":
                    title, output = payload
                    self._receive_ssh(title, output)
                elif kind == "ssh_lib_installed":
                    self.ssh_connect_busy = False
                    success, note = payload
                    self.ssh_status_var.set(note)
                    if success:
                        self.after(80, self._ssh_open_password)
                    else:
                        messagebox.showwarning("Dahili SSH kütüphanesi", note)
                elif kind == "ssh_hostkey_prompt":
                    self._ssh_handle_hostkey_prompt(payload)
                elif kind == "ssh_live_connected":
                    session_id, transport, label, remembered = payload
                    if self.ssh_workspace.set_status(session_id, "Bağlı", transport=transport, closed=False):
                        self.ssh_workspace.append(session_id, "\n[Bağlandı: %s]\n" % label)
                        self._ssh_update_remember_status()
                        self.ssh_status_var.set("SSH bağlantısı kuruldu: " + label +
                            (" · Parola geçici şifreli kasaya kaydedildi." if remembered else ""))
                        self._log("Dahili SSH bağlantısı: " + label + " (parola kaydedilmedi)")
                elif kind == "ssh_live_data":
                    self._ssh_receive_live(*payload)
                elif kind == "ssh_live_closed":
                    record = self.ssh_workspace.get(payload)
                    if record:
                        self.ssh_workspace.set_status(payload, "Kapandı", closed=True)
                        self.ssh_workspace.append(payload, "\n[Uzak SSH oturumu kapandı.]\n")
                elif kind == "ssh_vault_warning":
                    messagebox.showwarning("SSH parola kasası", payload)
                elif kind == "ssh_live_error":
                    session_id, description, auth_error, retry, profile = payload
                    record = self.ssh_workspace.get(session_id)
                    if record and not record.cancelled:
                        self.ssh_workspace.set_status(session_id, "Bağlantı hatası", closed=True)
                        self.ssh_workspace.append(session_id, "\n[Bağlantı kurulamadı: %s]\n" % description)
                        self.ssh_status_var.set(description)
                        self._ssh_update_remember_status()
                        if auth_error and retry == 0 and messagebox.askyesno(
                                "SSH parola hatası", description + "\n\nYeni bir sekmede yeniden denemek ister misiniz?"):
                            self.after(100, lambda p=profile: self._ssh_open_password(failed=True, profile_override=p))
                        elif not auth_error:
                            messagebox.showwarning("SSH bağlantısı", description)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _result_values(self, result: core.HostResult):
        return (result.ip, result.hostname or "-", result.mac or "-", result.services,
                "Evet" if result.ping else "Hayır", result.detected_via or "-",
                "Aktif" if result.verified else "Aday", str(result.elapsed_ms) if result.verified else "-")

    def _insert_result(self, result: core.HostResult):
        previous = self.results.get(result.ip)
        if previous and (previous.verified or not result.verified):
            return
        self.results[result.ip] = result
        tag = "candidate" if not result.verified else ("smb" if 445 in result.open_ports else "other")
        if previous:
            self.tree.item(result.ip, values=self._result_values(result), tags=(tag,))
        else:
            self.tree.insert("", "end", iid=result.ip, values=self._result_values(result), tags=(tag,))
        verified = sum(1 for r in self.results.values() if r.verified)
        possible = len(self.results) - verified
        self.found_var.set("%s aktif · %s aday" % (verified, possible))

    def _clear_results(self):
        self.results.clear()
        for row in self.tree.get_children():
            self.tree.delete(row)
        self.found_var.set("0 cihaz")

    def _sort_by(self, column: str, force_ascending: bool = False):
        rows = list(self.tree.get_children())
        if column == "ip":
            rows.sort(key=lambda r: int(ipaddress.IPv4Address(r)), reverse=False)
        else:
            index = list(self.tree["columns"]).index(column)
            rows.sort(key=lambda r: str(self.tree.item(r, "values")[index]).lower())
        if not force_ascending and getattr(self, "_last_sort", "") == column:
            rows.reverse()
            self._last_sort = ""
        else:
            self._last_sort = column
        for idx, row in enumerate(rows):
            self.tree.move(row, "", idx)

    def _selected(self) -> core.HostResult | None:
        current = self.tree.selection()
        if not current:
            messagebox.showinfo("Cihaz seçimi", "Lütfen önce tablodan bir cihaz seçin.")
            return None
        return self.results.get(current[0])

    def _double_click(self, event=None):
        selected = self._selected()
        if not selected:
            return
        if 445 in selected.open_ports:
            self._launch_smb(selected)
        else:
            self._launch_web(selected)

    def _context_menu(self, event):
        row = self.tree.identify_row(event.y)
        if not row:
            return
        self.tree.selection_set(row)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="SMB / Explorer", command=self._open_smb)
        menu.add_command(label="Web yonetimi", command=self._open_web)
        menu.add_command(label="SMB paylasimlarini sorgula", command=self._show_shares)
        menu.add_command(label="NAS hesabi ile baglan", command=self._smb_login_dialog)
        menu.add_separator()
        menu.add_command(label="IP kopyala", command=self._copy_ip)
        menu.add_command(label="UNC kopyala", command=self._copy_unc)
        menu.tk_popup(event.x_root, event.y_root)

    def _launch_smb(self, result: core.HostResult):
        if 445 not in result.open_ports:
            if not messagebox.askyesno("SMB yanıtı yok", "SMB (445) açık görünmüyor. Yine de Explorer açılsın mı?"):
                return
        target = "\\\\" + result.ip
        try:
            if os.name == "nt":
                subprocess.Popen(["explorer.exe", target])
            else:
                self.clipboard_clear()
                self.clipboard_append(target)
                messagebox.showinfo("UNC", target + " panoya kopyalandı.")
        except OSError as exc:
            messagebox.showerror("Explorer hatası", str(exc))

    def _open_smb(self):
        item = self._selected()
        if item:
            self._launch_smb(item)

    def _launch_web(self, result: core.HostResult):
        ports = result.open_ports
        if 443 in ports:
            url = "https://" + result.ip
        elif 80 in ports:
            url = "http://" + result.ip
        else:
            preferred = next((p for p in (8443, 5001, 8080, 5000) if p in ports), None)
            if preferred:
                scheme = "https" if preferred in (8443, 5001) else "http"
                url = "%s://%s:%s" % (scheme, result.ip, preferred)
            else:
                messagebox.showinfo("Web servisi", "Bu cihazda web portu tespit edilmedi.")
                return
        webbrowser.open(url)

    def _open_web(self):
        item = self._selected()
        if item:
            self._launch_web(item)

    def _copy_ip(self):
        item = self._selected()
        if item:
            self.clipboard_clear()
            self.clipboard_append(item.ip)
            self.status_var.set("IP kopyalandı: " + item.ip)

    def _copy_unc(self):
        item = self._selected()
        if item:
            value = "\\\\" + item.ip
            self.clipboard_clear()
            self.clipboard_append(value)
            self.status_var.set("UNC kopyalandı: " + value)

    def _show_shares(self):
        item = self._selected()
        if not item:
            return
        if 445 not in item.open_ports:
            messagebox.showinfo("SMB servisi", "Bu cihazda 445/TCP açık görünmüyor.")
            return
        self._log("SMB paylaşımları sorgulanıyor: " + item.ip, focus=True)
        def read():
            info = core.query_windows_shares(item.ip)
            self.msg_queue.put(("shares", (item.ip, info, False)))
        threading.Thread(target=read, name="agfo-smb-enum", daemon=True).start()

    def _open_smb_path(self, ip: str, share: str):
        target = '\\\\' + ip + '\\' + core.validate_smb_share(share)
        try:
            if os.name == "nt":
                subprocess.Popen(["explorer.exe", target], **core.hidden_process_options())
            else:
                self.clipboard_clear()
                self.clipboard_append(target)
                messagebox.showinfo("UNC", target + " panoya kopyalandı.")
        except OSError as exc:
            messagebox.showerror("Explorer hatası", str(exc))

    def _smb_login_dialog(self, ip: str = ""):
        if not ip:
            item = self._selected()
            if not item:
                messagebox.showinfo("Cihaz seçin", "Önce SMB servisi açık bir cihaz seçin.")
                return
            ip = item.ip
            if 445 not in item.open_ports:
                messagebox.showinfo("SMB", "Seçilen cihazda SMB servisi doğrulanmadı.")
                return
        dlg = tk.Toplevel(self)
        dlg.title("SMB ile bağlan: " + ip)
        dlg.transient(self)
        dlg.resizable(False, False)
        pane = ttk.Frame(dlg, padding=20)
        pane.pack(fill="both", expand=True)
        ttk.Label(pane, text='\\\\' + ip, font=("Segoe UI Semibold", 12)).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        ttk.Label(pane, text="Paylaşım adı").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Label(pane, text="NAS kullanıcısı").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Label(pane, text="NAS parolası").grid(row=3, column=0, sticky="w", pady=5)
        share_entry = ttk.Entry(pane, width=32)
        share_entry.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=5)
        user_entry = ttk.Entry(pane, width=32)
        user_entry.grid(row=2, column=1, sticky="ew", padx=(12, 0), pady=5)
        pw_entry = ttk.Entry(pane, width=32, show="*")
        pw_entry.grid(row=3, column=1, sticky="ew", padx=(12, 0), pady=5)
        ttk.Label(pane, text="Paylaşım boşsa listeyi sorgular. Liste kapalıysa örn. Backup yazın.\n"
                  "Parola dosyaya ve günlüğe kaydedilmez. Windows oturumu açık kalabilir.",
                  style="Info.TLabel", justify="left").grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(11, 10))
        buttons = ttk.Frame(pane)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Vazgeç", command=dlg.destroy).pack(side="left", padx=(0, 8))
        def go():
            share = share_entry.get().strip()
            username = user_entry.get().strip()
            password = pw_entry.get()
            try:
                if share:
                    core.validate_smb_share(share)
                if not share and not username:
                    messagebox.showinfo("Bilgi gerekli", "Paylaşım adı veya NAS kullanıcı adı girin.", parent=dlg)
                    return
            except ValueError as exc:
                messagebox.showerror("SMB paylaşımı", str(exc), parent=dlg)
                return
            pw_entry.delete(0, "end")
            dlg.destroy()
            if not username:
                self._open_smb_path(ip, share)
                return
            self._log("NAS hesabıyla bağlantı isteniyor: %s (%s)" %
                      (ip, share or "paylaşım listesi"), focus=True)
            def connect():
                try:
                    code = core.connect_smb_session(ip, share, username, password)
                    if code:
                        self.msg_queue.put(("smb_error", "SMB %s: %s" %
                                            (ip, core.explain_smb_error(code))))
                        return
                    result = core.query_windows_shares(ip) if not share else core.ShareQueryResult("")
                    self.msg_queue.put(("smb_connected", (ip, share, result)))
                except (OSError, ValueError) as exc:
                    self.msg_queue.put(("smb_error", "SMB bağlantısı: " + str(exc)))
            threading.Thread(target=connect, name="agfo-smb-login", daemon=True).start()
        ttk.Button(buttons, text="Bağlan / Aç", command=go).pack(side="left")
        dlg.bind("<Return>", lambda event: go())
        dlg.bind("<Escape>", lambda event: dlg.destroy())
        share_entry.focus_set()
        dlg.grab_set()

    def _text_dialog(self, title, content, size=(800, 500)):
        dlg = tk.Toplevel(self)
        dlg.title(title)
        dlg.geometry("%sx%s" % size)
        pal = PALETTES[self.appearance]
        dlg.configure(background=pal["bg"])
        text = scrolledtext.ScrolledText(dlg, wrap="word", bg=pal["panel"], fg=pal["text"],
                                         font=("Consolas", 10), relief="flat", padx=14, pady=14)
        text.insert("1.0", content)
        text.configure(state="disabled")
        text.pack(fill="both", expand=True, padx=13, pady=13)
        dlg._details_text = text
        ttk.Button(dlg, text="Kapat", command=dlg.destroy).pack(pady=(0, 12))
        return dlg

    def _network_details(self):
        self._log("Windows ağ / rota bilgileri okunuyor...", focus=True)
        def gather():
            pieces = ["Windows ağ aralıkları / otomatik öneriler", "-" * 55]
            for cidr, source in core.discover_windows_networks():
                pieces.append("%-22s %s" % (cidr, source))
            if os.name == "nt":
                for command in (["route.exe", "print", "-4"], ["net.exe", "use"], ["arp.exe", "-a"]):
                    pieces.extend(("", "> " + " ".join(command), "-" * 55))
                    try:
                        proc = safe_start_process(command, timeout=7)
                        pieces.append(core.decode_windows_net_output(proc.stdout))
                        if proc.stderr:
                            pieces.append(core.decode_windows_net_output(proc.stderr))
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        pieces.append(str(exc))
            else:
                pieces.append("Rota, ARP ve bağlı sürücü teşhisi yalnız Windows'ta çalışır.")
            self.msg_queue.put(("diagnostic", "\n".join(pieces)))
        threading.Thread(target=gather, name="agfo-net-diagnostic", daemon=True).start()

    def _log(self, message: str, focus: bool = False):
        if not hasattr(self, "console"):
            return
        timestamp = time.strftime("%H:%M:%S")
        self.console.configure(state="normal")
        self.console.insert("end", "[%s] %s\n" % (timestamp, str(message).rstrip()))
        # Keep a bounded in-app transcript to avoid unbounded RAM use.
        lines = int(self.console.index("end-1c").split(".")[0])
        if lines > 5000:
            self.console.delete("1.0", "501.0")
        self.console.see("end")
        self.console.configure(state="disabled")
        if focus:
            self.tabs.select(self.tab_logs)

    def _copy_log(self):
        self.clipboard_clear()
        self.clipboard_append(self.console.get("1.0", "end-1c"))
        self.status_var.set("İşlem günlüğü panoya kopyalandı.")

    def _clear_log(self):
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")

    def _export_csv(self):
        if not self.results:
            messagebox.showinfo("CSV", "Önce bir tarama yapın.")
            return
        filename = filedialog.asksaveasfilename(title="Bulunan cihazları kaydet",
                                                defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                                initialfile="AGFO-MultiSubnet-Sonuclar.csv")
        if not filename:
            return
        try:
            with open(filename, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle, delimiter=";")
                writer.writerow(("IP", "DNS adi", "MAC", "Durum", "Ping", "Servisler", "Portlar", "Bulgu", "Süre (ms)"))
                for item in sorted(self.results.values(), key=lambda r: int(ipaddress.IPv4Address(r.ip))):
                    writer.writerow((item.ip, item.hostname, item.mac,
                                     "Aktif" if item.verified else "Aday (dogrulanmadi)",
                                     "Evet" if item.ping else "Hayır",
                                     item.services, ",".join(map(str, item.open_ports)),
                                     item.detected_via, item.elapsed_ms if item.verified else ""))
            self.status_var.set("CSV kaydedildi: " + filename)
        except OSError as exc:
            messagebox.showerror("CSV hatası", str(exc))

    def _close(self):
        self.cancel.set()
        if hasattr(self, "_ssh_disconnect_all"):
            self._ssh_disconnect_all()
        self._save_settings()
        self.destroy()


def main():
    app = ScannerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
