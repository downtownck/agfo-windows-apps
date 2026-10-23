# -*- coding: utf-8 -*-
"""AGFO AI Editor - BRCGS ekranlarinin dili.

Kilavuz verisi (sorular, ipuclari, secenekler, 'yazmayin' kurallari) Turkce yazilmistir; alan anahtarlari bu Turkce
metinden turetildigi icin veri degistirilmez. Ekranda ve rapora giden metinde brcgs_data/i18n/guide_<dil>.json
eslemesi kullanilir. Arayuz metinleri ui() ile gecer; ileride ui_<dil>.json eklenerek baska dile cevrilebilir.
"""
from __future__ import annotations

import functools
import json

from . import data

LANG = 'en'


@functools.lru_cache(maxsize=None)
def _map(name):
    try:
        with open(data.data_root() / 'i18n' / ('%s_%s.json' % (name, LANG)), encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def guide(text):
    """Kilavuz verisindeki Turkce metnin ekrandaki karsiligi (yoksa kendisi)."""
    t = str(text or '')
    return _map('guide').get(t.strip(), t) if t else t


def ui(text):
    """Arayuz metni; ui_<dil>.json varsa oradan (su an arayuz zaten Ingilizce yazilidir)."""
    return _map('ui').get(text, text)
