# Veri sözlüğü ve yeniden üretim

`processed/` uygulamanın çalışması için yeterlidir. `raw/` büyük kaynak dosyalarını ve ham HTTP yanıtlarını içerir; Git’e alınmaz. Hazırlanmış dosyaların ve ana kaynakların SHA-256 değerleri `processed/manifest.json` içindedir. EGO’nun tekil ham yanıt kimlikleri ayrıca ilgili `rawSources` listelerindedir. Nüfusun referans tarihi 31.12.2025, OSM kesiti 20.10.2026’dır. HTTP gözlem zamanı (`observedAt`), yeniden işleme zamanı (`processedAt`) ve kaynağın geçerlilik tarihi birbirinin yerine kullanılamaz.

## Hazırlanmış dosyalar

| Dosya                                   | İçerik / birim                                                                                                           |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `population.json`                       | Resmî il/ilçe/mahalle toplamları, kodlar, kaynak notu                                                                    |
| `neighborhood-population-2025.csv`      | 1.427 yayımlanmış mahalle; UTF-8 BOM, kişi                                                                               |
| `dataset.json`                          | Talep noktaları, adaylar, OSM hastaneleri, konumlandırma yöntemleri ve model metaverisi                                  |
| `unmatched-neighborhoods.json`          | Konumu eşleşmeyen yayımlanmış mahalleler ve nedenleri; il–mahalle toplam farkı ayrıca metaveride                         |
| `province.geojson`, `districts.geojson` | Görselleştirme için sadeleştirilmiş OSM sınırları, WGS84                                                                 |
| `roads.geojson`                         | Görsel ana yol katmanı; yönlendirme grafiğinin tamamı değildir                                                           |
| `transit-lines.geojson`                 | Kullanılabilen resmî hatlar arasında OSM üzerinde modellenmiş geometri; görsel sadeleştirme uygulanır                         |
| `graph-coordinates.npy`                 | Yol grafiği düğümleri: `[boylam,enlem]`, WGS84                                                                           |
| `drive-graph.npz`, `walk-graph.npz`     | SciPy CSR ağları, kenar maliyeti **saniye**                                                                              |
| `car-matrix.npz`, `transit-matrix.npz`  | `minutes` dizisi: satırlar talepler; sütunlar önce adaylar, ardından mevcut hastaneler; **dakika**, bağlantı yoksa `inf` |
| `quality-report.json`                   | Aday–yol/ray kesişim kontrolü, nüfus ve matris boyutları                                                                 |
| `example-*-result.json`                 | Sürüm hazırlanırken hesaplanan, gerçek çözüm çıktıları; uygulama yerine sabit sonuç göstermez                            |
| `manifest.json`                         | Kaynak/çıktı bütünlük değerleri                                                                                          |

`id` ve `districtId` TÜİK yerleşim kodlarıdır, metin olarak tutulur. `node` ilgili yol grafiğinde sıfır tabanlı satır indeksidir; OSM kimliği değildir. Talep `osmRef` alanı gerçek OSM nesnesini gösterir. Aday kimliğinin `H-` devamı, üretildiği mahallenin kodudur; koordinatı mahalle merkezinin kendisi değildir. `snapMeters` / `accessMeters` varsayılan son erişim bağlantılarıdır. OSM mevcut hastanelerinin kapasite bilgisi doğrulanmamıştır. Yeni tesislerin kapasitesi çözüm çıktısında bulunur.

Nüfus CSV’si ilk çalışma kitabının ilgili alanlarını aktarır. OSM ile coğrafi eşleştirme yalnız `dataset.json` içinde yapılır. Kaynaklarını değiştirmek isteyenler, aynı mahalle/ad sırasını varsaymak yerine kimliklerle birleştirmelidir.

## EGO v0.5 dosyaları ve kaynak zamanı

