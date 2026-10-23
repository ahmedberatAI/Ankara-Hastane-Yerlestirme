import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const built = await build({ entryPoints: ["src/JointPlan.tsx"], bundle: true, platform: "node", format: "cjs",
  write: false, loader: { ".css": "empty" }, external: ["react", "react-dom/server"] });
const module = { exports: {} };
new Function("require", "module", "exports", built.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports);
const Content = module.exports.JointPlanContent;
const names = ["weekday-0800", "weekday-1000", "saturday-1000", "sunday-1000"];
const fixture = () => ({
  status: "witness_validated", transitPackageId: "current", planningVersion: "health-current",
  scenario: { mode: "transit", threshold: 45, coverageTarget: 95, districtFloor: 80, hospitalLimit: null },
  hospitalCount: 2, beds: 200, doctors: 40, resourcesSharedAcrossProfiles: true, annualDemandCountedOnce: true,
  sameIndividualsAcrossProfilesConstrained: false, annualEquivalentCostTRY: 189.2e9, originalTransitBudgetTRY: 189.6e9,
  budgetSlackTRY: .4e9, withinOriginalTransitBudget: true,
  selected: [0, 1].map(i => ({ candidateIndex: i, id: `H-${i}`, lon: 32 + i, lat: 39, beds: 100, doctors: 20, maximumAssignedPopulationAcrossProfiles: 300 })),
  profiles: names.map(profile => ({ profile, coveragePercent: 95, minimumDistrictCoveragePercent: 80, meanMinutes: 32, maxMinutes: 44,
    districts: Array.from({ length: 25 }, (_, i) => ({ id: `D-${i}`, name: `District ${i}`, population: 1000, coveragePercent: 80 })) })),
  conditionalOverlap: { province: { lowerPercent: 91, upperPercent: 93 }, sameIndividualsObserved: false },
});
const current = { candidates: fixture().selected, districts: fixture().profiles[0].districts };
const render = (report, packageId = "current", planningVersion = "health-current") => renderToStaticMarkup(
  React.createElement(Content, { report, packageId, planningVersion, current }));
const success = /Doğrulanmış model örneği/;
let html = render(fixture());
assert.match(html, success);
assert.match(html, /KAYITLI EGO DENEYİ/);
assert.match(html, /minimum hastane ihtiyacı değildir/);
assert.match(html, /91 hastanenin yeterliliğini/);
assert.match(html, /gerçek bir kamu bütçesi değil/);
assert.match(html, /Yıllık talep dört kez toplanmaz/);
assert.match(html, /aynı %95 kişinin dört profilde de/);
assert.match(html, /ayrıca en aza indirilmedi/);
assert.match(html, /canlı ayarlarla değişmez/);
assert.match(html, /2 sayısı hangi büyüklükteki tesisleri içeriyor/);
assert.match(html, /2 tanesi \(%100\) 100 yataklı şablonda/);
assert.match(html, /ayrı poliklinik veya sağlık merkezi türleri modellenmiyor/);
assert.match(html, /her konumun zorunlu olduğunu göstermez/);
assert.doesNotMatch(html, /239/);
for (const change of [r => r.transitPackageId = "old", r => r.planningVersion = "old-health", r => r.scenario.threshold = 60,
  r => r.scenario.coverageTarget = 90, r => r.scenario.districtFloor = 0, r => r.scenario.hospitalLimit = 91]) {
  const r = fixture(); change(r); html = render(r); assert.doesNotMatch(html, success); assert.match(html, /güncel veriyle eşleştiriliyor/);
}
for (const change of [r => r.status = "infeasible", r => r.resourcesSharedAcrossProfiles = false, r => r.annualDemandCountedOnce = 1,
  r => r.sameIndividualsAcrossProfilesConstrained = true, r => r.annualEquivalentCostTRY = NaN, r => r.budgetSlackTRY = NaN,
  r => r.budgetSlackTRY += 20, r => r.beds++, r => r.selected[1].id = r.selected[0].id,
  r => r.selected[1].lon = Infinity, r => r.withinOriginalTransitBudget = false, r => r.profiles.pop(),
  r => r.profiles[1] = r.profiles[0], r => r.profiles[0].coveragePercent = 94.9, r => r.profiles[0].minimumDistrictCoveragePercent = 81,
  r => r.profiles[0].maxMinutes = 46, r => r.profiles[0].districts.pop(), r => r.profiles[0].districts[0].coveragePercent = 79.9,
  r => r.conditionalOverlap.province.upperPercent = NaN, r => r.conditionalOverlap.province.lowerPercent = 99,
  r => r.conditionalOverlap.province = { lowerPercent: 100, upperPercent: 100 },
  r => r.conditionalOverlap.province.lowerPercent = 79]) {
  const r = fixture(); change(r);
  html = render(r); assert.doesNotMatch(html, success); assert.match(html, /doğrulaması tamamlanmamış/);
}
for (const change of [r => r.selected = null, r => r.conditionalOverlap = null, r => delete r.profiles,
  r => r.scenario = null, r => r.profiles[0].districts = null, r => r.selected[0] = null,
  r => r.selected[0].candidateIndex = NaN, r => r.selected[0].candidateIndex = 999999, r => r.selected[0].candidateIndex = .5,
  r => r.selected[0].lon = 0, r => r.selected[0].lon = 32.01, r => r.selected[0].maximumAssignedPopulationAcrossProfiles = NaN,
  r => r.profiles[0].districts[0].id = "unknown", r => r.profiles[0].districts[0].population = 900,
  r => { r.annualEquivalentCostTRY = 0; r.originalTransitBudgetTRY = 0; r.budgetSlackTRY = 0; }]) {
  const r = fixture(); change(r); html = render(r); assert.doesNotMatch(html, success); assert.match(html, /doğrulaması tamamlanmamış/);
}
assert.match(render(null), /doğrulaması tamamlanmamış/);
const above = fixture(); above.status = "validated_model_plan_above_reference_budget"; above.annualEquivalentCostTRY = 190e9;
above.budgetSlackTRY = -.4e9; above.withinOriginalTransitBudget = false;
html = render(above); assert.match(html, success); assert.match(html, /maliyet tavanını aşıyor/);
assert.match(html, /başka bir çözüm bulunamayacağı sonucu çıkarılamaz/); assert.doesNotMatch(html, /Pay küçük/);
above.annualEquivalentCostTRY = above.originalTransitBudgetTRY + .01; above.budgetSlackTRY = -.01;
html = render(above); assert.match(html, /maliyet tavanını aşıyor/); assert.doesNotMatch(html, /doğrulaması tamamlanmamış/);
console.log("Joint plan UI: current sources, targets, complete profiles, budget scope and same-person distinction verified.");
