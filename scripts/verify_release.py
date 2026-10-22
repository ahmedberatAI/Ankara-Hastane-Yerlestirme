"""Check the packaged data and both complete solve/route flows without a server."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import numpy as np
from backend.main import app, matrix, dataset, travel_times, Scenario

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
        summary = {'mode': mode, 'scenario': scenario, 'status': result['status'],
                   'hospitalCount': result.get('hospitalCount'), 'metrics': result.get('metrics')}
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
        times = travel_times(Scenario(**scenario))[:, selected]
        nearest = times.min(axis=1)
        populations = np.array([d['population'] for d in data['demands']])
        covered = int(populations[nearest <= scenario['threshold']].sum())
        assert covered == result['metrics']['coveredPopulation']
        assert covered >= data['metadata']['provincePopulation']*scenario['coverageTarget']/100 - 1e-5
        assert len(selected) == len(set(selected)) == result['hospitalCount']
        for d in result['districts']:
            assert d['coveragePercent'] >= scenario['districtFloor'] - 1e-5
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
