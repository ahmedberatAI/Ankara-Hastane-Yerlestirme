import savedReport from "../data/processed/transport-relaxation-results.json";

type Report = {
  transitPackageId: string;
  planningVersion: string;
  status: string;
  witnessFound: boolean;
  hospitalLimit: number;
  hospitalCount: number;
  beds: number;
  doctors: number;
  withinHospitalLimit: boolean;
  withinOriginalTransitBudget: boolean;
  annualEquivalentCostTRY: number;
  originalTransitBudgetTRY: number;
  resourcesSharedAcrossProfiles: boolean;
  annualDemandCountedOnce: boolean;
  sameHealthScenarioParameters: { coverageTarget: number; districtFloor: number };
  profiles: { profile: string; coveragePercent: number; minimumDistrictCoveragePercent: number }[];
};

const profiles = ["weekday-0800", "weekday-1000", "saturday-1000", "sunday-1000"];
const fmt = (value: number, digits = 0) =>
  value.toLocaleString("tr-TR", { maximumFractionDigits: digits });

export function TransportRelaxationContent({ report, packageId, planningVersion }: {
  report: Report;
  packageId?: string;
  planningVersion: string;
}) {
  if (!packageId || report.transitPackageId !== packageId ||
      report.planningVersion !== planningVersion || report.hospitalLimit !== 91 ||
      report.sameHealthScenarioParameters.coverageTarget !== 95 ||
      report.sameHealthScenarioParameters.districtFloor !== 80) {
    return <p className="benchmark-sensitivity" role="status">
      Ulaşımdan bağımsız kapasite kontrolü güncelleniyor; kayıtlı veri ve model sürümleri eşleşmiyor.
    </p>;
  }
  const complete = report.profiles.length === 4 &&
    new Set(report.profiles.map((row) => row.profile)).size === 4 &&
    report.profiles.every((row) => profiles.includes(row.profile) &&
      Number.isFinite(row.coveragePercent) && row.coveragePercent >= 95 - 1e-6 &&
      Number.isFinite(row.minimumDistrictCoveragePercent) && row.minimumDistrictCoveragePercent >= 80 - 1e-6);
  const validated = complete && report.witnessFound === true && report.status === "witness_validated" &&
    report.withinHospitalLimit === true && report.withinOriginalTransitBudget === true &&
    Number.isInteger(report.hospitalCount) && report.hospitalCount > 0 && report.hospitalCount <= 91 &&
    Number.isInteger(report.beds) && report.beds > 0 && Number.isInteger(report.doctors) && report.doctors > 0 &&
    Number.isFinite(report.annualEquivalentCostTRY) && report.annualEquivalentCostTRY >= 0 &&
    Number.isFinite(report.originalTransitBudgetTRY) && report.originalTransitBudgetTRY > 0 &&
    report.annualEquivalentCostTRY <= report.originalTransitBudgetTRY + 1 &&
    report.resourcesSharedAcrossProfiles === true && report.annualDemandCountedOnce === true;
  return <details className="robustness-details transport-relaxation">
    <summary>Kapasiteyi ulaşım etkisinden ayır</summary>
    {validated ? <>
      <p><b>Ulaşım kısıtları kaldırıldığında {fmt(report.hospitalCount)} tesisli uygun bir plan var.</b>{" "}
        {fmt(report.beds)} yatak ve {fmt(report.doctors)} hekim, il genelinde %95 ve her ilçede %80 talep hedefini karşılıyor.
        Aynı kaynaklar ve atamalar dört alternatif profilde korunuyor; yıllık talep ve gider bir kez sayılıyor.</p>
      <p>Yıllık eşdeğer maliyet {fmt(report.annualEquivalentCostTRY / 1e9, 3)} milyar TL;
        kayıtlı EGO planının {fmt(report.originalTransitBudgetTRY / 1e9, 3)} milyar TL sınırının altında.
        Tutarlar yaklaşık Aralık 2024 fiyatlarıyla, aynı kapasite ve maliyet varsayımlarına dayanıyor.</p>
      <p>Bu tanıda bütün konumlandırılmış mahalle–aday çiftleri erişilebilir sayılır; yolculuk süresi, hat, takvim ve aktarma kısıtları kaldırılır.
        Yüksek EGO sayısı yalnız toplam yatak ve hekim ihtiyacıyla açıklanamıyor.
        <b> Gerçek EGO ağıyla 91 hastanenin yeterli olduğu veya bu planın minimum tesis sayısını verdiği kanıtlanmıyor.</b></p>
    </> : <p>Bu kayıtla ulaşım kısıtları kaldırılmış modelde uygun bir tanık doğrulanamadı.
      Başka yerleşimler aranmadığı için 91 tesisin imkânsız olduğu sonucu çıkarılamaz.</p>}
    <small>Kaydedilmiş %95/%80 tanısıdır; canlı ayarlarla değişmez. Sağlık kapasitesinin klinik gerçekçiliğini ayrıca doğrulamaz.</small>
  </details>;
}

export default function TransportRelaxation(props: { packageId?: string; planningVersion: string }) {
  return <TransportRelaxationContent {...props} report={savedReport} />;
}
