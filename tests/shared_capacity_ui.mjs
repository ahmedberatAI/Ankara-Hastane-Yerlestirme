import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const built = await build({ entryPoints: ["src/SharedCapacity.tsx"], bundle: true,
  platform: "node", format: "cjs", write: false, external: ["react", "react-dom/server"] });
const module = { exports: {} };
new Function("require", "module", "exports", built.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports);
const Content = module.exports.SharedCapacityContent;
const profiles = ["weekday-0800", "weekday-1000", "saturday-1000", "sunday-1000"];
const fixture = () => ({
  transitPackageId: "current",
  sourcePlan: { sha256: "saved-plan", transitPackageId: "current", hospitalCount: 321,
    originalAnnualBudgetTRY: 2000000000,
    scenario: { threshold: 45, coverageTarget: 95, districtFloor: 80 } },
  result: { status: "infeasible", totalBeds: null, totalDoctors: null,
    annualEquivalentCostTRY: null, costGap: null, budgetStatus: "targets_infeasible", meetsOriginalBudget: false },
  independentResourceCeiling: { anyProfileProvesTargetsImpossible: true,
    profiles: profiles.map((profile) => ({ profile, status: "optimal", maximumCoveragePercent: 94.9,
      provinceTargetShortfallResidents: .256, linearProgrammingDualCertified: true })) },
});
const render = (report, packageId = "current", planSha = "saved-plan") =>
  renderToStaticMarkup(React.createElement(Content, { report, packageId, planSha }));

let report = fixture();
for (const html of [render(report, "old"), render(report, "current", "another-plan")]) {
  assert.match(html, /güncel kayıtlı planla eşleşmiyor/);
  assert.doesNotMatch(html, /321 konum/);
}
let html = render(report);
assert.match(html, /yalnız kapasite artırımı yeterli değil/);
assert.match(html, /0,25 kişi eşdeğeri/);
assert.doesNotMatch(html, /1 kişi eşdeğeri|0,26 kişi eşdeğeri/);
assert.match(html, /bütçe ve maliyet tamamen kaldırılır/);
assert.match(html, /Başka konumlarda veya gerçek Ankara/);

report = fixture();
report.result.status = "inconclusive";
report.independentResourceCeiling.profiles.forEach((row) => Object.assign(row, {
  status: "inconclusive", maximumCoveragePercent: null, provinceTargetShortfallResidents: null,
  linearProgrammingDualCertified: false,
}));
html = render(report);
assert.match(html, /henüz sonuçlandırılamadı/);
assert.match(html, /Sonuç belirsiz/);
assert.doesNotMatch(html, /0 kişi eşdeğeri|%0|yalnız kapasite artırımı yeterli değil/);

report = fixture();
report.independentResourceCeiling.profiles.pop();
assert.match(render(report), /Profil denetimleri tamamlanmamış/);
assert.doesNotMatch(render(report), /yalnız kapasite artırımı yeterli değil/);

report = fixture();
Object.assign(report.result, { status: "feasible", totalBeds: 999, totalDoctors: 111,
  annualEquivalentCostTRY: 3000000000, costGap: .5, budgetStatus: "incumbent_over_budget_unresolved" });
html = render(report);
assert.match(html, /orijinal bütçe içinde olduğu doğrulanmadı/);
assert.match(html, /Daha ucuz, bütçeye uygun bir çözümün bulunup bulunmadığı belirsiz/);
assert.match(html, /yalnız bu sabit konumlar için/);
assert.doesNotMatch(html, /tasarımı orijinal bütçe içinde bulundu/);
console.log("Shared capacity UI: stale, unknown, scope, incomplete profiles and conservative bound display passed.");
