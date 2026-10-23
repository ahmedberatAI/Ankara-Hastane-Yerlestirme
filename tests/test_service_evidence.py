"""Evidence cannot silently migrate across source, direction, day or clock."""
from copy import deepcopy
import json
from pathlib import Path
import numpy as np
import pytest
from backend.service_evidence import reviewed_events, event_key, digest
from scripts.build_timetable import pattern_offsets
from scripts.audit_service_evidence import validate_reviewed_services, validate_evidence_archive

ROOT = Path(__file__).resolve().parents[1]


def inputs():
    evidence = json.loads((ROOT/'data/processed/ego-service-evidence.json').read_text(encoding='utf8'))
    official = json.loads((ROOT/'data/processed/ego-official.json').read_text(encoding='utf8'))
    return evidence, official


def test_reviewed_catalog_matches_exact_sources_and_only_selected_events():
    evidence, official = inputs()
    active, withheld = reviewed_events(evidence, official)
    assert not withheld and len(active) == 49
    assert {key[0] for key in active} == {'560-8','615','527-1'}
    kizilcahamam = [v for k,v in active.items() if k[0] == '527-1']
    assert len(kizilcahamam) == 25
    assert all(v['span']['indicesZeroBasedInclusive'] == [0,97] for v in kizilcahamam)
    assert all(v['durationBudgetSeconds'] == 5100 for v in kizilcahamam)
    gudul = [v for k,v in active.items() if k[0] == '615']
    assert len(gudul) == 4
    assert {v['calendar'] for v in gudul} == {'weekday'}
    assert sorted(v['durationBudgetSeconds'] for v in gudul) == [5700,7200,7200,7200]
    assert all(v['span']['indicesZeroBasedInclusive'] == [0,85] for v in gudul)
    assert not any('CUMA' in k[3] or 'GÜDÜL' in k[3] for k in active if k[0] == '615')


@pytest.mark.parametrize('change,reason', [
    ('source','reviewed_source_bytes_changed'),
    ('dependency','reviewed_source_bytes_changed'),
    ('order','reviewed_stop_sequence_changed'),
    ('note','reviewed_calendar_event_changed'),
    ('clock','reviewed_calendar_event_changed'),
    ('calendar','reviewed_calendar_event_changed')])
def test_changed_sources_and_events_are_withheld_without_inventing_services(change,reason):
    evidence, official = inputs()
    evidence['events'] = [next(e for e in evidence['events'] if e['routeId']=='615')]
    e=evidence['events'][0]
    route=next(r for r in official['routes'] if r['id']=='615')
    if change in ('source','dependency'):
        filename='615.html' if change=='source' else '615-1.html'
        next(r for r in official['rawSources'] if r['file']==filename)['sha256']='f'*64
    elif change=='order':
        route['stops'][10],route['stops'][11]=route['stops'][11],route['stops'][10]
    else:
        entry=next(x for x in route['departures']['weekday'] if x['seconds']==e['departureSeconds'] and x['note']==e['exactNote'])
        if change=='note':entry['note']+=' CUMA'
        elif change=='clock':entry['seconds']+=60
        else:
            route['departures']['weekday'].remove(entry)
            route['departures']['sunday'].append(entry)
    active,withheld=reviewed_events(evidence,official)
    assert not active and withheld[0]['reason']==reason


@pytest.mark.parametrize('change', ['duplicate','occurrence','reversal','budget','calendar','claims','checksum'])
def test_invalid_rule_definitions_fail_loudly(change):
    evidence,official=inputs()
    evidence['events']=[next(e for e in evidence['events'] if e['routeId']=='615')]
    e=evidence['events'][0]
    if change=='duplicate':evidence['events'].append(deepcopy(e))
    elif change=='occurrence':e['span']['end']['occurrenceOrdinalOfSameStopId']+=1
    elif change=='reversal':e['span']['indicesZeroBasedInclusive'].reverse()
    elif change=='budget':e['durationBudgetSeconds']/=2
    elif change=='calendar':e['durationEvidence']['announcedCalendar']='sunday'
    elif change=='claims':e['currentArrivalTimeConfirmed']=True
    else:e['recordSha256']='0'*64
    with pytest.raises(ValueError):reviewed_events(evidence,official)


