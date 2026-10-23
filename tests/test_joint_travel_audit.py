"""Portable travel proof tests; independent auditor never invokes a solver."""
from copy import deepcopy
from fractions import Fraction as F
import json
import math
import os
from pathlib import Path

import numpy as np
import pytest

from scripts import audit_joint_travel as a
from scripts import audit_joint_plan as cost
from test_joint_plan_audit import tiny, write_fixture, update_cost


def blob(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode('utf8')


def portable(tiny, codes=None, source_sha=None):
    source, data, health, matrices, published, hashes = deepcopy(tiny)
    codes = codes or {name: cost.sha256(name.encode()) for name in a.MODEL_FILES}
    source_sha = source_sha or cost.sha256(blob(source))
    final = deepcopy(source['plan'])
    records = []
    # For the tiny fixture the exact optimum fills the cheaper first origin to
    # 100 and assigns 90 from the second; no native optimization is used.
    c0, c1 = 10 / .19, 20 / .19
    y0, z = c0 - c1, c1
    exact = F(.1) * F(y0) + F(.19) * F(z)
    exact += min(F(0), F(c0) - F(y0) - F(z)) * F(.1)
    exact += min(F(0), F(c1) - F(z)) * F(.1)
    lower = float(exact)
    if F(lower) > exact: lower = float(np.nextafter(lower, -np.inf))
    for row in final['profiles']:
        for i, n in enumerate((100., 90.)):
            row['allocations'][i]['population'] = n
            row['districts'][i]['coveragePercent'] = n
        row['meanMinutes'] = 2800 / 190
    for old, row in zip(source['plan']['profiles'], final['profiles']):
        records.append(dict(profile=row['profile'], status='travel_profile_accepted', reason=None,
            sourceMeanMinutes=old['meanMinutes'], finalMeanMinutes=row['meanMinutes'],
            solverReportedOptimal=True, certificateAccepted=True, inequalityDual=[y0, 0., 0., 0., 0., 0.],
            equalityDual=[z], exactLowerBoundNumerator=str(exact.numerator), exactLowerBoundDenominator=str(exact.denominator),
            lowerBoundMeanMinutes=lower, signedGapMinutes=row['meanMinutes']-lower, gapToleranceMinutes=1e-7))
    shared = dict(transitPackageId='p', planningVersion='h', scenario=deepcopy(source['scenario']),
                  sourceCostCertificateSHA256=source_sha, sourceSHA256=hashes, modelCodeSHA256=codes)
    plan = dict(format=1, artifactType='fixed-resource-four-profile-travel', **deepcopy(shared),
                generation=dict(fixedResourceTravelStagePerformed=True, jointTravelOptimumProven=False,
                                costOptimizationPerformed=False, extraBudgetTRY=0, annualDemandCountedOnce=True,
                                sameIndividualsAcrossProfilesConstrained=False), plan=final)
    proof = dict(format=1, artifactType='fixed-resource-travel-proof', **deepcopy(shared),
                 travelPlanSHA256=cost.sha256(blob(plan)), profiles=records,
                 executionOrigin=dict(kind='native_run', sourceReportSHA256=None, sourceVectorsSHA256=None),
                 timing=dict(configuredOverallSeconds=60., configuredProfileSeconds=15., searchElapsedSeconds=.1,
                             cooperativeLimitOverrunSeconds=0.), scope=a.PROOF_SCOPE)
    return dict(travel_plan=plan, proof=proof, source_certificate=source, data=data, health=health,
                matrices=matrices, published_single_profile=published, current_source_hashes=hashes,
                package_id='p', current_model_code_hashes=codes, source_certificate_sha256=source_sha,
                travel_plan_sha256=cost.sha256(blob(plan)))


def rebind(args):
    args['travel_plan_sha256'] = cost.sha256(blob(args['travel_plan']))
    args['proof']['travelPlanSHA256'] = args['travel_plan_sha256']


def fallback(args, index):
    old = args['source_certificate']['plan']['profiles'][index]
    args['travel_plan']['plan']['profiles'][index] = deepcopy(old)
    row = args['proof']['profiles'][index]
    row.update(status='source_preserved', sourceMeanMinutes=old['meanMinutes'], finalMeanMinutes=old['meanMinutes'],
               certificateAccepted=False, solverReportedOptimal=False, reason='Synthetic timeout')
    for k in ('inequalityDual', 'equalityDual', 'exactLowerBoundNumerator', 'exactLowerBoundDenominator',
              'lowerBoundMeanMinutes', 'signedGapMinutes', 'gapToleranceMinutes'): row[k] = None
    rebind(args)


def test_complete_independent_tiny_certificate_and_decimal_bill(tiny):
    args = portable(tiny); report = a.validate_joint_travel(**args)
    assert report['status'] == 'validated_fixed_resource_travel' and report['allProfilesAccepted']
    assert report['acceptedProfileCount'] == 4 and report['annualCostUnchanged'] and report['resourcesUnchanged']
    assert cost.D(report['decimalAnnualEquivalentCostTRY']) == cost.D('6050')
    assert all(x['meanMinutes'] == pytest.approx(2800/190) for x in report['profiles'])
    assert all(abs(x['primalMinusLowerBoundMinutes']) < 1e-12 for x in report['profiles'])
    assert not report['globalTravelOptimumProven'] and not report['sameIndividualsAcrossProfilesConstrained']
    assert report['conditionalOverlap']['province']['lowerPercent'] == 80


def test_mixed_and_all_fallback_are_explicit_and_bound_free(tiny):
    args = portable(tiny); fallback(args, 0)
    report = a.validate_joint_travel(**args)
    assert report['acceptedProfileCount'] == 3 and not report['allProfilesAccepted']
    assert report['profiles'][0]['sourceFallback'] and report['profiles'][0]['lowerBoundMinutes'] is None
    for i in range(1, 4): fallback(args, i)
    args['travel_plan']['generation']['fixedResourceTravelStagePerformed'] = False; rebind(args)
    report = a.validate_joint_travel(**args)
    assert report['acceptedProfileCount'] == 0 and not report['fixedResourceTravelStagePerformed']


def test_migrated_origin_is_explicit_reference_not_history_replay(tiny):
    args = portable(tiny); origin = dict(kind='reviewed_run_migration', sourceReportSHA256='a'*64, sourceVectorsSHA256='b'*64)
    args['proof']['executionOrigin'] = origin
    report = a.validate_joint_travel(**args)
    assert report['executionOrigin'] == origin and 'without loading or replaying' in report['executionOriginScope']


@pytest.mark.parametrize('origin', [None, {}, {'kind':'other','sourceReportSHA256':None,'sourceVectorsSHA256':None},
    {'kind':'native_run','sourceReportSHA256':'a'*64,'sourceVectorsSHA256':None},
    {'kind':'reviewed_run_migration','sourceReportSHA256':None,'sourceVectorsSHA256':'b'*64},
    {'kind':'reviewed_run_migration','sourceReportSHA256':'a'*64,'sourceVectorsSHA256':'broken'},
    {'kind':'native_run','sourceReportSHA256':None,'sourceVectorsSHA256':None,'replayed':True}])
def test_origin_metadata_is_fail_closed(tiny, origin):
    args = portable(tiny); args['proof']['executionOrigin'] = origin
    with pytest.raises(ValueError): a.validate_joint_travel(**args)


@pytest.mark.parametrize('mutation', ['format_bool', 'plan_package', 'proof_package', 'health', 'proof_health',
    'scenario', 'proof_scenario', 'source_hash', 'code_hash', 'missing_code', 'source_certificate', 'plan_hash',
    'strong_claim', 'bool_claim', 'extra_budget', 'stage_false', 'proof_order', 'duplicate_profile', 'missing_profile',
    'status', 'solver_bool', 'certificate_bool', 'dual_shape', 'dual_bool', 'dual_nan', 'dual_inf',
    'dual_wrong', 'numerator', 'denominator', 'fraction_not_reduced', 'bound', 'gap', 'tolerance', 'mean',
    'extra_claim_field', 'resource', 'double_material', 'flow_invalid', 'overall_limit', 'profile_limit', 'timing', 'scope'])
def test_false_or_stale_proofs_fail_closed(tiny, mutation):
    args = portable(tiny); plan = args['travel_plan']; proof = args['proof']; row = proof['profiles'][0]
    if mutation == 'format_bool': plan['format'] = True
    elif mutation == 'plan_package': plan['transitPackageId'] = 'x'
    elif mutation == 'proof_package': proof['transitPackageId'] = 'x'
    elif mutation == 'health': plan['planningVersion'] = 'old'
    elif mutation == 'proof_health': proof['planningVersion'] = 'old'
    elif mutation == 'scenario': plan['scenario']['threshold'] = 46
    elif mutation == 'proof_scenario': proof['scenario']['threshold'] = 46
    elif mutation == 'source_hash': proof['sourceSHA256']['dataset.json'] = '0'*64
    elif mutation == 'code_hash': proof['modelCodeSHA256']['backend/joint_model.py'] = '0'*64
    elif mutation == 'missing_code': del proof['modelCodeSHA256']['scripts/audit_joint_travel.py']
    elif mutation == 'source_certificate': plan['sourceCostCertificateSHA256'] = '0'*64
    elif mutation == 'plan_hash': proof['travelPlanSHA256'] = '0'*64
    elif mutation == 'strong_claim': plan['generation']['jointTravelOptimumProven'] = True
    elif mutation == 'bool_claim': plan['generation']['annualDemandCountedOnce'] = 1
    elif mutation == 'extra_budget': plan['generation']['extraBudgetTRY'] = 1
    elif mutation == 'stage_false': plan['generation']['fixedResourceTravelStagePerformed'] = False
    elif mutation == 'proof_order': proof['profiles'].reverse()
    elif mutation == 'duplicate_profile': proof['profiles'][1] = deepcopy(row)
    elif mutation == 'missing_profile': proof['profiles'].pop()
    elif mutation == 'status': row['status'] = 'globally_optimal'
    elif mutation == 'solver_bool': row['solverReportedOptimal'] = 1
    elif mutation == 'certificate_bool': row['certificateAccepted'] = 1
    elif mutation == 'dual_shape': row['inequalityDual'].pop()
    elif mutation == 'dual_bool': row['inequalityDual'][0] = False
    elif mutation == 'dual_nan': row['inequalityDual'][0] = float('nan')
    elif mutation == 'dual_inf': row['equalityDual'][0] = float('inf')
    elif mutation == 'dual_wrong': row['equalityDual'][0] += 3
    elif mutation == 'numerator': row['exactLowerBoundNumerator'] = str(int(row['exactLowerBoundNumerator'])+1)
    elif mutation == 'denominator': row['exactLowerBoundDenominator'] = '0'
    elif mutation == 'fraction_not_reduced':
        row['exactLowerBoundNumerator'] = str(int(row['exactLowerBoundNumerator'])*2)
        row['exactLowerBoundDenominator'] = str(int(row['exactLowerBoundDenominator'])*2)
    elif mutation == 'bound': row['lowerBoundMeanMinutes'] += 1e-8
    elif mutation == 'gap': row['signedGapMinutes'] += .1
    elif mutation == 'tolerance': row['gapToleranceMinutes'] = 1
    elif mutation == 'mean': row['finalMeanMinutes'] += .1
    elif mutation == 'extra_claim_field': row['minimumHospitalCountProven'] = True
    elif mutation == 'resource': plan['plan']['selected'][0]['doctors'] -= 1
    elif mutation == 'double_material': plan['plan']['annualMaterialCostTRY'] *= 4
    elif mutation == 'flow_invalid': plan['plan']['profiles'][0]['allocations'][0]['population'] += 1
    elif mutation == 'overall_limit': proof['timing']['configuredOverallSeconds'] = 61
    elif mutation == 'profile_limit': proof['timing']['configuredProfileSeconds'] = 16
    elif mutation == 'timing': proof['timing']['cooperativeLimitOverrunSeconds'] = 1
    elif mutation == 'scope': proof['scope'] = 'Global joint optimum over all Ankara'
    if mutation != 'plan_hash': rebind(args)
    with pytest.raises(ValueError): a.validate_joint_travel(**args)


@pytest.mark.parametrize('mutation', ['bound', 'dual', 'optimal', 'different_flow', 'stage_true'])
def test_fallback_never_invents_bound_or_silently_changes_original(tiny, mutation):
    args = portable(tiny)
    for i in range(4): fallback(args, i)
    args['travel_plan']['generation']['fixedResourceTravelStagePerformed'] = False
    row = args['proof']['profiles'][0]
    if mutation == 'bound': row['lowerBoundMeanMinutes'] = 0
    elif mutation == 'dual': row['inequalityDual'] = []
    elif mutation == 'optimal': row['solverReportedOptimal'] = True
    elif mutation == 'different_flow': args['travel_plan']['plan']['profiles'][0]['allocations'].reverse()
    else: args['travel_plan']['generation']['fixedResourceTravelStagePerformed'] = True
    rebind(args)
    with pytest.raises(ValueError): a.validate_joint_travel(**args)


def test_independent_exact_bound_repairs_sign_and_nonstationarity(tiny):
    args = portable(tiny); lp = a.represented_lp(args['data'], args['health'], args['source_certificate'], args['matrices'][a.PROFILES[0]])
    exact, lower = a.independent_bound(lp, [1.,0.,0.,0.,0.,0.], [0.])
    assert exact == 0 and lower == 0  # Wrong positive inequality sign is clipped.
    exact, lower = a.independent_bound(lp, [0.]*6, [1000.])
    assert exact <= F(2800/190) and F(lower) <= exact


def test_unused_open_site_keeps_resources_and_annual_bill(tiny):
    changed = deepcopy(tiny); source = changed[0]
    source['plan']['selected'].append(dict(candidateIndex=1, id='s1', templateId='ten', beds=10,
        doctors=1, grossAreaM2=101., footprintRadiusMeters=10., maximumAssignedPopulationAcrossProfiles=0.))
    update_cost(source, changed[2]); args = portable(changed)
    for i in range(4): fallback(args, i)
    args['travel_plan']['generation']['fixedResourceTravelStagePerformed'] = False; rebind(args)
    report = a.validate_joint_travel(**args)
    assert report['hospitalCount'] == 2 and report['beds'] == 20 and report['doctors'] == 11
    assert report['selected'][1]['maximumAssignedPopulationAcrossProfiles'] == 0
    assert cost.D(report['decimalAnnualEquivalentCostTRY']) == cost.D('9260')


def test_independent_bound_post_round_overflow_is_rejected():
    # Two free-in-box variables with sufficiently negative objective; no huge
    # real-data LP or solver required for the numeric conversion boundary.
    lp = dict(b=np.zeros(4), target=1., n=1, m=1, origins=np.array([0,0]),
              destinations=np.array([0,0]), district_rows=np.array([0,0]),
              c=np.array([-np.finfo(float).max,-1e290]), upper=np.ones(2))
    with pytest.raises(ValueError, match='Nonfinite downward'):
        a.independent_bound(lp, [0.]*4, [0.])


@pytest.fixture
def cli(tmp_path, tiny, monkeypatch):
    directory = write_fixture(tmp_path/'data/processed', tiny)
    for name in a.MODEL_FILES:
        target = tmp_path/name; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((a.ROOT/name).read_bytes())
    cert = cost.load_json((directory/'joint-plan.json').read_bytes())
    altered = deepcopy(tiny); altered = (cert, *altered[1:5], cert['sourceSHA256'])
    args = portable(altered, a.code_hashes(tmp_path), cost.sha256((directory/'joint-plan.json').read_bytes()))
    (directory/'travel-plan.json').write_bytes(blob(args['travel_plan']))
    (directory/'travel-proof.json').write_bytes(blob(args['proof']))
    calls = []
    monkeypatch.setattr(a, 'ROOT', tmp_path)
    monkeypatch.setattr(a, 'check_package', lambda root: calls.append(root) or 'p')
    return directory, calls


def test_safe_write_then_readonly_and_all_input_code_bindings(cli):
    directory, calls = cli; original = {n:(directory/n).read_bytes() for n in a.FILES}
    result = a.run(write=True); snapshot = {p.name:p.read_bytes() for p in directory.iterdir()}
    assert a.run() == result and len(calls) == 4
    assert snapshot == {p.name:p.read_bytes() for p in directory.iterdir()}
    assert original == {n:(directory/n).read_bytes() for n in a.FILES}
    assert len(result['sourceSHA256']) == 11 and len(result['modelCodeSHA256']) == 9


@pytest.mark.parametrize('name', a.FILES)
def test_each_portable_input_byte_mutation_is_detected(cli, name):
    directory, _ = cli; a.run(write=True)
    with (directory/name).open('ab') as stream: stream.write(b' ')
    with pytest.raises(ValueError): a.run()


@pytest.mark.parametrize('change', ['package', 'source', 'code'])
def test_exit_identity_change_prevents_publication(cli, monkeypatch, change):
    directory, calls = cli
    def package(root):
        calls.append(root)
        if len(calls) == 2:
            if change == 'package': return 'changed'
            target = directory/'travel-proof.json' if change == 'source' else a.ROOT/'backend/joint_travel.py'
            with target.open('ab') as stream: stream.write(b' ')
        return 'p'
    monkeypatch.setattr(a, 'check_package', package)
    with pytest.raises(ValueError): a.run(write=True)
    assert not (directory/'travel-summary.json').exists()


def test_hardlink_and_unique_temporary_do_not_modify_any_source(cli):
    directory, _ = cli; source = directory/'joint-plan.json'; original = source.read_bytes()
    os.link(source, directory/'travel-summary.json'); os.link(source, directory/'travel-summary.json.tmp')
    a.run(write=True)
    assert source.read_bytes() == original and (directory/'travel-summary.json.tmp').read_bytes() == original


def test_failed_replace_cleans_only_owned_temporary(cli, monkeypatch):
    directory, _ = cli; marker = directory/'.travel-summary-keep.json.tmp'; marker.write_text('keep')
    before = {p.name:p.read_bytes() for p in directory.iterdir()}
    monkeypatch.setattr(Path, 'replace', lambda *args: (_ for _ in ()).throw(OSError('synthetic replace failure')))
    with pytest.raises(OSError): a.run(write=True)
    assert before == {p.name:p.read_bytes() for p in directory.iterdir()}


@pytest.mark.parametrize('payload', [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'])
def test_json_loader_rejects_ambiguous_keys_and_nonfinite(payload):
    with pytest.raises(ValueError): cost.load_json(payload)
