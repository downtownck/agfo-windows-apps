## AGFO AI Manager 17.5.0 — AI Editor bağlantı anahtarı

- Yeni sayfa: **AI Manager › 🖊️ AI Editor bağlantısı**. "Anahtar oluştur"a basın, çıkan değeri AI Editor › Ayarlar › Bağlantı › *Bağlantı anahtarı* alanına yapıştırın. Uygulama Parolası gerekmez.
- Sunucu yetkilendirme başlığını düşürse ya da bir güvenlik eklentisi Uygulama Parolalarını kapatsa da çalışır.
- Anahtarlar onu oluşturan kullanıcıya bağlıdır, sitede yalnızca özet (HMAC) olarak saklanır, bir kez gösterilir, tek tek silinebilir ve yalnız AI Editor uçlarında geçerlidir.
- `/wp-json/agfo-ai/v1/editor/ping`: editörün bağlantı tanısı için sürüm ve evet/hayır bilgileri (gizli bilgi içermez).
- Uygulama Parolası ile bağlanma aynen çalışmaya devam eder.
