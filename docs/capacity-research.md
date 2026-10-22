# Kapasite ve maliyet araştırması

Araştırma tarihi: 22 Ekim 2026. Sağlık kayıtlarının referansı **2024**, yerleşim nüfusu **2025**, yapım birim fiyatı **2026**. Bu yıllar birbiriyle karıştırılmaz; oran aktarımı açık bir senaryodur.

## Doğrulanan resmî değerler

[Sağlık Bakanlığı yayın sayfası](https://www.saglik.gov.tr/TR-114952/saglik-istatistikleri-yilligi-2024.html) üzerinden [Türkçe yıllık PDF](https://dosyamerkez.saglik.gov.tr/Eklenti/52859/0/siy2024tr31122025pdf.pdf) indirildi. İlgili tablolar metin çıkarımı ve sayfa görüntüleriyle doğrulandı.

| Alan                            | Ankara değeri | Tablo | Basılı sayfa / PDF sayfası | Kullanım                                        |
| ------------------------------- | ------------: | ----- | -------------------------- | ----------------------------------------------- |
| Hastane                         |            85 | 7.20  | 162 / 191                  | 2024 bağlamı; güncel tesis sayısı iddiası değil |
| Yatak                           |        24.909 | 7.20  | 162 / 191                  | Mevcut kapasite bağlamı                         |
| Uzman hekim                     |        12.064 | 10.12 | 261 / 290                  | Tüm sektörler                                   |
| Pratisyen hekim                 |         3.448 | 10.12 | 261 / 290                  | Tüm sektörler                                   |
| Asistan hekim                   |        11.286 | 10.12 | 261 / 290                  | Tüm sektörler                                   |
| Toplam hekim                    |        26.798 | 10.12 | 261 / 290                  | Ayrılabilir hastane kadrosu değildir            |
| İkinci/üçüncü basamak başvurusu |    47.073.855 | 8.26  | 204 / 233                  | Yıllık başvuru yükü vekili                      |
| Yatan hasta/yatış               |     1.063.851 | 8.26  | 206 / 235                  | Yıllık yatış tahmini                            |
| Yatılan gün                     |     5.409.136 | 8.26  | 206 / 235                  | Yatak-gün talebi                                |
| Yatak doluluk oranı             |         %59,5 | 8.26  | 206 / 235                  | Gözlem; %80 senaryo tavanı ile aynı değil       |

2024 Ankara nüfusu **5.864.049**: [TÜİK İstatistiklerle Türkiye 2024](https://veriportali.tuik.gov.tr/api/tr/data/downloads?p=Gw%2FA2HZTNUHe8RkOENcGUdiCNBC3vYByhY73anmn16Tu5T597AxIpzMpdYwG2Nr3fwchzi64xujp1DOmjzMStY5glPPJWcl76E8bLNANwhU%3D&t=y). 2024 hizmet kullanımı / 2024 nüfusu oranları 2025 mahalle nüfusuna uygulanır. Sonuç yılda kişi başına 8,027534 başvuru, 0,181419 yatış ve 0,922423 yatış günüdür.

Başvuru tekil kişi değildir. 47,1 milyon sayısı birinci basamağı ve diş hekimliğini içermez; ikinci/üçüncü basamak toplamı özel tıp merkezlerini içerir (yıllık tablo 8.1, basılı 166). Bu nedenle yalnız hastane polikliniği sayısı diye etiketlenmez. Ankara'ya il dışından gelenler bu hizmet toplamlarında bulunabilir. İkamet kökeni, mahalle/yaş/branş bazında hasta akışı doğrulanamadı; bu kullanımın il sakinlerine orantılı dağıtımı bir model varsayımıdır. Kullanım, karşılanmamış ihtiyaç ölçümü değildir.

## Hekim kapasitesi: bilinen ve bilinmeyen

İl toplamı gerçek veridir; bir hastane hekiminin kaç klinik saat çalıştığı, her hizmetin kaç dakika sürdüğü ve branş dağılımı bu toplamdan çıkmaz. Bu nedenle 26.798 sayısı hastanelere ayrılabilir kadro veya kişi başına verimlilik hesabının paydası yapılmadı.

[WHO WISN](https://www.who.int/tools/wisn) iş yükü ile kullanılabilir çalışma süresine dayanan personel planlaması yaklaşımını sağlar. Uygulama tam WISN uygulaması değildir. Başlangıç **4.000 başvuru/hekim/yıl = 20 × 200 klinik gün** senaryosudur; resmî/klinik standart diye sunulmaz. Kullanıcı 2.000–6.000 arasında değiştirebilir. 30/90/180 hekimli tesis şablonları tasarım tercihleridir. Hekim başına yatış, ameliyat, nöbet, öğretim ve idari süre ayrı izlenmediği için gerçek kadro planlaması için zaman etüdü ve branş matrisi gerekir.

## Yapım maliyeti

[3 Şubat 2026, 33157 sayılı Resmî Gazete tebliği](https://www.resmigazete.gov.tr/eskiler/2026/02/20260203-4.htm) resmî sunucudan alınamadı. [TÜRMOB üzerindeki aynı tebliğin PDF nüshası](https://www.turmob.org.tr/arsiv/mbs/resmigazete/33157-33157-1.pdf) indirildi; hastane satırları görsel olarak doğrulandı. IV-C, 200 yatak altı **40.500 TL/m²**; V-B, 200 dahil 400 yatak altı **43.850 TL/m²**. V-A bedeli hastanelere yanlış uygulanmadı.

Şablon kapalı alanları **4.000 + 160 × yatak** m² olarak varsayıldı. Bunlar resmî tip proje standardı değildir. Ölçek bağlamı olarak [Kestel Devlet Hastanesi'nin resmî tanıtımı](https://kesteldh.saglik.gov.tr/TR-589270/hastanemiz.html) incelendi: 150 yatakla açılan bina 26.846 m² kapalı alana ve 5.490 m² tabana sahiptir; 2026 kapasitesi 165 yataktır. Bu tek bina Ankara için genel standart yerine konmadı.

| Şablon    | Hekim (varsayım) | Kapalı alan (varsayım) | Bina yapım göstergesi |
| --------- | ---------------: | ---------------------: | --------------------: |
| 50 yatak  |               30 |              12.000 m² |        486.000.000 TL |
| 150 yatak |               90 |              28.000 m² |      1.134.000.000 TL |
| 300 yatak |              180 |              52.000 m² |      2.280.200.000 TL |

Birim fiyatlar yaklaşık yapı bedeli göstergesidir. KDV, arsa, çevre düzenlemesi, dış altyapı, tıbbi cihaz, personel ve işletme giderleri hesapta yoktur. Gerçek ihale maliyeti veya yaşam döngüsü maliyeti iddiası yoktur. Kullanıcı talebi gereği mevcut bina/arsa mülkiyeti engel yapılmaz; yol ve yüzey ray koridorları dışlanmaya devam eder.

## Karar metriği

Kapasiteli yer seçimi + iki amaçlı epsilon-kısıt yaklaşımı seçildi: önce hedef talep payını karşılayan düşük bina bedeli, sonra o bedelin belirlenmiş ek bütçesiyle aynı toplam talebin yolculuğunu azaltma. İlçe tabanları her aşamada korunur. Maliyet ve dakika keyfî ağırlıklarla toplanmaz. **%10 ek bütçe, %80 doluluk, %95 talep ve 30/45 dakika tercihleri evrensel optimum değildir.** Değiştirilebilir oldukları arayüzde açıklanır.

Kaynak SHA-256 değerleri, tablo ve sayfa numaraları [health-planning.json](../data/processed/health-planning.json) içinde; yeniden kaynak doğrulaması `scripts/verify_health_sources.py` ile yapılır. Tam matematik [methodology.md](methodology.md) içindedir.
