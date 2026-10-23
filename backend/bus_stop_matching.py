"""Conservative direction/order matching on existing bus-road edges.

The policy is source consistency, not a measured boarding entrance or GPS route.
Ambiguous neighbors withhold a stop globally. Both audited anchors are fixed on
any affected journey leg. No car/walk graph or original vertex index changes.
"""
from collections import Counter, defaultdict
import hashlib
import json
import numpy as np
from scipy.sparse import csr_matrix
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree
from backend.geo import project, PROJECT

POLICY_VERSION = 'direction-order-neighbor-lock-v1'
POLICY = {
    'maximumEdgeDistanceMeters': 15.,
    'minimumVertexImprovementMeters': 10.,
    'minimumAlternativeMarginMeters': 10.,
    'gradeAmbiguityRadiusMeters': 30.,
    'minimumWitnessAlongMeters': 50.,
    'maximumWitnessAlongMeters': 1000.,
    'maximumWitnessDetourRatio': 2.,
    'witnessDetourToleranceMeters': 25.,
    'lockedPathLimitSeconds': 7200.,
}


def graded(tags):
    return (tags.get('bridge', 'no') not in ('no', 'false', '0') or
            tags.get('tunnel', 'no') not in ('no', 'false', '0') or
            tags.get('layer', '0') not in ('0', '0.0', ''))


class RoadIndex:
    """Ways retain distinct physical identities even where geometry crosses."""
    def __init__(self, ways):
        self.ways = ways
        self.lines = [LineString(w['xy']) for w in ways]
        self.tree = STRtree(self.lines)

    def query(self, point, radius):
        p = Point(point)
        return [(int(i), float(self.lines[i].distance(p)))
                for i in self.tree.query(p.buffer(radius))
                if self.lines[i].distance(p) <= radius]

    def segment(self, index, point):
        w = self.ways[index]
        xy = np.asarray(w['xy'], dtype=float)
        vectors = np.diff(xy, axis=0)
        lengths2 = np.einsum('ij,ij->i', vectors, vectors)
        fractions = np.clip(np.divide(np.einsum('ij,ij->i', point-xy[:-1], vectors), lengths2,
                                     out=np.zeros(len(vectors)), where=lengths2 > 0), 0, 1)
        projected = xy[:-1] + fractions[:, None] * vectors
        distances = np.linalg.norm(projected-point, axis=1)
        distances[lengths2 <= 1e-12] = np.inf
        s = int(distances.argmin())
        # A way can double back, including an immediately adjacent hairpin.
        # Only an adjacent segment whose nearest point is the SAME shared
        # endpoint is ordinary continuation rather than a second attachment.
        alternative=[]
        for j,d in enumerate(distances):
            if j==s: continue
            if j==s-1 and fractions[j]>=1-1e-12: continue
            if j==s+1 and fractions[j]<=1e-12: continue
            alternative.append(float(d))
        along = float(np.sqrt(lengths2[:s]).sum()+fractions[s]*np.sqrt(lengths2[s]))
        return {'wayId': str(w['id']), 'wayIndex': index, 'segment': s,
                'edge': [int(w['nodes'][s]), int(w['nodes'][s+1])],
                'fraction': float(fractions[s]), 'projected': projected[s].tolist(),
                'edgeDistanceMeters': float(distances[s]), 'alongMeters': along,
                'direction': w['direction'],
                'sameWayAlternativeMeters': min(alternative) if alternative else None}


