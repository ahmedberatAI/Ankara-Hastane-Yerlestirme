"""Audit shared resources at the CURRENT saved plan's fixed hospital plots.

--write creates shared-capacity-results.json. Normal invocation is read-only,
checks exact source/code identities, independently re-audits saved flows/costs,
reproduces physical capacity ceilings, and recertifies advertised MILP bounds.
There is deliberately no stale/frozen-source bypass.
"""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix, vstack

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.shared_capacity import repair_shared_capacity, SCOPE, BOUND_SCOPE, AREA_NUMERICAL_TOLERANCE_M2
from scripts.transit_provenance import check_package, sha

PROFILES = ('weekday-0800', 'weekday-1000', 'saturday-1000', 'sunday-1000')
MODEL_FILES = ('backend/shared_capacity.py', 'backend/capacity.py', 'backend/optimizer.py',
               'backend/main.py', 'backend/timetable.py', 'scripts/verify_release.py',
               'scripts/audit_shared_capacity.py', 'scripts/transit_provenance.py')
REPORT_SCOPE = ('Static saved-plan diagnosis: preserve every current selected location and footprint, '
                'share bed modules/physicians across four profiles with separate assignments. '
                'Not a new location plan, minimum hospital count, real-city infeasibility proof '
                'or clinical staffing standard. Recompute after any package/plan/calibration change.')


def _close(actual, expected, tolerance=.001):
    assert actual is not None and np.isfinite(actual), 'Missing/nonfinite numeric claim'
    assert abs(actual - expected) <= tolerance, f'Claim differs: {actual} != {expected}'


def _annuity(planning):
    e = planning['economics']; r, years = e['realDiscountRate'], e['horizonYears']
    return r / (1 - (1 + r) ** -years) if r else 1 / years


def validate_source_identity(plan, data, planning, package):
    """Identity check supplements verify_release.audit's full physical audit."""
    assert plan['status'] == 'feasible' and plan['scenario']['mode'] == 'transit'
    assert plan['metadata']['transitPackageId'] == data['metadata']['transitPackageId'] == package
    assert plan['transitEvidence']['packageId'] == package
    assert plan['capacity']['planningVersion'] == planning['version']
    s = plan['scenario']
    assert (s['threshold'], s['coverageTarget'], s['districtFloor']) == (45, 95, 80)
    assert s['transitProfile'] in PROFILES
    sites = plan['selected']; ids = [x['candidateIndex'] for x in sites]
    assert len(ids) == len(set(ids)) == plan['hospitalCount'] > 0
    assert set(ids) == set(plan['selectedIndices'])
    for site in sites:
        i = site['candidateIndex']
        assert isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(data['candidates'])
        original = data['candidates'][i]
        for key in ('id', 'lon', 'lat', 'node', 'entryLon', 'entryLat', 'accessMeters', 'footprintRadiusMeters'):
            assert site[key] == original[key], f'Saved site identity/footprint differs: {key}'
    assert [a['demandId'] for a in plan['assignments']] == [d['id'] for d in data['demands']]
    expected_districts = {d['id']: d for d in data['districts']}
    saved_districts = plan['districts']
    assert len(expected_districts) == len(data['districts']) > 0
    assert len(saved_districts) == len(expected_districts)
    assert {d['id'] for d in saved_districts} == set(expected_districts), 'Saved district identities/completeness differ'
    for district in saved_districts:
        population = district['population']
        assert not isinstance(population, bool) and np.isfinite(population) and population > 0
        assert population == expected_districts[district['id']]['population'], 'Saved district population denominator differs'
    budget = plan['capacity']['budgetLimitTRY']
    assert np.isfinite(budget) and budget >= 0


