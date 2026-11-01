## AGFO Mic Monitor 1.0.1: Kulaklık takıp çıkarınca devreye girme

Düzeltilen sorun: kulaklık takılınca dinleme kulaklığa geçmiyordu.

Nedeni:
- Ses kütüphanesi (PortAudio) aygıt listesini yalnızca açılışta okuyordu; kulaklık takılınca Windows'un açtığı yeni aygıtı görmüyordu.
- Kulaklık takılınca Windows özel moddaki akışı geçersiz kılıyor. Akış hata vermeden sessizce duruyordu; uygulama bunu fark etmiyordu.

1.0.1'deki değişiklikler:
- **Aygıt izleme:** Kulaklık ya da USB mikrofon takılıp çıkarılması ve varsayılan aygıtın değişmesi saniyede bir kontrol ediliyor. Değişiklik olunca aygıt listesi Windows'tan yeniden okunuyor ve dinleme yeni aygıtla kendiliğinden yeniden başlıyor.
- **Kulaklığa otomatik geçiş:** Çıkış olarak hoparlör seçiliyken kablolu ya da USB bir kulaklık takılırsa uygulama kulaklığa geçiyor. HDMI monitör ve Bluetooth aygıtlarına otomatik geçilmiyor.
- **Geri besleme koruması:** Kulaklık çıkarılınca ses hoparlöre dönüp mikrofonun ötmemesi için dinleme duraklatılıyor. Kulaklık yeniden takılınca kendiliğinden devam ediyor. Seçtiğiniz aygıt bağlı değilken listede "bağlı değil" olarak görünüyor, seçim kaybolmuyor.
- **Takılan akış algılama:** Yarım saniyelik aralıklarla üst üste üç kontrolde ses gelmezse akış takılmış sayılıyor. Uygulama ses kütüphanesini yeniden başlatıp akışı artan beklemeyle (0,4 / 1,5 / 4 sn) yeniden açıyor.
- Bazı Realtek sürücüleri takılı kulaklığı da "Hoparlör" adıyla gösteriyor. Hoparlör uyarısına bu durumu açıklayan bir not eklendi.
- "Yenile" düğmesi dinleme sürerken de çalışıyor.

Güncelleme: uygulamada "Güncelleme…" > "Şimdi güncelle". Ayarlarınız korunur.
