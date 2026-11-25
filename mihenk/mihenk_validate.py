# -*- coding: utf-8 -*-
"""Girdi temizleme, tarih islemleri ve tolerans degerlendirmesi."""
from __future__ import annotations

import datetime
import json

STAMP = '%Y-%m-%d %H:%M:%S'
DAY = '%Y-%m-%d'

ACCEPTED = (STAMP, '%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M', DAY,
            '%d.%m.%Y %H:%M', '%d.%m.%Y')


class MihenkError(Exception):
    """Kullaniciya gosterilecek dogrulama hatasi."""


def now() -> str:
    """Simdiki yerel zaman, kayit bicimiyle."""
    return datetime.datetime.now().strftime(STAMP)


def parse(value):
    """Metni datetime'a cevirir. Bos ya da anlasilmaz deger None doner."""
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value
    text = str(value).strip()
    if not text or text.startswith('0000-00-00'):
        return None
    for fmt in ACCEPTED:
        try:
            return datetime.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def stamp(value):
    """Metni kayit bicimine getirir; anlasilmazsa None."""
    dt = parse(value)
    return dt.strftime(STAMP) if dt else None


def day(value):
    """Metni gun bicimine getirir; anlasilmazsa None."""
    dt = parse(value)
    return dt.strftime(DAY) if dt else None


def require_stamp(value, label: str) -> str:
    """Zorunlu tarih alani: bos ya da gecersizse anlasilir hata verir."""
    out = stamp(value)
    if not out:
        raise MihenkError('%s geçerli bir tarih olmalı (ör. 2026-11-25 09:30).' % label)
    return out


def human(value, with_time=False, fmt=DAY) -> str:
    """Ekranda gosterilecek bicim. Bos deger bos metin doner."""
    dt = parse(value)
    if not dt:
        return ''
    return dt.strftime(fmt + (' %H:%M' if with_time else ''))


def enum(value, allowed, fallback):
    """Degeri bilinen kumeye hapseder."""
    text = ('' if value is None else str(value)).strip()
    return text if text in allowed else fallback


def text(value, limit=191) -> str:
    """Tek satirlik metin: bosluklari kirpar, satir sonlarini bosluga cevirir."""
    out = ('' if value is None else str(value)).replace('\r', ' ').replace('\n', ' ').strip()
    return out[:limit]


def multiline(value, limit=20000) -> str:
    """Cok satirli metin."""
    out = ('' if value is None else str(value)).replace('\r\n', '\n').strip()
    return out[:limit]


def integer(value, minimum=None, maximum=None, default=0) -> int:
    """Tam sayi; anlasilmazsa varsayilan."""
    try:
        out = int(float(str(value).strip().replace(',', '.')))
    except (TypeError, ValueError):
        out = default
    if minimum is not None:
        out = max(minimum, out)
    if maximum is not None:
        out = min(maximum, out)
    return out


def number(value):
    """Ondalik sayi; bos ya da anlasilmaz deger None."""
    if value is None:
        return None
    raw = str(value).strip().replace(',', '.')
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def add_interval(base, value: int, unit: str) -> str:
    """Bir tarihe aralik ekler. Ay ve yil, ayin son gununu tasirmadan ilerler."""
    dt = parse(base) or datetime.datetime.now()
    value = max(1, integer(value, 1, None, 1))
    if unit == 'day':
        dt = dt + datetime.timedelta(days=value)
    elif unit == 'week':
        dt = dt + datetime.timedelta(weeks=value)
    elif unit == 'year':
        dt = _shift_months(dt, value * 12)
    else:
        dt = _shift_months(dt, value)
    return dt.strftime(STAMP)


def _shift_months(dt: datetime.datetime, months: int) -> datetime.datetime:
    """31 Ocak + 1 ay = 28/29 Subat. Gun tasmasi kirpilir."""
    total = (dt.year * 12 + (dt.month - 1)) + months
    year, month = divmod(total, 12)
    month += 1
    last = _days_in_month(year, month)
    return dt.replace(year=year, month=month, day=min(dt.day, last))


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        nxt = datetime.date(year + 1, 1, 1)
    else:
        nxt = datetime.date(year, month + 1, 1)
    return (nxt - datetime.date(year, month, 1)).days


def days_between(start, end) -> int:
    """Iki tarih arasindaki tam gun farki. Anlasilmazsa 0."""
    a, b = parse(start), parse(end)
    if not a or not b:
        return 0
    return (b - a).days


def measurement_points(raw) -> list:
    """Olcum noktasi tablosunu normal bicime getirir.

    Girdi JSON metni ya da sozluk listesi olabilir. Toleransi olmayan bir nokta
    tek basina uygunlugu kanitlayamaz, bu yuzden karari 'na' kalir.
    """
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return []
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    if not isinstance(raw, (list, tuple)):
        return []
    points = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        label = text(row.get('label', ''), 120)
        nominal = number(row.get('nominal'))
        measured = number(row.get('measured'))
        tolerance = number(row.get('tolerance'))
        if tolerance is not None:
            tolerance = abs(tolerance)
        if not label and nominal is None and measured is None:
            continue
        deviation = None
        if nominal is not None and measured is not None:
            deviation = round(measured - nominal, 6)
        verdict = 'na'
        if deviation is not None and tolerance is not None:
            verdict = 'pass' if abs(deviation) <= tolerance else 'fail'
        points.append({
            'label': label,
            'nominal': nominal,
            'measured': measured,
            'tolerance': tolerance,
            'unit': text(row.get('unit', ''), 24),
            'deviation': deviation,
            'verdict': verdict,
        })
    return points


def evaluate_points(points) -> dict:
    """Noktalardan genel karari ve en buyuk sapmayi cikarir."""
    worst = None
    seen_pass = False
    for point in points:
        deviation = point.get('deviation')
        if deviation is not None:
            size = abs(deviation)
            if worst is None or size > worst:
                worst = size
        if point.get('verdict') == 'fail':
            return {'verdict': 'fail', 'max_deviation': worst}
        if point.get('verdict') == 'pass':
            seen_pass = True
    return {'verdict': 'pass' if seen_pass else 'unknown', 'max_deviation': worst}


def dump_points(points) -> str:
    """Noktalari kayit icin JSON'a cevirir."""
    return json.dumps(points, ensure_ascii=False)


def load_points(raw) -> list:
    """Kayittaki JSON'u geri okur; bozuksa bos liste."""
    if not raw:
        return []
    try:
        out = json.loads(raw)
    except ValueError:
        return []
    return out if isinstance(out, list) else []
