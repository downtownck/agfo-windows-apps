AGFO Router Connect 1.1.1

- Düzeltme: bazı bilgisayarlarda derlenen EXE "No module named 'tkinter'" hatasıyla açılmıyordu. Derleme artık EXE'yi kendi içinde sınar (`--selftest`); tkinter eksikse bir sonraki Python sürümüyle yeniden dener ve çalışan ilk EXE'yi kurar. PyInstaller'ın en iyi desteklediği Python sürümleri (3.10-3.13) öne alınır.
- Yayın öncesi kontrol de aynı öz-denetimi çalıştırır.
