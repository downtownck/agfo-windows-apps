# -*- coding: utf-8 -*-
"""AGFO Mihenk - cekirdek testleri (arayuz, ag ve Windows gerektirmez).

    python -I tests/test_core.py <mihenk klasoru>

Her test kendi gecici veritabaniyla calisir; makinede kurulu Mihenk verisine
dokunmaz.
"""
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))
os.environ['MIHENK_DATA_DIR'] = tempfile.mkdtemp()
os.environ.setdefault('APPDATA', tempfile.mkdtemp())
os.environ.setdefault('LOCALAPPDATA', tempfile.mkdtemp())

import mihenk_audit as audit  # noqa: E402
import mihenk_core as core  # noqa: E402
import mihenk_db as db  # noqa: E402
import mihenk_scheduler as scheduler  # noqa: E402
import mihenk_seed as seed  # noqa: E402
import mihenk_states as states  # noqa: E402
import mihenk_store as store  # noqa: E402
import mihenk_validate as v  # noqa: E402
from mihenk_repo import (AssetRepo, AssetTypes, CalibrationRepo, ImpactRepo,  # noqa: E402
                         RequestRepo, ScheduleRepo, WorkOrderRepo)

PASSED = []


def test(fn):
    fn()
    PASSED.append(fn.__name__)
    return fn


def fresh():
    """Bos bir veritabani acar."""
    path = pathlib.Path(tempfile.mkdtemp()) / 'mihenk.sqlite3'
    return db.connect(path)


def refuses(fn, needle=''):
    """Cagrinin MihenkError ile reddedildigini dogrular ve mesaji dondurur."""
    try:
        fn()
    except v.MihenkError as exc:
        text = str(exc)
        assert needle in text, 'beklenen mesaj yok: %r icinde %r' % (text, needle)
        return text
    raise AssertionError('reddedilmesi gerekirdi, kabul edildi')


def make_asset(conn, code='MCH-1', **extra):
    data = {'code': code, 'name': 'Test makinesi', 'asset_type': 'machine'}
    data.update(extra)
    return AssetRepo.create(conn, data)


def make_device(conn, code='THM-1'):
    return AssetRepo.create(conn, {'code': code, 'name': 'Test probu',
                                   'asset_type': 'measuring_device', 'commissioned_on': '2020-01-01'})


# ====================================================================== sema
@test
def schema_installs_all_tables():
    conn = fresh()
    status = db.table_status(conn)
    assert len(status) == 8, status
    assert all(status.values()), status
    assert db.table('asset') == 'asset'
    assert db.table('drop_me') == ''
    counts = db.counts(conn)
    assert set(counts) == set(db.TABLES) and max(counts.values()) == 0, counts


@test
def install_is_idempotent():
    conn = fresh()
    make_asset(conn)
    db.install(conn)
    db.install(conn)
    assert AssetRepo.count(conn) == 1


# ====================================================================== tarih ve olcum
@test
def interval_math_handles_month_ends():
    assert v.add_interval('2026-01-31 08:00:00', 1, 'month').startswith('2026-02-28')
    assert v.add_interval('2026-01-31 08:00:00', 1, 'year').startswith('2027-01-31')
    assert v.add_interval('2026-12-15 08:00:00', 1, 'month').startswith('2027-01-15')
    assert v.add_interval('2026-03-01 08:00:00', 2, 'week').startswith('2026-03-15')
    assert v.add_interval('2024-01-31 00:00:00', 1, 'month').startswith('2024-02-29')  # artik yil


@test
def date_parsing_accepts_the_formats_people_type():
    for text in ('2026-11-25', '2026-11-25 09:30', '25.11.2026 09:30', '2026-11-25T09:30'):
        assert v.parse(text) is not None, text
    assert v.parse('') is None and v.parse('yarin') is None
    assert v.stamp('25.11.2026') == '2026-11-25 00:00:00'
    assert v.human('2026-11-25 09:30:00', with_time=True) == '2026-11-25 09:30'


