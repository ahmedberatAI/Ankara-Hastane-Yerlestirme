"""Independent 44-clock certificate checks; no routing or optimizer runs."""
from copy import deepcopy
import io
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pytest

from scripts import audit_window_plan as a
from test_joint_plan_audit import tiny, update_cost


def recalc_manifest(w):
    manifest = w['manifest']
    manifest['windowRoutingPackageId'] = a.routing_package_id(manifest)
    w['manifest_sha256'] = a.digest(manifest)
    w['certificate']['profileManifestSHA256'] = w['manifest_sha256']


@pytest.fixture
def window(tiny, monkeypatch):
    monkeypatch.setattr(a, 'INDEPENDENT_ORIGINS', (0, 1))
    source, data, health, baseline, published, hashes = tiny
    data['metadata'].update(referenceDate='2025-12-31', osmDate='2026-10-22')
    profiles = a.expected_profiles(); names = [p['id'] for p in profiles]
    indices = {key: [dict(index=i, id=x['id']) for i, x in enumerate(data[field])]
               for key, field in [('origins', 'demands'), ('candidates', 'candidates')]}
    matrices = {p['id']: baseline[p['baseProfileId']].copy() for p in profiles}
    codes = {name: a.sha256(name.encode()) for name in a.MODEL_FILES}
    source_hashes = {**hashes, 'joint-plan.json': a.digest(source)}
    routing_sources = {name: a.sha256(name.encode()) for name in a.ROUTING_SOURCE_FILES}
    routing_sources.update({'data/processed/' + k: v for k, v in source_hashes.items()})
    records = []
    for p in profiles:
        name = p['id']; kind = 'canonical' if name in a.BASE_PROFILES else 'archived_0805_subset' if name == 'weekday-0805' else None
        records.append(dict(profileId=name, file=name+'.npz', sha256=a.sha256(name.encode()), shape=[2, 3],
            audit=dict(validated=True, independentOriginIndices=[0, 1], independentDestinationsPerOrigin=3,
                independentMaxMinutesError=0., elapsedSeconds=.1,
                baselineCheck=None if kind is None else dict(kind=kind, comparedRows=2, comparedColumns=3,
                                                             maxMinutesError=0., bitIdentical=True))))
    comparisons = []
    for base in a.BASE_PROFILES:
        ordered = sorted([p for p in profiles if p['baseProfileId'] == base], key=lambda p:p['departureSeconds'])
        comparisons.extend(dict(earlierProfileId=x['id'], laterProfileId=y['id'], commonFinitePairs=4,
                                maxEarlyArrivalViolationMinutes=0.) for x,y in zip(ordered[:-1], ordered[1:]))
    manifest = dict(format=1, artifactType='departure-window-matrices', mode='full', status='accepted',
        parentTransitPackageId='p', windowRoutingPackageId='', profiles=profiles, initialProfileIds=names[:12],
        producedProfileIds=names, sourceSHA256=routing_sources,
        routingCodeLF_SHA256={name:a.sha256(name.encode()) for name in a.ROUTING_CODE_FILES},
        frozenModelCodeLF_SHA256={name:codes[name] for name in a.FROZEN_MODEL_FILES},
        indices=dict(file='indices.json', sha256=a.digest(indices), demandIndexSHA256=a.digest(indices['origins']),
                     candidateIndexSHA256=a.digest(indices['candidates'])), matrices=records,
        constants=dict(horizonSeconds=7200, boardingSlackSeconds=60, maxBoardings=3),
        crossProfileAudit=dict(comparisons=comparisons, toleranceMinutes=.00002),
        archived0805=dict(archive='docs/experiments/departure-0805-evidence.zip',
            matrixMember='work/referees/profile-shift-full-v07.npz', matrixSHA256='a'*64,
            reportMember='work/referees/profile-shift-full-v07.json', reportSHA256='b'*64),
        builtAt='2026-10-23T05:00:00+00:00', elapsedSeconds=1., scope='Synthetic test manifest')
    plan = deepcopy(source['plan']); by_base = {p['profile']:p for p in plan['profiles']}
    plan['profiles'] = [dict(deepcopy(by_base[p['baseProfileId']]), profile=p['id']) for p in profiles]
    cert = dict(format=1, artifactType='window-common-resource-plan', transitPackageId='p', planningVersion='h',
        scenario=deepcopy(source['scenario']), profileManifestSHA256='', sourceSHA256=deepcopy(source_hashes),
        modelCodeSHA256=codes.copy(), budget=dict(limitTRY=10000., referenceAnnualCostTRY=6050., hardConstraint=True),
        generation=dict(method='Synthetic complete window witness', runReportSHA256='c'*64, vectorSHA256='d'*64,
            candidateIndices=[0,1,2], optimizedProfiles=names[:12], validatedProfiles=names,
            searchProvenOptimal=False, minimumHospitalCountProven=False, annualDemandCountedOnce=True,
            sameIndividualsAcrossProfilesConstrained=False), plan=plan)
    w = dict(certificate=cert, data=data, health=health, matrices=matrices, published_reference=published,
        source_cost_certificate=source, current_source_hashes=source_hashes, package_id='p', manifest=manifest,
        manifest_sha256='', current_code_hashes=codes, indices_document=indices, baseline_matrices=baseline)
    recalc_manifest(w)
    return w


