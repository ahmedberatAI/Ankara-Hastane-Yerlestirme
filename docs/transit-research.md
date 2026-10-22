# EGO tarifesi araştırması ve zaman bağımlı model · v0.4

Erişim: 22 Ekim 2026. Amaç 291 sonucunu küçük bir sayıya zorlamak değil, bu sayıyı üreten ulaşım varsayımlarını sınamak. İl %95, her ilçe %80, 45 dakika ve en fazla 91 hastane hedefleri korunur.

## Birincil kaynakta ne bulundu?

[EGO Hareket Saatleri](https://www.ego.gov.tr/hareketsaatleri) kataloğundaki **665 hat/yön/varyant** sorgulandı. Hepsi başarıyla alındı; **10.811 ayrı durak kimliği** bulundu. Bu, 665 benzersiz fiziksel hat veya bütün durakların konumunun doğrulandığı anlamına gelmez. Her kayıt üç gün türünün kalkış saatlerini, açıklamaları, durak sırasını, hat mesafesini ve toplam süreyi içerir.

Kaynak örnekleri:

- [110](https://www.ego.gov.tr/hareketsaatleri?hat_no=110): üç gün türünde 22.40 kalkışı; 48 dakika yayımlanan hat süresi. Bu hattı gündüz sürekli çalışıyor saymak yanlıştır.
- [111](https://www.ego.gov.tr/hareketsaatleri?hat_no=111): 45 dakika hat süresi; bazı seferler 10654 numaralı ara duraktan başlar, bazıları farklı yere uğrar.
- [548](https://www.ego.gov.tr/hareketsaatleri?hat_no=548): notlar Beypazarı/Sincan başlangıçlarını ayırır. Bir not içinde saatin tekrar yazılması iki ayrı sefer olarak sayılmaz. Başlangıcı kesin eşleştirilemeyen kayıtlar ilk duraktan kalkıyormuş gibi eklenmez.
- [M1-D](https://www.ego.gov.tr/hareketsaatleri?hat_no=M1-D), [M1-G](https://www.ego.gov.tr/hareketsaatleri?hat_no=M1-G): Koru–Törekent arasında yayımlanan yönlü kalkışlar ve 59/60 dakika toplam süre. Modelde Kızılay’da yapay M1/M2 aktarması yaratılmaz.
- [M4-D](https://www.ego.gov.tr/hareketsaatleri?hat_no=M4-D), [M4-G](https://www.ego.gov.tr/hareketsaatleri?hat_no=M4-G): Kızılay uzatması dahil resmî durak listesi.
- [A1-D](https://www.ego.gov.tr/hareketsaatleri?hat_no=A1-D), [A1-G](https://www.ego.gov.tr/hareketsaatleri?hat_no=A1-G): ANKARAY’ın ayrı gün türlerine ait kalkış listeleri.

Kaynakta **ara durakların bütün varış saatleri**, belirli tarihli hizmet istisnaları ve güncel toplu koordinat dışa aktarımı yok. `fetch_ego.py` sıralı, hız sınırlı isteklerle HTML yanıtlarını yerelde saklar; her dosyanın URL, boyut ve SHA-256 kimliği `ego-official.json` içinde tutulur. Yeniden çalıştırma önbelleği kullanır; `--refresh` açıkça yeni kesit alır. Normal hafta içi/cumartesi/pazar profilleri resmî tatil, kesinti veya canlı gecikme garantisi değildir.

## Durak koordinatları ve GTFS değerlendirmesi

Öncelik, resmî durak numarası ile güncel OSM `ref` eşleşmesidir. Raylı sistemde resmî durak adı OSM istasyonuyla eşleştirilir; geometri sadece ilgili EGO hattının raylarından bulunur. Aynı istasyondaki farklı ray hatları birbirine araç hareketi olarak bağlanmaz.

[Transitous Türkiye kaynak kataloğu](https://raw.githubusercontent.com/public-transport/transitous/main/feeds/tr.json), Ankara için bir [topluluk GTFS arşivi](https://dl.dropboxusercontent.com/scl/fi/d7u3d00gd85w2qbzedze6/ankara.zip?rlkey=4x8oz2sby5vvqgf1iuaeit70l) gösteriyor. İndirilen 21.990.864 baytlık dosyanın SHA-256 kimliği `c070ea3486a6390d1e67c1ed78cca935e287187dbd6edd89f0608605bbf59419`.

Bu paket **güncel resmî GTFS kabul edilmedi**: `feed_info` yok; takvim 08.08.2023–31.12.2030 aralığını gösteriyor; `H` hizmet kodu hafta sonlarını da işaretliyor; bazı komşu duraklarda aynı koordinatlar ve düzenli birer dakikalık ara durak zamanları var. Örneğin tarihsel A4/A6 koordinatları aynı; güncel OSM’de ayrı istasyonlar. Bu yüzden paketin **seferleri, takvimi, şekilleri ve ara durak saatleri kullanılmıyor**. Yalnız OSM’de bulunmayan, resmî katalogda hâlâ geçen otobüs durak kimliklerinin koordinatları ek kaynak olarak alınır ve açıkça tarihsel/topluluk kaynağı diye işaretlenir. Ham ZIP repoya yeniden dağıtılmaz.

[EGO’nun kart haritası](https://ankarakart.ego.gov.tr/) ve sayfanın `map_init.js` içinde kullandığı `DurakSorgula` işlemi de incelendi; 12908 için gözlenen yanıt HTTP 200/boş içerikti. Bu, kurumda konum verisi yok demek değildir; bu erişimden koordinat elde edilemedi. Kimlik doğrulama veya erişim kontrolü aşılmadı. Resmî tüm durak konum paketi hâlâ gereklidir.

Eksik koordinatlar, kaynaklar arası 300 m üzeri farklar, kullanılamayan hatlar, çözülemeyen özel sefer notları ve süre tutarsızlıkları [ego-quality.json](../data/processed/ego-quality.json) içinde tek tek tutulur. Kullanılan/yayımlanan sefer sayıları ayrı verilir. Eksikler hizmet yokluğunun kanıtı değildir.

## Süre nasıl hesaplanıyor?

1. Yolculuk bir normal gün türünde 08.00 veya 10.00’da mahalle temsil noktasından başlar. Her profil ayrı matristir; farklı saatlerin en iyi parçaları birleştirilmez.
2. Durak erişimi OSM yürüme ağından hesaplanır. Durağa varışa 60 saniye biniş hazırlığı eklenir; bundan önce geçmiş sefer kullanılamaz. Sabit 8/4 dakika bekleme kaldırılmıştır.
3. Otobüs için yönlü OSM yolları, `bus`/`psv` izinleri ve otobüse özel tek yön etiketleri kullanılır. Durağın en yakın düğümü karşı şeritteyse, en çok 200 m içindeki yakın yol düğümlerinde bağlantı yeniden aranır. Dönüş yasakları ve anlık trafik hâlâ yoktur. Duraklar arasındaki yol, resmî bir araç GPS izi değil, modellenmiş OSM güzergâhıdır.
4. Metro için A, M1–M2–M3 ve M4 ray ağları ayrı tutulur. Aynı hattın paralel raylarından bağlı bir bileşen kullanılır; hizmet yönü resmî durak sırasıdır. Koru–Törekent tek araçta devam edebilir; farklı hatlara geçiş yürüyüş ve yeniden biniştir.
5. Ara durak süreleri, yol/ray ağı ağırlıkları ve duruş payı kullanılarak yayımlanan toplam hat süresine dağıtılır. Eksik bağlantı kuş uçuşu çizgiyle tamamlanmaz. Yayımlanan toplam fiziksel alt sınırın altındaysa (otobüs 90, raylı sistem 80 km/sa ve 10 saniye/durak kontrolü) süre artırılır ve rapora yazılır. Bu sınırlar ve 25 saniyelik ağırlık payı ölçüm değil, açık model varsayımlarıdır.
6. İlk/son yürüyüş en çok 15, her aktarma yürüyüşü en çok 5 dakika; en fazla üç biniş/iki aktarma. Aktarma yürüyüşleri art arda zincirlenerek sınırsız yürüme üretemez. Doğrudan yürüyüş seçilen toplam süre eşiğine kadar mümkündür. Eski modeldeki doğrudan yürüyüş için 15 dakika kesmesi hatalıydı.
7. Aynı algoritma matris üretimini ve arayüzdeki rota açıklamasını besler. Küçük örneklerde bağımsız tek-yolculuk ile toplu hesap eşitliği sınanır. Rotada hat, biniş saati ve bekleme gösterilir; ara durak saati tahmin olarak etiketlenir.

## 291 ve 91 testi

291 önceki tarifesiz ağın coğrafi alt sınırıydı; güncel EGO ihtiyacı veya minimum hastane sayısı değildi. [Yeni deney raporu](transit-validation.md), aynı hedeflerle sırasıyla eski matrisi, yalnız doğrudan yürüyüşü düzeltilmiş matrisi ve dört tarifeli profili karşılaştırır. Bu kontrollü karşılaştırmada nüfus, adaylar, yatak/hekim modeli ve maliyetler değişmez.

91 testi, mevcut 91 hastanenin gerçek yerlerini ve kadrolarını test etmez; sıfırdan en fazla 91 tesis seçmeye izin verir. Tam aday/bağlantı coğrafi gevşetmesinin alt sınırı 91’i aşarsa **bu veri ve varsayımlar altında** 91 mümkün değildir. Eksik sefer/konumlar ve tahmini ara durak zamanları varken bunu gerçek Ankara için kesin bir imkânsızlık iddiasına dönüştürmek doğru olmaz.

Sonraki kritik doğrulama: EGO’dan geçerlilik tarihli `stops`, `trips`, `stop_times`, `calendar_dates`, gerçek yön/varyant geometrileri; durak koordinatlarının güncel kurumsal karşılığı; seçilmiş yolculuklarda ölçülmüş saatler. Dolmuş ve Başkentray bu sürümün EGO kapsamına eklenmiş değildir.
