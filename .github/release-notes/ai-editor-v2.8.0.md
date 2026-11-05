## AGFO AI Editor 2.8.0 — IFS auditXpress (.ifs) raporları

- **auditXpress dosyaları editörde açılıyor:** `.ifs` dosyasını açın ya da sürükleyin, rapor kendi sekmesinde açılır. Kaydet dosyayı auditXpress'in yazdığı biçimde, bire bir aynı yazar. Değiştirmediğiniz hiçbir alan ve sıra değişmez. Her kayıttan önce dosyanın önceki hali yedeklenir.
- **Kontrol listesi:** bütün maddeler listelenir ve süzülebilir: puansız, A/B/C/D/NA, açıklaması eksik, iç alanlı ya da metinde arama. Her maddede şunlar düzenlenir:
  - **Puan:** auditXpress'in kullandığı biçimde yazılır (A=20, B=15, C=5, D=−20, NA=0). B, C ve D'de düzeltme kaydı açılır, A'ya dönünce kapanır; D sayısı güncellenir. Yazılmış bir düzeltici faaliyet hiçbir zaman silinmez.
  - **English explanation, Explanation, Note.**
  - **Maddenin iç alanları:** metinler, evet/hayır seçimleri, kod listeleri ve tekrarlı satırlar. 4.5.1'deki ambalaj listesi gibi satırlar + ile eklenir, × ile silinir. CCP seçici ve kapsamlar gibi auditXpress kayıtlarına bağlı seçimler gösterilir ama değiştirilmez.
- **Rapor alanları:** firma profili, denetim bilgileri, tesis profili, kapsam, özetler. GLN ve yasal kayıt numaraları gibi tekrarlı gruplar dahil.
- **AI:**
  - **İngilizce açıklamayı yaz:** maddenin kanıtından (Explanation, Note, iç alanlar; Türkçe olabilir) puana uygun, resmi IFS dilinde İngilizce açıklama yazar. D'de "Deviation:" ile başlar, NA'da gerekçe yazar. Kanıtta olmayanı eklemez.
  - **✨ EN:** her İngilizce alanın yanında, eşi olan yerel dildeki alanı çevirir. **Boş EN alanlarını doldur** bir bölümdeki boş İngilizce alanların hepsini sırayla çevirir.
- **Özet:** puan dağılımı, açıklaması eksik B/C/D/NA maddeleri (tıklayınca maddeye gider), auditXpress'in son hesapladığı sonuç.
- **Hash:** auditXpress dosyayı kendi hash'iyle imzalıyor ve bu hash dışarıdan hesaplanamıyor. Varsayılan olarak özgün hash korunur; sekmedeki seçimle boşaltılabilir. auditXpress ya da IFS Database düzenlenmiş dosyayı kabul etmezse son kaydı auditXpress'te yapın.
- **Bilinen sınır:** madde numaraları ve madde metinleri `.ifs` dosyasında yok. Maddeler dosyadaki sırayla, iç alanlarının adıyla ya da açıklamalarının başıyla gösterilir. Bir madde sözlüğü eklendiğinde numaralar görünecek.
