# -*- coding: utf-8 -*-
"""Kayit katmani: varlik, plan, talep, is emri, kalibrasyon, etki degerlendirmesi.

Kural: hicbir depo status alanini dogrudan yazmaz. Durum yalnizca transition()
icinden, mihenk_states.guard() gectikten sonra degisir.
"""
from __future__ import annotations

import mihenk_audit as audit
import mihenk_states as states
import mihenk_store as store
import mihenk_validate as v
from mihenk_validate import MihenkError


# ====================================================================== varlik tipleri
class AssetTypes:
    """Varlik tipleri ve her tipin tasidigi ek ozellikler."""

    TYPES = {
        'location': 'Konum',
        'line': 'Üretim hattı',
        'machine': 'Makine',
        'component': 'Bileşen',
        'measuring_device': 'Ölçüm cihazı',
    }

    STATUSES = {
        'active': 'Aktif',
        'out_of_service': 'Hizmet dışı',
        'quarantined': 'Karantinada',
        'retired': 'Hurdaya ayrıldı',
    }

    COUNTER_UNITS = {
        '': '- yok -',
        'hour': 'Çalışma saati',
        'cycle': 'Çevrim',
        'km': 'Kilometre',
    }

    CRITICALITY = {1: '1 - düşük', 2: '2 - normal', 3: '3 - kritik'}

    ATTRIBUTES = {
        'measuring_device': (
            {'key': 'measuring_range', 'label': 'Ölçüm aralığı', 'type': 'text'},
            {'key': 'resolution', 'label': 'Çözünürlük', 'type': 'text'},
            {'key': 'accuracy_class', 'label': 'Doğruluk sınıfı', 'type': 'text'},
            {'key': 'reference_standard', 'label': 'Referans standart', 'type': 'text'},
        ),
        'machine': (
            {'key': 'power_kw', 'label': 'Güç (kW)', 'type': 'number'},
            {'key': 'year_built', 'label': 'Üretim yılı', 'type': 'number'},
            {'key': 'food_contact', 'label': 'Gıdaya temas eden yüzey', 'type': 'bool'},
        ),
        'line': (
            {'key': 'throughput', 'label': 'Nominal kapasite', 'type': 'text'},
        ),
        'component': (
            {'key': 'part_no', 'label': 'Parça numarası', 'type': 'text'},
        ),
        'location': (
            {'key': 'site_code', 'label': 'Saha kodu', 'type': 'text'},
        ),
    }

    @classmethod
    def label(cls, key: str) -> str:
        return cls.TYPES.get(key, key or '')

    @classmethod
    def attributes(cls, asset_type: str) -> tuple:
        return cls.ATTRIBUTES.get(asset_type, ())

    @classmethod
    def is_measuring(cls, asset_type: str) -> bool:
        return asset_type == 'measuring_device'


def _operator() -> str:
    return v.text(store.setting('operator', '') or '', 80)


def _rows(cursor) -> list:
    return [dict(r) for r in cursor.fetchall()]


def _row(cursor):
    found = cursor.fetchone()
    return dict(found) if found else None


