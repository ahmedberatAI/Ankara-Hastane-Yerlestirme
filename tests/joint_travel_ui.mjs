import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const built = await build({ entryPoints: ["src/JointTravel.tsx"], bundle: true, platform: "node", format: "cjs",
  write: false, loader: { ".css": "empty" }, external: ["react", "react-dom/server"] });
const module = { exports: {} };
new Function("require", "module", "exports", built.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports);
const Content = module.exports.JointTravelContent;
const names = ["weekday-0800", "weekday-1000", "saturday-1000", "sunday-1000"];
const source = {
  transitPackageId: "current-package", planningVersion: "current-health",
  sourceSHA256: { "joint-plan.json": "a".repeat(64), "dataset.json": "b".repeat(64) },
  hospitalCount: 2, beds: 200, doctors: 40, annualEquivalentCostTRY: 10e9,
  scenario: { mode: "transit", threshold: 45, coverageTarget: 95, districtFloor: 80, hospitalLimit: null },
  profiles: names.map(profile => ({ profile, meanMinutes: 32,
    districts: Array.from({ length: 25 }, (_, i) => ({ id: `D-${i}`, population: 1000, coveragePercent: 80 })) })),
};
const fixture = () => ({
  status: "validated_fixed_resource_travel", transitPackageId: source.transitPackageId, planningVersion: source.planningVersion,
  scenario: { ...source.scenario }, sourceCostCertificateSHA256: source.sourceSHA256["joint-plan.json"], sourceSHA256: { ...source.sourceSHA256 },
  hospitalCount: 2, beds: 200, doctors: 40, annualEquivalentCostTRY: 10e9,
  annualCostUnchanged: true, resourcesUnchanged: true, globalTravelOptimumProven: false,
  allProfilesAccepted: true, acceptedProfileCount: 4,
  profiles: names.map(profile => ({ profile, status: "travel_profile_accepted", accepted: true, sourceFallback: false,
    sourceMeanMinutes: 32, meanMinutes: 29, reductionMinutes: 3, coveragePercent: 95, minimumDistrictCoveragePercent: 80,
    maxMinutes: 44, lowerBoundMinutes: 29 + 1e-10, primalMinusLowerBoundMinutes: -1e-10,
    primalDualToleranceMinutes: 1e-7, certifiedForRepresentedFixedResourceLP: true,
    districts: structuredClone(source.profiles[0].districts) })),
  conditionalOverlap: { province: { lowerPercent: 92, upperPercent: 94 }, sameIndividualsObserved: false },
});
const render = (report, base = source) => renderToStaticMarkup(React.createElement(Content, { report, source: base }));
const success = /Aynı hastanelerle yolculuk süresini azaltmak/;
let html = render(fixture());
assert.match(html, success);
assert.match(html, /KAYITLI EGO DENEYİ/);
assert.match(html, /Bu kayıtlı EGO deneyi canlı ayarlarla değişmez/);
assert.match(html, /2 konum, 200 yatak ve 40 hekim sabit tutuldu/);
assert.match(html, /ek kaynak alınmadı/);
assert.match(html, /herkesin yolculuğunun kısaldığı anlamına gelmez/);
assert.match(html, /genel yerleşim optimumu/);
assert.match(html, /-1\.00e-10/);
assert.match(html, /sayısal uygulanabilirlik toleransından/);
assert.match(html, /harita yükleri ve ortak kapsam açıklaması maliyet aşamasına aittir/);
assert.doesNotMatch(html, /209/);
for (const mutate of [r => r.sourceCostCertificateSHA256 = "c".repeat(64), r => r.sourceSHA256["dataset.json"] = "x",
  r => r.transitPackageId = "old", r => r.planningVersion = "old", r => r.scenario.threshold = 60,
  r => r.scenario.districtFloor = 0]) {
  const r = fixture(); mutate(r); html = render(r);
  assert.doesNotMatch(html, success); assert.match(html, /güncel maliyet planıyla eşleştiriliyor/);
}
for (const mutate of [r => r.profiles.pop(), r => r.profiles[1] = r.profiles[0], r => r.resourcesUnchanged = 1,
  r => r.annualCostUnchanged = false, r => r.globalTravelOptimumProven = true, r => r.hospitalCount++, r => r.doctors++,
  r => r.annualEquivalentCostTRY += 100, r => r.status = "unverified", r => r.acceptedProfileCount = 3,
  r => r.allProfilesAccepted = false, r => r.conditionalOverlap.province.lowerPercent = 101,
  r => r.conditionalOverlap.province = { lowerPercent: 100, upperPercent: 100 },
  r => r.conditionalOverlap.province = { lowerPercent: 70, upperPercent: 94 },
  r => r.conditionalOverlap.sameIndividualsObserved = true, r => r.profiles[0].sourceMeanMinutes = 33,
  r => r.profiles[0].meanMinutes = NaN, r => r.profiles[0].meanMinutes = 33,
  r => r.profiles[0].sourceFallback = true, r => r.profiles[0].lowerBoundMinutes = null,
  r => r.profiles[0].primalMinusLowerBoundMinutes = null, r => r.profiles[0].primalMinusLowerBoundMinutes = -.1,
  r => r.profiles[0].primalDualToleranceMinutes = .1, r => r.profiles[0].certifiedForRepresentedFixedResourceLP = false,
  r => r.profiles[0].coveragePercent = 94.9, r => r.profiles[0].maxMinutes = 46,
  r => r.profiles[0].minimumDistrictCoveragePercent = 79, r => r.profiles[0].districts.pop(),
  r => r.profiles[0].districts[0].population = 900, r => r.profiles[0].districts[0].coveragePercent = 79,
  r => r.profiles[0].districts[0] = null, r => r.profiles[0] = null, r => r.conditionalOverlap = null,
  r => r.scenario = null, r => r.sourceSHA256 = null, r => r.profiles = null]) {
  const r = fixture(); mutate(r); html = render(r);
  assert.doesNotMatch(html, success); assert.match(html, /doğrulaması tamamlanmamış/);
}
assert.match(render(null), /doğrulaması tamamlanmamış/);
const fallback = fixture();
Object.assign(fallback.profiles[0], { status: "source_preserved", accepted: false, sourceFallback: true,
  certifiedForRepresentedFixedResourceLP: false, lowerBoundMinutes: null, primalMinusLowerBoundMinutes: null,
  primalDualToleranceMinutes: null, meanMinutes: 32, reductionMinutes: 0 });
fallback.acceptedProfileCount = 3; fallback.allProfilesAccepted = false;
html = render(fallback); assert.match(html, success); assert.match(html, /Başlangıç korundu/);
assert.match(html, /3\/4 profil için süre iyileştirmesi doğrulandı/);
fallback.profiles[0].lowerBoundMinutes = 30;
assert.doesNotMatch(render(fallback), success);
console.log("Fixed-resource travel UI: source binding, four profiles, same cost, signed gaps, fallback and narrow claims verified.");
