"""Independent source/order audit of directional bus-stop attachments.

Never import the matcher, graph splitter or timetable builder. Packaged evidence
and optional raw OSM checks are separate: absent raw OSM cannot validate a road,
its permissions, its nearest segment, or the absence of a nearby alternative.
"""
from collections import defaultdict, deque
import hashlib
import json
import math

import numpy as np
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

from scripts.audit_bus_projection import (
    _integer, _number, _original_osm, _require, _xy,
    GEOMETRY_TOLERANCE_METERS, RECORD_TOLERANCE_METERS,
)

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

# Reviewed v0.6 far-stop source records. Only these exact records may be used as
# pre-existing trusted neighbors. Other far-stop attachments retain their
# geometry audit, but do not acquire a source/order exception by adding a key.
BASELINE_FIELDS = (
    'originalNodeSnapMeters', 'node', 'edge', 'fraction', 'snapMeters', 'changed',
    'edgeCoordinates', 'projectedCoordinates', 'forwardSeconds', 'reverseSeconds',
)
BASELINE_SHA256 = {
    '50253': 'a11fcf5b1fbc62b7fbff6a272def875c8a3d9fe6e89fa601a2a932731d296044',
    '51270': 'd548c0311441dde1c08583e8c1ba28d72a721ead13c4282b058885f38fa33f7c',
    '51271': 'ee772e5bad29f6ce3e7624de7c3d888b42c5e81db4e2215d3fbddeaa711e42b9',
}


def _graded(tags):
    return (tags.get('bridge', 'no') not in ('no', 'false', '0') or
            tags.get('tunnel', 'no') not in ('no', 'false', '0') or
            tags.get('layer', '0') not in ('0', '0.0', ''))


class _SourceRoads:
    """Spatial source evidence independent of saved matching decisions."""
    def __init__(self, context):
        self.roads = context['roads']
        self.context = context
        self.lines = [LineString(r['xy']) for r in self.roads]
        self.tree = STRtree(self.lines)

    def nearby(self, point):
        p = Point(point)
        found = [(int(i), float(self.lines[int(i)].distance(p)))
                 for i in self.tree.query(p.buffer(40))]
        return sorted((item for item in found if item[1] <= 40),
                      key=lambda item: (item[1], item[0]))

    def on_way(self, index, point):
        road = self.roads[index]
        xy = road['xy']
        candidates = []
        before = 0.
        for j, (a, b) in enumerate(zip(xy, xy[1:])):
            vector = b-a
            squared = float(vector @ vector)
            if squared <= 1e-12:
                candidates.append((math.inf, j, 0., a, before))
                continue
            fraction = float(np.clip((point-a) @ vector/squared, 0, 1))
            projected = a+fraction*vector
            candidates.append((float(np.linalg.norm(point-projected)), j,
                               fraction, projected, before+fraction*math.sqrt(squared)))
            before += math.sqrt(squared)
        distance, j, fraction, projected, along = min(candidates, key=lambda c: (c[0], c[1]))
        alternatives = [c[0] for c in candidates if c[1] != j and
                        not (c[1] == j-1 and c[2] >= 1-1e-12) and
                        not (c[1] == j+1 and c[2] <= 1e-12)]
        return {'wayId': road['id'], 'segment': j,
                'edge': road['nodes'][j:j+2], 'osmNodeIds': road['osmNodeIds'][j:j+2], 'fraction': fraction,
                'projected': projected, 'edgeDistanceMeters': distance,
                'alongMeters': along, 'direction': road['direction'],
                'sameWayAlternativeMeters': min(alternatives) if alternatives else None}

    def candidate(self, point):
        nearby = self.nearby(point)
        if not nearby or nearby[0][1] > 15:
            return None
        if any(_graded(self.roads[i]['tags']) and d <= 30 for i, d in nearby):
            return None
        i, distance = nearby[0]
        if not self.roads[i]['direction'] or any(d-distance < 10 for _, d in nearby[1:]):
            return None
        c = self.on_way(i, point)
        if not 1e-9 < c['fraction'] < 1-1e-9:
            return None
        alternate = c['sameWayAlternativeMeters']
        if alternate is not None and alternate-distance < 10:
            return None
        c['distinctWayMarginMeters'] = nearby[1][1]-distance if len(nearby) > 1 else None
        return c

    def legacy_evidence(self, point, node):
        nearby = self.nearby(point)
        if not nearby:
            return {'resolved': False, 'reason': 'legacy_anchor_has_no_nearby_bus_way'}
        i, distance = nearby[0]
        c = self.on_way(i, point)
        facts = {'nearestWayId': self.roads[i]['id'], 'edgeDistanceMeters': distance,
                 'nearestEdge': c['edge'], 'oldNodeOnNearestWay': node in self.roads[i]['nodes'],
                 'oldNodeOnNearestSegment': node in c['edge']}
        reason = None
        if any(_graded(self.roads[j]['tags']) and d <= 30 for j, d in nearby):
            reason = 'legacy_neighbor_grade_ambiguity'
        elif not facts['oldNodeOnNearestWay']:
            reason = 'legacy_neighbor_node_not_on_nearest_way'
        elif not facts['oldNodeOnNearestSegment']:
            reason = 'legacy_neighbor_node_not_on_nearest_segment'
        elif np.linalg.norm(self.context['coordinates'][node]-point) > 300:
            reason = 'legacy_neighbor_exceeds_existing_snap_limit'
        if reason:
            return {**facts, 'resolved': False, 'reason': reason}
        facts['sharedEndpointAlternatives'] = []
        for j, d in nearby[1:]:
            if d-distance >= 10:
                continue
            alternate = self.on_way(j, point)
            f = alternate['fraction']
            endpoint = alternate['edge'][0] if f <= 1e-12 else (
                alternate['edge'][1] if f >= 1-1e-12 else None)
            if endpoint not in c['edge']:
                return {**facts, 'resolved': False, 'reason': 'legacy_neighbor_way_alternative_ambiguity'}
            facts['sharedEndpointAlternatives'].append({'wayId': alternate['wayId'], 'sharedNode': endpoint})
        alternate = c['sameWayAlternativeMeters']
        if alternate is not None and alternate-distance < 10:
            return {**facts, 'resolved': False, 'reason': 'legacy_neighbor_same_way_ambiguity'}
        return {**facts, 'resolved': True, 'reason': 'existing_node_on_unambiguous_nearest_road'}

    def legacy(self, point, node):
        return self.legacy_evidence(point, node)['resolved']


