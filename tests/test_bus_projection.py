"""Sparse OSM vertices must not erase a stop next to a real directed road."""
from copy import deepcopy
import numpy as np
import pytest
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from backend.bus_projection import attach_far_bus_stops
from backend.geo import project
from scripts.build_timetable import project_bus_stops,bus_retry_vertices


def graph(coords,edges):
    return csr_matrix(([w for a,b,w in edges],([a for a,b,w in edges],[b for a,b,w in edges])),
                      shape=(len(coords),len(coords))),np.asarray(coords,dtype=float)


def assert_existing_distances_preserved(original,split):
    np.testing.assert_allclose(dijkstra(split,indices=np.arange(original.shape[0]))[:,:original.shape[0]],
                               dijkstra(original),rtol=1e-12,atol=1e-10)


def test_same_edge_downstream_and_reverse_prohibition():
    g,xy=graph([[0,0],[2000,0]],[(0,1,100)])
    split,coords,stops,excluded=attach_far_bus_stops(g,xy,{'up':[700,5],'down':[1300,5]})
    assert not excluded and len(coords)==4
    up,down=stops['up']['node'],stops['down']['node']
    assert dijkstra(split,indices=up)[down]==pytest.approx(30)
    assert not np.isfinite(dijkstra(split,indices=down)[up])
    assert_existing_distances_preserved(g,split)
    np.testing.assert_array_equal(coords[:len(xy)],xy)
    assert np.all(coords[[up,down],1]==0)


def test_two_way_costs_and_nearby_existing_node_are_preserved():
    g,xy=graph([[0,0],[2000,0]],[(0,1,100),(1,0,160)])
    split,coords,stops,excluded=attach_far_bus_stops(g,xy,{'a':[700,8],'b':[1300,8],'near':[30,4]})
    a,b=stops['a']['node'],stops['b']['node']
    assert not excluded and not stops['near']['changed'] and stops['near']['node']==0
    assert dijkstra(split,indices=a)[b]==pytest.approx(30)
    assert dijkstra(split,indices=b)[a]==pytest.approx(48)
    assert_existing_distances_preserved(g,split)


def test_parallel_disconnected_carriageways_never_merge():
    g,xy=graph([[0,0],[2000,0],[0,80],[2000,80]],[(0,1,100),(3,2,100)])
    split,coords,stops,excluded=attach_far_bus_stops(g,xy,{'south':[700,5],'north':[1300,75]})
    assert not excluded
    assert not np.isfinite(dijkstra(split,indices=stops['south']['node'])[stops['north']['node']])
    assert not np.isfinite(dijkstra(split,indices=stops['north']['node'])[stops['south']['node']])
    assert_existing_distances_preserved(g,split)


def test_bridge_crossing_does_not_join_topology_and_ambiguous_snap_is_withheld():
    g,xy=graph([[0,0],[2000,0],[1000,-1000],[1000,1000]],[(0,1,100),(2,3,100)])
    split,coords,stops,excluded=attach_far_bus_stops(g,xy,{'a':[600,1],'b':[1001,400],'cross':[1000,0]})
    assert excluded['cross']['reason']=='ambiguous_distinct_bus_edges'
    assert len(excluded['cross']['candidateEdges'])==2 and 'cross' not in stops
    assert not np.isfinite(dijkstra(split,indices=stops['a']['node'])[stops['b']['node']])
    assert_existing_distances_preserved(g,split)


def test_equal_parallel_candidates_are_withheld_instead_of_choosing_a_direction():
    g,xy=graph([[0,0],[2000,0],[0,20],[2000,20]],[(0,1,100),(3,2,100)])
    split,coords,stops,excluded=attach_far_bus_stops(g,xy,{'midway':[1000,10]})
    assert not stops and excluded['midway']['reason']=='ambiguous_distinct_bus_edges'
    assert split.shape==g.shape
    assert_existing_distances_preserved(g,split)


def test_no_projection_outside_original_snap_limit_or_empty_graph():
    g,xy=graph([[0,0],[2000,0]],[(0,1,100)])
    split,coords,stops,excluded=attach_far_bus_stops(g,xy,{'far':[1000,301]})
    assert excluded['far']['reason']=='no_bus_edge_within_existing_snap_limit'
    assert not stops and split.shape==g.shape
    empty=csr_matrix((2,2))
    split,coords,stops,excluded=attach_far_bus_stops(empty,xy,{'far':[1000,0]})
    assert excluded['far']['reason']=='empty_bus_graph' and split.nnz==0


