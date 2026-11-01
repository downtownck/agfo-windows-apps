## AGFO Mic Monitor 1.0.2: Çıtırtı giderildi

Dinlerken duyulan çıtırtının asıl nedeni, ses iş parçacığının zamanında çalışamamasıydı. Python, iş parçacıkları arasında en geç 5 ms'de bir geçiş yapıyor. Ses tamponu 3–5 ms olunca, arayüz meşgulken ses verisi zamanında hazırlanamıyor ve kulaklığa boşluk gidiyordu. Ölçümde varsayılan ayarla 3 ms'lik sürelerin yarısı kaçırılıyordu; yeni ayarla hiçbiri kaçırılmıyor.

Değişiklikler:
- **İş parçacığı geçişi:** Dinleme sürerken ses iş parçacığı en geç 0,5 ms içinde çalışabiliyor. Bu, çıtırtının asıl düzeltmesi.
- **Daha hafif arayüz:** Seviye göstergesi her karede baştan çizilmiyor. Aygıt değişikliği kontrolü ayrı bir iş parçacığında yapılıyor.
- **Otomatik tampon büyütme:** 10 saniyede 6 ya da daha fazla kesinti algılanırsa tampon bir kademe büyütülüyor (5 → 10 → 20 ms) ve durum satırında bildiriliyor. Kayıt sürerken kayıt bozulmasın diye yalnızca uyarı gösteriliyor.
- **Doğru kesinti sayacı:** Akış başlarken gelen olağan bildirimler artık kesinti sayılmıyor; sayaç yalnızca gerçek taşma ve boşalmaları gösteriyor.
- **Ayrı akış kipi:** Giriş ve çıkış ayrı akış olarak açıldığında aradaki tampon, sürücünün blok boyutlarına göre kendini ayarlıyor. Boşalırsa sürekli kısa boşluklar yerine bir kez yeniden doluyor.

Güncelleme: uygulamada "Güncelleme…" > "Şimdi güncelle". Ayarlarınız korunur.