def _source_selection(context, registry, pairs, baseline, routing_pairs=None):
    source = _SourceRoads(context)
    routing_pairs = pairs if routing_pairs is None else routing_pairs
    involved = {s for pair in set(pairs) | set(routing_pairs) for s in pair}
    points = {s: _xy([[registry[s]['lon'], registry[s]['lat']]], s)[0]
              for s in involved}
    distances, positions = context['outgoingTree'].query(np.array(list(points.values())))
    old_distance = dict(zip(points, map(float, distances)))
    old_node = dict(zip(points, map(int, context['outgoingIndices'][positions])))
    candidates = {s: c for s, p in points.items() if s not in baseline
                  and (c := source.candidate(p)) is not None}
    witnesses, conflicts, neighbors = defaultdict(list), set(), defaultdict(set)
    for a, b in routing_pairs:
        if a != b:
            neighbors[a].add(b)
            neighbors[b].add(a)
    for a, b in pairs:
        if a == b or a not in candidates or b not in candidates:
            continue
        ca, cb = candidates[a], candidates[b]
        if ca['wayId'] != cb['wayId']:
            continue
        along = (cb['alongMeters']-ca['alongMeters'])*ca['direction']
        straight = float(np.linalg.norm(points[b]-points[a]))
        if not 50 <= abs(along) <= 1000 or abs(along) > straight*2+25:
            continue
        if along < 0:
            conflicts.update((a, b))
        else:
            evidence = {'from': a, 'to': b, 'alongMeters': along}
            witnesses[a].append(evidence)
            witnesses[b].append(evidence)
    initial = {s for s, c in candidates.items() if s not in conflicts and witnesses[s]
               and old_distance[s]-c['edgeDistanceMeters'] >= 10}
    relevant = initial | {v for s in initial for v in neighbors[s]}
    legacy = {s: source.legacy(points[s], old_node[s]) for s in relevant if s not in baseline}
    # Propagation from uncertified unselected neighbors is intentionally unlike
    # the production repeated-removal loop; compare the resulting fixed point.
    queue = deque(s for s in relevant-initial-set(baseline) if not legacy[s])
    removed = set()
    while queue:
        bad = queue.popleft()
        for neighbor in neighbors[bad]:
            if neighbor in initial and neighbor not in removed:
                removed.add(neighbor)
                if not legacy[neighbor]:
                    queue.append(neighbor)
    return {'selected': initial-removed, 'initial': initial, 'removed': removed,
            'candidates': candidates, 'witnesses': witnesses, 'legacy': legacy,
            'oldNode': old_node, 'oldDistance': old_distance, 'points': points,
            'source': source, 'neighbors': neighbors}


