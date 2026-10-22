"""Check the packaged data and both complete solve/route flows without a server."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import numpy as np
from backend.main import app, matrix, dataset, travel_times, Scenario, health_planning, site_conflicts

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/processed'

def run(write_examples=False):
    manifest_path = OUT/'manifest.json'
    if manifest_path.exists() and not write_examples:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        for record in manifest['files']:
            path = (ROOT/record['file']).resolve()
            assert path.is_relative_to(OUT.resolve()), 'Manifest path outside the packaged dataset'
            with path.open('rb') as f:
                actual = hashlib.file_digest(f,'sha256').hexdigest()
            assert actual == record['sha256'], f'Dataset integrity mismatch: {record["file"]}'
    client = TestClient(app)
    data = dataset()
    assert len(data['districts']) == 25
    assert sum(d['population'] for d in data['districts']) == data['metadata']['provincePopulation']
    assert sum(d['population'] for d in data['demands']) == data['metadata']['matchedPopulation']
    n, m = len(data['demands']), len(data['candidates']) + len(data['hospitals'])
    for mode in ('car', 'transit'):
        a = matrix(mode)
        assert a.shape == (n, m) and not np.isnan(a).any() and np.all(a >= 0)
    assert client.get('/api/data').status_code == 200
    for name in ('districts', 'province', 'roads', 'transit-lines'):
        assert client.get('/api/layers/' + name).status_code == 200
    if (ROOT/'dist/index.html').exists():
        assert client.get('/').status_code == 200
    report = []
    for mode, threshold in [('car', 30), ('transit', 45)]:
        scenario = {'mode': mode, 'threshold': threshold, 'coverageTarget': 95, 'districtFloor': 80, 'trafficFactor': 1}
        response = client.post('/api/solve', json=scenario)
        assert response.status_code == 200, response.text
        result = response.json()
        if write_examples:
            (OUT/f'example-{mode}-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8', newline='\n')
        summary = {'mode': mode, 'scenario': result['scenario'], 'status': result['status'],
                   'hospitalCount': result.get('hospitalCount'), 'metrics': result.get('metrics'),
                   'capacity': result.get('capacity'), 'searchScope': result.get('searchScope')}
        if result['status'] == 'infeasible':
            assert 'maximumCoveragePercent' in result
            summary['maximumCoveragePercent'] = result['maximumCoveragePercent']
            summary['limitingDistricts'] = result['limitingDistricts']
            # An explicitly labelled alternate case, not a silent default change.
            scenario = {**scenario, 'coverageTarget': max(50, int(result['maximumCoveragePercent']//5)*5),
                        'districtFloor': min([80]+[max(0,int(d['maximumPercent']//5)*5) for d in result['limitingDistricts']])}
            result = client.post('/api/solve', json=scenario).json()
            if write_examples:
                (OUT/f'example-{mode}-alternate-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8', newline='\n')
            summary['alternate'] = {'scenario': scenario, 'status': result['status'],
                                    'hospitalCount': result.get('hospitalCount'), 'metrics': result.get('metrics')}
        assert result['status'] in ('optimal','feasible'), result
        selected = result['selectedIndices']
        times = travel_times(Scenario(**scenario))
        populations = np.array([d['population'] for d in data['demands']])
        # Rebuild load from split flows, not from nearest geographic hospital.
        assigned = np.zeros(n)
        loads = {j: 0. for j in selected}
        weighted_time = 0.
        weighted_edges = []
        for i, (a, demand) in enumerate(zip(result['assignments'], data['demands'])):
            assert a['demandId'] == demand['id']
            for part in a['allocations']:
                j, population = part['candidateIndex'], part['population']
                assert j in selected and population >= 0
                assert part['candidateId'] == data['candidates'][j]['id']
                assert abs(part['minutes'] - times[i,j]) < 1e-6
                assert part['minutes'] <= scenario['threshold'] + 1e-7
                assert abs(part['fraction'] - population / populations[i]) < 1e-6
                assigned[i] += population; loads[j] += population
                weighted_time += population * times[i,j]
                weighted_edges.append((part['minutes'], population))
            assert assigned[i] <= populations[i] + .001
            assert abs(a['servedFraction'] - assigned[i] / populations[i]) < 1e-6
            assert a['covered'] == bool(assigned[i] >= populations[i] - 1e-4)
            if a['allocations']:
                assert a['candidateId'] == a['allocations'][0]['candidateId']
                assert a['minutes'] == a['allocations'][0]['minutes']
            else:
                assert a['candidateId'] is None and a['minutes'] is None
        covered = float(assigned.sum())
        assert abs(covered - result['metrics']['coveredPopulation']) < .001
        assert covered >= data['metadata']['provincePopulation']*scenario['coverageTarget']/100 - 1e-5
        assert len(selected) == len(set(selected)) == result['hospitalCount']
        assert not any(a in selected and b in selected for a,b in site_conflicts())
        assert abs(weighted_time / covered - result['metrics']['meanMinutes']) < 1e-6
        for d in result['districts']:
            assert d['coveragePercent'] >= scenario['districtFloor'] - 1e-5
            mask = np.array([origin['districtId'] == d['id'] for origin in data['demands']])
            assert abs(assigned[mask].sum() / d['population'] * 100 - d['coveragePercent']) < 1e-6
        config = health_planning()
        params = result['scenario']
        cost = beds = doctors = 0
        for c in result['selected']:
            template = next(t for t in config['templates'] if t['id'] == c['templateId'])
            load = loads[c['candidateIndex']]
            visits = load * config['rates']['visitsPerResident'] * params['demandMultiplier']
            bed_days = load * config['rates']['bedDaysPerResident'] * params['demandMultiplier']
            assert visits <= template['doctors'] * params['visitsPerDoctor'] + .1
            assert bed_days <= template['beds'] * 365 * params['bedOccupancy']/100 + .1
            assert abs(c['annualVisits'] - visits) < .1 and abs(c['annualBedDays'] - bed_days) < .1
            assert c['doctors'] == template['doctors'] and c['beds'] == template['beds']
            cost += template['grossAreaM2'] * template['unitCostTRY']
            beds += template['beds']; doctors += template['doctors']
        cap = result['capacity']
        assert cost == cap['constructionCostTRY'] and beds == cap['totalBeds'] and doctors == cap['totalDoctors']
        assert cost <= cap['budgetLimitTRY'] + 100
        assert abs(cap['budgetLimitTRY'] - cap['referenceCostTRY'] * (1+params['costTolerance']/100)) < 100
        assert result['metrics']['meanMinutes'] <= cap['referenceMeanMinutes'] + 1e-6
        assert result['lowerBound'] <= cap['referenceCostTRY'] + 100
        # Total-population P90 includes all unassigned/unlocated demand as infinity.
        weighted_edges.append((float('inf'), data['metadata']['provincePopulation'] - covered))
        cumulative = 0
        for minutes, weight in sorted(weighted_edges):
            cumulative += weight
            if cumulative >= .9 * data['metadata']['provincePopulation']:
                assert (result['metrics']['p90Minutes'] is None and not np.isfinite(minutes)) or abs(result['metrics']['p90Minutes'] - minutes) < 1e-6
                break
        eligible = [a for a in result['assignments'] if a['minutes'] is not None and a['minutes'] > 15]
        chosen_route = None
        for assignment in eligible[:12]:
            route = client.post('/api/route',json={**scenario,'demandId':assignment['demandId'],'candidateId':assignment['candidateId']})
            assert route.status_code == 200, route.text
            route = route.json()
            assert abs(route['minutes']-assignment['minutes']) < .001
            assert any(len(leg['coordinates']) > 1 for leg in route['legs'])
            if mode == 'car' or route['boardings']:
                chosen_route = route
                break
        assert chosen_route is not None, 'No representative vehicle route was verified'
        assert any(l['kind'] == ('drive' if mode == 'car' else 'ride') for l in chosen_route['legs'])
        summary['verifiedRoute'] = {'from':chosen_route['demand'],'to':chosen_route['candidate'],
                                    'minutes':chosen_route['minutes'],'boardings':chosen_route['boardings']}
        report.append(summary)
        print(json.dumps(summary,ensure_ascii=False),flush=True)
    if write_examples:
        (OUT/'validation-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8', newline='\n')
    return report

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--write-examples',action='store_true')
    run(parser.parse_args().write_examples)
