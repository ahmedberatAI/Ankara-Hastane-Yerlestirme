# Dört başlangıç saatinde ortak yerleşim

Kayıtlı tek profilli yerleşim hafta sonu hedeflerini sağlayamıyordu. Yalnız aynı yapı izlerindeki yatak ve hekim sayısını artırmak da yeterli değildi. Yeni deney **konumları da değiştirerek**, hafta içi 08.00/10.00 ve cumartesi/pazar 10.00 için aynı tesis, yatak ve hekim kaynaklarını seçiyor. Her profil kendi ulaşım matrisiyle ayrı talep atayabiliyor.

Mevcut doğrulanmış örnek **239 konum, 31.550 yatak ve 23.242 hekim** içeriyor. İl hedefi **%95**, her ilçenin tabanı **%80**, EGO süresi **45 dakika** olarak korundu. 20.516 konumlandırılamayan kişi tüm il ve ilçe paydalarında kaldı.

| Başlangıç profili | İl kapsamı | En düşük ilçe kapsamı | Atanan talebin ortalama süresi |
|---|---:|---:|---:|
| Hafta içi 08.00 | %95 | %80,04 | 32,15 dk |
| Hafta içi 10.00 | %95 | %80 | 32,26 dk |
| Cumartesi 10.00 | %95 | %80 | 31,98 dk |
| Pazar 10.00 | %95 | %80,04 | 32,48 dk |

Ondalık hesapla yıllık eşdeğer maliyet **189.178.318.200,076312 TL**. Önceki tek profil deneyinin değişmeyen **189.556.939.209,2935 TL/yıl** tavanının **378.621.009,217188 TL / %0,199740** altında. Arama sırasında bu tavan bir kısıt değildi; bulunan plan sonradan aynı tavanla karşılaştırıldı ve sağladığı doğrulandı. Bu, mevcut katsayılarla bütçeye uygun en az bir ortak tasarım bulunduğu anlamına gelir. Gerçek kamu bütçesi veya maliyet belirsizliğine dayanıklı bir güvence değildir. Pay özellikle küçüktür.

## Hesap

Her konumda en çok bir yatak modülü seçilir. Hekim sayısı ayrı bir tam sayıdır. Her profilde atanan talebin yatış günleri o konumun yatak kapasitesine, başvuru ve yatış temasları hekim kapasitesine sığmalıdır. Dört profil için ayrı hastane veya ayrı hekim kadroları kurulmaz. En zor profilin yüküne yetecek ortak kaynaklar gerekir; dört profilin yükleri toplanmaz.

Yıllık eşdeğer maliyet, yıllıklaştırılmış bina yatırımı ile tesis/yatak/hekim işletme giderleri ve **tek bir yıllık talebin** malzeme gideridir. Malzeme tutarı **33.668.611.722,743994 TL/yıl** olarak yalnız bir kez sayılır. Her profilde aynı 5.614.804 kişi eşdeğerinin yıllık talebi atandığı için bu tutar profiller arasında değişmez. Toplamın dörtle çarpılması da dört profile bölünmesi de yanlıştır.

Her atama, kendi profil matrisinde 45 dakika veya daha kısa olmalıdır. Bina ve hekim çalışma alanı adayın yol dışındaki yapı izine sığar; seçilen yapı izleri birbiriyle çakışmaz. Mevcut binalar yeni adayları engellemez. Modeldeki konumlar sürekli coğrafyanın 4.701 örnek adayıyla sınırlıdır.

## Arama ile kanıt ayrı

İlk ortak aday, dört ayrı profil çözümünden birleştirildiğinde 873 konum içeriyordu. Bu başlangıç planı bir ihtiyaç tahmini değildi. Düşük yüklü konum grupları sırayla kapatıldı; kalan sabit kaynaklarla dört ayrı doğrusal atama problemi çözüldü. Bir kapatma yalnız bütün fiziksel/hedef koşulları sağlanıp yıllık maliyet kesin biçimde azaldığında kabul edildi. Kaynak temizliği dört profilin en yüksek yükünü korudu.

İlk geçiş 433 konuma, ikinci geçiş 239 konuma indi. İkinci geçişte 702 denemenin 126'sı kabul edildi, 576'sı denenen sabit kaynaklarla olanaksız bulundu ve o geçişin kuyruğu tükendi. Bu başarısızlıklar başka kaynaklarla veya başka konumlarla olanaksızlık kanıtı değildir. Ara denemelerin tüm akışları arşivlenmediğinden, yayımlanan sertifika arama yolunun tamamını yeniden oynattığını iddia etmez. **Nihai konumlar ve 3.093 pozitif atama bağımsız olarak yeniden doğrulanır.**

239 minimum sayı değildir. Maliyet optimumu da kanıtlanmadı; bu kayıtta yeni alt sınır veya optimalite açıklığı yayımlanmıyor. Ortalama yolculuk süresi ayrıca optimize edilmedi. Daha az konum, daha ucuz kaynak veya farklı ulaşım dengesi bulunabilir.

## Aynı kişiler hakkında söylenebilecekler

Ortak olan tesisler ve kaynaklardır. Mahalle içindeki kişiler ayrı ayrı gözlenmez; her profilde %95 karşılanması aynı kişilerin dört profilde de %95 oranında karşılandığını göstermez.

Kayıtlı atamalar aynı mahalle nüfusunun alt kümeleri olarak yorumlanırsa, dört profilin ortak bölümünün koşullu aralığı **%91,624106–%92,227534** olur. Her mahallede alt uç `max(0, dört profilin toplamı − 3 × mahalle nüfusu)`, üst uç en düşük profil atamasıdır. Üst uç uygun hizalanmayla mümkün olabilir; garanti değildir. Bunlar kimlik verisi veya ek bir optimizasyon hedefi değildir.

