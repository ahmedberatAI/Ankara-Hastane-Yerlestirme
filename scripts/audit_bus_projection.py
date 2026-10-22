"""Independent audit of saved bus edge attachments, not their construction.

This module never calls the graph splitter or timetable builder. Full precision
attachment records must agree within 1 cm. Saved path coordinates are rounded
to six longitude/latitude decimals: in Ankara one point can move about 0.071 m,
so 0.20 m allows rounding of two points and projection arithmetic. This is not
permission to join roads or a claim about surveyed boarding locations.

Without raw OSM, geometry and internal evidence are audited, but original node
identity, permissions and nearest-original-node distance remain unverified.
"""
import argparse
import gzip
import json
import math
from pathlib import Path
import re

import numpy as np
from pyproj import Transformer
from scipy.spatial import cKDTree


GEOMETRY_TOLERANCE_METERS = .20
RECORD_TOLERANCE_METERS = .01
MAXIMUM_SNAP_METERS = 300.
PROJECT = Transformer.from_crs(4326, 32636, always_xy=True)


def _require(condition, message):
    if not condition:
        raise ValueError('Bus projection audit: ' + message)


def _number(value, label):
    _require(isinstance(value, (int, float)) and not isinstance(value, bool)
             and math.isfinite(value), label + ' must be finite')
    return float(value)


def _integer(value, label):
    _require(isinstance(value, int) and not isinstance(value, bool) and value >= 0,
             label + ' must be a nonnegative integer')
    return value


def _xy(coordinates, label):
    a = np.asarray(coordinates, dtype=float)
    _require(a.ndim == 2 and a.shape[1] == 2 and np.isfinite(a).all(), label + ' coordinates invalid')
    _require(np.all(np.abs(a[:, 0]) <= 180) and np.all(np.abs(a[:, 1]) <= 90), label + ' is not longitude/latitude')
    if len(a) == 1:
        x, y = PROJECT.transform(float(a[0, 0]), float(a[0, 1]))
        x, y = [x], [y]
    else:
        x, y = PROJECT.transform(a[:, 0], a[:, 1])
    result = np.column_stack((x, y))
    _require(np.isfinite(result).all(), label + ' projection invalid')
    return result


def _osm_road_policy(tags):
    """Independently spell out the documented bus graph's OSM tag policy.

    Numeric seconds are model costs, not observed bus speeds. Access and
    one-way overrides are checked against raw ways rather than saved metadata.
    """
    speeds = {'motorway': 95, 'trunk': 75, 'primary': 55, 'secondary': 45,
              'tertiary': 35, 'unclassified': 30, 'residential': 25,
              'living_street': 15, 'service': 15}
    road = tags.get('highway', '')
    if not road or road in ('proposed', 'construction'):
        return None
    base = road.removesuffix('_link')
    motor = next((tags[k] for k in ('motorcar', 'motor_vehicle', 'vehicle', 'access') if k in tags), None)
    allowed = base in speeds and motor not in ('no', 'private', 'agricultural', 'forestry')
    bus = tags.get('bus', tags.get('psv'))
    if bus in ('yes', 'designated', 'permissive') or road == 'busway':
        allowed = True
    if bus in ('no', 'private'):
        allowed = False
    if not allowed:
        return None
    default = 'yes' if tags.get('junction') == 'roundabout' or road == 'motorway' else 'no'
    one = next((tags[k] for k in ('oneway:bus', 'oneway:psv', 'oneway') if k in tags), default)
    speed = speeds.get(base, 20)
    sign = re.fullmatch(r'\d+(?:\.\d+)?', str(tags.get('maxspeed', '')))
    if sign:
        speed = min(speed, float(sign.group()) * .75)
    if road.endswith('_link'):
        speed = min(speed, 35)
    return one not in ('-1', 'reverse'), one not in ('yes', '1', 'true'), max(5., speed)