- `ego-official.json`: 665 resmî yön/varyant, üç normal gün türünün kalkışları/notları ve durak sırası; 666 ham HTML kimliği. 23 Ekim’deki önbellek işlemesi yeni HTTP erişimi değildir: bu 666 eski kaydın gözlem zamanı bilinmiyor, `observedAt` ve `retrievedAt` null tutuluyor. `processedAt` işlemenin zamanıdır; `sourceSnapshotId` kaynak dosya/URL/SHA kimliklerinden üretilir.
- `ego-stop-coordinates.json`: resmî Başkentkart sorgusundan 10.743 sayısal katalog kimliğinin tamamı; ham yanıt SHA, durak kimliği, istek ve kaynak bilgisi. 10.740 `observedAt` değeri yanıtın SHA+kimlik+endpoint sidecar kaydına bağlıdır. `11535`, `14162`, `14163` eski önbellek olduğundan zamanı bilinmez ve null kalır. Bilinen HTTP gözlemleri 22 Ekim 23.02–23 Ekim 00.24 TSİ aralığındadır. Katalogdaki 68 sayısal olmayan durak kimliği bu sayısal sorgu kesitine dahil değildir.
- `ego-network.json.gz`: 424 kullanılan yön/varyant, 537 sefer örüntüsü, koordinat kökeni, tahmini ara durak zamanları ve ağ güzergâhları. 10.811 katalog kimliğinin 10.743 koordinatı resmî sorgudan, 68’i OSM istasyon eşleşmesinden gelir; tarihsel ek kullanılmamıştır. Ara durak zamanları ölçülmüş veri değildir; bütün kimliklerin koordinatlı olması bütün seferlerin kullanılabildiğini göstermez.
- `ego-access.npz`, `ego-egress.npz`, `ego-transfers.npz`, `ego-direct.npz`: seyrek yürüme bağlantıları; saniye. CSR'de **olmayan giriş sıfır süre değil, bağlantı yok** anlamındadır.
- `transit-{weekday-0800,weekday-1000,saturday-1000,sunday-1000}-matrix.npz`: gün/başlangıç saati başına dakika matrisi. 120 dakika üzeri `inf`. `transit-matrix.npz` varsayılan hafta içi 10.00 kopyasıdır.
- `ego-quality.json`: kullanılan/yayımlanan seferler, koordinat kökenleri, adres/mesafe tutarsızlıkları, dışlanan hatlar ve gerekçeler, çözülemeyen özel seferlerin sütun/not saatleri, segment süre alt sınırları. Eksik/dışlanan hizmet, gerçek hizmetin yokluğu değildir.
- `transit-package.json`: ulaşım kodu, resmî kaynak kesitleri, ağ/geometri, yürüme bağlantıları, dört profil matrisi ve talep/aday/hastane/ilçe indekslerinin sırasını bağlayan `transitPackageId`. Yalnız bütün matrisler tamamlandıktan sonra yazılır. Kimlik, kendi `builtAt` alanını dışlar; diğer kaynak metaverileri dahil hazırlanan dosyaların tam baytlarını kapsar. Kod satır sonları Windows/Linux farkı için normalleştirilir, veri dosyaları normalleştirilmez.
- `transit-validation.json`: 291 tekrar üretimi, yalnız yürüyüş düzeltmesi, dört 91 testi, ilçe tabanı duyarlılığı ve bağımsız rota kontrolleri.
- `example-transit-*-91-result.json`: dört zaman profiline ait **en fazla 91** deneyi çıktıları; tam 91 açmak zorunlu değildir. Varsayılan profilin `example-transit-91-result.json` kopyası da doğrulanır.
- `robustness-results.json`: kaydedilmiş `example-transit-result.json` planının konum/yatak/hekim sayıları ve aynı yıllık eşdeğer bütçesi korunarak dört profilde yeniden talep ataması. Kaynak planın SHA’sı, sağlık kalibrasyonu, model kodları ve ulaşım paketi bağlanır. Ayrı coğrafi duyarlılık bölümü kapasite/maliyet/çakışma kısıtlarını kaldırır; sabit plan testiyle karıştırılmamalıdır.