def test_coincident_projections_merge_only_on_the_same_original_edge():
    g,xy=graph([[0,0],[2000,0]],[(0,1,100)])
    split,coords,stops,excluded=attach_far_bus_stops(g,xy,{'one':[1000,3],'two':[1000,7]})
    assert not excluded and stops['one']['node']==stops['two']['node']
    assert len(coords)==3 and np.all(split.data>0)
    assert_existing_distances_preserved(g,split)


def kurtbogazi_fixture():
    # Raw observed OSM edges: southbound way210621589 and northbound way195746359.
    coords=np.array([[32.703942,40.3227648],[32.6986886,40.3041873],
                     [32.6988454,40.3041664],[32.704102,40.322755]])
    xy=project(coords)
    weights=[np.linalg.norm(xy[1]-xy[0])/(75/3.6),np.linalg.norm(xy[3]-xy[2])/(75/3.6)]
    g=csr_matrix((weights,([0,2],[1,3])),shape=(4,4))
    official={'51270':{'lon':32.7011,'lat':40.313097},
              '51271':{'lon':32.701514,'lat':40.313036}}
    return g,coords,official


def test_real_kurtbogazi_51270_51271_restore_the_correct_separate_road_directions():
    g,coords,official=kurtbogazi_fixture();xy=project(coords)
    points=dict(zip(official,project([[s['lon'],s['lat']] for s in official.values()])))
    split,expanded,stops,excluded=attach_far_bus_stops(g,xy,points)
    assert not excluded and len(expanded)==6
    assert stops['51270']['edge']==[0,1] and stops['51270']['snapMeters']==pytest.approx(8.9478,abs=.001)
    assert stops['51271']['edge']==[2,3] and stops['51271']['snapMeters']==pytest.approx(13.3509,abs=.001)
    for code,start,end in [('51270',0,1),('51271',2,3)]:
        node=stops[code]['node']
        assert stops[code]['originalNodeSnapMeters']>1000
        assert np.isfinite(dijkstra(split,indices=start)[node])
        assert np.isfinite(dijkstra(split,indices=node)[end])
        assert not np.isfinite(dijkstra(split,indices=node)[start])
    assert_existing_distances_preserved(g,split)


def test_builder_integration_changes_only_distant_bus_snap_not_walk_or_stop_identity():
    g,coords,official=kurtbogazi_fixture();xy=project(coords)
    registry={code:{'id':code,**s,'driveNode':2,'driveSnapMeters':1010.,
                    'walkNode':15,'walkSnapMeters':1010.,'rail-ANode':8,
                    'coordinateSource':'EGO Başkentkart public stop query'} for code,s in official.items()}
    registry['rail-only']={'id':'rail-only','lon':32.7011,'lat':40.313097,
                           'driveNode':2,'driveSnapMeters':1010.,'walkNode':42}
    before=deepcopy(registry)
    split,new_coords,report=project_bus_stops(g,coords,registry,set(official))
    assert report['projectedStopCount']==report['addedVertexCount']==2
    assert report['attemptedStopCount']==2 and not report['unresolved']
    assert list(registry)==list(before) and registry['rail-only']==before['rail-only']
    for code in official:
        for field in ('id','lon','lat','walkNode','walkSnapMeters','rail-ANode','coordinateSource'):
            assert registry[code][field]==before[code][field]
        assert registry[code]['driveSnapMeters']<15 and registry[code]['driveProjection']['changed']
        record=registry[code]['driveProjection']
        assert record['edgeCoordinates']==coords[record['edge']].tolist()
        assert record['forwardSeconds'] is not None and record['reverseSeconds'] is None
    np.testing.assert_array_equal(new_coords[:len(coords)],coords)
    assert_existing_distances_preserved(g,split)
    # Reprojection of appended coordinates is on the same road, with no stop-to-road ride edge.
    np.testing.assert_allclose(project(new_coords)[registry['51270']['driveNode']],
        xy[0]+report['attachments']['51270']['fraction']*(xy[1]-xy[0]),atol=1e-8)


def test_retry_cannot_escape_projected_edge_to_nearby_opposite_carriageway():
    from scipy.spatial import cKDTree
    point=project([[32.8,39.9],[32.801,39.9]])[0]
    tree=cKDTree([point+[0,3],point+[0,20]])
    stop={'lon':32.8,'lat':39.9,'driveNode':99,'driveSnapMeters':8.,
          'driveProjection':{'edge':[10,11],'changed':True}}
    nodes,distances=bus_retry_vertices(tree,np.array([4,8]),stop)
    assert nodes.tolist()==[99] and distances.tolist()==[8.]
