# -*- coding: utf-8 -*-
"""Denetime hazir cikti: Excel kitabi, CSV ve yazdirilabilir HTML raporu.

PDF uretmiyoruz; bunun yerine yazdirmaya gore duzenlenmis bir HTML sayfasi
aciliyor ve tarayicidan "PDF olarak kaydet" deniyor. Kendi PDF yazicimizi
yazmak, Turkce karakter ve sayfa kirilimi tarafinda sessiz hatalar uretirdi.
"""
from __future__ import annotations

import csv
import datetime
import hashlib
import html
import pathlib
import shutil

import mihenk_core as core
import mihenk_reports as reports
import mihenk_store as store
import mihenk_validate as v
import mihenk_xlsx as xlsx
from mihenk_checklist import STATES as CHECK_STATES
from mihenk_checklist import WorkOrderChecklist
from mihenk_parts import PartRepo
from mihenk_repo import (AssetRepo, AssetTypes, CalibrationRepo, ImpactRepo, RequestRepo,
                         ScheduleRepo, WorkOrderRepo)
from mihenk_states import label as state_label
from mihenk_validate import MihenkError

MAX_CERTIFICATE_MB = 40


# ====================================================================== sertifika dosyalari
def certificates_dir() -> pathlib.Path:
    path = store.data_dir() / 'certificates'
    path.mkdir(parents=True, exist_ok=True)
    return path


def store_certificate(source, record_id) -> str:
    """Sertifika dosyasini veri klasorune kopyalar ve goreli yolunu dondurur.

    Yalnizca yol tutmak kirilgandir: dosya tasinir, disk sokulur, kayit
    bosa duser. Denetim kaniti olacak bir dosyanin kutugun yaninda durmasi
    gerekir.
    """
    source = pathlib.Path(str(source).strip('" '))
    if not source.exists() or not source.is_file():
        raise MihenkError('Sertifika dosyası bulunamadı: %s' % source)
    size_mb = source.stat().st_size / (1024 * 1024)
    if size_mb > MAX_CERTIFICATE_MB:
        raise MihenkError('Sertifika dosyası çok büyük (%.1f MB, sınır %d MB).'
                          % (size_mb, MAX_CERTIFICATE_MB))

    digest = hashlib.sha256()
    with open(source, 'rb') as handle:
        for block in iter(lambda: handle.read(65536), b''):
            digest.update(block)
    suffix = source.suffix.lower()[:10] or '.bin'
    name = 'cal-%d-%s%s' % (int(record_id), digest.hexdigest()[:12], suffix)
    target = certificates_dir() / name
    if not target.exists():
        shutil.copy2(source, target)
    return 'certificates/' + name


def certificate_path(stored) -> pathlib.Path:
    """Kayitli yolu diskteki tam yola cevirir. Eski mutlak yollar da calisir."""
    stored = str(stored or '').strip()
    if not stored:
        return pathlib.Path('')
    if stored.startswith('certificates/'):
        return store.data_dir() / stored
    return pathlib.Path(stored)


def certificate_exists(stored) -> bool:
    path = certificate_path(stored)
    return bool(str(path)) and path.exists()


# ====================================================================== tablolar
def _asset_label(conn, asset_id) -> str:
    return AssetRepo.label(conn, asset_id)


def assets_table(conn) -> dict:
    rows = []
    for row in AssetRepo.query(conn):
        plans = ScheduleRepo.query(conn, asset_id=int(row['id']), is_active=True)
        due = ''
        for plan in plans:
            when = plan['next_due_at']
            if when and (not due or when < due):
                due = when
        rows.append([
            row['code'], row['name'], AssetTypes.label(row['asset_type']),
            _asset_label(conn, int(row['parent_id'])) if int(row['parent_id']) else '',
            row['location_text'], row['manufacturer'], row['model'], row['serial_no'],
            'evet' if int(row['is_measuring_device']) else 'hayır',
            int(row['criticality']), state_label('asset', row['status']),
            v.human(row['commissioned_on']), len(plans), v.human(due),
            ImpactRepo.open_count_for_asset(conn, int(row['id'])),
        ])
    return {
        'title': 'Varlıklar',
        'headers': ['Kod', 'Ad', 'Tip', 'Üst varlık', 'Konum', 'Üretici', 'Model', 'Seri no',
                    'Ölçüm cihazı', 'Kritiklik', 'Durum', 'Devreye alma', 'Plan sayısı',
                    'Sıradaki vade', 'Açık etki'],
        'widths': [14, 28, 14, 24, 18, 16, 16, 16, 12, 9, 14, 13, 11, 14, 10],
        'rows': rows,
    }


