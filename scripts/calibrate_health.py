"""Reproduce every calibrated input. Observations and transferred proxies stay separate."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/processed/health-planning.json'


def run():
    p = json.loads(OUT.read_text(encoding='utf-8'))
    p['version'] = 'independent-capacity-2026-10-v2'
    p['rates']['contactsPerResident'] = p['rates']['visitsPerResident'] + p['rates']['admissionsPerResident']
    # Report p.44 gives 444 on-payroll + 2,828 off-payroll physicians.
    mlp = dict(hospitals=35, beds=6300, physicians=3272, annualContacts=7000000,
        doctorExpensesTRY=9994192000, otherPersonnelTRY=6417735000,
        materialsTRY=5113295000, outsourcedServicesTRY=2245638000,
        otherServiceCostsTRY=2533955000, administrationTRY=3366893000,
        administrationDepreciationTRY=184925000, advertisingTRY=1007767000)
    p['calibration'] = {
        'hospitalExamples': [
            {'name': 'Cebeci', 'beds': 1097, 'physicians': 921, 'outpatientVisits': 694180,
             'admissions': 40271, 'sourceId': 'au2024'},
            {'name': 'İbni Sina', 'beds': 665, 'physicians': 836, 'outpatientVisits': 703972,
             'admissions': 28865, 'sourceId': 'au2024'},
            {'name': 'Etlik Şehir Hastanesi', 'beds': 4050, 'grossAreaM2': 1145129,
             'sourceId': 'etlik'}],
        'operatingBenchmark': mlp,
        'contactsPerDoctorObserved': mlp['annualContacts'] / mlp['physicians'],
        'universityContactsPerDoctorObserved': (694180 + 40271 + 703972 + 28865) / (921 + 836),
        'scopeNote': 'MLP portföy göstergeleri ile konsolide giderlerin kapsamı birebir değildir; yönetilen tesisler, yan işler, yabancı faaliyetler ve yıl içi açılışlar vardır. Bölme işlemleri kamu hastanesi birim maliyeti ölçümü değil, açıkça aktarılan yaklaşık kalibrasyon senaryosudur. Yıl sonu hekim sayısı FTE veya yıllık ortalama değildir.',
    }
    p['defaults'] = dict(demandMultiplier=1, bedOccupancy=80, contactsPerDoctor=2140,
                         costTolerance=10, hospitalLimit=None, operatingCostMultiplier=1)
    # TMS29 operating figures use December 2024 purchasing power. Approximate
    # January-to-December rebasing of the January-effective building tariff,
    # using published CPI changes: Dec/Dec 44.38%, Jan/Dec 6.70%.
    factor = 1.4438 / 1.067
    p['economics'] = {
        'priceBase': 'Aralık 2024 TL (yaklaşık sabit fiyat)', 'priceYear': 2024,
        'buildingUnitCostNominalTRY': 22250, 'buildingClass': 'V-B',
        'constructionRebaseFactor': factor, 'buildingUnitCostTRY': 22250 * factor,
        'horizonYears': 25, 'realDiscountRate': .03,
        'annualDoctorCostTRY': mlp['doctorExpensesTRY'] / mlp['physicians'],
        'annualBedSupportCostTRY': (mlp['otherPersonnelTRY'] + mlp['outsourcedServicesTRY'] + mlp['otherServiceCostsTRY']) / mlp['beds'],
        'costPerContactTRY': mlp['materialsTRY'] / mlp['annualContacts'],
        'annualFixedSiteCostTRY': (mlp['administrationTRY'] - mlp['administrationDepreciationTRY'] - mlp['advertisingTRY']) / mlp['hospitals'],
        'excluded': 'Arsa, tıbbi cihaz yatırımı/yenilemesi, çevre ve dış altyapı, KDV ve kurumlar vergisi, finansman ve gelirler; toplam kamu bütçesi tahmini değildir. Amortisman, reklam ve finansman maliyeti işletme proxy tutarına eklenmez.',
    }
    p['design'] = {'baseAreaM2': 4000, 'areaPerBedM2': 160, 'areaPerDoctorM2': 80,
                   'maxFloors': 9, 'minimumDoctorsPerSite': 12,
                   'note': 'Alan bileşenleri, 9 kat ve 12 hekim alt sınırı tasarım varsayımlarıdır; klinik kadro standardı veya Etlik binasının kopyası değildir. Her adayda yatak ve ayrıca seçilen hekim alanının toplamı yol-dışı izin 9 kat alanına sığmalıdır.'}
    p['templates'] = [{'id': f'b{b}', 'label': f'{b:,} yatak'.replace(',', '.'), 'beds': b,
        'grossAreaM2': 4000 + 160*b, 'unitCostTRY': p['economics']['buildingUnitCostTRY'],
        'constructionCostTRY': (4000 + 160*b)*p['economics']['buildingUnitCostTRY']}
        for b in (50,150,300,600,1000,2000,4050)]
    p['sources'] = [s for s in p['sources'] if s['id'] not in ('cost2026','au2024','mlp2024','cost2024','etlik','cpi')]
    p['sources'].extend([
        {'id':'au2024', 'title':'Ankara Üniversitesi 2024 İdare Faaliyet Raporu · tablo 110, basılı s.160',
         'url':'https://sgdb.ankara.edu.tr/wp-content/uploads/sites/172/2025/07/A.U._2024_Yili_Idare_Faaliyet_Raporu_s.pdf',
         'localFile':'ankara-university-2024.pdf', 'pdfPages':[162,291],
         'note':'Cebeci ve İbni Sina yatak, hekim, ayakta/yatarak hasta kayıtları. Döner sermaye giderleri eksik kapsam nedeniyle toplam işletme maliyeti olarak kullanılmadı.'},
        {'id':'mlp2024','title':'MLP Care 2024 Faaliyet Raporu · basılı s.9, 44, 95, 118–119',
         'url':'https://investor.mlpcare.com/site/assets/files/3349/mlp_care_2024_faaliyet_raporu.pdf',
         'localFile':'mlp-2024.pdf','pdfPages':[10,45,96,119,120],
         'note':p['calibration']['scopeNote']},
        {'id':'cost2024','title':'2024 Yapı Yaklaşık Birim Maliyetleri · 20 Şubat 2024, RG 32466',
         'url':'https://webdosya.csb.gov.tr/db/sivas/menu/yapi-yaklasik-birim-maliyetleri-2024_20240223090428.pdf',
         'localFile':'costs2024.pdf','pdfPages':[5],
         'note':'2024 tebliğinde hastaneler V-B, 22.250 TL/m². 2026 tebliğinin yatak eşikleri bu yıla taşınmadı. Ocak fiyat düzeyi varsayılıp genel TÜFE ile yaklaşık Aralık 2024 TL’ye çevrildi; inşaat endeksi veya ihale fiyatı değildir.'},
        {'id':'etlik','title':'Etlik Şehir Hastanesi · resmî tanıtım',
         'url':'https://etliksehir.saglik.gov.tr/TR-852985/tanitim.html',
         'note':'4.050 yatak ve 1.145.129 m² kapalı alan; büyük tesis ölçeğinin gerçek örneği.'},
        {'id':'cpi','title':'TCMB · TÜİK tüketici fiyatları aylık ve yıllık değişimleri',
         'url':'https://www.tcmb.gov.tr/wps/wcm/connect/TR/TCMB+TR/Main+Menu/Istatistikler/Enflasyon+Verileri/Tuketici+Fiyatlari',
         'note':'2024 Aralık yıllık %44,38 ve Ocak aylık %6,70; yaklaşık Ocak–Aralık katsayısı 1,4438 / 1,067.'},
    ])
    for s in p['sources']:
        if 'localFile' in s:
            path = ROOT / 'data/raw/health' / s['localFile']
            if path.exists(): s['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        if s['id'] == 'wisn':
            s['note'] = 'Branş/aktivite süresiyle iş gücü ihtiyacı yöntemi. Gözlenen kişi başına yıllık temas oranı WISN kadro standardı değildir.'
    p['assumptions'] = [
        '2024 il hizmet kullanımı / 2024 nüfusu, 2025 mahalle nüfusuna uygulanır. Mahallede ölçülmüş klinik ihtiyaç veya karşılanmamış talep değildir.',
        'İkinci/üçüncü basamak başvuruları özel tıp merkezlerini de içerir. Ankara dışından gelenler, yaş, branş, gündüz nüfusu ve sevk akışları ayrıştırılmamıştır.',
        'Hekim yükü için temas = başvuru + yatış kullanılır. MLP’nin ayakta/yatan toplam 7,0 milyon ziyareti / 3.272 hekimi yaklaşık 2.140 temas/hekim/yıl verir. Bir yatış ile bir muayenenin klinik süreleri eşit değildir; bu yalnızca gözlenen karışımın toplulaştırılmış proxy oranıdır.',
        'Ankara Üniversitesi iki tıp hastanesinde gözlenen oran yaklaşık 835’tir. Eğitim/araştırma ve karmaşık hasta yükü nedeniyle başka kurumlara doğrudan taşınamaz; duyarlılık senaryosu olarak sunulur.',
        p['calibration']['scopeNote'],
        'İşletme giderlerinin sabit/hekime/yatağa/temasa dağıtımı ölçülmüş maliyet fonksiyonu değil, rapor kalemlerinden kurulan planlama varsayımıdır. İşletme çarpanı ile duyarlılık incelenmelidir.',
        'Maliyet göstergesi = bina yatırımı × sermaye geri kazanım katsayısı + yıllık işletme. 25 yıl ve %3 reel iskonto, değişmeyen reel gider ve sıfır hurda değeri varsayılır. Cari 2026 ihale bedeli değildir.',
        p['economics']['excluded'], p['design']['note'],
        'Yatak doluluğu %80 bir planlama tavanıdır; Ankara 2024 gözlemi %59,5’tir. Branş, yoğun bakım, nöbet, hemşire, kuyruk ve pik talep ayrıca optimize edilmez.',
        'Mevcut binalar engel sayılmaz. 45/80/120/210 m yarıçaplı yapı izleri yol ve yüzey ray koridorlarından ayrılır. Girişe en fazla 650 m varsayılan bağlantı eklenir; bağlantı gerçek servis yolu projesi değildir.',
        'Talep tesisler arasında bölünebilir. Hızlı model her mahallede her yapı-izi sınıfından en yakın 12 adayı kullanır. Geçerli çözüm tüm asıl kısıtlarla denetlenir; başarısız hızlı arama tüm Ankara için imkânsızlık ispatı değildir.',
        '91 sınırı mevcut hastaneleri koruma deneyi değil, sıfırdan en fazla 91 tesis yerleştirme deneyidir. Resmî 2024 envanteri 85’tir; 91 kullanıcı karşılaştırma eşiğidir.',
    ]
    OUT.write_text(json.dumps(p, ensure_ascii=False, indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Calibration written; contacts/physician:', p['calibration']['contactsPerDoctorObserved'])

if __name__ == '__main__': run()
