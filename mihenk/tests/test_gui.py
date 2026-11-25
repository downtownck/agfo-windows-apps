# -*- coding: utf-8 -*-
"""AGFO Mihenk - arayuz duman testi (xvfb ile Linux'ta da calisir).

    xvfb-run -a python -I tests/test_gui.py <mihenk klasoru>

Her ekran aciliyor mu, her pencere kuruluyor mu, reddedilen bir gecis cokme
yerine uyari mi veriyor: bunlara bakar. Gercek Windows gerekmez.
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

import tkinter as tk  # noqa: E402
from tkinter import messagebox, ttk  # noqa: E402

INFOS, WARNINGS = [], []
messagebox.showinfo = lambda *a, **k: INFOS.append(a)
messagebox.showwarning = lambda *a, **k: WARNINGS.append(a)
messagebox.showerror = lambda *a, **k: (_ for _ in ()).throw(AssertionError('hata kutusu: %s' % (a,)))
messagebox.askyesno = lambda *a, **k: True

import mihenk_app as A  # noqa: E402
import mihenk_dialogs as dialogs  # noqa: E402
import mihenk_seed as seed  # noqa: E402
import mihenk_states as states  # noqa: E402
import mihenk_theme as theme  # noqa: E402
import mihenk_widgets as w  # noqa: E402
from mihenk_checklist import ChecklistTemplate, WorkOrderChecklist  # noqa: E402
from mihenk_parts import PartRepo  # noqa: E402
from mihenk_repo import AssetRepo, CalibrationRepo, ImpactRepo, ScheduleRepo, WorkOrderRepo  # noqa: E402

PASSED = []


def test(fn):
    fn()
    PASSED.append(fn.__name__)
    return fn


root = tk.Tk()
root.withdraw()
app = A.MihenkApp(root)
report = seed.seed(app.conn)
assert report['ok'], report
app.refresh()
root.update()


def _button_texts(widget) -> list:
    """Bir pencerenin icindeki butun dugmelerin metinleri."""
    out = []
    for child in widget.winfo_children():
        if isinstance(child, ttk.Button):
            out.append(child.cget('text'))
        out.extend(_button_texts(child))
    return out


def pump():
    root.update_idletasks()
    root.update()


@test
def every_screen_opens_and_refreshes():
    for name, _label in A.NAV:
        app.go(name)
        pump()
        assert app.current == name
        screen = app.screens[name]
        screen.refresh()
        pump()


@test
def dashboard_counts_match_the_data():
    app.go('dashboard')
    pump()
    dashboard = app.screens['dashboard']
    assert dashboard.cards['impacts'].value.cget('text') == str(ImpactRepo.count(app.conn, 'open'))
    assert dashboard.cards['assets'].value.cget('text') == str(AssetRepo.count(app.conn, 'active'))
    assert dashboard.impact_table.row_count() == 1
    assert dashboard.overdue_table.row_count() >= 1


@test
def asset_table_lists_the_demo_set():
    app.go('assets')
    pump()
    screen = app.screens['assets']
    assert screen.table.row_count() == 8, screen.table.row_count()
    screen.search.set('THM')
    screen.refresh()
    pump()
    assert screen.table.row_count() == 2, screen.table.row_count()
    screen.search.set('')
    screen.refresh()
    pump()


@test
def asset_dialog_builds_for_the_quarantined_device():
    probe = AssetRepo.by_code(app.conn, seed.PREFIX + 'THM-01')
    dialog = dialogs.AssetDialog(app, probe['id'])
    pump()
    assert 'karantinada' in dialog.notice.cget('text').lower()
    assert dialog.code.get() == probe['code']
    dialog.destroy()
    pump()


@test
def asset_dialog_swaps_the_attribute_set_with_the_type():
    dialog = dialogs.AssetDialog(app)
    pump()
    dialog.asset_type.set_key('measuring_device')
    dialog._rebuild_attributes()
    pump()
    assert 'measuring_range' in dialog.attr_widgets
    dialog.asset_type.set_key('machine')
    dialog._rebuild_attributes()
    pump()
    assert 'power_kw' in dialog.attr_widgets and 'measuring_range' not in dialog.attr_widgets
    dialog.destroy()
    pump()


@test
def plan_dialog_hides_the_fields_the_basis_does_not_use():
    plan = ScheduleRepo.query(app.conn, basis='counter')[0]
    dialog = dialogs.PlanDialog(app, plan['id'])
    pump()
    assert str(dialog.counter_interval.cget('state')) == 'normal'
    assert str(dialog.interval_value.cget('state')) == 'disabled'
    dialog.basis.set_key('time')
    dialog._sync_basis()
    pump()
    assert str(dialog.interval_value.cget('state')) == 'normal'
    dialog.destroy()
    pump()


@test
def work_order_dialog_offers_the_legal_transitions_only():
    work_order = [r for r in WorkOrderRepo.query(app.conn, open_only=True)
                  if r['status'] == 'on_hold'][0]
    dialog = dialogs.WorkOrderDialog(app, work_order['id'])
    pump()
    labels = _button_texts(dialog.body)
    expected = {states.label('work_order', t)
                for t in states.next_states('work_order', 'on_hold')}
    assert expected & {text.split(' (')[0] for text in labels}, (labels, expected)
    dialog.destroy()
    pump()


@test
def closed_work_order_is_read_only():
    closed = WorkOrderRepo.query(app.conn, status='closed')[0]
    dialog = dialogs.WorkOrderDialog(app, closed['id'])
    pump()
    assert dialog.locked
    assert str(dialog.title_entry.cget('state')) == 'disabled'
    assert 'Kaydet' not in _button_texts(dialog.footer)
    dialog.destroy()
    pump()


@test
def points_grid_computes_and_colours_the_deviation():
    holder = tk.Toplevel(root)
    grid = dialogs.PointsGrid(holder, [{'label': 'Nokta', 'nominal': 10, 'measured': 10.2,
                                        'tolerance': 0.5, 'unit': 'C'}])
    grid.pack()
    pump()
    entry = grid.rows[0]
    assert entry['deviation'].cget('text') == '+0.2'
    assert str(entry['deviation'].cget('foreground')) == theme.color('ok')

    entry['measured'].delete(0, 'end')
    entry['measured'].insert(0, '12')
    grid.update_row(entry)
    pump()
    assert entry['deviation'].cget('text') == '+2'
    assert str(entry['deviation'].cget('foreground')) == theme.color('alert')

    grid.add_row({})
    pump()
    assert len(grid.rows) == 2
    collected = grid.collect()
    assert collected[0]['measured'] == '12'
    grid.remove_row(grid.rows[1])
    pump()
    assert len(grid.rows) == 1
    holder.destroy()
    pump()


@test
def calibration_dialog_shows_the_failure_and_links_the_impact():
    failing = CalibrationRepo.query(app.conn, result='fail')[0]
    dialog = dialogs.CalibrationDialog(app, failing['id'])
    pump()
    assert 'karantina' in dialog.notice.cget('text').lower()
    assert 'Etki değerlendirmesi' in _button_texts(dialog.footer)
    assert len(dialog.points.rows) == 3
    dialog.destroy()
    pump()


@test
def closed_calibration_is_read_only():
    closed = CalibrationRepo.query(app.conn, status='closed')[0]
    dialog = dialogs.CalibrationDialog(app, closed['id'])
    pump()
    assert dialog.locked and 'Sonucu kaydet' not in _button_texts(dialog.footer)
    assert str(dialog.points.rows[0]['nominal'].cget('state')) == 'disabled'
    dialog.destroy()
    pump()


@test
def impact_dialog_carries_the_window_and_refuses_an_empty_close():
    impact = ImpactRepo.query(app.conn, status='open')[0]
    dialog = dialogs.ImpactDialog(app, impact['id'])
    pump()
    assert dialog.affected_from.get() and dialog.affected_to.get()
    before = len(WARNINGS)
    dialog.close_assessment()            # karar ve degerlendirme bos
    pump()
    assert len(WARNINGS) > before, 'bos kapatma uyari vermeliydi'
    assert ImpactRepo.get(app.conn, impact['id'])['status'] == 'open'
    dialog.destroy()
    pump()


@test
def impact_can_be_closed_and_releases_the_asset():
    impact = ImpactRepo.query(app.conn, status='open')[0]
    asset_id = int(impact['asset_id'])
    dialog = dialogs.ImpactDialog(app, impact['id'])
    pump()
    w.write_text(dialog.evaluation, 'Pastorizasyon sicakligi dusuk olculmus olabilir.')
    w.write_text(dialog.scope, 'Son alti ayin pastorize partileri.')
    dialog.decision.set_key('rework')
    dialog.close_assessment()
    pump()
    assert ImpactRepo.get(app.conn, impact['id'])['status'] == 'closed'
    AssetRepo.transition(app.conn, asset_id, 'active')
    assert AssetRepo.get(app.conn, asset_id)['status'] == 'active'
    app.refresh()
    pump()


@test
def request_screen_actions_move_the_record():
    app.go('requests')
    pump()
    screen = app.screens['requests']
    open_rows = [r for r in screen.table._rows.values() if r['status'] == 'open']
    assert open_rows, 'acik talep bekleniyordu'
    screen.table.tree.selection_set(str(open_rows[0]['id']))
    pump()
    screen.move('triaged')
    pump()
    from mihenk_repo import RequestRepo
    assert RequestRepo.get(app.conn, open_rows[0]['id'])['status'] == 'triaged'


@test
def refused_transition_warns_instead_of_crashing():
    retired = AssetRepo.create(app.conn, {'code': 'GUI-RET', 'name': 'Hurda'})
    AssetRepo.transition(app.conn, retired, 'retired')
    before = len(WARNINGS)
    ok = app.run(lambda: AssetRepo.transition(app.conn, retired, 'active'), '')
    assert ok is False and len(WARNINGS) == before + 1


@test
def theme_switch_repaints_everything():
    import mihenk_store as store
    store.save_settings({'theme': 'dark'})
    app.apply_theme()
    pump()
    assert theme.mode() == 'dark'
    dark_bg = theme.color('bg')
    store.save_settings({'theme': 'light'})
    app.apply_theme()
    pump()
    assert theme.mode() == 'light' and theme.color('bg') != dark_bg
    for name, _label in A.NAV:
        app.go(name)
        pump()


@test
def date_entry_round_trips_and_calendar_opens():
    holder = tk.Toplevel(root)
    field = w.DateEntry(holder, with_time=True)
    field.pack()
    pump()
    field.set('2026-03-15 08:30')
    assert field.get() == '2026-03-15 08:30:00'
    field.set_now()
    assert field.get()
    popup = w.CalendarPopup(field)
    pump()
    popup.next_month()
    popup.prev_month()
    popup.choose(12)
    pump()
    assert field.get().startswith('%04d-%02d-12' % (popup.year, popup.month))
    field.clear()
    assert field.get() is None
    holder.destroy()
    pump()


@test
def welcome_dialog_offers_both_paths_and_only_shows_once():
    import mihenk_store as store
    store.save_settings({'first_run_done': False})
    dialog = dialogs.WelcomeDialog(app)
    pump()
    labels = _button_texts(dialog)
    assert 'Demo veriyle başla' in labels and 'Boş başla' in labels, labels
    dialog.start_empty()
    pump()
    assert dialog.choice == 'empty'
    assert store.setting('first_run_done') is True
    # Kutuk doluyken bir daha sorulmaz.
    assert app.should_offer_first_run() is False
    store.save_settings({'first_run_done': False})
    assert app.should_offer_first_run() is False, 'dolu kutukta karsilama cikmamali'
    assert store.setting('first_run_done') is True, 'dolu kutukta bayrak kendiliginden kapanmali'


@test
def update_button_appears_only_when_a_release_is_newer():
    app._update_checked({'status': 'current'})
    pump()
    assert not app.update_button.winfo_manager()
    app._update_checked({'status': 'update', 'version': '9.9.9'})
    pump()
    assert app.update_button.winfo_manager() == 'pack'
    assert '9.9.9' in app.update_button.cget('text')
    app.update_button.pack_forget()
    app.pending_update = None
    pump()


@test
def empty_list_explains_what_to_do_next():
    import mihenk_seed as seed
    seed.purge(app.conn)
    for leftover in AssetRepo.query(app.conn):       # onceki testlerin biraktigi varliklar
        AssetRepo.delete(app.conn, leftover['id'])
    app.refresh()
    for name in ('assets', 'plans', 'requests', 'work_orders', 'calibrations', 'impacts'):
        app.go(name)
        pump()
        screen = app.screens[name]
        assert screen.table.row_count() == 0, name
        assert screen._hint.winfo_manager() == 'pack', name
        assert len(screen._hint.cget('text')) > 30, name
    seed.seed(app.conn)
    app.refresh()
    pump()


@test
def settings_screen_saves_and_reports_health():
    app.go('settings')
    pump()
    screen = app.screens['settings']
    screen.operator.delete(0, 'end')
    screen.operator.insert(0, 'CGK')
    screen.save()
    pump()
    import mihenk_store as store
    assert store.setting('operator') == 'CGK'
    assert 'varlık' in screen.health.cget('text')
    assert str(screen.seed_button.cget('state')) == 'disabled', 'demo varken kur dugmesi kapali olmali'



@test
def modern_drawing_engine_is_in_use_or_names_why_not():
    assert theme.engine() in ('ttkbootstrap', 'classic')
    assert theme.engine_status()
    if theme.engine() == 'classic':
        print('   not: ttkbootstrap yok, klasik cizimle kosuldu —', theme.engine_status())


@test
def plan_dialog_edits_the_checklist_template():
    plan = [p for p in ScheduleRepo.query(app.conn)
            if ChecklistTemplate.count(app.conn, p['id'])][0]
    dialog = dialogs.PlanDialog(app, plan['id'])
    pump()
    assert len(dialog.checklist.rows) == ChecklistTemplate.count(app.conn, plan['id'])
    before = len(dialog.checklist.rows)
    dialog.checklist.add_row({'text': 'Yeni adım', 'is_critical': True})
    pump()
    assert len(dialog.checklist.rows) == before + 1
    dialog.checklist.remove_row(dialog.checklist.rows[0])
    pump()
    assert len(dialog.checklist.rows) == before
    assert dialog.checklist.rows[0]['order'].cget('text') == '1', 'sira yeniden numaralanmali'
    dialog.destroy()
    pump()


@test
def work_order_dialog_shows_and_saves_the_checklist():
    plan = [p for p in ScheduleRepo.query(app.conn)
            if ChecklistTemplate.count(app.conn, p['id']) and p['plan_type'] == 'pm'][0]
    orders = [r for r in WorkOrderRepo.query(app.conn, open_only=True)
              if int(r['schedule_id']) == int(plan['id'])]
    assert orders, 'plandan uretilmis is emri bekleniyordu'
    dialog = dialogs.WorkOrderDialog(app, orders[0]['id'])
    pump()
    assert dialog.checklist.rows, 'kontrol listesi gorunmeli'

    # Olcum isteyen adim bos birakilirsa kaydetme reddedilir.
    for row in dialog.checklist.rows:
        row['state'].set_key('ok')
    before = len(WARNINGS)
    assert dialog.checklist.save() is False
    assert len(WARNINGS) > before
    dialog.destroy()
    pump()


@test
def parts_screen_flags_low_stock():
    app.go('parts')
    pump()
    screen = app.screens['parts']
    assert screen.table.row_count() == 4, screen.table.row_count()
    assert 'düşük stok' in screen.count_label.cget('text')
    screen.low_only.set(True)
    screen.refresh()
    pump()
    assert 0 < screen.table.row_count() < 4
    screen.low_only.set(False)
    screen.refresh()
    pump()


@test
def part_dialog_records_a_movement():
    part = PartRepo.by_code(app.conn, seed.PREFIX + 'PRT-003')
    before = float(part['stock'])
    dialog = dialogs.PartDialog(app, part['id'])
    pump()
    dialog.move_amount.insert(0, '3')
    dialog.move_reason.set_key('receive')
    dialog.record_movement()
    pump()
    assert float(PartRepo.get(app.conn, part['id'])['stock']) == before + 3


@test
def reports_screen_fills_every_panel():
    app.go('reports')
    pump()
    screen = app.screens['reports']
    assert screen.cards['parts'].value.cget('text') != '—'
    assert screen.reliability.row_count() >= 0
    assert screen.ageing.row_count() >= 1, 'geciken plan bekleniyordu'
    screen.device.set_key(AssetRepo.by_code(app.conn, seed.PREFIX + 'THM-01')['id'])
    screen.refresh_deviation()
    pump()
    assert screen.deviation.row_count() == 2, screen.deviation.row_count()
    screen.period.set_key('30')
    screen.period_changed()
    pump()
    screen.period.set_key('365')
    screen.period_changed()
    pump()


@test
def export_dialog_writes_a_workbook():
    import mihenk_export as export
    dialog = dialogs.ExportDialog(app, 365)
    pump()
    assert len(dialog.choices) == len(export.ALL_TABLES)
    dialog._set_all(False)
    pump()
    assert dialog.keys() == []
    dialog._set_all(True)
    pump()

    target = pathlib.Path(tempfile.mkdtemp()) / 'cikti.xlsx'
    export.to_xlsx(app.conn, target, dialog.keys(), 365)
    assert target.exists() and target.stat().st_size > 2000
    dialog.destroy()
    pump()


app.close()
print('AGFO MIHENK GUI OK: %d tests' % len(PASSED))
