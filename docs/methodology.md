# Bağımsız yatak/hekim seçimi ve ulaşım modeli · v0.3

## Veri ve hedef

2024 Ankara hizmet kullanımı / aynı yılın nüfusu, 2025 mahallelerine uygulanır. Temas = ikinci/üçüncü basamak başvurusu + yatış; yatak yükü ayrı olarak yatış günüdür. Mahallede ölçülmüş klinik ihtiyaç değildir; il dışı sevkler ve özel tıp merkezi başvuruları ayrıştırılamamıştır. [Kalibrasyon kaynakları](capacity-research.md).

50/150/300/600/1.000/2.000/4.050 yatak seçenekleri vardır. Hekim sayısı yatak tipine sabitlenmez: bağımsız tam sayıdır. 2.140 temas/hekim/yıl, 7 milyon / 3.272 gözlenen özel grup oranından aktarılmış yaklaşık senaryodur; yıllık ortalama FTE veya klinik kapasite standardı değildir. 835 üniversite örneği ve gider çarpanı duyarlılık seçenekleridir. %80 yatak doluluğu planlama tavanıdır; Ankara gözlemi %59,5.

## Değişkenler

`x_jk ∈ {0,1}` yatak tipi; `d_j ∈ Z+` hekim kadrosu; `z_ij ≥ 0` bir mahalleden tesise atanan yıllık talebin kişi eşdeğeri. `B_k` yatak sayısı, `A_k = 4000 + 160 B_k` yatak tesisinin alanı; `a = 80` m²/hekim. `S_j = π r_j² × 9` izin azami kat alanı. `c`, `b` kişi başı temas ve yatış günü; `R` temas/hekim; `u` doluluk; `T` yolculuk eşiği.

```text
sum_k x_jk <= 1                              bir adayda bir yatak tipi
12 sum_k x_jk <= d_j                         açık tesiste asgari kadro varsayımı
d_j <= sum_k floor((S_j-A_k)/a) x_jk          bağımsız kadro + toplam alan
sum_i c z_ij <= R d_j                        hekim kaynağı
sum_i b z_ij <= sum_k 365 u B_k x_jk          yatak kaynağı
sum_j z_ij <= p_i                            talebi iki kez sayma
sum_ij z_ij >= q P                           resmî il toplamına göre hedef
sum_{i in district,j} z_ij >= r P_d           her ilçenin hedefi
z_ij = 0 if t_ij > T or no route             ağ ve süre
sum_jk x_jk <= 91                            yalnız 91 senaryosunda
sum_k(x_ak+x_bk) <= 1                        çakışan iki iz
```

Asgari kadronun alanı sığmayan tip kapatılır. Kapalı tesiste kadro sıfırdır. Yatış günü tekrar ortalama yatış süresiyle çarpılmaz. Branş, hemşire, pik saat, ameliyat/nöbet veya acil kapasitesi ayrıca modellenmez. 26.798 mevcut hekim tüm sektörler toplamıdır, atanabilir hastane kadrosu bütçesi değildir.

## Maliyet

Bütün bileşenler yaklaşık Aralık 2024 TL. 2024 V-B hastane bedeli 22.250 TL/m²; Ocak düzeyi varsayılıp `(1+0.4438)/(1+0.067)` genel TÜFE katsayısıyla yaklaşık Aralık düzeyine taşınır. Bu inşaat fiyat endeksi değil, ortak satın alma gücü proxy dönüşümüdür.

```text
K = unit_cost × sum_j(sum_k A_k x_jk + 80 d_j)
O = operating_multiplier × (fixed_site × sum_jk x_jk
      + physician_cost × sum_j d_j + bed_support × sum_jk B_k x_jk
      + materials_per_contact × sum_ij c z_ij)
CRF = 0.03 / (1 - (1.03)^(-25))
EAC = K × CRF + O
PV = K + O / CRF
```

