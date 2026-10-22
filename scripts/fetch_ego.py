"""Snapshot EGO's public route directory and three day-type timetables.

No credentials, live vehicle positions or personal data. Cached, sequential,
rate-limited requests. Preserve notes: a departure is NOT necessarily a trip
starting at the first listed stop. Raw responses stay outside git.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time

from bs4 import BeautifulSoup
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/ego'
OUT = ROOT / 'data/processed'
URL = 'https://www.ego.gov.tr/hareketsaatleri'
COMMUNITY_URL='https://dl.dropboxusercontent.com/scl/fi/d7u3d00gd85w2qbzedze6/ankara.zip?rlkey=4x8oz2sby5vvqgf1iuaeit70l'
DAYS = ('weekday', 'saturday', 'sunday')


def fetch_source(session, raw, name, params=None, refresh=False):
    """Preserve observation time on a cache hit; file mtime is not evidence."""
    path = raw / name
    provenance_path = raw / (name + '.source.json')
    url = URL + ('?hat_no=' + params['hat_no'] if params else '')
    observed_at = None
    downloaded = refresh or not path.exists()
    if downloaded:
        time.sleep(.45)
        response = session.get(URL, params=params, timeout=(15, 45))
        response.raise_for_status()
        content = response.content
        observed_at = datetime.now(timezone.utc).isoformat()
        path.write_bytes(content)
    else:
        content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if not downloaded and provenance_path.exists():
        prior = json.loads(provenance_path.read_text(encoding='utf-8'))
        if prior.get('sha256') == digest and prior.get('url') == url:
            observed_at = prior.get('observedAt')
    record = {'file': name, 'url': url, 'sha256': digest, 'bytes': len(content),
              'observedAt': observed_at,
              'observationTimeStatus': 'recorded_http_fetch' if observed_at else 'unknown_legacy_cache',
              'downloadedThisRun': downloaded}
    # Persist only a successful HTTP observation; an old cache stays explicitly unknown.
    if downloaded:
        provenance_path.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return content, record


def snapshot_metadata(records):
    identities = [{key: r[key] for key in ('file', 'url', 'sha256')} for r in sorted(records, key=lambda r: r['file'])]
    digest = hashlib.sha256(json.dumps(identities, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    observed = sorted(r['observedAt'] for r in records if r.get('observedAt'))
    unknown = len(records) - len(observed)
    return {'version': 'ego-web-sha256-' + digest, 'sourceSnapshotId': digest,
            'processedAt': datetime.now(timezone.utc).isoformat(),
            # Compatibility field: never substitute today's cache-processing time.
            'retrievedAt': observed[-1] if observed and not unknown else None,
            'observationPeriod': {'firstFetchedAt': observed[0] if observed else None,
                                  'lastFetchedAt': observed[-1] if observed else None,
                                  'unknownSourceCount': unknown}}


def parse_route(content, code):
    soup = BeautifulSoup(content, 'html.parser', from_encoding='utf-8' if isinstance(content, bytes) else None)
    kv = soup.select_one('table.hs-kv')
    if kv is None:
        raise ValueError(f'{code}: route details missing')
    values = [tr.select('td')[-1].get_text(' ', strip=True) for tr in kv.select('tr')]
    if values[0] != code:
        raise ValueError(f'{code}: wrong route {values[0]}')
    departures = {}
    cells = soup.select('table.hs-table td.hs-times')
    if len(cells) != 3:
        raise ValueError(f'{code}: expected three service day columns')
    for day, cell in zip(DAYS, cells):
        entries = []
        # A note can itself repeat the time; split only at HTML line breaks.
        for line in cell.get_text('\n', strip=True).splitlines():
            m = re.match(r'^(\d{2}):(\d{2})\s*(.*)$', line.strip())
            if m:
                hour, minute = int(m[1]), int(m[2])
                if hour > 29 or minute > 59:
                    raise ValueError(f'{code}: invalid clock time')
                entries.append({'seconds': hour*3600+minute*60, 'note': m[3].strip()})
        departures[day] = entries
    stops = []
    for tr in soup.select('table.route-table tbody tr'):
        cells = [td.get_text(' ', strip=True) for td in tr.select('td')]
        if len(cells) == 4:
            stops.append({'sequence': int(cells[0]), 'id': cells[1], 'name': cells[2], 'address': cells[3]})
    if [s['sequence'] for s in stops] != list(range(1,len(stops)+1)):
        raise ValueError(f'{code}: noncontiguous stop sequence')
    number = lambda s: float(re.search(r'[\d.,]+', s)[0].replace(',', '.')) if re.search(r'\d',s) else None
    return {'id':code,'name':values[1], 'origin':values[2], 'destination':values[3],
            'distanceKm':number(values[4]),'durationMinutes':number(values[5]),
            'mode':'bus' if code[0].isdigit() else ('subway' if code.startswith('M') else 'light_rail'),
            'departures':departures,'stops':stops,
            'serviceNote':soup.select_one('.hs-note').get_text(' ',strip=True) if soup.select_one('.hs-note') else '',
            'url':URL+'?hat_no='+code}


def run(refresh=False):
    RAW.mkdir(parents=True,exist_ok=True)
    session=requests.Session()
    session.headers['User-Agent']='AnkaraHospitalResearch/0.4 (public timetable research; cached requests)'
    records=[]
    def fetch(name,params=None):
        content, record = fetch_source(session, RAW, name, params, refresh)
        records.append(record)
        return content
    content=fetch('directory.html')
    soup=BeautifulSoup(content,'html.parser',from_encoding='utf-8')
    codes=[o['value'] for o in soup.select('select[name^="hat_no"] option') if o['value']!='0']
    assert len(codes)==len(set(codes)) and len(codes)>400
    routes=[];errors=[]
    for i,code in enumerate(codes):
        try:
            routes.append(parse_route(fetch(code+'.html',{'hat_no':code}),code))
        except (ValueError,requests.RequestException) as exc:
            errors.append({'route':code,'error':str(exc)})
        if i%40==0:print(f'EGO snapshot {i+1}/{len(codes)}; errors={len(errors)}',flush=True)
    result={**snapshot_metadata(records),
            'directoryCount':len(codes),'routes':routes,'errors':errors,'rawSources':records,
            'calendarScope':'Normal hafta içi / cumartesi / pazar; tarihli istisna takvimi ve tatil doğrulaması yok.',
            'sourceScope':'Resmi hat kimliği, sıralı duraklar, kalkış saatleri ve hat toplam süresi. Ara durak varış saatleri yayımlanmıyor.'}
    (OUT/'ego-official.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'routes':len(routes),'stops':len({s['id'] for r in routes for s in r['stops']}),'errors':errors},ensure_ascii=False),flush=True)
    if errors:raise SystemExit('Incomplete snapshot: inspect errors before building')
    community=RAW/'community-ankara.zip'
    if not community.exists():
        response=session.get(COMMUNITY_URL,timeout=(20,90));response.raise_for_status()
        community.write_bytes(response.content)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--refresh',action='store_true')
    run(parser.parse_args().refresh)
