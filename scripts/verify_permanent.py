"""Read-only, solver-independent audit of the permanent five-scenario plan.

Checks final allocations, shared integer resources and one annual bill. It does
not certify native bounds, minimum hospital count, unqueried pairs or all-day
accessibility. The pure auditor imports no optimizer or routing implementation.
"""
import argparse
from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path
import re
import sys

import numpy as np
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PROFILES = ('car', 'weekday-0800', 'weekday-1000', 'saturday-1000', 'sunday-1000')
WEIGHTS = {'car': .7, **{p: .075 for p in PROFILES[1:]}}
DATES = {'weekday-0800': '2026-10-27T08:00:00+03:00', 'weekday-1000': '2026-10-27T10:00:00+03:00',
         'saturday-1000': '2026-10-31T10:00:00+03:00', 'sunday-1000': '2026-11-01T10:00:00+03:00'}
FIXED = {'threshold': 30, 'transitThreshold': 60, 'coverageTarget': 95,
         'districtFloor': 80, 'contactsPerDoctor': 2140, 'bedOccupancy': 80,
         'demandMultiplier': 1, 'operatingCostMultiplier': 1, 'costTolerance': 10,
         'trafficFactor': 1, 'hospitalLimit': None, 'carWeight': 70}
TOLERANCES = {'residents': .001, 'districtPercent': 1e-6,
              'capacity': .1, 'areaM2': .001, 'moneyTRY': 1., 'minutes': 1e-6}
D = lambda v: Decimal(str(v))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(v, name, positive=False):
    require(not isinstance(v, (bool, np.bool_)) and isinstance(v, (int, float, np.integer, np.floating)) and math.isfinite(v)
            and (v > 0 if positive else v >= 0), 'Invalid finite number: ' + name)
    return v


def integer(v, name, minimum=0):
    require(type(v) is int and v >= minimum, 'Invalid integer: ' + name)
    return v


def identity(v, name):
    require(type(v) is str and bool(v), 'Invalid identity: ' + name)
    return v


def mapping(v, name):
    require(type(v) is dict, 'Mapping required: ' + name)
    return v


def sequence(v, name):
    require(type(v) is list, 'List required: ' + name)
    return v


def canonical(v):
    return json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf8')


def identical(a, b, name):
    require(canonical(a) == canonical(b), 'Different ' + name)


def near(actual, expected, tol, name):
    number(actual, name)
    require(abs(D(actual) - D(expected)) <= D(tol), 'Incorrect ' + name)


def load_json(blob):
    def pairs(items):
        out = {}
        for k, v in items:
            require(k not in out, 'Duplicate JSON key: ' + k)
            out[k] = v
        return out
    def invalid(value):
        raise ValueError('Nonfinite JSON: ' + value)
    return json.loads(blob, object_pairs_hook=pairs, parse_constant=invalid)


def _metrics(record, served, travel, population, samples, name):
    mapping(record, name)
    unserved = max(D(0), population - served)
    for key, expected, tol in (
            ('coveredPopulation', served, '.001'),
            ('reachablePopulation', served, '.001'),
            ('unreachableOrUnlocatedPopulation', unserved, '.001'),
            ('meanPopulationDenominator', served, '.001'),
            ('coveragePercent', served / population * 100, '.000001')):
        near(record.get(key), expected, tol, name + '.' + key)
    if served:
        near(record.get('meanMinutes'), travel / served, '.000001', name + '.meanMinutes')
    else:
        require(record.get('meanMinutes') is None, 'Empty mean must be null')
    # Independently compute the population (including unserved) 90th percentile.
    cumulative = D(0); p90 = None
    for minute, weight in sorted(samples, key=lambda x: x[0]):
        cumulative += weight
        if cumulative >= population * D('.9'):
            p90 = minute
            break
    if p90 is None:
        require(record.get('p90Minutes') is None, name + ' unserved p90 must be null')
    else:
        near(record.get('p90Minutes'), p90, '.000001', name + '.p90Minutes')


