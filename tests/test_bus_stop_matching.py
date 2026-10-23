from copy import deepcopy
import numpy as np
import pytest
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from backend.bus_stop_matching import (RoadIndex, select_attachments, split_edges,
    coherent_selection, classify_legacy_anchor, ValidatedBaselines, validate_baselines,
    match_bus_stops, official_bus_pairs, requires_locked_endpoints, locked_pair_result)
from backend.geo import project, PROJECT
from scripts.build_timetable import project_bus_stops, bus_graph


def road(code,xy,nodes=None,one=1,**tags):
    return {'id':code,'xy':np.array(xy,dtype=float),'nodes':nodes or list(range(len(xy))),
            'direction':one,'tags':{'highway':'primary',**tags}}


def graph(xy,edges):
    return csr_matrix(([c for a,b,c in edges],([a for a,b,c in edges],[b for a,b,c in edges])),
                      shape=(len(xy),len(xy))),np.array(xy,dtype=float)


def select(roads,points,pairs,old=100):
    return select_attachments(RoadIndex(roads),points,{s:old for s in points},pairs)


def test_vertex_under_300_is_not_an_exclusion_and_forward_order_is_required():
    r=road('forward',[[0,0],[1000,0]])
    points={'a':[200,5],'b':[500,6]}
    chosen,rejected=select([r],points,[('a','b')])
    assert set(chosen)=={'a','b'}
    assert chosen['a']['edgeDistanceMeters']==pytest.approx(5)
    opposite,rejected=select([r],points,[('b','a')])
    assert not opposite
    assert set(rejected.values())=={'official_local_order_conflicts_with_oneway'}


def test_conflicting_official_orders_are_not_resolved_by_majority_vote():
    chosen,rejected=select([road('one',[[0,0],[1000,0]])],
        {'a':[200,5],'b':[500,6]},[('a','b'),('a','b'),('b','a')])
    assert not chosen
    assert set(rejected.values())=={'official_local_order_conflicts_with_oneway'}


def test_equal_parallel_road_and_near_alternative_are_rejected():
    for gap in (10,18):
        roads=[road('one',[[0,0],[1000,0]]),road('two',[[0,gap],[1000,gap]],nodes=[2,3],one=-1)]
        chosen,rejected=select(roads,{'a':[200,5],'b':[500,5]},[('a','b')])
        assert not chosen
        assert set(rejected.values())=={'nearby_distinct_way_ambiguity'}


def test_more_distant_opposite_carriageway_does_not_merge():
    roads=[road('one',[[0,0],[1000,0]]),road('two',[[0,40],[1000,40]],nodes=[2,3],one=-1)]
    points={'a':[200,5],'b':[500,5],'c':[700,35],'d':[400,35]}
    chosen,_=select(roads,points,[('a','b'),('c','d')])
    assert len(chosen)==4
    g,xy=graph([[0,0],[1000,0],[0,40],[1000,40]],[(0,1,100),(3,2,140)])
    split,newxy,nodes=split_edges(g,xy,chosen)
    dist=dijkstra(split,indices=nodes['a'])
    assert dist[nodes['b']]==pytest.approx(30)
    assert not np.isfinite(dist[nodes['c']])
    assert not np.isfinite(dijkstra(split,indices=nodes['b'])[nodes['a']])
    np.testing.assert_allclose(dijkstra(split,indices=np.arange(4))[:,:4],dijkstra(g))


@pytest.mark.parametrize('tag,value',[('bridge','yes'),('tunnel','yes'),('layer','1')])
def test_grade_on_candidate_or_near_crossing_rejected(tag,value):
    points={'a':[200,5],'b':[500,5]}
    chosen,rejected=select([road('one',[[0,0],[1000,0]],**{tag:value})],points,[('a','b')])
    assert not chosen
    roads=[road('one',[[0,0],[1000,0]]),
           road('cross',[[200,-100],[200,100]],nodes=[2,3],**{tag:value})]
    chosen,rejected=select(roads,points,[('a','b')])
    assert 'a' not in chosen
    assert rejected['a']=='grade_or_nearby_grade_ambiguity'


