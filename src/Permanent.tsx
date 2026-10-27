import { CarFront, TrainFront, Info, ArrowUpRight } from "lucide-react";
import { transitProfileLabels } from "./types";
import type { Dataset, PlanningPolicy, PermanentPlan, PermanentProfile, PermanentRoute, Result, TravelMode } from "./types";

export const permanentProfiles: PermanentProfile[] = ["car", "weekday-0800", "weekday-1000", "saturday-1000", "sunday-1000"];
const fixed = { threshold: 30, transitThreshold: 60, coverageTarget: 95, districtFloor: 80,
  trafficFactor: 1, demandMultiplier: 1, bedOccupancy: 80, contactsPerDoctor: 2140,
  costTolerance: 10, hospitalLimit: null, operatingCostMultiplier: 1, carWeight: 70 };
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const text = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0;
const near = (a: unknown, b: number, tolerance = 1e-6) => finite(a) && Math.abs(a - b) <= tolerance;
const record = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === "object" && !Array.isArray(value);
const keysAre = (value: unknown, keys: string[]) => record(value) && Object.keys(value).sort().join("|") === [...keys].sort().join("|");
export function stableValue(value: unknown): string {
  if (typeof value === "number" && !Number.isFinite(value)) throw Error("Nonfinite JSON");
  if (Array.isArray(value)) return `[${value.map(stableValue).join(",")}]`;
  if (record(value)) return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${stableValue(value[key])}`).join(",")}}`;
  return JSON.stringify(value);
}
const same = (a: unknown, b: unknown) => stableValue(a) === stableValue(b);
const safeUrl = (value: unknown) => {
  if (!text(value)) return false;
  try { return new URL(value).protocol === "https:"; } catch { return false; }
};
const packageId = (value: unknown) => typeof value === "string" && /^motis-[a-f0-9]{64}$/.test(value);
function fail(message: string): never { throw Error(message); }
export const formatNumber = (n: number) => n.toLocaleString("tr-TR", { maximumFractionDigits: 0 });
export const formatDecimal = (n: number, digits = 1) => n.toLocaleString("tr-TR", { minimumFractionDigits: digits, maximumFractionDigits: digits });

export function policyProblem(value: unknown): string | null {
  try {
    if (!record(value) || value.id !== "ankara-permanent-v1" || value.version !== 1 ||
      value.classification !== "literature_informed_planning_policy" || value.clinicalStandard !== false || value.transitEngine !== "motis") fail("Planlama politikasının sürümü veya kapsamı uyuşmuyor.");
    for (const [key, expected] of Object.entries(fixed)) if (value[key] !== expected)
      fail("Sabit planlama hedefleri bu sürümle eşleşmiyor.");
    if (!same(value.profileIds, permanentProfiles) || !keysAre(value.profileDetails, permanentProfiles) ||
      !keysAre(value.profileWeights, permanentProfiles)) fail("Politikanın beş kesiti eksik.");
    const details = value.profileDetails as PlanningPolicy["profileDetails"];
    const weights = value.profileWeights as PlanningPolicy["profileWeights"];
    for (const id of permanentProfiles) {
      const p = details[id];
      if (!p || p.id !== id || !text(p.label) || p.mode !== (id === "car" ? "car" : "transit") ||
        !near(weights[id], id === "car" ? .7 : .075, 1e-12)) fail("Politika kesit kimliği veya ağırlığı tutarsız.");
      if (id === "car" ? p.departure !== null : !text(p.departure) || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00\+03:00$/.test(p.departure) || !Number.isFinite(Date.parse(p.departure))) fail("Politika tarih bilgisi geçersiz.");
    }
    if (!Array.isArray(value.sources) || !value.sources.length || value.sources.some(source =>
      !record(source) || !text(source.id) || !text(source.title) || !safeUrl(source.url)) ||
      new Set(value.sources.map(source => source.id)).size !== value.sources.length)
      fail("Politikanın kaynak kaydı doğrulanamadı.");
    return null;
  } catch (error) { return error instanceof Error ? error.message : "Planlama politikası doğrulanamadı."; }
}

