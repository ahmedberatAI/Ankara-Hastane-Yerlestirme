"""Describe two geometric walking connectors in the audited travel plan; no solver.

Default verifies a saved summary without writing. --write atomically refreshes
only data/processed/access-connector-summary.json after all identity checks.
"""
import argparse
import json
import math
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import audit_joint_travel as travel
from scripts.transit_provenance import check_package

OUTPUT = 'access-connector-summary.json'
SELF = 'scripts/audit_access_connectors.py'
SEMANTIC_FILES = ('scripts/build_timetable.py', 'backend/timetable.py')
SPEED = 1.25
check, digest, sha256, load_json = travel.check, travel.digest, travel.sha256, travel.cost.load_json
LOADED_CODE_SHA256 = sha256(Path(__file__).read_bytes().replace(b'\r\n', b'\n'))
DEFINITIONS = {
    'weight': 'Positive assigned population-equivalent per allocation, independently in each profile; not unique people or annual trip counts.',
    'meanDenominator': 'Sum of assigned population-equivalents in this profile: 95% of full province population, including unlocated population in the target denominator.',
    'ratioNumerator': 'Sum of assigned population-equivalent times the two connector minutes.',
    'ratioDenominator': 'Sum of assigned population-equivalent times full modeled travel minutes; ratio of sums, not mean of individual ratios.',
    'scope': 'Only demand.snapMeters and selected candidate.accessMeters, divided by 1.25 m/s and 60 s/min. These geometric connectors are not independently verified walkable paths. Stop snapping, transfers, network walking, waits and vehicle time are not attributed here. Their remainder is not validated travel, and subtracting the connectors is not a counterfactual reroute or new feasible plan.'}


def number(value, label, positive=False):
    return float(travel.cost.number(value, label, positive=positive))


def compute(data, certificate):
    """Arithmetic on an already independently validated complete travel plan."""
    meta, plan = data['metadata'], certificate['plan']
    demands, candidates = data['demands'], data['candidates']
    province = number(meta['provincePopulation'], 'province population', True)
    located = math.fsum(number(d['population'], 'origin population') for d in demands)
    check(abs(located-meta['matchedPopulation']) <= 1e-6 and
          abs(province-located-meta['unlocatedPopulation']) <= 1e-6, 'Located/unlocated population mismatch')
    check([p['profile'] for p in plan['profiles']] == list(travel.PROFILES), 'Four ordered profiles required')
    selected = {s['candidateIndex']: s['id'] for s in plan['selected']}
    check(len(selected) == len(plan['selected']) == plan['hospitalCount'], 'Selected count mismatch')
    profiles = []
    for profile in plan['profiles']:
        weights, origin_terms, site_terms, total_terms = [], [], [], []
        seen = set()
        for allocation in profile['allocations']:
            i, j = allocation['demandIndex'], allocation['candidateIndex']
            check(type(i) is int and 0 <= i < len(demands) and type(j) is int and 0 <= j < len(candidates), 'Invalid allocation index')
            check(j in selected and selected[j] == candidates[j]['id'] and (i, j) not in seen, 'Closed/duplicate/mismatched allocation')
            seen.add((i, j))
            weight = number(allocation['population'], 'assigned population', True)
            origin = number(demands[i]['snapMeters'], 'origin connector') / (SPEED*60)
            site = number(candidates[j]['accessMeters'], 'hospital connector') / (SPEED*60)
            total = number(allocation['minutes'], 'full travel minutes')
            check(total+1e-4 >= origin+site, 'Connectors exceed full modeled time')
            weights.append(weight); origin_terms.append(weight*origin)
            site_terms.append(weight*site); total_terms.append(weight*total)
        served, total_pm = math.fsum(weights), math.fsum(total_terms)
        check(served > 0 and total_pm > 0 and abs(served-province*.95) <= .001, 'Invalid served/full travel denominator')
        check(abs(served-profile['coveredPopulation']) <= .001 and
              abs(total_pm/served-profile['meanMinutes']) <= 1e-7, 'Published travel totals mismatch')
        origin_pm, site_pm = math.fsum(origin_terms), math.fsum(site_terms)
        profiles.append(dict(profile=profile['profile'], servedEquivalent=served,
            meanOriginMinutes=origin_pm/served, meanHospitalMinutes=site_pm/served,
            meanEndpointMinutes=(origin_pm+site_pm)/served,
            shareOfPersonMinutesPercent=(origin_pm+site_pm)/total_pm*100,
            totalMeanMinutes=total_pm/served))
    return dict(format=1, status='descriptive_explicit_connectors',
        transitPackageId=certificate['transitPackageId'], planningVersion=certificate['planningVersion'],
        hospitalCount=plan['hospitalCount'], walkingSpeedMetersPerSecond=SPEED,
        population=dict(provincePopulation=province, locatedPopulation=located,
                        unlocatedPopulation=province-located, targetServedPopulationEquivalentPerProfile=province*.95),
        definitions=dict(DEFINITIONS), profiles=profiles)


