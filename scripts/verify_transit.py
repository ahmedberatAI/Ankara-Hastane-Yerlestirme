"""Reproduce the old 291 claim, isolate the walking correction, rerun 91.

--write regenerates transit examples; car resource/cost inputs are unchanged.
Ordinary invocation audits the packaged profiles and routing traces offline.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
from pyproj import Transformer
from scipy.sparse import load_npz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.main import dataset, Scenario, travel_times, cached_solve, count_bound
from backend.timetable import PROFILES, DEFAULT_PROFILE, load_network, route_one
from backend.feasibility import geographic_bound
from scripts.transit_provenance import check_package
from scripts.audit_service_evidence import validate_reviewed_services, validate_evidence_archive
from scripts.audit_bus_projection import validate_bus_projections
from scripts.audit_bus_stop_matching import validate_bus_stop_matching
from scripts.verify_release import (verify_certificate, verify_result_package,
                                    verify_report_records, same_values, summarize, TRANSIT_REPORT_KEYS)

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'data/processed'
LEGACY_COMMIT='d2c5e226484e4aa9af9fe1eec801b18e024c96db'


def write(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')


def certificate(times,floor=80):
    d=dataset()
    return geographic_bound(times[:,:len(d['candidates'])],np.array([v['population'] for v in d['demands']]),
        np.array([v['districtId'] for v in d['demands']]),d['districts'],d['metadata']['provincePopulation'],45,.95,floor/100,time_limit=60)


def ablation_inputs(package_id):
    # Use the immutable Git object, never an unverified scratch cache. CI needs
    # fetch-depth: 0 so historical replay also works in a clean checkout.
    raw = subprocess.check_output(['git','show',LEGACY_COMMIT+':data/processed/transit-matrix.npz'],cwd=ROOT)
    old_data = json.loads(subprocess.check_output(['git','show',LEGACY_COMMIT+':data/processed/dataset.json'],cwd=ROOT))
    data = dataset()
    for field in ('demands','candidates','hospitals','districts'):
        same_values(old_data[field], data[field], 'ablation.fixedInputs.'+field)
    same_values(old_data['metadata']['provincePopulation'],data['metadata']['provincePopulation'],'ablation.provincePopulation')
    legacy = np.load(io.BytesIO(raw))['minutes']
    direct = load_npz(OUT/'ego-direct.npz').tocoo()
    assert legacy.shape == direct.shape
    corrected = legacy.copy()
    corrected[direct.row,direct.col] = np.minimum(corrected[direct.row,direct.col],direct.data/60)
    identities = {'legacyCommit':LEGACY_COMMIT,'legacyMatrixSha256':hashlib.sha256(raw).hexdigest(),
                  'directWalkSha256':hashlib.sha256((OUT/'ego-direct.npz').read_bytes()).hexdigest(),
                  'transitPackageId':package_id}
    return legacy, corrected, identities


def validate_experiment(report, package_id):
    results=[]
    for profile in PROFILES:
        result=json.loads((OUT/f'example-transit-{profile}-91-result.json').read_text(encoding='utf-8'))
        expected=Scenario(mode='transit',threshold=45,hospitalLimit=91,transitProfile=profile)
        same_values(result['scenario'],expected.model_dump(),'experiment.scenario')
        verify_result_package(result,package_id)
        verify_certificate(result['geographicCertificate'],count_bound('transit',45,95,80,1,profile))
        results.append(result)
    verify_report_records(report,results,package_id)
    legacy,corrected,identities=ablation_inputs(package_id)
    same_values(report['ablationInputs'],identities,'ablation.inputs')
    verify_certificate(report['legacy'],certificate(legacy))
    verify_certificate(report['walkingCorrectionOnly'],certificate(corrected))
    verify_certificate(report['withoutDistrictFloor'],certificate(travel_times(Scenario(mode='transit')),floor=0))
    same_values(json.loads((OUT/'example-transit-91-result.json').read_text(encoding='utf-8')),
                next(r for r in results if r['scenario']['transitProfile']==DEFAULT_PROFILE),'defaultProfileAlias')
    assert report['networkVersion']==dataset()['metadata']['transitVersion']


def validate_physical_network(network, official, quality):
    """Audit saved timings independently of the allocation/build functions."""
    projection=Transformer.from_crs('EPSG:4326','EPSG:32636',always_xy=True)
    coordinates=np.array([projection.transform(s['lon'],s['lat']) for s in network['stops']])
    assert np.isfinite(coordinates).all()
    registry={s['id']:i for i,s in enumerate(network['stops'])}
    assert len(registry)==len(network['stops']), 'Duplicate stop identity'
    official_routes={r['id']:r for r in official['routes']}
    accepted={p['route'] for p in network['patterns']}
    excluded={r['route'] for r in quality['excludedRoutes']}
    quarantined={r['route'] for r in quality['quarantinedRoutes']}
    assert len(excluded)==len(quality['excludedRoutes'])
    assert accepted.isdisjoint(excluded), 'Excluded route appears in usable timetable'
    assert accepted.isdisjoint(quarantined), 'Quarantined route appears in usable timetable'
    assert accepted | excluded == set(official_routes), 'Route quality accounting is incomplete'
    assert len(accepted)==quality['routedRouteCount']
    assert quarantined <= excluded and len(quarantined)==quality['quarantinedRouteCount']
    checks={r['route']:r for r in quality['routeGeometryChecks']}
    assert len(checks)==len(quality['routeGeometryChecks'])
    assert accepted <= checks.keys()
    for code, check in checks.items():
        route=official_routes[code]
        known=[s['id'] for s in route['stops'] if s['id'] in registry]
        points=coordinates[[registry[code] for code in known]]
        straight=float(np.linalg.norm(np.diff(points,axis=0),axis=1).sum())
        prefix='drive' if route['mode']=='bus' else ('rail-A' if code.startswith('A') else ('rail-M4' if code.startswith('M4') else 'rail-M123'))
        keys=[f'{prefix}:{a}:{b}' for a,b in zip(known[:-1],known[1:])]
        road=sum(network['segments'][key]['meters'] for key in keys)
        assert np.isfinite(road) and road>=0
        assert abs(check['straightStopChainMeters']-straight)<=1, 'Reported stop-chain length differs'
        assert abs(check['routedMeters']-road)<=1, 'Reported path length differs'
        published=float(route.get('distanceKm') or 0)*1000
        same_values(check['publishedMeters'],published or None,'geometry.publishedMeters')
        # Independent release gate: published model policy is 1.5x straight chain,
        # 2x routed length, or +2 km. Never import the builder's decision function.
        conflict=published>0 and (straight>max(1.5*published,published+2000) or road>max(2*published,published+2000))
        assert (check['status']=='quarantined')==conflict, 'Geometry quarantine contradicts independent consistency gate'
        assert (code in quarantined)==conflict
    for pattern in network['patterns']:
        source=official_routes[pattern['route']]
        assert pattern['mode']==source['mode'], 'Pattern mode differs from its official route'
        speed=90/3.6 if source['mode']=='bus' else 80/3.6
        code=source['id']
        prefix='drive' if source['mode']=='bus' else ('rail-A' if code.startswith('A') else ('rail-M4' if code.startswith('M4') else 'rail-M123'))
        for i,key in enumerate(pattern['segmentKeys']):
            segment=network['segments'][key]
            a,b=pattern['stops'][i:i+2]
            assert key==f'{prefix}:{network["stops"][a]["id"]}:{network["stops"][b]["id"]}', 'Pattern geometry does not join its declared stops'
            straight=float(np.linalg.norm(coordinates[a]-coordinates[b]))
            road=float(segment['meters'])
            assert np.isfinite(road) and road>=0
            required=max(road,straight)/speed+10
            elapsed=pattern['offsets'][i+1]-pattern['offsets'][i]
            assert np.isfinite(elapsed) and elapsed+1e-5>=required, f'{pattern["route"]} {key}: impossible segment time {elapsed:.3f}s < {required:.3f}s'
    for record in quality.get('coordinateAddressAudit',{}).get('conflicts',[]):
        if record['action'].startswith('quarantined'):
            assert record['stopId'] not in registry, 'Quarantined coordinate retained in timetable'


def validate_network():
    d=dataset();network,access,egress,transfers,direct=load_network()
    official=json.loads((OUT/'ego-official.json').read_text(encoding='utf-8'))
    q=json.loads((OUT/'ego-quality.json').read_text(encoding='utf-8'))
    validate_physical_network(network,official,q)
    evidence=json.loads((OUT/'ego-service-evidence.json').read_text(encoding='utf-8'))
    validate_evidence_archive(evidence,ROOT)
    validate_reviewed_services(network,official,q,evidence)
    raw_path=ROOT/'data/raw/ankara-osm.json.gz'
    if raw_path.exists():
        with gzip.open(raw_path,'rt',encoding='utf-8') as stream:raw_osm=json.load(stream)
    else:raw_osm=None
    projection_audit=validate_bus_projections(network,q,raw_osm)
    print('Bus edge projection audit:',json.dumps(projection_audit,ensure_ascii=True),flush=True)
    matching_audit=validate_bus_stop_matching(network,q,official,raw_osm)
    print('Bus stop matching audit:',json.dumps(matching_audit,ensure_ascii=True),flush=True)
    # The UI receives only these compact counts. They must refer to the same
    # independently audited package, never a previous build or missing-as-zero.
    for summary_key, report_key in (
        ('additionalDirectionMatchedStops','additionalDirectionMatchedStops'),
        ('neighborWithheldStops','neighborWithheldStops'),
        ('originalFarProjectedStops','originalFarProjectedStops'),
        ('projectionPolicyVersion','policyVersion')):
        same_values(d['metadata']['transitDataQuality'][summary_key],
                    q['busStopMatching'][report_key],'busStopMatching.summary.'+summary_key)
    del raw_osm
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
    package_id=check_package();d=dataset()
    assert d['metadata']['transitPackageId']==package_id
    if regenerate:
        legacy,corrected,identities=ablation_inputs(package_id)
        old=certificate(legacy)
        walking=certificate(corrected)
        print('Ablation',old['minimumCountLowerBound'],walking['minimumCountLowerBound'],flush=True)
        report={'date':datetime.now(timezone.utc).date().isoformat(),'networkVersion':d['metadata']['transitVersion'],
            'transitPackageId':package_id,'ablationInputs':identities,
            'legacy':old,'walkingCorrectionOnly':walking,'profiles':[],
            'scope':'Bu test model kapsamı içindir; eksik hizmet ve tahmini zamanlar gerçek Ankara için kesin ihtiyaç sayısı çıkarılmasını engeller.'}
        for profile in PROFILES:
            s=Scenario(mode='transit',threshold=45,hospitalLimit=91,transitProfile=profile)
            result=cached_solve(s.model_dump_json())
            write(OUT/f'example-transit-{profile}-91-result.json',result)
            if profile==DEFAULT_PROFILE:write(OUT/'example-transit-91-result.json',result)
            report['profiles'].append(summarize(result,TRANSIT_REPORT_KEYS))
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
    else:
        report=json.loads((OUT/'transit-validation.json').read_text(encoding='utf-8'))
        validate_experiment(report,package_id)
        same_values(report['routingChecks'],checks,'experiment.routingChecks')
    print('Packaged normal-day profiles, identities, paths, boarding times and matrices checked; dated service exceptions and field travel times are not validated.',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--write',action='store_true');run(parser.parse_args().write)
