## AGFO AI Editor 2.8.1 — IFS madde numaraları

- **Madde numaraları standarttaki gibi:** IFS Food 8'in 232 maddesi kendi numarasıyla görünüyor (1.1.1 … 4.5.1 … 5.11.4); KO maddeleri işaretli ve madde başlığının üstünde bölümü yazıyor ("4 Operational processes › 4.5 Product packaging"). 2.8.0'da maddeler dosyadaki sıra numarasıyla ("Madde 86") görünüyordu. Eşleşme dolu bir auditXpress dosyası ve IFS kontrol listesiyle doğrulandı.
- **Madde metinleri (Requirement):** IFS'in madde metinleri telifli olduğu için uygulamayla dağıtılmaz. Kontrol listesi sayfasındaki **Madde metinlerini içe aktar…** ile IFS kontrol listesi dosyasını (madde no ve metin, sekmeyle ayrılmış) bir kez yükleyin. Metinler yalnız bu bilgisayarda saklanır; her maddede auditXpress'teki gibi bir "Requirement" kutusunda görünür ve madde listesinde aranabilir. Madde sayısı ya da numaralar tutmazsa içe aktarma yapılmaz.
- **AI açıklaması madde metnini biliyor:** İngilizce açıklama yazılırken maddenin metni bağlam olarak verilir; metin kopyalanmaz, kanıtta olmayan uygunluk yazılmaz.
- **KO uyarısı:** KO maddesine D verilirse "denetim başarısız sayılır" uyarısı çıkar.
