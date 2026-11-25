# -*- coding: utf-8 -*-
"""Gostergeler ve rapor verisi.

Burada yalnizca sayi uretilir; cizim ve disa aktarim ayri modullerde. Her
gosterge, hangi kayitlardan hesaplandigini da dondurur, cunku bir denetcide
"bu oran nereden geliyor" sorusu her zaman gelir.
"""
from __future__ import annotations

import datetime

import mihenk_validate as v
from mihenk_parts import PartRepo
from mihenk_repo import AssetRepo, CalibrationRepo, ImpactRepo, ScheduleRepo, WorkOrderRepo

PERIODS = {
    '30': 'Son 30 gün',
    '90': 'Son 90 gün',
    '180': 'Son 6 ay',
    '365': 'Son 12 ay',
    '0': 'Tümü',
}


def period_start(days) -> str:
    """Donem baslangici. 0 ya da bos butun kayitlari kapsar."""
    days = int(days or 0)
    if days <= 0:
        return '1970-01-01 00:00:00'
    return (datetime.datetime.now() - datetime.timedelta(days=days)).strftime(v.STAMP)


def _minutes(start, end):
    a, b = v.parse(start), v.parse(end)
    if not a or not b or b < a:
        return None
    return (b - a).total_seconds() / 60.0


def plan_compliance(conn, days=365) -> dict:
    """Plandan uretilmis is emirlerinin zamaninda kapanma orani.

    Payda: donem icinde planlanmis ve artik acik olmayan is emirleri.
    Zamaninda sayilan: planlanan bitisten once ya da tolere edilen gecikme
    icinde tamamlanmis olanlar.
    """
    start = period_start(days)
    rows = [r for r in WorkOrderRepo.query(conn)
            if int(r['schedule_id']) and (r['planned_start'] or '') >= start]
    closed = [r for r in rows if r['status'] in ('completed', 'closed')]
    on_time = 0
    late = []
    for row in closed:
        plan = ScheduleRepo.get(conn, int(row['schedule_id']))
        tolerance = int(plan['tolerance_days']) if plan else 0
        due = v.parse(row['planned_end'] or row['planned_start'])
        done = v.parse(row['actual_end'])
        if not due or not done:
            continue
        if (done - due).days <= tolerance:
            on_time += 1
        else:
            late.append(row)
    total = len(closed)
    return {
        'total': total,
        'on_time': on_time,
        'late': len(late),
        'open': len(rows) - total,
        'rate': round(100.0 * on_time / total, 1) if total else None,
        'late_rows': late,
    }


def calibration_conformity(conn, days=365) -> dict:
    """Donem icinde sonuclanmis kalibrasyonlarin dagilimi."""
    start = period_start(days)
    rows = [r for r in CalibrationRepo.query(conn)
            if r['result'] and (r['performed_at'] or '') >= start]
    counts = {'pass': 0, 'conditional': 0, 'fail': 0}
    for row in rows:
        if row['result'] in counts:
            counts[row['result']] += 1
    total = len(rows)
    return {
        'total': total,
        'counts': counts,
        'rate': round(100.0 * counts['pass'] / total, 1) if total else None,
        'fail_rows': [r for r in rows if r['result'] == 'fail'],
    }


def downtime_by_month(conn, days=365) -> list:
    """Aya gore duruş dakikasi: [(ay, dakika, is emri sayisi)]."""
    start = period_start(days)
    buckets = {}
    for row in WorkOrderRepo.query(conn):
        when = row['actual_end'] or row['actual_start'] or row['planned_start']
        if not when or when < start:
            continue
        minutes = int(row['downtime_minutes'] or 0)
        if minutes <= 0:
            continue
        key = str(when)[:7]
        total, count = buckets.get(key, (0, 0))
        buckets[key] = (total + minutes, count + 1)
    return [(key, value[0], value[1]) for key, value in sorted(buckets.items())]


