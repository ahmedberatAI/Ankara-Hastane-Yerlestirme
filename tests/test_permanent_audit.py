"""Independent permanent-plan audit adversaries; no native search or routing."""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest

from scripts import verify_permanent as a


def fixture(pop=(1, 1), zero_open=False):
    # The production adapter is deliberately part of this integration fixture;
    # the audit itself does not import the optimizer/builder/serializer.
    from backend import permanent as p
    from backend import permanent_service as service
    policy = json.loads((a.ROOT / 'data/planning-policy.json').read_text(encoding='utf8'))
    health = {'version': 'audit-tiny',
        'rates': {'contactsPerResident': 2140, 'bedDaysPerResident': 292},
        'templates': [{'id': 'one', 'beds': 1, 'grossAreaM2': 1},
                      {'id': 'two', 'beds': 2, 'grossAreaM2': 2},
                      {'id': 'twenty', 'beds': 20, 'grossAreaM2': 20}],
        'design': {'areaPerDoctorM2': 1, 'maxFloors': 1, 'minimumDoctorsPerSite': 1},
        'economics': {'realDiscountRate': 0, 'horizonYears': 1, 'buildingUnitCostTRY': 1,
            'annualFixedSiteCostTRY': 1, 'annualDoctorCostTRY': 3,
            'annualBedSupportCostTRY': 2, 'costPerContactTRY': 5 / 2140}}
    data = {'metadata': {'provincePopulation': sum(pop)},
        'districts': [{'id': str(i), 'name': 'D' + str(i), 'population': value} for i, value in enumerate(pop)],
        'demands': [{'id': 'O' + str(i), 'districtId': str(i), 'population': value} for i, value in enumerate(pop)],
        'candidates': [{'id': 'C' + str(j), 'name': 'S' + str(j), 'lat': 39.9, 'lon': 32.8 + j * .02,
                        'footprintRadiusMeters': 10} for j in range(3)], 'hospitals': [{'id': 'existing'}]}
    times = {name: np.full((len(pop), 3), float(2 + 2*k)) for k, name in enumerate(p.PROFILES)}
    candidates = [{**c, 'candidateIndex': j} for j, c in enumerate(data['candidates'])]
    problem = p.build_permanent_problem(times, pop, [str(i) for i in range(len(pop))],
        data['districts'], sum(pop), health, policy, candidates, car_neighbors=None)
    vector = p._greedy_seed(problem, p.monotonic() + 3)
    assert vector is not None
    if zero_open:
        existing = {problem.xsite[x] for x in np.flatnonzero(vector[:problem.nx])}
        j = next(j for j in range(3) if j not in existing)
        x = next(x for x in problem.site_xs[j] if problem.xtype[x] == 0)
        vector[x] = 1; vector[problem.nx + j] = 1
    result = p._api_result(problem, vector, vector, problem.cost(vector) * 1.1,
        None, None, {}, [], p.monotonic(), [])
    ident = {'modelCodeLF_SHA256': {'test/model.py': 'a' * 64}, 'sourceSHA256': {'test': 'b' * 64},
        'planningVersion': health['version'], 'policyId': policy['id'], 'transitPackageId': 'motis-' + 'c' * 64}
    result = service.enrich(result, data, policy, ident)
    return result, data, health, times, policy


@pytest.fixture(autouse=True)
def forbid_native(monkeypatch):
    import highspy
    from backend import motis
    monkeypatch.setattr(highspy.Highs, 'run', lambda *x, **k: pytest.fail('Unexpected native solve'))
    monkeypatch.setattr(motis, 'request_json', lambda *x, **k: pytest.fail('Unexpected route/service request'))


def test_service_enrich_full_five_profile_roundtrip():
    args = fixture(); report = a.audit(*args)
    assert report['valid'] and report['profileCount'] == 5
    assert report['criticalTransitProfile'] == 'sunday-1000'
    assert report['weightedMeanMinutes'] == pytest.approx(.7 * 2 + .075 * 28)
    assert report['annualMaterialCostTRY'] == pytest.approx(9.5)
    assert not report['nativeBoundsCertified'] and not report['allDayServiceProven']
    assert not report['referenceIncumbentReplayed']


