# -*- coding: utf-8 -*-
"""AGFO Subscription Manager - cekirdek testleri (ag ve Windows gerektirmez).

    python -I tests/test_core.py <subscription-manager klasoru>
"""
import datetime as dt
import email.message
import json
import os
import pathlib
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))
os.environ['APPDATA'] = tempfile.mkdtemp()

import bankscan  # noqa: E402
import catalog  # noqa: E402
import mailscan as m  # noqa: E402
import store  # noqa: E402
import subscription_core as core  # noqa: E402
import subscription_update as upd  # noqa: E402

PASSED = []
D = dt.date(2026, 11, 2)


def test(fn):
    fn()
    PASSED.append(fn.__name__)
    return fn


def p(frm, subj, body):
    return m.parse_message(frm, subj, D, body, 'user@example.com')


@test
def numbers():
    assert m.parse_number('1,569.99') == 1569.99
    assert m.parse_number('1.499,99') == 1499.99
    assert m.parse_number('249,99') == 249.99
    assert m.parse_number('2599.99') == 2599.99
    assert m.find_amount('Total ₺1,569.99') == (1569.99, 'TRY')
    assert m.find_amount('Amount €28.00 EUR') == (28.0, 'EUR')


@test
def stripe_receipt():
    f = p('Songscription, Inc. <invoice+statements+acct_1@stripe.com>', 'Your receipt from Songscription, Inc. #1',
          'Receipt from Songscription, Inc. $9.99 Paid on November 2, 2026 with - 4242\n\n'
          'Receipt #2288-8987 Nov 2–Dec 2, 2026 Songscription Plus Qty 1 $9.99 Total $9.99')
    assert f['name'] == 'Songscription, Inc. – Songscription Plus', f
    assert (f['amount'], f['currency'], f['period'], f['channel']) == (9.99, 'USD', 'monthly', 'Stripe/Web')
    assert f['payment'].endswith('4242')


@test
def stripe_yearly_and_failed():
    f = p('X <invoice+statements+acct_2@stripe.com>', 'Your receipt from X #1',
          'Receipt #2932-6614-4235 Jul 18, 2026–Jul 18, 2027 X Premium (per Period) Qty 1 ₺1,569.99 Total ₺1,569.99')
    assert (f['name'], f['period'], f['amount'], f['currency']) == ('X – X Premium', 'yearly', 1569.99, 'TRY')
    g = p('Eleven Labs Inc. <failed-payments+acct_3@stripe.com>', '$5.00 payment to Eleven Labs Inc. was unsuccessful',
          "We weren't able to charge the credit card you provided.")
    assert g['status'] == 'failing' and g['amount'] == 5.0


@test
def google_play_and_apple():
    f = p('Google Play <googleplay-noreply@google.com>', 'Google Play Siparişi Makbuzunuz',
          "Google Play'deki Quora, Inc. aboneliğiniz yenilendi.\n\nPoe: 10 thousand points/day (Poe - Fast AI Chat) ₺249,99/ay\n\nMastercard-1111")
    assert (f['vendor'], f['amount'], f['period'], f['channel']) == ('Quora, Inc.', 249.99, 'monthly', 'Google Play')
    a = p('Apple <no_reply@email.apple.com>', 'Apple makbuzunuz.',
          'Fatura 9 Ekim 2026 Apple Hesabı: user@example.com iCloud iCloud+ with 50 GB of storage (Aylık) '
          'Yenileme: 10 Kasım 2026 ₺49,99 %20 KDV')
    assert a['name'] == 'iCloud+ with 50 GB of storage' and a['next_renewal'] == '2026-11-10' and a['amount'] == 49.99


@test
def paddle_paypal_renewal():
    f = p('Klangio GmbH (via Paddle.com) <help@paddle.com>', 'Your Klangio GmbH receipt',
          'Your Klangio GmbH subscription receipt Amount Paid TRY 2599.99 Receipt Date 23rd June 2026 '
          'Payment Method ending in 4242 Klangio Universe Yearly TRY 2166.66')
    assert (f['name'], f['amount'], f['period']) == ('Klangio Universe Yearly', 2599.99, 'yearly')
    g = p('PayPal <servicio@paypal.es>', 'Receipt for Your Payment to netcup GmbH',
          'You paid €28.00 EUR to netcup GmbH Merchant netcup GmbH')
    assert (g['name'], g['amount'], g['currency']) == ('netcup GmbH', 28.0, 'EUR')
    h = p('Formidable Forms <accounts@formidableforms.com>', 'FYI - Your Formidable Renewal Is Coming Up!',
          'part of the Formidable Pro fam this past year ... your plan will renew on November 29, 2026 ... at $599.00.')
    assert (h['next_renewal'], h['amount'], h['period']) == ('2026-11-29', 599.0, 'yearly')
    c = p('Paddle <help@paddle.com>', 'BUTTERFLY EFFECT PTE. LTD. aboneliğiniz iptal edilecek', 'Aboneliğiniz iptal edilecek')
    assert c['status'] == 'cancel_scheduled'


