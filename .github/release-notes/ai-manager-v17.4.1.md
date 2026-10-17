## AGFO AI Manager 17.4.1 — AI Editor "Kimlik doğrulanamadı" (401) düzeltmesi

- Bazı LiteSpeed/CGI sunucuları `Authorization` başlığını PHP'ye iletmiyor; bu durumda WordPress Uygulama Parolası hiç denetlenmiyor ve AI Editor 401 alıyordu. Editör (1.0.1+) aynı kimlik bilgisini `X-AGFO-Editor-Auth` başlığıyla da gönderir. Bu başlık yalnızca `/agfo-ai/v1/editor/*` için ve WordPress'in kendi Uygulama Parolası doğrulamasıyla kabul edilir.
- 401 yanıtları artık gerçek nedeni bildirir: parola hatalı, kullanıcı yok, Uygulama Parolaları bir güvenlik eklentisince kapatılmış ya da kimlik bilgisi sunucuya hiç ulaşmamış.
- Güncelleme: WordPress › Eklentiler ekranında "Güncelle" (17.4.0'dan itibaren GitHub'dan gelir).
