import { lazy, Suspense, useState } from "react";
import { MapPin, ChevronDown, ExternalLink } from "lucide-react";
import saved from "../data/processed/joint-plan-summary.json";
import { transitProfileLabels } from "./types";
import type { Dataset, Scenario, TransitProfile } from "./types";
import "./joint-plan.css";

const JointPlanMap = lazy(() => import("./JointPlanMap"));
const fmt = (n: number, digits = 1) => n.toLocaleString("tr-TR", { maximumFractionDigits: digits });
export type JointSite = {
  candidateIndex: number; id: string; lon: number; lat: number;
  templateId: string; beds: number; doctors: number;
  maximumAssignedPopulationAcrossProfiles: number;
};
export type JointPlanReport = {
  status: string; transitPackageId: string; planningVersion: string; scenario: Scenario;
  hospitalCount: number; beds: number; doctors: number;
  resourcesSharedAcrossProfiles: boolean; annualDemandCountedOnce: boolean;
  sameIndividualsAcrossProfilesConstrained: boolean;
  annualEquivalentCostTRY: number; originalTransitBudgetTRY: number; budgetSlackTRY: number;
  withinOriginalTransitBudget: boolean;
  selected: JointSite[];
  profiles: { profile: TransitProfile; coveragePercent: number; minimumDistrictCoveragePercent: number;
    meanMinutes: number; maxMinutes: number;
    districts: { id: string; name: string; population: number; coveredPopulation: number; coveragePercent: number }[];
  }[];
  conditionalOverlap: { province: { lowerPercent: number; upperPercent: number }; sameIndividualsObserved: boolean };
};

export function jointPlanState(report: JointPlanReport, packageId?: string, planningVersion?: string,
  current?: Pick<Dataset, "candidates" | "districts">) {
  const object = (value: unknown) => value != null && typeof value === "object" && !Array.isArray(value);
  if (!object(report) || !object(report.scenario) || !Array.isArray(report.selected) || !Array.isArray(report.profiles) ||
    !object(report.conditionalOverlap) || !object(report.conditionalOverlap.province) ||
    report.selected.some(s => !object(s)) || report.profiles.some(row => !object(row) || !Array.isArray(row.districts) ||
      row.districts.some(d => !object(d)))) return "invalid";
  if (!packageId || !planningVersion || report.transitPackageId !== packageId || report.planningVersion !== planningVersion ||
    report.scenario.mode !== "transit" || report.scenario.threshold !== 45 || report.scenario.coverageTarget !== 95 ||
    report.scenario.districtFloor !== 80 || report.scenario.hospitalLimit !== null) return "stale";
  const profiles = Object.keys(transitProfileLabels);
  const finite = (n: number) => Number.isFinite(n) && n >= 0;
  const positiveInteger = (n: number) => Number.isInteger(n) && n > 0;
  const overlap = report.conditionalOverlap.province;
  if (!["witness_validated", "validated_model_plan_above_reference_budget"].includes(report.status) ||
    report.resourcesSharedAcrossProfiles !== true || report.annualDemandCountedOnce !== true ||
    report.sameIndividualsAcrossProfilesConstrained !== false || report.conditionalOverlap.sameIndividualsObserved !== false ||
    ![report.hospitalCount, report.beds, report.doctors].every(positiveInteger) ||
    ![report.annualEquivalentCostTRY, report.originalTransitBudgetTRY].every(finite) || report.originalTransitBudgetTRY <= 0 ||
    !Number.isFinite(report.budgetSlackTRY) ||
    Math.abs(report.originalTransitBudgetTRY - report.annualEquivalentCostTRY - report.budgetSlackTRY) > 1 ||
    report.selected.length !== report.hospitalCount || new Set(report.selected.map(s => s.id)).size !== report.hospitalCount ||
    new Set(report.selected.map(s => s.candidateIndex)).size !== report.hospitalCount ||
    report.selected.some(s => !positiveInteger(s.beds) || !positiveInteger(s.doctors) || typeof s.id !== "string" || !s.id ||
      !Number.isInteger(s.candidateIndex) || s.candidateIndex < 0 || !finite(s.maximumAssignedPopulationAcrossProfiles) ||
      !Number.isFinite(s.lon) || !Number.isFinite(s.lat) || s.lon < 30 || s.lon > 35 || s.lat < 38 || s.lat > 42 ||
      (current && (!current.candidates[s.candidateIndex] || current.candidates[s.candidateIndex].id !== s.id ||
        current.candidates[s.candidateIndex].lon !== s.lon || current.candidates[s.candidateIndex].lat !== s.lat))) ||
    report.selected.reduce((n, s) => n + s.beds, 0) !== report.beds ||
    report.selected.reduce((n, s) => n + s.doctors, 0) !== report.doctors ||
    ![overlap.lowerPercent, overlap.upperPercent].every(finite) || overlap.lowerPercent > overlap.upperPercent || overlap.upperPercent > 100 ||
    report.profiles.length !== profiles.length || profiles.some(p => report.profiles.filter(row => row.profile === p).length !== 1) ||
    report.profiles.some(row => ![row.coveragePercent, row.minimumDistrictCoveragePercent, row.meanMinutes, row.maxMinutes].every(finite) ||
      Math.abs(row.coveragePercent - 95) > 1e-6 || row.minimumDistrictCoveragePercent < 80 - 1e-6 || row.maxMinutes > 45 ||
      row.meanMinutes > row.maxMinutes + 1e-6 || row.districts.length !== 25 || new Set(row.districts.map(d => d.id)).size !== 25 ||
      Math.abs(Math.min(...row.districts.map(d => d.coveragePercent)) - row.minimumDistrictCoveragePercent) > 1e-6 ||
      row.districts.some(d => typeof d.id !== "string" || !d.id || !finite(d.coveragePercent) || d.coveragePercent < 80 - 1e-6 || d.coveragePercent > 100 + 1e-6 ||
        (current && !current.districts.some(original => original.id === d.id && original.population === d.population)))) ||
    (current && current.districts.length !== 25)) return "invalid";
  // This sign comes from the independent Decimal calculation, with no budget
  // allowance. The one-lira check above only reconciles floating-point display.
  const within = report.budgetSlackTRY >= 0;
  if (report.withinOriginalTransitBudget !== within || (report.status === "witness_validated") !== within) return "invalid";
  return within ? "within" : "above";
}

