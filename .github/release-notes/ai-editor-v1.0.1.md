## AGFO AI Editor 1.0.1 — AI Manager bağlantı düzeltmesi

- Yetkilendirme başlığını PHP'ye iletmeyen sunucularda (LiteSpeed/CGI) bağlantı için yedek başlık gönderilir (AI Manager 17.4.1+ ile çalışır).
- "Kimlik doğrulanamadı" hatası artık nedenini söyler: parola bu kullanıcıya ait değil, kullanıcı adı yok, Uygulama Parolaları kapalı ya da kimlik bilgisi sunucuya ulaşmadı.
- Site adresi başka bir adrese yönlendiriyorsa (ör. www'li adres) kimlik bilgisi oraya taşınmaz; doğru adres Ayarlar'da söylenir.
