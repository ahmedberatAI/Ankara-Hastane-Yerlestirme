import gzip
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal
import numpy as np
from scipy.sparse import load_npz
from scipy.sparse.csgraph import dijkstra
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from backend.optimizer import solve_cover, metrics

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/processed'
app = FastAPI(title='Ankara Sağlık Erişimi', version='0.1.0')

@lru_cache(maxsize=1)
def dataset():
    return json.loads((DATA / 'dataset.json').read_text(encoding='utf-8'))

@lru_cache(maxsize=2)
def matrix(mode):
    path = DATA / f'{mode}-matrix.npz'
    if not path.exists():
        raise HTTPException(409, 'Bu ulaşım modu için ağ matrisi henüz hazırlanmadı.')
    return np.load(path)['minutes']

@lru_cache(maxsize=3)
def graph(name):
    return load_npz(DATA / f'{name}-graph.npz')

@lru_cache(maxsize=1)
def coordinates():
    return np.load(DATA / 'graph-coordinates.npy')

@lru_cache(maxsize=1)
def transit_details():
    with gzip.open(DATA / 'transit-details.json.gz', 'rt', encoding='utf-8') as f:
        return json.load(f)

class Scenario(BaseModel):
    mode: Literal['car', 'transit'] = 'car'
    threshold: int = Field(default=30, ge=10, le=120)
    coverageTarget: float = Field(default=95, ge=50, le=100)
    districtFloor: float = Field(default=80, ge=0, le=100)
    trafficFactor: float = Field(default=1, ge=1, le=2.5)

def travel_times(s):
    times = matrix(s.mode).astype(float)
    if s.mode == 'car' and s.trafficFactor != 1:
        data = dataset()
        origins = np.array([x['snapMeters'] / 75 for x in data['demands']])
        targets = np.array([x['accessMeters'] / 75 for x in data['candidates']+data['hospitals']])
        overhead = origins[:, None] + targets + 3
        times = np.maximum(times-overhead, 0) * s.trafficFactor + overhead
    return times

@app.get('/api/health')
def health():
    return {'status': 'ok', 'datasetReady': (DATA / 'dataset.json').exists()}

@app.get('/api/data')
def get_data():
    data = dataset()
    return {**data, 'sources': json.loads((ROOT / 'docs/sources.json').read_text(encoding='utf-8'))}

@app.get('/api/layers/{name}')
def get_layer(name: Literal['districts', 'province', 'roads', 'transit-lines']):
    return FileResponse(DATA / f'{name}.geojson', media_type='application/geo+json')

@app.get('/api/unmatched')
def unmatched():
    return FileResponse(DATA / 'unmatched-neighborhoods.json', media_type='application/json')

@lru_cache(maxsize=24)
def cached_solve(serialized):
    s = Scenario.model_validate_json(serialized)
    data = dataset()
    times = travel_times(s)
    n_candidates = len(data['candidates'])
    populations = np.array([d['population'] for d in data['demands']])
    district_ids = np.array([d['districtId'] for d in data['demands']])
    result = solve_cover(times[:, :n_candidates], populations, district_ids, data['districts'],
                         data['metadata']['provincePopulation'], s.threshold, s.coverageTarget/100, s.districtFloor/100)
    result['scenario'] = s.model_dump()
    result['metadata'] = data['metadata']
    result['modelLabel'] = 'Tarifesiz toplu taşıma ağ senaryosu' if s.mode == 'transit' else 'OSM yol ağı · tahmini sürüş süresi'
    if 'selectedIndices' in result:
        result['selected'] = [data['candidates'][i] for i in result['selectedIndices']]
        for assignment, demand in zip(result['assignments'], data['demands']):
            assignment['demandId'] = demand['id']
            assignment['candidateId'] = data['candidates'][assignment['candidateIndex']]['id']
        existing = times[:, n_candidates:]
        if existing.shape[1]:
            result['existingComparison'] = {'hospitalCount': existing.shape[1], 'inventory': 'OSM; tür ve kapasite eşdeğerliği doğrulanmadı',
                **metrics(existing.min(axis=1), populations, data['metadata']['provincePopulation'], s.threshold)}
    return result

