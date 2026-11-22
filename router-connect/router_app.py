# -*- coding: utf-8 -*-
"""AGFO Router Connect - evdeki router'lardan sinyali en guclusune baglanir.

Router listeni sen secersin (ag adi ya da, ayni adli router'lar icin, BSSID). "En yakına bağlan" tek seferde,
"Otomatik" ise belirli aralikla tarar ve yalnizca sinyal belirgin sekilde daha guclu oldugunda gecis yapar.
"""
import datetime as dt
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import router_history as history
import router_startup as startup
import router_update as updater
import router_wifi as wifi
from router_core import APP_NAME, VERSION
from router_store import Store

# ---- acik tema (AGFO UI kurali: koyu zeminde koyu yazi yok; baglantilar altı çizili degil)
BG = "#f6f7fb"
CARD = "#ffffff"
INK = "#1f2430"
MUTED = "#5b6475"
ACCENT = "#1f5fbf"
ROW_TAGS = {
    "connected": {"background": "#e3f6e8", "foreground": "#14532d"},
    "best": {"background": "#dbeafe", "foreground": "#16335f"},
    "far": {"background": CARD, "foreground": "#6b7280"},
    "ok": {"background": CARD, "foreground": INK},
}


def bars(signal):
    n = max(0, min(10, int(signal) // 10))
    return "█" * n + "░" * (10 - n) + f"  {int(signal)}%"


class App(tk.Tk):
    def __init__(self, minimized=False):
        super().__init__()
        self.title(f"{APP_NAME} {VERSION}")
        self.geometry("920x640")
        self.minsize(760, 520)
        self.configure(bg=BG)
        self.store = Store()
        self.busy = False
        self.nets, self.cur, self.decision = [], None, None
        self._auto_job = None
        self._ui_q = queue.Queue()      # arka plan is parcaciklari arayuze yalniz bu kuyruk uzerinden dokunur
        self._style()
        self._build()
        self.refresh_table()
        if minimized:
            self.iconify()
        self._pump()
        self.after(400, self._startup_tasks)

    # ------------------------------------------------------------ UI
    def _style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", background=BG, foreground=INK, font=("Segoe UI", 10))
        st.configure("Card.TFrame", background=CARD)
        st.configure("Card.TLabel", background=CARD, foreground=INK)
        st.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=("Segoe UI", 9))
        st.configure("Big.TLabel", background=CARD, foreground=INK, font=("Segoe UI Semibold", 14))
        st.configure("Title.TLabel", background=BG, foreground=INK, font=("Segoe UI Semibold", 15))
        st.configure("TButton", padding=(10, 5))
        st.configure("Accent.TButton", foreground="#ffffff", background=ACCENT)
        st.map("Accent.TButton", background=[("active", "#174a96"), ("disabled", "#9db7de")])
        st.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=INK, rowheight=28)
        st.configure("Treeview.Heading", background="#e9ecf3", foreground=INK, font=("Segoe UI Semibold", 9))
        st.map("Treeview", background=[("selected", "#cfe0fb")], foreground=[("selected", INK)])
        st.configure("TCheckbutton", background=BG, foreground=INK)

    def _build(self):
        top = ttk.Frame(self, padding=(14, 10, 14, 4))
        top.pack(fill="x")
        ttk.Label(top, text="Router bağlantısı", style="Title.TLabel").pack(side="left")
        ttk.Button(top, text="Güncelleme", command=lambda: self.check_update(manual=True)).pack(side="right")

        card = ttk.Frame(self, style="Card.TFrame", padding=(14, 10))
        card.pack(fill="x", padx=14, pady=(2, 6))
        ttk.Label(card, text="Şu an bağlı", style="Muted.TLabel").pack(anchor="w")
        self.now_lbl = ttk.Label(card, text="–", style="Big.TLabel")
        self.now_lbl.pack(anchor="w")
        self.hint_lbl = ttk.Label(card, text="", style="Muted.TLabel", wraplength=860, justify="left")
        self.hint_lbl.pack(anchor="w", pady=(2, 0))

        bar = ttk.Frame(self, padding=(14, 4))
        bar.pack(fill="x")
        self.btn_go = ttk.Button(bar, text="En yakına bağlan", style="Accent.TButton", command=self.connect_nearest)
        self.btn_go.pack(side="left", padx=(0, 6))
        self.btn_scan = ttk.Button(bar, text="Yenile", command=lambda: self.cycle(force=False, do_connect=False))
        self.btn_scan.pack(side="left", padx=(0, 6))
        ttk.Button(bar, text="Geçmişten bul…", command=self.open_discover).pack(side="left", padx=(0, 6))
        ttk.Button(bar, text="Router ekle…", command=self.open_picker).pack(side="left", padx=(0, 6))
        ttk.Button(bar, text="Yeniden adlandır", command=self.rename_selected).pack(side="left", padx=(0, 6))
        ttk.Button(bar, text="Listeden çıkar", command=self.remove_selected).pack(side="left")

        cols = ("name", "ssid", "bssid", "signal", "band", "state")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=7, selectmode="browse")
        for c, t, w in (("name", "Router", 150), ("ssid", "Ağ adı (SSID)", 170), ("bssid", "BSSID (sabit)", 140),
                        ("signal", "Sinyal", 190), ("band", "Bant", 70), ("state", "Durum", 120)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        for tag, cfg in ROW_TAGS.items():
            self.tree.tag_configure(tag, **cfg)
        self.tree.pack(fill="x", padx=14, pady=(6, 2))
        self.tree.bind("<Double-1>", lambda e: self.rename_selected())

        opt = ttk.Frame(self, padding=(14, 8, 14, 2))
        opt.pack(fill="x")
        s = self.store.settings
        self.v_auto = tk.BooleanVar(value=s["auto"])
        self.v_interval = tk.IntVar(value=s["interval"])
        self.v_margin = tk.IntVar(value=s["margin"])
        self.v_start = tk.BooleanVar(value=startup.is_enabled())
        ttk.Checkbutton(opt, text="Otomatik: en yakına kendiliğinden geç", variable=self.v_auto,
                        command=self.on_auto).grid(row=0, column=0, sticky="w")
        ttk.Label(opt, text="Tarama aralığı (sn):").grid(row=0, column=1, padx=(18, 4))
        ttk.Spinbox(opt, from_=30, to=600, increment=10, width=5, textvariable=self.v_interval,
                    command=self.on_settings).grid(row=0, column=2)
        ttk.Label(opt, text="Geçiş eşiği (sinyal puanı):").grid(row=0, column=3, padx=(18, 4))
        ttk.Spinbox(opt, from_=3, to=40, increment=1, width=4, textvariable=self.v_margin,
                    command=self.on_settings).grid(row=0, column=4)
        ttk.Checkbutton(opt, text="Windows açılınca küçültülmüş başlat", variable=self.v_start,
                        command=self.on_startup).grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))
        for w in opt.grid_slaves():
            if isinstance(w, ttk.Spinbox):
                w.bind("<FocusOut>", lambda e: self.on_settings())
                w.bind("<Return>", lambda e: self.on_settings())

        ttk.Label(self, text="Otomatik kip için pencereyi kapatma, küçült. Kapatırsan tarama durur.",
                  foreground=MUTED).pack(anchor="w", padx=14)
        self.logbox = tk.Text(self, height=9, bg=CARD, fg=INK, relief="flat", wrap="word", state="disabled",
                              font=("Consolas", 9), padx=8, pady=6)
        self.logbox.pack(fill="both", expand=True, padx=14, pady=(6, 12))

    # ------------------------------------------------------------ yardimcilar
    def post(self, fn):
        """Arka plan parcacigindan arayuz islemi siraya koyar (Tk'ye yalniz ana parcacik dokunur)."""
        self._ui_q.put(fn)

    def _pump(self):
        try:
            while True:
                fn = self._ui_q.get_nowait()
                try:
                    fn()
                except Exception as e:  # tek bir arayuz hatasi pompayi durdurmasin
                    self.log("✖ Arayüz hatası: %s" % e)
        except queue.Empty:
            pass
        self.after(80, self._pump)

    def log(self, text):
        self.logbox.configure(state="normal")
        self.logbox.insert("end", f"{dt.datetime.now():%H:%M:%S}  {text}\n")
        lines = int(self.logbox.index("end-1c").split(".")[0])
        if lines > 300:
            self.logbox.delete("1.0", f"{lines - 300}.0")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    def set_busy(self, busy):
        self.busy = busy
        st = "disabled" if busy else "normal"
        self.btn_go.configure(state=st)
        self.btn_scan.configure(state=st)

    def selected_router(self):
        sel = self.tree.selection()
        if not sel:
            return None
        i = self.tree.index(sel[0])
        return self.store.routers[i] if i < len(self.store.routers) else None

    def refresh_table(self):
        sel_idx = None
        if self.tree.selection():
            sel_idx = self.tree.index(self.tree.selection()[0])
        for i in self.tree.get_children():
            self.tree.delete(i)
        routers = self.store.routers
        ranked = wifi.rank(routers, self.nets)
        by_router = {id(x["router"]): x for x in ranked}
        me = wifi.current_router(routers, self.cur)
        best = ranked[0]["router"] if ranked else None
        for r in routers:
            hit = by_router.get(id(r))
            if r is me and self.cur and self.cur.get("connected"):
                tag, state = "connected", "Bağlı"
            elif hit is None:
                tag, state = "far", "Menzilde değil"
            elif r is best:
                tag, state = "best", "En yakın"
            else:
                tag, state = "ok", "Menzilde"
            sig = bars(hit["net"]["signal"]) if hit else "–"
            band = hit["net"]["band"] if hit else ""
            self.tree.insert("", "end", values=(r["name"], r["ssid"], wifi.fmt_mac(r["bssid"]) if r["bssid"] else "–",
                                                sig, band, state), tags=(tag,))
        kids = self.tree.get_children()
        if sel_idx is not None and sel_idx < len(kids):
            self.tree.selection_set(kids[sel_idx])
        if self.cur and self.cur.get("connected"):
            sig = f" · %{self.cur['signal']}" if self.cur.get("signal") is not None else ""
            self.now_lbl.configure(text=f"{self.cur['ssid']}{sig}")
        else:
            self.now_lbl.configure(text="Bağlı değil" if self.cur is not None else "Wi-Fi kartı bulunamadı")
        if not routers:
            self.hint_lbl.configure(text="Henüz router yok. \"Geçmişten bul…\" daha önce bağlandığın ağları ekler, \"Router ekle…\" elle seçtirir.")
        elif not ranked and self.nets:
            self.hint_lbl.configure(text="Seçtiğin router'ların hiçbiri şu an menzilde görünmüyor.")
        elif not self.nets:
            self.hint_lbl.configure(text=wifi.LOCATION_HINT if self.cur is not None else "")
        else:
            self.hint_lbl.configure(text="")

    # ------------------------------------------------------------ tarama / baglanma
    def connect_nearest(self):
        if not self.store.routers:
            messagebox.showinfo(APP_NAME, "Önce \"Router ekle…\" ile evdeki router'ları seç.")
            return
        self.cycle(force=True, do_connect=True)

    def cycle(self, force=False, do_connect=True):
        if self.busy:
            return
        self.set_busy(True)
        threading.Thread(target=self._cycle_worker, args=(force, do_connect), daemon=True).start()

    def _cycle_worker(self, force, do_connect):
        try:
            nets, _raw = wifi.scan()
            cur = wifi.current()
            d = wifi.decide(self.store.routers, nets, cur, self.store.settings["margin"], force)
            result = None
            if do_connect and d["action"] == "connect":
                t = d["target"]
                result = wifi.connect(t["net"]["ssid"], t["router"].get("bssid") or "", iface=cur)
                cur = wifi.current()
            self.post(lambda: self._cycle_done(nets, cur, d, result))
        except Exception as e:  # ag/kart hatasi arayuzu dusurmesin
            msg = str(e) or e.__class__.__name__
            self.post(lambda: self._cycle_failed(msg))

    def _cycle_done(self, nets, cur, d, result):
        self.nets, self.cur, self.decision = nets, cur, d
        self.set_busy(False)
        self.refresh_table()
        if result is not None:
            ok, msg = result
            self.log(("✔ " if ok else "✖ ") + msg)
        elif d["action"] == "connect":
            t = d["target"]
            self.log(f"Daha güçlü router var: {t['router']['name']} (%{t['net']['signal']}). Geçmek için \"En yakına bağlan\".")
        elif d["action"] == "keep":
            why = {"already_best": "Zaten en güçlü router'dasın.",
                   "within_margin": f"Daha güçlü router var ama fark eşiğin altında ({d.get('delta', 0)} puan)."}
            self.log(why.get(d["reason"], "Değişiklik gerekmedi."))
        elif d["action"] == "none":
            self.log({"no_router": "Seçili router'lardan hiçbiri menzilde değil.",
                      "other_network": "Başka bir ağa bağlısın; otomatik kip dokunmadı."}.get(d["reason"], "İşlem yok."))
        if not nets:
            self.log("Ağ listesi boş (Wi-Fi kapalı ya da konum izni kapalı olabilir).")

    def _cycle_failed(self, msg):
        self.set_busy(False)
        self.log("✖ Hata: " + msg)

    # ------------------------------------------------------------ otomatik kip
    def on_settings(self):
        try:
            self.store.settings["interval"] = int(self.v_interval.get())
            self.store.settings["margin"] = int(self.v_margin.get())
        except (tk.TclError, ValueError):
            return
        self.store.save()
        self.v_interval.set(self.store.settings["interval"])
        self.v_margin.set(self.store.settings["margin"])

    def on_auto(self):
        self.on_settings()
        self.store.set("auto", bool(self.v_auto.get()))
        self._schedule_auto()
        self.log("Otomatik kip " + ("açıldı." if self.v_auto.get() else "kapatıldı."))
        if self.v_auto.get():
            self.cycle(force=False, do_connect=True)

    def _schedule_auto(self):
        if self._auto_job is not None:
            self.after_cancel(self._auto_job)
            self._auto_job = None
        if self.store.settings["auto"]:
            self._auto_job = self.after(self.store.settings["interval"] * 1000, self._auto_tick)

    def _auto_tick(self):
        self._auto_job = None
        if self.store.settings["auto"]:
            self.cycle(force=False, do_connect=True)
            self._schedule_auto()

    def on_startup(self):
        want = bool(self.v_start.get())
        try:
            startup.set_enabled(want, updater.installed_exe())
            self.store.set("autostart", want)
        except OSError as e:
            self.v_start.set(not want)
            messagebox.showwarning(APP_NAME, str(e))

    # ------------------------------------------------------------ liste yonetimi
    def open_picker(self):
        PickDialog(self)

    def open_discover(self):
        DiscoverDialog(self)

    def find_known(self, auto=False):
        """Daha once baglanilan, su an menzilde gorunen aglari bulup listeye ekler (liste bos olsa da calisir)."""
        if self.busy:
            return
        self.set_busy(True)
        self.log("Daha önce bağlandığın ağlar aranıyor…")

        def work():
            try:
                found = history.gather()
                err = ""
            except Exception as e:
                found, err = [], str(e) or e.__class__.__name__
            self.post(lambda: self._known_done(found, err, auto))
        threading.Thread(target=work, daemon=True).start()

    def _known_done(self, found, err, auto):
        self.set_busy(False)
        if err:
            self.log("✖ Geçmiş okunamadı: " + err)
        else:
            picks = [f for f in found if f["suggest"]]
            added = [f["ssid"] for f in picks if self.store.add(f["ssid"], "", f["ssid"])]
            if added:
                self.log(f"{len(added)} router geçmişten otomatik eklendi: " + ", ".join(added)
                         + ". Yanlış olanı \"Listeden çıkar\" ile silebilirsin.")
            elif found:
                self.log("Geçmişte bağlandığın ağlar var ama şu an hiçbiri menzilde görünmüyor.")
            else:
                self.log("Windows'ta kayıtlı Wi-Fi ağı bulunamadı. \"Router ekle…\" ile elle seç.")
            self.refresh_table()
        if auto or self.store.routers:
            self.cycle(force=False, do_connect=bool(self.store.settings["auto"]))

    def rename_selected(self):
        r = self.selected_router()
        if not r:
            return
        name = simpledialog.askstring(APP_NAME, "Router adı:", initialvalue=r["name"], parent=self)
        if name is not None:
            self.store.rename(r, name)
            self.refresh_table()

    def remove_selected(self):
        r = self.selected_router()
        if r and messagebox.askyesno(APP_NAME, f"\"{r['name']}\" listeden çıkarılsın mı?"):
            self.store.remove(r)
            self.refresh_table()

    # ------------------------------------------------------------ baslangic ve guncelleme
    def _startup_tasks(self):
        if self.store.routers:
            self.cycle(force=False, do_connect=bool(self.store.settings["auto"]))
        else:
            self.find_known(auto=True)          # liste bossa gecmisten kendisi doldurur
        self._schedule_auto()
        self.after(2500, lambda: self.check_update(manual=False))

    def check_update(self, manual=False):
        def work():
            res = updater.check(force=manual)
            self.post(lambda: self._update_result(res, manual))
        threading.Thread(target=work, daemon=True).start()

    def _update_result(self, res, manual):
        st = res.get("status")
        if st == "update":
            self._offer_update(res)
        elif manual and st in ("current", "none", "throttled", "skipped"):
            messagebox.showinfo(APP_NAME, f"Güncelsin (v{VERSION}).")
        elif manual and st == "error":
            messagebox.showwarning(APP_NAME, f"Güncelleme denetlenemedi:\n{res.get('message', '')}")

    def _offer_update(self, res):
        v = res["version"]
        notes = (res["release"].get("notes") or "")[:600]
        if not messagebox.askyesno(APP_NAME, f"Yeni sürüm var: v{v} (kurulu: v{VERSION}).\n\n{notes}\n\n"
                                             f"İndirilip kurulsun mu? Paket SHA-256 ile doğrulanır; uygulama "
                                             f"kapanır, bu bilgisayarda yeniden derlenip açılır. Router listen korunur."):
            return

        def work():
            try:
                z = updater.download(res)
                folder = updater.extract(z)
                updater.run_installer(folder)
                self.post(self.destroy)
            except Exception as e:
                msg = str(e)
                self.post(lambda: messagebox.showerror(APP_NAME, f"Güncelleme başarısız:\n{msg}"))
        threading.Thread(target=work, daemon=True).start()


