import { useEffect, useState } from "react";
import type { Scenario, Result } from "./types";
import { transitProfileLabels } from "./types";

type Report = {
  date: string;
  planningVersion: string;
  transitPackageId: string;
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
  transitAudit?: {
    legacyLowerBound: number;
    walkingCorrectionLowerBound: number;
    officialRoutes: number;
    modeledRoutes: number;
    withoutDistrictFloorLowerBound: number;
    note: string;
  };
};
const fmt = (n: number) =>
  n.toLocaleString("tr-TR", { maximumFractionDigits: 1 });

export default function Benchmark({
  run,
  busy,
  packageId,
}: {
  run: (s: Scenario) => void;
  busy: boolean;
  packageId?: string;
}) {
  const [report, setReport] = useState<Report | null>(null);
  useEffect(() => {
    fetch("/api/benchmark-91")
      .then((r) => (r.ok ? r.json() : null))
      .then(setReport)
      .catch(() => {});
  }, []);
  if (!report) return null;
  if (!packageId || report.transitPackageId !== packageId) {
    return (
      <section className="benchmark" role="status">
        <h3>91 hastane karşılaştırması güncelleniyor</h3>
        <p>
          Kayıtlı deney ile uygulamanın ulaşım veri sürümü eşleşmiyor. Bu
          kayıtların sayıları güncel sonuç olarak gösterilemez.
        </p>
      </section>
    );
  }
  return (
    <section className="benchmark" aria-label="91 hastane karşılaştırma deneyi">
      <div className="benchmark-heading">
        <span className="eyebrow">AYNI KAPSAMA HEDEFLERİ</span>
        <h3>91 hastane yeterli mi?</h3>
        <p>
          En fazla 91 tesis · il genelinde %95 · her ilçede en az %80. Süre
          eşikleri araba için 30, EGO için 45 dakikadır. Sıfırdan yerleşim. Her
          EGO kartı yalnız belirtilen başlangıç saatini ve o profil için ayrı
          yerleşimi sınar; aynı hastane planının tüm saatlerde çalıştığı
          anlamına gelmez.
        </p>
      </div>
      <div className="benchmark-cases">
        {report.cases.map((c) => (
          <article key={c.scenario.mode + c.scenario.transitProfile}>
            <span>
              {c.scenario.mode === "car"
                ? "ARABA · 30 DK"
                : `EGO · 45 DK · ${transitProfileLabels[c.scenario.transitProfile]}`}
            </span>
            <b>
              {c.metrics
                ? "Hedefler sağlandı"
                : c.status === "infeasible"
                  ? "Bu veriyle 91 sınırı aşılır"
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
                  ? `Kapasite sınırsızken coğrafi alt sınır ${Math.ceil(c.geographicCertificate.minimumCountLowerBound - 1e-6)} tesis. Eksik hizmet ve tahmini ara durak süreleri sonucu etkileyebilir.`
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
      {report.transitAudit && (
        <p className="benchmark-sensitivity">
          <b>291 neden değişti?</b> Eski ağın alt sınırı{" "}
          {Math.ceil(report.transitAudit.legacyLowerBound - 1e-6)} idi. Yalnız
          doğrudan yürüyüşteki 15 dakika kesmesi düzeltilince{" "}
          {Math.ceil(report.transitAudit.walkingCorrectionLowerBound - 1e-6)}{" "}
          olur. Yukarıdaki EGO deneyleri buna resmî kalkış saatlerini de ekler.{" "}
          {report.transitAudit.note} Her ilçede %80 koşulu kaldırılan ayrı hafta
          içi 10.00 kontrolünde coğrafi alt sınır{" "}
          {Math.ceil(report.transitAudit.withoutDistrictFloorLowerBound - 1e-6)}{" "}
          olur. Bu son kontrol yatak, hekim ve maliyet içermediği için 91
          tesisin yeterliliğini kanıtlamaz.
        </p>
      )}
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