@test
def tolerance_evaluation_needs_a_tolerance():
    points = v.measurement_points([
        {'label': 'Sifir', 'nominal': 0, 'measured': 0.2, 'tolerance': 1.5},
        {'label': 'Tam', 'nominal': 1000, 'measured': 999.1, 'tolerance': 1.5},
    ])
    assert v.evaluate_points(points)['verdict'] == 'pass'
    assert abs(v.evaluate_points(points)['max_deviation'] - 0.9) < 1e-9

    out_of_range = v.measurement_points([{'nominal': 72, 'measured': 70.4, 'tolerance': 0.5}])
    assert out_of_range[0]['verdict'] == 'fail'
    assert v.evaluate_points(out_of_range)['verdict'] == 'fail'

    no_tolerance = v.measurement_points([{'label': 'Olcum', 'nominal': 10, 'measured': 10.1}])
    assert no_tolerance[0]['verdict'] == 'na'
    assert v.evaluate_points(no_tolerance)['verdict'] == 'unknown', 'toleranssiz nokta uygunluk kanitlayamaz'


# ====================================================================== varlik
@test
def asset_create_and_guards():
    conn = fresh()
    parent = make_asset(conn, 'LINE-1', asset_type='line')
    child = make_asset(conn, 'MCH-1', parent_id=parent)

    refuses(lambda: make_asset(conn, 'MCH-1'), 'başka bir varlık')
    refuses(lambda: AssetRepo.create(conn, {'code': 'X', 'name': ''}), 'Varlık adı')
    refuses(lambda: AssetRepo.create(conn, {'code': '', 'name': 'Y'}), 'Varlık kodu')

    refuses(lambda: AssetRepo.update(conn, parent, {'code': 'LINE-1', 'name': 'Hat',
                                                    'parent_id': child}), 'döngü')
    refuses(lambda: AssetRepo.update(conn, child, {'code': 'MCH-1', 'name': 'M',
                                                   'parent_id': child}), 'kendi üst varlığı')

    assert AssetRepo.descendant_ids(conn, parent) == [child]
    assert [r['id'] for r in AssetRepo.ancestors(conn, child)] == [parent]
    assert AssetRepo.label(conn, child) == 'MCH-1 - Test makinesi'
    assert child not in [i for i, _ in AssetRepo.options(conn, exclude=child)]


@test
def measuring_type_forces_the_measuring_flag():
    conn = fresh()
    device = make_device(conn)
    assert AssetRepo.get(conn, device)['is_measuring_device'] == 1
    assert AssetTypes.is_measuring('measuring_device')


@test
def type_attributes_are_stored_per_type():
    conn = fresh()
    asset = AssetRepo.create(conn, {'code': 'M-9', 'name': 'Makine', 'asset_type': 'machine',
                                    'attr': {'power_kw': '18.5', 'food_contact': 1,
                                             'year_built': '2019'}})
    attrs = AssetRepo.attributes(conn, asset)
    assert attrs['power_kw'] == '18.5' and attrs['food_contact'] == '1'
    assert 'measuring_range' not in attrs, 'baska tipin alani yazilmamali'


@test
def asset_with_history_cannot_be_deleted():
    conn = fresh()
    asset = make_asset(conn)
    plain = make_asset(conn, 'MCH-2')
    AssetRepo.delete(conn, plain)
    assert AssetRepo.get(conn, plain) is None

    ScheduleRepo.create(conn, {'asset_id': asset, 'plan_type': 'pm', 'title': 'Plan', 'is_active': 1})
    refuses(lambda: AssetRepo.delete(conn, asset), 'bakım geçmişi')

    parent = make_asset(conn, 'P-1', asset_type='line')
    make_asset(conn, 'C-1', parent_id=parent)
    refuses(lambda: AssetRepo.delete(conn, parent), 'alt varlık')


