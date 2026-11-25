# -*- coding: utf-8 -*-
"""Kontrol listesi sablonlari ve is emri uzerindeki isaretlemeler.

Sablon plana baglidir. Plandan bir is emri uretildiginde sablonun o anki hali
is emrine kopyalanir; sonra sablon degisirse gecmis is emri degismez. Denetime
"bu is nasil yapildi" diye soruldugunda gosterilen sey, o gun gecerli olan
listedir.
"""
from __future__ import annotations

import mihenk_audit as audit
import mihenk_store as store
import mihenk_validate as v
from mihenk_validate import MihenkError
from mihenk_i18n import t

STATES = {'pending': t('Bekliyor'), 'ok': t('Uygun'), 'na': t('Uygulanmaz'), 'fail': t('Uygunsuz')}


def _operator() -> str:
    return v.text(store.setting('operator', '') or '', 80)


def _rows(cursor) -> list:
    return [dict(r) for r in cursor.fetchall()]


# ====================================================================== sablon
class ChecklistTemplate:
    """Plana bagli adim listesi."""

    @staticmethod
    def items(conn, schedule_id) -> list:
        return _rows(conn.execute('SELECT * FROM checklist_item WHERE schedule_id = ?'
                                  ' ORDER BY position, id', (int(schedule_id),)))

    @staticmethod
    def count(conn, schedule_id) -> int:
        row = conn.execute('SELECT COUNT(*) AS c FROM checklist_item WHERE schedule_id = ?',
                           (int(schedule_id),)).fetchone()
        return int(row['c'])

    @staticmethod
    def save(conn, schedule_id, items) -> int:
        """Sablonu bastan yazar. Bos metinli satirlar atilir.

        Uretilmis is emirlerindeki kopyalara dokunmaz; onlar kendi anlarini tasir.
        """
        schedule_id = int(schedule_id)
        clean = []
        for row in (items or []):
            text = v.text(row.get('text'), 300)
            if not text:
                continue
            clean.append({
                'text': text,
                'needs_value': 1 if row.get('needs_value') else 0,
                'unit': v.text(row.get('unit'), 24),
                'is_critical': 1 if row.get('is_critical') else 0,
            })
        audit.intent(conn, 'schedule', schedule_id, 'checklist_save', {'items': len(clean)})
        conn.execute('DELETE FROM checklist_item WHERE schedule_id = ?', (schedule_id,))
        for position, row in enumerate(clean, start=1):
            conn.execute('INSERT INTO checklist_item (schedule_id, position, text, needs_value,'
                         ' unit, is_critical) VALUES (?, ?, ?, ?, ?, ?)',
                         (schedule_id, position, row['text'], row['needs_value'], row['unit'],
                          row['is_critical']))
        audit.result(conn, 'schedule', schedule_id, 'checklist_save', {'items': len(clean)})
        return len(clean)

    @staticmethod
    def delete_for_plan(conn, schedule_id) -> None:
        conn.execute('DELETE FROM checklist_item WHERE schedule_id = ?', (int(schedule_id),))


