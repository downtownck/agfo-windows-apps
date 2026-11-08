"""Find recurring charges in a bank / credit-card statement (CSV or XLSX)."""
import csv
import io
import re
import statistics
import datetime as dt

from mailscan import parse_number

DATE_KEYS = ["tarih", "date", "işlem tarihi", "islem tarihi", "valör", "valor", "posting"]
DESC_KEYS = ["açıklama", "aciklama", "description", "işlem", "islem", "merchant", "detay", "details", "narrative"]
AMOUNT_KEYS = ["tutar", "amount", "miktar", "işlem tutarı", "islem tutari"]
DEBIT_KEYS = ["borç", "borc", "debit", "çıkış", "cikis"]


def _read_rows(path):
    if path.lower().endswith((".xlsx", ".xlsm")):
        try:
            import openpyxl
        except ImportError:
            raise RuntimeError("XLSX okumak için openpyxl gerekli (Derle-ve-Kur.cmd kurar). CSV olarak da verebilirsin.")
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        return [["" if c is None else c for c in row] for row in ws.iter_rows(values_only=True)]
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "cp1254", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialect = csv.Sniffer().sniff(text[:5000], delimiters=";,\t|")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";" if text.count(";") > text.count(",") else ","
    return list(csv.reader(io.StringIO(text), dialect))


def _find_header(rows):
    for i, row in enumerate(rows[:40]):
        cells = [str(c).strip().lower() for c in row]
        has_date = any(any(k in c for k in DATE_KEYS) for c in cells)
        has_amt = any(any(k in c for k in AMOUNT_KEYS + DEBIT_KEYS) for c in cells)
        if has_date and has_amt:
            return i, cells
    raise RuntimeError("Başlık satırı bulunamadı (Tarih / Açıklama / Tutar sütunları gerekli).")


def _col(cells, keys):
    for k in keys:
        for j, c in enumerate(cells):
            if k in c:
                return j
    return None


def _to_date(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    s = str(v).strip()
    for f in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%y", "%m/%d/%Y", "%d.%m.%Y %H:%M", "%d.%m.%Y %H:%M:%S"):
        try:
            return dt.datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


def _to_num(v):
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("TL", "").replace("TRY", "").replace("₺", "").strip()
    neg = s.startswith("-") or s.endswith("-") or (s.startswith("(") and s.endswith(")"))
    s = s.strip("-() +")
    n = parse_number(s) if s else None
    if n is None:
        return None
    return -n if neg else n


def normalize_desc(s):
    s = str(s).upper()
    s = re.sub(r"\S*\d{4,}\S*", " ", s)        # card numbers, refs (also masked ones)
    s = re.sub(r"\b[X*]{3,}\S*", " ", s)
    s = re.sub(r"\b\d{1,2}[./]\d{1,2}([./]\d{2,4})?\b", " ", s)
    s = re.sub(r"[^A-ZÇĞİÖŞÜ0-9 .*&+-]", " ", s)
    s = re.sub(r"\b(IST|ISTANBUL|TR|TUR|USA|US|IE|GB|NL|DE|SE|SG|CA|IRL|DUBLIN|SAN FRANCISCO)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return " ".join(s.split()[:4])


def find_recurring(path, min_months=2, tolerance=0.25):
    rows = _read_rows(path)
    hi, cells = _find_header(rows)
    c_date = _col(cells, DATE_KEYS)
    c_desc = _col(cells, DESC_KEYS)
    c_amt = _col(cells, AMOUNT_KEYS)
    c_debit = _col(cells, DEBIT_KEYS)
    if c_date is None or c_desc is None or (c_amt is None and c_debit is None):
        raise RuntimeError("Tarih, açıklama ve tutar sütunları tanınamadı.")

    tx = []
    for row in rows[hi + 1:]:
        if len(row) <= max(x for x in (c_date, c_desc, c_amt, c_debit) if x is not None):
            continue
        d = _to_date(row[c_date])
        if not d:
            continue
        amt = None
        if c_debit is not None and str(row[c_debit]).strip():
            amt = _to_num(row[c_debit])
            amt = -abs(amt) if amt else None
        elif c_amt is not None:
            amt = _to_num(row[c_amt])
        if not amt:
            continue
        tx.append((d, normalize_desc(row[c_desc]), amt, str(row[c_desc]).strip()))

    # credit-card statements list spending as positive numbers; bank accounts as negative
    neg = sum(1 for t in tx if t[2] < 0)
    spend_sign = -1 if neg >= len(tx) / 2 else 1
    groups = {}
    for d, key, amt, raw in tx:
        if key and amt * spend_sign > 0:
            groups.setdefault(key, []).append((d, abs(amt), raw))

    out = []
    for key, items in groups.items():
        months = {(d.year, d.month) for d, _, _ in items}
        if len(months) < min_months:
            continue
        amts = [a for _, a, _ in items]
        med = statistics.median(amts)
        if med <= 0 or (max(amts) - min(amts)) / med > tolerance * 2:
            # allow price changes, but not wildly different amounts
            close = [a for a in amts if abs(a - med) / med <= tolerance]
            if len(close) < min_months:
                continue
        dates = sorted(d for d, _, _ in items)
        gaps = [(b - a).days for a, b in zip(dates, dates[1:])] or [30]
        g = statistics.median(gaps)
        period = "weekly" if g <= 10 else "monthly" if g <= 45 else "quarterly" if g <= 120 else "yearly"
        latest = max(items, key=lambda x: x[0])
        out.append({
            "name": key.title(), "vendor": key.title(), "amount": round(latest[1], 2), "currency": "TRY",
            "period": period, "next_renewal": "", "channel": "Banka/Kart", "status": "active",
            "account_email": "", "payment": "", "sender": "", "subject": latest[2],
            "date": latest[0].isoformat(), "count": len(items), "months": len(months),
            "first_seen": dates[0].isoformat(),
        })
    out.sort(key=lambda x: -x["amount"])
    return out