def select_attachments(index, points, original_snap, official_pairs, baseline=()):
    """Fail closed on nearby alternatives, grade or conflicting local order.

    A stop needs at least one short consecutive official pair on the SAME
    one-way way. This is positive source-consistency evidence, not proof of
    the real vehicle trajectory. Stops without it keep their old attachment.
    """
    selected, rejected, candidates = {}, {}, {}
    for code, point in points.items():
        if code in baseline:
            rejected[code] = 'retained_existing_projection'
            continue
        nearby = sorted(index.query(point, 40.), key=lambda value: (value[1], value[0]))
        if not nearby or nearby[0][1] > POLICY['maximumEdgeDistanceMeters']:
            rejected[code] = 'no_bus_way_within_edge_limit'
            continue
        wi, distance = nearby[0]
        w = index.ways[wi]
        if any(graded(index.ways[j]['tags']) and d <= POLICY['gradeAmbiguityRadiusMeters']
               for j,d in nearby):
            rejected[code] = 'grade_or_nearby_grade_ambiguity'
            continue
        if not w['direction']:
            rejected[code] = 'two_way_road_without_direction_witness'
            continue
        if len(nearby)>1 and nearby[1][1]-distance < POLICY['minimumAlternativeMarginMeters']:
            rejected[code] = 'nearby_distinct_way_ambiguity'
            continue
        record = index.segment(wi, np.asarray(point))
        record['distinctWayMarginMeters'] = nearby[1][1]-distance if len(nearby)>1 else None
        if (record['sameWayAlternativeMeters'] is not None and
            record['sameWayAlternativeMeters']-distance < POLICY['minimumAlternativeMarginMeters']):
            rejected[code] = 'same_way_segment_ambiguity'
            continue
        if not 1e-9 < record['fraction'] < 1-1e-9:
            rejected[code] = 'projection_at_existing_endpoint'
            continue
        # Keep close candidates as witnesses even if their old vertex is good.
        candidates[code] = record

    witnesses, conflicts = defaultdict(list), defaultdict(list)
    for a,b in official_pairs:
        if a == b or a not in candidates or b not in candidates:
            continue
        ca,cb = candidates[a], candidates[b]
        if ca['wayId'] != cb['wayId']:
            continue
        signed = (cb['alongMeters']-ca['alongMeters'])*ca['direction']
        straight = float(np.linalg.norm(np.asarray(points[a])-points[b]))
        if not POLICY['minimumWitnessAlongMeters'] <= abs(signed) <= POLICY['maximumWitnessAlongMeters']:
            continue
        if abs(signed) > straight*POLICY['maximumWitnessDetourRatio']+POLICY['witnessDetourToleranceMeters']:
            continue
        evidence = {'from': a, 'to': b, 'alongMeters': signed}
        if signed < 0:
            conflicts[a].append(evidence); conflicts[b].append(evidence)
        else:
            witnesses[a].append(evidence); witnesses[b].append(evidence)

    for code,record in candidates.items():
        improvement = original_snap[code]-record['edgeDistanceMeters']
        if conflicts[code]:
            rejected[code] = 'official_local_order_conflicts_with_oneway'
        elif not witnesses[code]:
            rejected[code] = 'no_unambiguous_same_way_forward_order_witness'
        elif improvement < POLICY['minimumVertexImprovementMeters']:
            rejected[code] = 'original_vertex_already_close'
        else:
            selected[code] = {**record, 'originalSnapMeters': original_snap[code],
                              'improvementMeters': improvement, 'witnesses': witnesses[code]}
    return selected, rejected


