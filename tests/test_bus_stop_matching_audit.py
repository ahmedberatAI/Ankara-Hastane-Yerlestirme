"""Hand-authored saved-artifact fixtures; no production matching construction."""
from copy import deepcopy

import numpy as np
from pyproj import Transformer
import pytest

from scripts.audit_bus_projection import validate_bus_projections
from scripts.audit_bus_stop_matching import validate_bus_stop_matching, POLICY, POLICY_VERSION, _SourceRoads

TO_LL = Transformer.from_crs(32636, 4326, always_xy=True)


def ll(x, y=0):
    return list(TO_LL.transform(500000+x, 4400000+y))


def fixture():
    seconds = 1000/(55/3.6)
    occurrences = [{'routeId': 'R', 'fromSequence': 0, 'toSequence': 1}]
    witness = {'from': 'A', 'to': 'B', 'alongMeters': 500., 'officialOccurrences': occurrences}
    records, stops = {}, []
    for sid, x, node in [('A', 200., 2), ('B', 700., 3)]:
        record = {'changed': True, 'method': 'direction_order', 'policyVersion': POLICY_VERSION, 'originalNode': 0,
                  'originalNodeSnapMeters': float(np.hypot(x, 5)), 'node': node,
                  'edge': [0, 1], 'fraction': x/1000, 'edgeCoordinates': [ll(0), ll(1000)],
                  'projectedCoordinates': ll(x), 'snapMeters': 5.,
                  'forwardSeconds': seconds, 'reverseSeconds': None,
                  'matchEvidence': {'wayId': '100', 'segmentIndex': 0, 'osmNodeIds': [10, 20],
                    'direction': 1, 'edgeDistanceMeters': 5., 'distinctWayMarginMeters': None,
                    'sameWayAlternativeMeters': None, 'witnesses': [deepcopy(witness)]}}
        records[sid] = record
        lon, lat = ll(x, 5)
        stops.append({'id': sid, 'lon': lon, 'lat': lat, 'driveNode': node,
                      'driveSnapMeters': 5., 'driveNodeCoordinates': ll(x),
                      'driveProjection': deepcopy(record)})
    lock = {'endpointPolicy': 'global_direction_match_pair_lock', 'sourceNode': 2,
            'destinationNode': 3, 'retryAttempted': False}
    network = {'stops': stops, 'segments': {'drive:A:B': {
        'coordinates': np.round([ll(200), ll(700)], 6).tolist(), 'meters': 500.,
        'secondsWeight': seconds*.5, **lock}}}
    quality = {'busStopProjection': {'policy': {'maximumSnapMeters': 300},
                'attachments': {}, 'unresolved': {}, 'attemptedStopCount': 0,
                'projectedStopCount': 0, 'addedVertexCount': 0},
        'busStopMatching': {'format': 1, 'policyVersion': POLICY_VERSION, 'policy': deepcopy(POLICY),
            'initialCandidateCount': 2, 'additionalDirectionMatchedStops': 2,
            'neighborWithheldStops': 0, 'originalFarProjectedStops': 0,
            'combinedProjectedStops': 2, 'attachments': deepcopy(records), 'rejected': {},
            'baselineValidation': {'trustedStopIds': [], 'records': {}},
            'selectionGuard': {'initialSelectedCount': 2, 'retainedCount': 2, 'withheldCount': 0,
                'withheld': {}, 'legacyAnchorStates': {
                    'A': {'resolved': True, 'reason': 'existing_node_on_unambiguous_nearest_road',
                          'nearestWayId': '100', 'edgeDistanceMeters': 5., 'nearestEdge': [0, 1],
                          'oldNodeOnNearestWay': True, 'oldNodeOnNearestSegment': True, 'sharedEndpointAlternatives': []},
                    'B': {'resolved': False, 'reason': 'legacy_neighbor_exceeds_existing_snap_limit',
                          'nearestWayId': '100', 'edgeDistanceMeters': 5., 'nearestEdge': [0, 1],
                          'oldNodeOnNearestWay': True, 'oldNodeOnNearestSegment': True}}},
            'changedPairs': [{'from': 'A', 'to': 'B', 'officialOccurrences': deepcopy(occurrences),
                'status': 'accepted', 'reason': None, 'searchLimitSeconds': 7200,
                'rawFixedSeconds': seconds*.5, 'rawFixedMeters': 500.,
                'secondsWeight': seconds*.5, 'meters': 500., 'geometryLimitMeters': 4000., **lock}]}}
    official = {'routes': [{'id': 'R', 'mode': 'bus', 'stops': [
        {'id': 'A', 'sequence': 1}, {'id': 'B', 'sequence': 2}]}]}
    osm = {'ways': {'100': {'id': 100, 'nodes': [10, 20], 'geometry': [ll(0), ll(1000)],
                           'tags': {'highway': 'primary', 'oneway': 'yes'}}}}
    return network, quality, official, osm


