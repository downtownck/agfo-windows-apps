# AGFO Phantom Shot — Tek tuşla sessiz ekran görüntüsü

Belirlediğiniz bir klavye ya da fare tuşuna basınca ekran görüntüsünü alır ve ayarladığınız klasöre kaydeder. **Ekranda hiçbir pencere, bildirim, ses ya da imleç değişimi göstermez.** Pencere yalnızca ayar ve kontrol içindir.

## Kurulum
ZIP'i açın, `phantom-shot/Kur-ve-Baslat.cmd` çalıştırın. Python 3.8+ ve tkinter gerekir (python.org kurulumunda varsayılan gelir). Kurulum betiği `mss` ve `pynput` paketlerini (gerekli), `pillow` ve `pystray` paketlerini (isteğe bağlı: JPG ve sistem tepsisi) `pip install --user` ile kurar. Uygulama `%LOCALAPPDATA%\Programs\AGFO Phantom Shot` altına kurulur ve Başlat menüsüne kısayol eklenir.

Elle kurulum: `pip install pynput mss` (ve isteğe bağlı `pip install pillow pystray`), ardından `Baslat.cmd`.

## Kullanım
1. **Kayıt klasörü** — "Gözat…" ile seçin. Boş bırakılırsa `~/Pictures/PhantomShots` (ya da Resimler) kullanılır.
2. **Tetik tuşu** — `f9`, `f12`, `print_screen`, `pause`, `scroll_lock` veya tek harf. İstemiyorsanız `(yok)`.
3. **Fare tuşu** — `middle`, `x1`, `x2` (yan tuşlar) veya `(yok)`. `left` önerilmez; normal tıklamaları da yakalar.
4. **Ekran** — `0` tüm ekranlar birleşik, `1` birincil, `2` ikincil…
5. **Biçim** — PNG veya JPG (+ kalite). Dosyalar `shot_20261020_215130_123.png` gibi zaman damgalı adlarla kaydedilir; üst üste yazılmaz.
6. **Başlat** — durum satırı yeşile döner ("Dinleniyor"). Artık tuşa her basışta görüntü sessizce kaydedilir; yalnızca durum satırında sayaç güncellenir. **Durdur** ile dinlemeyi kapatır.

- **Açılışta dinlemeye başla** ve **kapatınca sistem tepsisine küçült** seçenekleri kaydedilir. Tepsi için `pystray` + `pillow` gerekir; yoksa program kapatınca normal şekilde kapanır.
- Ayarlar `%LOCALAPPDATA%\AGFO\PhantomShot\config.json` dosyasında tutulur; güncelleme bu dosyaya dokunmaz.
- Windows'ta **Print Screen** tuşu sistemin kesme aracıyla çakışabilir; `f9`/`f12` daha temiz çalışır.

## GitHub'dan tek tıkla güncelleme
- Açılışta (en fazla 6 saatte bir) `downtownck/agfo-windows-apps` deposundaki `phantom-shot-v*` sürümleri denetlenir. Yeni sürüm varsa üstte **Şimdi güncelle / Notlar / Bu sürümü atla** bandı çıkar.
- **Şimdi güncelle**: sürüm ZIP'i indirilir, GitHub SHA-256 özetiyle (ve `SHA256SUMS.txt`) doğrulanır, ardından yerel güncelleme hattından geçer (paket/MANIFEST denetimi, Python ve PowerShell ön kontrolü, yedek, otomatik geri alma) ve uygulama yeniden başlar.
- **Güncelleme…** penceresinden ayrıca elle bir güncelleme paketi (.zip) seçebilir, yedek listesinden önceki bir sürüme dönebilirsiniz. Sorgu yalnızca GitHub'a gider; kişisel veri gönderilmez.

## Uygulama içi güncelleme (elle paket)
1. **Denetim** (paket diske açılmadan): ZIP yapısı ve dosya yolları, 30 MB sınırı, zorunlu dosyalar (`app.pyw`, `phantom_core.py`, `agfo_github_update.py`), sürüm bilgisi, sürüm düşürme/aynı sürüm uyarısı, varsa `MANIFEST.json` ile her dosyanın SHA-256 doğrulaması.
2. **Ön kontrol**: yeni dosyalar geçici klasöre açılır; Python dosyaları derlenir, PowerShell betiği sözdizimi denetiminden geçer.
3. **Uygulama**: mevcut sürüm yedeklenir (`%LOCALAPPDATA%\AGFO\PhantomShot\update-backups`, en son 3 yedek), dosyalar tek tek atomik olarak değiştirilir. Bir adım başarısız olursa önceki sürüm **otomatik geri yüklenir**. Ardından uygulama yeniden başlar.
4. **Geri dönüş**: yedek listesinden bir sürüm seçip "Seçili yedeğe dön" — dönmeden önce mevcut sürüm de yedeklenir.

Güncelleme yalnızca çalışma dosyalarını (`.py`/`.pyw`/`.ps1`/`.md` ve `assets/`) değiştirir; `config.json`, günlükler ve `tests/`, `packaging/`, `.cmd` dosyaları etkilenmez.

## Güvenlik
- Uygulama yalnızca `https://api.github.com/repos/downtownck/agfo-windows-apps/releases` adresini sorgular ve yalnızca `github.com` / `*.githubusercontent.com` üzerinden indirir (yönlendirmeler de denetlenir).
- İndirilen dosya GitHub'ın SHA-256 özetiyle ve/veya `SHA256SUMS.txt` ile doğrulanır; özet yoksa dosya kullanılmaz. MANIFEST bütünlük denetimidir, paketi kimin hazırladığını kanıtlamaz; kod imzası yoktur ve Windows SmartScreen uyarı gösterebilir.
- Phantom Shot kendi ekranınızı sizin bastığınız tuşla kaydeder; görüntüler yalnızca yerel diske yazılır, hiçbir yere gönderilmez.
