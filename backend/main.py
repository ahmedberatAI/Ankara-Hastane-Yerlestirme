import json
from functools import lru_cache
from pathlib import Path
from typing import Literal
import numpy as np
from scipy.sparse import load_npz
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree
from pyproj import Transformer
from threading import Lock
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from backend.optimizer import metrics
from backend.capacity import solve_capacity
from backend.feasibility import geographic_bound
from backend.timetable import DEFAULT_PROFILE, PROFILES, journey, load_network

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/processed'
app = FastAPI(title='Ankara Sağlık Erişimi', version='0.5.0')
solve_lock = Lock()

@lru_cache(maxsize=1)
def health_planning():
    return json.loads((DATA / 'health-planning.json').read_text(encoding='utf-8'))

@lru_cache(maxsize=1)
def site_conflicts():
    candidates = dataset()['candidates']
    project = Transformer.from_crs(4326, 32636, always_xy=True)
    xy = np.array([project.transform(c['lon'], c['lat']) for c in candidates])
    radii = np.array([c['footprintRadiusMeters'] for c in candidates])
    return [(a,b) for a,b in sorted(cKDTree(xy).query_pairs(2 * radii.max()))
            if np.linalg.norm(xy[a] - xy[b]) < radii[a] + radii[b]]

@lru_cache(maxsize=1)
def dataset():
    return json.loads((DATA / 'dataset.json').read_text(encoding='utf-8'))

@lru_cache(maxsize=5)
def matrix(mode,profile=DEFAULT_PROFILE):
    path = DATA / (f'transit-{profile}-matrix.npz' if mode=='transit' else 'car-matrix.npz')
    if not path.exists():
        raise HTTPException(409, 'Bu ulaşım modu için ağ matrisi henüz hazırlanmadı.')
    return np.load(path)['minutes']

@lru_cache(maxsize=3)
def graph(name):
    return load_npz(DATA / f'{name}-graph.npz')

@lru_cache(maxsize=1)
def coordinates():
    return np.load(DATA / 'graph-coordinates.npy')

class Scenario(BaseModel):
    model_config = {'extra': 'forbid'}
    mode: Literal['car', 'transit'] = 'car'
    threshold: int = Field(default=30, ge=10, le=120)
    coverageTarget: float = Field(default=95, ge=50, le=100)
    districtFloor: float = Field(default=80, ge=0, le=100)
    trafficFactor: float = Field(default=1, ge=1, le=2.5)
    demandMultiplier: float = Field(default=1, ge=.5, le=2)
    bedOccupancy: float = Field(default=80, ge=50, le=90)
    contactsPerDoctor: int = Field(default=2140, ge=500, le=10000)
    costTolerance: float = Field(default=10, ge=0, le=30)
    hospitalLimit: int | None = Field(default=None, ge=1, le=1000)
    operatingCostMultiplier: float = Field(default=1, ge=.5, le=2)
    transitProfile: Literal['weekday-0800','weekday-1000','saturday-1000','sunday-1000'] = DEFAULT_PROFILE

def travel_times(s):
    times = matrix(s.mode,s.transitProfile).astype(float)
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
    return {**data, 'healthPlanning': health_planning(),
            'sources': json.loads((ROOT / 'docs/sources.json').read_text(encoding='utf-8'))}

@app.get('/api/benchmark-91')
def benchmark_91():
    path = DATA / 'benchmark-91.json'
    if not path.exists(): raise HTTPException(404, '91 tesis deneyi henüz kaydedilmedi.')
    return FileResponse(path, media_type='application/json')

@app.get('/api/robustness')
def robustness_report():
    path = DATA / 'robustness-results.json'
    if not path.exists(): raise HTTPException(404, 'Sabit planın zaman profili deneyi henüz kaydedilmedi.')
    return FileResponse(path, media_type='application/json')

