# -*- coding: utf-8 -*-
"""Arayuz dili.

Kaynak metin Turkce; cevirinin anahtari da Turkce metnin kendisi. Ayri bir
anahtar dizisi tutmak yerine boyle yapildi, cunku kodu okuyan kisi ne
yazdigini dogrudan goruyor ve ceviri eksikse uygulama kirilmak yerine Turkce
gosteriyor.

Veritabanina yazilan degerler cevrilmez: durum anahtarlari, birim kodlari ve
gerekce anahtarlari her dilde aynidir. Cevrilen sey yalnizca ekranda gorunen
etiketlerdir, boylece dil degistirince kayitlar bozulmaz.

Dil, bu modul ice aktarilirken secilir ve surec boyunca degismez. Bunun
sebebi acik: NAV, LABELS, ALL_TABLES gibi sabit tablolar modul duzeyinde
kuruluyor ve metinlerini bir kez aliyor. Dil sonradan degistirilirse o
tablolar eski dilde kalirdi; yarisi Turkce yarisi Ingilizce bir ekran,
yeniden baslatmaktan daha kotudur. Bu yuzden Ayarlar ekranindaki secim
kaydediliyor ve uygulama yeniden baslatiliyor.
"""
from __future__ import annotations

import os

import mihenk_store as store

LANGUAGES = {'tr': 'Türkçe', 'en': 'English'}
DEFAULT = 'tr'

_LANGUAGE = DEFAULT
_TABLE = {}


def set_language(code: str) -> str:
    """Dili degistirir ve yururlukteki kodu dondurur."""
    global _LANGUAGE, _TABLE
    _LANGUAGE = code if code in LANGUAGES else DEFAULT
    _TABLE = EN if _LANGUAGE == 'en' else {}
    return _LANGUAGE


def language() -> str:
    return _LANGUAGE


def t(text: str) -> str:
    """Metni yururlukteki dile cevirir. Karsiligi yoksa oldugu gibi doner."""
    if not _TABLE:
        return text
    return _TABLE.get(text, text)


def tf(text: str, *args) -> str:
    """Bicimli metin: once cevirir, sonra % uygular."""
    translated = t(text)
    return (translated % args) if args else translated


def missing(strings) -> list:
    """Cevirisi olmayan metinler. Testler bununla acigi olcer."""
    return [s for s in strings if s not in EN and s not in _NOT_TEXT]


# Ay ve gun adlari sozlukte degil, cunku "Aralik" hem ay adi hem de planin
# "Aralik" alani; tek bir sozluk ikisini ayni anda tutamaz. Takvim bunlari
# sira numarasiyla ister, metinle degil.
MONTHS = {
    'tr': ('Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
           'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'),
    'en': ('January', 'February', 'March', 'April', 'May', 'June',
           'July', 'August', 'September', 'October', 'November', 'December'),
}
WEEKDAYS = {
    'tr': ('Pt', 'Sa', 'Ça', 'Pe', 'Cu', 'Ct', 'Pz'),
    'en': ('Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'),
}


def months() -> tuple:
    return MONTHS.get(_LANGUAGE, MONTHS[DEFAULT])


def weekdays() -> tuple:
    return WEEKDAYS.get(_LANGUAGE, WEEKDAYS[DEFAULT])


# Metin degil: cevrilmeyecek sabitler. Testteki kapsam olcumu bunlari sayar
# ki eksik ceviri listesi gercek acigi gostersin.
_NOT_TEXT = {'Derle-ve-Kur.cmd'} | set(MONTHS['tr']) | set(WEEKDAYS['tr'])


def _startup_language() -> str:
    """Ice aktarma aninda secilen dil.

    Once MIHENK_LANG ortam degiskeni (testler ve tasinabilir kullanim icin),
    sonra kayitli ayar. Ayar dosyasi okunamazsa Turkce.
    """
    env = (os.environ.get('MIHENK_LANG') or '').strip().lower()
    if env in LANGUAGES:
        return env
    try:
        return store.load_settings().get('language', DEFAULT)
    except Exception:
        return DEFAULT


