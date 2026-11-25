# -*- coding: utf-8 -*-
"""Birbirine bagli demo veri seti.

Her yazma gercek depolardan gecer; boylece demo yalnizca veri degil, durum
makinesini, karantina tetikleyicisini ve denetim gunlugunu de calistirir.
Butun demo varliklarinin kodu DEMO- ile baslar ve temizlik yalnizca o
varliklara baglidir.
"""
from __future__ import annotations

import datetime

import mihenk_scheduler as scheduler
import mihenk_validate as v
from mihenk_checklist import ChecklistTemplate, WorkOrderChecklist
from mihenk_parts import PartRepo
from mihenk_repo import AssetRepo, CalibrationRepo, ImpactRepo, RequestRepo, ScheduleRepo, WorkOrderRepo
from mihenk_i18n import t

PREFIX = 'DEMO-'


def when(days: int, hours: int = 0) -> str:
    """Simdiye gore kaydirilmis zaman."""
    moment = datetime.datetime.now() + datetime.timedelta(days=days, hours=hours)
    return moment.strftime(v.STAMP)


def demo_asset_ids(conn) -> list:
    rows = conn.execute("SELECT id FROM asset WHERE code LIKE ?", (PREFIX + '%',)).fetchall()
    return [int(r['id']) for r in rows]


def exists(conn) -> bool:
    if demo_asset_ids(conn):
        return True
    row = conn.execute('SELECT COUNT(*) AS c FROM part WHERE code LIKE ?',
                       (PREFIX + '%',)).fetchone()
    return int(row['c']) > 0