def split_edges(graph, xy, records):
    """Insert only vertices on original edge identities; preserve both costs.

    Existing vertex indices and all directed path distances remain invariant.
    Different source edges are never joined by coincident coordinate values.
    """
    graph=graph.tocsr(copy=True); graph.sum_duplicates(); graph.sort_indices()
    coo=graph.tocoo(); n=graph.shape[0]
    keys=coo.row.astype(np.int64)*n+coo.col
    keep=np.ones(len(keys), dtype=bool)
    extra_rows=[]; extra_cols=[]; extra_cost=[]
    # Already published virtual vertices retain their indices as well as their
    # physical edge/fraction. New experimental vertices follow those indices.
    pinned={int(r['node']):code for code,r in records.items() if 'node' in r and int(r['node'])>=n}
    if pinned and set(pinned)!=set(range(n,max(pinned)+1)):
        raise ValueError('Pinned virtual indices must be contiguous after original vertices')
    additions=[None]*len(pinned); assigned={}; groups=defaultdict(list)
    for code,r in records.items():
        a,b=map(int,r['edge']); f=float(r['fraction'])
        if not 0<f<1: raise ValueError('Interior edge fractions required')
        if a>b: a,b,f=b,a,1-f
        groups[a,b].append((f,code))
    for (a,b), entries in sorted(groups.items()):
        costs={}
        for u,v in ((a,b),(b,a)):
            key=u*n+v; at=int(np.searchsorted(keys,key))
            if at<len(keys) and keys[at]==key:
                keep[at]=False; costs[u,v]=float(coo.data[at])
        if not costs: raise ValueError('Cannot split an absent edge')
        ordered=[(0.,a)]
        for f,code in sorted(entries,key=lambda entry:(entry[0],0 if 'node' in records[entry[1]] else 1,entry[1])):
            if abs(f-ordered[-1][0])<1e-12:
                node=ordered[-1][1]
            else:
                point=xy[a]+f*(xy[b]-xy[a])
                if 'node' in records[code] and int(records[code]['node'])>=n:
                    node=int(records[code]['node']); additions[node-n]=point
                else:
                    node=n+len(additions); additions.append(point)
                ordered.append((f,node))
            assigned[code]=node
        ordered.append((1.,b))
        for (u,v), cost in costs.items():
            chain=ordered if u==a else ordered[::-1]
            for (f,start),(g,end) in zip(chain[:-1],chain[1:]):
                extra_rows.append(start); extra_cols.append(end); extra_cost.append(abs(g-f)*cost)
    if any(point is None for point in additions): raise ValueError('Unfilled pinned virtual vertex')
    new_xy=np.vstack([xy,additions]) if additions else xy.copy()
    result=csr_matrix((np.r_[coo.data[keep],extra_cost],
                       (np.r_[coo.row[keep],extra_rows],np.r_[coo.col[keep],extra_cols])),
                      shape=(len(new_xy),len(new_xy)))
    return result,new_xy,assigned


def classify_legacy_anchor(index,point,node):
    nearby=sorted(index.query(point,40),key=lambda item:(item[1],item[0]))
    if not nearby:return {'resolved':False,'reason':'legacy_anchor_has_no_nearby_bus_way'}
    wi,distance=nearby[0];way=index.ways[wi];candidate=index.segment(wi,np.asarray(point))
    metadata={'nearestWayId':str(way['id']),'edgeDistanceMeters':distance,
              'nearestEdge':candidate['edge'],
              'oldNodeOnNearestWay':int(node) in way['nodes'],
              'oldNodeOnNearestSegment':int(node) in candidate['edge']}
    if any(graded(index.ways[j]['tags']) and d<=30 for j,d in nearby):
        return {**metadata,'resolved':False,'reason':'legacy_neighbor_grade_ambiguity'}
    if not metadata['oldNodeOnNearestWay']:
        return {**metadata,'resolved':False,'reason':'legacy_neighbor_node_not_on_nearest_way'}
    if not metadata['oldNodeOnNearestSegment']:
        return {**metadata,'resolved':False,'reason':'legacy_neighbor_node_not_on_nearest_segment'}
    vertex=np.asarray(way['xy'][way['nodes'].index(int(node))])
    if np.linalg.norm(vertex-np.asarray(point))>300:
        return {**metadata,'resolved':False,'reason':'legacy_neighbor_exceeds_existing_snap_limit'}
    # Direction alone cannot remove ambiguity between distinct parallel roads.
    # Exempt only an alternative whose nearest point is an actual shared OSM
    # endpoint of the PRIMARY nearest segment, not merely the same way ID.
    metadata['sharedEndpointAlternatives']=[]
    for other,d in nearby[1:]:
        if d-distance>=10: continue
        alternate=index.segment(other,np.asarray(point));fraction=alternate['fraction']
        endpoint=(alternate['edge'][0] if fraction<=1e-12 else
                  (alternate['edge'][1] if fraction>=1-1e-12 else None))
        if endpoint is not None and endpoint in candidate['edge']:
            metadata['sharedEndpointAlternatives'].append({'wayId':alternate['wayId'],'sharedNode':endpoint})
            continue
        return {**metadata,'resolved':False,'reason':'legacy_neighbor_way_alternative_ambiguity'}
    alternative=candidate['sameWayAlternativeMeters']
    if alternative is not None and alternative-distance<10:
        return {**metadata,'resolved':False,'reason':'legacy_neighbor_same_way_ambiguity'}
    return {**metadata,'resolved':True,'reason':'existing_node_on_unambiguous_nearest_road'}