def plans_table(conn) -> dict:
    rows = []
    for plan in ScheduleRepo.query(conn):
        if plan['basis'] == 'counter':
            interval = 'her %d birim' % int(plan['counter_interval'])
            due = 'sayaç %d' % int(plan['next_due_counter'])
        else:
            interval = '%d %s' % (int(plan['interval_value']),
                                  ScheduleRepo.UNITS.get(plan['interval_unit'], ''))
            due = v.human(plan['next_due_at'])
        rows.append([
            plan['title'], _asset_label(conn, int(plan['asset_id'])),
            ScheduleRepo.PLAN_TYPES.get(plan['plan_type'], plan['plan_type']),
            ScheduleRepo.BASES.get(plan['basis'], plan['basis']), interval,
            int(plan['lead_days']), int(plan['tolerance_days']), plan['assignee'],
            v.human(plan['last_done_at']), due,
            'evet' if int(plan['is_active']) else 'hayır',
        ])
    return {
        'title': 'Planlar',
        'headers': ['Plan', 'Varlık', 'Tip', 'Esas', 'Aralık', 'Ön uyarı (gün)',
                    'Tolerans (gün)', 'Sorumlu', 'Son yapılma', 'Sıradaki vade', 'Aktif'],
        'widths': [30, 26, 14, 10, 16, 13, 13, 16, 13, 16, 8],
        'rows': rows,
    }


def work_orders_table(conn) -> dict:
    rows = []
    for row in WorkOrderRepo.query(conn):
        progress = WorkOrderChecklist.progress(conn, int(row['id']))
        rows.append([
            int(row['id']), row['title'], _asset_label(conn, int(row['asset_id'])),
            WorkOrderRepo.TYPES.get(row['wo_type'], row['wo_type']),
            WorkOrderRepo.PRIORITIES.get(row['priority'], row['priority']),
            row['assigned_to'], state_label('work_order', row['status']),
            v.human(row['planned_start'], with_time=True),
            v.human(row['actual_start'], with_time=True),
            v.human(row['actual_end'], with_time=True),
            int(row['labor_minutes']), int(row['downtime_minutes']),
            ('%d/%d' % (progress['done'], progress['total'])) if progress['total'] else '',
            PartRepo.work_order_cost(conn, int(row['id'])),
            row['work_done'], row['root_cause'], row['closed_by'],
        ])
    return {
        'title': 'İş emirleri',
        'headers': ['#', 'Başlık', 'Varlık', 'Tip', 'Öncelik', 'Sorumlu', 'Durum',
                    'Planlanan', 'Başlangıç', 'Bitiş', 'İşçilik (dk)', 'Duruş (dk)',
                    'Kontrol listesi', 'Parça maliyeti', 'Yapılan iş', 'Kök neden', 'Kapatan'],
        'widths': [6, 30, 24, 12, 10, 16, 13, 16, 16, 16, 12, 11, 13, 13, 50, 30, 14],
        'wrap_columns': (14, 15),
        'rows': rows,
    }


def calibrations_table(conn) -> dict:
    rows = []
    for row in CalibrationRepo.query(conn):
        points = CalibrationRepo.points(row)
        worst = ''
        if row['max_deviation'] is not None:
            worst = float(row['max_deviation'])
        rows.append([
            int(row['id']), _asset_label(conn, int(row['asset_id'])),
            CalibrationRepo.RECORD_TYPES.get(row['record_type'], row['record_type']),
            v.human(row['performed_at'], with_time=True), row['performed_by'],
            row['external_body'], row['accreditation_scope'], row['certificate_no'],
            'evet' if certificate_exists(row['certificate_path']) else '',
            row['traceability_ref'], row['tolerance_spec'], row['uncertainty'],
            len(points), worst,
            CalibrationRepo.RESULTS.get(row['result'], ''),
            state_label('calibration', row['status']),
            row['usage_limit'], ('#%d' % int(row['impact_id'])) if int(row['impact_id']) else '',
            row['notes'],
        ])
    return {
        'title': 'Kalibrasyon',
        'headers': ['#', 'Varlık', 'Tip', 'Yapılma', 'Yapan', 'Dış kuruluş', 'Akreditasyon',
                    'Sertifika no', 'Dosya var', 'İzlenebilirlik', 'Tolerans', 'Belirsizlik',
                    'Nokta', 'En büyük sapma', 'Sonuç', 'Durum', 'Kullanım sınırlaması',
                    'Etki', 'Notlar'],
        'widths': [6, 24, 12, 16, 16, 20, 22, 16, 9, 28, 22, 14, 7, 13, 11, 13, 30, 8, 40],
        'wrap_columns': (16, 18),
        'rows': rows,
    }


