"""No-solve audit of a saved plan in a transport-free relaxation.

This does not copy car journeys into transit. It keeps one validated resource
plan and allocation in four alternative contexts with transport removed.
"""
import argparse
from decimal import Decimal, localcontext
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile

import numpy as np
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.transit_provenance import check_package

PROFILES = ('weekday-0800', 'weekday-1000', 'saturday-1000', 'sunday-1000')
FILES = ('dataset.json', 'health-planning.json', 'example-car-result.json', 'example-transit-result.json')
PARAMETERS = ('coverageTarget', 'districtFloor', 'demandMultiplier', 'bedOccupancy',
              'contactsPerDoctor', 'operatingCostMultiplier')
TOLERANCE = {'residents': .001, 'capacity': .1, 'areaM2': .001, 'moneyTRY': 1., 'districtPercent': 1e-6}


def check(condition, reason):
    if not condition:
        raise ValueError(reason)


def number(value, name, minimum=0., strictly_positive=False):
    check(type(value) in (int, float), 'Expected numeric, non-boolean ' + name)
    check(math.isfinite(value) and (value > minimum if strictly_positive else value >= minimum), 'Invalid finite ' + name)
    return float(value)


def integer(value, name, minimum=0):
    check(type(value) is int and value >= minimum, 'Expected integer, non-boolean ' + name)
    return value


def identity(value, name):
    check(type(value) is str and bool(value), 'Invalid identity ' + name)
    return value


