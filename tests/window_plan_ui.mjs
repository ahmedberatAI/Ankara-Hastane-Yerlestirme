import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
const read = p => JSON.parse(fs.readFileSync(p, "utf8"));
const built = await build({ entryPoints: ["src/WindowPlan.tsx"], bundle: true, platform: "node", format: "cjs", write: false,
  loader: { ".css": "empty" }, external: ["react", "react-dom/server"],
  plugins: [{ name: "isolated-default-data", setup(b) {
    b.onResolve({ filter: /window-plan-summary\.json$/ }, () => ({ path: "empty-summary", namespace: "test" }));
    b.onLoad({ filter: /.*/, namespace: "test" }, () => ({ contents: "export default {}", loader: "js" }));
  } }] });
const mod = { exports: {} };
new Function("require", "module", "exports", built.outputFiles[0].text)(createRequire(import.meta.url), mod, mod.exports);
const { WindowPlanContent, windowPlanState } = mod.exports;
const data = { ...read("data/processed/dataset.json"), healthPlanning: read("data/processed/health-planning.json") };
const old = read("data/processed/joint-plan-summary.json");
const definitions = [0, -5, 5, -4, -3, -2, -1, 1, 2, 3, 4].flatMap(offset =>
  [["weekday", 480], ["weekday", 600], ["saturday", 600], ["sunday", 600]].map(([day, start]) => {
    const minute = start + offset;
    return `${day}-${String(Math.floor(minute / 60)).padStart(2, "0")}${String(minute % 60).padStart(2, "0")}`;
  }));
const identities = [...read("data/processed/manifest.json").files.filter(i => !i.file.includes("departure-window")),
  { file: "data/processed/departure-window-plan/window-plan.json", sha256: "a".repeat(64) },
  { file: "data/processed/departure-window/manifest.json", sha256: "b".repeat(64) }];
const fixture = () => ({ ...structuredClone(old), status: "validated_window_model_plan", profileCount: 44,
  certificateSHA256: "a".repeat(64), profileManifestSHA256: "b".repeat(64),
  allProfilesValidated: true, resourcesSharedAcrossProfiles: true, annualDemandCountedOnce: true,
  sameIndividualsAcrossProfilesConstrained: false, minimumHospitalCountProven: false, globalOptimalityProven: false,
  hardBudgetTRY: 189556939209.2935, withinHardBudget: true, budgetSlackTRY: 189556939209.2935 - old.annualEquivalentCostTRY,
  sourceAnnualEquivalentCostTRY: 175868263288.70182, sourceCostDeltaTRY: old.annualEquivalentCostTRY - 175868263288.70182,
  sourceHospitalCount: 209, candidatePoolSize: 239, fullCandidateCount: data.candidates.length,
  optimizedProfileIds: [...definitions], validatedProfileIds: [...definitions],
  profiles: definitions.map(profile => ({ ...structuredClone(old.profiles[0]), profile })) });