# ====================================================================== varlik
class AssetRepo:
    """Ekipman kutugu."""

    FIELDS = ('parent_id', 'asset_type', 'code', 'name', 'manufacturer', 'model', 'serial_no',
              'location_text', 'is_measuring_device', 'criticality', 'commissioned_on',
              'counter_unit', 'notes')

    @staticmethod
    def sanitize(data: dict) -> dict:
        """Form girdisini kayit bicimine getirir. status burada yok, bilerek."""
        asset_type = v.enum(data.get('asset_type'), AssetTypes.TYPES, 'machine')
        out = {
            'parent_id': v.integer(data.get('parent_id'), 0, None, 0),
            'asset_type': asset_type,
            'code': v.text(data.get('code'), 64),
            'name': v.text(data.get('name'), 191),
            'manufacturer': v.text(data.get('manufacturer'), 191),
            'model': v.text(data.get('model'), 191),
            'serial_no': v.text(data.get('serial_no'), 128),
            'location_text': v.text(data.get('location_text'), 191),
            'is_measuring_device': 1 if data.get('is_measuring_device') else 0,
            'criticality': v.integer(data.get('criticality'), 1, 3, 2),
            'commissioned_on': v.day(data.get('commissioned_on')),
            'counter_unit': v.enum(data.get('counter_unit'), AssetTypes.COUNTER_UNITS, ''),
            'notes': v.multiline(data.get('notes')),
        }
        if AssetTypes.is_measuring(asset_type):
            out['is_measuring_device'] = 1
        return out

    @staticmethod
    def get(conn, asset_id):
        return _row(conn.execute('SELECT * FROM asset WHERE id = ?', (int(asset_id or 0),)))

    @staticmethod
    def by_code(conn, code):
        return _row(conn.execute('SELECT * FROM asset WHERE code = ?', (v.text(code, 64),)))

    @staticmethod
    def query(conn, status='', asset_type='', search='', measuring=None, order='name') -> list:
        """Filtreli liste. order yalniz bilinen kolon adlarini kabul eder."""
        where, args = ['1=1'], []
        if status:
            where.append('status = ?')
            args.append(status)
        if asset_type:
            where.append('asset_type = ?')
            args.append(asset_type)
        if measuring is not None:
            where.append('is_measuring_device = ?')
            args.append(1 if measuring else 0)
        if search:
            like = '%' + str(search).strip() + '%'
            where.append('(name LIKE ? OR code LIKE ? OR serial_no LIKE ? OR location_text LIKE ?)')
            args.extend([like, like, like, like])
        column = order if order in ('name', 'code', 'status', 'asset_type', 'criticality', 'id') else 'name'
        sql = 'SELECT * FROM asset WHERE %s ORDER BY %s COLLATE NOCASE ASC' % (' AND '.join(where), column)
        return _rows(conn.execute(sql, args))

    @staticmethod
    def count(conn, status='') -> int:
        if status:
            row = conn.execute('SELECT COUNT(*) AS c FROM asset WHERE status = ?', (status,)).fetchone()
        else:
            row = conn.execute('SELECT COUNT(*) AS c FROM asset').fetchone()
        return int(row['c'])

    @staticmethod
    def children(conn, asset_id) -> list:
        return _rows(conn.execute('SELECT * FROM asset WHERE parent_id = ? ORDER BY name', (int(asset_id),)))

    @staticmethod
    def descendant_ids(conn, asset_id) -> list:
        """Alt varliklarin tum kimlikleri. Dongu olsa bile sonsuza gitmez."""
        found, queue, guard = [], [int(asset_id)], 0
        while queue and guard < 2000:
            guard += 1
            current = queue.pop(0)
            for row in conn.execute('SELECT id FROM asset WHERE parent_id = ?', (current,)).fetchall():
                child = int(row['id'])
                if child not in found:
                    found.append(child)
                    queue.append(child)
        return found

    @staticmethod
    def ancestors(conn, asset_id) -> list:
        """Kokten bu varliga kadar olan yol."""
        chain, guard = [], 0
        row = AssetRepo.get(conn, asset_id)
        while row and int(row['parent_id']) and guard < 50:
            guard += 1
            row = AssetRepo.get(conn, int(row['parent_id']))
            if row:
                chain.insert(0, row)
        return chain

    @staticmethod
    def label(conn, asset_id) -> str:
        row = AssetRepo.get(conn, asset_id)
        if not row:
            return ''
        return ('%s - %s' % (row['code'], row['name'])) if row['code'] else row['name']

    @staticmethod
    def options(conn, exclude=0) -> list:
        """Acilir liste icin (id, etiket) ciftleri. exclude ve altlari disarida kalir."""
        blocked = set()
        if exclude:
            blocked = set(AssetRepo.descendant_ids(conn, exclude)) | {int(exclude)}
        out = []
        for row in conn.execute('SELECT id, code, name FROM asset ORDER BY code COLLATE NOCASE').fetchall():
            if int(row['id']) in blocked:
                continue
            label = ('%s - %s' % (row['code'], row['name'])) if row['code'] else row['name']
            out.append((int(row['id']), label))
        return out

    @staticmethod
    def attributes(conn, asset_id) -> dict:
        rows = conn.execute('SELECT attr_key, attr_value FROM asset_attr WHERE asset_id = ?',
                            (int(asset_id),)).fetchall()
        return {r['attr_key']: r['attr_value'] for r in rows}

    @staticmethod
    def save_attributes(conn, asset_id, values: dict, asset_type: str) -> None:
        """Tipin ozellik setini yazar; baska tipin alanlarini silmez, dokunmaz."""
        values = values or {}
        for definition in AssetTypes.attributes(asset_type):
            key = definition['key']
            raw = values.get(key, '')
            if definition['type'] == 'bool':
                stored = '0' if not raw or str(raw) in ('0', 'False', 'false') else '1'
            elif definition['type'] == 'number':
                num = v.number(raw)
                stored = '' if num is None else str(num)
            else:
                stored = v.text(raw, 191)
            conn.execute(
                'INSERT INTO asset_attr (asset_id, attr_key, attr_value, attr_type) VALUES (?, ?, ?, ?)'
                ' ON CONFLICT(asset_id, attr_key) DO UPDATE SET attr_value = excluded.attr_value,'
                ' attr_type = excluded.attr_type',
                (int(asset_id), key, stored, definition['type']))

    @staticmethod
    def create(conn, data: dict) -> int:
        clean = AssetRepo.sanitize(data)
        if not clean['name']:
            raise MihenkError('Varlık adı zorunludur.')
        if not clean['code']:
            raise MihenkError('Varlık kodu zorunludur.')
        if AssetRepo.by_code(conn, clean['code']):
            raise MihenkError('Bu kodu başka bir varlık kullanıyor.')

        audit.intent(conn, 'asset', 0, 'create', {'code': clean['code']}, '', 'active')
        stamp = v.now()
        columns = list(AssetRepo.FIELDS) + ['status', 'created_at', 'updated_at']
        args = [clean[f] for f in AssetRepo.FIELDS] + ['active', stamp, stamp]
        cur = conn.execute('INSERT INTO asset (%s) VALUES (%s)'
                           % (', '.join(columns), ', '.join('?' * len(columns))), args)
        asset_id = int(cur.lastrowid)
        AssetRepo.save_attributes(conn, asset_id, data.get('attr'), clean['asset_type'])
        audit.result(conn, 'asset', asset_id, 'create', {'code': clean['code']}, '', 'active')
        return asset_id

    @staticmethod
    def update(conn, asset_id, data: dict) -> None:
        asset_id = int(asset_id)
        current = AssetRepo.get(conn, asset_id)
        if not current:
            raise MihenkError('Varlık bulunamadı.')
        clean = AssetRepo.sanitize(data)
        if not clean['name']:
            raise MihenkError('Varlık adı zorunludur.')
        if not clean['code']:
            raise MihenkError('Varlık kodu zorunludur.')
        clash = AssetRepo.by_code(conn, clean['code'])
        if clash and int(clash['id']) != asset_id:
            raise MihenkError('Bu kodu başka bir varlık kullanıyor.')
        if clean['parent_id'] == asset_id:
            raise MihenkError('Bir varlık kendi üst varlığı olamaz.')
        if clean['parent_id'] and clean['parent_id'] in AssetRepo.descendant_ids(conn, asset_id):
            raise MihenkError('Bu üst varlık hiyerarşide döngü oluşturur.')

        audit.intent(conn, 'asset', asset_id, 'update', {'code': clean['code']})
        assignments = ', '.join('%s = ?' % f for f in AssetRepo.FIELDS)
        args = [clean[f] for f in AssetRepo.FIELDS] + [v.now(), asset_id]
        conn.execute('UPDATE asset SET %s, updated_at = ? WHERE id = ?' % assignments, args)
        AssetRepo.save_attributes(conn, asset_id, data.get('attr'), clean['asset_type'])
        audit.result(conn, 'asset', asset_id, 'update', {'code': clean['code']})

    @staticmethod
    def transition(conn, asset_id, target: str, reason: str = '') -> None:
        asset_id = int(asset_id)
        row = AssetRepo.get(conn, asset_id)
        if not row:
            raise MihenkError('Varlık bulunamadı.')
        states.guard(conn, 'asset', row, target)
        audit.intent(conn, 'asset', asset_id, 'transition', {'reason': reason}, row['status'], target)
        conn.execute('UPDATE asset SET status = ?, updated_at = ? WHERE id = ?',
                     (target, v.now(), asset_id))
        audit.result(conn, 'asset', asset_id, 'transition', {'reason': reason}, row['status'], target)

    @staticmethod
    def record_counter(conn, asset_id, value, run_scan=True) -> dict:
        """Sayac okumasi kaydeder ve sayac tabanli planlari tetikler."""
        asset_id = int(asset_id)
        row = AssetRepo.get(conn, asset_id)
        if not row:
            raise MihenkError('Varlık bulunamadı.')
        if not row['counter_unit']:
            raise MihenkError('Bu varlıkta sayaç birimi tanımlı değil.')
        reading = v.integer(value, 0, None, 0)
        if reading < int(row['counter_value']):
            raise MihenkError('Sayaç okuması bir öncekinden düşük olamaz.')
        audit.intent(conn, 'asset', asset_id, 'counter', {'value': reading})
        stamp = v.now()
        conn.execute('UPDATE asset SET counter_value = ?, counter_read_at = ?, updated_at = ? WHERE id = ?',
                     (reading, stamp, stamp, asset_id))
        audit.result(conn, 'asset', asset_id, 'counter', {'value': reading})
        if run_scan:
            import mihenk_scheduler as scheduler
            return scheduler.scan_counter_plans(conn, asset_id)
        return {'work_orders': 0, 'calibrations': 0, 'skipped': 0}

    @staticmethod
    def delete(conn, asset_id) -> None:
        """Gecmisi olan varlik silinmez; hurdaya ayrilir."""
        asset_id = int(asset_id)
        if AssetRepo.children(conn, asset_id):
            raise MihenkError('Önce alt varlıkları taşıyın veya kaldırın.')
        for table in ('schedule', 'work_order', 'calibration'):
            row = conn.execute('SELECT COUNT(*) AS c FROM %s WHERE asset_id = ?' % table,
                               (asset_id,)).fetchone()
            if int(row['c']):
                raise MihenkError('Bu varlığın bakım geçmişi var, silinemez. '
                                  'Bunun yerine hurdaya ayırın.')
        audit.intent(conn, 'asset', asset_id, 'delete')
        conn.execute('DELETE FROM asset_attr WHERE asset_id = ?', (asset_id,))
        conn.execute('DELETE FROM asset WHERE id = ?', (asset_id,))
        audit.result(conn, 'asset', asset_id, 'delete')


