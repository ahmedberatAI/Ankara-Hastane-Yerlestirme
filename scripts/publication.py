"""Shared, offline validation for the precomputed public presentation."""
import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'data/precomputed-routes'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf8')


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def snapshot():
    from backend.permanent_service import read_plan
    from backend.permanent_evidence import PLAN_FILE
    plan = read_plan()
    blob = PLAN_FILE.read_bytes()
    require(json.loads(blob)['planId'] == plan['planId'], 'Plan changed while preparing publication')
    return plan, sha(blob)


def requests_for(plan):
    result = {}
    for view in ('car', 'transit'):
        profile = 'car' if view == 'car' else plan['criticalTransitProfile']
        for assignment in plan['profiles'][profile]['assignments']:
            for part in assignment['allocations']:
                require(number(part['population']) and part['population'] > 0, 'Nonpositive public allocation')
                request = {'planId':plan['planId'], 'view':view,
                    'demandId':assignment['demandId'], 'candidateId':part['candidateId']}
                require(all(re.fullmatch(r'[A-Za-z0-9_-]+', request[k]) for k in ('demandId','candidateId')), 'Unsafe route identity')
                key = view + '/' + request['demandId'] + '/' + request['candidateId']
                require(key not in result, 'Duplicate allocation route')
                result[key] = (request, part)
    return result


def validate_record(record, request, allocation, plan, plan_sha):
    require(type(record) is dict and type(record.get('format')) is int and record['format'] == 1, 'Invalid route record format')
    require(record.get('request') == request and record.get('sourcePlanSHA256') == plan_sha, 'Route record belongs to another plan')
    require(type(record.get('capturedAt')) is str and bool(record['capturedAt']), 'Missing capture time')
    require(type(record.get('captureCodeLF_SHA256')) is str and re.fullmatch('[a-f0-9]{64}',record['captureCodeLF_SHA256']), 'Missing capture code identity')
    r = record.get('response', {})
    profile = 'car' if request['view'] == 'car' else plan['criticalTransitProfile']
    require(r.get('planId') == plan['planId'] and r.get('profileId') == profile and r.get('routeMode') == request['view'], 'Route view/profile mismatch')
    require(number(r.get('minutes')) and abs(r['minutes'] - allocation['minutes']) <= .001, 'Route duration differs from allocation')
    require(r['minutes'] <= plan['policy']['threshold' if request['view'] == 'car' else 'transitThreshold'], 'Route exceeds fixed policy')
    scenario = r.get('scenario', {})
    require(scenario.get('demandId') == request['demandId'] and scenario.get('candidateId') == request['candidateId'], 'Route endpoints differ')
    require(all(scenario.get(k) == v and (number(scenario.get(k)) if number(v) else type(scenario.get(k)) is type(v))
                for k,v in plan['scenario'].items()), 'Route policy differs')
    require(scenario.get('routeMode') == request['view'], 'Route scenario mode differs')
    if request['view'] == 'transit':
        package = plan['identity']['transitPackageId']
        require(r.get('evidence', {}).get('packageId') == package and scenario.get('routingPackageId') == package, 'Route source package differs')
    for key in ('note','demand','candidate'):
        require(type(r.get(key)) is str and bool(r[key].strip()), 'Missing route label: ' + key)
    legs = r.get('legs')
    require(type(legs) is list and legs, 'Missing route geometry')
    count = 0
    for leg in legs:
        require(all(type(leg.get(k)) is str and bool(leg[k].strip()) for k in ('kind','label'))
                and type(leg.get('coordinates')) is list, 'Malformed route leg')
        for point in leg['coordinates']:
            require(type(point) is list and len(point) == 2 and all(number(v) for v in point)
                    and abs(point[0]) <= 180 and abs(point[1]) <= 90, 'Invalid route coordinate')
            count += 1
    require(count >= 2, 'Empty route geometry')
    require(type(r.get('boardings')) is list, 'Missing boarding records')
    for b in r['boardings']:
        require(all(type(b.get(k)) is str and bool(b[k]) for k in ('route','stop','mode')), 'Invalid boarding labels')
        require('waitMinutes' not in b or number(b['waitMinutes']) and b['waitMinutes'] >= 0, 'Invalid waiting time')
    return r


def cache_path(plan, request):
    return CACHE / plan['planId'] / request['view'] / (request['demandId'] + '-' + request['candidateId'] + '.json')


def validated_cache(plan, plan_sha):
    manifest = json.loads((CACHE / 'manifest.json').read_bytes())
    expected = requests_for(plan)
    require(manifest.get('format') == 1 and manifest.get('planId') == plan['planId']
            and manifest.get('sourcePlanSHA256') == plan_sha, 'Stale public route collection')
    require(set(manifest.get('routes', {})) == set(expected), 'Public route collection is incomplete')
    records = {}
    for key, (request, allocation) in expected.items():
        path = cache_path(plan, request)
        entry = manifest['routes'][key]
        require(entry.get('file') == path.relative_to(CACHE).as_posix(), 'Route cache path differs')
        blob = path.read_bytes()
        require(sha(blob) == entry.get('sha256'), 'Route cache checksum mismatch: ' + key)
        validate_record(json.loads(blob), request, allocation, plan, plan_sha)
        records[key] = (blob, entry)
    require(manifest.get('counts') == {v:sum(k.startswith(v + '/') for k in expected) for v in ('car','transit')}, 'Route counts differ')
    return manifest, records
