import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { build } from 'esbuild';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
const built = await build({ entryPoints: ['src/Permanent.tsx'], bundle: true, platform: 'node', format: 'cjs', write: false, external: ['react'] });
const m = { exports: {} }; new Function('require', 'module', 'exports', built.outputFiles[0].text)(createRequire(import.meta.url), m, m.exports);
const ui = m.exports, pkg = 'motis-' + 'a'.repeat(64), policy = JSON.parse(readFileSync('data/planning-policy.json', 'utf8'));
const clone = x => structuredClone(x);
const data = { healthPlanning: { version: 'health-test' }, metadata: { provincePopulation: 100, matchedPopulation: 100, unlocatedPopulation: 0, candidateCount: 1 },
  demands: [0, 1].map(i => ({ id: `D${i}`, name: `Mahalle ${i}`, district: `İlçe ${i}`, districtId: `I${i}`, population: 50, lon: 32.8, lat: 39.9 })),
  districts: [0, 1].map(i => ({ id: `I${i}`, name: `İlçe ${i}`, population: 50 })),
  candidates: [{ id: 'H', name: 'Ortak hastane', district: 'İlçe 0', districtId: 'I0', lon: 32.8, lat: 39.9, footprintRadiusMeters: 50 }] };
function fixture() {
  const profiles = Object.fromEntries(ui.permanentProfiles.map((id, i) => {
    const minutes = 10 + 5 * i;
    return [id, { profile: clone(policy.profileDetails[id]), metrics: { coveredPopulation: 95, coveragePercent: 95, meanMinutes: minutes, p90Minutes: minutes, unreachableOrUnlocatedPopulation: 5 },
      districts: data.districts.map(d => ({ ...d, coveredPopulation: 47.5, coveragePercent: 95 })),
      assignments: data.demands.map(d => ({ demandId: d.id, candidateId: 'H', candidateIndex: 0, minutes, covered: false, servedFraction: .95,
        allocations: [{ candidateId: 'H', candidateIndex: 0, population: 47.5, fraction: .95, minutes }] })),
      ...(id === 'car' ? {} : { transitEvidence: { engine: 'motis', packageId: pkg, profile: id, departure: policy.profileDetails[id].departure } }) }];
  }));
  return { artifactType: 'permanent-hospital-plan', status: 'feasible', planId: 'permanent-' + 'b'.repeat(64), planningVersion: 'health-test',
    policy: clone(policy), metadata: clone(data.metadata), scenario: { mode: 'hybrid', transitProfile: 'sunday-1000', ...Object.fromEntries(['threshold','transitThreshold','coverageTarget','districtFloor','trafficFactor','demandMultiplier','bedOccupancy','contactsPerDoctor','costTolerance','hospitalLimit','operatingCostMultiplier','transitEngine','carWeight'].map(k => [k, policy[k]])) },
    profiles, modalResults: { car: profiles.car, transit: profiles['sunday-1000'] }, criticalTransitProfile: 'sunday-1000',
    metrics: profiles.car.metrics, districts: profiles.car.districts, assignments: profiles.car.assignments,
    selected: [{ ...data.candidates[0], beds: 50, doctors: 12 }], hospitalCount: 1, capacity: { totalBeds: 50, totalDoctors: 12, annualEquivalentCostTRY: 10000000 },
    permanentSummary: { profileCount: 5, transitProfileCount: 4, profileWeights: clone(policy.profileWeights), annualDemandCountedOnce: true,
      sameIndividualsAcrossProfilesConstrained: false, thresholds: Object.fromEntries(ui.permanentProfiles.map(id => [id, id === 'car' ? 30 : 60])),
      criticalTransitProfile: 'sunday-1000', weightedMeanMinutes: 13.75, meanTransitMinutes: 22.5, worstTransitMeanMinutes: 30, minimumProvinceCoveragePercent: 95, minimumDistrictCoveragePercent: 95 },
    transitEvidence: { engine: 'motis', packageId: pkg, scope: 'Dört tarihli örnek; tüm gün değil.', profileDates: Object.fromEntries(ui.permanentProfiles.slice(1).map(id => [id, policy.profileDetails[id].departure])) } };
}
let tests = 0;
function test(name, fn) { try { fn(); tests++; } catch (e) { throw new Error(name, { cause: e }); } }
const check = r => ui.permanentPlanProblem(r, data, policy);
test('valid complete five-profile witness', () => assert.equal(check(fixture()), null));
test('policy is fixed and sourced, not a clinical standard', () => assert.equal(ui.policyProblem(policy), null));
for (const [label, mutate] of [
  ['clinical claim', p => p.clinicalStandard = true], ['policy version', p => p.version = '1'], ['different PT time', p => p.transitThreshold = 45],
  ['weight changed', p => p.profileWeights.car = .8], ['extra profile', p => p.profileIds.push('weekday-0805')], ['missing source', p => p.sources = []],
  ['unsafe source link', p => p.sources[0].url = 'javascript:alert(1)'], ['missing profile date', p => p.profileDetails['sunday-1000'].departure = null]
]) test(`reject policy: ${label}`, () => { const p = clone(policy); mutate(p); assert.ok(ui.policyProblem(p)); });
for (const [label, mutate] of [
  ['unknown solve', p => p.status = 'inconclusive'], ['fake id', p => p.planId = 'permanent-latest'], ['old health', p => p.planningVersion = 'old'],
  ['changed source population', p => p.metadata.provincePopulation = 101], ['different policy', p => p.policy.sources[0].title = 'changed'], ['changed scenario', p => p.scenario.demandMultiplier = 2],
  ['old45 threshold', p => p.scenario.transitThreshold = 45], ['unselected provider', p => p.scenario.transitEngine = 'ego'], ['only four profiles', p => delete p.profiles.car],
  ['six profiles', p => p.profiles['weekday-0805'] = clone(p.profiles.car)], ['wrong dates', p => p.transitEvidence.profileDates['weekday-0800'] = '2026-10-27'],
  ['missing package', p => delete p.transitEvidence.packageId], ['boolean cost', p => p.capacity.annualEquivalentCostTRY = true], ['NaN cost', p => p.capacity.annualEquivalentCostTRY = NaN],
  ['wrong bed total', p => p.capacity.totalBeds++], ['false count', p => p.hospitalCount++], ['fractional doctor', p => p.selected[0].doctors = 12.5],
  ['unknown hospital', p => p.selected[0].id = 'other'], ['different physical plot', p => p.selected[0].footprintRadiusMeters = 20], ['coordinate shifted', p => p.selected[0].lon++],
  ['duplicate hospital', p => { p.selected.push(clone(p.selected[0])); p.hospitalCount++; }], ['missing assignment', p => p.profiles.car.assignments.pop()],
  ['duplicate origin', p => p.profiles.car.assignments[1] = clone(p.profiles.car.assignments[0])], ['extra allocation', p => p.profiles.car.assignments[0].allocations.push(clone(p.profiles.car.assignments[0].allocations[0]))],
  ['unknown destination', p => p.profiles.car.assignments[0].allocations[0].candidateId = 'other'], ['wrong candidate index', p => p.profiles.car.assignments[0].allocations[0].candidateIndex = 3],
  ['negative flow', p => p.profiles.car.assignments[0].allocations[0].population = -1], ['wrong share', p => p.profiles.car.assignments[0].allocations[0].fraction = .5],
  ['over30', p => p.profiles.car.assignments[0].allocations[0].minutes = 31], ['over60', p => p.profiles['weekday-0800'].assignments[0].allocations[0].minutes = 61],
  ['changed main time', p => p.profiles.car.assignments[0].minutes = 11], ['fake covered flag', p => p.profiles.car.assignments[0].covered = true],
  ['wrong mean', p => p.profiles.car.metrics.meanMinutes = 9], ['wrong p90', p => p.profiles.car.metrics.p90Minutes = 2], ['fake province%', p => p.profiles.car.metrics.coveragePercent = 99],
  ['changed district population', p => p.profiles.car.districts[0].population = 51], ['fake district%', p => p.profiles.car.districts[0].coveragePercent = 99], ['missing district', p => p.profiles.car.districts.pop()],
  ['duplicate district', p => p.profiles.car.districts[1] = clone(p.profiles.car.districts[0])], ['missing PT evidence', p => delete p.profiles['weekday-0800'].transitEvidence],
  ['old per-profile package', p => p.profiles['weekday-0800'].transitEvidence.packageId = 'motis-'+'c'.repeat(64)], ['wrong clock', p => p.profiles['weekday-0800'].transitEvidence.departure = policy.profileDetails['weekday-1000'].departure],
  ['wrong profile label identity', p => p.profiles.car.profile.id = 'transit'], ['wrong critical', p => p.criticalTransitProfile = 'weekday-0800'],
  ['wrong modal display', p => p.modalResults.transit = p.profiles['weekday-0800']], ['weighted mean', p => p.permanentSummary.weightedMeanMinutes = 12],
  ['annual times five', p => p.permanentSummary.annualDemandCountedOnce = false], ['same people claim', p => p.permanentSummary.sameIndividualsAcrossProfilesConstrained = true],
  ['missing thresholds', p => delete p.permanentSummary.thresholds], ['only four summary', p => p.permanentSummary.profileCount = 4],
  ['mean PT', p => p.permanentSummary.meanTransitMinutes = 0], ['min district', p => p.permanentSummary.minimumDistrictCoveragePercent = 0]
]) test(`reject plan: ${label}`, () => { const r = fixture(); mutate(r); assert.ok(check(r)); });
test('same resources, only display metrics change', () => { const r = fixture(), before = JSON.stringify(r); for (const v of ['car','transit']) { const shown = ui.permanentResultForView(r,v); assert.equal(shown.selected,r.selected); assert.equal(shown.capacity,r.capacity); assert.equal(shown.metrics,r.profiles[v === 'car' ? 'car' : r.criticalTransitProfile].metrics); } assert.equal(JSON.stringify(r),before); });
function route(view = 'transit') { const p = fixture(), id = view === 'car' ? 'car' : p.criticalTransitProfile; return { planId:p.planId, profileId:id,routeMode:view,
  scenario:{...p.scenario,demandId:'D0',candidateId:'H',routingPackageId:pkg,transitProfile:p.criticalTransitProfile}, evidence:{packageId:pkg}, minutes:p.profiles[id].metrics.meanMinutes,
  demand:'Mahalle 0',candidate:'Ortak hastane',note:'Tarihsel kaynak senaryosu',legs:[{kind:'walk',label:'Yaya',coordinates:[[32.8,39.9],[32.81,39.91]]}],boardings:[] }; }
