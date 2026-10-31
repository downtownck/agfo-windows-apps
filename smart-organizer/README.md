# AGFO Smart Desktop Organizer v1.1.1

Windows Masaüstü ve Belgeler'deki dosyaları **taşımadan önce** analiz eden, proje/konu bazında klasör öneren, yalnızca kullanıcı onayıyla taşıyan uygulama.

## İlk kullanım — hedef klasör seçimi ZORUNLU

1. ZIP'i yeni bir klasöre çıkarın ve `Baslat.bat` çalıştırın (Python 3.10+).
2. Üstteki **Hedef klasörü seç...** düğmesine basın. Dosyaların gideceği **gerçek ana çalışma klasörünü** Windows klasör seçicisinden belirleyin. Örnek: `D:\AGFO-Dosyalar` veya `OneDrive\AGFO-Aktif`. Uygulama bu yolu kalıcı ayarlara kaydeder. **Belgeler/Masaüstü otomatik hedef olarak kullanılmaz.**
3. **Klasör planı** düğmesiyle 20 ana konu klasörünü ve tam yollarını inceleyin. İsterseniz **20 ana klasörü oluştur** düğmesine basarak bunları seçtiğiniz kökte, hiçbir dosya taşımadan oluşturun.
4. **Hızlı analiz et** düğmesine basın. Önerileri gözden geçirin; gerekirse **Hedefi değiştir** ile dosyanın konu klasörünü düzenleyin. Birden fazla dosyayı birlikte seçebilirsiniz.
5. **Seçilenleri kabul et/reddet** veya **TÜMÜNÜ kabul et/reddet** kullanın. **İncelenecek** durumundaki dosyalar toplu kabulde atlanır; siz klasör atamadan taşınmaz.
6. **ONAYLANANLARI TAŞI** düğmesinde **gerçek tam hedef yolları** tekrar gösterilir. Onaydan sonra yalnızca kabul edilenler taşınır. İşlem bitince hedef klasörlerin tam yolları listelenir; **Hedef ana klasörü aç** ile Windows Explorer'da açabilirsiniz.
7. **Son taşımayı geri al** işlemi SQLite günlüğündeki son taşımaları, çakışma yoksa, özgün konumlarına döndürür.

**Önemli:** `OneDrive\DOC-COP\Belgeler\AGFO Düzenlenenler` gibi eski sürümün kullandığı klasörler **otomatik taşınmaz, silinmez veya temizlenmez**. `DOC-COP`, `Çöp`, `Trash`, `$Recycle.Bin` içeren yollar hedef olarak reddedilir. Kullanıcı yeni hedef seçene kadar hiçbir taşıma yapılamaz. Mevcut ayarlar ve geri alma geçmişi korunur. Eski sürümdeki hedef seçimi yeni sürüme otomatik aktarılmaz.

## Fotoğraftaki ana klasörler

`BRCGS`, `IFS`, `ASI`, `GLOBALGAP`, `IAS`, `AGFO TR`, `AGFO SP`, `CSI`, `ATECQ`, `SPAIN`, `EGYPT`, `SES`, `VIDEO`, `GORSEL`, `WP`, `CYBERPANEL`, `WINAPP`, `FELSEFE`, `ROMAN`, `EDEBIYAT`.

`GLOBALG.A.P.`, `GLOBALGAP` ve `GGAP` aynı `GLOBALGAP` klasörüne; `IAS` ve `ASI` ayrı klasörlere önerilir. Konusu anlaşılamayan fatura, belge, denetim dosyası, arşiv, klasör veya kısayol genel bir `Belgeler`, `Denetimler`, `Arşivler` vb. klasöre **otomatik taşınmaz**; `İncelenecek` olarak kalır. İsterseniz kendi ana klasörünüzü **Klasörleri yönet** ile ekleyebilir veya alt klasör (ör. `BRCGS/2026`) tanımlayabilirsiniz. Uygulama mevcut diskteki klasörleri silmez.

## İsteğe bağlı yerel AI

GPU gerekmez. `KUR-GEMMA.cmd` Ollama'yı ve RAM'e göre `gemma3:1b` veya `gemma3:270m` modelini kurar. Ardından **Modelleri bul** ve **Yerel AI ile iyileştir** düğmelerini kullanabilirsiniz. AI içerik örnekleri yalnızca yerel `127.0.0.1:11434` adresine gönderilir; bulut AI servisi kullanılmaz. AI'nın genel tür etiketleri (`Belgeler`, `Denetimler` vb.) proje klasörü olarak kabul edilmez; konu belirsizse dosya yerinde kalır. CPU'da yanıtlar yavaş olabilir. PDF metni için isteğe bağlı `pypdf` gerekir (`py -3 -m pip install pypdf`).

## GitHub üzerinden güncelleme

**GitHub güncelleme** yalnızca `downtownck/agfo-windows-apps` deposundaki `smart-organizer-vX.Y.Z` etiketli GitHub Releases sürümlerini arar. ZIP ve `.sha256` dosyası varsa HTTPS üzerinden indirir, SHA-256 doğrular ve kullanıcıdan ayrı kurulum onayı alır. Eski program dosyaları yedeklenir. `%LOCALAPPDATA%\AGFO\SmartOrganizer` altındaki ayarlar ve `moves.sqlite3` günlüğü korunur. GitHub Release yayımlanmamışsa otomatik güncelleme bulunamaz. Windows üzerinde canlı kurulum testi ayrıca gereklidir.

## Güvenlik, kapsam ve sınırlamalar

- Kaynaklar Windows Known Folder API üzerinden tespit edilir; OneDrive yönlendirmesi desteklenir, **ama hedef otomatik belirlenmez**.
- Masaüstü/Belgeler'in yalnızca **doğrudan çocukları** taranır. Alt klasörlerin içi ayrı ayrı taranmaz; seçilen üst klasör bütün olarak taşınabilir. Hedef klasör kaynaklardan birinin içindeyse o klasör taramadan dışlanır.
- Çöp, disk kökü, Windows sistem klasörleri ve Masaüstü/Belgeler kökleri hedef seçilemez.
- Sadece **Kabul** durumundaki öğeler taşınır; hedefte çakışma varsa üzerine yazılmaz. Silme yapılmaz. Dosya taramadan sonra değişmişse taşıma engellenir.
- SQLite işlem kaydı `%LOCALAPPDATA%\AGFO\SmartOrganizer\moves.sqlite3` altındadır. Geri alma işlemi özgün yolda çakışma varsa atlar.
- Kısayollar taşındığında masaüstündeki simgeleri kaybolabilir; kısayol hedefleri değişmez. OneDrive taşımaları eşitleme başlatabilir.
- Masaüstü simgelerinin **ekran koordinatlarını** değiştirmez.
- `Baslat.bat` Python 3.10+ gerektirir. `EXE-OLUSTUR.bat` Windows üzerinde PyInstaller ile tek dosyalı EXE oluşturur. Bu kaynak ZIP, önceden derlenmiş EXE içermez.

## Geliştirici testleri

`py -3 -m unittest discover -s tests -v`

Kaynak MIT lisanslıdır. Bu sürüm Linux üzerinde birim testleri ve sanal grafik arayüz testiyle doğrulanmıştır; gerçek Windows/OneDrive ortamında ayrıca kontrol edilmelidir.
