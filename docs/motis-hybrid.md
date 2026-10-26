# EGO + Araba: ortak kaynak planı ve yerel MOTIS

Bu sürüm üç ayrı araştırma modu sunar: Araba, EGO ve EGO + Araba. Yeni arayüzde EGO sürelerinin sağlayıcısı yerel **MOTIS 2.10.2** motorudur. Özgün EGO kaynak deneyi ayrıca seçilebilir; önceki 91, dört saat ve 44 yakın başlangıç saati sonuçları o özgün modelin tarihsel kayıtlarıdır. Yeni MOTIS sonucunun doğrulaması olarak sunulmazlar.

## Hibrit ağırlığı ne anlama geliyor?

Başlangıç önceliği **%70 araba, %30 EGO**. Kullanıcının acil erişimde araç tarafına daha yüksek önem verme isteğini temsil eden değiştirilebilir bir planlama tercihidir. Ölçülmüş ambulans kullanım payı veya klinik talep dağılımı değildir. Araba matrisi mevcut kişisel araç yol ağı tahminidir; ambulansın trafik üstünlüğü, ışık geçişi, istasyon sevki, müdahale süresi ve hastane kabul gecikmesi ölçülmez. Ambulans için kanıtsız hız artışı uygulanmaz.

Her ulaşım türü, **aynı hastane konumları, yatakları ve hekimleriyle tam yıllık talebi karşılayabilecek ayrı bir senaryo** olarak çözülür. İki senaryo aynı anda toplanan iki ayrı nüfus değildir. Atamalar ulaşım türüne göre değişebilir. Başlangıçta her birinde il genelinde %95, her ilçede %80 talep tabanı korunur; araç sınırı 30, EGO sınırı 45 dakikadır. İki sürenin ortalaması alınarak uzun EGO yolculuğu kısa araba yolculuğuyla geçerli hale getirilmez.

1. Ortak bina ve kadronun yıllık eşdeğer maliyeti azaltılır.
2. İlk geçerli maliyet planına göre seçilen ek bütçe içinde `0,70 × araba ortalaması + 0,30 × EGO ortalaması` azaltılır. Varsayılan ek yıllık maliyet toleransı %10'dur.
3. Her modun ortalaması, kapsaması ve ilçe sonuçları ayrı gösterilir. Ağırlıklı süre iki ulaşım senaryosunun amaç değeridir; tek bir kişinin araba ve otobüsle yaptığı birleşik yolculuk değildir.

Bir tesiste her senaryonun atanan talebi ayrı ayrı hekim temas kapasitesine ve yatak günü kapasitesine sığmalıdır. Hekimler ve yataklar bağımsız tam sayı kararlarıdır. Kapalı alan ve çakışan yapı izleri de korunur. Bina yatırımı, kadro, yatak işletmesi ve yıllık malzeme talebi **bir kez** faturalanır. Modlar arasındaki tesis yüklerinin maksimumlarını bütün tesislerde toplayıp iki kez malzeme talebi üretme hatası yapılmaz. Talebin coğrafi homojenliği, hekim iş yükü ve maliyet proxy varsayımları [kapasite araştırmasındaki](capacity-research.md) sınırlara tabidir.

## Hangi veri ve motor?

