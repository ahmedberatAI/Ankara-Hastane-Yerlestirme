# Yakın başlangıç saatlerinde ortak yerleşim

Bu deney, önceki **209 konum / 26.400 yatak / 23.035 hekim** planının hafta içi 08.05'te gösterilen kapasite açığını ele alır. [Önceki araştırma ve olumsuz kapasite sınırı](departure-sensitivity.md) değiştirilmedi. Yeni yerleşimin sonuçları, bütün başlangıçlar için ayrı atama kayıtlarıyla denetlenir.

## Doğrulanmış sonuç

**226 konum / 30.900 yatak / 23.066 hekim** ile 44 başlangıcın tamamında aynı %95 il / en az %80 ilçe / en fazla 45 dakika koşulları sağlandı. Sonuç özgün sayısal toleranslar içinde bağımsız olarak yeniden hesaplandı; hiçbir hedef, nüfus paydası veya kapasite/maliyet katsayısı gevşetilmedi.

| Ölçü | Önceki dört başlangıç planı | Yeni 44 başlangıç planı |
|---|---:|---:|
| Konum | 209 | 226 |
| Yatak | 26.400 | 30.900 |
| Hekim | 23.035 | 23.066 |
| Yıllık eşdeğer maliyet | 175,868 milyar TL | **186,384 milyar TL** |
| 08.05 il hedefi | Kapasite üst sınırı %94,674 | **%95** |
| 08.05 ortalama / en uzun atama | Hedefi sağlayan plan yok | **26,64 / 44,96 dakika** |

Eski düzenle 160 konum ortak kaldı; 66 yeni konum seçildi ve 49 eski konum çıkarıldı. Yalnız mevcut konumlara kapasite eklenmedi. Yıllık fatura eski dört saatlik planın **10,516 milyar TL (%5,98)** üzerinde, değişmeyen **189,557 milyar TL** model tavanının **3,173 milyar TL** altında. 44 profilde ortalama yolculuklar **26,40–29,12 dakika**, en uzun pozitif atama **44,9886 dakika**; her profilin her ilçesi en az %80. Tam sonuçlar [bağımsız özette](../data/processed/window-plan-summary.json).

600 saniyelik toplam arama bütçesinde çözücü tam 44 profil sıcak başlangıcını açıkça kabul etti; asıl maliyet araması 312 adayın konum, yatak ve hekim kararlarını serbest bıraktı. Süre dolduğunda native çözücü daha iyi bir tam sayı ataması bulamamıştı (0 arama düğümü; başlangıç vektörü korunmuştu). Doğrulanmış kaynak temizliği atamaları değiştirmeden 2 konum, 100 yatak ve 29 hekimin gereksiz kapasitesini kaldırdı; **436,062 milyon TL/yıl** tasarruf bu adımdan geldi. Bunu native aramanın bulduğu ek bir yerleşim iyileşmesi olarak yorumlamamak gerekir. Son 44 sabit kaynak yolculuk LP'si de tamamlandı; kaynaklar ve fatura değişmedi. Bu son geçişin ortalama süre farkı yalnız sayısal düzeyde kaldı (en çok yaklaşık 2,43×10⁻⁹ dakika); ek anlamlı yolculuk tasarrufu iddiası yoktur.

Çözücünün bildirdiği, yalnız **312 aday ve bu 44 profil** için geçerli maliyet alt sınırı 171,063 milyar TL'dir. Son planın toplam yıllık faturasıyla hesaplanan açıklık **%8,22**; bu alt sınır bağımsız bir optimumluk kanıtı olarak sertifikalandırılmadı. Yayımlanan plan uygulanabilir bir araştırma sonucudur; minimum hastane sayısı, en ucuz olası düzen veya gerçek Ankara'da yeterlilik kanıtı değildir.

## Değişmeyen hedefler

Her başlangıçta Ankara'nın **5.910.320** kişilik toplam nüfusunun %95'i, **25 ilçenin her birinde en az %80** ve her pozitif atamada **en fazla 45 dakika** korunur. Konumlandırılamayan **20.516 kişi** paydadan çıkarılmaz. Hedefler, hekim verimliliği, yatak doluluğu, maliyet katsayıları, yol/yaya bağlantıları ve mevcut EGO ağının kapsamı değiştirilmez.