def independent_resource_ceiling(matrices, populations, demand_districts, districts,
                                 province_total, sites, planning, scenario, time_limit=30):
    """Optimistic physical upper envelope for homogeneous demand, without cost.

    Each plot independently takes the template/maximum staff pair maximizing
    min(bed-resident capacity, physician-resident capacity). No feasible shared
    resource design can exceed these site capacities in any profile. The same
    .001 m2 final area tolerance is added BEFORE integer rounding, then rounded
    one floating-point step toward +infinity. This can only weaken a bound; it
    cannot exclude a staff count accepted at a nearly integral plot boundary.
    """
    assert time_limit > 0 and np.isfinite(time_limit)
    pop = np.asarray(populations, dtype=float); dd = np.asarray(demand_districts)
    assert pop.ndim == 1 and dd.shape == pop.shape and np.all(np.isfinite(pop)) and np.all(pop >= 0)
    assert province_total > 0 and pop.sum() <= province_total + .001
    rates, design = planning['rates'], planning['design']
    contact = rates['contactsPerResident'] * scenario['demandMultiplier']
    bedrate = rates['bedDaysPerResident'] * scenario['demandMultiplier']
    assert contact > 0 and bedrate > 0
    capacities, impossible = [], []
    for site in sites:
        choices = []
        for template in planning['templates']:
            available = math.pi * site['footprintRadiusMeters'] ** 2 * design['maxFloors']
            physicians = math.floor(math.nextafter(
                (available + AREA_NUMERICAL_TOLERANCE_M2 - template['grossAreaM2']) / design['areaPerDoctorM2'], math.inf))
            if physicians >= design['minimumDoctorsPerSite']:
                choices.append(min(physicians * scenario['contactsPerDoctor'] / contact,
                    template['beds'] * 365 * scenario['bedOccupancy'] / 100 / bedrate))
        if not choices:
            impossible.append(site['candidateIndex'])
        capacities.append(max(choices) if choices else None)
    target = province_total * scenario['coverageTarget'] / 100
    quota = np.array([d['population'] * scenario['districtFloor'] / 100 for d in districts])
    lookup = {d['id']: i for i, d in enumerate(districts)}
    assert len(lookup) == len(districts) and set(dd).issubset(lookup)
    rows = []
    for profile, times in matrices.items():
        times = np.asarray(times)
        assert times.shape == (len(pop), len(sites)) and not np.any(np.isnan(times)) and not np.any(times < 0)
        base = {'profile': profile, 'status': None, 'maximumCoveredPopulation': None,
                'maximumCoveragePercent': None, 'certifiedPopulationUpperBound': None,
                'provinceTargetShortfallResidents': None, 'linearProgrammingDualCertified': False,
                'districtTargetsFeasible': None, 'provinceTargetPossible': None,
                'solverStatus': None, 'reason': None}
        if impossible:
            rows.append({**base, 'status': 'mandatory_site_infeasible', 'provinceTargetPossible': False,
                         'reason': 'A mandatory plot cannot fit any template/minimum physician count.'})
            continue
        origin, dest = np.where(np.isfinite(times) & (times <= scenario['threshold']))
        edges = len(origin)
        if not edges:
            if np.any(quota > 0):
                rows.append({**base, 'status': 'district_targets_infeasible', 'provinceTargetPossible': False,
                             'districtTargetsFeasible': False, 'reason': 'No access edges can meet positive district floors.'})
            else:
                rows.append({**base, 'status': 'optimal', 'maximumCoveredPopulation': 0.,
                    'maximumCoveragePercent': 0., 'certifiedPopulationUpperBound': 0.,
                    'provinceTargetShortfallResidents': target, 'linearProgrammingDualCertified': True,
                    'districtTargetsFeasible': True, 'provinceTargetPossible': target <= .001,
                    'reason': 'No access edges; zero service is the exact optimum.'})
            continue
        edge = np.arange(edges); n, m = len(pop), len(sites)
        A = coo_matrix((np.ones(edges * 2), (np.r_[origin, n + dest], np.tile(edge, 2))), shape=(n + m, edges))
        district_rows = np.array([lookup[dd[i]] for i in origin])
        D = coo_matrix((-np.ones(edges), (district_rows, edge)), shape=(len(districts), edges))
        A = vstack([A, D], format='csr'); b = np.r_[pop, capacities, -quota] / 1000
        solution = linprog(-np.ones(edges), A_ub=A, b_ub=b, bounds=(0, None), method='highs',
                           options={'time_limit': time_limit})
        base['solverStatus'] = int(solution.status)
        if solution.status == 2:
            rows.append({**base, 'status': 'district_targets_infeasible', 'provinceTargetPossible': False,
                         'districtTargetsFeasible': False, 'reason': 'Even maximum physical capacities cannot jointly meet district floors.'})
            continue
        if not solution.success:
            rows.append({**base, 'status': 'inconclusive', 'reason': solution.message})
            continue
        flow = np.asarray(solution.x); dual = np.asarray(solution.ineqlin.marginals)
        dual_objective = float(dual @ b)
        valid = (np.all(np.isfinite(flow)) and np.all(flow >= -1e-8) and np.all(A @ flow <= b + 1e-7)
                 and np.all(np.isfinite(dual)) and np.all(dual <= 1e-8)
                 and np.all(-np.ones(edges) - A.T @ dual >= -1e-8)
                 and abs(dual_objective - solution.fun) <= 1e-6)
        if not valid:
            rows.append({**base, 'status': 'inconclusive', 'reason': 'LP primal/dual numerical validation failed.'})
            continue
        # Repair tiny dual-sign/reduced-cost residuals using known per-edge
        # origin-population upper bounds. Never turn a numerically optimistic
        # dual value into a false impossibility certificate.
        safe_dual = np.minimum(dual, 0)
        reduced = -np.ones(edges) - A.T @ safe_dual
        safe_lower = float(safe_dual @ b + np.minimum(reduced, 0) @ (pop[origin] / 1000))
        maximum = float(-solution.fun * 1000)
        upper = max(maximum, float(-safe_lower * 1000))
        rows.append({**base, 'status': 'optimal', 'maximumCoveredPopulation': maximum,
                     'maximumCoveragePercent': maximum / province_total * 100,
                     'certifiedPopulationUpperBound': upper,
                     'provinceTargetShortfallResidents': max(0., target - upper),
                     'linearProgrammingDualCertified': True, 'districtTargetsFeasible': True,
                     'provinceTargetPossible': upper >= target - .001})
    return {'scope': 'Independent physical capacity upper bound at the same mandatory plots; costs and budget removed, district floors retained. Includes 0.001 m2 optimistic area tolerance before integer rounding. Homogeneous clinical rates only; not all candidate sites or real Ankara.',
            'impossibleMandatorySiteIndices': impossible, 'profiles': rows,
            'anyProfileProvesTargetsImpossible': any(r['provinceTargetPossible'] is False for r in rows)}


