# -*- coding: utf-8 -*-
"""SQLite semasi ve baglanti.

Sekiz tablo, WordPress eklentisindeki wp_mihenk_* tablolariyla ayni alanlari
tasir; boylece ileride iki taraf arasinda disa/ice aktarim yazmak kolay olur.
Tablo adlari yalnizca TABLES listesinden gelir, hicbir SQL tanimlayicisi
kullanici girdisinden uretilmez.
"""
from __future__ import annotations

import pathlib
import shutil
import sqlite3

SCHEMA_VERSION = 1

TABLES = ('asset', 'asset_attr', 'schedule', 'request', 'work_order', 'calibration', 'impact', 'log')

DDL = {
    'asset': """
        CREATE TABLE IF NOT EXISTS asset (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER NOT NULL DEFAULT 0,
            asset_type TEXT NOT NULL DEFAULT 'machine',
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL DEFAULT '',
            manufacturer TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            serial_no TEXT NOT NULL DEFAULT '',
            location_text TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            is_measuring_device INTEGER NOT NULL DEFAULT 0,
            criticality INTEGER NOT NULL DEFAULT 2,
            commissioned_on TEXT,
            counter_unit TEXT NOT NULL DEFAULT '',
            counter_value INTEGER NOT NULL DEFAULT 0,
            counter_read_at TEXT,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
    'asset_attr': """
        CREATE TABLE IF NOT EXISTS asset_attr (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL,
            attr_key TEXT NOT NULL,
            attr_value TEXT NOT NULL DEFAULT '',
            attr_type TEXT NOT NULL DEFAULT 'text',
            UNIQUE (asset_id, attr_key)
        )""",
    'schedule': """
        CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL,
            plan_type TEXT NOT NULL DEFAULT 'pm',
            title TEXT NOT NULL DEFAULT '',
            basis TEXT NOT NULL DEFAULT 'time',
            interval_value INTEGER NOT NULL DEFAULT 1,
            interval_unit TEXT NOT NULL DEFAULT 'month',
            counter_interval INTEGER NOT NULL DEFAULT 0,
            last_done_at TEXT,
            last_done_counter INTEGER NOT NULL DEFAULT 0,
            next_due_at TEXT,
            next_due_counter INTEGER NOT NULL DEFAULT 0,
            lead_days INTEGER NOT NULL DEFAULT 14,
            tolerance_days INTEGER NOT NULL DEFAULT 0,
            assignee TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1,
            instructions TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
    'request': """
        CREATE TABLE IF NOT EXISTS request (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL,
            reported_by TEXT NOT NULL DEFAULT '',
            reported_at TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            severity TEXT NOT NULL DEFAULT 'normal',
            status TEXT NOT NULL DEFAULT 'open',
            work_order_id INTEGER NOT NULL DEFAULT 0,
            rejection_reason TEXT NOT NULL DEFAULT '',
            closed_at TEXT
        )""",
    'work_order': """
        CREATE TABLE IF NOT EXISTS work_order (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL,
            schedule_id INTEGER NOT NULL DEFAULT 0,
            request_id INTEGER NOT NULL DEFAULT 0,
            wo_type TEXT NOT NULL DEFAULT 'corrective',
            title TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'new',
            priority TEXT NOT NULL DEFAULT 'normal',
            assigned_to TEXT NOT NULL DEFAULT '',
            planned_start TEXT,
            planned_end TEXT,
            actual_start TEXT,
            actual_end TEXT,
            downtime_minutes INTEGER NOT NULL DEFAULT 0,
            labor_minutes INTEGER NOT NULL DEFAULT 0,
            work_done TEXT NOT NULL DEFAULT '',
            root_cause TEXT NOT NULL DEFAULT '',
            hold_reason TEXT NOT NULL DEFAULT '',
            closed_by TEXT NOT NULL DEFAULT '',
            closed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
    'calibration': """
        CREATE TABLE IF NOT EXISTS calibration (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL,
            schedule_id INTEGER NOT NULL DEFAULT 0,
            record_type TEXT NOT NULL DEFAULT 'calibration',
            performed_at TEXT,
            performed_by TEXT NOT NULL DEFAULT '',
            external_body TEXT NOT NULL DEFAULT '',
            accreditation_scope TEXT NOT NULL DEFAULT '',
            certificate_no TEXT NOT NULL DEFAULT '',
            certificate_path TEXT NOT NULL DEFAULT '',
            traceability_ref TEXT NOT NULL DEFAULT '',
            measurement_points TEXT NOT NULL DEFAULT '[]',
            tolerance_spec TEXT NOT NULL DEFAULT '',
            max_deviation REAL,
            uncertainty TEXT NOT NULL DEFAULT '',
            result TEXT NOT NULL DEFAULT '',
            next_due_at TEXT,
            status TEXT NOT NULL DEFAULT 'planned',
            impact_id INTEGER NOT NULL DEFAULT 0,
            usage_limit TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
    'impact': """
        CREATE TABLE IF NOT EXISTS impact (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            calibration_id INTEGER NOT NULL DEFAULT 0,
            asset_id INTEGER NOT NULL,
            opened_at TEXT NOT NULL,
            opened_by TEXT NOT NULL DEFAULT '',
            affected_from TEXT,
            affected_to TEXT,
            affected_scope TEXT NOT NULL DEFAULT '',
            evaluation TEXT NOT NULL DEFAULT '',
            decision TEXT NOT NULL DEFAULT '',
            corrective_action TEXT NOT NULL DEFAULT '',
            closed_by TEXT NOT NULL DEFAULT '',
            closed_at TEXT,
            status TEXT NOT NULL DEFAULT 'open'
        )""",
    'log': """
        CREATE TABLE IF NOT EXISTS log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL DEFAULT '',
            entity_id INTEGER NOT NULL DEFAULT 0,
            action TEXT NOT NULL DEFAULT '',
            actor TEXT NOT NULL DEFAULT '',
            phase TEXT NOT NULL DEFAULT 'result',
            from_state TEXT NOT NULL DEFAULT '',
            to_state TEXT NOT NULL DEFAULT '',
            payload TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )""",
}

INDEXES = (
    'CREATE INDEX IF NOT EXISTS idx_asset_parent ON asset (parent_id)',
    'CREATE INDEX IF NOT EXISTS idx_asset_status ON asset (status)',
    'CREATE INDEX IF NOT EXISTS idx_schedule_asset ON schedule (asset_id)',
    'CREATE INDEX IF NOT EXISTS idx_schedule_due ON schedule (next_due_at)',
    'CREATE INDEX IF NOT EXISTS idx_request_status ON request (status)',
    'CREATE INDEX IF NOT EXISTS idx_wo_status ON work_order (status)',
    'CREATE INDEX IF NOT EXISTS idx_wo_asset ON work_order (asset_id)',
    'CREATE INDEX IF NOT EXISTS idx_cal_asset ON calibration (asset_id)',
    'CREATE INDEX IF NOT EXISTS idx_cal_status ON calibration (status)',
    'CREATE INDEX IF NOT EXISTS idx_impact_status ON impact (status)',
    'CREATE INDEX IF NOT EXISTS idx_log_entity ON log (entity_type, entity_id)',
)


def table(name: str) -> str:
    """Tablo adini beyaz listeden dogrular. Liste disindaki ad bos doner."""
    return name if name in TABLES else ''


def connect(path) -> sqlite3.Connection:
    """Baglanti acar ve semayi kurar."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode = WAL')
    conn.execute('PRAGMA synchronous = NORMAL')
    conn.execute('PRAGMA foreign_keys = ON')
    install(conn)
    return conn


def install(conn: sqlite3.Connection) -> None:
    """Eksik tablolari ve dizinleri olusturur. Var olan veriye dokunmaz."""
    for name in TABLES:
        conn.execute(DDL[name])
    for stmt in INDEXES:
        conn.execute(stmt)
    conn.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    conn.execute('INSERT OR IGNORE INTO meta (key, value) VALUES (?, ?)',
                 ('schema_version', str(SCHEMA_VERSION)))


def table_status(conn: sqlite3.Connection) -> dict:
    """Hangi tablolar yerinde: ad -> bool."""
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    present = {r['name'] for r in rows}
    return {name: (name in present) for name in TABLES}


def counts(conn: sqlite3.Connection) -> dict:
    """Her tablodaki satir sayisi."""
    out = {}
    for name in TABLES:
        try:
            out[name] = int(conn.execute('SELECT COUNT(*) AS c FROM %s' % name).fetchone()['c'])
        except sqlite3.Error:
            out[name] = -1
    return out


def backup(conn: sqlite3.Connection, dest) -> pathlib.Path:
    """Acik veritabanini tutarli bicimde kopyalar (WAL dahil)."""
    dest = pathlib.Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    target = sqlite3.connect(str(dest))
    try:
        conn.backup(target)
    finally:
        target.close()
    return dest


def restore(conn: sqlite3.Connection, source, db_file) -> None:
    """Yedegi geri yukler. Once mevcut dosyanin yanina .pre-restore kopyasi birakir."""
    source, db_file = pathlib.Path(source), pathlib.Path(db_file)
    if not source.exists():
        raise OSError('Yedek dosyası bulunamadı: %s' % source)
    probe = sqlite3.connect(str(source))
    try:
        names = {r[0] for r in probe.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        probe.close()
    missing = [t for t in TABLES if t not in names]
    if missing:
        raise OSError('Bu dosya bir Mihenk yedeği değil (eksik tablolar: %s)' % ', '.join(missing))
    conn.close()
    shutil.copyfile(db_file, str(db_file) + '.pre-restore')
    shutil.copyfile(source, db_file)
