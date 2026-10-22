# Gerçek hastane verileriyle kalibrasyon · 22 Ekim 2026

Bu sürüm **kısmi ve şeffaf bir kalibrasyondur**. Talep resmî Ankara verisine; büyük ölçek gerçek hastanelere; işletme ve hekim iş yükü açıkça aktarılan gözlem proxy tutarlarına dayanır. Kamu hastanesinin tam muhasebe maliyeti, hekim FTE ve branş bazlı iş yükü bulunmadığı için tam klinik/mali kalibrasyon iddiası yoktur.

## Kullanılan gözlemler

| Kaynak | Doğrulanan gözlem | Modele etkisi |
|---|---|---|
| Sağlık İstatistikleri Yıllığı 2024 | Ankara: 85 hastane, 24.909 yatak, 26.798 hekim; 47.073.855 başvuru, 1.063.851 yatış, 5.409.136 yatış günü | Aynı yılın 5.864.049 nüfusuyla kişi başı talep; mevcut kaynaklar bağlam |
| Ankara Üniversitesi 2024, tablo 110, basılı s.160 / PDF 162 | Cebeci 1.097 yatak/921 hekim/694.180 ayakta/40.271 yatarak; İbni Sina 665/836/703.972/28.865 | Sabit hekim-yatak oranı kaldırıldı; toplam temas/hekim ≈835 duyarlılığı |
| Etlik resmî tanıtımı | 4.050 yatak, 1.145.129 m² kapalı alan | Büyük tesis ölçeği eklendi; plan kopyalanmadı |
| MLP 2024, basılı s.9 ve 44 / PDF 10,45 | 35 portföy hastanesi, yaklaşık 6.300 yatak, 7 milyon ayakta/yatan ziyaret; 444 bordrolu + 2.828 bordrosuz hekim | 7.000.000 / 3.272 = 2.139,36; 2.140 temas/hekim senaryosu |
| 2024 Yapı Yaklaşık Birim Maliyetleri, RG 32466, PDF 5 | Hastaneler V-B: 22.250 TL/m² | Ortak fiyat yılına çevrilmiş bina göstergesi; 2026 sınıf eşikleri aktarılmadı |

Kaynakların özgün URL, tablo/sayfa, erişim tarihi ve SHA-256 bilgisi [health-planning.json](../data/processed/health-planning.json) içinde. Ankara Üniversitesi ve MLP PDF’lerinde sayfalar hem metinden hem görüntüden kontrol edildi; 2024 tebliğinin hastane sınıfı görüntüden okundu. `verify_health_sources.py` aynı dosyaları ve sayıları tekrar denetler.

## İşletme gideri türetimi

MLP konsolide 2024 dipnot 19 ve 20 (basılı s.118–119 / PDF 119–120) **bin TL** verir. Aşağıda TL’ye çevrilmiştir. TMS29 nedeniyle Aralık 2024 satın alma gücündedir (PDF 96).

| Model katsayısı | Gerçek gider kalemlerinden türetim |
|---|---|
| Hekim başına yıllık gider | 9.994.192.000 / 3.272 |
| Yatak başına yıllık destek | (6.417.735.000 diğer personel + 2.245.638.000 dış hizmet + 2.533.955.000 diğer hizmet gideri) / 6.300 |
| Temas başına malzeme | 5.113.295.000 / 7.000.000 |
| Tesis başına yıllık sabit | (3.366.893.000 yönetim − 184.925.000 amortisman − 1.007.767.000 reklam) / 35 |

**Bu bölümler ölçülmüş kamu hastanesi birim maliyeti değildir.** Portföy göstergesi ile mali konsolidasyon kapsamı aynı değildir; yönetilen hastaneler, yan işler ve yabancı faaliyetler vardır. Yıl içi açılışlar ve yıl sonu kadrosu, yıllık ortalama paydalardan farklıdır. Özel sektör ücret/tedavi karışımı kamu hastanesine doğrudan taşınamaz. Sabit/değişken gider ayrımı da regresyonla tahmin edilmiş bir maliyet fonksiyonu değildir. Bu nedenle işletme katsayısı 0,5–2 duyarlılığı açıkça sunulur.