@test
def counter_readings_never_go_backwards():
    conn = fresh()
    asset = make_asset(conn, 'MCH-C', counter_unit='hour')
    AssetRepo.record_counter(conn, asset, 100)
    refuses(lambda: AssetRepo.record_counter(conn, asset, 50), 'düşük olamaz')
    assert int(AssetRepo.get(conn, asset)['counter_value']) == 100

    plain = make_asset(conn, 'MCH-NC')
    refuses(lambda: AssetRepo.record_counter(conn, plain, 5), 'sayaç birimi')


# ====================================================================== plan
@test
def counter_plan_needs_a_counter_unit():
    conn = fresh()
    plain = make_asset(conn, 'MCH-P')
    refuses(lambda: ScheduleRepo.create(conn, {'asset_id': plain, 'plan_type': 'pm', 'title': 'P',
                                               'basis': 'counter', 'counter_interval': 100,
                                               'is_active': 1}), 'sayaç birimi')
    with_counter = make_asset(conn, 'MCH-Q', counter_unit='hour')
    refuses(lambda: ScheduleRepo.create(conn, {'asset_id': with_counter, 'plan_type': 'pm',
                                               'title': 'P', 'basis': 'counter',
                                               'counter_interval': 0, 'is_active': 1}), 'sayaç aralığı')
    refuses(lambda: ScheduleRepo.create(conn, {'asset_id': 0, 'plan_type': 'pm', 'title': 'P'}),
            'mevcut bir varlık')
    refuses(lambda: ScheduleRepo.create(conn, {'asset_id': with_counter, 'title': ''}), 'Plan başlığı')


@test
def plan_computes_its_own_next_due():
    conn = fresh()
    asset = make_asset(conn)
    plan_id = ScheduleRepo.create(conn, {'asset_id': asset, 'plan_type': 'pm', 'title': 'Aylik',
                                         'interval_value': 1, 'interval_unit': 'month',
                                         'is_active': 1, 'last_done_at': '2026-01-15 08:00'})
    plan = ScheduleRepo.get(conn, plan_id)
    assert plan['next_due_at'].startswith('2026-02-15'), plan['next_due_at']

    ScheduleRepo.mark_done(conn, plan_id, '2026-02-20 10:00')
    plan = ScheduleRepo.get(conn, plan_id)
    assert plan['last_done_at'].startswith('2026-02-20') and plan['next_due_at'].startswith('2026-03-20')


# ====================================================================== talep
@test
def request_must_be_triaged_before_conversion():
    conn = fresh()
    asset = make_asset(conn)
    request_id = RequestRepo.create(conn, {'asset_id': asset, 'summary': 'Ariza', 'severity': 'high'})
    refuses(lambda: RequestRepo.convert(conn, request_id), 'değerlendirin')

    RequestRepo.transition(conn, request_id, 'triaged')
    work_order_id = RequestRepo.convert(conn, request_id, {'assigned_to': 'Ekip'})
    row = RequestRepo.get(conn, request_id)
    assert row['status'] == 'converted' and int(row['work_order_id']) == work_order_id
    assert WorkOrderRepo.get(conn, work_order_id)['wo_type'] == 'corrective'

    refuses(lambda: RequestRepo.create(conn, {'asset_id': asset, 'summary': ''}), 'özet')
    refuses(lambda: RequestRepo.create(conn, {'asset_id': 0, 'summary': 'X'}), 'Mevcut bir varlık')


@test
def rejecting_a_request_needs_a_reason():
    conn = fresh()
    asset = make_asset(conn)
    request_id = RequestRepo.create(conn, {'asset_id': asset, 'summary': 'Gurultu'})
    RequestRepo.transition(conn, request_id, 'triaged')
    refuses(lambda: RequestRepo.transition(conn, request_id, 'rejected'), 'Ret gerekçesi')
    RequestRepo.transition(conn, request_id, 'rejected', {'rejection_reason': '78 dB, sinir icinde.'})
    assert RequestRepo.get(conn, request_id)['status'] == 'rejected'


