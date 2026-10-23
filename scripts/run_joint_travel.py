"""Minimize travel on a complete joint plan's unchanged sites and resources.

Writes separate portable travel-plan/proof JSON files to a new work directory.
The cost certificate is never changed. No ignored research files are required.
"""
import argparse
from copy import deepcopy
from pathlib import Path
import re
import sys
from time import monotonic

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_joint_plan as base
from backend.joint_travel import improve_travel

NEW_CODE_FILES = ('backend/joint_travel.py', 'scripts/run_joint_travel.py', 'scripts/audit_joint_travel.py')
CODE_FILES = base.CODE_FILES + NEW_CODE_FILES
SCOPE = ('Separate per-profile assignment LPs with every source open location, bed type and physician integer fixed, '
         'including zero-load sites. Bounds concern only these fixed resources and supplied matrices. '
         'No global joint location/resource optimum, hospital-count optimum, annual frequency weights, '
         'or coupling of individual identities across profiles.')


def code_hashes():
    return {name: base.sha((ROOT / name).read_bytes().replace(b'\r\n', b'\n')) for name in CODE_FILES}


def loaded_hashes():
    # Called after the independent auditor is installed/imported as part of this
    # command. Data and source certificate hashes always use exact file bytes.
    return code_hashes()


LOADED_CODE_HASHES = loaded_hashes()


def controls(seconds, profile_seconds):
    if base.positive(seconds, 'overall seconds') > 60 or base.positive(profile_seconds, 'profile seconds') > 15:
        raise ValueError('Maximum overall/per-profile limits are 60/15 seconds')


def resource_signature(plan):
    fields = ('candidateIndex', 'id', 'templateId', 'beds', 'doctors', 'grossAreaM2', 'footprintRadiusMeters')
    return sorted(tuple(s[k] for k in fields) for s in plan['selected'])


def validate_source(root=ROOT, seed=None):
    """Read-only preflight: package, complete source, original model, no solver."""
    root = Path(root).resolve(strict=True)
    seed_path = Path(seed) if seed is not None else root / 'data/processed/joint-plan.json'
    if not seed_path.is_absolute(): seed_path = root / seed_path
    seed_path = seed_path.resolve(strict=True)
    if not seed_path.is_file(): raise ValueError('Seed must be a complete cost certificate file')
    codes = code_hashes()
    if codes != LOADED_CODE_HASHES: raise ValueError('Loaded travel/model/audit code changed; restart command')
    package, hashes, seed_hash, source, data, health, matrices, published, audit = base.read_sources(root, seed_path)
    problem = base.formulate(data, health, matrices, source['scenario'],
                             [s['candidateIndex'] for s in source['plan']['selected']])
    vector, residuals = problem.read_plan(source['plan'])
    inputs = dict(root=root, seed_path=seed_path, package=package, hashes=hashes, seed_hash=seed_hash,
                  source=source, data=data, health=health, matrices=matrices, published=published,
                  source_audit=audit, problem=problem, source_vector=vector, source_residuals=residuals, codes=codes)
    unchanged(inputs)
    return inputs


def unchanged(inputs):
    base.unchanged(inputs['root'], inputs['package'], inputs['hashes'], inputs['seed_path'],
                   inputs['seed_hash'], {k: inputs['codes'][k] for k in base.CODE_FILES})
    if code_hashes() != inputs['codes'] or inputs['codes'] != LOADED_CODE_HASHES:
        raise ValueError('Loaded travel/model/audit code changed during run')


def execution_origin(value=None):
    """Describe native execution versus revalidation of a reviewed past run."""
    value = deepcopy(value) if value is not None else dict(kind='native_run', sourceReportSHA256=None, sourceVectorsSHA256=None)
    if not isinstance(value, dict) or set(value) != {'kind','sourceReportSHA256','sourceVectorsSHA256'}:
        raise ValueError('Exact execution origin fields required')
    if value['kind'] == 'native_run':
        if value['sourceReportSHA256'] is not None or value['sourceVectorsSHA256'] is not None:
            raise ValueError('Native execution cannot claim historical source artifacts')
    elif value['kind'] == 'reviewed_run_migration':
        if any(type(value[k]) is not str or re.fullmatch('[0-9a-f]{64}', value[k]) is None
               for k in ('sourceReportSHA256','sourceVectorsSHA256')):
            raise ValueError('Migration needs exact source report and vector SHA256 references')
    else: raise ValueError('Unknown execution origin')
    return value


