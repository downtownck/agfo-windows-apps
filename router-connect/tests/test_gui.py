# -*- coding: utf-8 -*-
"""AGFO Router Connect - arayuz duman testi (xvfb ile Linux'ta da calisir; gercek Wi-Fi karti gerekmez).

    xvfb-run -a python -I tests/test_gui.py <router-connect klasoru>
"""
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))
os.environ['APPDATA'] = tempfile.mkdtemp()
os.environ['LOCALAPPDATA'] = tempfile.mkdtemp()

from tkinter import messagebox  # noqa: E402

INFOS = []
messagebox.showinfo = lambda *a, **k: INFOS.append(a)
messagebox.showwarning = lambda *a, **k: INFOS.append(a)
messagebox.showerror = lambda *a, **k: (_ for _ in ()).throw(AssertionError(a))
messagebox.askyesno = lambda *a, **k: True

import time  # noqa: E402

import router_app as A  # noqa: E402
import router_history as history  # noqa: E402
import router_wifi as wifi  # noqa: E402

NETS = [
    {'ssid': 'Salon-Router', 'bssid': 'aa:bb:cc:00:00:01', 'signal': 78, 'band': '5 GHz', 'channel': 36},
    {'ssid': 'Salon-Router', 'bssid': 'aa:bb:cc:00:00:02', 'signal': 91, 'band': '2.4 GHz', 'channel': 6},
    {'ssid': 'Yatak-Odasi', 'bssid': 'de:ad:be:ef:00:10', 'signal': 45, 'band': '5 GHz', 'channel': 100},
    {'ssid': 'Komsu', 'bssid': '77:88:99:aa:bb:cc', 'signal': 12, 'band': '2.4 GHz', 'channel': 11},
]
STATE = {'cur': {'name': 'Wi-Fi', 'guid': '', 'ssid': 'Yatak-Odasi', 'bssid': 'de:ad:be:ef:00:10', 'signal': 45,
                 'connected': True}}
CONNECTS = []


def fake_connect(ssid, bssid='', iface=None, profile=None, **kw):
    CONNECTS.append((ssid, bssid))
    STATE['cur'] = {'name': 'Wi-Fi', 'guid': '', 'ssid': ssid, 'bssid': 'aa:bb:cc:00:00:02', 'signal': 91,
                    'connected': True}
    return True, 'Bağlandı: ' + ssid


wifi.scan = lambda *a, **k: (NETS, '')
wifi.current = lambda *a, **k: STATE['cur']
wifi.connect = fake_connect

A.App._startup_tasks = lambda self: None          # ag / otomatik tarama yok
app = A.App()
app.update()
assert app.title().endswith(A.VERSION) and not app.tree.get_children()
assert 'Router ekle' in app.hint_lbl.cget('text') or app.hint_lbl.cget('text') == ''

# gecmisten otomatik ekleme: liste bos olsa da bulur (Salon + Yatak menzilde, Komsu zayif, Kafe menzilde degil)
history.collect_registry = lambda: []
history.collect_events = lambda *a, **k: []
wifi.profiles = lambda *a, **k: ['Salon-Router', 'Yatak-Odasi', 'Komsu', 'Kafe']
app.find_known(auto=True)
for _ in range(80):
    app.update()
    if not app.busy and app.store.routers:
        break
    time.sleep(0.05)
assert [r['ssid'] for r in app.store.routers] == ['Salon-Router', 'Yatak-Odasi'], app.store.routers
assert 'otomatik eklendi' in app.logbox.get('1.0', 'end')
app.find_known(auto=False)                         # tekrar: yeni bir sey eklemez
for _ in range(40):
    app.update()
    time.sleep(0.05)
assert len(app.store.routers) == 2
for r in list(app.store.routers):
    app.store.remove(r)
app.refresh_table()
assert 'Geçmişten bul' in app.hint_lbl.cget('text')

# Gecmisten bul penceresi: menzildekiler onceden secili, ekle
dd = A.DiscoverDialog(app)
for _ in range(60):
    app.update()
    if dd.rows:
        break
    time.sleep(0.05)
assert len(dd.rows) == 4 and len(dd.tree.selection()) == 2, (len(dd.rows), dd.tree.selection())
dd.add()
assert sorted(r['ssid'] for r in app.store.routers) == ['Salon-Router', 'Yatak-Odasi']
for r in list(app.store.routers):
    app.store.remove(r)
