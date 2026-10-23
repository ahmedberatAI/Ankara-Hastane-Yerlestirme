"""Independently validate a 44-start common-resource plan; no solver or writer.

The frozen four-profile certificates stay separate. This module checks all
positive flows and one annual bill directly; it never imports window_model or
window_solver, and never mutates the old auditor's global profile constants.
"""
from decimal import localcontext
from copy import deepcopy
from datetime import datetime
import argparse
import io
import json
import math
from pathlib import Path
import sys
from zipfile import ZipFile

import numpy as np
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import audit_joint_plan as cost
from scripts.audit_joint_travel import MODEL_FILES as FROZEN_MODEL_FILES
from scripts.transit_provenance import check_package

MODEL_FILES = (*FROZEN_MODEL_FILES, 'backend/window_model.py', 'backend/window_solver.py',
               'scripts/run_window_plan.py', 'scripts/audit_window_plan.py', 'backend/window_seed.py')
SOURCE_FILES = (*cost.SOURCE_FILES, 'joint-plan.json')
ROUTING_CODE_FILES = ('backend/window_routing.py', 'scripts/build_window_matrices.py',
                      'backend/timetable.py', 'scripts/transit_provenance.py')
ROUTING_SOURCE_FILES = tuple('data/processed/' + name for name in (
    'dataset.json', 'health-planning.json', 'example-transit-result.json', 'transit-package.json',
    'joint-plan.json', 'travel-plan.json', 'travel-proof.json', 'travel-summary.json', 'ego-network.json.gz',
    'ego-access.npz', 'ego-egress.npz', 'ego-transfers.npz', 'ego-direct.npz',
    *(f'transit-{name}-matrix.npz' for name in cost.PROFILES))) + ('docs/experiments/departure-0805-evidence.zip',)
OFFSETS = (0, -5, 5, -4, -3, -2, -1, 1, 2, 3, 4)
BASE_PROFILES = cost.PROFILES
INDEPENDENT_ORIGINS = (42, 295, 54, 510, 1239, 638, 963, 228)
D, check, keys, number, integer = cost.D, cost.check, cost.keys, cost.number, cost.integer
identity, sequence, hash_value, near = cost.identity, cost.sequence, cost.hash_value, cost.near
sha256, digest, load_json = cost.sha256, cost.digest, cost.load_json
LOADED_AUDITOR_FILES = ('scripts/audit_window_plan.py', 'scripts/audit_joint_plan.py',
                        'scripts/audit_joint_travel.py', 'scripts/transit_provenance.py')
LOADED_AUDITOR_HASHES = {name: sha256((ROOT / name).read_bytes().replace(b'\r\n', b'\n'))
                         for name in LOADED_AUDITOR_FILES}


def expected_profiles():
    result = []
    for offset in OFFSETS:
        for base in BASE_PROFILES:
            day, clock = base.rsplit('-', 1)
            seconds = int(clock[:2]) * 3600 + int(clock[2:]) * 60 + offset * 60
            result.append(dict(id=f'{day}-{seconds // 3600:02d}{seconds % 3600 // 60:02d}',
                baseProfileId=base, offsetMinutes=offset, serviceDay=day,
                departureSeconds=seconds, timeZone='Europe/Istanbul'))
    return result


def same_hashes(actual, expected, names, label):
    keys(actual, names, label); keys(expected, names, 'current ' + label)
    for name in names:
        check(hash_value(actual[name]) == hash_value(expected[name]), 'Stale ' + label + ': ' + name)


def code_hashes(root=ROOT):
    return {name: sha256((Path(root) / name).read_bytes().replace(b'\r\n', b'\n')) for name in MODEL_FILES}


def routing_package_id(manifest):
    fields = ('format', 'artifactType', 'mode', 'status', 'parentTransitPackageId', 'profiles',
              'initialProfileIds', 'producedProfileIds', 'sourceSHA256', 'routingCodeLF_SHA256',
              'frozenModelCodeLF_SHA256', 'indices', 'constants', 'archived0805')
    payload = {name: manifest[name] for name in fields}
    payload['matrices'] = [{key: row[key] for key in ('profileId', 'file', 'sha256', 'shape')}
                           for row in manifest['matrices']]
    return 'window-' + digest(payload)


