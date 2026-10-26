from copy import deepcopy
from datetime import datetime
import json
import math
import numpy as np
import pytest
from backend import motis
from scripts import build_motis_matrices as build


def encode(points, precision=6):
    result='';last=[0,0]
    for point in points:
        for j,value in enumerate(point):
            v=round(value*10**precision);delta=v-last[j];last[j]=v
            n=~(delta<<1) if delta<0 else delta<<1
            while n>=32:result+=chr((32|(n&31))+63);n>>=5
            result+=chr(n+63)
    return result


def itinerary(begin='2026-10-27T05:02:00Z',end='2026-10-27T05:12:00Z',mode='BUS'):
    return {'startTime':begin,'endTime':end,'legs':[{'startTime':begin,'endTime':end,'mode':mode,
        'legGeometry':{'points':encode([(39.9,32.8),(39.91,32.81)]),'precision':6},
        'routeShortName':'X','tripId':'trip','from':{'name':'A'}}]}


def test_initial_wait_and_connectors_are_total_elapsed_not_itinerary_duration():
    response={'direct':[],'itineraries':[itinerary()]}
    result=motis.interpret_response(response,'weekday-0800',31,150)
    assert result['minutes']==14
    assert result['motorQueryTime']=='2026-10-27T05:01:00+00:00'
    assert result['initialWaitAfterQueryMinutes']==1
    assert result['queryCeilingWaitMinutes']==pytest.approx((60-31/1.25)/60)
    assert result['destinationConnectorMinutes']==2


def test_origin_connector_moves_query_before_search_not_after():
    p=motis.plan_parameters((39.9,32.8),(40,33),'weekday-0800',75.001)
    assert p['time']=='2026-10-27T05:02:00Z'
    bad=motis.interpret_response({'direct':[],'itineraries':[itinerary('2026-10-27T05:01:00Z')]},'weekday-0800',75.001)
    assert bad['status']=='unknown'


@pytest.mark.parametrize('v',[True,False,'1',float('nan'),float('inf'),-1])
def test_invalid_connectors(v):
    with pytest.raises(ValueError):motis.start_times('weekday-0800',v)


def test_dated_weekend_profiles_not_clock_only():
    assert motis.start_times('saturday-1000')[0].isoformat()=='2026-10-31T10:00:00+03:00'
    assert motis.start_times('sunday-1000')[0].isoformat()=='2026-11-01T10:00:00+03:00'


@pytest.mark.parametrize('mode',['CAR','CAR_PARKING','BICYCLE','ODM','UNKNOWN'])
def test_forbidden_mode_is_unknown(mode):
    r=motis.interpret_response({'direct':[],'itineraries':[itinerary(mode=mode)]},'weekday-0800')
    assert r['status']=='unknown' and r['minutes'] is None


def test_earliest_arrival_not_first_or_shortest_duration():
    a=itinerary('2026-10-27T05:10:00Z','2026-10-27T05:13:00Z')
    b=itinerary('2026-10-27T05:02:00Z','2026-10-27T05:12:00Z')
    r=motis.interpret_response({'direct':[],'itineraries':[a,b]},'weekday-0800')
    assert r['minutes']==12


def test_empty_is_unknown_never_a_proof_of_no_service():
    r=motis.interpret_response({'direct':[],'itineraries':[]},'weekday-0800')
    assert r['status']=='unknown' and r['minutes'] is None


def test_no_fabricated_straight_geometry():
    x=itinerary();del x['legs'][0]['legGeometry']
    assert motis.interpret_response({'direct':[],'itineraries':[x]},'weekday-0800')['status']=='unknown'


def test_polyline_output_is_longitude_latitude():
    assert motis.decode_polyline({'precision':6,'points':encode([(39.9,32.8),(40,33)])})==[[32.8,39.9],[33,40]]


@pytest.mark.parametrize('g',[{'precision':6,'points':'_'},{'precision':True,'points':'??'}, {'precision':6,'points':''}])
def test_malformed_polyline(g):
    with pytest.raises(ValueError):motis.decode_polyline(g)


def test_external_service_never_used(monkeypatch):
    monkeypatch.setattr(motis,'BASE_URL','https://api.transitous.org')
    with pytest.raises(ValueError):motis.request_json('/api/v6/plan')


