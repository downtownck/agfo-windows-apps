# -*- coding: utf-8 -*-
"""Vadesi gelen planlardan kayit uretir.

Tarama elle calistirilir ya da uygulama acilisinda bir kez yapilir. Ayni plan
icin acik bir kayit varken ikincisi uretilmez; tarama tekrar tekrar
calistirilabilir.
"""
from __future__ import annotations

import datetime

import mihenk_audit as audit
import mihenk_store as store
import mihenk_validate as v
from mihenk_repo import AssetRepo, CalibrationRepo, ScheduleRepo, WorkOrderRepo


def _empty() -> dict:
    return {'work_orders': 0, 'calibrations': 0, 'skipped': 0}


def _add(total: dict, made: str) -> None:
    if made == 'work_order':
        total['work_orders'] += 1
    elif made == 'calibration':
        total['calibrations'] += 1
    else:
        total['skipped'] += 1


def scan(conn) -> dict:
    """Takvim ve sayac tabanli butun planlari tarar."""
    total = _empty()
    now = v.parse(v.now())
    for plan in ScheduleRepo.query(conn, is_active=True, basis='time'):
        due = v.parse(plan['next_due_at'])
        if not due:
            continue
        if (due - now).days > int(plan['lead_days']):
            continue
        _add(total, generate_for_plan(conn, plan))

    counter = scan_counter_plans(conn)
    for key in total:
        total[key] += counter[key]

    store.save_settings({})  # ayar dosyasi yoksa olussun
    _remember_scan(total)
    return total


def scan_counter_plans(conn, asset_id=0) -> dict:
    """Sayac hedefini gecmis planlari tarar."""
    total = _empty()
    for plan in ScheduleRepo.query(conn, asset_id=asset_id, is_active=True, basis='counter'):
        if int(plan['counter_interval']) < 1:
            continue
        asset = AssetRepo.get(conn, int(plan['asset_id']))
        if not asset:
            continue
        if int(asset['counter_value']) < int(plan['next_due_counter']):
            continue
        _add(total, generate_for_plan(conn, plan))
    return total


def generate_for_plan(conn, plan: dict) -> str:
    """Planin gerektirdigi kaydi uretir. Zaten acik kayit varsa atlar."""
    asset = AssetRepo.get(conn, int(plan['asset_id']))
    if not asset or asset['status'] == 'retired':
        return 'skipped'

    if plan['plan_type'] == 'pm':
        if WorkOrderRepo.has_open_for_schedule(conn, int(plan['id'])):
            return 'skipped'
        work_order_id = WorkOrderRepo.create(conn, {
            'asset_id': int(plan['asset_id']),
            'schedule_id': int(plan['id']),
            'wo_type': 'preventive',
            'title': plan['title'],
            'priority': 'high' if int(asset['criticality']) >= 3 else 'normal',
            'assigned_to': plan['assignee'],
            'planned_start': plan['next_due_at'],
        })
        # Sablonun o anki hali is emrine kopyalanir; sonra sablon degisirse bu
        # is emri degismez.
        from mihenk_checklist import WorkOrderChecklist
        WorkOrderChecklist.copy_from_plan(conn, work_order_id, int(plan['id']))
        audit.result(conn, 'schedule', int(plan['id']), 'generated_work_order',
                     {'work_order_id': work_order_id})
        return 'work_order'

    if CalibrationRepo.has_open_for_schedule(conn, int(plan['id'])):
        return 'skipped'
    record_id = CalibrationRepo.create(conn, {
        'asset_id': int(plan['asset_id']),
        'schedule_id': int(plan['id']),
        'record_type': 'verification' if plan['plan_type'] == 'verification' else 'calibration',
    })
    audit.result(conn, 'schedule', int(plan['id']), 'generated_calibration', {'calibration_id': record_id})
    return 'calibration'


def overdue(conn, limit=100) -> list:
    """Vadesi gecmis planlar, tolere edilen gecikme dusuldukten sonra."""
    now = v.parse(v.now())
    out = []
    for plan in ScheduleRepo.query(conn, is_active=True):
        due = v.parse(plan['next_due_at'])
        if not due:
            continue
        if (now - due).days > int(plan['tolerance_days']):
            out.append(plan)
    out.sort(key=lambda p: p['next_due_at'] or '')
    return out[:limit]


def upcoming(conn, limit=100) -> list:
    """Vadesi yaklasan ama henuz gecmemis planlar."""
    now = v.parse(v.now())
    out = []
    for plan in ScheduleRepo.query(conn, is_active=True):
        due = v.parse(plan['next_due_at'])
        if not due or due < now:
            continue
        if (due - now).days <= int(plan['lead_days']):
            out.append(plan)
    out.sort(key=lambda p: p['next_due_at'] or '')
    return out[:limit]


def counter_pressure(conn) -> list:
    """Sayac hedefine yaklasan ya da gecmis planlar, kalan birim ile birlikte."""
    out = []
    for plan in ScheduleRepo.query(conn, is_active=True, basis='counter'):
        asset = AssetRepo.get(conn, int(plan['asset_id']))
        if not asset:
            continue
        remaining = int(plan['next_due_counter']) - int(asset['counter_value'])
        if remaining <= max(1, int(plan['counter_interval']) // 10):
            out.append({'plan': plan, 'asset': asset, 'remaining': remaining})
    out.sort(key=lambda item: item['remaining'])
    return out


def _remember_scan(total: dict) -> None:
    """Son tarama zamanini ayar dosyasinin yanina yazar (ayar semasini kirletmeden)."""
    try:
        path = store.data_dir() / 'last-scan.txt'
        with open(path, 'w', encoding='utf-8') as f:
            f.write('%s\t%d\t%d\t%d\n' % (datetime.datetime.now().strftime(v.STAMP),
                                          total['work_orders'], total['calibrations'], total['skipped']))
    except OSError:
        pass


def last_scan() -> dict:
    """Son taramanin zamani ve sonucu. Hic calismamissa bos sozluk."""
    try:
        with open(store.data_dir() / 'last-scan.txt', encoding='utf-8') as f:
            parts = f.read().strip().split('\t')
        if len(parts) == 4:
            return {'at': parts[0], 'work_orders': int(parts[1]),
                    'calibrations': int(parts[2]), 'skipped': int(parts[3])}
    except (OSError, ValueError):
        pass
    return {}
