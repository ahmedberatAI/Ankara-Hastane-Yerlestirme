# ERİŞİM · Ankara Hastane Yerleşim Laboratuvarı

Ankara’nın **25 ilçesinde**, belirlenen seyahat süresinde hedef nüfusa ulaşan **en az eşdeğer hastane sayısını** hesaplayan, harita üzerinde çalışan araştırma uygulaması.

Gerçek TÜİK mahalle nüfusları ve OpenStreetMap yol bağlantıları kullanılır. Mevcut binalar aday konumları engellemez; örnek yapı alanları karayolu ve yüzey demiryolu koridorlarının dışında seçilir. Mevcut hastaneler yeni yerleşimi kısıtlamaz; yalnızca ayrı bir erişim karşılaştırması sağlar.

> **Veri düzeyi:** Araba modu yönlü yol ağında tahmini süre hesaplar. EGO modu OSM güzergâhları, duraklar ve yürüyüş ağı üzerinde **tarifesiz bir senaryodur**. Güncel resmî GTFS doğrulanamadığından gerçek sefer saatleri, beklemeler ve hizmet takvimi kullanılıyor gibi gösterilmez. Bu sürüm kapasite, klinik ihtiyaç veya gerçek TL yatırım bütçesi hesaplamaz.

![ERİŞİM uygulamasının harita görünümü](docs/screenshots/overview.png)

## Kullanım

1. **Araba / EGO** modunu seçin.
2. En fazla yolculuk süresini, Ankara genelindeki erişim hedefini ve her ilçenin erişim tabanını ayarlayın.
3. **Yerleşimi hesapla** düğmesine basın. İlk açılışta araba senaryosu otomatik hesaplanır.
4. Bir mahalleyi arayıp seçerek önerilen hastaneye ağ üzerinden güzergâhı görün.
5. İlçe sonuçlarını açın, mevcut hastaneleri katman menüsünden gösterin veya senaryoyu kaynaklarıyla birlikte JSON olarak indirin.

Arayüz Türkçedir; kaynaklar, model açıklaması, veri açıkları ve çözümün optimalite durumu uygulamanın içindedir. Parametre değiştirildiğinde eski sonuç açıkça işaretlenir ve yeniden hesaplanana kadar dışa aktarma kapatılır.

## Yerel kurulum

Python **3.12** ve Node.js **22 veya 24** gerekir. Hazırlanmış veri dosyaları repoya dahildir; uygulamayı çalıştırmak için Türkiye harita verisini yeniden indirmek gerekmez. Harita altlığı ve web yazı tipleri internet kullanır; ağ matrisi ve optimizasyon yerel çalışır.

