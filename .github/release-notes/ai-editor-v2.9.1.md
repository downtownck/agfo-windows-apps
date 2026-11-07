## AGFO AI Editor 2.9.1 — Video: yeni ffmpeg uyumu

- **"Unrecognized option 'filter_complex_script'" hatası giderildi:** Uygulamanın indirdiği güncel ffmpeg bu seçeneği kaldırmış; video oluşturma bu yüzden başlamıyordu. Artık yeni sözdizimi (`-/filter_complex`) kullanılıyor; bilgisayarda eski bir ffmpeg varsa eski seçeneğe kendiliğinden geçiliyor. İndirilmiş ffmpeg'i silmeniz ya da yeniden indirmeniz gerekmez.
