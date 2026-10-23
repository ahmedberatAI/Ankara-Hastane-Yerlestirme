# Bağımsız hakem döngüsü · 22–23 Ekim 2026

**v0.7 kontrol noktasında kaynak, yönlendirme ve kapasite hesapları doğrulandı; genel model başarısı veya gerçek Ankara kalibrasyonu kabul edilmedi.** Geliştirme döngüsünün bitişi 23 Ekim 2026 08.00 TSİ. Ana %95 il, %80 ilçe ve 45 dakika EGO hedefleri korunuyor. Önceki sürümler aşağıda tarihsel denetim izi olarak saklanmıştır.

## 23 Ekim 05.35 TSİ: ortak maliyet aramasında 209 konum

Yeni arama önceki 239 konum havuzunda yatak ve hekimleri yeniden seçti: **209 konum / 26.400 yatak / 23.035 hekim**. Dört profilde il %95, her ilçe en az %80 ve 45 dakika hedefleri korundu. Yıllık eşdeğer maliyet **175,868263289 milyar TL**; 239 planına göre **%7,035719** düşük, değişmeyen önceki model tavanının **%7,221406** altında. Yıllık malzeme gideri bir kez sayıldı. İki bağımsız hakem kaynakları, tam atamaları, maliyetleri ve bütün özgün model koşullarını doğruladı.

Maliyet alt sınırı 173,211849311 milyar TL ve son planla %1,510457 açıklık **yalnız başlangıçtaki 239 konum havuzuna** aittir; tüm Ankara adaylarına veya minimum hastane sayısına genellenmez. Arama 300,328 saniyede zaman sınırında durdu. Ortalama süreler **31,69 / 32,37 / 32,43 / 32,82 dakika**; önceki plana göre üç profil biraz uzadı. Henüz süre iyileştirmesi kabulü yok. Aynı kişilere ilişkin koşullu ortak bölüm %92,677795–%92,780537; kimlik gözlemi veya %95 ortak kişi garantisi değildir.

Hacettepe'nin resmî mali bölümündeki yıllık gider/devreden borç ve bütçe transferi ayrımı ayrıca doğrulandı; tam kamu işletme gideri katsayısı türetilmedi. [Kaynak kapsamı](hacettepe-finance-check.md). Ulaşım girdileri, sağlık katsayıları ve 91 deneyleri değişmedi. Bu ilerleme mevcut model içindeki maliyet aramasındadır; gerçek EGO ve klinik kalibrasyon açıkları sürüyor.

Güncellenen sertifika salt okunur denetimden geçti; 47 çıktı manifestosu eşleşti. Arayüz regresyonu ve üretim derlemesi geçti. Tarayıcıda 209 konum / 26.400 yatak / 23.035 hekim, %7,22 tavan farkı ve dört profil görüldü. [Güncel hesap ekranı](screenshots/ortak-plan-209.png). Önceki kodun 623 testlik kabulü korunur; bu adımda çözücü kodu değiştirilmedi.

## Önceki ortak konum kontrol noktası: 239 konum

Konum, yatak ve hekim kaynaklarını birlikte seçen araştırma **239 konum / 31.550 yatak / 23.242 hekim** içeren bir ortak plan buldu. Dört başlangıç profilinin her birinde il %95, bütün ilçelerde en az %80 ve bütün pozitif atamalarda 45 dakika sınırı korundu. Yıllık eşdeğer maliyet **189,178318200 milyar TL**, önceki değişmeyen model tavanının **378,621009 milyon TL / %0,199740** altında. Bu yalnız mevcut modelde eski tavanı karşılayan en az bir ortak plan bulunduğunu gösterir; gerçek kamu bütçesi, minimum hastane sayısı veya 91 hastanenin yeterliliği kanıtı değildir.

Ulaşım hakemi 185.772 değişkenli özgün model vektörünü tam JSON atamalarından birebir yeniden oluşturdu; kaynak, alan, çakışma ve dört ayrı profil kısıtlarını bağımsız denetledi. Kanıt hakemi maliyetleri yüksek duyarlıklı ondalık hesapla, tek yıllık malzeme faturasıyla yeniden hesapladı. İki hakem de nihai planın bu dar kapsamda uygulanabilirliğini kabul etti. 702 denemenin kuyruğu tamamlandı; bu durum genel maliyet optimumu veya başka kaynaklarla daha fazla kapatmanın olanaksızlığı olarak sunulmuyor.

Ortak kaynaklar aynı kişiler demek değildir: dört ayrı %95 atamanın mahalle düzeyinde aynı nüfustan alt kümeler olduğu varsayılırsa ortak bölümün koşullu sınırları **%91,624106–%92,227534**. Kimlik verisi veya aynı kişilerin %95'ine hizmet garantisi yok. Ortalama süreler 32,15 / 32,26 / 31,98 / 32,48 dakika; bu aramada süre ayrıca optimize edilmedi.

Yayımlanan tam atama sertifikası ve bağımsız denetçi araştırma klasörüne bağımlı değildir. Arayüz ortak planı ayrı bir haritada, gri nüfus arka planını kapsama gibi boyamadan gösterir. Ulaşım paketi, sağlık katsayıları ve eski 91 deney girdileri değişmedi. Eksik hizmetler, tahmini ara durak süreleri, klinik iş yükü, il dışı talep ve tam işletme maliyeti açık konulardır. [Hesap ve kanıt kapsamı](joint-plan.md).