def test_same_way_doubling_back_is_still_ambiguous():
    roads=[road('loop',[[0,0],[1000,0],[1000,10],[0,10]])]
    chosen,rejected=select(roads,{'a':[200,4],'b':[500,4]},[('a','b')])
    assert not chosen
    assert set(rejected.values())=={'same_way_segment_ambiguity'}


def test_immediately_adjacent_hairpin_is_also_ambiguous():
    roads=[road('hairpin',[[0,0],[1000,0],[0,10]])]
    chosen,rejected=select(roads,{'a':[200,2],'b':[500,2]},[('a','b')])
    assert not chosen
    assert set(rejected.values())=={'same_way_segment_ambiguity'}


def test_adjacent_straight_shared_endpoint_is_ordinary_continuation():
    roads=[road('one',[[0,0],[400,0],[1000,0]])]
    chosen,rejected=select(roads,{'a':[200,2],'b':[500,2]},[('a','b')])
    assert set(chosen)=={'a','b'}


def test_distinct_way_without_forward_witness_is_not_inferred_connected():
    roads=[road('one',[[0,0],[400,0]]),road('two',[[600,0],[1000,0]],nodes=[2,3])]
    chosen,rejected=select(roads,{'a':[200,5],'b':[800,5]},[('a','b')])
    assert not chosen
    assert set(rejected.values())=={'no_unambiguous_same_way_forward_order_witness'}


def test_split_both_costs_same_edge_and_coincident_different_edges():
    g,xy=graph([[0,0],[1000,0],[0,0],[1000,0]],[(0,1,100),(1,0,160),(2,3,200)])
    records={'a':{'edge':[0,1],'fraction':.2},'b':{'edge':[1,0],'fraction':.5},
             'duplicate':{'edge':[0,1],'fraction':.2},'other':{'edge':[2,3],'fraction':.2}}
    split,newxy,nodes=split_edges(g,xy,records)
    assert nodes['a']==nodes['duplicate']
    assert nodes['a']!=nodes['other']
    assert dijkstra(split,indices=nodes['a'])[nodes['b']]==pytest.approx(30)
    assert dijkstra(split,indices=nodes['b'])[nodes['a']]==pytest.approx(48)
    assert not np.isfinite(dijkstra(split,indices=nodes['a'])[nodes['other']])
    np.testing.assert_allclose(dijkstra(split,indices=np.arange(4))[:,:4],dijkstra(g))
    np.testing.assert_array_equal(newxy[:4],xy)


def test_existing_projection_baseline_is_explicitly_preserved():
    points={'a':[200,5],'b':[500,5]}
    chosen,rejected=select_attachments(RoadIndex([road('one',[[0,0],[1000,0]])]),points,
        {'a':500,'b':500},[('a','b')],baseline={'a'})
    assert 'a' not in chosen
    assert rejected['a']=='retained_existing_projection'


def test_pinned_virtual_vertex_indices_survive_earlier_sorted_extra_splits():
    g,xy=graph([[0,0],[1000,0],[2000,0]],[(0,1,100),(1,2,100)])
    baseline={'old':{'edge':[1,2],'fraction':.5,'node':3}}
    bg,bxy,bnodes=split_edges(g,xy,baseline)
    combined={**baseline,'new':{'edge':[0,1],'fraction':.5}}
    ng,nxy,nnodes=split_edges(g,xy,combined)
    assert bnodes['old']==nnodes['old']==3
    assert nnodes['new']==4
    np.testing.assert_array_equal(nxy[:4],bxy)
    np.testing.assert_allclose(dijkstra(ng,indices=np.arange(4))[:,:4],dijkstra(bg))


