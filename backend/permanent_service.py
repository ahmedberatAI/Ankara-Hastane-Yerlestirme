"""Build once, independently audit, then serve one immutable city plan."""
from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path
import numpy as np
from pyproj import Transformer
from scipy.spatial import cKDTree
from backend import motis
from backend.permanent import PROFILES, solve_permanent
from backend.permanent_evidence import ROOT, POLICY_FILE, PLAN_FILE, MODEL_FILES, SOURCE_FILES, current_identity, load_policy, plan_id


def inputs():
    data = json.loads((ROOT / SOURCE_FILES['dataset']).read_text(encoding='utf-8'))
    planning = json.loads((ROOT / SOURCE_FILES['planning']).read_text(encoding='utf-8'))
    with np.load(ROOT / SOURCE_FILES['carMatrix'], allow_pickle=False) as raw:
        car = raw['minutes'].astype(float)
    matrices = {'car': car, **{name: motis.load_matrix(name) for name in motis.PROFILES}}
    shape = (len(data['demands']), len(data['candidates']) + len(data['hospitals']))
    if tuple(matrices) != PROFILES or any(t.shape != shape for t in matrices.values()):
        raise ValueError('Kalıcı plan matris/konum sırası uyuşmuyor.')
    return data, planning, matrices


def conflicts(candidates):
    project = Transformer.from_crs(4326, 32636, always_xy=True)
    xy = np.array([project.transform(c['lon'], c['lat']) for c in candidates])
    radii = np.array([c['footprintRadiusMeters'] for c in candidates])
    return [(a, b) for a, b in sorted(cKDTree(xy).query_pairs(2 * radii.max()))
            if np.linalg.norm(xy[a] - xy[b]) < radii[a] + radii[b]]


def enrich(result, data, policy, identity):
    """Presentation adapter preserves every allocation and common resource."""
    if result.get('status') != 'feasible':
        raise ValueError('Yalnız doğrulanmış beş profilli ortak plan yayımlanabilir.')
    result['selected'] = [{**data['candidates'][c['candidateIndex']], **c} for c in result.pop('capacitySites')]
    for name, profile in result['profiles'].items():
        profile['profile'] = policy['profileDetails'][name]
        if name != 'car':
            profile['transitEvidence'] = {'engine': 'motis', 'packageId': identity['transitPackageId'],
                'profile': name, 'departure': motis.PROFILES[name]}
        for assignment, demand in zip(profile['assignments'], data['demands']):
            assignment['demandId'] = demand['id']
            j = assignment['candidateIndex']
            assignment['candidateId'] = data['candidates'][j]['id'] if j is not None else None
            for part in assignment['allocations']:
                part['candidateId'] = data['candidates'][part['candidateIndex']]['id']
    critical = result['criticalTransitProfile']
    result['modalResults'] = {'car': result['profiles']['car'], 'transit': result['profiles'][critical]}
    for key in ('metrics', 'districts', 'assignments'):
        result[key] = result['profiles']['car'][key]
    result['policy'] = policy
    scenario_fields = ('threshold', 'transitThreshold', 'coverageTarget', 'districtFloor', 'trafficFactor',
        'demandMultiplier', 'bedOccupancy', 'contactsPerDoctor', 'costTolerance', 'hospitalLimit',
        'operatingCostMultiplier', 'transitEngine', 'carWeight')
    result['scenario'] = {key: policy[key] for key in scenario_fields} | {'mode': 'hybrid', 'transitProfile': critical}
    result['metadata'] = {**data['metadata'], 'activeTransitEngine': 'motis', 'activeTransitPackageId': identity['transitPackageId']}
    result['transitEvidence'] = {'engine': 'motis', 'engineVersion': motis.ENGINE_VERSION,
        'datasetScenario': motis.SCENARIO, 'packageId': identity['transitPackageId'],
        'profileDates': dict(motis.PROFILES), 'scope': policy['permanence']['timeCoverageLimit'],
        'unknownMeansNoService': False, 'allCandidateInfeasibilityProofAllowed': False}
    result['artifactType'] = 'permanent-hospital-plan'
    result['modelLabel'] = 'Tek kalıcı yerleşim · araba ve dört MOTIS örneği'
    result['identity'] = identity
    result['planningVersion'] = identity['planningVersion']
    result['builtAt'] = datetime.now(timezone.utc).isoformat()
    result['planId'] = plan_id(result)
    return result


def build_plan(*, time_limit=180):
    identity = current_identity()
    policy = load_policy()
    data, planning, matrices = inputs()
    candidates = [{**c, 'candidateIndex': i} for i, c in enumerate(data['candidates'])]
    m = len(candidates)
    result = solve_permanent({p: t[:, :m] for p, t in matrices.items()},
        np.array([d['population'] for d in data['demands']]),
        np.array([d['districtId'] for d in data['demands']]), data['districts'],
        data['metadata']['provincePopulation'], planning, policy, candidates,
        conflicts=conflicts(candidates), time_limit=time_limit)
    if result['status'] != 'feasible':
        return {**result, 'policy': policy, 'identity': identity}
    if current_identity() != identity:
        raise ValueError('Hesap sırasında kaynak veya model değişti; yeni plan yayımlanmadı.')
    result = enrich(result, data, policy, identity)
    from scripts.verify_permanent import audit
    result['auditSummary'] = audit(result, data, planning, matrices, policy)
    result['planId'] = plan_id(result)
    return result


def _signature():
    paths = [PLAN_FILE, POLICY_FILE, *[ROOT / p for p in MODEL_FILES], *[ROOT / p for p in SOURCE_FILES.values()],
             *[motis.MATRIX_DIR / (name + '-matrix.npz') for name in motis.PROFILES]]
    return tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in paths)


@lru_cache(maxsize=2)
def _read(signature, routing_package_id):
    del signature
    result = json.loads(PLAN_FILE.read_text(encoding='utf-8'))
    if result.get('planId') != plan_id(result) or result.get('identity') != current_identity():
        raise ValueError('Kalıcı planın model, politika veya veri kimliği değişti; yeniden hazırlanmalıdır.')
    if result['identity']['transitPackageId'] != routing_package_id:
        raise ValueError('Kalıcı plan farklı bir MOTIS paketine ait.')
    data, planning, matrices = inputs()
    from scripts.verify_permanent import audit
    audit(result, data, planning, matrices, load_policy())
    return result


def read_plan():
    if not PLAN_FILE.is_file():
        raise ValueError('Kaynakları doğrulanmış kalıcı plan henüz hazırlanmadı.')
    return _read(_signature(), motis.manifest()['packageId'])