# ====================================================================== plan
class ScheduleRepo:
    """Bakim, kalibrasyon ve dogrulama planlari. Tek tablo, uc tip."""

    PLAN_TYPES = {'pm': 'Önleyici bakım', 'calibration': 'Kalibrasyon', 'verification': 'Doğrulama'}
    UNITS = {'day': 'gün', 'week': 'hafta', 'month': 'ay', 'year': 'yıl'}
    BASES = {'time': 'Takvim', 'counter': 'Sayaç'}

    FIELDS = ('asset_id', 'plan_type', 'title', 'basis', 'interval_value', 'interval_unit',
              'counter_interval', 'lead_days', 'tolerance_days', 'assignee', 'is_active',
              'instructions', 'last_done_at', 'next_due_at')

    @staticmethod
    def sanitize(data: dict) -> dict:
        return {
            'asset_id': v.integer(data.get('asset_id'), 0, None, 0),
            'plan_type': v.enum(data.get('plan_type'), ScheduleRepo.PLAN_TYPES, 'pm'),
            'title': v.text(data.get('title'), 191),
            'basis': v.enum(data.get('basis'), ScheduleRepo.BASES, 'time'),
            'interval_value': v.integer(data.get('interval_value'), 1, None, 1),
            'interval_unit': v.enum(data.get('interval_unit'), ScheduleRepo.UNITS, 'month'),
            'counter_interval': v.integer(data.get('counter_interval'), 0, None, 0),
            'lead_days': v.integer(data.get('lead_days'), 0, None,
                                   v.integer(store.setting('default_lead_days', 14), 0, None, 14)),
            'tolerance_days': v.integer(data.get('tolerance_days'), 0, None, 0),
            'assignee': v.text(data.get('assignee'), 80),
            'is_active': 0 if not data.get('is_active') else 1,
            'instructions': v.multiline(data.get('instructions')),
            'last_done_at': v.stamp(data.get('last_done_at')),
            'next_due_at': v.stamp(data.get('next_due_at')),
        }

    @staticmethod
    def get(conn, plan_id):
        return _row(conn.execute('SELECT * FROM schedule WHERE id = ?', (int(plan_id or 0),)))

    @staticmethod
    def query(conn, asset_id=0, plan_type='', basis='', is_active=None) -> list:
        where, args = ['1=1'], []
        if asset_id:
            where.append('asset_id = ?')
            args.append(int(asset_id))
        if plan_type:
            where.append('plan_type = ?')
            args.append(plan_type)
        if basis:
            where.append('basis = ?')
            args.append(basis)
        if is_active is not None:
            where.append('is_active = ?')
            args.append(1 if is_active else 0)
        sql = ('SELECT * FROM schedule WHERE %s ORDER BY next_due_at IS NULL, next_due_at ASC'
               % ' AND '.join(where))
        return _rows(conn.execute(sql, args))

    @staticmethod
    def count_due(conn, overdue_only=False) -> int:
        """Vadesi gelen ya da gecen aktif plan sayisi."""
        rows = ScheduleRepo.query(conn, is_active=True)
        now = v.parse(v.now())
        total = 0
        for plan in rows:
            due = v.parse(plan['next_due_at'])
            if not due:
                continue
            if overdue_only:
                if (now - due).days > int(plan['tolerance_days']):
                    total += 1
            elif (due - now).days <= int(plan['lead_days']):
                total += 1
        return total

    @staticmethod
    def validate(conn, clean: dict) -> None:
        asset = AssetRepo.get(conn, clean['asset_id'])
        if not asset:
            raise MihenkError('Bu plan için mevcut bir varlık seçin.')
        if not clean['title']:
            raise MihenkError('Plan başlığı zorunludur.')
        if clean['basis'] == 'counter':
            if clean['counter_interval'] < 1:
                raise MihenkError('Sayaç tabanlı plan bir sayaç aralığı gerektirir.')
            if not asset['counter_unit']:
                raise MihenkError('Bu varlıkta sayaç birimi tanımlı değil, '
                                  'bu yüzden sayaç tabanlı plan taşıyamaz.')

    @staticmethod
    def compute_next_due(plan: dict, base) -> str:
        return v.add_interval(base, plan['interval_value'], plan['interval_unit'])

    @staticmethod
    def create(conn, data: dict) -> int:
        clean = ScheduleRepo.sanitize(data)
        ScheduleRepo.validate(conn, clean)
        if not clean['next_due_at']:
            clean['next_due_at'] = ScheduleRepo.compute_next_due(clean, clean['last_done_at'] or v.now())
        audit.intent(conn, 'schedule', 0, 'create',
                     {'asset_id': clean['asset_id'], 'plan_type': clean['plan_type']})

        last_counter = next_counter = 0
        if clean['basis'] == 'counter':
            asset = AssetRepo.get(conn, clean['asset_id'])
            last_counter = int(asset['counter_value']) if asset else 0
            next_counter = last_counter + clean['counter_interval']

        stamp = v.now()
        columns = list(ScheduleRepo.FIELDS) + ['last_done_counter', 'next_due_counter',
                                               'created_at', 'updated_at']
        args = [clean[f] for f in ScheduleRepo.FIELDS] + [last_counter, next_counter, stamp, stamp]
        cur = conn.execute('INSERT INTO schedule (%s) VALUES (%s)'
                           % (', '.join(columns), ', '.join('?' * len(columns))), args)
        plan_id = int(cur.lastrowid)
        audit.result(conn, 'schedule', plan_id, 'create', {'asset_id': clean['asset_id']})
        return plan_id

    @staticmethod
    def update(conn, plan_id, data: dict) -> None:
        plan_id = int(plan_id)
        if not ScheduleRepo.get(conn, plan_id):
            raise MihenkError('Plan bulunamadı.')
        clean = ScheduleRepo.sanitize(data)
        ScheduleRepo.validate(conn, clean)
        if not clean['next_due_at']:
            clean['next_due_at'] = ScheduleRepo.compute_next_due(clean, clean['last_done_at'] or v.now())
        audit.intent(conn, 'schedule', plan_id, 'update', {'plan_type': clean['plan_type']})
        assignments = ', '.join('%s = ?' % f for f in ScheduleRepo.FIELDS)
        args = [clean[f] for f in ScheduleRepo.FIELDS] + [v.now(), plan_id]
        conn.execute('UPDATE schedule SET %s, updated_at = ? WHERE id = ?' % assignments, args)
        audit.result(conn, 'schedule', plan_id, 'update', {'plan_type': clean['plan_type']})

    @staticmethod
    def mark_done(conn, plan_id, done_at='') -> None:
        """Plani yerine getirilmis sayar ve sonraki vadeye tasir."""
        plan_id = int(plan_id)
        plan = ScheduleRepo.get(conn, plan_id)
        if not plan:
            raise MihenkError('Plan bulunamadı.')
        done_at = v.stamp(done_at) or v.now()
        next_due = ScheduleRepo.compute_next_due(plan, done_at)
        audit.intent(conn, 'schedule', plan_id, 'mark_done', {'done_at': done_at})
        if plan['basis'] == 'counter':
            asset = AssetRepo.get(conn, int(plan['asset_id']))
            counter = int(asset['counter_value']) if asset else int(plan['last_done_counter'])
            conn.execute('UPDATE schedule SET last_done_at = ?, next_due_at = ?, last_done_counter = ?,'
                         ' next_due_counter = ?, updated_at = ? WHERE id = ?',
                         (done_at, next_due, counter, counter + int(plan['counter_interval']),
                          v.now(), plan_id))
        else:
            conn.execute('UPDATE schedule SET last_done_at = ?, next_due_at = ?, updated_at = ? WHERE id = ?',
                         (done_at, next_due, v.now(), plan_id))
        audit.result(conn, 'schedule', plan_id, 'mark_done', {'done_at': done_at, 'next_due_at': next_due})

    @staticmethod
    def set_active(conn, plan_id, active: bool) -> None:
        plan_id = int(plan_id)
        audit.intent(conn, 'schedule', plan_id, 'set_active', {'active': 1 if active else 0})
        conn.execute('UPDATE schedule SET is_active = ?, updated_at = ? WHERE id = ?',
                     (1 if active else 0, v.now(), plan_id))
        audit.result(conn, 'schedule', plan_id, 'set_active', {'active': 1 if active else 0})

    @staticmethod
    def delete(conn, plan_id) -> None:
        """Plani siler. Uretilmis kayitlar kendi gecmislerini korur."""
        plan_id = int(plan_id)
        audit.intent(conn, 'schedule', plan_id, 'delete')
        from mihenk_checklist import ChecklistTemplate
        ChecklistTemplate.delete_for_plan(conn, plan_id)
        conn.execute('DELETE FROM schedule WHERE id = ?', (plan_id,))
        audit.result(conn, 'schedule', plan_id, 'delete')


