"""Continue a complete audited joint plan in a new work directory.

Four separate assignments share locations and integer resources. The old
single-profile budget is a comparison, never a new constraint or budget.
Examples: --strategy cost --pool selected --seconds 300 --out work/joint-next
The current production certificate is never overwritten.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import sys
from time import monotonic

import highspy
import numpy as np
import pyproj
from pyproj import Transformer
import scipy
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.joint_model import build_joint_problem, positive
from backend.joint_solver import solve_cost
from backend.joint_heuristic import batch_close
from scripts.audit_joint_plan import SOURCE_FILES, PROFILES, load_json, validate_joint_plan
from scripts.transit_provenance import check_package

CODE_FILES = ('backend/joint_model.py', 'backend/joint_solver.py', 'backend/joint_heuristic.py',
              'scripts/run_joint_plan.py', 'scripts/audit_joint_plan.py', 'scripts/transit_provenance.py')
PLAN_FIELDS = ('selected', 'profiles', 'hospitalCount', 'totalBeds', 'totalDoctors',
               'annualEquivalentCostTRY', 'annualMaterialCostTRY', 'annualFixedResourceCostTRY')


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def code_hashes():
    # A checkout is portable across LF/CRLF; input and seed hashes remain exact.
    return {name: sha((ROOT / name).read_bytes().replace(b'\r\n', b'\n')) for name in CODE_FILES}


LOADED_CODE_HASHES = code_hashes()


def controls(strategy, pool, seconds, trial_seconds, max_trials, batch_size):
    if strategy not in ('close', 'cost') or pool not in ('all', 'selected'):
        raise ValueError('Unknown strategy or candidate pool')
    if positive(seconds, 'overall seconds') > 300 or positive(trial_seconds, 'trial seconds') > 15:
        raise ValueError('Maximum overall/trial limits are 300/15 seconds')
    for value, maximum in ((max_trials, 1000), (batch_size, 16)):
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError('Positive integer trial/batch limits must be at most 1000/16')


def output_directory(root, out):
    if out is None:
        raise ValueError('An explicit new --out work directory is required')
    root = Path(root).resolve(strict=True)
    path = Path(out)
    path = (path if path.is_absolute() else root / path).resolve(strict=False)
    work = (root / 'work').resolve(strict=False)
    # A junction at work/ itself must not redefine the allowed root as e.g.
    # data/processed/. Nested junctions are rejected by the resolved containment.
    if work != root / 'work' or path == work or not path.is_relative_to(work) or path.exists():
        raise ValueError('Output must be a new directory inside this repository work directory')
    return path


def read_sources(root, seed_path):
    package = check_package(root)
    directory = (root / 'data/processed').resolve(strict=True)
    blobs = {}
    for name in SOURCE_FILES:
        path = (directory / name).resolve(strict=True)
        if path.parent != directory or not path.is_file():
            raise ValueError('Input escapes the processed source directory')
        blobs[name] = path.read_bytes()
    parsed = {name: load_json(blob) for name, blob in blobs.items() if name.endswith('.json')}
    data, health, published = [parsed[name] for name in ('dataset.json', 'health-planning.json', 'example-transit-result.json')]
    count = len(data['candidates']); matrices = {}
    for profile in PROFILES:
        with np.load(io.BytesIO(blobs[f'transit-{profile}-matrix.npz']), allow_pickle=False) as archive:
            if set(archive.files) != {'minutes'}:
                raise ValueError('Unexpected matrix members')
            matrix = archive['minutes']
            if matrix.ndim != 2 or matrix.shape[1] < count:
                raise ValueError('Missing candidate columns')
            matrices[profile] = matrix[:, :count]
    hashes = {name: sha(blob) for name, blob in blobs.items()}
    seed_bytes = seed_path.read_bytes(); certificate = load_json(seed_bytes)
    audit = validate_joint_plan(certificate, data, health, matrices, published, hashes, package)
    return package, hashes, sha(seed_bytes), certificate, data, health, matrices, published, audit


def unchanged(root, package, hashes, seed_path, seed_hash, codes):
    if check_package(root) != package:
        raise ValueError('Transit package changed during the run')
    if any(sha((root / 'data/processed' / name).read_bytes()) != value for name, value in hashes.items()):
        raise ValueError('Input changed during the run')
    if sha(seed_path.read_bytes()) != seed_hash:
        raise ValueError('Seed changed during the run')
    if code_hashes() != codes or codes != LOADED_CODE_HASHES:
        raise ValueError('Loaded model/audit code changed during the run')


def formulate(data, health, matrices, scenario, selected_ids=None):
    ids = list(range(len(data['candidates']))) if selected_ids is None else sorted(selected_ids)
    if len(set(ids)) != len(ids) or any(type(j) is not int or not 0 <= j < len(data['candidates']) for j in ids):
        raise ValueError('Invalid candidate pool identities')
    sites = [dict(data['candidates'][j], candidateIndex=j) for j in ids]
    transform = Transformer.from_crs(4326, 32636, always_xy=True)
    xy = np.array([transform.transform(c['lon'], c['lat']) for c in sites])
    radii = np.array([c['footprintRadiusMeters'] for c in sites])
    conflicts = [(ids[a], ids[b]) for a, b in sorted(cKDTree(xy).query_pairs(2 * radii.max()))
                 if np.linalg.norm(xy[a] - xy[b]) < radii[a] + radii[b]]
    return build_joint_problem({p: m[:, ids] for p, m in matrices.items()},
        [d['population'] for d in data['demands']], [d['districtId'] for d in data['demands']],
        data['districts'], data['metadata']['provincePopulation'], sites, health, scenario, conflicts)


def export_certificate(source, result, report_hash, vector_hash, strategy):
    method = ('Validated source retained; no native search started: ' + result['searchSkipped'] if result.get('searchSkipped')
              else 'Reusable bounded joint-plan ' + strategy + ' search; complete independently audited plan')
    return {**{key: source[key] for key in ('format', 'transitPackageId', 'planningVersion', 'scenario', 'sourceSHA256')},
        'generation': {'method': method,
            # Format-1 historical names now identify this immutable run's files.
            'researchReportSHA256': report_hash, 'researchVectorSHA256': vector_hash,
            'searchProvenOptimal': False, 'minimumHospitalCountProven': False, 'travelTimeOptimized': False,
            'annualDemandCountedOnce': True, 'sameIndividualsAcrossProfilesConstrained': False},
        'plan': {key: result[key] for key in PLAN_FIELDS}}


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf8')


def write_new(path, blob):
    with path.open('xb') as stream:
        stream.write(blob)


def run(*, out, seed=None, strategy='close', pool='selected', seconds=300,
        trial_seconds=15, max_trials=1000, batch_size=16, root=ROOT):
    controls(strategy, pool, seconds, trial_seconds, max_trials, batch_size)
    began = monotonic(); root = Path(root).resolve(strict=True)
    folder = output_directory(root, out)
    seed_path = Path(seed) if seed is not None else root / 'data/processed/joint-plan.json'
    if not seed_path.is_absolute(): seed_path = root / seed_path
    seed_path = seed_path.resolve(strict=True)
    if not seed_path.is_file(): raise ValueError('Seed must be a complete saved certificate file')
    codes = code_hashes()
    if codes != LOADED_CODE_HASHES: raise ValueError('Model/audit code changed after import; restart this command')
    package, hashes, seed_hash, source, data, health, matrices, published, source_audit = read_sources(root, seed_path)
    ids = None if pool == 'all' else [s['candidateIndex'] for s in source['plan']['selected']]
    problem = formulate(data, health, matrices, source['scenario'], ids)
    source_vector, source_residuals = problem.read_plan(source['plan'])
    unchanged(root, package, hashes, seed_path, seed_hash, codes)
    # The new output root is reserved after source validation, before native work.
    # A failed run never overwrites either a prior result or the production seed.
    folder.mkdir(parents=True, exist_ok=False)
    remaining = seconds - (monotonic() - began); vectors = {}
    if remaining <= 0:
        result = problem.serialize(source_vector)
        result['searchSkipped'] = 'Preflight/model build exhausted the total search deadline; validated source retained'
    elif strategy == 'close':
        result = batch_close(problem, source['plan'], remaining, trial_seconds, max_trials, batch_size)
    else:
        result = solve_cost(problem, source['plan'], remaining, capture_vectors=vectors)
    search_elapsed = monotonic() - began
    final_vector, residuals = problem.read_plan(result)
    if result['annualEquivalentCostTRY'] > source['plan']['annualEquivalentCostTRY'] + max(.01, source['plan']['annualEquivalentCostTRY'] * 1e-12):
        raise ValueError('Final plan worsened the validated source cost')
    vectors.update(sourceOriginalVector=source_vector, finalOriginalVector=final_vector)
    archive = io.BytesIO(); np.savez_compressed(archive, **vectors); vector_bytes = archive.getvalue()
    native_log = result.get('warmStart', {}).pop('solverLog', None)
    report = {'format': 1, 'builtAt': datetime.now(timezone.utc).isoformat(), 'transitPackageId': package,
        'sourceSHA256': hashes, 'modelCodeSHA256': codes, 'codeHashNormalization': 'CRLF converted to LF; data/seed use exact bytes',
        'seed': {'path': str(seed_path), 'sha256': seed_hash, 'hospitalCount': source['plan']['hospitalCount']},
        'strategy': strategy, 'candidatePool': pool, 'candidateIndices': list(problem.ids),
        'fullCandidateCount': len(data['candidates']), 'dimensions': problem.dimensions,
        'controls': {'overallSeconds': seconds, 'trialSeconds': trial_seconds, 'maxTrials': max_trials, 'batchSize': batch_size},
        'searchElapsedSeconds': search_elapsed, 'cooperativeLimitOverrunSeconds': max(0., search_elapsed - seconds),
        'timeBudgetScope': 'Input validation and formulation count toward the search deadline. Native limits are cooperative; actual overrun is reported. Final independent auditing/hashing/serialization is additional.',
        'sourceResiduals': source_residuals, 'finalResiduals': residuals, 'result': result,
        'originalAnnualBudgetTRY': published['capacity']['budgetLimitTRY'], 'budgetIsConstraint': False,
        'newBudgetProduced': False, 'vectorSHA256': sha(vector_bytes),
        'solverLogSHA256': sha(native_log.encode('utf8')) if native_log is not None else None,
        'versions': {'python': platform.python_version(), 'numpy': np.__version__, 'scipy': scipy.__version__,
                     'highs': highspy.Highs().version(), 'pyproj': pyproj.__version__},
        'scope': 'Feasible common-resource plan conditional on four supplied matrices and health assumptions. Selected-pool bounds concern only these locations; failure is not global infeasibility. No minimum hospital count, 91-site conclusion, clinical adequacy, real travel-time or policy-budget guarantee. No travel stage.',
        'certificateGenerationHashFields': 'Format-1 researchReportSHA256/researchVectorSHA256 identify run-result.json/vectors.npz of this run, not a replay of historical research.'}
    report_bytes = json_bytes(report)
    certificate = export_certificate(source, result, sha(report_bytes), sha(vector_bytes), strategy)
    final_audit = validate_joint_plan(certificate, data, health, matrices, published, hashes, package)
    final_audit.update(seedCertificateSHA256=seed_hash, certificateSHA256=sha(json_bytes(certificate)),
        runReportSHA256=sha(report_bytes), vectorSHA256=sha(vector_bytes), modelCodeSHA256=codes,
        sourceAnnualEquivalentCostTRY=source_audit['annualEquivalentCostTRY'],
        postSearchValidationSeconds=monotonic() - began - search_elapsed)
    unchanged(root, package, hashes, seed_path, seed_hash, codes)
    write_new(folder / 'vectors.npz', vector_bytes)
    if native_log is not None: write_new(folder / 'solver.log', native_log.encode('utf8'))
    write_new(folder / 'run-result.json', report_bytes)
    write_new(folder / 'audit.json', json_bytes(final_audit))
    # Complete certificate is written last, after both model and independent gates.
    write_new(folder / 'joint-plan.json', json_bytes(certificate))
    print('Saved independently validated joint plan:', folder)
    print('Hospitals:', result['hospitalCount'], '; annual cost TRY:', result['annualEquivalentCostTRY'],
          '; within prior model budget:', final_audit['withinOriginalTransitBudget'])
    return report, certificate, final_audit


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, help='New directory under work/; existing paths are rejected')
    parser.add_argument('--seed', help='Complete joint-plan certificate; defaults to the current published plan')
    parser.add_argument('--strategy', choices=('close', 'cost'), default='close')
    parser.add_argument('--pool', choices=('all', 'selected'), default='selected')
    parser.add_argument('--seconds', type=float, default=300)
    parser.add_argument('--trial-seconds', type=float, default=15)
    parser.add_argument('--max-trials', type=int, default=1000)
    parser.add_argument('--batch-size', type=int, default=16)
    run(**vars(parser.parse_args()))