def audit(result, data, planning, matrices, policy):
    """Pure final-plan checks; matrices contain all current candidate columns.

    Positive infinity is unknown/non-retained support, never certified absence.
    Zero-load open facilities are legal and remain in both count and cost.
    """
    with localcontext() as ctx:
        ctx.prec = 45
        try:
            report = _audit(result, data, planning, matrices, policy)
            if 'auditSummary' in result:
                identical(result['auditSummary'], report, 'saved independent audit summary')
            return report
        except (KeyError, TypeError, IndexError, OverflowError) as exc:
            raise ValueError('Malformed permanent plan/input: ' + str(exc)) from exc


def _audit(r, data, h, matrices, policy):
    mapping(r, 'result'); mapping(policy, 'policy')
    for key, expected in FIXED.items():
        if expected is None:
            require(key in policy and policy[key] is None, 'Fixed policy differs: ' + key)
        else:
            require(number(policy.get(key), key) == expected, 'Fixed policy differs: ' + key)
    require(policy.get('profileIds') == list(PROFILES), 'Five fixed policy profiles required')
    require(policy.get('id') == 'ankara-permanent-v1' and type(policy.get('version')) is int
            and policy['version'] == 1 and policy.get('clinicalStandard') is False,
            'Policy identity or clinical scope differs')
    require(policy.get('classification') == 'literature_informed_planning_policy', 'Policy classification differs')
    details = mapping(policy['profileDetails'], 'profile details')
    require(set(details) == set(PROFILES), 'Policy profile details incomplete')
    for p in PROFILES:
        require(details[p]['id'] == p and details[p]['departure'] == DATES.get(p)
                and details[p]['mode'] == ('car' if p == 'car' else 'transit'), 'Policy dated profile differs')
    if 'profileWeights' in policy:
        identical(policy['profileWeights'], WEIGHTS, 'policy weights')
    identical(r.get('policy'), policy, 'result policy')
    require(r.get('status') == 'feasible' and r.get('incumbentValidated') is True,
            'A feasible validated final result is required')
    require(r.get('provenOptimal') is False and r.get('secondaryOptimal') is False,
            'Uncertified optimality claim')
    require(r.get('artifactType') == 'permanent-hospital-plan', 'Wrong artifact type')
    ident = mapping(r['identity'], 'identity')
    require(set(ident) == {'modelCodeLF_SHA256', 'sourceSHA256', 'planningVersion', 'policyId', 'transitPackageId'},
            'Identity fields differ')
    for field in ('modelCodeLF_SHA256', 'sourceSHA256'):
        values = mapping(ident[field], field)
        require(values and all(type(k) is str and type(v) is str and re.fullmatch('[a-f0-9]{64}', v)
                               for k, v in values.items()), 'Invalid hash identities')
    package = ident['transitPackageId']
    require(type(package) is str and re.fullmatch('motis-[a-f0-9]{64}', package), 'Invalid MOTIS identity')
    require(ident['planningVersion'] == h['version'] and ident['policyId'] == policy['id'], 'Planning/policy version differs')
    require(r.get('planningVersion') == h['version'], 'Top-level planning version differs')
    expected_metadata = {**data['metadata'], 'activeTransitEngine': 'motis', 'activeTransitPackageId': package}
    identical(r.get('metadata'), expected_metadata, 'current data metadata')
    evidence = mapping(r['transitEvidence'], 'transit evidence')
    require(evidence.get('engine') == 'motis' and evidence.get('packageId') == package
            and evidence.get('engineVersion') == '2.10.2'
            and evidence.get('datasetScenario') == 'historical_Ankara_community_GTFS_user_accepted_20261026'
            and evidence.get('unknownMeansNoService') is False
            and evidence.get('allCandidateInfeasibilityProofAllowed') is False,
            'Transit provenance/scope differs')
    identical(evidence.get('profileDates'), DATES, 'dated MOTIS profiles')
    identical(evidence.get('scope'), policy['permanence']['timeCoverageLimit'], 'time coverage scope')
    districts = sequence(data['districts'], 'districts')
    demands = sequence(data['demands'], 'demands')
    candidates = sequence(data['candidates'], 'candidates')
    require(districts and demands and candidates, 'Empty source arrays')
    total = D(number(data['metadata']['provincePopulation'], 'province population', True))
    dm = {}
    for d in districts:
        key = identity(d['id'], 'district ID')
        require(key not in dm, 'Duplicate district ID')
        dm[key] = D(number(d['population'], 'district population', True))
    require(sum(dm.values()) == total, 'District population denominator differs from province')
    pop = []; demand_ids = set(); located = dict.fromkeys(dm, D(0))
    for d in demands:
        key = identity(d['id'], 'demand ID')
        require(key not in demand_ids and d['districtId'] in dm, 'Duplicate demand/unknown district')
        demand_ids.add(key); value = D(number(d['population'], 'demand population'))
        pop.append(value); located[d['districtId']] += value
    require(all(located[k] <= dm[k] for k in dm), 'Located population exceeds full district denominator')
    require(len({identity(c['id'], 'candidate ID') for c in candidates}) == len(candidates),
            'Duplicate source candidate ID')
    require(set(mapping(matrices, 'matrices')) == set(PROFILES), 'Missing/extra profile matrix')
    arrays = {}
    for name in PROFILES:
        raw = np.asarray(matrices[name])
        allowed = {(len(demands), len(candidates)), (len(demands), len(candidates) + len(data.get('hospitals', [])))}
        require(raw.dtype.kind in 'fiu' and raw.shape in allowed, 'Matrix type/shape: ' + name)
        require(not np.isnan(raw).any() and not (raw < 0).any(), 'Invalid matrix: ' + name)
        arrays[name] = raw[:, :len(candidates)]
    design, rates, eco = h['design'], h['rates'], h['economics']
    minimum = integer(design['minimumDoctorsPerSite'], 'minimum doctors', 1)
    da = D(number(design['areaPerDoctorM2'], 'doctor area', True))
    floors = number(design['maxFloors'], 'floors', True)
    contact = D(number(rates['contactsPerResident'], 'contact rate', True))
    bedrate = D(number(rates['bedDaysPerResident'], 'bed rate', True))
    target = total * D('.95'); throughput = D(2140); occupancy = D('.8')
    staff_bound = max(minimum, math.ceil(float(total) * 95 / 100 * float(contact) / 2140))
    templates = {}
    for t in sequence(h['templates'], 'templates'):
        key = identity(t['id'], 'template ID'); require(key not in templates, 'Duplicate template')
        integer(t['beds'], 'template beds', 1); number(t['grossAreaM2'], 'template area', True)
        templates[key] = t
    require(templates, 'No templates')
    cp = mapping(r['commonPlan'], 'common plan')
    count = integer(cp['hospitalCount'], 'hospital count', 1)
    selected_rows = sequence(cp['selected'], 'common selected')
    require(len(selected_rows) == count == integer(r['hospitalCount'], 'reported count', 1), 'Count differs')
    selected = {}; points = []; minimum_area = math.inf
    transform = Transformer.from_crs(4326, 32636, always_xy=True)
    for s in selected_rows:
        j = integer(s['candidateIndex'], 'candidate index')
        require(j < len(candidates) and j not in selected, 'Unknown/duplicate candidate')
        base = candidates[j]
        require(type(s['id']) is str and s['id'] == base['id'], 'Candidate ID differs')
        radius = number(base['footprintRadiusMeters'], 'radius', True)
        near(s['footprintRadiusMeters'], radius, 0, 'footprint radius')
        lon, lat = number(base['lon'], 'longitude'), number(base['lat'], 'latitude')
        require(30 <= lon <= 35 and 38 <= lat <= 42, 'Candidate outside Ankara envelope')
        require(type(s['templateId']) is str and s['templateId'] in templates, 'Unknown template')
        t = templates[s['templateId']]
        require(integer(s['beds'], 'beds', 1) == t['beds'], 'Template beds differ')
        doctors = integer(s['doctors'], 'doctors', minimum)
        area = D(t['grossAreaM2']) + doctors * da
        area_bound = math.floor(math.nextafter((math.pi * radius ** 2 * floors + .001
                                              - min(x['grossAreaM2'] for x in templates.values())) / float(da), math.inf))
        require(doctors <= min(staff_bound, area_bound), 'Original staff upper bound exceeded')
        near(s['grossAreaM2'], area, '.001', 'gross area')
        slack = math.pi * radius ** 2 * floors - float(area)
        require(slack >= -.001, 'Plot capacity exceeded'); minimum_area = min(minimum_area, slack)
        number(s['maximumAssignedPopulationAcrossProfiles'], 'maximum site load')
        selected[j] = s; points.append((j, transform.transform(lon, lat), radius))
    for i, (_, point, radius) in enumerate(points):
        for _, previous, other_radius in points[:i]:
            require(math.dist(point, previous) >= radius + other_radius - 1e-7, 'Selected footprints overlap')
    indices = sequence(r['selectedIndices'], 'selected indices')
    require(all(type(i) is int for i in indices) and indices == list(selected), 'Selected indices differ')
    enriched = sequence(r['selected'], 'enriched selected')
    require(len(enriched) == count, 'Enriched selected count differs')
    for s, j in zip(enriched, selected):
        for key, expected in selected[j].items():
            identical(s.get(key), expected, 'selected.' + key)
        for key, value in candidates[j].items():
            if type(value) in (int, float): near(s.get(key), value, 0, 'selected source.' + key)
            else: identical(s.get(key), value, 'selected source.' + key)
    for key, expected in (('totalBeds', sum(s['beds'] for s in selected.values())),
                          ('totalDoctors', sum(s['doctors'] for s in selected.values()))):
        require(integer(cp[key], key, 1) == expected, key + ' differs')
        require(integer(r['capacity'][key], 'capacity ' + key, 1) == expected, 'Capacity ' + key + ' differs')
    core_profiles = sequence(cp['profiles'], 'common profiles')
    require([p.get('profile') for p in core_profiles] == list(PROFILES), 'Five complete ordered profiles required')
    api_profiles = mapping(r['profiles'], 'API profiles')
    require(set(api_profiles) == set(PROFILES), 'API profile set differs')
    all_loads = {}; derived = {}; minimum_contact = minimum_bed = None
    for profile in core_profiles:
        name = profile['profile']; limit = 30 if name == 'car' else 60
        served = [D(0)] * len(pop); loads = dict.fromkeys(selected, D(0)); flows = {}; samples = []
        origin_sites = [set() for _ in pop]
        dtravel = dict.fromkeys(dm, D(0)); dsamples = {k: [] for k in dm}
        travel = D(0)
        for f in sequence(profile['allocations'], name + ' core allocations'):
            i = integer(f['demandIndex'], 'allocation demand'); j = integer(f['candidateIndex'], 'allocation site')
            require(i < len(pop) and j in selected and (i, j) not in flows, 'Unknown/closed/duplicate flow')
            amount = D(number(f['population'], 'positive flow', True))
            require(pop[i] > 0, 'Positive allocation from zero population')
            minute = float(arrays[name][i, j])
            require(math.isfinite(minute) and 0 <= minute <= limit, 'Unknown or over-threshold allocation')
            near(f['minutes'], minute, '0.000001', 'matrix minutes')
            served[i] += amount; loads[j] += amount; flows[i, j] = (amount, minute); origin_sites[i].add(j)
            travel += amount * D(minute); samples.append((minute, amount))
            k = demands[i]['districtId']; dtravel[k] += amount * D(minute); dsamples[k].append((minute, amount))
        covered = sum(served)
        require(abs(covered - target) <= D('.001'), name + ' exact province target failed')
        require(all(a <= b + D('.001') for a, b in zip(served, pop)), name + ' origin population exceeded')
        dserved = dict.fromkeys(dm, D(0))
        for d, amount in zip(demands, served): dserved[d['districtId']] += amount
        for k in dm:
            require(dserved[k] / dm[k] * 100 >= D(80) - D('.000001'), name + ' district percentage target failed')
        near(profile['coveredPopulation'], covered, '.001', name + ' core coverage')
        near(profile['coveragePercent'], covered / total * 100, '.000001', name + ' core coverage percent')
        near(profile['meanMinutes'], travel / target, '.000001', name + ' core mean')
        rows = sequence(profile['districts'], 'core districts')
        require([x.get('id') for x in rows] == list(dm), 'Core district IDs differ')
        for row in rows: near(row['coveragePercent'], dserved[row['id']] / dm[row['id']] * 100, '.000001', 'core district coverage')
        api = mapping(api_profiles[name], 'API profile')
        identical(api.get('profile'), details[name], 'profile display identity')
        if name != 'car':
            identical(api.get('transitEvidence'), {'engine': 'motis', 'packageId': package,
                'profile': name, 'departure': DATES[name]}, 'profile transit evidence')
        _metrics(api['metrics'], covered, travel, total, samples, name)
        rows = sequence(api['districts'], 'API districts')
        require([x.get('id') for x in rows] == list(dm), 'API district IDs differ')
        for row, source in zip(rows, districts):
            for key, expected in source.items(): identical(row.get(key), expected, 'district source ' + key)
            k = row['id']; _metrics(row, dserved[k], dtravel[k], dm[k], dsamples[k], name + '/' + k)
        assignments = sequence(api['assignments'], 'assignments')
        require(len(assignments) == len(pop), 'Assignment origin count differs')
        for i, a in enumerate(assignments):
            identical(a.get('demandId'), demands[i]['id'], 'assignment demand ID')
            parts = sequence(a['allocations'], 'assignment parts'); seen = set(); previous = None
            for f in parts:
                j = integer(f['candidateIndex'], 'assignment candidate')
                require(j not in seen and (i, j) in flows, 'API allocation unknown/duplicate')
                seen.add(j); amount, minute = flows[i, j]
                near(f['population'], amount, 0, 'API amount'); near(f['minutes'], minute, '.000001', 'API minute')
                near(f['fraction'], amount / pop[i] if pop[i] else 0, '.000000001', 'allocation fraction')
                identical(f.get('candidateId'), candidates[j]['id'], 'allocation candidate ID')
                require(previous is None or amount <= previous, 'Assignments not in descending population order')
                previous = amount
            require(seen == origin_sites[i], 'API/core allocations differ')
            primary = parts[0] if parts else None
            identical(a['candidateIndex'], primary['candidateIndex'] if primary else None, 'primary candidate')
            identical(a['minutes'], primary['minutes'] if primary else None, 'primary minutes')
            identical(a.get('candidateId'), candidates[primary['candidateIndex']]['id'] if primary else None, 'primary candidate ID')
            near(a['servedFraction'], served[i] / pop[i] if pop[i] else 0, '.000000001', 'served fraction')
            require(type(a['covered']) is bool and a['covered'] == (served[i] >= pop[i] - D('.0001')), 'Covered flag differs')
        for j, s in selected.items():
            cs = s['doctors'] * throughput - loads[j] * contact
            bs = s['beds'] * D(365) * occupancy - loads[j] * bedrate
            require(cs >= D('-.1') and bs >= D('-.1'), name + ' separate bed/physician capacity exceeded')
            minimum_contact = cs if minimum_contact is None else min(minimum_contact, cs)
            minimum_bed = bs if minimum_bed is None else min(minimum_bed, bs)
        all_loads[name] = loads
        derived[name] = {'coveredPopulation': float(covered), 'coveragePercent': float(covered / total * 100),
            'minimumDistrictCoveragePercent': float(min(dserved[k] / dm[k] * 100 for k in dm)),
            'meanMinutes': float(travel / covered), 'maximumAssignedMinutes': max((m for m, _ in samples), default=0),
            'positiveAllocations': len(flows)}
    # Independently reconstruct the shared resources, material partition and bill.
    for key in ('realDiscountRate', 'buildingUnitCostTRY', 'annualFixedSiteCostTRY',
                'annualDoctorCostTRY', 'annualBedSupportCostTRY', 'costPerContactTRY'):
        number(eco[key], key)
    years = D(number(eco['horizonYears'], 'horizon', True)); rate = D(eco['realDiscountRate'])
    annuity = rate / (1 - (1 + rate) ** -years) if rate else 1 / years
    material = target * contact * D(eco['costPerContactTRY'])
    capex = operating = D(0)
    sites = enriched
    require([s.get('candidateIndex') for s in sites] == list(selected), 'Capacity site IDs differ')
    for s, j in zip(sites, selected):
        core = selected[j]
        for key, expected in core.items(): identical(s.get(key), expected, 'capacity site ' + key)
        load = max(all_loads[p][j] for p in PROFILES)
        near(core['maximumAssignedPopulationAcrossProfiles'], load, '.001', 'maximum load')
        near(s['assignedPopulation'], load, '.001', 'assigned load')
        require(set(s['assignedPopulationByProfile']) == set(PROFILES), 'Site profile loads incomplete')
        for p in PROFILES: near(s['assignedPopulationByProfile'][p], all_loads[p][j], '.001', 'site profile load')
        require(s['resourceLoadBasis'] == 'maximum_of_five_alternative_full_demand_scenarios_not_sum', 'Resource load semantics differ')
        require(s['materialAccountingBasis'] == 'car_allocation_partition_of_one_annual_bill', 'Material partition differs')
        near(s['materialAccountingPopulation'], all_loads['car'][j], '.001', 'material population')
        area = D(templates[s['templateId']]['grossAreaM2']) + s['doctors'] * da
        site_capex = area * D(eco['buildingUnitCostTRY'])
        breakdown = {'fixedSiteTRY': D(eco['annualFixedSiteCostTRY']),
            'physiciansTRY': s['doctors'] * D(eco['annualDoctorCostTRY']),
            'bedSupportTRY': s['beds'] * D(eco['annualBedSupportCostTRY']),
            'materialsTRY': all_loads['car'][j] * contact * D(eco['costPerContactTRY'])}
        require(set(s['operatingBreakdown']) == set(breakdown), 'Cost component set differs')
        for key, expected in breakdown.items(): near(s['operatingBreakdown'][key], expected, 1, 'site ' + key)
        site_op = sum(breakdown.values())
        near(s['constructionCostTRY'], site_capex, 1, 'site capex')
        near(s['annualOperatingCostTRY'], site_op, 1, 'site opex')
        near(s['annualEquivalentCostTRY'], site_capex * annuity + site_op, 1, 'site annual cost')
        near(s['annualContacts'], load * contact, '.1', 'site contacts')
        near(s['annualBedDays'], load * bedrate, '.1', 'site bed days')
        near(s['contactCapacity'], s['doctors'] * throughput, '.1', 'contact capacity')
        near(s['bedDayCapacity'], s['beds'] * D(365) * occupancy, '.1', 'bed capacity')
        near(s['doctorUtilizationPercent'], load * contact / (s['doctors'] * throughput) * 100, '.000001', 'site doctor utilization')
        near(s['bedUtilizationPercent'], load * bedrate / (s['beds'] * D(365) * occupancy) * 100, '.000001', 'site bed utilization')
        near(s['physicalOccupancyPercent'], load * bedrate / (s['beds'] * D(365)) * 100, '.000001', 'site physical occupancy')
        near(s['areaUtilizationPercent'], float(area) / (math.pi * candidates[j]['footprintRadiusMeters'] ** 2 * floors) * 100,
             '.000001', 'site area utilization')
        near(s['annualVisits'], load * D(number(rates.get('visitsPerResident', rates['contactsPerResident']), 'visits rate')), '.1', 'site visits')
        near(s['annualAdmissions'], load * D(number(rates.get('admissionsPerResident', 0), 'admission rate')), '.1', 'site admissions')
        capex += site_capex; operating += site_op - breakdown['materialsTRY']
    operating += material; annual = capex * annuity + operating
    cap = mapping(r['capacity'], 'capacity')
    for key, expected in (('annualEquivalentCostTRY', annual), ('annualMaterialCostTRY', material),
                          ('constructionCostTRY', capex), ('annualOperatingCostTRY', operating),
                          ('lifecyclePresentCostTRY', annual / annuity)):
        near(cap[key], expected, 1, key)
    for key, expected in (('annualEquivalentCostTRY', annual), ('annualMaterialCostTRY', material),
                          ('annualFixedResourceCostTRY', annual - material)):
        near(cp[key], expected, 1, 'common ' + key)
    require(cap['planningVersion'] == h['version'] and cap['annualDemandCountedOnce'] is True, 'Capacity version/annual demand differs')
    visits = D(rates.get('visitsPerResident', rates['contactsPerResident']))
    admissions = D(rates.get('admissionsPerResident', 0))
    for key, expected in {'annualContactsDemand': total * contact, 'annualContactsServed': target * contact,
        'annualBedDaysDemand': total * bedrate, 'annualBedDaysServed': target * bedrate,
        'annualVisitsDemand': total * visits, 'annualVisitsServed': target * visits,
        'annualAdmissionsDemand': total * admissions}.items(): near(cap[key], expected, '.1', key)
    near(cap['doctorUtilizationPercent'], target * contact / (cp['totalDoctors'] * throughput) * 100, '.000001', 'doctor utilization')
    near(cap['bedUtilizationPercent'], target * bedrate / (cp['totalBeds'] * D(365) * occupancy) * 100, '.000001', 'bed utilization')
    near(cap['horizonYears'], years, 0, 'horizon years'); near(cap['realDiscountRate'], rate, 0, 'real discount')
    reference = D(number(cap['referenceCostTRY'], 'reference cost', True))
    budget = reference * D('1.1')
    near(cap['budgetLimitTRY'], budget, max(.01, float(budget) * 1e-12), 'reference budget')
    require(annual <= budget + D(max(.01, float(budget) * 1e-12)), 'Stated reference budget exceeded')
    near(cap['referenceStage']['annualEquivalentCostTRY'], reference, 1, 'reference stage cost')
    near(cap['referenceStage']['coveragePercent'], 95, 0, 'reference coverage')
    critical = min(PROFILES[1:], key=lambda p: (-derived[p]['meanMinutes'], p))
    require(r['criticalTransitProfile'] == critical, 'Critical transit profile is not the worst complete mean')
    scenario_keys = ('threshold', 'transitThreshold', 'coverageTarget', 'districtFloor', 'trafficFactor',
        'demandMultiplier', 'bedOccupancy', 'contactsPerDoctor', 'costTolerance', 'hospitalLimit',
        'operatingCostMultiplier', 'transitEngine', 'carWeight')
    identical(r.get('scenario'), {k: policy[k] for k in scenario_keys} |
              {'mode': 'hybrid', 'transitProfile': critical}, 'immutable display scenario')
    modal = mapping(r['modalResults'], 'modal results')
    require(set(modal) == {'car', 'transit'}, 'Modal view set differs')
    identical(modal['car'], api_profiles['car'], 'car modal view')
    identical(modal['transit'], api_profiles[critical], 'critical transit modal view')
    for key in ('metrics', 'districts', 'assignments'): identical(r[key], api_profiles['car'][key], 'top-level car ' + key)
    summary = mapping(r['permanentSummary'], 'permanent summary')
    identical(summary['profileWeights'], WEIGHTS, 'profile objective weights')
    thresholds = {p: 30 if p == 'car' else 60 for p in PROFILES}
    identical(summary['thresholds'], thresholds, 'profile thresholds')
    for key, expected in {'carWeight': 70, 'transitWeight': 30, 'profileCount': 5,
            'transitProfileCount': 4, 'fullDemandScenarioCount': 5}.items(): near(summary[key], expected, 0, key)
    for key, expected in {'annualDemandCountedOnce': True, 'allFiveHardTargetsValidated': True,
            'sameIndividualsAcrossModesConstrained': False, 'sameIndividualsAcrossProfilesConstrained': False}.items():
        require(summary[key] is expected, 'Incorrect summary flag ' + key)
    require(summary['criticalTransitProfile'] == critical and
            summary['criticalTransitSelection'] == 'maximum_of_four_population_weighted_profile_means' and
            summary['criticalTransitTieBreak'] == 'ascending_profile_id', 'Critical selection semantics differ')
    means = {p: D(derived[p]['meanMinutes']) for p in PROFILES}
    computed = {'weightedMeanMinutes': sum(means[p] * D(WEIGHTS[p]) for p in PROFILES),
        'meanTransitMinutes': sum(means[p] for p in PROFILES[1:]) / 4,
        'worstTransitMeanMinutes': means[critical],
        'minimumProvinceCoveragePercent': min(x['coveragePercent'] for x in derived.values()),
        'minimumDistrictCoveragePercent': min(x['minimumDistrictCoveragePercent'] for x in derived.values())}
    for key, expected in computed.items(): near(summary[key], expected, '.000001', key)
    return {'format': 1, 'valid': True, 'scope': 'final_five_profile_physical_allocation_and_one_annual_bill',
        'profileCount': 5, 'transitProfileCount': 4, 'hospitalCount': count,
        'beds': cp['totalBeds'], 'doctors': cp['totalDoctors'], 'profiles': derived,
        'criticalTransitProfile': critical, **{k: float(v) for k, v in computed.items()},
        'annualEquivalentCostTRY': float(annual), 'annualMaterialCostTRY': float(material),
        'providedReferenceCostTRY': float(reference), 'providedReferenceBudgetTRY': float(budget),
        'budgetSlackTRY': float(budget - annual), 'referenceIncumbentReplayed': False,
        'minimumDoctorContactSlack': float(minimum_contact), 'minimumBedDaySlack': float(minimum_bed),
        'minimumAreaSlackM2': minimum_area, 'tolerances': dict(TOLERANCES),
        'nativeBoundsCertified': False, 'minimumHospitalCountProven': False,
        'allDayServiceProven': False, 'realCityFeasibilityProven': False,
        'unqueriedTransitPairsAreUnknown': True, 'sameIndividualsAcrossProfilesConstrained': False}


