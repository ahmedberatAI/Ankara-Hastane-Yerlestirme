"""Add audited, larger road-free plots and extend both routing graphs exactly.

Each new plot uses an existing entrance node and a no-shorter connector. Transit
destinations are sinks. Thus every feasible new incoming walking edge is a
subset of the original incoming edges, with its connector delta added. Reapply
the 15 minute walking limit, then recompute shortest paths on the extended graph.
No straight-line replacement of the road/transit network is made.
Run after build_dataset.py AND build_transit.py. Re-running is a no-op.
"""
import gzip
import json
import math
import sys
from pathlib import Path
import numpy as np
from scipy.sparse import load_npz, save_npz, coo_matrix
from scipy.sparse.csgraph import dijkstra
from shapely.geometry import LineString, Point, shape
from shapely.ops import transform
from shapely.strtree import STRtree
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.geo import project, lonlat, PROJECT, road_half_width

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/processed'


def run():
    data = json.loads((OUT/'dataset.json').read_text(encoding='utf-8'))
    if data['metadata'].get('largePlotVersion') == 1:
        print('Large plots already present. Rebuild base data to regenerate.'); return
    with gzip.open(ROOT/'data/raw/ankara-osm.json.gz', 'rt', encoding='utf-8') as f:
        raw = json.load(f)
    roads, widths, rails = [], [], []
    for w in raw['ways'].values():
        t = w['tags']
        if len(w['geometry']) < 2: continue
        if 'highway' in t and t.get('highway') not in ('construction','proposed'):
            roads.append(LineString(project(w['geometry']))); widths.append(road_half_width(t))
        if t.get('railway') in ('rail','light_rail','subway','tram') and t.get('tunnel') not in ('yes','building_passage') and t.get('layer','0') not in ('-1','-2','-3'):
            rails.append(LineString(project(w['geometry'])))
    tree, rail_tree = STRtree(roads), STRtree(rails)
    province = transform(PROJECT.transform, shape(raw['province']['geometry']))
    max_width = max(widths)
    base = data['candidates']
    added = []
    for j, c in enumerate(base):
        origin = project([[c['entryLon'], c['entryLat']]])[0]
        for r in (80,120,210):
            found = None
            for distance in (125,160,200,250,300,400,500,650):
                if distance < max(c['accessMeters'], r + 30): continue
                for angle in np.linspace(0,2*math.pi,48,endpoint=False):
                    p = Point(origin + distance*np.array([math.cos(angle),math.sin(angle)]))
                    if not province.covers(p.buffer(r)): continue
                    if any(p.distance(roads[i]) < r+widths[i]+.01 for i in tree.query(p.buffer(r+max_width))): continue
                    if any(p.distance(rails[i]) < r+5+.01 for i in rail_tree.query(p.buffer(r+5))): continue
                    found = p; break
                if found is not None: break
            if found is None: continue
            lon, lat = lonlat([[found.x, found.y]])[0]
            added.append({**c, 'id': c['id']+f'-R{r}', 'lon':float(lon), 'lat':float(lat),
                          'accessMeters':float(distance), 'footprintRadiusMeters':r, 'baseCandidateIndex':j})
        if j % 200 == 0: print(f'Plots {j}/{len(base)}; larger alternatives {len(added)}', flush=True)
    print(f'Extending matrices with {len(added)} larger plots', flush=True)
    old_count, nadd = len(base), len(added)
    car = np.load(OUT/'car-matrix.npz')['minutes']
    new_car = np.array([car[:,c['baseCandidateIndex']] + (c['accessMeters']-base[c['baseCandidateIndex']]['accessMeters'])/75 for c in added]).T
    np.savez_compressed(OUT/'car-matrix.npz', minutes=np.column_stack([car[:,:old_count],new_car,car[:,old_count:]]).astype(np.float32))
    with gzip.open(OUT/'transit-details.json.gz','rt',encoding='utf-8') as f: details=json.load(f)
    graph = load_npz(OUT/'transit-graph.npz')
    db, ob = details['destinationBase'], details['originBase']
    assert graph[db:,:].nnz == 0, 'Destination reuse requires sink nodes'
    old_edges = graph.tocsc()
    coo = graph.tocoo()
    def moved(node): return int(node)+nadd if node >= db+old_count else int(node)
    rows, cols, vals = coo.row.tolist(), [moved(c) for c in coo.col], coo.data.tolist()
    edge_types = {f'{moved(int(a))}:{moved(int(b))}':v for k,v in details['edgeTypes'].items() for a,b in [k.split(':')]}
    for j,c in enumerate(added):
        bj = c['baseCandidateIndex']; old_end = db+bj; new_end = db+old_count+j
        delta = (c['accessMeters']-base[bj]['accessMeters'])/1.25
        assert delta >= 0
        a,b = old_edges.indptr[old_end:old_end+2]
        for start,value in zip(old_edges.indices[a:b],old_edges.data[a:b]):
            assert details['edgeTypes'][f'{start}:{old_end}'] == 'walk'
            if value + delta <= 900:
                rows.append(int(start)); cols.append(new_end); vals.append(value+delta)
                edge_types[f'{start}:{new_end}']='walk'
    graph = coo_matrix((vals,(rows,cols)),shape=(graph.shape[0]+nadd,)*2).tocsr()
    save_npz(OUT/'transit-graph.npz',graph)
    details['nodes'][db+old_count:db+old_count] = [{**c,'kind':'destination','streetNode':c['node']} for c in added]
    details['edgeTypes']=edge_types
    # Ride geometries cannot end at destination sinks, so their keys are unchanged.
    assert all(int(k.split(':')[1]) < db for k in details['geometries'])
    with gzip.open(OUT/'transit-details.json.gz','wt',encoding='utf-8') as f:
        json.dump(details,f,ensure_ascii=False,separators=(',',':'))
    old_transit=np.load(OUT/'transit-matrix.npz')['minutes']
    new_transit=np.full((len(data['demands']),nadd),np.inf,dtype=np.float32)
    reverse=graph.T.tocsr()
    for j in range(nadd):
        new_transit[:,j]=dijkstra(reverse,indices=db+old_count+j)[ob:ob+len(data['demands'])]/60
    np.savez_compressed(OUT/'transit-matrix.npz',minutes=np.column_stack([old_transit[:,:old_count],new_transit,old_transit[:,old_count:]]))
    data['candidates'].extend(added)
    data['metadata'].update(largePlotVersion=1,baseCandidateCount=old_count,candidateCount=len(data['candidates']),
        siteModel='45/80/120/210 m yarıçaplı yol-dışı yapı izleri. Mevcut binalar engel değildir. Alan kapasitesi 9 kat tasarım varsayımıyla sınırlandırılır.')
    data['metadata']['candidateSearch']['footprintRadiiMeters']=[45,80,120,210]
    (OUT/'dataset.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8',newline='\n')
    print('Expanded candidate counts:', {r:sum(c['footprintRadiusMeters']==r for c in data['candidates']) for r in (45,80,120,210)},flush=True)

if __name__=='__main__': run()
