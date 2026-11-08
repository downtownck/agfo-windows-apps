"""AGFO Subscription Manager – all paid subscriptions in one window.

Lists subscriptions, totals them in TRY, warns about renewals and failed
payments, finds new ones in mail (IMAP) and bank statements, and walks you
through cancelling each one (manage page, cancellation e-mail, status log).
"""
import csv
import datetime as dt
import json
import sys
import threading
import urllib.parse
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

import catalog
import mailscan
import bankscan
from store import (Store, STATUSES, PERIODS, CURRENCY_SYMBOL, new_item, fmt_money, fmt_try,
                   parse_date, roll_forward)
from subscription_core import APP_NAME, VERSION
import subscription_update as updater

try:
    import keyring  # optional: Windows Credential Manager
except Exception:  # pragma: no cover
    keyring = None

KEYRING_SERVICE = "AGFO-Subscription-Manager"

# ---- light theme (AGFO UI rule: never dark text on a dark background)
BG = "#f6f7fb"
CARD = "#ffffff"
INK = "#1f2430"
MUTED = "#5b6475"
ACCENT = "#1f5fbf"
ROW_TAGS = {
    "failing": {"background": "#fde2e1", "foreground": "#7a1712"},
    "cancel_scheduled": {"background": "#fff4d6", "foreground": "#5c4200"},
    "check": {"background": "#e3eefc", "foreground": "#123a73"},
    "cancelled": {"background": "#f0f0f0", "foreground": "#8a8f99"},
    "soon": {"background": "#e7f6ea", "foreground": "#14532d"},
}
STATUS_ORDER = ["failing", "check", "active", "cancel_scheduled", "cancelled"]
COLUMNS = [
    ("name", "Abonelik", 240),
    ("scope", "Kapsam", 70),
    ("channel", "Kanal", 95),
    ("amount", "Tutar", 95),
    ("period", "Dönem", 70),
    ("monthly", "Aylık ₺", 90),
    ("next", "Sonraki yenileme", 150),
    ("payment", "Ödeme", 125),
    ("account", "Hesap", 170),
    ("status", "Durum", 105),
]


def open_url(url):
    if url:
        webbrowser.open(url)


def days_until(date_str):
    d = parse_date(date_str)
    return (d - dt.date.today()).days if d else None