Yeni saat kümesi:

| Normal hizmet günü | Başlangıç aralığı | Örnek sayısı |
|---|---|---:|
| Hafta içi | 07.55–08.05 | 11 |
| Hafta içi | 09.55–10.05 | 11 |
| Cumartesi | 09.55–10.05 | 11 |
| Pazar | 09.55–10.05 | 11 |

Aralık uçları dahil, **tam dakika başlangıçları** kullanılır. Bu 44 örnek arasındaki saniyeler, günün diğer saatleri, özel gün takvimleri veya gerçek sefer güvenilirliği için bir garanti verilmez.

## Konum, yatak, hekim ve maliyet nasıl birlikte seçiliyor?

Her adayda açık/kapalı kararı, bir yatak modülü ve ayrı tam sayı hekim kararı vardır. Aynı kararlar 44 başlangıcın tamamında geçerlidir. Her başlangıç için mahalle talebinin tesislere dağılımı ayrı seçilir; eski dört başlangıcın atamaları yeni saate kopyalanmaz.

Her profilde bir tesisin atanan talebi için iki ayrı sınır uygulanır:

- Yıllık yatak günü talebi ≤ yatak sayısı × 365 × doluluk oranı.
- Yıllık temas talebi (başvuru + yatış) ≤ hekim sayısı × hekim başına yıllık temas varsayımı.

Farklı profillerin yükleri üst üste eklenmez. Ortak kaynaklar her profili ayrı ayrı karşılayabilmelidir. Bu, aynı yıllık talebin farklı ulaşım koşullarında sınanmasıdır; 44 ayrı yıllık hasta nüfusu değildir. Her saatte aynı kişilerin hizmet alması ayrıca zorunlu tutulmaz.

Birinci aşama yıllık eşdeğer maliyeti azaltmayı amaçlar: yıllıklaştırılmış bina yatırımı + tesis/yatak/hekim işletme giderleri + malzeme. **Yıllık talep ve malzeme gideri yalnız bir kez** sayılır. Yolculuk süresi bu aşamada 45 dakikalık sert sınırdır. Ardından bulunan kaynaklar sabit tutularak, her başlangıç için atanan nüfusla ağırlıklı ortalama yolculuk süresini azaltan ayrı doğrusal programlar denenir. Bu ikinci aşama kaynakları veya yıllık faturayı değiştiremez; geçersiz bir sonuç, önceden doğrulanmış yeni maliyet aşamasının atamalarının yerine geçemez.

Önceki dört başlangıç planı **175,868 milyar TL/yıl** karşılaştırma değeridir. Sert üst sınır, önceki modeldeki **189.556.939.209,2935 TL/yıl** değeridir; yeni planın eski planla aynı maliyette olması varsayılmaz. Bu bir kamu tarafından açıklanmış bütçe değildir. Son bütçe kararı bağımsız Decimal hesapla, parasal tolerans eklenmeden verilir.

4.701 adayın tamamı için ulaşım matrisleri hesaplandı. Önceki 239 konumluk havuzun altı başlangıçta Gölbaşı ilçe hedefini sağlayamadığı, cumartesi 09.56'da il erişim üst sınırının %94,7086'da kaldığı görüldü. Bunlar kapasite ve bütçe henüz uygulanmadan bulunan gerekli erişim sınırlarıdır. Bu nedenle optimizasyona geçmeden aday havuzu genişletildi.

Bir açgözlü erişim taraması iki ek adayla (`H-98623-R120`, `H-1664-R210`) 44 başlangıcın coğrafi gerekli koşullarını sağladı. Büyük tesisler için alternatif seçenekler eklenerek **273 adaylık** havuz kuruldu: eski 239 + 34 yeni seçenek. Bu, 273 hastane açılacağı veya bu adayların hepsinin birlikte kullanılabileceği anlamına gelmez. Coğrafi kontrolde en düşük il erişim üst sınırı %95,4542; en düşük ilçe üst sınırı Kızılcahamam'da %80,0402'dir. Ortak kapasite, maliyet ve tesis çakışmaları ayrıca optimizasyonda sınanır.