def _digest(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _occurrences(values, label):
    _require(isinstance(values, list) and values, label + ': source occurrences missing')
    result = []
    for item in values:
        _require(isinstance(item, dict) and set(item) == {'routeId', 'fromSequence', 'toSequence'},
                 label + ': occurrence fields differ')
        _require(isinstance(item['routeId'], str), label + ': route identity invalid')
        a = _integer(item['fromSequence'], label + ': from sequence')
        b = _integer(item['toSequence'], label + ': to sequence')
        _require(0 <= a < b, label + ': invalid zero-based source sequence order')
        result.append((item['routeId'], a, b))
    _require(len(set(result)) == len(result), label + ': duplicate occurrence')
    return set(result)


def _official_pairs(official, registry):
    _require(isinstance(official, dict) and isinstance(official.get('routes'), list),
             'tracked official routes required for sequence checks')
    direct, routing = defaultdict(set), defaultdict(set)
    route_ids = set()
    for route in official['routes']:
        _require(route['id'] not in route_ids, 'duplicate official route identity')
        route_ids.add(route['id'])
        if route.get('mode') != 'bus':
            continue
        ordered = route['stops']
        for i, (a, b) in enumerate(zip(ordered, ordered[1:])):
            if a['id'] in registry and b['id'] in registry:
                direct[a['id'], b['id']].add((route['id'], i, i+1))
        known = [(i, s) for i, s in enumerate(ordered) if s['id'] in registry]
        for (i, a), (j, b) in zip(known, known[1:]):
            routing[a['id'], b['id']].add((route['id'], i, j))
    return direct, routing


def validate_bus_stop_matching(network, quality, official, osm=None):
    """Validate all saved decisions and, when available, independently raw sources.

    `packagedChecks` is deterministic with or without ignored local OSM files.
    `rawSourceChecks` explicitly states whether source reconstruction took place.
    Neither section establishes measured travel times or surveyed platforms.
    """
    registry = {s['id']: s for s in network['stops']}
    _require(len(registry) == len(network['stops']), 'duplicate stop identity')
    projections = {sid: s['driveProjection'] for sid, s in registry.items() if s.get('driveProjection')}
    selected = {sid: r for sid, r in projections.items() if r.get('method') == 'direction_order'}
    report = quality.get('busStopMatching')
    if report is None:
        _require(not selected, 'direction records lack busStopMatching report')
        return {'status': 'not_applicable', 'packagedChecks': {'directionMatchedStops': 0},
                'rawSourceChecks': {'provided': osm is not None, 'checked': False}}
    _require(isinstance(report, dict) and type(report.get('format')) is int and report['format'] == 1,
             'unsupported busStopMatching format')
    _require(report.get('policyVersion') == POLICY_VERSION, 'unexpected matching policy version')
    _require(isinstance(report.get('policy'), dict), 'matching policy missing')
    for key, value in POLICY.items():
        _require(_number(report['policy'].get(key), key) == value, 'unexpected matching policy ' + key)
    _require(report.get('attachments') == selected, 'matching attachment/stop bijection differs')
    rejected = report.get('rejected')
    _require(isinstance(rejected, dict) and set(rejected).isdisjoint(selected),
             'selected/rejected matching identities overlap')
    direct, routing = _official_pairs(official, registry)
    bus_ids = {s for pair in set(direct) | set(routing) for s in pair}
    _require(set(selected) | set(rejected) == bus_ids, 'selected/rejected identities do not cover official bus stops')

    baseline = report.get('baselineValidation')
    _require(isinstance(baseline, dict) and isinstance(baseline.get('records'), dict),
             'baseline validation missing')
    trusted = baseline.get('trustedStopIds')
    _require(isinstance(trusted, list) and len(trusted) == len(set(trusted)), 'trusted baseline identities invalid')
    _require(set(trusted) <= BASELINE_SHA256.keys(), 'unreviewed baseline identity injected')
    _require(set(baseline['records']) == set(trusted), 'baseline record/identity bijection differs')
    far = {sid: r for sid, r in projections.items() if r.get('method', 'far_edge') == 'far_edge'}
    _require(set(projections) == set(far) | set(selected), 'unknown projection method')
    _require(set(trusted) == set(far), 'far projection/baseline identities differ')
    for sid in trusted:
        entry = baseline['records'][sid]
        record = far[sid]
        _require(entry.get('record') == record, sid + ': baseline record differs from stop')
        _require(entry.get('recordSha256') == _digest(record), sid + ': baseline record checksum differs')
        _require(all(k in record for k in BASELINE_FIELDS), sid + ': baseline evidence incomplete')
        _require(_digest({k: record[k] for k in BASELINE_FIELDS}) == BASELINE_SHA256[sid],
                 sid + ': reviewed baseline source record changed')
        _require(entry.get('trustedForNeighborGuard') is True, sid + ': baseline trust is not established')
        _require(entry.get('edge') == record['edge'], sid + ': baseline edge differs')

    guard = report.get('selectionGuard')
    _require(isinstance(guard, dict) and isinstance(guard.get('withheld'), dict) and
             isinstance(guard.get('legacyAnchorStates'), dict), 'neighbor evidence missing')
    withheld, states = guard['withheld'], guard['legacyAnchorStates']
    _require(set(withheld).isdisjoint(selected), 'selected/withheld identities overlap')
    initial = set(selected) | set(withheld)
    _require(initial <= bus_ids-set(trusted), 'initial matching identities invalid')
    neighbors = defaultdict(set)
    for a, b in routing:
        if a != b:
            neighbors[a].add(b)
            neighbors[b].add(a)
    relevant = initial | {v for s in initial for v in neighbors[s]}
    _require(set(states) == relevant-set(trusted), 'legacy neighbor evidence identity set differs')
    for sid, state in states.items():
        _require(isinstance(state, dict) and isinstance(state.get('resolved'), bool) and
                 isinstance(state.get('reason'), str), sid + ': neighbor result invalid')
    queue = deque(s for s in relevant-initial-set(trusted) if not states[s]['resolved'])
    removed = set()
    while queue:
        bad = queue.popleft()
        for sid in neighbors[bad]:
            if sid in initial and sid not in removed:
                removed.add(sid)
                if not states[sid]['resolved']:
                    queue.append(sid)
    _require(removed == set(withheld), 'saved neighbor decisions are not the declared fixed point')
    for sid, row in withheld.items():
        _require(_integer(row.get('iteration'), sid + ': removal iteration') > 0,
                 sid + ': removal iteration must be positive')
        listed = row.get('neighbors')
        _require(isinstance(listed, list) and listed, sid + ': withholding witnesses missing')
        seen = set()
        for entry in listed:
            other = entry.get('stopId')
            _require(other in neighbors[sid] and other in states and other not in seen,
                     sid + ': invalid withholding neighbor identity')
            seen.add(other)
            _require({k: v for k, v in entry.items() if k != 'stopId'} == states[other]
                     and states[other]['resolved'] is False, sid + ': withholding witness differs')
    for key, expected in [('initialCandidateCount', len(initial)),
                          ('additionalDirectionMatchedStops', len(selected)),
                          ('neighborWithheldStops', len(withheld)),
                          ('originalFarProjectedStops', len(far)),
                          ('combinedProjectedStops', len(projections))]:
        _require(_integer(report.get(key), key) == expected, key + ' differs')
    for key, expected in [('initialSelectedCount', len(initial)), ('retainedCount', len(selected)),
                          ('withheldCount', len(withheld))]:
        _require(_integer(guard.get(key), key) == expected, 'guard ' + key + ' differs')

    for sid, record in selected.items():
        _require(record.get('changed') is True, sid + ': selected record must change its node')
        _require(record.get('policyVersion') == POLICY_VERSION, sid + ': record policy differs')
        _integer(record.get('originalNode'), sid + ': original node')
        _require(registry[sid]['driveNode'] == record.get('node'), sid + ': projected node identity differs')
        evidence = record.get('matchEvidence')
        _require(isinstance(evidence, dict) and isinstance(evidence.get('wayId'), str),
                 sid + ': matching source evidence missing')
        _integer(evidence.get('segmentIndex'), sid + ': source segment')
        _require(evidence.get('direction') in (-1, 1) and not isinstance(evidence.get('direction'), bool),
                 sid + ': source must have one permitted direction')
        _require(isinstance(evidence.get('osmNodeIds'), list) and len(evidence['osmNodeIds']) == 2
                 and len(set(evidence['osmNodeIds'])) == 2, sid + ': source node identities invalid')
        edge_distance = _number(evidence.get('edgeDistanceMeters'), sid + ': edge distance')
        _require(abs(edge_distance-record['snapMeters']) <= RECORD_TOLERANCE_METERS and edge_distance <= 15.01,
                 sid + ': source edge distance differs')
        for field in ('distinctWayMarginMeters', 'sameWayAlternativeMeters'):
            if evidence.get(field) is not None:
                value = _number(evidence[field], sid + ': ' + field)
                margin = value if field == 'distinctWayMarginMeters' else value-edge_distance
                _require(margin >= 10-1e-6, sid + ': reported road ambiguity violates policy')
        witnesses = evidence.get('witnesses')
        _require(isinstance(witnesses, list) and witnesses, sid + ': positive source witness required')
        seen = set()
        for witness in witnesses:
            pair = (witness.get('from'), witness.get('to'))
            _require(sid in pair and pair[0] != pair[1] and pair in direct and pair not in seen,
                     sid + ': witness is not a direct official neighbor')
            seen.add(pair)
            _require(_occurrences(witness.get('officialOccurrences'), sid) == direct[pair],
                     sid + ': witness official occurrences differ')
            along = _number(witness.get('alongMeters'), sid + ': witness distance')
            _require(50 <= along <= 1000, sid + ': witness distance violates policy')
            endpoints = _xy([[registry[s]['lon'], registry[s]['lat']] for s in pair], sid)
            _require(along <= np.linalg.norm(endpoints[1]-endpoints[0])*2+25+1e-6,
                     sid + ': witness detour violates policy')

    expected_pairs = {p for p in routing if p[0] in selected or p[1] in selected}
    rows = report.get('changedPairs')
    _require(isinstance(rows, list), 'changed pair evidence missing')
    saved_pairs = {(r.get('from'), r.get('to')) for r in rows}
    _require(len(saved_pairs) == len(rows) and saved_pairs == expected_pairs,
             'changed pair evidence is incomplete or duplicated')
    for key, segment in network['segments'].items():
        if key.startswith('drive:'):
            parts = key.split(':')
            if len(parts) == 3 and (parts[1] in selected or parts[2] in selected):
                _require((parts[1], parts[2]) in expected_pairs, 'unreported direction-matched segment: ' + key)
    if 'addedVertexCount' in report:
        _require(_integer(report['addedVertexCount'], 'matching added vertex count') ==
                 len({r['node'] for r in projections.values() if 0 < r['fraction'] < 1}),
                 'matching added vertex count differs')
    checked_segments, unresolved = 0, 0
    for row in rows:
        a, b = row['from'], row['to']
        label = a + ':' + b
        _require(_occurrences(row.get('officialOccurrences'), label) == routing[a, b],
                 label + ': changed pair source occurrences differ')
        _require(row.get('sourceNode') == registry[a]['driveNode'] and
                 row.get('destinationNode') == registry[b]['driveNode'], label + ': global endpoint identity differs')
        _require(row.get('retryAttempted') is False and
                 row.get('endpointPolicy') == 'global_direction_match_pair_lock', label + ': endpoint retry is not locked')
        _require(row.get('searchLimitSeconds') == 7200, label + ': search horizon differs')
        xy = _xy([[registry[s]['lon'], registry[s]['lat']] for s in (a, b)], label)
        limit = max(4000., float(np.linalg.norm(xy[1]-xy[0]))*8)
        _require(abs(_number(row.get('geometryLimitMeters'), label)-limit) <= .01,
                 label + ': geometry limit differs')
        for sid in (a, b):
            stop = registry[sid]
            point = _xy([stop.get('driveNodeCoordinates')], sid)[0]
            physical = _xy([[stop['lon'], stop['lat']]], sid)[0]
            _require(abs(np.linalg.norm(point-physical)-_number(stop['driveSnapMeters'], sid)) <= .01,
                     sid + ': global anchor coordinate/snap differs')
            if sid in projections:
                _require(np.linalg.norm(point-_xy([projections[sid]['projectedCoordinates']], sid)[0]) <= .01,
                         sid + ': global projected anchor differs')
        segment = network['segments'].get('drive:'+label)
        if row.get('status') == 'accepted':
            _require(segment is not None, label + ': accepted pair has no segment')
            for field in ('endpointPolicy', 'sourceNode', 'destinationNode', 'retryAttempted'):
                _require(segment.get(field) == row[field], label + ': segment endpoint evidence differs')
            for field in ('meters', 'secondsWeight'):
                value = _number(row.get(field), label + ': ' + field)
                _require(value >= 0 and math.isclose(value, _number(segment.get(field), label),
                         abs_tol=1e-6, rel_tol=1e-9), label + ': segment cost evidence differs')
            _require(row['meters'] <= limit+.01, label + ': accepted geometry exceeds gate')
            _require(row.get('reason') is None, label + ': accepted pair carries failure reason')
            _require(math.isclose(_number(row.get('rawFixedMeters'), label), row['meters'], abs_tol=1e-6) and
                     math.isclose(_number(row.get('rawFixedSeconds'), label), row['secondsWeight'], abs_tol=1e-6),
                     label + ': accepted fixed cost differs')
            points = _xy(segment['coordinates'], label)
            _require(np.linalg.norm(points[0]-_xy([registry[a]['driveNodeCoordinates']], a)[0]) <= GEOMETRY_TOLERANCE_METERS
                     and np.linalg.norm(points[-1]-_xy([registry[b]['driveNodeCoordinates']], b)[0]) <= GEOMETRY_TOLERANCE_METERS,
                     label + ': geometry does not use both locked global anchors')
            checked_segments += 1
        else:
            _require(row.get('status') == 'unresolved' and segment is None,
                     label + ': unresolved pair must not publish a segment')
            _require(row.get('meters') is None and row.get('secondsWeight') is None and
                     isinstance(row.get('reason'), str) and row['reason'], label + ': unresolved cost/reason invalid')
            reason = row['reason']
            raw_seconds, raw_meters = row.get('rawFixedSeconds'), row.get('rawFixedMeters')
            for value in (raw_seconds, raw_meters):
                if value is not None:
                    _require(_number(value, label) >= 0, label + ': negative unresolved raw cost')
            if reason == 'fixed_anchor_exceeds_existing_snap_limit':
                _require(max(registry[a]['driveSnapMeters'], registry[b]['driveSnapMeters']) > 300,
                         label + ': claimed snap failure is unsupported')
            elif reason == 'unresolved_within_7200_second_search':
                _require(raw_seconds is None and raw_meters is None, label + ': search failure carries finite path')
            elif reason == 'fixed_anchor_exceeds_existing_geometry_gate':
                _require(raw_seconds is not None and raw_seconds <= 7200 and
                         (raw_meters is None or raw_meters > limit), label + ': geometry failure is unsupported')
            else:
                _require(False, label + ': unknown fixed-anchor failure reason')
            unresolved += 1

    raw_result = {'provided': osm is not None, 'checked': False,
                  'omission': 'Raw OSM unavailable: road identity, nearest segment, direction, ambiguity and raw fixed point not independently checked.'}
    if osm is not None:
        _, _, _, context = _original_osm(osm, {tuple(sorted(r['edge'])) for r in projections.values()}, include_roads=True)
        expected = _source_selection(context, registry, direct, set(trusted), routing)
        for sid in trusted:
            entry, record = baseline['records'][sid], far[sid]
            point = _xy([[registry[sid]['lon'], registry[sid]['lat']]], sid)[0]
            nearby = expected['source'].nearby(point)
            _require(bool(nearby), sid + ': baseline has no nearby source road')
            i, distance = nearby[0]
            candidate = expected['source'].on_way(i, point)
            _require(entry.get('wayId') == candidate['wayId'] and entry.get('segmentIndex') == candidate['segment'] and
                     entry.get('edge') == candidate['edge'] and set(record['edge']) == set(candidate['edge']),
                     sid + ': baseline source road/segment evidence differs')
            _require(not any(_graded(context['roads'][j]['tags']) and d <= 30 for j, d in nearby) and
                     all(d-distance >= 10 for _, d in nearby[1:]) and
                     (candidate['sameWayAlternativeMeters'] is None or candidate['sameWayAlternativeMeters']-distance >= 10),
                     sid + ': trusted baseline has raw road ambiguity')
            _require(entry.get('reason') is None, sid + ': trusted baseline carries an exclusion reason')
            old_distance, position = context['outgoingTree'].query(point)
            _require(record.get('originalNode') == int(context['outgoingIndices'][position]) and
                     old_distance > 300 and abs(old_distance-record['originalNodeSnapMeters']) <= .01,
                     sid + ': baseline old node does not match raw source')
        _require(expected['initial'] == initial and expected['selected'] == set(selected),
                 'raw source matching/neighbor fixed point differs from saved selection')
        _require(set(expected['legacy']) == set(states), 'raw neighbor evidence identity set differs')
        for sid, resolved in expected['legacy'].items():
            _require(states[sid]['resolved'] == resolved, sid + ': raw legacy anchor decision differs')
            facts = expected['source'].legacy_evidence(expected['points'][sid], expected['oldNode'][sid])
            for field, value in facts.items():
                if field == 'edgeDistanceMeters':
                    _require(abs(_number(states[sid].get(field), sid)-value) <= .01,
                             sid + ': raw neighbor distance evidence differs')
                else:
                    _require(states[sid].get(field) == value, sid + ': raw neighbor source evidence differs: ' + field)
            _require(set(states[sid]) == set(facts), sid + ': unexpected neighbor source evidence fields')
        for sid, record in selected.items():
            c, evidence = expected['candidates'][sid], record['matchEvidence']
            _require(record['originalNode'] == expected['oldNode'][sid] and
                     abs(record['originalNodeSnapMeters']-expected['oldDistance'][sid]) <= .01,
                     sid + ': original node/distance differs from raw source')
            _require(evidence['wayId'] == c['wayId'] and evidence['segmentIndex'] == c['segment'] and
                     evidence['osmNodeIds'] == c['osmNodeIds'] and evidence['direction'] == c['direction'],
                     sid + ': raw way/segment/direction evidence differs')
            _require(set(record['edge']) == set(c['edge']), sid + ': projected edge differs from source match')
            _require(np.linalg.norm(_xy([record['projectedCoordinates']], sid)[0]-c['projected']) <= .01,
                     sid + ': raw nearest projection differs')
            for field in ('edgeDistanceMeters', 'distinctWayMarginMeters', 'sameWayAlternativeMeters'):
                actual, saved = c[field], evidence.get(field)
                _require((actual is None) == (saved is None), sid + ': raw alternative evidence differs')
                if actual is not None:
                    _require(abs(actual-_number(saved, sid)) <= .01, sid + ': raw distance/margin evidence differs')
            wanted = {(w['from'], w['to']): w['alongMeters'] for w in expected['witnesses'][sid]}
            reported = {(w['from'], w['to']): w['alongMeters'] for w in evidence['witnesses']}
            _require(wanted.keys() == reported.keys() and all(abs(v-reported[k]) <= .01 for k, v in wanted.items()),
                     sid + ': raw source witnesses differ')
        for row in rows:
            for sid in (row['from'], row['to']):
                if sid in projections:
                    continue
                point = context['coordinates'][_integer(registry[sid]['driveNode'], sid)]
                _require(np.linalg.norm(point-_xy([registry[sid]['driveNodeCoordinates']], sid)[0]) <= .01,
                         sid + ': legacy anchor coordinates differ from raw node')
        raw_result = {'provided': True, 'checked': True, 'omission': None,
                      'initialSourceSelectedStops': len(initial), 'sourceMatchedStops': len(selected),
                      'legacyNeighborDecisionsChecked': len(states)}
    return {'status': 'passed', 'packagedChecks': {
                'directionMatchedStops': len(selected), 'reviewedFarBaselineStops': len(trusted),
                'initialCandidateStops': len(initial), 'neighborWithheldStops': len(withheld),
                'changedOfficialPairs': len(rows), 'acceptedLockedSegments': checked_segments,
                'unresolvedLockedPairs': unresolved, 'officialSequenceEvidenceChecked': True,
                'scope': 'Saved source-order and global-anchor evidence; not measured routes, surveyed boarding points, or calibrated travel time.'},
            'rawSourceChecks': raw_result}
