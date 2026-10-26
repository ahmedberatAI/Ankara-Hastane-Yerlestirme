from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from backend import motis
from scripts import verify_motis as verify


def raw_response(query, transit=False):
    begin = query + timedelta(minutes=2)
    end = query + timedelta(minutes=22 if transit else 8)
    leg = {'startTime': begin.isoformat(), 'endTime': end.isoformat(),
           'mode': 'BUS' if transit else 'WALK', 'tripId': 'synthetic-test-trip' if transit else None,
           'legGeometry': {'points': '??', 'precision': 6}}
    item = {'startTime': begin.isoformat(), 'endTime': end.isoformat(), 'legs': [leg]}
    return {'direct': [] if transit else [item], 'itineraries': [item] if transit else []}


@pytest.fixture
def package(tmp_path, monkeypatch):
    original_root = motis.ROOT
    data_dir = tmp_path/'data/processed'; out = data_dir/'motis'; out.mkdir(parents=True)
    data = {'demands': [{'id': 'd0', 'node': 0, 'snapMeters': 31, 'population': 5000},
                        {'id': 'd1', 'node': 1, 'snapMeters': 75, 'population': 1000}],
            'candidates': [{'id': 'c0', 'node': 2, 'accessMeters': 75},
                           {'id': 'c1', 'node': 3, 'accessMeters': 150}],
            'hospitals': [{'id': 'h0'}]}
    (data_dir/'dataset.json').write_bytes(motis.canonical(data))
    np.save(data_dir/'graph-coordinates.npy', np.array([[32,39], [32.1,39.1], [33,40], [33.1,40.1]]))
    np.savez(data_dir/'car-matrix.npz', minutes=np.ones((2,3), dtype=np.float32))
    for name in ('backend/motis.py', 'scripts/build_motis_matrices.py'):
        target = tmp_path/name; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((original_root/name).read_bytes())
    monkeypatch.setattr(motis, 'ROOT', tmp_path)
    monkeypatch.setattr(motis, 'DATA', data_dir)
    monkeypatch.setattr(motis, 'MATRIX_DIR', out)
    refs = {'dataset': 'data/processed/dataset.json', 'graphCoordinates': 'data/processed/graph-coordinates.npy',
            'carMatrix': 'data/processed/car-matrix.npz'}
    for key in ('sourceManifest','config','runtimeConfig','GTFS','OSM','engine','imported/tt.bin','imported/osr/routing.bin'):
        refs[key] = 'work/missing/'+key
    hashes = {k: motis.file_sha(tmp_path/v) if (tmp_path/v).is_file() else 'a'*64 for k,v in refs.items()}
    indices = {k: [str(x['id']) for x in data[k]] for k in ('demands','candidates','hospitals')}
    scope = {'kind': 'restricted_edges', 'allCandidateInfeasibilityProofAllowed': False,
             'bulkIsOnlyShortlistHint': True, 'bulkAndPlanEquivalent': False, 'finalEndpoint': '/api/v6/plan',
             'connectorSpeedMetersPerSecond': 1.25, 'originConnectorBeforeQuery': True,
             'queryTimeCeilingMinutes': True, 'maximumTotalMinutes': 120., 'currentOfficialEGO': False,
             'unqueriedMeans': 'unknown, not no service', 'emptyPlanMeans': 'unknown within dated data and search limits',
             'perFootprintClass': 12}
    manifest = {'format': 1, 'engineVersion': motis.ENGINE_VERSION, 'policyVersion': motis.POLICY_VERSION,
        'scenario': motis.SCENARIO, 'profiles': motis.PROFILES, 'planParameters': motis.PLAN_PARAMETERS,
        'existingComparisonAvailable': False, 'searchScope': scope, 'indices': indices,
        'indexSHA256': hashlib.sha256(motis.canonical(indices)).hexdigest(), 'matrices': {},
        'sourceFiles': refs, 'sourceSHA256': hashes, 'codeLF_SHA256': motis.model_codes()}
    for profile in motis.PROFILES:
        path = out/(profile+'-matrix.npz')
        np.savez_compressed(path, minutes=np.array([[10,25,np.inf],[10,25,np.inf]], dtype=np.float32),
                            queried=np.array([[True,True,False],[True,True,False]]))
        manifest['matrices'][profile] = {'file': path.name, 'sha256': motis.file_sha(path),
            'departure': motis.PROFILES[profile], 'shape': [2,3], 'computedCount': 4, 'queriedCount': 4,
            'unknownQueriedCount': 0, 'unqueriedCount': 2, 'queryCount': 4,
            'providerFailureCount': 0, 'bulkFailureCount': 0}
    def save_manifest():
        manifest.pop('packageId', None)
        manifest['packageId'] = 'motis-'+hashlib.sha256(motis.canonical(manifest)).hexdigest()
        (out/'manifest.json').write_bytes(motis.canonical(manifest))
        motis._validated_manifest.cache_clear(); motis._load.cache_clear()
    save_manifest()
    snap = verify.snapshot()
    runtime = {'pid': 42, 'processCreatedEpoch': 123., 'processImportVerified': True, 'listener': '127.0.0.1:8088',
        'executable': 'work/free-routing-research-2026-10-26/motis-2.10.2/motis.exe',
        'importDirectory': 'work/free-routing-research-2026-10-26/local-motis/data'}
    doc = {'format': 1, 'artifactType': 'motis-recorded-route-checks', 'provider': 'motis',
        'datasetScenario': motis.SCENARIO, 'engineVersion': motis.ENGINE_VERSION,
        'packageId': manifest['packageId'], 'manifestSHA256': snap['manifestSHA256'],
        'sourceSHA256': manifest['sourceSHA256'], 'codeLF_SHA256': manifest['codeLF_SHA256'],
        'verificationCodeLF_SHA256': snap['verificationCodeLF_SHA256'],
        'matrixSHA256': {p: manifest['matrices'][p]['sha256'] for p in motis.PROFILES},
        'capturedAt': '2026-10-26T20:00:00+00:00', 'runtimeBefore': runtime, 'runtimeAfter': deepcopy(runtime),
        'currentOfficialEGO': False, 'allCandidateInfeasibilityProofAllowed': False,
        'matrixToleranceMinutes': .001, 'captureMethod': 'local_plan_raw_response',
        'cases': [], 'attemptedRequestsByProfile': {p: 2 for p in motis.PROFILES},
        'walkAndTransitByProfile': {p: True for p in motis.PROFILES}}
    for profile in motis.PROFILES:
        for j in (0,1):
            params, departure, query, oa, da = verify.expected_request(snap, profile, 0, j)
            raw = raw_response(query, j == 1)
            doc['cases'].append({'profile': profile, 'demandIndex': 0, 'candidateIndex': j,
                'demandId': 'd0', 'candidateId': 'c'+str(j), 'requestedDeparture': motis.PROFILES[profile],
                'originAccessMeters': oa, 'destinationAccessMeters': da,
                'request': {'method': 'GET', 'endpoint': '/api/v6/plan', 'parameters': params},
                'rawResponse': raw, 'rawResponseSHA256': hashlib.sha256(motis.canonical(raw)).hexdigest(),
                'derived': verify.derive_response(raw, departure, query, oa, da), 'matrixMinutes': 10. if j == 0 else 25.})
    (out/verify.FILE_NAME).write_bytes(motis.canonical(doc))
    yield snap, doc, manifest, out, save_manifest, runtime
    motis._validated_manifest.cache_clear(); motis._load.cache_clear()