def audit_shared_result(result, matrices, populations, demand_districts, districts,
                        province_total, sites, planning, scenario, budget):
    """Recompute serialized allocations and money, independently of MILP rows."""
    pop = np.asarray(populations); dd = np.asarray(demand_districts)
    target = province_total * scenario['coverageTarget'] / 100
    ids = [s['candidateIndex'] for s in sites]; index = {v: i for i, v in enumerate(ids)}
    assert result['hospitalCount'] == len(ids) and result['allSitesMandatoryOpen'] is True
    assert result['allSelectedSiteEdges'] is True and result['annualDemandCountedOnce'] is True
    assert result['budgetIsOptimizationConstraint'] is False
    assert result['profileNames'] == list(matrices) and result['scope'] == SCOPE
    assert result['boundScope'] == BOUND_SCOPE
    assert result['planningVersion'] == planning.get('version')
    _close(result['servedPopulationPerProfile'], target)
    _close(result['originalAnnualBudgetTRY'], budget)
    for field, expected in [('thresholdMinutes', scenario['threshold']),
                            ('coverageTargetPercent', scenario['coverageTarget']),
                            ('districtFloorPercent', scenario['districtFloor'])]:
        _close(result[field], expected)
    if result['status'] != 'feasible':
        assert result['status'] in ('infeasible', 'inconclusive')
        assert result['selected'] == [] and result['profiles'] == []
        assert all(result.get(key) is None for key in ('totalBeds', 'totalDoctors', 'annualEquivalentCostTRY',
            'annualFixedResourceCostTRY', 'annualMaterialCostTRY', 'costGap', 'numericFlowCorrectionResidents'))
        assert result['budgetStatus'] == ('targets_infeasible' if result['status'] == 'infeasible' else 'inconclusive')
        assert result['meetsOriginalBudget'] is (False if result['status'] == 'infeasible' else None)
        assert result['provenOptimal'] is False and result['incumbentValidated'] is False
        assert result['timeLimitedFeasible'] is False
        if result['status'] == 'infeasible':
            assert result.get('solverStatus') in (None, 2)
        return
    assert result['solverStatus'] in (0, 1)
    chosen = result['selected']
    assert [c['candidateIndex'] for c in chosen] == ids
    e, design, rates = planning['economics'], planning['design'], planning['rates']
    crf = _annuity(planning); fixed = 0.
    contact = rates['contactsPerResident'] * scenario['demandMultiplier']
    bedrate = rates['bedDaysPerResident'] * scenario['demandMultiplier']
    for current, original in zip(chosen, sites):
        assert current['id'] == original.get('id')
        assert current['footprintRadiusMeters'] == original['footprintRadiusMeters']
        t = next(t for t in planning['templates'] if t['id'] == current['templateId'])
        docs = current['doctors']
        assert not isinstance(docs, bool) and int(docs) == docs >= design['minimumDoctorsPerSite']
        assert current['beds'] == t['beds']
        area = t['grossAreaM2'] + docs * design['areaPerDoctorM2']
        _close(current['grossAreaM2'], area, .001)
        assert area <= math.pi * original['footprintRadiusMeters'] ** 2 * design['maxFloors'] + AREA_NUMERICAL_TOLERANCE_M2
        fixed += area * e['buildingUnitCostTRY'] * crf + scenario.get('operatingCostMultiplier', 1) * (
            e['annualFixedSiteCostTRY'] + current['beds'] * e['annualBedSupportCostTRY'] + docs * e['annualDoctorCostTRY'])
    variable = target * contact * e['costPerContactTRY'] * scenario.get('operatingCostMultiplier', 1)
    annual = fixed + variable
    _close(result['annualEquivalentCostTRY'], annual, 1.)
    _close(result['annualFixedResourceCostTRY'], fixed, 1.)
    _close(result['annualMaterialCostTRY'], variable, 1.)
    assert result['totalBeds'] == sum(c['beds'] for c in chosen)
    assert result['totalDoctors'] == sum(c['doctors'] for c in chosen)
    assert [p['profile'] for p in result['profiles']] == list(matrices)
    for profile in result['profiles']:
        name = profile['profile']; matrix = matrices[name]
        served = np.zeros(len(pop)); loads = np.zeros(len(ids)); travel = 0.
        for a in profile['allocations']:
            i, j, value = a['demandIndex'], index[a['candidateIndex']], a['population']
            assert isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(pop)
            assert np.isfinite(value) and value > 0
            assert np.isfinite(matrix[i, j]) and matrix[i, j] <= scenario['threshold']
            _close(a['minutes'], matrix[i, j], 1e-6)
            served[i] += value; loads[j] += value; travel += value * matrix[i, j]
        assert np.all(served <= pop + .001)
        _close(served.sum(), target)
        _close(profile['coveredPopulation'], target)
        _close(profile['coveragePercent'], target / province_total * 100, 1e-6)
        if target:
            _close(profile['meanMinutes'], travel / target, 1e-6)
        else:
            assert profile['meanMinutes'] is None
        assert np.asarray(profile['siteLoads']).shape == loads.shape
        assert np.allclose(profile['siteLoads'], loads, atol=.001, rtol=0)
        assert [d['id'] for d in profile['districts']] == [d['id'] for d in districts]
        for d, saved in zip(districts, profile['districts']):
            coverage = served[dd == d['id']].sum() / d['population'] * 100
            assert coverage >= scenario['districtFloor'] - 1e-6
            _close(saved['coveragePercent'], coverage, 1e-6)
        assert np.all(loads * contact <= np.array([c['doctors'] for c in chosen]) * scenario['contactsPerDoctor'] + .1)
        assert np.all(loads * bedrate <= np.array([c['beds'] for c in chosen]) * 365 * scenario['bedOccupancy'] / 100 + .1)
        assert result['allocationEdgesByProfile'][name] == int((np.isfinite(matrix) & (matrix <= scenario['threshold'])).sum())
    bound = result.get('minimumAnnualCostLowerBoundTRY')
    tolerance = max(.01, abs(annual) * 1e-9)
    _close(result['costNumericalToleranceTRY'], tolerance, 1e-8)
    if bound is not None:
        assert np.isfinite(bound) and bound <= annual + tolerance
        gap = max(0., (annual - bound) / annual) if annual else 0.
        _close(result['costGap'], gap, 1e-8)
    else:
        assert result['costGap'] is None
    assert result['provenOptimal'] is (result['costGap'] is not None and result['costGap'] <= 1e-8)
    assert result['timeLimitedFeasible'] is (result['solverStatus'] == 1)
    assert result['incumbentValidated'] is True
    met = annual <= budget + tolerance
    assert result['meetsOriginalBudget'] is met
    expected = ('feasible_within_original_budget' if met else
                'proven_over_original_budget_for_fixed_sites' if bound is not None and bound > budget + tolerance
                else 'incumbent_over_budget_unresolved')
    assert result['budgetStatus'] == expected


