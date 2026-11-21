## AGFO System Care 4.3.2 — netcup sunucusu da Tailscale çıkış noktası

- **VPN › Tailscale** bölümüne **netcup komutunu kopyala (yabancı IP)** eklendi: Hetzner'deki kurulumun aynısı, netcup (CyberPanel) sunucusu için. Makine adı `netcup-cikis`.
- Komut kayıtlı bir SSH sunucusunda System Care'den doğrudan çalıştırılabilir ya da AGFO Root Terminal'e yapıştırılabilir. Tailscale zaten bağlıysa yalnız çıkış noktalığını açar; ad ve DNS ayarı değişmez (`--accept-dns=false`).
- CyberPanel sunucularında firewalld çalışıyorsa Tailscale belgesindeki bilinen sorun için maskeleme (masquerade) açılır; firewalld yoksa güvenlik duvarına dokunulmaz. Aynı iyileştirme Hetzner komutunda da var.
- Tailscale listesinde `netcup` adlı makineler "Yurt dışı — netcup (yabancı IP)" olarak görünür.
