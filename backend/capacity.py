"""Capacitated, splittable location-allocation with a cost/time epsilon constraint.

Flows are thousands of residents' annual demand, not a count of unique patients.
Two independent resource constraints apply at every site: visits and bed-days.
"""
import numpy as np
import highspy
from types import SimpleNamespace
from time import monotonic
from scipy.optimize import Bounds
from scipy.sparse import coo_matrix, csr_matrix, vstack
from backend.optimizer import weighted_quantile


def annualization(planning):
    economics = planning['economics']
    r, years = economics['realDiscountRate'], economics['horizonYears']
    return r / (1 - (1 + r) ** -years) if r else 1 / years


def optimize(objective, integrality, bounds, A, lower, upper, time_limit, seed=None):
    """Use the native HiGHS API so a checked incumbent survives time limits."""
    A = A.tocsc()
    lp = highspy.HighsLp()
    lp.num_col_, lp.num_row_ = A.shape[1], A.shape[0]
    lp.col_cost_ = objective
    lp.col_lower_, lp.col_upper_ = bounds.lb, bounds.ub
    lp.row_lower_, lp.row_upper_ = lower, upper
    lp.a_matrix_.start_, lp.a_matrix_.index_, lp.a_matrix_.value_ = A.indptr, A.indices, A.data
    if np.any(integrality):
        lp.integrality_ = [highspy.HighsVarType.kInteger if i else highspy.HighsVarType.kContinuous for i in integrality]
    solver = highspy.Highs()
    solver.setOptionValue('output_flag', False)
    solver.setOptionValue('threads', 1)
    solver.setOptionValue('random_seed', 7)
    solver.setOptionValue('time_limit', time_limit)
    solver.setOptionValue('mip_rel_gap', .002)
    solver.passModel(lp)
    if seed is not None:
        supplied = highspy.HighsSolution()
        supplied.col_value = seed
        solver.setSolution(supplied)
    solver.run()
    info, solution, status = solver.getInfo(), solver.getSolution(), solver.getModelStatus()
    valid = info.primal_solution_status == highspy.SolutionStatus.kSolutionStatusFeasible
    return SimpleNamespace(x=np.array(solution.col_value) if valid else None,
        status=0 if status == highspy.HighsModelStatus.kOptimal else (2 if status == highspy.HighsModelStatus.kInfeasible else 1),
        mip_gap=info.mip_gap, mip_dual_bound=info.mip_dual_bound)


