## AGFO Mic Monitor 1.5.1: Dudak senkronu düzeltildi, prompter videosunda metin

### Dudak senkronu
Önceki sürüm görüntünün başlangıcını, ffmpeg'den ilk önizleme karesinin uygulamaya ulaştığı anla ölçüyordu. Bu ölçüme ffmpeg'in açılış süresi, filtreler ve boru gecikmesi de karışıyordu; kamera da ses kaydından sonra açıldığı için hata büyüyebiliyordu.

Artık:
- Her kamera karesi yakalandığı anın saatiyle damgalanıyor ve dosyaya bu damgayla yazılıyor.
- Sesin ilk örneğinin yakalandığı an da aynı saatle ölçülüyor. Ses kartının giriş gecikmesi ve altyapı hizalaması bu hesaba dahil.
- İki taraf aynı saate bağlı olduğu için aradaki fark doğrudan hesaplanıyor. Kareler gerçek zamanlarını taşıdığı için uzun kayıtlarda kayma birikmiyor.
- Kameranın kendi gecikmesi için görüntü 50 ms öne alınıyor. Kameranız farklıysa "Görüntü-ses" sürgüsüyle bir kez ayarlayın.

Testlerde sahte kamera bilinen bir anda flaş yapıyor ve flaşın videoda doğru zamanda göründüğü ±1 kare (33 ms) doğrulukla ölçülüyor. Uygulama üzerinden uçtan uca senkron testi de eklendi.

### Prompter videosunda metin
AGFO Prompter eklentisindeki gibi, prompter kaydının videosu artık okunan metni gösteriyor:
- O an okunan bölüm koyu zeminde beyaz kalın yazıyla ekranda. Bölümler okuduğunuz anda değişiyor.
- Kamera, seçtiğiniz köşede ve boyutta. Metin kameranın altında kalmayacak şekilde yerleşiyor, uzun bölümlerde yazı küçülüyor.
- Kamera kapalıysa video yalnızca metin ve sesten oluşuyor.
- 1280x720; kamerada 1920x1080 seçiliyse 1920x1080. Bölüm işaretleri videoda bölüm olarak duruyor.
- Kamera sekmesindeki "Prompter kaydında videoya metni koy" seçeneğiyle açılıp kapatılabiliyor. Kapalıysa önceki gibi yalnızca kamera görüntüsü kullanılıyor.