def validate_manifest(manifest, data, matrices, indices_document, baseline_matrices):
    """Check the full declared grid, ordered identities, baselines and FIFO.

    Byte SHA checks belong to the file reader. This semantic check does not
    claim to rerun every shortest-path query or the producer's event sampler.
    """
    keys(manifest, ('format', 'artifactType', 'mode', 'status', 'parentTransitPackageId',
        'windowRoutingPackageId', 'profiles', 'initialProfileIds', 'producedProfileIds',
        'sourceSHA256', 'routingCodeLF_SHA256', 'frozenModelCodeLF_SHA256', 'indices',
        'matrices', 'constants', 'crossProfileAudit', 'archived0805',
        'builtAt', 'elapsedSeconds', 'scope'), 'routing manifest')
    check(type(manifest['format']) is int and manifest['format'] == 1, 'Manifest format must be integer 1')
    check(manifest['artifactType'] == 'departure-window-matrices' and manifest['mode'] == 'full'
          and manifest['status'] == 'accepted', 'Complete accepted full matrix package required')
    expected = expected_profiles(); names = [row['id'] for row in expected]
    check(digest(manifest['profiles']) == digest(expected), 'Clock/calendar/profile grid differs')
    check(manifest['producedProfileIds'] == names and manifest['initialProfileIds'] == names[:12],
          'Missing, duplicate or reordered generated profiles')
    check(manifest['parentTransitPackageId'] == data['metadata']['transitPackageId'], 'Routing parent package differs')
    stamp = datetime.fromisoformat(identity(manifest['builtAt'], 'manifest build time').replace('Z', '+00:00'))
    check(stamp.tzinfo is not None and stamp.utcoffset().total_seconds() == 0, 'UTC build timestamp required')
    number(manifest['elapsedSeconds'], 'manifest elapsed time'); identity(manifest['scope'], 'routing scope')
    keys(manifest['sourceSHA256'], ROUTING_SOURCE_FILES, 'routing sources')
    keys(manifest['routingCodeLF_SHA256'], ROUTING_CODE_FILES, 'routing code')
    keys(manifest['frozenModelCodeLF_SHA256'], FROZEN_MODEL_FILES, 'frozen model code')
    for mapping in ('sourceSHA256', 'routingCodeLF_SHA256', 'frozenModelCodeLF_SHA256'):
        for value in manifest[mapping].values(): hash_value(value)
    keys(manifest['archived0805'], ('archive', 'matrixMember', 'matrixSHA256', 'reportMember', 'reportSHA256'), '08:05 archive reference')
    check(manifest['archived0805']['archive'] == 'docs/experiments/departure-0805-evidence.zip'
          and manifest['archived0805']['matrixMember'] == 'work/referees/profile-shift-full-v07.npz'
          and manifest['archived0805']['reportMember'] == 'work/referees/profile-shift-full-v07.json', 'Archive reference differs')
    for name in ('matrixSHA256', 'reportSHA256'): hash_value(manifest['archived0805'][name])
    check(manifest['windowRoutingPackageId'] == routing_package_id(manifest), 'Routing content identity differs')
    check(digest(manifest['constants']) == digest(dict(horizonSeconds=7200, boardingSlackSeconds=60, maxBoardings=3)),
          'Routing limits changed')
    keys(indices_document, ('origins', 'candidates'), 'index document')
    origins = [dict(index=i, id=row['id']) for i, row in enumerate(data['demands'])]
    candidates = [dict(index=i, id=row['id']) for i, row in enumerate(data['candidates'])]
    check(digest(indices_document['origins']) == digest(origins)
          and digest(indices_document['candidates']) == digest(candidates), 'Matrix row/column identities differ')
    keys(manifest['indices'], ('file', 'sha256', 'demandIndexSHA256', 'candidateIndexSHA256'), 'index identity')
    check(manifest['indices']['file'] == 'indices.json', 'Unexpected index filename')
    hash_value(manifest['indices']['sha256'])
    check(manifest['indices']['demandIndexSHA256'] == digest(origins)
          and manifest['indices']['candidateIndexSHA256'] == digest(candidates), 'Index order digest differs')
    check(type(matrices) is dict and set(matrices) == set(names), 'All 44 complete matrices required')
    records = sequence(manifest['matrices'], 'matrix records')
    check(len(records) == len(names), 'Missing matrix records')
    files = set(); n, m = len(origins), len(candidates)
    check(type(baseline_matrices) is dict and set(baseline_matrices) == set(BASE_PROFILES), 'Original baselines required')
    for expected_row, row in zip(expected, records):
        keys(row, ('profileId', 'file', 'sha256', 'shape', 'audit'), 'matrix record')
        name = expected_row['id']; check(row['profileId'] == name, 'Matrix record order differs')
        filename = identity(row['file'], 'matrix filename')
        check(Path(filename).name == filename and filename.endswith('.npz') and ':' not in filename
              and '/' not in filename and '\\' not in filename and filename.casefold() not in files,
              'Unsafe/duplicate matrix path')
        files.add(filename.casefold()); hash_value(row['sha256'])
        check(digest(row['shape']) == digest([n, m]), 'Matrix recorded dimensions differ')
        matrix = matrices[name]
        check(isinstance(matrix, np.ndarray) and matrix.dtype.kind == 'f' and matrix.shape == (n, m),
              'Matrix dimensions/type differ')
        check(not np.any(np.isnan(matrix)) and not np.any(matrix < 0), 'Invalid matrix values')
        audit = row['audit']
        keys(audit, ('validated', 'independentOriginIndices', 'independentDestinationsPerOrigin',
                     'independentMaxMinutesError', 'baselineCheck', 'elapsedSeconds'), 'routing audit')
        check(audit['validated'] is True, 'Routing checks not accepted')
        sample = sequence(audit['independentOriginIndices'], 'independent origins')
        check(bool(sample) and len(sample) == len(set(sample)), 'Missing/duplicate independent sample')
        for index in sample: check(integer(index, 'sample origin') < n, 'Sample origin outside full matrix')
        check(sample == list(INDEPENDENT_ORIGINS), 'Declared independent origin sample changed')
        check(integer(audit['independentDestinationsPerOrigin'], 'sample destinations') == m, 'Incomplete sampled destinations')
        check(number(audit['independentMaxMinutesError'], 'sample error') <= 2e-5, 'Independent routing error')
        number(audit['elapsedSeconds'], 'routing elapsed time')
        baseline = audit['baselineCheck']
        if name in BASE_PROFILES:
            check(np.array_equal(matrix, baseline_matrices[name]), 'Canonical source matrix changed')
            keys(baseline, ('kind', 'comparedRows', 'comparedColumns', 'maxMinutesError', 'bitIdentical'), 'baseline check')
            check(baseline['kind'] == 'canonical' and integer(baseline['comparedRows'], 'baseline rows') == n
                  and integer(baseline['comparedColumns'], 'baseline columns') == m
                  and type(baseline['maxMinutesError']) in (int, float) and baseline['maxMinutesError'] == 0
                  and baseline['bitIdentical'] is True, 'Original matrix baseline check differs')
        elif name == 'weekday-0805':
            keys(baseline, ('kind', 'comparedRows', 'comparedColumns', 'maxMinutesError', 'bitIdentical'), '08:05 baseline')
            check(baseline['kind'] == 'archived_0805_subset' and integer(baseline['comparedRows'], '08:05 rows') == n
                  and 0 < integer(baseline['comparedColumns'], '08:05 columns') <= m
                  and type(baseline['maxMinutesError']) in (int, float) and baseline['maxMinutesError'] == 0
                  and baseline['bitIdentical'] is True, '08:05 archived comparison missing')
        else: check(baseline is None, 'Unexpected canonical baseline claim')
    cross = manifest['crossProfileAudit']; keys(cross, ('comparisons', 'toleranceMinutes'), 'cross-profile audit')
    check(type(cross['toleranceMinutes']) in (int, float) and cross['toleranceMinutes'] == 2e-5, 'FIFO tolerance differs')
    comparisons = sequence(cross['comparisons'], 'FIFO records'); pairs = []
    for base in BASE_PROFILES:
        ordered = sorted((p for p in expected if p['baseProfileId'] == base), key=lambda x: x['departureSeconds'])
        pairs.extend(zip(ordered[:-1], ordered[1:]))
    check(len(comparisons) == len(pairs), 'Missing FIFO comparisons')
    lookup = {}
    for row in comparisons:
        keys(row, ('earlierProfileId', 'laterProfileId', 'commonFinitePairs', 'maxEarlyArrivalViolationMinutes'), 'FIFO comparison')
        pair = row['earlierProfileId'], row['laterProfileId']
        check(pair not in lookup, 'Duplicate FIFO pair'); lookup[pair] = row
    for earlier, later in pairs:
        pair = earlier['id'], later['id']; check(pair in lookup, 'Missing FIFO pair')
        row = lookup[pair]; common_count = 0; violation = 0.
        for first in range(0, n, 128):
            a = matrices[pair[0]][first:first+128].astype(np.float64)
            b = matrices[pair[1]][first:first+128].astype(np.float64)
            common = np.isfinite(a) & np.isfinite(b); common_count += int(common.sum())
            delta = (later['departureSeconds'] - earlier['departureSeconds']) / 60
            new_finite = ~np.isfinite(a) & np.isfinite(b)
            check(not np.any(b[new_finite] + delta < 120 - 2e-5), 'New finite route contradicts earlier search horizon')
            violation = max(violation, float(np.max(a[common] - b[common] - delta, initial=0)))
        check(integer(row['commonFinitePairs'], 'common pairs') == common_count, 'FIFO finite count differs')
        near(row['maxEarlyArrivalViolationMinutes'], violation, '0.000000001', 'FIFO violation')
        check(violation <= 2e-5, 'Absolute earliest arrival violates FIFO')
    return names