def test_full_matrices_with_unused_existing_columns_are_allowed():
    r, d, h, ts, pol = fixture()
    padded = {p: np.c_[t, np.full((len(t), 1), np.inf)] for p, t in ts.items()}
    assert a.audit(r, d, h, padded, pol) == a.audit(r, d, h, ts, pol)


def test_zero_load_open_site_remains_legal_in_count_and_bill():
    args = fixture(zero_open=True); result = a.audit(*args)
    assert any(s['assignedPopulation'] == 0 for s in args[0]['selected'])
    assert result['hospitalCount'] == len(args[0]['selected'])


@pytest.mark.parametrize('name', a.PROFILES)
def test_each_profile_required_in_common_and_api(name):
    args = fixture(); r = args[0]
    r['profiles'].pop(name)
    with pytest.raises(ValueError, match='profile'): a.audit(*args)
    args = fixture(); r = args[0]
    r['commonPlan']['profiles'] = [x for x in r['commonPlan']['profiles'] if x['profile'] != name]
    with pytest.raises(ValueError, match='profiles'): a.audit(*args)


@pytest.mark.parametrize('name', a.PROFILES)
def test_every_profile_hard_time_limit(name):
    args = fixture(); r, _, _, ts, _ = args
    f = next(p for p in r['commonPlan']['profiles'] if p['profile'] == name)['allocations'][0]
    ts[name][f['demandIndex'], f['candidateIndex']] = (30 if name == 'car' else 60) + .001
    with pytest.raises(ValueError, match='threshold'): a.audit(*args)


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -1, True, '1', None])
def test_allocation_numbers_are_strict(bad):
    args = fixture()
    args[0]['commonPlan']['profiles'][0]['allocations'][0]['population'] = bad
    with pytest.raises(ValueError): a.audit(*args)


def test_zero_positive_flow_record_is_rejected():
    args = fixture(); args[0]['commonPlan']['profiles'][0]['allocations'][0]['population'] = 0
    with pytest.raises(ValueError, match='positive flow'): a.audit(*args)


def test_closed_and_duplicate_positive_flow_rejected():
    args = fixture(); r = args[0]
    closed = next(j for j in range(3) if j not in r['selectedIndices'])
    r['commonPlan']['profiles'][0]['allocations'][0]['candidateIndex'] = closed
    with pytest.raises(ValueError, match='closed'): a.audit(*args)
    args = fixture(); rows = args[0]['commonPlan']['profiles'][0]['allocations']
    rows.append(deepcopy(rows[0]))
    with pytest.raises(ValueError, match='duplicate flow'): a.audit(*args)


def test_tiny_district_requires_percentage_not_absolute_population_tolerance():
    args = fixture(pop=(1, 10)); rows = args[0]['commonPlan']['profiles'][0]['allocations']
    first = next(x for x in rows if x['demandIndex'] == 0)
    second = next(x for x in rows if x['demandIndex'] == 1)
    delta = first['population'] - .79995
    first['population'] = .79995; second['population'] += delta
    with pytest.raises(ValueError, match='district percentage'): a.audit(*args)


def test_exact_province_target_not_only_at_least_95():
    args = fixture(); args[0]['commonPlan']['profiles'][0]['allocations'][0]['population'] += .01
    with pytest.raises(ValueError, match='exact province'): a.audit(*args)


def test_origin_amount_cannot_exceed_its_population():
    args = fixture(); rows = args[0]['commonPlan']['profiles'][0]['allocations']
    first = next(x for x in rows if x['demandIndex'] == 0)
    second = next(x for x in rows if x['demandIndex'] == 1)
    delta = 1.01 - first['population']; first['population'] += delta; second['population'] -= delta
    with pytest.raises(ValueError, match='origin population'): a.audit(*args)


