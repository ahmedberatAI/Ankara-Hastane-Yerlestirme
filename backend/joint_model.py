"""Explicit shared-location, integer-resource model with four separate flows.

Pure formulation and plan/vector validation: no optimizer or monkeypatch.
Annual demand is exact and identical in each profile, so materials count once.
"""
import math
from time import monotonic
import numpy as np
from scipy.sparse import coo_matrix

AREA_TOL=.001

class ModelInfeasible(ValueError):
    """Only the supplied candidate/profile model fails an elementary check."""


def positive(value,name):
    if isinstance(value,(bool,np.bool_)) or not isinstance(value,(int,float,np.integer,np.floating)) or not math.isfinite(value) or value<=0:
        raise ValueError('Invalid '+name)
    return float(value)


def finite_nonnegative(value,name):
    if isinstance(value,(bool,np.bool_)) or not isinstance(value,(int,float,np.integer,np.floating)) or not math.isfinite(value) or value<0:
        raise ValueError('Invalid '+name)
    return float(value)


def validate_vector(x, integer, lb, ub, A, lo, hi):
    x=np.asarray(x,dtype=float)
    if x.shape!=lb.shape or np.any(~np.isfinite(x)):
        raise ValueError('Warm-start vector shape/finiteness invalid')
    activity=A@x
    metrics={
        'maximumVariableViolation':float(max(np.maximum(lb-x,0).max(initial=0),np.maximum(x-ub,0).max(initial=0))),
        'maximumRowViolation':float(max(np.maximum(lo-activity,0).max(initial=0),np.maximum(activity-hi,0).max(initial=0))),
        'maximumIntegralityViolation':float(np.abs(x[integer!=0]-np.rint(x[integer!=0])).max(initial=0))}
    if metrics['maximumVariableViolation']>1e-8 or metrics['maximumRowViolation']>1e-7 or metrics['maximumIntegralityViolation']>1e-8:
        raise ValueError('Warm-start fails original constraints: '+str(metrics))
    return metrics


