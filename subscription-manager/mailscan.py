"""Scan IMAP mailboxes for subscription receipts / renewals / failed payments.

Read-only: messages are fetched with BODY.PEEK so nothing is marked as read,
and nothing is moved, deleted or sent.
"""
import email
import html
import imaplib
import re
import datetime as dt
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime

SUBJECT_HINTS = ["receipt", "invoice", "fatura", "makbuz", "subscription", "abonelik", "renew",
                 "yenilen", "payment", "ödeme", "odeme", "order", "sipariş", "trial", "deneme",
                 "membership", "üyelik", "billing", "charge", "cancel", "iptal", "plan"]
SENDER_HINTS = ["stripe.com", "paddle.com", "googleplay-noreply", "email.apple.com", "paypal",
                "fastspring", "chargebee", "lemonsqueezy", "2checkout", "recurly", "gumroad",
                "billing", "invoice", "receipt", "renewals", "payments"]
GMAIL_QUERY = ('newer_than:{m}m (subject:(receipt OR invoice OR fatura OR makbuz OR subscription OR '
               'abonelik OR renew OR renewal OR yenilenecek OR "payment failed" OR unsuccessful OR '
               'trial) OR from:(stripe.com OR paddle.com OR googleplay-noreply@google.com OR '
               'email.apple.com OR paypal OR fastspring.com OR 2checkout.com OR lemonsqueezy.com))')

MONTHS_EN = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MONTHS_TR = {m: i for i, m in enumerate(
    ["oca", "şub", "mar", "nis", "may", "haz", "tem", "ağu", "eyl", "eki", "kas", "ara"], 1)}

CUR_MAP = {"$": "USD", "€": "EUR", "£": "GBP", "₺": "TRY", "TL": "TRY", "TRY": "TRY",
           "USD": "USD", "EUR": "EUR", "GBP": "GBP"}
NUM = r"\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
AMOUNT_RE = re.compile(rf"(?P<cur>[$€£₺]|TRY|USD|EUR|GBP)\s?(?P<num>{NUM})|(?P<num2>{NUM})\s?(?P<cur2>TL|TRY|₺|USD|EUR)\b")


# ---------------------------------------------------------------- helpers
def parse_number(s):
    s = s.replace(" ", "").replace(" ", "")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        s = s.replace(",", ".") if len(tail) <= 2 else s.replace(",", "")
    elif "." in s:
        head, _, tail = s.rpartition(".")
        if len(tail) == 3 and head:
            s = s.replace(".", "")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def find_amount(text):
    for m in AMOUNT_RE.finditer(text or ""):
        cur = m.group("cur") or m.group("cur2")
        num = m.group("num") or m.group("num2")
        val = parse_number(num)
        if val and val > 0:
            return val, CUR_MAP.get(cur, "TRY")
    return None, None


def detect_period(text):
    t = (text or "").lower()
    if re.search(r"/\s?(yıl|year|yr)\b|yearly|annual|yıllık|\b1 year\b|per year|this past year|another full year", t):
        return "yearly"
    if re.search(r"/\s?(ay|month|mo)\b|monthly|aylık|per month", t):
        return "monthly"
    if re.search(r"/\s?(hafta|week)\b|weekly|haftalık", t):
        return "weekly"
    if re.search(r"quarterly|3 aylık|\(local sub\. quarterly\)", t):
        return "quarterly"
    # Stripe style period: "Oct 23–Nov 23, 2026" or "Jul 18, 2026–Jul 18, 2027"
    m = re.search(r"([A-Z][a-z]{2}) (\d{1,2})(?:, (\d{4}))?\s?[–-]\s?([A-Z][a-z]{2}) (\d{1,2}), (\d{4})", text or "")
    if m:
        m1, y1 = MONTHS_EN.get(m.group(1).lower()), int(m.group(3) or m.group(6))
        m2, y2 = MONTHS_EN.get(m.group(4).lower()), int(m.group(6))
        if m1 and m2:
            span = (y2 - y1) * 12 + (m2 - m1)
            if span >= 11:
                return "yearly"
            if span in (2, 3):
                return "quarterly"
            if span == 1:
                return "monthly"
    return "unknown"


