# Beş dakika sonraki yolculuk: 08.00 → 08.05

23 Ekim 2026 tarihli ek araştırma, kayıtlı dört başlangıç saatinin bütün güne güvence vermediğini gösteriyor. **Aynı 209 konum, 26.400 yatak ve 23.035 hekimle, türetilmiş 08.05 matrisinde %95 il hedefi sağlanamıyor.** Çözücü bildiriminin ardından ayrı bir kapasite sınırı hesaplandı ve kesir aritmetiğiyle doğrulandı. Bu sonuç yalnız bu sabit kaynaklar ve model matrisi için geçerlidir; gerçek Ankara'da kaç hastane gerektiğini söylemez. Mevcut dört profil sertifikası değiştirilmedi.

## Ne sabit tutuldu?

Hafta içi yolculuğa başlama saati 08.00'dan 08.05'e kaydırıldı. Hastaneler, kaynaklar, sağlık katsayıları, eksik nüfus dahil tam il/ilçe paydaları ve **%95 il / %80 her ilçe / 45 dakika** hedefleri aynı kaldı. Kaynak planın yıllık eşdeğer faturası yaklaşık **175,868 milyar TL**; bu, başarılı yeni bir 08.05 planının maliyeti olarak sunulmuyor. Yıllık hasta talebi yeniden eklenmedi.

Kısmi EGO ağı, resmî kalkışlar, tahmini ara durak süreleri ve giriş bağlantısı varsayımları korundu. Gecikme, trafik veya yeni hizmet verisi eklenmedi. Ağa dahil edilmeyen hizmetler gerçek hizmet yokluğu sayılmadı.

## Tam ulaşım hesabı

1.413 mahalle × seçili 209 hedef için iki başlangıçta **295.317'şer** süre hesaplandı. Bütün duraklar, hat örüntüleri ve aktarmalar aramada kaldı. Yalnız başlangıç satırları ve hedef sütunları bu araştırmaya ayrıldı.

| Kontrol | Sonuç |
|---|---:|
| 08.00 matrisinin üretimdeki aynı hedeflerle eşitliği | Bütün elemanlar birebir |
| Ayrı olay araması | 16 mahalle × 2 saat × 209 hedef |
| Bağımsız aramadaki en büyük süre farkı | 0,0000037847 dakika |
| 45 dakika sınırına yeni giren mahalle–tesis bağlantısı | 286 |
| 45 dakika sınırından çıkan bağlantı | 275 |
| En az bir hedefe 45 dakikada erişebilen nüfus: 08.00 | 5.686.361 |
| Aynı kapasitesiz erişim üst sınırı: 08.05 | 5.667.638 |

Bağlantı sayısındaki küçük net artış, nüfus kapsamının arttığı anlamına gelmiyor. Altı mahalle satırındaki **18.723 kişi**, seçili hedeflerin tümüne 45 dakika erişimini kaybediyor; başka hiçbir mahalle ilk kez erişim kazanmıyor. Bu sayılar yatak/hekim rekabetini içermez. İl hedefi **5.614.804 kişi** olduğundan, bu basit üst sınır tek başına hedefin olanaksızlığını kanıtlamaz. Bütün 25 ilçenin kapasitesiz üst sınırı da %80'in üzerindedir.

Her yolculuk aramasının ufku 120 dakikadır. Daha geç başlayan aramanın sonu da beş dakika kayar; yeni sonlu sürelerin bazıları yalnız bu ufuk farkından doğar. Ufuk dışında rota bulunmaması, gerçek hayatta ulaşımın olmadığı anlamına gelmez. Ortak sonlu çiftlerde mutlak varış sırası kayan nokta toleransıyla kontrol edildi; daha kısa yolculuk süresi daha erken mutlak varış demek değildir.

## Kapasite yeniden ataması