def test_exact_key_does_not_accept_different_time_note_route_or_day():
    evidence,official=inputs();active,_=reviewed_events(evidence,official)
    e=next(v for v in active.values() if v['routeId']=='615')
    assert active[event_key('615','weekday',e['departureSeconds'],e['exactNote'])] is e
    assert event_key('615','sunday',e['departureSeconds'],e['exactNote']) not in active
    assert event_key('615-1','weekday',e['departureSeconds'],e['exactNote']) not in active
    assert event_key('615','weekday',e['departureSeconds']+60,e['exactNote']) not in active
    assert event_key('615','weekday',e['departureSeconds'],e['exactNote']+' ') not in active


def test_direction_budget_is_not_proportional_slice_of_combined_loop():
    segments={str(i):{'meters':1000.,'endpointDistanceMeters':1000.,'secondsWeight':100.} for i in range(4)}
    keys=list(segments);old=np.array([0.,1800.,3600.,5400.,7200.])
    legacy,_=pattern_offsets(keys,segments,'drive',old,0,2)
    outbound,minimum=pattern_offsets(keys,segments,'drive',old,0,2,7200.)
    assert legacy[-1]==3600 and outbound[-1]==pytest.approx(7200)
    assert len(outbound)==3 and outbound[0]==0 and np.all(np.diff(outbound)>0)
    assert minimum>0
    tiny,_=pattern_offsets(keys,segments,'drive',old,0,2,1.)
    assert tiny[-1]==pytest.approx(minimum)  # physical bound remains in force


def test_whole_route_duration_cannot_be_changed_to_a_partial_budget():
    evidence,official=inputs()
    evidence['events']=[next(e for e in evidence['events'] if e['routeId']=='560-8')]
    evidence['events'][0]['durationBudgetSeconds']=2250
    with pytest.raises(ValueError,match='Whole-direction'):reviewed_events(evidence,official)


def audited_fixture():
    evidence,official=inputs()
    e=next(e for e in evidence['events'] if e['routeId']=='560-8')
    evidence['events']=[e]
    r=next(r for r in official['routes'] if r['id']=='560-8')
    stops=[{**s,'lon':32+i*.001,'lat':40.} for i,s in enumerate(r['stops'])]
    keys=[str(i) for i in range(len(stops)-1)]
    p={'route':'560-8','mode':'bus','stops':list(range(len(stops))),'segmentKeys':keys,
       'offsets':np.linspace(0,e['durationBudgetSeconds'],len(stops)).tolist(),
       'departures':{'weekday':[e['departureSeconds']],'saturday':[],'sunday':[]},
       'serviceEvidence':{'eventIds':[e['id']],'durationBudgetSeconds':e['durationBudgetSeconds'],
           'currentArrivalTimeConfirmed':False,'isMeasuredTravelTime':False,
           'assumptions':[e['assumption']],'timingConfidence':[e['timingConfidence']],
           'sourceUrls':[evidence['sources'][sid]['url'] for sid in e['evidenceSourceIds']]}}
    network={'stops':stops,'patterns':[p],'segments':{k:{'meters':1000} for k in keys}}
    quality={'reviewedServiceEvents':{'appliedEventIds':[e['id']],'appliedCount':1,
        'definedCount':1,'notAppliedEventIds':[],'invalidated':[]}}
    return network,official,quality,evidence


def test_independent_applied_evidence_audit_accepts_bound_direction():
    assert validate_reviewed_services(*audited_fixture())['appliedExactEvents']==1


@pytest.mark.parametrize('change',['half','day','duplicate','order','source','claims'])
def test_independent_audit_rejects_wrong_applied_events(change):
    network,official,quality,evidence=audited_fixture()
    p=network['patterns'][0]
    if change=='half':p['offsets']=[v/2 for v in p['offsets']]
    elif change=='day':p['departures']['sunday']=p['departures']['weekday']
    elif change=='duplicate':network['patterns'].append(deepcopy(p))
    elif change=='order':p['stops'][3],p['stops'][4]=p['stops'][4],p['stops'][3]
    elif change=='source':next(r for r in official['rawSources'] if r['file']=='560-8.html')['sha256']='f'*64
    else:p['serviceEvidence']['currentArrivalTimeConfirmed']=True
    with pytest.raises(AssertionError):validate_reviewed_services(network,official,quality,evidence)


def test_real_source_archives_and_planned_column_match():
    evidence,_=inputs()
    assert validate_evidence_archive(evidence,ROOT)=={'verifiedSourceArchives':9,'verifiedEventSources':49}