# ====================================================================== talep
class RequestRepo:
    """Sahadan gelen bildirimler. Is emrinden ayri tutulur."""

    SEVERITIES = {'low': 'Düşük', 'normal': 'Normal', 'high': 'Yüksek',
                  'stops_production': 'Üretimi durduruyor'}

    @staticmethod
    def get(conn, request_id):
        return _row(conn.execute('SELECT * FROM request WHERE id = ?', (int(request_id or 0),)))

    @staticmethod
    def query(conn, asset_id=0, status='') -> list:
        where, args = ['1=1'], []
        if asset_id:
            where.append('asset_id = ?')
            args.append(int(asset_id))
        if status:
            where.append('status = ?')
            args.append(status)
        sql = 'SELECT * FROM request WHERE %s ORDER BY reported_at DESC, id DESC' % ' AND '.join(where)
        return _rows(conn.execute(sql, args))

    @staticmethod
    def count(conn, status='') -> int:
        if status:
            row = conn.execute('SELECT COUNT(*) AS c FROM request WHERE status = ?', (status,)).fetchone()
        else:
            row = conn.execute('SELECT COUNT(*) AS c FROM request').fetchone()
        return int(row['c'])

    @staticmethod
    def create(conn, data: dict) -> int:
        asset_id = v.integer(data.get('asset_id'), 0, None, 0)
        summary = v.text(data.get('summary'), 191)
        if not asset_id or not AssetRepo.get(conn, asset_id):
            raise MihenkError('Mevcut bir varlık seçin.')
        if not summary:
            raise MihenkError('Kısa bir özet zorunludur.')
        audit.intent(conn, 'request', 0, 'create', {'asset_id': asset_id}, '', 'open')
        cur = conn.execute(
            'INSERT INTO request (asset_id, reported_by, reported_at, summary, description, severity, status)'
            ' VALUES (?, ?, ?, ?, ?, ?, ?)',
            (asset_id, _operator(), v.now(), summary, v.multiline(data.get('description')),
             v.enum(data.get('severity'), RequestRepo.SEVERITIES, 'normal'), 'open'))
        request_id = int(cur.lastrowid)
        audit.result(conn, 'request', request_id, 'create', {'asset_id': asset_id}, '', 'open')
        return request_id

    @staticmethod
    def transition(conn, request_id, target: str, data=None) -> None:
        request_id = int(request_id)
        row = RequestRepo.get(conn, request_id)
        if not row:
            raise MihenkError('Talep bulunamadı.')
        extra = {}
        if data and data.get('rejection_reason') is not None:
            extra['rejection_reason'] = v.multiline(data.get('rejection_reason'))
        states.guard(conn, 'request', row, target, extra)
        audit.intent(conn, 'request', request_id, 'transition', extra, row['status'], target)
        sets, args = ['status = ?'], [target]
        if 'rejection_reason' in extra:
            sets.append('rejection_reason = ?')
            args.append(extra['rejection_reason'])
        if target == 'closed':
            sets.append('closed_at = ?')
            args.append(v.now())
        args.append(request_id)
        conn.execute('UPDATE request SET %s WHERE id = ?' % ', '.join(sets), args)
        audit.result(conn, 'request', request_id, 'transition', extra, row['status'], target)

    @staticmethod
    def convert(conn, request_id, data=None) -> int:
        """Degerlendirilmis talebi is emrine cevirir."""
        request_id = int(request_id)
        row = RequestRepo.get(conn, request_id)
        if not row:
            raise MihenkError('Talep bulunamadı.')
        if row['status'] != 'triaged':
            raise MihenkError('Dönüştürmeden önce talebi değerlendirin.')
        data = data or {}
        work_order_id = WorkOrderRepo.create(conn, {
            'asset_id': int(row['asset_id']),
            'request_id': request_id,
            'wo_type': 'corrective',
            'title': v.text(data.get('title') or row['summary'], 191),
            'priority': 'high' if row['severity'] == 'stops_production' else 'normal',
            'assigned_to': data.get('assigned_to', ''),
        })
        RequestRepo.transition(conn, request_id, 'converted')
        conn.execute('UPDATE request SET work_order_id = ? WHERE id = ?', (work_order_id, request_id))
        return work_order_id


