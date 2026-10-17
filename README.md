# AGFO Windows Uygulamaları

| Uygulama | Klasör | Sürüm etiketi | Yayınlanan dosya |
|---|---|---|---|
| AGFO System Care | `system-care/` | `system-care-vX.Y.Z` | `AGFO-System-Care-vX.Y.Z.zip` (kurulum + uygulama içi güncelleme paketi) |
| AGFO SuperTools | `supertools/` | `supertools-vX.Y.Z` | `AGFO-SuperTools-vX.Y.Z.update.zip` (Güncelleme Merkezi) + `-Kurulum.zip` |
| AGFO BackupSync | `backupsync/` | `backupsync-vX.Y.Z` | `AGFO-BackupSync-Setup.exe` (Windows'ta GitHub Actions derler) |

## Güncelleme nasıl yayılır
1. Kod değişir, uygulamadaki sürüm numarası yükseltilir (System Care: `care_core.py` `VERSION`; SuperTools: `scanner_core.py` `APP_VERSION`; BackupSync: tüm dosyalardaki sürüm, test ile denetlenir).
2. İsteğe bağlı sürüm notu: `.github/release-notes/<etiket>.md`.
3. Etiket gönderilir (ör. `git tag supertools-v1.7.1 && git push origin supertools-v1.7.1`).
4. **Release** iş akışı: etiket ↔ kod sürümü ve ortak modül kopyaları denetlenir, testler çalışır, paket üretilir, `SHA256SUMS.txt` eklenir, GitHub Release yayınlanır.
5. Kurulu uygulamalar açılışta (System Care / SuperTools 6 saatte, BackupSync 12 saatte bir) yeni sürümü görür; kullanıcı **tek tıkla** günceller.

## Güvenlik
- Uygulamalar yalnızca `https://api.github.com/repos/downtownck/agfo-windows-apps/releases` adresini sorgular ve yalnızca `github.com` / `*.githubusercontent.com` üzerinden indirir (yönlendirmeler de denetlenir).
- İndirilen dosya GitHub'ın sürüm dosyası SHA-256 özetiyle ve/veya `SHA256SUMS.txt` ile doğrulanır; özet yoksa dosya kullanılmaz. Ardından her uygulamanın kendi paket doğrulaması (MANIFEST / update-manifest / setup manifest) ve yedek + otomatik geri alma mekanizması çalışır.
- Güven kökü bu GitHub hesabıdır: hesapta iki adımlı doğrulama açık olmalı, depoya yazma yetkisi sınırlı tutulmalıdır. Kod imzası yoktur; Windows SmartScreen uyarı gösterebilir.
- Ortak denetleyici: `shared/agfo_github_update.py` (her uygulamada birebir kopyası bulunur; CI kopyaların aynı olduğunu denetler).