# ====================================================================== is emri kopyasi
class WorkOrderChecklist:
    """Is emrine kopyalanmis liste ve isaretlemeleri."""

    @staticmethod
    def items(conn, work_order_id) -> list:
        return _rows(conn.execute('SELECT * FROM work_order_check WHERE work_order_id = ?'
                                  ' ORDER BY position, id', (int(work_order_id),)))

    @staticmethod
    def copy_from_plan(conn, work_order_id, schedule_id) -> int:
        """Plan sablonunu is emrine kopyalar. Zaten kopyalanmissa dokunmaz."""
        work_order_id, schedule_id = int(work_order_id), int(schedule_id)
        if not schedule_id or WorkOrderChecklist.items(conn, work_order_id):
            return 0
        source = ChecklistTemplate.items(conn, schedule_id)
        for row in source:
            conn.execute('INSERT INTO work_order_check (work_order_id, position, text, needs_value,'
                         ' unit, is_critical, state) VALUES (?, ?, ?, ?, ?, ?, ?)',
                         (work_order_id, row['position'], row['text'], row['needs_value'],
                          row['unit'], row['is_critical'], 'pending'))
        if source:
            audit.result(conn, 'work_order', work_order_id, 'checklist_copied',
                         {'items': len(source), 'schedule_id': schedule_id})
        return len(source)

    @staticmethod
    def add_item(conn, work_order_id, text, needs_value=False, unit='', is_critical=False) -> int:
        """Plan disi bir adim ekler (sahada cikan is)."""
        work_order_id = int(work_order_id)
        text = v.text(text, 300)
        if not text:
            raise MihenkError(t('Adım metni boş olamaz.'))
        row = conn.execute('SELECT COALESCE(MAX(position), 0) AS p FROM work_order_check'
                           ' WHERE work_order_id = ?', (work_order_id,)).fetchone()
        cur = conn.execute('INSERT INTO work_order_check (work_order_id, position, text,'
                           ' needs_value, unit, is_critical, state) VALUES (?, ?, ?, ?, ?, ?, ?)',
                           (work_order_id, int(row['p']) + 1, text, 1 if needs_value else 0,
                            v.text(unit, 24), 1 if is_critical else 0, 'pending'))
        return int(cur.lastrowid)

    @staticmethod
    def set_state(conn, item_id, state, value='', note='') -> None:
        """Bir adimi isaretler. Deger isteyen adim bos deger kabul etmez."""
        item_id = int(item_id)
        row = conn.execute('SELECT * FROM work_order_check WHERE id = ?', (item_id,)).fetchone()
        if not row:
            raise MihenkError(t('Adım bulunamadı.'))
        state = v.enum(state, STATES, 'pending')
        value = v.text(value, 80)
        if state == 'ok' and int(row['needs_value']) and not value:
            raise MihenkError(t('"%s" adımı bir ölçüm değeri istiyor.') % row['text'])
        conn.execute('UPDATE work_order_check SET state = ?, value = ?, note = ?, checked_by = ?,'
                     ' checked_at = ? WHERE id = ?',
                     (state, value, v.multiline(note, 500), _operator() if state != 'pending' else '',
                      v.now() if state != 'pending' else None, item_id))

    @staticmethod
    def save_all(conn, work_order_id, rows) -> None:
        """Ekrandaki butun satirlari bir kerede yazar."""
        for row in (rows or []):
            WorkOrderChecklist.set_state(conn, row.get('id'), row.get('state', 'pending'),
                                         row.get('value', ''), row.get('note', ''))
        audit.result(conn, 'work_order', int(work_order_id), 'checklist_saved',
                     WorkOrderChecklist.progress(conn, work_order_id))

    @staticmethod
    def progress(conn, work_order_id) -> dict:
        """Kac adim var, kaci isaretlendi, kaci uygunsuz."""
        rows = WorkOrderChecklist.items(conn, work_order_id)
        done = sum(1 for r in rows if r['state'] in ('ok', 'na'))
        failed = sum(1 for r in rows if r['state'] == 'fail')
        pending = sum(1 for r in rows if r['state'] == 'pending')
        critical_open = sum(1 for r in rows
                            if int(r['is_critical']) and r['state'] in ('pending', 'fail'))
        return {'total': len(rows), 'done': done, 'failed': failed, 'pending': pending,
                'critical_open': critical_open}

    @staticmethod
    def blocking_reason(conn, work_order_id):
        """Is emri tamamlanmaya hazir mi. Hazirsa None, degilse sebebi.

        Kritik adimlar isaretlenmeden is emri tamamlanamaz; kritik olmayan
        adimlar uyari konusudur, engel degil.
        """
        state = WorkOrderChecklist.progress(conn, work_order_id)
        if state['critical_open']:
            return (t('%d kritik kontrol adımı hâlâ bekliyor ya da uygunsuz.')
                    % state['critical_open'])
        return None

    @staticmethod
    def summary_text(conn, work_order_id) -> str:
        """Yapilan is alanina eklenecek kisa ozet."""
        rows = WorkOrderChecklist.items(conn, work_order_id)
        if not rows:
            return ''
        lines = []
        for row in rows:
            mark = {'ok': '[+]', 'na': '[-]', 'fail': '[!]', 'pending': '[ ]'}[row['state']]
            text = '%s %s' % (mark, row['text'])
            if row['value']:
                text += ': %s%s' % (row['value'], (' ' + row['unit']) if row['unit'] else '')
            if row['note']:
                text += ' — %s' % row['note']
            lines.append(text)
        return '\n'.join(lines)