Üretime taşınan ortak model, tam 4.701 aday ve seçili 239 aday için özgün araştırma formülünün bütün katsayı, indeks, sınır ve başlangıç vektörleriyle eşleşti. Üç hakemin kod/kanıt çapraz incelemesinden sonra **623 test geçti; üç Windows bağlantı oluşturma izin testi atlandı, üretim derlemesi geçti**. Yeni komutun gerçek veriyle süre bütçesi tükenen başlangıç kontrolü, yerel arama başlatmadan geçerli 239 planını ve doğru durum etiketini korudu. Bağımsız salt okunur denetim ve 47 çıktı manifestosu eşleşti. Tarayıcıda dört profil, bütçe, nüfus katmanı ve harita kontrol edildi; hata günlüğü boştu. [Hesap ekranı](screenshots/ortak-plan-hesabi.png) · [Ortak harita](screenshots/ortak-plan-haritasi.png). Yeni komutla henüz büyük maliyet araması yapılmadı; bu kabul sonraki bir koşunun sonucu için otomatik onay değildir.

## 23 Ekim 04.10 TSİ: kapasite ile ulaşımı ayıran ek kontrol

Ulaşım kısıtları kaldırılan yeni bağımsız denetimde kayıtlı araba planının **46 tesis / 18.550 yatak / 21.590 hekim** kaynakları ve atamaları dört alternatif profil için aynı tutuldu. Konumlandırılamayan nüfus paydalarda kaldı; il %95 ve her ilçe %80 hedefi korundu. Aynı yıllık talep ve malzeme gideri yalnız bir kez sayıldı. Yıllık eşdeğer maliyet **143,878 milyar TL**, kayıtlı EGO bütçesi **189,557 milyar TL** altında. Bu yalnız toplam kapasite, alan ve maliyet varsayımlarının yüksek EGO sayısını tek başına zorlamadığını gösterir. Gerçek EGO ağıyla 91 tesisin yeterliliği, minimum tesis sayısı veya klinik gerçekçilik kanıtlanmıyor. [Hesap ve sınırları](transport-relaxation.md).

Ulaşım hakemi üretim denetçisini hazırladı; kanıt hakemi kaynak kimliklerini, bağımsız ondalık maliyet/akış hesabını, dört profil kapsamını ve arayüz iddialarını çapraz inceledi. Kaynak ya da sağlık veri sürümü uyuşmazsa sonuç gizleniyor. Dosya yazımı için bulunan geçici dosya bağlantısı hatası, benzersiz ve özel açılmış dosya ile atomik değiştirme kullanılarak giderildi. Kabul yalnız bu tanının iç tutarlılığı kapsamındadır.

Başkentray için iki resmî tabloda 146 tren / 24 istasyon / 3.504 saat hücresi doğrulandı. Hafta içi takvimi sayfa ile tabloların birlikte yorumuna dayanıyor; hafta sonu takvimi bilinmiyor. Ray yolları doğrulansa da kat ve erişim koşullarıyla perona ulaşım kanıtı tamamlanmadı. Bu nedenle trenler üretim ağına eklenmedi; eksik model kapsamı gerçek hizmet yokluğu sayılmadı. [Kaynaklar ve erişim sorunu](baskentray-research.md).

**432 test geçti, iki test Windows sembolik bağlantı oluşturma izni nedeniyle atlandı; üretim derlemesi geçti.** Yeni rapor salt okunur yeniden üretimle ve 45 çıktı manifestosuyla doğrulandı. Yerel arayüzde yeni panelin sayıları, açıklamaları ve kaynak bağlantısı kontrol edildi; tarayıcı hata günlüğü boş. Matematik, ulaşım paketi ve önceki 91 deney girdileri değişmediği için aynı deneyler yeniden çözülmedi. [Ekran kontrolü](screenshots/kapasite-ulasim-tanisi.png). Ulaşım süreleri, eksik hizmetler, klinik kapasite ve tam maliyet kalibrasyonu açık; genel başarı kabulü yok.

## v0.7: giderilen hatalar ve kabul kapsamı

216 ek durağın yol bağlantısı, resmî sıra ve tek yönlü yol kanıtıyla yeniden kuruldu. 477 aday değişiklik belirsiz komşular nedeniyle bekletildi; önceki üç uzak-durak bağlantısı kimlikleri korunarak ayrıca doğrulandı. İlk daha geniş prototipler, iki yönlü paralel yol ve aynı yolun başka kolu gibi karşıörnekler nedeniyle kabul edilmedi. Yeni eşleştirmeye dokunan her parçanın iki ucu ortak durak kaydına kilitleniyor; rota araması başka bir düğüme geri dönemiyor. 438 çiftin 437'si geçiyor, önceden de kullanılmayan bir çift mevcut geometri sınırında belirsiz kalıyor. [Yöntem ve sınırlar](bus-stop-matching.md).