def same_number(a, b, name):
    check(number(a, name) == number(b, name), 'Scenario/source mismatch: ' + name)


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def audit(data, health, car, transit, hospital_limit=91):
    """Validate the complete source plan; return a conditional witness or unknown.

    Invalid/malformed input raises ValueError. A valid plan above the requested
    count or budget returns witnessFound=False, never an infeasibility claim.
    """
    limit = integer(hospital_limit, 'hospital limit', 1)
    check(car['status'] == 'feasible', 'A feasible saved car plan is required')
    cs, ts = car['scenario'], transit['scenario']
    check(cs['mode'] == 'car' and ts['mode'] == 'transit', 'Saved plan mode mismatch')
    for key in PARAMETERS:
        same_number(cs[key], ts[key], key)
    check(ts['coverageTarget'] == 95 and ts['districtFloor'] == 80, 'Exact 95/80 scenario required')
    for key in ('demandMultiplier', 'bedOccupancy', 'contactsPerDoctor', 'operatingCostMultiplier'):
        number(ts[key], key, strictly_positive=True)
    check(ts['bedOccupancy'] <= 100, 'Occupancy exceeds 100%')
    version = identity(health['version'], 'health version')
    check(car['capacity']['planningVersion'] == transit['capacity']['planningVersion'] == version, 'Health planning version mismatch')
    total = number(data['metadata']['provincePopulation'], 'province population', strictly_positive=True)
    same_number(car['metadata']['provincePopulation'], total, 'car province population')
    same_number(transit['metadata']['provincePopulation'], total, 'transit province population')
    check(tuple(data['metadata']['transitProfiles']) == PROFILES, 'Four exact alternative profile identities required')
    package = identity(data['metadata']['transitPackageId'], 'package')
    check(car['metadata']['transitPackageId'] == transit['metadata']['transitPackageId'] == package, 'Saved/current package mismatch')
    target = total * ts['coverageTarget'] / 100

    district_pop = {}
    for d in data['districts']:
        key = identity(d['id'], 'district')
        check(key not in district_pop, 'Duplicate district identity')
        district_pop[key] = number(d['population'], 'district population', strictly_positive=True)
    check(bool(district_pop) and abs(sum(district_pop.values()) - total) <= .001, 'Missing district or province denominator mismatch')
    demands = data['demands']
    demand_ids = [identity(d['id'], 'demand') for d in demands]
    check(bool(demands) and len(set(demand_ids)) == len(demand_ids), 'Missing/duplicate demand identity')
    pop = np.array([number(d['population'], 'demand population') for d in demands])
    check(float(pop.sum()) <= total + .001, 'Located population exceeds province denominator')
    located = dict.fromkeys(district_pop, 0.)
    for d, p in zip(demands, pop):
        check(d['districtId'] in located, 'Demand refers to missing district')
        located[d['districtId']] += p
    check(all(located[k] <= district_pop[k] + .001 for k in located), 'Located district population exceeds denominator')
    candidates = data['candidates']
    candidate_ids = [identity(c['id'], 'candidate') for c in candidates]
    check(bool(candidates) and len(set(candidate_ids)) == len(candidate_ids), 'Missing/duplicate candidate identity')

    design, rates, eco = health['design'], health['rates'], health['economics']
    minimum_staff = integer(design['minimumDoctorsPerSite'], 'minimum doctors', 1)
    doctor_area = number(design['areaPerDoctorM2'], 'doctor area', strictly_positive=True)
    floors = number(design['maxFloors'], 'floor limit', strictly_positive=True)
    contact = number(rates['contactsPerResident'], 'contact rate', strictly_positive=True) * ts['demandMultiplier']
    bedrate = number(rates['bedDaysPerResident'], 'bed-day rate', strictly_positive=True) * ts['demandMultiplier']
    for key in ('realDiscountRate', 'buildingUnitCostTRY', 'annualFixedSiteCostTRY',
                'annualBedSupportCostTRY', 'annualDoctorCostTRY', 'costPerContactTRY'):
        number(eco[key], key)
    years = number(eco['horizonYears'], 'cost horizon', strictly_positive=True)
    templates = {}
    for t in health['templates']:
        key = identity(t['id'], 'template')
        check(key not in templates, 'Duplicate template identity')
        integer(t['beds'], 'template beds', 1)
        number(t['grossAreaM2'], 'template area', strictly_positive=True)
        templates[key] = t
    check(bool(templates), 'No template definitions')

    count = integer(car['hospitalCount'], 'hospital count', 1)
    check(len(car['selected']) == count, 'Selected/hospital count mismatch')
    indices = [integer(j, 'selected index') for j in car['selectedIndices']]
    check(len(indices) == len(set(indices)) == count, 'Duplicate/missing selected index')
    selected, minimum_area_slack = {}, math.inf
    for site in car['selected']:
        j = integer(site['candidateIndex'], 'site index')
        check(j < len(candidates) and j not in selected, 'Unknown/duplicate selected site')
        base = candidates[j]
        check(site['id'] == base['id'], 'Selected site identity mismatch')
        for key in ('footprintRadiusMeters',):
            same_number(site[key], base[key], key)
            number(site[key], key, strictly_positive=True)
        for key in ('lon', 'lat'):
            # Ankara coordinates are positive; reject NaN/boolean values explicitly.
            same_number(site[key], base[key], key)
        check(30 <= site['lon'] <= 35 and 38 <= site['lat'] <= 42, 'Site outside declared Ankara coordinate envelope')
        check(site['templateId'] in templates, 'Unknown selected module')
        t = templates[site['templateId']]
        check(integer(site['beds'], 'site beds', 1) == t['beds'], 'Site/template bed mismatch')
        staff = integer(site['doctors'], 'site doctors', minimum_staff)
        area = t['grossAreaM2'] + staff * doctor_area
        check(abs(number(site['grossAreaM2'], 'site gross area', strictly_positive=True) - area) <= .001, 'Site gross area inconsistent')
        slack = math.pi * site['footprintRadiusMeters'] ** 2 * floors - area
        check(slack >= -.001, 'Site exceeds physical plot capacity')
        minimum_area_slack = min(minimum_area_slack, slack)
        selected[j] = site
    check(set(indices) == set(selected), 'Selected index sets differ')
    project = Transformer.from_crs(4326, 32636, always_xy=True)
    sites = list(selected.values())
    xy = np.array([project.transform(s['lon'], s['lat']) for s in sites])
    radii = np.array([s['footprintRadiusMeters'] for s in sites])
    clearance = None
    for i in range(count - 1):
        gap = float((np.linalg.norm(xy[i+1:] - xy[i], axis=1) - radii[i+1:] - radii[i]).min())
        check(gap >= -1e-7, 'Selected plots overlap')
        clearance = gap if clearance is None else min(clearance, gap)

    check(len(car['assignments']) == len(demands), 'Missing demand assignment record')
    served = np.zeros(len(demands))
    loads = dict.fromkeys(selected, 0.)
    flows = []
    for i, (d, assignment) in enumerate(zip(demands, car['assignments'])):
        check(assignment['demandId'] == d['id'], 'Demand/assignment identity or order mismatch')
        seen = set()
        for a in assignment['allocations']:
            j = integer(a['candidateIndex'], 'allocation site index')
            check(j in selected and j not in seen, 'Closed/duplicate assignment destination')
            check(a['candidateId'] == candidates[j]['id'], 'Assignment candidate identity mismatch')
            f = number(a['population'], 'allocated population', strictly_positive=True)
            seen.add(j)
            served[i] += f
            loads[j] += f
            flows.append({'demandIndex': i, 'candidateIndex': j, 'population': f})
    check(bool(np.all(served <= pop + .001)) and abs(float(served.sum()) - target) <= .001, 'Population conservation/95% target failed')
    district_served = dict.fromkeys(district_pop, 0.)
    for d, amount in zip(demands, served):
        district_served[d['districtId']] += amount
    coverage = {k: district_served[k] / district_pop[k] * 100 for k in district_pop}
    check(min(coverage.values()) >= 80 - 1e-6, 'District 80% target failed')
    for j, site in selected.items():
        # An unused open site is allowed by the original model. Preserve its
        # staff, beds, footprint, count and cost rather than silently closing it.
        check(abs(number(site['assignedPopulation'], 'site assigned population') - loads[j]) <= .001, 'Site assignment total mismatch')
        check(loads[j] * contact <= site['doctors'] * ts['contactsPerDoctor'] + .1, 'Physician capacity failed')
        check(loads[j] * bedrate <= site['beds'] * 365 * ts['bedOccupancy'] / 100 + .1, 'Bed capacity failed')
    check(integer(car['capacity']['totalBeds'], 'total beds', 1) == sum(s['beds'] for s in sites), 'Total beds mismatch')
    check(integer(car['capacity']['totalDoctors'], 'total doctors', 1) == sum(s['doctors'] for s in sites), 'Total doctors mismatch')

    D = lambda value: Decimal(str(value))
    with localcontext() as context:
        context.prec = 40
        rate = D(eco['realDiscountRate'])
        annuity = rate / (1 - (1 + rate) ** -D(years)) if rate else 1 / D(years)
        construction = sum(D(s['grossAreaM2']) * D(eco['buildingUnitCostTRY']) for s in sites)
        fixed_operating = sum(D(ts['operatingCostMultiplier']) * (D(eco['annualFixedSiteCostTRY']) +
                            D(s['beds']) * D(eco['annualBedSupportCostTRY']) +
                            D(s['doctors']) * D(eco['annualDoctorCostTRY'])) for s in sites)
        material = D(target) * D(contact) * D(eco['costPerContactTRY']) * D(ts['operatingCostMultiplier'])
        annual = construction * annuity + fixed_operating + material
    for key, expected in (('annualEquivalentCostTRY', annual), ('constructionCostTRY', construction),
                          ('annualOperatingCostTRY', fixed_operating + material)):
        check(abs(number(car['capacity'][key], key) - float(expected)) <= 1., 'Reported cost disagrees with one annual demand bill: ' + key)
    budget = number(transit['capacity']['budgetLimitTRY'], 'original transit budget', strictly_positive=True)
    count_ok, budget_ok = count <= limit, float(annual) <= budget + 1.
    return {
        'format': 1, 'status': 'witness_validated' if count_ok and budget_ok else 'no_witness_from_saved_plan',
        'witnessFound': bool(count_ok and budget_ok), 'solverRun': False,
        'transitPackageId': package, 'planningVersion': version, 'hospitalLimit': limit,
        'hospitalCount': count, 'beds': sum(s['beds'] for s in sites), 'doctors': sum(s['doctors'] for s in sites),
        'withinHospitalLimit': count_ok, 'withinOriginalTransitBudget': budget_ok,
        'sameHealthScenarioParameters': {key: ts[key] for key in PARAMETERS},
        'profiles': [{'profile': p, 'allocationSHA256': digest(flows), 'allocationCount': len(flows),
                      'coveredPopulation': float(served.sum()), 'coveragePercent': float(served.sum()) / total * 100,
                      'minimumDistrictCoveragePercent': min(coverage.values())} for p in PROFILES],
        'resourcesSharedAcrossProfiles': True, 'annualDemandCountedOnce': True,
        # PROJ/libm implementations can differ below a nanometre. Preserve the
        # unrounded overlap check above; serialize this diagnostic to micrometres
        # so exact report hashes replay on Windows and Linux.
        'minimumAreaSlackM2': minimum_area_slack,
        'minimumPlotClearanceMeters': None if clearance is None else round(clearance, 6),
        'annualEquivalentCostTRY': float(annual), 'decimalAnnualEquivalentCostTRY': str(annual),
        'decimalAnnualMaterialCostTRY': str(material), 'originalTransitBudgetTRY': budget,
        'budgetSlackTRY': budget - float(annual), 'numericalTolerances': TOLERANCE,
        'scope': 'All transport constraints removed; every demand-candidate pair is allowed. Same saved locations, resources and allocations copied to four alternative profiles. No route, departure, walking connection or real travel time is asserted. A feasible relaxation does not establish actual EGO feasibility or an optimal hospital count.',
        'noWitnessInterpretation': 'If this saved plan exceeds count or budget, no conclusion of infeasibility follows; no other plan was searched.'
    }