def code_hashes(root):
    return {name: sha256((root/name).read_bytes().replace(b'\r\n', b'\n')) for name in (SELF, *SEMANTIC_FILES)}


def paths(root):
    root = Path(root).resolve(strict=True)
    directory = root/'data/processed'
    check(directory.resolve(strict=True) == directory, 'Redirected processed directory')
    output = directory/OUTPUT
    check(output.resolve(strict=False) == output, 'Redirected output path')
    return root, directory, output


def current_report(root=ROOT):
    root, directory, _ = paths(root)
    package = check_package(root); codes = code_hashes(root)
    check(codes[SELF] == LOADED_CODE_SHA256, 'Loaded connector auditor differs from current code')
    audited = travel.current_report(directory, root)
    summary_path = directory/'travel-summary.json'
    check(summary_path.resolve(strict=True) == summary_path, 'Redirected travel summary')
    summary_bytes = summary_path.read_bytes()
    check(digest(load_json(summary_bytes)) == digest(audited), 'Saved travel summary is stale or altered')
    blobs = {name: (directory/name).read_bytes() for name in ('dataset.json', 'travel-plan.json')}
    for name, value in blobs.items():
        check(sha256(value) == audited['sourceSHA256'][name], 'Changed source before connector arithmetic')
    result = compute(load_json(blobs['dataset.json']), load_json(blobs['travel-plan.json']))
    check(result['transitPackageId'] == package, 'Package differs from travel plan')
    result.update(travelPlanSHA256=audited['travelPlanSHA256'],
        sourceCostCertificateSHA256=audited['sourceCostCertificateSHA256'],
        sourceTravelSummarySHA256=sha256(summary_bytes), sourceSHA256=dict(audited['sourceSHA256']),
        analysisCodeSHA256={SELF: codes[SELF]}, semanticCodeSHA256={n: codes[n] for n in SEMANTIC_FILES})
    verify_current(result, root)
    return result


def verify_current(result, root):
    root, directory, _ = paths(root)
    check(check_package(root) == result['transitPackageId'], 'Transit package changed')
    expected = {**result['analysisCodeSHA256'], **result['semanticCodeSHA256']}
    check(code_hashes(root) == expected and expected[SELF] == LOADED_CODE_SHA256, 'Connector code changed')
    for name, expected_hash in result['sourceSHA256'].items():
        path = directory/name
        check(path.resolve(strict=True) == path and sha256(path.read_bytes()) == expected_hash, 'Travel input changed: '+name)
    summary_path = directory/'travel-summary.json'
    check(summary_path.resolve(strict=True) == summary_path and
          sha256(summary_path.read_bytes()) == result['sourceTravelSummarySHA256'], 'Travel summary changed')
    # These nine hashes are already checked by the independent travel auditor;
    # recheck its complete saved code binding at this final publication gate.
    saved = load_json(summary_path.read_bytes())
    check(travel.code_hashes(root) == saved['modelCodeSHA256'], 'Published travel model code changed')


def run(write=False, root=ROOT):
    check(type(write) is bool, 'Write flag must be boolean')
    root, directory, output = paths(root)
    result = current_report(root)
    if not write:
        check(digest(load_json(output.read_bytes())) == digest(result), 'Saved connector summary differs')
    verify_current(result, root)
    if write:
        descriptor, name = tempfile.mkstemp(prefix='.access-connector-', suffix='.json.tmp', dir=directory)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
                stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
                stream.flush(); os.fsync(stream.fileno())
            verify_current(result, root)
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
    print('Wrote connector summary.' if write else 'Verified descriptive connector summary; no files changed.')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    run(write=parser.parse_args().write)
