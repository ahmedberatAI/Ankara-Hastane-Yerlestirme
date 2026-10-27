"""Precomputed route publication rejects missing, mixed or corrupt records."""
from copy import deepcopy
import json
import pytest
from scripts import publication as p


@pytest.fixture
def fixture():
    plan = {'planId':'permanent-'+'a'*64, 'criticalTransitProfile':'weekday-1000',
        'identity':{'transitPackageId':'motis-'+'c'*64}, 'policy':{'threshold':30,'transitThreshold':60},
        'scenario':{'mode':'hybrid','transitEngine':'motis','trafficFactor':1,'hospitalLimit':None}}
    plan['profiles'] = {name:{'assignments':[{'demandId':'D','allocations':[{'candidateId':'C','population':95,'minutes':minutes}]}]}
        for name,minutes in [('car',10),('weekday-1000',40)]}
    request, allocation = p.requests_for(plan)['transit/D/C']
    response = {'planId':plan['planId'],'profileId':'weekday-1000','routeMode':'transit','minutes':40,
        'scenario':{**plan['scenario'],'demandId':'D','candidateId':'C','routeMode':'transit','routingPackageId':plan['identity']['transitPackageId']},
        'evidence':{'packageId':plan['identity']['transitPackageId']}, 'note':'Tarihsel rota','demand':'Mahalle','candidate':'Hastane',
        'legs':[{'kind':'ride','label':'442','coordinates':[[32.,39.],[32.1,39.1]]}],
        'boardings':[{'route':'442','stop':'Durak','mode':'BUS','waitMinutes':3}]}
    record = {'format':1,'request':request,'response':response,'sourcePlanSHA256':'b'*64,
        'capturedAt':'2026-10-27T12:00:00+00:00','captureCodeLF_SHA256':'d'*64}
    return plan,request,allocation,record


def test_valid_positive_assigned_route(fixture):
    plan,request,allocation,record=fixture
    assert p.validate_record(record,request,allocation,plan,'b'*64) == record['response']


@pytest.mark.parametrize('case',['format-bool','stale-plan','source','minutes','profile','package','endpoint','traffic-bool','empty-label','coordinate','wait','no-geometry'])
def test_invalid_route_is_not_publishable(fixture,case):
    plan,request,allocation,r=fixture
    if case=='format-bool': r['format']=True
    if case=='stale-plan': r['response']['planId']='permanent-'+'e'*64
    if case=='source': r['sourcePlanSHA256']='f'*64
    if case=='minutes': r['response']['minutes']=39
    if case=='profile': r['response']['profileId']='weekday-0800'
    if case=='package': r['response']['evidence']['packageId']='other'
    if case=='endpoint': r['response']['scenario']['candidateId']='other'
    if case=='traffic-bool': r['response']['scenario']['trafficFactor']=True
    if case=='empty-label': r['response']['legs'][0]['label']=''
    if case=='coordinate': r['response']['legs'][0]['coordinates'][0][0]=float('inf')
    if case=='wait': r['response']['boardings'][0]['waitMinutes']=-1
    if case=='no-geometry': r['response']['legs']=[]
    with pytest.raises(ValueError): p.validate_record(r,request,allocation,plan,'b'*64)


def test_cache_needs_every_public_allocation(fixture,tmp_path,monkeypatch):
    plan,request,allocation,record=fixture
    monkeypatch.setattr(p,'CACHE',tmp_path)
    path=p.cache_path(plan,request);path.parent.mkdir(parents=True);blob=p.canonical(record);path.write_bytes(blob)
    manifest={'format':1,'planId':plan['planId'],'sourcePlanSHA256':'b'*64,
        'routes':{'transit/D/C':{'file':path.relative_to(tmp_path).as_posix(),'sha256':p.sha(blob)}},'counts':{'car':0,'transit':1}}
    (tmp_path/'manifest.json').write_bytes(p.canonical(manifest))
    with pytest.raises(ValueError,match='incomplete'): p.validated_cache(plan,'b'*64)


@pytest.mark.parametrize('case',['duplicate','unsafe','zero'])
def test_invalid_assignment_cannot_be_exported(fixture,case):
    plan,*_=fixture
    part=plan['profiles']['car']['assignments'][0]['allocations'][0]
    if case=='duplicate': plan['profiles']['car']['assignments'][0]['allocations'].append(deepcopy(part))
    if case=='unsafe': part['candidateId']='../secret'
    if case=='zero': part['population']=0
    with pytest.raises(ValueError): p.requests_for(plan)


def test_packaged_collection_matches_current_plan():
    plan,checksum=p.snapshot()
    manifest,records=p.validated_cache(plan,checksum)
    assert sum(manifest['counts'].values()) == len(records) == 2061
    assert manifest['counts']=={'car':1202,'transit':859}
