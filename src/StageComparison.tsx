import type { Result } from "./types";

const fmt = (value: number, digits = 1) =>
  value.toLocaleString("tr-TR", { maximumFractionDigits: digits });
const gap = (value: number | null | undefined) =>
  value == null ? "Hesaplanamadı" : `%${fmt(value * 100)}`;

export function allocationScopeLabel(result: Result) {
  return result.capacity?.optimalityScope === "all_candidate_allocation_edges"
    ? "örneklenen tam aday ağında"
    : result.searchScope
      ? "daraltılmış aramada"
      : "kayıtlı arama kapsamında";
}

export function CostGapCaption({ result }: { result: Result }) {
  const finalKnown =
    result.capacity != null && "finalPlanCostGap" in result.capacity;
  return (
    <>
      {finalKnown ? "Son plan maliyet açığı" : "İlk maliyet aşaması açığı"}:{" "}
      {gap(finalKnown ? result.capacity?.finalPlanCostGap : result.gap)} (
      {allocationScopeLabel(result)})
    </>
  );
}

export default function StageComparison({ result }: { result: Result | null }) {
  const capacity = result?.capacity;
  const first = capacity?.referenceStage;
  if (!result || !capacity || !first) return null;
  const cleanup = capacity.resourceCleanup;
  const allEdges = first.boundScope === "all_candidate_allocation_edges";
  return (
    <details className="stage-comparison">
      <summary>İlk maliyet planı ile son planı karşılaştır</summary>
      <p>
        İlk sütun maliyet aşamasında bulunan planı korur. Son sütun ulaşım
        tercihi ve uygulanabilen kaynak düzenlemesinden sonra dönen plandır.
        Hastane sayısını azaltmak ayrı bir amaç olarak çözülmez.
      </p>
      {capacity.numericalFallback?.selectedIncumbentValidated && (
        <p>
          Sayısal doğrulama için önceki geçerli plan kullanıldı. Son sütun, bu
          doğrulanmış planın akışını ve uygulanabilen kaynak düzenlemesini
          gösterir.
        </p>
      )}
      <div className="table-scroll">
        <table className="capacity-table">
          <thead>
            <tr>
              <th>Gösterge</th>
              <th>İlk maliyet planı</th>
              <th>Son plan</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Hastane</td>
              <td>{fmt(first.hospitalCount, 0)}</td>
              <td>
                {result.hospitalCount == null
                  ? "—"
                  : fmt(result.hospitalCount, 0)}
              </td>
            </tr>
            <tr>
              <td>Yatak</td>
              <td>{fmt(first.totalBeds, 0)}</td>
              <td>{fmt(capacity.totalBeds, 0)}</td>
            </tr>
            <tr>
              <td>Hekim</td>
              <td>{fmt(first.totalDoctors, 0)}</td>
              <td>{fmt(capacity.totalDoctors, 0)}</td>
            </tr>
            <tr>
              <td>Atanan kişi eşdeğeri</td>
              <td>{fmt(first.coveredPopulation, 0)}</td>
              <td>
                {result.metrics
                  ? fmt(result.metrics.coveredPopulation, 0)
                  : "—"}
              </td>
            </tr>
            <tr>
              <td>Ortalama yolculuk</td>
              <td>{fmt(first.meanMinutes, 2)} dk</td>
              <td>
                {result.metrics?.meanMinutes == null
                  ? "—"
                  : `${fmt(result.metrics.meanMinutes, 2)} dk`}
              </td>
            </tr>
            <tr>
              <td>Yıllık eşdeğer maliyet</td>
              <td>{fmt(first.annualEquivalentCostTRY / 1e9, 2)} mr ₺/yıl</td>
              <td>{fmt(capacity.annualEquivalentCostTRY / 1e9, 2)} mr ₺/yıl</td>
            </tr>
            <tr>
              <td>Aynı maliyet alt sınırına göre açıklık</td>
              <td>{gap(first.gap)}</td>
              <td>{gap(capacity.finalPlanCostGap)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        Maliyet aşamasının alt sınırı{" "}
        {first.lowerBoundTRY == null
          ? "hesaplanamadı"
          : `${fmt(first.lowerBoundTRY / 1e9, 2)} mr ₺/yıl`}
        .
        {allEdges
          ? " Bu sınır, örneklenen adayların bütün talep bağlantılarını kullanan maliyet problemine aittir."
          : ` Bu sınır, ${result.searchScope ? `her yapı izi sınıfından en yakın ${result.searchScope.nearestCandidatesPerFootprintClass} adayla` : "tutulan aday bağlantılarıyla"} daraltılan maliyet problemine aittir; bütün aday bağlantıları için küresel sınır değildir.`}{" "}
        İlk aşama açıklığı son planın açıklığı yerine kullanılamaz; açıklık,
        daha iyi bir çözümün mutlaka bulunacağı yüzdesi değildir. Süre
        aşamasının açıklığı farklı bir amaç değerine aittir.
      </p>
      {cleanup?.applied === true &&
        cleanup.allocationsPreserved &&
        cleanup.travelPreserved && (
          <p>
            Son kaynak düzenlemesinde atamalar ve yolculuk süreleri korunarak{" "}
            {fmt(cleanup.removedHospitalCount, 0)} boş tesis,
            {` ${fmt(cleanup.removedBeds, 0)} yatak ve ${fmt(cleanup.removedDoctors, 0)} hekim`}{" "}
            kaldırıldı. Yıllık maliyet{" "}
            {fmt(cleanup.annualCostReductionTRY / 1e6, 2)} mn ₺ azaldı. Bu,
            mevcut akış için kaynak düzenlemesidir; yeni konum optimizasyonu
            değildir.
          </p>
        )}
      {cleanup?.applied === false && (
        <p>
          Sayısal tolerans nedeniyle ek kaynak temizliği uygulanmadı; çözücünün
          geçerli planı korundu.
        </p>
      )}
      <small>
        {capacity.priceBase}. Toplam gerçek kamu bütçesi veya minimum hastane
        sayısı iddiası değildir.
      </small>
    </details>
  );
}
