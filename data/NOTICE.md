# Veri atıf ve yeniden kullanım notları

- **TÜİK, Adrese Dayalı Nüfus Kayıt Sistemi 2025:** kaynak çalışma kitabı ve kaynak notları `population.json` ile `docs/sources.json` içinde belirtilmiştir. [TÜİK yasal uyarısı](https://www.tuik.gov.tr/Kurumsal/Yasal_Uyari) kaynak gösterilerek yeniden kullanım koşullarını açıklar. TÜİK bu modelin sonuçlarını onaylamış değildir.
- **© OpenStreetMap contributors:** yollar, yürüyüş bağlantıları, idari sınırlar, mahalle konumları, toplu taşıma ilişkileri ve mevcut hastane katmanı OSM kaynaklıdır. [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) / [OSM telif sayfası](https://www.openstreetmap.org/copyright). OSM kaynaklı türetilmiş veritabanı ve matrisler bu koşullarla paylaşılır; yeniden dağıtımda kaynak atfı ve ilgili paylaşım koşulları korunmalıdır. Nüfus tablolarının bağımsız kaynak koşulları ayrıca geçerlidir.
- **Geofabrik:** Türkiye PBF veri kesiti sağlayıcısıdır; verinin temel kaynağı OpenStreetMap’tir. [İndirme sayfası](https://download.geofabrik.de/europe/turkey.html).
- **EGO / ABB / Sağlık Bakanlığı:** kaynak araştırmasında kullanılan bağlantılar kurumlara aittir. Resmî GTFS, resmî mahalle poligonları bu repoya aktarılmış değildir. Sağlık Bakanlığı 2024 il toplamları artık sağlık planlama parametrelerine alınmıştır; resmî tesis bazında kapasite envanteri değildir. OSM senaryosu resmî kurum çıktısı olarak sunulmaz.
- Harita altlığı `tile.openstreetmap.org` kullanır. Kamusal yoğun trafikle dağıtımda [OSM karo kullanım politikası](https://operations.osmfoundation.org/policies/tiles/) incelenmeli; toplu indirme, ön yükleme veya çevrimdışı karo kazıma yapılmamalıdır. Bu uygulama yalnız görünür harita alanı için standart Leaflet istekleri yapar.

Bu dosya uygulama koduna ayrıca bir lisans atamaz. Bağımlılıkların lisansları kendi paketlerinde geçerlidir.

- **2026 yapı bedelleri:** Resmî Gazete 33157 tebliğinin TÜRMOB nüshası. Kaynak, sınıf ve fiyat yılı health-planning.json içinde; kapalı alan ve kadro şablonları proje varsayımıdır.
