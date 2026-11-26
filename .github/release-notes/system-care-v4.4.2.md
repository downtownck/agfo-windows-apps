## AGFO System Care 4.4.2 — AI asistan artık takılmıyor

- **Neden takılıyordu:** AI Manager yanıtı geciktiğinde (sunucu zaman aşımı, HTTP 502/504) uygulama aynı isteği dört kez, her seferinde dört dakikaya kadar bekleyerek yeniden deniyordu; bu sırada sayfa "Yanıt bekleniyor…"da kalıyordu.
- **Şimdi:** bir soru en fazla 150 saniye sürer. Zaman aşımı tekrarlanmaz; ne olduğu ve ne yapılacağı (daha az veri, daha kısa soru) açıkça yazılır. Yalnız "meşgul" yanıtları (429/503) kısa beklemeyle bir-iki kez denenir.
- Beklerken geçen süre saniye saniye görünür; **Durdur** düğmesi isteği hemen bırakır (geç gelen yanıt yok sayılır).
- Veri toplanırken ("Bilgisayarımı değerlendir" gibi) hangi verinin okunduğu üstte yazar.
- Gönderilen veri 30.000 karakterle, yanıt uzunluğu AI Manager'ın 90 saniyelik sınırına sığacak şekilde sınırlandı.
- Her istek işlem günlüğüne yazılır (veri boyutu, süre, HTTP durumu): sorun olursa günlüğü gönderebilirsiniz.