@test
def generic_receipt_uses_total():
    f = p('Example Hosting <bilgi@hosting.example>', 'Ödeme Makbuzu',
          'Alan Adı Yenileme - a.com - 1 Yıl ₺820.81 TL\nAlan Adı Yenileme - b.net - 1 Yıl ₺945.25 TL\n'
          'Ara Toplam: ₺1766.06 TL\n20.00% KDV: ₺353.21 TL\nToplam: ₺2119.27 TL\n')
    assert (f['amount'], f['currency'], f['period']) == (2119.27, 'TRY', 'yearly'), f


@test
def noise_ignored():
    assert p('Friend <a@b.com>', 'Lunch?', 'see you at 12') is None


@test
def aggregate_groups():
    a = p('Suno <invoice+statements@suno.com>', 'Your receipt from Suno', 'Oct 23–Nov 23, 2026 Suno Premier Qty 1 $30.00')
    b = dict(a, date='2026-09-23')
    out = m.aggregate([a, b])
    assert len(out) == 1 and out[0]['count'] == 2 and out[0]['months'] == 2


@test
def imap_scan_with_fake_server():
    def mk(frm, subj, body):
        msg = email.message.EmailMessage()
        msg['From'], msg['Subject'], msg['Date'] = frm, subj, 'Sun, 25 Oct 2026 18:30:48 +0000'
        msg.set_content(body)
        return msg.as_bytes()
    msgs = {b'1': mk('"Suno" <invoice+statements@suno.com>', 'Your receipt from Suno #1',
                     'Oct 23–Nov 23, 2026 Suno Premier Qty 1 $30.00 Total $30.00'),
            b'2': mk('"Staff" <staff@example.org>', 'Fatura', 'internal'),
            b'3': mk('"Google Play" <googleplay-noreply@google.com>', 'Google Play Siparişi Makbuzunuz',
                     "Google Play'deki Storytel Sweden AB aboneliğiniz yenilendi.\nYıllık Sınırsız (Storytel) ₺1.499,99/yıl\n")}
    calls = []

    class Fake:
        def __init__(self, h, port): pass
        def login(self, u, pw): pass
        def list(self): return 'OK', [b'(\\HasNoChildren \\All) "/" "[Gmail]/All Mail"']
        def select(self, f, readonly=True):
            calls.append(('select', f, readonly))
            return 'OK', [b'3']
        def search(self, *a):
            calls.append(('search',) + a[:2])
            return 'OK', [b'1 2 3']
        def fetch(self, ids, what):
            assert 'PEEK' in what  # never marks messages as read
            out = []
            for i in ids.split(b','):
                raw = msgs[i]
                out += [(i + b' (X {1}', raw.split(b'\n\n')[0] + b'\n\n' if 'HEADER' in what else raw), b')']
            return 'OK', out
        def logout(self): pass
    old = m.imaplib.IMAP4_SSL
    m.imaplib.IMAP4_SSL = Fake
    try:
        for host in ('imap.gmail.com', 'mail.example.net'):
            calls.clear()
            res = m.aggregate(m.scan_account(host, 993, 'u', 'pw', 13, ['example.org']))
            assert {r['vendor'] for r in res} == {'Suno', 'Storytel Sweden AB'}, res
            assert all(c[2] is True for c in calls if c[0] == 'select')
    finally:
        m.imaplib.IMAP4_SSL = old