# ====================================================================== is emri
@test
def work_order_lifecycle_and_plan_roll_forward():
    conn = fresh()
    asset = make_asset(conn)
    plan_id = ScheduleRepo.create(conn, {'asset_id': asset, 'plan_type': 'pm', 'title': 'Aylik bakim',
                                         'interval_value': 1, 'interval_unit': 'month', 'is_active': 1,
                                         'lead_days': 7, 'next_due_at': seed.when(-10)})
    made = scheduler.scan(conn)
    assert made['work_orders'] == 1, made
    work_order_id = WorkOrderRepo.query(conn, open_only=True)[0]['id']

    refuses(lambda: WorkOrderRepo.transition(conn, work_order_id, 'completed'), 'izin verilmiyor')
    WorkOrderRepo.transition(conn, work_order_id, 'assigned', {'assigned_to': 'Ekip'})
    WorkOrderRepo.transition(conn, work_order_id, 'in_progress')
    assert WorkOrderRepo.get(conn, work_order_id)['actual_start'], 'baslangic kendiliginden dolmali'

    refuses(lambda: WorkOrderRepo.transition(conn, work_order_id, 'completed'), 'Yapılan iş')
    refuses(lambda: WorkOrderRepo.transition(conn, work_order_id, 'completed',
                                             {'work_done': 'Yapildi'}), 'İşçilik dakikası')
    WorkOrderRepo.transition(conn, work_order_id, 'completed',
                             {'work_done': 'Greslendi.', 'labor_minutes': 90,
                              'actual_end': '2026-05-10 12:00'})
    plan = ScheduleRepo.get(conn, plan_id)
    assert plan['last_done_at'].startswith('2026-05-10'), plan['last_done_at']
    assert plan['next_due_at'].startswith('2026-06-10'), plan['next_due_at']

    WorkOrderRepo.transition(conn, work_order_id, 'closed')
    row = WorkOrderRepo.get(conn, work_order_id)
    assert row['status'] == 'closed' and row['closed_at']
    refuses(lambda: WorkOrderRepo.update(conn, work_order_id, {'title': 'Yeni'}), 'artık düzenlenemez')
    refuses(lambda: WorkOrderRepo.transition(conn, work_order_id, 'in_progress'), 'izin verilmiyor')


@test
def hold_needs_a_reason():
    conn = fresh()
    asset = make_asset(conn)
    work_order_id = WorkOrderRepo.create(conn, {'asset_id': asset, 'title': 'Is'})
    WorkOrderRepo.transition(conn, work_order_id, 'assigned')
    refuses(lambda: WorkOrderRepo.transition(conn, work_order_id, 'on_hold'), 'Bekletme gerekçesi')
    WorkOrderRepo.transition(conn, work_order_id, 'on_hold', {'hold_reason': 'Parca bekleniyor'})
    assert WorkOrderRepo.get(conn, work_order_id)['status'] == 'on_hold'


# ====================================================================== kalibrasyon
@test
def passing_calibration_closes_and_rolls_the_plan():
    conn = fresh()
    device = make_device(conn)
    plan_id = ScheduleRepo.create(conn, {'asset_id': device, 'plan_type': 'calibration',
                                         'title': 'Yillik', 'interval_value': 12,
                                         'interval_unit': 'month', 'is_active': 1,
                                         'next_due_at': seed.when(-1)})
    record_id = CalibrationRepo.create(conn, {'asset_id': device, 'schedule_id': plan_id})
    CalibrationRepo.save_result(conn, record_id, {
        'performed_at': '2026-05-01 09:00',
        'points': [{'label': 'Sifir', 'nominal': 0, 'measured': 0.1, 'tolerance': 0.5},
                   {'label': 'Ust', 'nominal': 100, 'measured': 100.2, 'tolerance': 0.5}]})
    row = CalibrationRepo.get(conn, record_id)
    assert row['result'] == 'pass' and row['status'] == 'result_entered'
    assert abs(float(row['max_deviation']) - 0.2) < 1e-9

    CalibrationRepo.transition(conn, record_id, 'closed')
    assert AssetRepo.get(conn, device)['status'] == 'active', 'uygun sonuc karantina yapmaz'
    plan = ScheduleRepo.get(conn, plan_id)
    assert plan['next_due_at'].startswith('2027-05-01'), plan['next_due_at']


