# EGO tarifesi araştırması ve zaman bağımlı model

Araştırma güncellemesi: 23 Ekim 2026 TSİ. HTTP gözlem zamanı aşağıda ayrıca belirtilir; belge tarihi bütün kaynakların yeni indirildiği anlamına gelmez. İncelenen EGO deneyi il %95, her ilçe %80, 45 dakika ve en fazla 91 hastane hedeflerini kullanır. 291 tarihsel modelin sonucudur; ulaşım verisi ve varsayımları bağımsız denetimlerle yeniden sınanır.

## Birincil kaynakta ne bulundu?

[EGO Hareket Saatleri](https://www.ego.gov.tr/hareketsaatleri) kesiti **665 hat/yön/varyant** ve **10.811 ayrı durak kimliği** içerir. Bu, 665 benzersiz fiziksel hat veya bütün hizmetlerin modele bağlandığı anlamına gelmez. Her kayıt üç gün türünün kalkış saatlerini, açıklamaları, durak sırasını, mesafeyi ve sayfada `Süresi` olarak adlandırılan alanı içerir. Ham HTML katalog kimlikleri ve durak sıraları işlenmiş kayıtlarla bağımsız olarak eşleştirildi.

Kaynak örnekleri:

- [110](https://www.ego.gov.tr/hareketsaatleri?hat_no=110): üç gün türünde 22.40 kalkışı; süre alanı 48 dakika. Bu hattı gündüz sürekli çalışıyor saymak yanlıştır.
- [111](https://www.ego.gov.tr/hareketsaatleri?hat_no=111): 45 dakika hat süresi; bazı seferler 10654 numaralı ara duraktan başlar, bazıları farklı yere uğrar.
- [548](https://www.ego.gov.tr/hareketsaatleri?hat_no=548): notlar Beypazarı/Sincan başlangıçlarını ayırır. Bir not içinde saatin tekrar yazılması iki ayrı sefer olarak sayılmaz. Başlangıcı kesin eşleştirilemeyen kayıtlar ilk duraktan kalkıyormuş gibi eklenmez.
- [M1-D](https://www.ego.gov.tr/hareketsaatleri?hat_no=M1-D), [M1-G](https://www.ego.gov.tr/hareketsaatleri?hat_no=M1-G): Koru–Törekent arasında yayımlanan yönlü kalkışlar ve 59/60 dakika süre alanları. Modelde Kızılay’da yapay M1/M2 aktarması yaratılmaz.
- [M4-D](https://www.ego.gov.tr/hareketsaatleri?hat_no=M4-D), [M4-G](https://www.ego.gov.tr/hareketsaatleri?hat_no=M4-G): Kızılay uzatması dahil resmî durak listesi.
- [A1-D](https://www.ego.gov.tr/hareketsaatleri?hat_no=A1-D), [A1-G](https://www.ego.gov.tr/hareketsaatleri?hat_no=A1-G): ANKARAY’ın ayrı gün türlerine ait kalkış listeleri.

Tarife sayfaları **ara durakların bütün varış saatlerini** ve belirli tarihli bir `calendar_dates` tablosunu sağlamıyor. Başkentkart’ın tekil durak sorgusu aşağıda ayrı bir koordinat kaynağı olarak kullanılır; bu, bütün GTFS bileşenlerinin elde edildiği anlamına gelmez. Ham 665 HTML’nin başlık sırası hafta içi/cumartesi/pazar olarak doğrulandı; kaybolan saat/not satırı bulunmadı. Sayfalardaki bayram açıklaması tarihli bir hizmet takvimine dönüştürülmedi. Dört model profili normal gün türünü temsil eder; resmî tatil, kesinti veya canlı gecikme garantisi değildir.

`fetch_ego.py` sıralı, hız sınırlı isteklerle yanıtları saklar; her dosyanın URL, boyut ve SHA-256 kimliği `ego-official.json` içindedir. **666 eski HTML kaydının HTTP gözlem zamanı bilinmiyor.** 23 Ekim’deki yeniden işlemede bu zamanlar `observedAt: null`, `retrievedAt: null` ve `unknown_legacy_cache` olarak korundu. Yeni `processedAt` gözlem tarihi yapılmadı. Önbellekten tekrar işleme kaynak dosyalarının içeriğe dayalı kimliğini korur; `--refresh` yeni HTTP gözlemi alır ve onu yanıt SHA’sına bağlı sidecar kaydına yazar.

## Durak koordinatları ve GTFS değerlendirmesi

Birincil koordinat kaynağı [EGO Başkentkart haritası](https://baskentkart.ego.gov.tr/). Kamusal [map_init.js](https://baskentkart.ego.gov.tr/map_init.js), `bayiToDo.asp` adresindeki `POST fnc=DurakSorgula, durakNum=<kimlik>` işlemini gösterir. Kimlik doğrulama, canlı araç verisi veya kişisel bilgi kullanılmaz. Yanıt veri olarak ayrıştırılır; sunucudan gelen metin çalıştırılmaz. Windows-1254 yanıtlar Türkçe adres metnini koruyacak şekilde çözülür.

**10.743 sayısal katalog kimliğinin tamamı** yanıt verdi; boş yanıt, `notFound` veya hata yok. Her kaydın kimliği, koordinatı, adresi ve SHA’sı ham yanıtıyla eşleşir. Bunların **10.740** tanesinde HTTP gözlem zamanı SHA+durak kimliği+endpoint sidecar kaydıyla bağlıdır. Bilinen gözlemler **22 Ekim 23.02–23 Ekim 00.24 TSİ** aralığındadır. `11535`, `14162`, `14163` eski önbellek olduğundan zamanı bilinmez ve null tutulur. `processedAt` bunlara yeni erişim zamanı olarak atanmaz. Katalogdaki **68 sayısal olmayan kimlik** bu sayısal sorgu kesitine dahil değildir.

Öncelik resmî Başkentkart sorgusu → OSM `ref` eşleşmesi → eksik otobüs kimliğinde tarihsel topluluk koordinatıdır. Raylı sistemin sayısal olmayan kimliklerinde resmî durak adı OSM istasyonuyla eşleştirilir; geometri ilgili EGO hattının raylarından bulunur. Aynı istasyondaki farklı ray hatları araç hareketi olarak birleştirilmez. Resmî sorgunun gözlem zamanı, koordinat ile önbellek tarifesinin aynı hizmet tarihinde geçerli olduğunu garanti etmez.

[Transitous Türkiye kaynak kataloğu](https://raw.githubusercontent.com/public-transport/transitous/main/feeds/tr.json), Ankara için bir [topluluk GTFS arşivi](https://dl.dropboxusercontent.com/scl/fi/d7u3d00gd85w2qbzedze6/ankara.zip?rlkey=4x8oz2sby5vvqgf1iuaeit70l) gösteriyor. İndirilen 21.990.864 baytlık dosyanın SHA-256 kimliği `c070ea3486a6390d1e67c1ed78cca935e287187dbd6edd89f0608605bbf59419`.

Bu paket **güncel resmî GTFS kabul edilmedi**: `feed_info` yok; takvim 08.08.2023–31.12.2030 aralığını gösteriyor; `H` hizmet kodu hafta sonlarını da işaretliyor; bazı komşu duraklarda aynı koordinatlar ve düzenli birer dakikalık ara durak zamanları var. Örneğin tarihsel A4/A6 koordinatları aynı; OSM kesitinde ayrı istasyonlar. Bu yüzden paketin **seferleri, takvimi, şekilleri ve ara durak saatleri kullanılmıyor**. Yalnız birincil sorgu ve OSM eşleşmesinde bulunmayan, resmî katalogda hâlâ geçen otobüs durak kimlikleri için ek koordinat kaynağıdır; kullanılırsa tarihsel/topluluk etiketi taşır. Fiilî kaynak dağılımı kalite raporundadır. Ham ZIP repoya yeniden dağıtılmaz.

Daha önce `ankarakart.ego.gov.tr` adresindeki denemede boş HTTP 200 yanıtı alınmıştı. Başkentkart adresindeki başarılı sorgu bu eski denemeden ayrıdır. Boş yanıt durak yokluğu sayılmaz; `emptyUnavailable` olarak tutulur ve `--retry-unavailable` ile yeniden denenebilir. `--refresh` bütün seçili duraklarda yeni gözlem ister. Dosya değiştirme zamanı gözlem zamanı olarak kullanılmaz.

Eksik koordinatlar, kaynaklar arası 300 m üzeri farklar, kullanılamayan hatlar, çözülemeyen özel sefer notları ve süre tutarsızlıkları [ego-quality.json](../data/processed/ego-quality.json) içinde tek tek tutulur. Kullanılan/yayımlanan sefer sayıları ayrı verilir. Eksikler hizmet yokluğunun kanıtı değildir.

23 Ekim’de üretilen ağın kaynak kapsamı aşağıdadır. Aynı ağ, kod ve dört profil matrisini bağlayan güncel kimlik [ulaşım paketi kaydındadır](../data/processed/transit-package.json).

| Gösterge | Yeni ağ kaydı |
|---|---:|
| Kullanılan hat/yön/varyant | 430 / 665 |
| Sefer örüntüsü | 545 |
| Koordinatı olan katalog kimliği | 10.811 / 10.811 |
| Resmî sorgu / OSM istasyon eşleşmesi | 10.743 / 68 |
| Tarihsel topluluk kaynağından kullanılan koordinat | 0 |
| Hafta içi kullanılan / yayımlanan kalkış | 10.449 / 14.414 (%72,49) |
| Cumartesi kullanılan / yayımlanan kalkış | 8.153 / 10.805 (%75,46) |
| Pazar kullanılan / yayımlanan kalkış | 7.144 / 9.479 (%75,37) |

Bu sefer oranları nüfus kapsamı veya bütün gerçek hizmetin tamlığı değildir. 235 dışlanan varyantın 200’ünde yalnız çözülemeyen özel notlar, 12’sinde eksik yol/ray segmenti veya süre, 20’sinde yayımlanmış kalkış yoktur; `117-2`, `479`, `501-2` mesafe tutarsızlığıyla karantinadadır. Ayrıca 8.180 sefer notu çözümlenemedi, 61 varyantın süresi segment alt sınırları nedeniyle yükseltildi. Adres/ilçe kontrolünde 98 uyarı ve kaynak çiftleri arasında 397 mesafe farkı kaydı vardır; bunlar yanlış koordinatı kanıtlayan saha bulguları değildir. Bu kesitte tarihsel ek koordinat kullanılmadığından onun adres çelişkisine bağlı karantina sayısı sıfırdır. Tam koordinat kapsamına rağmen eksik sefer anlamı ve geometri, sonuçları sınırlamaya devam eder. Dar kanıt kümesindeki **49 kaydın tamamı dört örüntüye** uygulanmıştır. Önceki v0.6’ya göre kullanılabilen varyantlara **147 ve 527-1** eklenmiş; önceki kullanılan varyantlardan hiçbiri kaybolmamıştır. 527-1’in 25 incelenmiş kalkışına ek olarak 147’de hafta içi 14.00, cumartesi/pazar 09.30 ve 18.15 olmak üzere beş mevcut kalkış, yol geometrisi düzeldiği için genel not kurallarıyla kullanılabilir olmuştur; bunlar yeni bir süre yorumu değildir. 140, 146, 147-1, 147-2 ve 158-5’in geometrisi de artık bulunur, ancak özel notları hâlâ çözülemez. Bu yeni incelenebilir kayıtlarla çözülemeyen not sayısı net 20 artmıştır; sadece kullanılan sefer sayısından veri tamlığı sonucu çıkarılamaz. 527-2/3 ve 610 için belirsiz başlangıç notları devam eder.

Eski üç uzak-durak projeksiyonuna ek olarak 216 durak resmî sıra/yol yönü kanıtıyla bağlanmış, 477 aday komşu belirsizliği nedeniyle bekletilmiştir. Toplam 219 projeksiyon vardır; iki uzak durak yol kenarına da 300 m’den uzak olduğundan hâlâ bağlanmamıştır. Kısmi yön düzeltmesi 615 ve 560-8’de incelenen bütün sorunları çözmemiştir.

Kaynak tutarlılığı için ayrıca şu kontroller uygulanır:

- Resmî adresteki ilçe sınırının 3 km dışındaki tarihsel ek koordinat karantinaya alınır; birincil/OSM koordinatında aynı çelişki inceleme uyarısıdır. Her çelişki yanlış kaynağın hangisi olduğunu belirlemez; durak tahminle başka yere taşınmaz.
- Komşu duraklar arasındaki düz mesafe zinciri, yayımlanan mesafenin `max(1,5 × mesafe, mesafe + 2 km)` sınırını; modellenmiş yol/ray zinciri `max(2 × mesafe, mesafe + 2 km)` sınırını aşarsa hat karantinaya alınır. Yayımlanmış mesafe yoksa bu kontrol yapılamadığı açıkça kaydedilir.
- Bu geniş toleranslar saha doğrulaması değildir. Bağlantısı bulunamayan araç segmenti kuş uçuşu çizgiyle tamamlanmaz; bütün sayısal durakların yanıt vermesi bütün seferlerin modele bağlandığı anlamına gelmez.

## Özel sefer notlarının kapsamı

Not çözümü Türkçenin bütün gramerini yorumlayan bir sistem değildir; desteklenen başlangıç/bitiş örüntülerini muhafazakâr biçimde eşleştirir. Farklı veya çoklu saatler, çözülemeyen dönüş/servis dışı ifadeleri, belirsiz uçlar ve takvim koşulları genel hizmete çevrilmez. Sütun saatiyle aynı saati içeren yalnız-bitiş notu da saatin rolü belirsiz olduğu için dışlanır. `SADECE`, gün/tarih/tatil koşulları gibi ifadeler ayrılır; `OKULUNDAN`, `PAZAR YERİ` veya `19 MAYIS CD.` gibi durak adları tek başına takvim koşulu sayılmaz.

Örneğin 275 hattındaki `06:35 METRODAN BAŞLAR–07:02 21256 NUMARALI DURAK` notu 21256’da 06.35 kalkışı üretemez. 256’daki servis dışı dönüş ve 312’deki ayrı bitiş cümlesi de ana güzergâhın tamamında yolcu taşıma varsayımına dönüştürülmez. Dışlanan kayıtta `resolutionReason`, `columnSeconds` ve `noteClockSeconds` tutulur. Yeni kaynak ifadeleri ayrıca incelenmelidir; çözülemeyen hizmetin erişimi düşürme etkisi sonuç kapsamının bir parçasıdır.

Genel not çözümünün dışında, **49 tam saat/gün/not kaydı için dar bir kanıt kümesi** hazırlanmıştır. [560-8’in resmî sayfasındaki](https://www.ego.gov.tr/hareketsaatleri?hat_no=560-8) tam 1–55 yönü ve 75 dakika alanı, 8 hafta içi + 6 cumartesi + 6 pazar Sincan kalkışına bağlıdır. [615’in tarihli hareket–kapanış planı](https://www.ego.gov.tr/tr/duyuru/7621/615-gudululus-ve-6151-gudulceltikci-hattinin-servis-saatleri-duzenlenmistir) ise yalnız dört hafta içi Ulus → Güdül kalkışına 95/120 dakika tahmini bütçe verir. **2025 planının Ekim 2026 kapanış geçerliliği doğrulanmamıştır.** Dört kalkışın gözlenen tarifeyle eşleşmesi, eski kapanışları güncel ölçüm yapmaz. 615 dönüşü, hafta sonu, cuma ilavesi ve diğer belirsiz kırsal kayıtlar bu yorumla eklenmez.

[527-1’in hareket sayfası](https://www.ego.gov.tr/hareketsaatleri?hat_no=527-1) ve [erişilebilir tablosu](https://www.ego.gov.tr/engelli/duyurudetay/7721), ayrı Kızılcahamam → Ankara yönündeki 98 durak boyunca 11 hafta içi + 8 cumartesi + 6 pazar kalkışını bağlar. Tam yönün yayımlanmış 85 dakikalık alanı tahmini bütçedir; mevcut ağın fiziksel alt sınırı nedeniyle modelde 108,49 dakika kullanılır. Duyuru gövdesindeki 26 Aralık 2025 değişikliği diğer yönü anlatır; eklenmiş saat tablosunun geçerlilik tarihi bilinmez. 527-2’nin `RÜZGARLI` başlangıcının ilk durakla kesin bağı kurulamadığından 25 dönüş kaydı bekletilir.

Bu kurallar bütün terminal adlarını çözme iddiası taşımaz. Dokuz gerçek HTML arşivi, gözlem zamanları, gün/saat/yön ayrımları ve açık kalan 560-4, 158, 178, 490, 677 hizmetleri [dar sefer kanıtı belgesinde](service-evidence.md) açıklanır. Kaynak baytı, sıralı durak kimliği veya tam sefer kaydı değişirse ilgili yorum yeniden incelemeye kadar uygulanmaz.

## Süre nasıl hesaplanıyor?

1. Yolculuk bir normal gün türünde 08.00 veya 10.00’da mahalle temsil noktasından başlar. Her profil ayrı matristir; farklı saatlerin en iyi parçaları birleştirilmez.
2. Durak erişimi OSM yürüme ağından hesaplanır. Durağa varışa 60 saniye biniş hazırlığı eklenir; bundan önce geçmiş sefer kullanılamaz. Sabit 8/4 dakika bekleme kaldırılmıştır.
3. Otobüs için yönlü OSM yolları, `bus`/`psv` izinleri ve otobüse özel tek yön etiketleri kullanılır. Eski çıkış düğümüne 300 m’den uzak, mevcut yol kenarına 300 m içinde olan durak o kenara izdüşürülebilir; kenarın yönü ve toplam maliyeti korunur. Ayrı şeritler/kenarlar birleştirilmez, eşit yakınlıktaki belirsiz kenarlar dışarıda kalır. Üç uzak durak bu biçimde bağlıdır. Ayrı yön/sıra politikası en çok 15 m kenar uzaklığı, en az 10 m düğüm mesafesi iyileşmesi ve resmî ileri sıra tanığıyla 216 ek bağlantı yapar; 477 seçimi komşu belirsizliği nedeniyle global olarak bekletir. Yeni yön eşleştirmesine değen her parçanın iki ucu da kayıtlı düğüme sabittir. 438 etkilenen çiftin 437’si kabul edilir, biri geometri sınırında belirsiz kalır; başka düğüme retry yoktur. Bu yeni kapsamın dışındaki eski çiftler mevcut retry davranışını korur; projekte edilmiş uç kendi kenarını terk edemez. Bu işlem yürüme veya araba ağına yeni bağlantı eklemez. Dönüş yasakları ve anlık trafik hâlâ yoktur. Duraklar arasındaki yol, resmî bir araç GPS izi değil, modellenmiş OSM güzergâhıdır.
4. Metro için A, M1–M2–M3 ve M4 ray ağları ayrı tutulur. Aynı hattın paralel raylarından bağlı bir bileşen kullanılır; hizmet yönü resmî durak sırasıdır. Koru–Törekent tek araçta devam edebilir; farklı hatlara geçiş yürüyüş ve yeniden biniştir.
5. Her segmentin süre alt sınırı `max(yol/ray uzunluğu, duraklar arası düz mesafe) / azami hız + 10 saniye` olur; hız otobüste 90, raylı sistemde 80 km/saattir. Duraklar aynı yol düğümüne bağlansa bile farklı koordinatların fiziksel alt sınırı korunur. EGO süre alanının bu minimumlar toplamından kalan negatif olmayan kısmı ağ süresi + 25 saniye ağırlıklarıyla dağıtılır. Minimumlar toplamı daha uzunsa süre yükseltilip raporlanır. Bütün hat süresini tek katsayıyla ölçekleyip bazı segmentlerde alt sınırı kaybetme hatası giderilmiştir. Bu hız ve duruş değerleri ölçüm değil, model varsayımıdır; düz mesafe araç güzergâhı yerine kullanılmaz.
6. İlk/son yürüyüş en çok 15, her aktarma yürüyüşü en çok 5 dakika; en fazla üç biniş/iki aktarma. Aktarma yürüyüşleri art arda zincirlenerek sınırsız yürüme üretemez. Doğrudan yürüyüş seçilen toplam süre eşiğine kadar mümkündür. Eski modeldeki doğrudan yürüyüş için 15 dakika kesmesi hatalıydı.
7. Aynı yönlendirme kuralları matris üretimini ve arayüzdeki rota açıklamasını besler. Tek-yolculuk/toplu hesap eşleşmesi, kaçırılan sefer, aktarma sınırı ve kesin biniş zamanı sınanır. Üretilmiş veride her segmentin fiziksel alt sınırı süre dağıtım fonksiyonu çağrılmadan yeniden denetlenir. Bunlar iç tutarlılık kontrolleridir; ölçülmüş saha yolculuğuyla karşılaştırma yerine geçmez. Rotada hat, biniş saati ve bekleme gösterilir; ara durak saati tahmindir.

**Süre alanının yön/çevrim kapsamı her hatta doğrulanamadı.** Bazı durak listeleri gidiş ve dönüş yönlerini içerir; HTML alanı yalnız `Süresi` der. Genel model bu alanı bilinen durak zincirine dağıtır. Yukarıdaki 49 dar kayıt, kendi yön bütçesini kendi durak aralığında yeniden dağıtır; özellikle 615’in 1–86 gidiş süresi tam gidiş–dönüş zamanlarından kesilmez. Bütün hatların tek yön veya tam çevrim süresi olduğu varsayılmaz ve otomatik 2× düzeltme yapılmaz. Fiziksel hız sınırları terminal beklemesini veya aynı araçla dönüş yönüne devam iznini kanıtlamaz. Kurumsal `stop_times` veya hat bazında doğrulanmış yön süreleri gerekir.

Yol kenarı izdüşümleri ayrıca üreticinin bölme fonksiyonundan bağımsız denetlenir. Stop/rapor kimliği, özgün uçlar, kenar oranı, ilgili uzak-durak veya yön/sıra mesafe koşulları ve eklenen noktaya komşu geometri parçalarının yönü sınanır. Altı ondalıklı geometride 0,20 m, tam hassasiyetli kayıtta 0,01 m tolerans kullanılır. Ham OSM varsa gerçek ardışık kenar ve izinli yön de karşılaştırılır; yoksa kaynak denetimi yapılmış sayılmaz. `audit_bus_stop_matching.py` ayrıca takip edilen resmî sıraları, tanıkları ve bütün kilitli çiftleri kontrol eder; ham OSM varsa 693 ilk adaydan 216 seçime giden yol/alternatif/kat ve komşu kararlarını ayrı uygulamayla tekrar kurar. Paket kontrolleri ham kaynak olmayan CI’da da çalışır; ham kaynak kontrolünün yapılmaması ayrı raporlanır. [Yön eşleştirme kapsamı](bus-stop-matching.md) bu denetimlerin sınırlarını açıklar. Bu kontroller bütün yol ağı veya gerçek biniş yerinin saha doğrulaması değildir.

## Kaynak kesitinden sonuç paketine

`transit-package.json`, kaynaklar, dar sefer kuralları ve dokuz gerçek kanıt arşivi, ağ/geometri, dört yürüme CSR dosyası, dört profil matrisi, ulaşım kodu ve sıralı talep/aday/hastane/ilçe kimliklerini birlikte bağlar. Paket ancak bütün matrisler tamamlanınca yazılır. Dosyanın kendi `builtAt` zamanı dışında bağlı artifact baytları kimliğe dahildir; kaynakları yeniden işlemek bile paket kimliğini değiştirebilir. Kod satır sonları platformlar arasında normalleştirilir. Önbellek girdi anahtarının yanında gerçek çıktı dosyalarının SHA’sı da kontrol edilir; eski bir işaret dosyası başka sürümün çıktısını geçerli kılamaz.

Yeni ulaşım paketinden sonra bütün kayıtlı çözüm örnekleri yeniden hesaplanır; raporu yazmak tek başına yeterli değildir. Ardından sabit plan testi ve en son manifesto üretilir. Paket uyuşmazlığı arayüzde eski sayıları gizler. Adımlar ve salt okunur denetimler [veri yeniden üretim belgesindedir](../data/README.md).

## 291 ve 91 testi

291 önceki tarifesiz ağın coğrafi alt sınırıydı; güncel EGO ihtiyacı veya minimum hastane sayısı değildi. [Deney raporu](transit-validation.md), nüfus/aday kimlikleri korunarak eski matrisi, yalnız doğrudan yürüyüşü düzeltilmiş matrisi ve dört tarifeli profili karşılaştırır. İlk iki adım yürüyüş kesmesinin etkisini ayırır. Yeni profillerde resmî koordinatlar, özel notlar ve geometri/süre kontrolleri de değiştiği için bütün fark yalnız kalkış saatlerine bağlanamaz. Bu coğrafi alt sınır hesaplarında yatak/hekim ve maliyet kısıtları yoktur.

91 testi, mevcut 91 hastanenin gerçek yerlerini ve kadrolarını test etmez; sıfırdan en fazla 91 tesis seçmeye izin verir. Tam aday/bağlantı coğrafi gevşetmesinin alt sınırı 91’i aşarsa **bu veri ve varsayımlar altında** 91 mümkün değildir. Eksik sefer/konumlar ve tahmini ara durak zamanları varken bunu gerçek Ankara için kesin bir imkânsızlık iddiasına dönüştürmek doğru olmaz.

Kapasiteli maliyet/süre optimizasyonunun varsayılan araması her yapı izi sınıfından en yakın 12 aday bağlantısıyla sınırlıdır. Bu problemin maliyet veya süre açıklığı, bütün aday bağlantılarının küresel açıklığı değildir. İlk maliyet planının açıklığı son plan yerine kullanılamaz; arayüz ikisini ayırır. Tesis sayısını en aza indirmek ayrı bir amaç olarak çözülmez.

`robustness-results.json` farklı bir soruyu sınar: kaydedilmiş hafta içi 10.00 planının **aynı konumları, yatakları, hekimleri ve yıllık eşdeğer bütçe tavanı** diğer üç profilde de yeterli mi? Akış yeniden atanabilir; malzeme gideri yeni atanan talebe göre hesaplanır, sabit kaynak gideri korunur. Yıllık talep dört kez toplanmaz. İlçe tabanları kaldırılan tanı bütçeyi korur; ayrı coğrafi sayı tanısı kapasite/maliyet/çakışma koşullarını kaldırır. Belirsiz çözücü sonucu başarısızlık veya başarıya çevrilmez. Dört başlangıç profili bütün gün/yıl hizmet garantisi değildir.

Sonraki kritik doğrulama: EGO’dan birbirine aynı geçerlilik dönemiyle bağlı `stops`, `trips`, `stop_times`, `calendar_dates`, gerçek yön/varyant geometrileri ve seçilmiş yolculuklarda ölçülmüş saatler. Tekil kurumsal koordinat sorgusu bu ihtiyacın yalnız bir bölümünü karşılar. Dolmuş ve Başkentray bu sürümün EGO kapsamına eklenmiş değildir. Mali tutarlar da kısmi gider kalibrasyonudur; gerçek kamu bütçesi veya ihale bedeli değildir.
