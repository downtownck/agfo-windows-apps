# AGFO Mihenk 3.2.0

İngilizce arayüzün ekran görüntüsü alınırken ortaya çıkan çeviri ve yerleşim hataları.

Bunların hiçbiri 3.1.0'da testlerden geçmedi — testler kaçırdı. Her biri için önce
hatayı yakalayan testi yazdım, sonra düzelttim.

## Sayıları yanlış okutan çeviriler

Argümanlar kaynak metindeki sırayla uygulanıyor; üç çeviri o sıraya uymuyordu:

- Denetim raporu **"4 of 2 records passed"** yazıyordu. Doğrusu: 4 kayıt, 2'si uygun.
  Bir uygunluk göstergesinde bu kozmetik bir hata değil.
- İş emri kontrol listesi "%d adımdan %d tamamlandı" yerine tersini sayıyordu.
- Kapatma satırı tarihi ve kişiyi yer değiştiriyordu.

Artık iki test var: biri biçim belirteçlerinin iki dilde aynı tip ve sayıda olduğunu,
öteki metinlerin gerçek sayılarla doğru cümle ürettiğini ölçüyor.

## "Açık" iki şey demek

Türkçede hem durum ("open") hem tema ("light"). Tek sözlük ikisini birden tutamaz, biri
seçilir — seçilen "Light" olmuştu ve **etki değerlendirmesi penceresinde durum "Light"
görünüyordu**. Tema etiketleri artık kendi metnini kullanıyor ("Açık tema"). Aynı sorun
"Aralık" (ay adı / plan aralığı) için zaten çözülmüştü; test şimdi ikisini birden
koruyor.

## On altı çevrilmemiş metin

Demo varlık adları ("Kontrol terazisi", "Referans termometre", "Demo Fabrika"), denetim
raporundaki "Seri no" başlığı, kalibrasyon penceresindeki "Etiket", "Dosya…",
"Sonucu kaydet", ve ötekiler.

Hepsi aynı sebepten kaçmıştı: çıkarma ölçütü Türkçeye özgü harf (ş, ğ, ü, ö, ç, ı)
arıyordu, bu metinlerde öyle bir harf yok. Ölçüt genişletildi — büyük harfle başlayan ya
da boşluk içeren her metin aday; teknik olanlar açık bir listeyle eleniyor, yani yeni bir
metin ya çevrilir ya da bilerek listeye eklenir, sessizce kaçamaz.

Ayrıca iki test daha: demo veri iki dilde kurulup alan alan karşılaştırılıyor, dışa
aktarma tablolarının başlıkları da öyle.

## Yerleşim

- Tablo kolonları başlığın ve içeriğin gerçek genişliğine göre açılıyor. Kolon
  genişlikleri Türkçeye göre seçilmişti; "Result entered" yerine "Result ente"
  görünüyordu.
- Dar kolonlu tablolarda artan genişlik en geniş kolona gidiyor; tablonun sağı boş
  kalırken metin kırpılmıyor.
- Kenar çubuğu 214'ten 252 piksele çıktı: "Impact assessments" sığmıyordu.
- Yüzdeler her dilin kendi yazımıyla: %100 / 100%.
- "1 work orders" gibi tekil/çoğul bozuklukları giderildi.

## Doğrulananlar

Çekirdek 59, arayüz 35 (hem klasik hem modern çizimle), xlsx 5, dil 19 test; güncelleme
modülü testi. Dil testlerinin dördü bu sürümde eklendi ve eklenmeden önce gerçekten
başarısız olduğu görüldü.
