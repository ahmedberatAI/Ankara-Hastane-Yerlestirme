"""Independently audit a complete saved four-profile plan, without a solver.

Feasibility is conditional on the current matrices and health/cost assumptions.
Generation hashes identify historical research; the audit does not need or
claim to replay ignored research artifacts, intermediate trials or an optimizer.
"""
import argparse
from decimal import Decimal, localcontext
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile

import numpy as np
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.transit_provenance import check_package

PROFILES = ('weekday-0800', 'weekday-1000', 'saturday-1000', 'sunday-1000')
SOURCE_FILES = ('dataset.json', 'health-planning.json', 'example-transit-result.json', 'transit-package.json',
                *(f'transit-{p}-matrix.npz' for p in PROFILES))
FILES = (*SOURCE_FILES, 'joint-plan.json')
TOLERANCES = {'residents': .001, 'capacity': .1, 'areaM2': .001,
              'moneyTRY': 1., 'districtPercent': 1e-6, 'minutes': 1e-6}
D = lambda value: Decimal(str(value))


def check(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, name, minimum=0, positive=False):
    check(type(value) in (int, float), 'Non-boolean number required: ' + name)
    check(math.isfinite(value) and (value > minimum if positive else value >= minimum),
          'Invalid finite number: ' + name)
    return value


def integer(value, name, minimum=0):
    check(type(value) is int and value >= minimum, 'Integer required: ' + name)
    return value


def identity(value, name):
    check(type(value) is str and bool(value), 'Identity required: ' + name)
    return value


def keys(value, expected, name):
    check(type(value) is dict and set(value) == set(expected), 'Unexpected/missing fields: ' + name)


def sequence(value, name):
    check(type(value) is list, 'List required: ' + name)
    return value


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def hash_value(value):
    check(type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) is not None, 'Invalid SHA-256')
    return value


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                            allow_nan=False).encode('utf8'))


