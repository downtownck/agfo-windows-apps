## AGFO Phantom Shot 1.0.0 — ilk sürüm

Belirlediğiniz bir klavye ya da fare tuşuna basınca ekran görüntüsünü sessizce alıp kaydeden Windows aracı. **Ekranda hiçbir pencere, bildirim, ses ya da imleç değişimi göstermez** — pencere yalnızca ayar ve kontrol içindir.

- `AGFO-Phantom-Shot-v1.0.0.zip` içindeki `phantom-shot/Kur-ve-Baslat.cmd` ile kurulur; `mss` + `pynput` (gerekli), `pillow` + `pystray` (isteğe bağlı) `pip install --user` ile kurulur. Başlat menüsüne kısayol eklenir.
- Tetik: `f9`/`f12`/`print_screen`/`pause` gibi bir tuş veya fare yan tuşu (`middle`/`x1`/`x2`). Kayıt klasörü, biçim (PNG/JPG + kalite), ekran (tek/tüm) ve dosya öneki ayarlanır. Dosyalar zaman damgalı adlarla kaydedilir.
- "Açılışta dinlemeye başla" ve "kapatınca sistem tepsisine küçült" seçenekleri. Ayarlar `%LOCALAPPDATA%\AGFO\PhantomShot\config.json`.
- GitHub'dan tek tıkla güncelleme: `downtownck/agfo-windows-apps` deposundaki `phantom-shot-v*` sürümleri açılışta denetlenir; ZIP indirilip SHA-256 ile doğrulanır, mevcut sürüm yedeklenir, bir hata olursa otomatik geri alınır ve uygulama yeniden başlar.
- Kod imzalı değildir; SmartScreen "Ek bilgi › Yine de çalıştır" isteyebilir.