Önceki 08.00 süre planının 760 pozitif akışından **32'si**, yeni saatte 45 dakika sınırını aşıyor. Bu akışlar toplam **327.502,79 kişi eşdeğeri** içeriyor; yeniden dağıtım sonrası bu kadar kişinin kapsama dışında kaldığı söylenemez. Eski atama 08.05 için geçerli yedek çözüm olarak kullanılmadı.

Sabit kaynaklarla tek ek profilin atama programı çalıştırıldı. Yeni başlangıç açıkça `weekday-0805` olarak adlandırıldı. Üretim 08.00 problemine geri dönüldüğünde matris ve bütün amaç/kısıt katsayılarının birebir eşitliği, çalıştırmadan önce denetlendi. Hekim ve yatak kısıtları ayrı kaldı.

Tek gerçek çözücü çağrısı `status=2` (uygulanamazlık bildirimi) döndürdü. Çağrı anında bağımsız sertifika veya doğrulanmış bir yeni atama bulunmadığı için ham kaydın durumu **`inconclusive_without_validated_primal`**; `feasible`, ortalama, atamalar ve ikili kanıt alanları boş, `sourceFallback=false`. Bu tarihsel kayıt değiştirilmedi. Sonraki bağımsız kanıt aşağıda ayrı gösteriliyor. Hastane sayısı artırılmadı, hedefler gevşetilmedi.

## Çözücüden bağımsız kapasite sınırı

Bir ağ kesiti, 1.083 mahalle satırından 45 dakikada erişilebilen hedefleri 43 tesisle sınırlıyor. Bu taraftaki mahalleler 5.400.030 kişiyi içeriyor; hiç erişemeyen satırlar da bu grupta. Her tesis için nüfus kapasitesi, yatak ve hekim üst sınırlarının küçüğüyle sınırlı. Bu 43 tesiste 20 üst sınır yataktan, 23'ü hekimden geliyor.

Kesitin dışındaki 330 mahalleye tam nüfusları kadar hizmet verildiğini iyimser biçimde kabul etsek bile:

| Üst sınır hesabı | Kişi eşdeğeri |
|---|---:|
| Kesit içindeki 43 tesisin kapasitesi | 5.105.737,1995 |
| Diğer 330 mahallenin nüfus üst sınırı | 489.774,0330 |
| Toplam erişim ve kaynak üst sınırı | **5.595.511,2325** |
| %95 hedef, fiziksel sayısal tolerans düşüldükten sonra | **5.614.803,9990** |
| Hedefin altında kalan fark | **19.292,7665** |

Tüm 1.914 yasal mahalle–tesis bağlantısında kesit içinden dışarıya kaçış olmadığı denetlendi. Kapasite sınırlarına modelin satır toleransı eklendi; ilçe tabanları tamamen kaldırıldı. Dolayısıyla bu daha kolay problem bile il hedefini karşılayamıyor. Hesap gösterimde yuvarlansa da kanıttaki toplam ve karşılaştırma tam kesirlerle yapılıyor. Üst sınır il nüfusunun yaklaşık **%94,674**'ü; ulaşılabilecek kesin en yüksek kapsamın buna eşit olduğu iddia edilmiyor.

Tamsayı maksimum akış algoritması yalnız uygun kesiti buldu. Kanıtı kontrol etmek için akış algoritmasını veya LP çözücüsünü tekrar çalıştırmak gerekmiyor: kesit üyeleri, bütün yasal kenarlar ve kaynak üstleri yeterli. Ulaşım ve veri hakemleri bu kesiti ayrı kesir hesaplarıyla doğruladı; ayrıca yeniden kurulan LP satırlarıyla karşılaştırıldı. Bu **sabit 209 kaynak düzeninin** 08.05'teki başarısızlığıdır; başka kaynak dağılımının, yeni konumların, 91 hastanenin veya gerçek EGO hizmetinin olanaksızlığı değildir.

## Kabul ve sınırlar

