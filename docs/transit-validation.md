# EGO: 291 sonucunun denetimi ve yeni 91 testi · v0.7

23 Ekim 2026 TSİ. İl %95, her ilçe %80, 45 dakika. Nüfus ve 4.701 aday değiştirilmedi. [Kaynak ve model araştırması](transit-research.md).

## Kontrollü karşılaştırma

| Ulaşım modeli | Coğrafi alt sınır | En fazla 91 |
|---|---:|---|
| Önceki v0.3 tarifesiz matris | 291 | Sağlanmıyor |
| Aynı matris + yalnız doğrudan yürüyüş düzeltmesi | 169 | Sağlanmıyor |
| Resmî kalkışlar ve yeni koordinatlar · hafta içi 08.00 | 165 | Bu modelde sağlanmıyor |
| Resmî kalkışlar ve yeni koordinatlar · hafta içi 10.00 | 167 | Bu modelde sağlanmıyor |
| Resmî kalkışlar ve yeni koordinatlar · cumartesi 10.00 | 170 | Bu modelde sağlanmıyor |
| Resmî kalkışlar ve yeni koordinatlar · pazar 10.00 | 168 | Bu modelde sağlanmıyor |

Eski 291 sonucunda doğrudan yürüyüş de 15 dakikada kesiliyordu. 45 dakika senaryosunda daha uzun doğrudan yürüyüşleri geri eklemek, diğer girdiler sabitken sınırı 169'a indirir. Kontrolün eski matrisi değişmez Git commit `d2c5e226484e4aa9af9fe1eec801b18e024c96db` içinden alınır. v0.7, resmî durak koordinatları ve fiziksel süre sınırlarına ek olarak üç uzak düğüm bağlantısını mevcut yol kenarına oturtur ve 216 ek durağı yerel yön/sıra kanıtıyla eşler; 49 dar özel seferi yön ve süre kaynağıyla işler. [Tarihli varsayımlar ve çözülmemiş kayıtlar](service-evidence.md).

Sayılar kapasite, maliyet ve yapı-izi çakışması kaldırılmış, bütün aday/erişim bağlantılarını kullanan coğrafi gevşetmenin kesin minimumlarıdır; alt sınır ve geçerli konum sayısı eşittir. Aynı modelde 91'in yetmemesi gerçek kentte 91'in yetmediğini kanıtlamaz. Eksik hizmet, tahmini ara durak zamanı ve örneklenmiş konumlar nedeniyle bunlar kesin hastane ihtiyacı sayıları değildir.

## İlçe koşulu ve kaynaklar

Hafta içi 10.00'da yalnız ilçe tabanı kaldırılıp il %95 / 45 dakika korununca coğrafi alt sınır **32** olur. Kapasite içermeyen bu tanı 91'in yeterli olduğunu göstermez. Varsayılan ilçe hedefi değişmedi. Sekiz kırsal ilçenin birlikte etkisi, 24 süre/ilçe duyarlılığı ve aynı kapasitenin dört profilde testi [doğrulama raporunda](validation.md) bulunur.

| Kaynak / ağ kontrolü | Sonuç |
|---|---:|
| Resmî katalog yön/varyant | 665 |
| Ağa bağlanan yön/varyant | 430 |
| Kullanılan durak örüntüsü | 545 |
| Konumlandırılan ayrı durak kimliği | 10.811 / 10.811 |
| Güncel resmî Başkentkart otobüs koordinatı | 10.743 |
| OSM ray istasyonu eşlemesi | 68 |
| Eksik koordinat | 0 |
| Yürüyüş ağına 200 m içinde bağlanan durak | 10.730 |
| Kullanılan / yayımlanan hafta içi kalkış | 10.449 / 14.414 (%72,5) |
| Kullanılan / yayımlanan cumartesi kalkış | 8.153 / 10.805 (%75,5) |
| Kullanılan / yayımlanan pazar kalkış | 7.144 / 9.479 (%75,4) |

