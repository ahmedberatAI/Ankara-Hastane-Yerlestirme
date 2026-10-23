"""Bind transit results to exact model, network, matrix and index identities.

The identifier excludes this package's own build timestamp. Source metadata is
part of the exact artifact bytes, so reprocessing it intentionally changes the
package ID. Code hashes normalize line endings so the same Git checkout verifies
on Windows and Linux. Binary/derived artifacts do not.
Only a completed matrix build should write a new package identity.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ('weekday-0800', 'weekday-1000', 'saturday-1000', 'sunday-1000')
MODEL_FILES = ('backend/timetable.py', 'backend/geo.py', 'backend/bus_projection.py',
               'backend/bus_stop_matching.py',
               'backend/service_evidence.py', 'scripts/build_timetable.py', 'scripts/audit_service_evidence.py')
EVIDENCE_FILES = tuple(f'data/evidence/ego/{name}.html.gz' for name in (
    'ego-5608-accessible-7686', 'ego-615-accessible-7621', 'ego-615-announcement-7621',
    'ego-route-560-8', 'ego-route-615', 'ego-route-615-1',
    'ego-route-527-1', 'ego-527-directions-7333', 'ego-527-accessible-7721'))
ARTIFACT_FILES = (
    'ego-official.json', 'ego-stop-coordinates.json', 'ego-service-evidence.json', 'ego-quality.json', 'ego-network.json.gz',
    'graph-coordinates.npy', 'walk-graph.npz',
    'ego-access.npz', 'ego-egress.npz', 'ego-transfers.npz', 'ego-direct.npz',
    'transit-lines.geojson', 'transit-matrix.npz',
    *(f'transit-{profile}-matrix.npz' for profile in PROFILES),
)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(path, normalize_lines=False):
    if normalize_lines:
        return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def index_identity(data):
    # Row/column order is part of the identity, not merely a set of IDs.
    content = {key: data[key] for key in ('demands', 'candidates', 'hospitals', 'districts')}
    content['provincePopulation'] = data['metadata']['provincePopulation']
    return hashlib.sha256(canonical(content)).hexdigest()


def content_identity(records, index_sha):
    payload = {'format': 1, 'files': records, 'indexSha256': index_sha}
    return 'ego-' + hashlib.sha256(canonical(payload)).hexdigest()


def write_package(root=ROOT):
    root = Path(root); out = root/'data/processed'
    data = json.loads((out/'dataset.json').read_text(encoding='utf-8'))
    records = [{'file': name, 'kind': 'model', 'sha256': sha(root/name, True)} for name in MODEL_FILES]
    records += [{'file': 'data/processed/'+name, 'kind': 'artifact', 'sha256': sha(out/name)} for name in ARTIFACT_FILES]
    records += [{'file': name, 'kind': 'evidence', 'sha256': sha(root/name)} for name in EVIDENCE_FILES]
    index_sha = index_identity(data)
    identity = content_identity(records, index_sha)
    package = {'format': 1, 'transitPackageId': identity,
               'builtAt': datetime.now(timezone.utc).isoformat(),
               'indexSha256': index_sha, 'files': records,
               'scope': 'Identity and reproducibility; not proof of real-world transport accuracy.'}
    (out/'transit-package.json').write_text(json.dumps(package, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')
    data['metadata']['transitPackageId'] = identity
    (out/'dataset.json').write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':'))+'\n', encoding='utf-8', newline='\n')
    print('Transit package:', identity, flush=True)
    return package


def check_package(root=ROOT):
    root = Path(root); out = root/'data/processed'
    package = json.loads((out/'transit-package.json').read_text(encoding='utf-8'))
    data = json.loads((out/'dataset.json').read_text(encoding='utf-8'))
    expected_names = set(MODEL_FILES) | set(EVIDENCE_FILES) | {'data/processed/'+name for name in ARTIFACT_FILES}
    assert {r['file'] for r in package['files']} == expected_names, 'Transit package file set mismatch'
    assert len(package['files']) == len(expected_names), 'Duplicate transit package identity'
    for record in package['files']:
        name = record['file']
        is_model = name in MODEL_FILES
        assert record['kind'] == ('model' if is_model else ('evidence' if name in EVIDENCE_FILES else 'artifact'))
        assert sha(root/name, is_model) == record['sha256'], f'Transit package mismatch: {name}'
    assert index_identity(data) == package['indexSha256'], 'Transit row/column index mismatch'
    identity = content_identity(package['files'], package['indexSha256'])
    assert identity == package['transitPackageId'] == data['metadata']['transitPackageId'], 'Transit package ID mismatch'
    return identity


if __name__ == '__main__':
    print('Verified', check_package())
