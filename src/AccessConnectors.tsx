import { ChevronDown } from "lucide-react";
import type { JointTravelReport } from "./JointTravel";
import { transitProfileLabels } from "./types";
import type { TransitProfile } from "./types";

export type AccessConnectorReport = {
  format: number; status: string; transitPackageId: string; planningVersion: string;
  hospitalCount: number; walkingSpeedMetersPerSecond: number;
  travelPlanSHA256: string; sourceCostCertificateSHA256: string; sourceTravelSummarySHA256: string;
  sourceSHA256: Record<string, string>; analysisCodeSHA256: Record<string, string>; semanticCodeSHA256: Record<string, string>;
  population: { provincePopulation: number; locatedPopulation: number; unlocatedPopulation: number;
    targetServedPopulationEquivalentPerProfile: number };
  profiles: { profile: TransitProfile; servedEquivalent: number; meanOriginMinutes: number;
    meanHospitalMinutes: number; meanEndpointMinutes: number; shareOfPersonMinutesPercent: number; totalMeanMinutes: number }[];
};
const fmt = (n: number, digits = 2) => n.toLocaleString("tr-TR", { maximumFractionDigits: digits });
const finite = (n: number) => typeof n === "number" && Number.isFinite(n) && n >= 0;
const near = (a: number, b: number, tolerance = 1e-7) => finite(a) && finite(b) && Math.abs(a - b) <= tolerance;
const hash = (value: string) => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const object = (value: unknown) => value != null && typeof value === "object" && !Array.isArray(value);

export function accessConnectorState(report: AccessConnectorReport, travel: JointTravelReport, expectedSummarySHA: string) {
  if (!object(report) || !object(report.population) || !object(report.sourceSHA256) ||
    !object(report.analysisCodeSHA256) || !object(report.semanticCodeSHA256) ||
    !Array.isArray(report.profiles) || report.profiles.some(p => !object(p))) return "invalid";
  if (!hash(expectedSummarySHA) || report.sourceTravelSummarySHA256 !== expectedSummarySHA ||
    report.travelPlanSHA256 !== travel.sourceSHA256["travel-plan.json"] ||
    report.sourceCostCertificateSHA256 !== travel.sourceCostCertificateSHA256 ||
    report.transitPackageId !== travel.transitPackageId || report.planningVersion !== travel.planningVersion ||
    Object.keys(report.sourceSHA256).length !== Object.keys(travel.sourceSHA256).length ||
    Object.entries(travel.sourceSHA256).some(([name, sha]) => !hash(sha) || report.sourceSHA256[name] !== sha)) return "stale";
  const pop = report.population;
  const province = travel.profiles[0].districts.reduce((sum, d) => sum + d.population, 0);
  const names = Object.keys(transitProfileLabels);
  if (report.format !== 1 || report.status !== "descriptive_explicit_connectors" ||
    report.hospitalCount !== travel.hospitalCount || report.walkingSpeedMetersPerSecond !== 1.25 ||
    Object.keys(report.analysisCodeSHA256).length !== 1 || !hash(report.analysisCodeSHA256["scripts/audit_access_connectors.py"]) ||
    Object.keys(report.semanticCodeSHA256).length !== 2 ||
    !hash(report.semanticCodeSHA256["scripts/build_timetable.py"]) ||
    !hash(report.semanticCodeSHA256["backend/timetable.py"]) ||
    ![pop.provincePopulation, pop.locatedPopulation, pop.unlocatedPopulation].every(n => finite(n) && Number.isInteger(n)) ||
    pop.provincePopulation <= 0 || pop.provincePopulation !== province ||
    pop.locatedPopulation + pop.unlocatedPopulation !== province ||
    !near(pop.targetServedPopulationEquivalentPerProfile, province * travel.scenario.coverageTarget / 100, 1e-6) ||
    report.profiles.length !== 4 || names.some(name => report.profiles.filter(p => p.profile === name).length !== 1)) return "invalid";
  for (const row of report.profiles) {
    const source = travel.profiles.find(p => p.profile === row.profile);
    if (!source || ![row.servedEquivalent, row.meanOriginMinutes, row.meanHospitalMinutes, row.meanEndpointMinutes,
      row.shareOfPersonMinutesPercent, row.totalMeanMinutes].every(finite) || row.totalMeanMinutes <= 0 ||
      !near(row.servedEquivalent, pop.targetServedPopulationEquivalentPerProfile, 1e-6) ||
      row.servedEquivalent > pop.locatedPopulation + 1e-6 ||
      !near(row.totalMeanMinutes, source.meanMinutes) ||
      !near(row.meanEndpointMinutes, row.meanOriginMinutes + row.meanHospitalMinutes) ||
      row.meanEndpointMinutes > row.totalMeanMinutes + 1e-7 || row.shareOfPersonMinutesPercent > 100 ||
      !near(row.shareOfPersonMinutesPercent, 100 * row.meanEndpointMinutes / row.totalMeanMinutes)) return "invalid";
  }
  return "valid";
}

export default function AccessConnectors({ report, travel, expectedSummarySHA }: {
  report: AccessConnectorReport; travel: JointTravelReport; expectedSummarySHA: string;
}) {
  const state = accessConnectorState(report, travel, expectedSummarySHA);
  if (state !== "valid") return <p className="joint-note" role="status">Giriş bağlantısı hesabı güncel atamalarla eşleştiriliyor; önceki sayılar gösterilmiyor.</p>;
  return <details className="joint-details">
    <summary>Yolculuğun ne kadarı varsayılan giriş bağlantısı? <ChevronDown size={16} /></summary>
    <p>Mahalle temsil noktasından yola ve yoldan hastane sahasına iki kısa bağlantı varsayılıyor.
      Uzunlukları 1,25 m/s yürüme hızıyla süreye ekleniyor; arazide doğrulanmış giriş yolları değiller.</p>
    <div className="table-scroll"><table className="capacity-table joint-table">
      <caption>Kayıtlı süre aşaması · yalnız iki uç bağlantı · atanan taleple ağırlıklı</caption>
      <thead><tr><th>Başlangıç</th><th>İki bağlantı</th><th>Toplam kişi-dakikadaki pay</th></tr></thead>
      <tbody>{report.profiles.map(row => <tr key={row.profile}>
        <td>{transitProfileLabels[row.profile]}</td><td>{fmt(row.meanEndpointMinutes)} dk</td>
        <td>%{fmt(row.shareOfPersonMinutesPercent)}</td>
      </tr>)}</tbody>
    </table></div>
    <p>Ortalama, her profilde atanan {fmt(report.population.targetServedPopulationEquivalentPerProfile, 0)} kişi eşdeğeriyle ağırlıklıdır.
      Yüzde, toplam kişi-dakika içindeki paydır; dört profil toplanmaz.
      Durak/peron bağlantıları ve diğer ağ belirsizlikleri bu iki parçanın dışında kalır.</p>
    <p><b>Bu süreyi toplamdan çıkarmak yeni bir yolculuk hesabı değildir.</b> Giriş değişirse yetişilen sefer ve bekleme de değişebilir.
      Gösterilen pay, ölçülmüş hata oranı veya kazanılabilecek süre değildir; kalan süre de doğrulanmış saha ölçümü sayılmaz.</p>
    <a className="text-link" href="https://github.com/ahmedberatAI/Ankara-Hastane-Yerlestirme/blob/main/docs/access-connectors.md"
      target="_blank" rel="noreferrer">Bağlantı hesabı ve kapsamı</a>
  </details>;
}
