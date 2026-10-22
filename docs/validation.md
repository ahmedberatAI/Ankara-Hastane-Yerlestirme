# Doğrulama ve örnek hesaplamalar

22 Ekim 2026 · kapasite modeli v0.2.0. Sayılar resmî nüfus ve il düzeyindeki sağlık kullanımı, işlenmiş yol ağı ve açık planlama varsayımlarından üretilmiştir. Saha ölçümü veya kesin yatırım önerisi değildir.

## Veri kontrolleri

- 25 ilçenin nüfus toplamı **5.910.320** ile il toplamına eşit.
- 1.427 mahalleden **1.413’ü** konumlandırıldı; modellenen nüfus **5.889.804**. Konumsuz **20.516 kişi** resmî talep paydasında korunuyor.
- **1.397 adayın** 45 m yarıçaplı yapı izi yol ve yüzey ray koridorları dışında; adaylar Ankara il sınırında. Seçilen yapı izlerinin birbirleriyle çakışması da modelde yasak.
- İki süre matrisi de **1.413 × 1.521**: 1.397 aday + 124 mevcut OSM hastanesi. Negatif süre ve `NaN` yok; erişilemeyen bağlantılar `inf`.
- Mesafeler metre tabanlı UTM 36N ile denetleniyor.
- Sağlık Bakanlığı 2024 PDF’sindeki Ankara yatak, hekim, başvuru, yatış ve yatılan gün satırları sayfa görüntüsü ve metinle doğrulandı. 2026 yapı birim bedellerinin IV-C ve V-B sınıfları tebliğ nüshası üzerinden kontrol edildi.

Aday geometri kontrolü [quality-report.json](../data/processed/quality-report.json), dosya kimlikleri [manifest.json](../data/processed/manifest.json), sağlık kaynaklarının sayfa ve kapsam ayrıntıları [kapasite araştırması](capacity-research.md) içindedir.

## Gerçek veriyle kapasite ve güzergâh kontrolü

Aşağıdaki değerler `verify_release.py --write-examples` koşusunda kaydedilen sonuçlardır. Talep çarpanı 1, yatak doluluk tavanı %80, hekim başına yıllık başvuru 4.000 ve süre iyileştirmesi için ek yapım bütçesi %10 kullanıldı.

| Gösterge                               |                         Araba |              EGO ağ senaryosu |
| -------------------------------------- | ----------------------------: | ----------------------------: |
| Süre eşiği                             |                         30 dk |                         45 dk |
| Genel hedef / ilçe tabanı              |                     %95 / %80 |                     %95 / %80 |
| Bulunan tesis sayısı                   |                           172 |                           439 |
| Planlanan yatak                        |                        21.300 |                        33.850 |
| Planlanan hekim                        |                        12.780 |                        20.310 |
| Son bina yapım göstergesi              |            166,5848 milyar TL |            290,8144 milyar TL |
| İlk maliyet aşamasının bedeli          |            151,6686 milyar TL |            264,5582 milyar TL |
| İkinci aşamanın bütçe tavanı           |           166,83546 milyar TL |           291,01402 milyar TL |
| Karşılanan talep payı                  |                           %95 |                           %95 |
| Atanan nüfus eşdeğeri                  |                     5.614.804 |                     5.614.804 |
| Atanmayan veya konumsuz nüfus eşdeğeri |                       295.516 |                       295.516 |
| Atanan talep ağırlıklı ortalama süre   |                       6,93 dk |                       6,73 dk |
| İlk çözümün ortalama süresi            |                       8,28 dk |                      12,73 dk |
| Ortalama süre iyileşmesi               |                        %16,30 |                        %47,14 |
| Toplam nüfus üzerinden P90             |                      10,38 dk |                      22,35 dk |
| Hekim başvuru kapasitesi kullanımı     |                        %88,17 |                        %55,48 |
| Tanımlı yatak-gün kapasitesi kullanımı |                        %83,27 |                        %52,40 |
| Maliyet aşaması optimalite açığı       |                         %3,30 |                         %2,85 |
| Süre aşaması optimalite açığı          |                        %14,33 |                        %22,46 |
| Çözüm durumu                           | Geçerli; optimum kanıtlanmadı | Geçerli; optimum kanıtlanmadı |

İki modda da yıllık başvuru tahmini **47.445.297**, atanan başvuru **45.073.032**, toplam yatış tahmini **1.072.245**, yatış günü talebi **5.451.817** ve atanan yatış günü **5.179.227**. Başvurular tekil hasta değildir. Yatak kullanım oranı, %80 doluluk varsayımıyla tanımlanan kapasiteye bölünür; fiziksel yatak doluluğuyla aynı gösterge değildir.

Çıktılar [araba](../data/processed/example-car-result.json), [EGO](../data/processed/example-transit-result.json) ve [doğrulama özeti](../data/processed/validation-results.json) dosyalarında. Arayüz yeni parametrelerde API hesaplaması yapar; örnek dosyaları sabit sonuç olarak oynatmaz. Çözücü süre sınırlı olduğundan başka koşularda konumlar, sayılar ve ispat açıkları değişebilir. Her mahalle için süre eşiğindeki en yakın 16 aday kullanılır; optimum iddiası tüm sürekli Ankara coğrafyasını kapsamaz.

