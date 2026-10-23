import { lazy, Suspense, useState } from "react";
import { Clock3, MapPin, ChevronDown, ExternalLink } from "lucide-react";
import saved from "../data/processed/window-plan-summary.json";
import manifest from "../data/processed/manifest.json";
import { scenario as sourceScenario, sourceSHA256 as sourceCostHashes,
  transitPackageId as sourcePackageId, planningVersion as sourcePlanningVersion } from "../data/processed/joint-plan-summary.json";
import type { Dataset } from "./types";
import type { JointPlanReport, JointSite } from "./JointPlan";
import "./joint-plan.css";
const PlanMap = lazy(() => import("./JointPlanMap"));
const fmt = (n: number, digits = 1) => n.toLocaleString("tr-TR", { maximumFractionDigits: digits });
const definitions = [0, -5, 5, -4, -3, -2, -1, 1, 2, 3, 4].flatMap(offset =>
  [["weekday", 480], ["weekday", 600], ["saturday", 600], ["sunday", 600]].map(([day, start]) => {
    const minute = Number(start) + offset;
    return `${day}-${String(Math.floor(minute / 60)).padStart(2, "0")}${String(minute % 60).padStart(2, "0")}`;
  }));
const label = (id: string) => {
  const [day, time] = id.split("-");
  return `${day === "weekday" ? "Hafta içi" : day === "saturday" ? "Cumartesi" : "Pazar"} ${time.slice(0, 2)}.${time.slice(2)}`;
};
export type WindowReport = {
  status: string; transitPackageId: string; planningVersion: string;
  sourceSHA256: Record<string, string>; certificateSHA256: string; profileManifestSHA256: string;
  scenario: JointPlanReport["scenario"]; profileCount: number;
  allProfilesValidated: boolean; resourcesSharedAcrossProfiles: boolean; annualDemandCountedOnce: boolean;
  sameIndividualsAcrossProfilesConstrained: boolean; minimumHospitalCountProven: boolean; globalOptimalityProven: boolean;
  hospitalCount: number; beds: number; doctors: number; selected: JointSite[];
  annualEquivalentCostTRY: number; hardBudgetTRY: number; withinHardBudget: boolean; budgetSlackTRY: number;
  sourceAnnualEquivalentCostTRY: number; sourceCostDeltaTRY: number; sourceHospitalCount: number;
  candidatePoolSize: number; fullCandidateCount: number; optimizedProfileIds: string[]; validatedProfileIds: string[];
  provincePopulation: number;
  profiles: (Omit<JointPlanReport["profiles"][number], "profile"> & { profile: string; coveredPopulation: number })[];
};
type Identity = { file: string; sha256: string };
export function windowPlanState(report: WindowReport, data: Dataset, identities: Identity[]) {
  const obj = (v: unknown) => v !== null && typeof v === "object" && !Array.isArray(v);
  const near = (a: number, b: number, tolerance = 1e-6) => Number.isFinite(a) && Number.isFinite(b) && Math.abs(a - b) <= tolerance;
  const positive = (n: number) => Number.isInteger(n) && n > 0;
  if (!obj(report) || !obj(report.scenario) || !obj(report.sourceSHA256) || !Array.isArray(report.selected) ||
    !Array.isArray(report.profiles) || !Array.isArray(report.optimizedProfileIds) || !Array.isArray(report.validatedProfileIds) ||
    report.selected.some(s => !obj(s)) || report.profiles.some(p => !obj(p) || !Array.isArray(p.districts) || p.districts.some(d => !obj(d)))) return "invalid";
  const hashes = new Map(identities.map(i => [i.file, i.sha256]));
  const sourceNames = ["dataset.json", "health-planning.json", "example-transit-result.json", "transit-package.json", "joint-plan.json",
    ...["weekday-0800", "weekday-1000", "saturday-1000", "sunday-1000"].map(p => `transit-${p}-matrix.npz`)];
  if (report.transitPackageId !== data.metadata.transitPackageId || report.planningVersion !== data.healthPlanning.version ||
    report.transitPackageId !== sourcePackageId || report.planningVersion !== sourcePlanningVersion ||
    sourceNames.some(n => !/^[a-f0-9]{64}$/.test(report.sourceSHA256[n] || "") || hashes.get(`data/processed/${n}`) !== report.sourceSHA256[n]) ||
    Object.entries(sourceCostHashes).some(([name, hash]) => report.sourceSHA256[name] !== hash) ||
    Object.keys(report.scenario).length !== Object.keys(sourceScenario).length ||
    Object.entries(sourceScenario).some(([key, value]) => report.scenario[key as keyof typeof report.scenario] !== value) ||
    !/^[a-f0-9]{64}$/.test(report.certificateSHA256 || "") ||
    hashes.get("data/processed/departure-window-plan/window-plan.json") !== report.certificateSHA256 ||
    !/^[a-f0-9]{64}$/.test(report.profileManifestSHA256 || "") ||
    hashes.get("data/processed/departure-window/manifest.json") !== report.profileManifestSHA256) return "stale";
  if (report.status !== "validated_window_model_plan" || report.profileCount !== 44 || report.allProfilesValidated !== true ||
    report.resourcesSharedAcrossProfiles !== true || report.annualDemandCountedOnce !== true ||
    report.sameIndividualsAcrossProfilesConstrained !== false || report.minimumHospitalCountProven !== false || report.globalOptimalityProven !== false ||
    report.scenario.mode !== "transit" || report.scenario.threshold !== 45 || report.scenario.coverageTarget !== 95 || report.scenario.districtFloor !== 80 ||
    report.scenario.hospitalLimit !== null || report.withinHardBudget !== true || !near(report.hardBudgetTRY, 189556939209.2935, .001) ||
    !near(report.sourceAnnualEquivalentCostTRY, 175868263288.70182, .001) ||
    !Number.isFinite(report.annualEquivalentCostTRY) || report.annualEquivalentCostTRY <= 0 || report.annualEquivalentCostTRY > report.hardBudgetTRY ||
    !near(report.sourceCostDeltaTRY, report.annualEquivalentCostTRY - report.sourceAnnualEquivalentCostTRY, .001) ||
    !near(report.budgetSlackTRY, report.hardBudgetTRY - report.annualEquivalentCostTRY, .001) ||
    ![report.hospitalCount, report.beds, report.doctors, report.candidatePoolSize].every(positive) ||
    report.fullCandidateCount !== data.candidates.length || report.candidatePoolSize > report.fullCandidateCount ||
    report.hospitalCount > report.candidatePoolSize || report.sourceHospitalCount !== 209 ||
    report.selected.length !== report.hospitalCount || new Set(report.selected.map(s => s.candidateIndex)).size !== report.hospitalCount ||
    report.selected.reduce((n, s) => n + s.beds, 0) !== report.beds || report.selected.reduce((n, s) => n + s.doctors, 0) !== report.doctors ||
    report.selected.some(s => !positive(s.beds) || !positive(s.doctors) || !Number.isInteger(s.candidateIndex) || s.candidateIndex < 0 ||
      !Number.isFinite(s.maximumAssignedPopulationAcrossProfiles) || s.maximumAssignedPopulationAcrossProfiles < 0 ||
      !data.candidates[s.candidateIndex] || data.candidates[s.candidateIndex].id !== s.id ||
      data.candidates[s.candidateIndex].lon !== s.lon || data.candidates[s.candidateIndex].lat !== s.lat) ||
    !positive(report.provincePopulation) || report.provincePopulation !== data.metadata.provincePopulation ||
    data.districts.length !== 25 || new Set(data.districts.map(d => d.id)).size !== 25 ||
    data.districts.some(d => !positive(d.population)) ||
    data.districts.reduce((sum, d) => sum + d.population, 0) !== report.provincePopulation ||
    report.optimizedProfileIds.length !== 44 || report.optimizedProfileIds.some((p, i) => p !== definitions[i]) ||
    report.validatedProfileIds.length !== 44 || report.validatedProfileIds.some((p, i) => p !== definitions[i]) ||
    report.profiles.length !== 44 || report.profiles.some((p, i) => p.profile !== definitions[i] ||
      !near(p.coveragePercent, 95) || !Number.isFinite(p.meanMinutes) || p.meanMinutes < 0 ||
      !Number.isFinite(p.maxMinutes) || p.maxMinutes < 0 || p.maxMinutes > 45 || p.meanMinutes > p.maxMinutes + 1e-6 ||
      !near(p.coveredPopulation, report.provincePopulation * .95, .001) ||
      !near(p.coveragePercent, p.coveredPopulation / report.provincePopulation * 100) ||
      p.districts.length !== 25 || new Set(p.districts.map(d => d.id)).size !== 25 ||
      !near(p.districts.reduce((sum, d) => sum + d.coveredPopulation, 0), p.coveredPopulation, .001) ||
      !near(p.minimumDistrictCoveragePercent, Math.min(...p.districts.map(d => d.coveragePercent))) ||
      p.districts.some(d => !Number.isFinite(d.coveragePercent) || d.coveragePercent < 80 - 1e-6 || d.coveragePercent > 100 + 1e-6 ||
        !positive(d.population) || !Number.isFinite(d.coveredPopulation) || d.coveredPopulation < 0 ||
        d.coveredPopulation > d.population + .001 || !near(d.coveragePercent, d.coveredPopulation / d.population * 100) ||
        !data.districts.some(actual => actual.id === d.id && actual.population === d.population)))) return "invalid";
  return "valid";
}