Ankara Üniversitesi raporundaki 6.282.744.302,45 TL hastane döner sermaye gideri (PDF 291) bütün merkezi bütçe ücretlerini kapsamayabildiğinden **toplam işletme gideri olarak kullanılmadı**. Raporlar arası eksik kapsam sessizce tamamlanmadı.

## Kaynak ve tasarım varsayımları

- Temas = başvuru + yatış. MLP’nin ayakta/yatan toplam ziyaretiyle kapsam uyumu için ikisi toplanır. Bunlar tekil hasta sayısı değildir. Bir yatış ile bir muayenenin süreleri eşit değildir; kaynakta gözlenen ortalama hizmet karışımı aktarılır, aktivite süreleri ölçülmez.
- 835 üniversite oranı eğitim/araştırma ve karmaşık vaka yükünü içerir. 2.140 özel grup oranı da güvenli azami kapasite değildir. WHO WISN için branş/aktivite süreleri ve kullanılabilir klinik çalışma saatleri gereklidir.
- Yatak tipi 50/150/300/600/1.000/2.000/4.050; hekim kadrosu bağımsız tam sayı. Asgari 12 hekim/tesis, alan `4.000 + 160 × yatak + 80 × hekim`, 9 kat sınırı birer tasarım varsayımıdır. Etlik büyüklüğü gerçek olmakla birlikte bu formül Etlik’in gerçek projesi değildir.
- %80 yatak doluluğu tercih edilen planlama tavanı; Ankara 2024 gözlemi %59,5. Daha yüksek tavan, mevcut yatak sayısına göre daha az yatakla aynı yıllık günü karşılayabilir. Pik talep, yoğun bakım, hemşire, branş, ameliyathane ve kuyruk garantisi sağlamaz.
- Kapasiteyi sürekli tek tipe bağlayan eski 0,6 hekim/yatak ve 300 yatak üst sınırı kaldırıldı. Eski 24 ve 172 sonuçları farklı modellerin çıktılarıdır; yeni sonuçla doğrudan aynı problem gibi karşılaştırılamaz.

## Ortak fiyat tabanı

2026 bina bedelleriyle 2024 giderlerini toplamak yerine yaklaşık **Aralık 2024 TL** kullanılır. 2024 tebliği 1 Ocak’tan geçerlidir; tutarın Ocak fiyat düzeyini temsil ettiği varsayılır. [TCMB/TÜİK](https://www.tcmb.gov.tr/wps/wcm/connect/TR/TCMB+TR/Main+Menu/Istatistikler/Enflasyon+Verileri/Tuketici+Fiyatlari) yayımlı Aralık yıllık %44,38 ve Ocak aylık %6,70 değişimiyle `1,4438 / 1,067` dönüşümü uygulanır. Bu yaklaşık genel satın alma gücü düzeltmesidir, inşaat maliyet endeksi değildir.

25 yıl ve %3 reel iskonto ile bina yatırımı yıllıklaştırılır; yıllık işletmeyle aynı birime gelir. Sabit reel işletme ve sıfır hurda değeri varsayılır. Amortisman ve finansman tekrar eklenmez. Cihaz yatırımı/yenilemesi, arsa, dış altyapı ve KDV/kurumlar vergisi eksik olduğundan çıktı **tam kamu bütçesi veya kesin yatırım önerisi değildir**. Formüller [yöntem](methodology.md), gerçek deneyler [doğrulama](validation.md) belgesinde.

## Tam kalibrasyon için sonraki veri

Hastane bazında aynı yıl/kapsamla yatak türü, branş, ortalama aktif hekim FTE, poliklinik/acil/yatış/ameliyat iş yükü; merkezi bütçe+döner sermaye ücret ve işletme giderleri; yatırım ve cihaz yenileme; hastanın ikamet kökeni ve sevk matrisi gerekir. EGO için resmî sefer takvimi/GTFS, gerçek yol trafik profili ve nüfusun mahalle içi dağılımı da erişim sonucunu değiştirebilir. Bu veri eksikleri uydurma kesinlik ile kapatılmamıştır.
