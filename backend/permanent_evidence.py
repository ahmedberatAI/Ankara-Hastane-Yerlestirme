"""Exact identity of the permanent policy, mathematical model and inputs."""
from pathlib import Path
import hashlib
import json
from backend import motis

ROOT = Path(__file__).resolve().parents[1]
POLICY_FILE = ROOT / 'data/planning-policy.json'
PLAN_FILE = ROOT / 'data/processed/permanent-plan.json'
MODEL_FILES = (
    'backend/permanent.py', 'backend/permanent_service.py', 'backend/permanent_evidence.py',
    'backend/hybrid.py', 'backend/joint_model.py', 'backend/joint_solver.py', 'backend/joint_travel.py',
    'backend/optimizer.py', 'scripts/verify_permanent.py',
)
SOURCE_FILES = {
    'policy': 'data/planning-policy.json', 'dataset': 'data/processed/dataset.json',
    'planning': 'data/processed/health-planning.json', 'carMatrix': 'data/processed/car-matrix.npz',
    'motisManifest': 'data/processed/motis/manifest.json',
}


def code_identities():
    return {name: hashlib.sha256((ROOT / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for name in MODEL_FILES}


def source_identities():
    return {key: motis.file_sha(ROOT / name) for key, name in SOURCE_FILES.items()}


def load_policy():
    from backend.permanent import FIXED_POLICY, PROFILES, WEIGHTS, policy_values
    value = json.loads(POLICY_FILE.read_text(encoding='utf-8'))
    policy_values(value)
    if any(key not in value for key in FIXED_POLICY):
        raise ValueError('Sabit planlama politikasının zorunlu değerleri eksik.')
    if (value.get('id') != 'ankara-permanent-v1' or type(value.get('version')) is not int or value['version'] != 1
            or value.get('classification') != 'literature_informed_planning_policy' or value.get('clinicalStandard') is not False
            or value.get('transitEngine') != 'motis'
            or value.get('profileIds') != list(PROFILES) or value.get('profileWeights') != WEIGHTS):
        raise ValueError('Kalıcı planlama politikasının kimliği veya kapsamı değişti.')
    details = value.get('profileDetails', {})
    if set(details) != set(PROFILES):
        raise ValueError('Beş değerlendirilen profilin kaydı zorunludur.')
    for name in PROFILES:
        expected = None if name == 'car' else motis.PROFILES[name]
        if (type(value['profileWeights'].get(name)) not in (int, float)
                or details[name].get('id') != name or details[name].get('departure') != expected
                or details[name].get('mode') != ('car' if name == 'car' else 'transit')):
            raise ValueError('Planlama politikasının tarihli profil kimliği değişti.')
    flags = value.get('permanence', {})
    if (any(flags.get(k) is not True for k in ('sharedLocations', 'sharedBeds', 'sharedDoctors',
            'annualCostsCountedOnce', 'allProfilesMustMeetTargets'))
            or flags.get('sameIndividualsAcrossProfilesConstrained') is not False
            or flags.get('criticalTransitSelection') != 'maximum_population_weighted_mean_then_profile_id'):
        raise ValueError('Kalıcı yerleşimin ortak kaynak ve değerlendirme kapsamı değişti.')
    return value


def current_identity():
    policy = load_policy()
    manifest = motis.manifest()
    if set(manifest['matrices']) != set(motis.PROFILES):
        raise ValueError('Kalıcı plan için dört MOTIS matrisi birlikte gereklidir.')
    for name in motis.PROFILES:
        motis.load_matrix(name)
    planning = json.loads((ROOT / SOURCE_FILES['planning']).read_text(encoding='utf-8'))
    return {'modelCodeLF_SHA256': code_identities(), 'sourceSHA256': source_identities(),
            'planningVersion': planning['version'], 'policyId': policy['id'],
            'transitPackageId': manifest['packageId']}


def plan_id(result):
    value = {key: data for key, data in result.items() if key != 'planId'}
    return 'permanent-' + hashlib.sha256(motis.canonical(value)).hexdigest()