def test_default_offline_audit_does_not_query_or_inspect_live_process(package, monkeypatch):
    monkeypatch.setattr(motis, 'request_json', lambda *a, **kw: pytest.fail('Offline audit queried network'))
    monkeypatch.setattr(verify.motis_runtime, 'runtime_identity', lambda: pytest.fail('Offline audit requires running engine'))
    result = verify.audit()
    assert result['rawRouteChecks'] == 8 and result['networkQueriesPerformed'] == 0
    assert all(result['walkAndTransitByProfile'].values())


@pytest.mark.parametrize('field,value', [
    ('provider','ego'), ('datasetScenario','current official'), ('engineVersion','2.9'),
    ('packageId','motis-other'), ('manifestSHA256','0'*64), ('sourceSHA256',{}),
    ('codeLF_SHA256',{}), ('verificationCodeLF_SHA256',{}), ('matrixSHA256',{}),
    ('currentOfficialEGO',True), ('allCandidateInfeasibilityProofAllowed',True),
    ('matrixToleranceMinutes',1), ('captureMethod','bulk'), ('runtimeAfter',{}),
])
def test_capture_identity_and_scope_tampering_rejected(package, field, value):
    snap, doc, *_ = package; bad = deepcopy(doc); bad[field] = value
    with pytest.raises(ValueError): verify.validate_capture(bad, snap)