export function WindowPlanContent({ report, data, identities, map }: {
  report: WindowReport; data: Dataset; identities: Identity[]; map?: React.ReactNode;
}) {
  const state = windowPlanState(report, data, identities);
  if (state !== "valid") return <section className="joint-plan window-plan"><p role="status">{state === "stale"
    ? "Yakın saatler planının veri kimliği güncel paketle eşleşmiyor; sonuç gösterilmiyor."
    : "Yakın saatler planının doğrulaması tamamlanmadı; açık kapandı olarak gösterilmiyor."}</p></section>;
  const at0805 = report.profiles.find(p => p.profile === "weekday-0805")!;
  const delta = report.sourceCostDeltaTRY;
  return <section className="joint-plan window-plan" aria-labelledby="window-title">
    <div className="joint-heading"><div><span className="eyebrow">KAYITLI EGO DENEYİ · 44 BAŞLANGIÇ</span>
      <h3 id="window-title"><Clock3 size={25} /> Beş dakika değişince de çalışan plan</h3>
      <p>Konum, yatak ve hekim dağılımı yakın başlangıç saatleri birlikte hesaba katılarak yeniden seçildi.
        Hafta içi 07.55–08.05 ve 09.55–10.05; cumartesi ve pazar 09.55–10.05.
        Birer dakika arayla sınanan 44 başlangıç aynı tesisleri ve kaynakları kullanıyor.</p></div>
      <span className="joint-tag">44 / 44 başlangıç doğrulandı</span></div>
    <div className="joint-metrics"><div><b>{fmt(report.hospitalCount, 0)}</b><span>ortak hastane konumu</span></div>
      <div><b>{fmt(report.beds, 0)}</b><span>yatak</span></div><div><b>{fmt(report.doctors, 0)}</b><span>modelde hekim</span></div>
      <div><b>{fmt(report.annualEquivalentCostTRY / 1e9, 3)} <small>mr TL</small></b><span>yıllık eşdeğer maliyet</span></div></div>
    <p className="joint-travel-targets"><b>08.05 açığı bu modelde kapandı.</b> İl kapsamı %{fmt(at0805.coveragePercent, 0)},
      en düşük ilçe kapsamı %{fmt(at0805.minimumDistrictCoveragePercent, 2)}; ortalama yolculuk {fmt(at0805.meanMinutes, 2)} dk.
      44 başlangıcın her birinde hedefler aynı: ilde %95, her ilçede en az %80, her atamada en çok 45 dakika.</p>
    <div className="joint-budget">Önceki dört başlangıç saatinin planı: <b>{fmt(report.sourceAnnualEquivalentCostTRY / 1e9, 3)} milyar TL/yıl</b>.
      Yeni fark: <b>{delta >= 0 ? "+" : "−"}{fmt(Math.abs(delta) / 1e9, 3)} milyar TL/yıl</b> ({delta >= 0 ? "+" : "−"}{fmt(Math.abs(delta) / report.sourceAnnualEquivalentCostTRY * 100, 2)}%).
      Eski modelin {fmt(report.hardBudgetTRY / 1e9, 3)} milyar TL tavanının {fmt(report.budgetSlackTRY / 1e9, 3)} milyar TL altında.
      Bu tavan gerçek bir kamu bütçesi değildir.</div>
    <p className="joint-note">Bu sonuç yalnız bu 44 kayıtlı başlangıç için geçerlidir; aradaki saniyeler veya günün tamamı için garanti değildir.
      Kayıtlı deney canlı harita ayarlarıyla değişmez. Eksik sefer verileri, tahmini ara durak süreleri, klinik hekim kapasitesi ve kamu maliyetleriyle ilgili sınırlamalar sürüyor.</p>
    {map}
    <details className="joint-details"><summary>Hesap nasıl yapıldı? <ChevronDown size={16} /></summary>
      <p>{fmt(report.fullCandidateCount, 0)} aday için 44 ulaşım matrisi üretildi. Ortak maliyet araması {fmt(report.candidatePoolSize, 0)} konumluk havuzda
        tesis açma/kapatma, yatak modülü ve tam sayı hekim kararlarını birlikte seçti. Sonuç minimum hastane sayısı veya tüm Ankara için küresel optimum kanıtı değildir.</p>
      <p>Her başlangıç için ayrı talep dağılımı var; kaynaklar ortak, yıllık talep ve malzeme gideri bir kez sayılıyor.
        Yatak günü ve hekim temas (başvuru + yatış) kapasitesi ayrı sınırlar. Her saatte aynı kişilerin hizmet aldığını varsaymıyoruz.</p>
      <p>Maliyet; yıllıklaştırılmış bina yatırımını, tesis/yatak/hekim işletme giderlerini ve malzeme giderini içeriyor.
        Yolculuklar kayıtlı hat ve yaya bağlantılarından hesaplanıyor. Binaların varlığı yerleşimi engellemiyor;
        yol üzerinde olmayan adaylar ve tesis alanı/çakışma sınırları korunuyor.</p>
    </details>
    <details className="joint-details"><summary>44 başlangıcın sonuçları <ChevronDown size={16} /></summary>
      <div className="table-scroll"><table className="capacity-table joint-table"><caption>Her satır aynı yatak ve hekim kaynaklarını kullanır</caption>
        <thead><tr><th>Başlangıç</th><th>İl kapsamı</th><th>En düşük ilçe</th><th>Ortalama</th><th>En uzun</th></tr></thead>
        <tbody>{[...report.profiles].sort((a, b) => a.profile.localeCompare(b.profile)).map(p => <tr key={p.profile}>
          <td>{label(p.profile)}</td><td>%{fmt(p.coveragePercent, 0)}</td><td>%{fmt(p.minimumDistrictCoveragePercent, 2)}</td>
          <td>{fmt(p.meanMinutes, 2)} dk</td><td>{fmt(p.maxMinutes, 2)} dk</td></tr>)}</tbody></table></div>
    </details>
    <a className="text-link" href="https://github.com/ahmedberatAI/Ankara-Hastane-Yerlestirme/blob/main/docs/departure-window-plan.md" target="_blank" rel="noreferrer">
      Yöntem, maliyet farkı ve bağımsız denetim <ExternalLink size={14} /></a>
  </section>;
}

export default function WindowPlan({ data }: { data: Dataset }) {
  const [showMap, setShowMap] = useState(false);
  const report = saved as unknown as WindowReport;
  return <WindowPlanContent report={report} data={data} identities={manifest.files} map={<div>
    <button className="joint-map-toggle" aria-expanded={showMap} onClick={() => setShowMap(!showMap)}>
      <MapPin size={18} />{showMap ? "44 başlangıç planının haritasını kapat" : "Yeni ortak konumları haritada incele"}</button>
    {showMap && <Suspense fallback={<p>Yeni plan haritası yükleniyor…</p>}><PlanMap data={data} sites={report.selected} profileCount={44} /></Suspense>}
  </div>} />;
}
