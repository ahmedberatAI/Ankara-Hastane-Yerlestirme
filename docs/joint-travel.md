# Aynı kaynaklarla daha kısa yolculuk

[Ortak maliyet planı](joint-plan.md) dört başlangıç saati için aynı 209 konumu, 26.400 yatağı ve 23.035 hekimi seçmişti. Bu aşama **bu kaynakların tamamını sabit tutarak**, her profilde nüfusun tesislere dağılımını yeniden seçer. Yeni tesis açmaz, kapatmaz; yatak veya hekim eklemez. Dört profilin her birinde il hedefi %95, her ilçenin tabanı %80 ve atama başına süre sınırı 45 dakikadır.

| Başlangıç | Maliyet aşaması | Süre aşaması | Ortalama kısalma |
|---|---:|---:|---:|
| Hafta içi 08.00 | 31,68801645 dk | 28,13640755 dk | 3,55160890 dk |
| Hafta içi 10.00 | 32,36704689 dk | 29,12471027 dk | 3,24233663 dk |
| Cumartesi 10.00 | 32,42617860 dk | 30,39888253 dk | 2,02729607 dk |
| Pazar 10.00 | 32,82361778 dk | 31,07722317 dk | 1,74639461 dk |

Ortalamalar atanan taleple ağırlıklıdır. Hizmet verilen toplam nüfus aynı kalır; mahalle başına hizmet alan paylar değişebilir. Bu, aynı kişilerin tümünün daha kısa yolculuk yaptığı anlamına gelmez. Ayrı profiller yıllık sıklık ağırlıklarıyla birleştirilmedi.

Yıllık eşdeğer maliyet bağımsız ondalık hesapta yine **175.868.263.288,701820070258781870797300915922512 TL**. Bunun içindeki yıllık malzeme gideri **33.668.611.722,74399425 TL** yalnız bir kez sayılır. Kaynak temizliği yapılmadı. Ortalama kısalması için ek bütçe kullanılmadı.

## Bu hesabın kapsamı

Her profil için ayrı bir doğrusal atama problemi çözülür. Tüm seçilmiş tesislere, ilgili ulaşım matrisinde 45 dakika içinde kalan bütün aday bağlantılar kullanılır. Her mahalleden en fazla nüfusu kadar talep atanabilir; her tesisin yatak ve hekim sınırı ayrı korunur. Konumu bilinmeyen 20.516 kişi il ve ilçe paydalarında kalır.

Yeni dağılım 3.005 pozitif atama içerir. Her profilde %95 il kapsamı ve her ilçede en az %80,0402 kapsam sağlanır. En uzun pozitif atama 44,8923 dakikadır. Bunlar mevcut kısmi EGO modelinin sonuçlarıdır; gerçek tarifenin eksiksizliği anlamına gelmez.

Yeni atamaların aynı mahalle nüfusunun alt kümeleri olduğu varsayımında dört profilin ortak kişi kapsamı **%93,09262842–%93,23793987** aralığındadır. Kişi kimlikleri gözlenmediğinden aynı %95 kişinin tüm profillerde kapsandığı iddia edilemez. Eski maliyet aşamasının %92,677795–%92,780537 aralığı başka atamalara aittir. Arayüz bunları ayrı gösterir; mevcut ortak haritadaki tesis yükleri maliyet aşaması olarak etiketlidir.

## Alt sınır bağımsız nasıl denetlenir?

Amaç `min c·x`, koşullar `A·x ≤ b`, `E·x = d`, `0 ≤ x ≤ u` biçiminde kuruludur. `x` bin kişi eşdeğeridir. `T` kişi cinsinden il hedefi, `tⱼ` kayıtlı dakika süresi olmak üzere `cⱼ = tⱼ / (T / 1000)`. Böylece amaç doğrudan dakika cinsinden ortalamadır.

Denetçi optimizasyon yordamını veya onun alt sınır fonksiyonunu çağırmaz. Güncel nüfus, kaynak, sağlık ve dört ulaşım matrisinden bütün satırları ve bağlantı sırasını kendisi kurar. Her profil için kayıtlı çarpanların eşitsizlik kısmını `y ≤ 0` olacak biçimde keser. Sonra şu geçerli alt sınırı hesaplar:

```text
b·y + d·z + Σ min(0, c − Aᵀy − Eᵀz)ⱼ · uⱼ
```

Bu hesap, saklanan ikili kayan noktalı katsayıların **tam kesirli karşılıklarıyla** yapılır. Son terim, çarpanlar tam çift uygulanabilir olmasa bile sonlu değişken üst sınırlarını kullanarak farkı düzeltir. Bu nedenle çözücünün yalnız “optimal” etiketi kanıt olarak alınmaz.