@pytest.mark.parametrize('resource', ['bed', 'doctor'])
def test_bed_and_doctor_capacities_are_independent(resource):
    args = fixture(); r = args[0]; core = r['commonPlan']['selected'][0]; site = r['selected'][0]
    if resource == 'doctor':
        diff = core['doctors'] - 1; core['doctors'] = 1
        r['commonPlan']['totalDoctors'] -= diff; r['capacity']['totalDoctors'] -= diff
    else:
        diff = core['beds'] - 1; core['beds'] = 1; core['templateId'] = 'one'
        r['commonPlan']['totalBeds'] -= diff; r['capacity']['totalBeds'] -= diff
    core['grossAreaM2'] = core['beds'] + core['doctors']
    site.update(core)
    with pytest.raises(ValueError, match='separate bed/physician'): a.audit(*args)


def test_original_province_doctor_upper_bound():
    args = fixture(); r = args[0]; core = r['commonPlan']['selected'][0]
    core['doctors'] = 3; core['grossAreaM2'] = core['beds'] + 3
    r['selected'][0].update(core)
    with pytest.raises(ValueError, match='staff upper bound'): a.audit(*args)


def test_physical_footprints_cannot_overlap():
    args = fixture(zero_open=True); r, data = args[:2]
    first, second = r['selectedIndices'][:2]
    for key in ('lat', 'lon'):
        data['candidates'][second][key] = data['candidates'][first][key]
        r['selected'][1][key] = data['candidates'][first][key]
    with pytest.raises(ValueError, match='footprints overlap'): a.audit(*args)


def test_plot_and_doctor_area_are_combined():
    args = fixture(); r, data = args[:2]; j = r['selectedIndices'][0]
    data['candidates'][j]['footprintRadiusMeters'] = .2
    r['commonPlan']['selected'][0]['footprintRadiusMeters'] = .2
    r['selected'][0]['footprintRadiusMeters'] = .2
    with pytest.raises(ValueError, match='staff upper bound|Plot capacity'): a.audit(*args)


def test_district_p90_includes_unserved_residents():
    row = {'coveredPopulation': .8, 'reachablePopulation': .8,
        'unreachableOrUnlocatedPopulation': .2, 'meanPopulationDenominator': .8,
        'coveragePercent': 80, 'meanMinutes': 2, 'p90Minutes': None}
    a._metrics(row, a.D('.8'), a.D('1.6'), a.D(1), [(2, a.D('.8'))], 'district')
    row['p90Minutes'] = 2
    with pytest.raises(ValueError, match='p90'):
        a._metrics(row, a.D('.8'), a.D('1.6'), a.D(1), [(2, a.D('.8'))], 'district')


@pytest.mark.parametrize('key,value', [('threshold', 45), ('transitThreshold', 90), ('coverageTarget', 90),
    ('districtFloor', 79), ('contactsPerDoctor', True), ('bedOccupancy', 85), ('costTolerance', 15),
    ('carWeight', 50), ('hospitalLimit', 91)])
def test_policy_override_rejected(key, value):
    args = fixture(); args[4][key] = value; args[0]['policy'][key] = value
    with pytest.raises(ValueError, match='policy|number'): a.audit(*args)