export function JointPlanContent({ report, packageId, planningVersion, map, current }: {
  report: JointPlanReport; packageId?: string; planningVersion?: string; map?: React.ReactNode;
  current?: Pick<Dataset, "candidates" | "districts">;
}) {
  const state = jointPlanState(report, packageId, planningVersion, current);
  if (state === "stale") return <section className="joint-plan"><p role="status">Ortak plan güncel veriyle eşleştiriliyor; önceki hesap gösterilmiyor.</p></section>;
  if (state === "invalid") return <section className="joint-plan"><p role="status">Ortak planın doğrulaması tamamlanmamış. Bu, uygun plan bulunamayacağı anlamına gelmez.</p></section>;
  const overlap = report.conditionalOverlap.province;
  return <section className="joint-plan" aria-labelledby="joint-title">
    <div className="joint-heading"><div><span className="eyebrow">DÖRT BAŞLANGIÇ SAATİ · AYNI KAYNAKLAR</span>
      <h3 id="joint-title">Konumlar da birlikte seçilirse?</h3>
      <p>Her saat için ayrı hastaneler kurmak yerine, konumlar, yataklar ve hekimler ortak seçildi.
        Her profil kendi ulaşım bağlantılarıyla talep atıyor.</p></div><span className="joint-tag">Doğrulanmış model örneği</span></div>
    <div className="joint-metrics">
      <div><b>{fmt(report.hospitalCount, 0)}</b><span>ortak konum</span></div>
      <div><b>{fmt(report.beds, 0)}</b><span>yatak</span></div>
      <div><b>{fmt(report.doctors, 0)}</b><span>hekim</span></div>
      <div><b>{fmt(report.annualEquivalentCostTRY / 1e9, 3)} <small>mr ₺</small></b><span>yıllık eşdeğer maliyet · tek kez</span></div>
    </div>
    <p className="joint-budget">{state === "within"
      ? <>Önceki tek profil hesabının <b>{fmt(report.originalTransitBudgetTRY / 1e9, 3)} mr ₺/yıl</b> tavanının
          {" "}<b>%{fmt(report.budgetSlackTRY / report.originalTransitBudgetTRY * 100, 2)}</b> altında.
          Pay küçük; bu tavan gerçek bir kamu bütçesi değil, model karşılaştırmasıdır.</>
      : <>Hedefleri sağlayan bu plan önceki <b>{fmt(report.originalTransitBudgetTRY / 1e9, 3)} mr ₺/yıl</b> maliyet tavanını aşıyor.
          Tavanın altında başka bir çözüm bulunamayacağı sonucu çıkarılamaz.</>}
    </p>
    <div className="table-scroll"><table className="capacity-table joint-table">
      <caption>Aynı tesisler, ayrı atamalar · 45 dakika sınırı · süreler atanan taleple ağırlıklı</caption>
      <thead><tr><th>Başlangıç</th><th>İl kapsamı</th><th>En düşük ilçe</th><th>Ortalama süre</th></tr></thead>
      <tbody>{report.profiles.map(row => <tr key={row.profile}><td>{transitProfileLabels[row.profile]}</td>
        <td>%{fmt(row.coveragePercent, 2)}</td><td>%{fmt(row.minimumDistrictCoveragePercent, 2)}</td>
        <td>{fmt(row.meanMinutes, 2)} dk</td></tr>)}</tbody>
    </table></div>
    <p className="joint-note">Bu sayı minimum hastane ihtiyacı değildir. 91 hastanenin yeterliliğini veya gerçek EGO hizmetini kanıtlamaz.
      Yıllık talep dört kez toplanmaz. Ulaşım süresi bir sınırdır; bu aramada ayrıca en aza indirilmedi.</p>
    {map}
    <details className="joint-details"><summary>Aynı kişiler mi kapsanıyor? <ChevronDown size={16} /></summary>
      <p>Her profilde %95 hedefi ayrı sağlanıyor. Mahalle içindeki kişi kimlikleri izlenmediğinden aynı %95 kişinin dört profilde de
        hizmet aldığı söylenemez. Kayıtlı atamaların aynı mahalle nüfusundan alt kümeler olduğu varsayılırsa ortak bölüm
        koşullu olarak %{fmt(overlap.lowerPercent, 2)}–%{fmt(overlap.upperPercent, 2)} arasında kalır. Üst uç bir garanti değildir.</p>
      <p>Payda Ankara'nın tüm nüfusudur; konumu bilinmeyen nüfus paydadan çıkarılmadı.
        Dört başlangıç saati, günün her saati için garanti vermez. Eksik hat ve durak kanıtı gerçek hayatta hizmet yok demek değildir.</p>
    </details>
    <p className="joint-note">Kayıtlı deney canlı ayarlarla değişmez. Hekim verimliliği, hasta talebi, işletme giderleri ve ara durak süreleri
      kısmi kalibrasyon içerir. Maliyetler Aralık 2024 TL; arsa, tıbbi cihaz ve dış altyapı yatırımı hariç.</p>
    <a className="text-link" href="https://github.com/ahmedberatAI/Ankara-Hastane-Yerlestirme/blob/main/docs/joint-plan.md" target="_blank" rel="noreferrer">Hesap, kanıt ve yeniden çalıştırma <ExternalLink size={14} /></a>
  </section>;
}

export default function JointPlan({ data }: { data: Dataset }) {
  const [showMap, setShowMap] = useState(false);
  const report = saved as unknown as JointPlanReport;
  return <JointPlanContent report={report} packageId={data.metadata.transitPackageId} planningVersion={data.healthPlanning.version} current={data}
    map={<div className="joint-map-area"><button className="joint-map-toggle" onClick={() => setShowMap(!showMap)} aria-expanded={showMap}>
      <MapPin size={18} /> {showMap ? "Ortak plan haritasını kapat" : "Ortak konumları haritada incele"}</button>
      {showMap && <Suspense fallback={<p>Ortak plan haritası yükleniyor…</p>}><JointPlanMap data={data} sites={report.selected} /></Suspense>}
    </div>} />;
}