# ======================================================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {VERSION}")
        self.geometry("1380x800")
        self.minsize(1100, 600)
        self.configure(bg=BG)
        self.store = Store()
        self.sort_col, self.sort_rev = "status", False
        self._style()
        self._build()
        self.refresh()
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
        st.configure("Big.TLabel", background=CARD, foreground=INK, font=("Segoe UI Semibold", 16))
        st.configure("Title.TLabel", background=BG, foreground=INK, font=("Segoe UI Semibold", 15))
        st.configure("TButton", padding=(10, 5))
        st.configure("Accent.TButton", foreground="#ffffff", background=ACCENT)
        st.map("Accent.TButton", background=[("active", "#174a96")])
        st.configure("Danger.TButton", foreground="#ffffff", background="#b42318")
        st.map("Danger.TButton", background=[("active", "#8f1c13")])
        st.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=INK, rowheight=26)
        st.configure("Treeview.Heading", background="#e9ecf3", foreground=INK, font=("Segoe UI Semibold", 9))
        st.map("Treeview", background=[("selected", "#cfe0fb")], foreground=[("selected", INK)])

    def _build(self):
        top = ttk.Frame(self, padding=(14, 10, 14, 4))
        top.pack(fill="x")
        ttk.Label(top, text="Aboneliklerim", style="Title.TLabel").pack(side="left")
        self.rate_lbl = ttk.Label(top, text="", foreground=MUTED)
        self.rate_lbl.pack(side="right")

        # stat cards
        cards = ttk.Frame(self, padding=(14, 4))
        cards.pack(fill="x")
        self.stat = {}
        for key, title in (("monthly", "Aylık toplam (aktif)"), ("yearly", "Yıllık toplam"),
                           ("count", "Aktif abonelik"), ("soon", "30 gün içinde yenilenecek"),
                           ("failing", "Ödeme sorunu"), ("check", "Kontrol edilecek")):
            c = ttk.Frame(cards, style="Card.TFrame", padding=(14, 8))
            c.pack(side="left", padx=(0, 10), fill="x", expand=True)
            ttk.Label(c, text=title, style="Muted.TLabel").pack(anchor="w")
            v = ttk.Label(c, text="–", style="Big.TLabel")
            v.pack(anchor="w")
            self.stat[key] = v

        self.banner = tk.Label(self, text="", bg="#fff4d6", fg="#5c4200", anchor="w", padx=14, pady=6,
                               font=("Segoe UI", 10), justify="left", wraplength=1300)

        # toolbar
        bar = ttk.Frame(self, padding=(14, 8, 14, 4))
        bar.pack(fill="x")
        for text, cmd, style in (
            ("＋ Ekle", self.add_item, "TButton"),
            ("Düzenle", self.edit_selected, "TButton"),
            ("Sil", self.delete_selected, "TButton"),
            ("✉ E-posta tara", self.open_scan, "Accent.TButton"),
            ("Ekstre içe aktar", self.import_statement, "TButton"),
            ("İptal sihirbazı", lambda: self.cancel_wizard(self.selected_items()), "Danger.TButton"),
            ("Tümünü iptal…", self.cancel_all, "Danger.TButton"),
        ):
            ttk.Button(bar, text=text, command=cmd, style=style).pack(side="left", padx=(0, 5))
        ttk.Button(bar, text="Güncelleme", command=lambda: self.check_update(manual=True)).pack(side="right")
        ttk.Button(bar, text="CSV", command=self.export_csv).pack(side="right", padx=6)
        ttk.Button(bar, text="Yedekle", command=self.export_json).pack(side="right")
        ttk.Button(bar, text="Liste içe aktar", command=self.import_json).pack(side="right", padx=6)
        ttk.Button(bar, text="Kurlar", command=self.edit_rates).pack(side="right")

        # filters
        flt = ttk.Frame(self, padding=(14, 2, 14, 6))
        flt.pack(fill="x")
        ttk.Label(flt, text="Durum:").pack(side="left")
        self.f_status = ttk.Combobox(flt, state="readonly", width=16,
                                     values=["Tümü", "İptal edilmemiş"] + list(STATUSES.values()))
        self.f_status.set("İptal edilmemiş")
        self.f_status.pack(side="left", padx=(4, 12))
        ttk.Label(flt, text="Kapsam:").pack(side="left")
        self.f_scope = ttk.Combobox(flt, state="readonly", width=10, values=["Tümü", "Kişisel", "AGFO"])
        self.f_scope.set("Tümü")
        self.f_scope.pack(side="left", padx=(4, 12))
        ttk.Label(flt, text="Kanal:").pack(side="left")
        self.f_channel = ttk.Combobox(flt, state="readonly", width=14)
        self.f_channel.pack(side="left", padx=(4, 12))
        ttk.Label(flt, text="Ara:").pack(side="left")
        self.f_text = tk.StringVar()
        e = ttk.Entry(flt, textvariable=self.f_text, width=28)
        e.pack(side="left", padx=4)
        for w in (self.f_status, self.f_scope, self.f_channel):
            w.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        self.f_text.trace_add("write", lambda *_: self.refresh())

        # table + detail
        body = ttk.PanedWindow(self, orient="vertical")
        body.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        tf = ttk.Frame(body)
        self.tree = ttk.Treeview(tf, columns=[c[0] for c in COLUMNS], show="headings", selectmode="extended")
        for key, title, width in COLUMNS:
            self.tree.heading(key, text=title, command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=width, anchor="e" if key in ("amount", "monthly") else "w",
                             stretch=key in ("name", "account"))
        for tag, cfg in ROW_TAGS.items():
            self.tree.tag_configure(tag, **cfg)
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.show_detail())
        self.tree.bind("<Double-1>", lambda _e: self.edit_selected())
        self.tree.bind("<Button-3>", self.context_menu)
        self.tree.bind("<Delete>", lambda _e: self.delete_selected())
        body.add(tf, weight=4)

        det = ttk.Frame(body, style="Card.TFrame", padding=10)
        btns = ttk.Frame(det, style="Card.TFrame")
        btns.pack(fill="x")
        ttk.Button(btns, text="Yönetim / iptal sayfasını aç", style="Accent.TButton",
                   command=lambda: self.for_selected(self.open_manage)).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="İptal e-postası hazırla",
                   command=lambda: self.for_selected(self.compose_cancel_mail)).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="✓ İptal edildi olarak işaretle",
                   command=lambda: self.for_selected(lambda it: self.mark(it, "cancelled"))).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Kaynak e-postayı aç",
                   command=lambda: self.for_selected(lambda it: open_url(it.get("source_url")))).pack(side="left")
        self.detail = tk.Text(det, height=8, wrap="word", bg=CARD, fg=INK, relief="flat",
                              font=("Segoe UI", 10), padx=4, pady=6)
        self.detail.pack(fill="both", expand=True, pady=(8, 0))
        self.detail.configure(state="disabled")
        body.add(det, weight=1)

    # ------------------------------------------------------------ data → view
    def filtered(self):
        st = self.f_status.get()
        sc = self.f_scope.get()
        ch = self.f_channel.get()
        q = self.f_text.get().lower().strip()
        rev = {v: k for k, v in STATUSES.items()}
        out = []
        for it in self.store.items:
            if st == "İptal edilmemiş" and it["status"] == "cancelled":
                continue
            if st not in ("Tümü", "İptal edilmemiş", "") and it["status"] != rev.get(st):
                continue
            if sc not in ("Tümü", "") and it.get("scope") != sc:
                continue
            if ch not in ("Tümü", "") and it.get("channel") != ch:
                continue
            if q and q not in json.dumps(it, ensure_ascii=False).lower():
                continue
            out.append(it)
        return out

    def display_next(self, it):
        nxt = it.get("next_renewal") or ""
        if it["status"] == "active":
            nxt = roll_forward(nxt, it.get("period"))
        return nxt

    def refresh(self):
        channels = sorted({i.get("channel") or "" for i in self.store.items} - {""})
        self.f_channel["values"] = ["Tümü"] + channels
        if not self.f_channel.get():
            self.f_channel.set("Tümü")

        rows = self.filtered()

        def key(it):
            if self.sort_col == "status":
                return (STATUS_ORDER.index(it["status"]) if it["status"] in STATUS_ORDER else 9,
                        self.display_next(it) or "9999")
            if self.sort_col == "monthly":
                return self.store.monthly_try(it) or 0
            if self.sort_col == "amount":
                return self.store.to_try(it.get("amount"), it.get("currency")) or 0
            if self.sort_col == "next":
                return self.display_next(it) or "9999"
            m = {"account": "account_email"}
            return str(it.get(m.get(self.sort_col, self.sort_col), "")).lower()

        rows.sort(key=key, reverse=self.sort_rev)
        sel = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        for it in rows:
            nxt = self.display_next(it)
            du = days_until(nxt)
            tag = it["status"] if it["status"] != "active" else ("soon" if du is not None and 0 <= du <= 7 else "")
            nxt_txt = nxt
            if du is not None and it["status"] in ("active", "failing") and 0 <= du <= 30:
                nxt_txt = f"{nxt}  (" + ("bugün" if du == 0 else f"{du} gün") + ")"
            self.tree.insert("", "end", iid=it["id"], tags=(tag,), values=(
                it["name"], it.get("scope", ""), it.get("channel", ""),
                fmt_money(it.get("amount"), it.get("currency") or "TRY"),
                PERIODS.get(it.get("period") or "unknown", "?"),
                fmt_try(self.store.monthly_try(it)),
                nxt_txt, it.get("payment", ""), it.get("account_email", ""),
                STATUSES.get(it["status"], it["status"]),
            ))
        for i in sel:
            if self.tree.exists(i):
                self.tree.selection_add(i)
        self.update_stats()

    def update_stats(self):
        live = [i for i in self.store.items if i["status"] in ("active", "failing", "check")]
        paying = [i for i in self.store.items if i["status"] == "active"]
        monthly = sum(self.store.monthly_try(i) or 0 for i in paying)
        unknown = sum(1 for i in paying if self.store.monthly_try(i) is None)
        soon = [i for i in paying if (lambda d: d is not None and 0 <= d <= 30)(days_until(self.display_next(i)))]
        self.stat["monthly"].configure(text=fmt_try(monthly) + (f"  (+{unknown} ?)" if unknown else ""))
        self.stat["yearly"].configure(text=fmt_try(monthly * 12))
        self.stat["count"].configure(text=str(len(paying)))
        self.stat["soon"].configure(text=str(len(soon)))
        self.stat["failing"].configure(text=str(sum(1 for i in live if i["status"] == "failing")))
        self.stat["check"].configure(text=str(sum(1 for i in live if i["status"] == "check")))
        r = self.store.data["rates"]
        self.rate_lbl.configure(text=f"Kurlar ({self.store.data.get('rates_date') or 'varsayılan'}): "
                                     f"USD {r.get('USD', 0):.2f} · EUR {r.get('EUR', 0):.2f} · GBP {r.get('GBP', 0):.2f}")
        week = [i for i in paying if (lambda d: d is not None and 0 <= d <= 7)(days_until(self.display_next(i)))]
        failing = [i for i in live if i["status"] == "failing"]
        parts = []
        if week:
            parts.append("7 gün içinde yenilenecek: " + ", ".join(
                f"{i['name']} ({fmt_money(i.get('amount'), i.get('currency') or 'TRY')}, {self.display_next(i)})" for i in week))
        if failing:
            parts.append("Ödemesi başarısız olanlar (kart tekrar denenecek – istemiyorsan iptal et): " +
                         ", ".join(i["name"] for i in failing))
        if not self.store.items:
            parts.append("Liste boş. 'Liste içe aktar' ile hazır listeni yükle ya da 'E-posta tara' / 'Ekstre içe aktar' ile bul.")
        if parts:
            self.banner.configure(text="   •   ".join(parts))
            self.banner.pack(fill="x", padx=14, pady=(6, 0), after=self.stat["monthly"].master.master)
        else:
            self.banner.pack_forget()

    def show_detail(self):
        items = self.selected_items()
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if len(items) == 1:
            it = items[0]
            how = catalog.how_to(it)
            lines = [
                f"{it['name']}   —   {STATUSES.get(it['status'])}",
                f"Satıcı: {it.get('vendor') or '-'}   Kanal: {it.get('channel') or '-'}   Hesap: {it.get('account_email') or '-'}",
                f"Tutar: {fmt_money(it.get('amount'), it.get('currency') or 'TRY')} / {PERIODS.get(it.get('period') or 'unknown')}"
                f"   ≈ {fmt_try(self.store.monthly_try(it))} / ay   Ödeme: {it.get('payment') or '-'}",
                f"Yönetim sayfası: {self.manage_url(it) or '-'}   İptal e-postası: {self.cancel_email(it) or '-'}",
            ]
            if how:
                lines.append(f"Nasıl iptal edilir: {how}")
            if it.get("notes"):
                lines.append(f"Not: {it['notes']}")
            for h in (it.get("history") or [])[-4:]:
                lines.append(f"  · {h['date']}  {h['event']}  {h.get('note', '')}")
            self.detail.insert("1.0", "\n".join(lines))
        elif items:
            total = sum(self.store.monthly_try(i) or 0 for i in items if i["status"] == "active")
            self.detail.insert("1.0", f"{len(items)} abonelik seçili. Aktif olanların aylık toplamı: {fmt_try(total)} "
                                      f"(yıllık {fmt_try(total * 12)}).\n'İptal sihirbazı' seçilenleri tek tek "
                                      f"yönetim sayfasına götürür ve sonucu kaydeder.")
        self.detail.configure(state="disabled")

    def sort_by(self, col):
        self.sort_rev = not self.sort_rev if self.sort_col == col else False
        self.sort_col = col
        self.refresh()

    # ------------------------------------------------------------ helpers
    def selected_items(self):
        return [self.store.get(i) for i in self.tree.selection() if self.store.get(i)]

    def for_selected(self, fn):
        items = self.selected_items()
        if not items:
            messagebox.showinfo(APP_NAME, "Önce listeden bir abonelik seç.")
            return
        for it in items:
            fn(it)

    def manage_url(self, it):
        if it.get("manage_url"):
            return it["manage_url"]
        url, _, _ = catalog.lookup(it.get("channel", ""), it.get("name", ""), it.get("vendor", ""))
        return url

    def cancel_email(self, it):
        if it.get("cancel_email"):
            return it["cancel_email"]
        _, mail, _ = catalog.lookup(it.get("name", ""), it.get("vendor", ""))
        return mail

    def open_manage(self, it):
        url = self.manage_url(it)
        if url:
            open_url(url)
        else:
            messagebox.showinfo(APP_NAME, f"{it['name']} için kayıtlı bir yönetim sayfası yok. "
                                          "Düzenle'den ekleyebilir ya da iptal e-postası gönderebilirsin.")

    def compose_cancel_mail(self, it):
        to = self.cancel_email(it)
        if not to and it.get("channel") in ("Google Play", "Apple"):
            messagebox.showinfo(APP_NAME, f"{it['name']} bir {it['channel']} aboneliği; satıcıya e-posta yerine "
                                          f"{it['channel']} abonelik sayfasından iptal edilir. Sayfa açılıyor.")
            self.open_manage(it)
            return
        sig = self.store.settings.get("signature") or ""
        acct = it.get("account_email") or ""
        turkish = (to or "").endswith(".tr") or (
            it.get("currency") == "TRY" and it.get("channel") in ("Doğrudan", "Banka talimatı", "Banka/Kart"))
        if turkish:
            subj = f"Abonelik iptal talebi – {it['name']}"
            body = (f"Merhaba,\n\n{acct} hesabıma bağlı \"{it['name']}\" aboneliğimin/hizmetimin mevcut dönem sonunda "
                    f"iptal edilmesini ve otomatik yenilemenin kapatılmasını rica ederim. Kayıtlı ödeme yöntemimden "
                    f"başka tahsilat yapılmamasını ve iptalin yazılı olarak onaylanmasını rica ederim.\n\n"
                    f"Saygılarımla,\n{sig}")
        else:
            subj = f"Subscription cancellation request – {it['name']}"
            body = (f"Hello,\n\nPlease cancel my subscription \"{it['name']}\" on the account {acct}, effective at the "
                    f"end of the current billing period, and turn off automatic renewal. Please do not charge my "
                    f"payment method again, and confirm the cancellation by replying to this e-mail.\n\n"
                    f"Thank you,\n{sig}")
        if acct.endswith("@gmail.com") or acct.endswith("@googlemail.com"):
            url = ("https://mail.google.com/mail/?view=cm&fs=1&authuser=" + urllib.parse.quote(acct) +
                   "&to=" + urllib.parse.quote(to or "") + "&su=" + urllib.parse.quote(subj) +
                   "&body=" + urllib.parse.quote(body))
        else:
            url = f"mailto:{to}?subject={urllib.parse.quote(subj)}&body={urllib.parse.quote(body)}"
        open_url(url)
        if not to:
            messagebox.showinfo(APP_NAME, "Bu satıcının iptal adresi kayıtlı değil; taslak alıcısız açıldı. "
                                          "Destek adresini sitesinden bulup ekle.")

    def mark(self, it, status, note=""):
        self.store.set_status(it, status, note)
        self.refresh()
        self.show_detail()

    def context_menu(self, event):
        row = self.tree.identify_row(event.y)
        if not row:
            return
        if row not in self.tree.selection():
            self.tree.selection_set(row)
        m = tk.Menu(self, tearoff=0)
        m.add_command(label="Yönetim / iptal sayfasını aç", command=lambda: self.for_selected(self.open_manage))
        m.add_command(label="İptal e-postası hazırla", command=lambda: self.for_selected(self.compose_cancel_mail))
        m.add_command(label="İptal sihirbazı", command=lambda: self.cancel_wizard(self.selected_items()))
        m.add_separator()
        for st, label in STATUSES.items():
            m.add_command(label=f"Durum: {label}", command=lambda s=st: self.for_selected(lambda it: self.mark(it, s)))
        m.add_separator()
        m.add_command(label="Kaynak e-postayı aç", command=lambda: self.for_selected(lambda it: open_url(it.get("source_url"))))
        m.add_command(label="Düzenle", command=self.edit_selected)
        m.add_command(label="Sil", command=self.delete_selected)
        m.tk_popup(event.x_root, event.y_root)

    # ------------------------------------------------------------ CRUD
    def add_item(self):
        EditDialog(self, new_item())

    def edit_selected(self):
        items = self.selected_items()
        if items:
            EditDialog(self, dict(items[0]))

    def delete_selected(self):
        items = self.selected_items()
        if not items:
            return
        names = "\n".join("• " + i["name"] for i in items[:12])
        if messagebox.askyesno(APP_NAME, f"Listeden silinsin mi? (Bu, aboneliği İPTAL ETMEZ.)\n\n{names}"):
            for it in items:
                self.store.delete(it["id"])
            self.refresh()

    # ------------------------------------------------------------ cancel
    def cancel_all(self):
        live = [i for i in self.filtered() if i["status"] in ("active", "failing", "check")]
        if not live:
            messagebox.showinfo(APP_NAME, "Görünen listede iptal edilecek abonelik yok.")
            return
        total = sum(self.store.monthly_try(i) or 0 for i in live if i["status"] == "active")
        if messagebox.askyesno(APP_NAME, f"Görünen listedeki {len(live)} aboneliğin (aylık ≈ {fmt_try(total)}) "
                                         f"iptal sihirbazı başlatılsın mı?\n\nHer biri için yönetim sayfası açılır; "
                                         f"iptali sen onaylarsın, uygulama sonucu kaydeder.\nFiltreyle (ör. Kapsam: "
                                         f"Kişisel) önce daraltabilirsin."):
            self.cancel_wizard(live)

    def cancel_wizard(self, items):
        items = [i for i in items if i and i["status"] != "cancelled"]
        if not items:
            messagebox.showinfo(APP_NAME, "İptal edilecek abonelik seçilmedi (iptal edilmişler atlanır).")
            return
        CancelWizard(self, items)

    # ------------------------------------------------------------ import
    def open_scan(self):
        ScanDialog(self)

    def import_statement(self):
        path = filedialog.askopenfilename(title="Banka / kart ekstresi seç",
                                          filetypes=[("Ekstre", "*.csv *.xlsx *.xlsm *.txt"), ("Tümü", "*.*")])
        if not path:
            return
        try:
            found = bankscan.find_recurring(path)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Ekstre okunamadı:\n{e}")
            return
        if not found:
            messagebox.showinfo(APP_NAME, "Ekstrede en az iki ayda tekrarlanan bir ödeme bulunamadı.")
            return
        ReviewDialog(self, found, source="Ekstre")

    def merge_findings(self, findings):
        added = updated = 0
        for f in findings:
            existing = self.store.find_match(f.get("name", ""), f.get("vendor", ""))
            url, mail, _ = catalog.lookup(f.get("channel", ""), f.get("name", ""), f.get("vendor", ""))
            if existing:
                for k in ("amount", "currency", "payment", "account_email"):
                    if f.get(k) not in (None, ""):
                        existing[k] = f[k]
                if f.get("period") not in (None, "", "unknown"):
                    existing["period"] = f["period"]
                if f.get("next_renewal"):
                    existing["next_renewal"] = f["next_renewal"]
                if f.get("status") in ("failing", "cancel_scheduled") and existing["status"] != "cancelled":
                    existing["status"] = f["status"]
                existing["last_seen"] = f.get("date", "")
                updated += 1
            else:
                it = new_item(
                    name=f.get("name") or f.get("vendor"), vendor=f.get("vendor", ""), amount=f.get("amount"),
                    currency=f.get("currency") or "TRY", period=f.get("period") or "unknown",
                    next_renewal=f.get("next_renewal", ""), payment=f.get("payment", ""),
                    account_email=f.get("account_email", ""), channel=f.get("channel", ""),
                    status=f.get("status") or "active", manage_url=url, cancel_email=mail,
                    last_seen=f.get("date", ""), category="",
                    notes=f"Bulundu: {f.get('subject', '')[:120]} ({f.get('count', 1)} kayıt)")
                self.store.items.append(it)
                added += 1
        self.store.save()
        self.refresh()
        messagebox.showinfo(APP_NAME, f"{added} yeni abonelik eklendi, {updated} mevcut kayıt güncellendi.")

    # ------------------------------------------------------------ misc
    def export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="abonelikler.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Abonelik", "Satıcı", "Kapsam", "Kanal", "Tutar", "Para birimi", "Dönem", "Aylık TL",
                        "Sonraki yenileme", "Ödeme", "Hesap", "Durum", "Yönetim sayfası", "Not"])
            for it in self.filtered():
                m = self.store.monthly_try(it)
                w.writerow([it["name"], it.get("vendor"), it.get("scope"), it.get("channel"),
                            "" if it.get("amount") is None else str(it["amount"]).replace(".", ","),
                            it.get("currency"), PERIODS.get(it.get("period") or "unknown"),
                            "" if m is None else f"{m:.2f}".replace(".", ","), self.display_next(it),
                            it.get("payment"), it.get("account_email"), STATUSES.get(it["status"]),
                            self.manage_url(it), it.get("notes")])
        messagebox.showinfo(APP_NAME, f"Kaydedildi:\n{path}")

    def edit_rates(self):
        RatesDialog(self)

    def import_json(self, path=None):
        path = path or filedialog.askopenfilename(title="Abonelik listesi (JSON) seç",
                                                  filetypes=[("JSON", "*.json"), ("Tümü", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            incoming = data.get("items", []) if isinstance(data, dict) else list(data)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Dosya okunamadı:\n{e}")
            return
        added = updated = 0
        for raw in incoming:
            if not isinstance(raw, dict) or not raw.get("name"):
                continue
            if raw.get("id"):
                cur = self.store.get(raw["id"])  # exported lists carry ids: match only on id
            else:
                cur = self.store.find_match(raw["name"], raw.get("vendor", ""))
            if cur:
                hist = cur.get("history", []) + [h for h in raw.get("history", []) if h not in cur.get("history", [])]
                cur.update({k: v for k, v in raw.items() if k not in ("id", "history")})
                cur["history"] = hist
                updated += 1
            else:
                it = new_item(**{k: v for k, v in raw.items() if k != "id"})
                if raw.get("id") and not self.store.get(raw["id"]):
                    it["id"] = raw["id"]
                self.store.items.append(it)
                added += 1
        if isinstance(data, dict) and isinstance(data.get("settings"), dict):
            cur_s = self.store.settings
            for k, v in data["settings"].items():
                if k == "imap_accounts":
                    known = {a.get("user") for a in cur_s.get("imap_accounts", [])}
                    cur_s.setdefault("imap_accounts", []).extend(a for a in v if a.get("user") not in known)
                elif k == "ignore_domains":
                    cur_s["ignore_domains"] = sorted(set(cur_s.get("ignore_domains", [])) | set(v))
                elif not cur_s.get(k):
                    cur_s[k] = v
        if isinstance(data, dict) and data.get("rates") and not self.store.data.get("rates_date"):
            self.store.data["rates"].update(data["rates"])
        self.store.save()
        self.refresh()
        messagebox.showinfo(APP_NAME, f"İçe aktarıldı: {added} yeni, {updated} güncellendi.")

    def export_json(self):
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            initialfile=f"abonelikler-{dt.date.today().isoformat()}.json",
                                            filetypes=[("JSON", "*.json")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"items": self.store.items, "rates": self.store.data["rates"], "settings": self.store.settings},
                      f, ensure_ascii=False, indent=2)
        messagebox.showinfo(APP_NAME, f"Yedek kaydedildi:\n{path}")

    def _startup_tasks(self):
        if not str(self.store.data.get("rates_date") or "").startswith(dt.date.today().isoformat()):
            def work():
                try:
                    self.store.refresh_rates_tcmb()
                    self.after(0, self.refresh)
                except Exception:
                    pass
            threading.Thread(target=work, daemon=True).start()
        self.after(1500, lambda: self.check_update(manual=False))

    # ------------------------------------------------------------ self-update
    def check_update(self, manual=False):
        def work():
            res = updater.check(force=manual)
            self.after(0, lambda: self._update_result(res, manual))
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
                                             f"kapanır, bu bilgisayarda yeniden derlenip açılır. Verilerin korunur."):
            return

        def work():
            try:
                z = updater.download(res)
                folder = updater.extract(z)
                updater.run_installer(folder)
                self.after(0, self.destroy)
            except Exception as e:
                msg = str(e)
                self.after(0, lambda: messagebox.showerror(APP_NAME, f"Güncelleme başarısız:\n{msg}"))
        threading.Thread(target=work, daemon=True).start()


# ======================================================================
class EditDialog(tk.Toplevel):
    def __init__(self, app, item):
        super().__init__(app)
        self.app, self.item = app, item
        self.title("Abonelik")
        self.configure(bg=BG)
        self.transient(app)
        self.resizable(False, False)
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)
        self.vars = {}
        fields = [
            ("name", "Abonelik adı"), ("vendor", "Satıcı"), ("scope", "Kapsam"), ("category", "Kategori"),
            ("amount", "Tutar"), ("currency", "Para birimi"), ("period", "Dönem"),
            ("next_renewal", "Sonraki yenileme (YYYY-AA-GG)"), ("payment", "Ödeme yöntemi"),
            ("account_email", "Hesap e-postası"), ("channel", "Kanal"), ("status", "Durum"),
            ("manage_url", "Yönetim / iptal URL"), ("cancel_email", "İptal e-posta adresi"),
            ("source_url", "Kaynak e-posta linki"),
        ]
        for r, (k, label) in enumerate(fields):
            ttk.Label(frm, text=label).grid(row=r, column=0, sticky="w", pady=3, padx=(0, 10))
            val = item.get(k)
            if k == "status":
                v = tk.StringVar(value=STATUSES.get(val, "Aktif"))
                w = ttk.Combobox(frm, textvariable=v, values=list(STATUSES.values()), state="readonly", width=48)
            elif k == "period":
                v = tk.StringVar(value=PERIODS.get(val or "unknown", "?"))
                w = ttk.Combobox(frm, textvariable=v, values=list(PERIODS.values()), state="readonly", width=48)
            elif k == "currency":
                v = tk.StringVar(value=val or "TRY")
                w = ttk.Combobox(frm, textvariable=v, values=list(CURRENCY_SYMBOL.keys()), width=48)
            elif k == "scope":
                v = tk.StringVar(value=val or "Kişisel")
                w = ttk.Combobox(frm, textvariable=v, values=["Kişisel", "AGFO"], width=48)
            elif k == "channel":
                v = tk.StringVar(value=val or "")
                w = ttk.Combobox(frm, textvariable=v, width=48, values=[
                    "Google Play", "Apple", "Stripe/Web", "Paddle", "PayPal", "Doğrudan", "Banka/Kart", "Banka talimatı"])
            else:
                v = tk.StringVar(value="" if val is None else str(val))
                w = ttk.Entry(frm, textvariable=v, width=51)
            w.grid(row=r, column=1, sticky="we", pady=3)
            self.vars[k] = v
        r = len(fields)
        ttk.Label(frm, text="Not").grid(row=r, column=0, sticky="nw", pady=3)
        self.notes = tk.Text(frm, height=4, width=50, bg=CARD, fg=INK, font=("Segoe UI", 10))
        self.notes.insert("1.0", item.get("notes") or "")
        self.notes.grid(row=r, column=1, sticky="we", pady=3)
        b = ttk.Frame(frm)
        b.grid(row=r + 1, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(b, text="Vazgeç", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Kaydet", style="Accent.TButton", command=self.save).pack(side="right", padx=6)
        self.grab_set()

    def save(self):
        it = self.item
        rev_s = {v: k for k, v in STATUSES.items()}
        rev_p = {v: k for k, v in PERIODS.items()}
        for k, v in self.vars.items():
            val = v.get().strip()
            if k == "amount":
                if val:
                    n = mailscan.parse_number(val)
                    if n is None:
                        messagebox.showerror(APP_NAME, "Tutar sayı olmalı (ör. 249,99).", parent=self)
                        return
                    it[k] = n
                else:
                    it[k] = None
            elif k == "status":
                new = rev_s.get(val, "active")
                if new != it.get("status") and it.get("status"):
                    it.setdefault("history", []).append({"date": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
                                                         "event": f"{STATUSES.get(it['status'])} -> {val}", "note": "elle"})
                it[k] = new
            elif k == "period":
                it[k] = rev_p.get(val, "unknown")
            elif k == "next_renewal" and val and not parse_date(val):
                messagebox.showerror(APP_NAME, "Tarih biçimi YYYY-AA-GG olmalı.", parent=self)
                return
            else:
                it[k] = val
        it["notes"] = self.notes.get("1.0", "end").strip()
        if not it.get("name"):
            messagebox.showerror(APP_NAME, "Ad boş olamaz.", parent=self)
            return
        self.app.store.upsert(it)
        self.app.refresh()
        self.destroy()


# ======================================================================
class CancelWizard(tk.Toplevel):
    """Step through subscriptions: open manage page / mail, then record the outcome."""

    def __init__(self, app, items):
        super().__init__(app)
        self.app, self.items, self.i = app, items, 0
        self.done = []
        self.title("İptal sihirbazı")
        self.configure(bg=BG)
        self.geometry("720x430")
        self.transient(app)
        frm = ttk.Frame(self, padding=16)
        frm.pack(fill="both", expand=True)
        self.step = ttk.Label(frm, text="", foreground=MUTED)
        self.step.pack(anchor="w")
        self.title_lbl = ttk.Label(frm, text="", font=("Segoe UI Semibold", 15))
        self.title_lbl.pack(anchor="w", pady=(2, 6))
        self.info = tk.Text(frm, height=10, wrap="word", bg=CARD, fg=INK, relief="flat", font=("Segoe UI", 10),
                            padx=8, pady=8)
        self.info.pack(fill="both", expand=True)
        row1 = ttk.Frame(frm)
        row1.pack(fill="x", pady=(10, 4))
        ttk.Button(row1, text="1) Yönetim / iptal sayfasını aç", style="Accent.TButton",
                   command=lambda: self.app.open_manage(self.cur)).pack(side="left")
        ttk.Button(row1, text="İptal e-postası hazırla",
                   command=lambda: self.app.compose_cancel_mail(self.cur)).pack(side="left", padx=6)
        row2 = ttk.Frame(frm)
        row2.pack(fill="x", pady=4)
        ttk.Label(row2, text="2) Sonuç:").pack(side="left")
        ttk.Button(row2, text="✓ İptal ettim", style="Danger.TButton",
                   command=lambda: self.record("cancelled")).pack(side="left", padx=6)
        ttk.Button(row2, text="Dönem sonunda bitecek", command=lambda: self.record("cancel_scheduled")).pack(side="left")
        ttk.Button(row2, text="E-posta gönderdim, onay bekliyor",
                   command=lambda: self.record("check", "iptal e-postası gönderildi")).pack(side="left", padx=6)
        row3 = ttk.Frame(frm)
        row3.pack(fill="x", pady=(4, 0))
        ttk.Button(row3, text="Bunu tut (atla)", command=self.next).pack(side="left")
        ttk.Button(row3, text="Bitir", command=self.finish).pack(side="right")
        self.show()

    @property
    def cur(self):
        return self.items[self.i]

    def show(self):
        it = self.cur
        self.step.configure(text=f"{self.i + 1} / {len(self.items)}")
        self.title_lbl.configure(text=it["name"])
        how = catalog.how_to(it) or "Satıcının hesap/abonelik sayfasında 'Cancel / İptal' seçeneğini bul. " \
                                   "Bulamazsan iptal e-postası gönder."
        txt = (f"Kanal: {it.get('channel') or '-'}    Hesap: {it.get('account_email') or '-'}\n"
               f"Tutar: {fmt_money(it.get('amount'), it.get('currency') or 'TRY')} / "
               f"{PERIODS.get(it.get('period') or 'unknown')}   (≈ {fmt_try(self.app.store.monthly_try(it))}/ay)\n"
               f"Sonraki yenileme: {self.app.display_next(it) or '-'}    Durum: {STATUSES.get(it['status'])}\n\n"
               f"Nasıl: {how}\n\nYönetim sayfası: {self.app.manage_url(it) or '-'}\n")
        if it.get("notes"):
            txt += f"\nNot: {it['notes']}"
        self.info.configure(state="normal")
        self.info.delete("1.0", "end")
        self.info.insert("1.0", txt)
        self.info.configure(state="disabled")

    def record(self, status, note="sihirbaz"):
        self.app.store.set_status(self.cur, status, note)
        self.done.append((self.cur["name"], STATUSES[status]))
        self.next()

    def next(self):
        self.i += 1
        if self.i >= len(self.items):
            self.finish()
        else:
            self.show()

    def finish(self):
        self.app.refresh()
        if self.done:
            messagebox.showinfo("İptal sihirbazı", "Kaydedilen sonuçlar:\n\n" +
                                "\n".join(f"• {n}: {s}" for n, s in self.done), parent=self.app)
        self.destroy()


# ======================================================================
class ScanDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("E-postalardan abonelik bul")
        self.configure(bg=BG)
        self.geometry("760x520")
        self.transient(app)
        self.stop_flag = False
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Hesaplar (salt okunur IMAP; hiçbir ileti değiştirilmez):",
                  font=("Segoe UI Semibold", 10)).pack(anchor="w")
        self.acc_tree = ttk.Treeview(frm, columns=("email", "host", "port", "user"), show="headings", height=4)
        for c, t, w in (("email", "Hesap", 200), ("host", "IMAP sunucusu", 200), ("port", "Port", 60), ("user", "Kullanıcı", 200)):
            self.acc_tree.heading(c, text=t)
            self.acc_tree.column(c, width=w)
        self.acc_tree.pack(fill="x", pady=4)
        for a in app.store.settings["imap_accounts"]:
            self.acc_tree.insert("", "end", values=(a["email"], a["host"], a.get("port", 993), a.get("user", a["email"])))
        self.acc_tree.selection_set(self.acc_tree.get_children())
        ab = ttk.Frame(frm)
        ab.pack(fill="x")
        ttk.Button(ab, text="Hesap ekle", command=self.add_acc).pack(side="left")
        ttk.Button(ab, text="Düzenle", command=self.edit_acc).pack(side="left", padx=6)
        ttk.Button(ab, text="Kaldır", command=self.del_acc).pack(side="left")
        opt = ttk.Frame(frm)
        opt.pack(fill="x", pady=8)
        ttk.Label(opt, text="Kaç ay geriye:").pack(side="left")
        self.months = tk.IntVar(value=app.store.settings.get("scan_months", 13))
        ttk.Spinbox(opt, from_=1, to=36, textvariable=self.months, width=5).pack(side="left", padx=6)
        self.remember = tk.BooleanVar(value=keyring is not None)
        ttk.Checkbutton(opt, text="Şifreleri Windows Kimlik Yöneticisinde sakla", variable=self.remember,
                        state="normal" if keyring else "disabled").pack(side="left", padx=12)
        tip = ("Gmail için normal şifre değil 'Uygulama şifresi' gerekir: Google Hesabı > Güvenlik > 2 Adımlı Doğrulama > "
               "Uygulama şifreleri (myaccount.google.com/apppasswords). Diğer adresler için posta sunucusunun IMAP adresini "
               "ve şifreni gir. Taramadan sonra bulguları tek tek onaylayarak eklersin.")
        ttk.Label(frm, text=tip, wraplength=720, foreground=MUTED).pack(anchor="w", pady=(0, 6))
        self.log = tk.Text(frm, height=9, bg=CARD, fg=INK, font=("Consolas", 9), relief="flat")
        self.log.pack(fill="both", expand=True)
        bb = ttk.Frame(frm)
        bb.pack(fill="x", pady=(8, 0))
        self.start_btn = ttk.Button(bb, text="Taramayı başlat", style="Accent.TButton", command=self.start)
        self.start_btn.pack(side="right")
        ttk.Button(bb, text="Durdur", command=lambda: setattr(self, "stop_flag", True)).pack(side="right", padx=6)
        ttk.Button(bb, text="Uygulama şifresi sayfası",
                   command=lambda: open_url("https://myaccount.google.com/apppasswords")).pack(side="left")

    def _save_accounts(self):
        accs = []
        for iid in self.acc_tree.get_children():
            e, h, p, u = self.acc_tree.item(iid, "values")
            accs.append({"email": e, "host": h, "port": int(p), "user": u})
        self.app.store.settings["imap_accounts"] = accs
        self.app.store.save()

    def add_acc(self):
        e = simpledialog.askstring("Hesap", "E-posta adresi:", parent=self)
        if not e:
            return
        h = simpledialog.askstring("Hesap", "IMAP sunucusu:", parent=self,
                                   initialvalue="imap.gmail.com" if e.endswith("gmail.com") else "mail." + e.split("@")[-1])
        if not h:
            return
        self.acc_tree.insert("", "end", values=(e, h, 993, e))
        self._save_accounts()

    def edit_acc(self):
        sel = self.acc_tree.selection()
        if not sel:
            return
        e, h, p, u = self.acc_tree.item(sel[0], "values")
        h2 = simpledialog.askstring("Hesap", "IMAP sunucusu:", initialvalue=h, parent=self) or h
        p2 = simpledialog.askinteger("Hesap", "Port:", initialvalue=int(p), parent=self) or int(p)
        u2 = simpledialog.askstring("Hesap", "Kullanıcı adı:", initialvalue=u, parent=self) or u
        self.acc_tree.item(sel[0], values=(e, h2, p2, u2))
        self._save_accounts()

    def del_acc(self):
        for s in self.acc_tree.selection():
            self.acc_tree.delete(s)
        self._save_accounts()

    def say(self, msg):
        self.log.insert("end", msg + "\n")
        self.log.see("end")

    def start(self):
        accs = [self.acc_tree.item(i, "values") for i in self.acc_tree.selection()]
        if not accs:
            messagebox.showinfo(APP_NAME, "Taranacak hesabı seç.", parent=self)
            return
        creds = []
        for e, h, p, u in accs:
            pw = None
            if keyring:
                try:
                    pw = keyring.get_password(KEYRING_SERVICE, u)
                except Exception:
                    pw = None
            if not pw:
                pw = simpledialog.askstring("Şifre", f"{u} için IMAP / uygulama şifresi:", show="•", parent=self)
                if not pw:
                    continue
                if self.remember.get() and keyring:
                    try:
                        keyring.set_password(KEYRING_SERVICE, u, pw)
                    except Exception:
                        pass
            creds.append((e, h, int(p), u, pw))
        if not creds:
            return
        self.app.store.settings["scan_months"] = int(self.months.get())
        self.app.store.save()
        self.stop_flag = False
        self.start_btn.configure(state="disabled")
        months = int(self.months.get())
        ignore = self.app.store.settings.get("ignore_domains", [])

        def work():
            findings = []
            for e, h, p, u, pw in creds:
                try:
                    findings += mailscan.scan_account(h, p, u, pw, months, ignore,
                                                      progress=lambda m: self.after(0, self.say, m),
                                                      stop=lambda: self.stop_flag)
                except mailscan.ScanCancelled:
                    self.after(0, self.say, "Durduruldu.")
                    break
                except Exception as ex:
                    msg = str(ex)
                    if "AUTHENTICATIONFAILED" in msg or "Invalid credentials" in msg or "authentication" in msg.lower():
                        msg += "  → Şifre hatalı. Gmail için uygulama şifresi kullan."
                        if keyring:
                            try:
                                keyring.delete_password(KEYRING_SERVICE, u)
                            except Exception:
                                pass
                    self.after(0, self.say, f"{u}: HATA – {msg}")
            agg = mailscan.aggregate(findings)
            self.after(0, self.done, agg)

        threading.Thread(target=work, daemon=True).start()

    def done(self, agg):
        self.start_btn.configure(state="normal")
        self.say(f"Bitti: {len(agg)} olası abonelik.")
        if agg:
            ReviewDialog(self.app, agg, source="E-posta")


# ======================================================================
class ReviewDialog(tk.Toplevel):
    def __init__(self, app, findings, source=""):
        super().__init__(app)
        self.app, self.findings = app, findings
        self.title(f"Bulunanlar ({source}) – eklenecekleri seç")
        self.configure(bg=BG)
        self.geometry("1100x520")
        self.transient(app)
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Eklemek istediklerini seç (Ctrl/Shift ile çoklu). Zaten listede olanlar 'Güncelle' "
                            "olarak işaretli; onlar yeni tutar/tarihle güncellenir.", foreground=MUTED).pack(anchor="w")
        cols = (("act", "İşlem", 70), ("name", "Abonelik", 260), ("channel", "Kanal", 90), ("amount", "Tutar", 90),
                ("period", "Dönem", 70), ("count", "Kayıt", 50), ("last", "Son", 90), ("status", "Durum", 100),
                ("subject", "Örnek konu", 300))
        self.tree = ttk.Treeview(frm, columns=[c[0] for c in cols], show="headings", selectmode="extended")
        for c, t, w in cols:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, stretch=c in ("name", "subject"))
        for tag, cfg in ROW_TAGS.items():
            self.tree.tag_configure(tag, **cfg)
        sb = ttk.Scrollbar(frm, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True, pady=6)
        sb.pack(side="left", fill="y", pady=6)
        for n, f in enumerate(findings):
            exists = app.store.find_match(f.get("name", ""), f.get("vendor", ""))
            self.tree.insert("", "end", iid=str(n), tags=(f.get("status") if f.get("status") != "active" else "",),
                             values=("Güncelle" if exists else "Yeni", f.get("name"), f.get("channel"),
                                     fmt_money(f.get("amount"), f.get("currency") or "TRY"),
                                     PERIODS.get(f.get("period") or "unknown"), f.get("count", 1), f.get("date", ""),
                                     STATUSES.get(f.get("status"), ""), (f.get("subject") or "")[:90]))
        self.tree.selection_set([str(n) for n, f in enumerate(findings)
                                 if (f.get("months") or 1) >= 2 or f.get("period") != "unknown"
                                 or f.get("status") != "active"])
        bb = ttk.Frame(self, padding=(12, 0, 12, 12))
        bb.pack(fill="x")
        ttk.Button(bb, text="Vazgeç", command=self.destroy).pack(side="right")
        ttk.Button(bb, text="Seçilenleri ekle / güncelle", style="Accent.TButton", command=self.apply).pack(side="right", padx=6)
        ttk.Button(bb, text="Tümünü seç", command=lambda: self.tree.selection_set(self.tree.get_children())).pack(side="left")
        ttk.Button(bb, text="Seçimi kaldır", command=lambda: self.tree.selection_set(())).pack(side="left", padx=6)

    def apply(self):
        chosen = [self.findings[int(i)] for i in self.tree.selection()]
        self.destroy()
        if chosen:
            self.app.merge_findings(chosen)


