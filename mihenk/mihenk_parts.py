# -*- coding: utf-8 -*-
"""Yedek parca kutugu ve stok hareketleri.

Stok dogrudan yazilmaz: her degisim bir hareket satiri birakir ve bakiye o
satirin icinde saklanir. Boylece "stok neden bu seviyede" sorusunun cevabi
her zaman kayitta durur.
"""
from __future__ import annotations

import mihenk_audit as audit
import mihenk_store as store
import mihenk_validate as v
from mihenk_validate import MihenkError

UNITS = ('adet', 'metre', 'kg', 'litre', 'paket', 'takım')

REASONS = {
    'consume': 'İş emrinde kullanıldı',
    'receive': 'Giriş / satın alma',
    'return': 'İade',
    'count': 'Sayım düzeltmesi',
    'scrap': 'Hurda',
}


def _operator() -> str:
    return v.text(store.setting('operator', '') or '', 80)


def _rows(cursor) -> list:
    return [dict(r) for r in cursor.fetchall()]


def _row(cursor):
    found = cursor.fetchone()
    return dict(found) if found else None


class PartRepo:
    """Parca kutugu."""

    FIELDS = ('code', 'name', 'unit', 'min_stock', 'location_text', 'supplier', 'unit_cost',
              'is_active', 'notes')

    @staticmethod
    def sanitize(data: dict) -> dict:
        """Form girdisini kayit bicimine getirir. stock burada yok, bilerek."""
        cost = v.number(data.get('unit_cost'))
        minimum = v.number(data.get('min_stock'))
        return {
            'code': v.text(data.get('code'), 64),
            'name': v.text(data.get('name'), 191),
            'unit': v.text(data.get('unit'), 24) or 'adet',
            'min_stock': max(0.0, minimum if minimum is not None else 0.0),
            'location_text': v.text(data.get('location_text'), 191),
            'supplier': v.text(data.get('supplier'), 191),
            'unit_cost': max(0.0, cost if cost is not None else 0.0),
            'is_active': 0 if not data.get('is_active') else 1,
            'notes': v.multiline(data.get('notes')),
        }

    @staticmethod
    def get(conn, part_id):
        return _row(conn.execute('SELECT * FROM part WHERE id = ?', (int(part_id or 0),)))

    @staticmethod
    def by_code(conn, code):
        return _row(conn.execute('SELECT * FROM part WHERE code = ?', (v.text(code, 64),)))

    @staticmethod
    def query(conn, search='', low_only=False, active_only=True) -> list:
        where, args = ['1=1'], []
        if active_only:
            where.append('is_active = 1')
        if low_only:
            where.append('min_stock > 0 AND stock <= min_stock')
        if search:
            like = '%' + str(search).strip() + '%'
            where.append('(code LIKE ? OR name LIKE ? OR supplier LIKE ? OR location_text LIKE ?)')
            args.extend([like, like, like, like])
        sql = ('SELECT * FROM part WHERE %s ORDER BY code COLLATE NOCASE' % ' AND '.join(where))
        return _rows(conn.execute(sql, args))

    @staticmethod
    def count(conn, low_only=False) -> int:
        sql = 'SELECT COUNT(*) AS c FROM part WHERE is_active = 1'
        if low_only:
            sql += ' AND min_stock > 0 AND stock <= min_stock'
        return int(conn.execute(sql).fetchone()['c'])

    @staticmethod
    def low_stock(conn) -> list:
        """Asgari seviyenin altina dusmus parcalar."""
        return PartRepo.query(conn, low_only=True)

    @staticmethod
    def stock_value(conn) -> float:
        """Eldeki stogun birim maliyete gore toplami."""
        row = conn.execute('SELECT COALESCE(SUM(stock * unit_cost), 0) AS v FROM part'
                           ' WHERE is_active = 1').fetchone()
        return float(row['v'] or 0.0)

    @staticmethod
    def options(conn) -> list:
        out = []
        for row in conn.execute('SELECT id, code, name, stock, unit FROM part WHERE is_active = 1'
                                ' ORDER BY code COLLATE NOCASE').fetchall():
            out.append((int(row['id']), '%s - %s (%s %s)'
                        % (row['code'], row['name'], _fmt(row['stock']), row['unit'])))
        return out

    @staticmethod
    def create(conn, data: dict) -> int:
        clean = PartRepo.sanitize(data)
        if not clean['code']:
            raise MihenkError('Parça kodu zorunludur.')
        if not clean['name']:
            raise MihenkError('Parça adı zorunludur.')
        if PartRepo.by_code(conn, clean['code']):
            raise MihenkError('Bu kodu başka bir parça kullanıyor.')

        opening = v.number(data.get('stock'))
        opening = max(0.0, opening if opening is not None else 0.0)
        audit.intent(conn, 'part', 0, 'create', {'code': clean['code']})
        stamp = v.now()
        columns = list(PartRepo.FIELDS) + ['stock', 'created_at', 'updated_at']
        args = [clean[f] for f in PartRepo.FIELDS] + [0.0, stamp, stamp]
        cur = conn.execute('INSERT INTO part (%s) VALUES (%s)'
                           % (', '.join(columns), ', '.join('?' * len(columns))), args)
        part_id = int(cur.lastrowid)
        audit.result(conn, 'part', part_id, 'create', {'code': clean['code']})
        if opening:
            PartRepo.move(conn, part_id, opening, 'count', note='Açılış stoğu')
        return part_id

    @staticmethod
    def update(conn, part_id, data: dict) -> None:
        part_id = int(part_id)
        if not PartRepo.get(conn, part_id):
            raise MihenkError('Parça bulunamadı.')
        clean = PartRepo.sanitize(data)
        if not clean['code']:
            raise MihenkError('Parça kodu zorunludur.')
        if not clean['name']:
            raise MihenkError('Parça adı zorunludur.')
        clash = PartRepo.by_code(conn, clean['code'])
        if clash and int(clash['id']) != part_id:
            raise MihenkError('Bu kodu başka bir parça kullanıyor.')
        audit.intent(conn, 'part', part_id, 'update', {'code': clean['code']})
        assignments = ', '.join('%s = ?' % f for f in PartRepo.FIELDS)
        args = [clean[f] for f in PartRepo.FIELDS] + [v.now(), part_id]
        conn.execute('UPDATE part SET %s, updated_at = ? WHERE id = ?' % assignments, args)
        audit.result(conn, 'part', part_id, 'update', {'code': clean['code']})

    @staticmethod
    def move(conn, part_id, delta, reason='count', work_order_id=0, note='') -> float:
        """Stok hareketi yazar ve yeni bakiyeyi dondurur.

        Stok eksiye dusemez: eksiye dusurecek bir cikis reddedilir, cunku
        "elde yok ama kullanildi" diyen bir kutuk kimseye bir sey anlatmaz.
        """
        part_id = int(part_id)
        part = PartRepo.get(conn, part_id)
        if not part:
            raise MihenkError('Parça bulunamadı.')
        amount = v.number(delta)
        if amount is None or amount == 0:
            raise MihenkError('Miktar sıfırdan farklı olmalı.')
        reason = v.enum(reason, REASONS, 'count')
        balance = round(float(part['stock']) + amount, 4)
        if balance < 0:
            raise MihenkError('Stok eksiye düşemez: elde %s %s var, %s %s çıkış isteniyor.'
                              % (_fmt(part['stock']), part['unit'], _fmt(abs(amount)), part['unit']))

        payload = {'delta': amount, 'reason': reason, 'work_order_id': int(work_order_id or 0)}
        audit.intent(conn, 'part', part_id, 'movement', payload)
        # reason makine anahtari, note serbest metin: notun gerekceyi ezmemesi
        # icin ikisi ayri kolonda durur, yoksa "hangi hareket neydi" sorgulanamaz.
        conn.execute('INSERT INTO part_movement (part_id, work_order_id, delta, balance, reason,'
                     ' note, actor, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                     (part_id, int(work_order_id or 0), amount, balance, reason,
                      v.text(note, 191), _operator(), v.now()))
        conn.execute('UPDATE part SET stock = ?, updated_at = ? WHERE id = ?',
                     (balance, v.now(), part_id))
        payload['balance'] = balance
        audit.result(conn, 'part', part_id, 'movement', payload)
        return balance

    @staticmethod
    def consume(conn, part_id, quantity, work_order_id, note='') -> float:
        """Is emrinde parca kullanimi."""
        amount = v.number(quantity)
        if amount is None or amount <= 0:
            raise MihenkError('Kullanılan miktar sıfırdan büyük olmalı.')
        return PartRepo.move(conn, part_id, -abs(amount), 'consume', work_order_id, note)

    @staticmethod
    def reason_text(row) -> str:
        """Hareketin ekranda gorunen gerekcesi: not varsa o, yoksa gerekce etiketi."""
        note = (row.get('note') or '').strip() if isinstance(row, dict) else ''
        label = REASONS.get(row['reason'], row['reason'])
        return ('%s — %s' % (label, note)) if note else label

    @staticmethod
    def movements(conn, part_id=0, work_order_id=0, limit=200) -> list:
        where, args = ['1=1'], []
        if part_id:
            where.append('part_id = ?')
            args.append(int(part_id))
        if work_order_id:
            where.append('work_order_id = ?')
            args.append(int(work_order_id))
        args.append(int(limit))
        sql = ('SELECT * FROM part_movement WHERE %s ORDER BY id DESC LIMIT ?'
               % ' AND '.join(where))
        return _rows(conn.execute(sql, args))

    @staticmethod
    def used_on_work_order(conn, work_order_id) -> list:
        """Bir is emrinde kullanilan parcalar, parca bilgisiyle birlikte."""
        return _rows(conn.execute(
            'SELECT m.*, p.code, p.name, p.unit, p.unit_cost FROM part_movement m'
            ' INNER JOIN part p ON p.id = m.part_id'
            ' WHERE m.work_order_id = ? AND m.reason = ? ORDER BY m.id',
            (int(work_order_id), 'consume')))

    @staticmethod
    def work_order_cost(conn, work_order_id) -> float:
        """Is emrinde harcanan parcalarin maliyeti."""
        total = 0.0
        for row in PartRepo.used_on_work_order(conn, work_order_id):
            total += abs(float(row['delta'])) * float(row['unit_cost'])
        return round(total, 2)

    @staticmethod
    def delete(conn, part_id) -> None:
        """Hareketi olan parca silinmez; pasife alinir."""
        part_id = int(part_id)
        row = conn.execute('SELECT COUNT(*) AS c FROM part_movement WHERE part_id = ?',
                           (part_id,)).fetchone()
        if int(row['c']):
            raise MihenkError('Bu parçanın stok hareketi var, silinemez. '
                              'Bunun yerine pasife alın.')
        audit.intent(conn, 'part', part_id, 'delete')
        conn.execute('DELETE FROM part WHERE id = ?', (part_id,))
        audit.result(conn, 'part', part_id, 'delete')


def _fmt(value) -> str:
    """Sayiyi gereksiz sifir olmadan yazar."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return ('%g' % number)