Bu havuzdaki araştırmalardan sonra erişim ve parsel kapasitesi darboğazlarına yönelik 39 seçenek daha eklenerek **312 adaylık** havuz kuruldu. Bunlar yeni hastane açılışları değildir. Tüm adayların coğrafi erişim üst sınırları başlangıçlar arasında en az %96,1472 il ve %80,6990 ilçe kapsamına yükselir. Bu değerler kapasite ve bütçe uygulanmadan hesaplanır; gerçekleşen hizmet kapsamı olarak gösterilmez.

Asıl arama bu 312 konumda açma/kapatma, yatak modülü ve ayrı hekim kararlarını serbest bırakır. Eski 209 konumu açık tutmak zorunlu değildir. Havuz dışındaki alternatifler için küresel optimum veya minimum hastane sayısı iddiası kurulmaz. Bina varlığına göre aday elenmez; yol/ray üzerinde olmama, tesis alanı ve tesisler arası çakışma kuralları korunur. Havuzun tam indeks listesi, kaynak ve matris kimlikleri `candidate-pool.json` içinde saklanır.

Süre sınırlı aramalarda geçerli plan bulunamaması hedeflerin olanaksızlığını kanıtlamaz. İlk başlangıç araması, dört temel saatin 0/−5/+5 dakika karşılıklarını, yani 12 başlangıcı kullanır. Bulunan kaynakların 44 başlangıçta yeniden sınanması zorunludur; 12 başlangıç için uygunluk, 44 başlangıç için uygunluk sayılmaz.

Başlangıç üretmek için ayrıca tüm 44 profili içeren sürekli doğrusal programlar kullanılır. Bu ara hesaplarda kesirli tesis ve hekim kararları olabilir; bunlar hastane planı olarak yayımlanmaz. Her yerdeki en yüksek profil yükü için tek bir uygun yatak modülü ve tam sayı hekim sayısı seçilir. Alan, parsel çakışması ve yıllık bütçe bu dönüşümden sonra tekrar denetlenir. Kesirli hesapta uygun görünen bir karışım, gerçek bir tesis olarak araziye sığmayabilir veya yuvarlama sonrasında bütçeyi aşabilir.

Çakışan parsellerden birini kapatarak yapılan başlangıç denemeleri yalnız kendi kısıtlı aramalarını tanımlar. Coğrafi erişimin korunması, kaynakların veya maliyetin uygun olduğunu göstermez. Çözücünün küçük sayısal artıklarına uygulanan sınırlı düzeltmeler ham vektör, değişen miktar ve yeniden denetimle açıkça kaydedilir; kapsam hedefleri veya kabul toleransları artırılmaz.

Başlangıç aramasında kullanılan ek açılış cezası, çok düşük kesirlerle birçok tesise yük dağıtmayı azaltmayı amaçlayan bir hesaplama yöntemidir. Klinik veya ekonomik katsayı değildir. Bu cezalı amaç değeri gerçek yıllık maliyet ya da onun alt sınırı olarak sunulmaz. Bütçe satırı ve yayımlanacak yıllık fatura özgün maliyetlerle hesaplanır; asıl serbest maliyet aramasında bu ceza ve başlangıç için konan parsel kapatmaları kullanılmaz.

Bir başlangıç planı ancak bağımsız 44 profil ve kesin bütçe denetiminden geçerse asıl maliyet aramasına aktarılabilir. Asıl aramada bildirilen aday havuzunun konum, yatak ve hekim kararları tekrar serbesttir. Kısmi veya kısıtlı başlangıç aramalarının alt sınırları nihai maliyet açıklığına aktarılmaz. Doğrulanmış tam bir plan üretilemezse nihai sonuç yayımlanmaz.

## Kanıt ve yeniden denetim

Yeni matrisler mevcut EGO ağından, açık hizmet günü ve başlangıç saniyesiyle üretilir; üretimdeki dört profil sabiti değiştirilmez. Dört eski matrisin tüm mahalle/adaya ait değerleri birebir eşleşmelidir. Yeni 08.05 matrisinin eski 209 konumdaki bütün satırları da yayımlanmış olumsuz deneyle birebir eşleşmelidir.

