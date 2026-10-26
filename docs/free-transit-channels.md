# Ücretsiz ulaşım kanalları · 26 Ekim 2026

Kullanıcı 26 Ekim 2026 tarihinde bunun ticari bir ürün olmayacağını ve eski ulaşım verisinin araştırma için uygun olduğunu netleştirdi. Bu nedenle seçilen yol, **tarihsel Ankara GTFS + ücretsiz MOTIS rotalaması**dır. Google Cloud veya ödeme hesabı kurmak gerekmez. Önce X→Y erişimi doğrulanır; yeni hastane optimizasyonu henüz çalıştırılmadı.

## Doğrudan test edilen kanallar

| Kanal | Gözlenen yanıt | Kullanım kararı |
|---|---|---|
| [Transitous/MOTIS plan API](https://transitous.org/api/) | Anahtarsız HTTP 200; Ankara koordinatları arasında otobüs/metro/yürüyüş ve saatli rota JSON'u | Tarihsel veri senaryosu için hazır, anahtarsız araştırma kanalı. |
| EGO mobil durak servisi | Kendi araştırma User-Agent'imizle, kimlik doğrulamasız HTTP 200 ve `status=TRUE`; 11634 için altı tablo satırı | Durak/hat hizmeti gözlenebilir. Bir X→Y yolculuk planlama API'si olduğu gösterilmedi. |
| [EGO hareket saatleri](https://www.ego.gov.tr/hareketsaatleri?hat_no=286) | HTTP 200; 286 hattı, üç gün türü ve 79 durak | Ücretsiz birincil tarife ve hat kontrolü. Ara durakların bütün gerçek varış saatlerini vermez. |
| Eski EGO `mobil/map.asp` | HTTP 410 | Çalışan erişim yolu olarak önerilmez. |

Pilot boyunca ücretli Google API çağrısı yapılmadı. Ödeme hesabı, API anahtarı veya ücretli yedek sağlayıcı kullanılmadı. Ham yanıtlar, istek parametreleri, gözlem zamanı ve SHA256 kimlikleri yerel `work/free-routing-research-2026-10-26/` klasöründe saklandı. Lisansı ayrıca doğrulanmamış Ankara GTFS arşivi yeniden dağıtılmaz.

## Seçilen kanal: tarihsel Ankara verisiyle Transitous / MOTIS

[MOTIS 2.10.2 OpenAPI tanımı](https://raw.githubusercontent.com/motis-project/motis/refs/tags/v2.10.2/openapi.yaml) kullanıldı:

```text
GET https://api.transitous.org/api/v6/plan
fromPlace=39.9220369,32.8514606
toPlace=39.9641447,32.8303145
time=2026-10-27T05:05:00Z
arriveBy=false
timetableView=false
```

Bu koordinatlar Kızılay ve Etlik Şehir Hastanesi örneğidir. Başlangıç 27 Ekim 2026 **08.05 TSİ**. Tekil CLI denemesi 41, 44 ve 45 dakikalık üç sağlayıcı tahmini döndürdü. Bunlar ölçülmüş süre veya doğrulanmış kapsama değildir. Araç ayaklarında gerçek zaman verisi bildirilmedi.

**Veri sürümü:** [Transitous Türkiye kataloğundaki](https://raw.githubusercontent.com/public-transport/transitous/main/feeds/tr.json) Ankara üst kaynağı yeniden indirildi: 21.990.864 byte, SHA256 `c070ea3486a6390d1e67c1ed78cca935e287187dbd6edd89f0608605bbf59419`. Bu, önceki araştırmada takvim/ara durak zamanı ve koordinat sorunları nedeniyle güncel resmî GTFS olarak reddedilen dosyanın aynısıdır. Canlı API kendi işlenmiş kopyasını kullanır; katalog üst kaynağının hash'i, sunucudaki işlenmiş kopyanın hash'i diye sunulmaz. Kullanıcı eski veriyi araştırma senaryosu için kabul etti. Önceki [GTFS değerlendirmesi](transit-research.md), dosyanın güncel resmî veri olmadığını açıklayan kaynak notu olarak korunur; bu senaryoda yaşından dolayı veri elenmez.

**Beklemeyi eksik saymama:** Varsayılan tarife görünümündeki örnek rota 08.13–08.51 için 38 dakika bildirdi. Kişi 08.05'te yola hazırsa erişim süresi **46 dakika** olur. Kod bu nedenle `varış − istenen başlangıç` hesabını kullanır. `timetableView=false` sabit başlangıç için seçilir; gelen zaman çizelgesi ayrıca kontrol edilir.

**Yürüyüş sınırını açık tutma:** Servisin erişim/çıkış yürüyüşü varsayılanı 15 dakikadır. Tekil araştırma komutunda erişim, çıkış ve doğrudan yürüyüş için açıkça 45 dakika istenir. Bu, bütün olası bağlantıların hesaplandığına veya sunucunun kısıtsız olduğuna kanıt değildir. `radius` ile sıfır süreli durak bağlantısı oluşturulmaz.

## Şimdi kullanılabilen tek komut

```powershell
.venv\Scripts\python.exe -X utf8 scripts/probe_free_transit.py --origin "39.9220369,32.8514606" --destination "39.9641447,32.8303145" --departure "2026-10-27T08:05:00+03:00" --out "work/free-transit-example-01"
```

Çıktı klasörü yeni olmalıdır. `response.raw`, `source.json` ve `summary.json` üretilir. Yanıt, hata veya boş sonuç hiçbir zaman üretim matrisine aktarılmaz; sonuç bulunamaması hizmet yokluğu diye yorumlanmaz. Toplu sorgu modu, otomatik tekrar ve ücretli sağlayıcıya geçiş bulunmaz. On yedi çevrimdışı test; başlangıç beklemesini, 45 dakika eşiğini, bozuk yanıtları, hata/boş sonucu ve saat dilimini kontrol eder.

[Transitous kullanım kuralları](https://transitous.org/api/) hafif, ticari olmayan açık kaynak/prototip kullanımını hedefler. Büyük/otomatik iş yükü ve 24 saatte 720'den fazla ilgili rota isteği için işleticiyle koordinasyon ister; bu sayı sınırsız kullanıma izin veren bir kota değildir. Milyonlarca çift bu ortak sunucudan çekilmemelidir. Yerel çalıştırma için veri indirilebilir; bu araştırmada yukarıda kimliği kaydedilen tarihsel Ankara senaryosu kullanılır.

## Yerel motor kuruldu ve sorgulandı

[MOTIS 2.10.2 Windows sürümü](https://github.com/motis-project/motis/releases/tag/v2.10.2) resmî kaynaktan indirildi. ZIP SHA256 değeri `e5002346a2acfa40dacbf3ee7873e3193b76111222fae4858780dc8b3835d1e9`, GitHub sürüm kaydındaki digest ile eşleşti. Motor; indirilen özgün Ankara GTFS arşivi ve projede bulunan 20 Ekim 2026 Ankara OSM yol kesitiyle yerel olarak içe aktarıldı. Tarihsel toplu taşıma + 2026 yol kesiti bir araştırma senaryosudur.

Yerel API: `http://127.0.0.1:8088/api/v6/plan`. Yalnız bilgisayarın kendisine açıktır. 26 Ekim–8 Kasım 2026 hizmet günleri içe aktarıldı. Başlangıç/çıkış/doğrudan yürüyüş ve hazırlanmış aktarma yürüyüşü üst sınırları 45 dakikadır. Bu hazırlık sınırları yeni bir kapsama kanıtı veya hastane optimizasyonu değildir.

Yerel motor, aynı Kızılay–Etlik örneğinde 27 Ekim 08.05 başlangıcı için **32 dakikalık M1-D → 206** seçeneği döndürdü (HTTP 200). Bu, özgün tarihsel dosyadan hesaplanan tahmindir. Kamusal servisin işlenmiş GTFS/OSM paketi ve ayarları ayrı olduğundan 41 dakikalık dış API örneğiyle aynı sonuç vermesi beklenmez; iki sonuç tek matriste karıştırılmadı.

```powershell
.venv\Scripts\python.exe -X utf8 scripts/probe_free_transit.py --local --origin "39.9220369,32.8514606" --destination "39.9641447,32.8303145" --departure "2026-10-27T08:05:00+03:00" --out "work/local-transit-example-01"
```

Motor kapanırsa bu bilgisayarda tekrar başlatma:

```powershell
Set-Location work/free-routing-research-2026-10-26/local-motis
..\motis-2.10.2\motis.exe server --data data --log-level error
```

Motor, veri ve büyük ön işlem çıktıları `work/` altında tutulur; GitHub'a ikili dosya veya GTFS kopyası yüklenmez. `source-manifest.json`, yapılandırma/GTFS/OSM/motor kimliklerini kaydeder. Sonuçların yeniden üretilebilmesi için ilk içe aktarma yapılandırması da bu klasördedir. Yeni kurulumda resmî [MOTIS hızlı başlangıç](https://github.com/motis-project/motis/blob/v2.10.2/README.md) yönergeleri izlenebilir.

**Karar:** Hemen kullanılabilen kanal Transitous API'si; büyük hesaplar için aynı tür açık kaynak motor MOTIS yerelde kuruldu ve çalıştırıldı. Ankara arşivi ücretsiz indirildi: **611 hat kaydı, 10.018 durak, 33.506 sefer ve 2.550.198 durak-zaman satırı**. Bunlar GTFS tablo sayılarıdır; benzersiz fiziksel hat/gerçek güncel sefer garantisi olarak sunulmaz. Ücretli API gerekmiyor. Yeni çalışma tarihsel/topluluk veri senaryosu olarak adlandırılır; mevcut güncel EGO kaynak deneyiyle karıştırılmaz.
