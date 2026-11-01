## AGFO Mic Monitor 1.0.3: Güncellemeler gecikmeden görünüyor

Düzeltilen sorun: GitHub'daki yeni sürüm uygulamada görünmüyordu.

Nedeni: Uygulama güncellemeyi yalnızca açılışta denetliyor, sonucu 6 saat saklıyordu. Bir sürümü açtıktan sonra yayınlanan yeni sürüm 6 saat boyunca görünmüyordu. Uygulama açık kaldığı sürece de hiç yeniden denetleme yapılmıyordu.

Değişiklikler:
- Açılışta her seferinde GitHub'a gerçekten soruluyor. Yeni sürüm varsa üstte yeşil "Yeni sürüm hazır" şeridi çıkıyor; güncelseniz pencere açılmıyor.
- Uygulama açıkken 30 dakikada bir denetleniyor.
- "Güncelleme…" > "GitHub'da denetle" her zaman anında denetliyor.

Not: 1.0.2 ve önceki sürümlerden bu sürüme geçerken bir kez "Güncelleme…" > "GitHub'da denetle" düğmesine basın. Eski sürümler 6 saatlik önbelleği kullandığı için güncellemeyi kendiliğinden göremeyebilir.