def sync(network, quality):
    quality['busStopMatching']['attachments'] = {
        s['id']: deepcopy(s['driveProjection']) for s in network['stops'] if s.get('driveProjection')}


def test_valid_fixture_separates_deterministic_package_and_optional_raw_source():
    n, q, o, raw = fixture()
    packaged = validate_bus_stop_matching(n, q, o)
    full = validate_bus_stop_matching(n, q, o, raw)
    assert packaged['packagedChecks'] == full['packagedChecks']
    assert not packaged['rawSourceChecks']['checked']
    assert 'not independently checked' in packaged['rawSourceChecks']['omission']
    assert full['rawSourceChecks']['checked']
    assert full['packagedChecks']['acceptedLockedSegments'] == 1
    assert validate_bus_projections(n, q, raw)['projectedStopCount'] == 2


@pytest.mark.parametrize('kind', ['missing-official', 'missing-report', 'missing-attachment',
                                 'extra-neighbor', 'extra-rejected', 'count-boolean', 'policy'])
def test_evidence_identity_and_policy_tampering(kind):
    n, q, o, raw = fixture()
    m = q['busStopMatching']
    if kind == 'missing-official': o = None
    elif kind == 'missing-report': q.pop('busStopMatching')
    elif kind == 'missing-attachment': m['attachments'].pop('A')
    elif kind == 'extra-neighbor': m['selectionGuard']['legacyAnchorStates']['ghost'] = {'resolved': True, 'reason': 'fake'}
    elif kind == 'extra-rejected': m['rejected']['ghost'] = 'fake'
    elif kind == 'count-boolean': m['additionalDirectionMatchedStops'] = True
    else: m['policy']['maximumEdgeDistanceMeters'] = 20
    with pytest.raises(ValueError): validate_bus_stop_matching(n, q, o, raw)


@pytest.mark.parametrize('kind', ['reverse-pair', 'fake-route', 'false-sequence', 'duplicate', 'too-long', 'missing'])
def test_positive_witness_requires_exact_direct_official_occurrences(kind):
    n, q, o, raw = fixture()
    evidence = n['stops'][0]['driveProjection']['matchEvidence']
    w = evidence['witnesses'][0]
    if kind == 'reverse-pair': w['from'], w['to'] = w['to'], w['from']
    elif kind == 'fake-route': w['officialOccurrences'][0]['routeId'] = 'invented'
    elif kind == 'false-sequence': w['officialOccurrences'][0]['toSequence'] = 3
    elif kind == 'duplicate': evidence['witnesses'].append(deepcopy(w))
    elif kind == 'too-long': w['alongMeters'] = 1001
    else: evidence['witnesses'] = []
    sync(n, q)
    with pytest.raises(ValueError): validate_bus_stop_matching(n, q, o, raw)


@pytest.mark.parametrize('kind', ['missing-pair', 'duplicate-pair', 'source', 'destination', 'retry',
                                 'wrong-geometry', 'hidden-segment', 'failed-but-published'])
