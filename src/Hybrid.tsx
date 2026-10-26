import { CarFront, TrainFront, Info } from "lucide-react";
import { transitProfileLabels } from "./types";
import type { Result, Route, RoutingStatus, Scenario, TransitEngine, TravelMode } from "./types";

const decimal = (n: number | null | undefined) => n == null || !Number.isFinite(n)
  ? "—" : n.toLocaleString("tr-TR", { maximumFractionDigits: 1 });
const close = (a: unknown, b: number, tolerance = 1e-7) => typeof a === "number" && Number.isFinite(a) && Math.abs(a - b) <= tolerance;
export const engineFor = (scenario: Scenario): TransitEngine => scenario.transitEngine ?? "ego";
export const providerLabel = (engine: TransitEngine) => engine === "motis" ? "MOTIS" : "Özgün EGO modeli";
export function departureLabel(value: string): string {
  if (/^\d{2}:\d{2}$/.test(value)) return value;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? date.toLocaleTimeString("tr-TR", { timeZone: "Europe/Istanbul", hour: "2-digit", minute: "2-digit" }) : value;
}
export function profileDateLabel(value: string, dateOnly = false): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return value;
  return date.toLocaleString("tr-TR", { timeZone: "Europe/Istanbul", year: "numeric", month: "long", day: "numeric",
    ...(!dateOnly && value.includes("T") ? { hour: "2-digit", minute: "2-digit" } as const : {}) });
}
export function scenarioKey(s: Scenario): string {
  return JSON.stringify([s.mode, s.threshold, s.coverageTarget, s.districtFloor,
    s.trafficFactor, s.demandMultiplier, s.bedOccupancy, s.contactsPerDoctor,
    s.costTolerance, s.hospitalLimit, s.operatingCostMultiplier, s.transitProfile,
    engineFor(s), s.carWeight ?? 70, s.transitThreshold ?? 45]);
}
export function scenarioLabel(s: Scenario): string {
  if (s.mode === "car") return `Araba · ${s.threshold} dk`;
  const transit = `${providerLabel(engineFor(s))} · ${transitProfileLabels[s.transitProfile]}`;
  return s.mode === "hybrid"
    ? `EGO + Araba · araba ${s.threshold} dk / toplu ulaşım ${s.transitThreshold ?? 45} dk · ${transit}`
    : `${transit} · ${s.threshold} dk`;
}
export function routingAvailability(status: RoutingStatus | null, s: Scenario): { ready: boolean; detail: string } {
  if (s.mode === "car") return { ready: true, detail: "" };
  if (!status) return { ready: false, detail: "Ulaşım sağlayıcısının durumu henüz doğrulanmadı." };
  const provider = status[engineFor(s)];
  if (!provider || provider.ready !== true) return { ready: false, detail: provider?.detail || "Ulaşım sağlayıcısı hazır değil." };
  if (engineFor(s) === "motis" && (!Array.isArray(provider.matrixProfiles) || !provider.matrixProfiles.includes(s.transitProfile)))
    return { ready: false, detail: "Seçilen başlangıç için doğrulanmış MOTIS matrisi henüz hazır değil." };
  return { ready: true, detail: provider.detail };
}
export function hybridResultProblem(result: Result): string | null {
  if (result.scenario.mode !== "hybrid" || !["feasible", "optimal"].includes(result.status)) return null;
  const sites = result.selected;
  if (!Array.isArray(sites) || !sites.length || result.hospitalCount !== sites.length ||
      new Set(sites.map(site => site.id)).size !== sites.length ||
      sites.some(site => !Number.isInteger(site.beds) || !Number.isInteger(site.doctors) || site.beds! <= 0 || site.doctors! <= 0) ||
      !result.capacity || !close(result.capacity.totalBeds, sites.reduce((sum, site) => sum + site.beds!, 0)) ||
      !close(result.capacity.totalDoctors, sites.reduce((sum, site) => sum + site.doctors!, 0)) ||
      !Number.isFinite(result.capacity.annualEquivalentCostTRY) || result.capacity.annualEquivalentCostTRY < 0)
    return "Hibrit sonuçta ortak hastane ve kaynak kaydı doğrulanamadı. Sonuç gösterilmedi.";
  const siteIds = new Set(sites.map(site => site.id));
  const h = result.hybridSummary;
  const weight = result.scenario.carWeight ?? 70;
  if (!h || !close(h.carWeight, weight) || !close(h.transitWeight, 100 - weight) ||
      h.thresholds?.car !== result.scenario.threshold || h.thresholds?.transit !== (result.scenario.transitThreshold ?? 45) ||
      !Number.isFinite(h.weightedMeanMinutes) || typeof h.semantics !== "string" || !h.semantics.trim())
    return "Hibrit sonuçta ağırlık ve süre sözleşmesi doğrulanamadı. Sonuç gösterilmedi.";
  const modes = result.modalResults;
  if (!modes || !["car", "transit"].every(key => {
    const mode = modes[key as TravelMode];
    const limit = key === "car" ? result.scenario.threshold : (result.scenario.transitThreshold ?? 45);
    return mode && mode.metrics && Number.isFinite(mode.metrics.meanMinutes) &&
      mode.metrics.meanMinutes! >= 0 && mode.metrics.meanMinutes! <= limit + 1e-5 &&
      Number.isFinite(mode.metrics.coveragePercent) && mode.metrics.coveragePercent >= result.scenario.coverageTarget - 1e-5 &&
      mode.metrics.coveragePercent <= 100 + 1e-5 && Array.isArray(mode.assignments) && Array.isArray(mode.districts) &&
      mode.districts.length > 0 && mode.districts.every(d => typeof d.coveragePercent === "number" && Number.isFinite(d.coveragePercent) && d.coveragePercent >= result.scenario.districtFloor - 1e-5 && d.coveragePercent <= 100 + 1e-5) &&
      mode.assignments.every(a => Array.isArray(a.allocations) && a.allocations.every(part => siteIds.has(part.candidateId) && Number.isFinite(part.minutes) && part.minutes >= 0 && part.minutes <= limit + 1e-5));
  })) return "Hibrit hesabın iki ayrı ulaşım sonucu eksik. Sonuç gösterilmedi.";
  const weighted = (modes.car.metrics.meanMinutes! * weight + modes.transit.metrics.meanMinutes! * (100 - weight)) / 100;
  if (Math.abs(weighted - h.weightedMeanMinutes) > 1e-4)
    return "Hibrit sonuçta ağırlıklı süre iki ulaşım sonucuyla uyuşmuyor. Sonuç gösterilmedi.";
  return null;
}
export function responseProblem(result: Result, requested: Scenario): string | null {
  if (!result.scenario || scenarioKey(result.scenario) !== scenarioKey(requested))
    return "Sunucunun sonuç senaryosu gönderilen parametrelerle uyuşmuyor. Eski sonuç kullanılmadı.";
  if (requested.mode !== "car" && result.transitEvidence?.engine?.toLowerCase() !== engineFor(requested))
    return "Sonuçtaki ulaşım sağlayıcısı gönderilen istekle uyuşmuyor. Sonuç gösterilmedi.";
  return hybridResultProblem(result);
}
// Switching the map changes only the displayed flow; the common resource plan stays intact.
export function resultForView(result: Result | null, view: TravelMode): Result | null {
  if (!result || result.scenario.mode !== "hybrid") return result;
  if (hybridResultProblem(result)) return null;
  const mode = result.modalResults?.[view];
  return mode ? { ...result, metrics: mode.metrics, districts: mode.districts,
    assignments: mode.assignments, existingComparison: mode.existingComparison } : null;
}
export function routeRequest(result: Result, view: TravelMode, demandId: string, candidateId: string | null) {
  const actualMode = result.scenario.mode === "hybrid" ? view : result.scenario.mode;
  const motisTransit = actualMode === "transit" && engineFor(result.scenario) === "motis";
  const packageId = result.transitEvidence?.packageId;
  if (motisTransit && (typeof packageId !== "string" || !/^motis-[a-f0-9]{64}$/.test(packageId)))
    throw Error("Son hesaplamanın MOTIS paket kimliği doğrulanamadı. Rotadan önce yerleşimi yeniden hesaplayın.");
  return { ...result.scenario, demandId, candidateId,
    ...(motisTransit ? { routingPackageId: packageId } : {}),
    ...(result.scenario.mode === "hybrid" ? { routeMode: view } : {}) };
}
export function routeResponseProblem(route: Route, result: Result, view: TravelMode, demandId: string, candidateId: string | null): string | null {
  const expectedMode = result.scenario.mode === "hybrid" ? view : result.scenario.mode;
  if (!route.scenario || scenarioKey(route.scenario) !== scenarioKey(result.scenario) ||
      route.scenario.demandId !== demandId || route.scenario.candidateId !== candidateId || route.routeMode !== expectedMode)
    return "Güzergâh, seçilen ulaşım türü veya son hesaplanan senaryoyla uyuşmuyor. Gösterilmedi.";
  if (!Number.isFinite(route.minutes) || route.minutes < 0 || !Array.isArray(route.legs) || !Array.isArray(route.boardings))
    return "Güzergâh yanıtı doğrulanamadı.";
  if (expectedMode === "transit" && engineFor(result.scenario) === "motis") {
    const expectedPackage = result.transitEvidence?.packageId;
    if (typeof expectedPackage !== "string" || !/^motis-[a-f0-9]{64}$/.test(expectedPackage) ||
        route.scenario.routingPackageId !== expectedPackage || route.evidence?.packageId !== expectedPackage)
      return "Güzergâhın MOTIS paketi son hesaplanan yerleşimle uyuşmuyor. Rotadan önce yerleşimi yeniden hesaplayın.";
  }
  return null;
}