@test
def failing_calibration_quarantines_and_opens_impact():
    conn = fresh()
    device = make_device(conn)

    baseline = CalibrationRepo.create(conn, {'asset_id': device})
    CalibrationRepo.save_result(conn, baseline, {
        'performed_at': '2026-01-10 09:00',
        'points': [{'nominal': 72, 'measured': 72.1, 'tolerance': 0.5}]})
    CalibrationRepo.transition(conn, baseline, 'closed')

    failing = CalibrationRepo.create(conn, {'asset_id': device})
    CalibrationRepo.save_result(conn, failing, {
        'performed_at': '2026-06-20 09:00',
        'points': [{'nominal': 72, 'measured': 70.4, 'tolerance': 0.5}]})

    row = CalibrationRepo.get(conn, failing)
    assert row['result'] == 'fail' and int(row['impact_id']) > 0
    assert AssetRepo.get(conn, device)['status'] == 'quarantined'

    impact = ImpactRepo.get(conn, int(row['impact_id']))
    assert impact['status'] == 'open'
    assert impact['affected_from'].startswith('2026-01-10'), impact['affected_from']
    assert impact['affected_to'].startswith('2026-06-20'), impact['affected_to']


@test
def impact_window_falls_back_to_commissioning():
    conn = fresh()
    device = make_device(conn, 'THM-NEW')
    failing = CalibrationRepo.create(conn, {'asset_id': device})
    CalibrationRepo.save_result(conn, failing, {
        'performed_at': '2026-06-20 09:00',
        'points': [{'nominal': 10, 'measured': 12, 'tolerance': 0.5}]})
    impact = ImpactRepo.for_calibration(conn, failing)
    assert impact['affected_from'].startswith('2020-01-01'), impact['affected_from']


@test
def quarantine_cannot_be_lifted_while_an_impact_is_open():
    conn = fresh()
    device = make_device(conn)
    failing = CalibrationRepo.create(conn, {'asset_id': device})
    CalibrationRepo.save_result(conn, failing, {
        'performed_at': '2026-06-20 09:00',
        'points': [{'nominal': 72, 'measured': 70.4, 'tolerance': 0.5}]})
    impact_id = int(CalibrationRepo.get(conn, failing)['impact_id'])

    refuses(lambda: AssetRepo.transition(conn, device, 'active'), 'hizmete dönemez')
    refuses(lambda: CalibrationRepo.transition(conn, failing, 'closed'), 'etki değerlendirmesi')

    refuses(lambda: ImpactRepo.close(conn, impact_id, {'affected_from': '2026-01-10 09:00'}), 'Karar')
    ImpactRepo.close(conn, impact_id, {
        'affected_from': '2026-01-10 09:00', 'affected_to': '2026-06-20 09:00',
        'evaluation': 'Pastorizasyon sicakligi 1.6 C dusuk olcmus olabilir.',
        'decision': 'rework', 'corrective_action': 'Prob degistirildi.'})

    AssetRepo.transition(conn, device, 'active')
    CalibrationRepo.transition(conn, failing, 'closed')
    assert AssetRepo.get(conn, device)['status'] == 'active'
    assert CalibrationRepo.get(conn, failing)['status'] == 'closed'
    refuses(lambda: ImpactRepo.save(conn, impact_id, {'evaluation': 'Yeni'}), 'artık düzenlenemez')