```powershell
git clone https://github.com/ahmedberatAI/Ankara-Hastane-Yerlestirme.git
cd Ankara-Hastane-Yerlestirme
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
npm ci
npm run build
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

**Uygulama:** <http://127.0.0.1:8000> · **API belgesi:** <http://127.0.0.1:8000/docs>

macOS/Linux için `python3.12 -m venv .venv` ve `.venv/bin/python` kullanın. Geliştirme sırasında Python sunucusuna ek olarak ikinci terminalde `npm run dev` çalıştırın; Vite `/api` isteklerini 8000 portuna yönlendirir. `npm run preview` tek başına Python servisini başlatmaz.

Tek komutla hazırlanmış yerel sürümü başlatmak için: `npm start` (önceden kurulmuş `.venv` ve `dist` gerekir).

## Hangi veri gerçekten kullanılıyor?

| Katman             | Kaynak ve sürüm                                                                                          | Bu sürümde durum                                      |
| ------------------ | -------------------------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| Nüfus              | [TÜİK ADNKS 2025](https://www.tuik.gov.tr/media/announcements/2025ADNKS_FavoriTablolar.xlsx), 31.12.2025 | 5.910.320 kişi; yayımlanan 1.427 mahalle              |
| Mahalle konumu     | OSM adları + ilçe poligonları                                                                            | 1.413 mahalle, 5.889.804 kişi konumlandırıldı         |
| Karayolu / yürüyüş | [Geofabrik Türkiye OSM kesiti](https://download.geofabrik.de/europe/turkey.html), 20.10.2026             | 1.303.779 düğüm, 1.864.240 yönlü sürüş kenarı         |
| Toplu taşıma       | OSM hat ilişkileri ve sıralı duraklar                                                                    | 337 yönlü hat kaydı, 5.984 durak; tarife kullanılmadı |
| Mevcut hastaneler  | OSM `hospital` kayıtları                                                                                 | 124 kayıt; resmî ve eksiksiz hastane listesi değildir |
| Maliyet            | Eşdeğer standart tesis varsayımı                                                                         | Hastane başına 1 birim; TL ve kapasite verisi yok     |

Konumu bilinmeyen **20.516 kişi paydadan çıkarılmaz**. Bu kişilere erişim kanıtlanmış sayılmaz. Dolayısıyla modelin kapsama oranı, yalnız eşleşen nüfusa bölünerek yapay biçimde yükseltilmez.

## Neden bu ölçüt?

Ana gösterge **seçili sürede bir hastaneye erişebilen nüfus / resmî toplam nüfus** oranıdır. [WHO AccessMod](https://www.who.int/tools/accessmod-geographic-access-to-health-care) coğrafi erişimi seyahat süresi ve kapsanan nüfus üzerinden inceler. Tesis sayısı–kapsama ilişkisi, [Church & ReVelle’nin kapsama yer seçimi yaklaşımıyla](https://doi.org/10.1111/j.1435-5597.1974.tb00902.x) uyumludur.

Önce il genelindeki hedef ve **her ilçenin ayrı erişim tabanı** altında hastane sayısı en aza indirilir. Ardından aynı sayıda tesisle kapsama artırılır ve kapsama koşullarını koruyan iki tur yer değiştirme ile nüfus ağırlıklı yolculuk süresi iyileştirilir. Ortalama tek başına kullanılmaz: küçük, uzak ilçeleri gözden kaçırabilir.

Başlangıç değerleri araba için **30 dakika**, EGO senaryosu için **45 dakika**, il genelinde **%95**, her ilçede **%80**’dir. Bunlar **değiştirilebilir planlama varsayımlarıdır; evrensel sağlık standardı değildir**. “Optimal”, yalnızca ayrık aday kümesi ve model varsayımları içinde en az hastane sayısı için geçerlidir. Gerçek şehrin sürekli coğrafyasında veya ortalama yolculuk süresinde global optimum iddiası yoktur.

## Araştırma ve teknik belgeler

- [Veri kaynakları araştırması ve eksik veri planı](docs/research.md)
- [Matematiksel model, ulaşım varsayımları ve sınırlar](docs/methodology.md)
- [Veri sözlüğü, köken ve yeniden üretim](data/README.md)
- [Hesaplanmış örnek senaryolar ve doğrulama](docs/validation.md)
- [Makine tarafından okunabilen kaynak kataloğu](docs/sources.json)
- [Veri kalite raporu](data/processed/quality-report.json)
- [Kaynak ve çıktı dosyalarının SHA-256 manifestosu](data/processed/manifest.json)

## Kontroller

```powershell
.venv\Scripts\python.exe -m pytest -q
npm run build
.venv\Scripts\python.exe scripts/verify_release.py
```

Testler küçük bir örnekte minimum tesis sayısını tüm kombinasyonlarla karşılaştırır; ilçe tabanını, erişilemeyen/konumsuz nüfusu, yönlü güzergâhı ve API girdi sınırlarını kontrol eder. `verify_release.py`, hazırlanan matris boyutlarını ve nüfus toplamlarını ve her iki modun gerçek veriyle çözüm/güzergâh tutarlılığını denetler. Ham OSM veri dosyası varsa `scripts/audit_data.py` tüm adayların yol ve yüzey ray koridorlarına taşmadığını ayrıca kontrol eder.

İlk çözüm işlemciye göre onlarca saniye sürebilir. İlk MILP aşaması 20, ikinci aşama en fazla 10 saniye ile sınırlıdır; yerel süre iyileştirmesi ek süre alır. Kanıt tamamlanmazsa mevcut geçerli çözüm, alt sınır ve optimalite açığıyla gösterilir. Ulaşılamayan hedef için hayalî sonuç üretilmez.

## Yapı ve dağıtım

```text
src/                  React + TypeScript + Leaflet arayüz
backend/              FastAPI, yönlendirme, SciPy/HiGHS optimizasyonu
scripts/              İndirme, OSM çıkarımı, ağ/matris üretimi, denetim
data/processed/       Sürümlenmiş nüfus, coğrafya, ağ ve süre matrisleri
docs/                 Kaynak araştırması, yöntem, doğrulama
tests/                Optimizasyon ve API testleri
```

FastAPI derlenmiş React arayüzünü de sunar. Python işlemi gerektiği için uygulama **GitHub Pages üzerinde tek başına çalışmaz**. Sunuculu dağıtım için Node derlemesini ve Python servisini içeren `Dockerfile` hazırdır; Docker ile çalıştırma bu geliştirme ortamında doğrulanmadı. İlk sürüm yerel/tek kullanıcı kullanımına yöneliktir; internete açık çok kullanıcılı kullanım öncesinde iş kuyruğu, istek sınırı ve kalıcı sonuç önbelleği eklenmelidir.

## Veri atfı

Nüfus: **TÜİK, ADNKS 2025** — [yeniden kullanım koşulları](https://www.tuik.gov.tr/Kurumsal/Yasal_Uyari).

Harita, yollar ve OSM kaynaklı türetilmiş veri: **© OpenStreetMap contributors**, [ODbL 1.0](https://www.openstreetmap.org/copyright). Türetilmiş veri dosyaları bu koşullarla paylaşılır; bu atıf üçüncü taraf verinin sahipliğini değiştirmez. Kod için ayrıca bir açık kaynak lisansı seçilmemiştir. [Veri atıf ve lisans notları](data/NOTICE.md).
