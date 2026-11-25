# -*- coding: utf-8 -*-
"""Durum makinesi: uygulamadaki her durum degisiminin tek yetkilisi.

Depolar status alanini dogrudan yazmaz, buradan gecer. Karantina kilidinin
gercek bir kilit olmasinin sebebi budur: kurali yalnizca ekran degil, veri
katmani uygular.
"""
from __future__ import annotations

import mihenk_validate as v

MAP = {
    'asset': {
        'active': ('out_of_service', 'quarantined', 'retired'),
        'out_of_service': ('active', 'quarantined', 'retired'),
        'quarantined': ('active', 'out_of_service', 'retired'),
        'retired': (),
    },
    'request': {
        'open': ('triaged', 'rejected'),
        'triaged': ('converted', 'rejected'),
        'converted': ('closed',),
        'rejected': ('closed',),
        'closed': (),
    },
    'work_order': {
        'new': ('assigned', 'cancelled'),
        'assigned': ('in_progress', 'on_hold', 'cancelled'),
        'in_progress': ('on_hold', 'completed', 'cancelled'),
        'on_hold': ('in_progress', 'cancelled'),
        'completed': ('closed', 'in_progress'),
        'closed': (),
        'cancelled': (),
    },
    'calibration': {
        'planned': ('in_progress', 'cancelled'),
        'in_progress': ('result_entered', 'cancelled'),
        'result_entered': ('closed',),
        'closed': (),
        'cancelled': (),
    },
    'impact': {
        'open': ('closed',),
        'closed': (),
    },
}

LABELS = {
    'asset': {
        'active': 'Aktif',
        'out_of_service': 'Hizmet dışı',
        'quarantined': 'Karantinada',
        'retired': 'Hurdaya ayrıldı',
    },
    'request': {
        'open': 'Açık',
        'triaged': 'Değerlendirildi',
        'converted': 'Dönüştürüldü',
        'rejected': 'Reddedildi',
        'closed': 'Kapalı',
    },
    'work_order': {
        'new': 'Yeni',
        'assigned': 'Atandı',
        'in_progress': 'Sürüyor',
        'on_hold': 'Beklemede',
        'completed': 'Tamamlandı',
        'closed': 'Kapalı',
        'cancelled': 'İptal edildi',
    },
    'calibration': {
        'planned': 'Planlandı',
        'in_progress': 'Sürüyor',
        'result_entered': 'Sonuç girildi',
        'closed': 'Kapalı',
        'cancelled': 'İptal edildi',
    },
    'impact': {
        'open': 'Açık',
        'closed': 'Kapalı',
    },
}

REQUIRED = {
    'work_order': {
        'in_progress': {'actual_start': 'Gerçek başlangıç'},
        'on_hold': {'hold_reason': 'Bekletme gerekçesi'},
        'completed': {
            'work_done': 'Yapılan iş',
            'actual_end': 'Gerçek bitiş',
            'labor_minutes': 'İşçilik dakikası',
        },
    },
    'request': {
        'rejected': {'rejection_reason': 'Ret gerekçesi'},
    },
    'calibration': {
        'result_entered': {
            'performed_at': 'Yapılma zamanı',
            'result': 'Sonuç',
        },
    },
    'impact': {
        'closed': {
            'affected_from': 'Etkilenen başlangıç',
            'affected_to': 'Etkilenen bitiş',
            'evaluation': 'Değerlendirme',
            'decision': 'Karar',
        },
    },
}


def label(entity: str, state: str) -> str:
    """Durumun ekranda gorunen adi."""
    return LABELS.get(entity, {}).get(state, state or '')


def states(entity: str) -> dict:
    """Bir varligin tum durumlari: anahtar -> etiket."""
    return dict(LABELS.get(entity, {}))


def next_states(entity: str, current: str) -> tuple:
    """Bulunulan durumdan gidilebilecek durumlar."""
    return tuple(MAP.get(entity, {}).get(current, ()))


def can(entity: str, current: str, target: str) -> bool:
    """Gecis haritada var mi. Korumalari degerlendirmez."""
    return target in next_states(entity, current)


def required_fields(entity: str, target: str) -> dict:
    """Hedef duruma gecmeden once dolu olmasi gereken alanlar."""
    return dict(REQUIRED.get(entity, {}).get(target, {}))


def open_impact_count(conn, asset_id: int) -> int:
    """Bir varlik icin hala acik etki degerlendirmesi sayisi."""
    row = conn.execute("SELECT COUNT(*) AS c FROM impact WHERE asset_id = ? AND status = 'open'",
                       (int(asset_id),)).fetchone()
    return int(row['c']) if row else 0


def check_required(entity: str, target: str, row: dict, data=None) -> dict:
    """Hedef durumun zorunlu alanlari dolu mu. Degilse MihenkError firlatir.

    Kaydin kendisi ile yeni gelen degerleri birlestirip bakar; gecisten ayri
    durur, cunku ayni duruma yeniden yazarken de ayni kurallar gecerlidir.
    """
    merged = dict(row)
    merged.update({k: val for k, val in (data or {}).items() if val is not None})
    missing = []
    for field, field_label in required_fields(entity, target).items():
        value = merged.get(field)
        if value is None or str(value).strip() in ('', '0'):
            missing.append(field_label)
    if missing:
        raise v.MihenkError('Önce şu alanlar doldurulmalı: %s' % ', '.join(missing))
    return merged


def guard(conn, entity: str, row: dict, target: str, data=None) -> None:
    """Gecisi ve yanindaki veriyi denetler. Uygun degilse MihenkError firlatir."""
    data = data or {}
    current = str(row.get('status') or '')
    if current == target:
        raise v.MihenkError('Kayıt zaten bu durumda.')
    if not can(entity, current, target):
        raise v.MihenkError('%s durumundan %s durumuna geçişe izin verilmiyor.'
                            % (label(entity, current), label(entity, target)))

    merged = check_required(entity, target, row, data)

    if entity == 'asset' and current == 'quarantined' and target == 'active':
        count = open_impact_count(conn, int(row['id']))
        if count:
            raise v.MihenkError(
                '%d etki değerlendirmesi açıkken bu varlık hizmete dönemez.' % count)

    if entity == 'calibration' and target == 'closed':
        result = merged.get('result') or ''
        if result == 'fail':
            impact_id = int(merged.get('impact_id') or 0)
            impact = None
            if impact_id:
                impact = conn.execute('SELECT * FROM impact WHERE id = ?', (impact_id,)).fetchone()
            if not impact or impact['status'] != 'closed':
                raise v.MihenkError('Başarısız bir kalibrasyon ancak etki değerlendirmesi '
                                    'kapandıktan sonra kapatılabilir.')
        if result == 'conditional' and not str(merged.get('usage_limit') or '').strip():
            raise v.MihenkError('Şartlı bir sonuç kapatılmadan önce yazılı bir kullanım '
                                'sınırlaması gerektirir.')