Ulaşım ve veri hakemleri tam başlangıç matrisini, seçili bağımsız olay aramalarını, kimlikleri ve nüfus hesaplarını doğruladı. Atama yordamındaki değiştirilebilir bellek kaynağı/matrisi sorunu çalıştırmadan önce kapatıldı. 35 odaklı atama/kimlik testi ile yedi yönlendirme testi geçti. Gerçek sonuç ayrıca kaynak, kaynak faturası ve doğru boş durum alanları açısından incelendi. Tam yönlendirme 44,322 saniye; atama ön denetimi ve gerçek çağrının kaydı toplam 1,297 saniye sürdü. Bunlar gözlenen sürelerdir, genellenmiş performans garantisi değildir.

Bu ek deney **91 hastaneyi sınamaz**, dört mevcut başlangıç sertifikasının yerine geçmez, gün boyu güvenilirlik veya gerçek Ankara ihtiyacını ölçmez. Aynı mahallelerden başka oranlar atanabileceği için olası saatler arası ortalama farkı aynı kişilerin kazancı olarak yorumlanamaz. Üretim girdileri değişmediğinden eski 91 deneyleri yeniden çalıştırılmadı.

## Denetlenebilir kayıt

Kaynak paket: `ego-da0980e2b9057e21065f4b018a9e935d994f89f52572e08db4546710cf3eb997`.

| Kayıt | SHA-256 |
|---|---|
| Tam yönlendirme raporu | `b9f60e61b3bbee0c3aadf670e8f400338fa95dae015bdd590d3d5243096e4eb0` |
| 08.00 / 08.05 matris arşivi | `51b24496428a2d84f614c6809779aea5576512a8867bf7d6b0a519179070faab` |
| Gerçek atama çalıştırma kaydı | `2c550293f1121c3cbbdf3b5dd03698b9404a6c7f8b26b8c75646d0a37827b131` |
| Ayrı tam kesir kapasite sınırı | `a33d3e0d93df8efa367fe15189220d43ae38e08bbac638ce0f4be68e718fa9d7` |

[Araştırma arşivi](experiments/departure-0805-evidence.zip), özgün `work/referees/` yollarını koruyan değişmemiş kod, test, pilot/tam matris, sonuç ve hakem kayıtlarını içerir. [Dosya manifestosu](experiments/departure-0805-manifest.json) ham dosya SHA-256 değerlerini verir; raporlardaki kod kimlikleri ayrıca CRLF→LF normalleştirilmiştir. Bu arşiv üretim veri paketine eklenmiş yeni bir profil veya uygulamanın okuduğu dinamik sonuç değildir.

Arşiv, **aynı kaynak sürümündeki ayrı bir repo kopyasının köküne**, var olan dosyaları ezmeden açılabilir. Kaynak kimliklerinin ve başlangıç katsayılarının çözücü çağırmadan ön denetimi:

```powershell
.venv\Scripts\python.exe work/referees/run_departure_sensitivity.py
.venv\Scripts\python.exe work/referees/audit_departure_cut.py
```

İlk ön denetim kayıtlı gerçek LP sonucunu yeniden denetlemez; sonuç baytları manifestoya ve arşivdeki bağımsız hakem kayıtlarına bağlıdır. İkinci komut kesit üst sınırını yeniden kurulan LP satırları ve bütün yasal kenarlarla, çözücü çağırmadan doğrular. Aşağıdaki küçük testler sentetik çözücü denemeleri içerir, gerçek 209 tesis deneyini yeniden çalıştırmaz:

```powershell
.venv\Scripts\python.exe -m pytest work/referees/test_profile_shift_pilot.py work/referees/test_profile_shift_full.py work/referees/test_departure_sensitivity_lp.py work/referees/test_run_departure_sensitivity.py -q
```

İlk komut yalnız ön denetimdir. Kaydedilmiş gerçek çalıştırma sonucu ile yeni bir çalıştırma karıştırılmaz; mevcut sonuç dosyası varken `--run` üzerine yazmayı reddeder. Kaynak kimliği değişirse ön denetim de reddeder.