# ====================================================================== is emri
class WorkOrderRepo:
    """Is emirleri."""

    TYPES = {'preventive': 'Önleyici', 'corrective': 'Düzeltici', 'improvement': 'İyileştirme'}
    PRIORITIES = {'low': 'Düşük', 'normal': 'Normal', 'high': 'Yüksek'}

    FIELDS = ('asset_id', 'schedule_id', 'request_id', 'wo_type', 'title', 'priority', 'assigned_to',
              'planned_start', 'planned_end', 'actual_start', 'actual_end', 'downtime_minutes',
              'labor_minutes', 'work_done', 'root_cause', 'hold_reason')

    @staticmethod
    def sanitize(data: dict) -> dict:
        return {
            'asset_id': v.integer(data.get('asset_id'), 0, None, 0),
            'schedule_id': v.integer(data.get('schedule_id'), 0, None, 0),
            'request_id': v.integer(data.get('request_id'), 0, None, 0),
            'wo_type': v.enum(data.get('wo_type'), WorkOrderRepo.TYPES, 'corrective'),
            'title': v.text(data.get('title'), 191),
            'priority': v.enum(data.get('priority'), WorkOrderRepo.PRIORITIES, 'normal'),
            'assigned_to': v.text(data.get('assigned_to'), 80),
            'planned_start': v.stamp(data.get('planned_start')),
            'planned_end': v.stamp(data.get('planned_end')),
            'actual_start': v.stamp(data.get('actual_start')),
            'actual_end': v.stamp(data.get('actual_end')),
            'downtime_minutes': v.integer(data.get('downtime_minutes'), 0, None, 0),
            'labor_minutes': v.integer(data.get('labor_minutes'), 0, None, 0),
            'work_done': v.multiline(data.get('work_done')),
            'root_cause': v.multiline(data.get('root_cause')),
            'hold_reason': v.multiline(data.get('hold_reason')),
        }

    @staticmethod
    def get(conn, work_order_id):
        return _row(conn.execute('SELECT * FROM work_order WHERE id = ?', (int(work_order_id or 0),)))

    @staticmethod
    def query(conn, asset_id=0, status='', wo_type='', open_only=False) -> list:
        where, args = ['1=1'], []
        if asset_id:
            where.append('asset_id = ?')
            args.append(int(asset_id))
        if status:
            where.append('status = ?')
            args.append(status)
        if wo_type:
            where.append('wo_type = ?')
            args.append(wo_type)
        if open_only:
            where.append("status NOT IN ('closed', 'cancelled')")
        sql = ('SELECT * FROM work_order WHERE %s ORDER BY planned_start IS NULL, planned_start ASC, id DESC'
               % ' AND '.join(where))
        return _rows(conn.execute(sql, args))

    @staticmethod
    def count(conn, open_only=True) -> int:
        sql = 'SELECT COUNT(*) AS c FROM work_order'
        if open_only:
            sql += " WHERE status NOT IN ('closed', 'cancelled')"
        return int(conn.execute(sql).fetchone()['c'])

    @staticmethod
    def has_open_for_schedule(conn, schedule_id) -> bool:
        row = conn.execute("SELECT COUNT(*) AS c FROM work_order WHERE schedule_id = ?"
                           " AND status NOT IN ('closed', 'cancelled')", (int(schedule_id),)).fetchone()
        return int(row['c']) > 0

    @staticmethod
    def create(conn, data: dict) -> int:
        clean = WorkOrderRepo.sanitize(data)
        if not clean['asset_id'] or not AssetRepo.get(conn, clean['asset_id']):
            raise MihenkError('Mevcut bir varlık seçin.')
        if not clean['title']:
            raise MihenkError('İş emri başlığı zorunludur.')
        audit.intent(conn, 'work_order', 0, 'create', {'asset_id': clean['asset_id']}, '', 'new')
        stamp = v.now()
        columns = list(WorkOrderRepo.FIELDS) + ['status', 'created_at', 'updated_at']
        args = [clean[f] for f in WorkOrderRepo.FIELDS] + ['new', stamp, stamp]
        cur = conn.execute('INSERT INTO work_order (%s) VALUES (%s)'
                           % (', '.join(columns), ', '.join('?' * len(columns))), args)
        work_order_id = int(cur.lastrowid)
        audit.result(conn, 'work_order', work_order_id, 'create', {'asset_id': clean['asset_id']}, '', 'new')
        return work_order_id

    @staticmethod
    def update(conn, work_order_id, data: dict) -> None:
        work_order_id = int(work_order_id)
        current = WorkOrderRepo.get(conn, work_order_id)
        if not current:
            raise MihenkError('İş emri bulunamadı.')
        if current['status'] in ('closed', 'cancelled'):
            raise MihenkError('Kapatılmış veya iptal edilmiş bir iş emri artık düzenlenemez.')
        clean = WorkOrderRepo.sanitize(data)
        if not clean['title']:
            raise MihenkError('İş emri başlığı zorunludur.')
        audit.intent(conn, 'work_order', work_order_id, 'update', {'title': clean['title']})
        assignments = ', '.join('%s = ?' % f for f in WorkOrderRepo.FIELDS)
        args = [clean[f] for f in WorkOrderRepo.FIELDS] + [v.now(), work_order_id]
        conn.execute('UPDATE work_order SET %s, updated_at = ? WHERE id = ?' % assignments, args)
        audit.result(conn, 'work_order', work_order_id, 'update', {'title': clean['title']})

    @staticmethod
    def transition(conn, work_order_id, target: str, data=None) -> None:
        work_order_id = int(work_order_id)
        row = WorkOrderRepo.get(conn, work_order_id)
        if not row:
            raise MihenkError('İş emri bulunamadı.')
        data = data or {}
        extra = {}
        for field in ('work_done', 'root_cause', 'hold_reason'):
            if data.get(field) is not None:
                extra[field] = v.multiline(data[field])
        for field in ('labor_minutes', 'downtime_minutes'):
            if data.get(field) is not None:
                extra[field] = v.integer(data[field], 0, None, 0)
        for field in ('actual_start', 'actual_end'):
            if data.get(field) is not None:
                parsed = v.stamp(data[field])
                if parsed:
                    extra[field] = parsed
        if data.get('assigned_to') is not None:
            extra['assigned_to'] = v.text(data['assigned_to'], 80)

        if target == 'in_progress' and not extra.get('actual_start') and not row['actual_start']:
            extra['actual_start'] = v.now()
        if target == 'completed' and not extra.get('actual_end') and not row['actual_end']:
            extra['actual_end'] = v.now()

        states.guard(conn, 'work_order', row, target, extra)

        if target == 'completed':
            # Kritik kontrol adimlari isaretlenmeden is emri tamamlanamaz.
            from mihenk_checklist import WorkOrderChecklist
            blocking = WorkOrderChecklist.blocking_reason(conn, work_order_id)
            if blocking:
                raise MihenkError(blocking)

        audit.intent(conn, 'work_order', work_order_id, 'transition', extra, row['status'], target)

        sets = ['%s = ?' % f for f in extra] + ['status = ?', 'updated_at = ?']
        args = list(extra.values()) + [target, v.now()]
        if target == 'closed':
            sets += ['closed_by = ?', 'closed_at = ?']
            args += [_operator(), v.now()]
        args.append(work_order_id)
        conn.execute('UPDATE work_order SET %s WHERE id = ?' % ', '.join(sets), args)
        audit.result(conn, 'work_order', work_order_id, 'transition', extra, row['status'], target)

        if target == 'completed' and int(row['schedule_id']):
            ScheduleRepo.mark_done(conn, int(row['schedule_id']),
                                   extra.get('actual_end') or row['actual_end'] or v.now())