def verify_ceiling_record(saved, fresh):
    assert saved['scope'] == fresh['scope']
    assert saved['impossibleMandatorySiteIndices'] == fresh['impossibleMandatorySiteIndices']
    assert [x['profile'] for x in saved['profiles']] == [x['profile'] for x in fresh['profiles']]
    for old, new in zip(saved['profiles'], fresh['profiles']):
        if old['status'] == 'optimal':
            assert new['status'] == 'optimal', 'Cannot recertify saved physical capacity optimum'
            for field in ('maximumCoveredPopulation', 'maximumCoveragePercent', 'certifiedPopulationUpperBound',
                          'provinceTargetShortfallResidents'):
                _close(old[field], new[field])
            assert old['linearProgrammingDualCertified'] is True and old['districtTargetsFeasible'] is True
            assert old['provinceTargetPossible'] == new['provinceTargetPossible']
        else:
            assert old['status'] in ('inconclusive', 'district_targets_infeasible', 'mandatory_site_infeasible')
            assert all(old[key] is None for key in ('maximumCoveredPopulation', 'maximumCoveragePercent',
                                                  'certifiedPopulationUpperBound', 'provinceTargetShortfallResidents'))
            assert old['linearProgrammingDualCertified'] is False
            if old['status'] == 'inconclusive':
                assert old['provinceTargetPossible'] is None and old['districtTargetsFeasible'] is None
            else:
                assert old['status'] == new['status'], 'Cannot recertify physical infeasibility'
                assert old['provinceTargetPossible'] is False
                assert old['districtTargetsFeasible'] is (False if old['status'] == 'district_targets_infeasible' else None)
    assert saved['anyProfileProvesTargetsImpossible'] is any(p['provinceTargetPossible'] is False for p in saved['profiles'])


