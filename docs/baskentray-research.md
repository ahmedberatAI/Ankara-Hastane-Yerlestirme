# Başkentray: doğrulanan tarife ve açık erişim sorunu

23 Ekim 2026 kaynak kontrolünde iki yönde **146 trenin 24 istasyondaki 3.504 yayımlanmış saati** bulundu ve karşılaştırıldı. Bu tarife henüz hastane yerleştirme hesabına eklenmedi. İstasyon peronunu yürüyüş ağına bağlamak için gerekli kat ve giriş kanıtı tamamlanmadı. Modelde Başkentray bağlantısı bulunmaması, gerçek hizmetin bulunmadığı anlamına gelmez.

## Hangi tarife?

[TCDD günlük tren saatleri sayfasının resmî içerik kaydı](https://baskentrayadminapi.tcddtasimacilik.gov.tr/api/BaseSelectBaskentray/GetPageByIdAsyncBaskentray?id=171), 15 Aralık 2024 başlangıç geçerliliğini bildiriyor ve şu iki tabloya bağlantı veriyor:

| Yön | Yayımlanmış trenler | Kalkış / son varış | Yolculuk |
|---|---|---|---|
| [Sincan → Kayaş](https://adminapi.tcddtasimacilik.gov.tr/files/public/de1c8187-5dd7-4afa-8e7b-4a8a4263d689-S%C4%B0NCAN-KAYA%C5%9E%202025.pdf) | 73, çift numaralar | 06.00–23.30 / ertesi gün 00.19 | 49 dakika |
| [Kayaş → Sincan](https://adminapi.tcddtasimacilik.gov.tr/files/public/d998ed15-2ca6-48a5-9b1d-47a83803d66c-KAYA%C5%9E-S%C4%B0NCAN%202025.pdf) | 73, tek numaralar | 06.00–23.30 / ertesi gün 00.19 | 49 dakika |

Her trenin bütün istasyon saatleri, tren numarası ve tablo konumu kontrol edildi. Gece yarısını geçen varışlar aynı hizmet gününde 24.00'ı aşan süreler olarak tutuldu; son varış 24.19. Ortalama sıklıktan yeni kalkış saatleri üretilmedi.

**Hafta içi kapsamı bir kaynak değerlendirmesidir.** PDF'lerde ayrı gün takvimi yok. Bağlantı veren sayfanın hafta içi yoğun dönem açıklaması ile tablodaki 12/15/30 dakika aralıkları birlikte değerlendiriliyor. Hafta sonu saatleri, tatil istisnaları ve bitiş geçerliliği doğrulanmadı. Bu nedenle aynı trenlerin cumartesi ve pazara kopyalanması kabul edilmedi.

Aynı sayfada 2023 belge metadatası taşıyan eski tabloya ait başka bir bağlantı da kalmış: ikinci sabah kalkışı 06.11; seçilen 2025 tablosunda 06.12. Seçim, dosya adının yanında sayfadaki 12 dakikalık rejim ve belge tarihiyle uyuma dayanıyor. Eski ve yeni tablolar birleştirilmedi. Gözlem tarihi, tarifenin geçerlilik başlangıcı ve belgenin oluşturulma tarihi ayrı kavramlardır.

## Ray yolu ile peron erişimi ayrı kanıtlar

[Resmî sıralı istasyon dosyası](https://www.tcddtasimacilik.gov.tr/assets/BaskentrarGuzergah.txt) ile iki tarifenin sırası ve süreleri eşleşiyor. Buradaki Eryaman Banliyö / PDF'deki Eryaman YHT ad eşleşmesi, komşu duraklar ve sürelerle belgelenmiş bir çıkarımdır; giriş koordinatı değildir.

20 Ekim 2026 OSM kesitinde `14118633` ve `14118634` ray ilişkileri bağımsız denetlendi. Her yönde 24 durak, bağlantılı ve dallanmayan ray zinciri üzerinde doğru sırada. 46 istasyonlar arası parça ham yol üyelerine bağlı. Ancak `stop_position` ray üzerindeki araç konumudur; yolcu girişine eşitlenemez.

İlk yürüyüş prototipinin 19 bağlantı adayı bağımsız incelemede kabul edilmedi:

- **Cebeci:** perona yakın görünen nokta üst geçidin üst ucuydu. Önerilen kısa düz bağlantı merdivenle inmeyi atlıyordu.
- **Havadurağı:** seçilen üniversite tarafı girişinin OSM notunda asker kontrolü ve öğrenci kimliği koşulu var. Başka giriş seçmek, ortak yürüyüş grafiğinin kısıtlı geçidi kullanmasını tek başına engellemiyor. Bu bulgu bütün istasyonun kapalı olduğu anlamına gelmiyor.
- **Diğer 17 aday:** peron geometrisi içindeki merdiven uçlarına dayanıyor. Merdiven yönü ve kat etiketleri eksik; hangi ucun peron seviyesinde olduğu yeterince doğrulanmadı.

Yürüyüş yolu kenarına izdüşüm de tek başına çözüm değil. Platformla düzlemde kesişen bir araç yolu, farklı katta olabileceği için peron bağlantısı sayılamaz. Eksik kat bilgisi zemin kat kanıtı olarak kullanılmıyor. Bekletilen kayıtlar gerçek erişim yokluğu sayılmıyor.

## Modele eklenmeden önce

Her yön için peron–giriş–yürüyüş yolu bağlantısı ve kat geçişi kanıtlanmalı; kısıtlı girişler yürüyüş grafiğinde ele alınmalı. Normal hafta içi kapsamı ve bilinmeyen hafta sonu/istisna takvimi açıkça ayrılmalı. Yayımlanmış istasyon saatleri, otobüsler için kullanılan tahmini ara süre dağıtımına sokulmamalı: mevcut ray geometrisinde bazı nominal kesit ortalamaları 84,12 km/saate ulaşıyor; genel 80 km/saat varsayımı ve ek bekleme payı bu resmî saatleri değiştirebilir. Bu hız değeri ölçülmüş araç hızı değildir.

Entegrasyondan sonra yeni kaynak kimliğiyle yolculuklar, dört 91 tesis deneyi ve ortak kapasite sonuçları yeniden doğrulanmalı. Şimdiki **165 / 167 / 170 / 168** coğrafi alt sınırları, Başkentray eklenmiş bir ağın sonuçları değildir.

## Kaynak kimlikleri ve kabul kapsamı

| Kaynak | SHA-256 |
|---|---|
| Resmî sayfa içerik yanıtı | `0c61000090ccd7f03a657ac233d225a0fe0c9410dacce828d3f2955c62bd04b3` |
| Sincan → Kayaş PDF | `5ac94a5c6958981acce1ddd973dee0a506156ecc3ce86de6c4b7e7a53ce23050` |
| Kayaş → Sincan PDF | `65bd70338b000ad3c67688aca5736684e13760570c24ffa90223ea2a9923f6f6` |
| Resmî istasyon sırası | `d526204a305f43ab47cac3b0470dedad4837204f44744bb3ff3a5a594e0770ef` |

Ham HTTP arşivleri, tablo transkripsiyonu ve bağımsız geometri incelemeleri yerel araştırma dosyalarında tutuluyor; TCDD PDF tasarımları bu depoya yeniden dağıtılmıyor. Kamuya açık erişim, açık yeniden kullanım lisansı olarak sunulmuyor. TCDD ve OSM kaynaklarının kökenleri ayrıdır.

Kaynak hakeminin kabulü tablo transkripsiyonu ve sınırlı hafta içi yorumuna; ray incelemesinin kabulü OSM zincir tutarlılığına aittir. Peron erişimi ve Başkentray'ın üretim modeline entegrasyonu kabul edilmedi.