İlk aşama EAC’yi azaltır. İkinci aşama `EAC ≤ EAC_ref × (1+epsilon)` ve **aynı toplam atanmış talep** altında `sum t_ij z_ij` azaltır. Varsayılan epsilon %10’dur. 25 yıl, %3 reel iskonto, sabit yıllık reel işletme ve sıfır hurda varsayılır. Amortisman ve finansman tekrar gider olarak eklenmez. Arsa, tıbbi cihaz yatırımı/yenilemesi, dış altyapı ve KDV/kurumlar vergisi eksiktir; toplam yaşam döngüsü bütçesi olduğu iddia edilmez.

İşletme kalemlerini sabit/yatak/hekim/temasa ayırma, MLP portföy ve konsolidasyon kapsamlarının farklı olması nedeniyle **yaklaşık aktarım varsayımıdır**. Sadece resmî/gözlenen veri etiketiyle sunulmaz.

## Çözüm kapsamı ve 91 ispatı

Hızlı model her mahallede **her yapı-izi sınıfından en yakın 12** süre içi adayı tutar. Büyük seçenekler daha yakın küçük alanların arkasında kaybolmaz. Kapasiteli modelde coğrafi alt-küme elemesi yapılmaz. Alan, kapasite, çakışma, akış, il/ilçe, tam sayılık ve yıllık bütçe ham çözümde tekrar denetlenir.

LP yuvarlama ve artan kapasite/gider sezgiseli geçerli başlangıç arar; her MILP aşaması 35 saniye ile sınırlıdır. İkinci aşamaya sabit konum/kadro akış LP’siyle de başlangıç verilir. Daha iyi çözüm yoksa ilk plan korunur. Maliyet ve süre optimalite açıklıkları ayrı raporlanır. Sayı minimumunu veya bütün Ankara’da global optimumu kanıtlamaz.

91 senaryosu için ayrı model **4.701 adayın tamamı ve süre içindeki bütün kenarlar** üzerinde en az tesis sayısının alt sınırını bulur. Kapasite, maliyet ve çakışma kısıtları kaldırılır. Bu eş maliyetli gevşetmede tam alt-küme elemesi geçerlidir. Alt sınır >91 ise asıl modelde de 91 imkânsızdır; alt sınır ≤91 ise kapasite modeli ayrıca çözülmelidir. `inconclusive`, daraltılmış/süre sınırlı aramanın sonuçlandıramadığını belirtir; imkânsızlık değildir. [Deney kayıtları](validation.md).

## Göstergeler ve harita

- **Karşılanan talep:** `sum z_ij / resmi P`. Homojen oranlar nedeniyle başvuru, yatış günü ve nüfus eşdeğeri payı aynıdır. En yakın hastanenin yakın olması tek başına kapsanma değildir.
- **Ortalama süre:** `sum t_ij z_ij / sum z_ij`; yalnız atanan talep. Payda JSON'da bulunur.
- **P90:** her atamanın süresi ve kişi eşdeğeri ağırlığı; atanmamış ve konumsuz nüfus sonsuz süreyle toplam paydada. Sonuç sonsuzsa `null`/`—`.
- **Hekim yükü:** atanan temas / hekim temas kapasitesi. **Yatak kapasite yükü:** yatış günü / (yatak × 365 × doluluk tavanı). Yüzde 100 kapasite yükü, fiziksel doluluğun seçilen tavana ulaştığını anlatır. Fiziksel doluluk da JSON'da ayrı bulunur.
- **Mahalle rengi:** tam atanmış yeşil; kısmi turuncu; hiç atanmamış gri. Atanmamış olması yalnız ağ eksikliği anlamına gelmez: kapasite, süre veya kısmi hedefin ekonomik seçimi olabilir.
- **Güzergâh:** ilk olarak en çok payın atandığı tesis; bölünen payların diğer rotaları da seçilebilir. En yakın tesis ile kapasiteye uygun tesis aynı olmak zorunda değildir.
- **Mevcut envanter karşılaştırması:** OSM tesislerinin kapasitesi doğrulanmadığı için yalnız coğrafi erişimdir; kapasiteye göre talep karşılama ile eşdeğer gösterge değildir.

30/45 dakika, %95 il ve %80 ilçe hedefi evrensel standart değildir. Farklı modları karşılaştırırken aynı eşik ve hedefler kullanılmalıdır. Mahalle içi eşitlik ve bireysel ihtiyaç garantisi yoktur.