def verify_recomputed_claims(saved_result, fresh_result, ceiling):
    """A slower/changed solve cannot silently certify a stronger saved bound."""
    certificate = ceiling['anyProfileProvesTargetsImpossible']
    if saved_result['status'] == 'infeasible':
        assert fresh_result['status'] != 'feasible', 'Saved infeasibility contradicts a new valid design'
        assert certificate or fresh_result['status'] == 'infeasible', 'No reproduced proof of saved infeasibility'
    elif saved_result['status'] == 'feasible':
        assert not certificate and fresh_result['status'] != 'infeasible', 'Saved design contradicts physical infeasibility'
    bound = saved_result.get('minimumAnnualCostLowerBoundTRY')
    if bound is not None:
        fresh_bound = fresh_result.get('minimumAnnualCostLowerBoundTRY')
        tolerance = max(.01, abs(bound) * 1e-9)
        assert fresh_bound is not None and fresh_bound + tolerance >= bound, 'Fresh solve too weak to recertify saved cost lower bound; retry with longer limit'
        if fresh_result['status'] == 'feasible':
            assert bound <= fresh_result['annualEquivalentCostTRY'] + tolerance


def verify_bindings(saved, package, source_plan, source_files, model_files):
    assert saved['format'] == 1 and saved['scope'] == REPORT_SCOPE
    assert saved['transitPackageId'] == package and saved['sourcePlan'] == source_plan, 'Shared capacity report source plan/package changed'
    assert saved['sourceFiles'] == source_files, 'Shared capacity input hashes changed'
    assert saved['modelFiles'] == model_files, 'Shared capacity audit/model code changed; regenerate'


