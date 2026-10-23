import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  CarFront,
  TrainFront,
  Cross,
  Download,
  Info,
  X,
  Search,
  ChevronDown,
  ChevronRight,
  LoaderCircle,
  MapPin,
  SlidersHorizontal,
  Users,
  Timer,
  AlertTriangle,
  ExternalLink,
  Database,
  Route as RouteIcon,
} from "lucide-react";
import AnkaraMap from "./Map";
import HealthMethod from "./HealthMethod";
import Benchmark from "./Benchmark";
import Robustness from "./Robustness";
import StageComparison, {
  CostGapCaption,
  allocationScopeLabel,
} from "./StageComparison";
import { transitProfileLabels } from "./types";
import type { TransitProfile } from "./types";
import type {
  Dataset,
  Scenario,
  Result,
  Demand,
  Candidate,
  Route,
  Mode,
} from "./types";

const JointPlan = lazy(() => import("./JointPlan"));
const WindowPlan = lazy(() => import("./WindowPlan"));
const initial: Scenario = {
  mode: "car",
  threshold: 30,
  coverageTarget: 95,
  districtFloor: 80,
  trafficFactor: 1,
  demandMultiplier: 1,
  bedOccupancy: 80,
  contactsPerDoctor: 2140,
  hospitalLimit: null,
  operatingCostMultiplier: 1,
  costTolerance: 10,
  transitProfile: "weekday-1000",
};
const number = (n: number) =>
  n.toLocaleString("tr-TR", { maximumFractionDigits: 0 });
const decimal = (n: number | null | undefined, digits = 1) =>
  n == null
    ? "—"
    : n.toLocaleString("tr-TR", {
        maximumFractionDigits: digits,
        minimumFractionDigits: digits,
      });
const title = (s: string) =>
  s
    .toLocaleLowerCase("tr-TR")
    .replace(/(^|\s)\S/g, (c) => c.toLocaleUpperCase("tr-TR"));
const normalize = (s: string) =>
  s
    .toLocaleLowerCase("tr-TR")
    .replaceAll("ı", "i")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");

function Modal({
  kind,
  data,
  close,
}: {
  kind: "method" | "sources";
  data: Dataset;
  close: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      className="modal"
      onCancel={close}
      onClick={(e) => {
        if (e.target === ref.current) close();
      }}
    >
      <div className="modal-top">
        <div>
          <span className="eyebrow">AÇIK YÖNTEM · İZLENEBİLİR VERİ</span>
          <h2>
            {kind === "method"
              ? "Bu yerleşim nasıl hesaplanıyor?"
              : "Her sayının bir kaynağı var."}
          </h2>
        </div>
        <button
          className="icon-btn"
          onClick={close}
          aria-label="Pencereyi kapat"
        >
          <X />
        </button>
      </div>
      {kind === "method" ? (
        <HealthMethod data={data} />
      ) : (
        <div className="sources-content">
          <div className="source-overview">
            <div>
              <b>{number(data.metadata.matchedNeighborhoodCount)}</b>
              <span>haritayla eşleşen mahalle</span>
            </div>
            <div>
              <b>
                %
                {decimal(
                  (data.metadata.matchedPopulation /
                    data.metadata.provincePopulation) *
                    100,
                  2,
                )}
              </b>
              <span>konumu modellenen nüfus</span>
            </div>
            <div>
              <b>20 Ekim 2026</b>
              <span>OSM kesit tarihi</span>
            </div>
          </div>
          <p className="sources-intro">
            Resmî nüfus, topluluk harita verisi ve senaryo varsayımları ayrı
            tutulur. Kaynağa erişilmesi, bütün verinin modele alındığı anlamına
            gelmez.
          </p>
          {data.sources.map((s) => (
            <article className="source-item" key={s.id}>
              <div>
                <span className="source-publisher">
                  {s.publisher} · {s.date}
                </span>
                <h3>
                  <a href={s.url} target="_blank" rel="noreferrer">
                    {s.title}
                    <ArrowUpRight size={17} />
                  </a>
                </h3>
                <p>{s.usedFor}</p>
                <small>{s.note}</small>
              </div>
              <span className="source-status">{s.status}</span>
            </article>
          ))}
          <a
            className="text-link"
            href="/api/unmatched"
            target="_blank"
            rel="noreferrer"
          >
            Eşleşmeyen mahalle kayıtlarını incele <ExternalLink size={14} />
          </a>
        </div>
      )}
    </dialog>
  );
}