def reconstruct_plan(seed, profile_times, candidates, planning, scenario, variable_count):
    def integer(value,name,minimum=0):
        if isinstance(value,(bool,np.bool_)) or not isinstance(value,(int,np.integer)) or value<minimum:
            raise ValueError('Invalid seed integer '+name)
        return int(value)
    def finite(value,name,positive=False):
        if isinstance(value,(bool,np.bool_)) or not isinstance(value,(int,float,np.integer,np.floating)):
            raise ValueError('Invalid seed numeric '+name)
        try:value=float(value)
        except (OverflowError,ValueError):raise ValueError('Invalid seed numeric '+name) from None
        if not math.isfinite(value) or (value<=0 if positive else value<0):
            raise ValueError('Invalid seed finite '+name)
        return value
    if not isinstance(seed,dict) or seed.get('status','feasible')!='feasible' or seed.get('incumbentValidated',True) is not True:
        raise ValueError('Only a validated feasible seed may be supplied')
    count=integer(seed.get('hospitalCount'),'hospital count')
    if not isinstance(seed.get('selected'),list) or not all(isinstance(s,dict) for s in seed['selected']):
        raise ValueError('Invalid seed site records')
    if not isinstance(seed.get('profiles'),list) or not all(isinstance(p,dict) and isinstance(p.get('profile'),str) for p in seed['profiles']):
        raise ValueError('Invalid seed profile records')
    ids=[c['candidateIndex'] for c in candidates];local={j:k for k,j in enumerate(ids)}
    d=planning['design'];area=np.array([t['grossAreaM2'] for t in planning['templates']])
    radii=np.array([s['footprintRadiusMeters'] for s in candidates]);available=np.pi*radii**2*d['maxFloors']
    xs,ts=np.where(area[None,:]+d['minimumDoctorsPerSite']*d['areaPerDoctorM2']<=available[:,None]+AREA_TOL)
    type_by_id={t['id']:k for k,t in enumerate(planning['templates'])};index={(int(j),int(t)):k for k,(j,t) in enumerate(zip(xs,ts))}
    nx=len(xs);nf=nx+len(candidates);v=np.zeros(variable_count);selected=set()
    for site in seed['selected']:
        j=integer(site.get('candidateIndex'),'site candidate index');template=site.get('templateId')
        docs=integer(site.get('doctors'),'physicians',minimum=1);beds=integer(site.get('beds'),'beds',minimum=1)
        radius=finite(site.get('footprintRadiusMeters'),'footprint radius',positive=True)
        gross=finite(site.get('grossAreaM2'),'gross area',positive=True)
        if j not in local or j in selected or not isinstance(template,str) or template not in type_by_id:
            raise ValueError('Seed has missing/duplicate site or unknown template')
        k=local[j];t=type_by_id[template];source=candidates[k]
        if (k,t) not in index:
            raise ValueError('Invalid seed integer resources')
        if type(site.get('id')) is not type(source.get('id')) or site.get('id')!=source.get('id') or beds!=planning['templates'][t]['beds']:
            raise ValueError('Seed site/template identity mismatch')
        if abs(radius-source['footprintRadiusMeters'])>1e-8:
            raise ValueError('Seed building footprint changed')
        if abs(gross-area[t]-docs*d['areaPerDoctorM2'])>AREA_TOL:
            raise ValueError('Seed gross area inconsistent')
        selected.add(j);v[index[k,t]]=1;v[nx+k]=docs
    if len(selected)!=count:
        raise ValueError('Seed hospital count inconsistent')
    if [p['profile'] for p in seed['profiles']]!=list(profile_times):
        raise ValueError('Seed profile identities/order mismatch')
    offset=nf
    for profile in seed['profiles']:
        if not isinstance(profile.get('allocations'),list) or not all(isinstance(a,dict) for a in profile['allocations']):
            raise ValueError('Invalid seed allocation records')
        t=np.asarray(profile_times[profile['profile']]);oi,sj=np.where(np.isfinite(t)&(t<=scenario['threshold']))
        edges={(int(i),int(ids[j])):offset+k for k,(i,j) in enumerate(zip(oi,sj))};seen=set()
        for assignment in profile['allocations']:
            i=integer(assignment.get('demandIndex'),'demand index');j=integer(assignment.get('candidateIndex'),'allocation candidate index')
            f=finite(assignment.get('population'),'assigned population',positive=True)
            minutes=finite(assignment.get('minutes'),'travel minutes');key=(i,j)
            if key not in edges or key in seen or j not in selected:
                raise ValueError('Seed contains closed/missing/duplicate edge or invalid flow')
            if abs(minutes-float(t[i,local[j]]))>1e-6:
                raise ValueError('Seed travel value differs from current matrix')
            seen.add(key);v[edges[key]]=f/1000
        offset+=len(oi)
    if offset!=variable_count:raise ValueError('Original model variable layout mismatch')
    return v