def load_json(blob):
    def pairs(items):
        result = {}
        for key, value in items:
            check(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def constant(value):
        raise ValueError('Non-finite JSON constant: ' + value)
    return json.loads(blob, object_pairs_hook=pairs, parse_constant=constant)


def near(value, expected, tolerance, name):
    number(value, name)
    check(abs(D(value) - D(expected)) <= D(tolerance), 'Incorrect reported ' + name)


def validate_joint_plan(certificate, data, health, matrices, published_single_profile,
                        current_source_hashes, package_id=None):
    """Return an independent summary; malformed/invalid certificates raise.

    A valid plan above the reference budget remains a valid model plan, not an
    infeasibility certificate. Unused open sites remain in count/area/cost.
    Matrix arguments contain candidate columns only; +inf means unreachable.
    """
    with localcontext() as context:
        context.prec = 45
        return _validate(certificate, data, health, matrices, published_single_profile,
                         current_source_hashes, package_id)


def _validate(cert, data, health, matrices, published, source_hashes, package_id):
    keys(cert, ('format', 'transitPackageId', 'planningVersion', 'scenario', 'sourceSHA256', 'generation', 'plan'), 'certificate')
    check(type(cert['format']) is int and cert['format'] == 1, 'Certificate format must be integer 1')
    keys(source_hashes, SOURCE_FILES, 'current source hashes')
    keys(cert['sourceSHA256'], SOURCE_FILES, 'certificate source hashes')
    for name in SOURCE_FILES:
        check(hash_value(cert['sourceSHA256'][name]) == hash_value(source_hashes[name]), 'Stale source: ' + name)
    package = identity(data['metadata']['transitPackageId'], 'current package')
    check(published.get('status') == 'feasible', 'Original budget reference must be a feasible plan')
    check(cert['transitPackageId'] == published['metadata']['transitPackageId'] == package, 'Package mismatch')
    check(published.get('transitEvidence', {}).get('packageId') == package, 'Budget reference transit evidence differs')
    if package_id is not None:
        check(package == identity(package_id, 'verified package'), 'Verified package mismatch')
    version = identity(health['version'], 'health version')
    check(cert['planningVersion'] == published['capacity']['planningVersion'] == version, 'Health version mismatch')
    check(tuple(data['metadata']['transitProfiles']) == PROFILES, 'Current four profiles differ')
    generation = cert['generation']
    flags = {'searchProvenOptimal': False, 'minimumHospitalCountProven': False,
             'travelTimeOptimized': False, 'annualDemandCountedOnce': True,
             'sameIndividualsAcrossProfilesConstrained': False}
    keys(generation, ('method', 'researchReportSHA256', 'researchVectorSHA256', *flags), 'generation')
    identity(generation['method'], 'generation method')
    hash_value(generation['researchReportSHA256']); hash_value(generation['researchVectorSHA256'])
    for name, expected in flags.items():
        check(generation[name] is expected, 'Unsupported generation claim: ' + name)
    scenario = cert['scenario']
    numeric_parameters = ('threshold', 'coverageTarget', 'districtFloor', 'trafficFactor', 'demandMultiplier',
                          'bedOccupancy', 'contactsPerDoctor', 'costTolerance', 'operatingCostMultiplier')
    keys(scenario, (*numeric_parameters, 'mode', 'hospitalLimit', 'transitProfile'), 'scenario')
    for key in numeric_parameters:
        number(scenario[key], key, positive=key != 'costTolerance')
    check(scenario['mode'] == 'transit' and scenario['threshold'] == 45 and scenario['coverageTarget'] == 95
          and scenario['districtFloor'] == 80 and scenario['hospitalLimit'] is None
          and scenario['transitProfile'] == 'weekday-1000' and scenario['bedOccupancy'] <= 100,
          'Exact free-count four-profile 45/95/80 scenario required')
    check(digest(scenario) == digest(published['scenario']), 'Scenario differs from original budget reference')
    total = number(data['metadata']['provincePopulation'], 'province population', positive=True)
    near(published['metadata']['provincePopulation'], total, 0, 'reference province population')
    target = D(total) * D(scenario['coverageTarget']) / 100
    districts = sequence(data['districts'], 'districts'); district_map = {}
    for district in districts:
        key = identity(district['id'], 'district ID')
        check(key not in district_map, 'Duplicate district')
        number(district['population'], 'district population', positive=True)
        identity(district['name'], 'district name'); district_map[key] = district
    check(bool(districts) and abs(sum(D(d['population']) for d in districts) - D(total)) <= D('.001'),
          'Incomplete district/province denominators')
    demands = sequence(data['demands'], 'demands'); demand_ids = set(); located = dict.fromkeys(district_map, D(0)); pop = []
    for demand in demands:
        key = identity(demand['id'], 'demand ID')
        check(key not in demand_ids and demand['districtId'] in district_map, 'Duplicate/unknown demand identity')
        demand_ids.add(key); value = D(number(demand['population'], 'demand population'))
        pop.append(value); located[demand['districtId']] += value
    check(bool(demands) and all(located[k] <= D(d['population']) + D('.001') for k, d in district_map.items()),
          'Located district population exceeds full denominator')
    candidates = sequence(data['candidates'], 'candidates'); candidate_ids = set()
    for candidate in candidates:
        key = identity(candidate['id'], 'candidate ID')
        check(key not in candidate_ids, 'Duplicate candidate ID'); candidate_ids.add(key)
    check(bool(candidates) and type(matrices) is dict and set(matrices) == set(PROFILES), 'Incomplete candidate/profile matrix set')
    for name, matrix in matrices.items():
        check(isinstance(matrix, np.ndarray) and matrix.dtype.kind in 'fi' and matrix.shape == (len(demands), len(candidates)),
              'Matrix dimensions/type differ: ' + name)
        check(not np.any(np.isnan(matrix)) and not np.any(matrix < 0), 'Invalid matrix values: ' + name)
    design, rates, eco = health['design'], health['rates'], health['economics']
    minimum_doctors = integer(design['minimumDoctorsPerSite'], 'minimum doctors', 1)
    doctor_area = D(number(design['areaPerDoctorM2'], 'doctor area', positive=True))
    floors = number(design['maxFloors'], 'floors', positive=True)
    contact = D(number(rates['contactsPerResident'], 'contacts rate', positive=True)) * D(scenario['demandMultiplier'])
    bedrate = D(number(rates['bedDaysPerResident'], 'bed-days rate', positive=True)) * D(scenario['demandMultiplier'])
    # The supplied model also bounds each staff integer by the entire province
    # target's staffing need. It is an algebraic model bound, not a clinical cap.
    # Preserve the declared float arithmetic at its ceil boundary; Decimal is
    # used independently for all actual loads, capacities and costs below.
    province_staff_bound = max(minimum_doctors, math.ceil(
        (float(total) * float(scenario['coverageTarget']) / 100)
        * (float(rates['contactsPerResident']) * float(scenario['demandMultiplier']))
        / float(scenario['contactsPerDoctor'])))
    for key in ('realDiscountRate', 'buildingUnitCostTRY', 'annualFixedSiteCostTRY', 'annualBedSupportCostTRY',
                'annualDoctorCostTRY', 'costPerContactTRY'):
        number(eco[key], key)
    years = D(number(eco['horizonYears'], 'cost horizon', positive=True))
    templates = {}
    for template in sequence(health['templates'], 'templates'):
        key = identity(template['id'], 'template ID'); check(key not in templates, 'Duplicate template')
        integer(template['beds'], 'template beds', 1); number(template['grossAreaM2'], 'module area', positive=True)
        templates[key] = template
    check(bool(templates), 'No templates')
    plan = cert['plan']
    keys(plan, ('selected', 'profiles', 'hospitalCount', 'totalBeds', 'totalDoctors', 'annualEquivalentCostTRY',
                'annualMaterialCostTRY', 'annualFixedResourceCostTRY'), 'plan')
    count = integer(plan['hospitalCount'], 'hospital count', 1)
    check(len(sequence(plan['selected'], 'selected sites')) == count, 'Hospital count differs')
    selected = {}; locations = []; minimum_area = math.inf
    for site in plan['selected']:
        keys(site, ('candidateIndex', 'id', 'templateId', 'beds', 'doctors', 'grossAreaM2',
                    'footprintRadiusMeters', 'maximumAssignedPopulationAcrossProfiles'), 'selected site')
        j = integer(site['candidateIndex'], 'candidate index')
        check(j < len(candidates) and j not in selected, 'Duplicate/unknown selected candidate')
        base = candidates[j]; check(site['id'] == base['id'], 'Selected candidate identity differs')
        radius = number(base['footprintRadiusMeters'], 'current footprint', positive=True)
        near(site['footprintRadiusMeters'], radius, 0, 'footprint')
        lon = number(base['lon'], 'candidate longitude'); lat = number(base['lat'], 'candidate latitude')
        check(30 <= lon <= 35 and 38 <= lat <= 42, 'Candidate outside Ankara envelope')
        check(type(site['templateId']) is str and site['templateId'] in templates, 'Unknown module')
        module = templates[site['templateId']]
        check(integer(site['beds'], 'site beds', 1) == module['beds'], 'Module beds differ')
        staff = integer(site['doctors'], 'site doctors', minimum_doctors)
        check(staff <= province_staff_bound, 'Site exceeds original province-derived staff bound')
        area = D(module['grossAreaM2']) + D(staff) * doctor_area
        near(site['grossAreaM2'], area, '.001', 'site area')
        slack = math.pi * radius ** 2 * floors - float(area)
        check(slack >= -.001, 'Site physical area exceeded'); minimum_area = min(minimum_area, slack)
        number(site['maximumAssignedPopulationAcrossProfiles'], 'maximum site load')
        selected[j] = site
        locations.append({**site, 'lon': lon, 'lat': lat})
    check(integer(plan['totalBeds'], 'total beds', 1) == sum(s['beds'] for s in selected.values()), 'Total beds differ')
    check(integer(plan['totalDoctors'], 'total doctors', 1) == sum(s['doctors'] for s in selected.values()), 'Total doctors differ')
    transform = Transformer.from_crs(4326, 32636, always_xy=True)
    points = [transform.transform(s['lon'], s['lat']) for s in locations]; clearance = None
    for i, site in enumerate(locations):
        for j in range(i):
            gap = math.dist(points[i], points[j]) - site['footprintRadiusMeters'] - locations[j]['footprintRadiusMeters']
            check(math.isfinite(gap) and gap >= -1e-7, 'Selected physical footprints overlap')
            clearance = gap if clearance is None else min(clearance, gap)
    profiles = sequence(plan['profiles'], 'profiles')
    check(len(profiles) == 4 and [p.get('profile') for p in profiles] == list(PROFILES), 'Missing/duplicate/out-of-order profiles')
    maximum_loads = dict.fromkeys(selected, D(0)); all_served = []; profile_summaries = []
    minimum_doctor_slack = minimum_bed_slack = None
    for profile in profiles:
        keys(profile, ('profile', 'coveredPopulation', 'coveragePercent', 'meanMinutes', 'districts', 'allocations'), 'profile')
        name = profile['profile']; served = [D(0)] * len(demands); loads = dict.fromkeys(selected, D(0))
        seen = set(); travel = D(0); max_minutes = 0.
        allocations = sequence(profile['allocations'], 'allocations')
        for flow in allocations:
            keys(flow, ('demandIndex', 'candidateIndex', 'population', 'minutes'), 'allocation')
            i = integer(flow['demandIndex'], 'demand index'); j = integer(flow['candidateIndex'], 'allocation candidate')
            check(i < len(demands) and j in selected and (i, j) not in seen, 'Unknown/closed/duplicate allocation')
            seen.add((i, j)); amount = D(number(flow['population'], 'allocated population', positive=True))
            minutes = float(matrices[name][i, j]); number(flow['minutes'], 'reported minutes')
            check(math.isfinite(minutes) and minutes <= scenario['threshold'], 'Allocation unreachable/over threshold')
            near(flow['minutes'], minutes, '.000001', 'allocation minutes')
            served[i] += amount; loads[j] += amount; travel += amount * D(minutes); max_minutes = max(max_minutes, minutes)
        check(abs(sum(served) - target) <= D('.001') and all(s <= n + D('.001') for s, n in zip(served, pop)),
              'Province exact target/origin conservation failed')
        district_served = dict.fromkeys(district_map, D(0))
        for demand, amount in zip(demands, served): district_served[demand['districtId']] += amount
        district_rows = []
        for district in districts:
            k = district['id']; coverage = district_served[k] / D(district['population']) * 100
            check(coverage >= D(scenario['districtFloor']) - D('.000001'), 'District percentage target failed')
            district_rows.append({'id': k, 'name': district['name'], 'population': district['population'],
                                  'coveredPopulation': float(district_served[k]), 'coveragePercent': float(coverage)})
        recorded = sequence(profile['districts'], 'profile districts'); observed = {}
        for district in recorded:
            keys(district, ('id', 'coveragePercent'), 'profile district')
            k = identity(district['id'], 'profile district ID')
            check(k in district_map and k not in observed, 'Unknown/duplicate profile district'); observed[k] = district
        check(set(observed) == set(district_map), 'Missing profile district')
        for row in district_rows: near(observed[row['id']]['coveragePercent'], row['coveragePercent'], '.000001', 'district coverage')
        near(profile['coveredPopulation'], sum(served), '.001', 'profile served population')
        near(profile['coveragePercent'], sum(served) / D(total) * 100, '.000001', 'profile coverage')
        near(profile['meanMinutes'], travel / target, '.000001', 'mean minutes')
        for j, site in selected.items():
            doctor_slack = D(site['doctors']) * D(scenario['contactsPerDoctor']) - loads[j] * contact
            bed_slack = D(site['beds']) * 365 * D(scenario['bedOccupancy']) / 100 - loads[j] * bedrate
            check(doctor_slack >= D('-.1') and bed_slack >= D('-.1'), 'Independent doctor/bed capacity failed')
            maximum_loads[j] = max(maximum_loads[j], loads[j])
            minimum_doctor_slack = doctor_slack if minimum_doctor_slack is None else min(minimum_doctor_slack, doctor_slack)
            minimum_bed_slack = bed_slack if minimum_bed_slack is None else min(minimum_bed_slack, bed_slack)
        profile_summaries.append({'profile': name, 'coveredPopulation': float(sum(served)),
                                  'coveragePercent': float(sum(served) / D(total) * 100), 'meanMinutes': float(travel / target),
                                  'maxMinutes': max_minutes, 'allocationCount': len(allocations),
                                  'minimumDistrictCoveragePercent': min(r['coveragePercent'] for r in district_rows),
                                  'districts': district_rows})
        all_served.append(served)
    for j, site in selected.items(): near(site['maximumAssignedPopulationAcrossProfiles'], maximum_loads[j], '.001', 'maximum profile load')
    rate = D(eco['realDiscountRate']); annuity = rate / (1 - (1 + rate) ** -years) if rate else 1 / years
    construction = sum((D(templates[s['templateId']]['grossAreaM2']) + D(s['doctors']) * doctor_area)
                       * D(eco['buildingUnitCostTRY']) for s in selected.values())
    fixed_operating = sum(D(scenario['operatingCostMultiplier']) * (D(eco['annualFixedSiteCostTRY'])
                          + D(s['beds']) * D(eco['annualBedSupportCostTRY']) + D(s['doctors']) * D(eco['annualDoctorCostTRY']))
                          for s in selected.values())
    material = target * contact * D(eco['costPerContactTRY']) * D(scenario['operatingCostMultiplier'])
    annual = construction * annuity + fixed_operating + material
    for field, value in (('annualEquivalentCostTRY', annual), ('annualMaterialCostTRY', material),
                         ('annualFixedResourceCostTRY', annual - material)):
        near(plan[field], value, 1, field)
    budget = D(number(published['capacity']['budgetLimitTRY'], 'original transit budget', positive=True))
    budget_slack = budget - annual
    # Allow no monetary tolerance to manufacture a budget witness. Comparison
    # uses independently computed Decimal values, not the reported plan cost.
    within_budget = budget_slack >= 0
    clipped = [[min(pop[i], max(D(0), row[i])) for i in range(len(pop))] for row in all_served]
    correction = sum(abs(a - b) for row, clean in zip(all_served, clipped) for a, b in zip(row, clean))
    lower = [max(D(0), sum(row[i] for row in clipped) - 3 * pop[i]) for i in range(len(pop))]
    upper = [min(row[i] for row in clipped) for i in range(len(pop))]
    def overlap(indices, denominator):
        low = sum(lower[i] for i in indices); high = sum(upper[i] for i in indices)
        return {'denominator': denominator, 'lowerResidents': float(low), 'upperResidents': float(high),
                'lowerPercent': float(low / D(denominator) * 100), 'upperPercent': float(high / D(denominator) * 100)}
    return {'format': 1, 'status': 'witness_validated' if within_budget else 'validated_model_plan_above_reference_budget',
            'witnessFound': bool(within_budget), 'solverRun': False, 'transitPackageId': package, 'planningVersion': version,
            'scenario': dict(scenario), 'hospitalCount': count, 'beds': plan['totalBeds'], 'doctors': plan['totalDoctors'],
            'selected': locations, 'profiles': profile_summaries, 'provincePopulation': total,
            'locatedPopulation': float(sum(pop)), 'unlocatedPopulation': float(D(total) - sum(pop)),
            'resourcesSharedAcrossProfiles': True, 'annualDemandCountedOnce': True,
            'sameIndividualsAcrossProfilesConstrained': False, 'withinOriginalTransitBudget': bool(within_budget),
            'annualEquivalentCostTRY': float(annual), 'decimalAnnualEquivalentCostTRY': str(annual),
            'decimalAnnualMaterialCostTRY': str(material), 'decimalAnnualFixedResourceCostTRY': str(annual - material),
            'originalTransitBudgetTRY': float(budget), 'budgetSlackTRY': float(budget_slack),
            'decimalBudgetSlackTRY': str(budget_slack), 'budgetSlackPercent': float(budget_slack / budget * 100),
            'minimumAreaSlackM2': minimum_area, 'minimumPlotClearanceMeters': clearance,
            'minimumDoctorContactSlack': float(minimum_doctor_slack), 'minimumBedDaySlack': float(minimum_bed_slack),
            'numericalTolerances': dict(TOLERANCES), 'conditionalOverlap': {
                'province': overlap(list(range(len(pop))), total),
                'districts': [dict(id=d['id'], name=d['name'], **overlap(
                    [i for i, x in enumerate(demands) if x['districtId'] == d['id']], d['population'])) for d in districts],
                'sameIndividualsObserved': False, 'numericalClippingResidents': float(correction),
                'scope': 'Conditional intersections of subsets of each origin population, not observed patient identities. Lower=max(0,sum(served)-3*population); upper=min(served). Full denominators retained.'},
            'generation': dict(generation),
            'scope': 'Feasible saved plan in the current four-profile 45/95/80 model. No optimal or minimum hospital count, 91-site conclusion, real travel-time guarantee or clinical adequacy claim. Reference budget is a model ceiling, not a complete public cost estimate.',
            'generationReferenceScope': 'Generation SHA values identify historical research artifacts; this audit independently validates the complete published plan without replaying research or intermediate trials.',
            'aboveBudgetInterpretation': 'This valid saved plan may exceed the reference budget; no other plan was searched and no infeasibility conclusion follows.'}


def current_report(processed_directory):
    directory = Path(processed_directory).resolve(strict=True)
    check(directory.is_dir(), 'Processed source must be a directory')
    code = Path(__file__).read_bytes().replace(b'\r\n', b'\n'); blobs = {}
    for name in FILES:
        path = (directory / name).resolve(strict=True)
        check(path.parent == directory and path.is_file(), 'Source path escapes processed directory')
        blobs[name] = path.read_bytes()
    parsed = {name: load_json(blobs[name]) for name in FILES if name.endswith('.json')}
    candidate_count = len(parsed['dataset.json']['candidates']); matrices = {}
    for profile in PROFILES:
        with np.load(io.BytesIO(blobs[f'transit-{profile}-matrix.npz']), allow_pickle=False) as archive:
            check(set(archive.files) == {'minutes'}, 'Unexpected matrix archive members')
            matrix = archive['minutes']
            check(matrix.ndim == 2 and matrix.shape[1] >= candidate_count, 'Missing candidate columns')
            matrices[profile] = matrix[:, :candidate_count]
    hashes = {name: sha256(blobs[name]) for name in SOURCE_FILES}
    result = validate_joint_plan(parsed['joint-plan.json'], parsed['dataset.json'], parsed['health-planning.json'],
                                 matrices, parsed['example-transit-result.json'], hashes)
    result['sourceSHA256'] = {name: sha256(blob) for name, blob in blobs.items()}
    result['auditCodeSHA256'] = sha256(code)
    result['auditCodeHashNormalization'] = 'CRLF converted to LF; all nine input hashes use exact file bytes'
    for name, blob in blobs.items(): check((directory / name).read_bytes() == blob, 'Source changed during audit')
    check(Path(__file__).read_bytes().replace(b'\r\n', b'\n') == code, 'Audit code changed during audit')
    return result


def compare_report(report, processed_directory):
    check(digest(report) == digest(current_report(processed_directory)), 'Saved summary differs from current computation')
    return True


def run(write=False):
    check(type(write) is bool, 'Write flag must be boolean')
    package = check_package(ROOT); directory = (ROOT / 'data/processed').resolve(strict=True)
    output = directory / 'joint-plan-summary.json'
    check(output.resolve(strict=False).parent == directory, 'Output escapes processed directory')
    result = current_report(directory)
    check(result['transitPackageId'] == package, 'Current package differs from saved plan')
    if not write:
        check(digest(load_json(output.read_bytes())) == digest(result), 'Saved summary differs from current source/code/computation')
    check(check_package(ROOT) == package, 'Package changed before publication')
    for name, value in result['sourceSHA256'].items():
        check(sha256((directory / name).read_bytes()) == value, 'Source changed before publication')
    check(sha256(Path(__file__).read_bytes().replace(b'\r\n', b'\n')) == result['auditCodeSHA256'], 'Audit code changed before publication')
    if write:
        descriptor, name = tempfile.mkstemp(prefix='.joint-plan-', suffix='.json.tmp', dir=directory)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf8', newline='\n') as stream:
                stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
                stream.flush(); os.fsync(stream.fileno())
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
        print('Wrote independently validated joint-plan summary:', output)
    else:
        print('Verified joint-plan source, complete allocations, resources and one annual bill; no files changed.')
    print('Status:', result['status'], '; hospitals:', result['hospitalCount'], '; no minimum-count or real-city claim.')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Write the independently validated current plan summary')
    run(write=parser.parse_args().write)
