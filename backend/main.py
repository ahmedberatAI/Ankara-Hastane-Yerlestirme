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
app = FastAPI(title='Ankara Sağlık Erişimi', version='0.9.0')
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

def matrix(mode,profile=DEFAULT_PROFILE,engine='ego'):
    if mode == 'transit' and engine == 'motis':
        from backend.motis import load_matrix
        try:
            return load_matrix(profile)
        except (OSError, ValueError, RuntimeError) as exc:
            raise HTTPException(409, f'MOTIS matrisi kullanılamıyor: {exc}') from exc
    return legacy_matrix(mode, profile)

@lru_cache(maxsize=5)
def legacy_matrix(mode, profile=DEFAULT_PROFILE):
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
    mode: Literal['car', 'transit', 'hybrid'] = 'car'
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
    # Old saved experiments/API clients retain their original EGO model.
    # The current UI explicitly selects MOTIS for new transit/hybrid requests.
    transitEngine: Literal['ego', 'motis'] = 'ego'
    carWeight: float = Field(default=70, ge=51, le=95)
    transitThreshold: int = Field(default=45, ge=10, le=120)

def travel_times(s, mode=None):
    mode = mode or s.mode
    if mode == 'hybrid':
        raise ValueError('Hibrit erişim iki ayrı matrisle değerlendirilmelidir.')
    times = matrix(mode,s.transitProfile,s.transitEngine).astype(float)
    if mode == 'car' and s.trafficFactor != 1:
        data = dataset()
        origins = np.array([x['snapMeters'] / 75 for x in data['demands']])
        targets = np.array([x['accessMeters'] / 75 for x in data['candidates']+data['hospitals']])
        overhead = origins[:, None] + targets + 3
        times = np.maximum(times-overhead, 0) * s.trafficFactor + overhead
    return times

@app.get('/api/health')
def health():
    return {'status': 'ok', 'datasetReady': (DATA / 'dataset.json').exists()}

@app.get('/api/routing-status')
def routing_status():
    from backend.motis import routing_status as motis_status
    status = motis_status()
    if status.get('serviceAvailable'):
        from backend.motis_runtime import runtime_identity
        try:
            status['runtimeIdentity'] = runtime_identity()
        except RuntimeError as exc:
            status['serviceAvailable'] = False
            status['detail'] += ' Canlı rota motor kimliği doğrulanamadı: ' + str(exc)
    return {'motis': status,
            'ego': {'ready': all((DATA / f'transit-{p}-matrix.npz').exists() for p in PROFILES),
                    'detail': 'Özgün EGO kaynak deneyi; resmî terminal kalkışları ve tahmini ara durak süreleri.'}}

@app.get('/api/data')
def get_data():
    data = dataset()
    return {**data, 'healthPlanning': health_planning(),
            'sources': json.loads((ROOT / 'docs/sources.json').read_text(encoding='utf-8'))}

@app.get('/api/planning-policy')
def planning_policy():
    from backend.permanent_evidence import load_policy
    try:
        return load_policy()
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(409, f'Sabit planlama politikası doğrulanamadı: {exc}') from exc

def saved_permanent_plan():
    from backend.permanent_service import read_plan
    try:
        return read_plan()
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        raise HTTPException(409, f'Kalıcı plan yayımlanmaya hazır değil: {exc}') from exc

@app.get('/api/permanent-plan')
def permanent_plan():
    # A map view reads the same independently audited artifact; it never solves.
    return saved_permanent_plan()

class PermanentRouteRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    planId: str = Field(pattern=r'^permanent-[0-9a-f]{64}$')
    view: Literal['car', 'transit']
    demandId: str = Field(min_length=1, max_length=128)
    candidateId: str = Field(min_length=1, max_length=128)

