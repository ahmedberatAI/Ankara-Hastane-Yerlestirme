# Veri sözlüğü ve yeniden üretim

`processed/` uygulamanın çalışması için yeterlidir. `raw/` büyük kaynak dosyalarını içerir ve Git’e alınmaz. Kaynak ve çıktı SHA-256 değerleri `processed/manifest.json` içindedir. Dosyaların içindeki tarih, erişim tarihi ile karıştırılmamalıdır: nüfus 31.12.2025, OSM 20.10.2026.

## Hazırlanmış dosyalar

| Dosya                                   | İçerik / birim                                                                                                           |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `population.json`                       | Resmî il/ilçe/mahalle toplamları, kodlar, kaynak notu                                                                    |
| `neighborhood-population-2025.csv`      | 1.427 yayımlanmış mahalle; UTF-8 BOM, kişi                                                                               |
| `dataset.json`                          | Talep noktaları, adaylar, OSM hastaneleri, konumlandırma yöntemleri ve model metaverisi                                  |
| `unmatched-neighborhoods.json`          | Konumu eşleşmeyen yayımlanmış mahalleler ve nedenleri; il–mahalle toplam farkı ayrıca metaveride                         |
| `province.geojson`, `districts.geojson` | Görselleştirme için sadeleştirilmiş OSM sınırları, WGS84                                                                 |
| `roads.geojson`                         | Görsel ana yol katmanı; yönlendirme grafiğinin tamamı değildir                                                           |
| `transit-lines.geojson`                 | OSM ilişki geometrileri; model filtresinden daha geniş görsel katman, aktif hizmet garantisi yok                         |
| `graph-coordinates.npy`                 | Yol grafiği düğümleri: `[boylam,enlem]`, WGS84                                                                           |
| `drive-graph.npz`, `walk-graph.npz`     | SciPy CSR ağları, kenar maliyeti **saniye**                                                                              |
| `car-matrix.npz`, `transit-matrix.npz`  | `minutes` dizisi: satırlar talepler; sütunlar önce adaylar, ardından mevcut hastaneler; **dakika**, bağlantı yoksa `inf` |
| `transit-graph.npz`                     | Durak, araç içi, talep ve varış durum grafiği; saniye                                                                    |
| `transit-details.json.gz`               | Durum düğümleri, biniş/yürüme/araç kenar tipleri, gerçek üye yol geometrileri                                            |
| `quality-report.json`                   | Aday–yol/ray kesişim kontrolü, nüfus ve matris boyutları                                                                 |
| `example-*-result.json`                 | Sürüm hazırlanırken hesaplanan, gerçek çözüm çıktıları; uygulama yerine sabit sonuç göstermez                            |
| `manifest.json`                         | Kaynak/çıktı bütünlük değerleri                                                                                          |

`id` ve `districtId` TÜİK yerleşim kodlarıdır, metin olarak tutulur. `node` ilgili yol grafiğinde sıfır tabanlı satır indeksidir; OSM kimliği değildir. Talep `osmRef` alanı gerçek OSM nesnesini gösterir. Aday kimliğinin `H-` devamı, üretildiği mahallenin kodudur; koordinatı mahalle merkezinin kendisi değildir. `snapMeters` / `accessMeters` varsayılan son erişim bağlantılarıdır. OSM mevcut hastanelerinin kapasite bilgisi doğrulanmamıştır. Yeni tesislerin kapasitesi çözüm çıktısında bulunur.