def find_date_after(text, *anchors):
    """Find the first date that follows one of the anchor phrases."""
    for a in anchors:
        i = (text or "").lower().find(a.lower())
        if i < 0:
            continue
        chunk = text[i:i + 80]
        d = parse_any_date(chunk)
        if d:
            return d
    return None


def parse_any_date(s):
    s = s or ""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b", s)
    if m:
        try:
            return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    m = re.search(r"\b([A-Z][a-z]{2})[a-z]*\.? (\d{1,2}),? (\d{4})", s)
    if m and m.group(1).lower() in MONTHS_EN:
        return dt.date(int(m.group(3)), MONTHS_EN[m.group(1).lower()], int(m.group(2)))
    m = re.search(r"\b(\d{1,2}) ([A-Za-zÇĞİÖŞÜçğıöşü]{3})[A-Za-zçğıöşü]* (\d{4})", s)
    if m:
        k = m.group(2).lower()
        mon = MONTHS_TR.get(k) or MONTHS_EN.get(k)
        if mon:
            return dt.date(int(m.group(3)), mon, int(m.group(1)))
    return None


def dec(s):
    try:
        return str(make_header(decode_header(s or "")))
    except Exception:
        return s or ""


def body_text(msg):
    plain, htm = [], []
    for part in msg.walk() if msg.is_multipart() else [msg]:
        ctype = part.get_content_type()
        if part.get("Content-Disposition", "").lower().startswith("attachment"):
            continue
        if ctype not in ("text/plain", "text/html"):
            continue
        try:
            payload = part.get_payload(decode=True) or b""
            txt = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            continue
        (plain if ctype == "text/plain" else htm).append(txt)
    if plain:
        text = "\n".join(plain)
    else:
        text = "\n".join(htm)
        text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
        text = re.sub(r"(?i)<br\s*/?>|</p>|</tr>|</div>", "\n", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
    text = re.sub(r"[ \t ͏‌﻿]+", " ", text)
    return text[:20000]


# ---------------------------------------------------------------- parsing
def parse_message(sender, subject, date, body, account=""):
    """Return a finding dict or None."""
    name_disp, addr = parseaddr(sender)
    name_disp = dec(name_disp)
    if "<" in (sender or "") and (not name_disp or "," in sender.split("<")[0]):
        name_disp = sender.split("<")[0].strip().strip('"')
        am = re.search(r"<([^>]+)>", sender)
        if am:
            addr = am.group(1).strip().lower()
    addr = (addr or "").lower()
    subj = subject or ""
    low_subj = subj.lower()
    text = f"{subj}\n{body}"
    f = {"name": "", "vendor": "", "amount": None, "currency": "", "period": "unknown",
         "next_renewal": "", "channel": "", "status": "active", "account_email": account,
         "sender": addr, "subject": subj, "date": date.isoformat() if date else "", "payment": ""}

    # payment card hint
    m = re.search(r"(Visa|Mastercard|Amex|American Express)[-\s*•]*(\d{4})", body or "", re.I)
    if m:
        f["payment"] = f"{m.group(1).title()} •{m.group(2)}"
    else:
        m = re.search(r"(?:ending in|with -|Payment method -)\s*(\d{4})", body or "")
        if m:
            f["payment"] = f"Kart •{m.group(1)}"

    if re.search(r"unsuccessful|failed|başarısız|couldn.t process|insufficient|declined|past due", low_subj + (body or "")[:600].lower()):
        f["status"] = "failing"
    if re.search(r"cancel|iptal edil|sona eriyor|sona erecek|ending soon|benefits are ending|expire", low_subj):
        f["status"] = "cancel_scheduled"

    # ---- Google Play
    if "googleplay-noreply" in addr:
        f["channel"] = "Google Play"
        m = (re.search(r"Google Play'de(?:ki)? (.+?) (?:adlı satıcıdan|aboneliğiniz)", body) or
             re.search(r"subscription from (.+?) on Google Play", body) or
             re.search(r"Google Play'de(?:ki)? (.+?) ", body))
        seller = m.group(1).strip() if m else ""
        pm = re.search(r"^(.+?)\s+([₺$€£][\d.,]+)\s*/\s*(ay|yıl|hafta|month|year|week)", body, re.M)
        if pm:
            prod = pm.group(1).strip()
            f["amount"], f["currency"] = find_amount(pm.group(2))
            f["period"] = detect_period("/" + pm.group(3))
            pn = re.search(r"\((.+?)\)\s*$", prod)
            f["name"] = (pn.group(1) if pn else prod)[:60]
        else:
            m2 = re.search(r"(?:Sayın \w+, )?(.+?) \((.+?)\) aboneliğiniz", body)
            f["name"] = (m2.group(2) if m2 else seller)[:60]
        f["vendor"] = seller or f["name"]
        f["name"] = f["name"] or seller
        nr = find_date_after(body, "otomatik olarak yenilenecektir", "deneme süreniz", "will renew")
        if nr:
            f["next_renewal"] = nr.isoformat()
        if "sona erecek" in low_subj or "ending soon" in low_subj or "sona eriyor" in low_subj:
            f["status"] = "cancel_scheduled"
        return f if f["name"] else None

    # ---- Apple
    if addr.endswith("apple.com") and ("fatura" in low_subj or "makbuz" in low_subj or "receipt" in low_subj
                                       or "invoice" in low_subj or "fiyat" in low_subj):
        f["channel"] = "Apple"
        m = re.search(r"Apple (?:Hesabı|Account|ID): (\S+)", body)
        if m:
            f["account_email"] = m.group(1)
        m = re.search(r"\((Aylık|Yıllık|Monthly|Yearly|Haftalık|Weekly|1 ay|1 yıl)\)", body)
        if m:
            pre = body[max(0, m.start() - 120):m.start()]
            pre = re.split(r"Apple (?:Hesabı|Account|ID): \S+", pre)[-1].strip()
            words = pre.split()
            if len(words) > 1 and words[1].lower().startswith(words[0].lower()):
                words = words[1:]
            f["name"] = " ".join(words)[:60]
            f["period"] = detect_period(m.group(1))
        m = re.search(r"(?:Yenileme|Renews?):? ([^₺$€£\n]+?)\s*([₺$€£]\s?[\d.,]+)", body)
        if m:
            d = parse_any_date(m.group(1))
            if d:
                f["next_renewal"] = d.isoformat()
            f["amount"], f["currency"] = find_amount(m.group(2))
        f["vendor"] = "Apple"
        f["name"] = f["name"] or "Apple aboneliği"
        return f

    # ---- Paddle
    if "paddle.com" in addr:
        f["channel"] = "Paddle"
        m = re.search(r"Your (.+?) (?:subscription )?receipt", subj + "\n" + body) or \
            re.search(r"^(.+?) \(via Paddle", name_disp) or re.search(r"^(.+?) paddle\.com", body or "")
        vendor = m.group(1).strip() if m else name_disp
        f["vendor"] = vendor
        m = re.search(r"Amount Paid\s+([A-Z]{3})\s?([\d.,]+)", body)
        if m:
            f["amount"], f["currency"] = parse_number(m.group(2)), CUR_MAP.get(m.group(1), m.group(1))
        else:
            f["amount"], f["currency"] = find_amount(body)
        pm = re.search(r"(?:ending in|Payment Method[^\n]*?)\s*\d{4}\s+(.+?)\s+(?:TRY|USD|EUR|GBP|[$€£₺])\s?[\d.,]+", body)
        f["name"] = (pm.group(1).strip() if pm else vendor)[:60]
        f["period"] = detect_period(body)
        if "iptal edilecek" in body or "will be cancel" in body.lower():
            f["status"] = "cancel_scheduled"
            d = find_date_after(body, "tarihinde iptal", "Aboneliğiniz ", "cancelled on")
            if d:
                f["next_renewal"] = d.isoformat()
        return f

    # ---- PayPal
    if "paypal" in addr:
        m = re.search(r"You paid ([€$£₺]?[\d.,]+)\s?([A-Z]{3})? to (.+?)(?:\s+Merchant|\n|$)", body)
        if not m:
            return None
        f["channel"] = "PayPal"
        f["amount"], f["currency"] = find_amount(m.group(1) + (" " + m.group(2) if m.group(2) else ""))
        f["vendor"] = f["name"] = m.group(3).strip()
        f["period"] = "unknown"
        return f

    # ---- Stripe (receipts, upcoming invoices, failed payments, trials)
    if "stripe.com" in addr or addr.startswith("invoice+statements") or "receipts+" in addr:
        f["channel"] = "Stripe/Web"
        vendor = name_disp
        m = re.search(r"payment to (.+?) was unsuccessful", subj)
        if m:
            vendor = m.group(1)
            f["status"] = "failing"
            f["amount"], f["currency"] = find_amount(subj)
        f["vendor"] = vendor
        products = []
        for qm in re.finditer(r"Qty \d+\s+([$€£₺][\d.,]+)", body or ""):
            pre = body[max(0, qm.start() - 120):qm.start()]
            years = list(re.finditer(r"(?:19|20)\d{2}\b", pre))
            if years:
                pre = pre[years[-1].end():]
            pre = re.sub(r"\(per [^)]*\)", "", pre).strip(" -–,")
            amt, _ = find_amount(qm.group(1))
            if pre and "Usage" not in pre and amt:
                products.append(pre)
        f["name"] = f"{vendor} – {products[-1]}"[:70] if products and products[-1].lower() != vendor.lower() else vendor
        if f["amount"] is None:
            m = re.search(r"(?:Receipt from|Amount paid|Total)\s+.*?([$€£₺][\d.,]+)", body)
            f["amount"], f["currency"] = find_amount(m.group(1) if m else body)
        f["period"] = detect_period(body)
        if "upcoming-invoice" in addr or "renew soon" in low_subj:
            d = find_date_after(body, "automatically renew on", "se renovará automáticamente el", "renew on")
            if d:
                f["next_renewal"] = d.isoformat()
            if f["period"] == "unknown" and "monthly" in body.lower():
                f["period"] = "monthly"
        if "trial-ending" in addr:
            f["status"] = "check"
            d = find_date_after(body, "will end on")
            if d:
                f["next_renewal"] = d.isoformat()
        return f

    # ---- generic
    if not any(h in low_subj for h in SUBJECT_HINTS):
        return None
    amount, cur = find_amount(text)
    renew = find_date_after(body, "renew on", "renews on", "will renew", "yenilenecek", "yenileme tarihi", "Yenileme:")
    if amount is None and renew is None and f["status"] == "active":
        return None
    f["channel"] = "Doğrudan"
    f["vendor"] = name_disp or addr.split("@")[-1]
    f["name"] = f["vendor"]
    f["amount"], f["currency"] = amount, cur or ""
    f["period"] = detect_period(text)
    if renew:
        f["next_renewal"] = renew.isoformat()
    return f


def aggregate(findings):
    """Group findings by vendor/name; keep the latest values and count charges."""
    groups = {}
    for f in findings:
        key = (f.get("channel"), (f.get("name") or f.get("vendor") or "").lower().strip())
        g = groups.setdefault(key, {"findings": []})
        g["findings"].append(f)
    out = []
    for g in groups.values():
        fs = sorted(g["findings"], key=lambda x: x.get("date") or "")
        latest = dict(fs[-1])
        for f in reversed(fs):  # fill gaps from older messages
            for k in ("amount", "currency", "period", "payment", "next_renewal"):
                if latest.get(k) in (None, "", "unknown") and f.get(k) not in (None, "", "unknown"):
                    latest[k] = f[k]
        months = {(f.get("date") or "")[:7] for f in fs if f.get("date")}
        latest["count"] = len(fs)
        latest["months"] = len(months)
        latest["first_seen"] = fs[0].get("date", "")
        if latest["period"] == "unknown" and len(months) >= 3:
            latest["period"] = "monthly"
        out.append(latest)
    out.sort(key=lambda x: (x["status"] != "failing", -(x.get("months") or 0), x.get("name", "")))
    return out


# ---------------------------------------------------------------- IMAP
class ScanCancelled(Exception):
    pass


def _all_mail_folder(M):
    try:
        typ, data = M.list()
        for line in data or []:
            s = line.decode(errors="replace") if isinstance(line, bytes) else str(line)
            if "\\All" in s:
                name = s.rsplit(' "/" ', 1)[-1].strip()
                return name if name.startswith('"') else f'"{name}"'
    except Exception:
        pass
    return "INBOX"


def scan_account(host, port, user, password, months=13, ignore_domains=(), progress=None, stop=None):
    def say(msg):
        if progress:
            progress(msg)

    say(f"{user}: bağlanılıyor ({host})…")
    M = imaplib.IMAP4_SSL(host, int(port or 993))
    try:
        M.login(user, password)
        is_gmail = "gmail" in host.lower() or "googlemail" in host.lower()
        folder = _all_mail_folder(M) if is_gmail else "INBOX"
        M.select(folder, readonly=True)
        if is_gmail:
            q = GMAIL_QUERY.format(m=int(months))
            typ, data = M.search(None, "X-GM-RAW", '"' + q.replace('"', '\\"') + '"')
        else:
            since = (dt.date.today() - dt.timedelta(days=int(months) * 31)).strftime("%d-%b-%Y")
            typ, data = M.search(None, "SINCE", since)
        ids = (data[0] or b"").split() if data else []
        say(f"{user}: {len(ids)} ileti bulundu, başlıklar okunuyor…")

        # header pass (cheap) for non-gmail, filtered locally
        candidates = []
        for i in range(0, len(ids), 200):
            if stop and stop():
                raise ScanCancelled()
            chunk = b",".join(ids[i:i + 200])
            typ, rows = M.fetch(chunk, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            for row in rows or []:
                if not isinstance(row, tuple):
                    continue
                num = row[0].split()[0]
                hdr = email.message_from_bytes(row[1])
                frm = dec(hdr.get("From", ""))
                subj = dec(hdr.get("Subject", ""))
                addr = parseaddr(frm)[1].lower()
                if any(addr.endswith("@" + d) or addr.endswith("." + d) for d in ignore_domains):
                    continue
                if is_gmail or any(h in subj.lower() for h in SUBJECT_HINTS) or any(h in addr for h in SENDER_HINTS):
                    candidates.append(num)
            say(f"{user}: başlıklar {min(i + 200, len(ids))}/{len(ids)}")

        findings = []
        for n, num in enumerate(candidates, 1):
            if stop and stop():
                raise ScanCancelled()
            typ, rows = M.fetch(num, "(BODY.PEEK[])")
            raw = next((r[1] for r in rows or [] if isinstance(r, tuple)), None)
            if not raw:
                continue
            msg = email.message_from_bytes(raw)
            try:
                date = parsedate_to_datetime(msg.get("Date")).date()
            except Exception:
                date = None
            f = parse_message(dec(msg.get("From", "")), dec(msg.get("Subject", "")), date, body_text(msg), user)
            if f:
                findings.append(f)
            if n % 10 == 0 or n == len(candidates):
                say(f"{user}: ileti {n}/{len(candidates)} çözümlendi, {len(findings)} bulgu")
        return findings
    finally:
        try:
            M.logout()
        except Exception:
            pass