def test_bulk_values_only_choose_shortlist_car_union_and_class():
    b=np.array([1,2,3,np.inf,10,20.]);c=np.array([9,8,1,0,20,10.]);r=np.array([45,45,45,45,80,80])
    assert build.shortlist_indices(b,c,r,1)==[0,3,4,5]


def test_physical_entry_aliases_use_one_query_and_individual_connectors(monkeypatch):
    data={'demands':[{'id':'D','node':0,'snapMeters':0}], 'candidates':[
        {'id':'A','node':1,'entryLat':40,'entryLon':33,'accessMeters':75,'footprintRadiusMeters':45},
        {'id':'B','node':1,'entryLat':40,'entryLon':33,'accessMeters':150,'footprintRadiusMeters':80}], 'hospitals':[{'id':'H'}]}
    coords=np.array([[32,39],[33,40]]);entries,groups,mapping=build.entry_groups(data['candidates'],coords)
    calls=[]
    monkeypatch.setattr(build,'bulk_scores',lambda *a:(np.array([100.]),[]))
    def query(*a):
        calls.append(a);return {'status':'computed','minutes':10,'motorQueryTime':'x','providerArrivalTime':'y','boardings':[]}
    monkeypatch.setattr(motis,'query_plan',query)
    _,row,mask,_=build.calculate_row(0,'weekday-0800',data,coords,np.array([[1.,2.,3.]]),entries,groups,mapping,2000,12)
    assert len(calls)==1 and row.tolist()[:2]==[11,12]
    assert mask.tolist()==[True,True,False] and math.isinf(row[2])


def test_provider_failure_remains_queried_unknown(monkeypatch):
    data={'demands':[{'id':'D','node':0,'snapMeters':0}], 'candidates':[
        {'id':'A','node':0,'accessMeters':0,'footprintRadiusMeters':45}], 'hospitals':[]}
    coords=np.array([[32,39]]);entries,groups,mapping=build.entry_groups(data['candidates'],coords)
    monkeypatch.setattr(build,'bulk_scores',lambda *a:(np.array([1.]),[]))
    def fail(*a):raise motis.MotisUnavailable('offline')
    monkeypatch.setattr(motis,'query_plan',fail)
    _,row,mask,report=build.calculate_row(0,'weekday-0800',data,coords,np.array([[1.]]),entries,groups,mapping,2000,12)
    assert mask[0] and math.isinf(row[0]) and len(report['planErrors'])==1


def test_atomic_temp_does_not_follow_predictable_hardlink(tmp_path):
    import os
    source=tmp_path/'source.json';source.write_text('SOURCE')
    target=tmp_path/'target.json';os.link(source,tmp_path/'target.json.tmp')
    build.atomic_bytes(target,b'OUTPUT')
    assert source.read_text()=='SOURCE' and target.read_bytes()==b'OUTPUT'


