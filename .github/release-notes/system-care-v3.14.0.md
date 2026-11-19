# AGFO System Care 3.14.0 — SuperTools artık System Care içinde

Sol menüdeki **Ağ** bölümüne dört yeni sayfa geldi:

- **Ağ tarayıcı:** yerel ağdaki cihazları bulur (ICMP/TCP, ARP, SSDP/mDNS). SMB klasörünü ya da web arayüzünü açar, paylaşımları sorgular, NAS hesabıyla bağlanır, CSV kaydeder. Bulunan cihazdan tek tıkla SSH profili oluşturulur.
- **Ağ testleri:** MX, SPF, DMARC, DKIM, MTA-STS, SMTP, TLS, HTTP, TCP, ping, traceroute, RDAP.
- **SSH sunucularım:** kayıtlı sunucular. Parola isteğe bağlı olarak Windows DPAPI kasasında 1–24 saat saklanabilir; anahtar/agent desteği de var.
- **SSH oturumları:** birden çok dahili SSH oturumu ve alt alta iki oturum görünümü.

**VPN ile birlikte:** "UGREEN ayarını kopyala" ve "Hetzner komutunu kopyala" artık komutu kayıtlı bir SSH sunucusunda doğrudan çalıştırmayı da öneriyor. Bağlantı kurulunca komut oturuma gönderiliyor.

**Gizlilik:** SSH profilleri, parola kasası ve ayarlar yalnızca bu bilgisayarda, SuperTools ile aynı `%LOCALAPPDATA%\AGFO-MultiSubnet-Scanner` klasöründe kalır. SuperTools'taki kayıtlarınız System Care'de kendiliğinden görünür. Bu dosyalar pakete ya da depoya hiçbir zaman girmez; CI'daki gizlilik denetimi bunu her sürümde kontrol eder.
