# EGO: 291 sonucunun denetimi ve yeni 91 testi · v0.4

22 Ekim 2026. İl %95, her ilçe %80, 45 dakika. Nüfus, 4.701 aday, yatak/hekim talebi ve maliyet varsayımları değiştirilmedi. Kaynak ve algoritma ayrıntıları: [araştırma](transit-research.md).

## Kontrollü karşılaştırma

| Ulaşım modeli | Coğrafi alt sınır | En fazla 91 |
|---|---:|---|
| Önceki v0.3 tarifesiz matris | 291 | Sağlanmıyor |
| Aynı matris + yalnız doğrudan yürüyüş düzeltmesi | 169 | Sağlanmıyor |
| Resmî kalkışlar, hafta içi 08.00 | 166 | Bu veriyle sağlanmıyor |
| Resmî kalkışlar, hafta içi 10.00 | 171 | Bu veriyle sağlanmıyor |
| Resmî kalkışlar, cumartesi 10.00 | 171 | Bu veriyle sağlanmıyor |
| Resmî kalkışlar, pazar 10.00 | 170 | Bu veriyle sağlanmıyor |

**291 sonucunda bir model hatası vardı:** sadece yürüyerek ulaşılabilen yolculuklar da 15 dakikada kesiliyordu. İlk/son durak yürüyüşünün sınırı, doğrudan yürüyüşün toplam sınırı olarak uygulanamaz. 45 dakikalık senaryoda 20–45 dakikalık doğrudan yürüyüşleri geri eklemek, diğer her şeyi sabit tutunca 291’i 169’a indiriyor. Yeni model bu hatayı giderir; sabit bekleme yerine gün türüne ve başlangıç saatine göre ilk yetişilebilir seferi kullanır.

Tablodaki sayılar **kapasite, maliyet ve yapı-izi çakışmaları kaldırıldığında gereken asgari coğrafi konum sayılarıdır**. Tam aday/erişim bağlantıları kullanılır; alt sınır ile geçerli konum sayısı eşit, çözücü açıklığı sıfırdır. Yatak/hekim ve maliyet eklemek bu gerekli koşulu iyileştiremez. Dolayısıyla aynı veri, adaylar, saat ve hedeflerle 91 mümkün değildir. Bunlar gerçek Ankara’nın ihtiyaç duyduğu hastane sayıları değildir; eksik seferler/konumlar ve tahmini ara durak zamanları önemli sınırlardır. Test mevcut 91 hastanenin envanterini değerlendirmez, sıfırdan en fazla 91 konuma izin verir.

## İlçe koşulunun etkisi

Hafta içi 10.00 profilinde yalnız **her ilçede %80** koşulu kaldırılıp il geneli %95 ve 45 dakika korununca coğrafi alt sınır **35** olur. Bu, ilçeler arasında erişim eşitliği koşulunun sayıyı ciddi biçimde artırdığını gösterir. Bu ayrı kontrol yatak/hekim kapasitesi, maliyet veya yapı çakışması içermez; 91 hastaneyle bütün hedeflerin sağlandığını kanıtlamaz. Uygulamanın varsayılan %80 ilçe hedefi değiştirilmedi.

## Veri kapsamı

| Kontrol | Sonuç |
|---|---:|
| Resmî katalogda incelenen hat/yön/varyant | 665 / 665 |
| Modelle ağa bağlanabilen yön/varyant | 427 / 665 |
| Resmî ayrı durak kimliği | 10.811 |
| Koordinat eşleştirilen durak | 10.335 |
| OSM durak numarası / OSM ray istasyonu adı | 6.450 / 68 |
| Tarihsel topluluk kaynağından ek otobüs koordinatı | 3.817 |
| Koordinatı eksik durak | 476 |
| 200 m içinde yürüyüş ağına bağlanabilen durak | 10.258 |
| Kullanılan / yayımlanan hafta içi kalkış | 10.361 / 14.414 (%71,9) |
| Kullanılan / yayımlanan cumartesi kalkış | 8.022 / 10.805 (%74,2) |
| Kullanılan / yayımlanan pazar kalkış | 7.100 / 9.479 (%74,9) |
| Kaynaklar arasında 300 m üzeri koordinat farkı | 274 |
| Fiziksel alt sınır nedeniyle artırılan toplam süre | 89 |