@pytest.mark.parametrize('mutation', [
    lambda r: r['selected'][0].__setitem__('id', 'wrong'),
    lambda r: r['selected'][0].__setitem__('lat', 39.5),
    lambda r: r['selectedIndices'].__setitem__(0, True),
    lambda r: r['commonPlan']['selected'][0].__setitem__('doctors', True),
    lambda r: r['commonPlan']['selected'][0].__setitem__('beds', 3),
    lambda r: r['profiles']['car']['assignments'][0].__setitem__('demandId', 'wrong'),
    lambda r: r['profiles']['car']['assignments'][0]['allocations'][0].__setitem__('candidateId', 'wrong'),
    lambda r: r['profiles']['car']['districts'][0].__setitem__('population', .9),
    lambda r: r['profiles']['car']['assignments'][0].__setitem__('servedFraction', 0),
    lambda r: r['profiles']['car']['assignments'][0].__setitem__('covered', 1),
    lambda r: r['profiles']['car']['metrics'].__setitem__('p90Minutes', 0),
    lambda r: r['profiles']['car']['metrics'].__setitem__('meanPopulationDenominator', 2),
    lambda r: r['permanentSummary'].__setitem__('annualDemandCountedOnce', 1),
    lambda r: r['permanentSummary'].__setitem__('minimumDistrictCoveragePercent', 100),
    lambda r: r['permanentSummary'].__setitem__('meanTransitMinutes', 0),
    lambda r: r['permanentSummary']['profileWeights'].__setitem__('sunday-1000', .7),
    lambda r: r['capacity'].__setitem__('annualMaterialCostTRY', 47.5),
    lambda r: r['selected'][0]['operatingBreakdown'].__setitem__('materialsTRY', 47.5),
    lambda r: r['selected'][0].__setitem__('assignedPopulation', 9.5),
    lambda r: r['selected'][0].__setitem__('materialAccountingPopulation', 9.5),
    lambda r: r['capacity'].__setitem__('planningVersion', 'stale'),
    lambda r: r['identity'].__setitem__('planningVersion', 'stale'),
    lambda r: r['identity'].__setitem__('transitPackageId', 'ego-' + 'c'*64),
    lambda r: r['transitEvidence'].__setitem__('allCandidateInfeasibilityProofAllowed', True),
    lambda r: r['profiles']['weekday-1000']['transitEvidence'].__setitem__('departure', a.DATES['weekday-0800']),
    lambda r: r['scenario'].__setitem__('transitProfile', 'weekday-0800'),
])
def test_independent_tamper_rejections(mutation):
    args = fixture(); mutation(args[0])
    with pytest.raises(ValueError): a.audit(*args)


def test_best_profile_cannot_be_labelled_critical():
    args = fixture(); r = args[0]
    r['criticalTransitProfile'] = 'weekday-0800'
    r['permanentSummary']['criticalTransitProfile'] = 'weekday-0800'
    r['modalResults']['transit'] = r['profiles']['weekday-0800']
    with pytest.raises(ValueError, match='Critical'): a.audit(*args)


def test_modal_and_top_level_mix_rejected():
    args = fixture(); args[0]['modalResults']['transit'] = deepcopy(args[0]['profiles']['car'])
    with pytest.raises(ValueError, match='modal view'): a.audit(*args)
    args = fixture(); args[0]['assignments'] = deepcopy(args[0]['profiles']['weekday-0800']['assignments'])
    with pytest.raises(ValueError, match='top-level car'): a.audit(*args)


def test_native_bound_claim_is_not_a_feasibility_or_cost_certificate():
    args = fixture(); args[0]['lowerBound'] = 0; args[0]['gap'] = 1
    assert a.audit(*args)['nativeBoundsCertified'] is False
    args[0]['provenOptimal'] = True
    with pytest.raises(ValueError, match='optimality'): a.audit(*args)


def test_budget_reference_is_not_silently_increased():
    args = fixture(); r = args[0]
    r['capacity']['referenceCostTRY'] = 1
    r['capacity']['referenceStage']['annualEquivalentCostTRY'] = 1
    r['capacity']['budgetLimitTRY'] = 1.1
    with pytest.raises(ValueError, match='budget exceeded'): a.audit(*args)


def test_missing_population_is_not_removed_from_denominator():
    args = fixture(); args[1]['metadata']['provincePopulation'] = 2.1
    args[1]['districts'][0]['population'] = 1.1
    args[0]['metadata'] = {**args[1]['metadata'], 'activeTransitEngine': 'motis',
        'activeTransitPackageId': args[0]['identity']['transitPackageId']}
    with pytest.raises(ValueError, match='exact province'): a.audit(*args)


@pytest.mark.parametrize('bad', [np.nan, -np.inf, -1])
def test_matrix_invalid_values_even_on_unused_edges_rejected(bad):
    args = fixture(); args[3]['car'][0, 2] = bad
    with pytest.raises(ValueError, match='matrix'): a.audit(*args)


