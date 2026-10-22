"""Independently audit saved results. --write-examples performs fresh solves.

Recomputes resources/cost/area/quotas from raw assignments, not displayed metrics.
All four scenarios, plus actual graph paths and the full-edge 91 certificate.
"""
import argparse
import hashlib
import json
import math
import sys
from datetime import date
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from scipy.sparse.csgraph import dijkstra
from backend.main import app, dataset, health_planning, travel_times, Scenario, site_conflicts, cached_solve, count_bound, graph
from backend.timetable import PROFILES, DEFAULT_PROFILE, journey
from scripts.transit_provenance import check_package

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'data/processed'


BENCHMARK_KEYS = ('scenario', 'status', 'hospitalCount', 'metrics', 'capacity', 'geographicCertificate')
TRANSIT_REPORT_KEYS = (*BENCHMARK_KEYS, 'reason', 'transitEvidence')


def same_values(saved, expected, context='record'):
    """Compare a displayed report to its audited source, allowing rounding only."""
    if isinstance(expected, dict):
        assert isinstance(saved, dict) and saved.keys() == expected.keys(), f'{context}: fields differ'
        for key, value in expected.items():
            same_values(saved[key], value, context + '.' + key)
    elif isinstance(expected, list):
        assert isinstance(saved, list) and len(saved) == len(expected), f'{context}: length differs'
        for i, value in enumerate(expected):
            same_values(saved[i], value, context + f'[{i}]')
    elif isinstance(expected, (float, int)) and not isinstance(expected, bool):
        assert isinstance(saved, (float, int)) and not isinstance(saved, bool), f'{context}: not numeric'
        assert math.isclose(saved, expected, rel_tol=1e-9, abs_tol=1e-6), f'{context}: {saved} != {expected}'
    else:
        assert saved == expected, f'{context}: {saved!r} != {expected!r}'


def verify_certificate(saved, fresh):
    """A new solve must certify every advertised claim, not merely exceed 91."""
    for field in ('fullCandidateCount', 'undominatedCandidateCount', 'scope',
                  'thresholdMinutes', 'coverageTargetPercent', 'districtFloorPercent'):
        same_values(saved[field], fresh[field], 'certificate.' + field)
    assert saved['status'] in ('optimal', 'bounded', 'infeasible')
    if saved['status'] == 'infeasible':
        assert fresh['status'] == 'infeasible', 'Saved geographical infeasibility was not reproduced'
        assert saved['minimumCountLowerBound'] is None and saved['feasibleGeographicCount'] is None
        return
    lower, upper = saved['minimumCountLowerBound'], saved['feasibleGeographicCount']
    assert lower is not None and math.isfinite(lower) and lower >= 0
    assert upper is None or (isinstance(upper, int) and upper >= lower - 1e-6)
    assert fresh['minimumCountLowerBound'] is not None, 'Fresh solve did not certify the saved bound'
    if saved['status'] == 'optimal':
        assert upper is not None and math.isclose(lower, upper, abs_tol=1e-6)
        same_values(fresh['minimumCountLowerBound'], lower, 'certificate.optimalLowerBound')
        same_values(fresh['feasibleGeographicCount'], upper, 'certificate.optimalFeasibleCount')
    else:
        # Time-limited runs need not return identical bounds. A weaker fresh bound
        # cannot recertify a stronger old one: stop, rather than silently approve it.
        assert lower <= fresh['minimumCountLowerBound'] + 1e-6, 'Fresh solve is too weak to recertify the saved lower bound; rerun with a longer limit'
        assert upper is None or upper >= fresh['minimumCountLowerBound'] - 1e-6


def verify_result_package(result, package_id):
    if result['scenario']['mode'] == 'transit':
        assert package_id and result['metadata'].get('transitPackageId') == package_id, 'Result belongs to a different transit package'
        assert result.get('transitEvidence', {}).get('packageId') == package_id, 'Result evidence belongs to a different transit package'
        same_values(result['transitEvidence']['profile'], PROFILES[result['scenario']['transitProfile']], 'result.profile')


def summarize(result, keys):
    return {key: result[key] for key in keys if key in result}


def verify_report_records(report, results, package_id):
    assert report.get('transitPackageId') == package_id, 'Experiment report belongs to a different transit package'
    expected = {r['scenario']['transitProfile']: summarize(r, TRANSIT_REPORT_KEYS)
                for r in results if r['scenario']['mode'] == 'transit' and r['scenario']['hospitalLimit'] == 91}
    profiles = report['profiles']
    assert len(profiles) == len(expected) == len(PROFILES), 'Missing or duplicate profile report'
    assert {r['scenario']['transitProfile'] for r in profiles} == set(expected)
    for record in profiles:
        same_values(record, expected[record['scenario']['transitProfile']], 'experiment.profile')


