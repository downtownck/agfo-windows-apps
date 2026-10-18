## AGFO AI Editor 1.4.1 — çökme düzeltmesi

- **Düzeltildi:** 1.4.0'da editörde seçim yokken bazı tuş ve fare işlemlerinde (Delete, Backspace, Shift+ok, kes/kopyala, tıklama-sürükleme) uygulama `text doesn't contain any characters tagged with "sel"` hatasıyla kapanabiliyordu. Biçimli editörün Tk komut yönlendirmesi, Tk'nin kendi denetimlerinin beklediği hatayı Python istisnası olarak bırakıyordu. Artık hata Tk'ye doğru biçimde iletiliyor ve uygulama kapanmıyor.
- Yönlendirmede beklenmeyen bir hata olursa da uygulama çalışmaya devam eder.
- Bu durum için gerçek Tk tuş/fare olaylarıyla regresyon testi eklendi.