def current_report(processed_directory, hospital_limit=91):
    """Read exact fixed filenames, bind inputs/code, never write or invoke a solver."""
    directory = Path(processed_directory).resolve(strict=True)
    check(directory.is_dir(), 'Processed source must be a directory')
    blobs = {}
    for name in FILES:
        path = (directory / name).resolve(strict=True)
        check(path.parent == directory and path.is_file(), 'Source path escapes declared directory')
        blobs[name] = path.read_bytes()
    parsed = [json.loads(blobs[name]) for name in FILES]
    result = audit(*parsed, hospital_limit=hospital_limit)
    result['sourceSHA256'] = {name: hashlib.sha256(blob).hexdigest() for name, blob in blobs.items()}
    # Match repository checkout differences without normalizing source data bytes.
    code_bytes = Path(__file__).read_bytes().replace(b'\r\n', b'\n')
    result['auditCodeSHA256'] = hashlib.sha256(code_bytes).hexdigest()
    result['auditCodeHashNormalization'] = 'CRLF converted to LF; all four input hashes use exact file bytes'
    for name, blob in blobs.items():
        check((directory / name).read_bytes() == blob, 'Source changed while auditing')
    return result


def compare_report(report, processed_directory):
    """Read-only deterministic verification; stale/altered reports are rejected."""
    # Python dict equality conflates True/1 and 1.0/1. Canonical JSON preserves
    # those types and rejects NaN, so report tampering cannot exploit that rule.
    check(digest(report) == digest(current_report(processed_directory, hospital_limit=report['hospitalLimit'])),
          'Saved witness differs from current source/code/computation')
    return True


