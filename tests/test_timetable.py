import numpy as np
import pytest
from scipy.sparse import csr_matrix
from backend.timetable import route_one, route_batch, PROFILES
from scripts.build_timetable import (resolve_note, bus_graph, allocate_segment_times,
    route_geometry_check, validate_coordinate_districts, walking_cache_valid, record_walking_cache, coordinate_registry,
    nearby_bus_vertices,timing_segment_meters)
from scripts.build_timetable import resolve_note_details
from scripts.fetch_ego import parse_route


def graph(shape,entries):
    return csr_matrix(([v for a,b,v in entries],([a for a,b,v in entries],[b for a,b,v in entries])),shape=shape)


def pattern(i,stops,offsets,times):
    return {'id':i,'stops':stops,'offsets':offsets,'departures':{d:times for d in ('weekday','saturday','sunday')}}


def test_missed_transfer_waits_for_next_trip_and_batch_matches_scalar():
    t=36000
    network={'stops':[{}]*4,'patterns':[pattern(0,[0,1],[0,600],[t+300]),pattern(1,[2,3],[0,600],[t+1020,t+1800])]}
    access=graph((2,4),[(0,0,120),(1,0,360)])
    egress=graph((4,2),[(3,0,120)])
    transfers=graph((4,4),[(1,2,120)])
    direct=graph((2,2),[(0,1,1200),(1,1,1200)])
    args=network,access,egress,transfers,direct
    minutes,paths=route_one(*args,0,'weekday-1000')
    assert minutes[0]==42 # cannot catch 10:17 after 2 min walk + 1 min boarding slack
    assert minutes[1]==20 # walking-only journey must not be truncated at 15 min
    rides=[x for x in paths[0] if x['kind']=='ride']
    assert len(rides)==2 and rides[-1]['departureSeconds']==37800
    second,_=route_one(*args,1,'weekday-1000')
    assert not np.isfinite(second[0]) # first departure missed; no fictitious all-day service
    batch=route_batch(*args,'weekday-1000')
    np.testing.assert_allclose(batch,np.array([minutes,second]),atol=1e-5)


def test_no_fourth_boarding_or_chained_transfer_walk_shortcuts():
    t=36000
    network={'stops':[{}]*6,'patterns':[pattern(i,[i,i+1],[0,120],[t+120+i*240]) for i in range(4)]}
    access=graph((1,6),[(0,0,10)])
    egress=graph((6,2),[(4,0,10),(5,1,10)])
    transfers=graph((6,6),[(1,2,10),(2,5,10)])
    direct=graph((1,2),[])
    minutes,_=route_one(network,access,egress,transfers,direct,0,'weekday-1000')
    # Transfer 1->2 is legal; the unrelated 2->5 footpath cannot be chained for free.
    assert not np.isfinite(minutes[1])
    network['patterns']=network['patterns'][:4]
    empty=graph((6,6),[])
    minutes,_=route_one(network,access,egress,empty,direct,0,'weekday-1000')
    assert not np.isfinite(minutes[0])


def test_day_type_and_exact_boarding_boundary():
    p=pattern(0,[0,1],[0,60],[36060]);p['departures']['sunday']=[]
    args=({'stops':[{},{}],'patterns':[p]},graph((1,2),[(0,0,.001)]),graph((2,1),[(1,0,10)]),graph((2,2),[]),graph((1,1),[]))
    assert not np.isfinite(route_one(*args,0,'weekday-1000')[0][0])
    assert not np.isfinite(route_one(*args,0,'sunday-1000')[0][0])
    p['departures']['weekday']=[36061]
    assert np.isfinite(route_one(*args,0,'weekday-1000')[0][0])


