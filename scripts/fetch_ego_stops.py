"""Cache public EGO Başkentkart stop coordinates, sequentially and politely.

Endpoint and POST fields come from the public map_init.js. No credentials,
private information, device identifiers, authentication or eval are used.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'data/processed'
RAW = ROOT/'data/raw/ego/stops'
WORK = ROOT/'work/ego-research'
URL = 'https://baskentkart.ego.gov.tr/bayiToDo.asp'
MAP = 'https://baskentkart.ego.gov.tr/'


def parse_stop(content, stop_id):
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        # The legacy ASP endpoint also emits Windows Turkish without a charset.
        text = content.decode('cp1254')
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # The public map returns single-quoted object literals. literal_eval
        # accepts only literal data and never executes the server response.
        data = ast.literal_eval(text)
    if not isinstance(data, dict) or data.get('Err'):
        raise ValueError('Malformed or error response')
    if int(data.get('Row', -1)) == 0:
        return None
    if int(data.get('Row', -1)) != 1 or len(data.get('Tbl', [])) != 1:
        raise ValueError('Expected exactly one stop')
    row = data['Tbl'][0]
    if str(row['adi']) != str(stop_id):
        raise ValueError('Stop ID mismatch')
    lat, lon = float(row['px']), float(row['py'])
    if not (35 <= lat <= 43 and 25 <= lon <= 45):
        raise ValueError('Invalid Turkish coordinate range / swapped coordinates')
    return {'id': str(stop_id), 'lat': lat, 'lon': lon, 'address': row.get('yeri', ''),
            'coordinateSource': 'EGO Başkentkart public stop query',
            'sourceUrl': MAP, 'endpoint': URL, 'method': 'POST',
            'request': {'fnc': 'DurakSorgula', 'durakNum': str(stop_id)}}


def write(path, value):
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':'))+'\n', encoding='utf-8', newline='\n')
    temporary.replace(path)


def run(delay=.45, limit=None, retry_unavailable=False, refresh=False):
    RAW.mkdir(parents=True, exist_ok=True); WORK.mkdir(parents=True, exist_ok=True)
    official = json.loads((OUT/'ego-official.json').read_text(encoding='utf-8'))
    ids = {s['id'] for r in official['routes'] for s in r['stops'] if s['id'].isdigit()}
    # Read problematic/missing coordinates first; all catalogued bus stops are
    # still requested. This improves early diagnostic checkpoints, not selection.
    quality_path = OUT/'ego-quality.json'
    quality = json.loads(quality_path.read_text(encoding='utf-8')) if quality_path.exists() else {}
    priority = {'41893', '41821', '41831', '40379', '14396'}
    priority.update(s['id'] for s in quality.get('missingCoordinates', []))
    priority.update(s['stopId'] for s in quality.get('coordinateDisagreements', []))
    ordered = sorted(ids, key=lambda value: (value not in priority, value))
    if limit: ordered = ordered[:limit]
    session = requests.Session()
    session.headers.update({'User-Agent': 'AnkaraHospitalResearch/0.5 (public stop coordinates; cached sequential requests)', 'Referer': MAP})
    session.get(MAP, timeout=(15, 25)).raise_for_status()
    records = []; stops = {}; missing = []; unavailable = []; errors = []
    started = datetime.now(timezone.utc).isoformat()
    last_request = 0.0
    for i, code in enumerate(ordered):
        path = RAW/(code+'.txt')
        provenance_path = RAW/(code+'.source.json')
        needs_fetch = refresh or not path.exists() or (retry_unavailable and not path.read_bytes().strip())
        parsed = None; good = False
        for attempt in range(3):
            try:
                if needs_fetch:
                    time.sleep(max(0, delay-(time.monotonic()-last_request)))
                    last_request = time.monotonic()
                    response = session.post(URL, data={'fnc': 'DurakSorgula', 'durakNum': code}, timeout=(15, 30))
                    if response.status_code == 429:
                        raise RuntimeError('Rate limited; stop and resume later with a longer delay')
                    response.raise_for_status()
                    parsed = parse_stop(response.content, code) if response.content.strip() else None
                    path.write_bytes(response.content)
                    write(provenance_path, {'observedAt': datetime.now(timezone.utc).isoformat(),
                          'sha256': hashlib.sha256(response.content).hexdigest(),
                          'url': URL, 'stopId': code, 'contentType': response.headers.get('Content-Type')})
                else:
                    content = path.read_bytes()
                    parsed = parse_stop(content, code) if content.strip() else None
                good = True; break
            except RuntimeError:
                raise
            except (requests.RequestException, ValueError, SyntaxError, KeyError, TypeError) as exc:
                # A malformed cached payload must not be read repeatedly forever.
                needs_fetch = True
                if attempt == 2:
                    errors.append({'id': code, 'error': str(exc)[:250]})
                    print('Stop query error:', code, str(exc)[:200], flush=True)
                else: time.sleep(1+attempt*2)
        if good:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            provenance = json.loads(provenance_path.read_text(encoding='utf-8')) if provenance_path.exists() else {}
            observed = provenance.get('observedAt') if (provenance.get('sha256') == digest and
                       provenance.get('stopId') == code and provenance.get('url') == URL) else None
            records.append({'file': code+'.txt', 'stopId': code, 'sha256': digest, 'observedAt': observed})
            if parsed:
                stops[code] = {**parsed, 'observedAt': observed, 'rawSha256': digest}
            elif path.read_bytes().strip(): missing.append(code)
            else: unavailable.append(code)
        if (i+1) % 100 == 0 or i+1 == len(ordered):
            progress = {'requested': i+1, 'total': len(ordered), 'coordinates': len(stops), 'notFound': len(missing),
                        'emptyUnavailable': len(unavailable), 'errors': len(errors), 'startedAt': started, 'updatedAt': datetime.now(timezone.utc).isoformat()}
            write(WORK/'official-stop-progress.json', progress)
            print(json.dumps(progress), flush=True)
    result = {'format': 1, 'source': MAP, 'endpoint': URL, 'discoveredIn': MAP+'map_init.js',
              'processedAt': datetime.now(timezone.utc).isoformat(), 'catalogueStopCount': len(ids),
              'requestedCount': len(ordered), 'stops': stops, 'notFound': missing, 'emptyUnavailable': unavailable,
              'errors': errors, 'rawSources': records,
              'scope': 'Observed public stop query; no dated guarantee of alignment with the timetable snapshot.'}
    identities = [{'stopId': r['stopId'], 'sha256': r['sha256']} for r in records]
    result['snapshotId'] = 'ego-stops-'+hashlib.sha256(json.dumps(identities, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    write(OUT/'ego-stop-coordinates.json', result)
    if errors: raise SystemExit('Stop snapshot has errors; inspect before building.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--delay', type=float, default=.45)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--retry-unavailable', action='store_true', help='Re-query cached empty HTTP responses')
    parser.add_argument('--refresh', action='store_true', help='Request a new observation of every selected stop')
    args = parser.parse_args()
    if args.delay < .4: parser.error('Minimum polite request interval is 0.4 seconds')
    run(args.delay, args.limit, args.retry_unavailable, args.refresh)