/** Display gate only. Independent backend audits remain responsible for matrix/cost certificates. */
export function permanentPlanProblem(value: unknown, data: Dataset, policy: PlanningPolicy): string | null {
  try {
    const problem = policyProblem(policy); if (problem) fail(problem);
    if (!record(value) || value.artifactType !== "permanent-hospital-plan" || !text(value.planId) ||
        !/^permanent-[a-f0-9]{64}$/.test(value.planId)) fail("Kayıtlı planın kimliği doğrulanamadı.");
    const plan = value as unknown as PermanentPlan;
    if (!["feasible", "optimal"].includes(plan.status)) fail(plan.reason || "Bu kaynaklarla doğrulanmış kalıcı plan henüz hazır değil.");
    if (!same(plan.policy, policy)) fail("Plan ve güncel sabit politika farklı sürümlere ait.");
    if (plan.planningVersion !== data.healthPlanning.version) fail("Planın sağlık verisi sürümü güncel veriyle eşleşmiyor.");
    if (!record(plan.scenario) || plan.scenario.mode !== "hybrid" || plan.scenario.transitEngine !== "motis") fail("Planın ulaşım kapsamı uyuşmuyor.");
    for (const [key, expected] of Object.entries(fixed))
      if ((plan.scenario as unknown as Record<string, unknown>)[key] !== expected) fail("Plan sabit hedefleri korumuyor.");
    if (!data.demands?.length || !data.candidates?.length || !data.districts?.length ||
      !finite(data.metadata.provincePopulation) || data.metadata.provincePopulation <= 0 ||
      !near(data.districts.reduce((sum, d) => sum + d.population, 0), data.metadata.provincePopulation, .01))
      fail("Nüfus paydaları doğrulanamadı.");
    const meta = plan.metadata;
    for (const key of ["provincePopulation", "matchedPopulation", "unlocatedPopulation", "candidateCount"] as const)
      if (meta?.[key] !== data.metadata[key]) fail("Planın nüfus veya aday kaynağı güncel veriyle eşleşmiyor.");
    if (!keysAre(plan.profiles, permanentProfiles) || !keysAre(plan.modalResults, ["car", "transit"])) fail("Beş ulaşım kesitinin tamamı bulunamadı.");
    const evidence = plan.transitEvidence;
    if (!evidence || evidence.engine !== "motis" || !packageId(evidence.packageId) || !text(evidence.scope) ||
      !keysAre(evidence.profileDates, permanentProfiles.slice(1))) fail("MOTIS kaynak ve tarih kimliği eksik.");
    for (const id of permanentProfiles.slice(1)) {
      const date = evidence.profileDates[id as keyof typeof evidence.profileDates];
      if (date !== policy.profileDetails[id].departure) fail("Ulaşım kesitinin tarihi politikayla uyuşmuyor.");
    }
    if (!Array.isArray(plan.selected) || !plan.selected.length || plan.hospitalCount !== plan.selected.length || !plan.capacity)
      fail("Ortak hastane ve kapasite kaydı eksik.");
    const selected = new Map<string, number>(); let beds = 0; let doctors = 0;
    const byId = new Map(data.candidates.map((c, i) => [c.id, { c, i }]));
    for (const site of plan.selected) {
      const original = byId.get(site.id);
      if (!original || selected.has(site.id) || !Number.isInteger(site.beds) || site.beds! <= 0 ||
        !Number.isInteger(site.doctors) || site.doctors! <= 0 || !near(site.lon, original.c.lon, 1e-9) ||
        !near(site.lat, original.c.lat, 1e-9) || site.districtId !== original.c.districtId ||
        site.footprintRadiusMeters !== original.c.footprintRadiusMeters) fail("Hastane konum veya kaynak kimliği uyuşmuyor.");
      selected.set(site.id, original.i); beds += site.beds!; doctors += site.doctors!;
    }
    if (plan.capacity.totalBeds !== beds || plan.capacity.totalDoctors !== doctors ||
      !finite(plan.capacity.annualEquivalentCostTRY) || plan.capacity.annualEquivalentCostTRY <= 0)
      fail("Ortak yatak, hekim veya yıllık maliyet toplamı tutarsız.");
    const expectedDemands = new Map(data.demands.map(d => [d.id, d]));
    const expectedDistricts = new Map(data.districts.map(d => [d.id, d]));
    if (expectedDemands.size !== data.demands.length || expectedDistricts.size !== data.districts.length) fail("Tekil nüfus kimliği gerekli.");
    const summaries: { id: PermanentProfile; mean: number; coverage: number; minimum: number }[] = [];
    for (const id of permanentProfiles) {
      const profile = plan.profiles[id], limit = id === "car" ? policy.threshold : policy.transitThreshold;
      if (!profile || !same(profile.profile, policy.profileDetails[id]) || !Array.isArray(profile.assignments) || profile.assignments.length !== data.demands.length ||
        !Array.isArray(profile.districts) || profile.districts.length !== data.districts.length || !profile.metrics)
        fail("Kesitlerin mahalle veya ilçe kayıtları eksik.");
      const seen = new Set<string>(), totals = new Map<string, number>(); let served = 0, personMinutes = 0;
      const travel: { minutes: number; population: number }[] = [];
      for (const a of profile.assignments) {
        const demand = expectedDemands.get(a.demandId);
        if (!demand || seen.has(a.demandId) || !Array.isArray(a.allocations) || !finite(a.servedFraction) ||
          a.servedFraction < 0 || a.servedFraction > 1 + 1e-8 || typeof a.covered !== "boolean") fail("Mahalle ataması geçersiz.");
        seen.add(a.demandId); let load = 0; const destinations = new Set<string>();
        for (const allocation of a.allocations) {
          if (!selected.has(allocation.candidateId) || selected.get(allocation.candidateId) !== allocation.candidateIndex ||
            destinations.has(allocation.candidateId) || !finite(allocation.population) || allocation.population <= 0 ||
            !finite(allocation.minutes) || allocation.minutes < 0 || allocation.minutes > limit + 1e-6 ||
            !near(allocation.fraction, allocation.population / demand.population, 1e-7)) fail("Süre veya ortak hastane ataması tutarsız.");
          destinations.add(allocation.candidateId); load += allocation.population;
          personMinutes += allocation.population * allocation.minutes;
          travel.push({ minutes: allocation.minutes, population: allocation.population });
        }
        if (load > demand.population + .01 || !near(a.servedFraction, load / demand.population, 1e-7) ||
          a.covered !== (load >= demand.population - 1e-4)) fail("Mahalle talep payı tutarsız.");
        if (load > 0) {
          const principal = a.allocations.find(x => x.candidateId === a.candidateId);
          if (!principal || a.candidateIndex !== principal.candidateIndex || !near(a.minutes, principal.minutes, 1e-6)) fail("Gösterilen ana atama gerçek akışla uyuşmuyor.");
        } else if (a.candidateId !== null || a.candidateIndex !== null || a.minutes !== null) fail("Atanmayan mahalleye rota eklenmiş.");
        served += load; totals.set(demand.districtId, (totals.get(demand.districtId) || 0) + load);
      }
      const coverage = 100 * served / data.metadata.provincePopulation;
      if (coverage < policy.coverageTarget - 1e-6 || !near(profile.metrics.coveredPopulation, served, .05) ||
        !near(profile.metrics.coveragePercent, coverage) || !near(profile.metrics.meanMinutes, personMinutes / served) ||
        !near(profile.metrics.unreachableOrUnlocatedPopulation, data.metadata.provincePopulation - served, .05))
        fail("İl kapsamı veya ortalama yolculuk atamalarla uyuşmuyor.");
      travel.sort((a, b) => a.minutes - b.minutes);
      let cumulative = 0, p90 = travel.at(-1)?.minutes;
      for (const row of travel) { cumulative += row.population; if (cumulative >= .9 * data.metadata.provincePopulation) { p90 = row.minutes; break; } }
      if (p90 === undefined || !near(profile.metrics.p90Minutes, p90, 1e-5)) fail("Yüzdelik yolculuk süresi atamalarla uyuşmuyor.");
      const districtsSeen = new Set<string>(); let minimum = 100;
      for (const d of profile.districts) {
        const original = expectedDistricts.get(d.id), covered = totals.get(d.id) || 0;
        if (!original || districtsSeen.has(d.id) || d.population !== original.population ||
          !near(d.coveredPopulation, covered, .05) || !near(d.coveragePercent, covered / d.population * 100) ||
          d.coveragePercent! < policy.districtFloor - 1e-6) fail("İlçe kapsamı veya nüfus paydası tutarsız.");
        districtsSeen.add(d.id); minimum = Math.min(minimum, d.coveragePercent!);
      }
      if (id !== "car" && (!profile.transitEvidence || profile.transitEvidence.packageId !== evidence.packageId || profile.transitEvidence.engine !== "motis" ||
        profile.transitEvidence.profile !== id || profile.transitEvidence.departure !== policy.profileDetails[id].departure))
        fail("Kesitler farklı ulaşım kaynaklarına ait.");
      summaries.push({ id, mean: personMinutes / served, coverage, minimum });
    }
    const summary = plan.permanentSummary;
    if (!summary || summary.profileCount !== 5 || summary.transitProfileCount !== 4 || summary.annualDemandCountedOnce !== true ||
      summary.sameIndividualsAcrossProfilesConstrained !== false || !keysAre(summary.profileWeights, permanentProfiles) ||
      !keysAre(summary.thresholds, permanentProfiles) || permanentProfiles.some(id => summary.thresholds?.[id] !== (id === "car" ? 30 : 60)))
      fail("Beş kesitli ortak planın özeti doğrulanamadı.");
    for (const id of permanentProfiles) if (!near(summary.profileWeights[id], id === "car" ? .7 : .075, 1e-12))
      fail("Yolculuk önceliği ağırlıkları sabit politikayla uyuşmuyor.");
    const transit = summaries.slice(1), critical = [...transit].sort((a, b) => b.mean - a.mean || a.id.localeCompare(b.id))[0];
    if (plan.criticalTransitProfile !== critical.id || summary.criticalTransitProfile !== critical.id || plan.scenario.transitProfile !== critical.id ||
      !same(plan.modalResults!.car, plan.profiles.car) || !same(plan.modalResults!.transit, plan.profiles[critical.id]))
      fail("Gösterilen toplu taşıma kesiti en yüksek ortalamalı kayıtla uyuşmuyor.");
    if (!same(plan.metrics, plan.profiles.car.metrics) || !same(plan.assignments, plan.profiles.car.assignments) || !same(plan.districts, plan.profiles.car.districts))
      fail("Ana sonuç ve kayıtlı araba kesiti tutarsız.");
    if (!near(summary.weightedMeanMinutes, summaries.reduce((n, p) => n + p.mean * summary.profileWeights[p.id], 0)) ||
      !near(summary.meanTransitMinutes, transit.reduce((n, p) => n + p.mean, 0) / 4) || !near(summary.worstTransitMeanMinutes, critical.mean) ||
      !near(summary.minimumProvinceCoveragePercent, Math.min(...summaries.map(p => p.coverage))) ||
      !near(summary.minimumDistrictCoveragePercent, Math.min(...summaries.map(p => p.minimum)))) fail("Özet göstergeler beş kesitle uyuşmuyor.");
    return null;
  } catch (error) { return error instanceof Error ? error.message : "Kayıtlı kalıcı plan doğrulanamadı."; }
}