# ======================================================================
class DiscoverDialog(tk.Toplevel):
    """Daha once baglanilan aglar: Windows profilleri + ag gecmisi + zaman cizelgesi. Menzildekiler onceden secilir."""

    def __init__(self, app):
        super().__init__(app)
        self.app, self.rows = app, []
        self.title("Geçmişten bul")
        self.geometry("860x480")
        self.configure(bg=BG)
        self.transient(app)
        ttk.Label(self, text="Daha önce bağlandığın ağlar", style="Title.TLabel").pack(anchor="w", padx=14, pady=(12, 0))
        ttk.Label(self, text="Şu an menzilde olanlar evdeki router'lardır; onlar önceden seçili gelir. Gri satırlar "
                             "başka yerlerde bağlandığın ağlardır.", foreground=MUTED, wraplength=820,
                  justify="left").pack(anchor="w", padx=14, pady=(0, 4))
        cols = ("ssid", "signal", "last", "count", "note")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="extended")
        for c, t, w in (("ssid", "Ağ adı (SSID)", 220), ("signal", "Sinyal", 190), ("last", "Son bağlanma", 130),
                        ("count", "Bağlanma", 70), ("note", "Not", 200)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.tag_configure("far", foreground="#6b7280")
        self.tree.pack(fill="both", expand=True, padx=14, pady=4)
        self.lbl = ttk.Label(self, text="Aranıyor…", foreground=MUTED)
        self.lbl.pack(anchor="w", padx=14)
        bar = ttk.Frame(self, padding=(14, 8))
        bar.pack(fill="x")
        ttk.Button(bar, text="Yeniden ara", command=self.search).pack(side="left")
        ttk.Button(bar, text="Seçilenleri ekle", style="Accent.TButton", command=self.add).pack(side="right")
        ttk.Button(bar, text="Kapat", command=self.destroy).pack(side="right", padx=6)
        self.search()

    def search(self):
        self.lbl.configure(text="Aranıyor…")

        def work():
            try:
                found, err = history.gather(), ""
            except Exception as e:
                found, err = [], str(e) or e.__class__.__name__
            self.app.post(lambda: self._fill(found, err))
        threading.Thread(target=work, daemon=True).start()

    def _fill(self, found, err):
        if not self.winfo_exists():
            return
        self.rows = found
        for i in self.tree.get_children():
            self.tree.delete(i)
        keep = []
        for f in found:
            note = []
            if f["gw_match"]:
                note.append("router eşleşti")
            if not f["saved"]:
                note.append("kayıtlı profil yok")
            last = f["last"].strftime("%d.%m.%Y") if f["last"] else "–"
            iid = self.tree.insert("", "end", values=(f["ssid"], bars(f["signal"]) if f["visible"] else "menzilde değil",
                                                      last, f["count"] or "–", ", ".join(note)),
                                   tags=() if f["visible"] else ("far",))
            if f["suggest"]:
                keep.append(iid)
        self.tree.selection_set(keep)
        self.lbl.configure(text=err or (f"{len(found)} ağ bulundu, {len(keep)} tanesi menzilde." if found else
                                        "Windows'ta kayıtlı Wi-Fi ağı bulunamadı."))

    def add(self):
        picked = [self.rows[self.tree.index(i)] for i in self.tree.selection()]
        added = [f["ssid"] for f in picked if self.app.store.add(f["ssid"], "", f["ssid"])]
        self.app.refresh_table()
        self.app.log(f"{len(added)} router eklendi." if added else "Seçilenler zaten listede.")
        self.destroy()


class PickDialog(tk.Toplevel):
    """Gorunen aglardan router sec. Ayni adli (ornegin mesh) router'lar icin BSSID sabitlenebilir."""

    def __init__(self, app):
        super().__init__(app)
        self.app, self.rows = app, []
        self.title("Router seç")
        self.geometry("760x460")
        self.configure(bg=BG)
        self.transient(app)
        ttk.Label(self, text="Evdeki router'ları seç (Ctrl ile birden çok)", style="Title.TLabel").pack(
            anchor="w", padx=14, pady=(12, 4))
        cols = ("ssid", "bssid", "signal", "band")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="extended")
        for c, t, w in (("ssid", "Ağ adı (SSID)", 220), ("bssid", "BSSID", 150), ("signal", "Sinyal", 200),
                        ("band", "Bant", 80)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=14, pady=4)
        self.v_pin = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, variable=self.v_pin,
                        text="Seçilen ağların BSSID'sini sabitle (aynı adı taşıyan farklı router'lar için)").pack(
            anchor="w", padx=14)
        self.lbl = ttk.Label(self, text="Taranıyor…", foreground=MUTED)
        self.lbl.pack(anchor="w", padx=14, pady=(2, 0))
        bar = ttk.Frame(self, padding=(14, 8))
        bar.pack(fill="x")
        ttk.Button(bar, text="Yeniden tara", command=self.scan).pack(side="left")
        ttk.Button(bar, text="Seçilenleri ekle", style="Accent.TButton", command=self.add).pack(side="right")
        ttk.Button(bar, text="Kapat", command=self.destroy).pack(side="right", padx=6)
        self.scan()

    def scan(self):
        self.lbl.configure(text="Taranıyor…")

        def work():
            try:
                nets, _ = wifi.scan()
                err = ""
            except Exception as e:
                nets, err = [], str(e)
            self.app.post(lambda: self._fill(nets, err))
        threading.Thread(target=work, daemon=True).start()

    def _fill(self, nets, err):
        if not self.winfo_exists():
            return
        self.rows = sorted([n for n in nets if n["ssid"]], key=lambda n: (-n["signal"], n["ssid"]))
        for i in self.tree.get_children():
            self.tree.delete(i)
        for n in self.rows:
            self.tree.insert("", "end", values=(n["ssid"], n["bssid"], bars(n["signal"]), n["band"]))
        self.lbl.configure(text=err or (f"{len(self.rows)} ağ bulundu." if self.rows else wifi.LOCATION_HINT))

    def add(self):
        picked = [self.rows[self.tree.index(i)] for i in self.tree.selection()]
        if not picked:
            messagebox.showinfo(APP_NAME, "Önce listeden bir ya da birkaç ağ seç.", parent=self)
            return
        same_name = {}
        for n in picked:
            same_name.setdefault(n["ssid"], []).append(n)
        added = 0
        for ssid, group in same_name.items():
            pin = bool(self.v_pin.get()) or len(group) > 1      # aynı adda birden çok BSSID seçildiyse sabitle
            if pin:
                for n in group:
                    added += bool(self.app.store.add(ssid, n["bssid"], f"{ssid} ({n['bssid'][-5:]})"))
            else:
                added += bool(self.app.store.add(ssid, "", ssid))
        self.app.refresh_table()
        self.app.log(f"{added} router eklendi." if added else "Seçilenler zaten listede.")
        self.destroy()


def _single_instance():
    """Ayni anda tek kopya (iki kopya birbirinin baglantisini bozmasin)."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        h = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\AGFO-Router-Connect")
        if ctypes.windll.kernel32.GetLastError() == 183:      # ERROR_ALREADY_EXISTS
            return False
        _single_instance.handle = h
    except Exception:
        pass
    return True


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    if not _single_instance():
        return
    App(minimized="--minimized" in argv).mainloop()


if __name__ == "__main__":
    main()
