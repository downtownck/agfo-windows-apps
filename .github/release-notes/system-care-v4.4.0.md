## AGFO System Care 4.4.0 — İnternet hızı ve DNS yönetimi

**Ağ › İnternet hızı** — "internet hızlandırma / ping düşürme" adımlarını otomatik tarar, önerileri seçip uygularsınız:
- **DNS:** mevcut DNS ile Cloudflare, Google ve Quad9 gerçek çözümleme süresiyle ölçülür; belirgin fark varsa en hızlısı önerilir. Tailscale DNS'ine dokunulmaz, yerel filtre DNS'i (Pi-hole / şirket) varsa uyarılır.
- **Bağlantı hızı ve çift yön:** ağ kartı elle 10/100 Mbps ya da yarım çift yöne kilitlenmişse otomatiğe alınır; kart 1 Gbps destekleyip bağlantı düşük kurulduysa kablo uyarısı.
- **Windows Update paylaşımı (Teslim İyileştirme):** internet üzerinden yükleme açıksa kapatılır.
- **Wi-Fi sinyali**, **modem ve internet gecikmesi / kayıp / dalgalanma**, **başlangıç uygulamaları**, **interneti kullanan uygulamalar**.
- Windows Update hizmetini kapatmak önerilmez (güvenlik yamaları gelmez); duraklatma ayarı açılır.
- DNS ve paylaşım değişiklikleri İnce ayarlar › Geçmiş'ten geri alınır.

**Ağ › DNS yönetimi** — bağdaştırıcıların DNS'i, hız testi (en hızlısı otomatik seçilir), seçili bağdaştırıcılara uygulama, otomatiğe (DHCP) döndürme, önbellek temizleme ve geri alma tek sayfada.
