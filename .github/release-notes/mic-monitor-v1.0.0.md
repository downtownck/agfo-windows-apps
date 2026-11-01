## AGFO Mic Monitor 1.0.0: Mikrofonu gecikmesiz dinleme ve kayıt

Windows'un "Bu cihazı dinle" özelliği sesi Windows ses motorundan ve efektlerden (Voice Clarity, Nahimic, iyileştirmeler) geçirdiği için 50–100+ ms gecikiyor. Mic Monitor bu yolu atlıyor.

- **WASAPI özel mod + RAW akış:** Ses doğrudan mikrofondan kulaklığa gidiyor; Windows'un karıştırıcısı ve efekt katmanları atlanıyor. Kablolu kulaklıkla tipik gecikme 6–20 ms.
- **Otomatik geri düşme:** Özel mod reddedilirse sırasıyla özel giriş + paylaşımlı çıkış, paylaşımlı RAW, ayrı akış ve MME deneniyor. Denemeler "Ayrıntılar" penceresinde ve günlükte görünüyor.
- **Aynı anda kayıt:** Duyduğunuz ses WAV olarak (24 ya da 16 bit, mono ya da stereo) kaydediliyor. Kayıt ayrı iş parçacığında yazıldığı için dinlemeyi aksatmıyor. "Dinlemeyi sustur" ile yalnızca kayıt yapılabiliyor.
- **Canlı ayarlar:** Mikrofon kazancı, dinleme sesi ve kanal seçimi akışı kesmeden uygulanıyor. Seviye göstergesi ve kırpılma uyarısı var.
- **Uyarılar:** Bluetooth / Hands-Free çıkışı ve hoparlörden geri besleme riski için uyarı gösteriliyor.
- **Kendini onarma:** Cihaz çıkarılır ya da uyku sonrası akış düşerse yeniden açılıyor.
- **ASIO desteği** (isteğe bağlı): ASIO4ALL, FlexASIO ve ses kartı ASIO sürücüleri.
- Tek tıkla GitHub güncellemesi; yönetici gerektirmeyen kurulum ve kaldırma.

Kurulum: `AGFO-Mic-Monitor-v1.0.0-Kurulum.zip` dosyasını açıp `Derle-ve-Kur.cmd`'ye çift tıklayın.