def _original_osm(osm, target_edges):
    """Read original indexed endpoints and permitted consecutive raw edges.

    Retain only requested edge costs, plus outgoing vertices for the old snap
    test. No split graph or routing result is reconstructed or trusted.
    """
    _require(isinstance(osm.get('ways'), dict), 'raw OSM ways missing')
    index, coordinates, outgoing, costs = {}, [], set(), {}
    for way in osm['ways'].values():
        policy = _osm_road_policy(way.get('tags', {}))
        refs = way.get('nodes', [])
        if policy is None or len(refs) < 2:
            continue
        geometry = way.get('geometry', [])
        _require(len(refs) == len(geometry), 'raw OSM way node/geometry lengths differ')
        ids = []
        for ref, ll in zip(refs, geometry):
            if ref not in index:
                index[ref] = len(coordinates)
                coordinates.append(ll)
            else:
                _require(np.allclose(coordinates[index[ref]], ll, rtol=0, atol=1e-10),
                         'raw OSM node has conflicting coordinates')
            ids.append(index[ref])
        projected = _xy(geometry, 'raw OSM way')
        forward, reverse, speed = policy
        for a, b, length in zip(ids[:-1], ids[1:], np.linalg.norm(np.diff(projected, axis=0), axis=1)):
            if a == b or length <= 0:
                continue
            for u, v, permitted in ((a, b, forward), (b, a, reverse)):
                if permitted:
                    outgoing.add(u)
                    if tuple(sorted((u, v))) in target_edges:
                        costs[u, v] = min(costs.get((u, v), math.inf), float(length / (speed / 3.6)))
    _require(coordinates and outgoing, 'raw OSM contains no permitted bus edges')
    points = _xy(coordinates, 'raw OSM original nodes')
    return points, costs, cKDTree(points[sorted(outgoing)])