@test
def conditional_result_needs_a_usage_limit():
    conn = fresh()
    device = make_device(conn)
    record_id = CalibrationRepo.create(conn, {'asset_id': device})
    CalibrationRepo.save_result(conn, record_id, {
        'performed_at': '2026-06-20 09:00', 'result': 'conditional',
        'points': [{'nominal': 0, 'measured': 0.04, 'tolerance': 0.05}]})
    refuses(lambda: CalibrationRepo.transition(conn, record_id, 'closed'), 'kullanım sınırlaması')

    CalibrationRepo.save_result(conn, record_id, {
        'performed_at': '2026-06-20 09:00', 'result': 'conditional',
        'usage_limit': 'Yalnizca 0-50 C araliginda kullanilir.',
        'points': [{'nominal': 0, 'measured': 0.04, 'tolerance': 0.05}]})
    CalibrationRepo.transition(conn, record_id, 'closed')
    assert CalibrationRepo.get(conn, record_id)['status'] == 'closed'


@test
def result_entry_needs_a_date():
    conn = fresh()
    device = make_device(conn)
    record_id = CalibrationRepo.create(conn, {'asset_id': device})
    refuses(lambda: CalibrationRepo.save_result(conn, record_id, {
        'points': [{'nominal': 0, 'measured': 0.1, 'tolerance': 0.5}]}), 'Yapılma zamanı')


# ====================================================================== tarama
@test
def scan_is_idempotent():
    conn = fresh()
    asset = make_asset(conn)
    ScheduleRepo.create(conn, {'asset_id': asset, 'plan_type': 'pm', 'title': 'Gecikmis',
                               'is_active': 1, 'lead_days': 7, 'next_due_at': seed.when(-5)})
    first = scheduler.scan(conn)
    second = scheduler.scan(conn)
    assert first['work_orders'] == 1 and second['work_orders'] == 0, (first, second)
    assert second['skipped'] == 1, second
    assert WorkOrderRepo.count(conn, open_only=True) == 1


@test
def scan_skips_future_and_paused_plans():
    conn = fresh()
    asset = make_asset(conn)
    ScheduleRepo.create(conn, {'asset_id': asset, 'plan_type': 'pm', 'title': 'Uzak',
                               'is_active': 1, 'lead_days': 7, 'next_due_at': seed.when(60)})
    ScheduleRepo.create(conn, {'asset_id': asset, 'plan_type': 'pm', 'title': 'Duraklatilmis',
                               'is_active': 0, 'next_due_at': seed.when(-60)})
    assert scheduler.scan(conn) == {'work_orders': 0, 'calibrations': 0, 'skipped': 0}
    assert WorkOrderRepo.count(conn, open_only=True) == 0


@test
def counter_plan_fires_when_the_reading_passes_the_target():
    conn = fresh()
    asset = make_asset(conn, 'MCH-H', counter_unit='hour')
    ScheduleRepo.create(conn, {'asset_id': asset, 'plan_type': 'pm', 'title': '500 saatte revizyon',
                               'basis': 'counter', 'counter_interval': 500, 'is_active': 1})
    AssetRepo.record_counter(conn, asset, 300)
    assert WorkOrderRepo.count(conn, open_only=True) == 0, 'hedef gecilmeden uretilmemeli'
    AssetRepo.record_counter(conn, asset, 520)
    assert WorkOrderRepo.count(conn, open_only=True) == 1
    AssetRepo.record_counter(conn, asset, 530)
    assert WorkOrderRepo.count(conn, open_only=True) == 1, 'ikinci kayit uretilmemeli'


@test
def calibration_plan_generates_a_record_not_a_work_order():
    conn = fresh()
    device = make_device(conn)
    ScheduleRepo.create(conn, {'asset_id': device, 'plan_type': 'calibration', 'title': 'Alti aylik',
                               'is_active': 1, 'lead_days': 21, 'next_due_at': seed.when(-2)})
    made = scheduler.scan(conn)
    assert made == {'work_orders': 0, 'calibrations': 1, 'skipped': 0}, made
    assert CalibrationRepo.query(conn, open_only=True)[0]['record_type'] == 'calibration'


