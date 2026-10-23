# Kapasiteyi ulaşım etkisinden ayıran 91 tesis kontrolü

**Ulaşım kısıtları kaldırılmış modelde 91'in altında uygun bir plan var:** kayıtlı araba planının aynı 46 konumu, 18.550 yatağı, 21.590 hekimi ve atamaları, il genelinde %95 ve her ilçede %80 talep hedefini karşılıyor. Yıllık eşdeğer maliyeti **143,878 milyar TL**, kayıtlı EGO planının **189,557 milyar TL** yıllık tavanının altında. Tutarlar yaklaşık Aralık 2024 sabit fiyatlarıyla model göstergeleridir.

Bu sonuç, mevcut EGO deneylerindeki yüksek coğrafi sınırların yalnız toplam yatak ve hekim ihtiyacından kaynaklanmadığını gösterir. **Gerçek EGO hizmetiyle 91 hastanenin yeterliliğini veya 46'nın minimum olduğunu göstermez.**

## Ne korunuyor, hangi koşul kaldırılıyor?

| Unsur | Tanıdaki işlem |
|---|---|
| İl / ilçe talebi | %95 / %80 hedefleri ve nüfus paydaları korunur; konumu bilinmeyen nüfus paydadan çıkarılmaz. |
| Konumlar ve yapı izleri | Kayıtlı 46 aday konumu aynıdır. Yapı alanı ve konumlar arası çakışma denetlenir. |
| Yatak ve hekim | Seçilen modüller ve tam sayı kadrolar korunur; iki kapasite ayrı kontrol edilir. |
| Sağlık ve maliyet katsayıları | EGO kaydıyla aynı talep çarpanı, doluluk, hekim temas oranı ve işletme çarpanı zorunludur. |
| Yıllık bütçe | Mevcut EGO planının yıllık tavanı korunur. Bina yıllıklaştırması, işletme ve malzeme yeniden hesaplanır. |
| Ulaşım | Süre, erişilebilirlik, hat, takvim ve aktarma kısıtları kaldırılır. Bütün konumlandırılmış mahalle–aday çiftleri kullanılabilir sayılır. |

Araba yolculukları EGO sürelerine dönüştürülmez; bu kontrolde yolculuk süresi hiç kullanılmaz. Aynı talep atamaları dört alternatif profil için kopyalanabilir. Bu, dört farklı ulaşım doğrulaması değil, ulaşımın kaldırıldığı tek kaynak tanığının dört senaryoya da uygulanabilmesidir. Yıllık talep ve gider dörtle çarpılmaz.

## Nasıl denetleniyor?

Yeni optimizasyon çalıştırılmadan kayıtlı planın bütün talep atamaları toplanır. Hiçbir mahalle nüfusu aşılmaz; kapalı veya yanlış kimlikli adaya atama yapılamaz. İlçe paydaları, her tesisin yatış günü ve hekim temas yükü, modül büyüklüğü, hekim alanı ve yapı izlerinin ayrıklığı kontrol edilir. Tamsayı kadro koşulu korunur.

Maliyet Decimal aritmetiğiyle tekrar hesaplanır. Malzeme gideri tek yıllık talep üzerinden alınır; iki veya dört kez sayılması reddedilir. Sayısal toleranslar raporda açıkça kayıtlıdır. Bu, tam rasyonel bir ispat veya klinik iş yükü standardı değildir.

Rapor dört kaynak dosyasının tam SHA-256 kimliğine ve denetleyici kodunun satır sonu normalize edilmiş kimliğine bağlıdır. Salt okunur doğrulama güncel dosyalardan sonucu yeniden üretir; kaynağı, hesap sonucu, türü veya kod kimliği değişen kayıt kabul edilmez. Uygulama da ulaşım paketi, sağlık sürümü, 91 sınırı ve %95/%80 kapsamı eşleşmeyen kaydı olumlu sonuç olarak göstermez.

```powershell
.venv\Scripts\python.exe scripts/audit_transport_relaxation.py
```

`--write` güncel kaydı üretir. Kaynak plan 91'i veya bütçeyi aşarsa sonuç yalnız **bu plandan uygun tanık bulunamadı** olur. Başka yerleşimler aranmadığından olanaksızlık veya küresel optimum iddiası üretilemez.

## Açık sınırlamalar

Klinik branş, vaka karışımı, FTE ve Ankara dışından gelen hasta talebi bu tanıyla doğrulanmış olmaz. Temas/hekim ve işletme gideri katsayıları mevcut araştırma varsayımlarıdır. Aynı şekilde ulaşımın kaldırılması, eksik EGO/Başkentray/dolmuş hizmetini ölçmez veya tamamlamaz.

45 dakikalık gerçek EGO erişimi için resmî hizmet, durak/peron bağlantısı ve ara saat kalitesi ayrıca geliştirilmelidir. [Başkentray kaynak kontrolü ve açık peron sorunu](baskentray-research.md), [mevcut dört 91 deneyi](transit-validation.md), [kapasite ve maliyet kaynakları](capacity-research.md).
