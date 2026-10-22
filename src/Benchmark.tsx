import { useEffect, useState } from "react";
import type { Scenario, Result } from "./types";

type Report = {
  date: string;
  planningVersion: string;
  note: string;
  cases: Pick<
    Result,
    | "scenario"
    | "status"
    | "hospitalCount"
    | "metrics"
    | "capacity"
    | "geographicCertificate"
  >[];
  sensitivity?: { summary: { hospitalCount: number; totalDoctors: number } };
};
const fmt = (n: number) =>
  n.toLocaleString("tr-TR", { maximumFractionDigits: 1 });

export default function Benchmark({
  run,
  busy,
}: {
  run: (s: Scenario) => void;
  busy: boolean;
}) {
  const [report, setReport] = useState<Report | null>(null);
  useEffect(() => {
    fetch("/api/benchmark-91")
      .then((r) => (r.ok ? r.json() : null))
      .then(setReport)
      .catch(() => {});
  }, []);
  if (!report) return null;
  return (
    <section className="benchmark" aria-label="91 hastane karşılaştırma deneyi">
      <div className="benchmark-heading">
        <span className="eyebrow">AYNI HEDEFLERLE KONTROLLÜ DENEY</span>
        <h3>91 hastane yeterli mi?</h3>
        <p>
          En fazla 91 tesis · il genelinde %95 · her ilçede en az %80. Sıfırdan
          yerleşim.
        </p>
      </div>
      <div className="benchmark-cases">
        {report.cases.map((c) => (
          <article key={c.scenario.mode}>
            <span>
              {c.scenario.mode === "car"
                ? "ARABA · 30 DK"
                : "EGO AĞ SENARYOSU · 45 DK"}
            </span>
            <b>
              {c.metrics
                ? "Hedefler sağlandı"
                : c.status === "infeasible"
                  ? "91 tesisle sağlanamıyor"
                  : "Henüz sonuçlandırılamadı"}
            </b>
            {c.metrics && c.capacity ? (
              <p>
                {c.hospitalCount} tesis · {fmt(c.capacity.totalBeds)} yatak ·{" "}
                {fmt(c.capacity.totalDoctors)} hekim. Karşılanan talep %
                {fmt(c.metrics.coveragePercent)}.
              </p>
            ) : (
              <p>
                {c.geographicCertificate?.minimumCountLowerBound
                  ? `Kapasite sınırsızken bile coğrafi alt sınır ${Math.ceil(c.geographicCertificate.minimumCountLowerBound - 1e-6)} tesis. Bu ağda sadece binaları büyütmek yeterli değil.`
                  : "Süre sınırlı arama bir imkânsızlık ispatı değildir."}
              </p>
            )}
            <button
              className="text-link"
              disabled={busy}
              onClick={() => run(c.scenario)}
            >
              Bu deneyi haritada aç →
            </button>
          </article>
        ))}
      </div>
      {report.sensitivity && (
        <p className="benchmark-sensitivity">
          <b>Kadro varsayımı sonucu değiştirir.</b> Araba deneyinde üniversite
          örneklerinin 835 temas/hekim oranıyla{" "}
          {report.sensitivity.summary.hospitalCount} tesis ve{" "}
          {fmt(report.sensitivity.summary.totalDoctors)} hekim gerekiyor. Bu,
          Ankara’nın 26.798 toplam hekiminden fazladır; model mevcut kadroya
          atanabilirlik garantisi vermez.
        </p>
      )}
      <small>
        {report.note} Kayıt: {report.date}. Bu kart sabit deney kaydıdır;
        yukarıdaki canlı parametrelerle değişmez.
      </small>
    </section>
  );
}
