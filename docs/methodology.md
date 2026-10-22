# Model ve hesaplama yöntemi

## Amaç ve değişkenler

`i`: konumlandırılmış mahalle, `j`: ayrık hastane adayı, `d`: ilçe.

- `p_i`: mahallenin ADNKS nüfusu.
- `P`: Ankara’nın resmî toplam nüfusu; `P_d`: ilçenin resmî toplam nüfusu.
- `t_ij`: seçili ulaşım ağında mahalleden adaya tahmini dakika. Bağlantı yoksa sonsuz.
- `T`: kullanıcının seçtiği süre eşiği.
- `a_ij = 1[t_ij ≤ T]`: erişim matrisi.
- `x_j ∈ {0,1}`: adayda hastane açılması.
- `y_i ∈ {0,1}`: mahalle nüfusunun eşik içinde kapsanması.
- `q`: Ankara kapsama hedefi; `r`: her ilçe için kapsama tabanı.

Birincil problem:

```text
minimize  Σ_j x_j

y_i ≤ Σ_j a_ij x_j                         her i için
Σ_i p_i y_i ≥ q P
Σ_{i: district(i)=d} p_i y_i ≥ r P_d        her d için
x_j, y_i ∈ {0,1}
```

Her tesisin maliyeti aynı 1 birimdir. Farklı tesis büyüklükleri, kapasiteler veya hizmet türleri bu modelde yoktur. Bir hastaneye atanabilecek kişi sayısı sınırlanmaz; model **coğrafi erişim** ölçer. Nüfusun sağlık hizmeti ihtiyacının fiilen karşılandığı sonucunu üretmez.

İkinci aşama, birinci aşamadaki tesis sayısını eşitlik kısıtıyla sabitler ve kapsanan nüfusu artırır. Üçüncü aşamada en iyi tek tesis değişimi iki tur denenir: tesis sayısı, ikinci aşamada ulaşılan toplam kapsama ve ilçe tabanları korunur; nüfus ağırlıklı süre azaltılır. Yerel aramada erişilemeyen bir bağlantıya 1.440 dakika ceza verilir; **bu ceza kullanıcıya gerçek seyahat süresi olarak gösterilmez**.

Birinci aşamada kapsadığı mahalle kümesi başka eşit maliyetli adayın alt kümesi olan adaylar elenir; bu işlem minimum tesis sayısını değiştirmez. İkinci ve üçüncü aşamalar tüm aday havuzunu kullanır. Uygulamada `y` değişkenleri `[0,1]` aralığında sürekli bırakılabilir: ikili `x` altında erişilemeyen mahallede sıfır, erişilende bir olabildikleri için kapsama uygulanabilirliği ve hedef aynıdır; asıl tesis kararları ikilidir.

İkinci aşama 10 saniye ve %0,05 bağıl MILP toleransı kullanır. Birinci aşama 20 saniye ve sıfır bağıl açıklık ister. Süre sınırında geçerli bir çözüm varsa `feasible` ve açıklık/alt sınır raporlanır. `optimal` yalnız birinci aşamada en az tesis sayısının ispatlandığını anlatır. Seyahat süresi için global optimum iddiası yoktur. Donanım/süre sınırı nedeniyle aynı minimum sayıya sahip farklı konumlar ve ikincil sonuçlar çıkabilir.

## Neden ilçe tabanı var?

İl geneli %95 kapsama tek başına küçük ilçelerin büyük bölümünü dışarıda bırakmaya izin verebilir. Her ilçede ayrı bir minimum oran, coğrafi dengeyi açık bir kısıta dönüştürür. İlçe içinde mahalle/yaş/gelir düzeyinde eşitliği garanti etmez. İlçe tabanı yükseldikçe minimum tesis sayısı artabilir; sonuç bulunamaması da anlamlı bir bulgudur.

Başlangıçtaki araba 30 dakika, EGO senaryosu 45 dakika, %95 genel hedef ve %80 ilçe tabanı klinik standart değildir. Kullanıcı bu değerleri değiştirebilir. Araba ve EGO sonuçlarını doğrudan karşılaştırırken **aynı T, q ve r değerleri** kullanılmalıdır; farklı varsayılan sürelerle çıkan sayılar eşdeğer senaryo değildir.

## Talep noktaları ve konum belirsizliği

Her mahallenin nüfusu tek temsil noktasında kabul edilir. OSM yer etiketi önceliklidir; yoksa mahalle poligonu içinde bir nokta kullanılır. Nüfus ağırlıklı merkez veya her evin konumu bilinmez. İsim normalizasyonu Türkçe karakterleri ve “Mahallesi” gibi ekleri temizler; eşleşme ilçe sınırıyla kısıtlanır. Aynı ilçe/ad için birden fazla OSM kaydı varsa etiket önceliği ve veri sırası kullanılır; bu kayıtlar resmî kodla geometrik doğrulamadan geçmemiştir.

Nokta, ana karayolu bileşenindeki hem araç hem yürüyüş bağlantısı bulunan en yakın düğüme en fazla 1.500 metreyle bağlanır. Bu **kısa bağlantı kuş uçuşu uzunlukla varsayılır** ve yürüme hızıyla süreye eklenir. Uzun yolculuklar gerçek ağdadır; “hiçbir yerde düz çizgi kullanılmıyor” iddiası yoktur. Haritada giriş bağlantıları kesikli çizgidir. Bu bağlantılar duvar, dere veya arazi geçişi bakımından doğrulanmış değildir.