def seed(conn) -> dict:
    """Demo setini kurar ve ne yapildiginin ozetini dondurur."""
    if exists(conn):
        return {'ok': False, 'lines': [t('Demo verisi zaten var. Önce temizleyin.')], 'summary': {}}

    lines = []

    # ---------------------------------------------------------------- varliklar
    site = AssetRepo.create(conn, {
        'code': PREFIX + 'SITE-1', 'name': t('Demo Fabrika'), 'asset_type': 'location',
        'location_text': 'Tuzla', 'criticality': 1, 'attr': {'site_code': 'TZL'}})
    line = AssetRepo.create(conn, {
        'code': PREFIX + 'LINE-1', 'name': t('Dolum Hattı 1'), 'asset_type': 'line', 'parent_id': site,
        'criticality': 3, 'commissioned_on': '2019-04-01',
        'attr': {'throughput': t('9000 şişe/saat')}})
    filler = AssetRepo.create(conn, {
        'code': PREFIX + 'MCH-01', 'name': t('Döner dolum makinesi'), 'asset_type': 'machine',
        'parent_id': line, 'manufacturer': 'Krones', 'model': 'Modulfill 24',
        'serial_no': 'KR-2019-0442', 'location_text': t('A Holü'), 'criticality': 3,
        'commissioned_on': '2019-05-12', 'counter_unit': 'hour',
        'notes': t('Üç vardiya çalışır. Sayaç her vardiya devrinde HMI ekranından okunur.'),
        'attr': {'power_kw': '18.5', 'year_built': '2019', 'food_contact': 1}})
    capper = AssetRepo.create(conn, {
        'code': PREFIX + 'MCH-02', 'name': t('Kapaklama makinesi'), 'asset_type': 'machine',
        'parent_id': line, 'manufacturer': 'Arol', 'model': 'Euro SL', 'serial_no': 'AR-2020-1180',
        'location_text': t('A Holü'), 'criticality': 2,
        'attr': {'power_kw': '4', 'year_built': '2020', 'food_contact': 1}})
    valves = AssetRepo.create(conn, {
        'code': PREFIX + 'CMP-01', 'name': t('Dolum valf seti'), 'asset_type': 'component',
        'parent_id': filler, 'criticality': 2, 'attr': {'part_no': 'MF-VLV-24'}})
    probe = AssetRepo.create(conn, {
        'code': PREFIX + 'THM-01', 'name': t('Pastörizatör probu'), 'asset_type': 'measuring_device',
        'parent_id': line, 'manufacturer': 'Testo', 'model': '735-2', 'serial_no': 'TS-7788',
        'location_text': t('Pastörizatör çıkışı'), 'criticality': 3,
        'notes': t('CCP izleme cihazı.'),
        'attr': {'measuring_range': t('-50 ile 300 C'), 'resolution': '0.1 C',
                 'accuracy_class': t('A sınıfı'), 'reference_standard': t('ISO/IEC 17025 kalibreli referans')}})
    scale = AssetRepo.create(conn, {
        'code': PREFIX + 'SCL-01', 'name': t('Kontrol terazisi'), 'asset_type': 'measuring_device',
        'parent_id': line, 'manufacturer': 'Mettler Toledo', 'model': 'C33', 'serial_no': 'MT-4410',
        'location_text': t('Hat sonu'), 'criticality': 2,
        'attr': {'measuring_range': t('0 ile 3000 g'), 'resolution': '0.5 g', 'accuracy_class': 'XIII'}})
    reference = AssetRepo.create(conn, {
        'code': PREFIX + 'THM-02', 'name': t('Referans termometre'), 'asset_type': 'measuring_device',
        'parent_id': site, 'manufacturer': 'Fluke', 'model': '1524', 'serial_no': 'FL-9021',
        'criticality': 3,
        'attr': {'measuring_range': t('-200 ile 660 C'), 'resolution': '0.001 C',
                 'accuracy_class': t('Referans')}})
    lines.append(t('8 varlık, dört seviyeli hiyerarşi, üçü ölçüm cihazı.'))

    # ---------------------------------------------------------------- planlar
    plan_pm = ScheduleRepo.create(conn, {
        'asset_id': filler, 'plan_type': 'pm', 'title': t('Aylık yağlama ve conta kontrolü'),
        'basis': 'time', 'interval_value': 1, 'interval_unit': 'month', 'lead_days': 7,
        'tolerance_days': 2, 'assignee': t('Bakım ekibi'), 'is_active': 1,
        'instructions': t('1. Enerjiyi kes ve etiketle.\n2. Ana yatağı gresle.\n'
                        '3. Valf contalarını aşınmaya karşı incele.\n4. Sızıntı varsa kaydet.'),
        'last_done_at': when(-40), 'next_due_at': when(-10)})
    ScheduleRepo.create(conn, {
        'asset_id': filler, 'plan_type': 'pm', 'title': t('Her 500 çalışma saatinde valf revizyonu'),
        'basis': 'counter', 'counter_interval': 500, 'interval_value': 6, 'interval_unit': 'month',
        'lead_days': 0, 'assignee': t('Bakım ekibi'), 'is_active': 1,
        'instructions': t('24 dolum valfinin tamamı sökülür, temizlenir ve yeniden oturtulur.')})
    plan_probe = ScheduleRepo.create(conn, {
        'asset_id': probe, 'plan_type': 'calibration', 'title': t('Prob kalibrasyonu, altı aylık'),
        'basis': 'time', 'interval_value': 6, 'interval_unit': 'month', 'lead_days': 21,
        'is_active': 1, 'instructions': t('Referans termometreye karşı üç nokta: 0, 72 ve 90 C.'),
        'last_done_at': when(-190), 'next_due_at': when(-8)})
    plan_scale = ScheduleRepo.create(conn, {
        'asset_id': scale, 'plan_type': 'calibration', 'title': t('Kontrol terazisi kalibrasyonu, yıllık'),
        'basis': 'time', 'interval_value': 12, 'interval_unit': 'month', 'lead_days': 30,
        'is_active': 1, 'last_done_at': when(-350), 'next_due_at': when(12)})
    plan_verify = ScheduleRepo.create(conn, {
        'asset_id': reference, 'plan_type': 'verification',
        'title': t('Referans termometre aylık doğrulaması'), 'basis': 'time', 'interval_value': 1,
        'interval_unit': 'month', 'lead_days': 5, 'is_active': 1,
        'last_done_at': when(-35), 'next_due_at': when(-3)})
    ScheduleRepo.create(conn, {
        'asset_id': capper, 'plan_type': 'pm', 'title': t('Üç aylık kapaklama kafası servisi'),
        'basis': 'time', 'interval_value': 3, 'interval_unit': 'month', 'lead_days': 14,
        'is_active': 1, 'last_done_at': when(-20), 'next_due_at': when(70)})
    ScheduleRepo.create(conn, {
        'asset_id': valves, 'plan_type': 'pm',
        'title': t('Valf contası değişimi (duraklatıldı, yedek parça siparişte)'),
        'basis': 'time', 'interval_value': 12, 'interval_unit': 'month', 'is_active': 0,
        'next_due_at': when(-60)})
    ChecklistTemplate.save(conn, plan_pm, [
        {'text': t('Enerjiyi kes ve etiketle (LOTO)'), 'is_critical': 1},
        {'text': t('Ana yatak sıcaklığını ölç'), 'needs_value': 1, 'unit': 'C'},
        {'text': t('Ana yatağı gresle'), 'is_critical': 1},
        {'text': t('Valf contalarını aşınmaya karşı incele')},
        {'text': t('Sızıntı testi yap ve sonucu yaz'), 'needs_value': 1, 'unit': t('ml/dk')},
        {'text': t('Koruyucu kapakları yerine tak'), 'is_critical': 1},
    ])
    ChecklistTemplate.save(conn, plan_probe, [
        {'text': t('Referans termometreyi dengeye getir'), 'is_critical': 1},
        {'text': t('Buz noktası ölçümü'), 'needs_value': 1, 'unit': 'C', 'is_critical': 1},
        {'text': t('Pastörizasyon noktası ölçümü'), 'needs_value': 1, 'unit': 'C', 'is_critical': 1},
        {'text': t('Sertifikayı tara ve kayda ekle')},
    ])
    lines.append(t('7 plan: biri gecikmiş, biri sayaç tabanlı, biri yaklaşan, biri uzak, biri '
                 'duraklatılmış. İkisinde kontrol listesi şablonu var.'))

    # ---------------------------------------------------------------- talepler
    RequestRepo.create(conn, {
        'asset_id': capper, 'summary': t('Kapaklama her beşinci şişede gevşek kapak bırakıyor'),
        'description': t('Gece vardiyasında başladı. 3 numaralı kafada tork tutarsız görünüyor.'),
        'severity': 'high'})

    triaged = RequestRepo.create(conn, {
        'asset_id': filler, 'summary': t('CIP sonrası dolum altında ürün damlıyor'),
        'description': t('Her sabah yerde küçük birikinti. Valf contasından şüpheleniliyor.'),
        'severity': 'normal'})
    RequestRepo.transition(conn, triaged, 'triaged')

    rejected = RequestRepo.create(conn, {
        'asset_id': capper, 'summary': t('Makine çok gürültülü'),
        'description': t('Operatör yorumu, ölçüm eklenmemiş.'), 'severity': 'low'})
    RequestRepo.transition(conn, rejected, 'triaged')
    RequestRepo.transition(conn, rejected, 'rejected', {
        'rejection_reason': t('Gürültü 78 dB ölçüldü, sınır içinde. Bakım işlemi gerekmiyor.')})

    converted = RequestRepo.create(conn, {
        'asset_id': filler, 'summary': t('Giriş yıldız tekerinde şişe sıkışması'),
        'description': t('Bir vardiyada üç sıkışma. Kılavuz ray ayarı kaçmış olabilir.'),
        'severity': 'stops_production'})
    RequestRepo.transition(conn, converted, 'triaged')
    wo_from_request = RequestRepo.convert(conn, converted, {'assigned_to': t('Bakım ekibi')})
    lines.append(t('4 talep: açık, değerlendirilmiş, reddedilmiş ve dönüştürülmüş.'))

    # ---------------------------------------------------------------- is emirleri
    WorkOrderRepo.transition(conn, wo_from_request, 'assigned', {'assigned_to': t('Bakım ekibi')})
    WorkOrderRepo.transition(conn, wo_from_request, 'in_progress', {'actual_start': when(0, -3)})

    wo_hold = WorkOrderRepo.create(conn, {
        'asset_id': capper, 'wo_type': 'corrective', 'title': t('3 numaralı tork kafasını değiştir'),
        'priority': 'high', 'assigned_to': t('Bakım ekibi'),
        'planned_start': when(-2), 'planned_end': when(-1)})
    WorkOrderRepo.transition(conn, wo_hold, 'assigned', {'assigned_to': t('Bakım ekibi')})
    WorkOrderRepo.transition(conn, wo_hold, 'on_hold',
                             {'hold_reason': t('Yedek tork kafası siparişte, tahmini teslim iki hafta.')})

    wo_closed = WorkOrderRepo.create(conn, {
        'asset_id': filler, 'schedule_id': plan_pm, 'wo_type': 'preventive',
        'title': t('Aylık yağlama ve conta kontrolü (önceki çevrim)'), 'priority': 'normal',
        'assigned_to': t('Bakım ekibi'), 'planned_start': when(-41), 'planned_end': when(-41)})
    WorkOrderRepo.transition(conn, wo_closed, 'assigned', {'assigned_to': t('Bakım ekibi')})
    WorkOrderRepo.transition(conn, wo_closed, 'in_progress', {'actual_start': when(-40, -4)})
    WorkOrderChecklist.copy_from_plan(conn, wo_closed, plan_pm)
    # Anahtarlar kontrol listesine yazilan metinle eslesmeli; o metin de
    # cevriliyor, bu yuzden anahtarlar da t() ile kuruluyor.
    values = {t('Ana yatak sıcaklığını ölç'): '52',
              t('Sızıntı testi yap ve sonucu yaz'): '0'}
    for item in WorkOrderChecklist.items(conn, wo_closed):
        WorkOrderChecklist.set_state(conn, item['id'], 'ok', values.get(item['text'], ''))
    WorkOrderRepo.transition(conn, wo_closed, 'completed', {
        'work_done': t('Ana yatak greslendi. İki valf contasında aşınma görüldü ve değiştirildi. '
                     'Test çalışmasında sızıntı yok.'),
        'root_cause': t('Normal aşınma.'), 'actual_end': when(-40, -1),
        'labor_minutes': 180, 'downtime_minutes': 210})
    WorkOrderRepo.transition(conn, wo_closed, 'closed')
    # Tamamlanma plani ileri sardi; demo gecikmis plani gostermek istiyor, geri al.
    conn.execute('UPDATE schedule SET last_done_at = ?, next_due_at = ? WHERE id = ?',
                 (when(-40), when(-10), plan_pm))
    lines.append(t('İş emirleri sürüyor, beklemede ve kapalı durumlarında bırakıldı; '
                 'kapalı olan plana bağlı, bu yüzden plan uyumu hesaplanabiliyor.'))

    # ---------------------------------------------------------------- kalibrasyon
    cal_scale = CalibrationRepo.create(conn, {
        'asset_id': scale, 'schedule_id': plan_scale, 'record_type': 'calibration',
        'tolerance_spec': t('Çalışma aralığı boyunca ±1.5 g')})
    CalibrationRepo.save_result(conn, cal_scale, {
        'performed_at': when(-350), 'external_body': t('Mettler Toledo Servis'),
        'accreditation_scope': t('TS EN ISO/IEC 17025, kütle'),
        'certificate_no': 'MT-CAL-2025-7741',
        'traceability_ref': t('E2 sınıfı ağırlıklar, sertifika UME-2024-0912'),
        'tolerance_spec': t('Çalışma aralığı boyunca ±1.5 g'), 'uncertainty': '±0.4 g (k=2)',
        'notes': t('Hat durdurularak yerinde kalibre edildi.'),
        'points': [
            {'label': t('Sıfır'), 'nominal': 0, 'measured': 0.2, 'tolerance': 1.5, 'unit': 'g'},
            {'label': t('Yarım yük'), 'nominal': 500, 'measured': 500.6, 'tolerance': 1.5, 'unit': 'g'},
            {'label': t('Tam yük'), 'nominal': 1000, 'measured': 999.1, 'tolerance': 1.5, 'unit': 'g'},
        ]})
    CalibrationRepo.transition(conn, cal_scale, 'closed')

    cal_probe_old = CalibrationRepo.create(conn, {
        'asset_id': probe, 'schedule_id': plan_probe, 'record_type': 'calibration',
        'tolerance_spec': t('0, 72 ve 90 C noktalarında ±0.5 C')})
    CalibrationRepo.save_result(conn, cal_probe_old, {
        'performed_at': when(-190), 'certificate_no': 'INT-CAL-2026-0031',
        'traceability_ref': t('Referans termometre %sTHM-02, sertifika FL-2026-0004') % PREFIX,
        'tolerance_spec': t('0, 72 ve 90 C noktalarında ±0.5 C'), 'uncertainty': '±0.12 C (k=2)',
        'notes': t('Uygunluğu gerçekten kanıtlayan son sonuç. Etki aralığı buradan başlar.'),
        'points': [
            {'label': t('Buz noktası'), 'nominal': 0, 'measured': 0.1, 'tolerance': 0.5, 'unit': 'C'},
            {'label': t('Pastörizasyon'), 'nominal': 72, 'measured': 72.2, 'tolerance': 0.5, 'unit': 'C'},
            {'label': t('Üst nokta'), 'nominal': 90, 'measured': 89.8, 'tolerance': 0.5, 'unit': 'C'},
        ]})
    CalibrationRepo.transition(conn, cal_probe_old, 'closed')

    cal_probe_fail = CalibrationRepo.create(conn, {
        'asset_id': probe, 'schedule_id': plan_probe, 'record_type': 'calibration',
        'tolerance_spec': t('0, 72 ve 90 C noktalarında ±0.5 C')})
    CalibrationRepo.save_result(conn, cal_probe_fail, {
        'performed_at': when(-1), 'certificate_no': 'INT-CAL-2026-0198',
        'traceability_ref': t('Referans termometre %sTHM-02, sertifika FL-2026-0004') % PREFIX,
        'tolerance_spec': t('0, 72 ve 90 C noktalarında ±0.5 C'), 'uncertainty': '±0.12 C (k=2)',
        'notes': t('Prob pastörizasyon noktasında düşük okuyor. Rutin doğrulamada fark edildi.'),
        'points': [
            {'label': t('Buz noktası'), 'nominal': 0, 'measured': 0.3, 'tolerance': 0.5, 'unit': 'C'},
            {'label': t('Pastörizasyon'), 'nominal': 72, 'measured': 70.4, 'tolerance': 0.5, 'unit': 'C'},
            {'label': t('Üst nokta'), 'nominal': 90, 'measured': 88.9, 'tolerance': 0.5, 'unit': 'C'},
        ]})

    cal_reference = CalibrationRepo.create(conn, {
        'asset_id': reference, 'schedule_id': plan_verify, 'record_type': 'verification',
        'tolerance_spec': t('Buz noktasında ±0.05 C')})
    CalibrationRepo.save_result(conn, cal_reference, {
        'performed_at': when(-2), 'result': 'conditional',
        'tolerance_spec': t('Buz noktasında ±0.05 C'), 'uncertainty': '±0.02 C (k=2)',
        'notes': t('Kapatma korumasını göstermek için kullanım sınırlaması bilerek boş bırakıldı.'),
        'points': [{'label': t('Buz noktası'), 'nominal': 0, 'measured': 0.04,
                    'tolerance': 0.05, 'unit': 'C'}]})
    lines.append(t('Kalibrasyon: biri kapalı uygun, biri şartlı, biri uygunsuz '
                 '(%sTHM-01 karantinaya alındı, etki değerlendirmesi açık).') % PREFIX)

    # ---------------------------------------------------------------- yedek parcalar
    seal = PartRepo.create(conn, {
        'code': PREFIX + 'PRT-001', 'name': t('Dolum valfi contası (EPDM)'), 'unit': 'adet',
        'stock': 24, 'min_stock': 8, 'location_text': t('Depo A / Raf 3'),
        'supplier': t('Krones Yedek Parça'), 'unit_cost': 185, 'is_active': 1,
        'notes': t('Gıdaya temas eder; FDA 21 CFR 177.2600 belgesi dosyada.')})
    bearing = PartRepo.create(conn, {
        'code': PREFIX + 'PRT-002', 'name': t('Ana yatak rulmanı 6208-2RS'), 'unit': 'adet',
        'stock': 2, 'min_stock': 4, 'location_text': t('Depo A / Raf 1'),
        'supplier': t('SKF Türkiye'), 'unit_cost': 740, 'is_active': 1,
        'notes': t('Asgarinin altında bırakıldı: düşük stok uyarısı burada görülür.')})
    PartRepo.create(conn, {
        'code': PREFIX + 'PRT-003', 'name': t('Gıda sınıfı gres (1 kg)'), 'unit': 'kg',
        'stock': 9, 'min_stock': 3, 'location_text': t('Depo B'), 'supplier': t('Klüber'),
        'unit_cost': 420, 'is_active': 1, 'notes': t('NSF H1 sınıfı.')})
    PartRepo.create(conn, {
        'code': PREFIX + 'PRT-004', 'name': t('Tork kafası yayı'), 'unit': 'adet',
        'stock': 0, 'min_stock': 2, 'location_text': t('Depo A / Raf 2'), 'supplier': 'Arol',
        'unit_cost': 1250, 'is_active': 1, 'notes': t('Siparişte; bekleyen iş emrinin sebebi.')})

    PartRepo.consume(conn, seal, 2, wo_closed, t('Aşınmış iki conta değiştirildi'))
    PartRepo.move(conn, bearing, 2, 'receive', note=t('Satın alma girişi'))
    lines.append(t('4 yedek parça kütüğe girdi; biri asgarinin altında, biri tükenmiş durumda.'))

    # ---------------------------------------------------------------- sayac ve tarama
    AssetRepo.record_counter(conn, filler, 260)
    AssetRepo.record_counter(conn, filler, 540)

    summary = scheduler.scan(conn)
    lines.append(t('Tarama: %d iş emri, %d kalibrasyon kaydı üretildi, %d plan atlandı.')
                 % (summary['work_orders'], summary['calibrations'], summary['skipped']))
    lines.append(t('Şimdi deneyin: %sTHM-01 varlığını aktife almaya ve uygunsuz kaydını kapatmaya '
                 'çalışın. Etki değerlendirmesi kapanana kadar ikisi de reddedilmeli.') % PREFIX)

    return {'ok': True, 'lines': lines, 'summary': summary,
            'plan_pm': plan_pm, 'probe': probe, 'calibration_fail': cal_probe_fail,
            'reference_record': cal_reference, 'closed_work_order': wo_closed,
            'part_seal': seal, 'part_bearing': bearing}


