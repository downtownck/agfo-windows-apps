# AGFO Phantom Shot — Tek tuşla sessiz ekran görüntüsü

Belirlediğiniz bir klavye ya da fare tuşuna basınca ekran görüntüsünü alır ve ayarladığınız klasöre kaydeder. **Ekranda hiçbir pencere, bildirim, ses ya da imleç değişimi göstermez.** Pencere yalnızca ayar ve kontrol içindir.

Uygulama tek dosyalık bir **EXE** olarak çalışır. EXE, diğer AGFO uygulamalarında olduğu gibi **sizin bilgisayarınızda derlenir**. Yerelde üretilen dosya "internetten indirildi" damgası taşımaz; bu yüzden SmartScreen uyarısı çıkmaz.

## Kurulum (yönetici gerekmez)
1. GitHub Releases'ten **`AGFO-Phantom-Shot-vX.Y.Z-Kurulum.zip`** dosyasını indirip bir klasöre açın.
2. Klasördeki **`Derle-ve-Kur.cmd`** dosyasına çift tıklayın. Betik:
   - bilgisayardaki Python 3.10+ sürümünü (tkinter ile) bulur,
   - `%LOCALAPPDATA%\AGFO\PhantomShot\build` altında ayrı bir derleme ortamı kurar (Python kurulumunuza dokunmaz),
   - PyInstaller, mss, pynput, Pillow ve pystray kitaplıklarını bu ortama yükler,
   - `AGFO-Phantom-Shot.exe` dosyasını derler ve `%LOCALAPPDATA%\Programs\AGFO-Phantom-Shot` altına kurar,
   - Başlat menüsü (AGFO) ile masaüstüne kısayol ekler ve uygulamayı açar.

İlk derleme kitaplıkları indirdiği için birkaç dakika sürebilir. Bir hata olursa ayrıntılar `%LOCALAPPDATA%\AGFO\PhantomShot\build\last-build.txt` dosyasına yazılır. Yalnızca derlemek, kurmamak için `Sadece-Derle.cmd` kullanılır; EXE `dist\` klasörüne çıkar.

Python yoksa önce https://www.python.org/downloads/windows/ adresinden kurun. Derlenen EXE çalışmak için Python'a ihtiyaç duymaz.

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
`Baslat.cmd` uygulamayı derlemeden, Python ile doğrudan kaynaktan çalıştırır. Geliştirme içindir ve `pip install pynput mss pillow pystray` gerektirir. `packaging/build_windows.ps1` dosyasını yalnızca GitHub Actions kullanır; uygulama içi güncelleme EXE'sini o üretir.

## Güvenlik
- Uygulama yalnızca `https://api.github.com/repos/downtownck/agfo-windows-apps/releases` adresini sorgular ve yalnızca `github.com` / `*.githubusercontent.com` üzerinden indirir (yönlendirmeler de denetlenir).
- İndirilen EXE, GitHub'ın SHA-256 özetiyle ve/veya `SHA256SUMS.txt` ile doğrulanır; özet yoksa kurulmaz. Güven kökü bu GitHub hesabıdır; kod imzası yoktur.
- Phantom Shot kendi ekranınızı sizin bastığınız tuşla kaydeder; görüntüler yalnızca yerel diske yazılır, hiçbir yere gönderilmez.
