import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const built = await build({
  entryPoints: ["src/Robustness.tsx"],
  bundle: true,
  platform: "node",
  format: "cjs",
  write: false,
  external: ["react", "react-dom/server"],
});
const module = { exports: {} };
new Function("require", "module", "exports", built.outputFiles[0].text)(
  createRequire(import.meta.url),
  module,
  module.exports,
);
const Content = module.exports.RobustnessContent;
const profiles = [
  "weekday-0800",
  "weekday-1000",
  "saturday-1000",
  "sunday-1000",
];
const fixture = () => ({
  transitPackageId: "current",
  builtAt: "2026-10-23T00:00:00Z",
  sourcePlan: {
    transitPackageId: "current",
    hospitalCount: 321,
    totalBeds: 999,
    totalDoctors: 111,
    annualBudgetLimitTRY: 2000000000,
    scenario: {
      mode: "transit",
      transitProfile: "weekday-1000",
      threshold: 45,
      coverageTarget: 95,
      districtFloor: 80,
    },
  },
  profiles: profiles.map((profile) => ({
    profile,
    status: "targets_met",
    targetsMet: true,
    maximumCoveragePercent: 95,
    populationShortfall: 0,
    annualEquivalentCostTRY: 1800000000,
    annualBudget: {
      enforced: true,
      limitTRY: 2000000000,
      fixedCostTRY: 1000000000,
      variableCostPerResidentTRY: 100,
      scope: "partial calibration",
    },
  })),
  allProfilesTargetsMet: true,
  aggregateStatus: "all_targets_met",
  utilization: {
    count50BedSites: 1,
    countAssignedBelow1000Residents: 1,
    countAssignedBelow5000Residents: 2,
    medianSitePhysicalOccupancyPercent: 31.4,
  },
});
const render = (report, packageId = "current") =>
  renderToStaticMarkup(React.createElement(Content, { report, packageId }));

let report = fixture();
let html = render(report, "different-package");
assert.match(html, /güncel ulaşım veri paketiyle eşleşmiyor/);
assert.doesNotMatch(html, /321 hastane/);

report = fixture();
Object.assign(report.profiles[3], {
  status: "inconclusive",
  targetsMet: null,
  maximumCoveragePercent: null,
  populationShortfall: undefined,
});
report.allProfilesTargetsMet = null;
report.aggregateStatus = "inconclusive";
html = render(report);
assert.match(html, /Sonuç belirsiz/);
assert.match(html, /Henüz sonuçlandırılamadı/);
assert.doesNotMatch(html, /İncelenen tüm profillerde hedefler sağlandı/);

report = fixture();
Object.assign(report.profiles[3], {
  status: "district_targets_infeasible",
  targetsMet: false,
  maximumCoveragePercent: null,
  populationShortfall: undefined,
  withoutDistrictTargets: { maximumCoveragePercent: 99.9 },
});
report.allProfilesTargetsMet = false;
report.aggregateStatus = "some_targets_failed";
html = render(report);
const mainTable = html.match(/<tbody>(.*?)<\/tbody>/s)[1];
assert.doesNotMatch(mainTable, /99,9/);
assert.match(mainTable, /İlçe koşulları sağlanamıyor/);
assert.match(html, /ilçe tabanı olmadan en çok %99,9/);
assert.match(html, /Kayıtlı plan testi/);
assert.match(html, /talep dört kez toplanmaz/);

report = fixture();
report.profiles.pop();
html = render(report);
assert.match(html, /Profil kayıtları tamamlanmamış/);
assert.doesNotMatch(html, /İncelenen tüm profillerde hedefler sağlandı/);

report = fixture();
html = render(report);
assert.match(
  html,
  /Dört profilde aynı yıllık eşdeğer maliyet tavanı \(2 mr ₺\/yıl\) korunur/,
);
assert.match(html, /1,8 mr ₺\/yıl/);
assert.match(html, /İncelenen tüm profillerde hedefler sağlandı/);

report = fixture();
delete report.profiles[1].annualBudget;
html = render(report);
assert.match(html, /ortak bütçe doğrulanmadı/);
assert.doesNotMatch(
  html,
  /İncelenen tüm profillerde hedefler sağlandı|Dört profilde aynı yıllık eşdeğer maliyet tavanı/,
);
report.profiles[1].annualBudget = { enforced: true, limitTRY: 2100000000 };
html = render(report);
assert.match(html, /ortak bütçe doğrulanmadı/);

report = fixture();
Object.assign(report.profiles[0], {
  status: "fixed_cost_exceeds_budget",
  targetsMet: false,
  maximumCoveragePercent: null,
  populationShortfall: undefined,
  annualEquivalentCostTRY: undefined,
});
report.allProfilesTargetsMet = false;
report.aggregateStatus = "some_targets_failed";
html = render(report);
assert.match(html, /Sabit giderler bütçe tavanını aşıyor/);
assert.doesNotMatch(html, /İncelenen tüm profillerde hedefler sağlandı/);
const failedBudgetRow = html
  .match(/<tbody>(.*?)<\/tbody>/s)[1]
  .match(/<tr>(.*?)<\/tr>/s)[1];
assert.match(failedBudgetRow, /<td>—<\/td><td>—<\/td><td>—<\/td>/);
console.log(
  "Robustness UI: package, inconclusive, relaxed diagnostics, missing profiles, budget evidence and fixed-budget failure controls passed.",
);
