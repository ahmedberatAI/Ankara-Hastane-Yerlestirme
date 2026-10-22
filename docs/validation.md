# Doğrulama ve 91 hastane deneyi · v0.4

22 Ekim 2026. İl genelinde %95, her ilçede %80 talep; talep çarpanı 1, %80 yatak doluluğu, 2.140 temas/hekim/yıl, %10 ek yıllık maliyet. Tutarlar yaklaşık Aralık 2024 TL; kısmi gider kalibrasyonu, saha ölçümü değildir.

## Sonuçlar

| Senaryo | Tesis | Yatak | Hekim | Ortalama süre | Yıllık maliyet göstergesi |
|---|---:|---:|---:|---:|---:|
| Araba · 30 dk · sayı serbest | 46 | 18.550 | 21.613 | 17,32 dk | 143,95 mr TL/yıl |
| EGO · hafta içi 10.00 · 45 dk · sayı serbest | 211 | 24.950 | 22.971 | 26,94 dk | 172,82 mr TL/yıl |
| Araba · 30 dk · en fazla 91 | 46 | 18.550 | 21.613 | 17,32 dk | 143,95 mr TL/yıl |
| EGO · hafta içi 08.00 · 45 dk · en fazla 91 | **Bu veriyle uygun değil** | — | — | — | Coğrafi alt sınır **166** |
| EGO · hafta içi 10.00 · 45 dk · en fazla 91 | **Bu veriyle uygun değil** | — | — | — | Coğrafi alt sınır **171** |
| EGO · cumartesi 10.00 · 45 dk · en fazla 91 | **Bu veriyle uygun değil** | — | — | — | Coğrafi alt sınır **171** |
| EGO · pazar 10.00 · 45 dk · en fazla 91 | **Bu veriyle uygun değil** | — | — | — | Coğrafi alt sınır **170** |

Araba için 91 sınırı altında **46 tesisle geçerli bir plan** bulundu. 31×50, 5×150, 3×300, 2×600, 2×1.000 ve 3×4.050 yatak seçildi. Aynı 50 yatak tipinde hekim sayısı 12–61; 150 yatakta 174–183 değişiyor. Yatak ve hekim artık sabit oranla bağlanmıyor.

Bu plan 5.614.804 kişi eşdeğerinin talebini karşılıyor: il %95, bütün ilçeler en az %80. Bina yatırımı 146,96 milyar; işletme gideri 135,51 milyar/yıl; yıllıklaştırılmış toplam 143,95 milyar/yıl. 25 yıl/%3 sabit fiyat varsayımı kullanılır. Bu özel grup proxy tutarlarına dayalı eksik kapsamlı maliyet göstergesidir; Ankara kamu hastanelerinin gerçek gider toplamı değildir.

**46 minimum hastane sayısı değildir.** Maliyet aşaması açığı yaklaşık %1,82; 91 sınırlı koşunun süre aşaması açığı yaklaşık %59,79. Son plan ilk maliyet planının 18,29 dakikalık ortalamasını 17,32’ye düşürdü, fakat en kısa yol yerleşimi ispatlanmadı. Zaman sınırlı tekrar koşularında yerleşim ve açıklık değişebilir. Yeni EGO serbest sayı çözümü 211’dir; bu da minimum sayı değildir. Maliyet açığı %2,61, süre aşaması açığı %80,12’dir. Önceki araba çözümleri değiştirilmeden yeni sürümde tekrar denetlenmiştir.

## 91 için EGO kanıtının kapsamı

`backend/feasibility.py`, 4.701 adayın ve süre içindeki tüm ağ bağlantılarının tamamını kullanır. Kaynak kapasitesi, yapı-izi çakışmaları ve maliyetler kaldırıldığında bile asgari coğrafi konum sayısı dört profilde **166–171** bulundu (alt sınır = geçerli sayı, açıklık 0). Bu yüzden kapasite eklemek aynı ağ/eşik/hedefler altında 91’i mümkün yapamaz.

Eski 291 sınırını yükselten bir hata giderildi: doğrudan yürüyüş de 15 dakikada kesiliyordu. Yalnız bu düzeltmeyle alt sınır 169 olur. Yeni profiller resmî EGO kalkış listelerini kullanır; **665 yön/varyantın 427’si** ağa bağlanmıştır. Ara durak süreleri tahminidir; eksik hizmetler erişimi düşük gösterebilir. Bu nedenle sonuç gerçek EGO hizmetinin yetersizliğini veya kesin hastane ihtiyacını kanıtlamaz. İlçe tabanı kaldırılan ayrı coğrafi kontrolde alt sınır 35’tir; kapasite içermeyen bu kontrol 91’in yeterliliğini göstermez. [Kontrollü deney ve kapsam](transit-validation.md).