def verify_benchmark(report, results, transit_report, package_id, quality, sensitivity):
    assert report.get('transitPackageId') == package_id, 'Benchmark belongs to a different transit package'
    same_values(report['cases'], [summarize(r, BENCHMARK_KEYS) for r in results if r['scenario']['hospitalLimit'] == 91], 'benchmark.cases')
    same_values(report.get('sensitivity'), sensitivity, 'benchmark.sensitivity')
    expected = {'legacyLowerBound': transit_report['legacy']['minimumCountLowerBound'],
                'walkingCorrectionLowerBound': transit_report['walkingCorrectionOnly']['minimumCountLowerBound'],
                'withoutDistrictFloorLowerBound': transit_report['withoutDistrictFloor']['minimumCountLowerBound'],
                'officialRoutes': quality['officialRouteCount'], 'modeledRoutes': quality['routedRouteCount']}
    for field, value in expected.items():
        same_values(report['transitAudit'][field], value, 'benchmark.transitAudit.' + field)


def audit(result):
    data=dataset(); p=health_planning(); s=Scenario(**result['scenario'])
    assert result['capacity']['planningVersion']==p['version']
    n=len(data['demands']); pop=np.array([d['population'] for d in data['demands']])
    times=travel_times(s); indices=result['selectedIndices']; selected=set(indices)
    assert len(selected)==result['hospitalCount']
    assert s.hospitalLimit is None or len(selected)<=s.hospitalLimit
    assert not any(a in selected and b in selected for a,b in site_conflicts())
    assigned=np.zeros(n); loads={j:0. for j in selected}; travel=0.; weighted=[]
    for i,a in enumerate(result['assignments']):
        assert a['demandId']==data['demands'][i]['id']
        for part in a['allocations']:
            j,v=part['candidateIndex'],part['population']
            assert j in selected and v>=0
            assert part['candidateId']==data['candidates'][j]['id']
            assert abs(part['minutes']-times[i,j])<1e-5
            assert times[i,j]<=s.threshold+1e-6
            assert abs(part['fraction']-v/pop[i])<1e-7
            assigned[i]+=v; loads[j]+=v; travel+=v*times[i,j]; weighted.append((times[i,j],v))
        assert assigned[i]<=pop[i]+.001
        assert abs(a['servedFraction']-assigned[i]/pop[i])<1e-6
        assert a['covered']==(assigned[i]>=pop[i]-1e-4)
        assert a['candidateId']==(a['allocations'][0]['candidateId'] if a['allocations'] else None)
    covered=assigned.sum(); total=data['metadata']['provincePopulation']
    assert covered>=total*s.coverageTarget/100-.001
    assert abs(result['metrics']['coveredPopulation']-covered)<.001
    assert abs(result['metrics']['meanMinutes']-travel/covered)<1e-6
    for d in result['districts']:
        district_pop=assigned[np.array([x['districtId']==d['id'] for x in data['demands']])].sum()
        assert district_pop>=d['population']*s.districtFloor/100-.001
        assert abs(d['coveragePercent']-district_pop/d['population']*100)<1e-6
    eco=p['economics']; design=p['design']; rates=p['rates']; om=s.operatingCostMultiplier
    crf=eco['realDiscountRate']/(1-(1+eco['realDiscountRate'])**-eco['horizonYears'])
    beds=doctors=0;capex=opex=0
    for c in result['selected']:
        j=c['candidateIndex']; base=data['candidates'][j]
        assert c['id']==base['id'] and c['lon']==base['lon'] and c['lat']==base['lat']
        t=next(t for t in p['templates'] if t['id']==c['templateId'])
        assert c['beds']==t['beds'] and int(c['doctors'])==c['doctors']>=design['minimumDoctorsPerSite']
        area=t['grossAreaM2']+design['areaPerDoctorM2']*c['doctors']
        assert area<=math.pi*base['footprintRadiusMeters']**2*design['maxFloors']+.01
        assert c['grossAreaM2']==area
        contacts=loads[j]*rates['contactsPerResident']*s.demandMultiplier
        bed_days=loads[j]*rates['bedDaysPerResident']*s.demandMultiplier
        assert contacts<=c['doctors']*s.contactsPerDoctor+.1
        assert bed_days<=t['beds']*365*s.bedOccupancy/100+.1
        assert abs(c['annualContacts']-contacts)<.1 and abs(c['annualBedDays']-bed_days)<.1
        cc=area*eco['buildingUnitCostTRY']
        oc=om*(eco['annualFixedSiteCostTRY']+t['beds']*eco['annualBedSupportCostTRY']+c['doctors']*eco['annualDoctorCostTRY']+contacts*eco['costPerContactTRY'])
        assert abs(cc-c['constructionCostTRY'])<1 and abs(oc-c['annualOperatingCostTRY'])<1
        assert abs(cc*crf+oc-c['annualEquivalentCostTRY'])<1
        capex+=cc;opex+=oc;beds+=c['beds'];doctors+=c['doctors']
    cap=result['capacity'];annual=capex*crf+opex
    assert cap['totalBeds']==beds and cap['totalDoctors']==doctors
    for key,calc in [('constructionCostTRY',capex),('annualOperatingCostTRY',opex),('annualEquivalentCostTRY',annual),('lifecyclePresentCostTRY',annual/crf)]:
        assert abs(cap[key]-calc)<10
    assert annual<=cap['budgetLimitTRY']+100
    assert abs(cap['budgetLimitTRY']-cap['referenceCostTRY']*(1+s.costTolerance/100))<10
    assert result['lowerBound']<=cap['referenceCostTRY']+100
    assert result['metrics']['meanMinutes']<=cap['referenceMeanMinutes']+1e-6
    weighted.append((np.inf,total-covered));cumulative=0
    for minutes,w in sorted(weighted):
        cumulative+=w
        if cumulative>=.9*total-1e-7:
            assert (not np.isfinite(minutes) and result['metrics']['p90Minutes'] is None) or abs(result['metrics']['p90Minutes']-minutes)<1e-5
            break
    return {'mode':s.mode,'hospitalLimit':s.hospitalLimit,'status':result['status'],
        'transitProfile':s.transitProfile if s.mode=='transit' else None,
        'hospitalCount':len(selected),'totalBeds':beds,'totalDoctors':doctors,
        'coveragePercent':float(covered/total*100),'minimumDistrictCoveragePercent':min(d['coveragePercent'] for d in result['districts']),
        'meanMinutes':float(travel/covered),'annualEquivalentCostTRY':annual,'annualOperatingCostTRY':opex,
        'constructionCostTRY':capex,'costStageGap':cap['costStageGap'],'travelStageGap':cap['travelStageGap']}