export function permanentResultForView(plan: PermanentPlan, view: TravelMode): Result {
  const result = plan.profiles[view === "car" ? "car" : plan.criticalTransitProfile];
  return { ...plan, ...result, selected: plan.selected, capacity: plan.capacity };
}
export function permanentRouteRequest(plan: PermanentPlan, view: TravelMode, demandId: string, candidateId: string) {
  const result = plan.profiles[view === "car" ? "car" : plan.criticalTransitProfile];
  if (!result.assignments.some(a => a.demandId === demandId && a.allocations.some(x => x.candidateId === candidateId)))
    throw Error("Bu mahalle–hastane bağlantısı kayıtlı görünümde atanmadı.");
  return { planId: plan.planId, view, demandId, candidateId };
}
export function permanentRouteProblem(route: unknown, plan: PermanentPlan, view: TravelMode, demandId: string, candidateId: string): string | null {
  try {
    permanentRouteRequest(plan, view, demandId, candidateId);
    if (!record(route)) fail("Rota yanıtı eksik.");
    const r = route as unknown as PermanentRoute;
    const profileId = view === "car" ? "car" : plan.criticalTransitProfile;
    if (r.planId !== plan.planId || r.profileId !== profileId || r.routeMode !== view ||
      r.scenario?.demandId !== demandId || r.scenario?.candidateId !== candidateId) fail("Rota farklı plan veya mahalleye ait.");
    if (r.scenario?.mode !== "hybrid" || r.scenario.transitEngine !== "motis" || r.scenario.transitProfile !== plan.criticalTransitProfile ||
      Object.entries(fixed).some(([key, value]) => (r.scenario as unknown as Record<string, unknown>)[key] !== value))
      fail("Rota sabit planlama politikasıyla uyuşmuyor.");
    if (!finite(r.minutes) || r.minutes < 0 || !text(r.note) || !text(r.demand) || !text(r.candidate) ||
      !Array.isArray(r.legs) || !Array.isArray(r.boardings)) fail("Rota biçimi doğrulanamadı.");
    const allocation = plan.profiles[profileId].assignments.find(a => a.demandId === demandId)!.allocations.find(a => a.candidateId === candidateId)!;
    if (!near(r.minutes, allocation.minutes, .05)) fail("Rota süresi kayıtlı plan atamasıyla uyuşmuyor.");
    if (r.legs.some(leg => !text(leg.kind) || !text(leg.label) || !Array.isArray(leg.coordinates) || leg.coordinates.some(c =>
      !Array.isArray(c) || c.length !== 2 || !finite(c[0]) || !finite(c[1]) || Math.abs(c[0]) > 180 || Math.abs(c[1]) > 90))) fail("Rota geometrisi geçersiz.");
    if (r.boardings.some(b => !text(b.route) || !text(b.stop) || !text(b.mode) ||
      (b.departureTime !== undefined && !text(b.departureTime)) || (b.waitMinutes !== undefined && (!finite(b.waitMinutes) || b.waitMinutes < 0))))
      fail("Rota biniş kaydı doğrulanamadı.");
    if (view === "transit" && (!packageId(plan.transitEvidence.packageId) || r.evidence?.packageId !== plan.transitEvidence.packageId ||
      r.scenario?.routingPackageId !== plan.transitEvidence.packageId || r.scenario?.transitProfile !== profileId || r.scenario?.transitEngine !== "motis"))
      fail("Rota, planın MOTIS kaynak paketiyle eşleşmiyor.");
    return null;
  } catch (error) { return error instanceof Error ? error.message : "Rota doğrulanamadı."; }
}

