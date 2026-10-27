"""Explicit local API capture of every allocation visible in the public map."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import threading
import time
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.publication import CACHE, cache_path, canonical, requests_for, sha, snapshot, validate_record, validated_cache
from scripts.build_motis_matrices import atomic_bytes

THREAD = threading.local()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--workers', type=int, choices=range(1,5), default=3)
    args = parser.parse_args()
    if not args.write: parser.error('Use --write to capture the local, already authorized routes')
    plan, plan_sha = snapshot()
    expected = requests_for(plan)
    code_sha = sha(Path(__file__).read_bytes().replace(b'\r\n',b'\n'))
    api = requests.get('http://127.0.0.1:8000/api/permanent-plan',timeout=30)
    api.raise_for_status()
    if api.json()['planId'] != plan['planId']: raise ValueError('Local API has another plan')
    entries = {}; errors = []; pending = []
    for key, (request, allocation) in expected.items():
        path = cache_path(plan, request)
        if path.is_file():
            blob = path.read_bytes()
            validate_record(json.loads(blob),request,allocation,plan,plan_sha)
            entries[key] = {'file':path.relative_to(CACHE).as_posix(),'sha256':sha(blob)}
        else: pending.append((key,request,allocation))
    print(f'Capture: {len(expected)} required, {len(entries)} validated cached, {len(pending)} local requests',flush=True)
    def capture(item):
        key,request,allocation = item
        if not hasattr(THREAD,'session'): THREAD.session = requests.Session()
        last = None
        for attempt in range(3):
            try:
                response = THREAD.session.post('http://127.0.0.1:8000/api/permanent-route',json=request,timeout=60)
                response.raise_for_status()
                record = {'format':1,'request':request,'response':response.json(), 'sourcePlanSHA256':plan_sha,
                    'capturedAt':datetime.now(timezone.utc).isoformat(), 'captureCodeLF_SHA256':code_sha}
                validate_record(record,request,allocation,plan,plan_sha)
                blob = canonical(record); path = cache_path(plan,request)
                atomic_bytes(path,blob)
                return key, {'file':path.relative_to(CACHE).as_posix(),'sha256':sha(blob)}
            except (OSError,requests.RequestException,ValueError) as exc:
                last = exc
                if attempt < 2: time.sleep(1 + attempt)
        raise RuntimeError(key + ': ' + str(last))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(capture,item):item[0] for item in pending}
        for future in as_completed(futures):
            try:
                key, entry = future.result(); entries[key] = entry
            except Exception as exc:
                errors.append(str(exc)); print('FAILED ' + str(exc),flush=True)
            if len(entries) % 100 == 0 or len(entries) == len(expected):
                print(f'Validated {len(entries)}/{len(expected)} routes',flush=True)
    if errors: raise RuntimeError(f'{len(errors)} routes unavailable; complete publication was not created')
    after, after_sha = snapshot()
    if after['planId'] != plan['planId'] or after_sha != plan_sha: raise ValueError('Plan changed during capture')
    counts = {v:sum(k.startswith(v + '/') for k in expected) for v in ('car','transit')}
    manifest = {'format':1,'artifactType':'precomputed-permanent-routes','planId':plan['planId'],
        'sourcePlanSHA256':plan_sha,'transitPackageId':plan['identity']['transitPackageId'],
        'completedAt':datetime.now(timezone.utc).isoformat(),'counts':counts,'routes':dict(sorted(entries.items())),
        'scope':'All positive allocations in the car and the single displayed critical transit profile; historical data, not live traffic or current EGO.'}
    atomic_bytes(CACHE / 'manifest.json',canonical(manifest))
    validated_cache(plan,plan_sha)
    print(json.dumps({'complete':True,'counts':counts,'planId':plan['planId']},ensure_ascii=False),flush=True)


if __name__ == '__main__': main()