def coherent_selection(index,points,old_nodes,official_pairs,baseline,selected):
    if not isinstance(baseline, ValidatedBaselines):
        raise TypeError('Baseline trust requires source validation')
    neighbors=defaultdict(set)
    for a,b in official_pairs:
        if a!=b:neighbors[a].add(b);neighbors[b].add(a)
    # Classify the OLD anchor for every potentially exposed neighbor. If a
    # selected anchor is withheld, its old anchor becomes exposed next round.
    relevant={b for a in selected for b in neighbors[a]}|set(selected)
    states={code:classify_legacy_anchor(index,points[code],old_nodes[code])
            for code in relevant if code not in baseline}
    retained=dict(selected); withheld={};iteration=0
    while True:
        iteration+=1;remove={}
        for code in retained:
            unresolved=[neighbor for neighbor in sorted(neighbors[code])
                        if neighbor not in retained and neighbor not in baseline and
                        not states[neighbor]['resolved']]
            if unresolved:
                remove[code]={'iteration':iteration,'neighbors':[
                    {'stopId':s,**states[s]} for s in unresolved]}
        if not remove:break
        for code,why in remove.items():retained.pop(code);withheld[code]=why
    assert all(neighbor in retained or neighbor in baseline or states[neighbor]['resolved']
               for code in retained for neighbor in neighbors[code])
    report={'scope':'Neighbor-based fixed point. Withholding applies to the stop globally, not one leg. '
                    'No cost/outcome is used. Conservative omissions remain unknown service geometry.',
        'initialSelectedCount':len(selected),'retainedCount':len(retained),'withheldCount':len(withheld),
        'iterationsWithRemovals':iteration-1,'withheld':withheld,
        'reasonCounts':dict(Counter(s['reason'] for r in withheld.values() for s in r['neighbors'])),
        'legacyAnchorStates':states}
    return retained,report



class ValidatedBaselines(frozenset):
    """IDs whose full projection records passed independent source checks."""