def test_wrong_carriageway_neighbor_withholds_anchor_independent_of_cost():
    index=RoadIndex([road('forward',[[0,0],[1000,0]],[0,1]),
                     road('reverse',[[0,40],[1000,40]],[2,3],one=-1)])
    points={'selected':[200,5],'legacy':[500,5]}
    retained,report=coherent_selection(index,points,{'selected':2,'legacy':3},
        [('selected','legacy')],ValidatedBaselines(), {'selected':{'arbitraryTravelCost':-100000}})
    assert not retained
    assert report['withheld']['selected']['neighbors'][0]['reason']=='legacy_neighbor_node_not_on_nearest_way'


def test_nearby_tunnel_rejects_even_if_old_vertex_is_on_nearest_way():
    index=RoadIndex([road('surface',[[0,0],[1000,0]],[0,1]),
                     road('tunnel',[[400,-100],[400,100]],[2,3],layer='-1',tunnel='yes')])
    state=classify_legacy_anchor(index,[400,3],0)
    assert not state['resolved']
    assert state['reason']=='legacy_neighbor_grade_ambiguity'


def test_resolved_two_way_street_and_unique_carriageway_are_kept():
    index=RoadIndex([road('two',[[0,0],[1000,0]],[0,1],one=0),
                     road('one',[[0,100],[1000,100]],[2,3])])
    points={'selected':[200,100],'two':[50,3],'one':[900,103]}
    retained,report=coherent_selection(index,points,{'selected':2,'two':0,'one':3},
        [('two','selected'),('selected','one')],ValidatedBaselines(), {'selected':{}})
    assert set(retained)=={'selected'}
    assert not report['withheld']


def test_neighbor_withholding_reaches_fixed_point_without_leg_specific_teleport():
    index=RoadIndex([road('road',[[0,0],[1000,0]],[0,1])])
    points={'a':[100,4],'b':[300,4],'c':[500,4]}
    # Their OLD nodes are not on this road; a/b initially have accepted new
    # anchors. c's unresolved old anchor first removes b, then removes a.
    retained,report=coherent_selection(index,points,{'a':9,'b':8,'c':7},
        [('a','b'),('b','c')],ValidatedBaselines(), {'a':{},'b':{}})
    assert not retained
    assert report['withheld']['b']['iteration']==1
    assert report['withheld']['a']['iteration']==2
    assert report['iterationsWithRemovals']==2


def test_vertex_beyond_the_existing_300m_limit_is_not_a_resolved_legacy_anchor():
    index=RoadIndex([road('one',[[0,0],[1000,0]],[0,1])])
    state=classify_legacy_anchor(index,[500,5],0)
    assert not state['resolved']
    assert state['reason']=='legacy_neighbor_exceeds_existing_snap_limit'


def test_two_way_disconnected_parallel_roads_remain_ambiguous():
    index=RoadIndex([road('one',[[0,0],[1000,0]],[0,1],one=0),
                     road('two',[[0,10],[1000,10]],[2,3],one=0)])
    state=classify_legacy_anchor(index,[100,5],0)
    assert not state['resolved']
    assert state['reason']=='legacy_neighbor_way_alternative_ambiguity'


def test_two_way_adjacent_hairpin_is_still_ambiguous():
    index=RoadIndex([road('hairpin',[[0,0],[1000,0],[0,10]],[0,1,2],one=0)])
    state=classify_legacy_anchor(index,[100,2],0)
    assert not state['resolved']
    assert state['reason']=='legacy_neighbor_same_way_ambiguity'


def test_old_node_on_distant_branch_of_same_way_is_not_local_incidence():
    index=RoadIndex([road('folded',[[0,0],[1000,0],[1000,40],[100,40],[0,40]],[0,1,2,3,4])])
    state=classify_legacy_anchor(index,[100,5],3)
    assert not state['resolved']
    assert state['oldNodeOnNearestWay']
    assert not state['oldNodeOnNearestSegment']
    assert state['reason']=='legacy_neighbor_node_not_on_nearest_segment'