def current_report():
    """Load only current saved artifacts; no route request, mutation or solve."""
    from backend import permanent_evidence as evidence
    from backend import motis
    before_sources = evidence.source_identities(); before_code = evidence.code_identities()
    path = ROOT / 'data/processed/permanent-plan.json'
    blob = path.read_bytes(); result = load_json(blob)
    data = load_json((ROOT / 'data/processed/dataset.json').read_bytes())
    planning = load_json((ROOT / 'data/processed/health-planning.json').read_bytes())
    policy = load_json((ROOT / 'data/planning-policy.json').read_bytes())
    # Identity field names are finalized with the service's evidence helper.
    require(result.get('planId') == evidence.plan_id(result), 'Stale/tampered permanent plan ID')
    identical(result.get('identity', {}).get('sourceSHA256'), before_sources, 'entry source identities')
    identical(result.get('identity', {}).get('modelCodeLF_SHA256'), before_code, 'entry model identities')
    identical(result.get('identity'), evidence.current_identity(), 'current artifact identity')
    with np.load(ROOT / 'data/processed/car-matrix.npz', allow_pickle=False) as archive:
        car = archive['minutes'].copy()
    matrices = {'car': car[:, :len(data['candidates'])]}
    for profile in PROFILES[1:]: matrices[profile] = motis.load_matrix(profile)[:, :len(data['candidates'])]
    report = audit(result, data, planning, matrices, policy)
    require(before_sources == evidence.source_identities() and before_code == evidence.code_identities(),
            'Sources/model changed while verifying')
    require(path.read_bytes() == blob, 'Saved plan changed while verifying')
    return {**report, 'planId': result['planId'], 'savedPlanSHA256': hashlib.sha256(blob).hexdigest(),
            'sourceSHA256': before_sources, 'modelCodeLF_SHA256': before_code}


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    print(json.dumps(current_report(), ensure_ascii=False, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
