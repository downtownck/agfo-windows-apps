# -*- coding: utf-8 -*-
"""AGFO Subscription Manager - arayuz duman testi (xvfb ile Linux'ta da calisir).

    xvfb-run -a python -I tests/test_gui.py <subscription-manager klasoru>
"""
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))
os.environ['APPDATA'] = tempfile.mkdtemp()

from tkinter import filedialog, messagebox  # noqa: E402

import webbrowser  # noqa: E402

INFOS, URLS = [], []
messagebox.showinfo = lambda *a, **k: INFOS.append(a)
messagebox.showwarning = lambda *a, **k: INFOS.append(a)
messagebox.showerror = lambda *a, **k: (_ for _ in ()).throw(AssertionError(a))
messagebox.askyesno = lambda *a, **k: True
webbrowser.open = lambda u: URLS.append(u)

import mailscan  # noqa: E402
import subscription_app as A  # noqa: E402

A.App._startup_tasks = lambda self: None  # no network
app = A.App()
app.update()
assert not app.tree.get_children()  # empty on first run
app.import_json(str(ROOT / 'tests' / 'fixture_subscriptions.json'))
app.import_json(str(ROOT / 'tests' / 'fixture_subscriptions.json'))  # idempotent
assert len(app.store.items) == 6, len(app.store.items)
rows = app.tree.get_children()
assert len(rows) >= 5, len(rows)
assert app.stat['monthly'].cget('text').startswith('₺')

app.f_status.set('Ödeme sorunu')
app.refresh()
assert all(app.store.get(i)['status'] == 'failing' for i in app.tree.get_children())
app.f_status.set('İptal edilmemiş')
app.refresh()

for col in ('monthly', 'next', 'name', 'amount', 'status'):
    app.sort_by(col)

first = app.tree.get_children()[0]
app.tree.selection_set(first)
app.show_detail()
assert app.detail.get('1.0', 'end').strip()

d = A.EditDialog(app, dict(app.store.get(first)))
app.update()
d.save()

w = A.CancelWizard(app, [app.store.get(i) for i in app.tree.get_children()[:2]])
app.update()
w.record('cancelled')
w.record('cancel_scheduled')
assert app.store.get(first)['status'] in ('cancelled', 'cancel_scheduled')
assert app.store.get(first)['history'][-1]['note'] == 'sihirbaz'

f = mailscan.parse_message('NewApp <invoice+statements+acct_x@stripe.com>', 'Your receipt from NewApp', None,
                           'Oct 1–Nov 1, 2026 NewApp Pro Qty 1 $12.00 Total $12.00', 'user@example.com')
n = len(app.store.items)
r = A.ReviewDialog(app, mailscan.aggregate([f]), source='test')
app.update()
r.tree.selection_set(r.tree.get_children())
r.apply()
assert len(app.store.items) == n + 1

for it in app.store.items[:5]:
    app.compose_cancel_mail(it)
    app.open_manage(it)
assert URLS

A.RatesDialog(app).destroy()
A.ScanDialog(app).destroy()

out = os.path.join(tempfile.mkdtemp(), 'x.csv')
filedialog.asksaveasfilename = lambda **k: out
app.export_csv()
assert len(open(out, encoding='utf-8-sig').read().splitlines()) > 3

app.update()
app.destroy()
print('AGFO SUBSCRIPTIONS GUI SMOKE OK')