def validate_bus_projections(network, quality, osm=None):
    """Reject inconsistent attachments; return an explicit evidence summary.

    Geometry audit covers saved drive segments, including attachments passed
    through between stops. It checks adjacent pieces at inserted vertices, not
    every unrelated road edge in the network. Missing raw OSM is reported as a
    source audit omission, never as a source validation success.
    """
    stops = network['stops']
    registry = {s['id']: s for s in stops}
    _require(len(registry) == len(stops), 'duplicate stop identity')
    projections = {code: s['driveProjection'] for code, s in registry.items() if s.get('driveProjection')}
    report = quality.get('busStopProjection')
    _require(isinstance(report, dict), 'busStopProjection report missing')
    attachments, unresolved = report['attachments'], report['unresolved']
    _require(isinstance(attachments, dict) and isinstance(unresolved, dict), 'attachment/unresolved maps invalid')
    _require(set(attachments).isdisjoint(unresolved), 'a stop is both attached and unresolved')
    _require(set(attachments) | set(unresolved) <= registry.keys(), 'report names an unknown stop')
    _require(_number(report['policy']['maximumSnapMeters'], 'snap policy') == MAXIMUM_SNAP_METERS,
             'unexpected snap policy')
    _require(_integer(report['attemptedStopCount'], 'attempted count') == len(attachments) + len(unresolved),
             'attempted stop count differs')
    changed = {code: r for code, r in attachments.items() if r.get('changed') is True}
    _require(set(changed) == set(projections), 'report and stop projection identities differ')
    _require(_integer(report['projectedStopCount'], 'projected count') == len(changed), 'projected stop count differs')
    for code, record in attachments.items():
        _require(isinstance(record.get('changed'), bool), code + ': changed flag missing')
        _require(record == projections[code] if code in changed else not registry[code].get('driveProjection'),
                 code + ': report and stop projection records differ')
    edge_coordinates, edge_costs, node_records, records = {}, {}, {}, {}
    for code, r in changed.items():
        label = code + ': '
        stop = registry[code]
        edge = tuple(r['edge'])
        _require(len(edge) == 2 and edge[0] < edge[1], label + 'original edge identity invalid')
        for node in edge:
            _integer(node, label + 'edge node')
        node = _integer(r['node'], label + 'projected node')
        _require(stop['driveNode'] == node, label + 'drive node differs')
        endpoints = _xy(r['edgeCoordinates'], label + 'edge')
        _require(endpoints.shape == (2, 2), label + 'edge needs two endpoints')
        p = _xy([r['projectedCoordinates']], label + 'projected point')[0]
        source = _xy([[stop['lon'], stop['lat']]], label + 'stop')[0]
        vector = endpoints[1] - endpoints[0]
        length2 = float(vector @ vector)
        _require(length2 > 0, label + 'zero length original edge')
        fraction = _number(r['fraction'], label + 'fraction')
        _require(0 <= fraction <= 1, label + 'fraction outside original edge')
        expected = endpoints[0] + fraction * vector
        nearest_fraction = float(np.clip((source - endpoints[0]) @ vector / length2, 0, 1))
        _require(np.linalg.norm(p - expected) <= RECORD_TOLERANCE_METERS,
                 label + 'fraction and projected coordinates differ')
        _require(abs(nearest_fraction - fraction) * math.sqrt(length2) <= RECORD_TOLERANCE_METERS,
                 label + 'point is not the nearest projection on its original edge')
        distance = float(np.linalg.norm(source - p))
        _require(distance <= MAXIMUM_SNAP_METERS + RECORD_TOLERANCE_METERS, label + 'projection exceeds 300 m')
        for field, value in (('snapMeters', r['snapMeters']), ('driveSnapMeters', stop['driveSnapMeters'])):
            _require(abs(_number(value, label + field) - distance) <= RECORD_TOLERANCE_METERS,
                     label + field + ' differs from stop-to-projection distance')
        old = _number(r['originalNodeSnapMeters'], label + 'old node distance')
        _require(old > MAXIMUM_SNAP_METERS, label + 'old node distance does not exceed 300 m')
        costs = tuple(r[name] for name in ('forwardSeconds', 'reverseSeconds'))
        _require(any(v is not None for v in costs), label + 'original edge has no permitted direction')
        for value in costs:
            if value is not None:
                _require(_number(value, label + 'edge seconds') > 0, label + 'edge seconds must be positive')
        if edge in edge_costs:
            _require(edge_costs[edge] == costs, label + 'one original edge has conflicting direction costs')
        edge_costs[edge] = costs
        interior = 1e-12 < fraction < 1 - 1e-12
        _require((node not in edge) if interior else node == edge[0 if fraction <= 1e-12 else 1],
                 label + 'projected node identity conflicts with fraction')
        signature = (edge, tuple(r['projectedCoordinates']), fraction, costs)
        if node in node_records:
            _require(node_records[node] == signature, label + 'one projected node belongs to different edges or positions')
        node_records[node] = signature
        for index, point in zip(edge, endpoints):
            if index in edge_coordinates:
                _require(np.linalg.norm(edge_coordinates[index] - point) <= RECORD_TOLERANCE_METERS,
                         label + 'original node coordinates conflict')
            edge_coordinates[index] = point
        records[code] = {'node': node, 'edge': edge, 'endpoints': endpoints, 'point': p,
                         'fraction': fraction, 'costs': costs, 'interior': interior, 'oldDistance': old}
    interior_nodes = {r['node'] for r in records.values() if r['interior']}
    _require(_integer(report['addedVertexCount'], 'added vertex count') == len(interior_nodes),
             'added vertex count differs from distinct inserted nodes')
    _require(interior_nodes.isdisjoint(edge_coordinates), 'inserted vertex used as an original edge endpoint')

    if osm is not None and records:
        original, permitted, old_tree = _original_osm(osm, {r['edge'] for r in records.values()})
        for code, r in records.items():
            _require(max(r['edge']) < len(original), code + ': invented original node index')
            _require(np.max(np.linalg.norm(original[list(r['edge'])] - r['endpoints'], axis=1)) <= RECORD_TOLERANCE_METERS,
                     code + ': original endpoint coordinates disagree with raw OSM')
            if r['interior']:
                _require(r['node'] >= len(original), code + ': inserted node reuses an original node index')
            a, b = r['edge']
            for pair, value in zip(((a, b), (b, a)), r['costs']):
                actual = permitted.get(pair)
                _require((actual is None) == (value is None), code + ': direction lacks a permitted consecutive raw OSM edge')
                if actual is not None:
                    _require(math.isclose(value, actual, rel_tol=1e-9, abs_tol=1e-6),
                             code + ': original edge cost disagrees with raw OSM/model speed policy')
            stop = registry[code]
            actual = float(old_tree.query(_xy([[stop['lon'], stop['lat']]], code)[0])[0])
            _require(actual > MAXIMUM_SNAP_METERS and abs(actual - r['oldDistance']) <= RECORD_TOLERANCE_METERS,
                     code + ': original nearest outgoing node distance disagrees with raw OSM')

    # A geometry-only pass cannot identify a road by proximity to a crossing.
    # At each inserted point both adjacent pieces must fit ONE original edge.
    unique = {r['node']: r for r in records.values() if r['interior']}
    values = list(unique.values())
    tree = cKDTree([r['point'] for r in values]) if values else None
    checked_segments, checked_vertices, checked_pieces = 0, 0, 0

    def fits(record, points, i):
        a, b = record['endpoints']
        vector = b - a
        length = float(np.linalg.norm(vector))
        fractions = []
        for j in range(max(0, i - 1), min(len(points), i + 2)):
            fraction = float((points[j] - a) @ vector / (length * length))
            nearest = a + np.clip(fraction, 0, 1) * vector
            if np.linalg.norm(points[j] - nearest) > GEOMETRY_TOLERANCE_METERS:
                return False
            fractions.append(fraction)
        for delta in np.diff(fractions):
            # Duplicated six-decimal coordinates cannot establish a direction.
            if abs(delta) * length <= GEOMETRY_TOLERANCE_METERS:
                continue
            if record['costs'][0 if delta > 0 else 1] is None:
                return False
        return True

    for key, segment in network['segments'].items():
        if not key.startswith('drive:'):
            continue
        parts = key.split(':')
        _require(len(parts) == 3 and parts[1] in registry and parts[2] in registry, 'segment stop identity invalid: ' + key)
        points = _xy(segment['coordinates'], key)
        _require(len(points) >= 2, key + ': geometry needs two points')
        checked_segments += 1
        endpoint_requirements = {}
        for i, code in ((0, parts[1]), (len(points) - 1, parts[2])):
            if code in records:
                r = records[code]
                _require(np.linalg.norm(points[i] - r['point']) <= GEOMETRY_TOLERANCE_METERS,
                         key + ': segment endpoint differs from declared projected stop')
                if r['interior']:
                    endpoint_requirements[i] = r
        matches = tree.query_ball_point(points, GEOMETRY_TOLERANCE_METERS) if tree else [[] for _ in points]
        for i, candidates in enumerate(matches):
            if i in endpoint_requirements:
                candidates_records = [endpoint_requirements[i]]
            else:
                candidates_records = [values[j] for j in candidates]
            if not candidates_records:
                continue
            _require(any(fits(r, points, i) for r in candidates_records),
                     key + ': inserted vertex uses a different edge or prohibited direction')
            checked_vertices += 1
            checked_pieces += int(i > 0) + int(i + 1 < len(points))

    return {'status': 'passed', 'projectedStopCount': len(records),
            'addedVertexCount': len(interior_nodes), 'checkedDriveSegments': checked_segments,
            'checkedProjectionOccurrences': checked_vertices, 'checkedAdjacentPieces': checked_pieces,
            'geometryToleranceMeters': GEOMETRY_TOLERANCE_METERS,
            'recordToleranceMeters': RECORD_TOLERANCE_METERS,
            'rawOsmProvided': osm is not None,
            'sourceEdgesChecked': bool(osm is not None and records),
            'originalNearestNodeDistanceChecked': bool(osm is not None and records),
            'distinctSourceEdgeCount': len({r['edge'] for r in records.values()}) if osm is not None else None,
            'scope': 'Saved projection identities and adjacent directed geometry only; '
                     'not surveyed boarding access or validation of unrelated road edges. '
                     'Direction of pieces at or below the 0.20 m rounding tolerance is unresolved.',
            'sourceAuditOmission': None if osm is not None else
                'Raw OSM unavailable: original edge permissions, node identities and old nearest-node distances were not independently checked.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument('--network', type=Path, default=root / 'data/processed/ego-network.json.gz')
    parser.add_argument('--quality', type=Path, default=root / 'data/processed/ego-quality.json')
    parser.add_argument('--osm', type=Path, default=root / 'data/raw/ankara-osm.json.gz')
    args = parser.parse_args()
    with gzip.open(args.network, 'rt', encoding='utf-8') as stream:
        network = json.load(stream)
    osm = None
    if args.osm.exists():
        with gzip.open(args.osm, 'rt', encoding='utf-8') as stream:
            osm = json.load(stream)
    print(json.dumps(validate_bus_projections(network, json.loads(args.quality.read_text(encoding='utf-8')), osm),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
