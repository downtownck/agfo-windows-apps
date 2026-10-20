# AGFO Phantom Shot — Tek tuşla sessiz ekran görüntüsü

Belirlediğiniz bir klavye ya da fare tuşuna basınca ekran görüntüsünü alır ve ayarladığınız klasöre kaydeder. **Ekranda hiçbir pencere, bildirim, ses ya da imleç değişimi göstermez.** Pencere yalnızca ayar ve kontrol içindir.

Dağıtım tek dosyalık bir **EXE**'dir (PyInstaller). Çalışması için Python kurulu olması gerekmez; `mss`, `pynput`, `pillow` ve `pystray` EXE'nin içine gömülüdür.

## Kurulum (yönetici gerekmez)
En kolay yol: GitHub Releases'ten **`AGFO-Phantom-Shot-Kur.cmd`** dosyasını indirip çift tıklayın. Bu dosya:
1. En güncel `AGFO-Phantom-Shot.exe`'yi GitHub'dan indirir ve SHA-256 ile doğrular,
2. `%LOCALAPPDATA%\Programs\AGFO-Phantom-Shot` altına kurar,
3. Başlat menüsü (AGFO) ve masaüstü kısayolu oluşturur,
4. Uygulamayı başlatır.

Alternatif: Doğrudan `AGFO-Phantom-Shot.exe`'yi indirip çalıştırın; ilk açılışta bilgisayara kurulmayı teklif eder.

> **SmartScreen:** EXE kod imzalı değildir. `.cmd` ile indirmek genelde SmartScreen uyarısını atlatır (dosyaya tarayıcı "internetten indirildi" damgası eklemez); yine de ilk çalıştırmada Defender bir uyarı gösterirse **Ek bilgi › Yine de çalıştır** deyin. Sonraki güncellemeler uygulama içinden sessizce gelir.

## Kullanım
1. **Kayıt klasörü** — "Gözat…" ile seçin. Boşsa `~/Pictures/PhantomShots` (ya da Resimler).
2. **Tetik tuşu** — `f9`, `f12`, `print_screen`, `pause`, `scroll_lock` veya tek harf. İstemiyorsanız `(yok)`.
3. **Fare tuşu** — `middle`, `x1`, `x2` (yan tuşlar) veya `(yok)`. `left` önerilmez; normal tıklamaları da yakalar.
4. **Ekran** — `0` tüm ekranlar, `1` birincil, `2` ikincil…
5. **Biçim** — PNG veya JPG (+ kalite). Dosyalar `shot_20261020_215130_123.png` gibi zaman damgalı adlarla kaydedilir.
6. **Başlat** — durum satırı yeşile döner ("Dinleniyor"). Artık tuşa her basışta görüntü sessizce kaydedilir; yalnızca durum satırında sayaç güncellenir. **Durdur** ile kapatır.

- **Açılışta dinlemeye başla** ve **kapatınca sistem tepsisine küçült** seçenekleri kaydedilir.
- Ayarlar `%LOCALAPPDATA%\AGFO\PhantomShot\config.json` dosyasındadır; güncelleme bu dosyaya dokunmaz.
- Windows'ta **Print Screen** tuşu sistemin kesme aracıyla çakışabilir; `f9`/`f12` daha temiz çalışır.

## GitHub'dan tek tıkla güncelleme
- Açılışta (en fazla 6 saatte bir) `downtownck/agfo-windows-apps` deposundaki `phantom-shot-v*` sürümleri denetlenir. Yeni sürümde üstte **Şimdi güncelle / Notlar / Bu sürümü atla** bandı çıkar.
- **Şimdi güncelle**: yeni `AGFO-Phantom-Shot.exe` indirilir ve SHA-256 ile (GitHub özeti ve/veya `SHA256SUMS.txt`) doğrulanır. Uygulama kapanır; yeni sürüm kendini eski dosyanın üzerine yazar ve yeniden açılır. Ayarlarınız korunur.
- **Güncelleme…** penceresinden "GitHub'da denetle", "Şimdi güncelle" ve "Bu bilgisayardan kaldır" yapabilirsiniz. Sorgu yalnızca GitHub'a gider; kişisel veri gönderilmez.

## Kaldırma
Güncelleme penceresinde **Bu bilgisayardan kaldır** — ya da depodaki `Kaldir.cmd`. Program dosyası ve kısayollar silinir; ayarlarınız ve günlükler korunur.

## Geliştirme (kaynaktan çalıştırma)
`Baslat.cmd` uygulamayı Python ile kaynaktan çalıştırır (geliştirme için; `pip install pynput mss pillow pystray` gerekir). Dağıtım her zaman EXE'dir. EXE'yi yerelde derlemek için Python 3.12 ile `packaging/build_windows.ps1`.

## Güvenlik
- Uygulama yalnızca `https://api.github.com/repos/downtownck/agfo-windows-apps/releases` adresini sorgular ve yalnızca `github.com` / `*.githubusercontent.com` üzerinden indirir (yönlendirmeler de denetlenir).
- İndirilen EXE, GitHub'ın SHA-256 özetiyle ve/veya `SHA256SUMS.txt` ile doğrulanır; özet yoksa kurulmaz. Güven kökü bu GitHub hesabıdır; kod imzası yoktur.
- Phantom Shot kendi ekranınızı sizin bastığınız tuşla kaydeder; görüntüler yalnızca yerel diske yazılır, hiçbir yere gönderilmez.
