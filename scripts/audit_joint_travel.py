"""Audit portable fixed-resource travel plans and exact dual witnesses, without a solver.

The unchanged cost certificate and current data define every coefficient. Neither
the travel helper nor its exact-box proof implementation is imported here.
"""
import argparse
from copy import deepcopy
from fractions import Fraction
import io
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import json

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import audit_joint_plan as cost
from scripts.transit_provenance import check_package

MODEL_FILES = ('backend/joint_model.py', 'backend/joint_solver.py', 'backend/joint_heuristic.py',
               'scripts/run_joint_plan.py', 'scripts/audit_joint_plan.py', 'scripts/transit_provenance.py',
               'backend/joint_travel.py', 'scripts/run_joint_travel.py', 'scripts/audit_joint_travel.py')
AUDITOR_FILES = ('scripts/audit_joint_plan.py', 'scripts/transit_provenance.py', 'scripts/audit_joint_travel.py')
FILES = (*cost.SOURCE_FILES, 'joint-plan.json', 'travel-plan.json', 'travel-proof.json')
PROFILES = cost.PROFILES
GAP_TOLERANCE = 1e-7
COMPARISON_TOLERANCE = 1e-9
PROOF_SCOPE = ('Separate per-profile assignment LPs with every source open location, bed type and physician integer fixed, '
               'including zero-load sites. Bounds concern only these fixed resources and supplied matrices. '
               'No global joint location/resource optimum, hospital-count optimum, annual frequency weights, '
               'or coupling of individual identities across profiles.')
check, keys, digest, sha256 = cost.check, cost.keys, cost.digest, cost.sha256


def code_hashes(root=ROOT):
    return {name: sha256((Path(root) / name).read_bytes().replace(b'\r\n', b'\n')) for name in MODEL_FILES}


LOADED_AUDITOR_HASHES = {name: sha256((ROOT / name).read_bytes().replace(b'\r\n', b'\n')) for name in AUDITOR_FILES}


def finite(value, name):
    check(type(value) in (int, float) and math.isfinite(value), 'Finite non-boolean number required: ' + name)
    return float(value)


def near_signed(value, expected, tolerance, name):
    check(abs(finite(value, name) - expected) <= tolerance, 'Incorrect ' + name)


def hashes(actual, expected, names, label):
    keys(actual, names, label); keys(expected, names, 'current ' + label)
    for name in names:
        check(cost.hash_value(actual[name]) == cost.hash_value(expected[name]), 'Stale ' + label + ': ' + name)


def resource_signature(plan):
    fields = ('candidateIndex', 'id', 'templateId', 'beds', 'doctors', 'grossAreaM2', 'footprintRadiusMeters')
    return [(x['candidateIndex'], digest({k: x[k] for k in fields})) for x in sorted(plan['selected'], key=lambda x: x['candidateIndex'])]


def represented_lp(data, health, source, matrix):
    """Independent semantic row families, in the documented portable order.

    Matrix column ordering is current global candidate ordering; the local pool
    is the sorted source selection. Each variable is thousands of residents.
    """
    sites = sorted(source['plan']['selected'], key=lambda x: x['candidateIndex'])
    ids = [x['candidateIndex'] for x in sites]
    population = np.array([x['population'] for x in data['demands']], dtype=float)
    district_lookup = {x['id']: i for i, x in enumerate(data['districts'])}
    s = source['scenario']; rates = health['rates']
    contact = float(rates['contactsPerResident']) * float(s['demandMultiplier'])
    bedrate = float(rates['bedDaysPerResident']) * float(s['demandMultiplier'])
    target = float(data['metadata']['provincePopulation']) * float(s['coverageTarget']) / 100 / 1000
    times = np.asarray(matrix, dtype=float)[:, ids]
    origins, destinations = np.where(np.isfinite(times) & (times <= s['threshold']))
    beds = np.array([x['beds'] for x in sites], dtype=float)
    doctors = np.array([x['doctors'] for x in sites], dtype=float)
    rhs = np.r_[population / 1000, beds * 365 * (float(s['bedOccupancy']) / 100) / bedrate / 1000,
                doctors * (float(s['contactsPerDoctor']) / contact / 1000),
                [-x['population'] * s['districtFloor'] / 100 / 1000 for x in data['districts']]]
    district_rows = np.array([district_lookup[data['demands'][i]['districtId']] for i in origins], dtype=int)
    return dict(ids=ids, origins=origins, destinations=destinations, district_rows=district_rows,
                c=times[origins, destinations] / target, upper=population[origins] / 1000,
                b=rhs, target=target, n=len(population), m=len(sites))