## Talep noktaları ve konum belirsizliği

Her mahallenin nüfusu tek temsil noktasında kabul edilir. OSM yer etiketi önceliklidir; yoksa mahalle poligonu içinde bir nokta kullanılır. Nüfus ağırlıklı merkez veya her evin konumu bilinmez. İsim normalizasyonu Türkçe karakterleri ve “Mahallesi” gibi ekleri temizler; eşleşme ilçe sınırıyla kısıtlanır. Aynı ilçe/ad için birden fazla OSM kaydı varsa etiket önceliği ve veri sırası kullanılır; bu kayıtlar resmî kodla geometrik doğrulamadan geçmemiştir.

Nokta, ana karayolu bileşenindeki hem araç hem yürüyüş bağlantısı bulunan en yakın düğüme en fazla 1.500 metreyle bağlanır. Bu **kısa bağlantı kuş uçuşu uzunlukla varsayılır** ve yürüme hızıyla süreye eklenir. Uzun yolculuklar gerçek ağdadır; “hiçbir yerde düz çizgi kullanılmıyor” iddiası yoktur. Haritada giriş bağlantıları kesikli çizgidir. Bu bağlantılar duvar, dere veya arazi geçişi bakımından doğrulanmış değildir.

Konumu bilinmeyen 20.516 kişi erişilmiş sayılmaz ve resmî paydada kalır. Bu nüfusu yakın bir mahalleye uydurarak yerleştirme yapılmaz.

## Aday hastane konumları

Nüfusa göre sıralanan talep noktalarının farklı yol giriş düğümleri etrafında aday aranır. Yarıçaplar `80, 100, 125, 150, 180, 220, 270, 330, 400, 500, 650` metredir; her halkada 48 açı denenir. İlk uygun konum alınır. Aynı giriş düğümü tekrar kullanılmaz. Uygun aday bulunmaması, mahallenin talebini silmez.

İlk 1.397 adet 45 m izine, aynı girişler çevresinde 80/120/210 m izler eklendi: toplam 4.701 aday. Büyük izlerin bağlantısı orijinalden kısa olamaz ve 650 m sınırını aşamaz. Her yarıçap için 48 açılı, 125–650 m uzaklıklı halkalarda ilk yol/ray dışı konum seçilir. Bir girişe birden fazla alternatif iz bağlanabilir; seçilen izler fiziksel olarak çakışamaz.

Kapalı alan `4.000 + 160 × yatak + 80 × hekim` m² ve en fazla 9 kat birer tasarım varsayımıdır. İzin 9 kat alanı aşılmaz. Büyük hastane seçeneği küçük yapı izi üzerinde mümkün değilse değişken üst sınırı sıfırlanır. Gerçek Etlik kampüsünün taban planı veya imar uygunluğu modellenmez.

Mevcut bina, mülkiyet, imar, yıkım maliyeti, eğim, tarım/orman/su alanı yerleşim engeli olarak kullanılmaz; istenen idealize edilmiş kapsam budur. İl sınırının dışında aday üretilmez. OSM karayollarının tahmini genişlik koridorları ve yüzey ray yollarının 5 m yarı genişlik koridorları dışlanır. Yeraltındaki ray hatları yüzeyde engel sayılmaz.

Yol genişliği varsa `width/2`, yoksa yol sınıfı kullanılır: otoyol 13 m, ana bağlantı/trunk 12 m, primary 10 m, secondary 8 m, tertiary 6 m, diğerleri 4 m yarı genişlik. Bu etiketler gerçek kadastro yol sınırı değildir. Dolayısıyla “OSM’deki tahmini yol koridoruna taşmıyor” doğrulanır; haritada eksik yol bulunmadığı garanti edilmez.

Hastane sahası yol üzerinde değildir. Sahadan yol girişine bağlantı, 80–650 m arasında varsayılan bir giriş yoludur; arazi üzerindeki gerçek giriş güzergâhı çizilmemiştir. Adaylar mahalle etrafında örneklenir; Ankara’daki her olası koordinatın denenmesi anlamına gelmez.