app.refresh_table()

# bos listede "en yakina baglan" bilgilendirir, baglanmaz
app.connect_nearest()
assert INFOS and not CONNECTS

# router ekleme penceresi: tara, iki ag sec, ekle
dlg = A.PickDialog(app)
for _ in range(50):
    app.update()
    if dlg.rows:
        break
    time.sleep(0.05)
assert [n['ssid'] for n in dlg.rows][:2] == ['Salon-Router', 'Salon-Router'], dlg.rows   # sinyale gore sirali
items = dlg.tree.get_children()
sel = [i for i in items if dlg.tree.item(i, 'values')[0] in ('Salon-Router', 'Yatak-Odasi')]
dlg.tree.selection_set(sel[1:])                    # Salon (2,4GHz) + Yatak -> SSID ile eklenir (tek BSSID secildi)
dlg.add()
app.update()
names = [r['ssid'] for r in app.store.routers]
assert names == ['Salon-Router', 'Yatak-Odasi'] and all(not r['bssid'] for r in app.store.routers), app.store.routers

# BSSID sabitleme: ayni adli iki BSSID secilirse ikisi de sabitlenir
dlg2 = A.PickDialog(app)
for _ in range(50):
    app.update()
    if dlg2.rows:
        break
    time.sleep(0.05)
dlg2.tree.selection_set([i for i in dlg2.tree.get_children() if dlg2.tree.item(i, 'values')[0] == 'Salon-Router'])
dlg2.add()
assert len(app.store.routers) == 4 and sum(1 for r in app.store.routers if r['bssid']) == 2
for r in [r for r in app.store.routers if r['bssid']]:
    app.store.remove(r)
app.refresh_table()

# tarama + tablo
app.cycle(force=False, do_connect=False)
for _ in range(50):
    app.update()
    if not app.busy:
        break
    time.sleep(0.05)
rows = [app.tree.item(i, 'values') for i in app.tree.get_children()]
assert [r[0] for r in rows] == ['Salon-Router', 'Yatak-Odasi'], rows
assert rows[0][5] == 'En yakın' and rows[1][5] == 'Bağlı', rows
assert '91%' in rows[0][3] and '45%' in rows[1][3]
assert 'Yatak-Odasi' in app.now_lbl.cget('text')
assert not CONNECTS                                  # "Yenile" baglanti degistirmez

# en yakina bagl: Yatak'tan Salon'a gecer
app.connect_nearest()
for _ in range(80):
    app.update()
    if not app.busy:
        break
    time.sleep(0.05)
assert CONNECTS == [('Salon-Router', '')], CONNECTS
rows = [app.tree.item(i, 'values') for i in app.tree.get_children()]
assert rows[0][5] == 'Bağlı', rows



def settle(n=30):
    for _ in range(n):
        app.update()
        time.sleep(0.1)


# zaten en iyisindeyse yeniden baglanmaz
app._cycle_worker(True, True)
settle(5)
assert CONNECTS == [('Salon-Router', '')]

# otomatik kip: ayarlar kaydedilir, zamanlayici kurulur, kapaninca iptal olur
app.v_interval.set(5)
app.v_margin.set(99)
app.v_auto.set(True)
app.on_auto()
app.update()
assert app.store.settings['auto'] is True and app.store.settings['interval'] == 30 and app.store.settings['margin'] == 40
assert app._auto_job is not None
app.v_auto.set(False)
app.on_auto()
assert app._auto_job is None and app.store.settings['auto'] is False

# yeniden adlandir / cikar
app.tree.selection_set(app.tree.get_children()[0])
A.simpledialog.askstring = lambda *a, **k: 'Salon'
app.rename_selected()
assert app.store.routers[0]['name'] == 'Salon'
app.remove_selected()
assert len(app.store.routers) == 1

# hata durumunda arayuz dusmez
wifi.scan = lambda *a, **k: (_ for _ in ()).throw(wifi.WifiError('netsh yok'))
app.busy = True
app._cycle_worker(False, False)
settle(5)
assert not app.busy
assert 'Hata' in app.logbox.get('1.0', 'end')

app.update()
app.destroy()
print('AGFO ROUTER CONNECT GUI SMOKE OK')