## Bağımsız doğrulama ve kullanım

`data/processed/joint-plan.json` tam seçilmiş kaynakları, dört profilin pozitif atamalarını, değişmeyen senaryoyu ve sekiz veri kaynağının SHA-256 kimliğini taşır. `joint-plan-summary.json` arayüzün kullandığı bağımsız hesap özetidir. Varsayılan denetim salt okunurdur:

```powershell
.venv\Scripts\python.exe scripts/audit_joint_plan.py
```

Denetçi optimizasyon çalıştırmadan doğrudan nüfus paydalarını, kaynak/alan/çakışma koşullarını, her atamanın süre matrisini, bütün ilçe yüzdelerini, tek yıllık gideri ve eski tavanı yeniden hesaplar. Paket, sağlık verisi, sertifika veya denetçi kodu değişmişse eski özet kabul edilmez. `--write` yalnız bu denetimden türetilen özeti günceller; planı veya ulaşım matrislerini değiştirmez.

Yeni bir iyileştirme deneyi için mevcut tam plan başlangıç olarak kullanılabilir:

```powershell
# Aynı seçilmiş konum havuzunda kapatma ile yatak/hekim sayısını yeniden optimize et.
.venv\Scripts\python.exe scripts/run_joint_plan.py --strategy cost --pool selected --seconds 300 --out work/joint-cost-next

# Dört ayrı sabit-kapasite atama problemiyle grup kapatmayı dene.
.venv\Scripts\python.exe scripts/run_joint_plan.py --strategy close --pool selected --seconds 300 --out work/joint-close-next
```

Çıktı klasörü yeni ve deponun `work/` dizini içinde olmalıdır. Var olan dosyalar veya üretim planı üzerine yazılmaz. `--seed` ile önceki koşunun tam `joint-plan.json` sertifikası seçilebilir. Girdi ve kod kimlikleri girişte/çıkışta kontrol edilir; sonuç üretim optimizasyonuna güvenmeyen bağımsız denetimden tekrar geçer. `run-result.json`, vektörler, denetim ve tam yeni sertifika ayrı saklanır. Bu komutlar ana arayüzün kaydını otomatik değiştirmez.

`--pool selected`, yalnız başlangıç planının konumlarını seçilebilir tutar; bazılarını kapatabilir ve kaynakları büyütüp küçültebilir. Bu koşunun alt sınırı yalnız o konum havuzuna aittir. `--pool all` bütün kayıtlı adayları ve profil başına eşik içindeki bütün bağlantıları kullanır. Her iki durumda da fiziksel alan ve ilçe hedefleri korunur. Maliyet araması eski tavanı sessizce büyütmez ve yeni bir bütçe üretmez. Süre sınırı en çok 300 saniyelik toplam arama bütçesidir; yerel çözücünün kontrol aralıkları nedeniyle aşım olabilir, gerçek süre raporlanır. Son bağımsız denetim ve dosya yazımı ayrıca zaman alır. Çözücünün belirsiz veya kesilmiş durumu olanaksızlık sayılmaz; doğrulanmış başlangıç planı güvenli geri dönüş sağlar.

Üretim uygulamasında matematiksel model açık bir kurucu, yerel maliyet çözücüsü ve grup kapatma yordamı olarak ayrılmıştır. Model kurmak için çözücü fonksiyonu geçici olarak değiştirilmez. Eski araştırma çalıştırıcıları bir ürün bağımlılığı değildir.

Araştırma kaydının SHA-256 kimliği `c301e5cb0b0dfdfd0ea01bcb29416a34e6077d88fc70396812904222637f664f`. Araştırma arşivleri geliştirme klasöründedir; normal kurulum onları içermez. Standalone denetim bu arşivleri okuduğunu iddia etmez; yayımlanan planın bütün atamalarını kendi başına doğrular. Hazırlanmış planın tam byte kimliği ve güncel kaynaklar özet raporunda ayrıca tutulur.

Arayüzde **“Konumlar da birlikte seçilirse?”** bölümü bu kayıtlı örneği gösterir. Ayrı haritada konumlar dört profilde aynıdır; gri nüfus halkaları bir kapsama haritası değildir. Ana tek profil deneyleri ve canlı ayarlar bu kaydı değiştirmez. [Hesap ekranı](screenshots/ortak-plan-hesabi.png) · [Harita ekranı](screenshots/ortak-plan-haritasi.png).

## 91 testi ve gerçek Ankara

Ulaşım paketi ve eski 91 testinin katsayıları değişmedi. Önceden doğrulanmış dört coğrafi alt sınır **165 / 167 / 170 / 168** geçerli kalır; aynı veriyle ağır deney tekrar çalıştırılmadı. Yeni 239 planı bu sınırları çürütmez ve 91 tesisin yeterliliğini kanıtlamaz. Ulaşım kısıtlarını tamamen kaldıran [46 tesisli kontrol](transport-relaxation.md) ise yalnız toplam kapasite ve giderin yüksek EGO sonucunu tek başına zorlamadığını gösterir.

Özel seferler, ara durak saatleri, Başkentray ve diğer hizmetlerde eksik kanıt var. Hekim temas oranı klinik standart veya yıllık FTE ölçümü değil; hasta talebinde il dışı başvuru ayrımı yok. İşletme gideri kısmi bir aktarım hesabı, Aralık 2024 fiyat düzeyindedir; arsa, tıbbi cihaz ve dış altyapı yatırımları hariç. Bu eksikler nedeniyle hakemlerin matematik ve veri kimliği kabulü **gerçek kent için hastane ihtiyacı, klinik uygunluk veya genel model başarısı kabulü değildir**.
