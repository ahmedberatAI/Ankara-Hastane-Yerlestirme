"""Independently audit applied event identities and full direction budgets."""
from collections import Counter
import hashlib
import gzip
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup
import numpy as np
from pyproj import Transformer


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
        separators=(',',':'),allow_nan=False).encode()).hexdigest()


def validate_evidence_archive(evidence,root):
    """Verify actual archived HTTP bytes and the right-hand PLANNED table."""
    root=Path(root).resolve();archive_root=root/'data/evidence/ego';soups={}
    for sid,source in evidence['sources'].items():
        path=(root/source['archiveFile']).resolve()
        assert path.is_relative_to(archive_root), 'Evidence archive path outside its directory'
        body=gzip.decompress(path.read_bytes())
        assert hashlib.sha256(body).hexdigest()==source['sha256'], 'Evidence archive source SHA mismatch'
        assert len(body)==source['bytes'], 'Evidence archive byte size mismatch'
        soups[sid]=BeautifulSoup(body,'html.parser',from_encoding='utf-8')
    for e in evidence['events']:
        span_evidence=e.get('spanEvidence')
        assert span_evidence is not None or not any(
            evidence['sources'][sid]['kind']=='accessible_notice' for sid in e['evidenceSourceIds']), 'Accessible span evidence is required'
        if span_evidence is not None:
            sid=span_evidence['sourceId'];source=evidence['sources'][sid]
            assert sid in e['evidenceSourceIds'] and e['routeId'] in source['routeIds']
            assert source['kind']=='accessible_notice'
            heading=soups[sid].select_one('h1').get_text(' ',strip=True)
            assert heading==span_evidence['exactHeading'] and heading.startswith(e['routeId']+' ')
            labels={'weekday':'Hafta İçi:','saturday':'Cumartesi:','sunday':'Pazar:'}
            assert span_evidence['calendarLabel']==labels[e['calendar']]
            rows=[row for row in soups[sid].select('.portlet-body table tr')
                  if row.select_one('th').get_text(' ',strip=True)==labels[e['calendar']]]
            assert len(rows)==1, 'Accessible evidence calendar is absent or ambiguous'
            row_text=' '.join(rows[0].select_one('td').get_text(' ',strip=True).split())
            entries=re.findall(r'(?<!\S)\d{2}:\d{2};[^;]+;\d+;\d+(?=\s|$)',row_text)
            assert ' '.join(entries)==row_text, 'Accessible evidence contains an unparsed entry'
            a,b=e['span']['indicesZeroBasedInclusive'];seconds=e['departureSeconds']
            assert isinstance(seconds,int) and not isinstance(seconds,bool) and seconds%60==0, 'Accessible evidence has minute precision only'
            expected=f'{seconds//3600:02d}:{seconds%3600//60:02d};{e["exactNote"]};{a+1};{b+1}'
            assert entries.count(expected)==1 and span_evidence['exactEntry']==expected, 'Accessible evidence differs in clock/note/span'
            assert span_evidence['indicesOneBasedInclusive']==[a+1,b+1]
            assert span_evidence['tableEffectiveDateConfirmed'] is False
        duration=e['durationEvidence'];sid=duration['sourceId']
        assert sid in e['evidenceSourceIds'] and e['routeId'] in evidence['sources'][sid]['routeIds']
        if duration['type']=='dated_planned_departure_to_closing_interval':
            assert evidence['sources'][sid]['kind']=='dated_notice'
            table=soups[sid].select('table')[duration['sourceTableIndexZeroBased']]
            rows=[[c.get_text(' ',strip=True) for c in row.find_all(['td','th'],recursive=False)]
                  for row in table.select('tr')]
            assert rows[0][-1].startswith(e['routeId']+' ')
            assert rows[1][-1]=='HAFTA İÇİ PLANLANAN TARİFE', 'Wrong calendar/old timetable column'
            cells=rows[duration['plannedRowNumber']+2][5:]
            assert cells==duration['plannedCells'], 'Evidence plan row differs from archived HTML'
            assert canonical_sha(cells)==duration['plannedRowSha256']
            direction=lambda v: ''.join(c for c in v.upper() if c.isalnum())
            assert direction(cells[3])==direction(e['exactNote']), 'Evidence plan belongs to the opposite direction'
        else:
            assert duration['type']=='published_route_duration_field' and evidence['sources'][sid]['kind']=='timetable'
            values=[tr.select('td')[-1].get_text(' ',strip=True) for tr in soups[sid].select('table.hs-kv tr')]
            assert values[0]==e['routeId']
            assert float(values[5].split()[0].replace(',','.'))*60==e['durationBudgetSeconds']
            ids=[tr.select('td')[1].get_text(' ',strip=True) for tr in soups[sid].select('table.route-table tbody tr')]
            assert canonical_sha(ids)==e['stopSequenceSha256']
            assert e['span']['indicesZeroBasedInclusive']==[0,len(ids)-1]
    return {'verifiedSourceArchives':len(soups),'verifiedEventSources':len(evidence['events'])}