def test_changed_pairs_cannot_silently_retry_or_omit_evidence(kind):
    n, q, o, raw = fixture()
    m = q['busStopMatching']; row = m['changedPairs'][0]; seg = n['segments']['drive:A:B']
    if kind == 'missing-pair': m['changedPairs'] = []
    elif kind == 'duplicate-pair': m['changedPairs'].append(deepcopy(row))
    elif kind == 'source': row['sourceNode'] = seg['sourceNode'] = 0
    elif kind == 'destination': row['destinationNode'] = seg['destinationNode'] = 1
    elif kind == 'retry': row['retryAttempted'] = seg['retryAttempted'] = True
    elif kind == 'wrong-geometry': seg['coordinates'][-1] = np.round(ll(800), 6).tolist()
    elif kind == 'hidden-segment': n['segments'].clear()
    else: row.update(status='unresolved', reason='geometry', meters=None, secondsWeight=None)
    with pytest.raises(ValueError): validate_bus_stop_matching(n, q, o, raw)


@pytest.mark.parametrize('sid', ['injected', 'A', '50253'])
def test_arbitrary_baseline_key_cannot_bypass_neighbor_guard(sid):
    n, q, o, raw = fixture()
    b = q['busStopMatching']['baselineValidation']
    b['trustedStopIds'] = [sid]
    b['records'] = {sid: {'record': {}, 'recordSha256': 'invented', 'trustedForNeighborGuard': True}}
    with pytest.raises(ValueError): validate_bus_stop_matching(n, q, o, raw)


@pytest.mark.parametrize('kind', ['grade', 'parallel', 'reverse-source', 'source-way', 'source-nodes', 'distance', 'neighbor-trust'])
def test_raw_source_reconstruction_rejects_metadata_that_alone_looks_consistent(kind):
    n, q, o, raw = fixture()
    if kind == 'grade': raw['ways']['100']['tags']['bridge'] = 'yes'
    elif kind == 'parallel': raw['ways']['200'] = {'id': 200, 'nodes': [30, 40],
        'geometry': [ll(0, 10), ll(1000, 10)], 'tags': {'highway': 'primary', 'oneway': 'yes'}}
    elif kind == 'reverse-source': raw['ways']['100']['tags']['oneway'] = '-1'
    elif kind == 'neighbor-trust': q['busStopMatching']['selectionGuard']['legacyAnchorStates']['B']['resolved'] = True
    else:
        evidence = n['stops'][0]['driveProjection']['matchEvidence']
        if kind == 'source-way': evidence['wayId'] = 'fake'
        elif kind == 'source-nodes': evidence['osmNodeIds'] = [11, 22]
        else: evidence['sameWayAlternativeMeters'] = 999
        sync(n, q)
    with pytest.raises(ValueError): validate_bus_stop_matching(n, q, o, raw)


def road(code, xy, nodes, direction=0):
    return {'id': code, 'xy': np.asarray(xy, float), 'nodes': nodes, 'osmNodeIds': nodes,
            'direction': direction, 'tags': {'highway': 'secondary'}}


def source(roads):
    coordinates = {}
    for r in roads:
        coordinates.update(zip(r['nodes'], r['xy']))
    return _SourceRoads({'roads': roads, 'coordinates': np.asarray([coordinates[i] for i in range(len(coordinates))])})


def test_independent_legacy_check_rejects_two_way_parallel_and_hairpin():
    parallel = source([road('a', [[0, 0], [1000, 0]], [0, 1]),
                       road('b', [[0, 10], [1000, 10]], [2, 3])])
    assert not parallel.legacy(np.array([100., 5.]), 0)
    hairpin = source([road('h', [[0, 0], [1000, 0], [0, 10]], [0, 1, 2])])
    assert not hairpin.legacy(np.array([100., 2.]), 0)


def test_independent_legacy_check_requires_nearest_segment_not_distant_same_way_branch():
    folded = source([road('h', [[0, 0], [1000, 0], [1000, 40], [100, 40], [0, 40]], [0, 1, 2, 3, 4], 1)])
    assert not folded.legacy(np.array([100., 5.]), 3)