@app.post('/api/permanent-route')
def permanent_route(request: PermanentRouteRequest):
    saved = saved_permanent_plan()
    if saved['planId'] != request.planId:
        raise HTTPException(409, 'Haritadaki plan güncel kayıtla eşleşmiyor; sayfayı yenileyin.')
    profile = 'car' if request.view == 'car' else saved['criticalTransitProfile']
    assignment = next((a for a in saved['profiles'][profile]['assignments']
                       if a['demandId'] == request.demandId), None)
    allocation = next((a for a in assignment['allocations']
                       if a['candidateId'] == request.candidateId and a['population'] > 0), None) if assignment else None
    if allocation is None or not any(c['id'] == request.candidateId for c in saved['selected']):
        raise HTTPException(422, 'Bu ulaşım görünümünde mahalle, seçilen hastaneye atanmış değil.')
    policy = saved['policy']
    fixed = {key: policy[key] for key in Scenario.model_fields if key not in ('mode', 'transitProfile')}
    fixed.update(mode='hybrid', transitProfile=saved['criticalTransitProfile'],
                 demandId=request.demandId, candidateId=request.candidateId,
                 routeMode=request.view, routingPackageId=saved['identity']['transitPackageId'])
    response = route(RouteRequest(**fixed))
    limit = policy['threshold'] if request.view == 'car' else policy['transitThreshold']
    if (not np.isfinite(response['minutes']) or abs(response['minutes'] - allocation['minutes']) > .001
            or response['minutes'] > limit
            or request.view == 'transit' and response.get('evidence', {}).get('packageId') != saved['identity']['transitPackageId']):
        raise HTTPException(409, 'Güzergâh, kalıcı planın süre veya kaynak kaydıyla eşleşmiyor.')
    if saved_permanent_plan()['planId'] != request.planId:
        raise HTTPException(409, 'Güzergâh alınırken kalıcı plan değişti; sayfayı yenileyin.')
    return {**response, 'planId': request.planId, 'profileId': profile}

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

@app.get('/api/shared-capacity')
def shared_capacity_report():
    path = DATA / 'shared-capacity-results.json'
    if not path.exists(): raise HTTPException(404, 'Ortak kapasite deneyi henüz kaydedilmedi.')
    return FileResponse(path, media_type='application/json')

@lru_cache(maxsize=24)
def count_bound(mode,threshold,coverage,district_floor,traffic,profile=DEFAULT_PROFILE,engine='ego'):
    data=dataset()
    return geographic_bound(travel_times(Scenario(mode=mode,threshold=threshold,trafficFactor=traffic,transitProfile=profile,transitEngine=engine))[:,:len(data['candidates'])],
        np.array([d['population'] for d in data['demands']]),np.array([d['districtId'] for d in data['demands']]),
        data['districts'],data['metadata']['provincePopulation'],threshold,coverage/100,district_floor/100)

@app.get('/api/layers/{name}')
def get_layer(name: Literal['districts', 'province', 'roads', 'transit-lines']):
    return FileResponse(DATA / f'{name}.geojson', media_type='application/geo+json')

@app.get('/api/unmatched')
def unmatched():
    return FileResponse(DATA / 'unmatched-neighborhoods.json', media_type='application/json')