def independent_bound(lp, raw_y, raw_z):
    """Recompute weak duality by the four semantic row families, not sparse code.

    All Fraction conversions represent stored binary64 coefficients exactly.
    Nonpositive inequality multipliers plus finite origin-variable bounds repair
    arbitrary stationarity residuals. This is not an exact-feasible primal claim.
    """
    cost.sequence(raw_y, 'inequality dual'); cost.sequence(raw_z, 'equality dual')
    check(len(raw_y) == len(lp['b']) and len(raw_z) == 1, 'Dual dimensions differ from current fixed-resource LP')
    y = [Fraction.from_float(min(0., finite(v, 'inequality dual'))) for v in raw_y]
    z = Fraction.from_float(finite(raw_z[0], 'equality dual'))
    F = lambda x: Fraction.from_float(float(x))
    bound = sum((F(b) * v for b, v in zip(lp['b'], y)), Fraction()) + F(lp['target']) * z
    n, m = lp['n'], lp['m']
    for k, (origin, site, district) in enumerate(zip(lp['origins'], lp['destinations'], lp['district_rows'])):
        reduced = F(lp['c'][k]) - y[origin] - y[n + site] - y[n + m + site] + y[n + 2 * m + district] - z
        if reduced < 0:
            bound += reduced * F(lp['upper'][k])
    try:
        value = float(bound)
    except OverflowError:
        raise ValueError('Nonfinite rational lower-bound conversion') from None
    check(math.isfinite(value), 'Nonfinite lower bound')
    if Fraction.from_float(value) > bound:
        with np.errstate(over='ignore'):
            value = float(np.nextafter(value, -np.inf))
    check(math.isfinite(value), 'Nonfinite downward-rounded lower bound')
    return bound, value