Nüfus CSV’si ilk çalışma kitabının ilgili alanlarını aktarır. OSM ile coğrafi eşleştirme yalnız `dataset.json` içinde yapılır. Kaynaklarını değiştirmek isteyenler, aynı mahalle/ad sırasını varsaymak yerine kimliklerle birleştirmelidir.

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
.venv\Scripts\python.exe scripts/audit_data.py
.venv\Scripts\python.exe scripts/verify_release.py --write-examples
.venv\Scripts\python.exe scripts/manifest.py
```

İlk indirme Türkiye PBF’si nedeniyle yaklaşık 650 MB’tır; çıkarım ve grafik üretimi birkaç GB RAM kullanabilir. Kaynakların güncel URL’leri değişken içerik sunar: yeniden indirme aynı baytları garanti etmez. İndirilen PBF’nin dosya içi tarihini ve SHA-256 değerini kontrol edin. Tam aynı kesiti tekrarlamak için manifestodaki kaynak dosyalarını muhafaza etmek gerekir; “latest” dosyasını yeniden indirmek eski sürümü yeniden üretmek değildir.

İndirme aracı var olan dosyaları değiştirmez. Yeni sürüm üretirken mevcut `data/raw/` içeriğini kendi arşivinize alın ve ayrı çalışma kopyasında yeniden indirin. `extract_osm.py`, `ankara-region.osm.pbf` varsa bu ara dosyayı yeniden kullanır; farklı Türkiye PBF sürümüyle eski bölge ara dosyasını karıştırmayın. Tam pipeline sonunda **Python sunucusunu yeniden başlatın**, çünkü veri/grafik/çözüm önbellekleri işlem belleğindedir.

`population.py` bu sürümde ADNKS **2025 şemasına** sabittir. Yeni yıl için URL, sayfa adları, sütunlar ve baskılanan kayıt notları kontrol edilerek güncellenmelidir. Yeni yıl varmış gibi otomatik tarih üretmez. Gelecek veri sürümlerinde README’deki nüfus/adetler ve araştırma raporu da yeni manifestoyla birlikte güncellenmelidir.

## Köken ve kapsam

Nüfus ile OSM konumları farklı tarihlere aittir; mahalle bölünmesi/ad değişikliği etkisi bütünüyle giderilmemiştir. Ad eşleşmesi resmî poligon onayı değildir. Model ham kişisel kayıt kullanmaz; yayımlanmış toplu mahalle nüfuslarını işler.

Harita altlığı yalnız görseldir. Sonuçlar canlı harita karolarından hesaplanmaz; sürümlenmiş ağ matrislerinden hesaplanır. Altlık güncellense bile ağ kesiti değişmez. İnternet olmadığında yerel ana yol katmanı destek sağlar; çevrimdışı harita karosu paketi bu repoda yoktur.

## Kapasite parametreleri (v0.3)

`health-planning.json`: resmî il gözlemleri, gerçek hastane örnekleri, giderlerin kaynak kalemleri, türetim katsayıları, bağımsız yatak seçenekleri ve alan varsayımları. `scripts/calibrate_health.py` bu parametreleri kaynak transkripsiyonundan yeniden üretir. Ham dört PDF Git dışında tutulur; `verify_health_sources.py --download` dosya kimliklerini ve metin satırlarını denetler. Görsel kontrol gereken tebliğ sayfasının SHA-256 kimliği korunur. PyMuPDF yalnız kaynak denetimi içindir; uygulama bağımlılığı değildir.

`selected[]`: seçilen yatak tipi, bağımsız tam sayı `doctors`, toplam `grossAreaM2`, `constructionCostTRY`, `annualOperatingCostTRY`, `annualEquivalentCostTRY` ve gider kırılımı. Temas = başvuru + yatış; `contactCapacity` ve `annualContacts` aynı kapsamı kullanır. `capacity.referenceCostTRY` ve `budgetLimitTRY` artık **yıllık eşdeğer maliyet** birimindedir; eski yapım bütçesiyle karıştırılmamalıdır. Fiyat tabanı yaklaşık Aralık 2024 TL.

`assignments[].allocations[]` bölünebilir nüfus eşdeğeri, ağ süresi ve hastane kimliğidir. `candidateId/minutes` en büyük payın rotasıdır. `servedFraction` 0–1, `covered` tam atamayı gösterir. `searchScope` daraltılmış arama kapsamını; `geographicCertificate` tüm adaylarla gerekli konum sayısının alt sınırını bildirir. `inconclusive` çözüm bulunamadığı anlamına gelir, imkânsızlık değildir.

`example-car-91-result.json` ve `example-transit-91-result.json` 91 tesis sınırını test eder. `benchmark-91.json` arayüzdeki sabit karşılaştırma kartıdır; canlı parametrelerden ayrıdır. `example-car-91-university-result.json` ve `sensitivity-results.json` 835 temas/hekim duyarlılığıdır. Örnekler çalışma zamanındaki canlı optimizasyonun yerine oynatılmaz.

`expand_sites.py`, orijinal 1.397 adaya 3.304 büyük yapı izi ekler. Aynı yol girişini ve daha uzun/eşit bağlantıyı kullanır. Transit varış düğümleri çıkışsızdır; eski yürüyüş girişlerinin sürelerine bağlantı farkı eklenir, 15 dakika sınırı tekrar uygulanır, yeni hedeflere Dijkstra çalışır. Daha uzun bağlantı yeni erişim kenarı yaratamayacağı için bu güncelleme aynı ağ varsayımları altında tamdır. Yeniden çalıştırma idempotenttir; yeni kaynak üretiminde önce temel iki ağ betiği çalıştırılmalıdır.

API v0.3 alanı `contactsPerDoctor`, eski `visitsPerDoctor` yerine temas (başvuru + yatış) kapasitesidir. Bilinmeyen girdi alanları sessizce yok sayılmaz; 422 ile reddedilir.
