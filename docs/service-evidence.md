# Kırsal seferlerde yön ve süre kanıtı

23 Ekim 2026 incelemesi, iki hattaki **24 yayımlanmış kalkış kaydını** dar kapsamda yorumlar: 560-8 için 20 Sincan → Ayaş kaydı, 615 için yalnız dört hafta içi Ulus → Güdül kaydı. Yeni sefer icat edilmez. Bunlar ölçülmüş yolculuklar veya güncel resmî GTFS değildir; özellikle 615’in süreleri, güncel geçerliliği doğrulanmamış **2025 tarihli planın** açık bir model varsayımı olarak aktarılmasıdır.

## 560-8: tam yönün 75 dakikalık süre alanı

[Resmî hareket sayfasındaki](https://www.ego.gov.tr/hareketsaatleri?hat_no=560-8) durak zinciri Sincan Lale Meydanı `50328` ile başlar, Ayaş Sülüklü Sokak `50002` ile biter. Burada 1–55 sıraları **tam yayımlanmış yönü** kapsar. Aynı sayfanın `Süresi` alanı 75 dakikadır; süre bu tam zincire verilir. Uzun bir gidiş–dönüş zincirinden parça kesilerek, yarıya bölünerek veya ikiyle çarpılarak üretilmez.

| Gün türü | Dahil edilen Sincan kalkışları | Kayıt sayısı |
|---|---|---:|
| Hafta içi | 07.40, 08.00, 11.00, 14.15, 15.15, 16.10, 21.00, 22.15 | 8 |
| Cumartesi | 10.00, 11.45, 14.30, 15.00, 16.00, 19.00 | 6 |
| Pazar | 09.30, 11.30, 14.00, 16.45, 19.00, 22.15 | 6 |

Her kayıt kendi gün sütunu, saat ve tam notuyla bağlıdır. Hafta içi ve çoğu pazar kaydında not saati kalkış saatiyle aynıdır; cumartesi notları `SİNCAN` der. [Erişilebilir resmî sayfa](https://www.ego.gov.tr/engelli/duyurudetay/7686) bu kalkış/not ayrımını destekler. Cumartesi 22.15’teki farklı `SİNCAN AYAŞ BİTER` kaydı ve `1;1` alanları bu dar yorumun dışında bırakılmıştır.

75 dakika, her seferin ölçülmüş varış süresi değildir. Sayfada sefer başına varış veya kapanış saati bulunmaz. Erişilebilir sayfanın duyuru gövdesi 27 Kasım 2025’te başka bir güzergâha aktarılan 18.15 seferini anlatır; bu tarih, sayfanın altında gözlenen bütün saatlerin ortak geçerlilik tarihi yapılmaz.

## 615: tarihli plandan yalnız dört gidiş kaydı

[27 Ağustos 2025 tarihli resmî duyuru](https://www.ego.gov.tr/tr/duyuru/7621/615-gudululus-ve-6151-gudulceltikci-hattinin-servis-saatleri-duzenlenmistir), düzenlemenin 29 Ağustos 2025’te başlayacağını belirtir. Tablonun sağındaki **hafta içi planlanan tarife** kullanılır; soldaki eski tarife ile karıştırılmaz.

| Yön | Planlanan hareket | Planlanan kapanış | Aradaki süre |
|---|---:|---:|---:|
| Ulus → Güdül | 06.30 | 08.05 | 95 dakika |
| Ulus → Güdül | 09.00 | 11.00 | 120 dakika |
| Ulus → Güdül | 15.00 | 17.00 | 120 dakika |
| Ulus → Güdül | 20.00 | 22.00 | 120 dakika |

Bu dört hareket saati ve `ULUS TAN` notu, 23 Ekim 2026 TSİ’de gözlenen [615 hareket sayfasında](https://www.ego.gov.tr/hareketsaatleri?hat_no=615) da vardır. **Kalkışların eşleşmesi eski kapanış saatlerinin hâlâ geçerli olduğunu kanıtlamaz.** Duyuruda bitiş geçerlilik tarihi yoktur; 2026’da ölçülmüş veya yeniden onaylanmış terminal varışları elde edilmemiştir. Model, yukarıdaki tarihli süreleri bu dört eşleşen gidişe tahmini süre bütçesi olarak uygular.

Yön, yayımlanan zincirde `11554` Çevikkuvvet (1. sıra) → `57033` Güdül Otobüs Yazıhanesi (86. sıra) olarak tanımlanır. [Erişilebilir 615 sayfasındaki](https://www.ego.gov.tr/engelli/duyurudetay/7621) gidiş kayıtlarının `1;86` alanları ve [615-1’in](https://www.ego.gov.tr/hareketsaatleri?hat_no=615-1) aynı `57033` terminalinden başlaması bu eşleştirmeyi destekler. Kapanış tablosu doğrudan durak kodu yayımlamaz: kapanışın bu terminale eşlenmesi **kaynaklar arası çıkarımdır**. Aynı kökü taşıyan ilk durak adına göre otomatik seçim yapılmaz; sıra ve aynı kimliğin kaçıncı görünümü ayrıca korunur.

95/120 dakika, 160 duraklı gidiş–dönüş zincirinin eski zamanlarından dilimlenmez. Seçilen 1–86 yönünün tamamına yeni bütçe verilir. Segmentlerin fiziksel alt sınırları bütçeyi aşarsa model süreyi yükseltir ve kalite raporuna yazar; tahmini bütçe uğruna fiziksel sınır düşürülmez. Ara durak saatleri yine tahmindir.

## Açık kalan hizmetler

- **615 dönüşü:** tarihli planda beş Güdül kalkışı vardır. Ancak yayımlanmış zincirin 160. durağı Akköprü’dür; planın Ulus kapanışıyla aynı nokta olduğu doğrulanmamıştır. `86;1` alanı durak listesini ters çevirme veya terminale yapay bağlantı ekleme izni değildir. Bu beş dönüş kaydı bu yorumla eklenmez.
- **615 hafta sonu ve cuma ek seferi:** hafta içi kapanış süreleri hafta sonuna taşınmaz. 18.20 cuma ilavesi genel hafta içi sefer yapılmaz. Cumartesi/pazar notlarındaki `1;0` alanları tek başına yön çözmez.
- **560-4:** 21 basit Ayaş başlangıç kaydı için olası 10–51 yönü incelendi; 60 dakikalık tam hat alanının bu alt yöne ait olduğu kanıtlanmadı. Farklı saatli 86 Evler/Ayaş notları ve ters yön alanları ayrıca belirsizdir. Süre tahminle doldurulmaz.
- **158, 178, 490 ve 677:** terminalin hangi görünümünün kastedildiği, saatlerin başlangıç/dönüş rolü veya yön süresi yeterince bağlanamadı. Haymana, Bala, Kalecik ve Nallıhan’da bu modelleme açıklıkları sürer. Dışlanan kayıtlar gerçek hizmetin olmadığı anlamına gelmez.

Erişilebilir sayfalardaki iki sayısal alanın bütün hatlarda güvenilir başlangıç/bitiş şeması olduğu doğrulanmadı. `1;0`, ters sıralar ve çelişen kayıtlar bulunduğundan bu alanlardan genel bir yön çözümleyici üretilmez. 615-1 burada terminal kimliğinin destekleyici kaynağıdır; bu inceleme onun için yeni sefer kuralı eklemez.

## Seyrek yol düğümlerine bağlı üç durak

OSM’de uzun bir yol kenarının ortasındaki durak, yola birkaç metre uzak olduğu halde iki uç düğüme 300 metreden uzak kalabilir. Yeni otobüs bağlantısı bu durumu, mevcut yönlü yol kenarına nokta ekleyerek ele alır. En yakın eski çıkış düğümüne zaten 300 metre içinde ulaşan durak değiştirilmez; kenara uzaklık da 300 metreyi aşamaz. Eşit yakınlıktaki farklı kenarlar birleştirilmez. Yeni ağda `50253`, `51270` ve `51271` olmak üzere üç durak için bu bağlantı oluşmuştur; kayıtları `ego-quality.json` içindeki `busStopProjection` izler.

Beş uzak durak incelenmiştir; `22423` ve `22424` yol kenarına da 300 metreden uzak olduğundan bağlanmamıştır. Örneğin Kurtboğazı’ndaki `51270` ve `51271`, karşılıklı iki ayrı yol kenarında tutulur. Parçalar yalnız eski kenarın izin verdiği yönde ilerler; karşı şeride, köprüye veya ayrı yola yeni geçiş eklenmez. Bu değişiklik yürüme erişimini veya araba ağını kendiliğinden düzeltmez; gerçek durak girişinin sahada doğrulandığı anlamına gelmez.

Bağımsız denetim, üreticinin kenar bölme fonksiyonunu çağırmadan stop/rapor kimliklerini, özgün uçları, kenar üzerindeki konumu, mesafeleri ve yeni noktaya komşu rota parçalarının yönünü sınar. Altı ondalıklı yol geometrisi için 0,20 metre; tam hassasiyetli kayıtlar için 0,01 metre tolerans kullanılır. Ham OSM varsa özgün ardışık kenar, izinli yön ve eski en yakın çıkış düğümü uzaklığı da denetlenir. Ham kaynak yoksa bu kaynak kontrollerinin yapılmadığı açıkça raporlanır. Bu denetim tüm yol ağının veya saha yolculuklarının doğrulanması değildir; 0,20 metre altındaki parçaların yönü yuvarlamadan ayırt edilemez.

## Altı kaynak arşivi ve zamanların anlamı

`data/evidence/ego/` içinde altı gerçek HTTP yanıtı gzip olarak tutulur. `ego-service-evidence.json`, kaynak URL’sini, HTTP gözlem zamanını, açılmış yanıtın bayt sayısı ve SHA-256 kimliğini taşır. Gzip dosyasının kendi bayt kimliği ayrıca ulaşım paketine bağlanır. Aşağıdaki SHA’lar **gzip açıldıktan sonraki HTML’ye** aittir; kurum tarafından yayımlanmış imzalar değildir.

| Kaynak | HTTP observedAt (UTC) | Açılmış yanıt SHA-256 |
|---|---|---|
| [560-8 erişilebilir duyuru/saatler](https://www.ego.gov.tr/engelli/duyurudetay/7686) | `2026-10-22T22:06:19.596475+00:00` | `05f7355b8e9abe3d8da7d5befe48059b8fecd85fe169be70261036b647ad083a` |
| [615 erişilebilir duyuru/saatler](https://www.ego.gov.tr/engelli/duyurudetay/7621) | `2026-10-22T22:06:18.393478+00:00` | `66b9d2e31234c5a85141a759958468b659ef74b8e859aeb3cc6d32295b167070` |
| [615 tarihli hareket–kapanış planı](https://www.ego.gov.tr/tr/duyuru/7621/615-gudululus-ve-6151-gudulceltikci-hattinin-servis-saatleri-duzenlenmistir) | `2026-10-22T22:06:17.817843+00:00` | `9fdc1d355bf3d5242a79eef9e74e4275f4b258de652dc8c27d804519af6ef4b2` |
| [560-8 hareket sayfası](https://www.ego.gov.tr/hareketsaatleri?hat_no=560-8) | `2026-10-22T22:06:56.804903+00:00` | `51f04d6f0dc7b063341cf950445230c178abac87f8b9bbfed9baeff8dd4520b6` |
| [615 hareket sayfası](https://www.ego.gov.tr/hareketsaatleri?hat_no=615) | `2026-10-22T22:06:54.365110+00:00` | `e11edc1b07ada0c85ea3574ee2ec3d2338c110f27934eced68f390871d6a6c3e` |
| [615-1 terminal kimliği](https://www.ego.gov.tr/hareketsaatleri?hat_no=615-1) | `2026-10-22T22:06:55.202088+00:00` | `a2b9bc0b153731947574750378467794ae0492a2d741db667d16dd9bc0843c0c` |

Bu gözlemler 23 Ekim 2026 TSİ 01.06 civarındadır. Duyurunun yayın tarihi, uygulanacağı söylenen tarih, HTTP gözlem zamanı ve yeniden işleme zamanı ayrı tutulur. Daha önceki 666 tarife önbelleğinin bilinmeyen gözlem tarihleri bu yeni altı gözlemle geriye dönük doldurulmaz.

## Değişiklik olduğunda yorum nasıl durdurulur?

Her kural, kaynak yanıtının SHA’sına, sıralı durak kimliklerine, gün türüne, tam kalkış saatine ve tam nota bağlıdır. Kaynak baytları, durak sırası veya ilgili olay değişirse kural yeniden incelemeye kadar uygulanmaz. Tarihli planın satır hücreleri arşivlenmiş HTML tablosuyla da karşılaştırılır; yalnız elle yazılmış özetin hash’i yeterli kabul edilmez.

`ego-service-evidence.json` tanımlı 24 kuralı; `ego-quality.json` ise hangilerinin gerçekten uygulandığını, dışlandığını veya kaynak değişikliği nedeniyle geçersiz kaldığını gösterir. Bu pakette 24 kaydın tamamı üç örüntüde uygulanmıştır (560-8 için bir, 615’in 95 ve 120 dakikalık bütçeleri için iki). Bu, erişim hedefinin sağlandığı anlamına gelmez. Ağ, dört profil matrisi, kayıtlı hastane çözümleri, 91 testi ve sabit plan deneyi birlikte yeniden üretilir. Bütünlük denetimi bu kayıtları birbirine bağlar; tarihli süre varsayımını güncel saha gerçeğine dönüştürmez.
