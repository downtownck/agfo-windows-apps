## AGFO AI Editor 1.1.1 — güncelleme düzeltmesi

- Güncelleme artık gizli bir PowerShell betiğiyle yapılmıyor: indirilen yeni sürüm küçük bir "kuruluyor" penceresi açar, eski sürüm kapanınca kendini yerine koyar ve uygulamayı yeniden açar.
- Yeni sürüm Windows ya da bir güvenlik yazılımı tarafından engellenirse uygulama **kapanmaz**; ne olduğunu ve dosyanın yerini söyler.
- İndirilenlerden yeni bir sürüm açıldığında, kurulu sürümü onunla değiştirmeyi önerir.
- Başlangıçta bir hata olursa pencere sessizce kapanmaz; hata ekranda gösterilir ve `%LOCALAPPDATA%\AGFO-AI-Editor\error-log.txt` dosyasına yazılır. Güncelleme adımları `update-log.txt` dosyasına yazılır.
- Bu sürümün güncelleyicisi GitHub'ın Windows makinesinde gerçekten çalıştırılarak test edildi (eski sürüm açıkken dosya değiştirme ve yeniden başlatma).
- **1.0.x / 1.1.0'dan geçiş:** bu sürümdeki `AGFO-AI-Editor.exe` dosyasını indirip bir kez açın; kurulu sürümü değiştirmeyi önerir. Engellenirse önce `Trust-AgfoAiEditor.cmd` betiğini çalıştırın.
