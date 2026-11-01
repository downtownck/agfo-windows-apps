## AGFO Mic Monitor 1.5.0: Kamera, MP4 ve MP3

**Kamera** (yeni Kamera sekmesi):
- Bilgisayara bağlı kameralar listelenir. Çözünürlük seçenekleri: 720p, 1080p, 640x480 ya da otomatik.
- Önizleme prompter / söz ekranında seçtiğiniz köşede görünür: sağ üst, sol üst, sağ alt ya da sol alt; küçük, orta ya da büyük boyutta. Ayna görüntüsüdür, kendinizi doğal görürsünüz. Kayıt sırasında çerçevesi kırmızı olur.
- Kamera açıkken prompter metni kameranın altında kalmayacak şekilde yeniden bölümlenir.
- Kamera seçilen çözünürlüğü desteklemezse kendi çözünürlüğüyle yeniden açılır.

**MP4:**
- "Kayıtta kamerayı da kaydet" seçiliyse görüntü H.264 olarak kaydedilir.
- Kayıt bitince görüntü ile ses MP4'te birleştirilir. Altyapılı kayıtta karışım, değilse ses kullanılır.
- Görüntü ile sesin başlama farkı ölçülür ve otomatik düzeltilir. Gerekirse "Görüntü-ses" sürgüsüyle ince ayar yapılabilir.
- Prompter bölüm işaretleri MP4'e bölüm olarak geçer; Türkçe karakterler korunur.

**MP3:** Kayıt sekmesindeki "MP3 kopyası da oluştur" seçiliyse vokal ve karışımın MP3 kopyaları da çıkar (LAME VBR, yaklaşık 190 kbps). Bölüm işaretleri MP3'e de yazılır.

**ffmpeg:**
- MP3, MP4 ve kamera için gerekir. Uygulamaya gömülü değildir; Kamera sekmesindeki "ffmpeg'i indir" ile bir kez indirilir (31 MB).
- Kaynak: PyPI'daki imageio-ffmpeg 0.7.0 paketi içindeki ffmpeg 7.1 (gyan.dev essentials).
- Paket ve içindeki ffmpeg.exe ayrı ayrı SHA-256 ile doğrulanır; özetler uygulamada sabittir, uyuşmazsa dosya kullanılmaz.
- Bilgisayarda zaten ffmpeg kuruluysa o kullanılır.
- ffmpeg GPLv3 lisanslıdır ve ayrı bir program olarak çalıştırılır. Lisans notu indirme klasörüne yazılır.

Kayıt sonrası işler (kameranın kapatılması, karışım, işaretler, MP3, MP4) arka planda sırayla yapılır, dinleme ve arayüz beklemez. Sonuçta oluşan dosyalar ve varsa sorunlar durum satırında listelenir.