def measurement_points_table(conn) -> dict:
    """Her olcum noktasi ayri satir: denetcinin asil baktigi tablo."""
    rows = []
    for record in CalibrationRepo.query(conn):
        for point in CalibrationRepo.points(record):
            rows.append([
                int(record['id']), _asset_label(conn, int(record['asset_id'])),
                v.human(record['performed_at'], with_time=True),
                point.get('label', ''), point.get('nominal'), point.get('measured'),
                point.get('tolerance'), point.get('unit', ''), point.get('deviation'),
                {'pass': 'Uygun', 'fail': 'Uygunsuz', 'na': 'Değerlendirilmedi'}.get(
                    point.get('verdict'), ''),
            ])
    return {
        'title': 'Ölçüm noktaları',
        'headers': ['Kayıt #', 'Varlık', 'Yapılma', 'Nokta', 'Nominal', 'Ölçülen',
                    'Tolerans', 'Birim', 'Sapma', 'Karar'],
        'widths': [8, 24, 16, 20, 11, 11, 11, 8, 11, 15],
        'rows': rows,
    }


def impacts_table(conn) -> dict:
    rows = []
    for row in ImpactRepo.query(conn):
        rows.append([
            int(row['id']), _asset_label(conn, int(row['asset_id'])),
            ('#%d' % int(row['calibration_id'])) if int(row['calibration_id']) else '',
            v.human(row['opened_at'], with_time=True), row['opened_by'],
            v.human(row['affected_from'], with_time=True),
            v.human(row['affected_to'], with_time=True),
            row['affected_scope'], row['evaluation'],
            ImpactRepo.DECISIONS.get(row['decision'], ''), row['corrective_action'],
            state_label('impact', row['status']), row['closed_by'],
            v.human(row['closed_at'], with_time=True),
        ])
    return {
        'title': 'Etki değerlendirmeleri',
        'headers': ['#', 'Varlık', 'Kaynak kayıt', 'Açılma', 'Açan', 'Etkilenen başlangıç',
                    'Etkilenen bitiş', 'Kapsam', 'Değerlendirme', 'Karar', 'Düzeltici faaliyet',
                    'Durum', 'Kapatan', 'Kapanma'],
        'widths': [6, 24, 12, 16, 14, 18, 18, 40, 50, 22, 40, 10, 14, 16],
        'wrap_columns': (7, 8, 10),
        'rows': rows,
    }


def requests_table(conn) -> dict:
    rows = []
    for row in RequestRepo.query(conn):
        rows.append([
            int(row['id']), v.human(row['reported_at'], with_time=True), row['reported_by'],
            _asset_label(conn, int(row['asset_id'])), row['summary'], row['description'],
            RequestRepo.SEVERITIES.get(row['severity'], row['severity']),
            state_label('request', row['status']), row['rejection_reason'],
            ('#%d' % int(row['work_order_id'])) if int(row['work_order_id']) else '',
        ])
    return {
        'title': 'Talepler',
        'headers': ['#', 'Bildirim', 'Bildiren', 'Varlık', 'Özet', 'Açıklama', 'Önem',
                    'Durum', 'Ret gerekçesi', 'İş emri'],
        'widths': [6, 16, 14, 24, 34, 44, 14, 13, 30, 9],
        'wrap_columns': (5, 8),
        'rows': rows,
    }