export function profileLabel(plan: PermanentPlan, id: PermanentProfile) {
  if (id === "car") return "Araba · sabit yol ağı";
  const date = plan.transitEvidence.profileDates[id];
  return `${transitProfileLabels[id]} · ${new Date(date).toLocaleDateString("tr-TR", { day: "numeric", month: "long", year: "numeric", timeZone: "Europe/Istanbul" })}`;
}

export function PermanentTargets({ policy }: { policy: PlanningPolicy }) {
  return <section className="permanent-targets" aria-label="Sabit planlama hedefleri">
    <span className="eyebrow">PLANIN SABİT KOŞULLARI</span>
    <dl><div><dt>Araba</dt><dd>{policy.threshold} <small>dk</small></dd></div><div><dt>Toplu taşıma</dt><dd>{policy.transitThreshold} <small>dk</small></dd></div>
      <div><dt>İl genelinde talep</dt><dd>%{policy.coverageTarget}</dd></div><div><dt>Her ilçede en az</dt><dd>%{policy.districtFloor}</dd></div></dl>
    <p>Literatürden yararlanan planlama tercihleri. Resmî veya klinik standart değildir; ilçe tabanı kırsal erişimi koruyan proje koşuludur.</p>
  </section>;
}
export function PermanentViews({ plan, view, onView }: { plan: PermanentPlan; view: TravelMode; onView: (v: TravelMode) => void }) {
  return <section className="permanent-views" aria-label="Aynı hastanelerin erişim görünümü">
    <div className="hybrid-view-tabs" role="group" aria-label="Harita görünümü">{(["car", "transit"] as const).map(mode => <button key={mode} type="button" aria-pressed={view === mode} className={view === mode ? "selected" : ""} onClick={() => onView(mode)}>
      {mode === "car" ? <CarFront size={19} /> : <TrainFront size={19} />}<span><b>{mode === "car" ? "Araba" : "Toplu taşıma"}</b><small>Ortak hastaneler · {mode === "car" ? plan.policy.threshold : plan.policy.transitThreshold} dk</small></span></button>)}</div>
    <p>{view === "car" ? "Hastaneler, yataklar ve hekimler iki görünümde de aynıdır." : `Gösterilen kesit: ${profileLabel(plan, plan.criticalTransitProfile)}. Dört toplu taşıma kesitinin ortalaması en yüksek olanı; bütün günün en kötü durumu değil.`}</p>
  </section>;
}
export function PermanentEvidence({ plan }: { plan: PermanentPlan }) {
  return <details className="permanent-evidence"><summary><Info size={14} /> Bir araba + dört tarihli toplu taşıma kesiti · kaynak ve sınırlar</summary>
    <p>Konumlar ve kapasite birlikte planlandı. Her kesitte tam yıllık talep temel alınır, aynı yıllık maliyet bir kez hesaplanır. Araba önceliği %70, dört toplu taşıma kesitinin toplamı %30'dur; bu yalnız yolculuk amacının ağırlığıdır, hasta veya ambulans kullanım oranı değildir.</p>
    <div className="table-wrap"><table><caption>Aynı kaynaklarla ayrı sınanan beş kesit</caption><thead><tr><th>Kesit</th><th>İl kapsamı</th><th>En düşük ilçe</th><th>Ortalama</th></tr></thead><tbody>{permanentProfiles.map(id => <tr key={id}><td>{profileLabel(plan, id)}</td><td>%{formatDecimal(plan.profiles[id].metrics.coveragePercent)}</td><td>%{formatDecimal(Math.min(...plan.profiles[id].districts.map(d => d.coveragePercent!)))}</td><td>{formatDecimal(plan.profiles[id].metrics.meanMinutes!)} dk</td></tr>)}</tbody></table></div>
    <p>MOTIS, tarihsel topluluk GTFS verisi ve OSM yaya ağıyla çalışır. Araç geometrisi GTFS shapes kaynağına ait olabilir. Güncel resmî EGO tarifesi, canlı trafik, bütün saatlerde hizmet veya gerçek ambulans hızı doğrulanmış değildir. Eksik bağlantı gerçek hizmet yokluğu anlamına gelmez.</p>
    <p>Kapsam nüfus eşdeğeri talep atamasıdır; beş kesitte aynı bireylerin hizmet aldığı zorunlu değildir. Maliyet ve hekim verimi klinik doğrulama bekleyen model varsayımlarıdır. Seçilen hastane sayısı kanıtlanmış asgari ihtiyaç değildir.</p>
    <PermanentCalculation plan={plan} />
    <p>{plan.transitEvidence.scope}</p><p>Plan: <code>{plan.planId}</code><br />Ulaşım paketi: <code>{plan.transitEvidence.packageId}</code></p>
  </details>;
}
export function PermanentCalculation({ plan }: { plan: PermanentPlan }) {
  const c = plan.capacity;
  const money = (value: unknown) => finite(value) && value >= 0 ? `${formatDecimal(value / 1e9, 2)} milyar ₺/yıl` : "Kayıtta bildirilmedi";
  const gap = (value: unknown) => finite(value) && value >= 0 ? `%${formatDecimal(value * 100, 2)}` : "Geçerli alt sınır bildirilmedi";
  const nativeStatus = (performed: unknown, limited: unknown) => performed === false ? "Bu aşama çalıştırılmadı" : limited === true ? "Süre sınırında sonlandı" : limited === false ? "Süre sınırı bildirilmedi; bu tek başına optimum kanıtı değildir" : "Çözücü durumu bildirilmedi";
  const annuityReady = finite(c?.horizonYears) && c.horizonYears > 0 && finite(c.realDiscountRate) && c.realDiscountRate >= 0;
  return <details className="permanent-calculation"><summary>Kapasite, yıllık maliyet ve çözümün kanıt sınırı</summary>
    <p><b>İki ayrı kapasite koşulu.</b> Yıllık yatış-gün talebi, yatak × 365 × %{plan.policy.bedOccupancy} doluluk kapasitesini aşamaz. Bir yatak böylece yılda {formatNumber(365 * plan.policy.bedOccupancy / 100)} yatış-gün kapasitesi sağlar. Başvuru + yatış temas talebi de hekim × {formatNumber(plan.policy.contactsPerDoctor)} yıllık temas kapasitesini aşamaz. Her hastanenin kaynakları beş kesitte ayrı ayrı yeterli olmalıdır; kesit yükleri toplanmaz.</p>
    <p>{formatNumber(plan.policy.contactsPerDoctor)} temas/hekim, özel hastane portföyündeki yıllık temas ve yıl sonu hekim sayısından aktarılan yaklaşık verim varsayımıdır. Klinik FTE, branş kadrosu veya kamu hekimlerinin ölçülmüş yıllık çalışma kapasitesi değildir. %{plan.policy.bedOccupancy} doluluk da bu planın sabit varsayımıdır.</p>
    <p><b>Tek yıllık maliyet.</b> Tesislerin sabit işletme gideri + yatak destek gideri + hekim gideri + karşılanan başvuru/yatış temaslarına bağlı malzeme gideri + yıllıklaştırılmış yapım maliyeti. Aynı talebin malzeme bedeli beş kesit için yalnız bir kez yazılır; hastanelerin kesitler arasındaki azami yükleri maliyet amacıyla toplanmaz.</p>
    <p>{annuityReady ? <>Yapım yatırımı {formatNumber(c!.horizonYears!)} yıl ve %{formatDecimal(c!.realDiscountRate! * 100, 0)} reel iskonto oranıyla yıllıklaştırılır. Çarpan r / [1 − (1 + r)<sup>−n</sup>] formülüdür; r = 0 ise 1/n kullanılır.</> : "Yıllıklaştırma vadesi ve iskonto oranı bu kayıtta bildirilmedi."} {c?.priceBase ? `Fiyat temeli: ${c.priceBase}.` : ""} Arsa, tıbbi cihaz ve dış altyapı gibi dışarıda kalan kalemler vardır; kamu hastanesinin tam bütçesi değildir.</p>
    <dl><div><dt>Maliyet aşamasındaki referans</dt><dd>{money(c?.referenceCostTRY)}</dd></div><div><dt>Ortak süre aşaması bütçe tavanı</dt><dd>{money(c?.budgetLimitTRY)}</dd></div><div><dt>Son ortak plan</dt><dd>{money(c?.annualEquivalentCostTRY)}</dd></div></dl>
    <p>Bütçe tavanı, bulunan geçerli maliyet referansının %{plan.policy.costTolerance} üzerindedir. Referansın küresel en düşük maliyet olduğu kanıtlanmış sayılmaz. Bu sınır içinde araba %70 ve dört toplu taşıma kesiti toplam %30 ağırlıkla daha kısa erişim aranır.</p>
    <dl><div><dt>Referans maliyet açığı</dt><dd>{gap(c?.costStageGap)}</dd></div><div><dt>Son plan maliyet açığı</dt><dd>{gap(c?.finalPlanCostGap)}</dd></div><div><dt>Ağırlıklı süre aşaması açığı</dt><dd>{gap(c?.travelStageGap)}</dd></div></dl>
    <p>Maliyet aşaması: {nativeStatus(plan.solver?.costStagePerformed, plan.solver?.costTimeLimit)}. Süre aşaması: {nativeStatus(plan.solver?.travelStagePerformed, plan.solver?.travelTimeLimit)}.</p>
    <p>Açıklar, çözücünün bildirdiği alt sınırlara ve kullanılan aday/bağlantı kümesine aittir; bağımsız küresel optimum sertifikası değildir. {plan.searchScope?.restricted === true ? "Optimizasyonda bağlantı kümesi daraltılmıştır. " : ""}{finite(plan.searchScope?.retainedCandidateCount) && finite(plan.searchScope?.allCandidateCount) ? `${formatNumber(plan.searchScope.retainedCandidateCount)} / ${formatNumber(plan.searchScope.allCandidateCount)} aday aramada tutulmuştur. ` : ""}MOTIS'in sorgulanmamış bağlantıları ve tarihsel tarife sınırları da geçerlidir. Maliyet ve süre açıkları farklı amaçları ölçer; hiçbiri en az hastane sayısının veya gerçek dünyada bütün hizmetin kanıtı değildir.</p>
  </details>;
}
export function PolicySources({ policy }: { policy: PlanningPolicy }) {
  return <div className="permanent-sources"><p>30 / 60 dakika ile %95 / %80 hedefleri, bu sürüm için seçilmiş sabit planlama politikasıdır. Tek bir evrensel hastane standardı olarak sunulmaz.</p>
    {policy.sources.map(source => <article key={source.id}><a href={source.url} target="_blank" rel="noreferrer">{source.title} <ArrowUpRight size={14} /></a><p>{source.locator}{source.role ? ` · ${source.role}` : source.note}</p></article>)}
    <a href="https://github.com/ahmedberatAI/Ankara-Hastane-Yerlestirme/blob/main/docs/planning-standards.md" target="_blank" rel="noreferrer">Hedeflerin gerekçesini ve kapsamını oku <ArrowUpRight size={14} /></a>
  </div>;
}