export function ProviderStatus({ status, scenario, error, refresh }: {
  status: RoutingStatus | null; scenario: Scenario; error: string; refresh: () => void;
}) {
  const availability = routingAvailability(status, scenario);
  const provider = status?.[engineFor(scenario)];
  return <div className={`provider-status ${availability.ready ? "is-ready" : "is-unavailable"}`} role="status">
    <div><span className="provider-dot" /><b>{providerLabel(engineFor(scenario))} · {availability.ready ? "seçili profil hazır" : "henüz kullanılamıyor"}</b></div>
    <p>{error || availability.detail}</p>
    {provider?.engineVersion && <small>Motor: {provider.engineVersion}</small>}
    {provider?.datasetScenario && <small>Tarihsel Ankara topluluk GTFS senaryosu</small>}
    <button type="button" onClick={refresh}>Durumu yenile</button>
  </div>;
}

export function HybridPlanningNote() {
  return <p className="hybrid-planning-note">Araba önceliği, acil ulaşımı düşünmek için bir planlama varsayımıdır. Kişisel araç yolları kullanılır; ambulanslara özgü hız, güzergâh veya gerçekleşmiş kullanım oranı ölçülmez.</p>;
}

export function hybridScopeLabel(result: Result): string {
  return result.searchScope?.restricted === false ? "sunulan adaylar ve bağlantılar" : "daraltılmış aday bağlantıları";
}
export function HybridCostCaption({ result }: { result: Result }) {
  const gap = result.capacity?.finalPlanCostGap;
  return <>Son plan maliyet açığı: {gap == null ? "kanıt sınırı yok" : `%${decimal(gap * 100)}`} ({hybridScopeLabel(result)})</>;
}

