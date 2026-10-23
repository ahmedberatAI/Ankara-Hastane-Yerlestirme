# Otobüs durağını yönlü yol ağına bağlama

Bu yöntem resmî durak sırasıyla OSM yol yönünü birlikte kullanır. Gerçek peron girişinin, otobüsün GPS güzergâhının veya ölçülmüş seyahat süresinin doğrulaması değildir. Sayısal eşikler araştırma varsayımlarıdır; EGO tarafından yayımlanmış eşleştirme standardı olarak sunulmaz.

## Neden yalnız en yakın yol düğümü yeterli değil?

Uzun bir yol kenarının ortasındaki durak, yolun kendisine yakınken köşe düğümlerinden uzakta olabilir. Bölünmüş yollarda en yakın düğüm karşı taşıt yolunda da kalabilir. Bu durumda rota, gereksiz bir U dönüşü kullanır. Yalnız daha kısa yolu seçmek de güvenilir bir düzeltme değildir: yanlış yönde veya bağlantısız yol üzerinde kısa bir yol üretilebilir.

Önceki uzak-durak politikası, eski düğüme 300 metreden uzak kalan durakları mevcut yol kenarına bağlar. Bu politikanın üç doğrulanmış kaydı ayrı tutulur. Yeni politika daha yakın durakların yön/sıra tutarlılığını sınar; iki politikanın sayıları birbirine karıştırılmaz.

## Yeni eşleştirmenin koşulları

- Durak en yakın uygun yol kenarına en çok 15 metre uzaktadır; kenar bağlantısı eski düğüm bağlantısını en az 10 metre iyileştirir.
- Yakındaki başka yol veya aynı yolun başka kolu en az 10 metre daha uzakta olmalıdır. 30 metre içindeki köprü, tünel veya farklı katman belirsizliği seçimi durdurur.
- Aynı tek yönlü yol üzerinde, resmî listedeki ardışık bir durak çifti ileri yönü destekler. Yol boyunca mesafe 50–1.000 metre arasında olmalı, düz mesafenin iki katı +25 metreyi aşmamalıdır. Ters yönü destekleyen çelişkili sıra seçimi durdurur.
- Her gelen/giden komşu bağlantısı ayrıca incelenir. Eski düğümün aynı yolun herhangi bir yerinde bulunması yetmez; yerel en yakın segmentin ucunda olması gerekir. İki yönlü yol, paralel yol belirsizliğinden otomatik muaf tutulmaz. Ortak kavşak istisnası gerçek ortak yerel uç düğümü gerektirir.
- Bir durak elenince onun komşuları yeniden değerlendirilir; seçim değişmeyene kadar bu işlem sürer. Böylece artık kabul edilmeyen bir komşu, başka bir durağın kabul gerekçesi olarak kalmaz.

Mevcut üç uzak-durak kaydı yalnız kimlikleri ve gerçek kenarları doğrulanarak korunur. Bir sözlüğe durak kimliği eklemek, o durağa güvenilir başlangıç kaydı statüsü kazandırmaz.

## Rota hesaplanırken bağlantı korunur

Yol kenarı bölünürken izinli yönler ve toplam kenar maliyeti korunur; araba ve yürüme ağı değiştirilmez. Yeni eşleştirilmiş bir durağa dokunan her rota parçasının **iki ucu da** ağdaki tek ortak durak kaydına sabitlenir. Rota aramasının daha kısa yol bulmak için komşu bir düğüme geçmesine izin verilmez. Yol bulunamazsa veya mevcut geometri sınırı aşılırsa bağlantı çözülememiş olarak kalır; karşı yola geri dönüş yapılmaz.

Uzayan yasal yollar da sonuçta tutulur. Daha az hastane veya daha kısa yol üreten eşleştirmeler seçilmez. Çözülemeyen bağlantı, gerçek ulaşım hizmetinin yokluğu anlamına gelmez.

## Kanıt ve sınırlar

`ego-quality.json` içindeki `busStopMatching`, kabul edilen ve bekletilen durakları, yol/segment kimliklerini, resmî sıra tanıklarını, komşu eleme nedenlerini ve kilitli rota sonuçlarını saklar. Arayüze yalnız aynı raporla doğrulanmış küçük sayısal özet verilir. Ağ, kaynaklar, kod ve dört profil matrisi içerik kimlikleriyle aynı pakete bağlanır.

Bağımsız doğrulayıcı üretici eşleştirme fonksiyonlarını çağırmaz. Paketlenmiş durak/rota kayıtlarını ve resmî sıra tanıklarını yeniden sınar. Ham OSM mevcutsa en yakın segment, alternatif yol, katman, yön ve komşu seçimini ayrıca kaynak üzerinden yeniden kurar. Ham kaynak olmayan ortamda bu son kontrollerin yapılmadığını açıkça raporlar; paket içi tutarlılık kontrolünü saha doğrulaması olarak adlandırmaz.

Kapsam kısmidir. OSM'de eksik erişim/katman etiketleri, eski düğüm bağlantıları, belirsiz komşular, çözümlenmeyen özel seferler ve tahmini ara durak zamanları açık kalır. 615 ve 560-8'de araştırılan bazı hatalı bağlantılar komşu belirsizliği nedeniyle bu dar düzeltmeye alınamamıştır. Bu nedenle hastane sayıları gerçek Ankara'nın kesin ihtiyacı olarak kullanılamaz. Güncel uygulanmış sayılar ve 91 hastane deneyleri [ulaşım doğrulama raporundadır](transit-validation.md).
