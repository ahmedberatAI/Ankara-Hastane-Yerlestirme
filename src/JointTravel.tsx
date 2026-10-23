import { ArrowDownRight, ChevronDown } from "lucide-react";
import { transitProfileLabels } from "./types";
import type { TransitProfile } from "./types";
import type { JointPlanReport } from "./JointPlan";
import AccessConnectors from "./AccessConnectors";
import type { AccessConnectorReport } from "./AccessConnectors";
import savedConnectors from "../data/processed/access-connector-summary.json";
import manifest from "../data/processed/manifest.json";

const fmt = (n: number, digits = 2) => n.toLocaleString("tr-TR", { maximumFractionDigits: digits });
export type JointTravelReport = {
  status: string; transitPackageId: string; planningVersion: string;
  scenario: JointPlanReport["scenario"]; sourceCostCertificateSHA256: string; sourceSHA256: Record<string, string>;
  hospitalCount: number; beds: number; doctors: number; annualEquivalentCostTRY: number;
  annualCostUnchanged: boolean; resourcesUnchanged: boolean; globalTravelOptimumProven: boolean;
  allProfilesAccepted: boolean; acceptedProfileCount: number;
  profiles: {
    profile: TransitProfile; status: string; accepted: boolean; sourceFallback: boolean;
    sourceMeanMinutes: number; meanMinutes: number; reductionMinutes: number;
    coveragePercent: number; minimumDistrictCoveragePercent: number; maxMinutes: number;
    lowerBoundMinutes: number | null; primalMinusLowerBoundMinutes: number | null;
    primalDualToleranceMinutes: number | null; certifiedForRepresentedFixedResourceLP: boolean;
    districts: JointPlanReport["profiles"][number]["districts"];
  }[];
  conditionalOverlap: JointPlanReport["conditionalOverlap"];
};