def record_sha256(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def validate_baselines(graph, coords, index, registry, baseline):
    """Verify identity, coordinates, direction/cost and local source ambiguity.

    A malformed or injected record fails the build. A genuine far projection
    with unclear nearby roads remains a far projection but cannot exempt a new
    neighbor from the coherence guard. No arbitrary baseline key is trusted.
    """
    xy=project(coords); n=len(coords); trusted=set(); checks={}
    valid=np.flatnonzero(np.diff(graph.indptr)>0)
    original_tree=cKDTree(xy[valid]) if len(valid) else None
    for code,record in baseline.items():
        stop=registry.get(code)
        required=('node','edge','fraction','edgeCoordinates','projectedCoordinates',
                  'forwardSeconds','reverseSeconds','originalNode','originalNodeSnapMeters','snapMeters')
        if (stop is None or stop.get('driveProjection')!=record or
            any(k not in record for k in required) or not record.get('changed')):
            raise ValueError(f'Invalid baseline projection identity: {code}')
        a,b=map(int,record['edge']); fraction=float(record['fraction']); old=int(record['originalNode'])
        if (not 0<=a<n or not 0<=b<n or a==b or not 0<fraction<1 or
            not 0<=old<n or int(record['node'])<n or stop['driveNode']!=record['node']):
            raise ValueError(f'Invalid baseline source edge/node: {code}')
        point=project([[stop['lon'],stop['lat']]])[0]
        nearest_vertex_distance=float(original_tree.query(point)[0]) if original_tree is not None else np.inf
        if (graph.indptr[old+1]==graph.indptr[old] or nearest_vertex_distance<=300 or
            not np.isclose(nearest_vertex_distance,record['originalNodeSnapMeters'],atol=1e-6,rtol=0)):
            raise ValueError(f'Baseline did not originate at the closest distant outgoing vertex: {code}')
        expected=xy[a]+fraction*(xy[b]-xy[a])
        if (not np.allclose(record['edgeCoordinates'],coords[[a,b]],atol=1e-10,rtol=0) or
            not np.allclose(project([record['projectedCoordinates']])[0],expected,atol=1e-6,rtol=0) or
            not np.isclose(record['snapMeters'],np.linalg.norm(point-expected),atol=1e-6,rtol=0) or
            not np.isclose(record['originalNodeSnapMeters'],np.linalg.norm(point-xy[old]),atol=1e-6,rtol=0)):
            raise ValueError(f'Baseline projection coordinates do not match source: {code}')
        for u,v,key in ((a,b,'forwardSeconds'),(b,a,'reverseSeconds')):
            actual=float(graph[u,v]); reported=record[key]
            if (actual<=0 and reported is not None) or (actual>0 and
                    (reported is None or not np.isclose(actual,reported,rtol=1e-10,atol=1e-8))):
                raise ValueError(f'Baseline projection direction/cost mismatch: {code}')
        nearby=sorted(index.query(point,40.),key=lambda item:(item[1],item[0]))
        if not nearby:
            raise ValueError(f'Baseline projection lacks a nearby raw source road: {code}')
        wi,distance=nearby[0]; candidate=index.segment(wi,point)
        # A nearest whole way is not sufficient: its local segment must match.
        expected_fraction=candidate['fraction'] if candidate['edge']==[a,b] else 1-candidate['fraction']
        if (set(candidate['edge'])!={a,b} or not np.isclose(fraction,expected_fraction,atol=1e-10,rtol=0)):
            raise ValueError(f'Baseline projection does not match nearest raw segment: {code}')
        reason=None
        if any(graded(index.ways[j]['tags']) and d<=30 for j,d in nearby):
            reason='baseline_nearby_grade_ambiguity'
        elif len(nearby)>1 and nearby[1][1]-distance<10:
            reason='baseline_distinct_way_ambiguity'
        elif candidate['sameWayAlternativeMeters'] is not None and candidate['sameWayAlternativeMeters']-distance<10:
            reason='baseline_same_way_ambiguity'
        if reason is None:trusted.add(code)
        checks[code]={'recordSha256':record_sha256(record),'record':record,
            'wayId':candidate['wayId'],'segmentIndex':candidate['segment'],
            'edge':candidate['edge'],'trustedForNeighborGuard':reason is None,'reason':reason}
    pinned=[int(r['node']) for r in baseline.values()]
    if len(set(pinned))!=len(pinned) or set(pinned)!=set(range(n,n+len(pinned))):
        raise ValueError('Baseline virtual indices must be unique and contiguous')
    return ValidatedBaselines(trusted), {'trustedStopIds':sorted(trusted),'records':checks}


def official_bus_pairs(official, registry, bridge_missing=False):
    """Raw occurrences; optional missing-stop bridging is for guard/routing only.

    Direction witnesses always use the default, strictly consecutive mode.
    """
    pairs=defaultdict(list)
    for route in official['routes']:
        if route['mode']!='bus':continue
        ordered=[(i,s) for i,s in enumerate(route['stops']) if not bridge_missing or s['id'] in registry]
        for (i,a),(j,b) in zip(ordered[:-1],ordered[1:]):
            if a['id'] in registry and b['id'] in registry:
                pairs[a['id'],b['id']].append({'routeId':route['id'],
                    'fromSequence':i,'toSequence':j})
    return dict(pairs)


def match_bus_stops(graph, coords, roads, registry, official_pairs, baseline, routing_pairs=None):
    """Return combined bus graph, coordinates and full matching audit.

    Input graph/coords are ORIGINAL bus vertices, before far-stop splitting.
    Baseline records have already been created by the separate far policy.
    Only new selected stops' drive fields change; all original indices, walking
    anchors and existing far projection records retain their identities.
    """
    index=RoadIndex(roads)
    trusted,baseline_report=validate_baselines(graph,coords,index,registry,baseline)
    routing_pairs=official_pairs if routing_pairs is None else routing_pairs
    bus_ids={s for pair in routing_pairs for s in pair}
    points={s:project([[registry[s]['lon'],registry[s]['lat']]])[0] for s in sorted(bus_ids)}
    original_snap={s:float(registry[s]['driveSnapMeters']) for s in points}
    selected,rejected=select_attachments(index,points,original_snap,official_pairs,baseline)
    initial_count=len(selected)
    selected,guard=coherent_selection(index,points,{s:registry[s]['driveNode'] for s in points},
                                      routing_pairs,trusted,selected)
    for code in guard['withheld']:rejected[code]='neighbor_coherence_guard'
    combined={**baseline,**selected}
    result,expanded,nodes=split_edges(graph,project(coords),combined)
    if len(expanded)>len(coords):
        extra=np.array([PROJECT.transform(float(x),float(y),direction='INVERSE') for x,y in expanded[len(coords):]])
        new_coords=np.vstack([coords,extra])
    else:new_coords=coords.copy()
    attachments={}
    for code,candidate in selected.items():
        stop=registry[code];a,b=candidate['edge'];way=roads[candidate['wayIndex']];seg=candidate['segment']
        evidence={'wayId':candidate['wayId'],'segmentIndex':seg,
            'osmNodeIds':list(way['osmNodes'][seg:seg+2]),'direction':candidate['direction'],
            'edgeDistanceMeters':candidate['edgeDistanceMeters'],
            'distinctWayMarginMeters':candidate['distinctWayMarginMeters'],
            'sameWayAlternativeMeters':candidate['sameWayAlternativeMeters'],
            'witnesses':[{**w,'officialOccurrences':official_pairs[w['from'],w['to']]} for w in candidate['witnesses']]}
        record={'method':'direction_order','policyVersion':POLICY_VERSION,'changed':True,
            'originalNode':int(stop['driveNode']),'originalNodeSnapMeters':float(stop['driveSnapMeters']),
            'node':int(nodes[code]),'snapMeters':candidate['edgeDistanceMeters'],
            'edge':[int(a),int(b)],'fraction':candidate['fraction'],
            'edgeCoordinates':coords[[a,b]].tolist(),'projectedCoordinates':new_coords[nodes[code]].tolist(),
            'forwardSeconds':float(graph[a,b]) if graph[a,b]>0 else None,
            'reverseSeconds':float(graph[b,a]) if graph[b,a]>0 else None,'matchEvidence':evidence}
        stop.update({'driveNode':nodes[code],'driveSnapMeters':record['snapMeters'],'driveProjection':record})
        attachments[code]=record
    for code,record in baseline.items():
        if nodes[code]!=record['node']:raise RuntimeError('Existing projection node index changed')
    for stop in registry.values():stop['driveNodeCoordinates']=new_coords[stop['driveNode']].tolist()
    return result,new_coords,{'format':1,'policyVersion':POLICY_VERSION,'policy':POLICY,
        'scope':'Partial conservative source consistency, not measured boarding entrances or GPS routes. '
                'Longer legal paths remain visible. Missing grade/access tags and unchanged legacy snaps remain uncertain.',
        'initialCandidateCount':initial_count,'additionalDirectionMatchedStops':len(selected),
        'neighborWithheldStops':guard['withheldCount'],'originalFarProjectedStops':len(baseline),
        'combinedProjectedStops':len(combined),'addedVertexCount':len(expanded)-len(coords),
        'attachments':attachments,'rejected':rejected,'rejectionCounts':dict(Counter(rejected.values())),
        'selectionGuard':guard,'baselineValidation':baseline_report,'changedPairs':[]}


def requires_locked_endpoints(source_stop,target_stop,direction_matched_stop_ids):
    return source_stop in direction_matched_stop_ids or target_stop in direction_matched_stop_ids


def locked_pair_result(start,end,seconds,meters,stop_distance):
    """Classify the actual fixed endpoints without considering alternatives."""
    limit=max(4000.,float(stop_distance)*8)
    seconds=float(seconds) if np.isfinite(seconds) else None
    meters=float(meters) if np.isfinite(meters) else None
    reason=('unresolved_within_7200_second_search' if seconds is None else
            ('fixed_anchor_exceeds_existing_geometry_gate' if meters is None or meters>limit else None))
    return {'sourceNode':int(start),'destinationNode':int(end),
        'endpointPolicy':'global_direction_match_pair_lock','retryAttempted':False,
        'status':'accepted' if reason is None else 'unresolved','reason':reason,
        'searchLimitSeconds':7200,'geometryLimitMeters':limit,
        'rawFixedSeconds':seconds,'rawFixedMeters':meters,
        'secondsWeight':seconds if reason is None else None,'meters':meters if reason is None else None}
