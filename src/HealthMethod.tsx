import { Info, ArrowUpRight } from "lucide-react";
import type { Dataset } from "./types";
const fmt = (n: number, digits = 0) =>
  n.toLocaleString("tr-TR", { maximumFractionDigits: digits });

export default function HealthMethod({ data }: { data: Dataset }) {
  const p = data.healthPlanning,
    e = p.economics;
  return (
    <div className="method-content">
      <p className="lead">
        Yer, yatak ve hekim kadrosu birlikte seçilir. Her hastane aynı
        büyüklükte olmak zorunda değildir. Modelin amacı erişim hedeflerini
        sağlayan düşük yıllık maliyetli bir plan bulmaktır.
      </p>
      <div className="method-steps">
        <article>
          <span>01</span>
          <h3>Talebi hesapla</h3>
          <p>
            Mahalle nüfusu, Ankara’nın gözlenen hizmet kullanımına dönüşür.
            Temas hekim yükünü, yatış günü yatak yükünü belirler.
          </p>
        </article>
        <article>
          <span>02</span>
          <h3>Kaynakları seç</h3>
          <p>
            50–4.050 yataklı tesis seçenekleri ve bağımsız hekim sayısı.
            Yıllıklaştırılmış bina yatırımı ile işletme gideri birlikte
            azaltılır.
          </p>
        </article>
        <article>
          <span>03</span>
          <h3>Yolu kısalt</h3>
          <p>
            Aynı toplam talebi koruyarak ek yıllık maliyet sınırı içinde daha
            kısa yol aranır. Hastane sayısı sınırı iki aşamada da geçerlidir.
          </p>
        </article>
      </div>
      <h3>Gerçek hastaneler ne söylüyor?</h3>
      <div className="table-scroll">
        <table className="capacity-table">
          <thead>
            <tr>
              <th>Kaynak örneği</th>
              <th>Yatak</th>
              <th>Hekim</th>
              <th>Yıllık başvuru + yatış</th>
            </tr>
          </thead>
          <tbody>
            {p.calibration.hospitalExamples.map((h) => (
              <tr key={h.name}>
                <td>{h.name}</td>
                <td>{fmt(h.beds)}</td>
                <td>{h.physicians ? fmt(h.physicians) : "Bu kaynakta yok"}</td>
                <td>
                  {h.outpatientVisits !== undefined
                    ? fmt(h.outpatientVisits + (h.admissions ?? 0))
                    : "Ölçek örneği"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        Cebeci ve İbni Sina: Ankara Üniversitesi 2024 raporu, tablo 110. Etlik:
        hastanenin resmî tanıtımı. 4.050 yatak seçeneği gerçek bir ölçeğe
        dayanır; bu hastanenin binasını veya klinik organizasyonunu kopyalamaz.
      </p>
      <div className="note-block">
        <Info size={20} />
        <div>
          <b>Hekim/yatak oranı artık sabit değil.</b>
          <p>
            Aynı 300 yataklı seçenek farklı hekim kadrolarıyla açılabilir. Hekim
            sayısı tam sayıdır; yük ve alan sınırlarıyla belirlenir. Hekim alanı
            da yapı maliyetine ve yol dışındaki yapı izinin kapasitesine
            eklenir.
          </p>
        </div>
      </div>
      <h3>Resmî talep verisi · Ankara, 2024</h3>
      <div className="evidence-grid">
        {[
          [p.observed.beds, "hastane yatağı"],
          [p.observed.physicians, "hekim · tüm sektörler"],
          [p.observed.secondaryTertiaryVisits, "2. / 3. basamak başvurusu"],
          [p.observed.admissions, "hastane yatışı"],
          [p.observed.bedDays, "yatılan gün"],
          [p.observed.hospitalCount, "hastane · 2024 envanteri"],
        ].map(([v, l]) => (
          <div key={String(l)}>
            <b>{fmt(Number(v))}</b>
            <span>{l}</span>
          </div>
        ))}
      </div>
      <p>
        Sağlık Bakanlığı 2024 Yıllığı, tablolar 7.20, 8.26 ve 10.12. 26.798
        hekim, hastanelere ayrılabilir bir kadro bütçesi değildir. Kullanıcının
        91 karşılaştırma sınırı ile tarihli resmî envanter farklı şeylerdir.
      </p>
      <div className="formula">
        <span>İKİ AYRI KAYNAK KISITI</span>
        <strong>Atanan temas ≤ seçilen hekim × yıllık temas/hekim</strong>
        <strong>
          Atanan yatış günü ≤ seçilen yatak × 365 × doluluk tavanı
        </strong>
        <p>
          Kişi başı başvuru {fmt(p.rates.visitsPerResident, 3)}, yatış{" "}
          {fmt(p.rates.admissionsPerResident, 3)}, yatış günü{" "}
          {fmt(p.rates.bedDaysPerResident, 3)}. Temas = başvuru + yatış. Bu
          oranlar 2025 nüfusuyla ve seçilen talep çarpanıyla çarpılır.
        </p>
      </div>
      <h3>2.140 temas/hekim/yıl nereden geliyor?</h3>
      <p>
        MLP 2024 raporu 7,0 milyon ayakta/yatan ziyareti ve 444 bordrolu + 2.828
        bordrosuz hekimi bildirir. Bölümü{" "}
        {fmt(p.calibration.contactsPerDoctorObserved, 1)}; varsayılan senaryoda
        2.140’a yuvarlanır. Bu gözlenen bir grup ortalamasıdır; azami güvenli
        klinik kapasite veya WHO standardı değildir.
      </p>
      <p>
        Ankara Üniversitesi’nin iki tıp hastanesindeki aynı tür oran{" "}
        {fmt(p.calibration.universityContactsPerDoctorObserved, 1)}’tir. Eğitim,
        araştırma ve hasta karmaşıklığı farklıdır. Ayarlardaki 835 seçeneği bu
        daha düşük hizmet/hekim oranının duyarlılığını gösterir. Bir muayene ile
        bir yatışın süreleri eşit varsayılmış bir zaman etüdü yapılmaz; yalnızca
        gözlenen hizmet karışımı aktarılır.
      </p>
      <h3>İşletme gideri nasıl kuruldu?</h3>
      <p>
        MLP’nin denetlenmiş 2024 konsolide giderleri, yaklaşık bir maliyet
        fonksiyonuna ayrılır. Amortisman ve finansman giderleri tekrar eklenmez;
        reklam gideri dışarıda bırakılır. Ankara Üniversitesi döner sermaye
        giderleri bütün ücretleri kapsamayabildiği için toplam maliyet olarak
        alınmaz.
      </p>
      <div className="table-scroll">
        <table className="capacity-table">
          <thead>
            <tr>
              <th>Bileşen</th>
              <th>Modeldeki gösterge</th>
              <th>Türetim</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Hekim</td>
              <td>{fmt(e.annualDoctorCostTRY)} ₺/hekim/yıl</td>
              <td>Hekim gideri / 3.272</td>
            </tr>
            <tr>
              <td>Yatak desteği</td>
              <td>{fmt(e.annualBedSupportCostTRY)} ₺/yatak/yıl</td>
              <td>
                Diğer personel + hizmet alımı + diğer hizmet gideri / 6.300
              </td>
            </tr>
            <tr>
              <td>Malzeme</td>
              <td>{fmt(e.costPerContactTRY)} ₺/temas</td>
              <td>Malzeme tüketimi / 7 milyon</td>
            </tr>
            <tr>
              <td>Tesis başına sabit</td>
              <td>{fmt(e.annualFixedSiteCostTRY / 1e6, 2)} mn ₺/yıl</td>
              <td>Yönetim − amortisman − reklam / 35 tesis</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div className="note-block">
        <Info size={20} />
        <div>
          <b>Aktarılan maliyet proxy tutarları</b>
          <p>
            {p.calibration.scopeNote} Bu giderleri sabit/yatak/hekim/temas
            olarak ayırmak da bir varsayımdır. Ayarlardaki işletme çarpanı, ±%50
            dahil farklı gider seviyelerini test eder.
          </p>
        </div>
      </div>
      <div className="formula">
        <span>TEK BİRİMDE MALİYET</span>
        <strong>
          Yıllık maliyet = bina yatırımı × sermaye katsayısı + yıllık işletme
        </strong>
        <p>
          {e.horizonYears} yıl, %{fmt(e.realDiscountRate * 100)} reel iskonto,
          sabit reel giderler ve sıfır hurda değeri. Sermaye katsayısı r / [1 −
          (1+r)⁻ᴺ]. Bütün tutarlar {e.priceBase}.
        </p>
      </div>
      <p>
        2024 resmî tebliğinde hastaneler V-B sınıfı, 22.250 TL/m²’dir. Ocak
        fiyatı varsayılıp genel TÜFE değişimleriyle yaklaşık Aralık 2024
        düzeyine çevrilir. 2026 fiyatı ile 2024 giderleri doğrudan toplanmaz. Bu
        bir ihale keşfi veya tam kamu bütçesi değildir; cihaz, arsa ve dış
        altyapı yatırımı eksiktir.
      </p>
      <h3>Hastane büyüklüğü ve alan</h3>
      <p>
        {p.templates.map((t) => t.label).join(" · ")}. Hekim sayısı bu listeden
        bağımsız seçilir. Kapalı alan = 4.000 + 160 × yatak + 80 × hekim m²; en
        fazla 9 kat. Bu alan formülü ve tesis başına en az 12 hekim birer
        tasarım varsayımıdır, mevzuat standardı değildir.
      </p>
      <p>
        {fmt(data.metadata.candidateCount)} aday, 45/80/120/210 m yarıçaplı yol
        dışı yapı izlerinden oluşur. Büyük tesis küçük bir iz içine
        sıkıştırılmaz. Yol ve yüzey ray koridorlarına taşan veya birbirleriyle
        çakışan izler kullanılamaz. Mevcut binalar engel sayılmaz. Parsel, imar
        ve mühendislik uygunluğu sınanmaz.
      </p>
      <h3>91 hastane deneyi nasıl yorumlanmalı?</h3>
      <p>
        Araba 30, EGO 45 dakika; il genelinde %95 ve her ilçede %80 talep
        hedefi. İlk koşul en fazla 91 tesistir; tam 91 açmak zorunlu değildir.
        Geçerli plan bulunursa yatak, hekim, alan, maliyet, yol ve ilçe
        kısıtları ayrıca denetlenir.
      </p>
      <p>
        İmkânsızlık iddiası için tüm adayları ve tüm süre içi bağlantıları
        kullanan ayrı bir coğrafi model çalışır. Kapasite ve alan çakışmaları
        kaldırılmış bu iyimser modelde alt sınır 91’i aşarsa daha sıkı asıl
        model de 91 ile çözülemez. Bu kanıt kullanılan aday/yol ağına aittir;
        bütün Ankara için gerçek EGO planlama standardı değildir.
      </p>
      <h3>Maliyet ile süre arasındaki tercih</h3>
      <p>
        İlk aşamada düşük yıllık maliyetli geçerli plan aranır. Sonra aynı
        toplam talebe örneğin en fazla %10 ek yıllık maliyetle daha kısa yol
        aranır. Bir dakikaya keyfî TL fiyatı verilmez. Alt sınır ve optimalite
        açığı maliyet aşamasına aittir; son hastane sayısının minimum olduğunun
        kanıtı değildir.
      </p>
      <p>
        Hızlı model, her mahallede her yapı-izi sınıfından süre içindeki en
        yakın 12 adayı değerlendirir. Bu daraltılmış aramanın başarısızlığı
        imkânsızlık olarak sunulmaz. Mahalle talebi birden çok hastaneye
        bölünebilir. Ortalama yol bütün atama paylarıyla ağırlıklıdır; P90’da
        atanmamış ve konumsuz talep sonsuz süreli sayılır.
      </p>
      <h3>Ulaşım ve veri sınırları</h3>
      <p>
        <b>Araba:</b> yönlü OSM yolları ve sınıf bazlı hız, 3 dakika giriş/park;
        canlı trafik ve dönüş yasakları yok. <b>EGO:</b> OSM güzergâhları,
        yürüyüş ve aktarma ağı; otobüste 8, raylı sistemde 4 dakika varsayılan
        bekleme. Güncel GTFS bulunmadığı için tarifeli EGO yolculuğu ölçülmez.
        Büyük izlerde giriş bağlantısı süreye eklenir ve 15 dakikalık erişim
        yürüyüşü sınırı yeniden kontrol edilir.
      </p>
      <ul className="assumption-list">
        {p.assumptions.map((a) => (
          <li key={a}>{a}</li>
        ))}
      </ul>
      <h3>Hesabı besleyen kaynaklar</h3>
      {p.sources.map((s) => (
        <p key={s.id}>
          <a href={s.verifiedCopyUrl || s.url} target="_blank" rel="noreferrer">
            {s.title} <ArrowUpRight size={13} />
          </a>
          {s.note && <small className="source-detail">{s.note}</small>}
        </p>
      ))}
    </div>
  );
}
