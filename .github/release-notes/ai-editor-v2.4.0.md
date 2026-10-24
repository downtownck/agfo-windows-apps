## AGFO AI Editor 2.4.0 — Word görünümünde düzenleme

- **Word görünümünde yerinde düzenleme:** sayfadaki bir alana ya da rapor kutusuna tıklayınca, tam o yerde ve o boyutta bir düzenleyici açılır: metin alanında yazı kutusu, seçimli alanda açılır liste (seçince kaydolur), uzun alanlarda ve rapor kutularında çok satırlı kutu. Değişiklik hemen sayfada görünür (sarı işaretli); Word sayfayı arka planda yeniden çizer.
  - **Enter** (çok satırlıda **Ctrl+Enter**) ya da "✓ Done": kaydet · **Esc** ya da "✕": vazgeç · **Tab / Shift+Tab**: kaydedip sonraki/önceki alana geç · başka bir yere tıklamak da kaydeder.
  - "Form…" o alanı form görünümünde açar (kılavuz soruları, kanıt notu, NA/NC için).
  - Birleşik kutularda (birden çok madde tek kutuda) düzenlenen metin madde başlıklarına göre yeniden bölümlere ayrılır.
  - Etiketli ama Word alanı olmayan hücreler (CP/AB/SD'de "Company name", "Address", "Country") de tıklanıp düzenlenebilir.
  - NC sayıları (Critical/Major/Minor) NC listesinden sayıldığı için elle değiştirilmez; tıklayınca NC Action Plan açılır. NA/NC ve diğer resmi tablolar şimdilik formda düzenlenir.
- **Düzeltme:** Word'de yazılmış, dolu bir rapor kutusu yeniden kaydedilince metin mavi oluyordu (kutunun paragraf stili "Başlık 3"; Türkçe Word'de stil kimliği `Balk3`). Artık dolu kutuların kendi biçimine dokunulmuyor; biçim yalnız şablonun gri yer tutucu metni değiştirilirken düzeltiliyor.
- Sayfadaki alanları bulma daha dayanıklı: kısa ya da genel bir metin (ör. boş hücrenin "Country" etiketi) ilerideki bir yerde de geçse, sonraki alanlar kaybolmuyor.
