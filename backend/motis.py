"""Local MOTIS plan adapter; experimental bulk durations are never final costs.

Dates identify a historical community-GTFS scenario, not current EGO service.
Empty responses, unqueried pairs and provider errors are distinct unknowns.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import threading
from urllib.parse import urlsplit

import numpy as np
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/processed'
MATRIX_DIR = DATA / 'motis'
LOCAL = ROOT / 'work/free-routing-research-2026-10-26/local-motis'
BASE_URL = 'http://127.0.0.1:8088'
ENGINE_VERSION = '2.10.2'
SCENARIO = 'historical_Ankara_community_GTFS_user_accepted_20261026'
POLICY_VERSION = 'motis-local-plan-connectors-v1'
WALK_METERS_PER_SECOND = 1.25
MAX_MINUTES = 120.0
MAX_TRANSFERS = 2
PROFILES = {
    'weekday-0800': '2026-10-27T08:00:00+03:00',
    'weekday-1000': '2026-10-27T10:00:00+03:00',
    'saturday-1000': '2026-10-31T10:00:00+03:00',
    'sunday-1000': '2026-11-01T10:00:00+03:00',
}
PLAN_PARAMETERS = {
    'arriveBy': False, 'maxTravelTime': 120, 'maxTransfers': MAX_TRANSFERS,
    'maxMatchingDistance': 25, 'useRoutedTransfers': True,
    'pedestrianSpeed': WALK_METERS_PER_SECOND,
    'transitModes': 'TRANSIT', 'preTransitModes': 'WALK',
    'postTransitModes': 'WALK', 'directModes': 'WALK',
    'maxPreTransitTime': 2700, 'maxPostTransitTime': 2700,
    'maxDirectTime': 2700, 'timetableView': False, 'numItineraries': 5,
    'detailedTransfers': True, 'detailedLegs': True,
}
TRANSIT_MODES = frozenset({'TRAM', 'SUBWAY', 'FERRY', 'AIRPLANE', 'BUS',
    'COACH', 'RAIL', 'HIGHSPEED_RAIL', 'LONG_DISTANCE', 'NIGHT_RAIL',
    'REGIONAL_RAIL', 'REGIONAL_FAST_RAIL', 'SUBURBAN', 'METRO', 'CABLE_CAR', 'FUNICULAR', 'AERIAL_LIFT', 'AREAL_LIFT',
    'OTHER', 'TROLLEYBUS', 'MONORAIL'})
_THREAD = threading.local()


class MotisUnavailable(RuntimeError):
    """Provider failed or cannot supply a validated journey (not no-service)."""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def code_sha(path):
    return hashlib.sha256(Path(path).read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def _number(value, name, minimum=0):
    if isinstance(value, (bool, str)) or not isinstance(value, (int, float, np.number)):
        raise ValueError(f'{name} must be a finite number')
    result = float(value)
    if not math.isfinite(result) or result < minimum:
        raise ValueError(f'{name} must be finite and >= {minimum}')
    return result


def point(value):
    if not isinstance(value, (tuple, list, np.ndarray)) or len(value) != 2:
        raise ValueError('A point must be (latitude, longitude)')
    lat = _number(value[0], 'latitude', -90)
    lon = _number(value[1], 'longitude', -180)
    if lat > 90 or lon > 180:
        raise ValueError('Coordinate out of range')
    return (lat, lon)


def point_string(value):
    return ','.join(f'{x:.8f}' for x in point(value))


def start_times(profile, origin_access_meters=0):
    if profile not in PROFILES:
        raise ValueError('Unknown dated MOTIS profile')
    start = datetime.fromisoformat(PROFILES[profile])
    access = _number(origin_access_meters, 'origin access') / WALK_METERS_PER_SECOND
    reached = start + timedelta(seconds=access)
    # MOTIS truncates input timestamps to minutes; ceil prevents boarding before
    # the explicit origin connector has been traversed.
    query = datetime.fromtimestamp(math.ceil(reached.timestamp() / 60) * 60, timezone.utc)
    return start, query, access, (query - reached).total_seconds()


def plan_parameters(origin, destination, profile, origin_access_meters=0):
    _, query, _, _ = start_times(profile, origin_access_meters)
    return {**PLAN_PARAMETERS, 'fromPlace': point_string(origin),
            'toPlace': point_string(destination),
            'time': query.isoformat().replace('+00:00', 'Z')}


def _session():
    if not hasattr(_THREAD, 'session'):
        _THREAD.session = requests.Session()
        _THREAD.session.trust_env = False  # local service never uses a proxy
    return _THREAD.session


def request_json(path, *, params=None, payload=None, timeout=45):
    parsed = urlsplit(BASE_URL)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.port != 8088:
        raise ValueError('This adapter permits only local MOTIS at 127.0.0.1:8088')
    if path not in ('/api/v6/plan', '/api/v1/map/initial',
                    '/api/experimental/one-to-many-intermodal'):
        raise ValueError('Unsupported local MOTIS endpoint')
    try:
        if payload is None:
            query = {k: str(v).lower() if isinstance(v, bool) else v for k, v in (params or {}).items()}
            response = _session().get(BASE_URL + path, params=query, timeout=timeout, allow_redirects=False)
        else:
            response = _session().post(BASE_URL + path, json=payload, timeout=timeout, allow_redirects=False)
        if response.status_code != 200:
            raise MotisUnavailable(f'Local MOTIS HTTP {response.status_code}; result unknown')
        result = response.json()
        if not isinstance(result, dict):
            raise MotisUnavailable('Local MOTIS returned an invalid response; result unknown')
        return result
    except (requests.RequestException, ValueError) as exc:
        raise MotisUnavailable(f'Local MOTIS unavailable or invalid response: {type(exc).__name__}') from exc


def _time(value):
    if not isinstance(value, str):
        raise ValueError('Missing provider timestamp')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Provider timestamp needs timezone')
    return result


def decode_polyline(geometry):
    """Decode provider geometry as [longitude, latitude]; no straight fallback."""
    if not isinstance(geometry, dict) or not isinstance(geometry.get('points'), str):
        raise ValueError('Missing raw MOTIS leg geometry')
    precision = geometry.get('precision')
    if type(precision) is not int or not 0 <= precision <= 8:
        raise ValueError('Invalid polyline precision')
    encoded = geometry['points']; cursor = 0; lat = lon = 0; result = []
    def integer():
        nonlocal cursor
        number = shift = 0
        while True:
            if cursor >= len(encoded) or shift > 35:
                raise ValueError('Truncated or excessive encoded polyline')
            value = ord(encoded[cursor]) - 63; cursor += 1
            if value < 0 or value > 63:
                raise ValueError('Invalid polyline character')
            number |= (value & 31) << shift; shift += 5
            if value < 32:
                return ~(number >> 1) if number & 1 else number >> 1
    while cursor < len(encoded):
        lat += integer(); lon += integer()
        p = point((lat / 10**precision, lon / 10**precision))
        result.append([p[1], p[0]])
    if not result:
        raise ValueError('Empty raw MOTIS geometry')
    return result


def interpret_response(response, profile, origin_access_meters=0, destination_access_meters=0):
    """Select the earliest validated arrival, including initial wait/connectors."""
    start, query, origin_seconds, ceiling_seconds = start_times(profile, origin_access_meters)
    destination_seconds = _number(destination_access_meters, 'destination access') / WALK_METERS_PER_SECOND
    if not isinstance(response, dict):
        raise ValueError('Invalid MOTIS response')
    choices = []
    for key in ('direct', 'itineraries'):
        values = response.get(key)
        if not isinstance(values, list):
            raise ValueError(f'Missing MOTIS {key} list')
        choices.extend(values)
    accepted = []; invalid = 0
    for item in choices:
        try:
            begin, end = _time(item['startTime']), _time(item['endTime'])
            legs = item['legs']
            if not isinstance(legs, list) or not legs or begin < query or end < begin:
                raise ValueError('Invalid itinerary times/legs')
            output = []; boardings = []; previous = begin
            for leg in legs:
                mode = leg['mode']; a, b = _time(leg['startTime']), _time(leg['endTime'])
                if mode not in TRANSIT_MODES | {'WALK'} or a < previous or b < a or b > end:
                    raise ValueError('Unsupported mode or non-monotonic journey')
                if leg.get('cancelled') is True:
                    raise ValueError('Cancelled leg')
                geometry = decode_polyline(leg.get('legGeometry'))
                output.append({'kind': 'walk' if mode == 'WALK' else 'ride',
                    'label': 'MOTIS · yürüyüş' if mode == 'WALK' else str(leg.get('displayName') or leg.get('routeShortName') or mode),
                    'coordinates': geometry, 'mode': mode, 'startTime': leg['startTime'],
                    'endTime': leg['endTime'], 'rawGeometry': leg['legGeometry'],
                    'tripId': leg.get('tripId'), 'routeId': leg.get('routeId')})
                if mode != 'WALK' and not leg.get('interlineWithPreviousLeg', False):
                    boardings.append({'route': str(leg.get('routeShortName') or leg.get('displayName') or mode),
                        'stop': str(leg.get('from', {}).get('name', '')), 'mode': mode,
                        'departure': a.astimezone(timezone(timedelta(hours=3))).strftime('%H:%M'),
                        'departureTime': leg['startTime'], 'tripId': leg.get('tripId')})
                previous = b
            if previous != end or _time(legs[0]['startTime']) != begin or len(boardings) > MAX_TRANSFERS + 1:
                raise ValueError('Itinerary boundary or boarding count mismatch')
            minutes = ((end - start).total_seconds() + destination_seconds) / 60
            if not 0 <= minutes <= MAX_MINUTES:
                continue
            accepted.append({'minutes': minutes, 'legs': output, 'boardings': boardings,
                'requestedTime': start.isoformat(), 'motorQueryTime': query.isoformat(),
                'arrivalTime': (end + timedelta(seconds=destination_seconds)).isoformat(),
                'originConnectorMinutes': origin_seconds / 60,
                'destinationConnectorMinutes': destination_seconds / 60,
                'queryCeilingWaitMinutes': ceiling_seconds / 60,
                'initialWaitAfterQueryMinutes': (begin - query).total_seconds() / 60,
                'providerArrivalTime': end.isoformat(), 'provider': 'motis',
                'datasetScenario': SCENARIO, 'profile': profile})
        except (ValueError, TypeError, KeyError, OverflowError):
            invalid += 1
    if not accepted:
        return {'status': 'unknown', 'reason': 'invalid_provider_itineraries' if invalid else 'empty_or_outside_search_horizon',
                'minutes': None, 'invalidItineraryCount': invalid}
    result = min(accepted, key=lambda x: (x['minutes'], len(x['boardings'])))
    return {'status': 'computed', **result, 'invalidItineraryCount': invalid}


def query_plan(origin, destination, profile, origin_access_meters=0, destination_access_meters=0):
    params = plan_parameters(origin, destination, profile, origin_access_meters)
    response = request_json('/api/v6/plan', params=params)
    return interpret_response(response, profile, origin_access_meters, destination_access_meters)


def plan(origin, destination, profile, origin_access_meters=0, destination_access_meters=0):
    require_live_sources()
    result = query_plan(origin, destination, profile, origin_access_meters, destination_access_meters)
    if result['status'] != 'computed':
        raise MotisUnavailable('MOTIS journey unknown: ' + result['reason'])
    result['evidence'] = evidence(profile)
    return result


def source_files():
    manifest = json.loads((LOCAL / 'source-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('scenario') != SCENARIO or manifest.get('engine', {}).get('version') != ENGINE_VERSION:
        raise ValueError('MOTIS source scenario/version mismatch')
    paths = {'dataset': DATA / 'dataset.json', 'graphCoordinates': DATA / 'graph-coordinates.npy',
        'carMatrix': DATA / 'car-matrix.npz', 'runtimeConfig': LOCAL / 'data/config.yml',
        'sourceManifest': LOCAL / 'source-manifest.json', 'config': LOCAL / 'config.yml',
        'GTFS': ROOT / manifest['GTFS']['path'], 'OSM': ROOT / manifest['OSM']['path'],
        'engine': LOCAL.parent / 'motis-2.10.2/motis.exe'}
    # MOTIS server consumes imported data/config.yml, not the import input
    # config. Bind those immutable imported bytes as well as the raw sources.
    for path in sorted((LOCAL / 'data').rglob('*')):
        relative = path.relative_to(LOCAL / 'data')
        if path.is_file() and 'logs' not in relative.parts and path != LOCAL / 'data/config.yml':
            paths['imported/' + relative.as_posix()] = path
    hashes = {key: file_sha(path) for key, path in paths.items()}
    for key, expected in [('GTFS', manifest['GTFS']['sha256']), ('OSM', manifest['OSM']['sha256']),
                          ('config', manifest['configSHA256']), ('runtimeConfig', manifest['runtimeConfigSHA256']),
                          ('engine', manifest['engine']['executableSHA256'])]:
        if hashes[key] != expected:
            raise ValueError('Local MOTIS source hash mismatch: ' + key)
    return paths, hashes


def model_codes():
    return {str(p.relative_to(ROOT)).replace('\\', '/'): code_sha(p) for p in
            (ROOT / 'backend/motis.py', ROOT / 'scripts/build_motis_matrices.py')}


def _signature(paths):
    return tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in paths)


@lru_cache(maxsize=8)
def _validated_manifest(signature):
    del signature
    path = MATRIX_DIR / 'manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('policyVersion') != POLICY_VERSION or manifest.get('scenario') != SCENARIO:
        raise ValueError('Stale MOTIS matrix policy/scenario')
    if manifest.get('planParameters') != PLAN_PARAMETERS or manifest.get('profiles') != PROFILES:
        raise ValueError('MOTIS matrix parameters or dated profiles differ')
    paths = _manifest_source_paths(manifest)
    expected = manifest.get('sourceSHA256', {})
    if not isinstance(expected, dict) or set(expected) != set(paths):
        raise ValueError('MOTIS source manifest is incomplete')
    # A published matrix remains usable without the private local import/cache.
    # Every present source is verified; the packaged numerical inputs are required.
    for key, source_path in paths.items():
        if key in ('dataset', 'graphCoordinates', 'carMatrix') or source_path.exists():
            if not source_path.is_file() or file_sha(source_path) != expected[key]:
                raise ValueError('MOTIS source changed: ' + key)
    if manifest.get('codeLF_SHA256') != model_codes():
        raise ValueError('MOTIS matrix input or code changed; rebuild required')
    package = {k: v for k, v in manifest.items() if k != 'packageId'}
    expected = 'motis-' + hashlib.sha256(canonical(package)).hexdigest()
    if manifest.get('packageId') != expected:
        raise ValueError('MOTIS manifest identity mismatch')
    return manifest


def _manifest_source_paths(value):
    references = value.get('sourceFiles')
    if not isinstance(references, dict):
        raise ValueError('MOTIS source file identities missing')
    if not {'dataset', 'graphCoordinates', 'carMatrix', 'sourceManifest', 'config', 'runtimeConfig',
            'GTFS', 'OSM', 'engine', 'imported/tt.bin', 'imported/osr/routing.bin'} <= references.keys():
        raise ValueError('MOTIS runtime source identity is incomplete')
    paths = {}
    for key, reference in references.items():
        if not isinstance(reference, str) or Path(reference).is_absolute():
            raise ValueError('Invalid source path')
        path = (ROOT / reference).resolve()
        if not path.is_relative_to(ROOT.resolve()):
            raise ValueError('Source path escapes repository')
        paths[key] = path
    required = {'dataset': DATA / 'dataset.json', 'graphCoordinates': DATA / 'graph-coordinates.npy',
                'carMatrix': DATA / 'car-matrix.npz'}
    if any(paths.get(k) != p.resolve() for k, p in required.items()):
        raise ValueError('Packaged matrix input path mismatch')
    return paths


def manifest():
    path = MATRIX_DIR / 'manifest.json'
    if not path.is_file():
        raise ValueError('Yerel MOTIS matrisi henüz hazırlanmadı')
    value = json.loads(path.read_text(encoding='utf-8'))
    sources = _manifest_source_paths(value)
    paths = [path, ROOT / 'backend/motis.py', ROOT / 'scripts/build_motis_matrices.py', *sources.values()]
    signature = tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns) if p.exists()
                      else (str(p), None, None) for p in paths)
    return _validated_manifest(signature)


def require_live_sources():
    value = manifest()
    paths = _manifest_source_paths(value)
    if any(not path.is_file() for path in paths.values()):
        raise MotisUnavailable('Live MOTIS requires all locally imported source files; cached matrix remains available')
    service = request_json('/api/v1/map/initial', timeout=2).get('serverConfig', {})
    if service.get('motisVersion') != 'v' + ENGINE_VERSION or service.get('hasRoutedTransfers') is not True:
        raise MotisUnavailable('Live MOTIS engine does not match the matrix scenario')
    return value


@lru_cache(maxsize=4)
def _load(profile, package_id, signature):
    del package_id, signature
    m = manifest(); record = m.get('matrices', {}).get(profile)
    if not isinstance(record, dict) or record.get('file') != f'{profile}-matrix.npz':
        raise ValueError('MOTIS matrix profile missing')
    path = MATRIX_DIR / record['file']
    if file_sha(path) != record['sha256']:
        raise ValueError('MOTIS matrix checksum mismatch')
    with np.load(path, allow_pickle=False) as loaded:
        matrix = loaded['minutes']; queried = loaded['queried']
    data = json.loads((DATA / 'dataset.json').read_text(encoding='utf-8'))
    shape = (len(data['demands']), len(data['candidates']) + len(data['hospitals']))
    expected_indices = {key: [str(x['id']) for x in data[key]] for key in ('demands', 'candidates', 'hospitals')}
    if m.get('indices') != expected_indices or m.get('indexSHA256') != hashlib.sha256(canonical(expected_indices)).hexdigest():
        raise ValueError('MOTIS demand/candidate ordering mismatch')
    if matrix.shape != shape or queried.shape != shape or queried.dtype != bool or matrix.dtype != np.float32 or record['shape'] != list(shape):
        raise ValueError('MOTIS matrix shape/mask mismatch')
    if np.isnan(matrix).any() or np.isneginf(matrix).any() or (matrix < 0).any() or (np.isfinite(matrix) & (~queried | (matrix > MAX_MINUTES))).any():
        raise ValueError('Invalid MOTIS minute matrix')
    if int(np.isfinite(matrix).sum()) != record['computedCount'] or int(queried.sum()) != record['queriedCount']:
        raise ValueError('MOTIS matrix counts mismatch')
    if (int((queried & ~np.isfinite(matrix)).sum()) != record['unknownQueriedCount']
            or int((~queried).sum()) != record['unqueriedCount']):
        raise ValueError('MOTIS unknown/unqueried counts mismatch')
    if queried[:, len(data['candidates']):].any():
        raise ValueError('Existing MOTIS comparison is not part of this package')
    matrix.setflags(write=False)
    return matrix


def load_matrix(profile):
    if profile not in PROFILES:
        raise ValueError('Unknown MOTIS profile')
    m = manifest(); path = MATRIX_DIR / f'{profile}-matrix.npz'
    return _load(profile, m['packageId'], _signature([path]))


def evidence(profile):
    m = manifest(); load_matrix(profile)
    return {'engine': 'motis', 'engineVersion': ENGINE_VERSION, 'datasetScenario': SCENARIO,
        'packageId': m['packageId'], 'profile': profile, 'departure': PROFILES[profile],
        'profileDate': PROFILES[profile][:10], 'actualProfileDate': PROFILES[profile][:10],
        'gtfsSHA256': m['sourceSHA256']['GTFS'], 'existingComparisonAvailable': False,
        'timeZone': 'Europe/Istanbul', 'sourceSHA256': m['sourceSHA256'],
        'searchScope': m['searchScope'], 'matrix': m['matrices'][profile],
        'historicalCommunityGTFS': True, 'currentOfficialEGO': False,
        'unknownMeansNoService': False, 'allCandidateInfeasibilityProofAllowed': False,
        'assumedConnectorSpeedMetersPerSecond': WALK_METERS_PER_SECOND,
        'originConnectorBeforeQuery': True, 'queryTimeRoundedUpToMinute': True}


def routing_status():
    result = {'ready': False, 'matrixProfiles': [], 'detail': 'Yerel MOTIS matrisi henüz hazır değil.',
              'engineVersion': ENGINE_VERSION, 'datasetScenario': SCENARIO, 'serviceAvailable': False}
    try:
        service = request_json('/api/v1/map/initial', timeout=2)['serverConfig']
        result['serviceAvailable'] = service.get('motisVersion') == 'v' + ENGINE_VERSION and service.get('hasStreetRouting') is True
    except (RuntimeError, ValueError, KeyError, OSError):
        pass
    try:
        m = manifest()
        for profile in m.get('matrices', {}):
            load_matrix(profile); result['matrixProfiles'].append(profile)
        result['ready'] = bool(result['matrixProfiles'])
        result['detail'] = (f'Tarihsel GTFS senaryosu: {len(result["matrixProfiles"])} kayıtlı profil hesaplamaya hazır. '
                            + ('Canlı rota motoru açık.' if result['serviceAvailable'] else 'Canlı güzergâh için yerel MOTIS motoru gerekir.'))
    except (RuntimeError, ValueError, KeyError, OSError) as exc:
        result['detail'] = str(exc)
    return result