class JointProblem:
    """Immutable-by-convention complete sparse formulation and identity maps.

    Rows/column order intentionally match the independently reviewed original
    formulation. Candidate IDs can be sparse; every flow retains its profile.
    """
    def __init__(self,**fields):
        self.__dict__.update(fields)

    def cost(self,v):return float(self.c@v*self.cost_scale+self.material)

    def resources(self,v):
        opened=np.bincount(self.xsite,weights=v[:self.nx],minlength=self.m)>.5
        beds=np.bincount(self.xsite,weights=self.beds[self.xtype]*v[:self.nx],minlength=self.m)
        return opened,beds,v[self.nx:self.nf]

    def validate(self,v):
        residuals=validate_vector(v,*self.model[1:]);opened,beds,docs=self.resources(v)
        if np.any(v[self.nf:]<0) or np.any(docs[~opened]!=0):raise ValueError('Negative flow or staff at closed site')
        maximum=np.zeros(self.m)
        for j,xs in enumerate(self.site_xs):
            if self.area[self.xtype[xs]]@v[xs]+docs[j]*self.da>self.available[j]+AREA_TOL:
                raise ValueError('Original plot area exceeded')
        for p,(oi,sj) in self.edges.items():
            f=v[self.offsets[p]:self.offsets[p]+len(oi)]*1000
            if np.any(f[~opened[sj]]>0):raise ValueError('Any positive flow at closed site')
            served=np.bincount(oi,weights=f,minlength=self.n);loads=np.bincount(sj,weights=f,minlength=self.m)
            if np.any(served>self.pop+.001) or abs(served.sum()-self.target)>.001:raise ValueError('Original exact province/origin target violated')
            # Match the original physical validation in percentage units. An
            # absolute .001-resident allowance is too loose for small districts.
            if any(served[self.dd==d['id']].sum()/d['population']*100<self.s['districtFloor']-1e-6 for d in self.districts):
                raise ValueError('Original district target violated')
            if np.any(loads*self.contact>docs*self.s['contactsPerDoctor']+.1) or np.any(loads*self.bedrate>beds*365*self.occupancy+.1):
                raise ValueError('Original separate resource capacity exceeded')
            maximum=np.maximum(maximum,loads)
        return residuals,maximum

    def read_plan(self,plan):
        v=reconstruct_plan(plan,self.times,self.sites,self.h,self.s,len(self.c))
        residuals,maximum=self.validate(v);opened,beds,docs=self.resources(v)
        if any(isinstance(plan[k],bool) or not isinstance(plan[k],int) for k in ('hospitalCount','totalBeds','totalDoctors')):
            raise ValueError('Source resource totals must be integers')
        if plan['hospitalCount']!=int(opened.sum()) or plan['totalBeds']!=int(beds.sum()) or plan['totalDoctors']!=int(docs.sum()):
            raise ValueError('Source resource totals differ from original vector')
        annual=plan['annualEquivalentCostTRY']
        if isinstance(annual,bool) or not isinstance(annual,(int,float)) or not math.isfinite(annual) or abs(annual-self.cost(v))>max(.01,abs(annual)*1e-12):
            raise ValueError('Source annual cost differs from original vector')
        for site in plan['selected']:
            value=site['maximumAssignedPopulationAcrossProfiles']
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
                raise ValueError('Source maximum profile load must be finite')
            if abs(value-maximum[self.local[site['candidateIndex']]])>.001:
                raise ValueError('Source maximum profile load differs')
        if abs(finite_nonnegative(plan['annualMaterialCostTRY'],'source materials')-self.material)>max(.01,abs(self.material)*1e-12):
            raise ValueError('Source annual material bill differs')
        if abs(finite_nonnegative(plan['annualFixedResourceCostTRY'],'source fixed cost')-(self.cost(v)-self.material))>max(.01,abs(annual)*1e-12):
            raise ValueError('Source annual fixed bill differs')
        expected_ids={d['id'] for d in self.districts}
        for profile in plan['profiles']:
            p=profile['profile'];oi,sj=self.edges[p];f=v[self.offsets[p]:self.offsets[p]+len(oi)]*1000
            served=np.bincount(oi,weights=f,minlength=self.n)
            if abs(finite_nonnegative(profile['coveredPopulation'],'source profile population')-served.sum())>.001 or abs(finite_nonnegative(profile['coveragePercent'],'source profile coverage')-100*served.sum()/self.total)>1e-6:
                raise ValueError('Source profile coverage summary differs')
            mean=float(f@self.times[p][oi,sj]/self.target) if self.target else None
            if mean is None:
                if profile['meanMinutes'] is not None:raise ValueError('Zero-target mean must be absent')
            elif abs(finite_nonnegative(profile['meanMinutes'],'source mean time')-mean)>1e-6:
                raise ValueError('Source profile time summary differs')
            records=profile['districts']
            if not isinstance(records,list) or len(records)!=len(expected_ids) or {d['id'] for d in records}!=expected_ids:
                raise ValueError('Source profile district identities incomplete')
            observed={d['id']:finite_nonnegative(d['coveragePercent'],'source district coverage') for d in records}
            if any(abs(observed[d['id']]-100*served[self.dd==d['id']].sum()/d['population'])>1e-6 for d in self.districts):
                raise ValueError('Source profile district summary differs')
        return v,residuals

    def clean(self,v):
        """Resource-only cleanup; no flow clipping/drop or reassignment here."""
        before=self.cost(v);_,maximum=self.validate(v);clean=v.copy();clean[:self.nf]=0
        for j in np.flatnonzero(maximum>0):
            xs=self.site_xs[j];chosen=[int(x) for x in xs if v[x]>.5]
            if len(chosen)!=1:raise ValueError('Positive load without one source module')
            oldx=chosen[0];olddocs=int(v[self.nx+j])
            # The existing feasible choice is always retained as a fallback.
            # A numerical ceil at a capacity boundary must not increase staff.
            choices=[(self.module[self.xtype[oldx]]+olddocs*self.doc_cost,oldx,olddocs)]
            need=max(self.minimum,math.ceil(math.nextafter(maximum[j]*self.contact/self.s['contactsPerDoctor'],-math.inf)))
            if need<=olddocs:
                for x in xs:
                    t=int(self.xtype[x])
                    if self.area[t]+need*self.da<=self.available[j]+AREA_TOL and self.beds[t]*365*self.occupancy+.1>=maximum[j]*self.bedrate:
                        choices.append((self.module[t]+need*self.doc_cost,int(x),need))
            _,x,docs=min(choices);clean[x]=1;clean[self.nx+j]=docs
        try:self.validate(clean);valid=self.cost(clean)<=before+max(.01,abs(before)*1e-12)
        except ValueError:valid=False
        # No arbitrary tiny flow is discarded. If the complete resource cleanup
        # fails numerical validation, preserve the feasible pre-cleanup vector.
        final=clean if valid else v.copy()
        return final,{'applied':bool(valid),'allocationsPreserved':True,'numericFlowCorrectionResidents':0.,
            'annualCostReductionTRY':before-self.cost(final),'numericalFallbackToUncleanedResources':not valid}

    def serialize(self,v,cleanup=None):
        residuals,maximum=self.validate(v);chosen=np.flatnonzero(v[:self.nx]>.5);selected=[]
        for x in chosen:
            j,t=int(self.xsite[x]),int(self.xtype[x]);docs=int(v[self.nx+j])
            selected.append({'candidateIndex':int(self.ids[j]),'id':self.sites[j].get('id'),'templateId':self.h['templates'][t]['id'],
                'beds':int(self.beds[t]),'doctors':docs,'grossAreaM2':float(self.area[t]+docs*self.da),
                'footprintRadiusMeters':float(self.sites[j]['footprintRadiusMeters']),
                'maximumAssignedPopulationAcrossProfiles':float(maximum[j])})
        profiles=[]
        for p,(oi,sj) in self.edges.items():
            f=v[self.offsets[p]:self.offsets[p]+len(oi)]*1000;served=np.bincount(oi,weights=f,minlength=self.n)
            profiles.append({'profile':p,'coveredPopulation':float(served.sum()),'coveragePercent':100*float(served.sum())/self.total,
                'meanMinutes':float(f@self.times[p][oi,sj]/self.target) if self.target else None,
                'districts':[{'id':d['id'],'coveragePercent':100*float(served[self.dd==d['id']].sum())/d['population']} for d in self.districts],
                'allocations':[{'demandIndex':int(i),'candidateIndex':int(self.ids[j]),'population':float(a),'minutes':float(self.times[p][i,j])}
                    for i,j,a in zip(oi,sj,f) if a>0]})
        annual=self.cost(v)
        result={'status':'feasible','incumbentValidated':True,'provenOptimal':False,'costStagePerformed':False,
            'newJointAnnualBudgetTRY':None,'costGap':None,'minimumAnnualCostLowerBoundTRY':None,
            'selected':selected,'profiles':profiles,'hospitalCount':len(selected),'totalBeds':sum(s['beds'] for s in selected),
            'totalDoctors':sum(s['doctors'] for s in selected),'annualEquivalentCostTRY':annual,
            'annualMaterialCostTRY':self.material,'annualFixedResourceCostTRY':annual-self.material,
            'scope':'Validated plan in the supplied shared-resource model. No policy-budget, real-city or minimum hospital-count claim.',
            'annualDemandCountedOnce':True,'secondTravelStageImplemented':False,
            'originalModelResiduals':residuals,'resourceCleanup':cleanup,
            'profileReassignmentPerformed':False,'sameIndividualsAcrossProfilesConstrained':False}
        # Round-trip the actual serialized identities, resources and every
        # positive flow through the original complete model once more.
        back,_=self.read_plan(result)
        if np.max(np.abs(back-v),initial=0)>1e-12:raise ValueError('Serialized flow/resource roundtrip differs')
        return result


