"""Independent saved-artifact fixtures; never invoke the projection builder."""
from copy import deepcopy

import numpy as np
from pyproj import Transformer
import pytest

from scripts.audit_bus_projection import validate_bus_projections


TO_LL = Transformer.from_crs(32636, 4326, always_xy=True)


def ll(x, y=0):
    return list(TO_LL.transform(500000 + x, 4400000 + y))


def fixture(two_way=False):
    """A 2 km raw road, two inserted bus vertices and hand-authored paths."""
    ends = [ll(0), ll(2000)]
    seconds = 2000 / (55 / 3.6)
    records = {}
    stops = []
    for code, x, node in [('A', 700, 2), ('B', 1300, 3)]:
        r = {'changed': True, 'node': node, 'edge': [0, 1], 'fraction': x / 2000,
             'edgeCoordinates': ends, 'projectedCoordinates': ll(x),
             'forwardSeconds': seconds, 'reverseSeconds': seconds if two_way else None,
             'originalNodeSnapMeters': np.hypot(min(x, 2000 - x) if two_way else x, 5),
             'snapMeters': 5.}
        records[code] = r
        lon, lat = ll(x, 5)
        stops.append({'id': code, 'lon': lon, 'lat': lat, 'driveNode': node,
                      'driveSnapMeters': 5., 'driveProjection': deepcopy(r)})
    for code, x, node in [('S', 0, 0), ('E', 2000, 1)]:
        lon, lat = ll(x)
        stops.append({'id': code, 'lon': lon, 'lat': lat, 'driveNode': node, 'driveSnapMeters': 0.})
    network = {'stops': stops, 'segments': {
        'drive:S:A': {'coordinates': np.round([ll(0), ll(700)], 6).tolist()},
        'drive:A:B': {'coordinates': np.round([ll(700), ll(1300)], 6).tolist()},
        'drive:B:E': {'coordinates': np.round([ll(1300), ll(2000)], 6).tolist()},
        # Intermediate attachment occurrences must be checked too.
        'drive:S:E': {'coordinates': np.round([ll(0), ll(700), ll(1300), ll(2000)], 6).tolist()},
    }}
    quality = {'busStopProjection': {'policy': {'maximumSnapMeters': 300.},
        'attemptedStopCount': 2, 'projectedStopCount': 2, 'addedVertexCount': 2,
        'attachments': deepcopy(records), 'unresolved': {}}}
    osm = {'ways': {'100': {'id': 100, 'tags': {'highway': 'primary', 'oneway': 'no' if two_way else 'yes'},
                           'nodes': [10, 20], 'geometry': ends}}}
    return network, quality, osm


def sync(network, quality):
    for s in network['stops']:
        if 'driveProjection' in s:
            quality['busStopProjection']['attachments'][s['id']] = deepcopy(s['driveProjection'])


def test_independent_valid_fixture_includes_intermediate_points_and_raw_source():
    network, quality, osm = fixture()
    result = validate_bus_projections(network, quality, osm)
    assert result['sourceEdgesChecked'] and result['originalNearestNodeDistanceChecked']
    assert result['projectedStopCount'] == result['addedVertexCount'] == 2
    assert result['checkedProjectionOccurrences'] == 6
    assert result['checkedAdjacentPieces'] == 8
    assert result['distinctSourceEdgeCount'] == 1
    assert result['geometryToleranceMeters'] == .20


def test_raw_omission_is_explicit_and_does_not_claim_source_validation():
    network, quality, _ = fixture()
    result = validate_bus_projections(network, quality)
    assert not result['sourceEdgesChecked'] and not result['originalNearestNodeDistanceChecked']
    assert not result['rawOsmProvided'] and result['distinctSourceEdgeCount'] is None
    assert 'not independently checked' in result['sourceAuditOmission']


@pytest.mark.parametrize('field,value,match', [
    ('fraction', .5, 'fraction and projected'),
    ('projectedCoordinates', ll(700, 2), 'fraction and projected'),
    ('originalNodeSnapMeters', 300., 'does not exceed 300'),
    ('snapMeters', 7., 'snapMeters differs'),
    ('forwardSeconds', -1., 'must be positive'),
    ('node', 0, 'drive node differs'),
])
def test_bad_projection_record_rejected_even_if_report_repeats_it(field, value, match):
    network, quality, _ = fixture()
    network['stops'][0]['driveProjection'][field] = value
    sync(network, quality)
    with pytest.raises(ValueError, match=match):
        validate_bus_projections(network, quality)


@pytest.mark.parametrize('alter', ['identity', 'record', 'count', 'vertex-count', 'unresolved-overlap', 'missing-report'])
def test_report_and_stop_identity_accounting(alter):
    network, quality, _ = fixture()
    report = quality['busStopProjection']
    if alter == 'identity':
        report['attachments']['invented'] = report['attachments'].pop('A')
    elif alter == 'record':
        report['attachments']['A']['snapMeters'] = 6
    elif alter == 'count':
        report['projectedStopCount'] = 1
    elif alter == 'vertex-count':
        report['addedVertexCount'] = 1
    elif alter == 'unresolved-overlap':
        report['unresolved']['A'] = {'reason': 'ambiguous_distinct_bus_edges'}
    else:
        quality.clear()
    with pytest.raises(ValueError):
        validate_bus_projections(network, quality)


def test_far_stop_and_false_old_nearest_node_distance():
    network, quality, osm = fixture()
    network['stops'][0]['driveProjection']['originalNodeSnapMeters'] += 10
    sync(network, quality)
    with pytest.raises(ValueError, match='nearest outgoing node distance'):
        validate_bus_projections(network, quality, osm)
    network, quality, _ = fixture()
    network['stops'][0]['lon'], network['stops'][0]['lat'] = ll(700, 301)
    network['stops'][0]['driveProjection']['snapMeters'] = 301
    network['stops'][0]['driveSnapMeters'] = 301
    sync(network, quality)
    with pytest.raises(ValueError, match='exceeds 300'):
        validate_bus_projections(network, quality)