def test_notes_do_not_invent_full_route_departures():
    stops=[{'id':str(10000+i),'name':n} for i,n in enumerate(['A','B','C','D'])]
    assert resolve_note('-',stops)==(0,3)
    assert resolve_note('10001 NOLU DURAKTAN BAŞLAR',stops)==(1,3)
    assert resolve_note('10001 BAŞLAR 10002 BİTER',stops)==(1,2)
    assert resolve_note('SİNCAN DAN',stops) is None
    assert resolve_note('10001 BAŞLAR YÖK E GİDER',stops) is None
    assert resolve_note('AYBÜDEN HAREKET SAATİ',[{'id':'1','name':'AYBÜ'},{'id':'2','name':'terminal'}])==(0,1)


def test_bus_permissions_override_general_access_without_merging_bridges():
    from scipy.sparse.csgraph import dijkstra
    osm={'ways':{
        '1':{'tags':{'highway':'service','access':'private','bus':'yes','oneway':'yes','oneway:bus':'no'},
             'nodes':[1,2],'geometry':[[32.8,39.9],[32.801,39.9]]},
        '2':{'tags':{'highway':'primary','bus':'no'},'nodes':[2,3],'geometry':[[32.801,39.9],[32.802,39.9]]},
        '3':{'tags':{'highway':'primary'},'nodes':[4,5],'geometry':[[32.801,39.9],[32.801,39.901]]},
    }}
    g,c=bus_graph(osm)
    assert g[0,1]>0 and g[1,0]>0
    assert len(c)==4 # prohibited way does not add vertex 3
    assert not np.isfinite(dijkstra(g,indices=0)[2]) # same coordinates, different bridge node IDs


def test_schedule_parser_preserves_note_and_avoids_duplicate_time_in_note():
    html='''<table class="hs-kv"><tr><td>548</td></tr><tr><td>route</td></tr><tr><td>A</td></tr><tr><td>B</td></tr><tr><td>10 km</td></tr><tr><td>20 dakika</td></tr></table>
    <table class="hs-table"><td class="hs-times">05:45 05:45 BEYPAZARI NDAN<br>08:00 -</td><td class="hs-times">09:00 -</td><td class="hs-times"></td></table>
    <table class="route-table"><tbody><tr><td>1</td><td>10000</td><td>A</td><td>adres</td></tr><tr><td>2</td><td>10001</td><td>B</td><td>adres</td></tr></tbody></table>'''
    route=parse_route(html,'548')
    assert len(route['departures']['weekday'])==2
    assert route['departures']['weekday'][0]['note']=='05:45 BEYPAZARI NDAN'
    assert route['departures']['sunday']==[]
    assert route['durationMinutes']==20


def test_segment_duration_floor_cannot_be_lost_when_total_is_scaled():
    # An admissible whole-route duration cannot conceal an impossibly fast leg.
    # The former normalized weights assigned only 9.9 seconds to this 10 km leg.
    meters=np.array([10000.,100.]);weights=np.array([1.,100.])
    offsets,minimum=allocate_segment_times(meters,weights,1000,'drive')
    assert offsets[-1]==1000 and minimum<1000
    assert np.all(np.diff(offsets)>=meters/25+10-1e-9)
    # The observed 588-1 error was 5.485 km in 132.725 seconds (149 km/h).
    offsets,minimum=allocate_segment_times([5485.2443266],[132.7254068],132.7254068,'drive')
    assert abs(offsets[-1]-(5485.2443266/25+10))<1e-6
    rail,_=allocate_segment_times([1000],[1],20,'rail-A')
    assert abs(rail[-1]-55)<1e-6 # 80 km/h plus ten seconds, independently per leg.


