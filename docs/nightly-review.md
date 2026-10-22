# Bağımsız hakem döngüsü · 22–23 Ekim 2026

Bu kayıt geliştirme çalışmasının denetim izidir. **v0.5 ulaşım paketi, dört coğrafi 91 deneyi ve kapasite/dayanıklılık denetimleri tamamlandı. Üç hakem bu kontrol noktasının iç tutarlılığını kabul etti; genel model başarısı ve gerçek Ankara kalibrasyonu kabul edilmedi.** Kullanıcının belirlediği çalışma sonu 23 Ekim 2026 08.00 TSİ'dir. Başlangıç sürümü `22179a1`; aşağıdaki açık sorunlar için çalışma sürüyor.

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