[MOTIS 2.10.2](https://github.com/motis-project/motis/releases/tag/v2.10.2), ücretsiz özgün Ankara topluluk GTFS arşivi ve 20 Ekim 2026 OSM Ankara kesitiyle yerelde çalışır. GTFS SHA256: `c070ea3486a6390d1e67c1ed78cca935e287187dbd6edd89f0608605bbf59419`. Kaynakta 611 hat kaydı, 10.018 durak ve 33.506 sefer bulunur. Bunlar güncel resmî hizmetin eksiksiz envanteri değildir. Kullanıcı eski veriyi araştırma için kabul etmiştir; sürüm açıkça **tarihsel topluluk GTFS senaryosu** olarak adlandırılır.

Saat seçenekleri sabit deney tarihlerine bağlıdır: hafta içi 27 Ekim 2026 08.00/10.00; cumartesi 31 Ekim 10.00; pazar 1 Kasım 10.00, Europe/Istanbul. GTFS takvimini bu tarihlere sorgulamak, tarifelerin 2026'da güncel olduğunu kanıtlamaz. GTFS gün bayrakları düzeltilmiş gibi yapılmaz. İlk bekleme, yürüyüş ve aktarmalar süreye dahildir. Yürüyüş OSM ağına; araç ayaklarının geometrisi GTFS verisine dayanır. Geometri yoksa araç ayağına kuş uçuşu yol üretilmez.

MOTIS ve veri büyük hesaplarda bu bilgisayarda çalışır; ücretli Google API, API anahtarı, ödeme hesabı veya otomatik ücretli yedek sağlayıcı kullanılmaz. Kamusal Transitous sunucusuna toplu yük gönderilmez. [İndirme ve ilk gerçek sorgu kanıtı](free-transit-channels.md).

## Matris ile çizilen rota nasıl tutarlı tutuluyor?

[Sürüme sabitlenmiş OpenAPI tanımı](https://raw.githubusercontent.com/motis-project/motis/refs/tags/v2.10.2/openapi.yaml) kullanılır. Araştırmada deneysel toplu `/api/experimental/one-to-many-intermodal` sonucu, aynı koşullardaki `/api/v6/plan` ile eşdeğer çıkmadı: Kızılay–Etlik 08.05 pilotunda sırasıyla 33 ve 31 dakika; tek binişli seçeneklerde 46 ve 48 dakika gözlendi. Bu gözlem motorun bütününü yanlış ilan etmez; iki uç noktanın birbirinin yerine kanıtsız kullanılmasını engeller.

Toplu sonuç yalnız aday kısa listesinin sıralamasına yardım eder. Tutulan bağlantıların nihai süreleri tekil `/plan` sorgularıyla hesaplanır. Her mahalle ve yapı izi sınıfında toplu sonuçla önerilen adayların yanında karayoluyla yakın adaylar da korunur. Ortak yol girişleri tekrar sorgulanmaz; her hastanenin ayrı giriş bağlantısı sonradan hesaba katılır. Sorgulanan çiftler ve kapsam matrise bağlanır. **Sorgulanmayan çift, hizmet yokluğu değildir.** Daraltılmış grafikte plan bulunamaması tüm adaylar veya Ankara için olanaksızlık kanıtı sayılmaz. Gösterilen çözüm açıklıkları da bu arama kapsamındadır.

Mahalle temsil noktası ile mevcut yol düğümü, aday yol girişi ile hastane merkezi arasındaki bağlantılar varsayımsaldır ve haritada kesikli gösterilir. 75 m/dakika yürüme varsayımı kullanılır. Başlangıç bağlantısı motor sorgu saatini **öne taşır**; kaçırılan seferin beklemesi kaybolmaz. Motorun dakika çözünürlüğünde gerekiyorsa sorgu saati yukarı yuvarlanır ve bu ek bekleme süreye dahil edilir. Son süre, motor varışı eksi kişinin özgün başlangıcı artı son giriş bağlantısıdır. Durakları sıfır maliyetle bağlayan `radius` kullanılmaz.

Rota istenirken tekil motor sonucu kayıtlı matrisle yeniden karşılaştırılır; uyuşmazlık halinde başka kaynağa sessiz geçilmez. Motor kapalıysa bu açık hata olarak gösterilir. Kayıtlı matrisle optimizasyon motor çevrimdışıyken de yapılabilir; yeni yol çizimi motor gerektirir.

## Yerelde yeniden başlatma

Bu bilgisayardaki hazırlanmış kurulumda `npm start`, uygulamayı açarken 8088 portunda motor yoksa mevcut yerel MOTIS kurulumunu da başlatır. Var olan motor örneği yeniden kullanılmaktadır. İndirme veya ücretli çağrı başlatmaz. Uygulama `http://127.0.0.1:8000`, motor `http://127.0.0.1:8088` adresinde yalnız yerel erişime açıktır.

Yeni bilgisayarda motor ikili dosyası ve GTFS yeniden dağıtılmadığı için [resmî kurulum yönergesiyle](https://github.com/motis-project/motis/blob/v2.10.2/README.md) hazırlanmalıdır. Hazırlanmış matris ve kaynak kimlikleri repoda tutulur; ham GTFS, motor ve büyük içe aktarma çıktıları `work/` altında kalır. Motor girişlerinin hashleri, profil tarihleri, sorgu ayarları ve dosya kimlikleri matris manifestinde kaydedilir. Arayüzdeki kaynak durumu eksik profilleri ayrıca bildirir.
