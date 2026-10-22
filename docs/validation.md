# Doğrulama ve örnek hesaplamalar

22 Ekim 2026 tarihinde hazırlanan veri ve uygulama sürümü. Sayılar kaynak nüfus + işlenmiş ağ + açık model varsayımlarının sonuçlarıdır; saha ölçümü veya yatırım kararı değildir.

## Veri kontrolleri

- 25 ilçenin nüfus toplamı **5.910.320** ile il toplamına eşit.
- Yayımlanmış 1.427 mahalleden **1.413’ü** konumlandırıldı; modellenen nüfus **5.889.804**.
- Konumsuz **20.516 kişi** resmî kapsama paydasında korunuyor.
- **1.397 adayın** tamamının 45 m yarıçaplı izi, OSM karayolu koridorları ve yüzey ray koridorları dışında; adaylar Ankara il sınırında.
- Her iki süre matrisinin boyutu **1.413 × 1.521**: 1.397 aday + 124 mevcut OSM hastanesi.
- Matrislerde negatif süre ve `NaN` yok; erişilemeyen bağlantılar `inf` olarak korunuyor.
- Yol ve yürüyüş grafiğinin ortak düğüm koordinatları WGS84; mesafe hesabı metre tabanlı UTM 36N.

Ham geometriyle aday kontrolleri [quality-report.json](../data/processed/quality-report.json) içinde; dosya kimlikleri [manifest.json](../data/processed/manifest.json) içindedir.

## Gerçek veriyle uçtan uca API kontrolü

| Gösterge                                                 |                                           Araba |                       EGO ağ senaryosu |
| -------------------------------------------------------- | ----------------------------------------------: | -------------------------------------: |
| Süre eşiği                                               |                                           30 dk |                                  45 dk |
| Genel hedef / ilçe tabanı                                |                                       %95 / %80 |                              %95 / %80 |
| Bulunan tesis sayısı                                     |                                              24 |                                    291 |
| Çözüm durumu                                             | Geçerli çözüm; minimum sayı kanıtı tamamlanmadı | Aday havuzunda minimum sayı kanıtlandı |
| Matematiksel alt sınır                                   |                                              22 |                                    291 |
| Sayı için optimalite açığı                               |                                           %8,33 |                                     %0 |
| Eşik içinde kapsama                                      |                                         %98,197 |                                %95,066 |
| Kapsanan nüfus                                           |                                       5.803.762 |                              5.618.712 |
| Sonlu süresi hesaplanan nüfusla ağırlıklı ortalama       |                                        21,08 dk |                               21,09 dk |
| Toplam nüfus üzerinden P90                               |                                        28,07 dk |                               38,90 dk |
| Konumsuz veya seçilen tesislere ağdan erişilemeyen nüfus |                                          20.516 |                                262.989 |

Bu koşuların çıktıları [araba](../data/processed/example-car-result.json), [EGO senaryosu](../data/processed/example-transit-result.json) ve [doğrulama özeti](../data/processed/validation-results.json) olarak kaydedildi. UI her yeni parametre için API hesaplamasını kullanır; bu dosyaları sabit sonuç gibi oynatmaz. Süre sınırı nedeniyle başka donanımda ikincil konum/süre veya ispat durumu değişebilir.

**291, Ankara için gerçek yatırım önerisi değildir.** Tarifesiz OSM hizmet varsayımı, eksik hat/durak kapsamı, 15 dakikalık ilk/son yürüme sınırı, tek mahalle noktası, aday örneklemesi ve ilçe erişim tabanı bu sonucu etkiler. Küçük kırsal yerleşimler için yürüme/hat bağlantısı yoksa model yakında ayrı bir tesis gerektirebilir. Resmî GTFS, daha ayrıntılı talep ve kapasiteyle sonuç yeniden hesaplanmalıdır. Ayrıca iki sütunun süre eşikleri farklıdır; sayıları tek başına eşdeğer ulaşım performansı karşılaştırması olarak okumayın.

Araba rotasında **Ahmetadil → Çiftlikköy**, EGO örneğinde **Atıfbey → Kavacık Subayevleri** ve **M4 / Dışkapı** binişi doğrulandı. API’den dönen süreler matris/atama süreleriyle 0,001 dakika toleransında uyuşuyor; araba rotasında yol, EGO rotasında gerçek ray/yol üye geometrileri var.

## Otomatik testler

`python -m pytest -q`: **11 test geçti**. Küçük örnekte tüm kombinasyonlarla minimum sayı karşılaştırması, kırsal ilçe tabanı, bilinmeyen nüfusun paydası, sonsuz erişim süresi, nüfus ağırlıklı P90, kapsama koruyan iyileştirme, Türkçe ad/erişim etiketleri, aday alt küme elemesinin güvenliği, yönlü yol geri kurma, API parametre sınırları ve katman erişim listesi kontrol edildi.

`npm run build`: TypeScript denetimi ve Vite üretim derlemesi başarılı.

`python scripts/verify_release.py --write-examples`: her iki modun çözüm/güzergâh uçları, il/ilçe toplamları, kapsama kısıtları, matris boyutları ve değerleri başarılı. `python scripts/audit_data.py`: yol/ray taşması **0**.

Test ortamında Starlette/AnyIO bağımlılığından bir kullanımdan kaldırma uyarısı görülüyor; test başarısızlığı yok. Docker dosyası hazırlandı, fakat yerel Docker daemon’u çalışmadığı için konteyner çalıştırması doğrulanmadı.

## Arayüz kontrolü

Derlenmiş uygulama FastAPI üzerinden `127.0.0.1:8000` adresinde tarayıcıda kontrol edildi. Mahalle araması, rota çizimi, iki mod, hedef kontrolleri, model açıklaması, kaynak kataloğu, ilçe sonuçları ve mevcut hastane katmanı inceleme kapsamındadır. 390 px genişlikte gömülü mobil görünüm ayrıca incelendi; bu, gerçek cihaz veya bütün tarayıcılar üzerinde test iddiası değildir. Görseller `docs/screenshots/` altındadır.

Harita altlığı haricî OSM karo servisine bağlıdır; servis erişilemezse yerel ana yol katmanı açılır. Hesaplanan süreler harita karolarından türetilmez. EGO varsayımları, optimalite kanıtı ve eksik nüfus arayüzde görünür tutulur.

Tarayıcıdan indirilen EGO JSON dosyasında 291 tesis, 19 kaynak, parametreler ve dışa aktarma zamanı doğrulandı. Parametre değişiminde indirme düğmesi devre dışı kaldı. %100 kapsama denemesi, %97,9 model üst sınırını göstererek çözümsüz döndü. Mevcut hastane katmanında 124 işaret ve ilçe panelinde 25 sonuç kontrol edildi. Konsolda uygulama hatası gözlenmedi.

OSM çıkarımı, Windows kapanış sorununu gideren osmium 4.3.0 ile yeniden çalıştırıldı; açılmış JSON içeriği önceki veriyle SHA-256 düzeyinde aynı ve süreç normal sonlandı.
