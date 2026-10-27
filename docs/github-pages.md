# Önceden hesaplanmış web yayını

Bu sürüm aynı doğrulanmış kalıcı planı ve haritada seçilebilen **2.061 pozitif atamanın tamamını** sunar: 1.202 araba, 859 kritik toplu taşıma kesiti. Plan, kaynak ve tarih kimlikleri yerel sürümle aynıdır. Ziyaret sırasında Python, optimizasyon veya MOTIS servisi çalışmaz. Harita, mahalle arama, iki ulaşım görünümü, alternatif atama seçimi ve güzergâh inceleme tarayıcıda kullanılabilir. Harita altlığı ve yazı tipleri internet kullanır.

## Paketleme

```powershell
# Yalnız yeni plan/rota paketi hazırlarken: yerel uygulama ve MOTIS açık olmalı.
.venv\Scripts\python.exe scripts/capture_public_routes.py --write --workers 3

# Mevcut doğrulanmış kayıtları denetler ve statik siteyi üretir; yeni rota sorgulamaz.
npm run build:pages

# Python'a ve API'ye bağlanmayan, yalnız dosya sunan yerel önizleme.
npm run preview:pages
```

Varsayılan önizleme: `http://127.0.0.1:4173/Ankara-Hastane-Yerlestirme/`. Çıktı `dist-pages/` klasörüdür. `npm run build` ve `npm start` mevcut yerel API sürümünü üretip çalıştırmaya devam eder. Başka bir Pages depo adı için derlemede `PAGES_BASE_PATH=/DEPO_ADI/` verilir; alan adı kökü için `/` kullanılır.

Rota kayıtları `data/precomputed-routes/` içinde plan kimliğine ve plan dosyasının SHA-256 değerine bağlıdır. Her kaydın isteği, yanıtı, yakalama zamanı ve yakalama kodu kimliği saklanır. Yakalama yalnız pozitif atamalara yapılır; başarısız bir sorgu gerçek hizmet yokluğu sayılmaz ve eksik paket tamamlanmış diye yayımlanmaz. Tekrar çalıştırma, aynı planın doğrulanmış kayıtlarından devam eder.

Yayın derleyicisi planın bağımsız fiziksel denetimini ve bütün rota kayıtlarını yeniden doğrular. Açık bir dosya listesiyle yalnız gerekli veri ve geometriyi pakete koyar; yerel motor, ağ grafikleri, çalışma klasörü, kimlik bilgileri veya bütün depo kopyalanmaz. Yayın verisi yaklaşık **27 MB**'dır. Tarayıcı, istenen dosyanın boyutunu ve SHA-256 değerini denetler; eksik/karışmış kayıtta canlı API'ye sessizce geçmez. Statik yayın, hedeflerin açıklamasını da `method.html` içinde barındırır; arkadaşların özel kaynak depoya erişmesi gerekmez.

## GitHub Pages'i açma

[GitHub'ın belgesine](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages) göre depo **Settings → Pages → Source: GitHub Actions** olarak ayarlanır. `.github/workflows/pages.yml` doğrulama ve paketlemeyi çalıştırır. Gerçek dağıtımı etkinleştirmek için depo Actions değişkeni `PAGES_DEPLOY=true` yapılır. Değişken kapalıyken iş akışı paketi doğrular, dağıtımı atlar. Hazır kayıtlar yeniden üretilmeden her ziyarette veya her dağıtımda optimizasyon başlatılmaz.

GitHub Free'de Pages açık depolar için kullanılabilir. Gizli depodaki destek hesabın planına bağlıdır. Asıl kaynak deponun görünürlüğünü değiştirmek ayrı bir karardır; yalnız web dosyalarını içeren ayrı açık yayın deposu da kullanılabilir. Bu yöntem kaynak depoyu ve geçmişini gizli tutar. [GitHub Pages erişim koşulları](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages).

## Denetim

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_publication.py
node tests/publication_client.mjs
node tests/permanent_ui.mjs
npm run build:pages
```

Tarayıcı kapıları bütün 2.061 kaydı gerçek ortak planla eşleştirir. Eski plan, yanlış kesit, bozuk geometri, eksik kayıt, yanlış dosya hash'i ve proje alt yolu dışına çıkan bağlantılar reddedilir. Mevcut planın optimum olduğu veya tarihsel tarifenin güncel hizmeti temsil ettiği iddia edilmez. Yöntem penceresi MILP kararlarını, HiGHS aramasını, maliyet → süre sırasını ve kanıt sınırlarını açıklar.
