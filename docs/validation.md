# Doğrulama ve 91 hastane deneyi · v0.3

22 Ekim 2026. İl genelinde %95, her ilçede %80 talep; talep çarpanı 1, %80 yatak doluluğu, 2.140 temas/hekim/yıl, %10 ek yıllık maliyet. Tutarlar yaklaşık Aralık 2024 TL; kısmi gider kalibrasyonu, saha ölçümü değildir.

## Sonuçlar

| Senaryo | Tesis | Yatak | Hekim | Ortalama süre | Yıllık maliyet göstergesi |
|---|---:|---:|---:|---:|---:|
| Araba · 30 dk · sayı serbest | 46 | 18.550 | 21.613 | 17,32 dk | 143,95 mr TL/yıl |
| EGO ağ senaryosu · 45 dk · sayı serbest | 370 | 30.750 | 23.795 | 19,96 dk | 198,34 mr TL/yıl |
| Araba · 30 dk · en fazla 91 | 46 | 18.550 | 21.613 | 17,32 dk | 143,95 mr TL/yıl |
| EGO ağ senaryosu · 45 dk · en fazla 91 | **Uygun değil** | — | — | — | Coğrafi alt sınır **291** |

Araba için 91 sınırı altında **46 tesisle geçerli bir plan** bulundu. 31×50, 5×150, 3×300, 2×600, 2×1.000 ve 3×4.050 yatak seçildi. Aynı 50 yatak tipinde hekim sayısı 12–61; 150 yatakta 174–183 değişiyor. Yatak ve hekim artık sabit oranla bağlanmıyor.

Bu plan 5.614.804 kişi eşdeğerinin talebini karşılıyor: il %95, bütün ilçeler en az %80. Bina yatırımı 146,96 milyar; işletme gideri 135,51 milyar/yıl; yıllıklaştırılmış toplam 143,95 milyar/yıl. 25 yıl/%3 sabit fiyat varsayımı kullanılır. Bu özel grup proxy tutarlarına dayalı eksik kapsamlı maliyet göstergesidir; Ankara kamu hastanelerinin gerçek gider toplamı değildir.

**46 minimum hastane sayısı değildir.** Maliyet aşaması açığı yaklaşık %1,82; 91 sınırlı koşunun süre aşaması açığı yaklaşık %59,79. Son plan ilk maliyet planının 18,29 dakikalık ortalamasını 17,32’ye düşürdü, fakat en kısa yol yerleşimi ispatlanmadı. Zaman sınırlı tekrar koşularında yerleşim ve açıklık değişebilir. EGO serbest sayı çözümü 370’tir; bu da minimum sayı değildir.

## 91 için EGO kanıtının kapsamı

`backend/feasibility.py`, 4.701 adayın ve süre içindeki tüm ağ bağlantılarının tamamını kullanır. Kaynak kapasitesi, yapı-izi çakışmaları ve maliyetler kaldırıldığında bile asgari coğrafi konum sayısı **291** bulundu (alt sınır = geçerli sayı, açıklık 0). Bu yüzden kapasite eklemek aynı ağ/eşik/hedefler altında 91’i mümkün yapamaz. Kırsal erişim ve eksik tarife/ağ kapsamı temel etkendir.

Bu, **tarifesiz OSM EGO senaryosu** için ispat; gerçek EGO hizmetinin yetersizliği veya Ankara’da gerçekten 291 hastane gerektiği iddiası değildir. Aday örneklemesi, mahalle temsil noktaları, 15 dakika ilk/son yürüyüş ve eksik GTFS sonucu değiştirebilir. Mevcut 91 hastanenin yerlerini/kapasitelerini test etmez: sıfırdan en fazla 91 konum test edilir. Resmî 2024 envanteri 85’tir.

## Hekim varsayımının duyarlılığı

Aynı araba/91 koşulunda Ankara Üniversitesi örneklerinin **835 temas/hekim/yıl** oranıyla **50 tesis, 18.650 yatak ve 55.232 hekim** gerektiren geçerli çözüm bulundu. Ortalama 16,70 dakika, yıllık maliyet göstergesi 251,77 milyar TL.

Bu hekim sayısı Ankara’nın bütün sektörlerdeki 26.798 hekiminden fazladır. Bina sayısının yetmesi, personelin fiilen mevcut olduğu anlamına gelmez. Üniversite ve özel grup oranları farklı hizmet/eğitim karışımlarını taşır; il için doğru klinik kadro standardını tek başına kanıtlamaz. [Duyarlılık verisi](../data/processed/sensitivity-results.json).

## Bağımsız kontroller

- 23 birim/API testi geçti. Tam sayımla küçük yer/kadro problemi; iki kaynak; alan; çakışma; sayı sınırı; maliyet ve talep korunması; imkânsızlık/sonuçlandırılamama ayrımı.
- Beş kayıtlı gerçek veri senaryosu: dört ana koşu + üniversite duyarlılığı. Geçerli çözümlerde **bütün** atamalar, talebin iki kez sayılmaması, yol süreleri, il/ilçe paydaları, hekim/yatak, toplam alan, tam sayılık, çakışma ve yıllık maliyet yeniden hesaplandı.
- Büyük yapı izlerine örnek sürüş ve toplu taşıma rotaları, grafikten yeniden bulunan Dijkstra süreleriyle matris değerlerine karşı denetlendi.
- 4.701 yapı izinin yol/yüzey ray koridorlarıyla kesişimi yok. Matrisler 1.413 × 4.825 (4.701 aday + 124 OSM hastanesi). Negatif süre/NaN yok.
- Dört sağlık PDF’si SHA-256 ile, Ankara ve üniversite satırları ve MLP mali kalemleri metin/görüntüyle doğrulandı. 2024 V-B sınıfı görsel kontrol edildi.
- Üretim TypeScript/Vite derlemesi geçti. Masaüstü/mobil arayüz, yöntem penceresi, 91 karşılaştırması, parametre sonrası eski sonuç işareti ve JSON dışa aktarımı ayrıca denetlendi.

Kaynaklar: [kalibrasyon araştırması](capacity-research.md), [yöntem](methodology.md), [kalite raporu](../data/processed/quality-report.json), [dosya kimlikleri](../data/processed/manifest.json).

Örnekler: [araba](../data/processed/example-car-result.json), [EGO](../data/processed/example-transit-result.json), [araba ≤91](../data/processed/example-car-91-result.json), [EGO ≤91](../data/processed/example-transit-91-result.json), [835 duyarlılığı](../data/processed/example-car-91-university-result.json). Arayüz canlı hesaplamaları kullanır; sabit 91 deney kartı bundan ayrı etiketlenir.

```powershell
.venv\Scripts\python.exe -m pytest -q
npm run build
.venv\Scripts\python.exe scripts/verify_health_sources.py
.venv\Scripts\python.exe scripts/audit_data.py
.venv\Scripts\python.exe scripts/verify_release.py
```

Yeni çözümler üretmek için `verify_release.py --write-examples`, ardından `manifest.py`. Süre sınırlı çözücünün çıktıları değişirse bu tablo ve ekran görüntüleri de güncellenmelidir.
