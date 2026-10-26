import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";

const built = await build({ entryPoints: ["src/Hybrid.tsx"], bundle: true, platform: "node", format: "cjs",
  write: false, external: ["react", "react-dom/server"] });
const module = { exports: {} };
new Function("require", "module", "exports", built.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports);
const ui = module.exports;
const packageA = "motis-" + "a".repeat(64);
const packageB = "motis-" + "b".repeat(64);
const scenario = () => ({ mode: "hybrid", threshold: 30, transitThreshold: 45, carWeight: 70,
  transitEngine: "motis", transitProfile: "weekday-1000", coverageTarget: 95, districtFloor: 80,
  trafficFactor: 1, demandMultiplier: 1, bedOccupancy: 80, contactsPerDoctor: 2140,
  costTolerance: 10, hospitalLimit: null, operatingCostMultiplier: 1 });
const modal = (mean, candidate) => ({ metrics: { coveragePercent: 95, coveredPopulation: 95,
  meanMinutes: mean, p90Minutes: mean + 1, unreachableOrUnlocatedPopulation: 5 },
  districts: [{ id: candidate, name: candidate, population: 100, coveragePercent: 95 }],
  assignments: [{ demandId: "D", candidateId: candidate, candidateIndex: 0, minutes: mean,
    servedFraction: .95, covered: false, allocations: [{ candidateId: candidate, population: 95, minutes: mean }] }] });
const fixture = () => ({ status: "feasible", scenario: scenario(), selected: [{ id: "H1", beds: 50, doctors: 12 }, { id: "H2", beds: 50, doctors: 12 }],
  hospitalCount: 2, capacity: { totalBeds: 100, totalDoctors: 24, annualEquivalentCostTRY: 1e9,
    referenceCostTRY: 1e9, budgetLimitTRY: 1.1e9, finalPlanCostGap: .1 },
  searchScope: { restricted: true, kind: "restricted_allocation_edges" },
  modalResults: { car: modal(20, "H1"), transit: modal(40, "H2") },
  hybridSummary: { carWeight: 70, transitWeight: 100 * (1 - .7), weightedMeanMinutes: 26,
    thresholds: { car: 30, transit: 45 }, semantics: "Two full demand scenarios, one annual bill." },
  transitEvidence: { engine: "motis", packageId: packageA, scope: "Historical community GTFS scenario", profileDate: "2026-10-27", gtfsSHA256: "abc" } });
const render = (Component, props) => renderToStaticMarkup(React.createElement(Component, props));
let count = 0;
function test(label, fn) { fn(); count++; }