def run(write=False):
    """Fixed 91-site benchmark; default verifies the saved artifact read-only."""
    check(type(write) is bool, 'Write mode must be boolean')
    package = check_package(ROOT)
    directory = (ROOT / 'data/processed').resolve(strict=True)
    output = directory / 'transport-relaxation-results.json'
    check(output.resolve(strict=False).parent == directory, 'Report output escapes processed directory')
    report = current_report(directory, hospital_limit=91)
    check(type(report['hospitalLimit']) is int and report['hospitalLimit'] == 91, 'Benchmark hospital limit must be integer 91')
    check(report['transitPackageId'] == package, 'Witness/current transit package mismatch')
    if not write:
        saved = json.loads(output.read_bytes())
        check(type(saved) is dict and type(saved.get('hospitalLimit')) is int and saved['hospitalLimit'] == 91,
              'Saved benchmark hospital limit must be integer 91')
        check(digest(saved) == digest(report), 'Saved witness differs from current source/code/computation')
    # Package and the exact four input bytes must still be current immediately
    # before publication. No stale/frozen-source bypass exists.
    check(check_package(ROOT) == package, 'Transit package changed while auditing')
    for name, value in report['sourceSHA256'].items():
        check(hashlib.sha256((directory / name).read_bytes()).hexdigest() == value, 'Source changed before publication')
    if write:
        # Exclusive creation prevents a pre-existing symlink or hardlink at a
        # predictable temporary name from redirecting/truncating source data.
        descriptor, name = tempfile.mkstemp(prefix='.transport-relaxation-', suffix='.json.tmp', dir=directory)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf8', newline='\n') as stream:
                stream.write(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
        print('Wrote transport-free witness report:', output)
    else:
        print('Verified transport-free witness source, code and complete plan; no files changed.')
    print('Witness:', report['status'], '; hospitals:', report['hospitalCount'],
          '; limit:', report['hospitalLimit'], '; actual EGO feasibility is not established.')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Write the fixed current-package 91-site relaxation diagnosis')
    args = parser.parse_args()
    run(write=args.write)