def checklists_table(conn) -> dict:
    """Is emri kontrol listesi kayitlari: isin nasil yapildiginin kaniti."""
    rows = []
    for work_order in WorkOrderRepo.query(conn):
        for item in WorkOrderChecklist.items(conn, int(work_order['id'])):
            rows.append([
                int(work_order['id']), work_order['title'],
                _asset_label(conn, int(work_order['asset_id'])),
                int(item['position']), item['text'],
                'evet' if int(item['is_critical']) else '',
                CHECK_STATES.get(item['state'], item['state']),
                item['value'], item['unit'], item['note'], item['checked_by'],
                v.human(item['checked_at'], with_time=True),
            ])
    return {
        'title': 'Kontrol listeleri',
        'headers': ['İş emri', 'Başlık', 'Varlık', 'Sıra', 'Adım', 'Kritik', 'Durum',
                    'Değer', 'Birim', 'Not', 'İşaretleyen', 'Zaman'],
        'widths': [9, 26, 22, 6, 44, 8, 13, 12, 8, 30, 14, 16],
        'wrap_columns': (4, 9),
        'rows': rows,
    }


def parts_table(conn) -> dict:
    rows = []
    for row in PartRepo.query(conn, active_only=False):
        rows.append([
            row['code'], row['name'], row['unit'], float(row['stock']), float(row['min_stock']),
            'evet' if float(row['min_stock']) > 0 and float(row['stock']) <= float(row['min_stock'])
            else '',
            row['location_text'], row['supplier'], float(row['unit_cost']),
            round(float(row['stock']) * float(row['unit_cost']), 2),
            'evet' if int(row['is_active']) else 'hayır', row['notes'],
        ])
    return {
        'title': 'Yedek parçalar',
        'headers': ['Kod', 'Ad', 'Birim', 'Stok', 'Asgari', 'Düşük stok', 'Konum', 'Tedarikçi',
                    'Birim maliyet', 'Stok değeri', 'Aktif', 'Notlar'],
        'widths': [14, 30, 9, 10, 10, 11, 18, 20, 13, 12, 8, 30],
        'wrap_columns': (11,),
        'rows': rows,
    }


def part_movements_table(conn) -> dict:
    rows = []
    for row in PartRepo.movements(conn, limit=100000):
        part = PartRepo.get(conn, int(row['part_id']))
        rows.append([
            v.human(row['created_at'], with_time=True),
            part['code'] if part else '', part['name'] if part else '',
            float(row['delta']), float(row['balance']), PartRepo.reason_text(row),
            ('#%d' % int(row['work_order_id'])) if int(row['work_order_id']) else '',
            row['actor'],
        ])
    return {
        'title': 'Stok hareketleri',
        'headers': ['Zaman', 'Parça kodu', 'Parça', 'Değişim', 'Bakiye', 'Gerekçe',
                    'İş emri', 'Kullanıcı'],
        'widths': [16, 14, 28, 10, 10, 26, 9, 16],
        'rows': rows,
    }


def audit_log_table(conn) -> dict:
    import mihenk_audit as audit
    rows = []
    for row in audit.recent(conn, limit=100000, results_only=False):
        rows.append([
            v.human(row['created_at'], with_time=True), row['entity_type'], int(row['entity_id']),
            row['action'], row['phase'], row['from_state'], row['to_state'], row['actor'],
            row['payload'],
        ])
    return {
        'title': 'Denetim günlüğü',
        'headers': ['Zaman', 'Kayıt tipi', 'Kayıt #', 'İşlem', 'Aşama', 'Önceki durum',
                    'Yeni durum', 'Kullanıcı', 'Ayrıntı'],
        'widths': [16, 13, 9, 18, 8, 14, 14, 16, 50],
        'wrap_columns': (8,),
        'rows': rows,
    }


def reliability_table(conn, days=365) -> dict:
    rows = []
    for item in reports.asset_reliability(conn, days):
        if not item['failures']:
            continue
        rows.append([
            item['asset']['code'], item['asset']['name'], item['failures'],
            item['mtbf_hours'] if item['mtbf_hours'] is not None else '',
            item['mttr_hours'] if item['mttr_hours'] is not None else '',
            item['downtime_minutes'],
        ])
    return {
        'title': 'Güvenilirlik',
        'headers': ['Kod', 'Varlık', 'Arıza sayısı', 'MTBF (saat)', 'MTTR (saat)', 'Duruş (dk)'],
        'widths': [14, 30, 12, 13, 13, 12],
        'rows': rows,
    }


