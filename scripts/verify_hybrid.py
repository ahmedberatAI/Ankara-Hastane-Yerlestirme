"""Independent physical, flow and one-bill audit of a saved two-mode result."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import motis

CODE_FILES = ('backend/main.py', 'backend/hybrid.py', 'backend/joint_model.py',
              'backend/motis.py', 'backend/motis_runtime.py', 'backend/capacity.py',
              'backend/optimizer.py', 'scripts/verify_hybrid.py')


def code_identities():
    return {name: hashlib.sha256((ROOT / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for name in CODE_FILES}


def close(actual, expected, tolerance=.01):
    assert isinstance(actual, (int, float)) and not isinstance(actual, bool) and math.isfinite(actual)
    assert abs(actual - expected) <= tolerance, (actual, expected)


def audit(result, data, planning, matrices, package_id):
    assert result['status'] == 'feasible' and result['scenario']['mode'] == 'hybrid'
    s = result['scenario']; h = result['hybridSummary']; sites = result['selected']
    assert s['transitEngine'] == 'motis' and result['transitEvidence']['packageId'] == package_id
    assert result['modelCodeLF_SHA256'] == code_identities(), 'Saved hybrid model code changed'
    assert result['dataSHA256'] == {key: motis.file_sha(ROOT / filename) for key, filename in
        [('dataset', 'data/processed/dataset.json'), ('planning', 'data/processed/health-planning.json')]}
    close(h['carWeight'], s['carWeight']); close(h['transitWeight'], 100 - s['carWeight'])
    assert h['thresholds'] == {'car': s['threshold'], 'transit': s['transitThreshold']}
    assert h['annualDemandCountedOnce'] is True and h['twoFullDemandScenarios'] is True
    ids = [x['candidateIndex'] for x in sites]
    assert len(set(ids)) == len(ids) == result['hospitalCount']
    assert len(set(result['selectedIndices'])) == len(result['selectedIndices']) == len(ids)
    assert set(ids) == set(result['selectedIndices'])
    for field in ('metrics', 'assignments', 'districts'):
        assert result[field] == result['modalResults']['car'][field], 'Top-level car view differs: ' + field
    if s['hospitalLimit'] is not None:
        assert len(ids) <= s['hospitalLimit']
    selected = {x['candidateIndex']: x for x in sites}
    templates = {x['id']: x for x in planning['templates']}
    pop = np.array([x['population'] for x in data['demands']])
    total = data['metadata']['provincePopulation']; target = total * s['coverageTarget'] / 100
    rate = planning['rates']; contact = rate['contactsPerResident'] * s['demandMultiplier']
    bed_rate = rate['bedDaysPerResident'] * s['demandMultiplier']
    loads = {}; means = {}
    for mode, threshold in [('car', s['threshold']), ('transit', s['transitThreshold'])]:
        modal = result['modalResults'][mode]
        assert len(modal['assignments']) == len(pop)
        load = np.zeros(len(data['candidates'])); district_served = {d['id']: 0. for d in data['districts']}
        served = weighted = 0.
        for i, (assignment, demand) in enumerate(zip(modal['assignments'], data['demands'])):
            assert assignment['demandId'] == demand['id']
            amount = 0.
            seen = set()
            for part in assignment['allocations']:
                j = part['candidateIndex']; quantity = part['population']
                assert j in selected and j not in seen and not isinstance(quantity, bool) and math.isfinite(quantity) and quantity >= 0
                seen.add(j)
                assert part['candidateId'] == data['candidates'][j]['id']
                t = float(matrices[mode][i, j]); assert math.isfinite(t) and t <= threshold + 1e-7
                close(part['minutes'], t, .001)
                close(part['fraction'], quantity / pop[i], 1e-7)
                load[j] += quantity; amount += quantity; weighted += quantity * t
            assert amount <= pop[i] + .001
            close(assignment['servedFraction'], amount / pop[i], 1e-7)
            district_served[demand['districtId']] += amount; served += amount
        close(served, target, .001)
        close(modal['metrics']['coveragePercent'], 100 * served / total, 1e-6)
        means[mode] = weighted / served
        close(modal['metrics']['meanMinutes'], means[mode], 1e-6)
        district_records = {d['id']: d for d in modal['districts']}
        assert len(modal['districts']) == len(district_records) == len(data['districts'])
        assert set(district_records) == {d['id'] for d in data['districts']}
        for d in data['districts']:
            covered = district_served[d['id']]
            assert district_records[d['id']]['population'] == d['population']
            assert covered / d['population'] * 100 >= s['districtFloor'] - 1e-6, 'District percentage floor violated'
            close(district_records[d['id']]['coveragePercent'], covered / d['population'] * 100, 1e-6)
        loads[mode] = load
    close(h['weightedMeanMinutes'], (means['car'] * s['carWeight'] + means['transit'] * (100 - s['carWeight'])) / 100, 1e-6)
    eco = planning['economics']; design = planning['design']
    r = eco['realDiscountRate']; years = eco['horizonYears']; om = s['operatingCostMultiplier']
    annuity = r / (1 - (1 + r) ** -years) if r else 1 / years
    total_beds = total_docs = 0; capex = fixed_opex = 0.
    for j, site in selected.items():
        source = data['candidates'][j]; template = templates[site['templateId']]
        for key in ('id', 'lat', 'lon', 'footprintRadiusMeters', 'node', 'entryLat', 'entryLon', 'accessMeters'):
            assert site[key] == source[key]
        docs, beds = site['doctors'], site['beds']
        assert type(docs) is int and docs >= design['minimumDoctorsPerSite']
        assert type(beds) is int and beds == template['beds']
        available = math.pi * source['footprintRadiusMeters'] ** 2 * design['maxFloors']
        plot_ub = math.floor(np.nextafter((available + .001 - min(t['grossAreaM2'] for t in templates.values())) / design['areaPerDoctorM2'], np.inf))
        global_ub = max(design['minimumDoctorsPerSite'], math.ceil(target * contact / s['contactsPerDoctor']))
        assert docs <= min(plot_ub, global_ub), 'Physician variable bound violated'
        area = template['grossAreaM2'] + docs * design['areaPerDoctorM2']
        close(site['grossAreaM2'], area, .001)
        assert area <= math.pi * source['footprintRadiusMeters'] ** 2 * design['maxFloors'] + .001
        for mode in ('car', 'transit'):
            assert loads[mode][j] * contact <= docs * s['contactsPerDoctor'] + .1
            assert loads[mode][j] * bed_rate <= beds * 365 * s['bedOccupancy'] / 100 + .1
            close(site['assignedPopulationByMode'][mode], loads[mode][j], .001)
        close(site['assignedPopulation'], max(loads[mode][j] for mode in loads), .001)
        capex += area * eco['buildingUnitCostTRY']
        fixed_opex += om * (eco['annualFixedSiteCostTRY'] + docs * eco['annualDoctorCostTRY'] + beds * eco['annualBedSupportCostTRY'])
        total_beds += beds; total_docs += docs
    # Independent plot-conflict audit; no optimizer's conflict list is reused.
    from pyproj import Transformer
    project = Transformer.from_crs(4326, 32636, always_xy=True)
    xy = np.array([project.transform(x['lon'], x['lat']) for x in sites])
    for i in range(len(sites)):
        for j in range(i):
            assert np.linalg.norm(xy[i] - xy[j]) >= sites[i]['footprintRadiusMeters'] + sites[j]['footprintRadiusMeters']
    materials = target * contact * eco['costPerContactTRY'] * om
    annual = capex * annuity + fixed_opex + materials
    cap = result['capacity']
    assert cap['totalBeds'] == total_beds and cap['totalDoctors'] == total_docs
    close(cap['annualMaterialCostTRY'], materials, .1)
    close(sum(x['operatingBreakdown']['materialsTRY'] for x in sites), materials, .1)
    close(cap['constructionCostTRY'], capex, .1)
    close(cap['annualOperatingCostTRY'], fixed_opex + materials, .1)
    close(cap['annualEquivalentCostTRY'], annual, .1)
    close(cap['budgetLimitTRY'], cap['referenceCostTRY'] * (1 + s['costTolerance'] / 100), .1)
    assert annual <= cap['budgetLimitTRY'] + .1
    return {'hospitalCount': len(sites), 'beds': total_beds, 'doctors': total_docs,
            'weightedMeanMinutes': h['weightedMeanMinutes'], 'annualEquivalentCostTRY': annual,
            'modalMeanMinutes': means, 'provinceCoverageTarget': s['coverageTarget'],
            'minimumDistrictCoverageByMode': {mode: min(d['coveragePercent'] for d in result['modalResults'][mode]['districts']) for mode in loads},
            'scope': 'Final-plan physical flows, original resource bounds, single annual bill and stated reference-budget compliance. Does not independently certify cost-stage history or native dual bounds.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result', type=Path, default=ROOT / 'data/processed/hybrid-result.json')
    args = parser.parse_args()
    result = json.loads(args.result.read_text(encoding='utf-8'))
    data = json.loads((ROOT / 'data/processed/dataset.json').read_text(encoding='utf-8'))
    planning = json.loads((ROOT / 'data/processed/health-planning.json').read_text(encoding='utf-8'))
    with np.load(ROOT / 'data/processed/car-matrix.npz') as raw:
        car = raw['minutes'].astype(float)
    traffic = result['scenario']['trafficFactor']
    if traffic != 1:
        overhead = np.array([d['snapMeters'] / 75 for d in data['demands']])[:, None] + np.array([c['accessMeters'] / 75 for c in data['candidates'] + data['hospitals']]) + 3
        car = np.maximum(car - overhead, 0) * traffic + overhead
    matrices = {'car': car, 'transit': motis.load_matrix(result['scenario']['transitProfile'])}
    print(json.dumps(audit(result, data, planning, matrices, motis.manifest()['packageId']), ensure_ascii=False))


if __name__ == '__main__':
    main()