def build_joint_problem(profile_times,populations,demand_districts,districts,province_total,
                        candidates,planning,scenario,conflicts=()):
    """Build all supplied candidate/profile edges without invoking a solver."""
    started=monotonic()
    def positive(v, name, zero=False):
        if isinstance(v, (bool, np.bool_)) or not np.isfinite(v) or (v < 0 if zero else v <= 0):
            raise ValueError('Invalid ' + name)
        return float(v)
    total = positive(province_total, 'province population')
    pop = np.asarray(populations, dtype=float); dd = np.asarray(demand_districts)
    if pop.ndim != 1 or not len(pop) or pop.shape != dd.shape or np.any(~np.isfinite(pop)) or np.any(pop < 0) or pop.sum() > total + 1e-6:
        raise ValueError('Invalid located population or denominator')
    if not districts or not candidates or not isinstance(profile_times, dict) or len(profile_times)!=4:
        raise ValueError('Candidates, districts and named profiles required')
    if any(not isinstance(p, str) or not p for p in profile_times):
        raise ValueError('Invalid profile names')
    district_ids = [d['id'] for d in districts]
    denoms = np.array([positive(d['population'], 'district population') for d in districts])
    if len(set(district_ids)) != len(districts) or not set(dd).issubset(district_ids) or not np.isclose(denoms.sum(), total, rtol=1e-10, atol=1e-6):
        raise ValueError('District identity/denominators invalid')
    if any(pop[dd == d['id']].sum() > d['population'] + 1e-6 for d in districts):
        raise ValueError('District located population exceeds denominator')
    ids = [s['candidateIndex'] for s in candidates]
    if any(isinstance(i, bool) or not isinstance(i, (int, np.integer)) or i < 0 for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('Invalid candidate identities')
    id_to_local = {value: i for i, value in enumerate(ids)}
    local_conflicts = set()
    for pair in conflicts:
        if len(pair) != 2 or pair[0] not in id_to_local or pair[1] not in id_to_local or pair[0] == pair[1]:
            raise ValueError('Invalid plot conflict')
        local_conflicts.add(tuple(sorted((id_to_local[pair[0]], id_to_local[pair[1]]))))
    threshold = positive(scenario['threshold'], 'threshold')
    coverage = positive(scenario['coverageTarget'], 'coverage', zero=True)
    district_floor = positive(scenario['districtFloor'], 'district floor', zero=True)
    occupancy = positive(scenario['bedOccupancy'], 'occupancy') / 100
    if max(coverage, district_floor) > 100 or occupancy > 1:
        raise ValueError('Percent outside range')
    demand = positive(scenario['demandMultiplier'], 'demand multiplier')
    throughput = positive(scenario['contactsPerDoctor'], 'physician throughput')
    operating = positive(scenario.get('operatingCostMultiplier', 1), 'operating multiplier')
    tolerance = positive(scenario.get('costTolerance', 10), 'cost tolerance', zero=True) / 100
    hospital_limit = scenario.get('hospitalLimit')
    if hospital_limit is not None and (isinstance(hospital_limit, bool) or int(hospital_limit) != hospital_limit or hospital_limit < 0):
        raise ValueError('Invalid hospital limit')
    design, rates, eco = planning['design'], planning['rates'], planning['economics']
    min_docs = positive(design['minimumDoctorsPerSite'], 'minimum physicians')
    if int(min_docs) != min_docs: raise ValueError('Minimum physicians must be integer')
    doctor_area = positive(design['areaPerDoctorM2'], 'physician area')
    floors = positive(design['maxFloors'], 'floor limit')
    radii = np.array([positive(s['footprintRadiusMeters'], 'plot radius') for s in candidates])
    available = np.pi * radii ** 2 * floors
    contact = positive(rates['contactsPerResident'], 'contact rate') * demand
    bedrate = positive(rates['bedDaysPerResident'], 'bed-day rate') * demand
    templates = planning['templates']
    if not templates or len({x['id'] for x in templates}) != len(templates): raise ValueError('Invalid templates')
    beds = np.array([positive(x['beds'], 'beds') for x in templates])
    area = np.array([positive(x['grossAreaM2'], 'template area') for x in templates])
    if np.any(beds != np.rint(beds)): raise ValueError('Beds must be integer')
    for key in ('buildingUnitCostTRY', 'annualFixedSiteCostTRY', 'annualDoctorCostTRY', 'annualBedSupportCostTRY', 'costPerContactTRY', 'realDiscountRate'):
        positive(eco[key], key, zero=True)
    years = positive(eco['horizonYears'], 'cost horizon'); r = eco['realDiscountRate']
    annuity = r / (1 - (1 + r) ** -years) if r else 1 / years
    n, m = len(pop), len(candidates); target = total * coverage / 100
    def failure(status, reason):
        raise ModelInfeasible(reason)
    profile_edges = {}; matrices = {}
    for name, raw in profile_times.items():
        t = np.asarray(raw, dtype=float)
        if t.shape != (n, m) or np.any(np.isnan(t)) or np.any(t < 0): raise ValueError('Invalid matrix')
        matrices[name] = t; oi, sj = np.where(np.isfinite(t) & (t <= threshold)); profile_edges[name] = (oi, sj)
    if target > pop.sum() + 1e-6 or target < denoms.sum() * district_floor / 100 - 1e-6:
        return failure('infeasible', 'Exact target conflicts with located population or district floors within this model.')
    for name, t in matrices.items():
        accessible = (np.isfinite(t) & (t <= threshold)).any(axis=1)
        if pop[accessible].sum() < target - 1e-6 or any(pop[accessible & (dd == d['id'])].sum() < d['population'] * district_floor / 100 - 1e-6 for d in districts):
            return failure('infeasible', 'All supplied candidates fail geographic targets in ' + name)
    eligible = area[None, :] + min_docs * doctor_area <= available[:, None] + AREA_TOL
    xsite, xtype = np.where(eligible); nx = len(xsite); nf = nx + m
    if not nx: return failure('infeasible', 'No supplied plot fits minimum resources.')
    site_xs = [np.flatnonzero(xsite == j) for j in range(m)]
    max_docs = np.maximum(0, np.floor(np.nextafter((available + AREA_TOL - area.min()) / doctor_area, np.inf)))
    max_docs = np.minimum(max_docs, max(min_docs, math.ceil(target * contact / throughput)))
    max_docs[~eligible.any(axis=1)] = 0
    offsets = {}; nv = nf
    for name, (oi, _) in profile_edges.items(): offsets[name] = nv; nv += len(oi)
    module_cost = area * eco['buildingUnitCostTRY'] * annuity + operating * (eco['annualFixedSiteCostTRY'] + beds * eco['annualBedSupportCostTRY'])
    doc_cost = doctor_area * eco['buildingUnitCostTRY'] * annuity + operating * eco['annualDoctorCostTRY']
    material = target * contact * eco['costPerContactTRY'] * operating
    cost_scale = max(1., float(module_cost.max()), doc_cost)
    c = np.r_[module_cost[xtype], np.full(m, doc_cost), np.zeros(nv - nf)] / cost_scale
    integer = np.r_[np.ones(nf), np.zeros(nv - nf)]
    lb = np.zeros(nv); ub = np.r_[np.ones(nx), max_docs, np.concatenate([pop[oi] / 1000 for oi, _ in profile_edges.values()])]
    rows, cols, values, lo, hi = [], [], [], [], []
    def row(indices, vals, lower=-np.inf, upper=np.inf):
        rows.extend([len(lo)] * len(indices)); cols.extend(indices); values.extend(vals); lo.append(lower); hi.append(upper)
    for j, xs in enumerate(site_xs):
        ts = xtype[xs]; dj = nx + j
        row(xs, np.ones(len(xs)), upper=1.)
        row(np.r_[xs, dj], np.r_[np.full(len(xs), min_docs), -1.], upper=0.)
        # When closed, positive physician area forces staff to zero.
        row(np.r_[xs, dj], np.r_[(area[ts] - available[j]) / doctor_area, 1.], upper=0.)
    for a, b in sorted(local_conflicts):
        xs = np.r_[site_xs[a], site_xs[b]]; row(xs, np.ones(len(xs)), upper=1.)
    if hospital_limit is not None: row(np.arange(nx), np.ones(nx), upper=hospital_limit)
    def groups(indices, count):
        order = np.argsort(indices, kind='stable'); sizes = np.bincount(indices, minlength=count)
        return np.split(order, np.cumsum(sizes)[:-1])
    for name, (oi, sj) in profile_edges.items():
        fs = offsets[name] + np.arange(len(oi))
        for i, es in enumerate(groups(oi, n)): row(fs[es], np.ones(len(es)), upper=pop[i] / 1000)
        for j, es in enumerate(groups(sj, m)):
            xs = site_xs[j]
            row(np.r_[xs, fs[es]], np.r_[-beds[xtype[xs]] * 365 * occupancy / bedrate / 1000, np.ones(len(es))], upper=0.)
            row(np.r_[nx + j, fs[es]], np.r_[-throughput / contact / 1000, np.ones(len(es))], upper=0.)
        row(fs, np.ones(len(fs)), lower=target / 1000, upper=target / 1000)
        for d in districts:
            es = np.flatnonzero(dd[oi] == d['id']); row(fs[es], np.ones(len(es)), lower=d['population'] * district_floor / 100 / 1000)
    A = coo_matrix((values, (rows, cols)), shape=(len(lo), nv)).tocsc(); lo, hi = np.asarray(lo), np.asarray(hi)
    if np.any(~np.isfinite(c)) or np.any(~np.isfinite(A.data)) or np.any(~np.isfinite(lb)) or np.any(~np.isfinite(ub)):
        raise ValueError('Nonfinite derived formulation coefficients/bounds')
    return JointProblem(times=matrices,pop=pop,dd=dd,districts=districts,total=total,
        sites=candidates,h=planning,s=scenario,n=n,m=m,target=target,ids=ids,local=id_to_local,
        conflicts=tuple(conflicts),model=(c,integer,lb,ub,A,lo,hi),c=c,minimum=int(min_docs),
        da=doctor_area,available=available,beds=beds,area=area,xsite=xsite,xtype=xtype,
        nx=nx,nf=nf,site_xs=site_xs,contact=contact,bedrate=bedrate,occupancy=occupancy,
        q=throughput/contact/1000,bedcap=beds*365*occupancy/bedrate/1000,module=module_cost,
        doc_cost=doc_cost,cost_scale=cost_scale,material=material,edges=profile_edges,offsets=offsets,
        buildSeconds=monotonic()-started,dimensions={'binaryTemplates':nx,'integerPhysicians':m,
            'flowVariables':nv-nf,'variables':nv,'constraints':A.shape[0],'nonzeros':A.nnz,'conflicts':len(local_conflicts)})
