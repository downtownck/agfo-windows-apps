# -*- coding: utf-8 -*-
"""4.4 ag taramasi testleri icin ortak sahte kayitlar (test_core ve test_gui_nav)."""
NET_SCAN = [
    {'type': 'net-adapter', 'alias': 'Ethernet', 'desc': 'Realtek PCIe GbE', 'kind': 'ethernet', 'virtual': False, 'link_bps': 1e8, 'link': '100 Mbps',
     'ifindex': 7, 'gateway': '192.168.1.1', 'dns_static': [], 'dns_current': ['192.168.1.1'], 'guid': '{A}',
     'speed_duplex': {'display': '100 Mbps Full Duplex', 'value': '4', 'valid_display': ['Auto Negotiation', '10 Mbps Half Duplex', '100 Mbps Full Duplex', '1.0 Gbps Full Duplex'],
                      'valid_values': ['0', '1', '4', '6']}},
    {'type': 'net-adapter', 'alias': 'Tailscale', 'desc': 'Tailscale Tunnel', 'kind': 'other', 'virtual': True, 'dns_current': ['100.100.100.100'], 'guid': '{T}'},
    {'type': 'dns-probe', 'server': '192.168.1.1', 'median': 41.0, 'ok': 6, 'fail': 0, 'ping': 2.0},
    {'type': 'dns-probe', 'server': '1.1.1.1', 'median': 12.0, 'ok': 6, 'fail': 0, 'ping': 9.0},
    {'type': 'dns-probe', 'server': '8.8.8.8', 'median': 18.0, 'ok': 6, 'fail': 0, 'ping': 11.0},
    {'type': 'dns-probe', 'server': '9.9.9.9', 'median': None, 'ok': 0, 'fail': 6, 'ping': None},
    {'type': 'net-ping', 'target': 'gateway', 'ip': '192.168.1.1', 'sent': 10, 'lost': 0, 'avg': 1.2, 'jitter': 0.4},
    {'type': 'net-ping', 'target': 'internet', 'ip': '1.1.1.1', 'sent': 10, 'lost': 2, 'avg': 25.0, 'jitter': 31.0},
    {'type': 'net-do', 'policy': None, 'config': None, 'settings': 3},
    {'type': 'net-proc', 'pid': 10, 'name': 'msedge', 'connections': 22},
]