@lru_cache(maxsize=24)
def count_bound(mode,threshold,coverage,district_floor,traffic,profile=DEFAULT_PROFILE):
    data=dataset()
    return geographic_bound(travel_times(Scenario(mode=mode,threshold=threshold,trafficFactor=traffic,transitProfile=profile))[:,:len(data['candidates'])],
        np.array([d['population'] for d in data['demands']]),np.array([d['districtId'] for d in data['demands']]),
        data['districts'],data['metadata']['provincePopulation'],threshold,coverage/100,district_floor/100)

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
    certificate = None
    if s.hospitalLimit is not None:
        certificate = count_bound(s.mode,s.threshold,s.coverageTarget,s.districtFloor,s.trafficFactor,s.transitProfile)
    if certificate and (certificate['status']=='infeasible' or
                       certificate['minimumCountLowerBound'] is not None and certificate['minimumCountLowerBound']>s.hospitalLimit+1e-6):
        result={'status':'infeasible','reason':f'Bu veri paketi, örnek aday konumlar ve seçilen saat/hedeflerle {s.hospitalLimit} tesis sınırı, kapasite sınırsız kabul edilse bile erişim hedefini sağlayamıyor. Bu sonuç gerçek Ankara için kesin hastane ihtiyacı değildir.',
                'geographicCertificate':certificate,'infeasibilityScope':'all_candidates_geography'}
    else:
        result = solve_capacity(times[:, :n_candidates], populations, district_ids, data['districts'],
                         data['metadata']['provincePopulation'], health_planning(), s.threshold,
                         s.coverageTarget/100, s.districtFloor/100, s.demandMultiplier,
                         s.bedOccupancy/100, s.contactsPerDoctor, s.costTolerance/100, conflicts=site_conflicts(),
                         plot_radii=[c['footprintRadiusMeters'] for c in data['candidates']],
                         hospital_limit=s.hospitalLimit,operating_cost_multiplier=s.operatingCostMultiplier)
        if certificate: result['geographicCertificate']=certificate
    result['scenario'] = s.model_dump()
    result['metadata'] = data['metadata']
    result['modelLabel'] = ('EGO resmi kalkışlar · '+PROFILES[s.transitProfile]['label']+' · ara durak süreleri tahmini') if s.mode == 'transit' else 'OSM yol ağı · tahmini sürüş süresi'
    if s.mode=='transit':
        result['transitEvidence']={'version':data['metadata']['transitVersion'],
            'packageId':data['metadata'].get('transitPackageId'),'profile':PROFILES[s.transitProfile],
            'quality':data['metadata']['transitDataQuality'],
            'scope':'Sonuç yalnız kullanılabilen sefer/konum verisi ve tahmini ara durak süreleri için geçerlidir. Eksik hizmet, gerçek hayatta hizmet yokluğu değildir.'}
    if 'selectedIndices' in result:
        capacities = {c['candidateIndex']: c for c in result.pop('capacitySites')}
        result['selected'] = [{**data['candidates'][i], **capacities[i]} for i in result['selectedIndices']]
        for assignment, demand in zip(result['assignments'], data['demands']):
            assignment['demandId'] = demand['id']
            assignment['candidateId'] = data['candidates'][assignment['candidateIndex']]['id'] if assignment['candidateIndex'] is not None else None
            for part in assignment['allocations']:
                part['candidateId'] = data['candidates'][part['candidateIndex']]['id']
        existing = times[:, n_candidates:]
        if existing.shape[1]:
            result['existingComparison'] = {'hospitalCount': existing.shape[1], 'inventory': 'OSM; tür ve kapasite eşdeğerliği doğrulanmadı',
                **metrics(existing.min(axis=1), populations, data['metadata']['provincePopulation'], s.threshold)}
    return result

@app.post('/api/solve')
def solve(scenario: Scenario):
    with solve_lock:
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
        network=load_network()[0]
        exact,path=journey(di,ci,request.transitProfile)
        if not path or abs(exact-minutes)>.001:
            raise HTTPException(409,'Tarifeli rota ile kayıtlı matris eşleşmiyor; veri paketini yeniden oluşturun.')
        clock=PROFILES[request.transitProfile]['seconds']
        fmt=lambda s:f'{int(s//3600):02d}:{int(s%3600//60):02d}'
        for part in path:
            if part['kind']=='ride':
                pattern=network['patterns'][part['pattern']]
                a,b=part['boardPosition'],part['alightPosition']
                stop=network['stops'][pattern['stops'][a]]
                boardings.append({'route':pattern['route'],'stop':stop['name'],'mode':pattern['mode'],
                    'departureTime':fmt(part['departureSeconds']),'arrivalTime':fmt(part['arrivalSeconds']),
                    'waitMinutes':(part['departureSeconds']-clock)/60,
                    'timeBasis':'Terminal kalkışı resmi; ara durak zamanı tahmini'})
                for key in pattern['segmentKeys'][a:b]:
                    legs.append({'kind':'ride','label':pattern['route']+' · duraklar arası OSM güzergâhı',
                                 'coordinates':network['segments'][key]['coordinates']})
                clock=part['arrivalSeconds']
            else:
                kind=part['kind']
                n1=demand if kind in ('access','direct') else network['stops'][part['from']]
                n2=candidate if kind in ('egress','direct') else network['stops'][part['to']]
                start=n1.get('walkNode',n1.get('node'));end=n2.get('walkNode',n2.get('node'))
                legs.append({'kind':'walk','label':'Yürüyüş ağı','coordinates':street_path('walk',start,end)})
                for node,k in ((n1,start),(n2,end)):
                    legs.append({'kind':'connector','label':'Temsil / durak giriş bağlantısı',
                        'coordinates':[[node['lon'],node['lat']],coordinates()[k].tolist()]})
                clock+=part['seconds']
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