ALL_TABLES = (
    ('assets', 'Varlıklar', assets_table),
    ('plans', 'Planlar', plans_table),
    ('requests', 'Talepler', requests_table),
    ('work_orders', 'İş emirleri', work_orders_table),
    ('checklists', 'Kontrol listeleri', checklists_table),
    ('calibrations', 'Kalibrasyon', calibrations_table),
    ('points', 'Ölçüm noktaları', measurement_points_table),
    ('impacts', 'Etki değerlendirmeleri', impacts_table),
    ('parts', 'Yedek parçalar', parts_table),
    ('movements', 'Stok hareketleri', part_movements_table),
    ('reliability', 'Güvenilirlik', reliability_table),
    ('audit', 'Denetim günlüğü', audit_log_table),
)


def build_tables(conn, keys=None, days=365) -> list:
    """Istenen tablolari uretir. keys bos ise hepsi."""
    wanted = set(keys) if keys else {key for key, _label, _fn in ALL_TABLES}
    out = []
    for key, _label, builder in ALL_TABLES:
        if key not in wanted:
            continue
        out.append(builder(conn, days) if key == 'reliability' else builder(conn))
    return out


def default_name(prefix: str, suffix: str) -> str:
    return '%s-%s%s' % (prefix, datetime.datetime.now().strftime('%Y%m%d-%H%M'), suffix)


# ====================================================================== cikti bicimleri
def to_xlsx(conn, path, keys=None, days=365) -> pathlib.Path:
    """Secilen tablolari tek bir Excel kitabina yazar."""
    return xlsx.write(path, build_tables(conn, keys, days))


