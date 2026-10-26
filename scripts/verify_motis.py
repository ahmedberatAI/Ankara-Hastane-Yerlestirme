"""Offline verification of the four MOTIS matrices and eight raw journey checks.

Only --capture-live makes local HTTP requests (at most ten per profile). It
writes a separate route-checks.json; the frozen matrix manifest is not changed.
These checks certify recorded arithmetic/identity, not current EGO completeness.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from backend import motis, motis_runtime

FILE_NAME = 'route-checks.json'
TOLERANCE_MINUTES = .001
MAX_ATTEMPTS = 10
_LOADED_CODE = motis.code_sha(Path(__file__))
_LOADED_RUNTIME = motis.code_sha(ROOT / 'backend/motis_runtime.py')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, name, *, minimum=0):
    require(type(value) in (int, float) and math.isfinite(value) and value >= minimum,
            'Invalid finite number: ' + name)
    return float(value)


def integer(value, name, *, minimum=0):
    require(type(value) is int and value >= minimum, 'Invalid integer: ' + name)
    return value


def timestamp(value):
    require(isinstance(value, str), 'Missing timestamp')
    t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(t.tzinfo is not None, 'Timestamp has no timezone')
    return t


def verifier_codes():
    current = {'scripts/verify_motis.py': motis.code_sha(Path(__file__)),
               'backend/motis_runtime.py': motis.code_sha(ROOT / 'backend/motis_runtime.py')}
    require(current == {'scripts/verify_motis.py': _LOADED_CODE,
                        'backend/motis_runtime.py': _LOADED_RUNTIME}, 'Loaded verifier/runtime code changed')
    return current


def validate_matrices(manifest, data, arrays):
    """Pure shape/index/mask/metadata verification, in addition to byte hashes."""
    require(type(manifest.get('format')) is int and manifest['format'] == 1 and manifest.get('engineVersion') == motis.ENGINE_VERSION,
            'Unsupported MOTIS format/version')
    require(manifest.get('scenario') == motis.SCENARIO and manifest.get('policyVersion') == motis.POLICY_VERSION,
            'Unsupported MOTIS scenario/policy')
    require(manifest.get('profiles') == motis.PROFILES and manifest.get('planParameters') == motis.PLAN_PARAMETERS,
            'Profile dates or request parameters differ')
    require(manifest.get('existingComparisonAvailable') is False, 'Existing-hospital comparison is unsupported')
    scope = manifest.get('searchScope', {})
    expected_scope = {'kind': 'restricted_edges', 'allCandidateInfeasibilityProofAllowed': False,
        'bulkIsOnlyShortlistHint': True, 'bulkAndPlanEquivalent': False,
        'finalEndpoint': '/api/v6/plan', 'connectorSpeedMetersPerSecond': 1.25,
        'originConnectorBeforeQuery': True, 'queryTimeCeilingMinutes': True,
        'maximumTotalMinutes': 120., 'currentOfficialEGO': False,
        'unqueriedMeans': 'unknown, not no service',
        'emptyPlanMeans': 'unknown within dated data and search limits'}
    require(all(scope.get(k) == v and (not isinstance(v, bool) or type(scope.get(k)) is bool)
                for k, v in expected_scope.items()), 'Unsupported routing scope/unknown-state claim')
    integer(scope.get('perFootprintClass'), 'shortlist per footprint', minimum=1)
    require(set(manifest.get('matrices', {})) == set(motis.PROFILES) == set(arrays), 'All four matrices are required')
    for name in ('sourceSHA256', 'codeLF_SHA256'):
        require(isinstance(manifest.get(name), dict) and manifest[name]
                and all(isinstance(v, str) and re.fullmatch('[0-9a-f]{64}', v) for v in manifest[name].values()),
                'Invalid source/code SHA syntax')
    expected = {k: [str(x['id']) for x in data[k]] for k in ('demands', 'candidates', 'hospitals')}
    require(all(len(v) == len(set(v)) for v in expected.values()), 'Duplicate dataset identities')
    require(manifest.get('indices') == expected and manifest.get('indexSHA256') == hashlib.sha256(motis.canonical(expected)).hexdigest(),
            'Dataset ordering/identity mismatch')
    shape = (len(data['demands']), len(data['candidates']) + len(data['hospitals']))
    summaries = {}
    for profile in motis.PROFILES:
        record = manifest['matrices'][profile]
        matrix, queried = arrays[profile]
        require(record.get('file') == profile + '-matrix.npz' and record.get('departure') == motis.PROFILES[profile],
                'Matrix filename/departure mismatch')
        require(matrix.dtype == np.float32 and queried.dtype == bool and matrix.shape == queried.shape == shape
                and record.get('shape') == list(shape), 'Matrix type/shape/mask mismatch')
        require(not np.isnan(matrix).any() and not np.isneginf(matrix).any() and not (matrix < 0).any(), 'Invalid matrix duration')
        finite = np.isfinite(matrix)
        require(not (finite & (~queried | (matrix > 120))).any(), 'Finite unqueried/out-of-horizon duration')
        boundary = len(data['candidates'])
        require(not queried[:, boundary:].any() and not finite[:, boundary:].any(), 'Unsupported existing-hospital matrix entries')
        counts = {'computedCount': int(finite.sum()), 'queriedCount': int(queried.sum()),
                  'unknownQueriedCount': int((queried & ~finite).sum()), 'unqueriedCount': int((~queried).sum())}
        require(all(type(record.get(k)) is int and record[k] == v for k, v in counts.items()), 'Matrix counts mismatch')
        for k in ('queryCount', 'providerFailureCount', 'bulkFailureCount'):
            integer(record.get(k), k)
        require(record['providerFailureCount'] <= record['queryCount'], 'Impossible provider failure count')
        summaries[profile] = counts
    return summaries


def snapshot():
    """No HTTP: packaged source files and every present optional import are hashed."""
    codes = verifier_codes()
    manifest = motis.manifest()
    data = json.loads((motis.DATA / 'dataset.json').read_text(encoding='utf-8'))
    coords = np.load(motis.DATA / 'graph-coordinates.npy', allow_pickle=False)
    arrays = {}
    require(set(manifest.get('matrices', {})) == set(motis.PROFILES), 'All four matrices are required')
    for profile in motis.PROFILES:
        record = manifest['matrices'][profile]
        require(record.get('file') == profile + '-matrix.npz', 'Unexpected matrix path')
        path = motis.MATRIX_DIR / record['file']
        require(motis.file_sha(path) == record.get('sha256'), 'Matrix SHA mismatch')
        with np.load(path, allow_pickle=False) as z:
            require(set(z.files) == {'minutes', 'queried'}, 'Unexpected matrix archive members')
            arrays[profile] = (z['minutes'], z['queried'])
    summaries = validate_matrices(manifest, data, arrays)
    require(motis.manifest()['packageId'] == manifest['packageId'], 'Package changed during offline read')
    return {'manifest': manifest, 'data': data, 'coordinates': coords, 'arrays': arrays,
            'manifestSHA256': motis.file_sha(motis.MATRIX_DIR / 'manifest.json'),
            'verificationCodeLF_SHA256': codes, 'matrixSummaries': summaries}


def expected_request(snap, profile, i, j):
    data, coordinates = snap['data'], snap['coordinates']
    integer(i, 'demand index'); integer(j, 'candidate index')
    require(i < len(data['demands']) and j < len(data['candidates']), 'Sample index out of range')
    origin, destination = data['demands'][i], data['candidates'][j]
    o = coordinates[origin['node']]; d = coordinates[destination['node']]
    origin_access = number(origin['snapMeters'], 'origin connector')
    destination_access = number(destination['accessMeters'], 'destination connector')
    departure = timestamp(motis.PROFILES[profile])
    reached = departure + timedelta(seconds=origin_access / 1.25)
    query = datetime.fromtimestamp(math.ceil(reached.timestamp() / 60) * 60, timezone.utc)
    params = {**motis.PLAN_PARAMETERS, 'fromPlace': f'{float(o[1]):.8f},{float(o[0]):.8f}',
              'toPlace': f'{destination.get("entryLat", float(d[1])):.8f},{destination.get("entryLon", float(d[0])):.8f}',
              'time': query.isoformat().replace('+00:00', 'Z')}
    return params, departure, query, origin_access, destination_access


def _geometry(geometry):
    # Independent raw polyline validation, without creating substitute geometry.
    require(isinstance(geometry, dict) and isinstance(geometry.get('points'), str)
            and type(geometry.get('precision')) is int and 0 <= geometry['precision'] <= 8, 'Invalid raw geometry')
    s = geometry['points']; cursor = 0; coordinates = [0, 0]; count = 0
    while cursor < len(s):
        for axis in (0, 1):
            value = shift = 0
            while True:
                require(cursor < len(s) and shift <= 35, 'Truncated raw geometry')
                chunk = ord(s[cursor]) - 63; cursor += 1
                require(0 <= chunk <= 63, 'Invalid raw geometry character')
                value |= (chunk & 31) << shift; shift += 5
                if chunk < 32:
                    break
            coordinates[axis] += ~(value >> 1) if value & 1 else value >> 1
        require(abs(coordinates[0] / 10**geometry['precision']) <= 90
                and abs(coordinates[1] / 10**geometry['precision']) <= 180, 'Raw geometry coordinate range')
        count += 1
    require(count > 0, 'Empty raw geometry')


def derive_response(raw, departure, query, origin_access, destination_access):
    """Independent clock arithmetic and leg validation, not adapter interpretation."""
    require(isinstance(raw, dict) and isinstance(raw.get('direct'), list) and isinstance(raw.get('itineraries'), list),
            'Unsupported raw provider response')
    require(raw.get('error') in (None, False) and raw.get('status') in (None, 'success', 'ok'), 'Provider response reports failure')
    accepted = []
    for item in raw['direct'] + raw['itineraries']:
        require(isinstance(item, dict), 'Invalid provider itinerary')
        begin, end = timestamp(item.get('startTime')), timestamp(item.get('endTime'))
        legs = item.get('legs')
        require(begin >= query and end >= begin and isinstance(legs, list) and legs, 'Itinerary precedes requested origin access')
        previous = begin; boardings = rides = 0
        for index, leg in enumerate(legs):
            require(isinstance(leg, dict), 'Invalid raw leg')
            mode = leg.get('mode'); a, b = timestamp(leg.get('startTime')), timestamp(leg.get('endTime'))
            require(mode in motis.TRANSIT_MODES | {'WALK'} and a >= previous and a <= b <= end, 'Unsupported mode or nonmonotonic raw leg')
            require(leg.get('cancelled') is not True, 'Cancelled raw itinerary')
            interline = leg.get('interlineWithPreviousLeg', False)
            require(type(interline) is bool, 'Invalid interline state')
            if interline:
                require(index > 0 and mode != 'WALK' and legs[index-1].get('mode') != 'WALK', 'Interline lacks previous vehicle')
            _geometry(leg.get('legGeometry'))
            if mode != 'WALK':
                rides += 1; boardings += not interline
            previous = b
        require(timestamp(legs[0]['startTime']) == begin and previous == end and boardings <= 3, 'Raw itinerary boundary/transfer mismatch')
        minutes = ((end - departure).total_seconds() + destination_access / 1.25) / 60
        if 0 <= minutes <= 120:
            accepted.append({'minutes': minutes, 'journeyKind': 'transit' if rides else 'walk',
                'boardings': boardings, 'transfers': max(0, boardings-1),
                'originConnectorMinutes': origin_access / 75, 'destinationConnectorMinutes': destination_access / 75,
                'queryCeilingWaitMinutes': (query-departure).total_seconds()/60-origin_access/75,
                'initialWaitAfterQueryMinutes': (begin-query).total_seconds()/60,
                'providerArrivalTime': end.isoformat()})
    require(accepted, 'No validated in-horizon raw journey; unknown is not a successful check')
    return min(accepted, key=lambda x: (x['minutes'], x['boardings']))


def validate_capture(document, snap):
    manifest = snap['manifest']
    expected = {'format': 1, 'artifactType': 'motis-recorded-route-checks', 'provider': 'motis',
        'datasetScenario': motis.SCENARIO, 'engineVersion': motis.ENGINE_VERSION,
        'packageId': manifest['packageId'], 'manifestSHA256': snap['manifestSHA256'],
        'sourceSHA256': manifest['sourceSHA256'], 'codeLF_SHA256': manifest['codeLF_SHA256'],
        'verificationCodeLF_SHA256': snap['verificationCodeLF_SHA256'],
        'matrixSHA256': {p: manifest['matrices'][p]['sha256'] for p in motis.PROFILES},
        'currentOfficialEGO': False, 'allCandidateInfeasibilityProofAllowed': False,
        'matrixToleranceMinutes': TOLERANCE_MINUTES, 'captureMethod': 'local_plan_raw_response'}
    require(isinstance(document, dict) and set(document) == set(expected) | {'capturedAt', 'runtimeBefore',
        'runtimeAfter', 'cases', 'attemptedRequestsByProfile', 'walkAndTransitByProfile'}, 'Unsupported capture schema')
    require(type(document.get('format')) is int and all(document.get(k) == v
        and (not isinstance(v, bool) or type(document.get(k)) is bool) for k, v in expected.items()),
        'Capture source/provider/code/scope identity mismatch')
    require(document.get('runtimeBefore') == document.get('runtimeAfter'), 'Runtime changed during capture')
    runtime = document.get('runtimeBefore', {})
    require(runtime.get('processImportVerified') is True and runtime.get('listener') == '127.0.0.1:8088'
            and runtime.get('executable') == 'work/free-routing-research-2026-10-26/motis-2.10.2/motis.exe'
            and runtime.get('importDirectory') == 'work/free-routing-research-2026-10-26/local-motis/data', 'Unsupported runtime identity')
    integer(runtime.get('pid'), 'runtime PID', minimum=1); number(runtime.get('processCreatedEpoch'), 'process birth')
    timestamp(document.get('capturedAt'))
    cases = document.get('cases')
    require(isinstance(cases, list) and len(cases) == 8, 'Exactly eight route checks required')
    attempts = document.get('attemptedRequestsByProfile', {})
    require(set(attempts) == set(motis.PROFILES), 'Capture attempt profile set differs')
    require(all(type(n) is int and 2 <= n <= MAX_ATTEMPTS for n in attempts.values()), 'Capture request allowance exceeded')
    observed = {p: [] for p in motis.PROFILES}; seen = set(); max_difference = 0.
    for case in cases:
        require(isinstance(case, dict) and set(case) == {'profile','demandIndex','candidateIndex','demandId',
            'candidateId','requestedDeparture','originAccessMeters','destinationAccessMeters','request',
            'rawResponse','rawResponseSHA256','derived','matrixMinutes'}, 'Unsupported route-check schema')
        profile = case.get('profile'); require(profile in observed, 'Unknown sample profile')
        i, j = case.get('demandIndex'), case.get('candidateIndex')
        params, departure, query, origin_access, destination_access = expected_request(snap, profile, i, j)
        key = (profile, i, j); require(key not in seen, 'Duplicate route check'); seen.add(key)
        require(case.get('demandId') == str(snap['data']['demands'][i]['id'])
                and case.get('candidateId') == str(snap['data']['candidates'][j]['id'])
                and case.get('requestedDeparture') == motis.PROFILES[profile]
                and case.get('originAccessMeters') == origin_access and case.get('destinationAccessMeters') == destination_access,
                'Sample identities/connectors/date mismatch')
        require(case.get('request') == {'method': 'GET', 'endpoint': '/api/v6/plan', 'parameters': params}, 'Sample request parameters mismatch')
        raw = case.get('rawResponse')
        require(case.get('rawResponseSHA256') == hashlib.sha256(motis.canonical(raw)).hexdigest(), 'Raw response SHA mismatch')
        derived = derive_response(raw, departure, query, origin_access, destination_access)
        require(case.get('derived') == derived, 'Recorded derived journey differs from independent arithmetic')
        matrix, mask = snap['arrays'][profile]
        require(bool(mask[i,j]) and np.isfinite(matrix[i,j]), 'Sample is not a computed queried pair')
        number(case.get('matrixMinutes'), 'recorded matrix duration')
        require(case['matrixMinutes'] == float(matrix[i,j]), 'Sample matrix value mismatch')
        difference = abs(derived['minutes']-float(matrix[i,j])); max_difference = max(max_difference, difference)
        require(difference <= TOLERANCE_MINUTES, 'Raw arrival differs from saved matrix duration')
        observed[profile].append(derived['journeyKind'])
    require(all(len(v) == 2 for v in observed.values()), 'Each profile needs two route checks')
    diversity = {p: set(kinds) == {'walk', 'transit'} for p, kinds in observed.items()}
    require(document.get('walkAndTransitByProfile') == diversity, 'Sample diversity misreported')
    return {'status': 'validated_recorded_motis_snapshot', 'packageId': manifest['packageId'],
        'profiles': snap['matrixSummaries'], 'rawRouteChecks': 8, 'walkAndTransitByProfile': diversity,
        'maximumMatrixDifferenceMinutes': max_difference, 'networkQueriesPerformed': 0,
        'scope': 'Recorded historical-GTFS journeys and queried matrix cells; no current-service, complete-network or all-candidate infeasibility claim.'}


def audit():
    snap = snapshot()
    document = json.loads((motis.MATRIX_DIR / FILE_NAME).read_text(encoding='utf-8'))
    result = validate_capture(document, snap)
    require(motis.manifest()['packageId'] == snap['manifest']['packageId'] and verifier_codes() == snap['verificationCodeLF_SHA256'],
            'Package/code changed during offline audit')
    return result


def _sample_pairs(snap, profile):
    """Prefer high-population origins; alternate near walking/farther candidates."""
    matrix = snap['arrays'][profile][0][:, :len(snap['data']['candidates'])]
    populations = [number(d['population'], 'origin population') for d in snap['data']['demands']]
    origins = sorted(range(len(populations)), key=lambda i: (-populations[i], i))
    pairs = []
    for i in origins:
        finite = np.flatnonzero(np.isfinite(matrix[i]))
        if len(finite) < 2:
            continue
        near = min(finite, key=lambda j: (float(matrix[i,j]), int(j)))
        far = max((j for j in finite if j != near), key=lambda j: (float(matrix[i,j]), -int(j)))
        pairs.extend([(i, int(near)), (i, int(far))])
        if len(pairs) >= MAX_ATTEMPTS:
            break
    return pairs[:MAX_ATTEMPTS]


def capture_live():
    """Explicitly requested local capture; does not modify any matrix/manifest."""
    snap = snapshot(); manifest = snap['manifest']
    require(motis.require_live_sources()['packageId'] == manifest['packageId'], 'Live source package differs')
    before = motis_runtime.runtime_identity()
    document = {'format': 1, 'artifactType': 'motis-recorded-route-checks', 'provider': 'motis',
        'datasetScenario': motis.SCENARIO, 'engineVersion': motis.ENGINE_VERSION,
        'packageId': manifest['packageId'], 'manifestSHA256': snap['manifestSHA256'],
        'sourceSHA256': manifest['sourceSHA256'], 'codeLF_SHA256': manifest['codeLF_SHA256'],
        'verificationCodeLF_SHA256': snap['verificationCodeLF_SHA256'],
        'matrixSHA256': {p: manifest['matrices'][p]['sha256'] for p in motis.PROFILES},
        'capturedAt': datetime.now(timezone.utc).isoformat(), 'runtimeBefore': before,
        'currentOfficialEGO': False, 'allCandidateInfeasibilityProofAllowed': False,
        'matrixToleranceMinutes': TOLERANCE_MINUTES, 'captureMethod': 'local_plan_raw_response',
        'cases': [], 'attemptedRequestsByProfile': {}, 'walkAndTransitByProfile': {}}
    for profile in motis.PROFILES:
        candidates = []; attempts = 0
        for i, j in _sample_pairs(snap, profile):
            params, departure, query, oa, da = expected_request(snap, profile, i, j)
            raw = motis.request_json('/api/v6/plan', params=params); attempts += 1
            derived = derive_response(raw, departure, query, oa, da)
            value = float(snap['arrays'][profile][0][i,j])
            require(abs(derived['minutes']-value) <= TOLERANCE_MINUTES, 'Live provider differs from saved matrix; capture aborted')
            candidates.append({'profile': profile, 'demandIndex': i, 'candidateIndex': j,
                'demandId': str(snap['data']['demands'][i]['id']), 'candidateId': str(snap['data']['candidates'][j]['id']),
                'requestedDeparture': motis.PROFILES[profile], 'originAccessMeters': oa, 'destinationAccessMeters': da,
                'request': {'method': 'GET', 'endpoint': '/api/v6/plan', 'parameters': params},
                'rawResponse': raw, 'rawResponseSHA256': hashlib.sha256(motis.canonical(raw)).hexdigest(),
                'derived': derived, 'matrixMinutes': value})
            if {x['derived']['journeyKind'] for x in candidates} == {'walk', 'transit'}:
                break
        require(len(candidates) >= 2, 'Insufficient distinct computed pairs for two route checks')
        kinds = {x['derived']['journeyKind'] for x in candidates}
        chosen = [next(x for x in candidates if x['derived']['journeyKind'] == k) for k in ('walk', 'transit')] if len(kinds) == 2 else candidates[:2]
        document['cases'].extend(chosen)
        document['attemptedRequestsByProfile'][profile] = attempts
        document['walkAndTransitByProfile'][profile] = len(kinds) == 2
    document['runtimeAfter'] = motis_runtime.runtime_identity()
    require(motis.require_live_sources()['packageId'] == manifest['packageId'], 'Package changed during live capture')
    require(verifier_codes() == snap['verificationCodeLF_SHA256'], 'Verifier code changed during capture')
    validate_capture(document, snap)
    destination = motis.MATRIX_DIR / FILE_NAME
    require(motis.MATRIX_DIR.resolve() == motis.MATRIX_DIR.absolute() and destination.resolve().parent == motis.MATRIX_DIR.resolve()
            and not destination.is_symlink(), 'Capture output redirected outside expected package directory')
    fd, temporary = tempfile.mkstemp(prefix=FILE_NAME+'.', suffix='.tmp', dir=motis.MATRIX_DIR)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(motis.canonical(document)); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    result = audit()
    result.update(networkQueriesPerformed=sum(document['attemptedRequestsByProfile'].values()),
                  executionMode='live_capture_followed_by_offline_validation')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-live', action='store_true', help='Explicitly query local MOTIS and save eight raw checks')
    args = parser.parse_args()
    print(json.dumps(capture_live() if args.capture_live else audit(), ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
