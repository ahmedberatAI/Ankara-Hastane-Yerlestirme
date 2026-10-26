"""One light, keyless Transitous research query. Never a production matrix feed.

Usage policy: https://transitous.org/api/
No batches, automatic retries, credentials or paid fallback. Save raw evidence
under work/. Ankara's catalogued community feed has unresolved quality issues.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time

import requests

ENDPOINT = 'https://api.transitous.org/api/v6/plan'
LOCAL_ENDPOINT = 'http://127.0.0.1:8088/api/v6/plan'
USER_AGENT = ('AnkaraHospitalResearch/0.1 '
              '(+https://github.com/ahmedberatAI/Ankara-Hastane-Yerlestirme)')
ALLOWED_MODES = {'WALK', 'BUS', 'TRAM', 'SUBWAY', 'SUBURBAN', 'REGIONAL_RAIL',
                 'HIGH_SPEED_RAIL', 'LONG_DISTANCE', 'COACH', 'FERRY', 'RAIL'}


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('Explicit timezone required, e.g. 2026-10-27T08:05:00+03:00')
    return result


def coordinate(value):
    parts = value.split(',')
    if len(parts) != 2:
        raise ValueError('Use latitude,longitude')
    lat, lon = map(float, parts)
    if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('Invalid coordinate')
    return f'{lat:.7f},{lon:.7f}'


def parameters(origin, destination, departure):
    return dict(fromPlace=coordinate(origin), toPlace=coordinate(destination),
                time=timestamp(departure).astimezone(timezone.utc).isoformat(),
                arriveBy='false', timetableView='false',
                preTransitModes='WALK', postTransitModes='WALK', directModes='WALK',
                maxPreTransitTime=2700, maxPostTransitTime=2700, maxDirectTime=2700)


def summarize(payload, departure, http_status=200, local=False):
    requested = timestamp(departure)
    base = dict(provider='Local MOTIS' if local else 'Transitous / MOTIS',
                costChannel='local_no_per_query_api_fee' if local else 'keyless_free_public_service',
                datasetScenario='historical_community_GTFS',
                requestDeparture=requested.isoformat(), productionModelInput=False,
                currentOfficialAnkaraTimetableVerified=False,
                scope='Provider estimates only; no complete coverage or real-world accuracy proof.')
    if http_status != 200:
        return dict(base, status='unknown_provider_error', httpStatus=http_status, journeys=[])
    if not isinstance(payload, dict) or not all(isinstance(payload.get(k), list) for k in ('itineraries', 'direct')):
        raise ValueError('Unexpected provider response; never interpret it as no service')
    journeys = []
    for group in ('itineraries', 'direct'):
        for item in payload[group]:
            start, end = timestamp(item['startTime']), timestamp(item['endTime'])
            duration = item['duration']
            legs = item['legs']
            if (type(duration) not in (int, float) or not math.isfinite(duration)
                    or duration < 0 or start < requested or end < start
                    or abs((end-start).total_seconds()-duration) > 1
                    or not isinstance(legs, list) or not legs):
                raise ValueError('Inconsistent journey timeline')
            prior = start
            normalized = []
            for leg in legs:
                a, b = timestamp(leg['startTime']), timestamp(leg['endTime'])
                if leg['mode'] not in ALLOWED_MODES or a < prior or b < a or b > end:
                    raise ValueError('Unsupported mode or inconsistent leg timeline')
                prior = b
                normalized.append(dict(mode=leg['mode'], line=leg.get('routeShortName'),
                    startTime=a.isoformat(), endTime=b.isoformat(),
                    realtime=leg.get('realTime') is True, source=leg.get('source')))
            if timestamp(legs[0]['startTime']) != start or prior != end:
                raise ValueError('Legs do not cover the advertised journey timeline')
            elapsed = (end-requested).total_seconds()/60
            journeys.append(dict(providerJourneyMinutes=duration/60,
                elapsedFromRequestedDepartureMinutes=elapsed,
                initialWaitMinutes=(start-requested).total_seconds()/60,
                within45MinuteProviderEstimate=elapsed <= 45,
                startTime=start.isoformat(), endTime=end.isoformat(),
                transitLegCount=sum(x['mode'] != 'WALK' for x in normalized), legs=normalized))
    journeys.sort(key=lambda x: (x['elapsedFromRequestedDepartureMinutes'], x['transitLegCount']))
    return dict(base, status='provider_journeys_returned' if journeys else 'unknown_no_journey_returned',
                journeys=journeys)


def probe(origin, destination, departure, output, local=False):
    params = parameters(origin, destination, departure)
    folder = Path(output).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    began = time.monotonic()
    endpoint = LOCAL_ENDPOINT if local else ENDPOINT
    record = dict(endpoint=endpoint, parameters=params,
                  observedAt=datetime.now(timezone.utc).isoformat(), userAgent=USER_AGENT,
                  paidRequests=0, automaticRetries=0)
    try:
        response = requests.get(endpoint, params=params, headers={'User-Agent': USER_AGENT},
                                timeout=(10, 40), allow_redirects=False)
        raw = response.content
        (folder/'response.raw').write_bytes(raw)
        record.update(httpStatus=response.status_code, url=response.url,
                      bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        payload = response.json() if response.status_code == 200 else None
        result = summarize(payload, departure, response.status_code, local)
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        record['error'] = f'{type(error).__name__}: {error}'
        result = dict(status='unknown_fetch_or_validation_error', journeys=[],
                      productionModelInput=False)
    record['elapsedSeconds'] = time.monotonic()-began
    for name, value in [('source.json', record), ('summary.json', result)]:
        (folder/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n',
                                encoding='utf-8', newline='\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', required=True, help='latitude,longitude')
    parser.add_argument('--destination', required=True, help='latitude,longitude')
    parser.add_argument('--departure', required=True, help='ISO timestamp with explicit timezone')
    parser.add_argument('--out', required=True, help='New evidence directory, normally inside work/')
    parser.add_argument('--local', action='store_true', help='Use the local MOTIS service on port 8088')
    args = parser.parse_args()
    result = probe(args.origin, args.destination, args.departure, args.out, args.local)
    print(json.dumps(result, ensure_ascii=False, indent=2))