def solve_capacity(times, populations, demand_districts, districts, province_total,
                   planning, threshold=30, coverage_target=.95, district_floor=.8,
                   demand_multiplier=1., bed_occupancy=.8, contacts_per_doctor=2140,
                   cost_tolerance=.1, time_limit=35, neighbors=12, conflicts=(),
                   plot_radii=None, hospital_limit=None, operating_cost_multiplier=1.):
    """Choose a bed module AND an independent integer physician headcount.

    x[j,t] is a bed-module binary, d[j] physician integer, f[i,j] thousands of
    resident-equivalents. The two resources share a site but not a fixed ratio.
    All building area (including physician space) must fit its audited plot.
    Costs are equivalent annual constant-price TRY, including operations.
    """
    populations = np.asarray(populations, dtype=float)
    demand_districts = np.asarray(demand_districts)
    n, m = times.shape
    within = np.isfinite(times) & (times <= threshold)
    possible = within.any(axis=1)
    maximum = float(populations[possible].sum() / province_total)
    ceilings = [{'id':d['id'],'name':d['name'],'maximumPercent':
        100*float(populations[(demand_districts==d['id']) & possible].sum())/d['population']} for d in districts]
    limiting = [d for d in ceilings if d['maximumPercent']+1e-7 < 100*district_floor]
    if maximum+1e-9 < coverage_target or limiting or not n or not m:
        return {'status':'infeasible','reason':'Yol ağı ve süre sınırı erişim hedefini karşılamıyor.',
                'maximumCoveragePercent':maximum*100,'limitingDistricts':limiting,
                'infeasibilityScope':'all_candidates_geography'}
    radii = np.full(m,210.) if plot_radii is None else np.asarray(plot_radii,dtype=float)
    origin, dest = [], []
    # Retain nearest sites in EVERY footprint class, so large plots are not
    # silently pruned behind nearby small sites that cannot hold a large hospital.
    groups = np.unique(radii)
    for i in range(n):
        for radius in groups:
            choices=np.flatnonzero(within[i] & (radii==radius))
            if neighbors is not None:
                choices=choices[np.argsort(times[i,choices],kind='stable')[:neighbors]]
            origin.extend([i]*len(choices)); dest.extend(choices.tolist())
    origin,dest=np.asarray(origin,dtype=int),np.asarray(dest,dtype=int)
    sites=np.unique(dest); lookup={int(j):v for v,j in enumerate(sites)}
    local=np.asarray([lookup[int(j)] for j in dest]); edge_times=times[origin,dest]
    templates=planning['templates']; eco=planning['economics']; design=planning['design']
    k,h,e=len(templates),len(sites),len(origin)
    nx=h*k; nd=nx+h; nv=nd+e
    beds=np.array([t['beds'] for t in templates],dtype=float)
    area=np.array([t['grossAreaM2'] for t in templates],dtype=float)
    contact_rate=planning['rates']['contactsPerResident']*demand_multiplier
    visit_rate=planning['rates']['visitsPerResident']*demand_multiplier
    bed_rate=planning['rates']['bedDaysPerResident']*demand_multiplier
    admission_rate=planning['rates']['admissionsPerResident']*demand_multiplier
    area_per_doc=design['areaPerDoctorM2']; min_docs=design['minimumDoctorsPerSite']
    available_area=np.pi*radii[sites]**2*design['maxFloors']
    doctor_limits=np.maximum(0,np.floor((available_area[:,None]-area)/area_per_doc)).astype(int)
    eligible=doctor_limits>=min_docs
    max_docs=np.max(np.where(eligible,doctor_limits,0),axis=1)
    bed_residents=beds*365*bed_occupancy/bed_rate/1000
    doc_residents=contacts_per_doctor/contact_rate/1000
    capacity=np.minimum(bed_residents[None,:],doctor_limits*doc_residents)
    capacity[~eligible]=0
    crf=annualization(planning); unit=eco['buildingUnitCostTRY']; om=operating_cost_multiplier
    fixed_cost=(area*unit*crf+om*(eco['annualFixedSiteCostTRY']+beds*eco['annualBedSupportCostTRY']))/1e9
    doctor_cost=(area_per_doc*unit*crf+om*eco['annualDoctorCostTRY'])/1e9
    contact_cost=eco['costPerContactTRY']*contact_rate*1000*om/1e9
    objective=np.r_[np.tile(fixed_cost,h),np.full(h,doctor_cost),np.full(e,contact_cost)]
    integrality=np.r_[np.ones(nd),np.zeros(e)]
    bounds=Bounds(np.zeros(nv),np.r_[eligible.ravel().astype(float),max_docs,populations[origin]/1000])
    rows,cols,values,lower,upper=[],[],[],[],[]
    def row(indices,vals,lo=-np.inf,hi=np.inf):
        rows.extend([len(lower)]*len(indices)); cols.extend(indices); values.extend(vals)
        lower.append(lo); upper.append(hi)
    flow=nd+np.arange(e)
    origin_edges=[np.flatnonzero(origin==i) for i in range(n)]
    site_edges=[np.flatnonzero(local==j) for j in range(h)]
    for i,es in enumerate(origin_edges): row(flow[es],np.ones(len(es)),hi=populations[i]/1000)
    for j,es in enumerate(site_edges):
        xs=j*k+np.arange(k); dj=nx+j
        row(xs,np.ones(k),hi=1)
        row(np.r_[xs,dj],np.r_[-np.where(eligible[j],doctor_limits[j],0),1.],hi=0)
        row(np.r_[xs,dj],np.r_[np.full(k,min_docs),-1.],hi=0)
        row(np.r_[xs,flow[es]],np.r_[-bed_residents,np.ones(len(es))],hi=0)
        row(np.r_[dj,flow[es]],np.r_[-doc_residents,np.ones(len(es))],hi=0)
    local_conflicts={}
    for a,b in conflicts:
        if a in lookup and b in lookup:
            a,b=lookup[a],lookup[b]
            row(np.r_[a*k+np.arange(k),b*k+np.arange(k)],np.ones(2*k),hi=1)
            local_conflicts.setdefault(a,set()).add(b); local_conflicts.setdefault(b,set()).add(a)
    row(flow,np.ones(e),lo=province_total*coverage_target/1000)
    for d in districts:
        es=np.flatnonzero(demand_districts[origin]==d['id'])
        row(flow[es],np.ones(len(es)),lo=d['population']*district_floor/1000)
    if hospital_limit is not None: row(np.arange(nx),np.ones(nx),hi=hospital_limit)
    A=coo_matrix((values,(rows,cols)),shape=(len(lower),nv)).tocsc()
    lower,upper=np.asarray(lower),np.asarray(upper)
    def valid(v):
        if v is None: return False
        activity=A@v
        return bool(np.all(activity>=lower-1e-6) and np.all(activity<=upper+1e-6)
                    and np.all(v>=bounds.lb-1e-6) and np.all(v<=bounds.ub+1e-6)
                    and np.max(np.abs(v[:nd]-np.rint(v[:nd])))<1e-5)
    def fit(j,load):
        doctors=max(min_docs,int(np.ceil(load/doc_residents-1e-9)))
        ts=np.flatnonzero((capacity[j]>=load-1e-8)&eligible[j]&(doctor_limits[j]>=doctors))
        if not len(ts): return None
        typ=int(ts[np.argmin(fixed_cost[ts])]); return typ,doctors
    relaxation=optimize(objective,np.zeros(nv),bounds,A,lower,upper,min(12,time_limit))
    seed=None
    if relaxation.x is not None:
        rounded=relaxation.x.copy(); rounded[:nd]=0
        loads=np.bincount(local,weights=rounded[nd:],minlength=h)
        for j,load in enumerate(loads):
            if load<1e-8: continue
            option=fit(j,load)
            if option is None: break
            typ,doctors=option; rounded[j*k+typ]=1; rounded[nx+j]=doctors
        else:
            if valid(rounded): seed=rounded
    # A separate constructive start. It buys actual needed physicians, not the
    # maximum staff allowed in a footprint. The MILP may replace every choice.
    remaining=populations/1000; allocation=np.zeros(e); chosen=np.full(h,-1,dtype=int)
    loads=np.zeros(h); doctors=np.zeros(h,dtype=int); spent=np.zeros(h)
    district_index={d['id']:i for i,d in enumerate(districts)}
    di=np.array([district_index[d] for d in demand_districts])
    quota=np.array([d['population']*district_floor/1000 for d in districts])
    sorted_edges=[es[np.argsort(edge_times[es],kind='stable')] for es in site_edges]
    started=monotonic()
    for phase in (0,1):
        for _ in range(h*(k+1)+1):
            need=max(0.,province_total*coverage_target/1000-allocation.sum())
            if (phase==0 and quota.max()<1e-7) or (phase==1 and need<1e-7): break
            if monotonic()-started>max(15,time_limit): break
            count=int((chosen>=0).sum()); best=None
            for j,es in enumerate(sorted_edges):
                if chosen[j]<0 and (hospital_limit is not None and count>=hospital_limit): continue
                if chosen[j]<0 and any(chosen[v]>=0 for v in local_conflicts.get(j,())): continue
                residents=origin[es]
                available=(float(np.minimum(np.bincount(di[residents],weights=remaining[residents],minlength=len(districts)),np.maximum(quota,0)).sum())
                           if phase==0 else min(float(remaining[residents].sum()),need))
                if available<1e-8: continue
                for typ in np.flatnonzero(eligible[j]):
                    if chosen[j]>=0 and beds[typ]<beds[chosen[j]]: continue
                    amount=min(available,capacity[j,typ]-loads[j])
                    if amount<1e-8: continue
                    dc=max(min_docs,int(np.ceil((loads[j]+amount)/doc_residents-1e-9)))
                    cost=fixed_cost[typ]+doctor_cost*dc
                    score=amount/max(cost-spent[j],1e-10)
                    if best is None or score>best[0]: best=(score,j,typ,amount,dc,cost)
            if best is None: break
            _,j,typ,amount,dc,cost=best
            chosen[j]=typ; doctors[j]=dc; spent[j]=cost
            for edge in sorted_edges[j]:
                i=origin[edge]
                take=min(amount,remaining[i],max(0,quota[di[i]]) if phase==0 else amount)
                if take>0:
                    allocation[edge]+=take; remaining[i]-=take; loads[j]+=take; quota[di[i]]-=take; amount-=take
                if amount<1e-8: break
    greedy=np.zeros(nv)
    for j in np.flatnonzero(chosen>=0): greedy[j*k+chosen[j]]=1; greedy[nx+j]=doctors[j]
    greedy[nd:]=allocation
    if valid(greedy) and (seed is None or objective@greedy<objective@seed): seed=greedy
    first=optimize(objective,integrality,bounds,A,lower,upper,time_limit,seed)
    scope={'nearestCandidatesPerFootprintClass':neighbors,'footprintClasses':groups.tolist(),
           'candidateCount':h,'allocationEdges':e,'fullCandidateCount':m,'allAllocationEdges':neighbors is None}
    if first.x is None:
        # Restricted-edge infeasibility is NOT a proof over the full candidate set.
        proven=first.status==2 and neighbors is None
        return {'status':'infeasible' if proven else 'inconclusive',
            'reason':('Tüm adaylar altında kapasite ve erişim koşulları birlikte sağlanamıyor.' if proven else
                      'Süre sınırlı ve daraltılmış aramada geçerli plan bulunamadı; bu sonuç imkânsızlık ispatı değildir.'),
            'maximumCoveragePercent':maximum*100,'limitingDistricts':limiting,'searchScope':scope}
    if not valid(first.x): raise RuntimeError('Invalid first-stage incumbent')
    reference_cost=float(objective@first.x); reference_served=float(first.x[nd:].sum())
    first_minutes=float(first.x[nd:]@edge_times/reference_served); budget=reference_cost*(1+cost_tolerance)
    extra=csr_matrix(np.vstack([objective,np.r_[np.zeros(nd),np.ones(e)]]))
    travel_A=vstack([A,extra],format='csc'); travel_lo=np.r_[lower,-np.inf,reference_served]
    travel_hi=np.r_[upper,budget+1e-8,reference_served]
    travel_obj=np.r_[np.zeros(nd),edge_times/province_total*1000]
    # Reallocate with chosen facilities/staff fixed to make a fast, safe start.
    fixed=Bounds(np.r_[np.rint(first.x[:nd]),bounds.lb[nd:]],np.r_[np.rint(first.x[:nd]),bounds.ub[nd:]])
    allocation_lp=optimize(travel_obj,np.zeros(nv),fixed,travel_A,travel_lo,travel_hi,min(8,time_limit))
    travel_seed=allocation_lp.x if allocation_lp.x is not None else first.x
    second=optimize(travel_obj,integrality,bounds,travel_A,travel_lo,travel_hi,time_limit,travel_seed)
    solution=first.x
    if second.x is not None and valid(second.x) and objective@second.x<=budget+1e-6 and abs(second.x[nd:].sum()-reference_served)<1e-5 and travel_obj@second.x<=travel_obj@first.x+1e-8:
        solution=second.x
    elif valid(travel_seed) and objective@travel_seed<=budget+1e-6 and travel_obj@travel_seed<=travel_obj@first.x+1e-8:
        solution=travel_seed
    if not valid(solution): raise RuntimeError('Invalid final resource allocation')
    x=np.rint(solution[:nx]).reshape(h,k); ds=np.rint(solution[nx:nd]).astype(int)
    allocation=np.maximum(solution[nd:],0)*1000
    selected=[(j,int(np.argmax(x[j]))) for j in range(h) if x[j].sum()>.5]
    loads=np.bincount(dest,weights=allocation,minlength=m); capacity_sites=[]
    for lj,ti in selected:
        j=int(sites[lj]); t=templates[ti]; doctors=int(ds[lj]); assigned=float(loads[j])
        gross_area=t['grossAreaM2']+area_per_doc*doctors
        capex=gross_area*unit
        contact_capacity=doctors*contacts_per_doctor
        bed_capacity=t['beds']*365*bed_occupancy
        operating={
            'fixedSiteTRY':om*eco['annualFixedSiteCostTRY'],
            'physiciansTRY':om*doctors*eco['annualDoctorCostTRY'],
            'bedSupportTRY':om*t['beds']*eco['annualBedSupportCostTRY'],
            'materialsTRY':om*assigned*contact_rate*eco['costPerContactTRY']}
        opex=sum(operating.values())
        capacity_sites.append({'candidateIndex':j,'templateId':t['id'],'templateLabel':t['label'],
            'beds':t['beds'],'doctors':doctors,'grossAreaM2':gross_area,'constructionCostTRY':capex,
            'annualOperatingCostTRY':opex,'annualEquivalentCostTRY':capex*crf+opex,'operatingBreakdown':operating,
            'assignedPopulation':assigned,'annualVisits':assigned*visit_rate,'annualContacts':assigned*contact_rate,
            'annualAdmissions':assigned*admission_rate,'annualBedDays':assigned*bed_rate,
            'contactCapacity':contact_capacity,'bedDayCapacity':bed_capacity,
            'doctorUtilizationPercent':assigned*contact_rate/contact_capacity*100,
            'bedUtilizationPercent':assigned*bed_rate/bed_capacity*100,
            'physicalOccupancyPercent':assigned*bed_rate/(t['beds']*365)*100,
            'areaUtilizationPercent':gross_area/available_area[lj]*100})
    served=np.bincount(origin,weights=allocation,minlength=n)
    def summary(mask,total):
        w=allocation[mask]; covered=float(w.sum()); unserved=max(0.,total-covered)
        return {'coveredPopulation':covered,'coveragePercent':covered/total*100,
            'reachablePopulation':covered,'unreachableOrUnlocatedPopulation':unserved,'meanPopulationDenominator':covered,
            'meanMinutes':float(np.average(edge_times[mask],weights=w)) if covered else None,
            'p90Minutes':weighted_quantile(np.r_[edge_times[mask],np.inf],np.r_[w,unserved],.9)}
    actual=summary(np.ones(e,dtype=bool),province_total)
    district_metrics=[{**d,**summary(demand_districts[origin]==d['id'],d['population'])} for d in districts]
    assignments=[]
    for i,es in enumerate(origin_edges):
        es=es[allocation[es]>1e-7]; es=es[np.argsort(-allocation[es])]
        parts=[{'candidateIndex':int(dest[a]),'population':float(allocation[a]),
                'fraction':float(allocation[a]/populations[i]),'minutes':float(edge_times[a])} for a in es]
        primary=parts[0] if parts else None
        assignments.append({'candidateIndex':primary['candidateIndex'] if primary else None,
            'minutes':primary['minutes'] if primary else None,'servedFraction':float(served[i]/populations[i]),
            'covered':bool(served[i]>=populations[i]-1e-4),'allocations':parts})
    total_beds=sum(c['beds'] for c in capacity_sites); total_docs=sum(c['doctors'] for c in capacity_sites)
    capex=sum(c['constructionCostTRY'] for c in capacity_sites); opex=sum(c['annualOperatingCostTRY'] for c in capacity_sites)
    annual_cost=capex*crf+opex
    if abs(annual_cost-objective@solution*1e9)>100 or annual_cost>budget*1e9+100:
        raise RuntimeError('Annual cost reconstruction mismatch')
    if hospital_limit is not None and len(selected)>hospital_limit: raise RuntimeError('Site limit violated')
    def finite(v): return float(v) if v is not None and np.isfinite(v) else None
    return {'status':'feasible','selectedIndices':[int(sites[j]) for j,_ in selected],
        'hospitalCount':len(selected),'gap':finite(first.mip_gap),'lowerBound':finite(first.mip_dual_bound*1e9),
        'secondaryOptimal':bool(second.x is not None and second.status==0 and second.mip_gap<=1e-8),
        'metrics':actual,'districts':district_metrics,'assignments':assignments,'capacitySites':capacity_sites,
        'capacity':{'totalBeds':total_beds,'totalDoctors':total_docs,'constructionCostTRY':capex,
            'annualOperatingCostTRY':opex,'annualEquivalentCostTRY':annual_cost,
            'lifecyclePresentCostTRY':annual_cost/crf,'priceBase':eco['priceBase'],
            'horizonYears':eco['horizonYears'],'realDiscountRate':eco['realDiscountRate'],
            'referenceCostTRY':reference_cost*1e9,'budgetLimitTRY':budget*1e9,
            'referenceMeanMinutes':first_minutes,'travelImprovementPercent':100*(first_minutes-actual['meanMinutes'])/first_minutes if first_minutes else 0,
            'annualVisitsDemand':province_total*visit_rate,'annualVisitsServed':actual['coveredPopulation']*visit_rate,
            'annualContactsDemand':province_total*contact_rate,'annualContactsServed':actual['coveredPopulation']*contact_rate,
            'annualAdmissionsDemand':province_total*admission_rate,'annualBedDaysDemand':province_total*bed_rate,
            'annualBedDaysServed':actual['coveredPopulation']*bed_rate,
            'doctorUtilizationPercent':actual['coveredPopulation']*contact_rate/(total_docs*contacts_per_doctor)*100,
            'bedUtilizationPercent':actual['coveredPopulation']*bed_rate/(total_beds*365*bed_occupancy)*100,
            'costStageGap':finite(first.mip_gap),'costStageProvenOptimal':first.status==0 and first.mip_gap<=1e-8,
            'travelStageGap':finite(second.mip_gap) if second.x is not None else None,
            'travelStageImproved':actual['meanMinutes']<first_minutes-1e-7,'planningVersion':planning['version']},
        'searchScope':scope}