API sonuçlarındaki `metadata.transitPackageId` ve EGO için `transitEvidence.packageId` güncel paketle eşleşmelidir. Arayüzde kayıtlı karşılaştırmalar ve sabit plan testi başka pakete aitse eski sayılar güncel sonuç gibi gösterilmez. Bu bağ bütünlüğü doğrular; sahadaki yolculuk süresinin doğruluğunu kanıtlamaz.

Koordinat önceliği resmî Başkentkart sorgusu → OSM → eksik otobüs kimliğinde tarihsel topluluk ekidir. Bu kaynakların aynı hizmet tarihinde geçerli olduğu varsayılmaz. Resmî HTTP sorgusundan gelmek, koordinatın sahada doğrulandığı anlamına gelmez.

Uygulama eski `transit-graph.npz` ve `transit-details.json.gz` dosyalarını artık kullanmaz. Önceki sürüm Git geçmişindeki `d2c5e22` commit'inde korunur. `build_transit.py` bu dosyaları yalnız eski model/temel aday büyütme ara adımı için üretir; güncel EGO modelini üretmek için aşağıdaki `build_timetable.py` adımı zorunludur.

## Veriyi yeniden oluşturma

Repo kökünde, Python bağımlılıkları kurulduktan sonra:

```powershell
.venv\Scripts\python.exe scripts/download_sources.py
.venv\Scripts\python.exe scripts/population.py
.venv\Scripts\python.exe scripts/extract_osm.py
.venv\Scripts\python.exe scripts/build_dataset.py
.venv\Scripts\python.exe scripts/build_transit.py
.venv\Scripts\python.exe scripts/expand_sites.py
.venv\Scripts\python.exe scripts/calibrate_health.py
.venv\Scripts\python.exe scripts/fetch_ego.py
.venv\Scripts\python.exe scripts/fetch_ego_stops.py
.venv\Scripts\python.exe scripts/build_timetable.py
.venv\Scripts\python.exe scripts/verify_transit.py --write
.venv\Scripts\python.exe scripts/audit_data.py
.venv\Scripts\python.exe scripts/verify_release.py --write-examples
.venv\Scripts\python.exe scripts/audit_robustness.py --write
.venv\Scripts\python.exe scripts/manifest.py
.venv\Scripts\python.exe scripts/transit_provenance.py
.venv\Scripts\python.exe scripts/verify_transit.py
.venv\Scripts\python.exe scripts/verify_release.py
.venv\Scripts\python.exe scripts/audit_robustness.py
```

Son dört komut salt okunur doğrulamadır. `verify_release.py --write-examples`, araba/EGO, 91 sınırı ve hekim duyarlılığı dahil kayıtlı çözüm örneklerini yeniden hesaplar; `--write-report` tek başına eski planları yenilemez. Sabit plan testi en son kaydedilen planın ardından, manifesto da bütün çıktıların ardından üretilir. `audit_robustness.py --profiles-only` yalnız mevcut raporun dört sabit plan profilini yeniden çözen daha kısa denetimdir; bütün coğrafi duyarlılık ızgarasını yeniden çözmez ve yazma seçeneğiyle birleştirilemez.

`verify_transit.py` tarihsel 291 karşılaştırmasını Git’teki tam `d2c5e226484e4aa9af9fe1eec801b18e024c96db` kaydından okur. Sığ klonda bu geçmiş indirilmelidir. Nüfus veya adayların kimliği/sırası değişmişse eski matrisi yeni satır/sütunlarla eşleştirmeyi reddeder; böyle bir sürümde eski 291 kıyası aynı kontrollü deney olarak sürdürülemez.

İlk indirme Türkiye PBF’si nedeniyle yaklaşık 650 MB’tır; çıkarım ve grafik üretimi birkaç GB RAM kullanabilir. Kaynakların güncel URL’leri değişken içerik sunar: yeniden indirme aynı baytları garanti etmez. İndirilen PBF’nin dosya içi tarihini ve SHA-256 değerini kontrol edin. Tam aynı kesiti tekrarlamak için manifestodaki kaynak dosyalarını muhafaza etmek gerekir; “latest” dosyasını yeniden indirmek eski sürümü yeniden üretmek değildir.

