## AGFO Mic Monitor 1.2.0: Altyapı üzerine hizalı vokal kaydı ve çalışan güncelleme

### Yeni: Altyapı sekmesi
Enstrümantal altyapı çalıp üzerine şarkı söyleyerek kayıt yapabilirsiniz.
- **Desteklenen dosyalar:** WAV, MP3, FLAC, OGG, AIFF. Dosya, ses kartının örnekleme hızına yüksek kaliteyle dönüştürülür (hata payı -85 dB'nin altında, 4 dakikalık şarkı 1 saniyede hazır).
- **Altyapı Mic Monitor'ün içinden çalar.** Özel modda kulaklık çıkışını Mic Monitor tuttuğu için başka bir programdan çalınan altyapı duyulmuyordu; artık bu sorun yok.
- **Kayıt ve altyapı aynı anda başlar.** "Kaydı başlat" altyapıyı baştan çalar.
- **Gecikme otomatik düzeltilir.** Altyapıyı kulağınıza ulaşma gecikmesiyle duyarsınız, sesiniz de mikrofondan gecikmeyle gelir. Mic Monitor bu gidiş-dönüş süresini bilir ve vokalden düşer. Vokal dosyası altyapıyla örneği örneğine aynı noktadan başlar; Cool Edit, Audition ya da Audacity'de altyapının altına koyduğunuzda tam oturur. Gerekirse "Kayıt kaydırma" ile ince ayar yapılabilir.
- **İki dosya çıkar:**
  - `Kayit_..._vokal.wav`: yalnızca sesiniz, hizalı. Varsayılan olarak efektsiz kaydedilir.
  - `Kayit_..._karisim.wav`: altyapı ve vokal birlikte. Kulaklıkta duyduğunuz yankı ve reverb de karışıma eklenir. Ses hiçbir yerde -1 dBFS'yi aşmaz.
- Altyapı bitince kayıt kendiliğinden durur (isteğe bağlı). Altyapının sesi ayrı ayarlanır; çal, durdur ve başa sar düğmeleri var.

### Düzeltildi: GitHub'dan otomatik güncelleme
Önceki sürümlerde güncelleme denetimi hiç çalışmıyordu. Arka planda iş başlatan bir yardımcı uygulamaya kopyalanmamıştı; hem açılıştaki denetim hem "GitHub'da denetle" düğmesi sessizce başarısız oluyordu. 1.0.3'teki 6 saatlik önbellek düzeltmesi gerçek bir sorunu gideriyordu ama asıl neden bu değildi. Artık güncelleme yolu testlerde baştan sona çalıştırılıyor.

**Önemli:** 1.0.0 ile 1.1.0 arasındaki sürümler kendini güncelleyemez. Bu sürümü bir kez elle kurun: `AGFO-Mic-Monitor-v1.2.0-Kurulum.zip` dosyasını açıp `Derle-ve-Kur.cmd`'yi çalıştırın. Ayarlarınız korunur. Sonraki güncellemeler uygulama içinden gelecektir.
