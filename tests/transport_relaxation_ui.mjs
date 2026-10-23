import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const built = await build({ entryPoints: ["src/TransportRelaxation.tsx"], bundle: true,
  platform: "node", format: "cjs", write: false, external: ["react", "react-dom/server"] });
const module = { exports: {} };
new Function("require", "module", "exports", built.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports);
const Content = module.exports.TransportRelaxationContent;
const names = ["weekday-0800", "weekday-1000", "saturday-1000", "sunday-1000"];
const fixture = () => ({
  transitPackageId: "current", planningVersion: "health-current", status: "witness_validated",
  witnessFound: true, hospitalLimit: 91, hospitalCount: 47, beds: 18000, doctors: 21000,
  withinHospitalLimit: true, withinOriginalTransitBudget: true,
  annualEquivalentCostTRY: 140e9, originalTransitBudgetTRY: 190e9,
  resourcesSharedAcrossProfiles: true, annualDemandCountedOnce: true,
  sameHealthScenarioParameters: { coverageTarget: 95, districtFloor: 80 },
  profiles: names.map((profile) => ({ profile, coveragePercent: 95, minimumDistrictCoveragePercent: 80 })),
});
const render = (report, packageId = "current", planningVersion = "health-current") =>
  renderToStaticMarkup(React.createElement(Content, { report, packageId, planningVersion }));
const positive = /47 tesisli uygun bir plan var/;
let html = render(fixture());
assert.match(html, positive);
assert.match(html, /hat, takvim ve aktarma kısıtları kaldırılır/);
assert.match(html, /Gerçek EGO ağıyla 91 hastanenin yeterli olduğu.*kanıtlanmıyor/);
assert.match(html, /yıllık talep ve gider bir kez sayılıyor/);
assert.match(html, /canlı ayarlarla değişmez/);
assert.match(html, /klinik gerçekçiliğini ayrıca doğrulamaz/);
assert.doesNotMatch(html, /46 tesis/);
for (const stale of [render(fixture(), "old"), render(fixture(), "current", "old-health")]) {
  assert.match(stale, /güncelleniyor/);
  assert.doesNotMatch(stale, positive);
}
for (const change of [
  (r) => r.hospitalLimit = 1000,
  (r) => r.sameHealthScenarioParameters.districtFloor = 0,
  (r) => r.sameHealthScenarioParameters.coverageTarget = 90,
]) {
  const r = fixture(); change(r);
  assert.match(render(r), /güncelleniyor/);
  assert.doesNotMatch(render(r), positive);
}
for (const change of [
  (r) => r.witnessFound = false,
  (r) => r.witnessFound = 1,
  (r) => r.withinOriginalTransitBudget = false,
  (r) => r.annualEquivalentCostTRY = 191e9,
  (r) => r.annualEquivalentCostTRY = NaN,
  (r) => r.hospitalCount = 92,
  (r) => r.doctors = NaN,
  (r) => r.annualDemandCountedOnce = false,
  (r) => r.profiles.pop(),
  (r) => r.profiles[1] = r.profiles[0],
  (r) => r.profiles[0].coveragePercent = 94.9,
  (r) => r.profiles[0].minimumDistrictCoveragePercent = 79.9,
]) {
  const r = fixture(); change(r); html = render(r);
  assert.doesNotMatch(html, positive);
  assert.match(html, /uygun bir tanık doğrulanamadı/);
  assert.match(html, /imkânsız olduğu sonucu çıkarılamaz/);
}
console.log("Transport relaxation UI: scope, stale sources, incomplete evidence, budget and unknown cases passed.");