export function jointTravelState(report: JointTravelReport, source: JointPlanReport) {
  const object = (v: unknown) => v != null && typeof v === "object" && !Array.isArray(v);
  const finite = (v: number) => typeof v === "number" && Number.isFinite(v);
  const near = (a: number, b: number, tol = 1e-7) => finite(a) && finite(b) && Math.abs(a - b) <= tol;
  if (!object(report) || !object(report.scenario) || !object(report.sourceSHA256) || !Array.isArray(report.profiles) ||
    !object(report.conditionalOverlap) || !object(report.conditionalOverlap.province) ||
    report.profiles.some(p => !object(p) || !Array.isArray(p.districts) || p.districts.some(d => !object(d)))) return "invalid";
  if (!source.sourceSHA256 || !/^[a-f0-9]{64}$/.test(source.sourceSHA256["joint-plan.json"] || "") ||
    report.sourceCostCertificateSHA256 !== source.sourceSHA256["joint-plan.json"] ||
    report.transitPackageId !== source.transitPackageId || report.planningVersion !== source.planningVersion ||
    Object.entries(source.sourceSHA256).some(([name, hash]) => report.sourceSHA256[name] !== hash) ||
    Object.entries(source.scenario).some(([key, value]) => report.scenario[key as keyof typeof report.scenario] !== value)) return "stale";
  const overlap = report.conditionalOverlap.province;
  const names = Object.keys(transitProfileLabels);
  const count = report.profiles.filter(p => p.accepted === true).length;
  if (report.status !== "validated_fixed_resource_travel" || report.resourcesUnchanged !== true ||
    report.annualCostUnchanged !== true || report.globalTravelOptimumProven !== false ||
    report.hospitalCount !== source.hospitalCount || report.beds !== source.beds || report.doctors !== source.doctors ||
    !near(report.annualEquivalentCostTRY, source.annualEquivalentCostTRY, .001) ||
    report.acceptedProfileCount !== count || report.allProfilesAccepted !== (count === 4) ||
    report.conditionalOverlap.sameIndividualsObserved !== false || !finite(overlap.lowerPercent) || !finite(overlap.upperPercent) ||
    overlap.lowerPercent < 0 || overlap.upperPercent > 100 || overlap.lowerPercent > overlap.upperPercent ||
    report.profiles.length !== 4 || names.some(n => report.profiles.filter(p => p.profile === n).length !== 1)) return "invalid";
  for (const p of report.profiles) {
    const before = source.profiles.find(s => s.profile === p.profile);
    if (!before || !near(p.sourceMeanMinutes, before.meanMinutes) || !finite(p.meanMinutes) || p.meanMinutes < 0 ||
      !finite(p.maxMinutes) || p.maxMinutes > 45 || p.meanMinutes > p.maxMinutes + 1e-7 ||
      p.meanMinutes > p.sourceMeanMinutes + 1e-7 || !near(p.reductionMinutes, p.sourceMeanMinutes - p.meanMinutes) ||
      !near(p.coveragePercent, 95, 1e-6) || !finite(p.minimumDistrictCoveragePercent) ||
      p.minimumDistrictCoveragePercent < 80 - 1e-6 || p.minimumDistrictCoveragePercent > 100 ||
      p.districts.length !== 25 || new Set(p.districts.map(d => d.id)).size !== 25 ||
      !near(Math.min(...p.districts.map(d => d.coveragePercent)), p.minimumDistrictCoveragePercent, 1e-6) ||
      p.districts.some(d => !finite(d.coveragePercent) || d.coveragePercent < 80 - 1e-6 || d.coveragePercent > 100 + 1e-6 ||
        !before.districts.some(b => b.id === d.id && b.population === d.population))) return "invalid";
    if (p.accepted === true) {
      if (p.status !== "travel_profile_accepted" || p.sourceFallback !== false || p.certifiedForRepresentedFixedResourceLP !== true ||
        p.lowerBoundMinutes === null || !finite(p.lowerBoundMinutes) || p.primalMinusLowerBoundMinutes === null ||
        !near(p.primalMinusLowerBoundMinutes, p.meanMinutes - p.lowerBoundMinutes) ||
        p.primalDualToleranceMinutes !== 1e-7 || p.primalMinusLowerBoundMinutes < -p.primalDualToleranceMinutes) return "invalid";
    } else if (p.accepted !== false || p.status !== "source_preserved" || p.sourceFallback !== true ||
      p.certifiedForRepresentedFixedResourceLP !== false || p.lowerBoundMinutes !== null ||
      p.primalMinusLowerBoundMinutes !== null || p.primalDualToleranceMinutes !== null ||
      !near(p.meanMinutes, p.sourceMeanMinutes) || p.reductionMinutes !== 0) return "invalid";
  }
  if (overlap.upperPercent > Math.min(...report.profiles.map(p => p.coveragePercent)) + 1e-6 ||
    overlap.lowerPercent < Math.max(0, report.profiles.reduce((s, p) => s + p.coveragePercent, 0) - 300) - 1e-6) return "invalid";
  return "valid";
}

