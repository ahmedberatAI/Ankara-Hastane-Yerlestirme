# EGO: 291 sonucunun denetimi ve yeni 91 testi · v0.6

23 Ekim 2026 TSİ. İl %95, her ilçe %80, 45 dakika. Nüfus ve 4.701 aday değiştirilmedi. [Kaynak ve model araştırması](transit-research.md).

## Kontrollü karşılaştırma

| Ulaşım modeli | Coğrafi alt sınır | En fazla 91 |
|---|---:|---|
| Önceki v0.3 tarifesiz matris | 291 | Sağlanmıyor |
| Aynı matris + yalnız doğrudan yürüyüş düzeltmesi | 169 | Sağlanmıyor |
| Resmî kalkışlar ve yeni koordinatlar · hafta içi 08.00 | 165 | Bu modelde sağlanmıyor |
| Resmî kalkışlar ve yeni koordinatlar · hafta içi 10.00 | 166 | Bu modelde sağlanmıyor |
| Resmî kalkışlar ve yeni koordinatlar · cumartesi 10.00 | 170 | Bu modelde sağlanmıyor |
| Resmî kalkışlar ve yeni koordinatlar · pazar 10.00 | 168 | Bu modelde sağlanmıyor |

Eski 291 sonucunda doğrudan yürüyüş de 15 dakikada kesiliyordu. 45 dakika senaryosunda daha uzun doğrudan yürüyüşleri geri eklemek, diğer girdiler sabitken sınırı 169'a indirir. Kontrolün eski matrisi değişmez Git commit `d2c5e226484e4aa9af9fe1eec801b18e024c96db` içinden alınır. v0.6, resmî durak koordinatları ve fiziksel süre sınırlarına ek olarak üç uzak düğüm bağlantısını mevcut yol kenarına oturtur; 24 dar özel seferi yön ve süre kaynağıyla işler. [Tarihli varsayımlar ve çözülmemiş kayıtlar](service-evidence.md).

Sayılar kapasite, maliyet ve yapı-izi çakışması kaldırılmış, bütün aday/erişim bağlantılarını kullanan coğrafi gevşetmenin kesin minimumlarıdır; alt sınır ve geçerli konum sayısı eşittir. Aynı modelde 91'in yetmemesi gerçek kentte 91'in yetmediğini kanıtlamaz. Eksik hizmet, tahmini ara durak zamanı ve örneklenmiş konumlar nedeniyle bunlar kesin hastane ihtiyacı sayıları değildir.

## İlçe koşulu ve kaynaklar

Hafta içi 10.00'da yalnız ilçe tabanı kaldırılıp il %95 / 45 dakika korununca coğrafi alt sınır **31** olur. Kapasite içermeyen bu tanı 91'in yeterli olduğunu göstermez. Varsayılan ilçe hedefi değişmedi. Sekiz kırsal ilçenin birlikte etkisi, 24 süre/ilçe duyarlılığı ve aynı kapasitenin dört profilde testi [doğrulama raporunda](validation.md) bulunur.

| Kaynak / ağ kontrolü | Sonuç |
|---|---:|
| Resmî katalog yön/varyant | 665 |
| Ağa bağlanan yön/varyant | 428 |
| Kullanılan durak örüntüsü | 543 |
| Konumlandırılan ayrı durak kimliği | 10.811 / 10.811 |
| Güncel resmî Başkentkart otobüs koordinatı | 10.743 |
| OSM ray istasyonu eşlemesi | 68 |
| Eksik koordinat | 0 |
| Yürüyüş ağına 200 m içinde bağlanan durak | 10.730 |
| Kullanılan / yayımlanan hafta içi kalkış | 10.437 / 14.414 (%72,4) |
| Kullanılan / yayımlanan cumartesi kalkış | 8.143 / 10.805 (%75,4) |
| Kullanılan / yayımlanan pazar kalkış | 7.136 / 9.479 (%75,3) |

Kaynak kapsamı yüzdeleri sefer sayısı oranıdır; nüfus/hizmet kalitesi kapsamı değildir. 10.743 durak ham yanıtı bağımsız doğrulandı; 10.740 kaydın gerçek HTTP gözlem zamanı biliniyor, üç eski önbellek kaydında bilinmiyor. Tarife HTML önbelleğinin bilinmeyen gözlem zamanı yeniden işleme tarihiyle doldurulmadı. [Ayrıntılı kalite kaydı](../data/processed/ego-quality.json).

Hakem kontrolünde açık bir yol eşleştirme hatası saptandı: 615, 560-8 ve 516/616 örneklerinde en yakın düğüm karşı taşıt yolunda seçildiği için gereksiz U dönüşleri oluşuyor. Yönlü yol kenarına bağlantının tüm ağda düzeltilmesi bekliyor; bu durum süreleri uzatabilir. Mevcut paket bu bilinen sınırlamayla yayımlanıyor.

Çözülemeyen özel sefer, bağlantı veya geometri **gerçekte hizmet yok** anlamına gelmez. “Süresi” alanının bütün hatlarda tek yön mü tüm zincir mi olduğu doğrulanmadı; ara durak saatleri bu alanın durak zincirine dağıtılması varsayımını taşır. Başkentray, dolmuş, tarihli istisnalar, canlı gecikme ve araç doluluğu dahil değildir.

## Kapasiteli örnek ve doğrulama

Hafta içi 10.00, sayı serbest: **209 tesis, 24.950 yatak, 22.966 hekim**; ortalama 27,87 dakika, yıllık eşdeğer maliyet 172,67 milyar Aralık 2024 TL. İlk maliyet açıklığı %2,76; son plan maliyet açıklığı %2,75; süre açıklığı %80,79. Maliyet açıklıkları daraltılmış aday bağlantılarına aittir; minimum tesis sayısı değildir. [İlk/son plan ve bütçeli dayanıklılık](validation.md).

Bütün kullanılan kesitlerin fiziksel süre sınırları ve geometri kalite kararları bağımsız tekrar hesaplanır. Dört profil × sekiz başlangıç × 4.825 hedef için toplu matris tek-başlangıç yönlendirmesiyle karşılaştırılır. Paket dosyalarının, kodun ve satır/sütun indekslerinin içerik kimlikleri doğrulanır. Bu algoritma/veri tutarlılığı denetimidir; saha ölçümü değildir.

Okuma amaçlı kontroller: `verify_transit.py`, `verify_release.py`, `audit_robustness.py`, `audit_shared_capacity.py`. Tam yeniden üretim sırası [veri sözlüğünde](../data/README.md). [Makine raporu](../data/processed/transit-validation.json), [bağımsız hakem kaydı](nightly-review.md).
