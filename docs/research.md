# Ankara hastane yerleşimi: veri kaynakları araştırması

Araştırma / erişim tarihi: **22 Ekim 2026**. Kapsam: Ankara’nın 25 ilçesinde sıfırdan yerleşim; mevcut binalar engel değil, ulaşım koridorları yerleşim alanı değil.

## 1. Mahalle nüfusu: birincil kaynak TÜİK

[2025 ADNKS Favori Tablolar çalışma kitabı](https://www.tuik.gov.tr/media/announcements/2025ADNKS_FavoriTablolar.xlsx) doğrudan indirildi. `MAHALLE NÜFUSU`, `İLÇE NÜFUSU` ve `İL NÜFUSU` sayfaları birlikte işlendi. İl kodu 6 ile Ankara seçildi; mahalle ve ilçe kodları korundu. Tarih 31 Aralık 2025’tir.

| Kontrol                                                       |     Sonuç |
| ------------------------------------------------------------- | --------: |
| Resmî Ankara nüfusu                                           | 5.910.320 |
| 25 ilçe toplamı                                               | 5.910.320 |
| Yayımlanan mahalle sayısı                                     |     1.427 |
| Mahalle tablosundaki nüfus                                    | 5.907.026 |
| İl toplamına göre yayımlanmayan / bu tabloda yer almayan fark |     3.294 |
| OSM ile konumlandırılan mahalle                               |     1.413 |
| Konumlandırılan nüfus                                         | 5.889.804 |
| Toplam konumsuz nüfus                                         |    20.516 |

Çalışma kitabının notu, nüfusu 10 ve altında olan mahalleleri ve OSB’leri mahalle tablosundan dışlar. İl–mahalle toplamı farkı bilinmeyen bir mahalleye dağıtılmadı. Adı eşleşmeyen 11 ve bağlı yola 1.500 metreden uzak 3 mahalledeki toplam 17.222 kişi ve bu 3.294 kişi birlikte 20.516 kişilik konumsuz grubu oluşturur. Kapsama paydasında il ve ilçe resmî toplamları kullanılır.

İlçe farkları: Çubuk 14; Kahramankazan 1; Polatlı 1; Sincan 858; Yenimahalle 2.420. Bu farkların her birinin hangi OSB veya küçük mahalleden geldiği tahmin edilmedi.

Dosya SHA-256: `72e36cf8f1eeb2e8c12480e14148b42448c6aad05d19932d94add37f360980c1`.

Yaş, sağlık başvurusu, hastalık yükü veya gündüz nüfusu bu dosyadan türetilmedi. İlk sürümde kişi başına ihtiyaç ağırlığı eşittir. Sonraki aşamada resmî yaş dağılımı ve anonimleştirilmiş hizmet talebiyle ihtiyaç ağırlıkları ayrıca kalibre edilmelidir.

## 2. Mahalle sınırları ve yerleşim noktaları

[ABB CBS Başkent açık veri kataloğu](https://cbsbaskent.ankara.bel.tr/acik-veri) ve [Ankara Kent Rehberi Hizmeti kaydı](https://cbsbaskent.ankara.bel.tr/acik-veri/ankara-kent-rehberi-hizmeti) incelendi. Katalog kaydı, indirilebilir ham veri taahhüdü olmadığını açıklıyor. Web haritasının varlığı, bütün mahalle poligonlarının açık bir indirme ve yeniden kullanım izniyle sunulduğu şeklinde yorumlanmadı. [Demografi Ankara](https://demografi.ankara.bel.tr/) ek doğrulama kaynağı olarak kaydedildi.

İlk uygulamada OSM’nin il/ilçe poligonları, mahalle/köy yer etiketleri ve bulunabilen alt idari sınırlar kullanıldı. Eşleştirme **normalleştirilmiş ad + ilçe içinde bulunma** koşuluyla yapıldı. Yer etiketi varsa tercih edildi; yoksa poligonun içindeki temsil noktası kullanıldı. Bu, resmî UAVT koduyla yapılmış geometrik eşleştirme veya nüfus ağırlıklı mahalle merkezi değildir.

Gerekli iyileştirme: ABB’den sürüm tarihi, UAVT/ADNKS kodu, koordinat sistemi ve yeniden kullanım koşulları belirtilmiş resmî mahalle poligonları. Mahalle içi dağılım için [WorldPop](https://api.worldpop.org/v2/) veya resmî nüfus ızgaraları düşünülebilir; model tahmini raster, resmî nüfus sayımı diye sunulmamalı ve mahalle toplamlarına kalibre edilmelidir.

## 3. Karayolu ve yürüme ağı

[Geofabrik Türkiye](https://download.geofabrik.de/europe/turkey.html) kaynağından 651.173.145 baytlık OSM PBF indirildi. Dosya içindeki veri tarihi **2026-10-20T20:23:47Z**. İl sınırı ve yaklaşık 5 km çevre koridoru işlendi; sınır yakınında kısa süreli il dışına çıkan güzergâhlar mümkündür.

Karayolu çizgileri ortak OSM düğüm kimlikleriyle bağlandı. Böylece farklı seviyedeki köprü/tünel çizgileri yalnız çizgileri kesişiyor diye birleştirilmez. Tek yön, dönel kavşak varsayımı, temel araç/yaya erişim etiketleri ve yol sınıfları işlenir. Sayısal `maxspeed` değerleri varsayılan hızı sınırlar.

Araba süreleri ölçülmüş trafik süreleri değildir. Dönüş yasakları, koşullu erişim, trafik ışıkları, yokuş, hava ve saatlik yoğunluk yoktur. Eski trafik çarpanı duyarlılık deneylerine aittir; güncel ana arayüzde bulunmaz. Sonraki aşamada OSM dönüş ilişkilerini işleyen özel [OSRM](https://project-osrm.org/docs/v26.6.1/http) veya Valhalla hizmeti ve doğrulanmış hız profilleri kullanılmalıdır. Büyük matrisler ücretsiz demo sunucularına gönderilmez.

## 4. EGO ve raylı sistem: resmî kalkışlar ve koordinatlar, kısmi hizmet kapsamı

22–23 Ekim 2026 araştırmasında [EGO hareket saatleri](https://www.ego.gov.tr/hareketsaatleri) kataloğundaki **665 yön/varyant ve 10.811 durak kimliği** işlendi. Hafta içi, cumartesi ve pazar kalkışları ile hat süreleri kullanıldı; **430 yön/varyant** zaman bağımlı ağa bağlandı. Ara durak varışları resmî tarifede bulunmadığından ağ mesafeleriyle tahmin edilir. Çözülemeyen özel sefer notları varsayılan tam-hat seferi yapılmaz. “Süresi” alanının her hatta tek yön mü bütün durak zinciri mi olduğu doğrulanmadı; zincire dağıtılması model varsayımıdır.

[Resmî Başkentkart](https://baskentkart.ego.gov.tr/) durak sorgusu artık 10.743 otobüs durağının tamamına güncel kaynak koordinatı sağlıyor; 68 ray istasyonu OSM ile eşleştiriliyor. Yeni kesitte eksik durak koordinatı ve kullanılan tarihsel ek koordinat yok. Gerçek HTTP gözlem zamanı bilinen 10.740 kayıt ile zamanı bilinmeyen üç eski yanıt ayrılıyor. Tarife HTML önbelleğinin bilinmeyen gözlem zamanı işleme tarihiyle doldurulmadı. Gün türüne göre yayımlanmış kalkışların yaklaşık %72–75'i modele bağlanır; bu nüfus kapsamı değildir. Adla başlangıç notları ve yol kesiti eşleştirmeleri bazı kırsal hizmetleri dışarıda bırakıyor. Eksik veri gerçek hizmet yokluğu sayılmaz.

[EGO araştırması, kaynak örnekleri ve kalite sınırları](transit-research.md), [kontrollü 291/91 deneyleri](transit-validation.md). Tam güncel `stop_times`, tarihli istisnalar ve kurumsal koordinat paketi sonraki doğrulama için gereklidir.

## 5. Sağlık hizmeti, kapasite ve maliyet

İl düzeyindeki 2024 yatak, hekim, başvuru ve yatış tabloları artık modele alındı. Kaynakların tam değeri, sayfaları, kapsam farkları ve varsayımlar [kapasite araştırmasında](capacity-research.md). 2024 tebliği ve MLP işletme kalemleri ortak yaklaşık Aralık 2024 fiyat düzeyinde kullanılıyor; gerçek hastane örnekleriyle büyük ölçek seçenekleri, bağımsız kadro ve gider duyarlılığı eklendi. Kamu hastanesine aktarılan proxy tutarları varsayım olarak ayrı tutuluyor.

OSM'deki 124 hastane kaydı resmî envanter değildir. Sağlık Bakanlığı yıllığı 2024 için 85 tesis verir; tarih/kapsam eşitlenmeden sayı karşılaştırılmaz. OSM katmanı yalnız kapasitesiz coğrafi erişim karşılaştırmasıdır.

## 6. Model seçimi

Kapasiteli yer seçimi kullanılır: il/ilçe talep hedefleri altında düşük yıllık eşdeğer maliyet (yıllıklaştırılmış bina yatırımı + işletme); ardından belirlenmiş ek bütçeyle sabit toplam talep için daha kısa yol. [Matematiksel yöntem](methodology.md), nüfus eşdeğeri akışlarını ve iki kapasite kısıtını açıklar. Güncel ana uygulama, [literatürden yararlanan sabit politika](planning-standards.md) ile [tek kalıcı yerleşimi](permanent-plan.md) gösterir; kullanıcı süre, saat veya talep payı seçmez. Süre ve kapsam eşikleri resmî veya klinik standart değildir; [WHO AccessMod](https://www.who.int/tools/accessmod-geographic-access-to-health-care) kapsam yönteminin desteklenmesi bu projenin sayısal hedeflerini doğrulamaz.

## 8. Öncelikli sonraki veri işleri

1. Geçerlilik tarihli resmî GTFS: ara durak varışlarını, özel seferleri, koordinatları ve hizmet istisnalarını doğrulamak için kritik eksik.
2. Resmî mahalle poligonları ve yerleşim kodları: yanlış ad/merkez eşleşmesini azaltır.
3. Mahalle içi nüfus ızgarası ve yaş/ihtiyaç ağırlığı: mahalleyi tek nokta sayma yanlılığını azaltır.
4. Branş bazında kadro/zaman etüdü, yerel hasta akışı, gerçek tip proje alanı ve işletme maliyeti: şablon kapasite varsayımlarını kalibre eder.
5. Tam yönlendirme motoru ve ölçülmüş sürelerle kalibrasyon: dönüşler, trafik, erişim bariyerleri.
6. Daha yoğun aday üretimi ve aday yoğunluğu duyarlılığı: ayrık aday çözümünün coğrafi örnekleme etkisi.

Kaynakların bulunma/kullanılma durumları ayrıca [sources.json](sources.json) içinde tutulur. Bir kaynağın katalogda bulunması, o kaynağın verilerinin modele aktarılmış olduğu anlamına gelmez.