export function JointTravelContent({ report, source }: { report: JointTravelReport; source: JointPlanReport }) {
  const state = jointTravelState(report, source);
  if (state !== "valid") return <section className="joint-travel"><p role="status">{state === "stale"
    ? "Süre deneyi güncel maliyet planıyla eşleştiriliyor; önceki süre sonucu gösterilmiyor."
    : "Süre deneyinin doğrulaması tamamlanmamış. Yukarıdaki maliyet planı ayrı değerlendirilir."}</p></section>;
  const overlap = report.conditionalOverlap.province;
  return <section className="joint-travel" aria-labelledby="joint-travel-title">
    <span className="eyebrow">KAYITLI EGO DENEYİ · İKİNCİ AŞAMA</span>
    <h4 id="joint-travel-title">Aynı hastanelerle yolculuk süresini azaltmak</h4>
    <p>{fmt(report.hospitalCount, 0)} konum, {fmt(report.beds, 0)} yatak ve {fmt(report.doctors, 0)} hekim sabit tutuldu.
      Yalnız mahalle talebinin bu tesislere dağılımı yeniden seçildi. Yıllık eşdeğer maliyet
      {" "}<b>{fmt(report.annualEquivalentCostTRY / 1e9, 3)} milyar TL</b> olarak kaldı; ek kaynak alınmadı.</p>
    <div className="table-scroll"><table className="capacity-table joint-table joint-travel-table">
      <caption>Maliyet aşaması → süre aşaması · atanan taleple ağırlıklı ortalama</caption>
      <thead><tr><th>Başlangıç</th><th>Önce</th><th>Sonra</th><th>Kısalma</th></tr></thead>
      <tbody>{report.profiles.map(p => <tr key={p.profile}><td>{transitProfileLabels[p.profile]}</td>
        <td>{fmt(p.sourceMeanMinutes)} dk</td><td><b>{fmt(p.meanMinutes)} dk</b></td>
        <td>{p.accepted ? <span className="joint-time-saving"><ArrowDownRight size={15} />{fmt(p.reductionMinutes)} dk</span>
          : <span>Başlangıç korundu</span>}</td></tr>)}</tbody>
    </table></div>
    <p className="joint-travel-targets">Dört profilde de il kapsamı %95, her ilçede en az %80 ve her atamada en fazla 45 dakika korunuyor.</p>
    <p className="joint-note">Bu dört başlangıç, gün boyu erişimi garanti etmez.{" "}
      <a href="https://github.com/ahmedberatAI/Ankara-Hastane-Yerlestirme/blob/main/docs/departure-sensitivity.md"
        target="_blank" rel="noreferrer">08.05 ek deneyi ve kapasite sınırı</a></p>
    <p className="joint-note">Bu kayıtlı EGO deneyi canlı ayarlarla değişmez. Ortalama, her senaryoda hizmet verilen nüfus için hesaplanır. Hizmet alan mahalle payları değişebilir;
      herkesin yolculuğunun kısaldığı anlamına gelmez.</p>
    {!report.allProfilesAccepted && <p className="joint-note">{report.acceptedProfileCount}/4 profil için süre iyileştirmesi doğrulandı.
      Diğer profillerin eski atamaları korundu; iyileştirme bulunmaması olanaksızlık kanıtı değildir.</p>}
    <details className="joint-details"><summary>Süre hesabı neyi kanıtlıyor? <ChevronDown size={16} /></summary>
      <p>Her başlangıç saati ayrı bir atama problemi. Nüfusla ağırlıklı ortalama, aynı tesislerin yatak ve hekim sınırları içinde azaltılıyor.
        Tesis yeri ve büyüklüğü bu aşamada yeniden seçilmiyor. Dört profilin süreleri yıllık bir toplam gibi toplanmıyor.</p>
      <p>Bağımsız denetim kayıtlı sayısal katsayılardan süre alt sınırını tekrar hesaplar.
        Küçük negatif farklar sayısal uygulanabilirlik toleransından kaynaklanabilir; sıfıra gizlenmez.
        Bu kanıt genel yerleşim optimumu veya gerçek EGO tarifelerinin eksiksizliği anlamına gelmez.</p>
      <div className="table-scroll"><table className="capacity-table joint-table">
        <caption>Yalnız sabit kaynaklar için alt sınır · imzalı fark = ortalama − alt sınır</caption>
        <thead><tr><th>Başlangıç</th><th>Alt sınır</th><th>İmzalı fark (dk)</th></tr></thead>
        <tbody>{report.profiles.map(p => <tr key={p.profile}><td>{transitProfileLabels[p.profile]}</td>
          <td>{p.lowerBoundMinutes === null ? "Doğrulanmadı" : `${fmt(p.lowerBoundMinutes, 8)} dk`}</td>
          <td>{p.primalMinusLowerBoundMinutes === null ? "—" : p.primalMinusLowerBoundMinutes.toExponential(2)}</td></tr>)}</tbody>
      </table></div>
      <p>İmzalı fark için sayısal tolerans 10⁻⁷ dakika. Matematiksel alt sınır, bilgisayarda saklanan katsayılar içindir;
        klinik kapasite ve sefer süresi varsayımlarının doğruluğunu kanıtlamaz.</p>
      <p>Yeni atamaların aynı kişileri kapsama aralığı koşullu olarak %{fmt(overlap.lowerPercent)}–%{fmt(overlap.upperPercent)}.
        Aynı kişilerin dört profilde %95 kapsanması garanti edilmez. Yukarıdaki harita yükleri ve ortak kapsam açıklaması maliyet aşamasına aittir.</p>
    </details>
    <AccessConnectors report={savedConnectors as unknown as AccessConnectorReport} travel={report}
      expectedSummarySHA={manifest.files.find(f => f.file === "data/processed/travel-summary.json")?.sha256 || ""} />
    <a className="text-link" href="https://github.com/ahmedberatAI/Ankara-Hastane-Yerlestirme/blob/main/docs/joint-travel.md"
      target="_blank" rel="noreferrer">Süre aşaması: formül, bağımsız denetim ve sınırlar</a>
  </section>;
}
