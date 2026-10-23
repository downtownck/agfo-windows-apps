## AGFO AI Editor 2.2.1 — BRCGS raporları: İngilizce ekranlar, bölüm bazında NA/NC, AI rapor metni

- **İngilizce:** BRCGS ekranlarının tamamı İngilizce. Kılavuz soruları, ipuçları, seçenekler ve "yazmayın" kuralları (2.051 metin) İngilizce gösterilir. Kayıtlı yanıtlar ve Excel formları eskisi gibi eşleşir. Çeviriler ayrı bir dil dosyasında tutulur.
- **AI rapor metni:** bölümün kanıtlarını (kılavuz yanıtları ve kanıt notu, Türkçe de olabilir) düğmeyle İngilizce rapor diline çevirir. Metin doğrudan bölümün "Report text" kutusuna yazılır; elle düzeltilebilir. Kanıt kutuları kaynak olarak kalır. Kanıt sonradan değişirse uyarı gösterilir. Bölümdeki NC açıklamaları da aynı anda İngilizceye çevrilir.
- **Her bölümde NA ve NC:** bölüm sayfasında uygulanamaz alt maddeler (gerekçesiyle) ve uygunsuzluklar (Critical / Major / Minor, şablonda varsa Fundamental) eklenir. Bunlar NA tablolarına ve NC Action Plan'a yazılır.
- **Tarama ve sayım:** "Scan non-conformities and NA" bölüm metinlerindeki "Minor NC Ref. 2.2.2: …" ifadelerini bulur, NC'leri türüne göre ve NA maddelerini sayar. Raporun "Number of non-conformities" alanları bu sayılardan doldurulur. Artık "uygunsuzluk" kelimesi geçen sıradan cümleler NC sayılmıyor.
- **Gerçek rapor biçimi:** DOCX'e yazarken bölümün NC'leri metnin sonuna "Minor NC Ref. 2.7.1: …" biçiminde eklenir. Raporun başka bir yerinde zaten yazılıysa tekrar eklenmez. Bölümün tamamı uygulanamazsa ve metin boşsa "N/A: <gerekçe>" yazılır; alt madde NA'ları resmi NA tablosuna gider. Uygunsuzluk yoksa AI, bölümü o maddeye özgü bir uygunluk ifadesiyle bitirir ("Records sampled during the audit were found to be complete, legible…" gibi). Biçim gerçek bir Food Safety Issue 9 raporundan alındı.
- **Düzeltmeler:**
  - Bir kutuda "root cause analysis", "corrective action" gibi ifadeler geçince aynı tablodaki sonraki kutular DOCX'e yazılmıyordu (gerçek raporda 3.8–3.11 boş çıkıyordu). NC tabloları artık metne göre değil, resmi şablonun yapısına göre belirleniyor.
  - Word'de yazılmış raporları içe aktarırken kutu içindeki paragraflar bitişik okunuyordu; artık her paragraf ayrı satır.
  - Rapor gezgininin sol ağacında bir öğeye tıklayınca pencere donuyordu.