def test_bool_matrix_rejected():
    args = fixture(); args[3]['car'] = args[3]['car'].astype(bool)
    with pytest.raises(ValueError, match='Matrix'): a.audit(*args)


def test_saved_audit_summary_is_exact_not_bool_equal():
    args = fixture(); r = args[0]
    r['auditSummary'] = a.audit(*args)
    assert a.audit(*args)['valid']
    r['auditSummary']['profileCount'] = 5.0
    with pytest.raises(ValueError, match='audit summary'): a.audit(*args)


@pytest.mark.parametrize('blob', ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'])
def test_json_parser_rejects_ambiguous_records(blob):
    with pytest.raises(ValueError): a.load_json(blob)


def setup_cli(tmp_path, monkeypatch):
    from backend import permanent_evidence as e, motis
    args = fixture(); r, d, h, ts, pol = args
    processed = tmp_path / 'data/processed'; processed.mkdir(parents=True)
    files = {'dataset.json': d, 'health-planning.json': h, 'permanent-plan.json': r}
    for name, value in files.items(): (processed/name).write_bytes(a.canonical(value))
    (tmp_path/'data/planning-policy.json').write_bytes(a.canonical(pol))
    np.savez_compressed(processed/'car-matrix.npz', minutes=ts['car'])
    monkeypatch.setattr(a, 'ROOT', tmp_path)
    monkeypatch.setattr(e, 'source_identities', lambda: deepcopy(r['identity']['sourceSHA256']))
    monkeypatch.setattr(e, 'code_identities', lambda: deepcopy(r['identity']['modelCodeLF_SHA256']))
    monkeypatch.setattr(e, 'current_identity', lambda: deepcopy(r['identity']))
    monkeypatch.setattr(motis, 'load_matrix', lambda p: ts[p].copy())
    return args, processed/'permanent-plan.json'


def test_current_cli_read_only_and_all_five_matrices(tmp_path, monkeypatch):
    args, path = setup_cli(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    report = a.current_report()
    assert report['valid'] and report['planId'] == args[0]['planId']
    assert {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('field', ['sourceSHA256', 'modelCodeLF_SHA256', 'planningVersion', 'policyId', 'transitPackageId'])
def test_cli_current_identity_gate(tmp_path, monkeypatch, field):
    from backend import permanent_evidence as e
    args, _ = setup_cli(tmp_path, monkeypatch)
    changed = deepcopy(args[0]['identity']); changed[field] = 'wrong'
    monkeypatch.setattr(e, 'current_identity', lambda: changed)
    with pytest.raises(ValueError, match='identity'): a.current_report()


def test_cli_plan_id_tamper(tmp_path, monkeypatch):
    args, path = setup_cli(tmp_path, monkeypatch); args[0]['planId'] = 'permanent-' + '0'*64
    path.write_bytes(a.canonical(args[0]))
    with pytest.raises(ValueError, match='plan ID'): a.current_report()


@pytest.mark.parametrize('field', ['source_identities', 'code_identities'])
def test_cli_source_code_entry_exit_gate(tmp_path, monkeypatch, field):
    from backend import permanent_evidence as e
    args, _ = setup_cli(tmp_path, monkeypatch); calls = []
    key = 'sourceSHA256' if field == 'source_identities' else 'modelCodeLF_SHA256'
    def changing():
        calls.append(1); return deepcopy(args[0]['identity'][key]) if len(calls) == 1 else {'x': 'b'*64}
    monkeypatch.setattr(e, field, changing)
    with pytest.raises(ValueError, match='changed'): a.current_report()


def test_cli_saved_plan_entry_exit_gate(tmp_path, monkeypatch):
    _, path = setup_cli(tmp_path, monkeypatch); original = a.audit
    def mutation(*args):
        report = original(*args); path.write_text('{}'); return report
    monkeypatch.setattr(a, 'audit', mutation)
    with pytest.raises(ValueError, match='Saved plan changed'): a.current_report()


def test_cli_has_no_write_flag():
    with pytest.raises(SystemExit): a.main(['--write'])
