import numpy as np
from scipy.sparse import csr_matrix
from backend.timetable import route_one, route_batch, PROFILES
from scripts.build_timetable import resolve_note, bus_graph
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
