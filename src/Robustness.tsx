import { useEffect, useState } from "react";
import { transitProfileLabels } from "./types";
import type { Scenario, TransitProfile } from "./types";

type Certificate = {
  status: "optimal" | "bounded" | "infeasible";
  minimumCountLowerBound: number | null;
  feasibleGeographicCount: number | null;
};
type ProfileCheck = {
  profile: TransitProfile;
  status:
    | "targets_met"
    | "province_target_not_met"
    | "district_targets_infeasible"
    | "fixed_cost_exceeds_budget"
    | "inconclusive";
  targetsMet: boolean | null;
  maximumCoveragePercent: number | null;
  populationShortfall?: number;
  annualEquivalentCostTRY?: number;
  annualBudget?: {
    enforced: boolean;
    limitTRY: number | null;
    fixedCostTRY: number | null;
    variableCostPerResidentTRY: number | null;
    scope: string;
  };
  withoutDistrictTargets?: { maximumCoveragePercent: number } | null;
};
export type RobustnessReport = {
  transitPackageId: string;
  builtAt: string;
  sourcePlan: {
    transitPackageId: string;
    scenario: Scenario;
    hospitalCount: number;
    totalBeds: number;
    totalDoctors: number;
    annualBudgetLimitTRY?: number;
    sha256: string;
  };
  profiles: ProfileCheck[];
  allProfilesTargetsMet: boolean | null;
  aggregateStatus: "all_targets_met" | "some_targets_failed" | "inconclusive";
  utilization: {
    count50BedSites: number;
    countAssignedBelow1000Residents: number;
    countAssignedBelow5000Residents: number;
    medianSitePhysicalOccupancyPercent: number;
  };
  geographicDiagnostics?: {
    ruralDistricts: { id: string; name: string }[];
    ruralPopulationSharePercent: number;
    ruralProfile: TransitProfile;
    ruralDistrictFloorPercent: number;
    ruralThresholdMinutes: number;
    ruralCertificate: Certificate;
    sensitivity: {
      profile: TransitProfile;
      thresholdMinutes: number;
      districtFloorPercent: number;
      coverageTargetPercent: number;
      certificate: Certificate;
    }[];
  };
};
const fmt = (value: number, digits = 1) =>
  value.toLocaleString("tr-TR", { maximumFractionDigits: digits });
const bound = (value: number | null) =>
  value == null ? "Hesaplanamadı" : fmt(Math.ceil(value - 1e-6), 0);
const statusLabel: Record<ProfileCheck["status"], string> = {
  targets_met: "Hedefler sağlandı",
  province_target_not_met: "İl geneli hedefi sağlanmıyor",
  district_targets_infeasible: "İlçe koşulları sağlanamıyor",
  fixed_cost_exceeds_budget: "Sabit giderler bütçe tavanını aşıyor",
  inconclusive: "Henüz sonuçlandırılamadı",
};

