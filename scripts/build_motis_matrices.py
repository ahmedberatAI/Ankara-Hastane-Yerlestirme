"""Build restricted-edge matrices using only the local canonical /plan endpoint.

Experimental bulk costs select candidates; they never enter the final matrix.
Default runs a 100-origin pilot under work/. --write explicitly publishes complete
profiles. No calls are made to public Transitous infrastructure.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from backend import motis

SHORTLIST = 12


def atomic_bytes(path, content):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_npz(path, **arrays):
    import io
    buffer = io.BytesIO(); np.savez_compressed(buffer, **arrays)
    atomic_bytes(path, buffer.getvalue())


def entry_groups(candidates, coordinates):
    entries = []; groups = []; mapping = {}; candidate_entry = []
    for i, candidate in enumerate(candidates):
        ll = coordinates[candidate['node']]
        value = (candidate.get('entryLat', float(ll[1])), candidate.get('entryLon', float(ll[0])))
        key = motis.point_string(value)
        if key not in mapping:
            mapping[key] = len(entries); entries.append(motis.point(value)); groups.append([])
        idx = mapping[key]; candidate_entry.append(idx); groups[idx].append(i)
    return entries, groups, np.array(candidate_entry, dtype=np.int64)


def bulk_scores(origin, entries, profile, origin_access_meters, batch_size):
    """Hints only, with the same modes/transfers/speed as canonical /plan."""
    _, query, _, _ = motis.start_times(profile, origin_access_meters)
    common = {k: v for k, v in motis.PLAN_PARAMETERS.items() if k not in
              ('directModes', 'timetableView', 'numItineraries', 'detailedTransfers', 'detailedLegs')}
    for key in ('transitModes', 'preTransitModes', 'postTransitModes'):
        common[key] = [common[key]]
    common.update(one=motis.point_string(origin), time=query.isoformat().replace('+00:00', 'Z'), directMode='WALK')
    result = np.full(len(entries), np.inf); errors = []
    for first in range(0, len(entries), batch_size):
        last = min(first + batch_size, len(entries))
        try:
            response = motis.request_json('/api/experimental/one-to-many-intermodal',
                payload={**common, 'many': [motis.point_string(x) for x in entries[first:last]]})
            direct, transit = response['street_durations'], response['transit_durations']
            if not isinstance(direct, list) or not isinstance(transit, list) or len(direct) != last-first or len(transit) != last-first:
                raise ValueError('Bulk response shape mismatch')
            for local, (street, journeys) in enumerate(zip(direct, transit)):
                if not isinstance(street, dict) or not isinstance(journeys, list):
                    raise ValueError('Malformed bulk response')
                durations = []
                for item in [street, *journeys]:
                    if isinstance(item, dict) and 'duration' in item:
                        durations.append(motis._number(item['duration'], 'bulk duration'))
                if durations:
                    result[first+local] = min(durations) / 60
        except (motis.MotisUnavailable, ValueError, KeyError) as exc:
            errors.append({'firstEntry': first, 'lastEntryExclusive': last, 'reason': str(exc)})
    return result, errors


def shortlist_indices(bulk, car, radii, per_class=SHORTLIST):
    if type(per_class) is not int or per_class < 1:
        raise ValueError('Shortlist size must be positive integer')
    selected = set()
    for radius in sorted(set(radii.tolist())):
        members = np.flatnonzero(radii == radius)
        for scores in (bulk, car):
            valid = members[np.isfinite(scores[members])]
            ordered = sorted(valid, key=lambda i: (float(scores[i]), int(i)))
            selected.update(int(i) for i in ordered[:per_class])
    return sorted(selected)


def calculate_row(i, profile, data, coordinates, car, entries, groups, candidate_entry, batch_size, per_class):
    demand = data['demands'][i]; ll = coordinates[demand['node']]
    origin = (float(ll[1]), float(ll[0])); access = float(demand['snapMeters'])
    hints, bulk_errors = bulk_scores(origin, entries, profile, access, batch_size)
    destination_access = np.array([c['accessMeters'] for c in data['candidates']], dtype=float) / 75
    radii = np.array([c['footprintRadiusMeters'] for c in data['candidates']])
    hint_minutes = hints[candidate_entry] + destination_access
    selected = shortlist_indices(hint_minutes, car[i, :len(radii)], radii, per_class)
    selected_entries = sorted(set(int(candidate_entry[j]) for j in selected))
    row = np.full(len(data['candidates']) + len(data['hospitals']), np.inf, dtype=np.float32)
    queried = np.zeros(len(row), dtype=bool); errors = []; valid = 0; empty = 0
    examples = []
    for entry in selected_entries:
        # One physical entry can serve several hypothetical footprints. The
        # destination connector is added separately for every candidate alias.
        try:
            response = motis.query_plan(origin, entries[entry], profile, access, 0)
        except (motis.MotisUnavailable, ValueError) as exc:
            response = {'status': 'unknown', 'reason': 'provider_failure', 'minutes': None}
            errors.append({'entryIndex': entry, 'reason': str(exc)})
        for j in groups[entry]:
            queried[j] = True
            if response['status'] == 'computed':
                minutes = response['minutes'] + destination_access[j]
                if minutes <= motis.MAX_MINUTES:
                    row[j] = minutes
        if response['status'] == 'computed':
            valid += 1
            if len(examples) < 2:
                examples.append({'entryIndex': entry, 'candidateIndices': groups[entry],
                    'motorAndOriginMinutes': response['minutes'], 'motorQueryTime': response['motorQueryTime'],
                    'providerArrivalTime': response['providerArrivalTime'],
                    'tripIds': [b['tripId'] for b in response['boardings']]})
        else:
            empty += 1
    return i, row, queried, {'demandIndex': i, 'demandId': str(demand['id']),
        'selectedEntryCount': len(selected_entries), 'selectedCandidateCount': len(selected),
        'computedEntryCount': valid, 'unknownEntryCount': empty,
        'bulkErrors': bulk_errors, 'planErrors': errors, 'examples': examples}


def input_indices(data):
    return {'demands': [str(x['id']) for x in data['demands']],
            'candidates': [str(x['id']) for x in data['candidates']],
            'hospitals': [str(x['id']) for x in data['hospitals']]}


def build_profile(profile, *, write=False, pilot_count=100, workers=4, per_class=SHORTLIST):
    started = time.perf_counter(); paths, source_hashes = motis.source_files(); codes = motis.model_codes()
    service = motis.request_json('/api/v1/map/initial')['serverConfig']
    if service.get('motisVersion') != 'v' + motis.ENGINE_VERSION or service.get('hasRoutedTransfers') is not True:
        raise ValueError('Unexpected local MOTIS engine or missing routed transfers')
    batch_size = min(2000, int(service['maxOneToManySize']))
    data = json.loads(paths['dataset'].read_text(encoding='utf-8'))
    coordinates = np.load(paths['graphCoordinates'], allow_pickle=False)
    with np.load(paths['carMatrix'], allow_pickle=False) as source:
        car = source['minutes']
    entries, groups, candidate_entry = entry_groups(data['candidates'], coordinates)
    count = len(data['demands']) if write else min(pilot_count, len(data['demands']))
    shape = (len(data['demands']), len(data['candidates']) + len(data['hospitals']))
    if car.shape != shape:
        raise ValueError('Car shortlist matrix does not match current dataset')
    matrix = np.full(shape, np.inf, dtype=np.float32); queried = np.zeros(shape, dtype=bool)
    reports = [None] * count; completed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(calculate_row, i, profile, data, coordinates, car, entries, groups,
                               candidate_entry, batch_size, per_class) for i in range(count)]
        for future in as_completed(futures):
            i, row, mask, report = future.result(); matrix[i] = row; queried[i] = mask; reports[i] = report
            completed += 1
            if completed % 100 == 0 or completed == count:
                print(json.dumps({'profile': profile, 'completedOrigins': completed, 'totalOrigins': count,
                    'elapsedSeconds': round(time.perf_counter()-started, 3)}, ensure_ascii=False), flush=True)
    _, exit_hashes = motis.source_files()
    if source_hashes != exit_hashes or codes != motis.model_codes():
        raise RuntimeError('MOTIS sources/code changed during routing; nothing published')
    indices = input_indices(data)
    report = {'format': 1, 'profile': profile, 'date': motis.PROFILES[profile],
        'sourceSHA256': source_hashes, 'codeLF_SHA256': codes, 'indexSHA256': hashlib.sha256(motis.canonical(indices)).hexdigest(),
        'shape': list(shape), 'processedOriginCount': count, 'totalOriginCount': len(data['demands']),
        'queryCount': sum(x['selectedEntryCount'] for x in reports),
        'providerFailureCount': sum(len(x['planErrors']) for x in reports),
        'bulkFailureCount': sum(len(x['bulkErrors']) for x in reports),
        'computedCount': int(np.isfinite(matrix).sum()), 'queriedCount': int(queried.sum()),
        'unknownQueriedCount': int((queried & ~np.isfinite(matrix)).sum()),
        'unqueriedCount': int((~queried).sum()), 'existingComparisonAvailable': False,
        'batchSize': batch_size, 'uniqueEntryCount': len(entries), 'elapsedSeconds': time.perf_counter()-started,
        'originReports': reports}
    audit_dir = ROOT / 'work/motis-build' / ('full' if write else 'pilot')
    audit_dir.mkdir(parents=True, exist_ok=True)
    atomic_bytes(audit_dir / f'{profile}-report.json', motis.canonical(report))
    if not write:
        atomic_npz(audit_dir / f'{profile}-matrix.npz', minutes=matrix, queried=queried)
        return report
    out = motis.MATRIX_DIR; out.mkdir(parents=True, exist_ok=True)
    destination = out / f'{profile}-matrix.npz'
    previous = out / 'manifest.json'
    if previous.exists():
        manifest = json.loads(previous.read_text(encoding='utf-8'))
        if manifest.get('sourceSHA256') != source_hashes or manifest.get('codeLF_SHA256') != codes:
            raise RuntimeError('Existing MOTIS package has different inputs; use a fresh output directory')
        manifest.pop('packageId', None)
    else:
        manifest = {'format': 1, 'policyVersion': motis.POLICY_VERSION, 'scenario': motis.SCENARIO,
            'engineVersion': motis.ENGINE_VERSION, 'profiles': motis.PROFILES,
            'planParameters': motis.PLAN_PARAMETERS, 'sourceSHA256': source_hashes, 'codeLF_SHA256': codes,
            'sourceFiles': {key: path.relative_to(ROOT).as_posix() for key, path in paths.items()},
            'indices': indices, 'indexSHA256': report['indexSHA256'], 'matrices': {},
            'existingComparisonAvailable': False,
            'searchScope': {'kind': 'restricted_edges', 'allCandidateInfeasibilityProofAllowed': False,
                'bulkIsOnlyShortlistHint': True, 'finalEndpoint': '/api/v6/plan',
                'bulkAndPlanEquivalent': False, 'perFootprintClass': per_class,
                'selection': 'union of bulk-duration and car-duration nearest candidates per footprint; physical-entry aliases included',
                'unqueriedMeans': 'unknown, not no service', 'emptyPlanMeans': 'unknown within dated data and search limits',
                'connectorSpeedMetersPerSecond': 1.25, 'originConnectorBeforeQuery': True,
                'queryTimeCeilingMinutes': True, 'maximumTotalMinutes': motis.MAX_MINUTES,
                'currentOfficialEGO': False}}
    atomic_npz(destination, minutes=matrix, queried=queried)
    manifest['matrices'][profile] = {key: report[key] for key in
        ('shape', 'computedCount', 'queriedCount', 'unknownQueriedCount', 'unqueriedCount',
         'queryCount', 'providerFailureCount', 'bulkFailureCount', 'elapsedSeconds')}
    manifest['matrices'][profile].update(file=destination.name, sha256=motis.file_sha(destination),
        departure=motis.PROFILES[profile], builtAt=datetime.now(timezone.utc).isoformat(),
        auditSHA256=motis.file_sha(audit_dir / f'{profile}-report.json'))
    manifest['packageId'] = 'motis-' + hashlib.sha256(motis.canonical(manifest)).hexdigest()
    atomic_bytes(previous, motis.canonical(manifest))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profiles', nargs='+', choices=list(motis.PROFILES), default=['weekday-1000'])
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--pilot-count', type=int, default=100)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4 or not 1 <= args.pilot_count <= 1413:
        parser.error('workers must be 1..4 and pilot count 1..1413')
    for profile in args.profiles:
        report = build_profile(profile, write=args.write, pilot_count=args.pilot_count, workers=args.workers)
        print(json.dumps({k: report[k] for k in ('profile', 'queryCount', 'computedCount', 'queriedCount',
            'providerFailureCount', 'bulkFailureCount', 'elapsedSeconds')}), flush=True)


if __name__ == '__main__':
    main()
