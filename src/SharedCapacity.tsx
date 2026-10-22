import { useEffect, useState } from "react";
import { transitProfileLabels } from "./types";
import type { Scenario, TransitProfile } from "./types";

export type SharedCapacityReport = {
  transitPackageId: string;
  sourcePlan: {
    sha256: string;
    transitPackageId: string;
    hospitalCount: number;
    scenario: Scenario;
    originalAnnualBudgetTRY: number;
  };
  result: {
    status: "feasible" | "infeasible" | "inconclusive";
    totalBeds: number | null;
    totalDoctors: number | null;
    annualEquivalentCostTRY: number | null;
    costGap: number | null;
    budgetStatus: string;
    meetsOriginalBudget: boolean | null;
  };
  independentResourceCeiling: {
    anyProfileProvesTargetsImpossible: boolean;
    profiles: {
      profile: TransitProfile;
      status: "optimal" | "district_targets_infeasible" | "mandatory_site_infeasible" | "inconclusive";
      maximumCoveragePercent: number | null;
      provinceTargetShortfallResidents: number | null;
      linearProgrammingDualCertified: boolean;
    }[];
  };
};
const fmt = (n: number, digits = 1) => n.toLocaleString("tr-TR", { maximumFractionDigits: digits });

export function SharedCapacityContent({ report, packageId, planSha }: {
  report: SharedCapacityReport; packageId?: string; planSha: string;
}) {
  if (!packageId || report.transitPackageId !== packageId ||
    report.sourcePlan.transitPackageId !== packageId || report.sourcePlan.sha256 !== planSha) {
    return <p role="status">Ortak kapasite deneyi güncel kayıtlı planla eşleşmiyor; önceki sonuç gösterilmiyor.</p>;
  }
  const result = report.result;
  const plan = report.sourcePlan;
  const ceiling = report.independentResourceCeiling;
  const profiles = Object.keys(transitProfileLabels);
  const complete = ceiling.profiles.length === profiles.length && profiles.every((p) =>
    ceiling.profiles.filter((row) => row.profile === p).length === 1);
  const headline = !complete ? "Profil denetimleri tamamlanmamış" :
    result.status === "inconclusive" ? "Ortak kapasite deneyi henüz sonuçlandırılamadı" :
    result.status === "infeasible" ? "Bu konum ve yapı izlerinde yalnız kapasite artırımı yeterli değil" :
    result.meetsOriginalBudget === true ? "Ortak kapasite tasarımı orijinal bütçe içinde bulundu" :
    "Ortak kapasite tasarımı bulundu; orijinal bütçe içinde olduğu doğrulanmadı";
  return <details className="robustness-diagnostics shared-capacity">
    <summary>Sadece yatak ve hekim artırmak yeterli mi?</summary>
    <h4>{headline}</h4>
    <p>Kayıtlı <b>{fmt(plan.hospitalCount, 0)} konum ve yapı izi</b> korunur.
      Yatak tipi ve hekim sayısı dört profil için birlikte yeniden seçilir; her profil farklı hastanelere talep atayabilir.
      Hedefler {plan.scenario.threshold} dakika, il genelinde %{plan.scenario.coverageTarget},
      her ilçede %{plan.scenario.districtFloor}. Yeni konum veya daha geniş yapı izi seçilmez.</p>
    {complete && result.status === "feasible" && result.annualEquivalentCostTRY != null && <p>
      Bulunan tasarım: {result.totalBeds == null ? "—" : fmt(result.totalBeds, 0)} yatak,
      {" "}{result.totalDoctors == null ? "—" : fmt(result.totalDoctors, 0)} hekim;
      {" "}{fmt(result.annualEquivalentCostTRY / 1e9, 2)} mr ₺/yıl.
      Orijinal tavan {fmt(plan.originalAnnualBudgetTRY / 1e9, 2)} mr ₺/yıl.
      {result.costGap != null && ` Maliyet açıklığı %${fmt(result.costGap * 100, 2)}; yalnız bu sabit konumlar için.`}
      {result.budgetStatus === "incumbent_over_budget_unresolved" && " Daha ucuz, bütçeye uygun bir çözümün bulunup bulunmadığı belirsiz."}
    </p>}
    <p><b>Ayrı iyimser sınır:</b> bütçe ve maliyet tamamen kaldırılır;
      her yapı izine sığabilen en yüksek yatak/hekim kapasitesi verilir.
      İlçe hedefleri korunarak her profilde karşılanabilecek en çok talep hesaplanır.
      Bu sınır da il hedefinin altındaysa aynı yapı izlerinde kaynak satın almak sorunu çözemez.</p>
    <div className="table-scroll"><table className="capacity-table robustness-table">
      <caption>Aynı yapı izlerinde maliyet sınırı olmadan kapasite tavanı</caption>
      <thead><tr><th>Başlangıç profili</th><th>En çok karşılanan talep</th><th>İl hedefine en az açık</th></tr></thead>
      <tbody>{ceiling.profiles.map((row) => <tr key={row.profile}>
        <td>{transitProfileLabels[row.profile]}</td>
        <td>{row.status === "optimal" && row.linearProgrammingDualCertified && row.maximumCoveragePercent != null
          ? `%${fmt(row.maximumCoveragePercent, 2)}`
          : row.status === "district_targets_infeasible" ? "İlçe hedefleri sağlanamıyor"
          : row.status === "mandatory_site_infeasible" ? "Zorunlu yapı izi yetersiz" : "Sonuç belirsiz"}</td>
        <td>{row.status === "optimal" && row.linearProgrammingDualCertified && row.provinceTargetShortfallResidents != null
          ? `${fmt(Math.floor(Math.max(0, row.provinceTargetShortfallResidents) * 100) / 100, 2)} kişi eşdeğeri` : "—"}</td>
      </tr>)}</tbody>
    </table></div>
    <p>Bu kayıtlı planın tanısıdır; canlı ayarlar bu deneyi değiştirmez. Başka konumlarda veya gerçek Ankara'da
      hedeflerin olanaksız olduğunu göstermez. Klinik oranlar, yapı alanı ve ara durak süreleri model varsayımlarını içerir.</p>
  </details>;
}

export default function SharedCapacity({ packageId, planSha }: { packageId?: string; planSha: string }) {
  const [report, setReport] = useState<SharedCapacityReport | null>(null);
  useEffect(() => {
    let active = true;
    fetch("/api/shared-capacity").then((r) => r.ok ? r.json() : null).then((value) => {
      if (active) setReport(value);
    }).catch(() => {});
    return () => { active = false; };
  }, []);
  return report ? <SharedCapacityContent report={report} packageId={packageId} planSha={planSha} /> : null;
}