# ====================================================================== kalibrasyon
class CalibrationRepo:
    """Kalibrasyon ve dogrulama kayitlari."""

    RESULTS = {'pass': 'Uygun', 'conditional': 'Şartlı', 'fail': 'Uygunsuz'}
    RECORD_TYPES = {'calibration': 'Kalibrasyon', 'verification': 'Doğrulama'}

    RESULT_FIELDS = ('performed_at', 'performed_by', 'external_body', 'accreditation_scope',
                     'certificate_no', 'certificate_path', 'traceability_ref', 'measurement_points',
                     'tolerance_spec', 'max_deviation', 'uncertainty', 'result', 'usage_limit', 'notes')

    @staticmethod
    def get(conn, record_id):
        return _row(conn.execute('SELECT * FROM calibration WHERE id = ?', (int(record_id or 0),)))

    @staticmethod
    def query(conn, asset_id=0, record_type='', status='', result='', open_only=False) -> list:
        where, args = ['1=1'], []
        if asset_id:
            where.append('asset_id = ?')
            args.append(int(asset_id))
        if record_type:
            where.append('record_type = ?')
            args.append(record_type)
        if status:
            where.append('status = ?')
            args.append(status)
        if result:
            where.append('result = ?')
            args.append(result)
        if open_only:
            where.append("status NOT IN ('closed', 'cancelled')")
        sql = ('SELECT * FROM calibration WHERE %s ORDER BY performed_at IS NULL, performed_at DESC, id DESC'
               % ' AND '.join(where))
        return _rows(conn.execute(sql, args))

    @staticmethod
    def count(conn, open_only=True) -> int:
        sql = 'SELECT COUNT(*) AS c FROM calibration'
        if open_only:
            sql += " WHERE status NOT IN ('closed', 'cancelled')"
        return int(conn.execute(sql).fetchone()['c'])

    @staticmethod
    def has_open_for_schedule(conn, schedule_id) -> bool:
        row = conn.execute("SELECT COUNT(*) AS c FROM calibration WHERE schedule_id = ?"
                           " AND status NOT IN ('closed', 'cancelled')", (int(schedule_id),)).fetchone()
        return int(row['c']) > 0

    @staticmethod
    def last_valid_datetime(conn, asset_id, before_id=0):
        """Uygunlugu gercekten kanitlayan son kaydin zamani."""
        row = conn.execute(
            "SELECT performed_at FROM calibration WHERE asset_id = ? AND status = 'closed'"
            " AND result IN ('pass', 'conditional') AND performed_at IS NOT NULL AND id <> ?"
            ' ORDER BY performed_at DESC LIMIT 1',
            (int(asset_id), int(before_id or 0))).fetchone()
        return row['performed_at'] if row else None

    @staticmethod
    def create(conn, data: dict) -> int:
        asset_id = v.integer(data.get('asset_id'), 0, None, 0)
        if not asset_id or not AssetRepo.get(conn, asset_id):
            raise MihenkError('Mevcut bir varlık seçin.')
        audit.intent(conn, 'calibration', 0, 'create', {'asset_id': asset_id}, '', 'planned')
        stamp = v.now()
        cur = conn.execute(
            'INSERT INTO calibration (asset_id, schedule_id, record_type, tolerance_spec, status,'
            ' created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (asset_id, v.integer(data.get('schedule_id'), 0, None, 0),
             v.enum(data.get('record_type'), CalibrationRepo.RECORD_TYPES, 'calibration'),
             v.text(data.get('tolerance_spec'), 191), 'planned', stamp, stamp))
        record_id = int(cur.lastrowid)
        audit.result(conn, 'calibration', record_id, 'create', {'asset_id': asset_id}, '', 'planned')
        return record_id

    @staticmethod
    def _keep_certificate(data: dict) -> str:
        """Sertifika dosyasini veri klasorune kopyalar; zaten kopyalanmissa dokunmaz.

        Yalnizca disk yolu tutmak kirilgandir; denetim kaniti olacak dosya
        kutugun yaninda durmali.
        """
        raw = v.text(data.get('certificate_path'), 500)
        if not raw or raw.startswith('certificates/'):
            return raw
        import mihenk_export as export
        return export.store_certificate(raw, int(data.get('_record_id') or 0))

    @staticmethod
    def sanitize_result(data: dict) -> dict:
        points = v.measurement_points(data.get('points'))
        verdict = v.evaluate_points(points)
        result = v.enum(data.get('result'), CalibrationRepo.RESULTS, '')
        if not result and verdict['verdict'] != 'unknown':
            result = verdict['verdict']
        return {
            'performed_at': v.stamp(data.get('performed_at')),
            'performed_by': v.text(data.get('performed_by') or _operator(), 80),
            'external_body': v.text(data.get('external_body'), 191),
            'accreditation_scope': v.text(data.get('accreditation_scope'), 191),
            'certificate_no': v.text(data.get('certificate_no'), 128),
            'certificate_path': CalibrationRepo._keep_certificate(data),
            'traceability_ref': v.text(data.get('traceability_ref'), 191),
            'measurement_points': v.dump_points(points),
            'tolerance_spec': v.text(data.get('tolerance_spec'), 191),
            'max_deviation': verdict['max_deviation'],
            'uncertainty': v.text(data.get('uncertainty'), 64),
            'result': result,
            'usage_limit': v.multiline(data.get('usage_limit')),
            'notes': v.multiline(data.get('notes')),
        }

    @staticmethod
    def save_result(conn, record_id, data: dict) -> None:
        """Olculen sonucu yazar.

        Uygunsuz sonuc ayni islemde varligi karantinaya alir ve etki
        degerlendirmesini acar; ikisi hicbir zaman birbirinden ayrilmaz.
        """
        record_id = int(record_id)
        row = CalibrationRepo.get(conn, record_id)
        if not row:
            raise MihenkError('Kayıt bulunamadı.')
        if row['status'] in ('closed', 'cancelled'):
            raise MihenkError('Bu kayıt kapalı ve artık düzenlenemez.')
        data = dict(data or {})
        data['_record_id'] = record_id
        clean = CalibrationRepo.sanitize_result(data)

        if row['status'] == 'planned':
            CalibrationRepo.transition(conn, record_id, 'in_progress')
            row = CalibrationRepo.get(conn, record_id)

        if row['status'] == 'result_entered':
            # Kapatilmamis bir sonuc duzeltilebilir: ayni duruma yeniden yazilir,
            # zorunlu alanlar yine denetlenir.
            states.check_required('calibration', 'result_entered', row, clean)
        else:
            states.guard(conn, 'calibration', row, 'result_entered', clean)
        audit.intent(conn, 'calibration', record_id, 'save_result', {'result': clean['result']},
                     row['status'], 'result_entered')

        assignments = ', '.join('%s = ?' % f for f in CalibrationRepo.RESULT_FIELDS)
        args = [clean[f] for f in CalibrationRepo.RESULT_FIELDS] + ['result_entered', v.now(), record_id]
        conn.execute('UPDATE calibration SET %s, status = ?, updated_at = ? WHERE id = ?' % assignments, args)
        audit.result(conn, 'calibration', record_id, 'save_result', {'result': clean['result']},
                     row['status'], 'result_entered')

        if clean['result'] == 'fail':
            fresh = CalibrationRepo.get(conn, record_id)
            impact_id = ImpactRepo.open_for_calibration(conn, fresh)
            conn.execute('UPDATE calibration SET impact_id = ? WHERE id = ?', (impact_id, record_id))
            asset = AssetRepo.get(conn, int(row['asset_id']))
            if asset and asset['status'] not in ('quarantined', 'retired'):
                AssetRepo.transition(conn, int(row['asset_id']), 'quarantined',
                                     '#%d numaralı başarısız kayıt sonrası otomatik karantina' % record_id)

    @staticmethod
    def transition(conn, record_id, target: str, data=None) -> None:
        record_id = int(record_id)
        row = CalibrationRepo.get(conn, record_id)
        if not row:
            raise MihenkError('Kayıt bulunamadı.')
        states.guard(conn, 'calibration', row, target, data or {})
        audit.intent(conn, 'calibration', record_id, 'transition', data or {}, row['status'], target)

        sets, args = ['status = ?', 'updated_at = ?'], [target, v.now()]
        if target == 'closed' and int(row['schedule_id']):
            plan = ScheduleRepo.get(conn, int(row['schedule_id']))
            if plan:
                sets.append('next_due_at = ?')
                args.append(ScheduleRepo.compute_next_due(plan, row['performed_at'] or v.now()))
        args.append(record_id)
        conn.execute('UPDATE calibration SET %s WHERE id = ?' % ', '.join(sets), args)
        audit.result(conn, 'calibration', record_id, 'transition', data or {}, row['status'], target)

        if target == 'closed' and int(row['schedule_id']) and row['result'] in ('pass', 'conditional'):
            ScheduleRepo.mark_done(conn, int(row['schedule_id']), row['performed_at'] or v.now())

    @staticmethod
    def points(row: dict) -> list:
        return v.load_points(row.get('measurement_points'))


