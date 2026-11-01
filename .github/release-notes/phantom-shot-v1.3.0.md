## AGFO Phantom Shot 1.3.0: Hızlı ve tutarlı yakalama

Phantom Shot'ın bir süre sonra tuşa tepki vermemesi, bazen birden çok görüntü alması ve basışta sistemin takılması düzeltildi.

- **Bir süre sonra çalışmayı bırakması:** Görüntü alma ve PNG sıkıştırma, klavye kancasının içinde yapılıyordu. Bu, özellikle çoklu ekranda yarım saniyeyi aşabiliyordu. Windows yavaş kalan kancayı sessizce kaldırıyor, uygulama "Dinleniyor" yazarken tuşa basmak hiçbir şey yapmıyordu. Artık kanca yalnızca isteği sıraya koyuyor (mikrosaniyeler); yakalama ve kaydetme ayrı iş parçacıklarında yapılıyor.
- **Hız:** Ekran yakalayıcı her basışta yeniden kurulmuyor; kare tuşa basılır basılmaz alınıyor, kaydetme beklemeden arka planda yapılıyor. PNG daha hızlı sıkıştırılıyor. Art arda basışlar birbirini beklemiyor.
- **Basılı tutunca çok görüntü:** Tuşu basılı tutmak ya da çok hızlı çift basmak artık tek görüntü alıyor (en az 250 ms aralık).
- **Tuş başka bir şey açıyordu:** Tetik tuşu varsayılan olarak diğer programlara iletilmiyor; F9 ya da Print Screen başka bir uygulamayı tetiklemiyor ("Tetik tuşunu diğer programlara iletme" seçeneği).
- **Klavye düzeni:** Tetik, karakter yerine tuş koduyla eşleşiyor; harf tetikleri Türkçe klavyede, Shift veya CapsLock açıkken de çalışıyor.
- **Kendini onarma:** Dinleyici uyku/kilit sonrası düşerse 3 saniye içinde yeniden kuruluyor; ayrıca 10 dakikada bir sessizce yenileniyor. Ekran düzeni değişirse yakalayıcı yeniden kuruluyor.
- **Unutulan "Başlat":** "Açılışta dinlemeye başla" artık varsayılan olarak açık. Yeni "Windows açılışında tepside ve dinlemede başlat" seçeneğiyle uygulama oturum açılınca pencere göstermeden çalışmaya başlıyor. Tepsi simgesinin ipucu dinleme durumunu ve alınan görüntü sayısını gösteriyor.
- Yakalama hataları `%LOCALAPPDATA%\AGFO\PhantomShot\logs\phantom.log` dosyasına yazılıyor.
- Ayarlar ve tüm önceki işlevler (fare tuşu, ekran seçimi, PNG/JPG, tepsi, tek tıkla güncelleme, kaldırma) aynen korunuyor.