527-1'in 25 kalkışı, gerçek erişilebilir kaynak satırındaki gün/saat/not/1–98 aralığıyla eşleştirildi. Toplam 49 dar kural uygulanıyor ve dokuz gerçek HTTP arşivine bağlı. 85 dakikalık yayımlanmış alan fiziksel tabanla 108,492 dakikaya çıkıyor; bu ölçülmüş varış saati değil. Ekli saat tablosunun geçerlilik tarihi belirsiz. 527-2'nin başlangıç kimliği çözülmediği için bu yönde sefer türetilmedi.

430 yön/varyant ve 545 örüntü kullanılabiliyor. Önceki 543 örüntünün durak, kesit ve kalkışları korundu; 147'nin beş kalkışı ile 527-1'in 25 kalkışı eklendi. Bağımsız ulaşım hakemi 33 paket dosyasını, 295.158 yol/ray çizgi parçasını, 34.855 fiziksel süre oluşumunu ve 154.400 bağımsız yönlendirme sonucunu doğruladı. En büyük matris farkı 0,00000381 dakika. Ham kaynak seçicisi üretim fonksiyonlarını çağırmadan aynı 693 ilk aday / 477 bekleyen / 216 kabul ve 1.781 eski komşu kararını yeniden üretti.

Bu kabul, kaynak ve algoritma tutarlılığı kapsamındadır. 516/616'da incelenen iki bağlantı düzeldi; 615/560-8 örnekleri komşu belirsizliği nedeniyle bekliyor. Ara durak tahminleri, gerçek güzergâh ve peron girişleri sahada doğrulanmış değil.

## v0.7: yeni deneyler

91 sınırının coğrafi gevşetmesinde dört kesin minimum **165 / 167 / 170 / 168**. Bunlar aynı modelde gerekli koşulun alt sınırlarıdır; gerçek kent için ihtiyaç sayısı değildir. Yalnız ilçe tabanı kaldırılan hafta içi 10.00 tanısı 32, sekiz kırsal ilçenin birlikte coğrafi minimumu 135. Varsayılan hedefler değiştirilmedi.

Hafta içi 10.00 maliyet aşaması 204 tesis / 24.950 yatak / 22.966 hekim buldu; yıllık maliyet 172,3245 milyar 2024 TL, ortalama süre 30,9294 dakika. Bütçe içinde süre azaltma ve kaynak temizliği sonrası **261 tesis / 27.800 yatak / 23.534 hekim**, 183,9269 milyar TL/yıl ve 29,0622 dakika elde edildi. İlk maliyet açıklığı %2,5416, son planın maliyet açıklığı %8,6895, süre açıklığı %82,0166. Açıklıklar daraltılmış atama araması kapsamındadır. Bu büyük süre açıklığı daha iyi çözümler bulunabileceğini açık bırakır; 261 minimum veya önerilen gerçek hastane ihtiyacı değildir. Araba planları sayısal olarak değiştirilmeden yeniden denetlendi.

| Profil | Aynı 261 tesis/yatak/hekimle en çok talep | Aynı yapı izlerinde maliyetsiz fiziksel tavan |
|---|---:|---:|
| Hafta içi 08.00 | %92,5056 | %96,9630 |
| Hafta içi 10.00 | %95,2058 | %96,5419 |
| Cumartesi 10.00 | %85,7567 | %92,0937 |
| Pazar 10.00 | %85,2515 | %91,0738 |

Sabit kaynak testi aynı 189,5569 milyar TL yıllık tavanı koruyor; yalnız hafta içi 10.00 hedefi geçiyor. Ayrı fiziksel tavan maliyeti kaldırıp yapı izlerinin izin verdiği kaynakları kullanıyor; hafta sonu yine %95 altında. Dolayısıyla **aynı 261 yapı izinde** yalnız yatak/hekim artırmak dört profil için yetmiyor. Kanıt hakemi üretim model ve denetim fonksiyonlarını çağırmadan ayrı sparse LP'lerle sekiz yüzdeyi, kaynak/alan/akış denklemleriyle plan maliyetini ve süreyi yeniden doğruladı. Başka konumlar veya gerçek Ankara için olanaksızlık çıkarılamaz. Ortak konum seçimi üretim dışında ayrıca araştırılıyor.

## v0.7: açık kritik sınırlamalar

Terminal kalkışları korunurken 301 örüntünün tahmini ara ofsetleri değişti. Denetlenen bir 611 yolculuğunda 71,20 saniyelik daha erken ara varış, seferin 29,83 saniyeyle kaçırılmasına ve modelde 36,32 yerine 75,01 dakika bulunmasına yol açtı. Bu, gerçek hayatta ölçülmüş değişim değildir. Hafta içi coğrafi sınırın 166'dan 167'ye çıkması bu eşik hassasiyetiyle tutarlıdır; daha doğru kaynak eşleştirmesi mutlaka daha düşük hastane sayısı üretmez. [Deneyin kapsamı](transit-validation.md).

Sekiz kırsal ilçede 45 dakikada yürüyüş dışı ek aday kazanan durum yine yalnız Ayaş'ta hafta içi 10.00 ve pazar profilleridir. 527-1 eklenmesi Kızılcahamam için bu dar eşikte yeni aday kazandırmadı; gerçek hizmet yokluğu sonucu çıkarılmaz. Eksik özel seferler, Başkentray/dolmuş kapsamı, tarihli istisnalar ve ara varış saatleri açık kalıyor.