def test_source_geometry_conflict_is_quarantined_instead_of_making_a_four_hour_bus():
    # A historical fallback misplaced Ulupinar ~20 km from its neighbouring
    # stops; the official 489 route is only 10 km. It must fail before timing.
    route={'id':'489','distanceKm':10}
    registry={'a':{'lon':33.0944854,'lat':40.1551301},
              'b':{'lon':33.11411,'lat':39.970021},
              'c':{'lon':33.100537,'lat':40.180355}}
    known=[(i,{'id':code}) for i,code in enumerate(registry)]
    check=route_geometry_check(route,known,registry,['a:b','b:c'],
                              {'a:b':{'meters':32270},'b:c':{'meters':59210}})
    assert check['status']=='quarantined'
    assert len(check['reasons'])==2 and check['straightToPublishedRatio']>4
    # Plausible rounding must not disable an otherwise consistent route.
    registry={'a':{'lon':32.8,'lat':39.9},'b':{'lon':32.81,'lat':39.9}}
    check=route_geometry_check({'id':'ok','distanceKm':1},[(0,{'id':'a'}),(1,{'id':'b'})],
                              registry,['a:b'],{'a:b':{'meters':1200}})
    assert check['status']=='passed consistency gates'


def test_historical_coordinate_district_conflict_is_withheld_without_relocation():
    boundary={'features':[{'properties':{'name':'Testdistrict'},'geometry':{'type':'Polygon',
        'coordinates':[[[32.8,39.9],[32.9,39.9],[32.9,40.0],[32.8,40.0],[32.8,39.9]]]}}]}
    def stop(lon,source):
        return {'id':str(lon),'name':'Example','address':'Example Mh. Testdistrict/Ankara',
                'lon':lon,'lat':39.95,'coordinateSource':source}
    registry={'bad':stop(32.5,'Historical community GTFS coordinate; official stop ID'),
              'border':stop(32.79,'Historical community GTFS coordinate; official stop ID'),
              'osm':stop(32.5,'OSM stop ref')}
    retained,missing,audit=validate_coordinate_districts(registry,boundary)
    assert set(retained)=={'border','osm'} and audit['quarantinedCoordinateCount']==1
    assert len(missing)==1 and missing[0]['id']=='bad'
    assert registry['bad']['lon']==32.5 # no inferred location; input is preserved
    assert len(audit['conflicts'])==2 and audit['matchedStopCount']==3


def test_walking_cache_validates_shared_output_identity_in_a_b_a_sequence(tmp_path):
    paths={name:tmp_path/(name+'.npz') for name in ('access','egress','transfers','direct')}
    metadata=tmp_path/'walking-cache.json'
    for path in paths.values():path.write_bytes(b'output-A')
    record_walking_cache(metadata,'input-A',paths)
    old_metadata=metadata.read_bytes()
    assert walking_cache_valid(metadata,'input-A',paths)
    for path in paths.values():path.write_bytes(b'output-B')
    record_walking_cache(metadata,'input-B',paths)
    assert walking_cache_valid(metadata,'input-B',paths)
    assert not walking_cache_valid(metadata,'input-A',paths)
    # Even restoring an old A marker cannot bless the B output files.
    metadata.write_bytes(old_metadata)
    assert not walking_cache_valid(metadata,'input-A',paths)
    for path in paths.values():path.write_bytes(b'output-A')
    assert walking_cache_valid(metadata,'input-A',paths)
    paths['access'].write_bytes(b'corrupt')
    assert not walking_cache_valid(metadata,'input-A',paths)


