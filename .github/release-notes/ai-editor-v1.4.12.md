## AGFO AI Editor 1.4.12: Çevrilmiş PDF'ler artık şişmiyor

- **Dosya boyutu:** 50 KB'lik test belgesi çeviriden sonra 1,8 MB oluyordu. Nedeni, çeviride kullanılan her yazı tipinin (Arial, Arial Bold, Times Italic…) dosyasının tamamının (~550 KB) PDF'e gömülmesiydi. Artık yalnızca belgede geçen karakterler gömülüyor (yazı tipi alt kümesi). Alt küme belge geneli tek olduğundan her sayfaya ayrı kopya girmiyor.
- **Sıkıştırma:** Yeniden yazılan sayfa içerikleri sıkıştırılmadan kaydediliyordu; artık sıkıştırılıyor.
- Ölçümler: zor test belgesi 50 KB → 87 KB (önce 1,8 MB); CP410 (20 sayfa) 262 KB → 285 KB (önce 1,8 MB). Metin seçilebilir ve aranabilir kalıyor; Türkçe karakterler aynı.
- Aynı iyileştirme "Metni düzenle" ile yapılan yerinde düzenlemelerde de geçerli.
- Paket içindeki öz-sınama, yazı tipi alt kümesinin çalıştığını da denetliyor.