def validate_reviewed_services(network,official,quality,evidence):
    rules={e['id']:e for e in evidence['events']}
    assert len(rules)==len(evidence['events'])
    routes={r['id']:r for r in official['routes']}
    raw={s['file']:s['sha256'] for s in official['rawSources']}
    projection=Transformer.from_crs('EPSG:4326','EPSG:32636',always_xy=True)
    xy=np.array([projection.transform(s['lon'],s['lat']) for s in network['stops']])
    applied=[]
    for p in network['patterns']:
        record=p.get('serviceEvidence')
        if record is None:continue
        assert record['currentArrivalTimeConfirmed'] is False and record['isMeasuredTravelTime'] is False
        assert record['eventIds'], 'Reviewed pattern lacks exact event identities'
        expected={day:set() for day in ('weekday','saturday','sunday')}
        for eid in record['eventIds']:
            e=rules[eid];r=routes[e['routeId']]
            assert p['route']==e['routeId']
            for code,sha in e['dependentRouteRawHashes'].items():
                assert raw[f'{code}.html']==sha, 'Applied evidence uses changed source bytes'
            assert canonical_sha([s['id'] for s in r['stops']])==e['stopSequenceSha256']
            identity={k:e[k] for k in ('routeId','calendar','departureSeconds','exactNote')}
            assert canonical_sha(identity)==e['recordSha256']
            assert any(v['seconds']==e['departureSeconds'] and v['note']==e['exactNote']
                       for v in r['departures'][e['calendar']]), 'Reviewed event absent from its calendar'
            a,b=e['span']['indicesZeroBasedInclusive']
            assert [network['stops'][i]['id'] for i in p['stops']]==[s['id'] for s in r['stops'][a:b+1]], 'Reviewed pattern changed direction/stop occurrence'
            expected[e['calendar']].add(e['departureSeconds'])
            assert record['durationBudgetSeconds']==e['durationBudgetSeconds']
            assert e['assumption'] in record['assumptions'] and e['timingConfidence'] in record['timingConfidence']
            for sid in e['evidenceSourceIds']:
                assert evidence['sources'][sid]['url'] in record['sourceUrls']
            applied.append(eid)
        assert all(set(p['departures'][day])==clocks for day,clocks in expected.items()), 'Reviewed pattern invented/moved a departure'
        speed=90/3.6 if p['mode']=='bus' else 80/3.6
        minimum=sum(max(network['segments'][key]['meters'],float(np.linalg.norm(xy[a]-xy[b])))/speed+10
            for key,a,b in zip(p['segmentKeys'],p['stops'][:-1],p['stops'][1:]))
        expected_duration=max(record['durationBudgetSeconds'],minimum)
        assert abs(p['offsets'][-1]-expected_duration)<=1e-4, 'Direction budget sliced, doubled or silently shortened'
    counts=Counter(applied)
    assert all(v==1 for v in counts.values()), 'Reviewed event reused in multiple patterns'
    report=quality['reviewedServiceEvents']
    assert sorted(report['appliedEventIds'])==sorted(applied)
    assert report['appliedCount']==len(applied) and report['definedCount']==len(rules)
    assert set(report['notAppliedEventIds']).isdisjoint(applied)
    assert set(applied)|set(report['notAppliedEventIds'])|{e['id'] for e in report['invalidated']}==set(rules)
    return {'appliedExactEvents':len(applied),'reviewedPatternCount':sum(bool(p.get('serviceEvidence')) for p in network['patterns']),
            'currentArrivalTimesConfirmed':False}