@test
def retired_assets_generate_nothing():
    conn = fresh()
    asset = make_asset(conn)
    ScheduleRepo.create(conn, {'asset_id': asset, 'plan_type': 'pm', 'title': 'Plan',
                               'is_active': 1, 'next_due_at': seed.when(-5)})
    AssetRepo.transition(conn, asset, 'retired')
    assert scheduler.scan(conn)['skipped'] == 1
    assert WorkOrderRepo.count(conn, open_only=True) == 0


@test
def overdue_respects_the_tolerated_delay():
    conn = fresh()
    asset = make_asset(conn)
    ScheduleRepo.create(conn, {'asset_id': asset, 'plan_type': 'pm', 'title': 'Tolere edilen',
                               'is_active': 1, 'tolerance_days': 10, 'next_due_at': seed.when(-5)})
    assert scheduler.overdue(conn) == []
    ScheduleRepo.create(conn, {'asset_id': asset, 'plan_type': 'pm', 'title': 'Gercekten gecikmis',
                               'is_active': 1, 'tolerance_days': 0, 'next_due_at': seed.when(-5)})
    assert len(scheduler.overdue(conn)) == 1


# ====================================================================== durum makinesi
@test
def state_map_has_no_dead_labels():
    for entity, transitions in states.MAP.items():
        labels = states.LABELS[entity]
        for current, targets in transitions.items():
            assert current in labels, (entity, current)
            for target in targets:
                assert target in labels, (entity, target)
                assert target in transitions, (entity, target)


@test
def transition_to_the_same_state_is_refused():
    conn = fresh()
    asset = make_asset(conn)
    refuses(lambda: AssetRepo.transition(conn, asset, 'active'), 'zaten bu durumda')
    refuses(lambda: AssetRepo.transition(conn, asset, 'closed'), 'izin verilmiyor')


@test
def retired_is_a_one_way_door():
    conn = fresh()
    asset = make_asset(conn)
    AssetRepo.transition(conn, asset, 'retired')
    assert states.next_states('asset', 'retired') == ()
    refuses(lambda: AssetRepo.transition(conn, asset, 'active'), 'izin verilmiyor')


# ====================================================================== denetim gunlugu
@test
def every_change_leaves_intent_and_result():
    conn = fresh()
    asset = make_asset(conn)
    AssetRepo.transition(conn, asset, 'out_of_service', 'Tasiniyor')
    rows = audit.for_entity(conn, 'asset', asset, results_only=False)
    phases = [r['phase'] for r in rows]
    # Olusturma niyeti henuz id olmadigi icin 0 kimligine yazilir; gerisi cift gider.
    assert phases.count('intent') >= 1 and phases.count('result') >= 2, phases
    opening = audit.for_entity(conn, 'asset', 0, results_only=False)
    assert any(r['action'] == 'create' and r['phase'] == 'intent' for r in opening), opening
    latest = audit.for_entity(conn, 'asset', asset)[0]
    assert latest['from_state'] == 'active' and latest['to_state'] == 'out_of_service'
    assert 'Tasiniyor' in latest['payload']
    assert audit.count(conn) == len(rows) + len(opening)


@test
def a_refused_change_leaves_no_result_row():
    conn = fresh()
    device = make_device(conn)
    failing = CalibrationRepo.create(conn, {'asset_id': device})
    CalibrationRepo.save_result(conn, failing, {
        'performed_at': '2026-06-20 09:00',
        'points': [{'nominal': 72, 'measured': 70.4, 'tolerance': 0.5}]})
    before = len(audit.for_entity(conn, 'asset', device))
    refuses(lambda: AssetRepo.transition(conn, device, 'active'), 'hizmete dönemez')
    assert len(audit.for_entity(conn, 'asset', device)) == before, 'reddedilen gecis kayit birakmamali'