2025 Sağlık Bakanlığı bülteni görsel ve metin olarak incelendi. İlgili tablolar Türkiye/İBBS-1 düzeyinde; Ankara il satırı yok. Ankara 2024 katsayıları değiştirilmedi. Hekim temas oranı klinik kapasite standardı, kısmi işletme giderleri tam kamu bütçesi değil. [Sağlık kaynağı kapsam kontrolü](health-data-freshness.md).

**339 Python testi ve üretim derlemesi geçti.** Kaynak hashleri, arşiv satırları, tam ve ham kaynak bulunmayan denetim yolları, sabit/ortak kapasite sonuçları ve 44 hazırlanmış çıktının bütünlüğü kontrol edildi. Ulaşım ve kanıt hakemlerinin kabulü bu sınırlı kapsamı aşmıyor; araştırma modeli genel olarak başarılı tamamlandı sayılmıyor.

---

## Tarihsel v0.6 kontrol noktası

## v0.6: yeni kaynaklar ve ağ

665 yön/varyantın 428'i, 543 sefer örüntüsüyle kullanılıyor. 516, 616, 560-8 ve 615 kullanılabilir kapsama eklendi. Üç uzak durağın mevcut yönlü yol kenarına bağlanması eski düğümler arasındaki yolları, araba ve yürüyüş ağlarını koruyor. 527/610 ailesinin geometrisi düzelmesine rağmen çözülmemiş özel sefer notları hâlâ kullanımını engelliyor; eksik modellenen hizmet, hizmet yokluğu değildir.

24 özel kalkış kaydı, altı gerçek resmî HTTP arşivinin içerik kimlikleriyle bağlandı. 560-8 için tam yön bütçesi 75 dakika; 615'in yalnız dört hafta içi Ulus→Güdül kalkışında 2025 planındaki 95/120 dakika kullanılıyor. Tarihli planın bugün aynı kaldığı veya varışların ölçüldüğü iddia edilmiyor. [Kaynak ve yön varsayımları](service-evidence.md).

Ulaşım hakemi 29 paket bileşenini, 298.222 yol/ray çizgi parçasını, 34.627 kesit oluşumunun fiziksel süre tabanını ve dört profilde 154.400 bağımsız başlangıç–hedef sonucunu kontrol etti. Önceki 537 örüntünün ofsetleri korundu. Bu, algoritma ve kaynak tutarlılığı kabulüdür; araç güzergâhı veya saha süre doğrulaması değildir.

## v0.6: 91 ve kapasite deneyleri

Dört coğrafi 91 deneyinin minimumları hafta içi 08.00/10.00, cumartesi/pazar 10.00 için **165 / 166 / 170 / 168**. Bağımsız budamasız, zaman sınırlı MILP koşularının alt sınırları da 91'in üstünde; aynı kesin minimumları bağımsız tekrar kanıtlamış gibi sunulmuyor. Bu sayılar gerçek Ankara için ihtiyaç sayısı değildir. Mevcut 91 hastane envanteri yerine sıfırdan en fazla 91 aday konum sınanıyor.

Yeni hafta içi 10.00 kapasite planı **209 tesis, 24.950 yatak, 22.966 hekim**, %95 il talebi ve en düşük %80,0143 ilçe talebi sağlıyor. Ortalama 27,8667 dakika; yıllık eşdeğer maliyet 172,6697 milyar Aralık 2024 TL. Son maliyet açıklığı %2,7514 daraltılmış atama aramasına ait; süre açıklığı %80,7912. Küresel maliyet veya minimum tesis sayısı optimumu değildir. Araba planları değiştirilmeden yeniden denetlendi: 46 tesis, 18.550 yatak, 21.590 hekim.

Aynı 209 konum/yatak/hekim ve 189,9507 milyar TL yıllık tavanla dört profil testi yalnız hafta içi 10.00'da hedefleri sağlıyor. Hafta içi 08.00 üst kapsamı %93,6553; hafta sonunda ortak ilçe koşulları olanaksız, ana yüzde bu nedenle boş bırakılıyor.

Yeni ortak kaynak modelinde aynı konum ve yapı izleri korunup yatak/hekim kadrosu birlikte yeniden seçildi. Model bu yerleşimde dört profil hedeflerini sağlayamıyor. Maliyet ve bütçe kaldırılan ayrı fiziksel kapasite tavanı:

| Profil | İlçe tabanları korunarak en yüksek kapsam |
|---|---:|
| Hafta içi 08.00 | %94,7221 |
| Hafta içi 10.00 | %96,0370 |
| Cumartesi 10.00 | %89,8003 |
| Pazar 10.00 | %89,7204 |

Kanıt hakemi özgün kişi birimlerinde bağımsız LP kurarak bu dört tavanı tekrar üretti. Optimizasyon hakemi ayrıca ilçe tabanlarını kaldırıp alan/kaynakları yukarı yuvarlayan farklı bir maksimum akış hesabıyla üç profilin yine %95 altında kaldığını doğruladı. Bu yalnız **aynı 209 yapı izinde** daha fazla kaynak satın almanın yetmediğini gösterir; başka yerleşim veya gerçek Ankara için olanaksızlık değildir.