def labour_by_month(conn, days=365) -> list:
    """Aya gore iscilik dakikasi: [(ay, dakika, is emri sayisi)]."""
    start = period_start(days)
    buckets = {}
    for row in WorkOrderRepo.query(conn):
        when = row['actual_end'] or row['actual_start'] or row['planned_start']
        if not when or when < start:
            continue
        minutes = int(row['labor_minutes'] or 0)
        if minutes <= 0:
            continue
        key = str(when)[:7]
        total, count = buckets.get(key, (0, 0))
        buckets[key] = (total + minutes, count + 1)
    return [(key, value[0], value[1]) for key, value in sorted(buckets.items())]


def asset_reliability(conn, days=365) -> list:
    """Varlik basina MTBF ve MTTR.

    MTBF: ardisik duzeltici is emirleri arasindaki ortalama sure (saat). Iki
    arizasi olmayan varlikta hesaplanamaz, None doner; sifir yazmak yaniltir.
    MTTR: duzeltici is emirlerinde baslangic ile bitis arasinda gecen ortalama
    sure (saat).
    """
    start = period_start(days)
    out = []
    for asset in AssetRepo.query(conn):
        rows = [r for r in WorkOrderRepo.query(conn, asset_id=int(asset['id']))
                if r['wo_type'] == 'corrective' and (r['actual_start'] or '') >= start]
        rows.sort(key=lambda r: r['actual_start'] or '')
        repairs = [_minutes(r['actual_start'], r['actual_end']) for r in rows]
        repairs = [m for m in repairs if m is not None]
        gaps = []
        for earlier, later in zip(rows, rows[1:]):
            gap = _minutes(earlier['actual_end'] or earlier['actual_start'], later['actual_start'])
            if gap is not None:
                gaps.append(gap)
        downtime = sum(int(r['downtime_minutes'] or 0) for r in rows)
        out.append({
            'asset': asset,
            'failures': len(rows),
            'mtbf_hours': round(sum(gaps) / len(gaps) / 60.0, 1) if gaps else None,
            'mttr_hours': round(sum(repairs) / len(repairs) / 60.0, 1) if repairs else None,
            'downtime_minutes': downtime,
        })
    out.sort(key=lambda item: (-item['failures'], -item['downtime_minutes']))
    return out


def deviation_history(conn, asset_id) -> list:
    """Bir olcum cihazinin sapma gecmisi: [(tarih, sapma, sonuc)]."""
    rows = CalibrationRepo.query(conn, asset_id=asset_id)
    out = []
    for row in sorted(rows, key=lambda r: r['performed_at'] or ''):
        if not row['performed_at'] or row['max_deviation'] is None:
            continue
        out.append((row['performed_at'], float(row['max_deviation']), row['result']))
    return out


def overdue_ageing(conn) -> list:
    """Geciken planlar, kac gundur geciktigiyle birlikte."""
    import mihenk_scheduler as scheduler
    now = v.parse(v.now())
    out = []
    for plan in scheduler.overdue(conn, limit=500):
        due = v.parse(plan['next_due_at'])
        out.append({'plan': plan, 'days': (now - due).days if due else 0})
    out.sort(key=lambda item: -item['days'])
    return out


def summary(conn, days=365) -> dict:
    """Panoda ve raporun basinda gosterilen ozet."""
    compliance = plan_compliance(conn, days)
    conformity = calibration_conformity(conn, days)
    downtime = downtime_by_month(conn, days)
    labour = labour_by_month(conn, days)
    return {
        'period_days': int(days or 0),
        'period_label': PERIODS.get(str(days), '%s gün' % days),
        'assets_total': AssetRepo.count(conn),
        'assets_active': AssetRepo.count(conn, 'active'),
        'assets_quarantined': AssetRepo.count(conn, 'quarantined'),
        'work_orders_open': WorkOrderRepo.count(conn, open_only=True),
        'calibrations_open': CalibrationRepo.count(conn, open_only=True),
        'impacts_open': ImpactRepo.count(conn, 'open'),
        'plans_active': len(ScheduleRepo.query(conn, is_active=True)),
        'plans_overdue': ScheduleRepo.count_due(conn, overdue_only=True),
        'compliance': compliance,
        'conformity': conformity,
        'downtime_total': sum(item[1] for item in downtime),
        'labour_total': sum(item[1] for item in labour),
        'parts_low': PartRepo.count(conn, low_only=True),
        'parts_value': PartRepo.stock_value(conn),
    }
