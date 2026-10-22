# Kapasiteli yer seçimi ve ulaşım modeli

## Amaç

Sıfırdan 50, 150 veya 300 yataklı tesislerin konum ve büyüklükleri seçilir. Mevcut hastaneler kısıt değildir. Bir tesisin hem hekim başvuru kapasitesi hem yatak-gün kapasitesi karşılanmadan talep atanamaz. Eski kapasitesiz model `backend/optimizer.py` içinde tarihsel karşılaştırma ve ortak istatistik yardımcıları için korunur; `/api/solve` artık `backend/capacity.py` kullanır.

## Veri ile varsayımın ayrılması

Ayrıntılı köken, tablo/sayfa, SHA-256 ve varsayımlar: [health-planning.json](../data/processed/health-planning.json), [kapasite araştırması](capacity-research.md).

2024 Ankara toplamları: 47.073.855 ikinci/üçüncü basamak başvurusu; 1.063.851 yatış; 5.409.136 yatış günü. Aynı yılın 5.864.049 nüfusuna bölünerek oranlar türetilir. Bu oranlar 2025 nüfusuna ve kullanıcının talep çarpanına uygulanır. Birinci basamak ve diş başvuruları eklenmez. İkinci/üçüncü basamak toplamındaki özel tıp merkezleri ayrıştırılamadığından talep geniş kapsamlı bir vekil değişkendir. İl dışından gelen hastaların kökeni bilinmez; bütün kullanım il nüfusuna dağıtılır. Bu, gözlenmiş mahalle talebi veya karşılanmamış klinik ihtiyaç ölçümü değildir.

26.798 hekim ve 24.909 yatak mevcut durum bağlamıdır; tüm hekimleri hastanelere atanabilir insan kaynağı kabul eden bir bütçe kısıtı kullanılmaz. Şablon kadroları 30/90/180 hekimdir. Hekim başına yıllık 4.000 başvuru ve %80 yatak doluluk tavanı değiştirilebilir varsayımlardır. Başvuru kapasitesi; ameliyat, servis, nöbet ve eğitim saatlerini ayrı ayrı kapsayan bir kadro standardı değildir.

## Değişkenler ve kısıtlar

`i`: mahalle, `j`: aday, `k`: tesis tipi; `p_i`: nüfus; `x_jk`: ikili tesis seçimi; `z_ij >= 0`: yıllık talebi o tesise atanan **kişi eşdeğeri** (tekil hasta değil). Mahalle talebi bölünebilir. `v`: kişi başına yıllık başvuru; `b`: kişi başına yatış günü, her ikisi de talep çarpanını içerir. `D_k`, `B_k`, `C_k`: hekim, yatak ve bina yapım bedeli; `R`: başvuru/hekim/yıl; `u`: doluluk tavanı; `t_ij`: ağ süresi.

```text
sum_k x_jk <= 1                                    adayda en fazla bir tesis
sum_k(x_ak + x_bk) <= 1                            yapı izleri çakışan aday çifti
sum_j z_ij <= p_i                                  talebi iki kez sayma
sum_i v * z_ij <= sum_k D_k * R * x_jk              hekim kapasitesi
sum_i b * z_ij <= sum_k B_k * 365 * u * x_jk         yatak-gün kapasitesi
sum_ij z_ij >= q * P                               il hedefi
sum_{i in d,j} z_ij >= r * P_d                     her ilçe tabanı
z_ij = 0  if t_ij > T or no path                   süre/ağ kısıtı
```

Yatış sayısı ayrıca raporlanır: `atanan kişi eşdeğeri × yıllık yatış/nüfus`. Ortalama yatış süresi `5.409.136 / 1.063.851 = 5,084486...` gündür; yatış günü oranı bu süreyle **tekrar çarpılmaz**. Yatak doluluğu yıllık kapasiteyi tanımlar; pik gün, branş ve kuyruk garantisi değildir.

## Maliyet ve yolculuk süresi

1. `min sum_jk C_k x_jk`: kapasite, süre, il ve ilçe hedefleri altında düşük maliyetli çözüm.
2. Bulunan geçerli çözümün bedeli `C_ref`, atanan talebi `Z_ref` olarak kaydedilir. `sum C_k x_jk <= (1+epsilon) C_ref` ve `sum z_ij = Z_ref` eklenir. `min sum t_ij z_ij` çözülür. Toplam talep sabit olduğundan bu, atanan talebin ortalama süresini azaltır. Hangi mahalleye ne kadar pay ayrıldığı iki aşamada değişebilir; ilçe tabanları korunur.