Aday örneklemesi, mahalle temsil noktaları ve 15 dakika ilk/son durak yürüyüşü de sonucu etkiler. Mevcut 91 hastanenin yerlerini/kapasitelerini test etmez: sıfırdan en fazla 91 konum test edilir. Resmî 2024 envanteri 85’tir.

## Hekim varsayımının duyarlılığı

Aynı araba/91 koşulunda Ankara Üniversitesi örneklerinin **835 temas/hekim/yıl** oranıyla **50 tesis, 18.650 yatak ve 55.232 hekim** gerektiren geçerli çözüm bulundu. Ortalama 16,70 dakika, yıllık maliyet göstergesi 251,77 milyar TL.

Bu hekim sayısı Ankara’nın bütün sektörlerdeki 26.798 hekiminden fazladır. Bina sayısının yetmesi, personelin fiilen mevcut olduğu anlamına gelmez. Üniversite ve özel grup oranları farklı hizmet/eğitim karışımlarını taşır; il için doğru klinik kadro standardını tek başına kanıtlamaz. [Duyarlılık verisi](../data/processed/sensitivity-results.json).

## Bağımsız kontroller

- 29 birim/API testi geçti. Tam sayımla küçük yer/kadro problemi; iki kaynak; alan; çakışma; sayı sınırı; maliyet ve talep korunması; imkânsızlık/sonuçlandırılamama ayrımı; tarifeli yolculuk ve veri ayrıştırma sınırları.
- Sekiz kayıtlı gerçek veri senaryosu: yedi ana koşu + üniversite duyarlılığı. Geçerli çözümlerde **bütün** atamalar, talebin iki kez sayılmaması, yol süreleri, il/ilçe paydaları, hekim/yatak, toplam alan, tam sayılık, çakışma ve yıllık maliyet yeniden hesaplandı.
- Büyük yapı izlerine örnek sürüş rotaları Dijkstra ile; toplu taşıma rotaları gün/saat bağımlı yolculuk hesabıyla matris değerlerine karşı denetlendi. Dört EGO profilinin sekizer başlangıcında bütün hedefler bağımsız tek-başlangıç hesabıyla karşılaştırıldı.
- 4.701 yapı izinin yol/yüzey ray koridorlarıyla kesişimi yok. Matrisler 1.413 × 4.825 (4.701 aday + 124 OSM hastanesi). Negatif süre/NaN yok.
- Dört sağlık PDF’si SHA-256 ile, Ankara ve üniversite satırları ve MLP mali kalemleri metin/görüntüyle doğrulandı. 2024 V-B sınıfı görsel kontrol edildi.
- Üretim TypeScript/Vite derlemesi geçti. Tarayıcıda hafta içi 10.00/91 sonucu 171; gün değiştirip tekrar hesaplanan pazar 10.00/91 sonucu 170 olarak görüldü. Gün değişiminde eski sonuç uyarısı ve devre dışı dışa aktarım doğrulandı. Sayı serbest EGO hesabı 211 tesis verdi. Birlik–Hacı Bayram rotasında 413-7, 10.04 binişi, 1,3 dakika bekleme ve 44,5 dakika toplam süre; tahmini ara durak uyarısıyla gösterildi. [Görsel kontrol](screenshots/ego-tarife.png). Canlı süre sınırlı koşunun optimalite açıklıkları kayıtlı deneyden küçük farklar gösterebilir.
- 390 px çerçevede mevcut ana yerleşim görsel olarak kontrol edildi; yeni EGO kontrolünün etkileşim denetimi masaüstünde yapıldı. Önceki sürümün yöntem penceresi ve JSON indirme kontrolleri ayrıca korunur.

Kaynaklar: [kalibrasyon araştırması](capacity-research.md), [yöntem](methodology.md), [kalite raporu](../data/processed/quality-report.json), [dosya kimlikleri](../data/processed/manifest.json).

Örnekler: [araba](../data/processed/example-car-result.json), [EGO](../data/processed/example-transit-result.json), [araba ≤91](../data/processed/example-car-91-result.json), [EGO ≤91](../data/processed/example-transit-91-result.json), [835 duyarlılığı](../data/processed/example-car-91-university-result.json). Arayüz canlı hesaplamaları kullanır; sabit 91 deney kartı bundan ayrı etiketlenir.

```powershell
.venv\Scripts\python.exe -m pytest -q
npm run build
.venv\Scripts\python.exe scripts/verify_health_sources.py
.venv\Scripts\python.exe scripts/audit_data.py
.venv\Scripts\python.exe scripts/verify_release.py
.venv\Scripts\python.exe scripts/verify_transit.py
```

Yeni çözümler üretmek için `verify_release.py --write-examples`, ardından `manifest.py`. Süre sınırlı çözücünün çıktıları değişirse bu tablo ve ekran görüntüleri de güncellenmelidir.