Genel indirme aracı var olan dosyaları değiştirmez. Yeni sürüm üretirken mevcut `data/raw/` içeriğini kendi arşivinize alın ve ayrı çalışma kopyasında yeniden indirin. `extract_osm.py`, `ankara-region.osm.pbf` varsa bu ara dosyayı yeniden kullanır; farklı Türkiye PBF sürümüyle eski bölge ara dosyasını karıştırmayın. Tam pipeline sonunda **Python sunucusunu yeniden başlatın**, çünkü veri/grafik/çözüm önbellekleri işlem belleğindedir.

EGO betikleri normal çalışmada önbelleği korur. `fetch_ego.py --refresh` bütün tarife sayfalarını; `fetch_ego_stops.py --refresh` seçili bütün durakları yeniden sorgular. `fetch_ego_stops.py --retry-unavailable` yalnız önbellekte boş kalmış yanıtları tekrar ister; HTTP 200/boş yanıt gerçek durak yokluğu diye kaydedilmez. Bozuk önbellek yanıtı gerçek HTTP ile yeniden denenir. Yeni gözlemin sidecar kaydı yanıtın SHA’sına bağlanır; dosya kopyalama/değiştirme zamanı gözlem tarihi yapılmaz.

`build_timetable.py` yolculuk örüntüleri ve bütün profil matrisleri tamamlanmadan yeni paket kimliği yazmaz. `--network-only` sonrasında matrisler ve paket için `--matrices-only` çalıştırılmalıdır. Yürüme önbelleği girdi kimliği yanında dört gerçek çıktı dosyasının SHA’sını da sınar; eski işaret dosyasını geri getirmek başka girdilerle üretilmiş çıktıları geçerli kılmaz. Ara üretimler veya başarısız doğrulama sonrasında yeni kaynakları eski sonuçlarla birlikte yayımlamayın.

`population.py` bu sürümde ADNKS **2025 şemasına** sabittir. Yeni yıl için URL, sayfa adları, sütunlar ve baskılanan kayıt notları kontrol edilerek güncellenmelidir. Yeni yıl varmış gibi otomatik tarih üretmez. Gelecek veri sürümlerinde README’deki nüfus/adetler ve araştırma raporu da yeni manifestoyla birlikte güncellenmelidir.

## Köken ve kapsam

Nüfus ile OSM konumları farklı tarihlere aittir; mahalle bölünmesi/ad değişikliği etkisi bütünüyle giderilmemiştir. Ad eşleşmesi resmî poligon onayı değildir. Model ham kişisel kayıt kullanmaz; yayımlanmış toplu mahalle nüfuslarını işler.

Harita altlığı yalnız görseldir. Sonuçlar canlı harita karolarından hesaplanmaz; sürümlenmiş ağ matrislerinden hesaplanır. Altlık güncellense bile ağ kesiti değişmez. İnternet olmadığında yerel ana yol katmanı destek sağlar; çevrimdışı harita karosu paketi bu repoda yoktur.

## Kapasite parametreleri (v0.3)

`health-planning.json`: resmî il gözlemleri, gerçek hastane örnekleri, giderlerin kaynak kalemleri, türetim katsayıları, bağımsız yatak seçenekleri ve alan varsayımları. `scripts/calibrate_health.py` bu parametreleri kaynak transkripsiyonundan yeniden üretir. Ham dört PDF Git dışında tutulur; `verify_health_sources.py --download` dosya kimliklerini ve metin satırlarını denetler. Görsel kontrol gereken tebliğ sayfasının SHA-256 kimliği korunur. PyMuPDF yalnız kaynak denetimi içindir; uygulama bağımlılığı değildir.