@lru_cache(maxsize=24)
def _cached_solve(serialized, motis_package=None):
    s = Scenario.model_validate_json(serialized)
    data = dataset()
    times = travel_times(s, 'car' if s.mode == 'hybrid' else s.mode)
    transit_times = travel_times(s, 'transit') if s.mode == 'hybrid' else None
    n_candidates = len(data['candidates'])
    populations = np.array([d['population'] for d in data['demands']])
    district_ids = np.array([d['districtId'] for d in data['demands']])
    certificate = None
    uses_motis = s.mode in ('transit', 'hybrid') and s.transitEngine == 'motis'
    if s.hospitalLimit is not None and s.mode != 'hybrid' and not uses_motis:
        certificate = count_bound(s.mode,s.threshold,s.coverageTarget,s.districtFloor,s.trafficFactor,s.transitProfile,s.transitEngine)
    if certificate and (certificate['status']=='infeasible' or
                       certificate['minimumCountLowerBound'] is not None and certificate['minimumCountLowerBound']>s.hospitalLimit+1e-6):
        result={'status':'infeasible','reason':f'Bu veri paketi, örnek aday konumlar ve seçilen saat/hedeflerle {s.hospitalLimit} tesis sınırı, kapasite sınırsız kabul edilse bile erişim hedefini sağlayamıyor. Bu sonuç gerçek Ankara için kesin hastane ihtiyacı değildir.',
                'geographicCertificate':certificate,'infeasibilityScope':'all_candidates_geography'}
    elif s.mode == 'hybrid':
        from backend.hybrid import solve_hybrid
        result = solve_hybrid(times[:, :n_candidates], transit_times[:, :n_candidates],
            populations, district_ids, data['districts'], data['metadata']['provincePopulation'],
            health_planning(), s.model_dump(),
            [{**c, 'candidateIndex': i} for i, c in enumerate(data['candidates'])],
            conflicts=site_conflicts(), time_limit=90)
        if result['status'] == 'inconclusive':
            result['solverReason'] = result.get('reason')
            result['reason'] = ('Süre sınırlı ortak konum ve kapasite aramasında doğrulanmış bir plan bulunamadı. '
                                'İl, ilçe ve iki modun süre hedefleri korundu; bu sonuç olanaksızlık kanıtı değildir.')
    else:
        result = solve_capacity(times[:, :n_candidates], populations, district_ids, data['districts'],
                         data['metadata']['provincePopulation'], health_planning(), s.threshold,
                         s.coverageTarget/100, s.districtFloor/100, s.demandMultiplier,
                         s.bedOccupancy/100, s.contactsPerDoctor, s.costTolerance/100, conflicts=site_conflicts(),
                         plot_radii=[c['footprintRadiusMeters'] for c in data['candidates']],
                         hospital_limit=s.hospitalLimit,operating_cost_multiplier=s.operatingCostMultiplier)
        if certificate: result['geographicCertificate']=certificate
    if uses_motis:
        # MOTIS /plan checks a disclosed shortlist, not every possible edge.
        # Failure in that restricted graph must not become a global proof.
        result['routingSearchScope'] = 'queried_motis_plan_edges'
        if 'searchScope' in result:
            result['searchScope'] = {**result['searchScope'],
                'solverEdgeRestriction': result['searchScope'].get('restricted'),
                'upstreamRoutingRestriction': True, 'restricted': True,
                'boundScope': 'queried_motis_plan_edges_and_retained_solver_edges'}
        if result['status'] == 'infeasible':
            result['restrictedModelStatus'] = 'infeasible'
            result['restrictedModelReason'] = result.get('reason')
            result['status'] = 'inconclusive'
            result['infeasibilityScope'] = 'queried_motis_plan_edges_only'
            result['reason'] = ('Doğrulanmış MOTIS aday bağlantılarıyla hedefleri sağlayan plan bulunamadı. '
                                'Hedefler değiştirilmedi. Sorgulanmamış bağlantılar ve veri eksikleri nedeniyle '
                                'bu sonuç tüm adaylar veya gerçek Ankara için olanaksızlık kanıtı değildir.')
    result['scenario'] = s.model_dump()
    result['metadata'] = data['metadata']
    result['modelLabel'] = 'OSM yol ağı · tahmini sürüş süresi'
    if s.mode in ('transit', 'hybrid') and s.transitEngine == 'motis':
        from backend.motis import evidence
        result['transitEvidence'] = evidence(s.transitProfile)
        if result['transitEvidence']['packageId'] != motis_package:
            raise HTTPException(409, 'Hesap sırasında MOTIS veri paketi değişti. Sonucu yayımlamadan aynı paketle yeniden hesaplayın.')
        result['metadata'] = {**data['metadata'], 'activeTransitEngine': 'motis',
                              'activeTransitPackageId': result['transitEvidence'].get('packageId')}
        result['modelLabel'] = ('EGO + Araba · ortak kaynak planı · ' if s.mode == 'hybrid' else '') + 'MOTIS · tarihsel Ankara GTFS'
    elif s.mode in ('transit', 'hybrid'):
        result['modelLabel'] = ('EGO + Araba · ortak kaynak planı · ' if s.mode == 'hybrid' else '') + 'EGO resmi kalkışlar · '+PROFILES[s.transitProfile]['label']+' · ara durak süreleri tahmini'
        result['transitEvidence']={'engine':'ego','version':data['metadata']['transitVersion'],
            'packageId':data['metadata'].get('transitPackageId'),'profile':PROFILES[s.transitProfile],
            'quality':data['metadata']['transitDataQuality'],
            'scope':'Sonuç yalnız kullanılabilen sefer/konum verisi ve tahmini ara durak süreleri için geçerlidir. Eksik hizmet, gerçek hayatta hizmet yokluğu değildir.'}
    if result['status'] == 'feasible' and 'capacitySites' in result and 'assignments' in result:
        capacities = {c['candidateIndex']: c for c in result.pop('capacitySites')}
        result['selected'] = [{**data['candidates'][i], **capacities[i]} for i in result['selectedIndices']]
        def enrich_assignments(assignments):
            for assignment, demand in zip(assignments, data['demands']):
                assignment['demandId'] = demand['id']
                assignment['candidateId'] = data['candidates'][assignment['candidateIndex']]['id'] if assignment['candidateIndex'] is not None else None
                for part in assignment['allocations']:
                    part['candidateId'] = data['candidates'][part['candidateIndex']]['id']
        enrich_assignments(result['assignments'])
        for modal in result.get('modalResults', {}).values():
            enrich_assignments(modal['assignments'])
        existing = times[:, n_candidates:]
        if existing.shape[1] and (s.mode != 'transit' or not uses_motis or result['transitEvidence'].get('existingComparisonAvailable', False)):
            result['existingComparison'] = {'hospitalCount': existing.shape[1], 'inventory': 'OSM; tür ve kapasite eşdeğerliği doğrulanmadı',
                **metrics(existing.min(axis=1), populations, data['metadata']['provincePopulation'], s.threshold)}
        if s.mode == 'hybrid':
            result['modalResults']['car']['existingComparison'] = result.get('existingComparison')
            existing_transit = transit_times[:, n_candidates:]
            if existing_transit.shape[1] and (not uses_motis or result['transitEvidence'].get('existingComparisonAvailable', False)):
                result['modalResults']['transit']['existingComparison'] = {
                    'hospitalCount': existing_transit.shape[1],
                    'inventory': 'OSM; tür ve kapasite eşdeğerliği doğrulanmadı',
                    **metrics(existing_transit.min(axis=1), populations, data['metadata']['provincePopulation'], s.transitThreshold)}
    return result

