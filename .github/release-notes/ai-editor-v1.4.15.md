## AGFO AI Editor 1.4.15 — güncelleme kendiliğinden görünür

- Editör açıkken **30 dakikada bir** arka planda yeni sürüm olup olmadığını denetler (açılıştan 5 sn sonra ilk denetim). Denetim sessizdir; iş göstergesi ya da iptal düğmesi açmaz, çalışmanızı bölmez.
- Yeni sürüm varsa sağ üstte **"⬆ Güncelleme var: vX.Y.Z"** düğmesi kendiliğinden belirir, pencere başlığına not düşülür ve alt satırda bir kez bilgi verilir. Düğmeye basınca tek tıkla güncellenir.
- Düğme yalnız güncelleme paketi **gerçekten hazırsa** görünür: sürümde EXE ve SHA-256 özeti (GitHub özeti ya da SHA256SUMS.txt) bulunmalı. Paket henüz yüklenmediyse düğme çıkmaz, sonraki denetimde tekrar bakılır.
- En güncel sürüme geçilince düğme ve başlık notu kendiliğinden kalkar. Ağ hatasında gösterilen düğme kaybolmaz.
- Ayarlar → "GitHub'dan yeni sürümü kendiliğinden denetle" kapatılırsa arka plan denetimi yapılmaz; "Şimdi denetle" her zaman çalışır.
- Sürümle birlikte **AGFO-AI-Editor-Kur.cmd** yayınlanır: yönetici izni istemeden GitHub'daki en son sürümü indirir, SHA-256 ile doğrular, kurar, kısayolları oluşturur ve editörü açar. Teams'ten ya da bağlantıyla paylaşılabilir; içinde sabit sürüm yoktur.
