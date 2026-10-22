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

`id` ve `districtId` TÜİK yerleşim kodlarıdır, metin olarak tutulur. `node` ilgili yol grafiğinde sıfır tabanlı satır indeksidir; OSM kimliği değildir. Talep `osmRef` alanı gerçek OSM nesnesini gösterir. Aday kimliğinin `H-` devamı, üretildiği mahallenin kodudur; koordinatı mahalle merkezinin kendisi değildir. `snapMeters` / `accessMeters` varsayılan son erişim bağlantılarıdır. Kapasite bilgisi yoktur.

Nüfus CSV’si ilk çalışma kitabının ilgili alanlarını aktarır. OSM ile coğrafi eşleştirme yalnız `dataset.json` içinde yapılır. Kaynaklarını değiştirmek isteyenler, aynı mahalle/ad sırasını varsaymak yerine kimliklerle birleştirmelidir.

## Veriyi yeniden oluşturma

Repo kökünde, Python bağımlılıkları kurulduktan sonra:

```powershell
.venv\Scripts\python.exe scripts/download_sources.py
.venv\Scripts\python.exe scripts/population.py
.venv\Scripts\python.exe scripts/extract_osm.py
.venv\Scripts\python.exe scripts/build_dataset.py
.venv\Scripts\python.exe scripts/build_transit.py
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
