## AGFO System Care 4.3.3 — netcup çıkış noktası onarımı ve sunucu tanısı

- **Sorun:** netcup-cikis bağlı görünüyor ama internete çıkılamıyordu (Görünen IP denetimi bitmiyordu). CyberPanel sunucularında güvenlik duvarı Tailscale trafiğini iletmiyordu; ayrıca güvenlik duvarı yeniden yüklenince Tailscale'in kendi kuralları silinebiliyordu.
- **kur/onar komutu (Hetzner / netcup):** tekrar çalıştırılabilir. firewalld varsa maskelemeyi açar ve `tailscale0`'ı güvenilir bölgeye alır; CSF varsa `csfpost.sh`'a iletim kuralları ekler; ufw varsa `tailscale0` iletimine izin verir; güvenlik duvarı değiştiyse Tailscale'i yeniden başlatır; sonunda TAMAM / SORUN satırlarıyla tanı ve sunucunun dış IP'sini gösterir. Web siteleri ve DNS ayarı etkilenmez.
- **Sunucuyu tanıla:** yalnız okuyan tanı komutu; çıkış noktasının neden çalışmadığını gösterir.
- Tailscale çıkışı açıkken internete çıkılamazsa VPN sayfası artık bunu açıkça söyler ve tanıyı önerir.
- Sunucu düğmeleri ayrı satırda: dar pencerede kesilmiyor.
- Komutlar tek satır (sıkıştırılmış betik) olarak gönderilir; okunur hali System Care günlüğüne yazılır.
