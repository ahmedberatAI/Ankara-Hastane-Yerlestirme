# Hekim sayısından klinik çalışma zamanına

23 Ekim 2026 kaynak kontrolü. **Bu araştırma 2.140 temas/hekim/yıl varsayımını doğrulamadı veya değiştirmedi.** Ankara kamu/üniversite hastaneleri için hastane-yıl düzeyinde gerçekleşmiş klinik çalışma saati ya da tam zaman eşdeğeri (FTE) serisi bu sınırlı taramada bulunamadı. Bu, kurumlarda böyle bir kayıt bulunmadığı anlamına gelmez.

## Yeni resmî yöntem kaynağı

[Sağlık Bakanlığı GÖREN kılavuzu](https://sina.saglik.gov.tr/media/sina_files/GOREN_KILAVUZ.pdf#page=37), basılı s.36 / PDF 37. sayfa, SYPG-BH-5 göstergesi, 21 Mayıs 2026 revizyonudur. Aylık uzman poliklinik muayene sayısını, EKOBS/ÇKYS kimlik ve branş bilgileriyle aktif çalışma günü katsayısını dikkate alan hekim paydasına ve 22 iş gününe böler. Acil ve tanımlanan kontrol muayeneleri bu muayene sayımına dahil edilmez.

Bu bir gösterge tanımıdır; Ankara hastanelerinin gerçekleşmiş payda değerleri değildir. Gösterge sayfası katsayının bütün normalizasyon ayrıntılarını açıklamaz. Ham adam-gün toplamı, 22 günlük klinik saat veya yıllık FTE olarak yeniden yorumlanamaz. 2026 aylık uzman muayenesi, modelin 2024 yıllık başvuru + yatış toplamıyla aynı kapsamda değildir; doğrudan oran veya yıl dönüşümü yapılmadı.

## Bilkent çizelgelerinde çift sayım kontrolü

[Genel Hastane](https://ankarasehir.saglik.gov.tr/TR-416896/genel-hastane-hekim-calisma-listeleri.html) ve [Göğüs ve Kalp-Damar Hastanesi](https://ankarasehir.saglik.gov.tr/TR-672853/gogus-ve-kalp-damar-hastanesi-hekim-calisma-listeleri.html) başlıklı iki resmî bağlantının XLSX dosyaları incelendi. İkisi de 28 Eylül–28 Ekim 2026 dönemindeki 23 tarih sütununu içeriyor; saat alanı saptanmadı. Dönem, erişimden sonraki günleri de kapsadığından gerçekleşmiş yıllık çalışma kaydı değildir.

Dosya özetleri farklı olsa da **1.993 × 24 hücrenin adres ve değerleri aynı**; ikinci bağımsız inceleme ZIP/XML düzeyinde de bunu doğruladı. Başlıklar farklı diye iki kapasite havuzu olarak toplanmadı. Bir aylık plan 12 ile çarpılmadı; bir hücre tam klinik gün veya benzersiz hekim sayılmadı. İsimler araştırma raporuna veya model girdisine taşınmadı.

## Kalibrasyon için gereken veri

Bu projeye yönelik veri gereksinimi, aynı yılın kurum–branş–ay düzeyinde toplulaştırılmış kayıtlarıdır:

- Aktif gün katsayısının tanımı, izin/görevlendirme ve yıl içi kadro değişimleriyle birlikte hesaplanan payda.
- Planlanan ve gerçekleşen klinik oturum saatleri; servis, acil, ameliyathane ve klinik dışı görev zamanlarının ayrımı.
- Aynı kapsamdaki ilk/kontrol muayenesi, yatış ve işlem sayıları; görevler arasında çift sayım kontrolü.

Kullanılabilir saatten FTE türetilecekse tam zaman referansı ayrıca tanımlanıp kurumla doğrulanmalıdır. Gözlenen hizmet/çalışma süresi oranı da tek başına güvenli azami klinik kapasite değildir. [Mevcut katsayıların kaynağı ve sınırları](capacity-research.md) geçerliliğini korur.

## Kaynak kimlikleri

Üç yanıt 23 Ekim 2026 yaklaşık 03.28 UTC / 06.28 TSİ'de alındı. Bu gözlem zamanı, kaynağın yayın tarihi değildir. PDF'nin ilgili sayfası metin ve görüntüden kontrol edildi. Ham dosyalar araştırma arşivinde tutuldu; üretim ulaşım/sağlık paketine eklenmedi.

| Kaynak | Bayt | SHA-256 |
|---|---:|---|
| GÖREN PDF | 1.678.446 | `19680d44a144d338da649a8cc2d3794e3f1036fcc79f6147cd3adb764e4c7461` |
| Bilkent Genel Hastane XLSX | 252.794 | `565c9c137873e549c65e73dd0a0d1b1c56ba8280c121560e1d9657885136dfa4` |
| Bilkent Göğüs/Kalp-Damar XLSX | 252.809 | `4076ecee4574fddf8c76a673f97fe9d46b0a7e34800680c31dac0648ef9d7423` |

Yatak/hekim katsayıları, ulaşım matrisleri ve hedefler değişmedi. Dolayısıyla bu araştırma, kayıtlı 91 hastane deneylerinin yeni girdilerle tekrarlandığı veya daha gerçekçi bir kapasite sonucu elde edildiği şeklinde sunulmaz.