def test_44_clocks_one_annual_bill_and_generalized_overlap(window):
    r = a.validate_window_plan(**window)
    assert r['profileCount'] == 44 and len(r['profiles']) == 44
    assert r['annualEquivalentCostTRY'] == 6050 and r['annualMaterialCostTRY'] == 950
    assert r['sourceCostDeltaTRY'] == 0 and r['budgetSlackTRY'] == 3950
    assert r['conditionalOverlap']['province']['lowerPercent'] == 0
    assert r['conditionalOverlap']['province']['upperPercent'] == 90
    assert r['optimizedProfileIds'] == r['validatedProfileIds'][:12]
    assert r['allProfilesValidated'] and not r['solverRun']
    assert a.BASE_PROFILES == a.cost.PROFILES


def test_44_optimization_allowed_without_minimum_claim(window):
    window['certificate']['generation']['optimizedProfiles'] = window['certificate']['generation']['validatedProfiles'][:]
    assert len(a.validate_window_plan(**window)['optimizedProfileIds']) == 44


@pytest.mark.parametrize('mutation', [
    'pilot', 'incomplete', 'profile_clock', 'profile_offset_bool', 'profile_order', 'manifest_id', 'manifest_sha',
    'missing_matrix', 'matrix_nan', 'matrix_negative', 'matrix_bool', 'matrix_shape', 'matrix_baseline',
    'index_order', 'index_id', 'indices_digest', 'source_mismatch', 'frozen_code', 'code_hash', 'source_hash',
    'duplicate_path', 'path_escape', 'shape_bool', 'sample_bool', 'sample_none', 'sample_error',
    'fifo_missing', 'fifo_duplicate', 'fifo_count', 'fifo_violation', 'routing_horizon', 'status',
    'budget_reference', 'budget_increased', 'budget_false', 'budget_overrun', 'planning', 'scenario',
    'profile_missing', 'profile_duplicated', 'profile_reordered', 'flow_negative', 'flow_bool', 'flow_zero',
    'flow_duplicate', 'flow_closed', 'minutes', 'over45', 'province', 'district', 'doctor_capacity',
    'bed_capacity', 'total_beds', 'area', 'site_id', 'site_integer', 'maximum_load', 'material_44',
    'pool_missing_selected', 'pool_duplicate', 'pool_bool', 'pool_unknown', 'optimized_partial_block',
    'optimized_missing_initial', 'validated_incomplete', 'optimal_claim', 'flag_integer', 'extra_field'])