@pytest.mark.parametrize('kind', ['outgoing-reverse', 'incoming-reverse', 'parallel-lane', 'middle-lane-jump', 'wrong-endpoint'])
def test_saved_geometry_cannot_reverse_or_jump_carriageways(kind):
    network, quality, osm = fixture()
    if kind == 'outgoing-reverse':
        network['segments']['drive:A:S'] = {'coordinates': np.round([ll(700), ll(0)], 6).tolist()}
    elif kind == 'incoming-reverse':
        network['segments']['drive:E:A'] = {'coordinates': np.round([ll(2000), ll(700)], 6).tolist()}
    elif kind == 'parallel-lane':
        network['segments']['drive:A:B']['coordinates'].insert(1, np.round(ll(1000, 4), 6).tolist())
    elif kind == 'middle-lane-jump':
        network['segments']['drive:S:E']['coordinates'][2] = np.round(ll(1300, 4), 6).tolist()
    else:
        network['segments']['drive:A:B']['coordinates'][0] = np.round(ll(700, 4), 6).tolist()
    with pytest.raises(ValueError, match='different edge or prohibited direction|endpoint differs'):
        validate_bus_projections(network, quality, osm)


def test_legitimate_reverse_is_allowed_when_raw_edge_permits_it():
    network, quality, osm = fixture(two_way=True)
    network['segments']['drive:B:A'] = {'coordinates': np.round([ll(1300), ll(700)], 6).tolist()}
    assert validate_bus_projections(network, quality, osm)['sourceEdgesChecked']


def test_fabricated_reverse_permission_is_rejected_by_raw_osm():
    network, quality, osm = fixture()
    for stop in network['stops'][:2]:
        stop['driveProjection']['reverseSeconds'] = stop['driveProjection']['forwardSeconds']
    sync(network, quality)
    with pytest.raises(ValueError, match='permitted consecutive raw OSM edge'):
        validate_bus_projections(network, quality, osm)


@pytest.mark.parametrize('kind', ['not-consecutive', 'invented-coordinate', 'private-road', 'wrong-node-order', 'fabricated-cost'])
def test_raw_osm_binds_original_endpoints_permissions_and_costs(kind):
    network, quality, osm = fixture()
    way = osm['ways']['100']
    if kind == 'not-consecutive':
        way['nodes'] = [10, 15, 20]
        way['geometry'] = [ll(0), ll(1000), ll(2000)]
    elif kind == 'invented-coordinate':
        way['geometry'][0] = ll(0, 10)
    elif kind == 'private-road':
        way['tags']['bus'] = 'private'
    elif kind == 'wrong-node-order':
        way['nodes'].reverse()
        way['geometry'] = list(reversed(way['geometry']))
    else:
        for stop in network['stops'][:2]:
            stop['driveProjection']['forwardSeconds'] += 1
        sync(network, quality)
    with pytest.raises(ValueError):
        validate_bus_projections(network, quality, osm)


def test_bus_permission_and_oneway_override_are_read_from_raw_source():
    network, quality, osm = fixture()
    osm['ways']['100']['tags'].update({'motor_vehicle': 'no', 'bus': 'yes', 'oneway': 'no', 'oneway:bus': 'yes'})
    assert validate_bus_projections(network, quality, osm)['sourceEdgesChecked']


def test_two_stop_ids_may_share_one_node_on_the_same_original_edge():
    network, quality, osm = fixture()
    second = deepcopy(network['stops'][0])
    second['id'] = 'C'
    network['stops'].append(second)
    quality['busStopProjection']['attachments']['C'] = deepcopy(second['driveProjection'])
    quality['busStopProjection']['projectedStopCount'] += 1
    quality['busStopProjection']['attemptedStopCount'] += 1
    result = validate_bus_projections(network, quality, osm)
    assert result['projectedStopCount'] == 3 and result['addedVertexCount'] == 2


def test_fake_shared_projected_node_cannot_join_different_positions():
    network, quality, _ = fixture()
    network['stops'][1]['driveNode'] = 2
    network['stops'][1]['driveProjection']['node'] = 2
    sync(network, quality)
    with pytest.raises(ValueError, match='different edges or positions'):
        validate_bus_projections(network, quality)


def test_one_edge_cannot_have_different_permissions_for_its_two_inserted_stops():
    network, quality, _ = fixture()
    network['stops'][1]['driveProjection']['reverseSeconds'] = 100
    sync(network, quality)
    with pytest.raises(ValueError, match='conflicting direction costs'):
        validate_bus_projections(network, quality)


def test_rounding_tolerance_is_not_a_license_for_a_half_meter_lane_jump():
    network, quality, _ = fixture()
    network['segments']['drive:A:B']['coordinates'].insert(1, np.round(ll(1000, .5), 6).tolist())
    with pytest.raises(ValueError, match='different edge or prohibited direction'):
        validate_bus_projections(network, quality)


def test_empty_projection_report_does_not_claim_source_checks():
    network = {'stops': [], 'segments': {}}
    quality = {'busStopProjection': {'policy': {'maximumSnapMeters': 300}, 'attachments': {},
        'unresolved': {}, 'attemptedStopCount': 0, 'projectedStopCount': 0, 'addedVertexCount': 0}}
    result = validate_bus_projections(network, quality, {'ways': {}})
    assert result['projectedStopCount'] == 0 and not result['sourceEdgesChecked']
