## AGFO AI Manager 17.8.0: AI Editor'de iş başına çeviri modeli

- **Yeni `GET /editor/models` uç noktası.** Sitede anahtarı olan sağlayıcıların çeviriye uygun modellerini (Çeviri panosundaki liste) kalite puanı, 1000 kelime için tahmini maliyet ve hız sınıfıyla (`fast` / `normal` / `slow`) döndürüyor. Düşünen (reasoning) modeller `slow` sayılıyor. Kullanılamayan modeller listelenmiyor; yanıtta anahtar ya da gizli bilgi bulunmuyor.
- **`/editor/transform` isteğe bağlı `model="sağlayıcı|model"` alıyor.** Yalnız çeviri şablonlarında uygulanıyor. Sağlayıcının sitede anahtarı olmalı ve model sağlayıcının model listesinde bulunmalı; aksi halde 400 (`agfo_model_choice`) dönüyor.
- Seçilen model çalışmazsa 17.7.0'daki gibi varsayılan metin modeline düşülüyor. Bu durum sitenin Çeviri rotası hatası olarak kaydedilmiyor, panodaki uyarıyı etkilemiyor.
- Parametre gönderilmezse davranış 17.7.0 ile aynı.
- Testler: content-translate 35/35 (yeni T25–T29), editor-api 48/48 (yeni E42–E46). AI Editor uçtan uca testi gerçek editor API koduyla model seçimini doğruluyor.