@pytest.fixture
def cached_package(tmp_path,monkeypatch):
    import hashlib
    root=tmp_path;data=root/'data/processed';out=data/'motis';out.mkdir(parents=True)
    dataset={'demands':[{'id':'D'}],'candidates':[{'id':'C'}],'hospitals':[{'id':'H'}]}
    (data/'dataset.json').write_text(json.dumps(dataset),encoding='utf-8')
    np.save(data/'graph-coordinates.npy',np.array([[32.,39.]]))
    np.savez(data/'car-matrix.npz',minutes=np.array([[1.,2.]],dtype=np.float32))
    for file in ('backend/motis.py','scripts/build_motis_matrices.py'):
        path=root/file;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('CODE')
    monkeypatch.setattr(motis,'ROOT',root);monkeypatch.setattr(motis,'DATA',data);monkeypatch.setattr(motis,'MATRIX_DIR',out)
    refs={key:str(path.relative_to(root)).replace('\\','/') for key,path in {
        'dataset':data/'dataset.json','graphCoordinates':data/'graph-coordinates.npy','carMatrix':data/'car-matrix.npz'}.items()}
    for key in ('sourceManifest','config','runtimeConfig','GTFS','OSM','engine','imported/tt.bin','imported/osr/routing.bin'):
        refs[key]='work/missing/'+key
    hashes={key:motis.file_sha(root/path) if (root/path).exists() else 'a'*64 for key,path in refs.items()}
    indices={key:[str(x['id']) for x in dataset[key]] for key in ('demands','candidates','hospitals')}
    np.savez_compressed(out/'weekday-0800-matrix.npz',minutes=np.array([[12,np.inf]],dtype=np.float32),queried=np.array([[True,False]]))
    record={'file':'weekday-0800-matrix.npz','sha256':motis.file_sha(out/'weekday-0800-matrix.npz'),
            'shape':[1,2],'computedCount':1,'queriedCount':1,'unknownQueriedCount':0,'unqueriedCount':1}
    value={'policyVersion':motis.POLICY_VERSION,'scenario':motis.SCENARIO,'planParameters':motis.PLAN_PARAMETERS,
           'profiles':motis.PROFILES,'sourceFiles':refs,'sourceSHA256':hashes,'codeLF_SHA256':motis.model_codes(),
           'indices':indices,'indexSHA256':hashlib.sha256(motis.canonical(indices)).hexdigest(),
           'matrices':{'weekday-0800':record},'searchScope':{'kind':'restricted_edges'}}
    def save():
        value.pop('packageId',None);value['packageId']='motis-'+hashlib.sha256(motis.canonical(value)).hexdigest()
        (out/'manifest.json').write_bytes(motis.canonical(value));motis._validated_manifest.cache_clear();motis._load.cache_clear()
    save();yield root,data,out,value,save
    motis._validated_manifest.cache_clear();motis._load.cache_clear()


def test_cached_matrix_without_local_raw_import_is_usable(cached_package):
    assert motis.load_matrix('weekday-0800')[0,0]==12
    evidence=motis.evidence('weekday-0800')
    assert evidence['existingComparisonAvailable'] is False
    assert evidence['allCandidateInfeasibilityProofAllowed'] is False
    with pytest.raises(motis.MotisUnavailable):motis.require_live_sources()


def test_offline_ready_one_available_profile(cached_package,monkeypatch):
    def fail(*a,**k):raise motis.MotisUnavailable('offline')
    monkeypatch.setattr(motis,'request_json',fail)
    result=motis.routing_status()
    assert result['ready'] is True and result['serviceAvailable'] is False
    assert result['matrixProfiles']==['weekday-0800']


def test_present_runtime_source_mismatch_fails(cached_package):
    root,data,out,value,save=cached_package
    p=root/value['sourceFiles']['GTFS'];p.parent.mkdir(parents=True,exist_ok=True);p.write_text('WRONG')
    with pytest.raises(ValueError,match='source changed'):motis.load_matrix('weekday-0800')


def test_packaged_dataset_mutation_fails(cached_package):
    root,data,out,value,save=cached_package
    (data/'dataset.json').write_text('{}')
    with pytest.raises(ValueError,match='source changed'):motis.load_matrix('weekday-0800')


def test_index_identity_cannot_be_relabelled(cached_package):
    root,data,out,value,save=cached_package
    value['indices']['candidates']=['OTHER'];save()
    with pytest.raises(ValueError,match='ordering mismatch'):motis.load_matrix('weekday-0800')


@pytest.mark.parametrize('minutes,mask',[(np.nan,True),(-1,True),(121,True),(12,False)])
def test_bad_matrix_values_or_unqueried_finite_fail(cached_package,minutes,mask):
    root,data,out,value,save=cached_package
    p=out/'weekday-0800-matrix.npz';np.savez_compressed(p,minutes=np.array([[minutes,np.inf]],dtype=np.float32),queried=np.array([[mask,False]]))
    value['matrices']['weekday-0800']['sha256']=motis.file_sha(p);save()
    with pytest.raises(ValueError):motis.load_matrix('weekday-0800')


def test_runtime_identity_cannot_be_removed_from_manifest(cached_package):
    root,data,out,value,save=cached_package
    del value['sourceFiles']['imported/tt.bin'];del value['sourceSHA256']['imported/tt.bin'];save()
    with pytest.raises(ValueError,match='incomplete'):motis.load_matrix('weekday-0800')


def test_path_escape_rejected(cached_package):
    root,data,out,value,save=cached_package
    value['sourceFiles']['GTFS']='../../somewhere';save()
    with pytest.raises(ValueError,match='escapes'):motis.load_matrix('weekday-0800')