def validate_joint_travel(travel_plan, proof, source_certificate, data, health, matrices,
                          published_single_profile, current_source_hashes, package_id,
                          current_model_code_hashes, source_certificate_sha256, travel_plan_sha256):
    """Return recomputed UI metrics; every unsupported or stale claim raises."""
    header = ('format', 'artifactType', 'transitPackageId', 'planningVersion', 'scenario',
              'sourceCostCertificateSHA256', 'sourceSHA256', 'modelCodeSHA256', 'generation', 'plan')
    keys(travel_plan, header, 'travel plan')
    keys(proof, ('format', 'artifactType', 'travelPlanSHA256', 'sourceCostCertificateSHA256',
                 'transitPackageId', 'planningVersion', 'scenario', 'sourceSHA256', 'modelCodeSHA256',
                 'profiles', 'timing', 'scope', 'executionOrigin'), 'travel proof')
    for value in (travel_plan, proof):
        check(type(value['format']) is int and value['format'] == 1, 'Integer format 1 required')
        check(value['sourceCostCertificateSHA256'] == cost.hash_value(source_certificate_sha256), 'Wrong source cost certificate')
        hashes(value['sourceSHA256'], current_source_hashes, cost.SOURCE_FILES, 'source hash')
        hashes(value['modelCodeSHA256'], current_model_code_hashes, MODEL_FILES, 'model code hash')
        check(value['transitPackageId'] == package_id, 'Travel package mismatch')
    check(travel_plan['artifactType'] == 'fixed-resource-four-profile-travel' and
          proof['artifactType'] == 'fixed-resource-travel-proof', 'Unsupported artifact type')
    check(proof['travelPlanSHA256'] == cost.hash_value(travel_plan_sha256), 'Proof points to another travel plan')
    check(travel_plan['planningVersion'] == source_certificate['planningVersion'] == health['version'], 'Health version mismatch')
    check(digest(travel_plan['scenario']) == digest(source_certificate['scenario']), 'Travel scenario changed')
    check(proof['planningVersion'] == travel_plan['planningVersion'] and digest(proof['scenario']) == digest(travel_plan['scenario']), 'Proof scenario/health version differs')
    generation = travel_plan['generation']
    flags = {'jointTravelOptimumProven': False, 'costOptimizationPerformed': False,
             'annualDemandCountedOnce': True, 'sameIndividualsAcrossProfilesConstrained': False}
    keys(generation, (*flags, 'extraBudgetTRY', 'fixedResourceTravelStagePerformed'), 'travel generation')
    for k, v in flags.items(): check(generation[k] is v, 'Unsupported travel claim: ' + k)
    check(type(generation['fixedResourceTravelStagePerformed']) is bool, 'Travel stage flag must be boolean')
    check(finite(generation['extraBudgetTRY'], 'extra budget') == 0, 'No additional travel budget permitted')
    timing = proof['timing']
    keys(timing, ('configuredOverallSeconds', 'configuredProfileSeconds', 'searchElapsedSeconds',
                  'cooperativeLimitOverrunSeconds'), 'travel timing')
    check(0 < finite(timing['configuredOverallSeconds'], 'overall seconds') <= 60, 'Overall limit outside 0..60')
    check(0 < finite(timing['configuredProfileSeconds'], 'profile seconds') <= 15, 'Profile limit outside 0..15')
    elapsed = cost.number(timing['searchElapsedSeconds'], 'elapsed seconds')
    near_signed(timing['cooperativeLimitOverrunSeconds'], max(0., elapsed - timing['configuredOverallSeconds']), 1e-9, 'timing overrun')
    check(proof['scope'] == PROOF_SCOPE, 'Unsupported or contradictory proof scope')
    origin = proof['executionOrigin']
    keys(origin, ('kind', 'sourceReportSHA256', 'sourceVectorsSHA256'), 'execution origin')
    check(origin['kind'] in ('native_run', 'reviewed_run_migration'), 'Unknown execution origin')
    for key in ('sourceReportSHA256', 'sourceVectorsSHA256'):
        if origin['kind'] == 'native_run':
            check(origin[key] is None, 'Native run must not claim a historical migration reference')
        else:
            cost.hash_value(origin[key])

    before = cost.validate_joint_plan(source_certificate, data, health, matrices, published_single_profile,
                                     current_source_hashes, package_id)
    adapter = deepcopy(source_certificate); adapter['plan'] = travel_plan['plan']
    after = cost.validate_joint_plan(adapter, data, health, matrices, published_single_profile,
                                    current_source_hashes, package_id)
    check(resource_signature(source_certificate['plan']) == resource_signature(travel_plan['plan']), 'Fixed source resources changed')
    for field in ('decimalAnnualEquivalentCostTRY', 'decimalAnnualMaterialCostTRY', 'decimalAnnualFixedResourceCostTRY'):
        check(before[field] == after[field], 'Exact Decimal annual bill changed')
    records = cost.sequence(proof['profiles'], 'profile proofs')
    check(len(records) == 4 and tuple(x.get('profile') for x in records) == PROFILES, 'Exactly four ordered profile proofs required')
    output = []; accepted_count = 0
    for index, record in enumerate(records):
        keys(record, ('profile', 'status', 'sourceMeanMinutes', 'finalMeanMinutes', 'solverReportedOptimal',
                      'certificateAccepted', 'inequalityDual', 'equalityDual', 'exactLowerBoundNumerator',
                      'exactLowerBoundDenominator', 'lowerBoundMeanMinutes', 'signedGapMinutes', 'gapToleranceMinutes', 'reason'), 'profile proof')
        profile = record['profile']; old = before['profiles'][index]; new = after['profiles'][index]
        check(record['reason'] is None or type(record['reason']) is str, 'Reason must be text or null')
        check(type(record['solverReportedOptimal']) is bool and type(record['certificateAccepted']) is bool, 'Strict profile proof flags required')
        near_signed(record['sourceMeanMinutes'], old['meanMinutes'], COMPARISON_TOLERANCE, 'source profile mean')
        near_signed(record['finalMeanMinutes'], new['meanMinutes'], COMPARISON_TOLERANCE, 'final profile mean')
        check(new['meanMinutes'] <= old['meanMinutes'] + COMPARISON_TOLERANCE, 'Profile mean worsened')
        accepted = record['status'] == 'travel_profile_accepted'
        check(accepted or record['status'] == 'source_preserved', 'Unknown proof status')
        lower = signed = tolerance = None
        if accepted:
            check(generation['fixedResourceTravelStagePerformed'], 'Accepted profile without a travel stage')
            check(record['certificateAccepted'] and record['solverReportedOptimal'], 'Accepted profile lacks reported solver/certificate outcome')
            check(finite(record['gapToleranceMinutes'], 'gap tolerance') == GAP_TOLERANCE, 'Unsupported primal-dual tolerance')
            lp = represented_lp(data, health, source_certificate, matrices[profile])
            exact, lower = independent_bound(lp, record['inequalityDual'], record['equalityDual'])
            for k, pattern in (('exactLowerBoundNumerator', r'-?(0|[1-9][0-9]*)'), ('exactLowerBoundDenominator', r'[1-9][0-9]*')):
                check(type(record[k]) is str and len(record[k]) <= 10000 and re.fullmatch(pattern, record[k]) is not None, 'Canonical rational integer required')
            check(record['exactLowerBoundNumerator'] == str(exact.numerator) and
                  record['exactLowerBoundDenominator'] == str(exact.denominator), 'Exact rational dual certificate differs')
            check(finite(record['lowerBoundMeanMinutes'], 'lower bound') == lower, 'Downward-rounded dual bound differs')
            signed = new['meanMinutes'] - lower; tolerance = GAP_TOLERANCE
            near_signed(record['signedGapMinutes'], signed, COMPARISON_TOLERANCE, 'signed primal-dual gap')
            check(signed >= -GAP_TOLERANCE, 'Dual bound exceeds numerically validated primal beyond tolerance')
            accepted_count += 1
        else:
            check(not record['certificateAccepted'] and not record['solverReportedOptimal'], 'Fallback cannot claim an accepted or optimal solve')
            for k in ('inequalityDual', 'equalityDual', 'exactLowerBoundNumerator', 'exactLowerBoundDenominator',
                      'lowerBoundMeanMinutes', 'signedGapMinutes', 'gapToleranceMinutes'):
                check(record[k] is None, 'Fallback cannot carry a dual bound')
            check(digest(travel_plan['plan']['profiles'][index]) == digest(source_certificate['plan']['profiles'][index]), 'Fallback must preserve the complete original profile')
        output.append(dict(new, status=record['status'], accepted=accepted, sourceFallback=not accepted,
                           sourceMeanMinutes=old['meanMinutes'], reductionMinutes=old['meanMinutes'] - new['meanMinutes'],
                           lowerBoundMinutes=lower, primalMinusLowerBoundMinutes=signed, primalDualToleranceMinutes=tolerance,
                           certifiedForRepresentedFixedResourceLP=accepted, solverReportedOptimal=record['solverReportedOptimal']))
    check(generation['fixedResourceTravelStagePerformed'] == (accepted_count > 0), 'Travel stage flag disagrees with accepted profiles')
    # Drop the private format-1 adapter's historical generation labels.
    for key in ('generation', 'generationReferenceScope', 'aboveBudgetInterpretation'):
        after.pop(key, None)
    after.update(status='validated_fixed_resource_travel', profiles=output,
                 sourceCostCertificateSHA256=source_certificate_sha256, travelPlanSHA256=travel_plan_sha256,
                 resourcesUnchanged=True, annualCostUnchanged=True, globalTravelOptimumProven=False,
                 allProfilesAccepted=accepted_count == 4, acceptedProfileCount=accepted_count,
                 fixedResourceTravelStagePerformed=generation['fixedResourceTravelStagePerformed'],
                 modelCodeSHA256=dict(current_model_code_hashes), timing=dict(timing),
                 executionOrigin=dict(origin),
                 executionOriginScope='Historical migration references identify the reviewed original run; this portable audit checks reference formats and current plan/proof independently without loading or replaying ignored history. Current code hashes identify the portable formulation/serialization/audit, not necessarily the historical native producer.',
                 scope='Independently checked per-profile assignment on exactly the source cost-plan resources. Duals certify the represented binary64 LP; primal feasibility retains stated numerical tolerances. No global site/resource optimum, same-person95%, real travel-time or clinical guarantee.')
    return after