def run(write=False, time_limit=60, ceiling_time_limit=30):
    out = ROOT / 'data/processed'; output = out / 'shared-capacity-results.json'
    package = check_package(ROOT)  # No bypass: never audit old matrices as a new model.
    source_files = ('data/processed/example-transit-result.json', 'data/processed/dataset.json',
                    'data/processed/health-planning.json', 'data/processed/transit-package.json',
                    *(f'data/processed/transit-{name}-matrix.npz' for name in PROFILES))
    # Capture before reading any input, then recheck after every computation.
    hashes = {f: sha(ROOT / f) for f in source_files}
    model_hashes = {f: sha(ROOT / f, True) for f in MODEL_FILES}
    read = lambda path: json.loads(path.read_text(encoding='utf-8'))
    plan_path = out / 'example-transit-result.json'
    data, planning, plan = read(out / 'dataset.json'), read(out / 'health-planning.json'), read(plan_path)
    validate_source_identity(plan, data, planning, package)
    from scripts.verify_release import audit, verify_result_package
    verify_result_package(plan, package)
    audit(plan)  # Original allocations, cost, physical area, overlaps and quotas.
    sites, scenario = plan['selected'], plan['scenario']
    ids = [s['candidateIndex'] for s in sites]
    pop = np.array([d['population'] for d in data['demands']]); dd = np.array([d['districtId'] for d in data['demands']])
    total = data['metadata']['provincePopulation']; budget = plan['capacity']['budgetLimitTRY']
    matrices = {name: np.load(out / f'transit-{name}-matrix.npz')['minutes'][:, ids] for name in PROFILES}
    binding = {'file': 'data/processed/example-transit-result.json', 'sha256': hashes['data/processed/example-transit-result.json'],
               'transitPackageId': package, 'hospitalCount': plan['hospitalCount'], 'scenario': scenario,
               'originalAnnualBudgetTRY': budget, 'totalBeds': plan['capacity']['totalBeds'],
               'totalDoctors': plan['capacity']['totalDoctors'],
               'healthPlanningSha256': hashes['data/processed/health-planning.json']}
    saved = None
    if not write:
        saved = read(output)
        verify_bindings(saved, package, binding, hashes, model_hashes)
        audit_shared_result(saved['result'], matrices, pop, dd, data['districts'], total, sites, planning, scenario, budget)
    result = repair_shared_capacity(matrices, pop, dd, data['districts'], total, sites, planning, scenario,
                                    original_annual_budget=budget, time_limit=time_limit)
    for key in ('reason', 'totalBeds', 'totalDoctors', 'annualEquivalentCostTRY', 'costGap'):
        result.setdefault(key, None)
    audit_shared_result(result, matrices, pop, dd, data['districts'], total, sites, planning, scenario, budget)
    ceiling = independent_resource_ceiling(matrices, pop, dd, data['districts'], total, sites, planning, scenario, ceiling_time_limit)
    verify_ceiling_record(ceiling, ceiling)
    verify_recomputed_claims(result, result, ceiling)
    if saved:
        verify_ceiling_record(saved['independentResourceCeiling'], ceiling)
        verify_recomputed_claims(saved['result'], result, ceiling)
    assert hashes == {f: sha(ROOT / f) for f in source_files}, 'Sources changed during shared audit'
    assert model_hashes == {f: sha(ROOT / f, True) for f in MODEL_FILES}, 'Code changed during shared audit'
    assert check_package(ROOT) == package
    report = {'format': 1, 'builtAt': datetime.now(timezone.utc).isoformat(), 'transitPackageId': package,
              'scope': REPORT_SCOPE, 'sourcePlan': binding, 'sourceFiles': hashes, 'modelFiles': model_hashes,
              'result': result, 'independentResourceCeiling': ceiling}
    if write:
        temporary = output.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')
        temporary.replace(output)
        print('Wrote', output, flush=True)
    else:
        print('Verified shared capacity source/hash/flow/cost/bounds; no files changed.', flush=True)
    print('Shared fixed-site design:', result['status'], result['budgetStatus'], flush=True)
    for row in ceiling['profiles']:
        print('Physical capacity ceiling:', row['profile'], row['status'], row['maximumCoveragePercent'], flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--time-limit', type=float, default=60)
    parser.add_argument('--ceiling-time-limit', type=float, default=30)
    args = parser.parse_args()
    run(args.write, args.time_limit, args.ceiling_time_limit)
