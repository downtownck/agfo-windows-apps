## AGFO System Care 3.7.0 — İnce ayarlar ve Uygulama kur

WinCleaner (emirttac, MIT) katalogundan uygun bölümler System Care'e alındı. Yalnızca kayıt defteri, zamanlanmış görev, hizmet ve güç planı ayarları alındı; serbest komut çalıştıran ayarlar (bcdedit, netsh, betikler) dışarıda bırakıldı.

- Yeni **İnce ayarlar** sekmesi: 70 ayar + 28 hizmet; gizlilik/telemetri, oyun ve performans, görünüm ve Gezgin, Windows 11 arayüzü, ağ, Windows Update. Her satırda şu anki durum, risk düzeyi ve gereksinim (yönetici, yeniden başlatma, Gezgin).
- **Ön ayarlar**: Gamer Modu, Dengeli, Minimal / Sunucu, Laptop / Pil, Maksimum Gizlilik.
- **Birebir geri alma**: her değişiklikten önce mevcut değer kaydedilir; "Son değişikliği geri al" ve "Geçmiş…" ayarları önceki gerçek değerlerine döndürür. "Varsayılana döndür" Windows varsayılanını yazar.
- Tehlikeli ayarlar ayrı izinle, hile korumasını etkileyebilecek ayarlar ek onayla uygulanır; RPC, DCOM ve Windows Defender hizmetleri değiştirilemez.
- Profil dışa / içe aktarma (WinCleaner profilleri de okunur).
- **DNS**: DHCP, Cloudflare, Google, Quad9, AdGuard veya özel adresler; geri alınabilir. DNS önbelleğini temizleme.
- Yeni **Uygulama kur** sekmesi: 159 uygulama WinGet'ten sessiz kurulur / kaldırılır; kurulu olanlar işaretlenir.
- Düzeltme: kurulum betiği sürümü `care_core.py`'den okuyor.