export default function App() {
  const [data, setData] = useState<Dataset | null>(null);
  const [scenario, setScenario] = useState(initial);
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [modal, setModal] = useState<"method" | "sources" | null>(null);
  const [focus, setFocus] = useState<Candidate | Demand | null>(null);
  const [district, setDistrict] = useState("");
  const [search, setSearch] = useState("");
  const [selectedDemand, setSelectedDemand] = useState<Demand | null>(null);
  const [route, setRoute] = useState<Route | null>(null);
  const [routeBusy, setRouteBusy] = useState(false);
  const [routeError, setRouteError] = useState("");
  const [districtPanel, setDistrictPanel] = useState(false);
  const autoRun = useRef(false);
  const routeVersion = useRef(0);
  const solveVersion = useRef(0);
  const dirty =
    !!result &&
    Object.entries(scenario).some(
      ([key, value]) => result.scenario[key as keyof Scenario] !== value,
    );
  const displayedScenario = result?.scenario ?? scenario;
  const displayedProfile =
    transitProfileLabels[displayedScenario.transitProfile];
  const searchMatches = useMemo(
    () =>
      search.length > 1
        ? data?.demands
            .filter((d) =>
              normalize(`${d.name} ${d.district}`).includes(normalize(search)),
            )
            .slice(0, 7) || []
        : [],
    [data, search],
  );
  useEffect(() => {
    fetch("/api/data")
      .then((r) => {
        if (!r.ok)
          throw Error(
            "Veri servisine ulaşılamadı. Python sunucusunun çalıştığını kontrol edin.",
          );
        return r.json();
      })
      .then(setData)
      .catch((e) => {
        setError(e.message);
        setBusy(false);
      });
  }, []);
  async function solve(params: Scenario) {
    const version = ++solveVersion.current;
    setBusy(true);
    setError("");
    setRoute(null);
    setSelectedDemand(null);
    routeVersion.current++;
    try {
      const response = await fetch("/api/solve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      if (!response.ok)
        throw Error(
          "Çözüm hesaplanamadı. Sunucu bağlantısını kontrol edip tekrar deneyin.",
        );
      const next: Result = await response.json();
      if (version === solveVersion.current) {
        setResult(next);
        setRoute(null);
        setSelectedDemand(null);
        setRouteBusy(false);
        routeVersion.current++;
      }
    } catch (e) {
      if (version === solveVersion.current)
        setError(e instanceof Error ? e.message : "Hesaplama hatası");
    } finally {
      if (version === solveVersion.current) setBusy(false);
    }
  }
  useEffect(() => {
    if (data && !autoRun.current) {
      autoRun.current = true;
      void solve(initial);
    }
  }, [data]);
  function changeMode(mode: Mode) {
    if (mode === scenario.mode || busy) return;
    solveVersion.current++;
    routeVersion.current++;
    setResult(null);
    setRoute(null);
    setSelectedDemand(null);
    setRouteBusy(false);
    setError("");
    setScenario((s) => ({
      ...s,
      mode,
      threshold: mode === "car" ? 30 : 45,
      trafficFactor: 1,
    }));
  }
  async function selectDemand(demand: Demand, candidateId?: string) {
    setSelectedDemand(demand);
    setFocus(demand);
    setSearch("");
    setRoute(null);
    setRouteError("");
    setRouteBusy(false);
    const version = ++routeVersion.current;
    const assignment = result?.assignments?.find(
      (a) => a.demandId === demand.id,
    );
    if (!assignment) return;
    if (!candidateId && assignment.minutes === null) {
      setRouteError(
        "Bu senaryoda mahalleye süre ve kapasite koşullarını sağlayan talep payı atanmadı. Bu, gerçek hayatta hizmet olmadığı anlamına gelmez.",
      );
      return;
    }
    setRouteBusy(true);
    try {
      const response = await fetch("/api/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...result!.scenario,
          demandId: demand.id,
          candidateId: candidateId || assignment.candidateId,
        }),
      });
      if (!response.ok) throw Error("Güzergâh getirilemedi. Tekrar deneyin.");
      const next = await response.json();
      if (version === routeVersion.current) setRoute(next);
    } catch (e) {
      if (version === routeVersion.current)
        setRouteError(e instanceof Error ? e.message : "Güzergâh hatası");
    } finally {
      if (version === routeVersion.current) setRouteBusy(false);
    }
  }
  function download() {
    if (!result) return;
    const blob = new Blob(
      [
        JSON.stringify(
          {
            ...result,
            sources: data?.sources,
            healthPlanning: data?.healthPlanning,
            exportedAt: new Date().toISOString(),
          },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob),
      a = document.createElement("a");
    a.href = url;
    a.download = `ankara-${result.scenario.mode}${result.scenario.mode === "transit" ? `-${result.scenario.transitProfile}` : ""}-${result.scenario.threshold}dk.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
  const stats = result?.metrics;
  const capacity = result?.capacity;
  const selectedAssignment = result?.assignments?.find(
    (a) => a.demandId === selectedDemand?.id,
  );
  return (
    <div className="app">
      <header className="header">
        <a className="brand" href="/" aria-label="ERİŞİM ana sayfa">
          <span className="brand-icon">
            <Cross size={22} strokeWidth={2.5} />
          </span>
          <b>
            ERİŞİM<span>.</span>
          </b>
          <div className="brand-caption">
            ANKARA
            <br />
            <span>Sağlık yerleşim laboratuvarı</span>
          </div>
        </a>
        <nav>
          <span className="nav-active">Harita</span>
          <button onClick={() => setModal("method")} disabled={!data}>
            Yöntem <ArrowUpRight size={14} />
          </button>
          <button onClick={() => setModal("sources")} disabled={!data}>
            Veri kaynakları <ArrowUpRight size={14} />
          </button>
        </nav>
        <div className="prototype">
          <span /> Araştırma prototipi
        </div>
      </header>
      <div className="workspace">
        <aside className="sidebar">
          <div className="sidebar-intro">
            <span className="eyebrow">
              <span className="tiny-line" /> DAHA İYİ BİR SAĞLIK AĞI
            </span>
            <h1>
              Sağlığa
              <br /> daha yakın.
            </h1>
            <p>
              Yeterli kapasiteyi doğru konumlara yerleştirin. Yapım, işletme ve
              yolculuğu birlikte değerlendirin.
            </p>
          </div>
          <div className="control-section">
            <div className="label-row">
              <label>Ulaşım modeli</label>
              <span>01</span>
            </div>
            <div className="mode-tabs">
              <button
                className={scenario.mode === "car" ? "selected" : ""}
                onClick={() => changeMode("car")}
                disabled={busy}
              >
                <CarFront size={18} /> Araba
              </button>
              <button
                className={scenario.mode === "transit" ? "selected" : ""}
                onClick={() => changeMode("transit")}
                disabled={busy}
              >
                <TrainFront size={18} /> EGO
              </button>
            </div>
            <p
              className={`mode-note ${scenario.mode === "transit" ? "amber" : ""}`}
            >
              {scenario.mode === "car"
                ? "Gerçek yol ağı · tahmini sürüş süreleri"
                : "Resmî kalkış saatleri · ara durak süreleri tahmini"}
            </p>
            {scenario.mode === "transit" && (
              <label className="transit-profile">
                Yolculuğa başlama zamanı
                <select
                  aria-label="EGO gün ve hareket saati"
                  value={scenario.transitProfile}
                  disabled={busy}
                  onChange={(e) =>
                    setScenario((s) => ({
                      ...s,
                      transitProfile: e.target.value as TransitProfile,
                    }))
                  }
                >
                  {Object.entries(transitProfileLabels).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
                <small>
                  Normal hizmet günü · tatil ve canlı gecikme verisi yok
                </small>
              </label>
            )}
          </div>
          <div className="control-section settings">
            <div className="label-row">
              <label>Hedeflerinizi belirleyin</label>
              <span>02</span>
            </div>
            <p className="field-help">
              Süre ve kapsam hedefleri değiştirilebilir planlama tercihleridir;
              resmî veya klinik standart değildir.
            </p>
            <div className="slider-field">
              <label htmlFor="threshold">
                En fazla yolculuk süresi{" "}
                <strong>
                  {scenario.threshold}
                  <small> dk</small>
                </strong>
              </label>
              <input
                id="threshold"
                type="range"
                min="10"
                max="120"
                step="5"
                value={scenario.threshold}
                onChange={(e) =>
                  setScenario((s) => ({ ...s, threshold: +e.target.value }))
                }
                disabled={busy}
              />
              <div className="range-ends">
                <span>10 dk</span>
                <span>120 dk</span>
              </div>
            </div>
            <div className="slider-field">
              <label htmlFor="coverage">
                Karşılanacak talep payı{" "}
                <strong>%{scenario.coverageTarget}</strong>
              </label>
              <input
                id="coverage"
                type="range"
                min="50"
                max="100"
                step="1"
                value={scenario.coverageTarget}
                onChange={(e) =>
                  setScenario((s) => ({
                    ...s,
                    coverageTarget: +e.target.value,
                  }))
                }
                disabled={busy}
              />
              <div className="range-ends">
                <span>%50</span>
                <span>%100</span>
              </div>
            </div>
            <div className="slider-field">
              <label htmlFor="equity">
                Her ilçede en az talep payı{" "}
                <strong>%{scenario.districtFloor}</strong>
              </label>
              <input
                id="equity"
                type="range"
                min="0"
                max="100"
                step="5"
                value={scenario.districtFloor}
                onChange={(e) =>
                  setScenario((s) => ({ ...s, districtFloor: +e.target.value }))
                }
                disabled={busy}
              />
              <p className="field-help">
                Kırsal ilçeler de çözümün bir parçası olsun.
              </p>
            </div>
            {scenario.mode === "car" && (
              <label className="select-field">
                Yol süresi senaryosu
                <select
                  value={scenario.trafficFactor}
                  onChange={(e) =>
                    setScenario((s) => ({
                      ...s,
                      trafficFactor: +e.target.value,
                    }))
                  }
                  disabled={busy}
                >
                  <option value="1">Temel hız varsayımı</option>
                  <option value="1.3">Sürüş süresi × 1,3</option>
                  <option value="1.6">Sürüş süresi × 1,6</option>
                  <option value="2">Sürüş süresi × 2</option>
                </select>
              </label>
            )}
          </div>
          <label className="select-field site-limit">
            Hastane sayısı sınırı
            <select
              aria-label="Hastane sayısı sınırı"
              disabled={busy}
              value={scenario.hospitalLimit ?? "auto"}
              onChange={(e) =>
                setScenario((s) => ({
                  ...s,
                  hospitalLimit:
                    e.target.value === "auto" ? null : +e.target.value,
                }))
              }
            >
              <option value="auto">Maliyet ve erişime göre seç</option>
              <option value="91">En fazla 91 hastane</option>
            </select>
          </label>
          <details className="capacity-settings">
            <summary>
              Kapasite ve bütçe varsayımları <SlidersHorizontal size={16} />
            </summary>
            <p>
              Bu değerler gözlem değil, değiştirilebilir planlama tercihleridir.
            </p>
            <label className="select-field">
              Talep senaryosu
              <select
                aria-label="Talep senaryosu"
                value={scenario.demandMultiplier}
                disabled={busy}
                onChange={(e) =>
                  setScenario((s) => ({
                    ...s,
                    demandMultiplier: +e.target.value,
                  }))
                }
              >
                <option value="0.8">2024 kullanım oranı × 0,8</option>
                <option value="1">2024 kullanım oranı × 1</option>
                <option value="1.2">2024 kullanım oranı × 1,2</option>
                <option value="1.5">2024 kullanım oranı × 1,5</option>
              </select>
            </label>
            <label className="select-field">
              Yatak doluluk tavanı
              <select
                aria-label="Yatak doluluk tavanı"
                value={scenario.bedOccupancy}
                disabled={busy}
                onChange={(e) =>
                  setScenario((s) => ({ ...s, bedOccupancy: +e.target.value }))
                }
              >
                {[59.5, 60, 70, 80, 85, 90].map((v) => (
                  <option key={v} value={v}>
                    %{decimal(v, v === 59.5 ? 1 : 0)}
                    {v === 59.5 ? " · Ankara 2024" : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="select-field">
              Yıllık temas / hekim
              <select
                aria-label="Yıllık temas / hekim"
                value={scenario.contactsPerDoctor}
                disabled={busy}
                onChange={(e) =>
                  setScenario((s) => ({
                    ...s,
                    contactsPerDoctor: +e.target.value,
                  }))
                }
              >
                {[835, 1500, 2140, 3000, 4000, 6000].map((v) => (
                  <option key={v} value={v}>
                    {number(v)} temas
                    {v === 2140
                      ? " · MLP proxy"
                      : v === 835
                        ? " · AÜ duyarlılığı"
                        : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="select-field">
              İşletme maliyeti duyarlılığı
              <select
                aria-label="İşletme maliyeti duyarlılığı"
                value={scenario.operatingCostMultiplier}
                disabled={busy}
                onChange={(e) =>
                  setScenario((s) => ({
                    ...s,
                    operatingCostMultiplier: +e.target.value,
                  }))
                }
              >
                {[0.5, 0.75, 1, 1.25, 1.5, 2].map((v) => (
                  <option key={v} value={v}>
                    Gider proxy tutarı × {decimal(v, 2)}
                  </option>
                ))}
              </select>
            </label>
            <label className="select-field">
              Daha kısa yol için ek yıllık maliyet
              <select
                aria-label="Ek yıllık maliyet"
                value={scenario.costTolerance}
                disabled={busy}
                onChange={(e) =>
                  setScenario((s) => ({ ...s, costTolerance: +e.target.value }))
                }
              >
                {[0, 5, 10, 20, 30].map((v) => (
                  <option key={v} value={v}>
                    En fazla %{decimal(v, v === 59.5 ? 1 : 0)}
                    {v === 59.5 ? " · Ankara 2024" : ""}
                  </option>
                ))}
              </select>
            </label>
            <p>
              Ek bütçe, ilk aşamada bulunan geçerli çözümün bedeline göre
              hesaplanır.
            </p>
          </details>
          <div className="action-area">
            <button
              className="primary-btn"
              onClick={() => solve(scenario)}
              disabled={busy || !data}
            >
              {busy ? (
                <>
                  <LoaderCircle size={18} className="spin" /> Yerleşim
                  hesaplanıyor
                </>
              ) : (
                <>
                  {result ? "Yeniden hesapla" : "Yerleşimi hesapla"}
                  <ArrowRight size={19} />
                </>
              )}
            </button>
            <p className={dirty ? "dirty-note" : "small-note"}>
              {busy
                ? "Bağımsız yatak ve hekim kapasitesi, işletme ve ulaşım çözülüyor. Birkaç dakika sürebilir."
                : dirty
                  ? "Parametreler değişti. Harita son hesaplanan senaryoyu gösteriyor."
                  : "50–4.050 yatak · hekim kadrosu ayrıca seçilir"}
            </p>
          </div>
          <button
            className="method-teaser"
            onClick={() => setModal("method")}
            disabled={!data}
          >
            <span className="mini-icon">
              <SlidersHorizontal size={17} />
            </span>
            <div>
              <b>Kapasite nasıl hesaplanıyor?</b>
              <span>Modeli ve varsayımları keşfedin</span>
            </div>
            <ArrowUpRight size={17} />
          </button>
          {result?.selected && (
            <div className="site-list">
              <div className="label-row">
                <label>Önerilen konumlar</label>
                <span>{result.selected.length}</span>
              </div>
              <div className="site-scroll">
                {result.selected.map((c, i) => (
                  <button
                    key={c.id}
                    onClick={() => {
                      setFocus(c);
                      setRoute(null);
                      setSelectedDemand(null);
                      routeVersion.current++;
                    }}
                  >
                    <span className="site-number">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <div>
                      <b>{title(c.name)}</b>
                      <small>
                        {title(c.district)} · {c.beds} yatak · {c.doctors} hekim
                      </small>
                    </div>
                    <ChevronRight size={15} />
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="sidebar-bottom">
            <Database size={14} />
            <span>
              TÜİK 2025 + Sağlık Bakanlığı 2024
              <br />
              <small>25 ilçenin tamamı değerlendirilir.</small>
            </span>
          </div>
        </aside>
        <main className="main">
          <div className="main-topline">
            <div>
              <span className="eyebrow">ANKARA’NIN TAMAMI</span>
              <h2>Bir şehir. Daha dengeli erişim.</h2>
            </div>
            <button
              className="export-btn"
              onClick={download}
              disabled={!stats || busy || dirty}
            >
              <Download size={16} />
              <span>Senaryoyu indir</span>
            </button>
          </div>
          <div className="stats-grid">
            <div className="stat-card primary-stat">
              <div className="stat-label">
                Seçilen hastane <Cross size={17} />
              </div>
              <div className="stat-number">
                {busy ? (
                  <span className="stat-loading">···</span>
                ) : (
                  (result?.hospitalCount ?? "—")
                )}
                <span>adet</span>
              </div>
              <div className="stat-caption">
                {result?.status === "optimal" ||
                result?.status === "feasible" ? (
                  <CostGapCaption result={result} />
                ) : (
                  "Kapasiteye göre seçilen tesis sayısı"
                )}
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-label">
                Sürede karşılanan talep <Users size={17} />
              </div>
              <div className="stat-number">
                {stats ? `%${decimal(stats.coveragePercent)}` : "—"}
              </div>
              <div className="stat-caption">
                {stats
                  ? `${number(stats.coveredPopulation)} / ${number(data!.metadata.provincePopulation)} kişi eşdeğeri`
                  : "Nüfusla orantılı yıllık talep payı"}
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-label">
                Ortalama yolculuk <Timer size={17} />
              </div>
              <div className="stat-number">
                {decimal(stats?.meanMinutes)}
                <span>dk</span>
              </div>
              <div className="stat-caption">
                Kapasiteye atanan talep ile ağırlıklı
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-label">
                Nüfusun %90’ının süresi <RouteIcon size={17} />
              </div>
              <div className="stat-number">
                {decimal(stats?.p90Minutes)}
                <span>dk</span>
              </div>
              <div className="stat-caption">
                Uzun yolculukları görünür kılar
              </div>
            </div>
          </div>
          {result && (
            <p className={dirty ? "dirty-note" : "small-note"} role="status">
              Gösterilen hesap:{" "}
              {result.scenario.mode === "transit"
                ? `EGO · ${displayedProfile}`
                : "Araba"}
              {` · ${result.scenario.threshold} dk · il %${result.scenario.coverageTarget} · ilçe %${result.scenario.districtFloor}.`}
              {capacity && " Bu tesis sayısı, kanıtlanmış asgari ihtiyaç değildir."}
              {dirty && " Girdi değişiklikleri henüz bu sonuçlara uygulanmadı."}
              {capacity?.optimalityScope === "all_candidate_allocation_edges"
                ? " Maliyet açığı, örneklenen adayların bütün talep bağlantılarının bulunduğu probleme aittir; Ankara'nın her olası konumu için kanıt değildir."
                : result.searchScope &&
                  ` Maliyet açığı, her yapı izi sınıfından en yakın ${result.searchScope.nearestCandidatesPerFootprintClass} adayla sınırlı aramaya aittir; bütün aday bağlantıları için küresel optimalite kanıtı değildir.`}
            </p>
          )}
          {capacity && (
            <section
              className="capacity-strip"
              aria-label="Kapasite ve maliyet sonuçları"
            >
              <div>
                <span>PLANLANAN YATAK</span>
                <strong>{number(capacity.totalBeds)}</strong>
                <small>
                  Tanımlı kapasitenin %{decimal(capacity.bedUtilizationPercent)}
                  ’i kullanılıyor
                </small>
              </div>
              <div>
                <span>PLANLANAN HEKİM</span>
                <strong>{number(capacity.totalDoctors)}</strong>
                <small>
                  Temas kapasitesinin %
                  {decimal(capacity.doctorUtilizationPercent)}’i
                </small>
              </div>
              <div>
                <span>YILLIK MALİYET GÖSTERGESİ</span>
                <strong>
                  {decimal(capacity.annualEquivalentCostTRY / 1e9)}{" "}
                  <em>mr ₺</em>
                </strong>
                <small>Yıllıklaştırılmış bina + işletme · 2024 TL</small>
              </div>
              <button onClick={() => setModal("method")}>
                <Info size={18} />
                <span>
                  <b>Bu sayıların arkasında ne var?</b>
                  <small>Resmî veri, formüller ve varsayımlar</small>
                </span>
                <ArrowUpRight size={17} />
              </button>
            </section>
          )}
          <div className="map-toolbar">
            <div className="search-wrap">
              <Search size={16} />
              <input
                aria-label="Mahalle ara"
                placeholder="Mahalle veya ilçe ara"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              {search.length > 1 && (
                <div className="search-results">
                  {searchMatches.length ? (
                    searchMatches.map((d) => (
                      <button key={d.id} onClick={() => selectDemand(d)}>
                        <MapPin size={15} />
                        <div>
                          <b>{title(d.name)}</b>
                          <small>
                            {title(d.district)} · {number(d.population)} kişi
                          </small>
                        </div>
                      </button>
                    ))
                  ) : (
                    <p>Eşleşen mahalle bulunamadı.</p>
                  )}
                </div>
              )}
            </div>
            <label className="district-select">
              <select
                aria-label="Haritada ilçe"
                value={district}
                onChange={(e) => setDistrict(e.target.value)}
              >
                <option value="">Haritada ilçe bul</option>
                {data?.districts.map((d) => (
                  <option key={d.id} value={d.id}>
                    {title(d.name)}
                  </option>
                ))}
              </select>
              <ChevronDown size={14} />
            </label>
            <span className="map-data-tag">
              <span />
              {displayedScenario.mode === "transit"
                ? "EGO · kalkış tarifesi + tahmini geçiş"
                : "OSM · yol ağı"}
            </span>
          </div>
          {error && (
            <div className="error-banner" role="alert">
              <AlertTriangle size={18} />
              {error}
              <button onClick={() => window.location.reload()}>
                Tekrar dene
              </button>
            </div>
          )}
          {result && !stats && (
            <div className="error-banner" role="status">
              <AlertTriangle size={19} />
              <div>
                <b>{result.reason}</b>
                {result.geographicCertificate?.minimumCountLowerBound !=
                  null && (
                  <p>
                    Kapasite sınırsızken gerekli coğrafi alt sınır:{" "}
                    {Math.ceil(
                      result.geographicCertificate.minimumCountLowerBound -
                        1e-6,
                    )}{" "}
                    tesis. Kullanılan bütün adaylar ve süre içindeki bütün ağ
                    bağlantılarıyla hesaplandı.
                  </p>
                )}
                {result.maximumCoveragePercent !== undefined && (
                  <p>
                    Tüm adaylar açılsa bile ulaşılabilen üst sınır: %
                    {decimal(result.maximumCoveragePercent)}.
                    {result.limitingDistricts?.length
                      ? ` İlçe hedefini sınırlayanlar: ${result.limitingDistricts
                          .slice(0, 5)
                          .map(
                            (d) =>
                              `${title(d.name)} (%${decimal(d.maximumPercent)})`,
                          )
                          .join(", ")}.`
                      : ""}
                  </p>
                )}
                {result.transitEvidence && (
                  <p>{result.transitEvidence.scope}</p>
                )}
              </div>
            </div>
          )}
          {(scenario.mode === "transit" ||
            displayedScenario.mode === "transit") && (
            <div className="transit-banner">
              <Info size={16} />
              <span>
                <b>
                  {result ? "Son hesaplanan: " : "Seçili profil: "}
                  {displayedScenario.mode === "transit"
                    ? `EGO · ${displayedProfile}`
                    : "Araba"}
                  .
                </b>{" "}
                {result &&
                  (result.scenario.mode !== scenario.mode ||
                    (scenario.mode === "transit" &&
                      result.scenario.transitProfile !==
                        scenario.transitProfile)) && (
                    <strong>
                      Bekleyen seçim:{" "}
                      {scenario.mode === "transit"
                        ? `EGO · ${transitProfileLabels[scenario.transitProfile]}`
                        : "Araba"}
                      ; yeniden hesaplama gerekli.{" "}
                    </strong>
                  )}
                Tek başlangıç saati sınanır; günün tamamında hizmet garantisi
                vermez. Resmî kalkışlar kullanılır; ara durak zamanları tahmin
                edilir. Eksik sefer/konum verisi, hizmet yokluğu sayılmaz.
                {data?.metadata.transitDataQuality && (
                  <small className="transit-coverage">
                    Katalogdaki{" "}
                    {data.metadata.transitDataQuality.officialRouteCount}{" "}
                    yön/varyantın{" "}
                    {data.metadata.transitDataQuality.routedRouteCount} adedi
                    kullanılabiliyor.
                    {!!data.metadata.transitDataQuality.reviewedServiceEvents?.appliedCount && (
                      <> {data.metadata.transitDataQuality.reviewedServiceEvents.appliedCount} özel sefer kaydı,
                        kaynakla eşleştirilmiş yön ve açık süre varsayımlarıyla eklendi.</>
                    )}
                  </small>
                )}
              </span>
              <button onClick={() => setModal("method")}>Ayrıntılar</button>
            </div>
          )}
          <div className="map-area">
            {data ? (
              <AnkaraMap
                data={data}
                result={result}
                route={route}
                onDemand={selectDemand}
                focus={focus}
                district={district}
              />
            ) : (
              <div className="loading-map">
                <LoaderCircle className="spin" />
                <b>Ankara verileri hazırlanıyor</b>
              </div>
            )}
            {busy && (
              <div className="calculation-pill" role="status">
                <LoaderCircle size={17} className="spin" /> Kapasite, maliyet ve
                yolculuk süresi hesaplanıyor…
              </div>
            )}
            {selectedDemand && (
              <section className="route-card">
                <button
                  className="close-route"
                  aria-label="Güzergâhı kapat"
                  onClick={() => {
                    routeVersion.current++;
                    setSelectedDemand(null);
                    setRoute(null);
                    setRouteBusy(false);
                  }}
                >
                  <X size={16} />
                </button>
                <span className="eyebrow">MAHALLEDEN HASTANEYE</span>
                <h3>{title(selectedDemand.name)}</h3>
                <p>
                  {title(selectedDemand.district)} ·{" "}
                  {number(selectedDemand.population)} kişi
                </p>
                {selectedAssignment && (
                  <div className="allocation-list">
                    <b>
                      Yıllık talebin %
                      {decimal(selectedAssignment.servedFraction * 100)}’i
                      atandı
                    </b>
                    {selectedAssignment.allocations.map((a) => (
                      <button
                        key={a.candidateId}
                        disabled={routeBusy}
                        onClick={() =>
                          void selectDemand(selectedDemand, a.candidateId)
                        }
                      >
                        <span>
                          {title(
                            result?.selected?.find(
                              (c) => c.id === a.candidateId,
                            )?.name || "",
                          )}{" "}
                          · %{decimal(a.fraction * 100)}
                        </span>
                        <span>
                          {decimal(a.minutes)} dk <ArrowUpRight size={12} />
                        </span>
                      </button>
                    ))}
                    {selectedAssignment.allocations.length > 1 && (
                      <small>
                        İlk gösterilen yol en büyük talep payının atandığı
                        tesise aittir. Diğer payların yolunu seçebilirsiniz.
                      </small>
                    )}
                  </div>
                )}
                {routeBusy ? (
                  <div className="route-loading">
                    <LoaderCircle size={15} className="spin" /> Yol ağı
                    üzerinden güzergâh getiriliyor…
                  </div>
                ) : route ? (
                  <>
                    <div className="route-time">
                      {decimal(route.minutes)}
                      <span>dk</span>
                      <ArrowRight size={18} />
                      <b>{title(route.candidate)}</b>
                    </div>
                    {route.boardings.length > 0 && (
                      <div className="route-lines">
                        {route.boardings.map((b, i) => (
                          <span
                            key={i}
                            title={`${b.stop} · bekleme ${decimal(b.waitMinutes)} dk`}
                          >
                            {b.route}
                            {b.departureTime ? ` · ${b.departureTime}` : ""}
                          </span>
                        ))}
                        <small>
                          {Math.max(0, route.boardings.length - 1)} aktarma
                        </small>
                      </div>
                    )}
                    <small className="route-footnote">
                      {result?.scenario.mode === "transit" &&
                        `Bu rota: ${transitProfileLabels[result.scenario.transitProfile]}. `}
                      {route.note}{" "}
                      {result?.scenario.mode === "transit"
                        ? "Bekleme seçilen saate göre hesaplanır; ara durak geçişleri tahminidir."
                        : "Canlı trafik kullanılmaz."}
                    </small>
                    {[...new Set(route.boardings.map((b) => b.timingWarning).filter(Boolean))].map((warning) => (
                      <small className="route-footnote" key={warning}>{warning}</small>
                    ))}
                  </>
                ) : (
                  <p className="route-footnote">
                    {routeError ||
                      "Önce yerleşimi hesaplayın; ardından bu mahalleden önerilen hastaneye giden yolu görün."}
                  </p>
                )}
              </section>
            )}
          </div>
          <div className="map-footer">
            <div>
              <span className="live-dot" />
              <span>
                {data
                  ? `${number(data.metadata.matchedNeighborhoodCount)} mahalle · nüfusun %${decimal((data.metadata.matchedPopulation / data.metadata.provincePopulation) * 100, 2)}’si konumlandırıldı`
                  : "Veriler yükleniyor"}
              </span>
              <button
                onClick={() => setModal("sources")}
                aria-label="Veri kapsamı hakkında bilgi"
              >
                <Info size={14} />
              </button>
            </div>
            <button
              onClick={() => setDistrictPanel(!districtPanel)}
              disabled={!stats}
            >
              İlçe bazında sonuçlar{" "}
              <ChevronDown
                size={15}
                className={districtPanel ? "rotate" : ""}
              />
            </button>
          </div>
          {capacity && (
            <section className="capacity-explanation">
              <div>
                <span className="eyebrow">ERİŞİM + HİZMET KAPASİTESİ</span>
                <h3>Yakın olsun. Yükü de karşılasın.</h3>
                <p>
                  {decimal(capacity.annualVisitsDemand / 1e6, 2)} milyon tahmini
                  yıllık başvurunun{" "}
                  {decimal(capacity.annualVisitsServed / 1e6, 2)} milyonu süre
                  ve kapasite sınırları içinde atanıyor. Bu bir başvuru
                  tahminidir; tekil hasta sayısı değildir.
                </p>
              </div>
              <div className="tradeoff-summary">
                <b>Yıllık maliyet → daha kısa yol</b>
                <p>
                  İlk çözüm: {decimal(capacity.referenceCostTRY / 1e9)} mr ₺ ·{" "}
                  {decimal(capacity.referenceMeanMinutes)} dk
                </p>
                <p>
                  Son çözüm: {decimal(capacity.annualEquivalentCostTRY / 1e9)}{" "}
                  mr ₺/yıl · {decimal(stats?.meanMinutes)} dk
                </p>
                <small>
                  Aynı toplam talep · bütçe tavanı{" "}
                  {decimal(capacity.budgetLimitTRY / 1e9)} mr ₺.{" "}
                  {capacity.travelImprovementPercent > 0.01
                    ? `Süre %${decimal(capacity.travelImprovementPercent)} azaldı.`
                    : "Süre sınırında daha kısa geçerli çözüm bulunamadı."}
                </small>
                <small>
                  Süre aşaması açığı (
                  {result
                    ? allocationScopeLabel(result)
                    : "kayıtlı arama kapsamında"}
                  ):{" "}
                  {capacity.travelStageGap == null
                    ? "kanıt sınırı mevcut değil"
                    : `%${decimal(capacity.travelStageGap * 100)}`}
                  . Çözücünün amaç değeri ile alt sınırı arasındaki farktır;
                  beklenen iyileşme yüzdesi değildir.{" "}
                  {capacity.optimalityScope === "all_candidate_allocation_edges"
                    ? "Örneklenen adayların bütün talep bağlantılarının bulunduğu probleme aittir; sürekli coğrafyada küresel optimalite kanıtı değildir."
                    : result?.searchScope
                      ? `Her yapı izi sınıfından en yakın ${result.searchScope.nearestCandidatesPerFootprintClass} aday bağlantısıyla sınırlı probleme aittir; bütün aday bağlantıları için küresel optimalite kanıtı değildir.`
                      : "Kayıtlı aday bağlantılarına aittir; bütün aday bağlantıları için küresel optimalite kanıtı değildir."}
                </small>
                <small>
                  Bina yatırımı {decimal(capacity.constructionCostTRY / 1e9)} mr
                  ₺; işletme {decimal(capacity.annualOperatingCostTRY / 1e9)} mr
                  ₺/yıl. Aralık 2024 TL; cihaz, arsa ve dış altyapı yatırımları
                  hariç.
                </small>
              </div>
            </section>
          )}
          <StageComparison result={result} />
          {data && <Suspense fallback={<p>Yakın saatler planı yükleniyor…</p>}><WindowPlan data={data} /></Suspense>}
          {data && (
            <>
              <Benchmark
                busy={busy}
                packageId={data.metadata.transitPackageId}
                planningVersion={data.healthPlanning.version}
                run={(s) => {
                  setScenario(s);
                  void solve(s);
                }}
              />
              <Robustness packageId={data.metadata.transitPackageId} />
            </>
          )}
          {data && <details className="joint-details"><summary>Önceki dört başlangıç deneyi ve karşılaştırmalar</summary>
            <Suspense fallback={<p>Ortak plan yükleniyor…</p>}><JointPlan data={data} /></Suspense></details>}
          {districtPanel && result?.districts && (
            <section className="district-results">
              <div className="results-intro">
                <h3>Her ilçe görünür.</h3>
                <p>
                  Payda her ilçenin resmî nüfusudur. Eşleşmeyen nüfus
                  kapsanmamış kabul edilir.
                </p>
              </div>
              <div className="district-grid">
                {result.districts.map((d) => (
                  <button key={d.id} onClick={() => setDistrict(d.id)}>
                    <span>{title(d.name)}</span>
                    <strong>%{decimal(d.coveragePercent)}</strong>
                    <i style={{ width: `${d.coveragePercent}%` }} />
                  </button>
                ))}
              </div>
              {result.existingComparison && (
                <div className="comparison-note">
                  <b>Mevcut envanterle erişim karşılaştırması:</b> OSM’deki{" "}
                  {result.existingComparison.hospitalCount} hastane için aynı
                  sürede kapsama %
                  {decimal(result.existingComparison.coveragePercent)}. Hastane
                  türleri ve kapasiteleri eşdeğer olmadığı için bu sayı yeni
                  yerleşimin maliyet üstünlüğünü kanıtlamaz.
                </div>
              )}
            </section>
          )}
        </main>
      </div>
      {modal && data && (
        <Modal kind={modal} data={data} close={() => setModal(null)} />
      )}
      <footer className="mobile-footer">
        ERİŞİM · Ankara Sağlık Yerleşim Laboratuvarı
      </footer>
    </div>
  );
}