test("two modal views preserve exactly the common resources", () => {
  const r = fixture(), before = JSON.stringify(r);
  for (const mode of ["car", "transit"]) {
    const view = ui.resultForView(r, mode);
    assert.equal(view.selected, r.selected); assert.equal(view.capacity, r.capacity);
    assert.equal(view.metrics, r.modalResults[mode].metrics);
    assert.equal(view.assignments, r.modalResults[mode].assignments);
    assert.equal(view.districts, r.modalResults[mode].districts);
  }
  assert.equal(JSON.stringify(r), before);
});
test("70/30 binary64 rounding is accepted", () => assert.equal(ui.hybridResultProblem(fixture()), null));
for (const [label, mutate] of [
  ["wrong car weight", r => r.hybridSummary.carWeight = 71],
  ["wrong transit weight", r => r.hybridSummary.transitWeight = 70],
  ["wrong car limit", r => r.hybridSummary.thresholds.car = 45],
  ["wrong transit limit", r => r.hybridSummary.thresholds.transit = 30],
  ["missing modal transit", r => delete r.modalResults.transit],
  ["missing assignments", r => delete r.modalResults.car.assignments],
  ["missing districts", r => delete r.modalResults.transit.districts],
  ["missing semantic scope", r => r.hybridSummary.semantics = ""],
  ["averaged coverage disguised as travel", r => r.hybridSummary.weightedMeanMinutes = 95],
  ["nonfinite modal mean", r => r.modalResults.car.metrics.meanMinutes = Infinity],
  ["null modal mean", r => r.modalResults.car.metrics.meanMinutes = null],
  ["missing common resources", r => delete r.selected],
  ["inconsistent common resource count", r => r.hospitalCount = 8],
  ["inconsistent common bed sum", r => r.capacity.totalBeds = 150],
  ["allocation to a different hospital plan", r => r.modalResults.transit.assignments[0].allocations[0].candidateId = "OTHER"],
  ["transit misses its own province target", r => r.modalResults.transit.metrics.coveragePercent = 90],
  ["transit misses its own district floor", r => r.modalResults.transit.districts[0].coveragePercent = 75],
  ["long transit cannot be hidden by fast car", r => r.modalResults.transit.assignments[0].allocations[0].minutes = 46],
]) test(label, () => { const r = fixture(); mutate(r); assert.ok(ui.hybridResultProblem(r)); assert.equal(ui.resultForView(r, "car"), null); });
for (const status of ["inconclusive", "infeasible", "timeout"]) test(`${status} is not fabricated into a car plan`, () => {
  const r = { status, scenario: scenario(), reason: "No common incumbent" };
  assert.equal(ui.hybridResultProblem(r), null); assert.equal(ui.resultForView(r, "car"), null);
});
for (const [key, value] of [["transitEngine", "ego"], ["transitProfile", "weekday-0800"], ["carWeight", 80],
  ["transitThreshold", 60], ["threshold", 35], ["demandMultiplier", 1.5], ["contactsPerDoctor", 3000], ["hospitalLimit", 91]]) {
  test(`stale ${key} rejects response`, () => {
    const r = fixture(), requested = { ...scenario(), [key]: value };
    assert.notEqual(ui.scenarioKey(r.scenario), ui.scenarioKey(requested));
    assert.ok(ui.responseProblem(r, requested));
  });
}
test("evidence cannot silently fall back from MOTIS to old EGO", () => {
  const r = fixture(); r.transitEvidence.engine = "ego"; assert.ok(ui.responseProblem(r, scenario()));
});
test("unidentified MOTIS evidence fails closed", () => {
  const r = fixture(); delete r.transitEvidence.engine; assert.ok(ui.responseProblem(r, scenario()));
});
test("valid identified response and historical scenario defaults", () => {
  assert.equal(ui.responseProblem(fixture(), scenario()), null);
  assert.equal(ui.engineFor({ mode: "transit" }), "ego");
});
test("routeMode follows display only, preserving provider and both limits", () => {
  const r = fixture();
  for (const mode of ["car", "transit"]) {
    const request = ui.routeRequest(r, mode, "D", "H1");
    assert.equal(request.routeMode, mode); assert.equal(request.mode, "hybrid");
    assert.equal(request.transitEngine, "motis"); assert.equal(request.threshold, 30);
    assert.equal(request.transitThreshold, 45); assert.equal(request.carWeight, 70);
    assert.equal(request.routingPackageId, mode === "transit" ? packageA : undefined);
  }
  r.scenario.mode = "car"; assert.equal("routeMode" in ui.routeRequest(r, "transit", "D", "H1"), false);
});
test("MOTIS requires selected matrix, not only an alive server", () => {
  assert.equal(ui.routingAvailability(null, scenario()).ready, false);
  for (const motis of [{ ready: false }, { ready: true }, { ready: true, matrixProfiles: ["weekday-0800"] }])
    assert.equal(ui.routingAvailability({ motis }, scenario()).ready, false);
  assert.equal(ui.routingAvailability({ motis: { ready: true, matrixProfiles: ["weekday-1000"] } }, scenario()).ready, true);
  assert.equal(ui.routingAvailability(null, { ...scenario(), mode: "car" }).ready, true);
});
test("a route response is bound to view, source scenario and both endpoints", () => {
  const r = fixture();
  const route = { scenario: { ...r.scenario, demandId: "D", candidateId: "H1", routingPackageId: packageA },
    evidence: { packageId: packageA }, routeMode: "transit", minutes: 40, legs: [], boardings: [] };
  assert.equal(ui.routeResponseProblem(route, r, "transit", "D", "H1"), null);
  for (const mutate of [q => q.routeMode = "car", q => q.scenario.transitEngine = "ego",
    q => q.scenario.transitProfile = "weekday-0800", q => q.scenario.demandId = "OTHER",
    q => q.scenario.candidateId = "H2", q => delete q.scenario, q => q.minutes = Infinity]) {
    const changed = structuredClone(route); mutate(changed);
    assert.ok(ui.routeResponseProblem(changed, r, "transit", "D", "H1"));
  }
});
test("MOTIS transit routes cannot mix an old plan with a new source package", () => {
  const r = fixture();
  const route = { scenario: { ...r.scenario, demandId: "D", candidateId: "H1", routingPackageId: packageA },
    evidence: { packageId: packageA }, routeMode: "transit", minutes: 40, legs: [], boardings: [] };
  assert.equal(ui.routeResponseProblem(route, r, "transit", "D", "H1"), null);
  for (const mutate of [q => q.evidence.packageId = packageB, q => delete q.evidence,
    q => q.scenario.routingPackageId = packageB, q => delete q.scenario.routingPackageId]) {
    const changed = structuredClone(route); mutate(changed);
    assert.ok(ui.routeResponseProblem(changed, r, "transit", "D", "H1"));
  }
  const newer = structuredClone(route); newer.scenario.routingPackageId = packageB; newer.evidence.packageId = packageB;
  assert.ok(ui.routeResponseProblem(newer, r, "transit", "D", "H1"));
});
test("missing or malformed expected MOTIS identity blocks transit but not car routes", () => {
  for (const packageId of [undefined, null, "", "motis-stale", "ego-" + "a".repeat(64), 42]) {
    const r = fixture(); r.transitEvidence.packageId = packageId;
    assert.throws(() => ui.routeRequest(r, "transit", "D", "H1"), /paket kimliği/);
    assert.equal(ui.routeRequest(r, "car", "D", "H1").routingPackageId, undefined);
    const route = { scenario: { ...r.scenario, demandId: "D", candidateId: "H1", routingPackageId: packageId },
      evidence: { packageId }, routeMode: "transit", minutes: 40, legs: [], boardings: [] };
    assert.ok(ui.routeResponseProblem(route, r, "transit", "D", "H1"));
  }
});
test("single transit binds its actual mode and legacy EGO keeps its existing route contract", () => {
  const r = fixture(); r.scenario.mode = "transit";
  assert.equal(ui.routeRequest(r, "car", "D", "H1").routingPackageId, packageA);
  r.scenario.transitEngine = "ego";
  delete r.transitEvidence.packageId;
  assert.equal(ui.routeRequest(r, "transit", "D", "H1").routingPackageId, undefined);
  const route = { scenario: { ...r.scenario, demandId: "D", candidateId: "H1" }, routeMode: "transit", minutes: 40, legs: [], boardings: [] };
  assert.equal(ui.routeResponseProblem(route, r, "car", "D", "H1"), null);
  r.scenario.mode = "hybrid"; r.scenario.transitEngine = "motis";
  route.scenario = { ...r.scenario, demandId: "D", candidateId: "H1" }; route.routeMode = "car";
  assert.equal(ui.routeResponseProblem(route, r, "car", "D", "H1"), null);
});
test("unknown metadata displays unavailability", () => {
  const html = render(ui.ProviderStatus, { status: null, scenario: scenario(), error: "", refresh() {} });
  assert.match(html, /henüz kullanılamıyor/); assert.doesNotMatch(html, /seçili profil hazır/);
});
test("common-resource, annual-cost and unmeasured ambulance scope is visible", () => {
  const html = render(ui.HybridOverview, { result: fixture(), view: "transit", onViewChange() {} });
  assert.match(html, /Yıllık maliyet bir kez/); assert.match(html, /hasta oranı değildir/);
  assert.match(html, /Kişisel araç yolları kullanılır/); assert.match(html, /aynı kişilerin kapsandığı zorunlu tutulmaz/);
  assert.match(html, /daraltılmış aday bağlantıları/); assert.doesNotMatch(html, /undefined|30\.000000000000004/);
});
test("compact overview retains both view controls and exposes all assumptions in native details", () => {
  const html = render(ui.HybridOverview, { result: fixture(), view: "car", onViewChange() {} });
  const closedPart = html.slice(0, html.indexOf('<details class="hybrid-cost-details"'));
  assert.match(closedPart, /Ortak yatak ve hekimler/);
  assert.match(closedPart, /her modun tam talep senaryosuna/);
  assert.match(closedPart, /Yıllık maliyet bir kez/);
  assert.match(closedPart, /%70 araba \+ %30 toplu ulaşım/);
  assert.equal((closedPart.match(/aria-pressed=/g) ?? []).length, 2);
  assert.doesNotMatch(closedPart, /Kişisel araç yolları|hastane sayısının asgari/);
  assert.match(html, /<details class="hybrid-cost-details"><summary>Ağırlıklar, maliyet ve model sınırları<\/summary>/);
  assert.match(html, /ambulanslara özgü hız/);
  assert.match(html, /hasta oranı değildir/);
});
test("provider/date identity remains with last computed result when selection changes", () => {
  const r = fixture(); r.scenario.transitEngine = "ego"; r.transitEvidence = { engine: "ego", scope: "Old EGO" };
  const html = render(ui.TransitEvidenceNote, { result: r, scenario: scenario(), pending: true });
  assert.match(html, /Gösterilen hesap/); assert.match(html, /Özgün EGO modeli/);
  assert.match(html, /Bekleyen seçim/); assert.match(html, /MOTIS/);
});
test("MOTIS date, hash and historical scope", () => {
  const html = render(ui.TransitEvidenceNote, { result: fixture(), scenario: scenario(), pending: false });
  assert.match(html, /tarihsel topluluk GTFS/); assert.match(html, /güncel resmî EGO tarifesinin/);
  assert.match(html, /27 Ekim 2026/); assert.match(html, /GTFS SHA-256/);
});
test("source banner is a closed native disclosure with visible provider and date", () => {
  const html = render(ui.TransitEvidenceNote, { result: fixture(), scenario: scenario(), pending: false });
  assert.match(html, /^<details class="transit-banner provider-evidence"><summary>/);
  const summary = html.slice(0, html.indexOf("</summary>"));
  assert.match(summary, /MOTIS · tarihsel GTFS/); assert.match(summary, /27 Ekim 2026/);
  assert.match(html, /güncel resmî EGO tarifesinin/); assert.match(html, /GTFS SHA-256/);
  assert.doesNotMatch(html, /^<details[^>]*\sopen/);
});
test("MOTIS ISO departure uses Turkey time and is not mistaken for UTC", () => {
  assert.equal(ui.departureLabel("2026-10-27T05:12:00Z"), "08:12");
  assert.equal(ui.departureLabel("08:12"), "08:12");
  const r = fixture(); delete r.transitEvidence.profileDate; r.transitEvidence.departure = "2026-10-27T10:00:00+03:00";
  assert.match(render(ui.TransitEvidenceNote, { result: r, scenario: scenario(), pending: false }), /27 Ekim 2026 10:00/);
  assert.equal(ui.profileDateLabel("2026-10-27T05:12:00Z"), "27 Ekim 2026 08:12");
});
test("live App wires the view and invalidates asynchronous routes", () => {
  const app = readFileSync("src/App.tsx", "utf8");
  assert.match(app, /result=\{viewedResult\}/); assert.match(app, /const stats = viewedResult\?\.metrics/);
  assert.match(app, /\}, \[scenario, viewMode\]\)/); assert.match(app, /version === routeVersion\.current/);
  assert.match(app, /if \(busy \|\| dirty\)/); assert.match(app, /!availability\.ready/);
  assert.match(app, /Tarihsel özgün EGO deneyleri/);
  assert.ok(app.indexOf('result?.scenario.mode !== "hybrid" && capacityPanel') < app.indexOf('className="map-toolbar"'));
  assert.ok(app.indexOf('result?.scenario.mode === "hybrid" && capacityPanel') > app.indexOf('className="map-footer"'));
});
console.log(`${count} hybrid UI checks passed`);
