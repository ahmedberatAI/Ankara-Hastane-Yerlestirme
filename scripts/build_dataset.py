"""Build a directed street graph, audited demand points and off-road sites.

Run from the repository root after population.py and extract_osm.py.
The prototype models each matched neighborhood by one representative point.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gzip
import json
import math
from collections import defaultdict
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix, save_npz
from scipy.sparse.csgraph import dijkstra, connected_components
from shapely.geometry import shape, mapping, Point, LineString
from shapely.ops import transform
from shapely.strtree import STRtree
from backend.geo import normalize, project, lonlat, PROJECT, permissions, speed, road_half_width

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/processed'

def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8', newline='\n')

def run():
    with gzip.open(ROOT / 'data/raw/ankara-osm.json.gz', 'rt', encoding='utf-8') as f:
        osm = json.load(f)
    pop = json.loads((OUT / 'population.json').read_text(encoding='utf-8'))
    province = shape(osm['province']['geometry'])
    province_xy = transform(PROJECT.transform, province)
    district_lookup = {normalize(d['name']): d for d in pop['districts']}
    districts = []
    for a in osm['areas']:
        if a['properties'].get('admin_level') == '6' and normalize(a['properties'].get('name', '')) in district_lookup:
            d = district_lookup[normalize(a['properties']['name'])]
            poly = shape(a['geometry'])
            districts.append((d, poly))
    if len(districts) != 25:
        raise RuntimeError(f'Expected 25 district polygons, got {len(districts)}')
    district_geoms = [d[1] for d in districts]
    district_tree = STRtree(district_geoms)
    def district_at(lon, lat):
        p = Point(lon, lat)
        hits = district_tree.query(p, predicate='intersects')
        return districts[int(hits[0])][0]['id'] if len(hits) else None

    locations = defaultdict(list)
    for n in osm['nodes'].values():
        if n['tags'].get('place') in ('suburb', 'quarter', 'neighbourhood', 'village', 'hamlet', 'town', 'city'):
            d = district_at(n['lon'], n['lat'])
            for field in ('name', 'name:tr', 'official_name', 'alt_name'):
                for name in n['tags'].get(field, '').split(';'):
                    if name:
                        locations[(d, normalize(name))].append((n['lon'], n['lat'], 'osm_place', 'node/' + str(n['id'])))
    for a in osm['areas']:
        if a['properties'].get('admin_level') not in ('8', '10'):
            continue
        pt = shape(a['geometry']).representative_point()
        d = district_at(pt.x, pt.y)
        for field in ('name', 'name:tr', 'official_name', 'alt_name'):
            for name in a['properties'].get(field, '').split(';'):
                if name:
                    locations[(d, normalize(name))].append((pt.x, pt.y, 'osm_boundary_point', 'relation/' + str(a['id'])))

    # Shared node IDs preserve junctions and bridge/tunnel separation.
    nodes, coordinates, drive_edges, walk_edges = {}, [], {}, {}
    road_shapes, road_widths, overview_roads = [], [], []
    rail_shapes = []
    def index(ref, xy):
        if ref not in nodes:
            nodes[ref] = len(coordinates)
            coordinates.append(xy)
        return nodes[ref]
    def edge(store, a, b, cost):
        if a != b and cost > 0:
            key = (a, b)
            store[key] = min(store.get(key, float('inf')), cost)
    for w in osm['ways'].values():
        t = w['tags']
        if (len(w['geometry']) > 1 and t.get('railway') in ('rail', 'light_rail', 'subway', 'tram')
                and t.get('tunnel') not in ('yes', 'building_passage')
                and t.get('layer', '0') not in ('-1', '-2', '-3')):
            rail_shapes.append(LineString(project(w['geometry'])))
        if 'highway' not in t or len(w['geometry']) < 2 or t.get('highway') in ('construction', 'proposed'):
            continue
        xy = project(w['geometry'])
        line = LineString(xy)
        if line.length < .1:
            continue
        road_shapes.append(line)
        road_widths.append(road_half_width(t))
        can_drive, can_walk = permissions(t)
        if not can_drive and not can_walk:
            continue
        ids = [index(ref, p) for ref, p in zip(w['nodes'], w['geometry'])]
        one = t.get('oneway', 'yes' if t.get('junction') == 'roundabout' or t.get('highway') == 'motorway' else 'no')
        for pos in range(len(ids) - 1):
            a, b = ids[pos:pos+2]
            length = float(np.linalg.norm(xy[pos+1] - xy[pos]))
            if can_drive:
                seconds = length / (speed(t) / 3.6)
                if one not in ('-1', 'reverse'):
                    edge(drive_edges, a, b, seconds)
                if one not in ('yes', '1', 'true'):
                    edge(drive_edges, b, a, seconds)
            if can_walk:
                seconds = length / (3.0/3.6 if t.get('highway') == 'steps' else 4.5/3.6)
                edge(walk_edges, a, b, seconds)
                edge(walk_edges, b, a, seconds)
        if t.get('highway') in ('motorway', 'trunk', 'primary', 'secondary', 'tertiary'):
            overview_roads.append({'type': 'Feature', 'properties': {'class': t['highway']},
                'geometry': mapping(LineString(w['geometry']).simplify(.00015))})
    coords = np.asarray(coordinates)
    xy_nodes = project(coords)
    def sparse(edges):
        row, col = np.asarray(list(edges), dtype=np.int32).T
        return csr_matrix((list(edges.values()), (row, col)), shape=(len(coords), len(coords)))
    drive, walk = sparse(drive_edges), sparse(walk_edges)
    save_npz(OUT / 'drive-graph.npz', drive)
    save_npz(OUT / 'walk-graph.npz', walk)
    np.save(OUT / 'graph-coordinates.npy', coords)
    _, labels = connected_components(drive, directed=True, connection='weak')
    main_component = np.bincount(labels).argmax()
    valid_nodes = np.where((labels == main_component) & (np.diff(walk.indptr) > 0))[0]
    snap_tree = cKDTree(xy_nodes[valid_nodes])
    roads_tree = STRtree(road_shapes)
    rail_tree = STRtree(rail_shapes)
    road_widths = np.asarray(road_widths)
    max_road_width = float(road_widths.max())
    print(f'Graph: {len(coords):,} nodes, {drive.nnz:,} driving edges', flush=True)

    demands, unmatched = [], []
    for n in pop['neighborhoods']:
        matches = locations.get((n['districtId'], normalize(n['name'])), [])
        if not matches:
            unmatched.append({**n, 'reason': 'OSM adı ve ilçe sınırıyla eşleşmedi'})
            continue
        # Prefer an explicitly mapped place label, then a point inside its boundary.
        chosen = sorted(matches, key=lambda m: 0 if m[2] == 'osm_place' else 1)[0]
        pxy = project([chosen[:2]])[0]
        dist, k = snap_tree.query(pxy)
        if dist > 1500:
            unmatched.append({**n, 'reason': 'Bağlı yol ağına 1.500 metreden uzak'})
            continue
        demands.append({**n, 'lon': chosen[0], 'lat': chosen[1], 'locationMethod': chosen[2],
            'osmRef': chosen[3], 'node': int(valid_nodes[k]), 'snapMeters': round(float(dist), 1)})
    print(f'Matched {len(demands)} / {len(pop["neighborhoods"])} neighborhoods; population {sum(n["population"] for n in demands):,}', flush=True)

    candidates = []
    used_nodes = set()
    footprint_radius = 45
    for n in sorted(demands, key=lambda n: (-n['population'], n['id'])):
        node = n['node']
        if node in used_nodes:
            continue
        origin = xy_nodes[node]
        site = None
        for radius in (80, 100, 125, 150, 180, 220, 270, 330, 400, 500, 650):
            for angle in np.linspace(0, 2*math.pi, 48, endpoint=False):
                p = Point(origin + radius * np.array([math.cos(angle), math.sin(angle)]))
                footprint = p.buffer(footprint_radius)
                if not province_xy.covers(footprint):
                    continue
                nearby = roads_tree.query(p.buffer(footprint_radius + max_road_width))
                if any(p.distance(road_shapes[int(i)]) < footprint_radius + road_widths[int(i)] for i in nearby):
                    continue
                if any(p.distance(rail_shapes[int(i)]) < footprint_radius + 5
                       for i in rail_tree.query(p.buffer(footprint_radius + 5))):
                    continue
                site = p
                break
            if site is not None:
                break
        if site is None:
            continue
        slon, slat = lonlat([[site.x, site.y]])[0]
        used_nodes.add(node)
        candidates.append({'id': 'H-' + n['id'], 'name': n['name'], 'district': n['district'], 'districtId': n['districtId'],
            'lon': float(slon), 'lat': float(slat), 'node': node, 'entryLon': float(coords[node, 0]), 'entryLat': float(coords[node, 1]),
            'accessMeters': round(site.distance(Point(origin)), 1), 'footprintRadiusMeters': footprint_radius, 'costUnits': 1})

    hospitals, seen = [], set()
    for obj in [*osm['nodes'].values(), *osm['ways'].values()]:
        t = obj['tags']
        name = t.get('name:tr', t.get('name', ''))
        if not name or (t.get('amenity') != 'hospital' and t.get('healthcare') != 'hospital'):
            continue
        ll = [obj['lon'], obj['lat']] if 'lon' in obj else obj['geometry'][len(obj['geometry'])//2]
        if not province.covers(Point(ll)):
            continue
        key = normalize(name)
        if key in seen:
            continue
        seen.add(key)
        dist, k = snap_tree.query(project([ll])[0])
        if dist <= 1500:
            hospitals.append({'id': 'OSM-' + str(obj['id']), 'name': name, 'lon': ll[0], 'lat': ll[1],
                'node': int(valid_nodes[k]), 'accessMeters': round(float(dist), 1), 'source': 'OpenStreetMap', 'capacity': None})

    destinations = candidates + hospitals
    matrix = np.full((len(demands), len(destinations)), np.inf, dtype=np.float32)
    origins = np.array([n['node'] for n in demands])
    source_access = np.array([n['snapMeters'] / (4.5/3.6) for n in demands])
    # Reverse search: demand -> hospital, respecting one-way streets.
    reverse = drive.T.tocsr()
    for j, c in enumerate(destinations):
        dist = dijkstra(reverse, directed=True, indices=c['node'])
        matrix[:, j] = (dist[origins] + source_access + c['accessMeters']/(4.5/3.6) + 180) / 60
        if j % 100 == 0:
            print(f'Travel matrix: {j}/{len(destinations)}', flush=True)
    np.savez_compressed(OUT / 'car-matrix.npz', minutes=matrix)
    write('unmatched-neighborhoods.json', unmatched)
    write('roads.geojson', {'type': 'FeatureCollection', 'features': overview_roads})
    write('districts.geojson', {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': d, 'geometry': mapping(p.simplify(.001))} for d, p in districts]})
    write('province.geojson', {'type': 'Feature', 'properties': {'name': 'Ankara'}, 'geometry': mapping(province.simplify(.001))})
    transit_lines = []
    for r in osm['routes']:
        ways = [osm['ways'].get(str(m['ref'])) for m in r['members'] if m['type'] == 'w']
        lines = [w['geometry'] for w in ways if w and len(w['geometry']) > 1]
        if lines:
            transit_lines.append({'type': 'Feature', 'properties': {'ref': r['tags'].get('ref'), 'name': r['tags'].get('name'), 'mode': r['tags'].get('route')},
                'geometry': {'type': 'MultiLineString', 'coordinates': lines}})
    write('transit-lines.geojson', {'type': 'FeatureCollection', 'features': transit_lines})
    matched_pop = sum(n['population'] for n in demands)
    metadata = {**pop['metadata'], 'matchedNeighborhoodCount': len(demands), 'matchedPopulation': matched_pop,
        'unlocatedPopulation': pop['metadata']['provincePopulation'] - matched_pop, 'candidateCount': len(candidates),
        'osmDate': osm['sourceMetadata']['snapshotDate'], 'osmSha256': osm['sourceMetadata']['sha256'],
        'graphNodes': len(coords), 'graphEdges': drive.nnz,
        'existingHospitalCount': len(hospitals), 'transitStatus': 'gtfs_required', 'osmTransitRelationCount': len(transit_lines),
        'driveModel': 'Yönlü OSM yol ağı; yol sınıfına göre varsayılan hız; canlı trafik ve dönüş kısıtları yok.',
        'demandModel': 'Her eşleşen mahalle bir temsil noktasıdır; hane düzeyinde erişim değildir.',
        'siteModel': '45 m yarıçaplı örnek yapı alanı, tahmini yol genişliği ve yüzey ray hattı koridorlarının dışında. Mevcut binalar engel değildir.',
        'candidateSearch': {'footprintRadiusMeters': 45, 'maxEntryDistanceMeters': 650,
                            'angles': 48, 'surfaceRailHalfWidthMeters': 5}}
    write('dataset.json', {'metadata': metadata, 'districts': pop['districts'], 'demands': demands, 'candidates': candidates, 'hospitals': hospitals})
    print(json.dumps(metadata, ensure_ascii=False), flush=True)

if __name__ == '__main__':
    run()
