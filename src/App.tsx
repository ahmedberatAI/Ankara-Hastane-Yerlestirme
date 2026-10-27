import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowUpRight, Cross, Download, Info, X, Search, LoaderCircle, MapPin, AlertTriangle, Hospital, UsersRound, Clock3, ShieldCheck, BedDouble, Stethoscope, Wallet, Compass, ArrowDownRight } from "lucide-react";
import AnkaraMap from "./Map";
import { departureLabel } from "./Hybrid";
import { PermanentTargets, PermanentViews, PermanentEvidence, PolicySources, policyProblem, permanentPlanProblem,
  permanentResultForView, permanentRouteRequest, permanentRouteProblem, profileLabel, formatNumber as number, formatDecimal as decimal } from "./Permanent";
import type { Dataset, PlanningPolicy, PermanentPlan, PermanentRoute, TravelMode, Demand, Candidate } from "./types";

const title = (value: string) => value.toLocaleLowerCase("tr-TR").replace(/(^|\s)\S/g, s => s.toLocaleUpperCase("tr-TR"));
async function jsonResponse(response: Response) {
  const payload = await response.json();
  if (!response.ok) throw Error(typeof payload.detail === "string" ? payload.detail : "Kayıtlı plan verisi şu anda alınamadı.");
  return payload;
}
function MethodDialog({ policy, plan, close }: { policy: PlanningPolicy; plan: PermanentPlan | null; close: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  return <dialog ref={ref} className="modal permanent-modal" aria-labelledby="method-title" onCancel={close} onClick={e => { if (e.target === ref.current) close(); }}>
    <div className="modal-top"><div><span className="eyebrow">KAYNAKLI HEDEFLER · ORTAK KAPASİTE</span><h2 id="method-title">Kalıcı planın dayanağı</h2></div><button className="icon-btn" onClick={close} aria-label="Pencereyi kapat"><X /></button></div>
    <div className="permanent-method"><p>Tek yerleşim, bir araba ağı ve dört tarihli toplu taşıma kesitinde birlikte değerlendirilir. Her kesit aynı hastane, yatak ve hekim kapasitesini kullanır. Kaydedilmiş plan görüntülenir; sayfa açılışı yeni optimizasyon başlatmaz.</p>
      <PermanentTargets policy={policy} /><PolicySources policy={policy} />{plan && <PermanentEvidence plan={plan} />}</div>
  </dialog>;
}
export default function App() {
  const [data, setData] = useState<Dataset | null>(null);
  const [policy, setPolicy] = useState<PlanningPolicy | null>(null);
  const [plan, setPlan] = useState<PermanentPlan | null>(null);
  const [loading, setLoading] = useState(true), [error, setError] = useState("");
  const [reload, setReload] = useState(0), [view, setView] = useState<TravelMode>("car");
  const [modal, setModal] = useState(false), [query, setQuery] = useState("");
  const [district, setDistrict] = useState(""), [focus, setFocus] = useState<Candidate | Demand | null>(null);
  const [selectedDemand, setSelectedDemand] = useState<Demand | null>(null);
  const [route, setRoute] = useState<PermanentRoute | null>(null), [routeBusy, setRouteBusy] = useState(false), [routeError, setRouteError] = useState("");
  const routeVersion = useRef(0), routeController = useRef<AbortController | null>(null);
  function clearRoute() {
    routeVersion.current++; routeController.current?.abort(); setRoute(null); setRouteBusy(false); setRouteError(""); setSelectedDemand(null);
  }
  useEffect(() => {
    const controller = new AbortController(); let current = true;
    setLoading(true); setError(""); setPlan(null); setData(null); setPolicy(null); clearRoute();
    Promise.all([fetch("/api/data", { signal: controller.signal }).then(jsonResponse),
      fetch("/api/planning-policy", { signal: controller.signal }).then(jsonResponse)])
      .then(async ([dataset, fixedPolicy]) => {
        if (!current) return;
        const policyError = policyProblem(fixedPolicy); if (policyError) throw Error(policyError);
        setPolicy(fixedPolicy);
        const saved = await fetch("/api/permanent-plan", { signal: controller.signal }).then(jsonResponse);
        if (!current) return;
        const problem = permanentPlanProblem(saved, dataset, fixedPolicy); if (problem) throw Error(problem);
        setData(dataset); setPlan(saved);
      }).catch(reason => { if (current && reason.name !== "AbortError") setError(reason.message || "Plan doğrulanamadı."); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; controller.abort(); routeVersion.current++; routeController.current?.abort(); };
  }, [reload]);
  const displayed = useMemo(() => plan ? permanentResultForView(plan, view) : null, [plan, view]);
  const stats = displayed?.metrics;
  const assignment = displayed?.assignments?.find(a => a.demandId === selectedDemand?.id);
  const matches = useMemo(() => query.trim().length > 1 ? data?.demands.filter(d =>
    `${d.name} ${d.district}`.toLocaleLowerCase("tr-TR").includes(query.toLocaleLowerCase("tr-TR"))).slice(0, 7) || [] : [], [query, data]);
  function changeView(next: TravelMode) { if (next !== view) { clearRoute(); setView(next); } }
  async function selectDemand(demand: Demand, explicitCandidate?: string) {
    if (!plan || !displayed) return;
    routeController.current?.abort(); const controller = new AbortController(); routeController.current = controller;
    const version = ++routeVersion.current, routeView = view, routePlan = plan;
    setSelectedDemand(demand); setFocus(demand); setQuery(""); setRoute(null); setRouteError(""); setRouteBusy(false);
    const assigned = displayed.assignments?.find(a => a.demandId === demand.id);
    const candidateId = explicitCandidate || assigned?.candidateId;
    if (!candidateId) { setRouteError("Bu mahalle talebi, bu kayıtlı kesitte süre ve kapasite sınırları içinde atanmamış. Bu, gerçek hizmet bulunmadığının kanıtı değildir."); return; }
    setRouteBusy(true);
    try {
      const request = permanentRouteRequest(routePlan, routeView, demand.id, candidateId);
      const response = await fetch("/api/permanent-route", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request), signal: controller.signal });
      const result = await jsonResponse(response);
      if (version !== routeVersion.current) return;
      const problem = permanentRouteProblem(result, routePlan, routeView, demand.id, candidateId); if (problem) throw Error(problem);
      setRoute(result);
    } catch (reason) { if (version === routeVersion.current && !controller.signal.aborted) setRouteError(reason instanceof Error ? reason.message : "Rota doğrulanamadı."); }
    finally { if (version === routeVersion.current) setRouteBusy(false); }
  }
  function download() {
    if (!plan) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(plan, null, 2)], { type: "application/json" }));
    const a = document.createElement("a"); a.href = url; a.download = `${plan.planId}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <div className="app permanent-app">
    <a className="skip-link" href="#plan-haritasi">Haritaya geç</a>
    <header className="header"><a className="brand" href="/" aria-label="ERİŞİM ana sayfa"><span className="brand-icon"><Cross size={21} strokeWidth={2.1} /></span><b>ERİŞİM<span>.</span></b><div className="brand-caption">ANKARA<span>Kalıcı hastane planı</span></div></a>
      <nav aria-label="Ana menü"><span className="nav-active"><span /> Ortak plan</span><button onClick={() => setModal(true)} disabled={!policy}>Yöntem ve kaynaklar <ArrowUpRight size={14} /></button></nav><div className="prototype"><span /> Araştırma modeli</div></header>
    <div className="workspace"><aside className="sidebar">
      <div className="sidebar-intro"><span className="eyebrow"><span className="tiny-line" /> BİR ŞEHİR, ORTAK BİR PLAN</span><h1>Sağlığa<br />{" "}daha <em>yakın.</em></h1><p>Bir şehrin hastanelerini, herkesin erişimini gözeterek birlikte düşünmek.</p><span className="intro-location"><MapPin size={13} /> Ankara, Türkiye <span>25 ilçe</span></span></div>
      {policy && <PermanentTargets policy={policy} />}
      <button className="permanent-source-button" onClick={() => setModal(true)} disabled={!policy}><span>Bu hedefler neden seçildi?</span><ArrowUpRight size={16} /></button>
      <div className="permanent-sidebar-note"><span className="note-icon"><Compass size={17} /></span><p><b>Tek yerleşim, iki ulaşım biçimi.</b>Görünümü değiştirirken hastaneler, yataklar ve hekimler aynı kalır.</p></div>
      {plan && <details className="permanent-sites"><summary><Hospital size={16} /><span>Hastane konumları</span><b>{number(plan.hospitalCount!)}</b><ArrowDownRight className="disclosure-arrow" size={16} /></summary><div className="site-scroll">{plan.selected!.map((site, index) => <button key={site.id} onClick={() => { setFocus(site); clearRoute(); }}><span className="site-number">{index + 1}</span><div><b>{title(site.name)}</b><small>{title(site.district)} · {site.beds} yatak · {site.doctors} hekim</small></div><MapPin size={13} /></button>)}</div></details>}
      <div className="sidebar-bottom"><Info size={15} /><p>Klinik onay veya kesin hastane ihtiyacı değildir.<br /><small>Konumsuz nüfus da kapsam paydasında tutulur.</small></p></div>
    </aside><main className="main">
      <div className="main-topline"><div><span className="eyebrow">ŞEHRİN SAĞLIK HARİTASI</span><h2>Ankara için ortak bir yerleşim.</h2></div><button className="export-btn" disabled={!plan} onClick={download}><Download size={15} /> Planı indir</button></div>
      {loading && <div className="permanent-loading" role="status"><LoaderCircle className="spin" size={20} /> Kaydedilmiş plan yükleniyor…</div>}
      {error && <div className="error-banner" role="alert"><AlertTriangle size={20} /><div><b>Kalıcı plan gösterilemiyor</b><p>{error}</p><p>Doğrulanamayan bir kayıttan hastane veya kapsam sayısı üretilmedi.</p><button onClick={() => setReload(n => n + 1)}>Kaydı yeniden yükle</button></div></div>}
      {plan && stats && <>
        <section className="stats-grid" aria-label="Yerleşimin özeti"><article className="stat-card primary-stat"><div className="stat-label"><Hospital size={14} /> ORTAK HASTANE</div><div className="stat-number">{number(plan.hospitalCount!)}</div><div className="stat-caption">Beş kesitte aynı konumlar</div></article><article className="stat-card"><div className="stat-label"><UsersRound size={14} /> TALEP KAPSAMI</div><div className="stat-number">%{decimal(stats.coveragePercent)}</div><div className="stat-caption">{number(stats.coveredPopulation)} kişi eşdeğeri</div></article><article className="stat-card"><div className="stat-label"><Clock3 size={14} /> ORTALAMA ERİŞİM</div><div className="stat-number">{decimal(stats.meanMinutes!)}<span>dk</span></div><div className="stat-caption">Atanan talep ile ağırlıklı</div></article><article className="stat-card"><div className="stat-label"><ShieldCheck size={14} /> EN DÜŞÜK İLÇE</div><div className="stat-number">%{decimal(Math.min(...displayed!.districts!.map(d => d.coveragePercent!)))}</div><div className="stat-caption">Bu görünümde · hedef en az %80</div></article></section>
        <section className="map-panel" id="plan-haritasi" aria-label="Ankara erişim haritası" tabIndex={-1}>
        <div className="map-panel-heading"><div className="map-panel-title"><span className="map-title-icon"><Compass size={20} strokeWidth={1.5} /></span><div><h3>Şehri keşfedin</h3><p>Aynı hastaneler, farklı ulaşım yolları.</p></div></div><PermanentViews plan={plan} view={view} onView={changeView} /></div>
        <div className="map-toolbar"><div className="permanent-search"><Search size={15} /><input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Mahalle bul" aria-label="Haritada mahalle ara" />{matches.length > 0 && <div className="permanent-search-results">{matches.map(d => <button key={d.id} onClick={() => void selectDemand(d)}>{title(d.name)} <small>{title(d.district)}</small></button>)}</div>}</div><label className="permanent-district-filter">Haritada ilçe <select aria-label="Haritada ilçeyi göster" value={district} onChange={e => { setDistrict(e.target.value); clearRoute(); }}><option value="">Tüm ilçeler</option>{data!.districts.map(d => <option key={d.id} value={d.id}>{title(d.name)}</option>)}</select></label></div>
        <div className="map-area"><AnkaraMap data={data!} result={displayed} transitEngine="motis" viewMode={view} route={route} onDemand={d => void selectDemand(d)} focus={focus} district={district} />
          {selectedDemand && <section className="route-card"><button className="close-route" aria-label="Güzergâhı kapat" onClick={clearRoute}><X size={16} /></button><span className="eyebrow">MAHALLEDEN ORTAK HASTANEYE</span><h3>{title(selectedDemand.name)}</h3><p>{title(selectedDemand.district)} · {number(selectedDemand.population)} kişi</p>
            {assignment && <div className="allocation-list"><b>Talebin %{decimal(assignment.servedFraction * 100)}'i atandı</b>{assignment.allocations.map(a => <button key={a.candidateId} onClick={() => void selectDemand(selectedDemand, a.candidateId)} disabled={routeBusy}><span>{title(plan.selected!.find(c => c.id === a.candidateId)!.name)} · %{decimal(a.fraction * 100)}</span><span>{decimal(a.minutes)} dk <ArrowUpRight size={12} /></span></button>)}</div>}
            {routeBusy ? <div className="route-loading" role="status"><LoaderCircle className="spin" size={15} /> Kayıtlı atamanın güzergâhı getiriliyor…</div> : route ? <><div className="route-time">{decimal(route.minutes)}<span>dk</span><b>{title(route.candidate)}</b></div>{route.boardings.length > 0 && <div className="route-lines">{route.boardings.map((b, i) => <span key={i} title={b.stop}>{b.route}{b.departureTime ? ` · ${departureLabel(b.departureTime)}` : ""}</span>)}</div>}<small className="route-footnote">{view === "transit" ? `${profileLabel(plan, plan.criticalTransitProfile)}. ` : "Sabit araba ağı; canlı trafik yok. "}{route.note}</small></> : <p className="route-footnote" role={routeError ? "status" : undefined}>{routeError}</p>}
          </section>}
        </div><div className="map-footer"><span><span className="map-foot-dot" /> Mahalleye dokunun, hastaneye giden yolu görün.</span><span>{number(data!.metadata.matchedPopulation)} kişi konumlandırıldı · {number(data!.metadata.unlocatedPopulation)} kişi konumsuz, paydada</span></div>
        </section>
        <section className="capacity-strip permanent-capacity" aria-label="Değişmeyen ortak kaynaklar"><div><span><BedDouble size={16} /> ORTAK YATAK</span><strong>{number(plan.capacity!.totalBeds)}</strong><small>Beş kesitte aynı kapasite</small></div><div><span><Stethoscope size={16} /> ORTAK HEKİM</span><strong>{number(plan.capacity!.totalDoctors)}</strong><small>Klinik FTE ölçümü değildir</small></div><div><span><Wallet size={16} /> YILLIK EŞDEĞER MALİYET</span><strong>{decimal(plan.capacity!.annualEquivalentCostTRY / 1e9, 2)} <em>mr ₺</em></strong><small>Yıllık maliyet bir kez hesaplanır</small></div></section>
        <PermanentEvidence plan={plan} />
        <details className="permanent-districts"><summary>25 ilçenin bu görünümdeki kapsamı</summary><div className="district-grid">{displayed!.districts!.map(d => <button key={d.id} onClick={() => { setDistrict(d.id); clearRoute(); }}><span>{title(d.name)}</span><strong>%{decimal(d.coveragePercent!)}</strong><i style={{ width: `${Math.min(100, d.coveragePercent!)}%` }} /></button>)}</div></details>
      </>}
    </main></div>{modal && policy && <MethodDialog policy={policy} plan={plan} close={() => setModal(false)} />}
  </div>;
}