@pytest.mark.parametrize('field,value', [
    ('demandIndex',True), ('candidateIndex',2), ('demandId','other'), ('candidateId','other'),
    ('requestedDeparture','2026-10-28T08:00:00+03:00'), ('originAccessMeters',0),
    ('destinationAccessMeters',999), ('matrixMinutes',9), ('rawResponseSHA256','0'*64),
    ('profile','weekday-0805'), ('request',{}), ('derived',{}),
])
def test_case_identity_and_clock_tampering_rejected(package, field, value):
    snap, doc, *_ = package; bad = deepcopy(doc); bad['cases'][0][field] = value
    with pytest.raises(ValueError): verify.validate_capture(bad, snap)


def update_raw(case):
    case['rawResponseSHA256'] = hashlib.sha256(motis.canonical(case['rawResponse'])).hexdigest()


def test_arrival_edit_cannot_pass_by_refreshing_response_hash_and_derived_fields(package):
    snap, doc, *_ = package; bad = deepcopy(doc); case = bad['cases'][0]
    item = case['rawResponse']['direct'][0]
    changed = (datetime.fromisoformat(item['endTime'])+timedelta(minutes=1)).isoformat()
    item['endTime'] = item['legs'][0]['endTime'] = changed; update_raw(case)
    _, departure, query, oa, da = verify.expected_request(snap, case['profile'],0,0)
    case['derived'] = verify.derive_response(case['rawResponse'],departure,query,oa,da)
    with pytest.raises(ValueError, match='saved matrix'): verify.validate_capture(bad,snap)


@pytest.mark.parametrize('mutation', ['before_query','bad_mode','cancelled','bad_geometry','fake_interline','empty','nonmonotonic'])
def test_unsupported_raw_states_fail_closed(package,mutation):
    snap,doc,*_=package; bad=deepcopy(doc); case=bad['cases'][0]; item=case['rawResponse']['direct'][0]
    if mutation=='before_query':
        item['startTime']=item['legs'][0]['startTime']=motis.PROFILES[case['profile']]
    elif mutation=='bad_mode': item['legs'][0]['mode']='CAR'
    elif mutation=='cancelled': item['legs'][0]['cancelled']=True
    elif mutation=='bad_geometry': item['legs'][0]['legGeometry']['points']='_'
    elif mutation=='fake_interline': item['legs'][0]['interlineWithPreviousLeg']=True
    elif mutation=='empty': case['rawResponse']['direct']=[]
    elif mutation=='nonmonotonic': item['legs'][0]['endTime']=item['startTime']
    update_raw(case)
    with pytest.raises(ValueError): verify.validate_capture(bad,snap)


def test_four_boardings_fail_even_with_consistent_timestamps():
    start=datetime.fromisoformat('2026-10-27T05:00:00+00:00'); raw=raw_response(start,True)
    item=raw['itineraries'][0]; item['startTime']=start.isoformat(); item['endTime']=(start+timedelta(minutes=4)).isoformat()
    item['legs']=[{'mode':'BUS','startTime':(start+timedelta(minutes=k)).isoformat(),
        'endTime':(start+timedelta(minutes=k+1)).isoformat(),'legGeometry':{'points':'??','precision':6}} for k in range(4)]
    with pytest.raises(ValueError,match='transfer'): verify.derive_response(raw,start,start,0,0)


def test_counts_masks_existing_and_departures_recomputed(package):
    snap,_,m,*_=package
    for mutate in ('existing','unqueried','nan','shape','count','departure','scope'):
        arrays={p:(a.copy(),q.copy()) for p,(a,q) in snap['arrays'].items()}; manifest=deepcopy(m)
        p=next(iter(arrays));a,q=arrays[p]
        if mutate=='existing': a[0,2]=5;q[0,2]=True
        elif mutate=='unqueried': q[0,0]=False
        elif mutate=='nan': a[0,0]=np.nan
        elif mutate=='shape': arrays[p]=(a[:1],q[:1])
        elif mutate=='count': manifest['matrices'][p]['queriedCount']+=1
        elif mutate=='departure': manifest['matrices'][p]['departure']=motis.PROFILES['sunday-1000']
        elif mutate=='scope': manifest['searchScope']['allCandidateInfeasibilityProofAllowed']=True
        with pytest.raises(ValueError): verify.validate_matrices(manifest,snap['data'],arrays)