Her yeni matris, sekiz sabit başlangıç noktasından 4.701 hedefe bağımsız olay tabanlı rota aramasıyla örneklenir. Ardışık dakikalar arasında 40 tam matris FIFO kontrolü yapılır. Örnek rota denetimi, her rotanın bağımsız olarak baştan hesaplandığı anlamına gelmez.

Bağımsız plan denetçisi; 44 profilin tüm pozitif akışlarını, nüfus paydalarını, 25 ilçe hedefini, yatak/hekim sınırlarını, tam sayı kararlarını, tesis alanını ve tek yıllık faturayı yeniden hesaplar. Kaynak, kod, matris, profil sırası, ham çözüm vektörü ve rapor kimlikleri birbirine bağlanır. Eksik matris, bilinmeyen sonuç veya kısmi dosya tamamlanmış plan olarak kabul edilmez.

Yayımlanan sonucu **yeni optimizasyon çalıştırmadan** denetlemek için:

```sh
python scripts/audit_window_plan.py --certificate data/processed/departure-window-plan/window-plan.json --manifest data/processed/departure-window/manifest.json --summary data/processed/window-plan-summary.json --quiet
python scripts/manifest.py --check
node tests/window_plan_ui.mjs
```

Yeni, süre sınırlı bir maliyet araması için, henüz bulunmayan bir `work/` klasörü kullanılır:

```sh
python scripts/run_window_plan.py --manifest data/processed/departure-window/manifest.json --resource-seed data/processed/departure-window-plan/resource-seed.json --pool explicit --pool-file data/processed/departure-window-plan/candidate-pool.json --out work/window-reproduction-01 --seconds 600 --seed-seconds 90 --refine-seconds 120 --hard-seconds 900
```

Başlangıç kaynağının eski dört profil sertifikası denetlenir; 44 yeni atama ayrıca çözülüp doğrulanmadıkça sıcak başlangıç olarak kabul edilmez. Yerel kaynak ataması başarısızlığı, tüm konumlarda çözüm olmadığı anlamına gelmez. Yerel çözücü süre sınırı işbirlikçidir; dış süreç ayrıca sert zaman sınırıyla durdurulur. Süre sınırlı aramanın başka çalıştırmada aynı planı bulması garanti edilmez. Çözücü alt sınırı yalnız bildirilen aday havuzu ve profil kümesi içindir; bağımsız küresel optimum kanıtı değildir.

## Üç hakemin son kabulü

Ulaşım hakemi 33.448 pozitif atamanın tamamını 44 ham matrise karşı kontrol etti; optimizasyon hakemi özgün maliyet, 312 serbest aday, kaynak/alan/çakışma koşulları ve ham-son vektör zincirini; veri/arayüz hakemi yayın dosyalarını, kesin Decimal faturayı, kaynak arşivini ve sonuç iddialarını yeniden denetledi. Üçü de **kayıtlı model planının uygulanabilirliğini dar kapsamda kabul etti**; bu yayın kapsamında açık engel bulmadı. Gerçek hizmet, klinik FTE ve tam kamu maliyeti kalibrasyonuna genel kabul verilmedi.

[Son hakem kayıtları ve denetim kodları](experiments/departure-window-final-referees.zip), SHA256 `b814fa692a2811a7bdeedea5cb7ac55fc872658f1c61653934988fb4b6cb3447`. Arşivde üç özgün rapor, denetim kodları ve yayımlanmış girdilerin hash/yol eşlemesi bulunur. **1.139 Python testi geçti, beş Windows izin testi atlandı**; dokuz arayüz regresyonu gerçek yayın özetiyle geçti, üretim derlemesi tamamlandı. Son seyahat geçişi ayrıca anlamlı kazanç getirmiş gibi sunulmaz; kaynak temizliğinin maliyet etkisi yukarıda ayrı açıklanmıştır.

Gerçek tarayıcıda yeni plan kartı, 226 konumlu harita, 44 satırlık sonuç tablosu ve hesap açıklaması kontrol edildi; hata kaydı boş. [Sonuç ekranı](screenshots/ankara-yakin-saatler.png) · [Ortak konum haritası](screenshots/ankara-yakin-saatler-harita.png).