def to_csv(conn, folder, keys=None, days=365) -> list:
    """Her tabloyu ayri bir CSV dosyasina yazar (Excel'in actigi bicim)."""
    folder = pathlib.Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for table in build_tables(conn, keys, days):
        name = table['title'].replace(' ', '-').replace('/', '-').lower() + '.csv'
        target = folder / name
        with open(target, 'w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.writer(handle, delimiter=';')
            writer.writerow(table['headers'])
            for row in table['rows']:
                writer.writerow(['' if cell is None else cell for cell in row])
        written.append(target)
    return written


HTML_HEAD = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<title>%(title)s</title>
<style>
 :root { --ink:#1b2027; --muted:#6b7480; --line:#d7dce2; --alert:#b3261e; --ok:#1f7a3d; }
 * { box-sizing:border-box; }
 body { font-family:"Segoe UI",system-ui,sans-serif; color:var(--ink); margin:0; padding:28px 32px;
        font-size:12px; line-height:1.5; }
 h1 { font-size:22px; margin:0 0 4px; }
 h2 { font-size:15px; margin:26px 0 8px; padding-bottom:4px; border-bottom:1px solid var(--line); }
 .meta { color:var(--muted); font-size:11px; margin-bottom:18px; }
 .cards { display:flex; flex-wrap:wrap; gap:10px; margin:14px 0 6px; }
 .card { border:1px solid var(--line); border-radius:4px; padding:10px 14px; min-width:130px; }
 .card .v { font-size:19px; font-weight:700; }
 .card .l { color:var(--muted); font-size:10px; text-transform:uppercase; letter-spacing:.3px; }
 .card.alert .v { color:var(--alert); }
 table { border-collapse:collapse; width:100%%; font-size:10.5px; }
 th { background:#eef1f5; text-align:left; font-weight:600; }
 th, td { border:1px solid var(--line); padding:4px 6px; vertical-align:top; }
 tbody tr:nth-child(even) { background:#fafbfc; }
 .alert { color:var(--alert); font-weight:600; }
 .ok { color:var(--ok); }
 .note { color:var(--muted); font-size:11px; margin:6px 0 0; }
 footer { margin-top:30px; padding-top:8px; border-top:1px solid var(--line);
          color:var(--muted); font-size:10px; }
 @media print {
   body { padding:0; font-size:10.5px; }
   h2 { page-break-after:avoid; }
   table { page-break-inside:auto; }
   tr { page-break-inside:avoid; }
   thead { display:table-header-group; }
   .noprint { display:none; }
 }
 .noprint { background:#eef1f5; border:1px solid var(--line); border-radius:4px;
            padding:8px 12px; margin-bottom:18px; font-size:11px; }
</style></head><body>
<div class="noprint">Yazdırmak ya da PDF olarak kaydetmek için Ctrl+P.</div>
<h1>%(title)s</h1>
<div class="meta">%(meta)s</div>
"""


def _cell_html(value) -> str:
    if value is None:
        return ''
    if isinstance(value, float):
        return html.escape('%g' % value)
    return html.escape(str(value)).replace('\n', '<br>')


def _table_html(table: dict, limit=4000) -> str:
    rows = table['rows'][:limit]
    parts = ['<h2>%s <span class="note">(%d satır)</span></h2>'
             % (html.escape(table['title']), len(table['rows']))]
    if not rows:
        parts.append('<p class="note">Kayıt yok.</p>')
        return ''.join(parts)
    parts.append('<table><thead><tr>')
    parts.extend('<th>%s</th>' % html.escape(str(h)) for h in table['headers'])
    parts.append('</tr></thead><tbody>')
    for row in rows:
        parts.append('<tr>')
        parts.extend('<td>%s</td>' % _cell_html(cell) for cell in row)
        parts.append('</tr>')
    parts.append('</tbody></table>')
    if len(table['rows']) > limit:
        parts.append('<p class="note">İlk %d satır gösterildi; tamamı Excel çıktısındadır.</p>'
                     % limit)
    return ''.join(parts)


def to_html(conn, path, keys=None, days=365, title='Mihenk denetim raporu') -> pathlib.Path:
    """Yazdirmaya gore duzenlenmis tek dosyalik rapor."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = reports.summary(conn, days)
    operator = store.setting('operator', '') or ''
    meta = 'Oluşturma: %s · Dönem: %s · Mihenk v%s' % (
        v.human(v.now(), with_time=True), data['period_label'], core.VERSION)
    if operator:
        meta += ' · Hazırlayan: %s' % html.escape(operator)

    cards = [
        ('Aktif varlık', data['assets_active'], False),
        ('Karantinada', data['assets_quarantined'], bool(data['assets_quarantined'])),
        ('Açık iş emri', data['work_orders_open'], False),
        ('Açık kalibrasyon', data['calibrations_open'], False),
        ('Açık etki değerlendirmesi', data['impacts_open'], bool(data['impacts_open'])),
        ('Geciken plan', data['plans_overdue'], bool(data['plans_overdue'])),
        ('Plan uyumu',
         ('%%%s' % data['compliance']['rate']) if data['compliance']['rate'] is not None else '—',
         False),
        ('Kalibrasyon uygunluğu',
         ('%%%s' % data['conformity']['rate']) if data['conformity']['rate'] is not None else '—',
         False),
        ('Düşük stok', data['parts_low'], bool(data['parts_low'])),
    ]

    body = [HTML_HEAD % {'title': html.escape(title), 'meta': meta}, '<div class="cards">']
    for label, value, alert in cards:
        body.append('<div class="card%s"><div class="v">%s</div><div class="l">%s</div></div>'
                    % (' alert' if alert else '', html.escape(str(value)), html.escape(label)))
    body.append('</div>')

    compliance = data['compliance']
    body.append('<p class="note">Plan uyumu: %d iş emrinden %d tanesi zamanında kapandı, '
                '%d tanesi geç kaldı. Kalibrasyon: %d kayıttan %d uygun, %d şartlı, '
                '%d uygunsuz.</p>'
                % (compliance['total'], compliance['on_time'], compliance['late'],
                   data['conformity']['total'], data['conformity']['counts']['pass'],
                   data['conformity']['counts']['conditional'],
                   data['conformity']['counts']['fail']))

    for table in build_tables(conn, keys, days):
        body.append(_table_html(table))

    body.append('<footer>Mihenk v%s · AGFO · Bu rapor %s tarihinde üretildi. '
                'Kayıtların tamamı uygulamanın veritabanındadır.</footer></body></html>'
                % (core.VERSION, v.human(v.now(), with_time=True)))

    path.write_text(''.join(body), encoding='utf-8')
    return path