def validate_window_plan(certificate, data, health, matrices, published_reference, source_cost_certificate,
                         current_source_hashes, package_id, manifest, manifest_sha256, current_code_hashes,
                         indices_document, baseline_matrices):
    """Audit trusted parsed inputs; the read-only file wrapper establishes byte identity.

    Budget overruns fail this contract. They are not a proof that no other plan
    can satisfy the budget. No native optimizer or source search is executed.
    """
    with localcontext() as context:
        context.prec = 45
        return _validate_window(certificate, data, health, matrices, published_reference, source_cost_certificate,
            current_source_hashes, package_id, manifest, manifest_sha256, current_code_hashes,
            indices_document, baseline_matrices)


def _validate_window(cert, data, health, matrices, published, source, source_hashes, package,
                     manifest, manifest_sha, codes, indices_document, baselines):
    keys(cert, ('format', 'artifactType', 'transitPackageId', 'planningVersion', 'scenario',
               'profileManifestSHA256', 'sourceSHA256', 'modelCodeSHA256', 'budget', 'generation', 'plan'), 'window certificate')
    check(type(cert['format']) is int and cert['format'] == 1 and cert['artifactType'] == 'window-common-resource-plan',
          'Window certificate format differs')
    same_hashes(cert['sourceSHA256'], source_hashes, SOURCE_FILES, 'source hashes')
    same_hashes(cert['modelCodeSHA256'], codes, MODEL_FILES, 'model code hashes')
    check(hash_value(cert['profileManifestSHA256']) == hash_value(manifest_sha), 'Routing manifest differs')
    check(cert['transitPackageId'] == package == data['metadata']['transitPackageId'], 'Parent package differs')
    check(cert['planningVersion'] == health['version'], 'Current health version differs')
    profiles = validate_manifest(manifest, data, matrices, indices_document, baselines)
    for name in SOURCE_FILES:
        check(manifest['sourceSHA256']['data/processed/' + name] == source_hashes[name],
              'Manifest/plan source identity differs: ' + name)
    for name in FROZEN_MODEL_FILES:
        check(manifest['frozenModelCodeLF_SHA256'][name] == codes[name], 'Frozen model identity differs: ' + name)
    source_audit = cost.validate_joint_plan(source, data, health, baselines, published,
        {name: source_hashes[name] for name in cost.SOURCE_FILES}, package_id=package)
    check(digest(cert['scenario']) == digest(source['scenario']) == digest(published['scenario']), 'Scenario changed')
    budget = cert['budget']; keys(budget, ('limitTRY', 'referenceAnnualCostTRY', 'hardConstraint'), 'budget')
    check(budget['hardConstraint'] is True, 'Budget must be a hard constraint')
    limit = D(number(budget['limitTRY'], 'annual budget', positive=True))
    check(limit == D(published['capacity']['budgetLimitTRY']), 'Original budget ceiling changed')
    reference = D(source_audit['decimalAnnualEquivalentCostTRY'])
    near(budget['referenceAnnualCostTRY'], reference, '.001', 'source reference cost')
    generation = cert['generation']
    flags = dict(searchProvenOptimal=False, minimumHospitalCountProven=False, annualDemandCountedOnce=True,
                 sameIndividualsAcrossProfilesConstrained=False)
    keys(generation, ('method', 'runReportSHA256', 'vectorSHA256', 'candidateIndices',
                      'optimizedProfiles', 'validatedProfiles', *flags), 'generation')
    identity(generation['method'], 'generation method')
    hash_value(generation['runReportSHA256']); hash_value(generation['vectorSHA256'])
    for key, value in flags.items(): check(generation[key] is value, 'Unsupported generation claim: ' + key)
    pool = sequence(generation['candidateIndices'], 'candidate pool')
    for index in pool: check(integer(index, 'pool candidate') < len(data['candidates']), 'Unknown pool candidate')
    check(bool(pool) and pool == sorted(set(pool)), 'Pool must be unique sorted global candidates')
    optimized = sequence(generation['optimizedProfiles'], 'optimized profiles')
    check(bool(optimized) and len(optimized) == len(set(optimized)) and all(name in profiles for name in optimized),
          'Unknown/duplicate optimized profiles')
    check(optimized == [name for name in profiles if name in optimized]
          and all(name in optimized for name in profiles[:12]), 'Initial profile constraints missing or reordered')
    check(generation['validatedProfiles'] == profiles, 'All 44 complete profiles must be validated')
    for group in range(0, 44, 4):
        size = len(set(profiles[group:group+4]) & set(optimized))
        check(size in (0, 4), 'Optimized offsets must contain all four calendars')
    result = _resources_flows_and_cost(cert['plan'], data, health, matrices, cert['scenario'], profiles)
    check(all(site['candidateIndex'] in pool for site in result['selected']), 'Selected site outside declared candidate pool')
    annual = D(result['decimalAnnualEquivalentCostTRY']); slack = limit - annual
    check(slack >= 0, 'Hard annual budget exceeded; no feasible-budget witness certified')
    result.update(format=1, status='validated_window_model_plan', artifactType='window-common-resource-summary',
        transitPackageId=package, windowRoutingPackageId=manifest['windowRoutingPackageId'],
        planningVersion=health['version'], scenario=dict(cert['scenario']), profileManifestSHA256=manifest_sha,
        sourceSHA256=dict(source_hashes), modelCodeSHA256=dict(codes), profileCount=len(profiles),
        optimizedProfileIds=list(optimized), validatedProfileIds=list(profiles), profileDefinitions=manifest['profiles'],
        allProfilesValidated=True, annualDemandCountedOnce=True, resourcesSharedAcrossProfiles=True,
        sameIndividualsAcrossProfilesConstrained=False, solverRun=False, minimumHospitalCountProven=False,
        globalOptimalityProven=False, hardBudgetTRY=float(limit), decimalHardBudgetTRY=str(limit),
        withinHardBudget=True, budgetSlackTRY=float(slack), decimalBudgetSlackTRY=str(slack),
        sourceAnnualEquivalentCostTRY=float(reference), decimalSourceAnnualEquivalentCostTRY=str(reference),
        sourceCostDeltaTRY=float(annual-reference), decimalSourceCostDeltaTRY=str(annual-reference),
        sourceHospitalCount=source_audit['hospitalCount'], hospitalCountDelta=result['hospitalCount']-source_audit['hospitalCount'],
        candidatePoolSize=len(pool), fullCandidateCount=len(data['candidates']), generation=dict(generation),
        numericalTolerances=dict(cost.TOLERANCES),
        scope='Feasible common resources for 44 sampled minute starts only. No guarantee between sampled seconds, throughout the day, for real EGO service, clinical staffing, public budgets, minimum hospital count, or a 91-hospital conclusion. Annual demand and cost are counted once.',
        generationReferenceScope='Run and vector hashes identify generation artifacts; this validator does not replay optimization or certify a solver bound.')
    return result


