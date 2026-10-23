# Doğrulama ve 91 hastane deneyi · v0.7

23 Ekim 2026 TSİ. İl genelinde %95, her ilçede %80 talep; talep çarpanı 1, %80 yatak doluluğu, 2.140 temas/hekim/yıl ve %10 ek yıllık maliyet. Tutarlar yaklaşık Aralık 2024 TL; kısmi gider kalibrasyonu, saha ölçümü değildir. EGO örnekleri yeni ağla yeniden çözüldü. Araba modelinin sayısal planları korunup tekrar denetlendi; yeniden çözülmüş gibi sunulmaz.

## Kaydedilmiş tek profil kapasite çözümleri

Bu bölümdeki 261 tesis yalnız hafta içi 10.00 için bulunan önceki plandır. Daha sonra konumlar dört profil için birlikte seçildi: **209 konum / 26.400 yatak / 23.035 hekim**. Güncel ortak planın maliyet ve sabit kaynaklı süre aşamaları [ortak yerleşim](joint-plan.md) ve [süre denetimi](joint-travel.md) belgelerindedir; aşağıdaki tek profil kayıtları bu ayrı deneylerin yerine geçmez.

| Senaryo | Tesis | Yatak | Hekim | Ortalama süre | Yıllık eşdeğer maliyet |
|---|---:|---:|---:|---:|---:|
| Araba · 30 dk · sayı serbest | 46 | 18.550 | 21.590 | 17,32 dk | 143,88 mr TL/yıl |
| EGO · hafta içi 10.00 · 45 dk · sayı serbest | 261 | 27.800 | 23.534 | 29,06 dk | 183,93 mr TL/yıl |
| Araba · 30 dk · en fazla 91 | 46 | 18.550 | 21.590 | 17,32 dk | 143,88 mr TL/yıl |
| Araba · en fazla 91 · 835 temas/hekim duyarlılığı | 50 | 18.650 | 55.220 | 16,70 dk | 251,73 mr TL/yıl |

Araba/91 planı **46 tesisle** hedefleri sağlar: 31×50, 5×150, 3×300, 2×600, 2×1.000, 3×4.050 yatak tipleri seçildi. 5.614.804 kişi eşdeğerinin talebi karşılanır; ilçe paydaları konumu bilinmeyen nüfusu da içerir. Hekim sayısı her tesiste ayrı tam sayı olarak seçilir; sabit hekim/yatak oranı yoktur. Üniversite iş yükü duyarlılığında 55.220 hekim gerekir; bu, gözlenen 26.798 bütün-sektör hekim toplamıyla aynı kapsamda bir kadro mevcudiyeti garantisi değildir.

## İlk maliyet planı ve son plan

| Senaryo | Tesis: ilk → son | Yıllık maliyet: ilk → son (mr TL) | İlk maliyet açıklığı | Son maliyet açıklığı | Süre aşaması açıklığı |
|---|---:|---:|---:|---:|---:|
| Araba · sayı serbest | 46 → 46 | 143,95 → 143,88 | %1,89 | %1,84 | %67,02 |
| Araba · en fazla 91 | 46 → 46 | 143,95 → 143,88 | %1,82 | %1,77 | %60,98 |
| EGO · hafta içi 10.00 | 204 → 261 | 172,32 → 183,93 | %2,54 | %8,69 | %82,02 |

Maliyet alt sınırı her yapı izi sınıfından en yakın 12 aday bağlantısının tutulduğu **daraltılmış kaynak problemine** aittir. Tam aday bağlantıları için küresel maliyet sınırı değildir. İlk aşamanın açıklığı son planın açıklığı yerine kullanılamaz. Süre aşaması ayrı bir amaçtır; büyük açıklık daha iyi yerleşim olasılığını açık bırakır. Hiçbir kapasite planı minimum hastane sayısı kanıtı değildir. Süre sınırlı tekrar koşularında yerleşim ve kaynak sayıları değişebilir.