def test_missing_fourth_profile_and_byte_mutation_fail(package):
    _,_,manifest,out,save,_=package; p=next(iter(manifest['matrices']))
    original=manifest['matrices'].pop(p);save()
    with pytest.raises(ValueError,match='four'): verify.snapshot()
    manifest['matrices'][p]=original;save()
    with (out/original['file']).open('ab') as stream: stream.write(b'TAMPER')
    with pytest.raises(ValueError,match='SHA'): verify.snapshot()


def test_duplicate_samples_and_false_diversity_claim_rejected(package):
    snap,doc,*_=package
    bad=deepcopy(doc);bad['cases'][1]=bad['cases'][0]
    with pytest.raises(ValueError,match='Duplicate'): verify.validate_capture(bad,snap)
    bad=deepcopy(doc);bad['walkAndTransitByProfile']['weekday-0800']=False
    with pytest.raises(ValueError,match='diversity'): verify.validate_capture(bad,snap)


def test_capture_live_mock_uses_canonical_requests_and_only_eight_calls(package,monkeypatch):
    _,_,manifest,out,_,runtime=package; calls=[]
    monkeypatch.setattr(motis,'require_live_sources',lambda:manifest)
    monkeypatch.setattr(verify.motis_runtime,'runtime_identity',lambda:deepcopy(runtime))
    def request(path,*,params):
        assert path=='/api/v6/plan';calls.append(params)
        assert params['timetableView'] is False and params['maxTransfers']==2
        return raw_response(datetime.fromisoformat(params['time'].replace('Z','+00:00')),params['toPlace'].startswith('40.10000000'))
    monkeypatch.setattr(motis,'request_json',request)
    result=verify.capture_live()
    assert len(calls)==8 and result['rawRouteChecks']==8
    assert result['networkQueriesPerformed']==8
    assert json.loads((out/verify.FILE_NAME).read_text())['runtimeBefore']==runtime


def test_capture_rejects_package_or_runtime_changed_before_publication(package,monkeypatch):
    _,_,manifest,out,_,runtime=package; before=(out/verify.FILE_NAME).read_bytes(); count=[0]
    def live():
        count[0]+=1
        return manifest if count[0]==1 else {**manifest,'packageId':'changed'}
    monkeypatch.setattr(motis,'require_live_sources',live)
    monkeypatch.setattr(verify.motis_runtime,'runtime_identity',lambda:deepcopy(runtime))
    monkeypatch.setattr(motis,'request_json',lambda path,*,params:raw_response(datetime.fromisoformat(params['time'].replace('Z','+00:00')),params['toPlace'].startswith('40.10000000')))
    with pytest.raises(ValueError,match='Package changed'): verify.capture_live()
    assert (out/verify.FILE_NAME).read_bytes()==before


def test_loaded_code_mutation_is_not_claimed_as_current(monkeypatch):
    monkeypatch.setattr(verify,'_LOADED_CODE','0'*64)
    with pytest.raises(ValueError,match='Loaded'): verify.verifier_codes()


@pytest.mark.parametrize('field,value',[('currentOfficialEGO',0),('allCandidateInfeasibilityProofAllowed',0),
    ('format',True),('extraGlobalProof',True)])
def test_false_booleans_and_extra_claim_fields_are_not_coerced(package,field,value):
    snap,doc,*_=package;bad=deepcopy(doc);bad[field]=value
    with pytest.raises(ValueError):verify.validate_capture(bad,snap)


def test_capture_runtime_restart_aborts_without_replacing_saved_checks(package,monkeypatch):
    _,_,manifest,out,_,runtime=package;before=(out/verify.FILE_NAME).read_bytes();calls=[0]
    monkeypatch.setattr(motis,'require_live_sources',lambda:manifest)
    def identity():
        calls[0]+=1
        return {**runtime,'pid':42 if calls[0]==1 else 43}
    monkeypatch.setattr(verify.motis_runtime,'runtime_identity',identity)
    monkeypatch.setattr(motis,'request_json',lambda path,*,params:raw_response(datetime.fromisoformat(params['time'].replace('Z','+00:00')),params['toPlace'].startswith('40.10000000')))
    with pytest.raises(ValueError,match='Runtime changed'):verify.capture_live()
    assert (out/verify.FILE_NAME).read_bytes()==before


def test_equal_duration_near_and_far_samples_remain_distinct(package):
    snap,*_=package
    for matrix,_ in snap['arrays'].values():matrix[:,:2]=5
    pairs=verify._sample_pairs(snap,'weekday-0800')
    assert pairs[:2]==[(0,0),(0,1)]
    assert len(pairs)==len(set(pairs))