Son yayın kontrolünde eski ortak kapasite kaydının kod kimliği uyumsuzluğu da giderildi. Önceki `f6cadd7` değişikliği `backend/main.py` içinde iki giriş bağlantısı açıklamasını değiştirmiş, eski raporun hash'i geride kalmıştı. Rapor özgün `audit_shared_capacity.py --write --time-limit 60 --ceiling-time-limit 30` komutuyla yeniden üretildi ve salt okunur denetimden geçti. Sonuçlar, kaynaklar ve dört fiziksel kapasite tavanı birebir aynı kaldı; yalnız üretim zamanı ve ilgili kod hash'i değişti. Bu işlem yeni 44 profil modelinin girdilerini veya hedeflerini değiştirmedi. Eski yayın, ulaşım, dayanıklılık, ortak kapasite, ulaşım gevşetmesi, ortak plan, süre kanıtı ve giriş bağlantısı denetimlerinin tamamı geçti.

## Başlangıç planının kaynak zinciri

[Başlangıç kanıt arşivi](experiments/departure-window-seed-evidence.zip) (SHA256 `994ba68a5611559deb3ddb92a86be93cfdbd043253cbba68b0783afd3b56755e`), son 44 profil başlangıcının ham/sınırlı sayısal düzeltme/tam sayı vektörlerini, raporlarını, üretici kodunu, testlerini, kod ve veri kimliklerini ve önceki araştırmalara bağlarını içerir. Bağımsız ulaşım, optimizasyon ve veri denetimleri de arşivdedir. Arşivdeki `archive-manifest.json` her üyenin hash'ini ve depodaki dış gereksinimleri belirtir.

Büyük 44 matris arşivde tekrar tutulmaz. Temiz bir depo kopyasında arşiv repo köküne açılır; manifestteki `externalWindowMatrices` eşlemesine göre yayımlanmış matrisler özgün `work/window-routing/full-v1/` yollarına, hash'leri kontrol edilerek kopyalanır. İlgisiz yerel çalışma üzerine yazılmamalıdır. Arşivdeki README, yeni yerleşim araması başlatmadan ham çözümden sertifikaya kadar denetim komutunu verir.

Başlangıç üreticisinin geçerli çözümü 228 konum / 31.000 yatak / 23.095 hekim ve **186,819886564 milyar TL/yıl** idi. Arşivdeki `canonical-four-source.json`, bunun dört temel saatteki kaynak ve atamalarının birebir alt kümesidir; ayrı bir dört profil optimizasyonu değildir. `researchReportSHA256` ve `researchVectorSHA256`, aynı klasördeki gerçek `repair-result.json` ve `vectors.npz` dosyalarına çözümlenir. Asıl 312 adaylı arama bu kaynaklardan **yeni 44 atama** kurar ve özgün maliyet amacıyla konum/kaynak kararlarını tekrar serbest bırakır.

Başlangıçta toplam 146 çok küçük pozitif/negatif akış artığı sıfıra çekildi; 44 profil üzerindeki toplam mutlak değişim yaklaşık **0,000076 kişi eşdeğeri** idi. Ham değerler ve her profilin değişimi saklandı. Bu düzeltmenin ardından özgün matris, kapsam, kapasite ve bütçe koşulları yeniden denetlendi. Önceden var olan sayısal kabul toleransları (%95 toplamda 0,001 kişi; ilçe oranında 0,000001 yüzde puan) genişletilmedi. Parasal bütçe denetimi kesin Decimal hesapla yapıldı.

## Devam eden sınırlar

Bu deney, zaman örneklemesine bağlı gösterilmiş açığı ele alır. Eksik gerçek EGO hizmetleri, tahmini ara durak süreleri ve giriş bağlantıları; gerçek klinik branş/FTE/vaka karması; tam kamu yatırım ve işletme maliyetleri ayrıca doğrulanmalıdır. Daha fazla saat örneklemek bu veri boşluklarını kapatmaz.

Eski 91 hastane deneyinin kaynakları ve dört başlangıç matrisi değişmemiştir. Bu çalışma o deneyin yeniden çalıştırılması veya gerçek Ankara'da 91 hastanenin yetersizliğinin kanıtı olarak sunulmaz. Ayrı kaynak açıklamaları: [ulaşım](transit-validation.md), [kapasite](capacity-research.md), [önceki ortak plan](joint-plan.md).