def cached_solve(serialized):
    s = Scenario.model_validate_json(serialized)
    package = None
    if s.mode in ('transit', 'hybrid') and s.transitEngine == 'motis':
        from backend.motis import evidence
        try:
            package = evidence(s.transitProfile)['packageId']
        except (OSError, ValueError, RuntimeError, KeyError) as exc:
            raise HTTPException(409, f'MOTIS veri kimliği doğrulanamadı: {exc}') from exc
    return _cached_solve(serialized, package)

@app.post('/api/solve')
def solve(scenario: Scenario):
    with solve_lock:
        return cached_solve(scenario.model_dump_json())

class RouteRequest(Scenario):
    demandId: str
    candidateId: str
    routeMode: Literal['car', 'transit'] | None = None
    routingPackageId: str | None = Field(default=None, min_length=1, max_length=128)

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
    route_mode = request.routeMode if request.mode == 'hybrid' else request.mode
    if route_mode is None:
        raise HTTPException(422, 'Hibrit rotada gösterilecek ulaşım türünü seçin.')
    route_package = None
    runtime_before = None
    if route_mode == 'transit' and request.transitEngine == 'motis':
        from backend.motis import evidence
        from backend.motis_runtime import runtime_identity
        try:
            route_package = evidence(request.transitProfile)['packageId']
            runtime_before = runtime_identity()
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            raise HTTPException(503, f'Yerel MOTIS kaynak kimliği doğrulanamadı: {exc}') from exc
        if request.routingPackageId is not None and request.routingPackageId != route_package:
            raise HTTPException(409, 'Seçilen yerleşim eski MOTIS veri paketine ait. Güncel paketle yeniden hesaplayın.')
    minutes = travel_times(request, route_mode)[di, ci]
    if not np.isfinite(minutes):
        raise HTTPException(404, 'Bu veri ve arama ayarlarıyla hesaplanmış güzergâh yok; bu gerçek hizmet yokluğu anlamına gelmez.')
    legs = []
    boardings = []
    if route_mode == 'transit' and request.transitEngine == 'motis':
        from backend.motis import plan
        origin_entry = coordinates()[demand['node']]
        target_entry = coordinates()[candidate['node']]
        try:
            planned = plan((float(origin_entry[1]), float(origin_entry[0])),
                (candidate.get('entryLat', float(target_entry[1])), candidate.get('entryLon', float(target_entry[0]))),
                request.transitProfile, origin_access_meters=demand['snapMeters'],
                destination_access_meters=candidate['accessMeters'])
        except (OSError, ValueError, RuntimeError) as exc:
            raise HTTPException(503, f'Yerel MOTIS rotası alınamadı: {exc}') from exc
        try:
            package_after = evidence(request.transitProfile)['packageId']
            runtime_after = runtime_identity()
        except (OSError, ValueError, RuntimeError, KeyError) as exc:
            raise HTTPException(503, f'MOTIS rota kimliği yeniden doğrulanamadı: {exc}') from exc
        if (package_after != route_package or planned.get('evidence', {}).get('packageId') != route_package
                or runtime_after != runtime_before):
            raise HTTPException(409, 'Rota sırasında MOTIS veri paketi veya çalışan motor değişti. Aynı paketle yeniden hesaplayın.')
        if abs(planned['minutes'] - minutes) > .001:
            raise HTTPException(409, 'MOTIS rotası kayıtlı matrisle eşleşmiyor. Kaynak ve arama ayarlarını doğrulayarak matrisi yeniden oluşturun.')
        planned['legs'] = [
            {'kind': 'connector', 'label': 'Varsayımsal mahalle temsil noktası bağlantısı',
             'coordinates': [[demand['lon'], demand['lat']], origin_entry.tolist()]},
            *planned['legs'],
            {'kind': 'connector', 'label': 'Varsayımsal hastane giriş bağlantısı',
             'coordinates': [[candidate.get('entryLon', float(target_entry[0])), candidate.get('entryLat', float(target_entry[1]))], [candidate['lon'], candidate['lat']]]}]
        return {**planned, 'runtimeIdentity': runtime_after, 'minutes': float(minutes), 'demand': demand['name'], 'candidate': candidate['name'],
                'scenario': request.model_dump(), 'routeMode': route_mode,
                'note': 'MOTIS tarihsel GTFS ve OSM rotası. Kesikli giriş bağlantıları varsayımdır; başlangıç bağlantısı, ilk bekleme ve son bağlantı süreye dahildir.'}
    if route_mode == 'car':
        path = street_path('drive', demand['node'], candidate['node'])
        legs.append({'kind': 'drive', 'label': 'Yol ağı üzerinden sürüş', 'coordinates': path})
        legs.append({'kind': 'connector', 'label': 'Temsil noktası / varsayılan giriş bağlantısı',
                     'coordinates': [[demand['lon'], demand['lat']], coordinates()[demand['node']].tolist()]})
        legs.append({'kind': 'connector', 'label': 'Varsayılan hastane giriş bağlantısı',
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
                evidence=pattern.get('serviceEvidence')
                timing_warning=None
                if evidence:
                    timing_warning=('Bu yön için 2025 tarihli planın süre bütçesi kullanılır; güncel varış saati doğrulanmadı.'
                        if 'dated_planned_terminal_interval_with_unverified_current_validity' in evidence['timingConfidence']
                        else '527-1 ekli tablosunun geçerlilik tarihi doğrulanmadı; yayımlı süre fiziksel alt sınıra göre artırılabilir, ara varışlar tahminidir.'
                        if pattern['route']=='527-1'
                        else 'Yayımlı tek yön süresi duraklara dağıtılır; ara varışlar ölçülmüş değildir.')
                boardings.append({'route':pattern['route'],'stop':stop['name'],'mode':pattern['mode'],
                    'departureTime':fmt(part['departureSeconds']),'arrivalTime':fmt(part['arrivalSeconds']),
                    'waitMinutes':(part['departureSeconds']-clock)/60,
                    'timeBasis':'Terminal kalkışı resmi; ara durak zamanı tahmini',
                    'timingWarning':timing_warning,'timingSourceUrls':evidence['sourceUrls'] if evidence else []})
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
            'demand': demand['name'], 'candidate': candidate['name'], 'scenario': request.model_dump(), 'routeMode': route_mode,
            'note': 'Kesikli çizgiler varsayılan giriş bağlantılarıdır; arazide doğrulanmış yollar değildir. Kesintisiz çizgiler OSM yol/yürüyüş/ray ağını izler.'}

app.mount('/assets', StaticFiles(directory=ROOT / 'dist/assets', check_dir=False), name='assets')

@app.get('/')
def frontend():
    path = ROOT / 'dist/index.html'
    if path.exists():
        return FileResponse(path)
    return {'message': 'Arayüz için npm run dev veya önce npm run build çalıştırın.'}