def _resources_flows_and_cost(plan, data, health, matrices, scenario, profile_names):
    total = number(data['metadata']['provincePopulation'], 'province population', positive=True)
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
    check(bool(candidates) and type(matrices) is dict and set(matrices) == set(profile_names), 'Incomplete candidate/profile matrix set')
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
    check(len(profiles) == len(profile_names) and [p.get('profile') for p in profiles] == list(profile_names), 'Missing/duplicate/out-of-order profiles')
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
    clipped = [[min(pop[i], max(D(0), row[i])) for i in range(len(pop))] for row in all_served]
    correction = sum(abs(a - b) for row, clean in zip(all_served, clipped) for a, b in zip(row, clean))
    lower = [max(D(0), sum(row[i] for row in clipped) - (len(profile_names) - 1) * pop[i]) for i in range(len(pop))]
    upper = [min(row[i] for row in clipped) for i in range(len(pop))]
    def overlap(indices, denominator):
        low = sum(lower[i] for i in indices); high = sum(upper[i] for i in indices)
        return dict(denominator=denominator, lowerResidents=float(low), upperResidents=float(high),
                    lowerPercent=float(low / D(denominator) * 100), upperPercent=float(high / D(denominator) * 100))
    return dict(hospitalCount=count, beds=plan['totalBeds'], doctors=plan['totalDoctors'], selected=locations,
        profiles=profile_summaries, provincePopulation=total, locatedPopulation=float(sum(pop)),
        unlocatedPopulation=float(D(total) - sum(pop)), annualEquivalentCostTRY=float(annual),
        decimalAnnualEquivalentCostTRY=str(annual), annualMaterialCostTRY=float(material),
        decimalAnnualMaterialCostTRY=str(material), decimalAnnualFixedResourceCostTRY=str(annual-material),
        minimumAreaSlackM2=minimum_area, minimumPlotClearanceMeters=clearance,
        minimumDoctorContactSlack=float(minimum_doctor_slack), minimumBedDaySlack=float(minimum_bed_slack),
        conditionalOverlap=dict(province=overlap(list(range(len(pop))), total),
            districts=[dict(id=d['id'], name=d['name'], **overlap(
                [i for i, x in enumerate(demands) if x['districtId'] == d['id']], d['population'])) for d in districts],
            sameIndividualsObserved=False, numericalClippingResidents=float(correction),
            scope='Conditional intersection bounds per origin: lower=max(0,sum(served)-(K-1)*population), upper=min(served). These are not observed patient identities.'))


def _file_bytes(path, parent=None):
    path = Path(path)
    resolved = path.resolve(strict=True)
    check(resolved.is_file() and (parent is None or resolved.parent == Path(parent).resolve(strict=True)),
          'Input path escapes its declared directory')
    return resolved, resolved.read_bytes()


def _npz_minutes(blob, expected_shape=None):
    with np.load(io.BytesIO(blob), allow_pickle=False) as archive:
        check(set(archive.files) == {'minutes'}, 'Unexpected NPZ members')
        matrix = archive['minutes'].copy()
    check(matrix.ndim == 2 and matrix.dtype.kind == 'f', 'Floating point matrix required')
    if expected_shape is not None: check(matrix.shape == expected_shape, 'Matrix shape differs')
    check(not np.any(np.isnan(matrix)) and not np.any(matrix < 0), 'Invalid matrix values')
    return matrix


def _verify_archived_subset(root, manifest, matrices, data):
    ref = manifest['archived0805']
    archive = Path(root) / ref['archive']
    with ZipFile(archive) as z:
        names = z.namelist()
        check(len(names) == len(set(names)), 'Duplicate archive members')
        for key in ('matrixMember', 'reportMember'): check(names.count(ref[key]) == 1, 'Missing archive member')
        matrix_bytes = z.read(ref['matrixMember']); report_bytes = z.read(ref['reportMember'])
    check(sha256(matrix_bytes) == ref['matrixSHA256'] and sha256(report_bytes) == ref['reportSHA256'],
          'Archived 08:05 evidence hash differs')
    report = load_json(report_bytes)
    check(report['transitPackageId'] == manifest['parentTransitPackageId']
          and report['arraysSHA256'] == ref['matrixSHA256'], 'Archived package/array identity differs')
    source_names = [name for name in ROUTING_SOURCE_FILES if name.startswith('data/processed/')]
    expected_hashes = {name.removeprefix('data/processed/'): manifest['sourceSHA256'][name] for name in source_names}
    same_hashes(report['sourceSHA256'], expected_hashes, expected_hashes, 'archived routing sources')
    check(digest(report['profiles']) == digest({'0800': {'day': 'weekday', 'startSeconds': 28800},
                                               '0805': {'day': 'weekday', 'startSeconds': 29100}}),
          'Archived departure clocks differ')
    with np.load(io.BytesIO(matrix_bytes), allow_pickle=False) as archive:
        check(set(archive.files) == {'originIndices', 'targetCandidateIndices', 'minutes0800', 'minutes0805'},
              'Unexpected archived arrays')
        origins = archive['originIndices']; targets = archive['targetCandidateIndices']
        check(origins.dtype.kind in 'iu' and targets.dtype.kind in 'iu' and origins.ndim == targets.ndim == 1,
              'Archived index dtype differs')
        check(np.array_equal(origins, np.arange(len(data['demands']))) and len(targets) > 0
              and len(targets) == len(set(targets.tolist())) and np.all(targets >= 0)
              and np.all(targets < len(data['candidates'])), 'Archived candidate/origin identities differ')
        check(digest(report['origins']) == digest([dict(index=int(i), id=data['demands'][int(i)]['id'],
                    population=data['demands'][int(i)]['population'],
                    districtId=data['demands'][int(i)]['districtId']) for i in origins])
              and digest(report['targets']) == digest([dict(index=int(i), id=data['candidates'][int(i)]['id']) for i in targets]),
              'Archived ordered report identities differ')
        for clock, name in (('0800', 'weekday-0800'), ('0805', 'weekday-0805')):
            check(np.array_equal(archive['minutes' + clock], matrices[name][:, targets]), 'Archived time slice changed')
        row = next(row for row in manifest['matrices'] if row['profileId'] == 'weekday-0805')
        check(row['audit']['baselineCheck']['comparedColumns'] == len(targets), '08:05 subset column count differs')