@pytest.mark.parametrize('change',['calendar','span','note','source','date','missing'])
def test_accessible_exact_row_cannot_migrate_across_evidence(change):
    evidence,official=inputs()
    e=next(e for e in evidence['events'] if e['routeId']=='527-1')
    evidence['events']=[e]
    if change=='calendar':e['spanEvidence']['calendarLabel']='Pazar:'
    elif change=='span':e['spanEvidence']['indicesOneBasedInclusive']=[2,98]
    elif change=='note':e['spanEvidence']['exactEntry']=e['spanEvidence']['exactEntry'].replace('KIZILCAHAMAM DAN','RÜZGARLI DAN')
    elif change=='source':e['spanEvidence']['sourceId']='ego-527-directions-7333'
    elif change=='date':e['spanEvidence']['tableEffectiveDateConfirmed']=True
    else:del e['spanEvidence']
    with pytest.raises(ValueError,match='Accessible span'):reviewed_events(evidence,official)
    with pytest.raises(AssertionError):validate_evidence_archive(evidence,ROOT)


def test_accessible_exact_row_checks_actual_archive_heading():
    evidence,_=inputs()
    e=next(e for e in evidence['events'] if e['routeId']=='527-1')
    evidence['events']=[e]
    e['spanEvidence']['exactHeading']='527-2 Ankara Kızılcahamam'
    with pytest.raises(AssertionError):validate_evidence_archive(evidence,ROOT)


def test_accessible_exact_row_does_not_round_seconds_into_a_published_minute():
    evidence,official=inputs()
    e=next(e for e in evidence['events'] if e['routeId']=='527-1')
    evidence['events']=[e]
    route=next(r for r in official['routes'] if r['id']==e['routeId'])
    record=next(r for r in route['departures'][e['calendar']] if r['seconds']==e['departureSeconds'])
    record['seconds']+=1;e['departureSeconds']+=1
    e['recordSha256']=digest({key:e[key] for key in ('routeId','calendar','departureSeconds','exactNote')})
    with pytest.raises(ValueError,match='Accessible span'):reviewed_events(evidence,official)
    with pytest.raises(AssertionError,match='minute precision'):validate_evidence_archive(evidence,ROOT)


@pytest.mark.parametrize('clock',['105:45','x05:45','05:450','05:45:30'])
def test_accessible_exact_row_never_accepts_substring_of_invalid_clock(tmp_path,clock):
    import gzip,hashlib,shutil
    evidence,_=inputs()
    e=next(e for e in evidence['events'] if e['routeId']=='527-1')
    evidence['events']=[e]
    for source in evidence['sources'].values():
        target=tmp_path/source['archiveFile'];target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/source['archiveFile'],target)
    source=evidence['sources']['ego-527-accessible-7721'];target=tmp_path/source['archiveFile']
    body=gzip.decompress(target.read_bytes()).replace(b'05:45;',clock.encode()+b';')
    target.write_bytes(gzip.compress(body,mtime=0))
    source.update(sha256=hashlib.sha256(body).hexdigest(),bytes=len(body))
    with pytest.raises(AssertionError,match='unparsed entry'):validate_evidence_archive(evidence,tmp_path)


def test_same_clock_opposite_direction_planned_row_is_rejected():
    evidence,official=inputs()
    e=next(e for e in evidence['events'] if e['routeId']=='615' and e['departureSeconds']==32400)
    evidence['events']=[e]
    cells=['3','09:00','11:00',"GÜDÜL'DEN",'SAAT DEĞİŞTİ']
    e['durationEvidence'].update(plannedCells=cells,plannedRowSha256=digest(cells),plannedRowNumber=3,
        directionLabel=cells[3],changeLabel=cells[4])
    with pytest.raises(ValueError,match='Dated plan'):reviewed_events(evidence,official)
    with pytest.raises(AssertionError,match='opposite direction'):validate_evidence_archive(evidence,ROOT)


def test_duration_cannot_borrow_unrelated_route_source():
    evidence,official=inputs()
    e=next(e for e in evidence['events'] if e['routeId']=='615')
    evidence['events']=[e]
    e['durationEvidence']['sourceId']='ego-route-560-8'
    with pytest.raises(ValueError,match='source'):reviewed_events(evidence,official)


def test_fake_historical_source_sha_is_rejected_by_archived_bytes():
    evidence,_=inputs()
    evidence['sources']['ego-615-announcement-7621']['sha256']='f'*64
    with pytest.raises(AssertionError,match='SHA mismatch'):validate_evidence_archive(evidence,ROOT)
