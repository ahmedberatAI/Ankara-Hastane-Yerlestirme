"""Audit one saved EGO plan across time profiles without changing its resources.

Normal invocation is read-only and verifies the saved report and its bindings.
--write recomputes and writes data/processed/robustness-results.json.
--profiles-only skips re-solving the explicitly capacity-free geographic
diagnostics during a read-only check; their source bindings are still checked.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.feasibility import geographic_bound
from backend.robustness import evaluate_fixed_plan
from backend.timetable import PROFILES
from scripts.transit_provenance import check_package, sha

OUT = ROOT / 'data/processed'
RURAL_NAMES = ('HAYMANA', 'BALA', 'KIZILCAHAMAM', 'ÇAMLIDERE', 'KALECİK', 'AYAŞ', 'GÜDÜL', 'NALLIHAN')
MODEL_FILES = ('backend/robustness.py', 'scripts/audit_robustness.py',
               'backend/feasibility.py', 'backend/capacity.py', 'backend/optimizer.py')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def aggregate_profiles(profiles):
    values = [r['targetsMet'] for r in profiles]
    if any(v is False for v in values):
        return False, 'some_targets_failed'
    if not values or any(v is None for v in values):
        return None, 'inconclusive'
    return True, 'all_targets_met'


def assert_plan_binding(plan, data, package_id):
    """Reject old or differently indexed plans rather than silently relabeling."""
    if not package_id or data['metadata'].get('transitPackageId') != package_id:
        raise ValueError('Current transit package identity is required')
    if plan.get('metadata', {}).get('transitPackageId') != package_id:
        raise ValueError('Saved plan metadata belongs to another transit package')
    if plan.get('transitEvidence', {}).get('packageId') != package_id:
        raise ValueError('Saved plan transit evidence belongs to another package')
    if plan.get('status') != 'feasible' or plan['scenario']['mode'] != 'transit':
        raise ValueError('Robustness requires a feasible saved EGO plan')
    sites = plan['selected']
    indices = [s['candidateIndex'] for s in sites]
    if len(indices) != len(set(indices)) or set(indices) != set(plan['selectedIndices']):
        raise ValueError('Saved selected-site identities differ')
    if len(indices) != plan['hospitalCount']:
        raise ValueError('Saved hospital count differs')
    for s in sites:
        i = s['candidateIndex']
        if not 0 <= i < len(data['candidates']):
            raise ValueError('Saved candidate index is out of range')
        c = data['candidates'][i]
        if (s['id'], s['lon'], s['lat']) != (c['id'], c['lon'], c['lat']):
            raise ValueError('Saved candidate identity/location differs')
    if [a['demandId'] for a in plan['assignments']] != [d['id'] for d in data['demands']]:
        raise ValueError('Saved demand row identities differ')


def utilization(plan):
    sites = plan['selected']
    occupancy = np.array([s['physicalOccupancyPercent'] for s in sites])
    return {
        'count50BedSites': sum(s['beds'] == 50 for s in sites),
        'countAssignedBelow1000Residents': sum(s['assignedPopulation'] < 1000 for s in sites),
        'countAssignedBelow5000Residents': sum(s['assignedPopulation'] < 5000 for s in sites),
        'medianSitePhysicalOccupancyPercent': float(np.median(occupancy)),
        'sitePhysicalOccupancyQuartilesPercent': np.percentile(occupancy, [25, 50, 75]).tolist(),
        'scope': 'Original saved allocation; site-level percentiles, not a bed-weighted provincial occupancy statistic.',
    }


def run(write=False, plan_path=None, output_path=None, profiles_only=False, geography_time_limit=20):
    if write and profiles_only:
        raise ValueError('--write always includes the complete geographic diagnostic grid')
    plan_path = Path(plan_path or OUT / 'example-transit-result.json').resolve()
    output_path = Path(output_path or OUT / 'robustness-results.json').resolve()
    package_id = check_package(ROOT)
    data = read(OUT / 'dataset.json')
    planning = read(OUT / 'health-planning.json')
    plan = read(plan_path)
    assert_plan_binding(plan, data, package_id)
    if plan.get('capacity', {}).get('planningVersion') != planning['version']:
        raise ValueError('Saved plan uses another health-planning calibration')
    scenario = plan['scenario']
    selected = plan['selected']
    indices = [s['candidateIndex'] for s in selected]
    populations = np.array([d['population'] for d in data['demands']])
    demand_districts = np.array([d['districtId'] for d in data['demands']])
    total = data['metadata']['provincePopulation']
    binding = {
        'file': str(plan_path.relative_to(ROOT)).replace('\\', '/'),
        'sha256': sha(plan_path), 'transitPackageId': package_id,
        'scenario': scenario, 'hospitalCount': plan['hospitalCount'],
        'totalBeds': sum(s['beds'] for s in selected),
        'totalDoctors': sum(s['doctors'] for s in selected),
        'healthPlanningSha256': sha(OUT / 'health-planning.json'),
        'annualBudgetLimitTRY': plan['capacity']['budgetLimitTRY'],
    }
    report = {
        'format': 1, 'transitPackageId': package_id, 'sourcePlan': binding,
        'builtAt': datetime.now(timezone.utc).isoformat(),
        'modelFiles': {name: sha(ROOT / name, True) for name in MODEL_FILES},
        'scope': 'A static saved-plan stress test. Same sites/beds/physicians and original annual budget in every profile; annual demand and costs are not accumulated across profiles. Partial transit data, estimated times and partial cost calibration remain uncertain.',
        'profiles': [], 'utilization': utilization(plan),
    }
    saved = None
    if not write:
        saved = read(output_path)
        assert saved['transitPackageId'] == package_id, 'Robustness report is bound to another transit package'
        assert saved['sourcePlan'] == binding, 'Robustness source-plan SHA, scenario or calibration differs'
        assert saved['modelFiles'] == report['modelFiles'], 'Robustness model code changed; regenerate the report'
    matrices = {}
    for profile, spec in PROFILES.items():
        matrix = np.load(OUT / f'transit-{profile}-matrix.npz')['minutes']
        matrices[profile] = matrix[:, :len(data['candidates'])]
        result = evaluate_fixed_plan(matrix[:, indices], populations, demand_districts,
            data['districts'], total, selected, planning, scenario,
            annual_budget=binding['annualBudgetLimitTRY'])
        report['profiles'].append({'profile': profile, 'label': spec['label'], **result})
        print('Fixed plan', profile, result['status'], result['maximumCoveragePercent'], flush=True)
    report['allProfilesTargetsMet'], report['aggregateStatus'] = aggregate_profiles(report['profiles'])
    if saved is not None:
        assert len(saved['profiles']) == len(report['profiles'])
        for old, new in zip(saved['profiles'], report['profiles']):
            assert old['profile'] == new['profile'] and old['status'] == new['status'], 'Fixed-plan profile status changed'
            for key in ('maximumCoveragePercent', 'maximumCoveredPopulation', 'populationShortfall'):
                if key in new and new[key] is not None:
                    assert abs(old[key] - new[key]) < .001, f'Fixed-plan optimum changed: {key}'
            assert old['targetsMet'] == new['targetsMet']
            assert old['annualBudget'] == new['annualBudget'], 'Fixed-plan budget calibration changed'
            if new.get('annualEquivalentCostTRY') is not None:
                assert abs(old['annualEquivalentCostTRY'] - new['annualEquivalentCostTRY']) < 1, 'Fixed-plan annual cost changed'
            if new.get('withoutDistrictTargets') is not None:
                assert old.get('withoutDistrictTargets') is not None
                assert abs(old['withoutDistrictTargets']['maximumCoveredPopulation'] -
                           new['withoutDistrictTargets']['maximumCoveredPopulation']) < .001
        assert saved['allProfilesTargetsMet'] == report['allProfilesTargetsMet']
        assert saved['aggregateStatus'] == report['aggregateStatus']
        assert saved['utilization'] == report['utilization']
    if not profiles_only:
        rural = [d for d in data['districts'] if d['name'] in RURAL_NAMES]
        assert len(rural) == len(RURAL_NAMES), 'Rural district identity missing'
        profile = scenario['transitProfile']
        diagnostic = {
            'scope': 'Geographic count relaxation only: no beds, physicians, costs or footprint-overlap constraints. All sampled candidates and threshold-feasible edges. Does not prove a real-world hospital need or a capacitated plan.',
            'ruralDistricts': [{'id': d['id'], 'name': d['name']} for d in rural],
            'ruralPopulation': sum(d['population'] for d in rural),
            'ruralProfile': profile, 'ruralCoverageTargetPercent': 0,
            'ruralDistrictFloorPercent': scenario['districtFloor'],
            'ruralThresholdMinutes': scenario['threshold'], 'sensitivity': [],
        }
        diagnostic['ruralPopulationSharePercent'] = diagnostic['ruralPopulation'] / total * 100
        diagnostic['ruralCertificate'] = geographic_bound(matrices[profile], populations,
            demand_districts, rural, total, scenario['threshold'], 0,
            scenario['districtFloor'] / 100, time_limit=geography_time_limit)
        print('Rural-only geographic certificate', diagnostic['ruralCertificate'], flush=True)
        for profile in PROFILES:
            for threshold in (45, 60, 90):
                for floor in (60, 80):
                    certificate = geographic_bound(matrices[profile], populations, demand_districts,
                        data['districts'], total, threshold, scenario['coverageTarget'] / 100,
                        floor / 100, time_limit=geography_time_limit)
                    diagnostic['sensitivity'].append({'profile': profile, 'thresholdMinutes': threshold,
                        'districtFloorPercent': floor, 'coverageTargetPercent': scenario['coverageTarget'],
                        'certificate': certificate})
                    print('Geographic sensitivity', profile, threshold, floor,
                          certificate['minimumCountLowerBound'], certificate['feasibleGeographicCount'], flush=True)
        report['geographicDiagnostics'] = diagnostic
        if saved is not None:
            previous = saved['geographicDiagnostics']
            assert previous['ruralDistricts'] == diagnostic['ruralDistricts']
            assert previous['ruralPopulation'] == diagnostic['ruralPopulation']
            assert len(previous['sensitivity']) == len(diagnostic['sensitivity'])
            pairs = [(previous['ruralCertificate'], diagnostic['ruralCertificate'])]
            for old, new in zip(previous['sensitivity'], diagnostic['sensitivity']):
                assert all(old[k] == new[k] for k in ('profile', 'thresholdMinutes', 'districtFloorPercent', 'coverageTargetPercent'))
                pairs.append((old['certificate'], new['certificate']))
            for old, new in pairs:
                # Time-limited bounds may improve between runs. Contradictory
                # intervals fail; exact old minima must agree with exact new ones.
                for lower, feasible in ((old['minimumCountLowerBound'], new['feasibleGeographicCount']),
                                        (new['minimumCountLowerBound'], old['feasibleGeographicCount'])):
                    if lower is not None and feasible is not None:
                        assert lower <= feasible + 1e-6, 'Geographic bound intervals contradict'
                if old['status'] == 'infeasible':
                    assert new['feasibleGeographicCount'] is None, 'Saved infeasibility contradicts a new feasible geography'
                if new['status'] == 'infeasible':
                    assert old['feasibleGeographicCount'] is None, 'New infeasibility contradicts saved feasible geography'
                if old['status'] == new['status'] == 'optimal':
                    assert abs(old['minimumCountLowerBound'] - new['minimumCountLowerBound']) < 1e-6
    if write:
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
                               encoding='utf-8', newline='\n')
        print('Wrote', output_path, flush=True)
    else:
        print('Verified fixed-plan robustness and source bindings; no files changed.', flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--profiles-only', action='store_true')
    parser.add_argument('--geography-time-limit', type=float, default=20)
    args = parser.parse_args()
    run(args.write, args.plan, args.output, args.profiles_only, args.geography_time_limit)