def read_window_inputs(manifest_path, root=ROOT):
    """Read full matrix inputs and establish immutable byte/code/package bindings.

    This reader performs no routing, native optimization, publication or writes.
    ``unchanged_window_inputs`` must be called again after any dependent work.
    """
    root = Path(root).resolve(strict=True); package = check_package(root)
    for name, value in LOADED_AUDITOR_HASHES.items():
        check(sha256((ROOT / name).read_bytes().replace(b'\r\n', b'\n')) == value,
              'Loaded audit code changed; restart before auditing')
    path = Path(manifest_path)
    if not path.is_absolute(): path = root / path
    path, blob = _file_bytes(path); folder = path.parent; manifest = load_json(blob)
    # Parse identity fields before following any declared file references.
    check(type(manifest) is dict, 'Manifest object required')
    keys(manifest.get('sourceSHA256'), ROUTING_SOURCE_FILES, 'routing source paths')
    keys(manifest.get('routingCodeLF_SHA256'), ROUTING_CODE_FILES, 'routing code paths')
    keys(manifest.get('frozenModelCodeLF_SHA256'), FROZEN_MODEL_FILES, 'frozen code paths')
    raw_bindings = {str(path): sha256(blob)}; source_blobs = {}
    for name in ROUTING_SOURCE_FILES:
        p = root / name; resolved, content = _file_bytes(p, p.parent)
        check(resolved == p, 'Redirected repository source')
        check(sha256(content) == hash_value(manifest['sourceSHA256'][name]), 'Stale routing source: ' + name)
        raw_bindings[str(resolved)] = sha256(content)
        if name.startswith('data/processed/') and (name.endswith('.json') or name.startswith('data/processed/transit-')):
            source_blobs[Path(name).name] = content
    codes = code_hashes(root); code_bindings = dict(codes)
    for name, expected in LOADED_AUDITOR_HASHES.items():
        check(codes[name] == expected, 'Source tree audit code differs from loaded verifier')
    for section, names in (('routingCodeLF_SHA256', ROUTING_CODE_FILES), ('frozenModelCodeLF_SHA256', FROZEN_MODEL_FILES)):
        actual = {name: sha256((root / name).read_bytes().replace(b'\r\n', b'\n')) for name in names}
        same_hashes(manifest[section], actual, names, section); code_bindings.update(actual)
    data = load_json(source_blobs['dataset.json']); health = load_json(source_blobs['health-planning.json'])
    source = load_json(source_blobs['joint-plan.json']); published = load_json(source_blobs['example-transit-result.json'])
    check(type(manifest.get('indices')) is dict and manifest['indices'].get('file') == 'indices.json', 'Unexpected indices file')
    index_path, index_bytes = _file_bytes(folder / 'indices.json', folder)
    check(sha256(index_bytes) == hash_value(manifest['indices']['sha256']), 'Index document changed')
    raw_bindings[str(index_path)] = sha256(index_bytes); indices_document = load_json(index_bytes)
    matrices = {}; files = set()
    for row in sequence(manifest.get('matrices'), 'matrix records'):
        check(type(row) is dict, 'Matrix descriptor required')
        name = identity(row.get('profileId'), 'matrix profile'); filename = identity(row.get('file'), 'matrix filename')
        check(Path(filename).name == filename and '/' not in filename and '\\' not in filename
              and ':' not in filename and filename.endswith('.npz') and filename.casefold() not in files,
              'Unsafe/duplicate matrix path')
        check(name not in matrices, 'Duplicate matrix profile'); files.add(filename.casefold())
        matrix_path, matrix_bytes = _file_bytes(folder / filename, folder)
        check(sha256(matrix_bytes) == hash_value(row.get('sha256')), 'Matrix file changed: ' + name)
        raw_bindings[str(matrix_path)] = sha256(matrix_bytes)
        matrices[name] = _npz_minutes(matrix_bytes, (len(data['demands']), len(data['candidates'])))
    baselines = {}
    for name in BASE_PROFILES:
        matrix = _npz_minutes(source_blobs[f'transit-{name}-matrix.npz'])
        check(matrix.shape[0] == len(data['demands']) and matrix.shape[1] >= len(data['candidates']), 'Original baseline dimensions differ')
        baselines[name] = matrix[:, :len(data['candidates'])]
    validate_manifest(manifest, data, matrices, indices_document, baselines)
    _verify_archived_subset(root, manifest, matrices, data)
    inputs = dict(data=data, health=health, matrices=matrices, baseline_matrices=baselines,
        published_reference=published, source_cost_certificate=source,
        current_source_hashes={name: sha256(source_blobs[name]) for name in SOURCE_FILES},
        package_id=package, manifest=manifest, manifest_sha256=sha256(blob), current_code_hashes=codes,
        indices_document=indices_document,
        bindings=dict(root=str(root), files=raw_bindings, codeLF_SHA256=code_bindings, package_id=package))
    inputs['bindings']['parsedSHA256'] = {name: digest(inputs[name]) for name in
        ('data', 'health', 'published_reference', 'source_cost_certificate', 'manifest', 'indices_document')}
    inputs['bindings']['matrixDataSHA256'] = {name: sha256(matrix.tobytes(order='C')) for name, matrix in matrices.items()}
    inputs['bindings']['baselineDataSHA256'] = {name: sha256(matrix.tobytes(order='C')) for name, matrix in baselines.items()}
    for matrix in (*matrices.values(), *baselines.values()): matrix.setflags(write=False)
    unchanged_window_inputs(inputs, root)
    return inputs


def unchanged_window_inputs(inputs, root=ROOT):
    root = Path(root).resolve(strict=True); bindings = inputs['bindings']
    check(str(root) == bindings['root'], 'Input root changed')
    check(check_package(root) == bindings['package_id'] == inputs['package_id'], 'Source package changed')
    for path, expected in bindings['files'].items():
        check(sha256(Path(path).read_bytes()) == expected, 'Input changed: ' + path)
    for name, expected in bindings['codeLF_SHA256'].items():
        check(sha256((root / name).read_bytes().replace(b'\r\n', b'\n')) == expected, 'Code changed: ' + name)
    for name, expected in bindings['parsedSHA256'].items():
        check(digest(inputs[name]) == expected, 'Parsed source changed in memory: ' + name)
    for field, bound in (('matrices', 'matrixDataSHA256'), ('baseline_matrices', 'baselineDataSHA256')):
        check(set(inputs[field]) == set(bindings[bound]), 'In-memory matrix profile set changed')
        for name, expected in bindings[bound].items():
            check(sha256(inputs[field][name].tobytes(order='C')) == expected, 'In-memory matrix changed: ' + name)
    return True


def reconstruct_saved_vector(certificate, inputs):
    """Independent wire-order reconstruction, not a model-builder call.

    Eligible (site, template) binaries come first in row-major order, followed
    by one physician integer per candidate and row-major legal flows for every
    ordered profile. This matches the documented common-resource wire format.
    """
    data, health, scenario = inputs['data'], inputs['health'], certificate['scenario']
    pool = certificate['generation']['candidateIndices']; local = {g:j for j,g in enumerate(pool)}
    templates = health['templates']; template_indices = {t['id']:i for i,t in enumerate(templates)}
    areas = np.array([t['grossAreaM2'] for t in templates], dtype=float)
    available = np.array([math.pi * data['candidates'][g]['footprintRadiusMeters'] ** 2
                          * health['design']['maxFloors'] for g in pool])
    eligible = areas[None,:] + health['design']['minimumDoctorsPerSite'] * health['design']['areaPerDoctorM2'] <= available[:,None] + .001
    site_indices, type_indices = np.where(eligible); nx = len(site_indices); nf = nx + len(pool)
    prefix = np.zeros(nf); positions = {(int(j), int(t)):k for k,(j,t) in enumerate(zip(site_indices,type_indices))}
    for site in certificate['plan']['selected']:
        j = local[site['candidateIndex']]; key = j, template_indices[site['templateId']]
        check(key in positions, 'Selected module absent from wire eligibility')
        prefix[positions[key]] = 1.; prefix[nx+j] = site['doctors']
    pieces = [prefix]; edge_count = 0
    for profile in certificate['plan']['profiles']:
        matrix = inputs['matrices'][profile['profile']][:,pool]
        oi, sj = np.where(np.isfinite(matrix) & (matrix <= scenario['threshold']))
        indices = {(int(i),pool[int(j)]):k for k,(i,j) in enumerate(zip(oi,sj))}
        flow = np.zeros(len(oi))
        for allocation in profile['allocations']:
            key = allocation['demandIndex'], allocation['candidateIndex']
            check(key in indices, 'Allocation absent from wire edges')
            flow[indices[key]] = float(allocation['population']) / 1000
        pieces.append(flow); edge_count += len(flow)
    return np.concatenate(pieces), dict(binaryTemplates=nx, integerPhysicians=len(pool),
        sharedPrefix=nf, flowVariables=edge_count, profiles=len(certificate['plan']['profiles']))


