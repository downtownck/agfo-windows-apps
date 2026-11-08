"""Data storage, currency rates and money helpers."""
import json
import os
import shutil
import sys
import uuid
import datetime as dt
import urllib.request
import xml.etree.ElementTree as ET

STATUSES = {
    "active": "Aktif",
    "failing": "Ödeme sorunu",
    "cancel_scheduled": "İptal planlandı",
    "check": "Kontrol et",
    "cancelled": "İptal edildi",
}
PERIODS = {
    "weekly": "Haftalık",
    "monthly": "Aylık",
    "quarterly": "3 aylık",
    "yearly": "Yıllık",
    "biennial": "2 yıllık",
    "unknown": "?",
}
PERIOD_PER_MONTH = {"weekly": 52 / 12, "monthly": 1, "quarterly": 1 / 3, "yearly": 1 / 12,
                    "biennial": 1 / 24, "unknown": 0}
CURRENCY_SYMBOL = {"TRY": "₺", "USD": "$", "EUR": "€", "GBP": "£"}
DEFAULT_RATES = {"TRY": 1.0, "USD": 51.97, "EUR": 60.0, "GBP": 68.0}

FIELDS = ["id", "name", "vendor", "category", "scope", "amount", "currency", "period",
          "next_renewal", "payment", "account_email", "channel", "status", "manage_url",
          "cancel_email", "notes", "source_url", "last_seen", "history"]


def app_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    d = os.path.join(base, "AGFO", "SubscriptionManager")
    os.makedirs(d, exist_ok=True)
    return d


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def new_item(**kw):
    item = {f: "" for f in FIELDS}
    item.update({"id": uuid.uuid4().hex[:10], "amount": None, "currency": "TRY",
                 "period": "monthly", "status": "active", "scope": "Kişisel", "history": []})
    item.update({k: v for k, v in kw.items() if k in FIELDS})
    return item


class Store:
    def __init__(self, path=None):
        self.path = path or os.path.join(app_dir(), "subscriptions.json")
        self.data = None
        self.load()

    # ---------- persistence ----------
    def load(self):
        if not os.path.exists(self.path):
            seed = resource_path("seed_subscriptions.json")
            if os.path.exists(seed):
                shutil.copyfile(seed, self.path)
            else:
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump({"items": []}, f)
        with open(self.path, "r", encoding="utf-8") as f:
            self.data = json.load(f)
        self.data.setdefault("items", [])
        self.data.setdefault("rates", dict(DEFAULT_RATES))
        self.data.setdefault("rates_date", "")
        self.data.setdefault("settings", {})
        s = self.data["settings"]
        s.setdefault("imap_accounts", [])
        s.setdefault("ignore_domains", [])
        s.setdefault("signature", "")
        s.setdefault("scan_months", 13)
        s.setdefault("cancel_lang", "tr")
        for it in self.data["items"]:
            for f in FIELDS:
                it.setdefault(f, [] if f == "history" else ("" if f != "amount" else None))

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        if os.path.exists(self.path):
            shutil.copyfile(self.path, self.path + ".bak")
        os.replace(tmp, self.path)

    @property
    def items(self):
        return self.data["items"]

    @property
    def settings(self):
        return self.data["settings"]

    def get(self, item_id):
        for it in self.items:
            if it["id"] == item_id:
                return it
        return None

    def upsert(self, item):
        cur = self.get(item["id"])
        if cur:
            cur.update(item)
        else:
            self.items.append(item)
        self.save()

    def delete(self, item_id):
        self.data["items"] = [i for i in self.items if i["id"] != item_id]
        self.save()

    def set_status(self, item, status, note=""):
        old = item.get("status")
        item["status"] = status
        item.setdefault("history", []).append({
            "date": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "event": f"{STATUSES.get(old, old)} -> {STATUSES.get(status, status)}",
            "note": note,
        })
        self.save()

    def find_match(self, name, vendor=""):
        key = norm(name)
        vkey = norm(vendor)
        for it in self.items:
            if norm(it["name"]) == key or (vkey and norm(it.get("vendor", "")) == vkey and norm(it["name"]) in (key, vkey)):
                return it
        if vkey and len(vkey) >= 3:
            same_vendor = [it for it in self.items if norm(it.get("vendor", "")) == vkey]
            if len(same_vendor) == 1:
                return same_vendor[0]
        for it in self.items:
            n = norm(it["name"])
            if key and n and (key in n or n in key) and min(len(key), len(n)) >= 4:
                return it
        return None

    # ---------- money ----------
    def to_try(self, amount, currency):
        if amount in (None, ""):
            return None
        rate = self.data["rates"].get(currency or "TRY")
        if rate is None:
            return None
        return float(amount) * float(rate)

    def monthly_try(self, item):
        v = self.to_try(item.get("amount"), item.get("currency"))
        if v is None:
            return None
        return v * PERIOD_PER_MONTH.get(item.get("period") or "unknown", 0)

    def refresh_rates_tcmb(self, timeout=8):
        """Fetch today's forex selling rates from the Turkish Central Bank."""
        req = urllib.request.Request("https://www.tcmb.gov.tr/kurlar/today.xml",
                                     headers={"User-Agent": "AGFO-Subscription-Manager"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            root = ET.fromstring(r.read())
        rates = dict(self.data["rates"])
        for cur in root.findall("Currency"):
            code = cur.get("CurrencyCode") or cur.get("Kod")
            if code in ("USD", "EUR", "GBP"):
                txt = (cur.findtext("ForexSelling") or "").strip()
                unit = float((cur.findtext("Unit") or "1").strip() or 1)
                if txt:
                    rates[code] = float(txt) / unit
        rates["TRY"] = 1.0
        self.data["rates"] = rates
        self.data["rates_date"] = dt.date.today().isoformat()
        self.save()
        return rates


def norm(s):
    s = (s or "").lower()
    for a, b in (("ı", "i"), ("ş", "s"), ("ğ", "g"), ("ü", "u"), ("ö", "o"), ("ç", "c")):
        s = s.replace(a, b)
    for junk in (" inc.", " inc", " llc", " ltd.", " ltd", " gmbh", " pte.", " pte", " a.s.", " s.l.",
                 " limited", " corporation", ",", "."):
        s = s.replace(junk, " ")
    return " ".join(s.split())


def fmt_money(amount, currency):
    if amount in (None, ""):
        return "?"
    sym = CURRENCY_SYMBOL.get(currency, currency + " ")
    s = f"{float(amount):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sym}{s}"


def fmt_try(v):
    if v is None:
        return "?"
    return fmt_money(v, "TRY")


def parse_date(s):
    if not s:
        return None
    for f in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(s.strip(), f).date()
        except ValueError:
            pass
    return None


def roll_forward(date_str, period):
    """If a renewal date is in the past, move it forward by its period until it is not."""
    d = parse_date(date_str)
    if not d or period not in ("weekly", "monthly", "quarterly", "yearly", "biennial"):
        return date_str
    today = dt.date.today()
    guard = 0
    while d < today and guard < 200:
        guard += 1
        if period == "weekly":
            d += dt.timedelta(days=7)
        else:
            months = {"monthly": 1, "quarterly": 3, "yearly": 12, "biennial": 24}[period]
            m = d.month - 1 + months
            y = d.year + m // 12
            m = m % 12 + 1
            day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28,
                              31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
            d = dt.date(y, m, day)
    return d.isoformat()