test('route request is only immutable identity and view', () => assert.deepEqual(ui.permanentRouteRequest(fixture(),'transit','D0','H'), {planId:fixture().planId,view:'transit',demandId:'D0',candidateId:'H'}));
test('route rejects unassigned destination', () => assert.throws(() => ui.permanentRouteRequest(fixture(),'transit','D0','other')));
test('valid route is linked to actual displayed profile', () => assert.equal(ui.permanentRouteProblem(route(),fixture(),'transit','D0','H'),null));
test('car route does not require MOTIS package', () => { const r = route('car'); delete r.evidence; delete r.scenario.routingPackageId; assert.equal(ui.permanentRouteProblem(r,fixture(),'car','D0','H'),null); });
for (const [label, mutate] of [
  ['plan changed',r=>r.planId='permanent-'+'c'.repeat(64)],['view changed',r=>r.routeMode='car'],['profile changed',r=>r.profileId='weekday-0800'],
  ['demand changed',r=>r.scenario.demandId='D1'],['site changed',r=>r.scenario.candidateId='other'],['package changed',r=>r.evidence.packageId='motis-'+'c'.repeat(64)],
  ['request package changed',r=>r.scenario.routingPackageId='motis-'+'c'.repeat(64)],['provider changed',r=>r.scenario.transitEngine='ego'],
  ['traffic modified',r=>r.scenario.trafficFactor=2],['capacity modified',r=>r.scenario.contactsPerDoctor=1000],['route threshold modified',r=>r.scenario.transitThreshold=45],
  ['malformed boarding',r=>r.boardings.push({route:'442',stop:'A',mode:'BUS',waitMinutes:NaN})],
  ['minutes changed',r=>r.minutes=29],['nonfinite time',r=>r.minutes=NaN],['invalid geography',r=>r.legs[0].coordinates[0][0]=Infinity],['missing legs',r=>delete r.legs]
]) test(`reject route: ${label}`, () => { const r=route();mutate(r);assert.ok(ui.permanentRouteProblem(r,fixture(),'transit','D0','H')); });
const render = (C, props) => renderToStaticMarkup(React.createElement(C,props));
test('readonly policy has no knobs', () => { const html=render(ui.PermanentTargets,{policy}); assert.ok(html.includes('60'));assert.ok(html.includes('klinik standart değildir'));assert.doesNotMatch(html,/<input|<select|slider/); });
test('coherent critical PT view and limited time scope explained', () => {const html=render(ui.PermanentViews,{plan:fixture(),view:'transit',onView:()=>{}});assert.ok(html.includes('Pazar'));assert.ok(html.includes('bütün günün en kötü durumu değil'));assert.equal((html.match(/<button/g)||[]).length,2);});
test('evidence stays accessible and collapsed',()=>{const html=render(ui.PermanentEvidence,{plan:fixture()});assert.ok(html.startsWith('<details'));assert.doesNotMatch(html,/<details[^>]*open/);assert.ok(html.includes('aynı bireylerin'));assert.ok(html.includes('asgari ihtiyaç değildir'));});
test('fixed capacity and annual accounting explained without controls',()=>{const p=fixture();Object.assign(p.capacity,{horizonYears:25,realDiscountRate:.03,priceBase:'Aralık 2024 TL',referenceCostTRY:1e10,budgetLimitTRY:1.1e10});const html=render(ui.PermanentCalculation,{plan:p});for(const s of ['292','2.140','Klinik FTE','Başvuru + yatış','25','%3','yıllıklaştırılır','yalnız bir kez','10,00 milyar','11,00 milyar','%10'])assert.ok(html.includes(s),s);assert.doesNotMatch(html,/<input|<select|<button/);});
test('native gaps remain stage specific and scope limited',()=>{const p=fixture();Object.assign(p.capacity,{costStageGap:.2,finalPlanCostGap:.3,travelStageGap:.4});p.solver={costStagePerformed:true,travelStagePerformed:true,costTimeLimit:true,travelTimeLimit:false};p.searchScope={restricted:true,retainedCandidateCount:100,allCandidateCount:4701};const html=render(ui.PermanentCalculation,{plan:p});for(const s of ['%20,00','%30,00','%40,00','Süre sınırında sonlandı','daraltılmıştır','100','4.701','bağımsız küresel optimum sertifikası değildir'])assert.ok(html.includes(s),s);});
test('absent or invalid native bound never becomes zero gap',()=>{const p=fixture();Object.assign(p.capacity,{costStageGap:null,finalPlanCostGap:NaN,travelStageGap:true});const html=render(ui.PermanentCalculation,{plan:p});assert.equal((html.match(/Geçerli alt sınır bildirilmedi/g)||[]).length,3);assert.doesNotMatch(html,/%0,00|NaN|Infinity/);assert.ok(html.includes('Çözücü durumu bildirilmedi'));assert.ok(html.includes('bu kayıtta bildirilmedi'));});
test('skipped native stage is distinct from time limit',()=>{const p=fixture();p.solver={costStagePerformed:false,travelStagePerformed:false,costTimeLimit:false,travelTimeLimit:false};const html=render(ui.PermanentCalculation,{plan:p});assert.equal((html.match(/Bu aşama çalıştırılmadı/g)||[]).length,2);assert.doesNotMatch(html,/Süre sınırında sonlandı/);});
test('primary App fetches a saved plan; no scenario solve or adjustable input',()=>{const src=readFileSync('src/App.tsx','utf8'); for(const endpoint of ['/api/data','/api/planning-policy','/api/permanent-plan','/api/permanent-route']) assert.ok(src.includes(endpoint)); assert.doesNotMatch(src,/\/api\/solve|fetch\("\/api\/route|type="range"|type="number"|setScenario|setCarWeight|setTransitProfile/);assert.ok(src.includes('version !== routeVersion.current'));assert.ok(src.includes('clearRoute(); setView(next)'));assert.ok(src.includes('permanentRouteProblem(result, routePlan, routeView'));});
test('packaged permanent plan passes the actual dataset and health source display gate',()=>{
  const actualData = JSON.parse(readFileSync('data/processed/dataset.json','utf8'));
  actualData.healthPlanning = JSON.parse(readFileSync('data/processed/health-planning.json','utf8'));
  const actualPlan = JSON.parse(readFileSync('data/processed/permanent-plan.json','utf8'));
  assert.equal(ui.permanentPlanProblem(actualPlan,actualData,policy),null);
});
test('packaged actual car and transit route responses match the exact published plan',()=>{
  const bytes=readFileSync('data/processed/permanent-plan.json');
  const actualPlan=JSON.parse(bytes.toString('utf8'));
  const checks=JSON.parse(readFileSync('data/processed/permanent-route-checks.json','utf8'));
  assert.equal(checks.format,1);assert.equal(checks.planId,actualPlan.planId);
  assert.equal(checks.sourcePlanSHA256,createHash('sha256').update(bytes).digest('hex'));
  assert.equal(checks.cases.length,2);assert.deepEqual(checks.cases.map(c=>c.request.view).sort(),['car','transit']);
  for(const {request,response,allocatedPopulation} of checks.cases){
    assert.deepEqual(request,ui.permanentRouteRequest(actualPlan,request.view,request.demandId,request.candidateId));
    assert.equal(ui.permanentRouteProblem(response,actualPlan,request.view,request.demandId,request.candidateId),null);
    const profile=actualPlan.profiles[request.view==='car'?'car':actualPlan.criticalTransitProfile];
    const part=profile.assignments.find(a=>a.demandId===request.demandId).allocations.find(a=>a.candidateId===request.candidateId);
    assert.equal(allocatedPopulation,part.population);
  }
});
console.log(`${tests} permanent UI and source/route guard checks passed`);