def test_shared_node_endpoint_junction_is_allowed_but_coincident_identity_is_not():
    for shared in [True,False]:
        index=RoadIndex([road('main',[[0,0],[1000,0]],[0,1],one=0),
                         road('branch',[[0,0],[0,100]],[0 if shared else 2,3],one=0)])
        state=classify_legacy_anchor(index,[5,-2],0)
        assert state['resolved']==shared
        if shared: assert state['sharedEndpointAlternatives']==[{'wayId':'branch','sharedNode':0}]


def matching_fixture():
    origin=project([[32.8,39.9]])[0]
    xy=origin+np.array([[0,0],[400,0],[800,0],[0,1000],[2000,1000]])
    ll=np.array([PROJECT.transform(*p,direction='INVERSE') for p in xy])
    osm={'ways':{'main':{'nodes':[10,11,12],'geometry':ll[:3].tolist(),
                        'tags':{'highway':'primary','oneway':'yes'}},
                 'far':{'nodes':[13,14],'geometry':ll[3:].tolist(),
                        'tags':{'highway':'secondary'}}}}
    g,coords,roads=bus_graph(osm,include_roads=True)
    registry={}
    for code,offset,old in [('a',[200,5],0),('b',[500,5],1),('old',[1000,1005],3)]:
        point=origin+offset;lon,lat=PROJECT.transform(*point,direction='INVERSE')
        registry[code]={'id':code,'lon':lon,'lat':lat,'driveNode':old,
            'driveSnapMeters':float(np.linalg.norm(point-xy[old])),
            'walkNode':42,'walkSnapMeters':18.0,'rail-ANode':7}
    return g,coords,roads,registry


def prepare_far_baseline(g,coords,registry):
    _,_,report=project_bus_stops(g,coords,registry,{'a','b','old'})
    return {code:r['driveProjection'] for code,r in registry.items() if r.get('driveProjection')}


def test_production_combines_verified_far_pins_and_direction_matches_without_index_or_walk_changes():
    g,coords,roads,registry=matching_fixture();before=deepcopy(registry)
    baseline=prepare_far_baseline(g,coords,registry)
    old_record=deepcopy(baseline['old'])
    occurrences={('a','b'):[{'routeId':'fixture','fromSequence':0,'toSequence':1}],('old','old'):[]}
    combined,new_coords,report=match_bus_stops(g,coords,roads,registry,occurrences,baseline)
    assert set(report['attachments'])=={'a','b'}
    assert report['additionalDirectionMatchedStops']==2
    assert report['originalFarProjectedStops']==1
    assert registry['old']['driveProjection']==old_record
    assert registry['old']['driveNode']==len(coords)
    assert {registry[s]['driveNode'] for s in ('a','b')}=={len(coords)+1,len(coords)+2}
    assert report['baselineValidation']['trustedStopIds']==['old']
    for code in registry:
        for field in ('id','lon','lat','walkNode','walkSnapMeters','rail-ANode'):
            assert registry[code][field]==before[code][field]
        assert registry[code]['driveNodeCoordinates']==new_coords[registry[code]['driveNode']].tolist()
    for code in ('a','b'):
        record=report['attachments'][code]
        assert record['originalNode']==before[code]['driveNode']
        assert record['method']=='direction_order'
        assert record['matchEvidence']['witnesses'][0]['officialOccurrences']==occurrences['a','b']
    np.testing.assert_array_equal(new_coords[:len(coords)],coords)
    np.testing.assert_allclose(dijkstra(combined,indices=np.arange(len(coords)))[:,:len(coords)],dijkstra(g))
    bg,bxy,bnodes=split_edges(g,project(coords),baseline)
    np.testing.assert_allclose(project(new_coords)[:len(bxy)],bxy,atol=1e-7)
    np.testing.assert_allclose(dijkstra(combined,indices=np.arange(len(bxy)))[:,:len(bxy)],dijkstra(bg))


def test_baseline_dictionary_key_cannot_exempt_an_uncertain_neighbor():
    index=RoadIndex([road('one',[[0,0],[1000,0]])])
    with pytest.raises(TypeError,match='source validation'):
        coherent_selection(index,{'a':[100,2],'fake':[600,2]},
            {'a':9,'fake':8},[('a','fake')],{'fake':{}},{'a':{}})