Sabit kaynakların hafta sonu ilçe kotası sorununda her ilçe tek başına yeterli kaynak bulabiliyor, birlikte kaynaklar paylaşılıyor. Bağımsız gevşetilmiş kota ağında cumartesi en az 21.042 kişi eşdeğeri açık, minimum kesitte Etimesgut–Sincan–Yenimahalle; pazar en az 17.600 açık, kesitte Etimesgut–Sincan bulunuyor. Bunlar tek tek ilçelerin mutlak yetersizlik tavanları değildir. [Bütün sonuçlar ve kapsam](validation.md).

## v0.6: açık kritik sorunlar

**P1 — karşı taşıt yoluna bağlanma:** en yakın yol düğümü bazı resmî durakları karşı yöne bağlayıp gereksiz U dönüşü oluşturuyor. Örneğin 615'te 50174→57208 modelde 2.204 m, aynı izinli tek yönlü kenar üzerinde yönü koruyan projeksiyonda 146 m; 560-8'de 50167→50390 için 1.750 m / 261 m. 516/616'da da benzer örnekler var. Bunlar son üç uzak-durak düzeltmesinin dışında kalan eski hata sınıfı. Paket içindeki yol parçalarının legal olması, durakların doğru taşıt yoluna bağlandığını kanıtlamıyor. Düzeltme ayrı prototipte araştırılıyor; v0.6 bu açık sorunla yayımlanıyor ve arayüzde açıklanıyor.

**Kırsal hizmet kapsamı:** sekiz kırsal ilçede 45 dakikada toplu taşıma sayesinde ek aday kazanan tek yeni satır Ayaş/Başbereket, 164 kişi; hafta içi 10.00'da sekiz, pazar altı ek aday. Diğer yedi ilçe ve Ayaş'ın kalan satırları doğrudan yürüyüş adaylarıyla aynı. Bu gerçek hizmet yokluğu değildir. Ortak sekiz-ilçe coğrafi minimumu 135; yalnız ilçe tabanı kaldırılan il %95 tanısında minimum 31. Farklar toplanabilir nedensel katkı değildir.

Gerçek ara durak saatleri, tarihli işletme istisnaları, klinik branş/vaka karışımı ve tam kamu işletme maliyeti doğrulanmadı. Tek gün/saat profili ve dört profil testi bütün gün/yıl garantisi sağlamıyor. Bu sınırlamalar giderilmeden başarılı tamamlandı hükmü verilmiyor.

## v0.6 kabul ve uygulama kontrolü

**253 Python testi ve üretim derlemesi geçti.** Alan sınırında tamsayı hekim kapasitesini yanlış aşağı yuvarlayan üst sınır düzeltildi; belirsiz/olanaksız durum etiketleri, alt sınır kapsamı ve 25 ilçe kaydı/nüfus paydası zorunlu denetleniyor. Diğer hakemlerin ters örnekleri ve bağımsız küçük problem kontrolleri geçti. Yeni üretim denetçisi CI zincirine eklendi.

Kaynak/plan/model kimlikleri ve 44 işlenmiş çıktı manifestosu eşleşiyor. `verify_release.py`, `verify_transit.py`, `audit_robustness.py` ve `audit_shared_capacity.py` son dosyaları salt okunur doğruladı; dört kontrol de başarıyla tamamlandı.

| Hakem | Kabul edilen kapsam | Açık kalan hüküm |
|---|---|---|
| Ulaşım | Kaynak arşivleri, yönlü geometri, ofsetler, fiziksel sınırlar, bağımsız yönlendirme | P1 taşıt yolu eşlemesi için revizyon gerekli; gerçek süre kabulü yok |
| Kapasite / optimizasyon | Ham atama/alan/maliyet, model içi 91 sonucu, farklı maksimum akış ile sabit alan tavanları | Klinik ve mali tam kalibrasyon yok; konum planı çoklu profilde başarısız |
| Kanıt / arayüz | Yeni rapor, kaynak kimlikleri, API/JSON/React çıktısı ve belgeler | Yalnız açıklanmış model kapsamı; gerçek ihtiyaç ve saha süresi kabulü yok |

Yerel uygulama v0.6 olarak yeniden başlatıldı. Canlı arayüzde hafta içi 10.00/91 için 166, pazar 10.00/91 için 168 görüldü; seçim değişince eski hesap kendi etiketiyle kaldı ve bekleyen seçim ayrıca gösterildi. Yöntem penceresinde 24 sefer yorumu, tarihli süre varsayımları ve açık karşı yol hatası görüldü. Tarayıcı hata kaydı boştu. Yeni ortak kaynak bölümü 209 sabit konumu, dört ayrı tavanı ve başka konumlara genellenemeyeceğini gösteriyor. [Kapasite deneyi ekranı](screenshots/ego-ortak-kapasite-v06.png). GitHub CI sonucu ayrıca gözlenmedi; yerel test/denetim sonucu ile karıştırılmıyor.

## v0.5 tarihsel denetim kaydı

Aşağıdaki sayılar önceki c037950 kontrol noktasına aittir; güncel v0.7 ve tarihsel v0.6 sonuçları yukarıdadır.

## Değerlendirme yöntemi