## Araba ağı

1. OSM ortak düğüm kimlikleriyle yönlü grafik kurulur; yalnız çizgi kesişimi bağlantı oluşturmaz.
2. Tek yön, ters tek yön, dönel kavşak/otoyol varsayımı ve temel `access/motorcar/motor_vehicle/vehicle` izinleri kullanılır.
3. Yol uzunlukları metre cinsinden **EPSG:32636 (UTM 36N)** ile hesaplanır.
4. Hız varsayımları km/sa: otoyol 95; trunk 75; primary 55; secondary 45; tertiary 35; unclassified 30; residential 25; living_street/service 15. Sayısal `maxspeed` varsa bu değerin %75’i varsayılan hız için üst sınırdır. Bağlantı rampaları en fazla 35; alt hız sınırı 5 km/sa.
5. Temsil noktasından yola ve yoldan aday sahaya bağlantı 4,5 km/sa yürüme hızıyla eklenir. Ek 3 dakika park/giriş payı vardır.
6. Her adaydan **ters yönlü grafik** üzerinde Dijkstra ile mahalle→hastane süreleri bulunur. Böylece tek yönler tersine çevrilerek yanlış yönde yolculuk hesaplanmaz.

Trafik çarpanı yalnız sürüş bölümünü büyütür; yürüyüş ve 3 dakikalık payı değiştirmez. Canlı trafik, dönüş yasakları, koşullu erişim saatleri ve trafik ışığı gecikmeleri yoktur. Acil ambulans sürüş profili değildir.

## EGO zaman bağımlı ulaşım modeli

Resmî EGO web kataloğunun kalkış saatleri, durak sırası ve toplam hat süresi kullanılır. [Tam kaynak ve yöntem açıklaması](transit-research.md).

- Normal hafta içi 08.00/10.00, cumartesi 10.00, pazar 10.00 için ayrı süre matrisleri vardır. Seferler arasında keyfî zaman atlama veya farklı hareket saatlerini birleştirme yoktur.
- İlk durağa erişimden sonra 60 saniyelik biniş hazırlığını sağlayan ilk sefer seçilir. Aynı araçta ilerlerken tekrar bekleme eklenmez. Ara durak saatleri tahmini olduğundan bu işlem gerçek zamanlı EGO yolculuk tahmini değildir.
- `backend/timetable.py`, en çok üç binişli FIFO tarife taraması kullanır. Aynı turun araç varışlarından yalnız bir yaya aktarma adımı uygulanır. Toplu matris hesabı ile bağımsız tek-yolculuk izi karşılaştırılır.
- Otobüs geometrisi yönlü OSM yol ağından gelir; `bus/psv` ve otobüse özel tek yön etiketleri işlenir. Metro/ANKARAY geometrisi ilgili hatların OSM ray ağından gelir. Koru–Törekent seferi Kızılay'da yapay aktarma yapmaz. Araç içi uzun kuş uçuşu bağlantı yoktur.
- Ara durak süreleri yol/ray ağı ağırlıklarıyla yayımlanan toplam süreye dağıtılır. Fiziksel alt sınır kontrolüyle artırılan süreler kayıtlıdır. Bu tahminler kesin durak varışları veya canlı trafik değildir.
- İlk/son yürüyüş 15, aktarma yürüyüşü 5 dakika; biniş hazırlığı 1 dakika. En çok iki aktarma. Yalnız yürüyüş seçeneği toplam yolculuk eşiğine kadar mümkündür; 15 dakikada kesilmez.
- Bilinen durak koduyla başlangıç/bitiş ve kesin eşleşen istasyon adı işlenir. Çözülemeyen yön, özel uğrama ve ara durak notları tam-hat seferine dönüştürülmez. Hizmet/konum açıkları sonuçla birlikte yayımlanır.

Adaylar ve talepler değişmedi. [Yeni 91 deneyi](transit-validation.md) aynı %95/%80 hedeflerini korur. Bütün adaylarla coğrafi alt sınır hesaplanması, eksik gerçek hizmeti tamamlamaz; bu sınır yalnız sürümlenmiş model kapsamındadır.