def test_strict_identity_schema_flow_resource_and_claim_rejections(window, mutation):
    c=window['certificate']; m=window['manifest']; p=c['plan']; g=c['generation']; flow=p['profiles'][8]['allocations'][0]
    if mutation=='pilot': m['mode']='pilot';m['status']='pilot_passed'
    elif mutation=='incomplete': m['producedProfileIds'].pop()
    elif mutation=='profile_clock':m['profiles'][8]['departureSeconds']+=60
    elif mutation=='profile_offset_bool':m['profiles'][0]['offsetMinutes']=False
    elif mutation=='profile_order':m['profiles'].reverse()
    elif mutation=='manifest_id':m['windowRoutingPackageId']='window-'+'0'*64
    elif mutation=='manifest_sha':c['profileManifestSHA256']='0'*64
    elif mutation=='missing_matrix':window['matrices'].pop('weekday-0805')
    elif mutation=='matrix_nan':window['matrices']['weekday-0805'][0,0]=np.nan
    elif mutation=='matrix_negative':window['matrices']['weekday-0805'][0,0]=-1
    elif mutation=='matrix_bool':window['matrices']['weekday-0805']=np.zeros((2,3),bool)
    elif mutation=='matrix_shape':window['matrices']['weekday-0805']=np.zeros((2,2))
    elif mutation=='matrix_baseline':window['matrices']['weekday-0800'][0,1]=12
    elif mutation=='index_order':window['indices_document']['candidates'].reverse()
    elif mutation=='index_id':window['indices_document']['origins'][0]['id']='wrong'
    elif mutation=='indices_digest':m['indices']['demandIndexSHA256']='0'*64
    elif mutation=='source_mismatch':m['sourceSHA256']['data/processed/dataset.json']='0'*64
    elif mutation=='frozen_code':m['frozenModelCodeLF_SHA256']['backend/joint_model.py']='0'*64
    elif mutation=='code_hash':c['modelCodeSHA256']['backend/window_model.py']='0'*64
    elif mutation=='source_hash':c['sourceSHA256']['dataset.json']='0'*64
    elif mutation=='duplicate_path':m['matrices'][8]['file']=m['matrices'][0]['file']
    elif mutation=='path_escape':m['matrices'][8]['file']='../wrong.npz'
    elif mutation=='shape_bool':m['matrices'][8]['shape']=[True,3]
    elif mutation=='sample_bool':m['matrices'][8]['audit']['independentOriginIndices']=[False,1]
    elif mutation=='sample_none':m['matrices'][8]['audit']['independentOriginIndices']=[]
    elif mutation=='sample_error':m['matrices'][8]['audit']['independentMaxMinutesError']=.1
    elif mutation=='fifo_missing':m['crossProfileAudit']['comparisons'].pop()
    elif mutation=='fifo_duplicate':m['crossProfileAudit']['comparisons'][-1]=deepcopy(m['crossProfileAudit']['comparisons'][0])
    elif mutation=='fifo_count':m['crossProfileAudit']['comparisons'][0]['commonFinitePairs']+=1
    elif mutation=='fifo_violation':window['matrices']['weekday-0805'][0,0]=1
    elif mutation=='routing_horizon':m['constants']['horizonSeconds']=7300
    elif mutation=='status':m['status']='partial'
    elif mutation=='budget_reference':c['budget']['referenceAnnualCostTRY']+=1
    elif mutation=='budget_increased':c['budget']['limitTRY']+=1
    elif mutation=='budget_false':c['budget']['hardConstraint']=1
    elif mutation=='budget_overrun':c['budget']['limitTRY']=window['published_reference']['capacity']['budgetLimitTRY']=6049.99
    elif mutation=='planning':c['planningVersion']='old'
    elif mutation=='scenario':c['scenario']['threshold']=46
    elif mutation=='profile_missing':p['profiles'].pop()
    elif mutation=='profile_duplicated':p['profiles'][-1]=deepcopy(p['profiles'][0])
    elif mutation=='profile_reordered':p['profiles'].reverse()
    elif mutation=='flow_negative':flow['population']=-1
    elif mutation=='flow_bool':flow['population']=True
    elif mutation=='flow_zero':flow['population']=0
    elif mutation=='flow_duplicate':p['profiles'][8]['allocations'].append(deepcopy(flow))
    elif mutation=='flow_closed':flow['candidateIndex']=1
    elif mutation=='minutes':flow['minutes']+=1
    elif mutation=='over45':window['matrices']['weekday-0805'][0,0]=46
    elif mutation=='province':flow['population']-=1
    elif mutation=='district':p['profiles'][8]['districts'][0]['coveragePercent']-=1
    elif mutation=='doctor_capacity':p['selected'][0]['doctors']=1;p['selected'][0]['grossAreaM2']=101;p['totalDoctors']=1
    elif mutation=='bed_capacity':window['health']['rates']['bedDaysPerResident']=100
    elif mutation=='total_beds':p['totalBeds']+=1
    elif mutation=='area':p['selected'][0]['grossAreaM2']+=1
    elif mutation=='site_id':p['selected'][0]['id']='unknown'
    elif mutation=='site_integer':p['selected'][0]['doctors']=10.5
    elif mutation=='maximum_load':p['selected'][0]['maximumAssignedPopulationAcrossProfiles']+=1
    elif mutation=='material_44':p['annualMaterialCostTRY']*=44
    elif mutation=='pool_missing_selected':g['candidateIndices']=[1,2]
    elif mutation=='pool_duplicate':g['candidateIndices']=[0,0,1]
    elif mutation=='pool_bool':g['candidateIndices']=[False,1,2]
    elif mutation=='pool_unknown':g['candidateIndices'].append(3)
    elif mutation=='optimized_partial_block':g['optimizedProfiles'].append(m['profiles'][12]['id'])
    elif mutation=='optimized_missing_initial':g['optimizedProfiles'].pop()
    elif mutation=='validated_incomplete':g['validatedProfiles']=g['validatedProfiles'][:12]
    elif mutation=='optimal_claim':g['searchProvenOptimal']=True
    elif mutation=='flag_integer':g['annualDemandCountedOnce']=1
    elif mutation=='extra_field':c['provenGlobalOptimal']=True
    if mutation not in ('manifest_id','manifest_sha'):recalc_manifest(window)
    with pytest.raises((ValueError,TypeError)):a.validate_window_plan(**window)


def test_positive_unloaded_site_still_costs_and_counts(window):
    c=window['certificate'];s=deepcopy(c['plan']['selected'][0]);s.update(candidateIndex=1,id='s1',doctors=1,grossAreaM2=101.,maximumAssignedPopulationAcrossProfiles=0.)
    c['plan']['selected'].append(s);update_cost(c,window['health'])
    r=a.validate_window_plan(**window)
    assert r['hospitalCount']==2 and r['annualEquivalentCostTRY']==9260 and r['budgetSlackTRY']==740