Üç ayrı hakem ulaşım doğruluğunu, kapasite/optimizasyon matematiğini ve veri kanıtı/arayüz iddialarını inceliyor. Düzeltmeyi yazan hakemin görüşüne ek olarak başka bir hakemden inceleme alınıyor. Birim testlerinin geçmesi, gerçek Ankara için doğru sonuç veya yeterli hastane sayısı kanıtı sayılmıyor. Varsayılan %95 il, %80 ilçe ve 45 dakika EGO hedefleri korunuyor; farklı hedefler yalnız açık etiketli duyarlılık deneylerinde kullanılıyor.

## İlk turda saptanan ve düzeltilen sorunlar

| Bulgu | Düzeltme | İlk turda istenen kanıt |
|---|---|---|
| Tarihsel durak koordinatları bazı hatlarda yüzlerce kilometrelik sahte sapmalar oluşturuyor. | Güncel resmî Başkentkart durak sorgusu öncelikli kaynak yapıldı; adres/koordinat çelişkileri ve aşırı rota uzunlukları açık kalite kayıtlarıyla ayrılıyor. | Tam durak taraması, yeni ağ ve somut hat örneklerinin tekrar denetimi. |
| Toplam süre kontrolü tek tek kesitlerin fiziksel olarak aşırı hızlı olmasını engellemiyor. | Her kesitte ayrı asgari süre ve durak payı; yayımlanan toplam korunamıyorsa artış raporlanıyor. | Yeni ağın bütün kesitlerinde bağımsız hız/mesafe denetimi. |
| A→B→A veri değişiminde yürüyüş önbelleği yanlış çıktıyı yeniden kullanabiliyor. | Etkin girdi kimliği ve dört çıktı dosyasının içerik kimliği birlikte doğrulanıyor. | Regresyon geçti; yeni tam paket üretimi gerekiyor. |
| Tek başlangıç saati için bulunan hastane planı, farklı günlerde aynı kapasiteyle sınanmıyor. | Aynı konum/yatak/hekimlerle dört profilde yeniden tahsis LP'si; başarısız ve belirsiz durumlar ayrı gösteriliyor. | Yeni plan için dört profil ve coğrafi duyarlılık raporları. |
| Maliyet açıklığının yalnız daraltılmış bağlantı aramasına ait olduğu sonuç yanında yeterince açık değil. | Kapsam etiketi ve yöntem açıklaması eklendi; son planın minimum hastane sayısı olduğu iddia edilmiyor. | Gerçek raporlarla arayüz kontrolü. |
| Eski sonuçlar yeni saat veya veri paketiyle etiketlenebiliyor; kayıtlı sertifika sayıları eksik karşılaştırılıyor. | Veri/kod/indeks kimlikleri, sonuç bağları ve negatif regresyonlar eklendi; uyuşmayan kayıtlar gösterilmiyor. | Tam paket ve çevrimdışı yeniden üretim denetimi. |

## İkinci tur · yeniden üretim öncesindeki kayıt

Bu bölüm düzeltmeler yazılırken kaydedilen durumu anlatır. Burada beklenen deneylerin sonraki sonuçları ve güncel kabul düzeyi aşağıdaki v0.5 bölümlerindedir.

Bazı özel sefer notlarında tek durak numarası ve “başlar” sözcüğü yeterli kabul ediliyor, devamındaki “servis dışı”, adlandırılmış son durak veya ikinci saat gözden kaçabiliyordu. Bu durum doğrulanmamış dönüş yolculukları veya yanlış kalkış saati üretebilir. Desteklenen not örüntüleri daraltıldı; çelişkili saatler ve çözülemeyen koşullar açık gerekçeyle ayrılıyor. Kod çapraz incelemeden geçti; yeni matris etkisi henüz ölçülmedi. Hariç bırakılan kayıt, gerçekte sefer bulunmadığını göstermez.

Süreyi iyileştiren ikinci optimizasyon aşaması, aynı süreyi veren ve bütçeye sığan çözümler arasında kullanılmayan tesis/kaynak bırakabiliyordu. Kabul edilen son akışları ve süreyi değiştirmeden boş tesisleri kapatma, gerekli hekim sayısı ile en ucuz uygun yatak seçeneğini kullanma düzeltmesi eklendi ve çapraz incelemeden geçti. İlk maliyet planı ile son planın ayrı ölçümleri gösteriliyor; tesis sayısı hâlâ küresel minimum sayı iddiası taşımıyor.

Sabit planın dört profil testine orijinal yıllık maliyet tavanı da eklendi. Bina, yatak ve hekim giderleri sabit; malzeme gideri her profilde yeniden atanan yıllık talebe bağlıdır. İlçe koşulu kaldırılan ayrı tanıda bile bu bütçe korunur. Bu değişiklik maliyet kalibrasyonunun eksik kapsamını gidermez. Matematik bağımsız 100 küçük problemde doğrulandı; yeni gerçek veri raporu ve arayüz kontrolü bekliyor.

Kapasite düzeltmesinin çapraz incelemesi, çözücü toleransı içinde kapalı tesise çok küçük pozitif akış verilmesi halinde temizliğin hata verebildiğini ortaya çıkardı. Bu durumda doğrulanmış özgün çözümü koruyan ve temizliğin uygulanmadığını açıklayan geri dönüş eklendi. Maliyet alt sınırı geçerli çözümün maliyetini anlamlı ölçüde aşarsa da çelişki sıfır açıklık gibi gizlenmiyor. Bu sayısal sınırlar ayrıca regresyonla sınanıyor.

