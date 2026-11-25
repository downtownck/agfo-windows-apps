# AGFO Mihenk 2.1.0

Açık duran uygulama da yeni sürümü görüyor.

2.0.0 ve öncesinde güncelleme denetimi yalnızca **açılıştan 2,5 saniye sonra bir kez**
çalışıyordu. Gün boyu açık kalan bir Mihenk, aradan çıkan sürümü hiç fark etmiyordu;
görmek için kapatıp açmak gerekiyordu. Bu sürümde denetim çalışırken de saatte bir
yineleniyor.

Ağ trafiği artmıyor: gerçek istek `mihenk_update.CHECK_INTERVAL` (altı saat) ile
sınırlı; saatlik yoklama yalnızca o sınırın dolup dolmadığına bakıyor. Bir güncelleme
zaten bulunmuşsa tekrar sorulmuyor.

2.0.0'daki her şey yerinde: modern görünüm, kontrol listeleri, yedek parça stoğu,
raporlar ve denetime hazır çıktı.
