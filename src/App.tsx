import { useEffect, useMemo, useRef, useState } from "react";
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
  Check,
  AlertTriangle,
  ExternalLink,
  Database,
  Route as RouteIcon,
} from "lucide-react";
import AnkaraMap from "./Map";
import type {
  Dataset,
  Scenario,
  Result,
  Demand,
  Candidate,
  Route,
  Mode,
} from "./types";

const initial: Scenario = {
  mode: "car",
  threshold: 30,
  coverageTarget: 95,
  districtFloor: 80,
  trafficFactor: 1,
};
const number = (n: number) => n.toLocaleString("tr-TR");
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
        <div className="method-content">
          <p className="lead">
            Önce hedeflenen erişimi sağlayan hastane sayısını azaltıyoruz. Sonra
            aynı sayıyla daha fazla kişiye erişiyor, koşulları koruyarak
            yolculuk süresini iyileştiriyoruz.
          </p>
          <div className="method-steps">
            <article>
              <span>01</span>
              <h3>Nüfusun erişimi</h3>
              <p>
                Bir mahallenin temsil noktasından hastaneye yolculuk seçtiğiniz
                süreyi aşmıyorsa nüfusu kapsanmış sayılır.
              </p>
            </article>
            <article>
              <span>02</span>
              <h3>En az eşdeğer hastane</h3>
              <p>
                İl geneli hedef ve her ilçenin erişim tabanı birlikte sağlanır.
                Her yeni hastanenin maliyeti bir birim kabul edilir.
              </p>
            </article>
            <article>
              <span>03</span>
              <h3>Daha kısa yolculuk</h3>
              <p>
                Sayı sabit tutularak kapsama artırılır. Ardından kapsama
                hedeflerini bozmayan iki tur yer değişimi ile süre
                iyileştirilir.
              </p>
            </article>
          </div>
          <div className="formula">
            <span>ANA GÖSTERGE</span>
            <strong>
              Hedef sürede erişen nüfus / Ankara’nın toplam nüfusu
            </strong>
            <p>
              Konumu eşleşmeyen {number(data.metadata.unlocatedPopulation)} kişi
              toplamdan çıkarılmaz; kapsanmamış kabul edilir.
            </p>
          </div>
          <h3>Neden bu metrik?</h3>
          <p>
            Yalnızca ortalama süreyi azaltmak küçük ve uzak ilçeleri geride
            bırakabilir. Nüfus ağırlıklı kapsama, ilçe tabanı ve en az tesis
            hedefi, maliyet ile erişimi anlaşılır şekilde bağlar.{" "}
            <a
              href="https://www.who.int/tools/accessmod-geographic-access-to-health-care"
              target="_blank"
              rel="noreferrer"
            >
              WHO AccessMod
            </a>{" "}
            erişimi belirli sürede hizmete ulaşabilen nüfusla inceler. Tesis
            sayısı ve kapsama ilişkisi{" "}
            <a
              href="https://doi.org/10.1111/j.1435-5597.1974.tb00902.x"
              target="_blank"
              rel="noreferrer"
            >
              Church & ReVelle’nin yer seçimi yaklaşımına
            </a>{" "}
            dayanır.
          </p>
          <div className="note-block">
            <Info size={20} />
            <div>
              <b>30 dakika, %95 ve %80 birer planlama tercihidir.</b>
              <p>
                Bunlar evrensel sağlık standardı veya klinik güvenlik sınırı
                değildir. Farklı eşikleri karşılaştırın. Kapasite, yatak,
                personel ve gerçek yatırım bedeli bu ilk modelde yoktur.
              </p>
            </div>
          </div>
          <h3>İki ulaşım modu, iki veri düzeyi</h3>
          <p>
            <b>Araba:</b> gerçek yol bağlantıları ve tek yönler kullanılır.
            Hızlar yol sınıfından tahmin edilir. Canlı trafik ve dönüş yasakları
            henüz modellenmez; 3 dakika park/giriş payı eklenir.
          </p>
          <p>
            <b>EGO ağ senaryosu:</b> {number(data.metadata.transitRoutes || 0)}{" "}
            yönlü OSM hat kaydı; gerçek güzergâh geometrisi, yürüyüş
            bağlantıları ve aktarmalar kullanılır. Otobüs beklemesi 8, raylı
            sistem 4 dakika; otobüs hızı en fazla 28, raylı sistem hızı 40 km/sa
            varsayılır. Durak başına 25 saniye eklenir. İlk/son yürüyüş en fazla
            15, duraklar arası aktarma yürüyüşü 5 dakikadır. Kısa mesafede
            yalnız yürüyüş de mümkündür. Tüm hatların çalıştığı varsayılır;
            sefer takvimi, gerçek bekleme ve aktarma sayısı sınırı yoktur. Bu
            mod resmî tarifeli EGO hesabı değildir.
          </p>
          <h3>“Optimal” tam olarak ne demek?</h3>
          <p>
            Yalnızca {number(data.metadata.candidateCount)} ayrık aday ve seçili
            ağ varsayımları içinde en az hastane sayısı için kullanılır. Süre
            sınırında kanıt tamamlanmazsa sonuç “geçerli çözüm” olarak
            işaretlenir ve optimalite açığı gösterilir. Ortalama süre için
            global optimum iddiası yoktur.
          </p>
          <p>
            Her mahalle tek temsil noktasıdır; tüm sakinlerin aynı noktadan
            çıktığı kabul edilir. Hastaneler 45 metre yarıçaplı örnek yapı
            alanları olarak modellenir. Mevcut binalar yerleşimi engellemez; OSM
            yolları tahmini genişlikleriyle, yüzey ray hatları da koridorlarıyla
            dışlanır. Kesikli giriş bağlantıları varsayımsaldır. Sonraki aşama:
            nüfus ızgarası, resmî mahalle sınırları, kapasite, yol dönüşleri ve
            güncel GTFS.
          </p>
        </div>
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
    !!result && JSON.stringify(result.scenario) !== JSON.stringify(scenario);
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
  async function selectDemand(demand: Demand) {
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
    if (assignment.minutes === null) {
      setRouteError(
        "Bu senaryoda mahalleden seçili hastanelere ağ bağlantısı bulunmuyor.",
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
          candidateId: assignment.candidateId,
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
    a.download = `ankara-${result.scenario.mode}-${result.scenario.threshold}dk.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
  const stats = result?.metrics;
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
              Doğru konumlarda, daha az hastaneyle daha fazla insana ulaşın.
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
                : "Tarifesiz ağ senaryosu · bekleme ve hızlar varsayım"}
            </p>
          </div>
          <div className="control-section settings">
            <div className="label-row">
              <label>Hedeflerinizi belirleyin</label>
              <span>02</span>
            </div>
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
                Ankara genelinde erişim{" "}
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
                Her ilçede en az erişim{" "}
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
                ? "Hedefler, ilçe dengesi ve seyahat süreleri birlikte çözülüyor."
                : dirty
                  ? "Parametreler değişti. Harita son hesaplanan senaryoyu gösteriyor."
                  : "Hastane başına 1 maliyet birimi · sıfırdan yerleşim"}
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
              <b>Neden bu metrik?</b>
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
                      <small>{title(c.district)}</small>
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
              TÜİK 2025 + OpenStreetMap
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
                Önerilen hastane <Cross size={17} />
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
                {result?.status === "optimal" ? (
                  <>
                    <Check size={13} /> Aday kümesinde minimum sayı
                  </>
                ) : result?.status === "feasible" ? (
                  `Geçerli çözüm · açık %${decimal((result.gap ?? 0) * 100)}`
                ) : (
                  "En az maliyet birimi hedefi"
                )}
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-label">
                Hedef sürede erişim <Users size={17} />
              </div>
              <div className="stat-number">
                {stats ? `%${decimal(stats.coveragePercent)}` : "—"}
              </div>
              <div className="stat-caption">
                {stats
                  ? `${number(stats.coveredPopulation)} / ${number(data!.metadata.provincePopulation)} kişi`
                  : "Toplam nüfus üzerinden hesaplanır"}
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
                Hesaplanabilen nüfusla ağırlıklı
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
              {scenario.mode === "transit"
                ? "EGO · varsayımsal süreler"
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
              </div>
            </div>
          )}
          {scenario.mode === "transit" && (
            <div className="transit-banner">
              <Info size={16} />
              <span>
                <b>EGO ağ senaryosu.</b> Sefer tarifesi yok. Yürüyüş ve güzergâh
                ağdan; bekleme ve hızlar varsayımdan gelir.
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
                <LoaderCircle size={17} className="spin" /> En az hastane sayısı
                ve erişim dengesi hesaplanıyor…
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
                          <span key={i}>{b.route}</span>
                        ))}
                        <small>
                          {Math.max(0, route.boardings.length - 1)} aktarma
                        </small>
                      </div>
                    )}
                    <small className="route-footnote">
                      Kesikli çizgiler yürüyüş veya varsayılan giriş
                      bağlantısıdır.{" "}
                      {result?.scenario.mode === "transit"
                        ? "Beklemeler senaryo varsayımıdır."
                        : "Canlı trafik kullanılmaz."}
                    </small>
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