Yüzdeler sefer sayısı oranıdır; nüfus veya hizmet kalitesi kapsamı değildir. Özel sefer notları kesin çözülemediğinde, durak konumu ya da yol bağlantısı eksik olduğunda hizmet uydurulmaz. Eksik kayıt **gerçekte sefer yok** anlamına gelmez. Ara durak saatleri resmî toplam süre ve OSM ağı üzerinden tahmin edilir. Başkentray, dolmuş, tarihli istisnalar, canlı gecikme ve araç doluluğu dahil değildir. [Ayrıntılı kalite kayıtları](../data/processed/ego-quality.json).

## Kapasite ve maliyetli örnek

Hafta içi 10.00, hastane sayısı serbest: **211 tesis, 24.950 yatak, 22.971 hekim**. Karşılanan talep 5.614.804 kişi eşdeğeri (%95); en düşük ilçe oranı %80,014. Ortalama 26,94 dakika, P90 42,46 dakika. Yaklaşık Aralık 2024 TL ile bina yatırımı 200,93 milyar; işletme 161,28 milyar/yıl; yıllık eşdeğer maliyet 172,82 milyar/yıl.

Bu geçerli, süre sınırlı bir çözümdür; minimum tesis sayısı değildir. Maliyet aşaması açıklığı %2,61, yolculuk aşaması açıklığı %80,12: daha iyi bir yerleşim bulunabilir. Maliyetler önceki kısmi gider kalibrasyonudur. [Tam sonuç](../data/processed/example-transit-result.json).

## Doğrulama ve yeniden üretim

- 29 birim/API testi: kaçan kalkış, biniş hazırlık sınırı, farklı günler, aktarma sınırı, yürüyüş zincirleme yasağı, 15 dakikadan uzun doğrudan yürüyüş, özel sefer notu, yinelenen saat metni, otobüs erişim/tek yön izinleri ve köprü düğümü ayrımı dahil.
- Dört profilde sekiz temsilî başlangıç × 4.825 hedef için toplu matris, bağımsız tek-başlangıç çözümüyle eşleştirildi. Örnek araçlı izlerde biniş saati, bekleme, durak sırası ve en fazla üç biniş denetlendi. Bu algoritma tutarlılığı kontrolüdür; sahada ölçülen seyahat süresi doğrulaması değildir.
- Yedi ana kayıtlı senaryo ve 835 temas/hekim duyarlılığı denetlendi. Geçerli çözümlerin bütün atamaları, il/ilçe paydaları, iki kapasite, alan/çakışma ve maliyet yeniden hesaplandı. Dört EGO 91 testi tam bağlantılı coğrafi problemden yeniden doğrulandı.
- Ham kaynaklar mevcutken 666 EGO HTML dosyasının SHA-256 kimliği kontrol edilir. Paketlenmiş bütün veri dosyaları ayrıca manifestoyla doğrulanır.

```powershell
.venv\Scripts\python.exe -m pytest -q
npm run build
.venv\Scripts\python.exe scripts/verify_transit.py
.venv\Scripts\python.exe scripts/verify_release.py
```

Bu komutlar kayıtlı çıktıları değiştirmez. Yeni tarife kesiti için `fetch_ego.py --refresh`, ardından `build_timetable.py`; yeni kontrollü deneyler için `verify_transit.py --write` kullanılır. `verify_release.py --write-report` mevcut örnekleri tekrar denetleyip karşılaştırma kartlarını yeniler; tüm kapasite çözümlerini tekrar üretmek için `--write-examples` kullanılır. Son adım `manifest.py` olur. Eski matris, kontrollü deneyde Git commit `d2c5e226484e4aa9af9fe1eec801b18e024c96db` içinden alınır. [Makine raporu](../data/processed/transit-validation.json), [veri sözlüğü](../data/README.md).