export function HybridOverview({ result, view, onViewChange }: { result: Result; view: TravelMode; onViewChange: (mode: TravelMode) => void }) {
  const h = result.hybridSummary;
  if (hybridResultProblem(result) || !h || !result.modalResults) return null;
  return <section className="hybrid-overview" aria-label="Ortak hastaneler, iki ulaşım senaryosu">
    <div className="hybrid-overview-title"><div><span className="eyebrow">ORTAK HASTANELER</span><h3>Tek plan, iki ulaşım.</h3></div>
      <div className="hybrid-weighted"><b>{decimal(h.weightedMeanMinutes)} <small>dk</small></b><span>%{decimal(h.carWeight)} araba + %{decimal(h.transitWeight)} toplu ulaşım</span></div></div>
    <p className="hybrid-brief">Ortak yatak ve hekimler, her modun tam talep senaryosuna göre sınanır. Yıllık maliyet bir kez hesaplanır.</p>
    <div className="hybrid-view-tabs" role="group" aria-label="Haritada gösterilen ulaşım senaryosu">
      {(["car", "transit"] as const).map(mode => <button key={mode} type="button" aria-pressed={view === mode} className={view === mode ? "selected" : ""} onClick={() => onViewChange(mode)}>
        {mode === "car" ? <CarFront size={19} /> : <TrainFront size={19} />}<span><b>{mode === "car" ? "Araba görünümü" : "Toplu ulaşım görünümü"}</b><small>{h.thresholds[mode]} dk sınır · %{decimal(result.modalResults![mode].metrics.coveragePercent)} talep</small></span></button>)}
    </div>
    <details className="hybrid-cost-details"><summary>Ağırlıklar, maliyet ve model sınırları</summary>
      <p>Harita, ilçe sonuçları ve mahalle atamaları seçilen ulaşım türünü gösterir. Hastaneler ve kaynakları değişmez.</p>
      <p>Her ulaşım senaryosunda talebin tamamı temel alınır; il ve ilçe kapsamı ayrı sınanır. Ağırlıklar yalnız yolculuk amacını belirler; talep veya hasta oranı değildir.</p>
      <HybridPlanningNote />
      <p>Önce ortak yatak, hekim ve konumlarla yıllık maliyet aranır. Sonra ilk geçerli maliyetin üzerine izin verilen bütçe içinde araba ve toplu ulaşım ortalamalarının ağırlıklı toplamı azaltılır.</p>
      {result.capacity && <p>İlk maliyet: {decimal(result.capacity.referenceCostTRY / 1e9)} milyar ₺/yıl · tavan: {decimal(result.capacity.budgetLimitTRY / 1e9)} milyar ₺/yıl · son plan: {decimal(result.capacity.annualEquivalentCostTRY / 1e9)} milyar ₺/yıl.</p>}
      <p><HybridCostCaption result={result} />. Bu açık, çözücünün bildirdiği alt sınıra göredir; hastane sayısının asgari olduğunun veya tüm Ankara için optimumun kanıtı değildir.</p>
      {result.capacity && <p>Süre aşaması açığı: {result.capacity.travelStageGap == null ? "kanıt sınırı yok" : `%${decimal(result.capacity.travelStageGap * 100)}`} ({hybridScopeLabel(result)}). {Number.isFinite(result.capacity.referenceMeanMinutes) ? <>İlk planın ağırlıklı süresi {decimal(result.capacity.referenceMeanMinutes)} dk; son plan {decimal(h.weightedMeanMinutes)} dk. {result.capacity.travelStageImproved ? "Daha kısa geçerli atama bulundu." : "Süre sınırında ilk plandan daha kısa geçerli atama bulunamadı."}</> : "İlk süre aşamasının kaydı mevcut değil."}</p>}
      <p>İki senaryoda aynı kişilerin kapsandığı zorunlu tutulmaz. Maliyet, hekim verimi ve klinik uygunluk model varsayımlarına bağlıdır.</p>
    </details>
  </section>;
}