def test_injected_or_modified_baseline_record_is_rejected_before_selection():
    g,coords,roads,registry=matching_fixture();baseline=prepare_far_baseline(g,coords,registry)
    original=deepcopy(baseline)
    for mode in ('injected_key','coordinate','cost','node','fraction'):
        altered=deepcopy(original);r=deepcopy(registry)
        if mode=='injected_key':altered['fake']=deepcopy(altered['old'])
        elif mode=='fraction':
            record=altered['old'];record['fraction']=.6
            xy=project(coords);a,b=record['edge'];p=xy[a]+.6*(xy[b]-xy[a])
            record['projectedCoordinates']=list(PROJECT.transform(*p,direction='INVERSE'))
            stop=registry['old'];point=project([[stop['lon'],stop['lat']]])[0]
            record['snapMeters']=float(np.linalg.norm(point-p))
            r['old']['driveProjection']=record
        else:
            field,value={'coordinate':('projectedCoordinates',[0,0]),
                         'cost':('reverseSeconds',None),'node':('node',0)}[mode]
            altered['old'][field]=value;r['old']['driveProjection']=altered['old']
        with pytest.raises(ValueError):validate_baselines(g,coords,RoadIndex(roads),r,altered)


def test_missing_stop_cannot_be_a_direction_witness_but_bridged_neighbor_is_guarded():
    official={'routes':[{'id':'r','mode':'bus','stops':[{'id':'a'},{'id':'absent'},{'id':'b'}]}]}
    registry={'a':{},'b':{}}
    assert official_bus_pairs(official,registry)=={}
    bridged=official_bus_pairs(official,registry,bridge_missing=True)
    assert bridged=={('a','b'):[{'routeId':'r','fromSequence':0,'toSequence':2}]}
    index=RoadIndex([road('one',[[0,0],[1000,0]])])
    retained,report=coherent_selection(index,{'a':[100,2],'b':[600,2]},
        {'a':0,'b':99},bridged,ValidatedBaselines(),{'a':{}})
    assert not retained and report['withheld']['a']['neighbors'][0]['stopId']=='b'


def test_locked_pair_cannot_retry_at_either_end_or_reverse_a_oneway():
    selected={'new'}
    assert requires_locked_endpoints('new','legacy',selected)
    assert requires_locked_endpoints('legacy','new',selected)
    assert not requires_locked_endpoints('baseline','legacy',selected)
    # The cheap alternative3 must not replace the certified destination2.
    xy=np.array([[0,0],[3500,0],[0,20],[100,20]],dtype=float)
    g=csr_matrix(([350,350,10],([0,1,0],[1,2,3])),shape=(4,4))
    costs=dijkstra(g,indices=0,limit=7200)
    row=locked_pair_result(0,2,costs[2],7000.1,20)
    assert row['destinationNode']==2 and row['sourceNode']==0
    assert row['status']=='unresolved' and row['reason']=='fixed_anchor_exceeds_existing_geometry_gate'
    assert row['rawFixedSeconds']==700 and not row['retryAttempted']
    backwards=locked_pair_result(2,0,dijkstra(g,indices=2)[0],np.inf,20)
    assert backwards['reason']=='unresolved_within_7200_second_search'


def test_locked_horizon_geometry_gate_and_longer_valid_path_remain_distinct():
    row=locked_pair_result(0,1,np.inf,np.inf,100)
    assert row['reason']=='unresolved_within_7200_second_search'
    row=locked_pair_result(0,1,150,1500,100)
    assert row['status']=='accepted' and row['secondsWeight']==150
    assert row['meters']==1500 and row['geometryLimitMeters']==4000
    row=locked_pair_result(0,1,700,7198.488391,636.252424125)
    assert row['geometryLimitMeters']==pytest.approx(5090.019393)
    assert row['status']=='unresolved' and row['rawFixedMeters']==7198.488391