# ====================================================================== ayarlar ve yedek
@test
def settings_round_trip_and_survive_a_broken_file():
    store.save_settings({'operator': 'CGK', 'default_lead_days': 21})
    assert store.setting('operator') == 'CGK' and store.setting('default_lead_days') == 21
    store.save_settings({'unknown_key': 'x'})
    assert 'unknown_key' not in store.load_settings()

    with open(store.settings_path(), 'w', encoding='utf-8') as f:
        f.write('{bozuk')
    assert store.load_settings()['default_lead_days'] == store.DEFAULT_SETTINGS['default_lead_days']
    store.save_settings({'operator': ''})


@test
def backup_and_restore_round_trip():
    conn = fresh()
    make_asset(conn, 'BK-1')
    target = pathlib.Path(tempfile.mkdtemp()) / 'yedek.sqlite3'
    db.backup(conn, target)
    probe = db.connect(target)
    assert probe.execute("SELECT COUNT(*) AS c FROM asset WHERE code = 'BK-1'").fetchone()['c'] == 1
    probe.close()

    bogus = pathlib.Path(tempfile.mkdtemp()) / 'bos.sqlite3'
    import sqlite3
    sqlite3.connect(str(bogus)).close()
    try:
        db.restore(conn, bogus, ':memory:')
        raise AssertionError('Mihenk yedegi olmayan dosya kabul edilmemeliydi')
    except OSError as exc:
        assert 'Mihenk yedeği değil' in str(exc), exc


# ====================================================================== demo set
@test
def demo_seed_builds_the_whole_story():
    conn = fresh()
    report = seed.seed(conn)
    assert report['ok'], report

    assert AssetRepo.count(conn) == 8
    assert len(ScheduleRepo.query(conn)) == 7
    assert RequestRepo.count(conn) == 4
    assert ImpactRepo.count(conn, 'open') == 1

    probe = AssetRepo.by_code(conn, seed.PREFIX + 'THM-01')
    assert probe['status'] == 'quarantined'
    refuses(lambda: AssetRepo.transition(conn, probe['id'], 'active'), 'hizmete dönemez')

    conditional = CalibrationRepo.get(conn, report['reference_record'])
    assert conditional['result'] == 'conditional'
    refuses(lambda: CalibrationRepo.transition(conn, conditional['id'], 'closed'), 'kullanım sınırlaması')

    assert seed.seed(conn)['ok'] is False, 'ikinci kez kurulmamali'

    filler = AssetRepo.by_code(conn, seed.PREFIX + 'MCH-01')
    assert int(filler['counter_value']) == 540


@test
def demo_purge_removes_only_demo_rows():
    conn = fresh()
    keeper = make_asset(conn, 'REAL-1')
    ScheduleRepo.create(conn, {'asset_id': keeper, 'plan_type': 'pm', 'title': 'Gercek plan',
                               'is_active': 1})
    seed.seed(conn)
    assert AssetRepo.count(conn) == 9

    seed.purge(conn)
    assert AssetRepo.count(conn) == 1
    assert AssetRepo.by_code(conn, 'REAL-1') is not None
    assert len(ScheduleRepo.query(conn)) == 1, 'gercek plan durmali'
    assert ImpactRepo.count(conn, '') == 0 and CalibrationRepo.count(conn, open_only=False) == 0
    assert seed.purge(conn)['ok'] is False


@test
def version_and_paths_are_sane():
    assert core.VERSION.count('.') == 2 and core.APP_ID == 'mihenk'
    assert str(store.db_path()).endswith('mihenk.sqlite3')
    assert store.data_dir().exists()
    app = (ROOT / 'app.pyw').read_text(encoding='utf-8')
    assert "'--selftest' in sys.argv" in app
    assert app.index('--selftest') < app.index('from mihenk_app import main')


print('AGFO MIHENK CORE OK: %d tests' % len(PASSED))