@pytest.mark.parametrize('shared', [True, False])
def test_only_actual_shared_endpoint_identity_is_a_junction_exception(shared):
    roads = [road('main', [[0, 0], [1000, 0]], [0, 1]),
             road('branch', [[0, 0], [0, 100]], [0 if shared else 2, 2 if shared else 3])]
    assert source(roads).legacy(np.array([5., -2.]), 0) == shared


def test_original_edge_may_follow_descending_raw_way_node_order():
    n, q, o, raw = fixture()
    for stop in n['stops']:
        r = stop['driveProjection']
        r['edge'].reverse()
        r['edgeCoordinates'].reverse()
        r['fraction'] = 1-r['fraction']
        r['forwardSeconds'], r['reverseSeconds'] = r['reverseSeconds'], r['forwardSeconds']
    sync(n, q)
    assert validate_bus_projections(n, q, raw)['sourceEdgesChecked']


def test_bridged_missing_stop_pair_is_routing_evidence_but_cannot_be_positive_witness():
    n, q, o, raw = fixture()
    o['routes'][0]['stops'].insert(1, {'id': 'unknown', 'sequence': 2})
    # The only A->B source occurrence skips an unlocated official stop.
    with pytest.raises(ValueError, match='direct official neighbor'):
        validate_bus_stop_matching(n, q, o)
    o['routes'].append({'id': 'W', 'mode': 'bus', 'stops': [{'id': 'A'}, {'id': 'B'}]})
    for stop in n['stops']:
        stop['driveProjection']['matchEvidence']['witnesses'][0]['officialOccurrences'] = [
            {'routeId': 'W', 'fromSequence': 0, 'toSequence': 1}]
    sync(n, q)
    row = q['busStopMatching']['changedPairs'][0]
    row['officialOccurrences'] = [{'routeId': 'R', 'fromSequence': 0, 'toSequence': 2},
                                  {'routeId': 'W', 'fromSequence': 0, 'toSequence': 1}]
    assert validate_bus_stop_matching(n, q, o, raw)['status'] == 'passed'
    row['officialOccurrences'].pop(0)
    with pytest.raises(ValueError, match='source occurrences differ'):
        validate_bus_stop_matching(n, q, o, raw)


@pytest.mark.parametrize('reason,seconds,meters', [
    ('fixed_anchor_exceeds_existing_snap_limit', None, None),
    ('unresolved_within_7200_second_search', 60, 500),
    ('fixed_anchor_exceeds_existing_geometry_gate', 60, 500),
    ('unrecognized', None, None),
])
def test_unresolved_classification_must_agree_with_its_declared_evidence(reason, seconds, meters):
    n, q, o, raw = fixture()
    n['segments'].clear()
    q['busStopMatching']['changedPairs'][0].update(status='unresolved', reason=reason,
        rawFixedSeconds=seconds, rawFixedMeters=meters, secondsWeight=None, meters=None)
    with pytest.raises(ValueError): validate_bus_stop_matching(n, q, o, raw)


def test_report_cannot_hide_an_extra_segment_touching_a_matched_stop():
    n, q, o, raw = fixture()
    n['segments']['drive:B:A'] = deepcopy(n['segments']['drive:A:B'])
    with pytest.raises(ValueError, match='unreported direction-matched segment'):
        validate_bus_stop_matching(n, q, o, raw)


def test_accepted_status_cannot_survive_global_anchor_coordinate_tampering():
    n, q, o, raw = fixture()
    n['stops'][1]['driveNodeCoordinates'] = ll(700, .5)
    with pytest.raises(ValueError, match='anchor coordinate/snap differs|global projected anchor differs'):
        validate_bus_stop_matching(n, q, o, raw)


def test_raw_neighbor_metadata_cannot_lie_while_retaining_the_same_boolean_decision():
    n, q, o, raw = fixture()
    q['busStopMatching']['selectionGuard']['legacyAnchorStates']['A']['nearestWayId'] = 'invented'
    with pytest.raises(ValueError, match='raw neighbor source evidence differs'):
        validate_bus_stop_matching(n, q, o, raw)