def test_json_duplicate_keys_and_nonfinite_rejected():
    for blob in (b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":Infinity}'):
        with pytest.raises(ValueError):a.load_json(blob)


def json_bytes(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()


def npz_bytes(**arrays):
    buffer=io.BytesIO();np.savez_compressed(buffer,**arrays);return buffer.getvalue()


@pytest.fixture
def saved_window(window,tmp_path,monkeypatch):
    root=tmp_path;processed=root/'data/processed';processed.mkdir(parents=True)
    folder=root/'work/window';folder.mkdir(parents=True)
    for name in set(a.MODEL_FILES)|set(a.ROUTING_CODE_FILES):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((a.ROOT/name).read_bytes())
    for name in a.ROUTING_SOURCE_FILES:
        if name.startswith('data/processed/'): (root/name).write_bytes(json_bytes({'opaque':'routing source'}))
    for name,value in [('dataset.json',window['data']),('health-planning.json',window['health']),
                       ('example-transit-result.json',window['published_reference'])]:
        (processed/name).write_bytes(json_bytes(value))
    for name,matrix in window['baseline_matrices'].items():
        (processed/f'transit-{name}-matrix.npz').write_bytes(npz_bytes(minutes=matrix))
    hashes={name:a.sha256((processed/name).read_bytes()) for name in a.cost.SOURCE_FILES}
    source=deepcopy(window['source_cost_certificate']);source['sourceSHA256']=hashes
    (processed/'joint-plan.json').write_bytes(json_bytes(source));window['source_cost_certificate']=source
    current={name:a.sha256((processed/name).read_bytes()) for name in a.SOURCE_FILES}
    archived_matrices=npz_bytes(originIndices=np.arange(2),targetCandidateIndices=np.arange(3),
        minutes0800=window['matrices']['weekday-0800'],minutes0805=window['matrices']['weekday-0805'])
    old=dict(transitPackageId='p',arraysSHA256=a.sha256(archived_matrices),
        sourceSHA256={Path(name).name:a.sha256((root/name).read_bytes()) for name in a.ROUTING_SOURCE_FILES if name.startswith('data/processed/')},
        profiles={'0800':{'day':'weekday','startSeconds':28800},'0805':{'day':'weekday','startSeconds':29100}},
        origins=[dict(index=i, id=d['id'], population=d['population'], districtId=d['districtId'])
                 for i,d in enumerate(window['data']['demands'])],targets=window['indices_document']['candidates'])
    old_bytes=json_bytes(old);zip_path=root/'docs/experiments/departure-0805-evidence.zip';zip_path.parent.mkdir(parents=True)
    with ZipFile(zip_path,'w') as z:
        z.writestr('work/referees/profile-shift-full-v07.npz',archived_matrices)
        z.writestr('work/referees/profile-shift-full-v07.json',old_bytes)
    manifest=window['manifest'];manifest['sourceSHA256']={name:a.sha256((root/name).read_bytes()) for name in a.ROUTING_SOURCE_FILES}
    manifest['routingCodeLF_SHA256']={name:a.sha256((root/name).read_bytes().replace(b'\r\n',b'\n')) for name in a.ROUTING_CODE_FILES}
    codes=a.code_hashes(root);manifest['frozenModelCodeLF_SHA256']={name:codes[name] for name in a.FROZEN_MODEL_FILES}
    manifest['archived0805']['matrixSHA256']=a.sha256(archived_matrices);manifest['archived0805']['reportSHA256']=a.sha256(old_bytes)
    index_bytes=json_bytes(window['indices_document']);(folder/'indices.json').write_bytes(index_bytes)
    manifest['indices']['sha256']=a.sha256(index_bytes)
    for row in manifest['matrices']:
        blob=npz_bytes(minutes=window['matrices'][row['profileId']]);(folder/row['file']).write_bytes(blob);row['sha256']=a.sha256(blob)
    manifest['windowRoutingPackageId']=a.routing_package_id(manifest);manifest_bytes=json_bytes(manifest)
    path=folder/'manifest.json';path.write_bytes(manifest_bytes)
    cert=window['certificate'];cert['sourceSHA256']=current;cert['modelCodeSHA256']=codes;cert['profileManifestSHA256']=a.sha256(manifest_bytes)
    (folder/'window-plan.json').write_bytes(json_bytes(cert))
    monkeypatch.setattr(a,'check_package',lambda root:'p')
    return root,path,folder/'window-plan.json'


def test_readonly_reader_and_certificate_roundtrip(saved_window):
    root,manifest,cert=saved_window
    before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
    r=a.audit_saved_window_plan(cert,manifest,root,verify_artifacts=False)
    assert r['profileCount']==44 and r['annualEquivalentCostTRY']==6050
    assert before=={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('field',['data','health','source_cost_certificate','manifest','indices_document','matrices','baseline_matrices'])
def test_loaded_input_memory_mutation_rejected(saved_window,field):
    root,path,_=saved_window;loaded=a.read_window_inputs(path,root)
    if field in ('matrices','baseline_matrices'):
        key=next(iter(loaded[field]));changed=loaded[field][key].copy();changed[0,0]+=1;loaded[field][key]=changed
    else:loaded[field]['new_untrusted_field']=True
    with pytest.raises(ValueError,match='memory|matrix'):a.unchanged_window_inputs(loaded,root)


@pytest.mark.parametrize('kind',['matrix','source','code','manifest','indices'])
def test_entry_exit_file_mutation_rejected(saved_window,kind):
    root,path,_=saved_window;loaded=a.read_window_inputs(path,root)
    target={'matrix':path.parent/'weekday-0805.npz','source':root/'data/processed/dataset.json',
            'code':root/'backend/window_model.py','manifest':path,'indices':path.parent/'indices.json'}[kind]
    target.write_bytes(target.read_bytes()+b' ')
    with pytest.raises(ValueError):a.unchanged_window_inputs(loaded,root)


@pytest.mark.parametrize('kind',['matrix','indices','source','routing_code','loaded_audit_code','archive'])
def test_reader_rejects_tampered_files_before_acceptance(saved_window,kind):
    root,path,_=saved_window
    target={'matrix':path.parent/'weekday-0805.npz','indices':path.parent/'indices.json',
            'source':root/'data/processed/dataset.json','routing_code':root/'backend/window_routing.py',
            'loaded_audit_code':root/'scripts/audit_window_plan.py',
            'archive':root/'docs/experiments/departure-0805-evidence.zip'}[kind]
    target.write_bytes(target.read_bytes()+b' ')
    with pytest.raises(ValueError):a.read_window_inputs(path,root)


@pytest.mark.parametrize('kind',['population','districtId','missing_population','boolean_population','index','id'])
def test_archived_origin_full_identity_is_checked_even_with_refreshed_hash(saved_window,window,kind):
    root,path,_=saved_window
    manifest=json.loads(path.read_bytes()); ref=manifest['archived0805']; archive=root/ref['archive']
    with ZipFile(archive) as z: members={name:z.read(name) for name in z.namelist()}
    report=json.loads(members[ref['reportMember']]); origin=report['origins'][0]
    if kind=='population':origin['population']+=1
    elif kind=='districtId':origin['districtId']='wrong'
    elif kind=='missing_population':del origin['population']
    elif kind=='boolean_population':origin['population']=True
    elif kind=='index':origin['index']=1
    else:origin['id']='wrong'
    members[ref['reportMember']]=json_bytes(report)
    with ZipFile(archive,'w') as z:
        for name,blob in members.items():z.writestr(name,blob)
    ref['reportSHA256']=a.sha256(members[ref['reportMember']])
    with pytest.raises(ValueError,match='ordered report identities'):
        a._verify_archived_subset(root,manifest,window['matrices'],window['data'])


@pytest.fixture
def explicit_pool(window):
    return dict(format=1,candidateIndices=[0,1,2],method='Deterministic search expansion; no optimality claim',
        sourceSHA256=deepcopy(window['current_source_hashes']),profileManifestSHA256=window['manifest_sha256'])


def test_explicit_pool_is_bound_to_sources_and_contains_seed(window,explicit_pool):
    assert a.validate_explicit_candidate_pool(explicit_pool,window,[0,2],[0,1,2])==[0,1,2]
    assert explicit_pool['candidateIndices']==[0,1,2]


@pytest.mark.parametrize('kind',['bool_format','extra','missing_method','empty_method','missing_source','stale_source',
    'stale_manifest','bool_index','float_index','negative_index','outside_index','duplicate_index','unsorted',
    'empty','missing_seed','generation_mismatch'])
def test_explicit_pool_rejects_identity_and_scope_mutations(window,explicit_pool,kind):
    expected=[0,1,2];seed=[0,2]
    if kind=='bool_format':explicit_pool['format']=True
    elif kind=='extra':explicit_pool['globalOptimumProven']=True
    elif kind=='missing_method':del explicit_pool['method']
    elif kind=='empty_method':explicit_pool['method']=''
    elif kind=='missing_source':explicit_pool['sourceSHA256'].pop('joint-plan.json')
    elif kind=='stale_source':explicit_pool['sourceSHA256']['joint-plan.json']='e'*64
    elif kind=='stale_manifest':explicit_pool['profileManifestSHA256']='f'*64
    elif kind=='bool_index':explicit_pool['candidateIndices']=[False,1,2]
    elif kind=='float_index':explicit_pool['candidateIndices']=[0.,1,2]
    elif kind=='negative_index':explicit_pool['candidateIndices']=[-1,0,2]
    elif kind=='outside_index':explicit_pool['candidateIndices']=[0,2,3]
    elif kind=='duplicate_index':explicit_pool['candidateIndices']=[0,0,2]
    elif kind=='unsorted':explicit_pool['candidateIndices']=[2,1,0]
    elif kind=='empty':explicit_pool['candidateIndices']=[]
    elif kind=='missing_seed':explicit_pool['candidateIndices']=[0,1]
    else:expected=[0,2]
    with pytest.raises(ValueError):a.validate_explicit_candidate_pool(explicit_pool,window,seed,expected)


@pytest.fixture
def explicit_run_bundle(saved_window):
    root,path,cert_path=saved_window; inputs=a.read_window_inputs(path,root)
    cert=json.loads(cert_path.read_bytes());folder=cert_path.parent
    cert['generation']['optimizedProfiles']=cert['generation']['validatedProfiles'].copy()
    pool=dict(format=1,candidateIndices=cert['generation']['candidateIndices'],method='Synthetic explicit expansion',
              sourceSHA256=inputs['current_source_hashes'],profileManifestSHA256=inputs['manifest_sha256'])
    pool_blob=json_bytes(pool);(folder/'candidate-pool.json').write_bytes(pool_blob)
    seed_blob=(root/'data/processed/joint-plan.json').read_bytes();(folder/'resource-seed.json').write_bytes(seed_blob)
    (folder/'solver.log').write_bytes(b'No native test execution\n')
    vector,layout=a.reconstruct_saved_vector(cert,inputs)
    vector_blob=npz_bytes(finalOriginalVector=vector,costStageOriginalVector=vector,
                         costStageNativeValidatedVector=vector)
    (folder/'vectors.npz').write_bytes(vector_blob)
    result=dict(deepcopy(cert['plan']),feasible=True,incumbentValidated=True,status='feasible',
        hardBudgetConstraint=True,hardAnnualBudgetTRY=cert['budget']['limitTRY'],annualDemandCountedOnce=True,
        minimumHospitalCountProven=False,boundScope='supplied_candidate_pool_and_exact_named_profile_set',
        boundCandidateIndices=pool['candidateIndices'],profileIds=cert['generation']['optimizedProfiles'],
        profileCount=44,nativeBoundIndependentlyCertified=False,minimumAnnualCostLowerBoundTRY=None,costGap=None)
    report=dict(format=1,artifactType='departure-window-cost-run',transitPackageId=inputs['package_id'],
        profileManifestSHA256=inputs['manifest_sha256'],sourceSHA256=inputs['current_source_hashes'],
        modelCodeSHA256=inputs['current_code_hashes'],candidateIndices=pool['candidateIndices'],
        optimizedProfiles=cert['generation']['optimizedProfiles'],validatedProfiles=cert['generation']['validatedProfiles'],
        fullCandidateCount=len(inputs['data']['candidates']),
        boundScope='Only this candidate pool and these 44 named matrices; no global or minimum-count proof',
        result=result,vectorSHA256=a.sha256(vector_blob),resourceSeedSHA256=a.sha256(seed_blob),
        solverLogSHA256=a.sha256((folder/'solver.log').read_bytes()),
        seedResourceAudit='frozen_four_profile_independent_auditor',candidatePool='explicit',
        candidatePoolSHA256=a.sha256(pool_blob),dimensions=dict(layout,variables=len(vector)))
    cert['generation']['vectorSHA256']=report['vectorSHA256']
    report_blob=json_bytes(report);(folder/'run-result.json').write_bytes(report_blob)
    cert['generation']['runReportSHA256']=a.sha256(report_blob)
    cert_path.write_bytes(json_bytes(cert))
    return root,path,cert_path,inputs,report


def test_explicit_saved_artifact_roundtrip(explicit_run_bundle):
    root,path,cert,_,report=explicit_run_bundle
    result=a.audit_saved_window_plan(cert,path,root)
    assert result['runArtifactAudit']['candidatePool']=='explicit'
    assert result['runArtifactAudit']['candidatePoolSHA256']==report['candidatePoolSHA256']


@pytest.mark.parametrize('kind',['missing_file','changed_bytes','hash_missing','hash_wrong','pool_generation_mismatch','omitted_seed','stale_source','stale_manifest'])
def test_explicit_saved_artifact_tamper_rejected(explicit_run_bundle,kind):
    root,path,cert_path,_,report=explicit_run_bundle;folder=cert_path.parent
    pool_path=folder/'candidate-pool.json';pool=json.loads(pool_path.read_bytes())
    if kind=='missing_file':pool_path.unlink()
    elif kind=='changed_bytes':pool_path.write_bytes(pool_path.read_bytes()+b' ')
    elif kind=='hash_missing':report.pop('candidatePoolSHA256')
    elif kind=='hash_wrong':report['candidatePoolSHA256']='f'*64
    else:
        if kind=='pool_generation_mismatch':pool['candidateIndices']=[0,2]
        elif kind=='omitted_seed':pool['candidateIndices']=[1,2]
        elif kind=='stale_source':pool['sourceSHA256']['joint-plan.json']='f'*64
        else:pool['profileManifestSHA256']='f'*64
        blob=json_bytes(pool);pool_path.write_bytes(blob);report['candidatePoolSHA256']=a.sha256(blob)
    report_blob=json_bytes(report);(folder/'run-result.json').write_bytes(report_blob)
    cert=json.loads(cert_path.read_bytes());cert['generation']['runReportSHA256']=a.sha256(report_blob)
    cert_path.write_bytes(json_bytes(cert))
    with pytest.raises((ValueError,FileNotFoundError)):a.audit_saved_window_plan(cert_path,path,root)


def bind_adaptive(bundle,seed=None):
    root,path,cert_path,inputs,report=bundle; folder=cert_path.parent; directory=folder/'seed-preparation'
    if seed is not None:
        for name in seed['artifacts']:seed['artifacts'][name]=a.sha256((directory/name).read_bytes())
        (directory/'seed-preparation.json').write_bytes(json_bytes(seed))
    report['adaptiveSeedPreparationSHA256']=a.sha256((directory/'seed-preparation.json').read_bytes())
    report['vectorSHA256']=a.sha256((folder/'vectors.npz').read_bytes())
    report_blob=json_bytes(report);(folder/'run-result.json').write_bytes(report_blob)
    cert=json.loads(cert_path.read_bytes());cert['generation']['runReportSHA256']=a.sha256(report_blob)
    cert['generation']['vectorSHA256']=report['vectorSHA256'];cert_path.write_bytes(json_bytes(cert))


@pytest.fixture
def adaptive_run_bundle(explicit_run_bundle):
    bundle=explicit_run_bundle;root,path,cert_path,inputs,report=bundle
    folder=cert_path.parent; directory=folder/'seed-preparation';directory.mkdir()
    cert=json.loads(cert_path.read_bytes()); names=cert['generation']['validatedProfiles']; active=names[:12]
    complete=dict(deepcopy(cert['plan']),minimumAnnualCostLowerBoundTRY=None,costGap=None,provenOptimal=False)
    subset=deepcopy(cert);subset['plan']['profiles']=subset['plan']['profiles'][:12]
    partial,partial_layout=a.reconstruct_saved_vector(subset,inputs)
    vector,_=a.reconstruct_saved_vector(cert,inputs)
    rows=[dict(profile=name,status='checked_same_named_flow_reused' if name in active else 'profile_primal_checked',
               accepted=True,nativeStatus=None if name in active else 0) for name in names]
    diagnostic=dict(status='complete_44_seed_primal_checked',feasible=True,profiles=rows,failedProfileIds=[],
        modelInfeasibilityProven=False,resourcesUnchanged=True,annualDemandCountedOnce=True,
        sameNamedFlowsReused=active,oldProfilesRelabelled=False,elapsedSeconds=.1)
    stage=dict(stage=1,optimizedProfileIds=active,candidateIndices=cert['generation']['candidateIndices'],
        dimensions=dict(profiles=12,variables=len(partial)),resourceSeedPreparation={'status':'synthetic'},
        costResult=dict(deepcopy(subset['plan']),feasible=True),costStageElapsedSeconds=.1,cooperativeCostStageOverrunSeconds=0.,
        boundScope='Only this stage candidate pool and named profile subset; never copied into the final full-window cost bound.')
    (directory/'stage-01-cost.json').write_bytes(json_bytes(stage))
    (directory/'stage-01-cost-vectors.npz').write_bytes(npz_bytes(finalOriginalVector=partial))
    (directory/'stage-01-completion.json').write_bytes(json_bytes(diagnostic))
    (directory/'stage-01-completion-vectors.npz').write_bytes(npz_bytes(complete44Vector=vector))
    stage['fullWindowCompletion']=diagnostic
    seed=dict(format=1,artifactType='window-seed-preparation',status='complete_window_seed_prepared',feasible=True,
        fullProfileIds=names,candidateIndices=cert['generation']['candidateIndices'],hardAnnualBudgetTRY=10000.,
        referenceAnnualCostTRY=6050.,annualDemandCountedOnce=True,outerHardTimeoutRequired=True,
        independentFinalAuditRequired=True,globalInfeasibilityProven=False,globalOptimalityProven=False,
        profileSubsetBoundsTransferred=False,modelSignature='a'*64,
        helperCodeSHA256=inputs['current_code_hashes']['backend/window_seed.py'],
        callerSourceBindings=dict(sourceSHA256=inputs['current_source_hashes'],modelCodeSHA256=inputs['current_code_hashes'],
            profileManifestSHA256=inputs['manifest_sha256'],resourceSeedSHA256=report['resourceSeedSHA256'],
            candidatePoolSHA256=report['candidatePoolSHA256']),stages=[stage],
        artifacts={p.name:a.sha256(p.read_bytes()) for p in directory.iterdir()},completeSeedPlan=complete)
    report['result'].update(nativeRunStarted=True,costStagePerformed=True,
                           warmStart=dict(completeStartSupplied=True,solverAcceptedFeasibleStart=True))
    (folder/'vectors.npz').write_bytes(npz_bytes(finalOriginalVector=vector,costStageOriginalVector=vector,
        costStageNativeValidatedVector=vector,suppliedOriginalVector=vector))
    bind_adaptive(bundle,seed)
    return bundle,seed


def test_adaptive_complete_seed_source_vector_and_decimal_bill(adaptive_run_bundle):
    (root,path,cert,_,_),_=adaptive_run_bundle
    result=a.audit_saved_window_plan(cert,path,root)['runArtifactAudit']['adaptiveSeedAudit']
    assert result['completeSeedIndependentlyValidated'] and result['profileCount']==44
    assert a.D(result['decimalAnnualEquivalentCostTRY'])==a.D('6050')
    assert not result['partialStageBoundsTransferred'] and not result['partialStageOptimalityIndependentlyCertified']


@pytest.mark.parametrize('kind',['helper_hash','source_binding','code_binding','manifest_binding','seed_binding','pool_binding',
    'global_optimal','subset_bound','partial_status','missing_profile','wrong_flow','extra_doctor','wrong_material',
    'complete_bound','native_not_started','cost_not_started','warm_not_supplied','warm_not_accepted',
    'report_profile_scope','file_missing','file_changed','file_unlisted','escaping_artifact',
    'completion_vector','main_supplied_vector','main_supplied_missing','cost_vector_shape','completion_partial_label'])
def test_adaptive_seed_fails_closed_after_refreshing_outer_hashes(adaptive_run_bundle,kind):
    bundle,seed=adaptive_run_bundle;root,path,cert_path,inputs,report=bundle
    folder=cert_path.parent; directory=folder/'seed-preparation'
    if kind=='helper_hash':seed['helperCodeSHA256']='f'*64
    elif kind=='source_binding':seed['callerSourceBindings']['sourceSHA256']=dict(seed['callerSourceBindings']['sourceSHA256'],**{'joint-plan.json':'f'*64})
    elif kind=='code_binding':seed['callerSourceBindings']['modelCodeSHA256']=dict(seed['callerSourceBindings']['modelCodeSHA256'],**{'backend/window_seed.py':'f'*64})
    elif kind=='manifest_binding':seed['callerSourceBindings']['profileManifestSHA256']='f'*64
    elif kind=='seed_binding':seed['callerSourceBindings']['resourceSeedSHA256']='f'*64
    elif kind=='pool_binding':seed['callerSourceBindings']['candidatePoolSHA256']='f'*64
    elif kind=='global_optimal':seed['globalOptimalityProven']=True
    elif kind=='subset_bound':seed['profileSubsetBoundsTransferred']=True
    elif kind=='partial_status':seed['status']='seed_preparation_inconclusive';seed['feasible']=None
    elif kind=='missing_profile':seed['completeSeedPlan']['profiles'].pop()
    elif kind=='wrong_flow':seed['completeSeedPlan']['profiles'][8]['allocations'][0]['population']+=1
    elif kind=='extra_doctor':seed['completeSeedPlan']['selected'][0]['doctors']+=1
    elif kind=='wrong_material':seed['completeSeedPlan']['annualMaterialCostTRY']*=44
    elif kind=='complete_bound':seed['completeSeedPlan']['minimumAnnualCostLowerBoundTRY']=1
    elif kind=='native_not_started':report['result']['nativeRunStarted']=False
    elif kind=='cost_not_started':report['result']['costStagePerformed']=False
    elif kind=='warm_not_supplied':report['result']['warmStart']['completeStartSupplied']=False
    elif kind=='warm_not_accepted':report['result']['warmStart']['solverAcceptedFeasibleStart']=False
    elif kind=='report_profile_scope':report['optimizedProfiles']=report['optimizedProfiles'][:12]
    elif kind=='file_missing':(directory/'stage-01-cost.json').unlink()
    elif kind=='file_changed':(directory/'stage-01-cost.json').write_bytes(b'{}')
    elif kind=='file_unlisted':(directory/'extra.json').write_bytes(b'{}')
    elif kind=='escaping_artifact':seed['artifacts']['../run-result.json']='f'*64
    elif kind in ('completion_vector','completion_partial_label'):
        with np.load(directory/'stage-01-completion-vectors.npz') as z:v=z['complete44Vector'].copy()
        if kind=='completion_vector':v[-1]+=.01
        (directory/'stage-01-completion-vectors.npz').write_bytes(npz_bytes(**{('unvalidatedPartial44Vector' if kind=='completion_partial_label' else 'complete44Vector'):v}))
    elif kind=='cost_vector_shape':(directory/'stage-01-cost-vectors.npz').write_bytes(npz_bytes(finalOriginalVector=np.zeros(1)))
    else:
        with np.load(folder/'vectors.npz') as z:arrays={name:z[name].copy() for name in z.files}
        if kind=='main_supplied_vector':arrays['suppliedOriginalVector'][-1]+=.01
        else:del arrays['suppliedOriginalVector']
        (folder/'vectors.npz').write_bytes(npz_bytes(**arrays))
    if kind in ('file_missing','escaping_artifact'):
        (directory/'seed-preparation.json').write_bytes(json_bytes(seed));bind_adaptive(bundle)
    else:bind_adaptive(bundle,seed)
    with pytest.raises((ValueError,FileNotFoundError,KeyError)):a.audit_saved_window_plan(cert_path,path,root)