Konumu bilinmeyen 20.516 kişi erişilmiş sayılmaz ve resmî paydada kalır. Bu nüfusu yakın bir mahalleye uydurarak yerleştirme yapılmaz.

## Aday hastane konumları

Nüfusa göre sıralanan talep noktalarının farklı yol giriş düğümleri etrafında aday aranır. Yarıçaplar `80, 100, 125, 150, 180, 220, 270, 330, 400, 500, 650` metredir; her halkada 48 açı denenir. İlk uygun konum alınır. Aynı giriş düğümü tekrar kullanılmaz. Uygun aday bulunmaması, mahallenin talebini silmez.

Örnek tesis izi, **45 m yarıçaplı bir dairedir** (yaklaşık 6.362 m² taban alanı). Bu, hastane standart alanı veya yatak kapasitesi iddiası değildir; yola taşmama kontrolü için seçilmiş ve koddan değiştirilebilir bir geometrik varsayımdır. Büyük parsellerde daha fazla aday ve farklı yapı izi duyarlılığı sonraki aşamadır.

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

## EGO ağ senaryosu

Bu mod **resmî EGO tarifesiyle çalışan bir yolculuk planlayıcı değildir**. İlk uygulamada kullanılabilir gerçek yol/ray geometrilerini göstermek ve iki ulaşım modelinin farkını araştırmak içindir.

- OSM otobüs ilişkilerinde sayısal hat referansı, ayrıca subway/light_rail kullanılır. Tren hatları bu senaryoya eklenmez; dolayısıyla Başkentray dahil tüm toplu ulaşım ağı iddiası yoktur.
- Otobüste varsa platform düğümleri, aksi halde durak düğümleri; raylı sistemde durak düğümleri sıralarıyla işlenir. Durak geometrisine en fazla 200 m bağlantı kabul edilir.
- Her hat ilişkisinin kendi üye yol/ray parçalarında duraklar arası yol bulunur. Eksik bağlantıda duraklar arasına hayalî uzun düz çizgi çekilmez. Geometri alt grafiği çift yönlüdür; hizmet yönünü durak sırası belirler. Döngü/aynı yolun birden çok kullanımı bulunan ilişkiler için tam sefer geometrisi garantisi yoktur.
- Araç içi durum düğümleri sayesinde aynı araçta kalırken her durakta yeniden bekleme eklenmez. Her yeni binişte otobüs 8, raylı sistem 4 dakika varsayımsal bekleme vardır; `entry_only/exit_only` rollerine uyulur.
- Otobüs hızı yol hız varsayımıyla sınırlı, en fazla 28 km/sa; raylı sistem 40 km/sa. Durak geçişi başına 25 saniye eklenir.
- Yürüme OSM yaya ağından, 4,5 km/sa; merdivenlerde 3 km/sa hesaplanır. İlk/son yürüyüş bağlantısı en fazla 15 dakika; duraklar arası her aktarım yürüyüşü en fazla 5 dakikadır. Toplam aktarma sayısı veya toplam yürüyüş için ek tavan yoktur; ardışık yürüme bağlantıları mümkündür.
- 15 dakikaya kadar yalnız yürüyerek erişim de bir seçenektir. Dolayısıyla her EGO sonucu mutlaka otobüse/metroya binildiği anlamına gelmez.
- Hatların hepsinin o anda çalıştığı varsayılır. Hareket saati, gün, gerçek bekleme, son sefer, kesinti, kapasite ve engelli erişimi hesaba katılmaz.

Bu nedenle süreler iyimser veya kötümser olabilir. Erişilemeyen hedef; gerçek hizmet yokluğu, OSM kapsam açığı, tek nokta temsili, aday örneklemesi veya yürüme sınırından kaynaklanabilir. Uygulama gerçek EGO hizmet yetersizliği teşhisi koymaz.

## Göstergeler

| Gösterge            | Hesap / yorum                                                                                                      |
| ------------------- | ------------------------------------------------------------------------------------------------------------------ |
| T süresinde kapsama | `Σ p_i 1[min_j t_ij ≤ T] / P`; tüm il nüfusu paydada                                                               |
| Ortalama yolculuk   | Sonlu süresi hesaplanabilen nüfusla ağırlıklı ortalama; paydası ayrıca JSON’da                                     |
| P90                 | Toplam nüfusun %90’ının ulaştığı süre; bilinmeyen/erişilemeyen süre sonsuz kabul edilir; P90 sonsuzsa arayüzde `—` |
| İlçe kapsama        | Aynı yöntem, her ilçenin resmî nüfusu paydada                                                                      |
| Maliyet birimi      | Seçilen tesis sayısı; gerçek TL değildir                                                                           |
| Optimalite açığı    | Birinci aşama geçerli çözüm maliyeti ile matematiksel alt sınır arasındaki bağıl açık                              |

Eşleşmeyen nüfusu ortalama sürede sıfır süreli saymak veya sonsuz süreyi gerçek bir dakika olarak göstermek yerine, ortalama paydası ve erişilemeyen nüfus ayrı raporlanır. Sonuçlar bu iki gösterge birlikte okunarak karşılaştırılmalıdır.

## Üst sınır ve çözümsüz senaryo

Optimizasyondan önce bütün adaylar açılsa hangi mahallelere T içinde erişilebildiği hesaplanır. Toplam veya herhangi bir ilçe hedefi bu üst sınırı aşarsa `infeasible` döner; kapsama üst sınırı ve sınırlayan ilçeler görünür. Böylece eksik veri, sonsuz süre veya aşırı sıkı hedefler görünmez bir kuş uçuşu kestirmeyle kapatılmaz.
