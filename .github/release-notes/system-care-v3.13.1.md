# AGFO System Care 3.13.1

Tailscale çıkış noktası kurulumu için düzeltmeler:

- **Hetzner komutu**: Tailscale sunucuda zaten kuruluysa komut artık `tailscale up` hatasına düşmüyor. Bağlantıya, makine adına ve DNS ayarına dokunmadan yalnızca `tailscale set --advertise-exit-node` çalıştırıyor. İlk kurulumda `--accept-dns=false` kullanıyor, böylece sunucunun kendi DNS'i korunuyor.
- **Teşhis**: Henüz onaylı çıkış noktası yoksa VPN sayfası, tailnet'te bulunup çıkış noktası olmayan sunucuları ve yapılması gereken adımı gösteriyor.
- Adında "ugreen" ya da "hetzner" geçmeyen Linux makineleri "kendi sunucunuz / NAS" olarak etiketleniyor.