def current_report(processed_directory, root=ROOT):
    directory = Path(processed_directory).resolve(strict=True); root = Path(root).resolve(strict=True)
    codes = code_hashes(root)
    for name in AUDITOR_FILES:
        check(codes[name] == LOADED_AUDITOR_HASHES[name], 'Loaded auditor code differs from current source')
    blobs = {}
    for name in FILES:
        path = (directory / name).resolve(strict=True)
        check(path.parent == directory and path.is_file(), 'Source path escapes processed directory')
        blobs[name] = path.read_bytes()
    parsed = {n: cost.load_json(b) for n, b in blobs.items() if n.endswith('.json')}
    count = len(parsed['dataset.json']['candidates']); matrices = {}
    for p in PROFILES:
        with np.load(io.BytesIO(blobs[f'transit-{p}-matrix.npz']), allow_pickle=False) as z:
            check(set(z.files) == {'minutes'} and z['minutes'].ndim == 2 and z['minutes'].shape[1] >= count, 'Invalid matrix archive')
            matrices[p] = z['minutes'][:, :count]
    inputs = {n: sha256(blobs[n]) for n in cost.SOURCE_FILES}
    result = validate_joint_travel(parsed['travel-plan.json'], parsed['travel-proof.json'], parsed['joint-plan.json'],
        parsed['dataset.json'], parsed['health-planning.json'], matrices, parsed['example-transit-result.json'], inputs,
        parsed['dataset.json']['metadata']['transitPackageId'], codes, sha256(blobs['joint-plan.json']), sha256(blobs['travel-plan.json']))
    result['sourceSHA256'] = {n: sha256(b) for n, b in blobs.items()}
    for n, b in blobs.items(): check((directory / n).read_bytes() == b, 'Source changed during travel audit')
    check(code_hashes(root) == codes, 'Code changed during travel audit')
    return result


def run(write=False):
    check(type(write) is bool, 'Write flag must be boolean')
    package = check_package(ROOT); directory = (ROOT / 'data/processed').resolve(strict=True)
    output = directory / 'travel-summary.json'
    check(output.resolve(strict=False).parent == directory, 'Output escapes processed directory')
    result = current_report(directory, ROOT)
    check(result['transitPackageId'] == package, 'Current package differs from travel plan')
    if not write:
        check(digest(cost.load_json(output.read_bytes())) == digest(result), 'Saved travel summary differs from current computation')
    check(check_package(ROOT) == package, 'Package changed before publication')
    for n, h in result['sourceSHA256'].items(): check(sha256((directory / n).read_bytes()) == h, 'Source changed before publication')
    check(code_hashes(ROOT) == result['modelCodeSHA256'], 'Code changed before publication')
    if write:
        descriptor, name = tempfile.mkstemp(prefix='.travel-summary-', suffix='.json.tmp', dir=directory)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf8', newline='\n') as stream:
                stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
                stream.flush(); os.fsync(stream.fileno())
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
        print('Wrote independently validated fixed-resource travel summary:', output)
    else:
        print('Verified fixed-resource travel plan and exact dual evidence; no files changed.')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    run(write=parser.parse_args().write)