def purge(conn) -> dict:
    """Yalnizca DEMO- varliklarini ve onlara bagli her seyi siler."""
    ids = demo_asset_ids(conn)
    if not ids:
        if not exists(conn):
            return {'ok': False, 'lines': [t('Silinecek demo verisi yok.')]}
        ids = [0]          # yalnizca demo parcalar kalmis olabilir

    marks = ', '.join('?' * len(ids))
    removed = {}
    log_targets = {'asset': list(ids)}

    # Once varliga bagli kayitlarin kimliklerini topla: kontrol listesi ve stok
    # hareketleri bunlara asili.
    plan_ids = [int(r['id']) for r in
                conn.execute('SELECT id FROM schedule WHERE asset_id IN (%s)' % marks, ids)]
    wo_ids = [int(r['id']) for r in
              conn.execute('SELECT id FROM work_order WHERE asset_id IN (%s)' % marks, ids)]
    if plan_ids:
        sub = ', '.join('?' * len(plan_ids))
        removed['checklist_item'] = conn.execute(
            'DELETE FROM checklist_item WHERE schedule_id IN (%s)' % sub, plan_ids).rowcount
    if wo_ids:
        sub = ', '.join('?' * len(wo_ids))
        removed['work_order_check'] = conn.execute(
            'DELETE FROM work_order_check WHERE work_order_id IN (%s)' % sub, wo_ids).rowcount
        removed['part_movement'] = conn.execute(
            'DELETE FROM part_movement WHERE work_order_id IN (%s)' % sub, wo_ids).rowcount

    # Demo parcalar da DEMO- onekiyle yazildi; once hareketleri, sonra kendileri.
    part_ids = [int(r['id']) for r in
                conn.execute('SELECT id FROM part WHERE code LIKE ?', (PREFIX + '%',))]
    if part_ids:
        sub = ', '.join('?' * len(part_ids))
        removed['part_movement'] = (removed.get('part_movement', 0) + conn.execute(
            'DELETE FROM part_movement WHERE part_id IN (%s)' % sub, part_ids).rowcount)
        log_targets['part'] = part_ids
        removed['part'] = conn.execute('DELETE FROM part WHERE id IN (%s)' % sub,
                                       part_ids).rowcount

    for table in ('schedule', 'request', 'work_order', 'calibration', 'impact'):
        rows = conn.execute('SELECT id FROM %s WHERE asset_id IN (%s)' % (table, marks), ids).fetchall()
        log_targets[table] = [int(r['id']) for r in rows]
        cur = conn.execute('DELETE FROM %s WHERE asset_id IN (%s)' % (table, marks), ids)
        removed[table] = cur.rowcount

    log_rows = 0
    for entity, entity_ids in log_targets.items():
        if not entity_ids:
            continue
        sub = ', '.join('?' * len(entity_ids))
        cur = conn.execute('DELETE FROM log WHERE entity_type = ? AND entity_id IN (%s)' % sub,
                           [entity] + entity_ids)
        log_rows += cur.rowcount

    cur = conn.execute('DELETE FROM asset_attr WHERE asset_id IN (%s)' % marks, ids)
    removed['asset_attr'] = cur.rowcount
    cur = conn.execute('DELETE FROM asset WHERE id IN (%s)' % marks, ids)
    removed['asset'] = cur.rowcount
    removed['log'] = log_rows

    lines = [t('%s: %d satır silindi') % (name, count) for name, count in sorted(removed.items())]
    return {'ok': True, 'lines': lines, 'removed': removed}
