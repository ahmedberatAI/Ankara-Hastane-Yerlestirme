"""Reproduce the old 291 claim, isolate the walking correction, rerun 91.

--write regenerates transit examples; car resource/cost inputs are unchanged.
Ordinary invocation audits the packaged profiles and routing traces offline.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
from scipy.sparse import load_npz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.main import dataset, Scenario, travel_times, cached_solve, count_bound
from backend.timetable import PROFILES, DEFAULT_PROFILE, load_network, route_one
from backend.feasibility import geographic_bound

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'data/processed'


def write(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')


def certificate(times,floor=80):
    d=dataset()
    return geographic_bound(times[:,:len(d['candidates'])],np.array([v['population'] for v in d['demands']]),
        np.array([v['districtId'] for v in d['demands']]),d['districts'],d['metadata']['provincePopulation'],45,.95,floor/100,time_limit=60)


def validate_network():
    d=dataset();network,access,egress,transfers,direct=load_network()
    official=json.loads((OUT/'ego-official.json').read_text(encoding='utf-8'))
    q=json.loads((OUT/'ego-quality.json').read_text(encoding='utf-8'))
    assert len(official['routes'])==official['directoryCount']==q['officialRouteCount']
    assert not official['errors']
    assert q['routedRouteCount']+len(q['excludedRoutes'])==q['officialRouteCount']
    routes={r['id']:r for r in official['routes']}
    assert {'M1-D','M1-G','M4-D','M4-G','A1-D','A1-G'}<=set(p['route'] for p in network['patterns'])
    assert len(network['stops'])==q['coordinateStopCount']
    assert np.all(access.data<=900) and np.all(egress.data<=900) and np.all(transfers.data<=300) and np.all(direct.data<=7200)
    for i,p in enumerate(network['patterns']):
        assert p['id']==i and len(p['offsets'])==len(p['stops'])==len(p['segmentKeys'])+1
        assert p['offsets'][0]==0 and np.all(np.diff(p['offsets'])>0)
        ids=[network['stops'][j]['id'] for j in p['stops']]
        source_ids=[s['id'] for s in routes[p['route']]['stops']]
        # Respect order, including loops/repeated stops.
        cursor=0
        for code in ids:
            cursor=source_ids.index(code,cursor)+1
        for day,times in p['departures'].items():
            assert times==sorted(set(times))
            assert set(times)<={x['seconds'] for x in routes[p['route']]['departures'][day]}
    for source in official['rawSources']:
        path=ROOT/'data/raw/ego'/source['file']
        if path.exists():assert hashlib.sha256(path.read_bytes()).hexdigest()==source['sha256']
    # An independent, traced single-origin calculation checks all 4,825 destinations.
    # Select populated, rural, walking-only, and transit-accessible origins.
    indices=list(dict.fromkeys([0,len(d['demands'])-1,*np.argsort([-x['population'] for x in d['demands']])[:4],
        int(np.diff(access.indptr).argmax()),int(np.diff(access.indptr).argmin())]))
    checks=[]
    for profile in PROFILES:
        matrix=travel_times(Scenario(mode='transit',transitProfile=profile))
        assert matrix.shape==(len(d['demands']),len(d['candidates'])+len(d['hospitals']))
        assert not np.isnan(matrix).any() and np.all(matrix>=0)
        ridden=False
        for origin in indices:
            expected,paths=route_one(network,access,egress,transfers,direct,int(origin),profile)
            np.testing.assert_allclose(matrix[origin],expected,atol=2e-5,rtol=0)
            for path in paths:
                if not path:continue
                clock=PROFILES[profile]['seconds'];rides=0
                for leg in path:
                    if leg['kind']=='ride':
                        rides+=1
                        assert leg['departureSeconds']>=clock+60-1e-6
                        assert leg['arrivalSeconds']>=leg['departureSeconds']
                        clock=leg['arrivalSeconds'];ridden=True
                    else:clock+=leg['seconds']
                assert rides<=3 and clock<=PROFILES[profile]['seconds']+7200+1e-6
        assert ridden,'No scheduled journey checked'
        checks.append({'profile':profile,'origins':len(indices),'destinationsPerOrigin':matrix.shape[1],'traceAudit':'passed'})
        print('Timetable audited',profile,flush=True)
    return checks


def run(regenerate=False):
    d=dataset()
    if regenerate:
        legacy_path=ROOT/'work/ego-research/legacy/transit-matrix.npz'
        if not legacy_path.exists():
            legacy_path.parent.mkdir(parents=True,exist_ok=True)
            legacy_path.write_bytes(subprocess.check_output(['git','show','d2c5e226484e4aa9af9fe1eec801b18e024c96db:data/processed/transit-matrix.npz'],cwd=ROOT))
        legacy=np.load(legacy_path)['minutes']
        old=certificate(legacy)
        direct=load_npz(OUT/'ego-direct.npz').tocoo();corrected=legacy.copy()
        corrected[direct.row,direct.col]=np.minimum(corrected[direct.row,direct.col],direct.data/60)
        walking=certificate(corrected)
        print('Ablation',old['minimumCountLowerBound'],walking['minimumCountLowerBound'],flush=True)
        report={'date':'2026-10-22','networkVersion':d['metadata']['transitVersion'],
            'legacy':old,'walkingCorrectionOnly':walking,'profiles':[],
            'scope':'Bu test model kapsamı içindir; eksik hizmet ve tahmini zamanlar gerçek Ankara için kesin ihtiyaç sayısı çıkarılmasını engeller.'}
        for profile in PROFILES:
            s=Scenario(mode='transit',threshold=45,hospitalLimit=91,transitProfile=profile)
            result=cached_solve(s.model_dump_json())
            write(OUT/f'example-transit-{profile}-91-result.json',result)
            if profile==DEFAULT_PROFILE:write(OUT/'example-transit-91-result.json',result)
            report['profiles'].append({k:result[k] for k in ('scenario','status','reason','hospitalCount','metrics','capacity','geographicCertificate','transitEvidence') if k in result})
            print('91 test',profile,result['status'],result.get('geographicCertificate'),flush=True)
        report['withoutDistrictFloor']=certificate(travel_times(Scenario(mode='transit')),floor=0)
        s=Scenario(mode='transit',threshold=45)
        write(OUT/'example-transit-result.json',cached_solve(s.model_dump_json()))
        # Add the new optional profile to unchanged car examples, without recomputing
        # their model or claiming a new solve. Their numerical plans remain audited.
        for name in ('example-car-result.json','example-car-91-result.json','example-car-91-university-result.json'):
            path=OUT/name;r=json.loads(path.read_text(encoding='utf-8'));r['scenario']=Scenario(**r['scenario']).model_dump();r['metadata']=d['metadata'];write(path,r)
        write(OUT/'transit-validation.json',report)
    checks=validate_network()
    if regenerate:
        report['routingChecks']=checks;write(OUT/'transit-validation.json',report)
    print('All timetable identities, calendars, paths, boarding times and matrices checked.',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--write',action='store_true');run(parser.parse_args().write)