Kaynak temizliği aynı kabul edilen hasta akışını korur; boş tesisleri kapatır ve bu akış için en ucuz uygun yatak tipini/gerekli hekim sayısını kullanır. Sayısal olarak desteklenmeyen akış bulunursa doğrulanmış önceki çözüme dönüş açıkça kaydedilir. [Tam yöntem](methodology.md).

## 91 için EGO deneyi

| Profil | En fazla 91 | Gerekli coğrafi koşul |
|---|---|---|
| Hafta içi 08.00 · 45 dk · en fazla 91 | Bu modelde sağlanmıyor | Coğrafi alt sınır **165** |
| Hafta içi 10.00 · 45 dk · en fazla 91 | Bu modelde sağlanmıyor | Coğrafi alt sınır **167** |
| Cumartesi 10.00 · 45 dk · en fazla 91 | Bu modelde sağlanmıyor | Coğrafi alt sınır **170** |
| Pazar 10.00 · 45 dk · en fazla 91 | Bu modelde sağlanmıyor | Coğrafi alt sınır **168** |

4.701 aday ve süre içindeki bütün bağlantılar kullanılır. Yatak, hekim, maliyet ve yapı çakışması kaldırıldığında bile alt sınır 91'i aşıyor; aynı paketlenmiş modelde kaynak kısıtları bunu iyileştiremez. **Bu, gerçek Ankara için imkânsızlık veya kesin ihtiyaç sayısı değildir.** Eksik seferler, tahmini ara durak süreleri, aday örneklemesi ve mahalle temsil noktaları erişimi etkiler. Mevcut 91 hastanenin yer/kapasite envanteri test edilmiyor; sıfırdan en fazla 91 aday test ediliyor. Resmî 2024 envanteri 85'tir. [Kontrollü karşılaştırma](transit-validation.md).

## Aynı hastaneler farklı saatlerde yeterli mi?

Kayıtlı EGO planının **261 konumu, 27.800 yatağı, 23.534 hekimi** ve aynı **189,56 mr TL/yıl** tavanı korunur. Her profilde talep bu tesislere yeniden atanabilir; yıllık talep veya gider dört kez toplanmaz. Bütün seçili tesis bağlantıları kullanılır.

| Profil | Sonuç | İlçe koşulları altında en çok karşılanan talep |
|---|---|---:|
| Hafta içi 08.00 | İl hedefi sağlanmıyor | %92,506 |
| Hafta içi 10.00 | Hedefler sağlandı | %95,206 |
| Cumartesi 10.00 | İl hedefi sağlanmıyor | %85,757 |
| Pazar 10.00 | İl hedefi sağlanmıyor | %85,252 |

İlçe koşulları sağlanamıyorsa ana kapsama yüzdesi verilmez. İlçe tabanı kaldırılan tanı raporda ayrıca bulunur; bu değer asıl hedeflerin sağlandığı anlamına gelmez. Dört başlangıç profili bütün gün/yıl garantisi değildir. [Kimlikleri ve bütçesi bağlı rapor](../data/processed/robustness-results.json).

## Aynı yapı izlerinde kapasite artırımı yeterli mi?

Kayıtlı 261 konum ve yapı izi zorunlu açık tutulup dört profil için ortak yatak tipi/hekim sayısı seçildi. Sonuç: **`infeasible`**. Yeni konum veya daha geniş yapı izi seçilmedi; minimum hastane sayısı aranmadı. Kaynak tavanları ile yıllık maliyetler bir kez sayıldı. Orijinal bütçe 189,56 mr TL/yıldır.

Aşağıdaki **ayrı iyimser sınırda maliyet ve bütçe kaldırılır**; her alanda mümkün olan en yüksek yatak/hekim kapasitesi kullanılır, ilçe tabanları korunur. İl hedefinin altında kalan üst sınır, yalnız bu konum ve yapı izlerinde daha fazla kaynak satın almanın yetmediğini gösterir. Gerçek Ankara veya bütün adaylar için olanaksızlık değildir.

