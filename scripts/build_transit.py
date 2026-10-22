"""OSM-based transit scenario, explicitly NOT an official EGO timetable.

Uses ordered route stops, paths on each relation's actual member ways,
network walking access/transfers, and a separate boarding penalty per route.
All-day service, average waits and vehicle speeds are scenario assumptions.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gzip
import json
import re
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix, load_npz, save_npz
from scipy.sparse.csgraph import dijkstra
from backend.geo import project, speed

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/processed'

def run():
    with gzip.open(ROOT / 'data/raw/ankara-osm.json.gz', 'rt', encoding='utf-8') as f:
        osm = json.load(f)
    data = json.loads((OUT / 'dataset.json').read_text(encoding='utf-8'))
    coords = np.load(OUT / 'graph-coordinates.npy')
    walk = load_npz(OUT / 'walk-graph.npz')
    walk_nodes = np.flatnonzero(np.diff(walk.indptr) > 0)
    xy_nodes = project(coords)
    walk_tree = cKDTree(xy_nodes[walk_nodes])
    routes = []
    stop_registry = {}
    for r in osm['routes']:
        mode, ref = r['tags'].get('route'), r['tags'].get('ref', '')
        if mode not in ('subway', 'light_rail') and not (mode == 'bus' and re.fullmatch(r'\d{2,3}(?:-\d)?', ref)):
            continue
        stops = []
        preferred = 'platform' if mode == 'bus' and any(m['role'].startswith('platform') and m['type'] == 'n' for m in r['members']) else 'stop'
        roles = {}
        for member in r['members']:
            if member['type'] != 'n' or not (member['role'].startswith(preferred) or (preferred == 'stop' and member['role'] == 'bus_stop')):
                continue
            node = osm['nodes'].get(str(member['ref']))
            if not node:
                continue
            key = str(member['ref'])
            if stops and stops[-1] == key:
                continue
            dist, k = walk_tree.query(project([[node['lon'], node['lat']]])[0])
            if dist > 200:
                continue
            stop_registry[key] = {'id': key, 'name': node['tags'].get('name', ref),
                'lon': node['lon'], 'lat': node['lat'], 'streetNode': int(walk_nodes[k]), 'snapSeconds': float(dist)/(4.5/3.6)}
            stops.append(key)
            roles[key] = member['role']
        if len(stops) > 1:
            routes.append({**r, 'stops': stops, 'roles': roles})
    stops = list(stop_registry.values())
    stop_index = {s['id']: i for i, s in enumerate(stops)}
    info = [{**s, 'kind': 'stop'} for s in stops]
    edges, geometries, edge_types = {}, {}, {}
    def add(a, b, seconds, kind, geometry=None):
        if a == b or not np.isfinite(seconds):
            return
        if seconds < edges.get((a, b), np.inf):
            edges[(a, b)] = max(.01, float(seconds))
            edge_types[f'{a}:{b}'] = kind
            if geometry is not None:
                geometries[f'{a}:{b}'] = np.asarray(geometry).round(6).tolist()
    accepted_routes = []
    for r in routes:
        local_ids, local_coords, local_edges = {}, [], {}
        mode, ref = r['tags']['route'], r['tags'].get('ref', '')
        for member in r['members']:
            w = osm['ways'].get(str(member['ref'])) if member['type'] == 'w' else None
            if not w or len(w['geometry']) < 2:
                continue
            if mode == 'bus' and ('highway' not in w['tags'] or w['tags']['highway'] in ('construction', 'proposed')):
                continue
            if mode != 'bus' and w['tags'].get('railway') not in ('rail', 'light_rail', 'subway', 'tram'):
                continue
            ids = []
            for node_id, ll in zip(w['nodes'], w['geometry']):
                if node_id not in local_ids:
                    local_ids[node_id] = len(local_coords)
                    local_coords.append(ll)
                ids.append(local_ids[node_id])
            xy = project(w['geometry'])
            velocity = min(28, speed(w['tags'])) if mode == 'bus' else 40
            for a, b, length in zip(ids[:-1], ids[1:], np.linalg.norm(np.diff(xy, axis=0), axis=1)):
                if a == b:
                    continue
                seconds = max(.01, float(length)/(velocity/3.6))
                # Geometry graph is undirected; stop order below supplies service direction.
                local_edges[(a, b)] = min(local_edges.get((a,b), np.inf), seconds)
                local_edges[(b, a)] = min(local_edges.get((b,a), np.inf), seconds)
        if not local_edges:
            continue
        row, col = np.asarray(list(local_edges)).T
        local_graph = csr_matrix((list(local_edges.values()), (row, col)), shape=(len(local_coords), len(local_coords)))
        local_tree = cKDTree(project(local_coords))
        segment_count = 0
        states = []
        for key in r['stops']:
            s = stop_registry[key]
            dist, k = local_tree.query(project([[s['lon'], s['lat']]])[0])
            if dist > 200:
                states.append(None)
                continue
            state = len(info)
            info.append({**s, 'kind': 'onboard', 'route': ref, 'routeId': str(r['id']), 'mode': mode})
            if 'exit_only' not in r['roles'][key]:
                add(stop_index[key], state, 480 if mode == 'bus' else 240, 'board')
            if 'entry_only' not in r['roles'][key]:
                add(state, stop_index[key], .01, 'alight')
            states.append((state, int(k)))
        for before, after in zip(states[:-1], states[1:]):
            if before is None or after is None:
                continue
            cost, pred = dijkstra(local_graph, indices=before[1], return_predecessors=True)
            if not np.isfinite(cost[after[1]]) or cost[after[1]] > 7200:
                continue
            path = [after[1]]
            while path[-1] != before[1]:
                previous = int(pred[path[-1]])
                if previous < 0:
                    break
                path.append(previous)
            if path[-1] != before[1]:
                continue
            path.reverse()
            add(before[0], after[0], cost[after[1]] + 25, 'ride', np.asarray(local_coords)[path])
            segment_count += 1
        if segment_count:
            accepted_routes.append({'id': str(r['id']), 'ref': ref, 'mode': mode, 'segments': segment_count})
    print(f'Transit: {len(accepted_routes)} directional relations, {len(stops)} stops', flush=True)

    n, m = len(data['demands']), len(data['candidates']) + len(data['hospitals'])
    origin_base = len(info)
    info.extend([{**d, 'kind': 'origin', 'streetNode': d['node']} for d in data['demands']])
    destination_base = len(info)
    destinations = data['candidates'] + data['hospitals']
    info.extend([{**d, 'kind': 'destination', 'streetNode': d['node']} for d in destinations])
    origin_nodes = np.array([d['node'] for d in data['demands']])
    destination_nodes = np.array([c['node'] for c in destinations])
    origin_access = np.array([d['snapMeters']/(4.5/3.6) for d in data['demands']])
    destination_access = np.array([c['accessMeters']/(4.5/3.6) for c in destinations])
    stop_nodes = np.array([s['streetNode'] for s in stops])
    stop_access = np.array([s['snapSeconds'] for s in stops])
    for j, stop in enumerate(stops):
        distances = dijkstra(walk, indices=stop['streetNode'], limit=900, directed=True)
        source_cost = distances[origin_nodes] + origin_access + stop['snapSeconds']
        target_cost = distances[destination_nodes] + destination_access + stop['snapSeconds']
        for i in np.flatnonzero(source_cost <= 900):
            add(origin_base + int(i), j, source_cost[i], 'walk')
        for i in np.flatnonzero(target_cost <= 900):
            add(j, destination_base + int(i), target_cost[i], 'walk')
        transfer_cost = distances[stop_nodes] + stop_access + stop['snapSeconds']
        for k in np.flatnonzero(transfer_cost <= 300):
            if k != j:
                add(j, int(k), transfer_cost[k], 'walk')
        if j % 500 == 0:
            print(f'Walking access: {j}/{len(stops)}', flush=True)
    for j, candidate in enumerate(destinations):
        distances = dijkstra(walk, indices=candidate['node'], limit=900)
        cost = distances[origin_nodes] + origin_access + candidate['accessMeters']/(4.5/3.6)
        for i in np.flatnonzero(cost <= 900):
            add(origin_base+int(i), destination_base+j, cost[i], 'walk')
    row, col = np.asarray(list(edges), dtype=np.int32).T
    graph = csr_matrix((list(edges.values()), (row, col)), shape=(len(info), len(info)))
    save_npz(OUT / 'transit-graph.npz', graph)
    reverse = graph.T.tocsr()
    matrix = np.full((n, m), np.inf, dtype=np.float32)
    for j in range(m):
        matrix[:, j] = dijkstra(reverse, indices=destination_base+j)[origin_base:origin_base+n] / 60
    np.savez_compressed(OUT / 'transit-matrix.npz', minutes=matrix)
    with gzip.open(OUT / 'transit-details.json.gz', 'wt', encoding='utf-8') as f:
        json.dump({'nodes': info, 'originBase': origin_base, 'destinationBase': destination_base,
                   'geometries': geometries, 'edgeTypes': edge_types, 'routes': accepted_routes}, f, ensure_ascii=False, separators=(',', ':'))
    data['metadata'].update({'transitStatus': 'network_scenario', 'transitRoutes': len(accepted_routes), 'transitStops': len(stops),
        'transitAssumptions': {'busWaitMinutes': 8, 'railWaitMinutes': 4, 'busSpeedCapKmh': 28, 'railSpeedKmh': 40,
            'maxAccessWalkMinutes': 15, 'maxTransferWalkMinutes': 5, 'stopDwellSeconds': 25, 'scheduleAvailable': False,
            'maxTransfers': None, 'serviceWindow': 'Tüm hatların çalıştığı varsayımı'},
        'transitModel': 'OSM güzergâhları + ağ üzerinden yürüyüş. Tarife yok; bekleme ve hızlar senaryo varsayımı. Gerçek EGO erişim ölçümü değildir.'})
    (OUT / 'dataset.json').write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8', newline='\n')
    print('Transit scenario matrix written.', flush=True)

if __name__ == '__main__':
    run()