Varsayılan epsilon %10, değiştirilebilir aralık %0–30. **Bütçe, kanıtlanmış minimuma değil bulunan maliyet çözümüne göredir.** Dakikayı keyfî parasal değere dönüştürmeyen epsilon-kısıt yaklaşımıdır. Sonucun tesis sayısı amaç fonksiyonu değildir; kapasite ve maliyet seçimlerinden çıkar.

Şablonlarda alan `4.000 + 160 × yatak` m² varsayılır. 2026 tebliğinde IV-C: 40.500 TL/m² (200 yatak altı), V-B: 43.850 TL/m² (200–399 yatak). Bedeller 486 milyon, 1,134 milyar ve 2,2802 milyar TL'dir. **Bina yapım göstergesi**; KDV, arsa, çevre/dış altyapı, tıbbi cihaz, personel ve işletme giderleri hariçtir. Yaşam döngüsü maliyeti veya ihale keşfi değildir. Eşit birim maliyet yaklaşımı kaldırılmıştır.

## Çözüm kapsamı ve kalite

Her mahalle için eşik içindeki en yakın 16 aday tutulur. Kırsalda daha az bağlantı varsa hepsi kullanılır. Yalnız bu seyrek bağlantı havuzunda optimalite sınırı raporlanır; 1.397 adayın tüm olası bağlantıları için global optimum iddiası yoktur. Kapasite nedeniyle, eski küme-kapsama modelindeki alt-küme aday elemesi **kullanılmaz**: aynı yere erişen ek tesis ek kapasite sağlar.

HiGHS 1.12, tek iş parçacığı, seed 7. LP gevşetmesi (en fazla 15 saniye), ilçe ve il hedeflerini kapasite/maliyet oranıyla tamamlayan başlangıç çözümü; maliyet MILP'si 35 saniye. Seyahat aşaması için sabit tesislerde LP ataması ve bütçeye sığan kapasite ekleme denemeleri en fazla 12 saniye; ardından tam seyrek aday havuzunda seyahat MILP'si 35 saniye. Yerel başlangıç denemeleri optimalite iddiası taşımaz. Her ekleme LP ile doğrulanır. MILP toleransı %1; `optimal` etiketi yalnız raporlanan açık sıfıra yakınsa ve ek bütçe sıfırsa kullanılır. Aksi halde `feasible` ve iki aşamanın açıklıkları ayrı raporlanır.

Başlangıç çözümü sıcak başlangıç olarak verilir. İkinci aşama daha iyi geçerli çözüm bulamazsa ilk çözüm korunur. Ham, yuvarlanmamış çözümde kapasite, akış, il/ilçe ve bütçe kısıtları yeniden hesaplanır; ihlalde sonuç yayımlanmaz. API girdi aralıkları doğrulanır. Yeni senaryolar tekrar hesaplanır, aynı süreçte sonuçlar LRU belleğinde saklanır.

## Göstergeler ve harita

- **Karşılanan talep:** `sum z_ij / resmi P`. Homojen oranlar nedeniyle başvuru, yatış günü ve nüfus eşdeğeri payı aynıdır. En yakın hastanenin yakın olması tek başına kapsanma değildir.
- **Ortalama süre:** `sum t_ij z_ij / sum z_ij`; yalnız atanan talep. Payda JSON'da bulunur.
- **P90:** her atamanın süresi ve kişi eşdeğeri ağırlığı; atanmamış ve konumsuz nüfus sonsuz süreyle toplam paydada. Sonuç sonsuzsa `null`/`—`.
- **Hekim yükü:** atanan başvuru / hekim başvuru kapasitesi. **Yatak kapasite yükü:** yatış günü / (yatak × 365 × doluluk tavanı). Yüzde 100 kapasite yükü, fiziksel doluluğun seçilen tavana ulaştığını anlatır. Fiziksel doluluk da JSON'da ayrı bulunur.
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

Örnek tesis izi, **45 m yarıçaplı bir dairedir** (yaklaşık 6.362 m² taban alanı). Bu, yola taşmama kontrolü için geometrik bir varsayımdır. 50/150/300 yataklı şablonlarda 12.000/28.000/52.000 m² kapalı alan ve 2/5/9 kat varsayımıyla kat alanı dairenin alanını aşmaz. Mühendislik/imar uygunluğu anlamına gelmez. Büyük parsellerde daha fazla aday ve farklı yapı izi duyarlılığı sonraki aşamadır.

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
