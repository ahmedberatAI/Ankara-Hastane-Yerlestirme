import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const compiled = await build({ entryPoints: ["src/AccessConnectors.tsx"], bundle: true, platform: "node", format: "cjs",
  write: false, external: ["react", "react-dom/server"] });
const module = { exports: {} };
new Function("require", "module", "exports", compiled.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports);
const names = ["weekday-0800", "weekday-1000", "saturday-1000", "sunday-1000"];
const sourceSHA256 = { "travel-plan.json": "a".repeat(64), "dataset.json": "b".repeat(64), "travel-proof.json": "c".repeat(64) };
const travel = { transitPackageId: "package", planningVersion: "health", hospitalCount: 2,
  sourceSHA256, sourceCostCertificateSHA256: "d".repeat(64), scenario: { coverageTarget: 95 },
  profiles: names.map(profile => ({ profile, meanMinutes: 20,
    districts: Array.from({ length: 25 }, () => ({ population: 1000 })) })) };
const fixture = () => ({ format: 1, status: "descriptive_explicit_connectors", transitPackageId: "package", planningVersion: "health",
  hospitalCount: 2, walkingSpeedMetersPerSecond: 1.25, travelPlanSHA256: sourceSHA256["travel-plan.json"],
  sourceCostCertificateSHA256: travel.sourceCostCertificateSHA256, sourceTravelSummarySHA256: "e".repeat(64),
  sourceSHA256: { ...sourceSHA256 }, analysisCodeSHA256: { "scripts/audit_access_connectors.py": "f".repeat(64) },
  semanticCodeSHA256: { "scripts/build_timetable.py": "1".repeat(64), "backend/timetable.py": "2".repeat(64) },
  population: { provincePopulation: 25000, locatedPopulation: 24900, unlocatedPopulation: 100,
    targetServedPopulationEquivalentPerProfile: 23750 },
  profiles: names.map(profile => ({ profile, servedEquivalent: 23750, meanOriginMinutes: 1, meanHospitalMinutes: 4,
    meanEndpointMinutes: 5, shareOfPersonMinutesPercent: 25, totalMeanMinutes: 20 })) });
const render = (report, summary = "e".repeat(64)) => renderToStaticMarkup(React.createElement(module.exports.default,
  { report, travel, expectedSummarySHA: summary }));
const heading = /Yolculuğun ne kadarı varsayılan giriş bağlantısı/;
let html = render(fixture());
assert.match(html, heading);
assert.match(html, /23.750 kişi eşdeğeriyle ağırlıklıdır/);
assert.match(html, /Yüzde, toplam kişi-dakika içindeki paydır/);
assert.match(html, /dört profil toplanmaz/);
assert.match(html, /ölçülmüş hata oranı veya kazanılabilecek süre değildir/);
assert.match(html, /kalan süre de doğrulanmış saha ölçümü sayılmaz/);
assert.match(html, /Durak\/peron bağlantıları/);
for (const mutate of [
  r => r.sourceSHA256["dataset.json"] = "9".repeat(64), r => r.sourceSHA256["travel-proof.json"] = "9".repeat(64),
  r => delete r.sourceSHA256["dataset.json"], r => r.sourceSHA256.extra = "9".repeat(64),
  r => r.sourceTravelSummarySHA256 = "9".repeat(64), r => r.travelPlanSHA256 = "9".repeat(64),
  r => r.sourceCostCertificateSHA256 = "9".repeat(64), r => r.planningVersion = "old", r => r.transitPackageId = "old",
  r => r.status = "optimal", r => r.format = 2, r => r.hospitalCount = 3, r => r.walkingSpeedMetersPerSecond = 1.5,
  r => r.analysisCodeSHA256 = "missing", r => delete r.semanticCodeSHA256["backend/timetable.py"],
  r => r.profiles.pop(), r => r.profiles[1] = r.profiles[0], r => r.profiles[0] = null,
  r => r.profiles[0].servedEquivalent = 25000, r => r.profiles[0].meanOriginMinutes = NaN,
  r => r.profiles[0].meanHospitalMinutes = -1, r => r.profiles[0].meanEndpointMinutes = 6,
  r => r.profiles[0].shareOfPersonMinutesPercent = 5, r => r.profiles[0].totalMeanMinutes = 25,
  r => r.population.provincePopulation = 25001, r => r.population.unlocatedPopulation = 0,
  r => r.population.targetServedPopulationEquivalentPerProfile = 100000,
  r => { r.population.locatedPopulation = 23000; r.population.unlocatedPopulation = 2000; },
]) {
  const report = fixture(); mutate(report); html = render(report);
  assert.doesNotMatch(html, heading);
  assert.match(html, /önceki sayılar gösterilmiyor/);
}
assert.doesNotMatch(render(fixture(), "missing"), heading);
assert.doesNotMatch(render(null), heading);
// The packaged artifact must satisfy the same schema as the UI, not just synthetic fixtures.
const read = name => JSON.parse(readFileSync(`data/processed/${name}`, "utf8"));
const actual = read("access-connector-summary.json"), actualTravel = read("travel-summary.json");
const actualHash = read("manifest.json").files.find(f => f.file === "data/processed/travel-summary.json").sha256;
assert.equal(module.exports.accessConnectorState(actual, actualTravel, actualHash), "valid");
const actualHTML = renderToStaticMarkup(React.createElement(module.exports.default,
  { report: actual, travel: actualTravel, expectedSummarySHA: actualHash }));
assert.match(actualHTML, heading);
assert.match(actualHTML, /5.614.804 kişi eşdeğeriyle ağırlıklıdır/);
assert.match(actualHTML, /22,01/);
assert.match(actualHTML, /19,92/);
assert.equal(module.exports.accessConnectorState(actual, actualTravel, "0".repeat(64)), "stale");
console.log("Access connector UI: source identity, per-profile denominators and descriptive scope verified.");
