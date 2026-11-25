# -*- coding: utf-8 -*-
"""Denetim gunlugu.

Her yazma isleminden once niyet, sonra sonuc kaydedilir. Uygulama ortada
kapansa bile ne yapilmak istendigi kayitta kalir.
"""
from __future__ import annotations

import json

import mihenk_store as store
import mihenk_validate as v


def _actor() -> str:
    return v.text(store.setting('operator', '') or '', 80)


def write(conn, entity_type: str, entity_id: int, action: str, phase: str,
          payload=None, from_state: str = '', to_state: str = '') -> int:
    """Tek bir gunluk satiri yazar ve id'sini dondurur."""
    cur = conn.execute(
        'INSERT INTO log (entity_type, entity_id, action, actor, phase, from_state, to_state, payload, created_at)'
        ' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (v.text(entity_type, 32), int(entity_id or 0), v.text(action, 64), _actor(),
         'intent' if phase == 'intent' else 'result', v.text(from_state, 32), v.text(to_state, 32),
         json.dumps(payload or {}, ensure_ascii=False, default=str), v.now()))
    return int(cur.lastrowid)


def intent(conn, entity_type, entity_id, action, payload=None, from_state='', to_state='') -> int:
    """Bir degisiklige baslamadan once."""
    return write(conn, entity_type, entity_id, action, 'intent', payload, from_state, to_state)


def result(conn, entity_type, entity_id, action, payload=None, from_state='', to_state='') -> int:
    """Degisiklik tamamlandiktan sonra."""
    return write(conn, entity_type, entity_id, action, 'result', payload, from_state, to_state)


def for_entity(conn, entity_type: str, entity_id: int, limit: int = 50, results_only: bool = True) -> list:
    """Bir kaydin gecmisi, yeniden eskiye."""
    sql = 'SELECT * FROM log WHERE entity_type = ? AND entity_id = ?'
    args = [v.text(entity_type, 32), int(entity_id or 0)]
    if results_only:
        sql += " AND phase = 'result'"
    sql += ' ORDER BY id DESC LIMIT ?'
    args.append(int(limit))
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def recent(conn, limit: int = 50, results_only: bool = True) -> list:
    """Butun kayitlardaki son hareketler."""
    sql = 'SELECT * FROM log'
    if results_only:
        sql += " WHERE phase = 'result'"
    sql += ' ORDER BY id DESC LIMIT ?'
    return [dict(r) for r in conn.execute(sql, (int(limit),)).fetchall()]


def count(conn) -> int:
    """Toplam gunluk satiri."""
    return int(conn.execute('SELECT COUNT(*) AS c FROM log').fetchone()['c'])