**172 veya 439, Ankara’nın gerçek minimum hastane sayısı değildir.** Kapasitesiz önceki modelin 24 tesislik araba sonucu bu sürümün bulgusu olarak kullanılmamalıdır. Tesis büyüklükleri ve hekim üretkenliği varsayımsaldır. EGO’da doğrulanmış GTFS bulunmaması, eksik hat kapsamı, ilk/son yürüyüş sınırı, 50 yataklık en küçük tesis şablonu ve kırsal erişim tabanı çok sayıda yerel tesis gerektirebilir. EGO çözümünde birçok yolculuk yalnız yürüyüştür. Farklı süre eşikleri, tesis sayıları ve bütçeler nedeniyle iki ortalamadan ulaşım modlarının hız sıralaması çıkarılamaz.

Bina yapım göstergesi KDV, arsa, dış altyapı, tıbbi cihaz, personel ve işletme giderlerini kapsamaz. Mevcut OSM hastanelerinin karşılaştırması yalnız coğrafi erişimdir; kapasite eşdeğerliği kanıtı değildir.

## Otomatik doğrulama

- `python -m pytest -q`: **20 test geçti**. Küçük örnekte tüm tesis/şablon kombinasyonları ve bağımsız akış hesabıyla maliyet optimumu karşılaştırıldı. Yatak ve hekim darboğazları, artan talep, çözümsüz kapasite, ek bütçeyle süre iyileştirmesi, ilçe tabanı, konumsuz nüfus, çakışan yapı izleri ve API parametre sınırları denetlendi. Önceki ağ ve kapsama testleri de geçiyor.
- `npm run build`: TypeScript kontrolü ve Vite üretim derlemesi başarılı.
- `python scripts/verify_release.py --write-examples`: iki modda tüm bölünmüş atamalar bağımsız olarak yeniden toplandı. Her mahallenin talep sınırı, tesis başına yatak/hekim yükü, il ve ilçe tabanı, seçilen tesislerin çakışmaması, bütçe tavanı, maliyet toplamı, ağırlıklı süre ve P90 doğrulandı.
- Araba güzergâhı **Balıkhisar → Altınova**: 15,13765 dk. EGO güzergâhı **Atıfbey → Basınevleri**: 33,09148 dk, **203-7 / Dışkapı Metro İstasyonu** binişi. API süreleri matrisle 0,001 dakika toleransında uyuşuyor; yol/hat geometrileri mevcut.
- `python scripts/verify_health_sources.py`: iki PDF’nin SHA-256 kimliği, dört Ankara tablo satırı, türetilmiş oranlar ve tesis maliyet aritmetiği doğrulandı. PDF denetimi isteğe bağlı PyMuPDF bağımlılığı kullanır; uygulama çalışma zamanı için gerekmez.
- Önceki ham geometri denetiminde yol/ray taşması **0**; bu sürüm aday koordinatlarını ve ulaşım matrislerini değiştirmez.

Starlette/AnyIO bağımlılığından bir kullanımdan kaldırma uyarısı var; başarısız test yok. Yerel Docker daemon’u çalıştırılmadığından konteyner çalışması doğrulanmadı.

## Arayüz kontrolü

Son üretim derlemesi `127.0.0.1:8000` üzerinden kontrol edildi. Kapasite şeridinin dar masaüstü görünümünde sıkışma sorunu düzeltildi. Yatak, hekim ve maliyet değerleri görünür; maliyet ve süre optimalite açıkları ayrı açıklanıyor.

Karapürçek aramasında bölünmüş talep payları açıldı; ilk hastaneden Başak’a geçildiğinde rota ve süre 11,7 dakikadan 9,8 dakikaya değişti. Hekim başına başvuru kapasitesi değiştirildiğinde eski sonucu indirme düğmesi devre dışı kaldı. Resmî gözlemler ile değiştirilebilir planlama varsayımları yöntem penceresinde ayrı gösteriliyor.

Karapürçek tesis penceresinde 150 yatak, 90 hekim, 360.000/360.000 başvuru ve 41.367/43.800 yatış günü yükü görüntülendi. EGO’da Büyükbayat → Şehriban, 141 numaralı otobüsle 28,7 dakika olarak haritada doğrulandı. Rota paneline yükseklik sınırı ve gerektiğinde kaydırma eklendi; panel açıkken harita alanı büyüyor.

390 px genişliğinde gömülü mobil görünümde sonuç ve kapasite kartları incelendi; bu gerçek cihaz veya tüm tarayıcılar üzerinde test iddiası değildir. Tarayıcı konsolunda uygulama hatası yoktu. İndirilen EGO JSON’unda 23 kaynak, kapasite parametreleri, tesis yükleri, 25 ilçe ve dışa aktarma zamanı doğrulandı. Bu ayrı UI koşusu 486 tesis buldu; yukarıdaki 439 tesislik kayıtlı doğrulama koşusuyla farklılık süre sınırlı çözümden kaynaklanır. İkisi de bütçe ve kapasite koşullarını sağlar; tesis sayısı sabit veya kanıtlanmış minimum değildir.

Harita altlığı haricî OSM karo servisine bağlıdır; erişim kesilirse yerel ana yol katmanı açılır. Hesaplanan süreler karolardan türetilmez. Görseller `docs/screenshots/` altındadır.
