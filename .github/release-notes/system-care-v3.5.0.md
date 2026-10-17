## AGFO System Care 3.5.0 — Aygıt temizliği

GitHub'dan dağıtılan ilk güncelleme.

- **Aygıt temizliği** sekmesi: şu an bağlı olmayan (gizli) aygıtları — eski USB bellekler, telefonlar, yazıcılar, COM portları, kaldırılmış donanım — sınıflara göre listeler; son görülme tarihi ve kaç gündür görülmediğini gösterir.
- 30 günden eski olanlar varsayılan seçilir; sistem/yazılım aygıtları turuncu "Dikkat" olarak işaretlenir ve seçilmez. Süzgeç ve arama vardır.
- Seçilenler Windows'un kendi aracıyla (`pnputil /remove-device`) kaldırılır; kaldırmadan önce aygıtın bağlı olmadığı yeniden denetlenir. Yeniden takılan aygıt yeni aygıt olarak tanınır.
- İsteğe bağlı geri yükleme noktası, Windows'un 24 saat sınırına takılmadan oluşturulur.
- Kaldırma için uygulamanın yönetici olarak açılması gerekir.