Alt sınırın kesin kesir hesabı ile sayısal primal planın uygulanabilirliği farklı şeylerdir. Yayımlanan tam atamalardan yeniden hesaplanan dört profilin `ortalama − alt sınır` imzalı farkları yaklaşık **−2,49×10⁻¹⁴ / −2,13×10⁻¹⁴ / +1,03×10⁻⁹ / −6,75×10⁻¹⁴ dakika**. Sayısal tolerans **10⁻⁷ dakika**; küçük negatif farklar silinmez. Bu, tam rasyonel bir primal optimum veya tüm konum/büyüklük kararlarının optimumu iddiası değildir. Alt sınır yalnız bu sabit kaynakların, bu profilin ve bilgisayarda temsil edilen katsayıların atama problemine aittir.

## Dosyalar ve yeniden hesaplama

Maliyet aşamasının `joint-plan.json` ve `joint-plan-summary.json` dosyaları korunur. Yeni aşama ayrı dosyalardadır:

- `data/processed/travel-plan.json`: dört profilin tam pozitif atamaları ve sabit kaynaklar.
- `data/processed/travel-proof.json`: profil başına çarpanlar, alt sınır kesri, imzalı fark ve kabul/geri dönüş durumu.
- `data/processed/travel-summary.json`: bağımsız denetçinin arayüz için yeniden hesapladığı özet.

Kaynak maliyet sertifikasının tam SHA-256 kimliği `ac9c4e1031aa15d3ad1bc1b2d6b78b6094fa16ddb1ca035ee09bb31ae7bf9a93`. Sekiz model girdisi, kaynak sertifika ve ilgili güncel kod kimlikleri girişte ve çıkışta denetlenir. Üretim denetimi geliştirme klasöründeki eski arama kayıtlarını gerektirmez. Taşınan son atamalar ve çarpanlar yeniden doğrulanır; tarihsel arama yolunun tamamı yeniden oynatılmış sayılmaz.

Bu yayımlanan sonucun `executionOrigin.kind` alanı `reviewed_run_migration` olarak işaretlidir: yeni üretim komutuyla tekrar çözüldüğü iddia edilmez. Kaynak koşu kimliği `a094b92d491b1f6231084d28100c28cbe11d78a753e71f117470c716b3b0c9a4`, vektör kimliği `3bc5b1874954106af661f77719d5a1297c5f2da66ea9d86163cb48b13abaaf6e`. Süre gözlemleri o koşuya aittir; güncel dokuz kod kimliği taşıma ve yeniden denetimi bağlar. Normal kurulum tarihsel dosyaları okumaz, yalnız bu referansların biçimini kontrol eder. Asıl uygulanabilirlik ve alt sınır kanıtı, yayımlanan tam atamalar ve çarpanlardan güncel verilerle yeniden hesaplanır. Yeni komutla yapılan sonraki koşular `native_run` olarak işaretlenir.

```powershell
# Yayımlanan planı ve kesirli alt sınırlarını salt okunur denetle.
.venv\Scripts\python.exe scripts/audit_joint_travel.py

# Güncel maliyet sertifikası üzerinde yeni, en çok 60 saniyelik süre deneyi.
.venv\Scripts\python.exe scripts/run_joint_travel.py --seconds 60 --profile-seconds 15 --out work/joint-travel-next
```

Yeni çıktı klasörü deponun `work/` alanında olmalı ve önceden bulunmamalıdır. `--seed` başka bir tam maliyet sertifikası seçebilir. Koşu üretim dosyalarının üzerine yazmaz. Süre sınırı, bilinmeyen çözücü durumu veya sayısal doğrulama sorunu olan profilde **kaynağın bütün eski atamaları korunur**; olanaksızlık sonucu çıkarılmaz ve doğrulanmış alt sınır sunulmaz. Çıktı özeti hangi profillerin yeni atama kabul ettiğini açıkça belirtir. Denetçinin `--write` seçeneği yalnız doğrulanmış özetini günceller.

## 91 testi ve açık sorunlar

Ulaşım matrisleri, sağlık katsayıları ve 91 testinin hedefleri değişmedi. Bu nedenle aynı ağır 91 deneyleri tekrar çalıştırılmadı; mevcut dört coğrafi alt sınır **165 / 167 / 170 / 168** aynı veri kapsamında kalır. Yeni süre aşaması bu sınırları çürütmez ve gerçek Ankara'da 91 hastanenin yetersizliğini kanıtlamaz.

209 konumun 166'sı 50 yataklı model şablonudur. Asgari hekim, tesis türleri ve faaliyet giderleri hâlâ varsayımlar içerir; ayrı poliklinik/sağlık merkezi seçenekleri modellenmez. Bu plan minimum hastane sayısı veya klinik ihtiyaç envanteri değildir. EGO/Başkentray hizmet kapsamı, ara durak saatleri, klinik FTE, il dışı talep ve kamu işletme gideri eksikleri devam ediyor. Hakemlerin kabulü **matematiksel hesap ve kanıt zinciri kapsamındadır**; genel model başarısı ilanı değildir.

[Yerel uygulamadaki süre karşılaştırması](screenshots/ortak-sure-209.png) · [Alt sınır ve tolerans açıklaması](screenshots/ortak-sure-kaniti.png).