def portable_artifacts(inputs, result, capture, timing, *, execution_origin_record=None):
    """Build a complete portable record; also usable to migrate reviewed flows.

    This function does not solve, publish, or claim a new execution. The supplied
    timing and per-profile native observations remain observations of their run.
    An independent final audit is mandatory before writing either artifact.
    """
    source = inputs['source']; records = result.get('fixedResourceTravel', {}).get('profiles', [])
    by_name = {x['profile']: x for x in records}
    if records and (len(records) != len(base.PROFILES) or set(by_name) != set(base.PROFILES)):
        raise ValueError('Complete unique four-profile travel records required')
    if resource_signature(result) != resource_signature(source['plan']):
        raise ValueError('Any source resource/location/footprint changed')
    plan = {key: deepcopy(result[key]) for key in base.PLAN_FIELDS}
    # These fields describe exactly the same bill. Keep the source's published
    # float representation rather than introducing a new dot-product rounding.
    # Both model validation and the independent Decimal audit still check it.
    for key in ('annualEquivalentCostTRY','annualMaterialCostTRY','annualFixedResourceCostTRY'):
        plan[key] = source['plan'][key]
    profiles = []
    for old, final in zip(source['plan']['profiles'], plan['profiles']):
        name = old['profile']
        if name != final['profile']: raise ValueError('Profile identity/order changed')
        record = by_name.get(name)
        accepted = record is not None and record.get('accepted') is True
        entry = dict(profile=name, status='travel_profile_accepted' if accepted else 'source_preserved',
                     sourceMeanMinutes=old['meanMinutes'], finalMeanMinutes=final['meanMinutes'],
                     solverReportedOptimal=accepted, certificateAccepted=accepted,
                     reason=None if accepted else (record or {}).get('reason', result.get('searchSkipped', 'Source retained')),
                     inequalityDual=None, equalityDual=None, exactLowerBoundNumerator=None,
                     exactLowerBoundDenominator=None, lowerBoundMeanMinutes=None,
                     signedGapMinutes=None, gapToleranceMinutes=None)
        if accepted:
            if record.get('status') != 'travel_profile_accepted' or record.get('solverReportedOptimal') is not True:
                raise ValueError('Accepted profile status contradicts solver observation')
            dual = capture[name]; certificate = record['certificate']
            entry.update(inequalityDual=np.asarray(dual['inequalityDual'], float).tolist(),
                         equalityDual=np.asarray(dual['equalityDual'], float).tolist(),
                         exactLowerBoundNumerator=certificate['exactNumerator'],
                         exactLowerBoundDenominator=certificate['exactDenominator'],
                         lowerBoundMeanMinutes=certificate['lowerBoundMinutes'],
                         signedGapMinutes=final['meanMinutes']-certificate['lowerBoundMinutes'],
                         gapToleranceMinutes=1e-7)
        elif final != old:
            raise ValueError('A preserved profile must retain the complete exact source JSON assignment')
        profiles.append(entry)
    shared = dict(transitPackageId=inputs['package'], planningVersion=source['planningVersion'],
                  scenario=deepcopy(source['scenario']), sourceCostCertificateSHA256=inputs['seed_hash'],
                  sourceSHA256=inputs['hashes'], modelCodeSHA256=inputs['codes'])
    artifact = dict(format=1, artifactType='fixed-resource-four-profile-travel', **shared,
                    generation=dict(fixedResourceTravelStagePerformed=any(p['certificateAccepted'] for p in profiles),
                                    jointTravelOptimumProven=False, costOptimizationPerformed=False, extraBudgetTRY=0,
                                    annualDemandCountedOnce=True, sameIndividualsAcrossProfilesConstrained=False), plan=plan)
    proof = dict(format=1, artifactType='fixed-resource-travel-proof', **shared,
                 travelPlanSHA256=base.sha(base.json_bytes(artifact)), profiles=profiles,
                 timing=timing, scope=SCOPE, executionOrigin=execution_origin(execution_origin_record))
    return artifact, proof


def run(*, out, seed=None, seconds=60, profile_seconds=15, root=ROOT):
    from scripts.audit_joint_travel import validate_joint_travel
    controls(seconds, profile_seconds)
    began = monotonic(); root = Path(root).resolve(strict=True)
    folder = base.output_directory(root, out)
    inputs = validate_source(root, seed); p = inputs['problem']; source = inputs['source']
    folder.mkdir(parents=True, exist_ok=False)
    capture = {}; remaining = seconds - (monotonic() - began)
    if remaining <= 0:
        result = deepcopy(source['plan'])
        result['searchSkipped'] = 'Preflight exhausted travel budget; no native LP started'
        capture['finalVector'] = inputs['source_vector'].copy()
    else:
        result = improve_travel(p, source['plan'], remaining, profile_seconds, capture=capture)
    search_elapsed = monotonic() - began
    vector, residuals = p.read_plan(result)
    raw = capture['finalVector']
    delta = float(np.max(np.abs(vector-raw), initial=0))
    if not np.array_equal(vector[:p.nf], raw[:p.nf]) or delta > 1e-12:
        raise ValueError('Final JSON/original vector differs beyond serialization allowance')
    if not np.array_equal(vector[:p.nf], inputs['source_vector'][:p.nf]):
        raise ValueError('Fixed source resource vector changed')
    timing = dict(configuredOverallSeconds=seconds, configuredProfileSeconds=profile_seconds,
                  searchElapsedSeconds=search_elapsed, cooperativeLimitOverrunSeconds=max(0., search_elapsed-seconds))
    artifact, proof = portable_artifacts(inputs, result, capture, timing)
    artifact_bytes = base.json_bytes(artifact); proof_bytes = base.json_bytes(proof)
    audit = validate_joint_travel(travel_plan=artifact, proof=proof, source_certificate=source,
        data=inputs['data'], health=inputs['health'], matrices=inputs['matrices'],
        published_single_profile=inputs['published'], current_source_hashes=inputs['hashes'],
        package_id=inputs['package'], current_model_code_hashes=inputs['codes'],
        source_certificate_sha256=inputs['seed_hash'], travel_plan_sha256=base.sha(artifact_bytes))
    if audit['decimalAnnualEquivalentCostTRY'] != inputs['source_audit']['decimalAnnualEquivalentCostTRY']:
        raise ValueError('Independent Decimal annual bill changed')
    unchanged(inputs)
    # Source and all nine consumed code identities checked after independent
    # validation. No circular hashes: proof -> plan -> source cost certificate.
    base.write_new(folder / 'travel-proof.json', proof_bytes)
    base.write_new(folder / 'travel-audit.json', base.json_bytes(audit))
    base.write_new(folder / 'travel-plan.json', artifact_bytes)
    print('Saved separate fixed-resource travel plan:', folder)
    return artifact, proof, audit


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, help='New directory under work/; existing paths are rejected')
    parser.add_argument('--seed', help='Complete current joint cost certificate; defaults to published joint-plan.json')
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--profile-seconds', type=float, default=15)
    run(**vars(parser.parse_args()))
