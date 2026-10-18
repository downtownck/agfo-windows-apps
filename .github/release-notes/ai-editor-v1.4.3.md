## AGFO AI Editor 1.4.3 — tasarım PDF'lerinde doğru boyut, renk ve harf aralığı

Gönderilen "Essential AI Prompt Collection" PDF'i ile bulunan sorunlar:

- **Yeni metin çok küçük çıkıyordu:** Tasarım programları yazı boyutunu çoğu zaman "1 pt × büyütme matrisi" olarak kaydeder (örnek dosyada 1 × 225 × 0,24 = 54 pt). Görünen boyut artık matristen hesaplanıyor; düzeltilen başlık özgün boyutunda yazılıyor.
- **Renk yanlış seçilebiliyordu:** Büyük yazılarda satırın kutusunun içi çoğunlukla yazının kendisidir. Zemin rengi artık kutunun hemen dışından okunuyor; koyu zemindeki beyaz yazı beyaz, açık mavi başlık açık mavi kalıyor.
- **Harf aralığı korunuyor:** Özgün metindeki geniş harf aralığı (tracking) yeni metne de uygulanıyor. Özgün yazı tipi bilgisayarda kurulu değilse (ör. Montserrat) satır genişliği özgüne yakın kalacak şekilde ölçekleniyor. Çok kalın (Black/Heavy) yazı tiplerinde Windows'ta Arial Black kullanılıyor.
- 1.4.1'de görülen siyah kutu ve sayfanın kararması 1.4.2'de giderilmişti; bu dosyada da sayfanın geri kalanına dokunulmadığı doğrulandı.
- Ölçekli matrisle yazılmış metin için regresyon testi eklendi.
