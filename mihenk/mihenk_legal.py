# -*- coding: utf-8 -*-
"""Sorumluluk reddi.

Uygulama ucretsiz dagitiliyor. Metin tek bir yerde duruyor ve uc yerden
okunuyor: kurulum betigi (Derle-ve-Kur.cmd), ilk acilista cikan onay
penceresi, ve Ayarlar ekranindaki baglanti. Uc kopya tutulsaydi biri
gunceldigi gun otekiler eskimis olurdu.

Onay, ayar dosyasina surum numarasiyla yaziliyor (`disclaimer_accepted`).
Metin esasli bicimde degisirse VERSION artar ve onay yeniden sorulur;
boylece kullanicinin kabul ettigi seyin hangi metin oldugu belli olur.
"""
from __future__ import annotations

import mihenk_store as store
from mihenk_i18n import t

# Metin esasli degisirse artir: onay yeniden sorulur.
VERSION = 1

TITLE = 'Sorumluluk reddi'


def heading() -> str:
    return t('Sorumluluk reddi')


def text() -> str:
    """Tam metin. Satir sonlari korunur; kurulum betigi de bunu yazar."""
    return '\n\n'.join([
        t('AGFO Mihenk ücretsiz bir yazılımdır ve "olduğu gibi" sunulur. Açık ya da örtülü '
          'hiçbir garanti verilmez; belirli bir amaca uygunluk, kesintisiz çalışma ve '
          'hatasızlık garantisi de buna dahildir.'),
        t('Bu yazılım bir kalite yönetim sisteminin, akredite bir kalibrasyonun ya da yasal '
          'bir uygunluk değerlendirmesinin yerine geçmez. Kayıtlarınızın doğruluğu, '
          'saklanması, yedeklenmesi ve ilgili standartlara uygunluğu sizin '
          'sorumluluğunuzdadır.'),
        t('AGFO Teknik Kontrol ve yazılımın yazarları, bu yazılımın kullanımından ya da '
          'kullanılamamasından doğan hiçbir doğrudan, dolaylı, arızi veya sonuçsal zarardan '
          'sorumlu tutulamaz. Veri kaybı, üretim kaybı, denetim bulgusu ve ürün geri '
          'çağırma da buna dahildir.'),
        t('Bu yazılımı kullanmak, AGFO ile bir belgelendirme ilişkisi kurmaz ve hiçbir '
          'denetimde, belgelendirme kararında ya da başvuruda avantaj sağlamaz. AGFO '
          'belgelendirme faaliyetlerini tarafsızlık kurallarına göre yürütür.'),
        t('Yazılımı kurarak ve kullanarak bu şartları kabul etmiş olursunuz.'),
    ])


def accepted() -> bool:
    """Yururlukteki metin daha once onaylandi mi."""
    try:
        return int(store.setting('disclaimer_accepted') or 0) >= VERSION
    except (TypeError, ValueError):
        return False


def accept() -> None:
    store.save_settings({'disclaimer_accepted': VERSION})