def test_official_stop_query_precedes_osm_and_historical_coordinates(tmp_path,monkeypatch):
    import zipfile
    import scripts.build_timetable as builder
    monkeypatch.setattr(builder,'RAW',tmp_path)
    (tmp_path/'ego').mkdir()
    with zipfile.ZipFile(tmp_path/'ego/community-ankara.zip','w') as z:
        z.writestr('stops.txt','stop_id,stop_lon,stop_lat\n41893,32.584129,39.970246\n41894,32.58,39.97\n41895,32.59,39.97\n')
    official={'routes':[{'stops':[{'id':code,'name':code,'address':'Example Pursaklar'} for code in ('41893','41894','41895')]}]}
    osm={'nodes':{1:{'tags':{'highway':'bus_stop','ref':'41893'},'lon':32.6,'lat':39.98},
                  2:{'tags':{'highway':'bus_stop','ref':'41894'},'lon':32.85,'lat':40.14}}}
    primary={'format':1,'stops':{'41893':{'id':'41893','lat':40.143848,'lon':32.847659,
             'observedAt':'2026-10-22T21:00:00Z','rawSha256':'abc','sourceUrl':'https://baskentkart.ego.gov.tr/'}}}
    registry,missing,conflicts=coordinate_registry(official,osm,primary)
    assert not missing
    assert registry['41893']['lat']==40.143848 and registry['41893']['lon']==32.847659
    assert registry['41893']['coordinateSource']=='EGO Başkentkart public stop query'
    assert registry['41893']['coordinateRawSha256']=='abc'
    assert registry['41894']['coordinateSource']=='OSM stop ref'
    assert registry['41895']['coordinateSource'].startswith('Historical community')
    assert {x['comparedSource'] for x in conflicts if x['stopId']=='41893'}=={'OSM','Historical community GTFS'}


def test_bus_snap_retry_can_have_no_vertices_inside_its_stricter_limit():
    from scipy.spatial import cKDTree
    from backend.geo import PROJECT
    stop={'lon':32.8,'lat':39.9};point=np.array(PROJECT.transform(stop['lon'],stop['lat']))
    tree=cKDTree([point+[250,0],point+[290,0]])
    vertices,distances=nearby_bus_vertices(tree,np.array([4,8]),stop)
    # Initial snap permits 300 m, but the retry only permits 200 m. Empty is
    # a normal missing-connection result, never an argmin/Dijkstra error.
    assert len(vertices)==len(distances)==0
    tree=cKDTree([point+[50,0]])
    vertices,distances=nearby_bus_vertices(tree,np.array([4]),stop)
    assert vertices.tolist()==[4] and distances.tolist()==[50]


def test_distinct_stops_snapped_to_one_vertex_do_not_get_zero_travel_distance():
    segment={'meters':0.,'endpointDistanceMeters':450.}
    offsets,_=allocate_segment_times([timing_segment_meters(segment)],[25],10,'drive')
    assert offsets[-1]==28 # 450 m at 90 km/h plus ten seconds.
    assert timing_segment_meters({'meters':1000.,'endpointDistanceMeters':450.})==1000


@pytest.mark.parametrize('note,clock,reason',[
    ('20957 DURAKTAN BAŞLAR.D.SERVİS DIŞI',8*3600+38*60,'unresolved_return_deadhead_or_route_variant'),
    ('30995 ANAHATUN CAMİİNDEN BAŞLAR ULUS SON',9*3600,'start_instruction_has_unresolved_remaining_clause'),
    ('06:35 METRODAN BAŞLAR-07:02 21256 NUMARALI DURAK',6*3600+35*60,'multiple_note_clocks_require_separate_service_semantics'),
    ('15:55 HAREKET NOKTASI,16:30 BEŞEVLER 11495 BAŞLAR',15*3600+55*60,'multiple_note_clocks_require_separate_service_semantics'),
    ('G.PARKINDAN BAŞLAR.YEŞİLBAYIR 31141 SERVİS BİTER',18*3600+15*60,'start_instruction_has_unresolved_remaining_clause'),
    ('G.PARKINDAN BAŞLAR.YEŞİLBAYIR 31141 SERVİS BİTER',18*3600+35*60,'start_instruction_has_unresolved_remaining_clause'),
    ('06:45 21914 M.KENT SİTESİ BAŞLAR',6*3600+20*60,'note_clock_conflicts_with_column_clock'),
    ('20817 NOLU DURAKTAN BAŞLAR-DÖNÜŞ YAPMAZ',6*3600+20*60,'unresolved_return_deadhead_or_route_variant'),
    ('30361 NOLU DURAKTAN BŞLR İLK MECLİS SON',6*3600+8*60,'abbreviated_start_instruction_unresolved'),
])
def test_real_special_service_notes_do_not_invent_times_or_return_service(note,clock,reason):
    refs=('10000','20957','30995','21256','11495','31141','21914','20817','30361','10099')
    stops=[{'id':ref,'name':ref} for ref in refs]
    resolved=resolve_note_details(note,stops,clock)
    assert resolved['span'] is None and resolved['reason']==reason
    assert resolved['columnSeconds']==clock
    if '07:02' in note:assert resolved['noteClockSeconds']==[6*3600+35*60,7*3600+2*60]
    if note.startswith('06:45'):assert resolved['noteClockSeconds']==[6*3600+45*60]


