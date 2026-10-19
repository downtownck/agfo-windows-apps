## AGFO AI Editor 1.4.14: Gerçek üretici kılavuzlarıyla denendi

Tenda AC8 kurulum kılavuzu (tek sayfa, iki katlamalı yüz, 8 sütun, tablolar, ekran görüntüleri, çok dilli yasal metin) ve bir LTE yönlendirici kılavuzuyla denendi.

- **Kalın yazı hatası:** Bazı PDF'lerde yazı tipi "Regular" olduğu halde ağırlığı kalın (740) bildiriliyordu; bütün çeviri kalın çıkıyordu. Artık yazı tipi adı (Regular/Light/Book) esas alınıyor.
- **Tek nesnede iki başlık:** İki sütunun başlığı PDF'te tek metin nesnesiyse ("I Connect the router … II Connect the router to the internet") tek satır sayılıp birinci sütundan başlayarak yazılıyordu. Artık büyük boşlukta bölünüyor; her başlık kendi sütununda çevriliyor. Parçalardan biri çevrilmese bile kaybolmuyor.
- **Etiketli satırlar:** Kalın bir etiketle başlayan satırlar ("Polski: …", "Deutsch: …", "Q1: …") ayrı paragraf olarak kalıyor, birbirine eklenmiyor.
- **Asılı girinti:** Tire/madde ile başlayan ve devamı içeriden gelen satırlarda girinti korunuyor.
- **Satır taşması:** Yan sütundaki büyük başlıkla aynı yükseklikteki satırlar artık başlığın üstüne taşmıyor.
- **Okunamayan metin:** Yazı tipinin Unicode eşlemesi bozuk olan metin (bu kılavuzdaki Yunanca bölüm) modele gönderilmiyor ve PDF'te yerinde bırakılıyor; önceden kutu (□) olarak yeniden yazılıyordu.
- Not: Metni tamamen çizgiye (eğriye) çevrilmiş PDF'lerde (LTE yönlendirici kılavuzu) çevrilecek metin yoktur; uygulama bunu bildirir. Bunlar için metin tanıma (OCR) gerekir.