export function RobustnessContent({
  report,
  packageId,
}: {
  report: RobustnessReport;
  packageId?: string;
}) {
  const [diagnosticProfile, setDiagnosticProfile] =
    useState<TransitProfile | null>(null);
  if (
    !packageId ||
    report.transitPackageId !== packageId ||
    report.sourcePlan.transitPackageId !== packageId
  ) {
    return (
      <section className="robustness-panel" role="status">
        <h3>Aynı planın farklı saatlerdeki testi güncelleniyor</h3>
        <p>
          Kayıtlı test güncel ulaşım veri paketiyle eşleşmiyor; önceki sayılar
          gösterilmiyor.
        </p>
      </section>
    );
  }
  const plan = report.sourcePlan;
  const scenario = plan.scenario;
  const expectedProfiles = Object.keys(transitProfileLabels);
  const complete =
    report.profiles.length === expectedProfiles.length &&
    expectedProfiles.every(
      (profile) =>
        report.profiles.filter((row) => row.profile === profile).length === 1,
    );
  const passed = report.profiles.filter(
    (row) => row.targetsMet === true && row.status === "targets_met",
  ).length;
  const unresolved = report.profiles.filter(
    (row) => row.targetsMet == null || row.status === "inconclusive",
  ).length;
  const allMet =
    complete &&
    report.allProfilesTargetsMet === true &&
    report.aggregateStatus === "all_targets_met" &&
    passed === expectedProfiles.length;
  const budgetEnforced =
    complete &&
    plan.annualBudgetLimitTRY != null &&
    report.profiles.every(
      (row) =>
        row.annualBudget?.enforced === true &&
        row.annualBudget.limitTRY != null &&
        Math.abs(row.annualBudget.limitTRY - plan.annualBudgetLimitTRY!) <=
          Math.max(1e-6, Math.abs(plan.annualBudgetLimitTRY!) * 1e-9),
    );
  const diagnostic = report.geographicDiagnostics;
  const selectedProfile = diagnosticProfile ?? scenario.transitProfile;
  const unconstrained = report.profiles.filter(
    (row) => row.withoutDistrictTargets != null,
  );
  return (
    <section
      className="robustness-panel"
      aria-label="Aynı hastane planının farklı saatlerde sınanması"
    >
      <div className="robustness-heading">
        <div>
          <span className="eyebrow">AYNI KONUM · AYNI YATAK · AYNI HEKİM</span>
          <h3>Bu hastaneler farklı saatlerde yeterli mi?</h3>
        </div>
        <span
          className={`robustness-status ${allMet && budgetEnforced ? "met" : "limited"}`}
        >
          {allMet
            ? budgetEnforced
              ? "İncelenen tüm profillerde hedefler sağlandı"
              : "Erişim ve kapasite yeterli · ortak bütçe doğrulanmadı"
            : !complete
              ? "Profil kayıtları tamamlanmamış"
              : report.aggregateStatus === "inconclusive"
                ? `Sonuç belirsiz · ${unresolved} profil sonuçlandırılamadı`
                : `${passed}/${expectedProfiles.length} profilde hedefler sağlandı${unresolved ? ` · ${unresolved} profil belirsiz` : ""}`}
        </span>
      </div>
      <p>
        Kayıtlı {transitProfileLabels[scenario.transitProfile]} planı:{" "}
        <b>
          {fmt(plan.hospitalCount, 0)} hastane,
          {` ${fmt(plan.totalBeds, 0)} yatak, ${fmt(plan.totalDoctors, 0)} hekim`}
        </b>
        . Konumlar ve kaynaklar sabit; talep bu hastaneler arasında yeniden
        atanabilir. Hedefler {scenario.threshold} dakika, il genelinde %
        {scenario.coverageTarget}, her ilçede %{scenario.districtFloor}.
      </p>
      <p>
        {budgetEnforced
          ? `Dört profilde aynı yıllık eşdeğer maliyet tavanı (${fmt(plan.annualBudgetLimitTRY! / 1e9, 2)} mr ₺/yıl) korunur. Tesis, yatak ve hekimlerin sabit giderine yeniden atanan talebin malzeme gideri eklenir.`
          : "Bu kayıtta dört profil için aynı yıllık maliyet tavanının korunduğu doğrulanamıyor; ortak bütçe altında yeterlilik sonucu çıkarılamaz."}
      </p>
      <div className="table-scroll">
        <table className="capacity-table robustness-table">
          <caption>
            Kayıtlı planın ayrı gün ve başlangıç saatlerinde sınanması
          </caption>
          <thead>
            <tr>
              <th>Başlangıç profili</th>
              <th>Aynı planın durumu</th>
              <th>En çok karşılanan talep</th>
              <th>İl hedefine kalan kişi eşdeğeri</th>
              <th>Yıllık eşdeğer maliyet</th>
            </tr>
          </thead>
          <tbody>
            {report.profiles.map((row) => (
              <tr key={row.profile}>
                <td>{transitProfileLabels[row.profile]}</td>
                <td>
                  <span
                    className={`robustness-result ${row.targetsMet === true ? "met" : "limited"}`}
                  >
                    {statusLabel[row.status]}
                  </span>
                </td>
                <td>
                  {row.maximumCoveragePercent == null
                    ? "—"
                    : `%${fmt(row.maximumCoveragePercent)}`}
                </td>
                <td>
                  {row.populationShortfall == null
                    ? "—"
                    : fmt(
                        Math.max(0, Math.ceil(row.populationShortfall - 1e-6)),
                        0,
                      )}
                </td>
                <td>
                  {row.annualEquivalentCostTRY == null
                    ? "—"
                    : `${fmt(row.annualEquivalentCostTRY / 1e9, 2)} mr ₺/yıl`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="robustness-explanation">
        İlçe koşulları veya sabit giderlerin bütçe koşulu sağlanamıyorsa ana
        kapsama yüzdesi verilmez. Her satır yıllık talebi ayrı bir erişim
        senaryosunda sınar; talep dört kez toplanmaz. Dört başlangıç saati, tüm
        gün veya yıl boyunca hizmet garantisi değildir. Talep yeniden atanırken
        akışa bağlı yıllık işletme gideri değişebilir. Mali tutarlar kısmi gider
        kalibrasyonudur; gerçek hastane bütçesi veya ihale bedeli değildir.
      </p>
      {unconstrained.length > 0 && (
        <details className="robustness-details">
          <summary>İlçe koşulları kaldırılırsa ne değişiyor?</summary>
          <p>
            Bu ayrı tanı yatak ve hekim kapasitesini korur, ilçe tabanlarını
            kaldırır.
            {budgetEnforced && " Aynı yıllık maliyet tavanı da korunur."} Asıl
            hedeflerin sağlandığı anlamına gelmez.
          </p>
          <ul>
            {unconstrained.map((row) => (
              <li key={row.profile}>
                {transitProfileLabels[row.profile]}: ilçe tabanı olmadan en çok
                %{fmt(row.withoutDistrictTargets!.maximumCoveragePercent)}{" "}
                talep.
              </li>
            ))}
          </ul>
        </details>
      )}
      <details className="robustness-details">
        <summary>Bu planda küçük tesisler ve yatak kullanımı</summary>
        <p>
          İlk kayıtlı atamada {fmt(report.utilization.count50BedSites, 0)} tesis
          50 yataklı;
          {` ${fmt(report.utilization.countAssignedBelow1000Residents, 0)}`}{" "}
          tesis 1.000'den,
          {` ${fmt(report.utilization.countAssignedBelow5000Residents, 0)}`}{" "}
          tesis 5.000'den az kişi eşdeğerine hizmet veriyor. Tesislerin fiziksel
          yatak doluluğu medyanı %
          {fmt(report.utilization.medianSitePhysicalOccupancyPercent)}.
        </p>
        <p>
          Bu medyan yatak sayısıyla ağırlıklandırılmış il doluluğu değildir.
          Düşük kullanım, erişim hedefleri ile en küçük tesis boyutunun birlikte
          incelenmesi gerektiğini gösterir; klinik uygunluğu tek başına ölçmez.
        </p>
      </details>
      {diagnostic && (
        <details className="robustness-details">
          <summary>
            Süre ve ilçe hedefi hastane sayısını nasıl etkiliyor?
          </summary>
          <p>
            Bu tabloda yatak, hekim, maliyet ve yapı çakışması kısıtları
            kaldırılır; yeni coğrafi konumlar seçilebilir. Sayılar gerçek
            ihtiyaç veya sabit planın sonucu değildir. Alt sınırın 91'i geçmesi
            bu coğrafi modelde 91'i dışlar; 91'in altına inmesi kapasite
            yeterliliğini kanıtlamaz.
          </p>
          <label className="robustness-profile">
            Coğrafi tanı profili
            <select
              value={selectedProfile}
              onChange={(event) =>
                setDiagnosticProfile(event.target.value as TransitProfile)
              }
            >
              {Object.entries(transitProfileLabels).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <div className="table-scroll">
            <table className="capacity-table robustness-table">
              <thead>
                <tr>
                  <th>Süre eşiği</th>
                  <th>Her ilçede talep</th>
                  <th>Gerekli sayı alt sınırı</th>
                  <th>Bulunan coğrafi konum</th>
                </tr>
              </thead>
              <tbody>
                {diagnostic.sensitivity
                  .filter((row) => row.profile === selectedProfile)
                  .map((row) => (
                    <tr
                      key={`${row.thresholdMinutes}-${row.districtFloorPercent}`}
                    >
                      <td>{row.thresholdMinutes} dk</td>
                      <td>%{row.districtFloorPercent}</td>
                      <td>
                        {row.certificate.status === "infeasible"
                          ? "Coğrafi hedefler sağlanamıyor"
                          : bound(row.certificate.minimumCountLowerBound)}
                      </td>
                      <td>
                        {row.certificate.feasibleGeographicCount == null
                          ? "—"
                          : fmt(row.certificate.feasibleGeographicCount, 0)}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          <p>
            Alt sınır ile bulunan sayı farklıysa minimum sayı kanıtlanmış
            değildir. Tablodaki il geneli hedefi %{scenario.coverageTarget}.
          </p>
          <p>
            Seçili kırsal ilçeler (
            {diagnostic.ruralDistricts.map((d) => d.name).join(", ")}) nüfusun %
            {fmt(diagnostic.ruralPopulationSharePercent)}'ini oluşturuyor.
            Yalnız bu ilçelerde %{diagnostic.ruralDistrictFloorPercent} erişim
            koşuluyla,
            {` ${transitProfileLabels[diagnostic.ruralProfile]}, ${diagnostic.ruralThresholdMinutes} dakika`}{" "}
            tanısında coğrafi alt sınır
            {` ${bound(diagnostic.ruralCertificate.minimumCountLowerBound)}`}.
            Bu ayrı tanıda il geneli kapsama koşulu yoktur.
          </p>
        </details>
      )}
      <small>
        Kayıtlı plan testi; yukarıdaki canlı ayarlar bu tabloyu değiştirmez.
        Eksik hizmet/konum ve tahmini ara durak zamanları sonucu etkiler. Kayıt:{" "}
        {new Date(report.builtAt).toLocaleDateString("tr-TR", {
          timeZone: "Europe/Istanbul",
        })}{" "}
        (TSİ).
      </small>
    </section>
  );
}

export default function Robustness({ packageId }: { packageId?: string }) {
  const [report, setReport] = useState<RobustnessReport | null>(null);
  useEffect(() => {
    let active = true;
    fetch("/api/robustness")
      .then((response) => (response.ok ? response.json() : null))
      .then((value) => {
        if (active) setReport(value);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);
  return report ? (
    <RobustnessContent report={report} packageId={packageId} />
  ) : null;
}