export function TransitEvidenceNote({ scenario, result, pending }: { scenario: Scenario; result: Result | null; pending: boolean }) {
  const shown = result?.scenario ?? scenario;
  if (shown.mode === "car" && scenario.mode === "car") return null;
  const engine = engineFor(shown);
  const evidence = result?.transitEvidence;
  const date = evidence?.actualProfileDate ?? evidence?.profileDate ?? evidence?.departure;
  const sourceLabel = shown.mode === "car" ? "Araba hesabı"
    : engine === "motis" ? "MOTIS · tarihsel GTFS" : "Özgün EGO · kaynak ve zaman varsayımları";
  return <details className="transit-banner provider-evidence"><summary><Info size={15} />{sourceLabel}
    {date && ` · ${profileDateLabel(date, true)}`}{pending && " · yeni seçim bekliyor"}</summary><div>
    <b>{result ? "Gösterilen hesap: " : "Seçili hesap: "}{scenarioLabel(shown)}.</b>
    {pending && <p className="pending-provider">Bekleyen seçim: {scenarioLabel(scenario)}. Yeniden hesaplama gerekli.</p>}
    {shown.mode !== "car" && <p>{engine === "motis"
      ? "MOTIS, tarihsel topluluk GTFS verisiyle çalışır. Bu senaryo güncel resmî EGO tarifesinin veya canlı işletimin doğrulanması değildir. Yalnız sorgulanıp kayda alınan bağlantılar değerlendirilir."
      : "Özgün EGO modeli resmî kalkış kesitini ve tahmini ara durak sürelerini kullanır; MOTIS sonuçlarından ayrıdır."} Tek başlangıç sınanır; bütün gün için hizmet garantisi vermez. Eksik veri, gerçek hizmetin yokluğu anlamına gelmez.</p>}
    {date && <small>Tarifede kullanılan tarih / saat: {profileDateLabel(date)} · Türkiye saati</small>}
    {evidence?.scope && <small>{evidence.scope}</small>}
    {(evidence?.packageId || evidence?.gtfsSHA256 || evidence?.sourceSHA256) && <details><summary>Bu hesabın kaynak kimliği</summary>
      {evidence.packageId && <p>Paket: <code>{evidence.packageId}</code></p>}
      {evidence.gtfsSHA256 && <p>GTFS SHA-256: <code>{evidence.gtfsSHA256}</code></p>}
      {Object.entries(evidence.sourceSHA256 ?? {}).map(([key, hash]) => <p key={key}>{key}: <code>{hash}</code></p>)}
    </details>}
  </div></details>;
}