| Profil | En çok karşılanan talep | %95'e en az açık, kişi eşdeğeri | Denetim durumu |
|---|---:|---:|---|
| Hafta içi 08.00 | %96,963 | 0,00 | optimal |
| Hafta içi 10.00 | %96,542 | 0,00 | optimal |
| Cumartesi 10.00 | %92,094 | 171.772,19 | optimal |
| Pazar 10.00 | %91,074 | 232.051,81 | optimal |

[Paket, plan ve kaynak hashleriyle bağlı ortak kapasite raporu](../data/processed/shared-capacity-results.json). Zaman sınırı sonuçsuzluğu olanaksızlık olarak yorumlanmaz; bilinmeyen yüzdeler sıfır yapılmaz.

## Yüksek sayıyı ne açıklıyor?

İlk kayıtlı EGO atamasında 226 tesis 50 yataklı, 177 tesis 1.000'den ve 199 tesis 5.000'den az kişi eşdeğerine hizmet ediyor. Tesis doluluk medyanı %2,32; bu yatakla ağırlıklandırılmış il doluluğu değildir.

Haymana, Bala, Kızılcahamam, Çamlıdere, Kalecik, Ayaş, Güdül ve Nallıhan birlikte nüfusun %2,43'ini oluşturuyor. Yalnız bu sekiz ilçenin %80 koşulunu ortak bir yerleşimde sağlamak için 45 dk / hafta içi 10.00 coğrafi tanısının alt sınırı 135, bulunan sayı 135. İl geneli koşulu bu tanıda yoktur; ilçeler ayrı çözülüp sayıları toplanmamıştır. Düşük kullanım, erişim hedefleri ile en küçük tesis türünün birlikte incelenmesi gerektiğini gösterir; klinik uygunluk kanıtı değildir.

24 açık etiketli süre/ilçe duyarlılığı raporda ve arayüzde sunulur. Ana %95/%80/45 dk hedefleri bu deneyler nedeniyle değiştirilmedi.

## Bağımsız doğrulama

Python test paketi ve üretim derlemesi geçti. Kaydedilmiş yedi ana koşu ve 835 duyarlılığında tüm atamalar, nüfus paydaları, yatak/hekim, tam sayılık, yapı alanı/çakışma ve maliyet yeniden hesaplanır. Dört EGO profilinin sekiz başlangıcı × 4.825 hedefi bağımsız tek-başlangıç yönlendirmesiyle karşılaştırılır; bütün kullanılan kesitlerin fiziksel süre sınırları ayrıca denetlenir. Üç uzak durak ve 216 ek yön eşlemesinin özgün kenarları ham OSM ile, 49 özel sefer yorumu 9 gerçek kaynak arşiviyle kontrol edildi. Bu, saha seyahat süresi doğrulaması değildir.

Dört sağlık PDF'si ve sayısal kalibrasyon kontrol edildi. 4.701 yapı izinin yol/yüzey ray koridorlarıyla kesişimi yok; konumu bilinmeyen 20.516 kişi paydada kalır. Ulaşım paketi, kayıtlı örnekler ve sağlamlık raporu içerik kimlikleriyle bağlanır. Son hakem ve tarayıcı durumu [denetim kaydında](nightly-review.md) açıklanır.

```powershell
.venv\Scripts\python.exe -m pytest -q
npm run build
.venv\Scripts\python.exe scripts/verify_health_sources.py
.venv\Scripts\python.exe scripts/verify_transit.py
.venv\Scripts\python.exe scripts/verify_release.py
.venv\Scripts\python.exe scripts/audit_robustness.py
.venv\Scripts\python.exe scripts/audit_shared_capacity.py
```

Yeni örnekler için `verify_transit.py --write`, `verify_release.py --write-examples`, `audit_robustness.py --write`, `audit_shared_capacity.py --write`, son olarak `manifest.py` çalıştırılır. Kapasite kodu değişmeden araba planları korunuyorsa `verify_release.py --write-report` kullanılır. Süre sınırlı çözümler değişirse tablolar ve ekran görüntüleri güncellenmelidir. [Yeniden üretim ve kaynaklar](../data/README.md).
