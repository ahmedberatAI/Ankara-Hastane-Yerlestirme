import { Info, ArrowUpRight } from "lucide-react";
import type { Dataset } from "./types";

const fmt = (n: number, digits = 0) =>
  n.toLocaleString("tr-TR", { maximumFractionDigits: digits });

export default function HealthMethod({ data }: { data: Dataset }) {
  const p = data.healthPlanning;
  return (
    <div className="method-content">
      <p className="lead">
        Ulaşabilmek tek başına yeterli değil. Atanan talebin hem yatak hem hekim
        kapasitesine sığması gerekiyor. Model, tesisin yerini ve büyüklüğünü
        birlikte seçiyor.
      </p>
      <div className="method-steps">
        <article>
          <span>01</span>
          <h3>Talebi hesapla</h3>
          <p>
            Mahalle nüfusu × Ankara’nın kişi başı yıllık hizmet kullanımı.
            Başvurular hekim yüküne, yatış günleri yatak yüküne dönüşür.
          </p>
        </article>
        <article>
          <span>02</span>
          <h3>Maliyeti azalt</h3>
          <p>
            İl ve ilçe hedefleri sağlanırken 50, 150 veya 300 yataklı tesisler
            arasından düşük yapım bedelli bir yerleşim aranır.
          </p>
        </article>
        <article>
          <span>03</span>
          <h3>Yolu kısalt</h3>
          <p>
            Karşılanan toplam talebi koruyup seçtiğiniz ek bütçe sınırı içinde
            yolculuk süresini azaltırız. Süre ve kapasite sınırları korunur.
          </p>
        </article>
      </div>
      <h3>Resmî veri · Ankara, {p.referenceYear}</h3>
      <div className="evidence-grid">
        {[
          [p.observed.beds, "hastane yatağı"],
          [p.observed.physicians, "hekim · tüm sektörler"],
          [p.observed.secondaryTertiaryVisits, "2. / 3. basamak başvurusu"],
          [p.observed.admissions, "hastane yatışı"],
          [p.observed.bedDays, "yatılan gün"],
          [p.observed.hospitalCount, "hastane · 2024 envanteri"],
        ].map(([value, label]) => (
          <div key={String(label)}>
            <b>{fmt(Number(value))}</b>
            <span>{label}</span>
          </div>
        ))}
      </div>
      <p>
        Kaynak:{" "}
        <a href={p.sources[0].url} target="_blank" rel="noreferrer">
          Sağlık Bakanlığı 2024 Yıllığı
        </a>
        , tablolar 7.20, 8.26 ve 10.12; basılı sayfa 162, 204, 206 ve 261.
        Tarihli resmî envanter ile haritadaki doğrulanmamış OSM kayıtları farklı
        kapsamlardır.
      </p>
      <div className="formula">
        <span>MAHALLEDEN HİZMET TALEBİNE</span>
        <strong>
          Yıllık başvuru = nüfus × {fmt(p.rates.visitsPerResident, 3)} × talep
          çarpanı
        </strong>
        <strong>
          Yatış günü = nüfus × {fmt(p.rates.bedDaysPerResident, 3)} × talep
          çarpanı
        </strong>
        <p>
          2024 hizmet toplamları, aynı yılın {fmt(p.observed.population)}{" "}
          nüfusuna bölünür. Bu oranlar 2025 mahalle nüfusuna uygulanır. Başvuru,
          tekil hasta sayısı değildir.
        </p>
      </div>
      <h3>Bir hastanenin alabileceği yük</h3>
      <p>
        <b>Hekim sınırı:</b> atanan yıllık başvuru ≤ hekim sayısı × hekim başına
        yıllık başvuru kapasitesi.
      </p>
      <p>
        <b>Yatak sınırı:</b> atanan yıllık yatış günü ≤ yatak sayısı × 365 ×
        doluluk tavanı. Yatış süresi veriden {fmt(p.rates.lengthOfStayDays, 2)}{" "}
        gün olarak türetilir; yatış günü ayrıca bu süreyle tekrar çarpılmaz.
      </p>
      <div className="table-scroll">
        <table className="capacity-table">
          <thead>
            <tr>
              <th>Tesis şablonu</th>
              <th>Hekim</th>
              <th>Kapalı alan</th>
              <th>Birim bedel</th>
              <th>Yapım göstergesi</th>
            </tr>
          </thead>
          <tbody>
            {p.templates.map((t) => (
              <tr key={t.id}>
                <td>{t.label}</td>
                <td>{t.doctors}</td>
                <td>{fmt(t.grossAreaM2)} m²</td>
                <td>{fmt(t.unitCostTRY)} ₺/m²</td>
                <td>{fmt(t.constructionCostTRY / 1e6, 1)} mn ₺</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="note-block">
        <Info size={20} />
        <div>
          <b>Gözlem ile planlama varsayımı ayrı.</b>
          <p>
            Tesis büyüklükleri, hekim kadroları, kapalı alanlar, %80 doluluk
            tavanı ve 4.000 başvuru/hekim/yıl tasarım varsayımlarıdır. Sonuncusu
            20 başvuru × 200 klinik gün senaryosudur; resmî iş yükü standardı
            değildir. Ankara’daki 26.798 hekim, hastanelere ayrılabilir kadro
            olarak kullanılmaz.
          </p>
        </div>
      </div>
      <h3>Maliyet ve süre arasındaki tercih</h3>
      <p>
        Önce kapasite ve erişim hedefleri altında düşük maliyetli bir geçerli
        çözüm bulunur. Sonra örneğin %10 ek bütçe seçildiğinde, o çözümün yapım
        bedelinin en fazla 1,10 katıyla aynı toplam talebe daha kısa yol aranır.
        Sıfır ek bütçe seçeneği de vardır. Böylece bir dakikaya keyfî bir TL
        değeri vermeyiz.
      </p>
      <p>
        Maliyet açığı, ilk aşamanın bulunan bedeli ile matematiksel alt sınırı
        arasındadır; son yerleşimin minimum hastane sayısı olduğunu söylemez.
        Süre aşamasının açığı ayrıca sonuçların altında gösterilir; iki aşamanın
        matematiksel ispat sınırları farklıdır. Her aşama süre sınırlıdır.
        İkinci aşamada daha iyi geçerli çözüm bulunamazsa ilk çözüm korunur. Her
        mahalle için süre sınırındaki en yakın 16 aday kullanılır; sonuç bu
        arama kapsamına aittir.
      </p>
      <h3>Haritadaki renkler ve yol</h3>
      <p>
        Mahallenin yıllık talebi birden çok hastaneye bölünebilir. Yeşil tam,
        turuncu kısmi, gri atanmamış talebi gösterir. Mahalleye tıkladığınızda
        her tesisin aldığı pay ve güzergâhı açılır. Ortalama süre bütün atama
        paylarıyla ağırlıklıdır. P90 hesabında karşılanmayan ve konumu
        bilinmeyen talep sonsuz süreli sayılır.
      </p>
      <h3>Bu hesabın sınırları</h3>
      <ul className="assumption-list">
        {p.assumptions.map((a) => (
          <li key={a}>{a}</li>
        ))}
      </ul>
      <p>
        <b>Araba:</b> yönlü OSM yol ağı, sınıf bazlı hız ve 3 dakika giriş/park
        payı. Canlı trafik ve dönüş yasakları yoktur. <b>EGO:</b> gerçek OSM hat
        geometrileri, yürüyüş ve aktarmalar; otobüste 8, raylı sistemde 4 dakika
        varsayılan bekleme. Güncel GTFS doğrulanamadığı için tarifeli yolculuk
        hesabı değildir.
      </p>
      <p>
        30/45 dakika, %95 il hedefi ve %80 ilçe tabanı planlama tercihleridir.
        Binalar engel sayılmaz; tahmini yol ve yüzey ray koridorları dışlanır.
        İki önerilen tesisin yapı izleri de çakışamaz.{" "}
        {fmt(data.metadata.unlocatedPopulation)} konumsuz kişi talep paydasında
        kalır. Hastane dolulukları yıllık ortalamadır; branş, yoğun bakım,
        hemşire, kuyruk, pik gün ve deprem senaryosu ayrıca modellenmemiştir.
      </p>
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