def validate_explicit_candidate_pool(document, inputs, seed_indices, expected_pool=None):
    """Validate a source-bound search expansion; its method text proves no bound."""
    keys(document, ('format','candidateIndices','method','sourceSHA256','profileManifestSHA256'),
         'explicit candidate pool')
    check(type(document['format']) is int and document['format'] == 1, 'Explicit pool format must be integer 1')
    identity(document['method'], 'candidate pool method')
    same_hashes(document['sourceSHA256'], inputs['current_source_hashes'], SOURCE_FILES, 'candidate pool sources')
    check(hash_value(document['profileManifestSHA256']) == inputs['manifest_sha256'], 'Candidate pool manifest differs')
    pool = sequence(document['candidateIndices'], 'explicit candidate indices')
    for i in pool:
        integer(i, 'explicit candidate index')
        check(i < len(inputs['data']['candidates']), 'Explicit candidate index out of range')
    check(bool(pool) and pool == sorted(set(pool)), 'Explicit pool must be nonempty, sorted and unique')
    check(set(seed_indices) <= set(pool), 'Explicit pool omits a source seed candidate')
    if expected_pool is not None:
        check(digest(pool) == digest(expected_pool), 'Explicit candidate pool and generation differ')
    return pool.copy()


def verify_adaptive_seed_preparation(certificate, inputs, folder, report):
    """Validate the complete seed, not the optimality of partial cost stages."""
    claimed = report.get('adaptiveSeedPreparationSHA256')
    if claimed is None: return None
    hash_value(claimed)
    directory = Path(folder) / 'seed-preparation'
    check(directory.resolve(strict=True) == directory, 'Redirected adaptive seed directory')
    path, blob = _file_bytes(directory / 'seed-preparation.json', directory)
    check(sha256(blob) == claimed, 'Adaptive seed report hash differs')
    seed = load_json(blob); bindings = {str(path): blob}
    check(type(seed.get('format')) is int and seed['format'] == 1
          and seed.get('artifactType') == 'window-seed-preparation', 'Adaptive seed report format differs')
    check(seed.get('status') == 'complete_window_seed_prepared' and seed.get('feasible') is True,
          'Adaptive report has no complete seed')
    for name, value in dict(annualDemandCountedOnce=True, outerHardTimeoutRequired=True,
            independentFinalAuditRequired=True, globalInfeasibilityProven=False,
            globalOptimalityProven=False, profileSubsetBoundsTransferred=False).items():
        check(seed.get(name) is value, 'Unsupported adaptive seed claim: '+name)
    check(hash_value(seed['helperCodeSHA256']) == inputs['current_code_hashes']['backend/window_seed.py'],
          'Adaptive helper identity differs')
    hash_value(seed['modelSignature'])  # Historical internal fingerprint, not independently certified here.
    expected_bindings = dict(sourceSHA256=inputs['current_source_hashes'],modelCodeSHA256=inputs['current_code_hashes'],
        profileManifestSHA256=inputs['manifest_sha256'],resourceSeedSHA256=report['resourceSeedSHA256'],
        candidatePoolSHA256=report.get('candidatePoolSHA256'))
    keys(seed['callerSourceBindings'], expected_bindings, 'adaptive caller bindings')
    check(digest(seed['callerSourceBindings']) == digest(expected_bindings), 'Adaptive caller source/code bindings differ')
    names = [p['id'] for p in expected_profiles()]; pool = certificate['generation']['candidateIndices']
    check(seed['fullProfileIds'] == names and digest(seed['candidateIndices']) == digest(pool), 'Adaptive final scope differs')
    check(D(number(seed['hardAnnualBudgetTRY'],'seed hard budget')) == D(certificate['budget']['limitTRY']),
          'Adaptive hard budget differs')
    near(seed['referenceAnnualCostTRY'],certificate['budget']['referenceAnnualCostTRY'],'.001','adaptive reference cost')
    result = report['result']
    check(result.get('nativeRunStarted') is True and result.get('costStagePerformed') is True
          and report['optimizedProfiles'] == names, 'Adaptive final certificate requires an actual full-window cost run')
    warm = result.get('warmStart', {})
    check(warm.get('solverAcceptedFeasibleStart') is True and warm.get('completeStartSupplied') is True,
          'Complete adaptive seed was not accepted as the full-window warm start')
    stages = sequence(seed['stages'],'adaptive stages'); check(1 <= len(stages) <= 11,'Invalid adaptive stage count')
    full_wire, wire_layout = reconstruct_saved_vector(certificate,inputs)
    artifact_names = [f'stage-{i:02d}-{suffix}' for i in range(1,len(stages)+1)
                      for suffix in ('cost.json','cost-vectors.npz','completion.json','completion-vectors.npz')]
    keys(seed['artifacts'],artifact_names,'adaptive staged artifacts')
    check({p.name for p in directory.iterdir()} == set(artifact_names)|{'seed-preparation.json'},
          'Unlisted or missing adaptive artifacts')
    blobs = {}
    for name in artifact_names:
        artifact, content = _file_bytes(directory / name,directory)
        check(sha256(content) == hash_value(seed['artifacts'][name]), 'Adaptive stage file hash differs: '+name)
        bindings[str(artifact)] = content; blobs[name] = content
    active = names[:12]
    for index, stage in enumerate(stages,1):
        check(type(stage['stage']) is int and stage['stage'] == index
              and stage['optimizedProfileIds'] == active and digest(stage['candidateIndices']) == digest(pool),
              'Adaptive stage identities differ')
        check(stage['boundScope'] == 'Only this stage candidate pool and named profile subset; never copied into the final full-window cost bound.',
              'Adaptive partial bound scope differs')
        prefix = f'stage-{index:02d}'
        check(stage['costResult'].get('feasible') is True, 'Adaptive stage has no validated subset plan')
        check([p['profile'] for p in stage['costResult']['profiles']] == active, 'Adaptive cost profile labels differ')
        stage_variables = wire_layout['sharedPrefix'] + sum(int(np.count_nonzero(
            np.isfinite(inputs['matrices'][name][:,pool]) & (inputs['matrices'][name][:,pool] <= certificate['scenario']['threshold'])))
            for name in active)
        check(integer(stage['dimensions']['profiles'],'adaptive stage profile count') == len(active)
              and integer(stage['dimensions']['variables'],'adaptive stage variable count') == stage_variables,
              'Adaptive partial vector dimensions differ')
        recorded = load_json(blobs[prefix+'-cost.json'])
        check(digest(recorded) == digest({k:v for k,v in stage.items() if k not in ('fullWindowCompletion','nextProfileIds')}),
              'Adaptive cost stage record differs')
        diagnostic = load_json(blobs[prefix+'-completion.json'])
        check(digest(diagnostic) == digest(stage['fullWindowCompletion']), 'Adaptive completion record differs')
        rows = sequence(diagnostic['profiles'],'adaptive completion profiles')
        check(len(rows) == 44 and [r['profile'] for r in rows] == names
              and all(type(r['accepted']) is bool for r in rows), 'Adaptive completion profile identities differ')
        failed = [r['profile'] for r in rows if not r['accepted']]
        check(diagnostic['failedProfileIds'] == failed and diagnostic['modelInfeasibilityProven'] is False
              and diagnostic['resourcesUnchanged'] is True and diagnostic['annualDemandCountedOnce'] is True
              and diagnostic['oldProfilesRelabelled'] is False and diagnostic['sameNamedFlowsReused'] == active,
              'Adaptive completion scope differs')
        final = index == len(stages)
        check(diagnostic['feasible'] is (True if final else None), 'Partial completion promoted or final completion absent')
        if final:
            check(not failed and 'nextProfileIds' not in stage
                  and diagnostic['status'] == 'complete_44_seed_primal_checked', 'Final adaptive completion not complete')
        else:
            check(bool(failed), 'Intermediate adaptive stage lacks a failed profile')
            blocks = {names.index(p)//4 for p in failed}
            expanded = [p for i,p in enumerate(names) if p in active or i//4 in blocks]
            check(expanded != active and stage['nextProfileIds'] == expanded, 'Failed offset blocks were not activated exactly')
            active = expanded
        for suffix in ('cost-vectors.npz','completion-vectors.npz'):
            with np.load(io.BytesIO(blobs[prefix+'-'+suffix]),allow_pickle=False) as arrays:
                check(len(arrays.files) == len(set(arrays.files)), 'Duplicate adaptive NPZ members')
                if suffix == 'completion-vectors.npz':
                    check(arrays.files == ['complete44Vector' if final else 'unvalidatedPartial44Vector'],
                          'Adaptive partial/final vector label differs')
                else:
                    check(set(arrays.files) <= {'finalOriginalVector','suppliedOriginalVector','returnedRawVector'}
                          and 'finalOriginalVector' in arrays.files, 'Adaptive cost vector members differ')
                for name in arrays.files:
                    array = arrays[name]
                    length = len(full_wire) if suffix == 'completion-vectors.npz' else stage_variables
                    check(array.dtype.kind == 'f' and array.shape == (length,) and np.all(np.isfinite(array)), 'Invalid adaptive vector array')
    complete = seed['completeSeedPlan']; check(type(complete) is dict,'Complete adaptive plan required')
    check(complete.get('minimumAnnualCostLowerBoundTRY') is None and complete.get('costGap') is None
          and complete.get('provenOptimal') is False, 'Subset cost bound or optimality claim leaked into complete seed')
    seed_certificate = deepcopy(certificate)
    seed_certificate['generation'].update(optimizedProfiles=active,runReportSHA256=claimed,
        vectorSHA256=seed['artifacts'][f'stage-{len(stages):02d}-completion-vectors.npz'])
    seed_certificate['plan'] = {key:complete[key] for key in certificate['plan']}
    audited = validate_window_plan(seed_certificate,**{k:v for k,v in inputs.items() if k!='bindings'})
    expected, _ = reconstruct_saved_vector(seed_certificate,inputs)
    with np.load(io.BytesIO(blobs[f'stage-{len(stages):02d}-completion-vectors.npz']),allow_pickle=False) as arrays:
        check(np.array_equal(arrays['complete44Vector'],expected), 'Complete adaptive vector and independent JSON reconstruction differ')
    return dict(vector=expected,bindings=bindings,summary=dict(reportSHA256=claimed,stageCount=len(stages),
        completeSeedIndependentlyValidated=True,profileCount=44,hospitalCount=audited['hospitalCount'],
        decimalAnnualEquivalentCostTRY=audited['decimalAnnualEquivalentCostTRY'],
        withinHardBudget=audited['withinHardBudget'],partialStageOptimalityIndependentlyCertified=False,
        partialStageBoundsTransferred=False,scope='Complete seed resources, all 44 flows and one annual bill independently checked. Stage hashes bind the historical subset search; its optimality and native bounds are not independently certified.'))


def verify_run_artifacts(certificate, inputs, folder):
    """Bind adjacent result/vector/seed artifacts without trusting solver claims."""
    folder = Path(folder).resolve(strict=True); blobs = {}; paths = {}
    for name in ('run-result.json', 'vectors.npz', 'resource-seed.json', 'solver.log'):
        paths[name], blobs[name] = _file_bytes(folder / name, folder)
    generation = certificate['generation']; report = load_json(blobs['run-result.json'])
    check(sha256(blobs['run-result.json']) == generation['runReportSHA256'], 'Generation report hash differs')
    check(sha256(blobs['vectors.npz']) == generation['vectorSHA256'] == report['vectorSHA256'], 'Generation vector hash differs')
    check(sha256(blobs['resource-seed.json']) == hash_value(report['resourceSeedSHA256']), 'Resource seed hash differs')
    check(sha256(blobs['solver.log']) == hash_value(report['solverLogSHA256']), 'Native log hash differs')
    check(type(report['format']) is int and report['format'] == 1
          and report['artifactType'] == 'departure-window-cost-run', 'Run report type differs')
    check(report['transitPackageId'] == inputs['package_id']
          and report['profileManifestSHA256'] == inputs['manifest_sha256'], 'Run source package differs')
    same_hashes(report['sourceSHA256'], inputs['current_source_hashes'], SOURCE_FILES, 'run source hashes')
    same_hashes(report['modelCodeSHA256'], inputs['current_code_hashes'], MODEL_FILES, 'run model code')
    for field in ('candidateIndices', 'optimizedProfiles', 'validatedProfiles'):
        check(digest(report[field]) == digest(generation[field]), 'Run/certificate ' + field + ' differ')
    check(report['fullCandidateCount'] == len(inputs['data']['candidates']), 'Full candidate count differs')
    check(report['boundScope'] == 'Only this candidate pool and these 44 named matrices; no global or minimum-count proof',
          'Unrecognized bound scope')
    result = report['result']; plan = certificate['plan']
    check(result.get('feasible') is True and result.get('incumbentValidated') is True and result.get('status') == 'feasible',
          'Run lacks an explicitly validated incumbent')
    check(digest({key:result[key] for key in plan}) == digest(plan), 'Run result and complete certificate differ')
    check(result['hardBudgetConstraint'] is True and D(result['hardAnnualBudgetTRY']) == D(certificate['budget']['limitTRY']),
          'Run hard budget claim differs')
    check(result['annualDemandCountedOnce'] is True and result['minimumHospitalCountProven'] is False,
          'Run resource/count scope differs')
    check(result['boundScope'] == 'supplied_candidate_pool_and_exact_named_profile_set'
          and result['boundCandidateIndices'] == generation['candidateIndices'], 'Run bound candidate scope differs')
    check(result['profileIds'] == generation['optimizedProfiles']
          and integer(result['profileCount'], 'run profile count') == len(generation['optimizedProfiles']),
          'Run bound profile scope differs')
    check(result.get('nativeBoundIndependentlyCertified',False) is False, 'Native bound was not independently certified')
    lower, gap = result.get('minimumAnnualCostLowerBoundTRY'), result.get('costGap')
    if lower is None: check(gap is None, 'Gap without a lower bound')
    else:
        check(type(lower) in (int,float) and math.isfinite(lower), 'Invalid native lower bound')
        annual = number(plan['annualEquivalentCostTRY'], 'run annual cost', positive=True)
        tolerance = max(.01, abs(annual)*1e-9)
        near(result['costNumericalToleranceTRY'], tolerance, '.0000001', 'native bound tolerance')
        check(lower <= annual+tolerance, 'Native cost bound contradicts valid primal')
        near(gap, max(0.,(annual-lower)/annual), '.000000001', 'scoped native cost gap')
    seed = load_json(blobs['resource-seed.json'])
    source_audit = cost.validate_joint_plan(seed, inputs['data'], inputs['health'], inputs['baseline_matrices'],
        inputs['published_reference'], {name:inputs['current_source_hashes'][name] for name in cost.SOURCE_FILES},
        inputs['package_id'])
    check(report['seedResourceAudit'] == 'frozen_four_profile_independent_auditor', 'Seed scope differs')
    pool = generation['candidateIndices']
    check(report['candidatePool'] in ('seed','all','explicit'), 'Unknown candidate pool')
    seed_indices = sorted(site['candidateIndex'] for site in seed['plan']['selected'])
    candidate_pool_hash = None
    if report['candidatePool'] == 'explicit':
        name = 'candidate-pool.json'; paths[name], blobs[name] = _file_bytes(folder / name, folder)
        candidate_pool_hash = hash_value(report.get('candidatePoolSHA256'))
        check(sha256(blobs[name]) == candidate_pool_hash, 'Explicit candidate pool file hash differs')
        expected_pool = validate_explicit_candidate_pool(load_json(blobs[name]), inputs, seed_indices, pool)
    else:
        check(report.get('candidatePoolSHA256') is None, 'Non-explicit pool must not claim a separate pool file')
        expected_pool = seed_indices if report['candidatePool'] == 'seed' else list(range(len(inputs['data']['candidates'])))
    check(pool == expected_pool, 'Declared candidate pool does not match its source')
    adaptive = verify_adaptive_seed_preparation(certificate,inputs,folder,report)
    expected, layout = reconstruct_saved_vector(certificate, inputs)
    with np.load(io.BytesIO(blobs['vectors.npz']), allow_pickle=False) as arrays:
        allowed = {'finalOriginalVector','costStageOriginalVector','suppliedOriginalVector','returnedRawVector',
                   'costStageNativeValidatedVector'}
        check({'finalOriginalVector','costStageOriginalVector'} <= set(arrays.files)
              and set(arrays.files) <= allowed, 'Unexpected/missing vector members')
        for name in arrays.files:
            vector = arrays[name]
            check(vector.dtype.kind == 'f' and vector.shape == expected.shape and np.all(np.isfinite(vector)), 'Invalid vector array')
        check(np.array_equal(arrays['finalOriginalVector'], expected), 'Raw final vector and JSON differ')
        if adaptive is not None:
            check('suppliedOriginalVector' in arrays.files and np.array_equal(arrays['suppliedOriginalVector'],adaptive['vector']),
                  'Main warm-start vector differs from independently validated complete adaptive seed')
        if 'costStageOriginalVector' in arrays.files:
            check(np.array_equal(arrays['costStageOriginalVector'][:layout['sharedPrefix']],expected[:layout['sharedPrefix']]),
                  'Travel refinement changed resource prefix')
        if 'costStageNativeValidatedVector' in arrays.files:
            native, serialized = arrays['costStageNativeValidatedVector'], arrays['costStageOriginalVector']
            check(np.array_equal(native[:layout['sharedPrefix']],serialized[:layout['sharedPrefix']]),
                  'JSON roundtrip changed resource prefix')
            check(np.all(native[layout['sharedPrefix']:] >= 0), 'Negative validated cost-stage flow')
            rounding = 2 * np.spacing(np.maximum(np.abs(native),np.abs(serialized)))
            check(np.all(np.abs(native-serialized) <= rounding), 'Cost-stage JSON roundtrip exceeds two binary64 ULPs')
    dimensions = report['dimensions']
    for key in ('binaryTemplates','integerPhysicians','flowVariables','profiles'):
        check(integer(dimensions[key], 'run dimension') == layout[key], 'Run layout dimensions differ')
    check(integer(dimensions['variables'], 'run variable count') == len(expected), 'Run vector length differs')
    for name, content in blobs.items(): check(paths[name].read_bytes() == content, 'Run artifact changed during audit')
    if adaptive is not None:
        for path, content in adaptive['bindings'].items():
            check(Path(path).read_bytes() == content,'Adaptive seed artifact changed during audit')
    return dict(runReportSHA256=sha256(blobs['run-result.json']), vectorSHA256=sha256(blobs['vectors.npz']),
        resourceSeedSHA256=sha256(blobs['resource-seed.json']), finalVectorExactlyMatchesJSON=True,
        finalVectorLength=len(expected), resourceSeedFourProfileValidated=True,
        resourceSeedHospitalCount=source_audit['hospitalCount'], nativeBoundIndependentlyCertified=False,
        candidatePool=report['candidatePool'], candidatePoolSHA256=candidate_pool_hash,
        adaptiveSeedAudit=None if adaptive is None else adaptive['summary'],
        scope='Final JSON and raw vector agree exactly. Source seed is validated for its original four profiles only; its older flows are not a window fallback. Native cost bounds remain limited to the reported candidate pool and named model profiles.')


def audit_saved_window_plan(certificate_path, manifest_path, root=ROOT, *, verify_artifacts=True):
    root = Path(root).resolve(strict=True); inputs = read_window_inputs(manifest_path, root)
    path = Path(certificate_path)
    if not path.is_absolute(): path = root / path
    path, blob = _file_bytes(path); certificate = load_json(blob)
    result = validate_window_plan(certificate, **{k: v for k, v in inputs.items() if k != 'bindings'})
    check(type(verify_artifacts) is bool, 'Artifact verification flag must be boolean')
    if verify_artifacts: result['runArtifactAudit'] = verify_run_artifacts(certificate, inputs, path.parent)
    else: result['runArtifactAudit'] = dict(verified=False, scope='Complete plan only; generation references were not replayed or verified.')
    check(path.read_bytes() == blob, 'Certificate changed during audit')
    unchanged_window_inputs(inputs, root)
    result['certificateSHA256'] = sha256(blob)
    result['auditCodeSHA256'] = inputs['current_code_hashes']['scripts/audit_window_plan.py']
    result['profileManifestSHA256'] = inputs['manifest_sha256']
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--certificate', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--summary', help='Compare an existing saved summary exactly; never overwrite it')
    parser.add_argument('--quiet', action='store_true', help='Print only a compact validation result')
    args = parser.parse_args()
    summary = audit_saved_window_plan(args.certificate, args.manifest)
    if args.summary:
        _, saved = _file_bytes(args.summary)
        check(digest(load_json(saved)) == digest(summary), 'Saved window summary differs from independent computation')
    shown = {key:summary[key] for key in ('status','profileCount','hospitalCount','beds','doctors',
                                        'annualEquivalentCostTRY','budgetSlackTRY')} if args.quiet else summary
    print(json.dumps(shown, ensure_ascii=False, allow_nan=False, indent=2))
