## AGFO AI Editor 1.4.11: İçindekiler satırları gerçek modelle de düzgün

Zor test belgesinin gerçek model çevirisi (Together AI · DeepSeek-R1-Distill-Qwen-14B) incelendi.

- **İçindekiler:** Model bazı satırların nokta dizisini atınca satır nokta dizisiz, sayfanın ortasına kaymış çıkıyordu ("Risk temelli sıklık", "Denetimin gerçekleştirilmesi"). Artık nokta dizisi yeniden kuruluyor ve satır her zaman özgün girintide sola yaslı kalıyor. Çeviri talimatına da nokta dizilerini ve sayfa numaralarını koruma kuralı eklendi.
- Geri kalan düzen (tablolar, akış şeması, kutular, dipnot, bağlantı, damga, imza bloğu, döndürülmüş kenar yazısı, iki yana yaslı sütunlar) gerçek model çıktısında da doğru yerleşti. Kalan farklar modelin kelime seçimlerinden kaynaklanıyor (örneğin "APPROVED" → "ONAYLAYAN", çevrilmemiş "NORTHWIND SAFETY INSTITUTE").