# Turkce kaynak metin -> Ingilizce karsiligi.
EN = {
    'İngilizce arayüz: menü, ekranlar, pencereler, hata iletileri, demo veri ve yazdırılabilir rapor iki dilde. Dil, Ayarlar ekranından seçilir ve uygulama yeniden açıldığında geçerli olur; veritabanına yazılan durum ve birim anahtarları her iki dilde de aynı kalır, böylece dil değiştirmek kayıtları bozmaz. Uygulama ücretsiz yayınlandığı için ilk kurulumda ve ilk açılışta sorumluluk reddi gösterilip onaylanıyor.':
        'An English interface: menu, screens, dialogs, error messages, demo data and the printable report in both languages. The language is chosen on the Settings screen and takes effect when the application is reopened; the state and unit keys written to the database stay the same in both languages, so changing language cannot corrupt records. Because the application is published free of charge, a disclaimer is shown and acknowledged at the first installation and on the first run.',
    'Güncelleyici başlatıldıktan sonra uygulama artık kapanıyor. Önceki sürümde kapanmadığı için güncelleyici boşuna bekliyor, indirilen dosyayı kilitli tutuyor ve ikinci deneme "erişim engellendi" ile düşüyordu.':
        'The application now closes once the updater has started. In the previous version it did not, so the updater waited in vain, held the downloaded file locked, and the second attempt failed with "access denied".',
    'Açık duran uygulama yeni sürümü görüyor: güncelleme denetimi yalnızca açılışta değil, uygulama çalışırken saatte bir yineleniyor.':
        'An application left open sees the new version: the update check no longer runs only at startup but repeats every hour while the application is running.',
    'Kabul ediyorum': 'I accept',
    'Sorumluluk reddi': 'Disclaimer',
    'Kabul etmiyorum, çık': 'I do not accept, exit',
    'Okudum, kabul ediyorum.': 'I have read this and I accept it.',
    'Dil değişti. Uygulama şimdi yeniden açılsın mı?':
        'The language has changed. Reopen the application now?',
    'Mihenk ücretsizdir. Kullanmadan önce lütfen okuyun.':
        'Mihenk is free of charge. Please read this before using it.',
    'Dil değişikliği uygulama yeniden açıldığında geçerli olur.':
        'A change of language takes effect when the application is reopened.',
    'Yazılımı kurarak ve kullanarak bu şartları kabul etmiş olursunuz.':
        'By installing and using this software you accept these terms.',
    'Uygulama yeniden açılamadı: %s\n\nElle kapatıp açtığınızda yeni dil geçerli olacak.':
        'The application could not be reopened: %s\n\nClose and open it yourself and the new language will take effect.',
    'AGFO Mihenk ücretsiz bir yazılımdır ve "olduğu gibi" sunulur. Açık ya da örtülü hiçbir garanti verilmez; belirli bir amaca uygunluk, kesintisiz çalışma ve hatasızlık garantisi de buna dahildir.':
        'AGFO Mihenk is free software and is provided "as is". No warranty of any kind is given, express or implied, including any warranty of fitness for a particular purpose, uninterrupted operation or freedom from error.',
    'Bu yazılımı kullanmak, AGFO ile bir belgelendirme ilişkisi kurmaz ve hiçbir denetimde, belgelendirme kararında ya da başvuruda avantaj sağlamaz. AGFO belgelendirme faaliyetlerini tarafsızlık kurallarına göre yürütür.':
        'Using this software creates no certification relationship with AGFO and confers no advantage in any audit, certification decision or application. AGFO conducts its certification activities under its impartiality rules.',
    'Bu yazılım bir kalite yönetim sisteminin, akredite bir kalibrasyonun ya da yasal bir uygunluk değerlendirmesinin yerine geçmez. Kayıtlarınızın doğruluğu, saklanması, yedeklenmesi ve ilgili standartlara uygunluğu sizin sorumluluğunuzdadır.':
        'This software does not replace a quality management system, an accredited calibration or a statutory conformity assessment. The accuracy, retention, backup and standards compliance of your records remain your responsibility.',
    'AGFO Teknik Kontrol ve yazılımın yazarları, bu yazılımın kullanımından ya da kullanılamamasından doğan hiçbir doğrudan, dolaylı, arızi veya sonuçsal zarardan sorumlu tutulamaz. Veri kaybı, üretim kaybı, denetim bulgusu ve ürün geri çağırma da buna dahildir.':
        'AGFO Teknik Kontrol and the authors of this software accept no liability for any direct, indirect, incidental or consequential damage arising from the use of, or the inability to use, this software. That includes loss of data, loss of production, audit findings and product recall.',
    'Ad': 'Name',
    'Ay': 'Month',
    'Aç': 'Open',
    'ay': 'month(s)',
    'Ara': 'Search',
    'Boş': 'Empty',
    'Dil': 'Language',
    'Kod': 'Code',
    'Not': 'Note',
    'Sil': 'Delete',
    'Tip': 'Type',
    'gün': 'day(s)',
    'hiç': 'never',
    'yıl': 'year(s)',
    'Adım': 'Step',
    'Açan': 'Opened by',
    'Açık': 'Light',
    'Efor': 'Effort',
    'Esas': 'Basis',
    'Etki': 'Impact',
    'Hata': 'Error',
    'Koyu': 'Dark',
    'Onay': 'Confirm',
    'Pano': 'Dashboard',
    'Plan': 'Plan',
    'Stok': 'Stock',
    'Sıra': 'Order',
    'Tema': 'Theme',
    'Tümü': 'All',
    'Vade': 'Due',
    'Veri': 'Data',
    'Yeni': 'New',
    'evet': 'yes',
    'Önem': 'Severity',
    'Özet': 'Summary',
    'İade': 'Return',
    'Aktif': 'Active',
    'Arıza': 'Failures',
    'Aşama': 'Phase',
    'Birim': 'Unit',
    'Bitiş': 'End',
    'Değer': 'Value',
    'Dosya': 'File',
    'Durum': 'Status',
    'Dönem': 'Period',
    'Düşük': 'Low',
    'Geçiş': 'Transition',
    'Hurda': 'Scrap',
    'Kalan': 'Remaining',
    'Kapat': 'Close',
    'Karar': 'Decision',
    'Konum': 'Location',
    'Model': 'Model',
    'Nokta': 'Point',
    'Parça': 'Part',
    'Sapma': 'Deviation',
    'Sayaç': 'Counter',
    'Sonuç': 'Result',
    'Sürüm': 'Version',
    'Sıfır': 'Zero',
    'Tarih': 'Date',
    'Uygun': 'Pass',
    'Yapan': 'Performed by',
    'Zaman': 'Time',
    'hafta': 'week(s)',
    'hayır': 'no',
    'İşlem': 'Action',
    'Şimdi': 'Now',
    '%s gün': '%s days',
    'A Holü': 'Hall A',
    'Aralık': 'Interval',
    'Asgari': 'Minimum',
    'Atandı': 'Assigned',
    'Açılma': 'Opened',
    'Bakiye': 'Balance',
    'Başlık': 'Title',
    'Geçmiş': 'History',
    'Kaldır': 'Remove',
    'Kapalı': 'Closed',
    'Kapsam': 'Scope',
    'Kaydet': 'Save',
    'Klasör': 'Folder',
    'Klüber': 'Klüber',
    'Kritik': 'Critical',
    'Makine': 'Machine',
    'Miktar': 'Quantity',
    'Normal': 'Normal',
    'Notlar': 'Notes',
    'Reddet': 'Reject',
    'Takvim': 'Calendar',
    'Varlık': 'Asset',
    'Vazgeç': 'Cancel',
    'Yüksek': 'High',
    'klasik': 'classic',
    'modern': 'modern',
    'Çevrim': 'Cycles',
    'Şartlı': 'Conditional',
    '%d plan': '%d plans',
    '- yok -': '- none -',
    'Ayarlar': 'Settings',
    'Ayrıntı': 'Detail',
    'Bileşen': 'Component',
    'Değişim': 'Change',
    'Gerekçe': 'Reason',
    'Kapanma': 'Closed',
    'Kapatan': 'Closed by',
    'Kayıt #': 'Record #',
    'Nominal': 'Nominal',
    'Oluştur': 'Create',
    'Planlar': 'Plans',
    'Sorumlu': 'Assignee',
    'Sürüyor': 'In progress',
    'Tam yük': 'Full load',
    'Yapılma': 'Performed',
    'Ölçülen': 'Measured',
    'Öncelik': 'Priority',
    'Üretici': 'Manufacturer',
    'İş emri': 'Work order',
    '%d kayıt': '%d records',
    '%d parça': '%d parts',
    '%d talep': '%d requests',
    'A sınıfı': 'Class A',
    'Açıklama': 'Description',
    'Bekliyor': 'Pending',
    'Bildiren': 'Reported by',
    'Bildirim': 'Reported',
    'Etki yok': 'No impact',
    'Güç (kW)': 'Power (kW)',
    'Plan %s.': 'Plan %s.',
    'Raporlar': 'Reports',
    'Son 6 ay': 'Last 6 months',
    'Talepler': 'Requests',
    'Tolerans': 'Tolerance',
    'Uygunsuz': 'Fail',
    'Yedek al': 'Back up',
    'dk duruş': 'min downtime',
    'sayaç %d': 'counter %d',
    'Önleyici': 'Preventive',
    '%d varlık': '%d assets',
    '- hepsi -': '- all -',
    '- seçin -': '- select -',
    '1 - düşük': '1 - low',
    'Adım ekle': 'Add step',
    'Açık etki': 'Open impact',
    'Başlangıç': 'Start',
    'Beklemede': 'On hold',
    'Boş başla': 'Start empty',
    'Demo veri': 'Demo data',
    'Dosya var': 'File stored',
    'Doğrulama': 'Verification',
    'Düzeltici': 'Corrective',
    'Hazır: %s': 'Ready: %s',
    'Kilometre': 'Kilometres',
    'Kritiklik': 'Criticality',
    'Kullanıcı': 'User',
    'Kök neden': 'Root cause',
    'Plan ekle': 'Add plan',
    'Plan tipi': 'Plan type',
    'Planlanan': 'Planned',
    'Planlandı': 'Planned',
    'Saha kodu': 'Site code',
    'Sertifika': 'Certificate',
    'Seçim yok': 'Nothing selected',
    'Son 12 ay': 'Last 12 months',
    'Tarih seç': 'Pick a date',
    'Tedarikçi': 'Supplier',
    'Varlıklar': 'Assets',
    'Yarım yük': 'Half load',
    'Üst nokta': 'Upper point',
    '%d iş emri': '%d work orders',
    '2 - normal': '2 - normal',
    '3 - kritik': '3 - critical',
    'Duruş (dk)': 'Downtime (min)',
    'Düşük stok': 'Low stock',
    'Dışa aktar': 'Export',
    'Güncelleme': 'Update',
    'Kayıt tipi': 'Record type',
    'Klasörü aç': 'Open folder',
    'Nokta ekle': 'Add point',
    'Parça ekle': 'Add part',
    'Parça kodu': 'Part code',
    'Plan uyumu': 'Plan compliance',
    'Reddedildi': 'Rejected',
    'Son 30 gün': 'Last 30 days',
    'Son 90 gün': 'Last 90 days',
    'Talimatlar': 'Instructions',
    'Tamamlandı': 'Completed',
    'Uygulanmaz': 'Not applicable',
    'Varlık yok': 'No assets',
    'Yapılan iş': 'Work performed',
    'Yeni durum': 'New state',
    'dk işçilik': 'min labor',
    'Çözünürlük': 'Resolution',
    'Üst varlık': 'Parent',
    'Asgari stok': 'Minimum stock',
    'Bakım ekibi': 'Maintenance team',
    'Belirsizlik': 'Uncertainty',
    'Buz noktası': 'Ice point',
    'CSV klasörü': 'CSV folder',
    'Değerlendir': 'Triage',
    'Dış kuruluş': 'External body',
    'Gerçekleşen': 'Actual',
    'HTML raporu': 'HTML report',
    'Hepsini seç': 'Select all',
    'Hizmet dışı': 'Out of service',
    'Kalibrasyon': 'Calibration',
    'Karantinada': 'Quarantined',
    'MTBF (saat)': 'MTBF (hours)',
    'MTTR (saat)': 'MTTR (hours)',
    'Plan sayısı': 'Plan count',
    'SKF Türkiye': 'SKF Türkiye',
    'Son yapılma': 'Last done',
    'Stok değeri': 'Stock value',
    'Varlık ekle': 'Add asset',
    'Yaklaşanlar': 'Coming up',
    'Ölçüm ister': 'Needs value',
    'Üretim yılı': 'Year built',
    'İyileştirme': 'Improvement',
    'İş emirleri': 'Work orders',
    'İş emri #%d': 'Work order #%d',
    'İşaretleyen': 'Checked by',
    '%d açık etki': '%d open impact',
    '%d değerinde': 'at %d',
    '%s kaydı #%d': '%s record #%d',
    '0 ile 3000 g': '0 to 3000 g',
    'Akreditasyon': 'Accreditation',
    'Aktif varlık': 'Active assets',
    'Arıza bildir': 'Report a fault',
    'Arıza sayısı': 'Failure count',
    'Açık iş emri': 'Open work orders',
    'Açılış stoğu': 'Opening stock',
    'Devreye alma': 'Commissioned',
    'Dönüştürüldü': 'Converted',
    'Excel kitabı': 'Excel workbook',
    'Geciken plan': 'Overdue plans',
    'Geri çağırma': 'Recall',
    'Gerçek bitiş': 'Actual end',
    'Güvenilirlik': 'Reliability',
    'Kaynak kayıt': 'Source record',
    'Operatör adı': 'Operator name',
    'Parça kullan': 'Use part',
    'Sayaç birimi': 'Counter unit',
    'Sertifika no': 'Certificate no',
    'Tarih biçimi': 'Date format',
    'Tolerans (±)': 'Tolerance (±)',
    'Tüm dosyalar': 'All files',
    'duraklatıldı': 'paused',
    'her %d birim': 'every %d units',
    'kurulu değil': 'not installed',
    'Ölçüm cihazı': 'Measuring device',
    'Önceki durum': 'Previous state',
    'Üretim hattı': 'Production line',
    'İndiriliyor…': 'Downloading…',
    'İptal edildi': 'Cancelled',
    'İş emri ekle': 'Add work order',
    'İşçilik (dk)': 'Labor (min)',
    '-50 ile 300 C': '-50 to 300 C',
    'Birim maliyet': 'Unit cost',
    'Denetleniyor…': 'Checking…',
    'Değerlendirme': 'Evaluation',
    'Dolum Hattı 1': 'Filling Line 1',
    'Gecikme (gün)': 'Overdue (days)',
    'Güncelle: v%s': 'Update to v%s',
    'Kayıt oluştur': 'Create record',
    'Mihenk yedeği': 'Mihenk backup',
    'Pastörizasyon': 'Pasteurisation',
    'Plan silindi.': 'Plan deleted.',
    'Planı düzenle': 'Edit plan',
    'Ret gerekçesi': 'Rejection reason',
    'Sapma geçmişi': 'Deviation history',
    'Sayaç aralığı': 'Counter interval',
    'Sayaç baskısı': 'Counter pressure',
    'Seri numarası': 'Serial number',
    'Son okuma: %s': 'Last read: %s',
    'Sonuç girildi': 'Result entered',
    'Stok hareketi': 'Stock movement',
    'Sınıflandırma': 'Classification',
    'Sıradaki vade': 'Next due',
    'Uyarı aralığı': 'Warning window',
    'gün önce üret': 'days ahead',
    'Çalışma saati': 'Operating hours',
    'Ölçüm aralığı': 'Measuring range',
    '  açılış stoğu': '  opening stock',
    '(açıklama yok)': '(no description)',
    '- varlık yok -': '- no assets -',
    '-200 ile 660 C': '-200 to 660 C',
    '9000 şişe/saat': '9000 bottles/hour',
    'Durum ve sayaç': 'Status and counter',
    'En büyük sapma': 'Worst deviation',
    'Hangi tablolar': 'Which tables',
    'Kabul edilmedi': 'Refused',
    'Kurulamadı: %s': 'Could not install: %s',
    'Listeyi kaydet': 'Save checklist',
    'Modern görünüm': 'Modern look',
    'NSF H1 sınıfı.': 'NSF H1 grade.',
    'Normal aşınma.': 'Normal wear.',
    'Okumayı kaydet': 'Record reading',
    'Parça maliyeti': 'Parts cost',
    'Parça numarası': 'Part number',
    'Parça silindi.': 'Part deleted.',
    'Taslağı kaydet': 'Save draft',
    'Tolerans (gün)': 'Tolerance (days)',
    'Uygunsuz sonuç': 'Failed result',
    'Yalnızca aktif': 'Active only',
    'Yapılma zamanı': 'Performed at',
    'Yedek parçalar': 'Spare parts',
    'Yeniden işleme': 'Rework',
    'Ön uyarı (gün)': 'Lead days',
    'Önleyici bakım': 'Preventive maintenance',
    'İzlenebilirlik': 'Traceability',
    '%d açık iş emri': '%d open work orders',
    'Ayarları kaydet': 'Save settings',
    'Açılışta tarama': 'Scan at startup',
    'Demo veriyi kur': 'Install demo data',
    'Denetim günlüğü': 'Audit log',
    'Değerlendirildi': 'Triaged',
    'Doğruluk sınıfı': 'Accuracy class',
    'Durumu değiştir': 'Change status',
    'Etkilenen bitiş': 'Affected to',
    'Geciken planlar': 'Overdue plans',
    'Hareketi kaydet': 'Record movement',
    'Hiçbirini seçme': 'Select none',
    'Hurdaya ayrıldı': 'Retired',
    'Kontrol listesi': 'Checklist',
    'Parçayı düzenle': 'Edit part',
    'Tanım bilgileri': 'Identification',
    'Tip özellikleri': 'Type attributes',
    'Varlık silindi.': 'Asset deleted.',
    'Varlığı düzenle': 'Edit asset',
    'Yedek alınamadı': 'Backup failed',
    'bilinmeyen hata': 'unknown error',
    'etkinleştirildi': 'activated',
    'yüklenemedi: %s': 'could not be loaded: %s',
    'Ölçüm noktaları': 'Measurement points',
    'İş emri oluştur': 'Create work order',
    '  · %d açık etki': '  · %d open impact',
    '%d değerlendirme': '%d assessments',
    '- açık olanlar -': '- open only -',
    'Adım bulunamadı.': 'Step not found.',
    'Açık kalibrasyon': 'Open calibration',
    'Derle-ve-Kur.cmd': 'Derle-ve-Kur.cmd',
    'Etkilenen aralık': 'Affected window',
    'Etkilenen kapsam': 'Affected scope',
    'Geri yüklenemedi': 'Restore failed',
    'Gerçek başlangıç': 'Actual start',
    'Henüz kayıt yok.': 'No entries yet.',
    'Kaynak kayıt #%d': 'Source record #%d',
    'Kurulu sürüm: %s': 'Installed version: %s',
    'Nominal kapasite': 'Nominal throughput',
    'Plan bulunamadı.': 'Plan not found.',
    'Plan kaydedildi.': 'Plan saved.',
    'Sayım düzeltmesi': 'Stock count correction',
    'Stok hareketleri': 'Stock movements',
    'Tork kafası yayı': 'Torque head spring',
    'Yedek alındı: %s': 'Backed up: %s',
    'İşçilik dakikası': 'Labor minutes',
    ' · Hazırlayan: %s': ' · Prepared by: %s',
    'Ana yatağı gresle': 'Grease the main bearing',
    'Demo veri kuruldu': 'Demo data installed',
    'Denetlenemedi: %s': 'Could not check: %s',
    'Değerlendirilmedi': 'Not assessed',
    'Düşük stok kalemi': 'Low stock items',
    'Kayıt bulunamadı.': 'Record not found.',
    'Kontrol listeleri': 'Checklists',
    'Parça bulunamadı.': 'Part not found.',
    'Parça kaydedildi.': 'Part saved.',
    'Plan oluşturuldu.': 'Plan created.',
    'Referans standart': 'Reference standard',
    'Satın alma girişi': 'Purchase receipt',
    'Sertifika dosyası': 'Certificate file',
    'Sonuç kaydedildi.': 'Result saved.',
    'Talep bulunamadı.': 'Request not found.',
    'Talep kaydedildi.': 'Request recorded.',
    'Talep reddedildi.': 'Request rejected.',
    'Taramayı çalıştır': 'Run scan',
    'Yedeği geri yükle': 'Restore a backup',
    '  ·  %d düşük stok': '  ·  %d low stock',
    'Bekletme gerekçesi': 'Hold reason',
    'Buz noktası ölçümü': 'Measurement at the ice point',
    'CCP izleme cihazı.': 'CCP monitoring device.',
    'Demo veriyle başla': 'Start with demo data',
    'Düzeltici faaliyet': 'Corrective action',
    'Dışa aktarıldı: %s': 'Exported: %s',
    'Giriş / satın alma': 'Receipt / purchase',
    'Kayıt oluşturuldu.': 'Record created.',
    'Krones Yedek Parça': 'Krones Spare Parts',
    'Parça oluşturuldu.': 'Part created.',
    'Pastörizatör probu': 'Pasteuriser probe',
    'Sonraki duruma geç': 'Move to next state',
    'Talep güncellendi.': 'Request updated.',
    'Varlık bulunamadı.': 'Asset not found.',
    'Varlık kaydedildi.': 'Asset saved.',
    'Varsayılan sorumlu': 'Default assignee',
    'Üretimi durduruyor': 'Stops production',
    '\n\nRet gerekçesi: %s': '\n\nRejection reason: %s',
    '  ·  stok değeri %s': '  ·  stock value %s',
    ' %d kayıt üretildi.': ' %d records generated.',
    '%d açık kalibrasyon': '%d open calibration',
    'Ayarlar kaydedildi.': 'Settings saved.',
    'Demo veriyi temizle': 'Remove demo data',
    'Etkilenen başlangıç': 'Affected from',
    'Kullanılan parçalar': 'Parts used',
    'Listelerde görünsün': 'Show in lists',
    'Modern görünümü kur': 'Install the modern look',
    'Pasifleri de göster': 'Include inactive',
    'Pastörizatör çıkışı': 'Pasteuriser outlet',
    'Sertifika dosyaları': 'Certificate files',
    'Tolerans şartnamesi': 'Tolerance specification',
    'Toplam duruş (saat)': 'Total downtime (hours)',
    'Varlık oluşturuldu.': 'Asset created.',
    'Yalnızca düşük stok': 'Low stock only',
    'İş emri bulunamadı.': 'Work order not found.',
    'İş emri kaydedildi.': 'Work order saved.',
    '%s: %d satır silindi': '%s: %d rows removed',
    '- ölçüm cihazı yok -': '- no measuring devices -',
    'Demo veri kurulamadı': 'The demo data could not be installed',
    'Döner dolum makinesi': 'Rotary filling machine',
    'Dış kuruluş / kapsam': 'External body / scope',
    'Etki değerlendirmesi': 'Impact assessment',
    'Kullanım sınırlaması': 'Usage limitation',
    'Makine çok gürültülü': 'The machine is too noisy',
    'Plandan üretildi: %s': 'Generated from plan: %s',
    'Rapor hazırlandı: %s': 'Report ready: %s',
    'Varlık güvenilirliği': 'Asset reliability',
    'Yazdırılabilir rapor': 'Printable report',
    'Yedek geri yüklendi.': 'Backup restored.',
    'Önce bir plan seçin.': 'Select a plan first.',
    'İş emri oluşturuldu.': 'Work order created.',
    '   En büyük sapma: %g': '   Worst deviation: %g',
    '- noktalardan türet -': '- derive from points -',
    'Bu parça silinsin mi?': 'Delete this part?',
    'Bu plandan kayıt üret': 'Generate records from this plan',
    'Değerlendirmeyi kapat': 'Close assessment',
    'Kalibrasyon uygunluğu': 'Calibration conformity',
    'Kapananları da göster': 'Include closed',
    'Mihenk denetim raporu': 'Mihenk audit report',
    "Mihenk'e hoş geldiniz": 'Welcome to Mihenk',
    'Parça adı zorunludur.': 'Part name is required.',
    'Toplam işçilik (saat)': 'Total labor (hours)',
    'Tümünü uygun işaretle': 'Mark all as pass',
    'Önce bir talep seçin.': 'Select a request first.',
    'İş emrinde kullanıldı': 'Used on a work order',
    '%s tipinin özellikleri': 'Attributes of type %s',
    'Adım metni boş olamaz.': 'The step text cannot be empty.',
    'Açık kalibrasyon kaydı': 'Open calibration records',
    'Bekletme gerekçesi: %s': 'Hold reason: %s',
    'Buz noktasında ±0.05 C': '±0.05 C at the ice point',
    'Duraklat / etkinleştir': 'Pause / activate',
    'En az bir tablo seçin.': 'Select at least one table.',
    'Etki değerlendirmeleri': 'Impact assessments',
    'Güncellemeleri denetle': 'Check for updates',
    'Parça kodu zorunludur.': 'Part code is required.',
    'Tolerans / belirsizlik': 'Tolerance / uncertainty',
    'Varlık adı zorunludur.': 'Asset name is required.',
    'Gıda sınıfı gres (1 kg)': 'Food grade grease (1 kg)',
    'Gıdaya temas eden yüzey': 'Food contact surface',
    'Kayıt zaten bu durumda.': 'The record is already in that state.',
    'Kurulu sürüm güncel: %s': 'The installed version is current: %s',
    'Tarama henüz çalışmadı.': 'The scan has not run yet.',
    'Varlık kodu zorunludur.': 'Asset code is required.',
    '%d adımdan %d tamamlandı': '%d of %d steps done',
    'Etki değerlendirmesi #%d': 'Impact assessment #%d',
    'Kalibrasyon ve doğrulama': 'Calibration and verification',
    'Mevcut bir varlık seçin.': 'Select an existing asset.',
    'Pakette güvensiz yol: %s': 'Unsafe path in the package: %s',
    'Plan başlığı zorunludur.': 'Plan title is required.',
    'Varsayılan ön uyarı günü': 'Default lead days',
    'Önce bir varlık ekleyin.': 'Add an asset first.',
    'İzlenebilirlik referansı': 'Traceability reference',
    '\n\nKurulu sürüm değişmedi.': '\n\nThe installed version is unchanged.',
    'Ana yatak sıcaklığını ölç': 'Measure the main bearing temperature',
    'Aya göre duruş ve işçilik': 'Downtime and labor by month',
    'Açık etki değerlendirmesi': 'Open impact assessments',
    'Bu tipin ek özelliği yok.': 'This type has no extra attributes.',
    'Gerekçeli serbest bırakma': 'Release with justification',
    'Henüz parça kullanılmadı.': 'No parts used yet.',
    'Kayıt %s durumuna alındı.': 'Record moved to %s.',
    'Kısa bir özet zorunludur.': 'A short summary is required.',
    'Sahada çıkan adımı yazın:': 'Write the step that came up on site:',
    'Sayaç okuması kaydedildi.': 'Counter reading saved.',
    'Stok hareketi kaydedildi.': 'Stock movement recorded.',
    'Toplam parça maliyeti: %s': 'Total parts cost: %s',
    'gün gecikme tolere edilir': 'days of delay tolerated',
    'Ana yatak rulmanı 6208-2RS': 'Main bearing 6208-2RS',
    'Dolum valfi contası (EPDM)': 'Filling valve seal (EPDM)',
    'Silinecek demo verisi yok.': 'There is no demo data to remove.',
    'TS EN ISO/IEC 17025, kütle': 'TS EN ISO/IEC 17025, mass',
    'Yeni sürüm yayınlandı: v%s': 'A new version has been published: v%s',
    'Açık etki değerlendirmeleri': 'Open impact assessments',
    'Güncelleme uygulanamadı: %s': 'The update could not be applied: %s',
    'Parça kullanımı kaydedildi.': 'Part usage recorded.',
    'Varlık durumu değiştirildi.': 'Asset status changed.',
    'İş emri %s durumuna alındı.': 'Work order moved to %s.',
    'İş emri başlığı zorunludur.': 'Work order title is required.',
    '  ·  %d sertifika kopyalandı': '  ·  %d certificates copied',
    'Bu durumdan ileri gidilemez.': 'There is no transition out of this state.',
    'Pastörizasyon noktası ölçümü': 'Measurement at the pasteurisation point',
    'Yedek dosyası bulunamadı: %s': 'Backup file not found: %s',
    '%d etki değerlendirmesi açık.': '%d impact assessments are open.',
    'Ekipman bakımı ve kalibrasyon': 'Equipment maintenance and calibration',
    'Koruyucu kapakları yerine tak': 'Refit the guards',
    'Pakette Derle-ve-Kur.cmd yok.': 'The package does not contain Derle-ve-Kur.cmd.',
    'Prob kalibrasyonu, altı aylık': 'Probe calibration, six-monthly',
    'Talepten iş emri oluşturuldu.': 'Work order created from the request.',
    'kapalı (ayarlardan kapatıldı)': 'off (turned off in settings)',
    'yüklendi ama uygulanamadı: %s': 'loaded but could not be applied: %s',
    '<p class="note">Kayıt yok.</p>': '<p class="note">No records.</p>',
    'Açılış taraması yapılamadı: %s': 'The startup scan could not run: %s',
    'Aşınmış iki conta değiştirildi': 'Two worn seals replaced',
    'Miktar sıfırdan farklı olmalı.': 'The quantity must not be zero.',
    'Sertifikayı tara ve kayda ekle': 'Scan the certificate and attach it to the record',
    'Çalışma aralığı boyunca ±1.5 g': '±1.5 g across the working range',
    'Aylık yağlama ve conta kontrolü': 'Monthly greasing and seal check',
    'Enerjiyi kes ve etiketle (LOTO)': 'Isolate and tag out (LOTO)',
    'Etki değerlendirmesi kapatıldı.': 'Impact assessment closed.',
    'Sızıntı testi yap ve sonucu yaz': 'Run a leak test and write down the result',
    'Denetim günlüğüne bu ad yazılır.': 'This name is written into the audit log.',
    'Etki değerlendirmesi bulunamadı.': 'Impact assessment not found.',
    'Etki değerlendirmesi kaydedildi.': 'Impact assessment saved.',
    'Sertifika dosyası bulunamadı: %s': 'Certificate file not found: %s',
    'Önce şu alanlar doldurulmalı: %s': 'These fields are required first: %s',
    '0, 72 ve 90 C noktalarında ±0.5 C': '±0.5 C at the 0, 72 and 90 C points',
    '3 numaralı tork kafasını değiştir': 'Replace torque head 3',
    'Eski sürüm 90 saniyede kapanmadı.': 'The old version did not close within 90 seconds.',
    'Sertifika dosyası bulunamıyor: %s': 'Certificate file is missing: %s',
    'Üç aylık kapaklama kafası servisi': 'Quarterly capping head service',
    'Modern görünüm bileşeni kuruluyor…': 'Installing the modern look component…',
    'Operatör yorumu, ölçüm eklenmemiş.': 'Operator comment, no measurement attached.',
    '  (stok yalnızca hareketle değişir)': '  (stock changes only through movements)',
    'Bu kodu başka bir parça kullanıyor.': 'Another part already uses this code.',
    '"%s" adımı bir ölçüm değeri istiyor.': 'Step "%s" needs a measured value.',
    'Bir varlık kendi üst varlığı olamaz.': 'An asset cannot be its own parent.',
    'Bu kodu başka bir varlık kullanıyor.': 'Another asset already uses this code.',
    'ttkbootstrap çizimini kullan (varsa)': 'Use the ttkbootstrap drawing when available',
    '%s tarihinde %s tarafından kapatıldı.': 'Closed by %s on %s.',
    'Boş bırakılırsa aralıktan hesaplanır.': 'Left empty, it is computed from the interval.',
    'Bu plan için mevcut bir varlık seçin.': 'Select an existing asset for this plan.',
    'Giriş yıldız tekerinde şişe sıkışması': 'Bottle jam on the infeed starwheel',
    'Kontrol terazisi kalibrasyonu, yıllık': 'Checkweigher calibration, annual',
    'Referans termometre aylık doğrulaması': 'Monthly verification of the reference thermometer',
    'Bu kayıt kapalı ve artık düzenlenemez.':
        'This record is closed and can no longer be edited.',
    'Eski sürüm dosyası serbest kalmadı: %s': 'The old version file never unlocked: %s',
    'Oluşturma: %s · Dönem: %s · Mihenk v%s': 'Created: %s · Period: %s · Mihenk v%s',
    'Siparişte; bekleyen iş emrinin sebebi.': 'On order; the reason the work order is on hold.',
    'Valf contalarını aşınmaya karşı incele': 'Inspect the valve seals for wear',
    'Bu pencere yalnızca ilk açılışta çıkar.': 'This window appears only on the first run.',
    'Bu varlıkta sayaç birimi tanımlı değil.': 'This asset has no counter unit.',
    'CIP sonrası dolum altında ürün damlıyor': 'Product dripping under the filler after CIP',
    'Demo verisi zaten var. Önce temizleyin.': 'Demo data already exists. Remove it first.',
    'Her 500 çalışma saatinde valf revizyonu': 'Valve overhaul every 500 running hours',
    'Python %d.%d+ gerekir (bu Python %d.%d)':
        'Python %d.%d+ is required (this is Python %d.%d)',
    'Bu iş emri kapalı ve artık düzenlenemez.':
        'This work order is closed and can no longer be edited.',
    'Dönüştürmeden önce talebi değerlendirin.': 'Triage the request before converting it.',
    'Kullanılan miktar sıfırdan büyük olmalı.': 'The quantity used must be greater than zero.',
    'Varlıkta sayaç birimi tanımlı olmalıdır.': 'The asset must have a counter unit set.',
    'Bu üst varlık hiyerarşide döngü oluşturur.':
        'That parent would create a loop in the hierarchy.',
    'Sayaç okuması bir öncekinden düşük olamaz.':
        'A counter reading cannot be lower than the previous one.',
    'Önce alt varlıkları taşıyın veya kaldırın.': 'Move or remove the child assets first.',
    'İndirme klasörü kilitli dosyalarla dolu: %s':
        'The download folder is full of locked files: %s',
    'E2 sınıfı ağırlıklar, sertifika UME-2024-0912':
        'Class E2 weights, certificate UME-2024-0912',
    'Veri klasöründe %d sertifika dosyası duruyor.':
        '%d certificate files are kept in the data folder.',
    'Bu plan silinsin mi? Üretilmiş kayıtlar kalır.':
        'Delete this plan? Records already generated are kept.',
    'Bu varlık silinsin mi? Bu işlem geri alınamaz.':
        'Delete this asset? This cannot be undone.',
    'Python biçimi, örneğin %Y-%m-%d ya da %d.%m.%Y': 'Python format, e.g. %Y-%m-%d or %d.%m.%Y',
    'Uygulama açılırken vadesi gelen kayıtları üret':
        'Generate due records when the application opens',
    'Varlık etiketinde yazan benzersiz tanımlayıcı.':
        'The unique identifier printed on the asset tag.',
    'Aylık yağlama ve conta kontrolü (önceki çevrim)':
        'Monthly greasing and seal check (previous cycle)',
    'Ekipman bakımı, kalibrasyon ve doğrulama takibi':
        'Equipment maintenance, calibration and verification',
    '<h2>%s <span class="note">(%d satır)</span></h2>':
        '<h2>%s <span class="note">(%d rows)</span></h2>',
    'Sayaç tabanlı plan bir sayaç aralığı gerektirir.':
        'A counter based plan needs a counter interval.',
    'Sertifika dosyalarını da çıktı klasörüne kopyala':
        'Copy the certificate files into the output folder as well',
    '%s durumundan %s durumuna geçişe izin verilmiyor.':
        'Transition from %s to %s is not allowed.',
    'Kuruldu. Değişiklik için uygulamayı yeniden açın.':
        'Installed. Reopen the application for the change to take effect.',
    'Kütük şu anda boş. İki şekilde başlayabilirsiniz.':
        'The register is empty. There are two ways to start.',
    'Sayaç tabanlı plan bağlayabilmek için gereklidir.':
        'Required before a counter based plan can be attached.',
    'Yazdırmak ya da PDF olarak kaydetmek için Ctrl+P.': 'Press Ctrl+P to print or save as PDF.',
    '  %d kayıtta dosya yolu var ama dosya bulunamıyor.':
        '  %d records name a file that cannot be found.',
    '%s geçerli bir tarih olmalı (ör. 2026-11-25 09:30).':
        '%s must be a valid date (e.g. 2026-11-25 09:30).',
    'Kapaklama her beşinci şişede gevşek kapak bırakıyor':
        'The capper leaves a loose cap on every fifth bottle',
    'Sertifika dosyası çok büyük (%.1f MB, sınır %d MB).':
        'The certificate file is too large (%.1f MB, limit %d MB).',
    'Şartlı bir sonucun kapatılabilmesi için zorunludur.':
        'Required before a conditional result can be closed.',
    '8 varlık, dört seviyeli hiyerarşi, üçü ölçüm cihazı.':
        '8 assets in a four level hierarchy, three of them measuring devices.',
    'Referans termometreye karşı üç nokta: 0, 72 ve 90 C.':
        'Three points against the reference thermometer: 0, 72 and 90 C.',
    '%d kritik kontrol adımı hâlâ bekliyor ya da uygunsuz.':
        '%d critical checklist steps are still pending or failed.',
    'Bu dosya bir Mihenk yedeği değil (eksik tablolar: %s)':
        'This file is not a Mihenk backup (missing tables: %s)',
    'Kapatma, etki değerlendirmesi kapanana kadar engelli.':
        'Closing is blocked until the impact assessment is closed.',
    'Yedek tork kafası siparişte, tahmini teslim iki hafta.':
        'A replacement torque head is on order, estimated delivery two weeks.',
    '#%d numaralı başarısız kayıt sonrası otomatik karantina':
        'Automatic quarantine after failed record #%d',
    'Gıdaya temas eder; FDA 21 CFR 177.2600 belgesi dosyada.':
        'Food contact; the FDA 21 CFR 177.2600 certificate is on file.',
    'Kapatılmış bir etki değerlendirmesi artık düzenlenemez.':
        'A closed impact assessment can no longer be edited.',
    '%d etki değerlendirmesi açıkken bu varlık hizmete dönemez.':
        'This asset cannot return to service while %d impact assessments are open.',
    'Açılış taraması: %d iş emri, %d kalibrasyon kaydı üretildi.':
        'Startup scan: %d work orders and %d calibration records generated.',
    'Demo veri kuruldu. Ayarlar ekranından tek tıkla temizlenir.':
        'Demo data installed. One click on the Settings screen removes it.',
    'Kritik işaretli bir adım tamamlanmadan iş emri kapatılamaz.':
        'A work order cannot be completed while a step marked critical is unfinished.',
    'Kütükte aktif parça yok. Yedek parçalar ekranından ekleyin.':
        'No active parts in the register. Add them from the Spare parts screen.',
    'Stok eksiye düşemez: elde %s %s var, %s %s çıkış isteniyor.':
        'Stock cannot go negative: %s %s on hand, %s %s requested.',
    'Valf contası değişimi (duraklatıldı, yedek parça siparişte)':
        'Valve seal replacement (paused, spare part on order)',
    'Bir vardiyada üç sıkışma. Kılavuz ray ayarı kaçmış olabilir.':
        'Three jams in one shift. The guide rail setting may have drifted.',
    'Sessiz güncelleme yalnızca derlenmiş EXE için uygulanabilir.':
        'A silent update can only be applied to a compiled EXE.',
    'Gürültü 78 dB ölçüldü, sınır içinde. Bakım işlemi gerekmiyor.':
        'Noise measured at 78 dB, within limits. No maintenance action needed.',
    'Kapatılmış veya iptal edilmiş bir iş emri artık düzenlenemez.':
        'A closed or cancelled work order can no longer be edited.',
    '4 talep: açık, değerlendirilmiş, reddedilmiş ve dönüştürülmüş.':
        '4 requests: open, triaged, rejected and converted.',
    'Asgarinin altında bırakıldı: düşük stok uyarısı burada görülür.':
        'Deliberately left below the minimum, so the low stock warning shows here.',
    'Bu aralıkta hangi hatlar, ürünler ve partiler bu cihazdan geçti.':
        'Which lines, products and batches passed through this device inside the window.',
    'Tarama bitti: %d iş emri, %d kalibrasyon kaydı, %d plan atlandı.':
        'Scan finished: %d work orders, %d calibration records, %d plans skipped.',
    'Her sabah yerde küçük birikinti. Valf contasından şüpheleniliyor.':
        'A small pool on the floor every morning. The valve seal is the suspect.',
    '24 dolum valfinin tamamı sökülür, temizlenir ve yeniden oturtulur.':
        'All 24 filling valves are stripped, cleaned and reseated.',
    'Bu parçanın stok hareketi var, silinemez. Bunun yerine pasife alın.':
        'This part has stock movements and cannot be deleted. Make it inactive instead.',
    'Son tarama: %s — %d iş emri, %d kalibrasyon kaydı, %d plan atlandı.':
        'Last scan: %s — %d work orders, %d calibration records, %d plans skipped.',
    'Tarama: %d iş emri, %d kalibrasyon kaydı üretildi, %d plan atlandı.':
        'Scan: %d work orders and %d calibration records generated, %d plans skipped.',
    'v%s yayınlanmış ama paket henüz doğrulanamıyor (SHA-256 özeti yok).':
        'v%s has been published but the package cannot be verified yet (no SHA-256 digest).',
    'Bu varlık hurdaya ayrılsın mı? Hurdaya ayrılan varlık geri alınamaz.':
        'Retire this asset? A retired asset cannot be brought back.',
    'Yeni sürüm var: v%s — durum çubuğundaki Güncelle düğmesiyle kurulur.':
        'A new version is available: v%s — install it with the Update button in the status bar.',
    'Gece vardiyasında başladı. 3 numaralı kafada tork tutarsız görünüyor.':
        'Started on the night shift. Torque on head 3 looks inconsistent.',
    'Üç vardiya çalışır. Sayaç her vardiya devrinde HMI ekranından okunur.':
        'Runs three shifts. The counter is read off the HMI screen at every shift change.',
    'Bu varlığın bakım geçmişi var, silinemez. Bunun yerine hurdaya ayırın.':
        'This asset has maintenance history and cannot be deleted. Retire it instead.',
    'Uygunluğu gerçekten kanıtlayan son sonuç. Etki aralığı buradan başlar.':
        'The last result that actually proved conformity. The impact window starts here.',
    'Uygunsuz seçmek varlığı karantinaya alır ve etki değerlendirmesi açar.':
        'Choosing Fail quarantines the asset and opens an impact assessment.',
    '<p class="note">İlk %d satır gösterildi; tamamı Excel çıktısındadır.</p>':
        '<p class="note">First %d rows shown; the full set is in the Excel output.</p>',
    '4 yedek parça kütüğe girdi; biri asgarinin altında, biri tükenmiş durumda.':
        '4 spare parts entered the register; one is below its minimum, one is out of stock.',
    'Prob pastörizasyon noktasında düşük okuyor. Rutin doğrulamada fark edildi.':
        'The probe reads low at the pasteurisation point. Noticed during routine verification.',
    'Bir plandan gelen iş emrini tamamlamak, o planı sıradaki vadesine ilerletir.':
        'Completing a work order that came from a plan rolls that plan forward to its next due date.',
    'Bu seviyenin altına düşünce panoda uyarı çıkar. 0 yazarsanız uyarı verilmez.':
        'A warning appears on the dashboard below this level. Write 0 for no warning.',
    'Güncelleme uygulanamadı: %s\n\nYeni sürüm şu dosyada, doğrudan açabilirsin:\n%s':
        'The update could not be applied: %s\n\nThe new version is in this file, you can open it directly:\n%s',
    'Tolere edilen gecikme yalnızca gecikme raporunu etkiler, vadeyi değiştirmez.':
        'The tolerated delay only affects the overdue report; it never moves the due date.',
    'Kapatma korumasını göstermek için kullanım sınırlaması bilerek boş bırakıldı.':
        'The usage limitation is left empty on purpose, to show the closing guard.',
    'Kodu DEMO- ile başlayan bütün varlıklar ve onlara bağlı kayıtlar silinsin mi?':
        'Remove every asset whose code starts with DEMO- and the records attached to them?',
    'Şartlı bir sonuç kapatılmadan önce yazılı bir kullanım sınırlaması gerektirir.':
        'A conditional result needs a written usage limitation before it can be closed.',
    'Bu varlıkta sayaç birimi tanımlı değil, bu yüzden sayaç tabanlı plan taşıyamaz.':
        'This asset has no counter unit, so it cannot carry a counter based plan.',
    'Ölçüm cihazları kalibrasyon planı taşır ve etki değerlendirmesi tetikleyebilir.':
        'Measuring devices carry calibration plans and can trigger impact assessments.',
    'Göstergeler seçilen dönemdeki kayıtlardan hesaplanır; tahmin ya da örnekleme yok.':
        'Every figure is computed from the records in the selected period; nothing is estimated or sampled.',
    'Excel çıktısında her tablo ayrı bir sayfaya, CSV çıktısında ayrı bir dosyaya gider.':
        'In the Excel output each table goes to its own sheet; in the CSV output, to its own file.',
    'Uygunluğu gerçekten kanıtlayan son kayda göre dolduruldu. Yalnızca kanıtla daraltın.':
        'Pre-filled from the last record that actually proved conformity. Narrow it only with evidence.',
    'Başarısız bir kalibrasyon ancak etki değerlendirmesi kapandıktan sonra kapatılabilir.':
        'A failed calibration can only be closed after its impact assessment is closed.',
    'Önleyici plan iş emri üretir. Kalibrasyon ve doğrulama planı kalibrasyon kaydı üretir.':
        'A preventive plan generates work orders. Calibration and verification plans generate calibration records.',
    'Bu kayıt uygunsuz. Varlık otomatik karantinaya alındı ve bir etki değerlendirmesi açıldı.':
        'This record failed. The asset was quarantined automatically and an impact assessment was opened.',
    'Açık her değerlendirme, ilgili varlığı hizmet dışında tutar. Kapatma bir karar gerektirir.':
        'Every open assessment holds its asset out of service. Closing one requires a decision.',
    'Güncelleyici başlatılamadı (güvenlik yazılımı engellemiş olabilir). Kurulu sürüm değişmedi.':
        'The updater could not start (security software may have blocked it). The installed version is unchanged.',
    'Seçilen dosya Mihenk veri klasörüne kopyalanır; özgün dosya taşınsa bile kayıt boşa düşmez.':
        'The chosen file is copied into the Mihenk data folder, so the record survives if the original is moved.',
    'Değerlendirme kapatılsın mı? Kapatma varlığı karantinadan çıkarır ve kayıt düzenlenemez olur.':
        'Close the assessment? Closing releases the asset from quarantine and locks the record.',
    'Bu iş emrinde kontrol listesi yok. Plana bir şablon tanımlarsanız sonraki iş emirleri onu taşır.':
        'This work order has no checklist. Define a template on the plan and later work orders will carry it.',
    'v%s indirilip kurulsun mu?\n\nUygulama kısa süre kapanıp yeniden açılacak. Kayıtlarınıza dokunulmaz.':
        'Download and install v%s?\n\nThe application will close briefly and reopen. Your records are untouched.',
    'Bu sonuç uygunsuz. Varlık karantinaya alınacak ve etki değerlendirmesi açılacak.\n\nDevam edilsin mi?':
        'This result is a failure. The asset will be quarantined and an impact assessment will be opened.\n\nContinue?',
    'Kayıtlar: %d varlık · %d plan · %d talep · %d iş emri · %d kalibrasyon · %d etki · %d günlük satırı':
        'Records: %d assets · %d plans · %d requests · %d work orders · %d calibration · %d impact · %d log rows',
    'MTBF iki arızası olmayan varlıkta hesaplanamaz; o satırda boş kalır. Sıfır yazmak yanıltıcı olurdu.':
        'MTBF cannot be computed for an asset with fewer than two failures, so that cell stays empty. Writing zero would mislead.',
    'Giriş için artı, çıkış için eksi bir sayı yazın. İş emrinde kullanım, iş emri penceresinden işlenir.':
        'Write a positive number for a receipt, a negative one for an issue. Usage on a work order is recorded from the work order window.',
    'Çizim: %s — %s. Bileşen yoksa uygulama klasik çizimle sorunsuz çalışır; renkler iki yolda da aynıdır.':
        'Drawing: %s — %s. Without the component the application runs fine with the classic drawing; the colours are the same either way.',
    'Ana yatak greslendi. İki valf contasında aşınma görüldü ve değiştirildi. Test çalışmasında sızıntı yok.':
        'The main bearing was greased. Two valve seals showed wear and were replaced. No leak on the test run.',
    'Talep yok. Sahadan gelen bir arızayı buraya bildirin; değerlendirildikten sonra iş emrine dönüştürülür.':
        'No requests. Report a fault from the floor here; once triaged it becomes a work order.',
    'Etki değerlendirmesi yok. Bu kayıtlar elle açılmaz: bir kalibrasyon uygunsuz çıktığında kendiliğinden açılır.':
        'No impact assessments. These are never opened by hand: one opens automatically when a calibration fails.',
    'Yedek parça kütüğü boş. Parça ekleyin; iş emri penceresinden kullanım işlediğinizde stok kendiliğinden düşer.':
        'The spare parts register is empty. Add parts; stock drops on its own when you record usage from a work order.',
    'Bu varlık başarısız bir kalibrasyon sonrası karantinada. Açık her etki değerlendirmesi kapanmadan hizmete dönemez.':
        'This asset is quarantined after a failed calibration. It cannot return to service until every open impact assessment is closed.',
    'Kalibrasyon: biri kapalı uygun, biri şartlı, biri uygunsuz (%sTHM-01 karantinaya alındı, etki değerlendirmesi açık).':
        'Calibration: one closed as a pass, one conditional, one failed (%sTHM-01 is quarantined and its impact assessment is open).',
    '1. Enerjiyi kes ve etiketle.\n2. Ana yatağı gresle.\n3. Valf contalarını aşınmaya karşı incele.\n4. Sızıntı varsa kaydet.':
        '1. Isolate and tag out.\n2. Grease the main bearing.\n3. Inspect the valve seals for wear.\n4. Record any leak.',
    "Açık iş emri yok. Planlar vadesi geldiğinde kendiliğinden üretir; Pano'daki Taramayı çalıştır düğmesi bunu elle tetikler.":
        'No open work orders. Plans generate them when they fall due; the Run scan button on the Dashboard triggers it by hand.',
    'Henüz plan yok. Bir varlığa plan bağlayın: önleyici plan iş emri, kalibrasyon ve doğrulama planı kalibrasyon kaydı üretir.':
        'No plans yet. Attach a plan to an asset: a preventive plan generates work orders, a calibration or verification plan generates calibration records.',
    '%s tolerans dışında ölçüm yaptı. %s ile %s arasında ölçtüğü her şey, bu değerlendirme bir karara bağlanana kadar şüphelidir.':
        '%s measured outside tolerance. Everything it measured between %s and %s is in doubt until this assessment reaches a decision.',
    '7 plan: biri gecikmiş, biri sayaç tabanlı, biri yaklaşan, biri uzak, biri duraklatılmış. İkisinde kontrol listesi şablonu var.':
        '7 plans: one overdue, one counter based, one approaching, one distant, one paused. Two carry a checklist template.',
    'Toleransı girilmemiş bir nokta tek başına uygunluğu kanıtlamaz. Tolerans dışındaki tek bir nokta kaydın tamamını uygunsuz yapar.':
        'A point without a tolerance cannot prove conformity on its own. A single point outside tolerance fails the whole record.',
    'İş emirleri sürüyor, beklemede ve kapalı durumlarında bırakıldı; kapalı olan plana bağlı, bu yüzden plan uyumu hesaplanabiliyor.':
        'Work orders are left in progress, on hold and closed; the closed one is attached to its plan, so plan compliance can be computed.',
    'Bu plandan üretilen her iş emri bu listeyi taşır. Liste sonradan değişirse eski iş emirleri değişmez; her biri kendi anını tutar.':
        'Every work order generated from this plan carries this list. If the list changes later, past work orders do not; each keeps its own moment.',
    '<footer>Mihenk v%s · AGFO · Bu rapor %s tarihinde üretildi. Kayıtların tamamı uygulamanın veritabanındadır.</footer></body></html>':
        '<footer>Mihenk v%s · AGFO · This report was produced on %s. The complete records live in the application database.</footer></body></html>',
    'Açık kalibrasyon kaydı yok. Kalibrasyon planı vadesi gelince kayıt üretir; plan dışı bir ölçüm için Kayıt oluştur düğmesini kullanın.':
        'No open calibration records. A calibration plan generates one when it falls due; use Create record for an unplanned measurement.',
    'İlk açılışta demo veri ya da boş başlangıç soran karşılama penceresi, boş listelerde yönlendirme ve açılışta sessiz güncelleme denetimi.':
        'A welcome window on the first run offering demo data or an empty start, guidance on empty lists, and a silent update check at startup.',
    'Mevcut kayıtların yerine bu yedek konacak.\n\nŞu anki veritabanının bir kopyası .pre-restore uzantısıyla yanında bırakılır. Devam edilsin mi?':
        'This backup will replace your current records.\n\nA copy of the current database is left beside it with a .pre-restore extension. Continue?',
    'Şimdi deneyin: %sTHM-01 varlığını aktife almaya ve uygunsuz kaydını kapatmaya çalışın. Etki değerlendirmesi kapanana kadar ikisi de reddedilmeli.':
        'Try it now: attempt to set asset %sTHM-01 back to active and to close its failed record. Both must be refused until the impact assessment is closed.',
    'Kütük boş. Sağ üstteki Varlık ekle ile başlayın; ölçüm cihazları için "Ölçüm cihazı" kutusunu işaretleyin, kalibrasyon planı ancak öyle bağlanabilir.':
        'The register is empty. Start with Add asset at the top right; tick "Measuring device" for instruments, otherwise a calibration plan cannot be attached.',
    '<p class="note">Plan uyumu: %d iş emrinden %d tanesi zamanında kapandı, %d tanesi geç kaldı. Kalibrasyon: %d kayıttan %d uygun, %d şartlı, %d uygunsuz.</p>':
        '<p class="note">Plan compliance: %d of %d work orders closed on time, %d were late. Calibration: %d of %d records passed, %d conditional, %d failed.</p>',
    'Plan uyumu: %d iş emrinden %d tanesi zamanında kapandı, %d tanesi geç kaldı, %d tanesi hâlâ açık.    Kalibrasyon: %d kayıttan %d uygun, %d şartlı, %d uygunsuz.':
        'Plan compliance: %d of %d work orders closed on time, %d were late, %d are still open.    Calibration: %d of %d records passed, %d conditional, %d failed.',
    "Yeni sürüm var: v%s.\n\nKaynaktan çalıştığın için uygulama kendi kendini değiştiremez. GitHub'dan Kurulum ZIP'ini indirip Derle-ve-Kur.cmd çalıştırman gerekiyor.":
        'A new version is available: v%s.\n\nBecause you are running from source the application cannot replace itself. Download the installation ZIP from GitHub and run Derle-ve-Kur.cmd.',
    'Doğrudan kendi ekipmanınızı girersiniz. Önce Varlıklar ekranından bir varlık, sonra ona bir plan ekleyin; planlar vadesi geldiğinde iş emri ya da kalibrasyon kaydı üretir.':
        'You enter your own equipment straight away. Add an asset from the Assets screen, then a plan on it; plans generate work orders or calibration records when they fall due.',
    'Birbirine bağlı örnek bir set kurar: sekiz varlık, yedi plan, dört talep, iş emirleri ve biri uygunsuz üç kalibrasyon kaydı. Temizlik yalnızca kodu DEMO- ile başlayan varlıkları ve onlara bağlı kayıtları siler.':
        'Installs a connected sample set: eight assets, seven plans, four requests, work orders and three calibration records, one of them failing. Cleanup removes only the assets whose code starts with DEMO- and the records attached to them.',
    'Modern görünüm (ttkbootstrap) ve dört yeni yetenek: plana bağlı kontrol listesi şablonları ve iş emrinde işaretleme, yedek parça kütüğü ile stok hareketleri, plan uyumu / MTBF / MTTR / duruş eğilimi / sapma geçmişi göstergeleri, ve denetime hazır çıktı (Excel, CSV, yazdırılabilir rapor, veri klasöründe saklanan sertifika dosyaları).':
        'A modern look (ttkbootstrap) and four new capabilities: checklist templates on plans with tick-off on the work order, a spare parts register with stock movements, plan compliance / MTBF / MTTR / downtime trend / deviation history metrics, and audit-ready output (Excel, CSV, a printable report, certificate files kept in the data folder).',
    'İlk sürüm. Hiyerarşik varlık kütüğü ve tipe göre özellikler, önleyici bakım ile kalibrasyon ve doğrulamayı tek tabloda toplayan plan yapısı, talep ve iş emri akışları, ölçüm noktası tablosundan tolerans değerlendirmesi, uygunsuz sonuçta otomatik karantina ve etki değerlendirmesi, niyet ve sonuç çiftiyle denetim günlüğü, SQLite yedekleme ve demo veri seti.':
        'First release. A hierarchical asset register with per-type attributes, one plan structure covering preventive maintenance as well as calibration and verification, request and work order flows, tolerance evaluation from a measurement point table, automatic quarantine and impact assessment on a failed result, an audit log that pairs intent with result, SQLite backups and a demo data set.',
    'Bir dolum hattının sekiz varlığı, yedi planı, dört talebi ve üç kalibrasyon kaydı kurulur. Kayıtlardan biri bilerek uygunsuzdur: varlığı karantinaya almış ve bir etki değerlendirmesi açmıştır, böylece uygulamanın asıl kuralını çalışırken görürsünüz.\n\nBütün demo varlıklarının kodu DEMO- ile başlar ve Ayarlar ekranından tek tıkla temizlenir; kendi kayıtlarınıza dokunmaz.':
        "Installs eight assets, seven plans, four requests and three calibration records from a filling line. One record fails on purpose: it quarantines its asset and opens an impact assessment, so you see the application's central rule at work.\n\nEvery demo asset code starts with DEMO- and one click on the Settings screen removes them; your own records are untouched.",
}


set_language(_startup_language())