`selected[]`: seçilen yatak tipi, bağımsız tam sayı `doctors`, toplam `grossAreaM2`, `constructionCostTRY`, `annualOperatingCostTRY`, `annualEquivalentCostTRY` ve gider kırılımı. Temas = başvuru + yatış; `contactCapacity` ve `annualContacts` aynı kapsamı kullanır. `capacity.referenceCostTRY` ve `budgetLimitTRY` artık **yıllık eşdeğer maliyet** birimindedir; eski yapım bütçesiyle karıştırılmamalıdır. Fiyat tabanı yaklaşık Aralık 2024 TL.

`assignments[].allocations[]` bölünebilir nüfus eşdeğeri, ağ süresi ve hastane kimliğidir. `candidateId/minutes` en büyük payın rotasıdır. `servedFraction` 0–1, `covered` tam atamayı gösterir. `searchScope` daraltılmış arama kapsamını; `geographicCertificate` tüm adaylarla gerekli konum sayısının alt sınırını bildirir. `inconclusive` çözüm bulunamadığı anlamına gelir, imkânsızlık değildir.

`capacity.referenceStage` ilk maliyet aşamasının tesis/yatak/hekim/atama/süre/maliyet değerlerini korur. `costStageGap` ve sonuç kökündeki `gap` bu ilk aşamaya aittir; `finalPlanCostGap` son planın aynı maliyet alt sınırına göre açıklığıdır. `travelStageGap` son dönen akışın ayrı süre amacına aittir. `optimalityScope`, daraltılmış bağlantı aramasını bütün örneklenmiş aday bağlantılarından ayırır; ikisi de sürekli Ankara coğrafyası veya minimum hastane sayısı iddiası değildir. `resourceCleanup.applied` ve varsa `numericalFallback`, kaynak düzenlemesi ile sayısal doğrulama için önceki geçerli plana dönüşü açıklar.

`example-car-91-result.json` ve `example-transit-91-result.json` 91 tesis sınırını test eder. `benchmark-91.json` arayüzdeki sabit karşılaştırma kartıdır; canlı parametrelerden ayrıdır. `example-car-91-university-result.json` ve `sensitivity-results.json` 835 temas/hekim duyarlılığıdır. Örnekler çalışma zamanındaki canlı optimizasyonun yerine oynatılmaz.

`expand_sites.py`, orijinal 1.397 adaya 3.304 büyük yapı izi ekler. Aynı yol girişini ve daha uzun/eşit bağlantıyı kullanır. Eski tarifesiz ara ağın varış düğümleri çıkışsızdır; yürüyüş girişlerine bağlantı farkı eklenir, 15 dakika erişim sınırı tekrar uygulanır, yeni hedeflere Dijkstra çalışır. Bu işlem yalnız aday büyütme ara aşamasıdır; son EGO yürüme bağlantıları ve bütün profil matrisleri `build_timetable.py` ile yeniden üretilir. Son modelde doğrudan yürüyüş 15 dakikada kesilmez. Yeniden çalıştırma idempotenttir; yeni kaynak üretiminde önce temel iki ağ betiği çalıştırılmalıdır.

API v0.3 alanı `contactsPerDoctor`, eski `visitsPerDoctor` yerine temas (başvuru + yatış) kapasitesidir. Bilinmeyen girdi alanları sessizce yok sayılmaz; 422 ile reddedilir.

Yalnız tarife/koordinat güncellemesinde de kaynak betiklerinden sonraki zincir bütünüyle çalışır: `build_timetable.py` → `verify_transit.py --write` → `audit_data.py` → `verify_release.py --write-examples` → `audit_robustness.py --write` → `manifest.py`, ardından salt okunur denetimler. Bütün ham kaynakların değişmesi gerekmez: aynı nüfusla yeni tarife de eski çözümü ve sabit plan raporunu geçersiz kılabilir. API’de `transitProfile` dört izinli profilden birini seçer; varsayılan `weekday-1000`. Normal gün türleri tarihli tatil/istisna takvimi değildir.