const render = r => renderToStaticMarkup(React.createElement(WindowPlanContent, { report: r, data, identities }));
const good = fixture(); assert.equal(windowPlanState(good, data, identities), "valid");
const success = /08\.05 açığı bu modelde kapandı/;
const html = render(good); assert.match(html, success); assert.match(html, /44 \/ 44/);
assert.match(html, /araya|aradaki saniyeler/); assert.match(html, /gerçek bir kamu bütçesi değildir/);
assert.match(html, /minimum hastane sayısı/); assert.match(html, /yıllık talep ve malzeme gideri bir kez/);
for (const mutate of [r => r.status = "unverified", r => r.profileCount = 4, r => r.profiles.pop(),
  r => r.profiles[4] = r.profiles[0], r => r.validatedProfileIds.reverse(), r => r.profiles[8].coveragePercent = 94.9,
  r => r.profiles[8].districts[0].coveragePercent = 79, r => r.profiles[8].maxMinutes = 45.1,
  r => r.profiles[8].meanMinutes = NaN, r => r.profiles[8].districts.pop(), r => r.hardBudgetTRY++,
  r => r.annualEquivalentCostTRY = r.hardBudgetTRY + 1, r => r.budgetSlackTRY++, r => r.sourceCostDeltaTRY++,
  r => r.resourcesSharedAcrossProfiles = false, r => r.annualDemandCountedOnce = false,
  r => r.minimumHospitalCountProven = true, r => r.globalOptimalityProven = true,
  r => r.sameIndividualsAcrossProfilesConstrained = true, r => r.selected[0].doctors++,
  r => r.selected[0].lon++, r => r.scenario.coverageTarget = 94, r => r.scenario.districtFloor = 79,
  r => r.scenario.threshold = 46, r => r.profiles[0] = null, r => r.profiles = null,
  r => r.sourceSHA256 = null, r => r.scenario = null]) {
  const r = fixture(); mutate(r); assert.notEqual(windowPlanState(r, data, identities), "valid"); assert.doesNotMatch(render(r), success);
}
for (const mutate of [r => r.optimizedProfileIds = definitions.slice(0, 12),
  r => r.optimizedProfileIds = null, r => delete r.optimizedProfileIds,
  r => r.optimizedProfileIds.reverse(), r => r.optimizedProfileIds[4] = r.optimizedProfileIds[0],
  r => r.optimizedProfileIds.push("weekday-0806")]) {
  const r = fixture(); mutate(r); assert.equal(windowPlanState(r, data, identities), "invalid"); assert.doesNotMatch(render(r), success);
}
for (const mutate of [r => r.scenario.demandMultiplier = .1, r => r.scenario.contactsPerDoctor = 999999,
  r => r.scenario.bedOccupancy = 100, r => r.scenario.operatingCostMultiplier = .1,
  r => r.scenario.trafficFactor = 2, r => r.scenario.costTolerance = 20,
  r => r.scenario.transitProfile = "weekday-0800", r => delete r.scenario.demandMultiplier,
  r => r.scenario.newUnboundPreference = true]) {
  const r = fixture(); mutate(r); assert.equal(windowPlanState(r, data, identities), "stale"); assert.doesNotMatch(render(r), success);
}
for (const mutate of [r => r.provincePopulation++, r => r.provincePopulation = true,
  r => r.profiles[0].coveredPopulation = 0, r => r.profiles[0].coveredPopulation++,
  r => r.profiles[0].coveredPopulation = "5614804", r => r.profiles[0].coveredPopulation = Infinity,
  r => r.profiles[0].districts[0].coveredPopulation = 0, r => r.profiles[0].districts[0].coveredPopulation = NaN,
  r => r.profiles[0].districts[0].coveredPopulation = true, r => r.profiles[0].districts[0].coveredPopulation = -1,
  r => r.profiles[0].districts[0].population++, r => r.profiles[0].districts[0].population = 0,
  r => r.profiles[0].districts[0].coveredPopulation = r.profiles[0].districts[0].population + 1,
  r => r.profiles[0].maxMinutes = -1]) {
  const r = fixture(); mutate(r); assert.equal(windowPlanState(r, data, identities), "invalid"); assert.doesNotMatch(render(r), success);
}
// Changing two served counts in opposite directions keeps the province total
// fixed; each district's own percentage must still agree with its population.
const balanced = fixture(); balanced.profiles[0].districts[0].coveredPopulation++;
balanced.profiles[0].districts[1].coveredPopulation--;
assert.equal(windowPlanState(balanced, data, identities), "invalid");
for (const mutate of [r => r.transitPackageId = "old", r => r.planningVersion = "old",
  r => r.certificateSHA256 = "c".repeat(64), r => r.profileManifestSHA256 = "c".repeat(64),
  r => r.sourceSHA256["joint-plan.json"] = "c".repeat(64), r => delete r.sourceSHA256["dataset.json"]]) {
  const r = fixture(); mutate(r); assert.equal(windowPlanState(r, data, identities), "stale"); assert.doesNotMatch(render(r), success);
}
assert.equal(windowPlanState(null, data, identities), "invalid");
if (fs.existsSync("data/processed/window-plan-summary.json")) {
  const actual = read("data/processed/window-plan-summary.json");
  assert.equal(windowPlanState(actual, data, read("data/processed/manifest.json").files), "valid");
}
console.log("44-profile UI: grid, 95/80/45, strict budget, resource totals, source identities and limited claims passed.");