def run(write_examples=False,write_report=False):
    package_id=check_package()
    data=dataset();client=TestClient(app);report=[];benchmark=[];audited_results=[]
    assert data['metadata']['transitPackageId'] == package_id
    assert client.get('/api/data').status_code==200
    cases=[('car',30,None,'car',DEFAULT_PROFILE),('transit',45,None,'transit',DEFAULT_PROFILE),('car',30,91,'car-91',DEFAULT_PROFILE)]
    cases += [('transit',45,91,f'transit-{profile}-91',profile) for profile in PROFILES]
    for mode,threshold,limit,label,profile in cases:
        s=Scenario(mode=mode,threshold=threshold,hospitalLimit=limit,transitProfile=profile)
        path=OUT/f'example-{label}-result.json'
        if write_examples:
            result=cached_solve(s.model_dump_json())
            path.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
            if mode=='transit' and limit==91 and profile==DEFAULT_PROFILE:
                (OUT/'example-transit-91-result.json').write_bytes(path.read_bytes())
        result=json.loads(path.read_text(encoding='utf-8'))
        assert result['scenario']==s.model_dump()
        verify_result_package(result, package_id)
        if result['status']=='infeasible':
            certificate=count_bound(mode,threshold,95,80,1,profile)
            verify_certificate(result['geographicCertificate'], certificate)
            assert limit is not None and (certificate['status']=='infeasible' or certificate['minimumCountLowerBound']>limit)
            assert certificate['fullCandidateCount']==len(data['candidates'])
            report.append({'mode':mode,'hospitalLimit':limit,'transitProfile':profile,'status':'infeasible','geographicCertificate':result['geographicCertificate']})
        else:
            assert result['status']=='feasible',result.get('reason')
            assert result['capacity']['planningVersion']==health_planning()['version']
            report.append(audit(result))
            # A routed large plot is checked against the stored matrix too.
            candidates={c['candidateIndex']:c for c in result['selected']}
            pairs=[(a,x) for a in result['assignments'] for x in a['allocations'] if candidates[x['candidateIndex']]['footprintRadiusMeters']>45]
            found=False
            for a,x in sorted(pairs,key=lambda q:-q[1]['minutes'])[:40]:
                response=client.post('/api/route',json={**s.model_dump(),'demandId':a['demandId'],'candidateId':x['candidateId']})
                assert response.status_code==200
                route=response.json();assert abs(route['minutes']-x['minutes'])<.001
                assert any(len(leg['coordinates'])>1 for leg in route['legs'])
                if mode=='car' or route['boardings']:
                    di=next(i for i,d in enumerate(data['demands']) if d['id']==a['demandId'])
                    ci=x['candidateIndex']; demand=data['demands'][di]; candidate=data['candidates'][ci]
                    if mode=='car':
                        minutes=dijkstra(graph('drive'),indices=demand['node'])[candidate['node']]/60
                        minutes=minutes*s.trafficFactor+(demand['snapMeters']+candidate['accessMeters'])/75+3
                    else:
                        minutes,_=journey(di,ci,profile)
                    assert abs(minutes-x['minutes'])<.001,'Matrix does not match graph shortest path'
                    found=True;break
            assert found,'No large-plot vehicle route verified'
        if limit==91:
            if result['status'] != 'infeasible':
                verify_certificate(result['geographicCertificate'], count_bound(mode,threshold,95,80,1,profile))
            benchmark.append(summarize(result, BENCHMARK_KEYS))
        audited_results.append(result)
        print('Audited',label,flush=True)
    sensitivity_path=OUT/'example-car-91-university-result.json'
    sensitivity=None
    if write_examples:
        sr=cached_solve(Scenario(hospitalLimit=91,contactsPerDoctor=835).model_dump_json())
        sensitivity_path.write_text(json.dumps(sr,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    if sensitivity_path.exists():
        sr=json.loads(sensitivity_path.read_text(encoding='utf-8'))
        assert sr['scenario']['contactsPerDoctor']==835 and sr['scenario']['hospitalLimit']==91
        sensitivity={'scenario':sr['scenario'],'summary':audit(sr)}
    transit_report=json.loads((OUT/'transit-validation.json').read_text(encoding='utf-8'))
    if write_examples:
        assert transit_report.get('transitPackageId') == package_id
        transit_report['profiles'] = [summarize(r, TRANSIT_REPORT_KEYS) for r in audited_results
                                      if r['scenario']['mode'] == 'transit' and r['scenario']['hospitalLimit'] == 91]
        (OUT/'transit-validation.json').write_text(json.dumps(transit_report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    verify_report_records(transit_report, audited_results, package_id)
    quality=data['metadata']['transitDataQuality']
    if write_examples or write_report:
        (OUT/'sensitivity-results.json').write_text(json.dumps(sensitivity,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
        (OUT/'benchmark-91.json').write_text(json.dumps({'date':date.today().isoformat(),'planningVersion':health_planning()['version'],'transitPackageId':package_id,
            'note':'91 kullanıcı karşılaştırma sınırıdır; resmî 2024 envanteri 85. EGO: resmi kalkışlar, tahmini ara durak süreleri ve kısmi hizmet kapsamı; gerçek kent için kesin ihtiyaç sayısı değildir.',
            'cases':benchmark,'sensitivity':sensitivity,'transitAudit':{
                'legacyLowerBound':transit_report['legacy']['minimumCountLowerBound'],
                'walkingCorrectionLowerBound':transit_report['walkingCorrectionOnly']['minimumCountLowerBound'],
                'withoutDistrictFloorLowerBound':transit_report['withoutDistrictFloor']['minimumCountLowerBound'],
                'officialRoutes':quality['officialRouteCount'],'modeledRoutes':quality['routedRouteCount'],
                'note':f"{quality['routedRouteCount']}/{quality['officialRouteCount']} yön/varyant modele bağlandı; eksik seferler erişimi olduğundan düşük gösterebilir."}},ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
        (OUT/'validation-results.json').write_text(json.dumps({'date':date.today().isoformat(),'transitPackageId':package_id,'cases':report},ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    else:
        verify_benchmark(json.loads((OUT/'benchmark-91.json').read_text(encoding='utf-8')), audited_results, transit_report, package_id, quality, sensitivity)
        saved_validation=json.loads((OUT/'validation-results.json').read_text(encoding='utf-8'))
        assert saved_validation.get('transitPackageId') == package_id
        same_values(saved_validation['cases'], report, 'validation.cases')
        same_values(json.loads((OUT/'sensitivity-results.json').read_text(encoding='utf-8')), sensitivity, 'sensitivity.summary')
        from scripts.manifest import check
        check()
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--write-examples',action='store_true');parser.add_argument('--write-report',action='store_true')
    args=parser.parse_args();run(args.write_examples,args.write_report)