Kaynak kapsamı yüzdeleri sefer sayısı oranıdır; nüfus/hizmet kalitesi kapsamı değildir. 10.743 durak ham yanıtı bağımsız doğrulandı; 10.740 kaydın gerçek HTTP gözlem zamanı biliniyor, üç eski önbellek kaydında bilinmiyor. Tarife HTML önbelleğinin bilinmeyen gözlem zamanı yeniden işleme tarihiyle doldurulmadı. [Ayrıntılı kalite kaydı](../data/processed/ego-quality.json).

Hakem kontrolünde bazı en yakın yol düğümlerinin karşı taşıt yolunda seçilip gereksiz U dönüşleri oluşturduğu saptandı. 516/616'da incelenen iki bağlantı bu sürümde düzeltildi; 615 ve 560-8 örnekleri belirsiz komşuları nedeniyle bekliyor. 216 ek durağa uygulanan yön/sıra kuralı, 477 aday değişikliği bekletti. Bu kısmi düzeltme bütün ağın doğrulandığı anlamına gelmez. [Eşleştirme ve iki uç kilidi](bus-stop-matching.md).

## Ara durak zamanına duyarlılık

Önceki 543 örüntünün kalkışları korundu, ancak 301 örüntünün tahmini ara durak ofsetleri değişti. 281'i düzeltilmiş geometriyi doğrudan kullanıyor; diğer 20 kısa örüntü, ana hattın toplam süresinin paylaştırılmasından etkileniyor. Dört profilde 45 dakika eşiğini kazanan ve kaybeden aday bağlantıları birlikte görülüyor. Hafta içi 10.00 coğrafi sınırının 166'dan 167'ye çıkması gerçek hastane ihtiyacının arttığı anlamına gelmez.

Denetlenen bir örnekte 611'in 50351 durağındaki tahmini varış 71,20 saniye erkene kaydı. Mahalle temsil noktasından erişim ve 60 saniyelik biniş hazırlığı sonrası yolcu seferi 29,83 saniyeyle kaçırdığı için model yolculuğu 36,32 yerine 75,01 dakika buldu. Terminal kalkışı değişmedi. Bu, resmî ara durak varış saati bulunmamasının sonuçlara etkisini gösteren bir **model izi**; gözlenmiş gerçek bir yolculuk veya ölçülmüş gecikme değildir.

Çözülemeyen özel sefer, bağlantı veya geometri **gerçekte hizmet yok** anlamına gelmez. “Süresi” alanının bütün hatlarda tek yön mü tüm zincir mi olduğu doğrulanmadı; ara durak saatleri bu alanın durak zincirine dağıtılması varsayımını taşır. Başkentray, dolmuş, tarihli istisnalar, canlı gecikme ve araç doluluğu dahil değildir.

## Kapasiteli örnek ve doğrulama

Hafta içi 10.00, sayı serbest: **261 tesis, 27.800 yatak, 23.534 hekim**; ortalama 29,06 dakika, yıllık eşdeğer maliyet 183,93 milyar Aralık 2024 TL. İlk maliyet açıklığı %2,54; son plan maliyet açıklığı %8,69; süre açıklığı %82,02. Maliyet açıklıkları daraltılmış aday bağlantılarına aittir; minimum tesis sayısı değildir. [İlk/son plan ve bütçeli dayanıklılık](validation.md).

Bütün kullanılan kesitlerin fiziksel süre sınırları ve geometri kalite kararları bağımsız tekrar hesaplanır. Dört profil × yedi farklı başlangıç × 4.825 hedef için toplu matris tek-başlangıç yönlendirmesiyle karşılaştırılır. Paket dosyalarının, kodun ve satır/sütun indekslerinin içerik kimlikleri doğrulanır. Bu algoritma/veri tutarlılığı denetimidir; saha ölçümü değildir.

Okuma amaçlı kontroller: `verify_transit.py`, `verify_release.py`, `audit_robustness.py`, `audit_shared_capacity.py`. Tam yeniden üretim sırası [veri sözlüğünde](../data/README.md). [Makine raporu](../data/processed/transit-validation.json), [bağımsız hakem kaydı](nightly-review.md).