def test_complete_simple_start_end_and_rail_notes_are_preserved():
    stops=[{'id':'10000','name':'ULUS METRO İSTASYONU'},
           {'id':'21914','name':'MEBUSKENT'}, {'id':'10002','name':'Terminal'}]
    assert resolve_note('21914 NOLU DURAKTAN BAŞLAR',stops)==(1,2)
    assert resolve_note('10002 NOLU DURAK SON',stops)==(0,2)
    assert resolve_note('21914 BAŞLAR 10002 BİTER',stops)==(1,2)
    assert resolve_note('ULUS METRO İSTASYONUNDAN BAŞLAYACAK',stops)==(0,2)
    assert resolve_note('06:45 21914 M.KENT SİTESİ BAŞLAR',stops,6*3600+45*60)==(1,2)
    assert resolve_note('06:45 21914 M.KENT SİTESİ BAŞLAR',stops) is None
    repeated=stops+[stops[1]]
    assert resolve_note('21914 NOLU DURAKTAN BAŞLAR',repeated) is None


@pytest.mark.parametrize('note',[
    'SADECE OKUL GÜNLERİ 10001 NOLU DURAKTAN BAŞLAR',
    'SADECE PAZAR 10001 NOLU DURAK SON',
    '10001 BAŞLAR SADECE OKUL GÜNLERİ 10002 BİTER',
    'PAZAR HARİÇ 10001 NOLU DURAKTAN BAŞLAR',
    'HAFTA İÇİ 10001 NOLU DURAKTAN BAŞLAR',
    '23.10.2026 TARİHİNDE 10001 NOLU DURAKTAN BAŞLAR',
    '2026-10-23 10001 NOLU DURAKTAN BAŞLAR',
    '23/10/26 10001 NOLU DURAKTAN BAŞLAR',
])
def test_calendar_conditions_are_not_silently_promoted_to_every_service_day(note):
    stops=[{'id':str(10000+i),'name':str(i)} for i in range(4)]
    resolved=resolve_note_details(note,stops)
    assert resolved['span'] is None
    assert resolved['reason']=='conditional_or_dated_service_calendar_unresolved'


def test_stop_names_are_not_mistaken_for_school_or_market_calendar_conditions():
    stops=[{'id':str(10000+i),'name':str(i)} for i in range(4)]
    for note in ('10001 MAHMUT ÖZDEMİR OKULUNDAN BAŞLAR',
                 '10001 ÖZKENT AKBİLEK ORTAOKULU BAŞLAR',
                 '19 MAYIS CD.4.DURAK 10001 BAŞLAR',
                 '100.YIL PAZAR YERİ 10001 NO LU DURAKTAN BAŞLAR'):
        assert resolve_note(note,stops)==(1,3)


def test_matching_clock_does_not_establish_departure_role_for_end_only_note():
    stops=[{'id':str(10000+i),'name':str(i)} for i in range(4)]
    resolved=resolve_note_details('08:00 10002 NOLU DURAK SON',stops,8*3600)
    assert resolved['span'] is None
    assert resolved['reason']=='note_clock_at_end_only_instruction_unresolved'
    assert resolve_note('08:00 10001 NOLU DURAKTAN BAŞLAR',stops,8*3600)==(1,3)