# ====================================================================== etki degerlendirmesi
class ImpactRepo:
    """Etki degerlendirmeleri.

    Uygunsuz bir kalibrasyon yalnizca cihazin sorunu degildir: o cihazin son
    gecerli sonucundan beri olctugu her sey supheye duser. Bu kayit o araligi
    tasir.
    """

    DECISIONS = {
        'no_impact': 'Etki yok',
        'rework': 'Yeniden işleme',
        'recall': 'Geri çağırma',
        'release_with_justification': 'Gerekçeli serbest bırakma',
    }

    FIELDS = ('affected_from', 'affected_to', 'affected_scope', 'evaluation', 'decision',
              'corrective_action')

    @staticmethod
    def get(conn, impact_id):
        return _row(conn.execute('SELECT * FROM impact WHERE id = ?', (int(impact_id or 0),)))

    @staticmethod
    def for_calibration(conn, calibration_id):
        return _row(conn.execute('SELECT * FROM impact WHERE calibration_id = ? ORDER BY id DESC LIMIT 1',
                                 (int(calibration_id),)))

    @staticmethod
    def open_count_for_asset(conn, asset_id) -> int:
        return states.open_impact_count(conn, asset_id)

    @staticmethod
    def count(conn, status='open') -> int:
        if status:
            row = conn.execute('SELECT COUNT(*) AS c FROM impact WHERE status = ?', (status,)).fetchone()
        else:
            row = conn.execute('SELECT COUNT(*) AS c FROM impact').fetchone()
        return int(row['c'])

    @staticmethod
    def query(conn, status='', asset_id=0) -> list:
        where, args = ['1=1'], []
        if status:
            where.append('status = ?')
            args.append(status)
        if asset_id:
            where.append('asset_id = ?')
            args.append(int(asset_id))
        sql = 'SELECT * FROM impact WHERE %s ORDER BY opened_at DESC, id DESC' % ' AND '.join(where)
        return _rows(conn.execute(sql, args))

    @staticmethod
    def sanitize(data: dict) -> dict:
        return {
            'affected_from': v.stamp(data.get('affected_from')),
            'affected_to': v.stamp(data.get('affected_to')),
            'affected_scope': v.multiline(data.get('affected_scope')),
            'evaluation': v.multiline(data.get('evaluation')),
            'decision': v.enum(data.get('decision'), ImpactRepo.DECISIONS, ''),
            'corrective_action': v.multiline(data.get('corrective_action')),
        }

    @staticmethod
    def open_for_calibration(conn, calibration: dict) -> int:
        """Uygunsuz kayit icin degerlendirme acar; aralik son gecerli kayittan baslar."""
        existing = ImpactRepo.for_calibration(conn, int(calibration['id']))
        if existing:
            return int(existing['id'])
        asset_id = int(calibration['asset_id'])
        start = CalibrationRepo.last_valid_datetime(conn, asset_id, int(calibration['id']))
        if not start:
            asset = AssetRepo.get(conn, asset_id)
            if asset:
                start = (asset['commissioned_on'] + ' 00:00:00') if asset['commissioned_on'] else asset['created_at']
        end = calibration['performed_at'] or v.now()

        payload = {'calibration_id': int(calibration['id']), 'asset_id': asset_id,
                   'affected_from': start, 'affected_to': end}
        audit.intent(conn, 'impact', 0, 'open', payload, '', 'open')
        cur = conn.execute(
            'INSERT INTO impact (calibration_id, asset_id, opened_at, opened_by, affected_from,'
            ' affected_to, status) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (int(calibration['id']), asset_id, v.now(), _operator(), start, end, 'open'))
        impact_id = int(cur.lastrowid)
        audit.result(conn, 'impact', impact_id, 'open', payload, '', 'open')
        return impact_id

    @staticmethod
    def save(conn, impact_id, data: dict) -> None:
        impact_id = int(impact_id)
        row = ImpactRepo.get(conn, impact_id)
        if not row:
            raise MihenkError('Etki değerlendirmesi bulunamadı.')
        if row['status'] == 'closed':
            raise MihenkError('Kapatılmış bir etki değerlendirmesi artık düzenlenemez.')
        clean = ImpactRepo.sanitize(data)
        audit.intent(conn, 'impact', impact_id, 'save', {'decision': clean['decision']})
        assignments = ', '.join('%s = ?' % f for f in ImpactRepo.FIELDS)
        args = [clean[f] for f in ImpactRepo.FIELDS] + [impact_id]
        conn.execute('UPDATE impact SET %s WHERE id = ?' % assignments, args)
        audit.result(conn, 'impact', impact_id, 'save', {'decision': clean['decision']})

    @staticmethod
    def close(conn, impact_id, data: dict) -> None:
        impact_id = int(impact_id)
        row = ImpactRepo.get(conn, impact_id)
        if not row:
            raise MihenkError('Etki değerlendirmesi bulunamadı.')
        clean = ImpactRepo.sanitize(data)
        states.guard(conn, 'impact', row, 'closed', clean)
        ImpactRepo.save(conn, impact_id, data)
        audit.intent(conn, 'impact', impact_id, 'close', {'decision': clean['decision']}, 'open', 'closed')
        conn.execute('UPDATE impact SET status = ?, closed_by = ?, closed_at = ? WHERE id = ?',
                     ('closed', _operator(), v.now(), impact_id))
        audit.result(conn, 'impact', impact_id, 'close', {'decision': clean['decision']}, 'open', 'closed')
