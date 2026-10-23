# Yol hesabındaki varsayılan giriş bağlantıları

23 Ekim 2026. Kayıtlı **209 konum / 26.400 yatak / 23.035 hekim** içeren ortak EGO planının süre aşaması incelendi. Bu tanı mevcut atamaların bileşen hesabıdır; yeni bir yerleşim veya yeniden yönlendirme deneyi değildir.

## Hangi iki parça sayılıyor?

Mahalle temsil noktasından yol düğümüne kısa bağlantı ve yol düğümünden varsayılan hastane sahasına giriş. `dataset.json` bu uzunlukları sırasıyla `snapMeters` ve `accessMeters` olarak taşır. İkisi de 1,25 m/s, yani 75 m/dakika ile süreye eklenir. Hastane bağlantısı gerçek bir servis yolu projesi değildir. Başlangıç bağlantısı da her evden çıkışı temsil etmez.

Bu tanı durak–yürüyüş düğümü bağlantılarını, peron girişlerini, araç yoluna durak eşleştirmelerini veya ağın diğer doğruluk sorunlarını kapsamaz. OSM üzerinde rota bulunması, saha erişiminin doğrulandığı anlamına gelmez. [Konum ve ağ varsayımları](methodology.md#talep-noktaları-ve-konum-belirsizliği) ayrıca geçerlidir.

## Hesap

Her profilde pozitif atama miktarı `xᵢⱼ`, temsil bağlantısı `aᵢ`, hastane bağlantısı `bⱼ` ve kayıtlı toplam süre `tᵢⱼ` olsun:

```text
İki bağlantının süresi: cᵢⱼ = (aᵢ + bⱼ) / 75
Ortalama bağlantı süresi = Σ(xᵢⱼ × cᵢⱼ) / Σxᵢⱼ
Toplam kişi-dakika içindeki pay = Σ(xᵢⱼ × cᵢⱼ) / Σ(xᵢⱼ × tᵢⱼ)
```

Ortalama bağlantı süresinin paydası her profilde atanan **5.614.804 kişi eşdeğeridir**. Yüzde hesabının paydası ise aynı atamaların **toplam kişi-dakikasıdır**. Dört profil birbirine eklenmez. Kişi eşdeğeri, gözlenen tekil yolcu sayısı değildir. Ankara'nın 5.910.320 nüfusu, konumu modellenen 5.889.804 kişi ve konumsuz 20.516 kişi ayrı kalır; konumsuz nüfusa giriş süresi uydurulmaz.

| Başlangıç profili | Temsil bağlantısı | Hastane bağlantısı | İkisinin toplamı | Toplam kişi-dakikadaki pay |
|---|---:|---:|---:|---:|
| Hafta içi 08.00 | 0,1212 dk | 6,0721 dk | 6,1933 dk | %22,0116 |
| Hafta içi 10.00 | 0,1209 dk | 6,0720 dk | 6,1929 dk | %21,2635 |
| Cumartesi 10.00 | 0,1209 dk | 6,0714 dk | 6,1923 dk | %20,3701 |
| Pazar 10.00 | 0,1205 dk | 6,0709 dk | 6,1914 dk | %19,9227 |

Bağlantı ortalamaları birbirine yakınken paylarının farklı olması, profillerin toplam yolculuk sürelerinin farklılığını da yansıtır. Büyük hastanelerin erişim bağlantıları daha uzun olabildiğinden yalnız tesislerin eşit ağırlıklı ortalaması yolcu yükünü anlatmaz; burada atanan talep kullanılır.

## Ne sonuç çıkarılamaz?

**6,2 dakika, kaldırılabilir gecikme veya ölçülmüş hata değildir.** Bağlantıları kısaltmak ya da kaldırmak, durağa varış zamanını, yetişilen seferi, beklemeyi ve 15 dakikalık erişim kapısını değiştirebilir. Mevcut toplam süreden bu bileşeni çıkarmak yeni bir tarifeli yolculuk üretmez. Payın geri kalanı da doğrulanmış gerçek süre olarak yorumlanamaz.

Bu sonuç giriş yollarının ve mahalle içi dağılımın ayrıca doğrulanmasının önemini nicelleştirir. Bağlantılar keyfî olarak sıfırlanmadı; hedefler, kapasite katsayıları ve ulaşım matrisleri değiştirilmedi. Kayıtlı 91 hastane deneyleri bu tanıdan etkilenmez.

Haritada kesikli çizgiler varsayılan giriş bağlantılarını, kesintisiz turuncu çizgiler OSM yürüyüş ağını gösterir. Araç ve ray kesitleri kendi renkleriyle kesintisizdir. Bu çizim ayrımı, varsayımsal bir bağlantıyı gerçek yol sanmayı önlemek içindir.

## Yeniden denetleme

`python scripts/audit_access_connectors.py` salt okunur çalışır: kayıtlı süre planını ve bağımsız süre kanıtını doğrular, pozitif atamalardan bu bileşenleri yeniden hesaplar ve `data/processed/access-connector-summary.json` ile karşılaştırır. Yeni optimizasyon çalıştırmaz. Özet, süre özeti ve planı, 11 kaynak dosyası, dokuz model kodu ve üç analiz/bileşen kodunun kimliklerine bağlıdır. `--write` yalnız bu özeti atomik olarak yeniden üretir; ardından `python scripts/manifest.py` ile dosya manifestindeki SHA-256 kayıtları güncellenir. Arayüz kaynaklar uyuşmadığında eski sayıları göstermez.

Üretici hesabı ulaşım ve kanıt hakemlerinin bağımsız hesaplarıyla karşılaştırıldı. Kabul, bu iki model bileşeninin doğru toplanmasına aittir; bağlantıların gerçek dünyadaki geçerliliğine verilmiş bir onay değildir.