# ======================================================================
class RatesDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Döviz kurları (1 birim = ? TL)")
        self.configure(bg=BG)
        self.transient(app)
        frm = ttk.Frame(self, padding=14)
        frm.pack()
        self.vars = {}
        for r, c in enumerate(("USD", "EUR", "GBP")):
            ttk.Label(frm, text=c).grid(row=r, column=0, sticky="w", pady=3)
            v = tk.StringVar(value=f"{app.store.data['rates'].get(c, 0):.4f}")
            ttk.Entry(frm, textvariable=v, width=12).grid(row=r, column=1, pady=3, padx=8)
            self.vars[c] = v
        ttk.Button(frm, text="TCMB'den güncelle", command=self.fetch).grid(row=3, column=0, pady=(10, 0))
        ttk.Button(frm, text="Kaydet", style="Accent.TButton", command=self.save).grid(row=3, column=1, pady=(10, 0))
        self.grab_set()

    def fetch(self):
        try:
            rates = self.app.store.refresh_rates_tcmb()
            for c, v in self.vars.items():
                v.set(f"{rates.get(c, 0):.4f}")
            self.app.refresh()
        except Exception as e:
            messagebox.showerror(APP_NAME, f"TCMB kurları alınamadı:\n{e}", parent=self)

    def save(self):
        for c, v in self.vars.items():
            n = mailscan.parse_number(v.get())
            if n:
                self.app.store.data["rates"][c] = n
        self.app.store.data["rates_date"] = dt.date.today().isoformat() + " (elle)"
        self.app.store.save()
        self.app.refresh()
        self.destroy()


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    App().mainloop()


if __name__ == "__main__":
    main()