@test
def bank_statement_recurring():
    rows = [('05.08.2026', 'ELEVENLABS.IO 4022xxxx NEW YORK US', '-259,10'), ('05.09.2026', 'ELEVENLABS.IO 4022 NEW YORK US', '-259,80'),
            ('05.10.2026', 'ELEVENLABS.IO 4022 NEW YORK US', '-260,10'), ('23.08.2026', 'GOOGLE *TV+ G.CO/HELPPAY', '-129,99'),
            ('23.09.2026', 'GOOGLE *TV+ G.CO/HELPPAY', '-129,99'), ('23.10.2026', 'GOOGLE *TV+ G.CO/HELPPAY', '-169,99'),
            ('12.09.2026', 'MIGROS 1234', '-812,40'), ('14.10.2026', 'MAAS ODEMESI', '45.000,00')]
    text = 'Hesap Hareketleri\nTarih;Açıklama;Tutar;Bakiye\n' + ''.join(';'.join(r) + ';0\n' for r in rows)
    path = os.path.join(tempfile.mkdtemp(), 'ekstre.csv')
    open(path, 'w', encoding='cp1254').write(text)
    found = {f['name']: f for f in bankscan.find_recurring(path)}
    assert len(found) == 2, found
    assert all(f['period'] == 'monthly' and f['months'] == 3 for f in found.values())


FIXTURE = json.loads((ROOT / 'tests' / 'fixture_subscriptions.json').read_text(encoding='utf-8'))


@test
def store_seed_money_and_match():
    s = store.Store()
    assert s.items == []  # public repo ships an empty list; personal data is imported locally
    s.items.extend(store.new_item(**i) for i in FIXTURE['items'])
    s.save()
    assert len(s.items) == len(FIXTURE['items'])
    assert all(i['status'] in store.STATUSES for i in s.items)
    assert s.to_try(10, 'USD') == 10 * s.data['rates']['USD']
    suno = s.find_match('Suno – Suno Premier', 'Suno')
    assert suno and suno['name'] == 'Suno Premier'
    assert s.find_match('Storytel: Sesli kitap', 'Storytel Sweden AB')['name'].startswith('Storytel')
    it = s.items[0]
    s.set_status(it, 'cancelled', 'test')
    assert store.Store().get(it['id'])['status'] == 'cancelled'  # persisted
    assert os.path.exists(s.path + '.bak')


@test
def roll_forward_dates():
    today = dt.date.today()
    nxt = store.roll_forward((today - dt.timedelta(days=40)).isoformat(), 'monthly')
    assert dt.date.fromisoformat(nxt) >= today
    assert store.roll_forward('2099-01-01', 'yearly') == '2099-01-01'


@test
def catalog_lookup():
    assert catalog.lookup('Google Play')[0].startswith('https://play.google.com')
    assert catalog.lookup('', 'Suno Premier')[1] == 'billing@suno.com'
    assert catalog.how_to({'channel': 'Apple', 'name': 'iCloud+'})


@test
def updater_safety():
    assert upd.GH_PREFIX == 'subscription-manager-v'
    import re
    assert re.fullmatch(upd.GH_ASSET, 'AGFO-Subscription-Manager-v%s-Kurulum.zip' % core.VERSION)
    env = upd.scrub_env({'PATH': '/x', '_PYI_SPLASH': '1', '_MEIPASS2': 'c:/t'})
    assert '_PYI_SPLASH' not in env and '_MEIPASS2' not in env and env['PYINSTALLER_RESET_ENVIRONMENT'] == '1'
    d = tempfile.mkdtemp()
    good = os.path.join(d, 'AGFO-Subscription-Manager-v9.9.9-Kurulum.zip')
    with zipfile.ZipFile(good, 'w') as z:
        z.writestr('AGFO-Subscription-Manager-v9.9.9/Derle-ve-Kur.cmd', '@echo off')
    assert (upd.extract(good) / 'Derle-ve-Kur.cmd').exists()
    bad = os.path.join(d, 'bad.zip')
    with zipfile.ZipFile(bad, 'w') as z:
        z.writestr('../../evil.cmd', 'x')
        z.writestr('Derle-ve-Kur.cmd', 'x')
    try:
        upd.extract(bad)
        raise AssertionError('unsafe path accepted')
    except upd.ghu.GHUpdateError:
        pass
    rel = {'version': '9.9.9', 'assets': [{'name': 'AGFO-Subscription-Manager-v9.9.9-Kurulum.zip', 'url': 'https://github.com/x', 'size': 1}]}
    assert not upd.package_ready(rel, rel['assets'][0])  # no SHA-256 -> not offered


@test
def seed_json_valid():
    seed = json.loads((ROOT / 'seed_subscriptions.json').read_text(encoding='utf-8'))
    assert seed['items'] == [], 'no personal data in the public repo'
    data = FIXTURE
    ids = [i['id'] for i in data['items']]
    assert len(ids) == len(set(ids))
    for i in data['items']:
        assert i['period'] in store.PERIODS and i['currency'] in store.CURRENCY_SYMBOL


print('OK %d tests: %s' % (len(PASSED), ', '.join(PASSED)))
