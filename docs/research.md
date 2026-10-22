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

İlk sürümün süreleri ölçülmüş trafik süreleri değildir. Dönüş yasakları, koşullu erişim, trafik ışıkları, yokuş, hava ve saatlik yoğunluk yoktur. Arayüzdeki trafik çarpanı yalnız duyarlılık senaryosudur. Sonraki aşamada OSM dönüş ilişkilerini işleyen özel [OSRM](https://project-osrm.org/docs/v26.6.1/http) veya Valhalla hizmeti ve doğrulanmış hız profilleri kullanılmalıdır. Büyük matrisler ücretsiz demo sunucularına gönderilmez.

## 4. EGO ve raylı sistem: doğrulanan ile eksik olan

[EGO hareket saatleri](https://www.ego.gov.tr/hareketsaatleri) sayfası incelendi. Hat 110 için yapılan örnek sorgu gerçek durak sıralarını, durak numaralarını ve çıkış saatlerini veriyor; bu örnek bütün durakların varış saatleri, koordinatları ve hizmet takvimleriyle bir GTFS paketi sağlamıyor. [EGO raylı sistem](https://www.ego.gov.tr/sayfa/1075/rayli-sistem) ve [EGO Cep’te](https://www.ankara.bel.tr/mobil-uygulamalar/ego-cepte) resmî kapsam doğrulama kaynakları olarak kaydedildi.

Bu araştırmada **güncel Ankara GTFS indirme adresi, feed geçerlilik dönemi ve yeniden kullanım koşulları doğrulanamadı**. Bu, kurumda veri bulunmadığı anlamına gelmez. Resmî web sayfalarındaki sefer bilgilerinin bu uygulamaya entegre edildiği iddia edilmiyor.

Çalışan ilk EGO modu için OSM’deki sayısal otobüs hatları, metro ve hafif raylı sistem ilişkileri kullanıldı. Sıralı duraklar, gerçek üye yol/ray geometrileri ve ağ üzerinden yürüme bağlantılarıyla **337 yönlü hat kaydı / 5.984 durak** işlendi. Hat kaydı sayısı benzersiz resmî EGO hattı sayısı değildir; gidiş/dönüş ve varyantlar ayrı olabilir. Tüm hatların çalıştığı, otobüs için 8, raylı sistem için 4 dakika bekleme olduğu varsayılır. Hat işletmecisi ve güncel çalışma durumu resmî envanterle topluca doğrulanmış değildir.

Gerekli veri paketi: [GTFS Schedule](https://gtfs.org/documentation/schedule/reference/) standardında `agency`, `stops`, `routes`, `trips`, `stop_times`, `calendar` veya `calendar_dates`, gerektiğinde `frequencies`, `transfers`, `shapes`. Gerekli açıklamalar: saat dilimi, geçerlilik tarihleri, EGO/ÖHO/ÖTA kapsamı, metro/ANKARAY kapsamı, yürüme bağlantıları, aktarma kuralları, durak erişilebilirliği ve lisans. GTFS-RT, canlı tahminler için sonraki ek katmandır; statik tarifenin yerine geçmez.

GTFS elde edilince [OpenTripPlanner](https://www.opentripplanner.org/) ile hafta içi/hafta sonu, sabah yoğun/sakin saat gibi çoklu hareket zamanlarında süre matrisleri üretilmeli. Örnek hareket saatlerinin ortalaması yanında kötü durum yüzdelikleri de karşılaştırılmalıdır.

## 5. Mevcut hastaneler ve kapasite

[Ankara İl Sağlık Müdürlüğü sağlık tesisleri](https://ankaraism.saglik.gov.tr/TR%2C80707/saglik-tesislerimiz.html) resmî envanter doğrulaması için öncelikli kaynaktır. [Sağlık İstatistikleri Yıllığı 2024](https://www.saglik.gov.tr/TR-114952/saglik-istatistikleri-yilligi-2024.html) il düzeyindeki tesis, yatak ve personel göstergeleri için birincil yayın olarak bulundu; bu ilk modele kapasite tablosu aktarılmadı.

Haritada 124 adlandırılmış OSM hastane kaydı vardır. Bunlar resmî sayı, eksiksiz tesis listesi veya aynı hizmeti veren eşdeğer hastaneler değildir. Ad normalizasyonuyla yinelenen adlar azaltılmıştır; farklı adla çizilen aynı kampüs veya aynı adlı ayrı tesis hataları mümkündür. Karşılaştırma **aynı seyahat süresi modelindeki coğrafi erişim** içindir; yeni ağın gerçek kapasiteyi karşıladığını veya daha ucuz olduğunu kanıtlamaz.

Sonraki veri gereksinimi: tesis koordinatı, acil/genel/branş türü, kamu/özel kapsamı, aktiflik tarihi, yatak, uzmanlık, hekim ve yıllık hizmet kapasitesi. Kişilerin hastane ihtiyacı ile tesisin hizmet arzı eşleştirilmelidir.

## 6. Yapım ve işletme maliyeti

[ÇŞİDB Yüksek Fen Kurulu tebliğ kataloğu](https://yfk.csb.gov.tr/tebligler-iscilikler-329), yapı yaklaşık birim maliyetleri için birincil kaynaktır. [3 Şubat 2026 tarihli ilgili Resmî Gazete bağlantısı](https://www.resmigazete.gov.tr/eskiler/2026/02/20260203-4.htm) bulundu; bu oturumda birincil sunucudan tam metin başarıyla alınamadığı için TL/m² rakamı modele taşınmadı.

Bir hastanenin yatırım bedelini yalnız haritadaki konumdan çıkarmak mümkün değildir. Tip, yatak/kapasite, toplam inşaat alanı, tıbbi donanım ve altyapı kapsamı gereklidir. İşletme/personel maliyetleri ayrıca değerlendirilir. Bu sürümde tüm tesisler aynı **1 maliyet birimine** sahiptir; minimum tesis sayısı yalnız eşdeğer tesis varsayımı altında minimum model maliyetidir.

Gerçek maliyet sürümü için sabit yatırım + kapasiteye bağlı maliyet + yıllık işletme maliyetinin bugünkü değeri tanımlanmalıdır. Birim maliyet kaynağının kapsamı ve fiyat yılı açık tutulmalıdır. Kullanıcı talebi gereği mevcut yapı/yıkım/arsa edinimi kısıtları yer seçimini engellemez.

## 7. Seçilen yöntem ve alternatifler

[WHO AccessMod](https://www.who.int/tools/accessmod-geographic-access-to-health-care), belirli seyahat süresinde erişilebilen nüfusun incelenmesini destekler. [Church & ReVelle (1974)](https://doi.org/10.1111/j.1435-5597.1974.tb00902.x) sabit tesis sayısı altında kapsama yaklaşımının temel kaynaklarındandır. Bu uygulama bununla ilişkili **kısmi küme kapsama** problemini çözer: hedef erişimi sağlayan en az eşdeğer tesis, ek olarak ilçe bazında taban erişim.

| Yöntem                                          | Güçlü yanı                                     | Bu proje için tek başına eksik yanı                                          |
| ----------------------------------------------- | ---------------------------------------------- | ---------------------------------------------------------------------------- |
| p-median: sabit sayıyla ortalama süreyi azaltma | Ortalama yolculuğu iyi temsil eder             | Tesis sayısını önceden ister; küçük uzak nüfusu geride bırakabilir           |
| Maksimum kapsama: sabit bütçe/tesis sayısı      | Bütçeyle kaç kişiye erişileceği açıktır        | Gerekli minimum tesis sayısını doğrudan seçmez                               |
| Tam küme kapsama: herkese eşik içinde erişim    | Uç bölgeleri de zorunlu kapsar                 | Veri açığı varken olanaksız; çok küçük uzak talepler maliyeti belirleyebilir |
| **Hedefli kısmi kapsama + ilçe tabanı**         | Maliyet, erişim ve coğrafi denge açıklanabilir | Eşik ve hedefler politika tercihidir; kapasite ayrıca gerekir                |

Bu aşamada “tek doğru 30 dakika” veya “bilimsel olarak zorunlu %95” iddiası yoktur. Eşik, hedef ve ilçe tabanı senaryo kontrolleridir. Sonraki karar çalışmasında bu parametrelerin duyarlılığı, kapasite ve belirsizlikle birlikte değerlendirilmelidir.

## 8. Öncelikli sonraki veri işleri

1. Resmî GTFS ve yeniden kullanım izni: tarifeli EGO hesaplaması için kritik eksik.
2. Resmî mahalle poligonları ve yerleşim kodları: yanlış ad/merkez eşleşmesini azaltır.
3. Mahalle içi nüfus ızgarası ve yaş/ihtiyaç ağırlığı: mahalleyi tek nokta sayma yanlılığını azaltır.
4. Standart tesis türü, hizmet kapasitesi ve maliyet: hastane sayısını hizmet kapasitesiyle bağlar.
5. Tam yönlendirme motoru ve ölçülmüş sürelerle kalibrasyon: dönüşler, trafik, erişim bariyerleri.
6. Daha yoğun aday üretimi ve aday yoğunluğu duyarlılığı: ayrık aday çözümünün coğrafi örnekleme etkisi.

Kaynakların bulunma/kullanılma durumları ayrıca [sources.json](sources.json) içinde tutulur. Bir kaynağın katalogda bulunması, o kaynağın verilerinin modele aktarılmış olduğu anlamına gelmez.