Resmî sayfadaki “Süresi” alanının her hatta tek yönü mü bütün durak zincirini mi kapsadığı doğrulanamadı. Model bu alanı zincire dağıtır; bu bir varsayımdır. Otomatik ikiyle çarpma veya resmî çevrim süresi olduğu iddiası yapılmaz. Bu belirsizlik, tahmini ara durak saatlerinin gerçek seyahat süresi ölçümü yerine geçememesinin nedenlerinden biridir.

## Kaynak ve yorum sınırları

Güncel koordinat kaynağı [resmî Başkentkart haritası](https://baskentkart.ego.gov.tr/) ve sayfanın herkese açık durak sorgusudur. Ham yanıtın içerik kimliği, sorgulanan durak kimliği ve gerçek gözlem zamanı kaydedilir. Yeniden işleme zamanı kaynak gözlem zamanı olarak sunulmaz. Eski önbelleğin gözlem zamanı bilinmiyorsa bilinmiyor kalır. Güncel koordinat ve tarife kesitlerinin aynı tarihli işletme durumunu gösterdiği ayrıca garanti edilmez.

91 deneyi, sıfırdan seçilen en fazla 91 aday konum içindir; mevcut 91 hastanenin eksiksiz envanter ve kapasite denetimi değildir. Örnek adaylar, eksik hizmet ve tahmini ara durak süreleriyle bulunan bir model alt sınırı gerçek Ankara'daki kesin ihtiyaç sayısına dönüştürülemez. Dört zaman profili tüm gün veya yıl boyunca erişim garantisi değildir. Hekim verimliliği ve maliyetler mevcut kaynaklarla kısmi kalibrasyondur; branş bazında klinik iş yükü standardı değildir.

## Yeniden üretilen kaynak ve ağ

10.743 otobüs durağının tamamı resmî Başkentkart sorgusundan konumlandırıldı; 68 ray istasyonu OSM ile eşleştirildi. Eksik konum ve kullanılan tarihsel ek koordinat kalmadı. Kaynak hakemleri bütün ham yanıtların kimlik, içerik hash'i ve koordinatlarını bağımsız doğruladı. 10.740 yanıtın gözlem zamanı kanıta bağlı; üç eski önbellek yanıtının bilinmeyen zamanı boş bırakıldı.

Yeni ağ 665 yön/varyantın 424'ünü ve 537 sefer örüntüsünü içeriyor. Ulaşım hakemi 298.229 çizgi kenarının OSM yol/ray geometrisinde bulunduğunu; 34.065 kullanılan kesit tekrarında fiziksel süre tabanının ihlal edilmediğini doğruladı. Ayrı olay-zamanı aramasıyla 38.600 başlangıç/profil/hedef karşılaştırması matrisle eşleşti. Bu kabul iç tutarlılık içindir; araçların gerçekten bu yollardan geçtiğini veya ara durak saatlerinin sahada ölçüldüğünü göstermez.

Dört 91 coğrafi deneyi hafta içi 08.00/10.00, cumartesi/pazar 10.00 için sırasıyla 166/168/170/169 alt sınırını verdi. Optimizasyon hakeminin aday budaması kullanmayan ayrı MILP koşuları zaman sınırında daha geniş aralıklar verdi; dört bağımsız alt sınır da 91'i aştı. Bu bulgu aynı paketlenmiş modelle sınırlıdır.

## Üçüncü turda bulunan açık kapsam sorunu

Sekiz kırsal ilçede hafta içi 10.00 / 45 dakika için erişilebilen aday kümeleri, doğrudan yürüyüşle erişilen kümelerle aynı. Yalnız bu ilçelerin %80 koşulunu birlikte sağlayan coğrafi tanının minimumu 136. İl %95 korunup ilçe tabanları kaldırılınca minimum 32. Bu sayılar toplanabilir, bağımsız neden katkıları değildir.

Haymana, Bala, Kalecik, Ayaş, Güdül ve Nallıhan'a giden bazı hatlar adla belirtilmiş başlangıç notları çözülemediği için dışarıda. Bu, hizmet yokluğu olarak yorumlanamaz. Notların resmî durak sırası ve yön bilgisiyle güvenilir eşleştirilmesi araştırılıyor.

527/610 hatlarının eksik yol kesitleri Kurtboğazı 51270/51271 duraklarında yoğunlaşıyor. Resmî duraklar OSM yol kenarına yaklaşık 9/13 metre, en yakın kayıtlı yol düğümüne yaklaşık 1 kilometre uzak. Düğüm üzerinden 300 metre eşleştirme bu uzun kenarı kaçırıyor. Yolun ilgili kesitine yönü koruyan projeksiyon araştırılıyor; yürüyüş izni, ters yön veya düz çizgi araç bağlantısı uydurulmayacak. **Bu açık kapsam sorunu giderilmeden gerçek Ankara için hastane sayısının kalibre edildiği söylenemez.**

## Kapasite ve aynı planın dört zaman testi

Yeni kayıtlı EGO planı 209 tesis, 25.050 yatak, 22.966 hekim; %95 il kapsamı ve en düşük %80,0143 ilçe kapsamıyla 27,7844 dakika ortalama sağlar. Yıllık eşdeğer maliyet 172,875 milyar Aralık 2024 TL'dir. Hakem akış, iki kaynak, alan, çakışma ve maliyeti ham JSON üzerinden bağımsız tekrar hesapladı. Aynı akış için bütün tesisler en ucuz uygun yatak tipinde ve gereken en düşük tamsayı hekim sayısında; dört gereksiz hekim temizlendi.

Aynı konum/yatak/hekim ve 190,177 milyar TL yıllık maliyet tavanıyla yeniden tahsis:

| Profil | Sonuç |
|---|---|
| Hafta içi 08.00 | İl hedefi sağlanmıyor: en çok %93,8055 |
| Hafta içi 10.00 | Hedefler sağlanıyor: en çok %95,0008 |
| Cumartesi / pazar 10.00 | İlçe koşulları sağlanamıyor; ana kapsama yüzdesi verilmez |

Bağımsız tanıda yalnız Etimesgut ve Sincan bırakıldığında bile ortak %80 gereksinimine cumartesi yaklaşık 21.564, pazar 31.286 kişi eşdeğeri açık kalıyor. Her ilçe tek başına koşulu sağlarken birlikte erişebildikleri hekim kapasitesini paylaşıyorlar. Hekim sınırı kaldırılıp yatak korununca ilçe koşulları mümkün; ters durumda mümkün değil. Bu kayıtlı planın hafta sonu sorunu bütçe tavanından kaynaklanmıyor. Tanı, eksik ulaşım verisi ve ortalama hizmet talebi varsayımlarını korur; gerçek klinik kadro açığı ölçümü değildir.

Araba serbest/≤91 örnekleri bağımsız doğrulamada 46 tesis, 18.550 yatak, 21.590 hekim; üniversite oranlı duyarlılık 50 tesis, 18.650 yatak, 55.220 hekim verdi. Bütün ayrıntılar ve daraltılmış aramadaki ilk/son maliyet açıklıkları [doğrulama belgesinde](validation.md).

## v0.5 kontrol noktası için kabul durumu

İki kod inceleme turu, kaynak denetimleri ve bağımsız yeni ağ denetimi tamamlandı. **97 test ve üretim derlemesi geçti.** Dört sağlık PDF'sinin kimlik/sayı denetimi ve 4.701 adayın yol/yüzey ray alan denetimi de geçti. `verify_transit.py`, `verify_release.py` ve `audit_robustness.py` son kayıtları dosya değiştirmeden tekrar doğruladı. 42 işlenmiş çıktının manifestosu ve model/paket/plan kimlikleri eşleşti.

| Hakem | Kabul edilen kapsam | Açık kalan hüküm |
|---|---|---|
| Ulaşım | Kaynak, paket, yol geometrisi, kesit fiziksel sınırları ve yönlendirme iç tutarlılığı | Kırsal durak/hat kapsamı için revizyon gerekli; saha süreleri doğrulanmadı |
| Kapasite / optimizasyon | Kayıtlı planların matematiksel geçerliliği ve bağımsız dört profil LP'si | Plan üç profilde başarısız; EGO süre açıklığı %81,47; klinik/mali tam kalibrasyon yok |
| Kanıt / arayüz | Kaynak zamanları, JSON/API/belge sayıları ve gerçek raporla render edilen başarısızlık/bütçe gösterimi | Kırsal kapsam ve tek yön süre belirsizliği açık tutulmak koşuluyla kabul |

Tarayıcıda dört profil tablosunun 1/4 başarısı, hafta sonu boş ana oranları, aynı bütçe ve kayıtlı plan açıklaması görüldü. Sıfır açığın “-0” gösterimi düzeltildi; kayıt tarihi TSİ ile gösteriliyor. [Yeni ekran görüntüsü](screenshots/ego-dayaniklilik.png). Önceki sürümün `ego-tarife.png` ekranı tarihsel örnektir; v0.5 sonucu kanıtı sayılmaz.

Canlı arayüzde hafta içi 10.00/91 sonucu 168, pazar 10.00/91 sonucu 169 olarak görüldü. Profil değişince önceki hesap kendi saat etiketiyle kaldı; bekleyen seçim ayrıca belirtildi ve indirme devre dışıydı. Sayı serbest canlı EGO hesabı 209 tesis verdi. Birlik–Atıfbey yolculuğunda 413-7 için 10.03 ve 456 için 10.28 binişi, bir aktarma ve 44,4 dakika toplam süre gösterildi; tahmini ara durak uyarısı görünür. [Güncel rota ekranı](screenshots/ego-tarife-v05.png). Tarayıcı hata kaydı boştu. Canlı zaman sınırlı çözümün amaç değeri/açıklığı kayıtlı örnekten biraz farklı olabilir; sağlamlık tablosu açıkça kayıtlı plana aittir.

Bu bir doğrulanmış ara kontrol noktasıdır. Kırsal hizmet notları ile tek yön sürelerini birlikte çözme ve uzun yol kenarına durak bağlantısını düzeltme bir sonraki turdur. Ulaşım girdileri değişince ilgili 91/kapasite/dayanıklılık deneyleri ve hakem incelemeleri yeniden yapılmalıdır. Açık kritik sorunlar varken başarılı tamamlandı hükmü verilmedi.