@app.post('/api/solve')
def solve(scenario: Scenario):
    return cached_solve(scenario.model_dump_json())

class RouteRequest(Scenario):
    demandId: str
    candidateId: str

def reconstruct(predecessors, start, end):
    path = [int(end)]
    for _ in range(len(predecessors)):
        if path[-1] == start:
            return path[::-1]
        previous = int(predecessors[path[-1]])
        if previous < 0:
            return []
        path.append(previous)
    return []

def street_path(mode, start, end):
    distances, predecessors = dijkstra(graph(mode), indices=int(start), return_predecessors=True)
    if not np.isfinite(distances[end]):
        return []
    path = reconstruct(predecessors, start, end)
    return coordinates()[path].round(6).tolist()

@app.post('/api/route')
def route(request: RouteRequest):
    data = dataset()
    di = next((i for i, d in enumerate(data['demands']) if d['id'] == request.demandId), None)
    ci = next((i for i, c in enumerate(data['candidates']) if c['id'] == request.candidateId), None)
    if di is None or ci is None:
        raise HTTPException(404, 'Mahalle veya aday bulunamadı.')
    demand, candidate = data['demands'][di], data['candidates'][ci]
    minutes = travel_times(request)[di, ci]
    if not np.isfinite(minutes):
        raise HTTPException(404, 'Bu modda erişilebilir güzergâh bulunamadı.')
    legs = []
    boardings = []
    if request.mode == 'car':
        path = street_path('drive', demand['node'], candidate['node'])
        legs.append({'kind': 'drive', 'label': 'Yol ağı üzerinden sürüş', 'coordinates': path})
        legs.append({'kind': 'connector', 'label': 'Temsil noktası / varsayılan giriş bağlantısı',
                     'coordinates': [[demand['lon'], demand['lat']], coordinates()[demand['node']].tolist()]})
        legs.append({'kind': 'connector', 'label': 'Hastane giriş bağlantısı',
                     'coordinates': [coordinates()[candidate['node']].tolist(), [candidate['lon'], candidate['lat']]]})
    else:
        details = transit_details()
        start, end = details['originBase']+di, details['destinationBase']+ci
        distances, predecessors = dijkstra(graph('transit'), indices=start, return_predecessors=True)
        path = reconstruct(predecessors, start, end)
        for a, b in zip(path[:-1], path[1:]):
            kind = details['edgeTypes'].get(f'{a}:{b}')
            n1, n2 = details['nodes'][a], details['nodes'][b]
            if kind == 'board':
                boardings.append({'route': n2.get('route'), 'stop': n1['name'], 'mode': n2.get('mode')})
            if kind == 'ride':
                legs.append({'kind': 'ride', 'label': n1.get('route', 'Toplu taşıma'), 'coordinates': details['geometries'].get(f'{a}:{b}', [])})
            if kind == 'walk':
                geom = street_path('walk', n1['streetNode'], n2['streetNode'])
                legs.append({'kind': 'walk', 'label': 'Yürüyüş ağı', 'coordinates': geom})
                for node in (n1, n2):
                    legs.append({'kind': 'connector', 'label': 'Temsil / durak giriş bağlantısı', 'coordinates':
                                 [[node['lon'], node['lat']], coordinates()[node['streetNode']].tolist()]})
    return {'minutes': float(minutes), 'legs': legs, 'boardings': boardings,
            'demand': demand['name'], 'candidate': candidate['name'], 'scenario': request.model_dump(),
            'note': 'Kesikli çizgiler varsayılan kısa erişim bağlantılarıdır; gerçek yol geometrisi değildir.'}

app.mount('/assets', StaticFiles(directory=ROOT / 'dist/assets', check_dir=False), name='assets')

@app.get('/')
def frontend():
    path = ROOT / 'dist/index.html'
    if path.exists():
        return FileResponse(path)
    return {'message': 'Arayüz için npm run dev veya önce npm run build çalıştırın.'}
